# agents/audio_autopilot_agent.py
# Audio Autopilot Agent v1 do AgenteIA (Jarvis).
#
# Análogo ao Asset Autopilot, mas pra áudio. Quando produto está
# pronto_pra_editar mas SEM áudio, este agente:
#   1. Detecta nicho (do plano ou inferido pelo nome do produto)
#   2. Sugere queries curadas por nicho (dicionário interno)
#   3. Chama Audio Collector (Freesound CC0) via subprocess
#   4. Roda Asset Hunter pra mover de inbox → produto/audio/
#   5. Chama Audio Selector pra rankear (in-process — leve)
#   6. Reporta o melhor áudio escolhido com score
#
# Filosofia:
#   - NUNCA chama Gemini
#   - Reusa o que já existe: audio_collector, asset_hunter, audio_selector
#   - Subprocess com PYTHONIOENCODING=utf-8 (lição do Windows cp1252)
#   - Best-effort: se Collector falhar, sistema continua sem áudio
#   - Idempotente: se já tem áudio, só roda Selector
#
# CLI:
#   python -m agents.audio_autopilot_agent --produto "Cinto Modelador Slim Feminino"
#   python -m agents.audio_autopilot_agent --produto "X" --dry-run
#   python -m agents.audio_autopilot_agent --produto "X" --query "hip hop loop fitness"
#   python -m agents.audio_autopilot_agent --produto "X" --max-downloads 15
#   python -m agents.audio_autopilot_agent --produto "X" --forcar-coleta

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from shared.logger import get_logger
from agents.asset_agent import slugificar_produto

# Inferência de nicho via Copy Adapter (reuso de lógica)
try:
    from creative_engine.copy_adapter import inferir_nicho as _inferir_nicho_via_copy
    _COPY_ADAPTER_DISPONIVEL = True
except Exception:
    _COPY_ADAPTER_DISPONIVEL = False

log = get_logger(__name__)

# =================================================================
# CONFIGURAÇÃO
# =================================================================

PROJETO_ROOT = Path(__file__).parent.parent
PRODUTOS_ROOT = PROJETO_ROOT / "assets" / "produtos"
PLANS_DIR     = PROJETO_ROOT / "shared" / "content_plans"

EXT_AUDIO = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}

# Queries curadas por NICHO — em inglês (Freesound retorna melhor)
QUERIES_POR_NICHO = {
    "Beleza/Fitness": [
        "hip hop drum loop",
        "drum loop",
        "trap beat",
        "fashion loop",
        "workout beat",
        "electronic loop",
    ],
    "Beleza": [
        "fashion loop electronic",
        "elegant beat loop",
        "chill fashion music",
        "beauty vlog loop",
        "modern beauty beat",
    ],
    "Casa/Tech": [
        "hip hop drum loop",
        "tech electronic loop",
        "industrial beat 120 bpm",
        "modern tech background",
        "trap beat 120 bpm",
    ],
    "Casa": [
        "uplifting home loop",
        "chill home beat",
        "happy lifestyle loop",
        "modern lifestyle beat",
    ],
    "Cozinha": [
        "happy cooking loop",
        "uplifting kitchen beat",
        "fun cooking background",
    ],
    "Pet": [
        "happy pet loop",
        "playful upbeat beat",
        "fun animal background",
    ],
}

QUERIES_FALLBACK = [
    "hip hop drum loop",
    "electronic background loop",
    "upbeat beat 120 bpm",
]

# Inferência interna de nicho (fallback se Copy Adapter indisponível)
# keyword no nome do produto → nicho
_NICHO_KEYWORDS = [
    (("cinto modelador", "modelador", "slim", "shaper", "waist",
      "massageador", "fitness", "cervical", "academia", "treino"), "Beleza/Fitness"),
    (("maquiagem", "esfoliante", "skincare", "batom", "creme facial",
      "organizador acrilico", "organizador acrílico"), "Beleza"),
    (("aspirador", "teclado", "notebook", "laptop", "cabos", "usb",
      "carregador", "powerbank", "fone", "headset"), "Casa/Tech"),
    (("led", "lampada", "lâmpada", "fita led", "cortina led", "iluminacao",
      "iluminação", "vedante", "umidificador", "organizador"), "Casa"),
    (("cortador", "ralador", "espremedor", "fatiador", "panela", "frigideira"), "Cozinha"),
    (("pet", "cachorro", "gato", "coleira", "comedouro", "racao", "ração"), "Pet"),
]


