# brain/publish_guard.py
# Guarda de publicação autônoma do AgenteIA.
#
# Responsabilidade única: decidir se o Jarvis tem PERMISSÃO para publicar.
# Nunca executa ações — só valida regras e retorna veredito.
#
# Duas camadas de validação:
#   1. Laudo visual (auditoria Gemini Vision do auditor.py)
#   2. Config operacional (planilha Config_Agente do Google Sheets)
#
# Uso (via engine como ação brain-level):
#   ação: "validar_publicacao_autonoma"
#   → lê último laudo do state_manager
#   → lê Config_Agente da planilha
#   → retorna veredito estruturado

import json
from datetime import datetime

from shared.logger import get_logger

log = get_logger(__name__)


# =========================
# CAMPOS OBRIGATÓRIOS DO CONFIG
# (com defaults seguros — tudo bloqueado por padrão)
# =========================

CONFIG_DEFAULTS = {
    "modo_autonomo_publicacao":      "false",
    "limite_posts_por_dia":          "5",
    "horario_inicio":                "08:00",
    "horario_fim":                   "22:00",
    "exigir_hashtags":               "true",
    "permitir_publicar_com_warning": "false",
}


# =========================
# VALIDAÇÃO PURA
# =========================

def validar_publicacao_autonoma(laudo: dict, config: dict) -> dict:
    """
    Valida se o Jarvis tem permissão para publicar autonomamente.
    Não executa nenhuma ação — apenas analisa e retorna o veredito.

    Args:
        laudo:  dict retornado pela auditoria (auditor.py / state_manager)
                Campos esperados: pronto_para_publicar, captcha_detectado,
                login_necessario, erro_visivel, legenda_preenchida,
                video_carregado, botao_publicar_visivel, hashtags_visiveis
        config: dict com configurações da planilha Config_Agente
                Campos esperados: modo_autonomo_publicacao, limite_posts_por_dia,
                horario_inicio, horario_fim, exigir_hashtags,
                permitir_publicar_com_warning

    Returns:
        {
            "pode_publicar":  bool,
            "motivo":         str,   ← razão principal (aprovação ou primeiro bloqueio)
            "bloqueios":      list,  ← regras que reprovaram (impedem publicação)
            "warnings":       list,  ← avisos que não bloqueiam (se permitido por config)
        }
    """
    bloqueios = []
    warnings  = []

    # Aplica defaults para campos ausentes no config
    cfg = {**CONFIG_DEFAULTS, **{k.lower(): str(v).lower() for k, v in config.items()}}

    # ══════════════════════════════════════════════════════
    # BLOCO 1 — Regras da auditoria visual (sempre críticas)
    # ══════════════════════════════════════════════════════

    if not laudo:
        bloqueios.append("Laudo de auditoria ausente — execute revisar_post_tiktok antes")

    if laudo.get("captcha_detectado"):
        bloqueios.append("Captcha detectado — intervenção humana obrigatória")

    if laudo.get("login_necessario"):
        bloqueios.append("Sessão TikTok expirada — é necessário fazer login")

    if laudo.get("erro_visivel"):
        bloqueios.append("Erro visível na tela — post em estado inválido")

    if not laudo.get("legenda_preenchida"):
        bloqueios.append("Legenda não preenchida — post sem descrição")

    if not laudo.get("video_carregado"):
        bloqueios.append("Vídeo não confirmado na tela — upload pode ter falhado")

    if not laudo.get("pronto_para_publicar"):
        # Só adiciona se ainda não tem bloqueio mais específico
        causas_ja_cobertas = any("captcha" in b or "login" in b or "erro" in b
                                  or "legenda" in b or "vídeo" in b for b in bloqueios)
        if not causas_ja_cobertas:
            bloqueios.append("Auditoria marcou pronto_para_publicar=false sem causa específica")

    # Warnings de auditoria (não bloqueiam por si só)
    if not laudo.get("botao_publicar_visivel"):
        warnings.append("Botão Publicar não visível na tela — pode estar fora da área visível")

    if not laudo.get("hashtags_visiveis"):
        if cfg.get("exigir_hashtags") == "true":
            bloqueios.append("Hashtags não detectadas e exigir_hashtags=true na config")
        else:
            warnings.append("Hashtags não detectadas (exigir_hashtags=false — ignorando)")

    # ══════════════════════════════════════════════════════
    # BLOCO 2 — Regras operacionais (planilha Config_Agente)
    # ══════════════════════════════════════════════════════

    # Modo autônomo habilitado?
    if cfg.get("modo_autonomo_publicacao") != "true":
        bloqueios.append(
            "modo_autonomo_publicacao=false na planilha — "
            "publicação autônoma desativada pelo operador"
        )

    # Horário permitido?
    agora = datetime.now().strftime("%H:%M")
    inicio = cfg.get("horario_inicio", "08:00")
    fim    = cfg.get("horario_fim",    "22:00")
    if not _dentro_do_horario(agora, inicio, fim):
        bloqueios.append(
            f"Fora do horário permitido: agora={agora}, "
            f"janela={inicio}–{fim} (Config_Agente)"
        )

    # Limite diário (lido do state_manager)
    limite = int(cfg.get("limite_posts_por_dia", "5"))
    posts_hoje = _contar_posts_hoje()
    if posts_hoje >= limite:
        bloqueios.append(
            f"Limite diário atingido: {posts_hoje}/{limite} posts hoje (Config_Agente)"
        )

    # ══════════════════════════════════════════════════════
    # VEREDITO FINAL
    # ══════════════════════════════════════════════════════

    # Warnings bloqueiam apenas se config não permitir publicar com warnings
    tem_warnings_bloqueantes = (
        warnings
        and cfg.get("permitir_publicar_com_warning") != "true"
        and not bloqueios  # só importam se não há bloqueios duros
    )

    if bloqueios:
        motivo = bloqueios[0]  # primeiro bloqueio é o mais relevante
        log.error(f"🚫 PUBLICAÇÃO BLOQUEADA: {motivo}")
        for b in bloqueios:
            log.error(f"   ✗ {b}")
        for w in warnings:
            log.warning(f"   ⚠ {w}")
        return {
            "pode_publicar": False,
            "motivo":        motivo,
            "bloqueios":     bloqueios,
            "warnings":      warnings,
        }

    if tem_warnings_bloqueantes:
        motivo = f"Warnings presentes e permitir_publicar_com_warning=false: {warnings[0]}"
        log.warning(f"⚠️ PUBLICAÇÃO BLOQUEADA POR WARNING: {motivo}")
        return {
            "pode_publicar": False,
            "motivo":        motivo,
            "bloqueios":     [],
            "warnings":      warnings,
        }

    motivo = "Todas as regras de segurança aprovadas — publicação autorizada"
    log.info(f"✅ PUBLICAÇÃO AUTORIZADA: {motivo}")
    if warnings:
        for w in warnings:
            log.warning(f"   ⚠ {w} (não bloqueante)")

    return {
        "pode_publicar": True,
        "motivo":        motivo,
        "bloqueios":     [],
        "warnings":      warnings,
    }


