#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# portas_grupo.py — páginas de entrada pro grupo, no nosso domínio.
#
# ⚠️ POR QUE ISTO EXISTE: A META NÃO ACEITA `chat.whatsapp.com` COMO DESTINO
# (29/08). Pôr o link de convite do grupo no campo "URL do site" de uma campanha
# de Tráfego trava a publicação com:
#
#     ⛔ Defina o destino do seu anúncio como WhatsApp: Para receber mensagens
#        no WhatsApp, defina-o como destino do seu anúncio. (#2446860)
#
# E o "destino WhatsApp" que ela oferece abre CONVERSA 1:1 com o número, não o
# grupo. Ou seja: não existe caminho direto de anúncio pago pra grupo. Um
# endereço nosso que redireciona é o caminho — a Meta vê um site comum.
#
# ⚠️ E RESOLVE TRÊS PROBLEMAS DE UMA VEZ, não só o bloqueio:
#
#   1. GRUPO LOTA. WhatsApp para em ~1024 membros. Sem indireção, a campanha
#      continua mandando gente pra uma porta fechada — e o anúncio não avisa,
#      ele segue rodando normalmente enquanto você paga por clique perdido.
#      Aqui você troca o destino num arquivo e o anúncio nem sabe.
#
#   2. LINK QUEBRA. Se o número for banido ou o convite for redefinido, o
#      anúncio no ar vira link morto. Editar o destino de um anúncio ativo o
#      joga de volta pra revisão e você perde o aprendizado da campanha.
#
#   3. OTIMIZAÇÃO. O Meta mede "visualização da página de destino" — que é
#      melhor que clique, porque filtra o toque acidental. Num link que abre o
#      app do WhatsApp não há página pra carregar, então esse evento nunca
#      acontece. Com uma página de verdade no meio, ele volta a existir.
#
# ⚠️ REDIRECIONAMENTO, NÃO LANDING PAGE. Nada de "clique aqui para entrar":
# quem clicou no anúncio já decidiu, e todo passo a mais perde gente. A página
# some em menos de um segundo.
#
# ⚠️ O REDIRECT É `<meta refresh>` + JS, NOS DOIS. O JS é instantâneo; o meta
# funciona se o JS estiver bloqueado (navegador dentro do app, extensão). Um só
# dos dois deixa uma fatia do tráfego pago parada numa tela branca.
#
# COMO USAR:
#   1. edite shared/portas_grupo.json  (slug -> link de convite)
#   2. .venv/bin/python portas_grupo.py              # mostra o que faria
#   3. .venv/bin/python portas_grupo.py --publicar   # gera, commita e sobe
#
#   No anúncio, o destino vira:  https://topshopoficial.com.br/g/pet
#
# TROCAR DE GRUPO (quando o primeiro lotar): muda o link no JSON, roda de novo
# com --publicar. O anúncio segue intocado.

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DESTINOS = BASE_DIR / "shared" / "portas_grupo.json"
# mesmo endereço que o deploy_site usa — o site é um clone à parte, no
# repositório do GitHub Pages que serve o topshopoficial.com.br
SITE_REPO = Path(os.environ.get("TOPSHOP_SITE_DIR",
                                str(Path.home() / "topshop-site")))
PASTA = "g"          # https://topshopoficial.com.br/g/<slug>

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")


def _log(m):
    print(f"   {m}", flush=True)


def _valido(slug: str, url: str) -> str:
    """"" se o par serve; senão, o motivo.

    ⚠️ CONFERE ANTES DE GERAR, não depois de publicar. Uma página que redireciona
    pra lugar nenhum é indistinguível de uma que funciona — até você olhar o
    relatório da campanha e ver mil cliques e nenhum membro novo."""
    if not _SLUG.match(slug):
        return "slug tem que ser minúsculo, sem acento e sem espaço (ex: pet)"
    if not url.startswith("https://"):
        return "o link precisa começar com https://"
    if "chat.whatsapp.com" not in url and "t.me" not in url:
        # não é erro fatal — só quase sempre engano
        return "não parece link de convite de grupo (chat.whatsapp.com ou t.me)"
    return ""


def _pagina(url: str) -> str:
    """O HTML da porta. Curto de propósito: ele existe por meio segundo."""
    # aspas duplas do HTML e a URL entram cruas em dois contextos (atributo e
    # string JS), então escapo o que quebraria cada um
    href = url.replace("&", "&amp;").replace('"', "&quot;")
    js = url.replace("\\", "\\\\").replace("'", "\\'")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<!-- ⚠️ noindex: estas páginas são porta de entrada de anúncio, não conteúdo.
     Indexadas, competiriam com a vitrine na busca e apareceriam soltas. -->
