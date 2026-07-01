# creative_engine/product_video_renderer.py
# Product Video Renderer v1 do AgenteIA (Jarvis).
#
# Diferente do local_video_renderer (que gera placeholder com fundo+texto),
# este renderer monta vídeo REAL de afiliado usando clipes organizados
# pelo Asset Hunter. Estrutura padrão TikTok:
#
#   [dor 2-3s] → [demo 5-7s] → [resultado 3-4s] → [close 2-3s] → [cta 2-3s]
#
# Total alvo: 14-20s, formato vertical 9:16 (1080x1920).
#
# Filosofia:
#   - NUNCA chama Gemini, NUNCA abre TikTok, NUNCA posta
#   - Não depende de quota
#   - Falha de forma CLARA se clipes do seed (fakes) forem inválidos
#   - Retorna status estruturado: pode ser "Video_Renderizado",
#     "Aguardando_Assets" ou "Assets_Invalidos"
#
# Uso direto:
#   python -m creative_engine.product_video_renderer
#   python -m creative_engine.product_video_renderer --produto "Mini Aspirador de Teclado"
#
# Uso programático (Creative Engine v2 / Asset Router):
#   from creative_engine.product_video_renderer import renderizar_video_produto_com_assets
#   r = renderizar_video_produto_com_assets(
#           produto="Mini Aspirador de Teclado",
#           plano={"hook": "Seu teclado tá LIXO 🤮?", "cta": "Corre pro link na bio!"},
#       )
#   if r["status"] == "Aguardando_Assets":
#       # marcar produto na planilha
#   elif r["sucesso"]:
#       # subir r["video_path"] no TikTok

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

from shared.logger import get_logger

# Asset Agent (verificação + slug)
from agents.asset_agent import (
    slugificar_produto,
    verificar_assets_produto,
    ASSETS_ROOT as PRODUTOS_ROOT,
)

log = get_logger(__name__)

# =================================================================
# COMPATIBILIDADE MoviePy 1.x ↔ 2.x
# =================================================================
# MoviePy 2.x mudou:
#   - imports: 'from moviepy import ...' (não mais 'moviepy.editor')
#   - métodos: clip.cropped(), clip.resized(), clip.subclipped(),
#              clip.with_audio() em vez de set_audio()
#   - fx: 'moviepy.video.fx.crop' e similares foram reorganizados
#
# Estratégia: tenta v2 primeiro, fallback pra v1. Helpers centralizam tudo.

# Detector de versão — usado pra decidir entre métodos novos/velhos
_MOVIEPY_V2 = None  # cache do resultado depois da 1ª detecção


def _is_moviepy_v2() -> bool:
    """Detecta se é MoviePy 2.x baseado em existência de método/import."""
    global _MOVIEPY_V2
    if _MOVIEPY_V2 is not None:
        return _MOVIEPY_V2
    try:
        # Em 2.x, 'from moviepy import VideoFileClip' funciona direto
        # Em 1.x, só funciona via 'moviepy.editor'
        from moviepy import VideoFileClip  # type: ignore
        _MOVIEPY_V2 = True
    except ImportError:
        _MOVIEPY_V2 = False
    return _MOVIEPY_V2


def _import_moviepy():
    """
    Import compatível v1 e v2. Tenta v2 (sem .editor) primeiro,
    fallback pra v1 (com .editor).

    Returns:
        (VideoFileClip, AudioFileClip, ImageClip,
         CompositeVideoClip, concatenate_videoclips)
    """
    try:
        from moviepy import (              # type: ignore
            VideoFileClip,
            AudioFileClip,
            ImageClip,
            CompositeVideoClip,
            concatenate_videoclips,
        )
    except ImportError:
        from moviepy.editor import (       # type: ignore
            VideoFileClip,
            AudioFileClip,
            ImageClip,
            CompositeVideoClip,
            concatenate_videoclips,
        )
    return (VideoFileClip, AudioFileClip, ImageClip,
            CompositeVideoClip, concatenate_videoclips)


def _subclip(clip, inicio: float, fim: float):
    """Compat: clip.subclipped() em 2.x, clip.subclip() em 1.x."""
    if hasattr(clip, "subclipped"):
        return clip.subclipped(inicio, fim)
    return clip.subclip(inicio, fim)


