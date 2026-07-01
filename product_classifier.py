# agents/product_classifier.py
# Classificador de produtos do AgenteIA (Jarvis)
#
# Responsabilidade: ler Fila_de_Postagem e preencher automaticamente
# as colunas Nicho e Prioridade dos produtos que estiverem vazias.
#
# Não chama Gemini, não posta, não executa workflow.
# Apenas lê e atualiza a planilha.
#
# Uso:
#   from agents.product_classifier import classificar_fila_produtos
#   resultado = classificar_fila_produtos()

import json
import time
from pathlib import Path

from shared.logger import get_logger

log = get_logger(__name__)

PLANS_DIR = Path(__file__).parent.parent / "shared" / "content_plans"


# =================================================================
# INFERÊNCIA DE NICHO POR KEYWORDS
# =================================================================

_NICHO_KEYWORDS = {
    "Saúde/Fitness": (
        "massageador", "cervical", "muscular", "fitness", "yoga", "treino",
        "elástico", "caneleira", "whey", "pistola", "grip", "corda",
        "esportivo", "oxímetro", "peso", "tapete yoga", "rolo massagem",
    ),
    "Beleza": (
        "maquiagem", "facial", "skincare", "cílios", "esponja", "sérum",
        "escova alisadora", "chapinha", "depilador", "unha", "jade", "patch",
        "vaporizador", "olheiras", "colágeno", "vitamina c", "hialurônico",
    ),
    "Casa": (
        "aspirador", "pia", "banheiro", "led", "cortina", "lâmpada",
        "umidificador", "purificador", "fita rgb", "adesivo vedante",
        "suporte notebook", "dispenser sabonete", "sensor movimento",
    ),
    "Cozinha": (
        "cozinha", "legumes", "alho", "faca", "balança", "tempero", "gelo",
        "garrafa térmica", "seladora", "descascador", "cortador", "espremedor",
    ),
    "Tecnologia": (
        "fone", "bluetooth", "usb", "hub", "mouse", "webcam", "carregador",
        "projetor", "teclado", "smartwatch", "power bank", "ring light",
        "cancelamento ruído", "hdmi",
    ),
    "Pets": (
        "gato", "cachorro", "pet", "ração", "coleira", "mordedor pet",
        "bebedouro fonte", "tira pelos", "brinquedo gato",
    ),
    "Maternidade": (
        "bebê", "mamadeira", "babá", "mordedor silicone", "nasal",
        "amamentação", "termômetro", "trava segurança", "protetor quina",
    ),
    "Moda Feminina": (
        "cinto modelador", "bolsa", "meia-calça", "presilha", "chinelo",
        "óculos", "soutien", "tênis chunky", "slim feminino",
    ),
    "Organização": (
        "organizador", "etiquetadora", "caixa empilhável", "porta-sapatos",
        "separador roupas", "prateleira flutuante", "cubo mala", "cortiça",
    ),
}


def inferir_nicho(produto_nome: str) -> str:
    """Infere nicho pelo nome do produto usando keywords."""
    nome_lower = produto_nome.lower()
    for nicho, keywords in _NICHO_KEYWORDS.items():
        if any(kw in nome_lower for kw in keywords):
            return nicho
    return "Geral"


# =================================================================
# SCORING DE POTENCIAL
# =================================================================

_KW_DOR      = ("resolve", "alívio", "segurança", "proteção", "limpeza", "ergon", "vedante", "trava")
_KW_VISUAL   = ("satisfying", "antes/depois", "demonstração", "visual", "wow", "transformação")
_KW_TREND    = ("viral", "trend", "tendência", "curiosidade", "aesthetic", "rgb", "led")
_KW_IMPULSO  = ("mini", "portátil", "compacto", "acessível", "kit", "usb", "recarregável")
_KW_APELO    = ("feminino", "beleza", "casa", "fitness", "skincare", "moda", "slim", "modelador")
_KW_GENERICO = ("genérico", "básico", "simples", "comum")

# Características por nicho que indicam alto potencial visual
_NICHO_BONUS = {
    "Beleza":         ("antes/depois fácil", 8),
    "Casa":           ("demonstração visual", 8),
    "Cozinha":        ("satisfying de cortar/limpar", 8),
    "Organização":    ("antes/depois gaveta", 8),
    "Tecnologia":     ("unboxing/setup", 5),
    "Saúde/Fitness":  ("demonstração exercício", 5),
}


