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
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ⚠️ ISTO FALTAVA DESDE SEMPRE (10/09/2026). Este arquivo ANUNCIA override por
# `.env` (`COMENT_IG_CARROSSEL=a|||b|||c`) desde 22/08 — e nunca leu o `.env`.
# Só olhava `os.environ`, então os overrides só funcionavam por acaso, quando
# outro módulo tivesse carregado o arquivo antes no mesmo processo.
#
# Quem mostrou foi o `--nichos` na VPS, dizendo "AUTO_RESPONDER=0 ← desligado"
# enquanto o `auto_resposta` (que lê o `.env`) mostrava a DM ligada no mesmo
# minuto. Duas leituras da mesma máquina discordando: uma delas estava cega.
#
# ⚠️ E EU TINHA ACABADO DE MANDAR O DRE USAR `COMENT_IG_REEL_PET='...'` pra
# soltar frases sem deploy. Aquele comando não teria feito nada, sem sintoma.
try:
    from shared.envfile import carregar_env as _carregar_env
except Exception:  # pragma: no cover
    try:
        from envfile import carregar_env as _carregar_env
    except Exception:
        def _carregar_env(base=None, sobrescrever=False):
            return 0
_carregar_env(BASE_DIR)

MEMORIA = BASE_DIR / "shared" / "comentarios_recentes.json"
LEMBRAR = int(os.environ.get("COMENT_LEMBRAR", "4"))

# a regra do "não repete" mora em shared/rotacao.py desde 09/09 — os dois
# arquivos que respondem no Instagram usam a MESMA. O import tem os dois
# caminhos porque o repo é achatado e a VPS usa pacotes.
try:
    from shared.rotacao import escolher_sem_repetir as _rodar
except Exception:  # pragma: no cover
    from rotacao import escolher_sem_repetir as _rodar


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
#
# ⚠️ E O BANCO NÃO SABIA EM QUE CONTA ESTAVA (10/09/2026). O Dre, sobre um Reel
# do @topshoppet_ — um cachorro com problema de ouvido, produto de limpeza
# auricular: *"o primeiro comentário dele tá péssimo!!"*. O que saiu foi
# *"esse tem muita cara de produto que viraliza e depois some"* — frase de
# gadget viral num post de SAÚDE DO PET.
#
# E tinha pior sorteável na mesma conta: *"o perigo é comprar um e depois querer
# outro **pra cada canto da casa**"*, no perfil de pet.
#
# A causa: o banco era escolhido por `(plataforma, formato)` e MAIS NADA. Seis
# contas, seis nichos, um banco só. É a MESMA classe que este arquivo já
# documenta lá em cima — *"o comentário não sabia o que estava comentando"* —
# resolvida pra FORMATO em 22/08 e nunca pra NICHO.
#
# ⚠️ O CONSERTO NÃO APAGA FRASE DELE. As seis continuam as dele, palavra por
# palavra: duas apenas deixaram de ser universais e passaram a sair só onde
# funcionam. Frase boa no lugar errado é problema de endereço, não de texto.
_IG_REEL = [
    "deixei na bio 💛 no grupo eu mando os achadinhos antes de aparecerem por aqui.",
    "isso aí no dia a dia deve facilitar mais do que parece, salva pra lembrar quando precisar 🥰",
    "alguém aqui já tem um desses? quero saber se presta mesmo 👀 comenta uma nota de 0 a 10",
    "os achados que valem a pena vão pro grupo primeiro ✨ link na bio",
]

# frases que SÓ fazem sentido em alguns nichos, somadas ao banco universal.
# ⚠️ `pet` e `moda` estão VAZIOS DE PROPÓSITO, e o vazio é o recado: o Dre
# escreve melhor que eu (medido — as dele conversam, as minhas descreviam), e
# inventar frase na voz dele pra soltar em conta ao vivo seria trocar um defeito
# visível por um invisível. Enquanto não chegarem, essas contas usam só o banco
# universal, que é honesto em qualquer nicho.
_IG_REEL_POR_NICHO = {
    "casa": [
        "o perigo é comprar um e depois querer outro pra cada canto da casa 😂 curte se quer mais produtos assim por aqui",
    ],
    "tech": [
        "esse tem muita cara de produto que viraliza e depois some, salva aí antes que você esqueça o nome 😂",
    ],
    # @topshop.__ é a loja genérica: as duas cabem
    "geral": [
        "o perigo é comprar um e depois querer outro pra cada canto da casa 😂 curte se quer mais produtos assim por aqui",
        "esse tem muita cara de produto que viraliza e depois some, salva aí antes que você esqueça o nome 😂",
    ],
    "beleza": [],
    "moda": [],
    "pet": [],
}

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


