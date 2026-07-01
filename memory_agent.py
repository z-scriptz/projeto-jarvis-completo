# agents/memory_agent.py
# Memory Agent v1 do AgenteIA (Jarvis).
#
# Memória de LONGO PRAZO do sistema: registra aprendizados, avaliações
# de vídeos, erros e estratégias em JSONL local + vector store opcional.
# Antes de editar um vídeo, o Jarvis consulta a memória e aplica
# aprendizados anteriores ("não fazer trilha do seed", "preferir cortes
# mais curtos pra Casa/Tech", etc).
#
# Arquitetura:
#   memory/
#   ├── state.json              ← cache leve de estado (gerenciado por terceiros)
#   ├── lessons.jsonl           ← memórias gerais (erros, aprendizados, sistema)
#   ├── creative_lessons.jsonl  ← avaliações de vídeo (pontos bons/ruins/sugestões)
#   └── vector_store/           ← ChromaDB se disponível (opcional)
#
# Tier de busca (fallback gracioso):
#   1. ChromaDB + sentence-transformers (busca vetorial real)
#   2. ChromaDB com embedder default (busca vetorial leve)
#   3. JSONL + TF-IDF (puro Python, sempre funciona)
#
# Filosofia:
#   - NUNCA chama Gemini
#   - NUNCA abre TikTok
#   - NUNCA depende de API externa
#   - Funciona sem ChromaDB, sem sentence-transformers
#   - JSONL é a fonte da verdade; vetor é cache acelerador
#
# Uso direto:
#   python -m agents.memory_agent                       (teste padrão)
#   python -m agents.memory_agent --registrar-teste
#   python -m agents.memory_agent --buscar "edição sem áudio"
#   python -m agents.memory_agent --avaliar-video --produto "X" --video "..."
#   python -m agents.memory_agent --dump                (lista todas as memórias)

import argparse
import json
import re
import sys
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Optional

from shared.logger import get_logger

log = get_logger(__name__)

# =================================================================
# CONFIGURAÇÃO
# =================================================================

PROJETO_ROOT = Path(__file__).parent.parent
MEMORY_DIR   = PROJETO_ROOT / "memory"
LESSONS_PATH          = MEMORY_DIR / "lessons.jsonl"
CREATIVE_LESSONS_PATH = MEMORY_DIR / "creative_lessons.jsonl"
VECTOR_STORE_DIR      = MEMORY_DIR / "vector_store"
PLANS_DIR             = PROJETO_ROOT / "shared" / "content_plans"

# Tipos válidos (não impede outros, mas avisa)
TIPOS_CONHECIDOS = {
    "erro", "aprendizado", "edicao", "performance",
    "estrategia", "asset", "upload", "produto", "sistema", "avaliacao",
}

# Coleções
COLECAO_LESSONS  = "lessons"
COLECAO_CREATIVE = "creative_lessons"

PATH_POR_COLECAO = {
    COLECAO_LESSONS:  LESSONS_PATH,
    COLECAO_CREATIVE: CREATIVE_LESSONS_PATH,
}

# Stopwords PT/EN básicas pra busca por keyword
STOPWORDS = {
    "a", "à", "ao", "aos", "as", "às", "com", "como", "da", "das", "de", "do",
    "dos", "e", "em", "essa", "esse", "está", "este", "eu", "foi", "isso",
    "na", "nas", "no", "nos", "o", "os", "ou", "para", "por", "que", "se",
    "sem", "ser", "só", "também", "tem", "um", "uma", "uns", "umas", "uso",
    "and", "for", "from", "have", "in", "is", "it", "of", "on", "or",
    "the", "this", "to", "was", "with", "you",
}

# Cache de disponibilidade do vetor (lazy)
_VECTOR_STATUS = None  # None = não checado; (bool, str_motivo) depois


# =================================================================
# UTILS
# =================================================================

def _garantir_dirs():
    """Cria memory/ e shared/content_plans/ se não existem. Idempotente."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    PLANS_DIR.mkdir(parents=True, exist_ok=True)


def _gerar_id() -> str:
    """ID único legível: mem_YYYYMMDD_HHMMSS_6chars."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    suf = uuid.uuid4().hex[:6]
    return f"mem_{ts}_{suf}"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _tokenizar(texto: str) -> list[str]:
    """Tokens lowercase, sem pontuação, sem stopwords, len >= 2."""
    if not texto:
        return []
    palavras = re.findall(r"\w+", texto.lower(), flags=re.UNICODE)
    return [p for p in palavras if p not in STOPWORDS and len(p) >= 2]


def _path_da_colecao(colecao: str) -> Path:
    return PATH_POR_COLECAO.get(colecao, LESSONS_PATH)


# =================================================================
# VETOR (opcional)
# =================================================================

