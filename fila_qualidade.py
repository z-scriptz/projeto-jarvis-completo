#!/usr/bin/env python3
# fila_qualidade.py -- produzir PRIMEIRO o que já tem material bom.
#
# POR QUE EXISTE (15/08)
# O dia 12/08 foi gasto tentando CONSERTAR foto ruim: coletar na Amazon
# (0/6 de identidade), no Mercado Livre (403), na Shopee (anti-bot), recortar
# o produto (medido: PIOROU, 15% → 25% de densidade de texto). Quatro becos,
# todos medidos.
#
# A pergunta barata veio depois: **de 20 produtos da fila, quantos JÁ têm foto
# limpa? 12.** Sessenta por cento. O esforço inteiro estava otimizando a
# minoria — e a saída não é consertar material ruim, é escolher o bom primeiro.
# Isso não custa ferramenta nova: os detectores existem (`asset_ranker`,
# `texto_queimado`), a fila existe. Falta a ORDEM.
#
# ⚠️ CHAVEADO POR LINK, NUNCA POR ÍNDICE. O gravador insere no topo da fila
# (`fila.insert(0, ...)`), então o índice de um produto MUDA toda vez que a
# mineração roda — ~11 vezes por dia. Um ranking que guardasse "produza o
# índice 7" mandaria produzir outro produto poucas horas depois, sem errar
# nenhuma linha de código e sem avisar ninguém. O link é a identidade estável.
#
# ⚠️ LIMITADO POR PADRÃO. Cada produto sem veredito custa download + Gemini
# Vision. Deixar `--limite 0` como default é o mesmo erro que o `fila[:80]`
# escondia no `validar_fila` — rodada que não termina. O cache por link faz a
# segunda passada custar zero.
#
# O QUE ELE NÃO FAZ: não produz nada e não escreve na fila. Ele ordena e
# imprime o comando. Produzir continua sendo decisão de quem lê.
#
# Uso (na VPS, dentro de ~/jarvis):
#   .venv/bin/python fila_qualidade.py                 # avalia até 25 novos
#   .venv/bin/python fila_qualidade.py --limite 60
#   .venv/bin/python fila_qualidade.py --so-cache      # só mostra o que já sei
#   .venv/bin/python fila_qualidade.py --simular       # testa o encanamento

import argparse
import json
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CACHE = BASE_DIR / "shared" / "fila_qualidade.json"

# ordem de preferência para produzir. `nivel` vem do asset_ranker (A..D) e
# `texto` do texto_queimado — os dois já existem e já foram calibrados; aqui
# não se inventa métrica nova, só se ordena o que eles dizem.
PESO_NIVEL = {"A": 0, "B": 1, "C": 2, "D": 9}
# ⚠️ `nao_avaliado` NÃO é um degrau entre ressalva e reprovado — é ausência de
# medição. Fica no fim junto com o que foi reprovado, pra nunca subir no
# ranking por não ter sido medido.
PESO_TEXTO = {"aprovado": 0, "ressalva": 1, "reprovado": 9, "nao_avaliado": 8}


def _log(m):
    print(f"[qualidade] {m}", flush=True)


def _fila():
    """A fila, pelo mesmo caminho que o storyboard usa."""
    try:
        import storyboard as SB
        caminho = SB.FILA
    except Exception:
        caminho = BASE_DIR / "shared" / "produtos_fila.json"
    if not caminho.exists():
        raise SystemExit(f"[qualidade] não achei a fila em {caminho}")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return [x for x in dados if isinstance(x, dict)], caminho


def _urls(item: dict) -> list:
    vistas, saida = set(), []
    for u in [item.get("imagem")] + list(item.get("imagens") or []):
        if isinstance(u, str) and u.startswith("http") and u not in vistas:
            vistas.add(u)
            saida.append(u)
    return saida


def _carregar_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _salvar_cache(c: dict):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CACHE)          # troca atômica: cache pela metade é pior que nenhum


