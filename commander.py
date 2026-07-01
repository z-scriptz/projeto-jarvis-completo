# brain/commander.py
# Lado WSL: envia comandos pro executor Windows e lê resultados.
# O agente (Gemini) chama essas funções pra controlar o Windows.

import json
import time
from pathlib import Path
from shared.config import COMANDO_JSON, RESULTADO_JSON
from shared.logger import get_logger

log = get_logger(__name__)

TIMEOUT_RESULTADO = 60  # segundos esperando resultado


def enviar_comando(acao: str, **kwargs) -> dict:
    """
    Envia um comando para o executor Windows e aguarda resultado.
    
    Uso:
        enviar_comando("clicar", x=100, y=200)
        enviar_comando("digitar", texto="Olá mundo")
        enviar_comando("abrir_site", alvo="https://tiktok.com")
        enviar_comando("atalho", teclas=["ctrl", "c"])
    
    Retorna o resultado como dicionário.
    """
    comando = {"acao": acao, **kwargs}

    # Apaga resultado anterior se existir
    try:
        RESULTADO_JSON.unlink(missing_ok=True)
    except Exception:
        pass

    # Escreve o comando
    try:
        COMANDO_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(COMANDO_JSON, "w", encoding="utf-8") as f:
            json.dump(comando, f, ensure_ascii=False, indent=2)
        log.info(f"📤 Comando enviado: {acao} {kwargs}")
    except Exception as e:
        log.error(f"Erro ao escrever comando: {e}")
        return {"sucesso": False, "mensagem": str(e)}

    # Aguarda resultado
    return _aguardar_resultado()


def enviar_sequencia(passos: list) -> dict:
    """
    Envia uma sequência de ações pro executor.
    
    Uso:
        enviar_sequencia([
            {"acao": "abrir_site", "alvo": "https://tiktok.com"},
            {"acao": "aguardar", "segundos": 3},
            {"acao": "digitar", "texto": "produto viral"},
        ])
    """
    return enviar_comando("sequencia", passos=passos)


def _aguardar_resultado(timeout: float = TIMEOUT_RESULTADO) -> dict:
    """Fica checando resultado.json até aparecer ou timeout."""
    inicio = time.time()

    while time.time() - inicio < timeout:
        if RESULTADO_JSON.exists():
            try:
                with open(RESULTADO_JSON, "r", encoding="utf-8") as f:
                    resultado = json.load(f)
                RESULTADO_JSON.unlink(missing_ok=True)
                log.info(f"📥 Resultado: {resultado.get('mensagem')}")
                return resultado
            except Exception as e:
                log.error(f"Erro ao ler resultado: {e}")
        time.sleep(0.5)

    log.warning("⏰ Timeout aguardando resultado do executor")
    return {"sucesso": False, "mensagem": "Timeout: executor não respondeu"}


# =========================
# TESTE RÁPIDO
# =========================
if __name__ == "__main__":
    print("🧪 Testando: abrindo TikTok no Windows...")
    resultado = enviar_comando("abrir_site", alvo="https://tiktok.com")
    print(f"Resultado: {resultado}")