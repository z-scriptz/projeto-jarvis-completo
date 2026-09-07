#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# varrer_adulto.py -- tem alguma coisa +18 JÁ dentro do sistema, agora?
#
# POR QUE ISTO EXISTE (07/09/2026)
# ────────────────────────────────
# O filtro novo (`shared/termos.conteudo_adulto`) impede que item +18 ENTRE e
# que seja POSTADO daqui pra frente. Ele não diz nada sobre o que já está
# guardado — e tem 2.693 pacotes na inbox, ~380 vídeos renderizados esperando a
# vez e a fila de produtos do grupo, tudo coletado sem filtro nenhum.
#
# ⚠️ "AGORA ESTÁ PROTEGIDO" É RESPOSTA PELA METADE. O Dre pediu que nada disso
# seja postado no grupo dele; um vídeo desses já renderizado em
# `pronto_para_postar` vai ao ar sozinho, pelo daemon, sem passar por lugar
# nenhum onde o filtro novo esteja. Filtro de entrada não varre o estoque.
#
# Este script só OLHA e conta. Nada é apagado sem `--apagar`.
#
#   .venv/bin/python varrer_adulto.py             # só lista
#   .venv/bin/python varrer_adulto.py --apagar    # remove os pacotes achados
import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
try:
    from shared.termos import conteudo_adulto
except Exception as e:
    print(f"❌ não consegui carregar shared/termos.py: {str(e)[:90]}")
    raise SystemExit(1)

FILA = BASE / "shared" / "produtos_fila.json"
PRONTOS = BASE / "pronto_para_postar"
INBOX = BASE / "inbox_tiktok"
FEITOS = INBOX / "_produzidos"


def _achados_em_pacotes(raiz: Path):
    """(pasta, nome, motivo) pra cada pacote reprovado sob `raiz`."""
    if not raiz.exists():
        return
    for pasta in sorted(raiz.iterdir()):
        if not pasta.is_dir() or pasta.name.startswith("_"):
            continue
        pj = pasta / "plano.json"
        if not pj.exists():
            continue
        try:
            d = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            continue
        nome = (d.get("produto") or d.get("termo") or "").strip()
        if not nome:
            continue
        veta, motivo = conteudo_adulto(nome, d.get("descricao", ""),
                                       d.get("categoria", ""))
        if veta:
            yield pasta, nome, motivo


def main() -> int:
    apagar = "--apagar" in sys.argv[1:]
    total = 0

    # ── 1. a fila que alimenta os grupos ──────────────────────────────────
    print("\n── fila de produtos (grupos do WhatsApp e Telegram) ──")
    try:
        fila = json.loads(FILA.read_text(encoding="utf-8"))
    except Exception:
        fila = []
    ruins_fila = []
    for it in fila if isinstance(fila, list) else []:
        if not isinstance(it, dict):
            continue
        nome = str(it.get("campeao") or it.get("produto") or "")
        veta, motivo = conteudo_adulto(nome, it.get("descricao", ""),
                                       it.get("categoria", ""))
        if veta:
            ruins_fila.append((nome, motivo))
    if ruins_fila:
        for nome, motivo in ruins_fila:
            print(f"   🔞 {nome[:58]:60} {motivo}")
        print(f"\n   {len(ruins_fila)} de {len(fila)} na fila")
        # ⚠️ NÃO REESCREVO A FILA AQUI, NEM COM --apagar. Ela é editada em
        # produção por vários processos (piloto insere no topo ~11x/dia,
        # repescagem no fim) e regravar o arquivo inteiro a partir de uma leitura
        # antiga apaga o que entrou nesse meio-tempo. Os dois postadores já
        # barram estes itens em tempo de envio, que é onde importa.
        print(f"   (os postadores já barram estes — a fila não é reescrita "
              f"aqui de propósito, ela tem outros donos escrevendo nela)")
    else:
        print(f"   ✅ nada em {len(fila) if isinstance(fila, list) else 0} itens")
    total += len(ruins_fila)

    # ── 2. vídeos JÁ RENDERIZADOS, esperando o daemon postar ──────────────
    print("\n── pronto_para_postar (o daemon posta isto sozinho) ──")
    achados = []
    if PRONTOS.exists():
        # o pacote pronto não tem plano.json; o nome da pasta é o slug do produto
        for pasta in sorted(PRONTOS.iterdir()):
            if not pasta.is_dir():
                continue
            nome = pasta.name.replace("_", " ")
            veta, motivo = conteudo_adulto(nome)
            if veta:
                achados.append((pasta, nome, motivo))
    for pasta, nome, motivo in achados:
        print(f"   🔞 {nome[:58]:60} {motivo}")
    print(f"   {'✅ nada' if not achados else f'{len(achados)} achado(s)'}")
    total += len(achados)

    # ── 3. pacotes na inbox e nos já produzidos ───────────────────────────
    for rotulo, raiz in (("inbox_tiktok", INBOX), ("_produzidos", FEITOS)):
        print(f"\n── {rotulo} ──")
        lista = list(_achados_em_pacotes(raiz))
        for pasta, nome, motivo in lista:
            print(f"   🔞 {nome[:58]:60} {motivo}")
        print(f"   {'✅ nada' if not lista else f'{len(lista)} achado(s)'}")
        achados.extend(lista)
        total += len(lista)

    print(f"\n── resultado ──")
    print(f"   🔞 {total} item(ns) que o filtro novo reprovaria")
    if achados and apagar:
        n = 0
        for pasta, nome, _m in achados:
            try:
                shutil.rmtree(pasta, ignore_errors=True)
                n += 1
            except Exception as e:
                print(f"   ⚠️ não apaguei {pasta.name}: {str(e)[:60]}")
        print(f"   🗑️  {n} pasta(s) removida(s)")
    elif achados:
        print(f"   (nada foi alterado — use --apagar pra remover as pastas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
