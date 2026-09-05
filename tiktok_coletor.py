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
import math
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

# ── PISO DE VIEWS DO TIKTOK: 50.000 → 5.000 em 04/09/2026 ───────────────────
# Decisão do Dre: *"50k ta alto demais, pra nossa conta que ta pegando 1k 2k,
# o corte minimo pode ficar entre 5k"*.
#
# O argumento que sustenta não é a comparação com o alcance dele (são números
# de coisas diferentes: views do gringo no TikTok × alcance nosso no Reel). São
# estes dois:
#
#   1. SUPPLY É O GARGALO. 6 contas × 6 posts/dia. Nos 5 vídeos reais do
#      @seyis.shop (358 · 6.312 · 406 · 805.900 · 5.289) o piso de 50k deixava
#      passar UM (1/5). A 5k passam TRÊS (3/5) — triplica a fila desta fonte, e
#      o volume total vem das outras 43.
#   2. VIRALIDADE DA FONTE É PREDITOR FRACO — medido aqui, não suposto: o
#      `estudo_ganchos` mostrou o MESMO texto de gancho rendendo 1299 e 103 de
#      alcance (12×). Se o próprio gancho não prevê, views do vídeo de origem
#      preveem menos ainda. Filtrar duro por um sinal fraco é só perder fila.
#
# ⚠️ MUDEI O DEFAULT DO CÓDIGO, não só o `.env`. O roadmap já registra que "o
# .env vence o código" — o que também significa que, no dia em que a chave
# sumir do `.env` (edição à mão, VPS nova, restauração de backup), o piso
# voltaria calado pra 50k e a fila secaria sem ninguém entender por quê. Os
# dois alinhados é o que impede isso.
#
# ⚠️ O TIKTOK USA ESTE NÚMERO ABSOLUTO. O corte RELATIVO (`_melhores_do_perfil`,
# top N% de cada perfil) só roda no ramo do Instagram. Perfil pequeno e bom
# ainda pode dar zero — é o buraco do @topshoppet_. Se acontecer, a saída é
# estender o corte relativo pro TikTok, não zerar o piso.
MIN_VIEWS = 5_000       # min de views (override por MIN_VIEWS no .env — aplicado após _carregar_env)
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


def _termo_gringo(termo: str) -> bool:
    """O termo é legenda em inglês/espanhol em vez de nome de produto?

    ⚠️ ISTO DECIDE SE A VISÃO RODA (04/09/2026). Era usado só pra barrar link
    da Amazon; agora também abre o portão do Gemini Vision, e essa é a diferença
    entre perder o vídeo e produzir com ele.

    O que acontecia: no TikTok a visão só rodava se o termo fosse INVÁLIDO, e
    `'You can find this bye'` é válido — 5 palavras, só letras. A visão nunca
    rodava, o inglês virava "produto", não casava em marketplace nenhum e o
    vídeo morria. Numa rodada isso descartou centenas: 'smart gadgets unique
    accessories and', 'The Most Viral Gadget Must', 'Buy The Most Viral Gadget'.

    📌 E adicionar marketplace NÃO resolveria: não existe o que procurar. O
    defeito é de identificação, não de cobertura de loja.
    """
    palavras = re.findall(r"[a-zA-ZÀ-ÿ]+", (termo or "").lower())
    return any(p in _EN_WORDS or p in _ES_WORDS for p in palavras)


def _produto_pra_amazon(termo: str) -> bool:
    """Só monta link Amazon pra termo que PARECE produto pt-BR de verdade —
    rejeita se tiver qualquer palavra funcional/comida do inglês (o Gemini às
    vezes devolve legenda/hook gringo em vez de produto)."""
    if not termo or not _termo_valido(termo):
        return False
    palavras = re.findall(r"[a-zA-ZÀ-ÿ]+", termo.lower())
    if not (2 <= len(palavras) <= 8):
        return False
    return not _termo_gringo(termo)


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

# ── QUANTOS VÍDEOS VARRER POR PERFIL ─────────────────────────────────────────
# ⚠️ ISTO DEIXOU DE SER DETALHE EM 03/09. O Dre, sobre as 4 fontes novas:
# *"o bom delas é que podemos pegar vários vídeos antigos 2024/2025 que são
# bons e ainda prestam, diferente de vários perfis do instagram que só servia
# os mais recentes... agora podemos deixar vídeos por vários meses na produção"*.
#
# Os 40 do padrão eram calibrados pra fonte PERECÍVEL: varrer fundo não valia,
# porque vídeo velho daqueles perfis era ruim. Nestas 4 o acervo presta, e o
# `_melhores_do_perfil` fica com os melhores N% DE CADA PERFIL — então varrer
# 200 em vez de 40 não afrouxa o critério, só dá 5× mais candidatos pra ele
# escolher. É a diferença entre "o que saiu esta semana" e "meses de fila".
#
# Rodada de mineração de acervo (uma vez, demora):
#     .venv/bin/python tiktok_coletor.py --limite 200
# Ou fixo no .env, pra valer em toda rodada:
#     .venv/bin/python env_set.py POR_PERFIL 200
POR_PERFIL = int(os.environ.get("POR_PERFIL", POR_PERFIL))

