# agents/asset_agent.py
# Asset Agent v1 do AgenteIA (Jarvis).
#
# Gestão de assets REAIS de produto: vídeos crus, imagens e áudio que
# serão matéria-prima do Creative Engine pra montar vídeos de afiliado
# de verdade — em vez do placeholder atual (fundo + texto).
#
# Estrutura criada:
#   assets/
#   └── produtos/
#       └── <slug_produto>/
#           ├── raw/         ← clipes de vídeo brutos
#           ├── imagens/     ← thumbnails, fotos do produto
#           ├── audio/       ← trilha sonora, narração
#           └── metadata.json
#
# Filosofia:
#   - NUNCA chama Gemini, abre TikTok, baixa nada da internet ou posta
#   - NUNCA crasha: qualquer falha vira warning no relatório
#   - Custo zero — só leitura/escrita de arquivos locais
#
# Uso direto:
#   python -m agents.asset_agent
#
# Uso programático (futuro Creative Engine):
#   from agents.asset_agent import verificar_assets_produto
#   status = verificar_assets_produto("Mini Aspirador de Teclado")
#   if status["deve_aguardar"]:
#       # marcar produto como "Aguardando_Assets" na planilha
#       ...
#   else:
#       # tem clipes suficientes — Creative Engine pode montar
#       ...

import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Optional

from shared.logger import get_logger

log = get_logger(__name__)

# =================================================================
# CONFIGURAÇÃO
# =================================================================

PROJETO_ROOT = Path(__file__).parent.parent
ASSETS_ROOT  = PROJETO_ROOT / "assets" / "produtos"
PLANS_DIR    = PROJETO_ROOT / "shared" / "content_plans"

# Extensões aceitas em cada pasta
EXT_VIDEO   = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
EXT_IMAGEM  = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
EXT_AUDIO   = {".mp3", ".wav", ".m4a", ".ogg", ".aac"}

# Tamanho abaixo do qual o vídeo é provável "placeholder" (KB)
TAMANHO_PROVAVEL_PLACEHOLDER_KB = 200

# Pontos de corte pra classificar status
MINIMO_CLIPES_PRONTO  = 3      # < isso → assets_insuficientes
MINIMO_CLIPES_PREMIUM = 5      # ≥ isso + áudio + variedade → premium

# Aspect ratio alvo (TikTok = 9:16)
ASPECT_RATIO_ALVO     = 9 / 16
ASPECT_RATIO_TOLERANCIA = 0.05  # ±5% considerado "vertical"

# Score por categoria (soma até 100)
PONTOS_CLIPES_BASICOS   = 35   # 3+ clipes
PONTOS_CLIPES_PREMIUM   = 15   # 5+ clipes
PONTOS_COBERTURA_CENAS  = 25   # variedade de propósitos
PONTOS_AUDIO            = 10   # tem áudio próprio
PONTOS_IMAGENS          = 10   # ≥ 2 imagens
PONTOS_AR_VERTICAL      = 5    # maioria já em 9:16


# =================================================================
# 1) SLUGIFICAR
# =================================================================

def slugificar_produto(nome: str) -> str:
    """
    Converte 'Mini Aspirador de Teclado!' → 'mini_aspirador_de_teclado'.
    Remove acentos, especiais, deixa lowercase, troca espaços por '_'.
    Estável: rodar 2x dá o mesmo resultado.
    """
    if not isinstance(nome, str):
        nome = str(nome or "")

    # Remove acentos (NFD decompõe; filtra marks)
    nfkd = unicodedata.normalize("NFD", nome)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))

    # Lowercase + colapsa whitespace + troca por underscore
    s = sem_acento.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)       # remove especiais (mantém letras/digit/_/-)
    s = re.sub(r"[\s-]+", "_", s)        # whitespace/hífens → underscore
    s = re.sub(r"_+", "_", s).strip("_") # colapsa múltiplos _
    return s or "produto_sem_nome"


# =================================================================
# 2) CRIAR PASTA DE ASSETS
# =================================================================

def _metadata_inicial(produto_nome: str, slug: str) -> dict:
    return {
        "produto":             produto_nome,
        "slug":                slug,
        "criado_em":           time.strftime("%Y-%m-%d %H:%M:%S"),
        "atualizado_em":       time.strftime("%Y-%m-%d %H:%M:%S"),
        "nicho":               "",
        "fonte_assets":        "manual",  # manual | shopee | gravado | etc
        "notas":               "",
        "cache_videos":        {},        # cache: arquivo → {duracao, tamanho, mtime}
        "propositos_clipes":   {},        # cache: arquivo → "dor"|"demo"|"resultado"|"close"|"cta"
    }


