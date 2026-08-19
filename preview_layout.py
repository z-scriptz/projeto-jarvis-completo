#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# preview_layout.py -- renderiza SO 1 frame do layout (header + hook + CTA sobre
# o fundo + um retangulo cinza no lugar do video). RAPIDO: segundos, sem narracao,
# sem audio, sem Gemini, sem producao completa. Usa o CODIGO REAL do video
# (_criar_camadas_topo / _criar_cta_fixo), entao valida o layout de verdade.
#
# ⚠️ CARREGA O .env ANTES DE IMPORTAR O AGENTE (19/08).
# O narrated_video_agent le os knobs de os.environ e NUNCA carrega o .env: em
# producao quem injeta e o systemd (EnvironmentFile). Rodando este preview na
# mao, sem o .env, ele usava NOME_FONT=56/TEXTO_DX=16 (padroes do codigo)
# enquanto a VPS posta com 52/8 — ou seja, a previa mostrava um header que
# NAO era o que ia pro ar. Isso derrota o proposito de existir uma previa.
# Pior: o erro do selo que consertei em 19/08 era exatamente deste tipo (medir
# uma coisa e desenhar outra), e uma previa infiel teria me deixado "confirmar"
# o conserto olhando o quadro errado.
#
# Uso na VPS:
#   .venv/bin/python preview_layout.py                       # previa padrao
#   TOPSHOP_BG=branco .venv/bin/python preview_layout.py "Produto" 'l1\nl2' out.png
#   TOPSHOP_LOGO=logo_ts_casa.png TOPSHOP_HANDLE='@topshopcasa_' \
#       .venv/bin/python preview_layout.py                   # previa de uma conta
#
# Alem do quadro inteiro grava um RECORTE DO TOPO (…_header.png). O selo tem
# 46px num quadro de 1080x1920: no celular ninguem enxerga se esta colado no
# nome ou nao — que era justamente a duvida que originou tudo isso.
#
# Tudo tunavel pelas MESMAS envs da producao: TOPSHOP_BG, LOGO_X/Y/TAM, NOME_FONT,
# HANDLE_FONT, HK_MARGEM, HK_FONT, HK_ALT_LINHA, HK_GAP_VIDEO, VIDEO_Y, VIDEO_W_FRAC,
# CTA_TEXTO, CTA_Y, TXT_MARGEM, SELO_DX, TEXTO_DX, etc.
import os
import sys
from pathlib import Path

BASE = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(BASE))


def _carregar_env():
    """Mesma semantica dos outros carregadores do projeto: a PRIMEIRA ocorrencia
    vence, e quem ja esta no ambiente ganha do arquivo. Isso ultimo importa aqui:
    `TOPSHOP_BG=branco .venv/bin/python preview_layout.py` tem que continuar
    mandando no .env, senao nao da pra prever conta por conta."""
    for cand in (BASE / ".env", Path(".env")):
        if not cand.exists():
            continue
        try:
            linhas = cand.read_text(encoding="utf-8").splitlines()
        except Exception:
            return None
        for linha in linhas:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            chave, _, valor = linha.partition("=")
            chave = chave.strip()
            if chave and chave not in os.environ:
                os.environ[chave] = valor.strip().strip('"').strip("'")
        return cand
    return None


_ENV_LIDO = _carregar_env()   # ANTES do import: o agente le env no import (l.69)

from agents import narrated_video_agent as N          # noqa: E402

# knob -> padrao do codigo. Serve pra previa dizer QUAL numero a gerou; sem
# isso, "ficou torto" nao distingue codigo errado de .env errado.
_KNOBS = [("TOPSHOP_BG", "preto"), ("TOPSHOP_LOGO", "logo_ts.png"),
          ("TOPSHOP_HANDLE", "@topshop._"), ("LOGO_X", "100"), ("LOGO_Y", "112"),
          ("LOGO_TAM", "120"), ("TEXTO_DX", "16"), ("NOME_FONT", "56"),
          ("SELO_DX", "12"), ("TXT_MARGEM", "8"), ("HANDLE_FONT", "46")]


def _relatar_knobs():
    print(f"[previa] .env: {_ENV_LIDO or 'NAO ACHEI — usando padroes do codigo'}")
    for chave, padrao in _KNOBS:
        valor = os.environ.get(chave)
        if valor is None:
            print(f"[previa]   {chave:16} = {padrao:16} (padrao do codigo)")
        else:
            marca = "" if valor == padrao else "  <- difere do padrao"
            print(f"[previa]   {chave:16} = {valor:16} (ambiente){marca}")


def _recorte_do_topo(caminho: str, altura: int = 380):
    """Grava um zoom da faixa do cabecalho. O selo tem 46px num quadro de
    1080x1920 — olhar o quadro inteiro no celular nao responde a pergunta."""
    try:
        from PIL import Image
    except Exception as e:
        print(f"[previa] (sem recorte do topo: {e})")
        return None
    try:
        im = Image.open(caminho)
        topo = im.crop((0, 0, im.width, min(altura, im.height)))
        topo = topo.resize((topo.width * 2, topo.height * 2), Image.LANCZOS)
        saida = str(Path(caminho).with_name(Path(caminho).stem + "_header.png"))
        topo.save(saida)
        return saida
    except Exception as e:
        print(f"[previa] (sem recorte do topo: {e})")
        return None


def main():
    produto = sys.argv[1] if len(sys.argv) > 1 else "Passadeira Ferro a Vapor"
    hook = sys.argv[2] if len(sys.argv) > 2 else '"Minhas roupas vivem amassadas" 🥲\nA Shopee:'
    saida = sys.argv[3] if len(sys.argv) > 3 else "preview.png"
    hook = hook.replace("\\n", "\n")          # aceita \n literal na linha de comando

    _relatar_knobs()

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
    print(f"[previa] OK: {saida} | fundo: {bg} | hook: {hook!r}")
    topo = _recorte_do_topo(saida)
    if topo:
        print(f"[previa] OK: {topo}  <- o zoom do cabecalho (olhe o selo aqui)")


if __name__ == "__main__":
    main()
