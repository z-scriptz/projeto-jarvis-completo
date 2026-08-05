#!/usr/bin/env python3
# curso_page_builder.py -- gera a PÁGINA DE VENDAS do curso Afiliado Online.
#
# POR QUE EXISTE
# ──────────────
# A página da Hotmart é igual à de todo mundo e não é nossa. Esta é a que os
# afiliados vão divulgar, então ela precisa (1) vender, (2) parecer TopShop e
# (3) — a parte que ninguém lembra até dar errado — NÃO PERDER O PARÂMETRO DE
# AFILIADO no caminho até o checkout.
#
# O RISCO QUE MANDA NO DESENHO DESTE ARQUIVO
# O afiliado divulga topshopoficial.com.br/curso?src=ele. Se a página abrir o
# checkout SEM repassar esse parâmetro, a venda acontece e ele não recebe — e
# descobre semanas depois, pelo extrato. É um erro silencioso, que corrói a
# confiança dos afiliados justamente enquanto eles estão trabalhando de graça.
# Por isso _JS_AFILIADO existe e por isso ele é a última coisa que se mexe aqui.
#
# TOM: o curso se posiciona como MÉTODO, não milagre — a Aula 3 inteira é sobre
# honestidade de resultado. Copy de promessa fácil contradiz o produto e queima
# a confiança que ele constrói. Nada aqui promete ganho, prazo ou valor.
#
# MARCA: verde escuro + dourado (curso/remotion/src/theme.js). A vitrine é rosa
# choque — são marcas diferentes de propósito, não misture.
#
# Uso:
#   python3 curso_page_builder.py                 # gera em site/curso/index.html
#   python3 curso_page_builder.py --saida X.html
#   CURSO_CHECKOUT=https://pay.hotmart.com/... python3 curso_page_builder.py

import argparse
import html
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SAIDA_PADRAO = BASE_DIR / "site" / "curso" / "index.html"

# ── O QUE SÓ O DONO SABE ────────────────────────────────────────────────────
# O checkout PÚBLICO da Hotmart (pay.hotmart.com/...). NÃO é o link de
# app.hotmart.com/products/manage/... — aquele é a tela de ADMINISTRAÇÃO e o
# cliente cai num login. Enquanto estiver vazio, a página avisa em vez de
# publicar botão quebrado.
# `go.hotmart.com/<ID>?dp=1` e nao `pay.hotmart.com/<ID>`: o `dp=1` diz a
# Hotmart pra PULAR a pagina de vendas dela e ir direto ao checkout — que e
# justamente o motivo de existir pagina propria. O pay.hotmart tambem funciona,
# mas o go/dp=1 e o caminho que a Hotmart documenta pra este caso e o que
# preserva melhor o rastreio.
CHECKOUT = os.environ.get(
    "CURSO_CHECKOUT", "https://go.hotmart.com/B106927444O?dp=1").strip()

PRECO = os.environ.get("CURSO_PRECO", "179,90").strip()
PARCELA = os.environ.get("CURSO_PARCELA", "").strip()   # ex.: "12x de R$ 17,90"
GARANTIA = int(float(os.environ.get("CURSO_GARANTIA_DIAS", "7")))

CORES = {
    "bg1": "#0c1512", "bg2": "#07100c", "verde": "#12251b",
    "ink": "#eaf0ea", "muted": "#a7b6ab",
    "gold": "#d8b25a", "goldSoft": "#f0d79a", "quente": "#c98a72",
}

# ── CONTEUDO ────────────────────────────────────────────────────────────────
# Tudo abaixo sai das aulas que EXISTEM (curso/remotion/src/aulas/). Nada
# inventado: secao sem lastro numa aula nao entra.

TRAVAS = [
    ("🙈", "Não quero aparecer",
     "Você não precisa. O método inteiro é feito pra funcionar sem mostrar o rosto."),
    ("⏳", "Não tenho tempo",
     "O trabalho é montar o sistema uma vez. Depois é ele que roda, não você."),
    ("🧭", "Não sei por onde começar",
     "Existe uma ordem. Você vai segui-la, passo a passo, sem adivinhar nada."),
]

MAQUINA = [
    ("01", "Você não cria. Você <b>conecta</b>.",
     "O conteúdo que converte já existe. O que falta é o sistema que liga uma "
     "peça na outra."),
    ("02", "Vídeos que <b>não mostram você</b>",
     "O formato faceless não é limitação — é o que torna possível produzir em "
     "volume sem depender da sua presença."),
    ("03", "Alcance é <b>volume</b>, não sorte",
     "Um vídeo que estoura é ruído. Muitos vídeos, com método, viram média — e "
     "média dá pra prever."),
    ("04", "Do vídeo até o <b>checkout</b>",
     "O caminho inteiro, sem buraco: onde a pessoa te encontra, o que ela vê "
     "depois, e como ela chega na compra."),
    ("05", "Repita o que o <b>número</b> aprova",
     "Parar de decidir por opinião. O que mediu e funcionou, repete; o que "
     "não, sai."),
]

