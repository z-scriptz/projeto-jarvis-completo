#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# slides_html.py — o SISTEMA DE DESIGN do carrossel, em HTML/CSS.
#
# ⚠️ POR QUE ISTO SUBSTITUI O DESENHO EM PIL (22/08):
#
# O Dre mostrou um carrossel feito pelo Claude Design ao lado do meu e
# perguntou qual eu preferia. O dele, sem discussão — e o motivo não é gosto:
#
#   o meu   → uma CAPA bonita, e slides internos que não conversavam com ela
#   o dele  → um SISTEMA: paleta, escala tipográfica, formas de fundo e
#             hierarquia que se repetem slide a slide
#
# Carrossel não se julga por slide, se julga por sequência. Sete peças que
# parecem sete posts diferentes é o que faz um carrossel parecer amador, e era
# exatamente o que estava saindo daqui.
#
# ⚠️ E A TECNOLOGIA JÁ ERA A CERTA. Aquele design é HTML/CSS — o mesmo motor
# que já está na VPS. O que faltava não era ferramenta, era DECISÃO DE DESIGN.
# Hugging Face, ChatGPT, Fal: nenhum resolveria isso, porque nenhum é o
# problema. Um modelo de imagem faria a peça bonita e a marca infiel; aqui a
# logo, o @, o preço e a cor da conta saem exatos, de graça e em 2 segundos.
#
# O SISTEMA, em três tipos de slide:
#   CAPA      fundo escuro, tag do nicho, título gigante com a última linha
#             em cor, @handle e o botão de arrasto
#   CONTEÚDO  fundo creme, círculo numerado, título display, corpo em cinza,
#             pílula de conclusão, paginação 02/06
#   FECHO     fundo na cor da conta, título, pedido, @handle
#
# USO:
#   python3 slides_html.py --exemplo casa --saida /tmp/demo
#   from slides_html import renderizar_slides
#   arquivos = renderizar_slides(plano, pasta)   # -> [Path, ...] na ordem

import os
import re
import sys
import json
import base64
import random
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("slides_html")

LARG, ALT = 1080, 1350
ESCALA = 2

# ══════════════════════════════════════════════════════════════════════════
# PALETA POR CONTA
#
# ⚠️ CADA CONTA TEM UM TRIO, NÃO UMA COR. `acento` pinta o fecho e os
# círculos; `creme` é o fundo dos slides de conteúdo; `sombra` é a mancha
# geométrica atrás do número. Uma cor só não faz sistema — faz destaque.
# E a família é a MESMA nas seis contas (mesma tipografia, mesmas formas,
# mesma hierarquia): o que muda é o trio. Assim o grid de cada conta tem
# identidade própria e as seis continuam sendo, visivelmente, a mesma marca.
# ══════════════════════════════════════════════════════════════════════════
PALETAS = {
    "casa":   {"acento": "#C1662F", "creme": "#F2E8DC", "sombra": "#FBDFCE",
               "escuro": "#26221F", "clarinho": "#F6EFE6"},
    "tech":   {"acento": "#2F6F5E", "creme": "#E8EFEA", "sombra": "#CFE3D8",
               "escuro": "#1B2320", "clarinho": "#EDF3EF"},
    "beleza": {"acento": "#B4568A", "creme": "#F5E7EE", "sombra": "#F7D6E4",
               "escuro": "#241C21", "clarinho": "#F9EDF2"},
    "pet":    {"acento": "#2F6FA8", "creme": "#E6EEF5", "sombra": "#D2E4F2",
               "escuro": "#1B2229", "clarinho": "#EDF3F8"},
    "moda":   {"acento": "#C2456B", "creme": "#F6E7EA", "sombra": "#F8D5DD",
               "escuro": "#241B1E", "clarinho": "#FAEEF0"},
    "geral":  {"acento": "#B98B2E", "creme": "#F4EDDD", "sombra": "#F6E4BC",
               "escuro": "#232019", "clarinho": "#F8F2E6"},
}

# título = serifada display · corpo = geométrica. ⚠️ Fraunces é VARIÁVEL: o
# peso e o "SOFT" (arredondamento das serifas) são setados no CSS, não no
# arquivo — é isso que dá o desenho macio das referências sem comprar fonte.
_TITULO = ("Fraunces.ttf", "BreeSerif-Regular.ttf", "Anton-Regular.ttf")
_CORPO = ("Poppins-Medium.ttf", "Poppins-SemiBold.ttf", "Montserrat-Bold.ttf")

_RX_MARCA = re.compile(r"\*([^*]+)\*|\[([^\]]+)\]")


def _paleta(nicho: str) -> dict:
    return PALETAS.get((nicho or "geral").lower(), PALETAS["geral"])


# ══════════════════════════════════════════════════════════════════════════
# FOTO DE FUNDO
#
# ⚠️ O Dre: *"o ideal é que cada slide tenha um fundo chamativo, e não fique só
# com cores, mas literalmente imagens"*. Certo — mas olhando as referências do
# Claude Design com atenção, elas **não** põem foto em todo slide, e o motivo
# aparece nelas mesmas:
#
#   CAPA e FECHO  → foto cheia, escurecida. É onde tem 5 palavras.
#   CONTEÚDO      → foto SÓ NO TOPO, com fade pro creme (ou fundo sólido).
#                   É onde tem um PARÁGRAFO, e parágrafo sobre foto se lê mal.
#
# Ou seja: a foto entra onde ela ajuda o olho a parar, e sai de onde ela
# atrapalha o olho a ler. Copiar "foto em tudo" deixaria o carrossel bonito na
# miniatura e ilegível no celular — que é onde ele é lido.
#
# ⚠️ E A FONTE DA IMAGEM É PLUGÁVEL DE PROPÓSITO: qualquer JPG em
# `assets/fundos/<nicho>/` entra no rodízio. Foto sua, print, imagem gerada,
# banco de imagem — o módulo não sabe e não precisa saber de onde veio. Assim
# a decisão de ONDE arrumar foto (que é sua, e mudou duas vezes hoje) não fica
# soldada no código do desenho.
# ══════════════════════════════════════════════════════════════════════════
def _fundo(plano: dict, item: dict = None) -> str:
    """data: URI da foto de fundo, ou "" — nessa ordem: a do slide, a do
    plano, uma do acervo do nicho."""
    # ⚠️ `isinstance(cand, str)` NÃO É PARANOIA. O plano vem de JSON escrito
    # pelo Gemini e por três módulos diferentes; um `fundo: true` (em vez do
    # caminho) fez `Path(True)` levantar TypeError aqui dentro. E o estrago não
    # foi o erro: foi que o `renderizar_slides` engole exceção, devolve [] e o
    # carrossel cai no desenho em PIL — ou seja, o post sai FEIO, sai
    # publicado, e o log não diz que houve um erro de tipo num campo.
    for cand in ((item or {}).get("fundo"), (item or {}).get("foto"),
                 (plano.get("capa") or {}).get("fundo")):
        if isinstance(cand, str) and cand and Path(cand).exists():
            return _b64(cand)
    try:
        from fundo_ia import fundo_do_nicho
        alvo = fundo_do_nicho(plano.get("nicho", "geral"))
        if alvo:
            return _b64(alvo)
    except Exception:
        pass
    return ""


def _brand() -> Path:
    try:
        import render as R
        return R.BRAND_DIR
    except Exception:
        return BASE_DIR / "assets" / "brand"


def _b64(caminho) -> str:
    p = Path(caminho)
    if not p.exists():
        return ""
    tipo = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "ttf": "font/ttf"}.get(
                p.suffix.lower().lstrip("."), "application/octet-stream")
    return f"data:{tipo};base64," + base64.b64encode(p.read_bytes()).decode()


def _primeira(nomes) -> str:
    brand = _brand()
    for n in nomes:
        u = _b64(brand / n)
        if u:
            return u
    return ""


def _logo(nicho: str) -> str:
    try:
        from shared.marca import logo_do_nicho
        nome = logo_do_nicho(nicho, log)
        nome = nome[0] if isinstance(nome, (tuple, list)) else nome
        return _b64(_brand() / str(nome))
    except Exception:
        return ""


