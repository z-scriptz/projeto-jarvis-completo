#!/usr/bin/env python3
"""O pipeline de fotografia da TopShop: foto crua de marketplace → catálogo.

⚠️ O PROBLEMA NÃO É FOTO FEIA, É FOTO DIFERENTE
────────────────────────────────────────────────
Uma grade de 300 fotos com 300 fundos diferentes é ruído, por melhor que cada
uma seja. Trezentas no mesmo chão viram catálogo mesmo vindo de 300 vendedores.
Consistência é o que lê como direção de arte; qualidade individual vem depois.

AS TRÊS CLASSES (e onde cada uma pode aparecer)
───────────────────────────────────────────────
  A — editorial   recorte + creme + sombra + dobra   hero, destaque, card, tudo
  B — original    a foto como veio                   card e busca
  C — poluída     a foto como veio                   só o catálogo, nunca grande

⚠️ A CLASSE NÃO É GOSTO, É MEDIDA. "Essa é bonita" não escala pra 300 e não
sobrevive a quem vier depois. As perguntas são: a moldura é lisa o bastante pra
eu ter certeza de onde o produto acaba? e o recorte sobreviveu?

O KIT COLGATE, E DUAS DIAGNOSES MINHAS QUE ESTAVAM ERRADAS
──────────────────────────────────────────────────────────
No kit Colgate sumiram peças do produto. **Pra quem vai comprar, kit de 5
mostrado com 3 é pior que foto feia** — vira anúncio de outra oferta. Foto ruim
decepciona; foto que mente sobre o conteúdo é outra categoria de problema. Só
que eu errei DUAS vezes a causa antes de achar:

  1º ⚠️ Culpei a regra de proximidade e criei um portão de saída que media
     "quanta área foi descartada". Medido, o veredito saiu ao CONTRÁRIO: o
     Colgate passou com 2,8% (a falha real), e reprovaram o relógio (11%, era a
     caixinha de marca) e o infográfico do iPad (26%, era o infográfico
     inteiro). 📌 Área descartada não distingue "joguei fora lixo" de "joguei
     fora produto" — pune justamente onde descartar é o objetivo.
  2º A causa verdadeira: **as peças perdidas são BRANCAS sobre fundo BRANCO.**
     Não foram descartadas por regra nenhuma — foram absorvidas pela máscara de
     fundo, porque encostam no branco e têm a mesma cor. Isso é limite
     ESTRUTURAL de preenchimento por cor, não limiar mal calibrado.

📌 E é aí que eu parei. Já estava na terceira métrica pra salvar a abordagem —
o mesmo erro da saga da rolagem: afinar o número de um critério que não devia
existir. Preenchimento por cor não consegue separar branco de branco, ponto. A
saída foi usar a ferramenta feita pro problema (u2net, via rembg), que entende
OBJETO e não cor, e no Colgate devolve todas as peças.

MAS A IA NÃO GANHA SEMPRE — E É POR ISSO QUE OS DOIS FICAM
──────────────────────────────────────────────────────────
No infográfico da capa de iPad o rembg se perdeu (não existe "um objeto
saliente" numa colagem) e o preenchimento por cor devolveu o tablet limpo. Por
isso o pipeline não escolhe uma técnica: ele decide ANTES se a foto é
recortável, e infográfico simplesmente não entra. O sinal que separa é contagem
de manchinhas do tamanho de letra: **69 no infográfico, 0 a 4 em todas as
outras** — dois grupos distantes, não um limiar na faca.

    python3 fotografia.py                 # trata a fila inteira (o que faltar)
    python3 fotografia.py --prova 12      # folha antes/depois, não escreve nada
    python3 fotografia.py --refazer       # ignora o que já foi tratado
"""
import argparse
import hashlib
import io
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    from scipy import ndimage
except ImportError as e:
    print(f"❌ falta dependência ({e}). Instale:  pip install pillow numpy scipy")
    raise SystemExit(2)

BASE = Path(__file__).resolve().parent
FILA = BASE / "shared" / "produtos_fila.json"
SAIDA = BASE / "shared" / "fotos"
MANIFESTO = BASE / "shared" / "fotos_manifesto.json"

# as cores da marca — as MESMAS de gerar_marca.py e do site
CREME = (242, 238, 230)
ROSA = (200, 56, 94)
SOMBRA = (120, 112, 98)

