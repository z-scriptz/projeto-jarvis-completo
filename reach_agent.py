#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# reach_agent.py -- OLHOS DE ALCANCE do Jarvis. Puxa reach/views/engajamento dos
# últimos posts de CADA conta (IG Business) pela Graph API e salva em
# shared/reach.jsonl. É o que faltava: a máquina media VENDA (Shopee) mas era CEGA
# pra ALCANCE — e o alcance é o gargalo na fase de crescimento. O CEO cruza isso com
# o ledger (formato/hook) pra descobrir o que é MAIS VISTO.
#
# NÃO mexe nos uploaders — só LÊ os insights da própria conta (token que já temos).
# Uso (VPS):  cd ~/jarvis && .venv/bin/python reach_agent.py [--limite 30]
# Cron sugerido: 1x/dia (o reach amadurece em ~24-48h).
import os
import sys
import json
import time
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
CONTAS = BASE / "contas.json"
REACH = BASE / "shared" / "reach.jsonl"
GRAPH = "https://graph.facebook.com/v21.0"


def _carregar_env():
    for cand in (BASE / ".env", Path(".env")):
        if not cand.exists():
            continue
        for ln in cand.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#") or "=" not in ln:
                continue
            if ln.lower().startswith("export "):
                ln = ln[7:]
            k, _, v = ln.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        break


_carregar_env()


def _contas() -> dict:
    try:
        return json.loads(CONTAS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _token(conta: dict) -> str:
    env = conta.get("page_token_env", "")
    return (os.environ.get(env, "") if env else "").strip()


def _brl_int(n) -> str:
    try:
        return f"{int(n):,}".replace(",", ".")
    except Exception:
        return str(n)


def _insights(media_id: str, token: str) -> dict:
    """Tenta reach + views (plays). Degrada com elegância: métrica inválida p/ o tipo
    de mídia derruba a chamada, então cai pra só 'reach', depois pra nada."""
    out = {}
    for metricas in ("reach,plays", "reach", "views"):
        try:
            r = requests.get(f"{GRAPH}/{media_id}/insights",
                             params={"metric": metricas, "access_token": token},
                             timeout=25).json()
        except Exception:
            continue
        if r.get("error"):
            # sem permissão de insights → avisa uma vez lá em cima; aqui só segue
            out["_insights_erro"] = (r["error"].get("message") or "")[:120]
            continue
        for d in r.get("data", []):
            nome = d.get("name")
            val = ((d.get("values") or [{}])[0]).get("value")
            if nome == "reach":
                out["reach"] = val
            elif nome in ("plays", "views"):
                out["views"] = val
        if "reach" in out:
            break
    return out


def puxar_conta(nicho: str, conta: dict, limite: int) -> list:
    ig = str(conta.get("instagram_user_id", "")).strip()
    token = _token(conta)
    handle = conta.get("handle", nicho)
    if not (ig and token):
        print(f"  ⚠️  {handle}: sem instagram_user_id/token — pulo")
        return []
    try:
        r = requests.get(f"{GRAPH}/{ig}/media", params={
            "fields": "id,caption,timestamp,media_type,media_product_type,"
                      "permalink,like_count,comments_count",
            "limit": limite, "access_token": token}, timeout=30).json()
    except Exception as e:
        print(f"  ⚠️  {handle}: erro na Graph API: {str(e)[:80]}")
        return []
    if r.get("error"):
        print(f"  ⚠️  {handle}: {r['error'].get('message', '')[:120]}")
        return []
    itens, agora = [], int(time.time())
    for m in r.get("data", []):
        item = {
            "nicho": nicho, "handle": handle, "media_id": m.get("id"),
            "caption": (m.get("caption") or "")[:280],
            "timestamp": m.get("timestamp"),
            "tipo": m.get("media_product_type") or m.get("media_type") or "",
            "likes": m.get("like_count", 0), "comments": m.get("comments_count", 0),
            "permalink": m.get("permalink", ""), "coletado_em": agora,
        }
        item.update(_insights(m.get("id", ""), token))
        itens.append(item)
    return itens


def _salvar(itens: list):
    if not itens:
        return
    REACH.parent.mkdir(parents=True, exist_ok=True)
    with open(REACH, "a", encoding="utf-8") as f:
        for it in itens:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def main():
    argv = sys.argv[1:]
    limite = 30
    if "--limite" in argv:
        try:
            limite = int(argv[argv.index("--limite") + 1])
        except (IndexError, ValueError):
            pass
    contas = _contas()
    if not contas:
        print("❌ contas.json não encontrado/ilegível.")
        return 1
    print(f"👀 Puxando alcance dos últimos {limite} posts por conta…\n")
    total, sem_insights = [], False
    for nicho, conta in contas.items():
        if nicho.startswith("_") and nicho != "_default":
            continue
        itens = puxar_conta(nicho, conta, limite)
        total += itens
        com_reach = [i for i in itens if isinstance(i.get("reach"), int)]
        if itens and not com_reach:
            sem_insights = True
        if itens:
            reaches = [i["reach"] for i in com_reach] or [0]
            media = sum(reaches) / len(reaches) if reaches else 0
            top = max(itens, key=lambda i: i.get("reach", 0) or i.get("likes", 0))
            print(f"  📊 {conta.get('handle', nicho)}: {len(itens)} posts · "
                  f"reach médio {_brl_int(media)} · "
                  f"top {_brl_int(top.get('reach', top.get('likes', 0)))} "
                  f"(\"{(top.get('caption') or '')[:40]}…\")")
    _salvar(total)
    print(f"\n💾 {len(total)} posts salvos em {REACH.name}")
    if sem_insights:
        print("\n⚠️  Reach veio vazio — provável falta da permissão "
              "'instagram_manage_insights' no token. Likes/comentários funcionam; "
              "pra reach/views, re-autorize o token com esse escopo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
