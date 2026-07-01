# creative_engine/semantic_catalog.py
# Catálogo Semântico do AgenteIA (Jarvis) — "memória visual" do Jarvis.
#
# PROBLEMA QUE RESOLVE:
#   Hoje o Jarvis busca B-roll por QUERY EXATA em tempo real ("vegetable
#   chopper"). Se a palavra não bate com a tag do banco, não acha — e buscar
#   ao vivo a cada vídeo é lento e repetitivo. Pior: query literal não entende
#   CONCEITO (pede "fundo futurista", não acha "cyberpunk"/"neon"/"tech").
#
# O QUE FAZ:
#   Mantém um CATÁLOGO LOCAL dos clipes do Pexels/Pixabay (título + tags + URL),
#   indexado por EMBEDDING semântico no ChromaDB. A busca passa a ser por
#   CONCEITO: "fundo futurista" acha clipes com tag "cyberpunk" mesmo sem a
#   palavra exata, porque caem perto no espaço vetorial.
#
# POR QUE LOCAL (sentence-transformers, não API):
#   - Custo ZERO por vetor (catálogo pode ser enorme sem gastar)
#   - Offline, sem rate limit, sem mais uma quota pra estourar
#   - Modelo multilíngue: PT da busca casa com EN das tags (mesmo espaço)
#
# FONTES (100% com API oficial — sem scraping, sem violar termos):
#   - Pexels  (PEXELS_API_KEY)   — reusa buscar_pexels do asset_autopilot
#   - Pixabay (PIXABAY_API_KEY)  — reusa buscar_pixabay do asset_autopilot
#
# FLUXO:
#   indexar():  API → texto rico (título+tags+nicho) → embedding local →
#               ChromaDB (vetor + metadados: url, fonte, tipo, duração...)
#   buscar():   conceito → embedding → ChromaDB acha os N mais próximos
#
# CLI:
#   python -m creative_engine.semantic_catalog --indexar --nicho "Cozinha"
#   python -m creative_engine.semantic_catalog --indexar --query "vegetable chopper"
#   python -m creative_engine.semantic_catalog --buscar "fundo futurista tech"
#   python -m creative_engine.semantic_catalog --stats

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:  # permite testar isolado
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("semantic_catalog")

PROJETO_ROOT = Path(__file__).parent.parent
# ChromaDB persiste em disco aqui (sobrevive entre execuções)
CHROMA_DIR = PROJETO_ROOT / "shared" / "semantic_catalog_db"
COLLECTION_NOME = "broll_catalog"

# Modelo de embedding LOCAL multilíngue (PT+EN no mesmo espaço vetorial).
# ~120MB, baixado uma vez pelo sentence-transformers no primeiro uso.
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


# =================================================================
# EMBEDDINGS LOCAIS (sentence-transformers) — singleton
# =================================================================
# Carrega o modelo UMA vez (custa ~1-2s + RAM). Reusa em todas as chamadas.

_modelo_emb = None


def _get_modelo_embedding():
    """Carrega o modelo de embedding local (singleton). Lança erro claro se faltar a lib."""
    global _modelo_emb
    if _modelo_emb is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError(
                "sentence-transformers não instalado. "
                "Rode: pip install sentence-transformers")
        log.info(f"   🧠 Carregando modelo de embedding '{EMBEDDING_MODEL}' "
                 f"(1ª vez baixa ~120MB)...")
        _modelo_emb = SentenceTransformer(EMBEDDING_MODEL)
        log.info(f"   ✅ Modelo carregado")
    return _modelo_emb


def gerar_embedding(texto: str) -> list:
    """Gera o vetor de embedding de um texto (lista de floats)."""
    modelo = _get_modelo_embedding()
    # normalize_embeddings=True → vetores unitários, melhora busca por cosseno
    vec = modelo.encode(texto, normalize_embeddings=True)
    return vec.tolist()


def gerar_embeddings_lote(textos: list) -> list:
    """Gera embeddings de vários textos de uma vez (mais rápido que 1 a 1)."""
    modelo = _get_modelo_embedding()
    vecs = modelo.encode(textos, normalize_embeddings=True,
                         batch_size=32, show_progress_bar=False)
    return [v.tolist() for v in vecs]


# =================================================================
# CHROMADB — banco vetorial persistente
# =================================================================

_chroma_client = None


def _get_chroma_collection():
    """
    Retorna a collection do ChromaDB (cria se não existir). Persiste em disco.
    Usa distância de cosseno (boa pra embeddings normalizados de texto).
    """
    global _chroma_client
    try:
        import chromadb
    except ImportError:
        raise RuntimeError("chromadb não instalado. Rode: pip install chromadb")

    if _chroma_client is None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # get_or_create: idempotente. metadata define a métrica de distância.
    collection = _chroma_client.get_or_create_collection(
        name=COLLECTION_NOME,
        metadata={"hnsw:space": "cosine"})
    return collection


