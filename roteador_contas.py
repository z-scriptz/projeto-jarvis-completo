#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# roteador_contas.py -- decide EM QUAL conta cada produto vai, pelo nicho.
# Lê contas.json (mapa nicho -> conta) e classifica o produto por palavras-chave
# no nome + categoria. Usado pela produção (pra renderizar com o handle certo e
# gravar conta.json ao lado do vídeo) e, via esse conta.json, pela postagem.
#
# Uso rápido de teste:
#   python3 roteador_contas.py "Sérum facial com vitamina C"   -> beleza
#   python3 roteador_contas.py "Fone Bluetooth TWS"            -> tech
#   python3 roteador_contas.py "Lata de lixo com pedal"        -> geral
import os
import re
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONTAS_JSON = BASE_DIR / "contas.json"


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

# palavras-chave de ALTA precisão (o default 'geral' é o fallback seguro).
_BELEZA = (
    "beleza", "beauty", "skincare", "maquiag", "makeup", "perfume", "hidratante",
    "batom", "serum", "sérum", "depila", "cilios", "cílios", "sobrancelha",
    "gloss", "cosmetic", "esmalte", "secador de cabelo", "chapinha", "prancha",
    "cabelo", "unha", "pele", "labial", "rímel", "rimel", "delineador",
)
_TECH = (
    "fone", "headset", "earbud", "carregador", "smartwatch", "smart watch",
    "powerbank", "power bank", "projetor", "drone", "caixa de som", "bluetooth",
    "webcam", "mouse", "teclado", "ring light", "luminária led", "luminaria led",
    "gamer", "smart tv", "roteador wi", "ssd", "pendrive", "gadget",
    # celular + acessórios (capinha/capa/película de iPhone iam pro 'geral' antes)
    "celular", "smartphone", "iphone", "android", "telefone", "capinha",
    "capa de celular", "capa de telefone", "capa magnetica", "capa magnética",
    "magsafe", "pelicula", "película", "suporte de celular", "suporte celular",
    "suporte veicular", "cabo usb", "cabo tipo c", "cabo lightning",
    "carregador sem fio", "hub usb", "adaptador usb",
)


def _sem_acento(s: str) -> str:
    return (s or "").translate(str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc"))


def carregar_contas() -> dict:
    try:
        return json.loads(CONTAS_JSON.read_text(encoding="utf-8"))
    except Exception:
        # fallback: só a conta principal a partir do .env
        return {"_default": {
            "nicho": "geral",
            "handle": os.environ.get("TOPSHOP_HANDLE", "@topshop.__"),
            "instagram_user_id": os.environ.get("INSTAGRAM_USER_ID", ""),
            "facebook_page_id": os.environ.get("FACEBOOK_PAGE_ID", ""),
            "page_token_env": "FACEBOOK_PAGE_TOKEN",
            "youtube": "",
        }}


def nicho_do_produto(nome: str, categoria: str = "") -> str:
    t = _sem_acento(f"{categoria} {nome}".lower())
    if any(_sem_acento(k) in t for k in _BELEZA):
        return "beleza"
    if any(_sem_acento(k) in t for k in _TECH):
        return "tech"
    return "geral"


def conta_do_produto(nome: str, categoria: str = "") -> dict:
    """Retorna a conta (dict) do nicho do produto, com o token JÁ resolvido do
    .env (campo 'token'). Cai no _default se o nicho não tiver conta."""
    contas = carregar_contas()
    nicho = nicho_do_produto(nome, categoria)
    conta = dict(contas.get(nicho) or contas.get("_default") or {})
    conta.setdefault("nicho", nicho)
    env = conta.get("page_token_env", "")
    conta["token"] = os.environ.get(env, "") if env else ""
    return conta


def conta_para_json(conta: dict) -> dict:
    """Só o que o meta_uploader precisa ao lado do vídeo — SEM o token (fica no
    .env; o uploader resolve pelo page_token_env)."""
    return {
        "nicho": conta.get("nicho", "geral"),
        "handle": conta.get("handle", ""),
        "instagram_user_id": conta.get("instagram_user_id", ""),
        "facebook_page_id": conta.get("facebook_page_id", ""),
        "page_token_env": conta.get("page_token_env", ""),
        "youtube": conta.get("youtube", ""),
    }


def main():
    nome = " ".join(sys.argv[1:]) or "produto teste"
    c = conta_do_produto(nome)
    print(f"produto: {nome}")
    print(f"nicho  : {c.get('nicho')}")
    print(f"handle : {c.get('handle')}")
    print(f"ig_id  : {c.get('instagram_user_id')}  | page: {c.get('facebook_page_id')}")
    print(f"token  : {'✅ resolvido' if c.get('token') else '⚠️ vazio (' + c.get('page_token_env','') + ' não está no .env)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
