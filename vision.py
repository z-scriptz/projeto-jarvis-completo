# automation/vision.py
# Camada de visão do AgenteIA — roda no WINDOWS
# O agente passa a enxergar a tela antes e depois das ações.
#
# Dependências:
#   pip install pyautogui pillow opencv-python
#
# IMPORTANTE: pyautogui.locateOnScreen precisa do opencv-python para
# funcionar com confidence < 1.0 (matching por semelhança visual)

import time
from pathlib import Path
from typing import Optional, Tuple

import pyautogui

from shared.logger import get_logger

log = get_logger(__name__)

# =========================
# CONFIGURAÇÃO
# =========================

# Pasta de screenshots no Windows
SCREENSHOTS_DIR = Path(r"C:\AgenteIA\logs\screenshots")

# Segurança sempre ativa
pyautogui.FAILSAFE = True


# =========================
# FUNÇÕES DE VISÃO
# =========================

def tirar_screenshot(nome: str = "") -> str:
    """
    Tira screenshot da tela atual e salva em C:\\AgenteIA\\logs\\screenshots.

    Args:
        nome: nome do arquivo sem extensão (padrão: timestamp)

    Returns:
        Caminho completo do arquivo salvo (string)

    Uso:
        caminho = tirar_screenshot("antes_de_clicar")
    """
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    if not nome:
        nome = f"screen_{int(time.time())}"

    # Garante nome seguro para arquivo
    nome_limpo = "".join(c if c.isalnum() or c in "-_" else "_" for c in nome)
    caminho = SCREENSHOTS_DIR / f"{nome_limpo}.png"

    try:
        img = pyautogui.screenshot()
        img.save(str(caminho))
        log.info(f"📸 Screenshot salvo: {caminho}")
        return str(caminho)
    except Exception as e:
        log.error(f"Erro ao tirar screenshot: {e}")
        raise


def localizar_imagem(
    caminho_imagem: str,
    confidence: float = 0.8,
    regiao: Optional[Tuple[int, int, int, int]] = None,
) -> Optional[Tuple[int, int]]:
    """
    Localiza uma imagem na tela e retorna o centro (x, y).

    Args:
        caminho_imagem: caminho para o arquivo .png de referência
        confidence: 0.0 a 1.0 — quão parecido precisa ser (padrão 0.8)
        regiao: (left, top, width, height) para limitar a busca na tela

    Returns:
        Tupla (x, y) do centro da imagem encontrada, ou None se não encontrar

    Uso:
        pos = localizar_imagem(r"C:\\AgenteIA\\refs\\botao_postar.png")
        if pos:
            print(f"Encontrado em {pos}")
    """
    if not Path(caminho_imagem).exists():
        log.error(f"Imagem de referência não encontrada: {caminho_imagem}")
        return None

    try:
        resultado = pyautogui.locateCenterOnScreen(
            caminho_imagem,
            confidence=confidence,
            region=regiao,
        )
        if resultado:
            x, y = int(resultado.x), int(resultado.y)
            log.info(f"🎯 Imagem localizada em ({x}, {y}): {Path(caminho_imagem).name}")
            return (x, y)
        else:
            log.warning(f"🔍 Imagem não encontrada na tela: {Path(caminho_imagem).name}")
            return None

    except pyautogui.ImageNotFoundException:
        log.warning(f"🔍 Imagem não encontrada (confidence={confidence}): {Path(caminho_imagem).name}")
        return None
    except Exception as e:
        log.error(f"Erro ao localizar imagem: {e}")
        return None


def clicar_imagem(
    caminho_imagem: str,
    confidence: float = 0.8,
    duplo: bool = False,
    aguardar_antes: float = 0.5,
) -> dict:
    """
    Localiza uma imagem na tela e clica no centro dela.

    Args:
        caminho_imagem: caminho para o .png de referência
        confidence: precisão do matching (padrão 0.8)
        duplo: True para duplo clique
        aguardar_antes: segundos de espera antes de clicar

    Returns:
        dict com sucesso, mensagem, e coordenadas (x, y) ou None

    Uso:
        resultado = clicar_imagem(r"C:\\AgenteIA\\refs\\btn_publicar.png")
    """
    time.sleep(aguardar_antes)

    pos = localizar_imagem(caminho_imagem, confidence)

    if pos is None:
        return {
            "sucesso": False,
            "mensagem": f"Imagem não encontrada na tela: {Path(caminho_imagem).name}",
            "coordenadas": None,
        }

    x, y = pos
    try:
        pyautogui.moveTo(x, y, duration=0.4)
        if duplo:
            pyautogui.doubleClick(x, y)
            acao = "Duplo clique"
        else:
            pyautogui.click(x, y)
            acao = "Clique"

        msg = f"🖱️ {acao} em ({x}, {y}) — {Path(caminho_imagem).name}"
        log.info(msg)
        return {"sucesso": True, "mensagem": msg, "coordenadas": (x, y)}

    except Exception as e:
        log.error(f"Erro ao clicar na imagem: {e}")
        return {"sucesso": False, "mensagem": str(e), "coordenadas": None}


def observar_tela(contexto: str = "") -> str:
    """
    Tira screenshot da tela atual e retorna o caminho.
    Uso principal: o WSL/Gemini analisa a imagem depois para decidir
    o que fazer a seguir.

    Args:
        contexto: descrição do momento (ex: "apos_abrir_tiktok")

    Returns:
        Caminho da screenshot (para o WSL ler)

    Uso:
        caminho = observar_tela("antes_de_postar")
        # WSL recebe o caminho e manda o Gemini analisar
    """
    nome = f"obs_{contexto}_{int(time.time())}" if contexto else ""
    return tirar_screenshot(nome)


def aguardar_imagem(
    caminho_imagem: str,
    timeout: float = 15.0,
    confidence: float = 0.8,
    intervalo: float = 1.0,
) -> Optional[Tuple[int, int]]:
    """
    Fica tentando localizar uma imagem até ela aparecer ou dar timeout.
    Útil para aguardar carregamentos de página ou modais.

    Args:
        timeout: tempo máximo de espera em segundos
        intervalo: segundos entre cada tentativa

    Returns:
        (x, y) quando encontrar, None se timeout
    """
    inicio = time.time()
    tentativa = 0

    while time.time() - inicio < timeout:
        tentativa += 1
        pos = localizar_imagem(caminho_imagem, confidence)
        if pos:
            log.info(f"✅ Imagem apareceu após {tentativa} tentativa(s)")
            return pos
        log.debug(f"⏳ Aguardando imagem... tentativa {tentativa}")
        time.sleep(intervalo)

    log.warning(f"⏰ Timeout ({timeout}s) aguardando: {Path(caminho_imagem).name}")
    return None