# ⚠️ Os tamanhos que o site pede. Um celular exibindo card de 170px não pode
# baixar 1200px — hospedar a imagem só compensa se ela chegar no tamanho certo.
LARGURAS = (320, 640, 960)
LADO = 1000                      # o quadrado onde o produto é montado
MARGEM = 0.10                    # respiro em volta, igual pra todos

# portão de ENTRADA: quão lisa a moldura precisa ser
UNIF_MIN = 0.86
FUNDO_MIN = 0.28
# colagem/infográfico: manchinhas do tamanho de letra na frente
TXT_MAX = 20                     # medido: 69 no infográfico, 0-4 no resto
# portão de SAÍDA: o recorte tem que sobrar produto, e só produto
AREA_MIN = 0.045                 # produto minúsculo = recorte que comeu tudo
AREA_MAX = 0.92                  # produto ocupando tudo = fundo não foi achado
LADO_MINIMO = 400                # foto menor que isso não vira hero


def _cor_de_moldura(a, m):
    borda = np.concatenate([a[:m].reshape(-1, 3), a[-m:].reshape(-1, 3),
                            a[:, :m].reshape(-1, 3), a[:, -m:].reshape(-1, 3)])
    cor = np.median(borda, axis=0)
    uniforme = float((np.abs(borda - cor).max(axis=1) < 18).mean())
    return cor, uniforme


def analisar(im):
    """(array, máscara de fundo, uniformidade da moldura, área do fundo).

    📌 O fundo é o que PARECE com a moldura E ESTÁ LIGADO a ela. Sem a segunda
    metade, um pote branco sobre fundo branco viraria um buraco: o branco de
    dentro do produto também "parece" com a moldura."""
    a = np.asarray(im.convert("RGB"), dtype=np.float32)
    h, w, _ = a.shape
    m = max(6, int(min(h, w) * 0.04))
    cor, uniforme = _cor_de_moldura(a, m)
    dist = np.abs(a - cor).max(axis=2)
    rot, _ = ndimage.label(dist < 26)
    cantos = {rot[0, 0], rot[0, -1], rot[-1, 0], rot[-1, -1]}
    cantos.discard(0)
    fundo = np.isin(rot, list(cantos)) if cantos else np.zeros(dist.shape, bool)
    return a, fundo, uniforme, float(fundo.mean())


def recortar(im):
    """(alfa, laudo) — o recorte e o que ele custou.

    O laudo é o que o portão de saída lê. Ele não decide nada aqui: quem mede
    não julga, senão a decisão vira invisível."""
    _, fundo, unif, area_fundo = analisar(im)
    h, w = fundo.shape
    frente = ~fundo
    obj, n = ndimage.label(frente)
    if not n:
        return None, {"erro": "sem frente"}
    tam = ndimage.sum(frente, obj, range(1, n + 1))
    maior_i = int(tam.argmax()) + 1
    principal = obj == maior_i

    alcance = max(3, int(min(h, w) * 0.035))
    perto = ndimage.binary_dilation(principal, np.ones((alcance, alcance)))
    manter = {maior_i}
    for i in range(1, n + 1):
        if i == maior_i or tam[i - 1] < tam[maior_i - 1] * .04:
            continue
        if (perto & (obj == i)).any():
            manter.add(i)

    guardado = np.isin(obj, list(manter))
    # ⚠️ O NÚMERO QUE PEGA O CASO COLGATE: área de frente que a regra de
    # proximidade descartou. Selo de promoção é 1-2%; peça de kit é bem mais.
    perda = float((frente & ~guardado).sum() / max(frente.sum(), 1))

    alfa = ndimage.binary_closing(guardado, np.ones((3, 3))).astype(np.float32)
    alfa = ndimage.gaussian_filter(alfa, .8)
    laudo = {
        "uniforme": round(unif, 3),
        "area_fundo": round(area_fundo, 3),
        "area_produto": round(float(guardado.mean()), 3),
        "perda": round(perda, 4),
        "pecas": len(manter),
        "descartadas": n - len(manter),
        "lado": min(w, h),
    }
    return Image.fromarray((alfa * 255).astype(np.uint8), "L"), laudo


_SESSAO = None


def _sessao_ia():
    """A sessão do u2net, carregada uma vez só (leva ~10s; o resto é 0,5-1,7s
    por foto na CPU). Devolve None se o rembg não estiver instalado — o
    pipeline continua com o preenchimento por cor, pior mas vivo."""
    global _SESSAO
    if _SESSAO is None:
        try:
            from rembg import new_session
            _SESSAO = new_session("u2net")
        except Exception as e:
            print(f"⚠️  rembg indisponível ({type(e).__name__}) — recorte por "
                  f"COR, que perde produto claro em fundo claro. "
                  f"Instale:  pip install rembg onnxruntime")
            _SESSAO = False
    return _SESSAO or None


