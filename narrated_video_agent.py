# agents/narrated_video_agent.py
# Narrated Video Engine v1 do AgenteIA (Jarvis).
#
# Engine PARALELA ao Product Video Editor (CapCut). Em vez de cenas curtas com
# texto na tela, esta engine faz VÍDEO NARRADO:
#   roteiro curto → voz (Edge-TTS, grátis) → B-roll de fundo → legenda → MP4
#
# Por que existe: custo ~zero. PixVerse/HeyGen gastam crédito; esta engine usa
# Edge-TTS (grátis) + B-roll que o produto já tem + MoviePy. Dá VOLUME barato.
#
# Fluxo:
#   1. Lê plano + detecta categoria
#   2. Gera roteiro narrado de 12-18s (template determinístico por categoria)
#   3. Gera narração MP3 com Edge-TTS (+ word boundaries pra legenda)
#   4. Seleciona B-roll: 1º o que o produto já tem (raw/), senão avisa
#   5. Monta vídeo vertical 9:16 com MoviePy (B-roll em loop + narração)
#   6. Legenda por blocos de frase (sincronizada via boundaries)
#   7. Salva videos/<slug>_narrated.mp4
#   8. Registra memória
#
# NÃO usa Whisper (v1): legenda por frase, timing via word boundaries do Edge-TTS.
#
# CLI:
#   python -m agents.narrated_video_agent --produto "Cinto Modelador Slim Feminino"
#   python -m agents.narrated_video_agent --produto "X" --dry-run
#   python -m agents.narrated_video_agent --produto "X" --voz pt-BR-AntonioNeural

import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from shared.logger import get_logger
from agents.asset_agent import slugificar_produto

from creative_engine.narration_script_builder import (
    construir_roteiro, estimar_duracao_frase,
)
from creative_engine.tts_edge import (
    gerar_narracao, boundaries_para_blocos,
    edge_tts_disponivel, motivo_indisponivel, VOZ_PADRAO,
)

# Memória (best-effort)
# [FIX] memory_agent NÃO expõe 'registrar_aprendizado' (só existe
# 'registrar_memoria' / 'registrar_aprendizado_execucao'). O import antigo
# falhava sempre → _MEM_OK=False → memória NUNCA era registrada em silêncio.
try:
    from agents.memory_agent import registrar_memoria
    _MEM_OK = True
except Exception:
    _MEM_OK = False

log = get_logger(__name__)

PROJETO_ROOT  = Path(__file__).parent.parent
PRODUTOS_ROOT = PROJETO_ROOT / "assets" / "produtos"
PLANS_DIR     = PROJETO_ROOT / "shared" / "content_plans"
VIDEOS_DIR    = PROJETO_ROOT / "videos"
TMP_DIR       = PROJETO_ROOT / "videos" / "_tmp_narrated"

LARGURA, ALTURA = 1080, 1920   # canvas 9:16 (vídeo 3:4 reduzido fica centralizado dentro)
# Template de marca topshop — liga/desliga e textos. Carimba identidade no vídeo.
TEMPLATE_MARCA = True
MARCA_NOME = "TopShop"
MARCA_HANDLE = os.environ.get("TOPSHOP_HANDLE", "@topshop._")
# Pasta com os assets de marca (logo, fundo, selo, fontes)
BRAND_DIR = PROJETO_ROOT / "assets" / "brand"
EXT_VIDEO = {".mp4", ".mov", ".webm", ".m4v"}
EXT_IMG   = {".jpg", ".jpeg", ".png", ".webp"}


# =================================================================
# MOVIEPY IMPORT (compat v1/v2 — mesmo padrão do renderer)
# =================================================================

def _import_moviepy():
    try:
        from moviepy import (VideoFileClip, AudioFileClip, ImageClip,
                              CompositeVideoClip, concatenate_videoclips,
                              ColorClip, TextClip)
    except ImportError:
        from moviepy.editor import (VideoFileClip, AudioFileClip, ImageClip,
                                     CompositeVideoClip, concatenate_videoclips,
                                     ColorClip, TextClip)
    return (VideoFileClip, AudioFileClip, ImageClip,
            CompositeVideoClip, concatenate_videoclips, ColorClip, TextClip)


def _moviepy_disponivel() -> bool:
    try:
        _import_moviepy()
        return True
    except Exception:
        return False


def _with_duration(clip, dur):
    return clip.with_duration(dur) if hasattr(clip, "with_duration") else clip.set_duration(dur)


def _with_audio(clip, audio):
    return clip.with_audio(audio) if hasattr(clip, "with_audio") else clip.set_audio(audio)


def _with_start(clip, t):
    return clip.with_start(t) if hasattr(clip, "with_start") else clip.set_start(t)


def _with_position(clip, pos):
    return clip.with_position(pos) if hasattr(clip, "with_position") else clip.set_position(pos)


def _with_opacity(clip, op):
    """Opacidade robusta entre versões. Se nenhuma API existir, retorna o clip."""
    try:
        if hasattr(clip, "with_opacity"):
            return clip.with_opacity(op)
        if hasattr(clip, "set_opacity"):
            return clip.set_opacity(op)
    except Exception:
        pass
    return clip


def _logo_circular(logo_path: Path, tam: int = 110) -> Optional[Path]:
    """
    Recorta o logo num círculo (PNG com transparência) e salva em tmp.
    O template do @topshop._ usa o logo TS redondo, não quadrado.
    Retorna o caminho do PNG circular, ou None se falhar (usa o original).
    """
    try:
        from PIL import Image, ImageDraw
        img = Image.open(str(logo_path)).convert("RGBA")
        img = img.resize((tam, tam), Image.LANCZOS)
        # máscara circular
        mask = Image.new("L", (tam, tam), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, tam, tam), fill=255)
        img.putalpha(mask)
        out = TMP_DIR / f"logo_circ_{logo_path.stem}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out))
        return out
    except Exception as e:
        log.warning(f"   ⚠️  Recorte circular do logo falhou ({e}) — usando original")
        return None


def _crop_centro(clip, larg, alt):
    """
    Corta o clip pro tamanho (larg x alt) pegando o CENTRO. Robusto entre
    versões do MoviePy (crop em moviepy.video.fx ou método .cropped/.crop).
    Se nada funcionar, retorna o clip original.
    """
    try:
        cx, cy = clip.w / 2, clip.h / 2
        x1 = int(cx - larg / 2); y1 = int(cy - alt / 2)
        x2 = int(cx + larg / 2); y2 = int(cy + alt / 2)
        # MoviePy v2: clip.cropped(...) | v1: clip.crop(...)
        if hasattr(clip, "cropped"):
            return clip.cropped(x1=x1, y1=y1, x2=x2, y2=y2)
        if hasattr(clip, "crop"):
            return clip.crop(x1=x1, y1=y1, x2=x2, y2=y2)
        # fallback: efeito Crop
        try:
            from moviepy.video.fx.Crop import Crop
            return clip.with_effects([Crop(x1=x1, y1=y1, x2=x2, y2=y2)])
        except Exception:
            pass
    except Exception as e:
        log.warning(f"   ⚠️  Crop central falhou ({e}) — vídeo sem corte 3:4")
    return clip


def _resize_clip(clip, largura=None, altura=None):
    """
    Redimensiona um clip pra uma largura OU altura alvo (mantém proporção).
    Robusto entre versões do MoviePy (resized/resize).
    """
    try:
        if largura is not None:
            alvo = largura / clip.w
        elif altura is not None:
            alvo = altura / clip.h
        else:
            return clip
        if hasattr(clip, "resized"):
            return clip.resized(alvo)
        if hasattr(clip, "resize"):
            return clip.resize(alvo)
    except Exception:
        pass
    return clip


# =================================================================
# PLANO + B-ROLL
# =================================================================

def carregar_plano_mais_recente(produto: str) -> Optional[dict]:
    if not PLANS_DIR.exists():
        return None
    import re
    slug = slugificar_produto(produto)
    re_ts = re.compile(r"_(\d{8})_(\d{6})$")
    cands = []
    for f in PLANS_DIR.glob("plano_*.json"):
        if "_resultado" in f.stem or f.name == "ultimo_plano.json":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if slugificar_produto(data.get("produto") or data.get("nome") or "") != slug:
            continue
        m = re_ts.search(f.stem.replace("plano_", "", 1))
        ts = None
        if m:
            try:
                ts = datetime.strptime(m.group(1)+m.group(2), "%Y%m%d%H%M%S")
            except Exception:
                pass
        if ts is None:
            try:
                ts = datetime.fromtimestamp(f.stat().st_mtime)
            except Exception:
                continue
        cands.append((ts, data))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0][1]


def _eh_cena_ia(nome: str) -> bool:
    """
    True se o arquivo é uma cena gerada por IA. Reconhece o marcador 'ia_'
    no início (ia_dor_x.mp4) OU após o prefixo de propósito que o hunter
    adiciona (dor_ia_dor_x.mp4). Evita falso positivo de 'social'/'especial'
    exigindo que 'ia_' esteja no começo ou logo após um '_'.
    """
    n = nome.lower()
    return n.startswith("ia_") or "_ia_" in n


def coletar_broll_existente(produto: str, so_ia: bool = False) -> list:
    """
    Retorna lista de caminhos de B-roll que o produto JÁ tem (raw/ + imagens/).
    Reusa o que existe (grátis). Não coleta nada novo.

    so_ia: se True, retorna SÓ os arquivos com prefixo 'ia_' (cenas geradas por
    IA). Útil quando o produto tem cenas de IA boas + lixo velho do Pexels
    acumulado (pata de cachorro, quadra de tênis...) — usa só as de IA, que são
    coerentes entre si e relevantes.
    """
    slug = slugificar_produto(produto)
    pasta = PRODUTOS_ROOT / slug
    arquivos = []
    for sub in ("raw", "imagens"):
        d = pasta / sub
        if d.exists():
            for f in sorted(d.iterdir()):
                if f.is_file() and f.suffix.lower() in (EXT_VIDEO | EXT_IMG):
                    if so_ia and not _eh_cena_ia(f.name):
                        continue  # pula tudo que não é cena de IA
                    arquivos.append(f)
    return arquivos


# =================================================================
# MAPEAMENTO FRASE → CENA → B-ROLL
# =================================================================

# Sequência canônica de cenas de um anúncio curto
SEQUENCIA_CENAS = ["dor", "demo", "close", "resultado", "cta"]


def mapear_frases_para_cenas(frases: list) -> list:
    """
    Mapeia cada frase do roteiro a uma cena, proporcional ao nº de frases.

    5 frases → [dor, demo, close, resultado, cta] (1:1)
    3 frases → [dor, demo, cta] (distribui mantendo dor no início, cta no fim)
    N frases → distribui a sequência canônica proporcionalmente

    Garante sempre: 1ª frase = dor (gancho), última = cta (fechamento).
    """
    n = len(frases)
    if n == 0:
        return []
    if n == 1:
        return ["demo"]
    if n == len(SEQUENCIA_CENAS):
        return list(SEQUENCIA_CENAS)

    # Distribui proporcionalmente, fixando dor no início e cta no fim
    cenas = []
    for i in range(n):
        if i == 0:
            cenas.append("dor")
        elif i == n - 1:
            cenas.append("cta")
        else:
            # mapeia posição do meio pra cenas do meio (demo/close/resultado)
            meio = SEQUENCIA_CENAS[1:-1]  # [demo, close, resultado]
            idx = int((i - 1) / max(1, n - 2) * len(meio))
            idx = min(idx, len(meio) - 1)
            cenas.append(meio[idx])
    return cenas


