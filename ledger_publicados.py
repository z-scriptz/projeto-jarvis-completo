#!/usr/bin/env python3
# ledger_publicados.py -- liga O QUE FOI FEITO ao QUE FOI PUBLICADO.
#
# O BURACO QUE ISTO FECHA (08/08/2026)
# ────────────────────────────────────
# O projeto tem duas metades que nunca se encontraram:
#
#   posts_ledger.jsonl   sabe o HOOK, a categoria, o produto e o slug
#   metricas_agent       sabe as VENDAS por UTM
#
# E ninguém guarda o post publicado. O log imprime e joga fora:
#
#   ✅ [instagram] publicado: https://www.instagram.com/reel/Dbx0xxYjaeF/
#
# Sem esse ID não dá pra perguntar ao Instagram como o post foi. Resultado: com
# 100+ vídeos no ar, a pergunta "qual hook funciona?" é HOJE impossível de
# responder — não por falta de IA, por falta de uma coluna.
#
# POR QUE LER O LOG EM VEZ DE MEXER NO PUBLICADOR
# Mexer em quem publica é mexer no caminho que está funcionando, e o histórico
# dos 100+ vídeos já publicados continuaria perdido de qualquer forma. O log
# tem os dois lados: a linha 📤 traz o SLUG, a linha ✅ seguinte traz o ID.
# Ler é reversível e recupera o passado. Depois que isto provar valor, aí sim
# vale gravar o ID na hora da publicação.
#
# SÓ LÊ log e ledger. Escreve UM arquivo novo, nunca altera os existentes.
#
# Uso:
#   python3 ledger_publicados.py                 # tabela no terminal
#   python3 ledger_publicados.py --salvar        # grava shared/publicados.jsonl
#   python3 ledger_publicados.py --hooks         # ranking por hook

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LEDGER = BASE_DIR / "shared" / "posts_ledger.jsonl"
SAIDA = BASE_DIR / "shared" / "publicados.jsonl"
LOGS = [BASE_DIR / "logs", BASE_DIR]

# 2026-08-08 09:06:15 [INFO] agents.publish_guard:  📤 [instagram] 'slug' — tentativa 1/3
RE_TENTA = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2}).*?\[(\w+)\]\s+'([^']+)'")
# 2026-08-08 09:06:56 [INFO] agents.publish_guard:  ✅ [instagram] publicado: <url>
RE_OK = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2}).*?\[(\w+)\]\s+publicad[oa]:\s*(\S+)")

RE_ID_IG = re.compile(r"/reel/([A-Za-z0-9_-]+)|/p/([A-Za-z0-9_-]+)")


def _logs():
    vistos = set()
    for d in LOGS:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.log")):
            if f.name in vistos:
                continue
            vistos.add(f.name)
            yield f


def extrair_publicacoes() -> list:
    """[{data, hora, plataforma, slug, url, id}] a partir dos logs.

    O pareamento é por PROXIMIDADE: a linha '✅ publicado' pega o último slug
    anunciado na MESMA plataforma. É o que a estrutura do log permite, e é
    confiável porque a publicação é sequencial — mas por isso o slug fica
    vazio quando não houver um 📤 antes, em vez de eu chutar o mais próximo
    de qualquer plataforma.
    """
    achados = []
    for f in _logs():
        try:
            linhas = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        ultimo = {}          # plataforma -> slug
        for ln in linhas:
            m = RE_TENTA.search(ln)
            if m and "publicad" not in ln:
                ultimo[m.group(3)] = m.group(4)
                continue
            m = RE_OK.search(ln)
            if not m:
                continue
            data, hora, plat, url = m.groups()
            mid = RE_ID_IG.search(url)
            # POP, não GET: o slug é CONSUMIDO ao parear. Guardando-o, um '✅
            # publicado' sem '📤' antes herdava o slug do post ANTERIOR e o
            # dataset creditava o post ao hook errado — em silêncio, e o
            # ranking sairia mentindo com cara de dado. Melhor slug vazio, que
            # aparece na contagem de "SEM par", do que slug plausível e errado.
            achados.append({
                "data": data, "hora": hora, "plataforma": plat,
                "slug": ultimo.pop(plat, ""),
                "url": url.rstrip(".,);"),
                "id": (mid.group(1) or mid.group(2)) if mid else "",
            })
    # dedup por url (o log pode ter sido rotacionado e repetido)
    unicos, vistos = [], set()
    for a in achados:
        if a["url"] in vistos:
            continue
        vistos.add(a["url"])
        unicos.append(a)
    return unicos


