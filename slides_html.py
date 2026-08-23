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
    for cand in ((item or {}).get("fundo"), (item or {}).get("foto"),
                 (plano.get("capa") or {}).get("fundo")):
        if cand and Path(cand).exists():
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
.slide > *:not(.mancha):not(.fototopo):not(.fotocheia):not(.fade)
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
.lista i {{ font-style:normal; font-family:'Disp',serif;
            font-variation-settings:'wght' 900,'SOFT' 100;
            color:{p['acento']}; min-width:46px; }}
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
    handle = _h.escape(plano.get("handle") or "")
    tag = _h.escape((plano.get("nicho") or "geral").upper())
    logo = _logo(plano.get("nicho", "geral"))

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
  <div class="tag"><b>{tag}</b><span>{sub}</span></div>
  <h1 id="titulo" style="margin-top:auto;margin-bottom:44px;font-size:118px">
    {_marcar(hook, p['acento'])}</h1>
  <div class="rodape" style="margin-top:0">
    <div style="display:flex;align-items:center;gap:22px">
      {'<img src="' + logo + '" style="width:78px;height:78px;border-radius:50%">' if logo else ''}
      <div class="arroba">{handle}</div>
    </div>
    <div class="pilula" style="background:rgba(255,255,255,.10);
         color:{p['clarinho']};font-size:30px;padding:18px 34px">
      arrasta &rarr;</div>
  </div>
</div>"""


def _html_conteudo(item: dict, i: int, total: int, plano: dict) -> str:
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

    paginas = [_html_capa(plano, total)]
    for k, item in enumerate(itens, start=2):
        paginas.append(_html_conteudo(item, k, total, plano))
    paginas.append(_html_fecho(plano, total))

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
    "slides": [
        {"rotulo": "ERRO Nº 1", "titulo": "Guardar tudo o que sobrou",
         "linha": "Pote sem tampa, sacola de sacola e caixa vazia ocupam a "
                  "prateleira que faria falta pro que você usa toda semana.",
         "conclusao": "Descarta antes de organizar"},
        {"rotulo": "ERRO Nº 2", "titulo": "Organizar sem lugar fixo",
         "linha": "Se cada coisa volta pra um lugar diferente, a bagunça "
                  "reaparece em três dias. Lugar fixo é o que sustenta.",
         "conclusao": "Um lugar pra cada coisa"},
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
