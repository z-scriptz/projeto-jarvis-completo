#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# diag_contas.py — POR QUE UMA CONTA NÃO ESTÁ POSTANDO.
#
# ⚠️ NASCEU DE UMA PERGUNTA QUE LEVOU SEMANAS PRA SER RESPONDIDA (25/08): o
# @topshoppet_ não posta há dias e ninguém sabia dizer em que ponto da esteira
# ele parava. O vigia avisa que a conta está parada — e não avisa POR QUÊ,
# porque ele olha o resultado (o feed), não a máquina.
#
# E as causas possíveis moram em arquivos diferentes, o que é justamente o que
# torna o diagnóstico caro na mão:
#
#   contas.json          a conta existe? está `"ativa": false`?
#   roteador_contas.py   existe palavra-chave que mande produto pra ela?
#   produtos_fila.json   sobrou produto do nicho dela na fila?
#   pronto_para_postar/  tem pacote pronto esperando?
#   historico            o pacote saiu ou está encalhado?
#
# ⚠️ E EU CHUTEI ERRADO ANTES DE MEDIR. Achei que era `"ativa": false` — a
# causa estava até documentada no daemon desde 11/08 — e a primeira rodada
# mostrou pet com `ativa: sim`, 4 pacotes PRONTOS e o último post 19 dias
# atrás. A causa documentada era a causa ANTIGA. Por isso este arquivo existe:
# a explicação plausível e a explicação verdadeira se pareciam demais.
#
# ⚠️ O QUE ELE TEM QUE SEPARAR, e são coisas bem diferentes:
#
#   desligada  `"ativa": false` — invisível em toda ferramenta menos o daemon.
#              O vigia reporta a conta como parada; a produção nem soube dela.
#   sem insumo nada na fila, nada pronto — o problema está ANTES da postagem.
#   com fome   pacote pronto e a vez não vem. Com `post_por_conta` DESLIGADO o
#              daemon posta 1 pacote por slot NO TOTAL: quem tem estoque
#              pequeno nunca alcança a frente de uma fila funda.
#   órfã       pacote pronto sem `conta.json` legível. Não tem destino: só
#              envelhece na esteira até o expurgo por validade.
#
# As três últimas parecem idênticas de fora — "a conta não posta" — e pedem
# ações opostas. Confundi-las custa dias.
#
# USO (na VPS):
#   .venv/bin/python diag_contas.py
#   .venv/bin/python diag_contas.py pet     # só uma conta, com detalhe

import json
import sys
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRONTO = BASE / "pronto_para_postar"
CONFIG = BASE / "shared" / "content_plans" / "agendador_config.json"
HIST = BASE / "shared" / "content_plans" / "agendador_historico.json"
VALIDACAO = BASE / "shared" / "content_plans" / "validacao_fila.json"
LEDGER = BASE / "shared" / "posts_ledger.jsonl"
METRICAS = BASE / "shared" / "metricas_posts.jsonl"

# ⚠️ o produtos_fila.json mora em `shared/` na VPS e na raiz em algumas cópias.
# O vigia já resolve assim; se aqui eu olhasse só um dos dois, o diagnóstico
# diria "fila vazia" sobre uma fila cheia — o pior erro que ele pode cometer.
FILAS = (BASE / "shared" / "produtos_fila.json", BASE / "produtos_fila.json")


def _json(caminho: Path, padrao):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except Exception:
        return padrao


def _contas() -> dict:
    return _json(BASE / "contas.json", {}) or {}


def _nicho_da_chave(chave: str, conta: dict) -> str:
    """No contas.json o nicho é a CHAVE; só o `_default` traz o campo dentro."""
    return (conta.get("nicho") or "geral") if chave == "_default" else chave


