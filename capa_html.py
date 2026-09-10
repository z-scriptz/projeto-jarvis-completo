#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# capa_html.py — desenha a capa do carrossel em HTML/CSS e fotografa com o
# Chromium headless (Playwright).
#
# ⚠️ POR QUE ISTO EXISTE, E POR QUE NÃO É "MAIS UM RENDERIZADOR" (22/08):
#
# O Dre comparou a nossa capa com as que ele fez no ChatGPT: *"tá muito ruim"*.
# Eu tinha tratado a diferença como falta de FOTO — e ofereci gerar fundo com
# IA (crédito esgotado) e depois pegar foto de banco (*"como assim usar o
# pexels? pelo amor de deus"*, e ele tem razão: é foto genérica que mil contas
# usam). Duas respostas erradas pra mesma pergunta.
#
# A diferença real é TIPOGRAFIA E ACABAMENTO, e o PIL não faz isso:
#   · `letter-spacing` negativo — o "aperto" das manchetes daquelas capas
#   · sombra em CAMADAS (uma dura pra recortar, uma difusa pra profundidade)
#   · tarja INCLINADA atrás da palavra, com as pontas irregulares
#   · textura no texto, gradiente com blend, vinheta
# No Pillow, cada um desses é um algoritmo à mão. Em CSS é uma linha, e o
# Chromium desenha melhor do que eu escreveria.
#
# ⚠️ E O NAVEGADOR JÁ ESTÁ NA VPS. `ig_playwright`, `whatsapp_playwright`,
# `coletor_assets` e outros já rodam Chromium ali. Isto não acrescenta
# dependência nenhuma: acrescenta um uso novo pra uma que já é paga.
#
# O QUE ISTO **NÃO** É: não é IA. É determinístico, custa zero, roda offline,
# e o texto sai EXATO — inclusive a logo, o @handle e o preço, que uma imagem
# gerada não garante.
#
# USO:
#   python3 capa_html.py --exemplo casa            # vê a capa
#   python3 capa_html.py --plano p.json --saida out/01.jpg
#   python3 capa_html.py --html casa               # cospe o HTML, sem navegador
#
#   from capa_html import renderizar_capa
#   renderizar_capa(plano, Path("out/01.jpg"))

import os
import re
import sys
import json
import random
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
    log = logging.getLogger("capa_html")

LARG, ALT = 1080, 1350
ESCALA = 2                     # fotografa em 2x e reduz: mesma sobra do render

# a mesma paleta do carrossel_render — uma fonte só pra cor da conta
CORES = {
    "tech":   "#A3FF4F", "casa": "#FF8A33", "beleza": "#D67AFF",
    "pet":    "#5EC8FF", "moda": "#FF7AB0", "geral":  "#F5C542",
}

_RX_TARJA = re.compile(r"\[([^\]]+)\]")
_RX_COR = re.compile(r"\*([^*]+)\*")


def _cor(nicho: str) -> str:
    return CORES.get((nicho or "geral").lower(), CORES["geral"])


def _escurecer(hex_cor: str, fator: float = 0.62) -> str:
    """A mesma cor, mais escura. Pra texto em fundo CLARO.

    ⚠️ A PALETA FOI DESENHADA PRA FUNDO PRETO. Renderizado o `pet` (#5EC8FF) e
    o `beleza` (#D67AFF) sobre o creme da capa clara, a palavra em destaque
    ficou MAIS FRACA que o preto ao lado — ou seja, a palavra escolhida pra
    saltar virou a menos legível da capa. Inversão do propósito, e só apareceu
    olhando o JPG.
    Escurecer resolve sem tocar na identidade: é a mesma cor, com menos luz.
    A tarja continua com a cor cheia, porque lá o texto é branco POR CIMA dela.
    """
    try:
        h = (hex_cor or "").lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return "#%02x%02x%02x" % (int(r * fator), int(g * fator), int(b * fator))
    except Exception:
        return hex_cor


def _contraste(hex_cor: str) -> str:
    """#111 ou #fff — o que for legível SOBRE essa cor.

    ⚠️ EU TINHA CRAVADO `color:#fff` NA TARJA e o `tech` mostrou o erro: o
    verde-limão (#A3FF4F) tem luminância alta, e branco sobre ele some. A cor
    do texto não pode ser escolhida uma vez pra seis paletas diferentes —
    quatro delas são claras. Fórmula de luminância relativa (W3C), que é a
    mesma que decide contraste de acessibilidade.
    """
    try:
        h = (hex_cor or "").lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        return "#111" if lum > 0.55 else "#fff"
    except Exception:
        return "#fff"


def _b64(caminho) -> str:
    """Arquivo → data: URI. ⚠️ O Chromium headless recusa `file://` a partir de
    uma página `data:`/`about:blank`, e embutir é mais simples que servir uma
    pasta por HTTP só pra isso."""
    p = Path(caminho)
    if not p.exists():
        return ""
    tipo = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "ttf": "font/ttf", "otf": "font/otf"}.get(
                p.suffix.lower().lstrip("."), "application/octet-stream")
    return f"data:{tipo};base64," + base64.b64encode(p.read_bytes()).decode()


