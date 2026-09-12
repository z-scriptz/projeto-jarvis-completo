#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_nomear_produto.py -- com a DM barrada, o comentário tem que NOMEAR
#
# POR QUE ISTO EXISTE (12/09/2026)
# ────────────────────────────────
# O `diag_dm_permissao` fechou a questão da DM nas seis contas:
#
#   (#3) Application does not have the capability to make this API call.
#
# É capability do APP, não escopo do token — resolve no App Dashboard da Meta,
# em prazo que não é nosso. Enquanto isso, quem comenta "EU QUERO" **não recebe
# nada**. O Dre: *"quando a pessoa escreve 'EU QUERO' e não recebe o link, ela
# esquece o post."*
#
# 📌 Comentário do Instagram não deixa link clicável. Então o que dá pra
# melhorar não é o link — é a ESPECIFICIDADE:
#
#   "o link tá na bio"              → ela tem que lembrar o que viu
#   "é o Papete Vizzano, tá na bio" → ela procura UMA coisa
#
# Quem comenta já decidiu. Nomear é o que não devolve trabalho pra ela.
#
# ⚠️ E A FRASE SÓ VALE SE O NOME VIER. Ela depende de juntar dois ledgers, e se
# a junção não fechar a frase não pode sair prometendo. Foi por isso que o
# `--diag-produto` nasceu ANTES de eu confiar nela — o erro do carrossel (dois
# dias de capa num formato com 0/28 de link) foi exatamente confiar primeiro.
#
#   python3 teste_nomear_produto.py
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
sys.argv = ["teste"]
import auto_resposta as A  # noqa: E402

ok = falhou = 0


def checa(desc, cond, extra=""):
    global ok, falhou
    if cond:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}" + (f"\n      {extra}" if extra else ""))


print("\n── ⚠️ A JUNÇÃO É POR item_id, NÃO POR STRING DE LINK ──")
# o mesmo produto sai com sub_id diferente por plataforma; casar a URL inteira
# falharia calado — e falhar calado aqui significa nomear o produto ERRADO
checa("extrai o item_id da URL da Shopee",
      A._item_id("https://shopee.com.br/coisa-i.123456.7890123") == "123456.7890123")
checa("⚠️ o MESMO produto com sub_id diferente dá o MESMO item_id",
      A._item_id("https://shopee.com.br/x-i.9.8?sub_id=reels_a")
      == A._item_id("https://shopee.com.br/x-i.9.8?sub_id=carrossel_b") == "9.8",
      "casar por string separaria o mesmo produto em dois")
checa("link que não é da Shopee devolve vazio (não inventa)",
      A._item_id("https://encurtador.x/abc") == "")
checa("URL vazia não quebra", A._item_id("") == "")
checa("None não quebra", A._item_id(None) == "")

print("\n── o nome sai do posts_ledger, não do publicados.jsonl ──")
A._PRODUTO_POR_ITEM = {"123456.7890123": "Papete Vizzano Chic e Confortável",
                       "9.8": "Bolsa Tiracolo"}
A._LINKS_POR_POST = {
    "UMPROD": "https://shopee.com.br/a-i.123456.7890123",
    "DOISPROD": ["https://shopee.com.br/a-i.123456.7890123?sub_id=x",
                 "https://shopee.com.br/b-i.9.8"],
    "SEMNOME": "https://shopee.com.br/z-i.000.111",     # não está na tabela
}
_p = lambda sc: A._produtos_do_post(f"https://instagram.com/reel/{sc}/")  # noqa: E731
checa("post de 1 produto devolve 1 nome",
      _p("UMPROD") == ["Papete Vizzano Chic e Confortável"])
checa("carrossel devolve os N nomes", len(_p("DOISPROD")) == 2, str(_p("DOISPROD")))
checa("⚠️ link sem nome na tabela devolve [] (não chuta)", _p("SEMNOME") == [])
checa("post fora do ledger devolve []", _p("NAOEXISTE") == [])

print("\n── ⚠️ SEM NOME, CAI NO BANCO DE SEMPRE (não promete o que não tem) ──")
# frase que promete o que não chega é o defeito que este arquivo já documenta
# duas vezes; a terceira não pode ser introduzida pelo conserto
checa("banco de produto vazio quando não há nome", A._banco_produto([]) == [])
_semnome = A._escolhe_ig_tmpl(False, "post1", {}, [])
checa("a escolha cai nas frases de bio", _semnome in A._banco_ig(False), _semnome)
checa("⚠️ e nenhuma frase de bio tem placeholder solto",
      all("{" not in f for f in A._banco_ig(False)))

