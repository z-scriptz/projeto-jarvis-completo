#!/usr/bin/env python3
# auditoria_audio.py -- quantos vídeos saíram (ou vão sair) MUDOS.
#
# POR QUE EXISTE (16/08)
# O ROADMAP tem isto aberto desde 11/08, com ⏳ e sem ninguém ter conferido:
#
#     💳 ELEVENLABS COM PAGAMENTO PENDENTE (11/08) — vídeo saindo MUDO
#     HTTP 401 payment_required · Edge (fallback): No module named 'tts_edge'
#     ⏳ Conferir se algum pacote da esteira entrou sem faixa de áudio
#        enquanto isso durou — esses seriam postados sem narração.
#
# Nenhum TTS funcionando, os DOIS caminhos quebrados ao mesmo tempo. O render
# não falha por isso: ele anota `voz —` no relatório, monta o vídeo e devolve
# "sucesso". O daemon posta. É a MESMA forma de todos os defeitos de 15/08 —
# **o sistema relatando sucesso enquanto entrega a coisa errada, em silêncio.**
#
# ⚠️ E A PERGUNTA NÃO É "TEM ÁUDIO?". Um Reels sem narração mas COM música de
# fundo tem faixa de áudio, toca som, e passa em qualquer teste de "tem
# áudio?" — e ainda assim é o defeito, porque o que vende é a narração. Então
# aqui são TRÊS estados diferentes, nunca um booleano:
#
#   MUDO         sem faixa de áudio nenhuma            (pior caso)
#   SILENCIOSO   tem faixa, mas o volume médio é nada  (faixa vazia)
#   SEM_NARRACAO tem som de verdade, mas o relatório   (o caso do ElevenLabs:
#                do render diz `voz —`                  só a música sobrou)
#   OK           som + voz registrada
#
# O `SEM_NARRACAO` é o que o pagamento pendente produz, e é justamente o que
# um teste ingênuo deixaria passar.
#
# ⚠️ E ELE DIZ O QUE NÃO CONSEGUIU MEDIR. Pacote postado e apagado não deixa
# vídeo no disco: sobre esses, isto aqui não tem opinião — e falar "0 mudos"
# quando não se olhou é pior que não medir, porque parece resultado.
#
# NÃO APAGA, NÃO REPOSTA, NÃO CONSERTA NADA. Só lê e conta.
#
# Uso (na VPS, dentro de ~/jarvis):
#   .venv/bin/python auditoria_audio.py
#   .venv/bin/python auditoria_audio.py --desde 2026-08-10
#   .venv/bin/python auditoria_audio.py --json

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# volume médio (dBFS) abaixo do qual a faixa é, na prática, vazia.
# -50 dB é bem abaixo de música de fundo baixinha (que o projeto usa em
# MUSICA_FUNDO_VOL) e bem acima de silêncio digital puro (-91).
SILENCIO_DB = -50.0

EXT_VIDEO = {".mp4", ".mov", ".webm", ".m4v"}


def _log(m):
    print(f"[audio] {m}", flush=True)


def _ffprobe():
    return shutil.which("ffprobe")


def _ffmpeg():
    caminho = shutil.which("ffmpeg")
    if caminho:
        return caminho
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return exe
    except Exception:
        pass
    return None


def _pastas_de_pacote():
    """Onde os pacotes vivem. Reusa o daemon quando dá, como a auditoria_postagem.

    ⚠️ `daemon_maestro` calcula RAIZ como o diretório ACIMA do módulo. Na VPS
    ele mora em `agents/` e acerta; no repo achatado ele aponta pra fora do
    projeto. Por isso só aceito o caminho do daemon se ele EXISTIR — senão o
    scan roda no lugar errado e imprime "0 mudos" com cara de resposta.
    """
    sys.path.insert(0, str(RAIZ))
    DM = None
    for mod in ("agents.daemon_maestro", "daemon_maestro"):
        try:
            DM = __import__(mod, fromlist=["*"])
            break
        except Exception:
            continue

    alvos = []
    do_daemon = getattr(DM, "PRONTO_DIR", None) if DM else None
    if do_daemon and Path(do_daemon).is_dir():
        pronto = Path(do_daemon)
    else:
        pronto = RAIZ / "pronto_para_postar"
    for p in (pronto, pronto.parent / "fila_vencida", RAIZ / "postados"):
        if p.is_dir():
            alvos.append(p)
    return alvos


