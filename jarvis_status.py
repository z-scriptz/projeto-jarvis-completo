#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# jarvis_status.py -- PAINEL DE SAÚDE da máquina TopShop. Um comando só que mostra
# o pulso inteiro de relance: coleta (inbox/fontes/funil), produção, fila, postagem
# e dinheiro. Lê SÓ arquivos locais (rápido, sem rede). Com --full cruza com a
# Shopee pra ver quais FONTES já venderam (VENDE/MORTA/NOVA).
#
# Uso (VPS):  cd ~/jarvis && .venv/bin/python jarvis_status.py [dias] [--full]
import os
import re
import sys
import json
import time
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).resolve().parent
INBOX = BASE / "inbox_tiktok"
PRONTO = BASE / "pronto_para_postar"
LEDGER = BASE / "shared" / "posts_ledger.jsonl"
NICHOS = BASE / "shared" / "nichos_quentes.json"
SAUDE = BASE / "shared" / "fontes_saude.json"
IG_ROTACAO = BASE / "shared" / "ig_rotacao.json"
HIST = BASE / "shared" / "content_plans" / "agendador_historico.json"
TIKTOK_PERFIS = BASE / "tiktok_perfis.txt"
IG_PERFIS = BASE / "instagram_perfis.txt"
ZUMBI_RUNS = int(os.environ.get("COLETA_ZUMBI_RUNS", 3))

_TTY = sys.stdout.isatty()
def _c(s, cor):
    if not _TTY:
        return s
    cores = {"v": "92", "a": "93", "r": "91", "c": "96", "d": "90", "b": "1"}
    return f"\033[{cores.get(cor, '0')}m{s}\033[0m"


def _brl(v):
    return ("R$ " + f"{float(v or 0):,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")


def _ler_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def _ler_ledger(dias):
    if not LEDGER.exists():
        return []
    corte = time.time() - dias * 86400
    out = []
    for l in LEDGER.read_text(encoding="utf-8").splitlines():
        l = l.strip()
        if not l:
            continue
        try:
            r = json.loads(l)
            if r.get("ts", 0) >= corte:
                out.append(r)
        except Exception:
            pass
    return out


def _classificar_perfis(arq):
    """(ativos, pausa_429, zumbi, ceo, manual) contando linhas do arquivo de fontes."""
    ativos = pausa = zumbi = ceo = manual = 0
    if not arq.exists():
        return ativos, pausa, zumbi, ceo, manual
    for l in arq.read_text(encoding="utf-8").splitlines():
        s = l.strip()
        if not s:
            continue
        if not s.startswith("#"):
            ativos += 1
        elif "429-PAUSA" in s:
            pausa += 1
        elif "ZUMBI-COLETA" in s:
            zumbi += 1
        elif "PODADO CEO" in s:
            ceo += 1
        else:
            manual += 1
    return ativos, pausa, zumbi, ceo, manual


def _spark(valores):
    blocos = "▁▂▃▄▅▆▇█"
    if not valores:
        return ""
    mx = max(valores) or 1
    return "".join(blocos[min(len(blocos) - 1, int(v / mx * (len(blocos) - 1)))] for v in valores)


def _linha(titulo):
    print("\n" + _c(titulo, "b"))


