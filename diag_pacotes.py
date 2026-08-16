#!/usr/bin/env python3
# diag_pacotes.py -- por conta: o pacote que vai pro ar tem legenda?
#
# POR QUE EXISTE (15/08)
# O Dre: *"a conta topshopcasa_ não está postando o conteúdo com legenda, tá
# só postando o vídeo"*. E a legenda não é enfeite: o `hook_alana.py:500` diz
# que ela existe pra fazer a pessoa SALVAR e COMPARTILHAR, e save/share é dos
# maiores sinais de alcance do Instagram.
#
# ⚠️ NÃO DÁ PRA RESPONDER LENDO O CÓDIGO DESTE REPO. O daemon publica via
# `agents.publish_guard.publicar_com_garantia` — um arquivo que só existe na
# VPS. O `publish_guard.py` daqui é o `brain/publish_guard.py`, que só valida
# permissão e nem tem essa função. Adivinhar o que o outro faz seria repetir o
# erro do campo `texto` que inventei no `fila_qualidade` hoje.
#
# Então este arquivo não opina: ele abre os pacotes REAIS no disco e conta, por
# conta, quantos têm legenda e onde ela está. Se os pacotes da casa vierem sem
# legenda, o defeito é na PRODUÇÃO; se vierem com, o defeito é no publicador —
# e são consertos em arquivos diferentes.
#
# O que o produtor escreve hoje (`produzir_tiktok.py:378-411`):
#     video.mp4 · conta.json · engajamento.json
#     titulo_youtube.txt · descricao_youtube.txt · hashtags.txt
# ⚠️ Repare: **não existe `legenda.txt`**. A legenda mora no
# `shared/content_plans/plano_<slug>.json`, e o `descricao_youtube.txt` é
# legenda + hashtags com nome de YouTube. Se o publicador procurar um
# `legenda.txt`, ele não acha em conta NENHUMA — e aí a pergunta vira "por que
# as outras têm?".
#
# Não escreve nada. Só stdlib.
#
# Uso (na VPS):  python3 diag_pacotes.py
#                python3 diag_pacotes.py --conta casa

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
PACOTES = BASE / "pronto_para_postar"
PLANOS = BASE / "shared" / "content_plans"

ESPERADOS = ["video.mp4", "conta.json", "engajamento.json",
             "titulo_youtube.txt", "descricao_youtube.txt", "hashtags.txt"]


def _log(m):
    print(f"[pacotes] {m}", flush=True)


def _conta_do_pacote(pasta: Path) -> str:
    f = pasta / "conta.json"
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            return (d.get("handle") or d.get("nicho") or "?").strip()
        except Exception:
            return "(conta.json ilegível)"
    return "(sem conta.json)"


def _legenda_do_plano(slug: str):
    """(texto, de_onde) — ou (None, motivo). A legenda REAL que o publicador
    teria disponível."""
    f = PLANOS / f"plano_{slug}.json"
    if not f.exists():
        return None, f"plano_{slug}.json não existe"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        return None, f"plano ilegível: {str(e)[:50]}"
    txt = (d.get("legenda") or "").strip()
    return (txt, "plano.legenda") if txt else (None, "plano existe, legenda VAZIA")


def main():
    p = argparse.ArgumentParser(
        description="Os pacotes prontos pra postar têm legenda? Por conta.")
    p.add_argument("--conta", default="", help="filtra por handle/nicho")
    p.add_argument("--listar", action="store_true",
                   help="mostra pacote a pacote, não só o resumo")
    args = p.parse_args()

    if not PACOTES.exists():
        raise SystemExit(f"[pacotes] não achei {PACOTES}")

    pastas = sorted(d for d in PACOTES.iterdir() if d.is_dir())
    if not pastas:
        raise SystemExit(f"[pacotes] {PACOTES} está vazia")

    por_conta = defaultdict(lambda: {"n": 0, "com": 0, "sem": [],
                                     "faltando": defaultdict(int)})
    for pasta in pastas:
        conta = _conta_do_pacote(pasta)
        if args.conta and args.conta.lower() not in conta.lower():
            continue
        c = por_conta[conta]
        c["n"] += 1
        for nome in ESPERADOS:
            if not (pasta / nome).exists():
                c["faltando"][nome] += 1
        txt, de_onde = _legenda_do_plano(pasta.name)
        if txt:
            c["com"] += 1
        else:
            c["sem"].append((pasta.name, de_onde))
        if args.listar:
            marca = "✅" if txt else "❌"
            print(f"  {marca} {conta[:20]:20} {pasta.name[:38]:38} "
                  f"{de_onde}")

    print()
    print(f"  {'conta':24} {'pacotes':>7} {'com legenda':>12} {'sem':>5}")
    print("  " + "─" * 54)
    for conta, c in sorted(por_conta.items(), key=lambda kv: -kv[1]["n"]):
        print(f"  {conta[:24]:24} {c['n']:7} {c['com']:12} "
              f"{len(c['sem']):5}")

    # ── onde exatamente falta ───────────────────────────────────────────────
    for conta, c in sorted(por_conta.items()):
        if not c["sem"] and not c["faltando"]:
            continue
        print()
        print(f"  ── {conta} ──")
        if c["faltando"]:
            for nome, q in sorted(c["faltando"].items(), key=lambda kv: -kv[1]):
                print(f"     falta `{nome}` em {q}/{c['n']} pacote(s)")
        motivos = defaultdict(int)
        for _, motivo in c["sem"]:
            motivos[motivo.split(":")[0]] += 1
        for motivo, q in sorted(motivos.items(), key=lambda kv: -kv[1]):
            print(f"     sem legenda ({q}): {motivo}")
        for slug, motivo in c["sem"][:3]:
            print(f"       ex.: {slug[:44]} → {motivo}")

    print()
    total = sum(c["n"] for c in por_conta.values())
    com = sum(c["com"] for c in por_conta.values())
    if com == total:
        _log("TODO pacote tem legenda no plano.")
        _log("   Então o defeito NÃO é da produção: é o publicador que não "
             "está lendo, ou está lendo de outro lugar. O caminho é o "
             "`agents/publish_guard.py` da VPS — este repo não tem esse "
             "arquivo, então o próximo passo é olhar de onde ELE lê a legenda:")
        _log("     grep -n 'legenda\\|caption' agents/publish_guard.py")
    elif com == 0:
        _log("NENHUM pacote tem legenda no plano — o defeito é na PRODUÇÃO, "
             "antes de publicar.")
    else:
        _log(f"{total - com} de {total} pacotes sem legenda, e não é a frota "
             f"inteira.")
        _log("   Compare as contas acima: se falta só numa, a diferença está "
             "no que a produção fez PARA ELA — nicho, roteador, ou plano que "
             "não chegou a ser gravado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
