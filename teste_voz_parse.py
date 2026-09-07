#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_voz_parse.py -- a resposta do modelo é lida certo, mesmo fora do formato?
#
# O DEFEITO QUE ISTO TRAVA (06/09/2026)
# ─────────────────────────────────────
# Um vídeo SEM VOZ NENHUMA voltou assim:
#
#     "NÃO HÁ FALA | Não há vozes, apenas ruído"
#
# O veredito estava CERTO — o formato é que não era o meu. O parser exigia
# começar com VOZ ou MUSICA, caiu em 'erro', e 'erro' TROCA o áudio. Ou seja: eu
# arrancaria a trilha de um vídeo que não tinha voz alguma, que é exatamente o
# defeito que este detector veio evitar.
#
# ⚠️ O RISCO DO CONSERTO É O OPOSTO: se eu for tolerante demais e ler qualquer
# coisa como 'musica', deixo voz em inglês passar. Por isso metade deste teste
# são respostas que NÃO podem virar 'musica'.
#
#   python3 teste_voz_parse.py
import ast
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

# ⚠️ `produzir_tiktok` importa moviepy no topo. Carrego só o miolo do parser,
# reproduzindo a mesma sequência de decisões da `tem_voz`.
_src = (BASE / "produzir_tiktok.py").read_text("utf-8")
_ns = {}
for _no in ast.parse(_src).body:
    if isinstance(_no, ast.FunctionDef) and _no.name == "_sem_acento_maiusc":
        exec(compile(ast.Module([_no], []), "x", "exec"), _ns)
_sem_acento_maiusc = _ns["_sem_acento_maiusc"]

_NEGACOES = ("NAO HA FALA", "NAO HA VOZ", "NAO HA VOZES", "SEM FALA",
             "SEM VOZ", "NENHUMA VOZ", "NINGUEM FALA", "NAO HA NINGUEM")


def ler(bruto: str) -> str:
    """Mesma sequência da `tem_voz`, isolada pra dar pra testar sem API."""
    cabeca, _, _motivo = bruto.partition("|")
    t = _sem_acento_maiusc(cabeca)
    if t.startswith("VOZ"):
        return "voz"
    if t.startswith("MUSICA"):
        return "musica"
    for neg in _NEGACOES:
        if neg in t or neg in _sem_acento_maiusc(bruto):
            return "musica"
    return "erro"


ok = falhou = 0


def checa(desc, bruto, esperado):
    global ok, falhou
    got = ler(bruto)
    if got == esperado:
        ok += 1
        print(f"   ✅ {esperado:6} ← {bruto[:52]}")
    else:
        falhou += 1
        print(f"   ❌ {bruto[:52]}\n      esperava {esperado!r}, veio {got!r}")


print("\n── o formato que eu pedi ──")
checa("voz", "VOZ | mulher explicando o produto", "voz")
checa("musica", "MUSICA | música eletrônica com batida", "musica")
checa("acento", "MÚSICA | canto em hindi", "musica")

print("\n── O CASO REAL: modelo certo, formato meu ──")
checa("negação", "NÃO HÁ FALA | Não há vozes, apenas ruído", "musica")
checa("variantes", "Não há voz | só barulho de produto", "musica")
checa("sem fala", "SEM FALA | ruído ambiente", "musica")
checa("ninguém fala", "Ninguém fala neste áudio", "musica")

print("\n── ⚠️ O RISCO INVERSO: isto NÃO pode virar 'musica' ──")
# se eu ler qualquer coisa como música, deixo voz em inglês ir pro ar
checa("fala presente", "VOZ | há vozes falando ao fundo", "voz")
checa("afirma voz", "Há uma mulher narrando o produto", "erro")
checa("resposta vazia", "", "erro")
checa("modelo enrolou", "Desculpe, não consigo analisar áudio.", "erro")
checa("só o motivo", "| mulher narra sobre o produto", "erro")

print("\n── negação DENTRO de uma resposta de voz ──")
# ⚠️ este é o caso perigoso do meu conserto: a frase contém 'nao ha voz' mas o
# veredito é VOZ. O prefixo tem que ganhar da varredura de negação.
checa("prefixo VOZ vence a negação",
      "VOZ | fala baixa, quase não há voz audível", "voz")

print(f"\n{'='*58}\n   {ok} passou · {falhou} falhou\n{'='*58}")
raise SystemExit(1 if falhou else 0)
