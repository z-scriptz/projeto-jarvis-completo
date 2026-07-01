# agents/autonomous_orchestrator.py
# Orquestrador autônomo do AgenteIA (Jarvis)
#
# Conecta automaticamente:
#   1. Pipeline de planejamento (classifier → agent → planner)
#   2. Verificação de pré-requisitos (vídeo existe?)
#   3. Workflow de preparação do post (upload + detalhes + auditoria)
#   4. Verificação de permissão na Config_Agente
#   5. Workflow de publicação segura (guard + clique em Publicar)
#
# Filosofia: cada etapa é resiliente — falha de uma não derruba o todo,
# mas determina onde a pipeline para com clareza.
#
# Status finais possíveis (na planilha + no estado interno):
#   - "Planejado"            → planejamento OK (já é setado pelo pipeline_planejar)
#   - "Aguardando_Video"     → planejado mas sem arquivo de vídeo no disco
#   - "Preparado"            → upload + detalhes + auditoria OK, aguardando aprovação
#   - "Postado"              → publicado autonomamente com sucesso
#   - "Erro"                 → falhou em alguma etapa (motivo salvo no campo Erro)
#
# Uso:
#   from agents.autonomous_orchestrator import executar_pipeline_autonoma
#   resultado = executar_pipeline_autonoma()
#
# Teste via terminal:
#   python -m agents.autonomous_orchestrator

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

from shared.logger import get_logger
from shared.path_utils import windows_to_wsl_path

log = get_logger(__name__)

PLANS_DIR = Path(__file__).parent.parent / "shared" / "content_plans"

# Nome dos workflows usados pelo orquestrador
WORKFLOW_PREPARAR  = "preparar_post_tiktok_completo"
WORKFLOW_PUBLICAR  = "publicar_tiktok_seguro"

# Chave da Config_Agente que libera publicação autônoma
CHAVE_MODO_AUTONOMO = "modo_autonomo_publicacao"


# =================================================================
# HELPERS
# =================================================================

def _converter_plano_para_contexto(plano: dict, produto: dict) -> dict:
    """
    Converte o plano do content_planner + dados do produto em um contexto
    compatível com os workflows JSON (preparar_post_tiktok_completo etc).

    Os workflows substituem {legenda}, {hashtags}, {video_path} etc no
    momento da execução, então as chaves precisam bater.

    Args:
        plano:   dict retornado por gerar_plano_conteudo()
        produto: dict retornado por selecionar_produto_para_conteudo()

    Returns:
        dict com chaves prontas pra cascatear nos workflows.
    """
    video_path = plano.get("video_path_sugerido") or _fallback_video_path(produto)

    return {
        # Chaves usadas pelos workflows JSON ({video_path}, {legenda}, {hashtags})
        "video_path": video_path,
        "legenda":    plano.get("legenda", "") or "",
        "hashtags":   plano.get("hashtags", "") or "",

        # Chaves de contexto adicional (não substituídas mas úteis em logs)
        "produto":    produto.get("produto", ""),
        "nicho":      produto.get("nicho", ""),
        "plataforma": produto.get("plataforma", "TikTok"),
        "cta":        plano.get("cta", "") or "",
        "roteiro":    plano.get("roteiro", "") or "",
        "hook":       plano.get("hook", "") or "",
    }


def _fallback_video_path(produto: dict) -> str:
    """Gera path padrão de vídeo caso o plano não tenha sugerido."""
    nome = (produto.get("produto") or "video_teste").lower()
    nome = re.sub(r"[^\w\s-]", "", nome)
    nome = re.sub(r"\s+", "_", nome).strip("_")
    return f"C:\\AgenteIA\\videos\\{nome}.mp4"


def _video_existe(video_path_windows: str) -> bool:
    """
    Verifica se o arquivo de vídeo existe em disco.

    Detecta o SO em runtime:
      - Windows nativo: usa o caminho como está (C:\\...)
      - WSL/Linux:      converte para /mnt/c/... antes de checar

    Sem essa detecção, rodar o orquestrador no Windows quebrava porque
    o path convertido /mnt/c/... não existe no Windows nativo.
    """
    if not video_path_windows:
        return False
    try:
        if os.name == "nt":
            # Windows nativo — usa o caminho diretamente
            path_check = Path(video_path_windows)
        else:
            # WSL / Linux — precisa converter C:\... → /mnt/c/...
            path_check = Path(windows_to_wsl_path(video_path_windows))

        existe = path_check.exists()
        log.debug(f"  📁 Vídeo {'existe' if existe else 'NÃO existe'}: {path_check}")
        return existe
    except Exception as e:
        log.warning(f"  ⚠️ Erro ao verificar vídeo: {e}")
        return False


