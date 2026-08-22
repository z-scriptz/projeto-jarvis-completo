#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# midia_publica.py — publica um arquivo LOCAL numa URL HTTPS pública temporária.
#
# ⚠️ POR QUE ISTO EXISTE (medido em 22/08, na doc oficial, não por tentativa):
#
# A Graph API da Meta tem DOIS caminhos pra media entrar num container:
#
#   VÍDEO  → aceita o binário direto pelo `rupload.facebook.com` (resumable).
#            É o que o `meta_uploader.postar_instagram` já faz com os Reels:
#            nada precisa estar hospedado em lugar nenhum.
#   IMAGEM → **NÃO TEM caminho binário.** Só existe `image_url`, e a doc é
#            explícita: "We cURL media used in publishing attempts, so the
#            media must be hosted on a publicly accessible server."
#
# Ou seja: CARROSSEL (que é feito de imagens) e STORY DE IMAGEM são impossíveis
# sem um host público. Não é preferência de arquitetura — é a única porta.
#
# E a gente já tem o host: o Caddy do `jarvis.topshopoficial.com.br` (que subiu
# pro painel do TikTok, ROADMAP 4.6) tem certificado válido e está de pé. Falta
# uma rota de arquivo estático nele — 4 linhas, `--caddy` imprime elas.
#
# DESENHO:
#   - Nome do arquivo publicado leva um token aleatório. A pasta é servida
#     inteira pela web; sem o token, `1.jpg` de um pacote seria adivinhável e
#     qualquer um listaria o que a gente vai postar antes de a gente postar.
#   - Hardlink quando dá (mesmo disco = custo zero), cópia quando não dá.
#   - Coleta de lixo A CADA PUBLICAÇÃO, por idade. Sem cron, sem serviço, sem
#     mais uma coisa pra lembrar de ligar. A Meta busca a imagem em segundos;
#     6 horas de folga é ordens de grandeza a mais do que ela precisa.
#   - `publicar()` CONFERE que a URL responde 200 antes de devolver. Isto é o
#     ponto do módulo inteiro: sem a conferência, uma rota errada no Caddy
#     chega na gente como "container deu ERROR no processamento" — a mensagem
#     mais inútil da Graph API — e a gente perde uma tarde procurando no lugar
#     errado. Com ela, o erro diz `404 em https://.../midia/x.jpg`.
#
# USO:
#   from midia_publica import publicar, limpar
#   url = publicar("/root/jarvis/pronto_carrossel/slug/1.jpg")
#
#   python3 midia_publica.py --caddy     # imprime a rota pro Caddyfile
#   python3 midia_publica.py --teste     # publica 1 arquivo e prova que abre
#   python3 midia_publica.py --limpar    # força a coleta de lixo agora

import os
import sys
import time
import shutil
import secrets
from pathlib import Path

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("midia_publica")

try:
    import requests
    _REQUESTS_OK = True
except Exception:
    _REQUESTS_OK = False


BASE_DIR = Path(__file__).resolve().parent


def _pasta() -> Path:
    return Path(os.environ.get("MIDIA_PUBLICA_DIR", str(BASE_DIR / "midia_publica")))


def _base_url() -> str:
    return os.environ.get(
        "MIDIA_PUBLICA_URL", "https://jarvis.topshopoficial.com.br/midia"
    ).rstrip("/")


def _horas() -> float:
    try:
        return float(os.environ.get("MIDIA_PUBLICA_HORAS", "6"))
    except ValueError:
        return 6.0


def _confere_ligado() -> bool:
    # Desligável só pra emergência (ex: rede da VPS sem loopback externo).
    return os.environ.get("MIDIA_PUBLICA_CONFERIR", "1").strip().lower() not in ("0", "false", "nao", "não")


class MidiaPublicaErro(RuntimeError):
    """Erro que o chamador PODE ler e mostrar — sempre diz a URL envolvida."""


# ══════════════════════════════════════════════════════════════════════════
# COLETA DE LIXO
# ══════════════════════════════════════════════════════════════════════════
def limpar(horas: float = None) -> int:
    """Apaga o que está publicado há mais de `horas`. Devolve quantos saíram.

    Nunca levanta exceção: se a limpeza falhar, publicar continua valendo —
    lixo acumulado é problema de disco, não de postagem."""
    limite = time.time() - (horas if horas is not None else _horas()) * 3600
    pasta = _pasta()
    saiu = 0
    try:
        if not pasta.exists():
            return 0
        for arq in pasta.iterdir():
            try:
                if arq.is_file() and arq.stat().st_mtime < limite:
                    arq.unlink()
                    saiu += 1
            except Exception:
                continue
    except Exception as e:
        log.debug(f"   limpeza da mídia pública falhou (seguindo): {e}")
    if saiu:
        log.info(f"   🧹 mídia pública: {saiu} arquivo(s) vencido(s) removido(s)")
    return saiu


# ══════════════════════════════════════════════════════════════════════════
# PUBLICAR
# ══════════════════════════════════════════════════════════════════════════
def _nome_publico(origem: Path) -> str:
    """`1.jpg` → `1-a3f9c1d2e4b5.jpg`. Extensão preservada (o Caddy serve o
    Content-Type por ela, e a Meta recusa o que não souber ler)."""
    return f"{origem.stem}-{secrets.token_hex(6)}{origem.suffix.lower()}"


