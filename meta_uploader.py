# agents/meta_uploader.py
# Uploader da Meta — posta no FACEBOOK e no INSTAGRAM via Graph API.
#
# Um módulo só cobre as duas plataformas porque ambas usam a mesma Graph API
# da Meta (mesmo app, mesmo token). As diferenças:
#
#   FACEBOOK (Página) → aceita upload de ARQUIVO LOCAL direto (mais simples).
#       Fluxo: POST /{page_id}/videos com o arquivo → pronto.
#
#   INSTAGRAM (Reels) → NÃO aceita arquivo direto no fluxo padrão; exige o
#       vídeo numa URL pública OU o fluxo "resumable" (rupload.facebook.com),
#       que aceita o binário direto sem hospedar nada. Usamos o resumable.
#       Fluxo: cria container resumable → sobe o binário → poll status →
#              publica o container.
#
# CREDENCIAIS (env vars — nunca no código):
#   META_ACCESS_TOKEN       token de longa duração (User ou Page)
#   FACEBOOK_PAGE_ID        ID numérico da Página do Facebook
#   INSTAGRAM_USER_ID       ID da conta Instagram Business (ig-user-id)
#
# Contrato de retorno (igual ao publish_guard espera):
#   {"sucesso": bool, "url"|"erro": str}
#
# Uso:
#   from agents.meta_uploader import postar_facebook, postar_instagram
#   r = postar_facebook(video_path, legenda)
#   r = postar_instagram(video_path, legenda)

import os
import json
import time
from pathlib import Path
from typing import Optional

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("meta_uploader")

try:
    import requests
    _REQUESTS_OK = True
except Exception:
    _REQUESTS_OK = False

GRAPH = "https://graph.facebook.com/v21.0"
RUPLOAD = "https://rupload.facebook.com/ig-api-upload/v21.0"

# Quanto esperar o container do Instagram processar antes de publicar
IG_POLL_INTERVALO = 6      # segundos entre checagens
IG_POLL_MAX = 60           # máx ~6min (60 x 6s) — vídeo grande demora


# ══════════════════════════════════════════════════════════════════════════
# SESSÃO HTTP — pooling de conexões + retry SÓ em GET (idempotente).
#
# IMPORTANTE: retry automático NÃO cobre POST de propósito. Reenviar um POST
# de publicação (criar vídeo no FB / media_publish no IG) que já chegou ao
# servidor mas cuja resposta se perdeu geraria POST DUPLICADO — dois vídeos.
# Então só GET (buscar token da página, poll de status, permalink) tem retry;
# os uploads/publish ficam com uma única tentativa, evitando duplicata.
# ══════════════════════════════════════════════════════════════════════════
def _build_session():
    """requests.Session com retry/backoff restrito a GET (nunca POST)."""
    if not _REQUESTS_OK:
        return None
    s = requests.Session()
    try:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        retry = Retry(
            total=3,
            connect=3,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),   # POST fora do retry: evita duplicar post
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
    except Exception:
        log.debug("Retry adapter indisponível; usando Session simples.")
    return s


_HTTP = _build_session()


def _req():
    """Retorna a Session compartilhada, ou o módulo requests como fallback."""
    return _HTTP if _HTTP is not None else requests


# ══════════════════════════════════════════════════════════════════════════
# CREDENCIAIS
# ══════════════════════════════════════════════════════════════════════════
# Conta ativa por vídeo (multi-conta): setada por postar_* a partir de um
# conta.json ao lado do video.mp4. Vazio => usa as vars globais do .env.
_CTX: dict = {}


def _ativar_conta(video_path) -> None:
    """Lê conta.json ao lado do vídeo e ativa a conta daquele nicho (ig_id,
    page_id, token). Sem conta.json, limpa o contexto (usa o .env global)."""
    _CTX.clear()
    try:
        cj = Path(video_path).parent / "conta.json"
        if not cj.exists():
            return
        c = json.loads(cj.read_text(encoding="utf-8"))
        env = c.get("page_token_env", "")
        tok = os.environ.get(env, "") if env else ""
        _CTX.update({
            "facebook_page_id":  str(c.get("facebook_page_id", "")).strip(),
            "instagram_user_id": str(c.get("instagram_user_id", "")).strip(),
            "token":             (tok or "").strip(),
            "handle":            c.get("handle", ""),
        })
        if _CTX.get("handle"):
            log.info(f"   🎯 conta ativa: {_CTX['handle']} (nicho {c.get('nicho', '?')})")
    except Exception:
        _CTX.clear()


