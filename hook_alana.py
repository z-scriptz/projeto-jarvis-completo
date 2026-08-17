#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# hook_alana.py -- GERADOR DE HOOK viral (curiosity-gap, 2 linhas) com CATALOGO
# de formulas provadas. O Gemini escolhe a formula que melhor combina com o
# produto e escreve o hook; varia a formula a cada video (nao repete).
#
# >>> PRA EDITAR: e so mexer em FORMULAS (adicionar/tirar molde) e em
#     HOOKS_RESERVA (frases prontas por nicho, usadas se o Gemini cair). <<<
#
# Formato de saida: 1 ou 2 linhas. O narrated_video_agent respeita o "\n" e poe
# o emoji no fim da 1a linha (estilo Alana).
#
# Uso:
#   from hook_alana import gerar_hook_alana
#   hook = gerar_hook_alana("Passadeira a Vapor", descricao="...", nicho="casa")

import os
import re
import json
import random
from pathlib import Path
from typing import Optional

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    log = logging.getLogger("hook_alana")

BASE_DIR = Path(__file__).resolve().parent


def _carregar_env():
    """Lê o .env pra dentro do os.environ.

    Este módulo era o único da cadeia que NÃO carregava o .env: dependia de quem
    o importasse ter feito isso antes. O telegram_repurpose_hunter não faz — e o
    resultado era GEMINI_API_KEY vazia, com hook e legenda caindo no banco de
    reserva em silêncio (a conta de beleza publicando curiosidade genérica sobre
    organização da casa).

    Diferente dos outros carregadores do projeto, este também preenche quando a
    variável existe mas está VAZIA: variável vazia esconde o problema do mesmo
    jeito que a ausente.
    """
    for candidato in (BASE_DIR / ".env", Path(".env")):
        try:
            if not candidato.exists():
                continue
            linhas = candidato.read_text(encoding="utf-8").splitlines()
        except Exception as erro:        # .env ilegível não pode derrubar o import
            log.warning("não consegui ler %s: %s", candidato, str(erro)[:120])
            continue
        for linha in linhas:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            chave, _, valor = linha.partition("=")
            chave = chave.strip()
            valor = valor.strip().strip('"').strip("'")
            if chave and not os.environ.get(chave):
                os.environ[chave] = valor
        break


_carregar_env()

TAG_PADRAO = os.environ.get("HOOK_ALANA_TAG", "A Shopee:")

_RECENTES_PATH = Path(__file__).resolve().parent / "hooks_alana_recentes.json"
_RECENTES_MAX = 80
_REACH_JSONL = Path(__file__).resolve().parent / "shared" / "reach.jsonl"  # alcance (reach_agent)

# ─────────────────────────────────────────────────────────────────────────────
# CATALOGO DE FORMULAS VIRAIS (moldes). O Gemini escolhe a que combina com o
# produto e preenche. {tag} vira "A Shopee:" (ou HOOK_ALANA_TAG). Adicione as suas!
#   - use "\n" onde o hook tem 2 partes (linha 1 / linha 2)
#   - <...> = o que o Gemini preenche pensando no produto
#   - <emoji> = 1 emoji que combine (ele escolhe)
# ─────────────────────────────────────────────────────────────────────────────
# ⚠️ QUAIS DESTES MOLDES SÃO EM 1ª PESSOA (medido, não gosto).
# `storyboard.py:18` guarda o resultado de **133 posts de 08/08**:
#     hook em 1ª pessoa   3,8 a 5,1% de engajamento
#     hook de urgência    1,8 a 2,2%
#     "A Shopee:"         1,0 a 1,8%  (14 posts)
# Ou seja: 1ª pessoa rende 2 a 3× mais. Só que essa regra vivia SÓ no
# `storyboard.py`, que é o caminho AUTORAL — e o caminho autoral (`piloto.py`)
# nunca é chamado por nada. Quem produz de verdade é o `produzir_tiktok.py`,
# que chama ESTE arquivo. A medição existia, estava escrita, e não alcançava a
# produção. (15/08)
PRIMEIRA_PESSOA = {"desabafo_shopee", "eu_vs_shopee", "virei_fa",
                   "comprei_testei"}

FORMULAS = [
    ("desabafo_shopee",  '"<dor ou desejo do dia a dia em 1a pessoa>" <emoji>\n{tag}'),
    ("eu_vs_shopee",     'Eu: <juramento ou resistencia engracada>\n{tag}'),
    ("pov_beneficio",    'Pov: <o beneficio irresistivel / a situacao> <emoji>'),
    ("pov_melhor_compra",'Pov: A melhor compra que fiz pra <lugar/contexto> <emoji>'),
    ("alerta_exclusao",  'Nao mostre isso pra quem <ama/tem/gosta de X> <emoji>'),
    ("necessidade",      'Toda pessoa que <gosta de X> precisa ter isso <emoji>'),
    ("cumplice_humor",   'Que <alguem> nao veja esse video, amem <emoji>'),
    ("segredo",          'O segredo pra <resultado desejado> que ninguem te conta <emoji>'),
    ("virei_fa",         '<Nunca imaginei que eu ia precisar disso> <emoji>\n{tag}'),
    ("comprei_testei",   'Comprei sem esperar nada e <me surpreendeu demais> <emoji>'),
]

