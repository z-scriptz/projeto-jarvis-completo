# brain/decision_engine.py
# Motor de decisão autônoma do AgenteIA
#
# Recebe a análise do OBSERVE (Gemini Vision) e decide:
#   - Qual workflow executar a seguir
#   - Se deve tentar novamente
#   - Se deve abortar com erro
#   - Se o objetivo foi concluído
#
# É o cérebro entre OBSERVE e ACT:
#   THINK → ACT → OBSERVE → DECIDE → ACT → OBSERVE → DECIDE → ...

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from shared.logger import get_logger

log = get_logger(__name__)


# =========================
# TIPOS DE DECISÃO
# =========================

class TipoDecisao(str, Enum):
    CONTINUAR       = "continuar"       # executar próximo workflow
    REPETIR         = "repetir"         # repetir o mesmo workflow (tela ainda carregando)
    AGUARDAR        = "aguardar"        # esperar e observar de novo
    CONCLUIDO       = "concluido"       # objetivo atingido, encerrar ciclo
    ERRO_RECUPERAVEL= "erro_recuperavel"# tentar novamente do início
    ERRO_FATAL      = "erro_fatal"      # abortar e registrar erro


@dataclass
class Decisao:
    """Resultado do motor de decisão."""
    tipo:             TipoDecisao
    motivo:           str
    proximo_workflow: Optional[str] = None   # nome do JSON a executar
    aguardar_segundos: float = 0             # espera antes da próxima ação
    dados_extras:     dict = field(default_factory=dict)

    def __str__(self):
        base = f"[{self.tipo.upper()}] {self.motivo}"
        if self.proximo_workflow:
            base += f" → workflow: '{self.proximo_workflow}'"
        if self.aguardar_segundos:
            base += f" (aguarda {self.aguardar_segundos}s)"
        return base


# =========================
# REGRAS DE DECISÃO
# =========================
# Cada regra é: (condição, Decisao)
# A engine percorre em ordem e retorna a primeira que bater.
# Para adicionar lógica: insira uma nova regra no lugar certo.

def _avaliar_alerta(analise: dict, contexto: dict) -> Optional[Decisao]:
    """Alertas visuais têm prioridade máxima."""
    alerta = analise.get("alerta")
    if not alerta:
        return None

    alerta_lower = alerta.lower()

    # Captcha / verificação humana
    if any(p in alerta_lower for p in ("captcha", "verificação", "verify", "bot")):
        return Decisao(
            tipo=TipoDecisao.ERRO_FATAL,
            motivo=f"Captcha detectado — intervenção humana necessária: {alerta}",
        )

    # Login expirado
    if any(p in alerta_lower for p in ("login", "entrar", "sign in", "sessão", "session")):
        return Decisao(
            tipo=TipoDecisao.ERRO_FATAL,
            motivo=f"Sessão expirada — é necessário fazer login novamente: {alerta}",
        )

    # Limite de upload / quota
    if any(p in alerta_lower for p in ("limite", "limit", "quota", "ban", "bloqueado")):
        return Decisao(
            tipo=TipoDecisao.ERRO_FATAL,
            motivo=f"Conta bloqueada ou limite atingido: {alerta}",
        )

    # Erro genérico de rede
    if any(p in alerta_lower for p in ("erro", "error", "failed", "falhou", "unavailable")):
        return Decisao(
            tipo=TipoDecisao.ERRO_RECUPERAVEL,
            motivo=f"Erro recuperável detectado: {alerta}",
            aguardar_segundos=5,
        )

    return None