def _cena_do_arquivo(caminho: Path) -> str:
    """Extrai a cena do nome do arquivo (prefixo antes do 1º '_')."""
    nome = caminho.name.lower()
    for cena in SEQUENCIA_CENAS:
        if nome.startswith(f"{cena}_") or f"_{cena}_" in nome:
            return cena
    return ""


# =================================================================
# MONTAGEM DO VÍDEO
# =================================================================

def _aplicar_efeito(clip, efeito: str, mp):
    """
    Aplica um efeito leve ao clip (já em 720x1280). Best-effort: se a API do
    MoviePy não suportar, retorna o clip sem efeito (nunca quebra).

    efeito:
      zoom_in  — zoom progressivo suave (1.0 → ~1.08)
      punch_in — zoom fixo levemente mais forte (corte "seco" mais perto)
      crop_alt — pega um enquadramento deslocado (variar o mesmo asset)
      speed_105— acelera 5% (movimento sutil)
      none     — sem efeito
    """
    try:
        if efeito == "zoom_in":
            dur = clip.duration
            def _scale(t):
                return 1.0 + 0.08 * (t / dur if dur else 0)
            if hasattr(clip, "resized"):
                return clip.resized(_scale)
            elif hasattr(clip, "resize"):
                return clip.resize(_scale)
            return clip

        if efeito == "punch_in":
            fator = 1.08
            if hasattr(clip, "resized"):
                z = clip.resized(fator)
            elif hasattr(clip, "resize"):
                z = clip.resize(fator)
            else:
                return clip
            # recorta de volta pra 720x1280 (crop central do zoom)
            return _cobrir_916(z, mp)

        if efeito == "crop_alt":
            # desloca o crop: re-cobre com leve over-scale e corte deslocado
            fator = 1.12
            if hasattr(clip, "resized"):
                z = clip.resized(fator)
            elif hasattr(clip, "resize"):
                z = clip.resize(fator)
            else:
                return clip
            w, h = z.size
            x1 = max(0, (w - LARGURA) // 2 + 40)  # desloca 40px à direita
            y1 = max(0, (h - ALTURA) // 2)
            if hasattr(z, "cropped"):
                return z.cropped(x1=x1, y1=y1, x2=x1 + LARGURA, y2=y1 + ALTURA)
            elif hasattr(z, "crop"):
                return z.crop(x1=x1, y1=y1, x2=x1 + LARGURA, y2=y1 + ALTURA)
            return z

        if efeito == "speed_105":
            if hasattr(clip, "with_speed_scaled"):
                return clip.with_speed_scaled(1.05)
            elif hasattr(clip, "fx"):
                try:
                    from moviepy.video.fx import MultiplySpeed
                    return clip.with_effects([MultiplySpeed(1.05)])
                except Exception:
                    return clip
            return clip
    except Exception as e:
        log.warning(f"      efeito '{efeito}' falhou ({str(e)[:50]}) — sem efeito")
    return clip


def _preparar_corte_clip(caminho: Path, dur_alvo: float,
                          trecho_ini: float, trecho_fim: float,
                          efeito: str, mp, fontes: list):
    """
    Prepara o clip de UM corte da EDL: abre o asset, pega o trecho indicado
    (com loop se preciso), cobre 9:16, aplica efeito. Retorna o clip final.

    `fontes` acumula os clips-fonte originais pra fechar no fim (evita o
    WinError 6 do GC do ffmpeg ao deixar leitores órfãos).
    """
    (VideoFileClip, _, ImageClip, _, _, ColorClip, _) = mp
    ext = caminho.suffix.lower()

    if ext in EXT_IMG:
        base = ImageClip(str(caminho))
        base = _with_duration(base, dur_alvo)
        fonte = base
    else:
        fonte = VideoFileClip(str(caminho))
        fontes.append(fonte)  # rastreia pra fechar
        dur_fonte = fonte.duration or dur_alvo

        # Determina o trecho a usar
        ini = trecho_ini if trecho_fim > trecho_ini else 0.0
        # se o início pedido excede a fonte, volta pro começo
        if ini >= dur_fonte:
            ini = 0.0
        disponivel = dur_fonte - ini

        if disponivel >= dur_alvo:
            base = _subclip_seguro(fonte, ini, ini + dur_alvo)
        else:
            # trecho curto demais → loopa o trecho até cobrir dur_alvo
            try:
                from moviepy import concatenate_videoclips
            except ImportError:
                from moviepy.editor import concatenate_videoclips
            pedaco = _subclip_seguro(fonte, ini, dur_fonte)
            n = int(dur_alvo / max(0.1, pedaco.duration)) + 1
            base = concatenate_videoclips([pedaco] * n)
            base = _subclip_seguro(base, 0, dur_alvo)

    base = _cobrir_916(base, mp)
    base = _aplicar_efeito(base, efeito, mp)
    # garante duração exata do corte
    base = _with_duration(base, dur_alvo)
    return base


def _preparar_broll_clip(caminho: Path, dur_alvo: float, mp):
    """
    Carrega um B-roll (vídeo ou imagem), ajusta pra 9:16 cobrindo a tela,
    com duração dur_alvo (loop se vídeo curto). Retorna clip MoviePy.
    """
    (VideoFileClip, _, ImageClip, _, _, ColorClip, _) = mp
    ext = caminho.suffix.lower()
    if ext in EXT_IMG:
        clip = ImageClip(str(caminho))
        clip = _with_duration(clip, dur_alvo)
    else:
        clip = VideoFileClip(str(caminho))
        # loop se curto demais
        if clip.duration < dur_alvo:
            n = int(dur_alvo / clip.duration) + 1
            try:
                from moviepy import concatenate_videoclips
            except ImportError:
                from moviepy.editor import concatenate_videoclips
            clip = concatenate_videoclips([clip] * n)
        clip = _subclip_seguro(clip, 0, dur_alvo)
    # Redimensiona/corta pra 9:16 cobrindo
    clip = _cobrir_916(clip, mp)
    return clip


def _subclip_seguro(clip, ini, fim):
    if hasattr(clip, "subclipped"):
        return clip.subclipped(ini, min(fim, clip.duration))
    return clip.subclip(ini, min(fim, clip.duration))


def _cobrir_916(clip, mp):
    """Redimensiona o clip pra cobrir 720x1280 (crop central)."""
    w, h = clip.size
    escala = max(LARGURA / w, ALTURA / h)
    nova_w, nova_h = int(w * escala), int(h * escala)
    if hasattr(clip, "resized"):
        clip = clip.resized((nova_w, nova_h))
    elif hasattr(clip, "resize"):
        clip = clip.resize((nova_w, nova_h))
    # crop central
    x1 = (nova_w - LARGURA) // 2
    y1 = (nova_h - ALTURA) // 2
    if hasattr(clip, "cropped"):
        clip = clip.cropped(x1=x1, y1=y1, x2=x1 + LARGURA, y2=y1 + ALTURA)
    elif hasattr(clip, "crop"):
        clip = clip.crop(x1=x1, y1=y1, x2=x1 + LARGURA, y2=y1 + ALTURA)
    return clip


# Fontes candidatas por SO (a 1ª que o TextClip aceitar é usada).
# O bug do "vídeo sem texto": pediam 'DejaVu-Sans-Bold' (nome Linux) que não
# existe no Windows → TextClip falhava → except engolia → None silencioso.
_FONTES_CANDIDATAS = [
    "C:/Windows/Fonts/arialbd.ttf",   # Arial Bold (Windows)
    "C:/Windows/Fonts/Arial.ttf",     # Arial (Windows)
    "C:/Windows/Fonts/verdanab.ttf",  # Verdana Bold (Windows)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
    "Arial-Bold",                     # nome lógico (ImageMagick)
    "DejaVu-Sans-Bold",               # nome lógico (Linux)
    None,                             # último recurso: default do MoviePy
]

# Cache da fonte que funcionou (evita re-testar a cada legenda)
_FONTE_OK = "__nao_resolvida__"


def _resolver_fonte_textclip(TextClip):
    """
    Descobre UMA vez qual fonte o TextClip aceita neste ambiente.
    Testa criar um TextClip mínimo com cada candidata. Cacheia o resultado.
    Loga qual funcionou (ou avisa se nenhuma) — fim do None silencioso.
    """
    global _FONTE_OK
    if _FONTE_OK != "__nao_resolvida__":
        return _FONTE_OK
    from pathlib import Path as _P
    for fonte in _FONTES_CANDIDATAS:
        # pula caminhos de arquivo que não existem neste SO
        if fonte and ("/" in fonte or "\\" in fonte) and not _P(fonte).exists():
            continue
        try:
            kw = {"text": "Aa", "font_size": 40, "color": "white"}
            if fonte:
                kw["font"] = fonte
            _ = TextClip(**kw)
            _FONTE_OK = fonte
            log.info(f"   🔤 Fonte de legenda: {fonte or '(default MoviePy)'}")
            return _FONTE_OK
        except Exception:
            continue
    log.warning("   ⚠️  Nenhuma fonte aceita pelo TextClip — legendas podem falhar")
    _FONTE_OK = None
    return None


def _textclip_robusto(TextClip, texto, font_size, color, stroke_width,
                       largura_frac, fonte, stroke_color="black", text_align=None):
    """
    Cria um TextClip tentando várias assinaturas até uma funcionar.
    Ordem: (v2+margin) → (v1+margin) → (v2 sem margin) → (v1 sem margin).

    O 'margin' resolve o glifo cortado pelo stroke (a borda estoura a caixa e
    o MoviePy corta topo/base das letras). Mas nem toda versão aceita 'margin',
    então caímos pra sem-margin se precisar — texto nunca some por causa disso.

    stroke_color: cor do contorno. 'black' (padrão) ou 'white' (pro TopShop
    preto com sombra branca).
    text_align: 'West' (esquerda), 'center', 'East' (direita). Quando definido,
    alinha o texto dentro da caixa — útil pra marca colar à esquerda no logo.
    """
    size = (int(LARGURA * largura_frac), None)
    base = dict(color=color, stroke_color=stroke_color, stroke_width=stroke_width,
                method="caption", size=size)
    if fonte:
        base["font"] = fonte
    if text_align:
        base["text_align"] = text_align

    tentativas = [
        # (usa 'text='?, inclui margin?)
        dict(novo=True,  margin=True),
        dict(novo=False, margin=True),
        dict(novo=True,  margin=False),
        dict(novo=False, margin=False),
    ]
    for t in tentativas:
        kw = dict(base)
        # nome do parâmetro de tamanho da fonte muda entre versões
        if t["novo"]:
            kw["font_size"] = font_size
        else:
            kw["fontsize"] = font_size
        if t["margin"]:
            kw["margin"] = (10, 16)   # padding horizontal/vertical pro stroke caber
        try:
            if t["novo"]:
                return TextClip(text=texto, **kw)
            return TextClip(texto, **kw)
        except Exception:
            # se falhou e tinha text_align, tenta sem ele (versão não suporta)
            if "text_align" in kw:
                kw2 = dict(kw); kw2.pop("text_align")
                try:
                    if t["novo"]:
                        return TextClip(text=texto, **kw2)
                    return TextClip(texto, **kw2)
                except Exception:
                    pass
            continue
    return None


def _criar_legenda(texto: str, dur: float, inicio: float, mp):
    """Cria um TextClip de legenda na parte inferior. Robusto a fonte/versão."""
    (_, _, _, _, _, _, TextClip) = mp
    fonte = _fonte_montserrat("SemiBold") or _resolver_fonte_textclip(TextClip)
    txt = _textclip_robusto(TextClip, texto, font_size=44, color="white",
                            stroke_width=2, largura_frac=0.80, fonte=fonte)
    if txt is None:
        log.warning(f"   ⚠️  Legenda falhou pra '{texto[:30]}...'")
        return None
    txt = _with_duration(txt, dur)
    txt = _with_start(txt, inicio)
    # zona segura: abaixo da ação central do vídeo, ACIMA do CTA (faixa de baixo).
    # 1430 = não tampa o centro do vídeo nem invade o CTA do template.
    txt = _with_position(txt, ("center", 1430))
    return txt


def _criar_hook(texto: str, dur: float, mp):
    """
    Hook visual nos primeiros segundos: texto curto e chamativo pra prender
    quem assiste SEM SOM. Posicionado no terço superior (não tampa o centro
    nem a legenda de baixo).
    """
    (_, _, _, _, _, _, TextClip) = mp
    fonte = _resolver_fonte_textclip(TextClip)
    txt = _textclip_robusto(TextClip, texto, font_size=64, color="white",
                            stroke_width=3, largura_frac=0.82, fonte=fonte)
    if txt is None:
        return None
    txt = _with_duration(txt, dur)
    txt = _with_start(txt, 0.0)
    # terço superior — abaixo da faixa de marca (130px) com respiro
    txt = _with_position(txt, ("center", 360 if TEMPLATE_MARCA else 330))
    return txt


def _criar_cta(texto: str, dur: float, inicio: float, mp):
    """
    CTA de texto nos últimos segundos: chamada de ação curta e chamativa.
    Amarelo (contraste/urgência), no terço inferior mas acima da legenda.
    Aparece só no fim do vídeo (inicio = quando começar a aparecer).
    """
    (_, _, _, _, _, _, TextClip) = mp
    fonte = _resolver_fonte_textclip(TextClip)
    txt = _textclip_robusto(TextClip, texto, font_size=66, color="yellow",
                            stroke_width=3, largura_frac=0.82, fonte=fonte)
    if txt is None:
        return None
    txt = _with_duration(txt, dur)
    txt = _with_start(txt, inicio)
    # acima da legenda de baixo, mas no terço inferior (zona de ação)
    txt = _with_position(txt, ("center", ALTURA - 560))
    return txt


# ════════════════════════════════════════════════════════════════════
# TEMPLATE DE MARCA topshop — "carimba" identidade visual em todo vídeo
# (faixa superior com logo, CTA fixo embaixo, marca d'água)
# Espelha o formato dos vídeos manuais do @topshop._
# ════════════════════════════════════════════════════════════════════

def _fonte_montserrat(peso: str = "Bold") -> Optional[str]:
    """
    Retorna o caminho da Montserrat (peso estático) na pasta brand, se existir.
    peso: 'Bold', 'SemiBold', 'BoldItalic'. Fallback pro Bold, depois None.
    """
    cand = BRAND_DIR / f"Montserrat-{peso}.ttf"
    if cand.exists():
        return str(cand)
    # fallback: se pediu BoldItalic e não tem, tenta Bold
    if peso != "Bold":
        b = BRAND_DIR / "Montserrat-Bold.ttf"
        if b.exists():
            return str(b)
    return None


def _fonte_gancho(peso: str = "Light") -> tuple:
    """(caminho, familia) da fonte do GANCHO, no peso pedido.

    O Dre pediu "montserrat light, poppins, ou algo grande". A ordem aqui é
    essa mesma, e existe uma segunda opção de verdade porque a Montserrat
    estática precisa ser FATIADA da variável pelo fontTools (o Google não
    publica mais os pesos prontos) — e fontTools pode não estar no venv.

    Devolve (None, "") quando nenhuma das duas está na pasta, pra quem chama
    poder gritar. Cair calado na Liberation é entregar o feed velho achando que
    entregou o novo.
    """
    familia = os.environ.get("HOOK_FAMILIA", "").strip()
    ordem = [familia] if familia else ["Montserrat", "Poppins"]
    for fam in ordem:
        alvo = BRAND_DIR / f"{fam}-{peso}.ttf"
        if alvo.exists():
            return str(alvo), fam
    return None, ""


def _brand_asset(nome: str) -> Optional[Path]:
    """Retorna o caminho de um asset de marca se existir (logo_ts.png etc)."""
    p = BRAND_DIR / nome
    return p if p.exists() else None


def _emoji_aparado(nome: str, tam: int) -> Optional[Path]:
    """
    Carrega um PNG de emoji da pasta brand, APARA a margem transparente em volta
    (autocrop pelo canal alfa) e redimensiona pro tamanho pedido. Salva em tmp.

    Resolve o problema dos emojis "pequenos": muitos PNGs de emoji têm muito
    espaço transparente em volta do desenho. Sem aparar, o resize conta o vazio
    e o desenho visível fica menor que o esperado. Aparando, o `tam` vira o
    tamanho REAL do desenho — previsível e consistente entre emojis diferentes.

    Retorna o caminho do PNG aparado, ou None se não achar/não conseguir.
    """
    p = _brand_asset(nome)
    if p is None:
        return None
    try:
        from PIL import Image
        img = Image.open(str(p)).convert("RGBA")
        # bbox do conteúdo não-transparente (apara o vazio em volta)
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
        # redimensiona pro tamanho pedido (quadrado, mantém proporção do desenho)
        w, h = img.size
        escala = tam / max(w, h)
        novo = (max(1, int(w * escala)), max(1, int(h * escala)))
        img = img.resize(novo, Image.LANCZOS)
        out = TMP_DIR / f"emoji_{nome}"
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out))
        return out
    except Exception as e:
        log.warning(f"   ⚠️  Aparar emoji {nome} falhou ({e}) — usando original")
        return p