def _fonte_titulo_b64() -> tuple:
    """(data-uri, nome). Anton se existir, senão a Montserrat da marca."""
    try:
        import render as R
        brand = R.BRAND_DIR
    except Exception:
        brand = BASE_DIR / "assets" / "brand"
    for nome in ("Anton-Regular.ttf", "ArchivoBlack-Regular.ttf",
                 "BebasNeue-Regular.ttf"):
        u = _b64(brand / nome)
        if u:
            return u, nome.split("-")[0]
    return _b64(brand / "Montserrat-Bold.ttf"), "Montserrat"


def _corpo_b64() -> str:
    try:
        import render as R
        brand = R.BRAND_DIR
    except Exception:
        brand = BASE_DIR / "assets" / "brand"
    return _b64(brand / "Montserrat-Bold.ttf")


def _logo_b64(nicho: str) -> str:
    try:
        import render as R
        from shared.marca import logo_do_nicho
        nome = logo_do_nicho(nicho, log)
        nome = nome[0] if isinstance(nome, (tuple, list)) else nome
        return _b64(R.BRAND_DIR / str(nome))
    except Exception:
        return ""


def _marcar(hook: str) -> str:
    """`*x*` → span colorido · `[x]` → tarja. Devolve HTML já escapado."""
    import html as _h
    saida, pos = [], 0
    padrao = re.compile(r"\*([^*]+)\*|\[([^\]]+)\]")
    for m in padrao.finditer(hook or ""):
        saida.append(_h.escape(hook[pos:m.start()]))
        if m.group(1) is not None:
            saida.append(f'<em class="cor">{_h.escape(m.group(1))}</em>')
        else:
            saida.append(f'<em class="tarja">{_h.escape(m.group(2))}</em>')
        pos = m.end()
    saida.append(_h.escape(hook[pos:]))
    return "".join(saida)


# ══════════════════════════════════════════════════════════════════════════
# ESTILOS DE CAPA
#
# ⚠️ POR QUE ISTO DEIXOU DE SER UM TEMPLATE SÓ (10/09/2026)
#
# O Dre: *"as imagens estão todas iguais... a pessoa sabe que é da página, mas
# às vezes cansa visualmente, parece estar repetido"*. E não era impressão: o
# `montar_html` era UM html, escrito uma vez — fundo `#0d0d0f`, foto a 62% de
# brilho, véu, vinheta, brilho colorido, logo circular com selo ✓ e contador de
# páginas no topo, hook em CAIXA ALTA. **Sete formatos de conteúdo, um visual.**
#
# 📌 E OS CINCO VIRAIS QUE ELE MANDOU DIZEM O CONTRÁRIO DISSO:
#
#   @rafabri7o          fundo BRANCO, texto preto gigante, sem logo, sem contador
#   @lucureau           fundo BRANCO, tipografia preta, ícones, layout de versus
#   @olga_lehnerg       fundo claro, lettering colorido, recorte de rosto
#   @homemquesabetudo   fundo azul CLARO, duas colunas MITO|VERDADE
#   @lucasmagazinetech  escuro, mas com a foto do produto em DESTAQUE (não
#                       escurecida) e o texto embaixo
#
# **Quatro dos cinco têm fundo claro. Nenhum tem bloco de marca no topo.** O
# nosso fazia exatamente o oposto, em toda capa, todo dia, nas seis contas.
#
# ⚠️ E O DRE JÁ DEU A REGRA DE OURO: *"o formato vai variando sempre, não
# precisam ser todos da mesma forma idêntica; o que estoura hoje pode não
# estourar amanhã, mas devemos aproveitar e reaproveitar"*. Então isto nasce
# como uma LISTA que cresce, sorteada com memória (`shared/rotacao.py`, a mesma
# que impede a resposta repetida) — e não como um segundo template fixo, que só
# trocaria uma mesmice por outra.
ESTILOS = ("escuro", "claro", "mito_verdade", "versus")

# ⚠️ AFINIDADE FORMATO → ESTILO, E ELA VALE MAIS QUE O SORTEIO (10/09/2026)
#
# O Dre: *"podemos misturar estilos... e manter o template pra cada um"*. Sim —
# mas sortear entre TODOS seria pior que o template único que a gente acabou de
# matar, porque colocaria um layout de duas colunas MITO|VERDADE num carrossel
# de "5 achadinhos", onde não há mito nenhum pra contrastar.
#
# 📌 A regra: **quando o conteúdo já tem forma, o template segue a forma.**
# `mitos` é literalmente dois lados; `comparacao` é literalmente A contra B. Pra
# esses, o estilo não é gosto, é a estrutura da informação. Pro resto — lista,
# erros, história, passo a passo — não há forma imposta, e aí sim vale o sorteio
# com memória, que é o que impede a mesmice.
#
# É a mesma lógica que já governa o `comentarios.py`: banco por FORMATO, porque
# num carrossel de "3 erros" pedir "corre pegar o seu" é resposta pra pergunta
# que ninguém fez.
AFINIDADE = {
    "mitos": "mito_verdade",
    "comparacao": "versus",
}
# os que entram no sorteio livre — os de forma imposta ficam de fora, senão
# sairiam em carrossel que não tem dois lados
ESTILOS_LIVRES = ("escuro", "claro")
_MEM_ESTILO = BASE_DIR / "shared" / "capa_estilos_recentes.json"


