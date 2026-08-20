#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_fontes_ig.py -- ACRESCENTA perfis do IG sem apagar o que já está lá.
#
# POR QUE EXISTE (19/08)
# ──────────────────────
# O `deploy_seguro.py` recusou o `instagram_perfis.txt`:
#
#     ⛔ instagram_perfis.txt: DIVERGENTE
#        o repo acompanha este arquivo (4 commits), mas o conteúdo da VPS não
#        bate com nenhum. Alguém editou de um lado só.
#
# E ele está certo em recusar. Sobrescrever com a versão do repo apagaria os
# perfis que foram adicionados direto na VPS — fontes que estão coletando hoje
# e que ninguém lembraria de repor. O `--forcar` aqui custaria caro e calado:
# o coletor simplesmente passaria a visitar menos perfis, e o efeito (menos
# vídeo, menos pacote) só apareceria dias depois, longe da causa.
#
# ⚠️ ESTE ARQUIVO SÓ ACRESCENTA. Não apaga linha, não reordena, não reescreve
# comentário, não mexe em perfil existente. Se um perfil já está no arquivo —
# com @, sem @, em maiúscula, comentado ou não — ele é PULADO.
#
# É idempotente: rodar duas vezes não duplica nada.
#
# Uso (VPS):
#   python3 patch_fontes_ig.py --ver      # só mostra o que faria
#   python3 patch_fontes_ig.py            # aplica (com backup)

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
ARQUIVO = BASE / "instagram_perfis.txt"

# Os 18 que o Dre mandou em 19/08, pra destravar @topshoppet_ e @topshopmoda_.
#
# ⚠️ SEM TAG DE NICHO, DE PROPÓSITO. Ele: "como o seletor é por nicho, cada
# vídeo pode ser pra uma conta diferente; se nos perfis abaixo tiver algo
# referente a tecnologia, e não apenas moda e pet, o vídeo vai pra tecnologia".
# Escrever '#pet' aqui mandaria TODO vídeo do descontopets pro @topshoppet_,
# inclusive a câmera de segurança que aparecesse no meio. Sem tag, o
# `_perfis_do_arquivo` devolve nicho '' e quem decide é o roteador, produto a
# produto.
NOVOS = [
    "achadinhodeverdade",
    "portalsercriativa",
    "achadosdagrazy_",
    "promocaoweb26",
    "achadosdascar",
    "estiloquevale",
    "viciadaemachados",
    "descontopets",
    "zenlypaws",
    "azchpn",
    "supermelpets",
    "lovelycatonline",
    "nomesspupbowl",
    "fofocraciapet",
    "meupetfofooficial",
    "mundopetvideos",
    "outpaws.us",
    "justdodealsfinds",
]

CABECALHO = """
# ── pet / moda / achadinhos BR e gringos (ADICIONADOS 19/08) ──────────────
# O gatilho: o vigia mostrou 377 pacotes prontos e ZERO pro @topshoppet_ e
# @topshopmoda_. Faltavam as duas pontas — nicho no roteador (feito no mesmo
# dia) e fonte de vídeo. Estas são as fontes.
#
# ⚠️ SEM TAG DE NICHO, DE PROPÓSITO: o roteador decide pelo PRODUTO, não pela
# fonte. Um gadget que aparecer num perfil de pet vai pro @topshoptech_.
"""


def _log(m):
    print(f"[fontes] {m}", flush=True)


def _chave(linha: str) -> str:
    """Como comparar dois perfis. Tira o '#', o '@', a tag de nicho, o espaço e
    a caixa — senão '@DescontoPets' entraria de novo ao lado de 'descontopets'
    e o coletor visitaria o mesmo perfil duas vezes por rodada."""
    l = linha.strip().lstrip("#").strip()
    if "#" in l:                      # '@perfil #beleza' → '@perfil'
        l = l.split("#", 1)[0].strip()
    if l.startswith("http"):
        l = l.rstrip("/").split("/")[-1] or l
    return l.lstrip("@").strip().lower()


def main():
    p = argparse.ArgumentParser(
        description="Acrescenta perfis do IG sem apagar nada. Idempotente.")
    p.add_argument("--ver", action="store_true", help="mostra sem escrever")
    args = p.parse_args()

    if not ARQUIVO.exists():
        _log(f"não achei {ARQUIVO} — está rodando de dentro de ~/jarvis?")
        return 1

    linhas = ARQUIVO.read_text(encoding="utf-8").splitlines()

    # ⚠️ o índice inclui as linhas COMENTADAS. Um perfil comentado foi desligado
    # de propósito (fonte morta, conta que virou privada). Reintroduzi-lo como
    # linha ativa desfaria uma decisão sem ninguém perceber.
    existentes, comentados = set(), set()
    for l in linhas:
        k = _chave(l)
        if not k:
            continue
        if l.strip().startswith("#"):
            comentados.add(k)
        else:
            existentes.add(k)

    entram = [n for n in NOVOS if _chave(n) not in existentes
              and _chave(n) not in comentados]
    ja_ativos = [n for n in NOVOS if _chave(n) in existentes]
    desligados = [n for n in NOVOS if _chave(n) in comentados
                  and _chave(n) not in existentes]

    _log(f"o arquivo tem {len(existentes)} perfil(is) ativo(s)")
    if ja_ativos:
        _log(f"{len(ja_ativos)} já estava(m) lá: {', '.join(ja_ativos)}")
    if desligados:
        _log(f"⚠️  {len(desligados)} está(ão) COMENTADO(S) no arquivo — alguém "
             f"desligou de propósito, então NÃO vou reativar: "
             f"{', '.join(desligados)}")
        _log("     (se quiser de volta, descomente à mão)")
    if not entram:
        _log("nada a acrescentar — o arquivo já está do jeito que precisa")
        return 0

    _log(f"{len(entram)} perfil(is) a acrescentar:")
    for n in entram:
        _log(f"     + {n}")

    if args.ver:
        _log("(--ver: não escrevi nada)")
        return 0

    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ARQUIVO.with_suffix(f".txt.bak_{carimbo}")
    shutil.copy2(ARQUIVO, backup)

    texto = ARQUIVO.read_text(encoding="utf-8")
    if not texto.endswith("\n"):
        texto += "\n"
    texto += CABECALHO + "\n".join(entram) + "\n"
    ARQUIVO.write_text(texto, encoding="utf-8")

    total = len(existentes) + len(entram)
    _log(f"✅ acrescentei {len(entram)} · o arquivo agora tem {total} perfil(is)")
    _log(f"   backup: {backup.name}")
    _log("   confira:  .venv/bin/python tiktok_coletor.py --dry --limite 2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
