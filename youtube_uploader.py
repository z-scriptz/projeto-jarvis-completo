"""
agents/youtube_uploader.py
==========================
Upload automático de YouTube Shorts via YouTube Data API v3.

Lê o pacote de pronto_para_postar/<slug>/ (video.mp4 + titulo/descricao YouTube)
e sobe pro canal. Atualiza o manifest.json marcando youtube: postado.

SEGURANÇA POR PADRÃO:
  - Sobe como PRIVADO (privacyStatus="private"). Você revisa no YouTube Studio
    e torna público quando quiser. Evita publicar lixo automaticamente.
  - Use --publico pra subir como público direto (só quando confiar).

PRÉ-REQUISITOS (configuração no Google Cloud — feita uma vez):
  1. Projeto no Google Cloud Console
  2. YouTube Data API v3 ativada
  3. Tela de consentimento OAuth (Externo) com seu email como usuário de teste
  4. Credencial OAuth tipo "App para computador" → baixar JSON
  5. Salvar como shared/credentials/client_secret.json

  pip install google-api-python-client google-auth-oauthlib google-auth-httplib2

USO:
  python -m agents.youtube_uploader --produto "Mini Aspirador de Teclado"
  python -m agents.youtube_uploader --produto "X" --publico
  python -m agents.youtube_uploader --da-fila        # sobe todos pendentes

Primeira execução: abre o navegador pra você autorizar. Depois salva o token
em shared/credentials/youtube_token.json e não pede mais.
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("youtube_uploader")

RAIZ = Path(__file__).resolve().parent.parent
CRED_DIR = RAIZ / "shared" / "credentials"
CLIENT_SECRET = CRED_DIR / "client_secret.json"
TOKEN_PATH = CRED_DIR / "youtube_token.json"
PRONTO_DIR = RAIZ / "pronto_para_postar"

# Escopo mínimo necessário pra upload
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Imports do Google — só carregam se instalados (fallback claro se não)
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    _GOOGLE_OK = True
except Exception:
    _GOOGLE_OK = False


def _slug(produto: str) -> str:
    s = re.sub(r"[^\w\s-]", "", (produto or "").lower())
    return re.sub(r"[\s-]+", "_", s).strip("_")


def _checar_dependencias() -> bool:
    if not _GOOGLE_OK:
        log.error("❌ Bibliotecas do Google não instaladas. Rode:")
        log.error("   pip install google-api-python-client google-auth-oauthlib "
                  "google-auth-httplib2")
        return False
    if not CLIENT_SECRET.exists():
        log.error(f"❌ Credencial OAuth não encontrada: {CLIENT_SECRET}")
        log.error("   Baixe do Google Cloud Console (ID do cliente OAuth → App "
                  "para computador) e salve nesse caminho.")
        return False
    return True


def _autenticar():
    """
    Autentica via OAuth. 1ª vez: abre navegador. Depois: usa token salvo.
    Retorna o objeto 'youtube' pronto pra chamar a API.
    """
    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET), SCOPES)
            # abre o navegador local pra autorizar
            creds = flow.run_local_server(port=0)
        # salva o token pra não pedir de novo
        CRED_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        log.info(f"   🔑 Token salvo em {TOKEN_PATH}")

    return build("youtube", "v3", credentials=creds)


def _ler_pacote(produto: str) -> dict:
    """Lê video + titulo + descricao da pasta pronto_para_postar/<slug>/."""
    slug = _slug(produto)
    pasta = PRONTO_DIR / slug
    if not pasta.exists():
        raise FileNotFoundError(f"Pasta não encontrada: {pasta}. "
                                f"Rode o production_runner antes.")
    video = pasta / "video.mp4"
    if not video.exists():
        raise FileNotFoundError(f"Vídeo não encontrado: {video}")

    def _ler(nome, default=""):
        f = pasta / nome
        return f.read_text(encoding="utf-8").strip() if f.exists() else default

    titulo = _ler("titulo_youtube.txt", f"{produto} #shorts")
    descricao = _ler("descricao_youtube.txt", produto)
    hashtags = _ler("hashtags.txt", "")
    # YouTube: título max 100 chars
    if len(titulo) > 100:
        titulo = titulo[:97] + "..."
    return {"video": str(video), "titulo": titulo,
            "descricao": descricao, "hashtags": hashtags, "pasta": pasta}


def subir_video(produto: str, publico: bool = False) -> dict:
    """Sobe UM vídeo pro YouTube. Retorna dict com resultado."""
    if not _checar_dependencias():
        return {"sucesso": False, "erro": "dependencias_ou_credencial"}

    try:
        pacote = _ler_pacote(produto)
    except Exception as e:
        log.error(f"❌ {e}")
        return {"sucesso": False, "erro": str(e)}

    log.info(f"📤 Subindo '{produto}' pro YouTube...")
    log.info(f"   Título: {pacote['titulo']}")
    log.info(f"   Privacidade: {'PÚBLICO' if publico else 'PRIVADO (revise no Studio)'}")

    try:
        youtube = _autenticar()
    except Exception as e:
        log.error(f"❌ Falha na autenticação: {e}")
        return {"sucesso": False, "erro": f"auth: {e}"}

    # tags a partir das hashtags (sem o #)
    tags = [t.lstrip("#") for t in pacote["hashtags"].split() if t][:15]

    body = {
        "snippet": {
            "title": pacote["titulo"],
            "description": pacote["descricao"],
            "tags": tags,
            "categoryId": "22",  # People & Blogs (genérico, seguro)
        },
        "status": {
            "privacyStatus": "public" if publico else "private",
            "selfDeclaredMadeForKids": False,
        },
    }

    try:
        media = MediaFileUpload(pacote["video"], chunksize=-1, resumable=True,
                                mimetype="video/mp4")
        req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        resp = None
        while resp is None:
            status, resp = req.next_chunk()
            if status:
                log.info(f"   ⏳ {int(status.progress() * 100)}% enviado")

        video_id = resp.get("id")
        url = f"https://youtube.com/shorts/{video_id}"
        log.info(f"   ✅ Publicado! {url}")

        _atualizar_manifest(produto, video_id, url,
                            "public" if publico else "private")
        return {"sucesso": True, "video_id": video_id, "url": url}

    except Exception as e:
        log.error(f"   ❌ Falha no upload: {e}")
        return {"sucesso": False, "erro": str(e)}


def _atualizar_manifest(produto: str, video_id: str, url: str, privacidade: str):
    """Marca youtube como postado no manifest do produto (se existir)."""
    slug = _slug(produto)
    # procura o manifest mais recente em outputs/*/run_*/<slug>/manifest.json
    manifs = sorted((RAIZ / "outputs").glob(f"*/run_*/{slug}/manifest.json"),
                    reverse=True)
    if not manifs:
        return
    try:
        m = json.loads(manifs[0].read_text(encoding="utf-8"))
        m.setdefault("platforms", {})["youtube"] = "postado"
        m.setdefault("youtube_info", {})
        m["youtube_info"] = {"video_id": video_id, "url": url,
                             "privacidade": privacidade}
        manifs[0].write_text(json.dumps(m, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        log.info(f"   📝 Manifest atualizado: youtube → postado")
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Upload de YouTube Shorts via API")
    parser.add_argument("--produto", help="Nome do produto a subir")
    parser.add_argument("--publico", action="store_true",
                        help="Sobe como público (default: privado pra você revisar)")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("📺 YOUTUBE UPLOADER")
    log.info("=" * 60)

    if not args.produto:
        log.error("Forneça --produto 'Nome do Produto'")
        return 1

    r = subir_video(args.produto, publico=args.publico)
    return 0 if r.get("sucesso") else 1


if __name__ == "__main__":
    sys.exit(main())