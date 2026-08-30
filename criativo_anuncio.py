#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# criativo_anuncio.py — a peça ÚNICA do anúncio pago (imagem, não carrossel).
#
# ⚠️ POR QUE NÃO SERVE REAPROVEITAR A CAPA DO CARROSSEL (30/08). Ela tem o botão
# "arrasta →" desenhado nela. Num anúncio de imagem única isso manda deslizar
# onde não há nada pra deslizar — e o formato de imagem única é onde a verba
# pequena rende mais, porque não depende de a pessoa interagir pra ver o resto.
#
# ⚠️ E O OBJETIVO É OUTRO. O carrossel orgânico existe pra reter e educar; ele
# fecha pedindo seguir ou salvar. Este existe pra UM clique, comprado, de gente
# que nunca ouviu falar da marca. Tudo que não empurra pro clique é peso.
#
# ⚠️ A DIFERENCIAÇÃO É O NÚMERO, e ela não é retórica: nenhum concorrente de
# achadinho consegue escrever "4.931 vendas" porque nenhum deles mede produto.
# A gente mede desde 29/08 (`enriquecer_fila.py`), e é o único ativo aqui que
# não dá pra copiar sem construir o sistema atrás.
#
# DOIS ÂNGULOS, porque não se sabe qual ganha antes de medir:
#   produto    um herói, preço grande, o número de vendas como prova
#   curadoria  a régua (analisados / aprovados) + três produtos
#
# USO (na VPS, dentro de ~/jarvis):
#   .venv/bin/python criativo_anuncio.py                  # os dois ângulos
#   .venv/bin/python criativo_anuncio.py --angulo produto
#   .venv/bin/python previa_carrossel.py criativos_anuncio   # ver no Telegram

import argparse
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

FILA = BASE_DIR / "shared" / "produtos_fila.json"
SAIDA = BASE_DIR / "criativos_anuncio"


def _log(m):
    print(f"   {m}", flush=True)


