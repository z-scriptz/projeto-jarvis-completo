#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# caca_prompt_vazado.py -- tem pedaço de PROMPT virando nome de produto?
#
# O ACHADO (06/09/2026)
# ─────────────────────
# Rodando o `conferir_match --sem-foto`, apareceu isto na lista de pacotes:
#
#     ✅ 1) É O NOME DE UM PRODUTO FÍSICO À VEN   · u9_tech_DcQ6T3KKJoT
#
# Esse é um pedaço do MEU prompt. O Gemini devolveu as instruções em vez da
# resposta e o coletor gravou como se fosse o nome do produto. Esse pacote
# produziria um vídeo vendendo "1) É O NOME DE UM PRODUTO FÍSICO À VENDA", com
# link de busca pra isso.
#
# ⚠️ E O JUIZ APROVOU COM ✅. Perguntado "este vídeo mostra um <aquilo>?", ele
# disse SIM. Nome sem sentido devia dar TALVEZ — é fraqueza do juiz, anotada.
#
# ⚠️ ISTO NÃO GASTA API. São padrões literais de instrução, não julgamento de
# modelo: ou o nome tem marca de prompt, ou não tem. Chamar o Gemini pra
# decidir isso seria pagar por uma coisa que um regex resolve com certeza.
#
#   .venv/bin/python caca_prompt_vazado.py            # só lista
#   .venv/bin/python caca_prompt_vazado.py --marcar   # tira da fila
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
PASTAS = [BASE / "inbox_tiktok", BASE / "inbox_tiktok" / "_produzidos"]

# ⚠️ CONSERVADOR DE PROPÓSITO. Nome de produto de verdade é caótico — tem
# CAIXA ALTA ('KIT PLASÚTIL LUXO CESTO ROUPAS'), número, barra, parêntese. Se
# eu marcasse por "parece estranho", levaria produto bom junto. Aqui só entra
# o que é MARCA DE INSTRUÇÃO, coisa que ninguém põe em anúncio.
MARCAS = [
    (re.compile(r"^\s*\d+\s*[\)\.]\s"), "começa com item numerado ('1)')"),
    (re.compile(r"\b(é|e) o nome de um produto", re.I), "frase do meu prompt"),
    (re.compile(r"\bresponda (apenas|so|só|somente)\b", re.I), "instrução 'responda apenas'"),
    (re.compile(r"\b(sem explicar|sem markdown|sem aspas)\b", re.I), "instrução de formato"),
    (re.compile(r"^\s*(formato|exemplo|regras|resposta|saida|saída)\s*:", re.I), "rótulo de prompt"),
    (re.compile(r"\bem portugu[êe]s do brasil\b", re.I), "instrução de idioma"),
    (re.compile(r"\bproduto f[íi]sico [àa] venda\b", re.I), "frase do meu prompt"),
    (re.compile(r"\b(traduza|escreva|liste|devolva|retorne)\b.{0,20}\b(o|a|os|as)\b", re.I),
     "verbo de comando"),
    (re.compile(r"\{[a-z_]+\}"), "placeholder de template ('{nome}')"),
]


def marca_de_prompt(nome: str):
    """O motivo, se este nome tem marca de instrução. None se estiver limpo."""
    n = (nome or "").strip()
    if not n:
        return None
    for rx, motivo in MARCAS:
        if rx.search(n):
            return motivo
    return None


def main() -> int:
    marcar = "--marcar" in sys.argv[1:]

    achados, total = [], 0
    for pasta in PASTAS:
        if not pasta.exists():
            continue
        for pj in sorted(pasta.glob("*/plano.json")):
            try:
                info = json.loads(pj.read_text(encoding="utf-8"))
            except Exception:
                continue
            total += 1
            if info.get("nao_e_produto"):
                continue
            motivo = marca_de_prompt(info.get("produto") or "")
            if motivo:
                achados.append((pj, info, motivo))

    if not total:
        print("❌ nenhum plano.json — rode na VPS, dentro de ~/jarvis")
        return 1

    print(f"📦 {total} pacote(s) na fila\n")
    if not achados:
        print("✅ nenhum prompt vazado. O caso do u9_tech era isolado.")
        return 0

    print(f"🚨 {len(achados)} nome(s) com marca de prompt:\n")
    for pj, info, motivo in achados:
        print(f"   • {(info.get('produto') or '')[:64]}")
        print(f"     {motivo} · {pj.parent.name}")

    if not marcar:
        print(f"\n📋 pra tirar da fila: .venv/bin/python "
              f"caca_prompt_vazado.py --marcar")
        print(f"   ⚠️ OLHE A LISTA ANTES. Se algum for produto de verdade, o "
              f"padrão é meu\n      e eu conserto — não quero levar produto bom "
              f"junto.")
        return 0

    n = 0
    for pj, info, motivo in achados:
        try:
            # marca, não apaga — mesma regra do resto do projeto
            info["nao_e_produto"] = True
            info["motivo_bloqueio"] = f"caca_prompt_vazado: {motivo}"
            pj.write_text(json.dumps(info, ensure_ascii=False, indent=2),
                          encoding="utf-8")
            n += 1
        except Exception as e:
            print(f"   ⚠️ não marquei {pj.parent.name}: {str(e)[:50]}")
    print(f"\n   🚫 {n} fora da fila (reversível: tire 'nao_e_produto' do JSON)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
