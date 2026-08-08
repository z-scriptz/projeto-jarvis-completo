#!/usr/bin/env python3
# metricas_posts.py -- ETAPA 2 da medição: como cada post FOI.
#
# O QUE FECHA
# ───────────
# A etapa 1 (ledger_publicados) ligou o HOOK ao POST publicado: 523 publicações,
# 499 casadas. Falta a outra ponta — o desempenho. Sem ela, "qual hook funciona"
# continua sem resposta.
#
# O PROBLEMA DO ID
# O log dá a URL do reel, e dela sai o SHORTCODE (Dbx1Pu9DbM1). O Graph API não
# aceita shortcode: ele quer o media_id numérico. Não existe conversão offline
# — é preciso LISTAR a mídia da conta e casar pelo permalink. Por isso este
# script busca as mídias antes de pedir insight de qualquer coisa.
#
# CUSTO DE API, que neste projeto já mordeu
# Uma chamada de listagem por conta (paginada) + UMA por post. Com 4 contas e
# 200 posts do IG dá ~210 chamadas por execução — muito acima da passada de 5
# minutos do auto_resposta. Por isso: rodar 1x por dia no máximo, e o que já foi
# medido não é medido de novo (--refazer força).
#
# HONESTIDADE DO DADO
# Post com menos de 24h ainda está juntando alcance. Medir e guardar como se
# fosse final envenena a média — então posts recentes são PULADOS por padrão
# (--horas-min). É o mesmo motivo de a vitrine mostrar média de preço em vez do
# preço do dia.
#
# Uso (VPS):
#   .venv/bin/python metricas_posts.py --teste     # não chama API, mostra o plano
#   .venv/bin/python metricas_posts.py             # coleta e grava
#   .venv/bin/python metricas_posts.py --ranking   # o que os números dizem

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

GRAPH = "https://graph.facebook.com/v21.0"
CONTAS = BASE_DIR / "contas.json"
SAIDA = BASE_DIR / "shared" / "metricas_posts.jsonl"

# Preferidas primeiro; se o Graph recusar alguma (mudam de nome entre versões),
# o script tenta de novo com a lista curta em vez de desistir do post.
METRICAS = ["reach", "likes", "comments", "shares", "saved", "total_interactions"]
METRICAS_MIN = ["reach", "likes", "comments"]


def _log(m):
    print(f"[metricas] {m}", flush=True)


def _carregar_env():
    for cand in (BASE_DIR / ".env", Path(".env")):
        if not cand.exists():
            continue
        for linha in cand.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            k, _, v = linha.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        break


_carregar_env()


def _token(conta):
    env = conta.get("page_token_env", "")
    return ((os.environ.get(env, "") if env else "").strip()
            or os.environ.get("FACEBOOK_PAGE_TOKEN", "").strip()
            or os.environ.get("META_ACCESS_TOKEN", "").strip())


def _get(url, params):
    import requests
    try:
        r = requests.get(url, params=params, timeout=40)
        return r.json() or {}
    except Exception as e:
        return {"error": {"message": f"exceção: {str(e)[:90]}"}}


def _shortcode(url_ou_perma: str) -> str:
    """O trecho entre /reel/ ou /p/ e a próxima barra."""
    t = (url_ou_perma or "").rstrip("/")
    for marca in ("/reel/", "/p/", "/tv/"):
        if marca in t:
            return t.split(marca, 1)[1].split("/", 1)[0].split("?", 1)[0]
    return ""


def mapa_midias(conta, token, paginas=12) -> dict:
    """{shortcode: media_id} da conta. Pagina até acabar ou bater o teto.

    O teto existe porque conta antiga tem centenas de mídias e a gente só
    precisa das que estão no nosso ledger — mas parar cedo demais perderia
    posts antigos, então 12 páginas (~1200 mídias) cobre com folga.
    """
    ig = str(conta.get("instagram_user_id", "")).strip()
    if not ig:
        return {}
    mapa, url = {}, f"{GRAPH}/{ig}/media"
    params = {"fields": "id,permalink,timestamp", "limit": 100,
              "access_token": token}
    for _ in range(paginas):
        r = _get(url, params)
        if r.get("error"):
            _log(f"   ⚠️ listagem falhou: {r['error'].get('message','')[:90]}")
            break
        for m in r.get("data", []):
            sc = _shortcode(m.get("permalink", ""))
            if sc:
                mapa[sc] = m.get("id")
        prox = (r.get("paging") or {}).get("next")
        if not prox:
            break
        url, params = prox, {}
    return mapa


def insights(media_id, token) -> dict:
    """Métricas do post. {} quando o Graph recusa até a lista mínima."""
    for lista in (METRICAS, METRICAS_MIN):
        r = _get(f"{GRAPH}/{media_id}/insights",
                 {"metric": ",".join(lista), "access_token": token})
        if r.get("error"):
            continue
        fora = {}
        for it in r.get("data", []):
            vals = it.get("values") or [{}]
            fora[it.get("name")] = vals[0].get("value", 0)
        if fora:
            return fora
    return {}


def _ja_medidos() -> set:
    if not SAIDA.exists():
        return set()
    ids = set()
    for ln in SAIDA.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            ids.add(json.loads(ln).get("shortcode", ""))
        except Exception:
            pass
    return {i for i in ids if i}


