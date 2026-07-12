#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# auth_youtube.py -- autentica um CANAL do YouTube DIRETO NA VPS (headless),
# SEM túnel SSH. Você abre a URL, autoriza, o navegador tenta abrir 'localhost'
# e FALHA (normal) — mas o código fica na barra de endereço; você cola aqui.
# Gera token COM refresh_token (offline), que não morre em 1h.
#
# COMO USAR (numa sessão SSH normal, sem -L):
#   cd ~/jarvis && .venv/bin/python auth_youtube.py            # canal principal
#   cd ~/jarvis && .venv/bin/python auth_youtube.py beauty     # canal 'beauty'
#
# 1) Ele imprime uma URL. Abra no navegador (PC ou celular), no CANAL certo.
# 2) Autorize. O navegador vai tentar abrir 'http://localhost:8765/...' e FALHAR
#    ("localhost recusou"/"não foi possível acessar") — isso é ESPERADO.
# 3) Copie a URL INTEIRA da barra de endereço (tem '?code=...') e cole aqui.
#
# O 'canal' vira o sufixo do arquivo: youtube_token_<canal>.json
# (vazio = youtube_token.json, o principal).
import sys
import urllib.parse as _up
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CRED = RAIZ / "shared" / "credentials"
CLIENT = CRED / "client_secret.json"
REDIRECT = "http://localhost:8765/"   # não precisa estar no ar; só carrega o code
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _extrair_code(resp: str) -> str:
    resp = (resp or "").strip()
    if "code=" in resp:
        q = _up.urlparse(resp).query or resp.split("?", 1)[-1]
        vals = _up.parse_qs(q).get("code")
        if vals:
            return vals[0]
    return resp  # o usuário pode ter colado só o código puro


def main():
    canal = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    destino = CRED / (f"youtube_token_{canal}.json" if canal else "youtube_token.json")

    if not CLIENT.exists():
        print(f"❌ Falta a credencial OAuth: {CLIENT}")
        return 1
    try:
        from google_auth_oauthlib.flow import Flow
    except Exception:
        print("❌ Faltam libs: pip install google-auth-oauthlib google-api-python-client")
        return 1

    print("=" * 66)
    print(f"  AUTENTICAR canal: {canal or '(principal)'}  ->  {destino.name}")
    print("=" * 66)

    flow = Flow.from_client_secrets_file(str(CLIENT), scopes=SCOPES, redirect_uri=REDIRECT)
    auth_url, _ = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true")

    print("\n1) ABRA esta URL no navegador (no CANAL certo!):\n")
    print(auth_url)
    print("\n2) Autorize. O navegador vai tentar abrir 'localhost:8765' e FALHAR")
    print("   ('não foi possível acessar' / 'recusou') — ISSO É NORMAL.")
    print("3) COPIE a URL INTEIRA da barra de endereço (tem '?code=...').\n")

    resp = input("Cole aqui a URL (ou só o código) e Enter: ").strip()
    code = _extrair_code(resp)
    if not code:
        print("❌ Não achei o código. Rode de novo e cole a URL inteira.")
        return 1

    try:
        flow.fetch_token(code=code)
    except Exception as e:
        print(f"❌ Falha ao trocar o código por token: {e}")
        print("   (o código expira rápido — refaça o fluxo sem demorar.)")
        return 1

    creds = flow.credentials
    CRED.mkdir(parents=True, exist_ok=True)
    destino.write_text(creds.to_json(), encoding="utf-8")
    tem_refresh = bool(getattr(creds, "refresh_token", None))
    print(f"\n✅ Token salvo em {destino}")
    print(f"   refresh_token presente? {'SIM ✅' if tem_refresh else 'NÃO ⚠️'}")
    if not tem_refresh:
        print("   ⚠️ Sem refresh_token — revogue em myaccount.google.com/permissions")
        print("      e rode de novo (o prompt=consent força um novo refresh).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