def carregar_ledger() -> dict:
    """slug -> registro do posts_ledger (o mais recente vence)."""
    por_slug = {}
    if not LEDGER.exists():
        return por_slug
    for ln in LEDGER.read_text(encoding="utf-8", errors="ignore").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        s = (r.get("slug") or "").strip()
        if s:
            por_slug[s] = r
    return por_slug


def juntar() -> list:
    pubs = extrair_publicacoes()
    led = carregar_ledger()
    saida = []
    for p in pubs:
        r = led.get(p["slug"], {})
        saida.append({
            **p,
            "produto": r.get("produto", ""),
            "categoria": r.get("categoria", ""),
            "hook": r.get("hook", ""),
            "link": r.get("link", ""),
            # 'casado' é a métrica de saúde da própria junção: sem ela, um dia
            # a gente olharia um ranking construído sobre metade dos dados
            # achando que era o todo.
            "casado": bool(r),
        })
    return saida


def _relatorio(dados):
    print(f"publicações encontradas no log: {len(dados)}")
    casados = [d for d in dados if d["casado"]]
    print(f"  casadas com o posts_ledger: {len(casados)}")
    print(f"  SEM par no ledger:          {len(dados) - len(casados)}")
    if not dados:
        return
    print("\npor plataforma:")
    for k, v in Counter(d["plataforma"] for d in dados).most_common():
        print(f"   {k:12} {v:4}")
    print("\npor categoria (só as casadas):")
    for k, v in Counter(d["categoria"] or "-" for d in casados).most_common():
        print(f"   {k:12} {v:4}")
    com_hook = sum(1 for d in casados if d["hook"])
    print(f"\ncom hook registrado: {com_hook} de {len(casados)}")
    print("\nas 5 mais recentes:")
    for d in sorted(dados, key=lambda x: (x["data"], x["hora"]))[-5:]:
        h = (d["hook"] or "—")[:44].replace("\n", " ")
        print(f"   {d['data']} {d['hora']}  {d['id'] or '?':14} {h}")


def _ranking_hooks(dados):
    """Agrupa por hook. AINDA SEM DESEMPENHO: este script só monta a ponte.
    O ranking de verdade precisa das métricas de cada post, que é o próximo
    passo. Aqui dá pra ver quais hooks se repetem — e se algum domina demais,
    isso por si só já é um achado."""
    por = defaultdict(list)
    for d in dados:
        if d["hook"]:
            por[d["hook"].strip()].append(d)
    print(f"hooks distintos: {len(por)}  em {sum(len(v) for v in por.values())} posts")
    print("\nos mais repetidos:")
    for hook, itens in sorted(por.items(), key=lambda kv: -len(kv[1]))[:12]:
        print(f"   {len(itens):3}x  {hook[:66]}")


def main():
    p = argparse.ArgumentParser(
        description="Liga o posts_ledger (hook) ao post publicado (ID).")
    p.add_argument("--salvar", action="store_true",
                   help=f"grava {SAIDA.name}")
    p.add_argument("--hooks", action="store_true", help="agrupa por hook")
    args = p.parse_args()

    dados = juntar()
    if args.hooks:
        _ranking_hooks(dados)
    else:
        _relatorio(dados)

    if args.salvar:
        SAIDA.parent.mkdir(parents=True, exist_ok=True)
        with open(SAIDA, "w", encoding="utf-8") as f:
            for d in dados:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        print(f"\n✅ {SAIDA}  ({len(dados)} linhas)")
        print("   próximo passo: puxar as métricas de cada 'id' no Graph API.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
