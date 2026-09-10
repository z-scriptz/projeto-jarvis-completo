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
ESTILOS = ("escuro", "claro")
_MEM_ESTILO = BASE_DIR / "shared" / "capa_estilos_recentes.json"


def _escolher_estilo(conta: str) -> str:
    """Sorteia o estilo da capa, sem repetir o anterior daquela conta.

    `CARR_ESTILO=claro` no .env força um (pra testar ou pra travar).
    """
    forcado = os.environ.get("CARR_ESTILO", "").strip().lower()
    if forcado in ESTILOS:
        return forcado
    try:
        from shared.rotacao import escolher_sem_repetir as _rodar
    except Exception:
        try:
            from rotacao import escolher_sem_repetir as _rodar
        except Exception:
            return random.choice(list(ESTILOS))
    try:
        mem = json.loads(_MEM_ESTILO.read_text(encoding="utf-8"))
    except Exception:
        mem = {}
    chave = (conta or "?").lstrip("@").lower()
    escolhido, recentes = _rodar(list(ESTILOS), mem.get(chave) or [])
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

    hook = (capa.get("hook") or "").strip().upper()
    sub = _h.escape((capa.get("sub") or "").strip().upper())
    total = len(plano.get("slides") or []) + 2
    arrasta = _h.escape((capa.get("arrasta") or "ARRASTA PRO LADO").upper())
    handle = _h.escape(plano.get("handle") or "")

    # ⚠️ o estilo é do PLANO se ele mandar (auditoria, --estilo), senão sorteia
    estilo = (capa.get("estilo") or plano.get("estilo") or "").strip().lower()
    if estilo not in ESTILOS:
        estilo = _escolher_estilo(plano.get("handle") or nicho)
    if estilo == "claro":
        return _html_claro(hook=hook, sub=sub, total=total, arrasta=arrasta,
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
    # ⚠️ montado FORA da f-string: expressão de f-string não aceita barra
    # invertida no Python < 3.12, e este arquivo roda em três máquinas.
    cartao = (f"<div class=\"cartao\" style=\"background-image:url('{fundo_u}')\">"
              f"</div>") if tem_foto else ""
    margem_rodape = "34" if tem_foto else "auto"
    teto_hook = "520" if tem_foto else "900"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family:'Titulo'; src:url('{fonte_u}'); }}
@font-face {{ font-family:'Corpo'; src:url('{corpo_u}'); }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:{LARG}px; height:{ALT}px; overflow:hidden;
        font-family:'Corpo',sans-serif; background:#f4f1ea; color:#111; }}
.palco {{ position:relative; width:100%; height:100%;
          padding:96px 80px 80px; display:flex; flex-direction:column; }}

/* ⚠️ a mancha de cor é o ÚNICO enfeite, e fica ATRÁS do texto: nos virais o
   fundo tem uma forma (a nuvem azul da @olga_lehnerg), não um gradiente. */
.mancha {{ position:absolute; width:760px; height:760px; right:-190px;
           top:-160px; border-radius:50%; background:{cor}1f; }}

.hook {{ position:relative; font-family:'Titulo',sans-serif; font-size:126px;
         line-height:1.02; letter-spacing:-2px; color:#111;
         /* sem text-shadow: em fundo claro ela suja a letra em vez de recortar */ }}
.hook em {{ font-style:normal; }}
.cor {{ color:{cor}; }}
/* a tarja continua marcador, não retângulo — mas em fundo claro ela é a
   palavra em BRANCO sobre a cor, e não preta sobre a cor */
.tarja {{ position:relative; color:#fff; padding:0 14px; display:inline;
          line-height:inherit; }}
.tarja::before {{ content:''; position:absolute; left:-6px; right:-6px;
                  top:-.02em; bottom:-.10em; background:{cor}; z-index:-1;
                  transform:rotate(-1.2deg); border-radius:6px; }}

.sub {{ position:relative; margin-top:38px; padding-right:90px; font-size:40px;
        line-height:1.34; color:#4a4a52; text-transform:none; }}

/* a foto vira CARTÃO, não fundo. Sem foto, a capa é só tipografia. */
.cartao {{ position:relative; margin-top:auto; width:100%; height:560px;
           border-radius:28px; overflow:hidden; background:#e8e4db center/cover
           no-repeat; box-shadow:0 18px 50px rgba(0,0,0,.16); }}

.rodape {{ position:relative; margin-top:{margem_rodape}px;
           display:flex; align-items:center; gap:16px; font-size:30px;
           color:#6b6b74; }}
.rodape b {{ color:#111; font-weight:800; }}
.arrasta {{ margin-left:auto; display:flex; align-items:center; gap:12px;
            border:3px solid #111; border-radius:44px; padding:14px 28px;
            font-size:29px; font-weight:800; color:#111; }}
.arrasta i {{ font-style:normal; color:{cor}; font-size:32px; }}
</style></head><body><div class="palco">
  <div class="mancha"></div>
  <div class="hook" id="hook">{_marcar(hook)}</div>
  <div class="sub">{sub}</div>
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
    a = p.parse_args()

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

    saida = a.saida or f"capa_{plano.get('nicho', 'geral')}.jpg"
    r = renderizar_capa(plano, saida)
    if not r:
        return 1
    print(f"✅ {r}  ({Path(r).stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
