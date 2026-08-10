#!/usr/bin/env python3
# asset_ranker.py -- os assets deste produto dão um vídeo, ou dão nove cortes
#                    da mesma coisa?
#
# POR QUE EXISTE (10/08)
# O Dre viu o piloto e disse: "só tem uma imagem durante todo o vídeo". O
# ChatGPT completou a ideia com a frase que define este arquivo:
#
#   "9 cortes não significam 9 informações visuais — o cérebro percebe que é a
#    mesma foto."
#
# E a coleta de mais imagem está BLOQUEADA na origem (Shopee, anti-bot
# error=90309999, três medições). Então o que sobra sob nosso controle é
# SELEÇÃO: saber o que temos antes de produzir, e não descobrir assistindo.
#
# O QUE ELE MEDE, E O QUE ELE NÃO MEDE
# ────────────────────────────────────
# Mede, deterministicamente, sem pedir opinião a modelo nenhum:
#   diversidade  as imagens são DIFERENTES entre si? (dHash + Hamming)
#   tamanho      dá pra fechar um close sem virar pixel?
#
# ⚠️ NÃO mede NITIDEZ, e isso foi uma REMOÇÃO, não um esquecimento.
# Eu tinha posto variância de Laplaciano com limiar 90. Calibrei contra fotos
# reais antes de mandar, e o número reprovou tudo. Pior: medindo cinco fotos
# reais (0,9 · 4,0 · 10,6 · 11,0 · 15,0) contra duas DEGRADADAS de propósito
# (esticada de 260px = 1,5 · comprimida a qualidade 8 = 7,3), a comprimida
# pontuou MAIS ALTO que duas fotos boas. Os intervalos se sobrepõem: a métrica
# não separa o que ela promete separar.
# Manter seria repetir o erro do `faixa_preenchida`, que reprovava o caso bom.
# Métrica que não distingue não é métrica rigorosa — é ruído com casa decimal.
#
# NÃO mede texto promocional queimado na foto — que foi o defeito da escova
# alisadora e briga com hook, legenda e CTA. Isso é trabalho pro Gemini Vision,
# e ele **só entra se a chave existir**. Sem chave, o campo sai `nao_avaliado`,
# NUNCA "aprovado". Fingir que avaliou é pior que não avaliar.
#
# A ESCADA DE MATERIAL (ideia do ChatGPT via Dre, adotada):
#   S  vídeo + 4 imagens distintas      produção completa
#   A  4+ imagens distintas
#   B  2-3 distintas (+ enquadramentos)
#   C  1 imagem boa (+ enquadramentos)  só com foto excelente
#   D  1 imagem ruim                    NÃO PRODUZIR
#
# ⚠️ DIVERSIDADE NÃO É QUANTIDADE. Cinco fotos quase iguais valem menos que
# duas diferentes — e este arquivo existe justamente pra dizer isso com número.
#
# Uso:
#   python3 asset_ranker.py --pasta shared/assets/338059094_42415534997
#   python3 asset_ranker.py --imagens a.jpg b.jpg c.jpg --json

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
EXT = (".jpg", ".jpeg", ".png", ".webp")

# Limiares. Todos calibráveis, e todos com motivo escrito.
DIST_IGUAIS = 0.14      # abaixo disto duas imagens são a MESMA pro olho
DIVERSIDADE_MIN = 0.28  # média abaixo disto: "tenho N fotos, é uma só"
LADO_MIN = 600          # abaixo disto o close do EDL vira borrão


def _log(m):
    print(f"[ranker] {m}", flush=True)


def dhash(caminho: Path, tam: int = 8) -> int:
    """Assinatura perceptual: 64 bits que descrevem a ESTRUTURA da imagem.

    Compara cada pixel com o vizinho da direita numa versão 9x8 em cinza. Duas
    fotos do mesmo produto em ângulos diferentes dão hashes distantes; a mesma
    foto recortada dá hashes próximos. É o que permite responder "isto é outra
    imagem ou é a mesma de novo?" sem pedir nada a modelo nenhum.
    """
    from PIL import Image
    with Image.open(caminho) as im:
        g = im.convert("L").resize((tam + 1, tam), Image.LANCZOS)
        px = list(g.convert('L').tobytes())
    bits = 0
    for y in range(tam):
        for x in range(tam):
            esq = px[y * (tam + 1) + x]
            dir_ = px[y * (tam + 1) + x + 1]
            bits = (bits << 1) | (1 if esq > dir_ else 0)
    return bits


def distancia(a: int, b: int) -> float:
    """0.0 = idênticas · 1.0 = nada a ver. Hamming normalizado."""
    return bin(a ^ b).count("1") / 64.0


