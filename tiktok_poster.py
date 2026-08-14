#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# tiktok_poster.py -- MOTOR de postagem no TikTok (Content Posting API, Direct Post,
# push_by_file). Fonte ÚNICA da lógica de post: o painel web (tiktok_painel) e o
# daemon (quando o app for aprovado) chamam o MESMO postar_video(). Guarda/refresca
# o token por conta em shared/tiktok_tokens.json. Escolhe público quando auditado,
# SELF_ONLY quando sandbox. Mapeia nicho→conta pra multi-conta.
#
# CLI (teste): .venv/bin/python tiktok_poster.py <slug> [--nicho beleza] [--conta open_id]
import os
import sys
import json
import time
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
PRONTO = BASE / "pronto_para_postar"
TOKENS = BASE / "shared" / "tiktok_tokens.json"     # {open_id: {...}} — NÃO commitar

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
CREATOR_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


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


# ── tokens por conta ────────────────────────────────────────────────────────
def ler_tokens() -> dict:
    try:
        return json.loads(TOKENS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def salvar_tokens(d: dict):
    TOKENS.parent.mkdir(parents=True, exist_ok=True)
    TOKENS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def token_valido(open_id: str) -> str:
    """Access token válido da conta (refresca se expirou). '' se não der."""
    toks = ler_tokens()
    t = toks.get(open_id)
    if not t:
        return ""
    if t.get("expira_em", 0) - 60 > time.time():
        return t.get("access_token", "")
    r = requests.post(TOKEN_URL, data={
        "client_key": CLIENT_KEY, "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token", "refresh_token": t.get("refresh_token", "")},
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    j = r.json()
    if j.get("access_token"):
        t.update(access_token=j["access_token"],
                 refresh_token=j.get("refresh_token", t["refresh_token"]),
                 expira_em=time.time() + int(j.get("expires_in", 3600)))
        toks[open_id] = t
        salvar_tokens(toks)
        return t["access_token"]
    return ""


def conta_do_nicho(nicho: str = "") -> str:
    """open_id da conta TikTok pro nicho. Prioriza TIKTOK_CONTA_<NICHO> no .env
    (multi-conta); senão cai na única/primeira conta conectada."""
    env = os.environ.get(f"TIKTOK_CONTA_{(nicho or '').upper()}", "").strip()
    if env:
        return env
    toks = ler_tokens()
    return next(iter(toks), "")


# ── API ─────────────────────────────────────────────────────────────────────
def creator_info(token: str) -> dict:
    return requests.post(CREATOR_URL, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8"}, timeout=30).json()


def _privacidade(niveis: list) -> str:
    """Público se auditado; SELF_ONLY se sandbox (o único que client não auditado
    aceita — mandar FOLLOWER_OF_CREATOR/etc. dá erro de trava)."""
    if "PUBLIC_TO_EVERYONE" in niveis:
        return "PUBLIC_TO_EVERYONE"
    if "SELF_ONLY" in niveis:
        return "SELF_ONLY"
    return niveis[0] if niveis else "SELF_ONLY"


def legenda_do_slug(slug: str) -> str:
    for nome in ("descricao_youtube.txt", "hashtags.txt"):
        p = PRONTO / slug / nome
        if p.exists():
            t = p.read_text(encoding="utf-8").strip()
            if t:
                return t[:2100]
    return slug.replace("_", " ")[:150]


def checar_status(open_id: str, publish_id: str) -> dict:
    """Consulta o status do publish (PROCESSING / PUBLISH_COMPLETE / FAILED …)."""
    token = token_valido(open_id)
    if not token:
        return {"erro": "sem token"}
    return requests.post(STATUS_URL, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8"},
        json={"publish_id": publish_id}, timeout=30).json()


def postar_video(slug: str, nicho: str = "", open_id: str = "", legenda: str = "",
                 poll: bool = False) -> dict:
    """Posta 1 vídeo pronto (pronto_para_postar/<slug>/video.mp4) no TikTok via
    Direct Post push_by_file. Retorna {ok, publish_id, privacidade, status?, erro?}."""
    if not (CLIENT_KEY and CLIENT_SECRET):
        return {"ok": False, "erro": "faltam TIKTOK_CLIENT_KEY/SECRET no .env"}
    open_id = open_id or conta_do_nicho(nicho)
    if not open_id:
        return {"ok": False, "erro": "nenhuma conta TikTok conectada (use o painel)"}
    token = token_valido(open_id)
    if not token:
        return {"ok": False, "erro": f"sem token válido pra {open_id} (reconecte)"}
    video = PRONTO / slug / "video.mp4"
    if not video.exists():
        return {"ok": False, "erro": f"vídeo não encontrado: {slug}"}
    H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    ci = creator_info(token)
    niveis = (ci.get("data") or {}).get("privacy_level_options") or ["SELF_ONLY"]
    priv = _privacidade(niveis)
    tam = video.stat().st_size
    body = {
        "post_info": {
            "title": legenda or legenda_do_slug(slug), "privacy_level": priv,
            "disable_comment": False, "disable_duet": False, "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD", "video_size": tam,
            "chunk_size": tam, "total_chunk_count": 1,
        },
    }
    ini = requests.post(INIT_URL, headers=H, json=body, timeout=60).json()
    if (ini.get("error") or {}).get("code") not in (None, "ok"):
        return {"ok": False, "erro": f"init: {json.dumps(ini.get('error'))}"}
    d = ini.get("data") or {}
    publish_id, upload_url = d.get("publish_id"), d.get("upload_url")
    if not upload_url:
        return {"ok": False, "erro": f"sem upload_url: {json.dumps(ini)[:300]}"}
    with open(video, "rb") as f:
        up = requests.put(upload_url, data=f.read(), headers={
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{tam - 1}/{tam}"}, timeout=300)
    if up.status_code not in (200, 201, 206):
        return {"ok": False, "erro": f"upload HTTP {up.status_code}: {up.text[:200]}"}
    out = {"ok": True, "publish_id": publish_id, "privacidade": priv, "open_id": open_id}
    if poll:                                  # confirma o processamento (best-effort)
        for _ in range(6):
            time.sleep(4)
            st = (checar_status(open_id, publish_id).get("data") or {}).get("status", "")
            out["status"] = st
            if st in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX", "FAILED"):
                out["ok"] = st != "FAILED"
                break
    return out


def _slugs_prontos() -> list:
    if not PRONTO.exists():
        return []
    return [p.name for p in sorted(PRONTO.iterdir())
            if p.is_dir() and (p / "video.mp4").exists()]


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("--"):
        print("uso: tiktok_poster.py <slug> [--nicho beleza] [--conta open_id]")
        print("contas conectadas:", ", ".join(ler_tokens().keys()) or "(nenhuma)")
        print("prontos:", ", ".join(_slugs_prontos()[:10]) or "(nenhum)")
        return 1
    slug = args[0]
    nicho = args[args.index("--nicho") + 1] if "--nicho" in args else ""
    conta = args[args.index("--conta") + 1] if "--conta" in args else ""
    r = postar_video(slug, nicho=nicho, open_id=conta, poll=True)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