def _textclip_justo(TextClip, texto, font_size, fonte):
    """
    Cria um TextClip com caixa JUSTA ao texto (method='label', sem size fixo),
    só pra MEDIR a largura real do texto renderizado. Robusto a versão.
    Retorna o clip (quem chama lê .w e fecha), ou None.
    """
    for novo in (True, False):
        try:
            kw = dict(color="white", method="label")
            if fonte:
                kw["font"] = fonte
            if novo:
                kw["font_size"] = font_size
                return TextClip(text=texto, **kw)
            else:
                kw["fontsize"] = font_size
                return TextClip(texto, **kw)
        except Exception:
            continue
    return None


def _textclip_esq(TextClip, texto, font_size, color, stroke_width, stroke_color, fonte):
    """TextClip JUSTO (method='label') COM cor+contorno — alinhamento à ESQUERDA
    de verdade (a caixa 'caption' centraliza; o label não tem caixa, então o
    canto esquerdo do clip = começo do texto). Fallback pro caption se falhar.
    Usa margem transparente (TXT_MARGEM) p/ não CORTAR descendentes (p, g) e
    acentos — a caixa 'label' é justa e come as pontas sem essa folga."""
    _m = int(os.environ.get("TXT_MARGEM", 8))
    for com_margem in (True, False):          # tenta COM margem; se a versão não
        for novo in (True, False):            # aceitar, cai p/ label puro (não corta o texto)
            try:
                kw = dict(color=color, method="label")
                if fonte:
                    kw["font"] = fonte
                if stroke_width:
                    kw["stroke_color"] = stroke_color
                    kw["stroke_width"] = stroke_width
                if com_margem and _m:
                    kw["margin"] = (_m, _m)
                if novo:
                    kw["font_size"] = font_size
                    clipe = TextClip(text=texto, **kw)
                else:
                    kw["fontsize"] = font_size
                    clipe = TextClip(texto, **kw)
                # ⚠️ QUANTO DESTE CLIP É VAZIO. Quem posiciona algo DEPOIS deste
                # texto precisa saber que `.w` inclui margem transparente dos
                # dois lados — e que a margem pode NÃO ter sido aplicada, se a
                # versão do moviepy recusou o kwarg (é o laço aí de cima).
                # Sem isso, quem lê `.w` acerta a conta e erra o pixel.
                try:
                    clipe._margem_x = _m if (com_margem and _m) else 0
                except Exception:
                    pass
                return clipe
            except Exception:
                continue
    # não deu label → cai no caption (pode centralizar, mas não quebra)
    return _textclip_robusto(TextClip, texto, font_size, color, stroke_width,
                             0.92, fonte, stroke_color=stroke_color, text_align="West")


# ── EMOJI COLORIDO NO HOOK (Noto Color Emoji) ─────────────────────
_NOTO_EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

# emojis coloridos SEGUROS (1 codepoint) por palavra-chave do hook/produto
_HOOK_EMOJI_MAPA = [
    (("cozinha", "panela", "fog", "utensil", "copo", "garrafa", "talher",
      "fatiad", "ralad", "descasc"), "🍳"),
    (("beleza", "skincare", "makeup", "maquia", "batom", "perfume", "cabelo",
      "unha", "pele", "hidrat"), "💄"),
    (("pet", "cachorro", "gato", "aquari", "raç", "coleira"), "🐶"),
    (("fone", "carregad", "cabo", "gadget", "led", "lumin", "eletron", "usb",
      "bluetooth", "teclado"), "🔌"),
    (("fitness", "treino", "academ", "yoga", "muscula", "corrida", "emagrec"),
     "💪"),
    (("organiz", "decor", "closet", "guarda", "banheiro", "quarto", "suporte",
      "prateleira"), "🏠"),
    (("bebe", "bebê", "infantil", "criança", "banheira", "fralda",
      "mamadeira"), "🍼"),
    (("roupa", "jaqueta", "camisa", "moda", "vestido", "calça", "tenis",
      "tênis", "bota", "meia"), "👕"),
    (("moto", "capacete", "carro", "automot", "bike", "bicicleta", "scooter"),
     "🛵"),
    (("limpeza", "limpa", "esponja", "vassoura", "mancha"), "🧽"),
]


def _char_eh_emoji(ch: str) -> bool:
    o = ord(ch)
    return (0x1F300 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF
            or 0x1F1E6 <= o <= 0x1F1FF or 0x2B00 <= o <= 0x2BFF
            or o in (0x2705, 0x2714, 0x2764) or 0xFE00 <= o <= 0xFE0F
            or o == 0x200D)


