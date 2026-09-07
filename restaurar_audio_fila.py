#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# restaurar_audio_fila.py -- desfaz o consertar_audio_fila, devolvendo o áudio original
#
# O ESTRAGO (06/09/2026)
# ──────────────────────
# O Dre mandou parar no meio: *"temos que reverter isso agora!!! vamos flopar
# completamente, só 3 áudios pra esse tanto de vídeo"*. E ele está certo.
#
# ⚠️ O ERRO FOI MEU, E ELE TEM NOME. Eu escrevi, ONTEM, o aviso de repetição no
# `produzir_tiktok` ("4 faixas pra 12 vídeos: cada uma repete ~3x"). E aí
# construí o `consertar_audio_fila` — que troca áudio em LOTE, centenas de uma
# vez — SEM esse aviso e sem nenhum piso. Ele só exigia ≥1 trilha. Com 3 faixas
# e 382 vídeos, cada faixa cairia em ~127 posts.
#
# ⚠️ E EU ESCREVI "NÃO APAGA NADA" NO CABEÇALHO DELE. Era verdade sobre o
# ARQUIVO de vídeo (temp + replace), e falso sobre o CONTEÚDO: a faixa de áudio
# original foi sobrescrita, sem cópia. "Não apaga o arquivo" não é o mesmo que
# "não destrói dado", e eu tratei como se fosse.
#
# COMO A RECUPERAÇÃO É POSSÍVEL
# O vídeo de ORIGEM continua em `inbox_tiktok/_produzidos/<pasta>/video.*`, com
# o áudio intacto. Este script recola essa faixa no vídeo já renderizado.
#
# COMO SEI QUAIS FORAM TOCADOS (sem nenhum log, porque eu não gravei nenhum):
# pelo ÁUDIO. Se a faixa do vídeo É uma das nossas 3 trilhas, ele foi trocado.
#
# ⚠️ A 1ª TENTATIVA FOI POR MTIME E FALHOU POR OUTRO ERRO MEU. Eu tinha "salvo"
# o relógio da pasta no consertar_audio_fila — mas capturava DEPOIS do ffmpeg
# escrever o temporário dentro dela, ou seja, restaurava um valor já destruído.
# Os 41 tocados ficaram com data de hoje, e a detecção por mtime achou zero.
# Assinatura tirada do DADO não depende de eu ter acertado o relógio.
#
#   .venv/bin/python restaurar_audio_fila.py            # só lista
#   .venv/bin/python restaurar_audio_fila.py --aplicar  # devolve o áudio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRONTOS = BASE / "pronto_para_postar"
FEITOS = BASE / "inbox_tiktok" / "_produzidos"
INBOX = BASE / "inbox_tiktok"
VIDEO_EXTS = (".mp4", ".mov", ".m4v")
PARCIAIS = (".part", ".ytdl", ".temp", ".tmp", ".download")


def _pcm(caminho: Path, seg: int = 6):
    """Áudio cru, mono 8kHz, pros primeiros `seg` segundos. None se falhar."""
    try:
        import numpy as np
    except Exception:
        return None
    try:
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(caminho), "-t", str(seg),
             "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
            capture_output=True, timeout=90)
        if r.returncode != 0 or len(r.stdout) < 8000:
            return None
        return np.frombuffer(r.stdout, dtype="<i2").astype("float32")
    except Exception:
        return None


def parecido(a, b) -> float:
    """Correlação entre dois trechos de áudio, 0 a 1. Pura, pra dar pra testar.

    ⚠️ NORMALIZA ANTES DE COMPARAR porque a trilha entrou com volume 0.85 — sem
    isso, o mesmo áudio mais baixo pareceria diferente. Normalizado, volume some
    da conta e sobra a FORMA da onda.
    """
    try:
        import numpy as np
    except Exception:
        return 0.0
    if a is None or b is None:
        return 0.0
    n = min(len(a), len(b))
    if n < 8000:                     # menos de 1s: não dá pra afirmar nada
        return 0.0
    x, y = a[:n], b[:n]
    x = x - x.mean()
    y = y - y.mean()
    dx, dy = float(np.sqrt((x * x).sum())), float(np.sqrt((y * y).sum()))
    if dx < 1e-6 or dy < 1e-6:       # silêncio dos dois lados
        return 0.0
    return abs(float((x * y).sum()) / (dx * dy))


def _mapa_origem(slugify) -> dict:
    """slug do pronto_para_postar → vídeo de origem, via `produto` do plano."""
    mapa = {}
    for raiz in (FEITOS, INBOX):
        if not raiz.exists():
            continue
        for pasta in raiz.iterdir():
            if not pasta.is_dir() or pasta.name.startswith("_"):
                continue
            pj = pasta / "plano.json"
            if not pj.exists():
                continue
            try:
                nome = (json.loads(pj.read_text(encoding="utf-8")).get("produto")
                        or "").strip()
            except Exception:
                continue
            if not nome:
                continue
            vids = [v for v in pasta.glob("video.*")
                    if not v.name.endswith(PARCIAIS)]
            if vids:
                mapa.setdefault(slugify(nome), vids[0])
    return mapa


