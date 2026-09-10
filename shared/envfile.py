#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# shared/envfile.py -- ler o .env, num lugar só
#
# POR QUE ISTO EXISTE (10/09/2026)
# ────────────────────────────────
# O `comentarios.py --nichos` disse na VPS:
#
#     ⚠️ as 10 iscas de DM estão FORA do sorteio:
#          AUTO_RESPONDER=0   ← desligado
#          AUTO_RESP_DM=0     ← desligado
#
# E estava ERRADO — o `.env` do Dre tem as duas ligadas. O dry-run do
# `auto_resposta` mostrava `+DM:` na mesma máquina, no mesmo minuto.
#
# ⚠️ A CAUSA: `auto_resposta.py` chama `_carregar_env()` no import; o
# `comentarios.py` NUNCA leu o `.env`. Ele só olhava `os.environ`, que numa
# execução direta está vazio desses valores.
#
# ⚠️⚠️ E O ESTRAGO É MAIOR QUE O DIAGNÓSTICO ERRADO. O `comentarios.py`
# ANUNCIA no próprio docstring que aceita override por `.env`
# (`COMENT_IG_CARROSSEL=a|||b|||c`) — e **nenhum deles nunca funcionou**, a não
# ser por acaso, quando algum outro módulo tivesse carregado o `.env` antes no
# mesmo processo. Eu cheguei a mandar o Dre usar
# `COMENT_IG_REEL_PET='frase 1|||frase 2'` pra soltar frases sem deploy: aquele
# comando não teria feito nada, e o sintoma seria nenhum.
#
# É a mesma família do defeito que mais se repete aqui: a coisa está escrita,
# está documentada, está versionada — e não está ligada em lugar nenhum.
#
# 📌 POR QUE UM MÓDULO E NÃO UMA QUARTA CÓPIA: `auto_resposta`, `tiktok_coletor`
# e outros têm cada um o seu `_carregar_env()`, idêntico. Copiar de novo é como
# a rotação estava antes de virar `shared/rotacao.py` — conserta-se um e os
# outros seguem quebrados.
import os
from pathlib import Path


def carregar_env(base: Path = None, sobrescrever: bool = False) -> int:
    """Põe o `.env` no os.environ. Devolve quantas chaves entraram.

    ⚠️ NÃO SOBRESCREVE por padrão: variável exportada na mão (ou pelo systemd)
    tem que ganhar do arquivo, senão `AUTO_RESP_DM=0 python x.py` mentiria pra
    quem está testando.
    """
    base = base or Path(__file__).resolve().parent.parent
    n = 0
    for cand in (base / ".env", Path(".env")):
        if not cand.exists():
            continue
        try:
            linhas = cand.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for linha in linhas:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            k, _, v = linha.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and (sobrescrever or k not in os.environ):
                os.environ[k] = v
                n += 1
        break            # o primeiro que existir manda; não empilha os dois
    return n
