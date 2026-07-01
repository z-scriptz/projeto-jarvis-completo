# agents/audio_collector_agent.py
# Audio Collector Agent v1 do AgenteIA (Jarvis).
#
# Busca + baixa trilhas de áudio CC0 do Freesound, salva em
# assets/inbox/audio/ — de onde o Asset Hunter pega e organiza por produto.
#
# Fontes suportadas (v1):
#   - Freesound (token-based auth, previews MP3 128kbps)
#
# Filosofia:
#   - NUNCA chama Gemini
#   - NUNCA baixa áudio com licença restrita (filtra CC0 obrigatório)
#   - NUNCA armazena token no código (lê de env FREESOUND_API_KEY)
#   - Sempre baixa pra inbox (você revisa e Hunter organiza depois)
#   - Streaming download, chunks 8KB, limite 50MB por arquivo
#   - Anti-sobrescrita (sufixo _2, _3)
#   - Best-effort: falhas isoladas não derrubam batch
#
# Sobre licenças no Freesound:
#   - CC0          ✅ uso comercial livre, sem atribuição (única que usamos)
#   - CC-BY        ⚠️  precisa creditar — não usamos (problemático em TikTok)
#   - CC-BY-NC     ❌ não comercial — NUNCA usar pra afiliado
#   - Sampling+    ❌ regras estranhas — evitar
#
# Sobre previews vs original:
#   - Token simples → baixa só PREVIEWS (MP3 128kbps lossy)
#   - OAuth2 → baixa ORIGINAL (WAV/FLAC, mas é overkill pra TikTok)
#   - Pra TikTok, preview é suficiente — plataforma recomprime tudo de qualquer jeito
#
# Uso:
#   set FREESOUND_API_KEY=seu_token_aqui
#   python -m agents.audio_collector_agent --buscar "upbeat tiktok"
#   python -m agents.audio_collector_agent --buscar "lofi calm" --limite 10
#   python -m agents.audio_collector_agent --buscar "drums beat" --dry-run

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from shared.logger import get_logger

log = get_logger(__name__)

# =================================================================
# CONFIGURAÇÃO
# =================================================================

PROJETO_ROOT  = Path(__file__).parent.parent
INBOX_AUDIO   = PROJETO_ROOT / "assets" / "inbox" / "audio"
PLANS_DIR     = PROJETO_ROOT / "shared" / "content_plans"

# Freesound API
FREESOUND_BASE_URL = "https://freesound.org/apiv2"
FREESOUND_TIMEOUT  = 30
CHUNK_SIZE         = 8192
TAMANHO_MAX_MB     = 50    # áudio TikTok não precisa ser grande

# Filtros equilibrados (escolhidos pelo usuário): CC0 + rating ≥ 3.5 + 10-90s
FILTRO_LICENCA_DEFAULT  = 'license:"Creative Commons 0"'
FILTRO_RATING_DEFAULT   = "avg_rating:[3.5 TO 5.0]"
FILTRO_DURACAO_DEFAULT  = "duration:[10.0 TO 90.0]"

# Rate limit suave (Freesound permite 60 req/min com token)
ESPERA_ENTRE_DOWNLOADS = 1.0

USER_AGENT = "AgenteIA-AudioCollector/1.0"

# Status na planilha (se um dia integrarmos com Sheets)
STATUS_PENDENTE = "Pendente"
STATUS_BAIXADO  = "Baixado"
STATUS_ERRO     = "Erro"


# =================================================================
# AUTH
# =================================================================

def _eh_licenca_cc0(licenca: str) -> bool:
    """
    Detecta se uma string de licença representa CC0 / Public Domain.

    Aceita 3 formatos equivalentes que o Freesound usa:
      - "Creative Commons 0"                          (nome legado)
      - "cc0"                                          (abreviação)
      - "http://creativecommons.org/publicdomain/zero/..."  (URL canônica, formato atual)

    Returns: True se é CC0, False caso contrário.
    """
    if not licenca or not isinstance(licenca, str):
        return False
    s = licenca.strip().lower()
    if not s:
        return False
    # Padrões CC0 aceitos (em ordem de probabilidade)
    padroes_cc0 = (
        "creative commons 0",
        "publicdomain/zero",      # URL canônica
        "cc0",
        "creative commons zero",
    )
    return any(p in s for p in padroes_cc0)