def _logo_claro(nicho: str) -> bool:
    """A logo é clara (some em fundo claro) ou escura (some em fundo escuro)?

    ⚠️ ISTO EXISTE PORQUE O DEFEITO É INVISÍVEL PRO CÓDIGO. No carrossel de
    23/08 a logo saiu como um quadrado preto ilegível sobre marrom escuro — e
    nada falhou: o arquivo existe, o `<img>` carrega, o slide renderiza. Só um
    humano olhando percebe. Medir o brilho médio custa milissegundos e troca um
    palpite por um fato; sem isso eu teria que ESCOLHER um fundo de círculo e
    estar errado em metade das contas."""
    try:
        from PIL import Image
        from shared.marca import logo_do_nicho
        nome = logo_do_nicho(nicho, log)
        nome = nome[0] if isinstance(nome, (tuple, list)) else nome
        img = Image.open(_brand() / str(nome)).convert("RGBA")
        img.thumbnail((64, 64))
        somaL = somaA = 0
        for r, g, b, a in img.getdata():
            if a < 32:        # pixel transparente não é a logo, é o vazio
                continue
            somaL += (r * 299 + g * 587 + b * 114) // 1000
            somaA += 1
        return (somaL / somaA) > 128 if somaA else False
    except Exception:
        return False


def _cabecalho(plano: dict, i: int, total: int, escuro: bool,
               sobre_acento: bool = False) -> str:
    """Logo + marca + @ à esquerda, contador à direita. Em TODOS os slides.

    ⚠️ É ISTO QUE FAZ UM CARROSSEL PARECER DE UMA MARCA. Nas referências que o
    Dre mandou, o cabeçalho é idêntico nos 6 slides — é a âncora que deixa a
    composição variar embaixo sem o conjunto virar seis posts avulsos. O nosso
    tinha logo só na capa, e minúscula."""
    import html as _h
    p = _paleta(plano.get("nicho", "geral"))
    handle = _h.escape(plano.get("handle") or "")
    logo = _logo(plano.get("nicho", "geral"))
    cor = p["clarinho"] if escuro else "#1C1A18"

    # ⚠️ NO SLIDE `respiro` O FUNDO É A PRÓPRIA COR DE ACENTO, e o "Shop" saía
    # laranja sobre laranja: a marca virava "Top". Nada falhou — a cor existe,
    # o texto está lá, o contraste é que é zero. Peguei olhando o JPEG, não
    # lendo o código, e é o terceiro defeito desta família hoje (a logo escura
    # sobre escuro e o fundo .jpg que ninguém via são os outros dois).
    realce = p["escuro"] if sobre_acento else p["acento"]
    borda = p["clarinho"] if sobre_acento else p["acento"]

    # o círculo ganha fundo só quando a logo sumiria sem ele
    claro = _logo_claro(plano.get("nicho", "geral"))
    fundo = ("rgba(255,255,255,.92)" if (claro is False and escuro)
             else "rgba(0,0,0,.30)" if (claro and not escuro) else "transparent")
    selo = (f'<span class="selo" style="border-color:{borda};'
            f'background:{fundo}"><img src="{logo}"></span>') if logo else ""

    return f"""<header class="cabeca">
  <div class="marca">{selo}
    <div><div class="nome" style="color:{cor}">Top<em
      style="color:{realce};font-style:normal">Shop</em></div>
      <div class="arr" style="color:{cor}">{handle}</div></div></div>
  <div class="cont" style="color:{cor};border-color:{cor}55">{i}/{total}</div>
</header>"""


def _marcar(txt: str, cor: str) -> str:
    """`*x*` e `[x]` → destaque na cor. Devolve HTML escapado."""
    import html as _h
    saida, pos = [], 0
    for m in _RX_MARCA.finditer(txt or ""):
        saida.append(_h.escape(txt[pos:m.start()]))
        alvo = m.group(1) if m.group(1) is not None else m.group(2)
        saida.append(f'<em style="color:{cor};font-style:normal">'
                     f'{_h.escape(alvo)}</em>')
        pos = m.end()
    saida.append(_h.escape(txt[pos:]))
    return "".join(saida)


def _limpo(txt: str) -> str:
    return _RX_MARCA.sub(lambda m: m.group(1) or m.group(2), txt or "")


