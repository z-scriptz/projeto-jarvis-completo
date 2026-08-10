#!/usr/bin/env python3
# probe_imagens.py -- a API de afiliado da Shopee devolve MAIS DE UMA imagem?
#
# POR QUE ESTE ARQUIVO EXISTE (10/08)
# O Dre viu o piloto e disse duas vezes: "só tem uma imagem durante todo o
# vídeo". Eu respondi que a `productOfferV2` devolve um `imageUrl` só e que o
# gargalo era a origem. **Isso é o que eu SEI hoje, não necessariamente o que é
# verdade** — a query em shopee_affiliate.py pede `imageUrl` e mais nada, então
# ela nunca teve chance de devolver outra coisa.
#
# Antes de construir coletor, ranker e fila de assets em cima de uma suposição,
# vale UMA pergunta à API. Se ela já entrega galeria, metade do problema some
# hoje e de graça.
#
# COMO ELE FUNCIONA
# GraphQL rejeita a query INTEIRA quando um campo não existe — e o
# shopee_affiliate.py já vive com isso (o truque do `priceDiscountRate`). Então
# aqui cada campo candidato é testado SOZINHO, um pedido por campo: o que
# responder 200 existe, o que der erro não existe. Nada é adivinhado.
#
# ⚠️ SÓ LÊ. Não escreve na fila, não mexe em produto, não posta.
#
# Uso, na VPS (o .venv é quem carrega as credenciais do .env):
#   .venv/bin/python probe_imagens.py --item 22832360966
#   .venv/bin/python probe_imagens.py --fila 0

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Nomes plausíveis pra uma galeria de imagens numa API GraphQL. Não são chutes
# aleatórios: são as convenções que aparecem em APIs de catálogo. O teste é
# barato (uma chamada cada) e a resposta é definitiva.
CANDIDATOS = [
    "images",
    "imageUrls",
    "imageList",
    "productImages",
    "itemImages",
    "gallery",
    "galleryImages",
    "mainImages",
    "videoUrl",          # vídeo do produto vale MAIS que foto extra
    "productVideoUrl",
    "video",
]


def _log(m):
    print(f"[probe] {m}", flush=True)


def _carregar_env():
    import os
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


def _item_da_fila(indice: int):
    for cand in (BASE_DIR / "shared" / "produtos_fila.json",
                 Path("shared/produtos_fila.json")):
        if cand.exists():
            d = [x for x in json.loads(cand.read_text(encoding="utf-8"))
                 if isinstance(x, dict)]
            if 0 <= indice < len(d):
                return d[indice]
    return None


def main():
    p = argparse.ArgumentParser(
        description="Pergunta à Shopee se existe galeria de imagens.")
    p.add_argument("--item", help="itemId da Shopee")
    p.add_argument("--fila", type=int, help="índice em produtos_fila.json "
                                            "(descobre o itemId pelo link)")
    args = p.parse_args()

    _carregar_env()
    try:
        from integrations.shopee_affiliate import _executar_graphql
    except Exception:
        try:
            from shopee_affiliate import _executar_graphql
        except Exception as e:
            raise SystemExit(f"[probe] não importei o shopee_affiliate: {e}")

    item_id = (args.item or "").strip()
    if not item_id and args.fila is not None:
        it = _item_da_fila(args.fila)
        if not it:
            raise SystemExit("[probe] não achei esse índice na fila")
        try:
            from integrations.shopee_affiliate import extrair_ids_da_url
        except Exception:
            try:
                from shopee_affiliate import extrair_ids_da_url
            except Exception:
                extrair_ids_da_url = None
        link = it.get("link") or ""
        if extrair_ids_da_url and link:
            ids = extrair_ids_da_url(link) or {}
            if ids.get("ok"):
                item_id = str(ids.get("item_id") or "")
        if not item_id and link:
            # A FILA GUARDA LINK CURTO (s.shopee.com.br/9Kh92XRVv8), e o
            # extrair_ids_da_url só entende o formato longo com i.SHOP.ITEM.
            # Quem já resolvia isso é o preencher_fotos._ids_do_link, que SEGUE
            # o redirecionamento até a página do produto. Reusar em vez de
            # reescrever: é a mesma regra num lugar só que o projeto já cobra.
            try:
                from preencher_fotos import _ids_do_link
                _shop, _item = _ids_do_link(link)
                item_id = str(_item or "")
                if item_id:
                    _log(f"link curto resolvido → shop {_shop} · item {item_id}")
            except Exception as e:
                _log(f"não segui o link curto: {str(e)[:80]}")
        if not item_id:
            raise SystemExit(f"[probe] não extraí o itemId de {link[:70]!r} — "
                             "passe --item ITEMID")
    if not item_id:
        p.error("use --item ITEMID ou --fila N")

    _log(f"item {item_id}")

    # 1) confirma que o básico responde — se isto falhar, o resto não diz nada
    base = ("query { productOfferV2(itemId: " + item_id + ") { nodes { "
            "itemId productName imageUrl } } }")
    r = _executar_graphql(base)
    if r.get("_erro"):
        raise SystemExit(f"[probe] nem a query básica passou: {r['_erro']}\n"
                         "        confira SHOPEE_APP_ID / SHOPEE_APP_SECRET no .env")
    nodes = (((r.get("data") or {}).get("productOfferV2") or {}).get("nodes") or [])
    if not nodes:
        raise SystemExit("[probe] a API respondeu, mas não achou este item")
    _log(f"✅ básico ok — {nodes[0].get('productName', '')[:56]}")
    _log(f"   imageUrl: {nodes[0].get('imageUrl', '')[:78]}")

    # 2) um campo por vez: GraphQL derruba a query inteira por um campo inválido
    print()
    _log("testando campos candidatos, um por pedido:")
    achados = []
    for campo in CANDIDATOS:
        q = ("query { productOfferV2(itemId: " + item_id + ") { nodes { "
             "itemId " + campo + " } } }")
        resp = _executar_graphql(q)
        if resp.get("_erro"):
            print(f"     ✗ {campo}")
            continue
        ns = (((resp.get("data") or {}).get("productOfferV2") or {})
              .get("nodes") or [])
        valor = (ns[0] or {}).get(campo) if ns else None
        print(f"     ✅ {campo}  →  {json.dumps(valor, ensure_ascii=False)[:150]}")
        achados.append((campo, valor))

    print()
    if achados:
        _log(f"EXISTE galeria: {', '.join(c for c, _ in achados)}")
        _log("   próximo passo: acrescentar o campo na query de "
             "shopee_affiliate.obter_dados_produto e gravar a lista em "
             "`imagens` na fila — o piloto já sabe usar `imagens`")
    else:
        _log("nenhum campo de galeria existe nesta API.")
        _log("   então mais imagem por produto NÃO vem da API de afiliado, e o "
             "caminho é outro (página do produto, vídeo do hunter, ou banco "
             "próprio de assets). Pelo menos agora isso é fato, não suposição.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