def _obter_token() -> Optional[str]:
    """
    Lê o token do Freesound da variável de ambiente FREESOUND_API_KEY.
    Returns: token string ou None se não definida.
    """
    token = os.environ.get("FREESOUND_API_KEY", "").strip()
    if not token:
        return None
    return token


def _check_token() -> tuple[bool, str]:
    """Verifica se token está disponível. Retorna (ok, mensagem)."""
    token = _obter_token()
    if not token:
        return False, (
            "Variável FREESOUND_API_KEY não definida. "
            "No Windows: set FREESOUND_API_KEY=seu_token_aqui"
        )
    if len(token) < 16:
        return False, f"Token parece inválido (só {len(token)} caracteres)"
    return True, f"token presente ({token[:4]}...{token[-4:]})"


# =================================================================
# UTILS
# =================================================================

def _garantir_inbox():
    """Cria assets/inbox/audio/ se não existir."""
    INBOX_AUDIO.mkdir(parents=True, exist_ok=True)


def _sanitizar_nome(nome: str) -> str:
    """Remove caracteres problemáticos pra nome de arquivo."""
    if not isinstance(nome, str):
        nome = str(nome or "som")
    n = re.sub(r"[^\w\-.]", "_", nome)
    n = re.sub(r"_+", "_", n).strip("_")
    return n or "som"


def _destino_sem_conflito(pasta: Path, nome: str) -> Path:
    """Sufixo _2, _3 se já existir. Nunca sobrescreve."""
    candidato = pasta / nome
    if not candidato.exists():
        return candidato
    stem, suf = Path(nome).stem, Path(nome).suffix
    i = 2
    while True:
        candidato = pasta / f"{stem}_{i}{suf}"
        if not candidato.exists():
            return candidato
        i += 1
        if i > 99:
            return pasta / f"{stem}_{int(time.time())}{suf}"


def _resumir_url(url: str, max_chars: int = 60) -> str:
    try:
        p = urlparse(url)
        s = f"{p.netloc}{p.path}"
        if len(s) > max_chars:
            s = s[:max_chars - 3] + "..."
        return s
    except Exception:
        return url[:max_chars]


# =================================================================
# FREESOUND API
# =================================================================

def _executar_busca_freesound(params: dict) -> tuple[Optional[dict], str]:
    """Helper interno: executa um GET na busca, retorna (dados_json, erro_msg)."""
    try:
        import requests
    except ImportError:
        return None, "requests não instalado"

    url = f"{FREESOUND_BASE_URL}/search/text/"
    try:
        r = requests.get(url, params=params, timeout=FREESOUND_TIMEOUT,
                          headers={"User-Agent": USER_AGENT})
        if r.status_code == 401:
            return None, "401 Não autorizado — token inválido/expirado"
        if r.status_code == 429:
            return None, "429 Rate limit do Freesound — espere alguns minutos"
        r.raise_for_status()
        return r.json(), ""
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:140]}"


