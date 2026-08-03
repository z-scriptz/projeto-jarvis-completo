# shared/termos.py
# TERMO DE BUSCA — transforma nome cru de produto em algo que a Shopee acha.
#
# Vive aqui porque dois agentes precisam da MESMA regra, e regra de busca que
# diverge entre eles vira bug difícil: a repescagem acha o produto, o validador
# não, e o mesmo item aparece vivo num lugar e morto no outro.
#
# Quem usa:
#   repescagem    procura de novo o produto cujo anúncio morreu
#   validar_fila  refaz a busca quando o nome cheio não devolve nada
#
# Medido na fila real de 03/08: de 15 buscas que voltaram VAZIAS, 13 tinham
# mais de 5 palavras, com mediana de 16. Ninguém procura na Shopee com 16
# palavras — e a relevância exige que a MAIORIA das palavras do termo apareça
# no título do candidato, então termo comprido reprova até o produto certo.

import re

# Lixo de título de vídeo. Não é nome de produto e só atrapalha a busca —
# "Capa transparente borda cromada shorts" não existe na Shopee.
LIXO_BUSCA = {"shorts", "short", "reels", "reel", "tiktok", "viral", "achadinho",
              "achadinhos", "promo", "oferta", "barato", "compre", "link", "bio"}

# Preposição e artigo não identificam produto nenhum e ainda gastam vaga das
# 5 palavras que a busca aceita.
LIGACAO = {"de", "da", "do", "dos", "das", "para", "pra", "com", "em", "no",
           "na", "nos", "nas", "e", "o", "a", "os", "as", "um", "uma", "por"}

# Quantas palavras mandar pra busca.
PALAVRAS_BUSCA = 5

# Abaixo disto não dá pra cortar mais nada sem sobrar termo vazio.
PALAVRAS_MIN = 2


def termo_de_busca(bruto: str) -> str:
    """Transforma o nome cru num termo que a Shopee encontra.

    Três defeitos vistos na VPS, os três causando 'não achei o produto':

    1. cauda de YouTube: 'Capa transparente borda cromada shorts'.
    2. corte no meio da palavra: o slug tem 40 caracteres, então sobra
       'Fones De O', 'Porcelana Ko', 'Estreito Ces'. Palavra picada não casa
       com nada e ainda conta contra a relevância.
    3. título de anúncio inteiro: 'Kit Pó Compacto Tira Brilho (6 opções) +
       Base 2 em 1 (8 opções) + Blush Duo Coradinha Rosada Fast Glam'. A busca
       devolve zero — vira 'Kit Pó Compacto Tira Brilho'.
    """
    t = re.sub(r"[^\w\s]", " ", bruto or "")
    palavras = [p for p in t.split() if p]
    # a última pode ser um pedaço de palavra, cortesia do corte em 40 chars
    if len(palavras) > PALAVRAS_MIN and len(palavras[-1]) <= 3:
        palavras.pop()
    uteis = []
    for p in palavras:
        b = p.lower()
        if b in LIXO_BUSCA or b in LIGACAO or len(p) < 2:
            continue                         # 'de'/'para' só gastam vaga
        uteis.append(p)
        if len(uteis) >= PALAVRAS_BUSCA:
            break                            # termo curto acha; termo longo não
    return " ".join(uteis)
