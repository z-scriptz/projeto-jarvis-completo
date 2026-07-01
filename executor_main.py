# executor_main.py
# Ponto de entrada do executor — roda no WINDOWS
# Uso: python executor_main.py

import sys
import os

# Garante que a raiz do projeto está no path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from executor.engine import rodar_loop
from shared.logger import get_logger

log = get_logger("executor_main")

if __name__ == "__main__":
    print("=" * 50)
    print("  🤖 AgenteIA — Executor Windows")
    print("  Pressione CTRL+C para parar")
    print("  Mova o mouse pro canto da tela = parada de emergência")
    print("=" * 50)

    try:
        rodar_loop()
    except KeyboardInterrupt:
        log.info("⛔ Executor encerrado pelo usuário.")