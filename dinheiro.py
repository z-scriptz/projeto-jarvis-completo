#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# dinheiro.py -- QUANTO VALE UM POST. Fecha o loop entre o que foi publicado e
# o que virou comissão.
#
# POR QUE ISSO EXISTE (02/09/2026)
# ────────────────────────────────
# O Jarvis sabe o que publicou (`posts_ledger.jsonl`) e sabe o alcance de cada
# post (`metricas_posts.jsonl`). Não sabia o que VENDEU. R$1,67 de comissão em
# 375 posts era o único número financeiro, e ele não dizia de qual post veio.
#
# O Dre está decidindo R$3.000, sendo ~R$800 numa ferramenta de vídeo por IA:
# *"a gente pode investir os 800 em ferramentas IAs e fazer explodir vários
# vídeos, ou pode gastar, e não ganhar nada."* Sem saber quanto vale um post,
# isso é aposta. Com o número, é conta — e a conta do PAYBACK sai no fim.
#
# A AMARRA É O sub_id. Todo link de afiliado sai com até 5 etiquetas, na ordem
#     [canal, nicho, produto, FONTE, video]
# e o `posts_ledger` grava essa lista junto do post. A comissão volta da Shopee
# com as mesmas etiquetas, então dá pra dizer QUAL post pagou.
#
# ⚠️ TRÊS RESULTADOS DIFERENTES, E CONFUNDIR DOIS DELES É O ERRO CARO:
#     "não consegui ler a API"   ≠   "a API respondeu, zero conversões"
#     "zero conversões"          ≠   "conversões que não casaram com post"
# O primeiro é bug meu; o segundo é resultado de negócio; o terceiro é etiqueta
# quebrada. Os três saem nomeados, nunca somados num "R$ 0,00" que parece
# resposta e não é.
#
# USO (na VPS, dentro de ~/jarvis):
#   .venv/bin/python dinheiro.py                 # últimos 30 dias
#   .venv/bin/python dinheiro.py --dias 90
#   .venv/bin/python dinheiro.py --custo 800     # a conta do payback do Kling

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))


def _carregar_env():
    """⚠️ SEM ISTO O SCRIPT MENTE. Rodado sem o .env, o cliente da Shopee diz
    "SHOPEE_APP_ID não configurado" e o relatório inteiro sai como
    "não consegui ler" — indistinguível de um problema de schema.
    Aconteceu na 1ª execução real (02/09): o `probe_conversao.py` funcionou e
    este aqui não, pela ÚNICA diferença de que o probe carrega o .env e eu tinha
    esquecido. É o mesmo defeito que o hook_alana registra no cabeçalho dele
    ("era o único da cadeia que NÃO carregava o .env"), cometido de novo.
    Em produção quem injeta é o systemd; na mão, é isto."""
    for cand in (BASE / ".env", Path(".env")):
        if not cand.exists():
            continue
        try:
            linhas = cand.read_text(encoding="utf-8").splitlines()
        except Exception:
            return
        for linha in linhas:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            k, _, v = linha.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and not os.environ.get(k):
                os.environ[k] = v
        return


_carregar_env()

LEDGER = BASE / "shared" / "posts_ledger.jsonl"
METRICAS = BASE / "shared" / "metricas_posts.jsonl"


def _carregar(caminho: Path) -> list:
    if not caminho.exists():
        return []
    fora = []
    for linha in caminho.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            fora.append(json.loads(linha))
        except Exception:
            continue
    return fora


def _comissao_do_no(no: dict) -> float:
    """Soma a comissão de uma conversão, aceitando as variações de campo que a
    Shopee já usou. Campo desconhecido vira 0 e é CONTADO como desconhecido —
    somar como zero em silêncio seria inventar um resultado."""
    total = 0.0
    for pedido in (no.get("orders") or []):
        for item in (pedido.get("items") or []):
            for chave in ("itemTotalCommission", "totalCommission",
                          "commission", "estimatedCommission"):
                v = item.get(chave)
                if v not in (None, ""):
                    try:
                        total += float(v)
                    except (TypeError, ValueError):
                        pass
                    break
    return total


