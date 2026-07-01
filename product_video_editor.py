# creative_engine/product_video_editor.py
# Product Video Editor v1 do AgenteIA (Jarvis).
#
# Diferença do product_video_renderer:
#   - Renderer: "junta clipes brutos" → vídeo técnico, sem estilo
#   - Editor:   "estilo CapCut" → punch-in, texto por cena, CTA sintético,
#               cortes agressivos, pronto pra postar
#
# Pipeline:
#   [dor 1.8-2.5s + zoom + texto] →
#   [demo 3-5s + zoom + texto] →
#   [resultado 2-3s + zoom + texto] →
#   [close 1.5-2.5s + zoom + texto] →
#   [cta 1.5-2s + zoom + texto OU cta sintético (frame congelado)]
#
# Total alvo: 12-18s, 9:16 (1080x1920), 30fps, libx264 + yuv420p.
#
# Filosofia:
#   - Reusa helpers do product_video_renderer (sem duplicar código)
#   - Nunca chama Gemini, abre TikTok, posta
#   - Nunca crasha por áudio inválido (detector de header antes do MoviePy)
#   - Compatível MoviePy 1.x e 2.x (helpers compat do renderer)
#
# Uso direto:
#   python -m creative_engine.product_video_editor
#   python -m creative_engine.product_video_editor \
#       --produto "Mini Aspirador de Teclado" \
#       --hook "Seu teclado tá assim? 😳" \
#       --cta "Link na bio 🚀"
#
# Uso programático:
#   from creative_engine.product_video_editor import editar_video_produto_capcut_style
#   r = editar_video_produto_capcut_style(
#           produto="Mini Aspirador de Teclado",
#           plano={"hook": "...", "cta": "...",
#                  "textos_por_cena": {"dor": "...", "demo": "..."},
#                  "estilo": "viral_produto", "duracao_alvo": 15},
#       )

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

from agents.audio_selector_agent import selecionar_melhor_audio
from shared.logger import get_logger

# Copy Adapter: textos por categoria de produto (best-effort)
# Resolve bug de generalização (Cinto Modelador recebendo texto do Mini Aspirador).
try:
    from creative_engine.copy_adapter import (
        escolher_copy_por_cena,
        descrever_decisao as _descrever_decisao_copy,
    )
    _COPY_ADAPTER_OK = True
except Exception as _e_copy:
    _COPY_ADAPTER_OK = False
    _MOTIVO_COPY_FALHA = str(_e_copy)

# Asset Agent (verificação + slug)
from agents.asset_agent import (
    slugificar_produto,
    verificar_assets_produto,
    ASSETS_ROOT as PRODUTOS_ROOT,
)

# Memory Agent — consulta antes + registra depois (best-effort, não bloqueia)
try:
    from agents.memory_agent import (
        gerar_recomendacoes_edicao,
        registrar_aprendizado_execucao,
    )
    _MEMORY_DISPONIVEL = True
except Exception as _e_mem:
    _MEMORY_DISPONIVEL = False
    _MOTIVO_MEMORIA = str(_e_mem)

# Helpers compat do renderer — REUSO, sem duplicar
from creative_engine.product_video_renderer import (
    _import_moviepy,
    _is_moviepy_v2,
    _subclip,
    _set_audio,
    _crop_clip,
    _resize_clip,
    _audio_fadein,
    _audio_fadeout,
    _checar_dependencias,
    _ler_propositos_do_metadata,
    _selecionar_clipes_por_proposito,
    _selecionar_audio,
    _tentar_abrir_clipe,
    _ajustar_para_vertical,
    _adicionar_texto_overlay,
)

log = get_logger(__name__)

# =================================================================
# CONFIGURAÇÃO — estilo CapCut TikTok
# =================================================================

PROJETO_ROOT = Path(__file__).parent.parent
VIDEOS_DIR   = PROJETO_ROOT / "videos"

LARGURA_ALVO  = 1080
ALTURA_ALVO   = 1920
FPS_ALVO      = 30
AR_ALVO       = LARGURA_ALVO / ALTURA_ALVO

# Presets de estilo
PRESETS = {
    "viral_produto": {
        # Duração alvo de cada cena: (mínimo, máximo) — mais agressivo que renderer
        "duracoes": {
            "dor":       2.2,  # 1.8 a 2.5
            "demo":      4.0,  # 3 a 5
            "resultado": 2.5,  # 2 a 3
            "close":     2.0,  # 1.5 a 2.5
            "cta":       1.8,  # 1.5 a 2
        },
        "zoom_inicio":      1.00,
        "zoom_fim":         1.06,    # punch-in suave 6%
        "crossfade_seg":    0.15,    # punchy
        "fade_audio_seg":   0.4,
        "fonte_tamanho":    90,
        "cta_sintetico_dur": 1.5,
    },
    # Preset mais agressivo — ativado por memória quando avaliações anteriores
    # mencionam "cortes mais agressivos", "ritmo", "hook mais forte"
    "viral_produto_agressivo": {
        "duracoes": {
            "dor":       1.7,
            "demo":      3.0,
            "resultado": 2.0,
            "close":     1.5,
            "cta":       1.5,
        },
        "zoom_inicio":      1.00,
        "zoom_fim":         1.10,   # punch-in mais forte (10%)
        "crossfade_seg":    0.08,   # cortes secos
        "fade_audio_seg":   0.3,
        "fonte_tamanho":    96,
        "cta_sintetico_dur": 1.4,
    },
    # Preset balanceado — meio termo entre normal e agressivo.
    # Ativado por memória quando recomendações pedem ritmo mais punchy
    # MAS sem cortar tão curto que o vídeo fique abaixo de 10s.
    "viral_produto_agressivo_balanceado": {
        "duracoes": {
            "dor":       2.0,
            "demo":      4.0,
            "resultado": 2.5,
            "close":     1.8,
            "cta":       2.0,
        },
        "zoom_inicio":      1.00,
        "zoom_fim":         1.08,
        "crossfade_seg":    0.10,
        "fade_audio_seg":   0.3,
        "fonte_tamanho":    94,
        "cta_sintetico_dur": 2.0,
    },
}

DURACAO_ALVO_MIN  = 12.0   # legado — mantido pra compat
DURACAO_ALVO_MAX  = 18.0   # legado — mantido pra compat

