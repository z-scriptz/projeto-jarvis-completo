# agents/product_cleaner.py
# Limpador de fila do AgenteIA (Jarvis)
#
# Responsabilidade: detectar produtos duplicados na Fila_de_Postagem
# e organizá-los sem perder dados importantes.
#
# Modos:
#   "marcar"  (padrão) — marca duplicatas com Status="Duplicado" + observação
#                        na coluna Erro. NÃO apaga nada. Mantém a melhor linha
#                        como principal.
#   "remover"          — só remove duplicatas QUE ESTÃO VAZIAS e com status
#                        Pendente. Postado / Planejado / Preparado /
#                        Aguardando_Video são SEMPRE mantidas.
#
# Critério de duplicação:
#   1. Link_Post idêntico (quando ambos têm link)
#   2. Similaridade do nome do produto > 0.85 após normalização
#
# Critério para escolher a "linha principal" (a que fica):
#   1. Status Postado vence tudo
#   2. Planejado / Aguardando_Video / Preparado vencem
#   3. Maior prioridade (alta > media > baixa)
#   4. Mais campos preenchidos (Roteiro/Legenda/Hashtags)
#   5. Linha mais antiga (menor número de linha)
#
# Uso:
#   from agents.product_cleaner import limpar_produtos_duplicados
#   resultado = limpar_produtos_duplicados(modo="marcar")
#
# Teste via terminal:
#   python -m agents.product_cleaner

import json
import re
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from shared.logger import get_logger

log = get_logger(__name__)

PLANS_DIR = Path(__file__).parent.parent / "shared" / "content_plans"

# =================================================================
# CONFIGURAÇÃO
# =================================================================

# Limite de similaridade pra considerar duplicado
LIMITE_SIMILARIDADE = 0.85

# Status protegidos — nunca remover, mesmo no modo "remover"
STATUS_PROTEGIDOS = {
    "postado",
    "planejado",
    "preparado",
    "aguardando_video",
}

# Status que se beneficiam de ser linha principal (em ordem de prioridade)
STATUS_PRIORIDADE = [
    "postado",
    "planejado",
    "preparado",
    "aguardando_video",
    "gerado",
    "pendente",
    "duplicado",
    "erro",
]

# Termos genéricos a remover na normalização (não afetam identidade do produto)
TERMOS_GENERICOS = (
    "promocao", "promoção", "oferta", "kit", "novo", "original",
    "frete gratis", "frete grátis", "premium", "shopee", "amazon",
)

# Padrão pra remover emojis e outros símbolos não-letra
_PADRAO_EMOJI = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002700-\U000027BF"  # dingbats
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U00002600-\U000026FF"  # misc symbols
    "]+",
    flags=re.UNICODE,
)


# =================================================================
# NORMALIZAÇÃO
# =================================================================

def _normalizar_nome(nome: str) -> str:
    """
    Normaliza nome de produto pra comparação:
      - lowercase
      - remove acentos
      - remove emojis e símbolos
      - remove termos genéricos
      - colapsa espaços
    """
    if not nome:
        return ""

    # 1. Lowercase
    s = nome.lower()

    # 2. Remove acentos (NFKD + filtra combining marks)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))

    # 3. Remove emojis e símbolos especiais
    s = _PADRAO_EMOJI.sub(" ", s)

    # 4. Remove pontuação que não separa palavras (mantém - e espaços)
    s = re.sub(r"[^\w\s-]", " ", s)

    # 5. Remove termos genéricos
    for termo in TERMOS_GENERICOS:
        s = re.sub(rf"\b{re.escape(termo)}\b", " ", s)

    # 6. Colapsa espaços
    s = re.sub(r"\s+", " ", s).strip()

    return s


def _similaridade(nome_a: str, nome_b: str) -> float:
    """Retorna razão de similaridade entre dois nomes JÁ normalizados (0.0–1.0)."""
    if not nome_a or not nome_b:
        return 0.0
    return SequenceMatcher(None, nome_a, nome_b).ratio()


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
    """Retorna índice 1-based de uma coluna pelos nomes possíveis (-1 se não achar)."""
    for nome in nomes:
        nome_lower = nome.lower().strip()
        for i, h in enumerate(headers):
            if h == nome_lower:
                return i + 1
    return -1


def _ler_linha(row: list[str], headers: list[str]) -> dict:
    """Converte uma linha da planilha em dict {coluna_lower: valor}."""
    dados = {}
    for i, h in enumerate(headers):
        valor = row[i].strip() if i < len(row) else ""
        dados[h] = valor
    return dados


