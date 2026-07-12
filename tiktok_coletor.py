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
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PERFIS_TXT = BASE_DIR / "tiktok_perfis.txt"
VISTOS = BASE_DIR / "shared" / "tiktok_vistos.json"
INBOX = BASE_DIR / "inbox_tiktok"

MIN_VIEWS = 50_000      # só o que já provou tração
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
    return not any(p in _EN_WORDS for p in palavras)


def _amazon_link(termo: str) -> str:
    tag = os.getenv("AMAZON_TAG", "").strip()
    dom = os.getenv("AMAZON_DOMAIN", "amazon.com.br").strip() or "amazon.com.br"
    return f"https://www.{dom}/s?k={quote_plus(termo)}&tag={tag}"


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


def _ytdlp(args: list, timeout=120):
    return subprocess.run([*_resolver_ytdlp(), *args],
                          capture_output=True, text=True, timeout=timeout)


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return s[:40] or "video"


def _listar_videos(perfil: str, limite: int) -> list:
    """URLs dos vídeos mais recentes do perfil (sem baixar)."""
    url = perfil if perfil.startswith("http") else f"https://www.tiktok.com/@{perfil.lstrip('@')}"
    r = _ytdlp(["--flat-playlist", "-J", "--playlist-end", str(limite), url])
    try:
        d = json.loads(r.stdout)
        return [e.get("url") or f"https://www.tiktok.com/@x/video/{e.get('id')}"
                for e in (d.get("entries") or []) if e.get("id") or e.get("url")]
    except Exception:
        _log(f"   não consegui listar {perfil}: {(r.stderr or '')[:120]}")
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


def _identificar_produto(desc: str) -> str:
    return _termo_gemini(desc) or _termo_heuristico(desc)


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


def _parse_args():
    """--dry, --limite N e a lista de perfis (ou tiktok_perfis.txt)."""
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
            perfis.append(a)
            i += 1
    if not perfis and PERFIS_TXT.exists():
        perfis = [l.strip() for l in PERFIS_TXT.read_text(encoding="utf-8").splitlines()
                  if l.strip() and not l.strip().startswith("#")]
    return dry, limite, perfis


def main():
    dry, limite, perfis = _parse_args()
    if not perfis:
        _log("sem perfis. Uso: python3 tiktok_coletor.py @perfil1 @perfil2")
        _log("(ou crie tiktok_perfis.txt com 1 perfil por linha)")
        return 1

    vistos = _carregar_vistos()
    achados = 0
    for perfil in perfis:
        _log(f"perfil {perfil} …")
        for url in _listar_videos(perfil, limite):
            meta = _metadados(url)
            vid = meta.get("id")
            if not vid or vid in vistos:
                continue
            vistos.add(vid)      # marca cedo pra não repetir mesmo se descartar
            if meta["views"] < MIN_VIEWS or (meta["duracao"] and meta["duracao"] > MAX_DUR):
                continue
            termo = _identificar_produto(meta["descricao"])
            if not termo or not _termo_valido(termo):
                _log(f"   • {vid}: legenda sem produto claro (pulo)")
                continue
            _log(f"   • {meta['views']:,} views | produto: '{termo}'")

            m = minerar_oportunidades(termo)
            plataforma = "shopee"
            if m.get("ok") and m.get("campeao"):
                camp = m["campeao"]
                if not _match_relevante(termo, camp.get("nome", "")):
                    _log(f"     ✗ match fraco ('{camp.get('nome','?')[:35]}' não bate "
                         f"com o termo) — descarto")
                    continue
                origem = camp.get("product_link") or camp.get("offer_link")
                # sub_id SÓ alfanumérico (a Shopee rejeita _/-/etc → erro 11001)
                sub_termo = re.sub(r"[^A-Za-z0-9]", "", termo)[:16] or "viral"
                link = ""
                if origem:
                    lk = gerar_link_afiliado(origem, sub_ids=["tiktok", sub_termo])
                    if isinstance(lk, dict) and lk.get("ok"):
                        link = lk.get("short_link") or lk.get("link") or ""
                if not link:   # fallbacks: link já gerado pela mineração / offer cru
                    link = m.get("link_gerado") or camp.get("offer_link") or ""
                produto_nome = camp.get("nome", termo)
                imagem = camp.get("imagem", "")
                comissao = camp.get("comissao_valor", 0)
                _log(f"     ✓ Shopee: '{produto_nome[:45]}' | "
                     f"comissão R$ {comissao} | link: {link or '(falhou)'}")
            elif _amazon_ativo() and _produto_pra_amazon(termo):
                # Shopee não tem → Amazon (link de busca afiliado, só a tag)
                plataforma = "amazon"
                produto_nome = termo
                imagem = ""
                comissao = 0
                link = _amazon_link(termo)
                _log(f"     ✓ Amazon (busca afiliada): {link}")
            else:
                _log(f"     ✗ sem match na Shopee"
                     f"{' e sem Amazon' if _amazon_ativo() else ' (gringo/Amazon?)'}"
                     f" — descarto")
                continue
            achados += 1

            if dry:
                continue
            pasta = INBOX / f"{_slug(meta['uploader'])}_{vid}"
            arq = _baixar(url, pasta)
            if not arq:
                continue
            (pasta / "plano.json").write_text(json.dumps({
                "fonte": "tiktok", "plataforma": plataforma,
                "url": meta["url"], "uploader": meta["uploader"],
                "views": meta["views"], "descricao": meta["descricao"],
                "termo": termo, "produto": produto_nome,
                "link_afiliado": link, "imagem": imagem,
                "comissao_valor": comissao,
                "video": str(arq),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            _log(f"     ⬇️  baixado em {pasta.name}/ [{plataforma}]")

    # no --dry NÃO persiste o cache (senão a rodada real pula tudo que o teste viu)
    if not dry:
        _salvar_vistos(vistos)
    _log(f"fim. {achados} produto(s) casado(s) na Shopee "
         f"{'(dry — nada baixado, cache intacto)' if dry else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
