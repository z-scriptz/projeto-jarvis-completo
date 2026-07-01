# agents/performance_agent.py
# Performance Agent v1 do AgenteIA (Jarvis)
#
# Fecha o ciclo de aprendizado do Jarvis:
#   - Lê a aba Performance_Posts da planilha
#   - Calcula score por post (escala 0-120, baseado em views/curtidas/cliques/etc)
#   - Classifica posts em Excelente / Bom / Médio / Fraco
#   - Agrega aprendizados: melhor nicho, melhor produto, melhor hook,
#     hashtags frequentes em posts bons, nichos fracos
#   - Salva resumo em shared/content_plans/performance_resumo.json
#   - Atualiza state_manager com aprendizados
#
# Também expõe `registrar_post_planejado_no_performance()` para o
# orquestrador chamar quando um post for preparado/postado.
#
# Não usa Gemini. Não abre TikTok. Não publica. Não depende de quota.
#
# Uso:
#   from agents.performance_agent import analisar_performance_posts
#   resultado = analisar_performance_posts()
#
# Teste via terminal:
#   python -m agents.performance_agent

import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Optional

from shared.logger import get_logger

log = get_logger(__name__)

PLANS_DIR = Path(__file__).parent.parent / "shared" / "content_plans"
ABA_PERFORMANCE = "Performance_Posts"

# =================================================================
# CONFIGURAÇÃO
# =================================================================

# Headers da aba Performance_Posts (ordem importa — define a estrutura)
HEADERS_PERFORMANCE = [
    "Data",
    "Produto",
    "Nicho",
    "Plataforma",
    "Hook",
    "Legenda",
    "Hashtags",
    "Video_Path",
    "Status_Postagem",
    "Views",
    "Curtidas",
    "Comentarios",      # sem cedilha pra evitar problemas de encoding na planilha
    "Compartilhamentos",
    "Cliques",
    "Conversoes",
    "Score_Performance",
    "Aprendizado",
]

# Pesos máximos por métrica (somam 120, classificação usa esses pontos)
# Cada métrica recompensa de forma linear até o teto:
#   views: 1pt a cada DIVISOR views, teto MAX
PESOS = {
    "Views":             {"divisor": 100, "max": 40},
    "Curtidas":          {"divisor": 10,  "max": 20},
    "Comentarios":       {"divisor": 2,   "max": 10},
    "Compartilhamentos": {"divisor": 2,   "max": 10},
    "Cliques":           {"divisor": 5,   "max": 15},
    "Conversoes":        {"divisor": 1,   "max": 25},
}

# Faixas de classificação (você definiu na missão)
CLASSIFICACAO = [
    (70, "Excelente"),
    (45, "Bom"),
    (25, "Médio"),
    (0,  "Fraco"),
]

# Critério pra "post bom" (usado em hashtags frequentes / aprendizados)
SCORE_MINIMO_BOM = 45

# Mínimo de posts num nicho pra entrar em ranking (evita ruído)
MIN_POSTS_PARA_RANKING = 2

# Quantas hashtags top retornar
TOP_HASHTAGS_N = 10


# =================================================================
# HELPERS — PARSING E NORMALIZAÇÃO
# =================================================================

def _safe_int(valor) -> int:
    """Converte para int, aceitando '1.5k', '2,3M', '', None, etc."""
    if valor is None or valor == "":
        return 0
    if isinstance(valor, (int, float)):
        return int(valor)
    s = str(valor).strip().lower().replace(",", ".")
    if not s:
        return 0
    # Suporta "1.5k" → 1500, "2m" → 2000000
    mult = 1
    if s.endswith("k"):
        mult, s = 1_000, s[:-1]
    elif s.endswith("m"):
        mult, s = 1_000_000, s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return 0


def _extrair_hashtags(texto: str) -> list[str]:
    """Extrai hashtags de uma string normalizada (lowercase, sem #)."""
    if not texto:
        return []
    return [tag.lower() for tag in re.findall(r"#(\w+)", texto)]


# =================================================================
# CÁLCULO DE SCORE E CLASSIFICAÇÃO
# =================================================================

def calcular_score(metricas: dict) -> int:
    """
    Calcula score 0-120 baseado nas métricas do post.
    Cada métrica contribui linearmente até seu teto.

    Args:
        metricas: dict com chaves Views, Curtidas, Comentarios,
                  Compartilhamentos, Cliques, Conversoes
    """
    score = 0
    for chave, cfg in PESOS.items():
        valor = _safe_int(metricas.get(chave, 0))
        pontos = valor / cfg["divisor"]
        pontos = min(pontos, cfg["max"])
        score += pontos
    return int(round(score))


