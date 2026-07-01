# agents/audio_selector_agent.py
# Audio Selector Agent v1 do AgenteIA (Jarvis).
#
# Resolve o problema do "editor pega o áudio em ordem alfabética" → muitas
# vezes lewes_band_drums (banda marchando) vence Hip_Hop_Drum_Loop. Esse
# agente analisa a pasta de áudio de um produto e escolhe a MELHOR trilha
# pra estilo TikTok/vídeo de afiliado, baseado em:
#
#   1. Heurística por nome (sempre disponível)
#      - termos positivos: lofi, chill, electronic, beat, hip hop, etc
#      - termos negativos: band, marching, voice, nature, etc
#      - duração ideal: 15-45s
#      - BPM no nome (sinaliza músico sério)
#
#   2. Análise espectral via librosa (opcional, se instalado)
#      - BPM real detectado
#      - energia média (RMS)
#      - "vibe" via spectral centroid (acústico vs eletrônico)
#
#   3. Memória (opcional, se Memory Agent disponível)
#      - boost se áudio foi usado antes em vídeo bem avaliado
#      - penalidade se foi usado em vídeo mal avaliado
#
# Filosofia:
#   - NUNCA chama Gemini
#   - NUNCA depende de API externa
#   - Funciona sem librosa (fallback gracioso pra heurística)
#   - Cache de análise em .audio_scores.json (invalida por mtime)
#   - Devolve TODOS os áudios com score — escolher 1 é responsabilidade do caller
#
# Uso direto (inspeção):
#   python -m agents.audio_selector_agent --produto "Mini Aspirador de Teclado"
#   python -m agents.audio_selector_agent --produto "X" --top 5 --explicar
#
# Uso programático (Editor):
#   from agents.audio_selector_agent import selecionar_melhor_audio
#   audio_path = selecionar_melhor_audio("Mini Aspirador de Teclado")
#   if audio_path:
#       # usa essa trilha no editor

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

from shared.logger import get_logger

from agents.asset_agent import slugificar_produto, ASSETS_ROOT as PRODUTOS_ROOT

log = get_logger(__name__)

# =================================================================
# CONFIGURAÇÃO
# =================================================================

PROJETO_ROOT = Path(__file__).parent.parent
PLANS_DIR    = PROJETO_ROOT / "shared" / "content_plans"

EXT_AUDIO = {".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac"}

# ── INTEGRAÇÃO COM MEMORY (Tier 3, opcional/best-effort) ──
try:
    from agents.memory_agent import (
        buscar_audios_aprovados,
        buscar_audios_reprovados,
    )
    _MEMORY_DISPONIVEL = True
except Exception:
    _MEMORY_DISPONIVEL = False

# Boost por memória (Tier 3)
BOOST_AUDIO_EXATO_APROVADO    = 25   # mesmo arquivo aprovado antes
BOOST_TAGS_APROVADAS_PARCIAL  = 12   # ≥2 tags em comum com aprovado
BOOST_TAGS_APROVADAS_MINIMO   = 5    # 1 tag em comum
PENALIDADE_AUDIO_REPROVADO    = -25
PENALIDADE_TAGS_REPROVADAS    = -10


