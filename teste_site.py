#!/usr/bin/env python3
"""Abre o site num navegador de verdade e CLICA nas coisas.

⚠️ POR QUE ISTO EXISTE (01/09). O filtro de categoria do catálogo ficou morto e
nenhuma verificação minha pegou, porque todas liam o HTML como texto: o chip
estava lá, o `data-filtro` estava lá, o `aplicar()` estava lá — e o clique
morria no caminho, porque o arrasto da fita marcava `.arrastando` já no
`pointerdown` e `.arrastando .chip{pointer-events:none}` tirava o chip do teste
de acerto no meio do próprio clique:

    pointerdown -> chip          mouseup -> .fita-rolo
    mousedown   -> chip          click   -> .fita-rolo   (closest('.chip') = null)

📌 GREP NÃO CLICA. Página é comportamento, e comportamento só se verifica
executando. Quem achou o defeito foi o Dre, abrindo a página.

Como rodar (a VPS não precisa disto; é ferramenta de banca):

    pip install playwright
    python3 teste_site.py [pasta_do_site]

A pasta precisa ter `index.html` e `todos.html` gerados pelo bio_page_builder.
Sem argumento, usa ./site.
"""
import asyncio
import os
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("❌ falta o playwright:  pip install playwright")
    raise SystemExit(2)

# o Chromium do ambiente; se não existir, o playwright acha o dele sozinho
CHROMIUM = "/opt/pw-browsers/chromium"

# ⚠️ MEDIR NA PÁGINA, NUNCA NUM ARQUIVO DE TESTE À PARTE. Em 01/09 eu medi o til
# do Ã num HTML isolado, o @font-face não pegou, o canvas devolveu a métrica da
# fonte de reserva (0,844 em em vez de 0,935) e a correção saiu curta — o
# defeito continuou no ar depois de "corrigido". Aqui a medida sai da mesma
# página que o usuário vê, e desiste se a fonte não estiver carregada.
# ⚠️ COM TETO, SENAO TRAVA. Imagem com loading="lazy" fora da tela fica
# `complete === false` PARA SEMPRE (ela nem foi pedida), e foto de loja
# externa pendura no proxy. A primeira versao disto travou o teste em 9
# minutos. 📌 Espera de teste sempre com teto: sem ele, "esperar o
# carregamento" vira "esperar o que nunca vai acontecer".
ESPERAR_IMAGENS = """() => Promise.race([
    Promise.all([...document.images]
        .filter(i => !i.complete && i.getBoundingClientRect().top < innerHeight * 2)
        .map(i => new Promise(r => { i.onload = i.onerror = r; }))),
    new Promise(r => setTimeout(r, 2500))
])"""

MEDIR_MANCHETE = r"""() => {
  var h1 = document.querySelector('.abre h1');
  if (!h1) return null;
  var px = parseFloat(getComputedStyle(h1).fontSize);
  if (!document.fonts.check('400 ' + px + 'px "Instrument Serif"')) return null;
  var cv = document.createElement('canvas').getContext('2d');
  cv.font = '400 ' + px + 'px "Instrument Serif"';
  var linhas = [].map.call(h1.querySelectorAll('span'), function(sp){
    var b = sp.querySelector('b'), rc = b.getBoundingClientRect();
    var txt = b.textContent.toUpperCase();
    var m = cv.measureText(txt);
    var base = rc.top + (rc.height + px * 0.72) / 2;   /* base aproximada */
    return {txt: txt, alta: sp.classList.contains('alta'),
            sobe: m.actualBoundingBoxAscent / px,
            desce: m.actualBoundingBoxDescent / px,
            topo: base - m.actualBoundingBoxAscent,
            fim: base + m.actualBoundingBoxDescent};
  });
  var folgas = [];
  for (var i = 1; i < linhas.length; i++){
    folgas.push({onde: "'" + linhas[i-1].txt + "' → '" + linhas[i].txt + "'",
                 px: linhas[i].topo - linhas[i-1].fim});
  }
  var sub = document.querySelector('.abre-sub');
  if (sub) folgas.push({onde: 'manchete → subtítulo',
                        px: sub.getBoundingClientRect().top - linhas[linhas.length-1].fim});
  return {linhas: linhas, folgas: folgas};
}"""