def buscar_freesound(query: str, limite: int = 5,
                      filtro_licenca: str = FILTRO_LICENCA_DEFAULT,
                      filtro_rating: str = FILTRO_RATING_DEFAULT,
                      filtro_duracao: str = FILTRO_DURACAO_DEFAULT,
                      debug_licenca: bool = False) -> dict:
    """
    Busca sons no Freesound com filtros de qualidade + CC0.

    Estratégia de busca em 2 tentativas:
      1. Filtro server-side completo (rating + duração + CC0). Mais eficiente.
      2. Se vier vazio, retira o filtro de licença e valida CC0 client-side.
         Resolve casos onde a sintaxe do filtro server-side é incompatível
         com como o Freesound indexa licenças atualmente.

    Returns: dict com 'resultados' (lista) ou erro.
    """
    if not query or not isinstance(query, str):
        return {"sucesso": False, "mensagem": "query vazia", "resultados": []}

    ok, msg = _check_token()
    if not ok:
        return {"sucesso": False, "mensagem": msg, "resultados": []}

    token = _obter_token()
    fields = "id,name,username,duration,license,avg_rating,previews,url,tags,filesize"

    # ── Tentativa 1: filtro server-side completo ──
    filtros_completos = [filtro_licenca, filtro_rating, filtro_duracao]
    filtro_combinado = " ".join(f for f in filtros_completos if f)

    # Pede mais resultados pra ter espaço pra filtrar client-side se necessário
    page_size = min(max(limite * 4, 15), 30)

    params = {
        "query":       query,
        "filter":      filtro_combinado,
        "fields":      fields,
        "page_size":   page_size,
        "sort":        "rating_desc",
        "token":       token,
    }

    log.info(f"🔍 Freesound: buscando '{query[:50]}' (filtros: CC0 + rating + duração)")
    data, erro = _executar_busca_freesound(params)
    if erro:
        return {"sucesso": False, "resultados": [],
                "mensagem": f"Erro na busca: {erro}"}

    total = data.get("count", 0)
    raw_results = data.get("results", [])
    estrategia_usada = "filtro_server_completo"

    # ── Tentativa 2: fallback sem filtro de licença + validação client-side ──
    if total == 0:
        log.info(f"   ⚠️  0 resultados com filtro CC0 server-side — tentando sem filtro de licença...")
        filtros_sem_licenca = [filtro_rating, filtro_duracao]
        params["filter"] = " ".join(f for f in filtros_sem_licenca if f)
        data, erro = _executar_busca_freesound(params)
        if erro:
            return {"sucesso": False, "resultados": [],
                    "mensagem": f"Erro na busca (fallback): {erro}"}
        total = data.get("count", 0)
        raw_results = data.get("results", [])
        estrategia_usada = "fallback_validacao_client"

    # ── Processa resultados (com validação CC0 client-side em ambas estratégias) ──
    resultados = []
    rejeitados_licenca = 0
    licencas_rejeitadas = []  # pra debug

    for s in raw_results:
        if len(resultados) >= limite:
            break

        # Validação CC0 client-side (cinto + suspensório, mesmo que server filtre)
        licenca_bruta = s.get("license", "")
        if not _eh_licenca_cc0(licenca_bruta):
            rejeitados_licenca += 1
            if debug_licenca and len(licencas_rejeitadas) < 5:
                licencas_rejeitadas.append(licenca_bruta)
            continue

        previews = s.get("previews") or {}
        preview_url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3")
        if not preview_url:
            continue

        resultados.append({
            "id":             s.get("id"),
            "name":           s.get("name", "som"),
            "username":       s.get("username", "anonymous"),
            "duration":       round(float(s.get("duration") or 0), 2),
            "license":        licenca_bruta,
            "rating":         round(float(s.get("avg_rating") or 0), 2),
            "preview_url":    preview_url,
            "url_freesound":  s.get("url", ""),
            "tags":           s.get("tags") or [],
            "filesize":       s.get("filesize"),
        })

    log.info(f"   ✅ {len(resultados)} resultado(s) válido(s) "
             f"(de {total} brutos, {rejeitados_licenca} rejeitados por licença, "
             f"estratégia: {estrategia_usada})")

    if debug_licenca and licencas_rejeitadas:
        log.info(f"   🔬 [debug] Licenças rejeitadas: {licencas_rejeitadas}")

    return {
        "sucesso":            True,
        "query":              query,
        "total_encontrados":  total,
        "retornados":         len(resultados),
        "rejeitados_licenca": rejeitados_licenca,
        "resultados":         resultados,
        "estrategia":         estrategia_usada,
        "filtros_aplicados":  filtro_combinado,
        "mensagem":           "ok",
    }


