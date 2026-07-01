# agents/pipeline_planejar_conteudo.py
# Pipeline de planejamento de conteúdo do AgenteIA (Jarvis)
#
# Conecta automaticamente:
#   1. product_classifier → preenche Nicho/Prioridade na fila
#   2. product_agent      → escolhe o melhor produto
#   3. content_planner    → gera plano criativo completo
#
# Não posta, não executa workflow, não cria vídeo.
# Apenas planeja e salva o resultado na planilha e no state.
#
# Uso:
#   from agents.pipeline_planejar_conteudo import executar_pipeline_planejamento
#   resultado = executar_pipeline_planejamento()

import json
import time
from pathlib import Path

from shared.logger import get_logger

log = get_logger(__name__)

PLANS_DIR = Path(__file__).parent.parent / "shared" / "content_plans"


# =================================================================
# DETECÇÃO DE HEADERS (reutilizado de product_agent/classifier)
# =================================================================

def _detectar_linha_header(todas: list[list[str]]) -> tuple[list[str], int]:
    for idx, row in enumerate(todas):
        normalized = [str(h).strip().lower() for h in row]
        if "produto" in normalized and "status" in normalized:
            return normalized, idx + 1
    return [str(h).strip().lower() for h in todas[0]], 1


def _encontrar_coluna(headers: list[str], *nomes) -> int:
    for nome in nomes:
        for i, h in enumerate(headers):
            if h == nome.lower().strip():
                return i + 1
    return -1


# =================================================================
# ATUALIZAR PLANILHA COM O PLANO
# =================================================================

def _atualizar_planilha_com_plano(linha: int, plano: dict) -> bool:
    """
    Atualiza a linha da Fila_de_Postagem com o plano gerado.
    Só sobrescreve campos vazios, exceto Status que vira 'Planejado'.
    """
    try:
        from memory.sheets_engine import _aba, ABA_FILA
        aba = _aba(ABA_FILA)
        todas = aba.get_all_values()

        if len(todas) < 2:
            log.warning("Planilha vazia — não foi possível atualizar")
            return False

        headers, _ = _detectar_linha_header(todas)

        col_roteiro  = _encontrar_coluna(headers, "roteiro")
        col_legenda  = _encontrar_coluna(headers, "legenda")
        col_cta      = _encontrar_coluna(headers, "cta")
        col_hashtags = _encontrar_coluna(headers, "hashtags")
        col_status   = _encontrar_coluna(headers, "status")

        # Lê valores atuais da linha para não sobrescrever
        row_atual = todas[linha - 1] if linha - 1 < len(todas) else []
        while len(row_atual) < len(headers):
            row_atual.append("")

        def _celula_vazia(col_idx: int) -> bool:
            if col_idx == -1:
                return False
            return not row_atual[col_idx - 1].strip()

        atualizados = []

        if col_roteiro != -1 and _celula_vazia(col_roteiro):
            roteiro = plano.get("roteiro", "")[:49000]
            aba.update_cell(linha, col_roteiro, roteiro)
            atualizados.append("Roteiro")

        if col_legenda != -1 and _celula_vazia(col_legenda):
            aba.update_cell(linha, col_legenda, plano.get("legenda", ""))
            atualizados.append("Legenda")

        if col_cta != -1 and _celula_vazia(col_cta):
            aba.update_cell(linha, col_cta, plano.get("cta", ""))
            atualizados.append("CTA")

        if col_hashtags != -1 and _celula_vazia(col_hashtags):
            aba.update_cell(linha, col_hashtags, plano.get("hashtags", ""))
            atualizados.append("Hashtags")

        # Status sempre atualiza para Planejado
        if col_status != -1:
            aba.update_cell(linha, col_status, "Planejado")
            atualizados.append("Status→Planejado")

        log.info(f"📝 Linha {linha} atualizada: {atualizados}")
        return True

    except Exception as e:
        log.warning(f"⚠️ Falha ao atualizar planilha: {e}")
        return False


# =================================================================
# ATUALIZAR STATE
# =================================================================