def _token() -> str:
    return (_CTX.get("token") or os.environ.get("META_ACCESS_TOKEN", "")).strip()


def _page_id() -> str:
    return (_CTX.get("facebook_page_id") or os.environ.get("FACEBOOK_PAGE_ID", "")).strip()


def _ig_user_id() -> str:
    return (_CTX.get("instagram_user_id") or os.environ.get("INSTAGRAM_USER_ID", "")).strip()


def _checar_base() -> Optional[str]:
    """Retorna mensagem de erro se faltar algo essencial, senão None."""
    if not _REQUESTS_OK:
        return "lib 'requests' não instalada (pip install requests)"
    if not _token():
        return "META_ACCESS_TOKEN não configurado (env var)"
    return None


# ══════════════════════════════════════════════════════════════════════════
# PERMALINK — resolve a URL pública REAL de um objeto publicado
# ══════════════════════════════════════════════════════════════════════════
def _buscar_permalink(obj_id: str, campo: str, token: str, fallback: str) -> str:
    """
    Busca a URL pública REAL de um objeto publicado via Graph API.

    O id numérico que o publish retorna NÃO forma a URL pública: o Instagram
    usa um shortcode (ex: /reel/CxYz.../), não o media-id. Então consultamos
    o campo de permalink do objeto ('permalink' no IG, 'permalink_url' no FB).
    Se a consulta falhar por qualquer motivo, devolve o fallback informado.
    """
    try:
        r = _req().get(
            f"{GRAPH}/{obj_id}",
            params={"fields": campo, "access_token": token},
            timeout=30,
        )
        val = ((r.json() or {}).get(campo) or "").strip()
        if val:
            # FB às vezes devolve caminho relativo (/pagina/videos/123/)
            return val if val.startswith("http") else f"https://www.facebook.com{val}"
    except Exception as e:
        log.debug(f"   permalink ({campo}) indisponível: {e}")
    return fallback


# ══════════════════════════════════════════════════════════════════════════
# FACEBOOK — upload de arquivo local direto (simples)
# ══════════════════════════════════════════════════════════════════════════
def _page_access_token() -> Optional[str]:
    """
    Busca o token DA PÁGINA a partir do token de usuário.
    O Facebook exige o token da Página (não o de usuário) pra postar nela,
    mesmo com pages_manage_posts. Este token é derivado via /me/accounts.
    Retorna o token da página, ou None se não achar.
    """
    # 0) conta ativa (multi-conta) tem prioridade — token da página do nicho
    if _CTX.get("token"):
        return _CTX["token"]
    # 1) Se o usuário setou um token de página direto, usa ele
    direto = os.environ.get("FACEBOOK_PAGE_TOKEN", "").strip()
    if direto:
        return direto

    # 2) Deriva do token de usuário via /me/accounts
    try:
        r = _req().get(
            f"{GRAPH}/me/accounts",
            params={"access_token": _token(), "fields": "id,name,access_token"},
            timeout=30,
        )
        dados = r.json()
    except Exception as e:
        log.warning(f"   ⚠️  erro buscando token da página: {e}")
        return None

    paginas = dados.get("data") or []
    if not paginas:
        err = (dados.get("error") or {}).get("message") or "nenhuma página retornada"
        log.warning(f"   ⚠️  /me/accounts não retornou páginas: {err}")
        return None

    # Acha a página pelo FACEBOOK_PAGE_ID; se não bater, usa a primeira
    alvo = _page_id()
    for pag in paginas:
        if str(pag.get("id")) == alvo:
            tok = pag.get("access_token")
            if tok:
                log.info(f"   🔑 Token da página obtido ({pag.get('name', '?')})")
                return tok
    # fallback: primeira página
    tok = paginas[0].get("access_token")
    if tok:
        log.info(f"   🔑 Usando token da 1ª página ({paginas[0].get('name', '?')})")
    return tok