MENTALIDADE = [
    ("Os primeiros vão ser <b>ruins</b>",
     "E isso está previsto. Quem desiste no quinto vídeo desiste antes da "
     "parte em que o método começa a agir."),
    ("Ninguém pode <b>garantir</b> resultado",
     "Nem eu. Quem garante está vendendo outra coisa. O que dá pra garantir é "
     "o método e a ordem."),
    ("Meta de <b>processo</b>, não de resultado",
     "&ldquo;Publicar X vídeos nesta semana&rdquo; você controla. "
     "&ldquo;Faturar Y&rdquo; não. A primeira te move; a segunda te paralisa."),
    ("Compare com <b>você de ontem</b>",
     "A régua é o seu próprio avanço. Comparar com quem começou há dois anos "
     "só serve pra parar."),
]

AULAS_M0 = [
    ("Aula 1", "Bem-vindo",
     "A trava que te trouxe até aqui, por que dá pra fazer sem aparecer, e o "
     "que este curso é — e o que ele não é."),
    ("Aula 2", "A máquina que você vai construir",
     "As peças do sistema e como elas se encaixam. Sozinha, nenhuma funciona."),
    ("Aula 3", "A mentalidade que sustenta o resultado",
     "A parte que ninguém te conta, e que decide quem continua depois do "
     "primeiro mês."),
]

# A GRADE. `pronto` diz se o modulo JA ESTA GRAVADO — a pagina mostra selo
# "disponivel" ou "em breve" a partir disto. Mentir aqui e o jeito mais rapido
# de transformar venda em reembolso, e reembolso queima o afiliado que trouxe
# a venda junto com o dinheiro. Marque True so quando as aulas existirem.
MODULOS = [
    (0, "Boas-vindas", True, [
        "Bem-vindo ao Afiliado Online",
        "O que voce vai construir (a visao da maquina)",
        "Mentalidade: sistema &gt; esforco"]),
    (1, "Fundamentos do Afiliado Faceless", False, [
        "Como funciona a comissao (Shopee) e o rastreio",
        "Por que &ldquo;sem aparecer&rdquo; vende",
        "Criando sua conta de afiliado + seus primeiros links"]),
    (2, "Montando as Contas (a Fundacao)", False, [
        "Escolhendo o nicho e criando os perfis",
        "Bio que converte",
        "Identidade visual: template, logo e feed"]),
    (3, "A Esteira de Conteudo (o Coracao)", False, [
        "De onde vem o conteudo (fontes virais)",
        "Produzindo o video faceless (corte, template, audio)",
        "O hook que para o scroll",
        "A legenda que gera alcance (informativa + Publi)",
        "Hashtags em escada (SEO)"]),
    (4, "Alcance (o Gargalo Real)", False, [
        "Por que alcance e tudo no comeco",
        "As alavancas de alcance (audio, retencao, saves)",
        "Medindo o que funciona"]),
    (5, "Conversao (View &rarr; R$)", False, [
        "Link na bio, ID do produto e marcacao nativa do IG",
        "O canal do Telegram como ativo proprio",
        "Respondendo comentarios e DMs"]),
    (6, "Automacao (a Maquina Sozinha)", False, [
        "O que da (e o que nao da) pra automatizar",
        "Postagem no piloto automatico",
        "Medir, podar e escalar o que funciona"]),
    (7, "Escala (do Afiliado ao Empresario)", False, [
        "Ser dono da audiencia (a lista)",
        "Trafego pago quando faz sentido (CPA &lt; LTV)",
        "Proximos degraus: loja e infoproduto"]),
]

BONUS = ("Kit do Aluno", ["Templates e checklists", "Comunidade (em breve)"])

PRA_QUEM = [
    (True, "Quer uma renda online e não quer aparecer"),
    (True, "Prefere seguir um passo a passo a sair testando no escuro"),
    (True, "Aceita que resultado vem de execução, não de sorte"),
    (False, "Procura ficar rico rápido ou renda sem trabalho"),
    (False, "Quer garantia de valor ou de prazo — isso ninguém honesto dá"),
    (False, "Não pretende publicar com constância"),
]

