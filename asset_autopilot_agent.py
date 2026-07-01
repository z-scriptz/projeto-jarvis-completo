# agents/asset_autopilot_agent.py
# Asset Autopilot Agent v1 do AgenteIA (Jarvis).
#
# Resolve o gargalo "humano alimenta a inbox na mão": coleta assets sozinho
# de fontes SEGURAS, baixa pra inbox, dispara o Asset Hunter, reavalia.
#
# Fontes v1 (em ordem de tentativa):
#   A) Asset_Sources no Google Sheets — URLs curadas pelo usuário (NÃO implementado v1;
#      stub deixado pra integração futura com asset_collector_agent)
#   B) URLs diretas — arquivos .jpg/.png/.mp4/.webp/.mov passados via --url
#   C) og:image de página de produto — Shopee/Amazon/Mercado Livre/AliExpress
#      (NÃO Instagram/TikTok/YouTube — recusa explícita)
#   D) Pexels API (PEXELS_API_KEY env) — fotos + vídeos comerciais permitidos
#   E) Pixabay API (PIXABAY_API_KEY env) — fotos + vídeos CC0
#
# Filosofia:
#   - NUNCA chama Gemini
#   - APIs gratuitas best-effort: se não tiver chave, pula silenciosamente
#   - Sempre prefixa arquivos com fonte (pexels_, pixabay_, ogimage_, url_direct_)
#   - Reaproveita Asset Hunter pra organizar (não duplica lógica)
#
# Sobre licenças:
#   - Pexels: uso comercial OK, atribuição RECOMENDADA (não obrigatória)
#   - Pixabay: CC0 (sem atribuição obrigatória)
#   - Shopee/Amazon og:image: zona cinza, mas pra afiliado é prática comum
#   - Em todo caso: vídeo do afiliado é DERIVADO + transformativo
#
# Uso:
#   python -m agents.asset_autopilot_agent --produto "Cinto Modelador Slim Feminino"
#   python -m agents.asset_autopilot_agent --produto "X" --dry-run
#   python -m agents.asset_autopilot_agent --produto "X" --max-downloads 10
#   python -m agents.asset_autopilot_agent --produto "X" --ate-pronto
#   python -m agents.asset_autopilot_agent --produto "X" --query "waist trainer"
#   python -m agents.asset_autopilot_agent --produto "X" --url https://...img.jpg
#   python -m agents.asset_autopilot_agent --produto "X" --pagina https://shopee...

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from shared.logger import get_logger

from agents.asset_agent import (
    slugificar_produto,
    verificar_assets_produto,
)

log = get_logger(__name__)

# =================================================================
# CONFIGURAÇÃO
# =================================================================

PROJETO_ROOT = Path(__file__).parent.parent
INBOX_DIR    = PROJETO_ROOT / "assets" / "inbox"
# Subpastas que o Asset Hunter espera (não baixa em inbox/ raiz)
INBOX_VIDEOS = INBOX_DIR / "videos"
INBOX_IMGS   = INBOX_DIR / "imagens"
PLANS_DIR    = PROJETO_ROOT / "shared" / "content_plans"

# Extensões aceitas
EXT_VIDEO = {".mp4", ".mov", ".m4v", ".webm"}
EXT_IMG   = {".jpg", ".jpeg", ".png", ".webp"}
EXT_ACEITAS = EXT_VIDEO | EXT_IMG


def _subpasta_destino(ext: str) -> Path:
    """Roteia por extensão: .mp4→inbox/videos/, .jpg→inbox/imagens/."""
    if ext.lower() in EXT_VIDEO:
        return INBOX_VIDEOS
    if ext.lower() in EXT_IMG:
        return INBOX_IMGS
    return INBOX_DIR  # fallback raiz (não deveria acontecer)

# Sites bloqueados (NUNCA tentamos baixar conteúdo deles)
SITES_BLOQUEADOS = (
    "tiktok.com", "instagram.com", "youtube.com", "youtu.be",
    "facebook.com", "twitter.com", "x.com", "linkedin.com",
    "reels.", "reddit.com", "pinterest.com",
)

# Sites permitidos pra extração de og:image
SITES_ECOMMERCE_OK = (
    "shopee.com.br", "shopee.com", "amazon.com", "amazon.com.br",
    "mercadolivre.com.br", "mercadolibre.com", "aliexpress.com",
    "magalu.com.br", "magazineluiza.com.br", "americanas.com.br",
    "casasbahia.com.br", "kabum.com.br",
)

# Limites
MAX_DOWNLOADS_DEFAULT     = 5
MAX_CICLOS_ATE_PRONTO     = 5
SCORE_OBJETIVO            = 60   # score >= isso = pronto
TAMANHO_MIN_IMG_KB        = 20   # imagens menores que isso = thumbnail/lixo
TAMANHO_MIN_VIDEO_KB      = 100
TAMANHO_MAX_MB            = 50
TIMEOUT_REQUEST_SEG       = 20
RATE_LIMIT_ENTRE_REQS_SEG = 3.0  # 3s entre requests p/ não estressar serviços
CHUNK_SIZE                = 8192

USER_AGENT = "AgenteIA-AssetAutopilot/1.0 (afiliado-shopee-tiktok)"

# =================================================================
# CATÁLOGO SEMÂNTICO (fonte primária: consulta antes de bater na API)
# =================================================================
# O catálogo (creative_engine/semantic_catalog) é a 1ª fonte de candidatos:
# 674+ clipes já indexados por embedding, com busca por CONCEITO. Antes de
# gastar request na API do Pexels/Pixabay, perguntamos ao catálogo se ele já
# conhece clipes relevantes pra essa cena. Se sim, usamos as URLs dele (0 API);
# se não (score baixo), caímos pra API clássica como sempre.
#
# IMPORTANTE: o autopilot NÃO indexa nada no catálogo. O catálogo só cresce
# (de forma limpa) via creative_engine/semantic_indexer, rodado à parte. Assim
# nunca poluímos o catálogo com lixo da API antes do Visual Audit aprovar.
#
# Import defensivo: se o catálogo não estiver disponível (lib faltando, etc),
# o autopilot funciona normal — só não usa a 1ª camada (cai direto na API).
try:
    from creative_engine.semantic_catalog import buscar as _catalogo_buscar
    _CATALOGO_OK = True
except Exception:
    _CATALOGO_OK = False

# Threshold de relevância pra aceitar um candidato do catálogo (calibrável).
# Abaixo disso, o catálogo "não tem nada bom" e caímos pra API.
CATALOGO_SCORE_MIN = 0.35
# Liga/desliga o uso do catálogo como fonte primária (CLI pode sobrescrever).
USAR_CATALOGO = True