# ══════════════════════════════════════════════════════════════════════════
# CSS — um só, pros três tipos de slide
# ══════════════════════════════════════════════════════════════════════════
def _css(p: dict, fonte_t: str, fonte_c: str) -> str:
    return f"""
@font-face {{ font-family:'Disp'; src:url('{fonte_t}'); }}
@font-face {{ font-family:'Corpo'; src:url('{fonte_c}'); }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:{LARG}px; height:{ALT}px; overflow:hidden; font-family:'Corpo',
        sans-serif; -webkit-font-smoothing:antialiased; }}
.slide {{ position:relative; width:{LARG}px; height:{ALT}px; overflow:hidden;
          padding:86px 78px; display:flex; flex-direction:column; }}

/* ⚠️ A MANCHA É O QUE COSTURA A SEQUÊNCIA. Sem ela cada slide é um retângulo
   de cor com texto; com ela os slides parecem páginas do mesmo material. Ela
   sangra pra fora do quadro de propósito — forma cortada pela borda dá
   movimento, forma inteira e centrada dá apostila. */
.mancha {{ position:absolute; border-radius:50%; }}
/* ⚠️ A FOTO É UMA CAMADA, NÃO O `background` DO SLIDE. Como camada ela recebe
   filtro próprio (saturação, contraste, brilho) sem afetar o texto — foto de
   catálogo vem lavada e sem contraste, e é o filtro que tira a cara de
   catálogo. No `background` do slide, qualquer filtro apagaria a letra junto. */
.fototopo {{ position:absolute; left:0; right:0; top:0;
             background-position:center; background-size:cover;
             filter:saturate(1.12) contrast(1.06) brightness(.86); }}
.fotocheia {{ position:absolute; inset:0; background-position:center;
              background-size:cover;
              filter:saturate(1.1) contrast(1.05) brightness(.6); }}
/* o degradê que funde a foto no fundo sólido — é ele que deixa o parágrafo
   pousar em cor chapada mesmo com foto no mesmo slide */
.fade {{ position:absolute; left:0; right:0; }}
/* ⚠️ ELEMENTO POSICIONADO PINTA DEPOIS DO ESTÁTICO, mesmo vindo antes no
   HTML. Sem esta linha a mancha cobria o texto: no 1º teste a palavra "que"
   de "Guardar tudo o que sobrou" simplesmente sumiu atrás do círculo, e o
   título ficou agramatical sem nenhum erro aparecer em lugar nenhum. É o pior
   tipo de defeito visual — o post sai, publica, e só um humano lendo percebe. */
/* ⚠️ E AS CAMADAS DE FOTO PRECISAM FICAR DE FORA DESTA REGRA. Elas são
   `position:absolute`; o `position:relative` daqui sobrescrevia isso e o
   estrago era invisível de duas formas ao mesmo tempo: a `fotocheia` da capa
   perdia o `inset:0`, virava um div de altura zero e a foto simplesmente não
   aparecia; a `fototopo` do conteúdo caía no fluxo e passava a respeitar o
   padding do slide, ganhando uma margem branca dos lados que denunciava a
   montagem. Nenhum dos dois dá erro — os dois só saem errados. */
/* ⚠️ E EU CAÍ NELA DE NOVO, 23/08, com o `.gigante`. Ele nasceu `absolute`;
   esta regra o converteu em `relative`, ele caiu no fluxo como primeiro filho
   do flex e o "02" foi parar EM CIMA do cabeçalho, empurrando o resto. O
   comentário acima já avisava e mesmo assim aconteceu — porque a lista de
   exceções é o tipo de coisa que ninguém lembra de atualizar ao criar um
   elemento novo. **Toda camada `position:absolute` filha direta de `.slide`
   PRECISA entrar nesta lista.** */
.slide > *:not(.mancha):not(.fototopo):not(.fotocheia):not(.fade):not(.gigante)
  {{ position:relative; z-index:1; }}

/* título: a serifada, com peso e SOFT altos. `wonk` liga as formas
   alternativas do Fraunces — é o detalhe que tira a cara de Times. */
h1 {{ font-family:'Disp',Georgia,serif; font-variation-settings:'wght' 900,
      'SOFT' 100, 'WONK' 1, 'opsz' 90; line-height:.98; letter-spacing:-1px; }}
.corpo {{ font-size:38px; line-height:1.52; }}

.tag {{ display:inline-flex; align-items:center; gap:18px; }}
.tag b {{ background:{p['acento']}; color:{p['clarinho']}; border-radius:40px;
          padding:12px 30px; font-size:29px; letter-spacing:2.6px;
          font-weight:700; text-transform:uppercase; }}
.tag span {{ font-size:30px; opacity:.72; }}

.num {{ width:126px; height:126px; border-radius:50%; background:{p['acento']};
        color:{p['clarinho']}; font-family:'Disp',serif;
        font-variation-settings:'wght' 900,'SOFT' 100,'WONK' 1;
        font-size:74px; display:flex; align-items:center;
        justify-content:center; }}
.rotulo {{ font-size:30px; letter-spacing:3.4px; font-weight:700;
           color:{p['acento']}; text-transform:uppercase; }}

.pilula {{ display:inline-block; background:#DCEBD2; color:#2C5A2E;
           border-radius:40px; padding:20px 40px; font-size:32px;
           font-weight:700; }}
.pag {{ font-size:30px; font-weight:700; opacity:.42; letter-spacing:1px; }}
.rodape {{ margin-top:auto; display:flex; align-items:flex-end;
           justify-content:space-between; gap:28px; }}
.arroba {{ font-family:'Disp',serif;
           font-variation-settings:'wght' 800,'SOFT' 100,'WONK' 1;
           font-size:44px; }}
.foto {{ width:100%; border-radius:28px; object-fit:cover; }}
.preco {{ display:inline-block; background:{p['acento']}; color:{p['clarinho']};
          border-radius:40px; padding:16px 38px; font-size:46px;
          font-weight:700; margin-top:30px; }}
.lista {{ list-style:none; }}
.lista li {{ display:flex; gap:26px; align-items:flex-start; font-size:40px;
             line-height:1.34; margin-bottom:30px; }}
.cartao {{ border-radius:34px; padding:46px 44px; }}
.cartao li:last-child {{ margin-bottom:0; }}
.lista i {{ font-style:normal; font-family:'Disp',serif;
            font-variation-settings:'wght' 900,'SOFT' 100;
            color:{p['acento']}; min-width:46px; }}

/* ─── cabeçalho fixo: a âncora de identidade ────────────────────────────── */
.cabeca {{ display:flex; align-items:center; justify-content:space-between; }}
.marca {{ display:flex; align-items:center; gap:22px; }}
/* ⚠️ COMO O AVATAR DO INSTAGRAM: o PNG PREENCHE o círculo. Antes o `img` ia a
   70% com `contain`, e como a logo da conta já é um quadrado escuro com o TS
   dentro, o resultado era "um quadrado dentro de um círculo maior" — com um
   anel branco de fundo aparecendo em volta nos slides escuros. O Dre viu isso
   de primeira. Com `cover` a 100%, logo opaca preenche a moldura e o fundo
   nunca aparece; logo com transparência continua apoiada nele. */
.selo {{ width:96px; height:96px; border-radius:50%; border:3px solid;
         flex:0 0 96px; overflow:hidden; display:block; }}
.selo img {{ width:100%; height:100%; object-fit:cover; display:block; }}
.nome {{ font-family:'Disp',serif; font-variation-settings:'wght' 800,
         'SOFT' 100,'WONK' 1; font-size:46px; line-height:1; }}
.arr {{ font-size:27px; opacity:.66; margin-top:5px; }}
.cont {{ border:3px solid; border-radius:40px; padding:11px 30px;
         font-size:31px; font-weight:700; }}

/* ─── composições ───────────────────────────────────────────────────────── */
/* o número como ELEMENTO GRÁFICO, não como rótulo: sangra pela borda e é
   grande o bastante pra ser lido como forma antes de ser lido como número */
/* ⚠️ ELE MORA NO MEIO-ALTO, E ISSO É O PONTO. Na 1ª versão eu ancorei em
   `bottom:-96px`: o número saía cortado pela borda de baixo E por trás do
   parágrafo, virando mancha suja em vez de forma — e o miolo do slide ficava
   VAZIO, que é exatamente a crítica do Dre aos nossos slides ("metade de baixo
   vazia"). Ancorado abaixo do cabeçalho e sangrando pela direita, ele ocupa o
   vazio e o texto continua com a base livre. */
.gigante {{ position:absolute; font-family:'Disp',serif;
            font-variation-settings:'wght' 900,'SOFT' 100,'WONK' 1;
            font-size:540px; line-height:.72; right:-56px; top:186px;
            opacity:.16; pointer-events:none; letter-spacing:-18px; }}
.punch {{ font-family:'Disp',serif; font-variation-settings:'wght' 900,
          'SOFT' 100,'WONK' 1; line-height:1.02; letter-spacing:-2px; }}
/* ⚠️ O CONSERTO DO "PARECE QUE PEGOU DA SHOPEE". A foto de catálogo vem em
   fundo BRANCO. Recortada num card creme, o branco vaza e denuncia. Com
   `multiply` sobre superfície clara o branco vira a própria superfície e só o
   produto sobra — sem remover fundo, sem API, sem pagar nada. Por isso este
   slide é obrigatoriamente CLARO: em fundo escuro o multiply comeria o
   produto junto. */
.recorte {{ mix-blend-mode:multiply; filter:contrast(1.08) saturate(1.06);
            width:100%; object-fit:contain; }}
.metade {{ display:flex; gap:34px; align-items:stretch; }}
.metade > div {{ flex:1; display:flex; flex-direction:column;
                 justify-content:flex-end; }}
.versal {{ font-size:26px; letter-spacing:5px; text-transform:uppercase;
           font-weight:700; opacity:.6; }}
.caixa {{ border:3px solid {p['acento']}88; border-radius:26px;
          padding:26px 32px; display:flex; align-items:center; gap:24px;
          font-family:'Disp',serif; font-style:italic; font-size:34px;
          font-variation-settings:'wght' 600,'SOFT' 100; line-height:1.28; }}
"""


# ══════════════════════════════════════════════════════════════════════════
# OS TRÊS SLIDES
# ══════════════════════════════════════════════════════════════════════════
def _html_capa(plano: dict, total: int) -> str:
    import html as _h
    p = _paleta(plano.get("nicho", "geral"))
    capa = plano.get("capa") or {}
    hook = (capa.get("hook") or "").strip()
    sub = _h.escape((capa.get("sub") or "").strip())
    tag = _h.escape((plano.get("nicho") or "geral").upper())
    # a logo e o @ agora saem no `_cabecalho`, em TODOS os slides

    foto = _fundo(plano)
    camada = (f'<div class="fotocheia" style="background-image:url({foto})"></div>'
              f'<div class="fade" style="inset:0;background:linear-gradient('
              f'180deg,{p["escuro"]}e6 0%,{p["escuro"]}b3 42%,'
              f'{p["escuro"]}f2 100%)"></div>') if foto else ""

    return f"""<div class="slide" style="background:{p['escuro']};
     color:{p['clarinho']}">
  {camada}
  <div class="mancha" style="width:760px;height:760px;right:-260px;top:-230px;
       background:{p['acento']};opacity:{'.07' if foto else '.13'}"></div>
  {_cabecalho(plano, 1, total, True)}
  <h1 id="titulo" style="margin-top:auto;margin-bottom:38px;font-size:118px">
    {_marcar(hook, p['acento'])}</h1>
  <div class="rodape" style="margin-top:0">
    <div class="versal" style="color:{p['acento']};opacity:1;max-width:58%">
      {sub or tag}</div>
    <div class="pilula" style="background:rgba(255,255,255,.10);
         color:{p['clarinho']};font-size:30px;padding:18px 34px">
      arrasta &rarr;</div>
  </div>
</div>"""


