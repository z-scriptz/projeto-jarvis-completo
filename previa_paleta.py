#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# previa_paleta.py -- desenha o layout NOVO nas 6 contas, lado a lado, em PNG.
#
# ⚠️ O QUE ESTA PRÉVIA É E O QUE ELA NÃO É
# ────────────────────────────────────────
# É uma prévia de LAYOUT: posição, tamanho, cor e quebra de linha. Lê os MESMOS
# nomes de variável de ambiente da produção e a MESMA shared/paleta.py, então
# mexer no .env muda esta imagem igual muda o vídeo.
#
# NÃO é prova de pixel. O vídeo desenha o texto pelo TextClip do MoviePy; aqui é
# Pillow direto. Fontes iguais, motores diferentes — a largura de uma linha pode
# variar uns poucos pixels. Pra prova de pixel existe o preview_layout.py, que
# chama o código REAL do render (e por isso precisa do MoviePy e da VPS).
#
# Essa distinção não é frescura: o preview_layout.py tem um parágrafo inteiro no
# cabeçalho sobre a vez em que uma prévia infiel quase me fez "confirmar" um
# conserto olhando o quadro errado.
#
# USO:
#   python3 previa_paleta.py                    # as 6 contas numa folha só
#   python3 previa_paleta.py --nicho tech       # uma só, em tamanho cheio
#   python3 previa_paleta.py --gancho 'linha 1\nlinha 2'
#   python3 previa_paleta.py --saida /tmp/x.png

import argparse
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from PIL import Image, ImageDraw, ImageFont          # noqa: E402
from shared.paleta import do_nicho, _FUNDOS          # noqa: E402

LARG, ALT = 1080, 1920
BRAND = BASE / "assets" / "brand"

# ganchos de exemplo, no molde que o Dre pediu: duas linhas, situação
# reconhecível, sem citar produto e sem mandar fazer nada.
GANCHOS = {
    "geral":  "Tem coisa que a gente só\ndescobre que precisava depois",
    "moda":   "Descobri tarde por que\nalgumas roupas caem melhor",
    "beleza": "Ninguém me contou isso\nsobre pele oleosa",
    "casa":   "A bagunça nunca foi preguiça,\nera falta de lugar",
    "tech":   "O celular fica lento por\nmotivo que não é o celular",
    "pet":    "Meu cachorro parou de fazer\nisso e eu nem percebi quando",
}
HANDLES = {
    "geral": "@topshop.__", "moda": "@topshopmoda_", "beleza": "@topshopbeauty._",
    "casa": "@topshopcasa_", "tech": "@topshoptech_", "pet": "@topshoppet_",
}


def _fonte(familia: str, peso: str, tam: int):
    """A fonte de verdade, ou None. Nunca inventa substituta em silêncio."""
    for pasta in (BRAND, Path("/tmp/jarvis-fontes")):
        alvo = pasta / f"{familia}-{peso}.ttf"
        if alvo.exists():
            try:
                return ImageFont.truetype(str(alvo), tam)
            except Exception:
                pass
    return None


def _quebrar(d, txt, fonte, larg_max):
    """Quebra gulosa por largura — o mesmo critério do narrated_video_agent."""
    fora = []
    for par in [l for l in txt.split("\n") if l.strip()]:
        cur = []
        for w in par.split():
            if cur and d.textlength(" ".join(cur + [w]), font=fonte) > larg_max:
                fora.append(" ".join(cur))
                cur = [w]
            else:
                cur.append(w)
        if cur:
            fora.append(" ".join(cur))
    return fora or [txt]


