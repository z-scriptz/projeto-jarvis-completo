#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# carrossel_render.py — desenha os SLIDES de um carrossel do Instagram.
#
# POR QUE O CARROSSEL, E NÃO MAIS REEL (medido em 22/08):
# 47.202 impressões produziram 48 salvamentos — 1 a cada mil. O salvamento é o
# sinal que faz o Instagram entregar pra quem NÃO segue, e é justamente o que o
# Reel de achadinho não gera: a pessoa vê, acha legal, e passa. Carrossel é o
# formato que se salva, porque ele guarda INFORMAÇÃO (o produto, o preço, o
# porquê) em vez de só mostrar movimento.
#
# ⚠️ O QUE MANDA NO LAYOUT — cada número aqui tem uma razão, não um gosto:
#
#   1080×1350 (4:5), NÃO 1080×1080. É a maior área que o feed do Instagram
#   deixa um post ocupar; quadrado joga fora 25% da tela do celular de quem
#   está rolando.
#
#   TODOS os slides no MESMO tamanho. A doc da Meta: "Carousel images are all
#   cropped based on the first image in the carousel". Um slide de proporção
#   diferente não é reescalado — é CORTADO pelo primeiro, e o corte come o
#   texto de baixo sem avisar.
#
#   JPEG, sempre. "JPEG is the only image format supported." PNG é recusado
#   com o mesmo `ERROR` genérico de container que todo o resto devolve.
#
#   O CABEÇALHO É O MESMO DO REEL (logo redonda, "TopShop", selo, @handle) e a
#   cor de fundo sai do MESMO `_cor_fundo(nicho)`. Sem isso o carrossel entra
#   no grid com outra cara e a conta parece de duas pessoas diferentes — é o
#   mesmo erro que `_cor_fundo` já documenta pro vídeo reciclado.
#
# ESTRUTURA DE UM CARROSSEL (o plano é um JSON, ver --exemplo):
#   slide 1     CAPA     hook grande + "arrasta" — é o único que aparece no feed
#   slides 2..n PRODUTO  foto + título + preço
#   slide n     CTA      o pedido (salvar / comentar / link na bio)
#
# USO:
#   python3 carrossel_render.py --plano plano.json --saida pronto_carrossel/slug
#   python3 carrossel_render.py --exemplo casa      # vê o layout sem plano
#
#   from carrossel_render import renderizar
#   arquivos = renderizar(plano, pasta_saida)   # -> [Path, ...] na ordem

import os
import re
import sys
import json
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("carrossel_render")


# ⚠️ Os primitivos de desenho vêm do `render.py` DE PROPÓSITO, não copiados.
# `_texto_rico` sabe compor emoji colorido com ZWJ (o libass não sabe, e é por
# isso que o template do Reel é PIL); `_quebrar` mede largura real com emoji
# contando; `_cor_fundo` é a regra de marca. Duplicar os quatro aqui garantiria
# que um dia eles divergem e o carrossel sai com outra fonte que o Reel.
try:
    import render as R
except Exception as e:      # pragma: no cover
    raise SystemExit(
        f"não consegui importar render.py ({e}).\n"
        "Este módulo roda a partir da RAIZ (~/jarvis), onde o render.py mora —\n"
        "é de lá que o piloto.py também o importa."
    )


# ══════════════════════════════════════════════════════════════════════════
# GEOMETRIA — em pixels do quadro FINAL (1080×1350)
# ══════════════════════════════════════════════════════════════════════════
LARG, ALT = 1080, 1350
SUPER = 2                    # desenha em 2x e reduz: mesma sobra de pixel do Reel

MARGEM = 80

LOGO_X, LOGO_Y, LOGO_TAM = 80, 66, 96
NOME_FONT, HANDLE_FONT = 42, 32
SELO_TAM, SELO_DX, TEXTO_DX = 36, 12, 16
NOME_DY, HANDLE_DY = 36, 78          # deslocamento a partir do topo da logo

# ⚠️ 112 E NÃO 92: o hook da capa é a ÚNICA coisa que aparece no feed antes de
# alguém decidir tocar. `_texto_que_cabe` encolhe sozinho quando a frase é
# longa, então um teto alto não arrisca estourar — só deixa o hook CURTO
# ocupar a tela inteira, que é exatamente quando ele funciona melhor.
CAPA_FONT, CAPA_FONT_MIN = 112, 56
CAPA_ALT_LINHA = 1.16                # múltiplo do corpo da fonte
CAPA_MAX_LINHAS = 5
CAPA_Y_TOPO, CAPA_Y_BASE = 300, 1120 # a faixa livre entre cabeçalho e rodapé

# ⚠️ A FOTO DA SHOPEE É QUADRADA. Caixa achatada = corte no topo e no pé do
# produto, e produto cortado não vende. 800 de altura pra 920 de largura já
# custa ~13% da foto; menos que isso não deixa o título e o preço respirarem.
FOTO_Y, FOTO_H = 214, 800
FOTO_RAIO = 36
TITULO_FONT, TITULO_MIN = 50, 38
PRECO_FONT = 62
NUM_FONT = 34

CTA_FONT, CTA_LINHA_FONT = 76, 44

COR_MARCA = (245, 197, 66)           # #F5C542 — o mesmo ouro do COR_OURO do Reel
JPEG_Q = 92

# ══════════════════════════════════════════════════════════════════════════
# CAPA DRAMÁTICA — o modelo das referências que o Dre mandou (22/08)
#
# O que aquelas capas fazem e a minha capa limpa não fazia:
#   · a FOTO é o fundo do slide inteiro, escurecida, não uma caixa com margem
#   · texto em CAIXA ALTA, branco, ocupando o topo
#   · UMA PARTE da frase em COR — é a marca visual desses posts; o olho pousa
#     ali primeiro e é o que separa "capa de vídeo" de "arte de anúncio"
#   · subtexto menor embaixo, e o `1/8` numa pílula no rodapé
#
# ⚠️ A COR DE DESTAQUE É POR NICHO, e isso não é enfeite: é o pedido de
# "identidade visual de cada TopShop mantida". Duas contas nossas lado a lado
# no explorar têm que se distinguir sem ler o @.
_DESTAQUE = {
    "tech":   (163, 255, 79),      # verde-limão
    "casa":   (255, 138, 51),      # laranja
    "beleza": (214, 122, 255),     # roxo
    "pet":    (94, 200, 255),      # azul
    "moda":   (255, 122, 176),     # rosa
    "geral":  (245, 197, 66),      # o ouro da marca
}