def _set_audio(clip, audio):
    """Compat: clip.with_audio() em 2.x, clip.set_audio() em 1.x."""
    if hasattr(clip, "with_audio"):
        return clip.with_audio(audio)
    return clip.set_audio(audio)


def _crop_clip(clip, x1, x2, y1, y2):
    """
    Crop compatível. Em 2.x, usa clip.cropped(). Em 1.x, usa fx.crop.
    Fallback final: retorna clip original.
    """
    try:
        if hasattr(clip, "cropped"):
            return clip.cropped(x1=x1, y1=y1, x2=x2, y2=y2)
    except Exception:
        pass
    try:
        from moviepy.video.fx.crop import crop  # type: ignore
        return crop(clip, x1=x1, x2=x2, y1=y1, y2=y2)
    except ImportError:
        pass
    try:
        from moviepy.video.fx.Crop import Crop  # type: ignore (2.x algumas builds)
        return clip.fx(Crop, x1=x1, x2=x2, y1=y1, y2=y2)
    except ImportError:
        pass
    return clip


def _resize_clip(clip, newsize):
    """Resize compatível: clip.resized() em 2.x, fx.resize em 1.x."""
    try:
        if hasattr(clip, "resized"):
            return clip.resized(newsize)
    except Exception:
        pass
    try:
        from moviepy.video.fx.resize import resize  # type: ignore
        return resize(clip, newsize=newsize)
    except ImportError:
        pass
    try:
        from moviepy.video.fx.Resize import Resize  # type: ignore
        return clip.fx(Resize, new_size=newsize)
    except ImportError:
        pass
    return clip


def _audio_fadein(clip, dur: float):
    """Fade in de áudio — compat v1/v2."""
    try:
        if hasattr(clip, "with_effects"):
            from moviepy.audio.fx import AudioFadeIn   # type: ignore
            return clip.with_effects([AudioFadeIn(dur)])
    except Exception:
        pass
    try:
        from moviepy.audio.fx.audio_fadein import audio_fadein  # type: ignore
        return audio_fadein(clip, dur)
    except ImportError:
        pass
    return clip  # fallback: sem fade


def _audio_fadeout(clip, dur: float):
    """Fade out de áudio — compat v1/v2."""
    try:
        if hasattr(clip, "with_effects"):
            from moviepy.audio.fx import AudioFadeOut  # type: ignore
            return clip.with_effects([AudioFadeOut(dur)])
    except Exception:
        pass
    try:
        from moviepy.audio.fx.audio_fadeout import audio_fadeout  # type: ignore
        return audio_fadeout(clip, dur)
    except ImportError:
        pass
    return clip  # fallback: sem fade


# =================================================================
# CONFIGURAÇÃO
# =================================================================

PROJETO_ROOT  = Path(__file__).parent.parent
VIDEOS_DIR    = PROJETO_ROOT / "videos"

# Formato alvo (TikTok)
LARGURA_ALVO  = 1080
ALTURA_ALVO   = 1920
FPS_ALVO      = 30
AR_ALVO       = LARGURA_ALVO / ALTURA_ALVO   # 9:16 = 0.5625

# Duração alvo de cada cena (segundos) — ordem importa (= ordem do render)
CENAS_ORDEM = [
    ("dor",       2.5),
    ("demo",      6.0),
    ("resultado", 3.5),
    ("close",     2.5),
    ("cta",       2.5),
]
DURACAO_TOTAL_MAX = sum(d for _, d in CENAS_ORDEM)  # 17.0s

# Mínimo de clipes válidos pra justificar render
MIN_CLIPES_VALIDOS = 2

# Transições
CROSSFADE_SEG     = 0.3
FADE_AUDIO_SEG    = 0.5

# =================================================================
# DETECTAR DEPENDÊNCIAS
# =================================================================

def _checar_dependencias() -> tuple[bool, str]:
    """Retorna (ok, mensagem). Não crasha — só reporta."""
    try:
        _import_moviepy()
    except ImportError as e:
        return False, f"moviepy não disponível ({e}) — pip install moviepy"
    except Exception as e:
        return False, f"moviepy presente mas falhou ao importar: {e}"
    versao = "2.x" if _is_moviepy_v2() else "1.x"
    return True, f"moviepy {versao} ok"


# =================================================================
# LEITURA E SELEÇÃO DE CLIPES
# =================================================================

