# health_check.py
# Diagnóstico completo do AgenteIA
#
# Uso:
#   python health_check.py
#   python health_check.py --verbose

import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

# =========================
# CORES
# =========================

VERDE   = "\033[92m"
AMARELO = "\033[93m"
VERMELHO= "\033[91m"
CIANO   = "\033[96m"
DIM     = "\033[90m"
BOLD    = "\033[1m"
RESET   = "\033[0m"

OK   = f"{VERDE}✅{RESET}"
WARN = f"{AMARELO}⚠️ {RESET}"
FAIL = f"{VERMELHO}❌{RESET}"

BASE_DIR  = Path(__file__).parent
LOGS_DIR  = BASE_DIR / "logs"
LOG_FILE  = LOGS_DIR / "health_check.log"

VERBOSE = False  # definido pelo argparse


# =========================
# HELPERS DE RESULTADO
# =========================

_resultados: list[dict] = []


def _check(nome: str, status: str, detalhe: str = "", critico: bool = False):
    """
    Registra resultado de um check.
    status: "ok" | "warn" | "fail"
    """
    icone = {"ok": OK, "warn": WARN, "fail": FAIL}.get(status, WARN)
    _resultados.append({"nome": nome, "status": status, "detalhe": detalhe, "critico": critico})
    linha_detalhe = f" {DIM}({detalhe}){RESET}" if detalhe else ""
    print(f"  {icone} {nome}{linha_detalhe}")
    if VERBOSE and detalhe:
        print(f"     {DIM}↳ {detalhe}{RESET}")


def _secao(titulo: str):
    print(f"\n{CIANO}{BOLD}  {titulo}{RESET}")
    print(f"  {DIM}{'─' * 45}{RESET}")


def _salvar_log(conteudo: str):
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(conteudo + "\n")
    except Exception:
        pass


# =========================
# CHECKS
# =========================

def check_python():
    _secao("1. Ambiente Python")
    v = sys.version_info
    versao = f"{v.major}.{v.minor}.{v.micro}"

    if v.major == 3 and v.minor >= 10:
        _check("Python versão", "ok", versao)
    else:
        _check("Python versão", "warn", f"{versao} — recomendado 3.10+")

    venv = os.getenv("VIRTUAL_ENV") or os.getenv("CONDA_DEFAULT_ENV")
    if venv:
        _check("Ambiente virtual", "ok", Path(venv).name)
    else:
        _check("Ambiente virtual", "warn", "Nenhum venv detectado — recomendado usar um")


def check_env_vars():
    _secao("2. Variáveis de Ambiente")
    variaveis = {
        "GEMINI_API_KEY": True,   # True = crítica
    }
    for var, critica in variaveis.items():
        val = os.getenv(var, "")
        if val:
            preview = val[:6] + "..." + val[-4:] if len(val) > 12 else "***"
            _check(var, "ok", preview, critico=critica)
        else:
            _check(var, "fail" if critica else "warn",
                   "Não definida — export no terminal", critico=critica)


def check_pastas():
    _secao("3. Estrutura de Pastas")
    pastas = ["logs", "workflows", "refs", "memory", "brain", "analytics",
              "executor", "automation", "shared", "prompts"]
    for pasta in pastas:
        caminho = BASE_DIR / pasta
        if caminho.exists():
            _check(f"/{pasta}", "ok")
        else:
            critica = pasta in ("brain", "memory", "workflows", "executor")
            _check(f"/{pasta}", "fail" if critica else "warn",
                   "Pasta não encontrada", critico=critica)


def check_arquivos():
    _secao("4. Arquivos Críticos")
    arquivos = {
        "main.py":          True,
        "chat_agent.py":    True,
        "voice_agent.py":   False,
        "executor_main.py": True,
        "supervisor.py":    False,
        "health_check.py":  False,
        "credentials.json": False,
    }
    for arq, critico in arquivos.items():
        caminho = BASE_DIR / arq
        if caminho.exists():
            tam = caminho.stat().st_size
            _check(arq, "ok", f"{tam:,} bytes")
        else:
            _check(arq, "fail" if critico else "warn",
                   "Arquivo não encontrado", critico=critico)


