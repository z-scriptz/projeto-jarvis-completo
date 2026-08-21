#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# diag_conta.py -- o alcance de uma conta AO LONGO DO TEMPO, e contra as outras.
#
# POR QUE EXISTE (21/08)
# ─────────────────────
# O vigia mediu seguidores pela 1ª vez e o quadro virou de cabeça pra baixo:
#
#     @topshopcasa_       9 seguidores · 111 de alcance · 12,3x a base
#     @topshopbeauty._   36 seguidores · 120 de alcance ·  3,3x
#     @topshop.__        52 seguidores · 112 de alcance ·  2,2x
#     @topshoptech_     413 seguidores · 117 de alcance ·  0,28x   ← ???
#
# A ÚNICA conta com audiência de verdade é a ÚNICA entregando abaixo da base.
# As pequenas alcançam 2 a 12 vezes o número de seguidores; a grande alcança
# um quarto. Isso não é "conta pequena cresce mais fácil": é anomalia, e é
# onde está o dinheiro — 413 pessoas que já disseram sim e não estão vendo.
#
# ⚠️ ESTE ARQUIVO NÃO CONCLUI NADA. Ele responde UMA pergunta, que é a que
# separa as hipóteses:
#
#     SEMPRE foi assim?  → o problema é o conteúdo ou o nicho
#     CAIU num dia?      → a data é a pista, e aí procura-se o que mudou nela
#
# Sem essa separação, qualquer teoria (shadowban, link na legenda, frequência,
# conteúdo repetido) parece igualmente plausível — e eu já gastei rodadas
# demais neste projeto testando teorias plausíveis em vez de olhar o dado.
#
# Uso (VPS):
#   .venv/bin/python diag_conta.py tech
#   .venv/bin/python diag_conta.py --todas

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
METRICAS = BASE / "shared" / "metricas_posts.jsonl"


def _log(m):
    print(m, flush=True)


def _linhas():
    try:
        cru = METRICAS.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    fora = []
    for ln in cru:
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
            r["_q"] = datetime.strptime(f"{r.get('data')} {r.get('hora')}",
                                        "%Y-%m-%d %H:%M:%S")
            fora.append(r)
        except Exception:
            continue
    return fora


def _mediana(ns):
    ns = sorted(ns)
    return ns[len(ns) // 2] if ns else 0


def _barra(valor, teto, largura=28):
    if teto <= 0:
        return ""
    return "█" * max(1, int(largura * valor / teto)) if valor else ""


def por_semana(linhas, nicho=""):
    """Mediana de alcance por semana. É a série que responde 'caiu ou sempre foi'.

    Semana e não dia: com 2 a 3 posts por dia por conta, o dia é ruído. E
    MEDIANA e não média — um viral de 274 mil levanta a média de uma semana
    inteira e esconde que todo o resto ficou em 100.
    """
    grupos = defaultdict(list)
    for r in linhas:
        if nicho and (r.get("nicho") or "").lower() != nicho.lower():
            continue
        ano, sem, _ = r["_q"].isocalendar()
        grupos[(ano, sem)].append(r.get("reach", 0) or 0)
    return {k: (_mediana(v), len(v)) for k, v in sorted(grupos.items())}


def olhar(nicho: str, linhas: list):
    serie = por_semana(linhas, nicho)
    if not serie:
        _log(f"\n  [{nicho}] nenhum post medido — nada a dizer")
        return
    teto = max(m for m, _ in serie.values())
    _log(f"\n  ── {nicho} ──  (mediana de alcance por semana)")
    for (ano, sem), (med, n) in serie.items():
        seg = datetime.fromisocalendar(ano, sem, 1)
        _log(f"    {seg:%d/%m}  {med:>6,}  n={n:<3} {_barra(med, teto)}"
             .replace(",", "."))

    medianas = [m for m, _ in serie.values()]
    if len(medianas) >= 3:
        # ⚠️ compara o ÚLTIMO com o MELHOR, não com o anterior. Queda lenta em
        # 3 semanas não aparece na comparação semana a semana, e é justamente
        # a forma que uma conta morre sem ninguém notar.
        pior, melhor = medianas[-1], max(medianas)
        # ⚠️ formata o NÚMERO, não a frase. A 1ª versão fazia
        # `f"...({melhor:,}, semana de...)".replace(",", ".")` e trocava também
        # a vírgula do texto: saía "(841. semana de 06/07)". Erro bobo, mas o
        # tipo que faz a saída parecer defeituosa e o leitor duvidar do resto.
        _p, _m = f"{pior:,}".replace(",", "."), f"{melhor:,}".replace(",", ".")
        if melhor and pior < melhor * 0.5:
            quando = [k for k, v in serie.items() if v[0] == melhor][0]
            pico = datetime.fromisocalendar(quando[0], quando[1], 1)
            _log(f"    ⚠️  hoje ({_p}) é menos da METADE do melhor "
                 f"({_m}, semana de {pico:%d/%m})")
            _log(f"        → procure o que mudou entre {pico:%d/%m} e o fim daquela semana")
        else:
            _log(f"    o último ({_p}) está em linha com o melhor "
                 f"({_m}) — não caiu, sempre foi assim")


def main():
    p = argparse.ArgumentParser(
        description="Alcance de uma conta ao longo do tempo. Só lê.")
    p.add_argument("nicho", nargs="?", default="", help="tech, casa, beleza…")
    p.add_argument("--todas", action="store_true", help="todas as contas")
    args = p.parse_args()

    linhas = _linhas()
    if not linhas:
        _log(f"  sem métricas em {METRICAS}")
        _log("  rode antes: .venv/bin/python metricas_posts.py")
        return 1

    _log(f"  {len(linhas)} post(s) medido(s) · "
         f"de {min(r['_q'] for r in linhas):%d/%m} "
         f"a {max(r['_q'] for r in linhas):%d/%m}")

    if args.todas or not args.nicho:
        nichos = sorted({(r.get("nicho") or "?") for r in linhas})
        for n in nichos:
            olhar(n, linhas)
        _log("\n  ── comparação direta (última semana de cada) ──")
        for n in nichos:
            s = por_semana(linhas, n)
            if s:
                med, qtd = list(s.values())[-1]
                _log(f"    {n:10} {med:>6,} de alcance mediano · {qtd} post(s)"
                     .replace(",", "."))
    else:
        olhar(args.nicho, linhas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
