# executor/engine.py
# Motor do executor. Lê comando.json, despacha para o handler certo,
# escreve resultado.json. Loop limpo e desacoplado.

import json
import time
import os
from pathlib import Path

from executor.actions import Comando, Resultado, TipoAcao
from executor.handlers import REGISTRO
from executor.handlers_extras import HANDLERS_EXTRAS
from shared.config import COMANDO_JSON, RESULTADO_JSON, EXECUTOR_POLL_INTERVAL
from shared.logger import get_logger

log = get_logger(__name__)


# Mescla os handlers extras (janela_ativa, copiar_clipboard) no registro principal.
# REGISTRO já tem os handlers de mouse/teclado/sistema/visão; HANDLERS_EXTRAS
# adiciona os extras sem precisar editar handlers.py.
REGISTRO.update(HANDLERS_EXTRAS)


def executar_comando(dados: dict) -> Resultado:
    """
    Recebe um dicionário (já carregado do JSON),
    valida, despacha pro handler e retorna o Resultado.
    Suporta sequência recursivamente.
    """
    try:
        cmd = Comando.from_dict(dados)
    except ValueError as e:
        return Resultado(False, str(e))

    # Sequência: executa cada passo em ordem
    if cmd.acao == TipoAcao.SEQUENCIA:
        return _executar_sequencia(cmd)

    handler = REGISTRO.get(cmd.acao)
    if not handler:
        return Resultado(False, f"❌ Sem handler para ação: {cmd.acao}")

    try:
        resultado = handler(cmd)
        log.info(resultado.mensagem)
        return resultado
    except Exception as e:
        log.error(f"Erro em '{cmd.acao}': {e}")
        return Resultado(False, f"❌ Erro em '{cmd.acao}': {e}", cmd.acao)


def _executar_sequencia(cmd: Comando) -> Resultado:
    """Executa uma lista de passos em ordem, coletando resultados."""
    resultados = []
    sucesso_total = True

    for i, passo in enumerate(cmd.passos):
        log.info(f"Sequência passo {i+1}/{len(cmd.passos)}: {passo.get('acao')}")
        r = executar_comando(passo)
        resultados.append(r.to_dict())
        if not r.sucesso:
            sucesso_total = False
            log.warning(f"Passo {i+1} falhou: {r.mensagem}")

    return Resultado(
        sucesso=sucesso_total,
        mensagem=f"Sequência: {len(cmd.passos)} passos executados.",
        acao="sequencia",
        dados=resultados,
    )


def _salvar_resultado(resultado: Resultado):
    """Escreve resultado.json para o WSL poder ler a resposta."""
    try:
        RESULTADO_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(RESULTADO_JSON, "w", encoding="utf-8") as f:
            json.dump(resultado.to_dict(), f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Não conseguiu salvar resultado: {e}")


def rodar_loop():
    """
    Loop principal do executor.
    Fica verificando se comando.json apareceu.
    Quando aparece: lê, executa, apaga, salva resultado.
    """
    log.info("🤖 Executor iniciado. Aguardando comandos...")
    log.info(f"📂 Monitorando: {COMANDO_JSON}")
    log.info(f"🛠️  Ações registradas: {len(REGISTRO)} ({sorted(a.value for a in REGISTRO.keys())})")

    while True:
        try:
            if COMANDO_JSON.exists():
                # Lê o comando
                with open(COMANDO_JSON, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                log.info(f"📩 Comando recebido: {dados.get('acao')}")

                # Remove ANTES de executar (evita loop duplo)
                os.remove(COMANDO_JSON)

                # Executa
                resultado = executar_comando(dados)

                # Salva resultado para o WSL ler
                _salvar_resultado(resultado)

        except json.JSONDecodeError as e:
            log.error(f"JSON inválido: {e}")
            try:
                os.remove(COMANDO_JSON)
            except Exception:
                pass
        except Exception as e:
            log.error(f"Erro no loop: {e}")

        time.sleep(EXECUTOR_POLL_INTERVAL)