def criar_pasta_assets_produto(produto_nome: str) -> dict:
    """
    Cria a estrutura assets/produtos/<slug>/{raw,imagens,audio} +
    metadata.json (se não existir).

    Idempotente: chamar várias vezes não quebra nada e não sobrescreve
    metadata.json existente.

    Returns:
        {"sucesso": bool, "slug": str, "pasta": str, "criado": bool, "mensagem": str}
    """
    slug = slugificar_produto(produto_nome)
    pasta = ASSETS_ROOT / slug

    ja_existia = pasta.exists()
    try:
        (pasta / "raw").mkdir(parents=True, exist_ok=True)
        (pasta / "imagens").mkdir(parents=True, exist_ok=True)
        (pasta / "audio").mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return {
            "sucesso":   False,
            "slug":      slug,
            "pasta":     str(pasta),
            "criado":    False,
            "mensagem":  f"Falha ao criar pastas: {e}",
        }

    meta_path = pasta / "metadata.json"
    if not meta_path.exists():
        try:
            meta_path.write_text(
                json.dumps(_metadata_inicial(produto_nome, slug),
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            log.warning(f"Pasta criada mas metadata.json falhou: {e}")

    log.info(
        f"📁 Asset pasta {'reutilizada' if ja_existia else 'CRIADA'}: "
        f"{pasta.relative_to(PROJETO_ROOT)}"
    )
    return {
        "sucesso":  True,
        "slug":     slug,
        "pasta":    str(pasta),
        "criado":   not ja_existia,
        "mensagem": "Pasta pronta" if ja_existia else "Pasta criada do zero",
    }


# =================================================================
# 3) VERIFICAR ASSETS DE PRODUTO
# =================================================================

def _ler_metadata(pasta: Path) -> dict:
    meta_path = pasta / "metadata.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _salvar_metadata(pasta: Path, meta: dict):
    meta["atualizado_em"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        (pasta / "metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning(f"Falha ao salvar metadata: {e}")


def _info_video(arquivo: Path, cache_videos: dict) -> dict:
    """
    Tenta extrair duração + dimensões do vídeo via MoviePy.
    Usa cache em metadata.json baseado em mtime — só relê se arquivo mudou.

    Returns:
        {"duracao_seg": float, "largura": int, "altura": int,
         "aspect_ratio": float, "tamanho_bytes": int, "lido_via": str}
    """
    nome = arquivo.name
    try:
        stat = arquivo.stat()
        mtime = int(stat.st_mtime)
        tam = stat.st_size
    except Exception:
        return {"erro": "stat falhou"}

    # Cache hit
    cached = cache_videos.get(nome)
    if cached and cached.get("mtime") == mtime:
        return cached

    info = {
        "mtime":         mtime,
        "tamanho_bytes": tam,
        "duracao_seg":   None,
        "largura":       None,
        "altura":        None,
        "aspect_ratio":  None,
        "lido_via":      "stat_only",
    }

    # Tenta MoviePy
    try:
        from moviepy.editor import VideoFileClip
        try:
            with VideoFileClip(str(arquivo)) as clip:
                info["duracao_seg"]  = round(float(clip.duration or 0), 2)
                info["largura"]      = int(clip.w) if clip.w else None
                info["altura"]       = int(clip.h) if clip.h else None
                if info["largura"] and info["altura"]:
                    info["aspect_ratio"] = round(info["largura"] / info["altura"], 3)
                info["lido_via"]     = "moviepy"
        except Exception as e:
            log.debug(f"MoviePy falhou pra '{nome}': {e}")
            info["erro_moviepy"] = str(e)[:120]
    except ImportError:
        pass  # moviepy não instalado — cai pra stat_only

    cache_videos[nome] = info
    return info


def _propor_proposito_pelo_nome(nome_arquivo: str) -> Optional[str]:
    """
    Heurística simples por nome de arquivo. Útil quando o usuário
    nomeia clipes como 'demo_aspirando.mp4' ou 'closeup_produto.mov'.
    Returns: 'dor' | 'demo' | 'resultado' | 'close' | 'cta' | None
    """
    n = nome_arquivo.lower()
    mapa = [
        (("dor", "problema", "antes", "sujo", "bagunca"), "dor"),
        (("demo", "demonstr", "uso", "usando", "acao", "ação"), "demo"),
        (("resultado", "depois", "limpo", "antes_depois"), "resultado"),
        (("close", "closeup", "produto", "embalagem"), "close"),
        (("cta", "link", "compre", "corre"), "cta"),
    ]
    for chaves, propos in mapa:
        if any(k in n for k in chaves):
            return propos
    return None


def verificar_assets_produto(produto_nome: str) -> dict:
    """
    Inspeciona assets/produtos/<slug>/ e retorna um relatório completo
    do que tem lá. Decide se Creative Engine pode usar ou se deve
    marcar produto como "Aguardando_Assets".

    Returns:
        {
            "sucesso":             bool,
            "produto":             str,
            "slug":                str,
            "pasta":               str,
            "status":              "sem_assets" | "assets_insuficientes"
                                   | "pronto_para_edicao" | "pronto_para_edicao_premium",
            "deve_aguardar":       bool,    ← usar isso direto no orchestrator
            "score_prontidao":     int,     0-100
            "videos":              {qtd, total_bytes, duracao_total_seg, suspeitos_placeholder, ...},
            "imagens":             {qtd, total_bytes},
            "audio":               {qtd, total_bytes, tem_audio: bool},
            "cobertura_cenas":     {dor: bool, demo: bool, resultado: bool, close: bool, cta: bool},
            "avisos":              [...],
            "recomendacoes":       [...],
        }
    """
    slug = slugificar_produto(produto_nome)
    pasta = ASSETS_ROOT / slug

    relatorio = {
        "sucesso":         True,
        "produto":         produto_nome,
        "slug":            slug,
        "pasta":           str(pasta),
        "status":          "sem_assets",
        "deve_aguardar":   True,
        "score_prontidao": 0,
        "videos":          {"qtd": 0, "amostra": [], "total_bytes": 0,
                            "duracao_total_seg": 0.0, "suspeitos_placeholder": 0,
                            "ar_vertical_qtd": 0, "ar_horizontal_qtd": 0},
        "imagens":         {"qtd": 0, "total_bytes": 0},
        "audio":           {"qtd": 0, "total_bytes": 0, "tem_audio": False},
        "cobertura_cenas": {"dor": False, "demo": False, "resultado": False,
                            "close": False, "cta": False},
        "avisos":          [],
        "recomendacoes":   [],
        "timestamp":       time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    if not pasta.exists():
        relatorio["avisos"].append(f"Pasta de assets não existe: {pasta.relative_to(PROJETO_ROOT)}")
        relatorio["recomendacoes"].append(
            f"Rode criar_pasta_assets_produto('{produto_nome}') pra criar a estrutura."
        )
        return relatorio

    meta = _ler_metadata(pasta)
    cache_videos = meta.get("cache_videos", {})

    # ── Vídeos ──
    raw_dir = pasta / "raw"
    if raw_dir.exists():
        videos = [v for v in raw_dir.iterdir()
                  if v.is_file() and v.suffix.lower() in EXT_VIDEO]
        relatorio["videos"]["qtd"] = len(videos)

        propositos_existentes = meta.get("propositos_clipes", {})

        for v in videos:
            info = _info_video(v, cache_videos)
            relatorio["videos"]["total_bytes"] += info.get("tamanho_bytes", 0) or 0
            dur = info.get("duracao_seg") or 0
            relatorio["videos"]["duracao_total_seg"] += dur

            # Detector de placeholder: pequeno + sem áudio detectado
            tam_kb = (info.get("tamanho_bytes", 0) or 0) / 1024
            if tam_kb < TAMANHO_PROVAVEL_PLACEHOLDER_KB:
                relatorio["videos"]["suspeitos_placeholder"] += 1

            # Aspect ratio
            ar = info.get("aspect_ratio")
            if ar is not None:
                # 9/16 ≈ 0.5625 — vertical é AR < ~0.7
                if abs(ar - ASPECT_RATIO_ALVO) < ASPECT_RATIO_TOLERANCIA:
                    relatorio["videos"]["ar_vertical_qtd"] += 1
                elif ar > 1.0:
                    relatorio["videos"]["ar_horizontal_qtd"] += 1

            relatorio["videos"]["amostra"].append({
                "nome":          v.name,
                "tamanho_kb":    round(tam_kb, 1),
                "duracao_seg":   dur,
                "aspect_ratio":  ar,
                "proposito":     propositos_existentes.get(v.name)
                                 or _propor_proposito_pelo_nome(v.name),
            })

        # Limita amostra a 10 (relatórios não viram romance)
        relatorio["videos"]["amostra"] = relatorio["videos"]["amostra"][:10]

        # Cobertura de propósitos
        for item in relatorio["videos"]["amostra"]:
            prop = item.get("proposito")
            if prop in relatorio["cobertura_cenas"]:
                relatorio["cobertura_cenas"][prop] = True

        # Arredonda duração total
        relatorio["videos"]["duracao_total_seg"] = round(
            relatorio["videos"]["duracao_total_seg"], 2
        )

    # ── Imagens ──
    img_dir = pasta / "imagens"
    if img_dir.exists():
        imgs = [i for i in img_dir.iterdir()
                if i.is_file() and i.suffix.lower() in EXT_IMAGEM]
        relatorio["imagens"]["qtd"] = len(imgs)
        relatorio["imagens"]["total_bytes"] = sum(
            (i.stat().st_size for i in imgs), 0
        )

    # ── Áudio ──
    aud_dir = pasta / "audio"
    if aud_dir.exists():
        auds = [a for a in aud_dir.iterdir()
                if a.is_file() and a.suffix.lower() in EXT_AUDIO]
        relatorio["audio"]["qtd"] = len(auds)
        relatorio["audio"]["total_bytes"] = sum(
            (a.stat().st_size for a in auds), 0
        )
        relatorio["audio"]["tem_audio"] = len(auds) > 0

    # ── Score + status ──
    score = 0
    qtd_v = relatorio["videos"]["qtd"]
    if qtd_v >= MINIMO_CLIPES_PRONTO:
        score += PONTOS_CLIPES_BASICOS
    if qtd_v >= MINIMO_CLIPES_PREMIUM:
        score += PONTOS_CLIPES_PREMIUM

    propositos_cobertos = sum(1 for v in relatorio["cobertura_cenas"].values() if v)
    score += int(PONTOS_COBERTURA_CENAS * propositos_cobertos / 5)

    if relatorio["audio"]["tem_audio"]:
        score += PONTOS_AUDIO
    if relatorio["imagens"]["qtd"] >= 2:
        score += PONTOS_IMAGENS
    if qtd_v > 0:
        if relatorio["videos"]["ar_vertical_qtd"] >= qtd_v / 2:
            score += PONTOS_AR_VERTICAL

    relatorio["score_prontidao"] = min(100, score)

    # Decide status
    if qtd_v == 0 and relatorio["imagens"]["qtd"] == 0:
        relatorio["status"] = "sem_assets"
        relatorio["deve_aguardar"] = True
    elif qtd_v < MINIMO_CLIPES_PRONTO:
        relatorio["status"] = "assets_insuficientes"
        relatorio["deve_aguardar"] = True
    elif qtd_v >= MINIMO_CLIPES_PREMIUM and propositos_cobertos >= 3 \
         and relatorio["audio"]["tem_audio"]:
        relatorio["status"] = "pronto_para_edicao_premium"
        relatorio["deve_aguardar"] = False
    else:
        relatorio["status"] = "pronto_para_edicao"
        relatorio["deve_aguardar"] = False

    # Avisos contextuais
    susp = relatorio["videos"]["suspeitos_placeholder"]
    if susp > 0:
        relatorio["avisos"].append(
            f"{susp} vídeo(s) suspeito(s) de placeholder (<{TAMANHO_PROVAVEL_PLACEHOLDER_KB} KB)"
        )
    if qtd_v > 0 and relatorio["videos"]["ar_horizontal_qtd"] > 0:
        relatorio["avisos"].append(
            f"{relatorio['videos']['ar_horizontal_qtd']} clipe(s) horizontal(is) — "
            f"TikTok prefere 9:16 (cortar ou aplicar blur background)"
        )
    if not relatorio["audio"]["tem_audio"]:
        relatorio["avisos"].append("Sem áudio próprio — Creative Engine precisará adicionar trilha")

    # Recomendações por status
    if relatorio["status"] == "sem_assets":
        relatorio["recomendacoes"].append(
            f"Capture/baixe pelo menos {MINIMO_CLIPES_PRONTO} clipes e coloque em raw/"
        )
    elif relatorio["status"] == "assets_insuficientes":
        falta = MINIMO_CLIPES_PRONTO - qtd_v
        relatorio["recomendacoes"].append(
            f"Falta(m) {falta} clipe(s) pra atingir o mínimo de {MINIMO_CLIPES_PRONTO}"
        )
    elif relatorio["status"] == "pronto_para_edicao":
        faltantes = [k for k, v in relatorio["cobertura_cenas"].items() if not v]
        if faltantes:
            relatorio["recomendacoes"].append(
                f"Pra upgrade pra premium: cobrir cena(s) {faltantes} "
                f"(renomeie clipes pra incluir palavra-chave)"
            )

    # Persiste cache atualizado
    if meta:
        meta["cache_videos"] = cache_videos
        _salvar_metadata(pasta, meta)

    log.info(
        f"🔍 {produto_nome}: status={relatorio['status']} | "
        f"score={relatorio['score_prontidao']}/100 | "
        f"videos={qtd_v} imagens={relatorio['imagens']['qtd']} audio={relatorio['audio']['qtd']}"
    )
    return relatorio


# =================================================================
# 4) LISTAR PRODUTOS COM ASSETS
# =================================================================

def listar_produtos_com_assets() -> dict:
    """
    Varre assets/produtos/ e retorna lista de todos os produtos
    com algum asset registrado, ordenados por score de prontidão.
    """
    resultado = {
        "sucesso":     True,
        "total":       0,
        "prontos":     [],  # status pronto_*
        "incompletos": [],  # assets_insuficientes
        "vazios":      [],  # sem_assets (pasta criada mas vazia)
        "timestamp":   time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    if not ASSETS_ROOT.exists():
        resultado["sucesso"] = False
        resultado["mensagem"] = f"Diretório de assets não existe: {ASSETS_ROOT}"
        return resultado

    pastas_produto = [p for p in ASSETS_ROOT.iterdir() if p.is_dir()]
    resultado["total"] = len(pastas_produto)

    for pasta in pastas_produto:
        meta = _ler_metadata(pasta)
        produto_nome = meta.get("produto") or pasta.name
        status = verificar_assets_produto(produto_nome)

        item = {
            "produto":         produto_nome,
            "slug":            pasta.name,
            "status":          status["status"],
            "score":           status["score_prontidao"],
            "videos":          status["videos"]["qtd"],
            "imagens":         status["imagens"]["qtd"],
            "audio":           status["audio"]["qtd"],
        }

        if status["status"].startswith("pronto"):
            resultado["prontos"].append(item)
        elif status["status"] == "assets_insuficientes":
            resultado["incompletos"].append(item)
        else:
            resultado["vazios"].append(item)

    # Ordena cada lista por score desc
    resultado["prontos"].sort(key=lambda x: x["score"], reverse=True)
    resultado["incompletos"].sort(key=lambda x: x["score"], reverse=True)

    log.info(
        f"📊 Total de produtos: {resultado['total']} | "
        f"prontos: {len(resultado['prontos'])} | "
        f"incompletos: {len(resultado['incompletos'])} | "
        f"vazios: {len(resultado['vazios'])}"
    )
    return resultado


# =================================================================
# 5) BRIEF DE ASSETS NECESSÁRIOS
# =================================================================

# Templates por nicho — dicionário, NÃO Gemini.
# Cada nicho ajusta as recomendações de cada cena pra contexto real.
BRIEFS_POR_NICHO = {
    "Casa/Tech": {
        "dor":       "Close no problema real (ex: teclado sujo, fios bagunçados, móvel empoeirado). Iluminação natural, 3-5s.",
        "demo":      "Produto em uso no ambiente real (mesa, sala, escritório). Mostre as mãos operando. 4-6s.",
        "resultado": "Antes vs Depois lado a lado, ou close no resultado limpo/organizado. 3-4s.",
        "close":     "Embalagem do produto, marca visível, detalhes técnicos (botões, conectores). 2-3s.",
        "cta":       "Mãos apontando pro produto + tela com texto 'Link na bio'. 2-3s.",
    },
    "Beleza": {
        "dor":       "Close no rosto/pele com o problema (mancha, oleosidade, frizz). Ângulo frontal, luz suave. 3-5s.",
        "demo":      "Aplicação do produto em câmera lenta, foco na textura/efeito imediato. 5-7s.",
        "resultado": "Antes vs Depois com mesma iluminação, ou close no efeito final brilhante. 3-4s.",
        "close":     "Embalagem do produto + textura/cor visível. Gire o frasco/bisnaga lentamente. 2-3s.",
        "cta":       "Sorriso + apontar pro produto + texto 'Compre na bio'. 2-3s.",
    },
    "Cozinha": {
        "dor":       "Bagunça/dificuldade pré-produto (ex: descascar batata difícil, panela queimando). 3-5s.",
        "demo":      "Produto em ação fazendo a tarefa. Top-down ou ângulo de chef. 5-7s.",
        "resultado": "Comida/cozinha pronta, brilhante, apetitosa. Close + plate-up. 3-4s.",
        "close":     "Detalhes do produto: cabo, material, partes desmontáveis. 2-3s.",
        "cta":       "Mão segurando o produto + texto CTA. Som de 'ding' opcional. 2-3s.",
    },
    "Fitness": {
        "dor":       "Pessoa cansada/sem energia/equipamento ineficaz. Tom dramático. 3-5s.",
        "demo":      "Uso correto do produto durante treino, múltiplos ângulos. 5-7s.",
        "resultado": "Resultado físico, energia renovada, sorriso. Suor opcional. 3-4s.",
        "close":     "Produto detalhado, materiais, ergonomia. 2-3s.",
        "cta":       "Atleta apontando + texto motivacional. 2-3s.",
    },
}

BRIEF_GENERICO = {
    "dor":       "Mostre o problema/incômodo que o produto resolve. 3-5s.",
    "demo":      "Produto em uso real, mãos operando, iluminação clara. 5-7s.",
    "resultado": "Antes vs Depois ou efeito final claramente positivo. 3-4s.",
    "close":     "Produto sozinho em destaque, marca visível. 2-3s.",
    "cta":       "Convite à ação visual + texto 'Link na bio'. 2-3s.",
}


def gerar_brief_assets_necessarios(produto_nome: str, nicho: str = "") -> dict:
    """
    Gera um brief acionável do que capturar/baixar pra montar
    vídeo de afiliado bom. Adapta linguagem ao nicho.

    Sem Gemini — usa templates determinísticos.

    Returns:
        {
            "sucesso":         True,
            "produto":         str,
            "nicho":           str,
            "template_usado":  str,
            "cenas":           [
                {"id": "dor", "ordem": 1, "duracao_alvo_seg": "3-5",
                 "descricao": str, "essencial": bool},
                ...
            ],
            "duracao_total_alvo_seg": "12-22",
            "formato_alvo":     "vertical 9:16, 1080x1920",
            "dica_extra":       str,
        }
    """
    nicho_norm = (nicho or "").strip()
    template = BRIEFS_POR_NICHO.get(nicho_norm, BRIEF_GENERICO)
    template_usado = nicho_norm if nicho_norm in BRIEFS_POR_NICHO else "generico"

    cenas = [
        {"id": "dor",       "ordem": 1, "duracao_alvo_seg": "3-5", "descricao": template["dor"],       "essencial": True},
        {"id": "demo",      "ordem": 2, "duracao_alvo_seg": "5-7", "descricao": template["demo"],      "essencial": True},
        {"id": "resultado", "ordem": 3, "duracao_alvo_seg": "3-4", "descricao": template["resultado"], "essencial": True},
        {"id": "close",     "ordem": 4, "duracao_alvo_seg": "2-3", "descricao": template["close"],     "essencial": False},
        {"id": "cta",       "ordem": 5, "duracao_alvo_seg": "2-3", "descricao": template["cta"],       "essencial": True},
    ]

    dica = (
        "Nomeie os arquivos com o id da cena (ex: 'demo_aspirando.mp4', "
        "'closeup_produto.mov') pra o Asset Agent detectar cobertura automaticamente."
    )

    return {
        "sucesso":                True,
        "produto":                produto_nome,
        "nicho":                  nicho_norm,
        "template_usado":         template_usado,
        "cenas":                  cenas,
        "duracao_total_alvo_seg": "12-22",
        "formato_alvo":           "vertical 9:16, 1080x1920, ≤60s",
        "dica_extra":             dica,
        "timestamp":              time.strftime("%Y-%m-%d %H:%M:%S"),
    }


# =================================================================
# RELATÓRIO + MAIN
# =================================================================

def salvar_status(status: dict) -> Optional[str]:
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        caminho = PLANS_DIR / "asset_status.json"
        caminho.write_text(
            json.dumps(status, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        log.info(f"💾 Status salvo em: {caminho}")
        return str(caminho)
    except Exception as e:
        log.warning(f"⚠️ Falha ao salvar status: {e}")
        return None


def imprimir_relatorio(produto: str, status: dict, brief: dict, listagem: dict):
    print("\n" + "=" * 60)
    print(f"  📦 ASSET AGENT — Relatório de '{produto}'")
    print("=" * 60)

    print(f"\n  Slug:       {status['slug']}")
    print(f"  Pasta:      {status['pasta']}")
    print(f"  Status:     {status['status']}")
    print(f"  Score:      {status['score_prontidao']}/100")
    print(f"  Aguardar?:  {'SIM ⏸️' if status['deve_aguardar'] else 'NÃO ✅'}")

    print(f"\n  📊 Contagem:")
    print(f"    Vídeos:  {status['videos']['qtd']} ({status['videos']['total_bytes']/1024:.0f} KB total)")
    if status["videos"]["duracao_total_seg"]:
        print(f"             {status['videos']['duracao_total_seg']}s de duração total")
    if status["videos"]["suspeitos_placeholder"]:
        print(f"             ⚠️  {status['videos']['suspeitos_placeholder']} suspeito(s) de placeholder")
    print(f"    Imagens: {status['imagens']['qtd']}")
    print(f"    Áudio:   {status['audio']['qtd']}")

    print(f"\n  🎬 Cobertura de cenas:")
    for cena, ok in status["cobertura_cenas"].items():
        marca = "✅" if ok else "❌"
        print(f"    {marca}  {cena}")

    if status["avisos"]:
        print(f"\n  ⚠️  Avisos:")
        for a in status["avisos"]:
            print(f"     • {a}")

    if status["recomendacoes"]:
        print(f"\n  💡 Recomendações:")
        for r in status["recomendacoes"]:
            print(f"     • {r}")

    print(f"\n  📋 Brief sugerido (nicho: {brief['template_usado']}):")
    for c in brief["cenas"]:
        marca = "🎯" if c["essencial"] else "  "
        print(f"    {marca} {c['ordem']}. {c['id']:10s} [{c['duracao_alvo_seg']}s]  {c['descricao'][:55]}...")

    print(f"\n  📊 Total de produtos cadastrados: {listagem['total']}")
    print(f"     ✅ Prontos:     {len(listagem['prontos'])}")
    print(f"     🟡 Incompletos: {len(listagem['incompletos'])}")
    print(f"     🔴 Vazios:      {len(listagem['vazios'])}")

    print(f"\n  💾 Detalhes em: shared/content_plans/asset_status.json")
    print("=" * 60)


def main():
    """
    Teste padrão: cria pasta pra 'Mini Aspirador de Teclado',
    verifica assets, gera brief, lista produtos cadastrados, salva relatório.
    """
    log.info("=" * 60)
    log.info("📦 ASSET AGENT v1 — Iniciando diagnóstico")
    log.info("=" * 60)

    produto_teste = "Mini Aspirador de Teclado"
    nicho_teste   = "Casa/Tech"

    log.info(f"\n1️⃣  Criando estrutura para '{produto_teste}'...")
    criacao = criar_pasta_assets_produto(produto_teste)

    log.info(f"\n2️⃣  Verificando assets...")
    status = verificar_assets_produto(produto_teste)

    log.info(f"\n3️⃣  Gerando brief de cenas necessárias (nicho={nicho_teste})...")
    brief = gerar_brief_assets_necessarios(produto_teste, nicho_teste)

    log.info(f"\n4️⃣  Listando todos os produtos com assets...")
    listagem = listar_produtos_com_assets()

    relatorio_completo = {
        "produto_inspecionado": produto_teste,
        "criacao_pasta":        criacao,
        "status_assets":        status,
        "brief":                brief,
        "listagem_global":      listagem,
    }
    salvar_status(relatorio_completo)
    imprimir_relatorio(produto_teste, status, brief, listagem)

    # Exit code útil pra CI: 0 pronto, 1 aguardar, 2 erro
    if not status["sucesso"]:
        return 2
    return 1 if status["deve_aguardar"] else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())