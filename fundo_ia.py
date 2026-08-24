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
import re
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

# ⚠️ DEZ CENAS POR NICHO, NÃO TRÊS. Eram 3, e o Dre perguntou se devia gerar
# 10 fundos — com 3 prompts, 10 imagens seriam 3 cenários repetidos. O acervo
# ideal é 10-12 por nicho (fundo em TODO slide agora), então a lista de cenas
# tem que comportar isso sem repetir.
#
# ⚠️ E TODAS SÃO AMBIENTE, NUNCA PRODUTO. Foto de produto a gente já tem, da
# Shopee, e ela vive no slide de produto. O que falta é o LUGAR onde o produto
# viveria — sala, bancada, banheiro. É isso que transforma um retângulo de cor
# em capa, e é a única coisa que a gente não tem como conseguir de outro jeito.
CENARIOS = {
    "casa": [
        "modern cozy living room at dusk, dark grey sofa, warm lamp light, "
        "wooden coffee table with a small plant",
        "tidy minimalist kitchen counter at night, dark cabinets, soft warm light",
        "organized bedroom corner, neutral bedding, warm side lamp, dark walls",
        "clean laundry area at night, folded towels on a dark shelf, soft light",
        "entryway with a wooden bench and hooks, warm evening light, dark tones",
        "dining table set for two, dark wood, single pendant lamp above",
        "bathroom shelf with folded towels and a plant, moody warm light",
        "home office corner with a lamp and books, dark walls, evening",
        "balcony with plants and a chair at dusk, warm string lights",
        "open shelving with organized jars and baskets, dark kitchen, warm light",
    ],
    "tech": [
        "dark desk setup with subtle green accent lighting, keyboard out of focus",
        "close view of a dark workspace at night, screens glowing softly",
        "black desk with soft neon rim light, abstract circuit bokeh background",
        "gaming corner at night, dark walls, green accent light, chair silhouette",
        "cables and adapters neatly arranged on a dark surface, moody light",
        "smartphone charging on a dark nightstand, warm lamp behind",
        "headphones and laptop on a dark table, cinematic side light",
        "home theater corner at night, dark room, screen glow on the wall",
        "car dashboard at night with soft ambient lighting, blurred",
        "workbench with small tools and gadgets, dark tones, focused light",
    ],
    "beleza": [
        "elegant bathroom vanity at night, marble counter, soft purple accent light",
        "dark dressing table with a mirror, warm bulbs out of focus",
        "moody close view of a skincare shelf, soft violet lighting",
        "bathroom counter with folded towels and a candle, warm dark tones",
        "makeup brushes in a holder on a dark surface, soft pink light",
        "shower shelf with bottles, steam, moody lighting",
        "hair styling corner with a mirror and warm bulbs, dark walls",
        "nail care setup on a dark table, soft violet rim light",
        "perfume bottles on a dark shelf, cinematic light",
        "spa-like corner with a plant and a towel, dark tones, warm light",
    ],
    "pet": [
        "cozy living room floor with a dog bed, warm evening light, dark tones",
        "dark kitchen corner with pet bowls, soft blue accent light",
        "living room with a cat resting on a dark sofa, warm lamp",
        "dog toys on a wooden floor, evening light, dark background",
        "pet grooming corner with towels and brushes, moody light",
        "cat tree by a window at dusk, dark room, soft light",
        "leash and collar hanging by the door, warm dark entryway",
        "pet food storage in a dark pantry, soft warm light",
        "dog resting on a rug near a lamp, cozy dark living room",
        "window seat with a blanket where a pet sleeps, evening light",
    ],
    "moda": [
        "open wardrobe with hanging clothes, dark tones, soft pink rim light",
        "dark dressing room corner, mirror, warm moody lighting",
        "folded clothes on a dark shelf, soft pink accent lighting",
        "shoes lined up on a dark rack, cinematic side light",
        "accessories on a dark tray, soft pink light, shallow depth",
        "coat rack by a dark wall, warm evening light",
        "mirror selfie corner without people, dark room, soft light",
        "handbags on a shelf, dark tones, moody lighting",
        "jewelry on a dark surface, soft pink rim light",
        "neatly folded jeans and knitwear on a dark bench, warm light",
    ],
    "geral": [
        "dark modern interior with warm golden accent light, blurred background",
        "moody minimal room, dark walls, single warm lamp",
        "dark tabletop scene with warm golden rim light",
        "shopping bags on a dark floor by a door, warm light",
        "cozy corner with a chair and a lamp, dark tones",
        "desk with everyday objects out of focus, warm dark light",
        "shelf with assorted boxes and baskets, moody warm lighting",
        "kitchen counter at night, dark, single warm light source",
        "hallway with a plant and warm lamp, dark walls",
        "living room at dusk seen from the doorway, warm lamps on",
    ],
}


