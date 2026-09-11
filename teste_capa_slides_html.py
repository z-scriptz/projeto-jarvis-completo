#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_capa_slides_html.py -- a capa que VAI AO AR é a do slides_html
#
# POR QUE ISTO EXISTE (11/09/2026)
# ────────────────────────────────
# ⚠️⚠️ EU REDESENHEI A CAPA A NOITE INTEIRA NO ARQUIVO ERRADO.
#
# O `carrossel_render:777` faz:
#
#     from slides_html import renderizar_slides
#     prontos = renderizar_slides(plano, Path(saida))
#     if prontos:
#         return prontos          # ← acaba AQUI
#
# O `capa_html` é chamado 60 linhas DEPOIS desse `return`. Ele é a rede pra
# quando o navegador falha — nunca o que sai no post. Quatro estilos, rotação,
# afinidade, cor por nicho, 85 asserções: tudo num caminho morto pro carrossel.
#
# 📌 COMO EU ERREI: procurei `capa_html` dentro do `carrossel_render`, achei a
# chamada na linha 820, e tratei **"existe uma chamada"** como **"é chamado"**.
# Nunca olhei o que vinha antes. É a mesma classe que eu cataloguei o dia todo
# — o `comentarios.py` morto 5 dias, o formato `mitos` em peso 0 — cometida por
# mim, na maior escala da sessão.
#
# ⚠️ ENTÃO A PRIMEIRA SEÇÃO DESTE TESTE NÃO OLHA DESIGN NENHUM: ela olha QUEM
# DESENHA. Se alguém (eu) for mexer na capa de novo, é aqui que descobre qual
# arquivo importa, antes de gastar a noite.
#
#   python3 teste_capa_slides_html.py
import ast
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import slides_html as SH  # noqa: E402

ok = falhou = 0


def checa(desc, cond, extra=""):
    global ok, falhou
    if cond:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}" + (f"\n      {extra}" if extra else ""))


PLANO = {"nicho": "pet", "handle": "@topshoppet_", "formato": "mitos",
         "capa": {"hook": "4 mitos sobre seus *bichinhos* que voce acredita",
                  "sub": "e a maioria dos donos se engana", "foto": ""},
         "slides": [{"titulo": "Caes e gatos se odeiam", "texto": "nao e bem assim"},
                    {"titulo": "Gato e independente", "texto": "sao carinhosos"}],
         "cta": {"titulo": "Segue pra nao perder"}}

print("\n── ⚠️⚠️ QUEM DESENHA A CAPA QUE VAI AO AR ──")
_cr = (BASE / "carrossel_render.py").read_text("utf-8")
_i_sh = _cr.find("from slides_html import renderizar_slides")
_i_ret = _cr.find("return prontos", _i_sh)
_i_ch = _cr.find("from capa_html import renderizar_capa")
checa("o carrossel_render chama o slides_html", _i_sh > 0)
checa("…e RETORNA ali mesmo quando dá certo", 0 < _i_sh < _i_ret)
checa("⚠️ o capa_html vem DEPOIS desse return (é a rede, não o que sai)",
      0 < _i_ret < _i_ch,
      "se esta ordem inverter, o arquivo que manda mudou — leia antes de mexer")
checa("o slides_html tem a função da capa",
      any(isinstance(n, ast.FunctionDef) and n.name == "_html_capa"
          for n in ast.parse((BASE / "slides_html.py").read_text("utf-8")).body))

print("\n── ⚠️ A CAPA PERDEU O BLOCO DE MARCA (decisão do Dre, 11/09) ──")
# Este arquivo dizia desde 22/08 que o cabeçalho era idêntico nos 6 slides,
# vindo de referências de agosto. As de 10/09 são CAPAS que estouraram e
# nenhuma tem bloco de marca no topo. O Dre cortou: *"a referência mais recente
# decide, pq é estratégia nova e vem de virais"*.
os.environ.pop("CARR_CAPA_TOM", None)
capa = SH._html_capa(PLANO, 5)
# ⚠️ A ASSERÇÃO ERA `"TopShop" not in capa` E PASSAVA PELO MOTIVO ERRADO: o
# cabeçalho emite `Top<em ...>Shop</em>`, então a string literal NUNCA aparece
# — ela passaria com o cabeçalho ali do mesmo jeito. Terceira vez hoje que eu
# testo a forma em vez do fato. O elemento é que é inequívoco.
checa("a capa NÃO tem o cabeçalho (logo + @ + contador no topo)",
      'class="cabeca"' not in capa,
      "o bloco de marca voltou pro topo da capa")