class Placar:
    def __init__(self):
        self.falhas = []

    def __call__(self, cond, msg):
        print(("  ok    " if cond else "  FALHA ") + msg)
        if not cond:
            self.falhas.append(msg)


async def rodar(pasta: Path) -> int:
    p = Placar()
    base = "file://" + str(pasta.resolve())
    for arq in ("index.html", "todos.html"):
        if not (pasta / arq).exists():
            print(f"❌ {pasta/arq} não existe — gere o site antes")
            return 2

    lanc = {"executable_path": CHROMIUM} if Path(CHROMIUM).exists() else {}
    async with async_playwright() as pw:
        nav = await pw.chromium.launch(**lanc)

        # ── catálogo em tela larga ────────────────────────────────────────
        pg = await nav.new_page(viewport={"width": 1280, "height": 900})
        erros = []
        pg.on("pageerror", lambda e: erros.append(str(e)))
        await pg.goto(base + "/todos.html")
        await pg.wait_for_timeout(500)

        async def vis():
            return await pg.eval_on_selector_all(
                ".card", "e => e.filter(x => !x.classList.contains('esconde')).length")

        total = await vis()
        print(f"catálogo: {total} cards")
        p(total > 0, "a grade nasce com produtos")

        cats = await pg.eval_on_selector_all("#filtros .chip",
                                             "e => e.map(x => x.dataset.filtro)")
        alvo = next((c for c in cats if c != "todos"), None)
        p(alvo is not None, f"existe categoria pra testar ({cats})")
        if alvo:
            await pg.click(f'#filtros .chip[data-filtro="{alvo}"]')
            await pg.wait_for_timeout(500)
            n = await vis()
            p(0 < n < total, f"a categoria {alvo} filtra ({n} de {total})")
            p(await pg.eval_on_selector(f'#filtros .chip[data-filtro="{alvo}"]',
                                        "e => e.getAttribute('aria-pressed')") == "true",
              "o chip clicado fica marcado")
            await pg.click('#filtros .chip[data-filtro="todos"]')
            await pg.wait_for_timeout(500)
            p(await vis() == total, "'todos' devolve a grade inteira")

        # ⚠️ TROCAR DE CATEGORIA, NÃO SÓ FILTRAR UMA VEZ. O meu teste clicava
        # numa categoria vindo de "tudo" — o caminho fácil, onde os cards já
        # estão visíveis. O que quebrava era o outro: vir de uma categoria
        # pequena pra uma grande, com dezenas de cards saindo de escondido. O
        # Dre viu como "Cozinha só tem um relógio". 📌 Um teste que só percorre
        # a transição fácil aprova o código na única situação que não importa.
        alvos = [c for c in cats if c != "todos"][:6]
        perdas = 0
        for cat in (alvos + list(reversed(alvos)) + alvos):
            await pg.click(f'#filtros .chip[data-filtro="{cat}"]')
            await pg.wait_for_timeout(650)
            v = await vis()
            n = await pg.eval_on_selector_all(
                ".card", f"e => e.filter(x => x.dataset.categoria === {cat!r}).length")
            if v != n:
                perdas += 1
                print(f"        {cat}: visíveis={v} html={n}")
        p(perdas == 0, f"{len(alvos)*3} trocas de categoria sem perder card")
        await pg.click('#filtros .chip[data-filtro="todos"]')
        await pg.wait_for_timeout(600)

        if await pg.query_selector('#filtros-plat .loja[data-plat="shopee"]'):
            await pg.click('#filtros-plat .loja[data-plat="shopee"]')
            await pg.wait_for_timeout(500)
            p(await vis() > 0, "o filtro de loja responde")
            await pg.click('#filtros-plat .loja[data-plat="todos"]')
            await pg.wait_for_timeout(400)

        await pg.fill("#busca", "zzzzqqq")
        await pg.wait_for_timeout(500)
        p(await vis() == 0, "busca sem resultado esvazia a grade")
        p(await pg.eval_on_selector("#sem-res", "e => e.style.display !== 'none'"),
          "e o aviso de 'não tem' aparece")
        await pg.fill("#busca", "")
        await pg.wait_for_timeout(500)
        p(await vis() == total, "limpar a busca devolve tudo")

        # chegar pela home, já filtrado
        await pg.goto(base + "/index.html")
        await pg.wait_for_timeout(400)
        hrefs = await pg.eval_on_selector_all(".cat-l", "e => e.map(x => x.getAttribute('href'))")
        p(any("todos.html?c=" in (h or "") for h in hrefs),
          f"a home aponta pro catálogo com categoria ({len(hrefs)} links)")
        if alvo:
            await pg.goto(f"{base}/todos.html?c={alvo}")
            await pg.wait_for_timeout(700)
            p(await pg.eval_on_selector(f'#filtros .chip[data-filtro="{alvo}"]',
                                        "e => e.getAttribute('aria-pressed')") == "true",
              f"chegar por ?c={alvo} já abre filtrado")
            p(await vis() < total, "e a grade já vem cortada")

        # ── a marca no topo ───────────────────────────────────────────────
        await pg.goto(base + "/index.html")
        await pg.wait_for_timeout(500)
        icones = await pg.eval_on_selector_all(
            "link[rel=icon],link[rel=apple-touch-icon]", "e => e.map(x => x.href)")
        p(len(icones) == 2, f"favicon e apple-touch-icon no lugar ({len(icones)})")
        # ⚠️ O favicon ficou DUAS trocas de paleta pra trás sem ninguém notar,
        # porque é o único elemento do site que nunca se olha de perto.
        p(all("FF3D6E" not in h and "0B0C0F" not in h for h in icones),
          "o favicon não tem mais as cores aposentadas")

        # ⚠️ ESPERAR AS IMAGENS ANTES DE MEDIR ROLAGEM. Enquanto elas
        # carregam, o navegador reancora o scroll pra manter na tela o que você
        # está vendo — e isso EMPURRA o scrollY pra baixo no meio da subida ao
        # topo. Medido: 1163 -> 1636 -> 0, com o zero chegando em ~750ms. A
        # página está certa (a rolagem ganha a queda de braço); quem media
        # errado era o teste, cronometrando durante o carregamento.
        # 📌 NAO é o mesmo defeito de antes: aquele era a animação sendo
        # ABORTADA, este é ela sendo CONTRARIADA. Mesmo sintoma, causa outra.
        await pg.evaluate(ESPERAR_IMAGENS)
        await pg.evaluate("scrollTo(0, 2000)")
        await pg.wait_for_timeout(500)
        await pg.evaluate("window.__vivo = 1")
        url_antes = pg.url
        await pg.click("a.marca")
        serie = []
        for _ in range(14):            # até 2,1s, saindo assim que chegar
            await pg.wait_for_timeout(150)
            serie.append(await pg.evaluate("scrollY"))
            if serie[-1] == 0:
                break
        # 📌 A asserção conta o que MEDIU. "Falhou" sem número obriga a
        # reproduzir tudo de novo só pra saber o que aconteceu.
        p(serie[-1] == 0,
          f"clicar na marca na home leva ao topo (scrollY: {serie})")
        p(await pg.evaluate("window.__vivo || 0") == 1, "e não recarrega a página")
        p(pg.url == url_antes, "e não muda a URL")

        await pg.goto(base + "/todos.html")
        await pg.wait_for_timeout(500)
        await pg.click("a.marca")
        await pg.wait_for_load_state("load")
        await pg.wait_for_timeout(400)
        p(pg.url.endswith("index.html"),
          "fora da home a marca continua sendo link pra home")

        p(not erros, f"sem erro de JS ({erros or 'nenhum'})")
        await pg.close()

        # ── o arrasto, em tela estreita ───────────────────────────────────
        # ⚠️ TEM QUE SER ESTREITA. Em 1280px a fita não transborda, logo
        # scrollLeft fica 0 faça o que fizer — e o teste reprova o código certo.
        # (Foi o que aconteceu na primeira rodada: a asserção é que estava errada.)
        pg = await nav.new_page(viewport={"width": 480, "height": 900})
        await pg.goto(base + "/todos.html")
        await pg.wait_for_timeout(500)
        larg = await pg.eval_on_selector("#filtros", "e => [e.scrollWidth, e.clientWidth]")
        p(larg[0] > larg[1], f"a fita transborda em 480px ({larg[0]} > {larg[1]})")

        async def vis2():
            return await pg.eval_on_selector_all(
                ".card", "e => e.filter(x => !x.classList.contains('esconde')).length")

        total2 = await vis2()
        cx = await pg.eval_on_selector(
            "#filtros .chip:not([data-filtro='todos'])",
            "e => {var r = e.getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2];}")
        await pg.mouse.move(cx[0], cx[1])
        await pg.mouse.down()
        for dx in range(0, 141, 20):
            await pg.mouse.move(cx[0] - dx, cx[1])
            await pg.wait_for_timeout(20)
        await pg.mouse.up()
        await pg.wait_for_timeout(600)
        p(await pg.eval_on_selector("#filtros", "e => e.scrollLeft") > 0,
          "arrastar rola a fita")
        p(await vis2() == total2, "e soltar em cima do chip NÃO filtra")
        p(not await pg.eval_on_selector("#filtros", "e => e.classList.contains('arrastando')"),
          "a classe .arrastando sai no fim do gesto")

        await pg.mouse.move(cx[0], cx[1])
        await pg.mouse.down()
        await pg.mouse.move(cx[0] - 3, cx[1])
        await pg.wait_for_timeout(30)
        await pg.mouse.up()
        await pg.wait_for_timeout(600)
        p(await vis2() < total2, "tremida de 3px continua sendo clique")
        await pg.close()

        # ── a manchete não pode se atropelar ──────────────────────────────
        pg = await nav.new_page(viewport={"width": 1356, "height": 900})
        await pg.goto(base + "/index.html")
        # sem saída pra internet a fonte não vem do Google; FONTE_SERIF aponta
        # pro .ttf baixado à mão e o teste continua valendo
        local = os.environ.get("FONTE_SERIF", "")
        if local and Path(local).exists():
            await pg.add_style_tag(content=(
                "@font-face{font-family:'Instrument Serif';font-style:normal;"
                "font-weight:400;src:url('file://%s') format('truetype');}"
                % Path(local).resolve()))
            await pg.evaluate("document.fonts.load('168px \"Instrument Serif\"')")
        await pg.wait_for_timeout(1500)
        medida = await pg.evaluate(MEDIR_MANCHETE)
        if not medida:
            print("  (pulado) a Instrument Serif não carregou — sem ela a medida "
                  "seria da fonte de reserva, e foi exatamente esse engano que "
                  "deixou o til batendo em 01/09. Baixe o .ttf e aponte FONTE_SERIF.")
        else:
            for l in medida["linhas"]:
                print("    %-14s sobe %.3f em  desce %.3f em%s" % (
                    l["txt"], l["sobe"], l["desce"], "  [alta]" if l["alta"] else ""))
            for f in medida["folgas"]:
                p(f["px"] > 0, "folga %s (%.1fpx)" % (f["onde"], f["px"]))

        await nav.close()

    print("\n" + ("✅ tudo passou" if not p.falhas else f"❌ {len(p.falhas)} falha(s)"))
    return 1 if p.falhas else 0


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("site")
    raise SystemExit(asyncio.run(rodar(destino)))
