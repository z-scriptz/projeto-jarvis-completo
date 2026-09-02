#!/usr/bin/env python3
"""Criativos de anúncio a partir do que a máquina já sabe.

⚠️ POR QUE ISTO EXISTE. Os dois anúncios que funcionaram foram feitos à mão:
"produto" (233 cliques a R$0,11) e "curadoria" (R$0,08, o mais barato de
todos). Criativo feito à mão não escala e não se repete — e o que decide o
custo por clique é justamente PODER TROCAR a arte toda semana antes que o
público canse.

📌 A matéria-prima já está toda pronta: 128 fotos tratadas no chão da marca
(fotografia.py), 1.500 leituras de preço (historico_precos) e a identidade em
curva (gerar_marca.py). Isto aqui só monta.

OS DOIS FORMATOS, E POR QUE SÃO DOIS
────────────────────────────────────
  produto    um item grande, preço e a queda      → o que já vendeu
  curadoria  quatro itens, "o que baixou"         → o CPR mais barato

⚠️ NÃO INVENTAR TERCEIRO FORMATO. Os dois saíram de medição real; um terceiro
sairia de gosto meu e ia disputar orçamento com quem já provou. Formato novo
entra quando um dos dois morrer.

O QUE O CRIATIVO PODE DIZER
───────────────────────────
⚠️ Só o que o dado sustenta. "Caiu 27%" só aparece quando `caiu` existe;
"média de N dias" só quando há leitura suficiente. 📌 O anúncio é a primeira
coisa que a pessoa vê da TopShop — se ele exagerar, a página de termos que
promete o contrário vira papel.

    python3 criativos.py                  # 20 criativos em criativos/
    python3 criativos.py --quantos 30
    python3 criativos.py --so produto
"""
import argparse
import json
import os
import random
import sys
import textwrap
import urllib.request
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    print("❌ falta o pillow:  pip install pillow")
    raise SystemExit(2)

BASE = Path(__file__).resolve().parent
FILA = BASE / "shared" / "produtos_fila.json"
MANIFESTO = BASE / "shared" / "fotos_manifesto.json"
DIR_FOTOS = BASE / "shared" / "fotos"
SAIDA = BASE / "criativos"
FONTE_TTF = BASE / "assets" / "InstrumentSerif.ttf"
FONTE_URL = ("https://fonts.gstatic.com/s/instrumentserif/v5/"
             "jizBRFtNs2ka5fXjeivQ4LroWlx-2zI.ttf")

# as MESMAS cores da marca (gerar_marca.py, fotografia.py, o site)
CREME = (242, 238, 230)
NAVY = (26, 35, 56)
ROSA = (200, 56, 94)
MUTED = (128, 121, 108)

# 4:5 — o formato que ocupa mais tela no feed do Instagram sem ser cortado
LARG, ALT = 1080, 1350


def _fonte(tam: int, serif=True):
    """A serif da marca quando existe; a do sistema quando não.

    ⚠️ E ELA AVISA quando cai na reserva. Criativo com a tipografia errada não
    quebra nada — só deixa de ser nosso, e isso é pior de descobrir depois de
    já estar rodando como anúncio."""
    if serif and FONTE_TTF.exists():
        return ImageFont.truetype(str(FONTE_TTF), tam)
    for p in ("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"
              if serif else
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, tam)
    return ImageFont.load_default()


