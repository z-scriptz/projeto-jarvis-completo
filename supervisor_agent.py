# agents/supervisor_agent.py
# Supervisor Agent v1 do AgenteIA (Jarvis).
#
# A camada que transforma "vários agentes funcionando" em
# "sistema rodando sozinho". State machine + daemon loop + safe stop.
#
# Filosofia:
#   - Daemon 24h com sleep configurável (não 100% CPU)
#   - Decide UMA etapa por iteração baseado em estado de cada produto
#   - Para tudo e espera você em caso de erro (modo seguro)
#   - Lock file pra evitar 2 supervisores rodando ao mesmo tempo
#   - Heartbeat em arquivo pra você monitorar de outro terminal
#   - Memory é CONTEXTUAL (passa pra agentes), não decide a estratégia
#   - Dry-run final no TikTok (edita + preenche detalhes, NÃO posta)
#
# Estados de produto (state.json):
#   novo                  → ainda não foi planejado
#   plano_pronto          → planejamento OK (do pipeline_planejar)
#   sem_assets            → plano OK mas faltam clipes
#   pronto_pra_editar     → assets OK, pode editar
#   editado               → vídeo gerado, falta upload+detalhes
#   detalhes_preenchidos  → upload+detalhes OK, aguardando você revisar/postar
#   postado               → publicado (estado terminal)
#   ERRO_PAUSA            → falha registrada, supervisor pausou
#
# Uso:
#   python -m agents.supervisor_agent --status         (dashboard, não roda nada)
#   python -m agents.supervisor_agent --dry-run        (mostra o que faria)
#   python -m agents.supervisor_agent --single         (1 iteração e sai)
#   python -m agents.supervisor_agent --daemon         (loop 24h)
#   python -m agents.supervisor_agent --reset-pause    (limpa pause anterior)
#
# Filosofia de erros:
#   - Erro em UM produto → PAUSA TUDO, registra no state.json, sai
#   - Você lê o erro, conserta, roda --reset-pause, --daemon de novo
#   - Estado é persistente: continua do ponto onde parou

import argparse
import json
import os
import re
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable

from shared.logger import get_logger

# Asset Agent — verificar prontidão de assets
from agents.asset_agent import (
    slugificar_produto,
    verificar_assets_produto,
)

# Memory Agent — contextual (best-effort, não bloqueia)
try:
    from agents.memory_agent import (
        registrar_memoria,
        registrar_aprendizado_execucao,
        buscar_contexto_para_tarefa,
        gerar_recomendacoes_edicao,
    )
    _MEMORY_DISPONIVEL = True
except Exception as _e_mem:
    _MEMORY_DISPONIVEL = False
    _MOTIVO_MEMORIA = str(_e_mem)

# Editor — ação principal de criar vídeo
try:
    from creative_engine.product_video_editor import (
        editar_video_produto_capcut_style,
    )
    _EDITOR_DISPONIVEL = True
except Exception:
    _EDITOR_DISPONIVEL = False

log = get_logger(__name__)

# =================================================================
# CONFIGURAÇÃO
# =================================================================

PROJETO_ROOT   = Path(__file__).parent.parent
MEMORY_DIR     = PROJETO_ROOT / "memory"
# State PRÓPRIO do Supervisor (evita conflito com outros agentes que escrevem em state.json)
STATE_PATH     = MEMORY_DIR / "supervisor_state.json"
# Legado: state.json compartilhado — migramos só os produtos rastreados pelo Supervisor antes
STATE_PATH_LEGADO = MEMORY_DIR / "state.json"
LOCK_PATH      = MEMORY_DIR / ".supervisor.lock"
HEARTBEAT_PATH = MEMORY_DIR / ".supervisor.heartbeat"
PLANS_DIR     = PROJETO_ROOT / "shared" / "content_plans"
VIDEOS_DIR    = PROJETO_ROOT / "videos"

# Estados possíveis (não estamos usando IntEnum pra ficar legível no JSON)
ESTADO_NOVO                 = "novo"
ESTADO_PLANO_PRONTO         = "plano_pronto"
ESTADO_SEM_ASSETS           = "sem_assets"
ESTADO_PRONTO_PRA_EDITAR    = "pronto_pra_editar"
ESTADO_EDITADO              = "editado"
ESTADO_DETALHES_PREENCHIDOS = "detalhes_preenchidos"
ESTADO_POSTADO              = "postado"            # terminal (sucesso)
ESTADO_ERRO_PAUSA           = "ERRO_PAUSA"         # terminal (precisa de você)

ESTADOS_TERMINAIS = {ESTADO_POSTADO, ESTADO_ERRO_PAUSA}

# Ordem de progressão (não-pause). Útil pra mostrar % de progresso.
PROGRESSO_ESTADOS = [
    ESTADO_NOVO,
    ESTADO_PLANO_PRONTO,
    ESTADO_SEM_ASSETS,
    ESTADO_PRONTO_PRA_EDITAR,
    ESTADO_EDITADO,
    ESTADO_DETALHES_PREENCHIDOS,
    ESTADO_POSTADO,
]

# Limites de segurança
SLEEP_DEFAULT_SEG          = 30      # entre iterações do daemon
MAX_ITERS_POR_PRODUTO      = 5       # se um produto fica em loop, abandona
MAX_PRODUTOS_POR_CICLO     = 10      # quantos produtos visitar antes de dormir
SLEEP_QUANDO_NADA_FAZER    = 60      # se nada a fazer, dorme mais
HEARTBEAT_INTERVALO_SEG    = 10      # atualiza heartbeat a cada N segs


# =================================================================
# STATE: leitura/escrita atômica
# =================================================================

def _garantir_dirs():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)


def _ler_state() -> dict:
    """
    Lê supervisor_state.json. Migra do state.json antigo na primeira execução
    (se existe e tem campos do supervisor). Retorna dict vazio se nada existe.
    """
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"supervisor_state.json corrompido ({e}) — usando estado vazio")
            return {"produtos": {}, "iteracao": 0, "ultima_acao": None, "pause": None}

    # Migração automática: state.json compartilhado pode ter dados do supervisor
    if STATE_PATH_LEGADO.exists():
        try:
            antigo = json.loads(STATE_PATH_LEGADO.read_text(encoding="utf-8"))
            # Só migra se tem chaves do supervisor (evita herdar lixo de outros agentes)
            tem_chaves_supervisor = (
                isinstance(antigo, dict)
                and "produtos" in antigo
                and "iteracao" in antigo
            )
            if tem_chaves_supervisor:
                log.info(f"📦 Migrando state.json → supervisor_state.json "
                         f"({len(antigo.get('produtos', {}))} produto(s) preservados)")
                # Copia só campos relevantes (não polui)
                migrado = {
                    "produtos":    antigo.get("produtos", {}),
                    "iteracao":    antigo.get("iteracao", 0),
                    "ultima_acao": antigo.get("ultima_acao"),
                    "pause":       antigo.get("pause"),
                    "_migrado_de": str(STATE_PATH_LEGADO),
                    "_migrado_em": datetime.now().isoformat(timespec="seconds"),
                }
                # Salva o migrado imediatamente (consolidação)
                # Exceção à regra "_ler_state não escreve" — migração é one-shot
                try:
                    _salvar_state(migrado)
                    log.info(f"   ✅ Migração consolidada em {STATE_PATH.name}")
                except Exception as e:
                    log.warning(f"   ⚠️  Migração não consolidada (falha ao salvar): {e}")
                # Não apaga state.json — outros agentes podem usar
                return migrado
        except Exception as e:
            log.warning(f"Falha ao migrar state.json antigo: {e}")

    return {
        "produtos":     {},
        "iteracao":     0,
        "ultima_acao":  None,
        "pause":        None,
    }