checa("a capa não tem contador de página", 'class="cont"' not in capa)
checa("mas a marca continua na capa, no rodapé", "@topshoppet_" in capa)

print("\n   ── e o tom vem da paleta que já existia, sem cor nova ──")
_p = SH._paleta("pet")
checa("usa o `creme` do nicho como fundo", f"background:{_p['creme']}" in capa)
checa("o texto é o `escuro` do nicho", f"color:{_p['escuro']}" in capa)
checa("o destaque é o `acento` do nicho", _p["acento"] in capa)
checa("⚠️ nenhuma cor inventada fora da paleta",
      all(c in (_p["creme"], _p["escuro"], _p["acento"], _p["clarinho"],
                _p["sombra"], "#e8e4db")
          for c in set(__import__("re").findall(r"#[0-9A-Fa-f]{6}", capa))),
      str(set(__import__("re").findall(r"#[0-9A-Fa-f]{6}", capa))))

print("\n── ⚠️ OS SLIDES DE DENTRO NÃO MUDARAM ──")
# a regra de 22/08 continua valendo pro MIOLO: o cabeçalho é a âncora que deixa
# a composição variar sem o conjunto virar seis posts avulsos. Só a CAPA saiu.
_cab = SH._cabecalho(PLANO, 2, 5, False)
checa("o cabeçalho continua existindo pros outros slides",
      'class="cabeca"' in _cab)
checa("e ele tem o contador", "2" in _cab and "5" in _cab)

print("\n── ⚠️ REVERSÍVEL EM UMA LINHA (se o número piorar) ──")
os.environ["CARR_CAPA_TOM"] = "escuro"
_antiga = SH._html_capa(PLANO, 5)
checa("CARR_CAPA_TOM=escuro devolve a capa de antes",
      'class="cabeca"' in _antiga)
checa("…com o fundo escuro do nicho", f"background:{_p['escuro']}" in _antiga)
os.environ.pop("CARR_CAPA_TOM", None)
checa("sem a variável, o padrão é a capa CLARA",
      'class="cabeca"' not in SH._html_capa(PLANO, 5))

print("\n── ⚠️ A FOTO É CARTÃO, NÃO FUNDO ESCURECIDO ──")
# no @lucasmagazinetech o produto é a estrela; escurecer pra escrever por cima
# é o contrário. Sem foto, a capa é só tipografia (@rafabri7o).
checa("sem foto, nenhum cartão vazio", "capafoto" not in capa)
checa("a capa clara não usa a camada de véu", "fotocheia" not in capa)
_com_foto = dict(PLANO)
_com_foto["capa"] = dict(PLANO["capa"], foto=str(BASE / "teste_capa_slides_html.py"))
checa("plano com foto não quebra a montagem", bool(SH._html_capa(_com_foto, 5)))

print("\n── nada disso pode derrubar um post ──")
checa("plano sem capa nenhuma não quebra",
      bool(SH._html_capa({"nicho": "pet", "handle": "@x"}, 3)))
checa("nicho desconhecido cai na paleta geral",
      bool(SH._html_capa({"nicho": "nao_existe", "handle": "@x",
                          "capa": {"hook": "oi"}}, 3)))
checa("hook gigante não estoura",
      bool(SH._html_capa({"nicho": "pet", "handle": "@x",
                          "capa": {"hook": "u" * 300}}, 3)))

print(f"\n{'='*66}\n   {ok} passou · {falhou} falhou\n{'='*66}")
raise SystemExit(1 if falhou else 0)