def _escolher_estilo(conta: str, formato: str = "") -> str:
    """O estilo da capa: por AFINIDADE se o formato tem forma, senão sorteio.

    `CARR_ESTILO=claro` no .env força um (pra testar ou pra travar).
    """
    forcado = os.environ.get("CARR_ESTILO", "").strip().lower()
    if forcado in ESTILOS:
        return forcado
    # ⚠️ a afinidade vem ANTES do sorteio: num carrossel de mitos, duas colunas
    # não é preferência, é a estrutura do conteúdo
    afim = AFINIDADE.get((formato or "").strip().lower())
    if afim in ESTILOS:
        return afim
    try:
        from shared.rotacao import escolher_sem_repetir as _rodar
    except Exception:
        try:
            from rotacao import escolher_sem_repetir as _rodar
        except Exception:
            return random.choice(list(ESTILOS_LIVRES))
    try:
        mem = json.loads(_MEM_ESTILO.read_text(encoding="utf-8"))
    except Exception:
        mem = {}
    chave = (conta or "?").lstrip("@").lower()
    escolhido, recentes = _rodar(list(ESTILOS_LIVRES), mem.get(chave) or [])
    mem[chave] = recentes
    try:
        _MEM_ESTILO.parent.mkdir(parents=True, exist_ok=True)
        tmp = _MEM_ESTILO.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(mem, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(_MEM_ESTILO)
    except Exception:
        pass          # memória é conforto: nunca trava um post
    return escolhido or "escuro"


def montar_html(plano: dict) -> str:
    import html as _h
    capa = plano.get("capa") or {}
    nicho = plano.get("nicho", "geral")
    cor = _cor(nicho)
    fonte_u, fonte_nome = _fonte_titulo_b64()
    corpo_u = _corpo_b64()
    logo_u = _logo_b64(nicho)

    fundo = (capa.get("fundo") or capa.get("foto") or "")
    if not fundo:
        for s in (plano.get("slides") or []):
            if s.get("foto"):
                fundo = s["foto"]
                break
    fundo_u = _b64(fundo) if fundo else ""

    # ⚠️ O CRU E O MAIÚSCULO SÃO COISAS DIFERENTES, e eu tinha misturado: o
    # Python já entregava `.upper()` pros dois estilos, então "tirar o
    # uppercase" no CSS do claro não mudou NADA — a capa saiu em caixa alta
    # igual, e o teste passou porque conferia a regra CSS em vez do texto.
    hook_cru = (capa.get("hook") or "").strip()
    sub_cru = _h.escape((capa.get("sub") or "").strip())
    hook = hook_cru.upper()
    sub = sub_cru.upper()
    total = len(plano.get("slides") or []) + 2
    arrasta = _h.escape((capa.get("arrasta") or "ARRASTA PRO LADO").upper())
    handle = _h.escape(plano.get("handle") or "")

    # ⚠️ o estilo é do PLANO se ele mandar (auditoria, --estilo), senão sorteia
    estilo = (capa.get("estilo") or plano.get("estilo") or "").strip().lower()
    if estilo not in ESTILOS:
        estilo = _escolher_estilo(plano.get("handle") or nicho,
                                  plano.get("formato") or "")
    if estilo in ("mito_verdade", "versus"):
        return _html_dois_lados(estilo, hook=hook_cru, sub=sub_cru, total=total,
                                arrasta=arrasta, handle=handle, cor=cor,
                                fonte_u=fonte_u, corpo_u=corpo_u, plano=plano)
    if estilo == "claro":
        return _html_claro(hook=hook_cru, sub=sub_cru, total=total, arrasta=arrasta,
                           handle=handle, cor=cor, fonte_u=fonte_u,
                           corpo_u=corpo_u, fundo_u=fundo_u)

    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family:'Titulo'; src:url('{fonte_u}'); }}
