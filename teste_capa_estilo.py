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

print("\n── ⚠️ AFINIDADE: quando o conteúdo tem forma, o template segue a forma ──")
# O Dre: *"podemos misturar estilos... e manter o template pra cada um"*. Sim —
# mas sortear entre TODOS seria pior que o template único: colocaria duas
# colunas MITO|VERDADE num carrossel de "5 achadinhos", onde não há dois lados.
os.environ.pop("CARR_ESTILO", None)
checa("carrossel de mitos → capa de mito/verdade",
      C._escolher_estilo("@x", "mitos") == "mito_verdade")
checa("carrossel de comparação → capa de versus",
      C._escolher_estilo("@x", "comparacao") == "versus")
for f in ("lista", "erros", "historia", "passo_a_passo", "antes_depois", ""):
    checa(f"'{f or 'sem formato'}' cai no sorteio livre",
          C._escolher_estilo("@y", f) in C.ESTILOS_LIVRES)
# ⚠️ o lado que NÃO pode disparar: estilo de duas colunas em post sem dois lados
checa("⚠️ o sorteio livre NUNCA devolve capa de duas colunas",
      all(C._escolher_estilo(f"@c{i}", "lista") in ("claro", "escuro")
          for i in range(12)))

print("\n── ⚠️ AS CORES DA PALETA FORAM FEITAS PRA FUNDO PRETO ──")
# renderizado o pet (#5EC8FF) sobre o creme, a palavra em destaque ficou MAIS
# fraca que o preto ao lado: a que devia saltar virou a menos legível
checa("_escurecer escurece de verdade",
      C._escurecer("#5EC8FF") != "#5EC8FF" and len(C._escurecer("#5EC8FF")) == 7)
checa("cor inválida não quebra", C._escurecer("nao-e-cor") == "nao-e-cor")
# e o texto SOBRE a tarja tem que ser escolhido pela luminância, não cravado
# ⚠️ EU TINHA ASSERTADO QUE O ROXO PEDIA TEXTO BRANCO, e a medição derrubou:
# #D67AFF tem luminância 0.59 e com ela o texto ESCURO é mais legível. Medindo
# a paleta inteira, as SEIS cores são claras (0.59 a 0.87) — foram desenhadas
# pra fundo preto, onde elas é que são o brilho. Então em capa clara nenhuma
# aceita texto branco por cima, e a função só existe pra não travar isso numa
# constante: no dia em que entrar uma cor escura, ela decide sozinha.
for _n, _c in C.CORES.items():
    checa(f"tarja de '{_n}' pede texto escuro (paleta clara)",
          C._contraste(_c) == "#111", f"{_c} lum alta")
checa("e uma cor ESCURA pediria texto claro", C._contraste("#2B1B4D") == "#fff")
checa("_contraste não quebra com lixo", C._contraste("") in ("#111", "#fff"))
_tech = C.montar_html({"nicho": "tech", "handle": "@t", "slides": [{}],
                       "capa": {"hook": "um [dobro] disso", "sub": "s",
                                "estilo": "claro"}})
checa("⚠️ a capa do tech não pinta branco sobre limão",
      "color:#111" in _tech, "branco sobre #A3FF4F some")

print("\n── ⚠️ A CAPA DE DUAS COLUNAS DEGRADA, NÃO QUEBRA ──")
# capa que só sai com o JSON perfeito é capa que um dia não sai, e "não saiu"
# no meio da esteira custa mais que uma capa genérica
_sem_lados = C.montar_html({"nicho": "casa", "handle": "@c", "slides": [{}],
                            "capa": {"hook": "e ai?", "sub": "s",
                                     "estilo": "mito_verdade"}})
checa("sem lado_a/lado_b ainda sai capa", bool(_sem_lados) and "MITO" in _sem_lados)
checa("os rótulos MITO e VERDADE aparecem",
      "MITO" in _sem_lados and "VERDADE" in _sem_lados)
