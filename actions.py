# executor/actions.py
# Define todas as ações possíveis do executor.
# Adicionar nova ação = adicionar aqui + handler em handlers.py (ou handlers_extras.py). Só.

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class TipoAcao(str, Enum):
    """Catálogo de todas as ações suportadas."""
    # Mouse
    CLICAR     = "clicar"
    MOVER      = "mover"
    SCROLL     = "scroll"
    DUPLO_CLIQUE = "duplo_clicar"

    # Teclado
    DIGITAR    = "digitar"
    HOTKEY     = "atalho"
    TECLA      = "tecla"

    # Sistema
    ABRIR_SITE     = "abrir_site"
    ABRIR_PROGRAMA = "abrir_programa"
    AGUARDAR       = "aguardar"

    # Sequência
    SEQUENCIA  = "sequencia"

    # Visão (automation/vision.py)
    SCREENSHOT       = "screenshot"        # já existia, agora usa vision.py
    OBSERVAR_TELA    = "observar_tela"     # screenshot com contexto nomeado
    CLICAR_IMAGEM    = "clicar_imagem"     # localiza imagem e clica
    LOCALIZAR_IMAGEM = "localizar_imagem"  # só retorna coordenadas
    AGUARDAR_IMAGEM  = "aguardar_imagem"   # espera imagem aparecer

    # Janela e clipboard (handlers_extras.py)
    # Usados pelo brain/file_dialog_uploader.py pra validar diálogos
    # sem queimar cota Gemini e colar caminhos UTF-8 confiavelmente.
    JANELA_ATIVA     = "janela_ativa"      # info da janela em foco no Windows
    COPIAR_CLIPBOARD = "copiar_clipboard"  # copia texto pro clipboard


@dataclass
class Comando:
    """
    Estrutura de um comando recebido pelo executor.
    
    Exemplos de JSON válidos:
    
    {"acao": "clicar", "x": 100, "y": 200}
    {"acao": "digitar", "texto": "olá mundo"}
    {"acao": "atalho", "teclas": ["ctrl", "c"]}
    {"acao": "abrir_site", "alvo": "https://tiktok.com"}
    {"acao": "aguardar", "segundos": 3}
    {"acao": "clicar_imagem", "imagem": "C:\\AgenteIA\\refs\\btn_postar.png"}
    {"acao": "observar_tela", "contexto": "apos_abrir_tiktok"}
    {"acao": "aguardar_imagem", "imagem": "C:\\AgenteIA\\refs\\carregando.png", "timeout": 10}
    {"acao": "janela_ativa"}
    {"acao": "copiar_clipboard", "texto": "C:\\AgenteIA\\videos\\meu_video.mp4"}
    """
    acao: TipoAcao
    # Mouse
    x: Optional[int] = None
    y: Optional[int] = None
    duracao: float = 0.5
    # Teclado
    texto: Optional[str] = None
    teclas: Optional[list] = None
    tecla: Optional[str] = None
    # Sistema
    alvo: Optional[str] = None
    segundos: float = 1.0
    # Sequência
    passos: list = field(default_factory=list)
    # Visão
    imagem: Optional[str] = None        # caminho da imagem de referência
    confidence: float = 0.8             # precisão do matching
    contexto: str = ""                  # nome descritivo para o screenshot
    timeout: float = 15.0              # timeout para aguardar_imagem
    duplo: bool = False                 # duplo clique ao clicar_imagem
    # Extras livres para ações futuras
    extras: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, dados: dict) -> "Comando":
        """Converte um dicionário (JSON) em Comando."""
        acao_str = dados.get("acao", "")
        try:
            acao = TipoAcao(acao_str)
        except ValueError:
            raise ValueError(f"Ação desconhecida: '{acao_str}'. "
                             f"Válidas: {[a.value for a in TipoAcao]}")
        return cls(
            acao=acao,
            x=dados.get("x"),
            y=dados.get("y"),
            duracao=dados.get("duracao", 0.5),
            texto=dados.get("texto"),
            teclas=dados.get("teclas"),
            tecla=dados.get("tecla"),
            alvo=dados.get("alvo"),
            segundos=dados.get("segundos", 1.0),
            passos=dados.get("passos", []),
            imagem=dados.get("imagem"),
            confidence=dados.get("confidence", 0.8),
            contexto=dados.get("contexto", ""),
            timeout=dados.get("timeout", 15.0),
            duplo=dados.get("duplo", False),
            extras={k: v for k, v in dados.items()
                    if k not in {"acao","x","y","duracao","texto","teclas","tecla",
                                 "alvo","segundos","passos","imagem","confidence",
                                 "contexto","timeout","duplo"}},
        )


@dataclass
class Resultado:
    """Resultado de uma ação executada."""
    sucesso: bool
    mensagem: str
    acao: str = ""
    dados: Any = None

    def to_dict(self) -> dict:
        return {
            "sucesso": self.sucesso,
            "mensagem": self.mensagem,
            "acao": self.acao,
            "dados": self.dados,
        }