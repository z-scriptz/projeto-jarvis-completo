# analytics/scoring.py
# Calcula score de performance de cada produto/post
# Score = base para o agente priorizar o que funciona

from shared.logger import get_logger

log = get_logger(__name__)

# =========================
# PESOS DO SCORE
# Ajuste conforme o que importa mais pro seu negócio
# =========================
PESO_VIEWS      = 0.25
PESO_CLIQUES    = 0.35   # mais peso pois indica intenção de compra
PESO_VENDAS     = 0.25
PESO_LUCRO      = 0.15


def calcular_score(
    views: float = 0,
    cliques: float = 0,
    vendas: float = 0,
    lucro_est: float = 0,
    normalizar: bool = True,
) -> float:
    """
    Calcula o score de performance de um post.

    Score ponderado de 0 a 100 (se normalizar=True).
    Ou valor bruto se normalizar=False.

    Args:
        views: número de visualizações
        cliques: número de cliques no link
        vendas: número de vendas confirmadas
        lucro_est: lucro estimado em R$
        normalizar: se True, retorna 0-100 via log scale

    Returns:
        float — score do post
    """
    import math

    def log_scale(v: float) -> float:
        """Evita que números gigantes dominem o score."""
        return math.log1p(max(v, 0))

    score_bruto = (
        PESO_VIEWS   * log_scale(views)   +
        PESO_CLIQUES * log_scale(cliques) +
        PESO_VENDAS  * log_scale(vendas)  +
        PESO_LUCRO   * log_scale(lucro_est)
    )

    if not normalizar:
        return round(score_bruto, 4)

    # Normaliza pra 0-100 assumindo teto razoável (~100k views, ~1k cliques)
    TETO = (
        PESO_VIEWS   * log_scale(100_000) +
        PESO_CLIQUES * log_scale(5_000)   +
        PESO_VENDAS  * log_scale(500)     +
        PESO_LUCRO   * log_scale(10_000)
    )
    score = min((score_bruto / TETO) * 100, 100)
    return round(score, 2)


def calcular_ctr(views: float, cliques: float) -> float:
    """
    Click-Through Rate: % de views que viraram cliques.
    Métrica chave para avaliar qualidade do conteúdo.
    """
    if views <= 0:
        return 0.0
    return round((cliques / views) * 100, 2)


def calcular_conversao(cliques: float, vendas: float) -> float:
    """
    Taxa de conversão: % de cliques que viraram vendas.
    """
    if cliques <= 0:
        return 0.0
    return round((vendas / cliques) * 100, 2)


def classificar_score(score: float) -> str:
    """
    Classifica o score em categorias legíveis para o prompt do Gemini.
    """
    if score >= 80:
        return "🔥 VIRAL"
    elif score >= 60:
        return "✅ ALTO DESEMPENHO"
    elif score >= 40:
        return "📈 MÉDIO"
    elif score >= 20:
        return "📉 BAIXO"
    else:
        return "❌ FRACO"


def rankear_posts(posts: list[dict]) -> list[dict]:
    """
    Recebe lista de posts com métricas e retorna rankeada por score.

    Cada post deve ter: views, cliques, vendas, lucro_est, produto (opcional)

    Retorna mesma lista com campo 'score', 'ctr', 'conversao', 'classificacao' adicionados.
    """
    resultado = []
    for post in posts:
        views     = float(post.get("views", 0))
        cliques   = float(post.get("cliques", 0))
        vendas    = float(post.get("vendas", 0))
        lucro     = float(post.get("lucro_est", 0))

        score = calcular_score(views, cliques, vendas, lucro)
        post_enriquecido = {
            **post,
            "score":        score,
            "classificacao": classificar_score(score),
            "ctr":          calcular_ctr(views, cliques),
            "conversao":    calcular_conversao(cliques, vendas),
        }
        resultado.append(post_enriquecido)

    resultado.sort(key=lambda p: p["score"], reverse=True)
    log.info(f"📊 {len(resultado)} posts rankeados. Top: {resultado[0].get('produto','?')} ({resultado[0]['score']}) " if resultado else "Lista vazia")
    return resultado