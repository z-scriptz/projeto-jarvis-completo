#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# diag_corte.py -- ligar o CORTE_INTRO_AUTO vai cortar onde deve?
#
# A PENDÊNCIA QUE ISTO FECHA
# ──────────────────────────
# O `CORTE_INTRO_AUTO` está pronto desde 03/09 e DESLIGADO desde então, porque
# a condição que eu mesmo pus foi "só ligar depois de olhar 2-3 vídeos com o
# corte aplicado". Produzir 3 vídeos custa 30 min de VPS e mostra 3 casos —
# amostra pequena demais pra decidir uma chave que vale pra fila inteira.
#
# Aqui o detector roda no vídeo DE VERDADE, sem produzir nada, e devolve:
#   1. quantos seriam cortados, e de quanto (a distribuição)
#   2. uma folha de provas: o frame 0 ao lado do frame do corte
#
# Aí você olha UMA imagem com 8 pares e decide com base em 40 vídeos, não em 3.
#
# ⚠️ SORTEIA, NÃO PEGA OS PRIMEIROS. Aprendido hoje no `diag_rodizio`: os 40 da
# frente da fila eram 35 de casa, e quase não divergiam — medi a população
# errada e quase declarei um problema real como inexistente.
#
# ⚠️ NÃO GASTA API e NÃO MEXE NO .env: liga o AUTO só dentro deste processo.
#
#   .venv/bin/python diag_corte.py
#   .venv/bin/python diag_corte.py --amostra 60 --provas /tmp/cortes.jpg
#   .venv/bin/python diag_corte.py --amostra 300 --por-perfil
#
# ⚠️ MEDIDO EM 06/09 (40 sorteados): 4 cortados (10%), todos entre 0,8s e 1,0s,
# NENHUM no teto — ou seja, o detector achou transição de verdade nos quatro e
# a trava nunca precisou salvar. Risco baixo (come 1s de um vídeo de 13s), ganho
# modesto.
#
# ⚠️ E O ACHADO QUE IMPORTA: os 44 perfis do tiktok_perfis.txt estão TODOS sem
# `corte=N`. O pedido de 03/09 ("as contas que abrem com 'Amazon Gadgets', corta
# os 2 primeiros segundos") foi construído e nunca ligado, porque faltava saber
# QUAIS perfis têm carimbo. `--por-perfil` responde isso com dado, não memória.
import json
import os
import random
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
INBOX = BASE / "inbox_tiktok"
PARCIAIS = (".part", ".ytdl", ".temp", ".tmp", ".download")