FAQ = [
    ("Preciso mostrar o rosto?",
     "Não. O método inteiro é construído no formato <b>faceless</b> — os "
     "vídeos não mostram você. Essa não é uma adaptação: é o desenho do curso "
     "desde a primeira aula."),
    ("Preciso criar conteúdo do zero?",
     "Não. Uma das ideias centrais é que <b>você não cria, você conecta</b>. O "
     "conteúdo que converte já existe; o que falta é o sistema que liga uma "
     "peça na outra."),
    ("Em quanto tempo eu vejo resultado?",
     "Não tem resposta honesta com número. <b>Ninguém pode garantir resultado "
     "ou prazo</b> — e quem garante está vendendo outra coisa. O que o curso "
     "entrega é o método e a ordem; o resto depende da sua execução."),
    ("E se meus primeiros vídeos forem ruins?",
     "Vão ser. Isso está previsto e tem uma aula inteira sobre. Quem desiste "
     "no quinto vídeo desiste <b>antes</b> da parte em que o método começa a "
     "agir."),
    ("Que nome aparece na fatura do meu cartao?",
     "A cobranca e processada pela Hotmart e aparece comecando com "
     "<b>HTM*</b>, seguido de uma abreviacao do produto &mdash; e cada banco "
     "abrevia de um jeito. Nao e cobranca de outra empresa: e a Hotmart "
     "processando a sua compra."),
    ("Como funciona o pagamento?",
     "O pagamento é processado pela <b>Hotmart</b>, com acesso liberado logo "
     "após a confirmação. Você tem <b>{garantia} dias</b> de garantia."),
]


def _modulos_html() -> str:
    linhas = []
    for n, titulo, pronto, aulas in MODULOS:
        selo = ('<span class="selo-m ok">disponivel</span>' if pronto
                else '<span class="selo-m breve">em breve</span>')
        itens = "\n".join(f'        <li>{a}</li>' for a in aulas)
        aberto = " open" if pronto else ""
        linhas.append(
            f'      <details class="mod" data-revela{aberto}>\n'
            f'        <summary><span class="idx">{n:02d}</span>'
            f'<span class="tit">{titulo}'
            f'<em>{len(aulas)} aula{"s" if len(aulas) != 1 else ""}</em></span>'
            f'{selo}<span class="seta">+</span></summary>\n'
            f'        <ul>\n{itens}\n        </ul>\n'
            f'      </details>')
    bt, ba = BONUS
    itens = "\n".join(f'        <li>{a}</li>' for a in ba)
    linhas.append(
        f'      <details class="mod bonus" data-revela>\n'
        f'        <summary><span class="idx">&#127873;</span>'
        f'<span class="tit">Bonus &mdash; {bt}<em>{len(ba)} itens</em></span>'
        f'<span class="seta">+</span></summary>\n'
        f'        <ul>\n{itens}\n        </ul>\n'
        f'      </details>')
    return "\n".join(linhas)


def _esc(t: str) -> str:
    return html.escape(t or "", quote=True)


def _botao(texto: str, classe: str = "") -> str:
    """O botao de compra. Sem checkout configurado ele NAO vira link morto:
    vira um aviso visivel, porque publicar botao que nao compra e pior que
    publicar pagina sem botao."""
    cls = ("botao " + classe).strip()
    if not CHECKOUT:
        return (f'<span class="{cls} pendente" title="Defina CURSO_CHECKOUT">'
                f'&#9888; checkout nao configurado</span>')
    return (f'<a class="{cls}" data-checkout href="{_esc(CHECKOUT)}" '
            f'rel="noopener"><span>{_esc(texto)}</span></a>')


