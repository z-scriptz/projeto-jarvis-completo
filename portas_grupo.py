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
# ⚠️ LANDING, NÃO REDIRECIONAMENTO — E A MUDANÇA FOI FORÇADA (29/08). A 1ª
# versão redirecionava na hora. A Meta continuou recusando: o robô dela SEGUE o
# redirect e vê `chat.whatsapp.com` no fim, porque ele carrega a página, não só
# lê a URL digitada.
#
# ⚠️ A SAÍDA ÓBVIA É ARMADILHA. Dá pra detectar o robô e servir outra coisa —
# isso se chama cloaking, viola explicitamente as políticas da Meta, e a punição
# é banimento da conta de anúncios. Não fazemos.
#
# A saída legítima é a página parar de ser um desvio e virar destino: conteúdo
# de verdade, com um botão que leva ao grupo. É o que os concorrentes fazem
# (petdeals.com.br é o exemplo que o Dre trouxe), é o que a Meta espera, e de
# quebra faz a otimização por "visualização da página de destino" funcionar —
# ela é melhor que clique porque filtra o toque acidental.
#
# ⚠️ E A PROVA VEM DA NOSSA PRÓPRIA FILA. A página mostra achadinhos REAIS, com
# preço e número de vendas que vieram da API de afiliado da Shopee. Não é texto
# de vendedor: é o que o grupo entrega, com o número do lado. Nenhuma frase aqui
# afirma coisa que não aconteceu — sem "a gente testou", sem "eu uso".
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
FILA = BASE_DIR / "shared" / "produtos_fila.json"
QUANTOS_PRODUTOS = 6
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


