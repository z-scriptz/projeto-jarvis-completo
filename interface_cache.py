# brain/interface_cache.py
# Cache visual / Interface Memory do AgenteIA (Jarvis)
#
# Objetivo: reduzir chamadas Gemini Vision reaproveitando coordenadas
# já confirmadas de elementos de UI repetitivos (Select file, campo de
# legenda, botão Publicar, etc).
#
# Filosofia: cache complementa Gemini, NUNCA substitui.
#   - Cache hit  → tenta usar coordenada salva (rápido, free)
#   - Cache miss → cai pra Gemini (custa cota mas é robusto)
#   - Cache fail → invalida, marca falha, registra pra revisão
#
# Validação semântica (importante!):
#   "Clique executado pelo PyAutoGUI" ≠ "Clique acertou o elemento certo"
#   Para ações críticas (Select file, Publicar, etc), o caller deve
#   pendurar o sucesso via registrar_sucesso_pendente() e só confirmar
#   depois que validar semanticamente que a ação produziu o efeito
#   esperado (diálogo abriu, tela mudou, campo preencheu, etc).
#
# Segurança crítica:
#   - Elementos cuja chave contenha "publicar/postar/publish/post"
#     SÓ entregam coordenada se o chamador passar guard_aprovado=True.
#     Isso é defesa em profundidade contra clique acidental no Publicar.
#
# Storage: refs/interface_cache.json (JSON simples, versionável)
#
# Uso típico (com validação):
#   from brain.interface_cache import (
#       buscar_elemento_cache,
#       registrar_sucesso_pendente,
#       confirmar_clique_pendente,
#       descartar_clique_pendente,
#       registrar_falha,
#   )
#
#   # Antes do Gemini, tenta cache:
#   cached = buscar_elemento_cache(alvo="Select file", contexto="pagina_upload")
#   if cached:
#       clicar(cached.x, cached.y)
#       registrar_sucesso_pendente(alvo, contexto, x, y, "alta")
#       # ... mais tarde, depois de checar que diálogo abriu:
#       if dialogo_abriu:
#           confirmar_clique_pendente(alvo, contexto)
#       else:
#           descartar_clique_pendente(alvo, contexto)
#           registrar_falha(alvo, contexto, motivo="diálogo não abriu")

import json
import re
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from shared.logger import get_logger

log = get_logger(__name__)


# =================================================================
# CONFIGURAÇÃO
# =================================================================

CACHE_DIR  = Path(__file__).parent.parent / "refs"
CACHE_FILE = CACHE_DIR / "interface_cache.json"

# TTL: coordenadas mais antigas que isso são revalidadas via Gemini
TTL_DIAS = 30

# Limites de confiabilidade
MAX_FALHAS_PERMITIDAS = 2     # falhas > isso → marca como desconfiável
MIN_SUCESSOS_PARA_USO = 1     # precisa ter ao menos 1 sucesso pra entregar
MAX_FALHAS_DESCONFIAVEL = 3   # falhas >= isso → desconfiavel=True

# Confianças aceitas para ENTREGAR cache (baixa nunca é entregue)
CONFIANCAS_ACEITAS = ("alta", "media", "média")

# Termos que indicam ação destrutiva — exigem aprovação extra
TERMOS_PUBLICACAO = (
    "publicar", "postar", "publish", "post",
    "enviar", "compartilhar", "submit",
)

# Termos que indicam ações cujo "clique" pode passar sem realmente
# ter acertado o elemento certo. Para esses, o cache exige validação
# semântica do caller antes de reforçar o sucesso.
# Ex.: "Select file" — PyAutoGUI clica nas coordenadas, mas se for o
# canto da página (em vez do botão azul), o diálogo de arquivo NÃO abre.
# O caller precisa verificar e confirmar/descartar o clique.
TERMOS_VALIDACAO_SEMANTICA = (
    "select file", "selecionar video", "selecionar vídeo", "selecionar arquivo",
    "upload", "carregar", "escolher arquivo", "choose file",
    "publicar", "postar", "publish", "post",
    "enviar", "compartilhar", "submit",
    "salvar", "save", "confirmar", "confirm",
    "excluir", "deletar", "delete", "remover",
)

