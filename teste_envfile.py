#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_envfile.py -- quem lê o .env tem que ler do mesmo jeito
#
# POR QUE ISTO EXISTE (10/09/2026)
# ────────────────────────────────
# O `comentarios.py` ANUNCIAVA override por `.env` desde 22/08 e nunca leu o
# arquivo. Ninguém notou por semanas, porque a falha é silenciosa por natureza:
# **variável que não foi lida é indistinguível de variável que não foi
# definida**. Quem mostrou foi um diagnóstico novo dizendo "AUTO_RESPONDER=0"
# enquanto o `auto_resposta`, na mesma máquina e no mesmo minuto, respondia com
# a DM ligada.
#
# ⚠️ E A MEDIÇÃO DEPOIS FOI PIOR QUE O DEFEITO: **40 cópias** de `_carregar_env`
# no projeto, em 26 formas diferentes. A boa notícia é que a divergência
# PERIGOSA não existe — todas respeitam a variável já exportada. A ruim é que
# uma delas (`hook_alana`) tinha aprendido algo que as outras 39 não sabiam.
#
#   python3 teste_envfile.py
import ast
import os
import shutil
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from shared.envfile import carregar_env

ok = falhou = 0


def checa(desc, cond, extra=""):
    global ok, falhou
    if cond:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}" + (f"\n      {extra}" if extra else ""))


tmp = Path(tempfile.mkdtemp(prefix="envf_"))
(tmp / ".env").write_text(
    "# comentário\n"
    "\n"
    "SIMPLES=valor\n"
    "export EXPORTADA=comexport\n"
    'ASPAS="entre aspas"\n'
    "ASPAS_SIMPLES='simples'\n"
    "COM_IGUAL=a=b=c\n"
    "   ESPACADA   =   com espaco   \n"
    "SEM_IGUAL\n"
    "JA_NO_AMBIENTE=do_arquivo\n"
    "ESTAVA_VAZIA=do_arquivo\n", encoding="utf-8")

os.environ["JA_NO_AMBIENTE"] = "do_ambiente"
os.environ["ESTAVA_VAZIA"] = ""
n = carregar_env(tmp)

print("\n── o básico da leitura ──")
checa("lê chave simples", os.environ.get("SIMPLES") == "valor")
checa("tira o 'export '", os.environ.get("EXPORTADA") == "comexport")
checa("tira aspas duplas", os.environ.get("ASPAS") == "entre aspas")
checa("tira aspas simples", os.environ.get("ASPAS_SIMPLES") == "simples")
checa("valor com '=' dentro sobrevive", os.environ.get("COM_IGUAL") == "a=b=c")
checa("espaço em volta some", os.environ.get("ESPACADA") == "com espaco")
checa("linha sem '=' é ignorada", "SEM_IGUAL" not in os.environ)
checa("devolve quantas entraram", n >= 7, str(n))

print("\n── ⚠️ QUEM GANHA: o ambiente ou o arquivo? ──")
# variável exportada na mão (ou pelo systemd) tem que ganhar, senão
# `AUTO_RESP_DM=0 python x.py` mentiria pra quem está testando
checa("variável já exportada NÃO é sobrescrita",
      os.environ.get("JA_NO_AMBIENTE") == "do_ambiente")
os.environ["JA_NO_AMBIENTE"] = "do_ambiente"
carregar_env(tmp, sobrescrever=True)
checa("…mas sobrescrever=True força", os.environ.get("JA_NO_AMBIENTE") == "do_arquivo")

print("\n── ⚠️⚠️ VARIÁVEL VAZIA CONTA COMO AUSENTE ──")
# A regra veio da melhor das 40 cópias (hook_alana), que a aprendeu do jeito
# caro: a GEMINI_API_KEY chegava VAZIA (não ausente), o `k not in os.environ`
# achava que estava tudo certo, e hook e legenda caíam no banco de reserva EM
# SILÊNCIO — a conta de beleza publicando curiosidade sobre organização da casa.
checa("variável vazia é preenchida pelo arquivo",
      os.environ.get("ESTAVA_VAZIA") == "do_arquivo")