def _ler_propositos_do_metadata(slug: str) -> dict:
    """Lê propositos_clipes do metadata.json, se existir."""
    meta_path = PRODUTOS_ROOT / slug / "metadata.json"
    if not meta_path.exists():
        return {}
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return meta.get("propositos_clipes") or {}
    except Exception as e:
        log.warning(f"metadata.json corrompido pro slug '{slug}': {e}")
        return {}


def _selecionar_clipes_por_proposito(slug: str, propositos: dict) -> dict:
    """
    Retorna {proposito: Path do arquivo} priorizando o primeiro clipe
    de cada propósito encontrado em raw/.

    Se houver múltiplos arquivos pro mesmo propósito (ex: 2 demos),
    pega o de maior tamanho (heurística: mais conteúdo).
    """
    raw_dir = PRODUTOS_ROOT / slug / "raw"
    if not raw_dir.exists():
        return {}

    # Inverte: {proposito: [Path, Path, ...]}
    por_proposito: dict[str, list[Path]] = {}
    for arquivo, prop in propositos.items():
        caminho = raw_dir / arquivo
        if caminho.exists():
            por_proposito.setdefault(prop, []).append(caminho)

    # Pra cada propósito, pega o de maior tamanho
    selecionados = {}
    for prop, lista in por_proposito.items():
        if not lista:
            continue
        melhor = max(lista, key=lambda p: p.stat().st_size if p.exists() else 0)
        selecionados[prop] = melhor

    return selecionados


def _selecionar_audio(slug: str) -> Optional[Path]:
    """Pega o primeiro arquivo de áudio da pasta, se existir."""
    audio_dir = PRODUTOS_ROOT / slug / "audio"
    if not audio_dir.exists():
        return None
    for ext in (".mp3", ".m4a", ".wav", ".ogg", ".aac"):
        for arq in sorted(audio_dir.iterdir()):
            if arq.suffix.lower() == ext and arq.is_file():
                return arq
    return None


# =================================================================
# ABERTURA SEGURA DE CLIPES (capta corrompido/fake)
# =================================================================

def _tentar_abrir_clipe(caminho: Path, duracao_alvo: float) -> tuple[Optional[object], Optional[str]]:
    """
    Tenta abrir um clipe e cortá-lo para a duração alvo.
    Retorna (clip, None) se sucesso, (None, motivo_erro) se falhou.

    Estratégia de corte: se o clipe é mais longo que duracao_alvo,
    pega o trecho do MEIO (geralmente tem mais ação que início/fim).
    """
    try:
        VideoFileClip, *_ = _import_moviepy()
    except ImportError:
        return None, "moviepy não disponível"

    try:
        clip = VideoFileClip(str(caminho))
    except Exception as e:
        return None, f"abertura falhou: {str(e)[:140]}"

    try:
        dur_real = float(clip.duration or 0)
        if dur_real <= 0:
            clip.close()
            return None, "duração zero ou inválida"

        # Corta: se clipe é maior que alvo, pega trecho central
        if dur_real > duracao_alvo:
            inicio = (dur_real - duracao_alvo) / 2
            fim    = inicio + duracao_alvo
            clip   = _subclip(clip, inicio, fim)
        # Se for menor, deixa como está (fica abaixo do alvo, sem alongar)

        return clip, None
    except Exception as e:
        try:
            clip.close()
        except Exception:
            pass
        return None, f"corte falhou: {str(e)[:140]}"


# =================================================================
# AJUSTE 9:16 (crop central pra horizontais)
# =================================================================

