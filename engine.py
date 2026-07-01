# workflows/engine.py
# Workflow Engine do AgenteIA
#
# Transforma ações soltas em missões completas e reutilizáveis.
# Lê workflows de arquivos JSON, executa passo a passo,
# com retry por passo, parada em crítico e estado persistente.
#
# Uso em main.py:
#   from workflows.engine import executar_workflow
#   resultado = executar_workflow("postar_tiktok", contexto={"produto": "Cinto Modelador"})

import json
import time
from pathlib import Path
from typing import Optional

from brain.commander import enviar_comando
from memory.state_manager import registrar_etapa, atualizar_varios
from shared.logger import get_logger

log = get_logger(__name__)

WORKFLOWS_DIR = Path(__file__).parent

# Ações que executam no WSL via brain/ (não passam pelo executor Windows)
_ACOES_BRAIN = {
    "clicar_elemento_por_texto",
    "localizar_elemento_por_texto",
    "auditar_post_tiktok",
    "auditar_conteudo_tiktok",
    "auditar_botao_publicar_tiktok",
    "validar_publicacao_autonoma",
    "clicar_publicar_tiktok",
    "registrar_postagem_sheets",
    "selecionar_arquivo_upload_tiktok",
}

# Ações resolvidas pelo próprio engine (não vão pro executor nem pro brain)
_ACOES_ENGINE = {"executar_workflow"}


def _executar_acao_brain(acao: str, kwargs: dict) -> dict:
    from brain.vision_analyzer import (
        clicar_elemento_por_texto,
        localizar_elemento_por_texto,
    )

    if acao == "clicar_elemento_por_texto":
        contexto       = kwargs.get("contexto", "workflow_auto")
        alvo           = kwargs.get("alvo", "")
        conf_minima    = kwargs.get("confianca_minima", "media")
        usar_cache     = kwargs.get("usar_cache", True)
        resultado      = clicar_elemento_por_texto(
            contexto, alvo, conf_minima, usar_cache=usar_cache
        )

        if resultado.get("bloqueado"):
            return {"sucesso": False,
                    "mensagem": f"Bloqueio detectado: {resultado['mensagem']}",
                    "dados": resultado}
        return {
            "sucesso":  resultado.get("sucesso", False),
            "mensagem": resultado.get("mensagem", ""),
            "dados":    resultado,
        }

    if acao == "localizar_elemento_por_texto":
        contexto  = kwargs.get("contexto", "workflow_auto")
        alvo      = kwargs.get("alvo", "")
        resultado = localizar_elemento_por_texto(contexto, alvo)
        encontrado = resultado.get("encontrado", False)
        return {
            "sucesso":  encontrado,
            "mensagem": resultado.get("motivo", ""),
            "dados":    resultado,
        }

    if acao == "auditar_post_tiktok":
        from brain.auditor import auditar_post_tiktok
        contexto  = kwargs.get("contexto", "revisao_final_tiktok")
        resultado = auditar_post_tiktok(contexto=contexto)
        return {
            "sucesso":  resultado.get("sucesso", False),
            "mensagem": resultado.get("mensagem", ""),
            "dados":    resultado,
        }

    if acao == "auditar_conteudo_tiktok":
        from brain.auditor import auditar_conteudo_tiktok
        contexto  = kwargs.get("contexto", "auditoria_conteudo_tiktok")
        resultado = auditar_conteudo_tiktok(contexto=contexto)
        return {
            "sucesso":  resultado.get("sucesso", False),
            "mensagem": resultado.get("mensagem", ""),
            "dados":    resultado,
        }

    if acao == "auditar_botao_publicar_tiktok":
        from brain.auditor import auditar_botao_publicar_tiktok
        contexto  = kwargs.get("contexto", "auditoria_botao_publicar")
        resultado = auditar_botao_publicar_tiktok(contexto=contexto)
        return {
            "sucesso":  resultado.get("sucesso", False),
            "mensagem": resultado.get("mensagem", ""),
            "dados":    resultado,
        }

    if acao == "validar_publicacao_autonoma":
        from brain.publish_guard import executar_validacao
        resultado = executar_validacao()
        # Sempre persiste o veredito — mesmo False — para não herdar aprovação antiga
        try:
            from memory.state_manager import atualizar_varios
            atualizar_varios({
                "publish_guard_aprovado": resultado.get("pode_publicar", False),
                "publish_guard_motivo":   resultado.get("mensagem", ""),
            })
        except Exception:
            pass
        return {
            "sucesso":  resultado.get("sucesso", False),
            "mensagem": resultado.get("mensagem", ""),
            "dados":    resultado,
        }

    if acao == "clicar_publicar_tiktok":
        from brain.publish_guard import clicar_publicar_tiktok
        resultado = clicar_publicar_tiktok()
        return {
            "sucesso":  resultado.get("sucesso", False),
            "mensagem": resultado.get("mensagem", ""),
            "dados":    resultado,
        }

    if acao == "registrar_postagem_sheets":
        from memory.sheets_engine import registrar_postagem_sheets
        resultado = registrar_postagem_sheets()
        return {
            "sucesso":  resultado.get("sucesso", False),
            "mensagem": resultado.get("mensagem", ""),
            "dados":    resultado,
        }

    if acao == "selecionar_arquivo_upload_tiktok":
        from brain.file_dialog_uploader import selecionar_arquivo_upload_tiktok
        video_path = kwargs.get("video_path", "")
        if not video_path:
            return {
                "sucesso":  False,
                "mensagem": "Campo 'video_path' ausente — workflow precisa passar video_path para a ação selecionar_arquivo_upload_tiktok",
                "dados":    {"erro": "video_path_vazio"},
            }
        resultado = selecionar_arquivo_upload_tiktok(video_path)
        return {
            "sucesso":  resultado.get("sucesso", False),
            "mensagem": resultado.get("mensagem", ""),
            "dados":    resultado,
        }

    return {"sucesso": False, "mensagem": f"Ação brain desconhecida: {acao}", "dados": None}