def quadro(nicho: str, gancho: str = None) -> Image.Image:
    p = do_nicho(nicho)
    im = Image.new("RGB", (LARG, ALT), p["fundo_rgb"])
    d = ImageDraw.Draw(im)

    # ── a mesma geometria, lida das mesmas envs ──────────────────────────────
    w_frac = float(os.environ.get("VIDEO_W_FRAC", 0.90))
    larg_v = int(LARG * w_frac)
    alt_v = int(larg_v * 4 / 3)
    borda = (LARG - larg_v) // 2
    video_y = int(os.environ.get("VIDEO_Y", 500))
    raio = int(os.environ.get("VIDEO_RAIO", 28))

    logo_x = int(os.environ.get("LOGO_X", borda))
    logo_y = int(os.environ.get("LOGO_Y", 168))
    logo_tam = int(os.environ.get("LOGO_TAM", 140))
    k = logo_tam / 120.0
    texto_x = logo_x + logo_tam + int(os.environ.get("TEXTO_DX", 16))
    nome_font = int(os.environ.get("NOME_FONT", 52))   # o valor real da VPS
    handle_font = int(os.environ.get("HANDLE_FONT", 42))
    nome_dy = int(os.environ.get("NOME_DY", round(-12 * k)))
    # o @ e o selo penduram no NOME, não no logo — ver o comentário longo em
    # narrated_video_agent._criar_camadas_topo. Na 1ª prévia o selo caiu em
    # cima do "@topshopmoda_" justamente por estarem presos ao logo.
    handle_dy = int(os.environ.get("HANDLE_DY", nome_dy + round(nome_font * 1.038)))
    selo_dy = int(os.environ.get("SELO_DY", nome_dy + round(nome_font * 0.50)))
    selo_tam = int(os.environ.get("SELO_TAM", round(nome_font * 0.885)))
    hk_font = int(os.environ.get("HK_FONT", 60))
    hk_min = int(os.environ.get("HK_FONT_MIN", 34))
    hk_lin = int(os.environ.get("HK_ALT_LINHA", 76))
    hk_marg = int(os.environ.get("HK_MARGEM", borda))
    hk_marg_d = int(os.environ.get("HK_MARGEM_DIR", borda))
    hk_gap = int(os.environ.get("HK_GAP_VIDEO", 16))
    hk_max = LARG - hk_marg - hk_marg_d

    # ── a faixa do vídeo, com o canto arredondado ────────────────────────────
    # cinza neutro dos dois lados da luminância, pra não parecer parte da paleta
    cinza = (176, 176, 176) if p["claro"] else (72, 72, 76)
    d.rounded_rectangle((borda, video_y, borda + larg_v, video_y + alt_v),
                        radius=raio, fill=cinza)
    f_lbl = _fonte("Poppins", "Regular", 34) or ImageFont.load_default()
    rot = f"vídeo 3:4 · {larg_v}×{alt_v} · y {video_y}→{video_y + alt_v}"
    d.text((borda + larg_v // 2, video_y + alt_v // 2), rot, font=f_lbl,
           fill=(255, 255, 255) if not p["claro"] else (110, 110, 110), anchor="mm")

    # ── o cabeçalho ──────────────────────────────────────────────────────────
    d.ellipse((logo_x, logo_y, logo_x + logo_tam, logo_y + logo_tam),
              fill=p["tinta_rgb"])
    f_ts = _fonte("Montserrat", "Bold", int(logo_tam * 0.42)) or ImageFont.load_default()
    d.text((logo_x + logo_tam / 2, logo_y + logo_tam / 2), "TS", font=f_ts,
           fill=p["fundo_rgb"], anchor="mm")

    f_nome = _fonte("Montserrat", "Bold", nome_font) or ImageFont.load_default()
    f_hand = _fonte("Montserrat", "Bold", handle_font) or ImageFont.load_default()
    d.text((texto_x, logo_y + nome_dy), "TopShop", font=f_nome, fill=p["tinta_rgb"])
    larg_nome = d.textlength("TopShop", font=f_nome)
    selo_x = texto_x + larg_nome + int(os.environ.get("SELO_DX", 12))
    # o selo CENTRA NA TINTA DO NOME, medida — não num deslocamento cravado.
    # Era `logo_y + 14`, que não sabe onde a tinta começa nem quanto ela mede:
    # com handle curto a folga escondia; com "@topshopbeauty._" o selo encostava
    # no @. O renderizador de verdade faz a mesma conta pelo `.h` do clipe.
    if not os.environ.get("SELO_DY"):
        cx0, cy0, cx1, cy1 = f_nome.getbbox("TopShop")
        # sobe um tico: centro geométrico lê como baixo, porque o olho alinha
        # pela altura-x. Mesma constante do renderizador de verdade.
        subir = int(os.environ.get("SELO_SUBIR", round(nome_font * 0.08)))
        selo_dy = nome_dy + cy0 + (cy1 - cy0 - selo_tam) // 2 - subir
    d.ellipse((selo_x, logo_y + selo_dy, selo_x + selo_tam, logo_y + selo_dy + selo_tam),
              fill=(58, 141, 245))
    d.text((texto_x, logo_y + handle_dy), HANDLES.get(nicho, "@topshop.__"),
           font=f_hand, fill=p["secundaria_rgb"])

    # ── o gancho: encolhe até caber em 2 linhas, ancorado no topo do vídeo ────
    peso = os.environ.get("HOOK_PESO", "Light")
    txt = gancho or GANCHOS.get(nicho, GANCHOS["geral"])
    tam = hk_font
    f_hk = _fonte("Montserrat", peso, tam) or _fonte("Poppins", peso, tam)
    linhas = _quebrar(d, txt, f_hk or ImageFont.load_default(), hk_max)
    while tam > hk_min and len(linhas) > 2 and f_hk:
        tam -= 2
        f_hk = _fonte("Montserrat", peso, tam) or _fonte("Poppins", peso, tam)
        linhas = _quebrar(d, txt, f_hk, hk_max)
    f_hk = f_hk or ImageFont.load_default()
    hk_y = max(logo_y + logo_tam + 20, video_y - hk_gap - len(linhas) * hk_lin)
    for i, linha in enumerate(linhas):
        d.text((hk_marg, hk_y + i * hk_lin), linha, font=f_hk, fill=p["tinta_rgb"])

    return im


def folha(nichos, gancho=None, col=3) -> Image.Image:
    """Contact sheet: as contas lado a lado, que é como o Dre vai comparar."""
    esc = 0.28
    lw, lh = int(LARG * esc), int(ALT * esc)
    pad, rot_h = 26, 46
    lin = (len(nichos) + col - 1) // col
    folha = Image.new("RGB", (col * lw + (col + 1) * pad,
                              lin * (lh + rot_h) + (lin + 1) * pad), (28, 28, 30))
    d = ImageDraw.Draw(folha)
    f = _fonte("Poppins", "Medium", 22) or ImageFont.load_default()
    for i, n in enumerate(nichos):
        x = pad + (i % col) * (lw + pad)
        y = pad + (i // col) * (lh + rot_h + pad)
        folha.paste(quadro(n, gancho).resize((lw, lh), Image.LANCZOS), (x, y))
        p = do_nicho(n)
        d.text((x, y + lh + 12),
               f"{n}  ·  {p['fundo_hex']}",
               font=f, fill=(232, 232, 236))
    return folha


def main() -> int:
    ap = argparse.ArgumentParser(description="prévia do layout novo por nicho")
    ap.add_argument("--nicho", help="só este nicho, em 1080x1920")
    ap.add_argument("--gancho", help="texto do gancho (use \\n pra 2 linhas)")
    ap.add_argument("--saida", default="", help="caminho do PNG")
    ap.add_argument("--fundo", action="append", default=[], metavar="NICHO=#HEX",
                    help="testa outro tom sem editar código: --fundo moda=#DDD3C2")
    a = ap.parse_args()

    # trocar um tom é uma linha de comando, não um deploy: decidir cor é olhar,
    # e olhar precisa ser barato.
    for par in a.fundo:
        nicho, _, hexa = par.partition("=")
        nicho = nicho.strip().lower()
        if nicho not in _FUNDOS or not hexa.strip():
            print(f"⚠️  ignorei --fundo {par!r} (nicho desconhecido ou hex vazio)")
            continue
        _FUNDOS[nicho] = (hexa.strip(), "teste")

    gancho = a.gancho.replace("\\n", "\n") if a.gancho else None
    if a.nicho:
        im = quadro(a.nicho, gancho)
        saida = Path(a.saida or f"/tmp/previa_{a.nicho}.png")
    else:
        im = folha(list(_FUNDOS.keys()), gancho)
        saida = Path(a.saida or "/tmp/previa_paleta.png")
    saida.parent.mkdir(parents=True, exist_ok=True)
    im.save(saida)

    achou = _fonte("Montserrat", os.environ.get("HOOK_PESO", "Light"), 40)
    if not achou:
        print("⚠️  a Montserrat não está em assets/brand/ — a prévia caiu na "
              "fonte de reserva e NÃO mostra a tipografia nova.")
        print("   .venv/bin/python baixar_fontes.py")
    print(f"✅ {saida}  ({im.size[0]}x{im.size[1]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