def _vector_disponivel() -> tuple[bool, str]:
    """
    Detecta tier de vetor disponível. Resultado cacheado.
    Returns:
        (True, "chromadb+sentence_transformers") → tier 1
        (True, "chromadb_default") → tier 2
        (False, motivo) → tier 3 (JSONL puro)
    """
    global _VECTOR_STATUS
    if _VECTOR_STATUS is not None:
        return _VECTOR_STATUS
    try:
        import chromadb  # noqa: F401
    except ImportError:
        _VECTOR_STATUS = (False, "chromadb não instalado — usando JSONL")
        return _VECTOR_STATUS
    try:
        import sentence_transformers  # noqa: F401
        _VECTOR_STATUS = (True, "chromadb + sentence-transformers")
        return _VECTOR_STATUS
    except ImportError:
        # Chroma tem embedder default ONNX leve
        _VECTOR_STATUS = (True, "chromadb com embedder default")
        return _VECTOR_STATUS


def _indexar_vector(id_: str, texto: str, metadata: dict,
                    colecao: str) -> tuple[bool, str]:
    """Tenta indexar no ChromaDB. Falha silenciosa retornando (False, motivo)."""
    ok, _ = _vector_disponivel()
    if not ok:
        return False, "vector não disponível"

    try:
        import chromadb
        # PersistentClient salva em disco
        client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        col = client.get_or_create_collection(name=colecao)
        # Chroma exige metadata com valores primitivos — sanitiza
        meta_safe = {}
        for k, v in (metadata or {}).items():
            if isinstance(v, (str, int, float, bool)):
                meta_safe[k] = v
            elif isinstance(v, list):
                meta_safe[k] = ",".join(str(x) for x in v[:20])
            else:
                meta_safe[k] = str(v)[:200]
        col.add(ids=[id_], documents=[texto], metadatas=[meta_safe])
        return True, "ok"
    except Exception as e:
        return False, f"erro chromadb: {str(e)[:100]}"


def _buscar_vector(query: str, colecao: str, limite: int = 5,
                   filtros: Optional[dict] = None) -> tuple[list[dict], str]:
    """
    Busca vetorial. Retorna (resultados, motivo).
    resultados: lista de dicts com id, texto, metadata, score.
    """
    ok, motivo = _vector_disponivel()
    if not ok:
        return [], motivo

    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        try:
            col = client.get_collection(name=colecao)
        except Exception:
            return [], f"coleção '{colecao}' não existe no vector store"

        where = None
        if filtros:
            # Chroma só aceita filtros em metadata e operadores específicos
            where = {k: v for k, v in filtros.items()
                     if isinstance(v, (str, int, float, bool))}
            if not where:
                where = None

        res = col.query(query_texts=[query], n_results=limite, where=where)
        ids   = res.get("ids", [[]])[0]
        docs  = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        saida = []
        import math
        for i, id_ in enumerate(ids):
            doc  = docs[i]  if i < len(docs)  else ""
            meta = metas[i] if i < len(metas) else {}
            dist = dists[i] if i < len(dists) else 1.0
            # Distância → score em 0-100 via exp(-dist).
            # Chroma pode retornar distâncias > 1.0 (especialmente cosine
            # quando documentos são curtos), então clamp linear perdia
            # informação. exp(-dist) sempre dá score > 0:
            #   dist=0.0 → score=100 (match perfeito)
            #   dist=0.5 → score= 61
            #   dist=1.0 → score= 37
            #   dist=2.0 → score= 14
            try:
                score = max(1, min(100, int(round(math.exp(-float(dist)) * 100))))
            except Exception:
                score = 1
            saida.append({
                "id":       id_,
                "texto":    doc,
                "metadata": meta or {},
                "score":    score,
                "fonte":    "vector",
            })
        return saida, "ok"
    except Exception as e:
        return [], f"erro busca vetorial: {str(e)[:100]}"


# =================================================================
# JSONL (fonte da verdade)
# =================================================================

def _ler_jsonl(path: Path) -> list[dict]:
    """Lê arquivo JSONL e retorna lista de dicts. Linhas inválidas são puladas."""
    if not path.exists():
        return []
    saida = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    saida.append(json.loads(linha))
                except json.JSONDecodeError:
                    continue  # pula linha corrompida
    except Exception as e:
        log.warning(f"Falha ao ler {path.name}: {e}")
    return saida