def _videos(pastas):
    achados = []
    for base in pastas:
        for v in sorted(base.rglob("*")):
            if v.suffix.lower() in EXT_VIDEO and v.is_file():
                achados.append(v)
    return achados


def _tem_faixa_de_audio(ffprobe, video: Path):
    """(tem_faixa, detalhe). None = não consegui medir — que NÃO é 'não tem'."""
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_name", "-of", "json", str(video)],
            capture_output=True, text=True, timeout=90)
    except Exception as e:
        return None, f"ffprobe não rodou: {str(e)[:60]}"
    if r.returncode != 0:
        return None, f"ffprobe erro: {(r.stderr or '')[:60]}"
    try:
        fluxos = (json.loads(r.stdout or "{}").get("streams") or [])
    except Exception:
        return None, "ffprobe devolveu json inválido"
    if not fluxos:
        return False, "nenhuma faixa de áudio"
    return True, (fluxos[0].get("codec_name") or "?")


def _volume_medio(ffmpeg, video: Path):
    """dBFS médio via `volumedetect`. None = não consegui medir."""
    try:
        r = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostats", "-i", str(video),
             "-af", "volumedetect", "-vn", "-f", "null", "-"],
            capture_output=True, text=True, timeout=180)
    except Exception:
        return None
    for linha in (r.stderr or "").splitlines():
        if "mean_volume:" in linha:
            try:
                return float(linha.split("mean_volume:")[1].split("dB")[0])
            except Exception:
                return None
    return None


def _voz_do_relatorio(video: Path):
    """O que o RENDER anotou. É a única fonte que sabe se houve narração —
    o áudio sozinho não distingue 'só música' de 'música + voz'."""
    rel = video.with_suffix(".relatorio.json")
    if not rel.exists():
        return None, []
    try:
        d = json.loads(rel.read_text(encoding="utf-8"))
    except Exception:
        return None, []
    vozes = [v for v in (d.get("voz") or []) if v and v != "—"]
    return (vozes or None), (d.get("faltou") or [])


def _classificar(tem_faixa, detalhe, db, vozes):
    if tem_faixa is None:
        return "NAO_MEDIDO", detalhe
    if tem_faixa is False:
        return "MUDO", "sem faixa de áudio"
    if db is not None and db <= SILENCIO_DB:
        return "SILENCIOSO", f"faixa presente, volume médio {db:.1f} dB"
    if vozes is None:
        return "SEM_NARRACAO", "tem som, mas o render não registrou voz"
    return "OK", f"voz {'/'.join(vozes)}"


