#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# diff_roteador.py -- o que MUDA de conta com a regra nova, na fila de verdade
#
# POR QUE ISSO EXISTE (05/09/2026)
# ────────────────────────────────
# Troquei o desempate do roteador de ORDEM DAS LISTAS para ESPECIFICIDADE (o
# termo mais longo vence), porque 'sabonete' estava ganhando de 'saboneteira'.
# Escrevi 18 testes e todos passaram — mas os 18 casos fui EU que escolhi.
#
# Já apanhei disso aqui: o `limpar_inbox` tinha "21% de falso positivo" nos meus
# exemplos e 41% nos dados do Dre. Amostra que eu monto não mede nada; mede o
# que eu já esperava.
#
# Então este script roda as DUAS regras nos nomes reais do inbox e mostra só o
# que muda de conta. Não chama API, não escreve nada, não altera a fila.
#
#   .venv/bin/python diff_roteador.py
#   .venv/bin/python diff_roteador.py --tudo    # lista todas as mudanças
import re
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import roteador_contas as R          # noqa: E402

BASE = Path(__file__).resolve().parent
PASTAS = [BASE / "inbox_tiktok", BASE / "inbox_tiktok" / "_produzidos"]


# ── a regra VELHA, reconstruída aqui pra não depender de git ──────────────────
def _compilar_velho(palavras):
    alt = sorted((R._sem_acento(p.lower()) for p in palavras), key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(re.escape(p) for p in alt) + r")")


_V_PET = _compilar_velho(R._PET)
_V_BELEZA = _compilar_velho(R._BELEZA)
_V_TECH = _compilar_velho(R._TECH)
_V_CASA = _compilar_velho(R._CASA)
_V_MODA = _compilar_velho(R._MODA)


def nicho_velho(texto: str) -> str:
    """Ordem das listas decide, fim da palavra livre, sem veto de bicho."""
    for nome, rx in (("pet", _V_PET), ("beleza", _V_BELEZA), ("tech", _V_TECH),
                     ("casa", _V_CASA), ("moda", _V_MODA)):
        if rx.search(texto):
            return nome
    return ""


def main() -> int:
    tudo = "--tudo" in sys.argv[1:]

    nomes = []
    for pasta in PASTAS:
        if not pasta.exists():
            continue
        for pj in pasta.glob("*/plano.json"):
            try:
                info = json.loads(pj.read_text(encoding="utf-8"))
            except Exception:
                continue
            n = (info.get("produto") or info.get("termo") or "").strip()
            if n:
                nomes.append(n)

    if not nomes:
        print("❌ nenhum plano.json encontrado — rode na VPS, dentro de ~/jarvis")
        return 1

    print(f"📦 {len(nomes)} nome(s) de produto na fila\n")

    mudou = []
    antes = {}
    depois = {}
    for n in nomes:
        t = R._sem_acento(n.lower())
        a, d = nicho_velho(t), R._por_palavra_chave(t)
        antes[a] = antes.get(a, 0) + 1
        depois[d] = depois.get(d, 0) + 1
        if a != d:
            mudou.append((a, d, n))

    def linha(rotulo, cont):
        partes = " · ".join(f"{k or '(IA)'}={v}" for k, v in sorted(cont.items()))
        print(f"   {rotulo:8} {partes}")

    print("── distribuição por conta ──")
    linha("ANTES", antes)
    linha("DEPOIS", depois)

    pct = len(mudou) / len(nomes) * 100
    print(f"\n── mudaram de conta: {len(mudou)} de {len(nomes)} ({pct:.1f}%) ──")
    if not mudou:
        print("   nenhuma. A regra nova classifica esta fila igual à velha.")
        return 0

    # agrupa por transição: é aí que dá pra ver se a mudança tem SENTIDO ou se
    # foi um efeito colateral que eu não previ.
    por_par = {}
    for a, d, n in mudou:
        por_par.setdefault((a, d), []).append(n)

    for (a, d), itens in sorted(por_par.items(), key=lambda kv: -len(kv[1])):
        print(f"\n   {a or '(IA)'} → {d or '(IA)'}   ({len(itens)})")
        for n in (itens if tudo else itens[:6]):
            print(f"      • {n[:72]}")
        if not tudo and len(itens) > 6:
            print(f"      … +{len(itens) - 6} (use --tudo pra ver todas)")

    print(f"\n⚠️ OLHE AS TRANSIÇÕES ACIMA. Cada linha é um produto que vai pra")
    print(f"   OUTRA conta a partir de agora. Se alguma pilha parecer errada,")
    print(f"   o defeito é meu e eu conserto antes da próxima produção.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