# Dicionário PT→EN pra produtos conhecidos (melhora queries em bancos internacionais)
TRADUCAO_PRODUTO = {
    # Tech/Casa
    "mini aspirador":     ["mini vacuum", "keyboard cleaner", "desk cleaner"],
    "aspirador de teclado": ["keyboard vacuum", "computer cleaning"],
    "organizador de cabos": ["cable organizer", "cable management", "desk organizer"],
    "suporte notebook":   ["laptop stand", "notebook stand", "ergonomic laptop"],
    "lâmpada led":        ["led lamp", "smart light", "led bulb"],
    "lampada led":        ["led lamp", "smart light", "led bulb"],
    "fita led":           ["led strip", "rgb led light", "led tape"],
    "cortina led":        ["led curtain lights", "fairy lights"],
    # Beleza/Fitness
    "cinto modelador":    ["waist trainer", "body shaper belt", "slimming belt"],
    "modelador slim":     ["waist trainer", "body shaper"],
    "massageador":        ["neck massager", "massage device", "wellness device"],
    "esfoliante":         ["skincare exfoliant", "beauty routine"],
    # Beleza
    "organizador acrílico": ["makeup organizer", "vanity storage"],
    "maquiagem":          ["makeup", "beauty products"],
    # Casa
    "adesivo vedante":    ["waterproof tape", "sealing tape", "diy home repair"],
    "umidificador":       ["humidifier", "diffuser"],
    # Cozinha — traduções FECHADAS (genéricas trariam pera/planta/jardim)
    "cortador de legumes": ["vegetable chopper", "vegetable dicer", "manual food chopper"],
    "cortador de verduras": ["vegetable chopper", "vegetable cutter kitchen"],
    "cortador":           ["vegetable chopper", "food chopper kitchen"],
    "ralador":            ["kitchen grater", "vegetable grater"],
    "fatiador":           ["food slicer kitchen", "vegetable slicer"],
    "espremedor":         ["citrus juicer", "manual juicer kitchen"],
    "descascador":        ["vegetable peeler", "kitchen peeler"],
    "processador de alimentos": ["food processor", "vegetable chopper"],
    "picador":            ["food chopper", "vegetable chopper kitchen"],
}

# Por NICHO + CENA, queries genéricas que funcionam bem
QUERIES_POR_NICHO_E_CENA = {
    "Casa/Tech": {
        "dor":       ["messy desk frustrated", "dirty keyboard close up", "cluttered home office"],
        "demo":      ["product demonstration close up", "device testing", "tech unboxing"],
        "resultado": ["clean organized desk", "before after cleaning", "organized workspace"],
        "close":     ["product closeup details", "tech gadget detail"],
        "cta":       ["product on desk closeup", "hand holding gadget"],
    },
    "Beleza/Fitness": {
        "dor":       ["frustrated mirror reflection", "woman trying clothes mirror"],
        "demo":      ["woman wearing shapewear", "body shaper outfit", "waist trainer on body"],
        "resultado": ["confident woman mirror outfit", "slim waist outfit", "woman fashion mirror"],
        "close":     ["shapewear fabric closeup", "belt waist closeup"],
        "cta":       ["confident woman posing outfit", "woman fashion mirror"],
    },
    "Beleza": {
        "dor":       ["bad skin frustration", "messy beauty routine"],
        "demo":      ["beauty routine applying", "skincare application close up"],
        "resultado": ["beautiful skin glow", "before after beauty"],
        "close":     ["beauty product closeup", "cosmetic detail"],
        "cta":       ["woman applying skincare", "cosmetic product hand"],
    },
    "Casa": {
        "dor":       ["messy home cluttered", "kitchen problem mess"],
        "demo":      ["home cleaning demonstration", "household product use"],
        "resultado": ["organized clean home", "tidy organized room"],
        "close":     ["home product detail"],
        "cta":       ["product on kitchen counter", "hand using home product"],
    },
    "Cozinha": {
        # Queries FECHADAS — "cutter"/"slicer" soltos traziam pera, planta, jardim.
        # Ancoradas em "vegetable chopper/dicer" + "kitchen" pra trazer o produto certo.
        "dor":       ["messy vegetable chopping", "slow cutting vegetables knife", "kitchen prep struggle"],
        "demo":      ["vegetable chopper in use", "manual food chopper kitchen", "vegetable dicer demonstration"],
        "resultado": ["chopped vegetables bowl", "diced vegetables result", "prepped vegetables kitchen"],
        "close":     ["vegetable chopper closeup", "kitchen gadget detail"],
        "cta":       ["hand using vegetable chopper", "food chopper on counter"],
    },
    "Cozinha/Utensilio": {
        "dor":       ["messy vegetable chopping", "slow cutting vegetables knife", "kitchen prep struggle"],
        "demo":      ["vegetable chopper in use", "manual food chopper kitchen", "kitchen tool demonstration"],
        "resultado": ["chopped vegetables bowl", "diced vegetables result", "clean kitchen prep"],
        "close":     ["kitchen utensil closeup", "vegetable chopper detail"],
        "cta":       ["hand using kitchen tool", "kitchen gadget on counter"],
    },
}

# Default genérico se nicho não estiver mapeado.
# IMPORTANTE: nada de "happy customer"/"smiling person" soltos — queries vagas
# de emoção trazem QUALQUER coisa do banco (cachorro, família, quadra de tênis).
# Igualmente, "cutter"/"slicer"/"product" soltos trazem pera, planta, jardim.
# CTA usa o próprio produto em destaque, que é sempre relevante.
QUERIES_FALLBACK = {
    "dor":       ["product problem closeup"],
    "demo":      ["product in use hand"],
    "resultado": ["product result closeup"],
    "close":     ["product closeup detail"],
    "cta":       ["hand holding product"],
}


# =================================================================
# DESCOBERTA DE ESTADO
# =================================================================

def carregar_plano_mais_recente(produto: str) -> Optional[dict]:
    """
    Lê o plano mais recente em shared/content_plans/.
    Tenta padrão histórico plano_<slug>_<TS>.json, fallback pra
    plano_<slug>.json ou <slug>.json.
    """
    if not PLANS_DIR.exists():
        return None

    slug = slugificar_produto(produto)
    re_ts = re.compile(r"_(\d{8})_(\d{6})$")

    candidatos = []
    for f in PLANS_DIR.glob("plano_*.json"):
        if "_resultado" in f.stem or f.name == "ultimo_plano.json":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        nome_plano = data.get("produto") or data.get("nome") or ""
        if slugificar_produto(nome_plano) != slug:
            continue
        # Timestamp do nome (preferido) ou mtime
        m = re_ts.search(f.stem.replace("plano_", "", 1))
        if m:
            try:
                ts_str = m.group(1) + m.group(2)
                from datetime import datetime
                ts_dt = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
            except Exception:
                ts_dt = None
        else:
            ts_dt = None
        if ts_dt is None:
            try:
                from datetime import datetime as _dt
                ts_dt = _dt.fromtimestamp(f.stat().st_mtime)
            except Exception:
                continue
        candidatos.append((ts_dt, f, data))

    # Fallbacks
    for nome in (f"plano_{slug}.json", f"{slug}.json"):
        f = PLANS_DIR / nome
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                from datetime import datetime as _dt
                candidatos.append((_dt.fromtimestamp(f.stat().st_mtime), f, data))
            except Exception:
                pass

    if not candidatos:
        return None
    candidatos.sort(key=lambda x: x[0], reverse=True)
    _, path, data = candidatos[0]
    data["_plano_path"] = str(path)
    return data


