# executor/handlers_extras.py
# Handlers extras: janela ativa e clipboard.
#
# Usados pelo brain/file_dialog_uploader.py para:
#   - janela_ativa     → validar se diálogo de arquivo abriu (sem queimar Gemini)
#   - copiar_clipboard → colar caminho do vídeo via Ctrl+V (sem digitar)
#
# Sem esses handlers, o file_dialog_uploader cai pra fallback:
#   janela_ativa indisponível      → usa Gemini Vision (gasta cota)
#   copiar_clipboard indisponível  → usa digitar caractere a caractere
#
# Ambos fallbacks funcionam, mas registrar os handlers reais:
#   - economiza 1-3 chamadas Gemini por upload
#   - cola UTF-8/acentos/espaços sem problema
#   - aumenta confiabilidade

from typing import Callable
from executor.actions import Comando, Resultado, TipoAcao
from shared.logger import get_logger

log = get_logger(__name__)


# ─── Dependências externas (instalar antes de usar) ──────────────
# Windows (PowerShell ou cmd):
#   pip install pygetwindow pyperclip
#
# Se alguma não estiver instalada, o handler correspondente retorna
# erro claro em vez de quebrar o executor inteiro.

_PYGETWINDOW_DISPONIVEL = False
_PYPERCLIP_DISPONIVEL   = False

try:
    import pygetwindow as gw
    _PYGETWINDOW_DISPONIVEL = True
except ImportError:
    log.warning(
        "⚠️ pygetwindow não instalado — handler 'janela_ativa' indisponível. "
        "Instale com: pip install pygetwindow"
    )

try:
    import pyperclip
    _PYPERCLIP_DISPONIVEL = True
except ImportError:
    log.warning(
        "⚠️ pyperclip não instalado — handler 'copiar_clipboard' indisponível. "
        "Instale com: pip install pyperclip"
    )


# ═════════════════════════════════════════════════════════════════
# HANDLER: janela_ativa
# ═════════════════════════════════════════════════════════════════

def handle_janela_ativa(cmd: Comando) -> Resultado:
    """
    Retorna informações da janela atualmente em foco no Windows.

    Uso típico (brain/file_dialog_uploader):
        resultado = enviar_comando("janela_ativa")
        titulo = resultado["dados"]["titulo"]
        if "Abrir" in titulo or "Open" in titulo:
            # diálogo de arquivo aberto

    Returns:
        Resultado com dados = {
            "titulo":  str,    ← título da janela ativa
            "ativa":   bool,
            "largura": int,    ← largura da janela em pixels
            "altura":  int,    ← altura
            "x":       int,    ← posição left
            "y":       int,    ← posição top
        }
    """
    if not _PYGETWINDOW_DISPONIVEL:
        return Resultado(
            False,
            "❌ pygetwindow não instalado — execute 'pip install pygetwindow' e reinicie o executor",
            cmd.acao,
        )

    try:
        janela = gw.getActiveWindow()

        if janela is None:
            return Resultado(
                False,
                "🪟 Nenhuma janela ativa detectada",
                cmd.acao,
                dados={"titulo": "", "ativa": False},
            )

        titulo = janela.title or ""

        return Resultado(
            True,
            f"🪟 Janela ativa: '{titulo}'",
            cmd.acao,
            dados={
                "titulo":  titulo,
                "ativa":   True,
                "largura": janela.width,
                "altura":  janela.height,
                "x":       janela.left,
                "y":       janela.top,
            },
        )

    except Exception as e:
        return Resultado(
            False,
            f"❌ Erro ao obter janela ativa: {e}",
            cmd.acao,
        )


# ═════════════════════════════════════════════════════════════════
# HANDLER: copiar_clipboard
# ═════════════════════════════════════════════════════════════════

def handle_copiar_clipboard(cmd: Comando) -> Resultado:
    """
    Copia texto para o clipboard do Windows.

    Depois disso, o caller pode usar 'atalho' com ['ctrl', 'v']
    para colar em qualquer campo focado.

    Mais confiável que 'digitar' caractere por caractere:
      - acentos e UTF-8 sem problemas
      - velocidade irrelevante
      - paths com espaços e caracteres especiais funcionam

    Comando esperado:
        {"acao": "copiar_clipboard", "texto": "C:\\caminho\\arquivo.mp4"}

    Returns:
        Resultado com dados = {"tamanho_caracteres": int}
    """
    if not _PYPERCLIP_DISPONIVEL:
        return Resultado(
            False,
            "❌ pyperclip não instalado — execute 'pip install pyperclip' e reinicie o executor",
            cmd.acao,
        )

    if not cmd.texto:
        return Resultado(
            False,
            "❌ 'copiar_clipboard' precisa do campo 'texto'",
            cmd.acao,
        )

    try:
        pyperclip.copy(cmd.texto)

        # Validação dupla: confirma que copiou de verdade
        # (defesa contra clipboard travado por outro app)
        try:
            conteudo = pyperclip.paste()
            if conteudo != cmd.texto:
                log.warning(
                    f"⚠️ Clipboard copiou mas verificação não bate "
                    f"(esperado {len(cmd.texto)} chars, obtido {len(conteudo)})"
                )
        except Exception:
            pass  # paste pode falhar em alguns ambientes mas copy pode ter funcionado

        return Resultado(
            True,
            f"📋 Copiado {len(cmd.texto)} caractere(s) pro clipboard",
            cmd.acao,
            dados={"tamanho_caracteres": len(cmd.texto)},
        )

    except Exception as e:
        return Resultado(
            False,
            f"❌ Erro ao copiar pro clipboard: {e}",
            cmd.acao,
        )


# ═════════════════════════════════════════════════════════════════
# REGISTRO DOS HANDLERS EXTRAS
# Mesmo formato do REGISTRO de handlers.py — o engine mescla os dois.
# ═════════════════════════════════════════════════════════════════

HANDLERS_EXTRAS: dict[TipoAcao, Callable[[Comando], Resultado]] = {
    TipoAcao.JANELA_ATIVA:     handle_janela_ativa,
    TipoAcao.COPIAR_CLIPBOARD: handle_copiar_clipboard,
}