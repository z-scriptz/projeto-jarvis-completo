#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_diag_env.py -- o auditor acha a linha certa e NÃO vaza segredo
#
# POR QUE ISTO EXISTE (10/09/2026)
# ────────────────────────────────
# O `diag_env.py` errou o veredicto sobre a MESMA linha três vezes seguidas
# durante o desenvolvimento, cada vez por um motivo diferente:
#
#   1ª  `AUTO_RESP_DM_TMPL` → FANTASMA ("ninguém lê") — porque a chave está
#       dentro de um `IfExp` (`get("A" if x else "B", "")`) e eu só olhava
#       `args[0].value`. Ou seja: o diagnóstico dizia que ninguém lia a variável
#       que estava apagando as frases novas.
#   2ª  → NORMAL — porque o padrão do `get` é `""`; o banco só aparece na linha
#       seguinte (`env if env.strip() else _BANCO`), que é o idioma do projeto.
#   3ª  `GEMINI_API_KEY` → SOMBRA, com sugestão de COMENTAR a chave da API,
#       porque as funções que a leem também mencionam PROMPTs longos.
#
# ⚠️ E A PIOR NÃO FOI NENHUMA DAS TRÊS: a 1ª versão IMPRIMIU o valor do
# `GEMINI_API_KEY` na tela — num relatório cuja única razão de existir é ser
# copiado e colado pra outra pessoa ler. A regra do projeto é explícita:
# *"nunca colar tokens/segredos no chat"*.
#
#   python3 teste_diag_env.py
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import diag_env  # noqa: E402

ok = falhou = 0


def checa(desc, cond, extra=""):
    global ok, falhou
    if cond:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}" + (f"\n      {extra}" if extra else ""))


SEGREDO = "AIzaSyPALAVRASECRETAxxxxxxxxxxxxxxxxxxxxx"
COOKIE = "sessionid=abc123def456ghi789jkl"
tmp = Path(tempfile.mkdtemp(prefix="dgenv_"))
env = tmp / ".env"
env.write_text(
    "# comentário no topo\n"
    f"AUTO_RESP_DM_TMPL=Oiee! tá tudo aqui ó: {{site}} corre!\n"
    "# AUTO_RESP_IG_TMPLS=comentada|||nao conta\n"
    "MIN_VIEWS=5000\n"
    f"GEMINI_API_KEY={SEGREDO}\n"
    f"TIKTOK_COOKIES={COOKIE}\n"
    "VARIAVEL_QUE_NINGUEM_LE=xyz\n"
    "AUTO_RESP_MAX=200\n", encoding="utf-8")

saida = io.StringIO()
_stdout = sys.stdout
sys.stdout = saida
try:
    diag_env.main.__globals__["sys"].argv = ["diag_env.py", "--env", str(env), "--tudo"]
    diag_env.main()
finally:
    sys.stdout = _stdout
txt = saida.getvalue()

print("\n── ⚠️⚠️ NENHUM SEGREDO NA SAÍDA (ela vai pro chat) ──")
checa("a GEMINI_API_KEY não aparece", SEGREDO not in txt)
checa("o cookie do TikTok não aparece", COOKIE not in txt)
checa("nem um pedaço de 12 chars do segredo", SEGREDO[:12] not in txt)
checa("mas a chave é citada pelo NOME (senão não dá pra agir)",
      "GEMINI_API_KEY" in txt)
checa("mostra que há algo oculto, não some com a linha", "oculto" in txt)

print("\n── ⚠️ A LINHA QUE CAUSOU O DEFEITO DE HOJE ──")
# chave dentro de IfExp + banco só na linha seguinte: o formato que enganou
# minhas duas primeiras versões
i_sombra = txt.find("SOMBRA")
i_fantasma = txt.find("FANTASMA")
i_dm = txt.find("AUTO_RESP_DM_TMPL")
checa("AUTO_RESP_DM_TMPL é classificada", i_dm > 0)
checa("…como SOMBRA, não como fantasma",
      0 < i_sombra < i_dm and (i_fantasma < 0 or i_dm < i_fantasma),
      f"sombra={i_sombra} dm={i_dm} fantasma={i_fantasma}")
checa("diz o número da linha certa (2)", "linha   2" in txt or "linha 2" in txt)
checa("diz QUAL banco ela substitui", "_DM_" in txt)

print("\n── ⚠️ E NÃO PODE MANDAR COMENTAR A CHAVE DA API ──")
# diagnóstico que sugere quebrar a produção é pior que diagnóstico nenhum
_sugestoes = [l for l in txt.splitlines() if "sed -i" in l]
checa("há sugestão de conserto", len(_sugestoes) >= 1, str(_sugestoes))
checa("nenhuma sugestão mexe em segredo",
      not any("5s/" in s for s in _sugestoes),
      "linha 5 é a GEMINI_API_KEY: " + str(_sugestoes))
checa("a sugestão aponta a linha 2 (a sombra de verdade)",
      any("'2s/" in s for s in _sugestoes), str(_sugestoes))

print("\n── linha comentada não conta, linha morta conta ──")
checa("AUTO_RESP_IG_TMPLS comentada é ignorada",
      "AUTO_RESP_IG_TMPLS" not in txt)
checa("VARIAVEL_QUE_NINGUEM_LE aparece como fantasma",
      "VARIAVEL_QUE_NINGUEM_LE" in txt and i_fantasma > 0)

print("\n── ⚠️ CONFIGURAÇÃO NORMAL NÃO PODE VIRAR ALARME ──")
# MIN_VIEWS tem padrão int e é config legítima; marcá-la como sombra ensina a
# ignorar a saída, que é o jeito mais rápido de matar um diagnóstico
_ate_sombra = txt[i_sombra:i_fantasma if i_fantasma > 0 else len(txt)]
checa("MIN_VIEWS não está na lista de sombras", "MIN_VIEWS" not in _ate_sombra)
checa("AUTO_RESP_MAX não está na lista de sombras",
      "AUTO_RESP_MAX" not in _ate_sombra)

print("\n── nada disso pode quebrar ──")
vazio = Path(tempfile.mkdtemp(prefix="dgenv_v_"))
r = subprocess.run([sys.executable, str(BASE / "diag_env.py"),
                    "--env", str(vazio / "nao_existe.env")],
                   capture_output=True, text=True)
checa("sem .env sai com erro claro, sem traceback",
      "Traceback" not in r.stderr, r.stderr[-200:])

for d in (tmp, vazio):
    shutil.rmtree(d, ignore_errors=True)
print(f"\n{'='*64}\n   {ok} passou · {falhou} falhou\n{'='*64}")
raise SystemExit(1 if falhou else 0)
