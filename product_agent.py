# agents/product_agent.py
# Agente de seleção de produto do AgenteIA (Jarvis)
#
# Responsabilidade única: escolher o próximo produto da fila
# para virar conteúdo. Não posta, não executa, não chama Gemini.
#
# Fontes:
#   1. Google Sheets (Fila_de_Postagem) — prioridade
#   2. Fallback local — se planilha falhar ou estiver vazia
#
# Uso:
#   from agents.product_agent import selecionar_produto_para_conteudo
#   produto = selecionar_produto_para_conteudo()

import json
import time
from pathlib import Path

from shared.logger import get_logger

log = get_logger(__name__)

PLANS_DIR = Path(__file__).parent.parent / "shared" / "content_plans"

# Produto fallback quando planilha está vazia ou offline
FALLBACK_PRODUTO = {
    "produto":        "Mini Aspirador de Teclado",
    "nicho":          "Casa/Tech",
    "plataforma":     "TikTok",
    "link":           "",
    "comissao":       "",
    "linha_planilha": None,
    "status":         "Fallback",
    "fonte":          "fallback_local",
}


# =================================================================
# INFERÊNCIA DE NICHO
# =================================================================

_NICHO_KEYWORDS = {
    "Saúde/Fitness":  ("massageador", "cervical", "muscular", "fitness", "yoga", "treino",
                       "elástico", "caneleira", "whey", "pistola", "grip", "corda"),
    "Beleza":         ("maquiagem", "facial", "skincare", "cílios", "esponja", "sérum",
                       "escova", "alisadora", "depilador", "unha", "jade", "patch"),
    "Casa":           ("organizador", "pia", "banheiro", "led", "casa", "cortina", "lâmpada",
                       "umidificador", "purificador", "fita", "adesivo", "prateleira"),
    "Cozinha":        ("cozinha", "legumes", "alho", "faca", "balança", "tempero", "gelo",
                       "garrafa", "seladora", "descascador"),
    "Tecnologia":     ("fone", "bluetooth", "usb", "hub", "mouse", "webcam", "carregador",
                       "projetor", "teclado", "smartwatch", "power bank"),
    "Pets":           ("gato", "cachorro", "pet", "ração", "coleira", "mordedor"),
    "Maternidade":    ("bebê", "mamadeira", "mordedor", "babá", "berço", "nasal"),
    "Moda Feminina":  ("cinto modelador", "bolsa", "meia-calça", "presilha", "chinelo",
                       "óculos", "soutien", "tênis"),
    "Organização":    ("organizador", "etiquetadora", "caixa", "porta-sapatos", "separador"),
}

def _inferir_nicho(produto_nome: str) -> str:
    """Infere nicho pelo nome do produto usando keywords."""
    nome_lower = produto_nome.lower()
    for nicho, keywords in _NICHO_KEYWORDS.items():
        if any(kw in nome_lower for kw in keywords):
            return nicho
    return "Geral"


# =================================================================
# LEITURA DA PLANILHA
# =================================================================

def _detectar_linha_header(todas: list[list[str]]) -> tuple[list[str], int]:
    """
    Detecta automaticamente a linha de cabeçalho na planilha.
    Procura uma linha que contenha pelo menos 'Produto' e 'Status'.
    Retorna (headers_normalizados, indice_primeira_linha_dados).

    Cobre:
        - Planilha com título geral na linha 1 e headers na linha 2
        - Planilha com headers direto na linha 1
    """
    for idx, row in enumerate(todas):
        normalized = [str(h).strip().lower() for h in row]
        if "produto" in normalized and "status" in normalized:
            return normalized, idx + 1
    # Fallback: assume linha 0 como header
    return [str(h).strip().lower() for h in todas[0]], 1


def _buscar_candidatos_sheets() -> list[dict]:
    """
    Lê a Fila_de_Postagem e retorna candidatos com Status Pendente ou Gerado.
    Retorna lista vazia se planilha falhar.
    """
    try:
        from memory.sheets_engine import _aba, ABA_FILA
        aba = _aba(ABA_FILA)
        todas = aba.get_all_values()

        if len(todas) < 2:
            log.info("📋 Planilha vazia ou só cabeçalho")
            return []

        headers, start_idx = _detectar_linha_header(todas)
        log.info(f"📋 Headers detectados na linha {start_idx} da planilha: {headers[:5]}...")
        candidatos = []

        for i, row in enumerate(todas[start_idx:], start=start_idx + 1):
            # Garante colunas suficientes
            while len(row) < len(headers):
                row.append("")

            dados = {headers[j]: row[j].strip() for j in range(len(headers))}

            status = dados.get("status", "").strip()
            produto = dados.get("produto", "").strip()
            plataforma = dados.get("plataforma", "TikTok").strip() or "TikTok"

            if status.lower() not in ("pendente", "gerado"):
                continue
            if not produto:
                continue

            nicho_raw = (
                dados.get("nicho", "").strip()
                or dados.get("categoria", "").strip()
                or dados.get("segmento", "").strip()
                or _inferir_nicho(produto)
            )

            candidatos.append({
                "produto":        produto,
                "nicho":          nicho_raw,
                "plataforma":     plataforma,
                "link":           dados.get("link", dados.get("link_post", "")).strip(),
                "comissao":       dados.get("comissao", dados.get("comissão", "")).strip(),
                "prioridade":     dados.get("prioridade", "").strip(),
                "linha_planilha": i,
                "status":         status,
                "fonte":          "sheets",
            })

        log.info(f"📋 {len(candidatos)} candidato(s) encontrado(s) na planilha")
        return candidatos

    except Exception as e:
        log.warning(f"⚠️ Planilha indisponível: {e}")
        return []


