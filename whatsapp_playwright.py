#!/usr/bin/env python3
# whatsapp_playwright.py -- posta achadinho no GRUPO do WhatsApp pelo WhatsApp
# Web, com volume baixo e ritmo de gente.
#
# POR QUE ISSO EXISTE E O QUE ELE CUSTA
# ─────────────────────────────────────
# O WhatsApp NÃO tem API oficial pra postar em grupo. A Cloud API da Meta serve
# pra conversa 1:1 com quem optou por receber; grupo não está na superfície
# dela. Então isto aqui automatiza o WhatsApp WEB por trás — o que contraria os
# termos de uso, e um número banido leva junto o grupo e o contato comercial.
#
# A decisão de correr esse risco foi do dono do número, com a condição de ser
# conservador. Todo o desenho abaixo existe por causa disso: o que derruba
# número é VOLUME e PADRÃO DE ROBÔ, não a automação em si.
#
# AS TRAVAS (mexer nelas é aumentar o risco, não "otimizar")
#   DESLIGADO POR PADRÃO   WHATSAPP_ATIVO=1 no .env pra ligar
#   TETO POR RODADA        2 mensagens (WHATSAPP_MAX_RODADA)
#   TETO POR DIA           6 mensagens (WHATSAPP_MAX_DIA)
#   JANELA DE HORÁRIO      07:00–21:59 — ninguém manda achadinho às 3 da manhã
#   PAUSA ENTRE MENSAGENS  45 a 120s, sorteada
#   DIGITAÇÃO LENTA        o texto é digitado, não colado
#   PARA NA PRIMEIRA DÚVIDA  sessão caída, grupo não achado, seletor que sumiu
#                            → tira print, avisa no Telegram e encerra
#
# O FORMATO DA MENSAGEM (mudou em 19/08)
#   Vai TEXTO + LINK, sem anexo. A foto do produto quem monta é o WhatsApp, no
#   cartão de prévia que ele busca sozinho na URL da Shopee. O caminho antigo
#   (anexar a nossa miniatura) está no código, desligado — ver COM_FOTO.
#
# SESSÃO
#   O login é por QR, uma vez. Como a VPS não tem tela, o --login tira um print
#   do QR e MANDA PRO SEU TELEGRAM PRIVADO — você escaneia do celular. A sessão
#   fica em shared/whatsapp_sessao/ e sobrevive aos reinícios.
#
# ⚠️ O WhatsApp Web troca a marcação sem aviso e sem versão. Por isso cada
# elemento tem VÁRIOS seletores e, quando nenhum casa, o script tira print e
# para em vez de clicar no escuro. Print quebrado em shared/whatsapp_erros/.
#
# Uso (na VPS, sempre com o venv):
#   .venv/bin/python whatsapp_playwright.py --login      # 1ª vez: QR no Telegram
#   .venv/bin/python whatsapp_playwright.py --teste      # acha o grupo, não envia
#   .venv/bin/python whatsapp_playwright.py              # envia (respeita tetos)

import argparse
import json
import os
import random
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if not (BASE_DIR / "shared").exists() and (BASE_DIR.parent / "shared").exists():
    BASE_DIR = BASE_DIR.parent

FILA = BASE_DIR / "shared" / "produtos_fila.json"
CURADORIA = BASE_DIR / "shared" / "content_plans" / "validacao_fila.json"
ESTADO = BASE_DIR / "shared" / "whatsapp_enviados.json"
SESSAO = BASE_DIR / "shared" / "whatsapp_sessao"
ERROS = BASE_DIR / "shared" / "whatsapp_erros"
FOTOS = BASE_DIR / "shared" / "whatsapp_fotos"

# A regra de "esse nome serve pra cliente?" mora em shared/termos.py e é
# importada, nunca copiada: regra duplicada é a armadilha que já mordeu este
# projeto (arquivo na raiz divergindo do arquivo do pacote). Se ela não puder
# ser carregada, _candidatos devolve lista vazia e o script não manda nada —
# mesma política do resto do arquivo: na dúvida, para.
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
try:
    from shared.termos import nome_de_produto_ruim as _nome_ruim
except Exception as _e_imp:          # noqa: N816
    _nome_ruim = None
    _ERRO_REGRA = str(_e_imp)[:120]

# Mesma trava do postar_grupo, pela mesma razão: em 04/08 o crontab tinha a
# linha do postar_grupo repetida 4x e o grupo do Telegram recebeu tudo em
# quádruplo. Aqui o estrago seria pior — 4 navegadores na mesma sessão do
# WhatsApp é exatamente o padrão que derruba número.
try:
    from shared.trava import travar
except Exception:
    from contextlib import contextmanager

    @contextmanager
    def travar(_nome, base=None):
        yield True

# ⚠️ AS CONSTANTES DE AJUSTE NÃO MORAM AQUI — moram DEPOIS do `_carregar_env()`
# (procure por "AS TRAVAS, EM CÓDIGO"). Elas ficavam neste ponto do arquivo e
# eram lidas ANTES do .env ser carregado, então `WHATSAPP_MAX_DIA=3` no .env
# não mudava nada em execução manual: valia sempre o padrão do código. Só
# funcionava pelo systemd, que injeta o ambiente antes do Python subir.
# Corrigido em 19/08. Não traga knob nenhum pra cima desta linha.

