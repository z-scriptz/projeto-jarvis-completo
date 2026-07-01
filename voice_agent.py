# voice_agent.py
# Camada de voz do AgenteIA — Jarvis Multimodal
#
# Uso:
#   python voice_agent.py
#
# Dependências:
#   pip install speechrecognition pyttsx3 pyaudio
#   sudo apt install portaudio19-dev  (WSL/Ubuntu)
#
# Fluxo:
#   Microfone → Speech-to-Text → interpretar_comando / Gemini → Text-to-Speech

import os
import sys
import time
import threading

# ── Importações de voz ──────────────────────────────
try:
    import speech_recognition as sr
except ImportError:
    print("❌ Instale: pip install speechrecognition pyaudio")
    sys.exit(1)

try:
    import pyttsx3
except ImportError:
    print("❌ Instale: pip install pyttsx3")
    sys.exit(1)

# ── Reutiliza todo o cérebro do chat_agent ──────────
from chat_agent import (
    interpretar_comando,
    responder_com_gemini,
    normalizar_parametros_comando,
    _executar_workflow,
    _executar_observe,
    _executar_screenshot,
    _executar_clicar_texto,
    _executar_status,
    _falar,
    COR_IA, COR_EU, COR_DIM, COR_ERR, COR_GEM, RESET,
    MAX_HISTORICO,
    AJUDA,
)
from workflows.engine      import listar_workflows, executar_workflow
from brain.commander       import enviar_comando
from analytics.context_engine import gerar_contexto_estrategico
from memory.state_manager  import carregar_estado, limpar_estado
from shared.logger         import get_logger

log = get_logger("voice_agent")

# =========================
# CONFIGURAÇÃO DE VOZ
# =========================

WAKE_WORD        = "jarvis"
IDIOMA_STT       = "pt-BR"           # Speech-to-Text em português
TIMEOUT_ESCUTA   = 5                  # segundos aguardando fala
DURACAO_FRASE    = 8                  # segundos máximos por frase
VOZ_VELOCIDADE   = 175                # palavras por minuto (pyttsx3)
VOZ_VOLUME       = 0.95              # 0.0 a 1.0
COOLDOWN_COMANDO = 1.0               # segundos mínimos entre comandos

# True  → exige "Jarvis" antes de cada comando
# False → qualquer frase reconhecida vira comando (modo livre)
MODO_WAKE_WORD = False

# Comandos curtos aceitos mesmo sem wake word e com < 2 palavras
COMANDOS_CURTOS = {"status", "sair", "ajuda", "parar", "pausa"}

# =========================
# MOTOR DE VOZ (TTS)
# =========================

_engine_tts = None
_tts_lock   = threading.Lock()


def _iniciar_tts() -> pyttsx3.Engine:
    """Inicializa o motor de Text-to-Speech."""
    global _engine_tts
    engine = pyttsx3.init()
    engine.setProperty("rate",   VOZ_VELOCIDADE)
    engine.setProperty("volume", VOZ_VOLUME)

    # Tenta selecionar voz em português
    vozes = engine.getProperty("voices")
    for voz in vozes:
        if "brazil" in voz.id.lower() or "pt" in voz.id.lower():
            engine.setProperty("voice", voz.id)
            log.info(f"🎙️ Voz selecionada: {voz.name}")
            break

    _engine_tts = engine
    return engine


def falar_audio(texto: str, imprimir: bool = True):
    """
    Converte texto em fala via pyttsx3 (offline).
    Thread-safe via lock.

    Args:
        texto:     texto a ser falado
        imprimir:  se True, imprime no terminal também
    """
    if imprimir:
        _falar(texto, "ia")

    # Remove emojis — pyttsx3 não lida bem com eles
    texto_limpo = _remover_emojis(texto)
    if not texto_limpo.strip():
        return

    with _tts_lock:
        try:
            if _engine_tts is None:
                _iniciar_tts()
            _engine_tts.say(texto_limpo)
            _engine_tts.runAndWait()
        except Exception as e:
            log.warning(f"TTS falhou (silencioso): {e}")


