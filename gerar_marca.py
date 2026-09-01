#!/usr/bin/env python3
"""Desenha a identidade da TopShop em SVG, a partir das curvas REAIS da fonte.

⚠️ POR QUE ISTO É UM GERADOR E NÃO QUATRO ARQUIVOS DESENHADOS À MÃO
────────────────────────────────────────────────────────────────────
O conceito veio de uma imagem gerada por IA: monograma TS com uma dobra rosa no
canto. Imagem de IA tem curva torta, espessura irregular e espacejamento que
"parece" certo e não é — some tudo em 200px e aparece tudo em 2000px, num
letreiro ou numa gravação.

Vetorizar de verdade não é redesenhar no olho: é reconstruir com curvas de
verdade. Aqui as letras saem dos contornos da Instrument Serif — a MESMA fonte
das manchetes do site — extraídos com fontTools. São as Béziers que o
desenhista da fonte fez, com o espacejamento que ele definiu. O que é nosso é a
composição: o encaixe do S no T, a dobra, as proporções e as travas.

📌 CONSEQUÊNCIA PRÁTICA: a marca é reprodutível. Mudou a proporção? Muda o
número aqui e as quatro assinaturas saem juntas, coerentes. Ninguém vai
"consertar o SVG na mão" e deixar a versão principal diferente do favicon —
que é exatamente como uma identidade morre.

Licença: Instrument Serif é OFL (SIL Open Font License). Converter glifos em
contorno pra compor uma marca é uso permitido; o que a OFL restringe é
redistribuir a FONTE. Não distribuímos o .ttf — só as curvas resultantes.

AS QUATRO ASSINATURAS (e é só isso; não existe uma quinta)
──────────────────────────────────────────────────────────
  01 principal  símbolo + wordmark          uso padrão: site, e-mail, vídeo
  02 wordmark   só "topshop"                onde já existe o símbolo ao lado
  03 simbolo    só o TS com a dobra         avatar, selo, marca-d'água
  04 micro      TS redesenhado em geometria favicon, 16px, ícone de app

⚠️ A MICRO NÃO É A 03 REDUZIDA. Didone tem filete de 8 unidades de espessura:
em 16px isso é 0,13 do pixel e o antialiasing come. A micro é redesenhada em
geometria sólida — é o que toda marca séria faz, e é por isso que ela é uma
assinatura oficial e não um acidente.

    python3 gerar_marca.py [--fonte CAMINHO.ttf] [--saida assets/marca]
"""
import argparse
import sys
from pathlib import Path

try:
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont
except ImportError:
    print("❌ falta o fonttools:  pip install fonttools")
    raise SystemExit(2)


# ── as travas da marca (mexer AQUI, nunca no SVG) ────────────────────────────
NAVY = "#1A2338"        # a mesma --ink do site
ROSA = "#C8385E"        # a mesma --marca do site
CREME = "#F2EEE6"       # a mesma --bg

# encaixe do S no T, em unidades de em (1000 = corpo da fonte)
S_AVANCO = -0.055       # negativo = o S entra por baixo do braço do T
S_DESCE = 0.085         # o S rompe a linha de base: é o que faz "monograma"
DOBRA = 0.235           # cateto da dobra rosa
FOLGA = 0.070           # respiro em volta do desenho (margem óptica)

# a assinatura principal: distância entre símbolo e wordmark, em alturas de X
GAP_LOCKUP = 0.42


def _percurso(gs, nome, dx=0.0, dy=0.0, escala=1.0):
    """O contorno do glifo, em coordenadas de SVG (y pra baixo)."""
    pen = SVGPathPen(gs)
    # (a, b, c, d, e, f): espelha o y e aplica deslocamento
    tp = TransformPen(pen, (escala, 0, 0, -escala, dx, dy))
    gs[nome].draw(tp)
    return pen.getCommands()


def _limites(gs, nome):
    bp = BoundsPen(gs)
    gs[nome].draw(bp)
    return bp.bounds  # (xMin, yMin, xMax, yMax) no espaço da fonte