# ══════════════════════════════════════════════════════════════════════════
# BIBLIOTECA DE COMPOSIÇÕES
#
# ⚠️ O PEDIDO DO DRE, LITERAL (23/08): *"os slides não podem parecer variações
# do mesmo template... identidade consistente + composição variável"*. E ele
# nomeou o erro exato que a gente estava cometendo:
#
#       título à esquerda + foto à direita
#       título à esquerda + foto à direita
#       título à esquerda + foto à direita...
#       "isso fica bonito, mas visualmente cansa rápido"
#
# Era exatamente o `_html_conteudo` antigo: UMA composição (tag em cima, h1,
# miolo, rodapé) com três variações de MIOLO. Trocar a foto por uma lista não
# muda a composição — muda o recheio. O olho lê a estrutura, não o recheio.
#
# ⚠️ E A REGRA QUE VALE MAIS QUE AS COMPOSIÇÕES: **nunca a mesma duas vezes
# seguidas**, e sempre que der, alternando claro/escuro. Ter 6 composições e
# sortear cada slide daria repetição colada em 1/6 dos pares — e repetição
# colada é justamente o que se vê. É o mesmo raciocínio do rodízio dos fundos e
# dos fechos: memória do anterior vale mais que quantidade de opções.
#
# O que NÃO dá pra fazer aqui, e é honesto registrar: o ChatGPT põe a foto
# CERTA pra cada tópico (abajur em "iluminação quente", cesto em "cestos"). O
# acervo é de ambiente genérico do nicho — casa a estética, não o assunto.
# ══════════════════════════════════════════════════════════════════════════
_RX_NUM = re.compile(r"(\d+)")


def _numero_do_item(ctx: dict) -> int:
    """O número QUE O TEXTO DIZ, não o índice do slide.

    ⚠️ TRÊS NUMERAÇÕES BRIGANDO NO MESMO SLIDE (23/08): a bola dizia "3" (índice
    do slide), o rótulo dizia "HÁBITO 2" (o item de verdade) e o contador dizia
    "4/8". O leitor não tem como saber qual seguir — e o `ordem` era só
    `i - 1`, que coincide com o item apenas quando o carrossel não tem slide de
    abertura extra. Quando o rótulo traz número, ele MANDA."""
    m = _RX_NUM.search(ctx.get("rotulo") or "")
    return int(m.group(1)) if m else ctx["ordem"]


def _numerado(ctx: dict) -> bool:
    """Este slide É um item numerado da narrativa?

    ⚠️ `numero_semantico != numero_slide`, e essa confusão sobreviveu ao 1º
    conserto. O slide de ABERTURA — "Muita gente faz 3 coisas que só atrapalham"
    — ganhou uma bola com "1", porque a bola vinha do índice do slide. Ele não é
    a dica 1; ele é a promessa das três. Um "1" ali contradiz o "3" da própria
    frase, na mesma linha de visão. **Só o rótulo diz se o slide é um item.**"""
    return bool(_RX_NUM.search(ctx.get("rotulo") or ""))


def _marca_de_ordem(ctx: dict, p: dict) -> str:
    """UMA marca de ordem por slide, nunca duas — e NENHUMA quando o slide não
    é um item numerado. O rótulo ganha da bola porque diz o que é ("ERRO Nº 2");
    a bola só diz um algarismo solto."""
    if ctx["rotulo"]:
        return f'<div class="rotulo">{ctx["rotulo"]}</div>'
    return ""


def _comp_cheia(item, i, total, plano, p, ctx) -> str:
    """Foto dominante, texto mínimo. ~80% imagem. O slide que dá impacto."""
    import html as _h
    foto = ctx["fundo"] or ctx["fotoitem"]
    rotulo = ctx["rotulo"]
    return f"""<div class="slide" style="background:{p['escuro']};
     color:{p['clarinho']}">
  {'<div class="fotocheia" style="background-image:url(' + foto + ');'
   'filter:saturate(1.14) contrast(1.1) brightness(.88)"></div>' if foto else ''}
  <!-- ⚠️ o véu é leve NO MEIO de propósito: esta composição existe pra a foto
       aparecer. Escurecer o quadro inteiro transforma "foto dominante" em
       "retângulo escuro com legenda" — e aí ela não se distingue da `numero`. -->
  <div class="fade" style="inset:0;background:linear-gradient(180deg,
       {p['escuro']}a6 0%,{p['escuro']}0d 26%,{p['escuro']}00 46%,
       {p['escuro']}bf 74%,{p['escuro']}f7 100%)"></div>
  {_cabecalho(plano, i, total, True)}
  <div style="margin-top:auto">
    {'<div class="versal" style="color:' + p['acento'] + ';opacity:1;'
     'margin-bottom:22px">' + rotulo + '</div>' if rotulo else ''}
    <h1 style="font-size:96px">{_marcar(ctx['titulo'], p['acento'])}</h1>
  </div>
</div>"""


def _comp_numero(item, i, total, plano, p, ctx) -> str:
    """O número vira forma. Sangra pela borda e o texto pousa por cima.

    ⚠️ É A ÚNICA QUE SERVE NOS DOIS TONS, e isso não é enfeite: sem ela, depois
    de um slide escuro só sobrava a `meio` (as outras claras exigem foto ou
    lista), e o carrossel virava escuro→meio→escuro→meio. Alternância perfeita
    é um padrão como qualquer outro — só demora um slide a mais pra cansar."""
    n = _numero_do_item(ctx)
    claro = ctx.get("claro", False)
    fundoS = p["clarinho"] if claro else p["escuro"]
    corS = "#1C1A18" if claro else p["clarinho"]
    # ⚠️ A VERSÃO CLARA TAMBÉM LEVA FOTO, em faixa no alto. Sem isso ela era
    # texto sobre creme, e o carrossel de 23/08 saiu com 4 de 6 slides sem
    # imagem nenhuma — "só uma paleta laranja, outra branca", nas palavras do
    # Dre. Com 10 fundos no acervo, slide sem foto passa a ser escolha e não
    # consequência.
    faixa = ('<div class="fototopo" style="height:520px;background-image:url('
             + ctx['fundo'] + ')"></div><div class="fade" style="top:0;'
             'height:520px;background:linear-gradient(180deg,rgba(0,0,0,.44) 0%,'
             + p['clarinho'] + '00 44%,' + p['clarinho'] + 'e6 80%,'
             + p['clarinho'] + ' 100%)"></div>') if (claro and ctx['fundo']) else ''
    return f"""<div class="slide" style="background:{fundoS};color:{corS}">
  {'<div class="fotocheia" style="background-image:url(' + ctx['fundo'] + ');'
   'filter:saturate(1.05) contrast(1.05) brightness(.40)"></div>'
   if ctx['fundo'] and not claro else ''}
  {faixa}
  <div class="gigante" style="color:{p['acento']};
       opacity:{'.16' if claro else '.20'};
       {'top:430px' if faixa else ''}">{n:02d}</div>
  {_cabecalho(plano, i, total, (not claro) or bool(faixa))}
  <div style="margin-top:auto;max-width:86%">
    <h1 style="font-size:104px">{_marcar(ctx['titulo'], p['acento'])}</h1>
    {'<p class="corpo" style="margin-top:32px;opacity:.78">' + ctx['corpo']
     + '</p>' if ctx['corpo'] else ''}
  </div>
</div>"""


def _comp_respiro(item, i, total, plano, p, ctx) -> str:
    """A punchline. Cor chapada, uma frase, e nada mais.

    ⚠️ É O SLIDE QUE 'ACORDA O OLHO' — o Dre: *"depois de dois slides escuros,
    um slide claro"*. Ele não carrega informação nova; carrega RITMO. Por isso
    não leva foto: se levasse, seria mais um slide bonito no meio de slides
    bonitos, e o contraste morreria."""
    return f"""<div class="slide" style="background:{p['acento']};
     color:{p['clarinho']}">
  <div class="mancha" style="width:900px;height:900px;left:-320px;
       bottom:-340px;background:{p['clarinho']};opacity:.09"></div>
  {_cabecalho(plano, i, total, True, sobre_acento=True)}
  <div style="margin:auto 0;max-width:92%">
    {'<div class="versal" style="margin-bottom:28px">' + ctx['rotulo']
     + '</div>' if ctx['rotulo'] else ''}
    <div class="punch" style="font-size:118px">
      {_marcar(ctx['titulo'], p['clarinho'])}</div>
    {'<p class="corpo" style="margin-top:38px;opacity:.86">' + ctx['corpo']
     + '</p>' if ctx['corpo'] else ''}
  </div>
</div>"""


