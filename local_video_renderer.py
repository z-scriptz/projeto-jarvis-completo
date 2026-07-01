# creative_engine/local_video_renderer.py
# Renderizador de vídeo local via MoviePy + Pillow.
#
# Estratégia: TextClip do MoviePy depende de ImageMagick instalado, o que
# complica em ambientes Windows. Em vez disso, usamos Pillow pra desenhar
# o texto em um PIL.Image e convertemos pra ImageClip do MoviePy.
#
# Resultado: vídeo vertical 1080x1920 com:
#   - 1 cena de hook (primeira)
#   - N cenas intermediárias (descrição/texto_tela)
#   - 1 cena de CTA (última)
#
# Dependências: pip install moviepy imageio-ffmpeg pillow
#   (NÃO precisa de ImageMagick — usamos Pillow no lugar do TextClip)

import os
import re
from pathlib import Path
from typing import Optional

from shared.logger import get_logger

log = get_logger(__name__)


# =================================================================
# DETECTAR DEPENDÊNCIAS
# =================================================================

def _checar_dependencias() -> tuple[bool, str]:
    """Verifica se MoviePy e Pillow estão instalados. Retorna (ok, msg_erro)."""
    faltando = []
    try:
        import moviepy  # noqa
    except ImportError:
        faltando.append("moviepy")
    try:
        from PIL import Image  # noqa
    except ImportError:
        faltando.append("pillow")

    if faltando:
        msg = f"Dependência(s) ausente(s): {faltando}. Rode: pip install moviepy imageio-ffmpeg pillow"
        return False, msg
    return True, ""


# =================================================================
# HELPERS DE PATH
# =================================================================

def _slug(texto: str, max_len: int = 40) -> str:
    """Converte 'Mini Aspirador 🔥' → 'mini_aspirador'."""
    s = re.sub(r"[^\w\s-]", "", (texto or "").lower())
    s = re.sub(r"\s+", "_", s).strip("_")
    return s[:max_len] or "produto"


def _resolver_video_path(plano: dict, video_settings: dict) -> str:
    """
    Resolve o path final do vídeo:
      1. Usa plano["video_path_sugerido"] se existir
      2. Senão: C:\\AgenteIA\\videos\\video_auto_<slug>.mp4
    """
    sugerido = plano.get("video_path_sugerido", "").strip()
    if sugerido:
        return sugerido

    produto = plano.get("produto", "produto")
    return f"C:\\AgenteIA\\videos\\video_auto_{_slug(produto)}.mp4"


def _path_local(windows_path: str) -> Path:
    """
    Converte caminho Windows para o formato adequado ao SO atual.
    Necessário porque o agente pode rodar tanto no Windows quanto no WSL.
    """
    if os.name == "nt":
        return Path(windows_path)
    # WSL — usa o conversor centralizado
    from shared.path_utils import windows_to_wsl_path
    return Path(windows_to_wsl_path(windows_path))


# =================================================================
# RENDERIZADOR DE TEXTO VIA PILLOW
# =================================================================

def _carregar_fonte(tamanho: int):
    """
    Tenta carregar uma fonte legível. Cai em fontes nativas por SO.
    Funciona tanto no Windows quanto no Linux/WSL.
    """
    from PIL import ImageFont

    candidatas = []
    if os.name == "nt":
        candidatas = [
            "C:\\Windows\\Fonts\\arialbd.ttf",   # Arial Bold
            "C:\\Windows\\Fonts\\arial.ttf",
            "C:\\Windows\\Fonts\\segoeui.ttf",   # Segoe UI
        ]
    else:
        candidatas = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/mnt/c/Windows/Fonts/arialbd.ttf",  # WSL acessa fontes do Windows
            "/mnt/c/Windows/Fonts/arial.ttf",
        ]

    for fonte in candidatas:
        try:
            if Path(fonte).exists():
                return ImageFont.truetype(fonte, tamanho)
        except Exception:
            continue

    # Fallback final: fonte padrão do PIL (pequena mas funcional)
    log.warning("⚠️ Nenhuma fonte TTF encontrada — usando ImageFont.load_default() (pode ficar pequena)")
    return ImageFont.load_default()


