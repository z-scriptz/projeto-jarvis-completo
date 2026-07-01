# analytics/context_engine.py
# Gera o "Contexto Estratégico do Dia" para alimentar o PROMPT_TEMPLATE do THINK
#
# Fluxo:
#   1. Lê Config_Agente → contexto_do_dia manual (opcional)
#   2. Lê Historico_Performance → top produtos, nichos, alertas
#   3. Combina tudo em uma string pronta para entrar no prompt do Gemini

import time
from typing import Optional

from analytics.scoring import rankear_posts, calcular_ctr, calcular_conversao
from shared.logger import get_logger

log = get_logger(__name__)

# =========================
# FALLBACK — sem dados históricos
# =========================

CONTEXTO_FALLBACK = """
Nenhum histórico de performance disponível ainda.
Estratégia padrão: foco em produtos com alta demanda no TikTok Shop Brasil,
linguagem jovem e dinâmica, hooks de curiosidade nos primeiros 3 segundos,
CTA direto para o link de compra.
"""


# =========================
# 1. CONTEXTO MANUAL DO DIA
# =========================

def carregar_contexto_do_dia() -> str:
    """
    Lê a aba Config_Agente e busca a variável 'contexto_do_dia'.
    Permite que você escreva manualmente na planilha o foco do dia.

    Exemplo na planilha:
        contexto_do_dia | Foco em produtos fitness, semana pré-verão

    Retorna string vazia se não existir.
    """
    try:
        from memory.sheets_engine import ler_config
        config = ler_config()
        contexto = config.get("contexto_do_dia", "").strip()

        if contexto:
            log.info(f"📋 Contexto manual do dia carregado: '{contexto[:60]}...'")
        else:
            log.debug("Nenhum contexto_do_dia definido na planilha")

        return contexto

    except Exception as e:
        log.warning(f"Não foi possível ler Config_Agente: {e}")
        return ""


# =========================
# 2. ANÁLISE DO HISTÓRICO
# =========================

def _ler_historico_sheets() -> list[dict]:
    """
    Lê a aba Historico_Performance e retorna lista de dicts com métricas.
    Retorna lista vazia se falhar.
    """
    try:
        from memory.sheets_engine import conectar_planilha, ABA_HISTORICO
        aba = conectar_planilha().worksheet(ABA_HISTORICO)
        rows = aba.get_all_values()

        if len(rows) <= 1:
            return []  # só cabeçalho

        historico = []
        for row in rows[1:]:
            while len(row) < 7:
                row.append("")

            def safe_float(v):
                try:
                    return float(str(v).replace("R$", "").replace(",", ".").strip() or 0)
                except Exception:
                    return 0.0

            historico.append({
                "id_post":   row[0],
                "data_post": row[1],
                "views":     safe_float(row[2]),
                "cliques":   safe_float(row[3]),
                "vendas":    safe_float(row[4]),
                "lucro_est": safe_float(row[5]),
                "produto":   row[6] if len(row) > 6 else "",
            })

        log.info(f"📊 Histórico carregado: {len(historico)} registros")
        return historico

    except Exception as e:
        log.warning(f"Não foi possível ler Historico_Performance: {e}")
        return []


