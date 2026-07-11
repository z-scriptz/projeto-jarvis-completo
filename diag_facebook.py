#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# diag_facebook.py -- diagnostico PRECISO do erro "não consegui obter o token da
# página". Bate na Graph API com o teu token e diz EXATAMENTE o que falta:
# token válido? tem pages_show_list? você administra a página? o PAGE_ID bate?
#
# Uso (VPS):  cd ~/jarvis && .venv/bin/python diag_facebook.py
# (só LÊ — não posta nada. Nunca imprime o token completo.)
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
GRAPH = "https://graph.facebook.com/v21.0"

# permissões que o Jarvis precisa pra postar em Página + Instagram
PRECISA = [
    "pages_show_list",
    "pages_manage_posts",
    "pages_read_engagement",
    "instagram_basic",
    "instagram_content_publish",
    "business_management",
]


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


def _mascara(t: str) -> str:
    if not t:
        return "(vazio)"
    return f"{t[:6]}…{t[-4:]} ({len(t)} chars)"


def _get(sess, path, token, **params):
    params["access_token"] = token
    try:
        r = sess.get(f"{GRAPH}/{path}", params=params, timeout=30)
        try:
            j = r.json()
        except Exception:
            j = {}
        return r.status_code, j
    except Exception as e:
        return 0, {"error": {"message": f"falha de rede: {e}"}}


def _erro(j):
    e = (j or {}).get("error") or {}
    if not e:
        return ""
    return f"[code {e.get('code')}/{e.get('type')}] {e.get('message')}"