# Repassa TUDO que veio na URL da pagina pro checkout. E assim que o credito do
# afiliado sobrevive ao clique — e a razao de a pagina existir num dominio
# nosso em vez de mandar o afiliado direto pra Hotmart.
#
# O resto do JS e enfeite e SE DEGRADA: revelacao no scroll so acontece se
# houver IntersectionObserver, o parallax so no desktop, e nada disso roda com
# prefers-reduced-motion. O repasse do parametro nao e enfeite e roda sempre —
# por isso e a PRIMEIRA coisa do arquivo, antes de qualquer checagem de suporte.
_JS = r"""
(function(){
  var busca = window.location.search;
  if (busca && busca.length > 1){
    var extra = busca.substring(1);
    var bts = document.querySelectorAll('a[data-checkout]');
    for (var i=0;i<bts.length;i++){
      var h = bts[i].getAttribute('href');
      if (!h || h === '#') continue;
      bts[i].setAttribute('href', h + (h.indexOf('?') === -1 ? '?' : '&') + extra);
    }
  }

  var calmo = window.matchMedia &&
              window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* revelacao no scroll */
  var alvos = document.querySelectorAll('[data-revela]');
  if (calmo || !('IntersectionObserver' in window)){
    for (var j=0;j<alvos.length;j++) alvos[j].classList.add('visivel');
  } else {
    var obs = new IntersectionObserver(function(ents){
      ents.forEach(function(e){
        if (e.isIntersecting){ e.target.classList.add('visivel'); obs.unobserve(e.target); }
      });
    }, {rootMargin: '0px 0px -12% 0px', threshold: 0.08});
    for (var k=0;k<alvos.length;k++) obs.observe(alvos[k]);
  }

  /* barra fixa de compra: aparece quando o heroi sai da tela.
     No celular ela e o unico CTA sempre a mao — por isso nao depende de
     IntersectionObserver e tem plano B no scroll. */
  var barra = document.getElementById('barra');
  var heroi = document.getElementById('heroi');
  function mostra(v){ if (barra) barra.classList.toggle('aberta', v); }
  if (barra && heroi){
    if ('IntersectionObserver' in window){
      new IntersectionObserver(function(e){ mostra(!e[0].isIntersecting); },
                               {threshold: 0}).observe(heroi);
    } else {
      window.addEventListener('scroll', function(){
        mostra(window.scrollY > heroi.offsetHeight * 0.8);
      }, {passive:true});
    }
  }

  /* luz do heroi seguindo o ponteiro — so no desktop, so com mouse */
  if (!calmo && heroi && window.matchMedia('(pointer:fine)').matches){
    heroi.addEventListener('pointermove', function(e){
      var r = heroi.getBoundingClientRect();
      heroi.style.setProperty('--mx', (e.clientX - r.left) + 'px');
      heroi.style.setProperty('--my', (e.clientY - r.top) + 'px');
    });
  }

  /* FAQ: abrir uma fecha as outras */
  var faqs = document.querySelectorAll('.faq details');
  for (var f=0; f<faqs.length; f++){
    faqs[f].addEventListener('toggle', function(){
      if (!this.open) return;
      for (var g=0; g<faqs.length; g++) if (faqs[g] !== this) faqs[g].open = false;
    });
  }
})();
"""


