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
# ⚠️ REESCRITO EM 02/09. O Dre: *"o primeiro comentário que o jarvis faz no
# post tá muito feio, vamos fixar 3 melhores frases, até mesmo dá pra divulgar o
# grupo do whats"*. Ele pediu 3 e mandou 6 — ficaram as 6, porque banco maior é
# menos chance de parecer robô e o custo de guardar as seis é zero.
#
# ⚠️ E SAIU O "CORRE VER". A frase *"esse aqui some rápido, corre ver na bio"*
# estava aqui desde 22/08 — a MESMA construção que o Dre vetou nos ganchos em
# 21/08: *"'corre ver isso' é gramaticalmente errado, e não traz nenhum tipo de
# interesse na pessoa, só é um anúncio"*. A régua foi aplicada ao hook_alana e
# nunca chegou neste arquivo. Régua que vale num arquivo só não é régua.
#
# O GRUPO DO WHATSAPP entra em 1 de cada 3~4 frases, não em todas: encher os
# grupos é meta corrente e o 1º comentário é o espaço mais barato que existe,
# mas todo comentário puxando pro grupo vira panfleto.
#
# ⚠️ NO INSTAGRAM LINK EM COMENTÁRIO NÃO É CLICÁVEL. Por isso a frase do grupo
# manda pra BIO (onde o botão do grupo já existe, no topshopoficial.com.br) em
# vez de colar um `chat.whatsapp.com` que ninguém consegue tocar. No Facebook,
# onde o link funciona, ele vai direto — ver `_FB`.
#
# ⚠️ ESTAS SEIS SÃO DO DRE, PALAVRA POR PALAVRA (02/09). Eu tinha escrito três;
# ele mandou as dele e são melhores — e a diferença é ensinável, então fica
# registrada em vez de só substituída:
#
#   as minhas DESCREVIAM   "salva aí pra não perder depois"
#   as dele CONVERSAM      "salva aí antes que você esqueça o nome 😂"
#
# As dele têm uma opinião ("o perigo é comprar um e depois querer outro"), fazem
# uma pergunta de verdade ("quero saber se presta mesmo") e admitem dúvida —
# coisas que um anúncio não faz. É a mesma régua dos ganchos, aplicada ao
# comentário: situação reconhecível em vez de chamada pra ação.
#
# São SEIS e não três (ele pediu "3 melhores" e mandou 6): mais frases = menos
# chance de parecer robô, e o custo de manter as seis é zero.
_IG_REEL = [
    "deixei na bio 💛 no grupo eu mando os achadinhos antes de aparecerem por aqui.",
    "isso aí no dia a dia deve facilitar mais do que parece, salva pra lembrar quando precisar 🥰",
    "o perigo é comprar um e depois querer outro pra cada canto da casa 😂 curte se quer mais produtos assim por aqui",
    "esse tem muita cara de produto que viraliza e depois some, salva aí antes que você esqueça o nome 😂",
    "alguém aqui já tem um desses? quero saber se presta mesmo 👀 comenta uma nota de 0 a 10",
    "os achados que valem a pena vão pro grupo primeiro ✨ link na bio",
]

# ⚠️ O CARROSSEL NÃO HERDA AS SEIS. Quatro delas falam de COMPRAR ("o perigo é
# comprar um", "alguém já tem um desses") e o carrossel entrega CONTEÚDO — num
# post de "3 erros", perguntar se a pessoa já tem um desses é falar de um
# produto que o post não mostrou. Era exatamente a observação que já estava
# escrita aqui em 22/08; mantida.
_IG_CARROSSEL = [
    "salva esse aqui pra não esquecer 🔖",
    "💬 me conta qual te pegou de surpresa",
    "curte se quer mais conteúdo assim por aqui 💛",
    "os achados que valem a pena vão pro grupo primeiro ✨ link na bio",
]

# lista de produtos: aí sim faz sentido falar de link
_IG_LISTA = [
    "💬 qual você levaria primeiro?",
    "salva esse post, a lista é boa 🔖",
    "alguém aqui já tem um desses? quero saber se presta mesmo 👀 comenta uma nota de 0 a 10",
    "os achados que valem a pena vão pro grupo primeiro ✨ link na bio",
]

# no Facebook o link é CLICÁVEL — outro jogo, outro pedido.
# {whats} é o convite do grupo, e vem do MESMO lugar que o site publica
# (`_convite_whats()`): link de grupo duplicado à mão vira link morto o dia em
# que um dos dois for trocado. Sem o convite, a frase nem é sorteada.
_FB = [
    "tá aqui ó: {link}",
    "quem quiser ver de perto: {link}",
    "os achados que valem a pena vão pro grupo primeiro ✨ {whats}",
]


def _convite_whats() -> str:
    """O link do grupo. Env primeiro, depois a constante que o SITE usa.

    Não copio o `chat.whatsapp.com` pra cá de propósito: ele já mora em
    `bio_page_builder.GRUPO_WHATSAPP` e é publicado no topshopoficial.com.br.
    Duas cópias significam que, no dia em que o convite for trocado, uma delas
    manda gente pra um grupo morto — e ninguém descobre, porque um comentário
    com link errado não dá erro em lugar nenhum.

    O import tem os dois caminhos (raiz e pacote) porque o repo é achatado e a
    VPS usa pacotes.
    """
    env = os.environ.get("WHATSAPP_CONVITE", "").strip()
    if env:
        return env
    for caminho in ("bio_page_builder", "creative_engine.bio_page_builder"):
        try:
            mod = __import__(caminho, fromlist=["GRUPO_WHATSAPP"])
            return (getattr(mod, "GRUPO_WHATSAPP", "") or "").strip()
        except Exception:
            continue
    return ""

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
           "handle": (handle or conta or "").strip(),
           "whats": _convite_whats()}

    # frase que pede {link} sem link vira "compra aqui ó: " — fora.
    # Mesma regra pro {whats}: convidar pra um grupo sem dizer qual é pior que
    # não convidar.
    disponiveis = [f for f in frases
                   if ("{link}" not in f or ctx["link"])
                   and ("{whats}" not in f or ctx["whats"])]
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

    # ⚠️ A MEMÓRIA SE AJUSTA AO TAMANHO DO BANCO (02/09). LEMBRAR=4 fixo com um
    # banco de 3 frases é anti-repetição MORTO: as 3 ficariam "recentes", a
    # lista `novas` sairia vazia e o `or disponiveis` cairia em sorteio puro —
    # exatamente o que este arquivo existe pra impedir, sem nenhum sintoma além
    # de frases repetindo. Lembrar de tudo é o mesmo que não lembrar de nada.
    # METADE do banco, no máximo. `len-1` parece o teto óbvio e é armadilha:
    # com 3 frases ele lembra 2, sobra exatamente 1 candidata e a rotação vira
    # um ciclo fixo 1-2-3-1-2-3 — nunca repete, e é lido como robô do mesmo
    # jeito, só que por regularidade em vez de repetição. Medido antes de subir.
    # Metade preserva o comportamento de hoje nos bancos de 8 (lembrava 4).
    teto = max(1, min(LEMBRAR, len(disponiveis) // 2))
    memoria[chave] = ([escolhida] + recentes)[:teto]
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
