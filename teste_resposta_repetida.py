#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_resposta_repetida.py -- 6 respostas, 4 frases, uma delas 3 vezes
#
# POR QUE ISTO EXISTE (09/09/2026)
# ────────────────────────────────
# O Dre mandou os prints de um Reel do @topshoppet_ que explodiu, com a fila de
# "Eu quero" nos comentários e o bot respondendo:
#
#   ennycosta__      → Bio 🔗 dá uma olhada e me fala
#   isa__debortoli   → Achei também! Link na bio pra você ver o preço 👀
#   melissaemari2021 → Bio 🔗 dá uma olhada e me fala          ← 2ª vez
#   brsarah7         → O link tá na bio 🔗 depois me conta o que achou!
#   bonitobeloved    → Bio 🔗 dá uma olhada e me fala          ← 3ª vez
#   gabryelle_00     → Na bio tem ele e uns parecidos 👀
#
# *"esse burro respondendo quase tudo igual, parecendo um robozinho, o povo até
# desanima de comprar, ou para de comentar"*.
#
# ⚠️ A CAUSA ERA `random.choice` PURO — e a regra que impede isso já existia no
# arquivo ao lado (`comentarios.py`, desde 22/08) e nunca chegou aqui.
#
# ⚠️ E O TESTE TEM QUE ATRAVESSAR RODADAS DE CRON. O `auto_resposta` roda a cada
# poucos minutos; os comentários daquele Reel chegaram ao longo de 22 HORAS.
# Memória que só vive em RAM durante uma rodada não impede repetição nenhuma no
# caso real — então aqui o disco é exercitado de propósito.
#
#   python3 teste_resposta_repetida.py
import ast
import importlib
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
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


# ── a regra, sozinha ─────────────────────────────────────────────────────────
from shared.rotacao import escolher_sem_repetir as rodar

print("\n── a regra: não repete enquanto houver alternativa ──")
banco8 = [f"f{i}" for i in range(8)]
saidas, rec = [], []
for _ in range(4):
    esc, rec = rodar(banco8, rec)
    saidas.append(esc)
checa("4 sorteios num banco de 8 → 4 frases distintas", len(set(saidas)) == 4,
      str(saidas))
checa("a memória guarda METADE do banco (4 de 8)", len(rec) == 4, str(rec))

print("\n   ── ⚠️ lembrar de TUDO é o mesmo que não lembrar de nada ──")
# se o teto fosse len-1 ou len, `novas` esvaziaria e viraria sorteio puro
_, rec3 = rodar(["a", "b", "c"], [])
checa("banco de 3 lembra só 1 (metade, arredondando pra baixo)",
      len(rec3) == 1, str(rec3))
_, rec2 = rodar(["a", "b"], [])
checa("banco de 2 lembra 1 (o piso é 1, nunca 0)", len(rec2) == 1, str(rec2))
checa("banco de 1 não quebra", rodar(["a"], ["a"])[0] == "a")
checa("banco vazio devolve string vazia", rodar([], [])[0] == "")
checa("None no lugar do banco não quebra", rodar(None, None)[0] == "")

print("\n   ── ⚠️ a escolhida não pode entrar DUAS vezes na memória ──")
# ([escolhida] + recentes) sem filtrar duplicaria quando o `or candidatas`
# caísse numa frase que já estava lá, encurtando a janela real de proteção
_, rr = rodar(["a"], ["a"], lembrar=4)
checa("frase repetida não duplica na memória", rr.count("a") == 1, str(rr))

# ── a fiação, com disco de verdade ───────────────────────────────────────────
print("\n── ⚠️ O CASO REAL: um post, muitos comentários, VÁRIAS rodadas de cron ──")
tmp = Path(tempfile.mkdtemp(prefix="resp_"))
os.environ["AUTO_RESPONDER"] = "0"          # não deixa nada tentar a rede
ar = importlib.import_module("auto_resposta")
ar.FRASES_POST = tmp / "frases_por_post.json"

POST = "17900000000000000"                  # o Reel do pet
respostas = []
for rodada in range(3):                     # 3 passadas do cron
    mem = ar._carregar_frases_post()        # ⚠️ relê do DISCO, como o cron faz
    for _ in range(3):                      # 3 comentários novos por passada
        respostas.append(ar._escolhe_ig_tmpl(False, POST, mem))
    ar._salvar_frases_post(mem)

cont = Counter(respostas)
checa("o arquivo de memória foi criado", ar.FRASES_POST.exists())