def _inferir_nicho_interno(produto: str) -> str:
    """
    Fallback de inferência de nicho por keyword no nome do produto.
    Independe do Copy Adapter. Retorna "" se nada bater.
    """
    p = (produto or "").lower()
    for keywords, nicho in _NICHO_KEYWORDS:
        if any(kw in p for kw in keywords):
            return nicho
    return ""

# Quantas queries tentar por execução (rate limit Freesound)
MAX_QUERIES_POR_RUN = 3


# =================================================================
# DETECÇÃO DE ÁUDIO + PLANO
# =================================================================

def verificar_audio_produto(produto: str) -> dict:
    """Verifica se produto já tem áudio na pasta."""
    slug = slugificar_produto(produto)
    pasta = PRODUTOS_ROOT / slug / "audio"
    if not pasta.exists():
        return {"tem_audio": False, "total": 0, "arquivos": [], "pasta": str(pasta)}
    arquivos = sorted([
        f.name for f in pasta.iterdir()
        if f.is_file() and f.suffix.lower() in EXT_AUDIO
        and not f.name.startswith(".")
    ])
    return {
        "tem_audio": len(arquivos) > 0,
        "total":     len(arquivos),
        "arquivos":  arquivos,
        "pasta":     str(pasta),
    }


def carregar_plano_mais_recente(produto: str) -> Optional[dict]:
    """Lê plano_<slug>_<TS>.json mais recente."""
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
        m = re_ts.search(f.stem.replace("plano_", "", 1))
        ts_dt = None
        if m:
            try:
                ts_dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            except Exception:
                pass
        if ts_dt is None:
            try:
                ts_dt = datetime.fromtimestamp(f.stat().st_mtime)
            except Exception:
                continue
        candidatos.append((ts_dt, f, data))
    if not candidatos:
        return None
    candidatos.sort(key=lambda x: x[0], reverse=True)
    _, path, data = candidatos[0]
    data["_plano_path"] = str(path)
    return data


# =================================================================
# SUGESTÃO DE QUERIES
# =================================================================

def sugerir_queries(produto: str, nicho: str = "",
                     query_custom: str = "") -> list[str]:
    """
    Retorna lista de queries pra Freesound, ordenadas por prioridade.
    Mistura: query custom (se passada) + queries do nicho + fallback.
    """
    queries = []
    if query_custom:
        queries.append(query_custom)
    queries.extend(QUERIES_POR_NICHO.get(nicho, []))
    if not queries:
        queries.extend(QUERIES_FALLBACK)
    seen = set()
    final = []
    for q in queries:
        ql = q.lower().strip()
        if ql and ql not in seen:
            seen.add(ql)
            final.append(q)
    return final


# =================================================================
# SUBPROCESS HELPERS
# =================================================================