def _separar_emoji_hook(hook_txt: str):
    """Tira emojis do texto do hook (evita 'tofu' na fonte) e escolhe 1 emoji
    colorido: o que já vinha no hook, ou por palavra-chave, ou fogo."""
    achado = None
    limpo = []
    for ch in (hook_txt or ""):
        if _char_eh_emoji(ch):
            if achado is None and not (0xFE00 <= ord(ch) <= 0xFE0F) and ord(ch) != 0x200D:
                achado = ch
        else:
            limpo.append(ch)
    texto = "".join(limpo).strip()
    while "  " in texto:
        texto = texto.replace("  ", " ")
    if achado is None:
        t = texto.lower()
        for chaves, emo in _HOOK_EMOJI_MAPA:
            if any(k in t for k in chaves):
                achado = emo
                break
        if achado is None:
            achado = "🔥"
    return achado, (texto or (hook_txt or ""))


def _emoji_colorido_png(emoji_char: str, tam: int):
    """Renderiza 1 emoji COLORIDO (Noto) num PNG aparado no tamanho pedido.
    A Noto Color Emoji só carrega no tamanho 109 -> renderiza nele e reescala."""
    try:
        import os
        from PIL import Image, ImageDraw, ImageFont
        if not os.path.exists(_NOTO_EMOJI):
            return None
        fnt = ImageFont.truetype(_NOTO_EMOJI, 109)
        img = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((8, 8), emoji_char, font=fnt, embedded_color=True)
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
        w, h = img.size
        escala = tam / max(w, h)
        img = img.resize((max(1, int(w * escala)), max(1, int(h * escala))),
                         Image.LANCZOS)
        nome = "_".join(str(ord(c)) for c in emoji_char)
        out = TMP_DIR / f"hookemoji_{nome}_{tam}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out))
        return out
    except Exception as e:
        log.warning(f"   ⚠️  Emoji colorido '{emoji_char}' falhou: {e}")
        return None


def _quebrar_hook_2linhas(texto: str):
    """Divide o hook em 2 linhas equilibradas (corte na palavra mais perto do
    meio). Retorna [linha] se tiver 1 palavra só. Base do layout 2-linhas."""
    palavras = (texto or "").split()
    if len(palavras) < 2:
        return [texto]
    total = len(texto)
    acc, corte = 0, 1
    for i, w in enumerate(palavras):
        acc += len(w) + 1
        if acc >= total / 2:
            corte = i + 1
            break
    corte = max(1, min(corte, len(palavras) - 1))
    l1 = " ".join(palavras[:corte])
    l2 = " ".join(palavras[corte:])
    return [l1, l2] if l2 else [l1]


# Emoji colorido por NICHO do produto (1 codepoint = renderiza no Noto).
# Emoji por produto — duas listas, e a diferença entre elas é QUEM GANHA do
# emoji que o hook já trouxe.
#
# O hook vem com emoji escolhido pela fórmula ou pela frase de reserva, e esse
# costuma ser bom porque foi escrito junto com a frase. Até 03/08 o palpite por
# palavra-chave ganhava dele SEMPRE (linha `_emoji_do_produto(produto) or
# _emoji_do_txt`), e o resultado apareceu nos posts: luminária de urso com 🔌,
# separador de ovos com 🔌, suporte de celular com 🛵.
#
# ALTA CONFIANÇA vence o hook: aqui o emoji É o produto, e é pra isto que a
# regra foi criada (o ROADMAP cita câmera 📷 e óculos 😎 nominalmente).
_EMOJI_ALTA = [
    (("camera", "câmera", "filmadora", "gravador", "gravaç", "espiã", "espião",
      "gopro", "webcam", "dvr", "vigilância", "vigilancia"), "📷"),
    (("óculos de sol", "oculos de sol", "óculos", "oculos"), "😎"),
    (("cafeteira", "café", "cafe", "dolce gusto", "nespresso", "espresso",
      "expresso", "cappuccino", "capuccino", "moedor de café", "prensa francesa",
      "chaleira elétrica", "chaleira eletrica"), "☕"),
    # luminária saiu do grupo do carregador. Uma luminária de urso na mesa de
    # cabeceira com emoji de tomada foi o post mais fora de tom da semana.
    (("luminária", "luminaria", "abajur", "lampada", "lâmpada", "candeeiro",
      "led 3d", "luminária 3d"), "💡"),
    (("pet", "cachorro", "gato", "aquari", "coleira", "comedouro", "arranhador"),
     "🐶"),
    (("bebê", "bebe ", "infantil", "mamadeira", "fralda", "pelúcia", "pelucia",
      "urso ", "brinquedo"), "🧸"),
]

# BAIXA CONFIANÇA só entra se o hook NÃO trouxe emoji. São categorias largas,
# onde o acerto é aproximado e o emoji do hook quase sempre é melhor.
_EMOJI_BAIXA = [
    (("cozinha", "panela", "fritad", "air fryer", "utensil", "copo", "caneca",
      "garrafa", "talher", "fatiad", "ralad", "liquidif", "descasc", "prato",
      "tigela", "faca", "ovo", "ovos", "espremedor", "batedor"), "🍳"),
    (("skincare", "beleza", "maquia", "batom", "perfume", "cabelo", "cabelud",
      "unha", "pele", "hidrat", "serum", "sérum", "gloss", "labial", "blush",
      "sombra", "pó compacto"), "💄"),
    (("fone", "carregad", "cabo usb", "power bank", "gadget", "eletron",
      "bluetooth", "teclado", "mouse", "notebook", "smartwatch", "celular"),
     "🔌"),
    (("fitness", "treino", "academ", "yoga", "muscula", "corrida", "emagrec"),
     "💪"),
    (("organiz", "closet", "guarda-roupa", "prateleira", "cabide", "gaveta",
      "cesto", "necessaire", "nécessaire"), "🧺"),
    (("manta", "fronha", "lençol", "lencol", "cobertor", "edredom", "toalha",
      "almofada", "tapete", "cortina", "sofá", "sofa"), "🏠"),
    (("roupa", "jaqueta", "casaco", "moletom", "blusa", "camisa", "vestido",
      "calça", "short", "biquíni", "pijama", "tênis", "tamanco", "chinelo",
      "bota", "sandália", "sandalia", "scarpin", "bolsa", "mochila"), "👕"),
    # 'moto' sozinho pegava "suporte magnético moto" (um suporte de celular).
    # Agora exige contexto de veículo de verdade.
    (("motocicleta", "capacete", "automot", "bicicleta", "para-brisa",
      "parabrisa", "painel do carro", "porta-malas"), "🛵"),
    (("limpeza", "esponja", "vassoura", "rodo", "mop", "aspirador"), "🧽"),
]


def _pontuar(texto: str, lista) -> tuple:
    """(emoji, pontos) da categoria que mais casa. Pontuação em vez de
    'primeira que casa vence': 'Escova Massageadora para Couro Cabeludo' casava
    com 'massage' (fitness 💪) porque fitness vinha antes, mesmo tendo duas
    palavras de beleza. Contando, beleza ganha 2 a 1."""
    melhor, pontos = None, 0
    for chaves, emo in lista:
        n = sum(1 for k in chaves if k in texto)
        if n > pontos:
            melhor, pontos = emo, n
    return melhor, pontos


def _emoji_do_produto(produto: str, so_alta: bool = False):
    """Emoji que combina com o produto, ou None.

    so_alta=True devolve só as categorias que valem a pena sobrepor ao emoji
    que o hook já trouxe.
    """
    if not produto:
        return None
    p = str(produto).lower()
    emo, _ = _pontuar(p, _EMOJI_ALTA)
    if emo or so_alta:
        return emo
    emo, _ = _pontuar(p, _EMOJI_BAIXA)
    return emo


