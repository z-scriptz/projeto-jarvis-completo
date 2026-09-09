#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# semear_reprovados.py -- a evidência já foi paga; falta guardá-la
#
# POR QUE ISTO EXISTE (09/09/2026)
# ────────────────────────────────
# O `_produto_queimado` (tiktok_coletor) para de pagar o juiz de imagem pelo
# MESMO produto da loja depois de N reprovações. Mas ele nasce com o cache
# VAZIO — então a próxima rodada vai pagar 3 vezes por cada produto queimado
# antes de aprender o que eu JÁ SEI.
#
# 📌 E EU JÁ SEI. O `reprovado_match/` tem 119 pacotes que o juiz reprovou nas
# auditorias de 08/09 (76 + 37 + 6). Cada um daqueles "não" foi pago uma vez.
# Deixá-los apodrecendo numa pasta e pagar de novo pela mesma resposta é o
# mesmo defeito do dedup que este guarda veio consertar: **lembrar dos acertos
# e esquecer dos erros**.
#
# ⚠️ SÓ LÊ. Nada aqui escreve DENTRO das pastas dos pacotes — foi assim que eu
# rejuvenesci a fila duas vezes em 48h (41 pacotes em 06/09, 185 em 08/09).
# O único arquivo escrito é `shared/produtos_reprovados.json`.
#
# ⚠️ O CARIMBO DE TEMPO É O DA REPROVAÇÃO, NÃO O DE AGORA. Se eu usasse
# `time.time()`, as 119 contas expirariam todas juntas daqui a 30 dias, num
# bloco — e o laço voltaria inteiro no mesmo dia. Uso o mtime da pasta, que é
# quando ela foi movida pra `reprovado_match/`, ou seja, quando o juiz decidiu.
#
# ⚠️ E O NORMALIZADOR É IMPORTADO, NUNCA COPIADO. Se eu copiasse o
# `_norm_produto` pra cá, uma mudança nele faria o semeador gravar chaves que o
# coletor nunca leria — cache cheio e guarda inerte, sem erro nenhum no log.
#
#   .venv/bin/python semear_reprovados.py            # só mostra
#   .venv/bin/python semear_reprovados.py --aplicar  # grava o cache
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPROVADOS = BASE / "reprovado_match"

# importado do coletor: mesma chave, mesmo arquivo, mesma leitura
from tiktok_coletor import (PRODUTOS_REPROVADOS, _carregar_reprovados,
                            _norm_produto, _produto_queimado,
                            _salvar_reprovados)


def _nome_do_produto(pasta: Path) -> str:
    """O nome do produto da loja, venha de onde vier.

    Os pacotes em `reprovado_match/` chegaram por dois caminhos e guardam
    arquivos diferentes: os de `inbox_tiktok` têm `plano.json`; os que vieram
    de `pronto_para_postar` (o modo `--fila`) têm `engajamento.json`. Os dois
    usam o mesmo campo `produto`.
    """
    for nome in ("plano.json", "engajamento.json"):
        arq = pasta / nome
        if not arq.exists():
            continue
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
        except Exception:
            continue
        p = (d.get("produto") or "").strip()
        if p:
            return p
    return ""


def main() -> int:
    aplicar = "--aplicar" in sys.argv[1:]
    if not REPROVADOS.exists():
        print(f"❌ {REPROVADOS} não existe — nada reprovado ainda")
        return 1

    contas = defaultdict(lambda: {"n": 0, "ts": 0, "exemplo": ""})
    pastas = sem_nome = 0
    for pasta in sorted(REPROVADOS.iterdir()):
        if not pasta.is_dir():
            continue
        pastas += 1
        nome = _nome_do_produto(pasta)
        if not nome:
            sem_nome += 1
            continue
        chave = _norm_produto(nome)
        if not chave:
            sem_nome += 1
            continue
        reg = contas[chave]
        reg["n"] += 1
        # o mtime da pasta é quando ela foi MOVIDA pra cá = quando o juiz decidiu
        reg["ts"] = max(reg["ts"], int(pasta.stat().st_mtime))
        reg["exemplo"] = reg["exemplo"] or nome

    try:
        limite = int(os.getenv("MATCH_MAX_REPROVA", "3"))
    except ValueError:
        limite = 3

    print(f"\n📦 {pastas} pacote(s) em reprovado_match/ · "
          f"{sem_nome} sem nome de produto legível")
    print(f"🔑 {len(contas)} produto(s) distinto(s) · "
          f"limite atual MATCH_MAX_REPROVA={limite}\n")
    if not contas:
        print("✅ nada a semear")
        return 0

    ordem = sorted(contas.items(), key=lambda kv: -kv[1]["n"])
    queimados = [(k, v) for k, v in ordem if v["n"] >= limite]

    print(f"{'n':>3}  produto")
    for chave, reg in ordem[:15]:
        marca = "🔁" if reg["n"] >= limite else "  "
        print(f"{reg['n']:3d} {marca} {reg['exemplo'][:56]}")
    if len(ordem) > 15:
        print(f"      … e mais {len(ordem)-15}")

    print(f"\n🔁 {len(queimados)} produto(s) já passam do limite — estes o "
          f"coletor pula\n   sem julgar na próxima rodada.")
    # ⚠️ o resto NÃO é desperdício: a conta parcial fica gravada, e a próxima
    # reprovação do mesmo produto completa o limite em vez de recomeçar do zero.
    print(f"   (os outros {len(ordem)-len(queimados)} entram com a conta "
          f"parcial — a próxima reprovação\n   completa em vez de recomeçar.)")

    if not aplicar:
        print(f"\n   (nada foi gravado — use --aplicar)")
        return 0

    # ⚠️ FUNDE COM O QUE JÁ EXISTE, não sobrescreve. Se uma rodada já rodou com
    # o guarda ligado, o cache dela tem contas que este semeador não conhece —
    # e sobrescrever apagaria evidência mais nova que a minha.
    pr = _carregar_reprovados()
    novos = somados = 0
    for chave, reg in contas.items():
        antigo = pr.get(chave)
        if isinstance(antigo, dict):
            try:
                n_ant = int(antigo.get("n", 0))
                ts_ant = int(antigo.get("ts", 0))
            except (TypeError, ValueError):
                n_ant = ts_ant = 0
            pr[chave] = {"n": n_ant + reg["n"], "ts": max(ts_ant, reg["ts"])}
            somados += 1
        else:
            pr[chave] = {"n": reg["n"], "ts": reg["ts"]}
            novos += 1
    _salvar_reprovados(pr)

    agora_queimados = sum(1 for k in pr if _produto_queimado(k, pr, limite=limite))
    print(f"\n   ✅ {PRODUTOS_REPROVADOS.name}: {novos} produto(s) novo(s), "
          f"{somados} somado(s) ao que já havia")
    print(f"   🔁 {agora_queimados} produto(s) queimado(s) no cache — "
          f"o coletor não paga mais o juiz por eles")
    print(f"   (a conta expira em MATCH_REPROVA_DIAS="
          f"{os.getenv('MATCH_REPROVA_DIAS', '30')} dias, contada da reprovação)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
