#!/usr/bin/env python3
# probe_conversao.py -- SONDA (não altera nada). Descobre o formato do relatório
# de conversão da API de afiliado da Shopee PRA TUA CONTA, pra eu construir o
# "loop do dinheiro" (o Jarvis saber qual post virou comissão) com o schema certo.
# Roda em ~/jarvis:  python3 probe_conversao.py
import os
import sys
import json
import time
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


def _mostrar(titulo, resp, limite=1600):
    print("\n" + "=" * 60)
    print(titulo)
    print("=" * 60)
    txt = json.dumps(resp, ensure_ascii=False, indent=2)
    print(txt[:limite] + ("\n... (cortado)" if len(txt) > limite else ""))


# 1) INTROSPECÇÃO: quais queries a API expõe? (revela o nome exato do relatório)
q_intro = "{ __schema { queryType { fields { name description } } } }"
r1 = _executar_graphql(q_intro)
nomes = []
try:
    campos = (((r1.get("data") or {}).get("__schema") or {})
              .get("queryType") or {}).get("fields") or []
    nomes = [c.get("name") for c in campos]
except Exception:
    pass
if nomes:
    print("QUERIES DISPONÍVEIS NA API:")
    for n in nomes:
        print("  -", n)
    # candidatos de relatório de conversão/pedido
    rel = [n for n in nomes if any(t in (n or "").lower()
           for t in ("conversion", "report", "order", "valid", "commission"))]
    print("\nCANDIDATOS a relatório de comissão:", rel or "(nenhum óbvio)")
else:
    _mostrar("Introspecção (pode estar desabilitada) — resposta crua:", r1)

# 2) TENTATIVA de conversionReport nos últimos 14 dias (formato mais comum)
fim = int(time.time())
ini = fim - 14 * 24 * 3600
q_conv = (
    "query { conversionReport(purchaseTimeStart: %d, purchaseTimeEnd: %d, "
    "limit: 5) { nodes { conversionId purchaseTime "
    "orders { orderId items { itemName itemId shopId "
    "itemTotalCommission actualAmount } } } "
    "pageInfo { hasNextPage scrollId } } }" % (ini, fim)
)
r2 = _executar_graphql(q_conv)
_mostrar("TENTATIVA conversionReport (14 dias) — resposta crua:", r2)

print("\n>>> Cola TODA essa saída pro Claude. É só leitura, não mudou nada.")