def _criar_camadas_topo(dur_total: float, hook_txt: str, mp,
                        produto: str = "") -> list:
    """
    Monta a ZONA SUPERIOR do template topshop, fiel ao @topshop._:
      - logo TS REDONDO no canto superior esquerdo
      - 'TopShop' PRETO (Bold) com contorno BRANCO + selo verificado
      - '@topshop._' BRANCO (Bold) com contorno PRETO logo abaixo
      - Hook grande com sombra, centralizado, perto do vídeo
    """
    (_, _, ImageClip, _, _, ColorClip, TextClip) = mp
    camadas = []
    fonte_bold = _fonte_montserrat("Bold") or _resolver_fonte_textclip(TextClip)

    # ── ESTILO POR PALETA DE NICHO (02/09) ───────────────────────────────────
    # Era: `_bg in ("branco","white","bege","claro")` — três palavras decidindo
    # tudo, com a mesma regra copiada em produzir_tiktok e no hunter. Agora a
    # paleta é uma só (shared/paleta.py) e o nicho é quem manda.
    #
    # A tinta NÃO é mais "black ou white": é derivada da luminância do fundo lá
    # dentro. É o que impede o pedido literal do Dre ("tech: preto puro" +
    # "a fonte deve ser preta") de virar um retângulo preto.
    try:
        from shared.paleta import do_ambiente as _paleta_do_ambiente
        _pal = _paleta_do_ambiente()
    except Exception as _e:      # paleta quebrada não pode derrubar a produção
        log.warning(f"   ⚠️  paleta indisponível ({str(_e)[:80]}) — cai no preto/branco antigo")
        _bg = os.environ.get("TOPSHOP_BG", "preto").strip().lower()
        _cl = _bg in ("branco", "white", "bege", "claro")
        _pal = {"claro": _cl,
              "tinta_hex": "#000000" if _cl else "#FFFFFF",
              "secundaria_hex": "#7a7a7a" if _cl else "#FFFFFF",
              "contorno": 0 if _cl else int(os.environ.get("HK_STROKE_PRETO", 4)),
              "nicho": "?", "fundo_hex": "?", "fundo_nome": "fallback",
              "destaque_hex": "?"}
    _claro = _pal["claro"]
    C_NOME, SC_NOME, SW_NOME = _pal["tinta_hex"], "black", (0 if _claro else 3)
    C_HANDLE = _pal["secundaria_hex"]
    C_HOOK, SC_HOOK, SW_HOOK = _pal["tinta_hex"], "black", _pal["contorno"]

    # ── FONTE DO GANCHO: Montserrat, peso leve, grande (pedido do Dre) ────────
    # "fonte de letra: montserrat light, poppins, ou algo grande, deve ser preto"
    #
    # O peso é env (HOOK_PESO) e não constante porque nos dois perfis de
    # referência o gancho é REGULAR, não Light — Light em 48px sobre a borda do
    # vídeo perde corpo. Light é o que ele pediu e é o padrão; trocar pra
    # Regular é uma variável de ambiente, não um deploy.
    #
    # ⚠️ CAIR NA FONTE ANTIGA TEM QUE DOER DE LER. A Montserrat mora em
    # assets/brand/ (fora do Git, só na VPS). Se o .ttf do peso pedido não
    # estiver lá, o vídeo sai com Liberation e NINGUÉM percebe olhando o log —
    # foi assim que a logo errada foi parar num vídeo do @topshopcasa_.
    _LIB = "/usr/share/fonts/truetype/liberation/"
    _hk_peso = os.environ.get("HOOK_PESO", "Light")
    _hk_fonte = os.environ.get("HOOK_FONTE") if _claro else os.environ.get("HOOK_FONTE_PRETO")
    if not _hk_fonte:
        _hk_fonte, _fam = _fonte_gancho(_hk_peso)
        if not _hk_fonte:
            log.warning(
                f"   ⚠️  NEM MONTSERRAT-{_hk_peso.upper()}.TTF NEM POPPINS-{_hk_peso.upper()}.TTF "
                f"ESTÃO EM {BRAND_DIR}. O gancho vai sair na fonte antiga "
                f"(Liberation): o vídeo NÃO vai ter a cara nova, e nada mais "
                f"além desta linha vai avisar. "
                f"Rode: .venv/bin/python baixar_fontes.py")
            _hk_fonte = (_LIB + ("LiberationSans-Regular.ttf" if _claro
                                 else "LiberationSans-Bold.ttf"))
    if not (_hk_fonte and Path(_hk_fonte).exists()):
        _hk_fonte = fonte_bold
    log.info(f"   🎨 {_pal.get('nicho','?')}: fundo {_pal.get('fundo_hex','?')} "
             f"({_pal.get('fundo_nome','?')}) · tinta {_pal['tinta_hex']} · "
             f"fonte {Path(_hk_fonte).name if _hk_fonte else '?'}")

    # ── GEOMETRIA: a coluna do texto É a coluna do vídeo ──────────────────────
    # O render.py já amarrava os dois; este arquivo não, e usava LOGO_X=100
    # absoluto. Com VIDEO_W_FRAC subindo de 0,82 pra 0,90 (pedido: "aumentar o
    # vídeo nas bordas"), a borda esquerda do vídeo vai de 97 pra 54 — logo e
    # gancho ficariam 46px pra dentro do vídeo, desalinhados.
    # Derivando, mexer na largura do vídeo move a coluna inteira junto.
    # ⚠️ LOGO_X/HK_MARGEM no .env AINDA GANHAM. Se estiverem lá com os valores
    # velhos, esta derivação nunca acontece — é o mesmo mecanismo que fez o
    # SELO_DX do código ser ignorado por duas rodadas.
    _borda_video = int((LARGURA - int(LARGURA * float(os.environ.get("VIDEO_W_FRAC", 0.90)))) / 2)
    logo_x = int(os.environ.get("LOGO_X", _borda_video))
    logo_y = int(os.environ.get("LOGO_Y", 168))    # era 112 — "abaixar + o header"
    logo_tam = int(os.environ.get("LOGO_TAM", 140))  # era 120 — "aumentar + o logo"
    # tudo o que foi calibrado contra um logo de 120px acompanha a escala, em
    # vez de virar mais três números pra acertar no olho.
    _k = logo_tam / 120.0

    # ── Logo TS REDONDO (canto superior esquerdo) ──
    # logo POR CONTA/NICHO: a produção seta TOPSHOP_LOGO (ex.: logo_ts_tech.png,
    # logo_ts_beauty.png) antes de renderizar; cai na logo_ts.png padrão.
    logo_path = _brand_asset(os.environ.get("TOPSHOP_LOGO", "logo_ts.png"))
    if logo_path is None:
        logo_path = _brand_asset("logo_ts.png")
    if logo_path is not None:
        circular = _logo_circular(logo_path, tam=logo_tam) or logo_path
        try:
            logo = ImageClip(str(circular))
            logo = _resize_clip(logo, largura=logo_tam)
            logo = _with_duration(logo, dur_total)
            logo = _with_start(logo, 0.0)
            logo = _with_position(logo, (logo_x, logo_y))
            camadas.append(logo)
        except Exception as e:
            log.warning(f"   ⚠️  Logo TS falhou: {e}")

    texto_x = logo_x + logo_tam + int(os.environ.get("TEXTO_DX", 16))
    # ⚠️ A TIPOGRAFIA DO CABEÇALHO NÃO ESCALA COM O LOGO, DE PROPÓSITO.
    # O pedido foi "aumentar + o logo e abaixar", não "aumentar o nome". O
    # tamanho do nome já foi calibrado no olho pelo Dre e está no .env da VPS
    # (52/42, registrado em render.py:105). Na 1ª prévia eu escalei os dois por
    # _k e o selo azul foi parar em cima do "@topshopbeauty._" — mexer no que
    # já estava resolvido criou um defeito que não existia.
    # 52/42 aqui deixa este renderizador e o render.py finalmente com o MESMO
    # padrão, que é o valor real de produção (antes eram 56/46, letra morta).
    _nome_font = int(os.environ.get("NOME_FONT", 52))
    _handle_font = int(os.environ.get("HANDLE_FONT", 42))
    # ⚠️ O @ E O SELO PENDURAM NO NOME, NÃO NO LOGO (achado na 1ª prévia, 02/09).
    # Eu tinha escalado os dois por _k (= LOGO_TAM/120) e o selo azul caiu EM
    # CIMA do "@topshopmoda_": o vão entre o nome e o @ é um fato tipográfico do
    # TAMANHO DO NOME, e o .env da VPS tem NOME_FONT=52 (não 56), então as duas
    # escalas divergem — logo cresce 1,17×, nome cresce 1,25×.
    #
    # As constantes abaixo reproduzem EXATAMENTE os números de produção quando
    # NOME_FONT=52, que é o que está no ar hoje:
    #     handle_dy = -12 + round(52 × 1,038) = 42   ✔ é o valor de produção
    #     selo_dy   = -12 + round(52 × 0,50)  = 14   ✔ idem
    #     selo_tam  =       round(52 × 0,885) = 46   ✔ idem
    # Ou seja: no tamanho de hoje nada muda, e em qualquer outro tamanho a
    # relação se mantém em vez de precisar de três números novos no olho.
    _nome_dy = int(os.environ.get("NOME_DY", round(-12 * _k)))
    _handle_dy = int(os.environ.get("HANDLE_DY", _nome_dy + round(_nome_font * 1.038)))
    _selo_dy = int(os.environ.get("SELO_DY", _nome_dy + round(_nome_font * 0.50)))
    _selo_tam = int(os.environ.get("SELO_TAM", round(_nome_font * 0.885)))

    # ── 'TopShop' PRETO (Bold) com contorno BRANCO ──
    nome = _textclip_esq(TextClip, MARCA_NOME, _nome_font, C_NOME, SW_NOME, SC_NOME, fonte_bold)
    fim_topshop_x = texto_x + 235  # fallback se não der pra medir
    if nome is not None:
        nome = _with_duration(nome, dur_total)
        nome = _with_start(nome, 0.0)
        nome = _with_position(nome, (texto_x, logo_y + _nome_dy))
        camadas.append(nome)

    # ── Selo verificado — vai DEPOIS da tinta do 'TopShop'.
    #
    # ⚠️ O SELO ENTRAVA DENTRO DO NOME (achado em 19/08). O código media o nome
    # com um SEGUNDO clip (`_textclip_justo`) em vez de olhar o que desenhou.
    # Os dois clips não são iguais:
    #
    #     desenhado (_textclip_esq):  margin=8 dos dois lados + stroke_width=3
    #     medidor   (_textclip_justo): sem margem, sem contorno
    #
    # Então `larg_real` vinha ~11px curta e o selo pousava em cima da última
    # letra. O log dizia "Selo verificado em x=462 (larg real TopShop=238)" —
    # número certo, medida errada: a conta fechava com ela mesma. Foi o que me
    # fez olhar o log de 19/08 e concluir que estava tudo bem enquanto o Dre
    # via o selo dentro do nome. Ele estava certo.
    #
    # A margem entrou em 14/07 (a099f60, pra não cortar o 'p' de TopShop) e o
    # medidor não acompanhou. Por isso "os antigos não estavam saindo assim".
    #
    # AGORA MEDE O PRÓPRIO CLIP DESENHADO. Não existe mais um segundo clip pra
    # divergir do primeiro — que era a causa, não o sintoma.
    selo_aparado = _emoji_aparado("verificado.png", _selo_tam)
    if selo_aparado is not None:
        try:
            fim_tinta = None
            if nome is not None:
                # `.w` inclui a margem transparente dos DOIS lados; a tinta
                # termina uma margem antes da borda direita do clip.
                _mx = int(getattr(nome, "_margem_x", 0) or 0)
                fim_tinta = int(nome.w) - _mx
            if fim_tinta:
                selo_x = texto_x + fim_tinta + int(os.environ.get("SELO_DX", 12))
            else:
                # fallback estimado (fim_topshop_x é definido lá em cima)
                selo_x = fim_topshop_x + int(os.environ.get("SELO_DX", 12))

            # ── E A VERTICAL TAMBÉM MEDE O CLIP DESENHADO (02/09) ─────────────
            # O Dre, olhando a prévia das 6 contas: *"só o selo mesmo ficou
            # desalinhado"*. Estava — e por um deslocamento cravado no olho
            # (`logo_y + 14`), que não sabe onde a tinta do nome começa nem
            # quanto ela mede. Num handle curto (@topshop.__) a folga escondia o
            # erro; num longo (@topshopbeauty._) o selo encostava no @.
            #
            # A `margin=(_m,_m)` do _textclip_esq é (x, y): `.h` carrega a mesma
            # margem transparente em cima e embaixo que `.w` carrega nos lados.
            # Então a tinta do nome mede `h - 2m` e o selo centra nela.
            #
            # É a MESMA correção que a horizontal levou em 19/08 — "medir uma
            # coisa e desenhar outra" — só que na vertical, onde ela não tinha
            # sido feita. SELO_DY no .env continua ganhando (depuração).
            selo_dy = _selo_dy
            if nome is not None and not os.environ.get("SELO_DY"):
                try:
                    tinta_h = int(nome.h) - 2 * _mx
                    if tinta_h > 0:
                        selo_dy = _nome_dy + _mx + (tinta_h - _selo_tam) // 2
                except Exception:
                    pass

            selo = ImageClip(str(selo_aparado))
            selo = _with_duration(selo, dur_total)
            selo = _with_start(selo, 0.0)
            selo = _with_position(selo, (selo_x, logo_y + selo_dy))
            camadas.append(selo)
            log.info(f"   ✔️  Selo em x={selo_x} dy={selo_dy} (cravado seria "
                     f"{_selo_dy}) · fim da tinta do TopShop="
                     f"{(texto_x + fim_tinta) if fim_tinta else '?'} "
                     f"(clip={getattr(nome, 'w', '?')}×{getattr(nome, 'h', '?')} "
                     f"margem={_mx if nome is not None else '?'} contorno={SW_NOME})")
        except Exception as e:
            log.warning(f"   ⚠️  Selo verificado falhou: {e}")
    else:
        log.warning("   ⚠️  verificado.png NÃO encontrado na pasta brand!")

    # ── '@topshop._' BRANCO (Bold) com contorno PRETO ──
    # lê o handle em tempo de render (multi-conta): a produção seta TOPSHOP_HANDLE
    # por vídeo antes de renderizar; cai no MARCA_HANDLE default se não setado.
    _handle_txt = os.environ.get("TOPSHOP_HANDLE", MARCA_HANDLE) or MARCA_HANDLE
    handle = _textclip_esq(TextClip, _handle_txt, _handle_font,
                           C_HANDLE, (0 if _claro else 3), "black", fonte_bold)
    if handle is not None:
        handle = _with_duration(handle, dur_total)
        handle = _with_start(handle, 0.0)
        handle = _with_position(handle, (texto_x, logo_y + _handle_dy))
        camadas.append(handle)

    # ── HOOK à ESQUERDA, 1 OU 2 linhas, cor por fundo (estilo Alana) ──────────
    # >>> tudo tunável por .env (ajuste fino olhando 1 render de teste) <<<
    HK_FONT_MAX = int(os.environ.get("HK_FONT", 60))     # era 48 — "algo grande"
    HK_FONT_MIN = int(os.environ.get("HK_FONT_MIN", 34))
    # a margem do gancho é a BORDA DO VÍDEO, dos dois lados: a coluna do texto
    # e a coluna da mídia são a mesma, e simétrica.
    HK_MARGEM   = int(os.environ.get("HK_MARGEM", _borda_video))
    HK_ALTURA_LINHA = int(os.environ.get("HK_ALT_LINHA", 76))   # era 62, acompanha a fonte
    HK_MAX_LARG = LARGURA - HK_MARGEM - int(os.environ.get("HK_MARGEM_DIR", _borda_video))
    HK_EMOJI_TAM = int(os.environ.get("HK_EMOJI", 40))

    _emoji_do_txt, hook_txt_limpo = _separar_emoji_hook(hook_txt)
    # O emoji que veio NO HOOK ganha, porque foi escrito junto com a frase.
    # Só as categorias de alta confiança (câmera, óculos, café, luminária, pet,
    # bebê) sobrepõem — ali o emoji É o produto. Antes o palpite por
    # palavra-chave ganhava sempre, e foi assim que a luminária de urso saiu
    # com 🔌 e o suporte de celular com 🛵.
    _emoji_hook = (_emoji_do_produto(produto, so_alta=True)
                   or _emoji_do_txt
                   or _emoji_do_produto(produto))

    def _larg(txt, fnt):
        _m = _textclip_justo(TextClip, txt, fnt, _hk_fonte)
        w = getattr(_m, "w", 0) if _m is not None else 0
        if _m is not None:
            try: _m.close()
            except Exception: pass
        return w

    # LINHAS do hook:
    #   • quebra EXPLÍCITA "\n" (formato Alana: 'frase 😩' / 'A Shopee:') → respeita;
    #     o emoji fica no fim da 1ª linha (a frase relatable).
    #   • senão 1 linha (cabe na fonte cheia) ou auto-quebra em 2 (emoji na última).
    HK_FONT = HK_FONT_MAX

    def _wrap(txt, fnt):
        """Quebra GULOSA por largura: enche cada linha até HK_MAX_LARG (não vaza
        pela direita). Retorna a lista de linhas."""
        out, cur = [], []
        for w in (txt or "").split():
            if cur and _larg(" ".join(cur + [w]), fnt) > HK_MAX_LARG:
                out.append(" ".join(cur)); cur = [w]
            else:
                cur.append(w)
        if cur:
            out.append(" ".join(cur))
        return out or [txt]

    # parágrafos = quebra EXPLÍCITA "\n" (formato Alana: frase / A Shopee:); senão 1.
    _paras = [l.strip() for l in hook_txt_limpo.split("\n") if l.strip()] or [hook_txt_limpo]

    def _quebrar_tudo(fnt):
        """(linhas, índice da linha que leva o emoji) nesta fonte."""
        linhas, emoji_linha = [], 0
        for _pi, _par in enumerate(_paras):
            _wl = _wrap(_par, fnt)
            if _pi == 0:
                emoji_linha = len(_wl) - 1   # emoji no fim da 1ª frase
            linhas += _wl
        return linhas, emoji_linha

    # ENCOLHE ATÉ CABER EM 2 LINHAS, não só até a maior palavra caber.
    #
    # O critério antigo (palavra mais larga) deixava passar 3 linhas, e 3 linhas
    # já era apertado no layout velho. No layout novo — logo maior e mais baixo,
    # vídeo maior e mais baixo — a faixa acima do vídeo encolheu de 470 pra 500
    # menos um cabeçalho de 140: 3 linhas ENCOSTAM no vídeo.
    # Duas linhas também é o que o Dre pediu explicitamente ("use duas linhas de
    # texto no topo") e é o que os dois perfis de referência fazem, sem exceção.
    _linhas, _emoji_linha = _quebrar_tudo(HK_FONT)
    while HK_FONT > HK_FONT_MIN and len(_linhas) > 2:
        HK_FONT -= 2
        _linhas, _emoji_linha = _quebrar_tudo(HK_FONT)
    _n = len(_linhas)
    if _n > 2:
        # não trunco: o gancho inteiro vai no aviso. Aviso que corta a evidência
        # é meio aviso — e aqui a evidência é o texto que precisa ser reescrito.
        log.warning(
            f"   ⚠️  GANCHO NÃO CABE EM 2 LINHAS nem em {HK_FONT_MIN}px: saiu com "
            f"{_n} linhas e vai ENCOSTAR no vídeo. {len(hook_txt_limpo)} caracteres: "
            f"{hook_txt_limpo!r}")

    # POSIÇÃO VERTICAL: ancora o RODAPÉ do hook logo acima do topo do vídeo
    # (VIDEO_Y no hunter). Assim 1 OU 2 linhas ficam sempre "coladas" em cima do
    # vídeo, estilo Alana — sem precisar calibrar HK_Y por fora. HK_Y absoluto
    # ainda funciona como override (debug).
    _video_top = int(os.environ.get("VIDEO_Y", 500))   # era 470 — "abaixar + o vídeo"
    _gap = int(os.environ.get("HK_GAP_VIDEO", 16))
    if os.environ.get("HK_Y"):
        HK_Y = int(os.environ["HK_Y"])
    else:
        HK_Y = max(logo_y + logo_tam + 20, _video_top - _gap - _n * HK_ALTURA_LINHA)

    _hk_por_linha = []
    for _i, _linha in enumerate(_linhas):
        _y = HK_Y + _i * HK_ALTURA_LINHA
        _hk = _textclip_esq(TextClip, _linha, HK_FONT, C_HOOK, SW_HOOK, SC_HOOK, _hk_fonte)
        _hk_por_linha.append(_hk)
        if _hk is not None:
            _hk = _with_duration(_hk, dur_total)
            _hk = _with_start(_hk, 0.0)
            _hk = _with_position(_hk, (HK_MARGEM, _y))
            camadas.append(_hk)
    log.info(f"   📌 Hook ({_n}L, {'claro' if _claro else 'escuro'}): "
             f"\"{hook_txt_limpo.replace(chr(10), ' / ')}\"")

    # emoji COLORIDO no fim da linha certa (1ª no formato Alana; última no auto)
    if _emoji_hook and 0 <= _emoji_linha < _n:
        try:
            _epath = _emoji_colorido_png(_emoji_hook, HK_EMOJI_TAM)
            if _epath is not None:
                _y_emo = HK_Y + _emoji_linha * HK_ALTURA_LINHA
                _lw = _larg(_linhas[_emoji_linha], HK_FONT)
                _txm = int(os.environ.get("TXT_MARGEM", 8))
                # x: depois do fim REAL do texto (margem + largura) + folga tunável
                _ex = max(10, min(HK_MARGEM + _txm + (_lw or int(LARGURA * 0.5))
                                  + int(os.environ.get("HK_EMOJI_DX", 18)),
                                  LARGURA - HK_EMOJI_TAM - 10))
                # y: centra pela ALTURA DA FONTE (consistente entre claro/escuro; o
                # _alt do clip varia com o contorno) + nudge fino HK_EMOJI_DY.
                _ey = int(_y_emo + _txm + (HK_FONT - HK_EMOJI_TAM) / 2
                          + int(os.environ.get("HK_EMOJI_DY", 0)))
                _emo = ImageClip(str(_epath))
                _emo = _with_duration(_emo, dur_total)
                _emo = _with_start(_emo, 0.0)
                _emo = _with_position(_emo, (_ex, _ey))
                camadas.append(_emo)
        except Exception as e:
            log.warning(f"   ⚠️  Emoji do hook falhou (segue sem ele): {e}")

    return camadas


