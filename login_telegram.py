#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# login_telegram.py — cria a sessão Telethon que o radar e o descobridor usam.
#
# ⚠️ POR QUE ISTO EXISTE (29/08). O `descobridor_grupos` falhava TRÊS VEZES POR
# DIA, todos os dias, com esta linha no journal:
#
#     Please enter your phone (or bot token):
#     [ERROR] descobridor_grupos: erro na descoberta de grupos: EOF when
#             reading a line
#
# O Telethon não achou sessão válida e caiu no login interativo — dentro de um
# daemon, onde stdin é EOF. Falha instantânea, uma linha de log, e a máquina
# seguia em frente. Custo medido: `grupos_descoberta_max: 5` × 3 horários =
# **até 15 canais novos por dia** que nunca entraram, desde sempre.
#
# 📌 O sintoma não era "descoberta com erro", era A FILA NÃO CRESCER. O hunter
# continuou girando a mesma lista fixa de canais, a reposição travou em 16
# produtos/dia, e a pergunta "por que não consigo postar 36 por dia no grupo?"
# nasceu daqui — a três camadas de distância, sem nada ligando as duas coisas.
#
# ⚠️ O HUNTER NÃO PRECISA DISTO. Ele lê as prévias públicas do t.me por HTTP
# (`requests`), sem login — por isso continuou funcionando o tempo todo e
# escondeu o problema. Quem precisa de sessão de USUÁRIO é o radar (lê mensagem
# de grupo) e o descobridor (busca canais). Não confunda os dois: apagar esta
# sessão não derruba o hunter, e ter esta sessão não conserta o hunter.
#
# ⚠️ LOGIN É INTERATIVO E TEM QUE SER. O Telegram manda um código no app; não
# existe caminho não-assistido. Rode ISTO NA MÃO, uma vez, e a sessão fica em
# `shared/telegram_radar.session` e sobrevive aos reinícios.
#
# USO (na VPS, dentro de ~/jarvis):
#   .venv/bin/python login_telegram.py --conferir   # só diz se já está logado
#   .venv/bin/python login_telegram.py              # faz o login (pede código)

import argparse
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SESSAO = BASE_DIR / "shared" / "telegram_radar.session"


def _log(m):
    print(f"   {m}", flush=True)


def _carregar_env():
    """⚠️ SEM ISTO O TOKEN NÃO EXISTE. Este script roda na mão, fora do
    systemd — e é o systemd que injeta o ambiente. Mesmo motivo do
    `_carregar_env` do whatsapp_playwright e do postar_grupo."""
    for cand in (BASE_DIR / ".env", Path(".env")):
        if not cand.exists():
            continue
        for linha in cand.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            k, v = linha.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _credenciais() -> tuple:
    """(api_id, api_hash). Erro claro dizendo QUAL falta, não "não deu certo"."""
    api_id = (os.environ.get("TELEGRAM_API_ID") or "").strip()
    api_hash = (os.environ.get("TELEGRAM_API_HASH") or "").strip()
    faltam = [n for n, v in (("TELEGRAM_API_ID", api_id),
                             ("TELEGRAM_API_HASH", api_hash)) if not v]
    if faltam:
        _log(f"❌ falta no .env: {', '.join(faltam)}")
        _log("   Pegue em https://my.telegram.org → API development tools")
        return None, None
    if not api_id.isdigit():
        # ⚠️ `int(API_ID)` estoura lá dentro do descobridor com um ValueError
        # cru, no meio de um try genérico que só loga 100 caracteres. Melhor
        # descobrir aqui, com o nome da variável na frente.
        _log(f"❌ TELEGRAM_API_ID tem que ser numérico (achei {api_id[:12]!r})")
        return None, None
    return int(api_id), api_hash


def conferir(api_id: int, api_hash: str) -> int:
    """Diz se a sessão atual serve — SEM abrir prompt nenhum.

    ⚠️ `connect()` + `is_user_authorized()`, nunca `start()`. O `start()` é
    justamente o que pergunta o telefone quando não há sessão, e num terminal
    ele ficaria esperando você digitar. Conferir não pode ter efeito."""
    from telethon import TelegramClient
    cli = TelegramClient(str(SESSAO), api_id, api_hash)
    try:
        cli.connect()
        if not cli.is_user_authorized():
            _log(f"❌ sessão em {SESSAO.name} existe? "
                 f"{'sim' if SESSAO.exists() else 'NÃO'} — mas não está "
                 f"autorizada")
            _log("   É por isso que o descobridor_grupos falha 3x por dia.")
            _log("   Rode sem --conferir pra logar.")
            return 1
        eu = cli.get_me()
        _log(f"✅ logado como @{eu.username or eu.first_name} (id {eu.id})")
        _log(f"   sessão: {SESSAO}")
        return 0
    finally:
        try:
            cli.disconnect()
        except Exception:
            pass


def entrar(api_id: int, api_hash: str) -> int:
    """O login de verdade. Pede telefone e o código que chega no app."""
    if not sys.stdin.isatty():
        # 📌 Esta é EXATAMENTE a falha que este arquivo existe pra consertar.
        # Sem esta checagem, rodar isto de um cron repetiria o bug original —
        # prompt sem ninguém pra responder, EOF, e uma linha de erro por dia.
        _log("❌ isto precisa de um terminal de verdade: o Telegram manda um "
             "código no app e alguém tem que digitar.")
        _log("   Não coloque este script no cron.")
        return 2
    from telethon import TelegramClient
    SESSAO.parent.mkdir(parents=True, exist_ok=True)
    cli = TelegramClient(str(SESSAO), api_id, api_hash)
    try:
        cli.start()               # aqui ele pergunta telefone + código
        eu = cli.get_me()
        _log(f"✅ logado como @{eu.username or eu.first_name} (id {eu.id})")
        _log(f"   sessão gravada em {SESSAO}")
        _log("   O descobridor_grupos volta a rodar nos horários do config "
             "(08:30, 13:30, 20:30) — não precisa reiniciar o daemon.")
        return 0
    except Exception as e:
        _log(f"❌ login falhou: {type(e).__name__}: {str(e)[:160]}")
        return 1
    finally:
        try:
            cli.disconnect()
        except Exception:
            pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Cria/confere a sessão Telethon do radar e do descobridor.")
    p.add_argument("--conferir", action="store_true",
                   help="só diz se a sessão atual está autorizada")
    a = p.parse_args(argv)

    _carregar_env()
    api_id, api_hash = _credenciais()
    if not api_id:
        return 2
    try:
        import telethon        # noqa: F401
    except ImportError:
        _log("❌ telethon não está instalado neste venv")
        return 2
    return conferir(api_id, api_hash) if a.conferir else entrar(api_id, api_hash)


if __name__ == "__main__":
    sys.exit(main())