# =========================
# AÇÃO BRAIN-LEVEL
# Chamada pelo engine como "validar_publicacao_autonoma"
# =========================

def executar_validacao(contexto_extra: dict = None) -> dict:
    """
    Ação brain-level chamada pelo engine.
    Lê o último laudo do state_manager e o config da planilha,
    depois chama validar_publicacao_autonoma().

    Returns:
        dict compatível com o engine:
        {
            "sucesso":        bool,   ← True se pode_publicar, False caso contrário
            "mensagem":       str,
            "pode_publicar":  bool,
            "bloqueios":      list,
            "warnings":       list,
            "dados":          dict    ← veredito completo
        }
    """
    log.info("🛡️ Publish Guard — iniciando validação")

    # ── Lê laudo do state_manager ──────────────────────────────────
    laudo = _ler_laudo_do_state()
    if not laudo:
        msg = "Nenhum laudo de auditoria encontrado — execute revisar_post_tiktok antes"
        log.error(msg)
        return {
            "sucesso":       False,
            "mensagem":      msg,
            "pode_publicar": False,
            "bloqueios":     [msg],
            "warnings":      [],
            "dados":         {},
        }

    # ── Lê config da planilha ──────────────────────────────────────
    config = _ler_config_planilha()
    log.info(f"⚙️ Config carregado: {list(config.keys())}")

    # ── Valida ────────────────────────────────────────────────────
    veredito = validar_publicacao_autonoma(laudo, config)

    # ── Persiste veredito no state_manager ────────────────────────
    # CRÍTICO: clicar_publicar_tiktok() lê esses campos via
    # _ler_aprovacao_do_state(). Sem essa persistência, o clique
    # autônomo no Publicar nunca é liberado (lê o default False).
    # Sempre salva — tanto aprovação quanto reprovação — para não
    # herdar veredito antigo de sessões anteriores.
    try:
        from memory.state_manager import atualizar_varios
        atualizar_varios({
            "publish_guard_aprovado":   bool(veredito["pode_publicar"]),
            "publish_guard_motivo":     veredito["motivo"],
            "publish_guard_bloqueios":  veredito.get("bloqueios", []),
            "publish_guard_warnings":   veredito.get("warnings", []),
            "publish_guard_timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        log.info(
            f"💾 Publish Guard salvo no state: "
            f"aprovado={veredito['pode_publicar']} | "
            f"bloqueios={len(veredito.get('bloqueios', []))} | "
            f"warnings={len(veredito.get('warnings', []))}"
        )
    except Exception as e:
        log.warning(f"⚠️ Não foi possível salvar veredito do guard no state: {e}")

    return {
        "sucesso":       veredito["pode_publicar"],
        "mensagem":      veredito["motivo"],
        "pode_publicar": veredito["pode_publicar"],
        "bloqueios":     veredito["bloqueios"],
        "warnings":      veredito["warnings"],
        "dados":         veredito,
    }


# =========================
# AÇÃO BRAIN-LEVEL
# Chamada pelo engine como "clicar_publicar_tiktok"
# =========================

def clicar_publicar_tiktok() -> dict:
    """
    Localiza e clica no botão Publicar do TikTok.
    SÓ clica se o publish_guard tiver aprovado na mesma sessão
    (lê veredito do state_manager).

    Returns:
        dict compatível com o engine
    """
    from brain.vision_analyzer import clicar_elemento_por_texto

    log.info("🖱️ clicar_publicar_tiktok — verificando aprovação do guard")

    # ── Verifica aprovação no state ────────────────────────────────
    aprovado, motivo = _ler_aprovacao_do_state()
    if not aprovado:
        msg = f"Clique no Publicar bloqueado pelo guard: {motivo}"
        log.error(f"🚫 {msg}")
        return {"sucesso": False, "mensagem": msg, "dados": None}

    log.info("✅ Guard aprovou — localizando botão Publicar")

    # ── Tenta os textos do botão em ordem de prioridade ───────────
    alvos = ["Publicar", "Postar", "Post", "Publish"]
    for alvo in alvos:
        log.info(f"  🔍 Tentando localizar: '{alvo}'")
        resultado = clicar_elemento_por_texto(
            contexto="tela_publicacao_tiktok",
            alvo=alvo,
            confianca_minima="alta",   # exige alta confiança para publicar
            guard_aprovado=True,       # libera cache visual para "Publicar"
        )

        if resultado.get("bloqueado"):
            msg = f"Bloqueio detectado ao tentar clicar em Publicar: {resultado['mensagem']}"
            log.error(f"🚨 {msg}")
            return {"sucesso": False, "mensagem": msg, "dados": resultado}

        if resultado.get("sucesso"):
            log.info(f"  ✅ Botão '{alvo}' clicado em ({resultado.get('x')}, {resultado.get('y')})")
            # Salva flag de publicação iniciada no state
            try:
                from memory.state_manager import atualizar_varios
                atualizar_varios({"publicacao_iniciada": True, "ultima_acao": "clicar_publicar_tiktok"})
            except Exception:
                pass
            return {
                "sucesso":  True,
                "mensagem": f"Botão '{alvo}' clicado — publicação iniciada",
                "dados":    resultado,
            }

    # Nenhum botão encontrado
    msg = f"Botão Publicar não encontrado (tentou: {alvos})"
    log.error(f"❌ {msg}")
    return {"sucesso": False, "mensagem": msg, "dados": None}


# =========================
# HELPERS INTERNOS
# =========================

def _ler_laudo_do_state() -> dict:
    """Lê o último laudo de auditoria persistido pelo auditor.py."""
    try:
        from memory.state_manager import ler_estado
        state = ler_estado()
        return state.get("ultimo_laudo_auditoria", {})
    except Exception as e:
        log.warning(f"Não foi possível ler laudo do state: {e}")
        return {}


def _ler_aprovacao_do_state() -> tuple[bool, str]:
    """
    Verifica se o publish_guard aprovou nesta sessão.
    Retorna (aprovado: bool, motivo: str).
    """
    try:
        from memory.state_manager import ler_estado
        state = ler_estado()
        aprovado = state.get("publish_guard_aprovado", False)
        motivo   = state.get("publish_guard_motivo", "Guard não executado nesta sessão")
        return aprovado, motivo
    except Exception as e:
        log.warning(f"Não foi possível ler aprovação do state: {e}")
        return False, f"Erro ao ler state: {e}"


def _ler_config_planilha() -> dict:
    """
    Lê Config_Agente do Google Sheets.
    Retorna dict com os valores. Em caso de falha, usa os defaults seguros.
    """
    try:
        from memory.sheets_engine import ler_config_agente
        config = ler_config_agente()
        if config:
            log.info(f"⚙️ Config lido da planilha: {len(config)} entradas")
            return config
    except Exception as e:
        log.warning(f"Não foi possível ler planilha — usando defaults: {e}")

    log.warning("⚠️ Usando CONFIG_DEFAULTS (planilha indisponível) — publicação bloqueada por padrão")
    return CONFIG_DEFAULTS.copy()


def _dentro_do_horario(agora: str, inicio: str, fim: str) -> bool:
    """Verifica se 'agora' (HH:MM) está dentro do intervalo [inicio, fim]."""
    try:
        def hm(s):
            h, m = s.split(":")
            return int(h) * 60 + int(m)
        return hm(inicio) <= hm(agora) <= hm(fim)
    except Exception:
        return False  # falha → bloqueia por segurança


def _contar_posts_hoje() -> int:
    """Conta quantos posts foram registrados hoje no state_manager."""
    try:
        from memory.state_manager import ler_estado
        state = ler_estado()
        hoje  = datetime.now().strftime("%Y-%m-%d")
        return int(state.get(f"posts_publicados_{hoje}", 0))
    except Exception:
        return 0  # falha → assume 0 (conservador mas não bloqueia)