def _quebrar_texto(texto: str, fonte, largura_max: int, draw) -> list[str]:
    """Quebra texto em linhas que cabem em largura_max pixels."""
    palavras = texto.split()
    linhas = []
    linha_atual = ""

    for palavra in palavras:
        teste = f"{linha_atual} {palavra}".strip()
        try:
            bbox = draw.textbbox((0, 0), teste, font=fonte)
            largura = bbox[2] - bbox[0]
        except AttributeError:
            # PIL antigo
            largura, _ = draw.textsize(teste, font=fonte)

        if largura <= largura_max:
            linha_atual = teste
        else:
            if linha_atual:
                linhas.append(linha_atual)
            linha_atual = palavra

    if linha_atual:
        linhas.append(linha_atual)

    return linhas


def _renderizar_frame_cena(
    texto: str,
    largura: int,
    altura: int,
    bg_color: str,
    text_color: str,
    accent_color: str,
    eh_hook: bool = False,
    eh_cta: bool = False,
):
    """
    Renderiza UM frame (PIL.Image) com o texto centralizado.
    Retorna numpy array RGB pronto pra MoviePy.

    Estilos:
        eh_hook → texto MAIOR + accent color (chamativo)
        eh_cta  → fundo accent + ícone "🛒 Link na bio"
        normal  → texto branco em fundo escuro
    """
    from PIL import Image, ImageDraw
    import numpy as np

    # Cor de fundo (CTA tem fundo destacado)
    cor_fundo = accent_color if eh_cta else bg_color
    img = Image.new("RGB", (largura, altura), color=cor_fundo)
    draw = ImageDraw.Draw(img)

    # Tamanho de fonte adapta-se ao papel da cena
    tamanho_fonte = 110 if eh_hook else (95 if eh_cta else 80)
    fonte = _carregar_fonte(tamanho_fonte)

    # Cor do texto: branco no fundo escuro; branco no CTA também (contraste alto)
    cor_texto = text_color

    # Quebra de linha — margem horizontal de 80px de cada lado
    margem = 80
    largura_max = largura - (2 * margem)
    linhas = _quebrar_texto(texto, fonte, largura_max, draw)

    # Mede altura total e centraliza verticalmente
    altura_linha = tamanho_fonte + 20  # espaçamento entre linhas
    altura_total = len(linhas) * altura_linha
    y_inicio = (altura - altura_total) // 2

    # Desenha cada linha
    for i, linha in enumerate(linhas):
        try:
            bbox = draw.textbbox((0, 0), linha, font=fonte)
            largura_linha = bbox[2] - bbox[0]
        except AttributeError:
            largura_linha, _ = draw.textsize(linha, font=fonte)

        x = (largura - largura_linha) // 2
        y = y_inicio + (i * altura_linha)

        # Sombra/contorno pra legibilidade (preto offset 4px)
        for offset in [(3, 3), (-3, 3), (3, -3), (-3, -3)]:
            draw.text((x + offset[0], y + offset[1]), linha, font=fonte, fill="#000000")
        # Texto principal
        draw.text((x, y), linha, font=fonte, fill=cor_texto)

    # Marca d'água no canto inferior (sutil)
    fonte_pequena = _carregar_fonte(28)
    rodape = "AgenteIA" if not eh_cta else "🛒 Link na bio!"
    draw.text((margem, altura - 80), rodape, font=fonte_pequena, fill="#ffffff")

    return np.array(img)


# =================================================================
# RENDERIZADOR PRINCIPAL
# =================================================================