# Limites granulares de duração (TikTok)
DURACAO_POSTAVEL_MIN = 10.0   # < isso = vídeo ruim, penaliza score
DURACAO_IDEAL_MIN    = 12.0   # zona ótima
DURACAO_IDEAL_MAX    = 18.0
DURACAO_LIMITE_MAX   = 22.0   # > isso = perde retenção

# Extensão automática quando preset agressivo cai abaixo do mínimo
DEMO_BOOST_SEG          = 1.0   # +1s na demo
CTA_SINTETICO_BOOST_SEG = 2.2   # CTA sintético se estende pra 2.2s
BENEFICIO_DUR_SEG       = 2.0   # cena beneficio sintética
BENEFICIO_TEXTO_DEFAULT = "Pequeno, prático e salva seu setup ✨"

ORDEM_CENAS = ["dor", "demo", "resultado", "close", "cta"]

# Texto padrão por cena (usado se plano["textos_por_cena"] não tiver)
TEXTOS_PADRAO = {
    "dor":       "Seu teclado tá assim? 😳",
    "demo":      "Olha isso limpando...",
    "resultado": "Resultado em segundos ✨",
    "close":     "Mini, portátil e prático",
    "cta":       "Link na bio 🚀",
}

CTA_SINTETICO_TEXTO = "Quer o link? Tá na bio 👇"

# Termos que indicam "use preset mais agressivo" nas recomendações
TERMOS_AGRESSIVO = (
    "agressiv",         # "agressivo" / "agressivos"
    "cortes mais curt",
    "ritmo mais",
    "hook mais",
    "viral_produto_agressivo",
    "mais rápid",
    "mais punch",
)

# Termos que indicam "memória sente falta de áudio"
TERMOS_FALTA_AUDIO = (
    "sem áudio", "sem audio",
    "trilha real", "usar trilha", "adicionar áudio", "adicionar audio",
    "falta áudio", "falta audio",
)


def _consultar_memoria_para_edicao(produto: str, nicho: str) -> dict:
    """
    Consulta o Memory Agent (best-effort). Nunca crasha — retorna dict vazio
    se memória indisponível ou falhou.
    """
    if not _MEMORY_DISPONIVEL:
        log.info(f"🧠 Memory Agent indisponível ({_MOTIVO_MEMORIA[:80]}) — seguindo sem memória")
        return {}
    try:
        ctx = gerar_recomendacoes_edicao(produto=produto, nicho=nicho or "")
        return ctx or {}
    except Exception as e:
        log.warning(f"🧠 Falha ao consultar memória: {e} — seguindo sem")
        return {}


def _detectar_preset_por_memoria(recomendacoes: list[str]) -> Optional[str]:
    """
    Analisa recomendações da memória. Se ≥2 termos "agressivos" aparecem,
    sugere viral_produto_agressivo_BALANCEADO (não o puro — evita vídeos
    curtos demais que aprendemos serem ruins).
    """
    if not recomendacoes:
        return None
    blob = " ".join(recomendacoes).lower()
    hits = sum(1 for termo in TERMOS_AGRESSIVO if termo in blob)
    if hits >= 2:
        return "viral_produto_agressivo_balanceado"
    return None


def _memoria_pede_audio(recomendacoes: list[str]) -> bool:
    """True se memória menciona explicitamente falta de áudio / trilha."""
    if not recomendacoes:
        return False
    blob = " ".join(recomendacoes).lower()
    return any(termo in blob for termo in TERMOS_FALTA_AUDIO)


def _registrar_aprendizado_seguro(etapa: str, resultado: dict, resumo: str,
                                   tags: Optional[list[str]] = None):
    """Wrapper que NUNCA crasha o editor — só loga warning se falhar."""
    if not _MEMORY_DISPONIVEL:
        return
    try:
        registrar_aprendizado_execucao(
            etapa=etapa, resultado=resultado, resumo=resumo, tags=tags or [],
        )
        log.info(f"🧠 Aprendizado registrado na memória (tags={tags})")
    except Exception as e:
        log.warning(f"🧠 Falha ao registrar aprendizado: {e}")


def _estimar_duracao_total(preset: dict, propositos_disponiveis: set[str],
                            crossfade_seg: float) -> tuple[float, bool]:
    """
    Estima a duração total ANTES de abrir clipes — pra decidir se precisa
    inflar o preset preventivamente.

    Returns:
        (duracao_estimada, vai_precisar_cta_sintetico)
    """
    duracoes = preset["duracoes"]
    soma = 0.0
    n_cenas = 0
    for prop in ORDEM_CENAS:
        if prop in propositos_disponiveis:
            soma += duracoes.get(prop, 2.0)
            n_cenas += 1

    # Se falta cta, vai adicionar sintético
    precisa_cta_sintetico = "cta" not in propositos_disponiveis
    if precisa_cta_sintetico:
        soma += preset.get("cta_sintetico_dur", 1.5)
        n_cenas += 1

    # Crossfade negativo subtrai do total
    if n_cenas > 1:
        soma -= crossfade_seg * (n_cenas - 1)

    return max(0.0, soma), precisa_cta_sintetico


def _inflar_preset_pra_chegar_no_minimo(preset: dict,
                                          propositos_disponiveis: set[str],
                                          duracao_alvo_min: float) -> tuple[dict, list[str]]:
    """
    Se duração estimada < duracao_alvo_min, ESTENDE o preset:
      1. Boost na demo (+ DEMO_BOOST_SEG)
      2. Boost no CTA sintético (CTA_SINTETICO_BOOST_SEG)
      3. Adiciona "beneficio" via flag (cena sintética será criada depois)

    Returns:
        (preset_modificado, lista_de_ajustes_aplicados)
    """
    crossfade = preset.get("crossfade_seg", 0.15)
    dur_est, precisa_cta_sint = _estimar_duracao_total(
        preset, propositos_disponiveis, crossfade
    )
    if dur_est >= duracao_alvo_min:
        return preset, []   # nada a fazer

    preset_novo = json.loads(json.dumps(preset))  # deep copy seguro
    ajustes = []

    # Tentativa 1: estender demo (se disponível)
    if "demo" in propositos_disponiveis:
        preset_novo["duracoes"]["demo"] += DEMO_BOOST_SEG
        ajustes.append(f"+{DEMO_BOOST_SEG}s na demo")
        dur_est, _ = _estimar_duracao_total(preset_novo, propositos_disponiveis, crossfade)
        if dur_est >= duracao_alvo_min:
            return preset_novo, ajustes

    # Tentativa 2: estender CTA sintético
    if precisa_cta_sint:
        preset_novo["cta_sintetico_dur"] = max(
            preset_novo.get("cta_sintetico_dur", 1.5),
            CTA_SINTETICO_BOOST_SEG,
        )
        ajustes.append(f"CTA sintético → {CTA_SINTETICO_BOOST_SEG}s")
        dur_est, _ = _estimar_duracao_total(preset_novo, propositos_disponiveis, crossfade)
        if dur_est >= duracao_alvo_min:
            return preset_novo, ajustes

    # Tentativa 3: marca pra adicionar cena beneficio
    preset_novo["_adicionar_beneficio"] = True
    ajustes.append(f"cena 'beneficio' sintética ({BENEFICIO_DUR_SEG}s)")
    return preset_novo, ajustes


