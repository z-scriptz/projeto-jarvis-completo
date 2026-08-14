#!/usr/bin/env python3
# probe_subid.py -- SONDA (só leitura). Descobre ONDE o relatório de conversão
# guarda o sub_id / utm (a impressão digital do nosso post), pra separar a
# comissão DOS VÍDEOS da comissão de outras compras. Roda em ~/jarvis.
import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _carregar_env():
    for cand in (BASE_DIR / ".env", Path(".env")):
        if not cand.exists():
            continue
        for linha in cand.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            k, _, v = linha.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        break


_carregar_env()
try:
    from integrations.shopee_affiliate import _executar_graphql
except Exception:
    from shopee_affiliate import _executar_graphql

ALVOS = ("sub", "utm", "channel", "campaign", "custom", "attribution", "click")

# 1) Lista TODOS os tipos e seus campos; filtra os que parecem sub_id/utm.
q = "{ __schema { types { name kind fields { name } } } }"
r = _executar_graphql(q)
tipos = (((r.get("data") or {}).get("__schema") or {}).get("types") or [])

print("=== CAMPOS candidatos a sub_id/utm no schema ===")
achou = False
for t in tipos:
    nome_tipo = t.get("name") or ""
    if nome_tipo.startswith("__"):
        continue
    campos = [f.get("name") for f in (t.get("fields") or [])]
    hits = [c for c in campos if c and any(a in c.lower() for a in ALVOS)]
    if hits:
        achou = True
        print(f"\n  tipo {nome_tipo}:")
        for h in hits:
            print(f"     - {h}")

if not achou:
    print("(introspecção não revelou campos óbvios — dump cru abaixo)")
    print(json.dumps(r, ensure_ascii=False)[:1500])

# 2) Mostra os campos COMPLETOS dos tipos do conversionReport (pra eu ver tudo).
print("\n\n=== Campos completos dos tipos de conversão/pedido/item ===")
for t in tipos:
    nome_tipo = (t.get("name") or "")
    low = nome_tipo.lower()
    if any(k in low for k in ("conversion", "order", "item")) and not nome_tipo.startswith("__"):
        campos = [f.get("name") for f in (t.get("fields") or [])]
        if campos:
            print(f"\n  {nome_tipo}: {campos}")

print("\n>>> Cola TUDO isso pro Claude. Só leitura, não mudou nada.")
