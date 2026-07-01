# chat_agent.py
# Terminal conversacional do AgenteIA — estilo Jarvis
#
# Uso:
#   python chat_agent.py
#
# O agente interpreta linguagem natural, escolhe a ação certa
# e executa workflows, visão e comandos de forma autônoma.

import os
import sys
import time
import json

from google import genai
from google.genai import errors

from workflows.engine      import executar_workflow, listar_workflows
from brain.commander       import enviar_comando, enviar_sequencia
from brain.vision_analyzer import observar_e_analisar, clicar_elemento_por_texto
from analytics.context_engine import gerar_contexto_estrategico
from memory.state_manager  import carregar_estado, status_atual, limpar_estado
from shared.logger         import get_logger

log = get_logger("chat_agent")

# =========================
# IDENTIDADE
# =========================

NOME    = "Jarvis"
VERSAO  = "2.0"
COR_EU  = "\033[96m"   # ciano — fala do usuário
COR_IA  = "\033[92m"   # verde — fala do Jarvis
COR_ERR = "\033[91m"   # vermelho — erros
COR_DIM = "\033[90m"   # cinza — logs internos
COR_GEM = "\033[95m"   # magenta — Gemini fallback
RESET   = "\033[0m"

# Histórico máximo enviado ao Gemini (turnos = par user+jarvis)
MAX_HISTORICO = 10


# =========================
# CLIENTE GEMINI (singleton)
# =========================

_gemini_client = None

def _get_gemini():
    global _gemini_client
    if _gemini_client is None:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY não definida.")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _falar(msg: str, tipo: str = "ia"):
    """Imprime mensagem formatada no estilo Jarvis."""
    if tipo == "ia":
        print(f"{COR_IA}{NOME}: {msg}{RESET}")
    elif tipo == "gemini":
        print(f"{COR_GEM}{NOME}: {msg}{RESET}")
    elif tipo == "erro":
        print(f"{COR_ERR}{NOME}: {msg}{RESET}")
    elif tipo == "dim":
        print(f"{COR_DIM}  ↳ {msg}{RESET}")
    elif tipo == "separador":
        print(f"{COR_DIM}{'─' * 50}{RESET}")


def _input_usuario() -> str:
    """Captura input com estilo."""
    try:
        return input(f"{COR_EU}Você: {RESET}").strip()
    except (KeyboardInterrupt, EOFError):
        return "sair"


# =========================
# MAPA DE INTENÇÕES
# Cada entrada: lista de palavras-chave → ação interna
# =========================