def _pacotes_por_conta(contas: dict) -> tuple:
    """({nicho: [(idade_dias, slug)]}, órfãos) — lendo o `conta.json` do pacote.

    ⚠️ A PRIMEIRA VERSÃO DISTO CHUTAVA O NICHO PELO NOME DA PASTA, e o chute
    reportou 427 pacotes em 'geral' — número que não queria dizer nada, porque
    o default do chute ERA 'geral'. Todo pacote sem nicho no nome caía ali.

    A verdade mora em `pronto_para_postar/<slug>/conta.json`, que é exatamente
    de onde o daemon lê (`_conta_do_slug`). E ler do mesmo lugar tem uma
    consequência que o chute escondia: pacote com conta.json ilegível é ÓRFÃO
    pro daemon também — `_conta_do_slug` devolve "?" e TODOS eles viram uma
    "conta" só no rodízio de `_um_por_conta_sob_teto`. Um órfão sai por slot,
    não importa quantos sejam. Contar isso à parte é o ponto do diagnóstico."""
    por_nicho, orfaos = {}, []
    if not PRONTO.is_dir():
        return por_nicho, orfaos

    # ⚠️ CONTAR PASTA NÃO É CONTAR ESTEIRA. `_estoque_por_conta()` do daemon
    # conta só o que `_prontos_nao_postados()` devolve, e essa lista TIRA o que
    # já foi postado e o que passou da validade. Um pacote de 27 dias com
    # validade de 7 continua ocupando disco e aparece em qualquer `ls` — e é
    # invisível pra produção, que por isso acha a conta vazia. Reportar só o
    # total de pastas faz o diagnóstico discordar do daemon sem que nenhum dos
    # dois esteja errado.
    postados = set((_json(HIST, {}) or {}).get("postados") or [])
    validade = _modo_postagem()["validade"]

    # handle -> nicho, pra traduzir o que o conta.json grava
    de_handle = {}
    for chave, conta in contas.items():
        if isinstance(conta, dict):
            h = str(conta.get("handle") or "").lower().lstrip("@")
            if h:
                de_handle[h] = _nicho_da_chave(chave, conta)

    agora = datetime.now().timestamp()
    for p in PRONTO.iterdir():
        if not (p.is_dir() and (p / "video.mp4").exists()):
            continue
        idade = (agora - p.stat().st_mtime) / 86400
        # vivo = o daemon ainda enxerga. Mesma regra de _prontos_nao_postados.
        vivo = p.name not in postados and not (0 < validade <= idade)
        d = _json(p / "conta.json", None)
        if not isinstance(d, dict):
            orfaos.append((idade, p.name))
            continue
        nicho = str(d.get("nicho") or "").strip().lower()
        if not nicho:
            h = str(d.get("handle") or "").lower().lstrip("@")
            nicho = de_handle.get(h, "")
        if not nicho:
            orfaos.append((idade, p.name))
            continue
        por_nicho.setdefault(nicho, []).append((idade, p.name, vivo))
    return por_nicho, orfaos


def _modo_postagem() -> dict:
    """Como o daemon escolhe o que postar. É o que decide se dá pra passar fome.

    ⚠️ `post_por_conta` é OPT-IN. Desligado, o `ciclo_postagem` posta UM pacote
    por slot — `_prontos_nao_postados()[0]` — e conta nenhuma tem vaga
    reservada. Com a esteira funda, a conta de estoque pequeno simplesmente
    nunca chega na frente da fila. Não é erro de config nem token vencido: é a
    fila comendo o slot."""
    cfg = _json(CONFIG, {}) or {}
    return {
        "por_conta": bool(cfg.get("post_por_conta")),
        "teto": cfg.get("posts_por_dia_semana")
                or cfg.get("max_posts_por_conta_dia", 3),
        "validade": int(cfg.get("fila_validade_dias", 7) or 0),
        # ⚠️ "7" pode ser o valor escolhido OU o default de quem nunca escreveu
        # a chave, e a diferença importa: o comentário do _prontos_nao_postados
        # raciocina com validade 27. Imprimir só o número deixa quem lê achando
        # que alguém decidiu 7. É o mesmo erro do 'geral': valor igual ao
        # default não é leitura, é silêncio disfarçado de resposta.
        "validade_explicita": "fila_validade_dias" in cfg,
        "alvo_dias": int(cfg.get("estoque_alvo_dias", 3) or 0),
        "piso": int(cfg.get("producao_minima_por_conta", 0) or 0),
        "achou": CONFIG.exists(),
    }


