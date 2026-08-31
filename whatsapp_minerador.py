#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# whatsapp_minerador.py — lê grupo de achadinho dos outros e vira fila nossa.
#
# O QUE FAZ
# Abre os grupos-FONTE (os do concorrente, em WHATSAPP_FONTES), lê as mensagens
# novas, tira o nome do produto, procura esse produto na API de afiliado da
# Shopee e grava na `produtos_fila.json` com o NOSSO link. Nada do link dele
# entra em lugar nenhum — `_limpar_links_terceiros` apaga antes da extração.
#
# ⚠️ ISTO NUNCA ESCREVE NUM GRUPO. Nem nos deles, nem nos nossos. Não existe
# chamada de envio neste arquivo, e isso é proposital: quem posta é o
# `whatsapp_playwright`. Uma mensagem saindo de dentro do grupo do concorrente
# não tem desfazer, e a única garantia que vale é a estrutural.
#
# POR QUE ELE EXISTE (30/08)
# A esteira repunha ~11 achadinhos bons por dia e a meta virou 72. Medido no
# `hunter_seen.sqlite`, 60% das mensagens que o hunter do Telegram processa
# viram produto aproveitável (454 ok / 755). Três grupos cheios postando ~72
# por dia dão ~216 mensagens/dia → ~130 achadinhos. O gargalo nunca foi
# "quantos produtos existem", era quantas fontes a gente escutava.
#
# ⚠️ E A FONTE É FLUXO, NÃO ESTOQUE. Os grupos de achadinho ligam mensagem
# temporária (24h ou 7 dias) — o próprio TopShop VIP #3 está em 7 dias. Não
# existe "varrer uma vez e ter fonte pro ano": o que não for lido dentro da
# janela morre, e ao entrar num grupo não se herda histórico. Por isso este
# script roda várias vezes ao dia, e por isso perder um dia custa um dia.
#
# ⚠️ SESSÃO ÚNICA, DOIS PROGRAMAS (a restrição que molda o resto do arquivo).
# `_abrir` usa `launch_persistent_context(user_data_dir=SESSAO)` e o Dre
# decidiu usar O MESMO NÚMERO pra postar e pra ler. Dois Chromium no mesmo
# perfil não convivem: o segundo falha no lock do Chrome ou — pior — corrompe
# o perfil, e aí a sessão cai de verdade e o WhatsApp pede QR novo. Escanear
# QR à toa é justamente o padrão que faz o WhatsApp desconfiar da conta.
# Daí a trava do `whatsapp_playwright` (`travar`/`destravar`, uma só pros
# dois): quem chega primeiro roda, o outro desiste e tenta no próximo slot.
# Nenhum dos dois é urgente ao minuto.
#
# ⚠️ RITMO DE GENTE, NÃO DE ROBÔ. Uma conta que abre os mesmos 3 grupos, na
# mesma ordem, aos :00 de toda hora, é distinguível de um humano por qualquer
# heurística boba. Então: horário sorteado (não de hora em hora cravada),
# ordem dos grupos embaralhada, nem todo grupo em toda rodada, pausa variável
# entre grupos e uma rolagem antes de ler — que é o que um dedo faz.
#
# USO (na VPS, dentro de ~/jarvis):
#   .venv/bin/python whatsapp_minerador.py --teste     # lê e mostra, não grava
#   .venv/bin/python whatsapp_minerador.py             # lê e grava na fila
#   .venv/bin/python whatsapp_minerador.py --diag      # o que ele enxerga no DOM
#   .venv/bin/python whatsapp_minerador.py --fontes    # confere a config
#
# .env:
#   WHATSAPP_FONTES=Grupo do Fulano;Achadinhos da Ciclana   (separador é `;`)
#   WHATSAPP_MINA_MAX=40        teto de produtos consultados por rodada
#   WHATSAPP_MINA_GRUPOS=2      quantos grupos-fonte por rodada (0 = todos)

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ⚠️ TETO POR RODADA PORQUE CADA PRODUTO É UMA CHAMADA DE API. Sem ele, entrar
# num grupo movimentado numa segunda de manhã queima a cota do dia numa rodada
# e as outras voltam de mãos vazias sem explicar por quê.
MINA_MAX = int(float(os.environ.get("WHATSAPP_MINA_MAX", "40")))

# Quantos grupos-fonte visitar por rodada. Menos que o total, de propósito:
# ver os 3 sempre, toda vez, é padrão. Com 2 de 3 e ordem sorteada, o conjunto
# das visitas ao longo do dia cobre tudo sem nenhuma rodada ser previsível.
MINA_GRUPOS = int(float(os.environ.get("WHATSAPP_MINA_GRUPOS", "2")))