def _renderizar_video_via_creative_engine() -> dict:
    """
    Chama o Creative Engine para gerar o vídeo a partir do último plano.

    Returns:
        {
            "sucesso":        bool,
            "video_path":     str | None,
            "provider_usado": str,
            "mensagem":       str,
            "tentou":         bool,
        }

    Em caso de falha de import (Creative Engine não instalado), retorna
    sucesso=False sem quebrar o orquestrador.
    """
    try:
        from creative_engine.asset_router import gerar_assets_para_plano
    except ImportError as e:
        msg = f"Creative Engine não disponível: {e}"
        log.warning(f"  ⚠️ {msg}")
        return {
            "sucesso":        False,
            "video_path":     None,
            "provider_usado": "nenhum",
            "mensagem":       msg,
            "tentou":         False,
        }

    try:
        resultado_assets = gerar_assets_para_plano()
        return {
            "sucesso":        resultado_assets.get("sucesso", False),
            "video_path":     resultado_assets.get("video_path"),
            "provider_usado": resultado_assets.get("provider_usado", ""),
            "mensagem":       resultado_assets.get("mensagem", ""),
            "tentou":         True,
        }
    except Exception as e:
        msg = f"Exceção ao chamar Creative Engine: {e}"
        log.error(f"  ❌ {msg}")
        return {
            "sucesso":        False,
            "video_path":     None,
            "provider_usado": "erro",
            "mensagem":       msg,
            "tentou":         True,
        }



def _publicacao_autorizada_pelo_config() -> tuple[bool, str]:
    """
    Lê Config_Agente e verifica se modo_autonomo_publicacao=true.
    Retorna (permitido: bool, motivo: str).

    Em caso de falha de leitura, assume NÃO autorizado (conservador).
    """
    try:
        from memory.sheets_engine import ler_config_agente
        config = ler_config_agente()
        valor  = str(config.get(CHAVE_MODO_AUTONOMO, "false")).lower().strip()
        if valor == "true":
            return True, f"{CHAVE_MODO_AUTONOMO}=true (publicação autorizada)"
        return False, f"{CHAVE_MODO_AUTONOMO}={valor} (publicação NÃO autorizada)"
    except Exception as e:
        return False, f"erro ao ler Config_Agente: {e}"


def _atualizar_status_planilha(linha: Optional[int], status: str, erro: str = "") -> bool:
    """
    Atualiza status (e opcionalmente erro) numa linha da planilha.
    Falha silenciosa — não quebra o pipeline se a planilha estiver indisponível.
    """
    if not linha:
        log.debug("Sem linha_planilha — pulando atualização de status")
        return False
    try:
        from memory.sheets_engine import atualizar_status, registrar_erro
        if status == "Erro" and erro:
            registrar_erro(linha, erro)
        else:
            atualizar_status(linha, status)
        log.info(f"  📊 Planilha linha {linha} → {status}")
        return True
    except Exception as e:
        log.warning(f"  ⚠️ Falha ao atualizar planilha (linha {linha}, status {status}): {e}")
        return False


def _atualizar_state_orquestrador(
    produto: dict,
    status_final: str,
    sucesso: bool,
    motivo: str,
):
    """Persiste resultado do orquestrador no state_manager."""
    try:
        from memory.state_manager import atualizar_varios

        # Estado base
        if status_final == "Aguardando_Quota":
            estado_atual = "aguardando_quota"
        elif sucesso:
            estado_atual = "orquestrador_concluido"
        else:
            estado_atual = "orquestrador_falhou"

        update = {
            "produto_atual":    produto.get("produto", ""),
            "plataforma_atual": produto.get("plataforma", "TikTok"),
            "estado_atual":     estado_atual,
            "etapa_atual":      status_final,
            "ultimo_resultado_orquestrador": {
                "sucesso":      sucesso,
                "status_final": status_final,
                "motivo":       motivo,
                "timestamp":    time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        }

        # Flags específicas de quota — só seta quando o status é Aguardando_Quota,
        # pra não poluir o state em execuções normais.
        if status_final == "Aguardando_Quota":
            update["gemini_quota_bloqueada"]    = True
            update["gemini_quota_ultimo_erro"]  = time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            # Reseta quando uma execução posterior NÃO falhou por quota —
            # significa que a cota voltou.
            update["gemini_quota_bloqueada"]    = False

        atualizar_varios(update)
        log.debug(f"💾 State atualizado: estado_atual={estado_atual} | etapa={status_final}")
    except Exception as e:
        log.warning(f"⚠️ Não foi possível atualizar state: {e}")


def _salvar_resultado(resultado: dict) -> Optional[Path]:
    """Salva resultado completo em shared/content_plans/orchestrator_resultado.json."""
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        caminho = PLANS_DIR / "orchestrator_resultado.json"
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2, default=str)
        log.info(f"💾 Resultado salvo: {caminho}")
        return caminho
    except Exception as e:
        log.warning(f"⚠️ Falha ao salvar resultado: {e}")
        return None