# Frases PRONTAS por nicho (reserva quando o Gemini cai). Ja no formato final
# (com "\n" onde tem 2 partes). Cresca a vontade — sao 100% suas.
HOOKS_RESERVA = {
    "casa": [
        '"Minha casa vivia uma bagunça sem fim" 😩\n{tag}',
        '"Queria uma casa mais aconchegante" 🥺\n{tag}',
        '"Cansei de viver no meio da zona" 😮‍💨\n{tag}',
        '"Achava que casa arrumada era só pra rico" 😳\n{tag}',
        'Sua casa pode ficar organizada sem tomar o seu fim de semana 👀',
        'A bagunça de casa some bem mais rápido do que você imagina 🙌',
        'Pov: a comprinha baratinha que transformou a minha casa inteira 😍',
        'Eu não sabia que precisava disso até deixar minha casa impecável 🤯',
        'O segredo pra deixar a casa sempre cheirosa que ninguém te conta 🤫',
        'Comprei sem esperar nada e resolveu um problema que eu tinha há anos 😱',
        'Corre ver isso antes que acabe, tá baratinho demais na promoção 🏃‍♀️',
        'Você organizando a sua casa do jeito difícil esse tempo todo 😅',
        'O presente que salva uma casa nova e ninguém lembra de dar 🏡',
        'Isso deixou minha casa com cara de apartamento de revista 😍',
        'Parei de gastar à toa depois que achei esse achadinho pra casa 💸',
    ],
    "cozinha": [
        '"Passo horas na cozinha à toa" 😮‍💨\n{tag}',
        '"Odiava perder tempo cozinhando" 😩\n{tag}',
        '"Minha cozinha vivia um caos na hora do almoço" 😫\n{tag}',
        'Dá pra passar menos tempo na cozinha e comer igual de bem 👀',
        'Cozinhar todo dia deixa de ser sacrifício com um detalhe barato 😍',
        'Pov: a melhor compra que fiz pra facilitar a minha cozinha 🍳',
        'Eu não sabia viver sem isso depois que testei aqui em casa 🤯',
        'O truque de cozinha que a minha avó queria ter conhecido antes 👵',
        'Comprei achando que era bobeira e virou meu queridinho da cozinha 😅',
        'Pare de perder tempo cozinhando do jeito mais difícil de todos 🛑',
        'Isso me economiza uns 30 minutos toda vez que eu vou cozinhar ⏱️',
        'Corre que esse achadinho de cozinha tá saindo baratinho demais 🏃‍♀️',
        'O presente de cozinha que resolve a pior parte: a bagunça 🎁',
        'Ninguém me contou que existia isso e mudou minha cozinha inteira 🤫',
    ],
    "beleza": [
        '"Minha make vivia um caos total" 😩\n{tag}',
        '"Queria me sentir mais bonita" 🥺\n{tag}',
        '"Achava que pele linda era só de filtro" 😳\n{tag}',
        'Toda mulher que ama se cuidar e ficar linda precisa ter isso 😍',
        'A pele muda de um jeito que maquiagem nenhuma consegue imitar 👀',
        'Pov: o achadinho que mudou a minha rotina de beleza inteira ✨',
        'Eu não sabia que precisava disso até ver o resultado na minha pele 🤯',
        'O segredo de beleza que as famosas não te contam de jeito nenhum 🤫',
        'Comprei baratinho e substituiu meia dúzia de produtos caros 💸',
        'Corre ver isso antes que viralize e suma das prateleiras 🏃‍♀️',
        'Você cuidando da sua pele do jeito errado esse tempo todo 😬',
        'Presente perfeito pra você que ama um bom autocuidado em casa 🎁',
        'Isso me deixou pronta em 5 minutos e ainda durou o dia todo 😍',
        'Ninguém acredita que esse resultado veio de um achadinho barato 🤭',
    ],
    "tech": [
        '"Meu setup vivia um caos de fios" 😩\n{tag}',
        '"Vivia sem espaço nenhum no meu setup" 😮‍💨\n{tag}',
        '"Meu celular vivia descarregando na pior hora" 😫\n{tag}',
        'Esse gadget resolve em segundos o que te irrita há meses 👀',
        'Toda pessoa viciada em tecnologia precisa ter esse gadget agora 🔌',
        'Pov: o gadget que parece coisa do futuro bem na sua mão 🤯',
        'Eu não sabia que precisava disso até deixar meu setup impecável 😍',
        'O gadget que resolveu um problema que eu tinha há muito tempo 😱',
        'Comprei achando que era firula e hoje não vivo mais sem 😅',
        'Corre ver isso antes que esgote, tá baratinho demais pra função 🏃',
        'Você usando seu celular sem esse acessório ainda em 2026? 😬',
        'O presente de tecnologia que arranca um "onde achou isso?" 🎁',
        'Isso deixou meu setup com cara de gamer profissional na hora 🎮',
        'Parece caro mas foi um dos achadinhos mais baratos que já fiz 🤫',
    ],
    "pets": [
        '"Meu pet merecia muito mais" 🥺\n{tag}',
        '"Vivia sofrendo pra dar banho no meu cachorro" 😩\n{tag}',
        'Dá pra ter cachorro em casa sem a casa inteira cheirar mal 😱',
        'Seu pet fica bem mais tranquilo com uma coisinha barata 🐶',
        'Pov: a comprinha barata que deixou o meu pet muito mais feliz 🐾',
        'Eu não sabia que precisava disso até ver a alegria do meu pet 🥹',
        'O segredo pra acabar com o pelo espalhado pela casa toda 🐕',
        'Comprei sem esperar nada e virou o brinquedo favorito dele 🎾',
        'Corre ver isso antes que acabe, resolve a maior chatice do pet 🏃‍♀️',
        'O presente que transforma o cachorro no bicho mais mimado da rua 🎁',
        'Isso salvou minha casa dos estragos do meu pet quando fico fora 😅',
        'Ninguém me contou que existia isso e facilitou a vida com o pet 🤫',
    ],
    "moda": [
        '"Nunca me sentia bem vestida" 🥲\n{tag}',
        '"Achava que roupa boa custava uma fortuna" 😳\n{tag}',
        'Dá pra se arrumar em 5 minutos e parecer que levou uma hora 👀',
        'Toda mulher que quer se vestir bem sem gastar muito precisa ver 😍',
        'Pov: a peça que me devolveu a autoestima na hora de me arrumar 😍',
        'Eu não sabia que precisava disso até receber um monte de elogio 🥰',
        'O segredo pra montar look caro gastando pouquinho na Shopee 🤫',
        'Comprei sem fé e virou a peça que eu mais uso no guarda-roupa 😅',
        'Corre ver isso antes que acabe o estoque, tá voando na promoção 🏃‍♀️',
        'Você se vestindo bem sem gastar rios de dinheiro finalmente 💸',
        'O presente que parece caro e custou menos que um lanche 🎁',
        'Isso valoriza qualquer corpo e disfarça o que a gente não gosta 😍',
    ],
    "academia": [
        '"Minhas costas vivem doendo o dia todo" 😩\n{tag}',
        '"Cansei de acordar todo travado de manhã" 😮‍💨\n{tag}',
        'A dor depois do treino passa bem mais rápido com esse truque 💪',
        'Dá pra treinar em casa e sentir o mesmo peso da academia 👀',
        'Pov: o alívio que o meu corpo todo estava precisando há tempos 😮‍💨',
        'Eu não sabia que precisava disso até aliviar a dor na hora 😌',
        'O segredo pra recuperar o corpo mais rápido depois do treino 🤫',
        'Comprei achando que não ia funcionar e me arrependi de não ter antes 😅',
        'Corre ver isso antes que suma, muda o treino em casa inteiro 🏃',
        'O presente que alivia a dor do treino e custa quase nada 🎁',
        'Isso substituiu a massagem cara que eu pagava toda semana 💸',
    ],
    "geral": [
        '"Nunca imaginei precisar disso na vida" 😳\n{tag}',
        '"Vivia com um probleminha que ninguém resolvia" 😩\n{tag}',
        '"Achava que isso não ia funcionar de jeito nenhum" 🤨\n{tag}',
        'Economizar de verdade não é achar promoção, é achar isso aqui 👀',
        'Esse achadinho baratinho resolve um problema que todo mundo tem 🤫',
        'Pov: a melhor comprinha que eu fiz nesse mês inteiro 😍',
        'Comprei sem esperar nada e me surpreendeu demais com o resultado 🤯',
        'Eu não sabia que precisava disso até resolver de vez o meu problema 😱',
        'O segredo que ninguém te conta pra facilitar a vida gastando pouco 🤫',
        'Corre ver isso antes que viralize e o preço suba na Shopee 🏃‍♀️',
        'Você fazendo isso do jeito difícil esse tempo todo sem saber 😅',
        'Presente perfeito e baratinho pra dar pra qualquer pessoa 🎁',
        'Isso resolveu num segundo um problema que me incomodava há anos ⏱️',
        'Ninguém acredita quando eu falo o preço desse achadinho 🤭',
        'Parece caro mas é um dos achadinhos mais baratos da Shopee 💸',
    ],
}