def main():
    try:
        import requests
    except Exception:
        print("❌ lib 'requests' não instalada (pip install requests)")
        return 1
    sess = requests.Session()

    token = os.environ.get("META_ACCESS_TOKEN", "").strip()
    page_id = os.environ.get("FACEBOOK_PAGE_ID", "").strip()
    ig_id = os.environ.get("INSTAGRAM_USER_ID", "").strip()
    page_token = os.environ.get("FACEBOOK_PAGE_TOKEN", "").strip()

    print("=" * 58)
    print("🩺  DIAGNÓSTICO FACEBOOK / META")
    print("=" * 58)
    print(f"META_ACCESS_TOKEN : {_mascara(token)}")
    print(f"FACEBOOK_PAGE_ID  : {page_id or '❌ FALTANDO'}")
    print(f"INSTAGRAM_USER_ID : {ig_id or '(não setado)'}")
    print(f"FACEBOOK_PAGE_TOKEN(atalho): {'✅ setado' if page_token else '(não setado)'}")
    print()

    if not token:
        print("❌ Sem META_ACCESS_TOKEN no .env. Sem isso nada funciona.")
        return 1

    # 1) o token é válido? de quem é?
    st, me = _get(sess, "me", token, fields="id,name")
    if st != 200 or "id" not in me:
        print("❌ TOKEN INVÁLIDO ou expirado.")
        print("   " + (_erro(me) or f"HTTP {st}"))
        print("\n👉 Gere um token novo (passos no fim). Token de usuário expira!")
        return 1
    print(f"✅ Token válido — nome: {me.get('name')} (id {me.get('id')})")

    # 1.5) É um TOKEN DE PÁGINA? (o /me retorna a própria Página, não um usuário)
    st_ac, contas0 = _get(sess, "me/accounts", token, fields="id")
    sem_accounts = "nonexisting field" in (_erro(contas0).lower())
    eh_page_token = (page_id and str(me.get("id")) == page_id) or sem_accounts
    if eh_page_token:
        print("\n🎯 Esse token é um TOKEN DE PÁGINA (o /me retornou a própria Página,")
        print("   e /me/accounts não existe pra Página). Isso é BOM: pra postar na")
        print("   Página o Facebook usa exatamente um token de página como esse.")
        print("   Ele só está em META_ACCESS_TOKEN; o código procura em FACEBOOK_PAGE_TOKEN.")
        # verifica leitura da Página
        _, pg = _get(sess, page_id or str(me.get("id")), token, fields="name,fan_count")
        if "name" in pg:
            print(f"   ✅ Lê a Página: {pg.get('name')} (fãs: {pg.get('fan_count', '?')})")
        else:
            print(f"   ⚠️  Não leu a Página: {_erro(pg)}")
        # verifica alcance do Instagram
        if ig_id:
            _, ig = _get(sess, ig_id, token, fields="username,name")
            if "username" in ig or "name" in ig:
                print(f"   ✅ Alcança o Instagram: @{ig.get('username', ig.get('name'))}")
            else:
                print(f"   ⚠️  Não alcançou o IG ({ig_id}): {_erro(ig)}")
        print("\n" + "=" * 58)
        print("🧭  VEREDITO — fix de 1 linha")
        print("=" * 58)
        if page_token:
            print("• FACEBOOK_PAGE_TOKEN já está setado. Se ainda falhar, confirme que")
            print("  ele é o MESMO token de página (copie o de META_ACCESS_TOKEN).")
        else:
            print("• Adicione no .env:  FACEBOOK_PAGE_TOKEN=<o mesmo token de 3 meses>")
            print("  (o código usa ele direto pra postar na Página, sem /me/accounts).")
        print("• Depois: systemctl restart jarvis  → Facebook volta a postar.")
        print("• Instagram já usa esse token + INSTAGRAM_USER_ID (page token serve pro IG).")
        return 0

    # 2) permissões concedidas
    st, perms = _get(sess, "me/permissions", token)
    concedidas, negadas = set(), set()
    for p in (perms.get("data") or []):
        nome, status = p.get("permission"), p.get("status")
        (concedidas if status == "granted" else negadas).add(nome)
    print("\n🔑 Permissões:")
    faltando = []
    for p in PRECISA:
        if p in concedidas:
            print(f"   ✅ {p}")
        elif p in negadas:
            print(f"   ❌ {p}  (NEGADA — precisa reautorizar)")
            faltando.append(p)
        else:
            print(f"   ⚠️  {p}  (ausente)")
            faltando.append(p)

    # 3) páginas que o usuário administra
    st, contas = _get(sess, "me/accounts", token, fields="id,name,access_token,tasks")
    paginas = contas.get("data") or []
    print(f"\n📄 Páginas que você administra: {len(paginas)}")
    if not paginas:
        print("   ❌ NENHUMA. " + (_erro(contas) or "lista vazia"))
        print("   → Causa nº1: falta 'pages_show_list' OU você não é admin de")
        print("     nenhuma página com esse usuário.")
    achou = False
    for pg in paginas:
        pid = str(pg.get("id"))
        tem_tok = "🔑 tem token" if pg.get("access_token") else "sem token"
        marca = ""
        if pid == page_id:
            achou = True
            marca = "  ⬅️  ESTE é o seu FACEBOOK_PAGE_ID"
        print(f"   • {pg.get('name')} (id {pid}) — {tem_tok}{marca}")

    # 4) veredito
    print("\n" + "=" * 58)
    print("🧭  VEREDITO")
    print("=" * 58)
    if not page_id:
        print("• Falta FACEBOOK_PAGE_ID no .env. Copie o id de uma página acima.")
    elif paginas and not achou:
        print(f"• O FACEBOOK_PAGE_ID ({page_id}) NÃO está entre as páginas que você")
        print("  administra. Use um dos ids listados acima (o da página TopShop).")
    if faltando:
        print(f"• Permissões faltando: {', '.join(faltando)}")
        print("  Reautorize o token marcando TODAS elas.")
    if paginas and achou and not faltando:
        print("• Tudo certo pelas permissões/página! Se ainda falhar ao postar, o")
        print("  token de usuário pode ser de curta duração (expira ~1h). Troque")
        print("  por um token LONGO (60 dias) e derive um token de página que não")
        print("  expira (veja abaixo).")

    print("\n📘 COMO GERAR O TOKEN CERTO (rápido):")
    print("   1. developers.facebook.com → Graph API Explorer.")
    print("   2. App do TopShop → 'User Token' → Add Permissions: marque")
    print("      pages_show_list, pages_manage_posts, pages_read_engagement,")
    print("      instagram_basic, instagram_content_publish, business_management.")
    print("   3. 'Generate Access Token' e aceite com a conta ADMIN da página.")
    print("   4. Troque por token LONGO (60d):")
    print("      GET /oauth/access_token?grant_type=fb_exchange_token")
    print("          &client_id=APPID&client_secret=SECRET&fb_exchange_token=TOKEN")
    print("   5. Cole o token longo em META_ACCESS_TOKEN no .env e rode este")
    print("      diagnóstico de novo. (Opcional: pra nunca expirar, pegue o")
    print("      access_token da página em /me/accounts e ponha em")
    print("      FACEBOOK_PAGE_TOKEN — page token derivado de token longo não expira.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
