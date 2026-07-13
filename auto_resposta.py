#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# auto_resposta.py -- fecha o loop do engajamento: varre os posts RECENTES das
# contas (IG + FB, via Graph API), acha comentários com o GATILHO ("eu quero",
# "quanto", "link"...) e RESPONDE na hora — no FB com o LINK clicável do produto,
# no IG mandando pra BIO (no IG link em comentário não clica). Best-effort: se
# faltar permissão ou der erro, loga e segue. Nada trava.
#
# Descobre os posts sozinho (não depende de nada gravado) — funciona pra qualquer
# post, inclusive os do hunter. Usa o MESMO contas.json do roteador (3 contas).
#
# Uso (VPS):  cd ~/jarvis && .venv/bin/python auto_resposta.py            (responde)
#             .venv/bin/python auto_resposta.py --teste                   (dry-run)
# Liga com:   echo 'AUTO_RESPONDER=1' >> ~/jarvis/.env   (senão fica dormente)
import os
import re
import sys
import json
import time
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
GRAPH = "https://graph.facebook.com/v21.0"
STORE_DIR = BASE_DIR / "shared" / "engajamento"
RESPONDIDOS = STORE_DIR / "respondidos.json"


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

try:
    import requests
    _REQ_OK = True
except Exception:
    _REQ_OK = False


def _log(m):
    print(f"[auto_resposta] {m}")


def _ligado() -> bool:
    return os.environ.get("AUTO_RESPONDER", "0").strip().lower() in ("1", "true", "sim")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "")).encode("ascii", "ignore").decode()
    return s.lower().strip()


# gatilhos: default pensado pra isca "comenta EU QUERO" + perguntas de compra
_GATILHOS_DEFAULT = ("eu quero,quero,quanto custa,quanto,qual valor,valor,preco,"
                     "link,onde compro,onde compro,como compro,como comprar,me manda,"
                     "quero um,quero comprar,interesse,tenho interesse")


def _gatilhos() -> list:
    raw = os.environ.get("AUTO_RESP_GATILHOS", _GATILHOS_DEFAULT)
    return [g for g in (_norm(x) for x in raw.split(",")) if g]


def _bateu(texto: str, gatilhos: list) -> bool:
    t = _norm(texto)
    if not t:
        return False
    return any(g in t for g in gatilhos)


def _carregar_respondidos() -> dict:
    try:
        d = json.loads(RESPONDIDOS.read_text(encoding="utf-8"))
        corte = time.time() - 7 * 86400        # TTL 7 dias (limpa o histórico velho)
        return {k: v for k, v in d.items() if isinstance(v, (int, float)) and v >= corte}
    except Exception:
        return {}


def _salvar_respondidos(d: dict) -> None:
    try:
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        RESPONDIDOS.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _token_da_conta(conta: dict) -> str:
    """Resolve o token pelo page_token_env (contas.json); fallback global."""
    env = conta.get("page_token_env", "")
    return (os.environ.get(env, "") if env else "").strip() \
        or os.environ.get("FACEBOOK_PAGE_TOKEN", "").strip() \
        or os.environ.get("META_ACCESS_TOKEN", "").strip()


def _get(url, params):
    try:
        r = requests.get(url, params=params, timeout=30)
        return r.json() or {}
    except Exception as e:
        _log(f"   ⚠️ GET falhou: {str(e)[:80]}")
        return {}


def _post(url, data):
    try:
        r = requests.post(url, data=data, timeout=30)
        return r.json() or {}
    except Exception as e:
        return {"error": {"message": f"exceção: {str(e)[:80]}"}}


_URL_RE = re.compile(r"https?://\S+")


def _extrai_link(texto: str) -> str:
    m = _URL_RE.search(texto or "")
    return m.group(0) if m else ""


# ── INSTAGRAM ──────────────────────────────────────────────────────────────
def _resp_instagram(conta, token, gatilhos, respondidos, limites, teste) -> int:
    ig = str(conta.get("instagram_user_id", "")).strip()
    if not ig:
        return 0
    handle = _norm(conta.get("handle", "")).lstrip("@")
    tmpl = os.environ.get("AUTO_RESP_IG_TMPL",
                          "😍 aee! o link tá na BIO, corre pegar o seu 👉💨")
    corte = time.time() - limites["horas"] * 3600
    feitos = 0

    midia = _get(f"{GRAPH}/{ig}/media",
                 {"fields": "id,timestamp", "limit": limites["midias"],
                  "access_token": token}).get("data", [])
    for m in midia:
        if feitos >= limites["max"]:
            break
        cmts = _get(f"{GRAPH}/{m.get('id')}/comments",
                    {"fields": "id,text,username,timestamp", "limit": 50,
                     "access_token": token}).get("data", [])
        for c in cmts:
            cid = str(c.get("id", ""))
            if not cid or cid in respondidos:
                continue
            if _norm(c.get("username", "")).lstrip("@") == handle:   # não responde a si mesmo
                continue
            if not _bateu(c.get("text", ""), gatilhos):
                continue
            if teste:
                _log(f"   [DRY] IG responderia @{c.get('username')} → {tmpl}")
                respondidos[cid] = int(time.time()); feitos += 1
                if feitos >= limites["max"]:
                    break
                continue
            r = _post(f"{GRAPH}/{cid}/replies", {"message": tmpl, "access_token": token})
            if r.get("id"):
                _log(f"   💬 IG respondeu @{c.get('username')} ({conta.get('handle')})")
                respondidos[cid] = int(time.time()); feitos += 1
            else:
                err = (r.get("error") or {}).get("message") or str(r)[:120]
                _log(f"   ⚠️ IG não respondeu ({err})")
                if "permission" in err.lower() or "#200" in err or "#10" in err:
                    return feitos   # sem escopo: nem tenta os próximos
            if feitos >= limites["max"]:
                break
    return feitos


