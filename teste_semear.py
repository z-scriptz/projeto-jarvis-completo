#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_semear.py -- o semeador lê a evidência paga e grava a chave CERTA
#
# POR QUE ISTO EXISTE (09/09/2026)
# ────────────────────────────────
# O `semear_reprovados` gravaria um cache inútil sem erro nenhum no log se:
#   · a chave que ele grava não fosse a mesma que o coletor lê;
#   · ele sobrescrevesse contas mais novas em vez de somar;
#   · ele carimbasse tudo com `agora`, fazendo as 119 contas expirarem juntas.
#
# Nenhuma dessas três falha em pé: o script roda, imprime número bonito e o
# guarda continua inerte. Então o teste monta uma árvore de VERDADE (pacotes,
# JSONs, mtimes) e roda o `main()` em cima dela.
#
#   python3 teste_semear.py
import ast
import importlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

ok = falhou = 0


def checa(desc, cond, extra=""):
    global ok, falhou
    if cond:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}" + (f"\n      {extra}" if extra else ""))


# ── monta a árvore ────────────────────────────────────────────────────────────
tmp = Path(tempfile.mkdtemp(prefix="semear_"))
rep = tmp / "reprovado_match"
rep.mkdir()
cache = tmp / "produtos_reprovados.json"
AGORA = time.time()
DIA = 86400


def pacote(nome_pasta, produto, arquivo="plano.json", dias_atras=1.0):
    p = rep / nome_pasta
    p.mkdir()
    if produto is not None:
        (p / arquivo).write_text(json.dumps({"produto": produto}),
                                 encoding="utf-8")
    t = AGORA - dias_atras * DIA
    os.utime(p, (t, t))
    return p


# o laço real: 4 pacotes, o MESMO item da loja. As variações que a loja
# realmente devolve são de CAIXA e ACENTO — e essas o `_norm_produto` colapsa.
pacote("miniluxury_1", "Mini Frasco De Perfume 2ml 100PCS Spray Recarregável", dias_atras=1)
pacote("miniluxury_2", "mini frasco de perfume 2ml 100pcs spray recarregavel", dias_atras=2)
pacote("miniluxury_3", "MINI FRASCO DE PERFUME 2ML 100PCS SPRAY RECARREGÁVEL", dias_atras=3)
# veio da fila (--fila): guarda engajamento.json, não plano.json
pacote("miniluxury_4", "Mini  Frasco de Perfume 2ml 100pcs  Spray Recarregavel!",
       arquivo="engajamento.json", dias_atras=4)
# um item reprovado UMA vez só — conta parcial, não queima
pacote("bone_1", "Suporte Para Lavar Bonés Na Máquina De Lavar", dias_atras=5)
# pacote sem nome legível (a origem foi podada) — tem que ser contado à parte
pacote("orfao_1", None)
# JSON quebrado não pode derrubar a varredura inteira
_q = rep / "quebrado_1"
_q.mkdir()
(_q / "plano.json").write_text("{isso não é json", encoding="utf-8")
# arquivo solto no meio das pastas não pode quebrar nada
(rep / "leiame.txt").write_text("x", encoding="utf-8")

sem = importlib.import_module("semear_reprovados")
sem.REPROVADOS = rep
sem.PRODUTOS_REPROVADOS = cache
# o módulo importou as funções do coletor por VALOR; para redirecionar o arquivo
# de saída eu tenho que reapontar as duas que tocam o disco
import tiktok_coletor as tc
tc.PRODUTOS_REPROVADOS = cache

print("\n── a chave: quatro grafias, um produto ──")
os.environ["MATCH_MAX_REPROVA"] = "3"
_saida = sem.main()   # modo seco
checa("modo seco roda sem gravar", _saida == 0 and not cache.exists())

sys.argv = ["semear_reprovados.py", "--aplicar"]
sem.main()
checa("o --aplicar grava o cache", cache.exists())
pr = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}

_ch_perf = tc._norm_produto("Mini Frasco De Perfume 2ml 100PCS Spray Recarregável")
checa("as 4 grafias caíram numa chave só",
      pr.get(_ch_perf, {}).get("n") == 4,
      f"chaves gravadas: {list(pr)}")
checa("o produto de 1 reprovação entrou com a conta PARCIAL",
      pr.get(tc._norm_produto("Suporte Para Lavar Bonés Na Máquina De Lavar"),
             {}).get("n") == 1)
checa("órfão e JSON quebrado não viraram chave", len(pr) == 2, f"{list(pr)}")

