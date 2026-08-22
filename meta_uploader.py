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
    # ⚠️ E DIZ QUAL CONTA (21/08). A linha acima provou que a legenda SEMPRE é
    # enviada — 500 a 950 caracteres, nenhuma vazia. E mesmo assim o
    # @topshopcasa_ publicou 2 Reels recentes sem legenda, enquanto as outras
    # 3 contas saíram certas. Ou seja: o problema é DE UMA CONTA, e o log não
    # dizia de qual conta era cada linha — então não dava pra separar "a casa
    # mandou e a Meta descartou" de "a casa nem passou por aqui".
    #
    # `_CTX` é o contexto que o daemon monta por conta antes de postar; se ele
    # vier vazio, o upload cai nas env vars globais — e aí TODA postagem iria
    # pro mesmo perfil, o que é outro problema e este log também revela.
    _corte = (legenda or "").strip()
    _quem = (_CTX.get("handle") or _CTX.get("nicho")
             or f"ig_user_id={_ig_user_id()[-6:] or '?'}")
    log.info(f"   📝 legenda p/ Instagram [{_quem}]: {len(_corte)} caractere(s)"
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
# CARROSSEL E STORY — os dois formatos que faltavam (22/08)
#
# ⚠️ POR QUE ESTE BLOCO NÃO REAPROVEITA `postar_instagram` ACIMA.
# Aquela função é a única coisa deste arquivo que está publicando de verdade,
# em 6 contas, todo dia. Refatorar ela pra extrair helpers deixaria o deploy
# DIVERGENTE num arquivo em produção — que é exatamente o cenário que o
# `deploy_seguro.py` manda tratar cirurgicamente. Então os helpers abaixo são
# NOVOS e só o código novo os usa; `postar_instagram` fica byte a byte igual.
# O preço é ~20 linhas parecidas com as de lá. É barato pelo que compra.
#
# ⚠️ A REGRA QUE DECIDE O DESENHO (doc oficial da Meta, conferida 22/08):
#   VÍDEO  → binário direto no rupload (nada precisa ser hospedado)
#   IMAGEM → SÓ `image_url`; "we cURL media used in publishing attempts"
# Logo: story de VÍDEO funciona sem infra nenhuma. Carrossel e story de IMAGEM
# exigem host público — é o que `midia_publica.py` resolve.
#
# Limites que a Meta impõe e que a gente respeita aqui:
#   · carrossel: 2 a 10 filhos; a legenda vai no PAI, nunca nos filhos
#   · todos os slides são cortados pela proporção do PRIMEIRO — renderize
#     todos no mesmo tamanho ou o corte come o texto dos outros
#   · story de vídeo: até 60s
#   · 100 posts publicados por API em 24h por conta (o carrossel conta como 1)
# ══════════════════════════════════════════════════════════════════════════
_IMAGENS = (".jpg", ".jpeg", ".png", ".webp")
_VIDEOS = (".mp4", ".mov")
STORY_MAX_SEG = 60


def _e_imagem(p) -> bool:
    return Path(p).suffix.lower() in _IMAGENS


def _garantir_jpeg(origem: Path) -> Path:
    """Devolve um caminho JPEG. Converte se vier PNG/WEBP.

    ⚠️ A DOC É CATEGÓRICA E ISTO NÃO DÁ AVISO NENHUM SE FOR IGNORADO:
    "JPEG is the only image format supported. Extended JPEG formats such as
    MPO and JPS are not supported."  Mandar um PNG não devolve "formato
    inválido" — devolve o mesmo `ERROR` genérico de container que qualquer
    outro problema devolve. Converter aqui é mais barato que descobrir isso
    olhando log.

    O PNG do render tem canal alfa; achatar contra BRANCO é a escolha certa
    porque o template das contas novas já é branco — sobre preto apareceria
    uma borda clara em volta do texto."""
    if origem.suffix.lower() in (".jpg", ".jpeg"):
        return origem
    try:
        from PIL import Image
    except Exception:
        log.warning(f"   ⚠️  {origem.name} não é JPEG e o Pillow não está aqui "
                    "pra converter — a Meta provavelmente vai recusar")
        return origem
    destino = origem.with_suffix(".jpg")
    try:
        img = Image.open(origem)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            fundo = Image.new("RGB", img.size, (255, 255, 255))
            fundo.paste(img, mask=img.split()[-1])
            img = fundo
        else:
            img = img.convert("RGB")
        img.save(destino, "JPEG", quality=92, optimize=True)
        log.info(f"   🔄 {origem.name} → JPEG (único formato que a Meta aceita)")
        return destino
    except Exception as e:
        log.warning(f"   ⚠️  não converti {origem.name} pra JPEG ({e})")
        return origem


def _dur_segundos(arquivo) -> float:
    """Duração via ffprobe. 0.0 quando não dá pra saber (nunca levanta)."""
    import subprocess
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(arquivo)],
            capture_output=True, text=True, timeout=30)
        return float((r.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def _criar_container(ig: str, tok: str, campos: dict) -> tuple:
    """POST /{ig}/media. Devolve (container_id, erro)."""
    try:
        d = _req().post(f"{GRAPH}/{ig}/media",
                        data={**campos, "access_token": tok}, timeout=60).json()
    except Exception as e:
        return "", f"exceção criando container: {e}"
    cid = d.get("id")
    if cid:
        return cid, ""
    return "", ((d.get("error") or {}).get("message") or str(d)[:200])


def _subir_binario(container_id: str, arquivo: Path, tok: str) -> str:
    """Sobe o binário pro rupload. Devolve "" se OK, ou a mensagem de erro."""
    try:
        with open(arquivo, "rb") as f:
            d = _req().post(
                f"{RUPLOAD}/{container_id}",
                headers={"Authorization": f"OAuth {tok}", "offset": "0",
                         "file_size": str(arquivo.stat().st_size)},
                data=f.read(), timeout=600).json()
    except Exception as e:
        return f"exceção no upload binário: {e}"
    return "" if d.get("success") else (d.get("message") or str(d)[:200])


def _esperar_container(container_id: str, tok: str, tentativas: int,
                       intervalo: float, exigir_finished: bool = True) -> str:
    """Poll do status_code. "" se ficou pronto, senão a mensagem de erro.

    ⚠️ `exigir_finished=False` pros FILHOS DE CARROSSEL de imagem: container de
    imagem costuma nascer pronto e a Meta às vezes nem devolve `status_code`.
    Exigir FINISHED ali significaria esperar 6 minutos por um campo que nunca
    vem, e depois desistir de um container que estava perfeito."""
    for _ in range(max(1, tentativas)):
        try:
            st = (_req().get(f"{GRAPH}/{container_id}",
                             params={"fields": "status_code", "access_token": tok},
                             timeout=30).json() or {}).get("status_code", "")
        except Exception:
            st = ""
        if st == "FINISHED":
            return ""
        if st == "ERROR":
            return f"container {container_id} deu ERROR no processamento"
        if not st and not exigir_finished:
            return ""          # sem status = imagem já pronta
        time.sleep(intervalo)
    if not exigir_finished:
        return ""
    return f"timeout esperando processar (container {container_id})"


def _publicar_container(ig: str, creation_id: str, tok: str) -> tuple:
    """POST /{ig}/media_publish. Devolve (media_id, erro)."""
    try:
        d = _req().post(f"{GRAPH}/{ig}/media_publish",
                        data={"creation_id": creation_id, "access_token": tok},
                        timeout=60).json()
    except Exception as e:
        return "", f"exceção publicando: {e}"
    mid = d.get("id")
    if mid:
        return mid, ""
    return "", ((d.get("error") or {}).get("message") or str(d)[:200])


def postar_instagram_story(arquivo: str) -> dict:
    """
    Publica um STORY (imagem ou vídeo) na conta do `conta.json` ao lado do arquivo.

    Vídeo entra pelo binário (sem hospedar nada). Imagem passa pelo
    `midia_publica` porque a Graph API não aceita binário de imagem.

    ⚠️ O QUE A API **NÃO** FAZ, e é bom saber antes de planejar em cima:
    story publicado por API NÃO carrega figurinha nenhuma — nem enquete, nem
    caixa de pergunta, nem link, nem contagem regressiva. Menção a @perfil sem
    figurinha funciona; o resto, não. Story de API é conteúdo, não interação.

    Retorna {"sucesso", "url"|"erro"}.
    """
    _ativar_conta(arquivo)
    erro_base = _checar_base()
    if erro_base:
        return {"sucesso": False, "erro": erro_base}
    if not _ig_user_id():
        return {"sucesso": False, "erro": "INSTAGRAM_USER_ID não configurado"}

    midia = Path(arquivo)
    if not midia.exists():
        return {"sucesso": False, "erro": f"arquivo não encontrado: {arquivo}"}

    ig, tok = _ig_user_id(), _token()
    quem = _CTX.get("handle") or f"ig_user_id={ig[-6:] or '?'}"

    # ── STORY DE IMAGEM: precisa de URL pública ──────────────────────────
    if _e_imagem(midia):
        try:
            from midia_publica import publicar, MidiaPublicaErro
        except Exception as e:
            return {"sucesso": False, "erro": f"midia_publica indisponível: {e}"}
        try:
            url_img = publicar(_garantir_jpeg(midia))
        except MidiaPublicaErro as e:
            return {"sucesso": False, "erro": str(e)}
        log.info(f"   🖼️  Story (imagem) [{quem}]: {midia.name}")
        cid, err = _criar_container(ig, tok, {"media_type": "STORIES",
                                              "image_url": url_img})
        if not cid:
            return {"sucesso": False, "erro": f"container não criado: {err}"}
        err = _esperar_container(cid, tok, 10, 3, exigir_finished=False)
        if err:
            return {"sucesso": False, "erro": err}
    # ── STORY DE VÍDEO: binário direto ───────────────────────────────────
    else:
        dur = _dur_segundos(midia)
        if dur > STORY_MAX_SEG:
            # Recusar aqui é melhor que deixar a Meta recusar: ela devolve
            # "container deu ERROR", que não diz que o problema é a duração.
            return {"sucesso": False,
                    "erro": f"story de vídeo aceita até {STORY_MAX_SEG}s e este "
                            f"tem {dur:.0f}s — corte antes de mandar"}
        log.info(f"   🎬 Story (vídeo {dur:.0f}s) [{quem}]: {midia.name}")
        cid, err = _criar_container(ig, tok, {"media_type": "STORIES",
                                              "upload_type": "resumable"})
        if not cid:
            return {"sucesso": False, "erro": f"container não criado: {err}"}
        err = _subir_binario(cid, midia, tok)
        if err:
            return {"sucesso": False, "erro": f"upload binário falhou: {err}"}
        err = _esperar_container(cid, tok, IG_POLL_MAX, IG_POLL_INTERVALO)
        if err:
            return {"sucesso": False, "erro": err}

    media_id, err = _publicar_container(ig, cid, tok)
    if not media_id:
        return {"sucesso": False, "erro": f"publish do story recusado: {err}"}
    log.info(f"   ✅ Story publicado [{quem}] — {media_id}")
    # Story não tem permalink público (some em 24h); devolve o id de referência
    return {"sucesso": True, "url": f"story:{media_id}", "media_id": media_id}


def postar_instagram_carrossel(imagens: list, legenda: str = "") -> dict:
    """
    Publica um CARROSSEL de imagens. A conta sai do `conta.json` ao lado do 1º
    slide (mesmo contrato de pasta que o vídeo usa).

    Retorna {"sucesso", "url"|"erro"}.
    """
    if not imagens:
        return {"sucesso": False, "erro": "nenhum slide informado"}
    _ativar_conta(imagens[0])
    erro_base = _checar_base()
    if erro_base:
        return {"sucesso": False, "erro": erro_base}
    if not _ig_user_id():
        return {"sucesso": False, "erro": "INSTAGRAM_USER_ID não configurado"}

    slides = [Path(p) for p in imagens]
    faltando = [p.name for p in slides if not p.exists()]
    if faltando:
        return {"sucesso": False, "erro": f"slide(s) não encontrado(s): {faltando}"}
    if not all(_e_imagem(p) for p in slides):
        return {"sucesso": False,
                "erro": "por ora o carrossel é só de imagens (jpg/png)"}
    if not 2 <= len(slides) <= 10:
        return {"sucesso": False,
                "erro": f"carrossel aceita de 2 a 10 slides, recebi {len(slides)}"}

    try:
        from midia_publica import publicar, MidiaPublicaErro
    except Exception as e:
        return {"sucesso": False, "erro": f"midia_publica indisponível: {e}"}

    ig, tok = _ig_user_id(), _token()
    quem = _CTX.get("handle") or f"ig_user_id={ig[-6:] or '?'}"
    _corte = (legenda or "").strip()
    log.info(f"   🎠 Carrossel [{quem}]: {len(slides)} slides · legenda "
             f"{len(_corte)} caractere(s)"
             + (f" · começa com {_corte.splitlines()[0][:60]!r}" if _corte
                else "  ⚠️ VAZIA"))

    # ── 1. Cada slide vira um container filho ────────────────────────────
    filhos = []
    for i, slide in enumerate(slides, 1):
        try:
            url_img = publicar(_garantir_jpeg(slide))
        except MidiaPublicaErro as e:
            return {"sucesso": False, "erro": f"slide {i}: {e}"}
        cid, err = _criar_container(ig, tok, {"image_url": url_img,
                                              "is_carousel_item": "true"})
        if not cid:
            return {"sucesso": False, "erro": f"slide {i} recusado: {err}"}
        filhos.append(cid)
    log.info(f"   🎠 {len(filhos)} slide(s) aceitos, montando o carrossel...")

    for i, cid in enumerate(filhos, 1):
        err = _esperar_container(cid, tok, 10, 3, exigir_finished=False)
        if err:
            return {"sucesso": False, "erro": f"slide {i}: {err}"}

    # ── 2. Container pai (a legenda mora AQUI, não nos filhos) ───────────
    pai, err = _criar_container(ig, tok, {"media_type": "CAROUSEL",
                                          "children": ",".join(filhos),
                                          "caption": legenda})
    if not pai:
        return {"sucesso": False, "erro": f"carrossel não montado: {err}"}
    err = _esperar_container(pai, tok, 20, 3, exigir_finished=False)
    if err:
        return {"sucesso": False, "erro": err}

    # ── 3. Publica ───────────────────────────────────────────────────────
    media_id, err = _publicar_container(ig, pai, tok)
    if not media_id:
        return {"sucesso": False, "erro": f"publish do carrossel recusado: {err}"}

    if _engajar_ligado():
        _comentar(media_id, _montar_comentario("instagram", slides[0]), tok)
    # ⚠️ os arquivos publicados NÃO são apagados aqui de propósito: a Meta pode
    # rebuscar a imagem depois do publish. A coleta por idade do midia_publica
    # (6h) resolve sem correr esse risco.
    link = _buscar_permalink(media_id, "permalink", tok,
                             f"https://www.instagram.com/p/{media_id}")
    log.info(f"   ✅ Carrossel publicado [{quem}] — {link}")
    return {"sucesso": True, "url": link}


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
    parser.add_argument("--story", help="caminho da imagem OU vídeo pra postar como Story")
    parser.add_argument("--carrossel", nargs="+", metavar="IMG",
                        help="2 a 10 imagens, na ordem dos slides")
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
    elif args.story:
        print(f"\n📲 Postando Story: {args.story}")
        print(f"   → {postar_instagram_story(args.story)}")
    elif args.carrossel:
        print(f"\n🎠 Postando carrossel de {len(args.carrossel)} slide(s)")
        print(f"   → {postar_instagram_carrossel(args.carrossel, args.legenda)}")
    else:
        print("\nUse --diagnostico, --facebook <video>, --instagram <video>,")
        print("    --story <arquivo> ou --carrossel <img1> <img2> ...")
    print("=" * 60)