def classificar_score(score: int) -> str:
    """Retorna Excelente/Bom/Médio/Fraco baseado nas faixas."""
    for limite, rotulo in CLASSIFICACAO:
        if score >= limite:
            return rotulo
    return "Fraco"


# =================================================================
# LEITURA DA PLANILHA
# =================================================================

def _conectar_aba_performance():
    """
    Tenta abrir a aba Performance_Posts. Se não existir, tenta criar
    com headers. Retorna (aba, ja_existia: bool) ou (None, None) se falhar.

    Compatível com a API real do sheets_engine:
      - _aba(nome) → atalho que retorna Worksheet (raise se não existir)
      - conectar_planilha() → retorna Spreadsheet (necessário pra add_worksheet)
    """
    # Estratégia 1: tentar abrir aba existente pelo atalho _aba()
    try:
        from memory.sheets_engine import _aba
        aba = _aba(ABA_PERFORMANCE)
        log.info(f"📊 Aba '{ABA_PERFORMANCE}' encontrada")
        return aba, True
    except ImportError as e:
        log.error(f"❌ Não consegui importar _aba do sheets_engine: {e}")
        return None, None
    except Exception as e:
        # Provável WorksheetNotFound — aba não existe ainda. Vamos criar.
        log.warning(f"⚠️ Aba '{ABA_PERFORMANCE}' não existe ({type(e).__name__}) — tentando criar")

    # Estratégia 2: aba não existe — criar via conectar_planilha()
    try:
        from memory.sheets_engine import conectar_planilha
        planilha = conectar_planilha()
    except Exception as e:
        log.error(f"❌ Não consegui conectar à planilha pra criar a aba: {e}")
        return None, None

    try:
        aba = planilha.add_worksheet(
            title=ABA_PERFORMANCE,
            rows=200,
            cols=len(HEADERS_PERFORMANCE),
        )
        aba.append_row(HEADERS_PERFORMANCE)
        log.info(f"✅ Aba '{ABA_PERFORMANCE}' criada com {len(HEADERS_PERFORMANCE)} headers")
        return aba, False
    except Exception as e:
        log.error(f"❌ Não consegui criar aba '{ABA_PERFORMANCE}': {e}")
        return None, None


def _ler_posts_da_planilha() -> tuple[list[dict], bool]:
    """
    Lê todos os posts da aba Performance_Posts.

    Returns:
        (lista_de_posts_dict, conectou_planilha: bool)
        Cada post tem as chaves dos HEADERS_PERFORMANCE + "_linha" (número da linha).
    """
    aba, _ = _conectar_aba_performance()
    if aba is None:
        return [], False

    try:
        todas = aba.get_all_values()
    except Exception as e:
        log.error(f"❌ Erro ao ler aba '{ABA_PERFORMANCE}': {e}")
        return [], False

    if len(todas) < 2:
        log.info(f"📋 Aba '{ABA_PERFORMANCE}' vazia ou só com cabeçalho")
        return [], True

    # Linha 1 = headers reais da planilha (não confiamos cegamente nos nossos)
    headers_reais = [h.strip() for h in todas[0]]
    log.debug(f"Headers detectados: {headers_reais}")

    posts = []
    for offset, row in enumerate(todas[1:], start=2):  # start=2 porque linha 1 é header
        while len(row) < len(headers_reais):
            row.append("")
        post = {h: row[i].strip() for i, h in enumerate(headers_reais)}
        post["_linha"] = offset
        # Pula linhas sem Produto
        if not post.get("Produto"):
            continue
        posts.append(post)

    log.info(f"📊 {len(posts)} post(s) com produto na aba Performance_Posts")
    return posts, True


# =================================================================
# AGREGAÇÃO DE APRENDIZADOS
# =================================================================

