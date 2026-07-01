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
MARCA_HANDLE = "@topshop._"
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
        out = TMP_DIR / "logo_ts_circular.png"
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


def _criar_camadas_topo(dur_total: float, hook_txt: str, mp) -> list:
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

    logo_x, logo_y, logo_tam = 65, 90, 120

    # ── Logo TS REDONDO (canto superior esquerdo) ──
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

    texto_x = logo_x + logo_tam - 32

    # ── 'TopShop' PRETO (Bold) com contorno BRANCO ──
    nome = _textclip_robusto(TextClip, MARCA_NOME, font_size=56,
                             color="black", stroke_width=4, stroke_color="white",
                             largura_frac=0.32, fonte=fonte_bold, text_align="West")
    fim_topshop_x = texto_x + 235  # fallback se não der pra medir
    if nome is not None:
        nome = _with_duration(nome, dur_total)
        nome = _with_start(nome, 0.0)
        nome = _with_position(nome, (texto_x, logo_y - 12))
        camadas.append(nome)

    # ── Selo verificado — posiciona após a largura REAL do texto 'TopShop'.
    #    Mede criando um clip JUSTO (label) só pra ler a largura do texto,
    #    em vez de estimar (o clip 'caption' tem caixa larga e engana). ──
    selo_aparado = _emoji_aparado("verificado.png", 46)
    if selo_aparado is not None:
        try:
            # mede a largura real do "TopShop" com um TextClip justo (sem caixa)
            larg_real = None
            try:
                medidor = _textclip_justo(TextClip, MARCA_NOME, 56, fonte_bold)
                if medidor is not None:
                    larg_real = medidor.w
                    try: medidor.close()
                    except Exception: pass
            except Exception:
                pass
            if larg_real:
                # +50 extra: compensa a caixa do TextClip que pode centralizar
                # o texto (text_align nem sempre é suportado pela versão)
                selo_x = texto_x + larg_real + 64
            else:
                selo_x = texto_x + 290  # fallback estimado
            selo = ImageClip(str(selo_aparado))
            selo = _with_duration(selo, dur_total)
            selo = _with_start(selo, 0.0)
            selo = _with_position(selo, (selo_x, logo_y + 14))
            camadas.append(selo)
            log.info(f"   ✔️  Selo verificado em x={selo_x} (larg real TopShop={larg_real})")
        except Exception as e:
            log.warning(f"   ⚠️  Selo verificado falhou: {e}")
    else:
        log.warning("   ⚠️  verificado.png NÃO encontrado na pasta brand!")

    # ── '@topshop._' BRANCO (Bold) com contorno PRETO ──
    handle = _textclip_robusto(TextClip, MARCA_HANDLE, font_size=46,
                               color="white", stroke_width=3, stroke_color="black",
                               largura_frac=0.34, fonte=fonte_bold, text_align="West")
    if handle is not None:
        handle = _with_duration(handle, dur_total)
        handle = _with_start(handle, 0.0)
        handle = _with_position(handle, (texto_x, logo_y + 42))
        camadas.append(handle)

    # ── Hook com SOMBRA + texto branco — na faixa preta acima do vídeo ──
    hook_y = 198   # faixa preta de cima, abaixo da marca
    sombra = _textclip_robusto(TextClip, hook_txt, font_size=38,
                               color="black", stroke_width=0, stroke_color="black",
                               largura_frac=0.9, fonte=fonte_bold)
    if sombra is not None:
        sombra = _with_opacity(sombra, 0.55)
        sombra = _with_duration(sombra, dur_total)
        sombra = _with_start(sombra, 0.0)
        sombra = _with_position(sombra, ("center", hook_y + 4))
        camadas.append(sombra)
    hook = _textclip_robusto(TextClip, hook_txt, font_size=38,
                             color="white", stroke_width=3, stroke_color="black",
                             largura_frac=0.9, fonte=fonte_bold)
    if hook is not None:
        hook = _with_duration(hook, dur_total)
        hook = _with_start(hook, 0.0)
        hook = _with_position(hook, ("center", hook_y))
        camadas.append(hook)
        log.info(f"   📌 Hook: \"{hook_txt}\"")
        # (Emoji do hook removido — hook fica limpo, só o texto com sombra.)

    return camadas


def _criar_cta_fixo(dur_total: float, mp) -> list:
    """
    CTA fixo abaixo do vídeo: 'LINK NA BIO!' em Montserrat Bold PARRUDO
    (texto branco com contorno preto grosso), com emojis 🛒 e 🔥 como PNGs
    coloridos ao lado (carrinho.png e fogo.png na pasta brand).
    Retorna lista de camadas.
    """
    (_, _, ImageClip, _, _, _, TextClip) = mp
    camadas = []
    fonte_bold = _fonte_montserrat("Bold") or _resolver_fonte_textclip(TextClip)
    cta_y = 1645   # quase encostando no rodapé do vídeo (termina ~1644)

    # texto central, parrudo (stroke grosso pra destacar)
    txt = _textclip_robusto(TextClip, "LINK NA BIO!", font_size=54,
                            color="white", stroke_width=4, stroke_color="black",
                            largura_frac=0.55, fonte=fonte_bold)
    larg_texto = int(LARGURA * 0.55)
    if txt is not None:
        txt = _with_duration(txt, dur_total)
        txt = _with_start(txt, 0.0)
        txt = _with_position(txt, ("center", cta_y))
        camadas.append(txt)

    # Posiciona os emojis com base na largura REAL estimada do texto
    # "LINK NA BIO!" (não na caixa, que é maior). Texto centralizado.
    larg_texto_real = int(len("LINK NA BIO!") * 54 * 0.52)  # ~337px
    centro = LARGURA // 2
    fim_texto = centro + larg_texto_real // 2
    inicio_texto = centro - larg_texto_real // 2

    # carrinho (🛒) à ESQUERDA do texto — autocrop, mais pra baixo
    carrinho = _emoji_aparado("carrinho.png", 56)
    if carrinho is not None:
        try:
            c = ImageClip(str(carrinho))
            c = _with_duration(c, dur_total); c = _with_start(c, 0.0)
            c = _with_position(c, (inicio_texto - 56 - 18, cta_y + 22))
            camadas.append(c)
        except Exception as e:
            log.warning(f"   ⚠️  Emoji carrinho falhou: {e}")
    else:
        log.warning("   ⚠️  carrinho.png NÃO encontrado na pasta brand!")

    # fogo (🔥) à DIREITA do texto — autocrop, tamanho aprovado, mais pra baixo
    fogo = _emoji_aparado("fogo.png", 85)
    if fogo is not None:
        try:
            f = ImageClip(str(fogo))
            f = _with_duration(f, dur_total); f = _with_start(f, 0.0)
            f = _with_position(f, (fim_texto + 18, cta_y + 20))
            camadas.append(f)
        except Exception as e:
            log.warning(f"   ⚠️  Emoji fogo falhou: {e}")
    else:
        log.warning("   ⚠️  fogo.png NÃO encontrado na pasta brand!")

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
            for camada in _criar_camadas_topo(dur_total, hook_txt, mp):
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