<meta name="robots" content="noindex,nofollow">
<meta http-equiv="refresh" content="0;url={href}">
<title>Entrando no grupo…</title>
<style>
  body{{margin:0;min-height:100vh;display:flex;align-items:center;
       justify-content:center;background:#111;color:#fff;
       font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
  a{{color:#25d366}}
</style>
</head>
<body>
<p>Abrindo o grupo… <a href="{href}">toque aqui se não abrir</a></p>
<script>location.replace('{js}');</script>
</body>
</html>
"""


def _git(*args):
    return subprocess.run(["git", "-C", str(SITE_REPO), *args],
                          capture_output=True, text=True)


def publicar(quantas: int) -> bool:
    """git add/commit/push só da pasta das portas.

    ⚠️ TOCA SÓ EM `g/`. O `deploy_site` regenera o index.html no mesmo
    repositório e pode ter mudança pendente ali; um `git add -A` aqui levaria
    junto uma vitrine pela metade."""
    r = _git("add", PASTA)
    if r.returncode != 0:
        _log(f"❌ git add falhou: {(r.stderr or r.stdout)[:140]}")
        return False
    if not _git("diff", "--cached", "--quiet").returncode:
        _log("nada mudou — as páginas no ar já são estas ✔")
        return True
    r = _git("commit", "-m", f"portas do grupo: {quantas} endereço(s)")
    if r.returncode != 0:
        _log(f"❌ commit falhou: {(r.stderr or r.stdout)[:140]}")
        return False
    p = _git("push")
    if p.returncode != 0:
        erro = (p.stderr or p.stdout)
        if any(x in erro for x in ("non-fast-forward", "fetch first", "rejected")):
            # mesma reconciliação do deploy_site, pelo mesmo motivo: o cron dele
            # commita no mesmo repositório e as duas mãos divergem.
            _log("   divergiu do origin — rebase e tento uma vez")
            _git("fetch", "origin")
            if _git("rebase", "-X", "theirs", "@{u}").returncode != 0:
                _git("rebase", "--abort")
                _log("   ✗ rebase não resolveu — precisa de mão humana")
                return False
            p = _git("push")
        if p.returncode != 0:
            _log(f"❌ push falhou: {(p.stderr or p.stdout)[:160]}")
            return False
    _log("✅ no ar")
    return True


def rodar(publicar_de_verdade: bool) -> int:
    if not DESTINOS.exists():
        _log(f"❌ não achei {DESTINOS}")
        _log('   crie com:  {"pet": "https://chat.whatsapp.com/SEU_CONVITE"}')
        return 2
    try:
        destinos = json.loads(DESTINOS.read_text(encoding="utf-8"))
    except Exception as e:
        _log(f"❌ {DESTINOS.name} ilegível: {str(e)[:100]}")
        return 2
    if not isinstance(destinos, dict) or not destinos:
        _log(f"❌ {DESTINOS.name} tem que ser um objeto slug -> link")
        return 2
    if not SITE_REPO.is_dir():
        _log(f"❌ não achei o clone do site em {SITE_REPO}")
        _log("   defina TOPSHOP_SITE_DIR ou clone o repositório do site")
        return 2

    problemas = {s: m for s, u in destinos.items()
                 if (m := _valido(str(s), str(u)))}
    for s, m in problemas.items():
        _log(f"❌ {s}: {m}")
    if problemas:
        # ⚠️ PARA TUDO SE UM ESTIVER TORTO. Publicar metade deixaria anúncios
        # apontando pra páginas que existem e não levam a lugar nenhum.
        _log("nada foi gerado — corrija o JSON e rode de novo")
        return 1

    feitos = []
    for slug, url in destinos.items():
        destino = SITE_REPO / PASTA / str(slug) / "index.html"
        conteudo = _pagina(str(url))
        if publicar_de_verdade:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(conteudo, encoding="utf-8")
        feitos.append(slug)
        _log(f"{'✅' if publicar_de_verdade else '🧪'} /{PASTA}/{slug}  →  {url}")

    if not publicar_de_verdade:
        _log(f"SIMULAÇÃO — {len(feitos)} página(s). Nada gravado. "
             f"Use --publicar.")
        return 0
    return 0 if publicar(len(feitos)) else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Gera as páginas de entrada do grupo no nosso domínio.")
    p.add_argument("--publicar", action="store_true",
                   help="grava, commita e sobe (sem isto, só simula)")
    return rodar(p.parse_args(argv).publicar)


if __name__ == "__main__":
    sys.exit(main())