def _salvar_state(state: dict):
    """Escrita atômica via arquivo temporário + rename."""
    _garantir_dirs()
    tmp = STATE_PATH.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        tmp.replace(STATE_PATH)
    except Exception as e:
        log.error(f"Falha ao salvar state.json: {e}")
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def _atualizar_produto_no_state(state: dict, slug: str, **kwargs):
    """Atualiza/cria entrada do produto preservando contadores."""
    if "produtos" not in state:
        state["produtos"] = {}
    entrada = state["produtos"].get(slug, {
        "slug":            slug,
        "estado":          ESTADO_NOVO,
        "iteracoes":       0,
        "ultima_atualizacao": None,
        "historico":       [],
    })
    estado_antigo = entrada.get("estado")
    entrada.update(kwargs)
    entrada["ultima_atualizacao"] = datetime.now().isoformat(timespec="seconds")

    # Se o estado mudou, registra no histórico (limitado a 20)
    estado_novo = entrada.get("estado")
    if estado_novo != estado_antigo:
        hist = entrada.get("historico", [])
        hist.append({
            "ts":           entrada["ultima_atualizacao"],
            "de":           estado_antigo,
            "para":         estado_novo,
        })
        entrada["historico"] = hist[-20:]

    state["produtos"][slug] = entrada


# =================================================================
# LOCK & HEARTBEAT (concorrência)
# =================================================================

def _checar_e_criar_lock() -> tuple[bool, str]:
    """
    Cria PID file. Retorna (True, "criado") se OK.
    Se já existe e processo vivo: (False, "outro supervisor PID X").
    Se já existe mas processo morto: limpa e cria novo.
    """
    _garantir_dirs()
    if LOCK_PATH.exists():
        try:
            pid_antigo = int(LOCK_PATH.read_text().strip())
            # Tenta sinalizar com 0 (não mata, só checa se existe)
            try:
                os.kill(pid_antigo, 0)
                # Processo ainda vivo
                return False, f"outro supervisor já rodando (PID {pid_antigo})"
            except (ProcessLookupError, PermissionError):
                # Processo morreu, lock fantasma — limpa
                log.warning(f"Lock fantasma (PID {pid_antigo} não existe) — limpando")
                LOCK_PATH.unlink(missing_ok=True)
            except OSError:
                # No Windows os.kill(pid, 0) pode dar OSError pra processo morto
                LOCK_PATH.unlink(missing_ok=True)
        except (ValueError, OSError):
            # Lock corrompido — limpa
            LOCK_PATH.unlink(missing_ok=True)

    try:
        LOCK_PATH.write_text(str(os.getpid()))
        return True, "lock criado"
    except Exception as e:
        return False, f"falha ao criar lock: {e}"


def _liberar_lock():
    """Remove PID file. Sempre tenta, ignora erros."""
    try:
        if LOCK_PATH.exists():
            # Só remove se o PID for nosso (evita remover lock alheio)
            try:
                pid_lock = int(LOCK_PATH.read_text().strip())
                if pid_lock == os.getpid():
                    LOCK_PATH.unlink()
            except Exception:
                LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _atualizar_heartbeat(estado_atual: str = ""):
    """Escreve heartbeat com timestamp atual + estado."""
    try:
        hb = {
            "pid":       os.getpid(),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "estado":    estado_atual,
        }
        HEARTBEAT_PATH.write_text(json.dumps(hb, ensure_ascii=False))
    except Exception:
        pass


def _heartbeat_recente() -> tuple[Optional[datetime], Optional[dict]]:
    """Lê heartbeat. Retorna (datetime, dict) ou (None, None)."""
    if not HEARTBEAT_PATH.exists():
        return None, None
    try:
        data = json.loads(HEARTBEAT_PATH.read_text(encoding="utf-8"))
        return datetime.fromisoformat(data["timestamp"]), data
    except Exception:
        return None, None


def _resolver_produto_por_nome_ou_slug(nome_ou_slug: str) -> tuple[str, str]:
    """
    Aceita nome completo OU slug e devolve (produto_nome_canonico, slug).
    Estratégia:
      1. Tenta achar no listing de planos (compara case-insensitive em ambos)
      2. Se não achar, usa o input como nome e gera slug
    """
    if not nome_ou_slug:
        return "", ""
    alvo_lower = nome_ou_slug.strip().lower()
    alvo_slug = slugificar_produto(nome_ou_slug)

    # Busca em planos existentes (fonte de verdade pros nomes)
    try:
        for info in _listar_planos_produtos():
            if (info["produto"].lower() == alvo_lower
                or info["slug"] == alvo_slug):
                return info["produto"], info["slug"]
    except Exception:
        pass

    # Fallback: usa o input direto
    return nome_ou_slug.strip(), alvo_slug