def renderizar_video_local(plano: dict, config: Optional[dict] = None) -> dict:
    """
    Renderiza um vídeo .mp4 vertical 1080x1920 a partir do plano criativo.

    Args:
        plano:  dict do content_planner com hook, cenas, cta, video_path_sugerido
        config: dict opcional de video_settings (vem do providers_config.json)

    Returns:
        {
            "sucesso":     bool,
            "mensagem":    str,
            "video_path":  str | None,
            "duracao":     float,
            "num_cenas":   int,
            "provider":    "local_moviepy",
        }
    """
    # ── 1. Checar dependências ────────────────────────────────────────
    ok, erro = _checar_dependencias()
    if not ok:
        log.error(f"❌ {erro}")
        return {
            "sucesso":    False,
            "mensagem":   erro,
            "video_path": None,
            "duracao":    0,
            "num_cenas":  0,
            "provider":   "local_moviepy",
        }

    # Imports protegidos (já validados acima)
    from moviepy import ImageClip, concatenate_videoclips

    # ── 2. Settings com defaults ──────────────────────────────────────
    cfg = config or {}
    largura       = int(cfg.get("width",  1080))
    altura        = int(cfg.get("height", 1920))
    fps           = int(cfg.get("fps",    30))
    duracao_total = float(cfg.get("duracao_padrao", 12))
    bg_color      = cfg.get("bg_color",     "#1a1a2e")
    text_color    = cfg.get("text_color",   "#ffffff")
    accent_color  = cfg.get("accent_color", "#ff2e63")

    # ── 3. Montar lista de cenas (hook + intermediárias + cta) ───────
    cenas_plano = plano.get("cenas", []) or []
    hook   = plano.get("hook", "Você precisa ver isso 👀")
    cta    = plano.get("cta",  "Link na bio! 🛒")

    # Define textos de cada cena
    cenas_a_renderizar = []

    # Cena 1: hook (sempre)
    cenas_a_renderizar.append({"texto": hook, "tipo": "hook"})

    # Cenas intermediárias: usa texto_tela ou descricao das cenas do plano
    # Pula primeira e última do plano se quisermos manter hook/cta separados,
    # mas como o plano também já começa com hook e termina com cta, vamos usar
    # apenas as cenas do meio (índices 1 até -2) — quando existirem.
    if len(cenas_plano) >= 3:
        for cena in cenas_plano[1:-1]:
            texto = cena.get("texto_tela") or cena.get("descricao") or ""
            if texto.strip():
                cenas_a_renderizar.append({"texto": texto, "tipo": "intermediaria"})
    elif len(cenas_plano) == 2:
        # Plano curtinho — usa a cena do meio se houver
        cena = cenas_plano[0]
        texto = cena.get("texto_tela") or cena.get("descricao") or ""
        if texto.strip():
            cenas_a_renderizar.append({"texto": texto, "tipo": "intermediaria"})
    else:
        # Plano sem cenas — adiciona uma cena genérica usando o produto
        produto = plano.get("produto", "esse produto")
        cenas_a_renderizar.append({
            "texto": f"{produto} ✨\nFunciona DEMAIS",
            "tipo":  "intermediaria",
        })

    # Cena final: CTA (sempre)
    cenas_a_renderizar.append({"texto": cta, "tipo": "cta"})

    num_cenas = len(cenas_a_renderizar)
    duracao_por_cena = duracao_total / num_cenas
    log.info(f"🎬 Renderizando {num_cenas} cena(s) × {duracao_por_cena:.2f}s = {duracao_total}s")

    # ── 4. Renderizar cada cena como ImageClip ────────────────────────
    clips = []
    for i, cena in enumerate(cenas_a_renderizar, start=1):
        try:
            log.info(f"  🖼️  Cena {i}/{num_cenas} [{cena['tipo']}]: '{cena['texto'][:50]}...'")
            frame = _renderizar_frame_cena(
                texto=cena["texto"],
                largura=largura,
                altura=altura,
                bg_color=bg_color,
                text_color=text_color,
                accent_color=accent_color,
                eh_hook=(cena["tipo"] == "hook"),
                eh_cta=(cena["tipo"] == "cta"),
            )
            clip = ImageClip(frame, duration=duracao_por_cena)
            clips.append(clip)
        except Exception as e:
            log.error(f"  ❌ Falha ao renderizar cena {i}: {e}")
            return {
                "sucesso":    False,
                "mensagem":   f"Erro ao renderizar cena {i}: {e}",
                "video_path": None,
                "duracao":    0,
                "num_cenas":  num_cenas,
                "provider":   "local_moviepy",
            }

    # ── 5. Concatenar e exportar ──────────────────────────────────────
    video_path_windows = _resolver_video_path(plano, cfg)
    video_path_local   = _path_local(video_path_windows)

    # Cria pasta de destino se não existir
    try:
        video_path_local.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log.error(f"❌ Não foi possível criar pasta de destino: {e}")
        return {
            "sucesso":    False,
            "mensagem":   f"Erro ao criar pasta: {e}",
            "video_path": None,
            "duracao":    0,
            "num_cenas":  num_cenas,
            "provider":   "local_moviepy",
        }

    log.info(f"🎞️ Concatenando clips → {video_path_local}")

    try:
        video_final = concatenate_videoclips(clips, method="chain")
        video_final.write_videofile(
            str(video_path_local),
            fps=fps,
            codec="libx264",
            audio=False,
            preset="medium",
            ffmpeg_params=["-pix_fmt", "yuv420p"],  # ← TikTok exige yuv420p; sem isso rejeita silenciosamente
            logger=None,  # silencia barra do MoviePy
        )
        video_final.close()
        for c in clips:
            try:
                c.close()
            except Exception:
                pass

    except Exception as e:
        log.error(f"❌ Falha ao exportar vídeo: {e}")
        return {
            "sucesso":    False,
            "mensagem":   f"Erro ao exportar MP4: {e}",
            "video_path": None,
            "duracao":    0,
            "num_cenas":  num_cenas,
            "provider":   "local_moviepy",
        }

    log.info(f"✅ Vídeo renderizado: {video_path_local}")

    return {
        "sucesso":    True,
        "mensagem":   f"Vídeo renderizado com sucesso ({num_cenas} cenas, {duracao_total}s)",
        "video_path": video_path_windows,   # sempre devolve em formato Windows (espera-se pelo workflow)
        "duracao":    duracao_total,
        "num_cenas":  num_cenas,
        "provider":   "local_moviepy",
    }