def _comp_produto(item, i, total, plano, p, ctx) -> str:
    """Objeto isolado em superfície clara. O `multiply` some com o fundo
    branco do catálogo da Shopee — ver `.recorte` no CSS."""
    return f"""<div class="slide" style="background:{p['clarinho']};
     color:#1C1A18">
  <div class="mancha" style="width:820px;height:820px;right:-250px;top:-280px;
       background:{p['sombra']}"></div>
  {_cabecalho(plano, i, total, False)}
  <div style="margin-top:44px">
    <h1 style="font-size:76px">{_marcar(ctx['titulo'], p['acento'])}</h1>
  </div>
  <div style="margin:auto 0;display:flex;justify-content:center">
    {'<img class="recorte" src="' + ctx['fotoitem'] + '" style="max-height:600px">'
     if ctx['fotoitem'] else ''}
  </div>
  <div class="rodape">
    {'<div class="preco">' + ctx['preco'] + '</div>' if ctx['preco'] else '<div></div>'}
    {'<div class="caixa" style="max-width:47%">' + ctx['conclusao'] + '</div>'
     if ctx['conclusao'] else '<div></div>'}
  </div>
</div>"""


def _comp_meio(item, i, total, plano, p, ctx) -> str:
    """Foto sangrando na metade de cima, texto em cor chapada embaixo.

    A composição antiga — mantida porque É BOA. O defeito nunca foi ela; foi
    ela ser a ÚNICA."""
    return f"""<div class="slide" style="background:{p['creme']};color:#1C1A18">
  <!-- ⚠️ 62% DA ALTURA, NÃO 47%. Com a faixa em 640px sobrava uma área creme
       maior que a foto e o slide lia como "cortado no meio" — e ficava mais
       fraco que os slides escuros do mesmo carrossel, como se tivesse faltado
       imagem. A quebra clara é boa; a PROPORÇÃO é que estava errada. -->
  {'<div class="fototopo" style="height:840px;background-image:url('
   + ctx['fundo'] + ')"></div><div class="fade" style="top:0;height:840px;'
   'background:linear-gradient(180deg,rgba(0,0,0,.44) 0%,rgba(0,0,0,.06) 20%,'
   + p['creme'] + '00 52%,' + p['creme'] + 'e0 84%,' + p['creme']
   + ' 100%)"></div>' if ctx['fundo'] else ''}
  {_cabecalho(plano, i, total, bool(ctx['fundo']))}
  <div style="margin-top:auto">
    <div class="tag" style="gap:26px;margin-bottom:30px">
      {_marca_de_ordem(ctx, p)}
    </div>
    <h1 style="font-size:82px">{_marcar(ctx['titulo'], p['acento'])}</h1>
    {'<p class="corpo" style="margin-top:30px;opacity:.76">' + ctx['corpo']
     + '</p>' if ctx['corpo'] else ''}
  </div>
</div>"""


def _comp_checklist(item, i, total, plano, p, ctx) -> str:
    """Blocos curtos. É o slide feito pra ser SALVO."""
    itens = ctx["itens"]
    import html as _h
    linhas = "".join(
        f'<li><i>✓</i><span>{_h.escape(_limpo(t))}</span></li>'
        for t in itens[:7])
    # ⚠️ ELE ERA CREME VAZIO, E VINHA COLADO NO FECHO, QUE TAMBÉM É CLARO. O
    # carrossel terminava foto → creme vazio → creme vazio: justo o clímax
    # perdendo energia. Agora ele é foto cheia com véu e a lista num cartão —
    # continua sendo o slide de salvar, mas parece parte do mesmo carrossel.
    foto = ctx["fundo"] or _fundo(plano)
    escuro = bool(foto)
    return f"""<div class="slide" style="background:{p['escuro'] if escuro
     else p['clarinho']};color:{p['clarinho'] if escuro else '#1C1A18'}">
  {'<div class="fotocheia" style="background-image:url(' + foto + ');'
   'filter:saturate(1.05) contrast(1.04) brightness(.46)"></div>'
   '<div class="fade" style="inset:0;background:linear-gradient(180deg,'
   + p['escuro'] + 'b3 0%,' + p['escuro'] + '59 40%,' + p['escuro']
   + 'd9 100%)"></div>' if escuro else
   '<div class="mancha" style="width:700px;height:700px;right:-230px;'
   'bottom:-260px;background:' + p['sombra'] + '"></div>'}
  {_cabecalho(plano, i, total, escuro)}
  <div style="margin-top:52px">
    <h1 style="font-size:78px">{_marcar(ctx['titulo'], p['acento'])}</h1>
  </div>
  <ul class="lista cartao" style="margin-top:auto;margin-bottom:auto;
      {'background:rgba(0,0,0,.42);border:2px solid rgba(255,255,255,.16)'
       if escuro else ''}">{linhas}</ul>
</div>"""


# tom: pra alternar claro/escuro. quer: o que o slide precisa ter pra caber.
COMPOSICOES = {
    "cheia":     {"fn": _comp_cheia,     "tom": "escuro", "quer": "titulo"},
    "numero":    {"fn": _comp_numero,    "tom": "ambos",  "quer": "titulo"},
    "respiro":   {"fn": _comp_respiro,   "tom": "escuro", "quer": "curto"},
    "produto":   {"fn": _comp_produto,   "tom": "claro",  "quer": "foto"},
    "meio":      {"fn": _comp_meio,      "tom": "claro",  "quer": "titulo"},
    # "ambos" porque ele fica ESCURO quando há foto e claro quando não há —
    # e o tom precisa ser verdade, senão a alternância decide com base numa
    # informação errada e o log imprime um "c" onde saiu um slide escuro.
    "checklist": {"fn": _comp_checklist, "tom": "ambos",  "quer": "itens"},
}


# composições que nunca mostram foto (a `numero` escura mostra; a clara ganhou
# faixa; o `checklist` só fica sem quando o acervo do nicho está vazio)
_SEM_FOTO = {"respiro"}


def _elegiveis(ctx: dict) -> list:
    """As composições que o conteúdo DESTE slide comporta."""
    if ctx["itens"]:
        return ["checklist"]
    if ctx["fotoitem"]:
        return ["produto"]
    fora = []
    for nome, c in COMPOSICOES.items():
        if c["quer"] in ("foto", "itens"):
            continue
        # `respiro` só aceita frase curta: uma punchline de 14 palavras não é
        # punchline, é parágrafo em corpo 118px, e vaza o slide.
        if c["quer"] == "curto" and len(ctx["titulo"].split()) > 7:
            continue
        # `cheia` sem foto é retângulo escuro com texto — pior que `meio`.
        if nome == "cheia" and not (ctx["fundo"] or ctx["fotoitem"]):
            continue
        # a `numero` só serve pra slide que É um item numerado — ver `_numerado`
        if nome == "numero" and not _numerado(ctx):
            continue
        fora.append(nome)
    return fora or ["meio"]