class Marca:
    def __init__(self, caminho_fonte: Path):
        self.fonte = TTFont(str(caminho_fonte))
        self.gs = self.fonte.getGlyphSet()
        self.em = self.fonte["head"].unitsPerEm
        self.avanco = {g: self.fonte["hmtx"][g][0] for g in "TStopsh"}

    @staticmethod
    def _tinta(mono, escuro):
        """(cor da letra, cor da dobra, atributo extra da dobra).

        ⚠️ NAVY SOBRE PRETO NÃO É "VERSÃO ESCURA", É UMA MARCA QUE SUMIU. A
        primeira folha de contato saiu com a principal em #1A2338 sobre #14120F
        e só dava pra ler o rosa. Fundo escuro inverte a TINTA, não o fundo."""
        if mono:
            return "currentColor", "currentColor", ' opacity=".55"'
        if escuro == "css":
            # ⚠️ NO SITE A MARCA NÃO PODE TER COR FIXA. Tem tema claro e escuro,
            # e logo chumbada em #1A2338 vira mancha preta no escuro — que é o
            # defeito que a folha de contato mostrou. Com as variáveis do site,
            # a marca simplesmente segue o tema, sem segunda cópia pra manter.
            return "var(--ink)", "var(--marca)", ""
        return (CREME if escuro else NAVY), ROSA, ""

    # ── 03 SÍMBOLO ───────────────────────────────────────────────────────
    def simbolo(self, mono=False, escuro=False) -> str:
        """T e S encaixados, mais a dobra.

        ⚠️ O ENCAIXE É O DESENHO. Dois glifos lado a lado são duas letras; o que
        vira monograma é o S entrar POR BAIXO do braço direito do T e romper a
        linha de base. Sem isso é "TS", com isso é uma marca."""
        em = self.em
        tx = _limites(self.gs, "T")
        sx = _limites(self.gs, "S")
        alt_t = tx[3]                      # altura de maiúscula
        # o S começa onde o braço do T termina, recuado pelo avanço negativo
        s_esq = tx[2] + S_AVANCO * em - sx[0]
        s_base = S_DESCE * em

        larg = (s_esq + sx[2]) - tx[0]
        dobra = DOBRA * em
        folga = FOLGA * em
        # a dobra nasce na base do T e desce junto com o S: os dois pés da marca
        base = max(alt_t, s_base + sx[3])
        alt = base + max(s_base - sx[1], dobra)

        vb_x = tx[0] - folga
        vb_y = -folga
        vb_w = larg + folga * 2
        vb_h = alt + folga * 2

        # y=0 do SVG na altura do topo das maiúsculas
        d_t = _percurso(self.gs, "T", dx=0, dy=alt_t)
        d_s = _percurso(self.gs, "S", dx=s_esq, dy=alt_t + s_base)

        cor_tinta, cor_dobra, op_dobra = self._tinta(mono, escuro)

        # ⚠️ A DOBRA É UM TRIÂNGULO RETO, não um triângulo "bonitinho". Ela tem
        # que ler como CANTO DE PÁGINA VIRANDO: cateto vertical colado na haste
        # do T, hipotenusa subindo pra direita. Isoceles, pra funcionar
        # espelhada nos cantos das imagens sem precisar de outro desenho.
        x0 = tx[0] + (tx[2] - tx[0]) * 0.30      # sob a haste do T
        y0 = alt_t
        dobra_d = (f"M{x0:.1f} {y0:.1f}"
                   f"L{x0 + dobra:.1f} {y0 + dobra:.1f}"
                   f"L{x0:.1f} {y0 + dobra:.1f}Z")

        return self._svg(
            f"{vb_x:.1f} {vb_y:.1f} {vb_w:.1f} {vb_h:.1f}",
            f'<path d="{dobra_d}" fill="{cor_dobra}"{op_dobra}/>'
            f'<path d="{d_t}" fill="{cor_tinta}"/>'
            f'<path d="{d_s}" fill="{cor_tinta}"/>',
            titulo="TopShop")

    # ── 02 WORDMARK ──────────────────────────────────────────────────────
    def wordmark(self, mono=False, escuro=False) -> str:
        """"topshop", com "shop" na cor da marca.

        📌 O corte é semântico, não decorativo: separa o que a gente É (top) do
        que a gente FAZ (shop). Um corte no meio de "tops|hop" seria só cor."""
        em = self.em
        caneta = 0.0
        navy, rosa = [], []
        for i, ch in enumerate("topshop"):
            d = _percurso(self.gs, ch, dx=caneta, dy=0)
            (navy if i < 3 else rosa).append(d)
            caneta += self.avanco[ch]

        alto = max(_limites(self.gs, c)[3] for c in "topsh")
        baixo = min(_limites(self.gs, c)[1] for c in "topsh")
        folga = FOLGA * em
        vb = (f"{-folga:.1f} {-alto - folga:.1f} "
              f"{caneta + folga * 2:.1f} {alto - baixo + folga * 2:.1f}")

        cor_a, cor_b, op_b = self._tinta(mono, escuro)
        corpo = ("".join(f'<path d="{d}" fill="{cor_a}"/>' for d in navy)
                 + "".join(f'<path d="{d}" fill="{cor_b}"{op_b}/>' for d in rosa))
        return self._svg(vb, corpo, titulo="topshop")

    # ── 01 PRINCIPAL ─────────────────────────────────────────────────────
    def principal(self, mono=False, escuro=False) -> str:
        """Símbolo + wordmark, alinhados pela linha de base.

        ⚠️ ALINHAR PELO CENTRO SERIA O ERRO ÓBVIO. O símbolo desce abaixo da
        base (o S rompe) e o wordmark tem a perna do 'p'. Centralizados, os dois
        parecem tortos. Alinhados pela LINHA DE BASE das maiúsculas, parecem
        assentados — que é o que o olho procura."""
        em = self.em
        tx = _limites(self.gs, "T")
        sx = _limites(self.gs, "S")
        alt_t = tx[3]
        s_esq = tx[2] + S_AVANCO * em - sx[0]
        s_base = S_DESCE * em
        larg_sim = (s_esq + sx[2]) - tx[0]
        dobra = DOBRA * em

        # o wordmark entra na altura de x, escalado pra caber na maiúscula
        alto_w = max(_limites(self.gs, c)[3] for c in "topsh")
        baixo_w = min(_limites(self.gs, c)[1] for c in "topsh")
        esc = (alt_t * 0.92) / alto_w
        gap = GAP_LOCKUP * alt_t
        wx = tx[0] + larg_sim + gap

        caneta = 0.0
        navy, rosa = [], []
        for i, ch in enumerate("topshop"):
            d = _percurso(self.gs, ch, dx=wx + caneta * esc, dy=alt_t, escala=esc)
            (navy if i < 3 else rosa).append(d)
            caneta += self.avanco[ch]
        larg_w = caneta * esc

        folga = FOLGA * em
        topo = -folga
        base = alt_t + max(s_base + sx[3] - alt_t, dobra, -baixo_w * esc) + folga
        vb = (f"{tx[0] - folga:.1f} {topo:.1f} "
              f"{larg_sim + gap + larg_w + folga * 2:.1f} {base - topo:.1f}")

        cor_a, cor_b, op_b = self._tinta(mono, escuro)
        x0 = tx[0] + (tx[2] - tx[0]) * 0.30
        dobra_d = (f"M{x0:.1f} {alt_t:.1f}L{x0 + dobra:.1f} {alt_t + dobra:.1f}"
                   f"L{x0:.1f} {alt_t + dobra:.1f}Z")
        corpo = (f'<path d="{dobra_d}" fill="{cor_b}"{op_b}/>'
                 f'<path d="{_percurso(self.gs, "T", dy=alt_t)}" fill="{cor_a}"/>'
                 f'<path d="{_percurso(self.gs, "S", dx=s_esq, dy=alt_t + s_base)}" '
                 f'fill="{cor_a}"/>'
                 + "".join(f'<path d="{d}" fill="{cor_a}"/>' for d in navy)
                 + "".join(f'<path d="{d}" fill="{cor_b}"{op_b}/>' for d in rosa))
        return self._svg(vb, corpo, titulo="TopShop")

    # ── 04 MICRO ─────────────────────────────────────────────────────────
    def micro(self) -> str:
        """Redesenhada em geometria sólida, pra 16px.

        ⚠️ NÃO É A 03 REDUZIDA, e a razão é medida: o filete fino da Instrument
        Serif tem ~8 unidades num corpo de 1000. Num favicon de 16px isso dá
        0,13 pixel — o antialiasing transforma em névoa cinza, e o "S" vira uma
        mancha. Em tamanho pequeno o desenho tem que ser feito de novo, com
        traço uniforme e o mínimo de detalhe que ainda diz TS.

        📌 O que sobrevive da marca grande: a dobra rosa no mesmo canto, a mesma
        proporção de haste, e o T por cima do S. É o suficiente pra pessoa
        reconhecer sem nunca ter comparado os dois lado a lado."""
        # grade de 32, traço de 3,2 — a haste do T e o filete do S iguais
        # ⚠️ A PRIMEIRA VERSÃO LIA "TE". Eu montei o S com três retângulos
        # empilhados e dois conectores, achando que "três barras + degraus =
        # S". Três barras horizontais paralelas são um E, e nenhum leitor vai
        # ler outra coisa. 📌 O que faz o S é a CURVA TROCANDO DE LADO — então
        # ele é traçado, não preenchido: duas meias-voltas em sentidos opostos,
        # espessura uniforme e ponta arredondada, que é o que sobrevive a 16px.
        t = 3.2
        return self._svg(
            "0 0 32 32",
            f'<rect width="32" height="32" rx="7.5" fill="{NAVY}"/>'
            f'<g stroke="{CREME}" stroke-width="{t}" fill="none" '
            f'stroke-linecap="round" stroke-linejoin="round">'
            # T: braço e haste
            f'<path d="M6.6 9.4H17.4"/><path d="M12 9.4V22.2"/>'
            # S: duas meias-voltas opostas, desenhado como um S de verdade
            f'<path d="M25.4 13.6a3.3 3.3 0 0 0-5.9 1.9'
            f'c0 3.2 5.9 2.4 5.9 5.6a3.3 3.3 0 0 1-5.9 1.9"/>'
            f'</g>'
            # a dobra, no mesmo canto da marca grande
            f'<path d="M6.6 20.4L11.6 25.4H6.6Z" fill="{ROSA}"/>',
            titulo="TopShop")

    @staticmethod
    def _svg(viewbox, corpo, titulo="TopShop"):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" '
                f'role="img" aria-label="{titulo}">'
                f"<title>{titulo}</title>{corpo}</svg>")


