# executor/handlers.py
# Um handler por ação. Desacoplado, testável, expansível.
# Para adicionar nova ação: crie a função + registre no REGISTRO abaixo.

import time
import webbrowser
import subprocess
import pyautogui
from typing import Callable
from executor.actions import Comando, Resultado, TipoAcao
from automation.vision import (
    tirar_screenshot,
    localizar_imagem,
    clicar_imagem,
    observar_tela,
    aguardar_imagem,
)
from shared.logger import get_logger

log = get_logger(__name__)

# Segurança do PyAutoGUI
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.4


# =========================
# HANDLERS — MOUSE
# =========================

def handle_clicar(cmd: Comando) -> Resultado:
    if cmd.x is None or cmd.y is None:
        return Resultado(False, "❌ 'clicar' precisa de x e y", cmd.acao)
    pyautogui.click(cmd.x, cmd.y)
    return Resultado(True, f"🖱️ Clique em ({cmd.x}, {cmd.y})", cmd.acao)


def handle_duplo_clicar(cmd: Comando) -> Resultado:
    if cmd.x is None or cmd.y is None:
        return Resultado(False, "❌ 'duplo_clicar' precisa de x e y", cmd.acao)
    pyautogui.doubleClick(cmd.x, cmd.y)
    return Resultado(True, f"🖱️ Duplo clique em ({cmd.x}, {cmd.y})", cmd.acao)


def handle_mover(cmd: Comando) -> Resultado:
    if cmd.x is None or cmd.y is None:
        return Resultado(False, "❌ 'mover' precisa de x e y", cmd.acao)
    pyautogui.moveTo(cmd.x, cmd.y, duration=cmd.duracao)
    return Resultado(True, f"➡️ Mouse movido para ({cmd.x}, {cmd.y})", cmd.acao)


def handle_scroll(cmd: Comando) -> Resultado:
    clicks = cmd.extras.get("clicks", 3)
    pyautogui.scroll(clicks, x=cmd.x, y=cmd.y)
    return Resultado(True, f"🖱️ Scroll {clicks} clicks", cmd.acao)


# =========================
# HANDLERS — TECLADO
# =========================

def handle_digitar(cmd: Comando) -> Resultado:
    if not cmd.texto:
        return Resultado(False, "❌ 'digitar' precisa de texto", cmd.acao)
    pyautogui.write(cmd.texto, interval=0.05)
    return Resultado(True, f"⌨️ Digitado: {cmd.texto[:40]}...", cmd.acao)


def handle_hotkey(cmd: Comando) -> Resultado:
    if not cmd.teclas:
        return Resultado(False, "❌ 'atalho' precisa de teclas (lista)", cmd.acao)
    pyautogui.hotkey(*cmd.teclas)
    return Resultado(True, f"⌨️ Atalho: {'+'.join(cmd.teclas)}", cmd.acao)


def handle_tecla(cmd: Comando) -> Resultado:
    if not cmd.tecla:
        return Resultado(False, "❌ 'tecla' precisa do campo tecla", cmd.acao)
    pyautogui.press(cmd.tecla)
    return Resultado(True, f"⌨️ Tecla: {cmd.tecla}", cmd.acao)


# =========================
# HANDLERS — SISTEMA
# =========================

def handle_abrir_site(cmd: Comando) -> Resultado:
    if not cmd.alvo:
        return Resultado(False, "❌ 'abrir_site' precisa de alvo (URL)", cmd.acao)
    url = cmd.alvo if cmd.alvo.startswith("http") else f"https://{cmd.alvo}"
    webbrowser.open(url)
    time.sleep(2)
    return Resultado(True, f"🌐 Site aberto: {url}", cmd.acao)


def handle_abrir_programa(cmd: Comando) -> Resultado:
    if not cmd.alvo:
        return Resultado(False, "❌ 'abrir_programa' precisa de alvo", cmd.acao)
    PROGRAMAS = {
        "notepad": "notepad.exe",
        "calc": "calc.exe",
        "chrome": "chrome.exe",
        "explorer": "explorer.exe",
    }
    exe = PROGRAMAS.get(cmd.alvo.lower(), cmd.alvo)
    subprocess.Popen(exe, shell=True)
    time.sleep(2)
    return Resultado(True, f"🖥️ Programa aberto: {exe}", cmd.acao)


