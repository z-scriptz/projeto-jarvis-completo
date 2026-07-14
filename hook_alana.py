#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# hook_alana.py -- GERADOR DE HOOK estilo Alana ("frase relatable + A Shopee:").
#
# Formato viral que CONVERTE (o que faz a pessoa parar e comentar):
#     Linha 1:  "<dor/desejo do dia a dia em 1ª pessoa>" <emoji>
#     Linha 2:  A Shopee:
# Ex.:  "Não aguento mais varrer o quintal 😩"
#       A Shopee:
#
# A frase é a DOR que o produto resolve — a 2ª linha ("A Shopee:") apresenta o
# produto que aparece no vídeo. Renderiza como 2 linhas (o narrated_video_agent
# respeita o "\n" e põe o emoji no fim da 1ª linha).
#
# Gerado por IA (Gemini) quando HOOK_ALANA=1 + GEMINI_API_KEY; senão cai num
# banco de frases relatable por categoria (nunca quebra a produção).
#
# Uso:
#     from hook_alana import gerar_hook_alana
#     hook = gerar_hook_alana("Passadeira Ferro a Vapor", descricao="...", nicho="casa")

import os
import re
import json
import random
from pathlib import Path
from typing import Optional

TAG_PADRAO = os.environ.get("HOOK_ALANA_TAG", "A Shopee:")

# memória curta pra não repetir a mesma frase no feed
_RECENTES_PATH = Path(__file__).resolve().parent / "hooks_alana_recentes.json"
_RECENTES_MAX = 30

# ── Banco de fallback: dor/desejo relatable por categoria (1ª pessoa) ─────────
# Sem IA, cobre quando o Gemini está off/fora do ar. {p} = nada (frases genéricas
# por tema). Emoji já embutido no fim.
_FALLBACK = {
    "casa": [
        "Minha casa vivia uma bagunça 😩", "Não aguento mais essa zona em casa 🥲",
        "Cansei de perder tudo pela casa 😮‍💨", "Minha casa precisando de um help 🙏",
    ],
    "cozinha": [
        "Passo horas na cozinha à toa 😩", "Cansei de perder tempo cozinhando 😮‍💨",
        "Minha cozinha uma bagunça sem fim 🥲", "Queria praticidade na cozinha 🙏",
    ],
    "beleza": [
        "Minha make vivia um caos 😩", "Cansei da pele sem vida 🥲",
        "Queria me arrumar mais rápido 😮‍💨", "Minha autoestima precisando de um up ✨",
    ],
    "tech": [
        "Meu setup vivia uma bagunça de fios 😩", "Cansei da tecnologia complicada 😮‍💨",
        "Queria um gadget que resolvesse 🙌", "Meu quarto sem graça nenhuma 🥲",
    ],
    "pets": [
        "Meu pet merecia mais 🥺", "Cansei de correr atrás do meu bicho 😩",
        "Queria facilitar a vida do meu pet 🐶",
    ],
    "moda": [
        "Nunca me sentia bem na roupa 🥲", "Queria me vestir melhor sem esforço 😍",
        "Cansei de não gostar do espelho 😩",
    ],
    "academia": [
        "Cansei das dores nas costas 😩", "Meu corpo pedindo um alívio 😮‍💨",
        "Queria relaxar depois do treino 🙏",
    ],
    "geral": [
        "Não sabia que precisava disso 😳", "Cansei de viver sem isso 😩",
        "Como eu vivia sem isso? 🤯", "Queria ter achado isso antes 🥲",
        "Isso mudou meu dia a dia 😍",
    ],
}

# nicho reportado pela produção → chave do banco
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


def _fallback(nicho: str) -> str:
    chave = _NICHO_ALIAS.get((nicho or "").strip().lower(), "geral")
    pool = _FALLBACK.get(chave) or _FALLBACK["geral"]
    recentes = set(_ler_recentes())
    frescas = [f for f in pool if f not in recentes] or pool
    frase = random.choice(frescas)
    _registrar(frase)
    return f"{frase}\n{TAG_PADRAO}"


def _limpar_linha1(txt: str) -> Optional[str]:
    """Normaliza a saída do Gemini pra 1 frase curta com 1 emoji no fim."""
    txt = (txt or "").strip().strip('"').strip("*").strip()
    txt = re.sub(r"\s+", " ", txt)
    if not txt:
        return None
    # garante no máximo 1 emoji e que ele fique no FIM (o render põe no fim da linha)
    emojis = _EMOJI_RX.findall(txt)
    txt_sem = _EMOJI_RX.sub("", txt).strip().strip('"').strip()
    if not txt_sem:
        return None
    emo = emojis[0] if emojis else "😩"
    # frase curta demais/longa demais → deixa o chamador decidir (retorna do jeito)
    return f'"{txt_sem}" {emo}'


def _via_gemini(produto: str, descricao: str, nicho: str) -> Optional[str]:
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return None
    try:
        from google import genai
        cli = genai.Client(api_key=key)
        prompt = (
            "Você é copywriter de vídeos virais de afiliado no estilo da criadora "
            "Alana (Shopee). Crie UM gancho (hook) curtíssimo pro produto abaixo.\n\n"
            "FORMATO OBRIGATÓRIO — responda APENAS a Linha 1 (nada mais):\n"
            "Linha 1 = uma frase RELATABLE em 1ª pessoa, com a DOR ou desejo do dia a "
            "dia que ESTE produto resolve. Máximo 8 palavras, tom de desabafo/humor, "
            "termine com 1 emoji que combine (ex.: 😩 🥲 😮‍💨 🙃 🤯 😍).\n"
            "NÃO cite o nome do produto. NÃO use hashtag, aspas, markdown ou a palavra "
            "'Shopee'. Só a frase com o emoji no fim.\n\n"
            f"Produto: {produto}\n"
            f"Descrição: {(descricao or '')[:300]}\n"
        )
        r = cli.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"parts": [{"text": prompt}]}],
        )
        linha1 = _limpar_linha1(getattr(r, "text", "") or "")
        if not linha1:
            return None
        return f"{linha1}\n{TAG_PADRAO}"
    except Exception:
        return None


def gerar_hook_alana(produto: str, descricao: str = "", nicho: str = "") -> str:
    """Retorna hook 2-linhas 'frase relatable 😩\\nA Shopee:'.
    Tenta Gemini (se HOOK_ALANA=1 + key); senão banco por categoria."""
    ligado = os.getenv("HOOK_ALANA", "1").strip().lower() in ("1", "true", "sim")
    if ligado:
        via = _via_gemini(produto, descricao, nicho)
        if via:
            try:
                _registrar(via.split("\n")[0])
            except Exception:
                pass
            return via
    return _fallback(nicho)


if __name__ == "__main__":
    # teste rápido: python hook_alana.py "Passadeira a Vapor" casa
    import sys
    prod = sys.argv[1] if len(sys.argv) > 1 else "Passadeira Ferro a Vapor"
    nic = sys.argv[2] if len(sys.argv) > 2 else "casa"
    print(repr(gerar_hook_alana(prod, nicho=nic)))
    print("---\n" + gerar_hook_alana(prod, nicho=nic))
