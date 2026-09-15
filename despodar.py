#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""despodar.py -- desfaz podas de fontes feitas pelo ceo_agent numa data.

    python3 despodar.py                      # dry-run de HOJE
    python3 despodar.py --data 2026-09-15    # dry-run de um dia específico
    python3 despodar.py --executar           # aplica

⚠️ POR QUE ISTO EXISTE: em 15/09/2026 a consulta de vendas da Shopee falhou,
`_vendas_por_fonte()` devolveu vazio, e 8 fontes foram podadas sem NENHUM dado
de venda — o mesmo defeito que carimbou 36 no dia 14.

A poda sempre foi reversível (comenta a linha, não apaga), mas reverter na mão
em dois arquivos é chato o bastante para a pessoa não reverter. Isto tira essa
desculpa.

📌 Ele reverte pela MARCA DA DATA, não pela lista de handles: o que se quer
desfazer é *a rodada que não devia ter acontecido*, inteira.
"""
import argparse
import re
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TIKTOK_PERFIS = BASE_DIR / "tiktok_perfis.txt"
IG_PERFIS = BASE_DIR / "instagram_perfis.txt"

# Como `_podar_fontes()` escreve:
#   "# @handle #nicho   # PODADO CEO 2026-09-15: 8 posts, 0 vendas em vários dias"
PADRAO = re.compile(
    r"^#\s*(?P<original>.+?)\s*#\s*PODADO\s+CEO\s+(?P<data>\d{4}-\d{2}-\d{2}):")


def despodar(linha: str, data: str) -> str:
    """Devolve a linha original se ela foi podada NA data; senão, a mesma linha."""
    m = PADRAO.match(linha)
    if not m or m.group("data") != data:
        return linha
    return m.group("original").rstrip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=time.strftime("%Y-%m-%d"),
                    help="data da poda a desfazer (padrão: hoje)")
    ap.add_argument("--executar", action="store_true",
                    help="sem isto, só mostra o que faria")
    a = ap.parse_args()

    total = 0
    for arq in (TIKTOK_PERFIS, IG_PERFIS):
        if not arq.exists():
            print(f"·  {arq.name}: não existe, pulando")
            continue
        linhas = arq.read_text(encoding="utf-8").splitlines()
        novas, devolvidas = [], []
        for l in linhas:
            nova = despodar(l, a.data)
            if nova != l:
                devolvidas.append(nova)
            novas.append(nova)

        if not devolvidas:
            print(f"·  {arq.name}: nada podado em {a.data}")
            continue

        total += len(devolvidas)
        print(f"↩️  {arq.name}: {len(devolvidas)} fonte(s) de volta")
        for d in devolvidas:
            print(f"      {d}")
        if a.executar:
            arq.write_text("\n".join(novas) + "\n", encoding="utf-8")

    print()
    if not total:
        print(f"nenhuma poda de {a.data} encontrada.")
    elif a.executar:
        print(f"✅ {total} fonte(s) reativada(s). O coletor volta a puxar delas.")
    else:
        print(f"🔍 dry-run: {total} fonte(s) seriam reativadas. "
              f"rode de novo com --executar para aplicar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
