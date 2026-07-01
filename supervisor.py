# supervisor.py
# Supervisor 24/7 do AgenteIA
# Monitora processos principais e reinicia automaticamente se caírem.
#
# Uso:
#   python supervisor.py
#   CTRL+C para encerrar tudo

import os
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime

# =========================
# CONFIGURAÇÃO — edite aqui
# =========================

ENABLE_EXECUTOR   = True    # executor_main.py (Windows — roda via python)
ENABLE_VOICE      = True    # voice_agent.py
ENABLE_MAIN_LOOP  = False   # main.py --loop (processamento autônomo da fila)

CICLO_SEGUNDOS    = 10      # intervalo entre verificações
MAX_RESTARTS      = 10      # máximo de reinícios por processo (0 = ilimitado)
COOLDOWN_RESTART  = 5       # segundos de espera antes de reiniciar

# =========================
# CAMINHOS
# =========================

BASE_DIR  = Path(__file__).parent
LOGS_DIR  = BASE_DIR / "logs"
LOG_FILE  = LOGS_DIR / "supervisor.log"

PYTHON    = sys.executable  # mesmo python do ambiente atual

# =========================
# CORES DO TERMINAL
# =========================

VERDE  = "\033[92m"
AMARELO= "\033[93m"
VERMELHO="\033[91m"
CIANO  = "\033[96m"
DIM    = "\033[90m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


# =========================
# DEFINIÇÃO DOS PROCESSOS
# =========================

PROCESSOS = []

if ENABLE_EXECUTOR:
    PROCESSOS.append({
        "nome":    "executor",
        "cmd":     [PYTHON, str(BASE_DIR / "executor_main.py")],
        "descricao": "Executor Windows (mouse/teclado)",
    })

if ENABLE_VOICE:
    PROCESSOS.append({
        "nome":    "voice_agent",
        "cmd":     [PYTHON, str(BASE_DIR / "voice_agent.py")],
        "descricao": "Jarvis Voice Agent",
    })

if ENABLE_MAIN_LOOP:
    PROCESSOS.append({
        "nome":    "main_loop",
        "cmd":     [PYTHON, str(BASE_DIR / "main.py"), "--loop"],
        "descricao": "Loop autônomo THINK→ACT→OBSERVE",
    })


# =========================
# LOGGER DO SUPERVISOR
# =========================

def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(msg: str, nivel: str = "INFO"):
    linha = f"[{_ts()}] [{nivel}] {msg}"
    # Terminal
    cor = {
        "INFO":    VERDE,
        "WARN":    AMARELO,
        "ERROR":   VERMELHO,
        "START":   CIANO,
        "RESTART": AMARELO,
    }.get(nivel, RESET)
    print(f"{cor}{linha}{RESET}")
    # Arquivo
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass


# =========================
# ESTADO DOS PROCESSOS
# =========================

# Dicionário: nome → { processo: Popen, restarts: int, iniciado_em: float }
_estado: dict[str, dict] = {}


def _processo_vivo(nome: str) -> bool:
    """Verifica se o processo está rodando (poll() == None)."""
    entrada = _estado.get(nome)
    if not entrada or entrada.get("processo") is None:
        return False
    proc = entrada["processo"]
    return proc.poll() is None