def prompt_do_nicho(nicho: str, i: int = None) -> str:
    cenas = CENARIOS.get((nicho or "geral").lower(), CENARIOS["geral"])
    cena = cenas[i % len(cenas)] if i is not None else random.choice(cenas)
    return f"{cena}, {_COMUM}"


def _pasta(nicho: str) -> Path:
    return FUNDOS / (nicho or "geral").lower()


# ⚠️ NÃO VOLTE ISTO PRA `*.jpg`. O `--gerar` do Fal salvava .jpg e por isso o
# glob era .jpg — mas quem alimenta o acervo hoje é o Dre, baixando do ChatGPT,
# e o ChatGPT baixa .PNG. Com o glob antigo o carrossel renderizaria sem fundo
# nenhum, SEM ERRO E SEM AVISO: `_fundo()` no slides_html.py só devolve "" e o
# slide sai bonito, só que liso. É a pior categoria de bug daqui — o que não
# reclama. O `--importar` normaliza pra .jpg, mas o glob aceita os quatro
# formatos pra que largar o arquivo na pasta na mão TAMBÉM funcione.
EXTENSOES = (".jpg", ".jpeg", ".png", ".webp")


def existentes(nicho: str) -> list:
    p = _pasta(nicho)
    if not p.exists():
        return []
    return sorted(a for a in p.iterdir()
                  if a.suffix.lower() in EXTENSOES and a.is_file())


ALVO_L, ALVO_A = 1080, 1350


def _digestao(caminho) -> str:
    return hashlib.sha1(Path(caminho).read_bytes()).hexdigest()