def _fila_por_nicho() -> tuple:
    """(contagem por nicho, indefinidos, fonte) — com a regra da produção.

    ⚠️ Reusa as funções internas do `roteador_contas`, não reimplementa a
    classificação. Duas regras de "que nicho é este produto" divergiriam com o
    tempo, e o diagnóstico passaria a descrever um sistema que não existe.

    ⚠️ MAS NÃO CHAMA A IA. `nicho_do_produto()` cai no Gemini quando nenhuma
    palavra-chave bate — rodar um diagnóstico não pode custar uma rajada de
    chamadas pagas sobre a fila inteira. Aqui uso a palavra-chave (grátis e
    idêntica à da produção) e, para o resto, só LEIO o cache que a produção já
    gravou. O que sobra vira a coluna `?`: é honesto dizer "a IA decidiria" em
    vez de chutar 'geral' e inflar o número de uma conta que não é a dona."""
    # ⚠️ A PRODUÇÃO NÃO LÊ ESTE ARQUIVO PRIMEIRO. `_carregar_produtos_para_produzir`
    # tenta o `validacao_fila.json` (só classe mina_ouro/ok) e só CAI no
    # produtos_fila.json se aquele não render nada. Contar o produtos_fila e
    # dizer "há 6 produtos de pet na fila" descreve uma fila que a produção
    # talvez nem consulte — e leva a procurar o defeito no lugar errado.
    itens, fonte = [], "produtos_fila.json (fallback)"
    val = _json(VALIDACAO, {}) or {}
    bons = [p for p in (val.get("produtos") or [])
            if isinstance(p, dict) and p.get("classe") in ("mina_ouro", "ok")
            and p.get("produto")]
    if bons:
        itens, fonte = bons, "validacao_fila.json (é o que a produção usa)"
    else:
        for arq in FILAS:
            itens = _json(arq, []) or []
            if isinstance(itens, dict):
                itens = itens.get("produtos") or itens.get("itens") or []
            if itens:
                break

    cont, indefinidos = {}, 0
    try:
        import roteador_contas as RC
    except Exception as e:
        print(f"   (não classifiquei a fila: {str(e)[:60]})")
        return cont, len(itens), fonte

    cache = RC._ler_cache()
    for p in itens:
        p = p or {}
        # ⚠️ CLASSIFICO PELO CAMPO `produto`, e é de propósito: os DOIS caminhos
        # de `_carregar_produtos_para_produzir` montam {"nome": item["produto"]}.
        # `campeao` (o nome real) é mais rico e classificaria melhor — mas quem
        # decide o que produzir não olha pra ele. O diagnóstico tem que enxergar
        # o que a produção enxerga; se eu usar o nome melhor, digo que há
        # produto de pet na fila enquanto a produção nunca o vê como pet.
        # A diferença entre os dois é medida à parte, em _rota_da_producao().
        nome = str(p.get("produto") or p.get("nome") or p.get("titulo") or "")
        # `classe` NÃO entra aqui: é "mina_ouro"/"pilar", curadoria e não
        # assunto. Jogar isso no texto só adiciona ruído ao casamento.
        cat = str(p.get("categoria") or "")
        texto = RC._sem_acento(f"{cat} {nome}".lower())
        n = RC._por_palavra_chave(texto) or cache.get(RC._chave_cache(texto), "")
        if n:
            cont[n] = cont.get(n, 0) + 1
        else:
            indefinidos += 1
    return cont, indefinidos, fonte


def _ultimos_posts(contas: dict) -> dict:
    """{nicho: data do post mais recente} — uma passada só nos ledgers.

    ⚠️ Casa por HANDLE antes de casar por nicho. O ledger grava a conta como
    `@topshoppet_`, e procurar a substring 'geral' dentro de '@topshop.__' não
    acha nada — a conta principal apareceria eternamente como '?'. O handle é
    o identificador que o ledger realmente tem."""
    handles = {}
    for chave, conta in contas.items():
        if isinstance(conta, dict):
            h = str(conta.get("handle") or "").lower().lstrip("@")
            if h:
                handles[h] = _nicho_da_chave(chave, conta)

    ultimo = {}
    for arq in (LEDGER, METRICAS):
        if not arq.exists():
            continue
        try:
            linhas = arq.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for linha in linhas:
            try:
                d = json.loads(linha)
            except Exception:
                continue
            alvo = f"{d.get('conta','')} {d.get('handle','')}".lower()
            nicho = ""
            for h, n in handles.items():
                if h in alvo:
                    nicho = n
                    break
            nicho = nicho or str(d.get("nicho") or "")
            if not nicho:
                continue
            data = str(d.get("data") or d.get("ts") or d.get("quando") or "")[:10]
            if data and data > ultimo.get(nicho, ""):
                ultimo[nicho] = data
    return ultimo