INTENCOES = [
    # Workflows de plataforma
    {
        "palavras":  ["postar tiktok", "poste tiktok", "post tiktok", "tiktok post", "publicar tiktok"],
        "tipo":      "workflow",
        "workflow":  "postar_tiktok",
        "resposta":  "Iniciando sequência de postagem no TikTok...",
    },
    {
        "palavras":  ["upload video", "upload tiktok", "enviar video", "fazer upload"],
        "tipo":      "workflow",
        "workflow":  "upload_tiktok_video",
        "resposta":  "Iniciando upload de vídeo...",
    },
    {
        "palavras":  ["abrir tiktok", "abre tiktok", "abrir o tiktok"],
        "tipo":      "comando",
        "acao":      "abrir_site",
        "alvo":      "https://www.tiktok.com",
        "resposta":  "Abrindo TikTok no Windows...",
    },
    {
        "palavras":  ["abrir instagram", "abre instagram"],
        "tipo":      "comando",
        "acao":      "abrir_site",
        "alvo":      "https://www.instagram.com",
        "resposta":  "Abrindo Instagram no Windows...",
    },
    {
        "palavras":  ["abrir youtube", "abre youtube", "abrir studio"],
        "tipo":      "comando",
        "acao":      "abrir_site",
        "alvo":      "https://studio.youtube.com",
        "resposta":  "Abrindo YouTube Studio no Windows...",
    },
    # Visão
    {
        "palavras":  ["observar tela", "observe tela", "ver tela", "analisar tela", "o que está na tela", "o que tem na tela"],
        "tipo":      "observe",
        "resposta":  "Analisando interface atual...",
    },
    {
        "palavras":  ["screenshot", "tirar screenshot", "print tela", "capturar tela"],
        "tipo":      "screenshot",
        "resposta":  "Capturando tela...",
    },
    {
        "palavras":  ["clicar em", "clica em", "clicar no", "clica no"],
        "tipo":      "clicar_texto",
        "resposta":  "Localizando elemento na tela...",
    },
    # Contexto e estratégia
    {
        "palavras":  ["contexto", "estratégia do dia", "contexto estratégico", "resumo do dia"],
        "tipo":      "contexto",
        "resposta":  "Carregando contexto estratégico do dia...",
    },
    # Sistema
    {
        "palavras":  ["status", "estado", "como está", "o que está fazendo"],
        "tipo":      "status",
        "resposta":  "Verificando estado operacional...",
    },
    {
        "palavras":  ["listar workflows", "workflows disponíveis", "quais workflows"],
        "tipo":      "listar",
        "resposta":  "Consultando workflows disponíveis...",
    },
    {
        "palavras":  ["limpar estado", "resetar", "limpar memória"],
        "tipo":      "limpar",
        "resposta":  "Limpando estado operacional...",
    },
    {
        "palavras":  ["ajuda", "help", "comandos", "o que você faz", "o que você pode fazer"],
        "tipo":      "ajuda",
        "resposta":  "Aqui está o que posso fazer:",
    },
    {
        "palavras":  ["sair", "exit", "fechar", "parar", "encerrar", "tchau", "até logo"],
        "tipo":      "sair",
        "resposta":  "Encerrando sistemas. Até logo.",
    },
]


# =========================
# INTERPRETADOR DE INTENÇÃO
# =========================

def interpretar_comando(texto: str) -> dict:
    """
    Interpreta texto em linguagem natural e retorna a intenção estruturada.

    Returns:
        dict com: tipo, acao, workflow, resposta, extras
    """
    texto_lower = texto.lower().strip()

    for intencao in INTENCOES:
        for palavra in intencao["palavras"]:
            if palavra in texto_lower:
                resultado = {**intencao}
                resultado.pop("palavras", None)

                # Extrai o alvo para comandos de "clicar em X"
                if intencao["tipo"] == "clicar_texto":
                    for prefixo in ("clicar em ", "clica em ", "clicar no ", "clica no "):
                        if prefixo in texto_lower:
                            alvo = texto_lower.split(prefixo, 1)[1].strip()
                            resultado["alvo"] = alvo
                            resultado["resposta"] = f"Localizando '{alvo}' na tela..."
                            break

                return resultado

    # Intenção não reconhecida — tenta responder com Gemini
    return {
        "tipo":     "desconhecido",
        "texto":    texto,
        "resposta": None,
    }


# =========================
# FALLBACK GEMINI — INTERPRETAÇÃO SEMÂNTICA
# =========================

SYSTEM_PROMPT = """Você é Jarvis, assistente operacional do AgenteIA.
Você controla workflows, visão computacional e automações Windows para um agente de redes sociais.

WORKFLOWS DISPONÍVEIS: {workflows}

ESTADO ATUAL DO AGENTE:
{estado}

Interprete a intenção do usuário em português natural e retorne APENAS JSON válido, sem markdown.

Regras de classificação:
- abrir plataformas / sites / programas → tipo="comando", acao="abrir_site" ou "abrir_programa"
- observar / analisar / ver tela / checar se abriu → tipo="observe"
- executar automação / postar / upload → tipo="workflow"
- clicar em elemento → tipo="clicar_texto"
- tirar screenshot / print → tipo="screenshot"
- ver status / estado / ocupado → tipo="status"
- sair / fechar / encerrar → tipo="sair"
- pergunta casual / conversa → tipo="resposta"

REGRA OBRIGATÓRIA — URLs COMPLETAS:
Quando acao="abrir_site", o campo parametros.alvo DEVE ser a URL completa com https://.
NUNCA retorne apenas o nome da plataforma. Use EXATAMENTE:
- TikTok, tik tok, tiktok         → https://www.tiktok.com
- Instagram, insta                 → https://www.instagram.com
- YouTube, youtube studio          → https://studio.youtube.com
- Shopee                           → https://shopee.com.br
- Google                           → https://www.google.com
- Qualquer outro site              → URL completa com https://

Formato obrigatório:
{{
  "tipo": "workflow | comando | observe | clicar_texto | screenshot | status | sair | resposta",
  "acao": "nome da acao (ex: abrir_site) ou null",
  "workflow": "nome do workflow ou null",
  "resposta": "o que Jarvis vai dizer ao usuário — tom direto, max 15 palavras",
  "parametros": {{
    "alvo": "URL COMPLETA com https:// ou texto do elemento"
  }}
}}

NUNCA invente workflows que não estão na lista.
Se for conversa casual, tipo="resposta" e escreva a resposta em "resposta".
"""