# Quantas mensagens recentes olhar em cada grupo. O `hunter_seen` corta o que
# já foi visto, então repetir é barato — e a janela precisa ser maior que o
# volume entre duas rodadas, senão mensagem some antes de ser lida.
JANELA_MSGS = int(float(os.environ.get("WHATSAPP_MINA_JANELA", "60")))


def _log(m):
    print(f"[mina] {m}", flush=True)


# ── o que vem de outros módulos ──────────────────────────────────────────
# ⚠️ DOIS CAMINHOS DE IMPORT, SEMPRE. No repositório os arquivos são planos; na
# VPS o hunter mora em `agents/`. Um import só funciona num dos dois lugares, e
# o sintoma do errado é "módulo não encontrado" no meio da madrugada.
def _importar(nomes: list, atributos: list):
    for nome in nomes:
        try:
            import importlib
            mod = importlib.import_module(nome)
            return [getattr(mod, a) for a in atributos]
        except Exception as e:
            ultimo = e
            continue
    raise ImportError(f"não achei {nomes}: {ultimo}")


def _pecas():
    """As funções emprestadas, ou um erro que diz qual faltou.

    ⚠️ NADA DE `except: pass` AQUI. Foi assim que o `_classe_de` engoliu uma
    falha de import e gravou 41 produtos com número certo e classe vazia — e o
    estrago só apareceu semanas depois, no ranking do grupo. Se uma peça falta,
    este script não roda: ele existe pra gravar produto, e produto gravado pela
    metade é pior que rodada perdida."""
    wa = _importar(["whatsapp_playwright", "agents.whatsapp_playwright"],
                   ["_abrir", "_abrir_grupo", "_esperar_sessao", "_fechar_modal",
                    "_print_erro", "_avisar", "_STEALTH_JS",
                    "travar", "destravar"])
    hunter = _importar(
        ["telegram_repurpose_hunter", "agents.telegram_repurpose_hunter"],
        ["extrair_termo_produto", "_limpar_links_terceiros", "_registrar_no_site",
         "tratar_preco", "_deve_pular", "_marcar_processado", "_registrar_falha"])
    shopee = _importar(["shopee_affiliate", "integrations.shopee_affiliate"],
                       ["minerar_oportunidades", "gerar_link_afiliado"])
    return wa, hunter, shopee


def _fontes() -> list:
    """Os grupos do concorrente. Separador `;`, mesma regra do WHATSAPP_GRUPOS
    (nome de grupo de achadinho leva vírgula com frequência).

    ⚠️ NUNCA CAI PRO WHATSAPP_GRUPOS. Se esta variável estiver vazia, o certo é
    não minerar nada — herdar os grupos de POSTAGEM faria o minerador ler o que
    nós mesmos publicamos e reciclar o próprio conteúdo, inflando a fila com
    produtos que já foram ao ar. Um default 'esperto' aqui seria um loop."""
    bruto = (os.environ.get("WHATSAPP_FONTES", "") or "").strip()
    nomes = [g.strip() for g in bruto.split(";") if g.strip()]
    vistos, saida = set(), []
    for n in nomes:
        if n.lower() not in vistos:
            vistos.add(n.lower())
            saida.append(n)
    return saida


def _proprios() -> set:
    """Os NOSSOS grupos, em minúsculo — pra recusar se alguém colar um deles
    em WHATSAPP_FONTES por engano. Cinto além da suspensória do `_fontes`."""
    bruto = (os.environ.get("WHATSAPP_GRUPOS", "")
             or os.environ.get("WHATSAPP_GRUPO", "") or "")
    return {g.strip().lower() for g in bruto.split(";") if g.strip()}


# ── leitura do DOM ───────────────────────────────────────────────────────
# As mensagens ficam em `div[data-id]`; `message-in` é o que chegou (o que nós
# mandaríamos é `message-out`, e num grupo-fonte não existe). O `data-id` é
# estável — vira a chave do `hunter_seen`, que é o que impede reprocessar a
# mesma mensagem e gastar chamada de API duas vezes.
_JS_MENSAGENS = """
(limite) => {
  const main = document.querySelector('#main');
  if (!main) return {erro: 'sem #main'};
  const linhas = main.querySelectorAll('div[data-id]');
  const saida = [];
  for (const el of linhas) {
    const id = el.getAttribute('data-id') || '';
    if (!id) continue;
    const entrada = el.querySelector('.message-in') ||
                    (el.className || '').includes('message-in');
    if (!entrada) continue;
    const t = (el.innerText || '').trim();
    if (t) saida.push({id: id, texto: t.slice(0, 1200)});
  }
  return {itens: saida.slice(-limite)};
}
"""


