#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_veneno.py -- o pacote que não renderiza sai da fila ou fica pra sempre?
#
# O DEFEITO QUE ISTO TRAVA (05/09/2026)
# ─────────────────────────────────────
# Numa rodada de 6, um vídeo do inbox baixou truncado SEM O FRAME 0:
#
#   OSError: failed to read the first frame of video file
#            .../amaziiiigfinds_7632098200769367310/video.mp4
#
# A rodada saiu 5/6. Sem contador de falhas, esse pacote fica na fila pra
# sempre: é escolhido, falha, continua lá, e amanhã queima outro slot. Com 6
# posts/dia, um veneno na frente custa 1/6 da produção diária, todo dia.
#
# Já tinha acontecido em 17/08 (o "pacote-veneno" do roadmap).
#
# Roda em qualquer lugar: mexe em plano.json de mentira numa pasta temporária.
#   python3 teste_veneno.py
import ast
import json
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent

# ⚠️ `produzir_tiktok` importa moviepy no topo, o que não existe no dev local.
# Carrego só o que preciso, do fonte, sem executar o módulo inteiro.
_src = (BASE / "produzir_tiktok.py").read_text("utf-8")
_arv = ast.parse(_src)
_ns = {"json": json, "Path": Path, "os": __import__("os"),
       "_log": lambda *a, **k: None}
for _no in _arv.body:
    if isinstance(_no, ast.FunctionDef) and _no.name in ("_contar_falha",):
        exec(compile(ast.Module([_no], []), "produzir_tiktok.py", "exec"), _ns)
    if isinstance(_no, ast.Assign) and getattr(
            _no.targets[0], "id", "") == "MAX_FALHAS_RENDER":
        _ns["MAX_FALHAS_RENDER"] = 3

_contar_falha = _ns["_contar_falha"]
MAX = _ns["MAX_FALHAS_RENDER"]

ok = falhou = 0


def checa(desc, cond):
    global ok, falhou
    if cond:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}")


def plano(**campos) -> Path:
    d = Path(tempfile.mkdtemp())
    pj = d / "plano.json"
    base = {"produto": "Vídeo Corrompido de Teste", "imagem": "http://x/y.jpg"}
    base.update(campos)
    pj.write_text(json.dumps(base), encoding="utf-8")
    return pj


def ler(pj: Path) -> dict:
    return json.loads(pj.read_text(encoding="utf-8"))


print(f"\n── o veneno sai depois de {MAX} falhas, não na 1ª ──")
pj = plano()
n1 = _contar_falha(pj)
checa("1ª falha: conta mas NÃO bloqueia (pode ser rede/disco)",
      n1 == 1 and not ler(pj).get("nao_e_produto"))
n2 = _contar_falha(pj)
checa("2ª falha: ainda na fila", n2 == 2 and not ler(pj).get("nao_e_produto"))
n3 = _contar_falha(pj)
checa(f"{MAX}ª falha: sai da fila", n3 == MAX and ler(pj).get("nao_e_produto"))
checa("o motivo fica gravado (pra dar pra desfazer sabendo o porquê)",
      "render" in (ler(pj).get("motivo_bloqueio") or ""))

print("\n── conta, não apaga ──")
# ⚠️ mesma regra do limpar_inbox e do conferir_match: veredito de máquina tem
# de ser reversível tirando uma chave do JSON.
checa("o pacote continua existindo em disco", pj.exists())
checa("o nome do produto não foi tocado",
      ler(pj)["produto"] == "Vídeo Corrompido de Teste")
d = ler(pj)
del d["nao_e_produto"]
pj.write_text(json.dumps(d), encoding="utf-8")
checa("dá pra desbloquear tirando a chave", not ler(pj).get("nao_e_produto"))

print("\n── o contador não zera nem estoura ──")
pj2 = plano(falhas_render=1)
checa("continua de onde parou (não recomeça do zero)",
      _contar_falha(pj2) == 2)
pj3 = plano(falhas_render=99)
checa("pacote já muito falhado bloqueia na hora",
      _contar_falha(pj3) == 100 and ler(pj3).get("nao_e_produto"))

print("\n── plano ilegível não derruba a rodada ──")
d4 = Path(tempfile.mkdtemp())
pj4 = d4 / "plano.json"
pj4.write_text("{isso não é json", encoding="utf-8")
checa("devolve 0 em vez de explodir", _contar_falha(pj4) == 0)
pj5 = Path(tempfile.mkdtemp()) / "nem_existe.json"
checa("arquivo que não existe também não explode", _contar_falha(pj5) == 0)

print(f"\n{'='*52}\n   {ok} passou · {falhou} falhou\n{'='*52}")
raise SystemExit(1 if falhou else 0)
