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
# 2) drawtext NÃO EXISTE em todo build de FFmpeg.
#    O binário estático que testei tem libfreetype ligado e mesmo assim não
#    traz o filtro drawtext. Tem libass. Então o texto sai por ASS, e isso é
#    melhor de qualquer jeito: ASS anima de verdade (\t, \move, \fad, alfa por
#    palavra), que é exatamente o que ANIM_TEXTO pede e o drawtext não faz.
#
# 3) A MARCA NÃO PODE ZOOMAR JUNTO.
#    Logo e @ são desenhados UMA vez, em PNG com alfa, e entram DEPOIS do
#    movimento. Se entrassem antes, o punch-in ampliaria a logo a cada corte.
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

# Zonas seguras do template. O produto vive ENTRE elas — foi assim que o
# header da marca parou de cair em cima da foto.
TOPO_SEGURO = 300              # logo + TopShop + @
BASE_SEGURA = 430              # legendas

PAUSA_APOS_FALA = 0.25         # respiro no fim de cada bloco de narração; sem
                               # ele a última sílaba encosta no corte seguinte

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


# ── Placas (a imagem parada que o movimento vai percorrer) ───────────────────

def _placa(origem: Path, destino: Path, avisos: list) -> Path:
    """Foto do produto -> quadro vertical 9:16 pronto pro punch-in.

    FUNDO BORRADO, NÃO CORTE. Foto de e-commerce é quadrada. Pra "cobrir"
    1080x1920 ela teria que perder 44% da largura — e o que sai do quadro é
    justamente o produto. Então o produto entra INTEIRO (contain) e o vazio é
    preenchido com a própria foto ampliada e desfocada: o quadro fica cheio,
    a cor conversa com o produto, e nada é cortado.

    O produto é centrado ENTRE as zonas seguras, não no meio do quadro: em
    cima mora a marca, embaixo moram as legendas.
    """
    from PIL import Image, ImageFilter, ImageEnhance

    W, H = LARG * SUPER, ALT * SUPER
    img = Image.open(origem).convert("RGB")

    # fundo: cobre o quadro, desfoca e escurece — desfocado demais vira sopa,
    # de menos compete com o produto
    e = max(W / img.width, H / img.height)
    fundo = img.resize((max(1, int(img.width * e)), max(1, int(img.height * e))),
                       Image.LANCZOS)
    esq = (fundo.width - W) // 2
    topo = (fundo.height - H) // 2
    fundo = fundo.crop((esq, topo, esq + W, topo + H))
    fundo = fundo.filter(ImageFilter.GaussianBlur(radius=int(46 * SUPER)))
    fundo = ImageEnhance.Brightness(fundo).enhance(0.55)

    # PRODUTO NA LARGURA CHEIA — e isto foi corrigido OLHANDO O RENDER.
    #
    # A 1ª versão montou a foto como um "cartão" de 92% da largura, com canto
    # arredondado e sombra. Ficou bonito no quadro parado do primeiro corte e
    # ERRADO em movimento: o punch-in fecha o enquadramento, e a partir de zoom
    # 1,06 as bordas do cartão saem da tela. O vídeo começava com um cartão
    # desenhado e terminava com um retângulo cortado — o efeito aparecia e
    # sumia, que é pior do que nunca ter existido.
    #
    # Na largura cheia não há canto pra cortar: o que sai de quadro no zoom são
    # as laterais da própria foto, que é o que o olho espera de um push-in. A
    # foto também fica maior, e produto grande é o ponto do vídeo.
    livre_topo = TOPO_SEGURO * SUPER
    livre_base = H - BASE_SEGURA * SUPER
    alt_livre = livre_base - livre_topo
    r = min(W / img.width, alt_livre / img.height)
    prod = img.resize((max(1, int(img.width * r)), max(1, int(img.height * r))),
                      Image.LANCZOS)
    px = (W - prod.width) // 2
    py = livre_topo + (alt_livre - prod.height) // 2

    # sombra nas emendas de cima e de baixo: sem ela a foto encosta no fundo
    # borrado com uma linha reta e dura, e lê como imagem COLADA
    from PIL import ImageDraw
    sombra = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rectangle(
        (px, py, px + prod.width, py + prod.height), fill=(0, 0, 0, 190))
    sombra = sombra.filter(ImageFilter.GaussianBlur(radius=int(26 * SUPER)))
    fundo = Image.alpha_composite(fundo.convert("RGBA"), sombra).convert("RGB")
    fundo.paste(prod, (px, py))

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