# =================================================================
# SCORING DA LINHA PRINCIPAL
# =================================================================

def _score_linha_principal(linha_dados: dict) -> tuple:
    """
    Calcula tupla de comparação pra escolher qual linha duplicada é a "principal".
    Tupla maior = melhor candidata.

    Ordem (do mais importante pro menos):
      1. Status prioridade (postado > planejado > preparado > ... > pendente)
      2. Prioridade (alta=3, media=2, baixa=1)
      3. Quantidade de campos preenchidos (roteiro, legenda, hashtags)
      4. Linha mais antiga (negativo do número, pois menor número = mais antiga)
    """
    status = linha_dados.get("status", "").lower().strip()
    if status in STATUS_PRIORIDADE:
        score_status = len(STATUS_PRIORIDADE) - STATUS_PRIORIDADE.index(status)
    else:
        score_status = 0  # status desconhecido = menor prioridade

    prio = linha_dados.get("prioridade", "").lower().strip()
    score_prio = {"alta": 3, "media": 2, "média": 2, "baixa": 1}.get(prio, 0)

    score_preenchimento = sum(
        1 for campo in ("roteiro", "legenda", "hashtags")
        if linha_dados.get(campo, "").strip()
    )

    # Linha mais antiga (menor _linha) ganha — negativamos pra ordenar como "maior=melhor"
    linha_num = linha_dados.get("_linha", 999999)
    score_idade = -linha_num

    return (score_status, score_prio, score_preenchimento, score_idade)


# =================================================================
# AGRUPAMENTO DE DUPLICADAS
# =================================================================

def _agrupar_duplicadas(linhas: list[dict]) -> list[list[dict]]:
    """
    Agrupa linhas que são duplicadas entre si.
    Retorna lista de grupos. Cada grupo tem ≥1 linha;
    grupos com 1 linha = únicos, grupos com ≥2 = duplicados.

    Estratégia:
      1. Primeiro agrupa por Link_Post quando ambos têm link
      2. Depois agrupa por similaridade de nome normalizado > LIMITE_SIMILARIDADE
    """
    grupos: list[list[dict]] = []

    for linha in linhas:
        nome_norm = linha["_nome_normalizado"]
        link      = linha.get("link_post", "").strip().lower()

        if not nome_norm:
            # Sem nome → grupo isolado
            grupos.append([linha])
            continue

        # Tenta encaixar em um grupo existente
        encaixou = False
        for grupo in grupos:
            ref = grupo[0]
            ref_nome = ref["_nome_normalizado"]
            ref_link = ref.get("link_post", "").strip().lower()

            # Critério 1: Link_Post idêntico (forte evidência de duplicação)
            if link and ref_link and link == ref_link:
                grupo.append(linha)
                encaixou = True
                break

            # Critério 2: similaridade de nome
            sim = _similaridade(nome_norm, ref_nome)
            if sim >= LIMITE_SIMILARIDADE:
                linha["_similaridade"] = round(sim, 3)
                grupo.append(linha)
                encaixou = True
                break

        if not encaixou:
            grupos.append([linha])

    return grupos


# =================================================================
# AÇÕES NA PLANILHA
# =================================================================

def _marcar_como_duplicado(aba, linha_num: int, col_status: int, col_erro: int,
                          linha_principal: int) -> bool:
    """Marca uma linha como Duplicado + observação. Retorna True se OK."""
    try:
        if col_status != -1:
            aba.update_cell(linha_num, col_status, "Duplicado")
        if col_erro != -1:
            observacao = f"Duplicado da linha {linha_principal}"
            aba.update_cell(linha_num, col_erro, observacao)
        return True
    except Exception as e:
        log.warning(f"  ⚠️ Falha ao marcar linha {linha_num} como Duplicado: {e}")
        return False


def _pode_remover(linha_dados: dict) -> bool:
    """
    Verifica se uma linha pode ser REMOVIDA (modo agressivo).
    Critérios conservadores:
      - Status precisa ser "pendente" (ou vazio)
      - Roteiro, Legenda, Hashtags e Link_Post precisam estar vazios
    """
    status = linha_dados.get("status", "").lower().strip()
    if status in STATUS_PROTEGIDOS:
        return False
    if status and status != "pendente":
        return False

    for campo in ("roteiro", "legenda", "hashtags", "link_post"):
        if linha_dados.get(campo, "").strip():
            return False

    return True