def calcular_score(produto_nome: str, nicho: str = "") -> int:
    """Calcula score de potencial para vídeo curto de afiliado."""
    score = 0
    texto = f"{produto_nome} {nicho}".lower()

    if any(k in texto for k in _KW_DOR):
        score += 10
    if any(k in texto for k in _KW_VISUAL):
        score += 10
    if "antes/depois" in texto:
        score += 8
    if any(k in texto for k in _KW_IMPULSO):
        score += 8
    if any(k in texto for k in _KW_APELO):
        score += 5
    if any(k in texto for k in _KW_TREND):
        score += 5
    if any(k in texto for k in ("ticket baixo", "impulso", "acessível", "barato")):
        score += 5
    if any(k in texto for k in _KW_GENERICO):
        score -= 5

    # Bonus por nicho com alto potencial visual
    if nicho in _NICHO_BONUS:
        score += _NICHO_BONUS[nicho][1]

    return max(score, 0)


def score_para_prioridade(score: int) -> str:
    if score >= 25:
        return "alta"
    elif score >= 15:
        return "media"
    return "baixa"


# =================================================================
# DETECÇÃO DE HEADERS
# =================================================================

def _detectar_linha_header(todas: list[list[str]]) -> tuple[list[str], int]:
    """
    Detecta linha de cabeçalho que contenha 'Produto' e 'Status'.
    Retorna (headers_normalizados, indice_primeira_linha_dados).
    """
    for idx, row in enumerate(todas):
        normalized = [str(h).strip().lower() for h in row]
        if "produto" in normalized and "status" in normalized:
            return normalized, idx + 1
    return [str(h).strip().lower() for h in todas[0]], 1


def _encontrar_coluna(headers: list[str], *nomes) -> int:
    """
    Encontra índice (1-based, para gspread) de uma coluna pelos nomes possíveis.
    Retorna -1 se não encontrar.
    """
    for nome in nomes:
        nome_lower = nome.lower().strip()
        for i, h in enumerate(headers):
            if h == nome_lower:
                return i + 1  # gspread usa 1-based
    return -1


# =================================================================
# FUNÇÃO PRINCIPAL
# =================================================================

def classificar_fila_produtos() -> dict:
    """
    Lê Fila_de_Postagem e preenche Nicho e Prioridade automaticamente.
    Só atualiza células vazias — não sobrescreve ajuste manual.

    Returns:
        {
            "sucesso":             bool,
            "linhas_analisadas":   int,
            "linhas_atualizadas":  int,
            "ignoradas":           int,
            "colunas_ausentes":    list[str],
            "produtos":            list[dict],
        }
    """
    log.info("🏷️ Product Classifier — iniciando classificação da fila")

    produtos_classificados = []
    linhas_analisadas = 0
    linhas_atualizadas = 0
    ignoradas = 0
    colunas_ausentes = []

    try:
        from memory.sheets_engine import _aba, ABA_FILA
        aba = _aba(ABA_FILA)
        todas = aba.get_all_values()

        if len(todas) < 2:
            log.info("📋 Planilha vazia")
            return _resultado(True, 0, 0, 0, [], [])

        headers, start_idx = _detectar_linha_header(todas)
        log.info(f"📋 Headers na linha {start_idx}: {headers}")

        # Localiza colunas
        col_produto    = _encontrar_coluna(headers, "produto")
        col_status     = _encontrar_coluna(headers, "status")
        col_nicho      = _encontrar_coluna(headers, "nicho", "categoria", "segmento")
        col_prioridade = _encontrar_coluna(headers, "prioridade", "prio", "priority")

        if col_produto == -1 or col_status == -1:
            msg = "Colunas obrigatórias 'Produto' ou 'Status' não encontradas"
            log.error(f"❌ {msg}")
            return _resultado(False, 0, 0, 0, ["Produto", "Status"], [])

        if col_nicho == -1:
            colunas_ausentes.append("Nicho")
            log.warning("⚠️ Coluna 'Nicho' não encontrada — classificação de nicho será apenas local")

        if col_prioridade == -1:
            colunas_ausentes.append("Prioridade")
            log.warning("⚠️ Coluna 'Prioridade' não encontrada — classificação de prioridade será apenas local")

        if col_nicho == -1 and col_prioridade == -1:
            log.warning("⚠️ Nenhuma coluna para atualizar na planilha — apenas classificação local")

        # Processa cada linha
        for row_data in todas[start_idx:]:
            # Linha real na planilha (1-based)
            linha_planilha = start_idx + linhas_analisadas + 1

            while len(row_data) < len(headers):
                row_data.append("")

            dados = {headers[j]: row_data[j].strip() for j in range(len(headers))}

            produto_nome = dados.get("produto", dados.get(headers[col_produto - 1], "")).strip()
            status = dados.get("status", dados.get(headers[col_status - 1], "")).strip()

            if not produto_nome or status.lower() not in ("pendente", "gerado"):
                linhas_analisadas += 1
                ignoradas += 1
                continue

            linhas_analisadas += 1

            # Lê valores atuais
            nicho_atual = ""
            prio_atual = ""
            if col_nicho != -1 and col_nicho - 1 < len(row_data):
                nicho_atual = row_data[col_nicho - 1].strip()
            if col_prioridade != -1 and col_prioridade - 1 < len(row_data):
                prio_atual = row_data[col_prioridade - 1].strip()

            # Infere se vazio
            nicho_novo = nicho_atual or inferir_nicho(produto_nome)
            score = calcular_score(produto_nome, nicho_novo)
            prio_nova = prio_atual or score_para_prioridade(score)

            atualizado = False

            # Atualiza planilha se houver célula vazia para preencher
            if col_nicho != -1 and not nicho_atual:
                try:
                    aba.update_cell(linha_planilha, col_nicho, nicho_novo)
                    atualizado = True
                    log.info(f"  📝 Linha {linha_planilha}: Nicho = '{nicho_novo}'")
                except Exception as e:
                    log.warning(f"  ⚠️ Falha ao atualizar Nicho linha {linha_planilha}: {e}")

            if col_prioridade != -1 and not prio_atual:
                try:
                    aba.update_cell(linha_planilha, col_prioridade, prio_nova)
                    atualizado = True
                    log.info(f"  📝 Linha {linha_planilha}: Prioridade = '{prio_nova}' (score={score})")
                except Exception as e:
                    log.warning(f"  ⚠️ Falha ao atualizar Prioridade linha {linha_planilha}: {e}")

            if atualizado:
                linhas_atualizadas += 1
            elif nicho_atual and prio_atual:
                ignoradas += 1
                log.debug(f"  ↩ Linha {linha_planilha}: já classificado — '{produto_nome}'")

            produtos_classificados.append({
                "linha":      linha_planilha,
                "produto":    produto_nome,
                "nicho":      nicho_novo,
                "score":      score,
                "prioridade": prio_nova,
                "atualizado": atualizado,
                "nicho_era_vazio":      not nicho_atual,
                "prioridade_era_vazia": not prio_atual,
            })

    except Exception as e:
        log.error(f"❌ Erro ao classificar: {e}")
        return _resultado(False, linhas_analisadas, linhas_atualizadas, ignoradas,
                          colunas_ausentes, produtos_classificados)

    # Salva resumo local
    _salvar_resumo(produtos_classificados)

    log.info(
        f"✅ Classificação concluída: "
        f"{linhas_analisadas} analisadas → {linhas_atualizadas} atualizadas, "
        f"{ignoradas} ignoradas"
    )
    if colunas_ausentes:
        log.warning(f"⚠️ Colunas ausentes na planilha: {colunas_ausentes}")

    return _resultado(True, linhas_analisadas, linhas_atualizadas, ignoradas,
                      colunas_ausentes, produtos_classificados)


