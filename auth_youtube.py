#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# auth_youtube.py -- autentica um CANAL do YouTube DIRETO NA VPS (headless), via
# túnel SSH. Sem navegador na VPS e sem instalar nada no PC. Gera um token COM
# refresh_token (offline), que não morre em 1h.
#
# COMO USAR:
#   1) No seu PC, conecte com o túnel (porta 8765):
#         ssh -L 8765:localhost:8765 root@217.216.53.243
#   2) Já dentro da VPS:
#         cd ~/jarvis && .venv/bin/python auth_youtube.py            # canal principal
#         cd ~/jarvis && .venv/bin/python auth_youtube.py beauty     # canal 'beauty'
#   3) Ele imprime uma URL. ABRA no navegador do PC, faça login NA CONTA/CANAL
#      certo e autorize. O código volta pelo túnel e o token é salvo na VPS.
#
# O 'canal' vira o sufixo do arquivo: youtube_token_<canal>.json
# (vazio = youtube_token.json, o principal).
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CRED = RAIZ / "shared" / "credentials"
CLIENT = CRED / "client_secret.json"
PORT = 8765
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main():
    canal = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    destino = CRED / (f"youtube_token_{canal}.json" if canal else "youtube_token.json")

    if not CLIENT.exists():
        print(f"❌ Falta a credencial OAuth: {CLIENT}")
        print("   Baixe do Google Cloud (OAuth client, tipo 'App para computador').")
        return 1
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except Exception:
        print("❌ Faltam libs: pip install google-auth-oauthlib google-api-python-client")
        return 1

    print("=" * 64)
    print(f"  AUTENTICAR canal: {canal or '(principal)'}  ->  {destino.name}")
    print("=" * 64)
    print("  Requer o túnel:  ssh -L 8765:localhost:8765 root@217.216.53.243")
    print("  Vou imprimir a URL — abra NO NAVEGADOR DO PC, no canal certo.\n")

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES)
    creds = flow.run_local_server(
        host="localhost", port=PORT, open_browser=False,
        access_type="offline", prompt="consent",
        authorization_prompt_message="\n>>> ABRA ESTA URL NO NAVEGADOR DO PC:\n\n{url}\n",
        success_message="Pronto! Pode fechar a aba e voltar ao terminal.")

    CRED.mkdir(parents=True, exist_ok=True)
    destino.write_text(creds.to_json(), encoding="utf-8")
    tem_refresh = bool(getattr(creds, "refresh_token", None))
    print(f"\n✅ Token salvo em {destino}")
    print(f"   refresh_token presente? {'SIM ✅' if tem_refresh else 'NÃO ⚠️'}")
    if not tem_refresh:
        print("   ⚠️ Sem refresh_token — o app pode já ter sido autorizado antes.")
        print("      Revogue em myaccount.google.com/permissions e rode de novo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