def _eh_falha_por_quota(wf_resultado: dict) -> tuple[bool, str]:
    """
    Detecta se um workflow falhou especificamente por quota Gemini exaurida.

    Procura pistas em:
      - resultados[].mensagem (mensagem direta do passo)
      - resultados[].dados.etapa_falha (caso file_dialog_uploader propagou)
      - resultados[].dados.mensagem (mensagem do uploader)

    Returns:
        (eh_quota, motivo_para_log)
    """
    PISTAS = (
        "quota_excedida",
        "quota_gemini",
        "gemini sem quota",
        "resource_exhausted",
        "quota excedida",
    )

    resultados = wf_resultado.get("resultados") or []
    for r in resultados:
        # Pista 1: mensagem direta do passo
        msg = (r.get("mensagem") or "").lower()
        if any(p in msg for p in PISTAS):
            return True, r.get("mensagem", "")

        # Pista 2: campos profundos quando o workflow chamou uma ação brain
        # (ex.: selecionar_arquivo_upload_tiktok com etapa_falha="quota_gemini")
        dados = r.get("dados") or {}
        if isinstance(dados, dict):
            etapa_falha = (dados.get("etapa_falha") or "").lower()
            if etapa_falha in ("quota_gemini", "quota_excedida"):
                return True, dados.get("mensagem", "Quota Gemini esgotada")
            msg_dados = (dados.get("mensagem") or "").lower()
            if any(p in msg_dados for p in PISTAS):
                return True, dados.get("mensagem", "")

    return False, ""


# =================================================================
# REGISTRO NO PERFORMANCE AGENT
# =================================================================

# Set em memória pra evitar duplicar registro do mesmo (produto, video_path)
# dentro de uma mesma sessão Python. Protege contra dupla chamada acidental
# (ex.: operador relança o orquestrador no mesmo produto enquanto a aba já
# tem a entrada). Reseta quando o processo Python é reiniciado, o que é o
# comportamento correto — sessão nova pode re-registrar se for outra rodada.
_REGISTROS_PERFORMANCE_SESSAO: set = set()

# Status que justificam um registro em Performance_Posts. Outros status
# (Aguardando_*, Erro_*, Planejado, etc.) NÃO geram linha — o post não
# chegou a ser preparado/publicado de fato.
_STATUS_REGISTRAVEIS = {"Preparado", "Postado"}


