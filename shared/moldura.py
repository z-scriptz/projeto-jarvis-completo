#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# shared/moldura.py -- a GEOMETRIA da faixa de vídeo, em UM lugar só.
#
# POR QUE ISSO EXISTE (03/09/2026)
# ────────────────────────────────
# O Dre: *"o bug é nas duas contas: topshoptech e topshopmoda, estilo ta
# quadrado e a letra + vídeo ta em desordem, comparado as outras contas"*.
#
# A causa não era uma conta com defeito, era DOIS RENDERIZADORES QUE NÃO
# CONCORDAVAM. Dentro do MESMO arquivo (`narrated_video_agent.py`):
#
#   linha 1319 (o gancho):  _video_top = VIDEO_Y            → 500
#   linha 1550 (o vídeo):   _with_position(("center","center"))  → 276
#
# O gancho era ancorado logo acima de y=500 e o vídeo era desenhado em y=276.
# Duas fontes de verdade pra mesma medida, e o texto caía dentro do vídeo. Junto
# disso, a largura estava chumbada em `LARGURA * 0.95` (1026px) ignorando o
# `VIDEO_W_FRAC` (972px), e o `_cantos_arredondados` só existia no
# `telegram_repurpose_hunter.py` — o outro renderizador saía quadrado.
#
# 📌 É EXATAMENTE O MESMO ERRO DE DESENHO QUE A PALETA TEVE. A regra do fundo
# estava copiada em três arquivos e isso pôs a logo do @topshop.__ num vídeo do
# @topshopcasa_; a correção foi o `shared/paleta.py`. Aqui a geometria estava
# copiada em dois e desandou o layout de duas contas. Mesma doença, mesmo
# remédio: quem desenha IMPORTA daqui, ninguém recalcula.
#
# ⚠️ QUEM MEXER NUMA MEDIDA DAQUI MEXE NAS 6 CONTAS. É o objetivo.

import os

LARGURA, ALTURA = 1080, 1920          # canvas 9:16 das 6 contas


def _i(nome: str, padrao) -> int:
    """Env → int, tolerante a lixo. Chave ilegível NÃO pode derrubar o render:
    o `.env` da VPS é editado à mão e um 'VIDEO_Y=50O' (letra O) já aconteceu."""
    try:
        return int(float(str(os.environ.get(nome, padrao)).strip()))
    except (TypeError, ValueError):
        return int(padrao)


def faixa_video() -> dict:
    """A faixa 3:4 onde o vídeo vive: largura, altura, x, y e raio do canto.

    `VIDEO_W_FRAC` é a fração da largura do canvas (0,90 = 972px, "aumentar o
    vídeo nas bordas") e `VIDEO_Y` é o topo absoluto (500, "abaixar + o vídeo").
    A altura vem do 3:4 — nunca de um segundo env, senão dá pra pedir 4:3 sem
    querer.
    """
    frac = float(os.environ.get("VIDEO_W_FRAC", 0.90) or 0.90)
    larg = int(LARGURA * frac)
    larg -= larg % 2                       # par: encoder de vídeo exige
    alt = int(larg * 4 / 3)
    alt -= alt % 2
    return {
        "larg": larg,
        "alt": alt,
        "x": (LARGURA - larg) // 2,        # sempre centralizado na horizontal
        "y": _i("VIDEO_Y", 500),
        "raio": _i("VIDEO_RAIO", 28),
        "borda": (LARGURA - larg) // 2,    # a coluna onde texto e logo alinham
    }


def _image_transform(clip, func):
    """MoviePy v1 (`fl_image`) × v2 (`image_transform`)."""
    if hasattr(clip, "image_transform"):
        return clip.image_transform(func)
    return clip.fl_image(func)


def cantos_arredondados(clip, larg: int, alt: int, cor_fundo, raio: int = None,
                        log=None):
    """Arredonda os cantos da faixa de vídeo — "bordas do vídeo: 3:4 levemente
    arredondadas" (Dre, 02/09), que é o que os dois perfis de referência fazem.

    ⚠️ PINTA OS CANTOS COM A COR DO FUNDO, não usa máscara de transparência.
    Isso é escolha, não atalho: máscara em MoviePy muda de API entre a v1 e a v2
    (`with_mask` × `set_mask`, `ismask` × `is_mask`) e falha de formas diferentes
    em cada uma. Aqui o vídeo é sempre composto sobre um fundo SÓLIDO da paleta,
    então pintar o canto com essa cor é pixel a pixel indistinguível de recortar
    — e não depende de nenhuma API que possa mudar.
    ⚠️ E é justamente por isso que esta função NÃO SERVE sobre fundo com foto ou
    gradiente: ali o canto pintado apareceria como um quadradinho de cor chapada.
    (Foi o caso do `fundo.png` do narrated_video_agent, trocado pela paleta no
    mesmo dia em que esta função passou a ser usada por ele.)

    A borda é suavizada em ~1px (senão o arco sai serrilhado num quadro de
    972px), e só os ~700 pixels dos quatro cantos são tocados por quadro.
    """
    import numpy as np

    raio = _i("VIDEO_RAIO", 28) if raio is None else int(raio)
    if raio <= 0 or larg <= 2 * raio or alt <= 2 * raio:
        return clip
    try:
        # ⚠️ CENTRO DO PIXEL (+0,5), não o índice. Com o índice cru, o pixel da
        # borda reta cai EXATAMENTE sobre o contorno da forma e recebe meio-tom:
        # o resultado não é canto arredondado, é um halo de 1px da cor do fundo
        # em volta do vídeo inteiro. Medido antes de subir: 5.180 pixels tocados
        # por quadro em vez dos ~700 dos quatro cantos.
        ys = np.arange(alt).reshape(-1, 1) + 0.5
        xs = np.arange(larg).reshape(1, -1) + 0.5
        # distância "pra fora" do retângulo interno: 0 nas bordas retas, cresce
        # só dentro das quatro caixas de canto (SDF de retângulo arredondado).
        dx = np.maximum(0, np.maximum(raio - xs, xs - (larg - raio)))
        dy = np.maximum(0, np.maximum(raio - ys, ys - (alt - raio)))
        dist = np.sqrt((dx * dx + dy * dy).astype(np.float32))
        opac = np.clip(raio - dist + 0.5, 0.0, 1.0)      # 1 dentro, 0 fora
        idx = np.nonzero(opac < 1.0)
        if len(idx[0]) == 0:
            return clip
        a = opac[idx].reshape(-1, 1)
        cor = np.array(cor_fundo, dtype=np.float32).reshape(1, 3)
        fundo = cor * (1.0 - a)

        def _pintar(f):
            f = f.copy()
            f[idx] = (f[idx].astype(np.float32) * a + fundo).astype(np.uint8)
            return f

        return _image_transform(clip, _pintar)
    except Exception as e:
        # canto quadrado é um vídeo feio; canto quadrado + exceção é um vídeo
        # que não sai. O aviso fica no log e a produção continua.
        if log is not None:
            log.warning(f"cantos arredondados falharam ({e}) — canto reto")
        return clip


def resumo() -> str:
    """Uma linha pro log/diagnóstico — o que ESTE ambiente vai desenhar."""
    f = faixa_video()
    return (f"vídeo {f['larg']}x{f['alt']} em x={f['x']} y={f['y']} "
            f"(até y={f['y'] + f['alt']}), raio {f['raio']}px, "
            f"coluna do texto x={f['borda']}")


if __name__ == "__main__":
    print(resumo())