# =================================================================
# TEXTO RICO — o que vira embedding
# =================================================================

def _montar_texto_rico(item: dict) -> str:
    """
    Monta o texto que será embeddado a partir dos dados do clipe.
    Junta título + tags + nicho + cena num só texto, porque o embedding
    captura o SIGNIFICADO do conjunto. Quanto mais contexto relevante,
    melhor a busca por conceito.

    Espera um item no formato (estendido do buscar_pexels/buscar_pixabay):
      {url, id, owner, tipo, fonte, query, titulo?, tags?, nicho?, cena?, duracao?}
    """
    partes = []
    if item.get("titulo"):
        partes.append(str(item["titulo"]))
    # tags podem vir como lista ou string
    tags = item.get("tags")
    if isinstance(tags, (list, tuple)):
        partes.append(" ".join(str(t) for t in tags))
    elif isinstance(tags, str) and tags.strip():
        partes.append(tags)
    if item.get("query"):
        partes.append(str(item["query"]))
    if item.get("nicho"):
        partes.append(str(item["nicho"]))
    if item.get("cena"):
        partes.append(str(item["cena"]))
    texto = " | ".join(p for p in partes if p).strip()
    # fallback: se não veio nada textual, usa a query ou o id
    return texto or str(item.get("query") or item.get("id") or "video")


def _id_unico(item: dict) -> str:
    """
    ID determinístico do clipe no catálogo: fonte + id da fonte.
    Determinístico = re-indexar o mesmo clipe SOBRESCREVE (não duplica).
    """
    fonte = item.get("fonte", "?")
    sid = item.get("id", "")
    if sid:
        return f"{fonte}:{sid}"
    # sem id da fonte → usa hash da url (estável)
    import hashlib
    url = str(item.get("url", ""))
    return f"{fonte}:{hashlib.md5(url.encode()).hexdigest()[:12]}"


# =================================================================
# INDEXAÇÃO
# =================================================================

def indexar_itens(itens: list) -> dict:
    """
    Indexa uma lista de itens (clipes) no catálogo semântico.

    Cada item deve ter pelo menos {url, fonte} e idealmente {titulo, tags,
    tipo, query, nicho, duracao}. IDs determinísticos: re-indexar = atualizar
    (upsert), nunca duplica.

    Returns: {indexados, ignorados, total}
    """
    if not itens:
        return {"indexados": 0, "ignorados": 0, "total": 0}

    collection = _get_chroma_collection()

    # Monta os textos ricos e filtra itens sem URL (inúteis).
    # DEDUP POR ID: o mesmo clipe pode vir de várias queries (ex: um vídeo
    # casa com "vegetable chopper closeup" E "kitchen gadget detail"). O
    # ChromaDB exige IDs únicos DENTRO do mesmo upsert, então ficamos só com
    # a 1ª ocorrência de cada ID (e ainda economiza embeddings).
    ids, textos, metadatas = [], [], []
    ignorados = 0
    duplicados = 0
    vistos = set()
    for item in itens:
        if not item.get("url"):
            ignorados += 1
            continue
        _id = _id_unico(item)
        if _id in vistos:
            duplicados += 1
            continue
        vistos.add(_id)
        ids.append(_id)
        textos.append(_montar_texto_rico(item))
        # ChromaDB metadata: só aceita tipos simples (str/int/float/bool)
        tags = item.get("tags")
        tags_str = (" ".join(map(str, tags)) if isinstance(tags, (list, tuple))
                    else str(tags or ""))
        metadatas.append({
            "url":      str(item.get("url", "")),
            "fonte":    str(item.get("fonte", "?")),
            "tipo":     str(item.get("tipo", "video")),
            "titulo":   str(item.get("titulo", ""))[:300],
            "tags":     tags_str[:500],
            "query":    str(item.get("query", "")),
            "nicho":    str(item.get("nicho", "")),
            "owner":    str(item.get("owner", "")),
            "duracao":  float(item.get("duracao", 0) or 0),
            "indexado_em": datetime.now().isoformat(timespec="seconds"),
        })

    if duplicados:
        log.info(f"   ♻️  {duplicados} clipe(s) repetido(s) entre queries — "
                 f"mantido 1 de cada")

    if not ids:
        return {"indexados": 0, "ignorados": ignorados,
                "duplicados": duplicados, "total": len(itens)}

    # Gera embeddings em LOTE (bem mais rápido que 1 a 1)
    log.info(f"   🧮 Gerando {len(textos)} embedding(s) (local)...")
    embeddings = gerar_embeddings_lote(textos)

    # upsert: insere novos, atualiza existentes (mesmo id). Nunca duplica.
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=textos,
        metadatas=metadatas)

    log.info(f"   ✅ {len(ids)} clipe(s) indexado(s) no catálogo")
    return {"indexados": len(ids), "ignorados": ignorados,
            "duplicados": duplicados, "total": len(itens)}