def _num(v) -> float:
    """Preço como número — os três formatos que a fila guarda.

    ⚠️ Mesma função que já existe no carrossel_brain e no portas_grupo, e a
    terceira cópia me incomoda. Ela está aqui porque este módulo precisa rodar
    mesmo se o brain não importar (ele puxa Gemini, roteador, ledger), e um
    gerador de criativo não pode depender disso. Se um dia virar quatro, sobe
    pra `shared/`."""
    if isinstance(v, (int, float)):
        return float(v)
    t = re.sub(r"[^\d,.]", "", str(v or ""))
    if not t:
        return 0.0
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def _reais(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _mil(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def _esc(t) -> str:
    return (str(t or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _fila() -> list:
    try:
        d = json.loads(FILA.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _melhores(itens: list, quantos: int) -> list:
    """Os campeões medidos, com foto e preço. Ordem: classe, depois vendas.

    ⚠️ SÓ QUEM TEM NÚMERO. Todo o argumento da peça é o número; produto sem
    medição não tem o que mostrar e ainda ocupa o lugar de um que tem."""
    bons = [i for i in itens
            if isinstance(i, dict) and i.get("imagem")
            and str(i.get("classe") or "") in ("mina_ouro", "ok")
            and int(i.get("vendas") or 0) > 0 and _num(i.get("preco")) > 0]
    bons.sort(key=lambda i: (0 if i.get("classe") == "mina_ouro" else 1,
                             -int(i.get("vendas") or 0)))
    return bons[:quantos]


def _regua(itens: list) -> dict:
    medidos = [i for i in itens if isinstance(i, dict) and i.get("classe")]
    bons = [i for i in medidos if i["classe"] in ("mina_ouro", "ok")]
    return {"medidos": len(medidos), "bons": len(bons)}


_BASE_CSS = """
 *{box-sizing:border-box;margin:0;padding:0}
 body{width:1080px;height:1350px;overflow:hidden;background:#0b0d12;
      color:#eef1f5;font-family:system-ui,-apple-system,"Segoe UI",Roboto,
      sans-serif;-webkit-font-smoothing:antialiased}
 .p{width:1080px;height:1350px;padding:72px 66px;display:flex;
    flex-direction:column;position:relative;overflow:hidden}
 .mancha{position:absolute;border-radius:50%;filter:blur(10px)}
 .selo{display:inline-flex;align-items:center;gap:14px;background:#16341f;
       color:#4ade80;font-size:26px;font-weight:700;letter-spacing:.06em;
       padding:14px 26px;border-radius:99px;align-self:flex-start;
       text-transform:uppercase}
 .selo i{width:13px;height:13px;border-radius:99px;background:#25d366}
 h1{font-size:82px;line-height:1.06;letter-spacing:-.03em;font-weight:800;
    margin-top:34px}
 h1 em{font-style:normal;color:#25d366}
 .rodape{margin-top:auto;display:flex;justify-content:space-between;
         align-items:flex-end;gap:20px}
 .marca{font-size:27px;color:#8b939f;font-weight:600}
 .botao{background:#25d366;color:#062a14;font-size:31px;font-weight:800;
        padding:20px 38px;border-radius:16px}
"""


def _pagina(corpo: str, css: str) -> str:
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<style>{_BASE_CSS}{css}</style></head><body>{corpo}</body></html>")


def _angulo_produto(itens: list) -> str:
    """Um herói, preço grande, vendas como prova.

    ⚠️ O NÚMERO DE VENDAS É O GANCHO, não o produto. "Kit de potes" não para o
    dedo de ninguém; "4.931 pessoas já compraram" para, porque é prova social
    verificável e o cérebro lê antes de decidir se é anúncio."""
    p = (_melhores(itens, 1) or [None])[0]
    if not p:
        return ""
    nome = _esc(p.get("campeao") or p.get("produto") or "")[:64]
    css = """
 .foto{margin:40px 0 0;border-radius:28px;overflow:hidden;background:#161b24;
       height:700px}
 .foto img{width:100%;height:100%;object-fit:cover;display:block}
 .preco{font-size:104px;font-weight:800;letter-spacing:-.04em;margin-top:36px}
 .nome{font-size:31px;color:#9aa3b0;margin-top:10px;line-height:1.3}
"""
    return _pagina(f"""
<div class="p">
  <div class="mancha" style="width:760px;height:760px;right:-260px;top:-300px;
       background:rgba(37,211,102,.13)"></div>
  <span class="selo"><i></i>{_mil(p.get('vendas'))} pessoas já compraram</span>
  <div class="foto"><img src="{_esc(p.get('imagem'))}" alt=""></div>
  <div class="preco">{_reais(_num(p.get('preco')))}</div>
  <div class="nome">{nome}</div>
  <div class="rodape">
    <div class="marca">achadinhos todo dia<br>no grupo do WhatsApp</div>
    <div class="botao">Entrar de graça</div>
  </div>
</div>""", css)


def _angulo_curadoria(itens: list) -> str:
    """A régua + três produtos. O argumento é o critério, não o produto.

    ⚠️ ESTE ÂNGULO SÓ EXISTE PORQUE A GENTE MEDE. Sem `enriquecer_fila`, os
    dois números da régua não existiriam e a peça viraria a mesma promessa
    vazia que todo concorrente faz ("as melhores ofertas!")."""
    tres = _melhores(itens, 3)
    if len(tres) < 3:
        return ""
    r = _regua(itens)
    if r["medidos"] < 20:
        # régua com amostra pequena enfraquece em vez de convencer
        return ""
    cards = "".join(
        f'<figure class="c"><span class="v">{_mil(i.get("vendas"))} vendas</span>'
        f'<img src="{_esc(i.get("imagem"))}" alt="">'
        f'<b>{_reais(_num(i.get("preco")))}</b></figure>' for i in tres)
    css = """
 .grade{display:flex;gap:18px;margin-top:40px}
 .c{flex:1;background:#161b24;border-radius:22px;overflow:hidden;
    position:relative;padding-bottom:16px}
 .c img{width:100%;height:340px;object-fit:cover;display:block;
        background:#1c212b}
 .c .v{position:absolute;top:14px;left:14px;background:rgba(6,10,16,.88);
       color:#4ade80;font-size:19px;font-weight:700;padding:7px 13px;
       border-radius:99px}
 .c b{display:block;font-size:36px;margin:16px 0 0 18px;letter-spacing:-.02em}
 .regua{display:flex;gap:20px;margin-top:40px}
 .regua div{flex:1;background:#161b24;border-radius:20px;padding:26px 22px}
 .regua b{display:block;font-size:56px;letter-spacing:-.03em;color:#fff}
 .regua span{font-size:24px;color:#8b939f;line-height:1.3;display:block;
             margin-top:6px}
"""
    return _pagina(f"""
<div class="p">
  <div class="mancha" style="width:820px;height:820px;left:-300px;bottom:-340px;
       background:rgba(37,211,102,.10)"></div>
  <span class="selo"><i></i>Grupo gratuito no WhatsApp</span>
  <h1>A gente <em>mede</em> antes<br>de mandar pra você</h1>
  <div class="regua">
    <div><b>{_mil(r['medidos'])}</b><span>produtos analisados</span></div>
    <div><b>{_mil(r['bons'])}</b><span>passaram no corte</span></div>
  </div>
  <div class="grade">{cards}</div>
  <div class="rodape">
    <div class="marca">achadinhos da Shopee<br>com o link, todo dia</div>
    <div class="botao">Entrar de graça</div>
  </div>
</div>""", css)


ANGULOS = {"produto": _angulo_produto, "curadoria": _angulo_curadoria}


def render(html: str, destino: Path) -> bool:
    """HTML -> JPEG 1080x1350. False se o navegador não colaborar."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        _log(f"❌ playwright ausente ({str(e)[:70]})")
        return False
    try:
        from slides_html import _chromium
        exe = _chromium() or None
    except Exception:
        # ⚠️ o `_chromium()` do slides_html resolve o descasamento entre a
        # versão da lib e a dos binários; sem ele o Playwright procura um
        # caminho que não existe. Se não der pra importar, deixa o padrão —
        # que funciona quando as versões batem.
        exe = None
    try:
        with sync_playwright() as pw:
            nav = pw.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage"],
                executable_path=exe)
            pag = nav.new_page(viewport={"width": 1080, "height": 1350},
                               device_scale_factor=1)
            pag.set_content(html, wait_until="load")
            # respiro pras fotos da Shopee chegarem; sem isso o card sai cinza
            pag.wait_for_timeout(2500)
            pag.screenshot(path=str(destino), type="jpeg", quality=92)
            nav.close()
        return True
    except Exception as e:
        _log(f"❌ não renderizei ({type(e).__name__}: {str(e)[:110]})")
        return False


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Gera a peça única do anúncio (1080x1350).")
    p.add_argument("--angulo", choices=sorted(ANGULOS),
                   help="só um ângulo (padrão: todos)")
    a = p.parse_args(argv)

    itens = _fila()
    if not itens:
        _log(f"❌ {FILA} vazia ou ilegível")
        return 1
    SAIDA.mkdir(parents=True, exist_ok=True)

    alvos = [a.angulo] if a.angulo else sorted(ANGULOS)
    feitos = 0
    for nome in alvos:
        html = ANGULOS[nome](itens)
        if not html:
            # ⚠️ ÂNGULO SEM MATÉRIA-PRIMA NÃO É ERRO. `curadoria` precisa de 3
            # produtos medidos e de amostra ≥20; num acervo novo isso não
            # existe ainda, e falhar aqui pararia o outro ângulo junto.
            _log(f"⏭️  {nome}: sem dado suficiente na fila — pulo")
            continue
        destino = SAIDA / f"{nome}.jpg"
        if render(html, destino):
            kb = destino.stat().st_size // 1024
            _log(f"✅ {destino.relative_to(BASE_DIR)}  ({kb} KB)")
            feitos += 1
    if feitos:
        _log(f"{feitos} peça(s) em {SAIDA.name}/ — veja com:")
        _log(f"   .venv/bin/python previa_carrossel.py {SAIDA.name}")
    return 0 if feitos else 1


if __name__ == "__main__":
    sys.exit(main())
