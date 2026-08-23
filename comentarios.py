#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# comentarios.py — o 1º comentário de cada post, sem parecer robô.
#
# ⚠️ POR QUE ISTO EXISTE (reclamação do Dre, 22/08):
# *"o primeiro comentário em todos os posts, reels, carrossel, é sempre o
# mesmo... todo mundo que acompanha enjoa de ver o mesmo comentário robotizado
# toda vez. Pra carrossel isso nem faz sentido."*
#
# Ele está certo nas duas coisas, e a segunda é a mais séria:
#
#   1. ERA UMA FRASE SÓ. `meta_uploader._TMPL_IG` é uma constante. Todo Reel,
#      todo carrossel, todo dia, nas 6 contas: *"🛒 O link tá na BIO, corre
#      pegar o seu! 😍 / 💬 comenta EU QUERO que eu te ajudo a achar 👇"*.
#      Quem segue duas das nossas contas vê a mesma frase duas vezes por dia.
#
#   2. ⚠️ O COMENTÁRIO NÃO SABIA O QUE ESTAVA COMENTANDO. Num carrossel de
#      "3 erros que quase todo mundo comete", pedir "corre pegar o seu" é
#      resposta pra uma pergunta que ninguém fez — não tem "o seu" ali, tem
#      conteúdo. Comentário que ignora o post é pior que comentário repetido:
#      o repetido cansa, o desconexo denuncia a automação.
#
# DESENHO:
#   · banco POR FORMATO (reel · carrossel · carrossel de lista) e POR
#     PLATAFORMA (no Facebook o link é clicável; no Instagram não é, então lá
#     o pedido é de comentário/salvamento, não de clique)
#   · rotação com MEMÓRIA: guarda as últimas usadas por conta e não repete
#     enquanto houver alternativa. Sorteio puro repete — com 8 frases, a chance
#     de repetir a anterior é 1 em 8, ou seja, umas 9 vezes por mês.
#   · frase que precisa de {link} e não tem link simplesmente não é sorteada
#
# USO:
#   from comentarios import escolher
#   texto = escolher("instagram", formato="carrossel", conta="@topshopcasa_",
#                    link="", produto="Rodo mágico")

import os
import json
import random
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MEMORIA = BASE_DIR / "shared" / "comentarios_recentes.json"
LEMBRAR = int(os.environ.get("COMENT_LEMBRAR", "4"))


# ══════════════════════════════════════════════════════════════════════════
# OS BANCOS
#
# ⚠️ NENHUMA PROMETE O QUE A GENTE NÃO FAZ. "te mandei no direct" só entra
# quando o DM está de fato ligado — foi assim que o `auto_resposta` acabou
# mentindo pra cliente em julho, e a lição vale aqui igual.
# ══════════════════════════════════════════════════════════════════════════
_IG_REEL = [
    "🛒 o link tá na bio, é rapidinho de achar",
    "achei esse por acaso e não largo mais 👀",
    "tá na bio pra quem quiser ver de perto",
    "💬 comenta EU QUERO que eu te ajudo a achar",
    "esse aqui some rápido, corre ver na bio 🏃",
    "quem já tem um desses sabe do que eu tô falando",
    "link na bio · qualquer dúvida é só chamar",
    "salva aí pra não perder depois 🔖",
]

# ⚠️ CARROSSEL PEDE OUTRA COISA. O carrossel entrega CONTEÚDO, e o que faz ele
# ser entregue de novo é SALVAMENTO e COMENTÁRIO — não clique. Pedir "corre
# pegar o seu" num post de "3 erros" é falar de um produto que o post nem
# mostrou.
_IG_CARROSSEL = [
    "salva esse aqui pra não esquecer 🔖",
    "💬 qual desses você já fazia?",
    "manda pra quem precisa ler isso",
    "comenta aí se você já sabia disso 👀",
    "esse eu ia querer ter lido antes",
    "salva que depois você vai precisar",
    "💬 me conta qual te pegou de surpresa",
    "marca alguém que faz o número 1",
]

