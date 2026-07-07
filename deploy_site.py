#!/usr/bin/env python3
# deploy_site.py
# Regenera o index.html (VITRINE dos produtos POSTADOS) e sobe pro repositório
# do GitHub Pages (z-scriptz/Topshop-Site), que serve o topshopoficial.com.br.
#
# Fecha o funil de dinheiro: o Jarvis posta -> produtos_fila.json -> este script
# regenera o site com o produto (e o link de afiliado) -> a bio mostra o mesmo
# produto do vídeo.
#
# Uso (no VPS):  python3 deploy_site.py
# Pré-requisito: um CLONE do Topshop-Site em ~/topshop-site (ou env
#                TOPSHOP_SITE_DIR), com push configurado (token/credencial).
#                O daemon (ou um cron) chama este script de tempos em tempos.

import os
import sys
import subprocess
from pathlib import Path

SITE_REPO = Path(os.environ.get("TOPSHOP_SITE_DIR", str(Path.home() / "topshop-site")))


def _log(m):
    print(f"[deploy_site] {m}")


def _carregar_builder():
    try:
        from creative_engine import bio_page_builder as B   # layout do VPS
        return B
    except Exception:
        import bio_page_builder as B                          # repo flat
        return B


def _git(*args):
    return subprocess.run(["git", "-C", str(SITE_REPO), *args],
                          capture_output=True, text=True)


def main():
    if not (SITE_REPO / ".git").exists():
        _log(f"ERRO: {SITE_REPO} não é um repo git. Clone o Topshop-Site lá antes.")
        _log("Ex: git clone https://github.com/z-scriptz/Topshop-Site.git ~/topshop-site")
        return 2

    B = _carregar_builder()

    produtos = B._carregar_produtos()
    # só o que TEM link (= produtos realmente postados). Não minera Shopee aqui,
    # então é rápido e não depende de credencial.
    produtos = [p for p in produtos if p.get("link")]
    if not produtos:
        _log("nenhum produto com link — nada a publicar")
        return 1
    _log(f"{len(produtos)} produtos com link na vitrine")

    html = B.gerar_site(produtos)
    idx = SITE_REPO / "index.html"

    if idx.exists() and idx.read_text(encoding="utf-8") == html:
        _log("site sem mudança — não precisa subir")
        return 0
    idx.write_text(html, encoding="utf-8")

    _git("add", "index.html")
    c = _git("commit", "-m", f"vitrine: {len(produtos)} produtos (auto)")
    if c.returncode not in (0, 1):   # 1 = nada pra commitar (ok)
        _log("commit falhou: " + (c.stderr or c.stdout)[:200])
        return 1
    p = _git("push")
    if p.returncode != 0:
        _log("push falhou: " + (p.stderr or p.stdout)[:200])
        return 1
    _log(f"OK! Site publicado com {len(produtos)} produtos -> topshopoficial.com.br")
    return 0


if __name__ == "__main__":
    sys.exit(main())