def _escolher_comp(ctx: dict, recentes: list, tom_ant: str = "") -> tuple:
    """Nunca a mesma da anterior; quando dá, o tom oposto.

    Devolve (nome, tom). O tom sai daqui e não de dentro da composição porque a
    `numero` serve nos dois — e quem sabe qual falta é quem viu o slide de trás.

    ⚠️ A ALTERNÂNCIA É PREFERÊNCIA, NÃO LEI. Na 1ª versão eu filtrava pelo tom
    oposto e pronto: como só a `meio` é clara entre as de texto, TODO slide
    depois de um escuro virava `meio`, sempre. Sai um padrão e entra outro. Se
    o tom oposto deixa uma opção só, ela leva vantagem — não exclusividade.

    ⚠️⚠️ E "NÃO REPETIR A ANTERIOR" NÃO BASTA — foi o que o carrossel de 23/08
    provou, saindo assim:

        meio → respiro → meio → respiro → numero → checklist

    Nenhuma composição repetida em sequência, e mesmo assim **A→B→A→B**, que é
    um padrão tão legível quanto A→A→A. O Dre já tinha avisado ("visualmente
    cansa rápido") e eu implementei uma regra que só olhava UM slide pra trás.
    Agora a janela é dos DOIS últimos: alternar exige três composições, e três
    alternando já não parece fórmula."""
    op = _elegiveis(ctx)
    janela = [c for c in recentes[-2:] if c]
    livres = [o for o in op if o not in janela]
    if livres:
        op = livres
    elif len(op) > 1 and janela:            # a janela apagou tudo: cede o
        op = [o for o in op if o != janela[-1]] or op   # último, não os dois

    # ⚠️ NUNCA DOIS SLIDES SEM FOTO SEGUIDOS. A `respiro` é chapada por
    # definição e o `checklist` sem acervo também; colados, o carrossel abre um
    # buraco visual no meio de uma sequência fotográfica e parece que faltou
    # imagem. Vale só quando há foto disponível — sem acervo isto não inventa
    # nada, só não tem o que preferir.
    if recentes and recentes[-1] in _SEM_FOTO and (ctx["fundo"]
                                                   or ctx["fotoitem"]):
        com = [o for o in op if o not in _SEM_FOTO]
        if com:
            op = com

    if tom_ant:
        oposto = "claro" if tom_ant == "escuro" else "escuro"
        opostas = [o for o in op
                   if COMPOSICOES[o]["tom"] in (oposto, "ambos")]
        if len(opostas) >= 2 or (opostas and random.random() < .70):
            op = opostas
    nome = op[0] if len(op) == 1 else random.choice(op)

    tom = COMPOSICOES[nome]["tom"]
    if nome == "checklist":
        tom = "escuro" if ctx.get("tem_foto") else "claro"
    elif tom == "ambos":
        tom = ("claro" if tom_ant == "escuro" else "escuro") if tom_ant \
            else random.choice(["claro", "escuro"])
    ctx["claro"] = (tom == "claro")
    return nome, tom


def _html_conteudo(item: dict, i: int, total: int, plano: dict,
                   recentes: list = None, tom_ant: str = "") -> tuple:
    import html as _h
    p = _paleta(plano.get("nicho", "geral"))
    ctx = {
        "rotulo": _h.escape((item.get("rotulo") or "").strip().upper()),
        "titulo": (item.get("titulo") or "").strip(),
        "corpo": _h.escape((item.get("linha") or "").strip()),
        "preco": _h.escape((item.get("preco") or "").strip()),
        "conclusao": _h.escape((item.get("conclusao") or "").strip()),
        "ordem": max(1, i - 1),
        "itens": [str(x) for x in (item.get("itens") or []) if str(x).strip()],
        "fotoitem": (_b64(item["foto"]) if item.get("foto")
                     and Path(item["foto"]).exists() else ""),
        "fundo": _fundo(plano, item) if item.get("fundo") else "",
    }
    # o `checklist` cai no acervo do nicho mesmo sem `fundo` no item, então
    # "tem foto" aqui é mais amplo que `ctx["fundo"]`
    ctx["tem_foto"] = bool(ctx["fundo"] or ctx["fotoitem"] or _fundo(plano))
    nome, tom = _escolher_comp(ctx, recentes or [], tom_ant)
    return COMPOSICOES[nome]["fn"](item, i, total, plano, p, ctx), nome, tom


def _html_conteudo_legado(item: dict, i: int, total: int, plano: dict) -> str:
    import html as _h
    p = _paleta(plano.get("nicho", "geral"))
    rotulo = _h.escape((item.get("rotulo") or "").strip().upper())
    titulo = (item.get("titulo") or "").strip()
    corpo = _h.escape((item.get("linha") or "").strip())
    preco = _h.escape((item.get("preco") or "").strip())
    foto = _b64(item["foto"]) if item.get("foto") and Path(item["foto"]).exists() else ""
    itens = [str(x) for x in (item.get("itens") or []) if str(x).strip()]

    if itens:      # slide de RESUMO
        miolo = ('<ul class="lista" style="margin-top:54px">'
                 + "".join(f'<li><i>{k}</i><span>{_h.escape(_limpo(t))}</span></li>'
                           for k, t in enumerate(itens[:7], 1))
                 + "</ul>")
        tam = 78
    elif foto:     # slide de PRODUTO
        miolo = (f'<img class="foto" src="{foto}" style="height:520px;'
                 f'margin-top:44px">'
                 + (f'<div class="preco">{preco}</div>' if preco else ""))
        tam = 74
    else:          # slide de TEXTO
        miolo = (f'<p class="corpo" style="margin-top:44px;opacity:.74">{corpo}</p>'
                 if corpo else "")
        tam = 92

    # ⚠️ A FOTO PARA EM 46% E VIRA CREME. Aqui embaixo mora o parágrafo, e
    # parágrafo sobre foto se lê mal por melhor que seja o véu — é a mesma
    # divisão que as referências do Claude Design fazem: imagem onde tem 5
    # palavras, cor chapada onde tem texto corrido.
    fundo = _fundo(plano, item) if item.get("fundo") else ""
    topo = (f'<div class="fototopo" style="height:620px;'
            f'background-image:url({fundo})"></div>'
            f'<div class="fade" style="top:0;height:620px;'
            f'background:linear-gradient(180deg,rgba(0,0,0,.18) 0%,'
            f'{p["creme"]}00 30%,{p["creme"]}e6 76%,{p["creme"]} 100%)"></div>'
            ) if fundo else ""

    return f"""<div class="slide" style="background:{p['creme']};color:#1C1A18">
  {topo}
  <div class="mancha" style="width:660px;height:660px;right:-190px;top:-220px;
       background:{p['sombra']};opacity:{'.45' if fundo else '1'}"></div>
  <div class="tag" style="gap:26px">
    <div class="num">{i - 1}</div>
    {'<div class="rotulo">' + rotulo + '</div>' if rotulo else ''}
  </div>
  <h1 id="titulo" style="margin-top:52px;font-size:{tam}px">
    {_marcar(titulo, p['acento'])}</h1>
  {miolo}
  <div class="rodape">
    {'<div class="pilula">' + _h.escape(item.get('conclusao', '')) + '</div>'
     if item.get('conclusao') else '<div></div>'}
    <div class="pag">{i:02d} / {total:02d}</div>
  </div>
</div>"""


# ══════════════════════════════════════════════════════════════════════════
# O FECHO — CINCO MODELOS, EM RODÍZIO
#
# ⚠️ O Dre: *"o CTA no final do slide tá muito simples"*, e mandou 5 carrosséis
# reais. Lendo os cinco, o padrão não é "um CTA bonito" — é que **cada um pede
# UMA coisa, de um jeito**, e o jeito muda:
#
#   thaleslaray        "Comenta BASTIDORES que eu te mando o link"  → palavra
#                      -chave em destaque, dentro de caixa com borda
#   carlamarquete      "se esse post te ajudou, aproveita e me segue"
#   mariffernandes     "se você gosta de X: você encontrou o perfil certo"
#   detalhesdaminhacasa "Comenta AULA aqui embaixo ↓"
#   bettydiarista      **mockup do card de perfil** + "segue ou você nunca
#                      mais verá essa página"
#
# ⚠️ E ELE PEDIU O QUE FALTAVA: *"da pra diferenciar todo dia o CTA"*. Um fecho
# fixo é o mesmo problema do 1º comentário que a gente acabou de consertar —
# quem segue duas contas nossas vê a mesma peça duas vezes por dia. Então são
# cinco modelos em RODÍZIO COM MEMÓRIA, não sorteio: com 5 peças, o sorteio
# puro repete a anterior 1 vez em 5.
#
# ⚠️ O MOCKUP DE PERFIL NÃO INVENTA NÚMERO. O do bettydiarista mostra
# "100k seguidores". Se a gente estampar um número, ou ele é o real (que hoje
# é 9 em duas contas, e aí o CTA trabalha contra a gente) ou é mentira impressa
# na peça. Então o card mostra avatar, @ e o botão — que é o que faz o pedido.
# ══════════════════════════════════════════════════════════════════════════
FECHO_MEMORIA = BASE_DIR / "shared" / "fechos_recentes.json"


def _palavra_chave(plano: dict) -> str:
    """A palavra que o post pede no comentário. Sai do plano ou do formato."""
    cta = plano.get("cta") or {}
    p = (cta.get("palavra") or "").strip().upper()
    if p:
        return p[:14]
    return {"lista": "QUERO", "comparacao": "QUAL",
            "erros": "EU FAÇO", "passo_a_passo": "PASSO",
            "antes_depois": "ANTES", "historia": "CONTA",
            }.get(plano.get("formato", ""), "QUERO")


