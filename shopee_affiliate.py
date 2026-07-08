# integrations/shopee_affiliate.py
# Motor de conexão com a Shopee Affiliate Open API (Brasil) — GraphQL.
#
# O QUE FAZ (camada 1 — a fundação):
#   - Autentica na API da Shopee (assinatura SHA256, padrão oficial)
#   - Gera LINK DE AFILIADO rastreável a partir da URL de um produto
#     (o link com a TUA comissão — fecha o ciclo do dinheiro do vídeo)
#
# As outras capacidades (buscar produtos por comissão, extrair preço/título,
# relatório de conversões) reusam este mesmo motor — são só outras queries
# GraphQL em cima da mesma autenticação.
#
# SEGURANÇA: credenciais vêm de variáveis de ambiente, NUNCA no código:
#   SHOPEE_APP_ID     — o App ID (numérico) do painel Open API
#   SHOPEE_APP_SECRET — o App Secret (string longa) do painel Open API
#
# AUTENTICAÇÃO (confirmado em integrações públicas da API BR):
#   Signature = SHA256(appId + timestamp + payload + secret)
#   Header: Authorization: SHA256 Credential={appId}, Timestamp={ts}, Signature={sig}
#   timestamp = Unix em SEGUNDOS (não ms); janela de validade ~5 min
#   payload = o corpo JSON EXATO enviado ao endpoint GraphQL
#
# Endpoint GraphQL BR: https://open-api.affiliate.shopee.com.br/graphql

import os
import json
import time
import hashlib
from typing import Optional

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("shopee_affiliate")

try:
    import requests
    _REQUESTS_OK = True
except Exception:
    _REQUESTS_OK = False

# Endpoint oficial GraphQL do Open Platform de afiliados (Brasil)
SHOPEE_GRAPHQL_URL = "https://open-api.affiliate.shopee.com.br/graphql"
TIMEOUT_SEG = 30


def _credenciais() -> tuple:
    """Lê App ID e App Secret das env vars. Retorna (app_id, secret) ou (None, None)."""
    app_id = (os.environ.get("SHOPEE_APP_ID") or "").strip()
    secret = (os.environ.get("SHOPEE_APP_SECRET") or "").strip()
    return (app_id or None, secret or None)


def disponivel() -> tuple:
    """
    Checa se dá pra usar a API. Retorna (ok: bool, motivo: str).
    """
    app_id, secret = _credenciais()
    if not app_id or not secret:
        return (False, "SHOPEE_APP_ID/SHOPEE_APP_SECRET não configurados (env vars)")
    if not _REQUESTS_OK:
        return (False, "biblioteca 'requests' não instalada (pip install requests)")
    return (True, "")


def _assinar(app_id: str, timestamp: int, payload: str, secret: str) -> str:
    """
    Gera a assinatura SHA256 exigida pela Shopee.
    Fórmula oficial: SHA256(appId + timestamp + payload + secret)
    Retorna o hash em hexadecimal minúsculo.
    """
    base = f"{app_id}{timestamp}{payload}{secret}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _montar_headers(payload: str) -> dict:
    """
    Monta os headers de autenticação pra uma requisição.
    O payload deve ser EXATAMENTE a string JSON que vai no corpo (a assinatura
    é calculada sobre ela; qualquer diferença de espaço/ordem invalida).
    """
    app_id, secret = _credenciais()
    timestamp = int(time.time())  # Unix em SEGUNDOS
    assinatura = _assinar(app_id, timestamp, payload, secret)
    return {
        "Content-Type": "application/json",
        "Authorization": (f"SHA256 Credential={app_id}, "
                          f"Timestamp={timestamp}, Signature={assinatura}"),
    }