def _subids_do_no(no: dict) -> list:
    """As etiquetas da conversão, venham de onde vierem. `utmContent` costuma
    trazer os sub_ids concatenados; `subIds` vem como lista."""
    brutos = no.get("subIds") or no.get("sub_ids") or []
    if isinstance(brutos, str):
        brutos = [brutos]
    utm = no.get("utmContent") or no.get("utm_content") or ""
    if utm:
        brutos = list(brutos) + [p for p in str(utm).replace("|", "_").split("_") if p]
    return [str(b).strip() for b in brutos if str(b).strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="quanto vale um post")
    ap.add_argument("--dias", type=int, default=30)
    ap.add_argument("--custo", type=float, default=0.0,
                    help="custo de uma ferramenta (ex: 800) pra calcular o payback")
    ap.add_argument("--bruto", action="store_true",
                    help="imprime a resposta crua da API (pra depurar o schema)")
    a = ap.parse_args()

    try:
        from shopee_affiliate import relatorio_conversao
    except Exception:
        try:
            from integrations.shopee_affiliate import relatorio_conversao
        except Exception as e:
            print(f"❌ não consegui importar o cliente da Shopee: {e}")
            print("   use .venv/bin/python, de dentro de ~/jarvis.")
            return 1

    print(f"💰 lendo conversões dos últimos {a.dias} dias…\n")
    rel = relatorio_conversao(dias=a.dias)

    # ── caso 1: NÃO CONSEGUI LER. Isto não é "vendeu zero". ────────────────
    if not rel.get("ok"):
        print("❌ NÃO CONSEGUI LER O RELATÓRIO DE CONVERSÃO.")
        print(f"   {rel.get('erro')}")
        if rel.get("nomes_que_a_api_declara"):
            print(f"   a API declara estas queries parecidas: "
                  f"{rel['nomes_que_a_api_declara']}")
        for t in rel.get("tentativas") or []:
            print(f"   · tentei {t['query']}: {t['erro']}")
        print("\n⚠️  ISTO NÃO SIGNIFICA QUE NÃO VENDEU. Significa que eu não sei.")
        print("   Rode `.venv/bin/python probe_conversao.py` e me mande a saída")
        print("   inteira — ela revela o nome e os campos certos da query.")
        return 1

    conversoes = rel.get("conversoes") or []
    print(f"✅ a API respondeu pela query `{rel.get('query')}` · "
          f"{len(conversoes)} conversão(ões) no período")

    # ⚠️ SEM CAMPO DE ETIQUETA, A AMARRA É IMPOSSÍVEL — e isso precisa ser dito
    # ANTES da tabela, senão o relatório sai com "100% órfãs" e parece que as
    # nossas etiquetas quebraram, quando na verdade a API não devolve etiqueta
    # nenhuma. Diagnóstico errado manda consertar o lado certo do problema.
    if not rel.get("etiquetas"):
        print("\n⚠️  O NÓ DESTE RELATÓRIO NÃO EXPÕE sub_id.")
        print(f"   Campos que ele tem: {rel.get('campos_do_no') or '(não consegui listar)'}")
        print("   Sem etiqueta não dá pra dizer QUAL post vendeu — o total abaixo")
        print("   é real, mas a atribuição por post fica impossível por esta via.")
        print("   Caminho alternativo: `validatedReport` / `partnerOrderReport`,")
        print("   ou casar por itemId contra o produto do post.")
    if a.bruto and conversoes:
        print(json.dumps(conversoes[:3], ensure_ascii=False, indent=2)[:2000])

    # ── caso 2: RESPONDEU E NÃO HÁ CONVERSÃO. Isto É um resultado. ─────────
    if not conversoes:
        print("\n📉 Zero conversões no período — e isto é resposta, não erro.")
        print("   Com zero, qualquer ferramenta de R$800 tem payback infinito:")
        print("   o gargalo não é a qualidade do vídeo, é que o clique não")
        print("   está virando compra. Antes de gastar em produção, vale olhar")
        print("   o caminho do link (bio → site → Shopee) e o próprio produto.")
        return 0

    # ── a junção: comissão × post, pelo sub_id ────────────────────────────
    posts = _carregar(LEDGER)

    # ⚠️ SÓ ETIQUETA ÚNICA PODE AMARRAR UMA COMISSÃO A UM POST.
    #
    # Achado no teste, antes de subir: eu casava por QUALQUER sub_id, e o
    # contrato é [canal, nicho, produto, FONTE, video]. As quatro primeiras se
    # repetem em post após post — "ig" é etiqueta de TODOS. Resultado medido:
    # uma conversão de um vídeo que não existe no diário foi contada como
    # casada, e R$4,75 inteiros foram creditados a UM post que ganhou R$1,50.
    #
    # Atribuição errada é pior que atribuição nenhuma: ela vira "esse formato
    # converte", e vira decisão. Então a regra é dura — uma etiqueta que aponta
    # pra mais de um post NÃO amarra nada, e a conversão vira órfã declarada.
    contagem = {}
    for post in posts:
        for s in (post.get("sub_ids") or []):
            s = str(s).strip()
            if s:
                contagem.setdefault(s, []).append(post)
    por_subid = {s: v[0] for s, v in contagem.items() if len(v) == 1}
    ambiguas = len(contagem) - len(por_subid)
    if ambiguas:
        print(f"   ({ambiguas} etiqueta(s) genérica(s) ignorada(s) na amarra — "
              f"'ig', 'casa' e afins apontam pra vários posts)")

    # PLANO B DA AMARRA: o itemId. Quando o relatório não traz etiqueta, ainda
    # dá pra casar pelo PRODUTO — o `posts_ledger` grava `item_id`. É mais fraco
    # (dois posts do mesmo produto ficam ambíguos, e aí a regra dura vale igual),
    # mas é a diferença entre atribuir e não atribuir.
    cont_item = {}
    for post in posts:
        it = str(post.get("item_id") or "").strip()
        if it:
            cont_item.setdefault(it, []).append(post)
    por_item = {i: v[0] for i, v in cont_item.items() if len(v) == 1}

    casados, orfas, total, sem_valor = [], [], 0.0, 0
    for no in conversoes:
        val = _comissao_do_no(no)
        if val == 0.0:
            sem_valor += 1
        total += val
        # do MAIS específico pro menos: no contrato o vídeo é a última
        # etiqueta, e é a única que identifica um post sozinha.
        alvo = None
        for s in reversed(_subids_do_no(no)):
            if s in por_subid:
                alvo = por_subid[s]
                break
        if alvo is None:                      # plano B: pelo itemId do pedido
            for pedido in (no.get("orders") or []):
                for item in (pedido.get("items") or []):
                    it = str(item.get("itemId") or "").strip()
                    if it and it in por_item:
                        alvo = por_item[it]
                        break
                if alvo:
                    break
        (casados if alvo else orfas).append((no, val, alvo))

    print(f"\n💵 comissão somada no período: R$ {total:,.2f}".replace(",", "X")
          .replace(".", ",").replace("X", "."))
    if sem_valor:
        print(f"   ⚠️ {sem_valor} conversão(ões) sem campo de comissão que eu "
              f"reconheça — rode com --bruto e me mande, o nome do campo mudou")
    print(f"   {len(casados)} casada(s) com post · {len(orfas)} órfã(s)")
    if orfas:
        print("   ⚠️ ÓRFÃ = comissão real que não casou com nenhum post nosso —")
        print("      nem por etiqueta, nem por itemId. Quase sempre é venda de")
        print("      link publicado FORA do Jarvis (link seu, no WhatsApp, num")
        print("      grupo). Vale olhar os nomes abaixo antes de concluir:")
        for no, val, _ in sorted(orfas, key=lambda t: -t[1])[:6]:
            nomes = [i.get("itemName", "?") for p in (no.get("orders") or [])
                     for i in (p.get("items") or [])]
            print(f"      R$ {val:5.2f}  {(nomes[0] if nomes else '?')[:58]}"
                  .replace(".", ","))

    # ── por post, e depois a conta que decide ─────────────────────────────
    por_post = defaultdict(float)
    for _no, val, alvo in casados:
        if alvo:
            por_post[alvo.get("slug") or alvo.get("produto") or "?"] += val
    if por_post:
        print("\n── os que pagaram ──")
        for slug, val in sorted(por_post.items(), key=lambda kv: -kv[1])[:15]:
            print(f"   R$ {val:7.2f}".replace(".", ",") + f"  {slug[:60]}")

    metricas = _carregar(METRICAS)
    n_posts = len({m.get("shortcode") for m in metricas if m.get("shortcode")}) or len(posts)
    alcance = sum(float(m.get("alcance") or 0) for m in metricas)

    # ⚠️ A CONTA USA SÓ O QUE CASOU COM POST. Dividir o total (que inclui as
    # órfãs) pelo número de posts credita ao Jarvis venda que veio de outro
    # lugar — e o número resultante viraria "cada post vale X", que é
    # exatamente a mentira que este arquivo existe pra não contar.
    atribuido = sum(v for _n, v, alvo in casados if alvo)
    print("\n══ A CONTA QUE DECIDE ══")
    if not casados:
        print("   ⛔ NENHUMA comissão casou com um post nosso.")
        print("   Então NÃO EXISTE 'valor por post' pra calcular: o dinheiro do")
        print("   período entrou por outro caminho. Somar assim mesmo daria um")
        print("   número bonito e falso.")
        print("\n   O que isso responde sobre os R$800: nada ainda — mas diz onde")
        print("   olhar primeiro. Ou a etiqueta não está voltando da Shopee, ou")
        print("   os posts realmente não venderam no período. São problemas")
        print("   diferentes e o conserto de um não serve pro outro.")
        return 0
    print(f"   (usando só as {len(casados)} casadas: R$ {atribuido:.2f}"
          .replace(".", ",") + f" de R$ {total:.2f})".replace(".", ","))
    if n_posts:
        print(f"   R$ {atribuido / n_posts:.4f} por post publicado   ({n_posts} posts)"
              .replace(".", ",", 1))
    if alcance:
        print(f"   R$ {1000 * atribuido / alcance:.2f} por 1.000 de alcance   "
              f"({alcance:,.0f} de alcance somado)".replace(",", "."))

    if a.custo and n_posts and atribuido > 0:
        por_post_val = atribuido / n_posts
        precisa = a.custo / por_post_val
        print(f"\n   Pra pagar R$ {a.custo:.0f} no ritmo de hoje seriam "
              f"**{precisa:,.0f} posts**.".replace(",", "."))
        print("   ⚠️ E essa conta assume que o vídeo novo converte IGUAL ao de")
        print("      hoje. A aposta da ferramenta é justamente que converta")
        print("      MAIS — então o número acima é o teto do risco, não a")
        print("      previsão. Se ele já for aceitável, a decisão é fácil.")
    elif a.custo:
        print(f"\n   Não dá pra calcular o payback de R$ {a.custo:.0f}: "
              f"a comissão do período é zero.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
