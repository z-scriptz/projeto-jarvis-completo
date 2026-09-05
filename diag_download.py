#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# diag_download.py -- os vídeos do inbox estão truncados de verdade?
#
# A PERGUNTA (05/09/2026)
# ───────────────────────
# Quase todo render loga isto:
#
#   UserWarning: 1441836 bytes wanted but 0 bytes read at frame index 954
#                (out of a total 958 frames)
#
# E um pacote morreu de vez com "failed to read the first frame".
#
# ⚠️ MINHA HIPÓTESE É QUE A MAIORIA DESSES AVISOS É INOFENSIVA, e hipótese minha
# já errou várias vezes neste projeto. O padrão que me faz suspeitar: a falha é
# SEMPRE nos últimos 2 a 6 frames (412-414 de 415, 705 de 707, 289-294 de 294).
# Download truncado de verdade perde pedaço aleatório e grande, não sempre a
# poeirinha do fim. O moviepy calcula o total como `duração × fps` e pede frame
# que nunca existiu — isso é arredondamento dele, não arquivo quebrado.
#
# Mas suspeita não é medição. Este script MEDE, com ffmpeg/ffprobe:
#
#   1. o arquivo decodifica inteiro sem erro?      (ffmpeg -v error -f null)
#   2. quantos frames existem DE VERDADE?          (ffprobe -count_frames)
#   3. quantos o moviepy vai pedir?                (int(duração × fps))
#   4. tem arquivo .part/.ytdl sendo tratado como vídeo?
#
# E classifica cada um em: ok · arredondamento · TRUNCADO · ILEGÍVEL
#
#   .venv/bin/python diag_download.py                    # amostra de 25
#   .venv/bin/python diag_download.py --tudo             # inteiro (~3h30)
#   .venv/bin/python diag_download.py --frame0           # caça os venenos (~15min)
#   .venv/bin/python diag_download.py --frame0 --marcar  # ...e tira da fila
#
# ✅ MEDIDO EM 05/09/2026 (amostra de 25 no inbox real): 0 truncados, 0
# ilegíveis, 0 arquivos parciais em 2693. 68% deram 'arredondamento' (2 a 8
# frames a menos) com o decoder COMPLETAMENTE CALADO. A hipótese estava certa:
# o barulho no log é do moviepy, os downloads estão íntegros.
# ⚠️ Com n=25 e zero defeitos, a regra de três dá teto de ~12% — e sabe-se de
# 1 quebrado em 2693. Por isso existe o --frame0: baixo, mas não é zero.
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
PASTAS = [BASE / "inbox_tiktok", BASE / "inbox_tiktok" / "_produzidos"]

# sufixos que o yt-dlp usa pra arquivo INCOMPLETO. Se um destes está sendo
# tratado como vídeo, o download foi interrompido e ninguém percebeu.
SUFIXOS_PARCIAIS = (".part", ".ytdl", ".temp", ".tmp", ".download")


def _ffprobe(v: Path) -> dict:
    """duração, fps e nº de frames REALMENTE decodificáveis."""
    out = {}
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-count_frames", "-show_entries",
             "stream=nb_read_frames,r_frame_rate,duration",
             "-show_entries", "format=duration", "-of", "json", str(v)],
            capture_output=True, text=True, timeout=180)
        d = json.loads(r.stdout or "{}")
        st = (d.get("streams") or [{}])[0]
        out["frames_reais"] = int(st.get("nb_read_frames") or 0)
        fr = st.get("r_frame_rate") or "0/1"
        num, _, den = fr.partition("/")
        out["fps"] = (float(num) / float(den)) if float(den or 0) else 0.0
        out["dur"] = float((d.get("format") or {}).get("duration")
                           or st.get("duration") or 0)
    except Exception as e:
        out["erro_probe"] = str(e)[:60]
    return out


def _decodifica_limpo(v: Path) -> str:
    """Passa o arquivo inteiro pelo decoder. Silêncio = arquivo íntegro.

    ⚠️ ESTE É O TESTE QUE VALE. O aviso do moviepy diz o que o MOVIEPY pediu;
    isto diz o que o ARQUIVO tem. Se aqui sai vazio, o arquivo está bom e o
    aviso é do moviepy pedindo frame que não existe.
    """
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(v), "-f", "null", "-"],
                           capture_output=True, text=True, timeout=300)
        return (r.stderr or "").strip()
    except Exception as e:
        return f"(não rodou: {str(e)[:50]})"