def _iniciar(cfg: dict) -> bool:
    """
    Inicia um processo pela primeira vez.
    Retorna True se iniciou com sucesso.
    """
    nome = cfg["nome"]

    # Guarda de duplicata — não abre se já estiver vivo
    if _processo_vivo(nome):
        return True

    try:
        proc = subprocess.Popen(
            cfg["cmd"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(BASE_DIR),
        )
        _estado[nome] = {
            "processo":    proc,
            "restarts":    _estado.get(nome, {}).get("restarts", 0),
            "iniciado_em": time.time(),
            "cfg":         cfg,
        }
        _log(f"[START] '{nome}' iniciado — PID {proc.pid} | {cfg['descricao']}", "START")
        return True
    except FileNotFoundError:
        _log(f"Script não encontrado: {cfg['cmd'][1]}", "ERROR")
        return False
    except Exception as e:
        _log(f"Erro ao iniciar '{nome}': {e}", "ERROR")
        return False


def _reiniciar(nome: str) -> bool:
    """
    Encerra processo existente (se ainda ativo) e reinicia.
    Aplica cooldown e verifica limite de restarts.
    """
    entrada = _estado.get(nome, {})
    cfg     = entrada.get("cfg")
    if not cfg:
        return False

    restarts = entrada.get("restarts", 0)

    # Limite de restarts
    if MAX_RESTARTS > 0 and restarts >= MAX_RESTARTS:
        _log(
            f"'{nome}' atingiu limite de {MAX_RESTARTS} reinícios — desativando.",
            "ERROR"
        )
        return False

    # Mata processo zumbi se ainda existir
    proc = entrada.get("processo")
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    _log(f"[RESTART] '{nome}' encerrou — reiniciando em {COOLDOWN_RESTART}s... (restart #{restarts + 1})", "RESTART")
    time.sleep(COOLDOWN_RESTART)

    try:
        novo_proc = subprocess.Popen(
            cfg["cmd"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(BASE_DIR),
        )
        _estado[nome] = {
            "processo":    novo_proc,
            "restarts":    restarts + 1,
            "iniciado_em": time.time(),
            "cfg":         cfg,
        }
        _log(f"'{nome}' reiniciado — PID {novo_proc.pid}", "INFO")
        return True
    except Exception as e:
        _log(f"Falha ao reiniciar '{nome}': {e}", "ERROR")
        return False


def _encerrar_tudo():
    """Encerra todos os processos supervisionados."""
    _log("Encerrando todos os processos supervisionados...", "WARN")
    for nome, entrada in _estado.items():
        proc = entrada.get("processo")
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
                _log(f"  '{nome}' encerrado (PID {proc.pid})", "WARN")
            except Exception:
                try:
                    proc.kill()
                    _log(f"  '{nome}' forçado a encerrar", "WARN")
                except Exception:
                    pass


# =========================
# EXIBIÇÃO DE STATUS
# =========================

def _exibir_status(ciclo: int):
    """Imprime tabela de status no terminal."""
    print(f"\n{DIM}{'─' * 55}{RESET}")
    print(f"{BOLD}  Supervisor AgenteIA — ciclo #{ciclo} | {_ts()}{RESET}")
    print(f"{DIM}{'─' * 55}{RESET}")

    for nome, entrada in _estado.items():
        proc     = entrada.get("processo")
        vivo     = proc and proc.poll() is None
        pid      = proc.pid if proc else "—"
        restarts = entrada.get("restarts", 0)
        uptime   = int(time.time() - entrada.get("iniciado_em", time.time()))
        cfg      = entrada.get("cfg", {})

        status_cor   = VERDE if vivo else VERMELHO
        status_label = "● ONLINE" if vivo else "✗ OFFLINE"

        print(
            f"  {status_cor}{status_label}{RESET} "
            f"{nome:<16} "
            f"{DIM}PID:{pid:<8} restarts:{restarts:<4} uptime:{uptime}s{RESET}"
        )

    if not _estado:
        print(f"  {AMARELO}Nenhum processo configurado.{RESET}")

    print(f"{DIM}{'─' * 55}{RESET}")
    print(f"{DIM}  Próxima verificação em {CICLO_SEGUNDOS}s | CTRL+C para encerrar{RESET}\n")


# =========================
# LOOP PRINCIPAL
# =========================

def iniciar_supervisor():
    print(f"\n{CIANO}{'═' * 55}")
    print(f"  AgenteIA Supervisor v1.0")
    print(f"  Processos: {len(PROCESSOS)} | Ciclo: {CICLO_SEGUNDOS}s")
    print(f"  Log: {LOG_FILE}")
    print(f"{'═' * 55}{RESET}\n")

    if not PROCESSOS:
        print(f"{AMARELO}Nenhum processo habilitado. Edite as variáveis ENABLE_* no topo do arquivo.{RESET}")
        sys.exit(0)

    _log(f"Supervisor iniciado | {len(PROCESSOS)} processo(s) configurado(s)", "INFO")

    # Início inicial de todos os processos
    for cfg in PROCESSOS:
        _iniciar(cfg)
        time.sleep(1)  # escalonado para não sobrecarregar

    ciclo = 0

    try:
        while True:
            ciclo += 1
            _exibir_status(ciclo)

            # Verifica cada processo
            for nome, entrada in list(_estado.items()):
                if not _processo_vivo(nome):
                    _reiniciar(nome)

            time.sleep(CICLO_SEGUNDOS)

    except KeyboardInterrupt:
        print(f"\n{AMARELO}CTRL+C detectado — encerrando supervisor...{RESET}")
        _encerrar_tudo()
        _log("Supervisor encerrado pelo usuário", "WARN")
        print(f"{VERDE}Todos os processos encerrados. Até logo.{RESET}\n")
        sys.exit(0)


# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":
    iniciar_supervisor()