@font-face {{ font-family:'Corpo'; src:url('{corpo_u}'); }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:{LARG}px; height:{ALT}px; overflow:hidden;
        font-family:'Corpo',sans-serif; background:#0d0d0f; color:#fff; }}
.palco {{ position:relative; width:100%; height:100%; }}

/* ── fundo: a foto, tratada. ⚠️ `saturate` e `contrast` são o que tira a
   cara de catálogo: foto de produto vem lavada, em fundo branco. Sem isso
   ela vira uma mancha cinza atrás do texto. ── */
.foto {{ position:absolute; inset:0; background:#111 center/cover no-repeat;
         filter:saturate(1.15) contrast(1.08) brightness(.62); }}
.veu  {{ position:absolute; inset:0;
         background:linear-gradient(180deg,rgba(6,6,8,.93) 0%,
                    rgba(6,6,8,.80) 34%, rgba(6,6,8,.30) 62%,
                    rgba(6,6,8,.66) 100%); }}
/* vinheta: puxa o olho pro centro-alto, onde mora o hook */
.vinheta {{ position:absolute; inset:0;
            background:radial-gradient(120% 80% at 30% 26%,
                       rgba(0,0,0,0) 40%, rgba(0,0,0,.55) 100%); }}
.brilho {{ position:absolute; width:620px; height:620px; left:-160px; top:-150px;
           background:radial-gradient(circle,{cor}2e 0%,transparent 62%); }}

.topo {{ position:absolute; top:52px; left:64px; right:64px;
         display:flex; align-items:center; gap:18px; }}
.logo {{ width:92px; height:92px; border-radius:50%; object-fit:cover;
         border:3px solid {cor}; box-shadow:0 0 22px {cor}55; }}
.marca b {{ display:block; font-size:38px; letter-spacing:-.4px; }}
.marca span {{ display:block; font-size:29px; color:#c9c9cf; margin-top:2px; }}
.selo {{ display:inline-block; width:26px; height:26px; margin-left:8px;
         border-radius:50%; background:{cor}; position:relative; top:3px; }}
.selo::after {{ content:'✓'; position:absolute; inset:0; color:#111;
                font-size:18px; font-weight:900; display:flex;
                align-items:center; justify-content:center; }}
.pag {{ margin-left:auto; border:3px solid {cor}; border-radius:16px;
        padding:7px 20px; font-size:30px; font-weight:800; }}

/* ── o hook ── */
.bloco {{ position:absolute; left:64px; right:56px; top:250px; z-index:1; }}
.hook {{
         font-family:'Titulo',sans-serif; font-size:118px; line-height:.96;
         letter-spacing:-1.5px; text-transform:uppercase;
         /* sombra em DUAS camadas: a dura recorta a letra do fundo, a difusa
            dá profundidade. Uma só faz o texto parecer colado ou borrado. */
         text-shadow:0 4px 0 rgba(0,0,0,.85), 0 14px 34px rgba(0,0,0,.75); }}
.hook em {{ font-style:normal; }}
.cor {{ color:{cor}; }}
/* ⚠️ a tarja é INCLINADA e com respiro: reta e justa ela parece caixa de
   formulário. O -1.2° é o que faz parecer marcador, não retângulo. */
/* ⚠️ `z-index:-1` no ::before só funciona porque `.hook` tem `z-index:1` e
   vira contexto de empilhamento — sem isso a tarja vai parar ATRÁS do véu e
   some inteira, com o texto preto sobrando ilegível no escuro (foi o que
   aconteceu na 1ª tentativa).
   ⚠️ E `line-height:.96` é obrigatório: `inline-block` cria caixa com a
   altura CHEIA da fonte, o que inflou a linha e empurrou o subtítulo 250px
   pra baixo — o JS ancora o sub no `offsetHeight` real do hook, então uma
   caixa gorda aqui desloca tudo o que vem depois. */
.tarja {{ position:relative; color:#0b0b0d; padding:0 16px;
          display:inline; line-height:inherit; text-shadow:none; }}
/* ⚠️ o bloco EXTRAVASA a caixa da letra (top/bottom negativos). Justo, ele
   fica do tamanho do texto e some atrás das próprias letras — foi o que
   aconteceu na 2ª tentativa: laranja aparecendo só nas frestas. Nas
   referências o bloco tem folga generosa em volta da palavra. */
.tarja::before {{ content:''; position:absolute; left:-6px; right:-6px;
                  top:-.04em; bottom:-.12em; background:{cor}; z-index:-1;
                  transform:rotate(-1.2deg); border-radius:4px; }}

.sub {{ margin-top:46px; padding-right:60px; font-size:37px;
        line-height:1.32; letter-spacing:.2px; color:#e8e8ee;
        text-shadow:0 3px 12px rgba(0,0,0,.9); }}

.arrasta {{ position:absolute; left:64px; bottom:62px; display:flex;
            align-items:center; gap:14px; border:3px solid {cor};
            border-radius:44px; padding:16px 30px; font-size:31px;
            font-weight:800; letter-spacing:.6px;
            background:rgba(10,10,12,.42); backdrop-filter:blur(3px); }}
.arrasta i {{ font-style:normal; color:{cor}; font-size:34px; }}
</style></head><body><div class="palco">
  <div class="foto" style="background-image:url('{fundo_u}')"></div>
  <div class="veu"></div><div class="vinheta"></div><div class="brilho"></div>
  <div class="topo">
    {'<img class="logo" src="' + logo_u + '">' if logo_u else ''}
    <div class="marca"><b>TopShop<span class="selo"></span></b>
      <span>{handle}</span></div>
    <div class="pag">1/{total}</div>
  </div>
  <div class="bloco">
    <div class="hook" id="hook">{_marcar(hook)}</div>
    <div class="sub">{sub}</div>
  </div>
  <div class="arrasta">{arrasta} <i>&#10132;</i></div>
</div>
<script>
// ⚠️ SÓ O TAMANHO É AJUSTADO AQUI. Eu tinha posto o subtítulo em `position:
// absolute` e calculado o `top` dele por JS a partir do `offsetHeight` do
// hook — e ele pousava 250px abaixo do lugar. Posição é trabalho do CSS: hook
// e sub agora vivem no mesmo bloco em fluxo, separados por `margin-top`, e aí
// não há conta pra errar. O navegador continua sendo quem MEDE se o texto
// cabe, que é a única parte que o Python não faz sem chutar.
(function () {{
  var h = document.getElementById('hook');
  for (var t = 118; t > 52; t -= 2) {{
    h.style.fontSize = t + 'px';
    if (h.offsetHeight <= 620) break;
  }}
}})();
</script></body></html>"""


def _html_claro(hook, sub, total, arrasta, handle, cor,
                fonte_u, corpo_u, fundo_u) -> str:
    """A capa CLARA — o formato de 4 dos 5 virais que o Dre mandou.

    ⚠️ O QUE MUDA NÃO É A COR, É O QUE SAI DE CENA. Comparando os virais com a
    nossa capa escura, o que eles NÃO têm é o que mais pesava:

      · **sem logo circular, sem selo ✓, sem contador no topo.** Aquele bloco
        comia os 150px superiores de toda capa e é a primeira coisa que
        denuncia post de página comercial. A marca aparece no rodapé, discreta:
        quem gosta do conteúdo vai atrás de quem postou.
      · **sem CAIXA ALTA.** `text-transform:uppercase` num hook de 10 palavras
        vira bloco cinza no feed. Os cinco exemplos usam caixa normal, e é ela
        que deixa a frase ser LIDA em vez de escaneada.
      · **a foto não é fundo escurecido.** Aqui ela é um cartão, com moldura
        branca — como no @lucasmagazinetech, onde o produto é a estrela e o
        texto conversa com ele. Sem foto, a capa é só tipografia (@rafabri7o).

    ⚠️ E A ÚNICA COISA QUE FICA IGUAL É A LARGURA DA MEDIDA: o hook continua
    encolhendo por JS até caber. Isso não é estilo, é a diferença entre uma capa
    e um texto cortado.
    """
    tem_foto = bool(fundo_u)
    cor_texto = _escurecer(cor)
    cor_tarja = _contraste(cor)
    # ⚠️ montado FORA da f-string: expressão de f-string não aceita barra
    # invertida no Python < 3.12, e este arquivo roda em três máquinas.
    cartao = (f"<div class=\"cartao\" style=\"background-image:url('{fundo_u}')\">"
              f"</div>") if tem_foto else ""
    margem_rodape = "34px" if tem_foto else "auto"
    teto_hook = "520" if tem_foto else "760"
    justificar = "flex-start" if tem_foto else "center"
    # com o texto centralizado o hook tem mais folga vertical
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family:'Titulo'; src:url('{fonte_u}'); }}
@font-face {{ font-family:'Corpo'; src:url('{corpo_u}'); }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:{LARG}px; height:{ALT}px; overflow:hidden;
        font-family:'Corpo',sans-serif; background:#f4f1ea; color:#111; }}
.palco {{ position:relative; width:100%; height:100%;
          padding:96px 80px 80px; display:flex; flex-direction:column;
          justify-content:flex-start; }}
/* ⚠️ SEM FOTO, O TEXTO VAI PRO CENTRO — e quem centraliza é ESTE bloco, não o
   palco. O `justify-content` do palco não funcionava porque o rodapé tem
   `margin-top:auto`, que num flex absorve todo o espaço livre e não sobra
   nada pra distribuir. Sintoma: 400px de vazio entre o subtítulo e o rodapé,
   com a capa parecendo inacabada. Nos virais sem imagem (@rafabri7o) o texto
   ocupa o meio da tela. */
.texto {{ position:relative; flex:1; display:flex; flex-direction:column;
          justify-content:{justificar}; }}

/* ⚠️ a mancha de cor é o ÚNICO enfeite, e fica ATRÁS do texto: nos virais o
   fundo tem uma forma (a nuvem azul da @olga_lehnerg), não um gradiente. */
.mancha {{ position:absolute; width:760px; height:760px; right:-190px;
           top:-160px; border-radius:50%; background:{cor}1f; }}

.hook {{ position:relative; z-index:1;
         font-family:'Titulo',sans-serif; font-size:126px;
         line-height:1.02; letter-spacing:-2px; color:#111;
         /* sem text-shadow: em fundo claro ela suja a letra em vez de recortar */ }}
.hook em {{ font-style:normal; }}
.cor {{ color:{cor_texto}; }}
/* ⚠️ A TARJA AQUI NÃO USA `::before`, E O MOTIVO SAIU DA PRIMEIRA IMAGEM
   RENDERIZADA: no exemplo o trecho marcado era "na casa", que QUEBRA EM DUAS
   LINHAS — e `position:absolute` dentro de um `display:inline` partido se
   ancora só no primeiro fragmento. O bloco colapsou numa barra vertical de
   6px e sobrou "NA CASA" em BRANCO sobre fundo creme: ilegível.
   ⚠️ E não era o `z-index`, que foi meu primeiro palpite (copiado do aviso
   que eu mesmo tinha escrito no template escuro). Lá a tarja nunca quebrou
   linha, então o defeito estava lá o tempo todo, dormindo.
   `box-decoration-break:clone` é o recurso feito pra isto: pinta o fundo em
   CADA fragmento de linha. Perde a inclinação de -1.2°, e é uma troca boa —
   marcador torto ilegível não é marcador. */
.tarja {{ background:{cor}; color:{cor_tarja}; padding:2px 14px; display:inline;
          line-height:inherit; border-radius:6px;
          -webkit-box-decoration-break:clone; box-decoration-break:clone; }}

.sub {{ position:relative; margin-top:38px; padding-right:90px; font-size:40px;
        line-height:1.34; color:#4a4a52; text-transform:none; }}

/* a foto vira CARTÃO, não fundo. Sem foto, a capa é só tipografia. */
.cartao {{ position:relative; margin-top:auto; width:100%; height:560px;
           border-radius:28px; overflow:hidden; background:#e8e4db center/cover
           no-repeat; box-shadow:0 18px 50px rgba(0,0,0,.16); }}

.rodape {{ position:relative; margin-top:{margem_rodape};
           display:flex; align-items:center; gap:16px; font-size:30px;
           color:#6b6b74; }}
.rodape b {{ color:#111; font-weight:800; }}
.arrasta {{ margin-left:auto; display:flex; align-items:center; gap:12px;
            border:3px solid #111; border-radius:44px; padding:14px 28px;
            font-size:29px; font-weight:800; color:#111; }}
.arrasta i {{ font-style:normal; color:{cor}; font-size:32px; }}
</style></head><body><div class="palco">
  <div class="mancha"></div>
  <div class="texto">
    <div class="hook" id="hook">{_marcar(hook)}</div>
    <div class="sub">{sub}</div>
  </div>
  {cartao}
  <div class="rodape"><b>{handle}</b> · {total} slides
    <div class="arrasta">{arrasta} <i>&#10132;</i></div></div>
</div>
<script>
// mesma medida da capa escura: o navegador decide o tamanho, não eu
(function () {{
  var h = document.getElementById('hook');
  var teto = {teto_hook};
  for (var t = 126; t > 54; t -= 2) {{
    h.style.fontSize = t + 'px';
    if (h.offsetHeight <= teto) break;
  }}
}})();
</script></body></html>"""


def _dois_lados(plano: dict, estilo: str) -> tuple:
    """Os dois rótulos e os dois textos da capa de duas colunas.

    ⚠️ DEGRADA EM VEZ DE QUEBRAR. Se o plano não trouxer os dois lados, a capa
    ainda sai — com os rótulos e os dois primeiros slides. Capa que só funciona
    com o JSON perfeito é capa que um dia não sai, e "não saiu" no meio da
    esteira custa mais que uma capa genérica.
    """
    capa = plano.get("capa") or {}
    slides = [s for s in (plano.get("slides") or []) if isinstance(s, dict)]
    if estilo == "mito_verdade":
        rot_a, rot_b = "MITO", "VERDADE"
    else:
        rot_a, rot_b = "A", "B"
    a = (capa.get("lado_a") or "").strip()
    b = (capa.get("lado_b") or "").strip()
    if not a and slides:
        a = (slides[0].get("titulo") or slides[0].get("texto") or "").strip()
    if not b and len(slides) > 1:
        b = (slides[1].get("titulo") or slides[1].get("texto") or "").strip()
    # no versus os rótulos são os PRÓPRIOS produtos quando existirem
    if estilo == "versus":
        rot_a = (capa.get("rotulo_a") or a or "A").strip()[:26]
        rot_b = (capa.get("rotulo_b") or b or "B").strip()[:26]
        a = b = ""
    return rot_a, rot_b, a[:120], b[:120]


def _html_dois_lados(estilo, hook, sub, total, arrasta, handle, cor,
                     fonte_u, corpo_u, plano) -> str:
    """As capas de DUAS COLUNAS — `mito_verdade` e `versus`.

    ⚠️ POR QUE ESTAS DUAS COMPARTILHAM UM HTML: elas são a MESMA estrutura
    (título em cima, dois blocos lado a lado embaixo) com rótulos e cores
    diferentes. Escrever dois arquivos quase iguais seria criar a próxima
    divergência — foi assim que o `_carregar_env` virou 40 cópias.

    · `mito_verdade` vem do @homemquesabetudo (4.163 curtidas): fundo azul
      claro, MITO à esquerda em vermelho, VERDADE à direita em verde.
    · `versus` vem do @lucureau (4.757): fundo branco, os dois nomes empilhados
      com o "vs" no meio, tipografia preta e pesada.
    """
    import html as _h
    cor_texto = _escurecer(cor)
    cor_tarja = _contraste(cor)
    rot_a, rot_b, txt_a, txt_b = _dois_lados(plano, estilo)
    if estilo == "mito_verdade":
        fundo_pag, cor_a, cor_b = "#e8f2fb", "#d64545", "#2f9e5f"
        titulo_a, titulo_b = _h.escape(rot_a), _h.escape(rot_b)
    else:
        # ⚠️ NÃO é branco puro: o cartão também é branco, e branco sobre
        # branco vira caixa invisível — só a sombra denunciava que havia
        # algo ali. Cinza levíssimo dá o degrau sem virar outra cor.
        fundo_pag, cor_a, cor_b = "#f2f2f5", "#111111", cor_texto
        titulo_a, titulo_b = _h.escape(rot_a), _h.escape(rot_b)
    corpo_a, corpo_b = _h.escape(txt_a), _h.escape(txt_b)
    tem_corpo = bool(txt_a or txt_b)
    # ⚠️ no mito/verdade não há símbolo no meio: um "×" entre MITO e VERDADE
    # lê como multiplicação. No versus o "vs" É o nome do formato.
    meio = "vs" if estilo == "versus" else ""
    meio_html = f'<div class="meio">{meio}</div>' if meio else ""

    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family:'Titulo'; src:url('{fonte_u}'); }}
@font-face {{ font-family:'Corpo'; src:url('{corpo_u}'); }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:{LARG}px; height:{ALT}px; overflow:hidden;
        font-family:'Corpo',sans-serif; background:{fundo_pag}; color:#111; }}
.palco {{ position:relative; width:100%; height:100%;
          padding:88px 72px 76px; display:flex; flex-direction:column; }}
/* ⚠️ o grupo inteiro (título + sub + colunas) vai pro CENTRO, com o rodapé no
   pé. Sem isto o conteúdo grudava no topo e sobravam 500px de vazio embaixo —
   o mesmo defeito que a capa clara teve, pela mesma razão: `margin-top:auto`
   no rodapé absorve o espaço livre e não sobra o que distribuir no palco. */
.miolo {{ flex:1; display:flex; flex-direction:column; justify-content:center; }}
.hook {{ font-family:'Titulo',sans-serif; font-size:96px; line-height:1.02;
         letter-spacing:-1.6px; color:#111; }}
.hook em {{ font-style:normal; }}
.cor {{ color:{cor_texto}; }}
.tarja {{ background:{cor}; color:{cor_tarja}; padding:2px 12px; display:inline;
          border-radius:6px; -webkit-box-decoration-break:clone;
          box-decoration-break:clone; }}
.sub {{ margin-top:26px; font-size:36px; line-height:1.3; color:#55555f; }}

/* as duas colunas: é aqui que o formato vira desenho.
   ⚠️ `align-items:center`, não `stretch`: com stretch os cartões esticavam até
   o rodapé e sobravam 500px de branco embaixo de duas linhas de texto — a capa
   parecia um formulário vazio. O cartão tem que ter o tamanho do que ele diz. */
.lados {{ flex:0 0 auto; display:flex; gap:32px; align-items:stretch;
          margin:44px 0 0; }}
.lado {{ flex:1; display:flex; flex-direction:column; justify-content:center;
         min-height:280px; border-radius:26px; background:#fff; padding:38px 32px;
         box-shadow:0 10px 34px rgba(0,0,0,.08); }}
.rot {{ font-family:'Titulo',sans-serif; font-size:{'72' if estilo == 'mito_verdade' else '58'}px;
        line-height:1.04; letter-spacing:-1px; }}
.lado.a .rot {{ color:{cor_a}; }}
.lado.b .rot {{ color:{cor_b}; }}
.txt {{ margin-top:24px; font-size:33px; line-height:1.36; color:#3d3d45; }}
.meio {{ align-self:center; font-family:'Titulo',sans-serif; font-size:62px;
         color:#9a9aa4; }}

.rodape {{ margin-top:auto; display:flex; align-items:center; gap:16px;
           font-size:29px; color:#6b6b74; }}
.rodape b {{ color:#111; font-weight:800; }}
.arrasta {{ margin-left:auto; display:flex; align-items:center; gap:12px;
            border:3px solid #111; border-radius:44px; padding:13px 26px;
            font-size:28px; font-weight:800; color:#111; }}
.arrasta i {{ font-style:normal; color:{cor_texto}; font-size:31px; }}
</style></head><body><div class="palco">
  <div class="miolo">
  <div class="hook" id="hook">{_marcar(hook)}</div>
  <div class="sub">{sub}</div>
  <div class="lados">
    <div class="lado a"><div class="rot">{titulo_a}</div>
      {'<div class="txt">' + corpo_a + '</div>' if tem_corpo else ''}</div>
    {meio_html}
    <div class="lado b"><div class="rot">{titulo_b}</div>
      {'<div class="txt">' + corpo_b + '</div>' if tem_corpo else ''}</div>
  </div>
  </div>
  <div class="rodape"><b>{handle}</b> · {total} slides
    <div class="arrasta">{arrasta} <i>&#10132;</i></div></div>
</div>
<script>
(function () {{
  var h = document.getElementById('hook');
  for (var t = 96; t > 44; t -= 2) {{
    h.style.fontSize = t + 'px';
    if (h.offsetHeight <= 320) break;
  }}
}})();
</script></body></html>"""


def _chromium() -> str:
    """Caminho do Chromium, ou "" pra deixar o Playwright decidir.

    ⚠️ O PLAYWRIGHT PROCURA O NAVEGADOR PELA VERSÃO DELE, e quando a lib e os
    binários instalados não batem, o erro é `Executable doesn't exist at
    /opt/pw-browsers/chromium_headless_shell-1` — com o `-1194` ali do lado, na
    mesma pasta. Não é navegador faltando, é o número que não bate. Procurar o
    binário de verdade custa 6 linhas e evita um `playwright install` que
    baixaria 150 MB pra resolver um problema de nome."""
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


def renderizar_capa(plano: dict, destino) -> str:
    """Fotografa a capa. Devolve o caminho, ou "" com o motivo no log."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    html = montar_html(plano)
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        log.warning(f"   ⚠️  playwright ausente ({str(e)[:60]}) — capa HTML "
                    "não gerada; o carrossel cai no desenho em PIL")
        return ""
    try:
        with sync_playwright() as pw:
            nav = pw.chromium.launch(args=["--no-sandbox",
                                           "--disable-dev-shm-usage"],
                                     executable_path=_chromium() or None)
            pag = nav.new_page(viewport={"width": LARG, "height": ALT},
                               device_scale_factor=ESCALA)
            pag.set_content(html, wait_until="load")
            pag.wait_for_timeout(220)     # respiro pras fontes assentarem
            png = pag.screenshot(type="png")
            nav.close()
    except Exception as e:
        log.warning(f"   ⚠️  Chromium falhou ({str(e)[:90]})")
        return ""

    # ⚠️ JPEG, sempre: "JPEG is the only image format supported" na Meta. E o
    # screenshot sai em 2x — reduzir aqui é o mesmo passo do render em PIL.
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(png)).convert("RGB")
        if img.size != (LARG, ALT):
            img = img.resize((LARG, ALT), Image.LANCZOS)
        img.save(destino, "JPEG", quality=92, optimize=True)
    except Exception as e:
        log.warning(f"   ⚠️  não converti pra JPEG ({str(e)[:70]})")
        return ""
    return str(destino)


_EXEMPLO = {
    "casa": ("3 ERROS QUE QUASE TODO *MUNDO* COMETE [NA CASA]",
             "pequenos habitos que bagunçam tudo sem voce perceber"),
    "tech": ("5 ERROS QUE ESTAO [ACABANDO] COM SUA *BATERIA*",
             "e voce faz pelo menos 2 deles todo dia"),
}


def main() -> int:
    p = argparse.ArgumentParser(description="Capa do carrossel em HTML/CSS")
    p.add_argument("--exemplo", metavar="NICHO")
    p.add_argument("--plano", metavar="JSON")
    p.add_argument("--saida", default="")
    p.add_argument("--html", metavar="NICHO", help="cospe o HTML e sai")
    p.add_argument("--fundo", default="", help="imagem de fundo pro exemplo")
    p.add_argument("--estilo", default="", choices=("",) + tuple(ESTILOS),
                   help=f"força o estilo da capa: {', '.join(ESTILOS)}")
    p.add_argument("--todos", action="store_true",
                   help="gera UMA capa de cada estilo, pra comparar lado a lado")
    a = p.parse_args()
    if a.estilo:
        os.environ["CARR_ESTILO"] = a.estilo

    nicho = a.exemplo or a.html
    if a.plano:
        plano = json.loads(Path(a.plano).read_text(encoding="utf-8"))
    elif nicho:
        hook, sub = _EXEMPLO.get(nicho, _EXEMPLO["casa"])
        plano = {"nicho": nicho, "handle": f"@topshop{nicho}_",
                 "capa": {"hook": hook, "sub": sub, "fundo": a.fundo},
                 "slides": [{}, {}, {}], "cta": {}}
    else:
        p.print_help()
        return 1

    if a.html:
        print(montar_html(plano))
        return 0

    # ⚠️ O NOME LEVA O ESTILO, e isso não é enfeite: rodar duas vezes pra
    # comparar escuro × claro sobrescrevia o mesmo `capa_casa.jpg` e o Dre
    # ficava com UMA imagem, achando que tinha as duas. Comparação que só
    # existe se você lembrar de renomear no meio não é comparação.
    nicho_nome = plano.get("nicho", "geral")
    estilos_pedidos = list(ESTILOS) if a.todos else [
        a.estilo or os.environ.get("CARR_ESTILO", "").strip().lower() or ""]

    feitos = []
    for est in estilos_pedidos:
        if est:
            os.environ["CARR_ESTILO"] = est
            plano.setdefault("capa", {})["estilo"] = est
        sufixo = f"_{est}" if est else ""
        saida = a.saida if (a.saida and len(estilos_pedidos) == 1) \
            else f"capa_{nicho_nome}{sufixo}.jpg"
        r = renderizar_capa(plano, saida)
        if not r:
            return 1
        feitos.append(r)
        print(f"✅ {r}  ({Path(r).stat().st_size // 1024} KB)"
              + (f"  [estilo: {est}]" if est else ""))
    if len(feitos) > 1:
        print(f"\n   {len(feitos)} capas lado a lado — abra as duas antes de decidir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