def baixar_fonte() -> bool:
    if FONTE_TTF.exists():
        return True
    try:
        FONTE_TTF.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(FONTE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            FONTE_TTF.write_bytes(r.read())
        print(f"   ⬇️  fonte da marca baixada: {FONTE_TTF}")
        return True
    except Exception as e:
        print(f"   ⚠️  sem a Instrument Serif ({type(e).__name__}) — os criativos "
              f"vão sair com a serif do sistema, e NÃO vão parecer a TopShop")
        return False


# ── os dados ─────────────────────────────────────────────────────────────
def _historico():
    try:
        import historico_precos as H
        return H
    except Exception:
        try:
            from creative_engine import historico_precos as H
            return H
        except Exception:
            return None


def produtos_com_arte() -> list:
    """Só o que tem foto EDITORIAL e preço. O resto não vira anúncio.

    📌 Classe A não é capricho aqui: o criativo é a primeira impressão da
    marca, e foto crua de marketplace com selo de promoção do vendedor é
    exatamente o que a gente passou o dia inteiro tirando do caminho."""
    fila = json.loads(FILA.read_text(encoding="utf-8"))
    try:
        man = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    except Exception:
        man = {}
    H = _historico()
    fora = []
    for it in fila:
        if not isinstance(it, dict):
            continue
        url = (it.get("imagem") or "").strip()
        reg = man.get(url) or {}
        if reg.get("classe") != "A" or not reg.get("larguras"):
            continue
        arq = DIR_FOTOS / f"{reg['id']}_960.webp"
        if not arq.exists():
            continue
        r = {}
        if H is not None:
            try:
                r = H.resumo(it.get("link", "")) or {}
            except Exception:
                r = {}
        preco = float(r.get("preco") or it.get("preco") or 0)
        if preco <= 0:
            continue
        fora.append({
            "nome": (it.get("campeao") or it.get("produto") or "").strip(),
            "link": it.get("link", ""),
            "arte": arq,
            "preco": preco,
            "caiu": int(r.get("caiu") or 0),
            "off": int(r.get("off") or 0),
            "obs": int(r.get("obs") or 0),
            "de": float(r.get("de") or 0),
        })
    # o que caiu de preço primeiro: é o que o anúncio tem de mais forte pra dizer
    fora.sort(key=lambda p: (-p["caiu"], -p["off"]))
    return fora


def _reais(v: float) -> str:
    return ("R$ %.2f" % v).replace(".", ",")


def _cortar(nome: str, larg: int) -> str:
    """Nome legível pro anúncio. Título de marketplace tem 120 caracteres."""
    try:
        from shared.termos import nome_para_cliente
        nome = nome_para_cliente(nome, 60)
    except Exception:
        nome = nome[:60]
    return nome.strip(" -–—|")


# ── os desenhos ──────────────────────────────────────────────────────────
def _fundo() -> Image.Image:
    return Image.new("RGB", (LARG, ALT), CREME)


def _sem_dobra(foto: Image.Image) -> Image.Image:
    """A foto tratada JÁ TRAZ a dobra — e no criativo ela cai no meio da peça.

    ⚠️ Vi na primeira folha: duas dobras rosas, uma no canto do anúncio (certa)
    e outra flutuando no meio do produto (lixo visual). 📌 A assinatura marca a
    PEÇA, não cada elemento dentro dela — repetida, ela deixa de assinar e vira
    textura. Como o chão da foto é o mesmo creme do anúncio, pintar por cima é
    exato: não é remendo, é o mesmo pixel."""
    foto = foto.copy()
    L = foto.size[0]
    d = int(L * .125)                      # a dobra é .115; sobra de folga
    ImageDraw.Draw(foto).polygon(
        [(0, L - d), (d, L), (0, L)], fill=CREME)
    return foto


def _colar(base, foto, xy):
    """Cola a foto com a emenda suavizada.

    ⚠️ O CREME DOS DOIS É O MESMO VALOR E MESMO ASSIM APARECE UMA MOLDURA. A
    foto tratada é webp com perda: 242,238,230 vira 241,238,231 em alguns
    pixels, e o olho enxerga o retângulo. 📌 Não adianta acertar a cor — o
    conserto é não ter borda: máscara com 10px de desfoque e a emenda some,
    qualquer que seja o deslocamento do compressor."""
    m = Image.new("L", foto.size, 0)
    b = 14
    ImageDraw.Draw(m).rectangle([b, b, foto.size[0] - b, foto.size[1] - b], fill=255)
    base.paste(foto, xy, m.filter(ImageFilter.GaussianBlur(10)))


def _dobra(im, frac=.085):
    """A assinatura, no mesmo canto de sempre."""
    d = int(LARG * frac)
    tri = Image.new("L", im.size, 0)
    ImageDraw.Draw(tri).polygon([(0, ALT - d), (d, ALT), (0, ALT)], fill=255)
    im.paste(Image.new("RGB", im.size, ROSA), (0, 0), tri)


def _marca(dr, y=None):
    f = _fonte(38)
    txt = "topshop"
    dr.text((64, y if y is not None else ALT - 92), txt, font=f, fill=NAVY)
    larg = dr.textlength(txt, font=f)
    dr.text((64 + larg + 14, (y if y is not None else ALT - 92) + 8),
            "curadoria diária", font=_fonte(22, serif=False), fill=MUTED)


def _selo_queda(im, dr, pc: int):
    """A tarja da queda. Só existe quando o número existe."""
    if pc <= 0:
        return
    f = _fonte(52)
    txt = f"−{pc}%"
    w = dr.textlength(txt, font=f)
    x0, y0 = LARG - 90 - w, 74
    dr.rounded_rectangle([x0 - 26, y0 - 14, x0 + w + 26, y0 + 74],
                         radius=18, fill=ROSA)
    dr.text((x0, y0), txt, font=f, fill=(255, 255, 255))


def criativo_produto(p: dict) -> Image.Image:
    im = _fundo()
    dr = ImageDraw.Draw(im)

    foto = _sem_dobra(Image.open(p["arte"]).convert("RGB"))
    lado = 760
    foto = foto.resize((lado, lado), Image.LANCZOS)
    _colar(im, foto, ((LARG - lado) // 2, 150))

    _selo_queda(im, dr, p["caiu"] or p["off"])

    y = 980
    nome = _cortar(p["nome"], LARG - 128)
    for linha in textwrap.wrap(nome, width=26)[:2]:
        dr.text((64, y), linha, font=_fonte(56), fill=NAVY)
        y += 66

    y += 18
    dr.text((64, y), _reais(p["preco"]), font=_fonte(86), fill=NAVY)
    if p["de"] and p["de"] > p["preco"]:
        w = dr.textlength(_reais(p["preco"]), font=_fonte(86))
        fv = _fonte(38, serif=False)
        dr.text((64 + w + 22, y + 44), _reais(p["de"]), font=fv, fill=MUTED)
        wv = dr.textlength(_reais(p["de"]), font=fv)
        dr.line([64 + w + 22, y + 62, 64 + w + 22 + wv, y + 62], fill=MUTED, width=3)

    # ⚠️ a linha da prova só aparece quando há leitura pra sustentar
    if p["obs"] >= 3:
        dr.text((64, y + 116), f"preço acompanhado há {p['obs']} dias",
                font=_fonte(28, serif=False), fill=MUTED)

    _marca(dr)
    _dobra(im)
    return im


def criativo_curadoria(itens: list) -> Image.Image:
    im = _fundo()
    dr = ImageDraw.Draw(im)

    dr.text((64, 96), "O que baixou", font=_fonte(78), fill=NAVY)
    dr.text((64, 176), "de preço", font=_fonte(78), fill=ROSA)

    # ⚠️ A CONTA TEM QUE FECHAR NA ALTURA. A primeira versão usava célula de
    # 420 e a segunda fileira de preços caía EM CIMA da assinatura — grid que
    # transborda não é detalhe de acabamento, é o anúncio saindo torto.
    #   y0 + 2*(cel + rodapé) tem que caber antes da marca, em ALT-92.
    cel, gap, rodape = 372, 28, 92
    x0 = (LARG - (cel * 2 + gap)) // 2
    y0 = 300
    assert y0 + 2 * (cel + rodape) < ALT - 110, "o grid não cabe"
    for i, p in enumerate(itens[:4]):
        cx = x0 + (i % 2) * (cel + gap)
        cy = y0 + (i // 2) * (cel + rodape)
        foto = _sem_dobra(Image.open(p["arte"]).convert("RGB")).resize(
            (cel, cel), Image.LANCZOS)
        _colar(im, foto, (cx, cy))
        dr.text((cx + 4, cy + cel + 8), _reais(p["preco"]),
                font=_fonte(40), fill=NAVY)
        if p["caiu"]:
            dr.text((cx + 4, cy + cel + 52), f"caiu {p['caiu']}%",
                    font=_fonte(24, serif=False), fill=ROSA)

    _marca(dr)
    _dobra(im)
    return im


def main():
    ap = argparse.ArgumentParser(description="Criativos de anúncio da TopShop")
    ap.add_argument("--quantos", type=int, default=20)
    ap.add_argument("--so", choices=("produto", "curadoria"))
    ap.add_argument("--saida", default=str(SAIDA))
    args = ap.parse_args()

    baixar_fonte()
    if not FILA.exists():
        print(f"❌ {FILA} não existe")
        return 2
    prods = produtos_com_arte()
    print(f"🎨 {len(prods)} produto(s) com foto editorial e preço")
    if not prods:
        print("   rode fotografia.py antes — sem classe A não há criativo")
        return 1

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    n_cur = 0 if args.so == "produto" else max(1, args.quantos // 4)
    n_prod = 0 if args.so == "curadoria" else args.quantos - n_cur
    feitos = []

    for i, p in enumerate(prods[:n_prod], 1):
        cam = saida / f"produto_{i:02d}.jpg"
        criativo_produto(p).save(cam, "JPEG", quality=92)
        feitos.append(cam)

    baralho = list(prods)
    random.Random(7).shuffle(baralho)
    for i in range(n_cur):
        grupo = baralho[i * 4:(i + 1) * 4]
        if len(grupo) < 4:
            break
        cam = saida / f"curadoria_{i+1:02d}.jpg"
        criativo_curadoria(grupo).save(cam, "JPEG", quality=92)
        feitos.append(cam)

    peso = sum(c.stat().st_size for c in feitos) / 1e6
    print(f"✅ {len(feitos)} criativo(s) em {saida}  ({peso:.1f} MB)")
    print("   suba no Gerenciador como anúncios novos do conjunto que já roda —")
    print("   trocar a ARTE mantendo público e orçamento é o teste limpo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