# =================================================================
# BUSCA SEMÂNTICA
# =================================================================

def buscar(conceito: str, n: int = 5,
           tipo: Optional[str] = None,
           fonte: Optional[str] = None,
           score_minimo: float = 0.0) -> list:
    """
    Busca os N clipes mais próximos do CONCEITO (não da palavra exata).

    Ex: buscar("fundo futurista") acha clipes com tag "cyberpunk", "neon",
    "technology" — porque caem perto no espaço semântico.

    Args:
        conceito: o que você procura, em PT ou EN, livre ("fundo futurista tech")
        n:        quantos resultados retornar
        tipo:     filtra por "video" ou "photo" (opcional)
        fonte:    filtra por "pexels"/"pixabay" (opcional)
        score_minimo: THRESHOLD de segurança (0..1). Resultados com score abaixo
                  disso são DESCARTADOS. Evita o "bolo de chocolate devolve pele
                  bonita": quando o catálogo não tem nada relevante, todos os
                  scores ficam baixos (<0.2) e são cortados → retorna vazio, e o
                  caller sabe que precisa buscar em outra fonte. 0.0 = sem corte.

    Returns: lista de {url, fonte, tipo, titulo, tags, score, ...} ordenada
             do mais relevante pro menos. score: 0..1 (1 = idêntico).
    """
    collection = _get_chroma_collection()

    # Monta filtro de metadados (ChromaDB 'where')
    filtro = {}
    if tipo:
        filtro["tipo"] = tipo
    if fonte:
        filtro["fonte"] = fonte
    where = filtro or None

    # Embedda a busca e consulta o ChromaDB
    emb_busca = gerar_embedding(conceito)
    res = collection.query(
        query_embeddings=[emb_busca],
        n_results=n,
        where=where)

    saida = []
    # ChromaDB retorna listas-de-listas (1 por query). Pegamos a query 0.
    ids = (res.get("ids") or [[]])[0]
    metadatas = (res.get("metadatas") or [[]])[0]
    distancias = (res.get("distances") or [[]])[0]
    documentos = (res.get("documents") or [[]])[0]

    for i, _id in enumerate(ids):
        md = metadatas[i] if i < len(metadatas) else {}
        dist = distancias[i] if i < len(distancias) else 1.0
        # distância de cosseno → similaridade (0..1). Quanto menor a dist, melhor.
        score = round(1.0 - float(dist), 3)
        # THRESHOLD: corta o que está abaixo do mínimo (lixo de baixa relevância)
        if score < score_minimo:
            continue
        saida.append({
            "id":      _id,
            "url":     md.get("url", ""),
            "fonte":   md.get("fonte", "?"),
            "tipo":    md.get("tipo", ""),
            "titulo":  md.get("titulo", ""),
            "tags":    md.get("tags", ""),
            "nicho":   md.get("nicho", ""),
            "duracao": md.get("duracao", 0),
            "score":   score,
            "texto_indexado": documentos[i] if i < len(documentos) else "",
        })
    return saida


# =================================================================
# ESTATÍSTICAS
# =================================================================

def stats() -> dict:
    """Retorna estatísticas do catálogo (quantos clipes, por fonte, por tipo)."""
    collection = _get_chroma_collection()
    total = collection.count()
    info = {"total": total, "por_fonte": {}, "por_tipo": {}}
    if total == 0:
        return info
    # puxa todos os metadados (sem embeddings, leve) pra contar
    try:
        dados = collection.get(include=["metadatas"])
        for md in dados.get("metadatas", []):
            f = md.get("fonte", "?")
            t = md.get("tipo", "?")
            info["por_fonte"][f] = info["por_fonte"].get(f, 0) + 1
            info["por_tipo"][t] = info["por_tipo"].get(t, 0) + 1
    except Exception as e:
        log.warning(f"   ⚠️  Falha ao agregar stats: {e}")
    return info


# =================================================================
# COLETA DAS APIS (reusa o asset_autopilot — sem duplicar lógica)
# =================================================================

