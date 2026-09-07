#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_match_diag.py -- a peneira do diag_match separa o que eu acho que separa?
#
# POR QUE ISTO EXISTE (07/09/2026)
# ────────────────────────────────
# O `diag_match` vai dizer QUAL dos três estágios quebrou, e essa resposta
# decide um dia inteiro de trabalho. Se a peneira estiver errada eu conserto o
# estágio errado — foi exatamente o que aconteceu com o `--frame0` nesta semana
# (media algo *parecido* com o defeito e aprovou o pacote venenoso).
#
# ⚠️ OS DOIS ERROS CUSTAM COISAS DIFERENTES:
#   · falso POSITIVO (acusar um match bom) → o `--olho` inocenta. Custa API.
#   · falso NEGATIVO (um match ruim passar) → ele nunca chega no `--olho`, e
#     o vídeo vai ao ar com o produto errado. Este é o caro.
# Por isso os casos de "não pode passar" são a metade de baixo do arquivo.
#
#   python3 teste_match_diag.py
import ast
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
_src = (BASE / "diag_match.py").read_text("utf-8")
_ns = {}
# só as funções puras + o que elas usam; nada de ffmpeg, API ou inbox
exec(compile(ast.parse("import re, unicodedata"), "x", "exec"), _ns)
for _no in ast.parse(_src).body:
    if isinstance(_no, ast.Assign) and any(
            getattr(t, "id", "").startswith("_") for t in _no.targets):
        exec(compile(ast.Module([_no], []), "x", "exec"), _ns)
    if isinstance(_no, ast.FunctionDef) and _no.name in (
            "_sem_acento", "_palavras", "parentesco", "parece_gringo",
            "ler_veredito"):
        exec(compile(ast.Module([_no], []), "x", "exec"), _ns)
parentesco = _ns["parentesco"]
parece_gringo = _ns["parece_gringo"]
ler_veredito = _ns["ler_veredito"]

ok = falhou = 0


def checa(desc, cond, extra=""):
    global ok, falhou
    if cond:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}" + (f"\n      {extra}" if extra else ""))


def num(desc, valor, minimo=None, maximo=None):
    bom = (minimo is None or valor >= minimo) and (maximo is None or valor <= maximo)
    alvo = f"≥{minimo}" if maximo is None else (f"≤{maximo}" if minimo is None
                                                else f"{minimo}–{maximo}")
    checa(f"{desc:52} {valor:.2f} ({alvo})", bom)


print("\n── o termo casou com o produto: parentesco ALTO ──")
num("meia térmica → Meia Térmica Masculina Cano Alto",
    parentesco("meia térmica", "Meia Térmica Masculina Cano Alto"), minimo=0.99)
# ⚠️ O CASO DO PLURAL/GÊNERO: igualdade exata diria 0 e estaria errado
num("organizador gaveta → Organizadora de Gavetas Dupla",
    parentesco("organizador gaveta", "Organizadora de Gavetas Dupla"), minimo=0.99)
num("copo térmico → Civago Copo Térmico 380ml Inox",
    parentesco("copo térmico", "Civago Copo Térmico 380ml Inox Portátil"), minimo=0.99)
num("parcial conta como parcial",
    parentesco("luminária de flor", "Luminária Plafon Amadeirado Wood"),
    minimo=0.3, maximo=0.7)

print("\n── ⚠️ O CASO REAL DO DRE: a loja devolveu outra coisa ──")
num("meia térmica → Meia Calça INFANTIL PARA BALLET",
    parentesco("meia térmica", "Meia Calça Infantil para Ballet Elástica"),
    minimo=0.4, maximo=0.6)
num("aquecedor de pés → Meia Calça Infantil Ballet",
    parentesco("aquecedor de pes", "Meia Calça Infantil para Ballet Elástica"),
    maximo=0.1)
num("coleira cachorro → Spray de Defesa Pessoal",
    parentesco("coleira cachorro", "spray de defesa pessoal"), maximo=0.1)

print("\n── ⚠️ NÃO PODE PASSAR: palavra de catálogo não é parentesco ──")
# 'para', 'kit', 'infantil' aparecem em metade dos títulos da Shopee. Se elas
# contassem, qualquer produto casaria com qualquer termo e a peneira seria cega.
num("'kit para casa' → 'Kit para Casa de Bonecas'  (só palavra vazia)",
    parentesco("kit para casa", "Kit para Casa de Bonecas Infantil"), maximo=0.34)
num("'para com dos' não afirma nada",
    parentesco("para com dos", "Guia Dupla Retrátil para 2 Cães"), maximo=0.0)
num("termo vazio → 0 (não sei, não 'não casa')",
    parentesco("", "Qualquer Produto"), maximo=0.0)
num("produto vazio → 0", parentesco("meia térmica", ""), maximo=0.0)

print("\n── termo que é pedaço de legenda gringa ──")
checa("'stepped into the crowd taking' é gringo",
      parece_gringo("stepped into the crowd taking"))
checa("'You can find this bye' é gringo", parece_gringo("You can find this bye"))
checa("'The Most Viral Gadget Must' é gringo",
      parece_gringo("The Most Viral Gadget Must"))
# ⚠️ O RISCO INVERSO: acusar português de gringo faria a visão rodar à toa e
# ainda mandaria pro balde produto bom.
checa("'meia térmica' NÃO é gringo", not parece_gringo("meia térmica"))
checa("'balde de gelo' NÃO é gringo", not parece_gringo("balde de gelo"))
checa("'kit caneta refil multicolor' NÃO é gringo",
      not parece_gringo("kit caneta refil multicolor"))
checa("'mop de limpeza' NÃO é gringo (o falso positivo de 04/09)",
      not parece_gringo("mop de limpeza"))

print("\n── ⚠️ 'NAOCASA' CONTÉM 'CASA': a ordem da leitura ──")
checa("NAOCASA lido como naocasa",
      ler_veredito("NAOCASA | show de moda, sem produto") == "naocasa")
checa("CASA lido como casa",
      ler_veredito("CASA | copo térmico inox na mão") == "casa")
checa("NÃO CASA com acento e espaço",
      ler_veredito("NÃO CASA | bastidores de festa") == "naocasa")
checa("NAO-CASA com hífen", ler_veredito("NAO-CASA | desfile") == "naocasa")
checa("resposta fora do formato vira erro (não vira 'casa')",
      ler_veredito("Desculpe, não consigo ver o vídeo.") == "erro")
checa("resposta vazia vira erro", ler_veredito("") == "erro")

print(f"\n{'='*66}\n   {ok} passou · {falhou} falhou\n{'='*66}")
raise SystemExit(1 if falhou else 0)
