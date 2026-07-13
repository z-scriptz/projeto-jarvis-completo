#!/usr/bin/env python3
# metricas_agent.py -- O LOOP DO DINHEIRO. Puxa o relatório oficial de conversão
# da Shopee (comissões que REALMENTE caíram) e SEPARA o que veio dos vídeos do
# Jarvis (via o sub_id gravado no utmContent) do que veio de outras origens.
# Escreve shared/nichos_quentes.json pro hunter priorizar o que CONVERTE.
#
# Uso (VPS):  python3 metricas_agent.py [dias]      (padrão: 30 dias)
import os
import sys
import json
import time
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent
NICHOS_QUENTES = BASE_DIR / "shared" / "nichos_quentes.json"

# Impressão digital dos NOSSOS posts (a esteira grava esses sub_ids no link;
# eles reaparecem no utmContent do relatório). Se o utmContent bate, a venda
# veio de um vídeo/post nosso — não de uma compra avulsa (tua, da família...).
#
# IMPORTANTE: "tiktok" é o sub_id do pipeline PRINCIPAL (produzir_tiktok, 3/dia —
# o coletor gera o link com sub_ids=["tiktok", termo]). Sem ele aqui, TODA venda
# de vídeo do TikTok caía em "outros" e sumia do radar do CEO (vendas_video=0).
VIDEO_TAGS = ("hunterradar", "telegramrepurpos", "telegramrepurpose",
              "hunter", "topshop", "tiktok")


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

# plano B de categoria: se a Shopee não mandar a categoria oficial (vem vazia em
# conversão pendente), inferimos pelo nome — mesma lógica do site.
try:
    try:
        from creative_engine.bio_page_builder import _inferir_categoria as _infcat
    except Exception:
        from bio_page_builder import _inferir_categoria as _infcat
except Exception:
    def _infcat(p):
        return "Outros"


def _categoria(nome: str, oficial: str) -> str:
    o = (oficial or "").strip()
    if o:
        return o
    return _infcat({"nome": nome or "", "titulo": nome or ""})


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _tags_video() -> tuple:
    """VIDEO_TAGS + marcadores extras do .env (VIDEO_SUBID_TAGS=a,b,c) — permite
    plugar fonte nova sem mexer no código."""
    extra = tuple(t.strip().lower() for t in
                  os.getenv("VIDEO_SUBID_TAGS", "").split(",") if t.strip())
    return VIDEO_TAGS + extra


def _do_video(utm: str) -> bool:
    u = (utm or "").lower()
    return any(t in u for t in _tags_video())


def _canal(utm: str) -> str:
    """1ª etiqueta do sub_id = o CANAL. 'fb-beleza-serum' → 'fb'; 'tiktok-x' →
    'tiktok'; vazio/só traços → 'direto' (venda orgânica/avulsa, sem etiqueta)."""
    u = (utm or "").strip().lower().strip("-")
    if not u:
        return "direto"
    return u.split("-")[0] or "direto"


def _pagina(ini, fim, scroll_id=None, limite=100):
    scroll = f', scrollId: "{scroll_id}"' if scroll_id else ""
    q = ("query { conversionReport(purchaseTimeStart: %d, purchaseTimeEnd: %d, "
         "limit: %d%s) { nodes { conversionId purchaseTime utmContent "
         "conversionStatus orders { orderId items { itemId itemName "
         "itemTotalCommission actualAmount qty refundAmount categoryLv1Name "
         "channelType } } } pageInfo { hasNextPage scrollId } } }"
         % (ini, fim, limite, scroll))
    return _executar_graphql(q)


def puxar_conversoes(dias: int = 30, max_paginas: int = 30) -> list:
    fim = int(time.time())
    ini = fim - dias * 86400
    itens, scroll = [], None
    for _ in range(max_paginas):
        r = _pagina(ini, fim, scroll)
        if r.get("_erro"):
            if scroll:
                break
            raise RuntimeError(r["_erro"])
        rep = (r.get("data") or {}).get("conversionReport") or {}
        for node in rep.get("nodes") or []:
            utm = node.get("utmContent") or ""
            do_video = _do_video(utm)
            t = node.get("purchaseTime")
            for order in node.get("orders") or []:
                for it in order.get("items") or []:
                    itens.append({
                        "item_id": it.get("itemId"),
                        "nome": it.get("itemName", "") or "",
                        "comissao": _num(it.get("itemTotalCommission")),
                        "valor": _num(it.get("actualAmount")),
                        "reembolso": _num(it.get("refundAmount")),
                        "qtd": int(_num(it.get("qty"))),
                        "categoria": _categoria(it.get("itemName", ""),
                                                it.get("categoryLv1Name")),
                        "utm": utm,
                        "do_video": do_video,
                        "ts": t,
                        "pedido": order.get("orderId"),
                    })
        pg = rep.get("pageInfo") or {}
        if pg.get("hasNextPage") and pg.get("scrollId"):
            scroll = pg["scrollId"]
        else:
            break
    return itens


def _agrupar(itens):
    por_cat = defaultdict(lambda: {"comissao": 0.0, "vendas": 0})
    por_prod = defaultdict(lambda: {"nome": "", "comissao": 0.0, "vendas": 0,
                                    "utm": ""})
    total = 0.0
    for i in itens:
        total += i["comissao"]
        por_cat[i["categoria"]]["comissao"] += i["comissao"]
        por_cat[i["categoria"]]["vendas"] += 1
        p = por_prod[i["item_id"]]
        p["nome"] = i["nome"]
        p["comissao"] += i["comissao"]
        p["vendas"] += 1
        p["utm"] = i["utm"]
    cats = sorted(({"categoria": c, **v} for c, v in por_cat.items()),
                  key=lambda x: x["comissao"], reverse=True)
    prods = sorted(({"item_id": k, **v} for k, v in por_prod.items()),
                   key=lambda x: x["comissao"], reverse=True)
    return round(total, 2), cats, prods


