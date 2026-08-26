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
import time
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


# ⚠️ O ACERVO GANHOU UM NÍVEL: `assets/fundos/<nicho>/<formato>/`.
# O Dre está gerando 100 imagens POR NICHO organizadas por formato de carrossel
# (erros, comparação, checklist, lista, produto, antes-depois, CTA...). Isso é
# uma biblioteca de 600 imagens, e uma pasta chapada por nicho jogaria fora a
# informação mais valiosa que ela tem: **um fundo de "erros" e um de "checklist"
# não são intercambiáveis**. Com o formato na pasta, o rodízio deixa de ser
# "uma foto bonita do nicho" e vira "uma foto que combina com o que este
# carrossel está dizendo" — sem custar uma chamada de IA.
#
# A pasta rasa continua valendo: quem largar imagem direto em `fundos/casa/`
# tem o comportamento antigo, e é pra lá que o código cai quando o formato não
# tem acervo próprio. Nada do que já existe quebra.
# ⚠️ O DRE ORGANIZA A BIBLIOTECA COM OS NOMES DO CHATGPT; O BRAIN USA OS DELE.
# São listas parecidas e NÃO iguais, e a diferença é silenciosa: uma pasta
# `tech/curiosidade/` com 10 imagens ótimas nunca seria encontrada por um brain
# que chama aquilo de `historia`. Ninguém vê erro — o rodízio só cai na raiz e
# o trabalho de separação vira enfeite.
#
# Traduzir aqui é melhor que renomear 600 arquivos ou que obrigar o Dre a
# decorar os meus nomes: **a pasta pode se chamar do jeito que fizer sentido
# pra quem organiza.**
_ALIAS = {
    "curiosidade": "historia",      # "segredo revelado" — mesma estrutura
    "segredo": "historia",
    "antes-depois": "antes_depois",
    "antesdepois": "antes_depois",
    "comparação": "comparacao",
    "passo": "passo_a_passo",
    "passo-a-passo": "passo_a_passo",
    "problema-solucao": "problema_solucao",
    "nao-compre": "nao_compre",
    "naocompre": "nao_compre",
    "não_compre": "nao_compre",
    "top5": "lista",
    "ranking": "lista",
    "mitos_verdades": "mitos",
}


def _canon(formato: str) -> str:
    f = (formato or "").strip().lower().replace(" ", "_")
    return _ALIAS.get(f, f)


def _pasta(nicho: str, formato: str = "") -> Path:
    base = FUNDOS / (nicho or "geral").lower()
    return (base / _canon(formato)) if formato else base


# ⚠️ NÃO VOLTE ISTO PRA `*.jpg`. O `--gerar` do Fal salvava .jpg e por isso o
# glob era .jpg — mas quem alimenta o acervo hoje é o Dre, baixando do ChatGPT,
# e o ChatGPT baixa .PNG. Com o glob antigo o carrossel renderizaria sem fundo
# nenhum, SEM ERRO E SEM AVISO: `_fundo()` no slides_html.py só devolve "" e o
# slide sai bonito, só que liso. É a pior categoria de bug daqui — o que não
# reclama. O `--importar` normaliza pra .jpg, mas o glob aceita os quatro
# formatos pra que largar o arquivo na pasta na mão TAMBÉM funcione.
EXTENSOES = (".jpg", ".jpeg", ".png", ".webp")


def existentes(nicho: str, formato: str = "") -> list:
    """As imagens do nicho. Com `formato`, as daquele formato — e se ele não
    tiver acervo próprio, as da raiz do nicho."""
    def _dentro(p):
        if not p.exists():
            return []
        return sorted(a for a in p.iterdir()
                      if a.suffix.lower() in EXTENSOES and a.is_file())
    if formato:
        achadas = _dentro(_pasta(nicho, formato))
        if achadas:
            return achadas
    return _dentro(_pasta(nicho))


ALVO_L, ALVO_A = 1080, 1350


def _digestao(caminho) -> str:
    return hashlib.sha1(Path(caminho).read_bytes()).hexdigest()


def importar(nicho: str, origens: list, formato: str = "") -> int:
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

    destino = _pasta(nicho, formato)
    destino.mkdir(parents=True, exist_ok=True)
    # ⚠️ a deduplicação olha SÓ a pasta de destino. A mesma cena pode
    # legitimamente existir em `erros` e em `checklist` — são usos diferentes.
    jaTem = {_digestao(a) for a in destino.iterdir()
             if a.is_file() and a.suffix.lower() in EXTENSOES}
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
            base = f"{nicho.lower()}-{formato.lower()}" if formato else nicho.lower()
            saida = destino / f"{base}-{indice:02d}.jpg"
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


_STOP = {"de", "da", "do", "das", "dos", "e", "ou", "um", "uma", "uns", "umas",
         "o", "a", "os", "as", "que", "em", "no", "na", "nos", "nas", "por",
         "para", "pra", "com", "sem", "seu", "sua", "seus", "suas", "voce",
         "vc", "mais", "menos", "muito", "isso", "isto", "esse", "essa",
         "aquele", "ser", "ter", "faz", "fazer", "esta", "estao", "nao",
         "sim", "ja", "ainda", "todo", "toda", "todos", "todas", "cada"}


