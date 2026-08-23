#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# capa_ia.py — a CAPA INTEIRA gerada por IA, texto incluso.
#
# ⚠️ EU ESTAVA DESATUALIZADO, E O DRE CORRIGIU (22/08):
# *"vimos nas duas capas do chatgpt que ele montou a capa perfeitamente, com o
# texto exato, isso só depende de prompt"*. Ele está certo. Eu escrevi no
# `fundo_ia.py` que "a IA erra texto em português" — isso valia para os modelos
# de imagem de um ou dois anos atrás, e para o `flux/schnell` que eu mesmo
# escolhi, que é o modelo RÁPIDO E BARATO da família e o pior em tipografia.
# É a segunda vez nesta semana que meu conhecimento sobre IA generativa está
# atrás do que ele já viu funcionando (a primeira foi vídeo de produto).
#
# Modelos que hoje escrevem texto certo: Recraft V3, Ideogram, gpt-image.
# O default aqui é o Recraft V3, que é feito pra peça gráfica com tipografia.
#
# ⚠️ O QUE CONTINUA VERDADE, E NÃO É TEIMOSIA — é o que o TESTE tem que medir:
#   1. A LOGO. Nas capas de referência, a "TS TOPSHOP CASA" é uma invenção
#      parecida com a nossa, não a nossa. A IA não reproduz o arquivo da marca;
#      ela desenha algo do mesmo espírito. Duas capas seguidas com logos
#      ligeiramente diferentes é pior que capa simples com a logo certa.
#   2. O PREÇO. Se um "R$ 29,90" sai "R$ 28,90", isso é problema comercial,
#      não estético.
#   3. O CUSTO. Recraft/Ideogram custam ~10-60× o schnell POR IMAGEM. Só a
#      capa (1 por post) é sustentável; 9 slides por post, não.
#   4. CORRIGIR. Texto errado na IA só se conserta regerando a imagem toda.
#
# Por isso este módulo NÃO substitui o híbrido — ele fica ao lado, pra medir.
# `--comparar` gera as duas versões do MESMO hook, lado a lado. Quem decide é
# o Dre olhando, não eu argumentando.
#
# USO:
#   python3 capa_ia.py --teste casa                 # 1 capa, pra ver
#   python3 capa_ia.py --comparar casa              # IA inteira vs híbrida
#   python3 capa_ia.py --prompt casa                # o prompt, sem gastar
#
#   from capa_ia import gerar_capa
#   caminho = gerar_capa("casa", "3 ERROS QUE...", "subtitulo", "@topshopcasa_")

import os
import sys
import json
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SAIDA = BASE_DIR / "assets" / "capas_ia"

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("capa_ia")

try:
    from fundo_ia import _carregar_env, CENARIOS
    _carregar_env()
except Exception:
    CENARIOS = {}

# ⚠️ O DEFAULT NÃO É O `flux/schnell`. Aquele é o barato pra CENÁRIO, e é ruim
# de letra. Recraft V3 é feito pra peça gráfica com tipografia; Ideogram é a
# outra opção forte. Trocável por `CAPA_MODELO` no .env sem tocar no código.
MODELO = os.environ.get("CAPA_MODELO", "fal-ai/recraft-v3")

# a mesma paleta por nicho do carrossel_render — a IA recebe a cor por NOME
# porque hex em prompt de imagem é ignorado na prática
_COR = {
    "tech": "lime green", "casa": "vivid orange", "beleza": "violet purple",
    "pet": "sky blue", "moda": "hot pink", "geral": "golden yellow",
}

_CENARIO_CURTO = {
    "casa": "a cozy modern living room at dusk with a dark sofa and warm lamp",
    "tech": "a dark desk setup at night with subtle accent lighting",
    "beleza": "an elegant dark bathroom vanity with soft lighting",
    "pet": "a cozy living room with a pet bed and warm evening light",
    "moda": "an open wardrobe with clothes in moody lighting",
    "geral": "a dark modern interior with warm accent light",
}


def montar_prompt(nicho: str, hook: str, sub: str = "", handle: str = "") -> str:
    """O prompt da capa. O texto vai LITERAL e entre aspas.

    ⚠️ O TEXTO PRECISA IR EXATO E ISOLADO. Modelo de imagem escreve o que ele
    lê como texto a renderizar; descrever ("a headline about cleaning errors")
    faz ele INVENTAR a frase. Entre aspas e em caixa alta, ele copia."""
    cor = _COR.get((nicho or "geral").lower(), _COR["geral"])
    cena = _CENARIO_CURTO.get((nicho or "geral").lower(), _CENARIO_CURTO["geral"])
    partes = [
        "Instagram carousel cover, vertical 4:5 poster design.",
        f"Background: {cena}, photorealistic, cinematic, dark moody tones,"
        " strongly darkened so text stays readable.",
        f'Headline in very large bold condensed uppercase sans-serif, white,'
        f' aligned left in the upper half, exactly this text: "{hook}".',
        f'Highlight the most important words with a solid {cor} rectangular'
        f' block behind them, with black letters inside the block.',
    ]
    if sub:
        partes.append(f'Below the headline, a smaller uppercase line in white,'
                      f' exactly this text: "{sub}".')
    partes.append(f'Bottom left: a small rounded outlined pill in {cor} with the'
                  f' text "ARRASTA PRO LADO".')
    partes.append("Clean composition, high contrast, no extra text, no random"
                  " letters, correct Portuguese spelling, no watermark.")
    return " ".join(partes)


