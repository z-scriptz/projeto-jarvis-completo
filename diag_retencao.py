#!/usr/bin/env python3
# diag_retencao.py -- por que a retenção não vem? Pergunta à API, uma métrica
# por vez, e imprime a resposta DELA.
#
# POR QUE EXISTE (15/08)
# Medido: 9 conversões em 30 dias — o A/B por comissão precisaria de ~13 meses.
# A métrica viável é RETENÇÃO (tempo médio assistido), que tem contagem na casa
# das centenas por post. Só que ela não veio.
#
# As duas explicações óbvias já caíram, medidas:
#   · falta de permissão?  NÃO — o `reach` chegou (207/264/561/128). Sem
#     `instagram_manage_insights` o reach também viria vazio.
#   · não são Reels?       NÃO — `2041 REELS` no reach.jsonl, zero de outro tipo.
#
# Sobra a chamada. E aí está o defeito, que é meu: o `_insights` tenta
# combinações da mais rica pra mais pobre e, ao receber erro, faz
# `out["_insights_erro"] = ...` seguido de `continue`. O campo é sobrescrito
# pela tentativa seguinte, ninguém o imprime, e a combinação pobre passa. O
# resultado é "nenhum post trouxe retenção" sem UMA palavra sobre o motivo.
#
# ⚠️ ESTE ARQUIVO NÃO CHUTA NOME DE MÉTRICA. A Meta deprecia e renomeia métrica
# de Insights com frequência, e adivinhar aqui seria repetir o erro do campo
# `texto` que eu inventei no fila_qualidade. Ele pede UMA métrica por vez e
# mostra a mensagem literal da API — quem responde qual nome vale hoje é ela.
#
# Não escreve nada. Uma chamada por métrica, num único post.
#
# Uso (na VPS):  .venv/bin/python diag_retencao.py

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
# ⚠️ A VERSÃO DA API TEM QUE SER A MESMA DA PRODUÇÃO. Métrica de Insights é
# depreciada POR VERSÃO — sondar em v23 e concluir sobre um reach_agent que
# chama v21 responderia a pergunta de outro sistema. Lida do próprio
# reach_agent mais abaixo; este valor é só o fallback se o import falhar.
GRAPH = "https://graph.facebook.com/v21.0"

# candidatas conhecidas para tempo assistido + as básicas de controle.
# As de controle importam: se `reach` também falhar neste post, o problema não
# é o nome da métrica, é o post ou o token.
CANDIDATAS = [
    ("reach", "controle — se esta falhar, o problema não é o nome"),
    ("views", "controle novo (substituiu `plays` em versões recentes)"),
    ("plays", "controle antigo"),
    ("ig_reels_avg_watch_time", "tempo MÉDIO assistido — a que queremos"),
    ("ig_reels_video_view_total_time", "tempo TOTAL assistido"),
    ("saved", "salvamentos — proxy de interesse, alta contagem"),
    ("shares", "compartilhamentos"),
    ("total_interactions", "interações totais"),
]


def _log(m):
    print(f"[retencao] {m}", flush=True)


def main():
    try:
        import requests
    except Exception:
        raise SystemExit("[retencao] requests indisponível — use o .venv")

    # reaproveita o carregamento do reach_agent: duas ideias de "qual é o
    # token da conta" é o mesmo que nenhuma
    sys.path.insert(0, str(BASE))
    try:
        import reach_agent as RA
    except Exception as e:
        raise SystemExit(f"[retencao] não importei o reach_agent: {str(e)[:90]}")

    global GRAPH
    GRAPH = getattr(RA, "GRAPH", GRAPH)      # a MESMA versão que a produção usa
    _log(f"API: {GRAPH.rsplit('/', 1)[-1]} (a mesma do reach_agent)")

    contas = RA._contas()
    alvo = None
    for nicho, conta in (contas or {}).items():
        if nicho.startswith("_") and nicho != "_default":
            continue
        ig = str(conta.get("instagram_user_id", "")).strip()
        tok = RA._token(conta)
        if ig and tok:
            alvo = (nicho, conta, ig, tok)
            break
    if not alvo:
        raise SystemExit("[retencao] nenhuma conta com instagram_user_id + token")

    nicho, conta, ig, token = alvo
    handle = conta.get("handle", nicho)
    _log(f"conta de teste: {handle}")

    r = requests.get(f"{GRAPH}/{ig}/media",
                     params={"fields": "id,media_product_type,timestamp,permalink",
                             "limit": 5, "access_token": token},
                     timeout=30).json()
    if r.get("error"):
        raise SystemExit(f"[retencao] não listei as mídias: "
                         f"{r['error'].get('message', '')[:160]}")
    midias = [m for m in r.get("data", [])
              if (m.get("media_product_type") or "") == "REELS"]
    if not midias:
        raise SystemExit("[retencao] nenhum REELS nos últimos posts desta conta")

    m = midias[0]
    _log(f"post de teste: {m['id']} · {m.get('timestamp', '')[:10]} · "
         f"{m.get('media_product_type')}")
    print()

    validas, invalidas = [], []
    for metrica, porque in CANDIDATAS:
        resp = requests.get(f"{GRAPH}/{m['id']}/insights",
                            params={"metric": metrica, "access_token": token},
                            timeout=25).json()
        if resp.get("error"):
            msg = (resp["error"].get("message") or "")[:150]
            invalidas.append((metrica, msg))
            print(f"  ❌ {metrica:32} {msg}")
        else:
            val = None
            for d in resp.get("data", []):
                val = ((d.get("values") or [{}])[0]).get("value")
            validas.append((metrica, val))
            print(f"  ✅ {metrica:32} = {val}    ({porque})")

    print()
    tempo = [m_ for m_, _ in validas if "watch_time" in m_ or "view_total" in m_]
    if tempo:
        _log(f"MÉTRICA DE TEMPO DISPONÍVEL: {', '.join(tempo)}")
        _log("   → é com esta que o A/B de formato se mede. Ajuste a lista do "
             "`_insights` no reach_agent para pedir exatamente este nome.")
    else:
        _log("NENHUMA métrica de tempo assistido respondeu neste post.")
        _log("   Leia as mensagens acima: elas dizem se o nome foi depreciado, "
             "se falta permissão, ou se a métrica não vale pra este post.")
        proxies = [m_ for m_, _ in validas
                   if m_ in ("saved", "shares", "total_interactions", "views")]
        if proxies:
            _log(f"   Disponíveis como proxy de interesse: {', '.join(proxies)}")
            _log("   ⚠️ proxy NÃO é retenção: mede se gostou, não se assistiu "
                 "até o fim. Serve pra ordenar, não pra responder 'uma foto "
                 "só prende?'")
    return 0 if validas else 1


if __name__ == "__main__":
    sys.exit(main())