CAPA_TITULO_FONT, CAPA_TITULO_MIN = 118, 62
CAPA_SUB_FONT = 40
CAPA_ESCURO = int(os.environ.get("CARR_CAPA_ESCURO", "170"))   # 0-255 do véu


# ⚠️ AS REFERÊNCIAS USAM FONTE CONDENSADA, E A MONTSERRAT NÃO É.
# É a última diferença visual entre a nossa capa e as delas: a condensada
# empilha mais letra por linha, e é ela que dá aquele peso de cartaz. Não dá
# pra simular com a Montserrat — largura de letra é desenho, não configuração.
# Então: SE existir uma condensada em assets/brand, a capa usa; se não, cai na
# Montserrat e continua funcionando. Baixar o .ttf é a única coisa que falta,
# e é uma decisão de marca, não de código.
_CONDENSADAS = ("Anton-Regular.ttf", "ArchivoBlack-Regular.ttf",
                "Oswald-Bold.ttf", "BebasNeue-Regular.ttf")


def fonte_titulo(tam: int):
    """Fonte dos títulos de capa: condensada se houver, Montserrat se não."""
    from PIL import ImageFont
    for nome in _CONDENSADAS:
        arq = R.BRAND_DIR / nome
        if arq.exists():
            try:
                return ImageFont.truetype(str(arq), tam)
            except Exception:
                continue
    return R._fonte(tam)


def _cor_destaque(nicho: str) -> tuple:
    return _DESTAQUE.get((nicho or "geral").lower(), _DESTAQUE["geral"])


def _capa_dramatica_ligada() -> bool:
    return os.environ.get("CARR_CAPA", "dramatica").strip().lower() != "limpa"


def _px(v) -> int:
    return int(round(v * SUPER))


# ══════════════════════════════════════════════════════════════════════════
# IDENTIDADE DA CONTA
# ══════════════════════════════════════════════════════════════════════════
def _handle_do_nicho(nicho: str) -> str:
    """@handle a partir do contas.json — a MESMA fonte que o uploader usa."""
    try:
        c = json.loads((BASE_DIR / "contas.json").read_text(encoding="utf-8"))
    except Exception:
        return ""
    return ((c.get(nicho or "geral") or c.get("_default") or {}).get("handle") or "")


def _arquivo_da_logo(nicho: str) -> Path:
    try:
        from shared.marca import logo_do_nicho
        nome = logo_do_nicho(nicho, log)
        nome = nome[0] if isinstance(nome, (tuple, list)) else nome
    except Exception:
        nome = "logo_ts.png"
    return R.BRAND_DIR / str(nome)


# ══════════════════════════════════════════════════════════════════════════
# PEÇAS DE DESENHO
# ══════════════════════════════════════════════════════════════════════════
def _tela(claro: bool, cor_fundo: tuple):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (_px(LARG), _px(ALT)), (*cor_fundo, 255))
    return img, ImageDraw.Draw(img)


def _tintas(claro: bool) -> tuple:
    """(tinta, cinza) do tema. Sem contorno: aqui o texto pousa em fundo
    sólido, nunca em cima de foto — então contorno só engorda a letra."""
    return ((0, 0, 0, 255), (122, 122, 122, 255)) if claro \
        else ((255, 255, 255, 255), (176, 176, 176, 255))


