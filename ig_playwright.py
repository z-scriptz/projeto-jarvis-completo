#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ig_playwright.py -- lista os Reels de um perfil do Instagram usando um NAVEGADOR
# DE VERDADE (Playwright/Chromium + stealth). Contorna o bloqueio de API que derruba
# o instaloader/yt-dlp: renderiza a página /reels/ como um humano, ROLA a tela e lê
# os links dos reels direto do HTML. Reusa os MESMOS cookies (YTDLP_COOKIES) e o
# proxy (IG_PROXY). Só LISTA — o download de cada reel continua no yt-dlp + auto-crop.
#
# VPS (uma vez):  .venv/bin/pip install playwright && .venv/bin/playwright install chromium
# Teste:          .venv/bin/python ig_playwright.py promosda.alana 8
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# stealth mínimo: esconde as digitais que o IG usa pra pegar automação
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR','pt','en-US']});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
window.chrome = { runtime: {} };
const _q = window.navigator.permissions && window.navigator.permissions.query;
if (_q) { window.navigator.permissions.query = (p) => (
    p && p.name === 'notifications'
      ? Promise.resolve({state: Notification.permission}) : _q(p)); }
"""

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _log(m):
    print(f"[ig_playwright] {m}")


def _carregar_env():
    envf = BASE_DIR / ".env"
    if not envf.exists():
        return
    for ln in envf.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        if ln.lower().startswith("export "):
            ln = ln[7:]
        k, _, v = ln.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _proxy_playwright():
    """IG_PROXY=http://user:pass@host:porta → dict do Playwright (ou None)."""
    px = (os.environ.get("IG_PROXY") or "").strip()
    if not px:
        return None
    m = re.match(r"(https?|socks5)://(?:([^:@]+):([^@]+)@)?([^:/]+):(\d+)", px)
    if not m:
        return None
    scheme, user, pw, host, port = m.groups()
    cfg = {"server": f"{scheme}://{host}:{port}"}
    if user:
        cfg["username"] = user
    if pw:
        cfg["password"] = pw
    return cfg


def _cookies_playwright():
    """cookies.txt (Netscape, o mesmo do yt-dlp) → lista de cookies do Playwright."""
    arq = (os.environ.get("YTDLP_COOKIES") or os.environ.get("IG_COOKIES") or "").strip()
    if not arq or not Path(arq).exists():
        return []
    cks = []
    for ln in Path(arq).read_text(encoding="utf-8").splitlines():
        ln = ln.rstrip("\n")
        if not ln.strip() or ln.strip().startswith("#"):
            continue
        p = ln.split("\t")
        if len(p) < 7:
            continue
        domain, _flag, path, secure, expiry, name, value = p[:7]
        ck = {"name": name, "value": value, "domain": domain, "path": path or "/",
              "secure": str(secure).upper() == "TRUE", "httpOnly": False}
        try:
            if expiry and int(expiry) > 0:
                ck["expires"] = int(expiry)
        except ValueError:
            pass
        cks.append(ck)
    return cks


def _user_do_perfil(perfil: str) -> str:
    p = perfil.strip().rstrip("/")
    if "instagram.com" in p.lower():
        try:
            return [x for x in p.split("instagram.com/", 1)[1].split("/") if x][0].lstrip("@")
        except Exception:
            return ""
    return p.lstrip("@")


def listar_reels(perfil: str, limite: int = 8, headless: bool = True, timeout: int = 45) -> list:
    """Abre o /reels/ do perfil num Chromium real, rola e extrai os links dos reels."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        _log("playwright não instalado — .venv/bin/pip install playwright "
             "&& .venv/bin/playwright install chromium")
        return []
    user = _user_do_perfil(perfil)
    if not user:
        return []
    proxy = _proxy_playwright()
    urls, seen = [], set()
    _log(f"abrindo @{user}" + (" via proxy" if proxy else "") + " (Chromium real)…")
    with sync_playwright() as pw:
        exe = (os.environ.get("PLAYWRIGHT_CHROMIUM") or "").strip() or None
        browser = pw.chromium.launch(
            headless=headless, proxy=proxy, executable_path=exe,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-dev-shm-usage"])
        ctx = browser.new_context(user_agent=_UA, locale="pt-BR",
                                  viewport={"width": 1280, "height": 900})
        ctx.add_init_script(_STEALTH_JS)
        cks = _cookies_playwright()
        if cks:
            try:
                ctx.add_cookies(cks)
            except Exception as e:
                _log(f"cookies não aplicaram: {str(e)[:80]}")
        page = ctx.new_page()
        try:
            page.goto(f"https://www.instagram.com/{user}/reels/",
                      timeout=timeout * 1000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            for _ in range(10):
                for a in page.query_selector_all('a[href*="/reel/"]'):
                    m = re.search(r"/reel/([^/?#]+)", a.get_attribute("href") or "")
                    if m and m.group(1) not in seen:
                        seen.add(m.group(1))
                        urls.append(f"https://www.instagram.com/reel/{m.group(1)}/")
                if len(urls) >= limite:
                    break
                page.mouse.wheel(0, 5000)
                page.wait_for_timeout(2500)
        except Exception as e:
            _log(f"erro em @{user}: {str(e)[:150]}")
        finally:
            browser.close()
    _log(f"{len(urls)} reels de @{user}")
    return urls[:limite]


if __name__ == "__main__":
    _carregar_env()
    perfil = sys.argv[1] if len(sys.argv) > 1 else ""
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    hl = "--headed" not in sys.argv
    if not perfil:
        print("uso: python3 ig_playwright.py <perfil> [limite]")
        sys.exit(1)
    for u in listar_reels(perfil, lim, headless=hl):
        print(u)
