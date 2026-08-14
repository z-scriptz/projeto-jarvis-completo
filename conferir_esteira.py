#!/usr/bin/env python3
# conferir_esteira.py -- confere se cada vídeo PRONTO sabe de que conta ele é.
#
# POR QUE EXISTE (08/08/2026)
# O Dre viu um vídeo com a marca do @topshop.__ publicado no @topshopcasa_.
# Não é a logo que está errada: é o vídeo que foi RENDERIZADO para uma conta e
# POSTADO em outra.
#
# O mecanismo suspeito: cada pacote em pronto_para_postar/ carrega um
# `conta.json` ao lado dizendo o nicho e o handle. O daemon lê esse arquivo em
# _conta_do_slug/_nicho_do_slug — e quando ele FALTA, as funções devolvem "?" e
# "", e quem chama faz `or "geral"`. Um pacote sem conta.json vira "geral" sem
# ninguém avisar.
#
# Os pacotes antigos são os suspeitos: foram produzidos antes de a conta `casa`
# existir, quando produto de casa caía em "geral" e era renderizado com a marca
# do @topshop.__. Com 241 pacotes na esteira e 16 dias de fila, sobra tempo pra
# a classificação mudar entre produzir e postar.
#
# SÓ LÊ. Não apaga, não move, não posta.

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PRONTO = RAIZ / "pronto_para_postar"


def main():
    if not PRONTO.exists():
        print(f"não achei {PRONTO}")
        return 1

    pastas = sorted([p for p in PRONTO.iterdir() if p.is_dir()],
                    key=lambda p: p.stat().st_mtime)
    if not pastas:
        print("esteira vazia")
        return 0

    sem, com, ilegivel = [], [], []
    nichos, handles = Counter(), Counter()
    for p in pastas:
        f = p / "conta.json"
        if not f.exists():
            sem.append(p)
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            ilegivel.append(p)
            continue
        com.append((p, d))
        nichos[(d.get("nicho") or "-").lower()] += 1
        handles[d.get("handle") or "-"] += 1

    total = len(pastas)
    print(f"pacotes prontos: {total}")
    print(f"  COM conta.json:  {len(com)}")
    print(f"  SEM conta.json:  {len(sem)}   <- estes viram 'geral' silenciosamente")
    print(f"  ilegível:        {len(ilegivel)}")

    print("\nnicho declarado:")
    for n, q in nichos.most_common():
        print(f"   {n:10} {q:4}")
    print("\nhandle declarado:")
    for h, q in handles.most_common():
        print(f"   {h:20} {q:4}")

    if sem:
        print(f"\nos {min(10, len(sem))} SEM conta.json mais antigos:")
        for p in sem[:10]:
            d = datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m %H:%M")
            print(f"   {d}  {p.name[:56]}")

    # A checagem que interessa: pacote cujo nicho declarado NÃO é 'geral' mas
    # que é antigo o bastante pra ter sido renderizado quando 'casa' ainda não
    # existia. Esses são os candidatos a sair com a marca errada.
    print("\npacotes por dia e nicho (os antigos são os suspeitos):")
    por_dia = {}
    for p, d in com:
        dia = datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m")
        por_dia.setdefault(dia, Counter())[(d.get("nicho") or "-").lower()] += 1
    for p in sem:
        dia = datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m")
        por_dia.setdefault(dia, Counter())["SEM-conta.json"] += 1
    for dia in sorted(por_dia)[:30]:
        linha = "  ".join(f"{n}={q}" for n, q in sorted(por_dia[dia].items()))
        print(f"   {dia}  {linha}")

    print("\nO que fazer com o resultado:")
    print("  SEM conta.json > 0  -> estes precisam ser reclassificados ou podados;")
    print("                         postados hoje, vão pra conta errada.")
    print("  nicho 'casa' em pacote anterior à criação da conta casa")
    print("                      -> foi renderizado com a marca do @topshop.__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