def _criar_cena_beneficio(ultimo_clipe, duracao: float, texto: str):
    """
    Cria cena sintética 'beneficio' — frame congelado do melhor clipe
    (passado como ultimo_clipe) + texto destacado.

    Usa a mesma lógica do _criar_cta_sintetico mas com texto diferente.
    """
    try:
        _, _, ImageClip, _, _ = _import_moviepy()
    except Exception as e:
        return None, f"moviepy indisponível: {e}"

    try:
        t_frame = max(0.0, float(ultimo_clipe.duration or 0.1) - 0.1)
        if hasattr(ultimo_clipe, "to_ImageClip"):
            frame_clip = ultimo_clipe.to_ImageClip(t=t_frame)
        else:
            import numpy as np  # noqa: F401
            frame_array = ultimo_clipe.get_frame(t_frame)
            try:
                frame_clip = ImageClip(frame_array, duration=duracao)
            except TypeError:
                frame_clip = ImageClip(frame_array)

        if hasattr(frame_clip, "with_duration"):
            frame_clip = frame_clip.with_duration(duracao)
        elif hasattr(frame_clip, "set_duration"):
            frame_clip = frame_clip.set_duration(duracao)

        frame_clip = _ajustar_para_vertical(frame_clip)
        frame_clip = _adicionar_texto_overlay(frame_clip, texto, posicao="center")

        return frame_clip, None
    except Exception as e:
        return None, f"erro ao criar cena beneficio: {str(e)[:140]}"


# Áudio: tamanho mínimo + assinaturas de header válidas
AUDIO_MIN_BYTES = 10 * 1024  # 10 KB — abaixo disso, é fake
ASSINATURAS_AUDIO = [
    b"ID3",            # MP3 com tag ID3v2
    b"\xff\xfb",       # MP3 frame MPEG Layer 3
    b"\xff\xfa",       # MP3 frame
    b"\xff\xf3",       # MP3 frame
    b"\xff\xf2",       # MP3 frame
    b"RIFF",           # WAV
    b"OggS",           # OGG
    b"fLaC",           # FLAC
    b"ftyp",           # M4A (aparece no offset 4, mas vamos checar nos primeiros 12 bytes)
]


# =================================================================
# DETECTOR DE ÁUDIO VÁLIDO (evita traceback feio do MoviePy)
# =================================================================

def _audio_eh_valido(path: Path) -> tuple[bool, str]:
    """
    Confere se o arquivo de áudio é REAL (não é fake do seed nem corrompido).
    Verifica tamanho mínimo + assinatura de header conhecida.

    Returns: (válido, motivo)
        - True, "ok"
        - False, "muito pequeno (X bytes)"
        - False, "header não reconhecido"
        - False, "arquivo não existe"
    """
    try:
        if not path.exists():
            return False, "arquivo não existe"
        tam = path.stat().st_size
        if tam < AUDIO_MIN_BYTES:
            return False, f"muito pequeno ({tam} bytes < {AUDIO_MIN_BYTES})"

        with open(path, "rb") as f:
            head = f.read(12)

        # Se for tudo zeros (fake do seed) — rejeita rápido
        if all(b == 0 for b in head):
            return False, "header só com zeros (provável fake do --seed)"

        for assinatura in ASSINATURAS_AUDIO:
            # 'ftyp' aparece a partir do byte 4 em arquivos M4A/MP4
            if assinatura == b"ftyp":
                if b"ftyp" in head:
                    return True, "ok"
                continue
            if head.startswith(assinatura):
                return True, "ok"

        return False, f"header não reconhecido (primeiros bytes: {head[:4].hex()})"
    except Exception as e:
        return False, f"erro ao ler: {e}"


# =================================================================
# ZOOM PUNCH-IN (compat v1/v2)
# =================================================================

def _aplicar_punch_in(clip, zoom_inicio: float, zoom_fim: float):
    """
    Aplica zoom dinâmico crescente ao longo da duração do clipe.
    Em t=0: zoom_inicio (ex: 1.00). Em t=dur: zoom_fim (ex: 1.06).

    Compat:
      - MoviePy 2.x: clip.resized(lambda t: ...)
      - MoviePy 1.x: resize(clip, lambda t: ...)

    Mantém posição central (with_position se disponível) pra não escalar
    pro canto. Falha silenciosa → retorna clip original sem punch-in.
    """
    try:
        dur = float(clip.duration or 0)
        if dur <= 0 or zoom_fim <= zoom_inicio:
            return clip

        def zoom_func(t):
            # Linear: começa em zoom_inicio, termina em zoom_fim
            frac = min(max(t / dur, 0.0), 1.0)
            return zoom_inicio + (zoom_fim - zoom_inicio) * frac

        # Tenta v2 primeiro
        if hasattr(clip, "resized"):
            try:
                zoomed = clip.resized(zoom_func)
                # Mantém central
                if hasattr(zoomed, "with_position"):
                    zoomed = zoomed.with_position("center")
                return zoomed
            except Exception:
                pass

        # Fallback v1
        try:
            from moviepy.video.fx.resize import resize  # type: ignore
            zoomed = resize(clip, zoom_func)
            if hasattr(zoomed, "set_position"):
                zoomed = zoomed.set_position("center")
            return zoomed
        except Exception:
            pass

        return clip  # sem punch-in, mas não quebra
    except Exception as e:
        log.warning(f"   ⚠️  punch-in falhou: {e} — clip sem zoom")
        return clip