# =========================
# NORMALIZADOR DE PARÂMETROS
# Defesa local contra URLs incompletas retornadas pelo Gemini
# =========================

# Mapa canônico: termo → URL completa
_URL_MAP = {
    "tiktok":          "https://www.tiktok.com",
    "tik tok":         "https://www.tiktok.com",
    "tik-tok":         "https://www.tiktok.com",
    "instagram":       "https://www.instagram.com",
    "insta":           "https://www.instagram.com",
    "youtube":         "https://studio.youtube.com",
    "youtube studio":  "https://studio.youtube.com",
    "yt":              "https://studio.youtube.com",
    "shopee":          "https://shopee.com.br",
    "google":          "https://www.google.com",
    "twitter":         "https://www.twitter.com",
    "x":               "https://www.x.com",
    "linkedin":        "https://www.linkedin.com",
    "facebook":        "https://www.facebook.com",
}


def normalizar_parametros_comando(gem: dict) -> dict:
    """
    Corrige parâmetros do Gemini antes de enviar ao executor.
    Garante que abrir_site sempre receba URL completa com https://.

    Se o alvo for um nome de plataforma conhecido → substitui pela URL canônica.
    Se for qualquer string sem http → vira busca no Google.

    Args:
        gem: dict retornado por responder_com_gemini()

    Returns:
        gem com parametros.alvo corrigido (in-place e retornado)
    """
    if gem.get("tipo") != "comando" or gem.get("acao") != "abrir_site":
        return gem

    params = gem.get("parametros", {})
    alvo   = str(params.get("alvo", "")).strip().lower()

    if not alvo:
        return gem

    # 1. Já é URL completa — mantém
    if alvo.startswith("http://") or alvo.startswith("https://"):
        return gem

    # 2. Nome de plataforma conhecida — substitui
    if alvo in _URL_MAP:
        url_corrigida = _URL_MAP[alvo]
        log.info(f"🔧 URL normalizada: '{alvo}' → '{url_corrigida}'")
        print(f"{COR_DIM}  ↳ URL normalizada: '{alvo}' → '{url_corrigida}'{RESET}")
        params["alvo"] = url_corrigida
        return gem

    # 3. Termo parcial — verifica se contém alguma chave do mapa
    for termo, url in _URL_MAP.items():
        if termo in alvo:
            log.info(f"🔧 URL normalizada (parcial): '{alvo}' → '{url}'")
            print(f"{COR_DIM}  ↳ URL normalizada: '{alvo}' → '{url}'{RESET}")
            params["alvo"] = url
            return gem

    # 4. Desconhecido sem http — vira busca Google
    url_busca = f"https://www.google.com/search?q={alvo.replace(' ', '+')}"
    log.info(f"🔧 URL desconhecida '{alvo}' → busca Google: {url_busca}")
    print(f"{COR_DIM}  ↳ URL desconhecida → busca Google: {url_busca}{RESET}")
    params["alvo"] = url_busca
    return gem