def _criar_cta_fixo(dur_total: float, mp) -> list:
    """
    CTA fixo abaixo do vídeo: COMENTE "QUERO" 👇 (texto + emoji colorido).
    Cor por fundo (branco→preto / preto→branco). Texto/posição via .env.
    """
    (_, _, ImageClip, _, _, _, TextClip) = mp
    camadas = []

    # ── DESLIGADO POR PADRÃO DESDE 02/09 ─────────────────────────────────────
    # O Dre: "retirar o CTA 'COMENTE QUERO', aumentar o vídeo nas bordas, igual
    # ao perfil deles". Nenhum dos dois perfis que estão crescendo
    # (@achad0ideal, @ofertasdaflorzinha) queima CTA no vídeo — os dois pedem o
    # comentário na LEGENDA. E os 1672px onde essa barra morava são exatamente
    # onde o Instagram desenha a própria interface do Reels por cima.
    #
    # A função continua existindo, e ligada por CTA_ATIVO=1, porque o caminho de
    # ANÚNCIO pode querer CTA queimado — lá o vídeo roda fora do feed.
    if os.environ.get("CTA_ATIVO", "0").strip().lower() not in ("1", "true", "sim"):
        log.info("   🚫 CTA queimado desligado (CTA_ATIVO=0) — o pedido sai na legenda")
        return camadas

    fonte_bold = _fonte_montserrat("Bold") or _resolver_fonte_textclip(TextClip)
    try:
        from shared.paleta import do_ambiente as _paleta_do_ambiente
        _claro = _paleta_do_ambiente()["claro"]
    except Exception:
        _bg = os.environ.get("TOPSHOP_BG", "preto").strip().lower()
        _claro = _bg in ("branco", "white", "bege", "claro")
    C_CTA = "black" if _claro else "white"
    SW_CTA = 0 if _claro else 4

    CTA_TXT  = os.environ.get("CTA_TEXTO", 'COMENTE "QUERO"')
    CTA_FONT = int(os.environ.get("CTA_FONT", 52))
    cta_y    = int(os.environ.get("CTA_Y", 1672))

    txt = _textclip_robusto(TextClip, CTA_TXT, font_size=CTA_FONT,
                            color=C_CTA, stroke_width=SW_CTA, stroke_color="black",
                            largura_frac=0.72, fonte=fonte_bold)
    if txt is not None:
        txt = _with_duration(txt, dur_total)
        txt = _with_start(txt, 0.0)
        txt = _with_position(txt, ("center", cta_y))
        camadas.append(txt)

    # emoji 👇 colorido à direita do texto (mede a largura real p/ posicionar)
    try:
        _m = _textclip_justo(TextClip, CTA_TXT, CTA_FONT, fonte_bold)
        _lw = getattr(_m, "w", 0) if _m is not None else 0
        if _m is not None:
            try: _m.close()
            except Exception: pass
        _fim = LARGURA // 2 + (_lw or int(LARGURA * 0.45)) // 2
        _et = int(os.environ.get("CTA_EMOJI", 50))
        _ep = _emoji_colorido_png("👇", _et)
        if _ep is not None:
            e = ImageClip(str(_ep))
            e = _with_duration(e, dur_total); e = _with_start(e, 0.0)
            _edy = int(os.environ.get("CTA_EMOJI_DY", 22))   # desce o 👇 p/ alinhar
            e = _with_position(e, (min(_fim + 14, LARGURA - _et - 8), cta_y + _edy))
            camadas.append(e)
    except Exception as e:
        log.warning(f"   ⚠️  Emoji do CTA falhou (segue sem): {e}")

    return camadas


