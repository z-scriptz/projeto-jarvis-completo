#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# preview_layout.py -- renderiza SO 1 frame do layout (header + hook + CTA sobre
# o fundo + um retangulo cinza no lugar do video). RAPIDO: segundos, sem narracao,
# sem audio, sem Gemini, sem producao completa. Usa o CODIGO REAL do video
# (_criar_camadas_topo / _criar_cta_fixo), entao valida o layout de verdade.
#
# Uso na VPS:
#   TOPSHOP_BG=branco .venv/bin/python preview_layout.py "Produto" 'linha1\nA Shopee:' saida.png
#
# Tudo tunavel pelas MESMAS envs da producao: TOPSHOP_BG, LOGO_X/Y/TAM, NOME_FONT,
# HANDLE_FONT, HK_MARGEM, HK_FONT, HK_ALT_LINHA, HK_GAP_VIDEO, VIDEO_Y, VIDEO_W_FRAC,
# CTA_TEXTO, CTA_Y, TXT_MARGEM, etc.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents import narrated_video_agent as N


def main():
    produto = sys.argv[1] if len(sys.argv) > 1 else "Passadeira Ferro a Vapor"
    hook = sys.argv[2] if len(sys.argv) > 2 else '"Minhas roupas vivem amassadas" 🥲\nA Shopee:'
    saida = sys.argv[3] if len(sys.argv) > 3 else "preview.png"
    hook = hook.replace("\\n", "\n")          # aceita \n literal na linha de comando

    mp = N._import_moviepy()
    (VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip,
     concatenate_videoclips, ColorClip, TextClip) = mp
    L, A = N.LARGURA, N.ALTURA
    dur = 1.0

    bg = os.environ.get("TOPSHOP_BG", "preto").strip().lower()
    if bg in ("branco", "white"):
        cor = (255, 255, 255)
    elif bg in ("bege", "claro"):
        cor = (232, 224, 210)
    else:
        cor = (0, 0, 0)
    fundo = N._with_duration(ColorClip((L, A), color=cor), dur)

    # retangulo cinza = "onde o video entra" (so pra visualizar o enquadramento)
    fracw = float(os.environ.get("VIDEO_W_FRAC", "0.82"))
    vw = int(L * fracw)
    vy = int(os.environ.get("VIDEO_Y", "470"))
    vh = min(int(vw * 16 / 9), A - vy - 300)
    video = N._with_duration(ColorClip((vw, vh), color=(128, 130, 134)), dur)
    video = N._with_position(video, ("center", vy))

    camadas = [fundo, video]
    camadas += N._criar_camadas_topo(dur, hook, mp, produto=produto)
    camadas += N._criar_cta_fixo(dur, mp)

    comp = CompositeVideoClip(camadas, size=(L, A))
    comp.save_frame(saida, t=0)
    print("OK preview:", saida, "| fundo:", bg, "| hook:", repr(hook))


if __name__ == "__main__":
    main()
