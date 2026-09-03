#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_emoji_gancho.py -- prova que o emoji do gancho não entra mais na frase.
#
# O CASO REAL (04/09/2026): o post do @topshoptech_ saiu com
#     "Achava que livro importante precisava ser sem graça e sem bolso✨"
# e o Dre: *"olha o emoji entrando dentro da frase... é por isso que os vídeo
# fica flopado, parece iniciante"*. Ele culpou o Gemini. Não era o Gemini — o
# emoji é um PNG colado num x calculado, e a quebra de linha enchia a linha
# inteira sem reservar espaço pra ele.
#
# Este teste roda a MATEMÁTICA da quebra sem MoviePy nem fonte: mede largura com
# um modelo simples (largura média por caractere), que é o suficiente pra provar
# a regra "linha + emoji <= teto". A geometria real vem do .env na produção.
#
# Uso:  python3 teste_emoji_gancho.py
import sys

LARGURA = 1080
HK_MARGEM = 54                 # = borda do vídeo com VIDEO_W_FRAC=0.90
HK_MAX_LARG = LARGURA - 2 * HK_MARGEM      # 972
HK_EMOJI_TAM = 40
HK_EMOJI_DX = 18
EMOJI_RESERVA = HK_EMOJI_TAM + HK_EMOJI_DX + 10     # 68

falhas = []


HK_FONT_MAX, HK_FONT_MIN = 60, 34


def larg(txt, fnt):
    """Modelo de largura: ~0,46 do corpo por caractere (Montserrat Light).
    Calibrado pelo caso real: "precisava ser sem graça e sem bolso" (35 chars)
    cabia em UMA linha de 972px no post que saiu → 972/35 ≈ 27,8 ≈ 0,46 × 60."""
    return int(len(txt) * fnt * 0.46)


def wrap(txt, fnt, teto):
    out, cur = [], []
    for w in (txt or "").split():
        if cur and larg(" ".join(cur + [w]), fnt) > teto:
            out.append(" ".join(cur)); cur = [w]
        else:
            cur.append(w)
    if cur:
        out.append(" ".join(cur))
    return out or [txt]


def _quebra_na_fonte(txt, fnt, reserva):
    wl = wrap(txt, fnt, HK_MAX_LARG)
    if reserva and wl and larg(wl[-1], fnt) + reserva > HK_MAX_LARG:
        wl = wrap(txt, fnt, HK_MAX_LARG - reserva)
    return wl


def quebrar(txt, tem_emoji=True, reservar=True):
    """Reproduz a produção INTEIRA: encolhe a fonte até caber em 2 linhas.

    ⚠️ O ENCOLHIMENTO É O QUE CRIA A COLISÃO, e foi o que faltou na 1ª versão
    deste teste: sem ele o texto quebrava em 3 linhas curtas e o emoji nunca
    encostava — o teste passava nos dois lados e não provava nada. Encolher até
    2 linhas é justamente o que deixa a linha CHEIA."""
    reserva = EMOJI_RESERVA if (tem_emoji and reservar) else 0
    fnt = HK_FONT_MAX
    linhas = _quebra_na_fonte(txt, fnt, reserva)
    while fnt > HK_FONT_MIN and len(linhas) > 2:
        fnt -= 2
        linhas = _quebra_na_fonte(txt, fnt, reserva)
    return linhas, fnt


def checa(nome, ok, detalhe=""):
    print(f"  {'✅' if ok else '❌'} {nome}{('  — ' + detalhe) if detalhe else ''}")
    if not ok:
        falhas.append(nome)


def cabe(linhas, fnt):
    """O emoji fica na folga PEDIDA, ou o clamp espremeu ele contra o texto?

    ⚠️ O CRITÉRIO CERTO NÃO É "SOBREPÔS". Minha 1ª versão testava
    `x_emoji >= fim_texto` e passava no caso defeituoso: o emoji ficava 2px
    depois do texto — tecnicamente sem sobrepor, visualmente "bolso✨" colado,
    que é exatamente o que o Dre viu. O defeito é a folga espremida pelo
    `min(..., LARGURA - HK_EMOJI_TAM - 10)`, não a sobreposição."""
    fim_texto = HK_MARGEM + 8 + larg(linhas[-1], fnt)
    pedido = fim_texto + HK_EMOJI_DX
    x_emoji = min(pedido, LARGURA - HK_EMOJI_TAM - 10)
    return x_emoji == pedido, fim_texto, x_emoji


print("── o gancho REAL que floppou no @topshoptech_ ──")
HOOK = "Achava que livro importante precisava ser sem graça e sem bolso"

antes, f_a = quebrar(HOOK, reservar=False)     # regra ANTIGA
ok_antes, ft_a, xe_a = cabe(antes, f_a)
print(f"     ANTES  (fonte {f_a}px): {antes}")
print(f"            texto acaba em x={ft_a} · emoji iria pra x={xe_a}"
      f"{'   ← COLADO (clamp mordeu)' if not ok_antes else ''}")

depois, f_d = quebrar(HOOK)                    # regra NOVA
ok_depois, ft_d, xe_d = cabe(depois, f_d)
print(f"     DEPOIS (fonte {f_d}px): {depois}")
print(f"            texto acaba em x={ft_d} · emoji vai pra x={xe_d}")
print()
# ⚠️ o teste só vale se o caso ANTIGO de fato reproduzia o defeito. Um teste que
# passa nos dois lados não prova nada.
checa("a regra antiga REPRODUZ o defeito", not ok_antes,
      f"folga de só {xe_a - ft_a}px (pedia {HK_EMOJI_DX}px) — colado")
checa("a regra nova mantém a folga", ok_depois, f"folga {xe_d - ft_d}px")

print("\n── outros ganchos reais das contas ──")
CASOS = [
    "Achava que mãe só queria amor, mas tem um segredo.",
    "Eu vivia adiando qualquer coisa que me tirasse do quentinho.",
    "Eu subestimava o poder de um detalhe pra transformar qualquer roupa.",
    "Tem gadget que parece bobo até você usar uma semana",
    "Achava que a tela grande do cinema era insubstituível.",
    "Eu vivia adiando tirar um pelinho por causa da dor e da bagunça.",
    "Curto",
    "Uma frase absurdamente longa que enche as duas linhas inteiras sem "
    "nenhum respiro pra caber qualquer coisa depois dela no fim",
]
for h in CASOS:
    ls, f = quebrar(h)
    ok, ft, xe = cabe(ls, f)
    checa(f"{h[:42]}… ({len(ls)}L, {f}px)", ok, f"folga {xe - ft}px")

print("\n── sem emoji: NÃO pode encurtar a linha à toa ──")
com, _ = quebrar(HOOK, tem_emoji=True)
sem, _ = quebrar(HOOK, tem_emoji=False)
checa("sem emoji usa o orçamento cheio", len(sem) <= len(com),
      f"sem={len(sem)}L com={len(com)}L")

print()
if falhas:
    print(f"❌ {len(falhas)} falha(s): {', '.join(falhas)}")
    sys.exit(1)
print("✅ tudo passou")
