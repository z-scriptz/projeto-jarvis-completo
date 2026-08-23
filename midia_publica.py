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
#   python3 midia_publica.py --instalar-caddy   # instala a rota SOZINHO
#   python3 midia_publica.py --caddy     # só imprime a rota pro Caddyfile
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


# ⚠️ FORA DE /root, E ISSO NÃO É ARRUMAÇÃO — É A ÚNICA COISA QUE FUNCIONA.
# O default era `~/jarvis/midia_publica`, e o Caddy respondeu **403** nos
# arquivos: ele roda como usuário `caddy`, `/root` é modo 700, e ninguém
# atravessa isso. Dar `chmod 755 /root` resolveria o 403 e abriria a casa
# inteira — o `.env` com todos os tokens mora lá.
# `/var/www` existe justamente pra conteúdo que um servidor web serve.
# Um `MIDIA_PUBLICA_DIR` no .env continua mandando, se um dia precisar.
PASTA_PADRAO = "/var/www/jarvis-midia"


def _pasta() -> Path:
    return Path(os.environ.get("MIDIA_PUBLICA_DIR", PASTA_PADRAO))


def _pasta_alcancavel() -> str:
    """Diz por que o Caddy não conseguiria ler a pasta. "" se estiver tudo bem.

    ⚠️ 403 e 404 têm causas OPOSTAS e a mesma cara pra quem só vê "não abriu":
    404 é rota errada no Caddyfile, 403 é permissão no caminho. Errar de qual
    se trata custa a tarde inteira no arquivo errado."""
    p = _pasta().resolve()
    for pai in [p] + list(p.parents):
        if str(pai) == "/":
            break
        if not pai.exists():
            continue
        modo = pai.stat().st_mode & 0o777
        # o Caddy é "outro" usuário: precisa de x (atravessar) em cada nível
        if not modo & 0o001:
            return (f"{pai} está em modo {modo:o} — sem permissão de entrada "
                    f"pra quem não é o dono. O Caddy roda como outro usuário e "
                    f"vai devolver 403.")
    return ""


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
        # ⚠️ 403 E 404 MANDAM PRA ARQUIVOS DIFERENTES, e mandar pro errado
        # custou uma rodada: com o 404 o problema é a ROTA (Caddyfile); com o
        # 403 a rota está certa e o problema é PERMISSÃO no caminho. Dizer
        # "rode --caddy" nos dois casos manda procurar no lugar errado metade
        # das vezes.
        if r.status_code == 403:
            porque = _pasta_alcancavel() or (
                f"a rota existe, mas o Caddy não pode LER {_pasta()}. "
                f"Confira o dono e o modo da pasta e dos arquivos.")
            dica = (f"403 = permissão, não rota. {porque}\n   "
                    f"Rode: python3 midia_publica.py --instalar-caddy")
        elif r.status_code == 404:
            dica = ("404 = a rota /midia não está no Caddyfile (ou está DEPOIS "
                    "do reverse_proxy).\n   "
                    "Rode: python3 midia_publica.py --instalar-caddy")
        else:
            dica = "Rode: python3 midia_publica.py --instalar-caddy"
        raise MidiaPublicaErro(
            f"{url} respondeu HTTP {r.status_code} (esperado 200). A Meta vai "
            f"receber o mesmo e o container vai falhar sem dizer o porquê.\n   "
            + dica)
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
# VER — a volta do laço
# ══════════════════════════════════════════════════════════════════════════
# ⚠️ O DEFEITO ERA DE PROCESSO, NÃO DE CÓDIGO (23/08). O `--agora casa` monta
# 7 slides em `pronto_carrossel/` e imprime o CAMINHO. Só que quem precisa
# aprovar o visual está no navegador, e o caminho é de um disco que ele não vê.
# Resultado: o Dre só enxergava o carrossel DEPOIS de publicado no Instagram —
# ou seja, revisão só existia quando já era tarde. Sem isto, "olhe alguns
# prontos antes de ligar o `carrossel_ligado`" era uma instrução impossível.
#
# Isto NÃO abre porta nova: reusa o `publicar()`, que só ESCREVE arquivo numa
# pasta estática que o Caddy já serve. Não recebe upload, não executa nada. E
# some sozinho no `limpar()` das 6 horas, junto com os slides.
_VER_HTML = """<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titulo}</title>
<style>
 body{{margin:0;background:#14120f;color:#efe7dc;
      font:16px/1.5 system-ui,-apple-system,sans-serif}}
 header{{padding:22px 18px 6px;max-width:760px;margin:0 auto}}
 h1{{font-size:19px;margin:0 0 4px}}
 .sub{{color:#9b9086;font-size:13px}}
 .leg{{max-width:760px;margin:16px auto;padding:16px 18px;background:#1e1b17;
       border-radius:14px;white-space:pre-wrap;font-size:14px;
       color:#d8cec2}}
 .tira{{max-width:760px;margin:0 auto;padding:10px 18px 60px}}
 figure{{margin:0 0 26px;position:relative}}
 img{{width:100%;border-radius:12px;display:block;background:#000}}
 /* à DIREITA de propósito: o canto superior esquerdo do slide é onde vive a
    tag do nicho, e é o espaço vazio que o prompt do fundo reserva. Um contador
    de revisão cobrindo justo o que se quer revisar não serve. */
 figcaption{{position:absolute;top:12px;right:12px;background:#000000b0;
             color:#fff;font-size:12px;padding:5px 11px;border-radius:20px}}
 .fim{{max-width:760px;margin:0 auto;padding:0 18px 40px;color:#6f665e;
       font-size:12px}}
</style>
<header><h1>{titulo}</h1>
<div class="sub">{quantos} slides · some em ~6h · esta página não vai pro ar
 pra ninguém além de quem tem o link</div></header>
{legenda}
<div class="tira">{figuras}</div>
<div class="fim">{rodape}</div>
"""


