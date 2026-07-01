# main.py
# Loop central do AgenteIA
# Ciclo completo: THINK → ACT → OBSERVE
#
# THINK:   Gemini raciocina e gera o conteúdo
# ACT:     executor Windows abre site e prepara post
# OBSERVE: Gemini Vision analisa a tela e confirma o resultado
#
# Uso:
#   python main.py                  # roda uma vez
#   python main.py --loop           # loop contínuo
#   python main.py --observe        # testa só o OBSERVE agora
#   python main.py --intervalo 300  # loop a cada 5 min

import os
import sys
import time
import argparse
import re

from google import genai
from google.genai import errors

from memory.sheets_engine import (
    ler_produtos_pendentes,
    salvar_roteiro,
    atualizar_status,
    registrar_erro,
    ler_config,
)
from brain.commander import enviar_comando, enviar_sequencia
from brain.vision_analyzer import observar_e_analisar
from analytics.context_engine import gerar_contexto_estrategico
from workflows.engine import executar_workflow, listar_workflows
from brain.decision_engine import decidir, TipoDecisao, resumo_decisao
from memory.state_manager import (
    iniciar_workflow,
    registrar_etapa,
    atualizar_varios,
    limpar_estado,
    ja_processando,
    excedeu_tentativas,
    status_atual,
)
from shared.logger import get_logger

log = get_logger("main")


# =========================
# CLIENTE GEMINI
# =========================

def _criar_cliente_gemini():
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY não definida. Export no terminal.")
    return genai.Client(api_key=api_key)


# =========================
# THINK — GERAÇÃO DE CONTEÚDO
# =========================

PROMPT_TEMPLATE = """
Você é um estrategista de conteúdo viral especializado em {plataforma}.

--- CONTEXTO ESTRATÉGICO DO DIA ---
{contexto_estrategico}
------------------------------------

Produto para criar conteúdo: {produto}

Use o contexto estratégico acima para calibrar o tom, nicho e abordagem.
Se houver top produtos listados, inspire-se no estilo deles.
Se houver alertas, corrija os problemas apontados neste novo conteúdo.

Responda EXATAMENTE neste formato, sem texto adicional:

ROTEIRO:
[roteiro de até 20 segundos, dinâmico, persuasivo, linguagem brasileira moderna]

LEGENDA:
[legenda curta, com emojis, focada em SEO para {plataforma}]

CTA:
[chamada para ação direta]

HASHTAGS:
[10 hashtags separadas por espaço, com #]
"""

# Contexto estratégico é carregado uma vez por ciclo e compartilhado entre produtos
_contexto_cache: dict = {"texto": None, "gerado_em": 0}
_CONTEXTO_TTL = 1800  # 30 minutos — recarrega se o ciclo for muito longo


def _obter_contexto_estrategico() -> str:
    """
    Retorna o contexto estratégico do dia, usando cache de 30 min.
    Assim não consulta Sheets a cada produto — apenas uma vez por ciclo.
    """
    agora = time.time()
    if _contexto_cache["texto"] is None or (agora - _contexto_cache["gerado_em"]) > _CONTEXTO_TTL:
        log.info("♻️ Carregando contexto estratégico do dia...")
        _contexto_cache["texto"] = gerar_contexto_estrategico()
        _contexto_cache["gerado_em"] = agora
    return _contexto_cache["texto"]


