#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""teste_resposta_guardada.py -- a SEGUNDA intenção sob contrato.

A pergunta que este arquivo existe para responder não é "a resposta funciona".
É:

    ⚠️ o desenho da ESCOPO serve para uma ação que NÃO é `source.disable`?

Contrato que só serve ao caso que o inspirou não é infraestrutura — é um `if`
com YAML. Este caso é diferente em tudo: roda dezenas de vezes por dia, toca
gente de verdade, o estrago é spam (e conta restringida) em vez de dado
perdido, e a evidência é memória local em vez de consulta externa.
"""
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

OK = 0
FALHAS = []


def vale(cond, msg):
    global OK
    if cond:
        OK += 1
    else:
        FALHAS.append(msg)
        print(f"   ❌ {msg}")


def secao(t):
    print(f"\n── {t} " + "─" * max(0, 62 - len(t)))


print("\n💬 resposta a comentário sob contrato\n")
tmp = Path(tempfile.mkdtemp(prefix="resp_guard_"))

# ── 1 · memória ilegível ≠ memória vazia ──────────────────────────────────
secao("1 · 🔥 memória ilegível ≠ ninguém foi respondido")

os.environ["ESCOPO_ATIVO"] = "0"
import auto_resposta as A                                          # noqa: E402

A.RESPONDIDOS = tmp / "respondidos.json"
A.STORE_DIR = tmp

# arquivo inexistente: vazio LEGÍTIMO
vale(A._carregar_respondidos() == {}, "sem arquivo, memória vazia é legítima")
vale(A._PROCEDENCIA_MEMORIA["estado"] == "OK",
     "e a procedência diz que está tudo bem")
vale("primeira execução" in A._PROCEDENCIA_MEMORIA.get("nota", ""),
     "dizendo por quê")

# arquivo bom
A.RESPONDIDOS.write_text(json.dumps({"c1": time.time(), "c2": time.time()}),
                         encoding="utf-8")
d = A._carregar_respondidos()
vale(len(d) == 2, f"lê os dois comentários lembrados, veio {len(d)}")
vale(A._PROCEDENCIA_MEMORIA["estado"] == "OK", "procedência OK")
vale(str(A._PROCEDENCIA_MEMORIA.get("hash", "")).startswith("sha256:"),
     "com impressão digital do que foi lido")

# arquivo CORROMPIDO
A.RESPONDIDOS.write_text("{isso não é json", encoding="utf-8")
levantou = None
try:
    A._carregar_respondidos()
except A.MemoriaIlegivel as e:
    levantou = e
vale(levantou is not None,
     "⚠️ A ASSERÇÃO QUE IMPORTA: arquivo ilegível tem que LEVANTAR, não "
     "devolver {} — {} faria responder todo mundo dos últimos 7 dias de novo")
vale("todo mundo de novo" in str(levantou),
     f"e a mensagem diz o que estava em jogo: {str(levantou)[:80]!r}")
vale(A._PROCEDENCIA_MEMORIA["estado"] == "UNAVAILABLE",
     "a procedência registra a indisponibilidade")
vale(A._PROCEDENCIA_MEMORIA.get("erro"), "com o erro que impediu a leitura")

# ── 2 · a resposta sob contrato ───────────────────────────────────────────
secao("2 · a resposta a comentário passa por contrato")

try:
    import escopo                                                  # noqa: F401
    TEM_LIB = True
except ImportError:
    TEM_LIB = False

if not TEM_LIB:
    print("   ⚠️ biblioteca `escopo` não instalada — testes 2-4 pulados")
else:
    from escopo import Estado

    def montar(nome, memoria_ok=True, publica=True):
        for m in list(sys.modules):
            if m in {"escopo_jarvis"}:
                del sys.modules[m]
        os.environ["ESCOPO_ATIVO"] = "1"
        os.environ["ESCOPO_POLITICAS"] = str(BASE / "politicas")
        os.environ["ESCOPO_DADOS"] = str(tmp / nome)
        os.environ["FACEBOOK_PAGE_TOKEN"] = "token-de-teste"
        import escopo_jarvis as ej
        esc = ej._construir()
        # o Graph de mentira: devolve o id de volta, ou nada
        esc.registro.registrar(ej.VerificadorComentario(
            buscar=lambda rid, tok: ({"id": rid, "text": "oi"} if publica
                                     else {})))
        import importlib
        importlib.reload(A)
        A.guarda = ej.guarda
        A._PROCEDENCIA_MEMORIA = ({
            "estado": "OK", "fonte": "respondidos.json", "em": time.time(),
            "hash": "sha256:" + "cd" * 32, "lembrados": 12,
        } if memoria_ok else {
            "estado": "UNAVAILABLE", "fonte": "respondidos.json",
            "em": time.time(), "erro": "JSONDecodeError: corrompido",
        })
        A._post = lambda url, data: {"id": "resp_999"}
        return ej, esc

    def drenar(ej, esc, vezes=4):
        for _ in range(vezes):
            ej.processar_verificacoes()
            if esc.fila.caminho.exists():
                itens = json.loads(esc.fila.caminho.read_text(encoding="utf-8")
                                   or "[]")
                for it in itens:
                    it["proxima_em"] = 0
                esc.fila.caminho.write_text(json.dumps(itens), encoding="utf-8")
        return esc

    def ultima(esc):
        return [r for r in esc.livro.ler() if r.tipo == "acao"][-1]

    # memória boa + resposta publicada → ALLOW + VERIFIED
    ej, esc = montar("ok")
    A._responder_comentario(comentario="c_42", mensagem="oi!",
                            token="EAAG-token-secreto-de-verdade",
                            rede="instagram", conta="@topshoppet")
    drenar(ej, esc)
    a = ultima(esc)
    vale(a.corpo["veredito"]["decisao"] == "ALLOW",
         f"com memória boa, ALLOW — veio {a.corpo['veredito']['decisao']}")
    vale(esc.estado(a.hash) is Estado.VERIFICADO,
         f"e a resposta relida no Graph confirma → VERIFIED, deu "
         f"{esc.estado(a.hash).value}")
    vale(a.corpo["intencao"]["agente"] == "jarvis.resposta",
         "é outro agente, não o jarvis.ceo")

    # ⚠️ o token não pode estar em lugar nenhum do que foi para o disco
    tudo = esc.livro.caminho.read_text(encoding="utf-8")
    if esc.fila.caminho.exists():
        tudo += esc.fila.caminho.read_text(encoding="utf-8")
    vale("EAAG-token-secreto-de-verdade" not in tudo,
         "⚠️ TOKEN NO LIVRO É VAZAMENTO — e o livro existe para ser lido")
    vale("token-de-teste" not in tudo,
         "⚠️ nem o token do ambiente pode vazar pelo contexto da verificação")
    vale("«omitido" in tudo, "o campo aparece marcado como omitido")

    # ── 3 · memória indisponível → HOLD ───────────────────────────────────
    secao("3 · 🔥 memória ilegível segura a resposta")

    ej, esc = montar("sem_memoria", memoria_ok=False)
    A._responder_comentario(comentario="c_43", mensagem="oi!", token="t",
                            rede="instagram", conta="@x")
    a = ultima(esc)
    v = a.corpo["veredito"]
    vale(v["decisao"] == "HOLD",
         f"⚠️ sem memória confiável, HOLD — veio {v['decisao']}")
    vale(v["regra"] == "evidencia_indisponivel", "pela falta de evidência")
    vale("memoria_respondidos" in v["motivo"],
         f"nomeando a evidência que faltou: {v['motivo'][:80]!r}")

    # ── 4 · a API disse que publicou, mas não publicou ────────────────────
    secao("4 · 'a API devolveu id' ≠ 'a resposta está no post'")

    ej, esc = montar("fantasma", publica=False)
    A._responder_comentario(comentario="c_44", mensagem="oi!", token="t",
                            rede="instagram", conta="@x")
    drenar(ej, esc)
    a = ultima(esc)
    vale(esc.estado(a.hash) is Estado.FALHOU,
         f"⚠️ A API devolveu id e a releitura não achou nada → FAILED. "
         f"Deu {esc.estado(a.hash).value}")
    prova = [r for r in esc.livro.ler()
             if r.tipo == "verificacao"][-1].corpo["prova"]
    vale("publicado" in prova["motivo"],
         f"o motivo diz o que não bateu: {prova['motivo']!r}")

    integra, probs = esc.integro()
    vale(integra, f"a cadeia tem que fechar: {probs}")

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + "─" * 70)
if FALHAS:
    print(f"❌ {len(FALHAS)} falha(s) · {OK} asserção(ões) ok")
    sys.exit(1)
print(f"✅ {OK}/{OK} asserções")