def _avaliar_estado(analise: dict, contexto: dict) -> Optional[Decisao]:
    """Decisões baseadas no estado geral da tela."""
    estado    = analise.get("estado", "desconhecido")
    app_ativo = analise.get("app_ativo", "").lower()
    plataforma = contexto.get("plataforma", "tiktok").lower()
    etapa_atual = contexto.get("etapa_atual", "")

    # Tela ainda carregando — aguarda e re-observa
    if estado == "carregando":
        return Decisao(
            tipo=TipoDecisao.AGUARDAR,
            motivo="Página ainda carregando",
            aguardar_segundos=4,
        )

    # Tela bloqueada (modal, pop-up, cookie banner)
    if estado == "bloqueado":
        return Decisao(
            tipo=TipoDecisao.CONTINUAR,
            motivo="Tela bloqueada — tentando fechar modal",
            proximo_workflow="fechar_modal",
            aguardar_segundos=1,
        )

    # App correto aberto e pronto
    if estado == "pronto" and plataforma in app_ativo:

        # Decide próximo passo com base na etapa atual do ciclo
        if etapa_atual in ("act_concluido", "workflow_postar_tiktok_concluido"):
            return Decisao(
                tipo=TipoDecisao.CONTINUAR,
                motivo=f"{plataforma.title()} aberto e pronto para upload",
                proximo_workflow=f"upload_{plataforma}_video",
            )

        if etapa_atual in ("upload_concluido",):
            return Decisao(
                tipo=TipoDecisao.CONCLUIDO,
                motivo="Upload confirmado pelo Gemini Vision — ciclo encerrado com sucesso",
            )

        # Pronto mas etapa não mapeada — conclui conservadoramente
        return Decisao(
            tipo=TipoDecisao.CONCLUIDO,
            motivo=f"Tela pronta (etapa: {etapa_atual}) — considerando ciclo concluído",
        )

    # App errado aberto
    if estado == "pronto" and plataforma not in app_ativo and app_ativo:
        return Decisao(
            tipo=TipoDecisao.ERRO_RECUPERAVEL,
            motivo=f"App errado aberto: '{app_ativo}' (esperado: '{plataforma}')",
            aguardar_segundos=2,
        )

    # Estado desconhecido
    return Decisao(
        tipo=TipoDecisao.AGUARDAR,
        motivo=f"Estado desconhecido: '{estado}' — re-observando",
        aguardar_segundos=3,
    )


# =========================
# ENGINE PRINCIPAL
# =========================

def decidir(
    analise: dict,
    contexto: dict,
    tentativas_decisao: int = 0,
    max_tentativas: int = 3,
) -> Decisao:
    """
    Recebe a análise do OBSERVE e retorna a decisão autônoma.

    Args:
        analise:            dict retornado pelo Gemini Vision (observar_e_analisar)
        contexto:           estado atual do ciclo — campos esperados:
                              "plataforma"  (str) — tiktok | instagram | youtube
                              "produto"     (str) — nome do produto
                              "etapa_atual" (str) — etapa do state_manager
        tentativas_decisao: quantas vezes este ponto de decisão já foi atingido
        max_tentativas:     limite antes de escalar para ERRO_FATAL

    Returns:
        Decisao com tipo, motivo, próximo workflow e tempo de espera

    Uso em main.py:
        from brain.decision_engine import decidir, TipoDecisao

        obs = observe("apos_abrir_tiktok")
        decisao = decidir(obs["analise"], contexto={"plataforma": "tiktok", ...})

        if decisao.tipo == TipoDecisao.CONTINUAR:
            executar_workflow(decisao.proximo_workflow)
        elif decisao.tipo == TipoDecisao.CONCLUIDO:
            ...
    """
    # Guarda de segurança — evita loop infinito de decisões
    if tentativas_decisao >= max_tentativas:
        return Decisao(
            tipo=TipoDecisao.ERRO_FATAL,
            motivo=f"Máximo de {max_tentativas} ciclos de decisão atingido sem conclusão",
        )

    # OBSERVE falhou completamente
    if not analise or "erro" in analise:
        erro = analise.get("erro", "análise vazia") if analise else "OBSERVE não retornou dados"
        retry_excedido = analise.get("retry_excedido", False) if analise else False

        if retry_excedido:
            return Decisao(
                tipo=TipoDecisao.ERRO_RECUPERAVEL,
                motivo=f"Gemini Vision indisponível: {erro}",
                aguardar_segundos=10,
            )
        return Decisao(
            tipo=TipoDecisao.AGUARDAR,
            motivo=f"OBSERVE falhou pontualmente: {erro}",
            aguardar_segundos=5,
        )

    # Avalia alertas primeiro (prioridade máxima)
    decisao = _avaliar_alerta(analise, contexto)
    if decisao:
        log.info(f"🚨 Decisão (alerta): {decisao}")
        return decisao

    # Avalia estado da tela
    decisao = _avaliar_estado(analise, contexto)
    log.info(f"🧭 Decisão: {decisao}")
    return decisao


def resumo_decisao(decisao: Decisao) -> str:
    """Retorna string de log amigável para o ciclo principal."""
    icones = {
        TipoDecisao.CONTINUAR:        "▶️",
        TipoDecisao.REPETIR:          "🔁",
        TipoDecisao.AGUARDAR:         "⏳",
        TipoDecisao.CONCLUIDO:        "✅",
        TipoDecisao.ERRO_RECUPERAVEL: "⚠️",
        TipoDecisao.ERRO_FATAL:       "🚫",
    }
    return f"{icones.get(decisao.tipo, '❓')} {decisao}"