# ⚠️ CADA MODELO ESCREVE O PRÓPRIO TÍTULO — o `cta.titulo` do plano só vale no
# modelo `salva`. Deixando o plano mandar em todos, o fecho de PERFIL saía com
# o botão azul "Seguir" e o texto "Salva pra não perder" logo abaixo: a peça
# pedindo uma coisa e a frase pedindo outra. Título e pedido são a mesma
# decisão, então moram juntos.
def _fecho_comente(plano, p, cta, handle, total):
    """thaleslaray/detalhesdaminhacasa: pede COMENTÁRIO com palavra-chave."""
    import html as _h
    chave = _palavra_chave(plano)
    linhas = _h.escape(" ".join(str(x) for x in (cta.get("linhas") or []))[:120])
    return f"""<div class="slide" style="background:{p['creme']};color:#1C1A18">
  <div class="mancha" style="width:700px;height:700px;left:-240px;
       bottom:-260px;background:{p['sombra']}"></div>
  <h1 id="titulo" style="margin-top:auto;font-size:92px">Quer o link
    desses achadinhos?</h1>
  <div style="margin-top:52px;border:5px solid {p['acento']};border-radius:34px;
       padding:44px 46px;font-size:52px;line-height:1.3;font-weight:600">
    Comenta <b style="color:{p['acento']}">{_h.escape(chave)}</b>
    <span style="display:block;margin-top:10px">que eu te mando o link</span>
  </div>
  <div style="font-size:74px;margin-top:26px;color:{p['acento']}">&darr;</div>
  <div class="rodape"><div class="arroba">{handle}</div>
    <div class="pag">{total:02d} / {total:02d}</div></div>
</div>"""


def _fecho_perfil(plano, p, cta, handle, total):
    """bettydiarista: o card de perfil mockado. O pedido mais direto de SEGUIR
    que existe — a pessoa vê o botão e entende o que fazer sem ler."""
    import html as _h
    logo = _logo(plano.get("nicho", "geral"))
    return f"""<div class="slide" style="background:{p['escuro']};
     color:{p['clarinho']}">
  <div class="mancha" style="width:760px;height:760px;right:-250px;top:-240px;
       background:{p['acento']};opacity:.16"></div>
  <div style="margin-top:auto;background:{p['clarinho']};color:#14120F;
       border-radius:34px;padding:46px 44px">
    <div style="display:flex;align-items:center;gap:26px">
      {'<img src="' + logo + '" style="width:118px;height:118px;border-radius:50%">'
       if logo else '<div style="width:118px;height:118px;border-radius:50%;'
                    'background:' + p['acento'] + '"></div>'}
      <div>
        <div style="font-size:44px;font-weight:700">{handle}</div>
        <div style="font-size:32px;opacity:.6;margin-top:6px">
          achadinhos todo dia</div>
      </div>
    </div>
    <div style="margin-top:34px;background:#1877F2;color:#fff;border-radius:16px;
         padding:24px;text-align:center;font-size:40px;font-weight:700">
      Seguir</div>
  </div>
  <h1 id="titulo" style="margin-top:44px;font-size:78px">Segue pra não
    perder o próximo</h1>
  <div class="rodape"><div></div>
    <div class="pag" style="opacity:.6">{total:02d} / {total:02d}</div></div>
</div>"""


def _fecho_ajudou(plano, p, cta, handle, total):
    """carlamarquete: texto gigante, sem enfeite. Funciona porque é direto."""
    import html as _h
    return f"""<div class="slide" style="background:{p['acento']};
     color:{p['clarinho']};justify-content:center">
  <div class="mancha" style="width:900px;height:900px;left:-320px;top:-260px;
       background:rgba(255,255,255,.08)"></div>
  <h1 id="titulo" style="font-size:118px">se esse post te ajudou,
    <span style="opacity:.75">aproveita e me segue</span></h1>
  <div class="rodape"><div class="arroba">{handle}</div>
    <div class="pag" style="opacity:.6">{total:02d} / {total:02d}</div></div>
</div>"""


def _fecho_perfil_certo(plano, p, cta, handle, total):
    """mariffernandesdaily: fala com quem gosta DO TEMA, não com todo mundo."""
    import html as _h
    tema = {"casa": "casa organizada e achadinhos",
            "tech": "tecnologia e achadinhos",
            "beleza": "beleza e autocuidado",
            "pet": "pets e achadinhos",
            "moda": "moda e look do dia",
            }.get(plano.get("nicho", ""), "achadinhos que valem a pena")
    return f"""<div class="slide" style="background:{p['creme']};color:#1C1A18;
     justify-content:center">
  <div class="mancha" style="width:820px;height:820px;right:-280px;
       bottom:-300px;background:{p['sombra']}"></div>
  <p class="corpo" style="font-size:44px;opacity:.72">
    se você gosta de conteúdo sobre</p>
  <h1 id="titulo" style="font-size:96px;margin-top:18px">{_h.escape(tema)}</h1>
  <p class="corpo" style="font-size:48px;margin-top:40px;
     color:{p['acento']};font-weight:700">você achou o perfil certo</p>
  <div class="rodape"><div class="arroba">{handle}</div>
    <div class="pag">{total:02d} / {total:02d}</div></div>
</div>"""


def _fecho_salva(plano, p, cta, handle, total):
    """O clássico. Fica na roda porque salvamento é o sinal que a gente mede."""
    import html as _h
    linhas = _h.escape(" ".join(str(x) for x in (cta.get("linhas") or [])))
    # ⚠️ `mix-blend-mode:multiply` NA COR DA CONTA, não um véu preto: o véu
    # apaga a foto e sobra cinza; o multiply TINGE a foto na cor da marca e ela
    # continua se lendo como foto. É o que faz o fecho parecer da mesma família
    # que a capa sem ser a mesma imagem.
    foto = _fundo(plano)
    camada = (f'<div class="fotocheia" style="background-image:url({foto});'
              f'filter:saturate(.4) contrast(1.1) brightness(.9)"></div>'
              f'<div class="fade" style="inset:0;background:{p["acento"]};'
              f'mix-blend-mode:multiply"></div>'
              f'<div class="fade" style="inset:0;background:linear-gradient('
              f'180deg,{p["acento"]}66 0%,{p["acento"]}d9 100%)"></div>'
              ) if foto else ""

    return f"""<div class="slide" style="background:{p['acento']};
     color:{p['clarinho']}">
  {camada}
  <div class="mancha" style="width:820px;height:820px;right:-210px;
       bottom:-300px;background:rgba(255,255,255,.10)"></div>
  <div class="rotulo" style="color:{p['clarinho']};opacity:.8">
    {_h.escape((plano.get('nicho') or '').upper())}</div>
  <h1 id="titulo" style="margin-top:auto;font-size:106px">
    {_h.escape(_limpo(cta.get('titulo') or 'Salva pra não perder'))}</h1>
  <p class="corpo" style="margin-top:38px;opacity:.9">{linhas}</p>
  <div class="rodape"><div class="arroba">{handle}</div>
    <div class="pag" style="opacity:.62">{total:02d} / {total:02d}</div></div>
</div>"""


MODELOS_FECHO = {
    "comente": _fecho_comente, "perfil": _fecho_perfil,
    "ajudou": _fecho_ajudou, "perfil_certo": _fecho_perfil_certo,
    "salva": _fecho_salva,
}


