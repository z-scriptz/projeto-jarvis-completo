#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# tiktok_painel.py -- mini-painel web do TopShop pra INTEGRAÇÃO com o TikTok:
# Login Kit (OAuth) + Content Posting API (Direct Post, push_by_file). Serve dois
# propósitos: (1) o FLUXO visível que o review do TikTok exige no vídeo demo
# (conectar conta → escolher vídeo → postar → confirmação); (2) o motor de auth+post
# que o daemon reusa depois pra postar sozinho nas nossas contas oficiais.
#
# Roda atrás do Caddy (HTTPS) em jarvis.topshopoficial.com.br → localhost:8770.
#   .venv/bin/pip install flask requests
#   .venv/bin/python tiktok_painel.py            # dev (porta 8770)
#   (produção: gunicorn -b 127.0.0.1:8770 tiktok_painel:app)
#
# .env necessário (NÃO commitar):
#   TIKTOK_CLIENT_KEY=...           # da app no TikTok for Developers
#   TIKTOK_CLIENT_SECRET=...
#   TIKTOK_REDIRECT_URI=https://jarvis.topshopoficial.com.br/tiktok/callback
import os
import json
import time
import secrets
from pathlib import Path

import requests
from flask import Flask, request, redirect, session, url_for

BASE = Path(__file__).resolve().parent
PRONTO = BASE / "pronto_para_postar"
TOKENS = BASE / "shared" / "tiktok_tokens.json"     # {open_id: {...token...}} — NÃO commitar

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
CREATOR_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
SCOPES = "user.info.basic,video.publish"


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
CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "")
CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get("TIKTOK_REDIRECT_URI",
                              "https://jarvis.topshopoficial.com.br/tiktok/callback")

app = Flask(__name__)
app.secret_key = os.environ.get("TIKTOK_PANEL_SECRET", secrets.token_hex(16))


