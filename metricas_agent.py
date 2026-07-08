#!/usr/bin/env python3
# metricas_agent.py -- O LOOP DO DINHEIRO. Puxa o relatório oficial de conversão
# da Shopee (comissões que REALMENTE caíram), mostra quanto você ganhou e —
# o mais importante — DESCOBRE qual categoria/produto converte, escrevendo
# shared/nichos_quentes.json pro hunter passar a caçar mais do que dá lucro.
#
# Uso (VPS):  python3 metricas_agent.py [dias]      (padrão: 30 dias)
import os
import re
import sys
import json
import time
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent
NICHOS_QUENTES = BASE_DIR / "shared" / "nichos_quentes.json"


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

# reusa a MESMA categorização do site (consistência total)
try:
    try:
        from creative_engine.bio_page_builder import _inferir_categoria
    except Exception:
        from bio_page_builder import _inferir_categoria
except Exception:
    def _inferir_categoria(p):   # fallback se o builder não importar
        return "Outros"


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _pagina(ini, fim, scroll_id=None, limite=100):
    scroll = f', scrollId: "{scroll_id}"' if scroll_id else ""
    q = ("query { conversionReport(purchaseTimeStart: %d, purchaseTimeEnd: %d, "
         "limit: %d%s) { nodes { conversionId purchaseTime orders { orderId "
         "items { itemName itemId shopId itemTotalCommission actualAmount } } } "
         "pageInfo { hasNextPage scrollId } } }" % (ini, fim, limite, scroll))
    return _executar_graphql(q)


def puxar_conversoes(dias: int = 30, max_paginas: int = 30) -> list:
    """Lista achatada de itens vendidos (comissão que caiu) no período."""
    fim = int(time.time())
    ini = fim - dias * 86400
    itens, scroll = [], None
    for _ in range(max_paginas):
        r = _pagina(ini, fim, scroll)
        if r.get("_erro"):
            if scroll:      # erro só na paginação → fica com o que já temos
                break
            raise RuntimeError(r["_erro"])
        rep = (r.get("data") or {}).get("conversionReport") or {}
        for node in rep.get("nodes") or []:
            t = node.get("purchaseTime")
            for order in node.get("orders") or []:
                for it in order.get("items") or []:
                    itens.append({
                        "item_id": it.get("itemId"),
                        "nome": it.get("itemName", "") or "",
                        "comissao": _num(it.get("itemTotalCommission")),
                        "valor": _num(it.get("actualAmount")),
                        "ts": t,
                        "pedido": order.get("orderId"),
                    })
        pg = rep.get("pageInfo") or {}
        if pg.get("hasNextPage") and pg.get("scrollId"):
            scroll = pg["scrollId"]
        else:
            break
    return itens


def resumir(itens: list) -> dict:
    total_com = sum(i["comissao"] for i in itens)
    total_gmv = sum(i["valor"] for i in itens)
    n = len(itens)

    por_cat = defaultdict(lambda: {"comissao": 0.0, "vendas": 0, "gmv": 0.0})
    por_prod = defaultdict(lambda: {"nome": "", "comissao": 0.0, "vendas": 0})
    for i in itens:
        cat = _inferir_categoria({"nome": i["nome"], "titulo": i["nome"]})
        por_cat[cat]["comissao"] += i["comissao"]
        por_cat[cat]["vendas"] += 1
        por_cat[cat]["gmv"] += i["valor"]
        pid = i["item_id"]
        por_prod[pid]["nome"] = i["nome"]
        por_prod[pid]["comissao"] += i["comissao"]
        por_prod[pid]["vendas"] += 1

    cats = sorted(
        ({"categoria": c, **v} for c, v in por_cat.items()),
        key=lambda x: x["comissao"], reverse=True)
    prods = sorted(
        ({"item_id": p, **v} for p, v in por_prod.items()),
        key=lambda x: x["comissao"], reverse=True)
    return {
        "total_comissao": round(total_com, 2),
        "total_gmv": round(total_gmv, 2),
        "vendas": n,
        "por_categoria": cats,
        "top_produtos": prods[:15],
    }


def _brl(v):
    return ("R$ " + f"{v:,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")


def _salvar_nichos_quentes(resumo: dict, dias: int):
    """Escreve o que o hunter vai usar pra priorizar o que CONVERTE."""
    try:
        NICHOS_QUENTES.parent.mkdir(parents=True, exist_ok=True)
        ranking = [c["categoria"] for c in resumo["por_categoria"]
                   if c["comissao"] > 0]
        dados = {
            "gerado_em": int(time.time()),
            "periodo_dias": dias,
            "ranking_categorias": ranking,          # mais lucrativa primeiro
            "por_categoria": resumo["por_categoria"],
            "top_produtos": resumo["top_produtos"],
        }
        NICHOS_QUENTES.write_text(
            json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        print(f"(não consegui salvar nichos_quentes: {str(e)[:80]})")
        return False


def main():
    dias = 30
    if len(sys.argv) > 1:
        try:
            dias = max(1, int(sys.argv[1]))
        except ValueError:
            pass

    print(f"\n💰 RELATÓRIO DE COMISSÕES — últimos {dias} dias")
    print("=" * 52)
    try:
        itens = puxar_conversoes(dias)
    except Exception as e:
        print(f"ERRO ao puxar o relatório: {str(e)[:200]}")
        return 1

    if not itens:
        print("Nenhuma comissão no período ainda. O encanamento está pronto —")
        print("quando as vendas entrarem, é só rodar de novo. 🌱")
        return 0

    r = resumir(itens)
    print(f"\n  Comissão total : {_brl(r['total_comissao'])}")
    print(f"  Vendas         : {r['vendas']}")
    print(f"  GMV (vendido)  : {_brl(r['total_gmv'])}")
    if r["vendas"]:
        print(f"  Comissão média : {_brl(r['total_comissao'] / r['vendas'])}/venda")

    print("\n  🏆 POR CATEGORIA (o que te dá dinheiro):")
    for c in r["por_categoria"]:
        print(f"    {c['categoria']:<11} {_brl(c['comissao']):>11}  "
              f"· {c['vendas']} venda(s)")

    print("\n  🥇 TOP PRODUTOS:")
    for p in r["top_produtos"][:8]:
        print(f"    {_brl(p['comissao']):>10}  {p['nome'][:52]}")

    if _salvar_nichos_quentes(r, dias):
        print(f"\n✅ nichos_quentes.json atualizado — o hunter agora sabe o que")
        print("   converte (categoria mais lucrativa primeiro). Loop fechado. 🔁")
    return 0


if __name__ == "__main__":
    sys.exit(main())