def baixar_audio_freesound(item: dict, prefixo: str = "") -> dict:
    """
    Baixa o preview MP3 de um som retornado por buscar_freesound.

    Args:
        item:    dict do resultado da busca (com 'preview_url', 'name', 'id')
        prefixo: opcional — texto pra prefixar no nome do arquivo (ex: "freesound_")

    Returns:
        {sucesso, destino, tamanho_bytes, mensagem, erro}
    """
    _garantir_inbox()
    base = {
        "destino":       None,
        "tamanho_bytes": 0,
        "mensagem":      "",
        "erro":          None,
        "id":            item.get("id"),
        "name":          item.get("name"),
        "license":       item.get("license"),
    }

    url = item.get("preview_url")
    if not url:
        return {**base, "sucesso": False, "erro": "preview_url ausente"}

    # Valida licença antes mesmo de tentar baixar (cinto e suspensório)
    licenca = item.get("license") or ""
    if not _eh_licenca_cc0(licenca):
        return {**base, "sucesso": False,
                "erro": f"licença não é CC0 ('{licenca}') — recusado"}

    try:
        import requests
    except ImportError:
        return {**base, "sucesso": False, "erro": "requests não instalado"}

    # Nome do arquivo: <prefixo><id>_<nome_sanitizado>.mp3
    id_ = item.get("id")
    nome_san = _sanitizar_nome(item.get("name", "som"))[:40]  # limita pra nomes curtos
    nome_arq = f"{prefixo}freesound_{id_}_{nome_san}.mp3" if id_ else f"{prefixo}freesound_{nome_san}.mp3"
    destino = _destino_sem_conflito(INBOX_AUDIO, nome_arq)

    log.info(f"   ⬇️  [{id_}] '{item.get('name', '?')[:40]}' "
             f"({item.get('duration', 0)}s, rating {item.get('rating', 0)})")

    try:
        with requests.get(url, stream=True, timeout=FREESOUND_TIMEOUT,
                           headers={"User-Agent": USER_AGENT}) as r:
            r.raise_for_status()

            # Verifica Content-Type
            ct = (r.headers.get("Content-Type") or "").lower()
            if not (ct.startswith("audio/") or "mpeg" in ct or "octet-stream" in ct):
                return {**base, "sucesso": False,
                        "erro": f"Content-Type inesperado: {ct}"}

            # Verifica tamanho declarado
            content_length = r.headers.get("Content-Length")
            if content_length:
                try:
                    mb = int(content_length) / 1024 / 1024
                    if mb > TAMANHO_MAX_MB:
                        return {**base, "sucesso": False,
                                "erro": f"arquivo grande demais: {mb:.1f}MB > {TAMANHO_MAX_MB}MB"}
                except ValueError:
                    pass

            # Stream
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
                        return {**base, "sucesso": False,
                                "erro": f"excedeu {TAMANHO_MAX_MB}MB durante download"}

        base["destino"]       = str(destino)
        base["tamanho_bytes"] = baixado
        base["mensagem"]      = f"baixado {baixado / 1024:.1f} KB"
        log.info(f"      ✅ → {destino.name} ({baixado / 1024:.1f} KB)")
        return {**base, "sucesso": True}

    except Exception as e:
        try:
            destino.unlink(missing_ok=True)
        except Exception:
            pass
        return {**base, "sucesso": False,
                "erro": f"{type(e).__name__}: {str(e)[:140]}"}


# =================================================================
# PIPELINE BUSCAR + BAIXAR
# =================================================================

def coletar_audio(query: str, limite: int = 5, dry_run: bool = False,
                   prefixo: str = "", debug_licenca: bool = False) -> dict:
    """
    Pipeline completo: busca + baixa pra inbox.
    """
    log.info("=" * 60)
    log.info(f"🎵 AUDIO COLLECTOR — '{query}'")
    log.info(f"   modo: {'DRY-RUN' if dry_run else 'REAL'} | limite: {limite}")
    log.info("=" * 60)

    busca = buscar_freesound(query, limite=limite, debug_licenca=debug_licenca)
    if not busca["sucesso"]:
        return {
            "sucesso":          False,
            "query":            query,
            "total_buscados":   0,
            "baixados":         0,
            "erros":            0,
            "destinos":         [],
            "mensagem":         busca["mensagem"],
        }

    resultados = busca["resultados"]
    if not resultados:
        return {
            "sucesso":          True,
            "query":            query,
            "total_buscados":   0,
            "baixados":         0,
            "erros":            0,
            "destinos":         [],
            "mensagem":         f"Nenhum resultado pra '{query}' com filtros CC0",
        }

    log.info(f"\n📋 {len(resultados)} candidato(s) — {'simulando' if dry_run else 'baixando'}:")
    for r in resultados:
        log.info(f"   • [{r['id']}] {r['name'][:50]} ({r['duration']}s, rating {r['rating']}, by {r['username']})")

    if dry_run:
        return {
            "sucesso":         True,
            "query":           query,
            "total_buscados":  len(resultados),
            "baixados":        0,
            "erros":           0,
            "destinos":        [],
            "resultados":      resultados,
            "mensagem":        "dry-run — sem download",
            "modo":            "dry_run",
        }

    # Baixa cada um
    baixados = 0
    erros = 0
    destinos = []
    detalhes = []

    log.info(f"\n⬇️  Iniciando downloads...")
    for i, item in enumerate(resultados, 1):
        r = baixar_audio_freesound(item, prefixo=prefixo)
        detalhes.append({**item, "resultado_download": r})
        if r["sucesso"]:
            baixados += 1
            destinos.append(r["destino"])
        else:
            erros += 1
            log.warning(f"      ❌ falhou: {r.get('erro', '?')}")

        # Rate limit suave (Freesound permite 60/min)
        if i < len(resultados):
            time.sleep(ESPERA_ENTRE_DOWNLOADS)

    log.info(f"\n📊 Total: {len(resultados)} buscado(s) | "
             f"✅ baixados: {baixados} | ❌ erros: {erros}")

    return {
        "sucesso":          True,
        "query":            query,
        "total_buscados":   len(resultados),
        "baixados":         baixados,
        "erros":            erros,
        "destinos":         destinos,
        "resultados":       detalhes,
        "mensagem":         f"{baixados} de {len(resultados)} baixados",
        "modo":             "real",
        "timestamp":        time.strftime("%Y-%m-%d %H:%M:%S"),
    }


