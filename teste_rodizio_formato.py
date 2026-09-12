#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_rodizio_formato.py -- nenhuma conta pode ter o formato decidido de antemão
#
# POR QUE ISTO EXISTE (12/09/2026)
# ────────────────────────────────
# O Dre rodou 200 sorteios por conta na VPS:
#
#   @topshoppet_      lista 59 · erros 40 · mitos 31 · passo 29 · a_d 29 · hist 12
#   @topshoptech_     mitos 200
#   @topshopcasa_     mitos 200
#   @topshopmoda_     mitos 200
#   @topshopbeauty._  mitos 200
#   @topshop.__       mitos 200
#
# **200 de 200 não é acaso, é aritmética.** A cobertura era PORTEIRA: todo
# formato abaixo de COBERTURA furava a fila, e entre eles só os empatados no
# mínimo viravam candidatos. Com o mínimo único, `candidatos` tem UM elemento —
# e `random.choices` de um elemento é `return`.
#
# E a contagem é POR CONTA: as cinco chegaram nisso isoladas, no mesmo dia.
# Seis perfis, mesmo formato, ganchos quase idênticos:
#
#   tech    4 mitos que você ainda acredita sobre tecnologia
#   beleza  Mitos sobre os pés que você ainda acredita
#   moda    Coisas da moda que você acreditava ser verdade
#   geral   4 mitos que você ainda acredita sobre sua energia
#
# 📌 Quem segue duas contas vê o mesmo post duas vezes. É o *"parecendo um
# robozinho"* que ele reclamou nas RESPOSTAS, agora no CONTEÚDO — e a causa é a
# mesma das duas vezes: escolha sem memória do que já saiu.
#
# ⚠️ E O `--formatos` NÃO MOSTRAVA NADA DISSO. Ele somava as seis contas e
# imprimia o peso cru: "mitos 12 → 11%", quando a chance real era 100% em cinco.
# Relatório que mostra a intenção em vez do efeito é como não ter relatório.
#
#   python3 teste_rodizio_formato.py
import collections
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import carrossel_brain as C  # noqa: E402

ok = falhou = 0


def checa(desc, cond, extra=""):
    global ok, falhou
    if cond:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}" + (f"\n      {extra}" if extra else ""))


def com_ledger(linhas):
    """Troca o ledger por um sintético. Devolve o original pra restaurar."""
    orig = C._ledger
    C._ledger = lambda: list(linhas)
    return orig


def dist(conta, n=3000):
    return collections.Counter(C.escolher_formato(conta)[0] for _ in range(n))


# o estado exato da VPS em 12/09: mitos em 1, todo o resto já coberto
VPS = ([{"conta": "@topshopmoda_", "formato": "mitos", "data": "2026-09-11"}] +
       [{"conta": "@topshopmoda_", "formato": f, "data": "2026-09-01"}
        for f in ("lista", "erros", "antes_depois", "passo_a_passo", "historia")
        for _ in range(3)])

print("\n── ⚠️⚠️ O DEFEITO: 200 de 200 ──")
_orig = com_ledger(VPS)
try:
    d = dist("@topshopmoda_")
    top, n_top = d.most_common(1)[0]
    checa("⚠️ NENHUM formato leva tudo", n_top < 3000,
          f"{top} saiu {n_top}/3000 — a escolha voltou a ser decidida antes "
          f"do sorteio, igual em todas as contas")
    checa("⚠️ o mais provável fica abaixo de 60%", n_top < 1800,
          f"{top}={100*n_top/3000:.0f}% — {d.most_common()}")
    checa("pelo menos 4 formatos diferentes aparecem", len(d) >= 4,
          str(d.most_common()))

    print("\n   ── mas a cobertura continua EMPURRANDO ──")
    # sem o empurrão o mitos (peso 12) ficaria em ~12%; com ele tem que subir
    cru = 100.0 * C._pesos()["mitos"] / sum(p for p in C._pesos().values() if p > 0)
    real = 100.0 * d["mitos"] / 3000
    checa(f"o descoberto sai mais que o peso cru ({real:.0f}% > {cru:.0f}%)",
          real > cru * 1.4, f"cobertura virou decoração: {d.most_common()}")
    checa("…e ainda assim não monopoliza", real < 60, f"{real:.0f}%")
finally:
    C._ledger = _orig

print("\n── ⚠️ A CONTA 2 TEM QUE VER O QUE A CONTA 1 ACABOU DE POSTAR ──")
# o ciclo publica em sequência (90s entre contas) e o `registrar()` escreve na
# publicação — então o ledger de HOJE é o canal que já existe. Sem ele, seis
# contas decidem no escuro e repetem a mesma coisa.
import time  # noqa: E402
_hoje = time.strftime("%Y-%m-%d")
_orig = com_ledger(VPS)
try:
    antes = 100.0 * dist("@topshopmoda_")["mitos"] / 3000
finally:
    C._ledger = _orig