def recortar_ia(im):
    """O alfa do u2net. 📌 Ele entende OBJETO, não cor — e é por isso que devolve
    o tubo branco do kit Colgate que o preenchimento por cor comia junto com o
    fundo branco."""
    s = _sessao_ia()
    if s is None:
        return None
    try:
        from rembg import remove
        return remove(im, session=s).getchannel("A")
    except Exception as e:
        print(f"⚠️  recorte por IA falhou ({type(e).__name__})")
        return None


def _manchinhas(im):
    """Quantos blobs do tamanho de letra a frente tem. Infográfico tem dezenas.

    ⚠️ ESTE É O PORTÃO QUE FALTAVA. Sem ele o infográfico entra no recorte
    porque a moldura DELE também é branca lisa — e aí o u2net, que procura um
    objeto saliente, não acha nenhum e devolve pedaço de texto desbotado."""
    _, fundo, _, _ = analisar(im)
    h, w = fundo.shape
    area = h * w
    obj, n = ndimage.label(~fundo)
    if not n:
        return 0
    tam = ndimage.sum(~fundo, obj, range(1, n + 1))
    return int(((tam > area * .0002) & (tam < area * .005)).sum())


def classificar(im):
    """('A'|'B'|'C', motivo, alfa ou None). Só o A é tratado."""
    w, h = im.size
    if min(w, h) < LADO_MINIMO:
        return "C", f"pequena demais ({w}x{h})", None

    _, _, unif, area_fundo = analisar(im)
    if unif < UNIF_MIN or area_fundo < FUNDO_MIN:
        # ⚠️ B aqui não é "feia" — é "sem moldura lisa". Sem ela eu não tenho
        # como conferir o recorte, então não toco na foto.
        return "B", f"foto de cena (moldura {unif:.2f})", None

    txt = _manchinhas(im)
    if txt > TXT_MAX:
        return "C", f"colagem ou infográfico ({txt} manchas de texto)", None

    alfa = recortar_ia(im)
    tecnica = "u2net"
    if alfa is None:
        alfa, laudo = recortar(im)
        tecnica = "cor"
        if alfa is None:
            return "B", laudo.get("erro", "recorte falhou"), None

    # ── o PORTÃO DE SAÍDA ────────────────────────────────────────────────
    # ⚠️ Ele NÃO mede área descartada. Medi, e o veredito saía ao contrário:
    # reprovava justamente os recortes que jogaram fora selo e infográfico. O
    # que dá pra afirmar sem ambiguidade é se sobrou ALGUMA COISA de tamanho
    # plausível — recorte que comeu tudo, ou que não achou fundo nenhum.
    cob = float((np.asarray(alfa) > 128).mean())
    if not (AREA_MIN <= cob <= AREA_MAX):
        return "B", f"recorte suspeito ({cob*100:.0f}% da imagem)", None
    return "A", f"recorte limpo por {tecnica} ({cob*100:.0f}%)", alfa


def compor(im, alfa, lado=LADO):
    """O produto no chão da marca, com a sombra sempre igual."""
    cx = np.asarray(alfa) > 40
    ys, xs = np.where(cx)
    if not len(ys):
        return None
    caixa = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    corte, mask = im.crop(caixa), alfa.crop(caixa)
    alvo = int(lado * (1 - MARGEM * 2))
    e = min(alvo / corte.width, alvo / corte.height)
    novo = (max(1, int(corte.width * e)), max(1, int(corte.height * e)))
    corte = corte.resize(novo, Image.LANCZOS)
    mask = mask.resize(novo, Image.LANCZOS)

    fundo = Image.new("RGB", (lado, lado), CREME)
    px, py = (lado - novo[0]) // 2, (lado - novo[1]) // 2
    # ⚠️ A SOMBRA É O QUE FAZ RECORTE PARECER FOTOGRAFADO. Sem ela o produto
    # parece adesivo colado. Uma só, sempre na mesma direção e difusão — é a
    # REPETIÇÃO que lê como estúdio, não a sombra em si.
    s = Image.new("L", (lado, lado), 0)
    s.paste(mask, (px + int(lado * .012), py + int(lado * .020)))
    s = s.filter(ImageFilter.GaussianBlur(lado * .022))
    fundo = Image.composite(Image.new("RGB", (lado, lado), SOMBRA), fundo,
                            s.point(lambda v: int(v * .42)))
    fundo.paste(corte, (px, py), mask)
    return fundo