# ⚠️ A GARANTIA NÃO É "TODAS DISTINTAS", E ISTO IMPORTA. A memória guarda
# METADE do banco de propósito: se guardasse tudo, a rotação viraria uma
# permutação — nunca repete e é lida como robô do mesmo jeito, só que por
# regularidade em vez de repetição (o raciocínio está em shared/rotacao.py).
# Então o que se garante é uma JANELA: dentro de `memória + 1` respostas
# consecutivas, nenhuma frase aparece duas vezes.
JANELA = len(ar._banco_ig(False)) // 2 + 1
_colisao = [(i, j) for i in range(len(respostas))
            for j in range(i + 1, min(i + JANELA, len(respostas)))
            if respostas[i] == respostas[j]]
checa(f"⚠️ nenhuma frase repete dentro de {JANELA} respostas seguidas",
      not _colisao,
      f"colidiram nas posições {_colisao[:3]}")
checa("nunca repete a imediatamente anterior",
      not any(respostas[i] == respostas[i + 1] for i in range(len(respostas) - 1)))

# o número do print do Dre: 6 respostas, 4 frases, uma delas 3×. Com o conserto,
# 6 respostas seguidas têm que dar 6 frases (a janela é 5, mas em 6 sorteios
# sem reposição na janela o máximo que uma frase repete é 1 vez, nunca 3).
_seis = Counter(respostas[:6])
checa("nas 6 primeiras (o caso do print) nenhuma frase sai 3×",
      max(_seis.values()) < 3, str(_seis.most_common(2)))
checa("e saem pelo menos 5 frases diferentes (o print deu 4)",
      len(_seis) >= 5, f"{len(_seis)} distintas")

print("\n   ── ⚠️ a memória é POR POST, não global ──")
# repetir entre posts diferentes ninguém nota (cada um lê um post); repetir
# DENTRO do post é o que denuncia. Se a memória fosse global, um post viral
# esgotaria o banco e o post seguinte cairia em sorteio puro.
mem = ar._carregar_frases_post()
outro = ar._escolhe_ig_tmpl(False, "17911111111111111", mem)
checa("post novo escolhe do banco inteiro (não herda o esgotado)",
      bool(outro))
checa("cada post tem sua própria chave",
      len([k for k in mem if k.startswith(POST)]) == 1 and len(mem) == 2,
      str(list(mem)))

print("\n── ⚠️ SEM DM, NENHUMA RESPOSTA PODE PROMETER DIRECT ──")
# prometer o que não chega é pior que não responder: a pessoa espera, não
# recebe, e aprende que a conta mente
banco_sem_dm = ar._banco_ig(False)
checa("o banco sem-DM não cita direct/dm",
      not any(ar._menciona_dm(t) for t in banco_sem_dm), str(banco_sem_dm)[:100])
checa("o banco COM dm é outro, não o mesmo filtrado",
      set(ar._banco_ig(True)) != set(banco_sem_dm))

print("\n── ⚠️ O GRUPO DO WHATSAPP ENTRA NA ROTAÇÃO (mas não em todas) ──")
# R$300 de tráfego pago = 1 membro no grupo. Este Reel tinha dezenas de mãos
# levantadas de graça e NENHUMA resposta convidava pro grupo.
com_grupo = [t for t in banco_sem_dm if "grupo" in t.lower() or "zap" in t.lower()]
checa("existe frase que convida pro grupo", len(com_grupo) >= 1, str(com_grupo))
checa("mas não é a maioria (senão vira panfleto)",
      len(com_grupo) <= len(banco_sem_dm) / 3,
      f"{len(com_grupo)} de {len(banco_sem_dm)}")
# ⚠️ no IG link em comentário NÃO clica — a frase do grupo tem que mandar pra
# bio, não colar um chat.whatsapp.com que ninguém consegue tocar
checa("⚠️ nenhuma cola chat.whatsapp.com (no IG não clica)",
      not any("chat.whatsapp" in t for t in banco_sem_dm))
checa("as frases do grupo mandam pra bio",
      all("bio" in t.lower() for t in com_grupo), str(com_grupo))

print("\n── ⚠️ O POST DE 1000 COMENTÁRIOS (o teto real não era o AUTO_RESP_MAX) ──")
# O Dre: *"40 tá pouquíssimo, quase nada, tem post com +1000 comentários"*.
# Ele está certo de que 40 é pouco — mas 40 não era o que travava. O `limit:50`
# sem seguir `paging.next` fazia os outros 950 serem INALCANÇÁVEIS, e subir o
# AUTO_RESP_MAX pra 400 não mudaria nada.
_paginas_pedidas = []