print("\n── com nome, a frase NOMEIA ──")
_b = A._banco_produto(["Papete Vizzano Chic"])
checa("o banco de produto tem várias frases", len(_b) >= 4, str(len(_b)))
checa("⚠️ TODAS citam o produto",
      all("Papete Vizzano Chic" in f for f in _b),
      [f for f in _b if "Papete Vizzano Chic" not in f])
checa("⚠️ nenhuma sobrou com chave de formatação",
      all("{" not in f and "}" not in f for f in _b),
      [f for f in _b if "{" in f])
checa("nenhuma promete DM (a DM está barrada)",
      not any(A._menciona_dm(f) for f in _b))

print("\n   ── e no plural o número não repete o substantivo ──")
_bn = A._banco_produto(["a", "b", "c"])
# ⚠️ `n` já veio como "3 produtos" na 1ª versão e saiu "Tem 3 produtos
# achadinhos nesse post". O substantivo é da frase, não do placeholder.
checa("⚠️ nenhuma frase repete o substantivo",
      not any("produtos achadinhos" in f or "produtos produtos" in f
              or "achados achadinhos" in f for f in _bn), str(_bn))
checa("todas dizem quantos são", all("3" in f for f in _bn), str(_bn))
checa("⚠️ e NENHUMA nomeia um só (seria errar nos outros 2)",
      not any(f.startswith("É o a") or "Anota: a " in f for f in _bn), str(_bn))

print("\n── ⚠️ NOME GIGANTE VIRA COMENTÁRIO ILEGÍVEL ──")
_gigante = ("Conjunto Alfaiataria Super Elegante Feminino Blazer e Calça "
            "Social Cintura Alta Trabalho")
_bg = A._banco_produto([_gigante])
checa("o nome é cortado", all(len(f) < 120 for f in _bg),
      max(_bg, key=len) if _bg else "")
checa("…mas corta na palavra, não no meio dela",
      not any(f.split("💛")[0].rstrip().endswith(("Ele", "Femin", "Calç"))
              for f in _bg), str(_bg[:1]))
checa("e o começo do nome continua lá",
      all("Conjunto Alfaiataria" in f for f in _bg))

print("\n── a memória de rotação separa os bancos ──")
# ⚠️ chave misturada faz o "já disse isto neste post" olhar pra frases de outro
# conjunto e não significar nada
_mem = {}
A._escolhe_ig_tmpl(False, "postX", _mem, ["Papete Vizzano Chic"])
A._escolhe_ig_tmpl(False, "postX", _mem, [])
checa("banco de produto e banco de bio têm chaves distintas",
      "postX|prod" in _mem and "postX|bio" in _mem, str(sorted(_mem)))

print("\n   ── e não repete a frase no MESMO post ──")
_mem2, _vistas = {}, []
for _ in range(3):
    _vistas.append(A._escolhe_ig_tmpl(False, "postY", _mem2, ["Papete Vizzano"]))
checa("3 respostas seguidas, 3 frases diferentes",
      len(set(_vistas)) == 3, str(_vistas))

print("\n── o desligador existe ──")
import os  # noqa: E402
os.environ["AUTO_RESP_NOMEAR"] = "0"
try:
    checa("AUTO_RESP_NOMEAR=0 volta ao comportamento antigo",
          A._banco_produto(["Papete Vizzano"]) == [])
finally:
    os.environ.pop("AUTO_RESP_NOMEAR", None)
checa("sem a variável, o padrão é NOMEAR", bool(A._banco_produto(["Papete"])))

print("\n── nada disso pode derrubar uma resposta ──")
checa("ledger de produtos ilegível não quebra",
      isinstance(A._carregar_produtos(), dict))
os.environ["AUTO_RESP_IG_TMPLS_PRODUTO"] = "frase com {chave_que_nao_existe}"
try:
    checa("⚠️ placeholder errado no .env não derruba — cai no banco de sempre",
          A._escolhe_ig_tmpl(False, "p", {}, ["X"]) in A._banco_ig(False))
finally:
    os.environ.pop("AUTO_RESP_IG_TMPLS_PRODUTO", None)
checa("produtos=None não quebra", bool(A._escolhe_ig_tmpl(False, "p", {}, None)))

print(f"\n{'='*66}\n   {ok} passou · {falhou} falhou\n{'='*66}")
raise SystemExit(1 if falhou else 0)
