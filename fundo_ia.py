#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# fundo_ia.py — gera o FUNDO das capas de carrossel com IA (Fal).
#
# ⚠️ A PERGUNTA DO DRE (22/08): "então não tem como fazer essas capas, e os
# slides que o chatgpt faz?" Tem. E a peça que faltava não era layout — era a
# MATÉRIA-PRIMA DA IMAGEM.
#
# As capas que ele fez no ChatGPT usam foto de AMBIENTE: sala com sofá e luz
# baixa, setup com profundidade. A nossa usava foto de PRODUTO da Shopee, que é
# catálogo em fundo branco. Escurecida, foto de catálogo vira mancha; foto de
# ambiente vira capa. Nenhum ajuste de tipografia resolve isso.
#
# ⚠️ POR QUE A IA GERA SÓ O FUNDO, E NÃO A CAPA INTEIRA COMO O CHATGPT FAZ:
# porque a IA erra texto. Em português, com acento, ela troca letra, deforma
# glifo e inventa palavra — e quando erra não dá pra consertar, só regerar. A
# divisão que funciona é:
#       IA  → o ambiente (onde ela é ótima e a gente não tem como fazer)
#       PIL → o texto    (onde ela é ruim e a gente já é exato)
# É o melhor dos dois, e é reversível: fundo ruim se troca sem tocar no texto.
#
# ⚠️ E O FUNDO É REUSADO, NÃO GERADO POR POST. Um fundo por carrossel seriam
# ~60 imagens/mês por conta. O fundo é CENÁRIO, não conteúdo: 6 por nicho, bem
# feitos, rodam o mês inteiro sem ninguém notar — e o que muda de post pra post
# (hook, tarja, produto) já muda tudo o que o olho lê primeiro.
#
# USO:
#   python3 fundo_ia.py --gerar casa --quantos 6   # gera e guarda
#   python3 fundo_ia.py --listar                   # o que já existe
#   python3 fundo_ia.py --prompt casa              # vê o prompt, sem gastar
#
#   from fundo_ia import fundo_do_nicho
#   caminho = fundo_do_nicho("casa")   # "" se não houver nenhum

import os
import sys
import json
import random
import hashlib
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
FUNDOS = BASE_DIR / "assets" / "fundos"

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("fundo_ia")


def _carregar_env():
    for cand in (Path(".env"), BASE_DIR / ".env"):
        if not cand.exists():
            continue
        for linha in cand.read_text(encoding="utf-8", errors="ignore").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            k, _, v = linha.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        break


_carregar_env()

MODELO = os.environ.get("FUNDO_MODELO", "fal-ai/flux/schnell")

# ⚠️ TODO PROMPT TERMINA COM O MESMO PEDAÇO, e ele não é enfeite:
# "no text, no words, no logos" — porque o texto é NOSSO, escrito por cima em
# PIL. Fundo que já vem com letra da IA briga com o hook e não tem conserto.
# "empty space on the left" — o hook é alinhado à esquerda e ocupa o topo; se
# o assunto da foto ficar ali embaixo dele, o véu não salva.
_COMUM = ("photorealistic, cinematic lighting, shallow depth of field, "
          "moody dark tones, empty negative space on the upper left, "
          "no text, no words, no letters, no logos, no watermark, "
          "vertical composition")

CENARIOS = {
    "casa": [
        "modern cozy living room at dusk, dark grey sofa, warm lamp light, "
        "wooden coffee table with a small plant",
        "tidy minimalist kitchen counter at night, dark cabinets, soft warm light",
        "organized bedroom corner, neutral bedding, warm side lamp, dark walls",
    ],
    "tech": [
        "dark desk setup with subtle green accent lighting, keyboard out of focus",
        "close view of a dark workspace at night, screens glowing softly, "
        "cables neatly arranged",
        "black desk with soft neon rim light, abstract circuit bokeh background",
    ],
    "beleza": [
        "elegant bathroom vanity at night, marble counter, soft purple accent light",
        "dark dressing table with a mirror, warm bulbs out of focus",
        "moody close view of a skincare shelf, soft violet lighting",
    ],
    "pet": [
        "cozy living room floor with a dog bed, warm evening light, dark tones",
        "dark kitchen corner with pet bowls, soft blue accent light",
        "living room with a cat resting on a dark sofa, warm lamp",
    ],
    "moda": [
        "open wardrobe with hanging clothes, dark tones, soft pink rim light",
        "dark dressing room corner, mirror, warm moody lighting",
        "folded clothes on a dark shelf, soft pink accent lighting",
    ],
    "geral": [
        "dark modern interior with warm golden accent light, blurred background",
        "moody minimal room, dark walls, single warm lamp",
        "dark tabletop scene with warm golden rim light",
    ],
}


def prompt_do_nicho(nicho: str, i: int = None) -> str:
    cenas = CENARIOS.get((nicho or "geral").lower(), CENARIOS["geral"])
    cena = cenas[i % len(cenas)] if i is not None else random.choice(cenas)
    return f"{cena}, {_COMUM}"