def detectar_cenas_faltantes(produto: str) -> tuple[list[str], dict]:
    """
    Retorna (lista_cenas_faltantes, status_completo).
    Cenas faltantes = propósitos no plano - propósitos já cobertos.
    """
    status = verificar_assets_produto(produto)
    cobertura = status.get("cobertura_propositos") or {}
    propositos_essenciais = ["dor", "demo", "resultado", "close", "cta"]
    faltantes = []
    for p in propositos_essenciais:
        if cobertura.get(p, 0) == 0:
            faltantes.append(p)
    return faltantes, status


# =================================================================
# UTILS — sanitização, validação
# =================================================================

def _garantir_inbox():
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_VIDEOS.mkdir(parents=True, exist_ok=True)
    INBOX_IMGS.mkdir(parents=True, exist_ok=True)


def _sanitizar_nome(texto: str, max_chars: int = 40) -> str:
    s = re.sub(r"[^\w\-.]", "_", str(texto or ""))
    s = re.sub(r"_+", "_", s).strip("_")[:max_chars]
    return s or "asset"


def _destino_sem_conflito(pasta: Path, nome: str) -> Path:
    cand = pasta / nome
    if not cand.exists():
        return cand
    stem, suf = Path(nome).stem, Path(nome).suffix
    for i in range(2, 100):
        cand = pasta / f"{stem}_{i}{suf}"
        if not cand.exists():
            return cand
    return pasta / f"{stem}_{int(time.time())}{suf}"


def _eh_site_bloqueado(url: str) -> bool:
    if not url:
        return True
    netloc = urlparse(url).netloc.lower()
    return any(b in netloc for b in SITES_BLOQUEADOS)


def _eh_site_ecommerce_ok(url: str) -> bool:
    if not url:
        return False
    netloc = urlparse(url).netloc.lower()
    return any(s in netloc for s in SITES_ECOMMERCE_OK)


def _detectar_extensao(url: str, content_type: str = "") -> Optional[str]:
    # Tenta da URL primeiro
    parsed = urlparse(url)
    path_ext = Path(parsed.path).suffix.lower()
    if path_ext in EXT_ACEITAS:
        return path_ext
    # Tenta do Content-Type
    ct = (content_type or "").lower()
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if "mp4" in ct:
        return ".mp4"
    if "quicktime" in ct or "/mov" in ct:
        return ".mov"
    if "webm" in ct:
        return ".webm"
    return None


# =================================================================
# DOWNLOAD GENÉRICO
# =================================================================

def baixar_url_direta(url: str, nome_base: str,
                       fonte: str = "url") -> dict:
    """
    Baixa um arquivo da URL pra assets/inbox/.

    Args:
        url:       URL completa do arquivo
        nome_base: nome lógico (será sanitizado + prefixado com fonte)
        fonte:     prefixo do arquivo (pexels/pixabay/ogimage/url_direct)

    Returns: {sucesso, destino, tamanho_bytes, mensagem, erro}
    """
    _garantir_inbox()
    resp = {"url": url, "fonte": fonte, "destino": None,
            "tamanho_bytes": 0, "mensagem": "", "erro": None}

    # Bloqueio de sites proibidos
    if _eh_site_bloqueado(url):
        return {**resp, "sucesso": False,
                "erro": f"site bloqueado por política: {urlparse(url).netloc}"}

    try:
        import requests
    except ImportError:
        return {**resp, "sucesso": False, "erro": "requests não instalado"}

    try:
        with requests.get(url, stream=True, timeout=TIMEOUT_REQUEST_SEG,
                           headers={"User-Agent": USER_AGENT,
                                    "Accept": "image/*, video/*, */*"}) as r:
            if r.status_code != 200:
                return {**resp, "sucesso": False,
                        "erro": f"HTTP {r.status_code}"}

            content_type = r.headers.get("Content-Type", "")
            ext = _detectar_extensao(url, content_type)
            if ext is None:
                return {**resp, "sucesso": False,
                        "erro": f"extensão não detectada (CT={content_type[:40]})"}

            # Tamanho declarado
            content_length = r.headers.get("Content-Length")
            if content_length:
                try:
                    mb = int(content_length) / 1024 / 1024
                    if mb > TAMANHO_MAX_MB:
                        return {**resp, "sucesso": False,
                                "erro": f"arquivo grande demais: {mb:.1f}MB"}
                except ValueError:
                    pass

            nome_san = _sanitizar_nome(nome_base, max_chars=40)
            nome_final = f"{fonte}_{nome_san}{ext}"
            # Rota por extensão: vídeo → inbox/videos/, imagem → inbox/imagens/
            pasta_destino = _subpasta_destino(ext)
            destino = _destino_sem_conflito(pasta_destino, nome_final)

            baixado = 0
            with open(destino, "wb") as f:
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                    if not chunk:
                        continue
                    f.write(chunk)
                    baixado += len(chunk)
                    if baixado > TAMANHO_MAX_MB * 1024 * 1024:
                        f.close()
                        destino.unlink(missing_ok=True)
                        return {**resp, "sucesso": False,
                                "erro": f"excedeu {TAMANHO_MAX_MB}MB"}

            # Valida tamanho mínimo (filtra thumbnails)
            min_kb = TAMANHO_MIN_VIDEO_KB if ext in EXT_VIDEO else TAMANHO_MIN_IMG_KB
            if baixado < min_kb * 1024:
                destino.unlink(missing_ok=True)
                return {**resp, "sucesso": False,
                        "erro": f"muito pequeno ({baixado // 1024}KB < {min_kb}KB)"}

            resp["destino"]       = str(destino)
            resp["tamanho_bytes"] = baixado
            resp["mensagem"]      = f"baixado {baixado // 1024} KB"
            return {**resp, "sucesso": True}

    except Exception as e:
        return {**resp, "sucesso": False,
                "erro": f"{type(e).__name__}: {str(e)[:140]}"}


# =================================================================
# FONTE C: EXTRAÇÃO DE og:image DE PÁGINA DE PRODUTO
# =================================================================

def extrair_assets_de_pagina_produto(url: str) -> dict:
    """
    Lê HTML da página de produto e extrai URLs de og:image, twitter:image
    e <link rel='image_src'>. NÃO faz scraping profundo do DOM.

    Returns: {sucesso, urls_extraidas, mensagem}
    """
    if _eh_site_bloqueado(url):
        return {"sucesso": False, "urls_extraidas": [],
                "mensagem": f"site bloqueado: {urlparse(url).netloc}"}

    if not _eh_site_ecommerce_ok(url):
        return {"sucesso": False, "urls_extraidas": [],
                "mensagem": (f"domínio '{urlparse(url).netloc}' fora da lista de "
                              f"e-commerce permitida")}

    try:
        import requests
    except ImportError:
        return {"sucesso": False, "urls_extraidas": [],
                "mensagem": "requests não instalado"}

    try:
        r = requests.get(url, timeout=TIMEOUT_REQUEST_SEG,
                          headers={"User-Agent": USER_AGENT,
                                   "Accept": "text/html,*/*"})
        if r.status_code != 200:
            return {"sucesso": False, "urls_extraidas": [],
                    "mensagem": f"HTTP {r.status_code}"}
        html = r.text
    except Exception as e:
        return {"sucesso": False, "urls_extraidas": [],
                "mensagem": f"{type(e).__name__}: {str(e)[:140]}"}

    # Extração leve via regex (evita BeautifulSoup pra reduzir deps)
    padroes = [
        r'<meta\s+property="og:image"\s+content="([^"]+)"',
        r"<meta\s+property='og:image'\s+content='([^']+)'",
        r'<meta\s+name="twitter:image"\s+content="([^"]+)"',
        r'<link\s+rel="image_src"\s+href="([^"]+)"',
    ]
    urls = []
    for pat in padroes:
        urls.extend(re.findall(pat, html, flags=re.IGNORECASE))

    # Dedup preservando ordem
    seen = set()
    urls_final = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            urls_final.append(u)

    return {
        "sucesso":         len(urls_final) > 0,
        "urls_extraidas":  urls_final,
        "mensagem":        f"{len(urls_final)} URL(s) extraída(s)" if urls_final else "Nenhum og:image encontrado",
    }


