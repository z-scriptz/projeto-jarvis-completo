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


# Como reconhecer a FÓRMULA olhando o hook publicado. Espelha o catálogo do
# `hook_alana.FORMULAS` — ordem importa: 'pov_melhor_compra' antes de
# 'pov_beneficio', senão o genérico engole o específico.
_FORMULAS = [
    ("alerta_exclusao",   ("nao mostre isso pra quem", "não mostre isso pra quem")),
    ("necessidade",       ("toda pessoa que",)),
    ("eu_vs_shopee",      ("eu: ",)),
    ("pov_melhor_compra", ("pov: a melhor compra",)),
    ("pov_beneficio",     ("pov:",)),
    ("cumplice_humor",    ("nao veja esse video", "não veja esse vídeo")),
    ("segredo",           ("o segredo pra",)),
    ("virei_fa",          ("nunca imaginei", "nunca achei")),
    ("comprei_testei",    ("comprei sem esperar", "comprei so pra", "comprei só pra")),
    ("desabafo_shopee",   ('"',)),          # começa com fala entre aspas
]


def _formula(hook: str) -> str:
    h = (hook or "").strip().lower()
    for nome, marcas in _FORMULAS:
        for m in marcas:
            if h.startswith(m) or m in h[:40]:
                return nome
    return "(outro)"


def por_formula(linhas, nicho=""):
    """Alcance mediano por FÓRMULA de hook.

    ⚠️ POR QUE ISTO PRECISOU EXISTIR (21/08). Olhando a semana boa do tech,
    quatro dos seis melhores posts usavam 'Não mostre isso pra quem…' — a
    fórmula `alerta_exclusao`, que eu FILTREI FORA do prompt quando liguei o
    modo amplo, por ela fechar o público. No mesmo dia, mesma conta:

        1110  'Não mostre isso pra quem ama a própria privacidade'
         110  'O segredo pra transformar seu banho em um spa'

    Mesmo dia mata o argumento de que alcance acumula com o tempo. Ou a
    fórmula importa muito, ou o produto importa muito — e com 14 posts de uma
    conta não dá pra separar. Com 215 dá pra ao menos ver se o padrão se
    repete fora daquela semana.

    ⚠️ ISTO NÃO PROVA CAUSA. Fórmula e produto andam juntos: quem escreve
    'não mostre isso pra quem ama privacidade' está falando de uma bolsa de
    blindagem, que é um produto mais curioso que uma capa magnética. O que a
    tabela responde é se vale a pena TESTAR de propósito — não se deve mudar
    tudo agora.
    """
    grupos = defaultdict(list)
    for r in linhas:
        if nicho and (r.get("nicho") or "").lower() != nicho.lower():
            continue
        grupos[_formula(r.get("hook", ""))].append(r.get("reach", 0) or 0)
    return grupos


def olhar_formulas(linhas, minimo=3):
    grupos = por_formula(linhas)
    ordenado = sorted(((n, _mediana(v), len(v)) for n, v in grupos.items()
                       if len(v) >= minimo), key=lambda x: -x[1])
    if not ordenado:
        _log(f"\n  nenhuma fórmula com {minimo}+ posts medidos")
        return
    teto = ordenado[0][1]
    _log(f"\n  ── alcance mediano por FÓRMULA de hook (mín. {minimo} posts) ──")
    for nome, med, n in ordenado:
        _log(f"    {nome:20} {med:>6,}  n={n:<4} {_barra(med, teto)}"
             .replace(",", "."))
    fora = [(n, len(v)) for n, v in grupos.items() if len(v) < minimo]
    if fora:
        _log(f"    (fora: {', '.join(f'{n}={q}' for n, q in sorted(fora))} "
             f"— amostra pequena demais)")
    _log("    ⚠️  fórmula e produto andam juntos: isto diz o que TESTAR,")
    _log("        não o que já está provado.")


