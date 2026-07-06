#!/usr/bin/env python3
# integrations/telegram_repurpose_hunter.py
# PEÇA-CHAVE JARVIS — rev 6 "Máquina de Comissões"
# Correções sobre a rev 5 (alinhamento com o resto do projeto):
#   [FIX-9]  Plano gravado agora usa as chaves CANÔNICAS "narracao" e "duracao"
#            (lidas por autonomous_orchestrator / publicadores / finalizar_plano).
#            Aliases "narracao_propria"/"duracao_video" mantidos por compat.
#   [FIX-10] Varredura do Telegram passa a aceitar vídeo enviado como
#            documento/arquivo (mime video/*), não só msg.video.
#
# Correções sobre a rev 4:
#   [FIX-1] SyntaxError em _crop_clip (keyword `y1` repetido -> `y2`).
#   [FIX-2] Efeitos de diferenciação (mirror/zoom/grade/vinheta/velocidade) agora
#           são de fato aplicados no pipeline; _grade_frame duplicado removido.
#   [FIX-3] Facebook Ad Library: versão de API atualizada e campos reais
#           (a Ad Library NÃO expõe URL de vídeo direta — só ad_snapshot_url).
#   [FIX-4] Fetches HTTP síncronos saíram do event loop (rodam em executor).
#   [FIX-5] Render roda num ThreadPoolExecutor dedicado/limitado (backpressure).
#   [FIX-6] Download externo com limite de tamanho e checagem de Content-Type.
#   [FIX-7] Dedup com contagem de tentativas (evita reprocessar itens quebrados
#           indefinidamente). _carregar_vistos morto removido.
#   [FIX-8] requests.Session compartilhada com retry/backoff.

import os
import re
import sys
import json
import time
import random
import asyncio
import argparse
import sqlite3
import functools
import unicodedata
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from telethon import TelegramClient
import numpy as np
import requests

BASE_DIR = Path(__file__).parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

# Logger compartilhado ou fallback
try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("telegram_hunter")


# ── Núcleo obrigatório ────────────────────────────────────────────────────
from integrations.shopee_affiliate import minerar_oportunidades, gerar_link_afiliado
from shared.production_state import atualizar_produto  # esteira de produção


# User agent usado em requests a provedores externos
USER_AGENT = "jarvis-hunter/1.0 (+https://your.domain)"

# Teto de download para criativos externos (evita encher o disco).
MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024  # 200 MB

# Máximo de tentativas antes de considerar um item "morto" e parar de reprocessar.
MAX_TENTATIVAS = 3


def _build_session() -> requests.Session:
    """Sessão HTTP compartilhada com retry/backoff para provedores externos."""
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    try:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        retry = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
        )
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
    except Exception:
        log.debug("Retry adapter indisponível; usando sessão HTTP simples.")
    return s


_HTTP = _build_session()

# Executor dedicado para render (serializa/limita a re-produção de vídeo).
# NOTA: threads não são canceláveis — no timeout o encode segue até o fim,
# mas o pool limitado dá backpressure em vez de vazar threads sem limite.
_RENDER_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="render")


# ── Peças criativas (opcionais; degradam com elegância) ───────────────────
def _try_import(label, fn):
    try:
        return fn(), True
    except Exception as e:
        log.warning(f"{label} indisponível ({type(e).__name__}: {e}). Usando fallback.")
        return None, False


def _imp_hook():
    from creative_engine.hook_builder import construir_hook, cta_curto
    return (construir_hook, cta_curto)


def _imp_narr():
    from creative_engine.narration_script_builder import (
        construir_roteiro, estimar_duracao_frase)
    return (construir_roteiro, estimar_duracao_frase)


def _imp_tts():
    from creative_engine.tts_edge import (
        gerar_narracao, boundaries_para_blocos, edge_tts_disponivel)
    return (gerar_narracao, boundaries_para_blocos, edge_tts_disponivel)


def _imp_desc():
    from creative_engine.descricao_builder import montar_todas, montar_descricao
    return (montar_todas, montar_descricao)


def _imp_render():
    from creative_engine.product_video_renderer import (
        _import_moviepy, _subclip, _set_audio, _crop_clip, _resize_clip,
        _ajustar_para_vertical, LARGURA_ALVO, ALTURA_ALVO)
    return (_import_moviepy, _subclip, _set_audio, _crop_clip, _resize_clip,
            _ajustar_para_vertical, LARGURA_ALVO, ALTURA_ALVO)


def _imp_videoprovider():
    try:
        from providers.video_provider import gerar_video_externo
    except Exception:
        from creative_engine.video_provider import gerar_video_externo  # alt
    return gerar_video_externo


(_HOOK, _HOOK_OK) = _try_import("hook_builder", _imp_hook)
(_NARR, _NARR_OK) = _try_import("narration_script_builder", _imp_narr)
(_TTS, _TTS_OK) = _try_import("tts_edge", _imp_tts)
(_DESC, _DESC_OK) = _try_import("descricao_builder", _imp_desc)
(_RND, _RND_OK) = _try_import("product_video_renderer", _imp_render)
(_VPROV, _VPROV_OK) = _try_import("video_provider", _imp_videoprovider)

try:
    from moviepy import VideoFileClip  # noqa: F401 (só pra detectar presença)
    MOVIEPY_OK = True
except Exception:
    try:
        from moviepy.editor import VideoFileClip  # noqa: F401
        MOVIEPY_OK = True
    except Exception:
        MOVIEPY_OK = False
        log.warning("MoviePy ausente — re-produção de vídeo será ignorada.")


# ── Credenciais / paths ───────────────────────────────────────────────────
_API_ID_RAW = os.environ.get("TELEGRAM_API_ID", "")
_API_HASH   = os.environ.get("TELEGRAM_API_HASH", "")

SESSION_PATH  = BASE_DIR / "shared" / "jarvis_hunter_session"
INBOX_VIDEOS  = BASE_DIR / "assets" / "inbox" / "videos"
SHARED_PLANS  = BASE_DIR / "shared" / "content_plans"
SEEN_DB       = BASE_DIR / "shared" / "hunter_seen.sqlite"   # sqlite (msg_id TEXT)
VIDEO_TIMEOUT = 1200  # VPS de CPU fraco renderiza devagar; margem generosa

# Facebook token (opcional) para Ad Library API
FACEBOOK_ACCESS_TOKEN = os.environ.get("FACEBOOK_ACCESS_TOKEN", "")

# ──────────────────────────────────────────────────────────────────────────
# Configurações do pipeline de diferenciação
CFG_NARRACAO_NOVA      = False   # repost mantém o áudio original (sem narração própria)
CFG_AUDIO_ORIGINAL_VOL = 1.0     # áudio original do vídeo no volume cheio
CFG_MUSICA_FUNDO_VOL   = 0.12
CFG_LEGENDAS           = True
CFG_HOOK_OVERLAY       = True
CFG_CTA_FINAL          = True
CFG_REFRAME_ZOOM       = 1.06
CFG_GRADE              = True
CFG_BRILHO             = 1.02
CFG_SATURACAO          = 1.04
CFG_GRANULADO          = 3
CFG_LIMPAR_META        = True
CFG_VELOCIDADE         = 1.01
CFG_ZOOM_DIGITAL       = 0.01
CFG_MIRROR_X           = True
CFG_VINHETA            = True

CFG_INTRO_IA           = False
CFG_INTRO_IA_PROVIDER  = "pixverse"
CFG_INTRO_DUR          = 2.5