def gerar_capa(nicho: str, hook: str, sub: str = "", handle: str = "",
               destino: Path = None) -> str:
    """Gera a capa. Devolve o caminho, ou "" com o motivo no log."""
    chave = os.environ.get("FAL_KEY", "") or os.environ.get("FAL_API_KEY", "")
    if not chave:
        log.warning("   ⚠️  FAL_KEY ausente — capa de IA não gerada")
        return ""
    os.environ.setdefault("FAL_KEY", chave)
    try:
        import fal_client
    except Exception:
        log.warning("   ⚠️  fal_client não instalado "
                    "(.venv/bin/pip install fal-client)")
        return ""

    prompt = montar_prompt(nicho, hook, sub, handle)
    try:
        r = fal_client.subscribe(MODELO, arguments={
            "prompt": prompt,
            "image_size": {"width": 1080, "height": 1350},
        }, with_logs=False)
    except Exception as e:
        log.warning(f"   ⚠️  {MODELO} recusou: {str(e)[:120]}")
        return ""

    url = ""
    try:
        imgs = (r or {}).get("images") or []
        url = imgs[0].get("url", "") if imgs else ((r or {}).get("image") or {}).get("url", "")
    except Exception:
        pass
    if not url:
        log.warning(f"   ⚠️  sem imagem na resposta: {str(r)[:120]}")
        return ""

    destino = destino or (SAIDA / nicho / "capa.jpg")
    try:
        import requests
        b = requests.get(url, timeout=180).content
        if len(b) < 10 * 1024:
            log.warning(f"   ⚠️  imagem com {len(b)} byte(s) — algo saiu errado")
            return ""
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b)
    except Exception as e:
        log.warning(f"   ⚠️  não baixei: {str(e)[:100]}")
        return ""
    return str(destino)


# ══════════════════════════════════════════════════════════════════════════
# O TESTE — que é o ponto deste módulo
# ══════════════════════════════════════════════════════════════════════════
_HOOK_TESTE = {
    "casa": ("3 ERROS QUE QUASE TODO MUNDO COMETE NA CASA",
             "PEQUENOS HABITOS QUE BAGUNCAM TUDO SEM VOCE PERCEBER"),
    "tech": ("5 ERROS QUE ESTAO ACABANDO COM SUA BATERIA",
             "E VOCE FAZ PELO MENOS 2 DELES TODO DIA"),
}


def _comparar(nicho: str) -> int:
    """Gera a MESMA capa dos dois jeitos, pra decisão ser por olho, não por
    argumento — inclusive contra o meu."""
    hook, sub = _HOOK_TESTE.get(nicho, _HOOK_TESTE["casa"])
    pasta = SAIDA / f"comparar_{nicho}"
    pasta.mkdir(parents=True, exist_ok=True)

    print(f"🎯 hook do teste: {hook!r}\n")
    print(f"1️⃣  IA INTEIRA ({MODELO}) …", end=" ", flush=True)
    a = gerar_capa(nicho, hook, sub, destino=pasta / "a_ia_inteira.jpg")
    print("✅" if a else "❌ (veja o aviso acima)")

    print("2️⃣  HÍBRIDA (fundo de IA + texto em PIL) …", end=" ", flush=True)
    b = ""
    try:
        import carrossel_render as CR
        plano = {"nicho": nicho, "handle": "",
                 "capa": {"hook": hook.replace("NA CASA", "[NA CASA]")
                                      .replace("SUA BATERIA", "[SUA BATERIA]"),
                          "sub": sub},
                 "slides": [{"tipo": "texto", "titulo": "teste"}],
                 "cta": {"titulo": "teste"}}
        arqs = CR.renderizar(plano, pasta / "_hibrida")
        if arqs:
            destino = pasta / "b_hibrida.jpg"
            destino.write_bytes(Path(arqs[0]).read_bytes())
            b = str(destino)
    except Exception as e:
        print(f"❌ {str(e)[:90]}")
    else:
        print("✅" if b else "❌")

    print(f"\n📁 {pasta}")
    for x in (a, b):
        if x:
            print(f"   {x}")
    print("\nBaixa as duas e olha lado a lado. O que importa conferir:")
    print("   · o texto saiu EXATO e sem letra inventada?")
    print("   · a logo/marca ficou fiel ou é uma invenção parecida?")
    print("   · daria pra publicar 60 dessas por mês sem parecer repetido?")
    return 0 if (a or b) else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Capa inteira gerada por IA")
    p.add_argument("--teste", metavar="NICHO", help="gera 1 capa pra ver")
    p.add_argument("--comparar", metavar="NICHO",
                   help="IA inteira vs híbrida, mesmo hook")
    p.add_argument("--prompt", metavar="NICHO", help="imprime o prompt e sai")
    p.add_argument("--hook", default="", help="usa este hook em vez do padrão")
    a = p.parse_args()

    nicho = a.teste or a.comparar or a.prompt
    if not nicho:
        p.print_help()
        return 1
    hook, sub = _HOOK_TESTE.get(nicho, _HOOK_TESTE["casa"])
    if a.hook:
        hook = a.hook

    if a.prompt:
        print(f"🤖 {MODELO}\n")
        print(montar_prompt(nicho, hook, sub))
        return 0
    if a.comparar:
        return _comparar(nicho)

    print(f"🤖 {MODELO}")
    caminho = gerar_capa(nicho, hook, sub)
    if not caminho:
        return 1
    print(f"✅ {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