def _palavras(txt: str) -> set:
    import unicodedata
    t = unicodedata.normalize("NFKD", (txt or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {p for p in re.findall(r"[a-z]{3,}", t) if p not in _STOP}


def combinar(nicho: str, formato: str, assunto: str) -> str:
    """A imagem do acervo que MAIS TEM A VER com o assunto do slide.

    ⚠️ A BUSCA É DE TEXTO, NÃO DE IA — e é isso que a torna viável. O índice já
    guarda o que cada foto mostra; aqui só se conta quantas palavras do slide
    aparecem na descrição e nas tags. Custo: microssegundos, por post. Fazer
    isso com uma chamada de modelo a cada slide seria ~2.900 chamadas por mês
    pra escolher entre 10 fotos que já estão descritas em disco.

    ⚠️ E EMPATE VOLTA PRO RODÍZIO, de propósito. Sem isso, o melhor par
    texto↔foto de cada formato sairia em TODO carrossel daquele formato — a
    coerência subiria e a variedade morreria, que é o defeito que a gente
    passou uma semana consertando. O índice desempata; ele não manda sozinho."""
    idx = _indice()
    if not idx or not assunto:
        return ""
    alvo = _palavras(assunto)
    if not alvo:
        return ""
    candidatas = _todas(nicho)
    if formato:
        so_fmt = [c for c in candidatas
                  if c.parent.name == _canon(formato)]
        candidatas = so_fmt or candidatas

    placar = []
    for arq in candidatas:
        d = idx.get(str(arq.relative_to(FUNDOS)))
        if not d:
            continue
        dela = _palavras(d.get("desc", "")) | set(d.get("tags") or [])
        n = len(alvo & dela)
        if n:
            placar.append((n, str(arq)))
    if not placar:
        return ""
    melhor = max(p[0] for p in placar)
    # ⚠️ TODAS AS EMPATADAS NO TOPO, e o rodízio escolhe entre elas. Pegar
    # `max()` direto devolveria sempre o mesmo arquivo pro mesmo assunto.
    topo = [c for n, c in placar if n == melhor]
    return _rodizio(nicho + "|busca", topo)


def fundo_do_nicho(nicho: str, formato: str = "") -> str:
    """Um fundo do acervo do nicho. "" quando não há nenhum.

    ⚠️ RODÍZIO COM MEMÓRIA, NÃO SORTEIO — e isso vale DINHEIRO, não só estética.
    Com sorteio puro e N fundos, a chance de repetir o anterior é 1/N: com 6
    fundos e 8 carrosséis por semana, a mesma foto sairia repetida umas 1,3
    vezes por semana na MESMA conta. Guardando os últimos 3, os mesmos 6 fundos
    rendem o que 12 renderiam no sorteio — ou seja, **metade das imagens pra
    gerar**. É a mesma mecânica do rodízio dos fechos e do 1º comentário."""
    return _rodizio(nicho, [str(a) for a in existentes(nicho, formato)])


def _rodizio(chave: str, arqs: list) -> str:
    """Escolhe de `arqs` evitando os últimos usados sob `chave`.

    ⚠️ EXTRAÍDO DE DENTRO DO `fundo_do_nicho` (25/08) pra que a busca semântica
    use A MESMA memória em vez de reimplementar a dela. Duas memórias de
    rodízio no mesmo módulo seriam duas verdades sobre "o que já saiu" — e a
    segunda repetiria o que a primeira acabou de usar, com a aparência de estar
    funcionando."""
    if not arqs:
        return ""
    try:
        mem = json.loads(MEMORIA_FUNDO.read_text(encoding="utf-8"))
    except Exception:
        mem = {}
    recentes = mem.get(chave, [])
    novos = [a for a in arqs if a not in recentes]
    escolha = random.choice(novos or arqs)
    try:
        # lembra no máximo METADE do acervo: guardar demais esvazia a lista de
        # candidatos e o rodízio vira ordem fixa, que é o defeito oposto
        mem[chave] = ([escolha] + recentes)[:max(1, min(3, len(arqs) // 2))]
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
    return max(cands, key=_quando) if cands else None


def _quando(pasta) -> float:
    """A hora do arquivo MAIS NOVO dentro da pasta, não a da pasta.

    ⚠️ MTIME DE DIRETÓRIO NÃO É "MEXIDO POR ÚLTIMO". Ele só muda quando uma
    ENTRADA é criada ou removida — **reescrever um arquivo que já existe não
    mexe nele**. E o `--agora` reescreve `01.jpg`..`07.jpg` numa pasta que já
    os tinha, do mesmo dia. Resultado real (24/08): o Dre rodou `--agora tech`,
    a pasta `tech` ficou com o mtime da rodada ANTERIOR, a pasta `pet` (onde
    um `fundos/` tinha sido criado depois) ficou "mais nova" — e o `--do-plano`
    gerou 7 imagens de pet, pagas, enquanto ele testava tech.

    Ninguém erra sozinho aqui: o comando roda, imprime ✅ sete vezes, e o único
    sinal são os títulos dos slides falando de outro nicho no meio do log."""
    try:
        return max((a.stat().st_mtime for a in pasta.rglob("*") if a.is_file()),
                   default=pasta.stat().st_mtime)
    except Exception:
        return 0.0


# os dez papéis/formatos que a biblioteca usa — os nomes que o Dre e o ChatGPT
# combinaram. O `_ALIAS` traduz os que o brain chama de outra coisa.
FORMATOS_BIBLIOTECA = [
    "erros", "curiosidade", "comparacao", "antes_depois", "checklist",
    "lista", "produto", "problema_solucao", "nao_compre", "cta",
]


# ══════════════════════════════════════════════════════════════════════════
# ÍNDICE SEMÂNTICO — o que cada imagem MOSTRA
#
# ⚠️ O DIAGNÓSTICO QUE O DRE E O CHATGPT FIZERAM JUNTOS (25/08): o render está
# resolvido, o gargalo virou a ESCOLHA DA IMAGEM. Num carrossel de casa saiu:
#     "escolher a árvore"     → foto de cesto com manta
#     "abrir os galhos"       → foto de escritório com luminária
#     checklist da árvore     → foto de guarda-roupa antes/depois
# Texto e imagem contando duas histórias diferentes, o que mata retenção.
#
# A biblioteca por formato resolveu METADE do problema: ela garante que um
# carrossel de `erros` pegue fotos da pasta `erros`. Mas dentro da pasta o
# sorteio continua cego — e a frase do Dre nomeia o que falta: *"se o Jarvis
# ver a imagem e conseguir interpretar, vai ser um passo absurdo"*.
#
# ⚠️ E O CUSTO É O PONTO DE PROJETO. Perguntar a uma IA "qual destas 10 fotos
# combina com este slide?" a cada render seria uma chamada por SLIDE, todo dia,
# em 6 contas — o mesmo erro do fundo gerado por post que a gente já rejeitou.
# Aqui a visão passa UMA VEZ POR IMAGEM, na vida: descreve, guarda no índice, e
# daí em diante a escolha é comparação de texto, que custa zero.
#
#     230 imagens × 1 chamada  =  custo fixo, pago uma vez
#     8 slides × 2 posts/dia × 6 contas × 30 dias = 2.880 chamadas/mês evitadas
INDICE = FUNDOS / "indice.json"


def _indice() -> dict:
    try:
        return json.loads(INDICE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _descrever(caminho: Path) -> dict:
    """Uma frase e umas tags do que a foto MOSTRA. {} quando não deu."""
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not chave:
        return {}
    try:
        from google import genai
        from google.genai import types
        cli = genai.Client(api_key=chave)
        r = cli.models.generate_content(
            model=os.environ.get("GEMINI_MODELO_TXT", "gemini-2.5-flash"),
            contents=[
                types.Part.from_bytes(data=caminho.read_bytes(),
                                      mime_type="image/jpeg"),
                "Descreva em portugues o que esta foto MOSTRA, para escolher "
                "fundo de post. Responda SO um JSON:\n"
                '{"desc": "<uma frase curta e concreta>",\n'
                ' "tags": ["<objeto>", "<comodo/lugar>", "<acao>", "..."]}\n'
                "As tags sao substantivos simples em portugues, ate 8, "
                "so o que aparece de fato na imagem.",
            ])
        m = re.search(r"\{.*\}", (r.text or ""), re.S)
        d = json.loads(m.group(0)) if m else {}
        return {"desc": str(d.get("desc") or "")[:200],
                "tags": [str(t).lower().strip() for t in (d.get("tags") or [])
                         if str(t).strip()][:8]}
    except Exception as e:
        log.info(f"   ℹ️  não descrevi {caminho.name}: {str(e)[:70]}")
        return {}


def indexar(nicho: str = "", limite: int = 0) -> int:
    """Descreve as imagens ainda não descritas. Retomável de propósito.

    ⚠️ RETOMÁVEL PORQUE SÃO CENTENAS E A REDE CAI. Se o índice fosse refeito do
    zero a cada execução, uma queda no meio de 230 imagens jogaria fora tudo o
    que já foi pago. Cada imagem é gravada assim que descrita; rodar de novo
    continua de onde parou, e `--limite` deixa provar com 5 antes de soltar."""
    idx = _indice()
    alvos = []
    nichos = [nicho] if nicho else list(CENARIOS)
    for n in nichos:
        for arq in _todas(n):
            if str(arq.relative_to(FUNDOS)) not in idx:
                alvos.append(arq)
    if limite:
        alvos = alvos[:limite]
    if not alvos:
        print(f"✅ nada a fazer — {len(idx)} imagem(ns) já descritas.")
        return 0

    print(f"🔎 descrevendo {len(alvos)} imagem(ns)"
          + (f" (limite {limite})" if limite else "") + "\n")
    feitas = 0
    for arq in alvos:
        rel = str(arq.relative_to(FUNDOS))
        d = _descrever(arq)
        if not d.get("desc"):
            print(f"  ⚠️  {rel}: sem descrição — paro por aqui")
            break                      # mesmo motivo do `gerar()`
        idx[rel] = d
        INDICE.parent.mkdir(parents=True, exist_ok=True)
        INDICE.write_text(json.dumps(idx, ensure_ascii=False, indent=1),
                          encoding="utf-8")
        feitas += 1
        print(f"  ✅ {rel}\n     {d['desc'][:88]}\n     {', '.join(d['tags'])}")
    print(f"\n{'✅' if feitas else '⚠️ '} {feitas} descrita(s). "
          f"Índice: {len(idx)} imagem(ns) em {INDICE}")
    return 0 if feitas else 1


def _todas(nicho: str) -> list:
    """Todas as imagens do nicho, raiz e subpastas."""
    base = _pasta(nicho)
    if not base.exists():
        return []
    return sorted(a for a in base.rglob("*")
                  if a.is_file() and a.suffix.lower() in EXTENSOES)


def contato(nicho: str, saida=None) -> int:
    """Uma folha de contato POR FORMATO — grade de miniaturas num JPEG só.

    ⚠️ NASCEU DE UMA LIMITAÇÃO REAL, NÃO DE CAPRICHO. O Dre gerou 260 imagens e
    perguntou se eu conseguia olhar. Eu não vejo o disco da VPS nem a área de
    trabalho dele; e mesmo publicando com `midia_publica --ver`, 130 imagens
    são 130 arquivos pra baixar e olhar um por um — na prática, não revisa.
    Uma grade de 25 numa folha eu leio de uma vez, e o que salta (foto clara no
    meio de escuras, cena repetida, enquadramento errado) salta JUNTO, que é o
    que a revisão precisa enxergar.

    O nome do arquivo vai queimado em cada célula: sem isso eu diria "a terceira
    da segunda linha está estranha" e ninguém saberia qual é."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("❌ falta o Pillow — use o .venv")
        return 1

    base = _pasta(nicho)
    if not base.exists():
        print(f"❌ não achei {base}")
        return 1
    saida = Path(saida) if saida else (BASE_DIR / "pronto_carrossel"
                                       / f"contato_{nicho}")
    saida.mkdir(parents=True, exist_ok=True)

    grupos = []
    soltas = [a for a in sorted(base.iterdir())
              if a.is_file() and a.suffix.lower() in EXTENSOES]
    if soltas:
        grupos.append(("raiz", soltas))
    for d in sorted(x for x in base.iterdir() if x.is_dir()):
        fotos = [a for a in sorted(d.iterdir())
                 if a.is_file() and a.suffix.lower() in EXTENSOES]
        if fotos:
            grupos.append((d.name, fotos))
    if not grupos:
        print(f"⚠️  nenhuma imagem em {base}")
        return 1

    COL, CEL, PAD, TOPO = 5, 300, 8, 46
    feitas = 0
    for nome, fotos in grupos:
        linhas = (len(fotos) + COL - 1) // COL
        alt_cel = int(CEL * 1.25)          # as fontes são 4:5
        larg = COL * (CEL + PAD) + PAD
        alt = TOPO + linhas * (alt_cel + PAD) + PAD
        folha = Image.new("RGB", (larg, alt), (22, 22, 24))
        d = ImageDraw.Draw(folha)
        # ⚠️ SÓ ASCII NO CABEÇALHO. A fonte embutida do PIL não tem travessão
        # nem acento: o "—" saiu como quadradinho vazio na 1ª folha. Detalhe
        # bobo, mas a folha existe pra ser LIDA — caractere quebrado no título
        # é a primeira coisa que o olho encontra.
        d.text((PAD + 4, 14), f"{nicho} / {nome}  -  {len(fotos)} imagens",
               fill=(235, 235, 235))
        for i, f in enumerate(fotos):
            try:
                im = Image.open(f).convert("RGB")
            except Exception:
                continue
            im = im.resize((CEL, alt_cel), Image.LANCZOS)
            x = PAD + (i % COL) * (CEL + PAD)
            y = TOPO + (i // COL) * (alt_cel + PAD)
            folha.paste(im, (x, y))
            # etiqueta com o nome, pra dar pra apontar qual é qual
            d.rectangle([x, y + alt_cel - 22, x + CEL, y + alt_cel],
                        fill=(0, 0, 0))
            d.text((x + 5, y + alt_cel - 18), f.stem[:44], fill=(255, 255, 255))
        alvo = saida / f"{nicho}-{nome}.jpg"
        folha.save(alvo, "JPEG", quality=82, optimize=True)
        feitas += 1
        print(f"  🗂️  {alvo.name}  ({len(fotos)} imagens, "
              f"{alvo.stat().st_size // 1024} KB)")

    print(f"\n✅ {feitas} folha(s) em {saida}")
    print(f"   Publique pra revisão:  midia_publica.py --ver {saida}")
    return 0


_MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
          "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
_RX_TS = re.compile(r"(\d{1,2})\s+de\s+(\w{3})\w*\.?\s+de\s+(\d{4}),?\s+"
                    r"(\d{2})[_:h](\d{2})[_:](\d{2})", re.I)


def _quando_baixou(arq: Path) -> float:
    """A hora do download — LIDA DO NOME quando dá, senão do `mtime`.

    ⚠️ O `mtime` NÃO SOBREVIVE AO `scp`. Sem `-p`, todo arquivo chega na VPS com
    a hora da transferência, e aí ordenar por `mtime` devolve a ordem em que o
    shell expandiu o `*.png` — **alfabética**. Alfabética junta `(1)`, `(10)`,
    `(2)`, `(3)`: os blocos originais viram picadinho e o `--lotes` entregaria
    grupos errados com toda a cara de certos.

    Mas o ChatGPT carimba a hora NO NOME do arquivo ("ChatGPT Image 24 de ago.
    de 2026, 15_29_23 (4).png"), e nome sobrevive a qualquer cópia. O `mtime`
    vira só o plano B, pra imagem que veio de outra fonte."""
    m = _RX_TS.search(arq.name)
    if m:
        try:
            import datetime as _dt
            d, mes, ano, h, mi, s = m.groups()
            mesn = _MESES.get(mes[:3].lower())
            if mesn:
                return _dt.datetime(int(ano), mesn, int(d), int(h), int(mi),
                                    int(s)).timestamp()
        except Exception:
            pass
    return arq.stat().st_mtime


def _agrupar(fotos: list, tamanho: int, folga: int = 90) -> list:
    """Corta a lista em blocos por BURACO DE TEMPO, não a cada N fixo.

    ⚠️ CORTAR DE 10 EM 10 SÓ FUNCIONA SE TODO BLOCO TIVER 10. O acervo do Dre
    tem lotes de 10, mas também tem avulsas (uma imagem sozinha às 17_31_40) e
    lotes incompletos. Um único bloco de 9 desalinha TODO o resto da lista — e o
    erro não aparece: sai um `lote-14` misturando o fim de um formato com o
    começo de outro, e ninguém percebe até ver o carrossel.

    O download de um lote leva segundos; entre um lote e o outro passam
    dezenas. Cortar onde o buraco é grande devolve os blocos REAIS. O `tamanho`
    vira só um teto de segurança."""
    if not fotos:
        return []
    blocos, atual = [], [fotos[0]]
    for ant, foto in zip(fotos, fotos[1:]):
        gap = _quando_baixou(foto) - _quando_baixou(ant)
        if gap > folga or len(atual) >= tamanho:
            blocos.append(atual)
            atual = []
        atual.append(foto)
    if atual:
        blocos.append(atual)
    return blocos


def lotes(pasta, tamanho: int = 10, saida=None) -> int:
    """Reconstrói os blocos de download pela HORA e monta uma folha por bloco.

    ⚠️ O PROBLEMA REAL (24/08): o Dre baixou ~260 imagens em blocos de 10, todas
    caíram juntas em `Downloads`, e ele não lembra a ordem. Sem isso, as 260
    viram um monte só — o acervo funciona, mas perde a separação por nicho e
    formato que custou horas pra gerar.

    A memória de quem baixou falha; o **carimbo de tempo do arquivo, não**. O
    ChatGPT entrega os blocos em sequência, então ordenar por data e cortar de
    `tamanho` em `tamanho` devolve os blocos originais. O que o relógio NÃO
    sabe é o que cada bloco É — e é aí que entra a folha de contato: eu olho e
    digo "esse é pet", "esse é tech/produto". **Máquina reconstrói a ordem,
    olho humano põe o rótulo.** Nenhum dos dois faria o trabalho sozinho."""
    try:
        from PIL import Image
    except ImportError:
        print("❌ falta o Pillow — use o .venv")
        return 1
    pasta = Path(pasta).expanduser()
    brutas = [a for a in pasta.iterdir()
              if a.is_file() and a.suffix.lower() in EXTENSOES]
    if not brutas:
        print(f"❌ nenhuma imagem em {pasta}")
        return 1
    fotos = sorted(brutas, key=_quando_baixou)

    saida = Path(saida) if saida else BASE_DIR / "pronto_carrossel" / "lotes"
    if saida.exists():
        import shutil as _sh
        _sh.rmtree(saida)
    saida.mkdir(parents=True, exist_ok=True)

    blocos = _agrupar(fotos, tamanho)
    mapa = {}
    print(f"📦 {len(fotos)} imagem(ns) → {len(blocos)} lote(s) de {tamanho}\n")
    for n, bloco in enumerate(blocos, start=1):
        nome = f"lote-{n:02d}"
        mapa[nome] = {"nicho": "", "formato": "",
                      "arquivos": [str(a) for a in bloco]}
        _folha(bloco, saida / f"{nome}.jpg",
               f"{nome}  -  {len(bloco)} imagens  -  "
               f"{time.strftime('%d/%m %H:%M', time.localtime(_quando_baixou(bloco[0])))}")
        # ⚠️ MESMA FONTE DE HORA QUE O AGRUPAMENTO. Na 1ª rodada o corte já
        # usava a hora do NOME e o display ainda lia `mtime`: as 27 folhas
        # saíram todas com "17:51–17:55", que é a hora do `scp`. O agrupamento
        # estava CERTO e o relatório dizia o contrário — eu mesmo desconfiei do
        # próprio código olhando aquilo. Diagnóstico que mente é pior que
        # diagnóstico nenhum, e esta é a terceira vez que anoto isso.
        print(f"  🗂️  {nome}.jpg   "
              f"{time.strftime('%d/%m %H:%M', time.localtime(_quando_baixou(bloco[0])))}"
              f"  ({len(bloco)})")

    arq = saida / "lotes.json"
    arq.write_text(json.dumps(mapa, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n✅ folhas em {saida}")
    print(f"   1) publique:  midia_publica.py --ver {saida}")
    print(f"   2) preencha 'nicho' e 'formato' em {arq.name}")
    print(f"   3) aplique:   fundo_ia.py --aplicar-lotes {arq}")
    return 0


def _folha(fotos: list, alvo: Path, titulo: str) -> None:
    """A grade — usada pelo `--contato` e pelo `--lotes`."""
    from PIL import Image, ImageDraw
    COL, CEL, PAD, TOPO = 5, 300, 8, 46
    linhas = (len(fotos) + COL - 1) // COL
    alt_cel = int(CEL * 1.25)
    folha = Image.new("RGB", (COL * (CEL + PAD) + PAD,
                              TOPO + linhas * (alt_cel + PAD) + PAD),
                      (22, 22, 24))
    d = ImageDraw.Draw(folha)
    d.text((PAD + 4, 14), titulo, fill=(235, 235, 235))
    for i, f in enumerate(fotos):
        try:
            im = Image.open(f).convert("RGB").resize((CEL, alt_cel),
                                                     Image.LANCZOS)
        except Exception:
            continue
        x = PAD + (i % COL) * (CEL + PAD)
        y = TOPO + (i // COL) * (alt_cel + PAD)
        folha.paste(im, (x, y))
        d.rectangle([x, y + alt_cel - 22, x + CEL, y + alt_cel], fill=(0, 0, 0))
        d.text((x + 5, y + alt_cel - 18), f.stem[-40:], fill=(255, 255, 255))
    alvo.parent.mkdir(parents=True, exist_ok=True)
    folha.save(alvo, "JPEG", quality=82, optimize=True)


def aplicar_lotes(arquivo) -> int:
    """Lê o `lotes.json` já rotulado e importa cada bloco pro lugar certo."""
    arq = Path(arquivo).expanduser()
    try:
        mapa = json.loads(arq.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ não li {arq}: {e}")
        return 1
    total, pulados = 0, []
    for nome, info in mapa.items():
        nicho = (info.get("nicho") or "").strip().lower()
        if not nicho:
            pulados.append(nome)
            continue
        formato = (info.get("formato") or "").strip()
        arquivos = [Path(a) for a in info.get("arquivos") or []]
        arquivos = [a for a in arquivos if a.exists()]
        if not arquivos:
            print(f"  ⚠️  {nome}: os arquivos não estão mais lá")
            continue
        print(f"\n📂 {nome} → {nicho}" + (f"/{formato}" if formato else ""))
        total += importar(nicho, arquivos, formato)
    print(f"\n{'✅' if total else '⚠️ '} {total} imagem(ns) importada(s).")
    if pulados:
        # ⚠️ pular calado seria o pior desfecho: o Dre acharia que importou
        # tudo e o acervo ficaria menor do que ele pensa, sem sinal nenhum.
        print(f"⬜ {len(pulados)} lote(s) sem 'nicho' preenchido, não "
              f"importados: {', '.join(pulados[:10])}"
              f"{'…' if len(pulados) > 10 else ''}")
    return 0 if total else 1


def _nichos_conhecidos() -> set:
    """Os nichos que o sistema realmente atende — do contas.json, mais 'geral'.

    Lê do contas.json em vez de manter uma lista aqui porque a lista aqui
    envelheceria: pet e moda existiram semanas no contas.json antes de qualquer
    outro arquivo saber deles."""
    # ⚠️ UNIÃO, não substituição. Se o contas.json estiver ilegível — ou se o
    # Dre estiver montando a biblioteca de um nicho ANTES de criar a conta,
    # que é a ordem natural — recusar um nicho válido bloquearia uma
    # importação boa. Errar pro lado de aceitar aqui custa uma pasta a mais;
    # errar pro lado de recusar custa a importação que ele veio fazer.
    nichos = {"geral", "beleza", "tech", "casa", "pet", "moda"}
    try:
        c = json.loads((BASE_DIR / "contas.json").read_text(encoding="utf-8"))
        for chave, conta in c.items():
            if isinstance(conta, dict):
                nichos.add((conta.get("nicho") or "geral") if chave == "_default"
                           else chave.lower())
    except Exception:
        pass
    return nichos


def _nicho_da_pasta(nome: str) -> str:
    """'fundos-casa' → 'casa'. Nome desconhecido → "" (e quem chama recusa).

    ⚠️ O `--arvore` pegava `nicho_dir.name.lower()` CRU, e em 25/08 o Dre rodou
    `--arvore ~/fundos-chatgpt` numa árvore cujas pastas se chamam
    `fundos-casa`, `fundos-tech`… Resultado: nasceu um acervo em
    `fundos/fundos-casa/` com 10 imagens que NENHUM carrossel jamais leria,
    porque o nicho se chama `casa`. E o comando disse "✅ 10 imagem(ns)
    importada(s)" — sucesso completo, efeito zero.

    📌 Importar pra um nome que não existe é o pior tipo de falha: ela se
    parece com sucesso e só aparece semanas depois, como "por que esse nicho
    não tem fundo?". Por isso aqui o desconhecido é RECUSADO, não criado."""
    n = re.sub(r"^fundos?[-_]", "", str(nome or "").strip().lower())
    return n if n in _nichos_conhecidos() else ""


def importar_arvore(raiz) -> int:
    """Importa `<raiz>/<nicho>/<formato>/*` de uma vez só.

    ⚠️ ISTO SUBSTITUI UM LAÇO DE BASH QUE EU TINHA MANDADO O DRE COLAR — e
    laço colado é onde mora o erro que ninguém vê. São 60 pastas: um `for`
    escrito errado importa metade, e "metade" não aparece em lugar nenhum
    depois. Com um comando só, o programa é que sabe a estrutura, e o
    relatório do fim diz exatamente quantas entraram em cada formato."""
    raiz = Path(raiz).expanduser()
    if not raiz.is_dir():
        print(f"❌ não achei a pasta {raiz}")
        return 1
    # ⚠️ IMAGEM SOLTA NA RAIZ DA ÁRVORE ERA IGNORADA EM SILÊNCIO. O laço abaixo
    # só percorre DIRETÓRIOS — quem largasse os PNGs direto em `~/fundos/` via
    # "⚠️ 0 imagem(ns) importada(s)" e nenhuma explicação. Não dá pra adivinhar
    # o nicho de um arquivo solto (é justamente o que a pasta diz), então aqui
    # eu não chuto: eu conto e mando usar o `--importar`, que pede o nicho.
    soltas_raiz = [a for a in raiz.iterdir()
                   if a.is_file() and a.suffix.lower() in EXTENSOES]
    if soltas_raiz:
        print(f"⚠️  {len(soltas_raiz)} imagem(ns) solta(s) na raiz de {raiz.name}/ "
              f"— o --arvore só lê <nicho>/<formato>/, então elas ficaram de "
              f"fora.\n   Pra essas, diga o nicho: "
              f"`--importar <nicho> --de {raiz}` (+ `--formato <formato>`)")

    total, vazias, recusadas = 0, [], []
    for nicho_dir in sorted(d for d in raiz.iterdir() if d.is_dir()):
        nicho = _nicho_da_pasta(nicho_dir.name)
        if not nicho:
            recusadas.append(nicho_dir.name)
            continue
        if nicho != nicho_dir.name.lower():
            # o mapeamento tem que APARECER: importação silenciosa pra outro
            # nome é como o defeito nasceu.
            print(f"\n📂 {nicho_dir.name}  →  nicho '{nicho}'")
        subs = sorted(d for d in nicho_dir.iterdir() if d.is_dir())
        soltas = [a for a in nicho_dir.iterdir()
                  if a.is_file() and a.suffix.lower() in EXTENSOES]
        if soltas:
            print(f"\n📂 {nicho}  (raiz)")
            total += importar(nicho, [nicho_dir])
        for sub in subs:
            fotos = [a for a in sub.iterdir()
                     if a.is_file() and a.suffix.lower() in EXTENSOES]
            if not fotos:
                vazias.append(f"{nicho}/{sub.name}")
                continue
            print(f"\n📂 {nicho}/{sub.name}  →  {_canon(sub.name)}")
            total += importar(nicho, [sub], sub.name)
    print(f"\n{'✅' if total else '⚠️ '} {total} imagem(ns) importada(s).")
    if recusadas:
        print(f"\n❌ {len(recusadas)} pasta(s) IGNORADA(S) — o nome não "
              f"corresponde a nenhum nicho: {', '.join(recusadas[:8])}"
              f"{'…' if len(recusadas) > 8 else ''}")
        print(f"   nichos válidos: {', '.join(sorted(_nichos_conhecidos()))}")
        print(f"   (renomeie a pasta, ou use "
              f"`--importar <nicho> --de <pasta> --formato <formato>`)")
    if vazias:
        # não é erro: pasta vazia é formato que ainda não foi gerado. Mas
        # precisa aparecer, senão some no meio de 60 linhas de sucesso.
        print(f"⬜ {len(vazias)} pasta(s) ainda sem imagem: "
              f"{', '.join(vazias[:8])}{'…' if len(vazias) > 8 else ''}")
    return 0 if total else 1


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
    p.add_argument("--formato", metavar="FORMATO", default="",
                   help="erros, lista, checklist, comparacao, antes_depois... "
                        "guarda em fundos/<nicho>/<formato>/")
    # `nargs="?"` + `const=""`: `--do-plano` sozinho pega a pasta mais recente
    p.add_argument("--arvore", metavar="RAIZ",
                   help="importa uma árvore inteira <nicho>/<formato>/ de uma vez")
    p.add_argument("--indexar", metavar="NICHO", nargs="?", const="",
                   help="descreve o que cada imagem MOSTRA (1x por imagem)")
    p.add_argument("--limite", type=int, default=0,
                   help="com --indexar, para depois de N imagens")
    p.add_argument("--buscar", nargs=2, metavar=("NICHO", "ASSUNTO"),
                   help="mostra qual imagem o índice escolheria")
    p.add_argument("--lotes", metavar="PASTA",
                   help="reconstrói os blocos de download pela hora do arquivo")
    p.add_argument("--tamanho", type=int, default=10,
                   help="imagens por lote (padrão 10)")
    p.add_argument("--aplicar-lotes", metavar="JSON", dest="aplicar_lotes",
                   help="importa os lotes já rotulados no lotes.json")
    p.add_argument("--contato", metavar="NICHO",
                   help="folha de contato: grade de miniaturas por formato")
    p.add_argument("--criar-arvore", metavar="RAIZ",
                   help="cria as pastas <nicho>/<formato>/ vazias, pra receber")
    p.add_argument("--do-plano", metavar="PASTA", dest="do_plano",
                   nargs="?", const="",
                   help="1 imagem por slide, do texto do slide (Gemini). "
                        "Sem argumento, usa o carrossel mais recente.")
    a = p.parse_args()

    if a.indexar is not None:
        return indexar(a.indexar, a.limite)

    if a.buscar:
        n, assunto = a.buscar
        r = combinar(n, a.formato, assunto)
        idx = _indice()
        if not r:
            print(f"⚠️  nada casou com '{assunto}' em '{n}'"
                  + (f"/{a.formato}" if a.formato else "")
                  + (f"  ({len(idx)} no índice)" if idx else
                     "  — índice vazio, rode --indexar"))
            return 1
        d = idx.get(str(Path(r).relative_to(FUNDOS)), {})
        print(f"🎯 {r}\n   {d.get('desc','')}\n   {', '.join(d.get('tags') or [])}")
        return 0

    if a.lotes:
        return lotes(a.lotes, a.tamanho)

    if a.aplicar_lotes:
        return aplicar_lotes(a.aplicar_lotes)

    if a.contato:
        return contato(a.contato)

    if a.criar_arvore:
        raiz = Path(a.criar_arvore).expanduser()
        n = 0
        for nicho in CENARIOS:
            for f in FORMATOS_BIBLIOTECA:
                (raiz / nicho / f).mkdir(parents=True, exist_ok=True)
                n += 1
        print(f"📁 {n} pasta(s) em {raiz}\n")
        print("   Agora mande as imagens pra dentro delas. Do Windows:")
        print(f"   scp \"C:\\...\\moda-erros\\*.png\" "
              f"root@SEU_HOST:{raiz}/moda/erros/\n")
        print(f"   Depois:  fundo_ia.py --arvore {raiz}")
        return 0

    if a.arvore:
        return importar_arvore(a.arvore)

    if a.do_plano is not None:
        return do_plano(a.do_plano or None, a.seco)

    if a.importar:
        if not a.de:
            print("❌ falta o --de. Exemplo:\n"
                  f"   .venv/bin/python fundo_ia.py --importar {a.importar} "
                  f"--de ~/fundos-chatgpt/")
            return 1
        n = importar(a.importar, a.de, a.formato)
        acervo = existentes(a.importar, a.formato)
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
            base = _pasta(nicho)
            raiz = [a for a in base.iterdir()
                    if a.is_file() and a.suffix.lower() in EXTENSOES] \
                if base.exists() else []
            subs = sorted(d for d in base.iterdir() if d.is_dir()) \
                if base.exists() else []
            total = len(raiz) + sum(len(existentes(nicho, d.name)) for d in subs)
            marca = "✅" if total else "⬜"
            print(f"  {marca} {nicho:<8} {total:>3} fundo(s)"
                  + (f"  ·  {len(raiz)} na raiz" if raiz else ""))
            for d in subs:
                n = len([a for a in d.iterdir() if a.is_file()
                         and a.suffix.lower() in EXTENSOES])
                print(f"        └ {d.name:<16} {n:>3}")
            crus = [a for a in raiz if a.suffix.lower() != ".jpg"
                    or a.stat().st_size > 900_000]
            pesados += len(crus)
        if pesados:
            # não é purismo: o fundo vira base64 dentro do HTML, e PNG cru
            # multiplica o tamanho do HTML por 4. Ver `importar()`.
            print("\n⚠️  Tem imagem crua (PNG ou >900 KB) no acervo. Funciona,"
                  "\n   mas pesa o render. Normalize sem sair do lugar:"
                  "\n   .venv/bin/python fundo_ia.py --importar casa "
                  "--de assets/fundos/casa/")
        print("\nPrompts:  python3 fundo_ia.py --prompt casa --quantos 10")
        print("Importar: python3 fundo_ia.py --importar casa --de ~/Downloads/")
        print("  por formato:  --importar casa --formato erros --de ~/erros/")
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