def _agregar_aprendizados(posts_processados: list[dict]) -> dict:
    """
    Gera aprendizados a partir de posts já com score calculado.

    Returns:
        {
            "melhor_nicho":         str | None,
            "melhor_produto":       str | None,
            "melhor_hook":          str | None,
            "score_medio_geral":    float,
            "hashtags_top_bons":    list[str],
            "nichos_fracos":        list[str],
            "ranking_nichos":       list[dict],  ← debug/transparência
            "amostra_insuficiente": bool,
        }
    """
    if not posts_processados:
        return {
            "melhor_nicho":         None,
            "melhor_produto":       None,
            "melhor_hook":          None,
            "score_medio_geral":    0.0,
            "hashtags_top_bons":    [],
            "nichos_fracos":        [],
            "ranking_nichos":       [],
            "amostra_insuficiente": True,
        }

    # ── Score médio geral ─────────────────────────────────────────
    score_medio = sum(p["Score_Performance"] for p in posts_processados) / len(posts_processados)

    # ── Agrupar por nicho (média ponderada exige ≥ MIN posts) ──────
    por_nicho = {}
    for p in posts_processados:
        nicho = (p.get("Nicho") or "").strip() or "(sem nicho)"
        por_nicho.setdefault(nicho, []).append(p)

    ranking_nichos = []
    for nicho, lista in por_nicho.items():
        media_nicho = sum(p["Score_Performance"] for p in lista) / len(lista)
        ranking_nichos.append({
            "nicho":      nicho,
            "n_posts":    len(lista),
            "score_medio": round(media_nicho, 1),
            "elegivel":   len(lista) >= MIN_POSTS_PARA_RANKING,
        })
    ranking_nichos.sort(key=lambda x: x["score_medio"], reverse=True)

    elegiveis = [r for r in ranking_nichos if r["elegivel"]]
    melhor_nicho = elegiveis[0]["nicho"] if elegiveis else None

    # Nichos fracos: dos elegíveis, os com score médio < limite "Médio"
    nichos_fracos = [r["nicho"] for r in elegiveis if r["score_medio"] < 25]

    # ── Melhor produto: top score individual ───────────────────────
    posts_ord = sorted(posts_processados, key=lambda p: p["Score_Performance"], reverse=True)
    melhor_produto = posts_ord[0].get("Produto") if posts_ord else None
    melhor_hook    = posts_ord[0].get("Hook") if posts_ord else None

    # ── Hashtags frequentes em posts bons ──────────────────────────
    posts_bons = [p for p in posts_processados if p["Score_Performance"] >= SCORE_MINIMO_BOM]
    contador_tags = Counter()
    for p in posts_bons:
        for tag in _extrair_hashtags(p.get("Hashtags", "")):
            contador_tags[tag] += 1
    hashtags_top = [tag for tag, _ in contador_tags.most_common(TOP_HASHTAGS_N)]

    amostra_insuficiente = (
        len(posts_processados) < 3
        or len(posts_bons) < 3
        or not elegiveis
    )

    return {
        "melhor_nicho":         melhor_nicho,
        "melhor_produto":       melhor_produto,
        "melhor_hook":          melhor_hook,
        "score_medio_geral":    round(score_medio, 1),
        "hashtags_top_bons":    hashtags_top,
        "nichos_fracos":        nichos_fracos,
        "ranking_nichos":       ranking_nichos,
        "amostra_insuficiente": amostra_insuficiente,
        "total_posts_bons":     len(posts_bons),
    }


# =================================================================
# FUNÇÃO PRINCIPAL — ANÁLISE
# =================================================================