def check_workflows():
    _secao("5. Workflows JSON")
    pasta = BASE_DIR / "workflows"
    if not pasta.exists():
        _check("Pasta workflows/", "fail", "Não encontrada", critico=True)
        return

    jsons = list(pasta.glob("*.json"))
    if not jsons:
        _check("Workflows", "warn", "Nenhum workflow .json encontrado")
        return

    _check(f"Total workflows", "ok", f"{len(jsons)} arquivo(s)")

    for f in sorted(jsons):
        try:
            dados = json.loads(f.read_text(encoding="utf-8"))
            passos = len(dados.get("passos", []))
            nome   = dados.get("nome", f.stem)
            _check(f"  {f.name}", "ok", f"{passos} passo(s) | '{nome}'")
        except json.JSONDecodeError as e:
            _check(f"  {f.name}", "fail", f"JSON inválido: {e}", critico=True)


def check_gemini():
    _secao("6. Gemini API")
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        _check("Gemini API", "fail", "GEMINI_API_KEY não definida", critico=True)
        return

    try:
        from google import genai
        from google.genai import errors

        client   = genai.Client(api_key=api_key)
        inicio   = time.time()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Responda apenas: OK"
        )
        latencia = round((time.time() - inicio) * 1000)
        texto    = response.text.strip()

        if "ok" in texto.lower():
            _check("Gemini API", "ok", f"Resposta: '{texto}' | latência: {latencia}ms")
        else:
            _check("Gemini API", "warn", f"Resposta inesperada: '{texto[:40]}'")

    except Exception as e:
        _check("Gemini API", "fail", str(e)[:80], critico=True)


def check_sheets():
    _secao("7. Google Sheets")
    cred = BASE_DIR / "credentials.json"
    if not cred.exists():
        _check("credentials.json", "warn", "Não encontrado — Sheets desabilitado")
        return

    try:
        sys.path.insert(0, str(BASE_DIR))
        from memory.sheets_engine import conectar_planilha
        planilha = conectar_planilha()
        abas     = [ws.title for ws in planilha.worksheets()]
        _check("Google Sheets", "ok", f"Planilha acessível | abas: {abas}")
    except Exception as e:
        _check("Google Sheets", "fail", str(e)[:80])


def check_executor():
    _secao("8. Executor Windows")
    try:
        sys.path.insert(0, str(BASE_DIR))
        from shared.config import COMANDO_JSON, RESULTADO_JSON

        # Verifica se a pasta compartilhada existe (WSL → Windows)
        pasta = COMANDO_JSON.parent
        if not pasta.exists():
            _check("Pasta compartilhada", "warn",
                   f"{pasta} não encontrada — executor pode não estar rodando")
            return

        _check("Pasta compartilhada", "ok", str(pasta))

        # Testa envio de comando simples (aguardar 0s)
        from brain.commander import enviar_comando
        inicio   = time.time()
        resultado = enviar_comando("aguardar", segundos=0.1)
        latencia = round((time.time() - inicio) * 1000)

        if resultado.get("sucesso"):
            _check("Executor responde", "ok", f"latência: {latencia}ms")
        else:
            _check("Executor responde", "warn",
                   resultado.get("mensagem", "Sem resposta")[:60])

    except Exception as e:
        _check("Executor", "warn", f"Offline ou inacessível: {str(e)[:60]}")


def check_vision():
    _secao("9. Visão (Screenshot)")
    try:
        sys.path.insert(0, str(BASE_DIR))
        from brain.commander import enviar_comando

        resultado = enviar_comando("screenshot", contexto="health_check")
        if resultado.get("sucesso"):
            dados    = resultado.get("dados") or {}
            caminho  = dados if isinstance(dados, str) else str(dados)
            _check("Screenshot", "ok", f"Salvo em: {caminho[:60]}")
        else:
            _check("Screenshot", "warn",
                   resultado.get("mensagem", "Executor offline")[:60])
    except Exception as e:
        _check("Screenshot", "warn", str(e)[:60])


def check_state_manager():
    _secao("10. State Manager")
    try:
        sys.path.insert(0, str(BASE_DIR))
        from memory.state_manager import carregar_estado, ESTADO_VAZIO, STATE_FILE

        if not STATE_FILE.exists():
            _check("state.json", "warn", "Não existe ainda — será criado no primeiro ciclo")
            return

        estado = carregar_estado()
        tam    = STATE_FILE.stat().st_size

        # Valida campos obrigatórios
        campos_faltando = [k for k in ESTADO_VAZIO if k not in estado]
        if campos_faltando:
            _check("state.json estrutura", "warn",
                   f"Campos ausentes: {campos_faltando}")
        else:
            _check("state.json estrutura", "ok", "Todos os campos presentes")

        estado_atual = estado.get("estado_atual", "?")
        produto      = estado.get("produto_atual") or "—"
        etapa        = estado.get("etapa") or "ocioso"

        if estado_atual == "ocioso":
            _check("state.json conteúdo", "ok",
                   f"Agente ocioso | {tam} bytes")
        elif estado_atual == "processando":
            _check("state.json conteúdo", "warn",
                   f"Ciclo em andamento: produto='{produto}' etapa='{etapa}'")
        elif estado_atual == "erro":
            _check("state.json conteúdo", "warn",
                   f"Último ciclo terminou em erro: produto='{produto}'")
        else:
            _check("state.json conteúdo", "ok", f"estado={estado_atual} | {tam} bytes")

    except Exception as e:
        _check("State Manager", "fail", str(e)[:80], critico=True)


