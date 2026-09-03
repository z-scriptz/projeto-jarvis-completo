#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# prompt_video_ia.py -- monta o prompt de vídeo por IA que NÃO deixa o produto
# virar outro no meio do clipe.
#
# POR QUE ISSO EXISTE (03/09/2026)
# ────────────────────────────────
# O Dre gerou no Runway Gen-4.5 um clipe de 10s tecnicamente excelente — luz,
# mãos corretas, física da projeção, 9:16 nativo — e o produto MUDOU quatro
# vezes em 10 segundos: disco oval com lente azul → corpo retangular → retângulo
# com lente verde → caixa com anel verde. O prompt dizia, com todas as letras,
# *"consistent product, no morphing"*. Não adiantou.
#
# Pra afiliado isso não é imperfeição, é a falha central: a pessoa clica e
# recebe outra coisa.
#
# O QUE CAUSA A DERIVA, na ordem em que importa
# ─────────────────────────────────────────────
#   1. TEXT-TO-VIDEO. O modelo não tem o produto — ele INVENTA um a cada cena.
#      Nenhuma frase de prompt conserta ausência de informação.
#   2. TROCA DE CENA. No clipe do Dre o produto mudou EXATAMENTE nos cortes
#      (quarto → mão → sala → pedestal). Cada corte é uma chance de reinventar.
#   3. DESCREVER O PRODUTO no modo imagem-para-vídeo. Contraintuitivo e é o
#      erro mais comum: se a foto JÁ define o produto, adjetivo no prompt só dá
#      licença pro modelo reinterpretar. No i2v o prompt descreve MOVIMENTO.
#
# ⚠️ O CRITÉRIO DE ACEITAÇÃO NÃO É "FICOU BONITO". É: **é o MESMO produto no
# primeiro e no último quadro?** O clipe do Runway reprovaria apesar de lindo.
#
# USO:
#   python3 prompt_video_ia.py --produto "Kit Lixador de Pé Elétrico"
#   python3 prompt_video_ia.py --produto "..." --modo texto     # p/ comparar
#   python3 prompt_video_ia.py --produto "..." --segundos 5

import argparse


def _creme() -> str:
    """⚠️ FUNDO CREME, NÃO BRANCO. Vídeo com fundo branco puro ao lado de foto
    creme na mesma conta lê como duas marcas.

    Lê a cor de `fotografia.CREME` (o mesmo valor que pinta as fotos tratadas)
    em vez de repetir o hex aqui — hex repetido é hex que um dia diverge. O
    literal só entra se o import falhar (fotografia puxa PIL/numpy)."""
    for mod in ("fotografia", "creative_engine.fotografia"):
        try:
            rgb = __import__(mod, fromlist=["CREME"]).CREME
            return "#%02X%02X%02X" % tuple(int(c) for c in rgb[:3])
        except Exception:
            continue
    return "#F2EEE6"          # fotografia.py:81 em 03/09/2026


FUNDO = (f"soft warm cream background ({_creme()}), "
         f"same tone as the product photo")

# O que NUNCA muda, em qualquer modo. Cada item saiu de um defeito observado.
NEGATIVO = ("no text, no captions, no watermark, no logos, no brand names, "
            "no scene change, no cuts, no camera teleport, "
            "no morphing, no shape change, no color change, "
            "no extra objects appearing, no duplicated product, "
            "no distorted hands, no extra fingers")

# ── MOVIMENTOS (modo imagem-para-vídeo) ──────────────────────────────────────
# Só movimento de CÂMERA ou movimento MÍNIMO do objeto. Nada que peça pro modelo
# desenhar uma parte que a foto não mostra — é aí que ele inventa.
MOVIMENTOS = {
    "giro": "the product slowly rotates in place about 30 degrees, "
            "camera locked, revealing its side profile",
    "aproxima": "slow smooth dolly-in toward the product, "
                "shallow depth of field settling on its surface",
    "luz": "the light slowly sweeps across the product from left to right, "
           "camera locked, revealing texture and material",
    "mao": "a hand enters from the right, picks the product up gently "
           "and holds it steady toward camera",
    "flutua": "the product floats and turns very slowly, "
              "soft studio light orbiting around it",
}


