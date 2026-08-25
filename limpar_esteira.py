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
# ⚠️ E O QUE O DAEMON JÁ FAZ SOZINHO, ELE FAZ: o log mostrou `8 pacote(s) além
# de 27 dias → fila_vencida/`. O expurgo funciona. O que ninguém faz é limpar
# pacote JÁ POSTADO — o `_expurgar_vencidos()` filtra por idade, não por já ter
# cumprido a função, então o postado fica ocupando disco até envelhecer 27 dias.
# Eram 206 assim. É esse o buraco que esta ferramenta fecha.
#
# ⚠️ E O CORTE EDITORIAL É OPT-IN, POR ISSO O `--dias`. Tirar material que o
# daemon ainda considera bom é decisão de conteúdo, não manutenção. Ela tem que
# ser digitada, nunca herdada de um default — foi assumindo um default meu que
# eu quase apresentei 184 pacotes vivos como lixo.
#
# USO (na VPS):
#   .venv/bin/python limpar_esteira.py                # SÓ MOSTRA (padrão)
#   .venv/bin/python limpar_esteira.py --dias 7       # + corte editorial de 7d
#   .venv/bin/python limpar_esteira.py --dias 7 --aplicar

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


def validade_real() -> int:
    """Os dias de validade que o DAEMON usa. Não é o que está no arquivo.

    ⚠️ ISTO QUASE CUSTOU 184 PACOTES BONS (25/08). Eu lia o
    `agendador_config.json` e, não achando `fila_validade_dias`, aplicava 7.
    Mas `carregar_config()` mescla o arquivo por cima de `DEFAULTS`, e lá a
    chave vale **27**. O log do daemon dizia `8 pacote(s) além de 27 dias →
    fila_vencida/` enquanto meu relatório chamava de morto tudo acima de 7.

    Com o corte errado, o `--aplicar` teria tirado da esteira 184 pacotes que
    o daemon considera perfeitamente postáveis.

    📌 Default inventado é pior que default ausente: o ausente dá erro, o
    inventado dá um número plausível e errado — e aqui o número plausível
    autorizava uma operação irreversível."""
    for mod in ("agents.daemon_maestro", "daemon_maestro"):
        try:
            import importlib
            return int(importlib.import_module(mod)._validade_dias())
        except Exception:
            continue
    return 0        # 0 = não sei. Quem chama TEM que tratar, não assumir.


