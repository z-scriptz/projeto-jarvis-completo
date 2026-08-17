#!/usr/bin/env python3
# auditoria_video.py -- quantos pacotes na esteira têm vídeo QUEBRADO.
#
# POR QUE EXISTE (17/08)
# A @topshoptech_ ficou 3 dias sem postar. A causa foi UM pacote
# (`mesa_magica_de_desenho_projetor_de_giraf`) que o Instagram e o Facebook
# recusaram, com `ProcessingFailedError · retriable: False`. O `ffprobe` disse
# por quê, e a resposta não foi a que eu esperava:
#
#   METADADOS                     BITSTREAM
#   h264 · 1080x1920 · 30fps      Invalid NAL unit size (-37075930 > 10943)
#   7,93s · aac                   Error splitting the input into NAL units
#   ^ dentro do padrão de Reels   ^ centenas de vezes
#
# **O arquivo não está fora de especificação — está CORROMPIDO.** O container
# mente bonito: resolução, proporção, fps e duração todos certos. Quem olha só
# o `ffprobe -show_entries` (como eu ia fazer) aprova o vídeo. O defeito está
# no fluxo H.264 lá dentro, e só aparece quando alguém tenta DECODIFICAR.
#
# ⚠️ E É POR ISSO QUE ESTE ARQUIVO EXISTE. Um pacote quebrado custa 2 slots da
# conta antes da quarentena tirá-lo da frente. Se o render está produzindo isso
# em série, a quarentena vira enxugar gelo — cada vídeo novo derruba uma conta
# por 2 slots. A pergunta "é um ou são muitos?" decide se o conserto é limpar a
# fila ou consertar o render, e ela não se responde por palpite.
#
# COMO ELE TESTA: decodifica de verdade (`ffmpeg -f null -`), porque só a
# decodificação revela NAL corrompido. Por padrão só os primeiros segundos
# (`--segundos 3`): a corrupção medida aqui aparece do começo ao fim, e 3s por
# arquivo permite varrer a esteira inteira. `--completo` decodifica tudo.
#
# NÃO MOVE, NÃO APAGA, NÃO POSTA. Só lê e conta.
#
# Uso (na VPS, dentro de ~/jarvis):
#   .venv/bin/python auditoria_video.py
#   .venv/bin/python auditoria_video.py --limite 40
#   .venv/bin/python auditoria_video.py --completo --json

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# marcas de bitstream corrompido no stderr do ffmpeg. Só entram erros que
# significam DADO QUEBRADO — nada de aviso cosmético, senão o relatório enche
# de falso positivo e ninguém confia nele.
MARCAS = (
    "Invalid NAL unit size",
    "Error splitting the input into NAL units",
    "missing picture in access unit",
    "Invalid data found when processing input",
    "moov atom not found",
    "Truncating packet of size",
    "corrupt decoded frame",
    "error while decoding MB",
)


def _log(m):
    print(f"[video] {m}", flush=True)


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


def _pastas():
    """As pastas de pacote, do daemon quando dá (a mesma disciplina da
    auditoria_postagem: caminho do daemon só se ele EXISTIR)."""
    sys.path.insert(0, str(RAIZ))
    DM = None
    for mod in ("agents.daemon_maestro", "daemon_maestro"):
        try:
            DM = __import__(mod, fromlist=["*"])
            break
        except Exception:
            continue
    do_daemon = getattr(DM, "PRONTO_DIR", None) if DM else None
    pronto = (Path(do_daemon) if do_daemon and Path(do_daemon).is_dir()
              else RAIZ / "pronto_para_postar")
    alvos = [p for p in (pronto,
                         pronto.parent / "fila_problema",
                         pronto.parent / "fila_vencida") if p.is_dir()]
    return pronto, alvos


