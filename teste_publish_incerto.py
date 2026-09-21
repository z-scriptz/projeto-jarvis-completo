#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""teste_publish_incerto.py -- um POST que deu timeout não é um post que falhou.

⚠️ O DEFEITO QUE ISTO TRANCA. `_publicar_container` fazia:

    except Exception as e:
        return "", f"exceção publicando: {e}"

Um POST que dá timeout é o caso ambíguo clássico: **a Meta pode ter
processado.** O cliente só parou de esperar a resposta. Virava
`sucesso: False`, e o livro registrava falha sobre um post que podia estar
no ar, na frente do público de seis contas.

📌 E a regra que este arquivo aplica, vinda do `order.refunded_amount_matches`:
**afirmação sem caminho de falsificação não vale.** Cada estado abaixo tem um
caso que o vê acontecer — inclusive a armadilha do teste 6, que é onde um
conserto apressado erraria.

    python3 teste_publish_incerto.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import meta_uploader as M                                      # noqa: E402

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


class Resp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


class HTTPFalso:
    """A Meta de mentira. `publish` é o que o POST faz; `listas` é a fila de
    respostas do GET /media, uma por chamada."""

    def __init__(self, publish, listas):
        self.publish = publish
        self.listas = list(listas)
        self.posts = 0

    def get(self, url, **k):
        if not self.listas:
            raise ConnectionError("fim do roteiro de GET")
        item = self.listas.pop(0)
        if isinstance(item, Exception):
            raise item
        return Resp({"data": [{"id": i} for i in item]})

    def post(self, url, **k):
        self.posts += 1
        if isinstance(self.publish, Exception):
            raise self.publish
        return Resp(self.publish)


def montar(publish, listas):
    M._HTTP = HTTPFalso(publish, listas)
    return M._HTTP


print("\n🔒 publish do Instagram — três saídas, não duas\n")
M.time.sleep = lambda *_: None          # o ensaio não espera 30 segundos
_sleep_original = None

# ── 1 · caminho feliz ─────────────────────────────────────────────────────
secao("1 · a Meta respondeu com o id")

montar({"id": "17999"}, [["a", "b"]])
mid, err, incerto = M._publicar_container("IG1", "cont1", "tok")
vale((mid, err, incerto) == ("17999", "", False),
     f"publicou: {(mid, err, incerto)}")

# ── 2 · recusa de verdade ─────────────────────────────────────────────────
secao("2 · a Meta respondeu e disse NÃO")

montar({"error": {"message": "media type not supported"}}, [["a"]])
mid, err, incerto = M._publicar_container("IG1", "cont1", "tok")
vale(not mid and not incerto and "not supported" in err,
     f"⚠️ resposta COM motivo é negativa de verdade, não incerteza. "
     f"incerto={incerto}, err={err[:40]}")

# ── 3 · 🔥 a resposta se perdeu e o post ESTAVA no ar ─────────────────────
secao("3 · 🔥 timeout no publish, e apareceu id novo")

montar(ConnectionError("timeout lendo a resposta"),
       [["a", "b"],            # a foto de antes
        ["a", "b"],            # ainda não apareceu
        ["z9", "a", "b"]])     # nasceu
mid, err, incerto = M._publicar_container("IG1", "cont1", "tok")
vale(mid == "z9" and not incerto,
     f"🔥 O POST ESTAVA NO AR. A versão antiga devolveria `sucesso: False` e\n"
     f"      o livro registraria falha sobre um carrossel publicado na frente\n"
     f"      do público. Veio {(mid, incerto)}")

# ── 4 · a resposta se perdeu e de fato não publicou ───────────────────────
secao("4 · timeout, as duas leituras vieram, nada nasceu")

montar(ConnectionError("timeout"),
       [["a", "b"]] + [["a", "b"]] * 6)
mid, err, incerto = M._publicar_container("IG1", "cont1", "tok")
vale(not mid and not incerto and "não chegou" in err,
     f"⚠️ SÓ AQUI se pode afirmar que não publicou: havia linha de base, a\n"
     f"      releitura funcionou, e nenhum id novo apareceu. "
     f"incerto={incerto}")

# ── 5 · 🔥 sem linha de base não se afirma nada ───────────────────────────
secao("5 · 🔥 a foto de ANTES falhou")

montar(ConnectionError("timeout"), [ConnectionError("GET caiu")])
mid, err, incerto = M._publicar_container("IG1", "cont1", "tok")
vale(not mid and incerto and "NÃO SE SABE" in err,
     f"🔥 Sem foto de antes não há como resolver, e a resposta honesta é\n"
     f"      INCERTO. Chamar de recusa é o defeito original de volta.\n"
     f"      Veio incerto={incerto}, err={err[:50]}")

# ── 6 · 🔥 A ARMADILHA: não devolver post de ontem como se fosse deste ────
secao("6 · 🔥 sem linha de base, um id existente NÃO é o nosso")

montar(ConnectionError("timeout"),
       [ConnectionError("GET de antes caiu"),
        ["post_de_ontem", "outro_de_ontem"],
        ["post_de_ontem", "outro_de_ontem"]])
mid, err, incerto = M._publicar_container("IG1", "cont1", "tok")
vale(mid == "" and incerto,
     f"🔥 A CONTA TEM POSTS, e nenhum deles é prova desta ação. Um conserto\n"
     f"      apressado leria a conta, acharia `post_de_ontem` e devolveria\n"
     f"      como `media_id` — e aí o verificador iria ao Graph, confirmaria\n"
     f"      que o post EXISTE, e concluiria que esta ação o criou.\n"
     f"      Seria pior que a dúvida: VERIFIED em cima de nada.\n"
     f"      Veio {(mid, incerto)}")

# ── 7 · o POST é feito UMA vez ────────────────────────────────────────────
secao("7 · resolver a dúvida não republica")

h = montar(ConnectionError("timeout"), [["a"]] + [["a"]] * 6)
M._publicar_container("IG1", "cont1", "tok")
vale(h.posts == 1,
     f"⚠️ a resolução é feita com GET, nunca repetindo o POST — repetir para\n"
     f"      descobrir se funcionou é como se publica duas vezes. "
     f"POSTs: {h.posts}")

# ── 8 · o `incerto` chega ao chamador ─────────────────────────────────────
secao("8 · e sobe até quem decide republicar")

import inspect                                                 # noqa: E402
fonte = inspect.getsource(M.postar_instagram_carrossel)
vale('"incerto": incerto' in fonte,
     "📌 `postar_instagram_carrossel` devolve `incerto` no dicionário — sem\n"
     "      isso o conserto morre aqui dentro e o agendador decide no escuro")

import carrossel_agendador as CA                               # noqa: E402
fonte_ag = inspect.getsource(CA.publicar_um)
vale('"motivo": "incerto"' in fonte_ag,
     "e o agendador separa `incerto` de `recusado`, em vez de achatar os dois")

M._HTTP = None
print("\n" + "─" * 70)
if FALHAS:
    print(f"❌ {len(FALHAS)} falha(s) de {OK + len(FALHAS)}\n")
    sys.exit(1)
print(f"✅ {OK}/{OK} asserções\n")
print("📌 As três saídas, e por que nenhuma pode virar outra:\n")
print("   publicou     id na mão — o verificador tem o que levar ao Graph")
print("   recusado     a Meta respondeu com motivo. O post não existe.")
print("   INCERTO      a resposta se perdeu e a releitura não resolveu.")
print("                Republicar aqui é o post duplicado; registrar falha")
print("                aqui é o livro mentindo. As duas coisas precisam de")
print("                alguém olhando.\n")