# ══════════════════════════════════════════════════════════════════════════
# OS 10 COMENTÁRIOS FIXADOS DO DRE (10/09/2026)
#
# Estes são de outra natureza que os de cima: os outros CONVERSAM, estes fazem
# um PEDIDO — "comenta QUERO que eu te mando na DM". É a isca que alimenta o
# `auto_resposta`, e num Reel que estoura é o que transforma alcance em conversa.
#
# ⚠️⚠️ E CADA UM DELES É UMA PROMESSA QUE ALGUÉM TEM QUE CUMPRIR. Se o
# `auto_resposta` não estiver respondendo com DM, a conta pede publicamente
# "comenta QUERO que eu mando na sua DM", dezenas de pessoas comentam, e nada
# chega. Isso não é post fraco: é a conta mentindo pra quem levantou a mão — e
# é MUITO pior que o comentário genérico que a gente acabou de consertar.
#
# Por isso eles só entram no sorteio quando os DOIS interruptores estão ligados
# (AUTO_RESPONDER e AUTO_RESP_DM). É a mesma regra que já governa este arquivo
# desde julho, escrita no cabeçalho: *"NENHUMA PROMETE O QUE A GENTE NÃO FAZ"*.
#
# ⚠️ E SÓ EM REEL/LISTA, NUNCA EM CARROSSEL. Num carrossel de "3 erros" não
# existe "esse achadinho" pra mandar — o pedido não tem objeto. Mesma razão pela
# qual o carrossel nunca herdou o banco de Reel.
_IG_ISCA_DM = [
    "👀 Quer o link desse achadinho? Comenta “QUERO” que eu te mando na DM 💛",
    "😳 Eu sabia que vocês iam perguntar onde compra kkkkk. Comenta “QUERO” que eu mando o link!",
    "🔗 Gostou desse? Comenta “LINK” aqui embaixo que eu mando direto na sua DM 👇",
    "🛍️ Quer achar esse produto sem ficar procurando? Comenta “MANDA” que eu te envio na DM 💛",
    "👀 Quem quiser o link, deixa um “EU QUERO” aqui que eu mando no direct!",
    "🔥 Esse aqui merece entrar na lista de achadinhos! Comenta “LINK” que eu te mando onde encontrar.",
    "💛 Gostou do produto? Escreve “QUERO” aqui embaixo e olha sua DM depois 👀📩",
    "⚡ Quer ver preço e onde comprar? Comenta “MANDA” que eu envio o acesso na sua DM.",
    "🛒 Pra quem já tá procurando o link: comenta “EU QUERO” e eu mando no direct 👀",
    "👇 Quem chegou até aqui e quer esse achadinho, comenta “LINK” que o Jarvis manda na sua DM 🤖💛",
]


def _dm_responde() -> bool:
    """Os dois interruptores do `auto_resposta` estão ligados?

    ⚠️ ISTO NÃO PROVA QUE A DM CHEGA — prova que ela está LIGADA. O escopo
    `instagram_manage_messages` pode estar faltando e a chamada falhar em
    silêncio (o `_enviar_dm_ig` é best-effort de propósito). É o melhor sinal
    disponível de dentro deste arquivo, e é infinitamente melhor que soltar a
    isca sem olhar nada.
    """
    def _lig(nome):
        return os.environ.get(nome, "0").strip().lower() in ("1", "true", "sim")
    return _lig("AUTO_RESPONDER") and _lig("AUTO_RESP_DM")


_NICHO_POR_HANDLE = None


