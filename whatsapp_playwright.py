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
import sys
import time
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if not (BASE_DIR / "shared").exists() and (BASE_DIR.parent / "shared").exists():
    BASE_DIR = BASE_DIR.parent

FILA = BASE_DIR / "shared" / "produtos_fila.json"
ESTADO = BASE_DIR / "shared" / "whatsapp_enviados.json"
SESSAO = BASE_DIR / "shared" / "whatsapp_sessao"
ERROS = BASE_DIR / "shared" / "whatsapp_erros"

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
             "div[title='Caixa de texto de pesquisa']"]
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


def _mensagem(item: dict) -> str:
    """Formato do WhatsApp: *negrito* e URL crua.

    Nada de markdown de link — o WhatsApp não embute, e colchete solto no meio
    do texto fica feio. A URL sozinha vira prévia clicável sozinha.
    """
    nome = (item.get("campeao") or item.get("produto") or "Achadinho").strip()
    if len(nome) > 70:
        nome = nome[:67].rsplit(" ", 1)[0] + "..."
    preco = item.get("preco") or 0
    linhas = [f"*{nome}*"]
    if preco:
        linhas.append(f"💰 R$ {float(preco):.2f}".replace(".", ","))
    linhas.append("")
    linhas.append(item.get("link", ""))
    return "\n".join(linhas)


def _candidatos(fila, ja: set, quantos: int, resta_dia: int) -> list:
    """Quem entra nesta rodada. Separado do navegador de propósito: é a parte
    que decide o que vai pro ar, e tem que ser testável sem abrir o Chromium.

    Mesma regra do grupo do Telegram: precisa de link E foto. Sem foto o
    achadinho fica sem prévia e parece corrente de spam.
    """
    if not isinstance(fila, list):
        return []
    novos = [it for it in fila
             if isinstance(it, dict) and it.get("link") and it.get("imagem")
             and it["link"] not in ja]
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
  for (const el of document.querySelectorAll('[aria-label]')) {
    const L = (el.getAttribute("aria-label") || "").toLowerCase();
    if (L.includes("pesquis") || L.includes("search") || L.includes("busca"))
      lista.push({grupo: "aria-label busca", ...desc(el)});
  }
  return lista;
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
            busca = _achar(pagina, SEL_BUSCA)
            if not busca:
                caminho = _print_erro(pagina, "não achei a caixa de busca")
                _avisar("WhatsApp: a marcação da página mudou (busca). "
                        "Os seletores precisam de revisão.", caminho)
                return 1
            busca.click()
            pagina.keyboard.type(grupo, delay=random.randint(60, 140))
            pagina.wait_for_timeout(2200)
            item = pagina.query_selector(f"span[title='{grupo}']")
            if not item:
                caminho = _print_erro(pagina, f"grupo '{grupo}' não apareceu na busca")
                _avisar(f"WhatsApp: não achei o grupo '{grupo}'. "
                        "Confira o NOME EXATO em WHATSAPP_GRUPO no .env.", caminho)
                return 1
            item.click()
            pagina.wait_for_timeout(1800)

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