# ⚠️ PISO SEPARADO PRO INSTAGRAM, NASCENDO EM 0 (DESLIGADO) — 19/08.
# O MIN_VIEWS de 50k nunca valeu pro IG: as views vinham 0 do yt-dlp e o
# filtro só corta quando o número é conhecido. Agora que a grade de reels
# entrega a contagem, ligar 50k de repente cortaria quase tudo e a coleta
# despencaria — trocar um defeito calado por outro. Escolha o número olhando
# a distribuição:  .venv/bin/python ig_playwright.py --diag-views <perfil>
MIN_VIEWS_IG = int(os.environ.get("MIN_VIEWS_IG", "0"))

# CORTE RELATIVO: fica com os melhores N% da grade de CADA perfil. É o que
# substitui o número absoluto — ver `_melhores_do_perfil` pro porquê, com os
# números dos dois perfis que provaram que absoluto não serve.
IG_TOP_FRACAO = float(os.environ.get("IG_TOP_FRACAO", "0.6"))
# abaixo desta amostra o ranking não significa nada (com 2 reels, "a mediana"
# é ruído), então não corta
IG_MIN_AMOSTRA = int(os.environ.get("IG_MIN_AMOSTRA", "4"))

# quanto CADA corte descartaria nesta rodada — impresso no fim, pra decidir o
# MIN_VIEWS_IG com número em vez de palpite
_FAIXAS_VIEWS = (1_000, 5_000, 10_000, 25_000, 50_000, 100_000)

# Perfis cuja LISTAGEM falhou nesta rodada (erro de rede/extrator/429), não
# perfis que listaram e não renderam. A poda tem de tratar os dois casos de
# formas opostas — ver `_atualizar_saude_e_podar`.
_falhou_listar: set = set()
_cortaria = defaultdict(int)
_sem_views = defaultdict(int)

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


def _melhores_do_perfil(itens: list, perfil: str) -> list:
    """Fica com os melhores N% da grade DESTE perfil. [(url, views)] → idem.

    ⚠️ POR QUE RELATIVO E NÃO UM NÚMERO FIXO (medido em 20/08)
    ─────────────────────────────────────────────────────────
    Os dois perfis que o Dre mandou diagnosticar responderam coisas opostas:

        @promosda.alana   12 reels · mediana  46.100 · maior 434.000
        @descontopets      2 reels · mediana     270 · maior     270

    Qualquer corte ABSOLUTO que sirva um destrói o outro:

        MIN_VIEWS_IG= 1.000 → alana 12/12 · pets 0/2
        MIN_VIEWS_IG=25.000 → alana  8/12 · pets 0/2

    E zerar o pets é justamente reabrir o buraco que a gente fechou hoje: o
    @topshoppet_ voltaria a ficar mudo, agora por filtro em vez de por
    roteador. Um reel de 270 views num perfil que faz 200 É o viral daquele
    perfil; um de 4.799 no alana, que faz 46 mil, é o fundo do poço dele.

    Por isso o corte é por POSIÇÃO, não por valor: fica com os melhores da
    grade de cada um. Isso não consegue esvaziar perfil nenhum — o topo sempre
    existe — e some sozinho quando a amostra é pequena demais pra significar
    algo (`IG_MIN_AMOSTRA`).

    ⚠️ views=0 é "não sei", nunca "não teve": esses passam sempre, como no
    resto do arquivo. Cortar por desconhecimento seria o mesmo erro de origem.
    """
    if IG_TOP_FRACAO <= 0 or IG_TOP_FRACAO >= 1:
        return itens
    conhecidos = [(u, v) for u, v in itens if v]
    desconhecidos = [(u, v) for u, v in itens if not v]
    if len(conhecidos) < IG_MIN_AMOSTRA:
        if conhecidos:
            _log(f"   (só {len(conhecidos)} view(s) conhecida(s) em @{perfil} — "
                 f"amostra pequena demais pra ranquear, levo todos)")
        return itens
    quantos = max(1, math.ceil(len(conhecidos) * IG_TOP_FRACAO))
    melhores = sorted(conhecidos, key=lambda x: -x[1])[:quantos]
    piso = melhores[-1][1]
    _log(f"   top {int(IG_TOP_FRACAO * 100)}% de @{perfil}: {quantos}/"
         f"{len(conhecidos)} reel(s), de {piso:,} views pra cima"
         + (f" · +{len(desconhecidos)} sem view conhecida" if desconhecidos else ""))
    return melhores + desconhecidos


def _listar_ig_playwright(perfil: str, limite: int) -> list:
    """[(url, views)] via NAVEGADOR real (Playwright + stealth) — contorna o bloqueio
    de API do instaloader. Reusa cookies (YTDLP_COOKIES) + proxy (IG_PROXY).

    ⚠️ AS VIEWS VÊM DAQUI, NÃO DO yt-dlp. Pro IG o `--skip-download -J` volta
    sem `view_count`, e o filtro de viralidade do coletor só corta quando o
    número é conhecido — então ele nunca cortava nada. Ver `listar_reels_detalhado`."""
    try:
        import ig_playwright
        return ig_playwright.listar_reels_detalhado(perfil, limite)
    except Exception as e:
        _log(f"   playwright indisponível ({str(e)[:70]})")
        return []