def _texto_curto(p: Path, limite: int = 4000) -> str:
    try:
        t = p.read_text(encoding="utf-8").strip()
    except Exception:
        return ""
    return t[:limite] + ("…" if len(t) > limite else "")


def ver_pasta(pasta) -> str:
    """Publica os slides de uma pasta como UMA página, e devolve a URL dela."""
    origem = Path(pasta)
    if not origem.is_dir():
        raise MidiaPublicaErro(f"não é uma pasta: {origem}")

    imgs = sorted(a for a in origem.iterdir()
                  if a.is_file() and a.suffix.lower() in
                  (".jpg", ".jpeg", ".png", ".webp"))
    if not imgs:
        raise MidiaPublicaErro(f"nenhuma imagem em {origem}")

    figuras = []
    for i, img in enumerate(imgs, 1):
        # sem conferir cada uma: são até 10 GETs de ida e volta, e a página no
        # fim é conferida de qualquer jeito — se o Caddy não estiver servindo,
        # ela falha lá e a mensagem é a mesma.
        u = publicar(img, conferir=False)
        figuras.append(f'<figure><img src="{u}" alt="slide {i}" loading="lazy">'
                       f'<figcaption>{i}/{len(imgs)}</figcaption></figure>')

    leg = _texto_curto(origem / "legenda.txt")
    legenda = (f'<div class="leg">{_escapar(leg)}</div>') if leg else ""

    corpo = _VER_HTML.format(
        titulo=_escapar(origem.name), quantos=len(imgs),
        legenda=legenda, figuras="\n".join(figuras),
        rodape=_escapar(str(origem)))

    alvo = _pasta() / f"ver-{secrets.token_hex(6)}.html"
    alvo.write_text(corpo, encoding="utf-8")
    os.chmod(alvo, 0o644)
    url = f"{_base_url()}/{alvo.name}"
    _conferir(url)
    return url