def _ler_grupo(pagina, grupo: str, limite: int) -> list:
    """[{id, texto}] das mensagens recebidas visíveis.

    Rola um pouco antes de ler: é o que carrega mensagem mais antiga no
    WhatsApp Web e, de quebra, é o que uma pessoa faz ao abrir o grupo."""
    for _ in range(random.randint(2, 4)):
        try:
            pagina.mouse.wheel(0, -random.randint(600, 1400))
        except Exception:
            break
        pagina.wait_for_timeout(random.randint(400, 900))
    try:
        r = pagina.evaluate(_JS_MENSAGENS, limite) or {}
    except Exception as e:
        _log(f"   ⚠️ não li o DOM de {grupo}: {type(e).__name__} {str(e)[:80]}")
        return []
    if r.get("erro"):
        _log(f"   ⚠️ {grupo}: {r['erro']}")
        return []
    return [i for i in (r.get("itens") or []) if i.get("id") and i.get("texto")]


# ── o miolo ──────────────────────────────────────────────────────────────
def _aproveitar(texto: str, hunter, shopee, teste: bool) -> tuple:
    """(status, detalhe). status ∈ {'ok','sem_termo','sem_shopee','sem_link'}.

    Mesmo caminho do hunter do Telegram, e de propósito: é código já rodado
    454 vezes com sucesso. O que muda aqui é só de onde vem o texto."""
    (extrair, limpar, registrar, tratar_preco, _, _, _) = hunter
    minerar, gerar_link = shopee

    termo = extrair(limpar(texto))
    if not termo:
        return "sem_termo", ""
    m = minerar(termo)
    if not m.get("ok") or not m.get("campeao"):
        return "sem_shopee", termo
    c = m["campeao"]
    url = c.get("product_link") or c.get("offer_link") or ""
    if not url:
        return "sem_shopee", termo
    if teste:
        return "ok", f"{c.get('nome', termo)[:52]}  (R$ {c.get('preco', 0)})"

    try:
        r = gerar_link(url, sub_ids=["wa_mina", "whatsapp_minerador"])
        link = (r.get("link") or r.get("short_link") or "") \
            if isinstance(r, dict) else str(r or "")
    except Exception as e:
        _log(f"   ⚠️ link de afiliado falhou: {str(e)[:70]}")
        link = ""
    link = link or m.get("link_gerado") or ""
    if not link:
        return "sem_link", termo

    registrar(c.get("nome", termo), link, c.get("imagem", ""),
              plataforma="shopee", origem=url,
              preco=tratar_preco(c.get("preco", 0)))
    return "ok", c.get("nome", termo)[:52]


