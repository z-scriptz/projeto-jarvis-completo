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
        # ⚠️ O NÚMERO DE VENDAS FICA SOBRE A FOTO, não embaixo. É ele que
        # diferencia esta página das dos concorrentes — nenhum deles mede
        # produto — e informação que diferencia não pode ficar no rodapé do
        # card, onde o olho já passou batido.
        linhas.append(
            f'<figure class="c">'
            f'<span class="v">{vendas} vendas</span>'
            f'<img src="{_esc(p.get("imagem"))}" alt="{nome}" loading="lazy">'
            f'<figcaption><div class="n">{nome}</div><b>{preco}</b></figcaption>'
            f'</figure>')
    return ('<h2>O que entrou no grupo essa semana</h2>'
            '<div class="grade">' + "".join(linhas) + '</div>')


def _estatisticas() -> dict:
    """Números reais da fila pra página. {} se não der pra medir.

    ⚠️ SÓ NÚMERO QUE EXISTE. A tentação numa landing é escrever "+10.000
    membros satisfeitos" e seguir a vida. Aqui os três números saem do
    `produtos_fila.json` e podem ser conferidos: quantos produtos foram
    MEDIDOS pela API da Shopee, quantos passaram no corte, e quantas vendas
    esses aprovados somam.
    📌 Número inventado numa landing de anúncio pago é publicidade enganosa —
    e num nicho onde todo mundo inventa, o verificável é o diferencial."""
    try:
        itens = json.loads(FILA.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(itens, list):
        return {}
    medidos = [i for i in itens if isinstance(i, dict) and i.get("classe")]
    bons = [i for i in medidos if i["classe"] in ("mina_ouro", "ok")]
    if len(medidos) < 20:
        # amostra pequena vira número sem graça ("12 analisados") e enfraquece
        # em vez de convencer. Melhor a seção não existir.
        return {}
    return {"medidos": len(medidos), "bons": len(bons),
            "vendas": sum(int(i.get("vendas") or 0) for i in bons)}


def _mil(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


def _barra_stats(st: dict) -> str:
    if not st:
        return ""
    return (
        '<div class="stats">'
        f'<div><b>{_mil(st["medidos"])}</b><span>produtos analisados</span></div>'
        f'<div><b>{_mil(st["bons"])}</b><span>passaram no corte</span></div>'
        f'<div><b>{_mil(st["vendas"])}</b><span>vendas somadas</span></div>'
        '</div>')


def _pagina(url: str, produtos: list) -> str:
    """A landing.

    ⚠️ O BOTÃO É FIXO NO RODAPÉ, além do de cima. Num anúncio de tráfego a
    pessoa chega no celular e decide rolando; CTA que sai da tela junto com o
    scroll obriga a rolar de volta, e uma parte não rola. O fixo acompanha.

    ⚠️ NENHUMA FRASE AFIRMA O QUE NÃO ACONTECEU. Sem "a gente testou", sem "eu
    uso", sem contador de membros inventado. O que a página diz é verdade
    verificável: garimpamos, medimos, e os números vêm da API da Shopee. Em
    anúncio pago afirmação falsa vira problema com o CONAR."""
    href = _esc(url)
    st = _estatisticas()
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta name="theme-color" content="#0b0d12">
<title>Achadinhos da Shopee — grupo gratuito no WhatsApp</title>
<style>
 *{{box-sizing:border-box;-webkit-tap-highlight-color:transparent}}
 body{{margin:0;background:#0b0d12;color:#eef1f5;
      font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
      padding-bottom:92px}}
 .w{{max-width:520px;margin:0 auto;padding:0 18px}}
 header{{padding:30px 0 0}}
 .selo{{display:inline-flex;align-items:center;gap:7px;background:#16341f;
       color:#4ade80;font-size:12.5px;font-weight:600;letter-spacing:.03em;
       padding:6px 12px;border-radius:99px;margin-bottom:16px}}
 .selo i{{width:7px;height:7px;border-radius:99px;background:#25d366;
         display:block}}
 h1{{font-size:31px;line-height:1.15;margin:0 0 14px;letter-spacing:-.025em;
    font-weight:800}}
 h1 em{{font-style:normal;color:#25d366}}
 .sub{{color:#a8b0bb;margin:0;font-size:17px}}
 .cta{{display:block;background:#25d366;color:#062a14;text-decoration:none;
      text-align:center;font-weight:800;font-size:17.5px;padding:17px;
      border-radius:14px;box-shadow:0 6px 20px rgba(37,211,102,.22)}}
 .cta:active{{transform:translateY(1px)}}
 .obs{{color:#767e8a;font-size:13px;text-align:center;margin:11px 0 0}}
 .stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;
        margin:26px 0 6px;text-align:center}}
 .stats div{{background:#141821;border-radius:12px;padding:13px 6px}}
 .stats b{{display:block;font-size:20px;color:#fff;letter-spacing:-.02em}}
 .stats span{{font-size:11.5px;color:#7d8593;line-height:1.35;display:block;
             margin-top:3px}}
 h2{{font-size:13px;text-transform:uppercase;letter-spacing:.1em;
    color:#7d8593;margin:34px 0 13px;font-weight:700}}
 .grade{{display:grid;grid-template-columns:1fr 1fr;gap:11px}}
 .c{{margin:0;background:#141821;border-radius:14px;overflow:hidden;
    position:relative}}
 .c img{{width:100%;aspect-ratio:1;object-fit:cover;display:block;
        background:#1c212b}}
 .c .v{{position:absolute;top:8px;left:8px;background:rgba(6,10,16,.82);
       color:#4ade80;font-size:11px;font-weight:700;padding:4px 8px;
       border-radius:99px;backdrop-filter:blur(4px)}}
 .c figcaption{{padding:10px 11px 12px}}
 .c .n{{font-size:12.5px;color:#98a1ae;line-height:1.35;height:2.7em;
       overflow:hidden;margin-bottom:5px}}
 .c b{{color:#fff;font-size:17px;letter-spacing:-.02em}}
 ul{{list-style:none;padding:0;margin:0}}
 li{{padding:9px 0 9px 30px;position:relative;color:#d5dae1;
    border-bottom:1px solid #171c25}}
 li:last-child{{border:0}}
 li:before{{content:"✓";position:absolute;left:2px;top:9px;color:#25d366;
          font-weight:800}}
 .fixo{{position:fixed;left:0;right:0;bottom:0;padding:12px 18px 16px;
       background:linear-gradient(to top,#0b0d12 62%,rgba(11,13,18,0));
       z-index:9}}
 .fixo .w{{padding:0}}
</style>
</head>
<body>
<div class="w">
  <header>
    <span class="selo"><i></i>Grupo gratuito no WhatsApp</span>
    <h1>Os achadinhos da Shopee que <em>passam no filtro</em></h1>
    <p class="sub">Todo dia a gente analisa o que aparece e manda no grupo
    só o que tem tração de verdade — com o link direto.</p>
  </header>

  {_barra_stats(st)}

  {_cards(produtos)}

  <h2>Como funciona</h2>
  <ul>
    <li>Só entra produto com boa avaliação e preço que faz sentido</li>
    <li>O link vai junto — você não precisa procurar</li>
    <li>Poucas mensagens por dia, sem inundar seu WhatsApp</li>
    <li>Silencie ou saia quando quiser</li>
  </ul>

  <p class="obs" style="margin:30px 0 0">Entrar é de graça.</p>
</div>

<div class="fixo"><div class="w"><a class="cta" href="{href}">
Entrar no grupo</a></div></div>
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