def _boost_por_memoria(nome_arquivo: str, nicho: str = "") -> tuple[int, list[str]]:
    """
    Consulta Memory pra boost/penalidade baseada em avaliações passadas.

    Estratégia:
      1. Se NOME EXATO já foi aprovado: +25 (caso ideal)
      2. Tags em comum com aprovado: +5 a +15 proporcional
      3. Nome EXATO reprovado: -25
      4. Tags em comum com reprovado: -10

    Returns: (delta_score, lista_motivos). (0, []) se Memory indisponível.
    """
    if not _MEMORY_DISPONIVEL:
        return 0, []

    try:
        aprovados  = buscar_audios_aprovados(nicho=nicho, limite=20)
        reprovados = buscar_audios_reprovados(nicho=nicho, limite=20)
    except Exception as e:
        log.warning(f"   Memory falhou (best-effort): {e}")
        return 0, []

    if not aprovados and not reprovados:
        return 0, []

    delta = 0
    motivos = []

    # Tags do áudio atual (inferidas do nome — igual o memory faz)
    nome_lower = nome_arquivo.lower()
    tags_atual = set()
    for termo in ("hip_hop", "hip hop", "lofi", "lo_fi", "house", "trap", "edm",
                   "loop", "drum", "beat", "synth", "ambient", "chill",
                   "electronic", "industrial", "melody", "bass", "808",
                   "acoustic", "band", "marching", "voice", "piano"):
        if termo.replace("_", " ") in nome_lower.replace("_", " "):
            tags_atual.add(termo.replace(" ", "_"))

    # ── Match contra APROVADOS ──
    melhor_match_aprovado = 0
    motivo_aprovado = ""
    for ap in aprovados:
        if ap.get("audio_path", "").lower() == nome_arquivo.lower():
            # Match EXATO — boost máximo
            delta += BOOST_AUDIO_EXATO_APROVADO
            motivos.append(
                f"+{BOOST_AUDIO_EXATO_APROVADO} 🧠 áudio aprovado antes "
                f"(score humano {ap['score_humano']})"
            )
            melhor_match_aprovado = BOOST_AUDIO_EXATO_APROVADO
            break
        # Match por tags
        tags_ap = set(t.lower() for t in (ap.get("tags") or [])
                       if isinstance(t, str))
        # Filtra tags genéricas que não diferenciam (ex: "audio", "aprovado")
        tags_ap_filtradas = tags_ap - {"audio", "aprovado", "reprovado", "neutro"}
        tags_ap_filtradas = {t for t in tags_ap_filtradas if not t.startswith("nicho_")}
        overlap = tags_atual & tags_ap_filtradas
        if len(overlap) >= 2:
            boost = BOOST_TAGS_APROVADAS_PARCIAL
        elif len(overlap) == 1:
            boost = BOOST_TAGS_APROVADAS_MINIMO
        else:
            boost = 0
        if boost > melhor_match_aprovado:
            melhor_match_aprovado = boost
            motivo_aprovado = (
                f"+{boost} 🧠 tags similares a aprovado ({sorted(overlap)})"
            )

    if melhor_match_aprovado > 0 and not motivos:
        # Aplica boost de tags só se não houve match exato
        delta += melhor_match_aprovado
        motivos.append(motivo_aprovado)

    # ── Match contra REPROVADOS ──
    for rep in reprovados:
        if rep.get("audio_path", "").lower() == nome_arquivo.lower():
            delta += PENALIDADE_AUDIO_REPROVADO
            motivos.append(
                f"{PENALIDADE_AUDIO_REPROVADO} 🧠 áudio reprovado antes "
                f"(score humano {rep['score_humano']})"
            )
            break
        tags_rep = set(t.lower() for t in (rep.get("tags") or [])
                        if isinstance(t, str))
        tags_rep_filtradas = tags_rep - {"audio", "aprovado", "reprovado", "neutro"}
        tags_rep_filtradas = {t for t in tags_rep_filtradas if not t.startswith("nicho_")}
        overlap_rep = tags_atual & tags_rep_filtradas
        if len(overlap_rep) >= 2:
            delta += PENALIDADE_TAGS_REPROVADAS
            motivos.append(
                f"{PENALIDADE_TAGS_REPROVADAS} 🧠 tags similares a reprovado "
                f"({sorted(overlap_rep)})"
            )
            break  # uma penalidade só é suficiente

    return delta, motivos


# ── HEURÍSTICA POR NOME ──
# Termos que indicam trilha ADEQUADA pra TikTok (boost de score)
TERMOS_POSITIVOS = {
    # Estilo viral/moderno
    "lofi":         15,
    "lo-fi":        15,
    "chill":        12,
    "tiktok":       20,
    "viral":        15,
    "trap":         12,
    "hip hop":      12,
    "hiphop":       12,
    "hip_hop":      12,
    "electronic":   12,
    "synthwave":    14,
    "synth":         8,
    "house":        10,
    "edm":          12,
    "beat":          8,
    "groove":        8,
    "funky":         8,
    "upbeat":       12,
    "energetic":    10,
    "ambient":       6,   # pode servir pra background
    "background":   10,
    # Modern/tech
    "808":           6,
    "digital":       4,
    "bass":          4,
    # Sinaliza músico sério (BPM declarado = trilha estruturada)
    "bpm":           8,
    # Loops são geralmente trilhas, não SFX
    "loop":          8,
}