def _remover_emojis(texto: str) -> str:
    """Remove caracteres não-ASCII que travam o pyttsx3."""
    return texto.encode("ascii", "ignore").decode("ascii")


# =========================
# MOTOR DE ESCUTA (STT)
# =========================

def ouvir_microfone(
    timeout: float = TIMEOUT_ESCUTA,
    duracao: float = DURACAO_FRASE,
    calibrar: bool = False,
) -> str | None:
    """
    Captura áudio do microfone e converte para texto via Google STT.

    Args:
        timeout:  segundos aguardando início da fala
        duracao:  duração máxima da frase em segundos
        calibrar: se True, ajusta ruído ambiente antes de escutar

    Returns:
        Texto reconhecido (str) ou None se silêncio/erro
    """
    reconhecedor = sr.Recognizer()
    reconhecedor.pause_threshold = 0.8   # pausa antes de considerar fim da frase

    with sr.Microphone() as fonte:
        if calibrar:
            print(f"{COR_DIM}  ↳ Calibrando ruído ambiente...{RESET}", end="\r")
            reconhecedor.adjust_for_ambient_noise(fonte, duration=1)

        print(f"{COR_EU}[ouvindo]{RESET} ", end="", flush=True)

        try:
            audio = reconhecedor.listen(
                fonte,
                timeout=timeout,
                phrase_time_limit=duracao,
            )
        except sr.WaitTimeoutError:
            print()  # limpa linha
            return None

    # Transcrição via Google STT (online, gratuito)
    try:
        texto = reconhecedor.recognize_google(audio, language=IDIOMA_STT)
        print(f"{COR_EU}Você: {texto}{RESET}")
        log.info(f"STT: '{texto}'")
        return texto.lower().strip()

    except sr.UnknownValueError:
        print(f"{COR_DIM}  ↳ Não entendi. Tente novamente.{RESET}")
        return None
    except sr.RequestError as e:
        print(f"{COR_ERR}  ↳ Erro no serviço STT: {e}{RESET}")
        log.error(f"STT RequestError: {e}")
        return None


# =========================
# WAKE WORD
# =========================

def contem_wake_word(texto: str) -> bool:
    """Verifica se o texto contém a wake word 'jarvis'."""
    return WAKE_WORD in texto.lower()


def remover_wake_word(texto: str) -> str:
    """Remove 'jarvis' do início do texto para processar o comando limpo."""
    lower = texto.lower()
    for variante in (f"{WAKE_WORD}, ", f"{WAKE_WORD} ", WAKE_WORD):
        if lower.startswith(variante):
            return texto[len(variante):].strip()
    return texto.strip()


# =========================
# PROCESSADOR DE COMANDO DE VOZ
# =========================