_vs = C.montar_html({"nicho": "tech", "handle": "@t", "slides": [{}, {}],
                     "capa": {"hook": "qual?", "sub": "s", "estilo": "versus"}})
checa("o versus tem o 'vs' no meio", ">vs<" in _vs)
checa("o mito/verdade NÃO tem símbolo no meio (× lê como multiplicação)",
      'class="meio"' not in _sem_lados)
checa("⚠️ o cartão não é branco sobre branco no versus",
      "#f2f2f5" in _vs, "cartão invisível: só a sombra denunciava")

print("\n── ⚠️ A FOTO É O QUE FALTAVA PRA CHEGAR NA REFERÊNCIA ──")
# no @homemquesabetudo (4.163 curtidas) a MESMA esponja aparece em MITO e em
# VERDADE: o contraste está no texto, e repetir a imagem é o que deixa isso
# óbvio antes de a pessoa ler
_com_foto = C.montar_html({
    "nicho": "casa", "handle": "@c", "slides": [{}],
    "capa": {"hook": "e ai?", "sub": "s", "estilo": "mito_verdade",
             "lado_a": "a", "lado_b": "b",
             "foto_a": str(BASE / "teste_capa_estilo.py")}})   # arquivo real
checa("com foto, o cartão ganha bloco de imagem", 'class="img"' in _com_foto)
checa("sem foto, nenhum bloco de imagem vazio",
      'class="img"' not in _sem_lados)
# ⚠️ `_b64("")` virava Path(".") — que EXISTE e é DIRETÓRIO — e estourava com
# IsADirectoryError. Estava ali desde sempre; só apareceu quando um chamador
# novo passou "". `is_file()` responde a pergunta certa, `exists()` não.
checa("caminho vazio não estoura o _b64", C._b64("") == "")
checa("diretório não vira imagem", C._b64(".") == "")
checa("arquivo inexistente devolve vazio", C._b64("/nao/existe.jpg") == "")

print("\n── ⚠️ E O GERADOR PREENCHE OS DOIS LADOS ──")
# capa que adivinha é capa que um dia adivinha errado
_cb = (BASE / "carrossel_brain.py").read_text("utf-8")
_ns = {}
for _n in ast.parse(_cb).body:
    if isinstance(_n, ast.FunctionDef) and _n.name == "_lados_da_capa":
        exec(compile(ast.Module([_n], []), "x", "exec"), _ns)
_lados = _ns.get("_lados_da_capa")
checa("_lados_da_capa existe", _lados is not None)
if _lados:
    checa("formato sem dois lados não ganha campo nenhum",
          _lados("lista", [{"nome": "x", "foto": "a.jpg"}], [{}]) == {})
    _c = _lados("comparacao", [{"nome": "Fone 40", "foto": "a.jpg"},
                               {"nome": "Fone 200", "foto": "b.jpg"}], [])
    checa("comparação leva os DOIS produtos e as DUAS fotos",
          _c.get("rotulo_a") == "Fone 40" and _c.get("foto_b") == "b.jpg", str(_c))
    _m = _lados("mitos", [{"nome": "Esponja", "foto": "e.jpg"}],
                [{"titulo": "usar ate estragar"}, {"titulo": "trocar em 15 dias"}])
    checa("⚠️ no mitos a foto é a MESMA dos dois lados (é o formato)",
          _m.get("foto_a") == _m.get("foto_b") == "e.jpg", str(_m))
    checa("e os textos vêm dos slides", _m.get("lado_a") == "usar ate estragar")
    checa("sem produto e sem slide não inventa campo vazio",
          _lados("mitos", [], []) == {},
          "campo vazio é pior que ausente: a capa trata ausente como 'cai pro "
          "slide' e vazio como 'é isso mesmo'")
    checa("o gerador realmente chama isso",
          "**_lados_da_capa(formato, produtos, slides)" in _cb)

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
