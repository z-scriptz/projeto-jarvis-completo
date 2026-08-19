#!/usr/bin/env python3
# tiktok_coletor.py -- FONTE NOVA: pega vídeos VIRAIS de perfis do TikTok, usa o
# Gemini pra identificar o produto (o teu "print e procura", automatizado),
# acha o produto na Shopee, gera TEU link de afiliado (com sub_id 'tiktok' pra
# atribuição por canal) e baixa o vídeo sem marca d'água pra esteira.
#
# Achadinho gringo que não tem na Shopee é DESCARTADO (filtro natural).
#
# Uso (VPS):
#   python3 tiktok_coletor.py --dry @perfil1 @perfil2   # só identifica (não baixa)
#   python3 tiktok_coletor.py @perfil1 @perfil2         # identifica + baixa
#   python3 tiktok_coletor.py                           # lê tiktok_perfis.txt
import os
import re
import sys
import json
import time
import shutil
import subprocess
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent
PERFIS_TXT = BASE_DIR / "tiktok_perfis.txt"
IG_PERFIS_TXT = BASE_DIR / "instagram_perfis.txt"   # mesma esteira, fonte Instagram
VISTOS = BASE_DIR / "shared" / "tiktok_vistos.json"
INBOX = BASE_DIR / "inbox_tiktok"

MIN_VIEWS = 50_000      # min de views (default; override por MIN_VIEWS no .env — aplicado após _carregar_env)
MAX_DUR = 90            # segundos
POR_PERFIL = 40         # quantos vídeos recentes checar por perfil (--limite muda)

# --- Amazon: fallback quando NÃO tem na Shopee. Usa link de BUSCA afiliado
# (amazon.com.br/s?k=produto&tag=SUATAG) — não precisa da PA-API, só da tag.
# Gated por AMAZON_ATIVO=1 + AMAZON_TAG no .env (desligado = só Shopee, como hoje).
from urllib.parse import quote_plus

# palavras INGLESAS comuns (funcionais + de comida/lifestyle gringo). Se o termo
# tem QUALQUER uma como palavra inteira, é legenda/hook em inglês, não produto
# pt-BR → não vira link Amazon (evita "dirty coconut", "meal prep yogurt"...).
_EN_WORDS = frozenset("""
the a an with without for this that your you have has had make making made home
new most love good best my her his their and or who like now today high small big
buy order deliver want finding restock restocking packing pack prep prepping meal
protein soda yogurt lunch coconut sweet treat healthy drink refresher smoothie
salad cream blast organize organizing fridge kitchen watch dirty ultimate busy
forgetful themed satisfying people favorite floor mop steam cleaner gradient
projector lamp night light cake fruit summer daughter pink viral ice bag give
friend people setting starting cottage clean into every from they them we our
tips hacks hack
""".split())

# Espanhol. O conteúdo em espanhol chega junto no TikTok e passava inteiro:
# a lista acima só tem inglês, e o _termo_heuristico remove palavra funcional
# do PORTUGUÊS — numa legenda espanhola nada casa e a frase vira "produto".
#
# CADA palavra aqui foi escolhida por NÃO existir em português. Um "todo",
# "rico" ou "pelo" nesta lista reprovaria produto brasileiro legítimo, e o
# preço de um falso positivo (produto bom descartado calado) é maior que o de
# um falso negativo (que o filtro de juízo já pega).
_ES_WORDS = frozenset("""
cosas deberías deberias hacer mejorar apariencia huela hola muy más
cómo aquí también están tienes tiene mejor mejores día días años niños
niñas chicas chicos ellos nosotros ustedes siempre nuevo nueva pequeño pequeña
conmigo esto eso mucho mucha
""".split())


def _amazon_ativo() -> bool:
    return (os.getenv("AMAZON_ATIVO", "0").strip().lower() in ("1", "true", "sim")
            and bool(os.getenv("AMAZON_TAG", "").strip()))


def _produto_pra_amazon(termo: str) -> bool:
    """Só monta link Amazon pra termo que PARECE produto pt-BR de verdade —
    rejeita se tiver qualquer palavra funcional/comida do inglês (o Gemini às
    vezes devolve legenda/hook gringo em vez de produto)."""
    if not termo or not _termo_valido(termo):
        return False
    palavras = re.findall(r"[a-zA-ZÀ-ÿ]+", termo.lower())
    if not (2 <= len(palavras) <= 8):
        return False
    return not any(p in _EN_WORDS or p in _ES_WORDS for p in palavras)


def _amazon_link(termo: str) -> str:
    tag = os.getenv("AMAZON_TAG", "").strip()
    dom = os.getenv("AMAZON_DOMAIN", "amazon.com.br").strip() or "amazon.com.br"
    return f"https://www.{dom}/s?k={quote_plus(termo)}&tag={tag}"


def _tem_watermark(video, dur=0) -> bool:
    """Gemini Vision olha 1 frame: True se tem MARCA D'ÁGUA / @usuário / logo de
    OUTRO criador (que vazaria crédito no visual). Gated por ANTI_WATERMARK.
    Best-effort: desligado, sem key ou erro -> False (mantém o vídeo + loga)."""
    if os.getenv("ANTI_WATERMARK", "1").strip().lower() not in ("1", "true", "sim"):
        return False
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return False
    frame = Path(str(video)).with_suffix(".wm.jpg")
    try:
        # frame a ~40% do vídeo (evita intro preta; marca d'água costuma ser fixa)
        pos = max(1, int((float(dur) or 4) * 0.4))
        subprocess.run(["ffmpeg", "-y", "-ss", str(pos), "-i", str(video),
                        "-vframes", "1", "-q:v", "3", str(frame)],
                       capture_output=True, timeout=40)
        if not frame.exists() or frame.stat().st_size < 500:
            return False
        from google import genai
        from google.genai import types
        cli = genai.Client(api_key=key)
        prompt = (
            "Este é um frame de um vídeo de produto que vou REPOSTAR. Tem alguma "
            "MARCA D'ÁGUA, @usuário, logo, ou nome de criador/perfil SOBREPOSTO na "
            "imagem, que daria crédito a OUTRA pessoa? IGNORE texto do próprio "
            "produto/embalagem e preços. Responda SÓ com uma palavra: SIM ou NAO.")
        r = cli.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Part.from_bytes(data=frame.read_bytes(),
                                            mime_type="image/jpeg"), prompt])
        return (r.text or "").strip().upper().startswith("SIM")
    except Exception as e:
        _log(f"     (anti-watermark falhou, mantém o vídeo: {str(e)[:55]})")
        return False
    finally:
        try:
            frame.unlink()
        except Exception:
            pass