def _reais(v: float) -> str:
    """R$ 1.234,56 — mesma formatação do bio_page_builder."""
    return f"R$ {v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _num(v) -> float:
    """Preço como número, aceitando os três formatos que a fila guarda.

    ⚠️ Mesmo motivo do `_preco` do carrossel_brain, que quebrou hoje em
    'R$ 139,80': o campo passa por gravadores diferentes e chega como float,
    como string de número e como string já formatada."""
    if isinstance(v, (int, float)):
        return float(v)
    t = re.sub(r"[^\d,.]", "", str(v or ""))
    if not t:
        return 0.0
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def _esc(t) -> str:
    return (str(t or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _achadinhos(quantos: int = QUANTOS_PRODUTOS) -> list:
    """Os melhores da fila, pra página mostrar do que o grupo é feito.

    ⚠️ SÓ ENTRA QUEM TEM NÚMERO. A página exibe vendas e preço; produto sem
    medição viraria um card mudo no meio dos outros, e um card mudo ao lado de
    "4.931 vendas" parece produto ruim escondendo o número. Melhor mostrar
    quatro bons que seis desiguais.

    ⚠️ E A ORDEM É A MESMA DO GRUPO. Se a página promete os melhores e o grupo
    entrega outra coisa, a promessa quebra na primeira mensagem — que é o mesmo
    defeito de capa que o carrossel teve em 26/08, em outra superfície."""
    try:
        itens = json.loads(FILA.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(itens, list):
        return []
    bons = [i for i in itens
            if isinstance(i, dict) and i.get("imagem") and i.get("link")
            and str(i.get("classe") or "") in ("mina_ouro", "ok")
            and int(i.get("vendas") or 0) > 0 and _num(i.get("preco")) > 0]
    bons.sort(key=lambda i: (0 if i.get("classe") == "mina_ouro" else 1,
                             -int(i.get("vendas") or 0)))
    return bons[:quantos]


def _cards(produtos: list) -> str:
    if not produtos:
        # ⚠️ SEM PRODUTO, A SEÇÃO SOME — não vira grade vazia. Página de anúncio
        # com buraco visível custa mais caro que página curta.
        return ""
    linhas = []
    for p in produtos:
        nome = _esc(p.get("campeao") or p.get("produto") or "")[:70]
        preco = _reais(_num(p.get("preco")))
        # ponto de milhar no padrão brasileiro: 4931 -> 4.931
        vendas = f"{int(p.get('vendas') or 0):,}".replace(",", ".")
        linhas.append(
            f'<figure class="c">'
            f'<img src="{_esc(p.get("imagem"))}" alt="{nome}" loading="lazy">'
            f'<figcaption><b>{preco}</b>'
            f'<span>{vendas} vendas</span></figcaption>'
            f'</figure>')
    return ('<h2>Alguns dos últimos achadinhos</h2>'
            '<div class="grade">' + "".join(linhas) + '</div>')


def _pagina(url: str, produtos: list) -> str:
    """A landing. Curta: quem veio do anúncio decide em segundos.

    ⚠️ O BOTÃO APARECE DUAS VEZES, em cima e no fim. Quem já decidiu clica no
    primeiro sem rolar; quem foi convencido pelos produtos encontra o segundo
    onde acabou de se convencer. Um botão só custa uma das duas metades.

    ⚠️ NENHUMA FRASE AFIRMA O QUE NÃO ACONTECEU. Sem "a gente testou", sem "eu
    uso" — o que a página diz é o que é verdade: garimpamos, selecionamos, e
    os números ao lado de cada produto são da API da Shopee. Num anúncio pago
    afirmação falsa deixa de ser deselegante e vira problema com o CONAR."""
    href = _esc(url)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Grupo de achadinhos da Shopee</title>
<style>
 *{{box-sizing:border-box}}
 body{{margin:0;background:#0f1115;color:#f2f2f2;
      font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
 .w{{max-width:560px;margin:0 auto;padding:28px 18px 40px}}
 h1{{font-size:29px;line-height:1.2;margin:0 0 12px;letter-spacing:-.02em}}
 h1 b{{color:#25d366}}
 p.sub{{color:#b7bcc4;margin:0 0 22px}}
 h2{{font-size:15px;text-transform:uppercase;letter-spacing:.08em;
    color:#8b929c;margin:34px 0 14px;font-weight:600}}
 .cta{{display:block;background:#25d366;color:#08130c;text-decoration:none;
      text-align:center;font-weight:700;font-size:18px;padding:16px;
      border-radius:13px}}
 .cta:active{{transform:scale(.99)}}
 .obs{{color:#7d848d;font-size:13px;text-align:center;margin:10px 0 0}}
 .grade{{display:grid;grid-template-columns:1fr 1fr;gap:11px}}
 .c{{margin:0;background:#171a21;border-radius:12px;overflow:hidden}}
 .c img{{width:100%;aspect-ratio:1;object-fit:cover;display:block}}
 .c figcaption{{padding:9px 10px;font-size:14px;display:flex;
               justify-content:space-between;align-items:baseline;gap:6px}}
 .c b{{color:#25d366}}
 .c span{{color:#8b929c;font-size:12px}}
 ul{{list-style:none;padding:0;margin:0 0 26px}}
 li{{padding:7px 0 7px 26px;position:relative;color:#dfe3e8}}
 li:before{{content:"✓";position:absolute;left:0;color:#25d366;font-weight:700}}
</style>
</head>
<body>
<div class="w">
  <h1>Achadinhos da Shopee, <b>todo dia</b>, no seu WhatsApp</h1>
  <p class="sub">A gente garimpa e manda no grupo só o que vale a pena — com o
  link direto. Entrar é de graça.</p>

  <a class="cta" href="{href}">Entrar no grupo</a>
  <p class="obs">Grupo silenciável · saia quando quiser</p>

  <h2>O que você recebe</h2>
  <ul>
    <li>Produtos com avaliação boa e preço que faz sentido</li>
    <li>O link direto, sem precisar procurar</li>
    <li>Poucas mensagens por dia — nada de inundar seu WhatsApp</li>
  </ul>

  {_cards(produtos)}

  <p class="obs" style="margin:26px 0 12px">Pronto pra economizar?</p>
  <a class="cta" href="{href}">Entrar no grupo</a>
</div>
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

    # ⚠️ CARREGA UMA VEZ, NÃO POR PÁGINA. Todas as portas levam ao mesmo grupo e
    # mostram os mesmos achadinhos; reler a fila por slug seria trabalho igual
    # com resultado idêntico. E carregar aqui deixa o aviso sair uma vez só.
    produtos = _achadinhos()
    if not produtos:
        _log("⚠️  nenhum produto classificado com foto, preço e vendas na fila "
             "— as páginas saem sem a prova (rode enriquecer_fila.py)")
    else:
        _log(f"{len(produtos)} achadinho(s) na prova: "
             + ", ".join(str(p.get('campeao') or p.get('produto'))[:22]
                         for p in produtos[:3]) + "…")

    feitos = []
    for slug, url in destinos.items():
        destino = SITE_REPO / PASTA / str(slug) / "index.html"
        conteudo = _pagina(str(url), produtos)
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