def _env_utf8() -> dict:
    """Env com UTF-8 forçado (resolve cp1252 do Windows com emojis)."""
    return {**os.environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1"}


def executar_audio_collector(query: str, limite: int = 10) -> dict:
    """
    Chama audio_collector_agent --buscar QUERY --limite N via subprocess.
    Retorna {sucesso, returncode, baixados_estimados, stderr, stdout_tail}.
    """
    try:
        cmd = [sys.executable, "-m", "agents.audio_collector_agent",
                "--buscar", query, "--limite", str(limite)]
        log.info(f"   🎵 Collector: --buscar '{query}' --limite {limite}")
        proc = subprocess.run(cmd, cwd=str(PROJETO_ROOT),
                                capture_output=True, text=True,
                                encoding="utf-8", errors="replace",
                                env=_env_utf8(), timeout=180)
        # Procura "Baixados: N" ou similares no stdout
        baixados = 0
        for linha in proc.stdout.splitlines():
            m = re.search(r"[Bb]aixados?\s*:?\s*(\d+)", linha)
            if m:
                baixados = max(baixados, int(m.group(1)))
        return {
            "sucesso":            proc.returncode == 0,
            "returncode":         proc.returncode,
            "baixados_estimados": baixados,
            "stderr":             proc.stderr[-400:] if proc.stderr else "",
            "stdout_tail":        proc.stdout[-300:] if proc.stdout else "",
        }
    except subprocess.TimeoutExpired:
        return {"sucesso": False, "baixados_estimados": 0, "stderr": "timeout (>180s)"}
    except Exception as e:
        return {"sucesso": False, "baixados_estimados": 0,
                "stderr": f"{type(e).__name__}: {str(e)[:140]}"}


def executar_asset_hunter(produto: str) -> dict:
    """Roda asset_hunter_agent --produto X --mover via subprocess."""
    try:
        cmd = [sys.executable, "-m", "agents.asset_hunter_agent",
                "--produto", produto, "--mover"]
        log.info(f"   🎯 Hunter: --produto '{produto}' --mover")
        proc = subprocess.run(cmd, cwd=str(PROJETO_ROOT),
                                capture_output=True, text=True,
                                encoding="utf-8", errors="replace",
                                env=_env_utf8(), timeout=120)
        return {
            "sucesso":    proc.returncode == 0,
            "returncode": proc.returncode,
            "stderr":     proc.stderr[-400:] if proc.stderr else "",
        }
    except Exception as e:
        return {"sucesso": False, "stderr": f"{type(e).__name__}: {str(e)[:140]}"}


def executar_audio_selector(produto: str, nicho: str = "") -> dict:
    """
    Chama audio_selector_agent IN-PROCESS (mais rápido, retorna estrutura rica).
    """
    try:
        from agents.audio_selector_agent import rankear_audios_do_produto
        r = rankear_audios_do_produto(produto, usar_librosa=True,
                                        usar_cache=True, nicho=nicho)
        melhor = r.get("melhor") or {}
        return {
            "sucesso":          r.get("sucesso", False),
            "melhor_audio":     melhor.get("arquivo"),
            "score":            melhor.get("score", 0),
            "motivos":          melhor.get("motivos", [])[:8],
            "total_analisados": r.get("total", 0),
            "librosa_usado":    r.get("librosa_usado", False),
        }
    except Exception as e:
        log.warning(f"   Selector falhou (best-effort): {e}")
        return {"sucesso": False, "melhor_audio": None, "score": 0,
                "erro": f"{type(e).__name__}: {str(e)[:140]}"}


# =================================================================
# PIPELINE PRINCIPAL
# =================================================================

def autopilot_audio(produto: str,
                     max_downloads: int = 10,
                     query_custom: str = "",
                     skip_se_tem_audio: bool = True,
                     dry_run: bool = False) -> dict:
    """
    Pipeline: detecta sem áudio → coleta (max 3 queries) → hunter → selector.

    Args:
        produto:             nome do produto
        max_downloads:       limite total de áudios baixados
        query_custom:        sobrescreve queries do nicho
        skip_se_tem_audio:   se True e já tem áudio, só roda Selector
        dry_run:             lista queries que tentaria, não baixa

    Returns: relatório completo com áudio_autopilot_usado / audio_escolhido / score / status
    """
    log.info("=" * 60)
    log.info(f"🎵 AUDIO AUTOPILOT — '{produto}'")
    log.info(f"   Modo: {'DRY-RUN' if dry_run else 'REAL'} | max-downloads: {max_downloads}")
    log.info("=" * 60)

    slug = slugificar_produto(produto)

    # Lê plano + infere nicho (camadas de fallback)
    plano = carregar_plano_mais_recente(produto)
    nicho = ""
    if plano:
        nicho_raw = plano.get("nicho")
        # Normaliza: None, "", "?", "  " → tratado como vazio
        if isinstance(nicho_raw, str) and nicho_raw.strip() and nicho_raw.strip() != "?":
            nicho = nicho_raw.strip()
            log.info(f"   📋 Plano: {Path(plano.get('_plano_path', '?')).name}, nicho='{nicho}'")

    # Se ainda não temos nicho, infere pelo nome do produto
    if not nicho:
        # 1ª tentativa: Copy Adapter (mais rico)
        if _COPY_ADAPTER_DISPONIVEL:
            nicho = _inferir_nicho_via_copy(produto, plano) or ""
        # 2ª tentativa: fallback interno por keyword (independe do Copy Adapter)
        if not nicho:
            nicho = _inferir_nicho_interno(produto)
        if nicho:
            origem = "plano ausente" if not plano else "plano sem nicho"
            log.info(f"   📋 Nicho inferido pelo nome ({origem}): '{nicho}'")
        else:
            log.warning(f"   ⚠️  Nicho não inferido — usará queries fallback genéricas")

    # Verifica áudio atual
    status_inicial = verificar_audio_produto(produto)
    log.info(f"   📊 Áudio inicial: {status_inicial['total']} arquivo(s)")

    resultado = {
        "produto":               produto,
        "slug":                  slug,
        "nicho":                 nicho,
        "audio_inicial":         status_inicial["total"],
        "queries_planejadas":    [],
        "downloads_resumo":      [],
        "hunter_executado":      False,
        "audio_final":           0,
        "audio_escolhido":       None,
        "audio_score":           0,
        "audio_status":          "sem_audio",
        "audio_autopilot_usado": False,
    }

    queries = sugerir_queries(produto, nicho, query_custom)
    resultado["queries_planejadas"] = queries
    log.info(f"   🔍 Queries ({len(queries)}): {queries[:3]}{'...' if len(queries) > 3 else ''}")

    # ── Skip se já tem áudio ──
    if skip_se_tem_audio and status_inicial["tem_audio"]:
        log.info(f"\n⏭️  Produto JÁ tem {status_inicial['total']} áudio(s) — pulando coleta")
        log.info(f"   (use --forcar-coleta pra baixar mais)")
        log.info(f"\n📊 Selecionando melhor entre os existentes...")
        sel = executar_audio_selector(produto, nicho=nicho)
        resultado.update({
            "audio_final":     status_inicial["total"],
            "audio_escolhido": sel.get("melhor_audio"),
            "audio_score":     sel.get("score", 0),
            "audio_status":    _classificar_status(sel.get("score", 0)),
        })
        _logar_escolha(sel)
        return resultado

    # ── Dry-run ──
    if dry_run:
        log.info(f"\n🔍 [DRY-RUN] Tentaria essas {min(len(queries), MAX_QUERIES_POR_RUN)} primeiras queries no Freesound:")
        for i, q in enumerate(queries[:MAX_QUERIES_POR_RUN], 1):
            log.info(f"      {i}. '{q}'")
        if len(queries) > MAX_QUERIES_POR_RUN:
            log.info(f"      ... ({len(queries) - MAX_QUERIES_POR_RUN} extra(s) ficariam de reserva)")
        resultado["audio_status"] = "dry_run"
        return resultado

    # ── COLETA REAL ──
    log.info(f"\n────────────────────────────────────────────────────────────")
    log.info(f"📦 COLETA DE ÁUDIO (Freesound)")
    log.info(f"────────────────────────────────────────────────────────────")

    total_baixados = 0
    queries_que_funcionaram = []
    for i, query in enumerate(queries[:MAX_QUERIES_POR_RUN], 1):
        log.info(f"\n[{i}/{min(MAX_QUERIES_POR_RUN, len(queries))}] Query: '{query}'")
        r_coll = executar_audio_collector(
            query=query,
            limite=max(5, max_downloads // 2),
        )
        resultado["downloads_resumo"].append({
            "query":    query,
            "sucesso":  r_coll["sucesso"],
            "baixados": r_coll.get("baixados_estimados", 0),
            "erro":     r_coll.get("stderr", "")[:200] if not r_coll["sucesso"] else "",
        })
        if r_coll["sucesso"]:
            n = r_coll.get("baixados_estimados", 0)
            total_baixados += n
            if n > 0:
                queries_que_funcionaram.append(query)
                log.info(f"   ✅ +{n} áudio(s) baixado(s)")
            else:
                log.info(f"   ⏭️  query rodou mas 0 baixados (sem resultados úteis)")
        else:
            log.warning(f"   ❌ Collector falhou: {r_coll.get('stderr', '?')[:80]}")
        if total_baixados >= max_downloads:
            log.info(f"   🛑 Atingiu max-downloads ({max_downloads}) — parando")
            break

    log.info(f"\n📊 Total baixado: ~{total_baixados} áudio(s) "
             f"de {len(queries_que_funcionaram)} query(s) bem-sucedida(s)")

    # ── HUNTER ──
    if total_baixados > 0:
        log.info(f"\n────────────────────────────────────────────────────────────")
        log.info(f"📦 MOVENDO ÁUDIO (Hunter)")
        log.info(f"────────────────────────────────────────────────────────────")
        r_hunter = executar_asset_hunter(produto)
        resultado["hunter_executado"] = True
        resultado["hunter_sucesso"]   = r_hunter.get("sucesso", False)
        if not r_hunter.get("sucesso"):
            log.warning(f"   ⚠️  Hunter falhou: {r_hunter.get('stderr', '?')[:120]}")

    # ── SELECTOR ──
    log.info(f"\n────────────────────────────────────────────────────────────")
    log.info(f"🎯 SELECIONANDO MELHOR ÁUDIO")
    log.info(f"────────────────────────────────────────────────────────────")

    status_pos = verificar_audio_produto(produto)
    log.info(f"   Total na pasta do produto: {status_pos['total']} áudio(s)")

    if status_pos["total"] == 0:
        log.warning(f"   ⚠️  Pasta de áudio vazia — Collector pode ter falhado")
        resultado["audio_status"] = "sem_audio"
        resultado["mensagem"] = "Collector não baixou nada utilizável"
        return resultado

    sel = executar_audio_selector(produto, nicho=nicho)
    resultado["audio_final"]           = status_pos["total"]
    resultado["audio_escolhido"]       = sel.get("melhor_audio")
    resultado["audio_score"]           = sel.get("score", 0)
    resultado["audio_status"]          = _classificar_status(sel.get("score", 0))
    resultado["audio_autopilot_usado"] = total_baixados > 0
    _logar_escolha(sel)

    log.info(f"\n{'═' * 60}")
    log.info(f"🏁 RESULTADO")
    log.info(f"   Áudio: {status_inicial['total']} → {status_pos['total']} arquivo(s)")
    log.info(f"   Escolhido: {sel.get('melhor_audio', '?')}")
    log.info(f"   Score: {sel.get('score', 0)}/100 ({resultado['audio_status']})")
    log.info(f"{'═' * 60}")

    return resultado


def _classificar_status(score: int) -> str:
    if score >= 70:
        return "bom"
    if score >= 50:
        return "aceitavel"
    if score > 0:
        return "ruim"
    return "sem_audio"


def _logar_escolha(sel: dict):
    if not sel.get("melhor_audio"):
        log.warning(f"   ⚠️  Selector não encontrou áudio utilizável")
        return
    log.info(f"   🎯 Melhor: {sel['melhor_audio']}")
    log.info(f"      Score: {sel.get('score', 0)}/100")
    for m in (sel.get("motivos") or [])[:5]:
        log.info(f"      • {m}")


# =================================================================
# RELATÓRIO + CLI
# =================================================================

def salvar_resultado(resultado: dict) -> Optional[str]:
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        path = PLANS_DIR / "audio_autopilot_resultado.json"
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
        description="Audio Autopilot — coleta + curadoria automática de áudio"
    )
    parser.add_argument("--produto", required=True,
                        help="Nome do produto (ou slug)")
    parser.add_argument("--max-downloads", type=int, default=10,
                        dest="max_downloads",
                        help="Máx áudios baixados nessa execução (default 10)")
    parser.add_argument("--query", default="", dest="query_custom",
                        help="Query custom (sobrescreve heurística)")
    parser.add_argument("--forcar-coleta", action="store_true",
                        dest="forcar_coleta",
                        help="Coleta mesmo se produto já tem áudio")
    parser.add_argument("--dry-run", action="store_true",
                        dest="dry_run",
                        help="Lista queries que tentaria sem baixar")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info(f"🎵 AUDIO AUTOPILOT v1")
    log.info("=" * 60)

    r = autopilot_audio(
        produto=args.produto,
        max_downloads=args.max_downloads,
        query_custom=args.query_custom,
        skip_se_tem_audio=not args.forcar_coleta,
        dry_run=args.dry_run,
    )

    salvar_resultado(r)

    if r.get("audio_status") in ("bom", "aceitavel"):
        return 0
    if r.get("audio_status") == "dry_run":
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())