# ══════════════════════════════════════════════════════════════════════════
# ENGAJAMENTO — primeiro comentário automático (o "1º comentário" clássico)
#
# Logo após publicar, a máquina dropa o 1º comentário. Estratégia POR PLATAFORMA:
#   FACEBOOK  → link do produto (no FB o link em comentário é CLICÁVEL → venda)
#   INSTAGRAM → isca de engajamento (no IG link não clica; então "link na bio" +
#               pede comentário → gera sinal forte pro algoritmo)
# Gated por ENGAJAR_COMENTARIO=1. Best-effort: se falhar (ex: falta permissão),
# loga e segue — o post em si continua valendo.
# ══════════════════════════════════════════════════════════════════════════
_TMPL_IG = ("🛒 O link tá na BIO, corre pegar o seu! 😍\n"
            "💬 comenta \"EU QUERO\" que eu te ajudo a achar 👇")
_TMPL_FB = ("🛒 Compra aqui ó: {link}\n"
            "😍 aproveita que a oferta some rápido!")


def _engajar_ligado() -> bool:
    return os.environ.get("ENGAJAR_COMENTARIO", "0").strip().lower() in ("1", "true", "sim")


def _dados_engajamento(video_path) -> dict:
    """Lê engajamento.json ao lado do vídeo (link/produto/handle). {} se não houver."""
    try:
        ej = Path(video_path).parent / "engajamento.json"
        if ej.exists():
            return json.loads(ej.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _montar_comentario(plataforma: str, video_path) -> str:
    d = _dados_engajamento(video_path)
    ctx = {
        "link":    (d.get("link") or "").strip(),
        "handle":  (_CTX.get("handle") or d.get("handle") or "").strip(),
        "produto": (d.get("produto") or "").strip(),
    }
    tmpl = (os.environ.get("ENGAJAR_IG_TMPL", _TMPL_IG) if plataforma == "instagram"
            else os.environ.get("ENGAJAR_FB_TMPL", _TMPL_FB))
    # se o template precisa do {link} mas não temos, não comenta (evita "Compra aqui: ")
    if "{link}" in tmpl and not ctx["link"]:
        return ""
    try:
        return tmpl.format(**ctx).strip()
    except Exception:
        return ""


def _comentar(obj_id: str, texto: str, token: str) -> bool:
    """Posta o 1º comentário no objeto recém-publicado. Best-effort (nunca quebra)."""
    if not texto:
        return False
    try:
        r = _req().post(f"{GRAPH}/{obj_id}/comments",
                        data={"message": texto, "access_token": token}, timeout=30)
        d = r.json()
        if d.get("id"):
            log.info(f"   💬 1º comentário postado ({obj_id})")
            return True
        err = (d.get("error") or {}).get("message") or str(d)[:160]
        log.warning(f"   ⚠️  1º comentário não postou: {err}")
    except Exception as e:
        log.warning(f"   ⚠️  exceção no 1º comentário: {e}")
    return False


def postar_facebook(video_path: str, legenda: str = "") -> dict:
    """
    Posta um vídeo na Página do Facebook (upload de arquivo local).
    Usa o TOKEN DA PÁGINA (derivado do token de usuário automaticamente).
    Retorna {"sucesso", "url"|"erro"}.
    """
    _ativar_conta(video_path)
    erro_base = _checar_base()
    if erro_base:
        return {"sucesso": False, "erro": erro_base}
    if not _page_id():
        return {"sucesso": False, "erro": "FACEBOOK_PAGE_ID não configurado"}

    video = Path(video_path)
    if not video.exists():
        return {"sucesso": False, "erro": f"vídeo não encontrado: {video_path}"}

    # O Facebook exige o token DA PÁGINA pra postar nela
    page_token = _page_access_token()
    if not page_token:
        return {"sucesso": False,
                "erro": "não consegui obter o token da página (confere se o "
                        "token de usuário tem pages_show_list e se você é admin "
                        "da página)"}

    url = f"{GRAPH}/{_page_id()}/videos"
    log.info(f"   📘 Facebook: subindo '{video.name}' ({video.stat().st_size // 1024}KB)")
    try:
        with open(video, "rb") as f:
            files = {"source": f}
            data = {"description": legenda, "access_token": page_token}
            r = _req().post(url, data=data, files=files, timeout=300)
        dados = r.json()
    except Exception as e:
        return {"sucesso": False, "erro": f"exceção no upload: {e}"}

    # Sucesso = veio um id de vídeo
    video_id = dados.get("id")
    if video_id:
        # 1º comentário automático (FB: link clicável) — best-effort
        if _engajar_ligado():
            _comentar(video_id, _montar_comentario("facebook", video_path), page_token)
        # a URL pública real vem da permalink_url; fallback = watch?v= (válido
        # pra vídeo de feed, ao contrário do id solto que nem sempre resolve)
        link = _buscar_permalink(video_id, "permalink_url", page_token,
                                 f"https://www.facebook.com/watch/?v={video_id}")
        return {"sucesso": True, "url": link}
    # erro estruturado da Graph API
    err = (dados.get("error") or {}).get("message") or str(dados)[:200]
    return {"sucesso": False, "erro": f"Facebook recusou: {err}"}


# ══════════════════════════════════════════════════════════════════════════
# INSTAGRAM — Reels via resumable upload (sem hospedar nada)
# ══════════════════════════════════════════════════════════════════════════
def postar_instagram(video_path: str, legenda: str = "") -> dict:
    """
    Posta um Reel no Instagram Business via fluxo resumable:
      1. cria container (upload_type=resumable) → ig-container-id
      2. sobe o binário do vídeo pro rupload.facebook.com
      3. poll status do container até FINISHED
      4. publica o container
    Retorna {"sucesso", "url"|"erro"}.
    """
    _ativar_conta(video_path)
    erro_base = _checar_base()
    if erro_base:
        return {"sucesso": False, "erro": erro_base}
    if not _ig_user_id():
        return {"sucesso": False, "erro": "INSTAGRAM_USER_ID não configurado"}

    video = Path(video_path)
    if not video.exists():
        return {"sucesso": False, "erro": f"vídeo não encontrado: {video_path}"}

    ig = _ig_user_id()
    tok = _token()

    # ⚠️ REGISTRA O QUE VAI SER ENVIADO, ANTES DE ENVIAR (15/08).
    # 11 posts do @topshopcasa_ saíram sem legenda entre 10 e 15/08 e passei
    # uma tarde tentando DEDUZIR de artefato: pacote pendente, plano no disco,
    # ramo do publish_guard, data de commit. Duas hipóteses elegantes caíram
    # contra dado. E a razão de nenhuma fechar é simples: **ninguém anotou a
    # legenda que foi enviada**. O container é criado e a informação some.
    #
    # Uma linha de log responde na próxima postagem o que quatro rodadas de
    # inferência não responderam. Registra tamanho e começo — nunca o texto
    # inteiro, que polui o log e não acrescenta.
    _corte = (legenda or "").strip()
    log.info(f"   📝 legenda p/ Instagram: {len(_corte)} caractere(s)"
             + (f" · começa com {_corte.splitlines()[0][:60]!r}" if _corte
                else "  ⚠️ VAZIA — o Reel vai sair sem legenda"))

    # ── 1. Cria o container resumable ────────────────────────────────────
    try:
        r1 = _req().post(
            f"{GRAPH}/{ig}/media",
            data={
                "media_type": "REELS",
                "upload_type": "resumable",
                "caption": legenda,
                "access_token": tok,
            },
            timeout=60,
        )
        d1 = r1.json()
    except Exception as e:
        return {"sucesso": False, "erro": f"exceção criando container: {e}"}

    container_id = d1.get("id")
    if not container_id:
        err = (d1.get("error") or {}).get("message") or str(d1)[:200]
        return {"sucesso": False, "erro": f"container não criado: {err}"}

    log.info(f"   📸 Instagram: container {container_id} criado, subindo binário...")

    # ── 2. Sobe o binário pro rupload ────────────────────────────────────
    try:
        tam = video.stat().st_size
        with open(video, "rb") as f:
            r2 = _req().post(
                f"{RUPLOAD}/{container_id}",
                headers={
                    "Authorization": f"OAuth {tok}",
                    "offset": "0",
                    "file_size": str(tam),
                },
                data=f.read(),
                timeout=600,
            )
        d2 = r2.json()
    except Exception as e:
        return {"sucesso": False, "erro": f"exceção no upload binário: {e}"}

    if not d2.get("success"):
        err = d2.get("message") or str(d2)[:200]
        return {"sucesso": False, "erro": f"upload binário falhou: {err}"}

    log.info("   📸 Instagram: binário enviado, aguardando processamento...")

    # ── 3. Poll status até FINISHED ──────────────────────────────────────
    pronto = False
    for tentativa in range(IG_POLL_MAX):
        time.sleep(IG_POLL_INTERVALO)
        try:
            rs = _req().get(
                f"{GRAPH}/{container_id}",
                params={"fields": "status_code", "access_token": tok},
                timeout=30,
            )
            status = (rs.json() or {}).get("status_code", "")
        except Exception:
            continue
        if status == "FINISHED":
            pronto = True
            break
        if status == "ERROR":
            return {"sucesso": False, "erro": "container deu ERROR no processamento"}
        # IN_PROGRESS → continua esperando

    if not pronto:
        return {"sucesso": False, "erro": f"timeout esperando processar (container {container_id})"}

    # ── 4. Publica o container ───────────────────────────────────────────
    try:
        r4 = _req().post(
            f"{GRAPH}/{ig}/media_publish",
            data={"creation_id": container_id, "access_token": tok},
            timeout=60,
        )
        d4 = r4.json()
    except Exception as e:
        return {"sucesso": False, "erro": f"exceção publicando: {e}"}

    media_id = d4.get("id")
    if media_id:
        # 1º comentário automático (IG: isca de engajamento) — best-effort
        if _engajar_ligado():
            _comentar(media_id, _montar_comentario("instagram", video_path), tok)
        # o media-id numérico NÃO forma a URL do Reel (IG usa shortcode) —
        # busca a permalink real; fallback guarda ao menos o id de referência
        link = _buscar_permalink(media_id, "permalink", tok,
                                 f"https://www.instagram.com/reel/{media_id}")
        return {"sucesso": True, "url": link}
    err = (d4.get("error") or {}).get("message") or str(d4)[:200]
    return {"sucesso": False, "erro": f"publish recusado: {err}"}


# ══════════════════════════════════════════════════════════════════════════
# TESTE / DIAGNÓSTICO
# ══════════════════════════════════════════════════════════════════════════
def diagnostico() -> dict:
    """Checa o que está configurado, sem postar nada."""
    return {
        "requests_instalado": _REQUESTS_OK,
        "META_ACCESS_TOKEN":  "✅ ok" if _token() else "❌ faltando",
        "FACEBOOK_PAGE_ID":   "✅ ok" if _page_id() else "❌ faltando",
        "INSTAGRAM_USER_ID":  "✅ ok" if _ig_user_id() else "❌ faltando",
        "facebook_pronto":    bool(_token() and _page_id()),
        "instagram_pronto":   bool(_token() and _ig_user_id()),
        "ENGAJAR_COMENTARIO": "✅ ligado" if _engajar_ligado() else "⚪ desligado",
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Meta Uploader — Facebook + Instagram")
    parser.add_argument("--diagnostico", action="store_true",
                        help="checa credenciais sem postar")
    parser.add_argument("--facebook", help="caminho do vídeo pra postar no Facebook")
    parser.add_argument("--instagram", help="caminho do vídeo pra postar no Instagram")
    parser.add_argument("--legenda", default="Teste TopShop", help="legenda")
    args = parser.parse_args()

    print("=" * 60)
    print("  📱 META UPLOADER")
    print("=" * 60)

    if args.diagnostico:
        d = diagnostico()
        print("\n🔍 Diagnóstico de credenciais:")
        for k, v in d.items():
            print(f"   {k}: {v}")
    elif args.facebook:
        print(f"\n📘 Postando no Facebook: {args.facebook}")
        print(f"   → {postar_facebook(args.facebook, args.legenda)}")
    elif args.instagram:
        print(f"\n📸 Postando no Instagram: {args.instagram}")
        print(f"   → {postar_instagram(args.instagram, args.legenda)}")
    else:
        print("\nUse --diagnostico, --facebook <video> ou --instagram <video>")
    print("=" * 60)