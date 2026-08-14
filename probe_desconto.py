#!/usr/bin/env python3
# probe_desconto.py -- SONDA (só leitura). Descobre se a API de afiliado da
# Shopee devolve PREÇO ORIGINAL / % de desconto além do priceMin que a gente já
# usa. Se devolver, o riscado do card ("de R$ 149,90") passa a ser o desconto
# REAL da loja em vez do maior preço que a gente observou no histórico.
#
# POR QUE UMA SONDA, e não simplesmente pedir o campo: GraphQL rejeita a query
# INTEIRA quando um campo não existe. Pedir um campo incerto dentro da query do
# health-check derrubaria o deploy do site. Aqui cada candidato vai numa query
# separada e isolada — se falhar, falha só ele.
#
# Não escreve nada, não altera nada. Roda em ~/jarvis:
#     python3 probe_desconto.py                    # usa o 1º produto da fila
#     python3 probe_desconto.py --item 123456789 --shop 987654
#     python3 probe_desconto.py --link https://s.shopee.com.br/xxxx

import os
import re
import sys
import json
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
FILA = BASE_DIR / "shared" / "produtos_fila.json"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"

# Nomes plausíveis pro preço "de" / desconto. A doc da API muda entre versões,
# então a sonda testa um por um e reporta quais o servidor aceitou.
CANDIDATOS = [
    "priceDiscountRate",
    "priceBeforeDiscount",
    "originalPrice",
    "priceMin",           # controle: este a gente SABE que existe
    "discount",
    "listPrice",
    "priceMax",           # controle
]


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
            chave, _, valor = linha.partition("=")
            chave, valor = chave.strip(), valor.strip().strip('"').strip("'")
            if chave and chave not in os.environ:
                os.environ[chave] = valor
        break


def _graphql():
    try:
        from integrations.shopee_affiliate import _executar_graphql
        return _executar_graphql
    except Exception:
        from shopee_affiliate import _executar_graphql
        return _executar_graphql


def _ids_do_link(link: str):
    import requests
    r = requests.get(link, allow_redirects=True, timeout=15,
                     headers={"User-Agent": _UA})
    final = r.url or ""
    m = re.search(r"i\.(\d+)\.(\d+)", final)
    if m:
        return m.group(1), m.group(2)
    pares = re.findall(r"/(\d+)/(\d+)", final.split("?")[0])
    return pares[-1] if pares else (None, None)


def _primeiro_da_fila():
    try:
        fila = json.loads(FILA.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"não consegui ler {FILA}: {e}")
        return None, None
    for item in fila:
        if isinstance(item, dict) and item.get("link"):
            if (item.get("plataforma") or "shopee").lower() != "shopee":
                continue
            print(f"produto de teste: {item.get('produto', '?')[:50]}")
            try:
                return _ids_do_link(item["link"])
            except Exception as e:
                print(f"   não resolvi o link ({e}) — tento o próximo")
    return None, None


def _testar(gq, item_id, campo):
    """Uma query minúscula só com itemId + o campo candidato."""
    q = ("query { productOfferV2(itemId: " + str(item_id) +
         ") { nodes { itemId " + campo + " } } }")
    resp = gq(q)
    if resp.get("_erro"):
        return "erro", str(resp["_erro"])[:110]
    if resp.get("errors"):
        msg = str(resp["errors"])[:110]
        return "rejeitado", msg
    try:
        nodes = (((resp.get("data") or {}).get("productOfferV2") or {})
                 .get("nodes") or [])
        if not nodes:
            return "vazio", "query aceita, mas sem nodes"
        return "aceito", repr(nodes[0].get(campo))
    except Exception as e:
        return "erro", str(e)[:110]


def main():
    ap = argparse.ArgumentParser(description="Sonda campos de desconto da Shopee")
    ap.add_argument("--item", default="", help="itemId direto")
    ap.add_argument("--shop", default="", help="shopId (não é usado na query, só informativo)")
    ap.add_argument("--link", default="", help="link de afiliado ou do produto")
    a = ap.parse_args()

    _carregar_env()
    try:
        gq = _graphql()
    except Exception as e:
        print(f"API de afiliado indisponível: {e}")
        return 2

    item_id = a.item
    if not item_id and a.link:
        _, item_id = _ids_do_link(a.link)
    if not item_id:
        _, item_id = _primeiro_da_fila()
    if not item_id:
        print("não achei nenhum itemId pra testar — passe --item ou --link")
        return 1

    print(f"\nsondando itemId={item_id}\n")
    aceitos = []
    for campo in CANDIDATOS:
        estado, detalhe = _testar(gq, item_id, campo)
        marca = {"aceito": "✅", "rejeitado": "❌", "vazio": "⚠️ ", "erro": "⚠️ "}[estado]
        print(f"  {marca} {campo:22} {estado:10} {detalhe}")
        if estado == "aceito":
            aceitos.append(campo)

    print("\n" + "-" * 60)
    novos = [c for c in aceitos if c not in ("priceMin", "priceMax")]
    if novos:
        print(f"A API aceita: {', '.join(novos)}")
        print("Dá pra usar o desconto REAL da loja no riscado do card.")
        print("Me manda esta saída que eu ligo em obter_dados_produto.")
    elif "priceMin" in aceitos:
        print("Só os campos que já usamos existem — nenhum preço 'de' na API.")
        print("O riscado continua saindo do histórico (maior preço observado).")
    else:
        print("Nem os campos conhecidos passaram — provavelmente é credencial")
        print("ou rede, não ausência de campo. Confere SHOPEE_APP_ID/SECRET.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