def _registrar_no_performance_se_aplicavel(
    resultado: dict,
    status_final: str,
) -> dict:
    """
    Decide e executa o registro do post na aba Performance_Posts.

    Não interrompe o fluxo do orquestrador se algo falhar — captura qualquer
    erro e devolve estrutura consistente pro resultado["performance_registro"].

    Args:
        resultado:    dict do orquestrador (tem produto, plano, contexto_workflow)
        status_final: status já decidido pelo _finalizar

    Returns:
        dict pra colocar em resultado["performance_registro"]:
            {"executou": bool, "sucesso": bool, ...}
    """
    # ── 1. Filtro de status ───────────────────────────────────────
    if status_final not in _STATUS_REGISTRAVEIS:
        return {
            "executou": False,
            "motivo":   f"status_final={status_final} não exige registro em Performance_Posts",
        }

    # ── 2. Extrai dados (todos opcionais — defaults seguros) ─────
    produto_dict = resultado.get("produto") or {}
    plano_dict   = resultado.get("plano") or {}
    ctx_wf       = resultado.get("contexto_workflow") or {}

    produto_nome = (produto_dict.get("produto") or "").strip()
    video_path   = (ctx_wf.get("video_path") or "").strip()

    # ── 3. Dedup na sessão ────────────────────────────────────────
    # Chave usa produto+video_path porque o mesmo produto pode ter
    # vídeos diferentes (re-renderizado). Vazio em ambos = sem identidade
    # válida, então skipa o registro.
    if not produto_nome:
        return {
            "executou": False,
            "motivo":   "Sem nome de produto no resultado — pulando registro",
        }

    chave_dedup = (produto_nome.lower(), video_path.lower())
    if chave_dedup in _REGISTROS_PERFORMANCE_SESSAO:
        log.info(
            f"  ⏭️  Pulando registro em Performance_Posts: "
            f"'{produto_nome}' já registrado nesta sessão"
        )
        return {
            "executou": False,
            "motivo":   f"Já registrado nesta sessão: '{produto_nome}'",
        }

    # ── 4. Monta post_info no formato esperado ────────────────────
    post_info = {
        "produto":         produto_nome,
        "nicho":           produto_dict.get("nicho", ""),
        "plataforma":      produto_dict.get("plataforma", "TikTok"),
        "hook":            plano_dict.get("hook", ""),
        "legenda":         plano_dict.get("legenda", ""),
        "hashtags":        plano_dict.get("hashtags", ""),
        "video_path":      video_path,
        "status_postagem": status_final,
    }

    # ── 5. Chama o Performance Agent — protegido contra qualquer falha ──
    log.info(f"📊 Registrando em Performance_Posts: '{produto_nome[:40]}' (status={status_final})")
    try:
        from agents.performance_agent import registrar_post_planejado_no_performance
        reg = registrar_post_planejado_no_performance(post_info)

        # Marca dedup só APÓS sucesso/tentativa real — assim se a planilha
        # estava temporariamente offline e foi pro fallback, uma re-execução
        # na mesma sessão tenta de novo (o agent tem dedup interno em fallback).
        _REGISTROS_PERFORMANCE_SESSAO.add(chave_dedup)

        return {
            "executou": True,
            "sucesso":  reg.get("sucesso", False),
            "fonte":    reg.get("fonte"),
            "mensagem": reg.get("mensagem"),
        }
    except Exception as e:
        log.warning(f"⚠️ Falha ao registrar em Performance_Posts: {e}")
        return {
            "executou": True,
            "sucesso":  False,
            "erro":     str(e),
        }


def _finalizar(resultado: dict, status_final: str, motivo: str, sucesso: bool) -> dict:
    """Centraliza o encerramento — atualiza state, planilha e salva resultado."""
    resultado["status_final"]  = status_final
    resultado["motivo_final"]  = motivo
    resultado["sucesso"]       = sucesso
    resultado["timestamp_fim"] = time.strftime("%Y-%m-%d %H:%M:%S")

    # Atualiza planilha conforme o status final
    linha = resultado.get("linha_planilha")
    if linha:
        if status_final == "Postado":
            _atualizar_status_planilha(linha, "Postado")
        elif status_final == "Preparado":
            _atualizar_status_planilha(linha, "Preparado")
        elif status_final == "Aguardando_Video":
            _atualizar_status_planilha(linha, "Aguardando_Video")
        elif status_final == "Aguardando_Quota":
            # Não marca Erro na planilha — quota é condição temporária, não falha.
            # Mantém o status atual (geralmente Planejado/Preparado) e só registra
            # observação para o operador saber por que a execução parou.
            try:
                from memory.sheets_engine import registrar_erro
                registrar_erro(linha, f"Aguardando renovação de quota Gemini: {motivo}")
            except Exception as e:
                log.debug(f"Não foi possível registrar observação de quota na planilha: {e}")
        elif status_final.startswith("Erro"):
            _atualizar_status_planilha(linha, "Erro", motivo)
        # "Planejado" já foi setado pelo próprio pipeline de planejamento — não sobrescreve

    _atualizar_state_orquestrador(resultado.get("produto", {}), status_final, sucesso, motivo)

    # ── Registro no Performance Agent (ciclo de aprendizado) ──
    # Só registra em status Preparado/Postado. Não bloqueia o orquestrador
    # se a aba estiver indisponível — o agent tem fallback local próprio.
    resultado["performance_registro"] = _registrar_no_performance_se_aplicavel(
        resultado, status_final
    )

    _salvar_resultado(resultado)

    return resultado


# =================================================================
# PIPELINE PRINCIPAL
# =================================================================