def main():
    p = argparse.ArgumentParser(
        description="Conta quantos pacotes saíram sem narração/sem áudio.")
    p.add_argument("--desde", default="",
                   help="só pacotes modificados a partir de AAAA-MM-DD")
    p.add_argument("--json", action="store_true", help="saída em JSON")
    p.add_argument("--limite", type=int, default=0,
                   help="para depois de N vídeos (0 = todos)")
    args = p.parse_args()

    ffprobe, ffmpeg = _ffprobe(), _ffmpeg()
    if not ffprobe:
        _log("⚠️ ffprobe não encontrado — sem ele NÃO dá pra saber se há faixa")
        _log("   de áudio, e eu não vou chutar. `apt install ffmpeg`.")
        return 2
    if not ffmpeg:
        _log("⚠️ sem ffmpeg: consigo ver se HÁ faixa, mas não medir o volume.")
        _log("   'SILENCIOSO' (faixa vazia) vai passar como se tivesse som.")

    corte = None
    if args.desde:
        try:
            corte = datetime.strptime(args.desde, "%Y-%m-%d").replace(
                tzinfo=timezone.utc).timestamp()
        except ValueError:
            _log(f"--desde inválido: {args.desde!r} (use AAAA-MM-DD)")
            return 2

    pastas = _pastas_de_pacote()
    if not pastas:
        _log("nenhuma pasta de pacote encontrada — nada a medir.")
        _log("   procurei: pronto_para_postar/, fila_vencida/, postados/")
        return 1
    _log("olhando: " + " · ".join(str(x) for x in pastas))

    videos = _videos(pastas)
    if corte:
        antes = len(videos)
        videos = [v for v in videos if v.stat().st_mtime >= corte]
        _log(f"{antes} vídeo(s) no disco · {len(videos)} a partir de "
             f"{args.desde}")
    if args.limite:
        videos = videos[:args.limite]

    if not videos:
        _log("nenhum vídeo no filtro. Sem opinião — não é '0 mudos'.")
        return 0

    linhas, contagem = [], {}
    for i, v in enumerate(videos, 1):
        tem, det = _tem_faixa_de_audio(ffprobe, v)
        db = _volume_medio(ffmpeg, v) if (ffmpeg and tem) else None
        vozes, faltou = _voz_do_relatorio(v)
        estado, motivo = _classificar(tem, det, db, vozes)
        contagem[estado] = contagem.get(estado, 0) + 1
        linhas.append({
            "video": str(v.relative_to(RAIZ)) if str(v).startswith(str(RAIZ))
                     else str(v),
            "pasta": v.parent.name,
            "estado": estado,
            "motivo": motivo,
            "db": db,
            "voz": vozes or [],
            "faltou_no_render": faltou,
            "modificado": datetime.fromtimestamp(
                v.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
        })
        if not args.json and i % 20 == 0:
            _log(f"   … {i}/{len(videos)}")

    if args.json:
        print(json.dumps({"total": len(videos), "contagem": contagem,
                          "itens": linhas}, ensure_ascii=False, indent=2))
        return 0

    print()
    print(f"  {len(videos)} vídeo(s) medido(s)")
    for estado in ("MUDO", "SILENCIOSO", "SEM_NARRACAO", "OK", "NAO_MEDIDO"):
        if estado in contagem:
            print(f"    {estado:13} {contagem[estado]}")
    print()

    ruins = [l for l in linhas
             if l["estado"] in ("MUDO", "SILENCIOSO", "SEM_NARRACAO")]
    if ruins:
        print(f"  ⚠️ {len(ruins)} pacote(s) que iriam (ou foram) pro ar sem "
              f"narração:")
        for l in ruins[:30]:
            print(f"    [{l['estado']:12}] {l['modificado']}  "
                  f"{l['pasta'][:44]}")
            print(f"                    {l['motivo']}")
        if len(ruins) > 30:
            print(f"    … e mais {len(ruins) - 30}")
        print()
        print("  Esses estão em pronto_para_postar/ — o daemon posta nos "
              "horários.")
        print("  Pra impedir, mova a pasta ANTES do próximo slot. Reproduzir")
        print("  depende do TTS estar de pé (era o pagamento do ElevenLabs).")

    naomedido = contagem.get("NAO_MEDIDO", 0)
    if naomedido:
        print(f"  ⚠️ {naomedido} não deu pra medir — NÃO conte como bom.")

    # ⚠️ o limite honesto desta ferramenta, dito antes que alguém conclua
    # demais a partir dela
    print()
    print("  ⚠️ Isto só vê vídeo que AINDA está no disco. Pacote postado e")
    print("     apagado não deixa arquivo — sobre esses eu não tenho opinião.")
    print("     Pra saber se um post JÁ PUBLICADO saiu mudo, o caminho é o")
    print("     próprio Instagram, não este disco.")

    return 1 if ruins else 0


if __name__ == "__main__":
    sys.exit(main())