def processar_comando_voz(texto: str, historico: list) -> str:
    """
    Interpreta o texto transcrito e executa a ação correspondente.
    Reutiliza toda a lógica do chat_agent.py.

    Args:
        texto:     comando já sem a wake word
        historico: histórico da sessão para o Gemini

    Returns:
        Resposta em texto para ser falada e impressa
    """
    historico.append({"role": "user", "texto": texto})
    if len(historico) > MAX_HISTORICO * 2:
        historico[:] = historico[-(MAX_HISTORICO * 2):]

    intencao = interpretar_comando(texto)
    tipo     = intencao.get("tipo")

    # ── Intenções fixas ──────────────────────────────

    if tipo == "sair":
        falar_audio("Encerrando sistemas. Até logo.")
        sys.exit(0)

    elif tipo == "workflow":
        nome = intencao.get("workflow", "")
        return _executar_workflow(nome)

    elif tipo == "comando":
        acao   = intencao.get("acao", "")
        kwargs = {k: v for k, v in intencao.items()
                  if k not in ("tipo", "acao", "resposta", "palavras")}
        resultado = enviar_comando(acao, **kwargs)
        if resultado.get("sucesso"):
            return f"Feito. {resultado.get('mensagem','')[:60]}"
        return f"Falha: {resultado.get('mensagem','erro')[:60]}"

    elif tipo == "observe":
        return _executar_observe("voz_manual")

    elif tipo == "screenshot":
        return _executar_screenshot()

    elif tipo == "clicar_texto":
        alvo = intencao.get("alvo", "")
        return _executar_clicar_texto(alvo)

    elif tipo == "status":
        return _executar_status()

    elif tipo == "contexto":
        ctx = gerar_contexto_estrategico()
        # Versão curta para voz
        linhas = [l for l in ctx.split("\n") if l.strip()][:5]
        return " | ".join(linhas)

    elif tipo == "listar":
        wfs = listar_workflows()
        return f"Tenho {len(wfs)} workflow disponíveis: {', '.join(wfs)}"

    elif tipo == "limpar":
        limpar_estado()
        return "Estado operacional resetado."

    elif tipo == "ajuda":
        return "Posso abrir plataformas, observar a tela, executar workflows e responder perguntas. Diga Jarvis seguido do comando."

    # ── Fallback Gemini ──────────────────────────────
    elif tipo == "desconhecido":
        gem      = responder_com_gemini(texto, historico)
        gem      = normalizar_parametros_comando(gem)   # ← defesa local
        tipo_gem = gem.get("tipo", "erro")
        params   = gem.get("parametros", {})
        resposta_inicial = gem.get("resposta", "")

        print(
            f"{COR_DIM}  🧠 Gemini: tipo={tipo_gem}"
            + (f" | ▶ {gem.get('acao')}" if gem.get("acao") else "")
            + (f" | 📋 {gem.get('workflow')}" if gem.get("workflow") else "")
            + RESET
        )

        if tipo_gem == "workflow" and gem.get("workflow"):
            nome = gem["workflow"]
            if nome in listar_workflows():
                _executar_workflow(nome, ctx=params)
                return resposta_inicial or f"Executando {nome}."
            return f"Workflow {nome} não encontrado."

        elif tipo_gem == "comando" and gem.get("acao"):
            resultado = enviar_comando(gem["acao"], **params)
            acao_msg  = f"Feito." if resultado.get("sucesso") else f"Falha."
            return resposta_inicial or acao_msg

        elif tipo_gem == "observe":
            tela = _executar_observe(params.get("contexto", "voz_gemini"))
            return tela

        elif tipo_gem == "status":
            return _executar_status()

        elif tipo_gem == "sair":
            falar_audio("Encerrando sistemas. Até logo.")
            sys.exit(0)

        return resposta_inicial or "Entendido."

    return "Comando não reconhecido."


# =========================
# CONTROLE DE MODO E VALIDAÇÃO
# =========================

def _checar_controle_modo(texto: str) -> bool:
    """
    Verifica se o texto muda o modo de escuta.
    Retorna True se foi um comando de controle (não processar como ação).
    """
    global MODO_WAKE_WORD

    if "ativar wake word" in texto:
        MODO_WAKE_WORD = True
        msg = "Modo wake word ativado. Diga Jarvis antes de cada comando."
        print(f"{COR_DIM}  ↳ {msg}{RESET}")
        falar_audio(msg)
        return True

    if any(p in texto for p in ("desativar wake word", "modo livre")):
        MODO_WAKE_WORD = False
        msg = "Modo livre ativado. Pode falar diretamente."
        print(f"{COR_DIM}  ↳ {msg}{RESET}")
        falar_audio(msg)
        return True

    return False