# =================================================================
# FONTE D: PEXELS API
# =================================================================

def _pexels_token() -> Optional[str]:
    return os.environ.get("PEXELS_API_KEY", "").strip() or None


def buscar_pexels(query: str, tipo: str = "photo",
                   limite: int = 5) -> list[dict]:
    """
    Busca no Pexels. tipo: "photo" ou "video".
    Retorna lista de candidatos: [{url, id, owner, tipo}]
    """
    token = _pexels_token()
    if not token:
        return []
    try:
        import requests
    except ImportError:
        return []

    if tipo == "video":
        endpoint = "https://api.pexels.com/videos/search"
    else:
        endpoint = "https://api.pexels.com/v1/search"

    params = {"query": query, "per_page": min(limite, 80),
              "orientation": "portrait"}  # vídeo vertical = melhor pra TikTok

    try:
        r = requests.get(endpoint, params=params, timeout=TIMEOUT_REQUEST_SEG,
                          headers={"Authorization": token, "User-Agent": USER_AGENT})
        if r.status_code != 200:
            log.warning(f"   Pexels HTTP {r.status_code}: {r.text[:80]}")
            return []
        data = r.json()
    except Exception as e:
        log.warning(f"   Pexels falhou: {e}")
        return []

    saida = []
    if tipo == "video":
        for v in data.get("videos", [])[:limite]:
            files = v.get("video_files") or []
            # Pega o de qualidade média (não muito grande)
            files_filtrados = [f for f in files
                                if f.get("quality") in ("hd", "sd")
                                and f.get("link")]
            if not files_filtrados:
                continue
            # Prefere HD vertical, fallback SD
            files_filtrados.sort(key=lambda f: (
                0 if f.get("quality") == "hd" else 1,
                abs((f.get("width") or 1080) - 1080),
            ))
            escolhido = files_filtrados[0]
            saida.append({
                "url":   escolhido["link"],
                "id":    v.get("id"),
                "owner": (v.get("user") or {}).get("name", "?"),
                "tipo":  "video",
                "fonte": "pexels",
                "query": query,
            })
    else:
        for p in data.get("photos", [])[:limite]:
            src = p.get("src") or {}
            url_img = src.get("large") or src.get("medium") or src.get("original")
            if not url_img:
                continue
            saida.append({
                "url":   url_img,
                "id":    p.get("id"),
                "owner": p.get("photographer", "?"),
                "tipo":  "photo",
                "fonte": "pexels",
                "query": query,
            })
    return saida


# =================================================================
# FONTE E: PIXABAY API
# =================================================================

def _pixabay_token() -> Optional[str]:
    return os.environ.get("PIXABAY_API_KEY", "").strip() or None


def buscar_pixabay(query: str, tipo: str = "photo",
                    limite: int = 5) -> list[dict]:
    """
    Busca no Pixabay. tipo: "photo" ou "video".
    Todos os assets são CC0 (sem atribuição obrigatória).
    """
    token = _pixabay_token()
    if not token:
        return []
    try:
        import requests
    except ImportError:
        return []

    if tipo == "video":
        endpoint = "https://pixabay.com/api/videos/"
        params = {"key": token, "q": query, "per_page": max(3, min(limite, 30))}
    else:
        endpoint = "https://pixabay.com/api/"
        params = {"key": token, "q": query, "per_page": max(3, min(limite, 30)),
                   "image_type": "photo", "orientation": "vertical"}

    try:
        r = requests.get(endpoint, params=params, timeout=TIMEOUT_REQUEST_SEG,
                          headers={"User-Agent": USER_AGENT})
        if r.status_code != 200:
            log.warning(f"   Pixabay HTTP {r.status_code}: {r.text[:80]}")
            return []
        data = r.json()
    except Exception as e:
        log.warning(f"   Pixabay falhou: {e}")
        return []

    saida = []
    for hit in data.get("hits", [])[:limite]:
        if tipo == "video":
            videos = hit.get("videos") or {}
            # Pega qualidade média (medium ou small)
            for q in ("medium", "small", "tiny", "large"):
                v = videos.get(q) or {}
                url_v = v.get("url")
                if url_v:
                    saida.append({
                        "url":   url_v,
                        "id":    hit.get("id"),
                        "owner": hit.get("user", "?"),
                        "tipo":  "video",
                        "fonte": "pixabay",
                        "query": query,
                    })
                    break
        else:
            url_img = hit.get("largeImageURL") or hit.get("webformatURL")
            if url_img:
                saida.append({
                    "url":   url_img,
                    "id":    hit.get("id"),
                    "owner": hit.get("user", "?"),
                    "tipo":  "photo",
                    "fonte": "pixabay",
                    "query": query,
                })
    return saida


# =================================================================
# SUGESTÃO DE QUERIES POR PRODUTO + CENA
# =================================================================

def sugerir_queries_por_produto(produto: str, nicho: str,
                                  cenas_faltantes: list[str],
                                  query_custom: str = "") -> dict:
    """
    Retorna dict {cena: [queries]} pra cada cena faltante.
    Combina:
      - Tradução do nome do produto (dicionário curado)
      - Queries genéricas por nicho+cena
      - Query custom do usuário (se passada, ganha prioridade)
    """
    # Traduções do nome
    produto_lower = produto.lower()
    traducoes = []
    for chave, valores in TRADUCAO_PRODUTO.items():
        if chave in produto_lower:
            traducoes.extend(valores)
    if not traducoes:
        # Fallback: tira "de", "do", "para" e usa o resto
        words = [w for w in produto.split()
                  if w.lower() not in ("de", "do", "da", "para", "com", "em")]
        traducoes.append(" ".join(words))

    # Queries por nicho
    queries_nicho = QUERIES_POR_NICHO_E_CENA.get(nicho, QUERIES_FALLBACK)

    saida = {}
    for cena in cenas_faltantes:
        cena_queries = []
        # Custom tem prioridade
        if query_custom:
            cena_queries.append(query_custom)
        # Primeira combinação: traducao_produto + cena_keyword
        for trad in traducoes[:2]:
            cena_queries.append(f"{trad}")  # produto puro funciona bem em bancos
        # Queries genéricas do nicho/cena
        cena_queries.extend(queries_nicho.get(cena, QUERIES_FALLBACK.get(cena, [])))
        # Dedup
        seen = set()
        dedup = []
        for q in cena_queries:
            if q and q.lower() not in seen:
                seen.add(q.lower())
                dedup.append(q)
        saida[cena] = dedup[:5]  # max 5 queries por cena
    return saida