_NICHO_ALIAS = {
    "casa": "casa", "utilidades": "casa", "eletro": "tech", "tech": "tech",
    "cozinha": "cozinha", "beleza": "beleza", "skincare": "beleza",
    "maquiagem": "beleza", "pet": "pets", "pets": "pets", "moda": "moda",
    "fitness": "academia", "academia": "academia", "geral": "geral", "": "geral",
}

_EMOJI_RX = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF←-⇿⬀-⯿]"
)


def _ler_recentes() -> list:
    try:
        return json.loads(_RECENTES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _registrar(hook: str):
    try:
        r = _ler_recentes()
        r.append(hook)
        _RECENTES_PATH.write_text(json.dumps(r[-_RECENTES_MAX:], ensure_ascii=False),
                                  encoding="utf-8")
    except Exception:
        pass


def _chave_nicho(nicho: str) -> str:
    return _NICHO_ALIAS.get((nicho or "").strip().lower(), "geral")


def _eh_2linhas(h: str) -> bool:
    """True se o hook renderiza em 2 linhas: tem tag/quebra explícita OU é uma
    frase longa o bastante pra quebrar em 2 no vídeo (blindagem do formato)."""
    if "\n" in h or "{tag}" in h:
        return True
    return len(_EMOJI_RX.sub("", h).strip()) >= int(os.environ.get("HOOK_MIN_CHARS", 44))


# Palavras CONCRETAS que aparecem nas frases de reserva, com o que precisa
# existir no nome do produto pra elas fazerem sentido. Levantadas do próprio
# banco (contagem sobre HOOKS_RESERVA), não inventadas.
#
# Por que isto existe: em 03/08 saiu no ar um mouse gamer com o hook "Meu
# celular vivia descarregando na pior hora". A reserva conhece o NICHO (tech),
# não o produto — então qualquer coisa classificada como tech podia receber uma
# frase sobre bateria de celular.
_CONCRETO = {
    "celular":   ("celular", "smartphone", "iphone", "fone", "carregad", "cabo",
                  "power bank", "bateria"),
    "casa":      ("casa", "sofá", "sofa", "sala", "quarto", "manta", "almofada",
                  "cortina", "tapete", "lençol", "lencol", "decor"),
    "cozinha":   ("cozinha", "panela", "copo", "caneca", "talher", "fatiad",
                  "prato", "faca", "ovo", "ralad", "liquidif", "fritad"),
    "cozinhar":  ("cozinha", "panela", "fritad", "receita", "chef"),
    "cozinhando": ("cozinha", "panela", "fritad", "receita", "chef"),
    "pele":      ("pele", "skincare", "hidrat", "facial", "creme", "sérum",
                  "serum", "corporal"),
    "cachorro":  ("cachorro", "pet", "gato", "coleira", "raç", "comedouro"),
    "roupa":     ("roupa", "camisa", "vestido", "calça", "moda", "blusa",
                  "jaqueta", "casaco", "short"),
    "treino":    ("treino", "academ", "fitness", "muscula", "yoga", "corrida"),
    "academia":  ("treino", "academ", "fitness", "muscula", "yoga"),
    "corpo":     ("corpo", "fitness", "emagrec", "modelador", "massage"),
    "setup":     ("setup", "mouse", "teclado", "monitor", "notebook", "gamer",
                  "cadeira gamer", "headset"),
    "gadget":    ("gadget", "eletron", "usb", "bluetooth", "led", "smart"),
    "cabelo":    ("cabelo", "cabelud", "escova", "secador", "shampoo", "gloss"),
    "beleza":    ("beleza", "maquia", "batom", "blush", "pele", "unha", "gloss"),
    "mulher":    ("feminin", "vestido", "blush", "batom", "sandália", "bolsa"),
}


# As famílias de `_CONCRETO` que são NATIVAS de cada pool da reserva. Serve pra
# não rejeitar uma frase por falar do próprio assunto do nicho de onde ela veio.
_NATIVO_DO_NICHO = {
    "casa":     ("casa",),
    "cozinha":  ("cozinha", "cozinhar", "cozinhando"),
    "beleza":   ("beleza", "pele", "cabelo", "mulher"),
    "tech":     ("setup", "gadget", "celular"),
    "pets":     ("cachorro",),
    "moda":     ("roupa", "mulher"),
    "academia": ("treino", "academia", "corpo"),
}


def _conflita(frase: str, produto: str, nicho: str = "") -> bool:
    """A frase fala de uma coisa que o produto não é?

    'Meu celular vivia descarregando' + um mouse = a pessoa lê sobre bateria e
    vê um mouse. Ela não entende, e pula. Frase sem palavra concreta nunca
    conflita — e é por isso que a mais genérica da semana ('Vivia com um
    probleminha que ninguém resolvia') foi a de melhor alcance: ela serve
    qualquer produto.

    ⚠️ O NICHO DESARMA O CHOQUE, e sem ele a reserva emagrecia sozinha. O teste
    comparava a frase com o NOME do produto, e nome é um proxy ruim de assunto:
    "Organizador de Armário Dobrável" não contém a palavra "casa", então TODA
    frase do pool da casa que dizia "casa" era descartada — 11 de 14. Sobravam
    3 frases pra um nicho inteiro, e as mesmas 3 se repetiam. A frase veio do
    pool DA CASA; o assunto dela é o assunto do pool, por construção.

    Medido em 16/08: casa 3 → 14 frases utilizáveis com o mesmo produto.
    """
    f, p = frase.lower(), (produto or "").lower()
    nativas = _NATIVO_DO_NICHO.get(_chave_nicho(nicho), ()) if nicho else ()
    for palavra, parentes in _CONCRETO.items():
        if palavra in nativas:
            continue
        if palavra in f and not any(r in p for r in parentes):
            return True
    return False


def _cabe_no_formato(h: str) -> bool:
    """A mesma regra que o _limpar_saida aplica na saída do Gemini.

    Ela existia só lá, e a reserva passava por fora — foi assim que saíram
    posts com 3 linhas ('Meu celular vivia descarregando na pior hora' tem 45
    caracteres, o teto é 40, e ainda vinha o 'A Shopee:' embaixo).
    """
    if "{tag}" in h or "\n" in h:
        frase = h.split("{tag}")[0].split("\n")[0]
        return len(_EMOJI_RX.sub("", frase).strip()) <= int(
            os.environ.get("HOOK_MAX_L1", 40))
    return len(_EMOJI_RX.sub("", h).strip()) >= int(
        os.environ.get("HOOK_MIN_CHARS", 44))


# ── A REGRA DA AVA YUERGENS, num lugar só ───────────────────────────────────
# "O gancho é um filtro. Se você filtrar muita gente no começo, o algoritmo
# entende que aquele vídeo é ruim e não distribui pra mais pessoas."
#
# Estas são as marcas de PORTA: construções que exigem o espectador PERTENCER a
# um grupo pra continuar assistindo. O `analise_retencao` IMPORTA daqui em vez
# de copiar — régua duplicada vira duas réguas diferentes na primeira edição.
#
# ⚠️ AMPLO NÃO É GENÉRICO. No exemplo dela, "se você tem um golden que come
# tudo" vira "quer um cachorro que não come nada do chão?" — continua sendo
# sobre cachorro. Sobe UM degrau, não até "todo mundo".
PORTAS_DE_PUBLICO = (
    "se voce tem", "se voce e ", "se voce trabalha", "se voce sofre",
    "se voce usa", "se voce ama", "se vc tem",
    "pra quem ", "para quem ", "com quem ",
    "quem tem ", "quem ama ", "quem gosta", "quem usa ", "quem sofre",
    "toda pessoa que", "todo mundo que", "todas que ", "todos que ",
    "dona de ", "donas de ", "dono de ", "donos de ", "mae de ", "maes de ",
)


def _sem_acento(t: str) -> str:
    t = (t or "").lower()
    for a, b in (("á", "a"), ("â", "a"), ("ã", "a"), ("à", "a"), ("é", "e"),
                 ("ê", "e"), ("í", "i"), ("ó", "o"), ("ô", "o"), ("õ", "o"),
                 ("ú", "u"), ("ç", "c")):
        t = t.replace(a, b)
    return " " + " ".join(t.split()) + " "


def filtra_publico(hook: str) -> str:
    """A porta que o hook fecha, ou "" se ele não fecha nenhuma.

    Devolve o TRECHO encontrado (não um booleano) porque quem rejeita precisa
    dizer ao modelo o que exatamente reescrever — "seu hook está estreito" não
    ensina nada; "você escreveu 'pra quem'" ensina.
    """
    t = _sem_acento(hook)
    for p in PORTAS_DE_PUBLICO:
        if p in t:
            return p.strip()
    return ""


def _fallback(nicho: str, produto: str = "") -> str:
    pool = HOOKS_RESERVA.get(_chave_nicho(nicho)) or HOOKS_RESERVA["geral"]
    # 1) formato: nada que renderize em 3 linhas
    pool = [h for h in pool if _cabe_no_formato(h)] or pool
    # 1b) MESMA REGRA DO GERADOR (16/08, pedido do Dre: "a reserva tem que ser
    # tão boa quanto o conteúdo normal"). Antes disto, 21 das 107 frases do
    # banco FECHAVAM a porta ("não mostre isso pra quem…", "toda pessoa
    # que…") — exatamente a forma que o gerador passou a rejeitar. O Gemini
    # caía e o vídeo saía com o hook que a regra nova proíbe, sem ninguém ver.
    #
    # ⚠️ FILTRO EM TEMPO DE USO, não só faxina no banco. Reescrever as 21 zera
    # HOJE; o filtro garante AMANHÃ, quando alguém adicionar uma frase nova
    # (o cabeçalho deste arquivo convida: "cresça à vontade"). Régua que só
    # roda no dia da limpeza não é régua.
    _abertas = [h for h in pool if not filtra_publico(h)]
    if _abertas:
        pool = _abertas
    else:
        # não silencio: cair aqui significa que o nicho inteiro está estreito
        log.warning("reserva de %r: TODAS as frases fecham público — uso "
                    "mesmo assim, mas isso precisa ser corrigido no banco",
                    _chave_nicho(nicho))
    # 2) sentido: nada que fale de uma coisa que o produto não é
    sem_conflito = [h for h in pool if not _conflita(h, produto, nicho)]
    pool = sem_conflito or [h for h in pool if not any(
        w in h.lower() for w in _CONCRETO)] or pool
    # 3) variedade
    recentes = set(_ler_recentes())
    frescas = [h for h in pool if h not in recentes] or pool
    escolha = random.choice(frescas).replace("{tag}", TAG_PADRAO)
    _registrar(escolha)
    return escolha


def _limpar_saida(txt: str) -> Optional[str]:
    """Normaliza a saida do Gemini: tira markdown/rotulos, no maximo 2 linhas."""
    txt = (txt or "").strip()
    txt = txt.replace("```", "").replace("**", "")
    linhas = []
    for ln in txt.split("\n"):
        ln = ln.strip()
        ln = re.sub(r"^(linha\s*\d+\s*[:\-]|[-*•]\s*)", "", ln, flags=re.I).strip()
        if ln:
            linhas.append(ln)
        if len(linhas) == 2:
            break
    if not linhas:
        return None
    # se veio em 2 linhas mas a 2a NAO e uma tag (nao termina com ":"), o \n foi
    # quebra ARTIFICIAL no meio de uma frase unica -> junta e deixa o render quebrar
    # por largura (o emoji vai pro fim da ULTIMA linha, nao pro meio do hook).
    if len(linhas) == 2 and not linhas[1].rstrip().endswith(":"):
        linhas = [" ".join(linhas)]
    # GARANTE 2 LINHAS no video (formato TopShop e GRANDE — hook curto fica pequeno):
    #   • frase UNICA (1 linha): precisa ser LONGA o bastante pra QUEBRAR em 2.
    #   • frase + TAG (2 linhas): a frase precisa CABER em 1 linha (senao vira 3L).
    _min  = int(os.environ.get("HOOK_MIN_CHARS", 44))   # piso da frase unica
    _maxL1 = int(os.environ.get("HOOK_MAX_L1", 40))     # teto da frase antes da tag
    _vis0 = len(_EMOJI_RX.sub("", linhas[0]).strip())
    if len(linhas) == 1:
        if _vis0 < _min:            # 1 linha curta -> nao enche 2 linhas -> rejeita
            return None
    else:                           # frase + tag
        if _vis0 > _maxL1:          # frase longa -> quebraria e viraria 3 linhas -> rejeita
            return None
    return "\n".join(linhas)


def _hooks_vencedores(n: int = 4) -> list:
    """Os hooks das NOSSAS contas que MAIS alcançaram (reach_agent → reach.jsonl),
    pro Gemini APRENDER com os próprios vencedores. Só entra quem passou de um piso
    REAL (não ruído). Vazio se o dado ainda for ralo — aí o gerador segue como antes.
    Retorna [(hook, reach)]."""
    # DESLIGADO por padrão: a legenda passou a começar pela CURIOSIDADE (não pelo
    # hook), então a 1ª linha do caption no reach.jsonl não é mais o hook da tela —
    # aprender com ela poluiria o gerador. Religa com HOOK_LEARN=1 só se voltarmos
    # a cruzar reach × hook por outra fonte (ex.: ledger).
    if os.getenv("HOOK_LEARN", "0").strip().lower() not in ("1", "true", "sim"):
        return []
    try:
        por_id = {}
        for l in _REACH_JSONL.read_text(encoding="utf-8").splitlines():
            l = l.strip()
            if not l:
                continue
            r = json.loads(l)
            mid = r.get("media_id")
            if not mid or not isinstance(r.get("reach"), int):
                continue
            if r["reach"] >= por_id.get(mid, {}).get("reach", -1):
                por_id[mid] = r
        posts = list(por_id.values())
    except Exception:
        return []
    if len(posts) < 8:                       # dado ralo demais pra aprender (vira ruído)
        return []
    reaches = sorted(p["reach"] for p in posts)
    mediana = reaches[len(reaches) // 2] or 0
    piso = max(int(os.getenv("HOOK_REACH_PISO", 150)), int(mediana * 1.5))
    venc = sorted((p for p in posts if p["reach"] >= piso),
                  key=lambda p: p["reach"], reverse=True)
    hooks, vistos = [], set()
    for p in venc:
        cap = (p.get("caption") or "").strip()
        # a legenda começa com o HOOK ("hook\n\ndesenvolvimento") → pega a 1ª parte
        hook = re.split(r"\n\n|\n", cap)[0].strip()
        chave = _EMOJI_RX.sub("", hook).strip().lower()
        if hook and len(hook) > 8 and chave not in vistos:
            vistos.add(chave)
            hooks.append((hook, p["reach"]))
        if len(hooks) >= n:
            break
    return hooks


def _via_gemini(produto: str, descricao: str, nicho: str) -> Optional[str]:
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        log.warning("GEMINI_API_KEY ausente — HOOK sai do banco de reserva")
        return None
    try:
        from google import genai
        cli = genai.Client(api_key=key)
        _amplo = os.environ.get("HOOK_AMPLO", "1").strip().lower() not in (
            "0", "false", "nao", "não")
        # mostra um SUBCONJUNTO aleatorio das formulas (forca variedade entre posts)
        # ⚠️ SORTEIO UNIFORME DESPERDIÇAVA A MEDIÇÃO. Eram 10 moldes, só 4 em
        # 1ª pessoa, e `random.sample` os tratava como iguais — então ~60% do
        # que o modelo via vinha de moldes que os 133 posts dizem render 2-3×
        # menos. Agora a amostra GARANTE 3 de 1ª pessoa e deixa 2 vagas pros
        # outros.
        #
        # E ficam 2 vagas de propósito, em vez de forçar 5/5: se o gerador só
        # puder produzir 1ª pessoa, ninguém nunca mede se isso continua sendo
        # verdade. Sem variação não há aprendizado — e a medição de 08/08 é de
        # uma semana atrás, não é lei da natureza.
        _pp = [f for f in FORMULAS if f[0] in PRIMEIRA_PESSOA]
        _outros = [f for f in FORMULAS if f[0] not in PRIMEIRA_PESSOA]
        # ⚠️ NAO MOSTRE O QUE VOCE ACABOU DE PROIBIR. `alerta_exclusao` ("Nao
        # mostre isso pra quem <X>") e `necessidade` ("Toda pessoa que <X>")
        # sao LITERALMENTE as construcoes que a regra proibe — e o sorteio
        # podia colocar as duas na frente do modelo como "exemplo de tom", na
        # mesma mensagem que dizia pra nunca escrever aquilo. Instrucao
        # contraditoria: o exemplo concreto ganha da proibicao abstrata quase
        # sempre. Filtrado pela MESMA funcao que julga a saida, entao molde
        # novo que feche porta ja nasce excluido.
        if _amplo:
            _pp = [f for f in _pp if not filtra_publico(f[1])]
            _outros = [f for f in _outros if not filtra_publico(f[1])]
        amostra = (random.sample(_pp, k=min(3, len(_pp)))
                   + random.sample(_outros, k=min(2, len(_outros))))
        random.shuffle(amostra)
        moldes = "\n".join(f"- {nome}: {molde.replace('{tag}', TAG_PADRAO)}"
                           for nome, molde in amostra)
        # APRENDE COM OS PRÓPRIOS VENCEDORES: injeta os hooks que MAIS alcançaram nas
        # nossas contas, pro Gemini seguir o espírito do que JÁ funcionou aqui.
        _venc = _hooks_vencedores(4)
        bloco_venc = ""
        if _venc:
            _lst = "\n".join(f'- "{h}" (alcancou {rc} pessoas)' for h, rc in _venc)
            bloco_venc = (
                "IMPORTANTE — estes hooks das NOSSAS contas foram os que MAIS "
                "ALCANCARAM pessoas de verdade. Gere no MESMO espirito/energia deles "
                "(o que ja funcionou AQUI), mas sob medida pra ESTE produto, sem "
                "copiar:\n" + _lst + "\n\n")
        # ⚠️ PRINCIPIO NO LUGAR DE CATALOGO (16/08, pedido do Dre).
        # O catalogo de FORMULAS e um conjunto de formas EMPRESTADAS de outros
        # perfis, e ele tem um teto: o gerador so sabe preencher o que ja esta
        # na lista. O pedido foi outro -- "o proprio jarvis ira fazer os hooks".
        # Entao o modelo recebe a REGRA (a da Ava Yuergens) e escreve; os
        # moldes viram EXEMPLO de tom, nao gabarito a preencher.
        # ⚠️ AMPLO NAO E "TIRAR O 'PRA QUEM'" -- correcao do Dre em 16/08, e ele
        # esta certo. A 1a versao desta regra so PROIBIA a construcao que fecha
        # porta. Proibicao nao produz amplitude: da pra obedecer a regra inteira
        # e escrever "Odeio bone que amassa o cabelo!", que nao fecha porta
        # nenhuma e continua estreito de assunto. No exemplo dele a frase INTEIRA
        # muda -- outro vocabulario, outra estrutura, o substantivo sobe um
        # degrau. Por isso agora o modelo ve PARES de transformacao, nao uma
        # lista de proibicoes: exemplo negativo ensina o que nao fazer, exemplo
        # PAREADO ensina o que fazer no lugar.
        regra_ava = (
            "COMO ESCREVER UM GANCHO AMPLO (a regra que importa)\n"
            "Nao e 'tirar a palavra pra quem'. E REESCREVER A FRASE INTEIRA em\n"
            "outro vocabulario. Faca estes 3 movimentos:\n\n"
            "  (1) Troque QUEM A PESSOA E  ->  pelo QUE ELA QUER.\n"
            "  (2) Suba o substantivo UM DEGRAU (golden -> cachorro; base ->\n"
            "      maquiagem; air fryer -> jantar). Um degrau, nao ate 'todo\n"
            "      mundo': continua sendo do mesmo assunto.\n"
            "  (3) Feche com promessa de metodo ou resultado ('siga esses\n"
            "      passos', 'em 5 minutos', 'sem gastar quase nada').\n\n"
            "VEJA A FRASE INTEIRA MUDAR:\n"
            "  ESTREITO: 'se voce tem um golden que come tudo, ensino isso'\n"
            "  AMPLO   : 'quer um cachorro que nao come nada do chao sem a sua\n"
            "             permissao? siga esses passos'\n\n"
            "  ESTREITO: 'pra quem tem cabelo cacheado que vive embaracado'\n"
            "  AMPLO   : 'da pra desembaracar o cabelo em 5 minutos sem brigar\n"
            "             com ele todo santo dia'\n\n"
            "  ESTREITO: 'toda pessoa que cozinha todo dia precisa disso'\n"
            "  AMPLO   : 'o jantar de todo dia pode sujar metade da louca'\n\n"
            "Repare: nenhuma palavra da versao estreita sobrevive. Nao e a\n"
            "mesma frase sem o recorte -- e OUTRA frase, sobre o RESULTADO.\n\n"
            "VAGO NAO E AMPLO. 'meu setup vivia um caos de fios' nao fecha porta\n"
            "e tambem nao chama ninguem: nao promete nada. Amplo = alcanca muita\n"
            "gente E da um motivo pra ficar.\n\n"
            "1a pessoa e BEM-VINDA como TOM, se cumprir os 3 movimentos:\n"
            "  'Nunca imaginei que aplicar base fosse tao rapido e sem sujeira'\n\n"
            "PROIBIDO: 'pra quem', 'para quem', 'quem tem', 'quem ama',\n"
            "'se voce tem', 'se voce e', 'toda pessoa que', 'todo mundo que'.\n\n")
        prompt = (
            "Voce e copywriter de videos virais de afiliado (Shopee), estilo das "
            "criadoras que mais vendem no Reels/TikTok. Crie UM gancho (hook) "
            "curtissimo pro produto abaixo, que faca a pessoa PARAR de rolar.\n\n"
            f"{bloco_venc}"
            + (regra_ava +
               "Os exemplos abaixo servem de TOM, nao de formulario -- nao "
               "preencha lacuna, ESCREVA um gancho novo pra este produto:\n"
               f"{moldes}\n\n"
               if _amplo else
               "Escolha a FORMULA que melhor combina com ESTE produto (adapte, nao "
               "copie literal). Formulas disponiveis:\n"
               f"{moldes}\n\n")
            + "REGRAS:\n"
            "- Responda APENAS o hook, nada mais (sem explicar, sem aspas em volta "
            "de tudo, sem hashtag, sem markdown).\n"
            "- O hook DEVE ocupar 2 LINHAS no video: OU uma frase relatable/curiosidade "
            "com CORPO (~8 a 12 palavras, que encha 2 linhas), OU frase + tag curta na "
            "2a linha (ex.: a frase com emoji na 1a linha e '" + TAG_PADRAO + "' na 2a).\n"
            "- NAO faca hook curto que caiba em 1 linha so (fica pequeno no nosso formato).\n"
            "- Se a formula tiver 2 partes, use 2 linhas (a 2a linha curtinha).\n"
            "- 1a pessoa, tom de desabafo/humor/curiosidade. Portugues BR.\n"
            "- NAO cite o nome do produto. Termine a frase principal com 1 emoji "
            "que combine.\n\n"
            f"Produto: {produto}\n"
            f"Descricao: {(descricao or '')[:300]}\n"
        )
        # ⚠️ VERIFICAR A SAIDA, NAO CONFIAR NA INSTRUCAO. Mandar "nunca escreva
        # 'pra quem'" no prompt nao garante nada -- modelo desobedece, e a
        # desobediencia sai calada direto pro video. A regra so vale se ela for
        # CHECADA depois. Uma retentativa com o trecho exato que violou; se
        # insistir, cai na reserva (que e ruim, mas e ruim de forma conhecida).
        for tentativa in (1, 2):
            r = cli.models.generate_content(
                model="gemini-2.5-flash",
                contents=[{"parts": [{"text": prompt}]}],
            )
            hook = _limpar_saida(getattr(r, "text", "") or "")
            if not _amplo or not hook:
                return hook
            porta = filtra_publico(hook)
            if not porta:
                return hook
            log.info("hook fechou publico com %r — reescrevendo (%d/2)",
                     porta, tentativa)
            if tentativa == 2:
                # ⚠️ devolve None (nao o hook estreito): passar adiante o que a
                # regra acabou de reprovar transformaria a checagem em teatro.
                log.warning("hook seguiu estreito (%r) apos 2 tentativas — "
                            "vai pra reserva", porta)
                return None
            prompt += (f"\nATENCAO: sua resposta anterior usava \"{porta}\", que "
                       f"FECHA a porta pra quem nao pertence a esse grupo. "
                       f"Reescreva SEM essa construcao, mantendo a promessa.\n")
        return None
    except Exception as erro:
        log.warning("Gemini falhou no HOOK (%s: %s) — usando reserva",
                    type(erro).__name__, str(erro)[:140])
        return None


def _proibido(hook: str):
    """O motivo, se este hook viola uma regra MEDIDA. None se estiver limpo.

    ⚠️ A LISTA VEM DO `storyboard.py`, IMPORTADA — não copiada. Duas ideias do
    que é proibido é o mesmo que nenhuma: a cópia envelhece, alguém corrige um
    lado, e o outro segue publicando o que já foi medido como ruim.

    O buraco que isto fecha (15/08): o `storyboard.PROIBIDO` bane "corre
    ver/que/pra" com o número do lado ("1,8 a 2,2%, contra 3,8 a 5,1% dos de
    1ª pessoa") — mas só valia no caminho autoral, que não roda. Enquanto
    isso, "corre ver isso antes" estava no ar, com 6 posts medidos.
    """
    try:
        import storyboard as SB
        regras = SB.PROIBIDO
    except Exception:
        return None          # sem a regra, não invento uma: deixo passar
    for padrao, motivo in regras:
        if padrao.search(hook or ""):
            return motivo
    return None


def gerar_hook_alana(produto: str, descricao: str = "", nicho: str = "") -> str:
    """Retorna hook viral (1-2 linhas, varias formulas). Tenta Gemini
    (HOOK_ALANA=1 + key); senao usa o banco de reserva por nicho."""
    ligado = os.getenv("HOOK_ALANA", "1").strip().lower() in ("1", "true", "sim")
    if ligado:
        for tentativa in range(2):        # 2, não infinitas: cada uma é 1 chamada
            via = _via_gemini(produto, descricao, nicho)
            if not via:
                break
            motivo = _proibido(via)
            if not motivo:
                _registrar(via)
                return via
            log.warning('hook recusado (%s): "%s" — %s',
                        f"tentativa {tentativa + 1}", via.splitlines()[0][:60],
                        motivo)
    # a reserva também passa pela regra: banco antigo pode ter frase banida
    reserva = _fallback(nicho, produto)
    motivo = _proibido(reserva)
    if motivo:
        log.warning('reserva também recusada ("%s" — %s); usando 1ª pessoa '
                    'genérica', reserva.splitlines()[0][:50], motivo)
        return 'Comprei sem esperar nada e me surpreendeu demais 😅'
    return reserva


# ═════════════════════════════════════════════════════════════════════════════
# LEGENDA DE CURIOSIDADE (o padrão dos perfis que MAIS vendem)
# Legenda que ENSINA/curioseia sobre o produto → a pessoa SALVA e COMPARTILHA →
# save/share é dos maiores sinais de ALCANCE do Instagram. É diferente do hook
# (que é o texto na TELA do vídeo): a curiosidade vai na LEGENDA, embaixo.
# ═════════════════════════════════════════════════════════════════════════════

# Reserva por nicho (quando o Gemini cai). {nome} = nome curto do produto.
# Tom: "pouca gente sabe que…", agrega valor, claim SUAVE (nada de promessa
# médica/absoluta), 1 emoji no fim. 2-4 frases.
LEGENDAS_RESERVA = {
    "casa": [
        "Pouca gente repara, mas viver num ambiente organizado reduz o cansaço "
        "mental do dia — o cérebro relaxa mais fácil sem bagunça visual pra "
        "processar. Um detalhe simples como {nome} já ajuda a manter tudo no "
        "lugar sem esforço. 🏡",
        "Tem um motivo pra casa arrumada dar aquela sensação de leveza: menos "
        "estímulo desorganizado à vista, menos tensão acumulada no fim do dia. "
        "É aí que {nome} faz diferença no dia a dia. 🌿",
    ],
    "cozinha": [
        "Poucas pessoas sabem, mas ter as coisas certas à mão na cozinha faz o "
        "preparo render bem mais — menos tempo procurando, menos bagunça, mais "
        "vontade de cozinhar. {nome} resolve exatamente esse detalhe. 🍳",
        "O segredo de quem cozinha sem estresse quase nunca é talento: é ter o "
        "utensílio certo pra cada tarefa. {nome} é um desses que você não sabia "
        "que precisava. 👩‍🍳",
    ],
    "beleza": [
        "Muita gente não percebe, mas constância importa mais que produto caro "
        "no cuidado com a pele e o cabelo — pequenos hábitos diários é que "
        "aparecem no espelho. {nome} deixa esse cuidado mais fácil de manter. ✨",
        "Autocuidado não precisa ser complicado: às vezes é só o item certo "
        "pra transformar a rotina numa coisa gostosa de fazer. É o caso de "
        "{nome}. 💆‍♀️",
    ],
    "tech": [
        "Pouca gente imagina o tanto de tempo que a gente perde com pequenos "
        "perrengues do dia — cabo bagunçado, bateria acabando, celular sem "
        "apoio. {nome} é daqueles que resolve isso e você não larga mais. 🔌",
        "Nem sempre é a tecnologia mais cara que muda o dia: às vezes é um "
        "acessório simples e barato que facilita tudo. {nome} é um exemplo "
        "disso. 📱",
    ],
    "pets": [
        "Quem tem pet sabe: o bicho sente o ambiente. Pequenos cuidados no dia "
        "a dia deixam ele mais tranquilo e a casa mais limpa ao mesmo tempo. "
        "{nome} ajuda nos dois. 🐾",
        "Pouca gente comenta, mas metade do trabalho de cuidar de um pet é ter "
        "o item certo pra facilitar a rotina. {nome} é um desses que resolve. 🐶",
    ],
    "moda": [
        "Tem uma coisa que todo mundo que se arruma bem sabe: não é ter muita "
        "roupa, é ter as peças certas que combinam com tudo. {nome} é dessas "
        "que valorizam qualquer look. 👗",
        "Estilo é menos sobre tendência e mais sobre se sentir bem no que veste. "
        "Uma peça como {nome} resolve o look sem complicar. ✨",
    ],
    "academia": [
        "Pouca gente fala, mas constância no treino vem muito de reduzir "
        "atrito: quando o item certo tá ali pronto, fica mais fácil manter o "
        "hábito. {nome} ajuda nisso. 💪",
        "Resultado no treino é soma de pequenos detalhes — e ter o acessório "
        "certo é um deles. {nome} é simples e faz diferença na rotina. 🏋️",
    ],
    "geral": [
        "Pouca gente conhece, mas às vezes é um item simples e baratinho que "
        "resolve um probleminha que a gente carrega há anos sem nem perceber. "
        "{nome} é um desses achados. 👀",
        "Tem coisa que a gente só entende que precisava depois que tem: facilita "
        "o dia, custa pouco e você passa a usar toda hora. É o caso de {nome}. 😍",
    ],
}


def _limpar_legenda(txt: str) -> str:
    """Tira hashtag, markdown, aspas em volta e CTA que o Gemini às vezes cola."""
    t = (txt or "").strip()
    t = re.sub(r"[#*_`>]+", "", t)                       # markdown/hashtag
    t = re.sub(r"\b(link na bio|link da bio|garanta|corre[ ]?la|compre)\b.*$",
               "", t, flags=re.IGNORECASE | re.DOTALL)   # CTA vaza às vezes
    t = t.strip().strip('"').strip("'").strip()
    return t


# Reserva GENÉRICA no estilo informativo (quando o Gemini cai). Mesmo padrão dos
# perfis que vendem: abre com "Pouca gente...", 2 parágrafos, NÃO cita o produto,
# claim suave. Garante que a legenda sai informativa mesmo sem o Gemini.
LEGENDAS_RESERVA_INFO = [
    "Pouca gente imagina que os pequenos hábitos do dia a dia moldam muito mais o "
    "nosso bem-estar do que as grandes decisões. O corpo e a mente respondem à "
    "repetição, e é na constância que a diferença aparece.\n\nO mais curioso é que "
    "quase ninguém percebe isso acontecendo — só sente o resultado depois de um tempo.",

    "Pouca gente sabe que o ambiente ao nosso redor influencia diretamente o humor "
    "e a energia. Detalhes que parecem irrelevantes vão, aos poucos, mudando como a "
    "gente se sente dentro de casa.\n\nO mais curioso é que o cérebro registra essas "
    "mudanças mesmo sem a gente perceber conscientemente.",

    "Pouca gente imagina que a forma como a gente organiza as coisas afeta quanto de "
    "energia mental sobra pro resto do dia. Menos desordem à vista costuma significar "
    "menos cansaço no fim do dia.\n\nEm termos práticos, o cérebro gasta menos "
    "processando o que está bagunçado — e isso libera foco pro que importa.",

    "Pouca gente sabe que resolver um pequeno incômodo que a gente carrega há tempos "
    "costuma ter um efeito bem maior do que parece. O alívio não é só prático: ele "
    "mexe também com o humor.\n\nO mais curioso é que a gente só entende o tamanho do "
    "problema depois que ele deixa de existir.",
]


def _legenda_reserva(nome: str, nicho: str) -> str:
    return random.choice(LEGENDAS_RESERVA_INFO)


def _legenda_via_gemini(produto: str, descricao: str, nicho: str) -> Optional[str]:
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        log.warning("GEMINI_API_KEY ausente — LEGENDA sai do banco de reserva "
                    "(genérico, sem relação com o nicho)")
        return None
    try:
        from google import genai
        cli = genai.Client(api_key=key)
        prompt = (
            "Voce escreve a LEGENDA de um Reels. A legenda NAO vende: ela ENSINA "
            "uma CURIOSIDADE interessante ligada ao TEMA do produto. Esse formato "
            "'informativo' e o que faz o Instagram levar o video pro EXPLORAR mais "
            "rapido — a pessoa LE, SALVA e COMPARTILHA. E o padrao dos perfis que "
            "mais vendem.\n\n"
            "ESTRUTURA OBRIGATORIA — 2 paragrafos:\n"
            "- Paragrafo 1: comece EXATAMENTE com 'Pouca gente imagina que...' ou "
            "'Pouca gente sabe que...' e revele um efeito/fato surpreendente sobre "
            "o TEMA, com uma explicacao curta.\n"
            "- Paragrafo 2: comece com 'O mais curioso e que...' e aprofunde; "
            "inclua uma frase no formato 'Em termos de [area/ciencia], ...' com a "
            "conclusao.\n\n"
            "REGRAS:\n"
            "- Portugues BR, tom informativo e curioso (um 'voce sabia'), NADA "
            "comercial. NAO cite o produto, NAO fale em comprar/link/oferta/preco.\n"
            "- Curiosidade REAL e plausivel. Claim SUAVE ('costuma', 'pode', "
            "'tende a'). NUNCA prometa cura nem faca afirmacao medica categorica.\n"
            "- Responda SO os 2 paragrafos: sem titulo, sem hashtag, sem CTA, sem "
            "a palavra 'Publi', sem aspas, sem markdown, sem emoji.\n\n"
            f"Tema/Produto: {produto}\n"
            f"Descricao: {(descricao or '')[:300]}\n"
            f"Nicho: {nicho or 'geral'}\n"
        )
        r = cli.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"parts": [{"text": prompt}]}],
        )
        out = _limpar_legenda(getattr(r, "text", "") or "")
        # sanidade: precisa ter corpo (senao cai pra reserva)
        if len(out) < 80:                        # 2 parágrafos: exige corpo
            log.warning("Gemini devolveu legenda curta demais (%d chars) — "
                        "usando reserva", len(out))
            return None
        return out
    except Exception as erro:
        log.warning("Gemini falhou na LEGENDA (%s: %s) — usando reserva",
                    type(erro).__name__, str(erro)[:140])
        return None


def gerar_legenda_curiosidade(produto: str, descricao: str = "",
                              nicho: str = "") -> str:
    """Retorna 1 paragrafo de curiosidade pra legenda. Tenta Gemini
    (LEGENDA_CURIOSIDADE=1 + key); senao usa o banco de reserva por nicho."""
    ligado = os.getenv("LEGENDA_CURIOSIDADE", "1").strip().lower() in (
        "1", "true", "sim")
    if ligado:
        via = _legenda_via_gemini(produto, descricao, nicho)
        if via:
            return via
    return _legenda_reserva(produto, nicho)


if __name__ == "__main__":
    # teste rapido: python hook_alana.py "Produto" nicho  [N]
    import sys
    prod = sys.argv[1] if len(sys.argv) > 1 else "Passadeira Ferro a Vapor"
    nic = sys.argv[2] if len(sys.argv) > 2 else "casa"
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    for i in range(n):
        print(f"--- {i+1} ---")
        print(gerar_hook_alana(prod, nicho=nic))
        print("LEGENDA:", gerar_legenda_curiosidade(prod, nicho=nic))