def _checar(ffmpeg, video: Path, segundos: int):
    """(quebrado, [erros distintos]) — None em quebrado = não deu pra testar."""
    cmd = [ffmpeg, "-v", "error", "-nostdin"]
    if segundos > 0:
        cmd += ["-t", str(segundos)]
    cmd += ["-i", str(video), "-f", "null", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return None, ["ffmpeg travou (timeout)"]
    except Exception as e:
        return None, [f"ffmpeg não rodou: {str(e)[:60]}"]

    achados = []
    for linha in (r.stderr or "").splitlines():
        for m in MARCAS:
            if m in linha and m not in achados:
                achados.append(m)
    return (bool(achados), achados)


def main():
    p = argparse.ArgumentParser(
        description="Procura vídeo corrompido nos pacotes prontos.")
    p.add_argument("--segundos", type=int, default=3,
                   help="quantos segundos decodificar por vídeo (0 = tudo)")
    p.add_argument("--completo", action="store_true",
                   help="decodifica o vídeo inteiro (mesma coisa que --segundos 0)")
    p.add_argument("--limite", type=int, default=0,
                   help="para depois de N vídeos (0 = todos)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    segundos = 0 if args.completo else max(0, args.segundos)

    ffmpeg = _ffmpeg()
    if not ffmpeg:
        _log("⚠️ ffmpeg não encontrado — sem ele NÃO dá pra decodificar, e eu")
        _log("   não vou chamar de bom o que não testei. `apt install ffmpeg`.")
        return 2

    pronto, alvos = _pastas()
    if not alvos:
        _log(f"nenhuma pasta de pacote em {pronto.parent} — nada a medir.")
        return 1

    videos = []
    for base in alvos:
        for pasta in sorted(base.iterdir()):
            v = pasta / "video.mp4"
            if pasta.is_dir() and v.exists():
                videos.append((base.name, pasta.name, v))
    if args.limite:
        videos = videos[:args.limite]

    if not videos:
        _log("nenhum video.mp4 encontrado. Sem opinião — não é '0 quebrados'.")
        return 0

    _log(f"{len(videos)} vídeo(s) · decodificando "
         + (f"{segundos}s de cada" if segundos else "INTEIROS")
         + " · isto leva alguns minutos")

    t0 = time.time()
    quebrados, naomedidos, ok = [], [], 0
    for i, (onde, slug, v) in enumerate(videos, 1):
        ruim, erros = _checar(ffmpeg, v, segundos)
        reg = {"pasta": onde, "slug": slug, "erros": erros,
               "mb": round(v.stat().st_size / 1e6, 1)}
        if ruim is None:
            naomedidos.append(reg)
        elif ruim:
            quebrados.append(reg)
        else:
            ok += 1
        if not args.json and i % 25 == 0:
            _log(f"   … {i}/{len(videos)}  ({time.time() - t0:.0f}s)")

    if args.json:
        print(json.dumps({"total": len(videos), "ok": ok,
                          "quebrados": quebrados, "nao_medidos": naomedidos},
                         ensure_ascii=False, indent=2))
        return 0

    print()
    print(f"  {len(videos)} vídeo(s) testado(s) em {time.time() - t0:.0f}s")
    print(f"    íntegros   {ok}")
    print(f"    QUEBRADOS  {len(quebrados)}")
    if naomedidos:
        print(f"    não medidos {len(naomedidos)}  ⚠️ NÃO conte como bons")
    print()

    if quebrados:
        # ⚠️ a distribuição por pasta é o que separa "um acidente" de "o render
        # está gerando lixo": defeito só em `fila_problema/` é história antiga;
        # defeito em `pronto_para_postar/` é fila viva que vai derrubar conta.
        na_esteira = [q for q in quebrados if q["pasta"] == pronto.name]
        print(f"  ⚠️ {len(na_esteira)} deles estão em {pronto.name}/ — "
              f"cada um custa 2 slots da conta antes da quarentena agir.")
        print()
        for q in quebrados[:25]:
            print(f"    [{q['pasta'][:16]:16}] {q['slug'][:44]:44} "
                  f"{q['mb']:5.1f} MB")
            print(f"                     {' · '.join(q['erros'][:2])}")
        if len(quebrados) > 25:
            print(f"    … e mais {len(quebrados) - 25}")
        print()
        pc = 100 * len(quebrados) / len(videos)
        if pc >= 5:
            print(f"  🔴 {pc:.0f}% da esteira está quebrada — isso não é "
                  f"acidente de um arquivo.")
            print("     O conserto é no RENDER, não em limpar a fila: limpar "
                  "hoje só adia,")
            print("     porque a produção repõe ~12/dia no mesmo estado.")
        else:
            print(f"  🟡 {pc:.0f}% — parece acidente pontual, não defeito de "
                  f"linha. Tirar da")
            print("     esteira resolve; vale reconferir daqui a alguns dias.")
    else:
        print("  ✅ nenhum vídeo corrompido no que foi testado.")
        if segundos:
            print(f"     ⚠️ só os primeiros {segundos}s de cada um. Corrupção "
                  f"que comece depois")
            print("        disso passaria — use --completo pra varrer inteiro.")

    print()
    print("  NADA FOI MOVIDO OU APAGADO. Este script só lê.")
    return 1 if quebrados else 0


if __name__ == "__main__":
    sys.exit(main())