def _frase_valida(texto: str) -> bool:
    """
    No modo livre, valida se a frase merece ser processada.
    Aceita: frases com 2+ palavras OU comandos curtos conhecidos.
    """
    palavras = texto.strip().split()
    if len(palavras) >= 2:
        return True
    # Comando de uma palavra — aceita só se for da whitelist
    return texto.strip().lower() in COMANDOS_CURTOS


# =========================
# LOOP PRINCIPAL DE VOZ
# =========================

def iniciar_voz():
    """Loop principal do agente de voz."""
    global MODO_WAKE_WORD

    modo_label = f"wake word '{WAKE_WORD.upper()}'" if MODO_WAKE_WORD else "LIVRE (sem wake word)"

    print(f"\n{COR_IA}{'═' * 50}")
    print(f"  Jarvis — Voice Agent v1.1")
    print(f"  Modo: {modo_label}")
    print(f"  Idioma: {IDIOMA_STT}")
    print(f"{'═' * 50}{RESET}\n")

    _iniciar_tts()

    abertura = (
        f"Jarvis online. Modo {'wake word' if MODO_WAKE_WORD else 'livre'} ativado."
    )
    falar_audio(abertura)

    print(f"{COR_DIM}  ↳ Calibrando microfone...{RESET}")
    ouvir_microfone(timeout=2, calibrar=True)

    dica = (
        f"Diga '{WAKE_WORD.title()} [comando]'"
        if MODO_WAKE_WORD
        else "Pode falar diretamente. Ex: 'abrir TikTok', 'observar tela'"
    )
    print(f"{COR_DIM}  ↳ Pronto. {dica}{RESET}\n")

    historico:          list  = []
    falhas_consecutivas: int  = 0
    ultimo_comando:     float = 0.0
    MAX_FALHAS = 5

    while True:
        try:
            texto = ouvir_microfone(
                calibrar=(falhas_consecutivas >= MAX_FALHAS)
            )

            if not texto:
                falhas_consecutivas += 1
                continue

            falhas_consecutivas = 0

            # ── Controle de modo (sempre verificado) ──
            if _checar_controle_modo(texto):
                modo_label = f"wake word '{WAKE_WORD.upper()}'" if MODO_WAKE_WORD else "LIVRE"
                print(f"{COR_DIM}  ↳ Modo atual: {modo_label}{RESET}\n")
                continue

            # ── Cooldown entre comandos ────────────────
            agora = time.time()
            if agora - ultimo_comando < COOLDOWN_COMANDO:
                print(f"{COR_DIM}  ↳ Cooldown ativo — aguarde {COOLDOWN_COMANDO}s{RESET}")
                continue

            # ── Roteamento por modo ────────────────────
            if MODO_WAKE_WORD:
                # Exige wake word
                if not contem_wake_word(texto):
                    print(f"{COR_DIM}  ↳ Aguardando '{WAKE_WORD.title()}...'{RESET}")
                    continue
                comando = remover_wake_word(texto)
                if not comando:
                    falar_audio("Sim? Como posso ajudar?")
                    continue
            else:
                # Modo livre — valida frase mínima
                if not _frase_valida(texto):
                    print(f"{COR_DIM}  ↳ Frase muito curta — ignorada: '{texto}'{RESET}")
                    continue
                # Remove wake word se o usuário disse mesmo assim (hábito)
                comando = remover_wake_word(texto) if contem_wake_word(texto) else texto

            # ── Processa comando ───────────────────────
            print(f"{COR_DIM}{'─' * 50}{RESET}")
            ultimo_comando = time.time()

            resposta = processar_comando_voz(comando, historico)
            historico.append({"role": "jarvis", "texto": resposta})

            falar_audio(resposta)
            print()

        except KeyboardInterrupt:
            falar_audio("Encerrando Jarvis. Até logo.")
            sys.exit(0)
        except Exception as e:
            log.error(f"Erro no loop de voz: {e}")
            print(f"{COR_ERR}  ↳ Erro: {e}{RESET}")
            time.sleep(1)


# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":
    iniciar_voz()