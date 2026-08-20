#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_cache_roteador.py -- limpa do cache do roteador o que foi classificado
#                            por um prompt que não conhecia pet e moda.
#
# POR QUE EXISTE (20/08)
# ─────────────────────
# Em 19/08 o roteador ganhou os nichos `pet` e `moda` — antes disso
# `_NICHOS_VALIDOS` era ("beleza","tech","casa","geral") e o prompt do Gemini
# listava só esses quatro. Todo produto de pet ou moda que passou por ali
# voltou **'geral'**, e a resposta ficou GRAVADA:
#
#     shared/roteador_cache.json      {"caminha para cachorro g": "geral", …}
#
# O cache é consultado por produto, uma vez só. Sem limpar, os produtos já
# vistos continuam indo pro @topshop.__ para sempre, com o roteador novo
# instalado e funcionando — o conserto valeria só pro que ainda não passou.
#
# ⚠️ O QUE ELE APAGA, E O QUE NÃO APAGA
# ────────────────────────────────────
# A ordem no roteador é: palavra-chave PRIMEIRO, IA depois (e o cache vive
# dentro da IA). Isso muda o alvo:
#
#   • entrada que HOJE casa em pet/moda por palavra-chave → o cache nem é
#     consultado, ela já está corrigida. Apago mesmo assim, por higiene: é
#     entrada morta que só confunde quem for ler o arquivo.
#   • entrada com valor 'geral' → é a suspeita de verdade. 'geral' era o
#     balde do prompt velho, e é onde pet e moda foram parar. Apago pra ser
#     reperguntada com o prompt novo.
#   • entrada 'beleza' / 'tech' / 'casa' → MANTENHO. Foram classificações
#     positivas num prompt que sabia expressá-las; apagar seria queimar
#     chamada de API pra reconfirmar o que já está certo.
#
# ⚠️ CUSTA CHAMADA DE GEMINI. Cada entrada apagada é uma pergunta nova na
# próxima vez que o produto aparecer. Por isso o padrão é `--ver`: mostra o
# tamanho do estrago antes de fazer.
#
# Uso (VPS):
#   python3 patch_cache_roteador.py           # só mostra (padrão)
#   python3 patch_cache_roteador.py --aplicar # limpa, com backup

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

CACHE = BASE / "shared" / "roteador_cache.json"


def _log(m):
    print(f"[cache] {m}", flush=True)


def main():
    p = argparse.ArgumentParser(
        description="Limpa o cache do roteador do que o prompt velho classificou.")
    p.add_argument("--aplicar", action="store_true",
                   help="apaga de verdade (o padrão é só mostrar)")
    args = p.parse_args()

    if not CACHE.exists():
        _log(f"não existe {CACHE} — nada a limpar (o cache nasce na 1ª pergunta)")
        return 0
    try:
        dados = json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception as e:
        _log(f"cache ilegível ({str(e)[:60]}) — não mexo")
        return 1
    if not isinstance(dados, dict) or not dados:
        _log("cache vazio — nada a limpar")
        return 0

    try:
        import roteador_contas as R
    except Exception as e:
        _log(f"não consegui carregar o roteador: {str(e)[:70]}")
        return 1

    ja_corrigidas, geral, mantidas = {}, {}, {}
    for chave, valor in dados.items():
        agora = R._por_palavra_chave(R._sem_acento(str(chave).lower()))
        if agora in ("pet", "moda"):
            ja_corrigidas[chave] = (valor, agora)
        elif str(valor).strip().lower() == "geral":
            geral[chave] = valor
        else:
            mantidas[chave] = valor

    _log(f"o cache tem {len(dados)} entrada(s)")
    if ja_corrigidas:
        _log(f"{len(ja_corrigidas)} já corrigida(s) pela palavra-chave "
             f"(a IA nem é consultada nessas) — apago por higiene:")
        for chave, (antes, agora) in list(ja_corrigidas.items())[:8]:
            _log(f"     '{str(chave)[:44]}'  {antes} → {agora}")
        if len(ja_corrigidas) > 8:
            _log(f"     … e mais {len(ja_corrigidas) - 8}")
    _log(f"{len(geral)} com valor 'geral' — o balde do prompt velho, onde pet "
         f"e moda foram parar; apago pra reperguntar")
    _log(f"{len(mantidas)} mantida(s) (beleza/tech/casa — classificação que o "
         f"prompt velho sabia fazer)")

    apagar = len(ja_corrigidas) + len(geral)
    if not apagar:
        _log("nada a apagar — o cache já está coerente com o roteador novo")
        return 0
    _log(f"→ apagaria {apagar} de {len(dados)}; "
         f"cada uma vira 1 pergunta ao Gemini quando o produto reaparecer")

    if not args.aplicar:
        _log("(--ver é o padrão: não apaguei nada. Use --aplicar)")
        return 0

    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = CACHE.with_suffix(f".json.bak_{carimbo}")
    shutil.copy2(CACHE, backup)
    CACHE.write_text(json.dumps(mantidas, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    _log(f"✅ apaguei {apagar} · sobraram {len(mantidas)}")
    _log(f"   backup: {backup.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