_orig = com_ledger(VPS + [{"conta": "@topshoptech_", "formato": "mitos",
                           "data": _hoje} for _ in range(3)])
try:
    depois = 100.0 * dist("@topshopmoda_")["mitos"] / 3000
    checa(f"3 posts de 'mitos' hoje derrubam a chance ({antes:.0f}% → {depois:.0f}%)",
          depois < antes * 0.7,
          "a rede publicou o formato 3x e a 4ª conta não ficou sabendo")
    checa("mas não zera — amortece, não proíbe", depois > 0)
finally:
    C._ledger = _orig

print("\n── ⚠️ O SALVAMENTO MEDIDO PARTICIPA MESMO COM ALGUÉM DESCOBERTO ──")
# ⚠️ ESTE ERA O BURACO GRANDE: a fase 2 só rodava quando NINGUÉM estava abaixo
# da cobertura — ou seja, em 1 das 6 contas. Todo o ledger, os 215 posts, o
# cuidado com média pooled: não chegavam a influenciar escolha nenhuma.
#
# ⚠️ E A MÉDIA É SÓ DOS FORMATOS MEDIDOS. Com UM formato com alcance no ledger
# ele É a média, então `t/media = 1.0` e o fator não inclina nada — o primeiro
# cenário deste teste tinha só `historia` medido e acusou o código de errado. A
# medição só começa a mexer na distribuição com DOIS ou mais formatos medidos.
_medido = VPS + [
    {"conta": "@topshopmoda_", "formato": "historia", "data": "2026-09-02",
     "reach": 10000, "saved": 400},        # 40/mil
    {"conta": "@topshopmoda_", "formato": "erros", "data": "2026-09-02",
     "reach": 10000, "saved": 100},        # 10/mil — média 25, historia ×1.6
]
_orig = com_ledger(_medido)
try:
    _a, _d, _ = C._pesos_ajustados("@topshopmoda_")
    checa("⚠️ o fator de salvamento sai de 1.0 mesmo com 'mitos' descoberto",
          _d["historia"]["salvamento"] > 1.0,
          f"historia={_d['historia']} — a fase 2 continua inalcançável")
    checa("o teto de 2.0 no ajuste continua valendo",
          _d["historia"]["salvamento"] <= 2.0, str(_d["historia"]))
    checa("e o motivo impresso cita o salvamento",
          any("salvamento" in C.escolher_formato("@topshopmoda_")[1]
              for _ in range(60)))
finally:
    C._ledger = _orig

print("\n── o motivo explica a decisão (senão não dá pra corrigir depois) ──")
_orig = com_ledger(VPS)
try:
    _f, _m = C.escolher_formato("@topshopmoda_")
    checa("o motivo diz o peso base", "peso" in _m, _m)
    checa("…e a chance final em %", "%" in _m, _m)
    checa("cobertura aparece quando está agindo",
          any("cobertura" in C.escolher_formato("@topshopmoda_")[1]
              for _ in range(60)))
finally:
    C._ledger = _orig

print("\n── nada disso pode derrubar a esteira ──")
checa("conta desconhecida não quebra", bool(C.escolher_formato("@nao_existe")[0]))
checa("conta vazia não quebra", bool(C.escolher_formato("")[0]))
_pesos_reais = C._pesos
C._pesos = lambda: {f: 0 for f in C.FORMATOS}
try:
    checa("todos os pesos zerados → cai na lista",
          C.escolher_formato("@x") == ("lista",
                                       "todos os pesos zerados no .env — "
                                       "caindo na lista"))
finally:
    C._pesos = _pesos_reais
_orig = com_ledger([{"formato": "mitos"}, {"lixo": 1}, {"data": _hoje}])
try:
    checa("linha de ledger sem 'data' não quebra o de-hoje",
          isinstance(C._formatos_de_hoje(), dict))
finally:
    C._ledger = _orig

print("\n── ⚠️ O DEFEITO ADORMECIDO: 'comparacao' nunca incrementa ──")
# Quando não há par comparável, o `montar_plano` faz `formato = "lista"` e o
# plano vai pro ledger COMO lista. O `comparacao` fica em 0 pra sempre — e num
# dia em que CARR_PESO_COMPARACAO deixar de ser 0, ele passa a ser o eterno
# descoberto. Hoje dorme porque o peso é 0 no .env da VPS; o código aqui tem 10.
_src = (BASE / "carrossel_brain.py").read_text("utf-8")
checa("a troca comparacao→lista ainda está lá (documentando o risco)",
      'formato, cfg = "lista", FORMATOS["lista"]' in _src)
checa("⚠️ e o empurrão limita o estrago se ela acordar",
      C.COBERTURA_FORCA < 10,
      "com empurrão alto demais um zero permanente volta a monopolizar")

print(f"\n{'='*66}\n   {ok} passou · {falhou} falhou\n{'='*66}")
raise SystemExit(1 if falhou else 0)