def _listar_videos(perfil: str, limite: int, fonte: str = "tiktok") -> list:
    """[(url, views_da_listagem)] dos vídeos mais recentes do perfil (sem baixar).

    TikTok via yt-dlp; Instagram via Playwright (navegador real) → instaloader →
    yt-dlp (fallbacks).

    ⚠️ Devolve TUPLA desde 19/08. Era só a URL, e as views ficavam por conta do
    `_metadados` — que pro IG volta 0 e desliga o filtro de viralidade sem
    ninguém notar. `views=0` aqui significa "não sei", nunca "não teve"."""
    if fonte == "instagram":
        # URL DIRETA de reel/post → não precisa listar; o yt-dlp baixa direto.
        low = perfil.lower()
        if perfil.startswith("http") and ("/reel/" in low or "/p/" in low or "/tv/" in low):
            return [(perfil, 0)]
        # 1) Playwright (navegador real) — com RETRY: o IG é flaky (vimos 0→12 reels
        #    no MESMO perfil sem trocar nada), então uma 2ª tentativa recupera muito.
        urls = _listar_ig_playwright(perfil, limite)
        if not urls:
            time.sleep(int(os.environ.get("IG_RETRY_SEG", 6)))
            urls = _listar_ig_playwright(perfil, limite)
        if urls:
            # ranqueia ANTES de devolver: cada vídeo que passa daqui custa
            # download + uma chamada de visão do Gemini, então filtrar cedo é
            # mais barato e é o que faz o sistema levar o melhor de cada fonte
            return _melhores_do_perfil(urls, _ig_username(perfil))
        # 2) instaloader (API) SÓ se explicitamente ligado. O fallback yt-dlp do IG
        #    dá 429 e QUEIMA o IP do proxy (foi o que estrangulou tudo) — desligado
        #    por padrão. IG_FALLBACK_YTDLP=1 religa o comportamento antigo.
        if os.environ.get("IG_FALLBACK_YTDLP", "0").strip().lower() in ("1", "true", "sim"):
            # o instaloader devolve só URL — views 0 = "não sei"
            urls = [(u, 0) for u in _listar_ig_instaloader(perfil, limite)]
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
            # o --flat-playlist do TikTok já traz view_count em muitos casos;
            # quando não traz, 0 e o _metadados resolve depois
            vw = int(e.get("view_count") or 0)
            u = e.get("url")
            if u:
                out.append((u, vw))
            elif e.get("id") and fonte == "tiktok":   # TikTok resolve id→url
                out.append((f"https://www.tiktok.com/@x/video/{e.get('id')}", vw))
        return out
    except Exception:
        # ⚠️ REGISTRA A FALHA DE LISTAGEM (04/09/2026). Sem isto a poda não
        # distingue "listei e não rendeu nada" de "nem consegui perguntar", e
        # trata as duas como rodada 0-keeper. Foi o que comentou o
        # @airlandolists — a MELHOR fonte da rodada anterior, ~50 vídeos —
        # depois de um erro de JSON do TikTok. Ver `_atualizar_saude_e_podar`.
        _falhou_listar.add(_norm_perfil(perfil))
        _log(f"   não consegui listar {perfil} [{fonte}]: {(r.stderr or '')[:120]}")
        return []


def _relatorio_views():
    """O que o filtro de viralidade FARIA, sem ter feito.

    Existe porque o corte do IG nasce desligado (ver MIN_VIEWS_IG) e alguém
    precisa escolher o número. Sem esta tabela a escolha seria palpite — e
    palpite alto zera a coleta, palpite baixo mantém o problema que o Dre
    apontou: meme recente ganhando de produto viral."""
    total = sum(_sem_views.values()) + max(_cortaria.values(), default=0)
    if not _cortaria and not _sem_views:
        return
    _log("— views nesta rodada —")
    for fonte, n in sorted(_sem_views.items()):
        _log(f"   {n} vídeo(s) de {fonte} SEM view conhecida "
             f"(esses nunca são cortados — 0 significa 'não sei')")
    if _cortaria:
        _log(f"   corte que CADA piso faria (MIN_VIEWS_IG hoje = {MIN_VIEWS_IG:,}):")
        for faixa in _FAIXAS_VIEWS:
            n = _cortaria.get(faixa, 0)
            if n:
                _log(f"     abaixo de {faixa:>7,} → descartaria {n} vídeo(s)")
    if not MIN_VIEWS_IG and _cortaria:
        _log("   ⚠️  o corte do IG está DESLIGADO. Escolha um piso olhando a "
             "tabela acima e ligue com:  python3 env_set.py MIN_VIEWS_IG 10000")


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


