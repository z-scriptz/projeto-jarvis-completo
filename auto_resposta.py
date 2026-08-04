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
import random
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


# ── Respostas IG: 3 estilos que rodam pra todo post/reel ───────────────────
_IG_TMPLS_DEFAULT = (
    "Feito! Verifique suas dms! 😍 ou clique no link da bio.|||"
    "Te mandei no direct 🥰|||"
    "Corre que o link tá na bio 🚀 depois me fala o que achou! 👀")
# frase segura (não promete DM) — usada quando o DM está desligado
_IG_TMPL_SEM_DM = "Corre que o link tá na bio 🚀 depois me fala o que achou! 👀"


def _ig_tmpls() -> list:
    raw = os.environ.get("AUTO_RESP_IG_TMPLS", _IG_TMPLS_DEFAULT)
    return [t.strip() for t in raw.split("|||") if t.strip()]


def _menciona_dm(t: str) -> bool:
    n = _norm(t)
    return "dm" in n or "direct" in n


def _escolhe_ig_tmpl(dm_ok: bool) -> str:
    """Sorteia 1 dos 3 estilos. Sem DM confirmado, só usa os que NÃO prometem
    direct (pra nunca mentir 'te mandei no direct' sem ter mandado)."""
    tmpls = _ig_tmpls()
    if not dm_ok:
        tmpls = [t for t in tmpls if not _menciona_dm(t)] or [_IG_TMPL_SEM_DM]
    return random.choice(tmpls)


def _dm_ligado() -> bool:
    return os.environ.get("AUTO_RESP_DM", "0").strip().lower() in ("1", "true", "sim")


def _enviar_dm_ig(ig: str, comment_id: str, token: str) -> bool:
    """DM (private reply) em resposta a um comentário. No direct o link CLICA.
    Precisa do escopo instagram_manage_messages. Best-effort."""
    site = os.environ.get("AUTO_RESP_SITE", "topshopoficial.com.br")
    msg = os.environ.get(
        "AUTO_RESP_DM_TMPL",
        "Oiee! 😍 tá tudo aqui ó: {site} 💛 corre que as ofertas somem rápido!"
    ).format(site=site)
    r = _post(f"{GRAPH}/{ig}/messages", {
        "recipient": json.dumps({"comment_id": comment_id}),
        "message": json.dumps({"text": msg}),
        "access_token": token,
    })
    if r.get("message_id") or r.get("recipient_id") or r.get("id"):
        return True
    err = (r.get("error") or {}).get("message") or ""
    if err:
        _log(f"   ⚠️ DM IG falhou ({err[:100]})")
    return False


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
def _velho_demais(carimbo: str, horas: int) -> bool:
    """O post é mais antigo que a janela?

    O AUTO_RESP_HORAS existia desde sempre, aparecia no log como "janela 48h" —
    e NUNCA era usado pra filtrar nada. Quem limitava de fato era o
    AUTO_RESP_MIDIAS (os N posts mais recentes). O log dizia uma coisa que o
    código não cumpria.

    Sem carimbo (o Facebook nem pedia created_time) devolve False: na dúvida
    olha o post, porque deixar de responder um comentário custa mais que uma
    chamada a mais.
    """
    if not carimbo or horas <= 0:
        return False
    try:
        t = carimbo.strip().replace("Z", "+0000")
        # ISO do Graph: 2026-08-03T12:34:56+0000
        from datetime import datetime
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
            try:
                dt = datetime.strptime(t, fmt)
                break
            except ValueError:
                continue
        else:
            return False
        idade_h = (time.time() - dt.timestamp()) / 3600.0
        return idade_h > horas
    except Exception:
        return False


def _resp_instagram(conta, token, gatilhos, respondidos, limites, teste) -> int:
    ig = str(conta.get("instagram_user_id", "")).strip()
    if not ig:
        return 0
    handle = _norm(conta.get("handle", "")).lstrip("@")
    feitos = 0

    # SÓ comentários de cima (top-level). O /media/comments do IG já devolve os
    # parents; a gente NÃO desce em .replies, então nunca responde subcomentário.
    midia = _get(f"{GRAPH}/{ig}/media",
                 {"fields": "id,timestamp", "limit": limites["midias"],
                  "access_token": token}).get("data", [])
    for m in midia:
        if feitos >= limites["max"]:
            break
        if _velho_demais(m.get("timestamp", ""), limites["horas"]):
            continue          # fora da janela: nem pede os comentários
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

            # 1) DM (private reply) com o link clicável — se ligado e com escopo
            dm_ok = True if teste and _dm_ligado() else \
                (_enviar_dm_ig(ig, cid, token) if (_dm_ligado() and not teste) else False)
            # 2) resposta pública: sorteia 1 dos 3 estilos (só promete direct se DM foi)
            msg = _escolhe_ig_tmpl(dm_ok)

            if teste:
                _log(f"   [DRY] IG responderia @{c.get('username')} → {msg}"
                     + ("  (+DM)" if _dm_ligado() else ""))
                respondidos[cid] = int(time.time()); feitos += 1
                if feitos >= limites["max"]:
                    break
                continue
            r = _post(f"{GRAPH}/{cid}/replies", {"message": msg, "access_token": token})
            if r.get("id"):
                _log(f"   💬 IG respondeu @{c.get('username')} ({conta.get('handle')})"
                     + (" +DM" if dm_ok else ""))
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
                  {"fields": "id,created_time", "limit": limites["midias"],
                   "access_token": token}).get("data", [])
    for v in videos:
        if feitos >= limites["max"]:
            break
        if _velho_demais(v.get("created_time", ""), limites["horas"]):
            continue
        # filter=toplevel → só comentários de cima (ignora subcomentários/replies)
        cmts = _get(f"{GRAPH}/{v.get('id')}/comments",
                    {"fields": "id,message,from", "filter": "toplevel", "limit": 50,
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

    def _arg(nome, padrao):
        """--midias 5 / --horas 168. Existe porque rodar a cada 5 minutos com a
        janela inteira multiplicaria as chamadas do Graph por 12 e estouraria o
        limite da API. O cron faz duas passadas: uma rápida e frequente nos
        posts novos, e uma funda de hora em hora."""
        try:
            i = sys.argv.index(nome)
            return int(float(sys.argv[i + 1]))
        except (ValueError, IndexError):
            return padrao
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
        "horas": _arg("--horas", int(float(os.environ.get("AUTO_RESP_HORAS", "168")))),
        "midias": _arg("--midias", int(float(os.environ.get("AUTO_RESP_MIDIAS", "25")))),
        "max": _arg("--max", int(float(os.environ.get("AUTO_RESP_MAX", "40")))),
    }
    _log(f"{'DRY-RUN' if teste else 'ATIVO'} · {len(contas)} conta(s) · "
         f"gatilhos: {len(gatilhos)} · janela {limites['horas']}h "
         f"· até {limites['midias']} post(s) por conta")

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