# =================================================================
# COLETA POR FONTE
# =================================================================

def _chave_fonte(cand: dict) -> str:
    """
    Chave única de um vídeo-fonte: 'fonte:id' (ex: 'pexels:7802047').
    Usada pro dedup global — garante que o mesmo vídeo do banco não seja
    baixado duas vezes, mesmo aparecendo em queries/cenas diferentes.
    """
    return f"{cand.get('fonte', '?')}:{cand.get('id', '?')}"


def _candidatos_do_catalogo(query: str, nicho: str, tipo: str,
                             limite: int) -> list[dict]:
    """
    Busca candidatos no Catálogo Semântico (1ª fonte). Busca por QUERY + NICHO
    pra dar contexto semântico máximo ("vegetable chopper in use Cozinha").

    Retorna candidatos no MESMO formato do buscar_pexels/pixabay
    ({url, id, owner, tipo, fonte, query}), pra encaixar no fluxo de download
    sem mudar mais nada. Só inclui os que passam do CATALOGO_SCORE_MIN.

    Se o catálogo não estiver disponível ou não tiver nada relevante, retorna [].
    """
    if not (_CATALOGO_OK and USAR_CATALOGO):
        return []
    # Enriquecе a busca com o nicho (contexto semântico)
    conceito = f"{query} {nicho}".strip()
    try:
        achados = _catalogo_buscar(conceito, n=limite, tipo=tipo,
                                   score_minimo=CATALOGO_SCORE_MIN)
    except Exception as e:
        log.warning(f"      ⚠️  Catálogo falhou ({str(e)[:60]}) — caindo pra API")
        return []
    # Converte pro formato de candidato do autopilot
    candidatos = []
    for a in achados:
        # o id no catálogo é "fonte:idfonte" — extrai o id da fonte de volta
        id_fonte = a.get("id", "")
        if ":" in id_fonte:
            id_fonte = id_fonte.split(":", 1)[1]
        candidatos.append({
            "url":   a.get("url", ""),
            "id":    id_fonte,
            "owner": "?",  # catálogo não guarda owner detalhado
            "tipo":  a.get("tipo", tipo),
            "fonte": a.get("fonte", "catalogo"),
            "query": query,
            "_score_catalogo": a.get("score", 0),
        })
    return candidatos


def buscar_candidatos_cena(query: str, cena: str, nicho: str,
                            pexels_ok: bool, pixabay_ok: bool) -> list[dict]:
    """
    Busca candidatos pra uma cena, com CASCATA DE FONTES:
      1º  Catálogo Semântico (query + nicho, score_min) — 0 request à API
      2º  API clássica (Pexels + Pixabay) — só se o catálogo não trouxe nada

    O autopilot NÃO indexa no catálogo aqui (ele só cresce via semantic_indexer).
    Retorna lista de candidatos no formato padrão {url, id, owner, tipo, fonte, query}.
    """
    # 1ª FONTE: catálogo semântico
    candidatos = _candidatos_do_catalogo(query, nicho, "video", 5)
    candidatos += _candidatos_do_catalogo(query, nicho, "photo", 3)
    if candidatos:
        scores = [c.get("_score_catalogo", 0) for c in candidatos]
        log.info(f"      🧠 Catálogo: {len(candidatos)} candidato(s) "
                 f"(score {min(scores):.2f}–{max(scores):.2f}) — sem tocar na API")
        return candidatos

    # 2ª FONTE: API clássica (fallback, como antes)
    log.info(f"      📡 Catálogo sem match (>{CATALOGO_SCORE_MIN}) — buscando na API")
    candidatos = []
    if pexels_ok:
        candidatos.extend(buscar_pexels(query, "video", 5))
        candidatos.extend(buscar_pexels(query, "photo", 3))
        time.sleep(RATE_LIMIT_ENTRE_REQS_SEG)
    if pixabay_ok:
        candidatos.extend(buscar_pixabay(query, "video", 5))
        candidatos.extend(buscar_pixabay(query, "photo", 3))
        time.sleep(RATE_LIMIT_ENTRE_REQS_SEG)
    return candidatos