def assinar(im, frac=.115):
    """A dobra rosa no canto — a mesma do símbolo.

    📌 É o que faz 300 fotos de 300 vendedores lerem como um sistema. Uma marca
    d'água diz "isto é nosso"; uma dobra repetida diz "isto faz parte de algo",
    que é o que a gente quer."""
    im = im.copy()
    L = im.size[0]
    d = int(L * frac)
    tri = Image.new("L", im.size, 0)
    ImageDraw.Draw(tri).polygon([(0, L - d), (d, L), (0, L)], fill=255)
    im.paste(Image.new("RGB", im.size, ROSA), (0, 0), tri)
    return im


def tratar(im):
    """(imagem tratada ou None, classe, motivo)."""
    classe, motivo, alfa = classificar(im)
    if classe != "A":
        return None, classe, motivo
    pronta = compor(im, alfa)
    if pronta is None:
        return None, "B", "composição vazia"
    return assinar(pronta), "A", motivo


# ── nota e escolha por papel ─────────────────────────────────────────────
# ⚠️ HOJE TODO PRODUTO TEM UMA FOTO SÓ: a API de afiliado da Shopee devolve
# `imageUrl` no singular. Mercado Livre, Amazon e SHEIN devolvem várias — e
# quando isso entrar, a diferença tem que ser de DADO, não de refatoração.
# 📌 Por isso a nota e a escolha por papel já existem e já funcionam com N=1.
# O que eu NÃO fiz foi o motor de curadoria completo: sem várias fotas ele não
# teria entrada nenhuma, e código sem entrada não se prova — só apodrece.
PAPEIS = {
    "hero": {"classes": "A", "lado_min": 700},   # a foto grande da abertura
    "card": {"classes": "AB", "lado_min": 320},
    "lista": {"classes": "ABC", "lado_min": 0},  # o catálogo aceita tudo
}


def nota(registro: dict) -> int:
    """0-100, só com o que foi MEDIDO. Nada de 'parece boa'.

    A classe manda (é ela que diz se a foto entra no chão da marca), a
    resolução entra como piso e o enquadramento desempata: produto ocupando
    entre 25% e 65% do quadro é o que respira bem numa grade."""
    base = {"A": 70, "B": 45, "C": 15}.get(registro.get("classe", "C"), 15)
    lado = int(registro.get("lado", 0) or 0)
    res = min(20, int(lado / 60))                     # 1200px = 20 pontos
    cob = float(registro.get("cobertura", 0) or 0)
    enq = 10 - min(10, int(abs(cob - .45) * 40)) if cob else 0
    return max(0, min(100, base + res + enq))


def escolher(registros: list, papel: str = "card"):
    """O melhor registro pra este papel, ou None se nenhum servir.

    Com uma foto por produto isto devolve ela ou nada — e é esse 'ou nada' que
    já vale hoje: é o que impede um infográfico de virar a foto grande."""
    regra = PAPEIS.get(papel, PAPEIS["card"])
    aptos = [r for r in registros
             if r.get("classe", "C") in regra["classes"]
             and int(r.get("lado", 0) or 0) >= regra["lado_min"]]
    return max(aptos, key=nota) if aptos else None


# ── entrada e saída ──────────────────────────────────────────────────────
def _id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:14]


def baixar(url, tempo=25):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=tempo) as r:
        return Image.open(io.BytesIO(r.read())).convert("RGB")


def gravar(im, ident, saida=SAIDA):
    """Um webp por largura. 📌 Hospedar só compensa servindo o tamanho certo:
    card de 170px baixando 1200px é pior que hotlink."""
    saida.mkdir(parents=True, exist_ok=True)
    feitos = []
    for L in LARGURAS:
        p = saida / f"{ident}_{L}.webp"
        im.resize((L, L), Image.LANCZOS).save(p, "WEBP", quality=82, method=5)
        feitos.append(L)
    return feitos


