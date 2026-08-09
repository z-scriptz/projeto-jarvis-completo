#!/usr/bin/env python3
# render.py -- EDL -> MP4. O último elo: a linha do tempo vira vídeo.
#
# A CADEIA INTEIRA, PRA NÃO PERDER O FIO
#   storyboard.py  decide O QUE comunicar   (hook, narração, ordem)
#   edl.py         decide COMO comunicar    (corte, zoom, legenda, som)
#   render.py      EXECUTA                  (pixel, áudio, arquivo)
#
# Este arquivo não toma decisão criativa nenhuma. Se o vídeo ficou lento, o
# conserto é no edl.py; se a frase ficou fraca, é no storyboard.py. Aqui só se
# conserta o que saiu diferente do que o EDL mandou — e é justamente essa
# separação que deixa trocar o FFmpeg depois sem tocar no cérebro criativo.
#
# ─────────────────────────────────────────────────────────────────────────────
# O QUE EU MEDI ANTES DE ESCREVER (e mudou o desenho)
#
# 1) A NARRAÇÃO REAL NÃO CABE NO TEMPO PLANEJADO.
#    O edl.py estima a fala em 15 caracteres por segundo. Gerei o MP3 do hook
#    "Passei anos improvisando e resolvi por menos do que imaginava": o
#    storyboard reservou 2,5s e o Edge-TTS devolveu 3,89s. Renderizar pelo
#    plano cortaria a voz no meio da frase — no primeiro vídeo, na primeira
#    frase, que é a única que decide se alguém fica.
#    Por isso existe o passo CONFORMAR: gera a voz PRIMEIRO, mede, e estica a
#    linha do tempo pra caber. O EDL já previa isso ("quando existir o MP3 da
#    narração, a duração real dele manda").
#
# 2) O TEXTO SAI EM DOIS LUGARES, E ISSO FOI MEDIDO, NÃO ESCOLHIDO.
#    O `drawtext` do FFmpeg não existe em todo build — o estático que testei tem
#    libfreetype ligado e mesmo assim não traz o filtro. Sobrou libass. Só que
#    libass NÃO PINTA EMOJI: num quadro de teste com 😩 👆 😮‍💨 🔥 💡, forçando até
#    a Noto Color Emoji como fonte do estilo, ele desenhou todos em preto e
#    branco e ainda quebrou a sequência ZWJ do 😮‍💨 em dois desenhos soltos.
#    O Pillow desenha os mesmos emoji CORRETAMENTE, coloridos e com o ZWJ
#    composto (`embedded_color=True` na NotoColorEmoji). Daí a divisão:
#      PIL    o que é FIXO — cabeçalho, hook, barra de CTA. Tem emoji.
#      libass o que ANIMA  — legendas e destaques. Sem emoji (não precisam:
#             legenda é transcrição de narração).
#
# 3) O TEMPLATE É O QUE JÁ ESTÁ NO AR, não um que eu inventei.
#    O Dre mandou o print do feed: fundo BRANCO, cabeçalho pequeno no alto
#    (logo redonda · TopShop · selo · @), HOOK EM PRETO à esquerda logo abaixo,
#    a mídia como um bloco de largura cheia no meio, e a barra fixa
#    `COMENTE "QUERO" 👉` embaixo. O hook fica a favor do vídeo INTEIRO — não só
#    durante a seção do hook. Vídeo original que entra no feed com outro layout
#    lê como se fosse de outra conta.
#
# 4) SÓ A MÍDIA SE MEXE.
#    O zoom é aplicado à FAIXA DA MÍDIA, e o template branco entra por cima,
#    inteiro e parado. Na 1ª versão eu zoomava o quadro montado e o punch-in
#    ampliava a logo junto — e o cartão da foto saía da tela a partir de 1,06.
#
# O QUE AINDA NÃO SAI DAQUI (dito na cara, não escondido no código):
#   • transição "whip" — sai corte seco. O "flash" sai, desenhado no ASS.
#   • SFX (whoosh/pop/impacto) — não há arquivo de som no projeto.
#   • música de fundo — não há arquivo. E música do Instagram não se baixa:
#     entra no app (ou pelo Metricool). Por isso o piloto é modo `narracao`.
# O relatório no fim lista tudo o que faltou. Aviso que não avisa é pior que
# aviso nenhum.
#
# Uso:
#   python3 render.py --edl shared/edl/x.json --imagens pasta/ --saida out.mp4
#   python3 render.py --edl ... --imagens ... --mudo          (sem narração)
#   python3 render.py --edl ... --imagens ... --quadros 6     (só PNGs, sem MP4)

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BRAND_DIR = BASE_DIR / "assets" / "brand"
SAIDA_DIR = BASE_DIR / "shared" / "renders"

LARG, ALT = 1080, 1920
FPS = 30
SUPER = 2                      # a placa é renderizada em 2x: sobra de pixel
                               # pro punch-in não amolecer a imagem

# ── GEOMETRIA DO TEMPLATE TOPSHOP ────────────────────────────────────────────
#
# ⚠️ ESTES NÚMEROS NÃO SÃO MEUS. Eu os tinha tirado "no olho" de um print do
# feed e ERRAM QUASE TODOS. O Dre corrigiu: o template está no projeto, é só
# ler como os vídeos são feitos hoje. Os valores abaixo vêm de
#   narrated_video_agent._criar_camadas_topo / _criar_cta_fixo   (marca e hook)
#   telegram_repurpose_hunter (layout 3:4)                       (faixa do vídeo)
#   produzir_tiktok (regra do fundo por nicho)
# com os MESMOS nomes de variável de ambiente e os MESMOS padrões. Ajustar o
# template continua sendo mexer no .env, num lugar só, e os dois renderizadores
# obedecem — que é a diferença entre um template e dois parecidos.
#
# O que eu tinha errado, pra ficar registrado: logo 64 (é 120), nome 42 (é 56),
# handle 34 (é 46), margem 52 (é 55), hook 46 (é 48), mídia na largura cheia
# (é 82% centrada, em 3:4), topo da mídia calculado a partir do hook (é FIXO em
# 470, e é o HOOK que sobe), CTA 👉 a 95px do pé (é 👇 em CTA_Y=1672).
LOGO_X, LOGO_Y, LOGO_TAM = 100, 112, 120
NOME_FONT, HANDLE_FONT = 56, 46
TEXTO_DX, SELO_DX, SELO_TAM = 16, 12, 46

HK_MARGEM, HK_MARGEM_DIR = 55, 45
HK_FONT, HK_FONT_MIN = 48, 34
HK_ALTURA_LINHA = 62
HK_GAP_VIDEO = 16              # respiro entre o rodapé do hook e o topo do vídeo
HK_EMOJI_TAM = 40

# A FAIXA DA MÍDIA É FIXA, e é o hook que se move.
# Eu tinha invertido: calculava o topo da mídia a partir do tamanho do hook, o
# que faz a mídia dançar de vídeo pra vídeo conforme o hook tem 1 ou 2 linhas —
# e num feed em grade isso salta aos olhos. O template real ancora o RODAPÉ do
# hook logo acima do vídeo: a mídia fica sempre no mesmo lugar e o hook cresce
# pra cima.
VIDEO_Y = 470
VIDEO_W_FRAC = 0.82            # 885px de largura num quadro de 1080
VIDEO_ASPECTO = 4 / 3          # 3:4 -> 1180px de altura

CTA_TEXTO = 'COMENTE "QUERO"'
CTA_EMOJI = "👇"               # é 👇, não 👉 — o CTA aponta pro campo de comentário
CTA_FONT = 52
CTA_Y = 1672

# A NotoColorEmoji é bitmap (CBDT): o Pillow só a abre no tamanho da strike.
# Desenha-se em 109 e reduz-se — é o que faz o emoji sair colorido e nítido.
FONTE_EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
STRIKE_EMOJI = 109

PAUSA_APOS_FALA = 0.25         # respiro no fim de cada bloco de narração; sem
                               # ele a última sílaba encosta no corte seguinte
