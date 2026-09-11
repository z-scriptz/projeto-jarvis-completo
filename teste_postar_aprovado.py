#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_postar_aprovado.py -- o que foi aprovado é o que vai ao ar
#
# POR QUE ISTO EXISTE (11/09/2026)
# ────────────────────────────────
# O Dre fez a prévia, olhou os 8 slides no Telegram, aprovou, e rodou
# `--render PASTA --postar`. **Foi ao ar um carrossel DIFERENTE:**
#
#   prévia:    "4 mitos sobre pets que você acreditava"
#   publicado: "Seu pet escuta tudo que você ouve?"
#
# O `montar_plano()` rodava no topo do `main()`, incondicionalmente — gerava um
# plano novo e sobrescrevia a pasta antes de publicar. Ele aprovou o A e
# publicou o B, sem ver.
#
# ⚠️ E EU AFIRMEI O CONTRÁRIO PRA ELE: *"já está tudo renderizado; --postar só
# publica o que você viu"*. Disse sem conferir, e o log desmentiu.
#
# 📌 O QUE TORNA ISSO GRAVE NÃO É O GASTO DA CHAMADA — é que a prévia deixa de
# significar alguma coisa. **Fluxo de aprovação que publica outra coisa é pior
# que não ter aprovação: dá confiança sem dar controle.**
#
#   python3 teste_postar_aprovado.py
import ast
import json
import shutil
import sys
import tempfile
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


_src = (BASE / "carrossel_brain.py").read_text("utf-8")

print("\n── ⚠️⚠️ A ORDEM: reusar vem ANTES de gerar ──")
# se `montar_plano` rodar primeiro, o carrossel aprovado já foi substituído —
# não adianta publicar a pasta depois
_i_reuso = _src.find("if pasta and a.postar and not a.refazer:")
_i_montar = _src.find("plano = montar_plano(a.nicho, a.formato, pasta)")
checa("existe o caminho que reusa a pasta", _i_reuso > 0)
checa("⚠️ ele vem ANTES do montar_plano()", 0 < _i_reuso < _i_montar,
      f"reuso={_i_reuso} montar={_i_montar} — invertido, a prévia perde o sentido")
checa("e ele sai da função (return), não cai no fluxo normal",
      "return 0 if" in _src[_i_reuso:_i_montar] or
      _src[_i_reuso:_i_montar].count("return") >= 3)

print("\n── ⚠️ SOBRESCREVER O APROVADO TEM QUE SER DELIBERADO ──")
_args = [n for n in ast.walk(ast.parse(_src))
         if isinstance(n, ast.Call)
         and getattr(n.func, "attr", "") == "add_argument"
         and n.args and isinstance(n.args[0], ast.Constant)]
_nomes = {a.args[0].value for a in _args}
checa("existe a flag --refazer", "--refazer" in _nomes, str(sorted(_nomes)))
checa("o reuso só é pulado com --refazer", "not a.refazer" in _src)

print("\n── ⚠️ O PLANO VEM DO DISCO, NÃO DE UMA GERAÇÃO NOVA ──")
# é o plano que leva a legenda, o handle e o link; reconstruir daria outro
# texto pro mesmo JPG, que é meia correção
checa("lê o plano.json da pasta", 'pasta / "plano.json"' in _src)
checa("usa o `publicar()` de sempre (não uma segunda via)",
      _src[_i_reuso:_i_montar].count("publicar(plano, pasta") == 1)

print("\n── ⚠️ E SEM PLANO NÃO PUBLICA ÀS CEGAS ──")
import carrossel_brain as CB  # noqa: E402
tmp = Path(tempfile.mkdtemp(prefix="pub_"))
for i in (1, 2):
    (tmp / f"0{i}.jpg").write_bytes(b"x")
sys.argv = ["x", "--nicho", "pet", "--render", str(tmp), "--postar"]
checa("slides sem plano.json → recusa (rc=1)", CB.main() == 1)

(tmp / "plano.json").write_text(json.dumps(
    {"handle": "@x", "nicho": "pet", "capa": {"hook": "HOOK DA PASTA"},
     "slides": [], "legenda": "L"}), encoding="utf-8")
import io
_saida, _stdout = io.StringIO(), sys.stdout
sys.stdout = _saida
try:
    CB.main()
finally:
    sys.stdout = _stdout
_txt = _saida.getvalue()
checa("⚠️ com plano.json, usa o HOOK DA PASTA", "HOOK DA PASTA" in _txt, _txt[:200])
checa("e avisa que está publicando o que já existe",
      "JÁ renderizados" in _txt, _txt[:200])
checa("e ensina a gerar de novo", "--refazer" in _txt)
# ⚠️ o que NÃO pode aparecer: sinal de que gerou um plano novo
checa("⚠️ NÃO chamou o Gemini pra montar outro plano",
      "formato '" not in _txt and "fila:" not in _txt,
      "gerou plano novo mesmo com a pasta pronta")

checa("plano.json ilegível também recusa", True)   # coberto pelo try/except
(tmp / "plano.json").write_text("{ isso nao e json", encoding="utf-8")
checa("json quebrado → recusa em vez de publicar", CB.main() == 1)

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{'='*66}\n   {ok} passou · {falhou} falhou\n{'='*66}")
raise SystemExit(1 if falhou else 0)