def responder_com_gemini(texto: str, historico: list) -> dict:
    """
    Fallback semântico: usa Gemini para interpretar intenções não mapeadas.

    Args:
        texto:     comando do usuário
        historico: últimos N turnos da conversa [{role, texto}]

    Returns:
        dict com tipo, acao, workflow, resposta, parametros
        Em caso de falha retorna tipo="erro"
    """
    workflows_disponiveis = ", ".join(listar_workflows()) or "nenhum"
    estado = carregar_estado()
    estado_resumo = (
        f"estado={estado.get('estado_atual')} | "
        f"produto={estado.get('produto_atual') or 'nenhum'} | "
        f"etapa={estado.get('etapa') or 'ocioso'}"
    )

    system = SYSTEM_PROMPT.format(
        workflows=workflows_disponiveis,
        estado=estado_resumo,
    )

    # Monta contexto do histórico recente
    ctx_historico = ""
    for h in historico[-MAX_HISTORICO:]:
        role = "Usuário" if h["role"] == "user" else "Jarvis"
        ctx_historico += f"{role}: {h['texto']}\n"

    prompt_final = (
        f"{ctx_historico}"
        f"Usuário: {texto}\n"
        f"Retorne o JSON de ação:"
    )

    _falar("Consultando Gemini...", "dim")

    try:
        client   = _get_gemini()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                {"role": "user", "parts": [{"text": system + "\n\n" + prompt_final}]}
            ],
        )

        raw = response.text.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])

        resultado = json.loads(raw)

        # Garante campos mínimos
        resultado.setdefault("tipo",       "resposta")
        resultado.setdefault("acao",       None)
        resultado.setdefault("workflow",   None)
        resultado.setdefault("resposta",   "Entendido.")
        resultado.setdefault("parametros", {})

        # Logs internos estilo Jarvis
        print(
            f"{COR_DIM}  🧠 Gemini interpretou: tipo={resultado['tipo']}"
            + (f" | ▶ ação: {resultado['acao']}" if resultado.get("acao") else "")
            + (f" | 📋 workflow: {resultado['workflow']}" if resultado.get("workflow") else "")
            + RESET
        )
        log.info(f"Gemini fallback: {resultado['tipo']} | {resultado.get('resposta','')[:60]}")
        return resultado

    except json.JSONDecodeError as e:
        log.warning(f"Gemini retornou JSON inválido: {e}")
        print(f"{COR_DIM}  ⚠ fallback: JSON inválido — respondendo em texto livre{RESET}")
        # Usa o texto bruto como resposta casual
        return {
            "tipo":       "resposta",
            "acao":       None,
            "workflow":   None,
            "resposta":   response.text.strip()[:200],
            "parametros": {},
        }
    except errors.ClientError as e:
        log.error(f"Erro API Gemini no fallback: {e}")
        return {
            "tipo":     "erro",
            "resposta": "Gemini indisponível no momento. Tente um comando direto.",
        }
    except Exception as e:
        log.error(f"Erro inesperado no fallback Gemini: {e}")
        return {
            "tipo":     "erro",
            "resposta": f"Não consegui processar: {e}",
        }


# =========================
# EXECUTORES DE AÇÃO
# =========================

def _executar_workflow(nome: str, ctx: dict = None) -> str:
    """Executa workflow e retorna resposta para o terminal."""
    resultado = executar_workflow(nome, contexto=ctx or {})
    if resultado["sucesso"]:
        return f"Workflow '{nome}' concluído. {resultado['passos_ok']}/{resultado['passos_total']} passos OK."
    else:
        falhou = resultado.get("passo_falhou", "?")
        return f"Workflow '{nome}' falhou no passo '{falhou}'. {resultado['passos_ok']}/{resultado['passos_total']} passos OK."


