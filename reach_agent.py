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
    """Tenta RETENÇÃO + reach + views. Degrada com elegância: métrica inválida
    p/ o tipo de mídia derruba a chamada inteira, então tenta do mais rico pro
    mais pobre e para no primeiro que responder.

    ⚠️ POR QUE A RETENÇÃO ENTROU (15/08). Medido: **9 conversões em 30 dias.**
    Divididas em dois braços de um A/B são ~4,5 cada — detectar 50% de
    diferença precisaria de ~60 eventos por braço, ou seja **~13 meses**. O
    experimento "vídeo rico × vídeo simples" medido por COMISSÃO nasce morto
    nesse volume, e tanto eu quanto o ChatGPT tínhamos proposto exatamente
    isso. A medição de potência matou o desenho antes de gastar 20 produções.

    Subir no funil não é prêmio de consolação — para ESTA pergunta a retenção
    é a métrica MELHOR. "Vídeo de uma foto só prende o espectador?" é
    respondido diretamente por tempo médio assistido; comissão fica dois
    saltos depois, cheia de ruído. E `ig_reels_avg_watch_time` vem com
    contagem na casa das centenas por post, não 9 por mês.
    """
    out = {}
    # ⚠️ `plays` FOI DEPRECIADO NA v21 — medido com o diag_retencao em 15/08:
    #     (#100) metric[0] must be one of: impressions, reach, replies, saved,
    #     likes, comments, shares, total_interactions, follows...
    # E o pedido de Insights é ATÔMICO: UM nome inválido derruba o lote
    # inteiro. Todas as combinações antigas começavam com `reach,plays,...`,
    # inclusive o fallback `reach,plays` — então o encadeamento caía até
    # `reach` sozinho e a retenção NUNCA era pedida. Ela estava disponível o
    # tempo todo (3567ms = 3,57s no post de teste).
    # Lição pra próxima depreciação: um nome morto envenena o lote todo, e é
    # por isso que os erros agora são acumulados e impressos.
    for metricas in ("reach,views,ig_reels_avg_watch_time,"
                     "ig_reels_video_view_total_time",
                     "reach,views,ig_reels_avg_watch_time",
                     "reach,views", "reach", "views"):
        try:
            r = requests.get(f"{GRAPH}/{media_id}/insights",
                             params={"metric": metricas, "access_token": token},
                             timeout=25).json()
        except Exception:
            continue
        if r.get("error"):
            # ⚠️ ACUMULA, não sobrescreve. A versão anterior fazia
            # `out["_insights_erro"] = ...` a cada tentativa: a última apagava
            # as anteriores, ninguém imprimia o campo, e a combinação pobre
            # passava. Resultado real (15/08): "nenhum post trouxe retenção"
            # sem uma palavra sobre o motivo — com os Reels certos e a
            # permissão certa. Erro engolido é o modo de falha desta casa.
            msg = (r["error"].get("message") or "")[:120]
            out.setdefault("_insights_erros", []).append(f"{metricas}: {msg}")
            continue
        for d in r.get("data", []):
            nome = d.get("name")
            val = ((d.get("values") or [{}])[0]).get("value")
            if nome == "reach":
                out["reach"] = val
            elif nome in ("plays", "views"):
                out["views"] = val
            elif nome == "ig_reels_avg_watch_time":
                # vem em MILISSEGUNDOS na Graph API — guardar em segundos
                # evita que alguém compare 3200 com 3,2 daqui a três meses
                out["retencao_s"] = (round(val / 1000.0, 2)
                                     if isinstance(val, (int, float)) else None)
            elif nome == "ig_reels_video_view_total_time":
                out["tempo_total_s"] = (round(val / 1000.0, 1)
                                        if isinstance(val, (int, float)) else None)
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
    # a retenção é o número que decide o experimento "vídeo rico × 1 foto".
    # Se ela NÃO estiver vindo, dizer isso alto — descobrir daqui a um mês que
    # o campo estava vazio o tempo todo é perder o mês.
    com_ret = [i.get("retencao_s") for i in total
               if isinstance(i.get("retencao_s"), (int, float))]
    if com_ret:
        print(f"\n  ⏱️  retenção: {len(com_ret)}/{len(total)} posts com tempo "
              f"médio assistido · média {sum(com_ret) / len(com_ret):.1f}s")
    elif total:
        print("\n  ⚠️  NENHUM post trouxe tempo médio assistido — sem ele não "
              "dá pra medir retenção (comissão não serve: 9 vendas/mês).")
        # o motivo vem da própria API, não de palpite meu
        vistos = []
        for i in total:
            for e in (i.get("_insights_erros") or []):
                if e not in vistos:
                    vistos.append(e)
        for e in vistos[:4]:
            print(f"       a API respondeu → {e}")
        if not vistos:
            print("       (a API não devolveu erro: a métrica simplesmente "
                  "não veio nos dados)")
        print("       Diagnóstico métrica a métrica:  "
              ".venv/bin/python diag_retencao.py")

    _salvar(total)
    print(f"\n💾 {len(total)} posts salvos em {REACH.name}")
    if sem_insights:
        print("\n⚠️  Reach veio vazio — provável falta da permissão "
              "'instagram_manage_insights' no token. Likes/comentários funcionam; "
              "pra reach/views, re-autorize o token com esse escopo.")
    return 0


if __name__ == "__main__":
    # TRAVA DE INSTÂNCIA ÚNICA. Em 04/08/2026 o `crontab -l` tinha esta
    # mesma linha repetida (algumas 4x, o ceo_agent 8x) e as cópias rodaram
    # juntas o dia inteiro. shared/trava.py conta a história inteira.
    # Sem a trava disponível, roda como antes — ela protege, não bloqueia.
    try:
        from shared.trava import rodar_unico
    except Exception:
        sys.exit(main())
    sys.exit(rodar_unico("reach_agent", main))