def montar_video(produto: str, roteiro: dict, narracao_mp3: Path,
                  blocos_legenda: list, broll: list,
                  saida: Path, edl: Optional[dict] = None) -> dict:
    """
    Monta o vídeo. Dois modos:
      - COM EDL: executa a Edit Decision List (1 segmento por MICROCORTE,
        com trecho-fonte + efeito leve). Resolve a sensação de loop.
      - SEM EDL (fallback): 1 segmento por bloco (comportamento v1 antigo).

    Legendas são sempre por BLOCO (não por corte), sincronizadas.
    Returns: {sucesso, arquivo, duracao, erro}
    """
    mp = _import_moviepy()
    (VideoFileClip, AudioFileClip, ImageClip,
     CompositeVideoClip, concatenate_videoclips, ColorClip, TextClip) = mp

    abertos = []  # clips compostos a fechar no fim
    fontes  = []  # clips-fonte (VideoFileClip originais) — fechar p/ evitar WinError 6
    broll_por_nome = {b.name: b for b in broll}

    try:
        narr = AudioFileClip(str(narracao_mp3))
        dur_total = narr.duration

        segmentos = []

        if edl and edl.get("timeline"):
            # ── MODO EDL: um segmento por microcorte ──────────────────
            for corte in edl["timeline"]:
                dur_corte = max(0.5, corte["fim"] - corte["inicio"])
                asset_nome = corte.get("asset")
                caminho = broll_por_nome.get(asset_nome) if asset_nome else None

                seg = None
                if caminho is not None:
                    try:
                        seg = _preparar_corte_clip(
                            caminho, dur_corte,
                            corte.get("trecho_inicio", 0.0),
                            corte.get("trecho_fim", 0.0),
                            corte.get("efeito", "none"), mp, fontes)
                        log.info(f"   ✂️  {corte['inicio']:.1f}→{corte['fim']:.1f}s "
                                 f"[{corte['cena']}] {corte['efeito']} → {asset_nome}")
                    except Exception as e:
                        log.warning(f"      ⚠️  Falha no corte {asset_nome} "
                                    f"({str(e)[:50]}) — fundo sólido")
                        seg = None
                if seg is None:
                    seg = _with_duration(
                        ColorClip(size=(LARGURA, ALTURA), color=(20, 20, 30)), dur_corte)
                segmentos.append(seg)
                abertos.append(seg)
        else:
            # ── MODO FALLBACK: um segmento por bloco (v1 antigo) ──────
            frases = [b["texto"] for b in blocos_legenda]
            cenas_por_bloco = mapear_frases_para_cenas(frases)
            usados = set()
            for i, bloco in enumerate(blocos_legenda):
                dur_bloco = max(0.5, bloco["fim_seg"] - bloco["inicio_seg"])
                cena = cenas_por_bloco[i] if i < len(cenas_por_bloco) else "demo"
                seg = _segmento_robusto(broll, cena, usados, dur_bloco, mp, i + 1)
                if seg is None:
                    seg = _with_duration(
                        ColorClip(size=(LARGURA, ALTURA), color=(20, 20, 30)), dur_bloco)
                    log.warning(f"   🎬 Bloco {i+1} {cena} → (sem B-roll, fundo sólido) ({dur_bloco:.1f}s)")
                segmentos.append(seg)
                abertos.append(seg)

        if segmentos:
            fundo = concatenate_videoclips(segmentos)
        else:
            fundo = _with_duration(
                ColorClip(size=(LARGURA, ALTURA), color=(20, 20, 30)), dur_total)
        abertos.append(fundo)

        # Ajusta fundo à duração exata da narração
        if abs(fundo.duration - dur_total) > 0.1:
            fundo = _subclip_seguro(fundo, 0, dur_total)

        # ════════════════════════════════════════════════════════════
        # COMPOSIÇÃO COM TEMPLATE DE MARCA topshop (layout 3:4 fiel)
        # ════════════════════════════════════════════════════════════
        if TEMPLATE_MARCA:
            # Hook (texto que muda por vídeo) — vem do hook_builder
            if blocos_legenda:
                legenda_inicial = blocos_legenda[0]["texto"]
                try:
                    from creative_engine.hook_builder import construir_hook
                    hook_txt = construir_hook(produto, legenda_inicial=legenda_inicial,
                                              plano=roteiro)
                except Exception:
                    hook_txt = "OLHA ISSO 👀"
            else:
                hook_txt = "OLHA ISSO 👀"

            # 1) FUNDO DA MARCA atrás de tudo (a imagem escura com spotlight)
            camadas = []
            fundo_path = _brand_asset("fundo.png")
            if fundo_path is not None:
                try:
                    bg = ImageClip(str(fundo_path))
                    bg = _resize_clip(bg, largura=LARGURA)
                    # garante que cobre a altura toda
                    if bg.h < ALTURA:
                        bg = _resize_clip(bg, altura=ALTURA)
                    bg = _with_duration(bg, dur_total)
                    bg = _with_start(bg, 0.0)
                    bg = _with_position(bg, ("center", "center"))
                    camadas.append(bg)
                    abertos.append(bg)
                except Exception as e:
                    log.warning(f"   ⚠️  Fundo da marca falhou: {e}")

            # 2) O VÍDEO em 3:4, a 95% da largura (quase encostando nas bordas),
            #    CENTRALIZADO. Canvas 9:16 deixa preto em cima (marca+hook) e
            #    embaixo (CTA) — igual ao template manual do @topshop._.
            larg_video = int(LARGURA * 0.95)           # 1026px
            alt_video = int(larg_video * 4 / 3)         # 3:4 → 1368px
            vid = _resize_clip(fundo, largura=larg_video)
            vid = _crop_centro(vid, larg_video, alt_video)
            vid = _with_position(vid, ("center", "center"))
            camadas.append(vid)
            abertos.append(vid)

            # 3) Legendas da fala (por bloco) — posição relativa ao vídeo
            legendas_ok = 0
            for bloco in blocos_legenda:
                dur = max(0.5, bloco["fim_seg"] - bloco["inicio_seg"])
                leg = _criar_legenda(bloco["texto"], dur, bloco["inicio_seg"], mp)
                if leg is not None:
                    camadas.append(leg); abertos.append(leg); legendas_ok += 1

            # 4) Camadas do topo: logo + TopShop + selo + @ + hook
            for camada in _criar_camadas_topo(dur_total, hook_txt, mp, produto=produto):
                camadas.append(camada); abertos.append(camada)

            # 5) CTA fixo no rodapé
            for camada in _criar_cta_fixo(dur_total, mp):
                camadas.append(camada); abertos.append(camada)

            log.info(f"   🏷️  Template topshop aplicado (3:4, fundo + logo + "
                     f"marca + hook + CTA)")
            if legendas_ok:
                log.info(f"   📝 {legendas_ok}/{len(blocos_legenda)} legendas na tela")
        else:
            # ── Modo antigo (sem template): legendas + hook 2s + cta fim ──
            camadas = [fundo]
            legendas_ok = 0
            for bloco in blocos_legenda:
                dur = max(0.5, bloco["fim_seg"] - bloco["inicio_seg"])
                leg = _criar_legenda(bloco["texto"], dur, bloco["inicio_seg"], mp)
                if leg is not None:
                    camadas.append(leg); abertos.append(leg); legendas_ok += 1
            if blocos_legenda:
                legenda_inicial = blocos_legenda[0]["texto"]
                try:
                    from creative_engine.hook_builder import construir_hook
                    hook_txt = construir_hook(produto, legenda_inicial=legenda_inicial,
                                              plano=roteiro)
                except Exception:
                    hook_txt = "OLHA ISSO 👀"
                hook = _criar_hook(hook_txt, min(2.0, dur_total), mp)
                if hook is not None:
                    camadas.append(hook); abertos.append(hook)
            if blocos_legenda and dur_total > 3:
                try:
                    from creative_engine.hook_builder import cta_curto
                    cta_txt = cta_curto(produto)
                except Exception:
                    cta_txt = "LINK NA BIO 🔗"
                dur_cta = min(2.8, dur_total)
                cta = _criar_cta(cta_txt, dur_cta, dur_total - dur_cta, mp)
                if cta is not None:
                    camadas.append(cta); abertos.append(cta)

        video = CompositeVideoClip(camadas, size=(LARGURA, ALTURA))
        video = _with_duration(video, dur_total)
        video = _with_audio(video, narr)

        saida.parent.mkdir(parents=True, exist_ok=True)
        video.write_videofile(
            str(saida), fps=30, codec="libx264", audio_codec="aac",
            preset="ultrafast", threads=4, logger=None)

        # ── Fechamento ordenado pra eliminar "WinError 6" do GC do ffmpeg ──
        # A causa do crash: VideoFileClip-fonte deixados órfãos têm um leitor
        # ffmpeg que o __del__ tenta fechar no GC quando o processo já morreu.
        # Fechamos TUDO explicitamente aqui, incluindo readers internos.
        _fechar_tudo(video, narr, abertos, fontes)

        return {"sucesso": True, "arquivo": str(saida),
                "duracao": round(dur_total, 1), "erro": None}
    except Exception as e:
        _fechar_tudo(None, None, abertos, fontes)
        return {"sucesso": False, "arquivo": None, "duracao": 0,
                "erro": f"{type(e).__name__}: {str(e)[:200]}"}


def _fechar_clip_profundo(c):
    """Fecha um clip e seus leitores internos (video + audio) sem levantar erro."""
    if c is None:
        return
    # leitor de vídeo
    for attr in ("reader",):
        r = getattr(c, attr, None)
        if r is not None:
            try:
                r.close_proc() if hasattr(r, "close_proc") else None
            except Exception:
                pass
            try:
                r.close() if hasattr(r, "close") else None
            except Exception:
                pass
    # leitor de áudio do clip
    a = getattr(c, "audio", None)
    if a is not None:
        ar = getattr(a, "reader", None)
        if ar is not None:
            try:
                ar.close_proc() if hasattr(ar, "close_proc") else None
            except Exception:
                pass
    try:
        c.close()
    except Exception:
        pass


def _fechar_tudo(video, narr, abertos, fontes):
    """Fecha video composto, narração, compostos intermediários e fontes."""
    _fechar_clip_profundo(video)
    if narr is not None:
        try:
            narr.close()
        except Exception:
            pass
    for c in abertos:
        _fechar_clip_profundo(c)
    # fontes por último (são os VideoFileClip originais — origem do WinError 6)
    for c in fontes:
        _fechar_clip_profundo(c)


