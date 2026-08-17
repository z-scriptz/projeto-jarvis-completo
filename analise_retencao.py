#!/usr/bin/env python3
# analise_retencao.py -- o que os 80 posts já dizem, antes de construir nada.
#
# POR QUE EXISTE (15/08)
# Hoje o `reach_agent` passou a trazer `ig_reels_avg_watch_time`, e a primeira
# rodada deu **80/80 posts com retenção, média 6,0s**. Isso é o primeiro dado
# de COMPORTAMENTO DE AUDIÊNCIA que o projeto tem — até ontem havia alcance
# (quantos viram) e venda (9 em 30 dias), e nada sobre o que a pessoa faz
# durante o vídeo.
#
# ⚠️ E ELE JÁ ME CORRIGIU. Eu tinha lido 3,57s de UM post e escrito que "a
# pessoa sai em 3,5s, então variedade visual no meio do vídeo não pode ser o
# gargalo". Com n=80 a média é 6,0s — 27-43% de um vídeo de 14-22s. A hipótese
# não morreu, mas nasceu de n=1 e não sustenta o peso que eu dei a ela.
#
# Por isso este arquivo mostra DISTRIBUIÇÃO, não média. Média esconde
# bimodalidade: "6,0s" pode ser 80 posts em 6s, ou 40 posts em 2s e 40 em 10s,
# e essas duas realidades pedem ações opostas.
#
# ⚠️ O QUE ELE NÃO FAZ: não conclui causalidade. Retenção alta e alcance alto
# andarem juntos não diz quem puxa quem — o algoritmo do Instagram entrega mais
# o que retém, e mais entrega muda o público que assiste. Ele mostra o que há e
# nomeia as explicações alternativas.
#
# Só stdlib. Não escreve nada.
#
# Uso (na VPS):  python3 analise_retencao.py
#                python3 analise_retencao.py --top 8

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
REACH = BASE / "shared" / "reach.jsonl"


def _log(m):
    print(f"[retencao] {m}", flush=True)


def _carregar() -> list:
    """Dedup por media_id, ficando com a leitura de MAIOR alcance.

    Mesma regra do `ceo_agent._ler_reach`: o agente roda todo dia e o alcance
    só cresce, então a última leitura é a mais completa. Contar o mesmo post
    várias vezes inflaria qualquer média aqui.
    """
    if not REACH.exists():
        raise SystemExit(f"[retencao] não achei {REACH}")
    por_id = {}
    for linha in REACH.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(linha)
        except Exception:
            continue
        mid = r.get("media_id")
        if not mid:
            continue
        ant = por_id.get(mid)
        if ant is None or (r.get("reach") or 0) >= (ant.get("reach") or 0):
            por_id[mid] = r
    return list(por_id.values())