def _visao_ativa() -> bool:
    """Identificar produto pela IMAGEM (Gemini Vision) quando a legenda não revela
    (curiosity-gap, comum no IG). Gated VISAO_PRODUTO=1 + precisa da GEMINI_API_KEY."""
    return (os.getenv("VISAO_PRODUTO", "1").strip().lower() in ("1", "true", "sim")
            and bool(os.getenv("GEMINI_API_KEY", "")))


def _termo_por_visao(video, dur=0, legenda="") -> str:
    """Gemini Vision OLHA 3 frames (+ a legenda como pista) e diz que PRODUTO é —
    pra quando a legenda é só gancho ('você precisa ter ISSO 😍'). Termo PT-BR ou ''."""
    if not _visao_ativa():
        return ""
    key = os.getenv("GEMINI_API_KEY", "")
    n, frames, fpaths = 3, [], []
    try:
        d = float(dur) or 6.0
        for i in range(n):
            pos = max(1.0, d * (i + 1) / (n + 1))     # 3 momentos espalhados
            f = Path(str(video)).with_suffix(f".prod{i}.jpg")
            fpaths.append(f)
            subprocess.run(["ffmpeg", "-y", "-ss", f"{pos:.1f}", "-i", str(video),
                            "-vframes", "1", "-q:v", "3", str(f)],
                           capture_output=True, timeout=40)
            if f.exists() and f.stat().st_size > 500:
                frames.append(f.read_bytes())
        if not frames:
            return ""
        from google import genai
        from google.genai import types
        cli = genai.Client(api_key=key)
        pista = (f"A LEGENDA do vídeo (pode ser só um gancho, às vezes sem dizer o "
                 f"produto, mas ajuda a entender o USO) é: \"{legenda.strip()[:200]}\". "
                 if legenda.strip() else "")
        prompt = (
            "Estes são frames de um vídeo de 'achadinho'. " + pista +
            "Qual é o PRODUTO físico principal sendo mostrado/demonstrado? Responda "
            "APENAS com um termo CURTO e ESPECÍFICO de busca em português do Brasil "
            "pra achar ESSE produto numa loja (ex: 'palmilha ortopédica gel', "
            "'suporte de notebook', 'luminária de flor', 'organizador de geladeira'). "
            "Pense no PROBLEMA que ele resolve (ex: dor no pé em quem fica em pé = "
            "palmilha). Só o termo — sem marca, sem frase, sem aspas. Se não der pra "
            "identificar um produto físico, responda NAO.")
        parts = [types.Part.from_bytes(data=b, mime_type="image/jpeg") for b in frames]
        r = cli.models.generate_content(model="gemini-2.5-flash", contents=parts + [prompt])
        t = (r.text or "").strip().strip('"').strip("'").split("\n")[0].strip()
        if not t or t.upper().startswith("NAO") or len(t) > 60:
            return ""
        _log(f"     👁️  Gemini viu ({len(frames)} frames): '{t}'")
        return t
    except Exception as e:
        _log(f"     (visão de produto falhou: {str(e)[:55]})")
        return ""
    finally:
        for f in fpaths:
            try:
                f.unlink()
            except Exception:
                pass


def _carregar_env():
    for cand in (BASE_DIR / ".env", Path(".env")):
        if not cand.exists():
            continue
        for linha in cand.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            k, _, v = linha.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        break


_carregar_env()

# agora que o .env está carregado, aplica o override do min de views (se houver)
MIN_VIEWS = int(os.environ.get("MIN_VIEWS", MIN_VIEWS))

try:
    from integrations.shopee_affiliate import minerar_oportunidades, gerar_link_afiliado
except Exception:
    from shopee_affiliate import minerar_oportunidades, gerar_link_afiliado


def _log(m):
    print(f"[tiktok] {m}")


_YTDLP_CMD = None


def _resolver_ytdlp():
    """Acha o yt-dlp mesmo que o script rode com o python errado (o yt-dlp foi
    instalado no venv). Testa o binário e o módulo em vários interpretadores."""
    global _YTDLP_CMD
    if _YTDLP_CMD is not None:
        return _YTDLP_CMD
    # 1) binário 'yt-dlp' (PATH ou venv)
    for c in (shutil.which("yt-dlp"),
              str(BASE_DIR / ".venv" / "bin" / "yt-dlp"),
              "/root/jarvis/.venv/bin/yt-dlp"):
        if c and Path(c).exists():
            _YTDLP_CMD = [c]
            return _YTDLP_CMD
    # 2) python que tenha o módulo yt_dlp
    for py in (sys.executable,
               str(BASE_DIR / ".venv" / "bin" / "python3"),
               "/root/jarvis/.venv/bin/python3"):
        if py and Path(py).exists():
            try:
                r = subprocess.run([py, "-m", "yt_dlp", "--version"],
                                   capture_output=True, text=True, timeout=25)
                if r.returncode == 0:
                    _YTDLP_CMD = [py, "-m", "yt_dlp"]
                    return _YTDLP_CMD
            except Exception:
                pass
    _YTDLP_CMD = [sys.executable, "-m", "yt_dlp"]   # fallback (erro claro)
    return _YTDLP_CMD


def _cookies_args(fonte: str = "") -> list:
    """Cookies pro yt-dlp. O Instagram quase sempre EXIGE sessão logada pra listar
    Reels — aponte YTDLP_COOKIES (ou IG_COOKIES) pra um cookies.txt exportado do
    navegador. Sem cookies, o IG costuma falhar (login wall). O TikTok não precisa.
    Alternativa: YTDLP_COOKIES_FROM_BROWSER=chrome (usa cookies do navegador local)."""
    arq = (os.environ.get("YTDLP_COOKIES") or os.environ.get("IG_COOKIES") or "").strip()
    if arq and Path(arq).exists():
        return ["--cookies", arq]
    nav = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    if nav:
        return ["--cookies-from-browser", nav]
    return []


def _ig_proxy() -> str:
    """Proxy só pro Instagram (o IG bloqueia IP de datacenter). Aceita
    IG_PROXY=socks5://user:pass@host:porta ou http://... no .env. Pra socks5 no
    instaloader precisa: .venv/bin/pip install 'requests[socks]'. Vazio = sem proxy."""
    return (os.environ.get("IG_PROXY") or "").strip()


def _ytdlp(args: list, timeout=120, fonte: str = ""):
    # roteia SÓ requests do Instagram pelo proxy (TikTok continua direto/rápido)
    extra = []
    px = _ig_proxy()
    if px and (fonte == "instagram" or any("instagram.com" in str(a) for a in args)):
        extra = ["--proxy", px]
    return subprocess.run([*_resolver_ytdlp(), *_cookies_args(fonte), *extra, *args],
                          capture_output=True, text=True, timeout=timeout)


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return s[:40] or "video"