def rodar(teste: bool, diag: bool) -> int:
    fontes = _fontes()
    if not fontes:
        _log("❌ WHATSAPP_FONTES vazio no .env — nenhum grupo pra minerar.")
        _log("   python3 env_set.py WHATSAPP_FONTES 'Grupo A;Grupo B'")
        return 2
    nossos = _proprios()
    conflito = [g for g in fontes if g.lower() in nossos]
    if conflito:
        # ⚠️ minerar o próprio grupo recicla o que já publicamos: a fila
        # encheria de produto que já foi ao ar, com cara de produto novo.
        _log(f"❌ {len(conflito)} grupo(s) em WHATSAPP_FONTES são NOSSOS: "
             f"{', '.join(conflito)}. Fonte é grupo de terceiro.")
        return 2

    wa, hunter, shopee = _pecas()
    (_abrir, _abrir_grupo, _esperar_sessao, _fechar_modal,
     _print_erro, _avisar, _STEALTH_JS, travar, destravar) = wa
    (_, _, _, _, deve_pular, marcar, marcar_falha) = hunter

    # ⚠️ A TRAVA VEM DO POSTADOR, não é cópia. Duas implementações do mesmo
    # cadeado divergem no primeiro conserto e param de se enxergar — e o
    # sintoma seria dois Chromium no mesmo perfil, que é exatamente o que ela
    # existe pra impedir. O minerador é o lado que CEDE: espera pouco, porque
    # a próxima rodada dele serve igual, e o postador tem hora marcada.
    if not travar("minerador", espera_s=90):
        _log("⏭️  o postador está usando a sessão — saio e tento no próximo "
             "slot (o perfil do Chromium é um só)")
        return 0

    alvos = list(fontes)
    random.shuffle(alvos)                    # ordem nunca é a mesma
    if MINA_GRUPOS > 0:
        alvos = alvos[:MINA_GRUPOS]          # nem todo grupo em toda rodada
    _log(f"{len(alvos)} de {len(fontes)} grupo(s) nesta rodada")

    from playwright.sync_api import sync_playwright
    contas = {"lidas": 0, "novas": 0, "ok": 0,
              "sem_termo": 0, "sem_shopee": 0, "sem_link": 0}
    try:
        with sync_playwright() as pw:
            ctx = _abrir(pw)
            pagina = ctx.pages[0] if ctx.pages else ctx.new_page()
            ctx.add_init_script(_STEALTH_JS)
            try:
                pagina.goto("https://web.whatsapp.com", timeout=60000)
                est = _esperar_sessao(pagina)
                if est != "logado":
                    _print_erro(pagina, f"minerador: sessão em '{est}'")
                    return 1
                pagina.wait_for_timeout(4000)
                _fechar_modal(pagina)

                orcamento = MINA_MAX
                for i, g in enumerate(alvos):
                    if orcamento <= 0:
                        _log(f"teto da rodada ({MINA_MAX}) — paro aqui")
                        break
                    if not _abrir_grupo(pagina, g):
                        # grupo que sumiu não cala os outros — mesma regra do
                        # postador. Aqui é ainda menos grave: fonte a menos.
                        _log(f"   ⏭️  {g}: não abri, sigo")
                        continue
                    msgs = _ler_grupo(pagina, g, JANELA_MSGS)
                    contas["lidas"] += len(msgs)
                    if diag:
                        _log(f"   [diag] {g}: {len(msgs)} mensagem(ns)")
                        for m in msgs[-5:]:
                            _log(f"      {m['id'][:38]}  "
                                 f"{m['texto'].splitlines()[0][:60]!r}")
                        continue

                    canal = f"wa:{g}"
                    for m in msgs:
                        if orcamento <= 0:
                            break
                        if deve_pular(canal, m["id"]):
                            continue
                        contas["novas"] += 1
                        orcamento -= 1
                        try:
                            status, det = _aproveitar(m["texto"], hunter,
                                                      shopee, teste)
                        except Exception as e:
                            _log(f"   ⚠️ {type(e).__name__}: {str(e)[:80]}")
                            marcar_falha(canal, m["id"])
                            continue
                        contas[status] = contas.get(status, 0) + 1
                        if status == "ok":
                            _log(f"   {'🧪' if teste else '✅'} {det}")
                            if not teste:
                                marcar(canal, m["id"])
                        else:
                            # ⚠️ falha é REGISTRADA, não marcada como ok: o
                            # `_deve_pular` só desiste depois de MAX_TENTATIVAS,
                            # então um fora-do-ar da Shopee não queima a
                            # mensagem pra sempre.
                            marcar_falha(canal, m["id"])

                    if i < len(alvos) - 1:
                        espera = random.uniform(20, 75)
                        _log(f"   (pausa de {espera:.0f}s antes do próximo)")
                        time.sleep(espera)
                return 0
            except Exception as e:
                caminho = _print_erro(pagina, f"minerador parou: {str(e)[:90]}")
                _avisar(f"Minerador do WhatsApp parou: {str(e)[:180]}", caminho)
                return 1
            finally:
                _log(f"lidas {contas['lidas']} · novas {contas['novas']} · "
                     f"✅ {contas['ok']} · sem termo {contas['sem_termo']} · "
                     f"sem Shopee {contas['sem_shopee']} · "
                     f"sem link {contas['sem_link']}")
                try:
                    ctx.close()
                except Exception:
                    pass
    finally:
        destravar()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Lê grupos de achadinho de terceiros e alimenta a fila "
                    "com o NOSSO link de afiliado. Nunca envia mensagem.")
    p.add_argument("--teste", action="store_true",
                   help="lê e mostra o que aproveitaria, sem gravar na fila")
    p.add_argument("--diag", action="store_true",
                   help="mostra o que enxerga no DOM (pra conferir seletor)")
    p.add_argument("--fontes", action="store_true",
                   help="só lista os grupos-fonte configurados")
    a = p.parse_args(argv)

    if a.fontes:
        f = _fontes()
        _log(f"{len(f)} fonte(s): " + (", ".join(f) if f else "(nenhuma)"))
        nossos = _proprios()
        for g in f:
            if g.lower() in nossos:
                _log(f"   ⚠️  '{g}' também está em WHATSAPP_GRUPOS (é NOSSO)")
        return 0 if f else 1
    return rodar(a.teste, a.diag)


if __name__ == "__main__":
    sys.exit(main())