# =================================================================
# RELATÓRIO + CLI
# =================================================================

def salvar_resultado(resultado: dict) -> Optional[str]:
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        path = PLANS_DIR / "audio_collector_resultado.json"
        path.write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return str(path)
    except Exception as e:
        log.warning(f"Falha ao salvar: {e}")
        return None


def imprimir_relatorio(r: dict):
    print("\n" + "=" * 60)
    print(f"  🎵 AUDIO COLLECTOR — Relatório")
    print("=" * 60)
    print(f"  Query:           {r.get('query', '?')}")
    print(f"  Modo:            {r.get('modo', '?')}")
    print(f"  Buscados:        {r.get('total_buscados', 0)}")
    print(f"  Baixados:        {r.get('baixados', 0)}")
    print(f"  Erros:           {r.get('erros', 0)}")

    if r.get("mensagem"):
        print(f"\n  Mensagem: {r['mensagem']}")

    destinos = r.get("destinos") or []
    if destinos:
        print(f"\n  💾 Áudios salvos em assets/inbox/audio/:")
        for d in destinos:
            print(f"     • {Path(d).name}")

        # Mostra autores (transparência — mesmo CC0 é bom saber quem fez)
        autores = []
        for res in (r.get("resultados") or []):
            if isinstance(res, dict) and res.get("resultado_download", {}).get("sucesso"):
                nome = res.get("name", "?")[:40]
                autor = res.get("username", "?")
                fs_id = res.get("id", "?")
                autores.append(f"     • [{fs_id}] {nome} — por @{autor}")
        if autores:
            print(f"\n  👤 Autores (CC0, atribuição opcional):")
            for a in autores:
                print(a)

        print(f"\n  📋 Próximo passo:")
        print(f"     python -m agents.asset_hunter_agent --produto \"X\" --mover")

    erros_detalhes = [
        x for x in (r.get("resultados") or [])
        if isinstance(x, dict) and x.get("resultado_download", {}).get("erro")
    ]
    if erros_detalhes:
        print(f"\n  ⚠️  Erros detalhados:")
        for x in erros_detalhes[:5]:
            nome = x.get("name", "?")[:40]
            err = x.get("resultado_download", {}).get("erro", "?")
            print(f"     • {nome}: {err}")

    print(f"\n  💾 Detalhes em: shared/content_plans/audio_collector_resultado.json")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Audio Collector — baixa trilhas CC0 do Freesound pra inbox"
    )
    parser.add_argument("--buscar", required=False, default="",
                        help="Termo de busca (ex: 'upbeat tiktok')")
    parser.add_argument("--limite", type=int, default=5,
                        help="Máximo de áudios a baixar (default: 5, max 30)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Só lista candidatos, não baixa")
    parser.add_argument("--prefixo", default="",
                        help="Prefixo opcional no nome do arquivo")
    parser.add_argument("--debug-licenca", action="store_true",
                        dest="debug_licenca",
                        help="Mostra licenças bruta dos sons rejeitados (debug)")
    parser.add_argument("--check-token", action="store_true",
                        help="Só verifica se o token está OK e sai")
    args = parser.parse_args()

    if args.check_token:
        ok, msg = _check_token()
        print(f"{'✅' if ok else '❌'} {msg}")
        return 0 if ok else 2

    if not args.buscar:
        parser.print_help()
        print("\n  ⚠️  Use --buscar 'termo' pra começar")
        print("     Ex: python -m agents.audio_collector_agent --buscar 'upbeat tiktok'")
        return 2

    r = coletar_audio(query=args.buscar, limite=args.limite,
                       dry_run=args.dry_run, prefixo=args.prefixo,
                       debug_licenca=args.debug_licenca)
    salvar_resultado(r)
    imprimir_relatorio(r)

    if not r.get("sucesso"):
        return 2
    if r.get("erros", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())