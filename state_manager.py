# memory/state_manager.py
# Memória operacional persistente do AgenteIA
#
# Salva o estado atual do agente em memory/state.json
# Permite retomada inteligente após falha e evita ações duplicadas
#
# Fluxo:
#   THINK  → salva produto_atual, etapa="think_concluido"
#   ACT    → salva etapa="act_concluido", ultima_acao
#   OBSERVE→ salva etapa="observe_concluido", ultima_observacao
#   FIM    → limpar_estado()

import json
import time
import uuid
from pathlib import Path
from typing import Any

from shared.logger import get_logger

log = get_logger(__name__)

# =========================
# CAMINHO DO ARQUIVO
# =========================

STATE_FILE = Path(__file__).parent / "state.json"

# =========================
# ESTRUTURA PADRÃO
# =========================

ESTADO_VAZIO: dict = {
    "estado_atual":       "ocioso",
    "produto_atual":      "",
    "plataforma_atual":   "",
    "linha_planilha":     None,
    "etapa":              "",
    "ultima_acao":        "",
    "ultima_observacao":  "",
    "estado_tela":        "",
    "workflow_id":        "",
    "tentativas":         0,
    "max_tentativas":     3,
    "timestamp_inicio":   "",
    "timestamp_update":   "",
    "historico_etapas":   [],
}


# =========================
# OPERAÇÕES PRINCIPAIS
# =========================

def salvar_estado(dados: dict) -> bool:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        dados["timestamp_update"] = _agora()
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        log.debug(f"💾 Estado salvo: etapa='{dados.get('etapa')}' | produto='{dados.get('produto_atual')}'")
        return True
    except Exception as e:
        log.error(f"Erro ao salvar estado: {e}")
        return False


def carregar_estado() -> dict:
    if not STATE_FILE.exists():
        log.debug("state.json não existe — retornando estado vazio")
        return ESTADO_VAZIO.copy()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            dados = json.load(f)
        estado = {**ESTADO_VAZIO, **dados}
        log.debug(f"📂 Estado carregado: etapa='{estado.get('etapa')}' | produto='{estado.get('produto_atual')}'")
        return estado
    except json.JSONDecodeError as e:
        log.error(f"state.json corrompido: {e} — resetando para estado vazio")
        return ESTADO_VAZIO.copy()
    except Exception as e:
        log.error(f"Erro ao carregar estado: {e}")
        return ESTADO_VAZIO.copy()


# Alias — módulos externos (publish_guard, auditor, sheets_engine) usam ler_estado()
ler_estado = carregar_estado


def atualizar_estado(chave: str, valor: Any) -> bool:
    estado = carregar_estado()
    estado[chave] = valor
    return salvar_estado(estado)


def atualizar_varios(updates: dict) -> bool:
    estado = carregar_estado()
    estado.update(updates)
    return salvar_estado(estado)


def registrar_etapa(etapa: str, detalhe: str = "") -> bool:
    estado = carregar_estado()
    historico = estado.get("historico_etapas", [])
    historico.append({
        "etapa":   etapa,
        "detalhe": detalhe,
        "quando":  _agora(),
    })
    estado["etapa"] = etapa
    estado["historico_etapas"] = historico[-20:]
    return salvar_estado(estado)


def limpar_estado() -> bool:
    try:
        estado_anterior = carregar_estado()
        novo_estado = ESTADO_VAZIO.copy()
        novo_estado["historico_etapas"] = [{
            "etapa":   "ciclo_anterior_concluido",
            "detalhe": f"produto='{estado_anterior.get('produto_atual')}' | workflow={estado_anterior.get('workflow_id')}",
            "quando":  _agora(),
        }]
        log.info(f"🧹 Estado limpo após ciclo: workflow={estado_anterior.get('workflow_id')}")
        return salvar_estado(novo_estado)
    except Exception as e:
        log.error(f"Erro ao limpar estado: {e}")
        return False


# =========================
# HELPERS DE WORKFLOW
# =========================

def iniciar_workflow(produto: str, plataforma: str, linha: int) -> str:
    estado = carregar_estado()
    tentativas = 0
    if estado.get("produto_atual") == produto and estado.get("estado_atual") != "ocioso":
        tentativas = estado.get("tentativas", 0) + 1
        log.warning(f"⚠️ Retomando produto '{produto}' — tentativa {tentativas}")

    workflow_id = f"wf_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    salvar_estado({
        **ESTADO_VAZIO,
        "estado_atual":     "processando",
        "produto_atual":    produto,
        "plataforma_atual": plataforma,
        "linha_planilha":   linha,
        "workflow_id":      workflow_id,
        "tentativas":       tentativas,
        "timestamp_inicio": _agora(),
        "historico_etapas": [{
            "etapa": "workflow_iniciado",
            "detalhe": f"produto='{produto}' | plataforma={plataforma} | linha={linha}",
            "quando": _agora(),
        }],
    })
    log.info(f"🆔 Workflow iniciado: {workflow_id} | '{produto}'")
    return workflow_id


def ja_processando(produto: str) -> bool:
    estado = carregar_estado()
    em_progresso = (
        estado.get("produto_atual") == produto
        and estado.get("estado_atual") == "processando"
        and estado.get("etapa") not in ("observe_concluido", "")
    )
    if em_progresso:
        log.warning(f"⚠️ '{produto}' já está sendo processado (etapa: {estado.get('etapa')})")
    return em_progresso


def excedeu_tentativas() -> bool:
    estado = carregar_estado()
    excedeu = estado.get("tentativas", 0) >= estado.get("max_tentativas", 3)
    if excedeu:
        log.error(
            f"🚫 Produto '{estado.get('produto_atual')}' excedeu "
            f"{estado.get('max_tentativas')} tentativas — abortando"
        )
    return excedeu


# =========================
# UTILITÁRIO
# =========================

def _agora() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def status_atual() -> str:
    e = carregar_estado()
    if e["estado_atual"] == "ocioso":
        return "🟢 Agente ocioso"
    return (
        f"🔄 {e['estado_atual'].upper()} | "
        f"produto='{e['produto_atual']}' | "
        f"etapa='{e['etapa']}' | "
        f"tentativa {e['tentativas']+1}/{e['max_tentativas']}"
    )