#!/usr/bin/env python3
# conferir_render.py -- OLHA o vídeo que o render acabou de fazer.
#
# POR QUE EXISTE (09/08/2026)
# O Dre viu o piloto e disse a coisa mais importante do dia:
#
#   "muitos problemas só aparecem depois que o vídeo existe. O render não pode
#    ser o último estágio lógico do sistema: render → inspeção → correção."
#
# Ele está certo, e a prova é o próprio piloto. Os quatro defeitos que
# apareceram — cartão saindo da tela no zoom, legenda lavada, palavra isolada,
# emoji quebrado — NÃO existem no storyboard nem no EDL. Os dois estavam
# perfeitos. Os defeitos nasceram no encontro do plano com o pixel, e só um
# olho no arquivo pronto os encontra.
#
# ⚠️ E EU SÓ OS ACHEI PORQUE OLHEI. Se eu tivesse renderizado oito vídeos e
# postado, os quatro teriam ido ao ar. Esta é a diferença entre um sistema que
# executa e um que confere o que executou.
#
# O QUE ISTO É E O QUE NÃO É
# ──────────────────────────
# É uma checagem DETERMINÍSTICA no arquivo final: mede pixel e tempo, não pede
# opinião a modelo nenhum. Cada achado é um fato verificável, com o número que
# o produziu — na mesma disciplina do `--minimo 3` do ranking e da regra de
# ouro do ROADMAP (fato → observação → hipótese, nunca "achei estranho").
#
# NÃO é julgamento estético. "O vídeo é bom?" continua sendo pergunta pra olho
# humano e, mais adiante, pro visual_audit_agent com Gemini Vision (que hoje
# audita os INGREDIENTES — se o clipe combina com o produto — e não o BOLO).
# Reaproveitar o Vision dele pro arquivo pronto é o passo seguinte natural.
#
# O QUE ELE CONFERE (e qual defeito real cada um pegaria)
#   duracao          arquivo ≠ EDL          → conform/áudio saiu do lugar
#   moldura_estavel  a moldura muda         → o zoom está comendo a marca
#                                             (foi EXATAMENTE o bug do cartão)
#   midia_viva       a mídia não muda       → zoompan quebrado, vídeo parado
#   quadro_morto     quadro chapado         → asset falhou, saiu tela lisa
#   contraste_texto  faixa da legenda lisa  → legenda lavada ou ausente
#                                             (foi EXATAMENTE o bug do fade)
#   faixa_preenchida buraco na faixa        → foto pequena demais pro bloco
#
# Uso:
#   python3 conferir_render.py --video shared/renders/x.mp4
#   python3 conferir_render.py --video x.mp4 --quadros 12 --contato

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Quantos quadros amostrar. 10 num vídeo de 20s dá um a cada 2s — o suficiente
# pra pegar defeito que dura um corte inteiro, que é o tipo que importa. Defeito
# de 3 quadros não se vê no feed.
N_QUADROS = 10

TOL_DURACAO = 0.35        # segundos de diferença entre arquivo e EDL
DIF_MOLDURA = 2.0         # a moldura é a MESMA imagem o vídeo inteiro: qualquer
                          # diferença média acima disto é invasão
DIF_MIDIA_MIN = 1.2       # abaixo disto a mídia está praticamente parada
DESVIO_MORTO = 6.0        # desvio-padrão de um quadro chapado
CONTRASTE_MIN = 28.0      # desvio-padrão na faixa da legenda com texto legível


def _log(m):
    print(f"[conferir] {m}", flush=True)


def _ffmpeg() -> str:
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ""


def _dur(ff: str, arq: Path) -> float:
    import re
    try:
        r = subprocess.run([ff, "-hide_banner", "-i", str(arq)],
                           capture_output=True, text=True, timeout=60)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", r.stderr)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        pass
    return 0.0


def _extrair(ff: str, video: Path, pasta: Path, n: int, dur: float) -> list:
    pasta.mkdir(parents=True, exist_ok=True)
    fora = []
    for k in range(n):
        t = dur * (k + 0.5) / n
        alvo = pasta / f"q{k:02d}_{t:05.1f}s.png"
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                        str(alvo)], capture_output=True, timeout=120)
        if alvo.exists():
            fora.append((round(t, 2), alvo))
    return fora


