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


def _legenda_instagram(plano: dict):
    """RÉPLICA EXATA do `agents/publish_guard._legenda_instagram`, inclusive
    os defeitos — devolve (texto, qual_ramo).

    ⚠️ COPIAR LÓGICA É RUIM, E AQUI É O PONTO. Não estou reimplementando pra
    usar: estou reproduzindo pra MEDIR qual ramo a produção real dispara. O
    publicador só existe na VPS, e a única forma honesta de saber por onde a
    legenda sai é rodar a mesma decisão sobre os mesmos planos.

    Os três ramos, e a assimetria que interessa:
        1. descricoes.instagram      → devolvido SEM .strip(), sem validação
        2. publish_pack.legenda_ig   → devolvido SEM .strip(), sem validação
        3. plano.legenda             → .strip() e é o ÚNICO que o guarda da
                                       linha 95 exige antes de publicar
    Ou seja: o guarda valida o ramo 3 e o post pode sair pelo 1 ou pelo 2. Foi
    por isso que medimos 336/336 com legenda e mesmo assim há post sem.
    """
    descs = plano.get("descricoes") or {}
    if descs.get("instagram"):
        return descs["instagram"], "descricoes.instagram"
    pack = plano.get("publish_pack") or {}
    if pack.get("legenda_instagram"):
        return pack["legenda_instagram"], "publish_pack.legenda_instagram"
    return (plano.get("legenda") or "").strip(), "plano.legenda"


def _plano(slug: str):
    f = PLANOS / f"plano_{slug}.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


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
    p.add_argument("--mostrar", type=int, default=0,
                   help="imprime o TEXTO que iria pro Instagram, N por conta")
    p.add_argument("--listar", action="store_true",
                   help="mostra pacote a pacote, não só o resumo")
    args = p.parse_args()

    if not PACOTES.exists():
        raise SystemExit(f"[pacotes] não achei {PACOTES}")

    pastas = sorted(d for d in PACOTES.iterdir() if d.is_dir())
    if not pastas:
        raise SystemExit(f"[pacotes] {PACOTES} está vazia")

    por_conta = defaultdict(lambda: {"n": 0, "com": 0, "sem": [],
                                     "faltando": defaultdict(int),
                                     "ramos": defaultdict(int),
                                     "ig_vazia": [], "amostra": []})
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

        # O QUE O INSTAGRAM RECEBERIA DE VERDADE — pelo caminho do publicador
        pl = _plano(pasta.name)
        if pl is not None:
            saida, ramo = _legenda_instagram(pl)
            vazia = not (saida or "").strip()
            c["ramos"][ramo] += 1
            if vazia:
                c["ig_vazia"].append((pasta.name, ramo, repr(saida)[:40]))
            c["amostra"].append((pasta.name, ramo, saida or ""))
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

    # ── POR QUAL RAMO A LEGENDA DO INSTAGRAM SAI ───────────────────────────
    print()
    print("  ── O QUE O INSTAGRAM RECEBE (ramo do publish_guard) ──")
    print(f"     {'conta':22} {'ramo usado':32} {'vazias':>7}")
    for conta, c in sorted(por_conta.items()):
        if not c["ramos"]:
            continue
        ramos = " · ".join(f"{r.split('.')[-1]}:{q}"
                           for r, q in sorted(c["ramos"].items(),
                                              key=lambda kv: -kv[1]))
        print(f"     {conta[:22]:22} {ramos[:32]:32} "
              f"{len(c['ig_vazia']):7}")

    vazias = [(conta, x) for conta, c in por_conta.items()
              for x in c["ig_vazia"]]
    if vazias:
        print()
        print(f"  ❌ {len(vazias)} post(s) sairiam com legenda VAZIA no "
              f"Instagram:")
        for conta, (slug, ramo, valor) in vazias[:6]:
            print(f"     {conta[:18]:18} {slug[:30]:30} ramo={ramo} "
                  f"valor={valor}")
        print()
        print("     ⚠️ O guarda da linha 95 exige `plano.legenda` — o RAMO 3.")
        print("        Estes saem pelo ramo acima, que ninguém valida: o post")
        print("        passa na checagem e vai pro ar sem legenda.")
    else:
        print()
        print("  ✅ nenhum pacote atual sairia com legenda vazia por este")
        print("     caminho. Se a casa postou sem legenda, ou foi um pacote já")
        print("     consumido (não está mais aqui), ou a perda é depois — no")
        print("     `meta_uploader.postar_instagram` / na própria API.")

    # ── O TEXTO CRU ─────────────────────────────────────────────────────────
    # ⚠️ "não está vazio" ≠ "é uma legenda". Um `descricoes.instagram` pode ter
    # conteúdo e ainda assim não ser o que a pessoa vê como legenda — uma
    # descrição de YouTube, um resto de template, dois emojis. Contar caractere
    # responde "tem algo"; só o olho responde "é a coisa certa".
    if args.mostrar:
        for conta, c in sorted(por_conta.items()):
            print()
            print(f"  ── TEXTO QUE IRIA PRO INSTAGRAM · {conta} ──")
            # um de cada ramo primeiro: é a comparação que interessa
            vistos, mostrados = set(), 0
            for slug, ramo, txt in c["amostra"]:
                if ramo in vistos and mostrados >= args.mostrar:
                    break
                if ramo in vistos:
                    continue
                vistos.add(ramo)
                mostrados += 1
                print(f"     [{ramo}] {slug[:38]}  ({len(txt)} caracteres)")
                for linha in (txt or "(vazio)").splitlines()[:4]:
                    print(f"        │ {linha[:88]}")
                if len(txt.splitlines()) > 4:
                    print(f"        │ … +{len(txt.splitlines()) - 4} linha(s)")

    print()
    total = sum(c["n"] for c in por_conta.values())
    com = sum(c["com"] for c in por_conta.values())
    if com == total:
        _log("TODO pacote tem legenda no plano (ramo 3) — a produção está "
             "limpa.")
        _log("   O que decide é a tabela de RAMOS acima: o guarda só exige o "
             "ramo 3, e o post sai pelo 1 ou pelo 2 quando eles existem.")
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
