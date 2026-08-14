#!/usr/bin/env python3
# posts_ledger.py -- O DIÁRIO DO JARVIS. Cada vídeo produzido vira uma linha aqui
# (produto, hook, categoria, item_id, sub_id, horário). É a FUNDAÇÃO do
# aprendizado: depois a gente cruza este diário com o relatório de comissões
# (por item_id) e descobre QUAL hook / categoria / horário realmente converte.
# A/B de hooks, horário ótimo, score viral e "CEO IA" nascem todos daqui.
#
# Escreve em shared/posts_ledger.jsonl (1 JSON por linha — append-only, à prova
# de corrupção; nunca lança exceção pra não quebrar a produção do vídeo).
#
# Ver resumo:  python3 posts_ledger.py
import os
import re
import sys
import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LEDGER = BASE_DIR / "shared" / "posts_ledger.jsonl"


def _item_id(url: str) -> str:
    """Extrai o itemId da URL do produto (é a chave pra cruzar com a comissão)."""
    m = re.search(r"i\.(\d+)\.(\d+)", url or "")
    if m:
        return m.group(2)
    pares = re.findall(r"/(\d+)/(\d+)", (url or "").split("?")[0])
    return pares[-1][1] if pares else ""


def registrar(produto: str = "", link: str = "", url_shopee: str = "",
              categoria: str = "", hook: str = "", legenda: str = "",
              slug: str = "", sub_ids=None, plataforma: str = "",
              extra: dict = None) -> bool:
    """Anexa 1 post ao diário. Best-effort: qualquer erro é engolido (o diário
    NUNCA pode derrubar a produção do vídeo)."""
    try:
        agora = time.time()
        lt = time.localtime(agora)
        reg = {
            "ts": int(agora),
            "data": time.strftime("%Y-%m-%d", lt),
            "hora": lt.tm_hour,
            "produto": produto or "",
            "categoria": categoria or "",
            "hook": hook or "",
            "legenda": (legenda or "")[:400],
            "item_id": _item_id(url_shopee or link),
            "link": link or "",
            "sub_ids": list(sub_ids or []),
            "slug": slug or "",
            "plataforma": plataforma or "",
        }
        if extra:
            reg.update(extra)
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def carregar() -> list:
    """Lê o diário inteiro (lista de dicts). Ignora linhas corrompidas."""
    regs = []
    if not LEDGER.exists():
        return regs
    for linha in LEDGER.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            regs.append(json.loads(linha))
        except Exception:
            continue
    return regs


def _resumo():
    regs = carregar()
    print(f"\n📓 POSTS LEDGER — {LEDGER}")
    print("=" * 52)
    if not regs:
        print("Vazio ainda. Cada vídeo novo que o Jarvis produzir vira 1 linha.")
        print("(é a base do A/B de hooks, horário ótimo e score viral)")
        return 0
    print(f"  {len(regs)} posts registrados")
    from collections import Counter
    cats = Counter(r.get("categoria") or "?" for r in regs)
    horas = Counter(r.get("hora") for r in regs)
    print("\n  Por categoria:")
    for c, n in cats.most_common():
        print(f"    {c:<14} {n}")
    print("\n  Por horário (top 5):")
    for h, n in horas.most_common(5):
        print(f"    {h:02d}h   {n}")
    print("\n  Últimos 5 posts:")
    for r in regs[-5:]:
        print(f"    [{r.get('data')} {r.get('hora'):02d}h] "
              f"{(r.get('produto') or '?')[:40]}  ·  hook: "
              f"{(r.get('hook') or '')[:40]}")
    return 0


if __name__ == "__main__":
    sys.exit(_resumo())