def _segmento_robusto(broll, cena, usados, dur_bloco, mp, num_bloco):
    """
    Tenta criar um segmento de B-roll pra uma cena. Robusto a falha de abertura:
    pula clip quebrado, tenta outro da mesma cena, depois fallback.
    Returns: clip ou None se tudo falhar.
    Marca o clip escolhido em `usados`.
    """
    # Monta lista de tentativas em ordem de preferência (sem repetir)
    tentativas = []
    da_cena = [b for b in broll if _cena_do_arquivo(b) == cena]
    tentativas += [b for b in da_cena if b not in usados]      # cena, livre
    tentativas += [b for b in da_cena if b in usados]          # cena, usado
    tentativas += [b for b in broll if b not in usados and b not in da_cena]  # outro livre
    tentativas += [b for b in broll if b not in tentativas]    # resto

    for caminho in tentativas:
        try:
            seg = _preparar_broll_clip(caminho, dur_bloco, mp)
            usados.add(caminho)
            log.info(f"   🎬 Bloco {num_bloco} {cena} → {caminho.name} ({dur_bloco:.1f}s)")
            return seg
        except Exception as e:
            log.warning(f"      ⚠️  Falha ao abrir {caminho.name} ({str(e)[:60]}) — tentando outro")
            continue
    return None


# =================================================================
# PIPELINE PRINCIPAL
# =================================================================

def gerar_video_narrado(produto: str, voz: str = VOZ_PADRAO,
                          dry_run: bool = False,
                          permitir_imagens: bool = False,
                          forcar_render: bool = False,
                          so_ia: bool = False) -> dict:
    log.info("=" * 60)
    log.info(f"🎙️  NARRATED VIDEO ENGINE — '{produto}'")
    log.info(f"   Voz: {voz} | Modo: {'DRY-RUN' if dry_run else 'REAL'}")
    log.info("=" * 60)

    slug = slugificar_produto(produto)
    plano = carregar_plano_mais_recente(produto)

    # 1) Roteiro
    roteiro = construir_roteiro(produto, plano)
    dur_estimada = sum(estimar_duracao_frase(f) for f in roteiro["frases"])
    log.info(f"\n📝 Roteiro ({roteiro['fonte']}, ~{dur_estimada:.0f}s):")
    for i, f in enumerate(roteiro["frases"], 1):
        log.info(f"   {i}. {f}")

    resultado = {
        "produto": produto, "slug": slug,
        "categoria": roteiro["categoria"], "fonte_roteiro": roteiro["fonte"],
        "frases": roteiro["frases"], "voz": voz,
        "dur_estimada": round(dur_estimada, 1),
        "broll_usado": [], "narracao": None, "video": None,
        "sucesso": False,
    }

    # 2) B-roll existente
    broll = coletar_broll_existente(produto, so_ia=so_ia)
    if so_ia:
        log.info("   🤖 Modo SÓ-IA: usando apenas cenas geradas por IA (ia_*), "
                 "ignorando B-roll genérico do Pexels/Pixabay")
    resultado["broll_usado"] = [str(b.name) for b in broll]
    if broll:
        log.info(f"\n🎬 B-roll existente: {len(broll)} arquivo(s)")
        for b in broll[:6]:
            log.info(f"   • {b.name}")
    else:
        log.warning(f"\n⚠️  Sem B-roll do produto — vídeo usaria fundo sólido")
        log.warning(f"   (rode Asset Autopilot/Creative Generator antes pra ter visual)")

    if dry_run:
        log.info(f"\n🔍 [DRY-RUN] Geraria narração com '{voz}', montaria vídeo "
                 f"vertical {LARGURA}x{ALTURA} com {len(broll)} B-roll(s) + legendas")
        log.info(f"   Saída seria: videos/{slug}_narrated.mp4")
        resultado["dry_run"] = True
        return resultado

    # Checagem de dependências
    if not edge_tts_disponivel():
        log.error(f"❌ {motivo_indisponivel()}")
        resultado["erro"] = motivo_indisponivel()
        return resultado
    if not _moviepy_disponivel():
        log.error(f"❌ MoviePy não disponível (pip install moviepy)")
        resultado["erro"] = "moviepy não instalado"
        return resultado

    # 3) Narração
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    mp3_path = TMP_DIR / f"{slug}_narr.mp3"
    log.info(f"\n🎙️  Gerando narração com Edge-TTS...")
    narr = gerar_narracao(roteiro["texto_completo"], mp3_path, voz=voz,
                           dur_minima_esperada=dur_estimada)
    if not narr["sucesso"]:
        log.error(f"❌ Narração falhou após {narr.get('tentativas_usadas', '?')} "
                  f"tentativa(s): {narr['erro']}")
        resultado["erro"] = narr["erro"]
        return resultado
    nb = len(narr["word_boundaries"])
    log.info(f"   ✅ Narração: {mp3_path.name} "
             f"({nb} boundaries, ~{narr.get('dur_aprox', '?')}s, "
             f"tentativa {narr.get('tentativas_usadas', 1)})")
    if nb == 0:
        log.info(f"   ℹ️  Sem word boundaries — legenda usará timing proporcional")
    resultado["narracao"] = str(mp3_path)

    # 4) Blocos de legenda (timing real via boundaries)
    # Estima dur real do mp3
    try:
        mp = _import_moviepy()
        AudioFileClip = mp[1]
        _a = AudioFileClip(str(mp3_path)); dur_real = _a.duration; _a.close()
    except Exception:
        dur_real = dur_estimada
    blocos = boundaries_para_blocos(roteiro["frases"],
                                     narr["word_boundaries"], dur_real)
    log.info(f"   📑 {len(blocos)} bloco(s) de legenda, dur total {dur_real:.1f}s")

    # 4.5) Editing Brain → Edit Decision List (microcortes anti-loop)
    edl = None
    try:
        from creative_engine.editing_brain import montar_edl, logar_edl
        cenas_bloco = mapear_frases_para_cenas([b["texto"] for b in blocos])
        audit_path = PLANS_DIR / "visual_audit_resultado.json"
        edl = montar_edl(
            produto, blocos, broll,
            cenas_por_bloco=cenas_bloco,
            audit_path=audit_path if audit_path.exists() else None,
            salvar_em=PLANS_DIR / "edit_decision_list.json")
        logar_edl(edl)
    except Exception as e:
        log.warning(f"⚠️  Editing Brain indisponível ({str(e)[:80]}) — "
                    f"montagem usará modo bloco (1 clipe por frase)")
        edl = None

    # 4.6) Quality Gate — barreira de qualidade ANTES de renderizar.
    # Um agente confiável sabe quando NÃO deve entregar.
    if edl:
        try:
            from creative_engine.quality_gate import avaliar_qualidade, logar_veredito
            veredito = avaliar_qualidade(edl, broll, permitir_imagens=permitir_imagens)
            logar_veredito(veredito)
            if not veredito["aprovado"] and not forcar_render:
                log.warning("\n🛑 Renderização ABORTADA pelo Quality Gate.")
                log.warning("   Use --forcar-render pra renderizar mesmo assim "
                            "(ou --permitir-imagens se o problema for imagem estática).")
                return {
                    "sucesso": False,
                    "erro": "quality_gate_bloqueou",
                    "motivos": veredito["motivos"],
                    "sugestao": veredito["sugestao"],
                    "metricas": veredito["metricas"],
                }
            elif not veredito["aprovado"] and forcar_render:
                log.warning("   ⚠️  Quality Gate reprovou, mas --forcar-render ativo — "
                            "renderizando mesmo assim")
        except Exception as e:
            log.warning(f"⚠️  Quality Gate indisponível ({str(e)[:80]}) — "
                        f"renderizando sem barreira")

    # 5) Monta vídeo
    saida = VIDEOS_DIR / f"{slug}_narrated.mp4"
    log.info(f"\n🎬 Montando vídeo {LARGURA}x{ALTURA}...")
    mont = montar_video(produto, roteiro, mp3_path, blocos, broll, saida, edl=edl)
    if not mont["sucesso"]:
        log.error(f"❌ Montagem falhou: {mont['erro']}")
        resultado["erro"] = mont["erro"]
        return resultado

    resultado["video"] = mont["arquivo"]
    resultado["duracao"] = mont["duracao"]
    resultado["sucesso"] = True

    # Defesa extra: vídeo muito curto vs roteiro = provável narração truncada
    if mont["duracao"] < dur_estimada * 0.5:
        log.warning(f"\n⚠️  ATENÇÃO: vídeo saiu com {mont['duracao']}s mas o roteiro "
                    f"estimava ~{dur_estimada:.0f}s.")
        log.warning(f"   Possível narração truncada (instabilidade Edge-TTS). "
                    f"Confira o vídeo — se estiver cortado, rode de novo.")
        resultado["alerta"] = "duracao_suspeita"
    log.info(f"\n✅ Vídeo narrado: {saida.name} ({mont['duracao']}s)")

    # 6) Memória
    if _MEM_OK:
        try:
            registrar_memoria(
                "aprendizado",
                f"Vídeo narrado gerado pra '{produto}' (voz {voz}, "
                f"{len(broll)} B-roll, {mont['duracao']}s)",
                tags=["narrated", "video", slug, roteiro["categoria"]])
            log.info(f"🧠 Aprendizado registrado")
        except Exception:
            pass

    log.info(f"\n{'═' * 60}")
    log.info(f"🏁 RESULTADO")
    log.info(f"   Vídeo: {saida}")
    log.info(f"   Duração: {mont['duracao']}s | B-roll: {len(broll)} | Voz: {voz}")
    log.info(f"{'═' * 60}")
    return resultado


# =================================================================
# CLI
# =================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Narrated Video Engine — vídeo narrado barato (Edge-TTS + MoviePy)")
    parser.add_argument("--produto", required=True, help="Nome do produto")
    parser.add_argument("--voz", default=VOZ_PADRAO,
                        help=f"Voz Edge-TTS (default {VOZ_PADRAO})")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="Mostra roteiro/plano sem gerar nada")
    parser.add_argument("--permitir-imagens", action="store_true", dest="permitir_imagens",
                        help="Permite mais imagens estáticas (relaxa o Quality Gate)")
    parser.add_argument("--forcar-render", action="store_true", dest="forcar_render",
                        help="Renderiza mesmo se o Quality Gate reprovar")
    parser.add_argument("--so-ia", action="store_true", dest="so_ia",
                        help="Usa SÓ cenas geradas por IA (ia_*), ignora B-roll "
                             "genérico do Pexels (resolve lixo acumulado)")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info(f"🎙️  NARRATED VIDEO ENGINE v1")
    log.info("=" * 60)

    r = gerar_video_narrado(args.produto, voz=args.voz, dry_run=args.dry_run,
                            permitir_imagens=args.permitir_imagens,
                            forcar_render=args.forcar_render,
                            so_ia=args.so_ia)

    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        (PLANS_DIR / "narrated_video_resultado.json").write_text(
            json.dumps(r, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass

    if r.get("sucesso") or r.get("dry_run"):
        return 0
    # Distingue BLOQUEIO do Quality Gate (decisão correta) de ERRO real.
    # Exit 3 = bloqueado pelo gate; o Production Runner trata como "bloqueado",
    # não como "erro" (não conta como falha do sistema).
    if r.get("erro") == "quality_gate_bloqueou":
        return 3
    return 1


if __name__ == "__main__":
    sys.exit(main())