#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_idade_fila.py -- ninguém mais pode escrever DENTRO da pasta do pacote
#
# POR QUE ISTO EXISTE (09/09/2026)
# ────────────────────────────────
# Duas vezes em 48 horas eu rejuvenesci a fila escrevendo arquivo temporário
# dentro da pasta do pacote:
#
#   06/09 · `consertar_audio_fila` → 41 pacotes
#   08/09 · `conferir_match._frames` → 185 de 310
#
# ⚠️ NA PRIMEIRA VEZ EU CONSERTEI A OCORRÊNCIA, NÃO A CLASSE. Documentei em dois
# arquivos, escrevi "TEMPORÁRIO FORA DA PASTA" nos dois, e não fui procurar o
# mesmo padrão nos outros — o `conferir_match` estava ali o tempo todo. Este
# teste existe pra que a TERCEIRA vez falhe aqui em vez de aparecer no perfil do
# Dre uma semana depois.
#
# O custo do defeito: o daemon ordena a fila pelo mtime da pasta, e com
# `ordem_da_fila: mais_novo` um vídeo de 24 dias do formato ABANDONADO sobe pro
# topo e vai ao ar.
#
#   python3 teste_idade_fila.py
import ast
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
_src = (BASE / "restaurar_idade_fila.py").read_text("utf-8")
# o default do parâmetro referencia MARGEM_DIAS do módulo; carrego a constante
# antes da função pra exercitar o MESMO valor que roda em produção
_ns = {"MARGEM_DIAS": 3.0}
for _no in ast.parse(_src).body:
    if isinstance(_no, ast.FunctionDef) and _no.name == "precisa_corrigir":
        exec(compile(ast.Module([_no], []), "x", "exec"), _ns)
precisa_corrigir = _ns["precisa_corrigir"]

ok = falhou = 0


def checa(desc, cond, extra=""):
    global ok, falhou
    if cond:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}" + (f"\n      {extra}" if extra else ""))


print("\n── a regra da correção ──")
# os números reais do estrago
checa("pasta 0.3d × plano 23.8d → corrige", precisa_corrigir(0.3, 23.8))
checa("pasta 0.3d × plano 5.6d → corrige", precisa_corrigir(0.3, 5.6))
checa("pasta 0.3d × plano 0.3d → NÃO corrige", not precisa_corrigir(0.3, 0.3))
checa("diferença de 2d fica dentro da margem",
      not precisa_corrigir(0.3, 2.2))

print("\n── ⚠️ SÓ CORRIGE NUM SENTIDO ──")
# pasta mais VELHA que o plano não é falsificação: é pacote que ninguém tocou.
# Corrigir isso seria inventar dado em cima de dado bom.
checa("pasta 20d × plano 2d → NÃO mexe", not precisa_corrigir(20.0, 2.0))
checa("sem plano (None) → NÃO mexe", not precisa_corrigir(0.3, None))

print("\n── ⚠️ NINGUÉM ESCREVE DENTRO DA PASTA DO PACOTE ──")
# `video.with_suffix(...)` põe o arquivo AO LADO do vídeo, ou seja, dentro da
# pasta — e criar/apagar arquivo lá zera o mtime dela. Foi assim nas duas vezes.
for arq in ("conferir_match.py", "diag_match.py", "consertar_audio_fila.py",
            "restaurar_audio_fila.py"):
    p = BASE / arq
    if not p.exists():
        continue
    s = p.read_text("utf-8")
    # ignora as linhas de comentário, que FALAM do defeito de propósito
    codigo = "\n".join(l for l in s.splitlines()
                       if not l.lstrip().startswith("#"))
    checa(f"{arq} não cria temporário com `video.with_suffix`",
          "with_suffix" not in codigo,
          "usa with_suffix no código — o arquivo cai dentro da pasta")
    if "tempfile" in codigo or "gettempdir" in codigo:
        checa(f"{arq} usa tempfile (fora da pasta)", True)

print("\n── ⚠️ E A FONTE DA VERDADE NÃO PODE SER TOCADA ──")
# a idade real vem de shared/content_plans/plano_<slug>.json, escrito uma vez
# na produção. Se alguma ferramenta reescrevesse isso, a testemunha sumia.
checa("o restaurador lê o plano_<slug>.json",
      'f"plano_{pasta.name}.json"' in _src)
checa("usa os.utime pra devolver, não recria a pasta",
      "os.utime(pasta" in _src and "rmtree" not in _src)
checa("tem modo seco (só mostra) antes do --aplicar",
      "--aplicar" in _src and "nada foi alterado" in _src)

print(f"\n{'='*66}\n   {ok} passou · {falhou} falhou\n{'='*66}")
raise SystemExit(1 if falhou else 0)
