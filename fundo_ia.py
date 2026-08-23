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
# ⚠️ CORREÇÃO (22/08): eu escrevi aqui que "a IA erra texto em português" pra
# justificar gerar só o fundo. O Dre me corrigiu e tem razão — isso vale pros
# modelos de um/dois anos atrás e pro `flux/schnell` que este módulo usa, que é
# o RÁPIDO E BARATO da família e o pior em tipografia. Recraft V3 e Ideogram
# escrevem certo. A capa inteira por IA vive no `capa_ia.py` e o `--comparar`
# de lá põe as duas lado a lado.
#
# Este módulo continua valendo por OUTRO motivo, que não é qualidade de letra:
#       IA/foto → o ambiente (custa 1 imagem por NICHO, reusada o mês inteiro)
#       PIL     → o texto    (custa zero, e a marca sai EXATA: logo, @, selo)
# Ou seja, é o caminho barato e fiel à marca. O outro é o caminho bonito e caro.
# Quem decide entre os dois é o teste, não este comentário.
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
# ══════════════════════════════════════════════════════════════════════════
# FUNDO DE GRAÇA — Pexels
#
# ⚠️ ISTO EXISTE PORQUE A FAL TRANCOU (22/08): `User is locked. Reason:
# Exhausted balance.` Um fundo é CENÁRIO — sofá, bancada, mesa. Isso não
# precisa ser inventado por IA; existe aos milhares em banco de foto, de graça
# e com uso comercial liberado. Gastar crédito de geração pra ter uma sala de
# estar é gastar no lugar errado, e a fila de vídeo precisa desse crédito.
#
# O projeto JÁ TEM `asset_autopilot_agent.buscar_pexels`, com orientação
# retrato e tudo. Reusar em vez de reimplementar: é a mesma chave, o mesmo
# tratamento de erro e a mesma licença já documentada lá.
# ══════════════════════════════════════════════════════════════════════════
BUSCAS = {
    "casa": ["cozy dark living room", "modern kitchen counter night",
             "minimal bedroom dark", "home interior warm light"],
    "tech": ["dark desk setup", "gaming setup neon", "workspace night computer",
             "technology dark background"],
    "beleza": ["bathroom vanity marble", "skincare products dark",
               "makeup table mirror", "cosmetics flat lay dark"],
    "pet": ["dog resting living room", "cat on sofa dark", "pet bed home",
            "puppy indoor warm light"],
    "moda": ["clothing rack wardrobe", "folded clothes shelf",
             "fashion closet dark", "boutique interior"],
    "geral": ["dark modern interior", "moody home decor", "warm dark room",
              "minimal dark background"],
}


def _do_pexels(nicho: str, quantos: int) -> int:
    """Baixa fundos do Pexels. Devolve quantos vieram."""
    if not os.environ.get("PEXELS_API_KEY", "").strip():
        print("❌ PEXELS_API_KEY não está no .env — é grátis em "
              "pexels.com/api, e é o caminho sem custo pro fundo.")
        return 0
    try:
        try:
            from agents.asset_autopilot_agent import buscar_pexels
        except Exception:
            from asset_autopilot_agent import buscar_pexels
    except Exception as e:
        print(f"❌ não consegui usar o buscador do projeto: {str(e)[:90]}")
        return 0

    import requests
    pasta = _pasta(nicho)
    pasta.mkdir(parents=True, exist_ok=True)
    buscas = BUSCAS.get((nicho or "geral").lower(), BUSCAS["geral"])
    feitos, vistos = 0, set()
    for termo in buscas:
        if feitos >= quantos:
            break
        try:
            cands = buscar_pexels(termo, tipo="photo", limite=6) or []
        except Exception as e:
            print(f"  ⚠️  '{termo}': {str(e)[:70]}")
            continue
        for c in cands:
            if feitos >= quantos:
                break
            url = (c or {}).get("url", "")
            if not url or url in vistos:
                continue
            vistos.add(url)
            nome = hashlib.sha1(url.encode()).hexdigest()[:10]
            destino = pasta / f"pexels_{nome}.jpg"
            if destino.exists():
                continue
            try:
                b = requests.get(url, timeout=60).content
                if len(b) < 20 * 1024:
                    continue
                destino.write_bytes(b)
            except Exception:
                continue
            feitos += 1
            print(f"  ✅ {destino.name} ({len(b)// 1024} KB)  ← {termo}")
    return feitos


def _traduzir_fal(e) -> str:
    """⚠️ SALDO ESGOTADO NÃO É "A FAL RECUSOU" — E A DIFERENÇA É CARA.
    Em 22/08 a Fal respondeu `User is locked. Reason: Exhausted balance` e a
    mensagem genérica esconderia o que isso significa: a MESMA conta paga a
    geração de VÍDEO. Se ela travou aqui, a esteira de Reels travou junto, e
    ninguém foi avisado — é o tipo de coisa que só aparece dois dias depois,
    quando a fila esvazia."""
    txt = str(e)
    if "balance" in txt.lower() or "locked" in txt.lower():
        return ("SALDO DA FAL ESGOTADO (a conta está travada).\n"
                "   ⚠️ ATENÇÃO: é a MESMA conta que gera os VÍDEOS — a esteira\n"
                "   de Reels para junto, sem avisar. Confira a fila hoje.\n"
                "   Recarregue em fal.ai/dashboard/billing, ou use o fundo de\n"
                "   graça:  python3 fundo_ia.py --pexels " + "<nicho>")
    return f"Fal recusou: {txt[:120]}"


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
        return _traduzir_fal(e)

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
    p.add_argument("--pexels", metavar="NICHO",
                   help="baixa fundos do Pexels (GRATIS, sem gastar credito)")
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
    if a.pexels:
        print(f"📁 {_pasta(a.pexels)}\n🆓 Pexels (uso comercial liberado)\n")
        n = _do_pexels(a.pexels, a.quantos)
        if n:
            print(f"\n✅ {n} fundo(s) em {_pasta(a.pexels)}")
            print(f"   O carrossel de '{a.pexels}' já usa eles na próxima rodada.")
            return 0
        print("\n⚠️  nenhum fundo veio.")
        return 1
    if a.gerar:
        return gerar(a.gerar, a.quantos, a.seco)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