def _ajustar_para_vertical(clip):
    """
    Garante que o clipe sai em 9:16 (1080x1920).

    Estratégia:
      - Já é vertical (AR ≈ 9:16): só redimensiona pra 1080x1920
      - É horizontal/quadrado: faz CROP CENTRAL pra forçar AR 9:16,
        depois redimensiona pra 1080x1920
    """
    try:
        w, h = clip.w, clip.h
        if not w or not h:
            return _resize_clip(clip, (LARGURA_ALVO, ALTURA_ALVO))

        ar_atual = w / h

        # Tolerância: se já está próximo de 9:16, só redimensiona
        if abs(ar_atual - AR_ALVO) < 0.05:
            return _resize_clip(clip, (LARGURA_ALVO, ALTURA_ALVO))

        # Crop central pra forçar AR 9:16
        if ar_atual > AR_ALVO:
            # Vídeo mais largo → corta laterais
            nova_largura = int(h * AR_ALVO)
            x_centro = w / 2
            x1 = int(x_centro - nova_largura / 2)
            x2 = int(x_centro + nova_largura / 2)
            clip_cortado = _crop_clip(clip, x1=x1, x2=x2, y1=0, y2=h)
        else:
            # Vídeo mais alto que 9:16 → corta topo/base
            nova_altura = int(w / AR_ALVO)
            y_centro = h / 2
            y1 = int(y_centro - nova_altura / 2)
            y2 = int(y_centro + nova_altura / 2)
            clip_cortado = _crop_clip(clip, x1=0, x2=w, y1=y1, y2=y2)

        return _resize_clip(clip_cortado, (LARGURA_ALVO, ALTURA_ALVO))
    except Exception as e:
        log.warning(f"Ajuste 9:16 falhou: {e} — usando resize bruto")
        try:
            return _resize_clip(clip, (LARGURA_ALVO, ALTURA_ALVO))
        except Exception:
            return clip


# =================================================================
# OVERLAY DE TEXTO (hook + cta) — opcional, só se plano vier
# =================================================================

def _adicionar_texto_overlay(clip, texto: str, posicao: str = "top"):
    """
    Sobrepõe texto grande no clipe via Pillow (sem ImageMagick).
    posicao: 'top' (hook) ou 'bottom' (cta).

    Falha silenciosamente: se Pillow/numpy não funcionar, devolve clip sem texto.
    """
    if not texto:
        return clip
    try:
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np
        _, _, ImageClip, CompositeVideoClip, _ = _import_moviepy()
    except ImportError:
        return clip

    try:
        # Cria imagem transparente do tamanho do vídeo
        img = Image.new("RGBA", (LARGURA_ALVO, ALTURA_ALVO), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Fonte: tenta carregar padrão grande, fallback pra default
        try:
            font = ImageFont.truetype("arial.ttf", 90)
        except Exception:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 90)
            except Exception:
                font = ImageFont.load_default()

        # Quebra texto em linhas (~25 chars por linha)
        palavras = texto.split()
        linhas, atual = [], ""
        for p in palavras:
            if len(atual + " " + p) <= 25:
                atual = (atual + " " + p).strip()
            else:
                if atual:
                    linhas.append(atual)
                atual = p
        if atual:
            linhas.append(atual)

        # Posição vertical
        altura_total_texto = len(linhas) * 110
        if posicao == "top":
            y = 150
        else:  # bottom
            y = ALTURA_ALVO - altura_total_texto - 200

        # Desenha cada linha com fundo escuro pra contraste
        for linha in linhas:
            try:
                bbox = draw.textbbox((0, 0), linha, font=font)
                tw = bbox[2] - bbox[0]
            except Exception:
                tw = len(linha) * 45
            x = (LARGURA_ALVO - tw) // 2
            # Fundo preto semi-transparente
            draw.rectangle([(x - 20, y - 10), (x + tw + 20, y + 100)],
                           fill=(0, 0, 0, 180))
            # Texto branco
            draw.text((x, y), linha, font=font, fill=(255, 255, 255, 255))
            y += 110

        # Converte pra ImageClip e sobrepõe (compat v1/v2)
        arr = np.array(img)
        try:
            text_clip = ImageClip(arr, transparent=True, duration=clip.duration)
        except TypeError:
            # MoviePy 2.x: ImageClip não aceita duration no construtor
            text_clip = ImageClip(arr, transparent=True)
            if hasattr(text_clip, "with_duration"):
                text_clip = text_clip.with_duration(clip.duration)
            elif hasattr(text_clip, "set_duration"):
                text_clip = text_clip.set_duration(clip.duration)
        return CompositeVideoClip([clip, text_clip])
    except Exception as e:
        log.warning(f"Overlay de texto falhou (continuando sem): {e}")
        return clip


# =================================================================
# RENDERIZAÇÃO PRINCIPAL
# =================================================================