def _cabecalho(img, d, nicho: str, handle: str, claro: bool, avisos: list):
    """Logo + TopShop + selo + @handle — o mesmo bloco do Reel, na mesma ordem.
    Reproduzido aqui (e não importado) porque o `_camada_marca` do render
    desenha o template INTEIRO de 1080×1920, com faixa de vídeo e barra de CTA;
    dele só este pedaço serve."""
    from PIL import Image as _I
    tinta, cinza = _tintas(claro)

    arq = _arquivo_da_logo(nicho)
    if arq.exists():
        img.alpha_composite(R._logo_circular(arq, _px(LOGO_TAM)),
                            (_px(LOGO_X), _px(LOGO_Y)))
    else:
        avisos.append(f"logo '{arq.name}' não existe em {R.BRAND_DIR}")

    tx = _px(LOGO_X + LOGO_TAM + TEXTO_DX)
    f_nome = R._fonte(_px(NOME_FONT))
    larg = R._texto_rico(img, d, tx, _px(LOGO_Y + NOME_DY), "TopShop", f_nome, tinta)

    selo = R.BRAND_DIR / "verificado.png"
    if selo.exists():
        s = _I.open(selo).convert("RGBA")
        # ⚠️ apara a margem transparente ANTES do resize — sem isso o resize
        # conta o vazio e o desenho sai bem menor que o tamanho pedido. É a
        # mesma lição que custou dois dias no selo do Reel; o alfa sozinho é
        # que responde "aqui tem desenho?", porque branco-transparente
        # (255,255,255,0) não é zero pro getbbox() do RGBA.
        bb = s.getchannel("A").getbbox() or s.getbbox()
        if bb:
            s = s.crop(bb)
        s = s.resize((_px(SELO_TAM), _px(SELO_TAM)), _I.LANCZOS)
        img.alpha_composite(s, (tx + larg + _px(SELO_DX),
                                _px(LOGO_Y + NOME_DY) - _px(SELO_TAM) // 2))
    else:
        avisos.append("verificado.png não existe — sai sem o selo azul")

    if handle:
        R._texto_rico(img, d, tx, _px(LOGO_Y + HANDLE_DY), handle,
                      R._fonte(_px(HANDLE_FONT), negrito=False), cinza)


def _texto_que_cabe(d, texto: str, corpo: int, corpo_min: int, larg: int,
                    max_linhas: int, titulo: bool = False) -> tuple:
    """Encolhe a fonte até o texto caber em `max_linhas`. Devolve (linhas, fonte).

    ⚠️ ENCOLHER É O CAMINHO, CORTAR NÃO É. O teto fixo de 40 caracteres do
    `hook_alana` matava todo hook de duas linhas e ninguém via — o vídeo saía
    com a frase reserva. Aqui a fonte cede antes de a frase ceder."""
    escolhe = fonte_titulo if titulo else R._fonte
    for tam in range(corpo, corpo_min - 1, -2):
        f = escolhe(_px(tam))
        linhas = R._quebrar(d, texto, f, larg, max_linhas + 1)
        if len(linhas) <= max_linhas:
            return linhas, f
    f = escolhe(_px(corpo_min))
    return R._quebrar(d, texto, f, larg, max_linhas), f


def _bloco_centrado(img, d, linhas, fonte, cor, y_topo: int, y_base: int) -> int:
    """Escreve as linhas centradas na faixa, alinhadas à esquerda.

    Devolve o y (em px do canvas 2x) logo ABAIXO da última linha — quem quiser
    encostar algo embaixo usa isso em vez de chutar uma constante que fica
    errada assim que a fonte encolhe."""
    alt_linha = int(getattr(fonte, "size", 40) * CAPA_ALT_LINHA)
    total = alt_linha * len(linhas)
    y = _px((y_topo + y_base) / 2) - total // 2 + alt_linha // 2
    for ln in linhas:
        R._texto_rico(img, d, _px(MARGEM), y, ln, fonte, cor)
        y += alt_linha
    return y - alt_linha // 2


def _pilula(d, x: int, y: int, larg: int, alt: int, cor):
    d.rounded_rectangle((x, y, x + larg, y + alt), radius=alt // 2, fill=cor)


def _foto_arredondada(img, caminho: Path, x: int, y: int, larg: int, alt: int):
    """Cobre a caixa com a foto (corte central) e arredonda os cantos.

    ⚠️ COBRIR, não esticar. `resize((larg, alt))` deforma o produto — e produto
    deformado é a diferença entre "achadinho" e "anúncio suspeito"."""
    from PIL import Image, ImageDraw
    foto = Image.open(caminho).convert("RGB")
    escala = max(larg / foto.width, alt / foto.height)
    novo = (max(1, int(foto.width * escala)), max(1, int(foto.height * escala)))
    foto = foto.resize(novo, Image.LANCZOS)
    esq = (foto.width - larg) // 2
    topo = (foto.height - alt) // 2
    foto = foto.crop((esq, topo, esq + larg, topo + alt)).convert("RGBA")

    mask = Image.new("L", (larg, alt), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, larg - 1, alt - 1),
                                           radius=_px(FOTO_RAIO), fill=255)
    foto.putalpha(mask)
    img.alpha_composite(foto, (x, y))


PALAVRAS_MAX = int(os.environ.get("CARR_PALAVRAS_MAX", "12"))


def _conta_palavras(*textos) -> int:
    return sum(len(re.findall(r"\S+", t or "")) for t in textos)


def _vigiar_palavras(avisos: list, i: int, *textos):
    """⚠️ 8-12 PALAVRAS POR SLIDE É REGRA, NÃO ESTILO. Acima disso o slide vira
    parágrafo, a fonte encolhe pra caber (`_texto_que_cabe` obedece calado) e o
    que era uma capa de vídeo vira uma arte publicitária — que é exatamente o
    que o carrossel não pode parecer.

    Aqui só AVISA: este módulo desenha o que recebe. Quem corta é o
    `carrossel_brain`, que escreve o texto. O aviso pega inclusive plano
    escrito à mão, que não passa pelo brain nenhum."""
    n = _conta_palavras(*textos)
    if n > PALAVRAS_MAX:
        avisos.append(f"slide {i}: {n} palavras (o teto é {PALAVRAS_MAX}) — "
                      "a fonte vai encolher e o slide vira parágrafo")


def _numero_do_slide(img, d, i: int, n: int, claro: bool):
    """"3/6" no alto à direita — diz que tem mais, e quanto falta."""
    _, cinza = _tintas(claro)
    f = R._fonte(_px(NUM_FONT), negrito=False)
    txt = f"{i}/{n}"
    larg = R._texto_rico(None, d, 0, 0, txt, f, None, desenhar=False)
    R._texto_rico(img, d, _px(LARG - MARGEM) - larg, _px(LOGO_Y + NOME_DY),
                  txt, f, cinza)


# ══════════════════════════════════════════════════════════════════════════
# OS TRÊS TIPOS DE SLIDE
# ══════════════════════════════════════════════════════════════════════════
def _slide_capa(plano: dict, total: int, claro: bool, cor_fundo: tuple,
                avisos: list):
    img, d = _tela(claro, cor_fundo)
    tinta, cinza = _tintas(claro)
    capa = plano.get("capa") or {}
    _cabecalho(img, d, plano.get("nicho", "geral"), plano.get("handle", ""),
               claro, avisos)
    # a capa também é numerada (1/8). Antes eu tinha deixado sem, achando que
    # poluía; numerada ela ANUNCIA o tamanho do post logo no feed, e é isso que
    # faz a pessoa começar a arrastar em vez de passar.
    _numero_do_slide(img, d, 1, total, claro)

    hook = _limpa_marcas((capa.get("hook") or "").strip())
    if not hook:
        avisos.append("a capa veio SEM hook — é o único slide que o feed mostra")
    _vigiar_palavras(avisos, 1, hook)
    linhas, f = _texto_que_cabe(d, hook, CAPA_FONT, CAPA_FONT_MIN,
                                _px(LARG - 2 * MARGEM), CAPA_MAX_LINHAS)
    _bloco_centrado(img, d, linhas, f, tinta, CAPA_Y_TOPO, CAPA_Y_BASE)

    # rodapé "arrasta" — o swipe é o sinal que decide se o carrossel é
    # entregue de novo; pedir explicitamente custa uma linha.
    # ⚠️ 👉 e não "→": a seta U+2192 não existe na Montserrat nem na Liberation
    # e sai como espaço vazio. O emoji passa pelo caminho colorido do
    # `_texto_rico`, que não depende da fonte de texto ter o glifo.
    arrasta = (capa.get("arrasta") or "arrasta pro lado 👉").strip()
    R._texto_rico(img, d, _px(MARGEM), _px(1232), arrasta,
                  R._fonte(_px(38), negrito=False), cinza)
    return img


def _slide_produto(item: dict, i: int, n: int, plano: dict, claro: bool,
                   cor_fundo: tuple, avisos: list):
    img, d = _tela(claro, cor_fundo)
    tinta, cinza = _tintas(claro)
    _cabecalho(img, d, plano.get("nicho", "geral"), plano.get("handle", ""),
               claro, avisos)
    _numero_do_slide(img, d, i, n, claro)
    _vigiar_palavras(avisos, i, item.get("titulo"), item.get("linha"))

    foto = item.get("foto")
    if foto and Path(foto).exists():
        _foto_arredondada(img, Path(foto), _px(MARGEM), _px(FOTO_Y),
                          _px(LARG - 2 * MARGEM), _px(FOTO_H))
    else:
        avisos.append(f"slide {i}: sem foto ({foto or 'não informada'})")
        d.rounded_rectangle((_px(MARGEM), _px(FOTO_Y),
                             _px(LARG - MARGEM), _px(FOTO_Y + FOTO_H)),
                            radius=_px(FOTO_RAIO), outline=cinza, width=_px(3))

    # ⚠️ DAQUI PRA BAIXO O `y` ESTÁ EM PIXEL DO CANVAS 2x, não do quadro final.
    # Misturar as duas unidades na mesma variável já me custou um layout: a
    # fonte devolve `size` em 2x e a constante está em 1x, e a soma "funciona"
    # com um resultado errado que só aparece quando alguém muda o SUPER.
    y_s = _px(FOTO_Y + FOTO_H + 46)

    titulo = _limpa_marcas((item.get("titulo") or "").strip())
    linhas, f = _texto_que_cabe(d, titulo, TITULO_FONT, TITULO_MIN,
                                _px(LARG - 2 * MARGEM), 2)
    alt_linha = int(getattr(f, "size", 40) * 1.18)
    for ln in linhas:
        R._texto_rico(img, d, _px(MARGEM), y_s + alt_linha // 2, ln, f, tinta)
        y_s += alt_linha

    preco = (item.get("preco") or "").strip()
    if preco:
        fp = R._fonte(_px(PRECO_FONT))
        larg = R._texto_rico(None, d, 0, 0, preco, fp, None, desenhar=False)
        pad, altp = _px(30), _px(84)
        topo = y_s + _px(18)
        _pilula(d, _px(MARGEM), topo, larg + 2 * pad, altp, COR_MARCA)
        R._texto_rico(img, d, _px(MARGEM) + pad, topo + altp // 2, preco, fp,
                      (0, 0, 0, 255))
    return img


_RX_MARCA = re.compile(r"\*([^*]+)\*")


def _limpa_marcas(t: str) -> str:
    return _RX_MARCA.sub(r"\1", t or "")


_RX_TARJA = re.compile(r"\[([^\]]+)\]")


def _marcacao_tarja(texto: str) -> tuple:
    """`"3 ERROS [NA CASA]"` → `("3 ERROS NA CASA", {2, 3})`.

    ⚠️ A TARJA É O QUE MAIS SEPARA A NOSSA CAPA DA REFERÊNCIA. Nas capas que o
    Dre mandou, "NA CASA" não é texto laranja — é texto PRETO sobre um bloco
    laranja. Letra colorida some no meio da foto; bloco sólido não some, e é
    ele que o olho encontra primeiro no feed. São dois níveis de ênfase:
        *palavra*   → letra na cor do nicho
        [palavra]   → bloco na cor do nicho, letra preta
    """
    palavras, tarja, pos = [], set(), 0
    for m in _RX_TARJA.finditer(texto or ""):
        palavras.extend((texto[pos:m.start()]).split())
        for w in m.group(1).split():
            tarja.add(len(palavras))
            palavras.append(w)
        pos = m.end()
    palavras.extend((texto[pos:]).split())
    return " ".join(palavras), tarja


def _marcacao(texto: str) -> tuple:
    """`"5 ERROS *QUE ACABAM*"` → `("5 ERROS QUE ACABAM", {2, 3})`.

    ⚠️ A MARCAÇÃO É POR PALAVRA, NÃO POR TRECHO — e isso não é preferência, é
    a única coisa que funciona. Na 1ª tentativa eu procurava o par de
    asteriscos DEPOIS da quebra de linha, e a quebra partia a marca ao meio:
    `*ACABANDO COM` numa linha, `SUA BATERIA*` na outra. Nenhuma das duas tem
    par, então nada pintava e os asteriscos saíam literais no slide.
    Guardando o ÍNDICE das palavras destacadas, a quebra pode cair onde quiser.
    De quebra resolve a medição: quem é quebrado é o texto limpo, sem os
    asteriscos que não seriam desenhados."""
    palavras, destaque, pos = [], set(), 0
    for m in _RX_MARCA.finditer(texto or ""):
        palavras.extend((texto[pos:m.start()]).split())
        for w in m.group(1).split():
            destaque.add(len(palavras))
            palavras.append(w)
        pos = m.end()
    palavras.extend((texto[pos:]).split())
    return " ".join(palavras), destaque


def _escreve_marcado(img, d, x: int, y_meio: int, linha: str, fonte, cor,
                     cor_destaque, i0: int, destaque: set, tarja: set = None,
                     sombra: int = 0) -> int:
    """Escreve uma linha palavra a palavra. Devolve o índice da próxima.

    `sombra` > 0 desenha o texto deslocado em preto por baixo. ⚠️ SOBRE FOTO
    ISSO NÃO É ENFEITE: mesmo com o véu, letra branca sobre uma região clara da
    imagem perde a borda. A regra do Dre é contorno só branco — que aqui não
    serve, porque a letra JÁ é branca. Sombra resolve sem contornar."""
    tarja = tarja or set()
    espaco = d.textlength(" ", font=fonte)
    alt = int(getattr(fonte, "size", 40))
    cur, i = float(x), i0
    for w in (linha or "").split():
        larg = R._texto_rico(None, d, 0, 0, w, fonte, None, desenhar=False)
        if i in tarja:
            pad = int(alt * 0.16)
            d.rectangle((int(cur) - pad, y_meio - int(alt * 0.62),
                         int(cur) + larg + pad, y_meio + int(alt * 0.48)),
                        fill=cor_destaque)
            R._texto_rico(img, d, int(cur), y_meio, w, fonte, (0, 0, 0, 255))
        else:
            if sombra:
                R._texto_rico(img, d, int(cur) + sombra, y_meio + sombra, w,
                              fonte, (0, 0, 0, 190))
            R._texto_rico(img, d, int(cur), y_meio, w, fonte,
                          cor_destaque if i in destaque else cor)
        cur += larg + espaco
        i += 1
    return i


def _foto_de_fundo(img, caminho: Path, escuro: int):
    """A foto COBRE o slide inteiro, com um véu escuro por cima.

    ⚠️ O VÉU NÃO É ESTÉTICA, É LEGIBILIDADE. Texto branco sobre foto de produto
    sem véu some em qualquer região clara — e a regra do Dre é contorno só
    branco, que aqui não serve (o texto já é branco). O véu resolve sem
    contorno nenhum, que é o que aquelas referências fazem."""
    from PIL import Image
    _foto_arredondada(img, caminho, 0, 0, _px(LARG), _px(ALT))

    # ⚠️ VÉU EM GRADIENTE, NÃO CHAPADO. Chapado em 170 o produto sumia junto
    # com o texto — a foto virava uma mancha de cor. O texto mora no TERÇO
    # SUPERIOR; então é lá que o véu é forte e embaixo ele quase some, deixando
    # o produto aparecer. É o que as referências fazem, e é o que separa
    # "foto de fundo" de "fundo colorido".
    alt, larg = _px(ALT), _px(LARG)
    topo = max(0, min(255, escuro))
    pe = int(topo * 0.35)
    faixa = Image.new("L", (1, alt))
    faixa.putdata([int(topo + (pe - topo) * (y / max(1, alt - 1)))
                   for y in range(alt)])
    veu = Image.new("RGBA", (larg, alt), (0, 0, 0, 255))
    veu.putalpha(faixa.resize((larg, alt)))
    img.alpha_composite(veu, (0, 0))


def _slide_capa_dramatica(plano: dict, total: int, foto: Path, avisos: list):
    """A capa das referências: foto de fundo, CAIXA ALTA, destaque em cor."""
    from PIL import Image, ImageDraw
    nicho = plano.get("nicho", "geral")
    img = Image.new("RGBA", (_px(LARG), _px(ALT)), (12, 12, 12, 255))
    d = ImageDraw.Draw(img)
    _foto_de_fundo(img, foto, CAPA_ESCURO)

    branco = (255, 255, 255, 255)
    cor_dest = (*_cor_destaque(nicho), 255)
    capa = plano.get("capa") or {}

    _cabecalho(img, d, nicho, plano.get("handle", ""), False, avisos)

    # duas marcações no mesmo texto: [tarja] e *cor*. A tarja é extraída
    # primeiro porque ela some do texto; a cor roda sobre o que sobrou.
    bruto = (capa.get("hook") or "").strip().upper()
    sem_tarja, tarja = _marcacao_tarja(bruto)
    hook, destaque = _marcacao(sem_tarja)
    _vigiar_palavras(avisos, 1, hook)
    linhas, f = _texto_que_cabe(d, hook, CAPA_TITULO_FONT, CAPA_TITULO_MIN,
                                _px(LARG - 2 * MARGEM), 4, titulo=True)
    alt_linha = int(getattr(f, "size", 40) * 1.06)   # condensado: linhas juntas
    y, i = _px(290), 0
    for ln in linhas:
        i = _escreve_marcado(img, d, _px(MARGEM), y + alt_linha // 2, ln, f,
                             branco, cor_dest, i, destaque, tarja,
                             sombra=_px(4))
        y += alt_linha

    sub, dsub = _marcacao((capa.get("sub") or "").strip().upper())
    if sub:
        y += _px(26)
        fs = R._fonte(_px(CAPA_SUB_FONT))
        j = 0
        for ln in R._quebrar(d, sub, fs, _px(LARG - 2 * MARGEM), 3):
            j = _escreve_marcado(img, d, _px(MARGEM), y + _px(30), ln, fs,
                                 branco, cor_dest, j, dsub)
            y += _px(58)

    # ⚠️ O "1/8" VAI PRO TOPO DIREITO, na altura do @handle — é onde ele está
    # nas referências, e faz sentido: ali ele é lido junto com a marca, sem
    # disputar espaço com o hook. No rodapé eu o tinha posto sozinho, longe de
    # tudo, e ele sumia.
    txt = f"1/{total}"
    fp = R._fonte(_px(32))
    larg = R._texto_rico(None, d, 0, 0, txt, fp, None, desenhar=False)
    pad, altp = _px(20), _px(52)
    x1, ymeio = _px(LARG - MARGEM), _px(LOGO_Y + NOME_DY)
    d.rounded_rectangle((x1 - larg - 2 * pad, ymeio - altp // 2, x1,
                         ymeio + altp // 2),
                        radius=_px(16), outline=cor_dest, width=_px(3))
    R._texto_rico(img, d, x1 - larg - pad, ymeio, txt, fp, branco)

    # badge "ARRASTA PRO LADO" — nas referências ele é uma peça com contorno,
    # não texto solto. O arrasto é o sinal que decide a entrega do carrossel;
    # pedir de um jeito que se vê custa 6 linhas.
    arrasta = (capa.get("arrasta") or "ARRASTA PRO LADO").strip().upper()
    fa = R._fonte(_px(34))
    larg = R._texto_rico(None, d, 0, 0, arrasta, fa, None, desenhar=False)
    pad, altb = _px(30), _px(74)
    x0, y0 = _px(MARGEM), _px(ALT - 132)
    d.rounded_rectangle((x0, y0, x0 + larg + 2 * pad, y0 + altb),
                        radius=altb // 2, outline=cor_dest, width=_px(3))
    R._texto_rico(img, d, x0 + pad, y0 + altb // 2, arrasta, fa, branco)
    return img


def _slide_texto(item: dict, i: int, n: int, plano: dict, claro: bool,
                 cor_fundo: tuple, avisos: list):
    """Slide de TEXTO: rótulo em pílula + frase grande. Foto é opcional.

    ⚠️ SEM ESTE TIPO, METADE DOS FORMATOS NÃO EXISTE. "Erros", "Passo a passo",
    "História" e "Mitos" são slides de frase, não de vitrine — mandá-los pelo
    `_slide_produto` desenhava uma moldura de foto vazia embaixo de cada erro.
    A pílula ("ERRO 1", "PASSO 2", "ANTES") é o que dá ritmo ao arrasto: a
    pessoa sabe onde está na sequência sem ler."""
    img, d = _tela(claro, cor_fundo)
    tinta, cinza = _tintas(claro)
    _cabecalho(img, d, plano.get("nicho", "geral"), plano.get("handle", ""),
               claro, avisos)
    _numero_do_slide(img, d, i, n, claro)
    _vigiar_palavras(avisos, i, item.get("titulo"), item.get("linha"))

    # ⚠️ MEDE ANTES DE DESENHAR. Começando sempre no mesmo y, um slide de uma
    # frase curta ficava com meia tela de branco no pé — parece slide que
    # faltou carregar, e a pessoa para de arrastar. Com foto o bloco encosta no
    # topo (a foto ocupa o resto); sem foto, ele é centrado na faixa livre.
    largura = _px(LARG - 2 * MARGEM)
    rotulo = (item.get("rotulo") or "").strip().upper()
    fr, pad, altp = R._fonte(_px(38)), _px(26), _px(66)
    alt_rot = (altp + _px(56)) if rotulo else 0

    titulo, destaque = _marcacao((item.get("titulo") or "").strip())
    linhas, f = _texto_que_cabe(d, titulo, 84, 52, largura, 4)
    alt_linha = int(getattr(f, "size", 40) * CAPA_ALT_LINHA)

    apoio = (item.get("linha") or "").strip()
    fa = R._fonte(_px(40), negrito=False)
    linhas_apoio = R._quebrar(d, apoio, fa, largura, 3) if apoio else []
    alt_apoio = (_px(30) + len(linhas_apoio) * _px(58)) if linhas_apoio else 0

    foto = item.get("foto")
    tem_foto = bool(foto and Path(foto).exists())
    total = alt_rot + len(linhas) * alt_linha + alt_apoio
    y_s = _px(300) if tem_foto else max(_px(280),
                                        _px((300 + 1240) / 2) - total // 2)

    if rotulo:
        larg = R._texto_rico(None, d, 0, 0, rotulo, fr, None, desenhar=False)
        _pilula(d, _px(MARGEM), y_s, larg + 2 * pad, altp, COR_MARCA)
        R._texto_rico(img, d, _px(MARGEM) + pad, y_s + altp // 2, rotulo, fr,
                      (0, 0, 0, 255))
        y_s += alt_rot

    cor_dest = (*_cor_destaque(plano.get("nicho", "geral")), 255)
    i = 0
    for ln in linhas:
        i = _escreve_marcado(img, d, _px(MARGEM), y_s + alt_linha // 2, ln, f,
                             tinta, cor_dest, i, destaque)
        y_s += alt_linha

    if linhas_apoio:
        y_s += _px(30)
        for ln in linhas_apoio:
            R._texto_rico(img, d, _px(MARGEM), y_s + _px(28), ln, fa, cinza)
            y_s += _px(58)

    # foto opcional, no que sobrou do pé — só entra se couber inteira
    if tem_foto:
        sobra = _px(ALT - 70) - y_s
        if sobra > _px(240):
            alt_f = min(sobra - _px(40), _px(420))
            larg_f = int(alt_f * 1.15)
            _foto_arredondada(img, Path(foto), _px(MARGEM), y_s + _px(40),
                              larg_f, alt_f)
    return img


def _slide_resumo(item: dict, i: int, n: int, plano: dict, claro: bool,
                  cor_fundo: tuple, avisos: list):
    """A lista do que foi dito — o slide feito pra ser SALVO.

    ⚠️ ESTE É O SLIDE QUE ATACA O NOSSO PIOR NÚMERO. 47.202 impressões deram 48
    salvamentos (1 a cada mil), e salvamento é o sinal que faz o Instagram
    entregar pra quem não segue. Ninguém salva uma capa; salva-se a página que
    resume. Por isso ele é o penúltimo, e não o último: depois dele ainda vem o
    pedido."""
    img, d = _tela(claro, cor_fundo)
    tinta, cinza = _tintas(claro)
    _cabecalho(img, d, plano.get("nicho", "geral"), plano.get("handle", ""),
               claro, avisos)
    _numero_do_slide(img, d, i, n, claro)
    cor_dest = (*_cor_destaque(plano.get("nicho", "geral")), 255)

    itens = [str(x) for x in (item.get("itens") or []) if str(x).strip()]
    y_s = _px(300)
    rotulo = (item.get("rotulo") or "SALVA ISSO").strip().upper()
    fr = R._fonte(_px(38))
    larg = R._texto_rico(None, d, 0, 0, rotulo, fr, None, desenhar=False)
    pad, altp = _px(26), _px(66)
    _pilula(d, _px(MARGEM), y_s, larg + 2 * pad, altp, COR_MARCA)
    R._texto_rico(img, d, _px(MARGEM) + pad, y_s + altp // 2, rotulo, fr,
                  (0, 0, 0, 255))
    y_s += altp + _px(60)

    # ⚠️ a fonte encolhe com a QUANTIDADE de itens, não com o comprimento de
    # cada um: 7 itens em corpo 54 estouram o slide, e quem descobriria isso
    # seria o leitor, não o log.
    corpo = 54 if len(itens) <= 4 else (46 if len(itens) <= 6 else 40)
    f = R._fonte(_px(corpo))
    passo = _px(int(corpo * 1.85))
    for k, txt in enumerate(itens[:7], 1):
        n_larg = R._texto_rico(img, d, _px(MARGEM), y_s + passo // 2,
                               f"{k}", f, cor_dest)
        R._texto_rico(img, d, _px(MARGEM) + n_larg + _px(22), y_s + passo // 2,
                      _limpa_marcas(txt), f, tinta)
        y_s += passo
    return img


def _slide_cta(plano: dict, n: int, claro: bool, cor_fundo: tuple, avisos: list):
    img, d = _tela(claro, cor_fundo)
    tinta, cinza = _tintas(claro)
    cta = plano.get("cta") or {}
    _cabecalho(img, d, plano.get("nicho", "geral"), plano.get("handle", ""),
               claro, avisos)
    _numero_do_slide(img, d, n, n, claro)

    titulo = (cta.get("titulo") or "Salva esse post\npra não perder").strip()
    linhas, f = _texto_que_cabe(d, titulo.replace("\n", " "), CTA_FONT, 52,
                                _px(LARG - 2 * MARGEM), 3)
    pedidos = [str(x) for x in (cta.get("linhas") or [])]

    # o conjunto (título + pedidos) é centrado JUNTO. Antes o título centrava
    # sozinho e os pedidos vinham num y fixo, o que abria um vão morto no meio
    # do slide sempre que o título ocupava menos linhas do que o teto.
    alt_pedido = _px(66)
    desce = (len(pedidos) * alt_pedido) // 2
    fim = _bloco_centrado(img, d, linhas, f, tinta, 300 - desce // SUPER,
                          1060 - desce // SUPER)

    y = fim + _px(74)
    f_ped = R._fonte(_px(CTA_LINHA_FONT), negrito=False)
    for ln in pedidos:
        R._texto_rico(img, d, _px(MARGEM), y, ln, f_ped, cinza)
        y += alt_pedido
    return img


# ══════════════════════════════════════════════════════════════════════════
# RENDER
# ══════════════════════════════════════════════════════════════════════════
def renderizar(plano: dict, saida) -> list:
    """Desenha o carrossel inteiro. Devolve a lista de JPEGs, NA ORDEM.

    O plano manda; este módulo não escolhe produto, não escreve hook e não
    decide conta — só desenha o que recebe."""
    from PIL import Image

    nicho = plano.get("nicho") or "geral"
    if not plano.get("handle"):
        plano["handle"] = _handle_do_nicho(nicho)
    claro, cor_fundo = R._cor_fundo(nicho)

    itens = plano.get("slides") or []
    if not itens:
        raise ValueError("plano sem 'slides' — não há carrossel sem produto")

    total = 1 + len(itens) + (1 if plano.get("cta") is not False else 0)
    if total > 10:
        # ⚠️ A Meta corta em 10 filhos. Melhor aparar aqui, com aviso, do que
        # descobrir no publish que os últimos produtos sumiram em silêncio.
        sobra = total - 10
        itens = itens[:-sobra]
        total = 10
        log.warning(f"   ⚠️  carrossel tem no máximo 10 slides — deixei "
                    f"{sobra} produto(s) de fora")

    avisos, telas = [], []
    # ⚠️ A CAPA DRAMÁTICA EXIGE FOTO. Sem foto ela seria um retângulo preto com
    # texto — pior que a capa limpa. Então a escolha é pelo material que existe,
    # não por preferência: tem foto → dramática; não tem → limpa.
    # ⚠️ O FUNDO DE IA VEM ANTES DA FOTO DO PRODUTO, e é a diferença entre a
    # nossa capa e as referências: foto de catálogo escurecida vira mancha,
    # ambiente com profundidade vira capa. Sem fundo gerado, cai na foto do
    # produto (o que funcionava antes) e nada quebra.
    # A ordem é: fundo escolhido à mão → fundo de IA → foto do produto.
    # ⚠️ O FUNDO DE IA VEM ANTES DA FOTO DO PRODUTO, não depois, e essa ordem é
    # o ponto: o brain SEMPRE preenche `capa.foto` com a foto do produto, então
    # deixar ela na frente faria o fundo gerado nunca ser usado. Sem fundo
    # gerado, cai na foto do produto — o que já funcionava — e nada quebra.
    foto_capa = (plano.get("capa") or {}).get("fundo") or ""
    if not foto_capa:
        try:
            from fundo_ia import fundo_do_nicho
            foto_capa = fundo_do_nicho(nicho)
            if foto_capa:
                log.info(f"   🖼️  fundo de IA: {Path(foto_capa).name}")
        except Exception:
            pass
    if not foto_capa:
        foto_capa = ((plano.get("capa") or {}).get("foto")
                     or next((s.get("foto") for s in itens if s.get("foto")), ""))
    if _capa_dramatica_ligada() and foto_capa and Path(foto_capa).exists():
        telas.append(_slide_capa_dramatica(plano, total, Path(foto_capa), avisos))
    else:
        if _capa_dramatica_ligada() and not foto_capa:
            avisos.append("capa limpa: nenhum slide trouxe foto pra usar de fundo")
        telas.append(_slide_capa(plano, total, claro, cor_fundo, avisos))
    for k, item in enumerate(itens, start=2):
        # `tipo` manda; sem ele, o slide é de PRODUTO só quando tem o que uma
        # vitrine precisa (preço). Assim um plano antigo, sem `tipo`, continua
        # desenhando igual, e um slide de frase nunca ganha moldura de foto
        # vazia por omissão de campo.
        tipo = (item.get("tipo") or ("produto" if item.get("preco") else "texto"))
        desenha = {"produto": _slide_produto,
                   "resumo": _slide_resumo}.get(tipo, _slide_texto)
        telas.append(desenha(item, k, total, plano, claro, cor_fundo, avisos))
    if plano.get("cta") is not False:
        telas.append(_slide_cta(plano, total, claro, cor_fundo, avisos))

    pasta = Path(saida)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivos = []
    for k, tela in enumerate(telas, start=1):
        # reduz do 2x pro tamanho final: é aqui que a sobra de pixel vira borda
        # limpa na letra, do mesmo jeito que o Reel faz
        final = tela.convert("RGB").resize((LARG, ALT), Image.LANCZOS)
        arq = pasta / f"{k:02d}.jpg"     # JPEG: único formato que a Meta aceita
        final.save(arq, "JPEG", quality=JPEG_Q, optimize=True)
        arquivos.append(arq)

    for a in dict.fromkeys(avisos):
        log.warning(f"   ⚠️  {a}")
    log.info(f"   🎠 {len(arquivos)} slide(s) em {pasta}")

    if plano.get("legenda"):
        (pasta / "legenda.txt").write_text(plano["legenda"], encoding="utf-8")
    return arquivos


# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════
_EXEMPLO = {
    "nicho": "casa",
    "capa": {"hook": "Gastei 3 anos limpando errado e ninguém me avisou",
             "arrasta": "arrasta pro lado 👉"},
    "slides": [
        {"titulo": "Rodo mágico que seca o chão de uma passada",
         "preco": "R$ 29,90", "foto": ""},
        {"titulo": "Organizador de pia que some com a bagunça",
         "preco": "R$ 18,50", "foto": ""},
        {"titulo": "Pano de microfibra que não deixa marca no vidro",
         "preco": "R$ 12,90", "foto": ""},
    ],
    "cta": {"titulo": "Salva esse post pra não perder",
            "linhas": ["🛒 link na bio", "💬 comenta QUERO que eu te mando"]},
    "legenda": "3 achadinhos que mudaram a minha limpeza 🧽",
}


def main() -> int:
    p = argparse.ArgumentParser(description="Renderiza os slides de um carrossel")
    p.add_argument("--plano", help="JSON do plano do carrossel")
    p.add_argument("--saida", default="pronto_carrossel/teste",
                   help="pasta onde os slides são gravados")
    p.add_argument("--exemplo", metavar="NICHO", nargs="?", const="casa",
                   help="renderiza um carrossel de demonstração (sem plano)")
    p.add_argument("--diag", action="store_true",
                   help="diz de ONDE vêm a fonte e a logo, e o que achou")
    a = p.parse_args()

    if a.diag:
        # ⚠️ ISTO EXISTE PORQUE A CAPA SAIU EM MONTSERRAT NA VPS COM A ANTON
        # INSTALADA, e não havia como saber se o problema era o arquivo, a
        # pasta ou a versão do módulo. Três hipóteses, nenhum jeito de separar
        # — que é exatamente o buraco que uma linha de log fecha.
        from PIL import ImageFont
        print(f"render.py         {Path(R.__file__).resolve()}")
        print(f"BRAND_DIR         {R.BRAND_DIR}  (existe: {R.BRAND_DIR.exists()})")
        print(f"capa dramática    {'ligada' if _capa_dramatica_ligada() else 'DESLIGADA (CARR_CAPA=limpa)'}")
        print("\ncondensadas procuradas, na ordem:")
        achou = ""
        for nome in _CONDENSADAS:
            arq = R.BRAND_DIR / nome
            ok = arq.exists()
            print(f"  {'✅' if ok else '⬜'} {nome:<28} {arq}")
            if ok and not achou:
                achou = nome
        f = fonte_titulo(80)
        nome_real = getattr(f, "path", "?")
        print(f"\nfonte de título em uso: {nome_real}")
        if not achou:
            print("  ⚠️  nenhuma condensada em BRAND_DIR — a capa sai em Montserrat.")
            print(f"  Se o baixar_fontes.py gravou em OUTRA pasta, é ESSA a causa.")
            print(f"  Rode:  .venv/bin/python baixar_fontes.py --listar")
        return 0

    if a.exemplo:
        plano = dict(_EXEMPLO, nicho=a.exemplo)
        saida = a.saida if a.plano or a.saida != "pronto_carrossel/teste" \
            else f"pronto_carrossel/exemplo_{a.exemplo}"
    elif a.plano:
        plano = json.loads(Path(a.plano).read_text(encoding="utf-8"))
        saida = a.saida
    else:
        p.print_help()
        print("\nDica: --exemplo casa  (ou geral/beleza/tech/pet/moda)")
        return 1

    arquivos = renderizar(plano, saida)
    print("\n".join(str(x) for x in arquivos))
    print(f"\nPra postar:  .venv/bin/python -m agents.meta_uploader "
          f"--carrossel {' '.join(str(x) for x in arquivos)} --legenda '...'")
    print("(o conta.json precisa estar na MESMA pasta dos slides)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
