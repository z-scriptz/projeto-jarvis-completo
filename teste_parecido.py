#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_parecido.py -- a comparação de áudio reconhece a nossa trilha?
#
# POR QUE ISSO EXISTE (06/09/2026)
# ────────────────────────────────
# Preciso achar 41 vídeos cujo áudio foi trocado por uma das nossas 3 trilhas,
# e NÃO tenho log nem mtime confiável (eu mesmo destruí os dois). A única
# assinatura que sobrou é o próprio áudio.
#
# ⚠️ OS DOIS ERROS AQUI CUSTAM COISAS DIFERENTES:
#   · falso POSITIVO → restauro um vídeo que não precisava, colando por cima
#     dele o áudio da origem. Perda pequena e reversível.
#   · falso NEGATIVO → deixo um vídeo com a trilha repetida na fila, e ele vai
#     ao ar. É o que o Dre mandou evitar.
# Por isso o piso é 0.90 e não 0.99.
#
#   python3 teste_parecido.py
import ast
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
_src = (BASE / "restaurar_audio_fila.py").read_text("utf-8")
_ns = {}
for _no in ast.parse(_src).body:
    if isinstance(_no, ast.FunctionDef) and _no.name == "parecido":
        exec(compile(ast.Module([_no], []), "x", "exec"), _ns)
parecido = _ns["parecido"]

try:
    import numpy as np
except Exception:
    print("❌ numpy não disponível aqui — este teste precisa dele")
    raise SystemExit(1)

ok = falhou = 0


def checa(desc, valor, minimo=None, maximo=None):
    global ok, falhou
    bom = (minimo is None or valor >= minimo) and (maximo is None or valor <= maximo)
    alvo = f"≥{minimo}" if maximo is None else (f"≤{maximo}" if minimo is None
                                                else f"{minimo}–{maximo}")
    if bom:
        ok += 1
        print(f"   ✅ {desc:52} {valor:.3f} ({alvo})")
    else:
        falhou += 1
        print(f"   ❌ {desc:52} {valor:.3f} (esperava {alvo})")


rng = np.random.default_rng(42)
trilha = rng.standard_normal(48000).astype("float32")     # 6s a 8kHz
outra = rng.standard_normal(48000).astype("float32")

print("\n── a mesma trilha, em várias condições ──")
checa("idêntica", parecido(trilha, trilha), minimo=0.99)
# ⚠️ O CASO QUE IMPORTA: a trilha entra com volume 0.85 no ffmpeg
checa("mesma trilha a 85% do volume", parecido(trilha * 0.85, trilha), minimo=0.99)
checa("volume bem baixo (30%)", parecido(trilha * 0.30, trilha), minimo=0.99)
# perda de qualidade do AAC 128k: ruído pequeno somado
ruido = rng.standard_normal(48000).astype("float32") * 0.05
checa("com ruído de compressão AAC", parecido(trilha + ruido, trilha), minimo=0.90)

print("\n── áudio DIFERENTE não pode passar do piso ──")
checa("outra faixa qualquer", parecido(outra, trilha), maximo=0.30)
checa("silêncio", parecido(np.zeros(48000, dtype="float32"), trilha), maximo=0.30)
# vídeo com narração + música por baixo: parecido, mas não o bastante
mistura = (trilha * 0.4 + outra * 0.9).astype("float32")
checa("trilha por baixo de outra voz", parecido(mistura, trilha), maximo=0.60)

print("\n── bordas ──")
checa("None de um lado", parecido(None, trilha), maximo=0.0)
checa("None dos dois", parecido(None, None), maximo=0.0)
checa("curto demais (<1s) não afirma nada",
      parecido(trilha[:4000], trilha), maximo=0.0)
# tamanhos diferentes: compara o trecho comum
checa("vídeo mais curto que a trilha",
      parecido(trilha[:16000], trilha), minimo=0.99)

print(f"\n{'='*68}\n   {ok} passou · {falhou} falhou\n{'='*68}")
raise SystemExit(1 if falhou else 0)
