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

MAX_RODADA = int(float(os.environ.get("WHATSAPP_MAX_RODADA", "2")))
MAX_DIA = int(float(os.environ.get("WHATSAPP_MAX_DIA", "6")))
PAUSA_MIN = float(os.environ.get("WHATSAPP_PAUSA_MIN", "45"))
PAUSA_MAX = float(os.environ.get("WHATSAPP_PAUSA_MAX", "120"))
HORA_INI = int(float(os.environ.get("WHATSAPP_HORA_INI", "7")))
HORA_FIM = int(float(os.environ.get("WHATSAPP_HORA_FIM", "21")))

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


def _preco_do_item(item: dict) -> float:
    """Preço do item; 0 se ninguém sabe — e aí a linha some da mensagem.

    Nunca inventa: sem preço, o achadinho vai só com nome e link, que é o que
    já acontecia. Preço errado num grupo de compras é pior que preço nenhum.
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
    return 0.0


def _nome_do_item(item: dict) -> str:
    return (item.get("campeao") or item.get("produto")
            or item.get("titulo") or item.get("nome") or "").strip()


def _mensagem(item: dict) -> str:
    """Formato do WhatsApp: *negrito* e URL crua.

    Nada de markdown de link — o WhatsApp não embute, e colchete solto no meio
    do texto fica feio. A URL sozinha vira prévia clicável sozinha.
    """
    # espaço duplo vem de título de anúncio da Shopee e aparece na mensagem
    nome = " ".join((_nome_do_item(item) or "Achadinho").split())
    if len(nome) > 70:
        nome = nome[:67].rsplit(" ", 1)[0] + "..."
    preco = _preco_do_item(item)
    linhas = [f"*{nome}*"]
    if preco:
        linhas.append(f"💰 {_reais(preco)}")
    linhas.append("")
    linhas.append(item.get("link", ""))
    return "\n".join(linhas)


def _candidatos(fila, ja: set, quantos: int, resta_dia: int) -> list:
    """Quem entra nesta rodada. Separado do navegador de propósito: é a parte
    que decide o que vai pro ar, e tem que ser testável sem abrir o Chromium.

    Mesma regra do grupo do Telegram: precisa de link E foto. Sem foto o
    achadinho fica sem prévia e parece corrente de spam.

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
        return True

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
    return True


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
                caixa = _achar(pagina, SEL_CAIXA)
                if not caixa:
                    caminho = _print_erro(pagina, "não achei a caixa de mensagem")
                    _avisar("WhatsApp: a marcação mudou (caixa de mensagem).", caminho)
                    break

                texto = _mensagem(it)
                if teste:
                    _log(f"   [seco] mandaria:\n{texto}\n")
                    enviados += 1
                    continue

                caixa.click()
                # digita linha a linha: Enter manda a mensagem, então quebra de
                # linha tem que ser Shift+Enter
                for n, linha in enumerate(texto.split("\n")):
                    if n:
                        pagina.keyboard.press("Shift+Enter")
                    if linha:
                        pagina.keyboard.type(linha, delay=random.randint(25, 70))
                pagina.wait_for_timeout(random.randint(600, 1400))
                pagina.keyboard.press("Enter")
                pagina.wait_for_timeout(1500)

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
    p.add_argument("--forcar", action="store_true", help="ignora a janela de horário")
    p.add_argument("--quantos", type=int, default=MAX_RODADA)
    args = p.parse_args()

    # As travas de configuração vêm ANTES do playwright: erro de .env é o caso
    # comum, e ouvir "playwright não instalado" quando o problema é
    # WHATSAPP_GRUPO vazio manda a pessoa procurar no lugar errado.
    if not args.login and not args.diag and not _ligado() and not args.teste:
        _log("⚪ WHATSAPP_ATIVO desligado. Ligue com:")
        _log("     echo 'WHATSAPP_ATIVO=1' >> ~/jarvis/.env")
        _log("   (rode com --teste pra simular sem enviar)")
        return 0

    if not args.login and not args.diag and not args.forcar and not _dentro_da_janela():
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

    if args.login:
        return login()
    if args.diag:
        return diagnostico()
    return enviar(max(1, min(args.quantos, MAX_RODADA)), teste=args.teste)


if __name__ == "__main__":
    sys.exit(main())
