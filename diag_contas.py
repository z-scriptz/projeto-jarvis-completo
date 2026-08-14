#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# diag_contas.py -- enumera TODAS as Páginas + contas do Instagram ligadas ao seu
# token, pra montar o roteador multi-conta. SEGURO: imprime só ids/@usernames
# (nunca o token). Com --escrever, grava os tokens de cada página no .env como
# PAGE_TOKEN_<SLUG> (e mostra só mascarado).
#
# IMPORTANTE: pra listar TODAS as páginas, o META_ACCESS_TOKEN precisa ser um
# token de USUÁRIO (não de página) com pages_show_list + pages_manage_posts +
# instagram_basic + instagram_content_publish + business_management.
#
# Uso (VPS):  cd ~/jarvis && .venv/bin/python diag_contas.py
#   ver o que existe (não escreve nada)
#             cd ~/jarvis && .venv/bin/python diag_contas.py --escrever
#   grava os PAGE_TOKEN_<SLUG> no .env
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
GRAPH = "https://graph.facebook.com/v21.0"
ENV = BASE_DIR / ".env"


def _carregar_env():
    if not ENV.exists():
        return
    for linha in ENV.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        if linha.lower().startswith("export "):
            linha = linha[7:]
        k, _, v = linha.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_carregar_env()


def _mascara(t):
    return f"{t[:6]}…{t[-4:]}" if t else "(vazio)"


def _slug(nome):
    s = re.sub(r"[^A-Za-z0-9]+", "_", (nome or "").upper()).strip("_")
    return s or "PAGINA"


def _erro(j):
    e = (j or {}).get("error") or {}
    return f"[code {e.get('code')}/{e.get('type')}] {e.get('message')}" if e else ""


def _set_env(chave, valor):
    """Grava/atualiza CHAVE=valor no .env (sem duplicar)."""
    linhas = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    achou = False
    for i, l in enumerate(linhas):
        if l.strip().startswith(chave + "="):
            linhas[i] = f"{chave}={valor}"
            achou = True
            break
    if not achou:
        linhas.append(f"{chave}={valor}")
    ENV.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def _trocar_long_lived(sess, token, app_id, app_secret):
    """Troca um token de usuário CURTO por um LONG-LIVED (~60 dias). As páginas
    derivadas de um token long-lived viram tokens que NÃO EXPIRAM."""
    try:
        r = sess.get(f"{GRAPH}/oauth/access_token", timeout=30, params={
            "grant_type": "fb_exchange_token", "client_id": app_id,
            "client_secret": app_secret, "fb_exchange_token": token})
        return (r.json() or {}).get("access_token")
    except Exception:
        return None


def _validade(sess, token, app_id, app_secret):
    """Mostra quando o token expira (0 = nunca) via debug_token."""
    try:
        r = sess.get(f"{GRAPH}/debug_token", timeout=30, params={
            "input_token": token, "access_token": f"{app_id}|{app_secret}"})
        d = (r.json() or {}).get("data") or {}
        exp = d.get("expires_at")
        if exp == 0:
            return "NUNCA expira ✅"
        if exp:
            import time
            return "expira em " + time.strftime("%Y-%m-%d %H:%M", time.localtime(exp))
        return "?"
    except Exception:
        return "?"


def main():
    escrever = "--escrever" in sys.argv[1:]
    try:
        import requests
    except Exception:
        print("❌ lib 'requests' não instalada")
        return 1
    sess = requests.Session()
    token = os.environ.get("META_ACCESS_TOKEN", "").strip()
    if not token:
        print("❌ Sem META_ACCESS_TOKEN no .env.")
        return 1

    # long-lived: se tiver app id+secret, troca o token por um de 60 dias (as
    # páginas derivadas dele NÃO expiram — fim do 'session has expired').
    app_id = os.environ.get("FACEBOOK_APP_ID", "").strip()
    app_secret = os.environ.get("FACEBOOK_APP_SECRET", "").strip()
    if app_id and app_secret:
        ll = _trocar_long_lived(sess, token, app_id, app_secret)
        if ll:
            token = ll
            print("🔑 token trocado por LONG-LIVED (páginas derivadas não expiram)")
            if escrever:
                _set_env("META_ACCESS_TOKEN", token)
                print("   ✅ META_ACCESS_TOKEN (long-lived) atualizado no .env")
        print(f"   validade do token de usuário: {_validade(sess, token, app_id, app_secret)}")
    else:
        print("⚠️  Sem FACEBOOK_APP_ID / FACEBOOK_APP_SECRET no .env → NÃO dá pra fazer")
        print("   long-lived, e os PAGE_TOKEN vão expirar de novo. Ponha os 2 no .env.")

    # valida
    r = sess.get(f"{GRAPH}/me", params={"access_token": token, "fields": "id,name"}, timeout=30)
    me = r.json()
    if "id" not in me:
        print("❌ Token inválido: " + _erro(me))
        return 1
    print(f"Token de: {me.get('name')} (id {me.get('id')})")

    # lista páginas + IG ligado a cada uma
    r = sess.get(f"{GRAPH}/me/accounts", timeout=30, params={
        "access_token": token,
        "fields": "id,name,access_token,instagram_business_account{id,username,name}",
        "limit": 50,
    })
    dados = r.json()
    paginas = dados.get("data") or []
    if not paginas:
        print("\n❌ Nenhuma página listada. " + (_erro(dados) or ""))
        print("   → Provável: o token é de PÁGINA (não de usuário) ou falta")
        print("     pages_show_list. Gere um TOKEN DE USUÁRIO com as permissões.")
        return 1

    print(f"\n📄 {len(paginas)} página(s) encontrada(s):\n")
    print("=" * 62)
    resumo = []
    for pg in paginas:
        nome = pg.get("name", "?")
        pid = str(pg.get("id"))
        ptok = pg.get("access_token") or ""
        ig = pg.get("instagram_business_account") or {}
        ig_id = str(ig.get("id") or "")
        ig_user = ig.get("username") or ""
        slug = _slug(nome)
        print(f"• {nome}")
        print(f"    FACEBOOK_PAGE_ID  : {pid}")
        print(f"    INSTAGRAM_USER_ID : {ig_id or '(sem IG ligado)'}")
        print(f"    Instagram         : @{ig_user}" if ig_user else "    Instagram         : (nenhum)")
        print(f"    PAGE_TOKEN_{slug} : {_mascara(ptok)}")
        if escrever and ptok:
            _set_env(f"PAGE_TOKEN_{slug}", ptok)
            print(f"    ✅ gravado PAGE_TOKEN_{slug} no .env")
        print("-" * 62)
        resumo.append((nome, pid, ig_id, ig_user, slug))

    print("\n📋 COLA ISTO PRA MIM (é seguro — sem tokens):")
    for nome, pid, ig_id, ig_user, slug in resumo:
        print(f"   {nome} | page_id={pid} | ig_id={ig_id} | @{ig_user} | env=PAGE_TOKEN_{slug}")

    if not escrever:
        print("\nℹ️  Rode com  --escrever  pra gravar os PAGE_TOKEN_* no .env.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