def _executar_acao_engine(acao: str, kwargs: dict, contexto_pai: Optional[dict]) -> dict:
    """
    Executa ações resolvidas pelo próprio engine — sem passar pelo executor
    Windows nem pelo brain. Atualmente suporta apenas 'executar_workflow'.

    O contexto do workflow pai é repassado integralmente para o filho,
    permitindo que {video_path}, {legenda}, {hashtags} etc. funcionem
    em todos os níveis da cadeia.
    """
    if acao == "executar_workflow":
        nome_filho = kwargs.get("workflow", "")
        if not nome_filho:
            return {"sucesso": False, "mensagem": "Campo 'workflow' ausente no passo", "dados": None}

        log.info(f"  🔗 Workflow filho iniciado: '{nome_filho}'")
        resultado_filho = executar_workflow(nome_filho, contexto=contexto_pai)

        if resultado_filho["sucesso"]:
            log.info(
                f"  🔗 Workflow filho concluído: '{nome_filho}' — "
                f"{resultado_filho['passos_ok']}/{resultado_filho['passos_total']} passos OK"
            )
        else:
            log.error(
                f"  🔗 Workflow filho falhou: '{nome_filho}' — "
                f"parou em '{resultado_filho.get('passo_falhou')}'"
            )

        return {
            "sucesso":  resultado_filho["sucesso"],
            "mensagem": (
                f"Workflow '{nome_filho}': "
                f"{resultado_filho['passos_ok']}/{resultado_filho['passos_total']} passos OK"
            ),
            "dados": resultado_filho,
        }

    return {"sucesso": False, "mensagem": f"Ação engine desconhecida: {acao}", "dados": None}


def carregar_workflow(nome: str) -> dict:
    caminho = WORKFLOWS_DIR / f"{nome}.json"

    if not caminho.exists():
        disponiveis = [f.stem for f in WORKFLOWS_DIR.glob("*.json")]
        raise FileNotFoundError(
            f"Workflow '{nome}' não encontrado.\n"
            f"Disponíveis: {disponiveis}"
        )

    try:
        with open(caminho, "r", encoding="utf-8") as f:
            workflow = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Workflow '{nome}.json' tem JSON inválido: {e}")

    if "passos" not in workflow or not isinstance(workflow["passos"], list):
        raise ValueError(f"Workflow '{nome}' precisa ter campo 'passos' (lista)")
    if not workflow["passos"]:
        raise ValueError(f"Workflow '{nome}' não tem nenhum passo definido")

    log.info(
        f"📋 Workflow '{nome}' carregado: "
        f"{len(workflow['passos'])} passo(s) | v{workflow.get('versao', '?')}"
    )
    return workflow