_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/126.0.0.0 Safari/537.36")
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR','pt','en-US']});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
window.chrome = { runtime: {} };
"""

# Vários por campo de propósito: o WhatsApp Web troca marcação sem aviso. Se
# TODOS falharem, o script para e tira print — nunca clica adivinhando.
SEL_QR = ["canvas[aria-label*='scan' i]", "div[data-ref] canvas", "canvas"]
SEL_BUSCA = ["div[contenteditable='true'][data-tab='3']",
             "div[role='textbox'][data-tab='3']",
             "div[title='Caixa de texto de pesquisa']",
             # visto no print de 04/08: o campo se anuncia com este texto
             "div[contenteditable='true'][aria-label*='Pesquisar' i]",
             "div[contenteditable='true'][data-lexical-editor='true']"]

# O WhatsApp Web solta um "Novidades do WhatsApp Web" por cima de tudo depois
# de atualizar. Ele NÃO some sozinho e cobre a busca — foi o que derrubou o
# --teste de 04/08: os seletores da busca estavam certos, o elemento é que
# estava atrás do modal, e wait_for_selector(state="visible") falha nisso.
#
# Só clico em botão que esteja DENTRO de um role=dialog e cujo texto seja um
# dos abaixo. Clicar em "qualquer botão do diálogo" é como aceitar um termo
# sem ler: um dia o diálogo é "Sair de todos os aparelhos?".
SEL_MODAL = ["div[role='dialog']", "div[data-animate-modal-body='true']"]
TXT_MODAL_OK = ["Continuar", "Continue", "OK", "Ok", "Entendi", "Got it",
                "Agora não", "Not now", "Fechar", "Dispensar"]
SEL_CAIXA = ["div[contenteditable='true'][data-tab='10']",
             "div[contenteditable='true'][data-tab='6']",
             "footer div[contenteditable='true']",
             "div[role='textbox'][data-tab='10']"]
SEL_LOGADO = ["div[data-testid='chat-list']", "#pane-side", "div[aria-label*='Lista de conversas']"]

# O input de arquivo do WhatsApp Web é escondido (o clique no "+" é só
# enfeite). set_input_files funciona direto nele, sem abrir menu nenhum — é
# menos passo e menos coisa pra mudar de layout.
#
# Sem curinga `input[type='file']` de propósito: o WhatsApp tem MAIS DE UM
# desses, e um deles é o de DOCUMENTO. A foto entrando por ali vira anexo de
# arquivo no grupo — pior que não ter foto. Se nenhum destes casar, o post cai
# pro texto, que é a degradação segura.
SEL_ANEXO = ["input[type='file'][accept*='image']",
             "input[type='file'][accept*='jpeg']",
             "input[type='file'][accept*='png']"]

# ⚠️ PRECISA CLICAR NO ANEXO ANTES (19/08). O código ia direto ao
# `input[type=file]` e chamava `set_input_files` — o que funcionava no
# WhatsApp Web antigo, onde os inputs ficavam sempre montados. No redesign
# eles são montados SOB DEMANDA: o input existe no DOM, aceita o arquivo, e
# nada acontece, porque não está ligado a nada até o menu ser aberto.
# Sintoma medido: "nem imagem nem legenda: o set_input_files não chegou a
# disparar a prévia".
#
# ⚠️ ESTES SELETORES SÃO INFERÊNCIA, não medição — eu não vi o DOM do menu.
# Por isso a falha despeja os botões da tela: a próxima rodada corrige com
# dado em vez de com outro palpite meu.
SEL_BOTAO_ANEXO = [
    "button[aria-label*='anexar' i]",
    "button[aria-label*='attach' i]",
    "span[data-icon='plus-rounded']",
    "span[data-icon='clip']",
    "span[data-icon='attach-menu-plus']",
    "div[role='button'][aria-label*='anexar' i]",
    "div[title*='Anexar' i]",
]
# Depois de anexar, o WhatsApp abre uma TELA DE PRÉVIA com a foto e uma caixa
# de legenda separada da caixa de conversa. Digitar na caixa errada manda a
# legenda como mensagem solta e a foto sem texto — por isso a prévia é
# esperada antes de qualquer tecla.
SEL_PREVIA = ["div[data-testid='media-preview']",
              "div[aria-label*='Enviar'] img",
              "div[role='dialog'] img[src^='blob:']"]
# ⚠️ SAIU DAQUI: `img[src^='blob:']` solto. Medido em 19/08 — o WhatsApp
# renderiza as fotos JÁ ENVIADAS na conversa como `blob:`, então esse seletor
# casava com uma imagem qualquer do histórico do grupo e a checagem "a prévia
# abriu" passava SEM PRÉVIA NENHUMA. O erro seguinte então falava de uma caixa
# de legenda que não existia, e mandou a investigação (a minha) pro seletor
# errado por duas rodadas.

# A prévia do LINK é outra coisa: é o cartão que o WhatsApp monta sozinho
# quando reconhece uma URL na caixa, antes de você mandar. Não confundir com
# `SEL_PREVIA` acima, que é a tela de anexo de imagem.
#
# ⚠️ ESTES SELETORES SÃO PALPITE E SÓ SERVEM PRA LOG. Não vi este DOM. A
# lição das seis rodadas de figurinha é não deixar decisão pendurada em
# seletor não medido — então o envio NUNCA espera por eles: espera o relógio
# (`PREVIA_LINK_SEG`) e manda. Se casar, o log diz que casou, e aí passa a
# ser medição pra próxima vez.
SEL_PREVIA_LINK = ["div[data-testid='media-url-preview']",
                   "footer div[data-testid='link-preview']",
                   "footer a[href^='http'] img",
                   "footer div[role='button'] img[src^='http']"]

# ⚠️ MEDIDO EM 19/08, no despejo de controles: com a prévia aberta aparecem
# 'Cortar e girar', 'Filtrar', 'Desenho', 'Texto', 'Contorno' e o ícone
# `scissors`. São as ferramentas do EDITOR DE IMAGEM, e só existem na prévia.
# Isto não é palpite: é a lista que a própria tela imprimiu.
_ROTULOS_EDITOR = ("cortar e girar", "crop and rotate", "filtrar", "filter",
                   "desenho", "draw", "contorno")

_JS_EDITOR_ABERTO = """
() => {
  const sel = "button,[role='button'],span[data-icon]";
  for (const e of document.querySelectorAll(sel)) {
    if (e.offsetParent === null) continue;
    const rot = ((e.getAttribute("aria-label") || "") + " " +
                 (e.getAttribute("title") || "")).toLowerCase();
    if (!rot) continue;
    for (const alvo of ROTULOS) if (rot.includes(alvo)) return rot.slice(0, 40);
  }
  return "";
}
"""

_JS_PREVIA_ABERTA = """
() => {
  // A prévia É a tela que tem caixa de LEGENDA. Definir por isso, e não por
  // "existe uma imagem", é o que impede o falso positivo: imagem tem em toda
  // conversa; caixa de legenda só existe quando a prévia está aberta.
  const sel = "[contenteditable='true'],input,textarea,[role='textbox']";
  for (const e of document.querySelectorAll(sel)) {
    if (e.offsetParent === null) continue;
    const rot = ((e.getAttribute("aria-label") || "") + " " +
                 (e.getAttribute("aria-placeholder") || "") + " " +
                 (e.getAttribute("placeholder") || "")).toLowerCase();
    if (!rot) continue;
    if (rot.includes("pesquis") || rot.includes("search")) continue;
    if (rot.includes("digite uma mensagem") || rot.includes("type a message")) continue;
    return rot.slice(0, 60);   // achou um campo que só existe na prévia
  }
  return "";
}
"""


def _log(m):
    print(f"[whats] {m}", flush=True)


def _carregar_env():
    """Rodar do terminal não carrega o .env — só o systemd carrega. Mesmo
    carregador da repescagem e do validar_fila; foi essa a armadilha que
    fez o validador gravar 80 desertos em 03/08."""
    for cand in (BASE_DIR / ".env", Path(".env")):
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
            chave, _, valor = linha.partition("=")
            chave = chave.strip()
            if chave and chave not in os.environ:
                os.environ[chave] = valor.strip().strip('"').strip("'")
        return


_carregar_env()

# ── AS TRAVAS, EM CÓDIGO ──────────────────────────────────────────────────
# ⚠️ SÓ DEPOIS DO `_carregar_env()`. Estas linhas viviam no topo do arquivo e
# rodavam antes do .env ser lido — `os.environ.get` devolvia o padrão e o
# valor do arquivo era ignorado em toda execução manual. É o mesmo tipo de
# falha do `echo >> .env`: o ajuste "dá certo", o arquivo muda, o
# comportamento não.
MAX_RODADA = int(float(os.environ.get("WHATSAPP_MAX_RODADA", "2")))
MAX_DIA = int(float(os.environ.get("WHATSAPP_MAX_DIA", "6")))
PAUSA_MIN = float(os.environ.get("WHATSAPP_PAUSA_MIN", "45"))
PAUSA_MAX = float(os.environ.get("WHATSAPP_PAUSA_MAX", "120"))
HORA_INI = int(float(os.environ.get("WHATSAPP_HORA_INI", "7")))
HORA_FIM = int(float(os.environ.get("WHATSAPP_HORA_FIM", "21")))

# ⚠️ DESLIGADO POR PADRÃO DESDE 19/08 — o anexo de foto vira FIGURINHA.
#
# Histórico curto pra ninguém religar sem saber o que está religando: seis
# tentativas de anexar a foto, seis vezes o grupo recebeu FIGURINHA em vez de
# imagem. O `--diag-anexo` do dia 19 mostrou por quê: depois de clicar no "+"
# o DOM continua com UM ÚNICO `input[type=file]`, `accept='image/*'`, o mesmo
# de antes do clique — o menu de anexo não abre pra automação, e esse input
# solitário é o da figurinha. Não existe seletor a corrigir: o elemento que
# eu preciso não é montado.
#
# Então a mensagem vai SÓ COM O LINK, e quem monta o cartão de prévia é o
# próprio WhatsApp, a partir da URL da Shopee. Foto oficial do produto, título
# e preço vindos da origem — melhor do que a nossa miniatura, e sem anexo
# nenhum pra dar errado.
#
# WHATSAPP_COM_FOTO=1 volta o caminho antigo (o código continua inteiro), pra
# quando/se o WhatsApp Web montar o menu de novo.
COM_FOTO = os.environ.get("WHATSAPP_COM_FOTO", "0").strip().lower() in (
    "1", "true", "sim")
# Quanto esperar, depois de digitar, pelo WhatsApp buscar a prévia do link.
# Enter cedo demais manda a mensagem ANTES do cartão anexar, e aí sai link
# pelado — que é justamente o que estamos tentando evitar.
# 10s e não 5: a espera agora é ATIVA (sai assim que o cartão aparece), então
# um teto maior não custa tempo quando dá certo — só dá mais chance quando a
# Shopee demora a responder ao crawler do WhatsApp.
PREVIA_LINK_SEG = float(os.environ.get("WHATSAPP_PREVIA_LINK_SEG", "10"))


def _ligado() -> bool:
    return os.environ.get("WHATSAPP_ATIVO", "0").strip().lower() in ("1", "true", "sim")


def _grupo() -> str:
    return (os.environ.get("WHATSAPP_GRUPO", "") or "").strip()


def _avisar(texto: str, imagem: Path = None):
    """Manda pro Telegram privado — mesma via que o ceo_agent usa. É por aqui
    que chega o QR do login e o print de quando algo quebra."""
    tok = (os.environ.get("TELEGRAM_BOT_TOKEN", "") or "").strip()
    chat = ((os.environ.get("TELEGRAM_ALERT_CHAT_ID")
             or os.environ.get("TELEGRAM_CHAT_ID") or "")).strip()
    if not tok or not chat:
        _log("sem TELEGRAM_BOT_TOKEN/CHAT_ID — não consigo avisar por lá")
        return
    try:
        import requests
        if imagem and imagem.exists():
            with open(imagem, "rb") as f:
                requests.post(f"https://api.telegram.org/bot{tok}/sendPhoto",
                              timeout=30, data={"chat_id": chat, "caption": texto[:900]},
                              files={"photo": f})
        else:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          timeout=20, json={"chat_id": chat, "text": texto[:4000]})
    except Exception as e:
        _log(f"falhei ao avisar no Telegram: {str(e)[:80]}")


def _carregar_json(caminho: Path, padrao):
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:
        return padrao


def _salvar_estado(estado: dict):
    try:
        ESTADO.parent.mkdir(parents=True, exist_ok=True)
        tmp = ESTADO.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, ESTADO)
    except Exception as e:
        _log(f"não consegui gravar o estado: {e}")


def _dentro_da_janela() -> bool:
    return HORA_INI <= datetime.now().hour <= HORA_FIM


def _enviados_hoje(estado: dict) -> int:
    return int(estado.get("por_dia", {}).get(str(date.today()), 0))


def _reais(valor) -> str:
    """R$ 1.600,00 — com ponto de milhar.

    O teste seco mandaria "R$ 1600,00". Não está errado, mas preço sem
    separador some no meio da mensagem e é o número que decide a compra.
    """
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return ""
    return "R$ " + f"{n:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")


_indice_preco = None


def _precos_da_curadoria() -> dict:
    """Preço por link e por nome, vindo do relatório do validador.

    O teste seco de 04/08 mostrou os dois achadinhos limpos **sem preço**: os
    itens de `produtos_fila.json` nem sempre carregam `preco`. O dado existe —
    a curadoria guarda em `validacao_fila.json`, e é de lá que a vitrine
    complementa (`bio_page_builder`, o bloco "2) COMPLEMENTO").

    Então aqui é a MESMA fonte que a vitrine, não uma nova: preço que diverge
    entre a vitrine e o WhatsApp é pior que preço ausente — o cliente vê os
    dois. Nada de rede: só lê o arquivo que o validador já gravou.
    """
    global _indice_preco
    if _indice_preco is not None:
        return _indice_preco
    _indice_preco = {}
    rel = _carregar_json(CURADORIA, {})
    for p in (rel.get("produtos", []) if isinstance(rel, dict) else []):
        if not isinstance(p, dict):
            continue
        try:
            preco = float(p.get("preco") or 0)
        except (TypeError, ValueError):
            continue
        if preco <= 0:
            continue
        for chave in ((p.get("link") or "").strip(),
                      _norm(p.get("campeao") or ""),
                      _norm(p.get("produto") or "")):
            if chave:
                _indice_preco.setdefault(chave, preco)
    return _indice_preco


_historico = None


def _do_historico(link: str) -> dict:
    """O que `precos_historico.json` sabe sobre este link: preço e nome oficial.

    Esta é a MESMA fonte que a vitrine usa (`historico_precos.enriquecer`), e
    é indexada pelo mesmo link de afiliado que está na fila. Vem do
    health-check do deploy, que já pedia esses dados à API e passou a guardar
    — custo zero, nenhuma chamada nova.

    Resolve dois dos defeitos do primeiro post real: o preço que faltava e o
    nome truncado (aqui está o TÍTULO OFICIAL da Shopee, inteiro).
    """
    global _historico
    if not link:
        return {}
    if _historico is None:
        try:
            import historico_precos
            _historico = historico_precos
        except Exception as e:
            _log(f"sem histórico de preços ({str(e)[:60]}) — sigo sem ele")
            _historico = False
    if not _historico:
        return {}
    try:
        dados = _historico.carregar()
        r = _historico.resumo(link, dados=dados) or {}
        return {"preco": float(r.get("preco") or 0),
                "nome": (dados.get(link) or {}).get("nome") or ""}
    except Exception as e:
        _log(f"histórico ilegível ({str(e)[:60]}) — sigo sem ele")
        return {}


def _preco_do_item(item: dict) -> float:
    """Preço do item; 0 se ninguém sabe — e aí a linha some da mensagem.

    Três fontes, da mais específica pra mais geral: o que o item traz, a
    curadoria do validador, e o histórico do health-check. Todas já existem —
    não há chamada de rede nenhuma aqui.

    Nunca inventa: sem preço, o achadinho vai com nome e link. Preço errado
    num grupo de compras é pior que preço nenhum.
    """
    try:
        direto = float(item.get("preco") or 0)
    except (TypeError, ValueError):
        direto = 0.0
    if direto > 0:
        return direto
    idx = _precos_da_curadoria()
    for chave in ((item.get("link") or "").strip(),
                  _norm(_nome_do_item(item)),
                  _norm(item.get("produto") or "")):
        if chave and chave in idx:
            return idx[chave]
    return float(_do_historico((item.get("link") or "").strip()).get("preco") or 0)


def _nome_do_item(item: dict) -> str:
    return (item.get("campeao") or item.get("produto")
            or item.get("titulo") or item.get("nome") or "").strip()


# Antes ficava em 70 e cortava "Kit 4 Essência 10ml Para Aromatizador
# Difusor Umidificador..." no meio — o cliente não sabia o que era. A legenda
# de foto do WhatsApp aceita ~1024 caracteres; 110 mostra o nome inteiro da
# quase totalidade dos anúncios e ainda cabe numa olhada.
NOME_MAX = 110


def _titulo_do_item(item: dict) -> str:
    """O melhor nome disponível, inteiro sempre que couber.

    Prefere o título OFICIAL da Shopee (guardado pelo health-check) ao nome
    que o coletor extraiu do vídeo: é o mesmo nome que a vitrine mostra, e é
    o que o cliente vai reler quando abrir o link.
    """
    oficial = _do_historico((item.get("link") or "").strip()).get("nome") or ""
    nome = " ".join((oficial or _nome_do_item(item) or "Achadinho").split())

    # ⚠️ TÍTULO DA SHOPEE É EMPILHAMENTO DE PALAVRA-CHAVE, não frase. O
    # primeiro achadinho real do grupo saiu como "Pá Pega Coletora Pet Coletor
    # Fezes Cocô Cachorro Gato" — o vendedor repete sinônimo pra ranquear na
    # busca, e o resultado no grupo é uma frase desagradável de ler (queixa do
    # Dre em 19/08, e ele tem razão: ninguém compra de anúncio que dá nojo).
    #
    # Tiro só REPETIÇÃO e os termos crus mais óbvios. Não reescrevo o título:
    # ele é o mesmo nome que o cliente vai reler quando abrir o link, e mudar
    # o produto de nome faria a pessoa achar que clicou no lugar errado.
    _CRUS = {"fezes", "cocô", "coco", "excremento", "dejeto"}
    palavras, vistas, saida = nome.split(), set(), []
    for p in palavras:
        chave = _norm(p.strip(",.;")) or p.lower()
        if chave in _CRUS and saida:      # nunca apago a 1ª palavra
            continue
        if chave and chave in vistas:     # "Pá Pega Coletora ... Coletor"
            continue
        vistas.add(chave)
        saida.append(p)
    nome = " ".join(saida) or nome

    if len(nome) > NOME_MAX:
        nome = nome[:NOME_MAX - 1].rsplit(" ", 1)[0] + "…"
    return nome


def _link_etiquetado(item: dict) -> str:
    """O link do achadinho com o canal `wa` no sub_id. Best-effort.

    ⚠️ POR QUE (17/08): este script mandava `item["link"]`, o link genérico da
    fila — sem canal. Venda vinda do WhatsApp caía em "direto", misturada com
    tráfego orgânico e com o que não tem etiqueta nenhuma. Ou seja: o canal
    nasceria cego, e a pergunta "o WhatsApp paga?" só teria resposta refazendo
    a atribuição meses depois, no chute. É a mesma história dos 42 posts com
    plataforma `?` — e a gente acabou de montar as 5 etiquetas hoje justamente
    pra não repetir isso.

    ⚠️ ORDEM CANÔNICA, SEM BURACO: `[canal, nicho, produto]`. Três etiquetas e
    ponto — nada de vídeo aqui, e por isso NÃO entra a sentinela `semfonte`.
    Ela só existe pra segurar o índice 3 quando há vídeo no 4; usá-la aqui
    criaria uma "fonte" chamada semfonte em toda venda do grupo, que é
    exatamente o defeito que ela foi criada pra evitar.

    ⚠️ E FALHA VOLTA PRO LINK BASE, nunca derruba o envio. Link sem etiqueta
    perde a atribuição; link nenhum perde a venda. A escolha é fácil.
    """
    base = (item.get("link") or "").strip()
    origem = (item.get("origem") or item.get("origem_url") or "").strip()

    # ⚠️ A FILA NÃO TEM CAMPO DE ORIGEM — e isso quase deixou esta função ser
    # código morto. A 1ª versão exigia `origem`/`origem_url`; conferido em
    # `validar_fila`/`curar_fila`, nenhum dos dois grava esse campo, então ela
    # caía no `base` SEMPRE, em silêncio, e o teste seco mostrava link sem
    # etiqueta com cara de link etiquetado. O que a fila tem (desde hoje) é
    # `shop_id` + `item_id`, e a URL canônica se remonta com os dois — é o
    # mesmo formato `i.{shop}.{item}` que o `_extrair_ids` do próprio
    # `shopee_affiliate` sabe ler.
    if not origem:
        shop, item_id = (str(item.get("shop_id") or "").strip(),
                         str(item.get("item_id") or "").strip())
        if shop.isdigit() and item_id.isdigit():
            origem = f"https://shopee.com.br/-i.{shop}.{item_id}"

    if not origem:
        # ⚠️ NÃO SILENCIOSO. Sem origem não dá pra etiquetar, e o post sai com
        # o link base — a venda conta, a atribuição por canal não. Dizer isso
        # é o que impede "achei que estava medindo" daqui a um mês.
        _log(f"   (sem shop_id/item_id: '{(item.get('produto') or '?')[:34]}' "
             f"vai SEM etiqueta de canal)")
        return base
    try:
        try:
            from integrations.shopee_affiliate import gerar_link_afiliado
        except Exception:
            from shopee_affiliate import gerar_link_afiliado
        import re as _re

        def _s(x, padrao):
            v = _re.sub(r"[^A-Za-z0-9]", "", str(x or ""))[:16]
            return v or padrao

        # ⚠️ A FILA NÃO GRAVA `nicho` — conferido, 0 ocorrências no
        # `validar_fila` e no `curar_fila`. Então `item.get("nicho")` era
        # sempre None e a 2ª etiqueta saía `geral` pra TUDO: capa de edredom
        # (casa) e pijama (moda) vieram as duas como geral no teste de 18/08.
        # Etiqueta constante não é etiqueta — é um campo ocupado sem informar
        # nada, e ia empurrar a análise por nicho do WhatsApp pra sempre.
        #
        # Deriva com o MESMO roteador que a produção usa, em vez de inventar
        # regra local: se o `produzir_tiktok` chama uma coisa de "casa", o
        # WhatsApp precisa chamar igual, senão os dois canais não cruzam.
        nicho = ""
        try:
            import roteador_contas as _RC
            nicho = _RC.nicho_do_produto(
                item.get("produto") or item.get("campeao") or "",
                item.get("categoria") or "")
        except Exception:
            nicho = ""      # sem roteador cai no default, e o default é honesto
        subs = ["wa", _s(nicho, "geral"),
                _s(item.get("produto") or item.get("campeao"), "prod")]
        r = gerar_link_afiliado(origem, sub_ids=subs)
        if isinstance(r, dict) and r.get("ok"):
            novo = r.get("short_link") or r.get("link") or base
            # ⚠️ O SUCESSO TAMBÉM PRECISA FALAR. Eu tinha posto log nos quatro
            # caminhos de falha e deixado este mudo — e aí "funcionou" e "nem
            # foi chamado" produzem exatamente a mesma tela. Passei duas
            # rodadas concluindo "não foi chamado" sem ter como saber.
            #
            # E há um caso real em que o link SAI IGUAL mesmo dando certo: se
            # a Shopee devolve o mesmo short link pra mesma URL de origem, a
            # etiqueta fica registrada do lado deles e a URL não muda do nosso.
            # Pelo link não dá pra distinguir; pelos sub_ids, dá.
            _log(f"   🏷️  sub_ids={subs}"
                 + ("  (link inalterado — a Shopee reusou o encurtado)"
                    if novo == base else ""))
            return novo
        # ⚠️ SEGUNDA SAÍDA SILENCIOSA, na função que eu tinha ACABADO de
        # consertar por ser silenciosa (17/08). Eu tratei o caso "não tem
        # origem" e deixei passar o caso "a API respondeu não": o `if ok` sem
        # `else` caía no `return base` sem uma linha de log. O teste seco na
        # VPS mostrou o sintoma exato — link idêntico ao da rodada anterior e
        # NENHUM aviso, ou seja, os dois caminhos que eu sabia diagnosticar
        # estavam descartados e sobrou o que eu não tinha coberto.
        # Todo `if sucesso: return` precisa do irmão que conta o fracasso.
        _log(f"   (API recusou o link 'wa' de "
             f"'{(item.get('produto') or '?')[:28]}': "
             f"{str((r or {}).get('erro'))[:60]} — vai SEM etiqueta)")
    except Exception as e:
        _log(f"   (link etiquetado 'wa' falhou, uso o base: {str(e)[:60]})")
    return base


# ⚠️ CHAMADAS VARIADAS (pedido do Dre em 19/08). Antes era UMA frase fixa,
# "🔥 Corre que é por tempo limitado!", em todo achadinho de toda rodada. Num
# grupo que recebe 6 por dia, a mesma frase repetida vira ruído: o membro para
# de ler a linha inteira, e ela é justamente a que pede a ação.
#
# Repare que NENHUMA inventa urgência que não existe ("acaba em 2h", "últimas
# unidades") — a gente não sabe o estoque, e promessa falsa queima a
# comunidade que levou meses pra juntar. Elas variam o TOM, não o fato.
CHAMADAS = [
    "🔥 Corre que é por tempo limitado!",
    "👀 Achadinho desses não fica parado, viu",
    "🛒 Se gostou, garante o seu",
    "💸 Tá valendo demais por esse preço",
    "⚡ Dá uma olhada antes que suma",
    "😍 Esse aqui eu não deixaria passar",
]


def _chamada(item: dict) -> str:
    """A linha de chamada, sorteada — mas ESTÁVEL por produto.

    Sorteio por hash do link, e não `random.choice`: o mesmo achadinho
    reenviado (retentativa, rodada repetida) sai com a mesma frase. Com
    sorteio puro, uma falha no meio do envio poderia mandar o mesmo produto
    com duas chamadas diferentes, e no grupo isso lê como dois anúncios.
    """
    chave = (item.get("link") or item.get("produto") or "").strip()
    if not chave:
        return CHAMADAS[0]
    return CHAMADAS[sum(chave.encode("utf-8")) % len(CHAMADAS)]


def _mensagem(item: dict) -> str:
    """A legenda do achadinho — mesmo formato do grupo do Telegram.

    Copiar a FORMA do `_montar_legenda` do telegram_poster é de propósito: as
    duas comunidades são do mesmo dono e recebem os mesmos produtos. Formato
    diferente por surface faz o cliente que está nos dois achar que são
    revendas diferentes.

    Muda só a marcação: o WhatsApp usa *negrito* e não embute link em texto,
    então a URL vai crua — sozinha ela vira prévia clicável.
    """
    linhas = [f"🛍️ *{_titulo_do_item(item)}*", ""]
    preco = _preco_do_item(item)
    if preco:
        linhas.append(f"💰 {_reais(preco)}")
    linhas.append(_chamada(item))
    linhas.append("")
    # ⚠️ o link ETIQUETADO vai pra mensagem; o `item["link"]` cru continua
    # sendo a chave de dedup (`whatsapp_enviados.json`) em outro lugar do
    # arquivo. Trocar a chave faria o script reenviar tudo que já saiu, porque
    # o link etiquetado é novo a cada geração.
    linhas.append(f"👉 {_link_etiquetado(item)}")
    return "\n".join(linhas)


def _candidatos(fila, ja: set, quantos: int, resta_dia: int) -> list:
    """Quem entra nesta rodada. Separado do navegador de propósito: é a parte
    que decide o que vai pro ar, e tem que ser testável sem abrir o Chromium.

    Mesma regra do grupo do Telegram: precisa de link E foto.

    ⚠️ A exigência de foto SOBREVIVEU à mudança pra link-só (19/08), e não por
    esquecimento: desde que a prévia passou a vir do próprio WhatsApp, a nossa
    `imagem` não é mais usada no envio — mas item sem `imagem` é item cuja
    coleta veio incompleta, e esses costumam vir com preço e nome ruins
    também. O campo virou um atestado de coleta inteira. Se um dia quiser
    afrouxar, olhe primeiro quantos itens isso libera e com que cara.

    E precisa de NOME que sirva pra cliente. O teste seco de 04/08 ia mandar
    "*Produto com busca alta* — R$ 1.600,00": rótulo interno que vazou pra
    fila e que nenhum filtro do projeto pegava. Aqui vale a regra de quem
    publica — pular um produto bom custa menos que mandar lixo pro grupo.
    """
    if not isinstance(fila, list):
        return []
    if _nome_ruim is None:
        _log(f"❌ não consegui carregar shared/termos.py ({_ERRO_REGRA}) — sem a "
             "regra de nome eu não mando nada, pra não postar rótulo interno.")
        return []
    novos, pulados = [], 0
    for it in fila:
        if not isinstance(it, dict):
            continue
        if not it.get("link") or not it.get("imagem") or it["link"] in ja:
            continue
        if _nome_ruim(_nome_do_item(it)):
            pulados += 1
            continue
        novos.append(it)
    if pulados:
        _log(f"{pulados} item(ns) pulado(s) por nome que não serve pra cliente")
    return novos[:max(0, min(quantos, resta_dia))]


def _achar(pagina, seletores, timeout=8000):
    """O primeiro seletor que existir de verdade. None se nenhum casar."""
    for s in seletores:
        try:
            el = pagina.wait_for_selector(s, timeout=timeout, state="visible")
            if el:
                return el
        except Exception:
            continue
    return None


def _digitavel(nome: str) -> str:
    """O que dá pra digitar do nome do grupo.

    O grupo é "💭 ACHADINHOS VIP TOPSHOP". keyboard.type não emite caractere
    fora do BMP de forma confiável (emoji é par surrogate), e um emoji que sai
    errado transforma a busca em zero resultado. Digito só o texto legível —
    a busca do WhatsApp casa por trecho, então acha do mesmo jeito.
    """
    limpo = "".join(c for c in (nome or "") if ord(c) < 0x2190 or c.isspace())
    limpo = " ".join(limpo.split())
    return limpo or (nome or "").strip()


def _norm(s: str) -> str:
    return " ".join((s or "").split()).strip().lower()


def _achar_grupo(pagina, grupo: str):
    """A linha do grupo no resultado da busca.

    Tenta o título exato primeiro; se não casar (emoji, espaço a mais, nome
    renomeado no celular), aceita o item cujo título CONTENHA o texto legível.
    Só isso — não pego "o primeiro resultado", que é como se manda achadinho
    pra conversa errada.
    """
    alvo_cheio, alvo_txt = _norm(grupo), _norm(_digitavel(grupo))
    try:
        # ensure_ascii=False de propósito: no padrão, o json.dumps troca o
        # emoji por um par de escapes barra-u, e o CSS lê barra-d83d como
        # escape HEXADECIMAL, não como o emoji. O seletor casaria com nada.
        alvo_css = json.dumps(grupo, ensure_ascii=False)
        exato = pagina.query_selector(f"span[title={alvo_css}]")
        if exato:
            return exato
    except Exception:
        pass
    # o escopo vai do mais específico ao mais amplo. Varrer a página inteira é
    # seguro aqui porque a escolha é por comparação de título, não por posição:
    # ou o título casa com o grupo, ou o elemento é ignorado.
    for escopo in ("#pane-side span[title]",
                   "div[role='listitem'] span[title]",
                   "[role='grid'] span[title]",
                   "span[title]"):
        try:
            itens = pagina.query_selector_all(escopo)
        except Exception:
            continue
        for el in itens:
            try:
                t = _norm(el.get_attribute("title") or "")
            except Exception:
                continue
            if not t:
                continue
            if t == alvo_cheio or (alvo_txt and alvo_txt in t):
                return el
    return None


_RE_BUSCA = re.compile(r"pesquis|search|busca", re.I)


def _achar_busca(pagina):
    """A caixa de busca, perguntando pelo NOME e não pela marcação.

    Em 04/08 o WhatsApp Web trocou de layout (o painel direito virou "Enviar
    documento / Adicionar contato / Perguntar à Meta AI") e todo `SEL_BUSCA`
    baseado em `data-tab` parou de casar. Perseguir data-tab é correr atrás de
    um alvo que muda sem aviso.

    O que NÃO muda é o nome acessível: o campo se apresenta como "Pesquisar ou
    começar uma nova conversa" — está escrito no print. Então tento primeiro
    os CSS conhecidos (rápidos, e ainda valem em quem não atualizou) e, se
    nenhum casar, pergunto por papel/placeholder/título. Assim funciona seja o
    campo um <input>, um contenteditable ou o que inventarem depois.
    """
    el = _achar(pagina, SEL_BUSCA, timeout=3000)
    if el:
        return el
    tentativas = [
        lambda: pagina.get_by_role("textbox", name=_RE_BUSCA),
        lambda: pagina.get_by_placeholder(_RE_BUSCA),
        lambda: pagina.get_by_title(_RE_BUSCA),
        lambda: pagina.locator("[aria-label*='esquis' i], [placeholder*='esquis' i]"),
    ]
    for fazer in tentativas:
        try:
            loc = fazer().first
            loc.wait_for(state="visible", timeout=3000)
            return loc
        except Exception:
            continue
    return None


def _abrir_grupo(pagina, grupo: str):
    """Abre a conversa do grupo. True se abriu.

    Tenta pela LISTA antes da busca: no print de 04/08 o "💭 ACHADINHOS VIP
    TOPSHOP" está no topo do pane lateral, visível sem pesquisar nada. Quando
    ele está ali, esse caminho não depende de caixa de busca nenhuma — que é
    justo a parte que o WhatsApp mais mexe.
    """
    item = _achar_grupo(pagina, grupo)
    if item:
        item.click()
        _log("grupo aberto direto da lista (sem busca)")
        pagina.wait_for_timeout(1800)
        return _confere_conversa(pagina, grupo)

    busca = _achar_busca(pagina)
    if not busca:
        return None  # None = não achei a busca; False = achei mas não o grupo
    busca.click()
    # digita SEM emoji: o grupo é "💭 ACHADINHOS VIP TOPSHOP" e o keyboard.type
    # não emite caractere fora do BMP de forma confiável.
    pagina.keyboard.type(_digitavel(grupo), delay=random.randint(60, 140))
    pagina.wait_for_timeout(2200)
    item = _achar_grupo(pagina, grupo)
    if not item:
        return False
    item.click()
    pagina.wait_for_timeout(1800)
    return _confere_conversa(pagina, grupo)


_JS_TITULO_CONVERSA = """
() => {
  const m = document.querySelector('#main') || document;
  const h = m.querySelector('header');
  return h ? (h.innerText || '').trim().slice(0, 120) : '';
}
"""


def _confere_conversa(pagina, grupo: str) -> bool:
    """A conversa aberta é MESMO a do grupo? False quando é outra.

    ⚠️ POR QUE ISTO EXISTE (20/08). O `_abrir_grupo` clicava num item da lista
    e devolvia True sem olhar o que abriu. O risco não é a mensagem não sair —
    é ela sair NO LUGAR ERRADO: um anúncio de afiliado caindo na conversa
    privada de alguém, mandado por um robô, às 9 da manhã. Isso não dá pra
    desfazer, e é muito pior que uma rodada perdida.

    Regra: recuso quando tenho PROVA de que é outra conversa. Quando não
    consigo ler o cabeçalho, aviso e sigo — o item da lista foi casado pelo
    nome, então há evidência a favor, e travar tudo por um seletor que eu não
    medi já custou seis rodadas nesta mesma tela.
    """
    try:
        titulo = (pagina.evaluate(_JS_TITULO_CONVERSA) or "").strip()
    except Exception:
        titulo = ""
    if not titulo:
        _log("   ⚠️ não consegui ler o cabeçalho da conversa — sigo, mas sem "
             "conferir. (Se aparecer sempre, é seletor a corrigir.)")
        return True
    alvo = _sem_emoji(grupo).strip().lower()
    visto = _sem_emoji(titulo).strip().lower()
    if alvo and alvo.split("\n")[0] in visto:
        _log(f"   ✔️ conversa conferida: {titulo.splitlines()[0][:48]!r}")
        return True
    caminho = _print_erro(pagina, f"abri a conversa ERRADA: {titulo[:60]!r}")
    _avisar(f"WhatsApp: cliquei e abriu '{titulo.splitlines()[0][:60]}' em vez "
            f"de '{grupo}'. NÃO mandei nada — mensagem em conversa errada não "
            f"tem desfazer.", caminho)
    return False


def _sem_emoji(s: str) -> str:
    """Só letras/números/espaço — o nome do grupo tem emoji e o cabeçalho pode
    renderizar como imagem, então comparar cru daria falso negativo."""
    return re.sub(r"[^\w\s]", " ", s or "", flags=re.U)


def _fechar_modal(pagina, voltas: int = 3) -> int:
    """Dispensa o aviso que o WhatsApp Web abre por cima da interface.

    Retorna quantos diálogos foram fechados. Nenhum diálogo é o caso normal —
    por isso não é erro voltar 0. Faz até 3 voltas porque às vezes um aviso
    revela outro atrás.

    Deliberadamente conservador: só clica em botão que esteja dentro de um
    diálogo E cujo texto esteja em TXT_MODAL_OK. Se o diálogo for outra coisa
    (um "sair de todos os aparelhos?", por exemplo), o script prefere não
    achar a busca e parar com print a clicar no escuro.
    """
    fechados = 0
    for _ in range(max(1, voltas)):
        dialogo = None
        for s in SEL_MODAL:
            try:
                el = pagina.query_selector(s)
            except Exception:
                el = None
            if el and el.is_visible():
                dialogo = el
                break
        if not dialogo:
            break

        titulo = ""
        try:
            titulo = (dialogo.inner_text() or "").strip().splitlines()[0][:60]
        except Exception:
            pass

        clicou = False
        try:
            botoes = dialogo.query_selector_all("button, div[role='button']")
        except Exception:
            botoes = []
        for b in botoes:
            try:
                rotulo = (b.inner_text() or "").strip()
                if rotulo and any(rotulo.lower() == t.lower() for t in TXT_MODAL_OK):
                    b.click()
                    _log(f"aviso dispensado: {titulo!r} → botão {rotulo!r}")
                    clicou = True
                    break
            except Exception:
                continue

        if not clicou:
            # tem diálogo, mas nenhum botão que eu reconheça — não invento
            _log(f"⚠️  há um diálogo aberto que eu não sei fechar: {titulo!r}")
            break
        fechados += 1
        pagina.wait_for_timeout(1200)
    return fechados


def _print_erro(pagina, motivo: str) -> Path:
    ERROS.mkdir(parents=True, exist_ok=True)
    caminho = ERROS / f"{datetime.now():%Y%m%d-%H%M%S}.png"
    try:
        pagina.screenshot(path=str(caminho))
    except Exception:
        pass
    _log(f"❌ {motivo} — print em {caminho}")
    return caminho


def _baixar_foto(url: str) -> Path:
    """Baixa a foto do produto pra um arquivo temporário. None se não der.

    Sem foto o achadinho vira link solto — foi exatamente a queixa do primeiro
    post real. Mas foto é enfeite: se o download falhar, a mensagem vai como
    texto, que ainda vende. Nunca deixo o post inteiro morrer por causa dela.
    """
    url = (url or "").strip()
    if not url.startswith("http"):
        return None
    try:
        import requests
        r = requests.get(url, timeout=25, headers={"User-Agent": _UA})
        r.raise_for_status()
        if not r.content or len(r.content) < 1024:
            _log("   foto veio vazia demais — mando sem foto")
            return None
        tipo = (r.headers.get("Content-Type") or "").lower()
        FOTOS.mkdir(parents=True, exist_ok=True)
        base = FOTOS / f"{datetime.now():%H%M%S}-{random.randint(100, 999)}"

        # ⚠️ WEBP VIRA FIGURINHA NO WHATSAPP (medido 19/08). A Shopee serve as
        # fotos em WebP, e `.webp` É o formato de sticker do WhatsApp — o
        # primeiro achadinho real do grupo saiu como figurinha quadradinha em
        # vez de foto de produto. Não é questão de extensão: o WhatsApp lê o
        # conteúdo, então renomear não resolve. Converte de verdade.
        # ⚠️ PELOS BYTES, NÃO PELO CABEÇALHO (19/08). A 1ª versão olhava só o
        # `Content-Type` do HTTP — se o servidor manda header errado, ausente,
        # ou `application/octet-stream`, o WebP passa batido e a foto continua
        # virando figurinha. O arquivo diz o que é: WebP começa com "RIFF" e
        # traz "WEBP" no byte 8. Isso não depende de ninguém ser honesto.
        # ⚠️ SEMPRE JPEG, seja qual for a origem (19/08, 2ª volta).
        # A 1ª versão convertia só quando o `Content-Type` dizia webp — e a
        # foto continuou saindo como figurinha no grupo. Header mente, some,
        # ou vem `application/octet-stream`; e o WhatsApp decide pelo CONTEÚDO.
        # Em vez de acertar a adivinhação, tiro a adivinhação do caminho:
        # abre, converte, grava JPEG. Um re-encode por achadinho (6/dia) é
        # barato perto de um grupo recebendo sticker no lugar de produto.
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(r.content))
            formato = img.format or "?"
            # fundo branco: WebP e PNG costumam ter transparência, e JPEG não
            # tem canal alfa — sem isto o fundo sairia PRETO
            if img.mode in ("RGBA", "LA", "P"):
                fundo = Image.new("RGB", img.size, (255, 255, 255))
                img = img.convert("RGBA")
                fundo.paste(img, mask=img.split()[-1])
                img = fundo
            else:
                img = img.convert("RGB")
            destino = base.with_suffix(".jpg")
            img.save(destino, "JPEG", quality=90)
            if formato.upper() == "WEBP":
                _log(f"   foto era WebP (iria como FIGURINHA) — convertida "
                     f"pra JPEG  ·  Content-Type dizia {tipo or 'nada'}")
            else:
                _log(f"   foto {formato} normalizada pra JPEG")
            return destino
        except Exception as e:
            # ⚠️ só salvo o arquivo cru se ele JÁ for JPEG pelos bytes. Salvar
            # um webp que não consegui converter manda figurinha, e figurinha
            # é pior que foto nenhuma: parece spam de sticker no grupo.
            if r.content[:3] == b"\xff\xd8\xff":
                destino = base.with_suffix(".jpg")
                destino.write_bytes(r.content)
                _log(f"   (não abri com PIL: {str(e)[:40]} — mas os bytes são "
                     f"JPEG, mando assim)")
                return destino
            _log(f"   não converti a imagem ({str(e)[:45]}) — mando SEM foto, "
                 f"porque o formato cru pode ir como figurinha")
            return None

    except Exception as e:
        _log(f"   não baixei a foto ({str(e)[:60]}) — mando sem foto")
        return None


_JS_LEGENDA_FOCADA = """
() => {
  const a = document.activeElement;
  if (!a) return false;
  // ⚠️ NÃO EXIGIR MAIS `contenteditable` (19/08). O WhatsApp Web migrou os
  // campos de texto: o `--diag` de 18/08 mostrou a própria caixa de busca
  // como `<input type="text" role="textbox">`, e não mais como div
  // contenteditable. Com a exigência antiga, o clique acertava a legenda e a
  // VERIFICAÇÃO reprovava — o erro saía como "não consegui focar a legenda"
  // quando o foco estava certo. Aceita editável de qualquer forma.
  const tag = (a.tagName || "").toLowerCase();
  const editavel = (a.getAttribute("contenteditable") === "true"
                    || tag === "textarea"
                    || (tag === "input" && !["checkbox", "radio", "button",
                                             "submit", "file"].includes(
                          (a.getAttribute("type") || "text").toLowerCase()))
                    || a.getAttribute("role") === "textbox");
  if (!editavel) return false;
  const rot = ((a.getAttribute("aria-label") || "") + " " +
               (a.getAttribute("aria-placeholder") || "") + " " +
               (a.getAttribute("placeholder") || "") + " " +
               (a.getAttribute("data-tab") || "")).toLowerCase();
  // a caixa de BUSCA também é editável — se o foco caiu nela, digitar ali
  // procura conversa em vez de escrever legenda
  if (rot.includes("pesquis") || rot.includes("search")) return false;
  return true;
}
"""


def _sair_da_previa(pagina):
    """Descarta a prévia sem enviar, e CONFIRMA o descarte.

    ⚠️ ESCAPE NÃO FECHA O DIÁLOGO DE CONFIRMAÇÃO (medido 19/08, no print que o
    Dre mandou). O 1º Escape abre "Deseja descartar a seleção?" com os botões
    *Cancelar* e *Descartar* — e o 2º Escape não o dispensa. O diálogo ficava
    ABERTO cobrindo a página, e a tentativa seguinte (mandar só o texto) morria
    com `ElementHandle.click: Timeout 30000ms` — elemento visível cujo clique
    não completa é elemento coberto, e o que cobria era o nosso próprio
    diálogo.
    """
    for _ in range(2):
        try:
            pagina.keyboard.press("Escape")
            pagina.wait_for_timeout(700)
        except Exception:
            return

    # ⚠️ CLICO EM "Descartar" PELO TEXTO, e só dentro de um diálogo cujo
    # enunciado fale em descartar. A regra do `_fechar_modal` vale aqui: botão
    # de diálogo se clica sabendo qual diálogo é. "Descartar" no lugar errado
    # joga fora uma mensagem composta; num diálogo de sessão, seria pior.
    for _ in range(3):
        try:
            dlg = pagina.query_selector("div[role='dialog']")
            if not dlg or not dlg.is_visible():
                return
            txt = (dlg.inner_text() or "").lower()
            if "descartar" not in txt and "discard" not in txt:
                _log(f"   ⚠️ diálogo aberto que NÃO é o de descarte "
                     f"({txt.splitlines()[0][:48]!r}) — não clico, deixo pra "
                     f"revisão humana")
                _print_erro(pagina, "diálogo inesperado sobre a prévia")
                return
            for rot in ("Descartar", "Discard"):
                b = dlg.query_selector(f"button:has-text('{rot}')")
                if b and b.is_visible():
                    b.click(timeout=4000)
                    pagina.wait_for_timeout(700)
                    _log("   prévia descartada (confirmei no diálogo)")
                    break
            else:
                return
        except Exception:
            return


def _focar_legenda(pagina) -> bool:
    """Põe o cursor na caixa de LEGENDA da prévia. False se não conseguiu.

    Escrito depois do erro de 04/08: `ElementHandle.click: Timeout 30000ms`
    com "element is visible, enabled and stable". Elemento visível cujo clique
    não completa é elemento COBERTO por outro — eu pegava "a última
    contenteditable visível" da página, e a tela de prévia tem editor de
    imagem, texto, recorte. Peguei o elemento errado. Foi chute, e chute era
    justamente o que este arquivo diz não fazer.

    Agora vai pelo nome ("Adicione uma legenda") e, no fim, pelo caminho que
    não depende de marcação nenhuma: Tab até o foco cair numa editável que
    NÃO seja a busca. E o teclado confirma onde está antes de digitar —
    digitar na caixa de busca procuraria conversa em vez de escrever legenda.
    """
    # ⚠️ SEM PRENDER NA TAG (19/08). A lista antiga era toda `div[...]`, de
    # quando os campos do WhatsApp eram divs contenteditable. Eles viraram
    # `input`/`textarea` — visto no `--diag` de 18/08, onde a caixa de busca
    # aparece como `<input type="text" role="textbox">`. Seletor preso em
    # `div` não acha mais nada, e o sintoma é "não consegui focar a legenda".
    # Agora casa pelo RÓTULO (que é o que descreve a função) em qualquer tag.
    alvos = [
        "[contenteditable='true'][aria-label*='legenda' i]",
        "[contenteditable='true'][aria-placeholder*='legenda' i]",
        "[aria-label*='legenda' i]",
        "[aria-placeholder*='legenda' i]",
        "[placeholder*='legenda' i]",
        "[aria-label*='caption' i]",
        "[placeholder*='caption' i]",
        "[role='textbox'][aria-label*='legenda' i]",
    ]
    for s in alvos:
        try:
            el = pagina.query_selector(s)
            if el and el.is_visible():
                el.click(timeout=5000)
                if pagina.evaluate(_JS_LEGENDA_FOCADA):
                    return True
        except Exception:
            continue

    # último recurso sem marcação: o Tab anda pelos focáveis da prévia
    for _ in range(8):
        try:
            pagina.keyboard.press("Tab")
            pagina.wait_for_timeout(250)
            if pagina.evaluate(_JS_LEGENDA_FOCADA):
                return True
        except Exception:
            break
    # a prévia às vezes já abre com a legenda focada
    try:
        if pagina.evaluate(_JS_LEGENDA_FOCADA):
            return True
    except Exception:
        return False

    # ⚠️ FALHA VIRA EVIDÊNCIA (19/08). Antes, não focar rendia só um PNG — e
    # print não se lê de dentro de uma conversa, nem entra em `grep`. Sem a
    # marcação real, o conserto do seletor vira adivinhação, que é exatamente
    # o que o cabeçalho desta função diz não fazer. Agora ela DESPEJA os
    # campos de texto que existem na tela no momento da falha, e a próxima
    # quebra do WhatsApp Web já chega com o dado do lado do erro.
    #
    # Nunca imprime VALOR de campo — só rótulo, tag e tipo.
    try:
        campos = pagina.evaluate("""
        () => {
          const sel = "[contenteditable='true'],input,textarea,[role='textbox']";
          return Array.from(document.querySelectorAll(sel))
            .filter(e => e.offsetParent !== null)
            .slice(0, 14)
            .map(e => ({
              tag: e.tagName.toLowerCase(),
              tipo: e.getAttribute("type") || "",
              editavel: e.getAttribute("contenteditable") || "",
              papel: e.getAttribute("role") || "",
              rotulo: (e.getAttribute("aria-label") ||
                       e.getAttribute("aria-placeholder") ||
                       e.getAttribute("placeholder") || "").slice(0, 60),
            }));
        }""")
        _log("   campos de texto visíveis na prévia (pra corrigir o seletor):")
        for c in campos or []:
            _log(f"     <{c['tag']}{(' type=' + c['tipo']) if c['tipo'] else ''}"
                 f"{(' contenteditable=' + c['editavel']) if c['editavel'] else ''}"
                 f"{(' role=' + c['papel']) if c['papel'] else ''}>"
                 f"  rótulo: {c['rotulo']!r}")
        if not campos:
            _log("     NENHUM campo de texto visível — a prévia pode não ter "
                 "aberto de verdade, apesar de o passo anterior achar que sim.")
    except Exception as e:
        _log(f"   (não consegui listar os campos: {str(e)[:60]})")
    return False


def _dump_botoes(pagina, motivo: str):
    """Despeja os botões/ícones clicáveis da tela, pra corrigir seletor com
    dado em vez de palpite.

    ⚠️ Existe pela mesma razão do despejo de campos de texto: em 19/08 eu
    passei duas rodadas consertando o seletor errado porque a mensagem de erro
    descrevia um estado que não era o real. Print não entra em `grep`.
    Nunca imprime texto de mensagem — só rótulo/ícone de controle.
    """
    try:
        itens = pagina.evaluate("""
        () => {
          const sel = "button,[role='button'],span[data-icon]";
          return Array.from(document.querySelectorAll(sel))
            .filter(e => e.offsetParent !== null)
            // ⚠️ 20 ERA POUCO e cortava justamente o que interessa. Medido em
            // 19/08: a barra lateral do app (Conversas, Ligações, Status,
            // Canais, Comunidades, Ferramentas, Anunciar, Mídia, Config.,
            // Perfil…) vem PRIMEIRO no DOM e já enche as 20 vagas — o menu de
            // anexo, que abre perto da caixa de mensagem, nunca aparecia na
            // lista. Eu li "só tem a barra lateral" como "o menu não abriu".
            .slice(0, 60)
            .map(e => ({
              tag: e.tagName.toLowerCase(),
              icone: e.getAttribute("data-icon") || "",
              rotulo: (e.getAttribute("aria-label") ||
                       e.getAttribute("title") || "").slice(0, 40),
            }))
            .filter(x => x.icone || x.rotulo);
        }""")
        _log(f"   controles visíveis ({motivo}):")
        for i in itens or []:
            _log(f"     <{i['tag']}"
                 f"{(' data-icon=' + i['icone']) if i['icone'] else ''}>"
                 f"  rótulo: {i['rotulo']!r}")
    except Exception as e:
        _log(f"   (não consegui listar os controles: {str(e)[:60]})")


_JS_DESPEJO_PREVIA = """
() => {
  const pe = document.querySelector('footer') || document.body;
  const fora = [];
  for (const e of pe.querySelectorAll('img,div[role="button"],span[data-icon],a')) {
    if (e.offsetParent === null) continue;
    const r = e.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) continue;
    fora.push({
      tag: e.tagName.toLowerCase(),
      icone: e.getAttribute('data-icon') || '',
      src: (e.getAttribute('src') || '').slice(0, 70),
      testid: e.getAttribute('data-testid') || '',
      classe: (e.getAttribute('class') || '').split(' ')[0].slice(0, 24),
      texto: (e.innerText || '').trim().slice(0, 40),
      w: Math.round(r.width), h: Math.round(r.height),
    });
  }
  return fora.slice(0, 40);
}
"""


def _dump_previa(pagina):
    """O que existe no rodapé quando o cartão do link deveria estar lá.

    Existe porque MEDI que a Shopee serve og:image pro crawler do WhatsApp —
    então o cartão é possível, e "não vi cartão" pode ser o cartão faltando OU
    o meu seletor errado. Estas duas coisas pedem consertos opostos, e sem o
    despejo eu escolheria por palpite. Foi assim que a figurinha custou seis
    rodadas."""
    try:
        itens = pagina.evaluate(_JS_DESPEJO_PREVIA)
        _log("   — o que tem no rodapé agora (pra achar o cartão) —")
        for i in itens or []:
            partes = [f"<{i['tag']}"]
            for k in ("icone", "testid", "classe"):
                if i.get(k):
                    partes.append(f"{k}={i[k]}")
            partes.append(f"{i['w']}x{i['h']}>")
            if i.get("src"):
                partes.append(f"src={i['src']}")
            if i.get("texto"):
                partes.append(f"txt={i['texto']!r}")
            _log("     " + " ".join(partes))
    except Exception as e:
        _log(f"   (não consegui despejar o rodapé: {str(e)[:60]})")


def _enviar_texto(pagina, texto: str) -> bool:
    """Digita e manda a mensagem. False = não mandei nada (e já avisei).

    Este é o caminho PRINCIPAL desde 19/08 (ver COM_FOTO no topo). A foto do
    produto não vem mais de anexo nosso: vem do cartão de prévia que o próprio
    WhatsApp monta a partir da URL da Shopee.

    Por isso o `sleep` antes do Enter não é folclore de automação — é o tempo
    do WhatsApp ir buscar título/imagem no link. Mandar antes disso publica o
    link pelado, sem cartão, que é o formato que a gente está justamente
    tentando não postar.
    """
    caixa = _achar(pagina, SEL_CAIXA)
    if not caixa:
        caminho = _print_erro(pagina, "não achei a caixa de mensagem")
        _avisar("WhatsApp: a marcação mudou (caixa de mensagem).", caminho)
        return False
    caixa.click()
    # digita linha a linha: Enter manda a mensagem, então quebra de linha
    # tem que ser Shift+Enter
    for n, linha in enumerate(texto.split("\n")):
        if n:
            pagina.keyboard.press("Shift+Enter")
        if linha:
            pagina.keyboard.type(linha, delay=random.randint(25, 70))

    # ⚠️ ESPAÇO DEPOIS DA URL — é o que dispara a busca da prévia (20/08).
    #
    # MEDIDO: a Shopee SERVE og:image pro crawler do WhatsApp, inclusive no
    # link curto (`curl -A "WhatsApp/2.24.1 A" s.shopee.com.br/…` devolve
    # og:title, og:image e og:square_image do produto). Ou seja, o cartão com
    # foto é possível — não é limitação da Shopee, como parecia.
    #
    # O que falta é o WhatsApp RECONHECER que a URL acabou. Ele detecta link
    # por token enquanto você digita, e a nossa URL é a última coisa da
    # mensagem: sem delimitador, o token fica "aberto" e a busca não dispara.
    # O espaço fecha o token. Custa um caractere invisível no fim da mensagem.
    if "http" in texto.rsplit("\n", 1)[-1]:
        pagina.keyboard.type(" ")

    # ⚠️ O TEXTO CAIU MESMO NA CAIXA? Em 20/08 o script disse "✅ enviei 1
    # mensagem" e NADA chegou no grupo. `caixa.click()` + `keyboard.type` é fé:
    # se o clique não deu foco (modal por cima, elemento errado, caixa de
    # busca), as teclas vão pro vazio e ninguém percebe. Ler a caixa de volta
    # custa uma chamada e transforma "achei que digitei" em "digitei".
    escrito = _texto_da_caixa(pagina)
    if not escrito:
        _dump_botoes(pagina, "digitei e a caixa continuou vazia")
        caminho = _print_erro(pagina, "o texto não entrou na caixa")
        _avisar("WhatsApp: digitei e a caixa ficou vazia — o clique não pegou "
                "foco. Nada foi enviado.", caminho)
        return False

    # espera pelo RELÓGIO, não pelo seletor — SEL_PREVIA_LINK é palpite e só
    # entra no log. Se um dia o log mostrar que casa, aí sim vira espera de
    # verdade e o envio fica mais rápido.
    if PREVIA_LINK_SEG > 0:
        # ESPERA ATIVA, não `sleep` cego: sai assim que o cartão aparece (a
        # mensagem vai mais rápido) e só gasta o tempo todo quando ele não vem.
        # Antes era um sleep fixo que nem olhava até o fim.
        limite = time.time() + PREVIA_LINK_SEG
        achou = None
        while time.time() < limite:
            achou = _achar(pagina, SEL_PREVIA_LINK, timeout=600)
            if achou:
                break
            pagina.wait_for_timeout(400)
        if achou:
            _log(f"   prévia do link: cartão apareceu "
                 f"({PREVIA_LINK_SEG - (limite - time.time()):.1f}s)")
        else:
            _log("   prévia do link: não vi cartão")
            # ⚠️ Sem isto, "não vi cartão" é indistinguível de "o seletor está
            # errado" — e eu já queimei seis rodadas nesta tela por confiar em
            # seletor não medido. O despejo é o que transforma o próximo palpite
            # em correção. Só no primeiro item, pra não encher o log.
            if not getattr(_enviar_texto, "_ja_despejou", False):
                _enviar_texto._ja_despejou = True
                _dump_previa(pagina)
    else:
        pagina.wait_for_timeout(random.randint(600, 1400))

    # ⚠️ BOTÃO ANTES DA TECLA — a lição de 19/08, que eu não apliquei aqui.
    # O `_enviar_com_foto` já tinha aprendido isso (commit 47d0963: "era o
    # ENTER, não o formato"), e mesmo assim eu escrevi este caminho usando
    # `keyboard.press("Enter")` porque era mais simples. Deu no mesmo: em
    # 20/08 o log disse "✅ enviei" e o grupo não recebeu nada.
    enviou_por = ""
    for s in ("span[data-icon='send']",
              "button[aria-label*='Enviar' i]",
              "div[role='button'][aria-label*='Enviar' i]",
              "span[data-icon='wds-ic-send-filled']",
              "button[data-testid='send']"):
        try:
            b = pagina.query_selector(s)
            if b and b.is_visible():
                b.click(timeout=5000)
                enviou_por = f"botão ({s})"
                break
        except Exception:
            continue
    if not enviou_por:
        _dump_botoes(pagina, "não achei o botão de enviar")
        pagina.keyboard.press("Enter")
        enviou_por = "Enter (não achei o botão)"
    pagina.wait_for_timeout(2000)

    # ⚠️ A PROVA: A CAIXA ESVAZIOU?
    # Mensagem enviada limpa a caixa. Se o texto ainda está lá, o clique/tecla
    # não mandou nada — e é EXATAMENTE o que aconteceu em 20/08 sem ninguém
    # ficar sabendo, porque a função devolvia True por ter apertado teclas.
    #
    # "Apertei o botão" não é "a mensagem saiu". Toda a sessão foi sobre isso:
    # o selo cuja conta fechava consigo mesma, o filtro de views que não
    # filtrava, o vigia que carimbava vídeo velho. Função que relata sucesso
    # sem evidência é a mesma família.
    for _ in range(10):
        if not _texto_da_caixa(pagina):
            _log(f"   ✔️ mensagem saiu ({enviou_por})")
            return True
        pagina.wait_for_timeout(500)

    caminho = _print_erro(pagina, "a caixa não esvaziou — a mensagem NÃO saiu")
    _avisar(f"WhatsApp: escrevi mas não consegui enviar ({enviou_por}). "
            f"O texto ficou na caixa. Nada chegou no grupo.", caminho)
    return False


def _texto_da_caixa(pagina) -> str:
    """O que está escrito na caixa de mensagem agora. '' quando vazia.

    Serve pra duas perguntas opostas e igualmente importantes: 'o que eu
    digitei entrou?' (antes de enviar) e 'saiu?' (depois). As duas eram fé
    cega até 20/08."""
    for s in SEL_CAIXA:
        try:
            e = pagina.query_selector(s)
            if e and e.is_visible():
                return (e.inner_text() or "").strip()
        except Exception:
            continue
    return ""


def _enviar_com_foto(pagina, foto: Path, legenda: str) -> bool:
    """Anexa a foto e manda com a legenda junto. False se não deu.

    O contrato importa: **False significa que NADA foi enviado**. Se
    devolvesse False depois de já ter mandado alguma coisa, o chamador tentaria
    o texto e o grupo receberia o produto duas vezes.

    Por isso a prévia é esperada antes de digitar. Se ela não aparecer, o
    arquivo pode ter sido anexado mas nada foi enviado — aí eu tiro o print,
    fecho a prévia com Escape e devolvo False pro texto seguir.
    """
    def _pegar_input():
        """O input de FOTOS E VÍDEOS — não o de figurinha.

        ⚠️ A CAUSA REAL DA FIGURINHA (19/08, 4ª tentativa). O menu de anexo do
        WhatsApp novo tem entradas separadas: *Fotos e vídeos*, *Documento*,
        *Figurinha*. Cada uma tem o SEU `input[type=file]`, e todos casam com
        `accept*='image'`. Pegando o primeiro, a gente caía no de FIGURINHA —
        e isso explica os três sintomas de uma vez: o editor era o de sticker
        (por isso 'Contorno', que é recorte de figurinha), figurinha não tem
        campo de legenda, e o envio saía sticker com tecla OU com botão.
        Eu culpei o formato do arquivo e depois a tecla Enter; os dois estavam
        errados porque o arquivo entrava pela porta errada.

        O discriminador é o próprio `accept`: o input de foto aceita VÍDEO
        junto; o de figurinha, não.
        """
        try:
            achados = pagina.evaluate("""
            () => Array.from(document.querySelectorAll("input[type='file']"))
                   .map((e, i) => ({i, accept: e.getAttribute("accept") || ""}))
            """) or []
        except Exception:
            achados = []

        if achados:
            _log(f"   {len(achados)} input(s) de arquivo na página:")
            for a in achados:
                _log(f"     [{a['i']}] accept={a['accept'][:70]!r}")

        # 1) o que aceita vídeo é o de "Fotos e vídeos"
        for a in achados:
            if "video" in a["accept"].lower():
                el = pagina.query_selector_all("input[type='file']")[a["i"]]
                _log(f"     → uso o [{a['i']}] (aceita vídeo = Fotos e vídeos)")
                return el
        # 2) sem nenhum com vídeo, evito ao menos o que só aceita webp/png
        #    (cara de input de figurinha)
        for a in achados:
            acc = a["accept"].lower()
            if "image" in acc and "webp" not in acc:
                el = pagina.query_selector_all("input[type='file']")[a["i"]]
                _log(f"     → uso o [{a['i']}] (imagem, sem cara de figurinha)")
                return el

        for s in SEL_ANEXO:
            try:
                el = pagina.query_selector(s)
            except Exception:
                el = None
            if el:
                _log("     → nenhum distinguível; caí no primeiro que casou "
                     "(pode ser o de FIGURINHA)")
                return el
        return None

    # ⚠️ O CLIQUE NO MENU É PLANO B, NÃO PLANO A — corrigido em 19/08 com o
    # print que o Dre mandou. Eu tinha acabado de escrever que o input só é
    # montado sob demanda; a captura de tela mostra a PRÉVIA ABERTA com a foto,
    # ou seja, `set_input_files` no input direto FUNCIONA. Meu diagnóstico
    # anterior estava errado, e forçar o menu antes só adicionaria um clique
    # que pode abrir painel por cima do fluxo que já funciona.
    # Só abro o menu se o input não estiver lá.
    # ⚠️ ABRIR O MENU SEMPRE, E ESCOLHER "FOTOS E VÍDEOS" (19/08, 5ª volta).
    # O log fechou o caso: a página tem UM input só, `accept='image/*'` — sem
    # vídeo, ou seja, o de FIGURINHA. O input de fotos não está montado; ele
    # só nasce quando se clica na opção "Fotos e vídeos" dentro do menu do
    # `+`. Eu tinha deixado o clique no menu como plano B, e como um input É
    # encontrado (o errado), o menu nunca abria. Plano B que nunca roda é
    # código morto — e aqui era o código que resolvia.
    campo = None
    for s in SEL_BOTAO_ANEXO:
        try:
            b = pagina.query_selector(s)
            if not b or not b.is_visible():
                continue
            b.click(timeout=4000)
            pagina.wait_for_timeout(1200)
            _log(f"   menu de anexo aberto ({s})")
            break
        except Exception:
            continue
    else:
        _dump_botoes(pagina, "não achei o botão '+' de anexo")

    # escolhe a entrada de FOTOS (não Documento, não Figurinha)
    _escolhido = ""
    for rot in ("Fotos e vídeos", "Photos & videos", "Fotos", "Photos",
                "Galeria", "Gallery"):
        try:
            o = pagina.query_selector(f"[role='button']:has-text('{rot}'), "
                                      f"li:has-text('{rot}'), "
                                      f"div[role='menuitem']:has-text('{rot}')")
            if o and o.is_visible():
                o.click(timeout=4000)
                pagina.wait_for_timeout(1200)
                _escolhido = rot
                _log(f"   escolhi '{rot}' no menu de anexo")
                break
        except Exception:
            continue
    if not _escolhido:
        # ⚠️ não sigo calado: sem clicar em "Fotos e vídeos", o input que
        # sobra é o de figurinha, e a foto sai como sticker de novo.
        _dump_botoes(pagina, "menu aberto, mas não achei a opção de FOTOS")

    campo = _pegar_input()
    if not campo:
        _log("   não achei onde anexar arquivo — mando sem foto")
        _dump_botoes(pagina, "nenhum input[type=file] na tela")
        return False

    try:
        campo.set_input_files(str(foto))
    except Exception as e:
        _log(f"   falhei ao anexar ({str(e)[:60]}) — mando sem foto")
        return False

    # ⚠️ ESPERA PELA CAIXA DE LEGENDA, não por uma imagem. Ver o comentário do
    # `SEL_PREVIA`: imagem `blob:` existe em qualquer conversa com foto no
    # histórico, e o teste antigo dava positivo sem prévia aberta.
    # ⚠️ 15s ERA POUCO — medido em 19/08 pelos horários dos dois prints: às
    # 11:20:04 o check disse "nem imagem nem legenda"; às 11:20:43 a captura
    # de tela mostra a prévia montada com a foto. Ela apareceu DEPOIS do meu
    # teto. Eu declarei falha cedo e passei a caçar seletor de um problema que
    # era de tempo. A foto precisa ser lida do disco, processada e renderizada
    # — num VPS sem GPU isso passa de meio minuto.
    _TETO_PREVIA = int(os.environ.get("WHATSAPP_PREVIA_SEG", "60"))
    _js_editor = _JS_EDITOR_ABERTO.replace(
        "ROTULOS", json.dumps(list(_ROTULOS_EDITOR)))
    rotulo_previa = editor = ""
    for seg in range(_TETO_PREVIA):
        try:
            rotulo_previa = pagina.evaluate(_JS_PREVIA_ABERTA) or ""
            # ⚠️ A PRÉVIA PODE NÃO TER CAIXA DE LEGENDA. Medido 19/08: com a
            # prévia montada, o despejo listou 'Cortar e girar', 'Filtrar',
            # 'Desenho' — o editor de imagem — e NENHUM campo de legenda.
            # Eu esperei 60s por uma caixa que o WhatsApp novo não mostra, e
            # reportei "a prévia não abriu" com ela aberta na tela.
            editor = pagina.evaluate(_js_editor) or ""
        except Exception:
            rotulo_previa = editor = ""
        if rotulo_previa or editor:
            break
        # avisa a cada 15s pra não parecer travado num log de cron
        if seg and seg % 15 == 0:
            _log(f"   esperando a prévia montar… ({seg}s de {_TETO_PREVIA})")
        pagina.wait_for_timeout(1000)

    if editor and not rotulo_previa:
        _log(f"   prévia aberta pelo EDITOR ({editor!r}) e SEM caixa de "
             f"legenda — mando a foto e o texto em seguida")
        # ⚠️ ENTER NO EDITOR MANDA FIGURINHA (medido 19/08, três rodadas).
        # Eu culpei o formato do arquivo e converti tudo pra JPEG — e o log
        # provou que estava errado: "foto JPEG normalizada pra JPEG" e a
        # imagem saiu como sticker do mesmo jeito. O formato nunca foi o
        # problema. O editor tem a ferramenta **Contorno** (recorte de
        # figurinha), e o `Enter` dentro dele confirma ESSA ação.
        # O botão de enviar manda foto; a tecla manda o que o editor estiver
        # fazendo. São coisas diferentes.
        _enviou = False
        for s in ("span[data-icon='send']",
                  "button[aria-label*='Enviar' i]",
                  "div[role='button'][aria-label*='Enviar' i]",
                  "span[data-icon='wds-ic-send-filled']",
                  "button[data-testid='send']"):
            try:
                b = pagina.query_selector(s)
                if b and b.is_visible():
                    b.click(timeout=5000)
                    _log(f"   foto enviada pelo BOTÃO ({s})")
                    _enviou = True
                    break
            except Exception:
                continue
        if not _enviou:
            _dump_botoes(pagina, "não achei o botão de enviar da prévia")
            _log("   ⚠️ caindo no Enter — pode sair como FIGURINHA")
        try:
            if not _enviou:
                pagina.keyboard.press("Enter")   # último recurso
            pagina.wait_for_timeout(2000)
        except Exception as e:
            _print_erro(pagina, f"não consegui enviar a foto: {str(e)[:60]}")
            _sair_da_previa(pagina)
            return False

        # ⚠️ ESPERAR A PRÉVIA FECHAR ANTES DE DEVOLVER. Quem chama, ao receber
        # False, só manda o texto se a prévia já saiu (`daemon` do envio:
        # "se a prévia não fechou, digitar aqui escreveria a legenda DENTRO
        # dela"). Se eu devolvesse com ela ainda na tela, o item seria PULADO
        # e a foto ficaria no grupo sem preço e sem link — achadinho mudo, que
        # é pior que não ter postado.
        for _ in range(20):
            try:
                if not (pagina.evaluate(_js_editor) or ""):
                    break
            except Exception:
                break
            pagina.wait_for_timeout(500)
        else:
            _print_erro(pagina, "enviei a foto mas o editor não fechou")
            _log("   ⚠️ a legenda NÃO foi enviada — a foto está no grupo "
                 "sozinha. Mande o texto à mão ou apague a foto.")
            return False
        # ⚠️ devolve False DE PROPÓSITO: o contrato desta função é "True = foto
        # E legenda foram juntas". A foto saiu, mas o texto ainda não — quem
        # chama manda o texto em seguida, e é assim que a legenda não se perde.
        # Mentir True aqui deixaria o achadinho sem preço e sem link.
        _log("   foto enviada; a legenda vai como mensagem seguinte")
        return False

    if not rotulo_previa:
        # o `SEL_PREVIA` ainda serve pra dizer se ao menos a IMAGEM apareceu —
        # separa "o anexo não pegou" de "pegou mas a tela é outra"
        viu_imagem = bool(_achar(pagina, SEL_PREVIA, timeout=1500))
        _print_erro(pagina, "anexei a foto mas a prévia não abriu"
                    + (" (achei a imagem, mas nenhuma caixa de legenda — a "
                       "tela mudou de formato)" if viu_imagem else
                       " (nem imagem nem legenda: o `set_input_files` não "
                       "chegou a disparar a prévia)"))
        if not viu_imagem:
            _dump_botoes(pagina, "o menu de anexo provavelmente não abriu")
        try:
            pagina.keyboard.press("Escape")
            pagina.wait_for_timeout(800)
        except Exception:
            pass
        return False
    _log(f"   prévia aberta (campo de legenda: {rotulo_previa!r})")

    pagina.wait_for_timeout(1200)
    if not _focar_legenda(pagina):
        _print_erro(pagina, "prévia aberta mas não consegui focar a legenda")
        _sair_da_previa(pagina)
        return False

    try:
        for n, linha in enumerate(legenda.split("\n")):
            if n:
                pagina.keyboard.press("Shift+Enter")
            if linha:
                pagina.keyboard.type(linha, delay=random.randint(20, 55))
        pagina.wait_for_timeout(random.randint(700, 1500))
        pagina.keyboard.press("Enter")
        pagina.wait_for_timeout(2500)
        return True
    except Exception as e:
        # digitou parte da legenda mas não mandou: a prévia continua aberta e
        # nada foi enviado. Escape descarta, e o texto segue como plano B.
        _print_erro(pagina, f"falhei ao digitar a legenda: {str(e)[:70]}")
        _sair_da_previa(pagina)
        return False


def _abrir(pw, headless=True):
    """Contexto PERSISTENTE: a sessão do WhatsApp precisa sobreviver entre
    rodadas, senão seria um QR novo toda vez (e escanear QR toda hora é
    justamente o padrão que faz o WhatsApp desconfiar)."""
    SESSAO.mkdir(parents=True, exist_ok=True)
    exe = os.environ.get("CHROMIUM_PATH") or None
    return pw.chromium.launch_persistent_context(
        user_data_dir=str(SESSAO),
        headless=headless,
        executable_path=exe,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
              "--disable-dev-shm-usage"],
        user_agent=_UA, locale="pt-BR", timezone_id="America/Sao_Paulo",
        viewport={"width": 1280, "height": 860})


_DIAG_JS = """
() => {
  const lista = [];
  const desc = (el) => {
    const a = {};
    for (const at of el.attributes) {
      if (["class","style"].includes(at.name)) continue;
      a[at.name] = (at.value || "").slice(0, 60);
    }
    return {tag: el.tagName.toLowerCase(), attrs: a,
            texto: (el.innerText || "").trim().slice(0, 40),
            visivel: !!(el.offsetWidth || el.offsetHeight)};
  };
  for (const el of document.querySelectorAll('[contenteditable="true"]'))
    lista.push({grupo: "contenteditable", ...desc(el)});
  for (const el of document.querySelectorAll('[role="textbox"]'))
    lista.push({grupo: "role=textbox", ...desc(el)});
  // input/textarea entram inteiros: se a busca virou <input> sem aria-label,
  // filtrar por "pesquisa" a esconderia — e o ponto do diag é NÃO esconder.
  for (const el of document.querySelectorAll('input, textarea'))
    lista.push({grupo: "input/textarea", ...desc(el)});
  for (const el of document.querySelectorAll('[placeholder]'))
    lista.push({grupo: "placeholder", ...desc(el)});
  for (const el of document.querySelectorAll('[aria-label]')) {
    const L = (el.getAttribute("aria-label") || "").toLowerCase();
    if (L.includes("pesquis") || L.includes("search") || L.includes("busca"))
      lista.push({grupo: "aria-label busca", ...desc(el)});
  }
  // e os títulos do painel lateral: é por eles que o grupo é encontrado
  for (const el of document.querySelectorAll('span[title]')) {
    const t = el.getAttribute("title") || "";
    if (t.length > 1 && t.length < 70) lista.push({grupo: "span[title]", ...desc(el)});
  }
  const vistos = new Set();
  return lista.filter(a => {
    const k = a.grupo + JSON.stringify(a.attrs);
    if (vistos.has(k)) return false;
    vistos.add(k); return true;
  }).slice(0, 120);
}
"""


def diag_anexo():
    """Abre o menu de anexo no grupo e mostra o que aparece. NÃO ENVIA NADA.

    ⚠️ POR QUE EXISTE (19/08). O teto diário (6) bateu no meio do conserto da
    figurinha, e eu precisava saber se o clique em "Fotos e vídeos" resolveu —
    sem esperar até amanhã e sem gastar mensagem no grupo testando. O que está
    em dúvida (menu → opção → input certo) acontece ANTES de enviar, então dá
    pra verificar sem enviar.

    Também não incrementa o contador do dia nem entra na janela de horário:
    ele não posta, então as travas que existem pra não parecer robô não se
    aplicam. Roda quantas vezes quiser.
    """
    from playwright.sync_api import sync_playwright
    grupo = _grupo()
    if not grupo:
        _log("defina WHATSAPP_GRUPO no .env")
        return 2
    with sync_playwright() as pw:
        # mesma abertura do `diagnostico()`: `_abrir` devolve o CONTEXTO
        # persistente, não uma tupla. Eu tinha escrito `nav, pagina = _abrir(...)`
        # sem conferir a assinatura, e quebrou na primeira execução.
        ctx = _abrir(pw)
        pagina = ctx.pages[0] if ctx.pages else ctx.new_page()
        ctx.add_init_script(_STEALTH_JS)
        try:
            pagina.goto("https://web.whatsapp.com", timeout=60000)
            pagina.wait_for_timeout(6000)
            if not _achar(pagina, SEL_LOGADO, timeout=45000):
                _log("não estou logado — rode --login")
                return 1
            _fechar_modal(pagina)
            if not _abrir_grupo(pagina, grupo):
                _log(f"não achei o grupo '{grupo}'")
                return 1

            print()
            _log("=== ANTES de abrir o menu ===")
            antes = pagina.evaluate("""
            () => Array.from(document.querySelectorAll("input[type='file']"))
                   .map((e,i)=>({i, accept: e.getAttribute("accept")||""}))""")
            for a in antes or []:
                _log(f"   input[{a['i']}] accept={a['accept'][:70]!r}")
            if not antes:
                _log("   (nenhum input de arquivo)")

            aberto = ""
            for s in SEL_BOTAO_ANEXO:
                try:
                    b = pagina.query_selector(s)
                    if b and b.is_visible():
                        b.click(timeout=4000)
                        pagina.wait_for_timeout(1500)
                        aberto = s
                        break
                except Exception:
                    continue
            print()
            _log(f"=== DEPOIS de clicar no anexo ({aberto or 'NÃO ACHEI O +'}) ===")
            if not aberto:
                _dump_botoes(pagina, "procurando o botão '+'")
                return 1

            depois = pagina.evaluate("""
            () => Array.from(document.querySelectorAll("input[type='file']"))
                   .map((e,i)=>({i, accept: e.getAttribute("accept")||""}))""")
            for a in depois or []:
                marca = "  ← ACEITA VÍDEO (é o de fotos)" if "video" in a["accept"].lower() else ""
                _log(f"   input[{a['i']}] accept={a['accept'][:70]!r}{marca}")

            _log("   opções visíveis no menu:")
            _dump_botoes(pagina, "menu de anexo aberto")

            # tenta a opção de fotos e mostra o efeito
            for rot in ("Fotos e vídeos", "Photos & videos", "Fotos", "Photos"):
                try:
                    o = pagina.query_selector(
                        f"[role='button']:has-text('{rot}'), "
                        f"li:has-text('{rot}'), "
                        f"div[role='menuitem']:has-text('{rot}')")
                    if o and o.is_visible():
                        o.click(timeout=4000)
                        pagina.wait_for_timeout(1500)
                        print()
                        _log(f"=== DEPOIS de clicar em '{rot}' ===")
                        fim = pagina.evaluate("""
                        () => Array.from(document.querySelectorAll("input[type='file']"))
                               .map((e,i)=>({i, accept: e.getAttribute("accept")||""}))""")
                        for a in fim or []:
                            marca = ("  ← ESTE" if "video" in a["accept"].lower()
                                     else "")
                            _log(f"   input[{a['i']}] "
                                 f"accept={a['accept'][:70]!r}{marca}")
                        break
                except Exception:
                    continue
            else:
                _log("   ⚠️ não achei a opção de FOTOS no menu (veja a lista "
                     "acima e me diga o rótulo certo)")

            pagina.keyboard.press("Escape")
            print()
            _log("NADA foi enviado. Este modo só olha.")
            return 0
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def diagnostico():
    """Mostra o que a página REALMENTE tem, em vez de eu chutar seletor.

    O WhatsApp Web troca a marcação sem aviso e sem versão. Quando o --teste
    diz "não achei a caixa de busca", a resposta certa não é tentar outro
    seletor no escuro: é olhar. Isto imprime todo campo editável, todo
    role=textbox e todo aria-label de busca, com os atributos — é o que
    permite escolher um seletor que exista de verdade.
    """
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = _abrir(pw)
        pagina = ctx.pages[0] if ctx.pages else ctx.new_page()
        ctx.add_init_script(_STEALTH_JS)
        try:
            pagina.goto("https://web.whatsapp.com", timeout=60000)
            if not _achar(pagina, SEL_LOGADO, timeout=25000):
                _print_erro(pagina, "não está logado — rode --login primeiro")
                return 1
            _log("logado. deixando a interface assentar (6s)...")
            pagina.wait_for_timeout(6000)
            _fechar_modal(pagina)

            achados = pagina.evaluate(_DIAG_JS)
            _log(f"{len(achados)} elemento(s) candidatos:\n")
            for a in achados:
                marca = "  " if a.get("visivel") else "(oculto) "
                print(f"{marca}[{a['grupo']}] <{a['tag']}>")
                for k, v in a["attrs"].items():
                    print(f"      {k}={v!r}")
                if a.get("texto"):
                    print(f"      texto: {a['texto']!r}")
                print()

            caminho = _print_erro(pagina, "print do estado atual (não é erro)")
            _avisar("WhatsApp --diag: print da tela pra escolher os seletores.",
                    caminho)
            return 0
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def login():
    """Primeira vez: tira print do QR e manda pro Telegram pra escanear."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = _abrir(pw)
        pagina = ctx.pages[0] if ctx.pages else ctx.new_page()
        ctx.add_init_script(_STEALTH_JS)
        pagina.goto("https://web.whatsapp.com", timeout=60000)
        if _achar(pagina, SEL_LOGADO, timeout=12000):
            _log("já está logado — a sessão anterior continua válida ✔")
            ctx.close()
            return 0
        if not _achar(pagina, SEL_QR, timeout=30000):
            _print_erro(pagina, "não achei o QR nem a lista de conversas")
            ctx.close()
            return 1
        ERROS.mkdir(parents=True, exist_ok=True)
        qr = ERROS / "qr_login.png"
        pagina.screenshot(path=str(qr))
        _avisar("QR do WhatsApp Web — escaneie do celular em até 1 minuto.\n"
                "WhatsApp → Aparelhos conectados → Conectar aparelho.", qr)
        _log("QR enviado pro Telegram. Aguardando você escanear (até 2 min)...")
        for _ in range(24):
            time.sleep(5)
            if _achar(pagina, SEL_LOGADO, timeout=3000):
                _log("✅ conectado. A sessão fica salva em shared/whatsapp_sessao/")
                try:
                    qr.unlink()
                except Exception:
                    pass
                ctx.close()
                return 0
        _print_erro(pagina, "tempo esgotado esperando o QR ser escaneado")
        ctx.close()
        return 1