def levantar(validade: int, corte: int) -> tuple:
    """(postados, vencidos, velhos, vivos) — quatro montes, não dois.

    ⚠️ SÃO QUATRO PORQUE AS RAZÕES PEDEM CONVERSAS DIFERENTES:

      postado   cumpriu a função e virou lixo natural. Ninguém limpa isso hoje:
                o `_expurgar_vencidos()` filtra por IDADE, não por já ter ido
                ao ar, então o pacote postado só sai quando envelhece.
      vencido   passou da validade do daemon ({validade}d) sem nunca ir ao ar.
                Isto é produção desperdiçada, e é a métrica a acompanhar.
      velho     VIVO pro daemon, mas além do corte editorial que o Dre pediu.
                Não é lixo do sistema: é decisão de conteúdo — material montado
                com gancho e formato antigos.
      vivo      fica.

    Juntar "vencido" e "velho" num só monte é o que teria me feito apresentar
    184 pacotes bons como lixo. Separados, o Dre decide o segundo monte sabendo
    que está decidindo, e não achando que está confirmando um diagnóstico."""
    postados_hist = set((_json(HIST, {}) or {}).get("postados") or [])
    agora = time.time()
    postados, vencidos, velhos, vivos = [], [], [], []
    if not PRONTO.is_dir():
        return postados, vencidos, velhos, vivos

    for p in sorted(PRONTO.iterdir()):
        if not (p.is_dir() and (p / "video.mp4").exists()):
            continue
        idade = (agora - p.stat().st_mtime) / 86400
        if p.name in postados_hist:
            postados.append((idade, p))
        elif validade > 0 and idade >= validade:
            vencidos.append((idade, p))
        elif corte > 0 and idade >= corte:
            velhos.append((idade, p))
        else:
            vivos.append((idade, p))
    return postados, vencidos, velhos, vivos


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Tira da esteira o que não vai ao ar.")
    ap.add_argument("--dias", type=int, default=0,
                    help="CORTE EDITORIAL: também tira o que passa desta idade, "
                         "mesmo estando vivo pro daemon (ex.: --dias 7)")
    ap.add_argument("--aplicar", action="store_true",
                    help="move de verdade pra fila_vencida/ (sem isto, só mostra)")
    a = ap.parse_args(argv)

    if not PRONTO.is_dir():
        print(f"❌ {PRONTO} não existe — nada a limpar.")
        return 2

    validade = validade_real()
    if not validade:
        # ⚠️ Sem saber a validade do daemon eu NÃO chuto uma. Chutar aqui move
        # pasta de produção com base num número inventado.
        print("\n❌ não consegui ler a validade do daemon "
              "(`daemon_maestro._validade_dias()`).\n   Rode na VPS, da raiz do "
              "projeto. Não vou adivinhar um corte pra mover pastas.\n")
        return 2

    postados, vencidos, velhos, vivos = levantar(validade, a.dias)
    total = len(postados) + len(vencidos) + len(velhos) + len(vivos)
    alvo = postados + vencidos + velhos

    print(f"\n🧹 esteira: {total} pacote(s)  ·  validade do daemon: {validade}d"
          + (f"  ·  corte editorial: {a.dias}d" if a.dias else "") + "\n")
    print(f"   ✅ {len(vivos):>4} vivo(s) — ficam")
    print(f"   🗑️  {len(postados):>4} já postado(s) — ninguém limpa isso hoje")
    print(f"   ⏳ {len(vencidos):>4} venceram sem ir ao ar (>{validade}d)"
          f"  ← produção desperdiçada")
    if a.dias:
        print(f"   ✂️  {len(velhos):>4} vivos pro daemon, mas além de {a.dias}d"
              f"  ← DECISÃO DE CONTEÚDO, não lixo do sistema")
    elif validade > 7:
        # ⚠️ o Dre pediu material recente; sem --dias esta ferramenta NÃO faz
        # esse corte. Dizer isso é o que impede que ele leia "44 vivos" e ache
        # que o resto todo é lixo, como eu apresentei antes.
        print(f"\n   ℹ️  sem --dias, tudo abaixo de {validade}d conta como vivo. "
              f"Pra tirar material antigo por decisão editorial, use --dias N.")
    print(f"\n   💾 {_gb(sum(_tamanho(p) for _i, p in alvo))} nos "
          f"{len(alvo)} pacote(s) que sairiam\n")

    if alvo:
        print("   os 5 mais velhos que sairiam:")
        marca = ({id(p): "postado" for _i, p in postados}
                 | {id(p): "vencido" for _i, p in vencidos}
                 | {id(p): "editorial" for _i, p in velhos})
        for idade, p in sorted(alvo, reverse=True, key=lambda x: x[0])[:5]:
            print(f"      {idade:>5.0f}d  [{marca[id(p)]:<9}] {p.name[:52]}")
        print()
    mortos = [(i, p, marca[id(p)]) for i, p in alvo] if alvo else []

    if not a.aplicar:
        # ⚠️ o padrão é NÃO mexer. Mover centenas de pastas de produção é
        # irreversível na prática (dá pra voltar, mas ninguém volta), e este
        # script existe justamente porque a esteira já surpreendeu três vezes.
        print("   🧪 nada foi movido. Confira os números e rode de novo com "
              "--aplicar.\n")
        return 0

    peso = sum(_tamanho(p) for _i, p in alvo)
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