def coletar_de_fontes_api(queries_por_cena: dict, max_downloads: int,
                            ativar_pexels: bool = True,
                            ativar_pixabay: bool = True,
                            nicho: str = "") -> list[dict]:
    """
    Coleta com ROUND-ROBIN entre cenas (não esgota uma cena antes da próxima).

    Rodada 1: 1 download de dor, 1 de demo, 1 de resultado, 1 de close, 1 de cta
    Rodada 2: mais 1 de cada, até atingir max_downloads total

    Garante diversidade mesmo com max_downloads pequeno.
    """
    pexels_ok = ativar_pexels and _pexels_token() is not None
    pixabay_ok = ativar_pixabay and _pixabay_token() is not None

    log.info(f"🌐 APIs: Pexels {'✅' if pexels_ok else '❌ (sem PEXELS_API_KEY)'}, "
             f"Pixabay {'✅' if pixabay_ok else '❌ (sem PIXABAY_API_KEY)'}")
    if not pexels_ok and not pixabay_ok:
        return []

    # Estado por cena: índice da próxima query a tentar + downloads já feitos
    estado_cenas = {cena: {"query_idx": 0, "downloads_feitos": 0,
                            "candidatos_pendentes": []}
                      for cena in queries_por_cena}

    # Dedup GLOBAL por fonte+id: um mesmo vídeo-fonte (ex: pexels:7802047) só
    # é baixado UMA vez no projeto inteiro, mesmo que apareça em várias
    # queries/cenas. Sem isso, o top result de um termo de nicho (ex:
    # "waist trainer") era baixado repetido e o vídeo virava "uma cena só
    # em loop". Inclui o que o produto JÁ tem em raw/.
    fontes_baixadas = set()

    resultados = []
    baixados_total = 0

    # CAP POR CENA: evita que uma cena vire depósito de sobras. Sem isto, quando
    # as cenas "difíceis" (dor/demo) esgotam candidatos cedo, todas as rodadas
    # extras caíam numa cena só (no teu caso: cta levou 6 de 10 downloads, e as
    # queries vagas de cta trouxeram cachorro/quadra de tênis). Com o cap, cada
    # cena leva no máximo ~teto e o excedente simplesmente não é baixado.
    n_cenas = max(1, len(queries_por_cena))
    cap_por_cena = max(2, -(-max_downloads // n_cenas) + 1)  # ceil + 1 de folga
    log.info(f"   🎚️  Cap por cena: {cap_por_cena} download(s) "
             f"(evita concentração numa cena só)")

    # Rodada por rodada (round-robin)
    max_rodadas = max_downloads * 2  # safety: nunca mais que 2x max_downloads
    rodada = 0
    while baixados_total < max_downloads and rodada < max_rodadas:
        rodada += 1
        baixou_nessa_rodada = False
        log.info(f"\n🔄 Rodada {rodada} ({baixados_total}/{max_downloads} baixados)")

        for cena in queries_por_cena.keys():
            if baixados_total >= max_downloads:
                break
            # Cena já atingiu o teto? pula — não vira depósito de sobras.
            if estado_cenas[cena]["downloads_feitos"] >= cap_por_cena:
                continue
            est = estado_cenas[cena]

            # 1) Tenta candidato pendente da query anterior dessa cena
            if not est["candidatos_pendentes"]:
                # Avança pra próxima query e busca candidatos
                queries = queries_por_cena[cena]
                while est["query_idx"] < len(queries) and not est["candidatos_pendentes"]:
                    query_atual = queries[est["query_idx"]]
                    est["query_idx"] += 1
                    log.info(f"   🎬 [{cena}] query: '{query_atual}'")

                    # CASCATA: catálogo semântico primeiro, API como fallback.
                    # (buscar_candidatos_cena resolve a ordem internamente)
                    candidatos = buscar_candidatos_cena(
                        query_atual, cena, nicho, pexels_ok, pixabay_ok)

                    # Remove candidatos cujo vídeo-fonte JÁ foi baixado
                    # (dedup global por fonte+id) — é o que evita o loop.
                    candidatos = [
                        c for c in candidatos
                        if _chave_fonte(c) not in fontes_baixadas
                    ]

                    if candidatos:
                        # Marca a query no candidato pra log
                        for c in candidatos:
                            c["_query_origem"] = query_atual
                        est["candidatos_pendentes"] = candidatos
                        log.info(f"      {len(candidatos)} candidato(s) novo(s) encontrado(s)")
                    else:
                        log.info(f"      (sem candidatos novos)")

            # 2) Tenta baixar UM candidato pendente (que ainda não foi baixado)
            if est["candidatos_pendentes"]:
                cand = est["candidatos_pendentes"].pop(0)
                # Defesa dupla: pode ter sido baixado por outra cena nessa rodada
                if _chave_fonte(cand) in fontes_baixadas:
                    continue
                query_origem = cand.get("_query_origem", "?")
                nome_base = f"{cena}_{_sanitizar_nome(query_origem, 20)}_{cand['id']}"
                r = baixar_url_direta(cand["url"],
                                       nome_base=nome_base,
                                       fonte=cand["fonte"])
                r["cena_alvo"]  = cena
                r["tipo_asset"] = cand["tipo"]
                r["owner"]      = cand.get("owner", "?")
                r["query"]      = query_origem
                resultados.append(r)
                if r["sucesso"]:
                    # Marca o vídeo-fonte como baixado (dedup global)
                    fontes_baixadas.add(_chave_fonte(cand))
                    log.info(f"      ✅ [{cena}] {Path(r['destino']).name} "
                             f"({r['tamanho_bytes']//1024}KB, by @{r['owner']})")
                    baixados_total += 1
                    est["downloads_feitos"] += 1
                    baixou_nessa_rodada = True
                else:
                    log.warning(f"      ❌ [{cena}] {r.get('erro', '?')[:80]}")
                time.sleep(RATE_LIMIT_ENTRE_REQS_SEG / 2)

        # Safety: se rodou todas as cenas e ninguém baixou, sai
        if not baixou_nessa_rodada:
            # Check: alguma cena AINDA NÃO no cap e com queries/candidatos?
            tem_o_que_tentar = any(
                est["downloads_feitos"] < cap_por_cena
                and (est["candidatos_pendentes"]
                     or est["query_idx"] < len(queries_por_cena[cena]))
                for cena, est in estado_cenas.items()
            )
            if not tem_o_que_tentar:
                log.info(f"   🛑 Cenas esgotaram queries ou atingiram o cap — saindo")
                break

    log.info(f"\n📊 Total baixado: {baixados_total}/{max_downloads}")
    log.info(f"   Distribuição por cena:")
    for cena, est in estado_cenas.items():
        log.info(f"      {cena}: {est['downloads_feitos']} download(s)")
    return resultados


# =================================================================
# EXECUTAR ASSET HUNTER
# =================================================================

def curar_inbox_raiz() -> dict:
    """
    Move arquivos órfãos de assets/inbox/ (raiz) pras subpastas videos/imagens
    baseado na extensão. Útil pra recuperar arquivos baixados por versões
    antigas do Autopilot que não roteavam corretamente.

    Returns: {movidos, ignorados, erros}
    """
    _garantir_inbox()
    movidos, ignorados, erros = [], [], []

    if not INBOX_DIR.exists():
        return {"movidos": [], "ignorados": [], "erros": []}

    for arq in INBOX_DIR.iterdir():
        if arq.is_dir() or arq.name.startswith("."):
            continue
        ext = arq.suffix.lower()
        if ext not in EXT_ACEITAS:
            ignorados.append({"arquivo": arq.name, "motivo": f"ext '{ext}' não suportada"})
            continue
        destino_dir = _subpasta_destino(ext)
        if destino_dir == arq.parent:  # já tá no lugar certo (não deveria)
            continue
        try:
            destino = _destino_sem_conflito(destino_dir, arq.name)
            arq.rename(destino)
            movidos.append({"de": str(arq.name), "para": str(destino)})
        except Exception as e:
            erros.append({"arquivo": arq.name, "erro": str(e)[:140]})

    return {"movidos": movidos, "ignorados": ignorados, "erros": erros}


def executar_asset_hunter(produto: str) -> dict:
    """
    Roda asset_hunter_agent --produto X --mover via subprocess.

    Fix Windows: passa PYTHONIOENCODING=utf-8 + PYTHONUTF8=1 no env pra
    evitar UnicodeEncodeError quando Hunter imprime emojis em terminal
    cp1252 (default no Windows).

    Retorna dict {sucesso, stdout_resumo, returncode}.
    """
    try:
        # Env com UTF-8 forçado (resolve cp1252 do Windows com emojis no Hunter)
        env_utf8 = {**os.environ,
                     "PYTHONIOENCODING": "utf-8",
                     "PYTHONUTF8": "1"}
        cmd = [sys.executable, "-m", "agents.asset_hunter_agent",
                "--produto", produto, "--mover"]
        log.info(f"🎯 Disparando Asset Hunter pra '{produto}'...")
        proc = subprocess.run(cmd, cwd=str(PROJETO_ROOT),
                                capture_output=True, text=True,
                                encoding="utf-8", errors="replace",
                                env=env_utf8, timeout=120)
        # Procura linhas resumo no stdout
        linhas_resumo = []
        for linha in proc.stdout.splitlines():
            if any(k in linha for k in ("Movidas:", "Erros:", "Score", "📊", "✅",
                                          "Status do produto", "Δ:")):
                linhas_resumo.append(linha.strip())
        return {
            "sucesso":     proc.returncode == 0,
            "returncode":  proc.returncode,
            "resumo":      linhas_resumo[-15:],
            "stderr":      proc.stderr[-500:] if proc.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"sucesso": False, "resumo": [], "stderr": "timeout (>120s)"}
    except Exception as e:
        return {"sucesso": False, "resumo": [],
                "stderr": f"{type(e).__name__}: {str(e)[:140]}"}



    """
    Roda asset_hunter_agent --produto X --mover via subprocess.

    Fix Windows: passa PYTHONIOENCODING=utf-8 + PYTHONUTF8=1 no env pra
    evitar UnicodeEncodeError quando Hunter imprime emojis em terminal
    cp1252 (default no Windows).

    Retorna dict {sucesso, stdout_resumo, returncode}.
    """
    try:
        # Env com UTF-8 forçado (resolve cp1252 do Windows com emojis no Hunter)
        env_utf8 = {**os.environ,
                     "PYTHONIOENCODING": "utf-8",
                     "PYTHONUTF8": "1"}
        cmd = [sys.executable, "-m", "agents.asset_hunter_agent",
                "--produto", produto, "--mover"]
        log.info(f"🎯 Disparando Asset Hunter pra '{produto}'...")
        proc = subprocess.run(cmd, cwd=str(PROJETO_ROOT),
                                capture_output=True, text=True,
                                encoding="utf-8", errors="replace",
                                env=env_utf8, timeout=120)
        # Procura linhas resumo no stdout
        linhas_resumo = []
        for linha in proc.stdout.splitlines():
            if any(k in linha for k in ("Movidas:", "Erros:", "Score", "📊", "✅",
                                          "Status do produto", "Δ:")):
                linhas_resumo.append(linha.strip())
        return {
            "sucesso":     proc.returncode == 0,
            "returncode":  proc.returncode,
            "resumo":      linhas_resumo[-15:],
            "stderr":      proc.stderr[-500:] if proc.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"sucesso": False, "resumo": [], "stderr": "timeout (>120s)"}
    except Exception as e:
        return {"sucesso": False, "resumo": [],
                "stderr": f"{type(e).__name__}: {str(e)[:140]}"}


# =================================================================
# PIPELINE PRINCIPAL
# =================================================================

def autopilot_assets(produto: str,
                       max_downloads: int = MAX_DOWNLOADS_DEFAULT,
                       ate_pronto: bool = False,
                       max_ciclos: int = MAX_CICLOS_ATE_PRONTO,
                       url_direta: Optional[str] = None,
                       pagina_produto: Optional[str] = None,
                       query_custom: str = "",
                       dry_run: bool = False,
                       ativar_pexels: bool = True,
                       ativar_pixabay: bool = True,
                       executar_hunter: bool = True) -> dict:
    """
    Pipeline principal: detecta faltantes → coleta → hunter → reavalia.
    Repete até score >= SCORE_OBJETIVO se ate_pronto=True.
    """
    log.info("=" * 60)
    log.info(f"🚁 ASSET AUTOPILOT — '{produto}'")
    log.info(f"   Modo: {'DRY-RUN' if dry_run else 'REAL'} | "
             f"max-downloads: {max_downloads} | "
             f"ate-pronto: {ate_pronto}")
    log.info("=" * 60)

    slug = slugificar_produto(produto)
    plano = carregar_plano_mais_recente(produto)
    if plano:
        nicho = plano.get("nicho", "")
        log.info(f"   📋 Plano: {Path(plano.get('_plano_path', '?')).name}, nicho='{nicho or '?'}'")
    else:
        nicho = ""
        log.warning(f"   ⚠️  Nenhum plano encontrado pra '{produto}' — usando defaults")

    # Status inicial
    cenas_faltantes_inicial, status_inicial = detectar_cenas_faltantes(produto)
    score_inicial = status_inicial.get("score_prontidao", 0)
    log.info(f"   📊 Status inicial: {status_inicial['status']} (score {score_inicial}/100)")
    log.info(f"   🎬 Cenas faltantes: {cenas_faltantes_inicial or 'nenhuma!'}")

    resultado_geral = {
        "produto":            produto,
        "slug":                slug,
        "nicho":               nicho,
        "status_inicial":      status_inicial["status"],
        "score_inicial":       score_inicial,
        "cenas_faltantes":     cenas_faltantes_inicial,
        "downloads_tentados":  [],
        "downloads_ok":        [],
        "downloads_falha":     [],
        "paginas_extraidas":   [],
        "ciclos_executados":   0,
        "hunter_resumos":      [],
    }

    if not cenas_faltantes_inicial:
        log.info(f"\n✅ '{produto}' já tem TODAS as cenas — nada a fazer")
        resultado_geral["status_final"] = status_inicial["status"]
        resultado_geral["score_final"] = score_inicial
        resultado_geral["pronto_para_edicao"] = score_inicial >= SCORE_OBJETIVO
        resultado_geral["mensagem"] = "Nenhuma cena faltante"
        return resultado_geral

    queries = sugerir_queries_por_produto(produto, nicho,
                                            cenas_faltantes_inicial,
                                            query_custom=query_custom)
    log.info(f"\n🔍 Queries planejadas:")
    for cena, qs in queries.items():
        log.info(f"   {cena}: {qs[:3]}{'...' if len(qs) > 3 else ''}")

    # ── URL direta + página de produto: sempre tentamos primeiro (curado pelo usuário) ──
    if url_direta:
        log.info(f"\n🔗 URL direta passada: {url_direta[:80]}")
        if not dry_run:
            r = baixar_url_direta(url_direta,
                                    nome_base=f"manual_{slug}",
                                    fonte="url_direct")
            resultado_geral["downloads_tentados"].append(r)
            if r["sucesso"]:
                resultado_geral["downloads_ok"].append(r)
                log.info(f"   ✅ {Path(r['destino']).name}")
            else:
                resultado_geral["downloads_falha"].append(r)
                log.warning(f"   ❌ {r.get('erro')}")

    if pagina_produto:
        log.info(f"\n🔗 Página de produto: {pagina_produto[:80]}")
        ext = extrair_assets_de_pagina_produto(pagina_produto)
        resultado_geral["paginas_extraidas"].append({
            "url":     pagina_produto,
            "extraido": ext,
        })
        log.info(f"   {ext.get('mensagem', '?')}")
        if not dry_run:
            for i, img_url in enumerate(ext.get("urls_extraidas", [])[:3]):
                r = baixar_url_direta(img_url,
                                        nome_base=f"{slug}_pagina_{i}",
                                        fonte="ogimage")
                resultado_geral["downloads_tentados"].append(r)
                if r["sucesso"]:
                    resultado_geral["downloads_ok"].append(r)
                else:
                    resultado_geral["downloads_falha"].append(r)
                time.sleep(RATE_LIMIT_ENTRE_REQS_SEG)

    # ── DRY-RUN para por aqui ──
    if dry_run:
        log.info(f"\n🔍 [DRY-RUN] Não baixando nada. Tentaria:")
        log.info(f"   - Pexels: {'✅' if (ativar_pexels and _pexels_token()) else '❌'}")
        log.info(f"   - Pixabay: {'✅' if (ativar_pixabay and _pixabay_token()) else '❌'}")
        log.info(f"   - URL direta: {'sim' if url_direta else 'não'}")
        log.info(f"   - Página produto: {'sim' if pagina_produto else 'não'}")
        total_queries = sum(len(qs) for qs in queries.values())
        log.info(f"   - Total queries planejadas: {total_queries}")
        resultado_geral["status_final"] = status_inicial["status"]
        resultado_geral["score_final"] = score_inicial
        resultado_geral["pronto_para_edicao"] = False
        resultado_geral["mensagem"] = "Dry-run — nada baixado"
        return resultado_geral

    # ── Ciclos de coleta + Hunter ──
    ciclo = 0
    downloads_sem_progresso = 0
    while ciclo < (max_ciclos if ate_pronto else 1):
        ciclo += 1
        log.info(f"\n{'─' * 60}")
        log.info(f"📦 CICLO {ciclo}/{max_ciclos if ate_pronto else 1}")
        log.info(f"{'─' * 60}")

        # Recalcula cenas faltantes a cada ciclo
        cenas_atuais, status_atual = detectar_cenas_faltantes(produto)
        if not cenas_atuais:
            log.info(f"   🎉 Todas as cenas cobertas — saindo")
            break
        queries_ciclo = sugerir_queries_por_produto(produto, nicho,
                                                     cenas_atuais,
                                                     query_custom=query_custom)

        resultados_ciclo = coletar_de_fontes_api(
            queries_ciclo,
            max_downloads=max_downloads,
            ativar_pexels=ativar_pexels,
            ativar_pixabay=ativar_pixabay,
            nicho=nicho,
        )
        for r in resultados_ciclo:
            resultado_geral["downloads_tentados"].append(r)
            if r["sucesso"]:
                resultado_geral["downloads_ok"].append(r)
            else:
                resultado_geral["downloads_falha"].append(r)

        baixados_ciclo = sum(1 for r in resultados_ciclo if r["sucesso"])
        if baixados_ciclo == 0:
            downloads_sem_progresso += 1
            log.info(f"   ⚠️  Ciclo sem progresso (downloads_sem_progresso={downloads_sem_progresso})")
            if downloads_sem_progresso >= 2:
                log.info(f"   🛑 Sem progresso há 2 ciclos — saindo")
                break

        # Roda hunter se baixou algo
        if baixados_ciclo > 0 and executar_hunter:
            hunter_r = executar_asset_hunter(produto)
            resultado_geral["hunter_resumos"].append(hunter_r)
            for l in hunter_r.get("resumo", [])[-5:]:
                log.info(f"   📦 {l}")

        # Recalcula status
        _, status_pos = detectar_cenas_faltantes(produto)
        score_atual = status_pos.get("score_prontidao", 0)
        log.info(f"   📊 Score após ciclo: {score_atual}/100 (objetivo: {SCORE_OBJETIVO})")

        if ate_pronto and score_atual >= SCORE_OBJETIVO:
            log.info(f"   🎯 Score objetivo atingido — saindo")
            break

    # ── Status final ──
    cenas_finais, status_final = detectar_cenas_faltantes(produto)
    score_final = status_final.get("score_prontidao", 0)
    resultado_geral["ciclos_executados"] = ciclo
    resultado_geral["cenas_faltantes_final"] = cenas_finais
    resultado_geral["status_final"] = status_final["status"]
    resultado_geral["score_final"]  = score_final
    resultado_geral["pronto_para_edicao"] = score_final >= SCORE_OBJETIVO
    resultado_geral["mensagem"] = (
        f"{len(resultado_geral['downloads_ok'])} baixado(s), "
        f"{ciclo} ciclo(s), score {score_inicial}→{score_final}"
    )

    log.info(f"\n{'═' * 60}")
    log.info(f"🏁 RESULTADO FINAL")
    log.info(f"   Score: {score_inicial} → {score_final} "
             f"(Δ {score_final - score_inicial:+d})")
    log.info(f"   Status: {status_inicial['status']} → {status_final['status']}")
    log.info(f"   Downloads: {len(resultado_geral['downloads_ok'])} OK / "
             f"{len(resultado_geral['downloads_falha'])} falhas")
    log.info(f"   Pronto pra edição: {'✅ sim' if resultado_geral['pronto_para_edicao'] else '❌ não'}")
    log.info(f"{'═' * 60}")

    return resultado_geral


# =================================================================
# RELATÓRIO + CLI
# =================================================================

def salvar_resultado(resultado: dict) -> Optional[str]:
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        path = PLANS_DIR / "asset_autopilot_resultado.json"
        path.write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return str(path)
    except Exception as e:
        log.warning(f"Falha ao salvar relatório: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Asset Autopilot — coleta automática de assets pra um produto"
    )
    parser.add_argument("--produto", required=True,
                        help="Nome do produto (ou slug)")
    parser.add_argument("--max-downloads", type=int, default=MAX_DOWNLOADS_DEFAULT,
                        dest="max_downloads",
                        help=f"Máx downloads por execução (default {MAX_DOWNLOADS_DEFAULT})")
    parser.add_argument("--ate-pronto", action="store_true",
                        dest="ate_pronto",
                        help=f"Repete ciclos até score >= {SCORE_OBJETIVO} ou max {MAX_CICLOS_ATE_PRONTO} ciclos")
    parser.add_argument("--max-ciclos", type=int, default=MAX_CICLOS_ATE_PRONTO,
                        dest="max_ciclos",
                        help="Limite de ciclos em modo --ate-pronto")
    parser.add_argument("--url", default="", dest="url_direta",
                        help="URL de arquivo direto pra baixar (.jpg/.mp4/etc)")
    parser.add_argument("--pagina", default="", dest="pagina_produto",
                        help="URL de página de produto (Shopee/Amazon/etc) "
                              "pra extrair og:image")
    parser.add_argument("--query", default="", dest="query_custom",
                        help="Query custom (sobrescreve heurística pras buscas)")
    parser.add_argument("--no-pexels", action="store_true",
                        dest="no_pexels",
                        help="Desativa busca no Pexels")
    parser.add_argument("--no-pixabay", action="store_true",
                        dest="no_pixabay",
                        help="Desativa busca no Pixabay")
    parser.add_argument("--no-hunter", action="store_true",
                        dest="no_hunter",
                        help="Não roda Asset Hunter após baixar (debug)")
    parser.add_argument("--dry-run", action="store_true",
                        dest="dry_run",
                        help="Lista o que faria sem baixar nada")
    parser.add_argument("--curar-inbox", action="store_true",
                        dest="curar_inbox",
                        help="Move arquivos órfãos da raiz inbox/ pras subpastas "
                              "videos/imagens (recuperação de versões antigas)")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info(f"🚁 ASSET AUTOPILOT v1")
    log.info("=" * 60)

    # --curar-inbox: ação simples, sem buscar nada
    if args.curar_inbox:
        log.info("🧹 Curando inbox raiz → subpastas...")
        r = curar_inbox_raiz()
        log.info(f"   Movidos: {len(r['movidos'])}")
        for m in r["movidos"][:10]:
            log.info(f"      ✅ {m['de']} → {Path(m['para']).parent.name}/")
        log.info(f"   Ignorados: {len(r['ignorados'])}")
        for i in r["ignorados"][:5]:
            log.info(f"      ⏭️  {i['arquivo']} ({i['motivo']})")
        log.info(f"   Erros: {len(r['erros'])}")
        for e in r["erros"][:5]:
            log.warning(f"      ❌ {e['arquivo']}: {e['erro']}")
        return 0 if not r["erros"] else 2

    r = autopilot_assets(
        produto=args.produto,
        max_downloads=args.max_downloads,
        ate_pronto=args.ate_pronto,
        max_ciclos=args.max_ciclos,
        url_direta=args.url_direta or None,
        pagina_produto=args.pagina_produto or None,
        query_custom=args.query_custom,
        dry_run=args.dry_run,
        ativar_pexels=not args.no_pexels,
        ativar_pixabay=not args.no_pixabay,
        executar_hunter=not args.no_hunter,
    )

    salvar_resultado(r)

    if r.get("pronto_para_edicao"):
        return 0
    if r.get("downloads_ok"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())