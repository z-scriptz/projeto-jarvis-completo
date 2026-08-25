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
# ⚠️ E O CASO MAIS TRAIÇOEIRO É O `"ativa": false`, porque ele é INVISÍVEL em
# toda ferramenta que não seja esta. O vigia lê o contas.json inteiro e reporta
# a conta; a produção filtra por `ativa` e pula. As duas estão certas — só que
# uma diz "a conta existe e está parada" e a outra nunca soube que devia
# produzir. Quem lê os dois relatórios conclui que há um bug, e não há: há uma
# decisão antiga que ninguém desfez.
#
# USO (na VPS):
#   .venv/bin/python diag_contas.py
#   .venv/bin/python diag_contas.py pet     # só uma conta, com detalhe

import json
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRONTO = BASE / "pronto_para_postar"
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


def _pacotes_por_nicho() -> dict:
    """Pastas prontas em `pronto_para_postar/`, por nicho do slug."""
    cont = {}
    if not PRONTO.is_dir():
        return cont
    for p in PRONTO.iterdir():
        if not (p.is_dir() and (p / "video.mp4").exists()):
            continue
        # o nicho vem no nome da pasta; sem ele o pacote cai em geral
        nicho = "geral"
        for parte in p.name.lower().replace("-", "_").split("_"):
            if parte in ("beleza", "tech", "casa", "pet", "moda", "geral"):
                nicho = parte
                break
        cont.setdefault(nicho, []).append(p)
    return cont


def _fila_por_nicho() -> tuple:
    """(contagem por nicho, quantos ficaram indefinidos) — com a regra da produção.

    ⚠️ Reusa as funções internas do `roteador_contas`, não reimplementa a
    classificação. Duas regras de "que nicho é este produto" divergiriam com o
    tempo, e o diagnóstico passaria a descrever um sistema que não existe.

    ⚠️ MAS NÃO CHAMA A IA. `nicho_do_produto()` cai no Gemini quando nenhuma
    palavra-chave bate — rodar um diagnóstico não pode custar uma rajada de
    chamadas pagas sobre a fila inteira. Aqui uso a palavra-chave (grátis e
    idêntica à da produção) e, para o resto, só LEIO o cache que a produção já
    gravou. O que sobra vira a coluna `?`: é honesto dizer "a IA decidiria" em
    vez de chutar 'geral' e inflar o número de uma conta que não é a dona."""
    itens = []
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
        return cont, len(itens)

    cache = RC._ler_cache()
    for p in itens:
        p = p or {}
        # ⚠️ o item da fila NÃO tem "nome". Tem `produto` (termo de busca
        # genérico) e `campeao` (nome real do produto), e o resto do sistema lê
        # sempre `campeao or produto` — piloto.py, storyboard.py, revisao_geral.
        # Com "nome" eu classificava 24 de 24 como indefinido e o diagnóstico
        # acusaria "fila vazia" em toda conta. Erro de campo é erro silencioso:
        # não estoura, só zera.
        camp = p.get("campeao")
        if isinstance(camp, dict):
            camp = camp.get("nome") or camp.get("titulo") or ""
        nome = str(camp or p.get("produto") or p.get("nome")
                   or p.get("titulo") or "")
        # `classe` NÃO entra aqui: é "mina_ouro"/"pilar", curadoria e não
        # assunto. Jogar isso no texto só adiciona ruído ao casamento.
        cat = str(p.get("categoria") or "")
        texto = RC._sem_acento(f"{cat} {nome}".lower())
        n = RC._por_palavra_chave(texto) or cache.get(RC._chave_cache(texto), "")
        if n:
            cont[n] = cont.get(n, 0) + 1
        else:
            indefinidos += 1
    return cont, indefinidos


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


def olhar(so_esta: str = "") -> int:
    contas = _contas()
    if not contas:
        print("❌ contas.json ausente ou ilegível — nada a diagnosticar.")
        return 2

    pacotes = _pacotes_por_nicho()
    fila, indefinidos = _fila_por_nicho()
    ultimo = _ultimos_posts(contas)
    hoje = str(date.today())

    print(f"\n🔍 {len(contas)} conta(s) no contas.json  ·  {hoje}\n")
    print(f"   {'nicho':<8} {'handle':<20} {'ativa':<7} {'fila':>5} "
          f"{'prontos':>8}  último post")
    print("   " + "─" * 66)

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
        print(f"   {nicho:<8} {conta.get('handle',''):<20} "
              f"{'sim' if ativa else '❌ NÃO':<7} {col:>5} {len(prontos):>8}"
              f"  {visto or 'NUNCA'}")

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
        elif prontos and visto != hoje:
            problemas.append(
                f"{nicho}: {len(prontos)} pacote(s) PRONTO(S) e sem post hoje — "
                f"o gargalo é a POSTAGEM, não a produção. Olhe token e limite "
                f"diário dessa conta.")

    # ⚠️ tabela vazia + "nenhuma conta parada" seria a pior resposta possível:
    # a conta perguntada nem existe no arquivo, e é exatamente por isso que ela
    # não posta. Silêncio aqui vira "está tudo bem" na cabeça de quem lê.
    if so_esta and not achei:
        print(f"   (nenhuma conta com o nicho '{so_esta}')\n")
        print(f"⚠️  '{so_esta}' NÃO ESTÁ no contas.json desta máquina. Ou o "
              f"nicho tem outro nome, ou o arquivo aqui está atrasado em "
              f"relação ao da VPS — rode este diagnóstico NA VPS.\n")
        return 1

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