def _css() -> str:
    c = CORES
    return f"""
:root{{
  --bg1:{c['bg1']}; --bg2:{c['bg2']}; --verde:{c['verde']};
  --ink:{c['ink']}; --muted:{c['muted']};
  --gold:{c['gold']}; --goldSoft:{c['goldSoft']}; --quente:{c['quente']};
  --linha:rgba(216,178,90,.15);
  --card:rgba(18,37,27,.55);
}}
*{{box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{margin:0;background:var(--bg2);color:var(--ink);overflow-x:hidden;
  font:16px/1.68 system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,sans-serif;
  -webkit-font-smoothing:antialiased}}
.wrap{{max-width:1080px;margin:0 auto;padding:0 22px}}
section{{padding:78px 0;position:relative}}
h1,h2,h3{{line-height:1.16;margin:0 0 14px;letter-spacing:-.02em}}
h1{{font-size:clamp(32px,6vw,58px);font-weight:800}}
h2{{font-size:clamp(25px,3.8vw,38px);font-weight:750}}
h3{{font-size:18px;font-weight:650;letter-spacing:-.01em}}
p{{margin:0 0 14px;color:var(--muted)}}
b{{color:var(--goldSoft);font-weight:650}}
.g{{background:linear-gradient(100deg,var(--gold),var(--goldSoft) 55%,var(--gold));
  -webkit-background-clip:text;background-clip:text;color:transparent}}
.olho{{display:inline-flex;align-items:center;gap:8px;
  font:650 11.5px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.18em;text-transform:uppercase;color:var(--gold);
  margin-bottom:18px;padding:7px 13px;border-radius:999px;
  border:1px solid var(--linha);background:rgba(216,178,90,.06)}}

/* fundo vivo: duas manchas que giram devagar */
.orbe{{position:fixed;border-radius:50%;filter:blur(90px);opacity:.5;z-index:-1;
  pointer-events:none}}
.orbe.a{{width:52vw;height:52vw;top:-16vw;right:-14vw;
  background:radial-gradient(closest-side,rgba(216,178,90,.16),transparent);
  animation:flutua 26s ease-in-out infinite alternate}}
.orbe.b{{width:44vw;height:44vw;bottom:-16vw;left:-14vw;
  background:radial-gradient(closest-side,rgba(201,138,114,.12),transparent);
  animation:flutua 34s ease-in-out infinite alternate-reverse}}
@keyframes flutua{{to{{transform:translate3d(4vw,5vw,0) scale(1.14)}}}}

/* heroi */
.heroi{{padding:96px 0 74px;position:relative;isolation:isolate}}
.heroi::before{{content:"";position:absolute;inset:0;z-index:-1;pointer-events:none;
  background:radial-gradient(420px circle at var(--mx,72%) var(--my,28%),
             rgba(216,178,90,.10),transparent 70%);transition:opacity .3s}}
.heroi h1{{max-width:17ch}}
.lead{{font-size:clamp(17px,2.2vw,20.5px);max-width:60ch;margin-top:20px}}
.confia{{display:flex;flex-wrap:wrap;gap:9px;margin-top:26px;list-style:none;padding:0}}
.confia li{{font-size:13px;color:var(--muted);border:1px solid var(--linha);
  border-radius:999px;padding:7px 14px;background:rgba(18,37,27,.4)}}

/* revelacao */
[data-revela]{{opacity:0;transform:translateY(22px);
  transition:opacity .62s cubic-bezier(.2,.7,.3,1),transform .62s cubic-bezier(.2,.7,.3,1)}}
[data-revela].visivel{{opacity:1;transform:none}}
[data-revela][style*="--atraso"]{{transition-delay:var(--atraso)}}

/* grades */
ul.grade{{list-style:none;display:grid;gap:16px;padding:0;margin:30px 0 0;
  grid-template-columns:repeat(auto-fit,minmax(272px,1fr))}}
.cartao{{background:var(--card);border:1px solid var(--linha);border-radius:17px;
  padding:26px;transition:transform .22s ease,border-color .22s ease;
  position:relative;overflow:hidden}}
.cartao:hover{{transform:translateY(-4px);border-color:rgba(216,178,90,.4)}}
.cartao p{{margin:0;font-size:15px}}
.cartao .ico{{font-size:26px;display:block;margin-bottom:12px;line-height:1}}
.cartao .num{{font:700 12px/1 ui-monospace,Menlo,monospace;color:var(--gold);
  letter-spacing:.14em;display:block;margin-bottom:11px}}

/* e / nao e */
.duas{{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
  margin-top:30px}}
.duas>div{{border-radius:17px;padding:28px;border:1px solid var(--linha);
  background:var(--card)}}
.duas .sim h3{{color:var(--gold)}}
.duas .nao{{border-color:rgba(201,138,114,.3)}}
.duas .nao h3{{color:var(--quente)}}

/* pra quem e */
.quem{{list-style:none;padding:0;margin:30px 0 0;display:grid;gap:11px;
  grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}}
.quem li{{display:flex;gap:12px;align-items:flex-start;font-size:15.5px;
  color:var(--muted);background:var(--card);border:1px solid var(--linha);
  border-radius:13px;padding:15px 17px}}
.quem .m{{flex:0 0 auto;font-weight:800;line-height:1.5}}
.quem .ok .m{{color:var(--gold)}}
.quem .no .m{{color:var(--quente)}}

/* aulas: linha do tempo */
.linha{{list-style:none;padding:0;margin:30px 0 0;position:relative}}
.linha::before{{content:"";position:absolute;left:19px;top:12px;bottom:12px;width:2px;
  background:linear-gradient(var(--gold),transparent)}}
.linha li{{position:relative;padding:0 0 24px 58px}}
.linha li:last-child{{padding-bottom:0}}
.linha .bolha{{position:absolute;left:0;top:0;width:40px;height:40px;border-radius:50%;
  display:grid;place-items:center;background:var(--verde);
  border:1px solid rgba(216,178,90,.45);color:var(--gold);
  font:700 13px/1 ui-monospace,Menlo,monospace}}
.linha h3{{margin-bottom:5px}}
.linha p{{margin:0;font-size:15px}}

/* preco */
.preco{{text-align:center;border-radius:24px;padding:46px 26px;margin-top:30px;
  background:linear-gradient(165deg,rgba(18,37,27,.9),rgba(12,21,18,.9));
  border:1px solid rgba(216,178,90,.3);position:relative;overflow:hidden}}
.preco::before{{content:"";position:absolute;inset:-40%;
  background:conic-gradient(from 0deg,transparent,rgba(216,178,90,.12),transparent 32%);
  animation:gira 9s linear infinite;pointer-events:none}}
@keyframes gira{{to{{transform:rotate(360deg)}}}}
.preco>*{{position:relative}}
.valor{{font-size:clamp(44px,8vw,70px);font-weight:800;color:var(--goldSoft);
  letter-spacing:-.03em;line-height:1;margin:6px 0}}
.valor small{{font-size:.38em;font-weight:650;color:var(--gold);
  vertical-align:.9em;margin-right:6px}}
.parcela{{color:var(--muted);font-size:15px}}

/* botao */
.botao{{display:inline-block;margin-top:26px;padding:17px 38px;border-radius:999px;
  background:linear-gradient(135deg,var(--gold),var(--goldSoft));color:#14200f;
  font-weight:750;text-decoration:none;font-size:16.5px;position:relative;
  overflow:hidden;box-shadow:0 12px 32px rgba(216,178,90,.24);
  transition:transform .18s ease,box-shadow .18s ease}}
.botao::after{{content:"";position:absolute;top:0;left:-120%;width:60%;height:100%;
  background:linear-gradient(100deg,transparent,rgba(255,255,255,.5),transparent);
  animation:brilho 3.6s ease-in-out infinite}}
@keyframes brilho{{0%,68%{{left:-120%}}100%{{left:170%}}}}
.botao:hover{{transform:translateY(-2px);box-shadow:0 16px 40px rgba(216,178,90,.34)}}
.botao.grande{{font-size:18px;padding:20px 46px}}
.botao.pendente{{background:rgba(201,138,114,.16);color:var(--quente);
  border:1px dashed var(--quente);box-shadow:none;cursor:not-allowed}}
.botao.pendente::after{{display:none}}
.selo{{display:block;margin-top:15px;font-size:13.5px;color:var(--muted)}}

/* FAQ */
.faq{{margin-top:30px;display:grid;gap:11px}}
.faq details{{background:var(--card);border:1px solid var(--linha);
  border-radius:15px;overflow:hidden}}
.faq summary{{cursor:pointer;padding:20px 22px;font-weight:650;font-size:16.5px;
  list-style:none;display:flex;justify-content:space-between;gap:16px;
  align-items:center;transition:color .18s}}
.faq summary::-webkit-details-marker{{display:none}}
.faq summary:hover{{color:var(--goldSoft)}}
.faq summary::after{{content:"+";color:var(--gold);font-size:22px;font-weight:400;
  transition:transform .25s;flex:0 0 auto;line-height:1}}
.faq details[open] summary::after{{transform:rotate(45deg)}}
.faq .resp{{padding:0 22px 21px;color:var(--muted);font-size:15.5px;margin:0}}

/* barra fixa */
.barra{{position:fixed;left:0;right:0;bottom:0;z-index:40;
  background:rgba(7,16,12,.94);backdrop-filter:blur(12px);
  border-top:1px solid var(--linha);padding:12px 18px;
  display:flex;gap:16px;align-items:center;justify-content:center;
  transform:translateY(110%);transition:transform .3s cubic-bezier(.2,.7,.3,1)}}
.barra.aberta{{transform:none}}
.barra .b-preco{{font-weight:750;color:var(--goldSoft);white-space:nowrap}}
.barra .b-preco span{{display:block;font-size:12px;color:var(--muted);font-weight:400}}
.barra .botao{{margin:0;padding:13px 28px;font-size:15px}}
body{{padding-bottom:84px}}

/* grade de modulos */
.mods{{list-style:none;padding:0;margin:30px 0 0;display:grid;gap:13px}}
.mod{{background:var(--card);border:1px solid var(--linha);border-radius:16px;
  overflow:hidden;transition:border-color .22s}}
.mod:hover{{border-color:rgba(216,178,90,.36)}}
.mod>summary{{cursor:pointer;list-style:none;padding:20px 22px;display:flex;
  align-items:center;gap:15px}}
.mod>summary::-webkit-details-marker{{display:none}}
.mod .idx{{flex:0 0 auto;width:38px;height:38px;border-radius:11px;display:grid;
  place-items:center;background:rgba(216,178,90,.1);color:var(--gold);
  border:1px solid rgba(216,178,90,.3);
  font:700 14px/1 ui-monospace,Menlo,monospace}}
.mod .tit{{flex:1 1 auto;font-weight:650;font-size:16.5px;letter-spacing:-.01em}}
.mod .tit em{{display:block;font-style:normal;font-size:12.5px;color:var(--muted);
  font-weight:400;margin-top:3px}}
.mod .selo-m{{flex:0 0 auto;font:650 10.5px/1 ui-monospace,Menlo,monospace;
  letter-spacing:.1em;text-transform:uppercase;padding:6px 10px;border-radius:999px;
  white-space:nowrap}}
.mod .ok{{color:#14200f;background:linear-gradient(135deg,var(--gold),var(--goldSoft))}}
.mod .breve{{color:var(--muted);border:1px solid var(--linha)}}
.mod .seta{{flex:0 0 auto;color:var(--gold);font-size:19px;transition:transform .25s}}
.mod[open] .seta{{transform:rotate(45deg)}}
.mod ul{{margin:0;padding:0 22px 20px 74px;list-style:none}}
.mod ul li{{color:var(--muted);font-size:15px;padding:6px 0 6px 18px;position:relative}}
.mod ul li::before{{content:"";position:absolute;left:0;top:15px;width:7px;height:7px;
  border-radius:50%;background:rgba(216,178,90,.45)}}
.mod.bonus{{border-color:rgba(201,138,114,.32)}}
.mod.bonus .idx{{color:var(--quente);background:rgba(201,138,114,.1);
  border-color:rgba(201,138,114,.3)}}
@media (max-width:560px){{
  .mod ul{{padding-left:26px}}
  .mod .selo-m{{display:none}}
  .mod>summary{{padding:17px 16px;gap:12px}}
}}

hr.div{{border:0;border-top:1px solid var(--linha);margin:0}}
footer{{padding:48px 0 30px;color:var(--muted);font-size:13.5px}}
footer .aviso{{margin-top:12px;font-size:13px;opacity:.85;max-width:76ch}}

@media (max-width:560px){{
  section{{padding:58px 0}}
  .heroi{{padding:70px 0 56px}}
  .barra{{gap:12px;padding:10px 14px}}
  .barra .b-preco{{font-size:14px}}
}}
@media (prefers-reduced-motion:reduce){{
  *,*::before,*::after{{animation:none!important;transition:none!important}}
  html{{scroll-behavior:auto}}
}}
"""