def _rota_da_producao() -> tuple:
    """(o que a PRODUÇÃO acha, o que o nome REAL diria, divergências).

    ⚠️ A produção e o empacotamento leem campos DIFERENTES do mesmo item, e
    ninguém tinha olhado pra isso:

      daemon_maestro._carregar_produtos_para_produzir → {"nome": p["produto"]}
      resto do sistema (piloto, storyboard, revisao)   → campeao or produto

    `produto` é o termo de busca genérico ("Comedouro"); `campeao` é o nome
    real do achado ("Comedouro Automático Pet Gato Bebedouro"). O genérico
    perde as palavras que decidem o nicho — e quem escolhe O QUE PRODUZIR é
    justamente quem lê o genérico.

    Se isto divergir, o efeito é exato e silencioso: `falta[pet]` fica > 0 pra
    sempre, nenhum candidato é atribuído a pet, e o log escreve "ainda faltam
    pacotes (pet:N) mas não há produto desses nichos na fila" — uma frase
    FALSA, porque os produtos estão lá, só entraram pela porta errada."""
    dados = _json(VALIDACAO, {}) or {}
    itens = dados.get("produtos") or []
    if not itens:
        return {}, {}, []
    try:
        import roteador_contas as RC
    except Exception:
        return {}, {}, []

    cache = RC._ler_cache()

    def rotular(txt):
        t = RC._sem_acento(str(txt or "").lower())
        return RC._por_palavra_chave(t) or cache.get(RC._chave_cache(t), "") \
            or "geral?"

    prod, real, divs = {}, {}, []
    for p in itens:
        if not isinstance(p, dict) or p.get("classe") not in ("mina_ouro", "ok"):
            continue                       # só estes viram candidato à produção
        generico = p.get("produto") or ""
        campeao = p.get("campeao") or generico
        a, b = rotular(generico), rotular(campeao)
        prod[a] = prod.get(a, 0) + 1
        real[b] = real.get(b, 0) + 1
        if a != b:
            divs.append((a, b, str(campeao)[:52]))
    return prod, real, divs


def _dias_desde(data: str) -> int:
    """Dias entre `data` (YYYY-MM-DD) e hoje. Sem data = 9999, que é 'nunca'."""
    try:
        a, m, d = (int(x) for x in data[:10].split("-"))
        return (date.today() - date(a, m, d)).days
    except Exception:
        return 9999