# ⚠️ "português" NÃO BASTOU (04/09/2026). O prompt já pedia português e o
# Gemini devolveu `Ice Bucket` de uma legenda em inglês — nome de produto certo,
# idioma errado. E "Ice Bucket" não acha NADA na Shopee nem na Amazon BR: o
# vídeo morria como se a loja não tivesse o produto, quando o produto é balde
# de gelo e existe às centenas.
#
# Desde que as fontes viraram 100% gringas isso deixou de ser exceção. Agora a
# tradução é INSTRUÇÃO EXPLÍCITA e com exemplo, porque "responda em português"
# um modelo lê como "não precisa traduzir nome próprio".
_PROMPT_GEMINI = (
    "Você é um extrator de produtos. Da legenda de um vídeo, devolva APENAS o "
    "nome curto do PRODUTO FÍSICO à venda (2 a 6 palavras, sem hashtag, emoji, "
    "marca ou aspas).\n"
    "IDIOMA: responda SEMPRE em português do Brasil. Se a legenda estiver em "
    "inglês ou espanhol, TRADUZA o nome do produto — não repita o termo "
    "estrangeiro. Ex.: 'ice bucket' → 'balde de gelo'; 'sticky lint roller' → "
    "'rolo tira-pelos'; 'cordless vacuum' → 'aspirador sem fio'.\n"
    "REGRAS: se for receita, dica, frase motivacional, bastidores, ou se você "
    "não tiver CERTEZA do produto, responda exatamente NAO. Nunca invente, "
    "nunca explique, nunca escreva raciocínio nem a palavra THOUGHT — só o nome "
    "do produto ou NAO.\n\nLegenda: {desc}")

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
             "mini", "para", "com", "the", "and",
             # ⚠️ MATERIAL E EMBALAGEM ENTRARAM EM 20/08 — foi o que deixou
             # passar o pior match da rodada do Dre:
             #
             #   termo  'Conjunto de Panelas de Aço Inoxidável'
             #   Shopee 'Kit De Sortimento De Arruela Plana De Aço Inoxidável'
             #
             # A trava pedia UMA palavra em comum de 4+ letras, e as duas
             # dividem "inoxidavel". Só que material não identifica produto:
             # panela e arruela são de aço inox do mesmo jeito. Com estas na
             # lista, a coincidência precisa cair no substantivo — 'panelas'
             # contra 'arruela' — e o link errado morre.
             #
             # O vídeo dizia panelas e o link vendia arruela. Isso é pior que
             # não ter link: queima o clique e a confiança de quem clicou.
             "inoxidavel", "inox", "aluminio", "plastico", "silicone",
             "metal", "metalico", "vidro", "ceramica", "madeira", "couro",
             "tecido", "algodao", "poliester", "borracha", "acrilico",
             "kit", "conjunto", "sortimento", "pacote", "unidades", "unidade",
             "pecas", "peca", "jogo", "combo",
             "original", "premium", "novo", "nova", "luxo", "super", "ultra",
             "qualidade", "resistente", "antiderrapante",
             "preto", "preta", "branco", "branca", "azul", "rosa", "verde",
             "vermelho", "vermelha", "dourado", "dourada", "prata", "cinza",
             # ⚠️ MODO DE FIXAÇÃO E DE FUNCIONAMENTO (21/08) — mesma família do
             # material. O log passou a dizer QUAL palavra aprovou cada match e
             # entregou o caso:
             #
             #   'organizador de cabos adesivo' ↳ casou por: adesivo
             #     → Shopee devolveu 'Suporte Secador De Cabelo Parede Adesivo'
             #
             # 'adesivo' descreve COMO gruda, não O QUE é. Organizador de cabo
             # e suporte de secador são adesivos do mesmo jeito, como panela e
             # arruela eram de aço inox. Comparar: os matches CERTOS da mesma
             # rodada casaram pelo substantivo — 'coleira', 'cama'.
             "adesivo", "adesiva", "magnetico", "magnetica", "retratil",
             "giratorio", "giratoria", "dobravel", "ajustavel", "recarregavel",
             "universal", "multiuso", "antiaderente", "impermeavel"}


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _palavras_rel(s):
    s = _sem_acento((s or "").lower())
    return {p for p in re.findall(r"[a-z0-9]{4,}", s)} - _STOP_REL


def _match_relevante(termo: str, nome_produto: str) -> bool:
    """O produto que a Shopee devolveu tem que COMPARTILHAR pelo menos uma
    palavra significativa com o termo buscado. Mata o match falso ('silence' ->
    Camiseta, 'maravilhosa' -> Sandália): a Shopee sempre devolve ALGO, e sem
    essa trava o link vai pro produto errado."""
    t = _palavras_rel(termo)
    if not t:
        return False
    return bool(t & _palavras_rel(nome_produto))


def _ponte_do_match(termo: str, nome_produto: str) -> str:
    """QUAL palavra aprovou este match. '' quando nenhuma.

    ⚠️ EXISTE PRA PARAR DE ADIVINHAR (21/08). A coleta de hoje aprovou coisas
    assim:

        'varinha mágica'                 → 'Kit 3 Blusas Infantil Menina…'
        'Suporte para banho de cachorro' → 'Naninha Para Bebê Antialérgica…'
        'focinheira de pato'             → 'Corrente P/Papagaio/Arara/Pato…'

    O vídeo mostra uma coisa e o link vende outra — pior que não ter link,
    porque queima o clique de quem confiou. Eu poderia inventar a próxima
    regra (substantivo-cabeça? posição? tamanho?), mas hoje três teorias minhas
    morreram contra dado, e nenhuma delas era sobre o que o log podia dizer.
    Então o log passa a dizer QUAL palavra fez a ponte, e a regra nasce da
    lista de pontes ruins em vez de sair da minha cabeça."""
    comuns = _palavras_rel(termo) & _palavras_rel(nome_produto)
    return ", ".join(sorted(comuns)[:4])


# sufixos que o yt-dlp usa pra arquivo INCOMPLETO
_PARCIAIS = (".part", ".ytdl", ".temp", ".tmp", ".download")