def _executar_graphql(query: str, variables: dict = None) -> dict:
    """
    Executa uma query/mutation GraphQL na API da Shopee, autenticada.

    Returns: dict com a resposta JSON. Em erro, retorna
             {"_erro": "...", "_status": código}.
    """
    ok, motivo = disponivel()
    if not ok:
        return {"_erro": motivo}

    # IMPORTANTE: o payload assinado tem que ser BYTE-A-BYTE igual ao corpo
    # enviado. Por isso serializamos UMA vez e reusamos a mesma string.
    corpo = {"query": query}
    if variables:
        corpo["query"] = query  # garante presença
        corpo["variables"] = variables
    payload_str = json.dumps(corpo, separators=(",", ":"), ensure_ascii=False)

    headers = _montar_headers(payload_str)
    try:
        resp = requests.post(SHOPEE_GRAPHQL_URL,
                             data=payload_str.encode("utf-8"),
                             headers=headers, timeout=TIMEOUT_SEG)
    except Exception as e:
        return {"_erro": f"falha de rede: {type(e).__name__}: {str(e)[:200]}"}

    if resp.status_code != 200:
        return {"_erro": f"HTTP {resp.status_code}: {resp.text[:300]}",
                "_status": resp.status_code}
    try:
        data = resp.json()
    except Exception:
        return {"_erro": f"resposta não-JSON: {resp.text[:200]}"}

    # GraphQL devolve erros em data["errors"] mesmo com HTTP 200
    if isinstance(data, dict) and data.get("errors"):
        msg = data["errors"]
        return {"_erro": f"GraphQL erro: {str(msg)[:300]}", "_raw": data}
    return data


# =================================================================
# MINERADOR DE OPORTUNIDADES — score de lucro + Top 3 (campeão + reservas)
# =================================================================

# Corte de qualidade: nota mínima pra um produto entrar (não dá reembolso).
NOTA_MINIMA = 4.7
# Corte de tração: vendas mínimas (ignora produto fantasma sem prova social).
VENDAS_MINIMAS = 10


# Palavras curtas/genéricas que não ajudam a medir relevância (ignoradas).
_STOPWORDS_REL = {
    "de", "da", "do", "para", "pra", "com", "sem", "e", "o", "a", "os", "as",
    "em", "por", "no", "na", "um", "uma", "the", "of", "for", "and",
    "mini", "portatil", "portátil",  # genéricas demais sozinhas
}


def _palavras_chave(texto: str) -> set:
    """Extrai as palavras significativas de um texto (lower, sem stopwords)."""
    palavras = _re.findall(r"\w+", (texto or "").lower())
    return {p for p in palavras if len(p) >= 3 and p not in _STOPWORDS_REL}


def _relevancia(keyword: str, titulo_produto: str) -> float:
    """
    Mede quão relevante um produto é pra keyword buscada (0.0 a 1.0).

    Conta quantas palavras-chave da keyword aparecem no título do produto.
    Ex: keyword "aspirador teclado" vs título "Mini Aspirador USB Teclado"
        → 2 de 2 palavras casam → relevância alta.
        vs título "Soprador de Pó Computador" → 0 casam → relevância baixa.

    Returns: fração das palavras da keyword presentes no título (0.0–1.0).
    """
    kw_palavras = _palavras_chave(keyword)
    if not kw_palavras:
        return 1.0  # sem palavras úteis pra comparar → não penaliza
    titulo_palavras = _palavras_chave(titulo_produto)
    if not titulo_palavras:
        return 0.0
    casadas = kw_palavras & titulo_palavras
    return len(casadas) / len(kw_palavras)


# ── APRENDIZADO: boost pras categorias que os VÍDEOS já venderam ──────────
# O metricas_agent escreve shared/nichos_quentes.json com o que converteu. Aqui
# a gente relê os PRODUTOS que venderam, re-infere a categoria pela MESMA função
# do site (consistência) e dá nota extra pros produtos de categoria campeã.
# Fecha o loop: caça → posta → mede → caça mais do que dá dinheiro. 🔁
_NICHOS_CACHE = {"mtime": -1.0, "pesos": {}}


