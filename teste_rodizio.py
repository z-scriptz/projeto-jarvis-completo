#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_rodizio.py -- a rodada se espalha pelas contas ou cai numa só?
#
# O DEFEITO QUE ISTO TRAVA (05/09/2026)
# ─────────────────────────────────────
# `produzir_tiktok.py 5` produziu 5 de 5 pro @topshoppet_ e ZERO pras outras
# cinco contas. Não foi azar: a fila é `sorted(INBOX.iterdir())` e as pastas
# `achadinhos_*` sortam primeiro. Com 2154 pacotes, ordem alfabética é sorteio
# viciado — e a meta é 1.000 seguidores em TODAS as contas.
#
# Roda em qualquer lugar: não importa moviepy nem toca no inbox.
#   python3 teste_rodizio.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ⚠️ `produzir_tiktok` importa moviepy e afins no topo, o que não existe aqui.
# Carrego só a função pura, do fonte, sem executar o módulo inteiro.
import ast  # noqa: E402

_src = (Path(__file__).resolve().parent / "produzir_tiktok.py").read_text("utf-8")
_arv = ast.parse(_src)
_fn = next(n for n in _arv.body
           if isinstance(n, ast.FunctionDef) and n.name == "rodizio")
_ns: dict = {}
exec(compile(ast.Module([_fn], []), "produzir_tiktok.py", "exec"), _ns)
rodizio = _ns["rodizio"]

ok = falhou = 0


def checa(desc, obtido, esperado):
    global ok, falhou
    if obtido == esperado:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}\n      esperava {esperado!r}\n      veio     {obtido!r}")


print("\n── o caso real: a fila que produziu 5 pet seguidos ──")
# ordem alfabética da rodada de 04/09: achadinhos_do_mundo_pet_*, achadinhos_*
fila = [("pet", "escada"), ("pet", "escova"), ("pet", "bebedouro"),
        ("pet", "naninha"), ("pet", "limpador"),
        ("tech", "fone"), ("moda", "tenis"), ("casa", "organizador"),
        ("beleza", "serum"), ("geral", "caneca")]
checa("5 vagas se espalham em vez de irem todas pro pet",
      rodizio(fila, 5), ["escada", "fone", "tenis", "organizador", "serum"])

print("\n── ordem DENTRO do nicho é preservada ──")
# quem estava na frente do seu nicho continua na frente — rodízio não é sorteio
checa("segunda volta pega o 2º de cada nicho, não um aleatório",
      rodizio([("pet", "p1"), ("pet", "p2"), ("tech", "t1"), ("tech", "t2")], 4),
      ["p1", "t1", "p2", "t2"])
checa("a ordem dos nichos é a de aparição na fila",
      rodizio([("tech", "t1"), ("pet", "p1"), ("tech", "t2")], 3),
      ["t1", "p1", "t2"])

print("\n── quando não dá pra espalhar ──")
checa("um nicho só: entrega os que tem, na ordem",
      rodizio([("pet", "a"), ("pet", "b"), ("pet", "c")], 3), ["a", "b", "c"])
# ⚠️ ESTE É O QUE IMPORTA: se a fila SÓ tem pet, produzir 5 pet está certo.
# O rodízio espalha o que dá; não inventa conteúdo que não existe.
checa("fila com 2 e pedido de 5: devolve 2, não trava",
      rodizio([("pet", "a"), ("tech", "b")], 5), ["a", "b"])
checa("fila vazia devolve vazio",
      rodizio([], 5), [])
checa("pedido de zero devolve vazio",
      rodizio([("pet", "a")], 0), [])

print("\n── proporção: nicho com mais estoque não monopoliza a rodada ──")
muito_pet = [("pet", f"p{i}") for i in range(10)] + [("tech", "t1")]
checa("10 pet e 1 tech, 4 vagas → o tech entra na 2ª vaga",
      rodizio(muito_pet, 4), ["p0", "t1", "p1", "p2"])
# depois que o tech acaba, o resto é pet mesmo — e está certo: é o que existe.
checa("esgotado o tech, o resto volta a ser pet",
      rodizio(muito_pet, 6), ["p0", "t1", "p1", "p2", "p3", "p4"])

print("\n── as 6 contas, uma rodada de 6 ──")
seis = [("geral", "g"), ("beleza", "b"), ("tech", "t"),
        ("casa", "c"), ("moda", "m"), ("pet", "p")]
checa("uma vaga pra cada conta",
      rodizio(seis, 6), ["g", "b", "t", "c", "m", "p"])
checa("pedindo 12 com 6 disponíveis, entrega 6",
      len(rodizio(seis, 12)), 6)

print(f"\n{'='*52}\n   {ok} passou · {falhou} falhou\n{'='*52}")
raise SystemExit(1 if falhou else 0)