def _executar_passo(passo: dict, contexto: Optional[dict], numero: int, total: int) -> dict:
    acao      = passo.get("acao", "")
    descricao = passo.get("descricao") or acao
    max_retry = int(passo.get("retry", 0))
    delay     = float(passo.get("delay_retry", 3))
    total_tentativas = max_retry + 1

    kwargs = {}
    for campo in ("alvo", "segundos", "texto", "contexto", "imagem",
                  "confidence", "teclas", "tecla", "x", "y", "duracao",
                  "duplo", "timeout", "workflow",
                  "confianca_minima", "usar_cache",
                  "video_path"):
        if campo in passo:
            val = passo[campo]
            if isinstance(val, str) and contexto:
                for k, v in contexto.items():
                    val = val.replace(f"{{{k}}}", str(v))
            kwargs[campo] = val

    for tentativa in range(1, total_tentativas + 1):
        sufixo = f" (tentativa {tentativa}/{total_tentativas})" if total_tentativas > 1 else ""
        log.info(f"  ▶ Passo {numero}/{total}: [{acao}] {descricao}{sufixo}")

        try:
            if acao in _ACOES_ENGINE:
                resultado = _executar_acao_engine(acao, kwargs, contexto)
            elif acao in _ACOES_BRAIN:
                resultado = _executar_acao_brain(acao, kwargs)
            else:
                resultado = enviar_comando(acao, **kwargs)

            sucesso = resultado.get("sucesso", False)

            if sucesso:
                log.info(f"  ✅ Passo {numero} OK: {resultado.get('mensagem', '')[:80]}")
                return {"sucesso": True, "mensagem": resultado.get("mensagem", ""), "dados": resultado.get("dados")}

            log.warning(f"  ⚠️ Passo {numero} falhou: {resultado.get('mensagem', '')}")

        except Exception as e:
            log.error(f"  ❌ Passo {numero} exceção: {e}")
            resultado = {"mensagem": str(e)}

        if tentativa < total_tentativas:
            log.info(f"  ⏳ Retry em {delay}s...")
            time.sleep(delay)

    msg_final = resultado.get("mensagem", "Falha sem mensagem")
    log.error(f"  🚫 Passo {numero} [{acao}] esgotou {total_tentativas} tentativa(s): {msg_final}")
    return {"sucesso": False, "mensagem": msg_final, "dados": None}


def executar_workflow(nome: str, contexto: Optional[dict] = None) -> dict:
    log.info(f"\n{'─'*50}")
    log.info(f"🚀 Iniciando workflow: '{nome}'")
    if contexto:
        log.info(f"   Contexto recebido: {contexto}")

    try:
        workflow = carregar_workflow(nome)
    except (FileNotFoundError, ValueError) as e:
        log.error(str(e))
        return _resultado_erro(nome, str(e), passo_falhou="carregar_workflow")

    # Mescla contexto_padrao do JSON com o contexto recebido
    # Ordem: contexto_padrao é base, contexto externo sobrescreve
    contexto_final = {}
    contexto_final.update(workflow.get("contexto_padrao", {}))
    contexto_final.update(contexto or {})
    log.info(f"   Contexto efetivo: {contexto_final}")

    passos       = workflow["passos"]
    total        = len(passos)
    resultados   = []
    passos_ok    = 0
    passo_falhou = None

    atualizar_varios({
        "estado_atual": "processando",
        "ultima_acao":  f"workflow:{nome}",
    })
    registrar_etapa(f"workflow_{nome}_iniciado", f"{total} passos")

    for i, passo in enumerate(passos, start=1):
        passo_id   = passo.get("id", f"passo_{i}")
        eh_critico = passo.get("critico", False)

        registrar_etapa(f"passo_{passo_id}", passo.get("acao", ""))
        atualizar_varios({"ultima_acao": f"{nome}:{passo_id}"})

        resultado_passo = _executar_passo(passo, contexto_final, numero=i, total=total)
        resultado_passo["passo_id"] = passo_id
        resultados.append(resultado_passo)

        if resultado_passo["sucesso"]:
            passos_ok += 1
        elif eh_critico:
            passo_falhou = passo_id
            log.error(
                f"🛑 Passo crítico '{passo_id}' falhou — "
                f"interrompendo workflow '{nome}'"
            )
            break
        else:
            log.warning(f"  ↩ Passo '{passo_id}' não crítico — continuando workflow")

    sucesso_total = passo_falhou is None and passos_ok == total

    emoji = "✅" if sucesso_total else ("⚠️" if passos_ok > 0 else "❌")
    log.info(
        f"{emoji} Workflow '{nome}' finalizado: "
        f"{passos_ok}/{total} passos OK"
        + (f" | parou em '{passo_falhou}'" if passo_falhou else "")
    )
    registrar_etapa(
        f"workflow_{nome}_{'concluido' if sucesso_total else 'falhou'}",
        f"{passos_ok}/{total} passos"
    )

    return {
        "sucesso":      sucesso_total,
        "workflow":     nome,
        "passos_ok":    passos_ok,
        "passos_total": total,
        "passo_falhou": passo_falhou,
        "resultados":   resultados,
    }


def _resultado_erro(nome: str, mensagem: str, passo_falhou: str) -> dict:
    return {
        "sucesso":      False,
        "workflow":     nome,
        "passos_ok":    0,
        "passos_total": 0,
        "passo_falhou": passo_falhou,
        "resultados":   [{"sucesso": False, "mensagem": mensagem}],
    }


def listar_workflows() -> list[str]:
    return sorted(f.stem for f in WORKFLOWS_DIR.glob("*.json"))