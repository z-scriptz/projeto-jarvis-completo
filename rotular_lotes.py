#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# rotular_lotes.py — preenche o `lotes.json` com a leitura das folhas de contato.
#
# ⚠️ ARQUIVO DE UMA VEZ SÓ, e é de propósito que ele seja um SCRIPT e não um
# bloco pra colar. São 27 lotes; ditar isso no chat pro Dre digitar seria 27
# chances de errar um nome de formato — e formato escrito errado não dá erro,
# só cria uma pasta que o brain nunca vai procurar (foi o que o `_ALIAS` teve
# que resolver depois). Versionado, ele roda igual amanhã e fica registrado
# COMO a biblioteca foi classificada, que é o tipo de coisa que ninguém lembra
# em duas semanas.
#
# USO (na VPS):
#   .venv/bin/python rotular_lotes.py
#   .venv/bin/python fundo_ia.py --aplicar-lotes pronto_carrossel/lotes/lotes.json
"""Preenche o lotes.json com a leitura que o Claude fez das folhas (24/08).

⚠️ ISTO NÃO É PALPITE — é o que apareceu nas folhas de contato, e três pontos
foram conferidos um a um:
  lote-11  todas em tela dividida, antes|depois  → 4º formato da lista
  lote-08  cabo desencapado, celular na pia      → 1º (erros)
  lote-18  pia suja, armário bagunçado           → 1º (erros), agora em casa
Com o 1º, o 4º e o 10º batendo, a ordem dos dez formatos está confirmada.
"""
import json, sys
from pathlib import Path

FORMATOS = ["erros", "curiosidade", "comparacao", "antes_depois", "checklist",
            "lista", "produto", "problema_solucao", "nao_compre", "cta"]

# A PRIMEIRA LEVA: um lote por nicho, sem formato (vão pra raiz do nicho).
# São fundos de ambiente genérico, não foram gerados por formato.
PRIMEIRA = {1: "casa", 2: "pet", 3: "beleza", 4: "tech", 5: "moda",
            6: "casa", 7: "geral"}

alvo = Path(sys.argv[1] if len(sys.argv) > 1
            else "pronto_carrossel/lotes/lotes.json")
mapa = json.loads(alvo.read_text(encoding="utf-8"))

for chave in mapa:
    n = int(chave.split("-")[1])
    if n in PRIMEIRA:
        nicho, formato = PRIMEIRA[n], ""
    elif 8 <= n <= 17:
        nicho, formato = "tech", FORMATOS[n - 8]
    elif 18 <= n <= 27:
        nicho, formato = "casa", FORMATOS[n - 18]
    else:
        continue                      # lote que eu não vi: fica em branco
    mapa[chave]["nicho"] = nicho
    mapa[chave]["formato"] = formato

alvo.write_text(json.dumps(mapa, ensure_ascii=False, indent=2), encoding="utf-8")
for chave, info in mapa.items():
    n = len(info.get("arquivos") or [])
    print(f"  {chave}  {info['nicho'] or '(vazio)':8} "
          f"{info['formato'] or '(raiz)':18} {n:>3} imagens")