def executar_pipeline_autonoma() -> dict:
    """
    Pipeline autônoma completa: planeja → prepara → publica (se permitido).

    Retorna:
        {
            "sucesso":           bool,
            "timestamp_inicio":  str,
            "timestamp_fim":     str,
            "produto":           dict,
            "plano":             dict,
            "classificacao":     dict,
            "linha_planilha":    int | None,
            "contexto_workflow": dict,
            "etapas":            dict   ← detalhes de cada etapa
            "status_final":      str    ← Postado | Preparado | Aguardando_* | Erro_*
            "motivo_final":      str,
        }
    """
    log.info("═" * 60)
    log.info("🤖 ORQUESTRADOR AUTÔNOMO — Iniciando")
    log.info("═" * 60)

    resultado: dict = {
        "sucesso":           False,
        "timestamp_inicio":  time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp_fim":     "",
        "produto":           {},
        "plano":              {},
        "classificacao":     {},
        "linha_planilha":    None,
        "contexto_workflow": {},
        "etapas": {
            "planejamento":         {"executou": False, "sucesso": False, "mensagem": ""},
            "verificacao_video":    {"executou": False, "video_existe": False, "video_path": "",
                                     "renderizou": False, "render_provider": "", "render_mensagem": ""},
            "preparar_post":        {"executou": False, "sucesso": False,
                                     "passos_ok": 0, "passos_total": 0, "passo_falhou": None},
            "permissao_publicacao": {"executou": False, "permitido": False, "motivo": ""},
            "publicacao":           {"executou": False, "sucesso": False,
                                     "passos_ok": 0, "passos_total": 0, "passo_falhou": None},
        },
        "status_final": "",
        "motivo_final": "",
    }

    # ═══════════════════════════════════════════════════════════════
    # ETAPA 1 — PLANEJAMENTO (classifier → agent → planner)
    # ═══════════════════════════════════════════════════════════════
    log.info("\n📌 ETAPA 1/5 — Pipeline de Planejamento")
    try:
        from agents.pipeline_planejar_conteudo import executar_pipeline_planejamento
        plan = executar_pipeline_planejamento()

        resultado["produto"]         = plan.get("produto", {})
        resultado["plano"]           = plan.get("plano", {})
        resultado["classificacao"]   = plan.get("classificacao", {})
        resultado["linha_planilha"]  = plan.get("linha_planilha")
        resultado["etapas"]["planejamento"] = {
            "executou":    True,
            "sucesso":     plan.get("sucesso", False),
            "mensagem":    plan.get("status_final", ""),
            "fonte_plano": plan.get("fonte_plano", ""),
        }

        if not plan.get("sucesso") or not resultado["produto"].get("produto"):
            return _finalizar(
                resultado,
                status_final="Erro_Planejamento",
                motivo=f"Planejamento falhou: {plan.get('status_final', 'sem produto')}",
                sucesso=False,
            )

        log.info(
            f"  ✅ Planejado: '{resultado['produto'].get('produto')}' "
            f"(plano via {plan.get('fonte_plano')})"
        )
    except Exception as e:
        log.error(f"  ❌ Exceção no planejamento: {e}")
        resultado["etapas"]["planejamento"] = {
            "executou": True, "sucesso": False, "mensagem": str(e)
        }
        return _finalizar(resultado, "Erro_Planejamento", f"Exceção: {e}", sucesso=False)

    # ═══════════════════════════════════════════════════════════════
    # ETAPA 2 — MONTAR CONTEXTO PARA WORKFLOWS
    # ═══════════════════════════════════════════════════════════════
    log.info("\n📌 ETAPA 2/5 — Montar contexto para workflows")
    try:
        contexto = _converter_plano_para_contexto(resultado["plano"], resultado["produto"])
        resultado["contexto_workflow"] = contexto

        log.info("  📦 Contexto preparado:")
        for k, v in contexto.items():
            log.info(f"     {k}: {str(v)[:70]}")
    except Exception as e:
        log.error(f"  ❌ Falha ao montar contexto: {e}")
        return _finalizar(resultado, "Erro_Contexto", f"Falha ao montar contexto: {e}", sucesso=False)

    # ═══════════════════════════════════════════════════════════════
    # ETAPA 3 — VERIFICAR SE O VÍDEO EXISTE EM DISCO
    #          → se não existir, chama Creative Engine para renderizar
    # ═══════════════════════════════════════════════════════════════
    log.info("\n📌 ETAPA 3/5 — Verificar arquivo de vídeo")
    video_path = contexto.get("video_path", "")
    video_existe = _video_existe(video_path)

    resultado["etapas"]["verificacao_video"] = {
        "executou":          True,
        "video_existe":      video_existe,
        "video_existia":     video_existe,    # estado original (antes de renderizar)
        "video_path":        video_path,
        "renderizou":        False,
        "render_provider":   "",
        "render_mensagem":   "",
    }

    if not video_existe:
        log.info(f"  📭 Vídeo não encontrado: {video_path}")
        log.info(f"  🎬 Chamando Creative Engine para renderizar...")

        render = _renderizar_video_via_creative_engine()

        resultado["etapas"]["verificacao_video"].update({
            "renderizou":      render["tentou"] and render["sucesso"],
            "render_provider": render["provider_usado"],
            "render_mensagem": render["mensagem"],
        })

        if not render["sucesso"]:
            # Creative Engine falhou ou não está disponível — para com Aguardando_Video
            log.warning(f"  ⚠️ Creative Engine não conseguiu renderizar: {render['mensagem']}")
            return _finalizar(
                resultado,
                status_final="Aguardando_Video",
                motivo=f"Vídeo não pôde ser renderizado: {render['mensagem']}",
                sucesso=True,   # planejamento OK, só falta resolver renderização
            )

        # Se Creative Engine devolveu outro path (ex.: video_auto_*.mp4),
        # atualiza o contexto pra workflow usar o caminho certo
        video_path_renderizado = render.get("video_path") or video_path
        if video_path_renderizado != video_path:
            log.info(f"  🔁 Path atualizado: {video_path} → {video_path_renderizado}")
            video_path = video_path_renderizado
            contexto["video_path"] = video_path
            resultado["contexto_workflow"]["video_path"] = video_path

        # Reconfirma que o arquivo existe agora (sanity check pós-render)
        if not _video_existe(video_path):
            return _finalizar(
                resultado,
                status_final="Aguardando_Video",
                motivo=f"Creative Engine reportou sucesso mas arquivo não está em disco: {video_path}",
                sucesso=False,
            )

        resultado["etapas"]["verificacao_video"]["video_existe"] = True
        resultado["etapas"]["verificacao_video"]["video_path"]   = video_path
        log.info(
            f"  ✅ Vídeo renderizado por '{render['provider_usado']}': {video_path}"
        )
    else:
        log.info(f"  ✅ Vídeo encontrado (já existia): {video_path}")


    # ═══════════════════════════════════════════════════════════════
    # ETAPA 4 — WORKFLOW preparar_post_tiktok_completo
    # ═══════════════════════════════════════════════════════════════
    log.info(f"\n📌 ETAPA 4/5 — Workflow '{WORKFLOW_PREPARAR}'")
    try:
        from workflows.engine import executar_workflow
        wf_prep = executar_workflow(WORKFLOW_PREPARAR, contexto=contexto)

        resultado["etapas"]["preparar_post"] = {
            "executou":     True,
            "sucesso":      wf_prep.get("sucesso", False),
            "passos_ok":    wf_prep.get("passos_ok", 0),
            "passos_total": wf_prep.get("passos_total", 0),
            "passo_falhou": wf_prep.get("passo_falhou"),
        }

        if not wf_prep.get("sucesso"):
            # PRIMEIRA CHECAGEM: foi falha por quota? Não é erro do Jarvis
            # nem do TikTok — é condição temporária. Status especial.
            eh_quota, motivo_quota = _eh_falha_por_quota(wf_prep)
            if eh_quota:
                motivo = (
                    f"Gemini sem quota durante preparação do post: {motivo_quota}. "
                    f"Nenhuma alteração foi feita no TikTok. "
                    f"Tente novamente quando a cota renovar."
                )
                log.warning(f"  ⏸️  {motivo}")
                return _finalizar(resultado, "Aguardando_Quota", motivo, sucesso=False)

            motivo = (
                f"Workflow '{WORKFLOW_PREPARAR}' falhou em "
                f"'{wf_prep.get('passo_falhou')}' "
                f"({wf_prep.get('passos_ok')}/{wf_prep.get('passos_total')} passos OK)"
            )
            log.error(f"  ❌ {motivo}")
            return _finalizar(resultado, "Erro_Preparacao", motivo, sucesso=False)

        log.info(
            f"  ✅ Post preparado: {wf_prep.get('passos_ok')}/"
            f"{wf_prep.get('passos_total')} passos"
        )
    except Exception as e:
        # Mesmo numa exceção, tenta detectar se foi quota
        msg_exc = str(e).lower()
        if any(p in msg_exc for p in ("quota_excedida", "resource_exhausted", "quota excedida", "quota_gemini")):
            log.warning(f"  ⏸️  Exceção identificada como quota Gemini: {e}")
            resultado["etapas"]["preparar_post"] = {
                "executou": True, "sucesso": False, "mensagem": str(e)
            }
            return _finalizar(
                resultado,
                "Aguardando_Quota",
                f"Exceção de quota durante preparação: {e}",
                sucesso=False,
            )

        log.error(f"  ❌ Exceção em preparar_post: {e}")
        resultado["etapas"]["preparar_post"] = {
            "executou": True, "sucesso": False, "mensagem": str(e)
        }
        return _finalizar(resultado, "Erro_Preparacao", f"Exceção: {e}", sucesso=False)

    # ═══════════════════════════════════════════════════════════════
    # ETAPA 5 — VERIFICAR PERMISSÃO DE PUBLICAÇÃO
    # ═══════════════════════════════════════════════════════════════
    log.info("\n📌 ETAPA 5/5 — Permissão de publicação autônoma")
    permitido, motivo_perm = _publicacao_autorizada_pelo_config()
    resultado["etapas"]["permissao_publicacao"] = {
        "executou":  True,
        "permitido": permitido,
        "motivo":    motivo_perm,
    }
    log.info(f"  🛡️ {motivo_perm}")

    if not permitido:
        # Tudo certo até aqui — só precisa de aprovação humana
        return _finalizar(
            resultado,
            status_final="Preparado",
            motivo=f"Post preparado, aguardando aprovação humana ({motivo_perm})",
            sucesso=True,
        )

    # ═══════════════════════════════════════════════════════════════
    # ETAPA 6 (condicional) — WORKFLOW publicar_tiktok_seguro
    # ═══════════════════════════════════════════════════════════════
    log.info(f"\n📌 ETAPA 6 — Workflow '{WORKFLOW_PUBLICAR}'")
    try:
        from workflows.engine import executar_workflow
        wf_pub = executar_workflow(WORKFLOW_PUBLICAR, contexto=contexto)

        resultado["etapas"]["publicacao"] = {
            "executou":     True,
            "sucesso":      wf_pub.get("sucesso", False),
            "passos_ok":    wf_pub.get("passos_ok", 0),
            "passos_total": wf_pub.get("passos_total", 0),
            "passo_falhou": wf_pub.get("passo_falhou"),
        }

        if wf_pub.get("sucesso"):
            log.info(
                f"  🎉 Publicação concluída: {wf_pub.get('passos_ok')}/"
                f"{wf_pub.get('passos_total')} passos"
            )
            return _finalizar(
                resultado,
                status_final="Postado",
                motivo="Publicado autonomamente com sucesso",
                sucesso=True,
            )

        motivo = (
            f"Workflow '{WORKFLOW_PUBLICAR}' falhou em "
            f"'{wf_pub.get('passo_falhou')}' "
            f"({wf_pub.get('passos_ok')}/{wf_pub.get('passos_total')} passos OK)"
        )
        log.warning(f"  ⚠️ {motivo}")
        return _finalizar(resultado, "Erro_Publicacao", motivo, sucesso=False)

    except Exception as e:
        log.error(f"  ❌ Exceção em publicar: {e}")
        resultado["etapas"]["publicacao"] = {
            "executou": True, "sucesso": False, "mensagem": str(e)
        }
        return _finalizar(resultado, "Erro_Publicacao", f"Exceção: {e}", sucesso=False)