def olhar(so_esta: str = "") -> int:
    contas = _contas()
    if not contas:
        print("❌ contas.json ausente ou ilegível — nada a diagnosticar.")
        return 2

    pacotes, orfaos = _pacotes_por_conta(contas)
    fila, indefinidos, fonte_fila = _fila_por_nicho()
    ultimo = _ultimos_posts(contas)
    modo = _modo_postagem()
    hoje = str(date.today())

    print(f"\n🔍 {len(contas)} conta(s) no contas.json  ·  {hoje}")
    if not modo["achou"]:
        print("   ⚠️  agendador_config.json não encontrado — modo de postagem "
              "desconhecido (rode na VPS).")
    else:
        val = f"{modo['validade']}d" + ("" if modo["validade_explicita"]
                                        else " (DEFAULT, chave ausente)")
        print(f"   postagem: {'1 POR CONTA por slot (balanceado)' if modo['por_conta'] else '❌ 1 POR SLOT no total (clássico) — sem vaga reservada por conta'}"
              f"  ·  teto {modo['teto']}")
        print(f"   esteira:  validade {val}  ·  colchão {modo['alvo_dias']}d"
              f"  ·  piso {modo['piso']}/dia")
        print(f"   fila:     {fonte_fila}")
    print()
    print(f"   {'nicho':<8} {'handle':<20} {'ativa':<7} {'fila':>5} "
          f"{'pastas':>7} {'vivos':>6} {'+velho':>7}  último post")
    print("   " + "─" * 80)

    problemas, achei = [], 0
    for chave, conta in contas.items():
        if not isinstance(conta, dict):
            continue
        nicho = _nicho_da_chave(chave, conta)
        if so_esta and nicho != so_esta:
            continue
        achei += 1
        # ⚠️ ausência do campo = ATIVA. É o default do daemon, e o diagnóstico
        # tem que espelhar o código, não inventar um default mais seguro.
        ativa = conta.get("ativa") is not False
        prontos = pacotes.get(nicho, [])
        nf = fila.get(nicho, 0)
        visto = ultimo.get(nicho, "")
        # ⚠️ os indefinidos são POTENCIALMENTE geral: quando nem a palavra-chave
        # nem a IA decidem, `nicho_do_produto_detalhado` devolve 'geral'. Contar
        # o geral como 0 e gritar "sem produto na fila" seria acusar de fome
        # justamente a conta que come as sobras.
        talvez = indefinidos if nicho == "geral" else 0
        col = f"{nf}+{talvez}?" if talvez else str(nf)
        velho = f"{max(i for i, _n, _v in prontos):.0f}d" if prontos else "-"
        vivos = sum(1 for _i, _n, v in prontos if v)
        print(f"   {nicho:<8} {conta.get('handle',''):<20} "
              f"{'sim' if ativa else '❌ NÃO':<7} {col:>5} {len(prontos):>7}"
              f" {vivos:>6} {velho:>7}  {visto or 'NUNCA'}")

        # ⚠️ pasta cheia + vivos zerado é o caso que engana mais: o `ls` mostra
        # estoque, o daemon lê esteira vazia, e a produção acha que a conta
        # precisa de tudo. Quem olha o disco e quem olha o log discordam.
        if prontos and not vivos:
            problemas.append(
                f"{nicho}: {len(prontos)} pacote(s) no disco e ZERO visíveis pro "
                f"daemon — todos já postados ou passados da validade "
                f"({modo['validade']}d). Pra `_estoque_por_conta()` esta conta "
                f"está vazia; o `ls` diz o contrário. É disco ocupado, não "
                f"estoque.")

        if not ativa:
            problemas.append(
                f"{nicho}: `\"ativa\": false` no contas.json — a PRODUÇÃO nunca "
                f"vai gerar pra ela (é o único lugar que lê esse campo: "
                f"daemon_maestro._nichos_das_contas). Sem pacote produzido não "
                f"há o que postar, e o vigia reporta a conta como parada porque "
                f"ele lê o arquivo inteiro e não filtra por `ativa`. As duas "
                f"estão certas. Ligar é trocar para `true`.")
        elif nf + talvez == 0 and not prontos:
            problemas.append(
                f"{nicho}: ativa, mas SEM produto na fila e SEM pacote pronto. "
                f"Ou o roteador não tem palavra-chave que mande produto pra cá, "
                f"ou o coletor não trouxe nada do assunto.")
        elif vivos and _dias_desde(visto) >= 2:
            # ⚠️ o corte é 2 dias, não "não postou hoje". A pirâmide tem dia de
            # volume baixo e domingo é 0 — alarmar por um dia sem post faria o
            # diagnóstico gritar toda segunda-feira de manhã, e alarme que toca
            # sozinho é alarme que ninguém lê.
            d = _dias_desde(visto)
            quanto = f"{d} dias sem post" if visto else "e NUNCA postou"
            if not modo["por_conta"]:
                problemas.append(
                    f"{nicho}: {vivos} pacote(s) PRONTO(S) e vivo(s), o mais velho "
                    f"com {velho}, {quanto}. Com `post_por_conta` "
                    f"DESLIGADO o daemon posta 1 pacote por slot no total — não "
                    f"há vaga reservada por conta, e quem tem estoque pequeno "
                    f"nunca chega na frente da fila. Isto é FOME, não token "
                    f"vencido: o pacote está pronto e a vez não vem.")
            else:
                problemas.append(
                    f"{nicho}: {vivos} pacote(s) PRONTO(S) e vivo(s), o mais velho "
                    f"com {velho}, {quanto} — com o rodízio por conta "
                    f"LIGADO. Aí o gargalo é a publicação em si: veja o token "
                    f"dessa conta e o `fila_problema/` (pacote que a Meta recusa "
                    f"queima a vaga da conta naquele slot).")

    # ⚠️ tabela vazia + "nenhuma conta parada" seria a pior resposta possível:
    # a conta perguntada nem existe no arquivo, e é exatamente por isso que ela
    # não posta. Silêncio aqui vira "está tudo bem" na cabeça de quem lê.
    if so_esta and not achei:
        print(f"   (nenhuma conta com o nicho '{so_esta}')\n")
        print(f"⚠️  '{so_esta}' NÃO ESTÁ no contas.json desta máquina. Ou o "
              f"nicho tem outro nome, ou o arquivo aqui está atrasado em "
              f"relação ao da VPS — rode este diagnóstico NA VPS.\n")
        return 1

    # ⚠️ O TOTAL É A MANCHETE E ESTAVA ESCONDIDO NAS LINHAS. Pasta que venceu
    # não é estoque: é disco. Somar as duas colunas mostra de uma vez o
    # tamanho do desperdício, que por conta parecia sempre "uns poucos".
    tp = sum(len(v) for v in pacotes.values()) + len(orfaos)
    tv = sum(1 for v in pacotes.values() for _i, _n, viv in v if viv)
    if tp and not so_esta:
        print(f"\n   Σ {tp} pacote(s) no disco · {tv} vivo(s) · "
              f"{tp - tv} morto(s) ({(tp - tv) * 100 // max(tp, 1)}%)")
        if tp - tv > tv:
            problemas.append(
                f"esteira: {tp - tv} de {tp} pacotes estão MORTOS (postados ou "
                f"vencidos) e continuam ocupando disco. A validade em vigor é "
                f"{modo['validade']}d"
                + ("" if modo["validade_explicita"] else
                   " — e é o DEFAULT, ninguém escreveu `fila_validade_dias`. O "
                   "comentário do próprio `_prontos_nao_postados` raciocina com "
                   "27. Se 7 não foi uma escolha, a esteira está vencendo cerca "
                   "de quatro vezes mais rápido do que o projeto supunha")
                + f". Com a esteira nesse tamanho e o ritmo real de postagem, o "
                f"pacote vence antes de chegar a vez dele — produzir mais não "
                f"resolve, só aumenta a pilha que vai vencer.")

    prod, real, divs = _rota_da_producao()
    if divs:
        print(f"\n   ⚠️  ROTEAMENTO: {len(divs)} produto(s) que a PRODUÇÃO manda "
              f"pra um nicho e o nome real manda pra outro")
        for a, b, nome in divs[:6]:
            print(f"      {a:>8} → {b:<8} {nome}")
        print(f"      produção vê: "
              + ", ".join(f"{k}={v}" for k, v in sorted(prod.items())))
        print(f"      nome real:   "
              + ", ".join(f"{k}={v}" for k, v in sorted(real.items())))
        problemas.append(
            f"roteamento: {len(divs)} produto(s) são COBRADOS de uma conta e "
            f"ENTREGUES em outra. Quem escolhe o que produzir lê o campo "
            f"`produto`, o termo de busca genérico "
            f"(`_carregar_produtos_para_produzir` monta {{'nome': p['produto']}}); "
            f"quem monta o pacote lê `campeao`, o nome real. Então "
            f"`_priorizar_por_estoque` desconta o déficit da conta A — 'já "
            f"produzi pra ela' — e o `conta.json` do pacote sai com a conta B. "
            f"A conta A nunca enche, a conta B recebe pacote que não pediu, e "
            f"as duas parecem estar funcionando. É o candidato número 1 pra "
            f"explicar por que o `geral` acumula pacote sem ter produto na "
            f"fila: ele é o destino de quem perdeu o nicho no caminho.")

    if orfaos and not so_esta:
        velho = max(i for i, _ in orfaos)
        print(f"\n   ⚠️  {len(orfaos)} pacote(s) SEM conta.json legível "
              f"(mais velho: {velho:.0f}d)")
        for i, nome in sorted(orfaos, reverse=True)[:3]:
            print(f"      {i:>5.0f}d  {nome[:56]}")
        problemas.append(
            f"órfãos: {len(orfaos)} pacote(s) prontos sem `conta.json` legível"
            + (". Pro daemon TODOS eles são a MESMA conta — `_conta_do_slug` "
               "devolve '?' e o rodízio de `_um_por_conta_sob_teto` tira UM por "
               "slot, não importa quantos sejam."
               if modo["por_conta"] else
               ". No modo clássico eles entram na fila única como qualquer "
               "outro, e como são os mais VELHOS a drenagem por idade os põe "
               "na frente — eles comem o slot das contas de estoque pequeno.")
            + " E o pacote sem conta.json não tem destino: envelhece na esteira "
              "até o expurgo por validade levar embora.")

    if indefinidos:
        print(f"\n   ({indefinidos} produto(s) da fila sem palavra-chave nem "
              f"cache — a IA do roteador decidiria o nicho na produção; este "
              f"diagnóstico não chama a IA pra não gastar.)")

    if problemas:
        print("\n⚠️  O que está travando:\n")
        for p in problemas:
            print(f"   • {p}\n")
    else:
        print("\n✅ nenhuma conta parada por configuração.\n")
    return 0


if __name__ == "__main__":
    sys.exit(olhar(sys.argv[1] if len(sys.argv) > 1 else ""))