print("\n── ⚠️ O LIMITE CONHECIDO DA CHAVE: ela acaba na 8ª palavra ──")
# ⚠️ ISTO NÃO É DEFEITO NOVO, É O `_norm_produto` DO DEDUP (que o guarda
# reusa de propósito — duas chaves seriam dois caches). Mas é o teto do
# guarda, e é melhor ter escrito aqui do que descobrir no log:
#   caixa e acento     → MESMA chave (é o que a loja varia de verdade)
#   8ª palavra difere  → chave DIFERENTE, e o guarda conta separado
# Se um dia o log mostrar o mesmo item queimando em duas chaves, o conserto
# é aqui — e mexer nisto mexe TAMBÉM no dedup de produto, que tem cache em
# produção. Não é troca de uma linha.
checa("caixa e acento colapsam na mesma chave",
      tc._norm_produto("MINI FRASCO DE PERFUME 2ML 100PCS SPRAY RECARREGÁVEL")
      == tc._norm_produto("mini frasco de perfume 2ml 100pcs spray recarregavel"))
checa("pontuação e espaço duplo colapsam",
      tc._norm_produto("Mini  Frasco de Perfume 2ml 100pcs  Spray Recarregavel!")
      == _ch_perf)
checa("⚠️ a 8ª palavra diferente NÃO colapsa (teto conhecido)",
      tc._norm_produto("Mini Frasco De Perfume 2ml 100PCS Spray Recar") != _ch_perf,
      "se isto passar a colapsar, alguém mexeu no _norm_produto — "
      "confira o dedup de produto antes de comemorar")

print("\n── ⚠️ A CHAVE TEM QUE SER A QUE O COLETOR LÊ ──")
# se o semeador copiasse `_norm_produto` em vez de importar, uma mudança nele
# encheria o cache de chaves que o coletor nunca procuraria — sem erro no log
checa("o coletor considera o perfume QUEIMADO",
      tc._produto_queimado(_ch_perf, pr, limite=3))
checa("o coletor NÃO queima o de conta parcial",
      not tc._produto_queimado(
          tc._norm_produto("Suporte Para Lavar Bonés"), pr, limite=3))
_src_sem = (BASE / "semear_reprovados.py").read_text("utf-8")
_codigo = "\n".join(l for l in _src_sem.splitlines()
                    if not l.lstrip().startswith("#"))
checa("importa `_norm_produto`, não tem cópia dele",
      "from tiktok_coletor import" in _codigo and "def _norm_produto" not in _codigo)

print("\n── ⚠️ O CARIMBO É O DA REPROVAÇÃO, NÃO O DE AGORA ──")
# com `time.time()` as 119 contas expirariam todas no mesmo dia, e o laço
# voltaria inteiro de uma vez
_ts = pr.get(_ch_perf, {}).get("ts", 0)
checa("o ts veio do mtime da pasta (~1 dia atrás), não de agora",
      AGORA - 2 * DIA < _ts < AGORA - 0.5 * DIA,
      f"ts={_ts} agora={AGORA:.0f}")
checa("usa o mtime MAIS NOVO do grupo (a reprovação mais recente)",
      abs(_ts - (AGORA - 1 * DIA)) < 3600)
checa("conta velha demais deixa de queimar",
      not tc._produto_queimado(_ch_perf, {_ch_perf: {"n": 9, "ts": 0}},
                               limite=3, dias=30))

print("\n── ⚠️ SOMA, NÃO SOBRESCREVE ──")
# se uma rodada já rodou com o guarda ligado, o cache tem conta que o semeador
# não conhece. Sobrescrever apagaria evidência mais nova que a minha.
cache.write_text(json.dumps({
    _ch_perf: {"n": 2, "ts": int(AGORA)},
    "produto so do coletor": {"n": 5, "ts": int(AGORA)},
}), encoding="utf-8")
sem.main()
pr2 = json.loads(cache.read_text(encoding="utf-8"))
checa("a conta do coletor foi SOMADA à do semeador",
      pr2.get(_ch_perf, {}).get("n") == 6, f"n={pr2.get(_ch_perf)}")
checa("chave que só o coletor tinha continua lá",
      pr2.get("produto so do coletor", {}).get("n") == 5)
checa("o ts mais novo prevalece",
      abs(pr2.get(_ch_perf, {}).get("ts", 0) - AGORA) < 3600)

print("\n── ⚠️ NINGUÉM ESCREVE DENTRO DA PASTA DO PACOTE ──")
# 41 pacotes em 06/09, 185 em 08/09. O semeador varre 119 pastas: se ele
# escrevesse UM arquivo em cada uma, zeraria 119 mtimes de uma vez.
checa("o semeador não usa with_suffix", "with_suffix" not in _codigo)
checa("não escreve nas pastas varridas (só write_text no cache)",
      _codigo.count("write_text") == 0 and "_salvar_reprovados(pr)" in _codigo)
_mt = (rep / "miniluxury_1").stat().st_mtime
checa("o mtime das pastas varridas continua intacto",
      abs(_mt - (AGORA - 1 * DIA)) < 60, f"mtime={_mt}")

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{'='*64}\n   {ok} passou · {falhou} falhou\n{'='*64}")
raise SystemExit(1 if falhou else 0)
