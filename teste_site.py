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
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("❌ falta o playwright:  pip install playwright")
    raise SystemExit(2)

# o Chromium do ambiente; se não existir, o playwright acha o dele sozinho
CHROMIUM = "/opt/pw-browsers/chromium"


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

        await nav.close()

    print("\n" + ("✅ tudo passou" if not p.falhas else f"❌ {len(p.falhas)} falha(s)"))
    return 1 if p.falhas else 0


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("site")
    raise SystemExit(asyncio.run(rodar(destino)))