def _stat(img):
    """(média, desvio) do cinza de uma imagem PIL."""
    from PIL import ImageStat
    s = ImageStat.Stat(img.convert("L"))
    return s.mean[0], s.stddev[0]


def _diferenca(a, b) -> float:
    """Diferença média absoluta entre duas imagens do mesmo tamanho, 0-255."""
    from PIL import ImageChops, ImageStat
    d = ImageChops.difference(a.convert("L"), b.convert("L"))
    return ImageStat.Stat(d).mean[0]


def conferir(video: Path, n_quadros: int = N_QUADROS, contato: bool = False) -> dict:
    from PIL import Image

    ff = _ffmpeg()
    if not ff:
        raise SystemExit("[conferir] FFmpeg não encontrado")

    rel_arq = video.with_suffix(".relatorio.json")
    rel = {}
    if rel_arq.exists():
        try:
            rel = json.loads(rel_arq.read_text(encoding="utf-8"))
        except Exception:
            pass
    lay = rel.get("layout") or {}

    dur = _dur(ff, video)
    pasta = video.with_suffix("").parent / f"{video.stem}_conferencia"
    if pasta.exists():
        shutil.rmtree(pasta, ignore_errors=True)
    quadros = _extrair(ff, video, pasta, n_quadros, dur)
    if not quadros:
        raise SystemExit("[conferir] não consegui extrair nenhum quadro")

    achados = []

    def achar(chave, gravidade, msg, numero=None):
        achados.append({"checagem": chave, "gravidade": gravidade,
                        "descricao": msg, "medido": numero})

    # ── duração ─────────────────────────────────────────────────────────────
    dur_edl = rel.get("duracao_edl")
    if dur_edl and abs(dur - float(dur_edl)) > TOL_DURACAO:
        achar("duracao", "alta",
              f"o arquivo tem {dur:.2f}s e o EDL pediu {dur_edl}s — a narração "
              "ou a linha do tempo saiu do lugar",
              round(dur - float(dur_edl), 2))

    imgs = [(t, Image.open(p)) for t, p in quadros]
    L, A = imgs[0][1].size

    # ── quadro morto ────────────────────────────────────────────────────────
    for t, im in imgs:
        media, desvio = _stat(im)
        if desvio < DESVIO_MORTO:
            achar("quadro_morto", "alta",
                  f"{t}s: quadro praticamente chapado (desvio {desvio:.1f}) — "
                  "asset faltando ou tela lisa", round(desvio, 1))

    # ── moldura estável × mídia viva ────────────────────────────────────────
    # Só dá pra separar as duas zonas se o render disse ONDE fica a mídia. Sem
    # o relatório a checagem não roda — e é dito, não silenciado: checagem que
    # some sem avisar vira falsa sensação de vídeo conferido.
    y0, h = lay.get("y_midia"), lay.get("h_midia")
    if not (y0 and h):
        achar("layout", "media",
              f"não achei o layout em {rel_arq.name} — sem ele não dá pra "
              "separar moldura de mídia, e as duas checagens mais úteis "
              "(invasão da marca e mídia parada) ficam de fora")
    else:
        y1 = y0 + h
        base = imgs[0][1]
        moldura0 = base.crop((0, 0, L, y0))
        rodape0 = base.crop((0, y1, L, A))
        pior_moldura, pior_t = 0.0, 0
        for t, im in imgs[1:]:
            d = max(_diferenca(moldura0, im.crop((0, 0, L, y0))),
                    _diferenca(rodape0, im.crop((0, y1, L, A))))
            if d > pior_moldura:
                pior_moldura, pior_t = d, t
        if pior_moldura > DIF_MOLDURA:
            achar("moldura_estavel", "alta",
                  f"a moldura MUDA ao longo do vídeo (pior em {pior_t}s, "
                  f"diferença {pior_moldura:.1f}) — cabeçalho, hook e CTA "
                  "deviam ficar parados; algo do movimento está invadindo",
                  round(pior_moldura, 1))

        difs = [_diferenca(a[1].crop((0, y0, L, y1)), b[1].crop((0, y0, L, y1)))
                for a, b in zip(imgs, imgs[1:])]
        if difs and max(difs) < DIF_MIDIA_MIN:
            achar("midia_viva", "alta",
                  f"a mídia mal se mexe (maior diferença {max(difs):.2f}) — "
                  "zoom/pan não estão saindo, o vídeo é um slideshow parado",
                  round(max(difs), 2))

        # ── contraste na faixa da legenda ───────────────────────────────────
        # A legenda mora no rodapé da mídia. Texto branco com contorno preto
        # levanta muito o desvio-padrão da faixa; legenda lavada (o bug do fade
        # reiniciado) ou ausente deixa a faixa lisa.
        faixa = (0, max(y0, y1 - 150), L, y1)
        magros = [t for t, im in imgs if _stat(im.crop(faixa))[1] < CONTRASTE_MIN]
        if len(magros) > len(imgs) * 0.6:
            achar("contraste_texto", "media",
                  f"{len(magros)} de {len(imgs)} quadros com a faixa da legenda "
                  f"lisa (desvio < {CONTRASTE_MIN}) — legenda lavada, atrás do "
                  "produto ou simplesmente não desenhada", len(magros))

        # ── a faixa da mídia está preenchida? ───────────────────────────────
        for t, im in imgs[:3]:
            topo = _stat(im.crop((0, y0, L, y0 + 40)))
            baixo = _stat(im.crop((0, y1 - 40, L, y1)))
            if topo[1] < 3 and baixo[1] < 3 and abs(topo[0] - baixo[0]) < 3:
                achar("faixa_preenchida", "baixa",
                      f"{t}s: topo e base da faixa da mídia estão chapados e "
                      "iguais — a foto pode estar pequena demais pro bloco")
                break

    if contato:
        _contato(imgs, pasta / "_contato.png")

    # o que o render já sabia que faltou entra no mesmo relatório: quem confere
    # não deve precisar abrir dois arquivos pra saber o estado do vídeo
    faltou = rel.get("faltou") or []

    resultado = {
        "video": str(video), "duracao": round(dur, 2),
        "duracao_edl": dur_edl, "quadros": len(imgs),
        "pasta_quadros": str(pasta),
        "achados": achados,
        "faltou_no_render": faltou,
        "veredito": ("reprovado" if any(a["gravidade"] == "alta" for a in achados)
                     else "revisar" if achados else "passou"),
    }
    for _, im in imgs:
        im.close()
    (video.with_suffix(".conferencia.json")).write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    return resultado


