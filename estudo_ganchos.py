#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# estudo_ganchos.py -- QUAL FORMA DE GANCHO PEGA ALCANCE NAS NOSSAS CONTAS.
#
# POR QUE ISSO EXISTE (02/09/2026)
# ────────────────────────────────
# O Dre: *"vamo tentar arrumar esses ganchos, de verdade mesmo, é uma coisa que
# chama atenção nos primeiros segundos, quero que o jarvis estude os melhores
# ganchos [...] se quiser ele pode até dar uma olhada nesses perfis"*.
#
# Eu podia responder isso com opinião. Já quase custou caro uma vez: em 01/09
# apliquei dado de CTR de tráfego pago numa pergunta sobre rede social orgânica,
# e o Dre me parou — *"o formato que ganhou foi com tráfego pago, totalmente
# diferente de redes sociais"*. Ele estava certo, e a lição é a mesma aqui:
# gancho que funciona pro @achad0ideal (16k, nicho dele, público dele) é
# HIPÓTESE, não resposta. O que decide é o alcance das NOSSAS contas.
#
# E esse dado existe. `metricas_posts.jsonl` grava, por post publicado:
#     hook · produto · nicho · conta · alcance · curtidas · comentários
# Ou seja: dá pra perguntar "que FORMA de gancho pegou alcance" e a resposta sai
# do campo, não da minha cabeça.
#
# ⚠️ O QUE ESTE ARQUIVO NÃO PODE FAZER. Ele NÃO isola o gancho. Um Reel de
# alcance alto teve gancho, produto, vídeo, áudio e horário — e o alcance é
# resultado dos cinco. Correlação com n pequeno vira superstição fácil: se
# "pergunta" aparece em 4 posts e um deles viralizou por causa do áudio, a
# tabela vai dizer que pergunta funciona. Por isso:
#   · traço com menos de MIN_AMOSTRA posts sai marcado como "pouco caso"
#   · a saída fala em MEDIANA, não em média (um viral distorce a média inteira)
#   · e ela imprime a mediana geral do lado, pra comparação ser contra a base
#     e não contra o nada.
#
# COMO LER: um traço que aparece muito e tem mediana ACIMA da geral é candidato
# a virar regra no prompt do hook_alana. Um traço com 3 posts não é nada ainda —
# é um pedido de mais amostra.
#
# USO (na VPS, dentro de ~/jarvis):
#   .venv/bin/python estudo_ganchos.py
#   .venv/bin/python estudo_ganchos.py --conta @topshop.__
#   .venv/bin/python estudo_ganchos.py --metrica curtidas
#   .venv/bin/python estudo_ganchos.py --exemplos      # os melhores e piores

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

METRICAS = BASE / "shared" / "metricas_posts.jsonl"
MIN_AMOSTRA = 8          # abaixo disso a linha sai marcada, não some


# ══════════════════════════════════════════════════════════════════════════
# OS TRAÇOS
#
# Cada um é uma pergunta ESTRUTURAL sobre o texto — nada de "é bom" ou "é
# criativo", que eu não sei medir. São as formas que dá pra contar, e várias
# vieram de olhar os dois perfis que o Dre mandou:
#
#   @achad0ideal        "não mostre isso a uma pessoa friorenta"   → 2ª pessoa,
#                       imperativo negativo, convida a MARCAR alguém
#   @ofertasdaflorzinha "Se você tem uma estante de livros você precisa disso"
#                       → condicional, filtra por identificação
#
# Nenhum dos dois usa a nossa forma dominante ("Eu vivia…", "Achava que…"),
# que é 1ª pessoa e testemunho. Isso é a HIPÓTESE central a testar aqui: se
# testemunho perde pra convite, a tabela mostra.
# ══════════════════════════════════════════════════════════════════════════
def _t(rx):
    return re.compile(rx, re.I).search


TRACOS = {
    # ── pessoa gramatical ─────────────────────────────────────────────────
    "1ª pessoa (eu/meu/minha)":
        lambda h: bool(_t(r"\b(eu|meu|minha|meus|minhas|comprei|descobri|jurei|achava|vivia)\b")(h)),
    "2ª pessoa (você/seu)":
        lambda h: bool(_t(r"\b(você|voce|teu|tua|seu|sua|vc)\b")(h)),
    "impessoal (nem eu nem você)":
        lambda h: not _t(r"\b(eu|meu|minha|comprei|descobri|jurei|achava|vivia|você|voce|seu|sua|vc)\b")(h),

    # ── forma da frase ────────────────────────────────────────────────────
    "pergunta (?)":        lambda h: "?" in h,
    "condicional (se/quem)":
        lambda h: bool(_t(r"^\s*(se|quem)\b|\b(se você|quem tem|quem já|pra quem)\b")(h)),
    "imperativo negativo (não faça/mostre)":
        lambda h: bool(_t(r"\bn[ãa]o\s+(mostr|conta|faç|faz|compr|deix)")(h)),
    "negação (não/nunca/ninguém)":
        lambda h: bool(_t(r"\b(não|nao|nunca|ninguém|ninguem|nada)\b")(h)),
    "contraste (não X, é Y)":
        lambda h: bool(_t(r"(não é|nao e|nunca foi|não era)\s+\w+,?\s*(era|é|e)\b")(h)),

    # ── abertura, que é o que se lê em 1 segundo ──────────────────────────
    "abre com 'eu'":       lambda h: bool(_t(r"^\s*eu\b")(h)),
    "abre com 'achava/jurei/pensei'":
        lambda h: bool(_t(r"^\s*(achava|achei|jurei|pensei|imaginava)\b")(h)),
    "abre com 'descobri'": lambda h: bool(_t(r"^\s*descobri\b")(h)),
    "abre com verbo de comando":
        lambda h: bool(_t(r"^\s*(olha|veja|para|pare|corre|marca|salva|não)\b")(h)),

    # ── superfície ────────────────────────────────────────────────────────
    "tem emoji":           lambda h: bool(_t(r"[\U0001F300-\U0001FAFF☀-➿]")(h)),
    "2 linhas (tem \\n)":  lambda h: "\n" in h.strip(),
    "curto (≤ 45 car.)":   lambda h: len(h.replace("\n", " ")) <= 45,
    "longo (> 70 car.)":   lambda h: len(h.replace("\n", " ")) > 70,
    "cita o produto":      None,     # precisa do registro, tratado à parte
}