def marcar_produto_postado(nome_ou_slug: str,
                             nota_humana: str = "") -> dict:
    """
    Marca um produto como POSTADO (terminal):
      1. Cria flag videos/<slug>.postado.flag
      2. Atualiza state.produtos[slug].estado = ESTADO_POSTADO
      3. Limpa pause se esse produto era o culpado
      4. Registra memória de aprendizado com lead time
    """
    _garantir_dirs()
    produto, slug = _resolver_produto_por_nome_ou_slug(nome_ou_slug)
    if not slug:
        return {"sucesso": False, "mensagem": "produto inválido"}

    state = _ler_state()
    entrada = state.get("produtos", {}).get(slug, {})
    estado_antes = entrada.get("estado", "desconhecido")

    if estado_antes == ESTADO_POSTADO:
        return {
            "sucesso":  True,
            "produto":  produto,
            "slug":     slug,
            "mensagem": f"'{produto}' já estava como POSTADO — nada a fazer",
            "no_op":    True,
        }

    # 1. Cria a flag no filesystem (fonte de verdade)
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    flag_postado   = VIDEOS_DIR / f"{slug}.postado.flag"
    flag_preparado = VIDEOS_DIR / f"{slug}.preparado.flag"
    try:
        info_flag = {
            "produto":      produto,
            "slug":         slug,
            "marcado_em":   datetime.now().isoformat(timespec="seconds"),
            "nota_humana":  nota_humana or "",
            "estado_antes": estado_antes,
        }
        flag_postado.write_text(json.dumps(info_flag, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        # Postado implica preparado também — cria se não existir (consistência)
        if not flag_preparado.exists():
            flag_preparado.write_text(json.dumps(info_flag, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    except Exception as e:
        return {"sucesso": False, "mensagem": f"Falha ao criar flag: {e}"}

    # 2. Verifica vídeo (warning não-bloqueante)
    video_path = VIDEOS_DIR / f"{slug}_edited.mp4"
    sem_video = not video_path.exists()
    if sem_video:
        log.warning(f"⚠️  Vídeo {video_path.name} não encontrado — marcando assim mesmo")

    # 3. Atualiza state
    _atualizar_produto_no_state(state, slug,
                                  estado=ESTADO_POSTADO,
                                  produto_nome=produto,
                                  ultimo_resultado={
                                      "sucesso":    True,
                                      "mensagem":   "Marcado como postado manualmente",
                                      "nota_humana": nota_humana,
                                      "marcado_em": datetime.now().isoformat(timespec="seconds"),
                                  })

    # 4. Se esse produto era o pause, libera
    pause = state.get("pause")
    if pause and isinstance(pause, dict) and pause.get("produto") == produto:
        log.info(f"🧹 Limpando pause anterior (era desse produto)")
        state["pause"] = None

    _salvar_state(state)

    # 5. Memória contextual (best-effort)
    lead_time_dias = None
    if _MEMORY_DISPONIVEL:
        try:
            # Calcula lead time se tiver plano
            from pathlib import Path as _P
            planos = _listar_planos_produtos()
            info_plano = next((p for p in planos if p["slug"] == slug), None)
            if info_plano:
                lead_time_dias = (datetime.now() - info_plano["modified_at"]).days

            resumo = (
                f"Produto '{produto}' marcado como POSTADO manualmente. "
                f"Estado anterior: {estado_antes}. "
                f"Iterações no Supervisor: {entrada.get('iteracoes', 0)}. "
            )
            if lead_time_dias is not None:
                resumo += f"Lead time desde o plano: {lead_time_dias} dia(s). "
            if nota_humana:
                resumo += f"Nota do usuário: {nota_humana}"

            tags = ["supervisor", "postado", slug, "milestone"]
            if sem_video:
                tags.append("sem_video_no_disco")
            registrar_aprendizado_execucao(
                etapa="supervisor.marcar_postado",
                resultado={"sucesso": True, "slug": slug,
                           "lead_time_dias": lead_time_dias},
                resumo=resumo,
                tags=tags,
            )
        except Exception as e:
            log.warning(f"Memória falhou ao registrar (best-effort): {e}")

    return {
        "sucesso":         True,
        "produto":         produto,
        "slug":            slug,
        "estado_antes":    estado_antes,
        "estado_novo":     ESTADO_POSTADO,
        "flag_postado":    str(flag_postado),
        "lead_time_dias":  lead_time_dias,
        "sem_video":       sem_video,
        "mensagem":        f"'{produto}' marcado como POSTADO",
    }


def marcar_produto_preparado(nome_ou_slug: str,
                               nota_humana: str = "") -> dict:
    """
    Marca um produto com DETALHES_PREENCHIDOS (pré-postagem):
      1. Cria flag videos/<slug>.preparado.flag
      2. Atualiza state.produtos[slug].estado = ESTADO_DETALHES_PREENCHIDOS

    Diferente de marcar_postado: indica "detalhes prontos no TikTok mas
    ainda não publiquei" — útil pra você poder dormir e publicar amanhã.
    """
    _garantir_dirs()
    produto, slug = _resolver_produto_por_nome_ou_slug(nome_ou_slug)
    if not slug:
        return {"sucesso": False, "mensagem": "produto inválido"}

    state = _ler_state()
    entrada = state.get("produtos", {}).get(slug, {})
    estado_antes = entrada.get("estado", "desconhecido")

    if estado_antes == ESTADO_POSTADO:
        return {
            "sucesso":  False,
            "mensagem": f"'{produto}' já está POSTADO — não pode voltar pra preparado",
        }

    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    flag = VIDEOS_DIR / f"{slug}.preparado.flag"
    try:
        flag.write_text(json.dumps({
            "produto":     produto,
            "slug":        slug,
            "marcado_em":  datetime.now().isoformat(timespec="seconds"),
            "nota_humana": nota_humana,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return {"sucesso": False, "mensagem": f"Falha ao criar flag: {e}"}

    _atualizar_produto_no_state(state, slug,
                                  estado=ESTADO_DETALHES_PREENCHIDOS,
                                  produto_nome=produto)
    _salvar_state(state)

    return {
        "sucesso":      True,
        "produto":      produto,
        "slug":         slug,
        "estado_antes": estado_antes,
        "estado_novo":  ESTADO_DETALHES_PREENCHIDOS,
        "flag":         str(flag),
        "mensagem":     f"'{produto}' marcado como DETALHES_PREENCHIDOS",
    }


def desmarcar_produto_postado(nome_ou_slug: str) -> dict:
    """
    Rollback: remove flag .postado.flag e volta produto pra DETALHES_PREENCHIDOS.
    Segurança contra erro humano (você marcou o produto errado).
    """
    produto, slug = _resolver_produto_por_nome_ou_slug(nome_ou_slug)
    if not slug:
        return {"sucesso": False, "mensagem": "produto inválido"}

    flag_postado = VIDEOS_DIR / f"{slug}.postado.flag"
    if not flag_postado.exists():
        return {"sucesso": True, "no_op": True,
                "mensagem": f"'{produto}' não estava postado — nada a fazer"}

    # Remove flag
    try:
        flag_postado.unlink()
    except Exception as e:
        return {"sucesso": False, "mensagem": f"Falha ao remover flag: {e}"}

    # Volta state pra DETALHES_PREENCHIDOS (flag.preparado.flag ainda existe)
    state = _ler_state()
    flag_preparado = VIDEOS_DIR / f"{slug}.preparado.flag"
    novo_estado = ESTADO_DETALHES_PREENCHIDOS if flag_preparado.exists() else ESTADO_EDITADO
    _atualizar_produto_no_state(state, slug, estado=novo_estado)
    _salvar_state(state)

    return {
        "sucesso":     True,
        "produto":     produto,
        "slug":        slug,
        "estado_novo": novo_estado,
        "mensagem":    f"'{produto}' desmarcado — voltou pra {novo_estado}",
    }



def _listar_planos_produtos() -> list[dict]:
    """
    Lê shared/content_plans/ procurando arquivos `plano_*.json`.
    Se houver MÚLTIPLOS planos pro mesmo produto (histórico), escolhe o
    MAIS RECENTE (timestamp no nome > mtime do arquivo).

    Padrão dos nomes:
      plano_<slug>_<YYYYMMDD>_<HHMMSS>.json    (formato histórico)
      plano_<slug>.json                          (formato simples)
      <slug>.json                                (legado, compatibilidade)

    Returns:
        Lista de dicts ordenada por modified_at desc:
        [
            {
                "produto":     "Mini Aspirador de Teclado",
                "slug":        "mini_aspirador_de_teclado",
                "plano_path":  Path("..."),
                "modified_at": datetime,
                "total_planos": 7,  # quantos planos esse produto tem
            },
            ...
        ]
    """
    if not PLANS_DIR.exists():
        return []

    # Regex pra parsear timestamp no nome: _YYYYMMDD_HHMMSS no fim
    re_ts = re.compile(r"_(\d{8})_(\d{6})$")

    # Agrupa todos os planos por slug
    planos_por_slug: dict[str, list[dict]] = {}

    for f in PLANS_DIR.glob("plano_*.json"):
        # Pula arquivos que não são planos canônicos
        if "_resultado" in f.stem or f.name in ("ultimo_plano.json",):
            continue

        # Tenta ler o JSON pra extrair "produto"
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue

        produto = data.get("produto") or data.get("nome") or data.get("product_name")
        if not isinstance(produto, str) or not produto.strip():
            continue
        produto = produto.strip()

        slug = slugificar_produto(produto)

        # Timestamp: tenta extrair do nome, senão usa mtime
        timestamp_from_name = None
        # Tira "plano_" do prefixo
        stem = f.stem
        if stem.startswith("plano_"):
            stem = stem[len("plano_"):]
        m = re_ts.search(stem)
        if m:
            try:
                ts_str = m.group(1) + m.group(2)  # YYYYMMDDHHMMSS
                timestamp_from_name = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
            except ValueError:
                pass

        if timestamp_from_name is None:
            try:
                timestamp_from_name = datetime.fromtimestamp(f.stat().st_mtime)
            except Exception:
                timestamp_from_name = datetime.now()

        planos_por_slug.setdefault(slug, []).append({
            "produto":     produto,
            "slug":        slug,
            "plano_path":  f,
            "modified_at": timestamp_from_name,
        })

    # Pra cada slug, pega o mais recente
    saida = []
    for slug, lista in planos_por_slug.items():
        lista.sort(key=lambda x: x["modified_at"], reverse=True)
        escolhido = dict(lista[0])
        escolhido["total_planos"] = len(lista)
        saida.append(escolhido)

    # Ordena lista final por mais recente primeiro
    saida.sort(key=lambda x: x["modified_at"], reverse=True)
    return saida


# =================================================================
# DETERMINAÇÃO DE ESTADO ATUAL DE UM PRODUTO
# =================================================================

def _detectar_estado_real(produto: str,
                            plano_path: Optional[Path] = None) -> tuple[str, dict]:
    """
    Inspeciona o sistema de arquivos pra determinar em que ESTADO real
    o produto está. Função pura: não modifica nada.

    Args:
        produto:     nome do produto
        plano_path:  caminho do plano encontrado (do _listar_planos_produtos).
                     Se None, tenta caminhos legados <slug>.json e plano_<slug>.json
                     pra retrocompat.

    Returns: (estado, contexto_dict)
    """
    contexto = {"produto": produto}
    slug = slugificar_produto(produto)
    contexto["slug"] = slug

    # 1. Plano: se já veio resolvido, usa direto. Senão tenta fallbacks.
    if plano_path is not None and plano_path.exists():
        contexto["plano_path"] = str(plano_path)
    else:
        # Fallback pra estruturas legadas (compat com supervisor v0)
        candidatos_legado = [
            PLANS_DIR / f"plano_{slug}.json",
            PLANS_DIR / f"{slug}.json",
        ]
        encontrado = next((p for p in candidatos_legado if p.exists()), None)
        if encontrado is not None:
            contexto["plano_path"] = str(encontrado)
        else:
            return ESTADO_NOVO, contexto

    # 2. Assets prontos?
    try:
        status = verificar_assets_produto(produto)
        contexto["status_assets"] = status["status"]
        contexto["score_assets"]  = status.get("score_prontidao", 0)
        if status.get("deve_aguardar"):
            return ESTADO_SEM_ASSETS, contexto
    except Exception as e:
        contexto["erro_assets"] = str(e)[:140]
        return ESTADO_SEM_ASSETS, contexto

    # 3. Vídeo editado existe?
    video_editado = VIDEOS_DIR / f"{slug}_edited.mp4"
    if not video_editado.exists():
        return ESTADO_PRONTO_PRA_EDITAR, contexto
    contexto["video_path"] = str(video_editado)
    contexto["video_size_mb"] = round(video_editado.stat().st_size / 1024 / 1024, 2)

    # 4. Detalhes preenchidos? (heurística: arquivo .preparado.flag)
    flag_preparado = VIDEOS_DIR / f"{slug}.preparado.flag"
    if flag_preparado.exists():
        return ESTADO_DETALHES_PREENCHIDOS, contexto

    return ESTADO_EDITADO, contexto


# =================================================================
# AÇÕES POR ESTADO (cada uma roda 1 etapa)
# =================================================================

def _garantir_audio_antes_de_editar(produto: str) -> dict:
    """
    Se o produto não tem áudio, dispara o Audio Autopilot pra coletar.
    Best-effort: nunca trava o pipeline. Se falhar, edita sem áudio.

    Returns: dict com resumo do que rolou (vai pro relatório):
        {tentou, tinha_audio_antes, audio_apos, audio_escolhido, audio_status, erro}
    """
    info = {
        "tentou":            False,
        "tinha_audio_antes": None,
        "audio_apos":        None,
        "audio_escolhido":   None,
        "audio_status":      "desconhecido",
        "erro":              None,
    }
    try:
        from agents.audio_autopilot_agent import (
            autopilot_audio,
            verificar_audio_produto,
        )
    except Exception as e:
        info["erro"] = f"Audio Autopilot indisponível: {str(e)[:100]}"
        log.warning(f"   ⚠️  {info['erro']} — editando sem buscar áudio")
        return info

    try:
        status_audio = verificar_audio_produto(produto)
        info["tinha_audio_antes"] = status_audio.get("total", 0)

        if status_audio.get("tem_audio"):
            log.info(f"   🎵 Produto já tem {status_audio['total']} áudio(s) — não precisa coletar")
            info["audio_apos"] = status_audio["total"]
            info["audio_status"] = "ja_tinha"
            return info

        # Sem áudio: dispara Autopilot
        log.info(f"   🎵 Produto SEM áudio — disparando Audio Autopilot...")
        info["tentou"] = True
        r = autopilot_audio(produto, max_downloads=10)
        info["audio_apos"]      = r.get("audio_final", 0)
        info["audio_escolhido"] = r.get("audio_escolhido")
        info["audio_status"]    = r.get("audio_status", "desconhecido")

        if r.get("audio_escolhido"):
            log.info(f"   ✅ Áudio coletado: {r['audio_escolhido']} "
                     f"(score {r.get('audio_score', 0)}, status {r['audio_status']})")
        else:
            log.warning(f"   ⚠️  Autopilot não encontrou áudio — editor vai render SEM áudio")
    except Exception as e:
        info["erro"] = f"{type(e).__name__}: {str(e)[:120]}"
        log.warning(f"   ⚠️  Audio Autopilot falhou ({info['erro']}) — editando sem áudio")

    return info


def _acao_editar_video(produto: str, contexto: dict) -> dict:
    """
    Executa o Product Video Editor. Memory contextual.
    Returns: {sucesso, novo_estado, mensagem, detalhes}
    """
    if not _EDITOR_DISPONIVEL:
        return {
            "sucesso":      False,
            "novo_estado":  ESTADO_ERRO_PAUSA,
            "mensagem":     "Editor de vídeo não disponível (import falhou)",
        }

    # Memory contextual: lê recomendações mas NÃO decide (opção 2 do usuário)
    contexto_memoria = {}
    if _MEMORY_DISPONIVEL:
        try:
            ctx = gerar_recomendacoes_edicao(produto=produto, nicho="")
            contexto_memoria = {
                "recomendacoes": ctx.get("recomendacoes", []),
                "preset_sugerido": ctx.get("preset_sugerido"),
            }
        except Exception:
            pass

    plano_dict = {}
    # Lê plano se existir
    plano_path = Path(contexto.get("plano_path", ""))
    if plano_path.exists():
        try:
            plano_dict = json.loads(plano_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # ── Garante áudio ANTES de editar (Audio Autopilot, best-effort) ──
    # Se produto não tem áudio, tenta coletar. Se falhar, edita sem áudio.
    audio_autopilot_info = _garantir_audio_antes_de_editar(produto)

    try:
        resultado = editar_video_produto_capcut_style(
            produto=produto,
            plano=plano_dict or None,
        )
    except Exception as e:
        return {
            "sucesso":      False,
            "novo_estado":  ESTADO_ERRO_PAUSA,
            "mensagem":     f"Editor crashou: {type(e).__name__}: {str(e)[:140]}",
        }

    if resultado.get("status") == "Video_Editado":
        return {
            "sucesso":     True,
            "novo_estado": ESTADO_EDITADO,
            "mensagem":    resultado.get("mensagem", "Vídeo editado"),
            "detalhes":    {
                "video_path":     resultado.get("video_path"),
                "score":          resultado.get("score_edicao"),
                "duracao":        resultado.get("duracao"),
                "audio_autopilot": audio_autopilot_info,
            },
        }
    elif resultado.get("status") == "Aguardando_Assets":
        # Não é erro fatal — só falta asset, dispara o estado correspondente
        return {
            "sucesso":     False,
            "novo_estado": ESTADO_SEM_ASSETS,
            "mensagem":    resultado.get("mensagem", "Assets insuficientes"),
        }
    else:
        return {
            "sucesso":     False,
            "novo_estado": ESTADO_ERRO_PAUSA,
            "mensagem":    f"Editor retornou status inesperado: {resultado.get('status')}",
            "detalhes":    {"resultado_editor": resultado},
        }


def _acao_preencher_detalhes_tiktok(produto: str, contexto: dict) -> dict:
    """
    Placeholder pra etapa de preencher detalhes do TikTok.
    Sua escolha: edita + preenche detalhes mas NÃO posta.

    Esta v1 marca como "detalhes preenchidos" assumindo que existe um workflow
    `preparar_post_tiktok_completo` (referenciado no autonomous_orchestrator.py).

    NÃO chamamos esse workflow aqui na v1 — supervisor v1 só vai até EDITADO
    pra ser conservador. Quando você quiser ativar o passo de upload+detalhes
    do TikTok, descomenta o bloco abaixo.
    """
    # ── BLOQUEADO POR DESIGN (v1): supervisor não toca em TikTok ──
    # Sua escolha foi "editar + preencher detalhes mas NÃO postar".
    # Como o preenchimento de detalhes envolve abrir o TikTok (PyAutoGUI),
    # e supervisor v1 não tem maturidade pra controlar PyAutoGUI 24h sem
    # supervisão visual, marcamos como pronto-pra-você-fazer.
    #
    # Quando confiar no workflow `preparar_post_tiktok_completo`, ative:
    #   from agents.autonomous_orchestrator import preparar_post_workflow
    #   r = preparar_post_workflow(produto, video_path)
    #   if r["sucesso"]:
    #       return {"sucesso": True, "novo_estado": ESTADO_DETALHES_PREENCHIDOS, ...}
    return {
        "sucesso":     True,
        "novo_estado": ESTADO_EDITADO,   # mantém — não avança automaticamente na v1
        "mensagem":    "Detalhes TikTok: aguardando você abrir o TikTok manualmente (v1 conservador)",
        "detalhes":    {"motivo": "supervisor v1 não controla PyAutoGUI"},
    }


# =================================================================
# STATE MACHINE: decide qual ação rodar
# =================================================================

def decidir_acao(estado: str, contexto: dict) -> tuple[Optional[Callable], str]:
    """
    Dado o estado atual de um produto, decide qual ação executar.
    Retorna (função_a_executar, descrição) ou (None, motivo) se nada a fazer.
    """
    if estado == ESTADO_NOVO:
        return None, "produto novo, aguardando planejamento (rode pipeline_planejar)"

    if estado == ESTADO_PLANO_PRONTO:
        # Plano OK mas assets ainda não verificados — vai pra detecção
        return None, "plano pronto, supervisor vai detectar próximo estado real"

    if estado == ESTADO_SEM_ASSETS:
        return None, ("assets insuficientes — colete/grave clipes ou rode "
                       "asset_collector_agent")

    if estado == ESTADO_PRONTO_PRA_EDITAR:
        return _acao_editar_video, "editar vídeo (Product Video Editor)"

    if estado == ESTADO_EDITADO:
        return _acao_preencher_detalhes_tiktok, "preencher detalhes TikTok"

    if estado == ESTADO_DETALHES_PREENCHIDOS:
        return None, "✋ pronto pra você revisar e postar manualmente"

    if estado == ESTADO_POSTADO:
        return None, "produto já postado (terminal)"

    if estado == ESTADO_ERRO_PAUSA:
        return None, "produto em ERRO_PAUSA — investigue e use --reset-pause"

    return None, f"estado desconhecido: {estado}"


# =================================================================
# ITERAÇÃO PRINCIPAL DO SUPERVISOR
# =================================================================

def _executar_uma_iteracao(state: dict, dry_run: bool = False,
                            produto_filtro: Optional[str] = None) -> dict:
    """
    Executa UMA iteração: visita produtos planejados, escolhe UM
    pra agir, atualiza state.

    Args:
        state:          dict do supervisor_state.json
        dry_run:        se True, lista mas não executa
        produto_filtro: se informado, só considera esse produto
                         (aceita nome completo ou slug)

    Returns: {acao_executada, produto, novo_estado, mensagem, deve_pausar}
    """
    resultado_iter = {
        "acao_executada":  False,
        "produto":         None,
        "novo_estado":     None,
        "mensagem":        "",
        "deve_pausar":     False,
        "dry_run":         dry_run,
    }

    produtos_info = _listar_planos_produtos()
    if not produtos_info:
        resultado_iter["mensagem"] = "Nenhum plano encontrado em shared/content_plans/ (procura 'plano_*.json')"
        return resultado_iter

    # ── 🎯 Filtro de produto (se especificado) ──
    if produto_filtro:
        _, slug_alvo = _resolver_produto_por_nome_ou_slug(produto_filtro)
        produtos_filtrados = [p for p in produtos_info if p["slug"] == slug_alvo]
        if not produtos_filtrados:
            # Sugestão fuzzy: produtos com slug parecido
            sugestoes = []
            for p in produtos_info:
                # match parcial: se algum token da query bate
                tokens_query = set(slug_alvo.split("_"))
                tokens_p = set(p["slug"].split("_"))
                if tokens_query & tokens_p:
                    sugestoes.append(p["produto"])
            mensagem = f"❌ Produto '{produto_filtro}' não encontrado nos planos"
            if sugestoes:
                mensagem += f". Talvez quis dizer: {sugestoes[:3]}"
            else:
                mensagem += (f". Planos disponíveis: "
                              f"{[p['produto'] for p in produtos_info[:5]]}")
            resultado_iter["mensagem"] = mensagem
            resultado_iter["filtro_produto_falhou"] = True
            return resultado_iter
        produtos_info = produtos_filtrados
        log.info(f"🎯 Filtro de produto ativo: {produtos_info[0]['produto']}")

    # Visita os primeiros N produtos (limite de segurança)
    candidatos = []
    for info in produtos_info[:MAX_PRODUTOS_POR_CICLO]:
        produto = info["produto"]
        slug = info["slug"]
        plano_path = info["plano_path"]
        # Check se já tá em ERRO_PAUSA ou POSTADO no state
        entrada = state.get("produtos", {}).get(slug, {})
        estado_persistido = entrada.get("estado")
        if estado_persistido in ESTADOS_TERMINAIS:
            continue  # ignora terminais
        # Limite de iterações por produto
        if entrada.get("iteracoes", 0) >= MAX_ITERS_POR_PRODUTO:
            log.warning(f"⏭️  {produto}: max iterações atingido — pulando")
            continue

        # Detecta estado real (filesystem) — passa plano_path explícito
        estado_real, contexto = _detectar_estado_real(produto, plano_path=plano_path)
        # Anexa metadata do plano no contexto
        contexto["plano_modified_at"] = info["modified_at"].isoformat(timespec="seconds")
        contexto["total_planos_produto"] = info["total_planos"]
        # Decide ação
        funcao, descricao = decidir_acao(estado_real, contexto)
        candidatos.append({
            "produto":   produto,
            "slug":      slug,
            "estado":    estado_real,
            "contexto":  contexto,
            "funcao":    funcao,
            "descricao": descricao,
            "info_plano": info,
        })

    # Loga inventário (mostra idade do plano se útil)
    log.info(f"📊 Iteração {state.get('iteracao', 0)}: {len(candidatos)} produto(s) ativo(s)")
    agora = datetime.now()
    for c in candidatos[:10]:
        marca = "🎬" if c["funcao"] else "⏸️"
        info = c["info_plano"]
        idade_dias = (agora - info["modified_at"]).days
        sufixo_planos = f" ({info['total_planos']} planos)" if info["total_planos"] > 1 else ""
        idade_str = f"{idade_dias}d" if idade_dias > 0 else "hoje"
        log.info(f"   {marca} {c['produto']:35s} [{c['estado']:23s}] "
                 f"plano {idade_str}{sufixo_planos} — {c['descricao']}")

    # Escolhe o PRIMEIRO com ação disponível (FIFO simples na v1)
    escolhido = next((c for c in candidatos if c["funcao"] is not None), None)
    if not escolhido:
        resultado_iter["mensagem"] = "Nenhum produto com ação pendente — nada a fazer"
        return resultado_iter

    # Em dry-run, registra o que faria e retorna
    if dry_run:
        resultado_iter["acao_executada"] = False
        resultado_iter["produto"] = escolhido["produto"]
        resultado_iter["mensagem"] = f"[DRY-RUN] faria: {escolhido['descricao']}"
        log.info(f"\n🔍 [DRY-RUN] ação que seria executada:")
        log.info(f"   Produto: {escolhido['produto']}")
        log.info(f"   Estado:  {escolhido['estado']}")
        log.info(f"   Ação:    {escolhido['descricao']}")
        return resultado_iter

    # ── EXECUÇÃO REAL ──
    produto = escolhido["produto"]
    slug = escolhido["slug"]
    funcao = escolhido["funcao"]
    log.info(f"\n▶️  Executando: {escolhido['descricao']}")
    log.info(f"   Produto: {produto}")

    # Incrementa contador de iteração do produto ANTES (evita loop infinito se crashar)
    entrada_atual = state.get("produtos", {}).get(slug, {})
    iteracoes_produto = entrada_atual.get("iteracoes", 0) + 1
    _atualizar_produto_no_state(state, slug,
                                  estado=escolhido["estado"],
                                  iteracoes=iteracoes_produto)
    _salvar_state(state)

    # Executa a ação
    inicio = time.time()
    try:
        resultado_acao = funcao(produto, escolhido["contexto"])
    except Exception as e:
        # Crash não tratado pela ação — pausa
        resultado_acao = {
            "sucesso":     False,
            "novo_estado": ESTADO_ERRO_PAUSA,
            "mensagem":    f"Crash inesperado: {type(e).__name__}: {str(e)[:140]}",
        }
    duracao_acao = round(time.time() - inicio, 2)

    # Memory contextual: registra aprendizado (best-effort)
    if _MEMORY_DISPONIVEL:
        try:
            registrar_aprendizado_execucao(
                etapa="supervisor.iteracao",
                resultado=resultado_acao,
                resumo=(
                    f"Supervisor executou '{escolhido['descricao']}' pra "
                    f"'{produto}' em {duracao_acao}s. "
                    f"Estado: {escolhido['estado']} → {resultado_acao.get('novo_estado')}. "
                    f"Resultado: {resultado_acao.get('mensagem', '?')[:100]}"
                ),
                tags=["supervisor", slug, escolhido['estado']],
            )
        except Exception:
            pass

    # Atualiza state com resultado
    novo_estado = resultado_acao.get("novo_estado", ESTADO_ERRO_PAUSA)
    detalhes = resultado_acao.get("detalhes", {})

    _atualizar_produto_no_state(state, slug,
                                  estado=novo_estado,
                                  ultimo_resultado={
                                      "sucesso":    resultado_acao.get("sucesso", False),
                                      "mensagem":   resultado_acao.get("mensagem", ""),
                                      "duracao_s":  duracao_acao,
                                      "detalhes":   detalhes,
                                  })

    resultado_iter["acao_executada"] = True
    resultado_iter["produto"] = produto
    resultado_iter["novo_estado"] = novo_estado
    resultado_iter["mensagem"] = resultado_acao.get("mensagem", "")

    log.info(f"   {'✅' if resultado_acao.get('sucesso') else '⚠️ '} "
             f"{escolhido['estado']} → {novo_estado} ({duracao_acao}s)")
    log.info(f"   {resultado_acao.get('mensagem', '?')}")

    # ── DECISÃO DE PAUSA (sua escolha: parar tudo e esperar) ──
    if novo_estado == ESTADO_ERRO_PAUSA:
        state["pause"] = {
            "ts":         datetime.now().isoformat(timespec="seconds"),
            "produto":    produto,
            "estado_antes": escolhido["estado"],
            "motivo":     resultado_acao.get("mensagem", "?"),
            "detalhes":   detalhes,
        }
        resultado_iter["deve_pausar"] = True
        log.error(f"\n🚨 PAUSA: erro em '{produto}' — supervisor vai parar.")
        log.error(f"   Conserte e rode --reset-pause + --daemon de novo")

    return resultado_iter


# =================================================================
# LOOP DAEMON
# =================================================================

class SupervisorContext:
    """Container pra controle do daemon (signal handling, sleep, etc)."""
    def __init__(self):
        self.parar = False
        self.ultimo_heartbeat = 0.0


def _instalar_signal_handlers(ctx: SupervisorContext):
    def handler(signum, frame):
        log.info(f"\n📡 Sinal {signum} recebido — saindo limpo na próxima iteração")
        ctx.parar = True
    try:
        signal.signal(signal.SIGINT, handler)
        # SIGTERM nem sempre existe no Windows
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, handler)
    except Exception:
        pass  # ambientes restritos


def loop_daemon(sleep_seg: float = SLEEP_DEFAULT_SEG,
                 max_iteracoes: Optional[int] = None,
                 produto_filtro: Optional[str] = None) -> dict:
    """
    Loop principal do daemon. Roda iterações até:
      - max_iteracoes alcançado (se passado)
      - ERRO_PAUSA disparado
      - SIGINT/SIGTERM
      - state.pause já preenchido (recusa rodar)
      - produto_filtro chegou em estado terminal (POSTADO/ERRO_PAUSA)

    Args:
        sleep_seg:      pausa entre iterações
        max_iteracoes:  limite de iterações por sessão (None = infinito)
        produto_filtro: se informado, só trabalha nesse produto

    Returns: dict resumo da sessão.
    """
    ctx = SupervisorContext()
    _instalar_signal_handlers(ctx)

    state = _ler_state()
    if state.get("pause"):
        return {
            "sucesso":   False,
            "mensagem":  ("Supervisor pausado por erro anterior. "
                          "Use --status pra ver e --reset-pause pra limpar."),
            "pause":     state["pause"],
        }

    log.info("=" * 60)
    log.info(f"🤖 SUPERVISOR DAEMON iniciado (PID {os.getpid()})")
    if produto_filtro:
        log.info(f"   🎯 Filtro: SÓ '{produto_filtro}'")
    log.info(f"   Sleep entre iterações: {sleep_seg}s")
    log.info(f"   Max iterações: {max_iteracoes or '∞'}")
    log.info("=" * 60)

    iteracao_inicial = state.get("iteracao", 0)
    iteracao_atual = iteracao_inicial
    sessao_iters = 0
    historico_sessao = []

    while not ctx.parar:
        iteracao_atual += 1
        sessao_iters += 1
        state["iteracao"] = iteracao_atual
        state["ultima_acao"] = datetime.now().isoformat(timespec="seconds")
        _atualizar_heartbeat(f"iter_{iteracao_atual}")

        try:
            resultado = _executar_uma_iteracao(state, dry_run=False,
                                                  produto_filtro=produto_filtro)
        except Exception as e:
            log.error(f"💥 CRASH FATAL na iteração: {e}")
            state["pause"] = {
                "ts":      datetime.now().isoformat(timespec="seconds"),
                "motivo":  f"crash fatal: {str(e)[:140]}",
            }
            _salvar_state(state)
            break

        historico_sessao.append({
            "iter":    iteracao_atual,
            "produto": resultado.get("produto"),
            "novo":    resultado.get("novo_estado"),
            "msg":     resultado.get("mensagem", "")[:100],
        })

        _salvar_state(state)

        # Pausa solicitada por erro
        if resultado.get("deve_pausar"):
            break

        # Filtro de produto falhou ANTES da iteração — sai direto
        if resultado.get("filtro_produto_falhou"):
            log.error(f"❌ {resultado.get('mensagem', 'filtro falhou')}")
            break

        # Max iterações?
        if max_iteracoes and sessao_iters >= max_iteracoes:
            log.info(f"⏹️  Max iterações ({max_iteracoes}) alcançado — saindo")
            break

        # Se temos filtro de produto, checa se ele terminou (estado terminal)
        if produto_filtro:
            _, slug_alvo = _resolver_produto_por_nome_ou_slug(produto_filtro)
            entrada = state.get("produtos", {}).get(slug_alvo, {})
            estado_atual = entrada.get("estado")
            if estado_atual in ESTADOS_TERMINAIS:
                log.info(f"✅ Produto '{produto_filtro}' chegou em estado terminal "
                         f"'{estado_atual}' — saindo do daemon")
                break

        # Nada a fazer: dorme mais
        if not resultado.get("acao_executada"):
            sleep_efetivo = SLEEP_QUANDO_NADA_FAZER
            log.info(f"💤 Nada a fazer — dormindo {sleep_efetivo}s "
                     f"(Ctrl+C pra sair)")
        else:
            sleep_efetivo = sleep_seg
            log.info(f"💤 Próxima iteração em {sleep_efetivo}s "
                     f"(Ctrl+C pra sair)")

        # Sleep com check de stop periódico (responsivo ao SIGINT)
        dormido = 0.0
        while dormido < sleep_efetivo and not ctx.parar:
            time.sleep(min(1.0, sleep_efetivo - dormido))
            dormido += 1.0
            # Atualiza heartbeat durante sleep também
            if dormido % HEARTBEAT_INTERVALO_SEG < 1.0:
                _atualizar_heartbeat(f"iter_{iteracao_atual}_sleeping")

    log.info(f"\n🛑 Daemon encerrando (sessão: {sessao_iters} iterações)")
    return {
        "sucesso":         not state.get("pause"),
        "iteracoes_sessao": sessao_iters,
        "iteracao_final":  iteracao_atual,
        "pause":           state.get("pause"),
        "historico":       historico_sessao,
    }


# =================================================================
# DASHBOARD / STATUS
# =================================================================

def imprimir_status(produto_filtro: Optional[str] = None) -> int:
    """Mostra dashboard read-only. Returns exit code.

    Se produto_filtro for informado, filtra a tabela de produtos pra esse só.
    """
    state = _ler_state()
    print("=" * 70)
    titulo = "🤖 SUPERVISOR — Status"
    if produto_filtro:
        titulo += f" (filtro: {produto_filtro})"
    print(f"  {titulo}")
    print("=" * 70)

    # Heartbeat
    hb_dt, hb_data = _heartbeat_recente()
    if hb_dt:
        idade = (datetime.now() - hb_dt).total_seconds()
        if idade < 60:
            print(f"  🟢 Heartbeat: {int(idade)}s atrás (provável vivo)")
        elif idade < 600:
            print(f"  🟡 Heartbeat: {int(idade/60)}min atrás (talvez dormindo)")
        else:
            print(f"  🔴 Heartbeat: {int(idade/60)}min atrás (provavelmente morto)")
        print(f"      Estado registrado: {(hb_data or {}).get('estado', '?')}")
    else:
        print(f"  ⚪ Heartbeat: nenhum (supervisor nunca rodou)")

    # Lock
    if LOCK_PATH.exists():
        try:
            pid_lock = LOCK_PATH.read_text().strip()
            print(f"  🔒 Lock: PID {pid_lock} ativo")
        except Exception:
            print(f"  ⚠️  Lock existe mas corrompido")
    else:
        print(f"  🔓 Lock: livre")

    # Pause
    pause = state.get("pause")
    if pause:
        print(f"\n  🚨 PAUSADO em {pause.get('ts', '?')}")
        print(f"      Produto: {pause.get('produto', '?')}")
        print(f"      Motivo:  {pause.get('motivo', '?')}")
        print(f"\n  Pra continuar: --reset-pause && --daemon")
    else:
        print(f"\n  ✅ Não pausado")

    # Iteração
    print(f"\n  📊 Iteração total: {state.get('iteracao', 0)}")
    print(f"      Última ação:    {state.get('ultima_acao', 'nunca')}")

    # Produtos
    produtos = state.get("produtos", {})
    if produto_filtro:
        _, slug_alvo = _resolver_produto_por_nome_ou_slug(produto_filtro)
        produtos = {k: v for k, v in produtos.items() if k == slug_alvo}
        if not produtos:
            print(f"\n  ⚠️  Produto '{produto_filtro}' não tem registro no state ainda")
            print(f"     (rode --single ou --dry-run primeiro)")
            print("=" * 70)
            return 1

    if produtos:
        print(f"\n  📦 Produtos rastreados: {len(produtos)}")
        # Conta por estado
        contagem = {}
        for slug, ent in produtos.items():
            est = ent.get("estado", "?")
            contagem[est] = contagem.get(est, 0) + 1
        for est in PROGRESSO_ESTADOS + [ESTADO_ERRO_PAUSA]:
            n = contagem.get(est, 0)
            if n > 0:
                # Marca progresso
                idx = PROGRESSO_ESTADOS.index(est) if est in PROGRESSO_ESTADOS else -1
                pct = f" ({int((idx+1)/len(PROGRESSO_ESTADOS)*100)}%)" if idx >= 0 else ""
                marca = "🚨" if est == ESTADO_ERRO_PAUSA else "✅" if est == ESTADO_POSTADO else "🔄"
                print(f"      {marca} {est:25s} {n} produto(s){pct}")

        # Lista detalhada dos primeiros 10
        print(f"\n  📋 Detalhes (primeiros 10):")
        for slug, ent in list(produtos.items())[:10]:
            est = ent.get("estado", "?")
            iters = ent.get("iteracoes", 0)
            atualizado = ent.get("ultima_atualizacao", "?")[:19]
            print(f"      • {slug:30s} [{est:23s}] iters={iters} ({atualizado})")
    else:
        print(f"\n  📦 Nenhum produto rastreado ainda")

    print("=" * 70)
    return 0 if not pause else 2


# =================================================================
# CLI
# =================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Supervisor — daemon que orquestra Jarvis 24h"
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--daemon", action="store_true",
                        help="Loop 24h (Ctrl+C pra sair)")
    grupo.add_argument("--single", action="store_true",
                        help="Roda 1 iteração e sai")
    grupo.add_argument("--status", action="store_true",
                        help="Dashboard read-only (não modifica nada)")
    grupo.add_argument("--dry-run", action="store_true",
                        dest="dry_run",
                        help="Mostra o que faria sem executar")
    grupo.add_argument("--reset-pause", action="store_true",
                        dest="reset_pause",
                        help="Limpa estado de pause anterior")
    grupo.add_argument("--marcar-postado", default=None,
                        dest="marcar_postado", metavar="PRODUTO",
                        help="Marca produto como POSTADO (terminal). Aceita nome ou slug.")
    grupo.add_argument("--marcar-preparado", default=None,
                        dest="marcar_preparado", metavar="PRODUTO",
                        help="Marca produto como DETALHES_PREENCHIDOS (pré-publicação)")
    grupo.add_argument("--desmarcar-postado", default=None,
                        dest="desmarcar_postado", metavar="PRODUTO",
                        help="Rollback: volta produto de POSTADO pra preparado/editado")

    parser.add_argument("--nota", default="",
                        help="Nota opcional ao marcar (vai pra memória)")
    parser.add_argument("--produto", default=None, metavar="PRODUTO",
                        help="Filtra ações pra UM produto específico "
                             "(nome completo ou slug). Aplica em "
                             "--dry-run, --single, --daemon, --status.")

    parser.add_argument("--sleep", type=float, default=SLEEP_DEFAULT_SEG,
                        help=f"Segundos entre iterações no daemon (default: {SLEEP_DEFAULT_SEG})")
    parser.add_argument("--max-iter", type=int, default=None,
                        dest="max_iter",
                        help="Limite de iterações por sessão (default: infinito)")
    args = parser.parse_args()

    _garantir_dirs()

    # Default = status se nada foi passado
    if not any([args.daemon, args.single, args.status, args.dry_run,
                args.reset_pause, args.marcar_postado, args.marcar_preparado,
                args.desmarcar_postado]):
        args.status = True

    # ── Comandos de marcação (não precisam de lock — operações curtas) ──
    if args.marcar_postado:
        r = marcar_produto_postado(args.marcar_postado, nota_humana=args.nota)
        print()
        print("=" * 60)
        if r["sucesso"]:
            print(f"  ✅ {r['mensagem']}")
            if r.get("estado_antes"):
                print(f"     Estado: {r.get('estado_antes')} → {r.get('estado_novo')}")
            if r.get("lead_time_dias") is not None:
                print(f"     Lead time desde o plano: {r['lead_time_dias']} dia(s)")
            if r.get("sem_video"):
                print(f"     ⚠️  vídeo não encontrado no disco")
            if r.get("flag_postado"):
                print(f"     Flag: {r['flag_postado']}")
        else:
            print(f"  ❌ {r.get('mensagem', 'falha')}")
        print("=" * 60)
        return 0 if r["sucesso"] else 2

    if args.marcar_preparado:
        r = marcar_produto_preparado(args.marcar_preparado, nota_humana=args.nota)
        print()
        print("=" * 60)
        if r["sucesso"]:
            print(f"  ✅ {r['mensagem']}")
            print(f"     Estado: {r.get('estado_antes')} → {r.get('estado_novo')}")
        else:
            print(f"  ❌ {r.get('mensagem', 'falha')}")
        print("=" * 60)
        return 0 if r["sucesso"] else 2

    if args.desmarcar_postado:
        r = desmarcar_produto_postado(args.desmarcar_postado)
        print()
        print("=" * 60)
        if r["sucesso"]:
            print(f"  ✅ {r['mensagem']}")
        else:
            print(f"  ❌ {r.get('mensagem', 'falha')}")
        print("=" * 60)
        return 0 if r["sucesso"] else 2

    # --status: sem lock, read-only
    if args.status:
        return imprimir_status(produto_filtro=args.produto)

    # --reset-pause: limpa pause e sai (não usa --produto)
    if args.reset_pause:
        state = _ler_state()
        pause_anterior = state.get("pause")
        # Limpa o pause global
        state["pause"] = None

        # Devolve produtos em ERRO_PAUSA pra fila (volta pra "novo"
        # → o supervisor vai re-detectar o estado real no filesystem)
        produtos_resetados = []
        for slug, ent in state.get("produtos", {}).items():
            if ent.get("estado") == ESTADO_ERRO_PAUSA:
                ent["estado"] = ESTADO_NOVO
                ent["iteracoes"] = 0  # reseta contador (segunda chance)
                hist = ent.get("historico", [])
                hist.append({
                    "ts":   datetime.now().isoformat(timespec="seconds"),
                    "de":   ESTADO_ERRO_PAUSA,
                    "para": ESTADO_NOVO,
                    "motivo": "reset-pause manual",
                })
                ent["historico"] = hist[-20:]
                produtos_resetados.append(slug)

        _salvar_state(state)

        if pause_anterior:
            log.info(f"🧹 Limpando pause anterior: {pause_anterior.get('motivo', '?')}")
        else:
            log.info("ℹ️  Sem pause global pra limpar")
        if produtos_resetados:
            log.info(f"♻️  Produtos devolvidos pra fila: {produtos_resetados}")
        print("✅ Reset concluído. Use --daemon ou --single pra continuar.")
        return 0

    # --dry-run: sem lock, mostra o que faria
    if args.dry_run:
        state = _ler_state()
        if state.get("pause"):
            log.warning(f"⚠️  Sistema pausado — dry-run mesmo assim")
        log.info("=" * 60)
        log.info("🔍 SUPERVISOR DRY-RUN — não modifica nada")
        log.info("=" * 60)
        r = _executar_uma_iteracao(state, dry_run=True, produto_filtro=args.produto)
        # Exibe mensagem se houve mensagem importante (erro de filtro etc)
        if r.get("filtro_produto_falhou"):
            log.error(r.get("mensagem", "filtro falhou"))
            return 2
        if not r.get("acao_executada") and r.get("mensagem"):
            log.info(f"ℹ️  {r['mensagem']}")
        return 0

    # --single ou --daemon: precisa de lock
    ok_lock, msg_lock = _checar_e_criar_lock()
    if not ok_lock:
        log.error(f"❌ {msg_lock}")
        return 2

    try:
        if args.single:
            state = _ler_state()
            if state.get("pause"):
                log.error(f"⚠️  Supervisor pausado: {state['pause'].get('motivo')}")
                log.error(f"   Use --reset-pause pra liberar")
                return 2
            state["iteracao"] = state.get("iteracao", 0) + 1
            _atualizar_heartbeat("single_shot")
            log.info("=" * 60)
            log.info("🤖 SUPERVISOR SINGLE-SHOT — 1 iteração e sai")
            if args.produto:
                log.info(f"   🎯 Filtro: SÓ '{args.produto}'")
            log.info("=" * 60)
            resultado = _executar_uma_iteracao(state, dry_run=False,
                                                  produto_filtro=args.produto)
            _salvar_state(state)
            if resultado.get("filtro_produto_falhou"):
                log.error(resultado.get("mensagem", "filtro falhou"))
                return 2
            return 0 if not resultado.get("deve_pausar") else 2

        if args.daemon:
            resumo = loop_daemon(sleep_seg=args.sleep,
                                  max_iteracoes=args.max_iter,
                                  produto_filtro=args.produto)
            print()
            print("=" * 60)
            print(f"  🛑 Daemon encerrado")
            print(f"  Iterações na sessão: {resumo.get('iteracoes_sessao', 0)}")
            if resumo.get("pause"):
                print(f"  🚨 Pause: {resumo['pause'].get('motivo', '?')}")
            print("=" * 60)
            return 0 if not resumo.get("pause") else 2

    finally:
        _liberar_lock()
        _atualizar_heartbeat("encerrado")

    return 0


if __name__ == "__main__":
    sys.exit(main())