def _remover_linhas(aba, linhas_para_remover: list[int]) -> int:
    """
    Remove linhas da planilha (de baixo pra cima para não invalidar índices).
    Retorna quantas foram removidas com sucesso.
    """
    removidas = 0
    # Ordena decrescente para preservar índices das linhas acima
    for linha_num in sorted(linhas_para_remover, reverse=True):
        try:
            aba.delete_rows(linha_num)
            removidas += 1
            log.info(f"  🗑️ Linha {linha_num} removida")
            # Pausa pra evitar quota burst
            time.sleep(0.5)
        except Exception as e:
            log.warning(f"  ⚠️ Falha ao remover linha {linha_num}: {e}")
    return removidas


# =================================================================
# FUNÇÃO PRINCIPAL
# =================================================================

def limpar_produtos_duplicados(modo: str = "marcar") -> dict:
    """
    Detecta e organiza produtos duplicados na Fila_de_Postagem.

    Args:
        modo: "marcar" (padrão) — só marca como Duplicado.
              "remover" — remove duplicadas vazias com status Pendente.

    Returns:
        {
            "sucesso":               bool,
            "modo":                  str,
            "linhas_analisadas":     int,
            "duplicados_encontrados": int,  ← total de linhas duplicadas (não inclui as principais)
            "linhas_marcadas":       int,   ← quantas foram marcadas como "Duplicado"
            "linhas_removidas":      int,   ← só relevante no modo "remover"
            "grupos":                list,  ← detalhe dos grupos de duplicadas
            "timestamp":             str,
        }
    """
    if modo not in ("marcar", "remover"):
        msg = f"Modo inválido: '{modo}' (use 'marcar' ou 'remover')"
        log.error(msg)
        return _resultado_vazio(modo, msg, sucesso=False)

    log.info("═" * 60)
    log.info(f"🧹 PRODUCT CLEANER iniciando — modo='{modo}'")
    log.info("═" * 60)

    # ── 1. Ler planilha ───────────────────────────────────────────────
    try:
        from memory.sheets_engine import _aba, ABA_FILA
        aba = _aba(ABA_FILA)
        todas = aba.get_all_values()
    except Exception as e:
        msg = f"Falha ao ler planilha: {e}"
        log.error(f"❌ {msg}")
        return _resultado_vazio(modo, msg, sucesso=False)

    if len(todas) < 2:
        log.info("📋 Planilha vazia ou só cabeçalho — nada a limpar")
        return _resultado_vazio(modo, "Planilha vazia", sucesso=True)

    # ── 2. Detectar headers e colunas ─────────────────────────────────
    headers, start_idx = _detectar_linha_header(todas)
    log.info(f"📋 Headers detectados na linha {start_idx}: {headers}")

    col_produto    = _encontrar_coluna(headers, "produto")
    col_status     = _encontrar_coluna(headers, "status")
    col_erro       = _encontrar_coluna(headers, "erro", "observacao", "observação")

    if col_produto == -1 or col_status == -1:
        msg = "Colunas 'Produto' ou 'Status' não encontradas na planilha"
        log.error(f"❌ {msg}")
        return _resultado_vazio(modo, msg, sucesso=False)

    if col_erro == -1:
        log.warning("⚠️ Coluna 'Erro/Observação' não encontrada — não conseguirá registrar 'Duplicado da linha X'")

    # ── 3. Coletar linhas com dados ──────────────────────────────────
    linhas: list[dict] = []
    for offset, row in enumerate(todas[start_idx:]):
        linha_num = start_idx + offset + 1

        # Garante colunas suficientes
        while len(row) < len(headers):
            row.append("")

        dados = _ler_linha(row, headers)
        produto = dados.get("produto", "").strip()

        # Pula linhas sem produto
        if not produto:
            continue

        dados["_linha"]              = linha_num
        dados["_nome_normalizado"]   = _normalizar_nome(produto)
        linhas.append(dados)

    log.info(f"📊 {len(linhas)} linha(s) com produto identificadas")

    # ── 4. Agrupar duplicadas ────────────────────────────────────────
    grupos = _agrupar_duplicadas(linhas)

    grupos_duplicados = [g for g in grupos if len(g) > 1]
    grupos_unicos     = [g for g in grupos if len(g) == 1]

    log.info(
        f"🔍 Análise: {len(grupos_unicos)} produto(s) únicos | "
        f"{len(grupos_duplicados)} grupo(s) com duplicatas"
    )

    if not grupos_duplicados:
        log.info("✅ Nenhuma duplicata encontrada — fila já está limpa")
        return _finalizar(
            modo=modo,
            linhas_analisadas=len(linhas),
            grupos_duplicados=[],
            linhas_marcadas=0,
            linhas_removidas=0,
            sucesso=True,
        )

    # ── 5. Processar cada grupo ──────────────────────────────────────
    linhas_marcadas  = 0
    linhas_removidas = 0
    grupos_relatorio = []

    for grupo in grupos_duplicados:
        # Escolhe a "linha principal" (melhor score)
        grupo_ordenado = sorted(grupo, key=_score_linha_principal, reverse=True)
        principal      = grupo_ordenado[0]
        duplicadas     = grupo_ordenado[1:]

        linha_principal_num = principal["_linha"]
        produto_base        = principal.get("produto", "?")

        log.info(
            f"\n🔁 Grupo: '{produto_base[:50]}' | "
            f"principal=linha {linha_principal_num} | "
            f"duplicadas={[d['_linha'] for d in duplicadas]}"
        )

        # Detalhamento do grupo
        grupo_dict = {
            "produto_base":     produto_base,
            "linha_principal":  linha_principal_num,
            "status_principal": principal.get("status", ""),
            "duplicadas":       [],
            "removidas":        [],
            "marcadas":         [],
        }

        for dup in duplicadas:
            linha_num = dup["_linha"]
            grupo_dict["duplicadas"].append(linha_num)
            dup_status = dup.get("status", "").lower().strip()

            log.info(
                f"  ↪ Linha {linha_num} | "
                f"status='{dup_status or 'vazio'}' | "
                f"similaridade={dup.get('_similaridade', '—')} | "
                f"produto='{dup.get('produto', '')[:40]}'"
            )

            # ── Modo "remover" ──
            if modo == "remover" and _pode_remover(dup):
                # Será removida em batch depois (registrar agora)
                grupo_dict["removidas"].append(linha_num)
                continue

            # ── Modo "marcar" (padrão) ou linhas que não podem ser removidas ──
            # Não re-marca se já está Duplicado
            if dup_status == "duplicado":
                log.info(f"    ✅ Linha {linha_num} já estava marcada como Duplicado — pulando")
                continue

            ok = _marcar_como_duplicado(
                aba, linha_num, col_status, col_erro, linha_principal_num
            )
            if ok:
                linhas_marcadas += 1
                grupo_dict["marcadas"].append(linha_num)
                log.info(f"    📝 Linha {linha_num} → Status=Duplicado")
                # Pequena pausa pra não burstar quota
                time.sleep(0.3)

        # Executa remoções em batch (do maior pro menor número de linha)
        if modo == "remover" and grupo_dict["removidas"]:
            log.info(f"  🗑️ Removendo {len(grupo_dict['removidas'])} linha(s) vazia(s): {grupo_dict['removidas']}")
            removidas_agora = _remover_linhas(aba, grupo_dict["removidas"])
            linhas_removidas += removidas_agora

        grupos_relatorio.append(grupo_dict)

    # ── 6. Resumo final ──────────────────────────────────────────────
    duplicados_total = sum(len(g["duplicadas"]) for g in grupos_relatorio)

    return _finalizar(
        modo=modo,
        linhas_analisadas=len(linhas),
        grupos_duplicados=grupos_relatorio,
        linhas_marcadas=linhas_marcadas,
        linhas_removidas=linhas_removidas,
        sucesso=True,
        duplicados_total=duplicados_total,
    )