def _append_jsonl(path: Path, registro: dict) -> bool:
    """Append atômico (uma linha). Returns True/False."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        log.warning(f"Falha ao escrever em {path.name}: {e}")
        return False


def _score_keyword(query_tokens: set[str], texto: str,
                   tags: list[str]) -> int:
    """
    Score de relevância 0-100 por overlap de tokens + boost por tag exata.

    - Overlap de tokens query ∩ texto: 60% do peso
    - Tag exata na query: boost de 40 pontos por tag
    """
    if not query_tokens:
        return 0
    texto_tokens = set(_tokenizar(texto))
    if not texto_tokens:
        intersec = 0
    else:
        intersec = len(query_tokens & texto_tokens)
    # Normaliza pelo tamanho da query (não pelo do texto, senão favorece curtos)
    overlap_score = (intersec / max(1, len(query_tokens))) * 60

    # Boost por tag exata
    tag_boost = 0
    for tag in (tags or []):
        if not isinstance(tag, str):
            continue
        if tag.lower() in {t.lower() for t in query_tokens}:
            tag_boost += 15  # max 40 com 3+ tags
    tag_boost = min(tag_boost, 40)

    return min(100, int(round(overlap_score + tag_boost)))


def _buscar_jsonl(query: str, colecao: str, limite: int = 5,
                   filtros: Optional[dict] = None) -> list[dict]:
    """Busca no JSONL por relevância (TF-IDF leve)."""
    path = _path_da_colecao(colecao)
    memorias = _ler_jsonl(path)
    if not memorias:
        return []

    query_tokens = set(_tokenizar(query))
    resultados = []

    for mem in memorias:
        # Aplica filtros antes de calcular score (mais barato)
        if filtros:
            descartar = False
            for k, v in filtros.items():
                valor_mem = mem.get(k) or (mem.get("metadata") or {}).get(k)
                if valor_mem is None:
                    descartar = True
                    break
                if isinstance(v, str) and isinstance(valor_mem, str):
                    if v.lower() not in valor_mem.lower():
                        descartar = True
                        break
                elif valor_mem != v:
                    descartar = True
                    break
            if descartar:
                continue

        score = _score_keyword(query_tokens, mem.get("texto", ""),
                                mem.get("tags", []))
        if score > 0:
            resultados.append({
                "id":       mem.get("id", ""),
                "texto":    mem.get("texto", ""),
                "metadata": mem.get("metadata", {}),
                "tags":     mem.get("tags", []),
                "tipo":     mem.get("tipo", ""),
                "timestamp": mem.get("timestamp", ""),
                "score":    score,
                "fonte":    "jsonl",
            })

    resultados.sort(key=lambda x: x["score"], reverse=True)
    return resultados[:limite]


# =================================================================
# API PÚBLICA — 6 funções principais
# =================================================================

def registrar_memoria(tipo: str, texto: str,
                      metadata: Optional[dict] = None,
                      colecao: str = COLECAO_LESSONS,
                      tags: Optional[list[str]] = None) -> dict:
    """
    Registra uma memória no JSONL + indexa no vector se disponível.

    Args:
        tipo:     ver TIPOS_CONHECIDOS (erro, aprendizado, edicao, ...)
        texto:    texto principal da memória (até alguns KB)
        metadata: dict opcional com chaves arbitrárias (produto, nicho, ...)
        colecao:  "lessons" (default) ou "creative_lessons"
        tags:     lista opcional de tags pra busca rápida

    Returns:
        {sucesso, id, jsonl_path, vector_indexado, motivo_vector}
    """
    _garantir_dirs()
    if tipo not in TIPOS_CONHECIDOS:
        log.warning(f"Tipo '{tipo}' não está em TIPOS_CONHECIDOS — registrando mesmo assim")

    if not texto or not isinstance(texto, str):
        return {"sucesso": False, "mensagem": "texto vazio ou inválido"}

    if colecao not in PATH_POR_COLECAO:
        log.warning(f"Coleção '{colecao}' desconhecida — usando '{COLECAO_LESSONS}'")
        colecao = COLECAO_LESSONS

    id_ = _gerar_id()
    registro = {
        "id":        id_,
        "tipo":      tipo,
        "texto":     texto,
        "colecao":   colecao,
        "timestamp": _now_iso(),
        "metadata":  metadata or {},
        "tags":      tags or [],
    }

    path = _path_da_colecao(colecao)
    if not _append_jsonl(path, registro):
        return {"sucesso": False, "mensagem": "falha ao gravar JSONL"}

    # Vector (best-effort)
    meta_pra_vector = dict(registro["metadata"])
    meta_pra_vector.update({"tipo": tipo, "tags": tags or []})
    vector_ok, vector_motivo = _indexar_vector(id_, texto, meta_pra_vector, colecao)

    log.info(f"💾 Memória registrada: {id_} (tipo={tipo}, coleção={colecao}, "
             f"vector={'sim' if vector_ok else 'não'})")

    return {
        "sucesso":           True,
        "id":                id_,
        "jsonl_path":        str(path),
        "vector_indexado":   vector_ok,
        "motivo_vector":     vector_motivo,
    }


def buscar_memorias(query: str, colecao: str = COLECAO_LESSONS,
                    limite: int = 5,
                    filtros: Optional[dict] = None) -> dict:
    """
    Busca memórias relevantes. Tenta vector primeiro, fallback pra JSONL.

    Returns:
        {sucesso, resultados, fonte, total_encontrados, query, colecao}
    """
    _garantir_dirs()
    if not query or not isinstance(query, str):
        return {"sucesso": False, "mensagem": "query vazia",
                "resultados": [], "fonte": "nenhuma"}

    # Tenta vector
    resultados, motivo = _buscar_vector(query, colecao, limite=limite,
                                          filtros=filtros)
    fonte = "vector"
    if not resultados:
        # Fallback JSONL
        resultados = _buscar_jsonl(query, colecao, limite=limite,
                                     filtros=filtros)
        fonte = "jsonl"

    log.info(f"🔍 Busca: '{query[:50]}' → {len(resultados)} resultado(s) "
             f"(fonte={fonte}, motivo_vector={motivo})")

    return {
        "sucesso":            True,
        "query":              query,
        "colecao":            colecao,
        "fonte":              fonte,
        "motivo_vector":      motivo,
        "total_encontrados":  len(resultados),
        "resultados":         resultados,
    }


def registrar_aprendizado_execucao(etapa: str, resultado: dict,
                                    resumo: str,
                                    tags: Optional[list[str]] = None) -> dict:
    """
    Atalho específico pra registrar aprendizado de uma execução
    (ex: rodar o editor, hunter, renderer).

    Args:
        etapa:     nome da etapa (ex: "product_video_editor")
        resultado: dict completo retornado pela função
        resumo:    descrição em linguagem natural ("Editor melhorou em...")
        tags:      lista de tags

    O texto salvo é o resumo. metadata recebe o resultado.
    """
    if not resumo:
        return {"sucesso": False, "mensagem": "resumo vazio"}
    # Sanitiza resultado pra metadata (chaves primitivas)
    meta = {"etapa": etapa}
    if isinstance(resultado, dict):
        for k, v in resultado.items():
            if isinstance(v, (str, int, float, bool)):
                meta[k] = v
            elif isinstance(v, list):
                meta[k] = ",".join(str(x) for x in v[:20])
    return registrar_memoria(
        tipo="aprendizado",
        texto=resumo,
        metadata=meta,
        colecao=COLECAO_LESSONS,
        tags=tags,
    )


def registrar_avaliacao_video(produto: str, video_path: str,
                               pontos_bons: list[str],
                               pontos_ruins: list[str],
                               sugestoes: list[str],
                               score_humano: Optional[int] = None,
                               nicho: str = "") -> dict:
    """
    Avalia um vídeo gerado. Salva em creative_lessons.jsonl + vector.
    Texto gerado automaticamente compõe pontos bons/ruins/sugestões num
    parágrafo legível.
    """
    if not produto:
        return {"sucesso": False, "mensagem": "produto vazio"}

    # Compõe texto narrativo
    partes = [f"Produto: {produto}."]
    if nicho:
        partes.append(f"Nicho: {nicho}.")
    if pontos_bons:
        partes.append("Pontos bons: " + "; ".join(pontos_bons) + ".")
    if pontos_ruins:
        partes.append("Pontos ruins: " + "; ".join(pontos_ruins) + ".")
    if sugestoes:
        partes.append("Sugestões: " + "; ".join(sugestoes) + ".")
    if score_humano is not None:
        partes.append(f"Score humano: {score_humano}/100.")
    texto = " ".join(partes)

    metadata = {
        "produto":      produto,
        "nicho":        nicho or "",
        "video_path":   video_path or "",
        "score_humano": score_humano if score_humano is not None else "",
        "pontos_bons":  ";".join(pontos_bons or []),
        "pontos_ruins": ";".join(pontos_ruins or []),
        "sugestoes":    ";".join(sugestoes or []),
    }
    # Tags automáticas a partir de pontos ruins/sugestões (heurística leve)
    tags = ["avaliacao"]
    texto_lower = texto.lower()
    if "audio" in texto_lower or "áudio" in texto_lower or "som" in texto_lower:
        tags.append("audio")
    if "corte" in texto_lower or "ritmo" in texto_lower:
        tags.append("ritmo")
    if "texto" in texto_lower or "legenda" in texto_lower:
        tags.append("texto")
    if "hook" in texto_lower:
        tags.append("hook")
    if "lent" in texto_lower or "demor" in texto_lower:
        tags.append("performance")

    return registrar_memoria(
        tipo="avaliacao",
        texto=texto,
        metadata=metadata,
        colecao=COLECAO_CREATIVE,
        tags=tags,
    )


def registrar_avaliacao_audio(produto: str, audio_path: str,
                                avaliacao_humana: str = "",
                                score_audio: Optional[int] = None,
                                score_humano: Optional[int] = None,
                                nicho: str = "",
                                tags: Optional[list[str]] = None) -> dict:
    """
    Registra avaliação de uma trilha de áudio usada num vídeo.
    Salva em creative_lessons.jsonl + vector (se disponível).

    Próximas execuções do Audio Selector vão consultar essas memórias
    pra dar BOOST em áudios bem avaliados (e PENALIDADE nos ruins).

    Args:
        produto:           nome do produto
        audio_path:        caminho ou nome do arquivo de áudio
        avaliacao_humana:  texto livre ("áudio combinou bem", "ruim demais")
        score_audio:       score do Audio Selector quando foi escolhido (0-100)
        score_humano:      sua nota subjetiva (0-100). Se None, infere do texto.
        nicho:             nicho do produto (ex: "Casa/Tech") — crítico pra match
        tags:              tags adicionais (sistema infere mais automaticamente)

    Returns: {sucesso, id, jsonl_path, vector_indexado, score_humano_final}
    """
    if not produto or not audio_path:
        return {"sucesso": False, "mensagem": "produto e audio_path são obrigatórios"}

    # Normaliza audio_path → só nome do arquivo (Path/str → nome)
    audio_nome = Path(str(audio_path)).name

    # Se score_humano não veio, infere do texto livre
    if score_humano is None:
        if avaliacao_humana:
            t = avaliacao_humana.lower()
            positivos = ("combin", "bom", "boa", "ótim", "perfeit", "top", "show",
                         "bem", "excelente", "aprovad", "gost", "viral", "encaix")
            negativos = ("ruim", "péssim", "horrív", "feio", "errad", "estranh",
                         "não combin", "fora de", "reprovad", "rejeit")
            if any(p in t for p in negativos):
                score_humano = 25
            elif any(p in t for p in positivos):
                score_humano = 85
            else:
                score_humano = 60  # neutro
        elif score_audio is not None:
            score_humano = int(score_audio)  # usa o score do selector
        else:
            score_humano = 60  # default neutro

    # Compõe texto narrativo (vai pro vetor — busca semântica funciona melhor)
    partes = [f"Áudio: {audio_nome}.", f"Produto: {produto}."]
    if nicho:
        partes.append(f"Nicho: {nicho}.")
    if score_audio is not None:
        partes.append(f"Score do Audio Selector: {score_audio}/100.")
    partes.append(f"Score humano: {score_humano}/100.")
    if avaliacao_humana:
        partes.append(f"Avaliação: {avaliacao_humana}.")
    if score_humano >= 70:
        partes.append("Status: APROVADO — usar novamente em produtos similares.")
    elif score_humano <= 40:
        partes.append("Status: REPROVADO — evitar em produtos similares.")
    else:
        partes.append("Status: NEUTRO — referência fraca.")
    texto = " ".join(partes)

    # Tags automáticas (inferência leve do nome do arquivo)
    tags_auto = list(tags or [])
    tags_auto.append("audio")
    if nicho:
        # tag normalizada do nicho pra busca filtrada: "Casa/Tech" → "nicho_casa_tech"
        nicho_slug = re.sub(r"[^\w]+", "_", nicho.lower()).strip("_")
        if nicho_slug:
            tags_auto.append(f"nicho_{nicho_slug}")
    # Status como tag (filtro rápido)
    if score_humano >= 70:
        tags_auto.append("aprovado")
    elif score_humano <= 40:
        tags_auto.append("reprovado")
    else:
        tags_auto.append("neutro")
    # Termos do nome do arquivo viram tags (hip_hop, loop, drum, etc)
    nome_norm = re.sub(r"[_\-.]+", " ", Path(audio_nome).stem.lower())
    for termo in ("hip hop", "lofi", "lo fi", "house", "trap", "edm",
                   "loop", "drum", "beat", "synth", "ambient", "chill",
                   "electronic", "industrial", "melody", "bass", "808",
                   "acoustic", "band", "marching", "voice", "piano"):
        if termo in nome_norm:
            tags_auto.append(termo.replace(" ", "_"))
    # Dedup preservando ordem
    seen = set()
    tags_finais = []
    for t in tags_auto:
        if t and t not in seen:
            seen.add(t)
            tags_finais.append(t)

    metadata = {
        "produto":           produto,
        "nicho":             nicho or "",
        "audio_path":        audio_nome,
        "score_audio":       score_audio if score_audio is not None else "",
        "score_humano":      score_humano,
        "avaliacao_humana":  avaliacao_humana or "",
        "tipo_avaliacao":    "audio",
        "aprovado":          score_humano >= 70,
    }

    resultado = registrar_memoria(
        tipo="avaliacao",
        texto=texto,
        metadata=metadata,
        colecao=COLECAO_CREATIVE,
        tags=tags_finais,
    )
    resultado["score_humano_final"] = score_humano
    resultado["tags_aplicadas"] = tags_finais
    log.info(f"🎵 Avaliação de áudio registrada: '{audio_nome}' score_humano={score_humano} "
             f"({'APROVADO' if score_humano >= 70 else 'REPROVADO' if score_humano <= 40 else 'neutro'})")
    return resultado


def buscar_audios_aprovados(nicho: str = "", limite: int = 10,
                              apenas_aprovados: bool = True) -> list[dict]:
    """
    Retorna memórias de áudios já avaliados, filtradas por nicho.
    Cada item tem: arquivo, score_humano, tags, aprovado.

    Args:
        nicho:             se informado, filtra só pelo nicho (recomendado)
        limite:            máximo de resultados
        apenas_aprovados:  se True, retorna só score_humano >= 70

    Returns: lista de dicts (vazia se nada encontrado).
    """
    # Estratégia: lê creative_lessons.jsonl e filtra (mais robusto que
    # confiar em filtros vetoriais que variam por versão do Chroma)
    memorias = _ler_jsonl(CREATIVE_LESSONS_PATH)
    aprovados = []

    nicho_norm = (nicho or "").lower().strip()
    for mem in memorias:
        meta = mem.get("metadata") or {}
        if meta.get("tipo_avaliacao") != "audio":
            continue
        # Filtro de nicho (substring case-insensitive)
        if nicho_norm:
            nicho_mem = (meta.get("nicho") or "").lower()
            if nicho_norm not in nicho_mem and nicho_mem not in nicho_norm:
                continue
        score_h = meta.get("score_humano", 0)
        try:
            score_h = int(score_h)
        except (ValueError, TypeError):
            continue
        if apenas_aprovados and score_h < 70:
            continue
        aprovados.append({
            "id":              mem.get("id"),
            "audio_path":      meta.get("audio_path", ""),
            "produto":         meta.get("produto", ""),
            "nicho":           meta.get("nicho", ""),
            "score_humano":    score_h,
            "score_audio":     meta.get("score_audio"),
            "aprovado":        meta.get("aprovado", False),
            "tags":            mem.get("tags") or [],
            "avaliacao":       meta.get("avaliacao_humana", ""),
            "timestamp":       mem.get("timestamp", ""),
        })

    # Ordena por score humano desc + timestamp desc (mais recente vence em empate)
    aprovados.sort(key=lambda x: (x["score_humano"], x.get("timestamp", "")),
                    reverse=True)
    return aprovados[:limite]


def buscar_audios_reprovados(nicho: str = "", limite: int = 10) -> list[dict]:
    """Wrapper de buscar_audios_aprovados pra REJEITADOS (score_humano <= 40)."""
    # Reutiliza lógica mas inverte filtro
    memorias = _ler_jsonl(CREATIVE_LESSONS_PATH)
    reprovados = []
    nicho_norm = (nicho or "").lower().strip()
    for mem in memorias:
        meta = mem.get("metadata") or {}
        if meta.get("tipo_avaliacao") != "audio":
            continue
        if nicho_norm:
            nicho_mem = (meta.get("nicho") or "").lower()
            if nicho_norm not in nicho_mem and nicho_mem not in nicho_norm:
                continue
        score_h = meta.get("score_humano", 100)
        try:
            score_h = int(score_h)
        except (ValueError, TypeError):
            continue
        if score_h > 40:
            continue
        reprovados.append({
            "id":              mem.get("id"),
            "audio_path":      meta.get("audio_path", ""),
            "produto":         meta.get("produto", ""),
            "nicho":           meta.get("nicho", ""),
            "score_humano":    score_h,
            "tags":            mem.get("tags") or [],
            "avaliacao":       meta.get("avaliacao_humana", ""),
        })
    reprovados.sort(key=lambda x: x["score_humano"])
    return reprovados[:limite]


def buscar_contexto_para_tarefa(produto: str, nicho: str, tarefa: str,
                                  limite: int = 5) -> dict:
    """
    Busca contexto relevante pra uma tarefa específica.
    Roda buscas paralelas em ambas as coleções e agrega.
    """
    query = " ".join([x for x in [produto, nicho, tarefa] if x])

    # Busca nas duas coleções e mescla
    r_lessons = buscar_memorias(query=query, colecao=COLECAO_LESSONS,
                                  limite=limite)
    r_creative = buscar_memorias(query=query, colecao=COLECAO_CREATIVE,
                                   limite=limite)

    todos = []
    for r in r_lessons.get("resultados", []):
        todos.append({**r, "colecao": COLECAO_LESSONS})
    for r in r_creative.get("resultados", []):
        todos.append({**r, "colecao": COLECAO_CREATIVE})
    todos.sort(key=lambda x: x.get("score", 0), reverse=True)
    todos = todos[:limite]

    log.info(f"🎯 Contexto pra tarefa '{tarefa}' produto='{produto}': "
             f"{len(todos)} memória(s) relevante(s)")

    return {
        "sucesso":      True,
        "produto":      produto,
        "nicho":        nicho,
        "tarefa":       tarefa,
        "query":        query,
        "memorias":     todos,
        "total":        len(todos),
    }


def gerar_recomendacoes_edicao(produto: str, nicho: str = "",
                                limite_memorias: int = 5) -> dict:
    """
    Agrega sugestões de memórias passadas pra recomendar como editar
    o próximo vídeo desse produto/nicho.

    Estratégia (sem LLM):
        1. Busca memórias de creative_lessons relacionadas
        2. Extrai 'pontos_ruins' e 'sugestoes' dos metadados
        3. Conta frequência → ranqueia
        4. Top-N vira recomendação
        5. Decide preset baseado em frequência de termos
    """
    query = " ".join([x for x in [produto, nicho, "edicao video"] if x])

    busca = buscar_memorias(query=query, colecao=COLECAO_CREATIVE,
                              limite=limite_memorias * 2)  # busca mais e depois ranqueia
    memorias = busca.get("resultados", [])

    # Coleta sugestões + pontos ruins (transformados em "evitar X")
    sugestoes_coletadas = []
    contador_termos = Counter()
    memorias_usadas = []

    for mem in memorias[:limite_memorias]:
        memorias_usadas.append({
            "id":    mem.get("id"),
            "texto": mem.get("texto", "")[:140],
            "score": mem.get("score", 0),
        })
        meta = mem.get("metadata") or {}
        # Sugestões diretas — peso alto
        sugestoes_str = meta.get("sugestoes") or ""
        for s in sugestoes_str.split(";"):
            s = s.strip()
            if s:
                sugestoes_coletadas.append(s)
        # Pontos ruins viram "evitar"
        pontos_ruins_str = meta.get("pontos_ruins") or ""
        for p in pontos_ruins_str.split(";"):
            p = p.strip()
            if p:
                sugestoes_coletadas.append(f"evitar: {p}")
        # Acumula termos pra escolher preset
        for tag in mem.get("tags") or []:
            contador_termos[tag.lower()] += 1

    # Dedup com contagem (preservando ordem por frequência)
    contagem_sug = Counter(sugestoes_coletadas)
    recomendacoes = [s for s, _ in contagem_sug.most_common(8)]

    # Decide preset sugerido baseado em heurística simples
    preset_sugerido = "viral_produto"
    if contador_termos.get("ritmo", 0) >= 2 or contador_termos.get("audio", 0) >= 2:
        preset_sugerido = "viral_produto_agressivo"
    elif contador_termos.get("hook", 0) >= 2:
        preset_sugerido = "viral_produto_hook_forte"

    # Se não tem memória nenhuma, dá recomendação base
    if not recomendacoes:
        recomendacoes = [
            "Sem memórias prévias — comece com preset viral_produto",
            "Adicione áudio real (Pixabay/Mixkit) — fake do seed quebra",
            "Use cortes curtos (2-4s por cena)",
            "Hook de impacto nos primeiros 1-2s",
        ]

    log.info(f"💡 {len(recomendacoes)} recomendação(ões) pra produto='{produto}', "
             f"nicho='{nicho}', preset_sugerido='{preset_sugerido}'")

    return {
        "produto":         produto,
        "nicho":           nicho,
        "memorias_usadas": memorias_usadas,
        "recomendacoes":   recomendacoes,
        "preset_sugerido": preset_sugerido,
        "total_memorias_consultadas": len(memorias),
        "timestamp":       _now_iso(),
    }


# =================================================================
# RELATÓRIO + CLI
# =================================================================

def salvar_resultado(resultado: dict) -> Optional[str]:
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        path = PLANS_DIR / "memory_agent_resultado.json"
        path.write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return str(path)
    except Exception as e:
        log.warning(f"Falha ao salvar: {e}")
        return None


def imprimir_relatorio(rel: dict):
    print("\n" + "=" * 60)
    print(f"  🧠 MEMORY AGENT — Relatório")
    print("=" * 60)

    ok, motivo = _vector_disponivel()
    print(f"  Vector store: {'✅ ' + motivo if ok else '❌ ' + motivo}")
    print(f"  JSONL:        ✅ sempre disponível")

    if "memoria_registrada" in rel:
        m = rel["memoria_registrada"]
        print(f"\n  📝 Memória teste registrada:")
        print(f"     ID:      {m.get('id', '?')}")
        print(f"     Path:    {m.get('jsonl_path', '?')}")

    if "busca" in rel:
        b = rel["busca"]
        print(f"\n  🔍 Busca por '{b.get('query', '?')[:50]}':")
        print(f"     Fonte: {b.get('fonte', '?')}, encontrados: {b.get('total_encontrados', 0)}")
        for r in b.get("resultados", [])[:3]:
            print(f"     • [score={r.get('score', 0):3d}] {r.get('texto', '')[:80]}...")

    if "avaliacao" in rel:
        a = rel["avaliacao"]
        print(f"\n  🎬 Avaliação de vídeo:")
        print(f"     ID:    {a.get('id', '?')}")
        print(f"     Path:  {a.get('jsonl_path', '?')}")

    if "recomendacoes" in rel:
        r = rel["recomendacoes"]
        print(f"\n  💡 Recomendações pra próxima edição (produto: {r['produto']}):")
        print(f"     Preset sugerido: {r['preset_sugerido']}")
        print(f"     Memórias usadas: {len(r['memorias_usadas'])}")
        for i, rec in enumerate(r["recomendacoes"], 1):
            print(f"     {i}. {rec}")

    if "dump" in rel:
        d = rel["dump"]
        print(f"\n  📚 Dump completo:")
        print(f"     lessons.jsonl:          {d.get('lessons_count', 0)} entrada(s)")
        print(f"     creative_lessons.jsonl: {d.get('creative_count', 0)} entrada(s)")

    print(f"\n  💾 Detalhes: shared/content_plans/memory_agent_resultado.json")
    print("=" * 60)


def _executar_teste_padrao() -> dict:
    """
    Roda o pipeline completo de teste:
      1. Registra memória teste
      2. Busca por ela
      3. Registra avaliação real do Mini Aspirador
      4. Gera recomendações
    """
    resultado = {}

    # 1. Memória teste
    log.info("\n1️⃣  Registrando memória teste...")
    m1 = registrar_memoria(
        tipo="aprendizado",
        texto="Asset Hunter funciona bem com seed fake, mas é importante "
              "substituir por clipes reais antes de renderizar produção.",
        metadata={"etapa": "asset_hunter", "produto": "Mini Aspirador de Teclado"},
        tags=["asset", "seed", "mini_aspirador"],
    )
    resultado["memoria_registrada"] = m1

    # 2. Busca
    log.info("\n2️⃣  Buscando por 'asset hunter seed'...")
    busca = buscar_memorias(query="asset hunter seed mini aspirador", limite=3)
    resultado["busca"] = busca

    # 3. Avaliação real do Mini Aspirador (primeira memória real)
    log.info("\n3️⃣  Registrando avaliação do vídeo do Mini Aspirador...")
    av = registrar_avaliacao_video(
        produto="Mini Aspirador de Teclado",
        video_path="C:\\AgenteIA\\videos\\mini_aspirador_de_teclado_edited.mp4",
        pontos_bons=[
            "renderer cru funcionou tecnicamente",
            "editor adicionou textos por cena, punch-in e CTA sintético",
            "yuv420p export funcionou",
            "MoviePy 2.x compat OK",
        ],
        pontos_ruins=[
            "sem áudio (trilha do seed era fake)",
            "ritmo ainda simples",
            "texto pouco impactante",
            "render lento (105s no preset medium)",
            "vídeo ainda não prende público",
        ],
        sugestoes=[
            "usar trilha de áudio real (Pixabay/Mixkit)",
            "cortes mais agressivos (1.5-2.5s por cena)",
            "hook mais forte no primeiro segundo",
            "preset viral_produto_agressivo",
            "preset ultrafast pra render rápido",
        ],
        score_humano=45,
        nicho="Casa/Tech",
    )
    resultado["avaliacao"] = av

    # 4. Recomendações
    log.info("\n4️⃣  Gerando recomendações pro próximo vídeo...")
    rec = gerar_recomendacoes_edicao(
        produto="Mini Aspirador de Teclado",
        nicho="Casa/Tech",
    )
    resultado["recomendacoes"] = rec

    return resultado


def main():
    parser = argparse.ArgumentParser(
        description="Memory Agent — memória de longo prazo do Jarvis"
    )
    parser.add_argument("--registrar-teste", action="store_true",
                        help="Roda só o teste de registrar memória")
    parser.add_argument("--buscar", default="",
                        help="Busca memórias por query")
    parser.add_argument("--colecao", default=COLECAO_LESSONS,
                        choices=[COLECAO_LESSONS, COLECAO_CREATIVE],
                        help="Coleção pra buscar")
    parser.add_argument("--limite", type=int, default=5,
                        help="Limite de resultados na busca")
    parser.add_argument("--avaliar-video", action="store_true",
                        help="Registra avaliação manual de um vídeo")
    parser.add_argument("--produto", default="Mini Aspirador de Teclado",
                        help="Nome do produto pra --avaliar-video ou --recomendar")
    parser.add_argument("--nicho", default="Casa/Tech",
                        help="Nicho do produto")
    parser.add_argument("--video", default="",
                        help="Path do vídeo pra --avaliar-video")
    parser.add_argument("--recomendar", action="store_true",
                        help="Gera recomendações pra próximo vídeo")
    parser.add_argument("--dump", action="store_true",
                        help="Lista todas as memórias salvas")
    args = parser.parse_args()

    _garantir_dirs()
    log.info("=" * 60)
    log.info("🧠 MEMORY AGENT v1")
    log.info("=" * 60)

    resultado = {}

    # Modo: --buscar avulso
    if args.buscar:
        r = buscar_memorias(query=args.buscar, colecao=args.colecao,
                              limite=args.limite)
        resultado["busca"] = r

    # Modo: --avaliar-video (input mínimo via CLI; produção real seria via dict)
    elif args.avaliar_video:
        r = registrar_avaliacao_video(
            produto=args.produto,
            video_path=args.video,
            pontos_bons=["render técnico funcionou"],
            pontos_ruins=["avaliação stub via CLI — edite o JSONL pra detalhes"],
            sugestoes=["use a API programática pra avaliação detalhada"],
            nicho=args.nicho,
        )
        resultado["avaliacao"] = r

    # Modo: --recomendar
    elif args.recomendar:
        r = gerar_recomendacoes_edicao(produto=args.produto, nicho=args.nicho)
        resultado["recomendacoes"] = r

    # Modo: --dump
    elif args.dump:
        lessons = _ler_jsonl(LESSONS_PATH)
        creative = _ler_jsonl(CREATIVE_LESSONS_PATH)
        resultado["dump"] = {
            "lessons_count":  len(lessons),
            "creative_count": len(creative),
            "lessons":        lessons,
            "creative":       creative,
        }

    # Modo: --registrar-teste (só item 1)
    elif args.registrar_teste:
        m1 = registrar_memoria(
            tipo="sistema",
            texto="Teste de registro de memória — pipeline JSONL funcionando",
            metadata={"teste": True},
            tags=["teste", "sistema"],
        )
        resultado["memoria_registrada"] = m1

    # Default: teste padrão completo
    else:
        resultado = _executar_teste_padrao()

    salvar_resultado(resultado)
    imprimir_relatorio(resultado)

    return 0 if resultado else 2


if __name__ == "__main__":
    sys.exit(main())