# =================================================================
# TESTE VIA TERMINAL
# =================================================================

def _print_secao(titulo: str):
    print(f"\n{'─' * 60}")
    print(f"  {titulo}")
    print(f"{'─' * 60}")


def _print_etapa(nome: str, dados: dict):
    if not dados.get("executou"):
        print(f"  ⏭️  {nome:<22} — não executada")
        return

    sucesso = dados.get("sucesso", False)
    icone   = "✅" if sucesso else "⚠️"

    if "passos_total" in dados and dados["passos_total"] > 0:
        extra = f" ({dados.get('passos_ok', 0)}/{dados['passos_total']} passos)"
        if dados.get("passo_falhou"):
            extra += f" — falhou em '{dados['passo_falhou']}'"
    elif "permitido" in dados:
        extra = f" — {dados.get('motivo', '')}"
    elif "video_existe" in dados:
        if dados.get("renderizou"):
            extra = f" — renderizado por '{dados.get('render_provider', '?')}'"
        elif dados.get("video_existia"):
            extra = " — vídeo já existia, reutilizado"
        elif dados["video_existe"]:
            extra = " — vídeo encontrado"
        else:
            extra = " — vídeo NÃO encontrado (sem renderização possível)"
    elif "mensagem" in dados:
        extra = f" — {dados.get('mensagem', '')[:60]}"
    else:
        extra = ""

    print(f"  {icone} {nome:<22}{extra}")