# lista de produtos: aí sim faz sentido falar de link
_IG_LISTA = [
    "🛒 todos estão na bio, é só escolher",
    "salva esse post, a lista é boa 🔖",
    "💬 qual você levaria primeiro?",
    "os links estão na bio pra quem quiser ver",
    "comenta o número do seu favorito 👇",
    "manda pra quem tá querendo comprar",
    "salva aí que essa lista rende 🔖",
    "💬 qual desses você já tem?",
]

# no Facebook o link é CLICÁVEL — outro jogo, outro pedido
_FB = [
    "🛒 compra aqui ó: {link}",
    "quem quiser ver de perto: {link}",
    "tá aqui o link, aproveita: {link}",
    "achei nesse aqui ó 👉 {link}",
    "link direto, sem enrolação: {link}",
]

_BANCOS = {
    ("instagram", "reel"): _IG_REEL,
    ("instagram", "carrossel"): _IG_CARROSSEL,
    ("instagram", "lista"): _IG_LISTA,
    ("facebook", "reel"): _FB,
    ("facebook", "carrossel"): _FB,
    ("facebook", "lista"): _FB,
}


def _banco(plataforma: str, formato: str) -> list:
    """Banco do par, com override por .env (COMENT_IG_CARROSSEL=a|||b|||c)."""
    p = "facebook" if (plataforma or "").lower().startswith("f") else "instagram"
    f = (formato or "reel").lower()
    if f not in ("reel", "carrossel", "lista"):
        f = "carrossel" if "carro" in f else "reel"
    env = os.environ.get(f"COMENT_{p[:2].upper()}_{f.upper()}", "")
    if env.strip():
        frases = [x.strip() for x in env.split("|||") if x.strip()]
        if frases:
            return frases
    return list(_BANCOS.get((p, f)) or _IG_REEL)


# ══════════════════════════════════════════════════════════════════════════
# MEMÓRIA — não repetir a última
# ══════════════════════════════════════════════════════════════════════════
def _ler() -> dict:
    try:
        return json.loads(MEMORIA.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _gravar(dados: dict) -> None:
    try:
        MEMORIA.parent.mkdir(parents=True, exist_ok=True)
        tmp = MEMORIA.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(MEMORIA)
    except Exception:
        pass          # memória é conforto, não requisito: nunca trava um post


def escolher(plataforma: str, formato: str = "reel", conta: str = "",
             link: str = "", produto: str = "", handle: str = "") -> str:
    """A frase do 1º comentário. "" quando não há nada honesto a dizer."""
    frases = _banco(plataforma, formato)
    ctx = {"link": (link or "").strip(), "produto": (produto or "").strip(),
           "handle": (handle or conta or "").strip()}

    # frase que pede {link} sem link vira "compra aqui ó: " — fora
    disponiveis = [f for f in frases
                   if "{link}" not in f or ctx["link"]]
    if not disponiveis:
        return ""

    memoria = _ler()
    chave = f"{conta or '?'}|{(plataforma or 'ig')[:2]}|{formato}"
    recentes = memoria.get(chave) or []

    # ⚠️ SORTEIO PURO REPETE. Com 8 frases, a chance de sair a mesma da vez
    # anterior é 1 em 8 — umas 9 vezes por mês no nosso volume, e é exatamente
    # essa repetição que faz parecer robô. Tira as últimas do bolo primeiro.
    novas = [f for f in disponiveis if f not in recentes]
    escolhida = random.choice(novas or disponiveis)

    memoria[chave] = ([escolhida] + recentes)[:max(1, LEMBRAR)]
    _gravar(memoria)

    try:
        return escolhida.format(**ctx).strip()
    except Exception:
        # chave desconhecida num template do .env não pode derrubar o post
        return re.sub(r"\{[^}]*\}", "", escolhida).strip()


def _cli() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Testa o 1º comentário")
    p.add_argument("--plataforma", default="instagram")
    p.add_argument("--formato", default="carrossel",
                   help="reel · carrossel · lista")
    p.add_argument("--conta", default="@teste")
    p.add_argument("--link", default="")
    p.add_argument("--quantos", type=int, default=8)
    a = p.parse_args()
    print(f"{a.plataforma} · {a.formato} · {a.conta}\n")
    for i in range(a.quantos):
        print(f"  {i+1}. {escolher(a.plataforma, a.formato, a.conta, a.link)}")
    print(f"\n(memória em {MEMORIA})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
