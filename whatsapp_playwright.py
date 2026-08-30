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

# ⚠️ SEM ISTO, "AINDA CARREGANDO" ERA REPORTADO COMO "SESSÃO CAÍDA" (30/08).
# O ciclo só perguntava "a lista de conversas apareceu em 25s?" e, no não,
# gritava "a sessão caiu, rode --login". O print que ele mesmo tira provou o
# contrário: splash do WhatsApp com a BARRA DE PROGRESSO no meio — sessão viva,
# sincronizando. Se estivesse deslogado o print teria QR.
#
# 📌 Timeout não é diagnóstico. "Não achei em 25s" tem pelo menos três causas
# (deslogado / carregando / marcação mudou) e o código escolhia sempre a mais
# assustadora — a única que manda o dono escanear QR à toa, que é justamente o
# comportamento que faz o WhatsApp desconfiar da conta.
#
# A sincronização demora MAIS depois de mexer nas conversas (apagar tudo, criar
# grupo) — exatamente o que tinha acabado de acontecer.
SEL_CARREGANDO = ["[role='progressbar']", "progress",
                  "div[data-testid='startup-progressbar']"]

# ⚠️ SEM O `canvas` PELADO do SEL_QR: aqui a pergunta é "existe QR?", e um
# canvas qualquer na tela de carregamento responderia que sim, trocando
# "carregando" por "deslogado" e desfazendo a correção acima.
SEL_QR_ESTRITO = ["canvas[aria-label*='scan' i]", "div[data-ref] canvas"]

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
# ⚠️ MEDIDO NO DESPEJO DE 20/08, com o menu aberto. Não é mais palpite: são os
# botões que o menu tem, na ordem, todos com aria-label E texto —
#   Documento · Fotos e vídeos · Câmera · Áudio · Contato · Enquete · Evento ·
#   Nova figurinha · Catálogo · Resposta rápida
# "Nova figurinha" era o `input[type=file][accept='image/*']` solitário que
# aparecia antes de qualquer clique. A figurinha de seis rodadas tinha esse
# nome no menu o tempo todo, a duas linhas de 'Fotos e vídeos'.
ROTULOS_FOTOS = ("Fotos e vídeos", "Fotos e videos", "Photos & videos",
                 "Photos and videos", "Fotos", "Photos")

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
  let semRotulo = null;
  for (const e of document.querySelectorAll(sel)) {
    if (e.offsetParent === null) continue;
    const tab = e.getAttribute("data-tab") || "";
    // data-tab 3 = busca · 10/6 = caixa da conversa. Nenhum dos dois é legenda.
    if (tab === "3" || tab === "10" || tab === "6") continue;
    const rot = ((e.getAttribute("aria-label") || "") + " " +
                 (e.getAttribute("aria-placeholder") || "") + " " +
                 (e.getAttribute("placeholder") || "")).toLowerCase();
    if (rot) {
      if (rot.includes("pesquis") || rot.includes("search")) continue;
      // ⚠️ NÃO EXCLUIR POR "digite uma mensagem" — MEDIDO EM 20/08.
      // Eu excluía esse rótulo pra pular a caixa da conversa. Só que a caixa
      // de LEGENDA tem o MESMO rótulo:
      //
      //   <div data-tab='undefined' rótulo='Digite uma mensagem'      y=713 ← legenda
      //   <div data-tab='10'        rótulo='Digite uma mensagem p/…'  y=811 ← conversa
      //
      // Então a minha exclusão matava exatamente o campo que eu procurava, e
      // a foto saía separada do texto. O discriminador é o `data-tab`, já
      // tratado acima — o rótulo aqui só descreve, não decide.
      return rot.slice(0, 60);   // campo que só existe na prévia
    }
    // ⚠️ CAMPO SEM RÓTULO TAMBÉM CONTA (20/08). A versão anterior fazia
    // `if (!rot) continue` e descartava qualquer campo sem aria-label —
    // exatamente o erro que escondeu o menu de anexo por três rodadas: exigir
    // um atributo que o elemento não tem. O log provou aqui também: o editor
    // ABRIU ('cortar e girar') e a legenda foi dada como inexistente, então a
    // foto e o texto saíram como duas mensagens.
    //
    // Com o editor aberto, um contenteditable visível que NÃO é a busca nem a
    // caixa da conversa só pode ser a legenda. Guardo como 2ª opção pra um
    // campo rotulado ainda ter preferência.
    if (!semRotulo) semRotulo = "(campo sem rótulo, data-tab=" + (tab || "-") + ")";
  }
  return semRotulo || "";
}
"""

# Despejo dos campos de texto da tela — pra corrigir COM DADO quando a
# detecção da legenda falhar, em vez de eu inventar o próximo seletor.
_JS_CAMPOS = """
() => {
  const sel = "[contenteditable='true'],input,textarea,[role='textbox']";
  return Array.from(document.querySelectorAll(sel))
    .filter(e => e.offsetParent !== null)
    .slice(0, 20)
    .map(e => {
      const r = e.getBoundingClientRect();
      return {
        tag: e.tagName.toLowerCase(),
        tab: e.getAttribute("data-tab") || "",
        rotulo: (e.getAttribute("aria-label") || ""),
        dica: (e.getAttribute("aria-placeholder") ||
               e.getAttribute("placeholder") || ""),
        y: Math.round(r.top), alt: Math.round(r.height),
      };
    });
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

# ⚠️ ATÉ 30/08 UM ACHADINHO ERA QUEIMADO PARA SEMPRE. `estado["links"]` era uma
# lista sem data, e `_candidatos` cortava tudo que estivesse nela — então cada
# produto valia UM envio na vida inteira do grupo. Com um grupo pequeno isso
# passava despercebido; virou teto duro quando a pergunta passou a ser "72 por
# dia". A conta que denunciou: a esteira repõe ~11 bons/dia, e sem repost esses
# 11 são o máximo absoluto de conteúdo diário, com qualquer catálogo.
#
# 21 dias é o intervalo em que o grupo já rodou membros novos suficientes e
# quem viu não lembra. WHATSAPP_REPOST_DIAS=0 volta o comportamento antigo
# (nunca repete), pra quem quiser.
#
# 📌 A migração CARIMBA os links antigos com a data de hoje, de propósito. Ler
# a lista antiga como "sem data = pode repetir" liberaria centenas de produtos
# de uma vez na primeira rodada depois do deploy — o grupo levaria uma enxurrada
# de repetição e a culpa pareceria do WhatsApp. Carimbado, nada repete nos
# primeiros 21 dias e o recurso entra sozinho, no ritmo certo.
REPOST_DIAS = int(float(os.environ.get("WHATSAPP_REPOST_DIAS", "21")))

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


def _grupos() -> list:
    """Todos os grupos que recebem o achadinho. Nomes EXATOS, separados por `;`.

    ⚠️ NASCEU DA ESTRATÉGIA DE LOTAR VÁRIOS GRUPOS (29/08). Grupo do WhatsApp
    para em ~1024 membros; passar disso exige grupo novo, e o Dre quer encher
    quantos couberem. Cada achadinho vai pra TODOS — são audiências separadas,
    não uma lista fatiada.

    ⚠️ SEPARADOR É `;`, NÃO VÍRGULA. Nome de grupo de achadinho leva vírgula com
    frequência ("Achadinhos, Ofertas e Cupons") e o split silencioso partiria o
    nome em dois grupos que não existem — o script procuraria, não acharia,
    tiraria print e pararia. Erro de configuração que se disfarça de erro de
    interface é o pior de diagnosticar.

    Aceita `WHATSAPP_GRUPO` (singular) como está hoje, pra não quebrar o .env
    de quem já roda com um grupo só."""
    bruto = (os.environ.get("WHATSAPP_GRUPOS", "") or "").strip()
    if bruto:
        nomes = [g.strip() for g in bruto.split(";") if g.strip()]
        # nomes repetidos mandariam a mesma mensagem duas vezes pro mesmo lugar
        vistos, saida = set(), []
        for n in nomes:
            if n.lower() not in vistos:
                vistos.add(n.lower())
                saida.append(n)
        return saida
    um = _grupo()
    return [um] if um else []


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


def _enviados_em(estado: dict) -> dict:
    """{link: quando foi ao ar pela última vez}, em epoch.

    Migra o formato antigo — `links`, uma lista pelada — carimbando com AGORA.
    Ver o comentário de REPOST_DIAS: carimbar com agora é o que impede a
    enxurrada de repetição na primeira rodada depois do deploy."""
    mapa = estado.get("enviados_em")
    if not isinstance(mapa, dict):
        mapa = {}
    sem_data = [l for l in (estado.get("links") or []) if l and l not in mapa]
    if sem_data:
        agora = int(time.time())
        for l in sem_data:
            mapa[l] = agora
        estado["enviados_em"] = mapa
        _salvar_estado(estado)
        _log(f"🗓️  {len(sem_data)} link(s) antigo(s) sem data — carimbados com "
             f"hoje; voltam a ficar livres em {REPOST_DIAS} dia(s)")
    return mapa


def _bloqueados(estado: dict) -> set:
    """Os links que NÃO podem ir ao ar agora.

    ⚠️ Isto substituiu `set(estado["links"])`, e a diferença é o tempo: antes a
    resposta era "já foi alguma vez", agora é "foi RECENTE". Com REPOST_DIAS=0
    as duas voltam a ser a mesma coisa."""
    mapa = _enviados_em(estado)
    if REPOST_DIAS <= 0:
        return set(mapa)
    limite = time.time() - REPOST_DIAS * 86400
    return {l for l, ts in mapa.items() if float(ts or 0) >= limite}


def _dentro_da_janela() -> bool:
    return HORA_INI <= datetime.now().hour <= HORA_FIM


# ══════════════════════════════════════════════════════════════════════════
# HORÁRIOS SORTEADOS — o pedido do Dre (24/08): "os horários estão sempre
# fixos, queria que fosse mais aleatório"
#
# ⚠️ E O DEFEITO NÃO ESTAVA NESTE ARQUIVO. Ele nunca soube QUANDO rodar: só
# checava a janela (07–21h) e os tetos. Quem escolhia a hora era o **cron da
# VPS**, e cron é fixo por definição — `0 9,13,18 * * *` manda exatamente às
# 9:00:00, 13:00:00 e 18:00:00, todo santo dia, no segundo.
#
# ⚠️ ISSO É EXATAMENTE O "PADRÃO DE ROBÔ" QUE O CABEÇALHO DESTE ARQUIVO DIZ SER
# O QUE DERRUBA NÚMERO — mais até que o volume. Pessoa nenhuma manda mensagem
# no mesmo minuto todo dia; sistema antifraude não precisa de IA pra ver isso,
# só de um `GROUP BY minuto`.
#
# O conserto NÃO é "cron aleatório" (cron não sorteia). É inverter quem manda:
# o cron passa a acordar de 15 em 15 minutos e PERGUNTA se está na hora; quem
# responde é aqui, com uma agenda sorteada UMA VEZ POR DIA e guardada no
# estado. Mesmo desenho do `carrossel_agendador`, e pelo mesmo motivo.
GAP_MIN = int(float(os.environ.get("WHATSAPP_GAP_MIN", "35")))    # minutos
TOLERANCIA = int(float(os.environ.get("WHATSAPP_TOLERANCIA", "16")))
# ⚠️ DE QUANTO EM QUANTO O CRON ACORDA. Não é enfeite: é o que define o ÚLTIMO
# minuto sorteável da janela. Com `*/15 7-21` a última acordada é 21:45, então
# um slot sorteado às 21:52 NÃO SERIA ALCANÇADO POR NINGUÉM — e o dia acabaria
# com 11 mensagens em vez de 12, todo dia em que a última faixa caísse ali, sem
# erro nenhum no log. Achei simulando as acordadas contra a janela, não rodando.
# Se mudar o `*/15` no crontab, mude aqui junto.
CRON_MIN = int(float(os.environ.get("WHATSAPP_CRON_MIN", "15")))


def _agenda_do_dia(estado: dict) -> list:
    """Os horários de hoje, em minutos desde 00:00. Sorteia na 1ª chamada.

    ⚠️ SORTEADA UMA VEZ E GUARDADA, não sorteada a cada acordada. Se cada
    execução tirasse um dado novo, dois horários poderiam cair colados ou o dia
    inteiro passar sem nenhum — e o teto por dia deixaria de significar
    qualquer coisa. Guardando, a agenda é um FATO do dia: dá pra ver de manhã
    o que vai sair, e o log consegue dizer 'faltam 3'."""
    hoje = str(date.today())
    ag = estado.get("agenda") or {}
    if ag.get("dia") == hoje and ag.get("horarios"):
        return list(ag["horarios"])

    # o teto da janela recua até o último minuto que o cron ainda alcança
    ini = HORA_INI * 60
    fim = HORA_FIM * 60 + max(0, 59 - CRON_MIN)
    alvo = max(1, MAX_DIA)
    # ⚠️ O GAP É O QUE FAZ A ALEATORIEDADE PARECER HUMANA. Sorteio puro num
    # intervalo de 15h com 12 pontos junta dois deles a 3 minutos de distância
    # com frequência alta — e duas mensagens coladas chamam mais atenção que
    # horário fixo. Sorteio um ponto por FAIXA e jitter dentro dela.
    largura = (fim - ini) / alvo
    horarios, ultimo = [], -10 ** 9
    for i in range(alvo):
        a = ini + largura * i
        b = a + largura
        # a faixa encolhe pelas pontas pra não colar na faixa vizinha
        margem = min(largura * 0.18, 12)
        t = int(random.uniform(a + margem, b - margem))
        if t - ultimo < GAP_MIN:
            t = ultimo + GAP_MIN
        if t > fim:
            break
        horarios.append(t)
        ultimo = t

    estado["agenda"] = {"dia": hoje, "horarios": horarios}
    _salvar_estado(estado)
    _log("🎲 agenda de hoje: "
         + " · ".join(f"{t // 60:02d}:{t % 60:02d}" for t in horarios))
    return horarios


def _slot_devido(estado: dict):
    """O horário de hoje que já passou, ainda não foi usado e está na
    tolerância. Devolve None quando não é hora."""
    agora = datetime.now()
    agora_min = agora.hour * 60 + agora.minute
    feitos = set((estado.get("agenda") or {}).get("feitos") or [])
    for t in _agenda_do_dia(estado):
        if t in feitos:
            continue
        # ⚠️ JANELA DE TOLERÂNCIA, não igualdade. O cron acorda de 15 em 15 e
        # nunca vai cair no minuto exato do sorteio; sem folga, TODO slot seria
        # pulado e o WhatsApp nunca mandaria nada. É a mesma tolerância do
        # agendador de carrossel, pelo mesmo motivo.
        if 0 <= (agora_min - t) <= TOLERANCIA:
            return t
    return None


def _marcar_slot(estado: dict, t: int) -> None:
    ag = estado.setdefault("agenda", {})
    ag.setdefault("feitos", [])
    if t not in ag["feitos"]:
        ag["feitos"].append(t)
    _salvar_estado(estado)


def _enviados_hoje(estado: dict) -> int:
    """Quantos ACHADINHOS já saíram hoje — não quantas mensagens.

    ⚠️ ERAM A MESMA COISA ATÉ EXISTIR MAIS DE UM GRUPO (29/08). Com um grupo
    só, 1 achadinho = 1 mensagem e ninguém precisava distinguir. Com cinco
    grupos, o mesmo achadinho vira 5 mensagens — e se o teto continuasse
    contando mensagens, `MAX_DIA=6` passaria a significar **um achadinho por
    dia**, matando a cadência de conteúdo sem nenhum aviso.
    📌 Contador que muda de significado quando o sistema cresce é pior que
    contador errado: ele estava certo, e continua parecendo certo."""
    return int(estado.get("por_dia", {}).get(str(date.today()), 0))


def _mensagens_hoje(estado: dict) -> int:
    """Mensagens de verdade enviadas hoje, somando todos os grupos.

    Este é o número que importa pro risco: o que chama atenção é volume e
    ritmo de robô, e é ele que multiplica quando você acrescenta grupo."""
    return int(estado.get("msgs_por_dia", {}).get(str(date.today()), 0))


def _teto_mensagens() -> int:
    """Teto DURO de mensagens/dia, somando os grupos.

    ⚠️ EXISTE PORQUE O TETO DE ACHADINHOS DEIXOU DE LIMITAR O VOLUME. Antes,
    `MAX_DIA=6` garantia no máximo 6 mensagens; agora garante 6 achadinhos, que
    com 8 grupos são 48 mensagens. O número que o WhatsApp enxerga é o segundo.
    Padrão generoso o bastante pra não atrapalhar (6 achadinhos × 5 grupos) e
    baixo o bastante pra um erro de config não virar centena de mensagens."""
    try:
        return int(float(os.environ.get("WHATSAPP_MAX_MSG_DIA", "30")))
    except (TypeError, ValueError):
        return 30


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


def _estado_sessao(pagina, timeout=25000) -> str:
    """'logado' | 'qr' | 'carregando' | 'desconhecido'.

    A ordem importa: `logado` primeiro (é o caso normal e o mais barato de
    confirmar), e só depois as hipóteses do fracasso. As checagens seguintes
    são curtas de propósito — a essa altura a página já teve o `timeout`
    inteiro pra montar, e o que se pergunta agora é qual tela está na frente."""
    if _achar(pagina, SEL_LOGADO, timeout=timeout):
        return "logado"
    if _achar(pagina, SEL_QR_ESTRITO, timeout=1500):
        return "qr"
    if _achar(pagina, SEL_CARREGANDO, timeout=1500):
        return "carregando"
    return "desconhecido"


def _esperar_sessao(pagina, primeiro=25000, extra=90000) -> str:
    """Espera a sessão ficar utilizável, dando mais tempo a quem está de fato
    carregando — e só a esse.

    Esticar o timeout pra todo mundo custaria 90s em cada falha real de login.
    Esticar só quando a barra de progresso está na tela custa 0 no caso ruim e
    resolve o caso que estava sendo diagnosticado errado."""
    est = _estado_sessao(pagina, timeout=primeiro)
    if est != "carregando":
        return est
    _log(f"⏳ sessão viva, ainda sincronizando — dou mais {extra // 1000}s "
         f"(apagar conversas e criar grupo deixa isso demorado)")
    if _achar(pagina, SEL_LOGADO, timeout=extra):
        return "logado"
    return _estado_sessao(pagina, timeout=1500)


def _falar_do_estado(est: str) -> str:
    """A frase que descreve o problema — e que aponta pro conserto CERTO.

    ⚠️ Mandar "rode --login" quando a sessão está viva não é só ruído: escanear
    QR sem precisar é o padrão que faz o WhatsApp desconfiar da conta."""
    return {
        "qr": "sessão caída (QR na tela) — precisa logar de novo",
        "carregando": "o WhatsApp não terminou de sincronizar a tempo; a sessão "
                      "está viva, tentar de novo costuma resolver",
        "desconhecido": "não achei nem lista, nem QR, nem barra de progresso — "
                        "pode ser marcação nova do WhatsApp Web",
    }.get(est, est)


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
    # ⚠️ PRIMEIRA TENTATIVA: PELO data-tab, que é o que MEDI (20/08).
    # A caixa de legenda desta versão NÃO se chama "legenda" — ela se chama
    # 'Digite uma mensagem', igual à da conversa. Os rótulos abaixo, todos
    # procurando 'legenda'/'caption', não achariam nada, e o Tab às cegas do
    # fim é loteria. O que separa as duas é:
    #
    #   legenda  → data-tab='undefined'  (y=713, dentro da prévia)
    #   conversa → data-tab='10'         (y=811, no rodapé)
    #
    # Clico por coordenada, como no menu de anexo: não depende de qual nó o
    # Playwright escolhe nem de o elemento estar coberto por outro.
    try:
        d = pagina.evaluate("""
        () => {
          const sel = "[contenteditable='true'],input,textarea,[role='textbox']";
          for (const e of document.querySelectorAll(sel)) {
            if (e.offsetParent === null) continue;
            const tab = e.getAttribute("data-tab") || "";
            if (tab === "3" || tab === "10" || tab === "6") continue;
            const r = e.getBoundingClientRect();
            if (!r.width || !r.height) continue;
            return {x: Math.round(r.left + r.width / 2),
                    y: Math.round(r.top + r.height / 2), tab: tab};
          }
          return null;
        }""")
        if d:
            pagina.mouse.click(d["x"], d["y"])
            pagina.wait_for_timeout(400)
            _log(f"   foquei a legenda pelo data-tab={d['tab']!r}")
            return True
    except Exception as e:
        _log(f"   (não consegui focar pelo data-tab: {str(e)[:50]})")

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
            // ⚠️ FILTRA ANTES DE CORTAR. Antes o .slice vinha primeiro e
            // cortava os ELEMENTOS BRUTOS: barra lateral, cabeçalho e painel
            // do grupo enchiam as vagas, e o menu de anexo — que vem depois no
            // DOM — nunca entrava. Eu lia a lista sem o menu e concluía que o
            // menu não abriu, pela TERCEIRA vez nesta mesma investigação
            // (antes: slice(0,20), depois: ler só aria-label).
            .filter(e => (e.getAttribute("data-icon") ||
                          e.getAttribute("aria-label") ||
                          e.getAttribute("title") ||
                          (e.innerText || "").trim()))
            .slice(0, 140)
            .map(e => ({
              tag: e.tagName.toLowerCase(),
              icone: e.getAttribute("data-icon") || "",
              rotulo: (e.getAttribute("aria-label") ||
                       e.getAttribute("title") || "").slice(0, 40),
              // O texto visível, além do rótulo. Útil pra item que só tem
              // texto — embora, MEDIDO em 20/08, os itens deste menu tenham
              // aria-label normalmente ('Fotos e vídeos', 'Nova figurinha').
              //
              // ⚠️ REGISTRO DE UMA TEORIA MINHA QUE O DADO DERRUBOU: eu disse
              // que o menu sumia do despejo porque os itens não tinham
              // aria-label. Errado. Eles têm. O que os escondia era só o corte
              // antes do filtro (ver acima) — o menu fica no FIM do DOM, na
              // posição ~75, e o corte parava em 60. Uma causa, não duas.
              texto: (e.innerText || "").trim().replace(/\\s+/g, " ").slice(0, 40),
            }))
            .filter(x => x.icone || x.rotulo || x.texto);
        }""")
        _log(f"   controles visíveis ({motivo}):")
        for i in itens or []:
            _log(f"     <{i['tag']}"
                 f"{(' data-icon=' + i['icone']) if i['icone'] else ''}>"
                 f"  rótulo: {i['rotulo']!r}"
                 + (f"  texto: {i['texto']!r}" if i.get("texto") else ""))
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
    # ⚠️ HISTÓRICO DE SEIS DIAGNÓSTICOS ERRADOS MEUS, resumido pra ninguém
    # repetir: (1) "é o formato do arquivo" — converti tudo pra JPEG, saiu
    # sticker igual; (2) "é o Enter" — troquei pelo botão, sticker igual;
    # (3) "o input só nasce sob demanda"; (4) "o menu não abre pra automação";
    # (5) "o seletor do menu está errado"; (6) "o rótulo da opção é outro".
    #
    # A causa real: clicar em "Fotos e vídeos" abre o DIÁLOGO DE ARQUIVO DO
    # SISTEMA. O input é criado, clicado e descartado no mesmo instante. O
    # único `input[type=file]` que fica na página é o da FIGURINHA — então
    # todo `set_input_files` acertava a porta errada, e nenhuma das seis
    # teorias acima podia consertar isso, porque nenhuma era sobre a porta.
    if not _clicar_anexo(pagina):
        _dump_botoes(pagina, "não achei o botão '+' de anexo")
        return False

    # ⚠️ A FOTO ENTRA PELO SELETOR DE ARQUIVO, NÃO PELO input DO DOM.
    #
    # Esta é a correção da saga inteira (20/08). Clicar em "Fotos e vídeos"
    # abre o diálogo de arquivo do SISTEMA: o navegador cria o input, dispara
    # o clique nele e o descarta no mesmo instante. Procurar
    # `input[type=file]` depois do clique só acha o da FIGURINHA, que é o
    # único permanente — e foi exatamente por isso que toda foto virava
    # sticker: eu anexava no único input que sobrava.
    #
    # `expect_file_chooser` intercepta o diálogo nativo. É a forma canônica do
    # Playwright e não depende de o input existir no DOM.
    try:
        with pagina.expect_file_chooser(timeout=12000) as espera:
            escolhido = _clicar_opcao(pagina, ROTULOS_FOTOS)
            if not escolhido:
                _dump_botoes(pagina, "menu aberto, mas não achei 'Fotos e vídeos'")
        espera.value.set_files(str(foto))
        _log(f"   foto entregue pelo seletor de arquivo (opção {escolhido!r})")
    except Exception as e:
        # ⚠️ NÃO cai no input do DOM como plano B. O que sobra ali é o da
        # figurinha, e "tentar mesmo assim" foi o que produziu seis rodadas de
        # sticker no grupo. Sem o caminho certo, manda só o texto — que
        # funciona e não envergonha ninguém.
        _log(f"   o seletor de arquivo não abriu ({str(e)[:60]}) — mando sem foto")
        _dump_botoes(pagina, "expect_file_chooser falhou")
        try:
            pagina.keyboard.press("Escape")
        except Exception:
            pass
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
        # ⚠️ DESPEJA OS CAMPOS ANTES DE DESISTIR. Cair no envio separado é
        # perder a legenda junto da foto, e todo o histórico deste arquivo diz
        # que "não achei" costuma ser detecção ruim, não ausência. Se a caixa
        # estiver aqui embaixo, a próxima rodada corrige com dado.
        try:
            campos = pagina.evaluate(_JS_CAMPOS) or []
            _log("   — campos de texto na tela da prévia —")
            for c in campos:
                _log(f"     <{c['tag']}> data-tab={c['tab']!r} "
                     f"rótulo={c['rotulo'][:34]!r} dica={c['dica'][:34]!r} "
                     f"y={c['y']} alt={c['alt']}")
            if not campos:
                _log("     (nenhum campo editável visível — a legenda não "
                     "existe mesmo nesta tela)")
        except Exception as e:
            _log(f"   (não consegui listar os campos: {str(e)[:60]})")
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


_JS_CLICAR_ANEXO = """
() => {
  // O '+' e um SPAN de 24x24 (medido no despejo de 20/08). Quem escuta o
  // clique e o BOTAO em volta dele, nao o icone. Clicar no span pode nao
  // acionar nada — foi a diferenca que nunca tinha sido testada.
  const alvo = document.querySelector(
      "[data-testid='plus-rounded'],span[data-icon='plus-rounded']," +
      "span[data-icon='clip'],span[data-icon='attach-menu-plus']");
  if (!alvo) return {ok: false, motivo: 'nao achei o icone do +'};
  const bt = alvo.closest("button,[role='button'],div[tabindex]") || alvo;
  const r = bt.getBoundingClientRect();
  return {
    ok: true,
    tag: bt.tagName.toLowerCase(),
    igual_ao_icone: bt === alvo,
    rotulo: (bt.getAttribute('aria-label') || bt.getAttribute('title') || ''),
    x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2),
    w: Math.round(r.width), h: Math.round(r.height),
  };
}
"""


_JS_OPCAO_POR_TEXTO = """
(rotulos) => {
  // Acha o item do menu pelo TEXTO VISÍVEL. Os itens ('Documento', 'Fotos e
  // vídeos', 'Câmera', 'Nova figurinha') não têm aria-label nem title — só
  // texto. Por isso seletor de atributo nunca os pegou.
  //
  // Pega o nó MAIS FUNDO cujo texto bate, senão o <div> do menu inteiro
  // casaria com 'Fotos e vídeos' e o clique cairia no meio da lista — e
  // 'Nova figurinha' está a quatro linhas de distância. Errar aqui é
  // reproduzir a figurinha de propósito.
  const norm = s => (s || "").trim().toLowerCase()
      .normalize("NFD").replace(/[\\u0300-\\u036f]/g, "");
  let melhor = null;
  for (const e of document.querySelectorAll("li,div,span,button,[role='button']")) {
    if (e.offsetParent === null) continue;
    const t = norm(e.innerText);
    if (!t) continue;
    for (const r of rotulos) {
      if (t === norm(r)) {
        if (!melhor || e.contains(melhor) === false) melhor = e;
        if (melhor && melhor.contains(e)) melhor = e;   // fica com o mais fundo
      }
    }
  }
  if (!melhor) return {ok: false};
  const bt = melhor.closest("li,[role='button'],button,div[tabindex]") || melhor;
  const r = bt.getBoundingClientRect();
  if (!r.width || !r.height) return {ok: false};
  return {ok: true, tag: bt.tagName.toLowerCase(),
          texto: (bt.innerText || "").trim().slice(0, 40),
          x: Math.round(r.left + r.width / 2),
          y: Math.round(r.top + r.height / 2)};
}
"""


def _clicar_opcao(pagina, rotulos) -> str:
    """Clica num item de menu pelo TEXTO. '' se não achou."""
    try:
        d = pagina.evaluate(_JS_OPCAO_POR_TEXTO, list(rotulos))
    except Exception as e:
        _log(f"   não consegui procurar a opção: {str(e)[:60]}")
        return ""
    if not d or not d.get("ok"):
        return ""
    try:
        pagina.mouse.click(d["x"], d["y"])
        pagina.wait_for_timeout(1500)
        return d.get("texto") or "?"
    except Exception as e:
        _log(f"   o clique na opção falhou: {str(e)[:60]}")
        return ""


def _clicar_anexo(pagina) -> str:
    """Clica no '+' de anexo. Devolve o que clicou, ou '' se não achou.

    ⚠️ POR QUE ISTO É DIFERENTE DAS SEIS TENTATIVAS ANTERIORES (20/08).
    Até agora eu clicava no elemento que o seletor devolvia — e o despejo do
    rodapé finalmente mostrou o que ele é:

        <span icone=plus-rounded testid=plus-rounded classe=xxk0z11 24x24>

    Um SPAN de 24x24. É o ícone dentro do botão, não o botão. Playwright
    clica no centro do elemento que você der, e o handler pode estar no
    ancestral — então seis rodadas de "cliquei no + e o menu não abriu"
    podem ter sido seis cliques no lugar certo da tela e no elemento errado
    da árvore.

    Isto não é certeza; é a primeira hipótese em muito tempo que nasce de
    MEDIÇÃO e não de palpite. Por isso o clique usa coordenada real (mouse),
    que é o que mais se parece com gente, e o log diz se o ancestral era
    diferente do ícone — se for igual, esta teoria morre e a gente para de
    insistir no anexo.
    """
    try:
        d = pagina.evaluate(_JS_CLICAR_ANEXO)
    except Exception as e:
        _log(f"   não consegui localizar o '+': {str(e)[:60]}")
        return ""
    if not d or not d.get("ok"):
        _log(f"   {(d or {}).get('motivo', 'não achei o +')}")
        return ""
    if d.get("igual_ao_icone"):
        _log("   ⚠️ o ícone NÃO tem botão em volta — a teoria do ancestral "
             "não se aplica aqui; se o menu não abrir, é outra coisa.")
    else:
        _log(f"   achei o botão em volta do ícone: <{d['tag']}> "
             f"{d['w']}x{d['h']} rótulo={d['rotulo']!r}")
    try:
        # clique por COORDENADA: mais parecido com gente que element.click(),
        # e não depende de qual nó da árvore o Playwright escolhe
        pagina.mouse.click(d["x"], d["y"])
        pagina.wait_for_timeout(1600)
        return f"<{d['tag']}> em ({d['x']},{d['y']})"
    except Exception as e:
        _log(f"   o clique falhou: {str(e)[:60]}")
        return ""


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
            est = _esperar_sessao(pagina, primeiro=45000)
            if est != "logado":
                _log(_falar_do_estado(est))
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

            aberto = _clicar_anexo(pagina)
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

            # ⚠️ CLICA PELO TEXTO, não por seletor de atributo. Os itens deste
            # menu ('Documento', 'Fotos e vídeos', 'Câmera', 'Nova figurinha')
            # não têm aria-label nem title — foi por isso que o `:has-text`
            # dentro de `[role=button]/li/menuitem` não achou nada enquanto o
            # menu estava aberto na tela.
            # ⚠️ NÃO PROCURE O input[type=file] DEPOIS DO CLIQUE. Ele não fica.
            #
            # Clicar em "Fotos e vídeos" abre o SELETOR DE ARQUIVO DO SISTEMA.
            # O navegador cria o input, dispara o clique nele e o descarta no
            # mesmo instante — por isso `querySelectorAll("input[type=file]")`
            # depois do clique só encontra o da figurinha, que é permanente.
            # Eu estava procurando um elemento que já não existia e concluindo
            # "clicou mas não montou o input".
            #
            # O Playwright resolve isso com `expect_file_chooser`: ele
            # INTERCEPTA o diálogo nativo. É a forma canônica, e funciona
            # mesmo quando o input é transitório.
            print()
            _log("=== clicando em 'Fotos e vídeos' com o interceptador ligado ===")
            try:
                with pagina.expect_file_chooser(timeout=10000) as espera:
                    clicou = _clicar_opcao(pagina, ROTULOS_FOTOS)
                    if not clicou:
                        _log("   ⚠️ não achei a opção pelo texto")
                escolhedor = espera.value
                _log(f"   ✅ O SELETOR DE ARQUIVO ABRIU (cliquei em {clicou!r})")
                _log(f"      aceita vários arquivos: {escolhedor.is_multiple()}")
                _log("      → é POR AQUI que a foto entra, e não pelo input do DOM")
            except Exception as e:
                _log(f"   ⚠️ nenhum seletor de arquivo em 10s: {str(e)[:70]}")
                _log("      (se o clique não achou a opção, o problema é o "
                     "rótulo; se achou e não abriu diálogo, é outra coisa)")

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
            est = _esperar_sessao(pagina)
            if est != "logado":
                _print_erro(pagina, _falar_do_estado(est))
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

    grupos = _grupos()
    if not grupos:
        _log("WHATSAPP_GRUPOS (ou WHATSAPP_GRUPO) vazio no .env — preciso do "
             "NOME EXATO de cada grupo, separados por ';'")
        return 2

    fila = _carregar_json(FILA, [])
    if not isinstance(fila, list) or not fila:
        _log("fila vazia — nada a enviar")
        return 1

    estado = _carregar_json(ESTADO, {})
    if not isinstance(estado, dict):
        estado = {}
    ja = _bloqueados(estado)

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
            est = _esperar_sessao(pagina)
            if est != "logado":
                motivo = _falar_do_estado(est)
                caminho = _print_erro(pagina, motivo)
                # só manda escanear QR quando o QR está mesmo lá
                conserto = ("Rode:\n  .venv/bin/python whatsapp_playwright.py "
                            "--login" if est == "qr"
                            else "Não precisa logar de novo — o próximo slot "
                                 "tenta sozinho.")
                _avisar(f"WhatsApp: {motivo}\n{conserto}", caminho)
                return 1

            # a lista de conversas aparece antes da busca ficar utilizável;
            # sem esta espera o seletor falha por a interface ainda montar
            pagina.wait_for_timeout(4000)
            _fechar_modal(pagina)  # o "Novidades do WhatsApp Web" cobre a busca

            # ⚠️ UM GRUPO QUE SOME NÃO PODE CALAR OS OUTROS (29/08). Antes isto
            # era `return 1` na hora: com um grupo só, não achar o grupo era
            # mesmo o fim da rodada. Com vários, um nome digitado errado no
            # .env — ou um grupo em que a conta foi removida — apagaria o envio
            # dos outros quatro, e o log diria só "não achei o grupo X".
            # É a mesma lição do slot de Reels da @topshoptech_: falha de um
            # destino custava o slot inteiro da conta.
            abertos, perdidos = [], []
            for g in grupos:
                r = _abrir_grupo(pagina, g)
                if r:
                    abertos.append(g)
                else:
                    perdidos.append(g)
            if perdidos:
                caminho = _print_erro(
                    pagina, f"não achei: {', '.join(perdidos)[:80]}")
                _avisar(f"WhatsApp: não achei {len(perdidos)} grupo(s): "
                        f"{', '.join(perdidos)}. Confira o NOME EXATO em "
                        f"WHATSAPP_GRUPOS no .env (separador é ;).", caminho)
            if not abertos:
                _log("nenhum grupo alcançável — paro por aqui")
                return 1
            if len(abertos) > 1:
                _log(f"{len(abertos)} grupo(s): {', '.join(abertos)}")

            enviados = 0        # achadinhos concluídos
            msgs = 0            # mensagens de verdade (achadinho × grupo)
            parar = False
            hoje = str(date.today())
            for i, it in enumerate(alvo):
                texto = _mensagem(it)
                if teste:
                    _log(f"   [seco] mandaria {'COM foto' if COM_FOTO else 'SÓ LINK'}"
                         f" pra {len(abertos)} grupo(s):\n{texto}\n")
                    enviados += 1
                    continue

                # ⚠️ O MESMO ACHADINHO VAI PRA TODOS OS GRUPOS. São audiências
                # separadas, não uma lista fatiada — quem está no grupo 2 não
                # viu o que foi pro grupo 1.
                foi_em = 0
                for g in abertos:
                    if _mensagens_hoje(estado) + msgs >= _teto_mensagens():
                        _log(f"   teto de mensagens do dia ({_teto_mensagens()}) "
                             f"— paro aqui, o resto fica pra amanhã")
                        parar = True
                        break
                    if not _abrir_grupo(pagina, g):
                        # some no meio da rodada (renomeado, removeram a conta):
                        # segue pros outros. Config errada não é falha de envio.
                        _log(f"   ⏭️  {g}: sumiu no meio da rodada, pulo")
                        continue

                    foi = False
                    if COM_FOTO:
                        # caminho antigo, desligado por padrão (ver COM_FOTO no
                        # topo). Se a foto falhar em qualquer etapa, cai no
                        # texto — que ainda vende.
                        foto = _baixar_foto(it.get("imagem", ""))
                        if foto:
                            foi = _enviar_com_foto(pagina, foto, texto)
                            try:
                                foto.unlink()
                            except Exception:
                                pass

                    if not foi:
                        # se a prévia de imagem não fechou, digitar aqui
                        # escreveria a legenda DENTRO dela — melhor parar que
                        # postar torto. Com COM_FOTO=0 nunca há prévia, mas a
                        # checagem é barata e protege quem religar a foto.
                        if COM_FOTO and _achar(pagina, SEL_PREVIA, timeout=2500):
                            _print_erro(pagina, "a prévia não fechou — paro")
                            parar = True
                            break
                        # ⚠️ FALHA DE ENVIO PARA TUDO, diferente de grupo não
                        # encontrado. Não achar um grupo é problema de config e
                        # os outros seguem; `_enviar_texto` falhando quer dizer
                        # que a PÁGINA quebrou — seletor que sumiu, sessão
                        # caindo — e daí em diante nenhum clique é confiável.
                        # A regra da casa é parar na primeira dúvida.
                        if not _enviar_texto(pagina, texto):
                            parar = True
                            break

                    foi_em += 1
                    msgs += 1
                    estado.setdefault("msgs_por_dia", {})
                    estado["msgs_por_dia"][hoje] = \
                        estado["msgs_por_dia"].get(hoje, 0) + 1
                    _salvar_estado(estado)
                    _log(f"   ✅ {g}: "
                         f"{(it.get('campeao') or it.get('produto', ''))[:38]}")

                    espera = random.uniform(PAUSA_MIN, PAUSA_MAX)
                    _log(f"   (aguardando {espera:.0f}s)")
                    time.sleep(espera)

                # ⚠️ SÓ MARCA COMO ENVIADO SE SAIU EM ALGUM LUGAR. Marcar antes
                # do envio perderia o achadinho pra sempre numa rodada que
                # quebrou no meio — ele nunca mais seria candidato. E marcar uma
                # vez só (não por grupo) é o certo: o registro é "este produto
                # já foi ao ar", não "foi ao ar no grupo X".
                if foi_em:
                    enviados += 1
                    ja.add(it["link"])
                    # ⚠️ A DATA É O REGISTRO; `links` fica só como histórico.
                    # Gravar `estado["links"] = list(ja)` era o certo quando `ja`
                    # era o conjunto de tudo que já foi — agora `ja` é só o que
                    # está BLOQUEADO, e sobrescrever com ele apagaria do
                    # histórico todo produto que já saiu da quarentena.
                    estado.setdefault("enviados_em", {})[it["link"]] = \
                        int(time.time())
                    estado["links"] = sorted(
                        set(estado.get("links") or []) | {it["link"]})
                    estado.setdefault("por_dia", {})
                    estado["por_dia"][hoje] = estado["por_dia"].get(hoje, 0) + 1
                    _salvar_estado(estado)
                if parar:
                    break

            _log(f"{'simularia' if teste else 'enviei'} {enviados} achadinho(s)"
                 + (f" em {len(abertos)} grupo(s) = {msgs} mensagem(ns)"
                    if not teste and len(abertos) > 1 else ""))
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
    p.add_argument("--auto", action="store_true",
                   help="só envia se um horário sorteado de hoje estiver "
                        "vencendo — é o que o cron deve chamar")
    p.add_argument("--agenda", action="store_true",
                   help="mostra os horários sorteados de hoje e sai")
    args = p.parse_args()

    # ⚠️ `--agenda` ANTES DE QUALQUER TRAVA. Ele não abre navegador, não envia
    # nada e não depende de WHATSAPP_ATIVO: é justamente o comando pra olhar o
    # dia com o sistema DESLIGADO, antes de ligar. Trancá-lo atrás do `_ligado()`
    # seria dar um diagnóstico que só funciona quando não se precisa dele.
    if args.agenda:
        est = _carregar_json(ESTADO, {})
        hs = _agenda_do_dia(est)
        agora = datetime.now()
        am = agora.hour * 60 + agora.minute
        feitos = set((est.get("agenda") or {}).get("feitos") or [])
        print(f"\n📅 {date.today()}  ·  janela {HORA_INI:02d}:00–{HORA_FIM:02d}:59"
              f"  ·  teto {MAX_DIA}/dia, {MAX_RODADA}/rodada\n")
        for t in hs:
            marca = ("✅ enviado" if t in feitos else
                     "⏰ AGORA" if 0 <= (am - t) <= TOLERANCIA else
                     "· passou" if t < am else "· a caminho")
            print(f"   {t // 60:02d}:{t % 60:02d}   {marca}")
        print(f"\n   {_enviados_hoje(est)} de {MAX_DIA} enviada(s) hoje.")
        print(f"   Sorteada 1x por dia e guardada em {ESTADO.name} —"
              f" amanhã são outras.\n")
        return 0

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

        # ⚠️ O SLOT SÓ É MARCADO DEPOIS DO ENVIO DAR CERTO. Marcar antes
        # perderia o horário quando a sessão estivesse caída ou o grupo não
        # fosse achado — e o dia terminaria com menos mensagens do que o teto,
        # sem ninguém saber por quê. Falhou, o slot continua vencido e a
        # próxima acordada do cron (15 min) tenta de novo, dentro da tolerância.
        if args.auto:
            est = _carregar_json(ESTADO, {})
            slot = _slot_devido(est)
            if slot is None:
                prox = [t for t in _agenda_do_dia(est)
                        if t > datetime.now().hour * 60 + datetime.now().minute]
                quando = (f"{prox[0] // 60:02d}:{prox[0] % 60:02d}" if prox
                          else "amanhã")
                _log(f"não é hora — próximo horário sorteado: {quando}")
                return 0
            # ⚠️ UMA POR SLOT, NÃO `MAX_RODADA`. Com 12 horários sorteados e 2
            # mensagens por rodada seriam 24 tentativas contra um teto de 12: os
            # 6 primeiros horários gastariam o dia inteiro e a NOITE FICARIA
            # VAZIA — o espalhamento que este código existe pra criar morreria
            # na primeira tarde. `MAX_RODADA` foi feito pro modo antigo, de 3
            # disparos por dia, onde mandar 2 de uma vez era o único jeito de
            # chegar a 6. Aqui a conta é outra: 1 mensagem × N horários = N.
            #
            # O `--quantos` continua respeitado quando o Dre pede explicitamente
            # (ele nunca vem sozinho no cron), mas o padrão do `--auto` é 1.
            quantos = args.quantos if args.quantos != MAX_RODADA else 1
            _log(f"⏰ horário sorteado {slot // 60:02d}:{slot % 60:02d}"
                 f" — enviando {quantos}")
            r = enviar(max(1, min(quantos, MAX_RODADA)), teste=args.teste)
            if r == 0 and not args.teste:
                _marcar_slot(_carregar_json(ESTADO, {}), slot)
            return r

        return enviar(max(1, min(args.quantos, MAX_RODADA)), teste=args.teste)


if __name__ == "__main__":
    sys.exit(main())