print("\n── ⚠️ NADA AQUI PODE DERRUBAR UM IMPORT ──")
# metade do projeto chama isto na primeira linha do módulo
vazio = Path(tempfile.mkdtemp(prefix="envf_vazio_"))
checa("sem .env devolve 0, não explode", carregar_env(vazio) == 0)
ruim = Path(tempfile.mkdtemp(prefix="envf_ruim_"))
(ruim / ".env").write_bytes(b"\xff\xfe\x00BINARIO\x00")
try:
    r = carregar_env(ruim)
    checa(".env ilegível devolve 0, não explode", r == 0, str(r))
except Exception as e:
    checa(".env ilegível devolve 0, não explode", False, f"levantou {e!r}")

print("\n── ⚠️ OS TRÊS MIGRADOS USAM O COMPARTILHADO ──")
# consertar num lugar só conserta os três; enquanto forem cópias, não
for arq in ("comentarios.py", "auto_resposta.py", "tiktok_coletor.py"):
    s = (BASE / arq).read_text("utf-8")
    codigo = "\n".join(l for l in s.splitlines() if not l.lstrip().startswith("#"))
    checa(f"{arq} importa shared.envfile", "from shared.envfile import" in codigo)
    # ⚠️ e não pode ter sobrado a cópia antiga ao lado da importação nova
    checa(f"{arq} não tem mais a cópia própria",
          "os.environ[k] = v" not in codigo,
          "o corpo antigo do _carregar_env ainda está ali")

print("\n── 📌 O TAMANHO DA DÍVIDA QUE SOBRA (medido, não estimado) ──")
# O projeto já registrou esta dívida três vezes, em três arquivos diferentes.
# O número existe pra a decisão de migrar ser tomada com ele na mesa.
_copias = []
for p in sorted(BASE.glob("*.py")):
    try:
        arv = ast.parse(p.read_text("utf-8", errors="ignore"))
    except Exception:
        continue
    for n_ in ast.walk(arv):
        if not (isinstance(n_, ast.FunctionDef) and n_.name == "_carregar_env"):
            continue
        # ⚠️ O QUE DISTINGUE CÓPIA DE DELEGAÇÃO é ESCREVER no os.environ.
        # Minha primeira versão procurava a string "envfile" no dump do corpo e
        # contou os três migrados como cópias — o corpo deles é
        # `return _carregar_env_shared(BASE_DIR)`, que não contém essa palavra.
        # Contador errado num teste de dívida é pior que não ter contador:
        # ele reprova o conserto que acabou de ser feito.
        escreve = any(
            isinstance(alvo, ast.Subscript)
            and getattr(getattr(alvo.value, "value", None), "id", "") == "os"
            for s in ast.walk(n_) if isinstance(s, ast.Assign)
            for alvo in s.targets)
        if escreve:
            _copias.append(p.name)
print(f"   ainda com cópia própria: {len(_copias)} arquivo(s)")
# ⚠️ NÃO FALHA POR ISSO. Reprovar aqui obrigaria a migrar 37 arquivos de
# produção de uma vez, no meio de outra tarefa — que é exatamente o motivo
# registrado no `diag_match` pra não ter feito antes. O teste CONTA; quem
# decide é o Dre.
checa("os três pedidos foram migrados",
      not {"comentarios.py", "auto_resposta.py", "tiktok_coletor.py"} & set(_copias),
      str(sorted({"comentarios.py", "auto_resposta.py",
                  "tiktok_coletor.py"} & set(_copias))))

for d in (tmp, vazio, ruim):
    shutil.rmtree(d, ignore_errors=True)
print(f"\n{'='*64}\n   {ok} passou · {falhou} falhou\n{'='*64}")
raise SystemExit(1 if falhou else 0)
