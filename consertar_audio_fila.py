#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# consertar_audio_fila.py -- tira a voz gringa dos vídeos JÁ PRONTOS
#
# O PROBLEMA (06/09/2026)
# ───────────────────────
# O `pronto_para_postar` tem 376 vídeos e o conserto do áudio entrou HOJE.
# Nenhum deles passou por ele: todos saíram com o áudio ORIGINAL intocado,
# porque o `NARRAR_TIKTOK` desligado devolvia False sem chamar o plano B.
#
# Pela medição do `diag_voz` (25 sorteados), ~32% têm voz falando. Em 376 isso
# é ~120 vídeos com narração em INGLÊS na fila, e a 9 posts/dia eles vão saindo
# pelos próximos 42 dias.
#
# ⚠️ POR QUE NÃO RE-RENDERIZAR: re-render custa ~10 min por vídeo (63 HORAS pros
# 376). Trocar só a faixa de áudio de um mp4 pronto é `-c:v copy` — segundos,
# sem tocar na imagem. O hook queimado continua o antigo, mas voz em inglês é
# defeito de outra ordem: some da tela quem lê, não some do ouvido de quem
# escuta.
#
# ⚠️ NÃO APAGA NADA. Escreve num temporário e só troca se der certo.
#
#   .venv/bin/python consertar_audio_fila.py            # só mede
#   .venv/bin/python consertar_audio_fila.py --aplicar  # troca de verdade
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRONTOS = BASE / "pronto_para_postar"
VIDEO_EXTS = (".mp4", ".mov", ".m4v")


def main() -> int:
    args = sys.argv[1:]
    aplicar = "--aplicar" in args
    limite = 0
    if "--limite" in args:
        try:
            limite = int(args[args.index("--limite") + 1])
        except Exception:
            pass

    sys.path.insert(0, str(BASE))
    try:
        import produzir_tiktok as PT
    except Exception as e:
        print(f"❌ não consegui importar (rode na VPS, com a .venv): {str(e)[:90]}")
        return 1
    if not PRONTOS.exists():
        print(f"❌ {PRONTOS} não existe")
        return 1
    if not os.getenv("GEMINI_API_KEY"):
        print("❌ GEMINI_API_KEY vazio — o detector de voz não roda")
        return 1

    trilhas = PT._trilhas()
    if aplicar and not trilhas:
        print("❌ sem trilha na pasta de música — não tenho com o que substituir")
        return 1

    vids = []
    for pasta in sorted(PRONTOS.iterdir()):
        if not pasta.is_dir():
            continue
        for v in pasta.iterdir():
            if v.suffix.lower() in VIDEO_EXTS and v.stat().st_size > 10000:
                vids.append(v)
                break
    if not vids:
        print("❌ nenhum vídeo em pronto_para_postar")
        return 1
    if limite:
        vids = vids[:limite]

    print(f"📮 {len(vids)} vídeo(s) prontos · {len(trilhas)} trilha(s) "
          f"disponível(is)")
    print(f"   modo: {'APLICAR (troca o áudio)' if aplicar else 'só medir'}\n")

    com_voz, trocados, falhas, tokens = 0, 0, 0, 0
    for v in vids:
        ver, tk, pq = PT.tem_voz(PT._audio_amostra(v))
        tokens += tk
        if ver == "musica":
            continue
        com_voz += 1
        marca = "🗣️" if ver == "voz" else "⚠️"
        print(f"   {marca} {v.parent.name[:44]:46} {pq}")
        if not aplicar:
            continue

        musica = PT._escolher_musica()
        if not musica or not musica.exists():
            print("      ⚠️ sem trilha — pulo")
            falhas += 1
            continue
        # ⚠️ -c:v copy: a IMAGEM não é reprocessada. É por isso que isto leva
        # segundos e o render leva 10 min — e é por isso que o hook queimado
        # continua o antigo, o que aqui é aceitável.
        saida = v.with_suffix(".novoaudio.mp4")
        vol = os.getenv("MUSICA_SO_VOL", "0.85")
        cmd = ["ffmpeg", "-y", "-i", str(v), "-stream_loop", "-1",
               "-i", str(musica), "-map", "0:v:0", "-map", "1:a:0",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
               "-filter:a", f"volume={vol}", "-shortest", str(saida)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        except subprocess.TimeoutExpired:
            print("      ⚠️ ffmpeg estourou 240s")
            falhas += 1
            continue
        if r.returncode == 0 and saida.exists() and saida.stat().st_size > 10000:
            # ⚠️ GUARDA O RELÓGIO DA PASTA ANTES DE TROCAR (06/09/2026). O
            # `_vencido` do daemon mede a idade pelo mtime da PASTA, e trocar um
            # arquivo dentro dela zera esse mtime — medido: pasta de 40 dias
            # virava de 0. Rodar isto na fila REJUVENESCERIA os vídeos que
            # tocasse (só os ~23% com voz), criando idades falsas e misturadas.
            #
            # Ferramenta de conserto não pode mexer no relógio de validade: ela
            # conserta o áudio, e a fila continua com as idades que tinha.
            try:
                _st = v.parent.stat()
                _relogio = (_st.st_atime, _st.st_mtime)
            except Exception:
                _relogio = None
            saida.replace(v)          # só troca DEPOIS de dar certo
            if _relogio:
                try:
                    os.utime(v.parent, _relogio)
                except Exception:
                    pass
            trocados += 1
            print(f"      🎵 áudio trocado por '{musica.name[:40]}'")
        else:
            falhas += 1
            print(f"      ⚠️ falhou: {(r.stderr or '')[-120:]}")
            try:
                saida.unlink()
            except Exception:
                pass

    n = len(vids)
    print(f"\n── resultado ──")
    print(f"   🗣️ {com_voz} de {n} com voz ({com_voz/n*100:.0f}%)")
    if aplicar:
        print(f"   🎵 {trocados} trocados · ⚠️ {falhas} falharam")
    else:
        print(f"   (nada foi alterado — use --aplicar pra trocar)")
    if tokens:
        usd = float(os.getenv("GEMINI_USD_POR_MTOK", "0.30"))
        brl = float(os.getenv("USD_BRL", "5.40"))
        print(f"   🪙 {tokens:,} tokens · R$ {tokens/1_000_000*usd*brl:.2f}")

    print(f"\n⚠️ ISTO NÃO CONSERTA O HOOK. O texto está queimado na imagem e só")
    print(f"   sai re-renderizando (~10 min por vídeo). Aqui a gente tira a voz")
    print(f"   em inglês, que é o defeito mais grave e o mais barato de tirar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