CONTATO = """<!doctype html><meta charset=utf-8>
<title>TopShop — assinaturas oficiais</title>
<style>
:root{{color-scheme:light dark}}
body{{margin:0;background:{creme};color:{navy};
  font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;padding:40px}}
h1{{font-size:15px;letter-spacing:.16em;text-transform:uppercase;
  font-weight:600;margin:0 0 34px;opacity:.55}}
.g{{display:grid;gap:26px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}}
.c{{background:#fff;border:1px solid rgba(26,35,56,.1);border-radius:14px;
  padding:26px;display:flex;flex-direction:column;gap:16px}}
.c.esc{{background:#14120F;border-color:rgba(242,238,230,.14);color:{creme}}}
.n{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;opacity:.5}}
.p{{display:flex;align-items:center;justify-content:center;min-height:110px}}
.p svg{{max-width:100%;max-height:96px}}
.fila{{display:flex;align-items:flex-end;gap:22px;flex-wrap:wrap}}
.fila span{{display:flex;flex-direction:column;align-items:center;gap:7px;
  font-size:10px;opacity:.5}}
</style>
<h1>TopShop · assinaturas oficiais</h1>
<div class=g>
  <div class=c><span class=n>01 — principal</span><div class=p>{principal}</div></div>
  <div class=c><span class=n>02 — wordmark</span><div class=p>{wordmark}</div></div>
  <div class=c><span class=n>03 — símbolo</span><div class=p>{simbolo}</div></div>
  <div class=c><span class=n>04 — micro (favicon)</span><div class=p>
    <div class=fila>
      <span><svg width=64 height=64 viewBox="0 0 32 32">{micro_in}</svg>64</span>
      <span><svg width=32 height=32 viewBox="0 0 32 32">{micro_in}</svg>32</span>
      <span><svg width=16 height=16 viewBox="0 0 32 32">{micro_in}</svg>16</span>
    </div></div></div>
  <div class="c esc"><span class=n>principal — fundo escuro</span>
    <div class=p>{principal_esc}</div></div>
  <div class="c esc"><span class=n>monocromática</span>
    <div class=p style="color:{creme}">{mono}</div></div>
  <div class=c><span class=n>tamanho mínimo do símbolo — 24px</span>
    <div class=p><div class=fila>
      <span><svg width=24 height=24 viewBox="{vb_sim}">{sim_in}</svg>24</span>
      <span><svg width=40 height=40 viewBox="{vb_sim}">{sim_in}</svg>40</span>
      <span><svg width=72 height=72 viewBox="{vb_sim}">{sim_in}</svg>72</span>
    </div></div></div>
</div>
"""


