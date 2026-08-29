#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_carrossel_daemon.py - liga o ciclo do CARROSSEL no daemon_maestro.
#
# ⚠️ APOSENTADO EM 29/08 — A CHAMADA AGORA NASCE NO `daemon_maestro.py`.
# Este script injetava as 4 linhas em `agents/daemon_maestro.py`, que e
# EXATAMENTE o arquivo que o deploy sobrescreve. Cada deploy apagava o patch, e
# o carrossel parava sem log nenhum: o codigo nao existia mais pra falhar. Ele
# continua idempotente (nao duplica nada se voce rodar), mas nao ha mais o que
# aplicar. Mantido so pelo `--desfazer`, pros .bak antigos.
# 📌 Patch aplicado no destino do deploy e patch com data de validade.
#
# TRES LINHAS, e e de proposito: o daemon_maestro posta em 6 contas, todo dia,
# ha meses. Toda a logica do carrossel mora no `carrossel_agendador.py`; aqui a
# gente so acrescenta a chamada, dentro de um try/except. Se o modulo novo
# explodir, os Reels continuam saindo como sempre — que e a unica coisa que nao
# pode parar.
#
# O ciclo nasce DESLIGADO. Depois do patch, ligue quando quiser:
#   "carrossel_ligado": true   no agendador_config.json
#
# IDEMPOTENTE. Backup, py_compile antes de gravar, e --desfazer.
#
# USO (na raiz do jarvis):
#   python3 patch_carrossel_daemon.py            # aplica
#   python3 patch_carrossel_daemon.py --conferir # so diz o que faria
#   python3 patch_carrossel_daemon.py --desfazer # volta o .bak

import sys
import shutil
import py_compile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CANDIDATOS = ["agents/daemon_maestro.py", "daemon_maestro.py"]

MARCA = "carrossel_agendador"
ANCORA = '''    # 3) POSTAGEM (nos horários)
    if so in ("", "postar"):
        resumo["postagem"] = ciclo_postagem(cfg, hist, dry_run)'''

NOVO = ANCORA + '''

    # 4) CARROSSEL (horários próprios, fora dos slots do Reel)
    if so in ("", "postar", "carrossel"):
        try:
            import carrossel_agendador
            resumo["carrossel"] = carrossel_agendador.ciclo(cfg, dry_run)
        except Exception as e:
            log.warning(f"   ⚠️  ciclo do carrossel pulado: {str(e)[:100]}")'''


def _alvo() -> Path:
    for c in CANDIDATOS:
        p = RAIZ / c
        if p.exists():
            return p
    print("[x] nao achei o daemon_maestro.py")
    sys.exit(1)


def main() -> int:
    args = set(sys.argv[1:])
    alvo = _alvo()
    print(f"[alvo] {alvo}")
    bak = alvo.with_suffix(".py.bak-carrossel")

    if "--desfazer" in args:
        if not bak.exists():
            print(f"[x] nao existe {bak}")
            return 1
        shutil.copy2(bak, alvo)
        print("[<-] restaurado. Rode: systemctl restart jarvis.service")
        return 0

    texto = alvo.read_text(encoding="utf-8")
    if MARCA in texto:
        print("[ok] o ciclo do carrossel JA esta ligado - nada a fazer.")
        return 0
    if ANCORA not in texto:
        print("[x] nao achei o bloco da POSTAGEM em rodar_um_ciclo().")
        print("    O daemon da VPS diverge do repo. Me mande:")
        print(f"      grep -n 'ciclo_postagem(cfg, hist, dry_run)' {alvo}")
        return 1

    novo = texto.replace(ANCORA, NOVO, 1)
    print("[pos] acrescentando o ciclo 4 (carrossel) apos a postagem")
    if "--conferir" in args:
        print("\n[teste] nada foi gravado.")
        return 0

    temp = alvo.with_suffix(".py.novo")
    temp.write_text(novo, encoding="utf-8")
    try:
        py_compile.compile(str(temp), doraise=True)
    except py_compile.PyCompileError as e:
        temp.unlink()
        print(f"[x] nao compila - NADA foi alterado:\n{e}")
        return 1

    shutil.copy2(alvo, bak)
    temp.replace(alvo)
    print(f"[bak] {bak.name}")
    print(f"[ok] {alvo} patchado.")
    print("\n     Agora:  systemctl restart jarvis.service")
    print("     O ciclo nasce DESLIGADO. Pra ligar, no agendador_config.json:")
    print('       "carrossel_ligado": true')
    print("     Confira a agenda:  python3 carrossel_agendador.py --agenda")
    return 0


if __name__ == "__main__":
    sys.exit(main())