def _taxa_agrupada(linhas, chave, campo="saved", minimo=400):
    """Taxa POR MIL IMPRESSÕES, somando antes de dividir.

    ⚠️ POR QUE SOMAR ANTES DE DIVIDIR (21/08). Com alcance ~112 e 1 a 2
    salvamentos por post, a taxa de um post isolado é ruído: 2 salvos em 100
    dá 2,0%; 1 salvo em 112 dá 0,9%. UM salvamento de diferença vira "o dobro
    de desempenho", e aí qualquer ranking por post vira sorteio com cara de
    análise.

    Taxa agrupada (Σ salvos ÷ Σ alcance) não tem esse problema: cada post
    entra com o peso do alcance dele, e um grupo de 20 posts com 2 mil de
    alcance somado dá um número que significa algo.

    `minimo` é alcance somado, não número de posts — 3 posts de 800 dizem mais
    que 10 de 90.
    """
    grupos = defaultdict(lambda: [0, 0, 0])   # [soma_campo, soma_reach, posts]
    for r in linhas:
        k = chave(r)
        if not k:
            continue
        g = grupos[k]
        g[0] += int(r.get(campo, 0) or 0)
        g[1] += int(r.get("reach", 0) or 0)
        g[2] += 1
    fora = []
    for k, (soma, alc, n) in grupos.items():
        if alc >= minimo:
            fora.append((k, 1000.0 * soma / alc, soma, alc, n))
    return sorted(fora, key=lambda x: -x[1])


def olhar_intencao(linhas):
    """O que faz alguém QUERER GUARDAR — mais perto de 'o que vende' que alcance.

    ⚠️ POR QUE ISTO E NÃO ALCANCE. A tabela de fórmulas mostrou alcance
    mediano entre 109 e 134 em TODAS as fórmulas, TODAS as contas, TODAS as
    semanas. Essa uniformidade é o achado: o Instagram dá a cada post uma
    audiência de teste pequena e fixa, e nenhum dos nossos escapa dela. O hook
    não é a alavanca do alcance — ele decide o que acontece DEPOIS da
    impressão.

    Salvar é o sinal mais forte pra conteúdo de compra: quem salva pretende
    voltar. Compartilhar vem logo atrás. E são esses sinais que fazem o
    algoritmo empurrar além da audiência de teste.
    """
    total_s = sum(int(r.get("saved", 0) or 0) for r in linhas)
    total_c = sum(int(r.get("shares", 0) or 0) for r in linhas)
    total_a = sum(int(r.get("reach", 0) or 0) for r in linhas)
    if not total_a:
        _log("\n  sem alcance somado — nada a dividir")
        return
    _log(f"\n  ── INTENÇÃO (por mil impressões) ──")
    _log(f"    geral: {1000.0 * total_s / total_a:.1f} salvos/mil · "
         f"{1000.0 * total_c / total_a:.1f} compart./mil · "
         f"{total_s} salvos em {total_a:,} impressões".replace(",", "."))

    for titulo, chave in (("por FÓRMULA", lambda r: _formula(r.get("hook", ""))),
                          ("por NICHO", lambda r: r.get("nicho") or ""),
                          ("por CONTA", lambda r: r.get("conta") or "")):
        tab = _taxa_agrupada(linhas, chave)
        if not tab:
            continue
        _log(f"\n    {titulo}:")
        teto = tab[0][1]
        for k, taxa, soma, alc, n in tab:
            _log(f"      {str(k)[:20]:20} {taxa:>5.1f}/mil  "
                 f"({soma} salvos · {alc:,} alcance · {n} posts) "
                 f"{_barra(taxa, teto, 16)}".replace(",", "."))

    # ⚠️ post individual só entra com alcance que sustente a conta. Sem esse
    # piso, o "melhor post" seria sempre um com 40 de alcance e 1 salvo.
    bons = [r for r in linhas if (r.get("reach", 0) or 0) >= 200
            and int(r.get("saved", 0) or 0) >= 2]
    bons.sort(key=lambda r: -(1000.0 * (r.get("saved", 0) or 0) / (r.get("reach") or 1)))
    if bons:
        _log(f"\n    posts que mais fizeram guardar (alcance 200+, 2+ salvos):")
        for r in bons[:5]:
            taxa = 1000.0 * (r.get("saved", 0) or 0) / (r.get("reach") or 1)
            hook = (r.get("hook") or "").replace("\n", " / ")[:56]
            _log(f"      {taxa:>5.1f}/mil  {r.get('reach'):>5} alc · "
                 f"{r.get('saved')} salvos  {hook}")
    else:
        _log("\n    nenhum post com alcance 200+ e 2+ salvos — "
             "a amostra ainda não sustenta ranking por post")


def main():
    p = argparse.ArgumentParser(
        description="Alcance de uma conta ao longo do tempo. Só lê.")
    p.add_argument("--formulas", action="store_true",
                   help="alcance mediano por fórmula de hook")
    p.add_argument("--salvos", action="store_true",
                   help="o que faz GUARDAR (salvos/compart. por mil impressões)")
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

    if args.formulas:
        olhar_formulas(linhas)
        return 0

    if args.salvos:
        olhar_intencao(linhas)
        return 0

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
