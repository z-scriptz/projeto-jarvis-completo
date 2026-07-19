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


def _cookies_do_dominio(dominio: str) -> int:
    """Quantos cookies carregados pertencem ao domínio (ex.: 'instagram')."""
    return sum(1 for c in _cookies_playwright() if dominio in (c.get("domain") or "").lower())


def diagnosticar(perfil: str, timeout: int = 45) -> dict:
    """DIAGNÓSTICO do IG: abre o /reels/ e reporta o que o Instagram REALMENTE
    serviu (login-wall? vazio? challenge?), quantos cookies de IG entraram, e
    salva um print da tela. É a prova de por que o Playwright volta 0 reels."""
    out = {"perfil": perfil}
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        _log("playwright não instalado.")
        return out
    user = _user_do_perfil(perfil)
    proxy = _proxy_playwright()
    cook_total = len(_cookies_playwright())
    cook_ig = _cookies_do_dominio("instagram")
    out.update({"user": user, "proxy": bool(proxy),
                "cookies_total": cook_total, "cookies_instagram": cook_ig,
                "cookies_file": (os.environ.get("YTDLP_COOKIES")
                                 or os.environ.get("IG_COOKIES") or "(nenhum)")})
    shot = BASE_DIR / "shared" / f"diag_ig_{user or 'x'}.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        exe = (os.environ.get("PLAYWRIGHT_CHROMIUM") or "").strip() or None
        browser = pw.chromium.launch(
            headless=True, proxy=proxy, executable_path=exe,
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
                out["cookies_erro"] = str(e)[:120]
        page = ctx.new_page()
        try:
            page.goto(f"https://www.instagram.com/{user}/reels/",
                      timeout=timeout * 1000, wait_until="domcontentloaded")
            page.wait_for_timeout(4500)
            out["url_final"] = page.url
            titulo = (page.title() or "")
            out["titulo"] = titulo[:120]
            out["reels_links"] = len(page.query_selector_all('a[href*="/reel/"]'))
            out["post_links"] = len(page.query_selector_all('a[href*="/p/"]'))
            out["links_total"] = len(page.query_selector_all("a"))
            # o perfil CARREGOU se o @handle (ou o user) aparece no título da aba
            out["perfil_carregou"] = bool(user and user.lower() in titulo.lower())
            corpo = (page.inner_text("body") or "").lower()
            # LOGIN DURO = redirect pro /login OU título de página de login (não só o
            # texto de rodapé "Entrar/Criar conta" que aparece em perfil público).
            out["login_duro"] = ("/login" in page.url or "/accounts/login" in page.url
                                 or "entrar" in titulo.lower()
                                 or "log in" in titulo.lower())
            # SESSÃO FRACA = perfil carrega mas a grade de mídia não vem (0 reels/posts)
            out["midia_bloqueada"] = (out["perfil_carregou"]
                                      and out["reels_links"] == 0
                                      and out["post_links"] == 0)
            out["parece_login"] = out["login_duro"]
            out["parece_challenge"] = any(t in corpo for t in
                                          ("suspeita", "suspicious", "confirme", "confirm",
                                           "robô", "not a robot", "tente novamente mais tarde",
                                           "try again later"))
            try:
                page.screenshot(path=str(shot))
                out["screenshot"] = str(shot)
            except Exception:
                pass
        except Exception as e:
            out["erro"] = str(e)[:150]
        finally:
            browser.close()
    return out


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


# ── TikTok: autores de uma hashtag (ALAVANCA 2) ─────────────────────────────
# yt-dlp morreu pra hashtag do TikTok ("marked as broken"). Aqui abrimos a página
# /tag/HASHTAG num Chromium real, rolamos e lemos os @handles direto dos links de
# vídeo (/@handle/video/…). Reusa proxy + cookies + stealth do IG. Best-effort nas
# views (o container do TikTok muda de nome direto), então retorna 0 quando não acha
# — a descoberta pontua por frequência mesmo, então views é só um bônus.
def autores_hashtag_tiktok(tag: str, limite: int = 30, headless: bool = True,
                           timeout: int = 45) -> list:
    """Abre https://www.tiktok.com/tag/<tag> num navegador real e devolve
    [(handle, views)] dos vídeos que aparecerem (rolando a página)."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        _log("playwright não instalado — .venv/bin/pip install playwright "
             "&& .venv/bin/playwright install chromium")
        return []
    t = (tag or "").lstrip("#").strip()
    if not t:
        return []
    proxy = _proxy_playwright()
    vistos, out = set(), []
    _log(f"abrindo #{t}" + (" via proxy" if proxy else "") + " (Chromium real)…")
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
            page.goto(f"https://www.tiktok.com/tag/{t}",
                      timeout=timeout * 1000, wait_until="domcontentloaded")
            page.wait_for_timeout(4500)
            for _ in range(14):
                # JS que anda do link de vídeo pro card e pega o strong de views ao lado
                try:
                    itens = page.evaluate(
                        """() => {
                            const seen = {}, res = [];
                            document.querySelectorAll('a[href*="/video/"]').forEach(a => {
                                const m = (a.getAttribute('href')||'').match(/\\/@([^\\/?#]+)\\/video\\//);
                                if (!m) return;
                                const h = m[1].toLowerCase();
                                if (seen[h]) return; seen[h] = 1;
                                let v = 0, node = a;
                                for (let i = 0; i < 6 && node; i++) {
                                    const s = node.querySelector &&
                                        node.querySelector('strong[data-e2e="video-views"]');
                                    if (s) { v = s.textContent.trim(); break; }
                                    node = node.parentElement;
                                }
                                res.push([h, v]);
                            });
                            return res;
                        }"""
                    ) or []
                except Exception:
                    itens = []
                for h, vtxt in itens:
                    if h and h not in vistos:
                        vistos.add(h)
                        out.append((h, _views_para_int(vtxt)))
                if len(out) >= limite:
                    break
                page.mouse.wheel(0, 6000)
                page.wait_for_timeout(2500)
        except Exception as e:
            _log(f"erro em #{t}: {str(e)[:150]}")
        finally:
            browser.close()
    _log(f"{len(out)} autores em #{t}")
    return out[:limite]


def _views_para_int(v) -> int:
    """'1.2M' / '340.5K' / '12,3 mil' → int. Devolve 0 se não der."""
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v or "").strip().upper().replace(",", ".")
    if not s:
        return 0
    # ordem importa: MIL/MI antes de M, senão 'MIL' casa só o 'M' e vira milhão
    m = re.match(r"([\d.]+)\s*(MIL|MI|K|M|B)?", s)
    if not m:
        return 0
    try:
        n = float(m.group(1))
    except ValueError:
        return 0
    mult = {"K": 1e3, "MIL": 1e3, "M": 1e6, "MI": 1e6, "B": 1e9}.get(m.group(2) or "", 1)
    return int(n * mult)


if __name__ == "__main__":
    _carregar_env()
    hl = "--headed" not in sys.argv
    # modo hashtag do TikTok:  python3 ig_playwright.py --tag "#maquiagem" [limite]
    if "--tag" in sys.argv:
        i = sys.argv.index("--tag")
        tag = sys.argv[i + 1] if len(sys.argv) > i + 1 else ""
        lim = 30
        for a in sys.argv[i + 2:]:
            if a.isdigit():
                lim = int(a); break
        if not tag:
            print("uso: python3 ig_playwright.py --tag \"#hashtag\" [limite]")
            sys.exit(1)
        autores = autores_hashtag_tiktok(tag, lim, headless=hl)
        print(f"#{tag.lstrip('#')}: {len(autores)} autor(es)")
        for h, vw in autores:
            print(f"  @{h}  {vw:,} views" if vw else f"  @{h}  (views ?)")
        sys.exit(0)
    # DIAGNÓSTICO do IG: por que volta 0 reels?  ig_playwright.py --diag <perfil>
    if "--diag" in sys.argv:
        i = sys.argv.index("--diag")
        perfil = sys.argv[i + 1] if len(sys.argv) > i + 1 else "instagram"
        d = diagnosticar(perfil)
        print("\n=== DIAGNÓSTICO IG ===")
        for k in ("perfil", "user", "cookies_file", "cookies_total",
                  "cookies_instagram", "proxy", "url_final", "titulo",
                  "perfil_carregou", "reels_links", "post_links", "links_total",
                  "login_duro", "midia_bloqueada", "parece_challenge",
                  "screenshot", "erro", "cookies_erro"):
            if k in d:
                print(f"  {k:18}: {d[k]}")
        print("\n📖 leitura:")
        if d.get("cookies_instagram", 0) == 0:
            print("  ⚠️  ZERO cookies de instagram → o cookies.txt não tem sessão do IG. "
                  "É PRECISO um cookies.txt logado no IG.")
        if d.get("login_duro"):
            print("  ⚠️  LOGIN DURO (redirect/título de login) → sem sessão válida.")
        elif d.get("midia_bloqueada"):
            print("  ⚠️  SESSÃO FRACA: o perfil CARREGA mas a grade de mídia está BLOQUEADA "
                  "(0 reels/posts). Causa provável: sessionid expirado OU o IG desconfia do "
                  "IP do proxy (sessão criada noutro IP/dispositivo). Conserto: renovar o "
                  "ig_cookies.txt logado no IG — de preferência gerando a sessão JÁ pelo proxy.")
        if d.get("parece_challenge"):
            print("  ⚠️  CHALLENGE/anti-bot → IP do proxy pode estar queimado.")
        if d.get("reels_links", 0) > 0:
            print("  ✅ tem reels no DOM — sessão OK; o problema é seletor/scroll.")
        sys.exit(0)
    perfil = sys.argv[1] if len(sys.argv) > 1 else ""
    lim = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 8
    if not perfil:
        print("uso: python3 ig_playwright.py <perfil> [limite]  |  --tag \"#hashtag\"")
        sys.exit(1)
    for u in listar_reels(perfil, lim, headless=hl):
        print(u)