def _subid(x, padrao: str = "") -> str:
    """Etiqueta de sub_id da Shopee: SÓ alfanumérico, <=16 chars (a Shopee rejeita
    _/-/espaço → erro 11001). É a MESMA regra do produzir_tiktok — a fonte vira o
    sub_id[3] (canal, nicho, produto, FONTE) pro CEO cruzar venda × fonte."""
    v = re.sub(r"[^A-Za-z0-9]", "", str(x or ""))[:16]
    return v or padrao


def _url_perfil(perfil: str, fonte: str) -> str:
    """Monta a URL do perfil pela fonte. Instagram → /reels/ (só Reels);
    TikTok → /@handle. Se já vier http, usa como está."""
    if perfil.startswith("http"):
        return perfil
    h = perfil.lstrip("@")
    if fonte == "instagram":
        return f"https://www.instagram.com/{h}/reels/"
    return f"https://www.tiktok.com/@{h}"


def _ig_username(perfil: str) -> str:
    """Extrai o @username de um perfil do IG (aceita handle ou URL)."""
    p = perfil.strip().rstrip("/")
    if p.startswith("http"):
        # https://www.instagram.com/<user>/reels/ → <user>
        try:
            partes = [x for x in p.split("instagram.com/", 1)[1].split("/") if x]
            return partes[0].lstrip("@") if partes else ""
        except Exception:
            return ""
    return p.lstrip("@")


def _listar_ig_instaloader(perfil: str, limite: int) -> list:
    """Lista os Reels de um perfil do IG via instaloader (o yt-dlp não enumera
    perfil de forma confiável). Reusa o MESMO cookies.txt (YTDLP_COOKIES). Retorna
    URLs de reel; o download de cada um continua pelo yt-dlp (que já funciona)."""
    try:
        import instaloader
        import http.cookiejar
    except Exception:
        _log("   instaloader não instalado — rode: .venv/bin/pip install instaloader")
        return []
    user = _ig_username(perfil)
    if not user:
        return []
    # max_connection_attempts=1 → NÃO fica martelando em caso de rate-limit (cada
    # retry piora o castigo do IG). Melhor falhar rápido e tentar de novo mais tarde.
    L = instaloader.Instaloader(quiet=True, download_pictures=False,
                                download_videos=False, download_comments=False,
                                save_metadata=False, compress_json=False,
                                max_connection_attempts=1)
    try:
        # 1) AUTENTICA primeiro. PREFERIDO: sessão NATIVA do instaloader (o IG barra
        #    menos que cookies do navegador). Crie com a conta:
        #      .venv/bin/instaloader --login=SUA_CONTA  → INSTALOADER_USER no .env.
        login_user = os.environ.get("INSTALOADER_USER", "").strip()
        if login_user:
            # A SESSÃO NÃO PODE MORAR EM /tmp. Em 08/08 a coleta do Instagram
            # estava falhando havia dias com:
            #   [Errno 2] .../tmp/.instaloader-root/session-sxrwping
            # O arquivo não estava corrompido — tinha SUMIDO. Rodando como root
            # o instaloader cai em /tmp, e /tmp é limpo em reboot e por rotina
            # do sistema. Ou seja: a sessão tinha prazo de validade que ninguém
            # escolheu, e quando venceu o log dizia "falhou", não "sumiu".
            #
            # Ordem de procura: INSTALOADER_SESSION → shared/ (sobrevive) →
            # caminho padrão do instaloader (que pode ser /tmp — último recurso).
            sess = os.environ.get("INSTALOADER_SESSION", "").strip()
            nosso = BASE_DIR / "shared" / f"instaloader-{login_user}.session"
            if sess and Path(sess).exists():
                L.load_session_from_file(login_user, sess)
            elif nosso.exists():
                L.load_session_from_file(login_user, str(nosso))
            else:
                L.load_session_from_file(login_user)     # padrão (pode ser /tmp)
        else:
            # 2) fallback: cookies.txt do navegador (funciona, mas o IG barra mais)
            cookie = (os.environ.get("YTDLP_COOKIES") or os.environ.get("IG_COOKIES") or "").strip()
            if cookie and Path(cookie).exists():
                cj = http.cookiejar.MozillaCookieJar(cookie)
                cj.load(ignore_discard=True, ignore_expires=True)
                L.context._session.cookies.update(cj)
        # 3) PROXY *depois* de autenticar — o load_session cria uma sessão NOVA,
        #    então o proxy tem que ir na sessão que já carregou os cookies (senão
        #    a requisição vai sem login → "Profile does not exist").
        px = _ig_proxy()
        if px:
            L.context._session.proxies.update({"http": px, "https": px})
            _log(f"   via proxy {px.split('@')[-1]}")   # não loga user:senha
        prof = instaloader.Profile.from_username(L.context, user)
        urls = []
        for post in prof.get_posts():
            if getattr(post, "is_video", False):
                urls.append(f"https://www.instagram.com/reel/{post.shortcode}/")
            if len(urls) >= limite:
                break
        _log(f"   instaloader: {len(urls)} reels de @{user}")
        return urls
    except Exception as e:
        _log(f"   instaloader falhou em @{user}: {str(e)[:120]}")
        return []


def _listar_ig_playwright(perfil: str, limite: int) -> list:
    """Lista os Reels via NAVEGADOR real (Playwright + stealth) — contorna o bloqueio
    de API do instaloader. Reusa cookies (YTDLP_COOKIES) + proxy (IG_PROXY)."""
    try:
        import ig_playwright
        return ig_playwright.listar_reels(perfil, limite)
    except Exception as e:
        _log(f"   playwright indisponível ({str(e)[:70]})")
        return []


