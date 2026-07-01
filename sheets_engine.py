# memory/sheets_engine.py
# Integração completa com Google Sheets via gspread
# A planilha "AgenteIA_Dashboard" é a memória profunda e painel do agente
#
# SETUP:
#   1. Crie um projeto no Google Cloud Console
#   2. Ative APIs: Google Sheets API + Google Drive API
#   3. Crie uma Service Account e baixe o credentials.json
#   4. Compartilhe a planilha com o e-mail da service account
#   5. pip install gspread google-auth

import time
from datetime import datetime          # ← movido pro topo (estava no meio do arquivo)
from pathlib import Path
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from shared.logger import get_logger

log = get_logger(__name__)

# =========================
# CONFIGURAÇÃO
# =========================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CREDENTIALS_PATH = Path(__file__).parent.parent / "credentials.json"
NOME_PLANILHA = "AgenteIA_Dashboard"

# Abas da planilha
ABA_FILA       = "Fila_de_Postagem"
ABA_HISTORICO  = "Historico_Performance"
ABA_CONFIG     = "Config_Agente"

# Índices das colunas — Fila_de_Postagem (começa em 1 no gspread)
class ColFila:
    DATA       = 1   # A - Data de criação
    PRODUTO    = 2   # B - Nome do produto
    ROTEIRO    = 3   # C - Roteiro gerado pelo Gemini
    LEGENDA    = 4   # D - Legenda viral
    CTA        = 5   # E - Call to action
    HASHTAGS   = 6   # F - Hashtags
    STATUS     = 7   # G - Pendente | Gerado | Postado | Erro
    LINK_POST  = 8   # H - Link do post publicado
    ERRO       = 9   # I - Mensagem de erro (se houver)
    PLATAFORMA = 10  # J - TikTok | Instagram | YouTube

# Índices — Historico_Performance
class ColHistorico:
    ID_POST    = 1
    DATA_POST  = 2
    VIEWS      = 3
    CLIQUES    = 4
    VENDAS     = 5
    LUCROS_EST = 6


# =========================
# CONEXÃO
# =========================

_client_cache = None  # evita reconectar a cada chamada

def conectar_planilha() -> gspread.Spreadsheet:
    """
    Conecta ao Google Sheets e retorna o objeto da planilha.
    Usa cache interno para não reconectar desnecessariamente.
    """
    global _client_cache

    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            f"credentials.json não encontrado em: {CREDENTIALS_PATH}\n"
            "Baixe do Google Cloud Console e coloque na raiz do projeto."
        )

    try:
        creds = Credentials.from_service_account_file(
            str(CREDENTIALS_PATH), scopes=SCOPES
        )
        _client_cache = gspread.authorize(creds)
        planilha = _client_cache.open(NOME_PLANILHA)
        log.info(f"✅ Conectado à planilha: {NOME_PLANILHA}")
        return planilha
    except gspread.SpreadsheetNotFound:
        raise RuntimeError(
            f"Planilha '{NOME_PLANILHA}' não encontrada.\n"
            "Verifique se o nome está correto e se foi compartilhada "
            "com o e-mail da service account."
        )
    except Exception as e:
        log.error(f"Erro ao conectar planilha: {e}")
        raise


def _aba(nome_aba: str) -> gspread.Worksheet:
    """Retorna uma aba da planilha pelo nome."""
    return conectar_planilha().worksheet(nome_aba)


# =========================
# LEITURA
# =========================

def ler_produtos_pendentes() -> list[dict]:
    """
    Lê todas as linhas com Status = 'Pendente' na Fila_de_Postagem.

    Retorna lista de dicts:
    [{"linha": 2, "produto": "...", "plataforma": "..."}, ...]
    """
    try:
        aba = _aba(ABA_FILA)
        todas = aba.get_all_values()
        pendentes = []

        for i, row in enumerate(todas[1:], start=2):  # pula cabeçalho
            # Garante que a linha tem colunas suficientes
            while len(row) < 10:
                row.append("")

            status = row[ColFila.STATUS - 1].strip()
            produto = row[ColFila.PRODUTO - 1].strip()

            if status.upper() == "PENDENTE" and produto:
                pendentes.append({
                    "linha": i,
                    "produto": produto,
                    "plataforma": row[ColFila.PLATAFORMA - 1] or "TikTok",
                })

        log.info(f"📋 {len(pendentes)} produto(s) pendente(s) encontrado(s)")
        return pendentes

    except Exception as e:
        log.error(f"Erro ao ler pendentes: {e}")
        return []