def _caminho_nichos():
    from pathlib import Path
    base = Path(__file__).resolve().parent
    for c in (base.parent / "shared" / "nichos_quentes.json",
              base / "shared" / "nichos_quentes.json",
              Path("shared/nichos_quentes.json")):
        if c.exists():
            return c
    return None


def _infcat_nome(nome: str) -> str:
    try:
        try:
            from creative_engine.bio_page_builder import _inferir_categoria
        except Exception:
            from bio_page_builder import _inferir_categoria
        return _inferir_categoria({"nome": nome or "", "titulo": nome or ""})
    except Exception:
        return "Outros"


def _pesos_nicho() -> dict:
    """{categoria: peso 0..1} a partir do que os vídeos venderam (cache por mtime)."""
    p = _caminho_nichos()
    if not p:
        return {}
    try:
        mt = p.stat().st_mtime
        if mt == _NICHOS_CACHE["mtime"]:
            return _NICHOS_CACHE["pesos"]
        dados = json.loads(p.read_text(encoding="utf-8"))
        acc = {}
        for prod in dados.get("top_produtos", []):
            cat = _infcat_nome(prod.get("nome", ""))
            if cat and cat != "Outros":
                acc[cat] = acc.get(cat, 0.0) + float(prod.get("comissao", 0) or 0)
        if not acc:   # fallback: usa o ranking de categorias já salvo
            for i, cat in enumerate(dados.get("ranking_categorias", [])):
                if cat and cat != "Outros":
                    acc[cat] = acc.get(cat, 0.0) + max(1.0, 5.0 - i)
        maxv = max(acc.values()) if acc else 0.0
        pesos = {c: v / maxv for c, v in acc.items()} if maxv > 0 else {}
        _NICHOS_CACHE.update(mtime=mt, pesos=pesos)
        return pesos
    except Exception:
        return {}


def _fator_nicho(nome: str) -> float:
    """1.0 (neutro) a 1.5 (categoria que mais converteu nos vídeos)."""
    pesos = _pesos_nicho()
    if not pesos:
        return 1.0
    return 1.0 + 0.5 * pesos.get(_infcat_nome(nome), 0.0)


def _score_lucro(produto: dict, keyword: str = "") -> float:
    """
    Calcula o score de LUCRO de um produto. Filosofia: priorizar quanto você
    GANHA por venda (comissão em R$), modulado pela qualidade (nota).

    Componentes:
      - comissão em R$ (peso dominante — é o lucro direto por venda)
      - nota (multiplicador de qualidade — produto bom não vira reembolso)
      - vendas (leve empurrão — prova que vende, mas não domina o score;
        evita que volume gigante de produto-migalha vença um campeão de lucro)

    Retorna um número (quanto maior, melhor). Escala relativa, pra ranquear.
    """
    comissao_rs = float(produto.get("comissao_valor", 0) or 0)
    nota = float(produto.get("rating", 0) or 0)
    vendas = float(produto.get("vendas", 0) or 0)

    # Base: a comissão em R$ é o coração do score (o que entra no teu bolso).
    base = comissao_rs

    # Multiplicador de qualidade: nota 5.0 → 1.0; nota 4.7 → ~0.94; nota baixa pesa menos.
    # (nota/5.0) mantém entre 0 e 1; elevamos pra dar vantagem extra às notas altas.
    fator_nota = (nota / 5.0) ** 2 if nota > 0 else 0.0

    # Empurrão leve de tração: log das vendas pra não deixar volume dominar.
    # +1 evita log(0); o math.log dá retorno decrescente (1000 vendas não vale
    # 10x mais que 100, só um pouco mais).
    import math
    fator_vendas = 1.0 + (math.log10(vendas + 1) / 10.0)  # ~1.0 a ~1.4

    # Fator de relevância: quão parecido o título é com a keyword buscada.
    # Produto relevante mantém o score; produto que foge (ex: soprador quando
    # buscamos aspirador) perde pontos. Usamos um piso de 0.3 pra não zerar
    # produtos com nome muito diferente mas possivelmente certos (a relevância
    # textual é uma dica, não uma verdade absoluta).
    if keyword:
        rel = _relevancia(keyword, produto.get("nome", ""))
        fator_rel = 0.3 + 0.7 * rel   # rel=0 → 0.3; rel=1 → 1.0
    else:
        fator_rel = 1.0

    return round(base * fator_nota * fator_vendas * fator_rel *
                 _fator_nicho(produto.get("nome", "")), 3)


