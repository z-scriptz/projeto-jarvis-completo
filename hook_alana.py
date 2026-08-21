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
    # ⚠️ REESCRITO EM 21/08. O banco anterior era publicidade disfarçada de
    # gancho — 'Corre ver isso antes que acabe, tá baratinho demais', 'Pov: a
    # comprinha baratinha que transformou a minha casa'. O Dre: *"'corre ver
    # isso' é gramaticalmente errado, e não traz nenhum tipo de interesse na
    # pessoa, só é um anúncio"*. Ele estava certo, e a régua da Ava condena
    # isso: o gancho tem que ser AMPLO, e amplo não é vago nem é anúncio.
    #
    # O molde novo é: SITUAÇÃO RECONHECÍVEL → QUEBRA DE EXPECTATIVA.
    #   'A bagunça nunca foi preguiça, era falta de lugar'
    #   'O celular fica lento por motivo que não é o celular'
    # Nenhuma fecha público, nenhuma cita produto, nenhuma manda fazer nada.
    #
    # SAÍRAM AS ASPAS DE FALA e os emojis: '"Minha casa vivia uma bagunça" 😩'
    # vira depoimento, e depoimento já é um filtro de quem se identifica.
    # Afirmação direta alcança mais.
    #
    # ⚠️ ISTO É REDE DE SEGURANÇA, NÃO O PLANO. Frase fixa se repete, e hook
    # repetido perde força por melhor que seja. O certo é o Gemini gerar único
    # por vídeo — se estas aqui começarem a aparecer muito nos posts, o
    # problema é a geração estar caindo, não a reserva estar curta.
    "casa": [
        'A bagunça nunca foi preguiça, era falta de lugar\n{tag}',
        'O problema não é a casa pequena, é o espaço morto\n{tag}',
        'A casa fica maior sem ninguém mexer uma parede\n{tag}',
        'Descobri tarde que arrumar não precisa doer tanto\n{tag}',
        'Existe um jeito da casa parar de dar tanto trabalho',
        'Passei anos achando que casa arrumada dava trabalho',
        'Tem uma hora que a casa cansa a gente sem avisar',
        'Reparei que o cansaço de casa vem de detalhe bobo',
        'Levei anos pra entender por que a sala nunca rendia',
        'Tem coisa que resolve num dia o que incomoda há anos',
        'O que mais suja a casa é o que ninguém enxerga',
        'A casa muda quando uma coisa simples entra nela',
    ],
    "cozinha": [
        'A louça acumula porque a cozinha não ajuda\n{tag}',
        'Existe um motivo pra sempre faltar espaço na pia\n{tag}',
        'A gaveta de talher é onde a cozinha se perde\n{tag}',
        'A bancada vira uma bagunça sem ninguém perceber\n{tag}',
        'Cozinhar cansa mais pela bagunça do que pelo fogão',
        'Metade do tempo na cozinha a gente passa procurando',
        'A cozinha pequena rende quando para de brigar comigo',
        'Tem gente que cozinha rápido e não é por talento',
        'Comida boa começa antes da panela, na organização',
        'Passei a gostar de cozinhar quando parei de procurar',
        'Guardar comida errado estraga mais que cozinhar mal',
    ],
    "beleza": [
        'O que estraga o cabelo é a pressa do dia a dia\n{tag}',
        'Ninguém avisa que a pressa é a maior inimiga da pele\n{tag}',
        'A unha quebra por um motivo que ninguém investiga\n{tag}',
        'O perfume some rápido por causa de um detalhe bobo\n{tag}',
        'A pele muda mais com constância do que com produto novo',
        'Descobri tarde que cabelo bom é rotina, não sorte',
        'Tem um erro de rotina que quase todo mundo comete',
        'Minha pele mudou quando parei de fazer uma coisa',
        'Existe uma ordem certa e ela muda o resultado todo',
        'Cabelo bonito de vídeo tem mais preparo que produto',
        'Gastei anos com produto quando o problema era o método',
    ],
    "tech": [
        'O celular fica lento por motivo que não é o celular\n{tag}',
        'A bateria não acaba, ela é gasta sem a gente ver\n{tag}',
        'Ninguém conta que o carregador certo muda tudo\n{tag}',
        'O que trava o wifi normalmente está do lado dele\n{tag}',
        'Metade dos cabos que eu tinha em casa não servia',
        'Tem gadget que parece bobo até você usar uma semana',
        'O som ruim quase nunca é culpa do fone de ouvido',
        'Existe um jeito da mesa parar de virar ninho de fio',
        'Passei anos com a tela quebrando pelo mesmo motivo',
        'A tecnologia que resolve é a que some do caminho',
    ],
    "pets": [
        'O pelo espalha porque a casa não ajuda a recolher\n{tag}',
        'A comida do bicho estraga antes do que diz o pacote\n{tag}',
        'Cachorro ansioso quase sempre está entediado\n{tag}',
        'A unha do bicho é o que mais estraga o sofá\n{tag}',
        'Cachorro não faz bagunça por teimosia, é energia sobrando',
        'Descobri que meu gato dormia mal e eu nem via',
        'Bicho em apartamento precisa de rotina, não de espaço',
        'Tem um jeito de passear que cansa menos os dois',
        'O banho em casa deixou de ser guerra por um motivo',
        'Gato foge da água até descobrir que o problema era outro',
    ],
    "moda": [
        'A calça marca por um motivo que não é o seu corpo\n{tag}',
        'O sapato machuca por detalhe que dá pra resolver\n{tag}',
        'A camiseta perde a forma antes do tempo por descuido\n{tag}',
        'A roupa não fica ruim no corpo, fica ruim na medida',
        'Guarda-roupa cheio é o mais difícil de usar de manhã',
        'Existe uma peça que arruma o corpo inteiro sozinha',
        'Roupa boa é a que você não lembra que está usando',
        'Passei anos comprando roupa e usando as mesmas cinco',
        'Vestir bem é menos sobre peça e mais sobre encaixe',
        'O que envelhece um look não é a roupa, é o acabamento',
    ],
    "academia": [
        'Água sozinha não dá conta e ninguém explica direito\n{tag}',
        'A postura estraga o exercício antes dele começar\n{tag}',
        'O tênis errado desfaz o treino inteiro sem avisar\n{tag}',
        'O treino não rende quando o corpo não está pronto',
        'Descobri que a dor depois do treino tinha explicação',
        'Tem gente que treina menos e evolui mais, e não é sorte',
        'Passei a gostar de treinar quando parei de sofrer',
        'Recuperar é parte do treino e quase todo mundo pula',
        'Treinar em casa falha por falta de canto, não de vontade',
        'Levantar peso errado cansa mais e entrega menos',
    ],
    "geral": [
        'Ninguém repara nas coisas que funcionam bem\n{tag}',
        'O melhor conserto é o que você faz uma vez só\n{tag}',
        'O que parece frescura costuma ser o que resolve\n{tag}',
        'Tem coisa que a gente aguenta anos e resolve num dia',
        'Descobri que o incômodo pequeno é o que mais cansa',
        'Existe solução simples pro que parece problema grande',
        'A gente se acostuma com o que dá trabalho todo dia',
        'Passei anos improvisando o que já tinha jeito certo',
        'Tem detalhe que muda o dia inteiro e ninguém conta',
        'A pressa cria os problemas que a gente reclama depois',
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


def _bloco_nao_repita(quantos: int = 12) -> str:
    """Os últimos hooks que já foram ao ar, pro modelo não repetir.

    ⚠️ SEM ISTO O MODELO NÃO TEM COMO SABER (21/08). Cada chamada é
    independente: ele não lembra do que escreveu ontem, então converge
    naturalmente pras mesmas construções — foi assim que saíram dois hooks
    quase idênticos no mesmo dia ('Ninguém acredita que esse resultado veio de
    um achadinho' e 'Ninguém acredita quando eu falo o preço'). Não é falha do
    modelo: é falta de memória, e a memória está no `posts_ledger.jsonl`.

    Silencioso de propósito: se o ledger não existir ou vier ilegível, o
    prompt sai sem o bloco em vez de derrubar a geração. Hook repetido é
    ruim; hook nenhum é pior.
    """
    try:
        arq = BASE_DIR / "shared" / "posts_ledger.jsonl"
        linhas = arq.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return ""
    vistos, fora = set(), []
    for ln in reversed(linhas):
        if len(fora) >= quantos:
            break
        try:
            h = (json.loads(ln).get("hook") or "").split("\n")[0].strip()
        except Exception:
            continue
        chave = h.lower()[:40]
        if h and chave not in vistos:
            vistos.add(chave)
            fora.append(h)
    if not fora:
        return ""
    lista = "\n".join(f"  - {h[:70]}" for h in fora)
    return ("JA FORAM AO AR (nao repita nem faca variacao destes):\n"
            f"{lista}\n\n")


def _teto_l1() -> int:
    """Quantos caracteres cabem na 1ª linha do hook. DERIVADO, não cravado.

    ⚠️ O TETO DE 40 ESTAVA MATANDO TODO HOOK GERADO (medido em 21/08).
    O log de 18 a 20/08 tem uma rejeição atrás da outra, todas pela MESMA
    regra e todas por margem ridícula:

        a 1ª linha tinha 41 caracteres e o teto e 40 — vai pra reserva
        a 1ª linha tinha 42 … 43 … 44 … 45 … 46 … 50 … 51 …

    Nenhum hook do Gemini chegava ao vídeo. Todos caíam na reserva, que é o
    banco de frases prontas — e é por isso que o Dre olhou os posts novos e
    disse *"ainda é estilo Alana"*. Estava, literalmente: eram as frases do
    `HOOKS_RESERVA`, uma delas cópia exata.

    DE ONDE VINHA O 40. Medido: na largura útil de 970px (1080 − 2×55 de
    margem), no corpo 48, cabem ~40 caracteres. O número estava certo — pro
    corpo MÁXIMO.

    POR QUE ESTAVA ERRADO. O render NÃO usa corpo fixo: ele encolhe de
    `HK_FONT` (48) até `HK_FONT_MIN` (34) pra fazer caber. No corpo 34 cabem
    ~56 caracteres. Ou seja, a regra reprovava por não caber num tamanho que o
    render nem teria usado — ele teria diminuído a fonte e coberto tudo.

    Uma frase boa de 41 caracteres virava frase pronta de anúncio. Trocar
    conteúdo gerado por reserva genérica é o pior desfecho possível, e era o
    desfecho de TODOS os hooks desde 18/08.

    Agora sai da mesma conta que o render faz. 0.54 é a largura média de um
    caractere em fração do corpo, com folga sobre os 0.51 medidos — texto com
    muitas letras largas (M, W) não pode estourar.
    """
    try:
        larg = int(os.environ.get("HOOK_LARGURA_VIDEO", 1080))
        margem = int(os.environ.get("HK_MARGEM", 55))
        corpo = int(os.environ.get("HK_FONT_MIN", 34))   # o render encolhe até aqui
        cabe = int((larg - 2 * margem) / (corpo * 0.54))
    except Exception:
        cabe = 52
    return int(os.environ.get("HOOK_MAX_L1", cabe))


def _cabe_no_formato(h: str) -> bool:
    """A mesma regra que o _limpar_saida aplica na saída do Gemini.

    Ela existia só lá, e a reserva passava por fora — foi assim que saíram
    posts com 3 linhas ('Meu celular vivia descarregando na pior hora' tem 45
    caracteres, o teto é 40, e ainda vinha o 'A Shopee:' embaixo).
    """
    if "{tag}" in h or "\n" in h:
        frase = h.split("{tag}")[0].split("\n")[0]
        return len(_EMOJI_RX.sub("", frase).strip()) <= _teto_l1()
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


def _limpar_saida(txt: str, motivos: Optional[list] = None) -> Optional[str]:
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
    _maxL1 = _teto_l1()      # teto DERIVADO do que o render aguenta (ver _teto_l1)
    _vis0 = len(_EMOJI_RX.sub("", linhas[0]).strip())
    # ⚠️ `motivos` existe pra REJEIÇÃO PODER VIRAR PEDIDO. Antes isto só
    # devolvia None, e None caía direto na reserva — o modelo tinha escrito
    # algo aproveitável, errava o tamanho por 4 caracteres, e o vídeo saía com
    # frase fixa de banco. Medido em 16/08: "Não mostre isso pra quem ama
    # cabelo liso" tem 40 visíveis contra piso de 44, e virava fallback sem
    # ninguém pedir de novo. Quem chama usa o motivo pra reescrever o pedido.
    if len(linhas) == 1:
        if _vis0 < _min:            # 1 linha curta -> nao enche 2 linhas -> rejeita
            if motivos is not None:
                motivos.append(
                    f"seu hook tinha {_vis0} caracteres e o minimo e {_min}: "
                    f"ficou pequeno demais na tela. Escreva MAIS LONGO "
                    f"(~8 a 12 palavras), sem virar duas frases.")
            return None
    else:                           # frase + tag
        if _vis0 > _maxL1:          # frase longa -> quebraria e viraria 3 linhas -> rejeita
            if motivos is not None:
                motivos.append(
                    f"a 1a linha tinha {_vis0} caracteres e o teto e {_maxL1} "
                    f"quando existe uma 2a linha: encurte a 1a linha.")
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
        # ⚠️ DEFINICAO OPERACIONAL, NAO O ADJETIVO (21/08, pedido do Dre).
        # A versao anterior mandava "escreva um gancho amplo" e mostrava
        # transformacoes. Faltava dizer O QUE E amplo — e o Dre acertou o risco
        # em cheio: sem definicao, o modelo produz "Pequenas mudancas podem
        # transformar sua rotina". Isso e amplo, nao fecha porta nenhuma, e nao
        # vale nada. Amplitude sem concretude e so vagueza com boa reputacao.
        #
        # Tambem some daqui a instrucao antiga de "feche com promessa de metodo
        # ('siga esses passos')": aquilo e CTA, e CTA no gancho e anuncio. O
        # que prende nao e o convite, e a pergunta que fica na cabeca.
        # ⚠️ CTA NO GANCHO É KNOB, NÃO OPINIÃO (21/08).
        # O Dre disse que eu podia manter o 'siga esses passos' e que tinha se
        # confundido na própria regra. Só que a primeira intuição dele estava
        # certa pela régua da Ava — gancho amplo → valor estreito → CTA DE
        # NICHO: o CTA mora no fim, não no começo.
        #
        # O argumento que me convence é orçamento, não estilo: o gancho tem 52
        # caracteres. 'siga esses passos' come 17 — um terço — com palavras que
        # serviriam em qualquer vídeo do mundo. Trocar um terço do espaço por
        # algo genérico, em vez de uma cena concreta, é troca ruim.
        #
        # MAS ISSO É JULGAMENTO MEU, NÃO MEDIÇÃO. E desde 21/08 existe cadeia
        # de métricas por hook rodando (metricas_posts + a camada do vigia).
        # Então vira interruptor: HOOK_CTA=1 religa a promessa de método, e a
        # comparação passa a ser feita com alcance real em vez de gosto.
        _cta_ok = os.environ.get("HOOK_CTA", "0").strip().lower() in (
            "1", "true", "sim")
        regra_ava = (
            "O QUE E UM GANCHO AMPLO (definicao, nao adjetivo)\n"
            "Gancho amplo = uma frase que descreve uma SITUACAO, COMPORTAMENTO,\n"
            "INCOMODO, DESCOBERTA ou DESEJO reconhecivel por muita gente, SEM\n"
            "exigir que a pessoa pertenca a um subgrupo pra sentir curiosidade.\n\n"
            "PRECISA TER (as tres, juntas):\n"
            "  (1) CONCRETO: uma cena ou fato que da pra visualizar. Nada de\n"
            "      filosofia generica.\n"
            "  (2) PERGUNTA MENTAL: depois de ler, a pessoa quer saber 'como\n"
            "      assim?' ou 'e ai?'. Se nao abre pergunta, nao e gancho.\n"
            "  (3) LIGACAO REAL com o que o video mostra. Curiosidade que o\n"
            "      video nao cumpre vira decepcao e a pessoa sai.\n\n"
            "NAO PODE (cada uma destas reprova o gancho):\n"
            "  - comecar com 'Se voce...' ou qualquer recorte de publico;\n"
            "  - exigir raca, idade, profissao, tipo de cabelo, raca do animal;\n"
            "  - citar o produto pelo nome;\n"
            "  - parecer anuncio ('corre', 'aproveite', 'promocao', 'baratinho');\n"
            + ("  - trazer CTA de compra ('clica', 'arrasta', 'olha o link');\n"
               "    promessa de metodo ('siga esses passos', 'em 5 minutos') e\n"
               "    PERMITIDA, se sobrar espaco pra cena concreta antes dela;\n"
               if _cta_ok else
               "  - trazer CTA ('clica', 'arrasta', 'siga esses passos', 'olha o\n"
               "    link'). O gancho prende pela pergunta, nao pelo convite;\n")
            +
            "  - frase vazia de suspense ('voce nao vai acreditar', 'olha isso');\n"
            "  - ser generico a ponto de servir pra qualquer video.\n\n"
            "⚠️ AMPLO E VAGO NAO SAO A MESMA COISA. Este exemplo e amplo, nao\n"
            "fecha porta nenhuma, e mesmo assim e um gancho RUIM:\n"
            "     'Pequenas mudancas podem transformar sua rotina'\n"
            "Ruim porque nao mostra cena, nao abre pergunta e serviria pra\n"
            "qualquer video do mundo. Amplitude sem concretude nao vale nada.\n\n"
            "COMO CHEGAR LA — 2 movimentos:\n"
            "  (1) Troque QUEM A PESSOA E  ->  pelo QUE ELA VIVE.\n"
            "  (2) Suba o substantivo UM DEGRAU (golden -> cachorro; base ->\n"
            "      maquiagem; air fryer -> jantar). UM degrau, nao ate 'todo\n"
            "      mundo': continua sendo do mesmo assunto.\n\n"
            "VEJA A FRASE INTEIRA MUDAR:\n"
            "  ESTREITO: 'se voce tem um golden que come tudo do chao'\n"
            "  AMPLO   : 'Cachorro que come tudo do chao nao esta com fome'\n\n"
            "  ESTREITO: 'pra quem tem cabelo cacheado que vive embaracado'\n"
            "  AMPLO   : 'O cabelo embaraca mais pelo que a gente faz de noite'\n\n"
            "  ESTREITO: 'toda pessoa que cozinha todo dia precisa disso'\n"
            "  AMPLO   : 'Metade da louca do jantar nasce antes de cozinhar'\n\n"
            "Repare: nenhuma palavra da versao estreita sobrevive, e a versao\n"
            "ampla AFIRMA algo concreto que da vontade de conferir.\n\n"
            "1a pessoa e BEM-VINDA como TOM, se cumprir a definicao:\n"
            "  'Passei anos achando que casa arrumada dava trabalho'\n\n"
            "PROIBIDO LITERAL: 'pra quem', 'para quem', 'quem tem', 'quem ama',\n"
            "'se voce tem', 'se voce e', 'toda pessoa que', 'todo mundo que'.\n\n"
            f"{_bloco_nao_repita()}")
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
        # ⚠️ E A RETENTATIVA VALE PROS DOIS MOTIVOS DE REJEICAO, nao so pra
        # porta. Achado de 16/08 testando este caminho: hook reprovado por
        # FORMATO (curto demais, 1a linha longa demais) devolvia None e caia
        # direto na reserva -- sem ninguem pedir de novo. O modelo tinha
        # escrito algo aproveitavel e errado o tamanho por 4 caracteres, e o
        # video saia com frase fixa de banco. Isso explica parte dos 22% de
        # posts com hook de reserva medidos hoje.
        for tentativa in (1, 2):
            r = cli.models.generate_content(
                model="gemini-2.5-flash",
                contents=[{"parts": [{"text": prompt}]}],
            )
            motivos = []
            hook = _limpar_saida(getattr(r, "text", "") or "", motivos)
            queixa = ""
            if not hook:
                # sem motivo registrado = veio vazio/ilegivel, nada a explicar
                queixa = motivos[0] if motivos else ""
            elif _amplo:
                porta = filtra_publico(hook)
                if porta:
                    queixa = (f"voce usou \"{porta}\", que FECHA a porta pra "
                              f"quem nao pertence a esse grupo. Reescreva a "
                              f"FRASE INTEIRA falando do RESULTADO, nao de "
                              f"quem a pessoa e.")
            if hook and not queixa:
                return hook
            if not queixa:
                return None                     # saida vazia: nao ha o que pedir
            if tentativa == 2:
                # ⚠️ devolve None (nao o hook reprovado): passar adiante o que a
                # regra acabou de reprovar transformaria a checagem em teatro.
                log.warning("hook seguiu reprovado apos 2 tentativas (%s) — "
                            "vai pra reserva", queixa[:70])
                return None
            log.info("hook reprovado, reescrevendo (%d/2): %s",
                     tentativa, queixa[:70])
            prompt += f"\nATENCAO sobre a sua resposta anterior: {queixa}\n"
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