def _escapar(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


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


def _gravar_caddy(cf, novo: str) -> int:
    """Grava, valida e recarrega — restaurando o original se não validar.

    Extraída porque DOIS caminhos precisam dela (inserir a rota e corrigir o
    root de uma rota antiga), e uma rede de segurança duplicada é uma rede de
    segurança que um dia diverge da outra."""
    import shutil
    import subprocess
    from datetime import datetime

    bak = cf.with_name(cf.name + f".bak-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(cf, bak)
    cf.write_text(novo, encoding="utf-8")
    print(f"💾 backup em {bak}")

    try:
        r = subprocess.run(["caddy", "validate", "--config", str(cf)],
                           capture_output=True, text=True)
    except FileNotFoundError:
        # ⚠️ SEM O BINÁRIO, NÃO DÁ PRA VALIDAR — e um "deu certo" aqui seria
        # mentira. Mantém a edição (ela é uma inserção simples e o backup está
        # ali), mas diz em voz alta que a rede de segurança não rodou.
        print("⚠️  não achei o binário `caddy` no PATH — a edição FOI feita "
              "mas NÃO foi validada.")
        print(f"   Confira e recarregue à mão:\n"
              f"     caddy validate --config {cf} && systemctl reload caddy\n"
              f"   Se algo der errado:  cp {bak} {cf}")
        return 1
    if r.returncode != 0:
        shutil.copy2(bak, cf)
        print(f"❌ o Caddyfile não validou — RESTAUREI o original:\n"
              f"{(r.stderr or r.stdout)[-600:]}")
        return 1
    print("✅ Caddyfile válido.")

    try:
        r = subprocess.run(["systemctl", "reload", "caddy"],
                           capture_output=True, text=True)
    except FileNotFoundError:
        print("⚠️  validou, mas não achei `systemctl`. Recarregue o Caddy à mão.")
        return 1
    if r.returncode != 0:
        print(f"⚠️  validou mas o reload falhou: {(r.stderr or r.stdout)[-300:]}")
        print("   Rode à mão:  systemctl reload caddy")
        return 1
    print("🔄 Caddy recarregado.\n")
    return _cli_teste()


def _cli_instalar_caddy(aplicar: bool) -> int:
    """Insere a rota /midia no Caddyfile, com rede de segurança.

    ⚠️ ISTO EXISTE PORQUE O PASSO MANUAL FALHOU DUAS VEZES SEGUIDAS (22/08).
    Eu mandava `--caddy` imprimir a rota e pedia pra colar no arquivo. O Dre
    colou o BLOCO DE COMANDOS inteiro no terminal — e a linha "# cola no
    /etc/caddy/Caddyfile" virou comentário do bash. O `caddy validate` então
    respondeu "Valid configuration", porque o arquivo ESTÁ válido: ele só não
    tem a rota. Dois sinais verdes e o 404 continuou.

    Instrução no meio de uma sequência de comandos não é instrução, é um
    comando que não roda. Então vira comando.

    A rede: backup com timestamp → escreve → `caddy validate` → se falhar,
    RESTAURA e sai. Nunca deixa o Caddy com config quebrada."""
    import shutil
    import subprocess
    from datetime import datetime

    cf = Path(os.environ.get("CADDYFILE", "/etc/caddy/Caddyfile"))
    if not cf.exists():
        print(f"❌ não achei {cf}. Se o Caddy está noutro lugar: "
              f"CADDYFILE=/caminho/Caddyfile python3 midia_publica.py --instalar-caddy")
        return 1

    # ── a pasta primeiro: rota certa apontando pra pasta ilegível = 403 ──
    pasta = _pasta()
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        os.chmod(pasta, 0o755)
        print(f"📁 {pasta} (modo 755)")
    except Exception as e:
        print(f"❌ não consegui preparar {pasta}: {e}")
        return 1
    problema = _pasta_alcancavel()
    if problema:
        print(f"❌ {problema}")
        print(f"   Mude a pasta pra fora dali:  "
              f"python3 env_set.py MIDIA_PUBLICA_DIR {PASTA_PADRAO}")
        return 1

    texto = cf.read_text(encoding="utf-8")
    if "/midia" in texto:
        # ⚠️ IDEMPOTENTE NÃO É "NÃO MEXER". A primeira instalação gravou
        # `root * /root/jarvis/midia_publica`, que virou 403 quando a pasta
        # mudou de lugar; sair calado aqui deixaria a rota apontando pro
        # caminho velho para sempre, e o sintoma seria um 403 sem explicação.
        import re as _re
        m = _re.search(r"handle_path\s+/midia/\*\s*\{[^}]*?root\s+\*\s+(\S+)",
                       texto, _re.S)
        atual = m.group(1) if m else ""
        if atual == str(pasta):
            print(f"✅ {cf} já serve /midia em {pasta} — nada a fazer.")
            print("   Se o --teste ainda falha, o Caddy foi recarregado?")
            return 0
        if not m:
            print(f"⚠️  {cf} já menciona /midia mas não no formato que eu "
                  f"escrevo — não vou mexer. Confira à mão se o root é {pasta}.")
            return 1
        print(f"🔧 a rota /midia aponta pra {atual}, e a pasta agora é {pasta} "
              f"— corrigindo.")
        texto = texto[:m.start(1)] + str(pasta) + texto[m.end(1):]
        if not aplicar:
            print("🧪 conferência: nada foi gravado.")
            return 0
        return _gravar_caddy(cf, texto)

    # acha o bloco do host e a chave que o abre
    host = _base_url().split("//", 1)[-1].split("/", 1)[0]
    pos = texto.find(host)
    if pos < 0:
        print(f"❌ não achei um bloco de '{host}' em {cf}.")
        print("   Cole a rota à mão (python3 midia_publica.py --caddy) ou me "
              "mande a saída de:  cat /etc/caddy/Caddyfile")
        return 1
    abre = texto.find("{", pos)
    if abre < 0:
        print(f"❌ achei '{host}' mas não a chave '{{' que abre o bloco.")
        return 1
    fim_linha = texto.find("\n", abre)
    if fim_linha < 0:
        fim_linha = len(texto)

    # ⚠️ ENTRA LOGO NA PRIMEIRA LINHA DO BLOCO, e isso é o ponto: se entrasse
    # depois do `reverse_proxy` solto, o Caddy mandaria /midia/... pro Flask do
    # painel do TikTok e a Meta receberia um 404 de HTML — que é EXATAMENTE o
    # sintoma que a gente está tentando resolver.
    rota = (f"\n\thandle_path /midia/* {{\n"
            f"\t\troot * {_pasta()}\n"
            f"\t\tfile_server\n"
            f"\t}}\n")
    novo = texto[:fim_linha + 1] + rota + texto[fim_linha + 1:]

    print(f"📄 {cf}")
    print(f"📍 inserindo a rota como PRIMEIRA regra do bloco '{host}':")
    print("".join(f"      {l}\n" for l in rota.strip().splitlines()))

    if not aplicar:
        print("🧪 conferência: nada foi gravado. Rode sem --conferir pra aplicar.")
        return 0

    return _gravar_caddy(cf, novo)



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
    if "--instalar-caddy" in args:
        return _cli_instalar_caddy(aplicar="--conferir" not in args)
    if "--teste" in args:
        return _cli_teste()
    if "--ver" in args:
        return _cli_ver(sys.argv[1:])
    print(__doc__ or "")
    print("Use --instalar-caddy, --caddy, --teste, --ver <pasta> ou --limpar")
    return 0


def _ultima_pasta() -> Path:
    """A pasta de carrossel modificada mais recentemente. `--ver` sem
    argumento é o caso comum: acabou de rodar `--agora`, quer ver aquilo."""
    raiz = BASE_DIR / "pronto_carrossel"
    cands = [d for d in raiz.iterdir() if d.is_dir()] if raiz.is_dir() else []
    if not cands:
        raise MidiaPublicaErro(f"nenhuma pasta em {raiz}")
    return max(cands, key=lambda d: d.stat().st_mtime)


def _cli_ver(argv: list) -> int:
    resto = [a for a in argv if not a.startswith("--")]
    try:
        alvo = Path(resto[0]) if resto else _ultima_pasta()
        if not resto:
            print(f"📂 mais recente: {alvo.name}")
        url = ver_pasta(alvo)
    except MidiaPublicaErro as e:
        print(f"❌ {e}")
        print("   Se for 403/404, rode antes: "
              ".venv/bin/python midia_publica.py --teste")
        return 1
    print(f"\n🔗 {url}\n\n   Abre no celular também. Some sozinho em ~6h.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