def carregar_manifesto():
    if MANIFESTO.exists():
        try:
            return json.loads(MANIFESTO.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def main():
    ap = argparse.ArgumentParser(description="Pipeline de fotografia da TopShop")
    ap.add_argument("--prova", type=int, metavar="N",
                    help="folha antes/depois das N primeiras, sem escrever nada")
    ap.add_argument("--refazer", action="store_true",
                    help="reprocessa mesmo o que já está no manifesto")
    ap.add_argument("--sortear", action="store_true",
                    help="amostra espalhada pela fila, em vez das primeiras")
    ap.add_argument("--limite", type=int, default=0)
    args = ap.parse_args()

    if not FILA.exists():
        print(f"❌ {FILA} não existe")
        return 2
    fila = json.loads(FILA.read_text(encoding="utf-8"))
    urls, vistos = [], set()
    for it in fila:
        u = (it or {}).get("imagem", "") if isinstance(it, dict) else ""
        if u.startswith("http") and u not in vistos:
            vistos.add(u)
            urls.append(u)
    print(f"📷 {len(urls)} foto(s) distinta(s) na fila")

    manifesto = {} if args.refazer else carregar_manifesto()
    if args.prova:
        # ⚠️ AS PRIMEIRAS DA FILA NÃO SÃO UMA AMOSTRA. A fila entra em ordem de
        # mineração: as do topo vieram todas da mesma leva, do mesmo grupo,
        # muitas vezes do mesmo vendedor. Provar nelas é provar num nicho e
        # concluir sobre 297. 📌 Semente fixa: a amostra é espalhada MAS
        # repetível, senão duas rodadas não são comparáveis.
        if args.sortear:
            import random
            random.Random(7).shuffle(urls)
        urls = urls[:args.prova]
    elif args.limite:
        urls = urls[:args.limite]

    conta = {"A": 0, "B": 0, "C": 0, "falha": 0, "pulado": 0}
    pares = []
    t0 = time.time()
    for i, url in enumerate(urls, 1):
        ident = _id(url)
        if not args.prova and url in manifesto:
            conta["pulado"] += 1
            continue
        try:
            im = baixar(url)
        except Exception as e:
            conta["falha"] += 1
            print(f"  ⚠️  {i}/{len(urls)} não baixou: {type(e).__name__}")
            continue
        pronta, classe, motivo = tratar(im)
        conta[classe] += 1
        if args.prova:
            pares.append((im, pronta, classe, motivo))
            print(f"  {i:>3} {classe}  {motivo}")
            continue
        registro = {"classe": classe, "motivo": motivo, "id": ident,
                    "lado": min(im.size), "quando": int(time.time())}
        registro["nota"] = nota(registro)
        if pronta is not None:
            registro["larguras"] = gravar(pronta, ident)
        manifesto[url] = registro
        if i % 25 == 0:
            print(f"  … {i}/{len(urls)}  A={conta['A']} B={conta['B']} C={conta['C']}")

    if args.prova:
        _folha(pares, BASE / "prova_fotografia.png")
        print(f"\n📄 prova em {BASE/'prova_fotografia.png'}")
    else:
        MANIFESTO.write_text(json.dumps(manifesto, ensure_ascii=False, indent=1),
                             encoding="utf-8")
        print(f"\n📒 manifesto: {MANIFESTO} ({len(manifesto)} fotos)")
        peso = sum(p.stat().st_size for p in SAIDA.glob("*.webp")) if SAIDA.exists() else 0
        print(f"💾 {SAIDA}: {peso/1e6:.1f} MB")
    print(f"✅ A={conta['A']}  B={conta['B']}  C={conta['C']}  "
          f"falha={conta['falha']}  já feito={conta['pulado']}  "
          f"({time.time()-t0:.0f}s)")
    return 0


def _folha(pares, destino, cel=300):
    if not pares:
        return
    linhas = len(pares)
    folha = Image.new("RGB", (cel * 2 + 20, cel * linhas + 20), (255, 255, 255))
    d = ImageDraw.Draw(folha)
    for k, (antes, depois, classe, motivo) in enumerate(pares):
        y = 10 + k * cel
        a = antes.copy()
        a.thumbnail((cel - 18, cel - 18))
        folha.paste(a, (10 + (cel - a.size[0]) // 2, y + (cel - a.size[1]) // 2))
        if depois is not None:
            b = depois.copy()
            b.thumbnail((cel - 18, cel - 18))
            folha.paste(b, (10 + cel + (cel - b.size[0]) // 2, y + (cel - b.size[1]) // 2))
        else:
            d.rectangle([cel + 18, y + 10, cel * 2 + 2, y + cel - 10],
                        outline=(228, 223, 213))
            d.text((cel + 30, y + cel // 2 - 10), f"classe {classe}", fill=(140, 135, 125))
            d.text((cel + 30, y + cel // 2 + 4), motivo[:44], fill=(175, 170, 160))
        d.text((14, y + 4), classe, fill=(120, 115, 105))
    folha.save(destino)


if __name__ == "__main__":
    sys.exit(main())