def coletar_das_apis(query: str, tipo: str = "video",
                     limite: int = 10, nicho: str = "") -> list:
    """
    Coleta candidatos do Pexels + Pixabay reusando as funções do autopilot.
    Enriquece cada item com titulo/tags/nicho pra alimentar o embedding.

    NÃO baixa o vídeo — só pega os METADADOS + URL (leve, rápido, legal).
    O download real continua sendo do asset_autopilot quando o clipe for usado.
    """
    itens = []
    try:
        from agents.asset_autopilot_agent import buscar_pexels, buscar_pixabay
    except Exception as e:
        log.warning(f"   ⚠️  Não consegui importar buscas do autopilot ({e})")
        return itens

    for fonte_fn in (buscar_pexels, buscar_pixabay):
        try:
            res = fonte_fn(query, tipo=tipo, limite=limite)
        except Exception as e:
            log.warning(f"   ⚠️  {fonte_fn.__name__} falhou: {e}")
            continue
        for r in res:
            # enriquece: o autopilot já traz query/fonte; adiciona nicho
            r.setdefault("titulo", r.get("query", ""))
            r.setdefault("tags", r.get("query", ""))
            r["nicho"] = nicho
            itens.append(r)
    return itens


# =================================================================
# CLI
# =================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Catálogo Semântico Jarvis — indexa e busca B-roll por CONCEITO")
    parser.add_argument("--indexar", action="store_true",
                        help="Coleta das APIs e indexa no catálogo")
    parser.add_argument("--query", default="",
                        help="Query de coleta nas APIs (ex: 'vegetable chopper')")
    parser.add_argument("--nicho", default="",
                        help="Nicho pra enriquecer o contexto (ex: 'Cozinha')")
    parser.add_argument("--tipo", default="video", choices=["video", "photo"],
                        help="Tipo de asset (default: video)")
    parser.add_argument("--limite", type=int, default=10,
                        help="Quantos itens coletar por fonte (default 10)")
    parser.add_argument("--buscar", default="",
                        help="Busca semântica por CONCEITO (ex: 'fundo futurista')")
    parser.add_argument("--n", type=int, default=5,
                        help="Quantos resultados na busca (default 5)")
    parser.add_argument("--score-min", type=float, default=0.0, dest="score_min",
                        help="Threshold de relevância 0..1. Descarta resultados "
                             "abaixo disso (ex: 0.35). Default 0 (sem corte)")
    parser.add_argument("--stats", action="store_true",
                        help="Mostra estatísticas do catálogo")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("🧠 CATÁLOGO SEMÂNTICO JARVIS")
    log.info("=" * 60)

    if args.stats:
        s = stats()
        print(f"\n📊 Catálogo: {s['total']} clipe(s)")
        if s["por_fonte"]:
            print("   Por fonte:", dict(s["por_fonte"]))
        if s["por_tipo"]:
            print("   Por tipo:", dict(s["por_tipo"]))
        return 0

    if args.indexar:
        if not args.query:
            parser.error("--indexar precisa de --query (ex: --query 'vegetable chopper')")
        log.info(f"\n📥 Coletando '{args.query}' (tipo={args.tipo}, nicho='{args.nicho}')...")
        itens = coletar_das_apis(args.query, tipo=args.tipo,
                                 limite=args.limite, nicho=args.nicho)
        log.info(f"   📦 {len(itens)} candidato(s) coletado(s) das APIs")
        if not itens:
            log.warning("   ⚠️  Nada coletado (sem PEXELS_API_KEY/PIXABAY_API_KEY?)")
            return 1
        r = indexar_itens(itens)
        log.info(f"\n✅ Indexação: {r['indexados']} novo(s)/atualizado(s), "
                 f"{r['ignorados']} ignorado(s)")
        return 0

    if args.buscar:
        log.info(f"\n🔍 Buscando por conceito: '{args.buscar}'"
                 + (f" (score mínimo: {args.score_min})" if args.score_min else ""))
        resultados = buscar(args.buscar, n=args.n, tipo=args.tipo,
                            score_minimo=args.score_min)
        if not resultados:
            if args.score_min:
                print(f"   🛑 Nenhum clipe passou do score mínimo ({args.score_min}).")
                print(f"      O catálogo não tem nada suficientemente relevante pra "
                      f"'{args.buscar}'.")
                print(f"      (Isso é o threshold funcionando — melhor não ter resultado "
                      f"do que ter um clipe errado.)")
            else:
                print("   (nada encontrado — catálogo vazio? indexe primeiro com --indexar)")
            return 0
        print(f"\n🎯 {len(resultados)} resultado(s) por relevância:\n")
        for i, r in enumerate(resultados, 1):
            print(f"  {i}. [score {r['score']}] {r['fonte']} ({r['tipo']})")
            print(f"     {r['titulo'] or r['texto_indexado'][:60]}")
            print(f"     tags: {r['tags'][:80]}")
            print(f"     url:  {r['url'][:90]}")
            print()
        return 0

    parser.error("escolha uma ação: --indexar, --buscar, ou --stats")


if __name__ == "__main__":
    sys.exit(main())