def _api_falsa(url, params):
    """1000 comentários em páginas de 50, como o Graph devolve."""
    _paginas_pedidas.append(params.get("after"))
    ini = int(params.get("after") or 0)
    fim = min(ini + 50, 1000)
    d = {"data": [{"id": f"c{i}", "text": "eu quero"} for i in range(ini, fim)]}
    if fim < 1000:
        d["paging"] = {"next": "http://x", "cursors": {"after": str(fim)}}
    return d


_get_real = ar._get
ar._get = _api_falsa
try:
    todos = ar._get_paginas("http://x", {"limit": 50}, 20)
    checa("1000 comentários chegam inteiros (não 50)", len(todos) == 1000,
          f"vieram {len(todos)}")
    checa("pediu 20 páginas", len(_paginas_pedidas) == 20, str(len(_paginas_pedidas)))
    checa("a 1ª página vai sem cursor", _paginas_pedidas[0] is None)

    print("\n   ── ⚠️ e o teto de páginas segura, senão é chamada infinita ──")
    _paginas_pedidas.clear()
    parcial = ar._get_paginas("http://x", {"limit": 50}, 3)
    checa("com teto 3, para em 150", len(parcial) == 150, f"{len(parcial)}")

    # cursor que se repete: a API às vezes devolve o mesmo `after`
    def _api_travada(url, params):
        return {"data": [{"id": "c1"}],
                "paging": {"next": "http://x", "cursors": {"after": "MESMO"}}}
    ar._get = _api_travada
    checa("cursor repetido não vira laço infinito",
          len(ar._get_paginas("http://x", {}, 50)) == 2)

    # ⚠️ o lado que NÃO pode disparar: resposta sem paging nenhum
    ar._get = lambda u, p: {"data": [{"id": "c1"}, {"id": "c2"}]}
    checa("post pequeno (sem paging) devolve os 2 e para",
          len(ar._get_paginas("http://x", {}, 20)) == 2)
    ar._get = lambda u, p: {}
    checa("resposta vazia não quebra", ar._get_paginas("http://x", {}, 20) == [])
finally:
    ar._get = _get_real

print("\n── ⚠️ O ORÇAMENTO É POR CONTA, NÃO O BOLO DAS SEIS ──")
# antes: `rest = max - total` com `break` ao zerar. A PRIMEIRA conta do
# contas.json podia comer tudo e as outras cinco ficavam sem resposta nenhuma —
# no dia em que um post explode, que é o dia em que mais importa.
_src_ar = (BASE / "auto_resposta.py").read_text("utf-8")
checa("existe teto por conta e teto global separados",
      "AUTO_RESP_MAX_TOTAL" in _src_ar and "teto_total" in _src_ar)
checa("o laço das contas não dá break ao esgotar a conta (usa continue)",
      "min(limites[\"max\"], teto_total - total)" in _src_ar)
checa("o padrão por conta subiu de 40", '"AUTO_RESP_MAX", "200"' in _src_ar)

print("\n── ⚠️ RAJADA DE 200 RESPOSTAS É ASSINATURA DE ROBÔ PRA META ──")
# as contas SÃO o negócio; um perfil limitado custa mais que 200 respostas
# atrasadas
checa("existe pausa entre respostas", "_respirar" in _src_ar)
checa("a pausa tem jitter (intervalo exato também é assinatura)",
      "random.uniform" in _src_ar)
checa("o dry-run não dorme", "if teste:\n        return" in _src_ar)
checa("a pausa é regulável por .env", "AUTO_RESP_PAUSA" in _src_ar)

print("\n── ⚠️ A REGRA MORA NUM LUGAR SÓ ──")
# foi o defeito da semana inteira: regra certa, documentada, num arquivo só.
_src_ar = (BASE / "auto_resposta.py").read_text("utf-8")
_src_cm = (BASE / "comentarios.py").read_text("utf-8")
checa("auto_resposta importa shared.rotacao", "from shared.rotacao import" in _src_ar)
checa("comentarios importa shared.rotacao", "from shared.rotacao import" in _src_cm)
for arq, s in (("auto_resposta.py", _src_ar), ("comentarios.py", _src_cm)):
    codigo = "\n".join(l for l in s.splitlines() if not l.lstrip().startswith("#"))
    checa(f"{arq} não tem cópia própria da regra",
          "def escolher_sem_repetir" not in codigo)
checa("o coletor de frases grava de forma atômica (cron concorrente)",
      ".json.tmp" in _src_ar and "tmp.replace(" in _src_ar)
checa("o --teste não grava a memória no disco",
      "if not teste:" in _src_ar and "_salvar_frases_post(frases_post)" in _src_ar)

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{'='*66}\n   {ok} passou · {falhou} falhou\n{'='*66}")
raise SystemExit(1 if falhou else 0)