def coletar(horas_min=24, refazer=False, teste=False, limite=0):
    from ledger_publicados import juntar
    try:
        from shared.categorias import normalizar
    except Exception:
        def normalizar(c):
            return (c or "").split("_")[0].lower()

    posts = [p for p in juntar()
             if p["plataforma"] == "instagram" and p.get("id")]
    _log(f"{len(posts)} post(s) do Instagram no ledger")

    ja = set() if refazer else _ja_medidos()
    corte = time.time() - horas_min * 3600
    fila = []
    recentes = 0
    for p in posts:
        if p["id"] in ja:
            continue
        try:
            t = time.mktime(time.strptime(f"{p['data']} {p['hora']}",
                                          "%Y-%m-%d %H:%M:%S"))
        except Exception:
            t = 0
        if t and t > corte:
            recentes += 1          # ainda juntando alcance — não mede
            continue
        fila.append(p)
    if limite:
        fila = fila[:limite]

    _log(f"   já medidos: {len(ja)}  ·  recentes demais (<{horas_min}h): "
         f"{recentes}  ·  a medir agora: {len(fila)}")
    if teste:
        _log("--teste: nenhuma chamada de API foi feita.")
        for p in fila[:8]:
            _log(f"      {p['data']} {p['id']:14} {(p['hook'] or '—')[:44]}")
        return 0
    if not fila:
        _log("nada novo a medir ✔")
        return 0

    contas = json.loads(CONTAS.read_text(encoding="utf-8"))
    mapas, tokens = {}, {}
    for chave, conta in contas.items():
        tk = _token(conta)
        if not tk:
            continue
        m = mapa_midias(conta, tk)
        _log(f"   {conta.get('handle', chave)}: {len(m)} mídia(s) listada(s)")
        mapas[chave] = m
        tokens[chave] = tk

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    gravados = semid = semdado = 0
    with open(SAIDA, "a", encoding="utf-8") as f:
        for p in fila:
            sc = p["id"]
            media_id = tk = None
            for chave, m in mapas.items():
                if sc in m:
                    media_id, tk = m[sc], tokens[chave]
                    break
            if not media_id:
                semid += 1
                continue
            dados = insights(media_id, tk)
            if not dados:
                semdado += 1
                continue
            f.write(json.dumps({
                "shortcode": sc, "media_id": media_id,
                "data": p["data"], "hora": p["hora"],
                "hook": p["hook"], "produto": p["produto"],
                "categoria": p["categoria"],
                "nicho": normalizar(p["categoria"]),
                "url": p["url"], **dados,
                "medido_em": int(time.time()),
            }, ensure_ascii=False) + "\n")
            gravados += 1
            time.sleep(0.4)        # respiro entre chamadas

    _log(f"✅ {gravados} gravado(s) · {semid} sem media_id · {semdado} sem insight")
    if semid:
        _log("   (sem media_id = post de conta cujo token não está no .env, "
             "ou mídia fora das páginas listadas)")
    return 0


def ranking(minimo=3):
    """O que os números dizem, agrupado por hook e por nicho.

    `minimo` existe porque média de 1 post não é média — é anedota com casas
    decimais. Hook com menos que isso fica fora do ranking, e o total de
    ignorados é impresso pra ninguém achar que viu tudo.
    """
    if not SAIDA.exists():
        _log("ainda não há medições. Rode sem --ranking primeiro.")
        return 1
    linhas = []
    for ln in SAIDA.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            linhas.append(json.loads(ln))
        except Exception:
            pass
    if not linhas:
        _log("arquivo vazio.")
        return 1
    _log(f"{len(linhas)} post(s) medido(s)\n")

    def _mostra(titulo, chave):
        grupos = defaultdict(list)
        for r in linhas:
            k = (r.get(chave) or "").strip()
            if k:
                grupos[k].append(r)
        print(f"── {titulo} ──")
        fora = [(k, v) for k, v in grupos.items() if len(v) >= minimo]
        ignorados = len(grupos) - len(fora)
        def _med(v, campo):
            n = [r.get(campo, 0) or 0 for r in v]
            return sum(n) / len(n) if n else 0
        for k, v in sorted(fora, key=lambda kv: -_med(kv[1], "reach"))[:12]:
            # hook de 2 linhas quebraria a tabela; a quebra vira ' / '
            rotulo = " / ".join(x.strip() for x in k.splitlines() if x.strip())
            print(f"   alcance {_med(v,'reach'):8.0f} · curtidas {_med(v,'likes'):6.0f}"
                  f" · {len(v):3} post(s)   {rotulo[:56]}")
        if ignorados:
            print(f"   ({ignorados} grupo(s) com menos de {minimo} posts, fora do ranking)")
        print()

    _mostra("POR NICHO", "nicho")
    _mostra("POR HOOK", "hook")
    return 0


def main():
    p = argparse.ArgumentParser(description="Mede como cada post publicado foi.")
    p.add_argument("--teste", action="store_true", help="mostra o plano, sem API")
    p.add_argument("--ranking", action="store_true", help="lê o que já foi medido")
    p.add_argument("--refazer", action="store_true", help="remede o que já tem")
    p.add_argument("--horas-min", type=int, default=24,
                   help="idade mínima do post pra medir (padrão 24h)")
    p.add_argument("--limite", type=int, default=0, help="mede só os N primeiros")
    p.add_argument("--minimo", type=int, default=3,
                   help="posts mínimos por grupo no ranking")
    args = p.parse_args()

    if args.ranking:
        return ranking(args.minimo)
    try:
        import requests  # noqa: F401
    except Exception:
        _log("requests não instalado — use .venv/bin/python")
        return 2
    return coletar(args.horas_min, args.refazer, args.teste, args.limite)


if __name__ == "__main__":
    try:
        from shared.trava import rodar_unico
    except Exception:
        sys.exit(main())
    sys.exit(rodar_unico("metricas_posts", main))