def _pct(vals, p):
    if not vals:
        return None
    v = sorted(vals)
    k = (len(v) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


# ⚠️ A RÉGUA VEM DO `hook_alana`, NÃO É COPIADA. Quem GERA o hook e quem MEDE
# o hook precisam usar exatamente a mesma definição de "estreito" — duas cópias
# viram duas réguas na primeira edição, e aí a análise aprova o que o gerador
# rejeita (ou pior: o contrário, calado). Mesmo padrão do `_proibido`, que
# importa `storyboard.PROIBIDO` em vez de repetir a lista.
try:
    sys.path.insert(0, str(BASE))
    from hook_alana import PORTAS_DE_PUBLICO as _PORTAS
except Exception:
    _PORTAS = ()


def _norm_hook(t: str) -> str:
    """Chave de comparação: sem emoji, sem tag, sem pontuação, minúsculo."""
    t = (t or "").replace("{tag}", " ")
    t = "".join(ch for ch in t if ch.isalnum() or ch.isspace())
    return " ".join(t.lower().split())


_RESERVA_NORM = None


def _origem_do_hook(hook: str) -> str:
    """"reserva" se o hook é uma das frases fixas do `HOOKS_RESERVA`.

    O pool de reserva existe pra quando o Gemini cai. Ele é FIXO, então
    aparece literal e repetido no ledger; hook gerado sai único por vídeo.
    Comparar normalizado (sem emoji/tag) é o suficiente pra separar os dois.

    Devolve "?" se nem der pra importar o `hook_alana` — porque chutar
    "gerado" aqui inflaria justamente o número que a gente quer vigiar.
    """
    global _RESERVA_NORM
    if _RESERVA_NORM is None:
        try:
            sys.path.insert(0, str(BASE))
            import hook_alana as HA
            _RESERVA_NORM = {_norm_hook(h)
                             for lista in HA.HOOKS_RESERVA.values()
                             for h in lista}
        except Exception:
            _RESERVA_NORM = set()
    if not _RESERVA_NORM:
        return "?"
    return "reserva" if _norm_hook(hook) in _RESERVA_NORM else "gerado"


def _amplitude(hook: str) -> str:
    """"fecha_porta" se o hook exige pertencer a um grupo; "nao_fecha" senão.

    ⚠️ OS RÓTULOS MUDARAM DE NOME EM 16/08, E A MUDANÇA É O ACHADO. Antes eram
    "estreito"/"amplo", e o Dre derrubou isso com um exemplo: a saída rotulou
    "Odeio boné que amassa o cabelo!" como AMPLO — não tem "pra quem", passa na
    régua, e é estreitíssimo de assunto. **Ausência de porta não é amplitude.**

    No exemplo dele a frase INTEIRA muda de vocabulário:
        estreito: "se você tem um golden que come tudo, ensino isso"
        amplo   : "quer um cachorro que não come nada do chão sem sua
                   permissão? siga esses passos"
    Nenhuma palavra sobrevive; o substantivo sobe um degrau (golden→cachorro)
    e a frase passa a falar do RESULTADO, não de quem a pessoa é. Nada disso é
    detectável por lista de expressões proibidas.

    Então esta função continua útil e passa a se chamar pelo que faz: ela acha
    a PORTA. Medir amplitude de verdade precisaria julgar vocabulário e
    especificidade do substantivo — provavelmente com o próprio Gemini, e sem
    isso é melhor um rótulo honesto e estreito do que um rótulo bonito e falso.

    ⚠️ HEURÍSTICA, e conservadora: na dúvida devolve "nao_fecha". Errar pra
    "fecha_porta" criaria um balde pequeno e sujo, e balde sujo dá diferença
    falsa justamente na direção que a hipótese prevê — o jeito mais fácil de
    "confirmar" uma tese com a própria régua. Por isso quem chama IMPRIME
    exemplos dos dois lados: tem que dar pra conferir a olho.

    ⚠️ E MESMO COMO DETECTOR DE PORTA ela pega só um dos dois recortes:
      (1) recorte de PÚBLICO  — "se você tem um golden que come tudo"   ← pega
      (2) recorte de OBJETO   — "review do livro Pai Rico e Pai Pobre"  ← não
    Descobri montando o teste: escrevi `esperava amplo` pro exemplo do livro e
    o teste "passou" 12/12 — porque o gabarito era a minha própria limitação.
    Teste que herda o ponto cego do código passa sempre. Fica assim porque
    nossos hooks não nomeiam o produto (o curiosity-gap existe pra escondê-lo);
    se um dia passarem a citar marca/modelo, falta um segundo detector.
    """
    if not _PORTAS:
        return "?"      # sem a régua não há veredito — "nao_fecha" seria chute
    t = (hook or "").lower()
    for a, b in (("á", "a"), ("â", "a"), ("ã", "a"), ("à", "a"), ("é", "e"),
                 ("ê", "e"), ("í", "i"), ("ó", "o"), ("ô", "o"), ("õ", "o"),
                 ("ú", "u"), ("ç", "c")):
        t = t.replace(a, b)
    t = " " + " ".join(t.split()) + " "
    return "fecha_porta" if any(p in t for p in _PORTAS) else "nao_fecha"


def _spearman(xs, ys):
    """Correlação por POSTO, sem numpy. Posto e não valor porque alcance tem
    cauda longa (um post de 1.288 contra dezenas de 100) e Pearson viraria
    refém desse ponto."""
    n = len(xs)
    if n < 5:
        return None

    def postos(v):
        ordem = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[ordem[j + 1]] == v[ordem[i]]:
                j += 1
            media = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[ordem[k]] = media
            i = j + 1
        return r

    rx, ry = postos(xs), postos(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) *
           sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(num / den, 3) if den else None


def main():
    p = argparse.ArgumentParser(
        description="O que os posts já medidos dizem sobre retenção.")
    p.add_argument("--top", type=int, default=5)
    args = p.parse_args()

    posts = _carregar()
    com = [r for r in posts
           if isinstance(r.get("retencao_s"), (int, float))]

    print()
    print(f"  {len(posts)} posts únicos no reach.jsonl · "
          f"{len(com)} com retenção medida")
    if not com:
        _log("nenhum post com `retencao_s` ainda — rode o reach_agent "
             "atualizado primeiro (só as coletas novas trazem o campo)")
        return 1
    if len(com) < len(posts):
        print(f"  ⚠️  {len(posts) - len(com)} post(s) SEM retenção — são as "
              f"coletas feitas antes do conserto do `plays`. Ficam de fora "
              f"das contas abaixo, não entram como zero.")

    # ⚠️ POST NOVO DEMAIS NÃO TEM RETENÇÃO, TEM RUÍDO. Na rodada real apareceu
    # um `0.9s com reach=0`: ninguém viu, e ainda assim veio um tempo médio.
    # Insights de post recém-publicado ainda não amadureceram, e deixar isso no
    # bolo puxa a cauda de baixo sem significar nada.
    MIN_ALCANCE = 10
    crus = len(com)
    com = [r for r in com
           if not isinstance(r.get("reach"), int) or r["reach"] >= MIN_ALCANCE]
    if crus > len(com):
        print(f"  ⚠️  {crus - len(com)} post(s) com alcance < {MIN_ALCANCE} "
              f"fora da conta — insight que ainda não amadureceu não é "
              f"retenção baixa, é ausência de dado.")

    vals = [r["retencao_s"] for r in com]

    # ── distribuição, não média ─────────────────────────────────────────────
    print()
    print("  ── DISTRIBUIÇÃO DA RETENÇÃO (segundos) ──")
    print(f"     mínimo {min(vals):5.1f}   p25 {_pct(vals, .25):5.1f}   "
          f"mediana {_pct(vals, .5):5.1f}   p75 {_pct(vals, .75):5.1f}   "
          f"máximo {max(vals):5.1f}")
    print(f"     média  {st.mean(vals):5.1f}   desvio {st.pstdev(vals):5.1f}")

    # histograma cru: é o que denuncia bimodalidade, que a média esconde
    largura = max(1.0, (max(vals) - min(vals)) / 10 or 1.0)
    faixas = defaultdict(int)
    for v in vals:
        faixas[int((v - min(vals)) // largura)] += 1
    print()
    for i in range(10):
        ini = min(vals) + i * largura
        n = faixas.get(i, 0)
        if n or i == 0:
            print(f"     {ini:5.1f}-{ini + largura:4.1f}s │"
                  f"{'█' * min(40, n)} {n}")

    mediana = _pct(vals, .5)
    if abs(st.mean(vals) - mediana) > 0.15 * st.mean(vals):
        print()
        print(f"  ⚠️  média ({st.mean(vals):.1f}s) longe da mediana "
              f"({mediana:.1f}s) — a distribuição é torta. Use a MEDIANA pra "
              f"falar do post típico.")

    # ── por conta ───────────────────────────────────────────────────────────
    por_conta = defaultdict(list)
    for r in com:
        por_conta[r.get("handle") or r.get("nicho") or "?"].append(r)
    print()
    print("  ── POR CONTA ──")
    print(f"     {'conta':22} {'posts':>5} {'retenção':>10} {'alcance':>9}")
    for h, rs in sorted(por_conta.items(),
                        key=lambda kv: -_pct([x["retencao_s"] for x in kv[1]], .5)):
        ret = _pct([x["retencao_s"] for x in rs], .5)
        alc = [x.get("reach") for x in rs if isinstance(x.get("reach"), int)]
        print(f"     {h[:22]:22} {len(rs):5} {ret:9.1f}s "
              f"{(_pct(alc, .5) if alc else 0):9.0f}")

    # ── retenção × alcance ──────────────────────────────────────────────────
    pares = [(r["retencao_s"], r["reach"]) for r in com
             if isinstance(r.get("reach"), int)]
    if len(pares) >= 5:
        rho = _spearman([a for a, _ in pares], [b for _, b in pares])
        print()
        print(f"  ── RETENÇÃO × ALCANCE ──   ρ (Spearman) = {rho}   "
              f"n = {len(pares)}")
        if rho is not None:
            if rho > 0.4:
                print("     Andam juntos. ⚠️ E isso NÃO diz quem puxa quem: o")
                print("     algoritmo entrega mais o que retém, e mais entrega")
                print("     muda quem assiste. Correlação aqui é pista, não causa.")
            elif rho < -0.2:
                print("     Andam em sentidos OPOSTOS — inesperado o bastante")
                print("     pra checar se o alcance alto veio de outra origem.")
            else:
                print("     Praticamente independentes neste volume. Ou seja:")
                print("     segurar mais o espectador, aqui, ainda não está")
                print("     comprando mais entrega.")

        # ⚠️ A CORRELAÇÃO AGREGADA PODE SER ARTEFATO DAS CONTAS. Se uma conta
        # tem alcance alto E retenção um pouco maior, o ρ do bolo inteiro sobe
        # sem que exista relação nenhuma DENTRO de cada conta — é o paradoxo de
        # Simpson na prática. Medido em 15/08: retenção quase igual entre as
        # quatro contas (5,8 a 6,4s, desvio 2,2) e alcance 3,4× diferente. Com
        # esse formato, olhar só o agregado é a receita pra ver causa onde há
        # composição.
        print()
        print("     dentro de cada conta (é aqui que a relação é real ou some):")
        dentro = []
        for h, rs in sorted(por_conta.items()):
            pr = [(r["retencao_s"], r["reach"]) for r in rs
                  if isinstance(r.get("reach"), int)]
            if len(pr) < 5:
                print(f"       {h[:22]:22} n={len(pr)} — poucos posts pra medir")
                continue
            rh = _spearman([a for a, _ in pr], [b for _, b in pr])
            dentro.append(rh)
            print(f"       {h[:22]:22} ρ = {rh:>6}   (n={len(pr)})")
        if dentro:
            medio = round(sum(dentro) / len(dentro), 3)
            # ⚠️ TRÊS CASOS, NÃO DOIS. A 1ª versão só perguntava "o agregado é
            # maior que o interno?" e, com os DOIS perto de zero, imprimia
            # "a relação se sustenta" — anunciando que se sustenta uma relação
            # que não existe. Ausência de relação não é confirmação de relação.
            if rho is None or abs(rho) < 0.25:
                print(f"     agregado fraco ({rho}) — não há relação a "
                      f"explicar. Dentro das contas: média {medio}.")
            elif abs(rho) - abs(medio) > 0.25:
                print(f"     ⚠️  agregado {rho} × média dentro das contas "
                      f"{medio}: boa parte do agregado é DIFERENÇA ENTRE "
                      f"CONTAS, não relação entre posts.")
            else:
                print(f"     a relação se sustenta dentro das contas "
                      f"(média {medio}) — não é só composição.")

    # ── o HOOK real, vindo do ledger ────────────────────────────────────────
    # O `caption` do reach.jsonl é a legenda do Instagram. O hook que aparece
    # NA TELA é outro texto, e quem o guarda é o posts_ledger. Sem essa junção
    # a análise fala de legenda achando que fala de hook.
    #
    # ⚠️ O LEDGER NÃO TEM `media_id`, então a junção é pela legenda. Junção
    # aproximada que falha em silêncio inventa padrão — por isso a taxa de
    # casamento é impressa antes de qualquer agrupamento.
    LEDGER = BASE / "shared" / "posts_ledger.jsonl"
    if LEDGER.exists():
        def _chave(t):
            return "".join(ch for ch in (t or "").lower() if ch.isalnum())[:60]

        por_legenda = {}
        for linha in LEDGER.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(linha)
            except Exception:
                continue
            k = _chave(r.get("legenda"))
            if k:
                por_legenda[k] = r

        casados = 0
        for r in com:
            lig = por_legenda.get(_chave(r.get("caption")))
            if lig:
                casados += 1
                r["_hook"] = lig.get("hook") or ""
                r["_categoria"] = lig.get("categoria") or ""
                r["_origem_hook"] = _origem_do_hook(r["_hook"])

        # ── GERADO pelo Gemini, ou RESERVA de quando ele cai? ───────────────
        # ⚠️ ISTO PRECISA VIR ANTES DA TABELA DE MOLDES, porque decide o que a
        # tabela significa. O `HOOKS_RESERVA` é um pool FIXO de ~107 frases
        # usado quando o Gemini falha (e o ROADMAP registra 503 intermitente).
        # Frase fixa REPETE literal; hook gerado é único a cada vídeo.
        #
        # Consequência que eu não tinha visto: o corte `n>=5` da tabela abaixo
        # **seleciona reserva por construção**. O que repete o bastante pra
        # juntar n=5 é justamente o que não foi gerado. Medido em 16/08 — dos 3
        # moldes que passaram o corte, 2 são do pool de reserva. O "molde de
        # hook" que a gente vinha lendo era, em boa parte, o comportamento do
        # FALLBACK, não do gerador.
        _res = {k: 0 for k in ("gerado", "reserva", "?")}
        for r in com:
            if r.get("_hook"):
                _res[r.get("_origem_hook", "?")] += 1
        tot = sum(_res.values())
        if tot:
            print()
            print(f"  ── ORIGEM DO HOOK ──   gerado {_res['gerado']} · "
                  f"reserva (Gemini caiu) {_res['reserva']}"
                  + (f" · indefinido {_res['?']}" if _res["?"] else ""))
            if _res["reserva"]:
                pc = 100 * _res["reserva"] / tot
                print(f"     {pc:.0f}% dos posts medidos saíram com hook de "
                      f"RESERVA — frase fixa, não escrita pro produto.")
                if pc >= 25:
                    print("     ⚠️  Melhorar o gerador só alcança o resto. "
                          "Esta fatia depende do Gemini ficar de pé.")
                ret_g = [x["retencao_s"] for x in com
                         if x.get("_origem_hook") == "gerado"]
                ret_r = [x["retencao_s"] for x in com
                         if x.get("_origem_hook") == "reserva"]
                if len(ret_g) >= 8 and len(ret_r) >= 8:
                    print(f"     retenção: gerado {_pct(ret_g, .5):.1f}s "
                          f"(n={len(ret_g)})  ·  reserva "
                          f"{_pct(ret_r, .5):.1f}s (n={len(ret_r)})")

        print()
        print(f"  ── HOOK (do posts_ledger) ──   casaram {casados}/{len(com)} "
              f"posts pela legenda")
        if casados < len(com) * 0.5:
            print("     ⚠️  menos da metade casou. O agrupamento abaixo fala de "
                  "uma AMOSTRA enviesada — provavelmente os posts mais novos, "
                  "que o ledger tem. Não leia como retrato da frota.")

        if casados >= 10:
            # agrupa pelas 4 primeiras palavras do hook: é o MOLDE, e é o que
            # se repete entre produções diferentes
            grupos = defaultdict(list)
            for r in com:
                h = (r.get("_hook") or "").strip()
                if h:
                    grupos[" ".join(h.split()[:4]).lower()].append(r["retencao_s"])
            uteis = {k: v for k, v in grupos.items() if len(v) >= 5}
            if uteis:
                print(f"     molde de hook (só grupos com n>=5, de "
                      f"{len(grupos)} moldes vistos):")
                for k, v in sorted(uteis.items(),
                                   key=lambda kv: -_pct(kv[1], .5)):
                    print(f"       {_pct(v, .5):5.1f}s  n={len(v):3}  "
                          f"\"{k}…\"")
                print("     ⚠️ moldes com n<5 ficaram de fora: com 2-3 posts a "
                      "mediana é anedota.")
                # ⚠️ LISTA ORDENADA PARECE RANKING. E com n=5..9 sobre um
                # desvio de ~2s, a mediana de cada grupo balança mais do que a
                # distância entre os grupos — ordenar sem dizer isso convida a
                # concluir "use o molde do topo", que é o tipo de conclusão que
                # este projeto já pagou caro pra aprender a não tirar.
                # Erro-padrão da MEDIANA ~ 1.253 * desvio / raiz(n).
                medianas = [_pct(v, .5) for v in uteis.values()]
                menor_n = min(len(v) for v in uteis.values())
                erro_um = 1.253 * st.pstdev(vals) / (menor_n ** 0.5)
                # ⚠️ COMPARAR O MAIOR COM O MENOR DE k GRUPOS NÃO É COMPARAR
                # DOIS. Quanto mais moldes na tabela, maior a distância entre
                # os extremos SÓ POR ACASO. A 1ª versão usava o erro de UMA
                # mediana e, testada com moldes rigorosamente iguais, chamou
                # ruído de "sugestivo". Amplitude esperada de k medianas sob
                # acaso ≈ erro × d(k), com d tabelado.
                D = {2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326, 6: 2.534}
                k = len(uteis)
                ruido = erro_um * D.get(k, 2.7)
                espalha = max(medianas) - min(medianas)
                print(f"     espalhamento entre {k} moldes: {espalha:.1f}s   "
                      f"esperado só por acaso: ±{ruido:.1f}s "
                      f"(n={menor_n}, erro de uma mediana ±{erro_um:.1f}s)")
                if espalha < ruido:
                    print("     ⚠️  O ESPALHAMENTO É MENOR QUE O RUÍDO — nenhum "
                          "molde se separa dos outros. A ordem acima é acaso; "
                          "não escolha hook por ela.")
                elif espalha < 2 * ruido:
                    print("     ⚠️  espalhamento da ordem do ruído — sugestivo, "
                          "longe de conclusivo. Precisa de mais posts por "
                          "molde, não de mais moldes.")
                else:
                    print("     o espalhamento supera o ruído: vale testar o "
                          "molde do topo contra o da base, de propósito.")
            else:
                print(f"     nenhum molde com n>=5 ({len(grupos)} moldes em "
                      f"{casados} posts) — variedade demais pra agrupar ainda.")

        # ── AMPLO × ESTREITO: a hipótese da Ava Yuergens, no eixo certo ─────
        # A tabela de moldes acima mede RETENÇÃO, e a afirmação dela é sobre
        # DISTRIBUIÇÃO: "se você filtrar muita gente no começo, o algoritmo
        # entende que o vídeo é ruim e não distribui" → gancho estreito não
        # perde watch time de quem ficou, perde ALCANCE. Testar a hipótese na
        # retenção seria medir no eixo errado e concluir "não tem efeito".
        #
        # ⚠️ E O AGRUPAMENTO EM 2 BALDES É O QUE DÁ POTÊNCIA. A tabela de
        # moldes trabalha com n=5..9 por grupo, onde nada se separa do ruído
        # (medido: espalhamento 0,8s contra ±1,0s). Dois baldes juntam os
        # mesmos posts em grupos ~10x maiores — é a MESMA amostra, com uma
        # pergunta que ela consegue responder.
        if casados >= 10:
            print()
            print("  ── O HOOK FECHA A PORTA? (hipótese da Ava Yuergens) ──")
            print("     ⚠️ isto mede a PORTA, não a amplitude. 'não fecha' "
                  "NÃO quer dizer amplo:")
            print("        'Odeio boné que amassa o cabelo' passa aqui e "
                  "é estreito de assunto.")
            baldes = defaultdict(list)
            for r in com:
                h = (r.get("_hook") or "").strip()
                if h:
                    baldes[_amplitude(h)].append(r)

            # ⚠️ A CLASSIFICAÇÃO É HEURÍSTICA, então ela se mostra. Regra que
            # rotula em silêncio inventa o resultado que o rótulo já continha.
            for nome in ("fecha_porta", "nao_fecha"):
                rs = baldes.get(nome) or []
                if not rs:
                    continue
                ret = [x["retencao_s"] for x in rs]
                alc = [x["reach"] for x in rs if isinstance(x.get("reach"), int)]
                print(f"     {nome:11} n={len(rs):3}  "
                      f"retenção {_pct(ret, .5):4.1f}s  "
                      f"alcance {_pct(alc, .5):6.0f}" if alc else
                      f"     {nome:11} n={len(rs):3}  "
                      f"retenção {_pct(ret, .5):4.1f}s  alcance —")
                for x in rs[:2]:
                    print(f"                 ex: \"{(x.get('_hook') or '')[:52]}\"")

            e, a = (baldes.get("fecha_porta") or [],
                    baldes.get("nao_fecha") or [])
            if len(e) >= 8 and len(a) >= 8:
                ae = [x["reach"] for x in e if isinstance(x.get("reach"), int)]
                aa = [x["reach"] for x in a if isinstance(x.get("reach"), int)]
                if len(ae) >= 8 and len(aa) >= 8:
                    dif = _pct(aa, .5) - _pct(ae, .5)
                    # ⚠️ ALCANCE TEM CAUDA LONGA: o desvio é inflado por poucos
                    # posts grandes, então este piso de ruído sai LARGO. Isso
                    # torna o teste conservador — "não separou" aqui é fraco,
                    # mas "separou" seria forte.
                    juntos = ae + aa
                    erro = 1.253 * st.pstdev(juntos) / (min(len(ae), len(aa)) ** 0.5)
                    ruido = erro * 1.128           # d(k) para k=2 baldes
                    print(f"     diferença de alcance (não-fecha − fecha): "
                          f"{dif:+.0f}   ruído esperado: ±{ruido:.0f}")
                    if abs(dif) < ruido:
                        print("     ⚠️  DENTRO DO RUÍDO — estes dados NÃO "
                              "confirmam nem refutam a tese. Não mude a "
                              "estratégia de hook com base nesta linha.")
                    else:
                        lado = "quem NÃO fecha" if dif > 0 else "quem FECHA"
                        print(f"     o balde de {lado} alcança mais, "
                              f"acima do ruído. Ainda é observação, não "
                              f"experimento: ninguém sorteou qual post levou "
                              f"qual gancho.")
            else:
                print(f"     ⚠️  baldes pequenos demais (fecha={len(e)}, "
                      f"não-fecha={len(a)}) — precisa de ≥8 de cada lado. "
                      f"Sem isso eu não comparo.")
    else:
        print()
        print("  ── HOOK ──  posts_ledger.jsonl não existe: sem ele só dá pra "
              "olhar legenda, que não é o texto da tela.")

    # ── extremos, com o texto ───────────────────────────────────────────────
    ordem = sorted(com, key=lambda r: -r["retencao_s"])
    print()
    print(f"  ── {args.top} QUE MAIS SEGURARAM ──")
    for r in ordem[:args.top]:
        print(f"     {r['retencao_s']:5.1f}s  r={r.get('reach', '?'):>5}  "
              f"{(r.get('caption') or '')[:58]}")
    print()
    print(f"  ── {args.top} QUE MENOS SEGURARAM ──")
    for r in ordem[-args.top:]:
        print(f"     {r['retencao_s']:5.1f}s  r={r.get('reach', '?'):>5}  "
              f"{(r.get('caption') or '')[:58]}")

    print()
    _log("⚠️ nada aqui é causa. São 80 posts, sem variação controlada: os "
         "vídeos diferem em hook, produto, horário e conta ao mesmo tempo.")
    _log("   Serve pra escolher a PRÓXIMA pergunta, não pra responder "
         "nenhuma.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