def minerar_oportunidades(keyword: str, limite_busca: int = 30,
                          top_n: int = 3, nota_minima: float = NOTA_MINIMA,
                          vendas_minimas: int = VENDAS_MINIMAS,
                          ordenar_por: int = 2) -> dict:
    """
    Minera as melhores oportunidades de afiliado pra uma keyword:
      1. Busca produtos (limite_busca itens)
      2. Corta os de nota < nota_minima (qualidade — evita reembolso)
      3. Corta os de vendas < vendas_minimas (tração — evita produto fantasma)
      4. Calcula score de LUCRO (comissão × nota × tração × relevância)
      5. Retorna o Top N (campeão + reservas), do melhor pro pior score

    A estratégia dos "links espelhos": o top 1 é o campeão pra promover; os
    demais são reservas — se o vendedor #1 sumir/zerar estoque, troca pelo
    reserva sem perder o tráfego do vídeo.

    Args:
        vendas_minimas: corte de tração. Padrão 10 (ignora produtos fantasma
                        de 1-2 vendas). Baixe pra 5 em produtos recém-lançados,
                        suba pra 20 pra pegar só gigantes validados.

    Returns:
        {"ok": True, "keyword": str, "campeao": {...}, "reservas": [{...}],
         "top": [...], "analisados": int, "aprovados": int,
         "cortados_nota": int, "cortados_vendas": int}
        {"ok": False, "erro": "...", "diagnostico": {...}}
    """
    r = buscar_produtos(keyword, limite=limite_busca, ordenar_por=ordenar_por)
    if not r["ok"]:
        return {"ok": False, "erro": r["erro"]}

    produtos = r["produtos"]
    analisados = len(produtos)

    # Corte 1 — qualidade (nota): evita produto ruim que dá reembolso
    com_nota = [p for p in produtos if float(p.get("rating", 0) or 0) >= nota_minima]
    cortados_nota = analisados - len(com_nota)

    # Corte 2 — tração (vendas): evita produto fantasma sem prova social
    aprovados = [p for p in com_nota
                 if int(float(p.get("vendas", 0) or 0)) >= vendas_minimas]
    cortados_vendas = len(com_nota) - len(aprovados)

    if not aprovados:
        # Diagnóstico honesto: diz POR QUE não achou (ajuda a curar a fila)
        return {
            "ok": False,
            "erro": (f"nenhuma mina de ouro pra '{keyword}': de {analisados} "
                     f"produtos, {cortados_nota} reprovados na nota (< {nota_minima}) "
                     f"e {cortados_vendas} sem tração (< {vendas_minimas} vendas). "
                     f"Esse produto pode ser fraco de afiliados na Shopee."),
            "diagnostico": {"analisados": analisados,
                            "cortados_nota": cortados_nota,
                            "cortados_vendas": cortados_vendas},
        }

    # Calcula score e ordena (maior score primeiro)
    for p in aprovados:
        p["score"] = _score_lucro(p, keyword=keyword)
        p["relevancia"] = round(_relevancia(keyword, p.get("nome", "")), 2)
    aprovados.sort(key=lambda x: x["score"], reverse=True)

    top = aprovados[:top_n]
    return {
        "ok": True,
        "cortados_nota": cortados_nota,
        "cortados_vendas": cortados_vendas,
        "keyword": keyword,
        "campeao": top[0],
        "reservas": top[1:],
        "top": top,
        "analisados": analisados,
        "aprovados": len(aprovados),
    }


# =================================================================
# CAPACIDADE 3 — BUSCAR PRODUTOS POR KEYWORD (base do minerador)
# =================================================================

