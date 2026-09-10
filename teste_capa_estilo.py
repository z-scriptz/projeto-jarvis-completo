#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_capa_estilo.py -- a capa deixou de ser um template só
#
# POR QUE ISTO EXISTE (10/09/2026)
# ────────────────────────────────
# O Dre: *"as imagens estão todas iguais... a pessoa sabe que é da página, mas
# às vezes cansa visualmente, parece estar repetido"*. Não era impressão: o
# `capa_html.montar_html` era UM html — fundo #0d0d0f, foto a 62% de brilho,
# véu, vinheta, logo circular com selo ✓ e contador no topo, hook em CAIXA
# ALTA. **Sete formatos de conteúdo, um visual.**
#
# E os cinco virais que ele mandou dizem o contrário: QUATRO têm fundo claro e
# NENHUM tem bloco de marca no topo.
#
# ⚠️ ESTE TESTE OLHA O QUE SAI DE CENA, não a cor. A capa clara não é "a escura
# pintada de branco" — o que a aproxima das referências é o que ela deixou de
# ter: logo, selo, contador e caixa alta.
#
#   python3 teste_capa_estilo.py
import ast
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import capa_html as C  # noqa: E402

ok = falhou = 0


def checa(desc, cond, extra=""):
    global ok, falhou
    if cond:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}" + (f"\n      {extra}" if extra else ""))


PLANO = {"nicho": "casa", "handle": "@topshopcasa_",
         "capa": {"hook": "3 [erros] que quase todo mundo comete",
                  "sub": "o terceiro me custou caro"},
         "slides": [{}, {}, {}]}

tmp = Path(tempfile.mkdtemp(prefix="capa_"))
C._MEM_ESTILO = tmp / "estilos.json"


def html(estilo):
    p = dict(PLANO)
    p["capa"] = dict(PLANO["capa"], estilo=estilo)
    return C.montar_html(p)


claro, escuro = html("claro"), html("escuro")

print("\n── os dois estilos existem e são DIFERENTES ──")
checa("há mais de um estilo", len(C.ESTILOS) >= 2, str(C.ESTILOS))
checa("o html sai diferente em cada um", claro != escuro)
checa("o escuro continua escuro (#0d0d0f)", "#0d0d0f" in escuro)
checa("o claro tem fundo claro", "#f4f1ea" in claro)

print("\n── ⚠️ O QUE SAI DE CENA: nenhum dos 5 virais tem bloco de marca ──")
# aquele bloco comia os 150px superiores de toda capa e é a primeira coisa que
# denuncia post de página comercial
checa("o claro NÃO tem logo circular no topo", 'class="logo"' not in claro)
checa("o claro NÃO tem o selo ✓", "selo" not in claro)
checa("o claro NÃO tem contador de página no topo", '<div class="pag">' not in claro)
checa("mas a marca continua na capa (rodapé)", "@topshopcasa_" in claro)

print("\n── ⚠️⚠️ CAIXA ALTA: TESTAR O TEXTO, NÃO A REGRA CSS ──")
# ⚠️ A PRIMEIRA VERSÃO DESTE TESTE PASSOU COM A CAPA ERRADA. Eu assertava
# `"text-transform:uppercase" not in claro` — verdadeiro — e a capa saiu em
# CAIXA ALTA do mesmo jeito, porque o `montar_html` já fazia `.upper()` no
# Python antes de escolher o estilo. **Testei a regra, não o efeito**, que é
# exatamente a classe de defeito que este projeto persegue o dia todo. Só
# apareceu quando eu renderizei a imagem e OLHEI.
checa("o escuro força uppercase (como era)", "text-transform:uppercase" in escuro)
checa("o claro não tem a regra CSS de uppercase",
      "text-transform:uppercase" not in claro)
checa("⚠️ e o TEXTO do claro chega em caixa normal",
      "quase todo mundo comete" in claro,
      "o Python já entregava .upper() — a regra CSS não desfaz isso")
checa("⚠️ o subtítulo do claro também",
      "o terceiro me custou caro" in claro)
checa("o escuro continua recebendo o texto em maiúscula",
      "QUASE TODO MUNDO COMETE" in escuro)

print("\n── ⚠️ A TARJA TEM QUE SOBREVIVER À QUEBRA DE LINHA ──")
# ⚠️ Na 1ª imagem renderizada o trecho marcado era "na casa", que quebrou em
# DUAS linhas — e `::before` absoluto dentro de um `display:inline` partido se
# ancora só no primeiro fragmento. O bloco virou uma barra de 6px e sobrou
# "NA CASA" em BRANCO sobre fundo creme: ilegível.
# `box-decoration-break:clone` pinta o fundo em cada fragmento.
checa("o claro não usa ::before pra tarja", ".tarja::before" not in claro)
checa("usa box-decoration-break (pinta cada linha)",
      "box-decoration-break:clone" in claro)