def analisar_historico_performance() -> dict:
    """
    Lê o histórico e identifica top produtos, padrões de CTR/conversão
    e nichos mais fortes.

    Retorna dict com:
        top_produtos    — top 3 por score
        ctr_medio       — CTR médio geral
        conversao_media — taxa de conversão média
        total_posts     — quantidade de posts no histórico
        alertas         — observações automáticas
        status          — "ok" ou "sem_dados"
    """
    historico = _ler_historico_sheets()

    if not historico:
        log.info("Histórico vazio — usando fallback")
        return {"status": "sem_dados"}

    posts_rankeados = rankear_posts(historico)

    top3 = posts_rankeados[:3]
    total_views   = sum(p.get("views", 0) for p in historico)
    total_cliques = sum(p.get("cliques", 0) for p in historico)
    total_vendas  = sum(p.get("vendas", 0) for p in historico)

    alertas = []

    ctr_medio = calcular_ctr(total_views, total_cliques)
    if ctr_medio < 2.0:
        alertas.append(f"CTR médio baixo ({ctr_medio:.1f}%) — revisar hooks e CTAs")

    conv_media = calcular_conversao(total_cliques, total_vendas)
    if conv_media < 1.0:
        alertas.append(f"Conversão baixa ({conv_media:.1f}%) — testar landing pages ou links diretos")

    if posts_rankeados and posts_rankeados[-1]["score"] < 5:
        alertas.append(f"Produto fraco detectado: '{posts_rankeados[-1].get('produto','?')}' — considerar pausar")

    return {
        "status":          "ok",
        "total_posts":     len(historico),
        "top_produtos":    [
            {
                "produto":       p.get("produto", f"Post {p.get('id_post','?')}"),
                "score":         p["score"],
                "classificacao": p["classificacao"],
                "ctr":           p["ctr"],
                "views":         int(p.get("views", 0)),
                "lucro_est":     p.get("lucro_est", 0),
            }
            for p in top3
        ],
        "ctr_medio":       ctr_medio,
        "conversao_media": conv_media,
        "alertas":         alertas,
    }


# =========================
# 3. GERAR CONTEXTO ESTRATÉGICO
# =========================

def gerar_contexto_estrategico() -> str:
    """
    Combina contexto manual + análise do histórico em uma string
    pronta para entrar no PROMPT_TEMPLATE do THINK.

    Retorna string formatada com:
        - Foco do dia (manual ou padrão)
        - Top 3 produtos por performance
        - CTR e conversão médios
        - Alertas estratégicos

    Nunca lança exceção — em caso de falha retorna o fallback.
    """
    try:
        hoje = time.strftime("%d/%m/%Y")
        linhas = [f"📅 DATA: {hoje}"]

        # Bloco 1: contexto manual
        contexto_manual = carregar_contexto_do_dia()
        if contexto_manual:
            linhas.append(f"\n🎯 FOCO DO DIA:\n{contexto_manual}")

        # Bloco 2: análise do histórico
        analise = analisar_historico_performance()

        if analise["status"] == "sem_dados":
            linhas.append(f"\n📊 HISTÓRICO: Nenhum dado ainda. {CONTEXTO_FALLBACK.strip()}")
        else:
            # Top produtos
            linhas.append(f"\n🏆 TOP PRODUTOS (base: {analise['total_posts']} posts):")
            for i, p in enumerate(analise["top_produtos"], 1):
                linhas.append(
                    f"  {i}. {p['produto']} — Score {p['score']} {p['classificacao']} "
                    f"| CTR {p['ctr']}% | {p['views']:,} views | R$ {p['lucro_est']:.2f}"
                )

            # Métricas gerais
            linhas.append(
                f"\n📈 MÉTRICAS GERAIS:"
                f"\n  CTR médio: {analise['ctr_medio']:.1f}%"
                f"\n  Conversão média: {analise['conversao_media']:.1f}%"
            )

            # Alertas
            if analise["alertas"]:
                linhas.append("\n⚠️ ALERTAS ESTRATÉGICOS:")
                for alerta in analise["alertas"]:
                    linhas.append(f"  • {alerta}")

            # Recomendação automática
            if analise["top_produtos"]:
                melhor = analise["top_produtos"][0]
                linhas.append(
                    f"\n💡 RECOMENDAÇÃO: Priorize conteúdo no estilo de "
                    f"'{melhor['produto']}' — melhor score da base."
                )

        contexto_final = "\n".join(linhas)
        log.info(f"✅ Contexto estratégico gerado ({len(contexto_final)} chars)")
        return contexto_final

    except Exception as e:
        log.error(f"Erro ao gerar contexto estratégico: {e}")
        return f"📅 {time.strftime('%d/%m/%Y')}\n{CONTEXTO_FALLBACK.strip()}"