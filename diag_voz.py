#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# diag_voz.py -- o detector sabe separar "voz narrando" de "só música"?
#
# A PERGUNTA (06/09/2026)
# ───────────────────────
# Correção do Dre: *"é pra sair o áudio tipo narração; se o vídeo gringo for um
# áudio de música, não é pra retirar, é só se tiver alguma voz gringa narrando"*.
#
# O `_so_musica` passou a perguntar pro Gemini antes de trocar. Mas um juiz novo
# não entra em produção sem passar por controle — foi assim com o
# `conferir_match`, e lá o controle negativo salvou a decisão de bloquear 800
# pacotes.
#
# ⚠️ CONTROLE DE GRAÇA: as faixas da nossa pasta de trilha não têm NARRAÇÃO —
# ninguém falando por cima. O detector tem que dizer 'musica' nelas.
#
# ⚠️⚠️ MAS O RÓTULO DESTE CONTROLE É SUPOSIÇÃO MINHA, E ELA JÁ FALHOU. Na 1ª
# rodada escrevi "são MÚSICA PURA, sem voz" e o controle deu 3/4: a faixa
# 'Beautifully Stranded (Reels Sound - Before and After)' voltou como VOZ.
# Só que 'Beautifully Stranded' é nome de CANÇÃO — provavelmente tem vocal
# cantado. Ou seja: pode ser o detector desobedecendo o prompt, ou pode ser eu
# tendo chamado de "música pura" uma faixa com voz cantando.
#
# **Controle não vale mais que o rótulo dele.** Por isso o veredito agora vem
# com o MOTIVO: 'canto em ingles' aponta pro prompt, 'homem narrando' aponta
# pra mim. Sem o motivo, uma reprovação no controle é só um número que não
# conserta nada.
#
# ⚠️ O QUE ESTE CONTROLE NÃO MEDE: a sensibilidade. Ele prova que o detector não
# vê narração onde não tem; NÃO prova que ele acha narração onde tem. Pra isso
# eu precisaria de vídeos gringos rotulados à mão, e não tenho. Está dito aqui
# pra ninguém ler 4/4 e achar que o detector é perfeito.
#
#   .venv/bin/python diag_voz.py --amostra 25
import json
import os
import random
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
INBOX = BASE / "inbox_tiktok"
PARCIAIS = (".part", ".ytdl", ".temp", ".tmp", ".download")


def main() -> int:
    args = sys.argv[1:]
    n_alvo = 25
    if "--amostra" in args:
        try:
            n_alvo = int(args[args.index("--amostra") + 1])
        except Exception:
            pass

    sys.path.insert(0, str(BASE))
    try:
        import produzir_tiktok as PT
    except Exception as e:
        print(f"❌ não consegui importar (rode na VPS, com a .venv): {str(e)[:90]}")
        return 1

    if not os.getenv("GEMINI_API_KEY"):
        print("❌ GEMINI_API_KEY vazio — o detector não roda")
        return 1

    tokens = 0

    # ── CONTROLE: as nossas trilhas são música pura ────────────────────────
    trilhas = PT._trilhas()
    print(f"── controle: {len(trilhas)} trilha(s) nossa(s) — nenhuma tem "
          f"NARRAÇÃO ──")
    print(f"   (canto conta como música; se reprovar, leia o MOTIVO à direita)")
    erros_ctl = 0
    for t in trilhas:
        v, tk, pq = PT.tem_voz(PT._audio_amostra(t))
        tokens += tk
        marca = "✅" if v == "musica" else ("❌" if v == "voz" else "⚠️")
        if v == "voz":
            erros_ctl += 1
        # ⚠️ O MOTIVO É O QUE TORNA A FALHA CONSERTÁVEL: 'canto em ingles'
        # significa prompt fraco; 'homem narrando' significa que a MINHA
        # suposição (as 4 faixas são instrumentais) é que estava errada.
        print(f"   {marca} {v:7} {t.name[:44]:46} {pq}")
    if trilhas:
        print(f"\n   {len(trilhas) - erros_ctl}/{len(trilhas)} certos no controle.")
        if erros_ctl:
            print("   ❌ O DETECTOR VÊ VOZ ONDE SÓ TEM MÚSICA. Ele vai trocar")
            print("      trilha boa por trilha nossa. Não use até eu consertar.")
        else:
            print("   ✅ não inventa voz onde não tem.")
            print("      ⚠️ isto NÃO prova que ele ACHA voz onde tem — pra medir")
            print("         isso eu precisaria de vídeos rotulados à mão.")
    else:
        print("   (sem trilhas na pasta — controle não rodou)")

    # ── a fila de verdade ─────────────────────────────────────────────────
    vids = []
    if INBOX.exists():
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
        print("\n❌ nada na fila")
        return 1

    random.shuffle(vids)          # sorteia: a frente da fila não é amostra
    vids = vids[:n_alvo]
    print(f"\n── {len(vids)} vídeo(s) da fila, sorteados ──")
    tot = {"voz": 0, "musica": 0, "erro": 0}
    for pasta, v in vids:
        ver, tk, pq = PT.tem_voz(PT._audio_amostra(v))
        tokens += tk
        tot[ver] = tot.get(ver, 0) + 1
        marca = {"voz": "🗣️", "musica": "🎧", "erro": "⚠️"}[ver]
        print(f"   {marca} {ver:7} {pasta.name[:40]:42} {pq}")

    n = len(vids)
    print(f"\n── resultado ──")
    print(f"   🗣️ {tot['voz']} com voz (áudio SERÁ trocado)")
    print(f"   🎧 {tot['musica']} só música (áudio MANTIDO)")
    print(f"   ⚠️ {tot['erro']} não deu pra ouvir (troca, na dúvida)")
    if tokens:
        usd = float(os.getenv("GEMINI_USD_POR_MTOK", "0.30"))
        brl = float(os.getenv("USD_BRL", "5.40"))
        custo = tokens / 1_000_000 * usd * brl
        print(f"   🪙 {tokens:,} tokens · R$ {custo:.2f} "
              f"(R$ {custo/max(1, n+len(trilhas)):.4f} por vídeo)")
        print(f"   📊 a 12 vídeos/dia: R$ "
              f"{custo/max(1, n+len(trilhas))*12*30:.2f}/mês")
    print(f"\n   {tot['musica']}/{n} manteriam o áudio original — é esse o "
          f"conteúdo que\n   antes a gente jogava fora sem perguntar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
