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
# ⚠️ A 1ª RODADA REAL (329 posts, 02/09) MOSTROU DOIS DEFEITOS MEUS, e os dois
# viraram conserto aqui:
#
#   1. "tem emoji  +3767%"  — número gigante e FALSO. O grupo "sem emoji" tinha
#      22 posts com mediana de alcance **3**. Post com alcance 3 não é post com
#      pouco emoji: é post que não foi entregue. O traço estava pegando carona
#      num grupo morto. Agora exijo amostra dos DOIS lados e grito quando um
#      deles tem mediana perto de zero.
#
#   2. O fundo da lista era CARROSSEL, não Reel. O próprio metricas_posts.py
#      avisa: *"as duas coisas têm alcance típico bem diferente"*. Comparar
#      forma de gancho misturando os dois compara FORMATO, não gancho. Agora o
#      padrão é só Reel (`--tipo`).
#
#   3. E o alcance bruto mistura o TAMANHO DA CONTA. Um post do @topshop.__ e um
#      do @topshoppet_ não competem na mesma escala; qualquer traço que apareça
#      mais numa conta grande ganha um bônus que não é dele. Agora cada post é
#      medido contra a MEDIANA DA PRÓPRIA CONTA (`--bruto` desliga).
#
# Com esses três, a tabela da 1ª rodada perde o número de 3767% e o resto fica
# dentro de ±13% — que, lido honestamente, é: NENHUM traço de forma move o
# ponteiro. O que separava os 8 melhores dos 8 piores estava no ASSUNTO, não na
# forma. Isso é resultado, não fracasso da ferramenta.
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
import os
import re
import statistics
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