def think(client, produto: str, plataforma: str = "TikTok") -> dict | None:
    """
    THINK: Gemini raciocina e gera conteúdo para o produto.
    Inclui o contexto estratégico do dia no prompt automaticamente.
    Retorna dict com roteiro, legenda, cta, hashtags — ou None se falhar.
    """
    log.info(f"🧠 THINK: gerando conteúdo para '{produto}' ({plataforma})")
    registrar_etapa("think_iniciado", f"produto='{produto}'")

    contexto = _obter_contexto_estrategico()
    prompt = PROMPT_TEMPLATE.format(
        plataforma=plataforma,
        produto=produto,
        contexto_estrategico=contexto,
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        conteudo = _parsear_resposta(response.text)
        registrar_etapa("think_concluido", f"roteiro={len(conteudo.get('roteiro',''))} chars")
        log.info(f"✅ THINK concluído: roteiro gerado ({len(conteudo.get('roteiro',''))} chars)")
        return conteudo

    except errors.ClientError as e:
        registrar_etapa("think_erro", str(e))
        log.error(f"Erro de cota Gemini (429): {e}")
        return None
    except Exception as e:
        registrar_etapa("think_erro", str(e))
        log.error(f"Erro inesperado no THINK: {e}")
        return None


def _parsear_resposta(texto: str) -> dict:
    def extrair(secao: str) -> str:
        pattern = rf"{secao}:\s*(.*?)(?=\n[A-Z]+:|$)"
        match = re.search(pattern, texto, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    return {
        "roteiro":  extrair("ROTEIRO"),
        "legenda":  extrair("LEGENDA"),
        "cta":      extrair("CTA"),
        "hashtags": extrair("HASHTAGS"),
    }


# =========================
# ACT — WORKFLOW ENGINE
# =========================

# Mapa: plataforma → workflow JSON a executar
WORKFLOWS_PLATAFORMA = {
    "tiktok":    "postar_tiktok",
    "instagram": "postar_instagram",   # crie o JSON quando precisar
    "youtube":   "postar_youtube",     # crie o JSON quando precisar
}

def act(produto: str, plataforma: str, conteudo: dict) -> bool:
    """
    ACT: Executa o workflow da plataforma via Workflow Engine.
    Passa produto e plataforma como contexto para interpolação no JSON.
    Retorna True se o workflow foi concluído sem passo crítico falhando.
    """
    nome_workflow = WORKFLOWS_PLATAFORMA.get(plataforma.lower(), "postar_tiktok")
    log.info(f"⚙️ ACT: executando workflow '{nome_workflow}' para '{produto}'")
    registrar_etapa("act_iniciado", f"workflow={nome_workflow}")

    # Contexto disponível para interpolação nos passos do JSON
    ctx = {
        "produto":    produto,
        "plataforma": plataforma,
        "legenda":    conteudo.get("legenda", ""),
        "hashtags":   conteudo.get("hashtags", ""),
        "cta":        conteudo.get("cta", ""),
    }

    resultado = executar_workflow(nome_workflow, contexto=ctx)
    sucesso   = resultado["sucesso"]

    atualizar_varios({
        "ultima_acao": f"workflow:{nome_workflow}",
        "etapa":       "act_concluido" if sucesso else "act_erro",
    })

    log.info(
        f"{'✅' if sucesso else '❌'} ACT: {resultado['passos_ok']}/{resultado['passos_total']} passos"
        + (f" | parou em '{resultado['passo_falhou']}'" if resultado["passo_falhou"] else "")
    )
    return sucesso


# =========================
# OBSERVE — VISÃO DA TELA
# =========================

def observe(contexto: str) -> dict:
    """
    OBSERVE: tira screenshot → Gemini Vision analisa → retorna estado da tela.
    """
    log.info(f"👁️ OBSERVE: analisando tela — contexto: '{contexto}'")
    registrar_etapa("observe_iniciado", contexto)
    resultado = observar_e_analisar(contexto=contexto)

    if resultado["sucesso"]:
        analise = resultado["analise"]
        resumo = f"estado={analise.get('estado')} | app={analise.get('app_ativo')}"
        atualizar_varios({
            "ultima_observacao": resumo,
            "estado_tela":       analise.get("estado", ""),
            "etapa":             "observe_concluido",
        })
        log.info(
            f"👁️ OBSERVE: estado='{analise.get('estado')}' | "
            f"app='{analise.get('app_ativo')}' | "
            f"próxima='{str(analise.get('proxima_acao_sugerida',''))[:60]}'"
        )
    else:
        atualizar_varios({"etapa": "observe_erro", "ultima_observacao": resultado.get("erro", "")})
        log.warning(f"⚠️ OBSERVE falhou: {resultado.get('erro')}")

    return resultado


# =========================
# CICLO THINK → ACT → OBSERVE
# =========================

def ciclo_completo(item: dict, client) -> bool:
    """
    Ciclo autônomo completo: THINK → ACT → OBSERVE → DECIDE → ACT → ...

    O Decision Engine avalia cada OBSERVE e decide autonomamente:
      - CONTINUAR    → executa próximo workflow
      - AGUARDAR     → espera e re-observa
      - CONCLUIDO    → encerra com sucesso
      - ERRO_FATAL   → aborta e registra
      - ERRO_RECUPERAVEL → tenta de novo (até max_decisoes)
    """
    linha      = item["linha"]
    produto    = item["produto"]
    plataforma = item.get("plataforma", "TikTok")
    MAX_DECISOES = 5   # evita loop infinito de OBSERVE → DECIDE

    log.info(f"\n{'='*50}")
    log.info(f"🔄 CICLO AUTÔNOMO: linha={linha} | '{produto}' | {plataforma}")

    # ── GUARDA ─────────────────────────────────────
    if ja_processando(produto):
        if excedeu_tentativas():
            registrar_erro(linha, "Excedeu tentativas — abortando")
            limpar_estado()
            return False
        log.warning(f"⚠️ Retomando '{produto}'")

    iniciar_workflow(produto, plataforma, linha)
    atualizar_status(linha, "Em_Progresso")

    # ── THINK ──────────────────────────────────────
    conteudo = think(client, produto, plataforma)
    if not conteudo or not conteudo.get("roteiro"):
        registrar_erro(linha, "THINK falhou")
        atualizar_varios({"estado_atual": "erro"})
        return False

    salvar_roteiro(
        linha=linha,
        roteiro=conteudo["roteiro"],
        legenda=conteudo["legenda"],
        cta=conteudo["cta"],
        hashtags=conteudo["hashtags"],
    )

    # ── ACT INICIAL ────────────────────────────────
    act_ok = act(produto, plataforma, conteudo)
    if not act_ok:
        registrar_erro(linha, "ACT inicial falhou — workflow crítico não concluído")
        atualizar_varios({"estado_atual": "erro"})
        return False

    # ── LOOP AUTÔNOMO: OBSERVE → DECIDE → ACT ──────
    ctx_decisao = {
        "produto":    produto,
        "plataforma": plataforma.lower(),
        "legenda":    conteudo.get("legenda", ""),
        "hashtags":   conteudo.get("hashtags", ""),
    }

    for rodada in range(1, MAX_DECISOES + 1):
        log.info(f"\n🔁 Rodada de decisão {rodada}/{MAX_DECISOES}")

        # OBSERVE
        time.sleep(3)
        from memory.state_manager import carregar_estado
        ctx_decisao["etapa_atual"] = carregar_estado().get("etapa", "")

        obs = observe(f"rodada_{rodada}_{plataforma.lower()}")

        analise = obs.get("analise", {}) if obs.get("sucesso") else {"erro": obs.get("erro", "")}

        # DECIDE
        decisao = decidir(
            analise=analise,
            contexto=ctx_decisao,
            tentativas_decisao=rodada - 1,
            max_tentativas=MAX_DECISOES,
        )
        log.info(resumo_decisao(decisao))
        atualizar_varios({"ultima_observacao": decisao.motivo})

        # ── Executa decisão ─────────────────────────

        if decisao.tipo == TipoDecisao.CONCLUIDO:
            log.info(f"✅ Ciclo autônomo concluído: '{produto}'")
            limpar_estado()
            return True

        elif decisao.tipo == TipoDecisao.ERRO_FATAL:
            registrar_erro(linha, decisao.motivo)
            atualizar_varios({"estado_atual": "erro"})
            limpar_estado()
            return False

        elif decisao.tipo == TipoDecisao.ERRO_RECUPERAVEL:
            registrar_erro(linha, f"Erro recuperável (rodada {rodada}): {decisao.motivo}")
            if decisao.aguardar_segundos:
                log.info(f"⏳ Aguardando {decisao.aguardar_segundos}s antes de re-observar...")
                time.sleep(decisao.aguardar_segundos)
            # Não encerra — próxima rodada vai re-observar

        elif decisao.tipo == TipoDecisao.AGUARDAR:
            if decisao.aguardar_segundos:
                log.info(f"⏳ Aguardando {decisao.aguardar_segundos}s...")
                time.sleep(decisao.aguardar_segundos)
            # Próxima rodada re-observa sem nova ação

        elif decisao.tipo in (TipoDecisao.CONTINUAR, TipoDecisao.REPETIR):
            if decisao.proximo_workflow:
                log.info(f"▶️ Executando próximo workflow: '{decisao.proximo_workflow}'")
                ctx_conteudo = {**ctx_decisao, **conteudo}
                wf = executar_workflow(decisao.proximo_workflow, contexto=ctx_conteudo)
                if not wf["sucesso"] and wf.get("passo_falhou"):
                    log.warning(f"⚠️ Workflow '{decisao.proximo_workflow}' falhou em '{wf['passo_falhou']}'")
            else:
                log.info("▶️ Continuar sem novo workflow — re-observando")
            if decisao.aguardar_segundos:
                time.sleep(decisao.aguardar_segundos)

    # Esgotou rodadas sem conclusão
    registrar_erro(linha, f"Ciclo autônomo esgotou {MAX_DECISOES} rodadas sem conclusão")
    atualizar_varios({"estado_atual": "erro"})
    return False


# =========================
# PROCESSAR FILA
# =========================

def processar_pendentes() -> int:
    log.info("=" * 50)
    log.info("🤖 AgenteIA — iniciando processamento da fila")
    log.info(f"📌 {status_atual()}")

    config = ler_config()
    plataforma_padrao = config.get("plataforma_padrao", "TikTok")

    pendentes = ler_produtos_pendentes()
    if not pendentes:
        log.info("✅ Nenhum produto pendente. Aguardando próximo ciclo.")
        return 0

    log.info(f"📋 {len(pendentes)} produto(s) na fila")

    try:
        client = _criar_cliente_gemini()
    except RuntimeError as e:
        log.error(str(e))
        return 0

    processados = 0
    for item in pendentes:
        if not item.get("plataforma"):
            item["plataforma"] = plataforma_padrao

        ok = ciclo_completo(item, client)
        if ok:
            processados += 1
        time.sleep(5)  # pausa entre produtos

    log.info(f"🏁 Fila processada: {processados}/{len(pendentes)} com sucesso")
    return processados


# =========================
# ENTRY POINT
# =========================

def main():
    parser = argparse.ArgumentParser(description="AgenteIA — THINK → ACT → OBSERVE")
    parser.add_argument("--loop",      action="store_true", help="Roda em loop contínuo")
    parser.add_argument("--observe",   action="store_true", help="Testa só o OBSERVE agora")
    parser.add_argument("--contexto",  action="store_true", help="Exibe o contexto estratégico do dia")
    parser.add_argument("--workflow",  type=str,            help="Executa um workflow isolado (ex: postar_tiktok)")
    parser.add_argument("--intervalo", type=int, default=300, help="Segundos entre ciclos (padrão: 300)")
    args = parser.parse_args()

    # Executa workflow isolado para teste
    if args.workflow:
        log.info(f"🧪 Modo teste WORKFLOW: '{args.workflow}'")
        log.info(f"   Disponíveis: {listar_workflows()}")
        resultado = executar_workflow(args.workflow)
        import json as _json
        print("\n📊 Resultado:")
        print(_json.dumps(resultado, indent=2, ensure_ascii=False))
        return

    # Exibe contexto estratégico do dia
    if args.contexto:
        log.info("🧪 Modo teste CONTEXTO ESTRATÉGICO")
        contexto = gerar_contexto_estrategico()
        print("\n" + "="*60)
        print(contexto)
        print("="*60)
        return

    # Teste isolado do OBSERVE
    if args.observe:
        log.info("🧪 Modo teste OBSERVE")
        resultado = observe("teste_manual")
        if resultado["sucesso"]:
            import json
            print("\n📊 Análise Gemini Vision:")
            print(json.dumps(resultado["analise"], indent=2, ensure_ascii=False))
        else:
            print(f"❌ OBSERVE falhou: {resultado.get('erro')}")
        return

    # Loop contínuo
    if args.loop:
        log.info(f"🔁 Modo loop — intervalo: {args.intervalo}s")
        while True:
            try:
                processar_pendentes()
            except KeyboardInterrupt:
                log.info("⛔ Loop encerrado pelo usuário")
                sys.exit(0)
            except Exception as e:
                log.error(f"Erro inesperado: {e}")
            log.info(f"⏳ Próximo ciclo em {args.intervalo}s...")
            time.sleep(args.intervalo)

    # Roda uma vez
    else:
        processar_pendentes()


if __name__ == "__main__":
    main()