def main():
    ap = argparse.ArgumentParser(description="Gera as assinaturas da TopShop")
    ap.add_argument("--fonte", default="InstrumentSerif.ttf",
                    help="o .ttf da Instrument Serif")
    ap.add_argument("--saida", default="assets/marca")
    args = ap.parse_args()

    fonte = Path(args.fonte)
    if not fonte.exists():
        print(f"❌ fonte não encontrada: {fonte}\n"
              "   baixe em https://fonts.google.com/specimen/Instrument+Serif")
        return 2

    m = Marca(fonte)
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)

    # ⚠️ O SITE NÃO LÊ SVG DE ARQUIVO, LÊ ESTE .py. Um <img src> não herda o
    # tema (nem currentColor atravessa a fronteira do arquivo), e um asset a
    # mais é um asset que um dia não vai ser deployado junto — foi assim que a
    # logo de outra conta foi parar num vídeo (ver shared/marca.py). Constante
    # em Python viaja com o código.
    modulo = Path("shared/marca_svg.py")
    if modulo.parent.exists():
        modulo.write_text(
            '# GERADO POR gerar_marca.py — NÃO EDITAR À MÃO.\n'
            '# Reconstrua com:  python3 gerar_marca.py --fonte InstrumentSerif.ttf\n'
            '# As cores são variáveis do site (--ink / --marca), então a marca\n'
            '# segue o tema claro/escuro sem uma segunda cópia pra manter.\n\n'
            'PRINCIPAL = %r\n\nWORDMARK = %r\n\nSIMBOLO = %r\n\nMICRO = %r\n'
            % (m.principal(escuro="css"), m.wordmark(escuro="css"),
               m.simbolo(escuro="css"), m.micro()),
            encoding="utf-8")
        print(f"  🐍 {modulo}")

    pecas = {
        "topshop-principal.svg": m.principal(),
        "topshop-wordmark.svg": m.wordmark(),
        "topshop-simbolo.svg": m.simbolo(),
        "topshop-micro.svg": m.micro(),
        "topshop-principal-escuro.svg": m.principal(escuro=True),
        "topshop-wordmark-escuro.svg": m.wordmark(escuro=True),
        "topshop-simbolo-escuro.svg": m.simbolo(escuro=True),
        "topshop-principal-mono.svg": m.principal(mono=True),
        "topshop-simbolo-mono.svg": m.simbolo(mono=True),
    }
    for nome, svg in pecas.items():
        (saida / nome).write_text(svg, encoding="utf-8")
        print(f"  ✏️  {saida/nome}  ({len(svg)} bytes)")

    import re
    miolo = lambda s: re.sub(r"^<svg[^>]*>|</svg>$", "", s)
    vb = re.search(r'viewBox="([^"]+)"', pecas["topshop-simbolo.svg"]).group(1)
    folha = saida / "assinaturas.html"
    folha.write_text(CONTATO.format(
        creme=CREME, navy=NAVY,
        principal=pecas["topshop-principal.svg"],
        principal_esc=pecas["topshop-principal-escuro.svg"],
        wordmark=pecas["topshop-wordmark.svg"],
        simbolo=pecas["topshop-simbolo.svg"],
        mono=pecas["topshop-principal-mono.svg"],
        micro_in=miolo(pecas["topshop-micro.svg"]),
        sim_in=miolo(pecas["topshop-simbolo.svg"]), vb_sim=vb),
        encoding="utf-8")
    print(f"  📄 {folha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