def handle_aguardar(cmd: Comando) -> Resultado:
    time.sleep(cmd.segundos)
    return Resultado(True, f"⏳ Aguardou {cmd.segundos}s", cmd.acao)


def handle_screenshot(cmd: Comando) -> Resultado:
    nome = cmd.extras.get("nome", cmd.contexto or "")
    caminho = tirar_screenshot(nome)
    return Resultado(True, f"📸 Screenshot salvo: {caminho}", cmd.acao, dados=caminho)


# =========================
# HANDLERS — VISÃO
# =========================

def handle_observar_tela(cmd: Comando) -> Resultado:
    """Tira screenshot com contexto nomeado e retorna caminho pro WSL/Gemini."""
    try:
        caminho = observar_tela(contexto=cmd.contexto)
        return Resultado(
            True,
            f"👁️ Tela observada: {caminho}",
            cmd.acao,
            dados={"caminho_screenshot": caminho},
        )
    except Exception as e:
        return Resultado(False, f"❌ Erro ao observar tela: {e}", cmd.acao)


def handle_localizar_imagem(cmd: Comando) -> Resultado:
    """Localiza imagem na tela e retorna coordenadas."""
    if not cmd.imagem:
        return Resultado(False, "❌ 'localizar_imagem' precisa do campo imagem", cmd.acao)

    pos = localizar_imagem(cmd.imagem, confidence=cmd.confidence)
    if pos:
        return Resultado(
            True,
            f"🎯 Imagem localizada em {pos}",
            cmd.acao,
            dados={"x": pos[0], "y": pos[1]},
        )
    return Resultado(False, f"🔍 Imagem não encontrada na tela", cmd.acao)


def handle_clicar_imagem(cmd: Comando) -> Resultado:
    """Localiza imagem e clica no centro dela."""
    if not cmd.imagem:
        return Resultado(False, "❌ 'clicar_imagem' precisa do campo imagem", cmd.acao)

    r = clicar_imagem(cmd.imagem, confidence=cmd.confidence, duplo=cmd.duplo)
    return Resultado(
        r["sucesso"],
        r["mensagem"],
        cmd.acao,
        dados={"coordenadas": r.get("coordenadas")},
    )


def handle_aguardar_imagem(cmd: Comando) -> Resultado:
    """Espera uma imagem aparecer na tela até timeout."""
    if not cmd.imagem:
        return Resultado(False, "❌ 'aguardar_imagem' precisa do campo imagem", cmd.acao)

    pos = aguardar_imagem(cmd.imagem, timeout=cmd.timeout, confidence=cmd.confidence)
    if pos:
        return Resultado(
            True,
            f"✅ Imagem apareceu em {pos}",
            cmd.acao,
            dados={"x": pos[0], "y": pos[1]},
        )
    return Resultado(False, f"⏰ Timeout: imagem não apareceu em {cmd.timeout}s", cmd.acao)


# =========================
# REGISTRO DE HANDLERS
# Mapa: TipoAcao → função handler
# =========================

REGISTRO: dict[TipoAcao, Callable[[Comando], Resultado]] = {
    TipoAcao.CLICAR:           handle_clicar,
    TipoAcao.DUPLO_CLIQUE:     handle_duplo_clicar,
    TipoAcao.MOVER:            handle_mover,
    TipoAcao.SCROLL:           handle_scroll,
    TipoAcao.DIGITAR:          handle_digitar,
    TipoAcao.HOTKEY:           handle_hotkey,
    TipoAcao.TECLA:            handle_tecla,
    TipoAcao.ABRIR_SITE:       handle_abrir_site,
    TipoAcao.ABRIR_PROGRAMA:   handle_abrir_programa,
    TipoAcao.AGUARDAR:         handle_aguardar,
    # Visão
    TipoAcao.SCREENSHOT:       handle_screenshot,
    TipoAcao.OBSERVAR_TELA:    handle_observar_tela,
    TipoAcao.CLICAR_IMAGEM:    handle_clicar_imagem,
    TipoAcao.LOCALIZAR_IMAGEM: handle_localizar_imagem,
    TipoAcao.AGUARDAR_IMAGEM:  handle_aguardar_imagem,
}