def importar(nicho: str, origens: list) -> int:
    """Põe no acervo do nicho as imagens que o Dre baixou do ChatGPT.

    Faz três coisas que parecem frescura e não são:

    1. CONVERTE PRA JPEG. O ChatGPT entrega PNG de 2-3 MB. O `slides_html.py`
       embute a foto como data: URI dentro do HTML, e base64 engorda 33%: 7
       slides × 3 MB viram ~28 MB de HTML pro Chromium mastigar a cada
       carrossel. Em JPEG q88 o mesmo fundo pesa ~250 KB. O olho não vê a
       diferença — a foto ainda leva `brightness(.6)` por cima.
    2. NÃO AMPLIA, só reduz. Fundo menor que 1080x1350 fica borrado quando o
       `background-size:cover` estica; ampliar aqui não inventa pixel, só
       esconde o problema do aviso. Se vier pequeno, eu aviso e importo assim
       mesmo — quem decide se serve é quem olha.
    3. NÃO CORTA. A régua do prompt é "espaço vazio em cima à esquerda"; cortar
       aqui pra 4:5 mataria justamente essa margem, que é onde o título pousa.
       Quem corta é o CSS, na hora, e ele corta pelo centro.

    Duplicata é detectada por conteúdo (sha1 do JPEG final), não por nome:
    baixar a mesma imagem duas vezes é `Cena (1).png` e `Cena (2).png`, nomes
    diferentes e bytes iguais. Sem isso o rodízio acharia que tem 10 fundos
    quando tem 7, e repetiria os 3 clonados com o triplo da frequência.
    """
    try:
        from PIL import Image
    except ImportError:
        print("❌ falta o Pillow. Rode com o python do projeto:\n"
              "   .venv/bin/python fundo_ia.py --importar ...")
        return 0

    achados = []
    for o in origens:
        p = Path(o).expanduser()
        if p.is_dir():
            achados += [a for a in sorted(p.rglob("*"))
                        if a.is_file() and a.suffix.lower() in EXTENSOES]
        elif p.is_file():
            achados.append(p)
        else:
            print(f"⚠️  não achei: {o}")
    if not achados:
        print("⚠️  nenhuma imagem nos caminhos passados "
              f"(aceito {', '.join(EXTENSOES)}).")
        return 0

    destino = _pasta(nicho)
    destino.mkdir(parents=True, exist_ok=True)
    jaTem = {_digestao(a) for a in existentes(nicho)}
    indice = 0
    novos = 0

    for arq in achados:
        # ⚠️ IMPORTAR A PASTA EM CIMA DELA MESMA é o caso que o `--listar`
        # sugere pra normalizar PNG cru já guardado. Sem este bloco, o PNG
        # viraria um .jpg NOVO e o PNG continuaria lá: o acervo passaria a ter
        # a mesma foto duas vezes, e o rodízio a mostraria com o dobro da
        # frequência achando que são duas. Aqui o original é SUBSTITUÍDO.
        no_lugar = arq.resolve().parent == destino.resolve()
        if no_lugar and arq.suffix.lower() == ".jpg" \
                and arq.stat().st_size <= 900_000:
            continue

        try:
            img = Image.open(arq)
            img.load()
        except Exception as e:
            print(f"⚠️  {arq.name}: não abriu ({e})")
            continue

        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            # fundo preto, não branco: estes fundos são escuros e uma borda
            # branca vazando pelo alfa apareceria como halo no slide.
            base = Image.new("RGB", img.size, (0, 0, 0))
            base.paste(img, mask=img.split()[-1])
            img = base
        else:
            img = img.convert("RGB")

        l, a = img.size
        if l < ALVO_L or a < ALVO_A:
            print(f"⚠️  {arq.name}: {l}x{a} é menor que {ALVO_L}x{ALVO_A} — "
                  f"vai esticar. Importei mesmo assim.")
        else:
            escala = max(ALVO_L / l, ALVO_A / a)
            if escala < 1:
                img = img.resize((round(l * escala), round(a * escala)),
                                 Image.LANCZOS)

        temp = destino / ".importando.jpg"
        img.save(temp, "JPEG", quality=88, optimize=True,
                 progressive=True)
        chave = _digestao(temp)
        if chave in jaTem:
            temp.unlink()
            # ⚠️ SE A DUPLICATA MORA NA PRÓPRIA PASTA DE DESTINO, pular não
            # basta: o arquivo cru continuaria lá ao lado do .jpg gêmeo e o
            # acervo teria a mesma foto duas vezes — o defeito que este bloco
            # inteiro existe pra evitar. Peguei isso testando, depois de
            # escrever o comentário dizendo que estava resolvido.
            if no_lugar:
                arq.unlink()
                print(f"🗑️  {arq.name}: era cópia crua de um .jpg que já "
                      f"estava aqui, removi.")
            else:
                print(f"↻  {arq.name}: já estava no acervo, pulei.")
            continue

        if no_lugar:
            jaTem.discard(_digestao(arq))
            arq.unlink()

        while True:
            indice += 1
            saida = destino / f"{nicho.lower()}-{indice:02d}.jpg"
            if not saida.exists():
                break
        temp.replace(saida)
        jaTem.add(chave)
        novos += 1
        kb = saida.stat().st_size // 1024
        print(f"✅ {saida.name}  ({img.size[0]}x{img.size[1]}, {kb} KB) "
              f"← {arq.name}")

    return novos


MEMORIA_FUNDO = BASE_DIR / "shared" / "fundos_recentes.json"