def analisar_performance_posts() -> dict:
    """
    Lê a aba Performance_Posts, calcula scores, agrega aprendizados.
    Salva resumo em shared/content_plans/performance_resumo.json.

    Returns:
        {
            "sucesso":              bool,
            "fonte":                "planilha" | "fallback_vazio",
            "total_posts":          int,
            "distribuicao":         {"Excelente": int, "Bom": int, ...},
            "score_medio_geral":    float,
            "aprendizados":         dict,
            "timestamp":            str,
        }
    """
    log.info("═" * 60)
    log.info("📊 PERFORMANCE AGENT — Iniciando análise")
    log.info("═" * 60)

    posts_raw, conectou = _ler_posts_da_planilha()

    if not conectou:
        log.warning("⚠️ Planilha indisponível — salvando fallback local vazio")
        return _finalizar_fallback("Planilha indisponível ou erro de conexão")

    # ── Calcular score de cada post ───────────────────────────────
    posts_processados = []
    distribuicao = {"Excelente": 0, "Bom": 0, "Médio": 0, "Fraco": 0}

    for post in posts_raw:
        score = calcular_score(post)
        rotulo = classificar_score(score)
        post["Score_Performance"] = score
        post["_classificacao"]    = rotulo
        distribuicao[rotulo]     += 1
        posts_processados.append(post)

    if posts_processados:
        log.info(
            f"📈 Distribuição: "
            f"Excelente={distribuicao['Excelente']} | "
            f"Bom={distribuicao['Bom']} | "
            f"Médio={distribuicao['Médio']} | "
            f"Fraco={distribuicao['Fraco']}"
        )

    # ── Aprendizados ─────────────────────────────────────────────
    aprendizados = _agregar_aprendizados(posts_processados)

    if aprendizados.get("amostra_insuficiente"):
        log.warning(
            f"⚠️ Amostra pequena: {len(posts_processados)} post(s), "
            f"{aprendizados.get('total_posts_bons', 0)} bom(ns). "
            f"Aprendizados podem ser pouco confiáveis."
        )
    else:
        log.info(f"✨ Melhor nicho:    {aprendizados['melhor_nicho']}")
        log.info(f"✨ Melhor produto:  {aprendizados['melhor_produto']}")
        log.info(f"✨ Melhor hook:     {(aprendizados['melhor_hook'] or '')[:60]}...")
        log.info(f"✨ Score médio:     {aprendizados['score_medio_geral']}")
        if aprendizados["hashtags_top_bons"]:
            log.info(f"✨ Hashtags top:    {', '.join(aprendizados['hashtags_top_bons'][:5])}")

    # ── Resumo final ─────────────────────────────────────────────
    resumo = {
        "sucesso":           True,
        "fonte":             "planilha",
        "total_posts":       len(posts_processados),
        "distribuicao":      distribuicao,
        "score_medio_geral": aprendizados["score_medio_geral"],
        "aprendizados":      aprendizados,
        "timestamp":         time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    _salvar_resumo(resumo)
    _atualizar_state(aprendizados)

    log.info("═" * 60)
    log.info(f"✅ Performance Agent concluído: {len(posts_processados)} post(s) analisados")
    log.info("═" * 60)

    return resumo


# =================================================================
# REGISTRO DE POST NOVO NA ABA
# =================================================================

def registrar_post_planejado_no_performance(post_info: dict) -> dict:
    """
    Adiciona uma nova linha na aba Performance_Posts com métricas zeradas.

    Chamado pelo orquestrador quando um post é preparado/postado.
    Por enquanto, métricas (Views, Curtidas, etc.) ficam zeradas — o
    operador (ou um futuro agente de coleta) preenche depois.

    Args:
        post_info: dict com chaves:
            - produto, nicho, plataforma
            - hook, legenda, hashtags
            - video_path, status_postagem

    Returns:
        {
            "sucesso":   bool,
            "fonte":     "planilha" | "fallback_local",
            "linha":     int | None,
            "mensagem":  str
        }
    """
    log.info(f"📝 Registrando post no Performance: '{post_info.get('produto', '?')[:40]}'")

    # Monta a linha respeitando a ordem dos HEADERS_PERFORMANCE
    linha = [
        time.strftime("%Y-%m-%d %H:%M:%S"),               # Data
        post_info.get("produto", ""),                     # Produto
        post_info.get("nicho", ""),                       # Nicho
        post_info.get("plataforma", "TikTok"),            # Plataforma
        post_info.get("hook", ""),                        # Hook
        post_info.get("legenda", ""),                     # Legenda
        post_info.get("hashtags", ""),                    # Hashtags
        post_info.get("video_path", ""),                  # Video_Path
        post_info.get("status_postagem", "Preparado"),    # Status_Postagem
        0, 0, 0, 0, 0, 0,                                  # métricas zeradas
        0,                                                 # Score_Performance inicial
        "",                                                # Aprendizado (preenche depois)
    ]

    aba, _ = _conectar_aba_performance()
    if aba is None:
        log.warning("⚠️ Planilha indisponível — salvando registro em fallback local")
        return _registrar_em_fallback(post_info, linha)

    try:
        aba.append_row(linha)
        log.info(f"  ✅ Linha adicionada na aba Performance_Posts")
        return {
            "sucesso":  True,
            "fonte":    "planilha",
            "linha":    None,  # gspread não retorna número da linha em append_row v6
            "mensagem": "Post registrado em Performance_Posts",
        }
    except Exception as e:
        log.error(f"❌ Falha ao escrever na planilha: {e}")
        return _registrar_em_fallback(post_info, linha)


# =================================================================
# FALLBACK LOCAL
# =================================================================

def _registrar_em_fallback(post_info: dict, linha: list) -> dict:
    """Salva o registro em shared/content_plans/performance_local.json."""
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        caminho = PLANS_DIR / "performance_local.json"
        dados = []
        if caminho.exists():
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    dados = json.load(f)
            except Exception:
                dados = []
        registro = {h: linha[i] for i, h in enumerate(HEADERS_PERFORMANCE) if i < len(linha)}
        registro["_motivo_fallback"] = "Planilha indisponível"
        dados.append(registro)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        log.info(f"  💾 Fallback salvo em {caminho} ({len(dados)} registro(s))")
        return {
            "sucesso":  True,
            "fonte":    "fallback_local",
            "linha":    None,
            "mensagem": f"Salvo em fallback local: {caminho.name}",
        }
    except Exception as e:
        return {
            "sucesso":  False,
            "fonte":    None,
            "linha":    None,
            "mensagem": f"Falha total: nem planilha nem fallback funcionaram: {e}",
        }


def _finalizar_fallback(motivo: str) -> dict:
    """Quando análise não conseguiu nem ler planilha."""
    resumo = {
        "sucesso":           False,
        "fonte":             "fallback_vazio",
        "motivo":            motivo,
        "total_posts":       0,
        "distribuicao":      {"Excelente": 0, "Bom": 0, "Médio": 0, "Fraco": 0},
        "score_medio_geral": 0.0,
        "aprendizados":      {},
        "timestamp":         time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _salvar_resumo(resumo)
    return resumo


def _salvar_resumo(resumo: dict):
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        caminho = PLANS_DIR / "performance_resumo.json"
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(resumo, f, ensure_ascii=False, indent=2)
        log.info(f"💾 Resumo salvo: {caminho}")
    except Exception as e:
        log.warning(f"⚠️ Não consegui salvar resumo: {e}")


def _atualizar_state(aprendizados: dict):
    """Persiste os aprendizados no state_manager pra outros agentes consumirem."""
    try:
        from memory.state_manager import atualizar_varios
        atualizar_varios({
            "estado_atual":         "performance_analisada",
            "melhor_nicho":         aprendizados.get("melhor_nicho") or "",
            "melhor_hook":          aprendizados.get("melhor_hook") or "",
            "melhor_produto":       aprendizados.get("melhor_produto") or "",
            "ultimo_score_medio":   aprendizados.get("score_medio_geral", 0),
            "hashtags_top_bons":    aprendizados.get("hashtags_top_bons", []),
            "nichos_fracos":        aprendizados.get("nichos_fracos", []),
            "performance_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        log.info(f"💾 State atualizado com aprendizados de performance")
    except Exception as e:
        log.warning(f"⚠️ Não consegui atualizar state: {e}")


# =================================================================
# TESTE VIA TERMINAL
# =================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  📊 Performance Agent v1 — Teste")
    print("=" * 60)

    resultado = analisar_performance_posts()

    print(f"\n{'─' * 60}")
    print(f"  📋 RESULTADO")
    print(f"{'─' * 60}")
    icone = "✅" if resultado["sucesso"] else "⚠️"
    print(f"  {icone} Sucesso:              {resultado['sucesso']}")
    print(f"  📂 Fonte:                {resultado.get('fonte', '?')}")
    print(f"  📊 Total de posts:       {resultado['total_posts']}")
    print(f"  📈 Score médio geral:    {resultado['score_medio_geral']}")

    dist = resultado.get("distribuicao", {})
    if any(dist.values()):
        print(f"\n  Distribuição:")
        for k, v in dist.items():
            if v > 0:
                print(f"    {k}: {v} post(s)")

    apr = resultado.get("aprendizados", {})
    if apr and not apr.get("amostra_insuficiente"):
        print(f"\n  ✨ APRENDIZADOS")
        print(f"     Melhor nicho:     {apr.get('melhor_nicho', '?')}")
        print(f"     Melhor produto:   {(apr.get('melhor_produto') or '?')[:50]}")
        print(f"     Melhor hook:      {(apr.get('melhor_hook') or '?')[:60]}")
        if apr.get("hashtags_top_bons"):
            print(f"     Top hashtags:     #{', #'.join(apr['hashtags_top_bons'][:5])}")
        if apr.get("nichos_fracos"):
            print(f"     Nichos fracos:    {', '.join(apr['nichos_fracos'])}")
    elif apr.get("amostra_insuficiente"):
        print(f"\n  ⚠️ Amostra insuficiente para aprendizados confiáveis")
        print(f"     (precisa de pelo menos 3 posts + alguns 'Bons')")

    if resultado.get("motivo"):
        print(f"\n  💬 {resultado['motivo']}")

    print(f"\n  💾 Resumo: shared/content_plans/performance_resumo.json")
    print("=" * 60)