# Termos que indicam trilha INADEQUADA (penalidade forte)
TERMOS_NEGATIVOS = {
    # Acústico/orgânico (não combina com produto tech)
    "acoustic":      -15,
    "folk":          -12,
    "country":       -15,
    "band":          -20,   # banda real, não eletrônico
    "marching":      -25,
    "march":         -15,
    "orchestra":     -18,
    "orchestral":    -18,
    "classical":     -15,
    "violin":        -12,
    "cello":         -12,
    "acoustic guitar": -12,
    "piano":          -8,   # piano puro raramente combina com produto
    # Voz/fala
    "voice":         -20,
    "speech":        -25,
    "talking":       -25,
    "vocal":         -15,
    "singing":       -15,
    "chorus":        -10,
    "spoken":        -20,
    "narration":     -25,
    # SFX (efeitos sonoros, não trilhas)
    "bang":          -25,
    "crash":         -20,
    "hit":           -15,
    "slam":          -20,
    "door":          -20,
    "bell":          -15,
    "whistle":       -20,
    "siren":         -25,
    "alarm":         -20,
    "scream":        -30,
    # Natureza (raramente combina com produto)
    "nature":        -15,
    "bird":          -20,
    "water":         -10,
    "wind":          -10,
    "forest":        -15,
    "rain":          -10,
    "ocean":         -10,
    "thunder":       -20,
    # Específicos suspeitos
    "mexican":       -15,
    "church":        -20,
    "tribal":        -15,
    "lewes":         -20,   # band drums lewes (caso real do user!)
    "heartbeat":     -15,   # batimento cardíaco = SFX
    "heart_beat":    -15,
}

# Duração ideal pra TikTok (segundos)
DURACAO_IDEAL_MIN  = 15
DURACAO_IDEAL_MAX  = 45
DURACAO_ACEITAVEL_MAX = 90

# Threshold pra considerar "áudio bom" (score >= isso)
SCORE_BOM        = 50
SCORE_ACEITAVEL  = 25  # abaixo disso, alerta usuário

# Cache de scores
CACHE_FILENAME = ".audio_scores.json"


# =================================================================
# DETECTOR DE LIBROSA
# =================================================================

_LIBROSA_DISPONIVEL = None

def _librosa_disponivel() -> bool:
    """Checagem lazy + cached de se librosa está instalado."""
    global _LIBROSA_DISPONIVEL
    if _LIBROSA_DISPONIVEL is not None:
        return _LIBROSA_DISPONIVEL
    try:
        import librosa  # noqa: F401
        _LIBROSA_DISPONIVEL = True
    except ImportError:
        _LIBROSA_DISPONIVEL = False
    return _LIBROSA_DISPONIVEL


# =================================================================
# HEURÍSTICA POR NOME
# =================================================================