def buscar_produtos(keyword: str, limite: int = 20,
                    pagina: int = 1, ordenar_por: int = 2) -> dict:
    """
    Busca produtos na Shopee por palavra-chave, retornando a lista com os
    dados que importam pro minerador (nome, preço, comissão, vendas, nota).

    Args:
        keyword:    termo de busca (ex: "espelho led", "cortador de legumes")
        limite:     quantos produtos trazer (a API costuma aceitar até 50)
        pagina:     página de resultados (1 = primeira)
        ordenar_por: sortType da Shopee. Valores comuns:
                     0=relevância, 1=mais vendidos, 2=maior comissão (default)

    Returns:
        {"ok": True, "produtos": [ {nome, preco, comissao_rate, comissao_valor,
         vendas, rating, item_id, shop_id, offer_link}, ... ]}
        {"ok": False, "erro": "..."}
    """
    if not keyword or not keyword.strip():
        return {"ok": False, "erro": "keyword vazia"}

    kw = _escapar_graphql_string(keyword.strip())
    # productOfferV2 com keyword + paginação + ordenação.
    query = (
        "query { productOfferV2("
        f'keyword: "{kw}", '
        f"sortType: {int(ordenar_por)}, "
        f"page: {int(pagina)}, "
        f"limit: {int(limite)}"
        ") { nodes { "
        "itemId shopId productName priceMin priceMax imageUrl "
        "commissionRate commission sales ratingStar offerLink productLink "
        "} } }"
    )

    resp = _executar_graphql(query)
    if resp.get("_erro"):
        return {"ok": False, "erro": resp["_erro"]}

    try:
        nodes = (((resp.get("data") or {}).get("productOfferV2") or {})
                 .get("nodes") or [])
    except Exception:
        nodes = []

    if not nodes:
        return {"ok": False,
                "erro": f"busca sem resultados pra '{keyword}'. "
                        f"Resposta: {str(resp)[:150]}"}

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    produtos = []
    for p in nodes:
        produtos.append({
            "nome":           p.get("productName", ""),
            "preco":          _num(p.get("priceMin")),
            "preco_max":      _num(p.get("priceMax")),
            "imagem":         p.get("imageUrl", ""),
            "comissao_rate":  _num(p.get("commissionRate")),   # 0.14 = 14%
            "comissao_valor": _num(p.get("commission")),        # BRL
            "vendas":         int(_num(p.get("sales"))),
            "rating":         _num(p.get("ratingStar")),
            "item_id":        p.get("itemId"),
            "shop_id":        p.get("shopId"),
            "offer_link":     p.get("offerLink", ""),
            "product_link":   p.get("productLink", ""),
        })
    return {"ok": True, "produtos": produtos, "total": len(produtos)}


# =================================================================
# CAPACIDADE 2 — EXTRAIR DADOS DO PRODUTO (título, preço, imagem, comissão)
# =================================================================

import re as _re


def extrair_ids_da_url(url: str) -> dict:
    """
    Extrai shopId e itemId de uma URL de produto da Shopee.

    A URL traz os dois no padrão '...-i.{shopId}.{itemId}'. Ex:
      https://shopee.com.br/Espelho-LED-i.789807677.10398027894
      → shopId=789807677, itemId=10398027894

    Returns: {"ok": True, "shop_id": int, "item_id": int} ou {"ok": False, "erro": ...}
    """
    if not url:
        return {"ok": False, "erro": "url vazia"}
    # procura o padrão i.NUMERO.NUMERO (aceita query string depois)
    m = _re.search(r"i\.(\d+)\.(\d+)", url)
    if not m:
        return {"ok": False,
                "erro": "URL não tem o padrão i.shopId.itemId (é link de produto?)"}
    return {"ok": True, "shop_id": int(m.group(1)), "item_id": int(m.group(2))}


