#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# limpar_esteira.py — TIRA DA ESTEIRA O QUE NÃO VAI MAIS AO AR.
#
# ⚠️ DECISÃO DO DRE (25/08), e ela é de conteúdo, não de disco: "não quero
# produtos tão antigos assim, nós fizemos muitas mudanças, no gancho, formato,
# e vídeos antigos podem estragar nosso algoritmo, vamos focar no presente e
# esquecer esses pacotes".
#
# Isso importa pra ferramenta: o critério NÃO é espaço em disco, é idade do
# material. Um pacote de 27 dias foi montado com o gancho velho, o formato
# velho e a capa velha. Postar ele hoje não é aproveitar estoque — é publicar
# uma versão antiga do projeto num perfil que está sendo medido.
#
# ⚠️ E ELE NÃO APAGA. Move pra `fila_vencida/`, que é exatamente pra onde o
# `_expurgar_vencidos()` do daemon já move — mesma pasta, mesma convenção. Se
# eu inventasse um destino novo, passariam a existir dois lugares com o mesmo
# significado e o próximo a olhar não saberia qual é o de verdade. Apagar de
# vez continua sendo uma decisão humana, tomada depois de olhar o que saiu.
#
# ⚠️ MISTÉRIO QUE ELE TAMBÉM MEDE: o expurgo do daemon roda a cada ciclo de
# postagem e MESMO ASSIM havia pacotes de 27 dias na esteira com validade de 7.
# Ou ele não está rodando, ou está falhando calado (o `shutil.move` dele só
# loga warning). Por isso aqui cada falha é contada e mostrada — se a limpeza
# manual falhar nos mesmos, achamos a causa junto.
#
# USO (na VPS):
#   .venv/bin/python limpar_esteira.py                # SÓ MOSTRA (padrão)
#   .venv/bin/python limpar_esteira.py --dias 7       # muda o corte de idade
#   .venv/bin/python limpar_esteira.py --aplicar      # move de verdade

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRONTO = BASE / "pronto_para_postar"
VENCIDA = BASE / "fila_vencida"
HIST = BASE / "shared" / "content_plans" / "agendador_historico.json"
CONFIG = BASE / "shared" / "content_plans" / "agendador_config.json"


def _json(caminho: Path, padrao):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except Exception:
        return padrao


def _tamanho(pasta: Path) -> int:
    """Bytes do pacote. Só um nível — o vídeo é 99% do peso e varrer recursivo
    centenas de pastas custa mais do que a precisão vale."""
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


def levantar(dias: int) -> tuple:
    """(mortos, vivos) — mortos = já postado OU mais velho que `dias`.

    ⚠️ As duas razões andam juntas mas NÃO são a mesma coisa, e o relatório
    separa: "postado" é pacote que cumpriu sua função e virou lixo natural;
    "velho" é pacote que nunca foi ao ar e perdeu a validade esperando. O
    segundo é desperdício de produção, o primeiro não. Somar os dois num número
    só esconderia exatamente a métrica que interessa acompanhar."""
    postados = set((_json(HIST, {}) or {}).get("postados") or [])
    agora = time.time()
    mortos, vivos = [], []
    if not PRONTO.is_dir():
        return mortos, vivos

    for p in sorted(PRONTO.iterdir()):
        if not (p.is_dir() and (p / "video.mp4").exists()):
            continue
        idade = (agora - p.stat().st_mtime) / 86400
        if p.name in postados:
            razao = "postado"
        elif dias > 0 and idade >= dias:
            razao = "velho"
        else:
            vivos.append((idade, p))
            continue
        mortos.append((idade, p, razao))
    return mortos, vivos


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Tira da esteira o que não vai ao ar.")
    ap.add_argument("--dias", type=int, default=None,
                    help="corte de idade (padrão: fila_validade_dias da config, ou 7)")
    ap.add_argument("--aplicar", action="store_true",
                    help="move de verdade pra fila_vencida/ (sem isto, só mostra)")
    a = ap.parse_args(argv)

    cfg = _json(CONFIG, {}) or {}
    dias = a.dias if a.dias is not None else int(cfg.get("fila_validade_dias", 7) or 7)

    mortos, vivos = levantar(dias)
    if not PRONTO.is_dir():
        print(f"❌ {PRONTO} não existe — nada a limpar.")
        return 2

    peso = sum(_tamanho(p) for _i, p, _r in mortos)
    postado = sum(1 for _i, _p, r in mortos if r == "postado")
    velho = len(mortos) - postado

    print(f"\n🧹 esteira: {len(mortos) + len(vivos)} pacote(s)  ·  corte de {dias} dias\n")
    print(f"   ✅ {len(vivos):>4} vivo(s) — ficam")
    print(f"   🗑️  {postado:>4} já postado(s)")
    print(f"   ⏳ {velho:>4} nunca postado(s) e além de {dias}d  ← produção desperdiçada")
    print(f"   💾 {_gb(peso)} em pacotes mortos\n")

    if mortos:
        print("   os 5 mais velhos:")
        for idade, p, razao in sorted(mortos, reverse=True, key=lambda x: x[0])[:5]:
            print(f"      {idade:>5.0f}d  [{razao:<7}] {p.name[:52]}")
        print()

    if not a.aplicar:
        # ⚠️ o padrão é NÃO mexer. Mover centenas de pastas de produção é
        # irreversível na prática (dá pra voltar, mas ninguém volta), e este
        # script existe justamente porque a esteira já surpreendeu três vezes.
        print("   🧪 nada foi movido. Confira os números e rode de novo com "
              "--aplicar.\n")
        return 0

    movidos, falhas = 0, []
    VENCIDA.mkdir(parents=True, exist_ok=True)
    for _idade, p, _razao in mortos:
        alvo = VENCIDA / p.name
        try:
            if alvo.exists():
                # nome repetido não pode virar exceção silenciosa nem
                # sobrescrever: o pacote antigo em fila_vencida também é prova.
                alvo = VENCIDA / f"{p.name}__{int(time.time())}"
            shutil.move(str(p), str(alvo))
            movidos += 1
        except Exception as erro:
            falhas.append((p.name, str(erro)[:90]))

    print(f"   ✅ {movidos} pacote(s) → fila_vencida/  ({_gb(peso)} liberados "
          f"da esteira)")
    if falhas:
        # ⚠️ ISTO É O ACHADO, NÃO O RUÍDO. O expurgo do daemon só loga warning
        # quando o move falha, e é candidato a explicar por que pacote de 27
        # dias continuava na esteira com validade de 7.
        print(f"\n   ⚠️  {len(falhas)} falha(s) ao mover — mesma operação que o "
              f"`_expurgar_vencidos()` do daemon faz calado:")
        for nome, erro in falhas[:5]:
            print(f"      {nome[:40]}: {erro}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