def _normalizar_nome(nome: str) -> str:
    """Lowercase + sem extensão + underscores como espaços."""
    s = Path(nome).stem.lower()
    s = re.sub(r"[_\-.]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _score_por_nome(nome: str) -> tuple[int, list[str]]:
    """
    Retorna (score, motivos) baseado em termos no nome do arquivo.
    Score começa em 40 (neutro), termos somam/subtraem.
    """
    nome_norm = _normalizar_nome(nome)
    score = 40  # neutro
    motivos = []

    for termo, peso in TERMOS_POSITIVOS.items():
        if termo in nome_norm:
            score += peso
            motivos.append(f"+{peso} '{termo}'")

    for termo, peso in TERMOS_NEGATIVOS.items():
        if termo in nome_norm:
            score += peso
            motivos.append(f"{peso} '{termo}'")

    return score, motivos


def _score_por_duracao(dur_seg: Optional[float]) -> tuple[int, str]:
    """Score baseado na duração. Retorna (delta, motivo)."""
    if dur_seg is None or dur_seg <= 0:
        return 0, "duração desconhecida"
    if DURACAO_IDEAL_MIN <= dur_seg <= DURACAO_IDEAL_MAX:
        return 15, f"duração ideal ({dur_seg:.1f}s)"
    if dur_seg < DURACAO_IDEAL_MIN and dur_seg >= 10:
        return -5, f"curto ({dur_seg:.1f}s)"
    if DURACAO_IDEAL_MAX < dur_seg <= DURACAO_ACEITAVEL_MAX:
        return -8, f"longo ({dur_seg:.1f}s — editor vai cortar)"
    if dur_seg < 10:
        return -20, f"muito curto ({dur_seg:.1f}s)"
    return -15, f"muito longo ({dur_seg:.1f}s)"


# =================================================================
# ANÁLISE ESPECTRAL (librosa, opcional)
# =================================================================

def _analisar_espectral(path: Path) -> Optional[dict]:
    """
    Análise via librosa (se disponível). Retorna dict com bpm, energia,
    centroid (vibe), ou None se falhar/indisponível.
    """
    if not _librosa_disponivel():
        return None
    try:
        import librosa
        import numpy as np

        # Carrega max 60s pra economizar tempo (TikTok não precisa mais)
        y, sr = librosa.load(str(path), sr=22050, mono=True, duration=60.0)
        if len(y) < sr:  # menos de 1s = lixo
            return None

        # BPM
        try:
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            bpm = float(tempo) if tempo else 0.0
        except Exception:
            bpm = 0.0

        # Energia média (RMS)
        try:
            rms = librosa.feature.rms(y=y)
            energia = float(np.mean(rms))
        except Exception:
            energia = 0.0

        # Spectral centroid — "brilho" do som
        # Eletrônico/sintético tem centroid alto (> 2500Hz)
        # Acústico/orgânico tem centroid baixo (< 1500Hz)
        try:
            centroids = librosa.feature.spectral_centroid(y=y, sr=sr)
            centroid_medio = float(np.mean(centroids))
        except Exception:
            centroid_medio = 0.0

        return {
            "bpm":       round(bpm, 1),
            "energia":   round(energia, 4),
            "centroid":  round(centroid_medio, 0),
        }
    except Exception as e:
        log.warning(f"Análise espectral falhou em {path.name}: {e}")
        return None


def _score_por_espectral(analise: dict) -> tuple[int, list[str]]:
    """Score baseado em features espectrais."""
    if not analise:
        return 0, []

    delta = 0
    motivos = []

    bpm = analise.get("bpm", 0)
    if 90 <= bpm <= 140:
        delta += 12
        motivos.append(f"+12 BPM {bpm:.0f} (faixa TikTok)")
    elif 70 <= bpm < 90 or 140 < bpm <= 160:
        delta += 6
        motivos.append(f"+6 BPM {bpm:.0f} (ok)")
    elif bpm > 0:
        delta -= 4
        motivos.append(f"-4 BPM {bpm:.0f} (fora da faixa)")

    # Energia: trilhas TikTok geralmente têm energia média-alta
    energia = analise.get("energia", 0)
    if energia >= 0.05:
        delta += 8
        motivos.append(f"+8 energia alta ({energia:.3f})")
    elif energia < 0.01:
        delta -= 10
        motivos.append(f"-10 energia muito baixa ({energia:.3f})")

    # Centroid: > 2500 = eletrônico, < 1500 = acústico orgânico
    centroid = analise.get("centroid", 0)
    if centroid >= 2500:
        delta += 8
        motivos.append(f"+8 brilho alto ({centroid:.0f}Hz, eletrônico)")
    elif centroid < 1500 and centroid > 0:
        delta -= 8
        motivos.append(f"-8 brilho baixo ({centroid:.0f}Hz, acústico)")

    return delta, motivos


# =================================================================
# UTILS: duração rápida (sem librosa)
# =================================================================

def _duracao_rapida(path: Path) -> Optional[float]:
    """
    Tenta ler duração sem carregar arquivo todo.
    Estratégia 1: mutagen (super leve, lê só header)
    Estratégia 2: ffprobe via subprocess
    Estratégia 3: tamanho heurístico (péssimo, mas não None)
    """
    # mutagen
    try:
        from mutagen import File as MutagenFile  # type: ignore
        f = MutagenFile(str(path))
        if f and f.info and f.info.length:
            return round(float(f.info.length), 2)
    except Exception:
        pass

    # ffprobe
    try:
        import subprocess
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return round(float(out.stdout.strip()), 2)
    except Exception:
        pass

    # Heurística: MP3 ~128kbps = 16KB/s, dá pra estimar grosso
    try:
        tam_bytes = path.stat().st_size
        if path.suffix.lower() in (".mp3",):
            return round(tam_bytes / 16000, 2)  # 128kbps ≈ 16KB/s
    except Exception:
        pass

    return None


# =================================================================
# CACHE
# =================================================================

def _ler_cache(pasta_audio: Path) -> dict:
    cache_path = pasta_audio / CACHE_FILENAME
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _salvar_cache(pasta_audio: Path, cache: dict):
    cache_path = pasta_audio / CACHE_FILENAME
    try:
        cache_path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning(f"Falha ao salvar cache: {e}")


def _entrada_cache_valida(entrada: dict, mtime: int) -> bool:
    """True se entrada do cache ainda é válida (mtime bate)."""
    return isinstance(entrada, dict) and entrada.get("mtime") == mtime


# =================================================================
# ANÁLISE DE UM ARQUIVO
# =================================================================

def analisar_audio(path: Path, usar_librosa: bool = True,
                    nicho: str = "") -> dict:
    """
    Analisa um arquivo de áudio e retorna dict com score + motivos.

    Args:
        path:         caminho do arquivo
        usar_librosa: se True e librosa disponível, faz análise espectral
        nicho:        se informado, consulta Memory pra boost/penalidade
                       por avaliações passadas no mesmo nicho

    Returns:
        {
            "arquivo":      str,
            "score":        int (0-100),
            "duracao":      float | None,
            "motivos":      [str, ...],
            "espectral":    dict | None,
            "mtime":        int,
        }
    """
    motivos_total = []

    # 1. Score por nome
    score_nome, motivos_nome = _score_por_nome(path.name)
    motivos_total.extend(motivos_nome)

    # 2. Duração
    dur = _duracao_rapida(path)
    delta_dur, motivo_dur = _score_por_duracao(dur)
    score_total = score_nome + delta_dur
    if motivo_dur:
        sinal = "+" if delta_dur >= 0 else ""
        motivos_total.append(f"{sinal}{delta_dur} {motivo_dur}")

    # 3. Análise espectral (se ativada e disponível)
    espectral = None
    if usar_librosa:
        espectral = _analisar_espectral(path)
        if espectral:
            delta_esp, motivos_esp = _score_por_espectral(espectral)
            score_total += delta_esp
            motivos_total.extend(motivos_esp)

    # 4. TIER 3: boost/penalidade por memória de avaliações passadas
    if nicho:
        delta_mem, motivos_mem = _boost_por_memoria(path.name, nicho=nicho)
        if delta_mem != 0:
            score_total += delta_mem
            motivos_total.extend(motivos_mem)

    # Clamp 0-100
    score_total = max(0, min(100, score_total))

    try:
        mtime = int(path.stat().st_mtime)
    except Exception:
        mtime = 0

    return {
        "arquivo":   path.name,
        "score":     score_total,
        "duracao":   dur,
        "motivos":   motivos_total,
        "espectral": espectral,
        "mtime":     mtime,
    }


# =================================================================
# API PÚBLICA: rankear pasta inteira
# =================================================================

def rankear_audios_do_produto(produto: str,
                                usar_librosa: bool = True,
                                usar_cache: bool = True,
                                nicho: str = "") -> dict:
    """
    Rankeia todos os áudios da pasta do produto.

    Args:
        produto:      nome do produto
        usar_librosa: análise espectral se disponível
        usar_cache:   usa cache em .audio_scores.json (invalida por mtime)
        nicho:        opcional — se informado, ativa Tier 3 (boost por memória)

    Returns: dict com analises ordenadas por score desc.
    """
    slug = slugificar_produto(produto)
    pasta = PRODUTOS_ROOT / slug / "audio"

    if not pasta.exists():
        return {
            "sucesso":  False,
            "produto":  produto,
            "slug":     slug,
            "pasta":    str(pasta),
            "total":    0,
            "analises": [],
            "melhor":   None,
            "mensagem": "Pasta de áudio não existe",
        }

    arquivos = sorted([
        p for p in pasta.iterdir()
        if p.is_file() and p.suffix.lower() in EXT_AUDIO and not p.name.startswith(".")
    ])

    if not arquivos:
        return {
            "sucesso":  True,
            "produto":  produto,
            "slug":     slug,
            "pasta":    str(pasta),
            "total":    0,
            "analises": [],
            "melhor":   None,
            "mensagem": "Pasta vazia",
        }

    cache = _ler_cache(pasta) if usar_cache else {}
    librosa_ok = usar_librosa and _librosa_disponivel()
    memory_ok = bool(nicho) and _MEMORY_DISPONIVEL

    log.info(f"🎵 Analisando {len(arquivos)} áudio(s) "
             f"(librosa: {'sim' if librosa_ok else 'não'}, "
             f"memory: {'sim (' + nicho + ')' if memory_ok else 'não'}, "
             f"cache: {len(cache)} entrada(s))")

    analises = []
    cache_novo = {}
    inicio = time.time()

    for i, arquivo in enumerate(arquivos, 1):
        try:
            mtime = int(arquivo.stat().st_mtime)
        except Exception:
            mtime = 0

        # Cache: válido se mtime bate E mesmo nicho usado na análise anterior
        cached = cache.get(arquivo.name)
        cache_hit = (
            usar_cache
            and _entrada_cache_valida(cached, mtime)
            and cached.get("_nicho_cache", "") == nicho  # invalida se nicho mudou
        )
        if cache_hit:
            analises.append(cached)
            cache_novo[arquivo.name] = cached
            continue

        # Análise fresca
        if librosa_ok or memory_ok:
            log.info(f"   [{i}/{len(arquivos)}] analisando {arquivo.name}...")
        analise = analisar_audio(arquivo, usar_librosa=librosa_ok, nicho=nicho)
        # Marca qual nicho foi usado (pra invalidação correta do cache)
        analise["_nicho_cache"] = nicho
        analises.append(analise)
        cache_novo[arquivo.name] = analise

    # Salva cache atualizado
    if usar_cache and cache_novo != cache:
        _salvar_cache(pasta, cache_novo)

    # Ordena por score desc
    analises.sort(key=lambda x: x.get("score", 0), reverse=True)
    melhor = analises[0] if analises else None

    duracao = round(time.time() - inicio, 2)
    log.info(f"   Concluído em {duracao}s — melhor: {melhor['arquivo'] if melhor else '—'} "
             f"(score {melhor['score'] if melhor else '?'})")

    return {
        "sucesso":        True,
        "produto":        produto,
        "slug":           slug,
        "pasta":          str(pasta),
        "total":          len(analises),
        "analises":       analises,
        "melhor":         melhor,
        "librosa_usado":  librosa_ok,
        "duracao_seg":    duracao,
        "timestamp":      time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def selecionar_melhor_audio(produto: str,
                              score_minimo: int = SCORE_ACEITAVEL,
                              usar_librosa: bool = True,
                              nicho: str = "") -> Optional[Path]:
    """
    Função simples pro Editor usar. Retorna Path do MELHOR áudio
    (ou None se nenhum disponível ou todos abaixo do score mínimo).

    Args:
        produto:      nome do produto
        score_minimo: se melhor for < isso, retorna None
        usar_librosa: se False, só heurística por nome
        nicho:        se informado, ativa boost por memória (Tier 3)
    """
    r = rankear_audios_do_produto(produto, usar_librosa=usar_librosa, nicho=nicho)
    melhor = r.get("melhor")
    if not melhor:
        return None
    if melhor.get("score", 0) < score_minimo:
        log.warning(f"⚠️  Melhor áudio tem score {melhor['score']} < mínimo {score_minimo} — "
                    f"retornando None (Editor vai render sem áudio)")
        return None
    slug = r["slug"]
    return PRODUTOS_ROOT / slug / "audio" / melhor["arquivo"]


# =================================================================
# RELATÓRIO + CLI
# =================================================================

def salvar_resultado(resultado: dict) -> Optional[str]:
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        path = PLANS_DIR / "audio_selector_resultado.json"
        path.write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return str(path)
    except Exception as e:
        log.warning(f"Falha ao salvar: {e}")
        return None


def imprimir_relatorio(r: dict, top: int = 5, explicar: bool = False):
    print("\n" + "=" * 70)
    print(f"  🎵 AUDIO SELECTOR — '{r['produto']}'")
    print("=" * 70)
    print(f"  Pasta:         {r['pasta']}")
    print(f"  Total áudios:  {r['total']}")
    print(f"  Librosa:       {'✅ usado' if r.get('librosa_usado') else '❌ não disponível (só heurística)'}")
    print(f"  Duração:       {r.get('duracao_seg', '?')}s")

    if not r.get("sucesso"):
        print(f"\n  ❌ {r.get('mensagem', 'Falha')}")
        return

    if r["total"] == 0:
        print(f"\n  ⚠️  Nenhum áudio na pasta")
        return

    analises = r["analises"][:top]
    print(f"\n  🏆 Top {len(analises)}:")
    for i, a in enumerate(analises, 1):
        score = a.get("score", 0)
        if score >= SCORE_BOM:
            marca = "🟢"
        elif score >= SCORE_ACEITAVEL:
            marca = "🟡"
        else:
            marca = "🔴"
        dur = a.get("duracao")
        dur_str = f"{dur:.1f}s" if dur else "?s"
        nome = a["arquivo"][:55]
        print(f"     {i:2d}. {marca} [{score:3d}] {nome:55s} ({dur_str})")
        if explicar and a.get("motivos"):
            for m in a["motivos"][:6]:
                print(f"             → {m}")
            esp = a.get("espectral")
            if esp:
                print(f"             → espectral: BPM={esp.get('bpm', '?')}, "
                      f"energia={esp.get('energia', '?')}, "
                      f"brilho={esp.get('centroid', '?')}Hz")

    melhor = r.get("melhor")
    if melhor:
        score = melhor["score"]
        print(f"\n  🎯 Escolha automática: {melhor['arquivo']}")
        if score >= SCORE_BOM:
            print(f"     Score {score}/100 — 🟢 BOM (use sem hesitar)")
        elif score >= SCORE_ACEITAVEL:
            print(f"     Score {score}/100 — 🟡 ACEITÁVEL (tente melhorar buscando mais áudios)")
        else:
            print(f"     Score {score}/100 — 🔴 RUIM (recomendo render sem áudio)")

    print(f"\n  💾 Detalhes em: shared/content_plans/audio_selector_resultado.json")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Audio Selector — escolhe melhor áudio pra vídeo de produto"
    )
    parser.add_argument("--produto", default="Mini Aspirador de Teclado",
                        help="Nome do produto pra analisar")
    parser.add_argument("--nicho", default="",
                        help="Nicho do produto (ativa boost por memória)")
    parser.add_argument("--top", type=int, default=5,
                        help="Quantos áudios mostrar no ranking (default: 5)")
    parser.add_argument("--explicar", action="store_true",
                        help="Mostra motivos do score de cada áudio")
    parser.add_argument("--no-librosa", action="store_true",
                        help="Desativa análise espectral (só heurística por nome)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Re-analisa tudo, ignora cache")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info(f"🎵 AUDIO SELECTOR — '{args.produto}'")
    log.info("=" * 60)

    r = rankear_audios_do_produto(
        produto=args.produto,
        usar_librosa=not args.no_librosa,
        usar_cache=not args.no_cache,
        nicho=args.nicho,
    )

    salvar_resultado(r)
    imprimir_relatorio(r, top=args.top, explicar=args.explicar)

    if not r.get("sucesso"):
        return 2
    if r["total"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())