def _cita_produto(reg) -> bool:
    """O gancho repete alguma palavra do nome do produto?

    Os dois perfis de referência NÃO fazem isso — falam da situação, e o produto
    aparece no vídeo. É um traço que vale medir justamente porque a intuição
    diz o contrário.
    """
    hook = (reg.get("hook") or "").lower()
    palavras = [p for p in re.findall(r"[a-zà-ú]{5,}", (reg.get("produto") or "").lower())]
    return any(p in hook for p in palavras[:6])


def _valor(reg, metrica: str) -> float:
    if metrica == "engajamento":
        alc = float(reg.get("alcance") or reg.get("reach") or 0)
        itr = sum(float(reg.get(k) or 0) for k in
                  ("curtidas", "likes", "comentarios", "comments", "salvos", "saved"))
        return (100.0 * itr / alc) if alc else 0.0
    for chave in (metrica, {"alcance": "reach", "curtidas": "likes"}.get(metrica, "")):
        if chave and reg.get(chave) is not None:
            return float(reg[chave] or 0)
    return 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description="que forma de gancho pega alcance")
    ap.add_argument("--conta", default="", help="só uma conta (ex: @topshop.__)")
    ap.add_argument("--nicho", default="")
    ap.add_argument("--metrica", default="alcance",
                    choices=("alcance", "curtidas", "engajamento"))
    ap.add_argument("--exemplos", action="store_true",
                    help="mostra os 8 melhores e os 8 piores ganchos")
    a = ap.parse_args()

    if not METRICAS.exists():
        print(f"❌ não achei {METRICAS}")
        print("   colete primeiro:  .venv/bin/python metricas_posts.py --coletar")
        return 1

    regs = []
    for linha in METRICAS.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            r = json.loads(linha)
        except Exception:
            continue
        if not (r.get("hook") or "").strip():
            continue
        if a.conta and (r.get("conta") or "") != a.conta:
            continue
        if a.nicho and (r.get("nicho") or "") != a.nicho:
            continue
        regs.append(r)

    if len(regs) < MIN_AMOSTRA * 2:
        print(f"⚠️  só {len(regs)} post(s) medidos com gancho gravado.")
        print("   Com essa amostra qualquer tabela aqui é ruído. Rode o "
              "metricas_posts por mais uns dias antes de decidir por ela.")
        if not regs:
            return 1

    valores = [_valor(r, a.metrica) for r in regs]
    base = statistics.median(valores)
    print(f"📊 {len(regs)} post(s) medidos · métrica: {a.metrica}")
    print(f"   mediana geral: {base:.1f}   (é contra ela que cada linha compara)\n")

    linhas = []
    for nome, teste in TRACOS.items():
        if nome == "cita o produto":
            com = [r for r in regs if _cita_produto(r)]
        else:
            com = [r for r in regs if teste(r.get("hook") or "")]
        sem = [r for r in regs if r not in com]
        if not com or not sem:
            continue
        mcom = statistics.median([_valor(r, a.metrica) for r in com])
        msem = statistics.median([_valor(r, a.metrica) for r in sem])
        delta = (100.0 * (mcom - msem) / msem) if msem else 0.0
        linhas.append((delta, nome, len(com), mcom, msem))

    linhas.sort(reverse=True)
    print(f"   {'traço':<42} {'posts':>5} {'com':>8} {'sem':>8}   dif")
    print("   " + "─" * 74)
    for delta, nome, n, mcom, msem in linhas:
        marca = "  ⚠️ pouco caso" if n < MIN_AMOSTRA else ""
        sinal = "+" if delta >= 0 else ""
        print(f"   {nome:<42} {n:>5} {mcom:>8.0f} {msem:>8.0f}  "
              f"{sinal}{delta:>5.0f}%{marca}")

    print("\n   ⚠️ ISTO É CORRELAÇÃO, NÃO CAUSA. O alcance de um Reel vem do")
    print("      gancho, do produto, do vídeo, do áudio e do horário juntos.")
    print("      Traço com poucos posts é pedido de mais amostra, não achado.")

    if a.exemplos:
        ordenados = sorted(regs, key=lambda r: _valor(r, a.metrica))
        print(f"\n── os 8 de MENOR {a.metrica} ──")
        for r in ordenados[:8]:
            print(f"   {_valor(r, a.metrica):>7.0f}  {(r.get('hook') or '').replace(chr(10),' / ')[:66]}")
        print(f"\n── os 8 de MAIOR {a.metrica} ──")
        for r in ordenados[-8:]:
            print(f"   {_valor(r, a.metrica):>7.0f}  {(r.get('hook') or '').replace(chr(10),' / ')[:66]}")
        print("\n   Ler estes 16 na mão vale mais que a tabela inteira: a tabela")
        print("   conta a FORMA, e o que decide costuma estar no assunto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