def resumir(itens: list) -> dict:
    video = [i for i in itens if i["do_video"]]
    outros = [i for i in itens if not i["do_video"]]
    tv, cats_v, prods_v = _agrupar(video)
    to, cats_o, _ = _agrupar(outros)
    return {
        "total": round(sum(i["comissao"] for i in itens), 2),
        "gmv": round(sum(i["valor"] for i in itens), 2),
        "vendas": len(itens),
        "video": {"total": tv, "vendas": len(video),
                  "categorias": cats_v, "produtos": prods_v[:15]},
        "outros": {"total": to, "vendas": len(outros), "categorias": cats_o},
    }


def _brl(v):
    return ("R$ " + f"{v:,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")


def _salvar_nichos_quentes(resumo: dict, dias: int):
    try:
        NICHOS_QUENTES.parent.mkdir(parents=True, exist_ok=True)
        v = resumo["video"]
        ranking = [c["categoria"] for c in v["categorias"] if c["comissao"] > 0]
        dados = {
            "gerado_em": int(time.time()),
            "periodo_dias": dias,
            "fonte": "conversoes_de_video",     # só o que os vídeos venderam
            "comissao_video": v["total"],
            "ranking_categorias": ranking,       # a mais lucrativa primeiro
            "por_categoria": v["categorias"],
            "top_produtos": v["produtos"],
        }
        NICHOS_QUENTES.write_text(
            json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        print(f"(não consegui salvar nichos_quentes: {str(e)[:80]})")
        return False


def main():
    dias = 30
    for arg in sys.argv[1:]:
        if arg.isdigit():
            dias = max(1, int(arg))
            break

    print(f"\n💰 COMISSÕES — últimos {dias} dias")
    print("=" * 52)
    try:
        itens = puxar_conversoes(dias)
    except Exception as e:
        print(f"ERRO ao puxar o relatório: {str(e)[:200]}")
        return 1

    # DIAGNÓSTICO: lista os utmContent crus + se cada um é reconhecido como vídeo.
    # Serve pra CRAVAR se existe venda de TikTok caindo em "outros" por engano.
    if "--utms" in sys.argv:
        from collections import Counter
        print("\n🔬 utmContent das conversões (marcador → nº itens · do_video?):")
        cont = Counter((i["utm"] or "(vazio)") for i in itens)
        if not cont:
            print("   (nenhuma conversão no período — sem venda ainda, tracking ok)")
        for utm, n in cont.most_common():
            print(f"   {'✅VÍDEO' if _do_video(utm) else '⚪outros'}  {utm[:60]:<60} · {n}")
        print(f"\n   tags reconhecidas como vídeo: {_tags_video()}")
        return 0

    if not itens:
        print("Nenhuma comissão no período. O encanamento está pronto —")
        print("quando as vendas entrarem, rode de novo. 🌱")
        _salvar_nichos_quentes(resumir(itens), dias)
        return 0

    r = resumir(itens)
    v, o = r["video"], r["outros"]
    print(f"\n  Comissão TOTAL : {_brl(r['total'])}  ({r['vendas']} vendas · "
          f"GMV {_brl(r['gmv'])})")
    print(f"    ├─ 💚 DOS VÍDEOS : {_brl(v['total'])}  ({v['vendas']} vendas)")
    print(f"    └─ ⚪ Outras     : {_brl(o['total'])}  ({o['vendas']} vendas)")

    # ATRIBUIÇÃO POR CANAL (1ª etiqueta do sub_id): fb / ig / tiktok / hunter / direto
    from collections import defaultdict
    por_canal = defaultdict(lambda: {"comissao": 0.0, "vendas": 0})
    for i in itens:
        c = por_canal[_canal(i["utm"])]
        c["comissao"] += i["comissao"]
        c["vendas"] += 1
    print("\n  📡 POR CANAL (de onde veio a venda):")
    for canal, d in sorted(por_canal.items(), key=lambda x: -x[1]["comissao"]):
        rotulo = "direto/orgânico (sem etiqueta)" if canal == "direto" else canal
        print(f"     {rotulo:<32} {_brl(d['comissao']):>10}  · {d['vendas']} venda(s)")

    if v["vendas"]:
        print("\n  🏆 CATEGORIAS que os VÍDEOS venderam:")
        for c in v["categorias"]:
            print(f"     {c['categoria']:<22} {_brl(c['comissao']):>10}  "
                  f"· {c['vendas']} venda(s)")
        print("\n  🥇 PRODUTOS que os VÍDEOS venderam:")
        for p in v["produtos"][:8]:
            print(f"     {_brl(p['comissao']):>10}  {p['nome'][:50]}")
    else:
        print("\n  💚 Nenhuma venda ATRIBUÍDA aos vídeos ainda.")
        print("     (as vendas de hoje vieram de outras origens — normal no")
        print("      começo; o vídeo→clique→compra leva alguns dias). O")
        print("      rastreamento por sub_id já está ligado pra capturar. 🌱")
        if o["categorias"]:
            print("\n  ⚪ Pra referência, o que VENDEU (qualquer origem):")
            for c in o["categorias"][:6]:
                print(f"     {c['categoria']:<22} {_brl(c['comissao']):>10}")

    if _salvar_nichos_quentes(r, dias):
        print("\n✅ nichos_quentes.json atualizado (só conversões de vídeo).")
        print("   Próximo passo: o hunter priorizar essas categorias. 🔁")
    return 0


if __name__ == "__main__":
    sys.exit(main())
