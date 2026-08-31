#!/usr/bin/env python3
# historico_precos.py -- guarda o preço que a API de afiliado já devolve e que
# hoje a gente joga fora, pra vitrine poder mostrar MÉDIA em vez de um número
# travado que envelhece.
#
# POR QUE MÉDIA, e não o preço exato: o site é estático (regenera no deploy,
# não acompanha a Shopee ao vivo). Preço exato numa página estática mente em
# algumas horas, e cliente que chega na loja e vê outro valor não volta. Média
# do período + data da última conferida é honesto e envelhece bem.
#
# DE ONDE VEM A LEITURA (custo zero): o deploy_site já chama obter_dados_produto
# de cada produto no health-check, e essa resposta JÁ TRAZ o preço. A gente só
# passou a guardar. Nenhuma chamada nova à API.
#
# UMA leitura por produto por dia (a última do dia vence), então o cron pode
# rodar 4x ao dia sem inflar o histórico.
#
# Uso (no VPS):
#     python3 historico_precos.py --ver              # o que já foi coletado
#     python3 historico_precos.py --ver --link URL   # detalhe de um produto
#     python3 historico_precos.py --podar            # limpa o que saiu da fila

import os
import sys
import json
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ARQUIVO = BASE_DIR / "shared" / "precos_historico.json"

# Quanto tempo de histórico a gente guarda por produto. Acima disso não serve
# pra média "recente" e só engorda o arquivo.
DIAS_GUARDADOS = 45
# Janela padrão da média mostrada no site.
JANELA_PADRAO = 7
# Abaixo de 3 leituras não existe média — é uma observação só, e o site avisa
# isso com "conferido em <data>" em vez de fingir precisão.
MIN_LEITURAS = 3
# Desconto mínimo pra ganhar selo. Não é frescura: um "-5%" ao lado de um
# "-58%" ensina o olho que o selo amarelo não quer dizer nada, e aí o selo bom
# perde força junto. Produto abaixo disso aparece normal, só sem o selo.
MIN_DESCONTO = 15

_MESES = ("jan", "fev", "mar", "abr", "mai", "jun",
          "jul", "ago", "set", "out", "nov", "dez")


# ── arquivo ───────────────────────────────────────────────────────────────
def carregar() -> dict:
    """Histórico completo. Arquivo ausente ou corrompido vira dicionário vazio
    — nunca explode o deploy por causa de estatística."""
    try:
        dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"[historico_precos] histórico ilegível ({e}) — começando vazio")
        return {}


def salvar(dados: dict) -> bool:
    """Grava atômico: escreve num temporário e troca. Assim uma interrupção no
    meio não deixa o histórico pela metade."""
    try:
        ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
        tmp = ARQUIVO.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, ARQUIVO)
        return True
    except Exception as e:
        print(f"[historico_precos] não consegui salvar: {e}")
        return False


