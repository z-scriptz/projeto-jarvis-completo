# analytics/strategy.py
# Lê o Historico_Performance, identifica padrões e gera insights estratégicos
# O agente usa isso para tomar decisões melhores sobre o que postar

from collections import defaultdict
from analytics.scoring import rankear_posts, calcular_ctr, calcular_conversao
from shared.logger import get_logger

log = get_logger(__name__)


# =========================
# ANÁLISE DE HISTÓRICO
# =========================

def analisar_estrategia(historico: list[dict]) -> dict:
    """
    Análise completa do histórico de posts.
    Identifica top produtos, padrões de CTR/conversão e nichos mais fortes.

    Args:
        historico: lista de dicts com campos:
            produto, views, cliques, vendas, lucro_est, data_post, plataforma

    Returns:
        dict com análise completa — usado pelo context_engine pra gerar o prompt

    Uso:
        dados = ler_historico_sheets()
        analise = analisar_estrategia(dados)
    """
    if not historico:
        log.warning("Histórico vazio — sem dados para analisar")
        return {"status": "sem_dados"}

    posts_rankeados = rankear_posts(historico)

    return {
        "status":           "ok",
        "total_posts":      len(historico),
        "top_produtos":     _top_produtos(posts_rankeados),
        "piores_produtos":  _piores_produtos(posts_rankeados),
        "nicho_mais_forte": _nicho_mais_forte(posts_rankeados),
        "metricas_gerais":  _metricas_gerais(historico),
        "padroes":          _detectar_padroes(posts_rankeados),
        "recomendacoes":    _gerar_recomendacoes(posts_rankeados),
    }


def _top_produtos(posts: list[dict], n: int = 5) -> list[dict]:
    """Top N produtos por score."""
    return [
        {
            "produto":       p.get("produto", "?"),
            "score":         p["score"],
            "classificacao": p["classificacao"],
            "ctr":           p["ctr"],
            "views":         p.get("views", 0),
            "lucro_est":     p.get("lucro_est", 0),
        }
        for p in posts[:n]
    ]


def _piores_produtos(posts: list[dict], n: int = 3) -> list[dict]:
    """Bottom N produtos por score."""
    return [
        {"produto": p.get("produto", "?"), "score": p["score"]}
        for p in posts[-n:]
    ]


def _nicho_mais_forte(posts: list[dict]) -> dict:
    """
    Agrupa posts por nicho/categoria e calcula score médio por grupo.
    Retorna o nicho mais forte.

    Nota: requer campo 'nicho' nos dados do histórico.
    Se não existir, usa 'plataforma' como agrupador.
    """
    grupos: dict[str, list[float]] = defaultdict(list)

    for p in posts:
        chave = p.get("nicho") or p.get("plataforma") or "geral"
        grupos[chave].append(p["score"])

    if not grupos:
        return {}

    media_por_grupo = {
        grupo: round(sum(scores) / len(scores), 2)
        for grupo, scores in grupos.items()
    }

    melhor = max(media_por_grupo, key=media_por_grupo.get)
    return {
        "nicho":        melhor,
        "score_medio":  media_por_grupo[melhor],
        "todos":        dict(sorted(media_por_grupo.items(), key=lambda x: x[1], reverse=True)),
    }


def _metricas_gerais(historico: list[dict]) -> dict:
    """Métricas agregadas de todo o histórico."""
    total_views   = sum(float(p.get("views", 0)) for p in historico)
    total_cliques = sum(float(p.get("cliques", 0)) for p in historico)
    total_vendas  = sum(float(p.get("vendas", 0)) for p in historico)
    total_lucro   = sum(float(p.get("lucro_est", 0)) for p in historico)

    return {
        "total_views":    int(total_views),
        "total_cliques":  int(total_cliques),
        "total_vendas":   int(total_vendas),
        "lucro_total":    round(total_lucro, 2),
        "ctr_medio":      calcular_ctr(total_views, total_cliques),
        "conversao_media": calcular_conversao(total_cliques, total_vendas),
        "lucro_por_post": round(total_lucro / len(historico), 2) if historico else 0,
    }


def _detectar_padroes(posts: list[dict]) -> list[str]:
    """
    Detecta padrões observáveis no histórico.
    Retorna lista de observações em texto (alimenta o prompt).
    """
    padroes = []
    if not posts:
        return padroes

    # CTR alto nos top posts
    top3_ctr = [p["ctr"] for p in posts[:3]]
    if top3_ctr and sum(top3_ctr) / len(top3_ctr) > 5:
        padroes.append(f"Top 3 posts têm CTR médio de {sum(top3_ctr)/len(top3_ctr):.1f}% — acima da média do mercado")

    # Concentração de performance
    if len(posts) >= 5:
        top20_lucro = sum(float(p.get("lucro_est", 0)) for p in posts[:max(1, len(posts)//5)])
        total_lucro = sum(float(p.get("lucro_est", 0)) for p in posts)
        if total_lucro > 0 and top20_lucro / total_lucro > 0.6:
            padroes.append("80% do lucro vem dos 20% melhores posts — foco nos nichos vencedores")

    # Queda de performance nos piores
    if len(posts) >= 3:
        ultimo = posts[-1]
        if ultimo["score"] < 10:
            padroes.append(f"Produto '{ultimo.get('produto','?')}' com score muito baixo — considerar pausar")

    return padroes


def _gerar_recomendacoes(posts: list[dict]) -> list[str]:
    """
    Gera recomendações acionáveis baseadas nos dados.
    """
    recomendacoes = []

    if not posts:
        return ["Nenhum dado histórico — poste mais para gerar insights"]

    top = posts[0]
    recomendacoes.append(
        f"Priorize conteúdo similar a '{top.get('produto','?')}' (score {top['score']} — {top['classificacao']})"
    )

    # CTR baixo geral
    ctr_medio = sum(p["ctr"] for p in posts) / len(posts)
    if ctr_medio < 2:
        recomendacoes.append("CTR geral abaixo de 2% — revise os hooks e CTAs dos roteiros")

    # Conversão baixa
    conv_media = sum(p["conversao"] for p in posts) / len(posts)
    if conv_media < 1:
        recomendacoes.append("Conversão abaixo de 1% — testar páginas de destino diferentes ou links mais diretos")

    return recomendacoes