# ── armazenamento de tokens (por conta / open_id) ───────────────────────────
def _ler_tokens() -> dict:
    try:
        return json.loads(TOKENS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _salvar_tokens(d: dict):
    TOKENS.parent.mkdir(parents=True, exist_ok=True)
    TOKENS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _token_valido(open_id: str) -> str:
    """Access token válido da conta (refresca se expirou). '' se não der."""
    toks = _ler_tokens()
    t = toks.get(open_id)
    if not t:
        return ""
    if t.get("expira_em", 0) - 60 > time.time():
        return t.get("access_token", "")
    # refresh
    r = requests.post(TOKEN_URL, data={
        "client_key": CLIENT_KEY, "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token", "refresh_token": t.get("refresh_token", "")},
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    j = r.json()
    if j.get("access_token"):
        t.update(access_token=j["access_token"], refresh_token=j.get("refresh_token", t["refresh_token"]),
                 expira_em=time.time() + int(j.get("expires_in", 3600)))
        toks[open_id] = t
        _salvar_tokens(toks)
        return t["access_token"]
    return ""


# ── páginas ─────────────────────────────────────────────────────────────────
_CSS = ("body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:760px;"
        "margin:0 auto;padding:28px 20px;line-height:1.55;color:#111}"
        "h1{font-size:1.5rem}.btn{display:inline-block;background:#fe2c55;color:#fff;"
        "padding:11px 18px;border-radius:8px;text-decoration:none;font-weight:600;border:0;"
        "cursor:pointer;font-size:1rem}.card{border:1px solid #eee;border-radius:10px;"
        "padding:14px 16px;margin:12px 0}.ok{color:#0a8a3a}.err{color:#c00}"
        "select,input{padding:8px;border:1px solid #ccc;border-radius:6px;font-size:1rem}"
        "code{background:#f5f5f5;padding:1px 5px;border-radius:4px}")


def _pagina(corpo: str) -> str:
    return (f"<!doctype html><html lang=pt-BR><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>TopShop · TikTok</title><style>{_CSS}</style></head><body>"
            f"<h1>🅣 TopShop · Publicação no TikTok</h1>{corpo}</body></html>")


@app.route("/")
def home():
    if not (CLIENT_KEY and CLIENT_SECRET):
        return _pagina("<p class=err>Faltam TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET no .env.</p>")
    toks = _ler_tokens()
    contas = "".join(
        f"<div class=card>✅ <b>@{t.get('username', open_id)}</b> "
        f"<span style='color:#888'>({open_id[:10]}…)</span></div>"
        for open_id, t in toks.items()) or "<p style='color:#888'>Nenhuma conta conectada ainda.</p>"
    form = ""
    if toks:
        prontos = []
        if PRONTO.exists():
            prontos = [p.name for p in sorted(PRONTO.iterdir())
                       if p.is_dir() and (p / "video.mp4").exists()][:50]
        opts_conta = "".join(f"<option value='{oid}'>@{t.get('username', oid)}</option>"
                             for oid, t in toks.items())
        opts_video = "".join(f"<option value='{s}'>{s}</option>" for s in prontos) \
            or "<option value=''>(nenhum vídeo em pronto_para_postar/)</option>"
        form = (f"<h2>Postar um vídeo</h2><form method=post action='/tiktok/postar' class=card>"
                f"<p>Conta: <select name=open_id>{opts_conta}</select></p>"
                f"<p>Vídeo: <select name=slug>{opts_video}</select></p>"
                f"<p>Legenda: <input name=legenda size=48 placeholder='opcional (usa a do vídeo)'></p>"
                f"<button class=btn type=submit>Postar no TikTok</button></form>")
    return _pagina(
        f"<h2>Contas conectadas</h2>{contas}"
        f"<p><a class=btn href='/tiktok/login'>+ Conectar conta do TikTok</a></p>{form}")


@app.route("/tiktok/login")
def login():
    state = secrets.token_urlsafe(16)
    session["state"] = state
    params = {
        "client_key": CLIENT_KEY, "scope": SCOPES, "response_type": "code",
        "redirect_uri": REDIRECT_URI, "state": state,
    }
    q = "&".join(f"{k}={requests.utils.quote(str(v), safe='')}" for k, v in params.items())
    return redirect(f"{AUTH_URL}?{q}")


@app.route("/tiktok/callback")
def callback():
    if request.args.get("error"):
        return _pagina(f"<p class=err>TikTok recusou: {request.args.get('error_description', '')}</p>"
                       "<p><a href='/'>voltar</a></p>")
    if request.args.get("state") != session.get("state"):
        return _pagina("<p class=err>state inválido (possível CSRF). Tente de novo.</p>")
    code = request.args.get("code", "")
    r = requests.post(TOKEN_URL, data={
        "client_key": CLIENT_KEY, "client_secret": CLIENT_SECRET, "code": code,
        "grant_type": "authorization_code", "redirect_uri": REDIRECT_URI},
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    j = r.json()
    if not j.get("access_token"):
        return _pagina(f"<p class=err>Falha no token: <code>{json.dumps(j)[:400]}</code></p>")
    open_id = j.get("open_id", "conta")
    toks = _ler_tokens()
    toks[open_id] = {
        "access_token": j["access_token"], "refresh_token": j.get("refresh_token", ""),
        "expira_em": time.time() + int(j.get("expires_in", 3600)),
        "scope": j.get("scope", ""), "username": open_id,
    }
    # tenta pegar o @username via creator_info (deixa a conta mais legível na tela)
    try:
        ci = requests.post(CREATOR_URL, headers={
            "Authorization": f"Bearer {j['access_token']}",
            "Content-Type": "application/json; charset=UTF-8"}, timeout=30).json()
        u = (ci.get("data") or {}).get("creator_username")
        if u:
            toks[open_id]["username"] = u
    except Exception:
        pass
    _salvar_tokens(toks)
    return redirect(url_for("home"))


# ── postagem (Direct Post, push_by_file) ────────────────────────────────────
def _legenda_do_slug(slug: str) -> str:
    for nome in ("descricao_youtube.txt", "hashtags.txt"):
        p = PRONTO / slug / nome
        if p.exists():
            t = p.read_text(encoding="utf-8").strip()
            if t:
                return t[:2100]
    return slug.replace("_", " ")[:150]


def _postar(open_id: str, slug: str, legenda: str) -> dict:
    token = _token_valido(open_id)
    if not token:
        return {"ok": False, "erro": "sem token válido pra essa conta (reconecte)"}
    video = PRONTO / slug / "video.mp4"
    if not video.exists():
        return {"ok": False, "erro": f"vídeo não encontrado: {slug}"}
    H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    # 1) creator_info: valida a conta e diz os privacy_level PERMITIDOS (app não
    #    auditado só permite SELF_ONLY = privado; auditado libera público).
    ci = requests.post(CREATOR_URL, headers=H, timeout=30).json()
    dados = ci.get("data") or {}
    niveis = dados.get("privacy_level_options") or ["SELF_ONLY"]
    # app AUDITADO → público; NÃO auditado → SELF_ONLY (o único que a TikTok aceita
    # de client não auditado; mandar FOLLOWER_OF_CREATOR/etc. ainda dá erro de trava).
    if "PUBLIC_TO_EVERYONE" in niveis:
        privacidade = "PUBLIC_TO_EVERYONE"
    elif "SELF_ONLY" in niveis:
        privacidade = "SELF_ONLY"
    else:
        privacidade = niveis[0]
    tam = video.stat().st_size
    # 2) init (push_by_file, arquivo inteiro num chunk só)
    body = {
        "post_info": {
            "title": legenda or _legenda_do_slug(slug),
            "privacy_level": privacidade,
            "disable_comment": False, "disable_duet": False, "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD", "video_size": tam,
            "chunk_size": tam, "total_chunk_count": 1,
        },
    }
    ini = requests.post(INIT_URL, headers=H, json=body, timeout=60).json()
    if (ini.get("error") or {}).get("code") not in (None, "ok"):
        return {"ok": False, "erro": f"init falhou: {json.dumps(ini.get('error'))}"}
    d = ini.get("data") or {}
    publish_id, upload_url = d.get("publish_id"), d.get("upload_url")
    if not upload_url:
        return {"ok": False, "erro": f"sem upload_url: {json.dumps(ini)[:300]}"}
    # 3) upload dos bytes (PUT com Content-Range do arquivo inteiro)
    with open(video, "rb") as f:
        dados_bin = f.read()
    up = requests.put(upload_url, data=dados_bin, headers={
        "Content-Type": "video/mp4",
        "Content-Range": f"bytes 0-{tam - 1}/{tam}"}, timeout=300)
    if up.status_code not in (200, 201, 206):
        return {"ok": False, "erro": f"upload HTTP {up.status_code}: {up.text[:200]}"}
    return {"ok": True, "publish_id": publish_id, "privacidade": privacidade}


@app.route("/tiktok/postar", methods=["POST"])
def postar():
    open_id = request.form.get("open_id", "")
    slug = request.form.get("slug", "")
    legenda = request.form.get("legenda", "").strip()
    if not open_id or not slug:
        return _pagina("<p class=err>Escolha a conta e o vídeo.</p><p><a href='/'>voltar</a></p>")
    r = _postar(open_id, slug, legenda)
    if r.get("ok"):
        return _pagina(
            f"<div class=card><p class=ok>✅ Enviado ao TikTok!</p>"
            f"<p>publish_id: <code>{r['publish_id']}</code><br>"
            f"privacidade: <code>{r['privacidade']}</code> "
            f"{'(privado — app ainda em sandbox)' if r['privacidade'] == 'SELF_ONLY' else '(público)'}</p>"
            f"<p>Confira o status no app do TikTok da conta.</p></div>"
            f"<p><a class=btn href='/'>voltar</a></p>")
    return _pagina(f"<div class=card><p class=err>❌ {r.get('erro')}</p></div>"
                   f"<p><a href='/'>voltar</a></p>")


@app.route("/health")
def health():
    return {"ok": True, "contas": len(_ler_tokens())}


@app.route("/tiktok/debug")
def debug():
    """Mostra o que o TikTok REALMENTE enxerga de cada conta conectada (creator_info):
    privacy_level_options, se a conta está private, limites. É a prova de causa do
    erro 'unaudited_client_can_only_post_to_private_accounts'."""
    out = {}
    for oid in _ler_tokens():
        token = _token_valido(oid)
        if not token:
            out[oid] = {"erro": "sem token válido"}
            continue
        try:
            ci = requests.post(CREATOR_URL, headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8"}, timeout=30).json()
            out[oid] = ci
        except Exception as e:
            out[oid] = {"erro": str(e)[:150]}
    return out


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("TIKTOK_PANEL_PORT", 8770)))