METRICAS = BASE / "shared" / "metricas_posts.jsonl"
MIN_AMOSTRA = 8          # abaixo disso a linha sai marcada, não some
# "estourou" = passou disto vezes a mediana da própria conta.
LIMIAR = float(os.environ.get("ESTUDO_ESTOURO", "3"))


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
    ap.add_argument("--tipo", default="reel", choices=("reel", "carrossel", "tudo"),
                    help="misturar carrossel com Reel compara FORMATO, não gancho")
    ap.add_argument("--bruto", action="store_true",
                    help="não normaliza pela conta (mistura tamanho de conta)")
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
        # `tipo` só é gravado pro carrossel (metricas_posts._carrosseis);
        # ausente = Reel.
        tipo = (r.get("tipo") or "reel").strip().lower()
        if a.tipo != "tudo" and tipo != a.tipo:
            continue
        regs.append(r)

    if len(regs) < MIN_AMOSTRA * 2:
        print(f"⚠️  só {len(regs)} post(s) medidos com gancho gravado.")
        print("   Com essa amostra qualquer tabela aqui é ruído. Rode o "
              "metricas_posts por mais uns dias antes de decidir por ela.")
        if not regs:
            return 1

    # ── NORMALIZAÇÃO POR CONTA ────────────────────────────────────────────
    # Sem isto, o alcance bruto carrega o TAMANHO DA CONTA junto. Um traço que
    # por acaso aparece mais no @topshop.__ (a maior) ganha um bônus que é da
    # conta, não do gancho — e a tabela credita ao gancho.
    # Cada post vira "quantas vezes a mediana da PRÓPRIA conta", então 1,0 = um
    # post mediano pra aquela conta, em qualquer conta.
    por_conta = {}
    for r in regs:
        por_conta.setdefault(r.get("conta") or "?", []).append(_valor(r, a.metrica))
    medianas = {c: (statistics.median(v) or 0) for c, v in por_conta.items()}

    # ⚠️ CONTA MORTA QUEBRA A NORMALIZAÇÃO — é o MESMO bug do "+3767%", uma
    # camada acima. O @topshoppet_ tem mediana de alcance **3**: dividir por 3
    # transforma um post de 178 (que é pouco) em "59× a mediana", e ele sobe pro
    # topo da lista passando na frente de um post de 1737 alcance real.
    # Conta que não está sendo entregue não mede gancho: mede a conta.
    PISO_CONTA = float(os.environ.get("ESTUDO_PISO_CONTA", "20"))
    mortas = {c: m for c, m in medianas.items() if m < PISO_CONTA}
    if mortas and len(mortas) < len(medianas):
        regs = [r for r in regs if (r.get("conta") or "?") not in mortas]
        medianas = {c: m for c, m in medianas.items() if c not in mortas}

    def val(r):
        bruto = _valor(r, a.metrica)
        if a.bruto:
            return bruto
        m = medianas.get(r.get("conta") or "?", 0)
        return (bruto / m) if m else 0.0

    # ── POST NÃO ENTREGUE NÃO É MEDIÇÃO DE GANCHO ─────────────────────────
    # O guard de "grupo morto" trata o sintoma numa linha; a causa é que posts
    # com alcance perto de zero entram no grupo "sem" de TODO traço e puxam
    # todas as comparações. Alcance 3 numa conta cuja mediana é 115 não diz
    # nada sobre o texto: diz que o Instagram não entregou o post.
    # Eles saem da conta, e a quantidade é IMPRESSA — descarte silencioso é
    # como se fabrica um número bonito sem perceber.
    PISO = float(os.environ.get("ESTUDO_PISO", "0.10"))
    vivos = [r for r in regs if not medianas.get(r.get("conta") or "?", 0)
             or _valor(r, a.metrica) >= PISO * medianas[r.get("conta") or "?"]]
    descartados = len(regs) - len(vivos)

    unidade = a.metrica if a.bruto else "× a mediana da conta"
    base = statistics.median([val(r) for r in vivos]) if vivos else 0.0
    print(f"📊 {len(regs)} post(s) · tipo {a.tipo} · métrica: {a.metrica}"
          f"{'' if a.bruto else ' (normalizado por conta)'}")
    if not a.bruto and len(medianas) > 1:
        det = " · ".join(f"{c} {m:.0f}" for c, m in
                         sorted(medianas.items(), key=lambda kv: -kv[1]))
        print(f"   mediana de cada conta: {det}")
    print(f"   mediana geral: {base:.2f} {unidade}")
    if mortas:
        det = ", ".join(f"{c} (mediana {m:.0f})" for c, m in sorted(mortas.items()))
        print(f"   ⛔ conta(s) fora por não estarem sendo entregues: {det}")
    if descartados:
        print(f"   ⛔ {descartados} post(s) fora: alcance abaixo de "
              f"{PISO:.0%} da mediana da própria conta — não foram entregues, "
              f"e medir texto neles é medir a entrega")
    regs = vivos
    print()

    linhas = []
    for nome, teste in TRACOS.items():
        if nome == "cita o produto":
            com = [r for r in regs if _cita_produto(r)]
        else:
            com = [r for r in regs if teste(r.get("hook") or "")]
        ids = {id(r) for r in com}
        sem = [r for r in regs if id(r) not in ids]
        if not com or not sem:
            continue
        mcom = statistics.median([val(r) for r in com])
        msem = statistics.median([val(r) for r in sem])
        # ⚠️ GRUPO DE COMPARAÇÃO MORTO INVENTA EFEITO GIGANTE. Foi assim que
        # "tem emoji" saiu +3767%: os 22 sem emoji tinham mediana de alcance 3,
        # ou seja, não eram posts com pouco emoji, eram posts não entregues.
        # Dividir por um número perto de zero explode qualquer diferença.
        morto = (msem < 0.05 * base) or (mcom < 0.05 * base)
        # ── TAXA DE ESTOURO ────────────────────────────────────────────────
        # A mediana é quase cega nesta distribuição. Nos dados reais do Dre a
        # mediana é 1,0 e os melhores posts batem 11-14× — cauda pesada, como
        # todo alcance orgânico. Um traço que DOBRE a chance de estourar mexe
        # pouquíssimo na mediana, porque a mediana é o post do meio e o meio não
        # estoura nunca.
        # E "estourar" é a pergunta que interessa: o Dre quer um viral, não um
        # post levemente acima do meio.
        ec = sum(1 for r in com if val(r) >= LIMIAR)
        es = sum(1 for r in sem if val(r) >= LIMIAR)
        tc, ts = 100.0 * ec / len(com), 100.0 * es / len(sem)
        linhas.append((tc - ts, nome, len(com), len(sem), mcom, msem, morto,
                       ec, tc, es, ts))

    linhas.sort(reverse=True)
    estouros = sum(1 for r in regs if val(r) >= LIMIAR)
    print(f"   ⚡ ESTOURO = post que passou de {LIMIAR:.0f}× a mediana da conta. "
          f"{estouros} de {len(regs)} ({100.0*estouros/max(1,len(regs)):.1f}%).")
    print("      A coluna que importa é esta; a mediana é quase cega numa "
          "distribuição de cauda pesada.\n")
    print(f"   {'traço':<40} {'posts':>5} {'estourou':>13} {'sem o traço':>13}"
          f"   mediana")
    print("   " + "─" * 82)
    for (_ord, nome, n, nsem, mcom, msem, morto, ec, tc, es, ts) in linhas:
        if morto:
            marca = "  ⛔"
        elif n < MIN_AMOSTRA or nsem < MIN_AMOSTRA:
            marca = "  ⚠️"
        elif ec < 3:
            # 1 ou 2 estouros num traço é uma coincidência com nome de achado.
            marca = "  ⚠️"
        else:
            marca = "   "
        med = f"{'+' if mcom >= msem else ''}{100.0*(mcom-msem)/msem:>4.0f}%" if msem else "    ?"
        print(f"   {nome:<40} {n:>5}   {ec:>2}/{n:<3} {tc:>4.1f}%   "
              f"{es:>3}/{nsem:<3} {ts:>4.1f}%   {med}{marca}")
    print("\n   ⚠️ = amostra pequena ou menos de 3 estouros (coincidência com "
          "nome de achado) · ⛔ = grupo de comparação morto")

    print("\n   ⚠️ ISTO É CORRELAÇÃO, NÃO CAUSA. O alcance de um Reel vem do")
    print("      gancho, do produto, do vídeo, do áudio e do horário juntos.")
    print("      Traço com poucos posts é pedido de mais amostra, não achado.")

    if a.exemplos:
        ordenados = sorted(regs, key=val)
        for titulo, fatia in (("MENOR", ordenados[:8]), ("MAIOR", ordenados[-8:])):
            print(f"\n── os 8 de {titulo} {a.metrica} ──")
            for r in fatia:
                print(f"   {_valor(r, a.metrica):>7.0f} ({val(r):4.2f}×)  "
                      f"{(r.get('conta') or '?')[:16]:<16} "
                      f"{(r.get('hook') or '').replace(chr(10),' / ')[:52]}")
        print("\n   Ler estes 16 na mão vale mais que a tabela inteira: a tabela")
        print("   conta a FORMA, e o que decide costuma estar no assunto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