if __name__ == "__main__":
    print("=" * 60)
    print("  🤖 Orquestrador Autônomo — Teste")
    print("=" * 60)

    resultado = executar_pipeline_autonoma()

    produto = resultado.get("produto", {})
    plano   = resultado.get("plano", {})

    # ── Cabeçalho ─────────────────────────────────────────────
    _print_secao("📊 RESULTADO GERAL")
    print(f"  Status:  {'✅' if resultado['sucesso'] else '❌'} {resultado.get('status_final', '?')}")
    print(f"  Motivo:  {resultado.get('motivo_final', '?')}")
    print(f"  Início:  {resultado.get('timestamp_inicio', '?')}")
    print(f"  Fim:     {resultado.get('timestamp_fim', '?')}")

    # ── Produto e plano ───────────────────────────────────────
    _print_secao("📦 PRODUTO ESCOLHIDO")
    print(f"  Produto:       {produto.get('produto', '—')}")
    print(f"  Nicho:         {produto.get('nicho', '—')}")
    print(f"  Plataforma:    {produto.get('plataforma', '—')}")
    print(f"  Linha planilha:{resultado.get('linha_planilha', '—')}")
    print(f"  Fonte plano:   {resultado.get('etapas', {}).get('planejamento', {}).get('fonte_plano', '—')}")

    if plano:
        _print_secao("🎬 CONTEÚDO PLANEJADO")
        hook = (plano.get("hook") or "")[:70]
        leg  = (plano.get("legenda") or "")[:70]
        ht   = (plano.get("hashtags") or "")[:70]
        cta  = (plano.get("cta") or "")[:70]
        vid  = plano.get("video_path_sugerido") or "—"
        print(f"  🎣 Hook:     {hook}")
        print(f"  📝 Legenda:  {leg}")
        print(f"  #️⃣  Hashtags:{ht}")
        print(f"  📢 CTA:      {cta}")
        print(f"  🎥 Vídeo:    {vid}")

    # ── Etapas ────────────────────────────────────────────────
    _print_secao("🔄 ETAPAS EXECUTADAS")
    etapas = resultado.get("etapas", {})
    _print_etapa("Planejamento",          etapas.get("planejamento", {}))
    _print_etapa("Verificação vídeo",     etapas.get("verificacao_video", {}))
    _print_etapa("Preparação do post",    etapas.get("preparar_post", {}))
    _print_etapa("Permissão publicação",  etapas.get("permissao_publicacao", {}))
    _print_etapa("Publicação",            etapas.get("publicacao", {}))

    # ── Interpretação ─────────────────────────────────────────
    _print_secao("💡 INTERPRETAÇÃO")
    status = resultado.get("status_final", "")
    msgs = {
        "Postado":             "🎉 Post publicado autonomamente com sucesso!",
        "Preparado":           "📋 Post preparado e auditado. Aguardando aprovação humana "
                               "(modo_autonomo_publicacao=false na planilha).",
        "Aguardando_Video":    "🎥 Planejamento OK, mas o Creative Engine não conseguiu renderizar o vídeo. "
                               "Verifique se MoviePy/Pillow estão instalados: pip install moviepy imageio-ffmpeg pillow",
        "Erro_Planejamento":   "❌ Planejamento falhou (verifique planilha e API Gemini).",
        "Erro_Contexto":       "❌ Falha ao montar contexto a partir do plano.",
        "Erro_Preparacao":     "❌ Workflow de preparação do post falhou (verifique screenshots em logs).",
        "Erro_Publicacao":     "❌ Workflow de publicação falhou (verifique guard + auditoria).",
    }
    print(f"  {msgs.get(status, 'Status desconhecido — inspecione o JSON salvo.')}")

    _print_secao("💾 ARQUIVOS")
    print(f"  Resultado completo: shared/content_plans/orchestrator_resultado.json")
    print(f"  Último plano:       shared/content_plans/ultimo_plano.json")
    print(f"  Produto:            shared/content_plans/produto_selecionado.json")

    print("=" * 60)