def ler_config() -> dict:
    """
    Lê a aba Config_Agente e retorna um dicionário {Variavel: Valor}.
    Útil para o agente buscar configurações sem hardcode.
    """
    try:
        aba = _aba(ABA_CONFIG)
        rows = aba.get_all_values()
        config = {}
        for row in rows[1:]:  # pula cabeçalho
            if len(row) >= 2 and row[0]:
                config[row[0].strip()] = row[1].strip()
        log.info(f"⚙️ Config carregada: {list(config.keys())}")
        return config
    except Exception as e:
        log.error(f"Erro ao ler config: {e}")
        return {}


# Alias para compatibilidade com publish_guard.py que importa ler_config_agente
# ← BUG CORRIGIDO: publish_guard chamava ler_config_agente mas a função se chama ler_config
ler_config_agente = ler_config


# =========================
# ESCRITA — STATUS
# =========================

def atualizar_status(linha: int, status: str):
    """
    Atualiza o Status de uma linha.
    Status válidos: Pendente | Gerado | Postado | Erro
    """
    try:
        aba = _aba(ABA_FILA)
        aba.update_cell(linha, ColFila.STATUS, status)
        log.info(f"🔄 Linha {linha} → Status: {status}")
    except Exception as e:
        log.error(f"Erro ao atualizar status (linha {linha}): {e}")


# =========================
# ESCRITA — CONTEÚDO GERADO
# =========================

def salvar_roteiro(
    linha: int,
    roteiro: str,
    legenda: str = "",
    cta: str = "",
    hashtags: str = "",
):
    """
    Salva o conteúdo gerado pelo Gemini na linha da planilha
    e marca o status como 'Gerado'.
    """
    try:
        aba = _aba(ABA_FILA)
        hoje = time.strftime("%d/%m/%Y %H:%M")

        aba.update_cell(linha, ColFila.DATA, hoje)
        aba.update_cell(linha, ColFila.ROTEIRO, roteiro[:49000])
        aba.update_cell(linha, ColFila.LEGENDA, legenda)
        aba.update_cell(linha, ColFila.CTA, cta)
        aba.update_cell(linha, ColFila.HASHTAGS, hashtags)
        aba.update_cell(linha, ColFila.STATUS, "Gerado")
        aba.update_cell(linha, ColFila.ERRO, "")

        log.info(f"✅ Roteiro salvo na linha {linha}")
    except Exception as e:
        log.error(f"Erro ao salvar roteiro (linha {linha}): {e}")
        registrar_erro(linha, str(e))


# =========================
# ESCRITA — ERRO
# =========================

def registrar_erro(linha: int, erro: str):
    """
    Marca a linha com Status = 'Erro' e salva a mensagem de erro.
    """
    try:
        aba = _aba(ABA_FILA)
        aba.update_cell(linha, ColFila.STATUS, "Erro")
        aba.update_cell(linha, ColFila.ERRO, erro[:1000])
        log.warning(f"❌ Erro registrado na linha {linha}: {erro[:80]}")
    except Exception as e:
        log.error(f"Erro ao registrar erro (linha {linha}): {e}")


# =========================
# ESCRITA — PÓS POSTAGEM
# =========================

def registrar_postagem(linha: int, link_post: str, plataforma: str = ""):
    """
    Após postar, salva o link e marca Status = 'Postado'.
    """
    try:
        aba = _aba(ABA_FILA)
        aba.update_cell(linha, ColFila.STATUS, "Postado")
        aba.update_cell(linha, ColFila.LINK_POST, link_post)
        log.info(f"🚀 Postagem registrada na linha {linha}: {link_post}")
    except Exception as e:
        log.error(f"Erro ao registrar postagem (linha {linha}): {e}")


def registrar_metricas(
    linha: int,
    views: int = 0,
    cliques: int = 0,
    vendas: int = 0,
    lucros_est: float = 0.0,
    link_post: str = "",
):
    """
    Salva métricas de performance na aba Historico_Performance.
    """
    try:
        aba = _aba(ABA_HISTORICO)
        hoje = time.strftime("%d/%m/%Y")
        aba.append_row([
            f"POST_{int(time.time())}",
            hoje,
            views,
            cliques,
            vendas,
            f"R$ {lucros_est:.2f}",
            link_post,
        ])
        log.info(f"📊 Métricas registradas: {views} views, {cliques} cliques")
    except Exception as e:
        log.error(f"Erro ao registrar métricas: {e}")


# =========================
# ESCRITA — PÓS WORKFLOW AUTÔNOMO
# =========================