def montar() -> str:
    travas = "\n".join(
        f'      <li class="cartao" data-revela style="--atraso:{i*90}ms">'
        f'<span class="ico">{ico}</span><h3>{_esc(t)}</h3><p>{d}</p></li>'
        for i, (ico, t, d) in enumerate(TRAVAS))

    maquina = "\n".join(
        f'      <li class="cartao" data-revela style="--atraso:{i*70}ms">'
        f'<span class="num">{n}</span><h3>{t}</h3><p>{d}</p></li>'
        for i, (n, t, d) in enumerate(MAQUINA))

    mental = "\n".join(
        f'      <li class="cartao" data-revela style="--atraso:{i*70}ms">'
        f'<h3>{t}</h3><p>{d}</p></li>'
        for i, (t, d) in enumerate(MENTALIDADE))

    quem = "\n".join(
        f'      <li class="{"ok" if bom else "no"}" data-revela '
        f'style="--atraso:{i*55}ms"><span class="m">{"&#10003;" if bom else "&#10007;"}'
        f'</span><span>{_esc(txt)}</span></li>'
        for i, (bom, txt) in enumerate(PRA_QUEM))

    aulas = "\n".join(
        f'      <li data-revela style="--atraso:{i*90}ms">'
        f'<span class="bolha">{i+1:02d}</span><h3>{_esc(t)}</h3><p>{_esc(d)}</p></li>'
        for i, (n, t, d) in enumerate(AULAS_M0))

    faq = "\n".join(
        f'      <details data-revela style="--atraso:{i*55}ms">'
        f'<summary>{_esc(p)}</summary>'
        f'<p class="resp">{r.format(garantia=GARANTIA)}</p></details>'
        for i, (p, r) in enumerate(FAQ))

    modulos = _modulos_html()
    parcela = f'<div class="parcela">{_esc(PARCELA)}</div>' if PARCELA else ""

    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Afiliado Online &mdash; uma renda online sem precisar aparecer</title>