def _abre_o_primeiro_frame(v: Path) -> bool:
    """O frame 0 abre PELO MOVIEPY? Pega o que matou um pacote em 05/09:

        OSError: failed to read the first frame of video file

    ⚠️ TEM QUE SER O MOVIEPY, NÃO O FFMPEG. Minha primeira versão usava
    `ffmpeg -vframes 1` e ela aprovaria o pacote quebrado: uma varredura nos
    2693 vídeos do inbox deu 0 reprovados, incluindo o que tinha derrubado duas
    rodadas. O aviso original explica —

        1769472 bytes wanted but 0 bytes read at frame index 0   (=1024×576×3)

    o moviepy quer um frame inteiro de rawvideo pelo cano e recebe zero; o
    ffmpeg só quer "um frame decodificável" e consegue. Testar com ffmpeg era
    testar OUTRA COISA, parecida o bastante pra me enganar.

    ⚠️ NÃO checo o vídeo inteiro de propósito: custaria minutos por rodada, e o
    defeito visto mata no frame 0. Perder os últimos frames o moviepy contorna.
    """
    try:
        from moviepy.video.io.VideoFileClip import VideoFileClip
    except Exception:
        return True     # sem moviepy aqui? não é motivo pra jogar vídeo fora
    try:
        c = VideoFileClip(str(v))
        try:
            c.get_frame(0)
            return True
        finally:
            try:
                c.close()
            except Exception:
                pass
    except Exception:
        return False


def _baixar(url: str, destino: Path) -> Path | None:
    destino.mkdir(parents=True, exist_ok=True)
    saida = destino / "video.%(ext)s"
    try:
        r = _ytdlp(["-o", str(saida), "--no-playlist", "--no-warnings",
                    "-f", "mp4/bv*+ba/b", url], timeout=300)
    except subprocess.TimeoutExpired:
        # ⚠️ ANTES ISTO SUBIA COMO EXCEÇÃO e o yt-dlp morria deixando
        # 'video.mp4.part' em disco (05/09/2026).
        _log("   download estourou o tempo (300s) — limpando o parcial")
        _limpar_parciais(destino)
        return None
    if r.returncode != 0:
        _log(f"   download falhou: {(r.stderr or '')[:120]}")
        _limpar_parciais(destino)
        return None

    # ⚠️ 'video.*' CASA COM 'video.mp4.part'. O glob antigo adotava o arquivo
    # incompleto como se fosse o vídeo pronto, e ele seguia pra produção — o
    # mesmo padrão está no `_pendentes()` do produzir_tiktok.
    vids = [v for v in destino.glob("video.*")
            if not v.name.endswith(_PARCIAIS)]
    if not vids:
        _log("   download não deixou arquivo utilizável")
        _limpar_parciais(destino)
        return None

    v = vids[0]
    if not _abre_o_primeiro_frame(v):
        _log(f"   ⚠️ baixou mas não abre o 1º frame — descartando ({v.name})")
        try:
            v.unlink()
        except Exception:
            pass
        _limpar_parciais(destino)
        return None
    return v


def _limpar_parciais(destino: Path):
    """Tira os .part/.ytdl do caminho. Sem isto eles ficam na pasta e o glob
    do produtor os adota como vídeo."""
    for p in destino.glob("video.*"):
        if p.name.endswith(_PARCIAIS):
            try:
                p.unlink()
            except Exception:
                pass


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
        if k in _falhou_listar:
            # ⚠️ O BURACO QUE A TRAVA POR CANAL NÃO FECHAVA (04/09/2026).
            #
            # A trava por canal só protege quando o canal INTEIRO deu zero. Mas
            # o TikTok bloqueia INTERMITENTEMENTE: nesta rodada 5 perfis
            # renderam 157 produtos e ~25 levaram `Failed to parse JSON`. Como
            # o canal rendeu, a trava não disparou, e os que foram BLOQUEADOS
            # contaram rodada 0-keeper. Resultado: 12 fontes comentadas,
            # incluindo o @airlandolists — que na rodada anterior tinha sido a
            # MELHOR de todas, com ~50 vídeos.
            #
            # A distinção que faltava: "listei e não rendeu" é informação sobre
            # a FONTE; "não consegui listar" é informação sobre a REDE. Só a
            # primeira pode podar. Uma fonte que nem chegou a ser perguntada
            # não foi avaliada — penalizá-la é medir o meu proxy, não ela.
            #
            # Como na trava por canal, o contador NÃO zera: quem falha sempre
            # não ganha imunidade eterna, só não é punido por rodada em que o
            # TikTok não respondeu.
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
    if _falhou_listar:
        _log(f"saúde das fontes: {len(_falhou_listar)} fonte(s) NÃO PUDERAM SER "
             f"LISTADAS (erro de rede/extrator) — não avaliadas, não penalizadas: "
             f"{', '.join('@' + p for p in sorted(_falhou_listar))}")
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
    """Lê 1 perfil por linha. Nicho OPCIONAL via '#nicho' (ex.: '@loja #beleza')
    — o vídeo herda esse nicho na produção. Sem tag → nicho '' (aí a produção
    roteia pelo produto). Retorna (perfil, fonte, nicho).

    Também aceita `corte=N` (segundos de intro a pular, ex.: '@x #tech corte=2').
    Isso NÃO entra na tupla — vai pro `_CORTE_PERFIL`, porque a tupla de 3 é
    desempacotada em 5 lugares e mudar a aridade quebraria todos eles.
    As duas marcas valem em qualquer ordem."""
    if not caminho.exists():
        return []
    out = []
    for l in caminho.read_text(encoding="utf-8").splitlines():
        l = l.strip()
        if not l or l.startswith("#"):
            continue
        nicho, corte = "", 0.0
        # corte PRIMEIRO: se o #nicho saísse antes, um "corte=2" no fim da linha
        # deixaria de estar "no fim" pro regex do nicho — e vice-versa. Tirar as
        # duas marcas antes de sobrar o @ resolve a ordem.
        m = re.search(r"\bcorte\s*=\s*(\d+(?:[.,]\d+)?)", l, re.I)
        if m:
            try:
                corte = float(m.group(1).replace(",", "."))
            except ValueError:
                corte = 0.0
            l = (l[:m.start()] + " " + l[m.end():]).strip()
        m = re.search(r"#(\w+)\s*$", l)      # tag de nicho no fim: "@perfil #beleza"
        if m:
            nicho = m.group(1).lower()
            l = l[:m.start()].strip()
        if not l:
            continue                          # linha que só tinha marcações
        if corte > 0:
            _CORTE_PERFIL[_norm_perfil(l)] = corte
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


