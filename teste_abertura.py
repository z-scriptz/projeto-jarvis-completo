#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_abertura.py -- a repetição de MOLDE é detectada, não só a de frase?
#
# O DEFEITO QUE ISTO TRAVA (06/09/2026)
# ─────────────────────────────────────
# O Dre: "os hooks estão horrorosos". Numa rodada real, 8 de 14 começaram com
# "Eu achava que" — cada frase diferente, o mesmo molde sempre.
#
# O `_bloco_nao_repita` já mostrava os hooks anteriores pedindo "não repita", e
# o modelo OBEDECEU: nenhuma frase se repete. O que se repete é a ABERTURA.
# Frase inteira era a unidade errada de medida.
#
# Roda em qualquer lugar: não chama API nem lê arquivo.
#   python3 teste_abertura.py
import ast
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

# ⚠️ hook_alana importa coisas que não existem no dev local. Carrego só as duas
# funções puras, do fonte.
_src = (BASE / "hook_alana.py").read_text("utf-8")
_ns = {}
for _no in ast.parse(_src).body:
    if isinstance(_no, ast.FunctionDef) and _no.name in ("_abertura", "aberturas_gastas"):
        exec(compile(ast.Module([_no], []), "hook_alana.py", "exec"), _ns)
_abertura = _ns["_abertura"]
aberturas_gastas = _ns["aberturas_gastas"]

ok = falhou = 0


def checa(desc, obtido, esperado):
    global ok, falhou
    if obtido == esperado:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}\n      esperava {esperado!r}\n      veio     {obtido!r}")


print("\n── a assinatura do molde ──")
checa("tira maiúscula e pontuação",
      _abertura("Eu achava que era impossível ter um esconderijo 🤫"),
      "eu achava que")
checa("acento é preservado (não normalizo, só comparo entre si)",
      _abertura("Minha função na piscina era só correr atrás"),
      "minha função na")
checa("emoji no começo não vira palavra",
      _abertura("😩 Minha casa vivia uma bagunça"), "minha casa vivia")
checa("só a 1ª linha conta (a 2ª é a tag)",
      _abertura("Eu achava que dava trabalho\nAchei na Shopee"), "eu achava que")
checa("hook vazio não explode", _abertura(""), "")


print("\n── O CASO REAL: 8 de 14 com o mesmo começo ──")
rodada = [
    "Eu achava que era impossível ter um esconderijo confortável no meio da rua",
    "Eu achava que peixe esquecia tudo em três segundos",
    "Eu achava que só cirurgia resolvia a gravidade no espelho",
    "Eu achava que pra ter paz em casa era preciso virar um ninja",
    "Eu achava que ter a horta perfeita exigia dedicação em tempo integral",
    "Eu achava que ter um pet no sofá significava levantar toda hora",
    "Minha casa não era um refúgio até eu entender que o cheiro muda tudo",
    "Minha função na piscina era só correr atrás e segurar filho",
    "Minha coluna reclamava cada vez que eu limpava o banheiro",
    "Passei anos achando que aquário não tinha surpresa nova todo dia",
]
gastas = dict(aberturas_gastas(rodada))
checa("pega 'eu achava que' com 6 usos", gastas.get("eu achava que"), 6)
checa("'minha' sozinho NÃO é molde (3 palavras diferentes)",
      "minha casa não" in gastas, False)
checa("abertura única não entra na lista",
      "passei anos achando" in gastas, False)

print("\n── o corte de 3 usos ──")
# ⚠️ 2 usos não é molde, é coincidência. Marcar cedo demais gastaria a única
# recusa que a gente tem (só a 1ª tentativa recusa) com falso alarme.
checa("2 usos ainda passa",
      dict(aberturas_gastas(["Eu achava que a", "Eu achava que b"])), {})
checa("3 usos já é molde",
      dict(aberturas_gastas(["Eu achava que a", "Eu achava que b",
                             "Eu achava que c"])), {"eu achava que": 3})

print("\n── variedade de verdade não é punida ──")
variado = [
    "Ninguém avisa que a pressa estraga o café",
    "Comprei achando que era bobagem e me calei",
    "Passei anos limpando errado sem saber",
    "Meu chefe perguntou onde comprei na mesma semana",
    "Descobri isso tarde demais pra minha coluna",
]
checa("5 hooks variados: nenhuma abertura gasta", aberturas_gastas(variado), [])

print("\n── ordem: a mais gasta aparece primeiro ──")
mix = (["Eu achava que a", "Eu achava que b", "Eu achava que c",
        "Eu achava que d"] + ["Minha casa vivia x", "Minha casa vivia y",
                              "Minha casa vivia z"])
checa("ordenado por uso, maior primeiro",
      [a for a, _ in aberturas_gastas(mix)],
      ["eu achava que", "minha casa vivia"])

print("\n── hook curto demais não vira molde ──")
# 'Odeio isso' tem 2 palavras: não dá pra chamar de abertura repetida
checa("hooks de 2 palavras são ignorados",
      aberturas_gastas(["Odeio isso", "Odeio isso", "Odeio isso"]), [])

print(f"\n{'='*56}\n   {ok} passou · {falhou} falhou\n{'='*56}")
raise SystemExit(1 if falhou else 0)