def _pasta(nicho: str) -> Path:
    return FUNDOS / (nicho or "geral").lower()


def existentes(nicho: str) -> list:
    p = _pasta(nicho)
    return sorted(p.glob("*.jpg")) if p.exists() else []


def fundo_do_nicho(nicho: str) -> str:
    """Um fundo já gerado, sorteado. "" quando não há nenhum.

    Sorteia em vez de rodar em ordem porque a ordem faria dois posts seguidos
    da mesma conta usarem o mesmo cenário sempre que a fila reiniciasse."""
    arqs = existentes(nicho)
    return str(random.choice(arqs)) if arqs else ""


# ══════════════════════════════════════════════════════════════════════════
# GERAÇÃO
# ══════════════════════════════════════════════════════════════════════════
def _gerar_um(prompt: str, destino: Path) -> str:
    """Gera 1 fundo. "" se OK, senão a mensagem de erro."""
    chave = os.environ.get("FAL_KEY", "") or os.environ.get("FAL_API_KEY", "")
    if not chave:
        return ("FAL_KEY não está no .env — sem ela não dá pra gerar fundo "
                "(o carrossel continua saindo com a foto do produto)")
    os.environ.setdefault("FAL_KEY", chave)
    try:
        import fal_client
    except Exception:
        return "a lib 'fal_client' não está instalada (pip install fal-client)"
    try:
        r = fal_client.subscribe(MODELO, arguments={
            "prompt": prompt,
            # 1080×1350 é o quadro do carrossel; pedir na proporção certa evita
            # corte, e corte em fundo é onde some justamente o vazio do topo
            "image_size": {"width": 1080, "height": 1350},
            "num_images": 1,
        }, with_logs=False)
    except Exception as e:
        return f"Fal recusou: {str(e)[:120]}"

    url = ""
    try:
        url = ((r or {}).get("images") or [{}])[0].get("url", "")
    except Exception:
        pass
    if not url:
        return f"a Fal não devolveu imagem: {str(r)[:120]}"

    try:
        import requests
        b = requests.get(url, timeout=120).content
        if len(b) < 10 * 1024:
            return f"a imagem veio com {len(b)} byte(s) — algo saiu errado"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b)
    except Exception as e:
        return f"não baixei a imagem: {str(e)[:100]}"
    return ""


def gerar(nicho: str, quantos: int = 6, seco: bool = False) -> int:
    pasta = _pasta(nicho)
    ja = len(existentes(nicho))
    print(f"📁 {pasta}  ({ja} fundo(s) hoje)")
    print(f"🤖 {MODELO}\n")
    feitos = 0
    for i in range(quantos):
        p = prompt_do_nicho(nicho, i)
        nome = hashlib.sha1(f"{nicho}{i}{random.random()}".encode()).hexdigest()[:10]
        destino = pasta / f"{nome}.jpg"
        print(f"  {i+1}/{quantos} …", end=" ", flush=True)
        if seco:
            print(f"[seco] {p[:70]}…")
            continue
        erro = _gerar_um(p, destino)
        if erro:
            print(f"❌ {erro}")
            # ⚠️ PARA NO PRIMEIRO ERRO. Se a chave está errada ou o crédito
            # acabou, as outras 5 tentativas vão falhar igual — insistir só
            # gasta tempo e, se for cobrança por tentativa, dinheiro.
            break
        feitos += 1
        print(f"✅ {destino.name} ({destino.stat().st_size // 1024} KB)")
    if feitos:
        print(f"\n✅ {feitos} fundo(s) novo(s) em {pasta}")
        print(f"   O carrossel de '{nicho}' já usa eles na próxima rodada.")
    return 0 if feitos or seco else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Fundos de capa gerados por IA")
    p.add_argument("--gerar", metavar="NICHO", help="gera fundos pro nicho")
    p.add_argument("--quantos", type=int, default=6)
    p.add_argument("--seco", action="store_true", help="mostra sem gastar crédito")
    p.add_argument("--listar", action="store_true")
    p.add_argument("--prompt", metavar="NICHO", help="imprime o prompt e sai")
    a = p.parse_args()

    if a.prompt:
        for i in range(len(CENARIOS.get(a.prompt, CENARIOS["geral"]))):
            print(f"\n[{i}] {prompt_do_nicho(a.prompt, i)}")
        return 0
    if a.listar:
        print(f"📁 {FUNDOS}\n")
        for nicho in CENARIOS:
            arqs = existentes(nicho)
            marca = "✅" if arqs else "⬜"
            print(f"  {marca} {nicho:<8} {len(arqs)} fundo(s)")
        print("\nGerar:  python3 fundo_ia.py --gerar casa --quantos 6")
        return 0
    if a.gerar:
        return gerar(a.gerar, a.quantos, a.seco)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