def _listar_videos(perfil: str, limite: int, fonte: str = "tiktok") -> list:
    """URLs dos vídeos mais recentes do perfil (sem baixar). TikTok via yt-dlp;
    Instagram via Playwright (navegador real) → instaloader → yt-dlp (fallbacks)."""
    if fonte == "instagram":
        # URL DIRETA de reel/post → não precisa listar; o yt-dlp baixa direto.
        low = perfil.lower()
        if perfil.startswith("http") and ("/reel/" in low or "/p/" in low or "/tv/" in low):
            return [perfil]
        # 1) Playwright (navegador real) — com RETRY: o IG é flaky (vimos 0→12 reels
        #    no MESMO perfil sem trocar nada), então uma 2ª tentativa recupera muito.
        urls = _listar_ig_playwright(perfil, limite)
        if not urls:
            time.sleep(int(os.environ.get("IG_RETRY_SEG", 6)))
            urls = _listar_ig_playwright(perfil, limite)
        if urls:
            return urls
        # 2) instaloader (API) SÓ se explicitamente ligado. O fallback yt-dlp do IG
        #    dá 429 e QUEIMA o IP do proxy (foi o que estrangulou tudo) — desligado
        #    por padrão. IG_FALLBACK_YTDLP=1 religa o comportamento antigo.
        if os.environ.get("IG_FALLBACK_YTDLP", "0").strip().lower() in ("1", "true", "sim"):
            urls = _listar_ig_instaloader(perfil, limite)
            if urls:
                return urls
        else:
            _log("   (IG vazio nesta rodada — Playwright 0; NÃO martelo yt-dlp p/ não "
                 "tomar 429. IG_FALLBACK_YTDLP=1 religa os fallbacks.)")
            return []
    url = _url_perfil(perfil, fonte)
    r = _ytdlp(["--flat-playlist", "-J", "--playlist-end", str(limite), url], fonte=fonte)
    try:
        d = json.loads(r.stdout)
        out = []
        for e in (d.get("entries") or []):
            u = e.get("url")
            if u:
                out.append(u)
            elif e.get("id") and fonte == "tiktok":   # TikTok resolve id→url
                out.append(f"https://www.tiktok.com/@x/video/{e.get('id')}")
        return out
    except Exception:
        _log(f"   não consegui listar {perfil} [{fonte}]: {(r.stderr or '')[:120]}")
        return []


def _metadados(url: str) -> dict:
    r = _ytdlp(["--skip-download", "-J", "--no-playlist", url])
    try:
        d = json.loads(r.stdout)
        return {
            "id": str(d.get("id") or ""),
            "url": d.get("webpage_url") or url,
            "descricao": (d.get("description") or d.get("title") or "").strip(),
            "views": int(d.get("view_count") or 0),
            "duracao": int(d.get("duration") or 0),
            "uploader": d.get("uploader") or "",
        }
    except Exception:
        return {}


_LIXO = re.compile(r"#\S+|http\S+|@\S+|[\U0001F000-\U0001FAFF☀-➿]", re.U)


def _termo_heuristico(desc: str) -> str:
    t = _LIXO.sub(" ", desc or "")
    t = re.split(r"[.!?\n]", t)[0]                      # 1ª frase
    t = re.sub(r"\b(produto|que|facilita|muito|essa|esse|isso|para|pra|com|de|do|da|"
               r"quer|o|a|comprar|link|na|bio|comentarios|comentários)\b", " ", t, flags=re.I)
    palavras = [p for p in re.findall(r"[A-Za-zÀ-ÿ]{3,}", t)]
    return " ".join(palavras[:5]).strip()


_PROMPT_GEMINI = (
    "Você é um extrator de produtos. Da legenda de um vídeo, devolva APENAS o "
    "nome curto do PRODUTO FÍSICO à venda (2 a 6 palavras, português, sem "
    "hashtag, emoji, marca ou aspas). REGRAS: se for receita, dica, frase "
    "motivacional, bastidores, ou se você não tiver CERTEZA do produto, responda "
    "exatamente NAO. Nunca invente, nunca explique, nunca escreva raciocínio nem "
    "a palavra THOUGHT — só o nome do produto ou NAO.\n\nLegenda: {desc}")

# termos que NÃO são produto (vazamento do Gemini, hooks gringos, genéricos)
_LIXO_TERMO = ("thought", "user wants", "product name", "aproveite", "promoç",
               "promoc", "oferta", "olha isso", "corre ", "bastidores", "receita",
               "pense", "silêncio", "silencio", "how ", "why ", "easy ", "more ",
               "quick ", "avoid ", "pov ", "your ", " store")


def _termo_valido(t: str) -> bool:
    tl = (t or "").lower().strip()
    if len(tl) < 3 or ":" in t or len(t.split()) > 6:
        return False
    if any(x in tl for x in _LIXO_TERMO):
        return False
    return bool(re.search(r"[A-Za-zÀ-ÿ]{3,}", t))


