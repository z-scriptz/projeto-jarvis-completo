# shared/production_state.py
# Estado de PRODUÇÃO por produto — fonte única de verdade pro Production Runner.
#
# POR QUE EXISTE:
#   O projeto tinha estado espalhado (state.json do ciclo THINK/ACT/OBSERVE,
#   supervisor_state.json da postagem). Nenhum deles responde "qual o status
#   de produção de cada produto?". Pra rodar um lote 24h sem o Jarvis se perder,
#   precisa de UMA fonte que diga, por produto: gerou? aprovou? bloqueou? erro?
#
#   Esta camada é independente e limpa — NÃO mexe no state_manager nem no
#   supervisor (que são complexos e cuidam de outras coisas). Só registra o
#   resultado de produção de cada produto.
#
# ARQUIVO: shared/state/jarvis_state.json
#   {
#     "cortador_de_legumes": {
#        "produto": "Cortador de Legumes",
#        "status": "video_gerado" | "bloqueado" | "erro" | "revisar",
#        "ultimo_video": "outputs/.../video.mp4",
#        "quality_gate": "aprovado" | "bloqueado",
#        "motivos": [...], "erro": "...",
#        "ultima_execucao": "2026-06-11 13:47:06"
#     }, ...
#   }

import json
import re
import time
from pathlib import Path
from typing import Optional

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    log = logging.getLogger("production_state")

# Local do estado. Tenta achar a raiz do projeto; cai pra cwd.
def _state_path() -> Path:
    # shared/production_state.py → raiz = parent.parent
    raiz = Path(__file__).resolve().parent.parent
    d = raiz / "shared" / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d / "jarvis_state.json"


STATUS_VALIDOS = {
    "pendente",       # ainda não processado
    "processando",    # em andamento (detecta travamento)
    "video_gerado",   # sucesso, aprovado na 1ª tentativa
    "recuperado",     # aprovado após autocorreção (recoleta + re-tentativa)
    "precisa_revisar",# bloqueado mesmo após autocorreção — material insuficiente
    "revisar",        # gerou mas qualidade duvidosa (ex: forçado)
    "bloqueado",      # Quality Gate barrou (sem autocorreção)
    "erro",           # falhou após retries
}


def _slug(produto: str) -> str:
    s = re.sub(r"[^\w\s-]", "", (produto or "").lower())
    return re.sub(r"[\s-]+", "_", s).strip("_")


def carregar() -> dict:
    """Lê o estado inteiro. Nunca quebra — se corrompido, retorna vazio."""
    p = _state_path()
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"jarvis_state.json corrompido ({e}) — usando estado vazio")
        return {}


def _salvar_tudo(estado: dict) -> bool:
    """Grava o estado inteiro de forma atômica (tmp + replace)."""
    p = _state_path()
    try:
        tmp = p.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False, indent=2)
        tmp.replace(p)   # replace atômico: nunca deixa arquivo meio-escrito
        return True
    except Exception as e:
        log.error(f"Falha ao salvar jarvis_state.json: {e}")
        return False


def atualizar_produto(produto: str, **campos) -> dict:
    """
    Atualiza (ou cria) o registro de um produto. Merge dos campos passados.
    Sempre carimba ultima_execucao. Retorna o registro atualizado.

    Ex: atualizar_produto("Cortador de Legumes", status="video_gerado",
                           ultimo_video="...", quality_gate="aprovado")
    """
    estado = carregar()
    slug = _slug(produto)
    reg = estado.get(slug, {"produto": produto})
    reg.update(campos)
    reg["produto"] = produto
    reg["ultima_execucao"] = _agora()
    if "status" in campos and campos["status"] not in STATUS_VALIDOS:
        log.warning(f"status '{campos['status']}' não é padrão "
                    f"(válidos: {sorted(STATUS_VALIDOS)})")
    estado[slug] = reg
    _salvar_tudo(estado)
    return reg


def obter_produto(produto: str) -> Optional[dict]:
    """Retorna o registro de um produto, ou None."""
    return carregar().get(_slug(produto))


def status_de(produto: str) -> str:
    """Status atual de um produto (ou 'pendente' se nunca processado)."""
    reg = obter_produto(produto)
    return reg.get("status", "pendente") if reg else "pendente"


def resumo() -> dict:
    """Conta produtos por status (pra relatório/dashboard)."""
    estado = carregar()
    contagem = {}
    for reg in estado.values():
        s = reg.get("status", "pendente")
        contagem[s] = contagem.get(s, 0) + 1
    return contagem


def _agora() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")