def obter_dados_produto(url_ou_item: str,
                        shop_id: Optional[int] = None) -> dict:
    """
    Busca os dados oficiais de um produto: título, preço, imagem, comissão.

    Aceita a URL completa do produto (extrai os IDs sozinho) OU o itemId direto
    (passando shop_id também). Usa a query productOfferV2 filtrando por itemId.

    Returns (sucesso):
      {"ok": True, "titulo": str, "preco": float, "imagem": str,
       "comissao_rate": float, "comissao_valor": float, "offer_link": str,
       "item_id": int, "shop_id": int}
    Returns (falha): {"ok": False, "erro": str}
    """
    # resolve os IDs (da URL ou direto)
    if shop_id is not None and str(url_ou_item).isdigit():
        item_id = int(url_ou_item)
    else:
        ids = extrair_ids_da_url(url_ou_item)
        if not ids["ok"]:
            return {"ok": False, "erro": ids["erro"]}
        shop_id, item_id = ids["shop_id"], ids["item_id"]

    # productOfferV2 aceita filtrar por itemId. Pedimos os campos que importam.
    query = (
        "query { productOfferV2(itemId: " + str(item_id) + ") { nodes { "
        "itemId productName priceMin priceMax imageUrl "
        "commissionRate commission offerLink productLink ratingStar sales "
        "} } }"
    )

    resp = _executar_graphql(query)
    if resp.get("_erro"):
        return {"ok": False, "erro": resp["_erro"]}

    try:
        nodes = (((resp.get("data") or {}).get("productOfferV2") or {})
                 .get("nodes") or [])
    except Exception:
        nodes = []
    if not nodes:
        return {"ok": False,
                "erro": f"produto não encontrado (itemId={item_id}). "
                        f"Resposta: {str(resp)[:150]}"}

    p = nodes[0]
    # a API codifica números como string às vezes; converte com segurança
    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    return {
        "ok": True,
        "titulo": p.get("productName", ""),
        "preco": _num(p.get("priceMin")),
        "preco_max": _num(p.get("priceMax")),
        "imagem": p.get("imageUrl", ""),
        "comissao_rate": _num(p.get("commissionRate")),   # 0.38 = 38%
        "comissao_valor": _num(p.get("commission")),       # em BRL
        "rating": _num(p.get("ratingStar")),
        "vendas": int(_num(p.get("sales"))),
        "offer_link": p.get("offerLink", ""),
        "item_id": item_id,
        "shop_id": shop_id,
    }


# =================================================================
# CAPACIDADE 1 — GERAR LINK DE AFILIADO RASTREÁVEL
# =================================================================


