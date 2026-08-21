#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_legenda_verifica.py -- confere a legenda DEPOIS de publicar, no ar.
#
# POR QUE EXISTE (21/08)
# ─────────────────────
# O @topshopcasa_ publicou 2 Reels recentes SEM legenda. O log prova que a
# legenda foi enviada:
#
#     09:14  🎯 conta ativa: @topshopcasa_
#     09:14  📝 legenda p/ Instagram: 821 caractere(s)
#     13:04  📝 legenda p/ Instagram: 824 caractere(s)
#     18:40  📝 legenda p/ Instagram: 726 caractere(s)
#
# E as outras 3 contas, com o MESMO código e o mesmo formato de legenda,
# saíram certas. Então: mandamos, a Meta aceitou o container e publicou sem.
# Não sei ainda por quê — e é justamente por isso que este patch NÃO tenta
# adivinhar nem corrigir.
#
# ⚠️ O QUE ELE FAZ É TROCAR O ATRASO DA DESCOBERTA.
# Hoje a falha aparece quando alguém abre o Instagram e olha — foram DIAS até
# o vigia apontar, e mais um dia até acreditarmos nele. Depois deste patch ela
# aparece 3 segundos depois de publicar, com o container_id em mãos e um aviso
# no Telegram. É a diferença entre um mistério e um chamado.
#
# Também é o que vai permitir descobrir a causa: com o aviso na hora, dá pra
# comparar o container que deu certo com o que deu errado, no mesmo dia.
#
# ⚠️ PATCH CIRÚRGICO porque o `agents/meta_uploader.py` está DIVERGENTE — o
# deploy inteiro foi recusado e sobrescrever apagaria o que foi editado só na
# VPS. Idempotente: rodar duas vezes não duplica.
#
# Uso (VPS):
#   python3 patch_legenda_verifica.py --ver     # mostra o que faria
#   python3 patch_legenda_verifica.py           # aplica, com backup

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
ALVO = BASE / "agents" / "meta_uploader.py"

MARCA = "# [patch_legenda_verifica]"

ANCORA = """    media_id = d4.get("id")
    if media_id:"""

ENXERTO = '''    media_id = d4.get("id")
    if media_id:
        {marca} confere a legenda NO AR, 3s depois de publicar.
        # O Reel sai sem legenda mesmo tendo sido enviada (medido no
        # @topshopcasa_ em 20/08: 821, 824 e 726 caracteres mandados, Reels
        # publicados vazios). Sem esta checagem a falha só aparece quando
        # alguém abre o app — foram dias. Aqui ela aparece na hora, com o
        # container em mãos, que é o que vai permitir achar a causa.
        try:
            if (legenda or "").strip():
                time.sleep(3)
                _rv = _req().get(
                    f"{{GRAPH}}/{{media_id}}",
                    params={{"fields": "caption", "access_token": tok}},
                    timeout=30,
                )
                _cap = ((_rv.json() or {{}}).get("caption") or "").strip()
                if not _cap:
                    # ⚠️ log.error e SÓ. Eu ia mandar Telegram daqui e o
                    # `_avisar_telegram` não existe neste módulo — o import
                    # falharia dentro do try e o aviso nunca sairia, fingindo
                    # que alguém foi avisado. O ERROR aqui já é colhido pelo
                    # bloco de logs da revisao_geral e pelo vigia, que são
                    # quem tem a via do Telegram de verdade.
                    log.error(
                        f"   ❌ LEGENDA SUMIU [{{_CTX.get('handle') or '?'}}]: "
                        f"mandei {{len(legenda.strip())}} caractere(s) e o Reel "
                        f"publicado está SEM legenda. "
                        f"container={{container_id}} media={{media_id}}")
                else:
                    log.info(f"   ✔️ legenda confirmada no ar "
                             f"({{len(_cap)}} caractere(s))")
        except Exception as _e:
            # checagem nunca derruba a publicação: o post já saiu
            log.warning(f"   (não consegui conferir a legenda no ar: {{str(_e)[:60]}})")
'''.format(marca=MARCA)


def _log(m):
    print(f"[patch] {m}", flush=True)


def main():
    p = argparse.ArgumentParser(
        description="Confere a legenda depois de publicar. Cirúrgico e idempotente.")
    p.add_argument("--ver", action="store_true", help="mostra sem escrever")
    args = p.parse_args()

    if not ALVO.exists():
        _log(f"não achei {ALVO} — está rodando de dentro de ~/jarvis?")
        return 1
    texto = ALVO.read_text(encoding="utf-8")

    if MARCA in texto:
        _log("já aplicado — nada a fazer (idempotente)")
        return 0
    if texto.count(ANCORA) != 1:
        # ⚠️ não adivinho lugar. Âncora ambígua = arquivo diferente do que eu
        # li, e enxertar no lugar errado quebra a publicação inteira.
        _log(f"a âncora aparece {texto.count(ANCORA)}x (esperava 1) — NÃO mexo")
        _log("   o arquivo da VPS diverge do que eu conheço; me mande:")
        _log("   grep -n 'media_id = d4.get' agents/meta_uploader.py")
        return 1
    if "import time" not in texto:
        _log("o arquivo não importa `time` — NÃO mexo (o enxerto usa sleep)")
        return 1

    _log("âncora encontrada, 1 ocorrência ✓")
    _log("vou inserir a checagem logo após o publish:")
    for l in ENXERTO.splitlines()[1:8]:
        _log(f"   {l}")
    _log("   …")

    if args.ver:
        _log("(--ver: não escrevi nada)")
        return 0

    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ALVO.with_suffix(f".py.bak_{carimbo}")
    shutil.copy2(ALVO, backup)
    ALVO.write_text(texto.replace(ANCORA, ENXERTO.rstrip("\n"), 1), encoding="utf-8")

    import py_compile
    try:
        py_compile.compile(str(ALVO), doraise=True)
    except Exception as e:
        shutil.copy2(backup, ALVO)
        _log(f"❌ o arquivo não compilou ({str(e)[:80]}) — DESFIZ, nada mudou")
        return 1

    _log(f"✅ aplicado · backup: {backup.name}")
    _log("   reinicie o serviço:  systemctl restart jarvis.service")
    return 0


if __name__ == "__main__":
    sys.exit(main())