def _conferir(url: str) -> None:
    """Levanta MidiaPublicaErro se a URL não responder 200 com corpo."""
    if not _confere_ligado():
        return
    if not _REQUESTS_OK:
        log.warning("   ⚠️  'requests' ausente — publicando SEM conferir a URL")
        return
    try:
        # GET com stream, não HEAD: alguns file servers respondem HEAD de um
        # jeito e GET de outro, e quem vai fazer GET é a Meta.
        r = requests.get(url, timeout=20, stream=True)
        tam = r.headers.get("Content-Length", "?")
        r.close()
    except Exception as e:
        raise MidiaPublicaErro(
            f"não consegui abrir {url} ({e}). O Caddy está servindo "
            f"{_pasta()} em {_base_url()}? Rode: python3 midia_publica.py --caddy"
        )
    if r.status_code != 200:
        raise MidiaPublicaErro(
            f"{url} respondeu HTTP {r.status_code} (esperado 200). A Meta vai "
            f"receber o mesmo e o container vai falhar sem dizer o porquê. "
            f"Rode: python3 midia_publica.py --caddy"
        )
    log.debug(f"   🌐 publicado e conferido: {url} ({tam} bytes)")


def publicar(arquivo, conferir: bool = True) -> str:
    """Deixa `arquivo` acessível numa URL HTTPS pública. Devolve a URL.

    Levanta MidiaPublicaErro com mensagem legível se algo impedir."""
    origem = Path(arquivo)
    if not origem.exists():
        raise MidiaPublicaErro(f"arquivo não existe: {origem}")

    limpar()   # o lixo de ontem sai antes de a gente escrever o de hoje

    pasta = _pasta()
    try:
        pasta.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise MidiaPublicaErro(f"não consegui criar {pasta}: {e}")

    destino = pasta / _nome_publico(origem)
    try:
        # hardlink não copia bytes; se for outro dispositivo, cai pra cópia
        try:
            os.link(origem, destino)
        except OSError:
            shutil.copy2(origem, destino)
        os.chmod(destino, 0o644)   # o Caddy roda como outro usuário
    except Exception as e:
        raise MidiaPublicaErro(f"não consegui publicar {origem.name}: {e}")

    url = f"{_base_url()}/{destino.name}"
    if conferir:
        try:
            _conferir(url)
        except MidiaPublicaErro:
            try:
                destino.unlink()      # não deixa arquivo órfão de uma falha
            except Exception:
                pass
            raise
    return url


def despublicar(url: str) -> bool:
    """Remove agora o arquivo de uma URL devolvida por publicar()."""
    try:
        alvo = _pasta() / url.rsplit("/", 1)[-1]
        if alvo.is_file():
            alvo.unlink()
            return True
    except Exception:
        pass
    return False


# ══════════════════════════════════════════════════════════════════════════
# CLI — diagnóstico
# ══════════════════════════════════════════════════════════════════════════
_CADDY = """\
# ─── cole isto no /etc/caddy/Caddyfile, DENTRO do bloco que já existe do
#     jarvis.topshopoficial.com.br (o mesmo que faz reverse_proxy pro 8770) ───

	handle_path /midia/* {{
		root * {pasta}
		file_server
	}}

# Depois:  caddy validate --config /etc/caddy/Caddyfile  &&  systemctl reload caddy
#
# ⚠️ A ORDEM IMPORTA: `handle_path /midia/*` precisa vir ANTES do
# `reverse_proxy` solto do bloco, senão o Caddy manda /midia/... pro Flask do
# painel do TikTok e a Meta recebe um 404 de HTML.
"""


def _cli_teste() -> int:
    alvo = _pasta() / ".teste"
    try:
        alvo.parent.mkdir(parents=True, exist_ok=True)
        # PNG 1x1 válido — arquivo de verdade, não texto com nome de imagem
        alvo.write_bytes(bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000a49444154789c6360000002000100ffff030000060005573bcec9000000"
            "0049454e44ae426082"))
        alvo_png = alvo.with_suffix(".png")
        alvo.replace(alvo_png)
    except Exception as e:
        print(f"❌ não consegui escrever em {_pasta()}: {e}")
        return 1
    print(f"📁 pasta:  {_pasta()}")
    print(f"🌐 base:   {_base_url()}")
    try:
        url = publicar(alvo_png)
    except MidiaPublicaErro as e:
        print(f"\n❌ {e}")
        print("\n   Rode `python3 midia_publica.py --caddy` e configure a rota.")
        return 1
    finally:
        try:
            alvo_png.unlink()
        except Exception:
            pass
    print(f"\n✅ FUNCIONA — {url} respondeu 200.")
    print("   Carrossel e story de imagem estão liberados.")
    despublicar(url)
    return 0


def main() -> int:
    args = set(sys.argv[1:])
    if "--caddy" in args:
        print(_CADDY.format(pasta=_pasta()))
        return 0
    if "--limpar" in args:
        print(f"🧹 {limpar(0.0)} arquivo(s) removido(s) de {_pasta()}")
        return 0
    if "--teste" in args:
        return _cli_teste()
    print(__doc__ or "")
    print("Use --caddy, --teste ou --limpar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