def _contato(imgs: list, destino: Path):
    """Grade com todos os quadros num PNG só — revisar 10 arquivos é revisar 3."""
    from PIL import Image, ImageDraw
    cols = 5
    lin = (len(imgs) + cols - 1) // cols
    lg, at = 300, 533
    folha = Image.new("RGB", (cols * lg, lin * (at + 26)), (24, 24, 24))
    d = ImageDraw.Draw(folha)
    for i, (t, im) in enumerate(imgs):
        x, y = (i % cols) * lg, (i // cols) * (at + 26)
        folha.paste(im.convert("RGB").resize((lg, at), Image.LANCZOS), (x, y))
        d.text((x + 8, y + at + 6), f"{t}s", fill=(220, 220, 220))
    folha.save(destino)
    _log(f"contato em {destino}")


def main():
    p = argparse.ArgumentParser(description="Confere o MP4 que o render fez.")
    p.add_argument("--video", required=True)
    p.add_argument("--quadros", type=int, default=N_QUADROS)
    p.add_argument("--contato", action="store_true",
                   help="monta uma folha de contato com todos os quadros")
    args = p.parse_args()

    v = Path(args.video)
    if not v.exists():
        raise SystemExit(f"[conferir] não achei {v}")

    r = conferir(v, args.quadros, args.contato)
    icone = {"passou": "✅", "revisar": "👀", "reprovado": "❌"}[r["veredito"]]
    print()
    _log(f"{icone} {r['veredito'].upper()} — {v.name} · {r['duracao']}s · "
         f"{r['quadros']} quadros")
    for a in r["achados"]:
        marca = {"alta": "❌", "media": "👀", "baixa": "·"}[a["gravidade"]]
        print(f"   {marca} [{a['checagem']}] {a['descricao']}")
    if not r["achados"]:
        print("   nenhum defeito mecânico. O julgamento estético continua "
              "sendo seu — os quadros estão em")
        print(f"   {r['pasta_quadros']}")
    if r["faltou_no_render"]:
        print("\n   o render já tinha avisado que faltou:")
        for x in r["faltou_no_render"]:
            print(f"     · {x}")
    return 1 if r["veredito"] == "reprovado" else 0


if __name__ == "__main__":
    sys.exit(main())
