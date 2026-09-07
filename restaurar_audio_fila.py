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
# o `consertar_audio_fila` preserva o mtime da PASTA mas o `replace()` deixa o
# ARQUIVO com a hora de agora. Então `video.mp4 mais novo que a pasta` é a
# assinatura exata de quem ele mexeu. Foi sorte, não projeto.
#
#   .venv/bin/python restaurar_audio_fila.py            # só lista
#   .venv/bin/python restaurar_audio_fila.py --aplicar  # devolve o áudio
import json
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRONTOS = BASE / "pronto_para_postar"
FEITOS = BASE / "inbox_tiktok" / "_produzidos"
INBOX = BASE / "inbox_tiktok"
VIDEO_EXTS = (".mp4", ".mov", ".m4v")
PARCIAIS = (".part", ".ytdl", ".temp", ".tmp", ".download")


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

    # ── quem foi tocado: arquivo mais novo que a pasta ────────────────────
    tocados = []
    for pasta in sorted(PRONTOS.iterdir()):
        if not pasta.is_dir():
            continue
        for v in pasta.iterdir():
            if v.suffix.lower() not in VIDEO_EXTS or v.stat().st_size < 10000:
                continue
            # 5s de folga: produção grava pasta e arquivo quase juntos
            if v.stat().st_mtime > pasta.stat().st_mtime + 5:
                tocados.append((pasta, v))
            break

    if not tocados:
        print("✅ nenhum vídeo com áudio trocado — nada a restaurar.")
        return 0

    mapa = _mapa_origem(slugify)
    print(f"🔎 {len(tocados)} vídeo(s) com áudio trocado")
    print(f"   {len(mapa)} origem(ns) mapeada(s) em _produzidos/\n")

    ok = semfonte = falhas = 0
    for pasta, v in tocados:
        origem = mapa.get(pasta.name)
        if not origem or not origem.exists():
            semfonte += 1
            print(f"   ❌ SEM ORIGEM  {pasta.name[:52]}")
            continue
        if not aplicar:
            ok += 1
            print(f"   ↩️  restauraria  {pasta.name[:44]:46} ← {origem.parent.name[:26]}")
            continue

        saida = v.with_suffix(".origaudio.mp4")
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
            st = pasta.stat()
            relogio = (st.st_atime, st.st_mtime)
            saida.replace(v)
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