# =================================================================
# HELPERS
# =================================================================

def _resultado(sucesso, analisadas, atualizadas, ignoradas, colunas_ausentes, produtos):
    return {
        "sucesso":            sucesso,
        "linhas_analisadas":  analisadas,
        "linhas_atualizadas": atualizadas,
        "ignoradas":          ignoradas,
        "colunas_ausentes":   colunas_ausentes,
        "produtos":           produtos,
    }


def _salvar_resumo(produtos: list[dict]):
    """Salva classificação local para referência."""
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    caminho = PLANS_DIR / "classificacao_produtos.json"
    resumo = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(produtos),
        "produtos": produtos,
    }
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2)
    log.info(f"💾 Resumo salvo: {caminho}")


# =================================================================
# TESTE VIA TERMINAL
# =================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  🏷️ Product Classifier — Teste")
    print("=" * 60)

    resultado = classificar_fila_produtos()

    print(f"\n📊 Resumo:")
    print(f"   Sucesso:     {resultado['sucesso']}")
    print(f"   Analisadas:  {resultado['linhas_analisadas']}")
    print(f"   Atualizadas: {resultado['linhas_atualizadas']}")
    print(f"   Ignoradas:   {resultado['ignoradas']}")
    if resultado["colunas_ausentes"]:
        print(f"   ⚠️ Colunas ausentes: {resultado['colunas_ausentes']}")

    print(f"\n🏷️ Produtos classificados:")
    for p in resultado["produtos"]:
        flag = "📝" if p.get("atualizado") else "↩"
        print(
            f"   {flag} Linha {p['linha']:3d} | "
            f"[{p['prioridade']:5s} score={p['score']:2d}] "
            f"{p['produto'][:40]:40s} → {p['nicho']}"
        )

    print(f"\n💾 Salvo em: shared/content_plans/classificacao_produtos.json")
    print("=" * 60)