<meta name="description" content="Um metodo passo a passo para construir renda
online no formato faceless: sem mostrar o rosto e sem postar o dia inteiro na
mao.">
<meta name="theme-color" content="{CORES['bg2']}">
<meta property="og:title" content="Afiliado Online">
<meta property="og:description" content="Uma renda online de verdade &mdash; sem
precisar aparecer. Um metodo, nao um milagre.">
<meta property="og:type" content="website">
<style>{_css()}</style>

<div class="orbe a"></div><div class="orbe b"></div>

<div class="wrap">

<section class="heroi" id="heroi">
  <span class="olho">&#9679; Afiliado Online</span>
  <h1>Uma renda online de verdade &mdash;<br><span class="g">sem precisar aparecer.</span></h1>
  <p class="lead">A vontade existe. O que trava e quase sempre o mesmo:
  <b>nao quero aparecer</b>, <b>nao tenho tempo</b>, <b>nao sei por onde
  comecar</b>. Este e o caminho que resolve os tres &mdash; construindo um
  <b>sistema que trabalha por voce</b>, em vez de voce trabalhar o dia inteiro.</p>
  {_botao("Quero comecar agora", "grande")}
  <ul class="confia">
    <li>&#10003; Formato faceless</li>
    <li>&#10003; Passo a passo</li>
    <li>&#10003; Acesso imediato</li>
    <li>&#10003; {GARANTIA} dias de garantia</li>
  </ul>
</section>

<hr class="div">

<section>
  <span class="olho" data-revela>O que te trouxe aqui</span>
  <h2 data-revela>Voce quer &mdash; mas <span class="g">trava</span></h2>
  <p data-revela>Sao quase sempre os mesmos tres motivos. E os tres tem resposta.</p>
  <ul class="grade">
{travas}
  </ul>
</section>

<section>
  <span class="olho" data-revela>O que este curso e</span>
  <h2 data-revela>Um <span class="g">metodo</span>. Nao um milagre.</h2>
  <div class="duas">
    <div class="sim" data-revela><h3>&#10003; E isto</h3><p>Um sistema real,
      passo a passo, que voce constroi e coloca pra rodar. Com ordem, com
      regua, e com o que fazer em cada etapa.</p></div>
    <div class="nao" data-revela style="--atraso:110ms"><h3>&#10007; Nao e isto</h3>
      <p>Promessa de ficar rico da noite pro dia. Resultado vem de execucao
      &mdash; e a gente e honesto sobre isso desde a primeira aula.</p></div>
  </div>