# ══════════════════════════════════════════════════════════════════════════
# CORTE DA INTRO — o gringo abre com carimbo ("Amazon Gadgets", nome do canal)
# e a AÇÃO DO PRODUTO só começa depois. No Reel o gancho é 1-3s (medido no
# estudo_ganchos), então 2s de carimbo alheio queima a janela INTEIRA que
# decide a retenção. Pedido do Dre em 03/09: "cortar os 2 primeiros segundos
# e já começar na ação do produto".
#
# A mesma ideia do `_detectar_caixa` (variância no tempo revela o que é
# conteúdo e o que é enfeite), só que no eixo do TEMPO em vez do espaço.
#
# ⚠️ SÓ RECONHECE CARIMBO PARADO. Intro ANIMADA (texto entrando, contagem) se
# mexe igual ao produto, e aí o detector devolve 0.0 — o vídeo sai inteiro.
# Isso é de propósito: a marcação manual `corte=N` no tiktok_perfis.txt existe
# justamente pra esses, e ganha do detector.

# perfil (normalizado) → segundos de corte fixo, lido do tiktok_perfis.txt.
# Dict de módulo em vez de 4º item da tupla: a tupla (perfil, fonte, nicho) é
# desempacotada em 5 lugares e mudar a aridade quebraria todos.
_CORTE_PERFIL: dict = {}


def _onde_comeca_acao(diffs: list, dt: float, base: float,
                      quieto: float = 0.35, minimo: float = 0.6) -> float:
    """DECISÃO PURA (sem ffmpeg, sem I/O) — por isso é testável.

    `diffs[i]` = quanto o frame i+1 mudou em relação ao i (0-255, escala de
    cinza). `dt` = intervalo entre frames. `base` = movimento TÍPICO do vídeo,
    medido no MEIO dele — é a régua: sem ela, um vídeo naturalmente paradão
    (produto no pedestal) seria lido como intro inteira.

    Devolve o segundo em que a ação começa, ou 0.0 quando não há o que cortar.
    """
    if base <= 0.5:
        return 0.0                    # vídeo inteiro parado → não sei dizer
    limiar = base * quieto
    i = 0
    while i < len(diffs) and diffs[i] < limiar:
        i += 1
    if i == 0:
        return 0.0                    # já abre se mexendo → nada a cortar
    if i >= len(diffs):
        return 0.0                    # janela toda parada → suspeito, não corto
    # `diffs[i-1]` quieto ⇒ frame[i-1] ≈ frame[i]: o carimbo dura até i*dt.
    # Corto EM i*dt e não em (i+1)*dt de propósito: sobrar 0,2s de carimbo é
    # inofensivo, comer o primeiro instante da ação não é.
    t = i * dt
    return round(t, 2) if t >= minimo else 0.0


def _frames_cinza(video: Path, inicio: float, dur: float, fps: float,
                  tag: str) -> list:
    """Extrai frames em UMA chamada de ffmpeg (filtro fps) e devolve arrays
    HxW em escala de cinza. Uma chamada por trecho, não uma por frame: são ~20
    frames e 20 processos custariam ~7s por vídeo."""
    import numpy as np
    from PIL import Image
    saida = video.parent / f".ci_{tag}_%03d.jpg"
    padrao = f".ci_{tag}_"
    try:
        subprocess.run(["ffmpeg", "-y", "-ss", f"{inicio:.2f}", "-t", f"{dur:.2f}",
                        "-i", str(video), "-vf", f"fps={fps:g},scale=240:-2",
                        "-q:v", "4", str(saida)], capture_output=True, timeout=60)
        arqs = sorted(p for p in video.parent.glob(f"{padrao}*.jpg"))
        out = []
        for p in arqs:
            try:
                out.append(np.asarray(Image.open(p).convert("L"), dtype=np.int16))
            except Exception:
                pass
        return out if len({a.shape for a in out}) <= 1 else []
    finally:
        for p in video.parent.glob(f"{padrao}*.jpg"):
            try:
                p.unlink()
            except Exception:
                pass


def _diffs(frames: list) -> list:
    import numpy as np
    return [float(np.abs(frames[i + 1] - frames[i]).mean())
            for i in range(len(frames) - 1)]