# =================================================================
# CTA SINTÉTICO (frame congelado do último clipe)
# =================================================================

def _criar_cta_sintetico(ultimo_clipe, duracao: float, texto: str):
    """
    Cria uma cena CTA artificial: congela o último frame do último clipe
    e segura por `duracao` segundos com `texto` em destaque.

    Retorna (cta_clip, erro):
        - sucesso: (clip novo, None)
        - falha:   (None, motivo)
    """
    try:
        _, _, ImageClip, _, _ = _import_moviepy()
    except Exception as e:
        return None, f"moviepy indisponível: {e}"

    try:
        # Pega frame quase no final (evita problemas se duration é exata)
        t_frame = max(0.0, float(ultimo_clipe.duration or 0.1) - 0.1)

        # Estratégia 1: usar to_ImageClip se disponível (mais limpo)
        if hasattr(ultimo_clipe, "to_ImageClip"):
            frame_clip = ultimo_clipe.to_ImageClip(t=t_frame)
        else:
            # Estratégia 2: get_frame + ImageClip
            import numpy as np  # noqa: F401
            frame_array = ultimo_clipe.get_frame(t_frame)
            try:
                frame_clip = ImageClip(frame_array, duration=duracao)
            except TypeError:
                # v2 não aceita duration no construtor
                frame_clip = ImageClip(frame_array)

        # Aplica duração (compat v1/v2)
        if hasattr(frame_clip, "with_duration"):
            frame_clip = frame_clip.with_duration(duracao)
        elif hasattr(frame_clip, "set_duration"):
            frame_clip = frame_clip.set_duration(duracao)

        # Ajusta pra 9:16 (frame pode ter outras dimensões)
        frame_clip = _ajustar_para_vertical(frame_clip)

        # Sobrepõe texto centro grande
        frame_clip = _adicionar_texto_overlay(frame_clip, texto, posicao="center")

        return frame_clip, None
    except Exception as e:
        return None, f"erro ao criar CTA sintético: {str(e)[:140]}"


# =================================================================
# PIPELINE PRINCIPAL DE EDIÇÃO
# =================================================================

