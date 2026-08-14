#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# tiktok_painel.py -- mini-painel web do TopShop pra INTEGRAÇÃO com o TikTok:
# Login Kit (OAuth) + Content Posting API. É o FLUXO visível que o review do TikTok
# exige no vídeo demo (conectar conta → escolher vídeo → postar → confirmação). A
# lógica de token/post vive em tiktok_poster.py (mesma que o daemon usa) — aqui é só
# a casca web (OAuth + UI).
#
# Roda atrás do Caddy (HTTPS) em jarvis.topshopoficial.com.br → localhost:8770.
#   .venv/bin/pip install flask requests
#   .venv/bin/python tiktok_painel.py            # dev (porta 8770)
import os
import json
import time
import secrets

import requests
from flask import Flask, request, redirect, url_for, session

import tiktok_poster as TP     # motor: tokens + postagem (fonte única)

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
SCOPES = "user.info.basic,video.publish"
CLIENT_KEY = TP.CLIENT_KEY
CLIENT_SECRET = TP.CLIENT_SECRET
REDIRECT_URI = os.environ.get("TIKTOK_REDIRECT_URI",
                              "https://jarvis.topshopoficial.com.br/tiktok/callback")

app = Flask(__name__)
app.secret_key = os.environ.get("TIKTOK_PANEL_SECRET", secrets.token_hex(16))

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
    toks = TP.ler_tokens()
    contas = "".join(
        f"<div class=card>✅ <b>@{t.get('username', oid)}</b> "
        f"<span style='color:#888'>({oid[:10]}…)</span></div>"
        for oid, t in toks.items()) or "<p style='color:#888'>Nenhuma conta conectada ainda.</p>"
    form = ""
    if toks:
        prontos = TP._slugs_prontos()[:50]
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
    params = {"client_key": CLIENT_KEY, "scope": SCOPES, "response_type": "code",
              "redirect_uri": REDIRECT_URI, "state": state}
    q = "&".join(f"{k}={requests.utils.quote(str(v), safe='')}" for k, v in params.items())
    return redirect(f"{AUTH_URL}?{q}")


@app.route("/tiktok/callback")
def callback():
    if request.args.get("error"):
        return _pagina(f"<p class=err>TikTok recusou: {request.args.get('error_description', '')}</p>"
                       "<p><a href='/'>voltar</a></p>")
    if request.args.get("state") != session.get("state"):
        return _pagina("<p class=err>state inválido (possível CSRF). Tente de novo.</p>")
    r = requests.post(TP.TOKEN_URL, data={
        "client_key": CLIENT_KEY, "client_secret": CLIENT_SECRET,
        "code": request.args.get("code", ""),
        "grant_type": "authorization_code", "redirect_uri": REDIRECT_URI},
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    j = r.json()
    if not j.get("access_token"):
        return _pagina(f"<p class=err>Falha no token: <code>{json.dumps(j)[:400]}</code></p>")
    open_id = j.get("open_id", "conta")
    toks = TP.ler_tokens()
    toks[open_id] = {
        "access_token": j["access_token"], "refresh_token": j.get("refresh_token", ""),
        "expira_em": time.time() + int(j.get("expires_in", 3600)),
        "scope": j.get("scope", ""), "username": open_id,
    }
    try:
        u = (TP.creator_info(j["access_token"]).get("data") or {}).get("creator_username")
        if u:
            toks[open_id]["username"] = u
    except Exception:
        pass
    TP.salvar_tokens(toks)
    return redirect(url_for("home"))


@app.route("/tiktok/postar", methods=["POST"])
def postar():
    open_id = request.form.get("open_id", "")
    slug = request.form.get("slug", "")
    legenda = request.form.get("legenda", "").strip()
    if not open_id or not slug:
        return _pagina("<p class=err>Escolha a conta e o vídeo.</p><p><a href='/'>voltar</a></p>")
    r = TP.postar_video(slug, open_id=open_id, legenda=legenda)
    if r.get("ok"):
        priv = r.get("privacidade", "")
        return _pagina(
            f"<div class=card><p class=ok>✅ Enviado ao TikTok!</p>"
            f"<p>publish_id: <code>{r['publish_id']}</code><br>"
            f"privacidade: <code>{priv}</code> "
            f"{'(privado — app ainda em sandbox)' if priv == 'SELF_ONLY' else '(público)'}</p>"
            f"<p>Confira o status no app do TikTok da conta.</p></div>"
            f"<p><a class=btn href='/'>voltar</a></p>")
    return _pagina(f"<div class=card><p class=err>❌ {r.get('erro')}</p></div>"
                   f"<p><a href='/'>voltar</a></p>")


@app.route("/health")
def health():
    return {"ok": True, "contas": len(TP.ler_tokens())}


@app.route("/tiktok/debug")
def debug():
    """creator_info bruto de cada conta (privacy_level_options, status) — prova de
    causa dos erros de posting."""
    out = {}
    for oid in TP.ler_tokens():
        token = TP.token_valido(oid)
        out[oid] = TP.creator_info(token) if token else {"erro": "sem token válido"}
    return out


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("TIKTOK_PANEL_PORT", 8770)))
