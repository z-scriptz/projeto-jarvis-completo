#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_nicho_fonte.py -- a etiqueta da fonte vence a lista de palavras?
#
# O DEFEITO QUE ISTO TRAVA (06/09/2026)
# ─────────────────────────────────────
# O `_nicho_da_pasta` (que monta o rodízio) honra o `nicho_fonte` do plano.json;
# o `_produzir` (que posta) ignorava. Duas respostas pro mesmo pacote. Medido no
# lote real de 12:
#
#   balde 'casa' → postou em 'pet'    'Caneca Gato Rosa Carinhas'
#   balde 'tech' → postou em 'moda'   'relógio de fibra de carbono'
#
# Consequências, e a segunda é pior:
#   1. o rodízio reserva vaga numa conta e o vídeo sai noutra (2 de 12 = 17%)
#   2. marcar uma fonte como #casa não valia NADA na hora de postar
#
#   python3 teste_nicho_fonte.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import roteador_contas as R          # noqa: E402

ok = falhou = 0


def checa(desc, obtido, esperado):
    global ok, falhou
    if obtido == esperado:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}\n      esperava {esperado!r}, veio {obtido!r}")


def nicho(nome, forcado=""):
    c = R.conta_do_produto(nome, "", forcado)
    return c.get("nicho_detectado") or ""


def quem(nome, forcado=""):
    return R.conta_do_produto(nome, "", forcado).get("decidido_por") or ""


print("\n── os dois casos reais do lote ──")
# a lista diz 'pet' por causa de 'Gato'; a fonte diz casa, e a fonte manda
checa("caneca de gato: fonte casa vence 'gato'",
      nicho("Caneca Gato Rosa Carinhas 500ml Porcelana Fofa", "casa"), "casa")
checa("relógio: fonte tech vence 'relogio'",
      nicho("relógio de fibra de carbono forjado", "tech"), "tech")

print("\n── sem etiqueta, nada muda ──")
checa("sem fonte, a lista decide (pet)",
      nicho("Caneca Gato Rosa Carinhas 500ml Porcelana Fofa"), "pet")
checa("sem fonte, a lista decide (moda)",
      nicho("relógio de fibra de carbono forjado"), "moda")
checa("string vazia não força nada",
      nicho("Ração para gato castrado", ""), "pet")

print("\n── etiqueta inválida é ignorada, não quebra ──")
# ⚠️ a fonte é arquivo de texto editado à mão: erro de digitação vai acontecer.
# Etiqueta que não é nicho válido tem que CAIR na lista, nunca virar conta.
checa("nicho inexistente cai na lista",
      nicho("Ração para gato castrado", "cozinha"), "pet")
checa("lixo não vira conta",
      nicho("Ração para gato castrado", "#$%"), "pet")
checa("None não explode",
      nicho("Ração para gato castrado", None), "pet")

print("\n── o log tem que dizer QUEM decidiu ──")
# sem isso, um roteamento errado vira caça ao tesouro no futuro
checa("decidido pela fonte", quem("Caneca Gato Rosa", "casa"), "fonte")
checa("decidido pela palavra-chave", quem("Ração para gato castrado"),
      "palavra-chave")

print("\n── maiúscula e espaço na etiqueta ──")
# o arquivo de fontes é escrito por humano: '#Casa ' acontece
checa("'CASA' funciona", nicho("Caneca Gato Rosa", "CASA"), "casa")
checa("' casa ' funciona", nicho("Caneca Gato Rosa", " casa "), "casa")

print(f"\n{'='*56}\n   {ok} passou · {falhou} falhou\n{'='*56}")
raise SystemExit(1 if falhou else 0)