PISO_LEGENDA = 0.25            # nenhum bloco de legenda fica menos que isto na
                               # tela, mesmo que a voz o diga correndo

# Cor da legenda em ASS é &HBBGGRR (invertido em relação ao HTML).
COR_BRANCO = "&H00FFFFFF"
COR_PRETO = "&H00000000"
COR_OURO = "&H0042C5F5"        # #F5C542


def _log(m):
    print(f"[render] {m}", flush=True)


# ── FFmpeg ───────────────────────────────────────────────────────────────────

def _ffmpeg() -> str:
    """Caminho do ffmpeg. Prefere o do sistema; cai no estático do imageio.

    O estático existe pra máquina sem apt (foi o caso do ambiente onde isto
    foi escrito e testado). Na VPS o do sistema ganha, que é o mesmo que a
    produção de hoje já usa.
    """
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ""


def _tem_filtro(ff: str, nome: str) -> bool:
    try:
        s = subprocess.run([ff, "-hide_banner", "-filters"],
                           capture_output=True, text=True, timeout=30).stdout
        return re.search(rf"^\s*\S+\s+{re.escape(nome)}\s", s, re.M) is not None
    except Exception:
        return False


def _dur_midia(ff: str, arq: Path) -> float:
    """Duração em segundos, lendo o cabeçalho pelo próprio ffmpeg.

    Sem ffprobe de propósito: o binário estático do imageio traz só o ffmpeg, e
    depender do ffprobe faria o render falhar em máquina que só tem um dos dois.
    """
    try:
        r = subprocess.run([ff, "-hide_banner", "-i", str(arq)],
                           capture_output=True, text=True, timeout=60)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", r.stderr)
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return h * 3600 + mi * 60 + s
    except Exception:
        pass
    return 0.0


# ── Texto ────────────────────────────────────────────────────────────────────

_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE00-\U0000FE0F"
    "\U0001F1E6-\U0001F1FF\U00002190-\U000021FF\U00002B00-\U00002BFF\u200d]+")


def _limpar_fala(t: str) -> str:
    """Tira emoji antes de mandar pro TTS.

    O hook aprovado termina em 😮‍💨 e o CTA em 👆. Emoji no texto do TTS ou vira
    silêncio ou vira a leitura do nome do símbolo — e "polegar para cima" no
    fim do CTA estraga o único momento em que a pessoa decide clicar.
    """
    return re.sub(r"\s{2,}", " ", _EMOJI.sub(" ", t or "")).strip(" .,;:")


def _limpar_tela(t: str) -> str:
    """Tira emoji do texto QUE VAI PRA TELA. Isto dói, e é medido.

    Renderizei um quadro de teste com 😩 👆 😮‍💨 🔥 💡 em duas fontes, inclusive
    forçando a Noto Color Emoji como fonte do estilo. O libass deste FFmpeg
    desenhou TODOS em preto e branco, pequenos, e ainda quebrou a sequência ZWJ
    do 😮‍💨 em dois desenhos soltos. Não é ajuste de tamanho: libass aqui não
    pinta emoji colorido, ponto.

    O projeto já tinha resolvido isso do jeito certo em outro lugar: o
    narrated_video_agent NÃO escreve emoji como texto, ele cola PNG de emoji da
    pasta brand (_emoji_aparado). Esse é o caminho da v2 deste render. Enquanto
    ele não existe aqui, emoji quebrado na tela é pior que emoji nenhum — o
    hook é a única frase que decide se a pessoa fica, e um quadrado torto no fim
    dela entrega vídeo automático.

    O emoji continua na LEGENDA do post (outro arquivo, outro caminho). Some só
    do que é queimado no vídeo.
    """
    return re.sub(r"\s{2,}", " ", _EMOJI.sub(" ", t or "")).strip()


def _ass_escapar(t: str) -> str:
    return (t or "").replace("\\", "\\\\").replace("{", "\\{") \
                    .replace("}", "\\}").replace("\n", "\\N")


def _ass_tempo(s: float) -> str:
    s = max(0.0, s)
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    return f"{h}:{m:02d}:{s % 60:05.2f}"


# ── Texto com emoji (PIL) ────────────────────────────────────────────────────
#
# Aqui mora a razão de o hook ser desenhado em PIL e não em ASS: o libass deste
# FFmpeg pinta emoji em preto e branco e quebra sequência ZWJ; o Pillow pinta
# colorido e compõe o ZWJ certo. O template publicado usa emoji em quase todo
# hook (🧸 😊 😎 🏅) e na barra `COMENTE "QUERO" 👉` — sem isso o vídeo original
# não se parece com o que a conta já publica.

_CACHE_EMOJI = {}


def _img_emoji(seq: str, altura: int):
    """Um pedaço de emoji virado imagem, na altura pedida. None se não der."""
    chave = (seq, altura)
    if chave in _CACHE_EMOJI:
        return _CACHE_EMOJI[chave]
    from PIL import Image, ImageDraw, ImageFont
    try:
        f = ImageFont.truetype(FONTE_EMOJI, STRIKE_EMOJI)
    except Exception:
        _CACHE_EMOJI[chave] = None
        return None
    try:
        tela = Image.new("RGBA", (STRIKE_EMOJI * 3 * max(1, len(seq)),
                                  int(STRIKE_EMOJI * 1.6)), (0, 0, 0, 0))
        ImageDraw.Draw(tela).text((0, 0), seq, font=f, embedded_color=True)
        bb = tela.getbbox()
        if not bb:
            raise ValueError("nada desenhado")
        tela = tela.crop(bb)
        r = altura / tela.height
        img = tela.resize((max(1, int(tela.width * r)), altura), Image.LANCZOS)
    except Exception:
        img = None
    _CACHE_EMOJI[chave] = img
    return img


def _pedacos(t: str) -> list:
    """Divide o texto em trechos (conteudo, é_emoji), na ordem."""
    fora, i = [], 0
    for m in _EMOJI.finditer(t or ""):
        if m.start() > i:
            fora.append((t[i:m.start()], False))
        fora.append((m.group(), True))
        i = m.end()
    if i < len(t or ""):
        fora.append((t[i:], False))
    return fora