# =================================================================
# SCORING / PRIORIZAÇÃO
# =================================================================

def _calcular_score(candidato: dict) -> int:
    """
    Calcula score de prioridade para um candidato.
    Quanto maior, mais prioritário.
    """
    score = 0

    # Status: Pendente vale mais que Gerado
    if candidato["status"].lower() == "pendente":
        score += 10
    elif candidato["status"].lower() == "gerado":
        score += 5

    # Plataforma TikTok tem prioridade
    if candidato["plataforma"].lower() == "tiktok":
        score += 5

    # Campos preenchidos valem pontos
    if candidato.get("nicho"):
        score += 3
    if candidato.get("link"):
        score += 3
    if candidato.get("comissao"):
        score += 3

    # Prioridade explícita na planilha
    prio = candidato.get("prioridade", "").lower()
    if prio in ("alta", "high", "urgente"):
        score += 20
    elif prio in ("media", "medium", "normal"):
        score += 5
    elif prio in ("baixa", "low"):
        score += 1

    return score


# =================================================================
# SALVAR E REGISTRAR
# =================================================================

def _salvar_produto(produto: dict) -> Path:
    """Salva o produto selecionado em shared/content_plans/."""
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    caminho = PLANS_DIR / "produto_selecionado.json"
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(produto, f, ensure_ascii=False, indent=2)
    log.info(f"💾 Produto salvo: {caminho}")
    return caminho


def _registrar_no_state(produto: dict):
    """Atualiza state_manager com o produto selecionado."""
    try:
        from memory.state_manager import atualizar_varios
        atualizar_varios({
            "produto_atual":    produto["produto"],
            "plataforma_atual": produto["plataforma"],
            "linha_planilha":   produto.get("linha_planilha"),
            "estado_atual":     "planejando_conteudo",
        })
        log.info(f"📝 State atualizado: produto='{produto['produto']}' | estado=planejando_conteudo")
    except Exception as e:
        log.warning(f"Não foi possível atualizar state: {e}")


# =================================================================
# FUNÇÃO PRINCIPAL
# =================================================================

def selecionar_produto_para_conteudo() -> dict:
    """
    Seleciona o próximo produto da fila para virar conteúdo.

    Prioridade:
        1. Planilha (Pendente > Gerado, TikTok, campos preenchidos)
        2. Fallback local se planilha vazia ou offline

    Returns:
        dict com produto selecionado:
        {
            "produto":        str,
            "nicho":          str,
            "plataforma":     str,
            "link":           str,
            "comissao":       str,
            "linha_planilha": int | None,
            "status":         str,
            "fonte":          "sheets" | "fallback_local",
        }
    """
    log.info("🔍 Product Agent — selecionando próximo produto...")

    # Tenta planilha
    candidatos = _buscar_candidatos_sheets()

    if candidatos:
        # Ordena por score (maior primeiro)
        candidatos.sort(key=_calcular_score, reverse=True)

        selecionado = candidatos[0]
        score = _calcular_score(selecionado)

        log.info(
            f"🏆 Selecionado: '{selecionado['produto']}' "
            f"(score={score} | status={selecionado['status']} | "
            f"plataforma={selecionado['plataforma']} | linha={selecionado['linha_planilha']})"
        )

        if len(candidatos) > 1:
            log.info(f"   Outros candidatos: {[c['produto'] for c in candidatos[1:5]]}")
    else:
        selecionado = FALLBACK_PRODUTO.copy()
        log.warning("⚠️ Nenhum produto na planilha — usando fallback local")

    # Metadados
    selecionado["timestamp_selecao"] = time.strftime("%Y-%m-%d %H:%M:%S")

    # Salva e registra
    _salvar_produto(selecionado)
    _registrar_no_state(selecionado)

    log.info(f"✅ Product Agent concluído: '{selecionado['produto']}' ({selecionado['fonte']})")
    return selecionado


# =================================================================
# TESTE VIA TERMINAL
# =================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  🔍 Product Agent — Teste")
    print("=" * 60)

    produto = selecionar_produto_para_conteudo()

    print(f"\n📦 Produto:    {produto['produto']}")
    print(f"🏷️  Nicho:      {produto.get('nicho', '—')}")
    print(f"📱 Plataforma: {produto['plataforma']}")
    print(f"🔗 Link:       {produto.get('link', '—') or '—'}")
    print(f"💰 Comissão:   {produto.get('comissao', '—') or '—'}")
    print(f"📊 Status:     {produto['status']}")
    print(f"📡 Fonte:      {produto['fonte']}")
    print(f"📋 Linha:      {produto.get('linha_planilha', '—')}")
    print(f"⏰ Seleção:    {produto.get('timestamp_selecao', '—')}")
    print(f"\n💾 Salvo em: shared/content_plans/produto_selecionado.json")
    print("=" * 60)