def avaliar(imagens: list) -> dict:
    """Nota o CONJUNTO, não cada foto isolada.

    A pergunta que interessa não é "esta foto é boa?", e sim "com estas fotos
    dá pra fazer um vídeo que não pareça a mesma imagem nove vezes?".
    """
    from PIL import Image

    itens, hashes = [], []
    for caminho in imagens:
        try:
            with Image.open(caminho) as im:
                w, h = im.size
            hs = dhash(caminho)
        except Exception as e:
            itens.append({"arquivo": str(caminho), "erro": str(e)[:80]})
            continue
        problemas = []
        if min(w, h) < LADO_MIN:
            problemas.append(f"pequena ({w}x{h}; close vira borrão)")
        itens.append({"arquivo": Path(caminho).name, "largura": w, "altura": h,
                      "problemas": problemas})
        hashes.append((Path(caminho).name, hs))

    # ── diversidade: o número que o ChatGPT propôs, e ele estava certo ──────
    pares, iguais = [], []
    for i in range(len(hashes)):
        for j in range(i + 1, len(hashes)):
            d = distancia(hashes[i][1], hashes[j][1])
            pares.append(d)
            if d < DIST_IGUAIS:
                iguais.append((hashes[i][0], hashes[j][0], round(d, 3)))
    media = round(sum(pares) / len(pares), 3) if pares else 0.0

    bons = [i for i in itens if not i.get("erro") and not i["problemas"]]
    n_distintas = _quantas_distintas(hashes)

    # ── a escada ────────────────────────────────────────────────────────────
    if n_distintas >= 4 and bons:
        nivel = "A"
    elif n_distintas >= 2 and bons:
        nivel = "B"
    elif bons:
        nivel = "C"
    else:
        nivel = "D"

    return {
        "quantas": len(itens),
        "distintas": n_distintas,
        "diversidade": media,
        "pares_iguais": iguais,
        "nivel": nivel,
        "itens": itens,
        "texto_queimado": "nao_avaliado",   # só o Vision responde isto
        "veredito": _veredito(nivel, media, n_distintas),
    }


def _quantas_distintas(hashes) -> int:
    """Conta grupos de imagens realmente diferentes entre si.

    Duas fotos a menos de DIST_IGUAIS caem no mesmo grupo. É isso que impede
    "tenho 5 imagens" de virar argumento quando as 5 são a mesma.
    """
    grupos = []
    for nome, h in hashes:
        for g in grupos:
            if distancia(h, g[0]) < DIST_IGUAIS:
                g.append(h)
                break
        else:
            grupos.append([h])
    return len(grupos)


def _veredito(nivel: str, media: float, distintas: int) -> str:
    if nivel == "D":
        # texto ajustado quando a métrica de nitidez saiu: veredito que cita
        # critério que não existe mais manda procurar defeito onde não há
        return ("NÃO PRODUZIR: nenhuma imagem utilizável — todas abaixo de "
                f"{LADO_MIN}px de lado, o close do EDL viraria borrão")
    if distintas <= 1:
        return ("produzir com ressalva: UMA informação visual só. Os cortes "
                "vão parecer a mesma foto — o piloto deriva enquadramentos, "
                "mas isso disfarça, não resolve")
    if media < DIVERSIDADE_MIN:
        return (f"produzir com ressalva: {distintas} imagens distintas, mas a "
                f"diversidade média é baixa ({media}) — variam pouco entre si")
    return f"ok: {distintas} informações visuais distintas (diversidade {media})"


def main():
    p = argparse.ArgumentParser(
        description="Mede se os assets dão um vídeo ou nove cortes iguais.")
    p.add_argument("--pasta", help="pasta com as imagens do produto")
    p.add_argument("--imagens", nargs="*", default=[], help="arquivos soltos")
    p.add_argument("--json", action="store_true", help="saída em JSON")
    args = p.parse_args()

    arquivos = [Path(x) for x in args.imagens]
    if args.pasta:
        pasta = Path(args.pasta)
        if not pasta.is_dir():
            raise SystemExit(f"[ranker] não é pasta: {pasta}")
        arquivos += sorted(f for f in pasta.iterdir() if f.suffix.lower() in EXT)
    if not arquivos:
        p.error("use --pasta PASTA ou --imagens a.jpg b.jpg")

    r = avaliar(arquivos)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r["nivel"] != "D" else 1

    icone = {"S": "🏆", "A": "✅", "B": "👍", "C": "👀", "D": "❌"}[r["nivel"]]
    print()
    _log(f"{icone} NÍVEL {r['nivel']} · {r['quantas']} arquivo(s) · "
         f"{r['distintas']} distinta(s) · diversidade {r['diversidade']}")
    for i in r["itens"]:
        if i.get("erro"):
            print(f"   ✗ {i['arquivo']}: {i['erro']}")
            continue
        marca = "·" if not i["problemas"] else "⚠️"
        print(f"   {marca} {i['arquivo']:22} {i['largura']}x{i['altura']:<8} "
              f"{'; '.join(i['problemas'])}")
    for a, b, d in r["pares_iguais"]:
        print(f"   🔁 {a} e {b} são a MESMA imagem pro olho (distância {d})")
    print(f"\n   → {r['veredito']}")
    print("   (texto queimado na foto e nitidez: NÃO avaliados aqui. O "
          "primeiro precisa do Gemini Vision;")
    print("    o segundo eu tentei medir e a métrica não separou foto boa de "
          "foto degradada — então saiu)")
    return 0 if r["nivel"] != "D" else 1


if __name__ == "__main__":
    sys.exit(main())