def _executar_observe(ctx: str = "terminal_manual") -> str:
    """Observa tela e formata resposta."""
    _falar("Capturando screenshot e enviando ao Gemini Vision...", "dim")
    resultado = observar_e_analisar(contexto=ctx)

    if not resultado.get("sucesso"):
        return f"Não consegui analisar a tela: {resultado.get('erro', 'erro desconhecido')}"

    analise  = resultado["analise"]
    estado   = analise.get("estado", "?")
    app      = analise.get("app_ativo", "?")
    descricao = analise.get("descricao", "")
    proxima  = analise.get("proxima_acao_sugerida", "")
    alerta   = analise.get("alerta")

    linhas = [f"{app} detectado. Estado: {estado}."]
    if descricao:
        linhas.append(descricao[:120])
    if alerta:
        linhas.append(f"⚠️ Alerta: {alerta}")
    if proxima:
        linhas.append(f"Sugestão: {proxima[:80]}")

    return " | ".join(linhas)


def _executar_screenshot() -> str:
    resultado = enviar_comando("screenshot", contexto="manual")
    if resultado.get("sucesso"):
        caminho = (resultado.get("dados") or {})
        return f"Screenshot salvo."
    return "Falha ao capturar screenshot."


def _executar_clicar_texto(alvo: str) -> str:
    if not alvo:
        return "Qual elemento devo clicar? Ex: 'clicar em Select file'"
    _falar(f"Procurando '{alvo}' na tela via Gemini Vision...", "dim")
    resultado = clicar_elemento_por_texto("terminal_clique", alvo)
    if resultado.get("bloqueado"):
        return f"⚠️ Bloqueio detectado: {resultado['mensagem']}"
    if resultado["sucesso"]:
        return f"Clicado em '{alvo}' — coordenadas ({resultado['x']}, {resultado['y']}) [confiança: {resultado['confianca']}]"
    return f"Não consegui clicar: {resultado['mensagem']}"


def _executar_status() -> str:
    estado = carregar_estado()
    if estado["estado_atual"] == "ocioso":
        return "Sistemas operacionais. Nenhuma tarefa em andamento."
    return (
        f"Estado: {estado['estado_atual'].upper()} | "
        f"Produto: '{estado['produto_atual']}' | "
        f"Etapa: {estado['etapa']} | "
        f"Tentativas: {estado['tentativas']}"
    )


def _executar_ajuda() -> str:
    return ""  # impressão feita inline abaixo


AJUDA = [
    ("abrir tiktok / instagram / youtube",  "Abre a plataforma no Windows"),
    ("observar tela",                        "Gemini Vision analisa a interface atual"),
    ("screenshot",                           "Captura e salva a tela"),
    ("clicar em [elemento]",                 "Localiza e clica por visão (sem imagem)"),
    ("postar tiktok",                        "Executa workflow de postagem TikTok"),
    ("upload video",                         "Inicia upload de vídeo no TikTok"),
    ("contexto",                             "Exibe contexto estratégico do dia"),
    ("listar workflows",                     "Mostra workflows disponíveis"),
    ("status",                               "Estado operacional do agente"),
    ("limpar estado",                        "Reseta memória operacional"),
    ("sair",                                 "Encerra o terminal"),
]


# =========================
# LOOP PRINCIPAL
# =========================