def _termo_gemini(desc: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or not desc:
        return ""
    prompt = _PROMPT_GEMINI.format(desc=desc[:500])

    def _limpa(t):
        t = (t or "").strip().strip('"').split("\n")[0].strip()
        return "" if t.upper().startswith("NAO") else t[:80]

    # SDK nova (google-genai). Rate-limit do free tier: espera e tenta de novo.
    import time as _t
    for tentativa in (1, 2):
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            resp = client.models.generate_content(
                model="gemini-2.5-flash", contents=[{"parts": [{"text": prompt}]}])
            return _limpa(resp.text)
        except Exception as e:
            s = str(e)
            if tentativa == 1 and ("429" in s or "RESOURCE_EXHAUSTED" in s
                                   or "quota" in s.lower()):
                _log("   Gemini rate-limit — espero 20s e tento de novo")
                _t.sleep(20)
                continue
            _log(f"   Gemini indisponível ({s[:50]}) — uso heurística")
            return ""
    return ""


def _identificar_produto(desc: str):
    """(termo, tem_juizo).

    tem_juizo diz se ALGUÉM avaliou que aquilo é produto. O Gemini avalia: o
    prompt manda responder NAO pra receita, dica, frase motivacional ou dúvida.
    O _termo_heuristico não avalia nada — ele corta a primeira frase da legenda,
    remove palavras funcionais do PORTUGUÊS e devolve as 5 primeiras que
    sobraram. Numa legenda em espanhol nenhuma dessas palavras casa, e a frase
    passa inteira:

        "Cosas que deberías hacer para mejorar tu apariencia 💅 #tips"
          -> 'Cosas deberías hacer mejorar apariencia'

    Os três nomes-lixo que estavam na fila em 03/08 saíram exatamente daí. O
    heurístico continua servindo pro caminho da Shopee, onde a busca e o
    _match_relevante checam o termo contra a realidade — mas não pode mais
    sustentar sozinho uma entrada na Amazon, que é só uma URL de busca.
    """
    t = _termo_gemini(desc)
    if t:
        return t, True
    return _termo_heuristico(desc), False


# adjetivos genéricos não contam como "parentesco" (senão 'Ventilador portátil'
# casa com 'Aquecedor Portátil' só pelo 'portátil')
_STOP_REL = {"portatil", "eletrico", "eletrica", "eletronico", "eletronica",
             "automatico", "automatica", "digital", "profissional", "grande",
             "pequeno", "pequena", "completo", "completa", "casual", "facil",
             "mini", "para", "com", "the", "and"}


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _match_relevante(termo: str, nome_produto: str) -> bool:
    """O produto que a Shopee devolveu tem que COMPARTILHAR pelo menos uma
    palavra significativa com o termo buscado. Mata o match falso ('silence' ->
    Camiseta, 'maravilhosa' -> Sandália): a Shopee sempre devolve ALGO, e sem
    essa trava o link vai pro produto errado."""
    def palavras(s):
        s = _sem_acento((s or "").lower())
        return {p for p in re.findall(r"[a-z0-9]{4,}", s)} - _STOP_REL
    t, n = palavras(termo), palavras(nome_produto)
    if not t:
        return False
    return bool(t & n)


def _baixar(url: str, destino: Path) -> Path | None:
    destino.mkdir(parents=True, exist_ok=True)
    saida = destino / "video.%(ext)s"
    r = _ytdlp(["-o", str(saida), "--no-playlist", "--no-warnings",
                "-f", "mp4/bv*+ba/b", url], timeout=300)
    if r.returncode != 0:
        _log(f"   download falhou: {(r.stderr or '')[:120]}")
        return None
    vids = list(destino.glob("video.*"))
    return vids[0] if vids else None


def _carregar_vistos() -> set:
    try:
        return set(json.loads(VISTOS.read_text(encoding="utf-8")).get("ids", []))
    except Exception:
        return set()


def _salvar_vistos(ids: set):
    try:
        VISTOS.parent.mkdir(parents=True, exist_ok=True)
        VISTOS.write_text(json.dumps({"ids": sorted(ids)}, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    except Exception:
        pass


# ── SAÚDE DAS FONTES: poda por COLETA (o 1º estágio do funil de fontes) ──────
# A descoberta joga largo (por nome), mas muita fonte é ZUMBI (conta morta de ~100
# views → tudo cai no filtro) ou IG que só dá 429. Aqui: fonte que não rende NENHUM
# vídeo aproveitável por N rodadas SEGUIDAS é comentada nos *_perfis.txt (reversível,
# não apaga). Trava: só penaliza numa rodada que PROVOU funcionar (rendeu ≥1 keeper
# em ALGUMA fonte) — se a rodada inteira flopou (rede/proxy caiu), ninguém é punido.
SAUDE_FONTES = BASE_DIR / "shared" / "fontes_saude.json"
COLETA_ZUMBI_RUNS = int(os.environ.get("COLETA_ZUMBI_RUNS", 3))     # rodadas 0-keeper p/ podar
IG_ROTACAO = BASE_DIR / "shared" / "ig_rotacao.json"               # janela rotativa de fontes IG


def _rotacionar_ig(perfis: list) -> list:
    """O IG estrangula (429) se a gente martela dezenas de perfis por rodada. Aqui
    a coleta processa no MÁXIMO IG_MAX_PERFIS_RUN perfis de IG por rodada, numa
    JANELA ROTATIVA — cobre todos ao longo de várias rodadas sem burst. TikTok passa
    inteiro (não estrangula assim)."""
    cap = int(os.environ.get("IG_MAX_PERFIS_RUN", 12))
    ig = [p for p in perfis if p[1] == "instagram"]
    outros = [p for p in perfis if p[1] != "instagram"]
    if cap <= 0 or len(ig) <= cap:
        return perfis
    try:
        st = json.loads(IG_ROTACAO.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    off = int(st.get("offset", 0)) % len(ig)
    sel = [ig[(off + i) % len(ig)] for i in range(cap)]
    st["offset"] = (off + cap) % len(ig)
    try:
        IG_ROTACAO.parent.mkdir(parents=True, exist_ok=True)
        IG_ROTACAO.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    _log(f"IG: {len(ig)} fontes → rodando {cap} nesta rodada (rotação, offset {off}); "
         f"TikTok: {len(outros)}")
    return outros + sel


def _norm_perfil(p: str) -> str:
    return (p or "").strip().lstrip("@").rstrip("/").lower().split("/")[-1]


def _ler_saude() -> dict:
    try:
        return json.loads(SAUDE_FONTES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _salvar_saude(d: dict):
    try:
        SAUDE_FONTES.parent.mkdir(parents=True, exist_ok=True)
        SAUDE_FONTES.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _comentar_fonte(perfil: str, fonte: str, motivo: str) -> bool:
    """Comenta a linha do perfil no arquivo certo (tiktok/instagram). Reversível:
    prefixa com '# ' + motivo, não apaga. Retorna True se comentou."""
    arq = IG_PERFIS_TXT if fonte == "instagram" else PERFIS_TXT
    if not arq.exists():
        return False
    alvo = _norm_perfil(perfil)
    linhas = arq.read_text(encoding="utf-8").splitlines()
    mudou = False
    for i, l in enumerate(linhas):
        ls = l.strip()
        if not ls or ls.startswith("#"):
            continue
        h = re.split(r"[\s#]", ls)[0].strip()
        if _norm_perfil(h) == alvo:
            linhas[i] = f"# {ls}   # {motivo}"
            mudou = True
    if mudou:
        arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return mudou


def _atualizar_saude_e_podar(perfis: list, keepers: dict, dry: bool):
    """Atualiza o contador de rodadas 0-keeper por fonte e poda os zumbis. Só roda
    de verdade (não-dry) e só se a rodada PROVOU funcionar (algum keeper no total)."""
    if dry:
        return
    auto = os.environ.get("COLETA_PODA_AUTO", "1").strip().lower() in ("1", "true", "sim")
    total_keepers = sum(keepers.values())
    if total_keepers <= 0:
        _log("saúde das fontes: rodada sem NENHUM keeper (rede/proxy?) — não penalizo "
             "ninguém desta vez.")
        return

    # ⚠️ A TRAVA GLOBAL NÃO COBRIA O CASO REAL (18/08). Ela só protege quando a
    # rodada INTEIRA dá zero. Só que as fontes vivem em dois canais com infra
    # diferente: TikTok (3 fontes, direto) e Instagram (83, via `IG_PROXY` +
    # Playwright). Com o proxy vencido, as 83 do IG dão zero e as 3 do TikTok
    # continuam rendendo — `total_keepers > 0`, a trava não dispara, e o
    # contador sobe para 83 fontes CURADAS de uma vez. Em `COLETA_ZUMBI_RUNS`
    # (3) rodadas elas são comentadas do arquivo.
    #
    # Foi exatamente o cenário de 18/08: proxy vencido há 3 dias, e o painel
    # mostrando **11 fontes a 1 rodada de podar**. A poda existe pra cortar
    # fonte que não rende; não pra converter uma pane de infraestrutura em
    # perda permanente de curadoria.
    #
    # A trava agora é POR CANAL: se NENHUMA fonte de um canal rendeu, o
    # problema é do canal, não das fontes dele.
    por_canal = defaultdict(int)
    fontes_do_canal = defaultdict(int)
    for perfil, fonte, _nf in perfis:
        k = _norm_perfil(perfil)
        if not k:
            continue
        fontes_do_canal[fonte] += 1
        por_canal[fonte] += keepers.get(k, 0)
    canais_mudos = {f for f, n in fontes_do_canal.items()
                    if n >= 3 and por_canal.get(f, 0) <= 0}
    for f in sorted(canais_mudos):
        _log(f"saúde das fontes: canal '{f}' deu ZERO keeper em "
             f"{fontes_do_canal[f]} fonte(s) — trato como pane do canal "
             f"(proxy/login/429), NÃO penalizo essas fontes.")

    saude = _ler_saude()
    hoje = time.strftime("%Y-%m-%d")
    podados = []
    for perfil, fonte, _nf in perfis:
        k = _norm_perfil(perfil)
        if not k:
            continue
        if fonte in canais_mudos:
            # ⚠️ não zera o contador: se o canal voltar e a fonte seguir muda,
            # ela continua de onde parou. Zerar aqui daria imunidade eterna a
            # quem sempre falha junto com o canal.
            continue
        s = saude.get(k) or {"zero_seguidas": 0, "fonte": fonte}
        s["fonte"] = fonte
        s["checado"] = hoje
        if keepers.get(k, 0) > 0:
            s["zero_seguidas"] = 0
            s["ultimo_ok"] = hoje
        else:
            s["zero_seguidas"] = int(s.get("zero_seguidas", 0)) + 1
            if auto and s["zero_seguidas"] >= COLETA_ZUMBI_RUNS:
                motivo = (f"ZUMBI-COLETA {hoje}: {s['zero_seguidas']} rodadas sem vídeo "
                          f"aproveitável (view baixa/429) — reative tirando este #")
                if _comentar_fonte(perfil, fonte, motivo):
                    podados.append(k)
        saude[k] = s
    _salvar_saude(saude)
    if podados:
        _log(f"🧹 poda por coleta: {len(podados)} fonte(s) zumbi comentada(s) "
             f"(reversível): {', '.join('@' + p for p in podados)}")


# ── Dedup por PRODUTO: o mesmo item (2 vídeos diferentes → mesmo produto) não
# vira 2 posts. Janela de DEDUP_DIAS: depois disso o produto pode voltar. ──
PRODUTOS_VISTOS = BASE_DIR / "shared" / "produtos_vistos.json"


def _norm_produto(nome: str) -> str:
    """Chave normalizada do produto: sem acento, minúsculo, 1as 8 palavras."""
    s = (nome or "").lower().translate(str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc"))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split()[:8])


def _carregar_produtos_vistos() -> dict:
    try:
        return dict(json.loads(PRODUTOS_VISTOS.read_text(encoding="utf-8")))
    except Exception:
        return {}


def _salvar_produtos_vistos(pv: dict):
    try:
        PRODUTOS_VISTOS.parent.mkdir(parents=True, exist_ok=True)
        PRODUTOS_VISTOS.write_text(json.dumps(pv, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    except Exception:
        pass


def _produto_repetido(chave: str, pv: dict) -> bool:
    """True se o produto já foi coletado dentro dos últimos DEDUP_DIAS dias."""
    if not chave:
        return False
    ts = pv.get(chave)
    if not ts:
        return False
    try:
        dias = int(os.getenv("DEDUP_DIAS", "30"))
    except ValueError:
        dias = 30
    return (time.time() - ts) < dias * 86400


def _fonte_do_arg(a: str) -> tuple:
    """Detecta a fonte de um perfil passado na linha de comando.
    'ig:@x' ou url do instagram → instagram; senão tiktok (compat)."""
    low = a.lower()
    if low.startswith("ig:") or low.startswith("instagram:"):
        return a.split(":", 1)[1].strip(), "instagram", ""
    if "instagram.com" in low:
        return a, "instagram", ""
    return a, "tiktok", ""


def _perfis_do_arquivo(caminho: Path, fonte: str) -> list:
    """Lê 1 perfil por linha. Nicho OPCIONAL via '#nicho' no fim da linha
    (ex.: '@bgbeautyloja #beleza') — o vídeo herda esse nicho na produção.
    Sem tag → nicho '' (aí a produção roteia pelo produto). Retorna
    (perfil, fonte, nicho)."""
    if not caminho.exists():
        return []
    out = []
    for l in caminho.read_text(encoding="utf-8").splitlines():
        l = l.strip()
        if not l or l.startswith("#"):
            continue
        nicho = ""
        m = re.search(r"#(\w+)\s*$", l)      # tag de nicho no fim: "@perfil #beleza"
        if m:
            nicho = m.group(1).lower()
            l = l[:m.start()].strip()
        out.append((l, fonte, nicho))
    return out


def _detectar_caixa(frames, thr_std=8.0, frac=0.06, pad=6):
    """Acha a caixa do conteúdo que SE MEXE (o vídeo do produto) dentro de uma
    moldura ESTÁTICA (borda + texto/@ do criador). frames: arrays HxW (cinza).
    Retorna (x0,y0,x1,y1) ou None se não houver caixa sã (aí não corta)."""
    import numpy as np
    stk = np.stack(frames).astype(np.float32)
    std = stk.std(axis=0)                       # quanto cada pixel varia no tempo
    mask = std > thr_std                         # pixels que "se mexem" = produto
    H, W = mask.shape
    ys = np.where(mask.mean(axis=1) > frac)[0]   # linhas com atividade
    xs = np.where(mask.mean(axis=0) > frac)[0]   # colunas com atividade
    if len(ys) < 4 or len(xs) < 4:
        return None
    y0, y1 = max(0, ys[0] - pad), min(H, ys[-1] + pad)
    x0, x1 = max(0, xs[0] - pad), min(W, xs[-1] + pad)
    w, h = x1 - x0, y1 - y0
    if w < W * 0.25 or h < H * 0.25 or (w * h) / float(W * H) > 0.985:
        return None                              # caixa degenerada → não corta
    return int(x0), int(y0), int(x1), int(y1)


def _auto_crop(video: Path) -> bool:
    """Gated AUTO_CROP=1. Corta a MOLDURA estática (borda/texto/@ do criador) e
    deixa só a janela do PRODUTO. Best-effort: sem caixa sã, mantém o vídeo inteiro.
    Bônus: se o @/marca do criador estava na borda, o corte já tira (o anti-watermark
    nem reclama). Roda ANTES do anti-watermark de propósito."""
    if os.getenv("AUTO_CROP", "0").strip().lower() not in ("1", "true", "sim"):
        return False
    try:
        import numpy as np
        from PIL import Image
    except Exception:
        _log("   (auto-crop: falta numpy/Pillow — pulo)")
        return False
    fpaths = []
    try:
        pr = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-show_entries", "format=duration",
             "-of", "json", str(video)], capture_output=True, text=True, timeout=30)
        info = json.loads(pr.stdout or "{}")
        st = (info.get("streams") or [{}])[0]
        W, H = int(st.get("width") or 0), int(st.get("height") or 0)
        dur = float((info.get("format") or {}).get("duration") or 0)
        if not (W and H):
            return False
        thr = float(os.getenv("AUTO_CROP_THR", "8"))
        frac = float(os.getenv("AUTO_CROP_FRAC", "0.06"))
        n, frames = 6, []
        for i in range(n):
            pos = max(0.1, dur * (i + 1) / (n + 1)) if dur else i * 0.5
            f = video.parent / f".crop_f{i}.jpg"
            fpaths.append(f)
            subprocess.run(["ffmpeg", "-y", "-ss", f"{pos:.2f}", "-i", str(video),
                            "-vframes", "1", "-vf", "scale=360:-2", "-q:v", "4", str(f)],
                           capture_output=True, timeout=30)
            if f.exists():
                frames.append(np.asarray(Image.open(f).convert("L"), dtype=np.uint8))
        if len(frames) < 3 or len({fr.shape for fr in frames}) != 1:
            return False
        hs, ws = frames[0].shape
        box = _detectar_caixa(frames, thr_std=thr, frac=frac)
        if not box:
            return False
        sx, sy = W / float(ws), H / float(hs)      # reescala p/ o tamanho real
        x0 = int(box[0] * sx) & ~1
        y0 = int(box[1] * sy) & ~1
        cw = max(2, int((box[2] - box[0]) * sx)) & ~1
        ch = max(2, int((box[3] - box[1]) * sy)) & ~1
        if cw < W * 0.25 or ch < H * 0.25 or x0 + cw > W or y0 + ch > H:
            return False
        out = video.with_suffix(".crop.mp4")
        r = subprocess.run(["ffmpeg", "-y", "-i", str(video),
                            "-vf", f"crop={cw}:{ch}:{x0}:{y0}", "-c:a", "copy", str(out)],
                           capture_output=True, text=True, timeout=180)
        if r.returncode == 0 and out.exists() and out.stat().st_size > 1000:
            out.replace(video)
            _log(f"   ✂️  auto-crop: moldura removida → {cw}x{ch} (era {W}x{H})")
            return True
        _log(f"   (auto-crop: ffmpeg falhou, mantém inteiro: {(r.stderr or '')[-100:]})")
        try:
            out.unlink()
        except Exception:
            pass
    except Exception as e:
        _log(f"   (auto-crop falhou, mantém inteiro: {str(e)[:70]})")
    finally:
        for f in fpaths:
            try:
                f.unlink()
            except Exception:
                pass
    return False


def _parse_args():
    """--dry, --limite N e perfis (ou tiktok_perfis.txt + instagram_perfis.txt).
    Retorna perfis como lista de (perfil, fonte)."""
    args = sys.argv[1:]
    dry = "--dry" in args
    limite = POR_PERFIL
    perfis = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--dry":
            i += 1
        elif a == "--limite" and i + 1 < len(args):
            try:
                limite = max(1, int(args[i + 1]))
            except ValueError:
                pass
            i += 2
        else:
            perfis.append(_fonte_do_arg(a))
            i += 1
    if not perfis:      # sem args → lê as duas listas (TikTok + Instagram)
        perfis = _perfis_do_arquivo(PERFIS_TXT, "tiktok") \
            + _perfis_do_arquivo(IG_PERFIS_TXT, "instagram")
    return dry, limite, perfis


def main():
    # modo calibração: testa o auto-crop num arquivo (força AUTO_CROP=1).
    #   python3 tiktok_coletor.py --crop-teste /caminho/video.mp4
    if "--crop-teste" in sys.argv:
        i = sys.argv.index("--crop-teste")
        alvo = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        if not alvo or not Path(alvo).exists():
            _log("uso: tiktok_coletor.py --crop-teste /caminho/video.mp4"); return 1
        os.environ["AUTO_CROP"] = "1"
        src = Path(alvo)
        cp = src.with_name(src.stem + "_cropTESTE" + src.suffix)
        shutil.copy2(src, cp)
        _log(f"testando auto-crop em cópia: {cp.name}")
        ok = _auto_crop(cp)
        _log(f"resultado: {'✂️ CORTOU (veja ' + cp.name + ')' if ok else 'não cortou (moldura não detectada / vídeo cheio)'}")
        return 0

    # modo diagnóstico: lista os reels de um perfil do IG (sem baixar nada).
    #   python3 tiktok_coletor.py --ig-teste promosda.alana
    if "--ig-teste" in sys.argv:
        i = sys.argv.index("--ig-teste")
        alvo = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        if not alvo:
            _log("uso: tiktok_coletor.py --ig-teste <perfil>"); return 1
        urls = _listar_ig_playwright(alvo, 8) or _listar_ig_instaloader(alvo, 8)
        for u in urls:
            _log(f"   • {u}")
        _log(f"{'✅ ' + str(len(urls)) + ' reels listados' if urls else '❌ 0 reels (confere cookies/instaloader)'}")
        return 0

    dry, limite, perfis = _parse_args()
    if not perfis:
        _log("sem perfis. Uso: python3 tiktok_coletor.py @tiktok1 ig:@insta1")
        _log("(ou crie tiktok_perfis.txt e/ou instagram_perfis.txt — 1 perfil por linha)")
        return 1

    perfis = _rotacionar_ig(perfis)      # limita/rotaciona IG p/ não tomar 429
    ig_delay = int(os.environ.get("IG_DELAY_SEG", 8))   # respiro entre perfis de IG

    vistos = _carregar_vistos()
    produtos_vistos = _carregar_produtos_vistos()
    achados = 0
    keepers = defaultdict(int)     # vídeos aproveitados por fonte (p/ poda por coleta)
    for perfil, fonte, nicho_fonte in perfis:
        _log(f"perfil {perfil} [{fonte}{'/' + nicho_fonte if nicho_fonte else ''}] …")
        if fonte == "instagram" and ig_delay > 0 and not dry:
            time.sleep(ig_delay)     # espaça os requests de IG (anti-429)
        for url in _listar_videos(perfil, limite, fonte):
            meta = _metadados(url)
            vid = meta.get("id")
            if not vid or vid in vistos:
                continue
            vistos.add(vid)      # marca cedo pra não repetir mesmo se descartar
            # views: só corta se for CONHECIDO e baixo. O yt-dlp às vezes não pega a
            # contagem do IG (vem 0) — aí a gente confia na curadoria do perfil.
            if (meta["views"] and meta["views"] < MIN_VIEWS) or \
               (meta["duracao"] and meta["duracao"] > MAX_DUR):
                _log(f"   • {vid}: fora do filtro (views={meta['views']}, "
                     f"dur={meta['duracao']}s) — pulo")
                continue
            pasta = INBOX / f"{_slug(meta['uploader'])}_{vid}"
            termo, termo_com_juizo = _identificar_produto(meta["descricao"])
            arq_pre = None
            # IG: a legenda é quase sempre um HOOK (curiosity-gap: "pouca gente imagina…"),
            # NÃO o produto — então a VISÃO (Gemini) é a autoridade. TikTok: a legenda
            # costuma nomear o produto, então a visão só entra se o texto falhar.
            usar_visao = _visao_ativa() and not dry and (
                fonte == "instagram" or not termo or not _termo_valido(termo))
            if usar_visao:
                arq_pre = _baixar(url, pasta)
                tv = (_termo_por_visao(arq_pre, meta.get("duracao") or 0,
                                       meta.get("descricao") or "") if arq_pre else "")
                if tv:
                    # a visão vence a legenda-hook — e ela é o Gemini olhando o
                    # frame, então tem o mesmo juízo que o extrator de legenda
                    termo, termo_com_juizo = tv, True
                elif fonte == "instagram":
                    termo = ""                        # IG sem visão: não confia no hook
            if not termo or not _termo_valido(termo):
                _log(f"   • {vid}: sem produto claro (legenda+visão) — pulo")
                if arq_pre:
                    shutil.rmtree(pasta, ignore_errors=True)
                continue
            _log(f"   • {meta['views']:,} views | produto: '{termo}'")

            m = minerar_oportunidades(termo)
            plataforma = "shopee"
            origem = ""      # URL original do produto (p/ re-etiquetar link por canal)
            if m.get("ok") and m.get("campeao"):
                camp = m["campeao"]
                if not _match_relevante(termo, camp.get("nome", "")):
                    _log(f"     ✗ match fraco ('{camp.get('nome','?')[:35]}' não bate "
                         f"com o termo) — descarto")
                    if arq_pre:
                        shutil.rmtree(pasta, ignore_errors=True)
                    continue
                origem = camp.get("product_link") or camp.get("offer_link")
                # sub_ids na ordem canônica [canal, nicho, produto, FONTE] — o índice 3
                # (fonte) é o que o CEO cruza com a venda p/ saber qual perfil converte.
                sub_termo = _subid(termo, "viral")
                sub_fonte = _subid(perfil, "")
                link = ""
                if origem:
                    lk = gerar_link_afiliado(origem, sub_ids=[
                        "tiktok", _subid(nicho_fonte, "geral"), sub_termo, sub_fonte])
                    if isinstance(lk, dict) and lk.get("ok"):
                        link = lk.get("short_link") or lk.get("link") or ""
                if not link:   # fallbacks: link já gerado pela mineração / offer cru
                    link = m.get("link_gerado") or camp.get("offer_link") or ""
                produto_nome = camp.get("nome", termo)
                imagem = camp.get("imagem", "")
                comissao = camp.get("comissao_valor", 0)
                _log(f"     ✓ Shopee: '{produto_nome[:45]}' | "
                     f"comissão R$ {comissao} | link: {link or '(falhou)'}")
            elif _amazon_ativo() and termo_com_juizo and _produto_pra_amazon(termo):
                # Shopee não tem → Amazon (link de busca afiliado, só a tag)
                plataforma = "amazon"
                produto_nome = termo
                imagem = ""
                comissao = 0
                link = _amazon_link(termo)
                _log(f"     ✓ Amazon (busca afiliada): {link}")
            else:
                if _amazon_ativo() and not termo_com_juizo:
                    motivo = " e o termo veio da heurística (ninguém checou que é produto)"
                elif _amazon_ativo():
                    motivo = " e sem Amazon"
                else:
                    motivo = " (gringo/Amazon?)"
                _log(f"     ✗ sem match na Shopee{motivo} — descarto")
                if arq_pre:
                    shutil.rmtree(pasta, ignore_errors=True)
                continue

            # dedup por PRODUTO: o mesmo item não entra 2x (dentro de DEDUP_DIAS)
            chave_prod = _norm_produto(produto_nome)
            if _produto_repetido(chave_prod, produtos_vistos):
                _log(f"     ⤵️  produto repetido ('{produto_nome[:38]}') — pulo (dedup)")
                if arq_pre:
                    shutil.rmtree(pasta, ignore_errors=True)
                continue
            achados += 1

            if dry:
                continue
            arq = arq_pre or _baixar(url, pasta)   # reusa o download da visão, se houve
            if not arq:
                continue
            # auto-crop: tira a moldura estática (borda/texto/@ do criador) e deixa
            # só a janela do produto. Roda ANTES do anti-watermark (o corte pode já
            # remover o @ que estava na borda).
            _auto_crop(arq)
            # anti-watermark: não reposta vídeo com marca d'água de terceiro (o
            # visual vazaria crédito, mesmo com a narração matando o áudio).
            if _tem_watermark(arq, meta.get("duracao") or 0):
                _log("     🚫 marca d'água detectada — descarto (não credita terceiro)")
                shutil.rmtree(pasta, ignore_errors=True)
                continue
            produtos_vistos[chave_prod] = int(time.time())   # só marca o que FICOU
            (pasta / "plano.json").write_text(json.dumps({
                "fonte": fonte, "nicho_fonte": nicho_fonte, "plataforma": plataforma,
                "perfil_fonte": perfil.lstrip("@").lower(),   # PERFIL curado (p/ CEO medir/podar)
                "url": meta["url"], "uploader": meta["uploader"],
                "views": meta["views"], "descricao": meta["descricao"],
                "termo": termo, "produto": produto_nome,
                "link_afiliado": link, "imagem": imagem,
                "origem_url": origem,      # URL original → produzir re-etiqueta por canal
                "comissao_valor": comissao,
                "video": str(arq),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            keepers[_norm_perfil(perfil)] += 1      # rendeu vídeo → fonte viva
            _log(f"     ⬇️  baixado em {pasta.name}/ [{plataforma}]")

    # no --dry NÃO persiste o cache (senão a rodada real pula tudo que o teste viu)
    if not dry:
        _salvar_vistos(vistos)
        _salvar_produtos_vistos(produtos_vistos)
    _atualizar_saude_e_podar(perfis, keepers, dry)   # poda por coleta (zumbis/429)
    _log(f"fim. {achados} produto(s) casado(s) na Shopee "
         f"{'(dry — nada baixado, cache intacto)' if dry else ''}")
    return 0


if __name__ == "__main__":
    # TRAVA DE INSTÂNCIA ÚNICA. Em 04/08/2026 o `crontab -l` tinha esta
    # mesma linha repetida (algumas 4x, o ceo_agent 8x) e as cópias rodaram
    # juntas o dia inteiro. shared/trava.py conta a história inteira.
    # Sem a trava disponível, roda como antes — ela protege, não bloqueia.
    try:
        from shared.trava import rodar_unico
    except Exception:
        sys.exit(main())
    sys.exit(rodar_unico("tiktok_coletor", main))
