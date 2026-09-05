#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_download.py -- o diagnóstico separa arquivo quebrado de ruído do moviepy?
#
# ⚠️ ESTE TESTE EXISTE CONTRA MIM. Eu entrei nessa investigação com a hipótese
# de que os avisos são inofensivos. Um classificador escrito por quem já tem
# resposta favorita tende a confirmá-la. Então os casos aqui incluem os que
# CONTRARIAM a minha hipótese, e eles têm que ser pegos como quebrados.
#
#   python3 teste_download.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diag_download import classificar          # noqa: E402

ok = falhou = 0


def checa(desc, obtido, esperado):
    global ok, falhou
    if obtido == esperado:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}\n      esperava {esperado!r}, veio {obtido!r}")


print("\n── os casos REAIS do log (últimos 2-6 frames, decoder calado) ──")
checa("412-414 de 415: moletom", classificar("", 415, 418), "arredondamento")
checa("515-517 de 519: aquário", classificar("", 519, 522), "arredondamento")
checa("705 de 707: umidificador", classificar("", 707, 709), "arredondamento")
checa("289-294 de 294: para-brisa", classificar("", 294, 300), "arredondamento")

print("\n── o pacote-veneno ──")
checa("não decodifica nem um frame", classificar("", 0, 289), "ilegivel")
checa("zero frames mesmo com decoder calado", classificar("", 0, 0), "ilegivel")

print("\n── CONTRA a minha hipótese: isto TEM que dar quebrado ──")
# ⚠️ se o decoder reclama, não interessa quantos frames faltam: é truncado.
checa("decoder reclamou, faltando só 1 frame",
      classificar("moov atom not found", 900, 901), "truncado")
checa("decoder reclamou e as contas batem",
      classificar("Invalid NAL unit size", 500, 500), "truncado")
# ⚠️ perda grande NUNCA é arredondamento, mesmo com o decoder calado
checa("faltando 9 frames já é truncado", classificar("", 491, 500), "truncado")
checa("faltando metade do vídeo", classificar("", 250, 500), "truncado")
checa("faltando 100 frames", classificar("", 400, 500), "truncado")

print("\n── as bordas do corte de 8 ──")
checa("faltando 8 ainda é arredondamento", classificar("", 492, 500), "arredondamento")
checa("faltando 9 não é mais", classificar("", 491, 500), "truncado")
checa("faltando 1", classificar("", 499, 500), "arredondamento")

print("\n── arquivo íntegro de verdade ──")
checa("contas batem exatamente", classificar("", 500, 500), "ok")
# o ffprobe às vezes conta MAIS frames que duração×fps; não é defeito
checa("mais frames reais que pedidos", classificar("", 505, 500), "ok")

print(f"\n{'='*56}\n   {ok} passou · {falhou} falhou\n{'='*56}")
raise SystemExit(1 if falhou else 0)