# =================================================================
# TESTE VIA TERMINAL
# =================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  🎞️ Local Video Renderer — Teste")
    print("=" * 60)

    plano_teste = {
        "produto":  "Umidificador de Ar Mini com LED",
        "hook":     "Você PRECISA conhecer esse Umidificador 👀",
        "cta":      "Link na bio! Corre que tá acabando 🔥",
        "cenas": [
            {"tempo": "0-2s",  "texto_tela": "Você PRECISA ver isso 👀",  "descricao": "Hook"},
            {"tempo": "2-5s",  "texto_tela": "Umidificador Mini ✨",      "descricao": "Mostra produto"},
            {"tempo": "5-8s",  "texto_tela": "Funciona DEMAIS 🔥",        "descricao": "Demonstração"},
            {"tempo": "8-12s", "texto_tela": "Link na bio! 🛒",           "descricao": "CTA"},
        ],
        "video_path_sugerido": "C:\\AgenteIA\\videos\\umidificador_de_ar_mini_com_led.mp4",
    }

    config_teste = {
        "width":           1080,
        "height":          1920,
        "fps":             30,
        "duracao_padrao":  12,
        "bg_color":        "#1a1a2e",
        "text_color":      "#ffffff",
        "accent_color":    "#ff2e63",
    }

    resultado = renderizar_video_local(plano_teste, config_teste)

    print(f"\n  Sucesso:    {resultado['sucesso']}")
    print(f"  Mensagem:   {resultado['mensagem']}")
    print(f"  Vídeo:      {resultado['video_path']}")
    print(f"  Duração:    {resultado['duracao']}s")
    print(f"  Cenas:      {resultado['num_cenas']}")
    print(f"  Provider:   {resultado['provider']}")
    print("=" * 60)