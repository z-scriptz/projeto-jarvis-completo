#!/usr/bin/env python3
# check_ambiente.py — pré-voo do Jarvis antes de subir o daemon 24/7 na VPS.
#
# Roda NA RAIZ do projeto:  python check_ambiente.py
#
# Confere, sem gastar crédito nem postar nada:
#   1. Módulos-base (shared.logger/config/path_utils) importam?
#   2. Módulos do pipeline (daemon, produção, uploaders) importam?
#   3. Bibliotecas de terceiros instaladas?
#   4. Variáveis de ambiente essenciais setadas? (não imprime o valor)
#   5. Pastas de trabalho existem/são graváveis?
#
# Sai com código 0 se está TUDO pronto, ou 1 se algo crítico falta.

import importlib
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
# garante que os pacotes do projeto (shared/, agents/, ...) sejam importáveis
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

OK, FALHAS = "✅", []


def _check_import(nome, critico=True):
    try:
        importlib.import_module(nome)
        print(f"  {OK} import {nome}")
        return True
    except Exception as e:
        marca = "❌" if critico else "⚠️ "
        print(f"  {marca} import {nome}  →  {type(e).__name__}: {str(e)[:120]}")
        if critico:
            FALHAS.append(f"import {nome}")
        return False


def _check_env(nome, critico=True):
    val = os.environ.get(nome, "").strip()
    if val:
        print(f"  {OK} {nome} setada")
        return True
    marca = "❌" if critico else "⚠️ "
    print(f"  {marca} {nome} AUSENTE")
    if critico:
        FALHAS.append(f"env {nome}")
    return False


def _check_pasta(rel, criar=True):
    p = RAIZ / rel
    try:
        if criar:
            p.mkdir(parents=True, exist_ok=True)
        ok = p.exists() and os.access(p, os.W_OK)
        print(f"  {OK if ok else '❌'} {rel}  ({'gravável' if ok else 'NÃO gravável'})")
        if not ok:
            FALHAS.append(f"pasta {rel}")
        return ok
    except Exception as e:
        print(f"  ❌ {rel}  →  {e}")
        FALHAS.append(f"pasta {rel}")
        return False


print("=" * 64)
print(f"  🔎 PRÉ-VOO JARVIS — {RAIZ}")
print(f"  Python {sys.version.split()[0]}")
print("=" * 64)

print("\n[1] Módulos-base (shared/):")
_check_import("shared.logger")
_check_import("shared.config")
_check_import("shared.path_utils")
_check_import("shared.production_state")

print("\n[2] Pipeline (o caminho do daemon 24/7):")
_check_import("agents.daemon_maestro")
_check_import("agents.production_runner_agent")
_check_import("agents.publish_guard")
_check_import("agents.youtube_uploader")
_check_import("agents.meta_uploader")
_check_import("agents.orchestrator")
_check_import("creative_engine.produzir_video")
_check_import("integrations.shopee_affiliate")
_check_import("integrations.telegram_repurpose_hunter", critico=False)

print("\n[3] Bibliotecas de terceiros:")
_check_import("requests")
_check_import("numpy")
_check_import("moviepy")
_check_import("PIL")
_check_import("telethon", critico=False)
_check_import("edge_tts", critico=False)
_check_import("googleapiclient", critico=False)  # youtube
_check_import("bs4", critico=False)              # scraping opcional

print("\n[4] Variáveis de ambiente:")
_check_env("SHOPEE_APP_ID")
_check_env("SHOPEE_APP_SECRET")
_check_env("TELEGRAM_API_ID", critico=False)
_check_env("TELEGRAM_API_HASH", critico=False)
_check_env("META_ACCESS_TOKEN", critico=False)
_check_env("FACEBOOK_PAGE_ID", critico=False)
_check_env("INSTAGRAM_USER_ID", critico=False)
_check_env("FAL_KEY", critico=False)

print("\n[5] Pastas de trabalho (criadas se faltarem):")
_check_pasta("videos")
_check_pasta("pronto_para_postar")
_check_pasta("shared/content_plans")
_check_pasta("shared/credentials", criar=False)

print("\n[6] Token do YouTube:")
tok = RAIZ / "shared" / "credentials" / "youtube_token.json"
if tok.exists() and tok.stat().st_size > 0:
    print(f"  {OK} youtube_token.json presente")
else:
    print("  ⚠️  youtube_token.json ausente — o 1º upload vai tentar abrir "
          "navegador (trava em VPS headless). Gere local e copie pra cá.")

print("\n" + "=" * 64)
if FALHAS:
    print(f"  ❌ {len(FALHAS)} item(ns) CRÍTICO(s) faltando:")
    for f in FALHAS:
        print(f"       • {f}")
    print("  → resolva antes de subir o daemon.")
    print("=" * 64)
    sys.exit(1)
else:
    print("  ✅ Ambiente pronto. Pode rodar:  python -m agents.daemon_maestro --once --dry-run")
    print("=" * 64)
    sys.exit(0)