# ── FACEBOOK ───────────────────────────────────────────────────────────────
def _resp_facebook(conta, token, gatilhos, respondidos, limites, teste) -> int:
    page = str(conta.get("facebook_page_id", "")).strip()
    if not page:
        return 0
    site = os.environ.get("AUTO_RESP_SITE", "topshopoficial.com.br")
    tmpl = os.environ.get("AUTO_RESP_FB_TMPL",
                          "😍 aqui ó: {link} — aproveita que a oferta some rápido!")
    feitos = 0

    videos = _get(f"{GRAPH}/{page}/videos",
                  {"fields": "id", "limit": limites["midias"],
                   "access_token": token}).get("data", [])
    for v in videos:
        if feitos >= limites["max"]:
            break
        cmts = _get(f"{GRAPH}/{v.get('id')}/comments",
                    {"fields": "id,message,from", "limit": 50,
                     "access_token": token}).get("data", [])
        # 1) descobre o LINK do produto a partir do NOSSO 1º comentário (tem o link)
        link = ""
        for c in cmts:
            if str((c.get("from") or {}).get("id", "")) == page:
                link = _extrai_link(c.get("message", "")) or link
        link = link or site
        # 2) responde os comentários de gatilho (que não são nossos)
        for c in cmts:
            cid = str(c.get("id", ""))
            if not cid or cid in respondidos:
                continue
            if str((c.get("from") or {}).get("id", "")) == page:      # não responde a si mesmo
                continue
            if not _bateu(c.get("message", ""), gatilhos):
                continue
            msg = tmpl.format(link=link)
            if teste:
                _log(f"   [DRY] FB responderia {(c.get('from') or {}).get('name')} → {msg}")
                respondidos[cid] = int(time.time()); feitos += 1
                if feitos >= limites["max"]:
                    break
                continue
            r = _post(f"{GRAPH}/{cid}/comments", {"message": msg, "access_token": token})
            if r.get("id"):
                _log(f"   💬 FB respondeu ({conta.get('handle') or page})")
                respondidos[cid] = int(time.time()); feitos += 1
            else:
                err = (r.get("error") or {}).get("message") or str(r)[:120]
                _log(f"   ⚠️ FB não respondeu ({err})")
                if "permission" in err.lower() or "#200" in err or "#10" in err:
                    return feitos
            if feitos >= limites["max"]:
                break
    return feitos


def main():
    teste = "--teste" in sys.argv or "--dry" in sys.argv
    if not _REQ_OK:
        _log("❌ 'requests' não instalado."); return 1
    if not _ligado() and not teste:
        _log("⚪ AUTO_RESPONDER desligado (rode com --teste pra simular, ou "
             "'echo AUTO_RESPONDER=1 >> .env' pra ligar).")
        return 0

    try:
        import roteador_contas as RC
        contas = RC.carregar_contas()
    except Exception as e:
        _log(f"❌ não carreguei contas.json: {e}"); return 1

    gatilhos = _gatilhos()
    respondidos = _carregar_respondidos()
    limites = {
        "horas": int(float(os.environ.get("AUTO_RESP_HORAS", "48"))),
        "midias": int(float(os.environ.get("AUTO_RESP_MIDIAS", "8"))),
        "max": int(float(os.environ.get("AUTO_RESP_MAX", "40"))),
    }
    _log(f"{'DRY-RUN' if teste else 'ATIVO'} · {len(contas)} conta(s) · "
         f"gatilhos: {len(gatilhos)} · janela {limites['horas']}h")

    total = 0
    for chave, conta in contas.items():
        token = _token_da_conta(conta)
        if not token:
            _log(f"   ⏭️  {conta.get('handle', chave)}: sem token ({conta.get('page_token_env')}) — pulo")
            continue
        rest = {**limites, "max": max(0, limites["max"] - total)}
        if rest["max"] <= 0:
            break
        total += _resp_instagram(conta, token, gatilhos, respondidos, rest, teste)
        rest = {**limites, "max": max(0, limites["max"] - total)}
        if rest["max"] <= 0:
            break
        total += _resp_facebook(conta, token, gatilhos, respondidos, rest, teste)

    if not teste:
        _salvar_respondidos(respondidos)
    _log(f"✅ {'simularia' if teste else 'respondi'} {total} comentário(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