# ── escrita ───────────────────────────────────────────────────────────────
def _numero(v, padrao=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return padrao


def ler_leitura(v) -> tuple:
    """Uma leitura gravada vira (preço, preço_de).

    Aceita os dois formatos por compatibilidade: número solto é o formato
    antigo (só preço, de quando a gente ainda não tinha o desconto da loja);
    lista [preço, de] é o atual. As leituras já coletadas continuam valendo.
    """
    if isinstance(v, (list, tuple)) and v:
        p = _numero(v[0])
        d = _numero(v[1]) if len(v) > 1 else 0.0
        return p, (d if d > p else 0.0)
    return _numero(v), 0.0


def registrar(link: str, preco, nome: str = "", quando: date = None,
              dados: dict = None, de=0) -> dict:
    """Anota a leitura de hoje de um produto.

    `de` é o preço antes do desconto da loja (vem do priceDiscountRate da API).
    Guardado junto porque o desconto muda com o tempo igual o preço — usar o
    desconto de hoje num preço que é média de 7 dias daria uma conta torta.

    Passe `dados` pra acumular várias leituras em memória e salvar uma vez só
    no fim (é o que o deploy_site faz); sem ele, lê e grava na hora.

    Preço zero/negativo/ilegível é ignorado: a API devolve 0 quando não
    conseguiu o valor, e um zero no histórico estragaria a média.
    """
    preco = _numero(preco)
    if preco <= 0 or not link:
        return dados if dados is not None else {}
    de = _numero(de)

    sozinho = dados is None
    if sozinho:
        dados = carregar()

    dia = (quando or date.today()).isoformat()
    reg = dados.setdefault(link, {"nome": nome, "leituras": {}})
    if nome:
        reg["nome"] = nome
    # a última leitura do dia vence — o cron rodando 4x/dia não vira 4 pontos
    reg.setdefault("leituras", {})[dia] = (
        [round(preco, 2), round(de, 2)] if de > preco else round(preco, 2))

    if sozinho:
        salvar(dados)
    return dados


def podar(links_vivos=None, dias: int = DIAS_GUARDADOS, dados: dict = None) -> dict:
    """Joga fora leitura velha e produto que saiu da vitrine.

    `links_vivos=None` significa "não sei quem está na vitrine" — nesse caso
    só a idade é podada, nenhum produto é removido. É o padrão seguro: some
    produto do histórico só quando o chamador afirma quem está vivo.
    """
    if dados is None:
        dados = carregar()
    corte = (date.today() - timedelta(days=dias)).isoformat()
    vivos = set(links_vivos) if links_vivos is not None else None

    for link in list(dados.keys()):
        if vivos is not None and link not in vivos:
            del dados[link]
            continue
        leituras = dados[link].get("leituras") or {}
        dados[link]["leituras"] = {d: v for d, v in leituras.items() if d >= corte}
        if not dados[link]["leituras"]:
            del dados[link]
    return dados


# ── leitura ───────────────────────────────────────────────────────────────
def _data_curta(iso: str) -> str:
    """'2026-07-31' -> '31/jul'."""
    try:
        d = datetime.strptime(iso, "%Y-%m-%d").date()
        return f"{d.day}/{_MESES[d.month - 1]}"
    except Exception:
        return iso


def resumo(link: str, janela: int = JANELA_PADRAO, dados: dict = None,
           hoje: date = None) -> dict:
    """O que a vitrine precisa saber sobre o preço de um produto.

    Devolve {} quando não há leitura nenhuma — o chamador decide o que fazer
    (hoje: não mostra preço).

    Campos:
      preco  média do período (ou a única leitura, quando obs < MIN_LEITURAS)
      obs    quantas leituras entraram na conta
      media  True quando `preco` é média de verdade (obs >= MIN_LEITURAS)
      de     maior preço observado no período, pro riscado
      off    % entre `de` e `preco` (0 quando não vale a pena mostrar)
      caiu   % de queda da última leitura contra a primeira (0 se < 5%)
      visto  data da última conferida, curta ('31/jul')
      min/max extremos do período
    """
    if dados is None:
        dados = carregar()
    leituras = (dados.get(link) or {}).get("leituras") or {}
    if not leituras:
        return {}

    corte = ((hoje or date.today()) - timedelta(days=janela - 1)).isoformat()
    dentro = {d: v for d, v in leituras.items() if d >= corte}
    # produto que não é conferido há mais de uma janela ainda merece mostrar o
    # que se sabe dele — melhor o dado antigo COM data do que nenhum dado
    if not dentro:
        dentro = leituras

    dias = sorted(dentro)
    lidos = [ler_leitura(dentro[d]) for d in dias]
    vals = [p for p, _ in lidos]
    obs = len(vals)
    media_real = obs >= MIN_LEITURAS

    preco = round(sum(vals) / obs, 2) if media_real else vals[-1]
    maior, menor = max(vals), min(vals)

    # Riscado, por duas fontes — vale a MAIOR das duas, porque as duas são
    # verdade sobre o mesmo produto:
    #   a) o "de" da própria loja (priceDiscountRate), na média do período —
    #      média porque o desconto muda de dia pro dia igual o preço, e cruzar
    #      o desconto de hoje com a média de 7 dias daria conta torta;
    #   b) o maior preço que a gente REALMENTE observou.
    # Nunca usamos priceMax da API: lá ele é o teto entre variações (cor,
    # tamanho), e comparar a variação cara com a barata inventaria desconto.
    des = [d if d > 0 else p for p, d in lidos]
    de_loja = round(sum(des) / len(des), 2) if media_real else des[-1]

    # Descontos enormes (70%+) NÃO são aparados: esse é o número que a própria
    # Shopee mostra na página. Se o card dissesse menos, o cliente chegaria lá
    # e veria um desconto MAIOR que o anunciado — quebra a confiança do lado
    # errado. Coerência com o destino vale mais que sobriedade.
    de, off = 0.0, 0
    candidato = max(de_loja, maior)
    if candidato > preco > 0:
        pct = int(round((1 - preco / candidato) * 100))
        if pct >= MIN_DESCONTO:
            de, off = candidato, pct

    # queda dentro do período: última leitura contra a primeira
    caiu = 0
    if media_real and vals[0] > 0:
        q = int(round((1 - vals[-1] / vals[0]) * 100))
        caiu = q if q >= 5 else 0

    return {
        "preco": preco,
        "obs": obs,
        "media": media_real,
        "de": de,
        "off": off,
        "caiu": caiu,
        "visto": _data_curta(dias[-1]),
        "visto_iso": dias[-1],
        "min": menor,
        "max": maior,
        # ⚠️ A SÉRIE SÓ SAI COM 3+ LEITURAS, e o piso é honestidade, não estilo.
        # Dois pontos viram uma reta: uma reta desenha "subindo" ou "descendo"
        # com a mesma convicção de vinte pontos, e a pessoa lê tendência onde
        # existe uma medição a mais. Abaixo de MIN_LEITURAS a resposta certa é
        # não desenhar nada.
        # 📌 É o mesmo dado que já alimentava `preco`/`min`/`max` — a diferença
        # é que agora ele pode ser VISTO. Média com data prova pouco; a linha
        # dos últimos dias prova sozinha se o preço de hoje é bom.
        "serie": [[d[5:], v] for d, v in zip(dias, vals)] if obs >= MIN_LEITURAS else [],
    }


def enriquecer(produtos: list, janela: int = JANELA_PADRAO) -> list:
    """Cola o resumo de preço em cada produto da vitrine, no lugar.

    Sem histórico, cai pro `preco` que o produto já trouxe da fila (a leitura
    do dia em que ele entrou) marcado como observação única. Sem nada disso,
    o produto fica sem preço e a vitrine simplesmente não mostra — é melhor
    não falar de preço do que falar errado.
    """
    dados = carregar()
    for p in produtos:
        link = p.get("link", "")
        # o título OFICIAL da Shopee veio de carona no health-check e está
        # guardado aqui. Quem usa é o bio_page_builder, pra consertar card com
        # nome sem sentido ("2 mil vendidos").
        oficial = (dados.get(link) or {}).get("nome")
        if oficial:
            p["titulo_oficial"] = oficial
        r = resumo(link, janela=janela, dados=dados)
        if not r and p.get("preco"):
            try:
                unico = float(p["preco"])
            except (TypeError, ValueError):
                unico = 0.0
            if unico > 0:
                r = {"preco": round(unico, 2), "obs": 1, "media": False,
                     "de": 0.0, "off": 0, "caiu": 0,
                     "visto": _data_curta(date.today().isoformat()),
                     "visto_iso": date.today().isoformat(),
                     "min": unico, "max": unico}
        p["preco_resumo"] = r
        if r:
            p["preco"] = r["preco"]
    return produtos


# ── CLI ───────────────────────────────────────────────────────────────────
def _ver(link_filtro: str = ""):
    dados = carregar()
    if not dados:
        print(f"histórico vazio ({ARQUIVO})")
        print("ele começa a encher sozinho na próxima rodada do deploy_site.py")
        return 0

    if link_filtro:
        r = resumo(link_filtro, dados=dados)
        reg = dados.get(link_filtro) or {}
        print(f"{reg.get('nome', '?')}\n{link_filtro}")
        for d in sorted((reg.get('leituras') or {})):
            p, dd = ler_leitura(reg['leituras'][d])
            print(f"   {d}  R$ {p:.2f}" + (f"   (de R$ {dd:.2f})" if dd else ""))
        print(f"\nresumo: {json.dumps(r, ensure_ascii=False)}")
        return 0

    total = sum(len(v.get("leituras") or {}) for v in dados.values())
    print(f"{len(dados)} produtos · {total} leituras · {ARQUIVO}\n")
    linhas = []
    for link, reg in dados.items():
        r = resumo(link, dados=dados)
        if not r:
            continue
        linhas.append((r["obs"], reg.get("nome", "?")[:44], r))
    for obs, nome, r in sorted(linhas, reverse=True):
        marca = "~" if r["media"] else " "
        extra = f"  caiu {r['caiu']}%" if r["caiu"] else ""
        de = f"  de R$ {r['de']:.2f} (-{r['off']}%)" if r["off"] else ""
        print(f"  {obs:2d} leituras  {marca}R$ {r['preco']:7.2f}{de}{extra}"
              f"   {r['visto']}   {nome}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Histórico de preços da vitrine")
    ap.add_argument("--ver", action="store_true", help="mostra o que já foi coletado")
    ap.add_argument("--link", default="", help="detalha um produto (com --ver)")
    ap.add_argument("--podar", action="store_true",
                    help=f"remove leitura com mais de {DIAS_GUARDADOS} dias")
    ap.add_argument("--simular", action="store_true", help="não grava nada")
    a = ap.parse_args()

    if a.podar:
        dados = carregar()
        antes = sum(len(v.get("leituras") or {}) for v in dados.values())
        dados = podar(dados=dados)      # sem links_vivos: só poda por idade
        depois = sum(len(v.get("leituras") or {}) for v in dados.values())
        print(f"leituras: {antes} -> {depois}")
        if not a.simular:
            salvar(dados)
        else:
            print("(simulação: nada gravado)")
        return 0

    return _ver(a.link)


if __name__ == "__main__":
    sys.exit(main())
