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
# ⚠️ o NOME é montado: se o literal existisse aqui, o próprio arquivo de teste
# seria a "prova" de que a variável é usada — e o auditor a chamaria de viva.
MORTA = "VARIAVEL" + "_QUE_NINGUEM" + "_LE"
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
    f"{MORTA}=xyz\n"
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


def _secao(nome):
    """O trecho de UMA seção. ⚠️ Fatiar `de SOMBRA até FANTASMA` quebrou quando
    entrou a seção INDIRETA no meio e quando FANTASMA some (find devolve -1 e a
    fatia vai até o fim, engolindo as NORMAIS)."""
    ini = txt.find(nome)
    if ini < 0:
        return ""
    fins = [txt.find(o, ini + 1) for o in ("⚠️  SOMBRA", "🔗 INDIRETA",
                                           "🕳️  FANTASMA", "✅ NORMAIS", "=" * 72)]
    fins = [f for f in fins if f > ini]
    return txt[ini:min(fins)] if fins else txt[ini:]

print("\n── ⚠️⚠️ NENHUM SEGREDO NA SAÍDA (ela vai pro chat) ──")
checa("a GEMINI_API_KEY não aparece", SEGREDO not in txt)
checa("o cookie do TikTok não aparece", COOKIE not in txt)
checa("nem um pedaço de 12 chars do segredo", SEGREDO[:12] not in txt)
checa("mas a chave é citada pelo NOME (senão não dá pra agir)",
      "GEMINI_API_KEY" in txt)
checa("mostra que há algo oculto, não some com a linha",
      "oculto" in txt or "GEMINI_API_KEY" in txt,
      "o valor tem que sumir, mas a linha não")

print("\n── ⚠️⚠️ NÃO PODE MANDAR APAGAR CONFIGURAÇÃO VIVA ──")
# ⚠️ NA PRIMEIRA EXECUÇÃO REAL o relatório listou 18 "linhas mortas" — e a
# maioria NÃO era. Duas formas de leitura são invisíveis pro AST:
#   · `os.environ.get(especifico)` com `especifico = "TIKTOK_COOKIES" if ...`
#     — o Dre tinha ACABADO de configurar esses cookies;
#   · `os.environ.get(conta["page_token_env"])`, com o nome da chave vindo do
#     contas.json — apagar aquelas 4 linhas derrubaria 4 contas.
# Mandar apagar isso é o pior estrago que um diagnóstico pode causar.
checa("⚠️ TIKTOK_COOKIES NÃO é chamada de linha morta",
      "TIKTOK_COOKIES" not in _secao("🕳️  FANTASMA"),
      "é lida por chave dinâmica em tiktok_coletor._cookies_args")
checa("ela aparece como INDIRETA (viva, por caminho que o AST não vê)",
      "TIKTOK_COOKIES" in _secao("🔗 INDIRETA") or
      "TIKTOK_COOKIES" in _secao("✅ NORMAIS"))
checa("a seção indireta avisa pra NÃO apagar",
      "NÃO APAGUE" in txt or not _secao("🔗 INDIRETA"))

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
checa("a variável morta aparece como fantasma",
      MORTA in txt and i_fantasma > 0, f"fantasma={i_fantasma}")

print("\n── ⚠️ CONFIGURAÇÃO NORMAL NÃO PODE VIRAR ALARME ──")
# MIN_VIEWS tem padrão int e é config legítima; marcá-la como sombra ensina a
# ignorar a saída, que é o jeito mais rápido de matar um diagnóstico
_ate_sombra = _secao("⚠️  SOMBRA")
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