def enviar(quantos: int, teste: bool = False) -> int:
    from playwright.sync_api import sync_playwright

    grupo = _grupo()
    if not grupo:
        _log("WHATSAPP_GRUPO vazio no .env — preciso do NOME EXATO do grupo")
        return 2

    fila = _carregar_json(FILA, [])
    if not isinstance(fila, list) or not fila:
        _log("fila vazia — nada a enviar")
        return 1

    estado = _carregar_json(ESTADO, {})
    if not isinstance(estado, dict):
        estado = {}
    ja = set(estado.get("links", []))

    resta_dia = MAX_DIA - _enviados_hoje(estado)
    if resta_dia <= 0:
        _log(f"teto do dia atingido ({MAX_DIA}) — paro por hoje")
        return 0
    alvo = _candidatos(fila, ja, quantos, resta_dia)
    if not alvo:
        _log("nenhum achadinho novo (todos já foram) ✔")
        return 0
    _log(f"envio {len(alvo)} nesta rodada (teto rodada {quantos}, "
         f"resta hoje {resta_dia})")

    with sync_playwright() as pw:
        ctx = _abrir(pw)
        pagina = ctx.pages[0] if ctx.pages else ctx.new_page()
        ctx.add_init_script(_STEALTH_JS)
        try:
            pagina.goto("https://web.whatsapp.com", timeout=60000)
            if not _achar(pagina, SEL_LOGADO, timeout=25000):
                caminho = _print_erro(pagina, "sessão caída — precisa logar de novo")
                _avisar("WhatsApp: a sessão caiu. Rode:\n"
                        "  .venv/bin/python whatsapp_playwright.py --login", caminho)
                return 1

            # a lista de conversas aparece antes da busca ficar utilizável;
            # sem esta espera o seletor falha por a interface ainda montar
            pagina.wait_for_timeout(4000)
            _fechar_modal(pagina)  # o "Novidades do WhatsApp Web" cobre a busca
            aberto = _abrir_grupo(pagina, grupo)
            if aberto is None:
                caminho = _print_erro(pagina, "não achei a caixa de busca")
                _avisar("WhatsApp: não achei a busca NEM o grupo na lista. "
                        "Rode --diag pra ver os campos da página.", caminho)
                return 1
            if not aberto:
                caminho = _print_erro(pagina, f"grupo '{grupo}' não apareceu na busca")
                _avisar(f"WhatsApp: não achei o grupo '{grupo}'. "
                        "Confira o NOME EXATO em WHATSAPP_GRUPO no .env.", caminho)
                return 1

            enviados = 0
            for i, it in enumerate(alvo):
                texto = _mensagem(it)
                if teste:
                    _log(f"   [seco] mandaria {'COM foto' if COM_FOTO else 'SÓ LINK'}:"
                         f"\n{texto}\n")
                    enviados += 1
                    continue

                foi = False
                if COM_FOTO:
                    # caminho antigo, desligado por padrão (ver COM_FOTO no topo).
                    # Se a foto falhar em qualquer etapa, cai no texto — que
                    # ainda vende.
                    foto = _baixar_foto(it.get("imagem", ""))
                    if foto:
                        foi = _enviar_com_foto(pagina, foto, texto)
                        try:
                            foto.unlink()
                        except Exception:
                            pass

                if not foi:
                    # se a prévia de imagem não fechou, digitar aqui escreveria
                    # a legenda DENTRO dela — melhor pular este item que postar
                    # torto. Com COM_FOTO=0 nunca há prévia, mas a checagem é
                    # barata e protege quem religar a foto.
                    if COM_FOTO and _achar(pagina, SEL_PREVIA, timeout=2500):
                        _print_erro(pagina, "a prévia não fechou — pulo este item")
                        break
                    if not _enviar_texto(pagina, texto):
                        break

                enviados += 1
                ja.add(it["link"])
                estado["links"] = list(ja)
                estado.setdefault("por_dia", {})
                hoje = str(date.today())
                estado["por_dia"][hoje] = estado["por_dia"].get(hoje, 0) + 1
                _salvar_estado(estado)
                _log(f"   ✅ {(it.get('campeao') or it.get('produto', ''))[:44]}")

                if i < len(alvo) - 1:
                    espera = random.uniform(PAUSA_MIN, PAUSA_MAX)
                    _log(f"   (aguardando {espera:.0f}s)")
                    time.sleep(espera)

            _log(f"{'simularia' if teste else 'enviei'} {enviados} mensagem(ns).")
            return 0
        except Exception as e:
            caminho = _print_erro(pagina, f"erro inesperado: {str(e)[:90]}")
            _avisar(f"WhatsApp parou: {str(e)[:200]}", caminho)
            return 1
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def main():
    p = argparse.ArgumentParser(description="Posta achadinho no grupo do WhatsApp.")
    p.add_argument("--login", action="store_true", help="conecta pelo QR (1ª vez)")
    p.add_argument("--diag", action="store_true",
                   help="mostra os campos que a página tem (pra corrigir seletor)")
    p.add_argument("--teste", action="store_true", help="acha o grupo e mostra, sem enviar")
    p.add_argument("--diag-anexo", dest="diag_anexo", action="store_true",
                   help="abre o menu de anexo e mostra os inputs, SEM enviar")
    p.add_argument("--forcar", action="store_true", help="ignora a janela de horário")
    p.add_argument("--quantos", type=int, default=MAX_RODADA)
    args = p.parse_args()

    # As travas de configuração vêm ANTES do playwright: erro de .env é o caso
    # comum, e ouvir "playwright não instalado" quando o problema é
    # WHATSAPP_GRUPO vazio manda a pessoa procurar no lugar errado.
    if (not args.login and not args.diag and not args.diag_anexo
            and not _ligado() and not args.teste):
        _log("⚪ WHATSAPP_ATIVO desligado. Ligue com:")
        _log("     echo 'WHATSAPP_ATIVO=1' >> ~/jarvis/.env")
        _log("   (rode com --teste pra simular sem enviar)")
        return 0

    if (not args.login and not args.diag and not args.diag_anexo
            and not args.forcar and not _dentro_da_janela()):
        _log(f"fora da janela ({HORA_INI:02d}:00–{HORA_FIM:02d}:59) — nada enviado.")
        return 0

    if not args.login and not args.diag and not _grupo():
        _log("WHATSAPP_GRUPO vazio no .env — preciso do NOME EXATO do grupo.")
        _log("   echo 'WHATSAPP_GRUPO=Nome Exato Do Grupo' >> ~/jarvis/.env")
        return 2

    try:
        import playwright  # noqa: F401
    except Exception:
        _log("playwright não instalado no ambiente atual.")
        _log("use o venv:  .venv/bin/python whatsapp_playwright.py ...")
        return 2

    # a trava vale pra TUDO que abre navegador, não só pro envio: duas sessões
    # do Chromium no mesmo user_data_dir corrompem o perfil, e perfil corrompido
    # aqui significa escanear o QR de novo — o padrão que faz o WhatsApp
    # desconfiar da conta.
    with travar("whatsapp_playwright") as livre:
        if not livre:
            _log("outra instância já está com o navegador — saio sem fazer nada ✔")
            return 0
        if args.login:
            return login()
        if args.diag:
            return diagnostico()
        if args.diag_anexo:
            return diag_anexo()
        return enviar(max(1, min(args.quantos, MAX_RODADA)), teste=args.teste)


if __name__ == "__main__":
    sys.exit(main())