def _atualizar_state(produto: dict, plano: dict):
    """Registra resultado do pipeline no state_manager."""
    try:
        from memory.state_manager import atualizar_varios
        atualizar_varios({
            "estado_atual":                  "conteudo_planejado",
            "produto_atual":                 produto.get("produto", ""),
            "nicho_atual":                   produto.get("nicho", plano.get("nicho", "")),
            "plataforma_atual":              produto.get("plataforma", "TikTok"),
            "linha_planilha":                produto.get("linha_planilha"),
            "video_path_sugerido":           plano.get("video_path_sugerido", ""),
            "legenda_planejada":             plano.get("legenda", ""),
            "hashtags_planejadas":           plano.get("hashtags", ""),
            "ultimo_pipeline_planejamento":  time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        log.info("💾 State atualizado: estado=conteudo_planejado")
    except Exception as e:
        log.warning(f"⚠️ Não foi possível atualizar state: {e}")


# =================================================================
# SALVAR RESUMO LOCAL
# =================================================================

def _salvar_resumo(resultado: dict):
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    caminho = PLANS_DIR / "pipeline_planejamento_resultado.json"
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    log.info(f"💾 Resumo pipeline salvo: {caminho}")


# =================================================================
# PIPELINE PRINCIPAL
# =================================================================

def executar_pipeline_planejamento() -> dict:
    """
    Pipeline completo de planejamento de conteúdo:
        1. Classifica fila (nicho + prioridade)
        2. Seleciona melhor produto
        3. Gera plano criativo
        4. Atualiza planilha e state

    Não posta, não executa workflow, não cria vídeo.

    Returns:
        {
            "sucesso":         bool,
            "produto":         dict,
            "plano":           dict,
            "classificacao":   dict,
            "linha_planilha":  int | None,
            "status_final":    str,
            "fonte_plano":     str,
        }
    """
    log.info("=" * 50)
    log.info("🎬 PIPELINE DE PLANEJAMENTO — Iniciando")
    log.info("=" * 50)

    resultado = {
        "sucesso":        False,
        "produto":        {},
        "plano":          {},
        "classificacao":  {},
        "linha_planilha": None,
        "status_final":   "",
        "fonte_plano":    "",
    }

    # ── ETAPA 1: Classificar fila ──────────────────────────────────
    log.info("\n📌 ETAPA 1/3 — Classificar fila de produtos")
    try:
        from agents.product_classifier import classificar_fila_produtos
        classificacao = classificar_fila_produtos()
        resultado["classificacao"] = classificacao
        log.info(
            f"   ✅ Classificação: {classificacao.get('linhas_atualizadas', 0)} atualizadas "
            f"de {classificacao.get('linhas_analisadas', 0)} analisadas"
        )
    except Exception as e:
        log.warning(f"   ⚠️ Classificação falhou (continuando): {e}")
        resultado["classificacao"] = {"sucesso": False, "erro": str(e)}

    # ── ETAPA 2: Selecionar produto ────────────────────────────────
    log.info("\n📌 ETAPA 2/3 — Selecionar melhor produto")
    try:
        from agents.product_agent import selecionar_produto_para_conteudo
        produto = selecionar_produto_para_conteudo()
        resultado["produto"] = produto
        resultado["linha_planilha"] = produto.get("linha_planilha")
        log.info(
            f"   ✅ Selecionado: '{produto['produto']}' "
            f"({produto.get('nicho', '?')} | {produto.get('plataforma', '?')} | "
            f"linha={produto.get('linha_planilha', '?')})"
        )
    except Exception as e:
        log.error(f"   ❌ Seleção de produto falhou: {e}")
        resultado["status_final"] = f"Falha na seleção: {e}"
        _salvar_resumo(resultado)
        return resultado

    # ── ETAPA 3: Gerar plano criativo ──────────────────────────────
    log.info("\n📌 ETAPA 3/3 — Gerar plano de conteúdo")
    try:
        from agents.content_planner import gerar_plano_conteudo
        plano = gerar_plano_conteudo(produto)
        resultado["plano"] = plano
        resultado["fonte_plano"] = plano.get("fonte", "desconhecido")
        log.info(
            f"   ✅ Plano gerado ({plano.get('fonte', '?')}) — "
            f"hook: '{plano.get('hook', '')[:50]}...'"
        )
    except Exception as e:
        log.error(f"   ❌ Geração de plano falhou: {e}")
        resultado["status_final"] = f"Falha no plano: {e}"
        _salvar_resumo(resultado)
        return resultado

    # ── PÓS: Atualizar planilha ───────────────────────────────────
    linha = produto.get("linha_planilha")
    if linha:
        log.info(f"\n📝 Atualizando planilha — linha {linha}")
        planilha_ok = _atualizar_planilha_com_plano(linha, plano)
        resultado["status_final"] = "Planejado" if planilha_ok else "Planejado (planilha falhou)"
    else:
        log.info("\n📝 Sem linha_planilha — apenas planejamento local")
        resultado["status_final"] = "Planejado (local)"

    # ── PÓS: Atualizar state ──────────────────────────────────────
    _atualizar_state(produto, plano)

    # ── PÓS: Salvar resumo ────────────────────────────────────────
    resultado["sucesso"] = True
    resultado["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _salvar_resumo(resultado)

    log.info("\n" + "=" * 50)
    log.info(f"✅ PIPELINE CONCLUÍDO — '{produto['produto']}' → {resultado['fonte_plano']}")
    log.info(f"   Status: {resultado['status_final']}")
    log.info("=" * 50)

    return resultado


# =================================================================
# TESTE VIA TERMINAL
# =================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  🎬 Pipeline de Planejamento — Teste")
    print("=" * 60)

    resultado = executar_pipeline_planejamento()

    produto = resultado.get("produto", {})
    plano   = resultado.get("plano", {})

    print(f"\n{'─' * 60}")
    print(f"📊 Resultado: {'✅ Sucesso' if resultado['sucesso'] else '❌ Falha'}")
    print(f"\n📦 Produto:    {produto.get('produto', '?')}")
    print(f"🏷️  Nicho:      {produto.get('nicho', '?')}")
    print(f"📱 Plataforma: {produto.get('plataforma', '?')}")
    print(f"📋 Linha:      {resultado.get('linha_planilha', '?')}")
    print(f"📡 Fonte:      {resultado.get('fonte_plano', '?')}")

    print(f"\n🎣 Hook:       {plano.get('hook', '?')[:60]}")
    print(f"📜 Roteiro:    {plano.get('roteiro', '?')[:80]}...")
    print(f"📝 Legenda:    {plano.get('legenda', '?')[:60]}")
    print(f"#️⃣  Hashtags:   {plano.get('hashtags', '?')[:60]}")
    print(f"📢 CTA:        {plano.get('cta', '?')}")
    print(f"🎥 Vídeo:      {plano.get('video_path_sugerido', '?')}")

    print(f"\n📊 Status:     {resultado.get('status_final', '?')}")

    classif = resultado.get("classificacao", {})
    if classif.get("linhas_atualizadas"):
        print(f"🏷️  Classif:    {classif['linhas_atualizadas']} produtos classificados")

    print(f"\n💾 Salvo em: shared/content_plans/pipeline_planejamento_resultado.json")
    print("=" * 60)