def _nicho_da_conta(conta: str) -> str:
    """O nicho da conta, a partir do `contas.json` — que já é indexado por nicho.

    ⚠️ NÃO DUPLICO O MAPA AQUI. O `contas.json` é a fonte que o roteador usa pra
    decidir em que conta cada produto vai; uma segunda cópia neste arquivo
    ficaria desatualizada no dia em que uma conta for criada ou trocar de nicho,
    e o sintoma seria comentário de nicho errado — exatamente o defeito que este
    roteamento existe pra consertar.

    ⚠️ HANDLE QUE NÃO RESOLVE DEVOLVE "" (desconhecido), NÃO "geral" — e a
    diferença é o defeito inteiro. `geral` é o @topshop.__, a loja genérica, e o
    banco dele carrega JUSTAMENTE as duas frases que não podem sair no pet
    ("pra cada canto da casa", "produto que viraliza"). Se um handle não
    resolvesse e caísse em `geral`, o conserto se desfazia sozinho, em silêncio,
    exatamente na conta que motivou o conserto.
    Desconhecido usa só o banco universal, que é honesto em qualquer conta.
    """
    global _NICHO_POR_HANDLE
    if _NICHO_POR_HANDLE is None:
        _NICHO_POR_HANDLE = {}
        for cam in (BASE_DIR / "contas.json", BASE_DIR / "shared" / "contas.json"):
            try:
                dados = json.loads(cam.read_text(encoding="utf-8"))
            except Exception:
                continue
            for chave, val in (dados or {}).items():
                if not isinstance(val, dict):
                    continue
                h = (val.get("handle") or "").strip().lstrip("@").lower()
                if not h:
                    continue
                nicho = (val.get("nicho") or "").strip().lower()
                if not nicho:
                    # o contas.json é indexado POR NICHO; '_default' é o geral
                    nicho = "geral" if chave.startswith("_") else chave.lower()
                _NICHO_POR_HANDLE[h] = nicho
            break
    return _NICHO_POR_HANDLE.get((conta or "").strip().lstrip("@").lower(), "")


def _banco(plataforma: str, formato: str, conta: str = "") -> list:
    """Banco do par, com override por .env (COMENT_IG_CARROSSEL=a|||b|||c).

    No Reel do Instagram o banco é universal + as frases do NICHO da conta.
    """
    p = "facebook" if (plataforma or "").lower().startswith("f") else "instagram"
    f = (formato or "reel").lower()
    if f not in ("reel", "carrossel", "lista"):
        f = "carrossel" if "carro" in f else "reel"

    # override por nicho vem primeiro: COMENT_IG_REEL_PET=a|||b|||c é como o Dre
    # solta as frases dele sem precisar de deploy
    nicho = _nicho_da_conta(conta)
    if p == "instagram" and nicho:
        env_n = os.environ.get(f"COMENT_IG_{f.upper()}_{nicho.upper()}", "")
        if env_n.strip():
            frases = [x.strip() for x in env_n.split("|||") if x.strip()]
            if frases:
                return frases

    env = os.environ.get(f"COMENT_{p[:2].upper()}_{f.upper()}", "")
    if env.strip():
        frases = [x.strip() for x in env.split("|||") if x.strip()]
        if frases:
            return frases

    base = list(_BANCOS.get((p, f)) or _IG_REEL)
    if p == "instagram" and f == "reel" and nicho:
        base += list(_IG_REEL_POR_NICHO.get(nicho) or [])
    # a isca de DM só entra onde há um produto pra mandar E onde a DM responde
    if p == "instagram" and f in ("reel", "lista") and _dm_responde():
        base += list(_IG_ISCA_DM)
    return base


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
    frases = _banco(plataforma, formato, conta)
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
    # ⚠️ a chave da memória continua por CONTA, não por nicho: duas contas do
    # mesmo nicho postando no mesmo dia não podem herdar a rotação uma da outra.
    chave = f"{conta or '?'}|{(plataforma or 'ig')[:2]}|{formato}"
    recentes = memoria.get(chave) or []

    # ⚠️ A REGRA SAIU DAQUI EM 09/09 e virou `shared/rotacao.py`. Ela estava
    # certa e documentada — e morava só neste arquivo, enquanto o
    # `auto_resposta.py` respondia os comentários com `random.choice` puro e
    # mandava "Bio 🔗 dá uma olhada e me fala" pra três pessoas no mesmo post.
    # O raciocínio inteiro (por que metade, por que não `len-1`) está lá.
    escolhida, memoria[chave] = _rodar(disponiveis, recentes, LEMBRAR)
    if not escolhida:
        return ""
    _gravar(memoria)

    try:
        return escolhida.format(**ctx).strip()
    except Exception:
        # chave desconhecida num template do .env não pode derrubar o post
        return re.sub(r"\{[^}]*\}", "", escolhida).strip()


