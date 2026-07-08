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
POR_PERFIL = 8          # quantos vídeos recentes checar por perfil


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
    "Você recebe a legenda de um vídeo de achadinho. Responda APENAS com o nome "
    "curto do produto pra buscar na Shopee (2 a 6 palavras, português, sem "
    "hashtag, sem emoji, sem marca, sem aspas). Se a legenda for só um hook e não "
    "der pra saber QUAL é o produto, responda exatamente: NAO.\n\nLegenda: {desc}")


def _termo_gemini(desc: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or not desc:
        return ""
    prompt = _PROMPT_GEMINI.format(desc=desc[:500])

    def _limpa(t):
        t = (t or "").strip().strip('"').split("\n")[0].strip()
        return "" if t.upper().startswith("NAO") else t[:80]

    # SDK nova (google-genai) — a que o resto do projeto usa
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.5-flash", contents=[{"parts": [{"text": prompt}]}])
        return _limpa(resp.text)
    except Exception:
        pass
    # SDK antiga (google.generativeai) — fallback se a nova não estiver instalada
    try:
        import google.generativeai as _old
        _old.configure(api_key=api_key)
        resp = _old.GenerativeModel("gemini-1.5-flash").generate_content(prompt)
        return _limpa(getattr(resp, "text", ""))
    except Exception as e:
        _log(f"   Gemini indisponível ({str(e)[:50]}) — uso heurística")
        return ""


def _identificar_produto(desc: str) -> str:
    return _termo_gemini(desc) or _termo_heuristico(desc)


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


def _perfis_alvo() -> list:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        return args
    if PERFIS_TXT.exists():
        return [l.strip() for l in PERFIS_TXT.read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.strip().startswith("#")]
    return []


def main():
    dry = "--dry" in sys.argv[1:]
    perfis = _perfis_alvo()
    if not perfis:
        _log("sem perfis. Uso: python3 tiktok_coletor.py @perfil1 @perfil2")
        _log("(ou crie tiktok_perfis.txt com 1 perfil por linha)")
        return 1

    vistos = _carregar_vistos()
    achados = 0
    for perfil in perfis:
        _log(f"perfil {perfil} …")
        for url in _listar_videos(perfil, POR_PERFIL):
            meta = _metadados(url)
            vid = meta.get("id")
            if not vid or vid in vistos:
                continue
            vistos.add(vid)      # marca cedo pra não repetir mesmo se descartar
            if meta["views"] < MIN_VIEWS or (meta["duracao"] and meta["duracao"] > MAX_DUR):
                continue
            termo = _identificar_produto(meta["descricao"])
            if not termo:
                _log(f"   • {vid}: não identifiquei o produto (pulo)")
                continue
            _log(f"   • {meta['views']:,} views | produto: '{termo}'")

            m = minerar_oportunidades(termo)
            if not m.get("ok") or not m.get("campeao"):
                _log(f"     ✗ sem match na Shopee (gringo/Amazon?) — descarto")
                continue
            camp = m["campeao"]
            origem = camp.get("product_link") or camp.get("offer_link")
            lk = gerar_link_afiliado(origem, sub_ids=["tiktok", _slug(termo)]) if origem else {}
            link = lk.get("short_link", "") if isinstance(lk, dict) and lk.get("ok") else ""
            _log(f"     ✓ Shopee: '{camp.get('nome','?')[:45]}' | "
                 f"comissão R$ {camp.get('comissao_valor', 0)} | "
                 f"link: {link or '(falhou)'}")
            achados += 1

            if dry:
                continue
            pasta = INBOX / f"{_slug(meta['uploader'])}_{vid}"
            arq = _baixar(url, pasta)
            if not arq:
                continue
            (pasta / "plano.json").write_text(json.dumps({
                "fonte": "tiktok", "url": meta["url"], "uploader": meta["uploader"],
                "views": meta["views"], "descricao": meta["descricao"],
                "termo": termo, "produto": camp.get("nome", termo),
                "link_afiliado": link, "imagem": camp.get("imagem", ""),
                "comissao_valor": camp.get("comissao_valor", 0),
                "video": str(arq),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            _log(f"     ⬇️  baixado em {pasta.name}/")

    _salvar_vistos(vistos)
    _log(f"fim. {achados} produto(s) casado(s) na Shopee "
         f"{'(dry — nada baixado)' if dry else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