def classificar(erros: str, frames_reais: int, frames_pedidos: int) -> str:
    """O veredito, separado pra ser testável sem ffmpeg.

    'ilegivel'       — nem decodifica: pacote-veneno
    'truncado'       — decodifica mas o decoder reclama, ou falta pedaço grande
    'arredondamento' — arquivo íntegro; o moviepy é que pede 1-6 frames a mais
    'ok'             — íntegro e as contas batem
    """
    if frames_reais <= 0:
        return "ilegivel"
    if erros:
        return "truncado"
    faltando = frames_pedidos - frames_reais
    if faltando <= 0:
        return "ok"
    # ⚠️ o corte de 8 não é teoria: os casos reais do log perderam de 2 a 6
    # frames. Acima disso não dá mais pra chamar de arredondamento.
    return "arredondamento" if faltando <= 8 else "truncado"


def _abre_frame0(v: Path) -> bool:
    """Só o frame 0 — mas pelo MOVIEPY, que é quem de fato renderiza.

    ⚠️ MEU PRIMEIRO TESTE AQUI ERA O ERRADO (05/09/2026, achado pelo próprio
    resultado). Eu usava `ffmpeg -vframes 1`, varri os 2693 e deu 0 quebrados —
    incluindo o `amaziiiigfinds`, que tinha derrubado DUAS rodadas com
    "failed to read the first frame". Os dois não podem estar certos.

    A diferença está no aviso original:

        1769472 bytes wanted but 0 bytes read at frame index 0

    1769472 = 1024 × 576 × 3. O moviepy abre um cano de rawvideo esperando
    exatamente um frame nessas dimensões e recebe ZERO bytes. O
    `ffmpeg -vframes 1` só pede "um frame decodificável qualquer" e consegue.
    **Eu testava uma coisa parecida, não a mesma coisa** — o guarda não pegaria
    o pacote que motivou a existência dele.

    Agora o teste é o próprio moviepy. Só cai no ffmpeg quando não há moviepy
    (dev local), e aí é declaradamente um teste mais fraco.
    """
    try:
        from moviepy.video.io.VideoFileClip import VideoFileClip
    except Exception:
        try:
            r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(v),
                                "-vframes", "1", "-f", "null", "-"],
                               capture_output=True, text=True, timeout=60)
            return r.returncode == 0 and not (r.stderr or "").strip()
        except Exception:
            return True     # não deu pra testar: não condeno o arquivo
    try:
        c = VideoFileClip(str(v))
        try:
            c.get_frame(0)
            return True
        finally:
            try:
                c.close()
            except Exception:
                pass
    except Exception:
        return False


def varrer_frame0(videos: list, marcar: bool) -> int:
    """Caça TODOS os pacotes-veneno de uma vez, em vez de descobrir um por dia.

    ⚠️ POR QUE ESTE MODO EXISTE (05/09/2026). A amostra de 25 deu 0 quebrados,
    mas a gente SABE que existe pelo menos um (o amaziiiigfinds) — a regra de
    três com n=25 só garante teto de ~12%, não zero. E cada veneno que sobra
    queima um slot de produção quando é sorteado, silenciosamente.

    Decodificar os 2693 inteiros custaria ~3h30 de VPS. Só o frame 0 custa
    ~0,3s por arquivo (~15 min no inbox todo) e pega exatamente o defeito que
    para a produção — vídeo que perde o FIM o moviepy contorna sozinho.
    """
    ruins = []
    for i, v in enumerate(videos, 1):
        if i % 250 == 0:
            print(f"   … {i}/{len(videos)} · {len(ruins)} quebrado(s) até aqui")
        if not _abre_frame0(v):
            ruins.append(v)
            print(f"   ☠️  {v.parent.name}")

    print(f"\n── {len(ruins)} de {len(videos)} não abrem o 1º frame "
          f"({len(ruins)/max(1,len(videos))*100:.2f}%) ──")
    if not ruins:
        print("   ✅ nenhum veneno na fila.")
        return 0
    if not marcar:
        print("\n📋 pra tirar da fila: .venv/bin/python diag_download.py "
              "--frame0 --marcar")
        return 0

    marcados = 0
    for v in ruins:
        pj = v.parent / "plano.json"
        try:
            info = json.loads(pj.read_text(encoding="utf-8"))
            # ⚠️ MARCA, NÃO APAGA — mesma regra do limpar_inbox, do
            # conferir_match e do contador de falhas. Reversível tirando a
            # chave do JSON.
            info["nao_e_produto"] = True
            info["motivo_bloqueio"] = "diag_download: vídeo não abre o 1º frame"
            pj.write_text(json.dumps(info, ensure_ascii=False, indent=2),
                          encoding="utf-8")
            marcados += 1
        except Exception as e:
            print(f"   ⚠️ não marquei {v.parent.name}: {str(e)[:50]}")
    print(f"   🚫 {marcados} pacote(s) fora da fila (reversível: tire "
          f"'nao_e_produto' do plano.json)")
    return 0


