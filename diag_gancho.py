#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# diag_gancho.py -- quantos posts foram ao ar com o GANCHO falando de outro
# produto? Roda a regra nova sobre o diário do que JÁ FOI PUBLICADO.
#
# POR QUE ISSO EXISTE (02/09/2026)
# ────────────────────────────────
# O Dre viu no @topshop.__ um post cujo vídeo mostra resfriar o quarto, cuja
# legenda fala de dormir bem, e cujo GANCHO na tela dizia "Eu vivia recarregando
# o gás do ar do CARRO sem resolver". Três textos, dois produtos. Ele nomeou o
# custo melhor do que eu: *"é por causa dessas coisas que mata o vídeo e a
# retenção cai, às vezes foi entregue pro público errado"*.
#
# A causa era estrutural: `_conflita()` filtrava só o BANCO DE RESERVA. O gancho
# escrito pelo Gemini ia direto pra tela sem nenhuma checagem de assunto. E o
# dicionário `_CONCRETO` não tinha NENHUMA família de veículo, então nem na
# reserva "carro" seria barrado.
#
# Consertar é metade. A outra metade é saber se aquilo foi UM post ou TRINTA —
# e ninguém sabe isso olhando o feed, porque o gancho fica queimado no vídeo e
# só é legível assistindo cada um. O diário (`shared/posts_ledger.jsonl`) grava
# o gancho de cada post desde sempre. Então a regra nova roda sobre o passado.
#
# ⚠️ ISTO NÃO CONSERTA NADA. Só mede. Os posts listados aqui já estão no ar.
#
# USO (na VPS, dentro de ~/jarvis):
#   .venv/bin/python diag_gancho.py              # os últimos 120 posts
#   .venv/bin/python diag_gancho.py --tudo
#   .venv/bin/python diag_gancho.py --quantos 40

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

LEDGER = BASE / "shared" / "posts_ledger.jsonl"


def _nicho(reg) -> str:
    n = (reg.get("nicho") or "").strip().lower()
    if n:
        return n
    try:
        from shared.categorias import normalizar
        return normalizar(reg.get("categoria") or "")
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser(
        description="posts publicados cujo gancho fala de outro produto")
    ap.add_argument("--quantos", type=int, default=120)
    ap.add_argument("--tudo", action="store_true")
    a = ap.parse_args()

    if not LEDGER.exists():
        print(f"❌ não achei {LEDGER}")
        print("   rode de dentro de ~/jarvis na VPS.")
        return 1
    try:
        from hook_alana import _conflita
    except Exception as e:
        print(f"❌ não consegui importar hook_alana._conflita: {e}")
        print("   use .venv/bin/python — o módulo lê o .env e precisa das libs.")
        return 1

    regs = []
    for linha in LEDGER.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            regs.append(json.loads(linha))
        except Exception:
            continue
    if not a.tudo:
        regs = regs[-a.quantos:]

    com_gancho = [r for r in regs if (r.get("hook") or "").strip()]
    suspeitos, por_nicho = [], {}
    for r in com_gancho:
        n = _nicho(r)
        por_nicho[n or "?"] = por_nicho.get(n or "?", 0)
        # a LEGENDA entra como texto do produto de propósito: o Dre confirmou
        # que "a legenda é sempre a certa". É o melhor retrato do produto que o
        # diário guarda — a descrição da Shopee não é gravada aqui.
        if _conflita(r["hook"], r.get("produto", ""), n,
                     r.get("legenda", ""), estrito=True):
            suspeitos.append(r)
            por_nicho[n or "?"] += 1

    total = len(com_gancho)
    print(f"📓 {len(regs)} post(s) lidos · {total} com gancho gravado\n")
    if not total:
        print("nenhum gancho no diário — nada a medir.")
        return 0

    pct = 100.0 * len(suspeitos) / total
    print(f"🚩 {len(suspeitos)} de {total} ({pct:.1f}%) o gancho fala de uma "
          f"coisa que o produto não é\n")
    if por_nicho:
        linha = " · ".join(f"{k} {v}" for k, v in sorted(
            por_nicho.items(), key=lambda kv: -kv[1]) if v)
        if linha:
            print(f"   por nicho: {linha}\n")

    for r in suspeitos[-25:]:
        print(f"  📅 {r.get('data','?')} · {r.get('plataforma') or '?'} · "
              f"nicho {_nicho(r) or '?'}")
        print(f"     produto: {(r.get('produto') or '?')[:78]}")
        print(f"     gancho:  {(r.get('hook') or '').replace(chr(10), ' / ')[:78]}")
        leg = (r.get("legenda") or "").replace("\n", " ")[:78]
        if leg:
            print(f"     legenda: {leg}")
        print()
    if len(suspeitos) > 25:
        print(f"  … e mais {len(suspeitos) - 25}. Use --quantos pra recortar.")

    print("A regra que aponta estes posts agora roda ANTES de publicar "
          "(hook_alana.gerar_hook_alana, estrito=True).")
    print("Os que estão aqui já foram ao ar — isto é a conta do que passou, "
          "não uma fila de trabalho.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