checa("a cor do nicho está na própria tarja", ".tarja {" in claro or ".tarja{" in claro)
_marcado = C.montar_html({"nicho": "casa", "handle": "@x", "slides": [{}],
                          "capa": {"hook": "erro [na casa] que ninguem ve",
                                   "sub": "s", "estilo": "claro"}})
checa("trecho marcado que quebra linha continua no html",
      'class="tarja"' in _marcado and "na casa" in _marcado)

print("\n── ⚠️ A FOTO É CARTÃO, NÃO FUNDO ESCURECIDO ──")
# no @lucasmagazinetech o produto é a estrela; escurecer a 62% é o oposto
checa("o escuro escurece a foto (brightness)", "brightness(.62)" in escuro)
checa("o claro não escurece nada", "brightness(" not in claro)
checa("sem foto, o claro não deixa cartão vazio",
      'class="cartao"' not in claro, "não havia foto no plano")
com_foto = dict(PLANO)
com_foto["capa"] = dict(PLANO["capa"], estilo="claro", fundo="")
checa("plano sem foto não quebra", bool(C.montar_html(com_foto)))

print("\n── ⚠️ O TEXTO CONTINUA CABENDO (isso não é estilo, é legibilidade) ──")
for est in ("claro", "escuro"):
    h = html(est)
    checa(f"{est}: o JS mede e encolhe o hook",
          "offsetHeight" in h and "fontSize" in h)
_longo = dict(PLANO)
_longo["capa"] = {"hook": "u" * 220, "sub": "x", "estilo": "claro"}
checa("hook gigante não estoura a montagem", bool(C.montar_html(_longo)))

print("\n── ⚠️ ROTAÇÃO: não pode cair sempre no mesmo ──")
# a mesmice é o defeito que este arquivo veio consertar; sortear sem memória
# devolveria o mesmo estilo várias vezes seguidas
os.environ.pop("CARR_ESTILO", None)
saidas = [C._escolher_estilo("@topshopcasa_") for _ in range(8)]
checa("usa os dois estilos em 8 sorteios", len(set(saidas)) == 2,
      str(Counter(saidas)))
checa("nunca repete o imediatamente anterior",
      not any(saidas[i] == saidas[i + 1] for i in range(len(saidas) - 1)),
      str(saidas))
checa("a memória foi pro disco", C._MEM_ESTILO.exists())

print("\n   ── e é POR CONTA, não global ──")
# duas contas postando no mesmo dia não podem herdar a rotação uma da outra
mem = json.loads(C._MEM_ESTILO.read_text(encoding="utf-8"))
C._escolher_estilo("@topshoppet_")
mem2 = json.loads(C._MEM_ESTILO.read_text(encoding="utf-8"))
checa("cada conta tem sua chave", len(mem2) == len(mem) + 1, str(list(mem2)))

print("\n   ── e dá pra travar por .env ──")
os.environ["CARR_ESTILO"] = "claro"
checa("CARR_ESTILO força o estilo",
      all(C._escolher_estilo("@x") == "claro" for _ in range(4)))
os.environ["CARR_ESTILO"] = "nao_existe"
checa("valor inválido no .env não trava a capa",
      C._escolher_estilo("@x") in C.ESTILOS)
os.environ.pop("CARR_ESTILO", None)

print("\n── ⚠️ O FORMATO QUE ELE MANDOU ESTAVA DESLIGADO ──")
# @homemquesabetudo, MITO | VERDADE sobre a esponja: 4.163 curtidas. A
# estrutura estava pronta aqui, em peso 0, com o comentário "entra na roda
# quando o Dre quiser" — e ninguém nunca quis porque ninguém sabia que dava.
_src = (BASE / "carrossel_brain.py").read_text("utf-8")
_i = _src.find("FORMATOS = {")
_fmts = ast.literal_eval(_src[_i + 11:_src.find("\n}\n", _i) + 2])
checa("o formato 'mitos' está LIGADO", _fmts["mitos"]["peso"] > 0,
      f"peso={_fmts['mitos']['peso']}")
checa("nenhum formato sozinho passa de 1/3 da roda",
      max(f["peso"] for f in _fmts.values()) <= sum(
          f["peso"] for f in _fmts.values()) / 3 + 1,
      str({k: v["peso"] for k, v in _fmts.items()}))
checa("continuam existindo 7 formatos", len(_fmts) == 7, str(list(_fmts)))

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{'='*66}\n   {ok} passou · {falhou} falhou\n{'='*66}")
raise SystemExit(1 if falhou else 0)