def main() -> int:
    aplicar = "--aplicar" in sys.argv[1:]
    sys.path.insert(0, str(BASE))
    try:
        import produzir_tiktok as PT
        slugify = PT.H._slugify
    except Exception as e:
        print(f"❌ não consegui importar (rode na VPS, com a .venv): {str(e)[:90]}")
        return 1
    if not PRONTOS.exists():
        print(f"❌ {PRONTOS} não existe")
        return 1

    # ── quem foi tocado: o ÁUDIO DELE É UMA DAS NOSSAS TRILHAS ────────────
    #
    # ⚠️ A 1ª VERSÃO USAVA MTIME E NÃO FUNCIONOU — E O MOTIVO FOI OUTRO ERRO MEU
    # (06/09/2026). O `consertar_audio_fila` "preservava" o mtime da pasta, mas
    # capturava o relógio DEPOIS do ffmpeg já ter escrito o arquivo temporário
    # dentro dela — ou seja, restaurava um valor já destruído. Medido: pasta de
    # 30 dias virava 0 antes mesmo da captura.
    #
    # Resultado: os tocados ficaram com data de HOJE (e com `ordem_da_fila:
    # mais_novo` furariam a fila na frente do formato novo), e a detecção por
    # mtime achava 0 deles.
    #
    # Agora a assinatura é o próprio dado: se o áudio do vídeo É uma das nossas
    # 3 trilhas, ele foi trocado. Isso não depende de relógio nenhum.
    trilhas = PT._trilhas()
    if not trilhas:
        print("❌ sem trilhas na pasta de música — não tenho com o que comparar")
        return 1
    print(f"🎧 comparando com {len(trilhas)} trilha(s) nossa(s)…")
    refs = [(t.name, _pcm(t)) for t in trilhas]
    if not any(p is not None for _n, p in refs):
        print("❌ não consegui ler o áudio das trilhas (ffmpeg/numpy?)")
        return 1

    piso = float(os.environ.get("PISO_PARECIDO", "0.90"))
    tocados = []
    for pasta in sorted(PRONTOS.iterdir()):
        if not pasta.is_dir():
            continue
        for v in pasta.iterdir():
            if v.suffix.lower() not in VIDEO_EXTS or v.stat().st_size < 10000:
                continue
            amostra = _pcm(v)
            melhor, qual = 0.0, ""
            for nome, ref in refs:
                s = parecido(amostra, ref)
                if s > melhor:
                    melhor, qual = s, nome
            if melhor >= piso:
                tocados.append((pasta, v, melhor, qual))
            break

    if not tocados:
        print("✅ nenhum vídeo com áudio trocado — nada a restaurar.")
        return 0

    mapa = _mapa_origem(slugify)
    print(f"🔎 {len(tocados)} vídeo(s) com áudio trocado")
    print(f"   {len(mapa)} origem(ns) mapeada(s) em _produzidos/\n")

    ok = semfonte = falhas = 0
    for pasta, v, sim, qual in tocados:
        origem = mapa.get(pasta.name)
        if not origem or not origem.exists():
            semfonte += 1
            print(f"   ❌ SEM ORIGEM  {pasta.name[:40]:42} "
                  f"(bate {sim:.2f} com {qual[:22]})")
            continue
        if not aplicar:
            ok += 1
            print(f"   ↩️  restauraria  {pasta.name[:40]:42} "
                  f"(bate {sim:.2f} com {qual[:22]})")
            continue

        # ⚠️ TEMPORÁRIO FORA DA PASTA. Escrever dentro dela zera o mtime da
        # pasta — foi assim que o `consertar_audio_fila` destruiu a idade de 41
        # pacotes antes mesmo de eu "preservar" o relógio.
        st = pasta.stat()
        relogio = (st.st_atime, st.st_mtime)
        saida = Path(tempfile.gettempdir()) / f"jarvis_restaura_{os.getpid()}.mp4"
        # imagem do RENDERIZADO + áudio do ORIGINAL. -c:v copy: não reprocessa.
        cmd = ["ffmpeg", "-y", "-i", str(v), "-i", str(origem),
               "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
               "-c:a", "aac", "-b:a", "128k", "-shortest", str(saida)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        except subprocess.TimeoutExpired:
            falhas += 1
            print(f"   ⚠️ timeout      {pasta.name[:52]}")
            continue
        if r.returncode == 0 and saida.exists() and saida.stat().st_size > 10000:
            shutil.move(str(saida), str(v))     # temp está noutro filesystem
            # devolve o relógio DA PASTA e do ARQUIVO — assim o vídeo deixa de
            # aparecer como "tocado" e a restauração não vira um novo estrago.
            try:
                os.utime(v, relogio)
                os.utime(pasta, relogio)
            except Exception:
                pass
            ok += 1
            print(f"   ✅ restaurado   {pasta.name[:52]}")
        else:
            falhas += 1
            print(f"   ⚠️ falhou       {pasta.name[:44]}: {(r.stderr or '')[-90:]}")
            try:
                saida.unlink()
            except Exception:
                pass

    print(f"\n── resultado ──")
    if aplicar:
        print(f"   ✅ {ok} restaurados · ❌ {semfonte} sem origem · "
              f"⚠️ {falhas} falharam")
    else:
        print(f"   ↩️  {ok} restauráveis · ❌ {semfonte} sem origem")
        print(f"   (nada foi alterado — use --aplicar)")
    if semfonte:
        print(f"\n   ⚠️ 'SEM ORIGEM' = o pacote saiu de `_produzidos` (foi podado")
        print(f"      ou renomeado). Nesses o áudio original não volta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
