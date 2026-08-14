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


_shop_id_global = [""]


def _interna(item_id: str, shop_id: str):
    """Pergunta à API INTERNA da loja (v4/item/get) se existe galeria.

    POR QUE VALE PERGUNTAR, mesmo o projeto já tendo anotado "a API interna
    (403)": aquela anotação é sobre RASPAR A PÁGINA e sobre uma tentativa
    antiga. Este endpoint é o que o próprio site usa e devolve `images` como
    lista de hashes — que, com o prefixo do CDN, viram URL de imagem.
    A resposta muda o rumo inteiro do Asset Collector, então merece um pedido.

    ⚠️ SÓ LÊ, uma vez, com o User-Agent de navegador. Se der 403, é 403 — e a
    conclusão é que o caminho da galeria não é este.
    """
    if not shop_id:
        _log("sem shop_id, pulo a API interna (use --item junto com --shop)")
        return
    print()
    _log("API interna da loja (v4/item/get):")
    url = (f"https://shopee.com.br/api/v4/item/get?itemid={item_id}"
           f"&shopid={shop_id}")
    try:
        import requests
        r = requests.get(url, timeout=25, headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"),
            "Referer": f"https://shopee.com.br/product/{shop_id}/{item_id}",
            "X-Requested-With": "XMLHttpRequest",
        })
    except Exception as e:
        _log(f"     ✗ falhou: {str(e)[:90]}")
        return
    if r.status_code != 200:
        _log(f"     ✗ HTTP {r.status_code} — a loja bloqueia este endpoint "
             "daqui. A galeria não vem por aqui.")
        return
    try:
        dados = (r.json() or {}).get("data") or {}
    except Exception:
        _log("     ✗ respondeu 200 mas não era JSON (provável página de bloqueio)")
        return
    if not dados:
        _log("     ✗ 200 com data vazio — bloqueio silencioso")
        return
    imgs = dados.get("images") or []
    video = dados.get("video_info_list") or []
    _log(f"     ✅ RESPONDEU · {len(imgs)} imagem(ns) · {len(video)} vídeo(s)")
    for h in imgs[:6]:
        print(f"        https://cf.shopee.com.br/file/{h}")
    if video:
        _log("     ⚠️  TEM VÍDEO DO PRODUTO — vale mais que foto extra")


def main():
    p = argparse.ArgumentParser(
        description="Pergunta à Shopee se existe galeria de imagens.")
    p.add_argument("--item", help="itemId da Shopee")
    p.add_argument("--shop", default="", help="shopId (só com --item --interna)")
    p.add_argument("--fila", type=int, help="índice em produtos_fila.json "
                                            "(descobre o itemId pelo link)")
    p.add_argument("--interna", action="store_true",
                   help="testa também a API interna da loja (v4/item/get), "
                        "que é onde a galeria costuma estar")
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
    if args.shop:
        _shop_id_global[0] = args.shop.strip()
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
        if extrair_ids_da_url and link:  # noqa: E501
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
                _shop_id_global[0] = str(_shop or "")
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
        # com --interna a pergunta é sobre OUTRA API: não faz sentido desistir
        # só porque a credencial de afiliado não está aqui
        if args.interna and _shop_id_global[0]:
            _log(f"a API de afiliado não respondeu ({r['_erro'][:60]}) — "
                 "sigo direto pra interna")
            _interna(item_id, _shop_id_global[0])
            return 0
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

    if args.interna:
        _interna(item_id, _shop_id_global[0])

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