def _escolher_fecho(conta: str) -> str:
    """Rodízio com memória — nunca o mesmo da vez anterior naquela conta."""
    import random
    forcado = os.environ.get("CARR_FECHO", "").strip()
    if forcado in MODELOS_FECHO:
        return forcado
    try:
        mem = json.loads(FECHO_MEMORIA.read_text(encoding="utf-8"))
    except Exception:
        mem = {}
    recentes = mem.get(conta or "?", [])
    novos = [m for m in MODELOS_FECHO if m not in recentes]
    escolha = random.choice(novos or list(MODELOS_FECHO))
    try:
        mem[conta or "?"] = ([escolha] + recentes)[:3]
        FECHO_MEMORIA.parent.mkdir(parents=True, exist_ok=True)
        FECHO_MEMORIA.write_text(json.dumps(mem, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    except Exception:
        pass          # memória é conforto: nunca trava um post
    return escolha


def _html_fecho(plano: dict, total: int) -> str:
    import html as _h
    p = _paleta(plano.get("nicho", "geral"))
    cta = plano.get("cta") or {}
    handle = _h.escape(plano.get("handle") or "")
    modelo = _escolher_fecho(plano.get("handle", ""))
    log.info(f"   🎬 fecho '{modelo}'")
    return MODELOS_FECHO[modelo](plano, p, cta, handle, total)


# ⚠️ O AJUSTE DE TAMANHO RODA NO NAVEGADOR, e é a única coisa que o JS faz.
# Quem MEDE se o texto cabe tem que ser quem DESENHA — no PIL isso era uma
# conta aproximada de largura de caractere, e ela errava justamente nos
# títulos longos, que são os que precisam caber.
_JS = """<script>
(function () {
  var h = document.getElementById('titulo');
  if (!h) return;
  var caixa = h.parentElement.clientHeight * 0.56;
  var t = parseInt(getComputedStyle(h).fontSize, 10);
  while (t > 46 && h.offsetHeight > caixa) { t -= 3; h.style.fontSize = t + 'px'; }
})();
</script>"""


def _pagina(corpo: str, plano: dict) -> str:
    p = _paleta(plano.get("nicho", "geral"))
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>"
            f"{_css(p, _primeira(_TITULO), _primeira(_CORPO))}</style></head>"
            f"<body>{corpo}{_JS}</body></html>")


# ══════════════════════════════════════════════════════════════════════════
# RENDER
# ══════════════════════════════════════════════════════════════════════════
def _chromium() -> str:
    """⚠️ O Playwright acha o navegador pela versão DELE; quando a lib e os
    binários não batem, o erro é `Executable doesn't exist at .../-1` com o
    `-1194` na mesma pasta. Não é navegador faltando, é número que não bate."""
    env = os.environ.get("PW_CHROMIUM", "").strip()
    if env and Path(env).exists():
        return env
    base = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"))
    if not base.exists():
        return ""
    for padrao in ("chromium-*/chrome-linux/chrome",
                   "chromium_headless_shell-*/chrome-linux/headless_shell"):
        achados = sorted(base.glob(padrao))
        if achados:
            return str(achados[-1])
    return ""


def renderizar_slides(plano: dict, pasta) -> list:
    """Desenha o carrossel inteiro. Devolve os JPEGs na ordem, ou [] se não deu.

    Devolver [] em vez de levantar é de propósito: quem chama cai no desenho
    em PIL e o post sai do mesmo jeito. Nenhuma publicação pode depender de o
    navegador estar bem."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    itens = plano.get("slides") or []
    total = len(itens) + 2

    # ⚠️ ESTE `try` É O QUE FALTAVA. A montagem do HTML ficava FORA de qualquer
    # captura: um erro aqui subia direto pro `carrossel_render`, que cai no PIL
    # sem dizer por quê. Resultado prático de um `fundo: true` num campo que
    # espera caminho: o post sai feio, sai publicado, e o log não menciona
    # erro nenhum. Agora o motivo aparece antes de a gente perder a tarde.
    try:
        paginas = [_html_capa(plano, total)]
        # O `anterior` é o estado que faz a regra funcionar. Sem ele cada slide
        # decidiria sozinho e duas composições iguais coladas voltariam a
        # acontecer — o defeito que esta biblioteca existe pra resolver.
        recentes, tom_ant, usadas = [], "escuro", []  # a capa é sempre escura
        for k, item in enumerate(itens, start=2):
            corpo, nome, tom_ant = _html_conteudo(item, k, total, plano,
                                                  recentes, tom_ant)
            paginas.append(corpo)
            recentes.append(nome)
            usadas.append(f"{nome}({tom_ant[0]})")
        paginas.append(_html_fecho(plano, total))
    except Exception as e:
        log.warning(f"   ⚠️  não montei o HTML ({type(e).__name__}: "
                    f"{str(e)[:120]}) — caindo no PIL")
        return []
    if usadas:
        log.info(f"   🧩 composições: {' → '.join(usadas)}")

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        log.warning(f"   ⚠️  playwright ausente ({str(e)[:60]}) — caindo no PIL")
        return []

    arquivos = []
    try:
        with sync_playwright() as pw:
            nav = pw.chromium.launch(args=["--no-sandbox",
                                           "--disable-dev-shm-usage"],
                                     executable_path=_chromium() or None)
            pag = nav.new_page(viewport={"width": LARG, "height": ALT},
                               device_scale_factor=ESCALA)
            for k, corpo in enumerate(paginas, start=1):
                pag.set_content(_pagina(corpo, plano), wait_until="load")
                pag.wait_for_timeout(160)
                png = pag.screenshot(type="png")
                arq = pasta / f"{k:02d}.jpg"
                _gravar_jpeg(png, arq)
                arquivos.append(arq)
            nav.close()
    except Exception as e:
        log.warning(f"   ⚠️  Chromium falhou ({str(e)[:100]}) — caindo no PIL")
        return []

    if plano.get("legenda"):
        (pasta / "legenda.txt").write_text(plano["legenda"], encoding="utf-8")
    log.info(f"   🎨 {len(arquivos)} slide(s) pelo navegador em {pasta}")
    return arquivos


def _gravar_jpeg(png: bytes, destino: Path) -> None:
    """⚠️ JPEG sempre — "JPEG is the only image format supported" na Meta."""
    import io
    from PIL import Image
    img = Image.open(io.BytesIO(png)).convert("RGB")
    if img.size != (LARG, ALT):
        img = img.resize((LARG, ALT), Image.LANCZOS)
    img.save(destino, "JPEG", quality=92, optimize=True)


_EXEMPLO = {
    "nicho": "casa", "handle": "@topshopcasa_",
    "capa": {"hook": "Você está cometendo esse erro *sem perceber*",
             "sub": "3 erros que bagunçam a casa"},
    # ⚠️ `fundo: True` em todos os de texto porque é ASSIM QUE O BRAIN MANDA.
    # Sem isso o exemplo nunca exercitava a composição `cheia` (ela exige foto),
    # e um exemplo que não passa por todos os caminhos é um teste que aprova o
    # que não testou.
    "slides": [
        {"rotulo": "ERRO Nº 1", "titulo": "Guardar tudo o que sobrou",
         "fundo": True,
         "linha": "Pote sem tampa, sacola de sacola e caixa vazia ocupam a "
                  "prateleira que faria falta pro que você usa toda semana.",
         "conclusao": "Descarta antes de organizar"},
        {"rotulo": "ERRO Nº 2", "titulo": "Organizar sem lugar fixo",
         "fundo": True,
         "linha": "Se cada coisa volta pra um lugar diferente, a bagunça "
                  "reaparece em três dias. Lugar fixo é o que sustenta.",
         "conclusao": "Um lugar pra cada coisa"},
        {"rotulo": "ERRO Nº 3", "titulo": "Deixar tudo à vista",
         "fundo": True,
         "linha": "Superfície cheia cansa o olho antes de a casa estar suja.",
         "conclusao": "Superfície livre"},
        {"rotulo": "", "titulo": "", "itens": [
            "Descartar o que não usa", "Lugar fixo pra cada coisa",
            "Limpar por zona, não por cômodo"]},
    ],
    "cta": {"titulo": "Salva pra não perder",
            "linhas": ["Volta nesse post no dia da faxina."]},
}


def main() -> int:
    p = argparse.ArgumentParser(description="Slides do carrossel em HTML/CSS")
    p.add_argument("--exemplo", metavar="NICHO")
    p.add_argument("--plano", metavar="JSON")
    p.add_argument("--saida", default="/tmp/slides")
    a = p.parse_args()

    if a.plano:
        plano = json.loads(Path(a.plano).read_text(encoding="utf-8"))
    elif a.exemplo:
        plano = dict(_EXEMPLO, nicho=a.exemplo,
                     handle=f"@topshop{a.exemplo}_")
    else:
        p.print_help()
        return 1

    arqs = renderizar_slides(plano, a.saida)
    if not arqs:
        return 1
    print("\n".join(str(x) for x in arqs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