# =================================================================
# HELPERS DE RESULTADO
# =================================================================

def _finalizar(
    modo: str,
    linhas_analisadas: int,
    grupos_duplicados: list,
    linhas_marcadas: int,
    linhas_removidas: int,
    sucesso: bool,
    duplicados_total: Optional[int] = None,
) -> dict:
    """Monta dicionário de resultado, salva em disco e retorna."""
    if duplicados_total is None:
        duplicados_total = sum(len(g["duplicadas"]) for g in grupos_duplicados)

    resultado = {
        "sucesso":               sucesso,
        "modo":                  modo,
        "linhas_analisadas":     linhas_analisadas,
        "duplicados_encontrados": duplicados_total,
        "linhas_marcadas":       linhas_marcadas,
        "linhas_removidas":      linhas_removidas,
        "grupos":                grupos_duplicados,
        "timestamp":             time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Salva
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        caminho = PLANS_DIR / "limpeza_produtos_resultado.json"
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        log.info(f"💾 Resultado salvo: {caminho}")
    except Exception as e:
        log.warning(f"⚠️ Falha ao salvar resultado: {e}")

    log.info("═" * 60)
    log.info(
        f"{'✅' if sucesso else '❌'} CLEANER concluído: "
        f"{duplicados_total} duplicadas | "
        f"{linhas_marcadas} marcadas | {linhas_removidas} removidas"
    )
    log.info("═" * 60)

    return resultado


def _resultado_vazio(modo: str, mensagem: str, sucesso: bool) -> dict:
    return {
        "sucesso":               sucesso,
        "modo":                  modo,
        "linhas_analisadas":     0,
        "duplicados_encontrados": 0,
        "linhas_marcadas":       0,
        "linhas_removidas":      0,
        "grupos":                [],
        "mensagem":              mensagem,
        "timestamp":             time.strftime("%Y-%m-%d %H:%M:%S"),
    }


# =================================================================
# TESTE VIA TERMINAL
# =================================================================

if __name__ == "__main__":
    import sys

    # Permite escolher modo via argumento: python -m agents.product_cleaner remover
    modo_arg = "marcar"
    if len(sys.argv) > 1 and sys.argv[1] in ("marcar", "remover"):
        modo_arg = sys.argv[1]

    print("=" * 60)
    print(f"  🧹 Product Cleaner — Teste (modo='{modo_arg}')")
    print("=" * 60)

    if modo_arg == "remover":
        print("\n  ⚠️ MODO REMOVER ATIVADO")
        print("     Só remove linhas duplicadas COM Status=Pendente E vazias.")
        print("     Postado / Planejado / Preparado / Aguardando_Video são protegidos.")
        print()

    resultado = limpar_produtos_duplicados(modo=modo_arg)

    print(f"\n{'─' * 60}")
    print(f"  📊 RESULTADO")
    print(f"{'─' * 60}")
    icone = "✅" if resultado["sucesso"] else "❌"
    print(f"  {icone} Sucesso:               {resultado['sucesso']}")
    print(f"  🛠️  Modo:                   {resultado['modo']}")
    print(f"  📊 Linhas analisadas:       {resultado['linhas_analisadas']}")
    print(f"  🔁 Duplicados encontrados:  {resultado['duplicados_encontrados']}")
    print(f"  📝 Linhas marcadas:         {resultado['linhas_marcadas']}")
    print(f"  🗑️  Linhas removidas:        {resultado['linhas_removidas']}")

    grupos = resultado.get("grupos", [])
    if grupos:
        print(f"\n{'─' * 60}")
        print(f"  🔁 GRUPOS DE DUPLICATAS ({len(grupos)})")
        print(f"{'─' * 60}")
        for i, g in enumerate(grupos, 1):
            print(f"\n  Grupo {i}: '{g['produto_base'][:50]}'")
            print(f"    🏆 Principal:  linha {g['linha_principal']} (status='{g.get('status_principal', '?')}')")
            print(f"    ↪ Duplicadas: {g['duplicadas']}")
            if g.get("marcadas"):
                print(f"    📝 Marcadas:  {g['marcadas']}")
            if g.get("removidas"):
                print(f"    🗑️  Removidas: {g['removidas']}")

    print(f"\n{'─' * 60}")
    print(f"  💾 ARQUIVOS")
    print(f"{'─' * 60}")
    print(f"  Resultado: shared/content_plans/limpeza_produtos_resultado.json")

    if resultado.get("mensagem"):
        print(f"\n  💬 {resultado['mensagem']}")

    print(f"\n{'─' * 60}")
    print(f"  💡 PRÓXIMO PASSO")
    print(f"{'─' * 60}")
    if resultado["sucesso"] and resultado["duplicados_encontrados"] > 0:
        if modo_arg == "marcar":
            print(f"  ✅ {resultado['linhas_marcadas']} linha(s) marcadas como Duplicado na planilha.")
            print(f"  Confira a aba Fila_de_Postagem. Quando estiver tranquilo, pode rodar:")
            print(f"      python -m agents.product_cleaner remover")
            print(f"  (isso só remove duplicatas VAZIAS com status Pendente)")
        else:
            print(f"  ✅ Limpeza concluída. Linhas com dados foram MANTIDAS (marcadas como Duplicado).")
            print(f"  Próximo orquestrador vai pegar produtos únicos:")
            print(f"      python -m agents.autonomous_orchestrator")
    elif resultado["sucesso"]:
        print(f"  ✅ Fila já está limpa, sem duplicatas detectadas.")
    else:
        print(f"  ❌ {resultado.get('mensagem', 'Falha na limpeza')}")

    print("=" * 60)