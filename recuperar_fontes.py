#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# recuperar_fontes.py -- reconstrói a lista de perfis-FONTE a partir do estado
# que o coletor deixou em disco, quando o arquivo de perfis se perdeu.
#
# POR QUE ISSO EXISTE (03/09/2026) — E FOI CULPA MINHA
# ────────────────────────────────────────────────────
# Eu li o `instagram_perfis.txt` DO REPO (36 perfis), tratei como se fosse o de
# produção e mandei uma linha de deploy que sobrescreve:
#
#     git show FETCH_HEAD:instagram_perfis.txt > instagram_perfis.txt
#
# Só que a VPS tinha **98 fontes** — o arquivo cresceu lá (add_fontes.py, poda
# automática) e NUNCA voltou pro git. O arquivo do repo estava velho, e o
# `git show` apagou 98 fontes vivas por cima. Não havia commit pra desfazer:
# arquivo rastreado + modificação nunca commitada = o `git show` come.
#
# ⚠️ A LIÇÃO, PRA NÃO REPETIR: `git show FETCH_HEAD:X > X` só é seguro pra
# arquivo que o REPO é dono. Pra arquivo que a PRODUÇÃO edita (listas de fonte,
# .env, estado), o repo é a cópia velha — sobrescrever é perder.
#
# A recuperação existe porque o coletor deixa rastro em três lugares:
#   1. shared/fontes_saude.json   {perfil: {"zero_seguidas": N, "fonte": canal}}
#   2. shared/ig_rotacao.json     (só o offset — não tem nomes, mas confirma o total)
#   3. inbox_tiktok/*/plano.json  campo `perfil_fonte` (só quem já rendeu vídeo)
#   4. shared/posts_ledger.jsonl  idem, histórico longo
#
# Uso (VPS):
#   .venv/bin/python recuperar_fontes.py                 # só MOSTRA o que achou
#   .venv/bin/python recuperar_fontes.py --canal instagram
#   .venv/bin/python recuperar_fontes.py --canal instagram --gravar
import argparse
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SAUDE = BASE_DIR / "shared" / "fontes_saude.json"
LEDGER = BASE_DIR / "shared" / "posts_ledger.jsonl"
INBOX = BASE_DIR / "inbox_tiktok"
ARQUIVO = {"instagram": BASE_DIR / "instagram_perfis.txt",
           "tiktok": BASE_DIR / "tiktok_perfis.txt"}


def _norm(p: str) -> str:
    return (p or "").strip().lstrip("@").rstrip("/").lower().split("/")[-1]


def _da_saude(canal: str) -> dict:
    """A fonte MAIS COMPLETA: o coletor grava aqui TODA fonte que ele varreu,
    tenha rendido vídeo ou não. É o único lugar que guarda também as que nunca
    renderam — que são justamente as que o `perfil_fonte` do ledger não tem."""
    try:
        d = json.loads(SAUDE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"   ⚠️  {SAUDE.name} ilegível ({str(e)[:60]})")
        return {}
    out = {}
    for perfil, s in (d or {}).items():
        if not isinstance(s, dict):
            continue
        if canal and s.get("fonte") != canal:
            continue
        out[_norm(perfil)] = int(s.get("zero_seguidas", 0))
    return out


def _do_ledger() -> set:
    """Perfis que JÁ RENDERAM vídeo. Não distingue canal (o ledger não guarda),
    então serve de conferência, não de fonte primária."""
    achados = set()
    for pj in sorted(INBOX.glob("*/plano.json")) if INBOX.exists() else []:
        try:
            achados.add(_norm(json.loads(pj.read_text(encoding="utf-8"))
                              .get("perfil_fonte", "")))
        except Exception:
            pass
    if LEDGER.exists():
        try:
            for linha in LEDGER.read_text(encoding="utf-8").splitlines():
                if '"perfil_fonte"' not in linha:
                    continue
                m = re.search(r'"perfil_fonte"\s*:\s*"([^"]+)"', linha)
                if m:
                    achados.add(_norm(m.group(1)))
        except Exception:
            pass
    achados.discard("")
    return achados


def _no_arquivo(canal: str) -> set:
    arq = ARQUIVO.get(canal)
    if not arq or not arq.exists():
        return set()
    out = set()
    for l in arq.read_text(encoding="utf-8").splitlines():
        l = l.strip()
        if not l or l.startswith("#"):
            continue
        out.add(_norm(re.split(r"[\s#]", l)[0]))
    out.discard("")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="recupera lista de perfis-fonte")
    ap.add_argument("--canal", default="instagram", choices=("instagram", "tiktok"))
    ap.add_argument("--gravar", action="store_true",
                    help="acrescenta ao arquivo do canal (NUNCA sobrescreve)")
    a = ap.parse_args()

    print(f"🔎 recuperando fontes do canal '{a.canal}'\n")
    saude = _da_saude(a.canal)
    print(f"   {SAUDE.name}: {len(saude)} perfil(is)")
    rendeu = _do_ledger()
    print(f"   ledger + inbox:   {len(rendeu)} perfil(is) que já renderam vídeo")
    atual = _no_arquivo(a.canal)
    print(f"   {ARQUIVO[a.canal].name}: {len(atual)} perfil(is) HOJE")

    faltando = sorted(set(saude) - atual)
    if not faltando:
        print("\n✅ nada a recuperar — o arquivo já tem tudo que o histórico conhece.")
        return 0

    # quem já rendeu vídeo é PROVA de que a fonte presta; separo pra ele decidir
    provados = [p for p in faltando if p in rendeu]
    resto = [p for p in faltando if p not in rendeu]

    print(f"\n⚠️  {len(faltando)} perfil(is) do histórico NÃO estão no arquivo:\n")
    if provados:
        print(f"   ✅ {len(provados)} JÁ RENDERAM VÍDEO (prova de que prestam):")
        for p in provados:
            print(f"      {p}   (rodadas 0-keeper: {saude.get(p, 0)})")
    if resto:
        print(f"\n   ◻️  {len(resto)} sem vídeo registrado "
              f"(pode ser fonte nova, morta, ou de antes do ledger):")
        print("      " + ", ".join(resto))

    if not a.gravar:
        print(f"\n📋 pra gravar (ACRESCENTA no fim, não sobrescreve):")
        print(f"   .venv/bin/python recuperar_fontes.py --canal {a.canal} --gravar")
        return 0

    arq = ARQUIVO[a.canal]
    # ⚠️ ACRESCENTA. Sobrescrever foi exatamente o que causou o problema; esta
    # ferramenta não pode repetir o defeito que ela existe pra consertar.
    from datetime import date
    bloco = [f"\n# ── recuperado de {SAUDE.name} em {date.today().isoformat()} ──"]
    if provados:
        bloco.append("# já renderam vídeo no histórico:")
        bloco += provados
    if resto:
        bloco.append("# sem vídeo registrado — a poda por coleta decide:")
        bloco += resto
    with arq.open("a", encoding="utf-8") as f:
        f.write("\n".join(bloco) + "\n")
    print(f"\n✅ {len(faltando)} perfil(is) ACRESCENTADOS em {arq.name} "
          f"(o que já estava lá foi preservado)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