def registrar_postagem_sheets() -> dict:
    """
    Registra a postagem mais recente na planilha após publicação autônoma.
    Chamada pelo workflow engine como ação brain-level.

    Lê o state_manager para montar o registro e atualiza a Fila_de_Postagem.
    Não quebra o workflow se a planilha estiver indisponível.

    Returns:
        { "sucesso": bool, "mensagem": str, "dados": dict }
    """
    log.info("📊 Registrando postagem na planilha...")

    # ── Lê contexto do state_manager ──────────────────────────────
    try:
        from memory.state_manager import carregar_estado, atualizar_varios
        state = carregar_estado()
    except Exception as e:
        log.warning(f"Não foi possível ler state_manager: {e}")
        state = {}

    agora      = datetime.now()
    timestamp  = agora.strftime("%Y-%m-%d %H:%M:%S")
    data_hoje  = agora.strftime("%Y-%m-%d")
    plataforma = state.get("plataforma_atual", "TikTok")
    produto    = state.get("produto_atual", "")
    legenda    = state.get("legenda_atual", "")
    hashtags   = state.get("hashtags_atuais", "")
    laudo      = state.get("ultimo_laudo_auditoria", {})
    motivo     = laudo.get("motivo", "Publicado via workflow autônomo")

    linha_registro = {
        "Data":       data_hoje,
        "Timestamp":  timestamp,
        "Produto":    produto,
        "Legenda":    legenda[:100] if legenda else "",
        "Hashtags":   hashtags[:100] if hashtags else "",
        "Status":     "Postado",
        "Plataforma": plataforma,
        "Motivo":     motivo,
        "Link_Post":  "",
        "Erro":       "",
    }

    # ── Tenta escrever na planilha ─────────────────────────────────
    try:
        sheet = _aba(ABA_FILA)   # ← BUG CORRIGIDO: era _get_sheet() que não existe

        # Encontra linha com status Em_Progresso ou Gerado para a plataforma atual
        registros = sheet.get_all_records()
        linha_atualizar = None
        for i, row in enumerate(registros, start=2):
            if (row.get("Status") in ("Em_Progresso", "Gerado")
                    and row.get("Plataforma", "").lower() == plataforma.lower()):
                linha_atualizar = i
                break

        if linha_atualizar:
            sheet.update_cell(linha_atualizar, ColFila.STATUS, "Postado")
            # Registra timestamp na coluna Erro (reutilizada como log) se não houver coluna própria
            log.info(f"✅ Linha {linha_atualizar} atualizada para 'Postado'")
        else:
            # Nenhuma linha pendente — adiciona nova linha
            sheet.append_row(list(linha_registro.values()))
            log.info("✅ Nova linha adicionada em Fila_de_Postagem")

    except Exception as e:
        log.warning(f"⚠️ Planilha indisponível, registro não salvo: {e}")
        return {
            "sucesso":  True,   # não bloqueia o workflow
            "mensagem": f"Postagem realizada, mas planilha indisponível: {e}",
            "dados":    linha_registro,
        }

    # ── Atualiza contador diário no state ─────────────────────────
    try:
        from memory.state_manager import atualizar_varios
        chave_contador = f"posts_publicados_{data_hoje}"
        contador_atual = int(state.get(chave_contador, 0))
        atualizar_varios({
            chave_contador:            contador_atual + 1,
            "ultimo_post_timestamp":   timestamp,
            "ultimo_post_plataforma":  plataforma,
        })
        log.info(f"📈 Posts hoje: {contador_atual + 1}")
    except Exception as e:
        log.warning(f"Não foi possível atualizar contador: {e}")

    return {
        "sucesso":  True,
        "mensagem": f"Postagem registrada: {plataforma} | {timestamp}",
        "dados":    linha_registro,
    }


# =========================
# HELPER INTERNO
# =========================

def _col_index(sheet: gspread.Worksheet, nome_coluna: str) -> Optional[int]:
    """Retorna índice (1-based) de uma coluna pelo nome do header. None se não existir."""
    try:
        headers = sheet.row_values(1)
        return headers.index(nome_coluna) + 1
    except (ValueError, Exception):
        return None


# =========================
# TESTE RÁPIDO
# =========================

if __name__ == "__main__":
    print("🧪 Testando conexão com Google Sheets...")
    try:
        pendentes = ler_produtos_pendentes()
        if pendentes:
            print(f"✅ {len(pendentes)} produto(s) pendente(s):")
            for p in pendentes:
                print(f"   Linha {p['linha']}: {p['produto']} ({p['plataforma']})")
        else:
            print("ℹ️ Nenhum produto pendente. Adicione na planilha com Status=Pendente")

        config = ler_config()
        if config:
            print(f"⚙️ Config: {config}")
    except Exception as e:
        print(f"❌ Erro: {e}")