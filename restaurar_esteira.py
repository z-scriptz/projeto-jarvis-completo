#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# restaurar_esteira.py — DEVOLVE PRA ESTEIRA O QUE FOI TIRADO INDEVIDAMENTE.
#
# ⚠️ ELE EXISTE PORQUE EU ERREI (25/08). O `limpar_esteira.py` na sua primeira
# versão lia o `agendador_config.json` cru, não achava `fila_validade_dias` e
# aplicava um default MEU de 7 dias — enquanto o `DEFAULTS` do daemon diz 27.
# Com esse corte, o `--aplicar` mandou pra `fila_vencida/` 184 pacotes que o
# daemon considerava perfeitamente postáveis, junto dos 206 que já tinham ido
# ao ar. 410 pastas, 5,1 GB.
#
# O `shutil.move` dentro do mesmo sistema de arquivos é um rename: **o mtime
# foi preservado**. É isso que torna a volta possível e honesta — a idade de
# cada pacote continua sendo a idade real, não a hora em que eu o movi. Se o
# mtime tivesse sido reescrito, todo pacote voltaria "novo" e a validade do
# daemon passaria a mentir por mais 27 dias.
#
# ⚠️ O QUE ELE NÃO DEVOLVE, e o motivo importa:
#
#   já postado    cumpriu a função. Devolver isso reenche a esteira de material
#                 que o daemon vai ignorar (`_prontos_nao_postados` filtra por
#                 `postados`) e desfaz a única parte da limpeza que era certa.
#   > validade    o daemon já o descartaria no primeiro ciclo. Voltaria só pra
#                 ser expurgado de novo — barulho, não recuperação.
#
# Sobra exatamente o que foi levado por engano: não postado e dentro da
# validade real.
#
# USO (na VPS):
#   .venv/bin/python restaurar_esteira.py             # SÓ MOSTRA (padrão)
#   .venv/bin/python restaurar_esteira.py --aplicar   # devolve de verdade

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRONTO = BASE / "pronto_para_postar"
VENCIDA = BASE / "fila_vencida"
HIST = BASE / "shared" / "content_plans" / "agendador_historico.json"

# sufixo que o limpar_esteira acrescenta quando o nome já existia no destino
_SUFIXO = re.compile(r"__\d{9,}$")


def _json(caminho: Path, padrao):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except Exception:
        return padrao


def _tamanho(pasta: Path) -> int:
    total = 0
    try:
        for f in pasta.iterdir():
            if f.is_file():
                total += f.stat().st_size
    except Exception:
        pass
    return total


def _gb(n: int) -> str:
    return f"{n / 1024**3:.2f} GB" if n >= 1024**3 else f"{n / 1024**2:.0f} MB"


def validade_real() -> int:
    """A validade do DAEMON. Mesma função que ele usa, não um default meu.

    ⚠️ Foi exatamente inventar um default aqui que criou a necessidade deste
    arquivo. Sem conseguir ler, ele PARA — não adivinha um número pra mover
    pastas de produção."""
    for mod in ("agents.daemon_maestro", "daemon_maestro"):
        try:
            import importlib
            return int(importlib.import_module(mod)._validade_dias())
        except Exception:
            continue
    return 0


def levantar(validade: int) -> tuple:
    """(devolver, postados, velhos) — o que volta e o que fica, com o porquê."""
    postados_hist = set((_json(HIST, {}) or {}).get("postados") or [])
    agora = time.time()
    devolver, postados, velhos = [], [], []
    if not VENCIDA.is_dir():
        return devolver, postados, velhos

    for p in sorted(VENCIDA.iterdir()):
        if not (p.is_dir() and (p / "video.mp4").exists()):
            continue
        # ⚠️ o nome no histórico é o ORIGINAL; se o limpar_esteira teve que
        # desambiguar com sufixo, comparar o nome da pasta erraria e o pacote
        # postado voltaria como se nunca tivesse ido ao ar.
        original = _SUFIXO.sub("", p.name)
        idade = (agora - p.stat().st_mtime) / 86400
        if original in postados_hist:
            postados.append((idade, p))
        elif validade > 0 and idade >= validade:
            velhos.append((idade, p))
        else:
            devolver.append((idade, p, original))
    return devolver, postados, velhos


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Devolve pra esteira o que foi tirado indevidamente.")
    ap.add_argument("--aplicar", action="store_true",
                    help="move de verdade de volta (sem isto, só mostra)")
    a = ap.parse_args(argv)

    if not VENCIDA.is_dir():
        print(f"\n❌ {VENCIDA} não existe — nada a restaurar.\n")
        return 2

    validade = validade_real()
    if not validade:
        print("\n❌ não consegui ler a validade do daemon "
              "(`daemon_maestro._validade_dias()`).\n   Rode na VPS, da raiz do "
              "projeto. Não vou adivinhar pra mover pastas.\n")
        return 2

    devolver, postados, velhos = levantar(validade)
    total = len(devolver) + len(postados) + len(velhos)
    peso = sum(_tamanho(p) for _i, p, _o in devolver)

    print(f"\n♻️  fila_vencida: {total} pacote(s)  ·  validade do daemon: "
          f"{validade}d\n")
    print(f"   ↩️  {len(devolver):>4} VOLTAM — não postados e dentro da validade")
    print(f"   🗑️  {len(postados):>4} ficam — já foram ao ar")
    print(f"   ⏳ {len(velhos):>4} ficam — passaram dos {validade}d de verdade")
    print(f"\n   💾 {_gb(peso)} voltando pra esteira\n")

    if devolver:
        idades = [i for i, _p, _o in devolver]
        print(f"   idade do que volta: {min(idades):.0f}d a {max(idades):.0f}d "
              f"(mediana {sorted(idades)[len(idades)//2]:.0f}d)")
        print("   os 5 mais velhos que voltam:")
        for idade, p, _o in sorted(devolver, reverse=True, key=lambda x: x[0])[:5]:
            print(f"      {idade:>5.0f}d  {p.name[:56]}")
        print()

    if not a.aplicar:
        print("   🧪 nada foi movido. Confira e rode de novo com --aplicar.\n")
        return 0

    PRONTO.mkdir(parents=True, exist_ok=True)
    voltaram, falhas, pulados = 0, [], 0
    for _idade, p, original in devolver:
        alvo = PRONTO / original
        if alvo.exists():
            # ⚠️ já existe um pacote com esse nome na esteira: o certo é NÃO
            # tocar. Sobrescrever trocaria um pacote vivo por uma cópia antiga.
            pulados += 1
            continue
        try:
            shutil.move(str(p), str(alvo))
            voltaram += 1
        except Exception as erro:
            falhas.append((p.name, str(erro)[:90]))

    print(f"   ✅ {voltaram} pacote(s) de volta em pronto_para_postar/")
    if pulados:
        print(f"   ⏭️  {pulados} pulado(s): já existe pacote com esse nome na "
              f"esteira (não sobrescrevi)")
    if falhas:
        print(f"\n   ⚠️  {len(falhas)} falha(s):")
        for nome, erro in falhas[:5]:
            print(f"      {nome[:40]}: {erro}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