def prompt_imagem(produto: str, movimento: str = "giro", segundos: int = 5) -> str:
    """O modo CERTO pra afiliado: a foto real define o produto, o prompt só pede
    movimento. Repare que o NOME do produto não entra na descrição visual — ele
    é referência, não instrução de desenho."""
    mov = MOVIMENTOS.get(movimento, MOVIMENTOS["giro"])
    return (
        f"{segundos}s vertical 9:16 product video. "
        f"KEEP THE PRODUCT IN THE INPUT IMAGE EXACTLY AS IT IS — "
        f"identical shape, identical colors, identical proportions, "
        f"identical details and markings. Do not redesign it. "
        f"ONE single continuous shot, no cuts. "
        f"Motion: {mov}. "
        f"{FUNDO}. Soft diffused studio lighting, gentle shadow under the "
        f"product, premium commercial look, photorealistic, subtle natural "
        f"motion, steady camera. "
        f"({produto}) "
        f"NEGATIVE: {NEGATIVO}."
    )


def prompt_texto(produto: str, segundos: int = 10) -> str:
    """O modo que o Dre já testou. Fica aqui pra COMPARAÇÃO justa — mesma
    duração, mesmo produto — e com as duas travas que o prompt do ChatGPT não
    tinha: UMA cena só e um cenário só.

    ⚠️ Isto NÃO conserta o problema de fundo (o modelo continua inventando o
    produto). Só reduz a deriva DENTRO do clipe, tirando os cortes."""
    return (
        f"{segundos}s vertical 9:16 product video of a {produto}. "
        f"ONE single continuous locked shot in ONE single location. "
        f"No cuts, no scene changes, no location changes. "
        f"The product appears at second 1 and must remain the exact same object "
        f"until the end — same shape, same color, same size, same details. "
        f"Motion: slow dolly-in with a gentle light sweep across the product. "
        f"{FUNDO}. Soft diffused studio lighting, photorealistic, premium "
        f"commercial look, steady camera. "
        f"NEGATIVE: {NEGATIVO}."
    )


CRITERIO = """
═══ COMO JULGAR O CLIPE (não é "ficou bonito") ═══

  1. PRODUTO IDÊNTICO?  Pause no segundo 1 e no último segundo, lado a lado.
     Mesma forma, mesma cor, mesma lente/botão/alça? Se mudou, REPROVA —
     por mais bonito que esteja. Foi assim que o clipe do Runway reprovou.

  2. É O PRODUTO DA FOTO?  (só no modo imagem) Compare com a foto de entrada.
     "Parecido" não serve: a pessoa vai receber o da foto.

  3. MÃOS.  Se aparecer mão, conta os dedos.

  4. CORTE.  Teve troca de cena? Cada corte foi onde o produto derivou.

  5. PRIMEIRO SEGUNDO.  O produto já está em quadro? No Reel o gancho é 1-3s;
     clipe que "chega" no produto no segundo 4 desperdiça o que importa.

  Reprovar em 1, 2 ou 4 = o modelo não serve pra afiliado, independente do preço.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="prompt de vídeo por IA sem deriva")
    ap.add_argument("--produto", required=True)
    ap.add_argument("--modo", default="imagem", choices=("imagem", "texto"),
                    help="imagem = parte da foto real (o certo pra afiliado)")
    ap.add_argument("--movimento", default="giro", choices=tuple(MOVIMENTOS))
    ap.add_argument("--segundos", type=int, default=5)
    a = ap.parse_args()

    if a.modo == "imagem":
        print("═══ MODO IMAGEM-PARA-VÍDEO (suba uma foto de shared/fotos/) ═══\n")
        print(prompt_imagem(a.produto, a.movimento, a.segundos))
        print("\n⚠️ Suba a foto TRATADA (fundo creme, recorte limpo) — não a crua")
        print("   da Shopee. A foto é que define o produto; o prompt só move.")
    else:
        print("═══ MODO TEXTO-PARA-VÍDEO (só pra comparar com o teste do Runway) ═══\n")
        print(prompt_texto(a.produto, a.segundos))
        print("\n⚠️ Este modo INVENTA o produto. Serve pra medir quanto a trava de")
        print("   'uma cena só' reduz a deriva — não pra publicar.")
    print(CRITERIO)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