def check_imports():
    _secao("11. Dependências Python")
    libs = {
        "google.generativeai":  ("google-generativeai", False),
        "google.genai":         ("google-genai",         True),
        "gspread":              ("gspread",               False),
        "pyautogui":            ("pyautogui",             True),
        "speech_recognition":   ("speechrecognition",     False),
        "pyttsx3":              ("pyttsx3",               False),
        "fastapi":              ("fastapi",               True),
        "uvicorn":              ("uvicorn",               True),
        "httpx":                ("httpx",                 True),
        "undetected_chromedriver": ("undetected-chromedriver", False),
    }
    for modulo, (pip_nome, critico) in libs.items():
        try:
            __import__(modulo)
            _check(pip_nome, "ok")
        except ImportError:
            _check(pip_nome, "fail" if critico else "warn",
                   f"pip install {pip_nome}", critico=critico)


# =========================
# RESULTADO FINAL
# =========================

def exibir_resultado(duracao: float):
    total   = len(_resultados)
    oks     = sum(1 for r in _resultados if r["status"] == "ok")
    warns   = sum(1 for r in _resultados if r["status"] == "warn")
    falhas  = sum(1 for r in _resultados if r["status"] == "fail")
    criticos= sum(1 for r in _resultados if r["status"] == "fail" and r["critico"])
    score   = f"{oks}/{total}"

    print(f"\n{CIANO}{'═' * 50}{RESET}")
    print(f"{BOLD}  Resultado Final — AgenteIA Health Check{RESET}")
    print(f"{CIANO}{'═' * 50}{RESET}")
    print(f"  {OK}  OK:       {oks}")
    print(f"  {WARN} Warnings: {warns}")
    print(f"  {FAIL} Falhas:   {falhas} ({criticos} crítica(s))")
    print(f"  {DIM}Tempo: {duracao:.2f}s{RESET}")

    barra = (VERDE + "█" * oks + RESET +
             AMARELO + "▒" * warns + RESET +
             VERMELHO + "░" * falhas + RESET)
    print(f"\n  [{barra}]")

    if criticos > 0:
        print(f"\n  {VERMELHO}{BOLD}Score: {score} — Sistema com falhas críticas!{RESET}")
        print(f"  {VERMELHO}Corrija os itens ❌ antes de rodar em produção.{RESET}")
    elif warns > 0:
        print(f"\n  {AMARELO}{BOLD}Score: {score} — Sistema operacional com alertas.{RESET}")
    else:
        print(f"\n  {VERDE}{BOLD}Score: {score} — Sistema 100% operacional! ✅{RESET}")

    print(f"  {DIM}Log salvo: {LOG_FILE}{RESET}")
    print(f"{CIANO}{'═' * 50}{RESET}\n")

    # Salva log
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log = (
        f"\n[{ts}] Health Check — {score} OK | {warns} warn | {falhas} fail | {duracao:.2f}s\n"
        + "\n".join(f"  [{r['status'].upper()}] {r['nome']}: {r['detalhe']}" for r in _resultados)
    )
    _salvar_log(log)


# =========================
# ENTRY POINT
# =========================

def main():
    global VERBOSE

    parser = argparse.ArgumentParser(description="AgenteIA Health Check")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Exibe detalhes extras de cada check")
    args    = parser.parse_args()
    VERBOSE = args.verbose

    print(f"\n{CIANO}{'═' * 50}")
    print(f"  AgenteIA Health Check")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'═' * 50}{RESET}")

    inicio = time.time()

    check_python()
    check_env_vars()
    check_pastas()
    check_arquivos()
    check_workflows()
    check_imports()
    check_gemini()
    check_sheets()
    check_executor()
    check_vision()
    check_state_manager()

    exibir_resultado(round(time.time() - inicio, 2))


if __name__ == "__main__":
    main()