def _texto_rico(img, d, x: int, y_meio: int, texto: str, fonte, cor,
                contorno=0, cor_contorno=(0, 0, 0, 255), desenhar=True) -> int:
    """Escreve texto+emoji numa linha e devolve a largura ocupada.

    `y_meio` é o MEIO da linha, não o topo: é o único jeito de alinhar o
    desenho do emoji (que vem como imagem) com a letra (que vem como fonte)
    sem depender de métrica de baseline que cada fonte reporta diferente.
    """
    alt_emoji = int(getattr(fonte, "size", 40) * 1.12)
    cur = x
    for pedaco, eh_emoji in _pedacos(texto):
        if eh_emoji:
            im = _img_emoji(pedaco, alt_emoji)
            if im is None:
                continue
            if desenhar:
                img.alpha_composite(im, (cur, y_meio - im.height // 2))
            cur += im.width + 4
        else:
            if desenhar:
                d.text((cur, y_meio), pedaco, font=fonte, fill=cor,
                       anchor="lm", stroke_width=contorno,
                       stroke_fill=cor_contorno)
            cur += int(d.textlength(pedaco, font=fonte))
    return cur - x


def _quebrar(d, texto: str, fonte, larg_max: int, max_linhas: int) -> list:
    """Quebra gulosa por largura REAL (emoji conta). Corta no limite de linhas."""
    linhas, atual = [], []
    for p in (texto or "").split():
        teste = " ".join(atual + [p])
        if atual and _texto_rico(None, d, 0, 0, teste, fonte, None,
                                 desenhar=False) > larg_max:
            linhas.append(" ".join(atual))
            atual = [p]
            if len(linhas) == max_linhas:
                return linhas
        else:
            atual.append(p)
    if atual and len(linhas) < max_linhas:
        linhas.append(" ".join(atual))
    return linhas or [""]


# ── Layout: onde cada faixa do template começa e termina ─────────────────────

def _cor_fundo(nicho: str) -> tuple:
    """(é_claro, cor RGB) pela MESMA regra da produção.

    produzir_tiktok:305 decide: geral (@topshop.__) = PRETO, pra manter o grid
    da conta principal; contas novas = BRANCO, estilo Alana. Override por
    FORCE_BG (testar os dois) ou BG_<NICHO>. Replicar a regra aqui, com os
    mesmos nomes, é o que impede o vídeo original de sair com fundo diferente
    do vídeo reciclado na MESMA conta.
    """
    padrao = "preto" if (nicho or "geral") in ("geral", "") else "branco"
    bg = (os.environ.get("FORCE_BG")
          or os.environ.get("BG_" + (nicho or "").upper())
          or os.environ.get("TOPSHOP_BG")
          or padrao).strip().lower()
    if bg in ("branco", "white"):
        return True, (255, 255, 255)
    if bg in ("bege", "claro"):
        return True, (232, 224, 210)
    return False, (0, 0, 0)


def _layout(edl: dict, imgs: list, avisos: list) -> dict:
    """As faixas do quadro, com a geometria do template que já está no ar.

    A FAIXA DA MÍDIA É FIXA (VIDEO_Y=470, 82% da largura, 3:4) e é o HOOK que
    se acomoda: o rodapé dele é ancorado logo acima do vídeo, então 1 ou 2
    linhas ficam sempre "coladas" em cima da mídia. Eu tinha feito o contrário
    — mídia calculada a partir do hook — e isso faz o bloco de vídeo mudar de
    altura de post pra post, que num grid de perfil salta aos olhos.
    """
    from PIL import Image, ImageDraw

    nicho = (edl.get("template") or {}).get("nicho") or "geral"
    claro, cor = _cor_fundo(nicho)

    d = ImageDraw.Draw(Image.new("RGBA", (LARG, ALT)))
    hook_txt = next((t.get("texto", "") for t in edl["trilhas"]["texto"]
                     if t.get("estilo") == "hook"), "")
    larg_max = LARG - HK_MARGEM - HK_MARGEM_DIR

    # o template real reduz a fonte antes de aceitar uma 3ª linha (HK_FONT_MIN):
    # hook em 3 linhas empurra o rodapé pra cima do cabeçalho
    fonte_hook, linhas = None, []
    for tam in range(HK_FONT, HK_FONT_MIN - 1, -2):
        fonte_hook = _fonte(tam)
        linhas = _quebrar(d, hook_txt, fonte_hook, larg_max, 4)
        if len(linhas) <= 2:
            break
    if len(linhas) > 2:
        avisos.append(f"o hook ficou com {len(linhas)} linhas mesmo em "
                      f"{HK_FONT_MIN}px — o storyboard precisa escrever mais "
                      f"curto: {hook_txt[:70]!r}")

    largura_v = int(LARG * VIDEO_W_FRAC)
    h_midia = int(largura_v * VIDEO_ASPECTO)
    y_midia = int(os.environ.get("VIDEO_Y", VIDEO_Y))
    x_midia = (LARG - largura_v) // 2

    piso_hook = LOGO_Y + LOGO_TAM + 20
    y_hook = max(piso_hook,
                 y_midia - HK_GAP_VIDEO - len(linhas) * HK_ALTURA_LINHA)
    if y_hook == piso_hook and hook_txt:
        avisos.append("o hook encostou no cabeçalho — está comprido demais "
                      "para a faixa entre a marca e o vídeo")

    return {"claro": claro, "cor_fundo": cor, "nicho": nicho,
            "hook_linhas": linhas, "hook_font": fonte_hook.size,
            "y_hook": y_hook,
            "x_midia": x_midia, "larg_midia": largura_v,
            "y_midia": y_midia, "h_midia": h_midia,
            "y_cta": int(os.environ.get("CTA_Y", CTA_Y))}


# ── Placas (a imagem parada que o movimento vai percorrer) ───────────────────

def _placa(origem: Path, destino: Path, lay: dict, avisos: list) -> Path:
    """Foto do produto -> SÓ a faixa da mídia, pronta pro punch-in.

    A placa não é o quadro inteiro: é só o bloco que se mexe. O template branco
    (cabeçalho, hook, barra de CTA) entra depois, por cima, parado. Foi assim
    que o zoom parou de ampliar a logo junto.

    A faixa é a MESMA do template publicado: 82% da largura, proporção 3:4.
    O hunter chega nela esticando o vídeo pra 9:16 e cortando o meio — o que
    funciona pra vídeo vertical de terceiro e DESTRUIRIA foto de produto, que é
    quadrada e sairia deformada. Aqui a foto entra INTEIRA (contain) na mesma
    caixa: geometria idêntica, produto intacto.

    O que sobra dentro da caixa é preenchido com a própria foto ampliada e
    desfocada, puxada pro claro ou pro escuro conforme o fundo do template, pra
    não abrir um bloco de cor estranha no meio do quadro.
    """
    from PIL import Image, ImageFilter, ImageEnhance

    W, H = lay["larg_midia"] * SUPER, lay["h_midia"] * SUPER
    img = Image.open(origem).convert("RGB")

    e = max(W / img.width, H / img.height)
    fundo = img.resize((max(1, int(img.width * e)), max(1, int(img.height * e))),
                       Image.LANCZOS)
    esq, topo = (fundo.width - W) // 2, (fundo.height - H) // 2
    fundo = fundo.crop((esq, topo, esq + W, topo + H))
    fundo = fundo.filter(ImageFilter.GaussianBlur(radius=int(46 * SUPER)))
    fundo = ImageEnhance.Brightness(fundo).enhance(
        1.25 if lay["claro"] else 0.55)
    if lay["claro"]:
        fundo = ImageEnhance.Color(fundo).enhance(0.5)

    r = min(W / img.width, H / img.height)
    prod = img.resize((max(1, int(img.width * r)), max(1, int(img.height * r))),
                      Image.LANCZOS)
    fundo.paste(prod, ((W - prod.width) // 2, (H - prod.height) // 2))

    destino.parent.mkdir(parents=True, exist_ok=True)
    fundo.save(destino, "PNG")
    if img.width < 600 or img.height < 600:
        avisos.append(f"{origem.name}: {img.width}x{img.height} — foto pequena, "
                      "o punch-in vai amolecer")
    return destino


# ── Camada de marca ──────────────────────────────────────────────────────────

def _fonte(tam: int, negrito=True):
    from PIL import ImageFont
    cands = []
    if negrito:
        cands += [BRAND_DIR / "Montserrat-Bold.ttf",
                  Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
                  Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]
    else:
        cands += [BRAND_DIR / "Montserrat-Regular.ttf",
                  Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
                  Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    for c in cands:
        if c.exists():
            return ImageFont.truetype(str(c), tam)
    return ImageFont.load_default()


def _familia_ass() -> tuple:
    """(nome da família, pasta de fontes) pro libass.

    Passar a pasta importa: sem `fontsdir` o libass depende do fontconfig da
    máquina, e a Montserrat do projeto não está instalada no sistema — o vídeo
    sairia com outra fonte sem ninguém reclamar.
    """
    if (BRAND_DIR / "Montserrat-Bold.ttf").exists():
        return "Montserrat", str(BRAND_DIR)
    if Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf").exists():
        return "Liberation Sans", ""
    return "DejaVu Sans", ""


def _logo_circular(caminho: Path, tam: int):
    from PIL import Image, ImageDraw
    img = Image.open(caminho).convert("RGBA").resize((tam, tam), Image.LANCZOS)
    mask = Image.new("L", (tam, tam), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, tam - 1, tam - 1), fill=255)
    img.putalpha(mask)
    return img


def _camada_marca(edl: dict, lay: dict, destino: Path, avisos: list) -> Path:
    """O TEMPLATE INTEIRO num PNG com alfa: cabeçalho, hook e barra de CTA.

    Reproduz o print do feed que o Dre mandou: fundo branco, logo redonda no
    alto à esquerda, "TopShop" em preto com o selo, "@handle" em cinza abaixo,
    o HOOK em preto alinhado à esquerda, e a barra `COMENTE "QUERO" 👉` no pé.

    TUDO AQUI É FIXO E DURA O VÍDEO INTEIRO — inclusive o hook. No template
    publicado ele não some quando a narração passa da primeira frase; é o
    cabeçalho do post, não uma legenda. O EDL trata o hook como texto de uma
    seção, e é o render que reconcilia com o template real.

    Desenhado em PIL, não em ASS, POR CAUSA DO EMOJI: o libass pinta emoji em
    preto e branco e quebra sequência ZWJ; o Pillow pinta colorido e compõe o
    ZWJ certo. Quase todo hook do print tem emoji.

    Qual logo e qual @ vêm do EDL, que pegou de shared/marca.py e contas.json.
    Aqui não se decide marca; aqui se desenha.
    """
    from PIL import Image, ImageDraw

    tp = edl.get("template") or {}
    claro = lay["claro"]
    # cores do template real: claro = preto sem contorno, @ em #7a7a7a;
    # escuro = branco com contorno preto (senão some sobre o vídeo)
    tinta = (0, 0, 0, 255) if claro else (255, 255, 255, 255)
    cinza = (122, 122, 122, 255) if claro else (255, 255, 255, 255)
    contorno = 0 if claro else 3
    cor_contorno = (0, 0, 0, 255)

    camada = Image.new("RGBA", (LARG, ALT), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)

    # a moldura é o próprio template: cobre tudo MENOS a caixa da mídia, que
    # fica transparente pro vídeo aparecer por baixo
    r, g, b = lay["cor_fundo"]
    fundo = (r, g, b, 255)
    x0, x1 = lay["x_midia"], lay["x_midia"] + lay["larg_midia"]
    y0, y1 = lay["y_midia"], lay["y_midia"] + lay["h_midia"]
    fx0, fx1 = lay["x_midia"], lay["x_midia"] + lay["larg_midia"]
    d.rectangle((0, 0, LARG, y0), fill=fundo)
    d.rectangle((0, y1, LARG, ALT), fill=fundo)
    d.rectangle((0, y0, x0, y1), fill=fundo)          # as tarjas laterais dos
    d.rectangle((x1, y0, LARG, y1), fill=fundo)       # 18% que a mídia não usa

    # ── cabeçalho ───────────────────────────────────────────────────────────
    logo_x = int(os.environ.get("LOGO_X", LOGO_X))
    logo_y = int(os.environ.get("LOGO_Y", LOGO_Y))
    logo_tam = int(os.environ.get("LOGO_TAM", LOGO_TAM))
    arq_logo = BRAND_DIR / (tp.get("logo") or "logo_ts.png")
    if arq_logo.exists():
        camada.alpha_composite(_logo_circular(arq_logo, logo_tam), (logo_x, logo_y))
    else:
        avisos.append(f"logo '{arq_logo.name}' não existe em {BRAND_DIR} — "
                      "o vídeo sai SEM a marca no canto")

    texto_x = logo_x + logo_tam + int(os.environ.get("TEXTO_DX", TEXTO_DX))
    f_nome = _fonte(int(os.environ.get("NOME_FONT", NOME_FONT)))
    # o template posiciona o clipe do nome em (texto_x, logo_y-12) pelo canto;
    # aqui o texto é centrado na linha, então o meio fica meia fonte abaixo
    larg_nome = _texto_rico(camada, d, texto_x, logo_y - 12 + f_nome.size // 2,
                            "TopShop", f_nome, tinta, contorno, cor_contorno)

    selo = BRAND_DIR / "verificado.png"
    if selo.exists():
        from PIL import Image as _I
        s = _I.open(selo).convert("RGBA").resize((SELO_TAM, SELO_TAM), _I.LANCZOS)
        # o selo é centrado NA LINHA DO NOME. O template o põe em logo_y+14
        # porque lá o nome é um clipe do MoviePy com folga própria; aqui o
        # texto é centrado na linha, e copiar o número cru fazia o selo descer
        # em cima do @handle — apareceu no quadro de revisão.
        camada.alpha_composite(
            s, (texto_x + larg_nome + int(os.environ.get("SELO_DX", SELO_DX)),
                logo_y - 12 + f_nome.size // 2 - SELO_TAM // 2))
    else:
        avisos.append("verificado.png não existe — sai sem o selo azul")

    handle = tp.get("handle") or ""
    if not handle:
        avisos.append("o EDL veio SEM handle — confira contas.json pro nicho "
                      f"'{tp.get('nicho')}'")
    else:
        f_h = _fonte(int(os.environ.get("HANDLE_FONT", HANDLE_FONT)))
        _texto_rico(camada, d, texto_x, logo_y + 42 + f_h.size // 2, handle,
                    f_h, cinza, contorno, cor_contorno)

    # ── hook: rodapé ancorado logo acima do vídeo ───────────────────────────
    f_hook = _fonte(lay["hook_font"])
    margem_h = int(os.environ.get("HK_MARGEM", HK_MARGEM))
    for i, linha in enumerate(lay["hook_linhas"]):
        _texto_rico(camada, d, margem_h,
                    lay["y_hook"] + i * HK_ALTURA_LINHA + HK_ALTURA_LINHA // 2,
                    linha, f_hook, tinta, contorno, cor_contorno)

    # ── CTA fixo ────────────────────────────────────────────────────────────
    # `COMENTE "QUERO" 👇` — o texto e a posição são os do template
    # (CTA_TEXTO/CTA_FONT/CTA_Y). O emoji é 👇, apontando pro campo de
    # comentário; eu tinha posto 👉 por ter lido o print em vez do código.
    cta = os.environ.get("CTA_TEXTO", CTA_TEXTO)
    if cta:
        cta = f"{cta} {os.environ.get('CTA_EMOJI', CTA_EMOJI)}".strip()
        f_cta = _fonte(int(os.environ.get("CTA_FONT", CTA_FONT)))
        larg = _texto_rico(None, d, 0, 0, cta, f_cta, None, desenhar=False)
        _texto_rico(camada, d, (LARG - larg) // 2,
                    lay["y_cta"] + f_cta.size // 2, cta, f_cta,
                    tinta, contorno, cor_contorno)

    destino.parent.mkdir(parents=True, exist_ok=True)
    camada.save(destino, "PNG")
    return destino


# ── Legendas e animação (ASS) ────────────────────────────────────────────────

def _ancora(pos: str, lay: dict) -> tuple:
    """Posição do EDL -> (alinhamento ASS, x, y), SEMPRE dentro da mídia.

    As coordenadas são calculadas a partir da faixa da mídia, não fixas no
    quadro: o hook pode ter 1, 2 ou 3 linhas e empurrar a mídia pra baixo. Com
    número fixo, a legenda de um vídeo de hook curto flutuaria no branco e a de
    um hook longo cairia fora da foto — os dois lêem como erro de montagem.
    """
    topo = lay["y_midia"]
    base = lay["y_midia"] + lay["h_midia"]
    meio = topo + lay["h_midia"] // 2
    return {"topo":         (8, LARG // 2, topo + 46),
            "centro_alto":  (8, LARG // 2, topo + 46),
            "centro":       (5, LARG // 2, meio),
            "centro_baixo": (2, LARG // 2, base - 74),
            }.get(pos, (2, LARG // 2, base - 74))

# estilo -> tamanho, cor do texto, contorno/padding, cor do contorno, caixa?
# 'destaque' é o único com CAIXA (BorderStyle 3): ele cai em cima da foto e
# contorno sozinho não garante leitura sobre qualquer produto. Os outros vivem
# sobre fundo borrado, onde contorno preto grosso já basta — e caixa em tudo
# deixaria o vídeo com cara de apresentação de slides.
ESTILO_ASS = {
    "hook":     (74, COR_BRANCO, 6, COR_PRETO, False),
    "destaque": (52, COR_BRANCO, 16, "&H99000000", True),
    "legenda":  (58, COR_BRANCO, 5, COR_PRETO, False),
    "cta":      (66, COR_OURO, 6, COR_PRETO, False),
}


def _tags_entrada(anim: dict, x: int, y: int) -> str:
    """ANIM_TEXTO -> tags ASS.

    Aqui é onde "o texto ENTRA, não aparece" vira pixel. Cada entrada do
    ANIM_TEXTO do edl.py tem uma tradução direta:
      pop         escala de 60% pra 105% e assenta em 100% (o overshoot é o
                  que faz parecer vivo; sem ele é só um crescer)
      slide_cima  \\move subindo 60px, com fade curto
      escala      cresce de 85% sem overshoot — o CTA pede firmeza, não pulo
    """
    e = (anim or {}).get("entrada", "")
    dur = int(float((anim or {}).get("dur_entrada", 0.2)) * 1000)
    if e in ("pop", "pop_palavra"):
        # o overshoot é curto de propósito na legenda: ela troca a cada ~1s e
        # um pulo longo em cada bloco deixa o rodapé do vídeo inquieto
        alto = 106 if e == "pop" else 103
        volta = int(dur * 1.3)
        return (f"\\pos({x},{y})\\fscx60\\fscy60"
                f"\\t(0,{dur},\\fscx{alto}\\fscy{alto})"
                f"\\t({dur},{volta},\\fscx100\\fscy100)")
    if e == "slide_cima":
        return f"\\move({x},{y + 60},{x},{y},0,{dur})\\fad({dur},0)"
    if e == "escala":
        return (f"\\pos({x},{y})\\fscx85\\fscy85"
                f"\\t(0,{dur},\\fscx100\\fscy100)")
    return f"\\pos({x},{y})\\fad({dur},0)"


def _dialogos_palavra(txt: str, ini: float, fim: float, al: int, x: int, y: int,
                      anim: dict) -> list:
    """pop_palavra: as palavras aparecem uma a uma, sem a linha dançar.

    O jeito ingênuo (uma legenda por palavra) faz o texto pular de posição a
    cada palavra, porque a linha muda de largura. Aqui a linha inteira é
    desenhada desde o começo e as palavras que ainda não chegaram ficam
    TRANSPARENTES: o espaço já está reservado, então nada se mexe — só surge.

    DOIS DEFEITOS FORAM CORRIGIDOS AQUI OLHANDO QUADRO EXTRAÍDO:

    1) A animação de entrada valia pra TODO estado. Cada estado dura ~0,1s e o
       fade é de 0,12s, então a legenda recomeçava o fade a cada palavra e nunca
       chegava a ficar opaca — no quadro de 9,55s ela estava cinza-lavada sobre
       o fundo borrado, quando devia estar branca. Agora a entrada é só do 1º.

    2) A revelação era por TRANSPARÊNCIA: as palavras que ainda não tinham
       chegado ficavam invisíveis mas ocupando espaço. Resolvia o pulo da linha
       e criava outro problema — no quadro de 10,60s aparecia a palavra "lado"
       sozinha e deslocada pra esquerda, porque o resto do bloco era espaço
       vazio. Palavra solta e torta lê como erro, não como edição.
       Agora o bloco INTEIRO aparece de uma vez e o que anda é o DESTAQUE: a
       palavra do momento fica dourada. É o padrão de legenda que o formato já
       consagrou, e resolve os dois: nada se mexe e a leitura acompanha a fala.
    """
    palavras = (txt or "").split()
    if not palavras:
        return []
    entrada = "{\\an%d%s}" % (al, _tags_entrada(anim, x, y))
    depois = "{\\an%d\\pos(%d,%d)}" % (al, x, y)
    if len(palavras) == 1:
        return [(ini, fim, entrada + _ass_escapar(txt))]
    passo = (fim - ini) / len(palavras)
    linhas = []
    for i in range(len(palavras)):
        t0 = ini + passo * i
        t1 = ini + passo * (i + 1) if i < len(palavras) - 1 else fim
        pedacos = []
        for j, p in enumerate(palavras):
            e = _ass_escapar(p)
            pedacos.append(f"{{\\1c{COR_OURO}}}{e}{{\\1c{COR_BRANCO}}}"
                           if j == i else e)
        linhas.append((t0, t1, (entrada if i == 0 else depois) + " ".join(pedacos)))
    return linhas


def _ass(edl: dict, lay: dict, destino: Path, avisos: list) -> Path:
    fam, _ = _familia_ass()
    cab = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {LARG}",
           f"PlayResY: {ALT}", "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
           "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
           "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
           "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
           "Alignment, MarginL, MarginR, MarginV, Encoding"]
    for nome, (tam, cor, bord, cor_bord, caixa) in ESTILO_ASS.items():
        # a margem acompanha a caixa da mídia: legenda mais larga que o vídeo
        # que ela legenda vaza pra tarja lateral do template
        marg = lay["x_midia"] + 20
        cab.append(f"Style: {nome},{fam},{tam},{cor},{COR_BRANCO},{cor_bord},"
                   f"&H90000000,-1,0,0,0,100,100,0,0,"
                   f"{3 if caixa else 1},{bord},{0 if caixa else 2},"
                   f"5,{marg},{marg},60,1")
    cab += ["", "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text"]

    linhas, caidos = [], []
    for tx in edl["trilhas"]["texto"]:
        estilo = tx.get("estilo", "legenda")
        # o HOOK não passa por aqui: no template publicado ele é fixo e dura o
        # vídeo inteiro, então quem o desenha é o PIL, com emoji e tudo
        if estilo == "hook":
            continue
        if estilo not in ESTILO_ASS:
            estilo = "legenda"
        al, x, y = _ancora(tx.get("posicao"), lay)
        anim = tx.get("anim") or {}
        cabec = "{\\an%d%s}" % (al, _tags_entrada(anim, x, y))
        ini, fim = float(tx["inicio"]), float(tx["fim"])
        if fim <= ini:
            continue
        bruto = tx.get("texto", "")
        texto = _limpar_tela(bruto)
        if texto != bruto:
            caidos += _EMOJI.findall(bruto)
        if not texto:
            continue
        if anim.get("entrada") == "pop_palavra":
            for t0, t1, corpo in _dialogos_palavra(texto, ini, fim, al, x, y, anim):
                linhas.append((t0, t1, estilo, corpo))
        else:
            linhas.append((ini, fim, estilo, cabec + _ass_escapar(texto)))

    if caidos:
        avisos.append(
            "emoji retirado do texto na tela (" + " ".join(dict.fromkeys(caidos))
            + ") — o libass desenha emoji em preto e branco e quebra sequência "
            "ZWJ; medido num quadro de teste. Caminho certo é colar PNG de "
            "emoji como o narrated_video_agent faz. Fica pra v2")

    # FLASH na troca de seção. É o "flash" do TRANSICAO_SECAO, desenhado como
    # um retângulo branco de 0,12s que some. Sai pelo ASS de propósito: xfade
    # ENCURTA o vídeo pelo tempo da transição, e aí legenda e voz saem do lugar.
    # Aqui a transição não custa um frame da linha do tempo.
    # O flash cobre SÓ a faixa da mídia. Piscar o template branco junto seria
    # piscar a marca — e a marca não faz parte da narrativa, ela só está lá.
    y0, y1 = lay["y_midia"], lay["y_midia"] + lay["h_midia"]
    fx0, fx1 = lay["x_midia"], lay["x_midia"] + lay["larg_midia"]
    for a, b in zip(edl["trilhas"]["visual"], edl["trilhas"]["visual"][1:]):
        if b.get("transicao") == "flash":
            t = float(b["inicio"])
            linhas.append((t, t + 0.12, "legenda",
                           "{\\an7\\pos(0,0)\\bord0\\shad0\\1c&HFFFFFF&"
                           "\\alpha&H20&\\fad(0,120)\\p1}"
                           f"m {fx0} {y0} l {fx1} {y0} l {fx1} {y1} "
                           f"l {fx0} {y1}"
                           "{\\p0}"))

    corpo = [f"Dialogue: 0,{_ass_tempo(a)},{_ass_tempo(b)},{e},,0,0,0,,{t}"
             for a, b, e, t in sorted(linhas, key=lambda z: z[0])]
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(cab + corpo) + "\n", encoding="utf-8")
    return destino


# ── Narração e conformação da linha do tempo ────────────────────────────────

def _falar(fala: str, alvo: Path, nicho: str, ff: str, avisos: list) -> dict:
    """Uma fala -> MP3, pelo ElevenLabs. Edge-TTS é só a rede de segurança.

    A ORDEM IMPORTA E NÃO É PREFERÊNCIA MINHA. O ElevenLabs é a voz que este
    projeto já publica, com voz POR NICHO (feminina em beleza, masculina no
    resto — narracao_ia._voz_do_nicho). Vídeo original narrado por outra voz
    entra no mesmo feed soando como outro canal.

    E ele devolve o TEMPO EXATO DE CADA CARACTERE, que o Edge-TTS não dá. É
    disso que a legenda vive: sem alinhamento, o bloco de legenda é repartido
    proporcionalmente ao número de letras — chute educado que erra sempre um
    pouco, e legenda fora de sincronia denuncia vídeo automático mesmo quando
    todo o resto está certo.
    """
    try:
        from narracao_ia import falar_com_tempos
        r = falar_com_tempos(fala, alvo, nicho)
    except Exception as e:
        r = {"ok": False, "erro": f"{type(e).__name__}: {str(e)[:90]}"}

    if r.get("ok"):
        if not r.get("tempos"):
            avisos.append(f"ElevenLabs sem alinhamento ({r.get('erro')}) — a "
                          "legenda volta a ser repartida por tamanho, que erra "
                          "um pouco sempre")
        return {"arquivo": alvo, "dur": _dur_midia(ff, alvo) or r.get("dur", 0),
                "chars": r.get("chars", ""), "tempos": r.get("tempos") or [],
                "voz": "elevenlabs"}

    erro_11 = r.get("erro")
    try:
        from tts_edge import gerar_narracao, edge_tts_disponivel
        if not edge_tts_disponivel():
            raise RuntimeError("edge-tts não instalado")
        kw = {"voz": os.environ["TTS_VOZ"]} if os.environ.get("TTS_VOZ") else {}
        e = gerar_narracao(fala, alvo, **kw)
        if not e.get("sucesso"):
            raise RuntimeError(e.get("erro") or "falha")
    except Exception as e2:
        avisos.append(f"nenhum TTS respondeu — ElevenLabs: {erro_11} · "
                      f"Edge: {str(e2)[:70]}. Este trecho fica MUDO e a legenda "
                      "continua")
        return {}

    avisos.append(f"ElevenLabs não respondeu ({erro_11}) — saiu no Edge-TTS, "
                  "que é rede de segurança e NÃO é a voz da marca. Não publique "
                  "assim sem ouvir")
    return {"arquivo": alvo, "dur": _dur_midia(ff, alvo), "chars": "",
            "tempos": [], "voz": "edge"}


def _narrar(edl: dict, tmp: Path, ff: str, avisos: list) -> list:
    """Gera o MP3 de cada bloco de narração e MEDE o que saiu.

    Retorna [{inicio_plano, texto, arquivo, dur, chars, tempos}]. É a medição
    desta lista que manda na linha do tempo depois — não a estimativa de
    caracteres do EDL.
    """
    itens = [a for a in edl["trilhas"]["audio"]
             if a.get("tipo") == "narracao" and _limpar_fala(a.get("texto"))]
    if not itens:
        return []
    nicho = (edl.get("template") or {}).get("nicho") or "geral"

    fora = []
    for i, a in enumerate(sorted(itens, key=lambda z: float(z["inicio"]))):
        fala = _limpar_fala(a.get("texto"))
        r = _falar(fala, tmp / f"narr_{i:02d}.mp3", nicho, ff, avisos)
        if not r:
            continue
        r.update({"inicio_plano": float(a["inicio"]), "texto": fala})
        fora.append(r)
        marca = "🎙️" if r["voz"] == "elevenlabs" else "⚠️ "
        exato = "" if not r["tempos"] else f" · {len(r['tempos'])} tempos"
        _log(f"   {marca}  {r['dur']:5.2f}s{exato}  “{fala[:46]}”")
    return fora


def _conformar(edl: dict, narracoes: list, avisos: list) -> dict:
    """Estica a linha do tempo pra caber a voz REAL.

    O EDL estima a fala por caracteres; o TTS entrega o que entrega. Medido:
    hook planejado em 2,5s, narrado em 3,89s. Sem este passo o vídeo corta a
    frase no meio — e é a primeira frase, a que decide se a pessoa fica.

    Cada bloco de narração abre um TRECHO da linha do tempo (do início dele até
    o início do próximo). O trecho só CRESCE, nunca encolhe: o tempo planejado
    veio do ritmo que o storyboard quis, e sobrar meio segundo de imagem é
    respiro; faltar é frase cortada.

    O remapeamento é linear por trecho e vale pra TODAS as trilhas — visual,
    texto e áudio saem do mesmo mapa, então nada desencontra.
    """
    if not narracoes:
        return edl

    total = float(edl["duracao_total"])
    marcos = sorted({round(n["inicio_plano"], 3) for n in narracoes} | {0.0})
    bordas = marcos + [total]

    novo_ini, mapa = 0.0, []       # (ini_velho, fim_velho, ini_novo, escala)
    for i in range(len(marcos)):
        v0, v1 = bordas[i], bordas[i + 1]
        largura = max(0.01, v1 - v0)
        falas = [n["dur"] for n in narracoes
                 if abs(n["inicio_plano"] - marcos[i]) < 0.005]
        preciso = (max(falas) + PAUSA_APOS_FALA) if falas else 0.0
        nova = max(largura, preciso)
        mapa.append((v0, v1, novo_ini, nova / largura))
        novo_ini += nova

    def remap(t: float) -> float:
        t = float(t)
        for v0, v1, n0, esc in mapa:
            if t < v1 - 1e-6 or v1 >= total - 1e-6:
                return round(n0 + (max(t, v0) - v0) * esc, 3)
        return round(novo_ini, 3)

    for c in edl["trilhas"]["visual"]:
        c["inicio"], c["fim"] = remap(c["inicio"]), remap(c["fim"])
    for tx in edl["trilhas"]["texto"]:
        tx["inicio"], tx["fim"] = remap(tx["inicio"]), remap(tx["fim"])
    for a in edl["trilhas"]["audio"]:
        if "inicio" in a:
            a["inicio"] = remap(a["inicio"])
    for n in narracoes:
        n["inicio"] = remap(n["inicio_plano"])

    _resincronizar_legendas(edl, narracoes, avisos)

    antes = total
    edl["duracao_total"] = round(novo_ini, 2)
    if abs(novo_ini - antes) > 0.05:
        _log(f"   ⏱️  linha do tempo {antes:.2f}s → {novo_ini:.2f}s "
             "(a voz real mandou)")
    if novo_ini > 34:
        avisos.append(f"vídeo ficou com {novo_ini:.0f}s — acima do que o "
                      "storyboard mira (15-20s). Narração longa demais para o "
                      "ritmo planejado")
    return edl


def _resincronizar_legendas(edl: dict, narracoes: list, avisos: list):
    """Cola cada bloco de legenda no instante EXATO em que a voz o diz.

    O `edl.py` reparte o tempo de um bloco pela quantidade de letras dele. É um
    chute educado: assume que toda letra leva o mesmo tempo, e nenhuma leva.
    "Cheguei" e "em casa e" têm tamanhos parecidos e durações bem diferentes.

    O ElevenLabs devolve, pra cada caractere do texto, quando ele começa e
    quando acaba. Então aqui a legenda para de ser estimada e passa a ser LIDA.

    A COMPARAÇÃO É SÓ POR ALFANUMÉRICO, e isso não é frouxidão: o `_batidas`
    do edl.py faz `strip(" ,;:")` nas pontas de cada batida, então o bloco de
    legenda quase nunca tem a mesma pontuação do texto que foi falado. Comparar
    letra por letra com pontuação falharia em praticamente todo bloco.

    Se o casamento falhar, o bloco FICA COM O TEMPO ANTIGO e o render avisa —
    legenda no tempo aproximado é ruim, legenda no lugar errado é pior.
    """
    fim_total = float(edl["duracao_total"])
    ordem = sorted(narracoes, key=lambda n: n["inicio"])
    falhas = 0

    for k, n in enumerate(ordem):
        if not n.get("tempos") or not n.get("chars"):
            continue
        ini_seg = float(n["inicio"])
        fim_seg = float(ordem[k + 1]["inicio"]) if k + 1 < len(ordem) else fim_total

        # posições dos caracteres "de verdade" do que foi falado
        alfa = [(i, c.lower()) for i, c in enumerate(n["chars"]) if c.isalnum()]
        blocos = [t for t in edl["trilhas"]["texto"]
                  if t.get("estilo") == "legenda"
                  and ini_seg - 0.01 <= float(t["inicio"]) < fim_seg]
        blocos.sort(key=lambda t: float(t["inicio"]))

        cursor = 0
        for b in blocos:
            alvo = [c.lower() for c in b.get("texto", "") if c.isalnum()]
            if not alvo:
                continue
            p = cursor
            while p < len(alfa) and alfa[p][1] != alvo[0]:
                p += 1
            casou = (p + len(alvo) <= len(alfa) and
                     all(alfa[p + j][1] == alvo[j] for j in range(len(alvo))))
            if not casou:
                falhas += 1
                continue
            i0 = alfa[p][0]
            i1 = alfa[p + len(alvo) - 1][0]
            t0 = min(ini_seg + n["tempos"][i0][0], fim_seg - PISO_LEGENDA)
            t1 = min(ini_seg + n["tempos"][i1][1], fim_seg)
            # a fala pode terminar depois do trecho (o corte seguinte já entrou):
            # sem este piso o bloco viraria duração zero e o _ass o descartaria,
            # ou seja, a última legenda da cena simplesmente não apareceria
            b["inicio"] = round(max(0.0, t0), 3)
            b["fim"] = round(max(t1, b["inicio"] + PISO_LEGENDA), 3)
            cursor = p + len(alvo)

    if falhas:
        avisos.append(f"{falhas} bloco(s) de legenda não casaram com o "
                      "alinhamento da voz e ficaram no tempo estimado")


# ── Grafo do FFmpeg ─────────────────────────────────────────────────────────

def _expr_corte(c: dict, nframes: int) -> tuple:
    """Expressões de zoom/pan do zoompan para um corte.

    z anda linearmente de zoom_de a zoom_para pelo índice do quadro de SAÍDA.
    x/y são o canto do recorte em coordenadas de ENTRADA: centrado é
    (iw-iw/zoom)/2, e o pan desliza dentro da folga que o zoom abriu — nunca
    além dela, senão o recorte sai da imagem e o FFmpeg trava na borda.
    """
    zi = float(c.get("zoom_de", 1.0))
    zf = float(c.get("zoom_para", 1.0))
    n1 = max(1, nframes - 1)
    z = f"{zi}+({zf}-{zi})*on/{n1}"
    if "pan_de" in c:
        pd = 1.0 if float(c["pan_de"]) > 0 else -1.0
        pp = 1.0 if float(c["pan_para"]) > 0 else -1.0
        p = f"({pd}+({pp}-{pd})*on/{n1})"
        x = f"(iw-iw/zoom)/2*(1+{p})"
    else:
        x = "(iw-iw/zoom)/2"
    return z, x, "(ih-ih/zoom)/2"


def _montar_comando(ff: str, edl: dict, placas: dict, marca: Path, lay: dict,
                    ass: Path, narracoes: list, saida: Path,
                    crf: int) -> list:
    entradas, filtros, rotulos = [], [], []
    cortes = edl["trilhas"]["visual"]
    dur_total = float(edl["duracao_total"])
    hm, lm = lay["h_midia"], lay["larg_midia"]

    # entrada 0: a lona do template. Tudo é montado EM CIMA dela, então o
    # quadro nunca fica com buraco preto se alguma faixa não for coberta.
    cor = "white" if lay["claro"] else "black"
    entradas += ["-f", "lavfi", "-t", f"{dur_total:.3f}",
                 "-i", f"color=c={cor}:s={LARG}x{ALT}:r={FPS}"]

    for i, c in enumerate(cortes, start=1):
        dur = max(1.0 / FPS, float(c["fim"]) - float(c["inicio"]))
        n = max(1, int(round(dur * FPS)))
        placa = placas[c["asset"]]
        # -t um pouco maior que o preciso: com `-loop 1` sem limite o FFmpeg
        # lê pra sempre; o trim abaixo é quem define o tamanho exato.
        entradas += ["-loop", "1", "-t", f"{dur + 0.2:.3f}", "-i", str(placa)]
        z, x, y = _expr_corte(c, n)
        # o zoompan devolve o tamanho da FAIXA, não do quadro: é isso que faz o
        # punch-in mexer só na mídia e deixar cabeçalho, hook e CTA parados
        filtros.append(
            f"[{i}:v]zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={lm}x{hm}:"
            f"fps={FPS},trim=end_frame={n},setpts=PTS-STARTPTS,"
            f"format=yuv420p,setsar=1[v{i}]")
        rotulos.append(f"[v{i}]")

    i_marca = len(cortes) + 1
    entradas += ["-loop", "1", "-i", str(marca)]

    fam, fontes = _familia_ass()
    esc = str(ass).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    op_ass = f"ass=filename='{esc}'" + (f":fontsdir='{fontes}'" if fontes else "")

    filtros.append("".join(rotulos) + f"concat=n={len(cortes)}:v=1:a=0[vmidia]")
    filtros.append(f"[0:v][vmidia]overlay={lay['x_midia']}:{lay['y_midia']}:"
                   "shortest=1[vbase]")
    # o template entra DEPOIS: assim ele não participa do zoom de nenhum corte
    # e fica cravado no mesmo lugar o vídeo inteiro
    filtros.append(f"[{i_marca}:v]format=rgba[marca]")
    filtros.append("[vbase][marca]overlay=0:0:shortest=1[vmarca]")
    filtros.append(f"[vmarca]{op_ass},format=yuv420p[vout]")

    if narracoes:
        base = len(cortes) + 2
        rot_a = []
        for k, n in enumerate(narracoes):
            entradas += ["-i", str(n["arquivo"])]
            atraso = int(round(float(n.get("inicio", n["inicio_plano"])) * 1000))
            filtros.append(f"[{base + k}:a]adelay={atraso}|{atraso},"
                           f"aformat=sample_fmts=fltp:sample_rates=48000:"
                           f"channel_layouts=stereo[a{k}]")
            rot_a.append(f"[a{k}]")
        # normalize=0: com normalize=1 o amix DIVIDE o volume pelo número de
        # entradas e a narração sai sussurrada, porque as falas nem se
        # sobrepõem — cada uma toca sozinha no seu trecho.
        filtros.append("".join(rot_a) +
                       f"amix=inputs={len(rot_a)}:normalize=0:dropout_transition=0,"
                       f"apad,atrim=0:{dur_total:.3f}[aout]")
        mapa_audio = ["-map", "[aout]", "-c:a", "aac", "-b:a", "160k"]
    else:
        entradas += ["-f", "lavfi", "-t", f"{dur_total:.3f}",
                     "-i", "anullsrc=r=48000:cl=stereo"]
        mapa_audio = ["-map", f"{len(cortes) + 2}:a", "-c:a", "aac", "-b:a", "96k"]

    return ([ff, "-hide_banner", "-loglevel", "error", "-y"] + entradas +
            ["-filter_complex", ";".join(filtros), "-map", "[vout]"] + mapa_audio +
            ["-r", str(FPS), "-t", f"{dur_total:.3f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(saida)])


# ── Assets ───────────────────────────────────────────────────────────────────

EXT_IMG = (".jpg", ".jpeg", ".png", ".webp")


def _resolver_imagens(origem: str, n: int, avisos: list) -> list:
    """asset_1..asset_N -> arquivos, na ordem alfabética da pasta.

    Faltando imagem, as últimas REPETEM a primeira em vez de o render abortar —
    mas com aviso. Vídeo com foto repetida ainda é vídeo; render que morre no
    meio da esteira é fila parada.
    """
    p = Path(origem)
    arqs = ([p] if p.is_file() else
            sorted([f for f in p.iterdir() if f.suffix.lower() in EXT_IMG])
            if p.is_dir() else [])
    if not arqs:
        raise SystemExit(f"[render] nenhuma imagem em {origem}")
    if len(arqs) < n:
        avisos.append(f"o EDL pede {n} imagem(ns) e há {len(arqs)} — as que "
                      "faltam repetem a primeira")
        arqs = arqs + [arqs[0]] * (n - len(arqs))
    return arqs[:n]


# ── Render ───────────────────────────────────────────────────────────────────

def renderizar(edl: dict, origem_imgs: str, saida: Path, mudo=False,
               crf=20, quadros=0) -> dict:
    avisos = []
    ff = _ffmpeg()
    if not ff:
        raise SystemExit("[render] FFmpeg não encontrado (nem no sistema nem "
                         "no imageio-ffmpeg)")
    # checa ANTES de gerar narração e placas: sem libass o vídeo sai sem uma
    # letra, e descobrir isso depois de 5 chamadas de TTS é desperdício. O
    # drawtext não serve de plano B — o build estático que testei tem
    # libfreetype ligado e mesmo assim não traz o filtro.
    if not _tem_filtro(ff, "ass"):
        raise SystemExit(
            f"[render] este FFmpeg ({ff}) não tem o filtro 'ass' (libass). "
            "Todo o texto do vídeo sai por ele — hook, legenda e CTA. "
            "Instale um FFmpeg com --enable-libass ou "
            "`pip install imageio-ffmpeg`, que traz um estático com libass")

    modo = edl.get("modo_audio", "narracao")
    if any(a["tipo"] == "sfx" for a in edl["trilhas"]["audio"]):
        avisos.append("SFX pedidos pelo EDL (whoosh/pop/impacto) — não há "
                      "arquivo de som no projeto, saem de fora")
    if any(x["tipo"] in ("musica", "musica_alta") for x in edl["trilhas"]["audio"]):
        avisos.append(f"modo '{modo}' pede música — não existe arquivo local, e "
                      "música do Instagram não se baixa: entra no app (ou pelo "
                      "Metricool). O vídeo sai sem trilha")
    if any(c.get("transicao") == "whip" for c in edl["trilhas"]["visual"]):
        avisos.append("transição 'whip' ainda não implementada — sai corte seco")

    n_assets = max(int(edl.get("assets_disponiveis") or 1),
                   max((int(re.sub(r"\D", "", c["asset"]) or 1)
                        for c in edl["trilhas"]["visual"]), default=1))
    imgs = _resolver_imagens(origem_imgs, n_assets, avisos)

    tmp = Path(tempfile.mkdtemp(prefix="render_"))
    try:
        lay = _layout(edl, imgs, avisos)
        placas = {}
        for i, f in enumerate(imgs, 1):
            placas[f"asset_{i}"] = _placa(f, tmp / f"placa_{i}.png", lay, avisos)

        narracoes = [] if mudo else _narrar(edl, tmp, ff, avisos)
        if mudo:
            avisos.append("rodou com --mudo: sem narração, o vídeo tem que "
                          "prender só pelo texto")
        edl = _conformar(edl, narracoes, avisos)

        marca = _camada_marca(edl, lay, tmp / "marca.png", avisos)
        ass = _ass(edl, lay, tmp / "legendas.ass", avisos)

        saida.parent.mkdir(parents=True, exist_ok=True)
        cmd = _montar_comando(ff, edl, placas, marca, lay, ass, narracoes,
                              saida, crf)
        _log(f"   🎬 {len(edl['trilhas']['visual'])} corte(s) · "
             f"{edl['duracao_total']}s · codificando…")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if r.returncode != 0 or not saida.exists():
            (SAIDA_DIR).mkdir(parents=True, exist_ok=True)
            (SAIDA_DIR / "ultimo_erro.txt").write_text(
                " ".join(cmd) + "\n\n" + r.stderr, encoding="utf-8")
            raise SystemExit(f"[render] FFmpeg falhou:\n{r.stderr[-1800:]}")

        if quadros:
            _amostrar(ff, saida, saida.with_suffix(""), quadros, edl)

        dur = _dur_midia(ff, saida)
        rel = {"arquivo": str(saida), "produto": edl.get("produto", ""),
               "duracao_arquivo": round(dur, 2),
               "duracao_edl": edl["duracao_total"],
               "cortes": len(edl["trilhas"]["visual"]),
               "modo_audio": modo, "mudo": bool(mudo),
               "narracoes": len(narracoes),
               "tamanho_mb": round(saida.stat().st_size / 1e6, 2),
               "template": edl.get("template", {}),
               "voz": sorted({n.get("voz", "?") for n in narracoes}),
               # o layout entra no relatório porque é o que o inspetor precisa
               # pra saber ONDE olhar no quadro (faixa da mídia vs. moldura)
               "layout": {k: v for k, v in lay.items() if k != "hook_linhas"},
               "hook_linhas": lay["hook_linhas"],
               # sem dict.fromkeys, uma falha do ElevenLabs vira 5 linhas
               # idênticas no relatório e o aviso importante some no meio
               "faltou": list(dict.fromkeys(avisos))}
        saida.with_suffix(".relatorio.json").write_text(
            json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
        return rel
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _amostrar(ff: str, video: Path, prefixo: Path, n: int, edl: dict):
    """Tira N quadros ao longo do vídeo.

    Existe porque revisar render assistindo é lento e porque quem revisa nem
    sempre pode abrir um player. Quadro parado pega o que mais dói: legenda
    fora da zona segura, marca em cima do produto, texto cortado.
    """
    dur = float(edl["duracao_total"])
    pasta = Path(f"{prefixo}_quadros")
    pasta.mkdir(parents=True, exist_ok=True)
    for k in range(n):
        t = dur * (k + 0.5) / n
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                        str(pasta / f"q{k:02d}_{t:04.1f}s.png")],
                       capture_output=True, timeout=120)
    _log(f"   🖼️  {n} quadro(s) em {pasta}")


def main():
    p = argparse.ArgumentParser(description="EDL -> MP4 (o render).")
    p.add_argument("--edl", required=True)
    p.add_argument("--imagens", required=True,
                   help="pasta com as fotos do produto (ou um arquivo só)")
    p.add_argument("--saida", default="")
    p.add_argument("--mudo", action="store_true",
                   help="sem narração — testa se o vídeo prende só pelo texto")
    p.add_argument("--crf", type=int, default=20)
    p.add_argument("--quadros", type=int, default=0,
                   help="tira N quadros do resultado pra revisar sem player")
    args = p.parse_args()

    arq = Path(args.edl)
    edl = json.loads(arq.read_text(encoding="utf-8"))
    saida = Path(args.saida) if args.saida else SAIDA_DIR / f"{arq.stem}.mp4"

    _log(f"{edl.get('produto', '')[:60]}  [{edl.get('modo_audio')}]")
    rel = renderizar(edl, args.imagens, saida, mudo=args.mudo, crf=args.crf,
                     quadros=args.quadros)

    print()
    _log(f"✅ {rel['arquivo']}")
    _log(f"   {rel['duracao_arquivo']}s · {rel['cortes']} cortes · "
         f"{rel['tamanho_mb']} MB · {rel['narracoes']} narração(ões)")
    if abs(rel["duracao_arquivo"] - rel["duracao_edl"]) > 0.3:
        _log(f"   ⚠️  arquivo {rel['duracao_arquivo']}s ≠ EDL "
             f"{rel['duracao_edl']}s")
    if rel["faltou"]:
        print()
        _log("faltou (e o vídeo saiu assim mesmo):")
        for x in rel["faltou"]:
            print(f"     · {x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