</section>

<section>
  <span class="olho" data-revela>A maquina</span>
  <h2 data-revela>O que voce vai <span class="g">construir</span></h2>
  <p data-revela>Cinco pecas que se encaixam. Sozinha, nenhuma funciona.</p>
  <ul class="grade">
{maquina}
  </ul>
</section>

<section>
  <span class="olho" data-revela>A parte que ninguem te conta</span>
  <h2 data-revela>A <span class="g">mentalidade</span> que sustenta o resultado</h2>
  <p data-revela>E o que decide quem continua depois do primeiro mes.</p>
  <ul class="grade">
{mental}
  </ul>
</section>

<section>
  <span class="olho" data-revela>A grade</span>
  <h2 data-revela>8 modulos, do <span class="g">zero ao sistema</span></h2>
  <p data-revela>Clique num modulo pra ver as aulas. O <b>Modulo 0 ja esta
  disponivel</b>; os demais entram conforme sao gravados &mdash; e voce nao paga
  nada a mais por eles.</p>
  <ul class="mods">
{modulos}
  </ul>
</section>

<section>
  <span class="olho" data-revela>Comeca aqui</span>
  <h2 data-revela>Modulo 0 &mdash; <span class="g">a base</span></h2>
  <p data-revela>Tres aulas que colocam voce na direcao certa antes da primeira
  execucao.</p>
  <ul class="linha">
{aulas}
  </ul>
</section>

<section>
  <span class="olho" data-revela>Antes de decidir</span>
  <h2 data-revela>Isto e <span class="g">pra voce</span>?</h2>
  <p data-revela>Prefiro que voce saia agora a comprar esperando outra coisa.</p>
  <ul class="quem">
{quem}
  </ul>
</section>

<section>
  <span class="olho" data-revela>Acesso</span>
  <h2 data-revela>Comece <span class="g">hoje</span></h2>
  <div class="preco" data-revela>
    <div class="parcela">Acesso ao curso Afiliado Online</div>
    <div class="valor"><small>R$</small>{_esc(PRECO)}</div>
    {parcela}
    {_botao("Garantir meu acesso", "grande")}
    <span class="selo">Pagamento processado pela Hotmart &middot;
      {GARANTIA} dias de garantia</span>
  </div>
</section>

<section>
  <span class="olho" data-revela>Duvidas</span>
  <h2 data-revela>O que costumam <span class="g">perguntar</span></h2>
  <div class="faq">
{faq}
  </div>
</section>

<hr class="div">

<footer>
  <div><b>Afiliado Online</b> &mdash; um metodo para construir renda online no
  formato faceless.</div>
  <p class="aviso">Este curso ensina um metodo. Ele nao garante resultado,
  ganho ou prazo: o que voce alcanca depende da sua execucao &mdash; e a gente
  diz isso na aula, nao so aqui embaixo.</p>
</footer>

</div>

<div class="barra" id="barra">
  <div class="b-preco">R$ {_esc(PRECO)}<span>acesso imediato</span></div>
  {_botao("Quero o curso")}
</div>

<script>{_JS}</script>
"""


def main() -> int:
    p = argparse.ArgumentParser(description="Gera a pagina de vendas do curso.")
    p.add_argument("--saida", default=str(SAIDA_PADRAO))
    args = p.parse_args()

    if not CHECKOUT:
        print("[curso] AVISO: CURSO_CHECKOUT vazio — a pagina sai com AVISO no")
        print("[curso]   lugar do botao, de proposito: botao que nao compra e")
        print("[curso]   pior que pagina sem botao.")
    elif "app.hotmart.com" in CHECKOUT or "/manage/" in CHECKOUT:
        print("[curso] ERRO: CURSO_CHECKOUT aponta pro painel de ADMINISTRACAO")
        print("[curso]   da Hotmart. O cliente cairia numa tela de login. Use o")
        print("[curso]   link publico (go.hotmart.com/<ID>?dp=1).")
        return 2

    destino = Path(args.saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    pagina = montar()
    destino.write_text(pagina, encoding="utf-8")
    print(f"[curso] OK {destino}  ({len(pagina)/1024:.1f} KB)")
    if CHECKOUT:
        print(f"[curso]   checkout: {CHECKOUT}")
        print("[curso]   os parametros da URL sao repassados pro checkout "
              "(credito do afiliado)")
    return 0


if __name__ == "__main__":
    try:
        from shared.trava import rodar_unico
    except Exception:
        sys.exit(main())
    sys.exit(rodar_unico("curso_page_builder", main))