CFG_HOOK_SEG = 2.5
CFG_CTA_SEG  = 2.5
CFG_DUR_MAX  = 34.0

VOZ_NARRACAO = "pt-BR-FranciscaNeural"

_GRAIN_RNG = np.random.default_rng()


# ══════════════════════════════════════════════════════════════════════════
# UTILITÁRIOS
# ══════════════════════════════════════════════════════════════════════════
def _validar_credenciais() -> tuple:
    if not _API_ID_RAW or not _API_HASH:
        return False, "TELEGRAM_API_ID ou TELEGRAM_API_HASH ausentes."
    try:
        int(_API_ID_RAW)
    except ValueError:
        return False, f"TELEGRAM_API_ID deve ser numérico: {_API_ID_RAW!r}"
    return True, ""


def _salvar_json_atomico(caminho: Path, dados) -> bool:
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        tmp.replace(caminho)
        return True
    except Exception:
        try:
            tmp.unlink()
        except Exception:
            pass
        log.exception(f"Falha ao salvar {caminho.name}")
        return False


# ── Seen DB (sqlite) para evitar race conditions entre processos -----------
def _init_seen_db():
    try:
        SEEN_DB.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(SEEN_DB), timeout=10, isolation_level=None)
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS seen (
                canal      TEXT NOT NULL,
                msg_id     TEXT NOT NULL,
                ts         INTEGER NOT NULL,
                status     TEXT NOT NULL DEFAULT 'ok',
                tentativas INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (canal, msg_id)
            )
        """)
        cur.close()
        conn.close()
    except Exception:
        log.exception("Falha ao inicializar seen DB")


_init_seen_db()


def _deve_pular(canal: str, msg_id) -> bool:
    """True se o item já foi concluído com sucesso ou falhou demais."""
    try:
        conn = sqlite3.connect(str(SEEN_DB), timeout=10)
        cur = conn.cursor()
        cur.execute(
            "SELECT status, tentativas FROM seen WHERE canal = ? AND msg_id = ? LIMIT 1",
            (canal, str(msg_id)),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return False
        status, tentativas = row
        if status == "ok":
            return True
        if (tentativas or 0) >= MAX_TENTATIVAS:
            log.debug(f"{canal}/{msg_id} excedeu {MAX_TENTATIVAS} tentativas; pulando.")
            return True
        return False
    except Exception:
        log.exception("Falha ao verificar visto")
        return False


def _marcar_processado(canal: str, msg_id):
    try:
        conn = sqlite3.connect(str(SEEN_DB), timeout=10)
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO seen (canal, msg_id, ts, status, tentativas) "
            "VALUES (?, ?, ?, 'ok', 0)",
            (canal, str(msg_id), int(time.time())),
        )
        # manter apenas os últimos 500 por canal
        cur.execute("""
            DELETE FROM seen
            WHERE canal = ?
            AND msg_id NOT IN (
                SELECT msg_id FROM seen WHERE canal = ? ORDER BY ts DESC LIMIT 500
            )
        """, (canal, canal))
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        log.exception("Falha ao marcar processado")


def _registrar_falha(canal: str, msg_id):
    """Incrementa o contador de tentativas de um item que falhou."""
    try:
        conn = sqlite3.connect(str(SEEN_DB), timeout=10)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO seen (canal, msg_id, ts, status, tentativas) "
            "VALUES (?, ?, ?, 'fail', 1) "
            "ON CONFLICT(canal, msg_id) DO UPDATE SET "
            "tentativas = tentativas + 1, ts = excluded.ts, "
            "status = CASE WHEN seen.status = 'ok' THEN 'ok' ELSE 'fail' END",
            (canal, str(msg_id), int(time.time())),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        log.exception("Falha ao registrar falha")


# ── Texto / produto extraction helpers -----------------------------------
_PALAVRAS_RUIDO = {"promo", "promoção", "oferta", "desconto", "cupom", "frete",
                   "grátis", "gratis", "link", "bio", "shopee", "achadinho",
                   "achadinhos", "compre", "corre", "imperdível", "imperdivel"}


def _limpar_linha(linha: str) -> str:
    linha = re.sub(r"https?://\S+", "", linha)
    linha = re.sub(r"#\w+", "", linha)
    linha = unicodedata.normalize("NFKC", linha)
    linha = re.sub(r"[^\w\s,.\-À-ÿ]", " ", linha)
    return re.sub(r"\s+", " ", linha).strip()


def _parece_preco(linha: str) -> bool:
    return bool(re.search(r"r?\$?\s*\d+[\.,]?\d*", linha.lower())) and \
        len(re.sub(r"[^\w]", "", linha)) <= 8


def extrair_termo_produto(texto: str) -> str:
    """Escolhe a linha que mais parece NOME DE PRODUTO (não a 1ª cegamente)."""
    if not texto:
        return ""
    brutas = [l for l in texto.split("\n") if l.strip()]
    cands = []
    for l in brutas[:6]:
        c = _limpar_linha(l)
        if not c or _parece_preco(c):
            continue
        palavras = c.split()
        if len(palavras) < 2 or len(palavras) > 9:
            continue
        ruido = sum(1 for p in palavras if p.lower() in _PALAVRAS_RUIDO)
        score = len(palavras) - 2 * ruido
        cands.append((score, c[:60]))
    if cands:
        cands.sort(key=lambda x: x[0], reverse=True)
        return cands[0][1]
    for l in brutas:
        c = _limpar_linha(l)
        if c:
            return c[:60]
    return ""


def tratar_preco(preco_raw) -> float:
    if preco_raw is None:
        return 0.0
    if isinstance(preco_raw, (int, float)):
        return float(preco_raw)
    try:
        p = str(preco_raw).strip().replace("R$", "").replace(" ", "")
        if "," in p and "." in p:
            p = p.replace(".", "").replace(",", ".")
        elif "," in p:
            p = p.replace(",", ".")
        return float(p)
    except Exception:
        log.warning(f"Preço inválido {preco_raw!r} -> 0.0")
        return 0.0


def _slugify(texto: str) -> str:
    s = re.sub(r"\W+", "_", (texto or "").lower()).strip("_")[:40]
    return s or f"produto_{int(time.time())}"


# ── Legendas / hashtags dinâmicas ----------------------------------------
_HASHTAGS_BASE = ["#achadinhos", "#shopee", "#achadinhosshopee", "#ofertas"]
_HASHTAGS_CAT = {
    "cozinha": ["#cozinha", "#casa", "#utilidades", "#organizacao"],
    "beleza":  ["#beleza", "#skincare", "#autocuidado", "#makeup"],
    "casa":    ["#casa", "#decor", "#organizacao", "#donadecasa"],
    "tech":    ["#gadgets", "#tecnologia", "#achadostech"],
    "fitness": ["#fitness", "#treino", "#saude"],
    "pet":     ["#pet", "#cachorro", "#gato", "#petlovers"],
}
_LEGENDA_TEMPLATES = [
    "{hook} Esse {nome} virou meu queridinho 😍",
    "Precisava te mostrar esse {nome}! {hook}",
    "Para de procurar — achei o {nome} ideal. {hook}",
    "{hook} O {nome} que tá viralizando 🔥",
    "Não acredito no preço desse {nome}! {hook}",
]


def _hashtags_para(categoria: str) -> str:
    cat = (categoria or "").lower()
    extra = []
    for chave, tags in _HASHTAGS_CAT.items():
        if chave in cat:
            extra = tags
            break
    tags = _HASHTAGS_BASE + extra
    vistos, out = set(), []
    for t in tags:
        if t not in vistos:
            vistos.add(t)
            out.append(t)
    return " ".join(out[:8])


def _legenda_dinamica(nome: str, hook: str) -> str:
    nome_curto = " ".join((nome or "produto").split()[:4])
    tmpl = random.choice(_LEGENDA_TEMPLATES)
    return tmpl.format(hook=hook or "Olha isso!", nome=nome_curto).strip()


# ══════════════════════════════════════════════════════════════════════════
# RENDER — helpers de compat (reusa do product_video_renderer; com fallback)
# ══════════════════════════════════════════════════════════════════════════
if _RND_OK:
    (_import_moviepy, _subclip, _set_audio, _crop_clip, _resize_clip,
     _ajustar_para_vertical, LARGURA_ALVO, ALTURA_ALVO) = _RND
else:
    LARGURA_ALVO, ALTURA_ALVO = 1080, 1920

    def _import_moviepy():
        try:
            from moviepy import (VideoFileClip, AudioFileClip, ImageClip,
                                 CompositeVideoClip, concatenate_videoclips)
        except ImportError:
            from moviepy.editor import (VideoFileClip, AudioFileClip, ImageClip,
                                        CompositeVideoClip, concatenate_videoclips)
        return (VideoFileClip, AudioFileClip, ImageClip,
                CompositeVideoClip, concatenate_videoclips)

    def _subclip(c, a, b):
        return c.subclipped(a, b) if hasattr(c, "subclipped") else c.subclip(a, b)

    def _set_audio(c, a):
        return c.with_audio(a) if hasattr(c, "with_audio") else c.set_audio(a)

    def _resize_clip(c, sz):
        return c.resized(sz) if hasattr(c, "resized") else c.resize(sz)

    def _crop_clip(c, x1, x2, y1, y2):
        if hasattr(c, "cropped"):
            return c.cropped(x1=x1, y1=y1, x2=x2, y2=y2)  # [FIX-1]
        from moviepy.video.fx.crop import crop
        return crop(c, x1=x1, x2=x2, y1=y1, y2=y2)

    def _ajustar_para_vertical(c):
        return _resize_clip(c, (LARGURA_ALVO, ALTURA_ALVO))


def _image_transform(clip, func):
    if hasattr(clip, "image_transform"):
        return clip.image_transform(func)
    return clip.fl_image(func)


def _aplicar_mirror_x(clip):
    try:
        from moviepy.video import fx as vfx  # importa o fx localmente para evitar falhas
        return clip.with_effects([vfx.MirrorX()])
    except Exception:
        return _image_transform(clip, lambda f: np.ascontiguousarray(f[:, ::-1]))


def _aplicar_velocidade(clip, fator):
    if not fator or fator == 1.0:
        return clip
    try:
        if hasattr(clip, "with_speed_scaled"):
            return clip.with_speed_scaled(fator)
        if hasattr(clip, "speedx"):
            return clip.speedx(fator)
        from moviepy.video.fx.speedx import speedx
        return speedx(clip, fator)
    except Exception:
        log.exception("Ajuste de velocidade falhou; mantendo original.")
        return clip


def _vol(audio, fator):
    if hasattr(audio, "with_volume_scaled"):
        return audio.with_volume_scaled(fator)
    if hasattr(audio, "volumex"):
        return audio.volumex(fator)
    return audio


def _clip_timing(clip, dur=None, start=None, pos=None):
    if dur is not None:
        clip = clip.with_duration(dur) if hasattr(clip, "with_duration") else clip.set_duration(dur)
    if start is not None:
        clip = clip.with_start(start) if hasattr(clip, "with_start") else clip.set_start(start)
    if pos is not None:
        clip = clip.with_position(pos) if hasattr(clip, "with_position") else clip.set_position(pos)
    return clip


def _composite_audio(tracks):
    try:
        from moviepy import CompositeAudioClip
    except Exception:
        try:
            from moviepy.editor import CompositeAudioClip
        except Exception:
            from moviepy.audio.AudioClip import CompositeAudioClip
    return CompositeAudioClip(tracks)


# ── [L5] vinheta + grade leve + grão (função única, sem duplicação) --------
def _adicionar_vignette(rgb_frame, intensidade=0.15):
    # rgb_frame: uint8 RGB or RGBA
    try:
        h, w = rgb_frame.shape[:2]
        yy, xx = np.ogrid[:h, :w]
        cy, cx = h / 2.0, w / 2.0
        r = np.sqrt(((xx - cx) ** 2 + (yy - cy) ** 2))
        max_r = np.sqrt(cx**2 + cy**2)
        mask = (r / (max_r + 1e-9))
        vignette = 1.0 - (mask ** 2) * intensidade
        vignette = vignette[:, :, np.newaxis]
        out = (rgb_frame[:, :, :3].astype(np.float32) * vignette).astype(np.uint8)
        if rgb_frame.ndim == 3 and rgb_frame.shape[2] == 4:
            res = rgb_frame.copy()
            res[:, :, :3] = out
            return res
        return out
    except Exception:
        return rgb_frame


def _processar_frame(frame, brilho, saturacao, granulado, aplicar_vignette):
    """Aplica brilho/saturação/grão e vinheta a um frame numpy (não recursivo)."""
    try:
        rgb = frame[:, :, :3].astype(np.float32)
        if brilho != 1.0:
            rgb *= float(brilho)
        if saturacao != 1.0:
            lum = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] +
                   0.114 * rgb[:, :, 2])[:, :, np.newaxis]
            rgb = lum + float(saturacao) * (rgb - lum)
        if granulado > 0:
            rgb += _GRAIN_RNG.normal(0.0, float(granulado), rgb.shape).astype(np.float32)
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)
        if aplicar_vignette:
            rgb = _adicionar_vignette(rgb, intensidade=0.15)
        if frame.ndim == 3 and frame.shape[2] == 4:
            out = frame.copy()
            out[:, :, :3] = rgb
            return out
        return rgb
    except Exception:
        return frame


# ── [L5] reframe (zoom estático central) ---------------------------------
def _aplicar_reframe(clip, z):
    if not z or z <= 1.0:
        return clip
    w, h = LARGURA_ALVO, ALTURA_ALVO
    nw, nh = int(round(w * z)), int(round(h * z))
    try:
        ampliado = _resize_clip(clip, (nw, nh))
        x1 = (nw - w) // 2
        y1 = (nh - h) // 2
        return _crop_clip(ampliado, x1=x1, x2=x1 + w, y1=y1, y2=y1 + h)
    except Exception:
        log.exception("Reframe falhou")
        return clip


def _aplicar_zoom_digital(clip, fator=0.01):
    if fator <= 0:
        return clip
    try:
        from PIL import Image
    except Exception:
        # Se PIL não disponível, retorne o clip original
        return clip

    def _zoom_frame(frame):
        try:
            h, w = frame.shape[:2]
            nw, nh = int(round(w * (1.0 - fator))), int(round(h * (1.0 - fator)))
            x = max(0, (w - nw) // 2)
            y = max(0, (h - nh) // 2)
            cropped = frame[y:y+nh, x:x+nw]
            img = Image.fromarray(cropped)
            resized = img.resize((w, h), resample=Image.LANCZOS)
            return np.asarray(resized)
        except Exception:
            return frame

    return _image_transform(clip, lambda f: _zoom_frame(f))


def _aplicar_efeitos_diferenciacao(clip):
    """[FIX-2] Aplica de fato mirror + zoom digital + grade/grão/vinheta."""
    if CFG_MIRROR_X:
        clip = _aplicar_mirror_x(clip)
        log.debug("VFX-1: Mirror X")
    if CFG_ZOOM_DIGITAL and CFG_ZOOM_DIGITAL > 0:
        clip = _aplicar_zoom_digital(clip, fator=CFG_ZOOM_DIGITAL)
        log.debug(f"VFX-3: Zoom {CFG_ZOOM_DIGITAL * 100:.0f}%")

    brilho = CFG_BRILHO if CFG_GRADE else 1.0
    sat = CFG_SATURACAO if CFG_GRADE else 1.0
    grain = CFG_GRANULADO if CFG_GRADE else 0
    if brilho != 1.0 or sat != 1.0 or grain > 0 or CFG_VINHETA:
        clip = _image_transform(
            clip,
            lambda f, _b=brilho, _s=sat, _g=grain, _v=CFG_VINHETA:
                _processar_frame(f, _b, _s, _g, _v),
        )
        log.debug(f"VFX-2,4,5: brilho={brilho} sat={sat} grain={grain} vignette={CFG_VINHETA}")
    return clip


# ── [L2/L3/L4] geração de PNG de texto (full-frame transparente) ----------
def _carregar_fonte(tam: int):
    from PIL import ImageFont
    for nome in ("arialbd.ttf", "arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(nome, tam)
        except Exception:
            continue
    return ImageFont.load_default()


def _quebrar(draw, texto, fonte, larg_max):
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        teste = (atual + " " + p).strip()
        try:
            w = draw.textbbox((0, 0), teste, font=fonte)[2]
        except Exception:
            w = len(teste) * fonte.size * 0.5
        if w <= larg_max or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


def _txt_png(texto, banda):
    """banda: 'hook' (topo) | 'caption' (centro-baixo) | 'cta' (rodapé)."""
    from PIL import Image, ImageDraw
    cfg = {
        "hook":    dict(size=94, y_frac=0.18, fill=(255, 255, 255), wmax=0.86),
        "caption": dict(size=72, y_frac=0.66, fill=(255, 255, 0), wmax=0.90),
        "cta":     dict(size=70, y_frac=0.86, fill=(255, 255, 255), wmax=0.86),
    }[banda]
    img = Image.new("RGBA", (LARGURA_ALVO, ALTURA_ALVO), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fonte = _carregar_fonte(cfg["size"])
    larg_max = int(LARGURA_ALVO * cfg["wmax"])
    linhas = _quebrar(draw, (texto or "").upper() if banda != "caption" else texto,
                      fonte, larg_max)
    alt_linha = int(cfg["size"] * 1.18)
    total_h = alt_linha * len(linhas)
    y = int(ALTURA_ALVO * cfg["y_frac"]) - total_h // 2
    for ln in linhas:
        try:
            w = draw.textbbox((0, 0), ln, font=fonte)[2]
        except Exception:
            w = len(ln) * cfg["size"] * 0.5
        x = (LARGURA_ALVO - w) // 2
        draw.text((x, y), ln, font=fonte, fill=cfg["fill"],
                  stroke_width=6, stroke_fill=(0, 0, 0))
        y += alt_linha
    return np.array(img)


def _overlay(ImageClip, png_arr, inicio, dur):
    try:
        ic = ImageClip(png_arr, transparent=True)
    except TypeError:
        ic = ImageClip(png_arr)
    return _clip_timing(ic, dur=max(0.2, dur), start=max(0.0, inicio), pos=(0, 0))


# ══════════════════════════════════════════════════════════════════════════
# NARRAÇÃO  (roda no thread do executor → asyncio.run interno é seguro)
# ══════════════════════════════════════════════════════════════════════════
def _produzir_narracao(produto, plano, slug, destino_dir):
    """Retorna (mp3_path|None, frases, dur_aprox, word_boundaries)."""
    if not (CFG_NARRACAO_NOVA and _NARR_OK and _TTS_OK):
        return None, [], 0.0, []
    construir_roteiro, estimar = _NARR
    gerar_narracao, _bp, edge_ok = _TTS
    try:
        if callable(edge_ok) and not edge_ok():
            log.warning("Edge-TTS indisponível; vídeo seguirá sem narração própria.")
            return None, [], 0.0, []
        roteiro = construir_roteiro(produto, plano=plano)
        frases = roteiro.get("frases", []) or []
        texto = roteiro.get("texto_completo") or " ".join(frases)
        if not texto.strip():
            return None, [], 0.0, []
        dur_estimada = sum(estimar(f) for f in frases) if frases else 0.0
        mp3 = destino_dir / f"narr_{slug}.mp3"
        res = gerar_narracao(texto, mp3, voz=VOZ_NARRACAO,
                             dur_minima_esperada=dur_estimada)
        if not res.get("sucesso"):
            log.warning(f"Narração falhou: {res.get('erro')}")
            return None, [], 0.0, []
        return (Path(res["arquivo"]), frases,
                float(res.get("dur_aprox") or dur_estimada),
                res.get("word_boundaries") or [])
    except Exception:
        log.exception("Erro ao produzir narração")
        return None, [], 0.0, []


# ══════════════════════════════════════════════════════════════════════════
# INTRO DE IA opcional  [L6]
# ══════════════════════════════════════════════════════════════════════════
def _gerar_intro_ia(plano):
    if not (CFG_INTRO_IA and _VPROV_OK):
        return None
    try:
        res = _VPROV(plano, provider=CFG_INTRO_IA_PROVIDER)
        if isinstance(res, dict):
            caminho = res.get("arquivo") or res.get("video_path") or res.get("path")
            if caminho and Path(caminho).exists():
                log.info(f"Intro de IA gerada por {CFG_INTRO_IA_PROVIDER}: {caminho}")
                return Path(caminho)
        log.warning(f"Intro de IA não produziu arquivo válido: {res}")
    except Exception:
        log.exception("Falha na intro de IA")
    return None


# ══════════════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL DE RE-PRODUÇÃO (sync → roda no executor)
# ══════════════════════════════════════════════════════════════════════════
def _reproduzir_video_sync(src: Path, dst: Path, produto: str,
                           nome_produto: str, plano: dict) -> dict:
    if not MOVIEPY_OK:
        return {"sucesso": False, "erro": "MoviePy ausente"}

    slug = _slugify(produto)
    (VideoFileClip, AudioFileClip, ImageClip,
     CompositeVideoClip, concatenate_videoclips) = _import_moviepy()

    abertos = []  # pra fechar tudo no fim
    narr_path = None
    try:
        # 1) NARRAÇÃO própria (substitui áudio saturado) ───────────────────
        narr_path, frases, narr_dur, wbounds = _produzir_narracao(
            produto, plano, slug, src.parent)

        # 2) Carrega fonte, aplica velocidade e define duração-alvo ─────────
        base = VideoFileClip(str(src))
        abertos.append(base)
        if CFG_VELOCIDADE and CFG_VELOCIDADE != 1.0:
            base = _aplicar_velocidade(base, CFG_VELOCIDADE)
        dur_src = float(base.duration or CFG_DUR_MAX)
        if narr_dur > 0:
            alvo = min(dur_src, narr_dur + 0.8, CFG_DUR_MAX)
        else:
            alvo = min(dur_src, CFG_DUR_MAX)
        alvo = max(2.0, round(alvo, 2))
        base = _subclip(base, 0, min(alvo, dur_src))

        # 3) 9:16 → reframe → efeitos de diferenciação ─────────────────────
        base = _ajustar_para_vertical(base)
        base = _aplicar_reframe(base, CFG_REFRAME_ZOOM)
        base = _aplicar_efeitos_diferenciacao(base)  # [FIX-2]

        # 4) ÁUDIO: narração (+ original baixo + trilha opcional) ──────────
        tracks = []
        if narr_path and Path(narr_path).exists():
            a_narr = AudioFileClip(str(narr_path))
            abertos.append(a_narr)
            a_narr = _subclip(a_narr, 0, min(alvo, float(a_narr.duration or alvo)))
            tracks.append(a_narr)
        if CFG_AUDIO_ORIGINAL_VOL > 0 and base.audio is not None:
            tracks.append(_vol(base.audio, CFG_AUDIO_ORIGINAL_VOL))
        musica = plano.get("musica_fundo")
        if musica and Path(musica).exists():
            try:
                a_mus = AudioFileClip(str(musica))
                abertos.append(a_mus)
                a_mus = _subclip(a_mus, 0, min(alvo, float(a_mus.duration or alvo)))
                tracks.append(_vol(a_mus, CFG_MUSICA_FUNDO_VOL))
            except Exception:
                log.exception("Trilha de fundo ignorada")

        if tracks:
            try:
                base = _set_audio(base, _composite_audio(tracks))
            except Exception:
                log.exception("Mixagem de áudio falhou; mantendo original.")

        # 5) OVERLAYS: legendas + TEMPLATE DE MARCA TopShop ────────────────
        overlays = []
        # 5a) Legendas da fala (mantém — sincronizadas com a narração)
        try:
            if CFG_LEGENDAS and frases and _TTS_OK:
                _g, boundaries_para_blocos, _e = _TTS
                blocos = boundaries_para_blocos(frases, wbounds, narr_dur or alvo)
                for b in blocos:
                    ini = float(b.get("inicio_seg", 0))
                    fim = float(b.get("fim_seg", ini))
                    txt = b.get("texto", "")
                    if not txt or ini >= alvo:
                        continue
                    fim = min(fim, alvo)
                    overlay_item = _overlay(ImageClip, _txt_png(txt, "caption"), ini, max(0.4, fim - ini))
                    if overlay_item:
                        overlays.append(overlay_item)
        except Exception:
            log.exception("Legendas parcialmente ignoradas")

        # 5b) TEMPLATE DE MARCA TopShop — reusa as camadas prontas do
        # narrated_video_agent (logo TS + nome + @handle + selo + hook + CTA
        # com emojis), pra o hunter ter a MESMA identidade fixa.
        _marca_ok = False
        try:
            from agents.narrated_video_agent import (
                _criar_camadas_topo, _criar_cta_fixo,
                _import_moviepy as _brand_mp_import)
            _mp_brand = _brand_mp_import()   # 7-tuple (inclui ColorClip, TextClip)
            hook_txt = (_HOOK[0](nome_produto, plano=plano)
                        if _HOOK_OK else "OLHA ISSO")
            for camada in _criar_camadas_topo(alvo, hook_txt, _mp_brand):
                if camada is not None:
                    overlays.append(camada)
            for camada in _criar_cta_fixo(alvo, _mp_brand):
                if camada is not None:
                    overlays.append(camada)
            _marca_ok = True
            log.info("🏷️  Template de marca TopShop aplicado no hunter")
        except Exception:
            log.exception("Template de marca falhou; caindo pro hook/CTA simples")

        # 5c) Fallback: se a marca falhou, usa o hook/CTA simples (antigo)
        if not _marca_ok:
            try:
                if CFG_HOOK_OVERLAY:
                    _hk = (_HOOK[0](nome_produto, plano=plano)
                           if _HOOK_OK else "Olha isso!")
                    _oi = _overlay(ImageClip, _txt_png(_hk, "hook"), 0.0, min(CFG_HOOK_SEG, alvo))
                    if _oi:
                        overlays.append(_oi)
                if CFG_CTA_FINAL:
                    _ct = _HOOK[1](nome_produto) if _HOOK_OK else "Link na Bio! 🛒"
                    _ini = max(0.0, alvo - CFG_CTA_SEG)
                    _oi = _overlay(ImageClip, _txt_png(_ct, "cta"), _ini, alvo - _ini)
                    if _oi:
                        overlays.append(_oi)
            except Exception:
                log.exception("Overlays de fallback também falharam")

        # 5.5) LAYOUT TopShop: reduz o vídeo pra 3:4 e centraliza num canvas
        # 9:16 (fundo da marca), deixando faixa preta em cima (marca+hook) e
        # embaixo (CTA) — igual aos vídeos do narrated_video_agent.
        _narr_audio = base.audio
        try:
            from agents.narrated_video_agent import (
                _import_moviepy as _brand_mp_import, _brand_asset)
            _ColorClip = _brand_mp_import()[5]

            # fundo: brand fundo.png se existir, senão quase-preto
            _fp = _brand_asset("fundo.png")
            if _fp is not None:
                _fundo_bg = _resize_clip(ImageClip(str(_fp)), (LARGURA_ALVO, ALTURA_ALVO))
            else:
                _fundo_bg = _ColorClip(size=(LARGURA_ALVO, ALTURA_ALVO), color=(12, 12, 16))
            _fundo_bg = _clip_timing(_fundo_bg, dur=alvo, start=0.0, pos=("center", "center"))
            abertos.append(_fundo_bg)

            # vídeo reduzido pra 3:4 (95% da largura), centralizado
            _larg_v = int(LARGURA_ALVO * 0.95)                       # 1026
            _alt_full = int(_larg_v * ALTURA_ALVO / LARGURA_ALVO)    # 9:16 escalado
            _alt_v = int(_larg_v * 4 / 3)                            # 3:4
            _vid = _resize_clip(base, (_larg_v, _alt_full))
            _yc = max(0, (_alt_full - _alt_v) // 2)
            _vid = _crop_clip(_vid, x1=0, x2=_larg_v, y1=_yc, y2=_yc + _alt_v)
            _vid = _clip_timing(_vid, pos=("center", "center"))
            abertos.append(_vid)

            clip_final = CompositeVideoClip([_fundo_bg, _vid, *overlays],
                                            size=(LARGURA_ALVO, ALTURA_ALVO))
            clip_final = _set_audio(clip_final, _narr_audio)   # preserva a narração
        except Exception:
            log.exception("Layout 3:4 falhou; usando vídeo em tela cheia")
            clip_final = CompositeVideoClip([base, *overlays]) if overlays else base
        abertos.append(clip_final)

        # 6) INTRO de IA opcional (prefixa) ────────────────────────────────
        intro_path = _gerar_intro_ia(plano)
        if intro_path:
            try:
                intro = VideoFileClip(str(intro_path))
                abertos.append(intro)
                intro = _subclip(intro, 0, min(CFG_INTRO_DUR, float(intro.duration or CFG_INTRO_DUR)))
                intro = _ajustar_para_vertical(intro)
                clip_final = concatenate_videoclips([intro, clip_final], method="compose")
                abertos.append(clip_final)
            except Exception:
                log.exception("Concatenação da intro falhou; seguindo sem.")

        # 7) Escrita com metadados limpos + faststart ─────────────────────
        dst.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg_params = []
        if CFG_LIMPAR_META:
            ffmpeg_params += ["-map_metadata", "-1"]
        ffmpeg_params += ["-movflags", "+faststart"]
        kwargs = dict(codec="libx264", audio_codec="aac", fps=30,
                      logger=None, ffmpeg_params=ffmpeg_params)
        try:
            clip_final.write_videofile(str(dst), threads=4, preset="ultrafast", **kwargs)
        except TypeError:
            clip_final.write_videofile(str(dst), **kwargs)

        log.info(f"Vídeo re-produzido: {dst.name} "
                 f"(narração={'sim' if narr_path else 'não'}, "
                 f"overlays_ativos={len(overlays)}, dur={alvo}s)")
        return {"sucesso": True, "narracao": bool(narr_path),
                "duracao": alvo, "frases": frases}
    except Exception:
        log.exception("Erro na re-produção")
        return {"sucesso": False, "erro": "erro interno"}
    finally:
        for c in abertos:
            try:
                c.close()
            except Exception:
                pass
        if narr_path and Path(narr_path).exists():
            try:
                Path(narr_path).unlink()
            except Exception:
                pass


async def reproduzir_video(src: Path, dst: Path, produto: str,
                           nome_produto: str, plano: dict) -> dict:
    loop = asyncio.get_running_loop()  # [FIX-B]
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(_RENDER_EXECUTOR, _reproduzir_video_sync,
                                 src, dst, produto, nome_produto, plano),
            timeout=VIDEO_TIMEOUT,
        )
    except asyncio.TimeoutError:
        log.error(f"Timeout ({VIDEO_TIMEOUT}s) na re-produção de {src.name}")
        return {"sucesso": False, "erro": "timeout"}


# ══════════════════════════════════════════════════════════════════════════
# FLUXO POR MENSAGEM
# ══════════════════════════════════════════════════════════════════════════
def _limpar_links_terceiros(texto: str) -> str:
    """Remove links (http/https) ou menções a outros canais."""
    if not texto:
        return ""
    texto_limpo = re.sub(r'https?://\S+', '', texto)
    texto_limpo = re.sub(r'@\S+', '', texto_limpo)
    return re.sub(r' +', ' ', texto_limpo).strip()


# Link da Shopee que costuma vir na própria mensagem (curto ou normal, com ou
# sem http:// na frente).
_SHOPEE_LINK_RE = re.compile(
    r'(?:https?://)?(?:s\.shopee\.com\.br|shope\.ee|shopee\.com\.br)/\S+', re.I)


def _extrair_link_shopee(texto: str):
    """Acha o 1º link da Shopee na mensagem (curto s.shopee/shope.ee ou normal).
    É mais confiável do que re-buscar o produto pelo nome (que às vezes falha)."""
    if not texto:
        return None
    m = _SHOPEE_LINK_RE.search(texto)
    if not m:
        return None
    url = m.group(0).rstrip('.,);]}"\'')
    if not url.lower().startswith("http"):
        url = "https://" + url
    return url


def _resolver_link_shopee(url: str):
    """Segue o redirect do link curto -> URL limpa do produto (sem query de
    tracking de terceiro). Best-effort: se não resolver, retorna None."""
    try:
        import requests
        r = requests.get(url, allow_redirects=True, timeout=12,
                         headers={"User-Agent": "Mozilla/5.0 (Linux; Android 10)"})
        final = (r.url or "").split("?")[0]
        if "shopee.com.br" in final and final.rstrip("/") != url.rstrip("/"):
            return final
    except Exception:
        log.debug("Não consegui resolver o link curto da Shopee (usa fallback).")
    return None


async def processar_mensagem_telegram(msg, sub_id: str = "hunter_radar"):
    if not getattr(msg, "text", None):
        return None

    # NOVO: o link da Shopee normalmente JÁ vem na mensagem. Usar ele é bem
    # mais confiável do que re-buscar o produto pelo NOME (que falha quando o
    # nome não bate na busca) — era por isso que muitos produtos eram perdidos.
    link_na_msg = _extrair_link_shopee(msg.text)

    # limpeza preliminar de links/menções (só pra extrair o NOME do produto)
    texto_para_extracao = _limpar_links_terceiros(msg.text)
    termo = extrair_termo_produto(texto_para_extracao)
    if not termo:
        log.warning("Nenhum termo de produto extraído. Ignorando.")
        return None
    log.info(f"Termo do produto: {termo!r}")
    atualizar_produto(termo, status="processando", origem="telegram_hunter")

    url_shopee = None
    mineracao = {}

    # 1a) PREFERIDO: link que veio na própria mensagem (resolve curto -> produto)
    if link_na_msg:
        url_shopee = _resolver_link_shopee(link_na_msg) or link_na_msg
        log.info(f"Link da mensagem -> {url_shopee}")

    # 1b) FALLBACK: minera por nome (só se a mensagem não trouxe link)
    if not url_shopee:
        try:
            mineracao = minerar_oportunidades(termo)
        except Exception:
            log.exception("Erro na mineração Shopee")
            atualizar_produto(termo, status="erro", erro="falha mineração")
            return None
        if not mineracao.get("ok") or not mineracao.get("campeao"):
            log.warning(f"{termo!r} não localizado na Shopee (e sem link na msg).")
            atualizar_produto(termo, status="erro", erro="não localizado na Shopee")
            return None
        campeao = mineracao["campeao"]
        url_shopee = campeao.get("product_link") or campeao.get("offer_link")

    if not url_shopee:
        atualizar_produto(termo, status="erro", erro="sem URL Shopee")
        return None

    # gerar link de afiliado
    # A Shopee REJEITA sub_id com caractere especial (erro 11001 "invalid sub
    # id"). Limpa pra só alfanumérico (igual o radar faz), senão o link vem
    # vazio e o produto é descartado antes de virar vídeo.
    _subs = [re.sub(r"[^A-Za-z0-9]", "", s)[:16] for s in (sub_id, "telegramrepurpose") if s]
    _subs = [s for s in _subs if s] or ["hunter"]
    try:
        res_link = gerar_link_afiliado(url_shopee, sub_ids=_subs)
        if isinstance(res_link, dict):
            meu_link = res_link.get("link") or res_link.get("short_link") or ""
        else:
            meu_link = str(res_link or "")
    except Exception:
        log.exception("Erro ao gerar link de afiliado")
        meu_link = ""

    # fallback apenas se gerar_link_afiliado falhar
    if not meu_link:
        meu_link = mineracao.get("link_gerado") or ""
    if not meu_link:
        log.error("Link de afiliado vazio.")
        atualizar_produto(termo, status="erro", erro="link de afiliado vazio")
        return None
    log.info(f"Link gerado: {meu_link}")

    # 2) Download do criativo (retry)
    slug = _slugify(termo)
    INBOX_VIDEOS.mkdir(parents=True, exist_ok=True)
    video_tmp   = INBOX_VIDEOS / f"temp_{slug}.mp4"
    video_final = INBOX_VIDEOS / f"{slug}.mp4"

    baixou = False
    for tent in range(1, 4):
        try:
            log.info(f"Download (tentativa {tent}/3)...")
            await msg.download_media(file=str(video_tmp))
            if video_tmp.exists() and video_tmp.stat().st_size > 0:
                baixou = True
                break
            log.warning(f"Tentativa {tent}: arquivo vazio/ausente.")
        except Exception:
            log.exception(f"Tentativa {tent} falhou")
        if tent < 3:
            await asyncio.sleep(3)
    if not baixou:
        log.error("Download falhou após 3 tentativas.")
        atualizar_produto(termo, status="erro", erro="falha no download")
        return None

    # 3) Monta plano parcial (pra hook/roteiro/legenda usarem contexto)
    nome_produto = campeao.get("nome", termo)
    preco = tratar_preco(campeao.get("preco", 0))
    hook_preview = (_HOOK[0](nome_produto, plano={}) if _HOOK_OK else "Olha isso!")

    plano = {
        "produto":        nome_produto,
        "titulo_real":    nome_produto,
        "preco_real":     preco,
        "link_afiliado":  meu_link,
        "musica_fundo":   "",
        "hook":           hook_preview,
    }

    # 4) RE-PRODUÇÃO com camadas de conteúdo
    resultado = {"sucesso": False}
    try:
        resultado = await reproduzir_video(video_tmp, video_final,
                                           termo, nome_produto, plano)
    finally:
        if video_tmp.exists():
            try:
                video_tmp.unlink()
                log.debug(f"Temp removido: {video_tmp.name}")
            except Exception:
                log.exception("Falha ao remover temp")

    if not resultado.get("sucesso"):
        atualizar_produto(termo, status="erro",
                          erro=f"re-produção: {resultado.get('erro')}")
        return None

    # 5) Legenda + hashtags dinâmicas + descrições por plataforma
    categoria = ""
    if _NARR_OK:
        try:
            from creative_engine.narration_script_builder import _categoria_do_produto
            categoria = _categoria_do_produto(nome_produto) or ""
        except Exception:
            log.debug("Não foi possível determinar categoria via narration_script_builder")

    legenda = _legenda_dinamica(nome_produto, hook_preview)
    hashtags = _hashtags_para(categoria)

    plano.update({
        "video_path_sugerido": str(video_final),
        "roteiro_narrado":     resultado.get("frases", []),
        "legenda":             legenda,
        "hashtags":            hashtags,
        "cta":                 (_HOOK[1](nome_produto) if _HOOK_OK else "Link na Bio!"),
        # [FIX-9] chaves canônicas que o resto do projeto lê
        # (autonomous_orchestrator, publicadores, finalizar_plano):
        "narracao":            resultado.get("narracao", False),
        "duracao":             resultado.get("duracao"),
        # aliases descritivos mantidos por compatibilidade retroativa
        "narracao_propria":    resultado.get("narracao", False),
        "duracao_video":       resultado.get("duracao"),
        "categoria":           categoria,
        "status_producao":     "video_gerado",
    })

    if _DESC_OK:
        try:
            montar_todas, _md = _DESC
            descs = montar_todas(plano, ["tiktok", "youtube", "instagram"])
            plano["descricoes"] = {p: d.get("descricao", "") for p, d in descs.items()}
        except Exception:
            log.exception("montar_todas falhou")

    # 6) Persiste plano (atômico) + registra na esteira
    try:
        SHARED_PLANS.mkdir(parents=True, exist_ok=True)
        _salvar_json_atomico(SHARED_PLANS / f"plano_{slug}.json", plano)
        _salvar_json_atomico(SHARED_PLANS / "ultimo_plano.json", plano)
        atualizar_produto(
            termo, status="video_gerado", nome_real=nome_produto,
            ultimo_video=str(video_final), link_afiliado=meu_link,
            quality_gate="aprovado", origem="telegram_hunter",
        )
        log.info("Plano gravado e produto registrado na esteira.")
    except Exception:
        log.exception("Falha ao persistir plano")

    # 7) PONTE PRA ESTEIRA — copia o vídeo re-produzido pra
    # pronto_para_postar/<slug>/ (mesmo slug do plano_<slug>.json), que é de
    # onde o daemon posta. Sem isso o vídeo do hunter ficava só em
    # assets/inbox e nunca era postado.
    try:
        import shutil
        pp_dir = BASE_DIR / "pronto_para_postar" / slug
        pp_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(video_final), str(pp_dir / "video.mp4"))
        # IG/FB usam a legenda do plano; o YouTube lê estes .txt daqui:
        _hashtags_txt = plano.get("hashtags", "") or ""
        (pp_dir / "titulo_youtube.txt").write_text(
            (f"{nome_produto} #shorts")[:100], encoding="utf-8")
        (pp_dir / "descricao_youtube.txt").write_text(
            ((plano.get("legenda", "") or "") + "\n\n" + _hashtags_txt).strip(),
            encoding="utf-8")
        (pp_dir / "hashtags.txt").write_text(_hashtags_txt, encoding="utf-8")
        log.info(f"🚚 Esteira abastecida: {pp_dir / 'video.mp4'}")
    except Exception:
        log.exception("Falha ao abastecer pronto_para_postar")

    return plano


# ══════════════════════════════════════════════════════════════════════════
# Providers externos (Facebook Ad Library, TikTok Creative Center)
# Cada função retorna lista de creatives normalizados:
#   {id, video_url, text, source, meta}
# ══════════════════════════════════════════════════════════════════════════
def fetch_facebook_creatives(query: str, region: str = "BR",
                             access_token: str = None, limit: int = 20):
    """
    Consulta a Ad Library (ads_archive).

    IMPORTANTE: a Ad Library NÃO expõe uma URL direta de vídeo/MP4 — apenas
    `ad_snapshot_url` (uma página de snapshot). Portanto os itens retornados
    aqui vêm com `video_url` vazio e serão ignorados pelo pipeline de vídeo;
    servem como inteligência/tendência (texto), não como fonte de mídia.
    """
    out = []
    if not access_token:
        log.warning("FACEBOOK_ACCESS_TOKEN ausente; pulando Facebook fetch.")
        return out
    try:
        endpoint = "https://graph.facebook.com/v21.0/ads_archive"
        params = {
            "search_terms": query,
            "ad_reached_countries": json.dumps([region]),
            "ad_type": "ALL",
            "fields": ("id,ad_creative_bodies,ad_creative_link_captions,"
                       "ad_snapshot_url,page_name,publisher_platforms"),
            "limit": limit,
            "access_token": access_token,
        }
        r = _HTTP.get(endpoint, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        registros = data.get("data", []) or []
        for itm in registros[:limit]:
            bodies = itm.get("ad_creative_bodies") or []
            text = bodies[0] if bodies else ""
            cid = itm.get("id") or str(time.time())
            out.append({
                "id": str(cid),
                "video_url": "",  # Ad Library não fornece MP4 direto
                "text": text,
                "source": "facebook",
                "meta": {
                    "ad_snapshot_url": itm.get("ad_snapshot_url", ""),
                    "page_name": itm.get("page_name", ""),
                    "raw": itm,
                },
            })
        if registros:
            log.info(f"Facebook Ad Library: {len(registros)} anúncios (sem MP4 direto; "
                     "só ad_snapshot_url).")
    except Exception:
        log.exception("Erro fetch_facebook_creatives")
    return out


def fetch_tiktok_creatives(query: str, region: str = "BR", limit: int = 20):
    # Placeholder: o Creative Center do TikTok costuma embutir JSON na página ou
    # ter endpoints internos. Implementação robusta exige investigar a página
    # real; aqui tentamos um scraping leve se bs4 estiver presente.
    out = []
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception:
        log.warning("BeautifulSoup não disponível; pulando TikTok fetch. "
                    "Instale 'beautifulsoup4' para habilitar.")
        return out

    try:
        search_url = (f"https://ads.tiktok.com/creative_center/search/"
                      f"?q={requests.utils.quote(query)}&region={region}")
        r = _HTTP.get(search_url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # NOTE: selectors abaixo são ilustrativos. Ajuste conforme a estrutura
        # atual do Creative Center.
        cards = soup.select(".video-card") or soup.select(".creative-card")
        for c in cards[:limit]:
            try:
                vid = c.select_one("video")
                video_url = vid['src'] if vid and vid.has_attr('src') else ""
                caption = c.get_text(strip=True)[:400]
                cid = c.get("data-id") or c.get("id") or str(time.time())
                if video_url:
                    out.append({
                        "id": str(cid),
                        "video_url": video_url,
                        "text": caption,
                        "source": "tiktok",
                        "meta": {},
                    })
            except Exception:
                continue
    except Exception:
        log.exception("Erro fetch_tiktok_creatives")
    return out


class PseudoMsg:
    """Objeto compatível com processar_mensagem_telegram:
    .text, .id, async download_media(file=...)."""
    def __init__(self, creative):
        self.creative = creative
        self.text = creative.get("text") or ""
        self.id = creative.get("id")
        self.video_url = creative.get("video_url")

    async def download_media(self, file: str):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._download_sync, file)

    def _download_sync(self, file):
        if not self.video_url:
            raise ValueError("creative sem video_url")
        p = Path(file)
        try:
            resp = _HTTP.get(self.video_url, stream=True, timeout=30)
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "")
            if ctype and not (ctype.startswith("video/")
                              or ctype == "application/octet-stream"):
                log.warning(f"Content-Type inesperado ({ctype}) para {self.video_url}")
            p.parent.mkdir(parents=True, exist_ok=True)
            total = 0
            with p.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise ValueError(
                            f"arquivo excede limite de {MAX_DOWNLOAD_BYTES} bytes")
                    fh.write(chunk)
            return str(p)
        except Exception:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass
            log.exception(f"Falha ao baixar {self.video_url}")
            raise


async def varrer_provedores(query: str, providers=("facebook", "tiktok"),
                            region="BR", limit: int = 20):
    log.info(f"Varredura de provedores para query={query} "
             f"providers={providers} limit={limit}")
    loop = asyncio.get_running_loop()
    all_creatives = []
    for prov in providers:
        try:
            if prov == "facebook":
                # [FIX-4] fetch síncrono roda em executor (não bloqueia o loop)
                creatives = await loop.run_in_executor(
                    None,
                    functools.partial(fetch_facebook_creatives, query,
                                      region=region,
                                      access_token=FACEBOOK_ACCESS_TOKEN,
                                      limit=limit),
                )
            elif prov == "tiktok":
                creatives = await loop.run_in_executor(
                    None,
                    functools.partial(fetch_tiktok_creatives, query,
                                      region=region, limit=limit),
                )
            else:
                log.warning(f"Provedor desconhecido: {prov}")
                creatives = []
        except Exception:
            log.exception(f"Erro ao buscar creatives do provedor {prov}")
            creatives = []
        all_creatives.extend(creatives)

    processed = 0
    for creative in all_creatives:
        canal = creative.get("source", "provider")
        cid = creative.get("id")
        if not creative.get("video_url"):
            log.debug(f"Creative {cid} de {canal} sem video_url; pulando.")
            continue
        try:
            if _deve_pular(canal, cid):
                log.debug(f"Creative {cid} de {canal} já tratado; pulando.")
                continue
            pseudo = PseudoMsg(creative)
            plano = await processar_mensagem_telegram(pseudo, sub_id=f"provider_{canal}")
            if plano:
                _marcar_processado(canal, cid)
                processed += 1
            else:
                _registrar_falha(canal, cid)
        except Exception:
            log.exception(f"Erro ao processar creative {cid} de {canal}")
            _registrar_falha(canal, cid)
        await asyncio.sleep(1)  # pequeno delay para reduzir taxa de requests
    log.info(f"Varredura de provedores concluída. {processed} items processados.")


# ══════════════════════════════════════════════════════════════════════════
# VARREDURA DO CANAL (com dedup)
# ══════════════════════════════════════════════════════════════════════════
async def varrer_canal_por_criativos(canal_username: str, limite: int = 50):
    ok, motivo = _validar_credenciais()
    if not ok:
        log.error(f"Credenciais inválidas: {motivo}")
        return

    log.info(f"Sessão Telethon -> {canal_username} (Varrendo até {limite} mensagens...)")

    async with TelegramClient(str(SESSION_PATH), int(_API_ID_RAW), _API_HASH) as client:
        try:
            entidade = await client.get_input_entity(canal_username)

            count = 0
            async for msg in client.iter_messages(entidade, limit=limite):
                # [FIX-10] aceita vídeo nativo E vídeo enviado como documento/arquivo
                # (canais de achadinhos às vezes mandam o .mp4 "como arquivo",
                # que não vem em msg.video mas tem mime_type video/*).
                _mime = getattr(getattr(msg, "file", None), "mime_type", "") or ""
                if not (msg.video or _mime.startswith("video/")):
                    continue

                texto_analise = msg.text or ""
                if not texto_analise and getattr(msg, "buttons", None):
                    try:
                        texto_analise = " ".join([b.text for row in msg.buttons for b in row])
                    except Exception:
                        texto_analise = ""

                if _deve_pular(canal_username, msg.id):
                    log.debug(f"Msg {msg.id} já tratada; pulando.")
                    continue

                try:
                    plano = await processar_mensagem_telegram(msg)
                    if plano:
                        _marcar_processado(canal_username, msg.id)
                        count += 1
                    else:
                        _registrar_falha(canal_username, msg.id)
                except Exception:
                    log.exception(f"Erro mensagem ID {getattr(msg, 'id', None)}")
                    _registrar_falha(canal_username, msg.id)

                await asyncio.sleep(3)  # Delay saudável para evitar bloqueio do Telegram

            log.info(f"Varredura concluída. {count} novos vídeos processados.")
        except Exception:
            log.exception(f"Erro no canal {canal_username!r}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jarvis Repurpose Hunter (rev 5)")
    parser.add_argument("--canal",  help="@canal_alvo")
    parser.add_argument("--limite", type=int, default=3)
    parser.add_argument("--fontes", help="Lista de fontes separadas por vírgula: facebook,tiktok")
    parser.add_argument("--query", help="Query para varrer provedores (ex: 'achadinhos shopee')")
    args = parser.parse_args()
    log.info("Iniciando Módulo de Captura e Re-produção de Conteúdo...")
    try:
        if args.fontes and args.query:
            providers = [p.strip() for p in args.fontes.split(",") if p.strip()]
            asyncio.run(varrer_provedores(args.query, providers=providers, limit=args.limite))
        elif args.canal:
            asyncio.run(varrer_canal_por_criativos(args.canal, args.limite))
        else:
            log.error("Nenhum alvo informado. Use --canal @canal "
                      "ou --fontes facebook,tiktok --query '...'")
    except KeyboardInterrupt:
        log.info("Encerrado manualmente pelo usuário.")
    except Exception:
        log.exception("Erro fatal no runner")
    finally:
        _RENDER_EXECUTOR.shutdown(wait=True)
