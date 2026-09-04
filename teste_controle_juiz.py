#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_controle_juiz.py -- a leitura do controle negativo está certa?
#
# POR QUE ISSO EXISTE
# ───────────────────
# O --controle existe pra eu parar de pedir o olho do Dre pra coisa que dá pra
# medir. Mas a MEDIÇÃO só vale se a leitura dela estiver certa — senão eu troco
# um palpite meu por um número que eu interpretei errado, que é pior, porque
# número parece verdade.
#
# Roda em qualquer lugar: não precisa de API, ffmpeg nem internet.
#   python3 teste_controle_juiz.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conferir_match import ler_controle          # noqa: E402

ok = falhou = 0


def checa(desc, obtido, esperado):
    global ok, falhou
    if obtido == esperado:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}\n      esperava {esperado!r}, veio {obtido!r}")


print("\n── juiz que não julga (o caso que eu suspeito) ──")
# as duas amostras reais deram 60% e 67% de reprovação. Se o embaralhado der
# a mesma coisa, ele está chutando NAO.
checa("reprova real e embaralhado igual (65% x 65%)",
      ler_controle(0.65, 0.65), "cego")
checa("embaralhado só 10 pontos acima do real",
      ler_controle(0.75, 0.65), "cego")
checa("embaralhado 100%, real 90% — diferença pequena demais",
      ler_controle(1.00, 0.90), "cego")

print("\n── juiz frouxo (deixa passar par errado de fábrica) ──")
checa("aprova metade dos embaralhados",
      ler_controle(0.50, 0.10), "frouxo")
checa("aprova 3 de 10 embaralhados",
      ler_controle(0.70, 0.00), "frouxo")
# ⚠️ mas 'cego' VENCE 'frouxo', e eu tinha escrito o contrário aqui. Se ele
# reprova real e embaralhado na mesma taxa, o problema não é "aprova demais" —
# é que ele não está olhando. Dizer 'frouxo' aqui insinuaria que os ❌ prestam.
checa("mesma taxa nos dois → cego, não frouxo",
      ler_controle(0.40, 0.40), "cego")

print("\n── juiz que presta ──")
checa("reprova 100% do embaralhado e 60% do real",
      ler_controle(1.00, 0.60), "presta")
checa("reprova 90% do embaralhado e 20% do real",
      ler_controle(0.90, 0.20), "presta")
checa("no limite exato do piso, com folga na margem",
      ler_controle(0.75, 0.10), "presta")

print("\n── as bordas, onde eu costumo errar ──")
# piso é >=, não >: 0.75 cravado ainda passa
checa("rep_ctl exatamente no piso não é frouxo",
      ler_controle(0.75, 0.00), "presta")
checa("um fio abaixo do piso já é frouxo",
      ler_controle(0.7499, 0.00), "frouxo")
# margem é >=, então diferença de exatamente 0.15 ainda é 'cego'
checa("diferença de exatamente 15 pontos ainda é cego",
      ler_controle(1.00, 0.85), "cego")
checa("16 pontos de diferença já presta",
      ler_controle(1.00, 0.84), "presta")
checa("caso perfeito: 100% embaralhado, 0% real",
      ler_controle(1.00, 0.00), "presta")

print("\n── e o caso que ninguém espera ──")
# se o real reprovar MAIS que o embaralhado, tem algo muito errado — mas isso
# cai em 'cego', que é o veredito seguro (não bloqueia nada).
checa("real reprova mais que o embaralhado → cego (seguro)",
      ler_controle(0.80, 0.95), "cego")

print(f"\n{'='*52}\n   {ok} passou · {falhou} falhou\n{'='*52}")
raise SystemExit(1 if falhou else 0)