def main():
    argv = sys.argv[1:]
    full = "--full" in argv
    dias = 30
    for a in argv:
        if a.isdigit():
            dias = int(a); break

    print(_c("═" * 60, "d"))
    print(_c(f"  🤖 JARVIS · Painel de Saúde", "c") + _c(f"   {time.strftime('%Y-%m-%d %H:%M')}", "d"))
    print(_c("═" * 60, "d"))

    # ── COLETA ──────────────────────────────────────────────────────────────
    _linha("📥 COLETA")
    inbox_n = 0
    if INBOX.exists():
        inbox_n = sum(1 for p in INBOX.iterdir() if p.is_dir() and not p.name.startswith("_"))
    tk = _classificar_perfis(TIKTOK_PERFIS)
    ig = _classificar_perfis(IG_PERFIS)
    print(f"  Inbox (aguardando produção): {_c(inbox_n, 'b')} vídeos")
    print(f"  Fontes ativas: TikTok {_c(tk[0], 'v')} · IG {_c(ig[0], 'v')}")
    pausadas = tk[1] + ig[1]
    podadas = tk[2] + ig[2] + tk[3] + ig[3]
    if pausadas or podadas:
        print(f"  Silenciadas: {_c(pausadas, 'a')} em pausa (429) · "
              f"{_c(podadas, 'a')} podadas (zumbi/CEO)")
    rot = _ler_json(IG_ROTACAO, {})
    if ig[0] > 0:
        cap = int(os.environ.get("IG_MAX_PERFIS_RUN", 12))
        print(f"  IG rotação: offset {rot.get('offset', 0)}/{ig[0]} "
              f"({cap}/rodada → cobre todos em ~{max(1, -(-ig[0]//cap))} rodadas)")
    saude = _ler_json(SAUDE, {})
    if saude:
        acumulando = [k for k, v in saude.items() if int(v.get("zero_seguidas", 0)) >= 1]
        quase = [k for k, v in saude.items() if int(v.get("zero_seguidas", 0)) == ZUMBI_RUNS - 1]
        if acumulando:
            msg = f"  Saúde: {_c(len(acumulando), 'a')} fonte(s) sem render vídeo"
            if quase:
                msg += f" · {_c(len(quase), 'r')} a 1 rodada de podar"
            print(msg)

    # ── PRODUÇÃO ────────────────────────────────────────────────────────────
    _linha(f"🏭 PRODUÇÃO (últimos 7d)")
    led7 = _ler_ledger(7)
    por_nicho = defaultdict(int)
    por_dia_prod = defaultdict(int)
    for r in led7:
        por_nicho[(r.get("nicho") or "?").lower()] += 1
        por_dia_prod[r.get("data") or time.strftime("%Y-%m-%d", time.localtime(r.get("ts", 0)))] += 1
    print(f"  Total: {_c(len(led7), 'b')} posts produzidos")
    if por_nicho:
        print("  Por nicho: " + " · ".join(
            f"{n} {c}" for n, c in sorted(por_nicho.items(), key=lambda x: -x[1])))
    dias7 = [time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400)) for i in range(6, -1, -1)]
    serie = [por_dia_prod.get(d, 0) for d in dias7]
    print(f"  Ritmo 7d: {_c(_spark(serie), 'c')}  ({'/'.join(str(v) for v in serie)})")

    # ── FILA ────────────────────────────────────────────────────────────────
    _linha("📮 FILA (pronto_para_postar)")
    fila_conta = defaultdict(int)
    fila_n = 0
    if PRONTO.exists():
        for p in sorted(PRONTO.iterdir()):
            if not p.is_dir() or not (p / "video.mp4").exists():
                continue
            fila_n += 1
            cj = _ler_json(p / "conta.json", {})
            h = cj.get("handle") or cj.get("nicho") or "?"
            fila_conta[h] += 1
    print(f"  Prontos p/ postar: {_c(fila_n, 'b')}")
    if fila_conta:
        print("  Por conta: " + " · ".join(
            f"{h} {c}" for h, c in sorted(fila_conta.items(), key=lambda x: -x[1])))

    # ── POSTAGEM ────────────────────────────────────────────────────────────
    _linha("📤 POSTAGEM (últimos 7d)")
    hist = _ler_json(HIST, {})
    pordia = hist.get("por_dia", {})

    # ⚠️ CONTAR VÍDEOS, NÃO HORÁRIOS — o mesmo bug que a `auditoria_postagem`
    # corrigiu em 11/08 e que sobreviveu aqui por mais uma semana. O histórico
    # guarda `por_dia[dia][HORARIO] = slug` (modo clássico) ou `= [slug, ...]`
    # (modo `post_por_conta`, LIGADO na VPS), então `len(pordia[d])` conta as
    # CHAVES = os slots usados, não os vídeos que saíram.
    #
    # Medido em 17/08, lado a lado na mesma máquina:
    #     jarvis_status        "10 posts publicados"   ← slots
    #     auditoria_postagem   "últimos 7d: 39"        ← vídeos
    # O Dre olhou o painel achando que a postagem tinha desabado pra 10/semana.
    # Um slot com 4 contas vale 4 vídeos e este painel contava 1.
    def _videos_no_dia(slots):
        return sum(len(v) if isinstance(v, list) else 1
                   for v in (slots or {}).values())

    seriep = [_videos_no_dia(pordia.get(d, {})) for d in dias7]
    total_post7 = sum(seriep)
    print(f"  Total: {_c(total_post7, 'b')} posts publicados · "
          f"{_c(len(hist.get('postados', [])), 'd')} no histórico")
    print(f"  Ritmo 7d: {_c(_spark(seriep), 'c')}  ({'/'.join(str(v) for v in seriep)})")
    if fila_n > 0 and total_post7 == 0:
        print(_c("  ⚠️  fila cheia mas 0 postado em 7d — checar o daemon!", "r"))

    # ── DINHEIRO ────────────────────────────────────────────────────────────
    _linha(f"💰 DINHEIRO (métricas em cache)")
    nq = _ler_json(NICHOS, {})
    if nq:
        com = nq.get("comissao_video", 0)
        cats = nq.get("por_categoria", [])[:4]
        gerado = nq.get("gerado_em")
        idade = ""
        if gerado:
            h = (time.time() - gerado) / 3600
            idade = f" (atualizado há {int(h)}h)" if h >= 1 else " (recente)"
        print(f"  Comissão vídeo: {_c(_brl(com), 'v')}{_c(idade, 'd')}")
        if cats:
            print("  Top categorias: " + " · ".join(
                f"{c.get('categoria')} {_brl(c.get('comissao', 0))}" for c in cats if c.get("comissao")))
    else:
        print(_c("  (sem nichos_quentes.json ainda — rode metricas_agent)", "d"))

    # ── FONTES (funil) ──────────────────────────────────────────────────────
    _linha("🔎 FONTES (funil descoberta→coleta→venda)")
    led = _ler_ledger(dias)
    posts_fonte = defaultdict(int)
    for r in led:
        pf = (r.get("perfil_fonte") or "").strip().lower()
        if pf:
            posts_fonte[pf] += 1
    if not posts_fonte:
        print(_c("  Ainda sem posts etiquetados por fonte (produção nova preenche). "
                 "Em algumas semanas cada fonte aparece aqui.", "d"))
    elif full:
        try:
            import ceo_agent as C
            fontes = C._analisar_fontes(dias)
            vende = [f for f in fontes if f["veredito"] == "VENDE"]
            morta = [f for f in fontes if f["veredito"] == "MORTA"]
            nova = [f for f in fontes if f["veredito"] == "NOVA"]
            print(f"  {_c(len(vende), 'v')} VENDE · {_c(len(morta), 'r')} MORTA · "
                  f"{_c(len(nova), 'a')} NOVA (de {len(fontes)} com posts)")
            for f in vende[:6]:
                print(f"    {_c('✅', 'v')} @{f['fonte']} ({f['nicho']}): "
                      f"{f['posts']}p · {f['vendas']}v · {_brl(f['comissao'])}")
            if morta:
                print(_c(f"    💀 podar: " + ", ".join('@' + f['fonte'] for f in morta[:8]), "r"))
        except Exception as e:
            print(_c(f"  (--full falhou ao cruzar com a Shopee: {str(e)[:60]})", "d"))
    else:
        top = sorted(posts_fonte.items(), key=lambda x: -x[1])[:8]
        print(f"  {len(posts_fonte)} fontes produzindo (top por volume; --full cruza c/ venda):")
        print("    " + " · ".join(f"@{k} {v}" for k, v in top))

    print(_c("\n" + "═" * 60, "d"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
