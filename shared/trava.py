# shared/trava.py
# TRAVA DE INSTÂNCIA ÚNICA — impede que duas cópias do mesmo script rodem
# juntas e façam o trabalho duas vezes.
#
# POR QUE ISSO EXISTE (04/08/2026)
# ────────────────────────────────
# O grupo do Telegram recebeu cada achadinho QUATRO vezes. A causa não foi o
# código: `crontab -l` tinha a MESMA linha do postar_grupo repetida 4x (linhas
# 3, 81, 114 e 140), todas em `15 */2 * * *`. Os quatro processos subiram no
# mesmo minuto, leram o mesmo `grupo_postados.json` — que ainda não tinha nada
# daquela rodada — e postaram os mesmos produtos.
#
# Dá pra limpar o crontab, e a gente limpou. Mas o crontab é editado à mão, por
# várias pessoas e scripts, e vai duplicar de novo. A defesa que dura é o
# próprio script recusar-se a rodar duas vezes.
#
# POR QUE flock E NÃO ARQUIVO DE PID
# O flock é solto pelo KERNEL quando o processo morre — inclusive se ele for
# morto com -9 ou a VPS reiniciar no meio. Arquivo de PID sobrevive ao crash e
# trava tudo até alguém apagar na mão, o que é pior que o problema original:
# em vez de postar 4x, para de postar e ninguém percebe.

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def rodar_unico(nome: str, funcao, *args, **kwargs) -> int:
    """Roda `funcao` só se nenhuma outra cópia estiver rodando.

    Feito pra caber numa linha no fim do script:

        if __name__ == "__main__":
            sys.exit(rodar_unico("auto_resposta", main))

    Devolve 0 quando desiste. A segunda instância não falhou — ela encontrou
    trabalho já em andamento, que é a resposta certa. Código de erro aqui faria
    o cron mandar e-mail de falha a cada 5 minutos.
    """
    with travar(nome) as livre:
        if not livre:
            print(f"[{nome}] outra instância já está rodando — saio sem fazer "
                  "nada ✔", flush=True)
            return 0
        return funcao(*args, **kwargs)


@contextmanager
def travar(nome: str, base: Path = None):
    """Entrega True se ESTE processo pegou a trava, False se outro já tem.

    Uso:
        with travar("postar_grupo") as livre:
            if not livre:
                return 0          # o outro está trabalhando; saio limpo
            ...

    Sair limpo importa: a segunda instância não é erro, é o cron duplicado
    fazendo o que faz. Se ela gritasse, o log encheria de alarme falso e o
    alarme de verdade se perderia no meio.
    """
    pasta = base or BASE_DIR
    try:
        pasta.mkdir(parents=True, exist_ok=True)
    except Exception:
        # sem onde gravar a trava, é melhor deixar rodar do que travar tudo
        yield True
        return

    arquivo = None
    try:
        arquivo = open(pasta / f".trava_{nome}", "w")
    except Exception:
        yield True
        return

    try:
        try:
            fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False              # outro processo está com ela
            return
        try:
            arquivo.write(str(os.getpid()))
            arquivo.flush()
        except Exception:
            pass                     # o PID é só pra depurar; não é a trava
        yield True
    finally:
        try:
            arquivo.close()          # fecha = solta o flock
        except Exception:
            pass