# Padrão pra remover emojis e símbolos
_PADRAO_EMOJI = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002700-\U000027BF"
    "\U0001F900-\U0001F9FF"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE,
)


# =================================================================
# NORMALIZAÇÃO DE CHAVE
# =================================================================

def _normalizar(texto: str) -> str:
    """Normaliza texto: lowercase, sem acento, sem emoji, com underscore."""
    if not texto:
        return ""
    s = texto.lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _PADRAO_EMOJI.sub(" ", s)
    s = re.sub(r"[^\w\s-]", " ", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s[:80]  # limita parte do alvo


def gerar_chave_cache(alvo: str, contexto: str) -> str:
    """
    Gera chave estável a partir de alvo + contexto.

    Exemplos:
        ("Select file", "pagina_upload_tiktok")
            → "pagina_upload_tiktok__select_file"
        ("campo de descrição do vídeo...", "tela_detalhes_tiktok_apos_upload")
            → "tela_detalhes_tiktok_apos_upload__campo_de_descricao_do_video"
    """
    ctx       = _normalizar(contexto) or "global"
    alvo_norm = _normalizar(alvo)     or "elemento"
    return f"{ctx}__{alvo_norm}"


def _eh_acao_destrutiva(chave_ou_alvo: str) -> bool:
    """Detecta se a chave/alvo envolve ação destrutiva (Publicar, Postar, etc)."""
    s = chave_ou_alvo.lower()
    return any(termo in s for termo in TERMOS_PUBLICACAO)


def exige_validacao_semantica(alvo: str) -> bool:
    """
    Determina se um alvo requer validação semântica pós-clique.

    Para alvos como "Select file" / "Publicar", PyAutoGUI clicar
    nas coordenadas NÃO garante que o elemento certo foi acertado.
    O caller deve verificar o efeito (diálogo abriu, tela mudou, etc)
    antes de confirmar o sucesso no cache.

    Args:
        alvo: texto do elemento (ex: "Select file", "Publicar")

    Returns:
        True se o alvo está na lista de ações críticas conhecidas.
    """
    if not alvo:
        return False
    s = alvo.lower()
    return any(termo in s for termo in TERMOS_VALIDACAO_SEMANTICA)


# =================================================================
# I/O DO CACHE
# =================================================================

def carregar_cache() -> dict:
    """Lê o cache do disco. Retorna {} se não existir ou estiver corrompido."""
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        log.error(f"❌ Cache corrompido ({e}) — começando vazio")
        return {}
    except Exception as e:
        log.error(f"❌ Erro ao ler cache: {e}")
        return {}


def salvar_cache(cache: dict) -> bool:
    """Persiste o cache no disco. Retorna True se OK."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        log.error(f"❌ Erro ao salvar cache: {e}")
        return False


# =================================================================
# CONSULTA AO CACHE
# =================================================================

def _expirado(timestamp_str: str) -> bool:
    """Verifica se um timestamp 'YYYY-MM-DD HH:MM:SS' já passou do TTL."""
    if not timestamp_str:
        return True
    try:
        dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - dt) > timedelta(days=TTL_DIAS)
    except Exception:
        return True  # data inválida → considera expirado por segurança


def buscar_elemento_cache(
    alvo: str,
    contexto: str,
    guard_aprovado: bool = False,
) -> Optional[dict]:
    """
    Busca uma coordenada no cache.

    Args:
        alvo:           texto do elemento (ex: "Select file")
        contexto:       contexto da tela (ex: "pagina_upload_tiktok")
        guard_aprovado: True se o Publish Guard aprovou.
                        Obrigatório para entregar coordenadas de "Publicar".

    Returns:
        dict com {x, y, confianca, from_cache, sucessos, falhas, ...}
        ou None se não houver entrada confiável.
    """
    chave = gerar_chave_cache(alvo, contexto)
    cache = carregar_cache()
    entrada = cache.get(chave)

    if not entrada:
        log.info(f"  📭 Cache MISS: '{chave}'")
        return None

    # ── Defesa em profundidade: ações destrutivas exigem aprovação ──
    if _eh_acao_destrutiva(chave) and not guard_aprovado:
        log.warning(
            f"  🛡️ Cache contém '{chave}' (ação destrutiva), mas "
            f"guard_aprovado=False — recusando por segurança"
        )
        return None

    # ── Filtros de confiabilidade ───────────────────────────────────
    if entrada.get("desconfiavel"):
        log.info(f"  ⚠️ Cache HIT mas marcado como desconfiável: '{chave}'")
        return None

    confianca = entrada.get("confianca", "").lower()
    if confianca not in CONFIANCAS_ACEITAS:
        log.info(f"  ⚠️ Cache HIT mas confiança baixa ('{confianca}'): '{chave}'")
        return None

    sucessos = int(entrada.get("sucessos", 0))
    falhas   = int(entrada.get("falhas", 0))

    # Regra normal: precisa ter ao menos 1 sucesso de clique anterior.
    # EXCEÇÃO (cache cooperativo): se a entrada foi DOADA pelo
    # localizar_elemento_por_texto (via_localizar=True), o "sucesso"
    # da localização pelo Gemini já vale como evidência inicial.
    # Aceitamos entregar sem cliques anteriores, mas se já houver
    # falhas registradas, a regra de falhas (abaixo) ainda barra.
    veio_do_localizar = bool(entrada.get("via_localizar"))

    if sucessos < MIN_SUCESSOS_PARA_USO and not veio_do_localizar:
        log.info(f"  ⚠️ Cache HIT mas sucessos={sucessos} < {MIN_SUCESSOS_PARA_USO}: '{chave}'")
        return None

    if falhas > MAX_FALHAS_PERMITIDAS:
        log.info(f"  ⚠️ Cache HIT mas falhas={falhas} > {MAX_FALHAS_PERMITIDAS}: '{chave}'")
        return None

    # ── TTL ─────────────────────────────────────────────────────────
    ultima_val = entrada.get("ultima_validacao", "")
    if _expirado(ultima_val):
        log.info(f"  ⏰ Cache HIT mas expirado (>{TTL_DIAS} dias): '{chave}'")
        return None

    # ── Cache válido ────────────────────────────────────────────────
    x = int(entrada.get("x", 0))
    y = int(entrada.get("y", 0))
    log.info(
        f"  ⚡ Cache HIT: '{chave}' → ({x}, {y}) "
        f"[confiança={confianca} | sucessos={sucessos} | falhas={falhas}]"
    )

    return {
        "from_cache":       True,
        "chave":            chave,
        "x":                x,
        "y":                y,
        "confianca":        confianca,
        "sucessos":         sucessos,
        "falhas":           falhas,
        "ultima_validacao": ultima_val,
        "alvo":             entrada.get("alvo", alvo),
        "contexto":         entrada.get("contexto", contexto),
    }


# =================================================================
# REGISTRO DE SUCESSO / FALHA
# =================================================================

def registrar_sucesso(
    alvo: str,
    contexto: str,
    x: int,
    y: int,
    confianca: str = "alta",
) -> bool:
    """
    Registra sucesso de clique/localização. Cria ou atualiza entrada.

    Comportamento:
      - Se entrada nova: cria com sucessos=1, falhas=0
      - Se entrada existe: incrementa sucessos, reduz falhas (mínimo 0),
        atualiza coordenadas SE a confiança nova >= confiança salva
      - Remove flag desconfiavel se ela estiver presente
    """
    if not alvo or not contexto:
        log.warning("registrar_sucesso ignorado — alvo ou contexto vazio")
        return False

    chave = gerar_chave_cache(alvo, contexto)
    cache = carregar_cache()
    entrada = cache.get(chave, {})

    NIVEIS = {"baixa": 0, "media": 1, "média": 1, "alta": 2}

    # Atualiza coordenadas só se a nova confiança for >= salva
    # (evita "downgrade" da coordenada por um clique de menor qualidade)
    confianca_atual = entrada.get("confianca", "baixa")
    if NIVEIS.get(confianca, 0) >= NIVEIS.get(confianca_atual, 0):
        entrada["x"]         = int(x)
        entrada["y"]         = int(y)
        entrada["confianca"] = confianca

    entrada["alvo"]              = alvo
    entrada["contexto"]          = contexto
    entrada["sucessos"]          = int(entrada.get("sucessos", 0)) + 1
    entrada["falhas"]            = max(0, int(entrada.get("falhas", 0)) - 1)  # reduz erros
    entrada["ultima_validacao"]  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entrada.pop("desconfiavel", None)  # reabilita se estava desconfiável

    cache[chave] = entrada
    ok = salvar_cache(cache)
    if ok:
        log.info(
            f"  💾 Cache atualizado: '{chave}' "
            f"→ ({entrada['x']}, {entrada['y']}) "
            f"[sucessos={entrada['sucessos']} | falhas={entrada['falhas']}]"
        )
    return ok


def registrar_falha(alvo: str, contexto: str, motivo: str = "") -> bool:
    """
    Registra falha de clique/localização. Incrementa contador e marca
    como desconfiável se ultrapassar limite.
    """
    if not alvo or not contexto:
        return False

    chave = gerar_chave_cache(alvo, contexto)
    cache = carregar_cache()
    entrada = cache.get(chave)

    if not entrada:
        # Não existe ainda — não faz sentido marcar falha
        log.debug(f"registrar_falha: '{chave}' não está no cache, ignorado")
        return False

    entrada["falhas"]       = int(entrada.get("falhas", 0)) + 1
    entrada["ultima_falha"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if motivo:
        entrada["ultimo_motivo_falha"] = motivo[:200]

    if entrada["falhas"] >= MAX_FALHAS_DESCONFIAVEL:
        entrada["desconfiavel"] = True
        log.warning(
            f"  🚫 '{chave}' marcado como DESCONFIÁVEL "
            f"(falhas={entrada['falhas']} ≥ {MAX_FALHAS_DESCONFIAVEL})"
        )
    else:
        log.info(f"  ⚠️ Falha registrada em '{chave}' (falhas={entrada['falhas']})")

    cache[chave] = entrada
    return salvar_cache(cache)


# =================================================================
# CACHE COOPERATIVO (alimentado pelo localizar_elemento_por_texto)
# =================================================================
#
# Filosofia: o `localizar_elemento_por_texto` NUNCA pula Gemini —
# ele é usado em gates críticos onde falso positivo do cache pode
# fazer o orquestrador seguir um fluxo errado (ex.: achar que a tela
# de detalhes abriu quando ainda está na seleção).
#
# MAS: quando o localizar tem sucesso com confiança média/alta,
# vale a pena DOAR a coordenada pro cache, marcada como
# "via_localizar". Assim, um clique posterior no mesmo (alvo, contexto)
# pode usar essa coordenada sem chamar Gemini de novo.
#
# Diferenças pra registrar_sucesso clássico:
#   - Marca via_localizar=True, tipo_cache="cooperativo"
#   - Marca usado_para_resposta=False (só pra trace/debug)
#   - Não incrementa sucessos do clique (não houve clique)
#   - Coordenada vira "disponível pra cliques futuros"
#
# O buscar_elemento_cache() NÃO precisa mudar: ele encontra a entrada
# normalmente pela chave. A diferença é só de metadados.

def registrar_via_localizar(
    alvo: str,
    contexto: str,
    x: int,
    y: int,
    confianca: str,
) -> bool:
    """
    Doa uma coordenada encontrada pelo Gemini (via localizar_elemento_por_texto)
    para o cache cooperativo. Cliques futuros no mesmo alvo/contexto poderão
    usar essa coordenada sem chamar Gemini.

    Só aceita coordenadas com confiança "media"/"média"/"alta". Coordenadas
    de confiança baixa NÃO entram no cache (proteção contra alucinação leve).

    Comportamento:
      - Entrada NOVA: cria com sucessos=0, falhas=0, via_localizar=True
      - Entrada EXISTENTE: atualiza coordenada SE a confiança nova >= salva
        (mesma regra anti-downgrade do registrar_sucesso), e marca
        via_localizar=True nos metadados se ainda não estiver

    Args:
        alvo, contexto, x, y, confianca: dados retornados pelo Gemini Vision

    Returns:
        True se gravou no cache. False se rejeitado por confiança baixa
        ou erro de I/O.
    """
    if not alvo or not contexto:
        log.debug("registrar_via_localizar ignorado — alvo ou contexto vazio")
        return False

    confianca_lower = (confianca or "").lower()
    if confianca_lower not in CONFIANCAS_ACEITAS:
        log.debug(
            f"  ⏭️  Cache cooperativo: confiança '{confianca}' rejeitada "
            f"(precisa media/alta)"
        )
        return False

    chave = gerar_chave_cache(alvo, contexto)
    cache = carregar_cache()
    entrada = cache.get(chave, {})

    NIVEIS = {"baixa": 0, "media": 1, "média": 1, "alta": 2}

    # Atualiza coordenadas só se a nova confiança >= salva
    # (mesma regra do registrar_sucesso — evita downgrade)
    confianca_atual_salva = entrada.get("confianca", "baixa")
    if NIVEIS.get(confianca_lower, 0) >= NIVEIS.get(confianca_atual_salva, 0):
        entrada["x"]         = int(x)
        entrada["y"]         = int(y)
        entrada["confianca"] = confianca_lower

    # Metadados base (não mexe em sucessos/falhas — não houve clique aqui)
    entrada["alvo"]     = alvo
    entrada["contexto"] = contexto
    entrada.setdefault("sucessos", 0)
    entrada.setdefault("falhas",   0)

    # Metadados específicos do cache cooperativo
    entrada["via_localizar"]        = True
    entrada["tipo_cache"]           = "cooperativo"
    entrada["usado_para_resposta"]  = False  # pra trace — localizar nunca lê do cache
    entrada["ultima_doacao"]        = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Se nunca foi validada por clique, marca quando entrou pela primeira vez
    entrada.setdefault(
        "ultima_validacao",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    # Limpa flag desconfiavel se houver — Gemini achou de novo
    entrada.pop("desconfiavel", None)

    cache[chave] = entrada
    ok = salvar_cache(cache)
    if ok:
        log.info(
            f"  💾 Localizar salvou coordenada no cache cooperativo: "
            f"'{chave}' → ({entrada['x']}, {entrada['y']}) "
            f"[confiança={entrada['confianca']}]"
        )
    return ok



#
# Filosofia: o cache só "aprende" quando confirmar que o efeito real
# aconteceu. PyAutoGUI clicar não significa "acertou o elemento certo".
#
# Fluxo do caller:
#   1. clicar nas coordenadas do cache
#   2. registrar_sucesso_pendente() — não persiste ainda
#   3. fazer ação que valida o efeito (próximo passo, gate, observe)
#   4. SE efeito ok      → confirmar_clique_pendente()  (aí persiste sucesso)
#      SE efeito falhou  → descartar_clique_pendente() + registrar_falha()

# Buffer de sucessos pendentes em memória (não persiste em disco)
# Chave: chave_cache → dict com x, y, confianca, timestamp
# =================================================================
# SUCESSO PENDENTE (validação semântica)
# =================================================================
#
# Filosofia: o cache só "aprende" quando confirmar que o efeito real
# aconteceu. PyAutoGUI clicar não significa "acertou o elemento certo".
#
# Fluxo do caller:
#   1. clicar nas coordenadas do cache
#   2. registrar_sucesso_pendente() — não persiste ainda
#   3. fazer ação que valida o efeito (próximo passo, gate, observe)
#   4. SE efeito ok      → confirmar_clique_pendente()  (aí persiste sucesso)
#      SE efeito falhou  → descartar_clique_pendente() + registrar_falha()

# Buffer de sucessos pendentes em memória (não persiste em disco)
# Chave: chave_cache → dict com x, y, confianca, timestamp
_pendentes: dict = {}


def registrar_sucesso_pendente(
    alvo: str,
    contexto: str,
    x: int,
    y: int,
    confianca: str = "alta",
) -> bool:
    """
    Registra um clique como "potencialmente bem-sucedido" mas
    aguardando validação semântica.

    NÃO PERSISTE NO DISCO. Fica em buffer em memória até o caller
    chamar confirmar_clique_pendente() ou descartar_clique_pendente().

    Args:
        alvo, contexto, x, y, confianca: mesmos de registrar_sucesso

    Returns:
        True se registrou o pendente, False se faltou dado.
    """
    if not alvo or not contexto:
        return False

    chave = gerar_chave_cache(alvo, contexto)
    _pendentes[chave] = {
        "alvo":       alvo,
        "contexto":   contexto,
        "x":          int(x),
        "y":          int(y),
        "confianca":  confianca,
        "timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    log.info(f"  ⏸️ Sucesso PENDENTE de validação: '{chave}' → ({x}, {y})")
    return True


def confirmar_clique_pendente(alvo: str, contexto: str) -> bool:
    """
    Confirma que um clique pendente teve o efeito esperado.
    Move do buffer para o cache persistente via registrar_sucesso().

    Args:
        alvo, contexto: mesmos usados no registrar_sucesso_pendente

    Returns:
        True se havia pendente e foi confirmado. False se não havia.
    """
    chave = gerar_chave_cache(alvo, contexto)
    pendente = _pendentes.pop(chave, None)
    if not pendente:
        log.debug(f"confirmar_clique_pendente: nada pendente para '{chave}'")
        return False

    log.info(f"  ✅ Validação confirmada: '{chave}' — persistindo no cache")
    return registrar_sucesso(
        alvo=pendente["alvo"],
        contexto=pendente["contexto"],
        x=pendente["x"],
        y=pendente["y"],
        confianca=pendente["confianca"],
    )


def descartar_clique_pendente(alvo: str, contexto: str, motivo: str = "") -> bool:
    """
    Descarta um clique pendente — efeito esperado NÃO aconteceu.
    Remove do buffer SEM persistir no cache.

    Quem chamou também deve chamar registrar_falha() para penalizar
    a entrada caso ela já estivesse no cache (cache existia mas a
    coordenada estava errada).

    Args:
        alvo, contexto: mesmos usados no registrar_sucesso_pendente
        motivo:         opcional, só pra log

    Returns:
        True se descartou um pendente, False se nada estava pendente.
    """
    chave = gerar_chave_cache(alvo, contexto)
    pendente = _pendentes.pop(chave, None)
    if not pendente:
        return False

    log.warning(
        f"  ❌ Clique pendente DESCARTADO: '{chave}' "
        f"— efeito esperado não ocorreu"
        + (f" ({motivo})" if motivo else "")
    )
    return True


def listar_pendentes() -> list[dict]:
    """Útil pra debug — retorna os cliques aguardando validação."""
    return [
        {"chave": chave, **dados}
        for chave, dados in _pendentes.items()
    ]


def limpar_pendentes() -> int:
    """Limpa todos os pendentes (chamado entre workflows pra evitar leak)."""
    n = len(_pendentes)
    _pendentes.clear()
    return n


# =================================================================
# LIMPEZA / MANUTENÇÃO
# =================================================================

def limpar_cache_desconfiavel(remover: bool = False) -> dict:
    """
    Trata itens desconfiáveis.

    Args:
        remover: se True, deleta as entradas. Se False (padrão), só lista.

    Returns:
        {
            "desconfiaveis":   list  ← chaves identificadas
            "expiradas":       list  ← chaves cujo TTL passou
            "removidas":       int   ← total removido (0 se remover=False)
            "mantidas_total":  int
        }
    """
    cache = carregar_cache()
    desconfiaveis = []
    expiradas     = []

    for chave, entrada in list(cache.items()):
        if entrada.get("desconfiavel"):
            desconfiaveis.append(chave)
        if _expirado(entrada.get("ultima_validacao", "")):
            expiradas.append(chave)

    removidas = 0
    if remover:
        for chave in set(desconfiaveis):
            del cache[chave]
            removidas += 1
        salvar_cache(cache)
        log.info(f"🧹 {removidas} entrada(s) desconfiáveis removidas")
    else:
        log.info(
            f"🔎 Inspeção: {len(desconfiaveis)} desconfiáveis | "
            f"{len(expiradas)} expiradas | {len(cache)} no total"
        )

    return {
        "desconfiaveis":  desconfiaveis,
        "expiradas":      expiradas,
        "removidas":      removidas,
        "mantidas_total": len(cache),
    }


def estatisticas_cache() -> dict:
    """Retorna estatísticas do cache (útil pra debug e monitoramento)."""
    cache = carregar_cache()
    total      = len(cache)
    confiaveis = sum(1 for e in cache.values() if not e.get("desconfiavel"))
    sucessos   = sum(int(e.get("sucessos", 0)) for e in cache.values())
    falhas     = sum(int(e.get("falhas", 0))   for e in cache.values())

    return {
        "total_entradas":     total,
        "entradas_confiaveis": confiaveis,
        "entradas_desconfiaveis": total - confiaveis,
        "sucessos_acumulados": sucessos,
        "falhas_acumuladas":   falhas,
        "arquivo":             str(CACHE_FILE),
    }


# =================================================================
# TESTE VIA TERMINAL
# =================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  🧠 Interface Cache — Teste")
    print("=" * 60)

    # ── Teste 1: gerar chaves ─────────────────────────────────────
    print("\n📝 Teste 1: gerar chaves")
    casos = [
        ("Select file", "pagina_upload_tiktok"),
        ("campo de descrição do vídeo onde aparecem legenda e hashtags",
         "tela_detalhes_tiktok_apos_upload"),
        ("Publicar", "tela_publicacao_tiktok"),
        ("Botão 🔥 Postar", "tela_final"),
    ]
    for alvo, ctx in casos:
        chave = gerar_chave_cache(alvo, ctx)
        print(f"  ({alvo[:30]!r:<32}, {ctx!r:<35}) → {chave}")

    # ── Teste 2: registrar Select file fake ───────────────────────
    print("\n💾 Teste 2: registrar 'Select file' em (960, 430)")
    ok = registrar_sucesso(
        alvo="Select file",
        contexto="pagina_upload_tiktok",
        x=960, y=430,
        confianca="alta",
    )
    print(f"  Salvou: {ok}")

    # ── Teste 3: buscar Select file ────────────────────────────────
    print("\n🔍 Teste 3: buscar 'Select file'")
    encontrado = buscar_elemento_cache(
        alvo="Select file",
        contexto="pagina_upload_tiktok",
    )
    if encontrado:
        print(f"  ✅ HIT: x={encontrado['x']}, y={encontrado['y']}, conf={encontrado['confianca']}")
    else:
        print(f"  ❌ MISS")

    # ── Teste 4: tentar pegar Publicar SEM aprovação ──────────────
    print("\n🛡️ Teste 4: buscar 'Publicar' SEM guard_aprovado (deve recusar)")
    # Primeiro registra um Publicar fake
    registrar_sucesso("Publicar", "tela_publicacao_tiktok", x=500, y=600, confianca="alta")

    pub = buscar_elemento_cache(
        alvo="Publicar",
        contexto="tela_publicacao_tiktok",
        guard_aprovado=False,
    )
    print(f"  Resultado: {'❌ ENTREGOU (BUG!)' if pub else '✅ RECUSOU (correto)'}")

    print("\n🛡️ Teste 4b: buscar 'Publicar' COM guard_aprovado=True")
    pub2 = buscar_elemento_cache(
        alvo="Publicar",
        contexto="tela_publicacao_tiktok",
        guard_aprovado=True,
    )
    print(f"  Resultado: {'✅ ENTREGOU (correto)' if pub2 else '❌ RECUSOU'}")

    # ── Teste 5: registrar falha ──────────────────────────────────
    print("\n⚠️ Teste 5: registrar 3 falhas em 'Select file' (deve marcar desconfiável)")
    for i in range(3):
        registrar_falha("Select file", "pagina_upload_tiktok", motivo=f"teste {i+1}")

    print("\n🔍 Teste 5b: buscar 'Select file' após 3 falhas (deve ser MISS por desconfiável)")
    encontrado2 = buscar_elemento_cache(
        alvo="Select file",
        contexto="pagina_upload_tiktok",
    )
    print(f"  Resultado: {'❌ ENTREGOU (BUG!)' if encontrado2 else '✅ MISS por desconfiável (correto)'}")

    # ── Teste 6: estatísticas ──────────────────────────────────────
    print("\n📊 Teste 6: estatísticas")
    stats = estatisticas_cache()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # ── Teste 7: inspeção de desconfiáveis ────────────────────────
    print("\n🧹 Teste 7: inspeção de desconfiáveis")
    inspecao = limpar_cache_desconfiavel(remover=False)
    print(f"  Desconfiáveis: {inspecao['desconfiaveis']}")
    print(f"  Expiradas:     {inspecao['expiradas']}")
    print(f"  Total mantido: {inspecao['mantidas_total']}")

    print(f"\n💾 Arquivo: {CACHE_FILE}")
    print("=" * 60)