def _corte_intro(video: Path, dur: float, perfil: str = "") -> float:
    """Quantos segundos pular no começo. Ordem de autoridade:

       1. `corte=N` do tiktok_perfis.txt  → o Dre VIU o padrão, ganha de tudo
       2. CORTE_INTRO_AUTO=1              → detector (só carimbo parado)
       3. 0.0                             → vídeo inteiro

    Best-effort em toda falha: devolve 0.0 e o vídeo sai inteiro."""
    fixo = _CORTE_PERFIL.get(_norm_perfil(perfil), 0.0)
    teto = min(float(os.getenv("CORTE_INTRO_MAX", "4")), max(0.0, dur) * 0.25)
    sobra_min = float(os.getenv("CORTE_INTRO_SOBRA", "6"))

    def _cap(t: float, origem: str) -> float:
        """Nenhum corte pode roubar o vídeo: teto de 25% da duração e sobra
        mínima. Sem isso um clipe de 8s viraria 4s e o render alonga em loop."""
        if t <= 0:
            return 0.0
        if t > teto:
            _log(f"   (corte {origem} {t:.1f}s > teto {teto:.1f}s — uso o teto)")
            t = teto
        if dur and (dur - t) < sobra_min:
            _log(f"   (corte {origem}: sobrariam {dur - t:.1f}s < {sobra_min:.0f}s "
                 f"— não corto)")
            return 0.0
        return round(t, 2)

    if fixo > 0:
        t = _cap(fixo, f"fixo de @{perfil}")
        if t > 0:
            _log(f"   ✂️  intro: pulo {t:.1f}s (corte= do tiktok_perfis.txt)")
        return t

    if os.getenv("CORTE_INTRO_AUTO", "0").strip().lower() not in ("1", "true", "sim"):
        return 0.0
    if dur < sobra_min + 1:
        return 0.0
    try:
        import numpy  # noqa: F401  (só pra falhar cedo e com mensagem clara)
        from PIL import Image  # noqa: F401
    except Exception:
        _log("   (corte-intro: falta numpy/Pillow — pulo)")
        return 0.0
    try:
        fps = float(os.getenv("CORTE_INTRO_FPS", "5"))
        dt = 1.0 / fps
        janela = min(float(os.getenv("CORTE_INTRO_JANELA", "4")), teto + dt)
        ini = _frames_cinza(video, 0.0, janela, fps, "ini")
        # a RÉGUA vem do meio do vídeo, onde a ação já está rolando
        meio = _frames_cinza(video, max(0.0, dur * 0.5), 1.0, fps, "mid")
        if len(ini) < 3 or len(meio) < 3:
            return 0.0
        dmeio = _diffs(meio)
        base = sorted(dmeio)[len(dmeio) // 2]        # mediana = régua robusta
        t = _onde_comeca_acao(_diffs(ini), dt, base)
        t = _cap(t, "auto")
        if t > 0:
            _log(f"   ✂️  intro: pulo {t:.1f}s (carimbo parado detectado; "
                 f"movimento típico {base:.1f})")
        return t
    except Exception as e:
        _log(f"   (corte-intro falhou, vídeo inteiro: {str(e)[:70]})")
        return 0.0


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
        for url, views_listagem in _listar_videos(perfil, limite, fonte):
            meta = _metadados(url)
            vid = meta.get("id")
            if not vid or vid in vistos:
                continue
            vistos.add(vid)      # marca cedo pra não repetir mesmo se descartar

            # a listagem sabe mais que o yt-dlp no IG: lá o view_count não vem
            if not meta.get("views") and views_listagem:
                meta["views"] = views_listagem

            # ⚠️ O CORTE DO IG É SEPARADO E NASCE DESLIGADO (MIN_VIEWS_IG=0).
            # Até 19/08 o `MIN_VIEWS=50_000` não filtrava NADA no Instagram,
            # porque views vinha 0 e a condição `if (meta["views"] and ...)` é
            # falsa com zero. Agora que a view existe, ligar 50k de uma vez
            # poderia cortar quase tudo e a coleta cairia pra perto de zero —
            # trocar um defeito silencioso por outro. Então: ele CONTA quantos
            # cortaria em cada faixa e só corta quando alguém escolher o número
            # olhando a distribuição real (ig_playwright.py --diag-views).
            piso = MIN_VIEWS_IG if fonte == "instagram" else MIN_VIEWS
            if meta["views"]:
                for faixa in _FAIXAS_VIEWS:
                    if meta["views"] < faixa:
                        _cortaria[faixa] += 1
            else:
                _sem_views[fonte] += 1

            if (piso and meta["views"] and meta["views"] < piso) or \
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
            # ⚠️ O 4º CASO ENTROU EM 04/09 E É O QUE SALVA AS FONTES GRINGAS.
            #
            # Antes: `instagram OR termo vazio OR termo inválido`. Faltava o
            # caso MAIS COMUM do TikTok gringo — termo VÁLIDO que é legenda em
            # inglês: 'You can find this bye', 'smart gadgets unique accessories
            # and', 'The Most Viral Gadget Must'. Válido passava, a visão não
            # rodava, e o vídeo morria sem NUNCA ter sido olhado. Numa só rodada
            # foram centenas — de fontes que o Dre classificou como as melhores.
            #
            # 📌 O SINAL CERTO É `termo_com_juizo`, NÃO UMA LISTA DE PALAVRAS.
            # Tentei primeiro casar inglês por vocabulário (`_termo_gringo`) e
            # medi: pegou 10 de 17 casos reais ('Fall centerpiece idea' e
            # 'Genius unnecessary' escaparam) e ainda deu falso positivo em
            # 'Mop de limpeza' — porque "mop" está na lista de inglês. Lista de
            # palavras nunca vai cobrir legenda livre.
            #
            # `termo_com_juizo=False` significa que o termo veio da HEURÍSTICA
            # (regex na legenda) e ninguém checou que é produto — é exatamente
            # a frase que o log imprimia em cada descarte. Cobre 100% dos casos,
            # sem vocabulário pra manter.
            #
            # CUSTO: mais download + chamada de visão. É o troco certo — supply
            # é o gargalo, e a alternativa era jogar o vídeo fora. Desligue com
            # VISAO_SEM_JUIZO=0 se a fatura do Gemini pesar.
            _visao_sem_juizo = (os.getenv("VISAO_SEM_JUIZO", "1").strip().lower()
                                in ("1", "true", "sim"))
            # ⚠️ E O `_termo_gringo` VOLTOU — aqui ele serve (04/09).
            # Eu tinha descartado ele como portão por ter pegado só 10 de 17 e
            # dado falso positivo em 'Mop de limpeza'. Mas ele cobre um caso que
            # o `termo_com_juizo` NÃO cobre: o Gemini APROVAR um termo e ainda
            # assim devolver inglês ('Ice Bucket'). Aí `com_juizo=True` e o
            # termo não é duvidoso pela regra nova — mas nenhuma loja brasileira
            # vai achar.
            #
            # A assimetria de custo é o que autoriza usá-lo aqui e não no link
            # da Amazon: falso positivo aqui = UMA chamada de visão a mais
            # (o Dre: "temos dinheiro suficiente para colocar no gemini"); lá
            # = um produto bom rejeitado pra sempre.
            #
            # ⚠️ ESTA REDE TEM BURACO CONHECIDO, e é de propósito. `_EN_WORDS` é
            # lista de palavras FUNCIONAIS, não dicionário: 'Ice Bucket' cai
            # (por "ice"), mas 'Sticky Lint Roller' PASSA — nenhuma das três
            # está lá. Medido, não suposto.
            #
            # Não fechei o buraco com "termo sem acento e sem 'de' é gringo"
            # porque isso dispararia em 'Lixeira inteligente', 'Perfume',
            # 'Blush compacto' — metade dos produtos pt-BR curtos — e cada
            # disparo é um DOWNLOAD a mais, não só uma chamada de API.
            # A defesa principal é o prompt (que agora manda TRADUZIR); esta
            # aqui é a segunda linha, e segunda linha com buraco conhecido é
            # melhor que primeira linha cara.
            _duvidoso = bool(termo) and _visao_sem_juizo and (
                not termo_com_juizo or _termo_gringo(termo))
            usar_visao = _visao_ativa() and not dry and (
                fonte == "instagram" or not termo or not _termo_valido(termo)
                or _duvidoso)
            if usar_visao and _duvidoso:
                _pq = ("veio em inglês/espanhol" if termo_com_juizo
                       else "saiu da heurística, ninguém checou")
                _log(f"   🔍 '{termo[:40]}' {_pq} — chamo a visão "
                     f"em vez de arriscar")
            if usar_visao:
                arq_pre = _baixar(url, pasta)
                tv = (_termo_por_visao(arq_pre, meta.get("duracao") or 0,
                                       meta.get("descricao") or "") if arq_pre else "")
                if tv:
                    # a visão vence a legenda-hook — e ela é o Gemini olhando o
                    # frame, então tem o mesmo juízo que o extrator de legenda
                    termo, termo_com_juizo = tv, True
                elif fonte == "instagram" or _duvidoso:
                    # a visão OLHOU e não achou produto. O termo da heurística
                    # já era suspeito (foi ele que chamou a visão), então
                    # mantê-lo só produziria busca de marketplace com legenda
                    # em inglês — e um log que culpa a loja por um defeito de
                    # identificação. Zera: o descarte sai como "legenda+visão".
                    termo = ""
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
                _ponte = _ponte_do_match(termo, produto_nome)
                _log(f"     ✓ Shopee: '{produto_nome[:45]}' | "
                     f"comissão R$ {comissao} | link: {link or '(falhou)'}")
                # a palavra que aprovou o match, sempre — é ela que vai
                # mostrar qual regra falta, sem eu ter que adivinhar
                _log(f"       ↳ casou por: {_ponte or '(?)'}")
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
            # onde a AÇÃO começa. Medido aqui (o vídeo cru está na mão e o
            # ffmpeg é barato) e APLICADO no render — assim o número fica
            # gravado no plano.json e dá pra auditar/sobrescrever depois.
            corte_ini = _corte_intro(arq, float(meta.get("duracao") or 0), perfil)
            produtos_vistos[chave_prod] = int(time.time())   # só marca o que FICOU
            (pasta / "plano.json").write_text(json.dumps({
                "corte_inicio": corte_ini,
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
    _relatorio_views()
    if dry and any(f == "instagram" for _, f, _ in perfis):
        # ⚠️ O --dry NÃO É PRÉVIA FIEL PRO INSTAGRAM, e isso enganou o Dre (e
        # a mim) em 20/08. A visão só roda quando `not dry`:
        #
        #     usar_visao = _visao_ativa() and not dry and (...)
        #
        # e pro IG a legenda é HOOK, não produto. Sem visão, o termo cai na
        # heurística de legenda e sai lixo — 'THRU', 'VQJN', 'amo HVSZ',
        # 'Wait Iron Man core can'. Numa rodada de verdade esses vídeos ou
        # ganham nome de produto pela visão, ou são descartados (`termo = ""`).
        # Nenhum deles viraria post com esse nome.
        _log("⚠️  --dry: a VISÃO não roda, então os nomes de produto do "
             "Instagram vieram da legenda (que é hook) e saem tortos de "
             "propósito. Numa rodada real a visão nomeia ou descarta. Use o "
             "--dry pra ver VIEWS e FONTES, não pra julgar nome de produto.")
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