def editar_video_produto_capcut_style(
    produto: str,
    plano: Optional[dict] = None,
    output_path: Optional[str] = None,
) -> dict:
    """
    Edita vídeo de produto estilo CapCut/TikTok pronto pra postar.

    Args:
        produto:     nome do produto (será slugificado)
        plano:       dict opcional com:
            - hook:           texto pro primeiro clipe (sobrescreve cena 'dor')
            - cta:            texto pra cena CTA (real ou sintética)
            - textos_por_cena: dict {cena_id: texto} — sobrescreve TEXTOS_PADRAO
            - estilo:         "viral_produto" (default)
            - duracao_alvo:   alvo em segundos (12-18, clamped)
        output_path: caminho do MP4 final (default: videos/<slug>_edited.mp4)

    Returns:
        {
            "sucesso": bool,
            "status": "Video_Editado" | "Aguardando_Assets" | "Assets_Invalidos" | "Erro",
            "video_path": str | None,
            "produto": str,
            "cenas_usadas": [...],
            "cta_sintetico": bool,
            "duracao": float,
            "score_edicao": int,  # 0-100
            "modo": "edicao_capcut",
        }
    """
    log.info("=" * 60)
    log.info(f"✂️  PRODUCT VIDEO EDITOR — '{produto}' (estilo CapCut)")
    log.info("=" * 60)
    inicio = time.time()

    plano = plano or {}
    nicho = plano.get("nicho", "")
    estilo_pedido_pelo_usuario = "estilo" in plano  # True se vier no plano
    estilo = plano.get("estilo", "viral_produto")
    if estilo not in PRESETS:
        log.warning(f"Estilo '{estilo}' desconhecido — usando 'viral_produto'")
        estilo = "viral_produto"

    # ── 🧠 Consulta memória de longo prazo (best-effort) ──
    log.info(f"\n🧠 Consultando memória pra produto='{produto}', nicho='{nicho or '(sem nicho)'}'...")
    ctx_memoria = _consultar_memoria_para_edicao(produto=produto, nicho=nicho)
    recomendacoes_memoria = ctx_memoria.get("recomendacoes", [])
    memorias_usadas = ctx_memoria.get("memorias_usadas", [])
    preset_sugerido_memoria = ctx_memoria.get("preset_sugerido")

    if recomendacoes_memoria:
        log.info(f"🧠 Memória consultada — {len(recomendacoes_memoria)} recomendação(ões), "
                 f"{len(memorias_usadas)} memória(s) usada(s):")
        for rec in recomendacoes_memoria[:5]:
            log.info(f"   • {rec}")
    else:
        log.info(f"🧠 Sem memórias prévias pra esse contexto — usando defaults")

    # Override do estilo baseado em memória (só se usuário NÃO especificou)
    if not estilo_pedido_pelo_usuario:
        # Tier 1: usar preset_sugerido do Memory Agent se válido
        if preset_sugerido_memoria and preset_sugerido_memoria in PRESETS:
            if preset_sugerido_memoria != estilo:
                log.info(f"🧠 Memória sugere preset '{preset_sugerido_memoria}' — aplicando")
                estilo = preset_sugerido_memoria
        elif preset_sugerido_memoria and preset_sugerido_memoria not in PRESETS:
            log.warning(f"🧠 Memória sugeriu preset '{preset_sugerido_memoria}' "
                        f"mas não está em PRESETS — mantendo '{estilo}'")
        # Tier 2: análise das recomendações em texto livre
        preset_por_texto = _detectar_preset_por_memoria(recomendacoes_memoria)
        if preset_por_texto and preset_por_texto in PRESETS and preset_por_texto != estilo:
            log.info(f"🧠 Recomendações apontam pra estilo agressivo — "
                     f"trocando '{estilo}' → '{preset_por_texto}'")
            estilo = preset_por_texto
    else:
        log.info(f"   (estilo fornecido pelo usuário: '{estilo}' — memória não sobrescreve)")

    preset = PRESETS[estilo]

    # Clampa duração alvo
    duracao_alvo = plano.get("duracao_alvo", 15.0)
    try:
        duracao_alvo = float(duracao_alvo)
    except (TypeError, ValueError):
        duracao_alvo = 15.0
    if duracao_alvo < DURACAO_ALVO_MIN or duracao_alvo > DURACAO_ALVO_MAX:
        log.warning(
            f"duracao_alvo={duracao_alvo}s fora do sweet spot "
            f"[{DURACAO_ALVO_MIN}-{DURACAO_ALVO_MAX}] — clampando"
        )
        duracao_alvo = max(DURACAO_ALVO_MIN, min(DURACAO_ALVO_MAX, duracao_alvo))

    # Resolve textos por cena — 4 camadas (mais específico ganha):
    #   Camada 0: TEXTOS_PADRAO (universal, hardcoded)
    #   Camada 1: Copy Adapter (categoria detectada por nome do produto)
    #   Camada 2: plano["textos_por_cena"] (custom explícito)
    #   Camada 3: plano["hook"] → dor, plano["cta"] → cta (precedência máxima)
    textos = dict(TEXTOS_PADRAO)

    # Camada 1: Copy Adapter (best-effort — não quebra se falhar)
    if _COPY_ADAPTER_OK:
        try:
            copy_resultado = escolher_copy_por_cena(
                produto=produto,
                plano=plano,
                cenas=list(textos.keys()),
                nicho=nicho,
)
            fontes_copy = copy_resultado.pop("_fontes", {})
            categoria_detectada = copy_resultado.pop("_categoria_detectada", "(nenhuma)")
            for cena, texto_adapter in copy_resultado.items():
                if texto_adapter:
                    textos[cena] = texto_adapter
            log.info(f"📝 Copy Adapter: {_descrever_decisao_copy(produto, plano, nicho=nicho)}")
            contagem = {}
            for fonte in fontes_copy.values():
                chave = fonte.split(":")[0]
                contagem[chave] = contagem.get(chave, 0) + 1
            resumo_fontes = " ".join(f"{k}:{v}" for k, v in contagem.items())
            log.info(f"   Distribuição de fontes: {resumo_fontes}")
        except Exception as e:
            log.warning(f"⚠️  Copy Adapter falhou ({e}) — usando TEXTOS_PADRAO")
    else:
        log.warning(f"⚠️  Copy Adapter indisponível — usando TEXTOS_PADRAO "
                    f"(textos podem não combinar com o produto)")

    # Camada 2: plano customizado tem precedência sobre Copy Adapter
    textos_custom = plano.get("textos_por_cena") or {}
    for cena, txt in textos_custom.items():
        if txt:
            textos[cena] = txt
    # Camada 3: hook/cta do plano (precedência máxima nessas cenas específicas)
    if plano.get("hook"):
        textos["dor"] = plano["hook"]
    if plano.get("cta"):
        textos["cta"] = plano["cta"]

    resposta_base = {
        "produto":       produto,
        "slug":          slugificar_produto(produto),
        "video_path":    None,
        "cenas_usadas":  [],
        "cta_sintetico": False,
        "duracao":       0,
        "score_edicao":  0,
        "modo":          "edicao_capcut",
        "estilo":        estilo,
        "timestamp":     time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # ── 0. Deps ──
    ok_dep, msg_dep = _checar_dependencias()
    if not ok_dep:
        return {**resposta_base, "sucesso": False, "status": "Erro",
                "mensagem": msg_dep}

    # ── 1. Status do produto ──
    log.info("\n1️⃣  Verificando status dos assets...")
    status = verificar_assets_produto(produto)
    log.info(f"   Status: {status['status']} | Score assets: {status['score_prontidao']}/100")

    if status.get("deve_aguardar"):
        return {
            **resposta_base,
            "sucesso":  False,
            "status":   "Aguardando_Assets",
            "mensagem": (
                f"Assets insuficientes ({status['status']}). "
                f"{status.get('recomendacoes', ['Adicione mais clipes.'])[0]}"
            ),
        }

    slug = status["slug"]

    # ── 2. Propósitos + seleção ──
    log.info("\n2️⃣  Lendo metadata + selecionando clipes...")
    propositos = _ler_propositos_do_metadata(slug)
    if not propositos:
        return {
            **resposta_base,
            "sucesso":  False,
            "status":   "Assets_Invalidos",
            "mensagem": "Nenhum propósito no metadata. Rode o Asset Hunter.",
        }
    selecionados = _selecionar_clipes_por_proposito(slug, propositos)
    log.info(f"   Clipes encontrados pra: {list(selecionados.keys())}")

    # ── 🛡️ Guard preventivo: inflar preset se duração estimada < 10s ──
    propositos_disp = set(selecionados.keys())
    preset, ajustes_aplicados = _inflar_preset_pra_chegar_no_minimo(
        preset, propositos_disp, DURACAO_POSTAVEL_MIN
    )
    if ajustes_aplicados:
        dur_est, _ = _estimar_duracao_total(
            preset, propositos_disp, preset.get("crossfade_seg", 0.15)
        )
        log.info(
            f"🛡️  Preset '{estilo}' estendido pra evitar vídeo curto:"
        )
        for aj in ajustes_aplicados:
            log.info(f"      • {aj}")
        log.info(f"      Duração estimada agora: ~{dur_est:.1f}s")

    # ── 3. Editar cada cena ──
    log.info(f"\n3️⃣  Editando cenas (estilo: {estilo})...")
    cenas_editadas = []   # lista de (proposito, clip)
    erros_cenas    = []

    for proposito in ORDEM_CENAS:
        if proposito not in selecionados:
            log.info(f"   ⏭️  '{proposito}' não disponível — pulando (CTA sintético entra depois se faltar 'cta')")
            continue

        caminho = selecionados[proposito]
        dur_alvo = preset["duracoes"].get(proposito, 2.5)

        # Abre + corta (do meio, helper do renderer)
        clip, erro = _tentar_abrir_clipe(caminho, dur_alvo)
        if erro:
            log.warning(f"   ❌ '{proposito}' ({caminho.name}): {erro}")
            erros_cenas.append({"proposito": proposito, "arquivo": caminho.name, "erro": erro})
            continue

        # Ajusta 9:16
        try:
            clip = _ajustar_para_vertical(clip)
        except Exception as e:
            log.warning(f"   ⚠️  '{proposito}': crop 9:16 falhou ({e})")
            erros_cenas.append({"proposito": proposito, "arquivo": caminho.name,
                                "erro": f"crop falhou: {e}"})
            try: clip.close()
            except Exception: pass
            continue

        # Punch-in
        clip = _aplicar_punch_in(clip,
                                  zoom_inicio=preset["zoom_inicio"],
                                  zoom_fim=preset["zoom_fim"])

        # Texto da cena
        texto_cena = textos.get(proposito, "")
        if texto_cena:
            posicao = "top" if proposito in ("dor", "demo") else "bottom"
            clip = _adicionar_texto_overlay(clip, texto_cena, posicao=posicao)

        cenas_editadas.append((proposito, clip))
        log.info(f"   ✅ '{proposito}': {clip.duration:.1f}s, "
                 f"texto='{texto_cena[:30]}{'...' if len(texto_cena) > 30 else ''}'")

    if len(cenas_editadas) < 2:
        # Não dá pra editar com 1 cena só — usa renderer com --force pra isso
        for _, c in cenas_editadas:
            try: c.close()
            except Exception: pass
        return {
            **resposta_base,
            "sucesso":  False,
            "status":   "Assets_Invalidos",
            "mensagem": (f"Apenas {len(cenas_editadas)} cena(s) válida(s). "
                         f"Editor precisa de pelo menos 2 (mais CTA sintético no fim)."),
            "erros_cenas": erros_cenas,
        }

    # ── 4. CTA sintético se faltar a cena 'cta' ──
    tem_cta_real = any(p == "cta" for p, _ in cenas_editadas)
    cta_sintetico_usado = False
    if not tem_cta_real:
        log.info(f"\n4️⃣  Cena 'cta' faltando — criando CTA sintético do último frame...")
        ultimo_prop, ultimo_clip = cenas_editadas[-1]
        cta_clip, erro_cta = _criar_cta_sintetico(
            ultimo_clip,
            duracao=preset["cta_sintetico_dur"],
            texto=plano.get("cta") or CTA_SINTETICO_TEXTO,
        )
        if cta_clip is not None:
            cenas_editadas.append(("cta_sintetico", cta_clip))
            cta_sintetico_usado = True
            log.info(f"   ✅ CTA sintético adicionado ({preset['cta_sintetico_dur']}s)")
        else:
            log.warning(f"   ⚠️  CTA sintético falhou ({erro_cta}) — seguindo sem")
    else:
        log.info(f"\n4️⃣  Cena 'cta' real presente — não precisa de sintético")

    # ── 4b. Cena 'beneficio' sintética se preset pediu (vídeo curto demais) ──
    beneficio_usado = False
    if preset.get("_adicionar_beneficio") and cenas_editadas:
        log.info(f"\n4️⃣b ️ Adicionando cena 'beneficio' (vídeo seria curto demais)...")
        # Usa demo como melhor candidato; fallback resultado; senão último
        melhor_clipe = None
        for prop_pref in ("demo", "resultado", "dor"):
            for prop, clip in cenas_editadas:
                if prop == prop_pref:
                    melhor_clipe = clip
                    break
            if melhor_clipe is not None:
                break
        if melhor_clipe is None and cenas_editadas:
            melhor_clipe = cenas_editadas[-1][1]

        if melhor_clipe is not None:
            bene_clip, erro_b = _criar_cena_beneficio(
                melhor_clipe,
                duracao=BENEFICIO_DUR_SEG,
                texto=BENEFICIO_TEXTO_DEFAULT,
            )
            if bene_clip is not None:
                # Insere antes do CTA (sintético ou real) pra ordem fazer sentido:
                # dor → demo → resultado → close → BENEFICIO → cta
                # Reordena: tudo menos cta, então beneficio, então cta
                cenas_sem_cta = [(p, c) for p, c in cenas_editadas if "cta" not in p]
                cenas_cta     = [(p, c) for p, c in cenas_editadas if "cta" in p]
                cenas_editadas = cenas_sem_cta + [("beneficio", bene_clip)] + cenas_cta
                beneficio_usado = True
                log.info(f"   ✅ Cena 'beneficio' adicionada: \"{BENEFICIO_TEXTO_DEFAULT}\"")
            else:
                log.warning(f"   ⚠️  Cena 'beneficio' falhou ({erro_b}) — seguindo sem")

    # ── 5. Concatenar ──
    cenas_usadas = [p for p, _ in cenas_editadas]
    log.info(f"\n5️⃣  Concatenando {len(cenas_editadas)} cena(s) com crossfade...")
    *_, concatenate_videoclips = _import_moviepy()
    video_final = None
    try:
        clipes_so = [c for _, c in cenas_editadas]
        if len(clipes_so) == 1:
            video_final = clipes_so[0]
        else:
            video_final = concatenate_videoclips(
                clipes_so,
                method="compose",
                padding=-preset["crossfade_seg"],
            )
    except Exception as e:
        log.error(f"   ❌ Concatenação falhou: {e}")
        for _, c in cenas_editadas:
            try: c.close()
            except Exception: pass
        return {
            **resposta_base,
            "sucesso":  False,
            "status":   "Erro",
            "mensagem": f"Erro na concatenação: {e}",
            "cenas_usadas": cenas_usadas,
        }

    duracao_total = round(float(video_final.duration or 0), 2)

    # ── 6. Áudio (com detector de validade) ──
    log.info(f"\n6️⃣  Verificando áudio...")
    audio_path = selecionar_melhor_audio(produto, usar_librosa=True)
    usar_audio = False
    audio_clip_final = None
    audio_motivo = ""

    if audio_path is None:
        audio_motivo = "produto sem arquivo de áudio"
        log.info(f"   ⏭️  {audio_motivo}")
    else:
        valido, motivo = _audio_eh_valido(audio_path)
        if not valido:
            audio_motivo = f"áudio inválido ({motivo})"
            log.warning(f"   ⚠️  {audio_path.name}: {audio_motivo} — pulando sem tentar MoviePy")
        else:
            log.info(f"   📀 Áudio válido: {audio_path.name}")
            try:
                _, AudioFileClip, *_ = _import_moviepy()
                audio_raw = AudioFileClip(str(audio_path))
                if audio_raw.duration < duracao_total:
                    audio_clip_final = _subclip(audio_raw, 0, audio_raw.duration)
                else:
                    audio_clip_final = _subclip(audio_raw, 0, duracao_total)
                audio_clip_final = _audio_fadein(audio_clip_final, preset["fade_audio_seg"])
                audio_clip_final = _audio_fadeout(audio_clip_final, preset["fade_audio_seg"])
                video_final = _set_audio(video_final, audio_clip_final)
                usar_audio = True
                log.info(f"   ✅ Áudio aplicado com fade in/out")
            except Exception as e:
                audio_motivo = f"MoviePy falhou ao processar áudio: {str(e)[:80]}"
                log.warning(f"   ⚠️  {audio_motivo}")

    # 🧠 Cross-check: memória pediu áudio e a gente não conseguiu aplicar?
    if not usar_audio and _memoria_pede_audio(recomendacoes_memoria):
        log.warning(f"   ⚠️  🧠 Memória recomenda áudio real, mas produto está sem áudio válido")
        log.warning(f"      → Considere baixar trilha do Pixabay/Mixkit e colocar em "
                    f"assets/produtos/<slug>/audio/")

    # ── 7. Output path ──
    if output_path:
        path_out = Path(output_path)
    else:
        VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        path_out = VIDEOS_DIR / f"{slug}_edited.mp4"

    # Backup do anterior se existir
    if path_out.exists():
        backup = path_out.with_suffix(".mp4.bak")
        try:
            shutil.move(str(path_out), str(backup))
            log.info(f"   💾 Backup: {backup.name}")
        except Exception:
            pass

    # ── 8. Export ──
    log.info(f"\n7️⃣  Exportando: {path_out.name}")
    try:
        write_kwargs = {
            "fps":           FPS_ALVO,
            "codec":         "libx264",
            "preset":        "ultrafast",   # render rápido (era 105s, vira ~25s)
            "ffmpeg_params": ["-pix_fmt", "yuv420p"],
            "logger":        None,
        }
        if not _is_moviepy_v2():
            write_kwargs["audio"] = usar_audio
        video_final.write_videofile(str(path_out), **write_kwargs)
    except Exception as e:
        log.error(f"❌ Export falhou: {e}")
        return {
            **resposta_base,
            "sucesso":     False,
            "status":      "Erro",
            "mensagem":    f"Erro no export: {e}",
            "cenas_usadas": cenas_usadas,
            "duracao":     duracao_total,
        }
    finally:
        try: video_final.close()
        except Exception: pass
        for _, c in cenas_editadas:
            try: c.close()
            except Exception: pass
        if audio_clip_final is not None:
            try: audio_clip_final.close()
            except Exception: pass

    # ── 9. Score ──
    score = 0
    # 25 pts: tem 5 cenas (mesmo que cta seja sintético)
    if len(cenas_usadas) >= 5:
        score += 25
    else:
        score += 5 * len(cenas_usadas)
    # 20 pts: áudio válido
    if usar_audio:
        score += 20
    # 15 pts: textos aplicados em todas as cenas usadas (não-sintéticas)
    cenas_reais = [c for c in cenas_usadas if c != "cta_sintetico"]
    if cenas_reais and all(textos.get(c) for c in cenas_reais):
        score += 15
    # Duração — score gradual (era binário 12-18s, agora reflete realidade):
    #   < 10s: 0 pts + PENALIZAÇÃO -10
    #   10-12s: 7 pts (aceitável)
    #   12-18s: 15 pts (ideal)
    #   18-22s: 7 pts (longo mas postável)
    #   > 22s: 0 pts
    duracao_muito_curta = duracao_total < DURACAO_POSTAVEL_MIN
    if duracao_muito_curta:
        score -= 10
    elif DURACAO_POSTAVEL_MIN <= duracao_total < DURACAO_IDEAL_MIN:
        score += 7
    elif DURACAO_IDEAL_MIN <= duracao_total <= DURACAO_IDEAL_MAX:
        score += 15
    elif DURACAO_IDEAL_MAX < duracao_total <= DURACAO_LIMITE_MAX:
        score += 7
    # > DURACAO_LIMITE_MAX: 0 pts
    # 15 pts: punch-in aplicado (sempre tenta — soma se preset tem zoom)
    if preset["zoom_fim"] > preset["zoom_inicio"]:
        score += 15
    # 10 pts: hook+cta nos extremos
    if "dor" in cenas_usadas and ("cta" in cenas_usadas or "cta_sintetico" in cenas_usadas):
        score += 10
    score = max(0, min(100, score))

    duracao_render = round(time.time() - inicio, 2)
    log.info(f"\n✅ Edição concluída em {duracao_render}s")
    log.info(f"   Vídeo: {path_out.name}")
    log.info(f"   Duração: {duracao_total}s | Score edição: {score}/100")

    # Monta retorno final
    retorno = {
        **resposta_base,
        "sucesso":           True,
        "status":            "Video_Editado",
        "video_path":        str(path_out),
        "cenas_usadas":      cenas_usadas,
        "cta_sintetico":     cta_sintetico_usado,
        "beneficio_sintetico": beneficio_usado,
        "duracao":           duracao_total,
        "duracao_curta":     duracao_muito_curta,
        "score_edicao":      score,
        "usou_audio":        usar_audio,
        "audio_motivo":      audio_motivo if not usar_audio else "ok",
        "duracao_render_s":  duracao_render,
        "erros_cenas":       erros_cenas,
        "textos_aplicados":  {c: textos.get(c, "") for c in cenas_usadas if c not in ("cta_sintetico", "beneficio")},
        "estilo_usado":      estilo,
        "ajustes_preset":    ajustes_aplicados,
        "memoria_consultada": bool(recomendacoes_memoria),
        "mensagem":          (f"Vídeo editado: {len(cenas_usadas)} cena(s), "
                              f"{duracao_total}s, score={score}/100"
                              f"{', CTA sintético' if cta_sintetico_usado else ''}"
                              f"{', beneficio' if beneficio_usado else ''}"
                              f"{', com áudio' if usar_audio else ', SEM áudio'}"
                              f"{' ⚠️  CURTO DEMAIS' if duracao_muito_curta else ''}"),
    }

    # ── 🧠 Registra aprendizado pra próximas edições aprenderem ──
    slug = resposta_base["slug"]
    resumo_partes = [
        f"Vídeo editado pra '{produto}' (nicho={nicho or 'n/a'}).",
        f"Estilo usado: {estilo}.",
        f"Cenas: {cenas_usadas}.",
        f"Score edição: {score}/100, duração: {duracao_total}s.",
        f"Áudio: {'aplicado' if usar_audio else 'AUSENTE (' + audio_motivo + ')'}.",
    ]
    if cta_sintetico_usado:
        resumo_partes.append("CTA sintético usado (faltava clipe cta).")
    if recomendacoes_memoria:
        resumo_partes.append(
            f"Memória influenciou — {len(recomendacoes_memoria)} recomendação(ões) consideradas."
        )
    # Sugestão pra próxima vez baseada no que ficou ruim
    sug_futura = []
    if not usar_audio:
        sug_futura.append("adicionar trilha de áudio válida (Pixabay/Mixkit)")
    if score < 70:
        sug_futura.append("revisar textos por cena pra mais impacto")
    if cta_sintetico_usado:
        sug_futura.append("gravar clipe CTA real (evita CTA sintético genérico)")
    if sug_futura:
        resumo_partes.append("Sugestões futuras: " + "; ".join(sug_futura) + ".")
    resumo = " ".join(resumo_partes)

    tags = ["edicao", "video", slug, estilo]
    if not usar_audio:
        tags.append("sem_audio")
    if cta_sintetico_usado:
        tags.append("cta_sintetico")
    if beneficio_usado:
        tags.append("beneficio_sintetico")
    if duracao_muito_curta:
        tags.append("duracao_curta")

    _registrar_aprendizado_seguro(
        etapa="product_video_editor",
        resultado=retorno,
        resumo=resumo,
        tags=tags,
    )

    # ── 🚨 Memória EXTRA: se ficou curto, registra como erro pra
    # próxima edição aprender ──
    if duracao_muito_curta and _MEMORY_DISPONIVEL:
        try:
            from agents.memory_agent import registrar_memoria
            registrar_memoria(
                tipo="erro",
                texto=(
                    f"Vídeo agressivo do produto '{produto}' ficou curto demais "
                    f"({duracao_total}s < {DURACAO_POSTAVEL_MIN}s). Próxima edição "
                    f"deve usar 'viral_produto_agressivo_balanceado' ou aumentar "
                    f"CTA sintético/cena beneficio. Estilo usado foi '{estilo}'."
                ),
                metadata={
                    "produto":   produto,
                    "nicho":     nicho or "",
                    "estilo":    estilo,
                    "duracao":   duracao_total,
                    "limite":    DURACAO_POSTAVEL_MIN,
                },
                tags=["edicao", "duracao_curta", slug, "lição_aprendida"],
            )
            log.warning(f"   🚨 Memória de erro registrada: vídeo ficou < {DURACAO_POSTAVEL_MIN}s")
        except Exception as e:
            log.warning(f"   Falha ao registrar memória de duração curta: {e}")

    return retorno


# =================================================================
# RELATÓRIO + CLI
# =================================================================

def imprimir_relatorio(r: dict):
    print("\n" + "=" * 60)
    print(f"  ✂️  PRODUCT VIDEO EDITOR — Relatório")
    print("=" * 60)
    print(f"  Produto:   {r['produto']}")
    print(f"  Slug:      {r['slug']}")
    print(f"  Estilo:    {r.get('estilo', '?')}")
    print(f"  Status:    {r['status']}")

    if r["sucesso"]:
        print(f"\n  ✅ Vídeo editado salvo em:")
        print(f"     {r['video_path']}")
        print(f"\n  📊 Métricas:")
        print(f"     Duração:       {r['duracao']}s")
        print(f"     Score edição:  {r['score_edicao']}/100")
        print(f"     Cenas usadas:  {r['cenas_usadas']}")
        print(f"     CTA sintético: {'✅ sim' if r.get('cta_sintetico') else 'não'}")
        print(f"     Áudio:         {'✅ aplicado' if r.get('usou_audio') else '❌ ' + r.get('audio_motivo', '')}")
        if r.get("textos_aplicados"):
            print(f"\n  📝 Textos por cena:")
            for cena, txt in r["textos_aplicados"].items():
                print(f"     {cena:12s} → \"{txt}\"")
    else:
        print(f"\n  ❌ Falha: {r.get('mensagem', '?')}")
        if r.get("erros_cenas"):
            print(f"\n  📋 Erros por cena:")
            for e in r["erros_cenas"]:
                print(f"     • [{e['proposito']:10s}] {e['arquivo']}: {e['erro']}")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Product Video Editor — edição estilo CapCut com punch-in, textos por cena, CTA sintético"
    )
    parser.add_argument("--produto", default="Mini Aspirador de Teclado",
                        help="Nome do produto alvo")
    parser.add_argument("--hook", default="",
                        help="Texto da primeira cena (sobrescreve cena 'dor')")
    parser.add_argument("--cta", default="",
                        help="Texto da cena CTA (real ou sintética)")
    parser.add_argument("--estilo", default=None,
                        choices=list(PRESETS.keys()),
                        help="Preset de estilo (default: deixa memória sugerir, ou 'viral_produto')")
    parser.add_argument("--duracao-alvo", type=float, default=15.0,
                        dest="duracao_alvo",
                        help="Duração alvo em segundos (12-18, default: 15)")
    parser.add_argument("--output", default="",
                        help="Caminho do MP4 (default: videos/<slug>_edited.mp4)")
    args = parser.parse_args()

    plano = {
        "duracao_alvo": args.duracao_alvo,
    }
    # Só adiciona estilo no plano se usuário PASSOU explicitamente
    # (default None = deixa memória decidir)
    if args.estilo is not None:
        plano["estilo"] = args.estilo
    if args.hook:
        plano["hook"] = args.hook
    if args.cta:
        plano["cta"] = args.cta

    r = editar_video_produto_capcut_style(
        produto=args.produto,
        plano=plano,
        output_path=args.output or None,
    )
    imprimir_relatorio(r)

    if r["status"] == "Video_Editado":
        return 0
    elif r["status"] == "Aguardando_Assets":
        return 1
    else:
        return 2


if __name__ == "__main__":
    sys.exit(main())