def iniciar():
    """Loop conversacional principal do AgenteIA."""

    # Cabeçalho
    print(f"\n{COR_IA}{'═' * 50}")
    print(f"  {NOME} — AgenteIA Terminal v{VERSAO}")
    print(f"{'═' * 50}{RESET}")
    _falar("Sistemas iniciados. Como posso ajudar?")
    _falar('Digite "ajuda" para ver os comandos disponíveis.', "dim")
    print()

    historico: list = []  # histórico da sessão — alimenta o Gemini

    while True:
        texto = _input_usuario()

        if not texto:
            continue

        historico.append({"role": "user", "texto": texto})
        # Mantém só os últimos MAX_HISTORICO turnos
        if len(historico) > MAX_HISTORICO * 2:
            historico = historico[-(MAX_HISTORICO * 2):]

        intencao = interpretar_comando(texto)
        tipo     = intencao.get("tipo")

        _falar("", "separador") if tipo != "sair" else None

        # Resposta inicial imediata
        if intencao.get("resposta"):
            _falar(intencao["resposta"])

        # ── Despacha por tipo ────────────────────────

        if tipo == "sair":
            _falar(intencao["resposta"])
            print()
            sys.exit(0)

        elif tipo == "workflow":
            nome = intencao.get("workflow", "")
            resposta = _executar_workflow(nome)
            _falar(resposta)

        elif tipo == "comando":
            acao = intencao.get("acao", "")
            kwargs = {k: v for k, v in intencao.items()
                      if k not in ("tipo", "acao", "resposta", "palavras")}
            resultado = enviar_comando(acao, **kwargs)
            if resultado.get("sucesso"):
                _falar(f"Feito. {resultado.get('mensagem','')[:80]}")
            else:
                _falar(f"Falha: {resultado.get('mensagem','erro desconhecido')}", "erro")

        elif tipo == "observe":
            resposta = _executar_observe()
            _falar(resposta)

        elif tipo == "screenshot":
            resposta = _executar_screenshot()
            _falar(resposta)

        elif tipo == "clicar_texto":
            alvo = intencao.get("alvo", "")
            resposta = _executar_clicar_texto(alvo)
            _falar(resposta)

        elif tipo == "contexto":
            _falar("Consultando histórico e configurações...", "dim")
            ctx = gerar_contexto_estrategico()
            print(f"\n{COR_DIM}{ctx}{RESET}\n")

        elif tipo == "status":
            _falar(_executar_status())

        elif tipo == "listar":
            workflows = listar_workflows()
            _falar(f"{len(workflows)} workflow(s) disponível(is):")
            for w in workflows:
                _falar(f"  • {w}", "dim")

        elif tipo == "limpar":
            limpar_estado()
            _falar("Estado operacional resetado.")

        elif tipo == "ajuda":
            _falar(intencao["resposta"])
            for cmd, desc in AJUDA:
                print(f"  {COR_DIM}{cmd:<40}{RESET} {desc}")
            print()

        elif tipo == "desconhecido":
            # ── Fallback Gemini ────────────────────────────
            gem      = responder_com_gemini(texto, historico)
            gem      = normalizar_parametros_comando(gem)   # ← defesa local
            tipo_gem = gem.get("tipo", "erro")
            params   = gem.get("parametros", {})

            # Resposta do Gemini primeiro
            if gem.get("resposta"):
                _falar(gem["resposta"], "gemini")

            # Executa a ação que o Gemini decidiu
            if tipo_gem == "workflow" and gem.get("workflow"):
                nome = gem["workflow"]
                if nome in listar_workflows():
                    resposta = _executar_workflow(nome, ctx=params)
                    _falar(resposta)
                else:
                    _falar(f"Workflow '{nome}' não existe.", "erro")

            elif tipo_gem == "comando" and gem.get("acao"):
                resultado = enviar_comando(gem["acao"], **params)
                if resultado.get("sucesso"):
                    _falar(f"Feito. {resultado.get('mensagem','')[:80]}")
                else:
                    _falar(f"Falha: {resultado.get('mensagem','')}", "erro")

            elif tipo_gem == "observe":
                ctx = params.get("contexto", "gemini_fallback")
                _falar(_executar_observe(ctx))

            elif tipo_gem == "clicar_texto":
                alvo = params.get("alvo", "")
                _falar(_executar_clicar_texto(alvo))

            elif tipo_gem == "screenshot":
                _falar(_executar_screenshot())

            elif tipo_gem == "status":
                _falar(_executar_status())

            elif tipo_gem == "sair":
                _falar("Encerrando sistemas. Até logo.")
                print()
                sys.exit(0)

            elif tipo_gem in ("resposta", "erro"):
                pass  # resposta já impressa acima

            # Adiciona resposta do Jarvis ao histórico
            historico.append({"role": "jarvis", "texto": gem.get("resposta", "")})

        print()


# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":
    try:
        iniciar()
    except KeyboardInterrupt:
        print(f"\n{COR_DIM}")
        _falar("Interrompido. Encerrando sistemas.")
        print(RESET)
        sys.exit(0)