def _diag_nichos() -> int:
    """Cada conta resolve pro nicho certo? E que banco ela usa?

    ⚠️ ESTE MODO EXISTE PORQUE O ROTEAMENTO FALHA CALADO. Handle que não está no
    `contas.json` cai em "desconhecido" e usa só o banco universal — correto,
    mas invisível: o post sai normal e ninguém descobre que aquela conta nunca
    recebeu as frases do nicho dela.
    """
    _nicho_da_conta("")          # força carregar o mapa
    mapa = _NICHO_POR_HANDLE or {}
    print(f"\n{'='*72}\n  NICHO POR CONTA — de onde sai o 1º comentário\n{'='*72}")
    print(f"\n  contas.json: {len(mapa)} conta(s) mapeada(s)\n")
    if not mapa:
        print("  ⚠️ nenhuma! O contas.json não foi lido — todas usam só o "
              "banco universal.")
        return 1
    for handle, nicho in sorted(mapa.items(), key=lambda kv: kv[1]):
        banco = _banco("instagram", "reel", handle)
        extras = _IG_REEL_POR_NICHO.get(nicho)
        if extras is None:
            marca, obs = "⚠️ ", f"nicho '{nicho}' não tem banco — só o universal"
        elif not extras:
            # ⚠️ VAZIO AQUI NÃO É PENDÊNCIA (10/09). O Dre respondeu: *"essas aí
            # são as frases que ficaram em todas as contas"* — as 14 respostas e
            # as 10 iscas são UNIVERSAIS de propósito. Este marcador chegou a
            # dizer "esperando as frases do Dre" e viraria cobrança de uma coisa
            # já entregue, que é o defeito que o próprio ROADMAP chama de
            # "pendência marcada e nunca desmarcada vira mentira com aparência
            # de registro".
            marca, obs = "○ ", "sem frase exclusiva (usa o banco universal)"
        else:
            marca, obs = "✅", f"+{len(extras)} frase(s) do nicho"
        print(f"   {marca} @{handle:<20} {nicho:<8} {len(banco)} frase(s)  {obs}")
    # ⚠️ O NÚMERO QUE IMPORTA AQUI É SE A ISCA ESTÁ VIVA. As 10 iscas de DM só
    # entram no sorteio com AUTO_RESPONDER e AUTO_RESP_DM ligados — e uma isca
    # que não sai é exatamente o defeito que este projeto repete: frase
    # escrita, versionada e morta, sem nenhum sinal.
    if _dm_responde():
        print(f"\n  ✅ as {len(_IG_ISCA_DM)} iscas de DM estão ATIVAS "
              f"(AUTO_RESPONDER e AUTO_RESP_DM ligados)")
    else:
        print(f"\n  ⚠️ as {len(_IG_ISCA_DM)} iscas de DM estão FORA do sorteio:")
        for k in ("AUTO_RESPONDER", "AUTO_RESP_DM"):
            v = os.environ.get(k, "0")
            print(f"       {k}={v}" + ("" if v.strip().lower() in ("1", "true", "sim")
                                       else "   ← desligado"))
        print(f"     Elas pedem 'comenta QUERO que eu mando na DM'; sem o "
              f"respondedor\n     ligado o pedido sai e ninguém responde.")
    print(f"\n  ○ nichos sem frase exclusiva usam o banco universal — o Dre "
          f"disse que\n    as frases dele valem pra todas as contas. Se um dia "
          f"quiser específicas:\n    COMENT_IG_REEL_PET='frase 1|||frase 2'")
    return 0


def _cli() -> int:
    import argparse
    if "--nichos" in sys.argv:
        return _diag_nichos()
    p = argparse.ArgumentParser(description="Testa o 1º comentário")
    p.add_argument("--nichos", action="store_true",
                   help="mostra o nicho de cada conta e o banco que ela usa")
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