def main() -> int:
    tudo = "--tudo" in sys.argv[1:]
    so_frame0 = "--frame0" in sys.argv[1:]
    marcar = "--marcar" in sys.argv[1:]
    limite = 10_000 if tudo else 25

    videos, parciais = [], []
    for pasta in PASTAS:
        if not pasta.exists():
            continue
        for p in sorted(pasta.glob("*/video.*")):
            if p.name.endswith(SUFIXOS_PARCIAIS):
                parciais.append(p)
            else:
                videos.append(p)

    if not videos and not parciais:
        print("❌ nenhum vídeo encontrado — rode na VPS, dentro de ~/jarvis")
        return 1

    print(f"📦 {len(videos)} vídeo(s) · {len(parciais)} arquivo(s) PARCIAL\n")

    if parciais:
        # ⚠️ ISTO É DEFEITO CERTO, sem precisar de medição. O `_baixar` faz
        # `destino.glob("video.*")` e 'video.mp4.part' CASA com esse padrão —
        # o mesmo glob está no `_pendentes()` do produtor. Download
        # interrompido vira "vídeo" pronto pra produzir.
        print(f"🚨 {len(parciais)} DOWNLOAD(S) INTERROMPIDO(S) sendo tratados como vídeo:")
        for p in parciais[:15]:
            print(f"   • {p.parent.name}/{p.name}  ({p.stat().st_size:,} bytes)")
        if len(parciais) > 15:
            print(f"   … +{len(parciais) - 15}")
        print()

    if so_frame0:
        return varrer_frame0(videos, marcar)

    amostra = videos[:limite]
    if len(videos) > limite:
        import random
        random.shuffle(videos)
        amostra = videos[:limite]
        print(f"🔬 amostra de {limite} sorteados (use --tudo pro inbox inteiro)\n")

    tot = {"ok": 0, "arredondamento": 0, "truncado": 0, "ilegivel": 0}
    ruins = []
    for v in amostra:
        info = _ffprobe(v)
        reais = info.get("frames_reais", 0)
        pedidos = int(info.get("dur", 0) * info.get("fps", 0))
        erros = _decodifica_limpo(v)
        cls = classificar(erros, reais, pedidos)
        tot[cls] += 1
        marca = {"ok": "✅", "arredondamento": "🟡",
                 "truncado": "❌", "ilegivel": "☠️"}[cls]
        print(f"   {marca} {cls:15} reais={reais:5} pedidos={pedidos:5} "
              f"({pedidos - reais:+3}) · {v.parent.name[:34]}")
        if cls in ("truncado", "ilegivel"):
            ruins.append((v, erros[:150]))

    n = len(amostra)
    print(f"\n── resultado de {n} vídeo(s) ──")
    for k in ("ok", "arredondamento", "truncado", "ilegivel"):
        pct = tot[k] / max(1, n) * 100
        print(f"   {k:15} {tot[k]:4}  ({pct:.0f}%)")

    print()
    quebrados = tot["truncado"] + tot["ilegivel"]
    if quebrados == 0:
        print("✅ NENHUM ARQUIVO QUEBRADO. Os avisos do moviepy são dele: ele pede")
        print("   `duração × fps` frames e o arquivo tem 1-6 a menos. O download")
        print("   está íntegro — o barulho no log é ruído, não perda.")
    else:
        print(f"⚠️ {quebrados} de {n} realmente quebrados ({quebrados/n*100:.0f}%).")
        print("   Aí o problema É o download, e o conserto é no _baixar.")
        for v, e in ruins[:5]:
            print(f"   • {v.parent.name}: {e or '(sem erro do decoder)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