def _escapar_graphql_string(s: str) -> str:
    """Escapa uma string pra inserir dentro de uma query GraphQL inline."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def gerar_link_afiliado(url_produto: str,
                        sub_ids: Optional[list] = None) -> dict:
    """
    Converte a URL de um produto Shopee num LINK DE AFILIADO rastreável.

    Args:
        url_produto: URL normal do produto (ex: https://shopee.com.br/produto-i.123.456)
        sub_ids:     até 5 etiquetas de rastreio (ex: ["tiktok", "cortador", "video01"])
                     pra saber depois qual canal/criativo gerou a venda.

    Returns:
        {"ok": True, "short_link": "https://s.shopee.com.br/..."} em sucesso
        {"ok": False, "erro": "..."} em falha
    """
    if not url_produto or not url_produto.strip():
        return {"ok": False, "erro": "url_produto vazia"}

    # Monta o input INLINE na mutation (a Shopee NÃO usa tipo nomeado/variável;
    # o input vai direto no corpo da query, como no exemplo oficial da API).
    url_esc = _escapar_graphql_string(url_produto.strip())
    campos = [f'originUrl: "{url_esc}"']
    if sub_ids:
        # até 5 sub-IDs, cada um como string escapada
        ids = [f'"{_escapar_graphql_string(str(s))}"' for s in sub_ids[:5]]
        campos.append(f'subIds: [{", ".join(ids)}]')
    input_inline = ", ".join(campos)

    query = ("mutation { generateShortLink(input: { " + input_inline +
             " }) { shortLink } }")

    resp = _executar_graphql(query)
    if resp.get("_erro"):
        return {"ok": False, "erro": resp["_erro"]}

    # extrai o short link da resposta (defensivo a variações de formato)
    try:
        short = (resp.get("data") or {}).get("generateShortLink") or {}
        link = short.get("shortLink")
    except Exception:
        link = None

    if not link:
        return {"ok": False, "erro": f"resposta sem shortLink: {str(resp)[:200]}"}
    return {"ok": True, "short_link": link, "sub_ids": sub_ids[:5] if sub_ids else []}


# =================================================================
# CLI (pra testar isolado)
# =================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Shopee Affiliate — gera link de afiliado rastreável")
    parser.add_argument("--url", default="",
                        help="URL do produto Shopee pra converter em link de afiliado")
    parser.add_argument("--produto", default="",
                        help="URL do produto pra EXTRAIR dados (título, preço, imagem, comissão)")
    parser.add_argument("--buscar", default="",
                        help="Busca produtos por palavra-chave (ex: 'espelho led')")
    parser.add_argument("--minerar", default="",
                        help="Minera a MINA DE OURO de uma keyword (top 3 por score de lucro)")
    parser.add_argument("--gerar-links", action="store_true", dest="gerar_links",
                        help="Com --minerar: já gera os links de afiliado do top 3")
    parser.add_argument("--vendas-min", type=int, default=VENDAS_MINIMAS,
                        dest="vendas_min",
                        help=f"Corte de vendas mínimas no minerador (padrão {VENDAS_MINIMAS})")
    parser.add_argument("--limite", type=int, default=15,
                        help="Quantos produtos trazer na busca (default 15)")
    parser.add_argument("--ordenar", type=int, default=2,
                        help="Ordenação: 0=relevância, 1=mais vendidos, 2=maior comissão")
    parser.add_argument("--sub-ids", default="",
                        help="Sub-IDs de rastreio separados por vírgula (máx 5). "
                             "Ex: tiktok,cortador,video01")
    parser.add_argument("--checar", action="store_true",
                        help="Só checa se as credenciais estão configuradas")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("🛒 SHOPEE AFFILIATE")
    log.info("=" * 60)

    ok, motivo = disponivel()
    if args.checar:
        if ok:
            app_id, _ = _credenciais()
            print(f"✅ Credenciais OK (App ID: {app_id[:4]}...{app_id[-2:]})")
            print("   (App Secret presente, oculto por segurança)")
        else:
            print(f"❌ {motivo}")
        return 0 if ok else 1

    if not ok:
        log.error(f"❌ {motivo}")
        print("\n💡 Configure as variáveis de ambiente:")
        print('   set SHOPEE_APP_ID=seu_app_id')
        print('   set SHOPEE_APP_SECRET=seu_app_secret')
        return 1

    if not args.url and not args.produto and not args.buscar and not args.minerar:
        parser.error("use --url, --produto, --buscar, --minerar ou --checar")

    # Minerar oportunidades (a mina de ouro: top 3 por score de lucro)
    if args.minerar:
        log.info(f"\n⛏️  Minerando oportunidades pra '{args.minerar}' "
                 f"(nota ≥ {NOTA_MINIMA}, vendas ≥ {args.vendas_min})")
        m = minerar_oportunidades(args.minerar, vendas_minimas=args.vendas_min)
        if not m["ok"]:
            print(f"\n❌ {m['erro']}")
            return 1
        print(f"\n💰 MINA DE OURO — '{m['keyword']}'")
        print(f"   ({m['analisados']} analisados | {m.get('cortados_nota',0)} cortados na nota"
              f" | {m.get('cortados_vendas',0)} cortados nas vendas"
              f" | {m['aprovados']} aprovados)\n")
        for i, p in enumerate(m["top"]):
            tag = "🏆 CAMPEÃO" if i == 0 else f"🥈 RESERVA {i}"
            print(f"  {tag} | score {p['score']}")
            print(f"     {p['nome'][:55]}")
            print(f"     comissão {p['comissao_rate']*100:.0f}% (R$ {p['comissao_valor']:.2f})"
                  f" | {p['vendas']} vendas | {p['rating']:.1f}⭐")
            print(f"     product_link: {p.get('product_link','')[:70]}")
            print()
        # opcionalmente já gera os links de afiliado do top 3
        if args.gerar_links:
            print("🔗 Gerando links de afiliado do top 3 (links espelhos):\n")
            for i, p in enumerate(m["top"]):
                origem = p.get("product_link") or p.get("offer_link")
                if not origem:
                    print(f"   {i+1}. (sem product_link pra gerar)")
                    continue
                sub = ["minerador", _re.sub(r"\W+", "", args.minerar)[:10], f"top{i+1}"]
                lk = gerar_link_afiliado(origem, sub_ids=sub)
                rotulo = "principal" if i == 0 else f"reserva_{i}"
                if lk["ok"]:
                    print(f"   {rotulo}: {lk['short_link']}")
                else:
                    print(f"   {rotulo}: ❌ {lk['erro'][:60]}")
            print()
        return 0

    # Buscar produtos por keyword
    if args.buscar:
        ordem = {0: "relevância", 1: "mais vendidos", 2: "maior comissão"}.get(
            args.ordenar, str(args.ordenar))
        log.info(f"\n🔎 Buscando '{args.buscar}' (ordenado por: {ordem})")
        r = buscar_produtos(args.buscar, limite=args.limite, ordenar_por=args.ordenar)
        if not r["ok"]:
            print(f"\n❌ Falhou: {r['erro']}")
            return 1
        print(f"\n✅ {r['total']} produto(s) encontrado(s):\n")
        for i, p in enumerate(r["produtos"], 1):
            print(f"  {i}. {p['nome'][:55]}")
            print(f"     R$ {p['preco']:.2f}"
                  + (f"–{p['preco_max']:.2f}" if p['preco_max'] > p['preco'] else "")
                  + f" | comissão {p['comissao_rate']*100:.0f}% (R$ {p['comissao_valor']:.2f})"
                  + f" | {p['vendas']} vendas | {p['rating']:.1f}⭐")
            print(f"     item={p['item_id']} shop={p['shop_id']}")
            print()
        return 0

    # Extrair dados do produto
    if args.produto:
        log.info(f"\n🔍 Extraindo dados do produto: {args.produto[:70]}...")
        d = obter_dados_produto(args.produto)
        if d["ok"]:
            print(f"\n✅ Dados do produto:")
            print(f"   Título:    {d['titulo']}")
            print(f"   Preço:     R$ {d['preco']:.2f}"
                  + (f" – R$ {d['preco_max']:.2f}" if d['preco_max'] > d['preco'] else ""))
            print(f"   Comissão:  {d['comissao_rate']*100:.1f}% (R$ {d['comissao_valor']:.2f})")
            print(f"   Avaliação: {d['rating']:.1f}⭐ | {d['vendas']} vendas")
            print(f"   Imagem:    {d['imagem'][:70]}")
            print(f"   IDs:       shop={d['shop_id']} item={d['item_id']}")
        else:
            print(f"\n❌ Falhou: {d['erro']}")
            return 1
        return 0

    sub_ids = [s.strip() for s in args.sub_ids.split(",") if s.strip()] or None
    log.info(f"\n🔗 Gerando link de afiliado pra: {args.url}")
    if sub_ids:
        log.info(f"   Sub-IDs de rastreio: {sub_ids}")

    r = gerar_link_afiliado(args.url, sub_ids=sub_ids)
    if r["ok"]:
        print(f"\n✅ Link de afiliado gerado:")
        print(f"   {r['short_link']}")
        if r.get("sub_ids"):
            print(f"   Rastreio: {r['sub_ids']}")
    else:
        print(f"\n❌ Falhou: {r['erro']}")
        return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())