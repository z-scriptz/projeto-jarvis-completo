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
_RECENTES_MAX = 40

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
        '"Minha casa vivia uma bagunça" 😩\n{tag}',
        'Pov: A melhor compra que fiz pra minha casa 😍',
        'Não mostre isso pra quem ama organização 👀',
        'Toda pessoa que odeia bagunça precisa ter isso 🙌',
    ],
    "cozinha": [
        '"Passo horas na cozinha à toa" 😮‍💨\n{tag}',
        'Pov: A melhor compra que fiz pra minha cozinha 🍳',
        'Toda pessoa que cozinha todo dia precisa ter isso 😍',
        'O segredo pra facilitar a cozinha que ninguém te conta 🤫',
    ],
    "beleza": [
        '"Minha make vivia um caos" 😩\n{tag}',
        'Toda mulher que ama maquiagem precisa ter isso 😍',
        'Pov: O achadinho que mudou minha rotina de beleza ✨',
        'O segredo do glow que ninguém te conta 🤫',
    ],
    "tech": [
        '"Meu setup vivia um caos de fios" 😩\n{tag}',
        'Pov: O gadget que parece coisa do futuro 🤯',
        'Não mostre isso pra quem ama tecnologia 👀',
        'Toda pessoa viciada em gadget precisa ter isso 🔌',
    ],
    "pets": [
        'Não mostre isso pra donos de cachorro 😱',
        '"Meu pet merecia mais" 🥺\n{tag}',
        'Toda pessoa que ama pet precisa ter isso 🐶',
    ],
    "moda": [
        '"Nunca me sentia bem na roupa" 🥲\n{tag}',
        'Pov: A peça que me deu autoestima de novo 😍',
        'O segredo pra se vestir melhor sem esforço 🤫',
    ],
    "academia": [
        '"Minhas costas vivem doendo" 😩\n{tag}',
        'Pov: O alívio que meu corpo precisava 😮‍💨',
        'Toda pessoa que treina precisa ter isso 💪',
    ],
    "geral": [
        '"Nunca imaginei que eu ia precisar disso" 😳\n{tag}',
        'Pov: A melhor compra que fiz esse mês 😍',
        'Não mostre isso pra quem gosta de gastar pouco 👀',
        'O achadinho que ninguém sabe que existe 🤫',
        'Comprei sem esperar nada e me surpreendeu demais 🤯',
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


def _fallback(nicho: str) -> str:
    pool = HOOKS_RESERVA.get(_chave_nicho(nicho)) or HOOKS_RESERVA["geral"]
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
    # nao deixa a 1a linha gigante (curiosity-gap e curto)
    if len(linhas[0]) > 90:
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