def fundo_do_nicho(nicho: str) -> str:
    """Um fundo do acervo do nicho. "" quando não há nenhum.

    ⚠️ RODÍZIO COM MEMÓRIA, NÃO SORTEIO — e isso vale DINHEIRO, não só estética.
    Com sorteio puro e N fundos, a chance de repetir o anterior é 1/N: com 6
    fundos e 8 carrosséis por semana, a mesma foto sairia repetida umas 1,3
    vezes por semana na MESMA conta. Guardando os últimos 3, os mesmos 6 fundos
    rendem o que 12 renderiam no sorteio — ou seja, **metade das imagens pra
    gerar**. É a mesma mecânica do rodízio dos fechos e do 1º comentário."""
    arqs = [str(a) for a in existentes(nicho)]
    if not arqs:
        return ""
    try:
        mem = json.loads(MEMORIA_FUNDO.read_text(encoding="utf-8"))
    except Exception:
        mem = {}
    recentes = mem.get(nicho, [])
    novos = [a for a in arqs if a not in recentes]
    escolha = random.choice(novos or arqs)
    try:
        # lembra no máximo METADE do acervo: guardar demais esvazia a lista de
        # candidatos e o rodízio vira ordem fixa, que é o defeito oposto
        mem[nicho] = ([escolha] + recentes)[:max(1, min(3, len(arqs) // 2))]
        MEMORIA_FUNDO.parent.mkdir(parents=True, exist_ok=True)
        MEMORIA_FUNDO.write_text(json.dumps(mem, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    except Exception:
        pass
    return escolha


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


# ══════════════════════════════════════════════════════════════════════════
# GEMINI — a resposta pra "eu mesmo que preciso fazer as imagens?"
#
# ⚠️ NÃO. E A CHAVE JÁ ESTÁ NO `.env` HÁ MESES. O projeto inteiro chama
# `google.genai` com `GEMINI_API_KEY` pra escrever texto (main, ceo_agent,
# narration_script_builder...). A MESMA chave e o MESMO cliente geram imagem —
# muda só o nome do modelo. Não precisa de conta nova, chave nova nem SDK novo.
#
# ⚠️ O QUE ISSO **NÃO** É: não é o ChatGPT ilimitado do Dre. Aquilo é
# assinatura, e assinatura não vira API. Aqui se paga por imagem, na conta do
# Google que o projeto já usa. Ou seja, as duas fontes coexistem e servem a
# coisas diferentes:
#     ChatGPT (mão, ilimitado 31 dias) → acervo de ambiente, reusado o mês todo
#     Gemini  (API, por imagem)        → a foto DAQUELE slide, no dia, sozinho
# A segunda é a que resolve o gargalo que o ChatGPT apontou ("se eu tirar o
# texto, a imagem ainda representa o assunto?"), porque ela nasce do texto do
# slide. A primeira continua valendo por ser de graça e sem depender de rede.
MODELO_IMG = os.environ.get("GEMINI_MODELO_IMG", "gemini-2.5-flash-image")


def _gemini_imagem(prompt: str, destino: Path) -> str:
    """Gera UMA imagem pelo Gemini. Devolve "" se deu certo, ou o motivo."""
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not chave:
        return ("GEMINI_API_KEY não está no ambiente. Ela existe no .env da "
                "VPS — rode com o mesmo carregador de env dos outros módulos.")
    try:
        from google import genai
    except ImportError:
        return "falta o pacote google-genai (.venv/bin/pip install google-genai)"

    try:
        cli = genai.Client(api_key=chave)
        r = cli.models.generate_content(model=MODELO_IMG, contents=prompt)
    except Exception as e:
        return _traduzir_gemini(e)

    # a imagem vem como parte inline dentro da resposta, junto de partes de
    # texto — pegar a primeira parte com bytes, e não a primeira parte.
    try:
        for cand in (r.candidates or []):
            for parte in (getattr(cand.content, "parts", None) or []):
                dados = getattr(getattr(parte, "inline_data", None), "data", None)
                if dados:
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    destino.write_bytes(dados)
                    return ""
    except Exception as e:
        return f"resposta em formato inesperado: {e}"
    return ("a resposta veio sem imagem — normalmente é o prompt sendo "
            "recusado por política de conteúdo")


def _traduzir_gemini(e: Exception) -> str:
    """⚠️ Mensagem de API não diz o que FAZER. Estes três erros têm conserto
    diferente e a mesma cara de 'deu erro'."""
    t = str(e)
    if "403" in t or "PERMISSION" in t.upper():
        return ("403: a chave não tem acesso a geração de imagem. Costuma ser "
                "faturamento desligado no projeto do Google Cloud — a mesma "
                "chave que escreve texto pode não estar liberada pra imagem.")
    if "404" in t or "NOT_FOUND" in t:
        return (f"404: o modelo '{MODELO_IMG}' não existe pra esta chave. "
                f"Ajuste com GEMINI_MODELO_IMG=<nome> no .env.")
    if "429" in t or "RESOURCE_EXHAUSTED" in t.upper():
        return "429: cota estourada. Espera a janela virar ou sobe o limite."
    return t[:200]


def _ultimo_carrossel():
    """A pasta de carrossel mais recente.

    ⚠️ COMANDO COM DATA ESCRITA NA MÃO É COMANDO COM PRAZO DE VALIDADE. Eu
    mandei o Dre rodar `--do-plano pronto_carrossel/20260823_manual_casa` e,
    entre um comando e o outro, passou da meia-noite na VPS: o render criou
    `20260824_...` e o meu caminho apontava pro dia anterior. Deu "não achei
    plano.json" num sistema que estava funcionando. **E eu já tinha aprendido
    isso**: o `midia_publica --ver` pega a mais recente sozinho justamente por
    causa desta armadilha — só não apliquei aqui. Lição repetida é lição não
    aprendida."""
    raiz = BASE_DIR / "pronto_carrossel"
    cands = [d for d in raiz.iterdir() if d.is_dir()] if raiz.is_dir() else []
    return max(cands, key=lambda d: d.stat().st_mtime) if cands else None


def do_plano(pasta=None, seco: bool = False) -> int:
    """Gera UMA imagem POR SLIDE, a partir do que aquele slide diz.

    ⚠️ ESTE É O CONSERTO DO MAIOR DEFEITO QUE SOBROU. Hoje o fundo sai por
    rodízio do acervo do NICHO: o slide fala "bebê em posição errada" e o fundo
    é uma despensa com potes. Casa a estética da conta e não casa o assunto. O
    teste que o ChatGPT propôs — *"se eu remover todo o texto, essa imagem
    ainda representa o assunto deste slide?"* — dava NÃO em 4 dos 8.

    O plano já existe em disco ANTES do render e já sabe o que cada slide diz.
    Então a foto pode nascer do texto em vez de ser sorteada."""
    pasta = Path(pasta) if pasta else _ultimo_carrossel()
    if pasta is None:
        print("❌ nenhuma pasta em pronto_carrossel/")
        return 1
    plano_j = pasta / "plano.json"
    if not plano_j.exists():
        print(f"❌ não achei {plano_j}")
        irmas = sorted((BASE_DIR / "pronto_carrossel").glob("*/plano.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)[:3]
        if irmas:
            print("   Mas existe plano.json em:")
            for i in irmas:
                print(f"     {i.parent}")
            print("   (rode sem argumento que eu pego o mais recente)")
        return 1
    plano = json.loads(plano_j.read_text(encoding="utf-8"))
    nicho = plano.get("nicho", "geral")
    saida = pasta / "fundos"
    alvos = []
    capa = plano.get("capa") or {}
    if capa.get("hook"):
        alvos.append((1, capa.get("hook", ""), capa.get("sub", "")))
    slides = plano.get("slides") or []
    for k, sl in enumerate(slides, start=2):
        # ⚠️ O CHECKLIST TAMBÉM ENTRA. Na 1ª rodada eu pulava os slides de
        # `itens` "porque usam fundo de ambiente" — e o resultado foi o slide
        # de checklist de MAMADEIRA aparecer sobre uma prateleira de potes de
        # cozinha. É o mesmo defeito que o `--do-plano` existe pra matar, só
        # que eu tinha aberto uma exceção pra ele.
        if sl.get("itens"):
            alvos.append((k, " · ".join(str(x) for x in sl["itens"][:4]),
                          "cena de contexto, o texto entra num cartão por cima"))
            continue
        alvos.append((k, sl.get("titulo") or "", sl.get("linha") or ""))
    # e o FECHO, que é o último slide e também vinha do acervo genérico
    cta = plano.get("cta") or {}
    if cta:
        alvos.append((len(slides) + 2, cta.get("titulo") or "",
                      " ".join(cta.get("linhas") or [])))

    print(f"🎯 {len(alvos)} imagem(ns) — uma por slide, do texto dele\n")
    # ⚠️ RODA NO `--seco` TAMBÉM. A direção é uma chamada de TEXTO, que custa
    # uma fração de uma imagem — e é exatamente ela que precisa ser conferida
    # antes de gastar. Um `--seco` que mostra um prompt diferente do que vai
    # rodar de verdade é pior que não ter `--seco`: aprova o que não testou.
    direcao = _direcao_visual(nicho, alvos)
    if direcao:
        print(f"   🎬 direção visual: {len(direcao)} cena(s) traduzidas\n")
    feitos = 0
    for n, titulo, apoio in alvos:
        p = (prompt_do_slide(nicho, direcao[n]) if n in direcao
             else prompt_do_slide(nicho, titulo, apoio))
        destino = saida / f"{n:02d}.png"
        print(f"  slide {n:02d} · {titulo[:46]}")
        if seco:
            print(f"     {p[:150]}…\n")
            continue
        erro = _gemini_imagem(p, destino)
        if erro:
            print(f"     ❌ {erro}")
            break                          # mesmo motivo do `gerar()`
        feitos += 1
        print(f"     ✅ {destino.name} ({destino.stat().st_size // 1024} KB)")
    if feitos:
        print(f"\n✅ {feitos} imagem(ns) em {saida}")
    return 0 if (feitos or seco) else 1


def _direcao_visual(nicho: str, alvos: list) -> dict:
    """Traduz o TEXTO de cada slide numa CENA fotografável. {n: briefing}.

    ⚠️ ESTE É O SALTO QUE O TESTE DE 24/08 REVELOU. Mandar o texto literal pro
    modelo de imagem funciona quando a frase é concreta ("Confira o fluxo do
    bico" → saiu bico e bebê mamando, ótimo) e falha quando é abstrata:

        "Você provavelmente erra em dois passos todo dia"
              ↓ o modelo não tem o que fotografar
        um bebê num trocador, sem mamadeira, sem erro, sem nada do assunto

    Frase abstrata não é fotografável. Alguém precisa decidir O QUE MOSTRAR
    quando o texto não mostra nada — e esse alguém é uma chamada de TEXTO, que
    custa uma fração da chamada de imagem. Por isso vem antes, e por isso vale
    a pena mesmo quando falha: se a direção não vier, cai no texto literal, que
    é o que já existia.

    Uma chamada só pro carrossel inteiro: além de mais barato, o modelo vê os
    slides juntos e não repete a mesma cena em dois deles."""
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not chave:
        return {}
    lista = "\n".join(f'{n}. {t} — {a[:120]}' for n, t, a in alvos)
    pedido = (
        f"Voce e diretor de arte de um perfil de Instagram do nicho '{nicho}'.\n"
        f"Para CADA slide abaixo, descreva UMA cena fotografavel que mostre o "
        f"assunto do slide. Regras:\n"
        f"- descreva OBJETOS, PESSOAS e AMBIENTE concretos, nunca conceitos\n"
        f"- se a frase for abstrata, escolha a cena que a pessoa veria na vida "
        f"real naquele momento\n"
        f"- nada de texto, letreiro, cartaz ou numero na cena\n"
        f"- cenas DIFERENTES entre si, sem repetir o mesmo enquadramento\n"
        f"- ate 25 palavras cada, em ingles\n"
        f"Responda SO um JSON: {{\"1\": \"cena\", \"2\": \"cena\"}}\n\n{lista}")
    try:
        from google import genai
        cli = genai.Client(api_key=chave)
        r = cli.models.generate_content(
            model=os.environ.get("GEMINI_MODELO_TXT", "gemini-2.5-flash"),
            contents=pedido)
        bruto = (r.text or "").strip()
        m = re.search(r"\{.*\}", bruto, re.S)
        dados = json.loads(m.group(0)) if m else {}
        return {int(k): str(v).strip() for k, v in dados.items()
                if str(v).strip()}
    except Exception as e:
        log.info(f"   ℹ️  sem direção visual ({str(e)[:70]}) — uso o texto cru")
        return {}


def prompt_do_slide(nicho: str, titulo: str, apoio: str = "") -> str:
    """O prompt da foto DESTE slide. O texto do slide é o briefing."""
    # ⚠️ TIRA O MARKUP. `*sem perceber*` e `[preço]` são instruções de REALCE
    # pro render — dentro de um prompt de imagem viram lixo que o modelo tenta
    # interpretar, e asterisco em prompt costuma virar ênfase de estilo.
    limpo = re.sub(r"[\*\[\]]", "", " ".join(x for x in (titulo, apoio) if x))
    # ⚠️ E TIRA O PREÇO. "Torneira com aquecedor: R$126,35 vale o dobro" foi pro
    # prompt inteiro no 1º teste. Preço num briefing de FOTO é um convite pro
    # modelo desenhar uma etiqueta com número — e número desenhado por IA sai
    # errado, some no véu, ou pior: sai CERTO e vira um preço gravado no pixel,
    # que a gente não consegue mais corrigir quando a Shopee mudar o valor. O
    # preço tem lugar próprio, a pílula do render, onde é texto de verdade.
    limpo = re.sub(r"R\$\s?[\d.,]+", "", limpo, flags=re.I)
    assunto = " ".join(limpo.split())[:260]
    return (
        f"Fotografia editorial realista para um post de Instagram do nicho "
        f"'{nicho}'. A cena deve mostrar CLARAMENTE o assunto: {assunto}. "
        f"Enquadramento vertical 4:5, luz baixa e quente, sombras marcadas, "
        f"profundidade de campo rasa, aparência cinematográfica e cara de foto "
        f"real — não ilustração, não 3D, não render. "
        # a régua de sempre: texto na imagem é o que mais denuncia montagem, e
        # o canto de cima à esquerda é onde a tipografia do slide vai pousar.
        f"Sem nenhum texto, sem palavras, sem letras, sem logotipos, sem "
        f"marcas d'água. Deixe espaço negativo limpo no canto superior "
        f"esquerdo para o título entrar por cima depois.")


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
    p.add_argument("--importar", metavar="NICHO",
                   help="põe no acervo as imagens baixadas do ChatGPT")
    p.add_argument("--de", nargs="+", metavar="CAMINHO", default=[],
                   help="pasta ou arquivos de onde importar")
    # `nargs="?"` + `const=""`: `--do-plano` sozinho pega a pasta mais recente
    p.add_argument("--do-plano", metavar="PASTA", dest="do_plano",
                   nargs="?", const="",
                   help="1 imagem por slide, do texto do slide (Gemini). "
                        "Sem argumento, usa o carrossel mais recente.")
    a = p.parse_args()

    if a.do_plano is not None:
        return do_plano(a.do_plano or None, a.seco)

    if a.importar:
        if not a.de:
            print("❌ falta o --de. Exemplo:\n"
                  f"   .venv/bin/python fundo_ia.py --importar {a.importar} "
                  f"--de ~/fundos-chatgpt/")
            return 1
        n = importar(a.importar, a.de)
        acervo = existentes(a.importar)
        print(f"\n{'✅' if n else '⚠️ '} {n} fundo(s) novo(s). "
              f"Acervo de '{a.importar}': {len(acervo)}.")
        if acervo:
            print(f"   Ver o carrossel usando eles:\n"
                  f"   .venv/bin/python carrossel_agendador.py "
                  f"--agora {a.importar}")
        return 0 if n else 1

    if a.prompt:
        cenas = CENARIOS.get(a.prompt, CENARIOS["geral"])
        n = min(a.quantos, len(cenas))
        print(f"🎨 {n} prompts pro nicho '{a.prompt}' — cole um por vez no "
              f"ChatGPT/Gemini/Fal.\n"
              f"   Formato: 1080x1350 (vertical 4:5). Salve em "
              f"{_pasta(a.prompt)}/\n"
              f"   ⚠️ São FUNDOS, não slides: sem texto, sem logo. O texto e a "
              f"marca entram por cima, no render.\n")
        for i in range(n):
            print(f"── {i + 1}/{n} " + "─" * 58)
            print(prompt_do_nicho(a.prompt, i))
            print()
        return 0
    if a.listar:
        print(f"📁 {FUNDOS}\n")
        pesados = 0
        for nicho in CENARIOS:
            arqs = existentes(nicho)
            marca = "✅" if arqs else "⬜"
            crus = [a for a in arqs if a.suffix.lower() != ".jpg"
                    or a.stat().st_size > 900_000]
            pesados += len(crus)
            aviso = f"  ⚠️  {len(crus)} sem normalizar" if crus else ""
            print(f"  {marca} {nicho:<8} {len(arqs)} fundo(s){aviso}")
        if pesados:
            # não é purismo: o fundo vira base64 dentro do HTML, e PNG cru
            # multiplica o tamanho do HTML por 4. Ver `importar()`.
            print("\n⚠️  Tem imagem crua (PNG ou >900 KB) no acervo. Funciona,"
                  "\n   mas pesa o render. Normalize sem sair do lugar:"
                  "\n   .venv/bin/python fundo_ia.py --importar casa "
                  "--de assets/fundos/casa/")
        print("\nPrompts:  python3 fundo_ia.py --prompt casa --quantos 10")
        print("Importar: python3 fundo_ia.py --importar casa --de ~/Downloads/")
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
