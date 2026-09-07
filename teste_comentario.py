#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_comentario.py -- o 1º comentário sai do banco do Dre, e sai rodando?
#
# O DEFEITO QUE ISTO TRAVA (07/09/2026)
# ─────────────────────────────────────
# O Dre: *"após todo post ele posta 1 comentário igual, e eu tinha te dado 5
# comentários ou mais nas conversas passadas para colocar, e isso não mudou"*.
#
# ⚠️ E NÃO TINHA MUDADO MESMO. Em 02/09 eu escrevi o `comentarios.py` inteiro —
# as seis frases dele palavra por palavra, banco separado por formato, rotação
# com memória — e NUNCA troquei a chamada no `meta_uploader`. O
# `_montar_comentario` seguiu lendo a constante `_TMPL_IG`. Cinco dias de posts
# nas seis contas com a MESMA frase, e a frase ainda era a vetada ("corre pegar
# o seu"). Módulo escrito, testado, versionado e morto.
#
# ⚠️ POR ISSO METADE DESTE TESTE OLHA A FIAÇÃO, NÃO O BANCO. Testar só o
# `escolher()` teria passado 100% em 02/09, com o sistema publicando a frase
# velha o tempo todo. O teste tem que perguntar "o uploader CHAMA isso?", que é
# a pergunta que ninguém fez. É a terceira vez na semana que o defeito é esse
# (o `_so_musica` sem chamador, as trilhas na pasta que nada lia, e agora isto).
#
#   python3 teste_comentario.py
import ast
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import comentarios                                     # noqa: E402

# memória de mentira: o teste não pode sujar a rotação de produção
comentarios.MEMORIA = Path(tempfile.gettempdir()) / "teste_coment_memoria.json"
try:
    comentarios.MEMORIA.unlink()
except Exception:
    pass

ok = falhou = 0


def checa(desc, cond, extra=""):
    global ok, falhou
    if cond:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}" + (f"\n      {extra}" if extra else ""))


# ⚠️ AS CONSTRUÇÕES QUE O DRE VETOU, em 21/08 ("corre ver isso") e que eu
# repeti sem perceber no `_TMPL_IG` ("corre pegar o seu"). Nenhuma frase que vá
# ao ar pode conter isso — nem o banco, nem a rede de segurança.
VETADAS = ("corre ver", "corre pegar", "corre garantir")

print("\n── o banco é o do Dre, e nenhuma frase vetada passa ──")
todas = (comentarios._IG_REEL + comentarios._IG_CARROSSEL
         + comentarios._IG_LISTA + comentarios._FB)
checa(f"banco de Reel tem 6 frases (ele mandou 6)", len(comentarios._IG_REEL) == 6,
      f"tem {len(comentarios._IG_REEL)}")
for v in VETADAS:
    achou = [f for f in todas if v in f.lower()]
    checa(f"nenhuma frase do banco diz '{v}'", not achou, str(achou)[:90])

print("\n── rotação: não repete enquanto houver alternativa ──")
saidas = [comentarios.escolher("instagram", formato="reel", conta="@topshoptech_")
          for _ in range(6)]
checa("6 chamadas, nenhuma vazia", all(saidas), str(saidas)[:80])
repetiu_seguida = any(saidas[i] == saidas[i + 1] for i in range(len(saidas) - 1))
checa("nunca repete a frase imediatamente anterior", not repetiu_seguida)
checa("usou pelo menos 4 frases diferentes em 6 posts", len(set(saidas)) >= 4,
      f"usou {len(set(saidas))}")

print("\n── carrossel NÃO herda o banco de Reel ──")
# num carrossel de "3 erros" não existe "um desses" pra comprar
carr = set(comentarios._IG_CARROSSEL)
checa("banco do carrossel é diferente do de Reel",
      carr != set(comentarios._IG_REEL))
vaza = [f for f in carr if "comprar um" in f or "já tem um desses" in f]
checa("nenhuma frase de carrossel fala de comprar um produto", not vaza,
      str(vaza)[:90])

print("\n── frase com {link} não sai sem link ──")
fb_sem = [comentarios.escolher("facebook", formato="reel", conta="@x", link="")
          for _ in range(8)]
checa("no Facebook sem link, nunca sai '{link}' cru",
      all("{link}" not in (f or "") for f in fb_sem), str(fb_sem)[:90])
com = comentarios.escolher("facebook", formato="reel", conta="@y",
                           link="https://s.shopee.com.br/abc")
checa("com link, a frase do FB carrega o link",
      "shopee.com.br/abc" in (com or "") or com == "", com)

print("\n── ⚠️ A FIAÇÃO: o meta_uploader realmente chama o módulo? ──")
# Isto é o que faltou em 02/09. Não importo o meta_uploader (ele puxa requests
# e token da Meta); leio a árvore, que é suficiente pra responder a pergunta.
_arv = ast.parse((BASE / "meta_uploader.py").read_text("utf-8"))
_fn = next((n for n in ast.walk(_arv)
            if isinstance(n, ast.FunctionDef) and n.name == "_montar_comentario"), None)
checa("_montar_comentario existe", _fn is not None)
if _fn:
    corpo = ast.dump(_fn)
    checa("ele importa `comentarios`", "'comentarios'" in corpo)
    checa("ele chama `escolher`", "escolher" in corpo)
    checa("ele aceita `formato`", any(a.arg == "formato" for a in _fn.args.args))

# o carrossel precisa passar formato="carrossel" — senão herda o banco de Reel
_chamadas = [n for n in ast.walk(_arv)
             if isinstance(n, ast.Call)
             and getattr(n.func, "id", "") == "_montar_comentario"]
checa("as 3 chamadas do uploader continuam lá", len(_chamadas) == 3,
      f"achei {len(_chamadas)}")
_carr = [c for c in _chamadas
         if any(k.arg == "formato" and getattr(k.value, "value", "") == "carrossel"
                for k in c.keywords)]
checa("exatamente 1 chamada passa formato='carrossel'", len(_carr) == 1,
      f"achei {len(_carr)}")

print("\n── a rede de segurança não pode ressuscitar a frase vetada ──")
_src = (BASE / "meta_uploader.py").read_text("utf-8")
_tmpl = [n for n in ast.walk(_arv)
         if isinstance(n, ast.Assign)
         and any(getattr(t, "id", "").startswith("_TMPL_") for t in n.targets)]
_textos = " ".join(ast.literal_eval(ast.unparse(n.value)) if isinstance(n.value, ast.Constant)
                   else ast.unparse(n.value) for n in _tmpl).lower()
for v in VETADAS:
    checa(f"a reserva do uploader não diz '{v}'", v not in _textos)

print(f"\n{'='*62}\n   {ok} passou · {falhou} falhou\n{'='*62}")
raise SystemExit(1 if falhou else 0)