def _camada_marca(edl: dict, destino: Path, avisos: list) -> Path:
    """PNG com alfa: logo redonda + TopShop + selo + @, e a marca d'água.

    A GEOMETRIA É A MESMA do template que já está no ar
    (narrated_video_agent._criar_camadas_topo) e lê as MESMAS variáveis de
    ambiente — LOGO_X, LOGO_Y, LOGO_TAM, NOME_FONT, HANDLE_FONT, TEXTO_DX.
    Não importei aquele arquivo porque ele é MoviePy de ponta a ponta e este
    render é FFmpeg; mas repetir os números com outros nomes seria repetir o
    erro do dicionário de logo duplicado. Mudou lá, muda aqui, pelos knobs.

    Qual logo e qual @ vêm do EDL, que por sua vez pegou de shared/marca.py e
    contas.json. Aqui não se decide marca; aqui se desenha.
    """
    from PIL import Image, ImageDraw

    tp = edl.get("template") or {}
    W, H = LARG, ALT
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)

    logo_x = int(os.environ.get("LOGO_X", 100))
    logo_y = int(os.environ.get("LOGO_Y", 112))
    logo_tam = int(os.environ.get("LOGO_TAM", 120))
    nome_font = int(os.environ.get("NOME_FONT", 56))
    handle_font = int(os.environ.get("HANDLE_FONT", 46))
    texto_dx = int(os.environ.get("TEXTO_DX", 16))

    arq_logo = BRAND_DIR / (tp.get("logo") or "logo_ts.png")
    if arq_logo.exists():
        camada.alpha_composite(_logo_circular(arq_logo, logo_tam), (logo_x, logo_y))
    else:
        avisos.append(f"logo '{arq_logo.name}' não existe em {BRAND_DIR} — "
                      "o vídeo sai SEM a marca no canto")

    texto_x = logo_x + logo_tam + texto_dx
    f_nome = _fonte(nome_font)
    d.text((texto_x, logo_y - 12), "TopShop", font=f_nome,
           fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0, 255))

    larg_nome = int(d.textlength("TopShop", font=f_nome))
    selo = BRAND_DIR / "verificado.png"
    if selo.exists():
        from PIL import Image as _I
        s = _I.open(selo).convert("RGBA").resize((46, 46), _I.LANCZOS)
        camada.alpha_composite(s, (texto_x + larg_nome + 12, logo_y + 14))
    else:
        avisos.append("verificado.png não existe — sai sem o selo")

    handle = tp.get("handle") or ""
    if not handle:
        avisos.append("o EDL veio SEM handle — confira contas.json pro nicho "
                      f"'{tp.get('nicho')}'")
    else:
        d.text((texto_x, logo_y + 42), handle, font=_fonte(handle_font),
               fill=(255, 255, 255, 255), stroke_width=3,
               stroke_fill=(0, 0, 0, 255))

    # marca d'água discreta no rodapé: quem salva o vídeo leva o @ junto
    if handle:
        f_ag = _fonte(30, negrito=False)
        w = int(d.textlength(handle, font=f_ag))
        d.text(((W - w) // 2, H - 74), handle, font=f_ag,
               fill=(255, 255, 255, 150), stroke_width=2,
               stroke_fill=(0, 0, 0, 120))

    destino.parent.mkdir(parents=True, exist_ok=True)
    camada.save(destino, "PNG")
    return destino


# ── Legendas e animação (ASS) ────────────────────────────────────────────────

ANCORA = {                     # posição do EDL -> (alinhamento ASS, x, y)
    "centro_alto": (8, LARG // 2, 470),
    # 'topo' era 320 e batia exatamente na borda de cima da foto — no quadro de
    # revisão o texto parecia estar cortando a imagem. 380 põe ele DENTRO da
    # foto, que com a caixa atrás vira selo, não acidente.
    "topo":        (8, LARG // 2, 380),
    "centro":      (5, LARG // 2, 960),
    "centro_baixo": (2, LARG // 2, ALT - 360),
}

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


def _ass(edl: dict, destino: Path, avisos: list) -> Path:
    fam, _ = _familia_ass()
    cab = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {LARG}",
           f"PlayResY: {ALT}", "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
           "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
           "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
           "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
           "Alignment, MarginL, MarginR, MarginV, Encoding"]
    for nome, (tam, cor, bord, cor_bord, caixa) in ESTILO_ASS.items():
        cab.append(f"Style: {nome},{fam},{tam},{cor},{COR_BRANCO},{cor_bord},"
                   f"&H90000000,-1,0,0,0,100,100,0,0,"
                   f"{3 if caixa else 1},{bord},{0 if caixa else 2},"
                   f"5,90,90,60,1")
    cab += ["", "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text"]

    linhas, caidos = [], []
    for tx in edl["trilhas"]["texto"]:
        estilo = tx.get("estilo", "legenda")
        if estilo not in ESTILO_ASS:
            estilo = "legenda"
        al, x, y = ANCORA.get(tx.get("posicao"), ANCORA["centro_baixo"])
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
    for a, b in zip(edl["trilhas"]["visual"], edl["trilhas"]["visual"][1:]):
        if b.get("transicao") == "flash":
            t = float(b["inicio"])
            linhas.append((t, t + 0.12, "legenda",
                           "{\\an7\\pos(0,0)\\bord0\\shad0\\1c&HFFFFFF&"
                           "\\alpha&H20&\\fad(0,120)\\p1}"
                           f"m 0 0 l {LARG} 0 l {LARG} {ALT} l 0 {ALT}{{\\p0}}"))

    corpo = [f"Dialogue: 0,{_ass_tempo(a)},{_ass_tempo(b)},{e},,0,0,0,,{t}"
             for a, b, e, t in sorted(linhas, key=lambda z: z[0])]
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(cab + corpo) + "\n", encoding="utf-8")
    return destino


# ── Narração e conformação da linha do tempo ────────────────────────────────

def _narrar(edl: dict, tmp: Path, ff: str, avisos: list) -> list:
    """Gera o MP3 de cada bloco de narração e MEDE o que saiu.

    Retorna [{inicio_plano, texto, arquivo, dur}]. É a medição desta lista que
    manda na linha do tempo depois — não a estimativa de caracteres do EDL.
    """
    itens = [a for a in edl["trilhas"]["audio"]
             if a.get("tipo") == "narracao" and _limpar_fala(a.get("texto"))]
    if not itens:
        return []
    try:
        from tts_edge import gerar_narracao, edge_tts_disponivel, motivo_indisponivel
    except Exception as e:
        avisos.append(f"TTS indisponível ({str(e)[:70]}) — vídeo sai MUDO")
        return []
    if not edge_tts_disponivel():
        avisos.append(f"TTS indisponível: {motivo_indisponivel()} — vídeo sai MUDO")
        return []

    voz = os.environ.get("TTS_VOZ", "").strip()
    fora = []
    for i, a in enumerate(sorted(itens, key=lambda z: float(z["inicio"]))):
        fala = _limpar_fala(a.get("texto"))
        alvo = tmp / f"narr_{i:02d}.mp3"
        kw = {"voz": voz} if voz else {}
        r = gerar_narracao(fala, alvo, **kw)
        if not r.get("sucesso"):
            avisos.append(f"narração {i} falhou ({r.get('erro')}) — este trecho "
                          "fica mudo e a legenda continua")
            continue
        dur = _dur_midia(ff, alvo)
        fora.append({"inicio_plano": float(a["inicio"]), "texto": fala,
                     "arquivo": alvo, "dur": dur})
        _log(f"   🎙️  {dur:5.2f}s  “{fala[:52]}”")
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


def _montar_comando(ff: str, edl: dict, placas: dict, marca: Path,
                    ass: Path, narracoes: list, saida: Path,
                    crf: int) -> list:
    entradas, filtros, rotulos = [], [], []
    cortes = edl["trilhas"]["visual"]

    for i, c in enumerate(cortes):
        dur = max(1.0 / FPS, float(c["fim"]) - float(c["inicio"]))
        n = max(1, int(round(dur * FPS)))
        placa = placas[c["asset"]]
        # -t um pouco maior que o preciso: com `-loop 1` sem limite o FFmpeg
        # lê pra sempre; o trim abaixo é quem define o tamanho exato.
        entradas += ["-loop", "1", "-t", f"{dur + 0.2:.3f}", "-i", str(placa)]
        z, x, y = _expr_corte(c, n)
        filtros.append(
            f"[{i}:v]zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={LARG}x{ALT}:"
            f"fps={FPS},trim=end_frame={n},setpts=PTS-STARTPTS,"
            f"format=yuv420p,setsar=1[v{i}]")
        rotulos.append(f"[v{i}]")

    i_marca = len(cortes)
    entradas += ["-loop", "1", "-i", str(marca)]

    fam, fontes = _familia_ass()
    esc = str(ass).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    op_ass = f"ass=filename='{esc}'" + (f":fontsdir='{fontes}'" if fontes else "")

    filtros.append("".join(rotulos) + f"concat=n={len(cortes)}:v=1:a=0[vcat]")
    # a marca entra DEPOIS do concat: assim ela não participa do zoom de
    # nenhum corte e fica cravada no mesmo lugar o vídeo inteiro
    filtros.append(f"[{i_marca}:v]format=rgba[marca]")
    filtros.append("[vcat][marca]overlay=0:0:shortest=1[vmarca]")
    filtros.append(f"[vmarca]{op_ass},format=yuv420p[vout]")

    dur_total = float(edl["duracao_total"])
    if narracoes:
        base = len(cortes) + 1
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
        mapa_audio = ["-map", f"{len(cortes) + 1}:a", "-c:a", "aac", "-b:a", "96k"]

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
        placas = {}
        for i, f in enumerate(imgs, 1):
            placas[f"asset_{i}"] = _placa(f, tmp / f"placa_{i}.png", avisos)

        narracoes = [] if mudo else _narrar(edl, tmp, ff, avisos)
        if mudo:
            avisos.append("rodou com --mudo: sem narração, o vídeo tem que "
                          "prender só pelo texto")
        edl = _conformar(edl, narracoes, avisos)

        marca = _camada_marca(edl, tmp / "marca.png", avisos)
        ass = _ass(edl, tmp / "legendas.ass", avisos)

        saida.parent.mkdir(parents=True, exist_ok=True)
        cmd = _montar_comando(ff, edl, placas, marca, ass, narracoes, saida, crf)
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
               "faltou": avisos}
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