def _baixar(urls: list, destino: Path) -> list:
    import requests
    destino.mkdir(parents=True, exist_ok=True)
    caminhos = []
    for i, u in enumerate(urls):
        alvo = destino / f"{i}.jpg"
        try:
            r = requests.get(u, timeout=40,
                             headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200 or len(r.content) < 2048:
                continue
            alvo.write_bytes(r.content)
            caminhos.append(alvo)
        except Exception:
            continue
    return caminhos


def julgar(item: dict, pasta: Path) -> dict:
    """O veredito de UM produto, pelos detectores que já existem.

    Devolve sempre `avaliado`: produto sem foto e produto com foto ruim são
    coisas diferentes, e achatar os dois em "não presta" apaga justamente a
    informação que decide o que fazer com ele.
    """
    urls = _urls(item)
    if not urls:
        return {"avaliado": False, "motivo": "sem URL de foto na fila",
                "n_fotos": 0}

    fotos = _baixar(urls, pasta)
    if not fotos:
        return {"avaliado": False, "motivo": f"nenhuma das {len(urls)} URLs "
                                             f"baixou", "n_fotos": 0}

    nome = (item.get("campeao") or item.get("produto") or "")[:60]
    try:
        import asset_ranker as AR
        r = AR.avaliar([str(f) for f in fotos], nome)
    except Exception as e:
        return {"avaliado": False, "motivo": f"asset_ranker falhou: "
                                             f"{str(e)[:70]}", "n_fotos": len(fotos)}

    # ⚠️ A CHAVE É `texto_queimado` E O CAMPO É `pior` — lidos do
    # asset_ranker.py:176 e do texto_queimado.avaliar_varias, não chutados.
    # A 1ª versão escreveu `r.get("texto").get("veredito")`: chave inexistente
    # → {} → default "nao_avaliado". Os 12 produtos da 1ª rodada na VPS saíram
    # TODOS "nao_avaliado" por causa disso, e o ranking virou empate geral. O
    # default transformou "eu li errado" em "o detector não opinou", que é
    # exatamente o disfarce que o `nao_avaliado` já pregou em 12/08.
    tq = r.get("texto_queimado") or {}
    return {"avaliado": True, "n_fotos": len(fotos),
            "nivel": r.get("nivel", "?"),
            "texto": tq.get("pior", "nao_avaliado"),
            "fotos_usaveis": tq.get("usaveis"),
            "bloqueia": bool(tq.get("bloqueia")),
            "erro_texto": tq.get("erro", ""),
            "distintas": r.get("distintas"),
            "veredito": r.get("veredito", ""),
            "ts": int(time.time())}


def _julgar_simulado(item: dict, pasta: Path) -> dict:
    """Juiz de mentira para testar o ENCANAMENTO sem gastar cota nem rede.
    Determinístico pelo link, pra rodar duas vezes dar igual."""
    urls = _urls(item)
    if not urls:
        return {"avaliado": False, "motivo": "sem URL de foto na fila",
                "n_fotos": 0}
    h = sum(ord(c) for c in (item.get("link") or ""))
    return {"avaliado": True, "n_fotos": len(urls),
            "nivel": "ABCD"[h % 4],
            "texto": ["aprovado", "ressalva", "reprovado"][h % 3],
            "distintas": 1 + h % 3, "veredito": "(simulado)",
            "ts": int(time.time())}


def _chave_de_ordem(reg: dict):
    """Menor = produzir antes. Empate desfeito por mais fotos distintas."""
    return (PESO_NIVEL.get(reg.get("nivel"), 9),
            PESO_TEXTO.get(reg.get("texto"), 9),
            -(reg.get("distintas") or 0),
            -(reg.get("n_fotos") or 0))


def _produzivel(reg: dict) -> bool:
    return (reg.get("avaliado")
            and reg.get("nivel") != "D"
            and reg.get("texto") != "reprovado")


def main():
    p = argparse.ArgumentParser(
        description="Ordena a fila por qualidade do material que já existe.")
    p.add_argument("--limite", type=int, default=25,
                   help="quantos produtos NOVOS avaliar nesta rodada "
                        "(padrão 25; cada um custa download + Vision)")
    p.add_argument("--so-cache", action="store_true",
                   help="não avalia nada novo: só mostra o que já está no cache")
    p.add_argument("--refazer", action="store_true",
                   help="ignora o cache e reavalia (gasta cota de novo)")
    p.add_argument("--simular", action="store_true",
                   help="juiz de mentira, para testar o encanamento")
    p.add_argument("--top", type=int, default=15,
                   help="quantos mostrar na lista final")
    args = p.parse_args()

    itens, caminho = _fila()
    _log(f"{len(itens)} itens na fila ({caminho})")

    cache = {} if args.refazer else _carregar_cache()
    juiz = _julgar_simulado if args.simular else julgar

    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="fila_qual_"))
    novos, pulados_sem_link = 0, 0
    try:
        for item in itens:
            link = (item.get("link") or "").strip()
            if not link:
                # sem link o produto não tem identidade estável — e o índice
                # não serve, porque muda a cada gravação da mineração
                pulados_sem_link += 1
                continue
            if link in cache and not args.refazer:
                continue
            if args.so_cache or novos >= args.limite:
                continue
            cache[link] = juiz(item, tmp / str(novos))
            cache[link]["nome"] = (item.get("campeao")
                                   or item.get("produto") or "")[:70]
            novos += 1
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    if novos:
        _salvar_cache(cache)
        _log(f"{novos} produto(s) avaliado(s) nesta rodada · cache em "
             f"{CACHE.name}")

    # ── o que a fila tem, hoje ──────────────────────────────────────────────
    na_fila = {(i.get("link") or "").strip() for i in itens}
    conhecidos = {k: v for k, v in cache.items() if k in na_fila}
    faltam = len([i for i in itens
                  if (i.get("link") or "").strip()
                  and (i.get("link") or "").strip() not in cache])

    avaliados = {k: v for k, v in conhecidos.items() if v.get("avaliado")}
    sem_material = {k: v for k, v in conhecidos.items() if not v.get("avaliado")}

    print()
    print(f"  fila: {len(itens)}  ·  já julgados: {len(conhecidos)}  ·  "
          f"faltam julgar: {faltam}")
    if pulados_sem_link:
        print(f"  {pulados_sem_link} item(ns) sem link — sem identidade "
              f"estável, ficam de fora do ranking")
    if faltam:
        print(f"  → rode de novo com --limite {min(faltam, 60)} para "
              f"cobrir mais")

    if not avaliados:
        print()
        _log("nada avaliado ainda. Rode sem --so-cache para julgar a fila.")
        return 1

    prontos = {k: v for k, v in avaliados.items() if _produzivel(v)}
    print()
    print(f"  ✅ PRODUZÍVEIS AGORA: {len(prontos)}/{len(avaliados)} "
          f"({100 * len(prontos) / len(avaliados):.0f}% do que foi julgado)")
    if sem_material:
        print(f"  ⚠️  {len(sem_material)} sem material utilizável "
              f"(foto que não baixou ou fila sem URL)")
    print()

    # ── a medição de TEXTO aconteceu? ───────────────────────────────────────
    # Com 1 foto por produto, `nivel` é C pra todo mundo e `distintas` é 1 pra
    # todo mundo: o ÚNICO critério que separa produto bom de produto ruim é o
    # texto queimado. Se ele não rodou, não existe ranking — existe uma lista
    # na ordem em que a fila estava. Dizer isso é obrigatório.
    dist = {}
    for reg in avaliados.values():
        dist[reg.get("texto", "?")] = dist.get(reg.get("texto", "?"), 0) + 1
    print("  texto queimado: " + " · ".join(
        f"{k}: {v}" for k, v in sorted(dist.items(), key=lambda x: -x[1])))

    cegos = dist.get("nao_avaliado", 0)
    if cegos >= max(1, len(avaliados) // 2):
        print()
        _log(f"⚠️  MEDIÇÃO DE TEXTO NÃO ACONTECEU em {cegos}/{len(avaliados)}")
        erros = {r.get("erro_texto") for r in avaliados.values()
                 if r.get("erro_texto")}
        for e in list(erros)[:3]:
            _log(f"     motivo: {e}")
        if not erros:
            _log("     sem erro registrado — provável GEMINI_API_KEY ausente "
                 "ou cota estourada (o detector devolve nao_avaliado nos dois)")
        _log("   Com 1 foto por produto, o nível é C e a diversidade é 1 pra "
             "TODOS.")
        _log("   Sem o texto, o que segue NÃO é ranking de qualidade — é a "
             "fila na ordem em que estava. Resolva o detector e rode com "
             "--refazer.")

    ordem = sorted(prontos.items(), key=lambda kv: _chave_de_ordem(kv[1]))
    for i, (link, reg) in enumerate(ordem[:args.top], 1):
        print(f"  {i:2}. [{reg.get('nivel')}·{reg.get('texto'):9}] "
              f"{reg.get('distintas') or '?'} distinta(s)  "
              f"{reg.get('nome', '')[:52]}")

    if ordem:
        melhor = ordem[0][0]
        print()
        print("  Para produzir o melhor da fila AGORA:"
              if not cegos >= max(1, len(avaliados) // 2)
              else "  O PRIMEIRO da lista (sem medição de texto, é só o "
                   "primeiro):")
        print(f"    {sys.executable} piloto.py --fila-link '{melhor}'")
        print()
        print("  ⚠️ use --fila-link, não --fila N: o índice muda a cada")
        print("     gravação da mineração, e o link não.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
