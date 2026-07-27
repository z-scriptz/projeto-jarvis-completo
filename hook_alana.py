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

TAG_PADRAO = os.environ.get("HOOK_ALANA_TAG", "A Shopee:")

_RECENTES_PATH = Path(__file__).resolve().parent / "hooks_alana_recentes.json"
_RECENTES_MAX = 80

# ─────────────────────────────────────────────────────────────────────────────
# CATALOGO DE FORMULAS VIRAIS (moldes). O Gemini escolhe a que combina com o
# produto e preenche. {tag} vira "A Shopee:" (ou HOOK_ALANA_TAG). Adicione as suas!
#   - use "\n" onde o hook tem 2 partes (linha 1 / linha 2)
#   - <...> = o que o Gemini preenche pensando no produto
#   - <emoji> = 1 emoji que combine (ele escolhe)
# ─────────────────────────────────────────────────────────────────────────────
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
        'Não mostre isso pra quem ama deixar a casa sempre organizada 👀',
        'Toda pessoa que sofre com bagunça dentro de casa precisa ver isso 🙌',
        'Pov: a comprinha baratinha que transformou a minha casa inteira 😍',
        'Eu não sabia que precisava disso até deixar minha casa impecável 🤯',
        'O segredo pra deixar a casa sempre cheirosa que ninguém te conta 🤫',
        'Comprei sem esperar nada e resolveu um problema que eu tinha há anos 😱',
        'Corre ver isso antes que acabe, tá baratinho demais na promoção 🏃‍♀️',
        'Você organizando a sua casa do jeito difícil esse tempo todo 😅',
        'Presente perfeito pra quem acabou de se mudar pra casa nova 🏡',
        'Isso deixou minha casa com cara de apartamento de revista 😍',
        'Parei de gastar à toa depois que achei esse achadinho pra casa 💸',
    ],
    "cozinha": [
        '"Passo horas na cozinha à toa" 😮‍💨\n{tag}',
        '"Odiava perder tempo cozinhando" 😩\n{tag}',
        '"Minha cozinha vivia um caos na hora do almoço" 😫\n{tag}',
        'Não mostre isso pra quem passa o dia inteiro dentro da cozinha 👀',
        'Toda pessoa que cozinha todo santo dia precisa ter isso na cozinha 😍',
        'Pov: a melhor compra que fiz pra facilitar a minha cozinha 🍳',
        'Eu não sabia viver sem isso depois que testei aqui em casa 🤯',
        'O truque de cozinha que a minha avó queria ter conhecido antes 👵',
        'Comprei achando que era bobeira e virou meu queridinho da cozinha 😅',
        'Pare de perder tempo cozinhando do jeito mais difícil de todos 🛑',
        'Isso me economiza uns 30 minutos toda vez que eu vou cozinhar ⏱️',
        'Corre que esse achadinho de cozinha tá saindo baratinho demais 🏃‍♀️',
        'Presente perfeito pra quem ama cozinhar mas odeia a bagunça depois 🎁',
        'Ninguém me contou que existia isso e mudou minha cozinha inteira 🤫',
    ],
    "beleza": [
        '"Minha make vivia um caos total" 😩\n{tag}',
        '"Queria me sentir mais bonita" 🥺\n{tag}',
        '"Achava que pele linda era só de filtro" 😳\n{tag}',
        'Toda mulher que ama se cuidar e ficar linda precisa ter isso 😍',
        'Não mostre isso pra quem é viciada em skincare e maquiagem 👀',
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
        'Não mostre isso pra quem é apaixonado por tecnologia e gadget 👀',
        'Toda pessoa viciada em tecnologia precisa ter esse gadget agora 🔌',
        'Pov: o gadget que parece coisa do futuro bem na sua mão 🤯',
        'Eu não sabia que precisava disso até deixar meu setup impecável 😍',
        'O gadget que resolveu um problema que eu tinha há muito tempo 😱',
        'Comprei achando que era firula e hoje não vivo mais sem 😅',
        'Corre ver isso antes que esgote, tá baratinho demais pra função 🏃',
        'Você usando seu celular sem esse acessório ainda em 2026? 😬',
        'Presente perfeito pra quem é nerd e ama uma tecnologia nova 🎁',
        'Isso deixou meu setup com cara de gamer profissional na hora 🎮',
        'Parece caro mas foi um dos achadinhos mais baratos que já fiz 🤫',
    ],
    "pets": [
        '"Meu pet merecia muito mais" 🥺\n{tag}',
        '"Vivia sofrendo pra dar banho no meu cachorro" 😩\n{tag}',
        'Não mostre isso pra quem ama e cuida de cachorro dentro de casa 😱',
        'Toda pessoa que ama o seu pet como um filho precisa ter isso 🐶',
        'Pov: a comprinha barata que deixou o meu pet muito mais feliz 🐾',
        'Eu não sabia que precisava disso até ver a alegria do meu pet 🥹',
        'O segredo pra acabar com o pelo espalhado pela casa toda 🐕',
        'Comprei sem esperar nada e virou o brinquedo favorito dele 🎾',
        'Corre ver isso antes que acabe, todo dono de pet vai amar 🏃‍♀️',
        'Presente perfeito pra quem trata o cachorro como parte da família 🎁',
        'Isso salvou minha casa dos estragos do meu pet quando fico fora 😅',
        'Ninguém me contou que existia isso e facilitou a vida com o pet 🤫',
    ],
    "moda": [
        '"Nunca me sentia bem vestida" 🥲\n{tag}',
        '"Achava que roupa boa custava uma fortuna" 😳\n{tag}',
        'Não mostre isso pra quem ama se arrumar e se sentir linda 👀',
        'Toda mulher que quer se vestir bem sem gastar muito precisa ver 😍',
        'Pov: a peça que me devolveu a autoestima na hora de me arrumar 😍',
        'Eu não sabia que precisava disso até receber um monte de elogio 🥰',
        'O segredo pra montar look caro gastando pouquinho na Shopee 🤫',
        'Comprei sem fé e virou a peça que eu mais uso no guarda-roupa 😅',
        'Corre ver isso antes que acabe o estoque, tá voando na promoção 🏃‍♀️',
        'Você se vestindo bem sem gastar rios de dinheiro finalmente 💸',
        'Presente perfeito pra quem ama moda mas vive de olho no preço 🎁',
        'Isso valoriza qualquer corpo e disfarça o que a gente não gosta 😍',
    ],
    "academia": [
        '"Minhas costas vivem doendo o dia todo" 😩\n{tag}',
        '"Cansei de acordar todo travado de manhã" 😮‍💨\n{tag}',
        'Toda pessoa que treina pesado e sente muita dor precisa ter isso 💪',
        'Não mostre isso pra quem é viciado em treino e academia 👀',
        'Pov: o alívio que o meu corpo todo estava precisando há tempos 😮‍💨',
        'Eu não sabia que precisava disso até aliviar a dor na hora 😌',
        'O segredo pra recuperar o corpo mais rápido depois do treino 🤫',
        'Comprei achando que não ia funcionar e me arrependi de não ter antes 😅',
        'Corre ver isso, todo mundo que treina devia ter um em casa 🏃',
        'Presente perfeito pra quem vive na academia e sente dor depois 🎁',
        'Isso substituiu a massagem cara que eu pagava toda semana 💸',
    ],
    "geral": [
        '"Nunca imaginei precisar disso na vida" 😳\n{tag}',
        '"Vivia com um probleminha que ninguém resolvia" 😩\n{tag}',
        '"Achava que isso não ia funcionar de jeito nenhum" 🤨\n{tag}',
        'Não mostre isso pra quem ama economizar e achar promoção 👀',
        'Toda pessoa que ama um bom achadinho baratinho precisa ver isso 🤫',
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


def _fallback(nicho: str) -> str:
    pool = HOOKS_RESERVA.get(_chave_nicho(nicho)) or HOOKS_RESERVA["geral"]
    pool = [h for h in pool if _eh_2linhas(h)] or pool   # só entradas de 2 linhas
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


def _via_gemini(produto: str, descricao: str, nicho: str) -> Optional[str]:
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return None
    try:
        from google import genai
        cli = genai.Client(api_key=key)
        # mostra um SUBCONJUNTO aleatorio das formulas (forca variedade entre posts)
        amostra = random.sample(FORMULAS, k=min(5, len(FORMULAS)))
        moldes = "\n".join(f"- {nome}: {molde.replace('{tag}', TAG_PADRAO)}"
                           for nome, molde in amostra)
        prompt = (
            "Voce e copywriter de videos virais de afiliado (Shopee), estilo das "
            "criadoras que mais vendem no Reels/TikTok. Crie UM gancho (hook) "
            "curtissimo pro produto abaixo, no estilo curiosity-gap que faz a "
            "pessoa PARAR de rolar e comentar.\n\n"
            "Escolha a FORMULA que melhor combina com ESTE produto (adapte, nao "
            "copie literal). Formulas disponiveis:\n"
            f"{moldes}\n\n"
            "REGRAS:\n"
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
        r = cli.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"parts": [{"text": prompt}]}],
        )
        return _limpar_saida(getattr(r, "text", "") or "")
    except Exception:
        return None


def gerar_hook_alana(produto: str, descricao: str = "", nicho: str = "") -> str:
    """Retorna hook viral (1-2 linhas, varias formulas). Tenta Gemini
    (HOOK_ALANA=1 + key); senao usa o banco de reserva por nicho."""
    ligado = os.getenv("HOOK_ALANA", "1").strip().lower() in ("1", "true", "sim")
    if ligado:
        via = _via_gemini(produto, descricao, nicho)
        if via:
            _registrar(via)
            return via
    return _fallback(nicho)


if __name__ == "__main__":
    # teste rapido: python hook_alana.py "Produto" nicho  [N]
    import sys
    prod = sys.argv[1] if len(sys.argv) > 1 else "Passadeira Ferro a Vapor"
    nic = sys.argv[2] if len(sys.argv) > 2 else "casa"
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    for i in range(n):
        print(f"--- {i+1} ---")
        print(gerar_hook_alana(prod, nicho=nic))