def _dur(v: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(v)],
            capture_output=True, text=True, timeout=60)
        return float((r.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def _frame(v: Path, t: float) -> bytes:
    f = v.with_suffix(f".corte{int(t*100)}.jpg")
    try:
        subprocess.run(["ffmpeg", "-y", "-ss", f"{max(0.0, t):.2f}", "-i", str(v),
                        "-vframes", "1", "-vf", "scale=360:-2", "-q:v", "4",
                        str(f)], capture_output=True, timeout=40)
        return f.read_bytes() if f.exists() and f.stat().st_size > 500 else b""
    except Exception:
        return b""
    finally:
        try:
            f.unlink()
        except Exception:
            pass


def _folha(pares, destino: Path) -> Path:
    """ANTES (frame 0) | DEPOIS (frame do corte), um par por linha.

    ⚠️ É ISTO QUE DECIDE, não o número. O detector pode acertar a estatística e
    ainda cortar no lugar errado: se a ESQUERDA já mostra o produto, o corte
    comeu conteúdo bom; se a esquerda é carimbo/tela parada e a direita é o
    produto em ação, ele fez exatamente o que devia.
    """
    from PIL import Image, ImageDraw
    import io
    L, PAD, ROT = 360, 8, 22
    folha = Image.new("RGB", (L * 2 + PAD * 3, (L + ROT + PAD) * len(pares) + PAD),
                      (250, 250, 250))
    d = ImageDraw.Draw(folha)
    for i, (nome, t, a, b) in enumerate(pares):
        y = PAD + i * (L + ROT + PAD)
        d.text((PAD, y), f"[corta {t:.1f}s]  {nome[:64]}", fill=(20, 20, 20))
        d.text((PAD, y + ROT - 11), "ANTES (0s)", fill=(150, 150, 150))
        d.text((PAD + L + PAD, y + ROT - 11), f"DEPOIS ({t:.1f}s)",
               fill=(150, 150, 150))
        for j, raw in enumerate((a, b)):
            x = PAD + j * (L + PAD)
            try:
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                im.thumbnail((L, L))
                folha.paste(im, (x, y + ROT))
            except Exception:
                d.rectangle([x, y + ROT, x + L, y + ROT + L], outline=(200, 60, 60))
    destino.parent.mkdir(parents=True, exist_ok=True)
    folha.save(str(destino), quality=88)
    return destino


def _por_perfil(vids, TC) -> int:
    """Quais PERFIS abrem com carimbo — pra saber em quem pôr `corte=N`.

    ⚠️ A PERGUNTA REAL (achada em 06/09/2026). O pedido do Dre em 03/09 foi:
    "as contas que começam com 'Amazon Gadgets' de início, pode cortar os 2
    primeiros segundos". A funcionalidade (`corte=N` no tiktok_perfis.txt) foi
    construída e **NUNCA FOI LIGADA**: os 44 perfis estão sem marcação nenhuma,
    e as 3 ocorrências de 'corte=' no arquivo são comentário explicando a
    sintaxe.

    Faltava o dado: QUAIS perfis abrem com carimbo. Isso não está na cabeça de
    ninguém de forma confiável — mas está nos vídeos, e o detector já sabe ler.

    O detector automático é conservador (corta ~1s quando tem certeza). O
    `corte=N` é a decisão humana: "este perfil SEMPRE abre com 2s de intro,
    corta sempre". Um não substitui o outro — este relatório diz em quem vale a
    pena cravar o manual.
    """
    porp = {}
    for pasta, v in vids:
        perfil = pasta.name.rsplit("_", 1)[0] if "_" in pasta.name else pasta.name
        dur = _dur(v)
        if dur <= 0:
            continue
        try:
            t = TC._corte_intro(v, dur, "")
        except Exception:
            continue
        d = porp.setdefault(perfil, {"n": 0, "cortes": []})
        d["n"] += 1
        if t > 0:
            d["cortes"].append(t)

    linhas = []
    for perfil, d in porp.items():
        if d["n"] < 3:
            continue        # 1-2 vídeos não dizem nada sobre um perfil
        taxa = len(d["cortes"]) / d["n"]
        med = (sorted(d["cortes"])[len(d["cortes"]) // 2] if d["cortes"] else 0.0)
        linhas.append((taxa, perfil, d["n"], len(d["cortes"]), med))
    linhas.sort(reverse=True)

    print("\n── carimbo de abertura POR PERFIL (≥3 vídeos) ──")
    if not linhas:
        print("   (nenhum perfil com 3+ vídeos na amostra — use --amostra maior)")
        return 0
    print(f"   {'perfil':34} {'vídeos':>6} {'c/ carimbo':>11} {'mediana':>8}")
    for taxa, perfil, n, c, med in linhas[:25]:
        marca = "  ← candidato a corte=" + str(max(1, round(med))) if taxa >= 0.6 else ""
        print(f"   {perfil[:34]:34} {n:6} {c:6} ({taxa*100:3.0f}%) {med:7.1f}s{marca}")

    cand = [l for l in linhas if l[0] >= 0.6]
    print(f"\n   {len(cand)} perfil(is) com carimbo em 60%+ dos vídeos.")
    if cand:
        print("   ⚠️ ANTES DE CRAVAR: confira 1 vídeo de cada na folha de provas.")
        print("      `corte=N` corta SEMPRE, inclusive nos vídeos daquele perfil")
        print("      que não têm carimbo — por isso o piso é 60% e não 30%.")
    return 0


def main() -> int:
    args = sys.argv[1:]
    n_alvo = 40
    if "--amostra" in args:
        try:
            n_alvo = int(args[args.index("--amostra") + 1])
        except Exception:
            pass
    provas = ""
    if "--provas" in args:
        try:
            provas = args[args.index("--provas") + 1]
        except Exception:
            pass

    # ⚠️ liga o AUTO só AQUI DENTRO. O .env da VPS não é tocado — se o
    # resultado for ruim, não ficou nada ligado por engano.
    os.environ["CORTE_INTRO_AUTO"] = "1"

    sys.path.insert(0, str(BASE))
    try:
        import tiktok_coletor as TC
    except Exception as e:
        print(f"❌ não consegui importar (rode na VPS, com a .venv): {str(e)[:90]}")
        return 1

    if not INBOX.exists():
        print(f"❌ {INBOX} não existe — rode na VPS, dentro de ~/jarvis")
        return 1

    vids = []
    for pasta in INBOX.iterdir():
        if not pasta.is_dir() or pasta.name.startswith("_"):
            continue
        pj = pasta / "plano.json"
        if not pj.exists():
            continue
        try:
            if json.loads(pj.read_text(encoding="utf-8")).get("nao_e_produto"):
                continue
        except Exception:
            continue
        v = [x for x in pasta.glob("video.*") if not x.name.endswith(PARCIAIS)]
        if v:
            vids.append((pasta, v[0]))

    if not vids:
        print("❌ nada na fila — rode na VPS, dentro de ~/jarvis")
        return 1

    random.shuffle(vids)            # sorteia: a frente da fila não é amostra
    vids = vids[:n_alvo]
    print(f"📦 {len(vids)} vídeo(s) sorteados\n")

    if "--por-perfil" in args:
        return _por_perfil(vids, TC)

    cortados, intactos, pares = [], 0, []
    for pasta, v in vids:
        dur = _dur(v)
        # perfil vazio de propósito: quero medir o DETECTOR, não o `corte=N`
        # que você já cravou à mão pra alguns perfis.
        try:
            t = TC._corte_intro(v, dur, "")
        except Exception as e:
            print(f"   ⚠️ {pasta.name[:40]}: {str(e)[:50]}")
            continue
        if t > 0:
            cortados.append((pasta.name, t, dur))
            print(f"   ✂️  {t:4.1f}s de {dur:5.1f}s  ({t/dur*100:4.1f}%)  "
                  f"{pasta.name[:44]}")
            if provas and len(pares) < 10:
                a, b = _frame(v, 0.0), _frame(v, t)
                if a and b:
                    pares.append((pasta.name, t, a, b))
        else:
            intactos += 1

    n = len(vids)
    print(f"\n── resultado ──")
    print(f"   ✂️  {len(cortados)} cortados ({len(cortados)/n*100:.0f}%)")
    print(f"   ▶️  {intactos} sairiam inteiros")
    if cortados:
        ts = sorted(t for _, t, _ in cortados)
        meio = ts[len(ts) // 2]
        print(f"   corte: menor {ts[0]:.1f}s · mediana {meio:.1f}s · "
              f"maior {ts[-1]:.1f}s")
        # ⚠️ o teto é 4s OU 25% da duração, o que for menor. Corte encostado no
        # teto é sinal de que o detector não achou a ação e o cap é que segurou
        # — não é o detector funcionando, é a trava funcionando.
        no_teto = sum(1 for _, t, d in cortados
                      if abs(t - min(4.0, d * 0.25)) < 0.05)
        if no_teto:
            print(f"   ⚠️ {no_teto} bateram no TETO — nesses o detector não "
                  f"achou a ação,\n      quem segurou foi a trava. Olhe esses "
                  f"com atenção redobrada.")

    if provas and pares:
        try:
            alvo = Path(provas)
            if alvo.is_dir() or not alvo.suffix:
                alvo = alvo / "provas_corte.jpg"
            _folha(pares, alvo)
            print(f"\n   🖼️  provas em {alvo}  ({len(pares)} pares)")
            print(f"      ESQUERDA = frame 0 · DIREITA = onde ficaria o começo")
            print(f"      ⚠️ Se a ESQUERDA já mostra o produto, o corte comeu")
            print(f"         conteúdo bom. Se é carimbo/tela parada e a direita")
            print(f"         é o produto, ele fez o que devia.")
        except Exception as e:
            print(f"\n   ⚠️ não montei as provas: {str(e)[:70]}")
    elif provas:
        print(f"\n   (nenhum corte pra mostrar — sem provas a montar)")

    print(f"\n⚠️ NADA FOI LIGADO. Isto rodou com CORTE_INTRO_AUTO=1 só dentro")
    print(f"   deste processo. Pra valer, é CORTE_INTRO_AUTO=1 no .env da VPS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