def renderizar_video_produto_com_assets(
    produto: str,
    plano: Optional[dict] = None,
    output_path: Optional[str] = None,
    permitir_assets_insuficientes: bool = False,
) -> dict:
    """
    Monta vídeo TikTok 9:16 a partir dos clipes reais do produto.

    Args:
        produto:     Nome do produto (ex: "Mini Aspirador de Teclado")
        plano:       Opcional. Dict com 'hook' e 'cta' pra overlay de texto.
                     Se None, monta vídeo limpo só com clipes.
        output_path: Opcional. Caminho completo do MP4 final.
                     Default produção: videos/<slug>_asset_render.mp4
                     Default modo teste: videos/<slug>_asset_render_TESTE.mp4
        permitir_assets_insuficientes:
                     Se True, ignora gate "deve_aguardar" do Asset Agent e
                     tenta renderizar com o que tiver (mínimo 1 clipe válido).
                     ⚠️  Modo de teste/diagnóstico — vídeo gerado NÃO deve ser
                     publicado. Status retornado vira "Video_Renderizado_Teste"
                     e dict tem `modo_teste: True`.

    Returns:
        Dict com chaves:
            - sucesso: bool
            - status: "Video_Renderizado" | "Video_Renderizado_Teste"
                    | "Aguardando_Assets" | "Assets_Invalidos" | "Erro"
            - modo_teste: bool (True se permitir_assets_insuficientes ativou)
            - video_path: str | None
            - produto, assets_usados, duracao, score_assets, score_video,
              erros_clipes, mensagem
    """
    log.info("=" * 60)
    log.info(f"🎬 PRODUCT VIDEO RENDERER — '{produto}'")
    log.info("=" * 60)
    inicio = time.time()

    resposta_base = {
        "produto":       produto,
        "slug":          slugificar_produto(produto),
        "video_path":    None,
        "assets_usados": [],
        "erros_clipes":  [],
        "duracao":       0,
        "score_assets":  0,
        "score_video":   0,
        "modo_teste":    permitir_assets_insuficientes,
        "timestamp":     time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Aviso gordo se modo teste estiver ligado — pra ninguém confundir depois
    if permitir_assets_insuficientes:
        log.warning("=" * 60)
        log.warning("⚠️  MODO FORCE ATIVADO — render de teste com assets insuficientes")
        log.warning("    Vídeo gerado NÃO deve ser publicado no TikTok.")
        log.warning("    Saída irá para arquivo com sufixo _TESTE.mp4 por segurança.")
        log.warning("=" * 60)

    # ── 0. Dependências ──
    ok_dep, msg_dep = _checar_dependencias()
    if not ok_dep:
        return {**resposta_base, "sucesso": False, "status": "Erro",
                "mensagem": msg_dep}

    # ── 1. Verificar assets do produto ──
    log.info("\n1️⃣  Verificando status dos assets...")
    status = verificar_assets_produto(produto)
    resposta_base["score_assets"] = status["score_prontidao"]
    resposta_base["slug"]         = status["slug"]

    log.info(f"   Status: {status['status']} | Score: {status['score_prontidao']}/100")

    if status.get("deve_aguardar"):
        if not permitir_assets_insuficientes:
            log.warning(f"⏸️  Produto não está pronto pra render — {status['status']}")
            return {
                **resposta_base,
                "sucesso":  False,
                "status":   "Aguardando_Assets",
                "mensagem": (
                    f"Assets insuficientes ({status['status']}). "
                    f"{status.get('recomendacoes', ['Adicione mais clipes em raw/'])[0]}"
                ),
            }
        # Modo teste: segue mesmo com assets insuficientes
        log.warning(
            f"   ⚡ Bypass do gate 'deve_aguardar' ativo — "
            f"prosseguindo mesmo com status='{status['status']}'"
        )

    slug = status["slug"]

    # ── 2. Ler propósitos do metadata ──
    log.info("\n2️⃣  Lendo metadata.json...")
    propositos = _ler_propositos_do_metadata(slug)
    if not propositos:
        log.warning("metadata.json sem propositos_clipes — tente rodar Asset Hunter primeiro")
        return {
            **resposta_base,
            "sucesso":  False,
            "status":   "Assets_Invalidos",
            "mensagem": "Nenhum propósito de clipe registrado no metadata. Rode o Asset Hunter.",
        }

    # ── 3. Selecionar clipes ──
    log.info("\n3️⃣  Selecionando clipes por propósito...")
    selecionados = _selecionar_clipes_por_proposito(slug, propositos)
    log.info(f"   Encontrados: {list(selecionados.keys())}")

    if not selecionados:
        return {
            **resposta_base,
            "sucesso":  False,
            "status":   "Assets_Invalidos",
            "mensagem": "Nenhum clipe encontrado na pasta raw/ que bata com metadata.",
        }

    # ── 4. Abrir e cortar clipes na ordem certa ──
    log.info("\n4️⃣  Abrindo e cortando clipes (na ordem dor → demo → resultado → close → cta)...")
    clipes_prontos = []
    erros_clipes   = []
    propositos_usados = []

    for prop, dur_alvo in CENAS_ORDEM:
        if prop not in selecionados:
            log.info(f"   ⏭️  Cena '{prop}' não disponível — pulando")
            continue

        caminho = selecionados[prop]
        clip, erro = _tentar_abrir_clipe(caminho, dur_alvo)
        if erro:
            log.warning(f"   ❌ '{prop}' ({caminho.name}): {erro}")
            erros_clipes.append({
                "proposito": prop,
                "arquivo":   caminho.name,
                "erro":      erro,
            })
            continue

        # Ajusta pra vertical 9:16
        try:
            clip_v = _ajustar_para_vertical(clip)
        except Exception as e:
            log.warning(f"   ⚠️  Ajuste vertical falhou em '{prop}': {e}")
            clip.close()
            erros_clipes.append({"proposito": prop, "arquivo": caminho.name,
                                  "erro": f"ajuste 9:16 falhou: {e}"})
            continue

        # Hook overlay no primeiro clipe (se tiver plano)
        if prop == CENAS_ORDEM[0][0] and plano and plano.get("hook"):
            clip_v = _adicionar_texto_overlay(clip_v, plano["hook"], posicao="top")

        # CTA overlay no último (se for cta e tiver plano)
        if prop == "cta" and plano and plano.get("cta"):
            clip_v = _adicionar_texto_overlay(clip_v, plano["cta"], posicao="bottom")

        clipes_prontos.append(clip_v)
        propositos_usados.append(prop)
        log.info(f"   ✅ '{prop}' OK ({caminho.name}, {clip_v.duration:.1f}s)")

    # ── 5. Validação: mínimo de clipes válidos ──
    # Em produção: precisa de pelo menos MIN_CLIPES_VALIDOS (=2) cenas
    # Em modo teste: aceita até 1 — só pra validar pipeline com 1 clipe único
    min_efetivo = 1 if permitir_assets_insuficientes else MIN_CLIPES_VALIDOS
    if len(clipes_prontos) < min_efetivo:
        log.error(f"\n❌ Apenas {len(clipes_prontos)} clipe(s) válido(s) — mínimo é {min_efetivo}")
        for c in clipes_prontos:
            try:
                c.close()
            except Exception:
                pass
        return {
            **resposta_base,
            "sucesso":      False,
            "status":       "Assets_Invalidos",
            "mensagem":     (f"Assets existem ({len(propositos)} no metadata), "
                             f"mas só {len(clipes_prontos)} clipe(s) abriu como vídeo válido. "
                             f"{'Em modo teste precisa de pelo menos 1.' if permitir_assets_insuficientes else 'Substitua os arquivos do seed por clipes reais.'}"),
            "erros_clipes": erros_clipes,
        }

    # ── 6. Concatenar com crossfade ──
    log.info(f"\n5️⃣  Concatenando {len(clipes_prontos)} cena(s)...")
    *_, concatenate_videoclips = _import_moviepy()
    try:
        if len(clipes_prontos) == 1:
            # Caso especial: 1 clipe só (modo teste). Sem concatenate/crossfade.
            log.info("   ⚡ 1 clipe só — pulando concatenate, usando direto")
            video_final = clipes_prontos[0]
        else:
            # method='compose' suporta clips de tamanhos diferentes (mesmo já normalizados)
            # padding negativo cria crossfade
            video_final = concatenate_videoclips(
                clipes_prontos,
                method="compose",
                padding=-CROSSFADE_SEG,
            )
    except Exception as e:
        log.error(f"❌ Falha ao concatenar: {e}")
        for c in clipes_prontos:
            try:
                c.close()
            except Exception:
                pass
        return {
            **resposta_base,
            "sucesso":  False,
            "status":   "Erro",
            "mensagem": f"Erro ao concatenar clipes: {e}",
            "erros_clipes": erros_clipes,
        }

    duracao_total = round(float(video_final.duration or 0), 2)

    # ── 7. Áudio (trilha dedicada se existir) ──
    audio_path = _selecionar_audio(slug)
    usar_audio = False
    audio_clip = None
    if audio_path:
        log.info(f"\n6️⃣  Carregando trilha de áudio: {audio_path.name}")
        try:
            _, AudioFileClip, *_ = _import_moviepy()

            audio_raw = AudioFileClip(str(audio_path))
            # Ajusta duração do áudio à do vídeo (loop ou corte)
            if audio_raw.duration < duracao_total:
                # Áudio mais curto que o vídeo — corta vídeo pra duração do áudio
                # ou deixa loop? Vou cortar o áudio (mais simples e seguro)
                audio_clip = _subclip(audio_raw, 0, audio_raw.duration)
                log.info(f"   ⚠️  Trilha mais curta ({audio_raw.duration:.1f}s) que vídeo ({duracao_total}s)")
            else:
                audio_clip = _subclip(audio_raw, 0, duracao_total)

            # Fade in/out (helpers cuidam da compat)
            audio_clip = _audio_fadein(audio_clip, FADE_AUDIO_SEG)
            audio_clip = _audio_fadeout(audio_clip, FADE_AUDIO_SEG)
            video_final = _set_audio(video_final, audio_clip)
            usar_audio = True
            log.info(f"   ✅ Trilha aplicada com fade in/out")
        except Exception as e:
            log.warning(f"   ⚠️  Falha ao aplicar áudio: {e} — render sem áudio")

    # ── 8. Determinar output path ──
    if output_path:
        path_out = Path(output_path)
    else:
        VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        sufixo = "_TESTE" if permitir_assets_insuficientes else ""
        path_out = VIDEOS_DIR / f"{slug}_asset_render{sufixo}.mp4"

    # Backup se já existir
    if path_out.exists():
        backup = path_out.with_suffix(".mp4.bak")
        try:
            shutil.move(str(path_out), str(backup))
            log.info(f"   💾 Backup do vídeo anterior em: {backup.name}")
        except Exception:
            pass

    # ── 9. Exportar ──
    log.info(f"\n7️⃣  Exportando vídeo final para: {path_out.name}")
    try:
        # Parâmetros base (compatíveis v1 e v2)
        write_kwargs = {
            "fps":           FPS_ALVO,
            "codec":         "libx264",
            "preset":        "medium",
            "ffmpeg_params": ["-pix_fmt", "yuv420p"],
            "logger":        None,
        }
        # Em 2.x, 'audio' como bool foi removido. Detecta auto pelo clip.
        # Em 1.x, audio=True/False ainda é aceito.
        if not _is_moviepy_v2():
            write_kwargs["audio"] = usar_audio
        video_final.write_videofile(str(path_out), **write_kwargs)
    except Exception as e:
        log.error(f"❌ Falha ao exportar MP4: {e}")
        return {
            **resposta_base,
            "sucesso":      False,
            "status":       "Erro",
            "mensagem":     f"Erro ao exportar MP4: {e}",
            "erros_clipes": erros_clipes,
            "duracao":      duracao_total,
        }
    finally:
        # Limpa clipes da memória
        try:
            video_final.close()
        except Exception:
            pass
        for c in clipes_prontos:
            try:
                c.close()
            except Exception:
                pass
        if audio_clip:
            try:
                audio_clip.close()
            except Exception:
                pass

    # ── 10. Calcular score do vídeo final ──
    score_video = 0
    score_video += min(60, len(propositos_usados) * 12)   # 12 pts/cena, max 60
    if usar_audio:                                          # 15 pts: tem áudio
        score_video += 15
    if "dor" in propositos_usados and "cta" in propositos_usados:  # 15 pts: hook+cta
        score_video += 15
    if not erros_clipes:                                    # 10 pts: sem erro
        score_video += 10

    # Em modo teste, limita score a 60 — mesmo que técnicamente passe,
    # o vídeo não é apto pra produção
    if permitir_assets_insuficientes:
        score_video = min(score_video, 60)

    duracao_final = round(time.time() - inicio, 2)
    log.info(f"\n✅ Renderização concluída em {duracao_final}s")

    status_final = "Video_Renderizado_Teste" if permitir_assets_insuficientes else "Video_Renderizado"
    msg_base = (f"Vídeo renderizado com {len(propositos_usados)} cena(s), "
                f"{duracao_total}s, score={score_video}/100")
    if permitir_assets_insuficientes:
        msg_base += " ⚠️  MODO TESTE — NÃO PUBLICAR no TikTok, só validação técnica"

    return {
        **resposta_base,
        "sucesso":          True,
        "status":           status_final,
        "video_path":       str(path_out),
        "assets_usados":    [str(selecionados[p].relative_to(PROJETO_ROOT))
                             for p in propositos_usados if p in selecionados],
        "propositos_usados": propositos_usados,
        "duracao":          duracao_total,
        "score_video":      score_video,
        "usou_audio":       usar_audio,
        "erros_clipes":     erros_clipes,
        "duracao_render_s": duracao_final,
        "mensagem":         msg_base,
    }


# =================================================================
# RELATÓRIO IMPRESSO
# =================================================================

def imprimir_relatorio(r: dict):
    print("\n" + "=" * 60)
    print(f"  🎬 PRODUCT VIDEO RENDERER — Relatório")
    print("=" * 60)
    print(f"  Produto:  {r['produto']}")
    print(f"  Slug:     {r['slug']}")
    print(f"  Status:   {r['status']}")
    if r.get("modo_teste"):
        print(f"  ⚠️  MODO TESTE — NÃO PUBLICAR este vídeo")

    if r["sucesso"]:
        print(f"\n  ✅ Vídeo salvo em: {r['video_path']}")
        print(f"     Duração:       {r['duracao']}s")
        print(f"     Score vídeo:   {r['score_video']}/100")
        print(f"     Score assets:  {r['score_assets']}/100")
        print(f"     Tem áudio:     {'✅' if r.get('usou_audio') else '❌'}")
        print(f"     Cenas usadas:  {r.get('propositos_usados', [])}")
        if r.get("modo_teste"):
            print(f"\n  🧪 Use este render apenas para validar pipeline técnico:")
            print(f"     - MoviePy abre o(s) clipe(s)?")
            print(f"     - Crop 9:16 funciona?")
            print(f"     - Export yuv420p OK?")
            print(f"     Pra produção real: adicione mais clipes (mínimo 3).")
    else:
        print(f"\n  ❌ Falha: {r.get('mensagem', '?')}")
        if r.get("erros_clipes"):
            print(f"\n  📋 Erros por clipe:")
            for e in r["erros_clipes"]:
                print(f"     • [{e['proposito']:10s}] {e['arquivo']}: {e['erro']}")

    print("=" * 60)


# =================================================================
# CLI
# =================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Product Video Renderer — monta vídeo 9:16 com clipes reais"
    )
    parser.add_argument("--produto", default="Mini Aspirador de Teclado",
                        help="Nome do produto alvo")
    parser.add_argument("--hook", default="",
                        help="Texto pra overlay no início (opcional)")
    parser.add_argument("--cta", default="",
                        help="Texto pra overlay no final (opcional)")
    parser.add_argument("--output", default="",
                        help="Caminho do MP4 final (default: videos/<slug>_asset_render.mp4 "
                             "ou videos/<slug>_asset_render_TESTE.mp4 em modo --force)")
    # Aliases pro mesmo flag — você mencionou os 2 nomes
    parser.add_argument("--force", "--allow-insufficient",
                        dest="force",
                        action="store_true",
                        help="Modo de teste: renderiza mesmo se Asset Agent disser "
                             "'deve_aguardar=True'. Mínimo de clipes vira 1. "
                             "Vídeo gerado NÃO deve ser publicado.")
    args = parser.parse_args()

    plano = {}
    if args.hook:
        plano["hook"] = args.hook
    if args.cta:
        plano["cta"] = args.cta

    r = renderizar_video_produto_com_assets(
        produto=args.produto,
        plano=plano or None,
        output_path=args.output or None,
        permitir_assets_insuficientes=args.force,
    )
    imprimir_relatorio(r)

    # Exit codes: 0 sucesso, 1 aguardar, 2 erro
    # Teste OK também conta como sucesso (0) — pipeline técnico validou
    if r["status"] in ("Video_Renderizado", "Video_Renderizado_Teste"):
        return 0
    elif r["status"] == "Aguardando_Assets":
        return 1
    else:
        return 2


if __name__ == "__main__":
    sys.exit(main())