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
# descobre semanas depois, pelo extrato. Erro silencioso, que corrói a
# confiança dos afiliados justamente enquanto eles trabalham de graça. Por isso
# o repasse é a PRIMEIRA coisa do JS, antes de qualquer checagem de suporte: o
# resto da página é enfeite e pode degradar, o crédito do afiliado não.
#
# ACENTUAÇÃO — a falha da 1ª versão
# Ela saiu inteira SEM ACENTO ("voce", "metodo", "conteudo") porque o texto
# passou por heredoc de shell. Numa página de vendas em português isso destrói
# a credibilidade antes de qualquer argumento. Por isso este arquivo é escrito
# direto, NUNCA gerado por shell, e o CSS é string comum com .replace() em vez
# de f-string — f-string obrigaria a duplicar toda chave `{}` do CSS, e foi
# exatamente assim que a versão anterior quebrou.
#
# TOM: o curso se posiciona como MÉTODO, não milagre — a Aula 3 inteira é sobre
# honestidade de resultado. Copy de promessa fácil contradiz o produto e queima
# a confiança que ele constrói. Nada aqui promete ganho, prazo ou valor.
#
# MARCA: verde escuro + dourado (curso/remotion/src/theme.js). A vitrine é rosa
# choque — são marcas diferentes de propósito, não misture.
#
# Uso:
#   python3 curso_page_builder.py
#   python3 curso_page_builder.py --saida /tmp/previa.html

import argparse
import html
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SAIDA_PADRAO = BASE_DIR / "site" / "curso" / "index.html"

# `go.hotmart.com/<ID>?dp=1` e não `pay.hotmart.com/<ID>`: o `dp=1` manda a
# Hotmart PULAR a página de vendas dela e ir direto ao checkout — que é
# justamente o motivo de existir página própria. Sem ele, o cliente sai da
# nossa página pra ver a da Hotmart, e a nossa vira só um desvio.
CHECKOUT = os.environ.get(
    "CURSO_CHECKOUT", "https://go.hotmart.com/B106927444O?dp=1").strip()

# Conferidos na tabela da Hotmart (05/08). O PARCELADO é o número grande porque
# é a barreira real de decisão; o à vista aparece logo abaixo, sem esconder.
PRECO_VISTA = os.environ.get("CURSO_PRECO", "179,99").strip()
PARCELAS = os.environ.get("CURSO_PARCELAS", "12").strip()
PARCELA_VALOR = os.environ.get("CURSO_PARCELA_VALOR", "18,62").strip()
GARANTIA = int(float(os.environ.get("CURSO_GARANTIA_DIAS", "7")))

CORES = {
    "bg1": "#0c1512", "bg2": "#060d0a", "verde": "#12251b",
    "ink": "#f2f7f2", "muted": "#9fb0a4",
    "gold": "#d8b25a", "goldSoft": "#f5e0ad", "quente": "#e08b63",
}

# ── CONTEÚDO ────────────────────────────────────────────────────────────────
# Cada bloco tem lastro numa aula que existe em curso/remotion/src/aulas/.
# Seção sem lastro não entra.

TRAVAS = [
    ("🙈", "“Não quero aparecer”",
     "Você não precisa. O método inteiro é feito pra funcionar sem mostrar o "
     "rosto — não é adaptação, é o desenho."),
    ("⏳", "“Não tenho tempo”",
     "O trabalho é montar o sistema uma vez. Depois é ele que roda, não você."),
    ("🧭", "“Não sei por onde começar”",
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
     "“Publicar X vídeos nesta semana” você controla. “Faturar Y” não. A "
     "primeira te move; a segunda te paralisa."),
    ("Compare com <b>você de ontem</b>",
     "A régua é o seu próprio avanço. Comparar com quem começou há dois anos "
     "só serve pra parar."),
]

# `pronto` diz se o módulo JÁ ESTÁ GRAVADO — a página tira daqui o selo
# "disponível" ou "em breve". Marcar True num módulo que não existe é o jeito
# mais rápido de transformar venda em reembolso, e reembolso queima o afiliado
# que trouxe a venda junto com o dinheiro.
MODULOS = [
    (0, "Boas-vindas", True, [
        "Bem-vindo ao Afiliado Online",
        "O que você vai construir (a visão da máquina)",
        "Mentalidade: sistema &gt; esforço"]),
    (1, "Fundamentos do Afiliado Faceless", False, [
        "Como funciona a comissão (Shopee) e o rastreio",
        "Por que “sem aparecer” vende",
        "Criando sua conta de afiliado + seus primeiros links"]),
    (2, "Montando as Contas (a Fundação)", False, [
        "Escolhendo o nicho e criando os perfis",
        "Bio que converte",
        "Identidade visual: template, logo e feed"]),
    (3, "A Esteira de Conteúdo (o Coração)", False, [
        "De onde vem o conteúdo (fontes virais)",
        "Produzindo o vídeo faceless (corte, template, áudio)",
        "O hook que para o scroll",
        "A legenda que gera alcance (informativa + Publi)",
        "Hashtags em escada (SEO)"]),
    (4, "Alcance (o Gargalo Real)", False, [
        "Por que alcance é tudo no começo",
        "As alavancas de alcance (áudio, retenção, saves)",
        "Medindo o que funciona"]),
    (5, "Conversão (View &rarr; R$)", False, [
        "Link na bio, ID do produto e marcação nativa do IG",
        "O canal do Telegram como ativo próprio",
        "Respondendo comentários e DMs"]),
    (6, "Automação (a Máquina Sozinha)", False, [
        "O que dá (e o que não dá) pra automatizar",
        "Postagem no piloto automático",
        "Medir, podar e escalar o que funciona"]),
    (7, "Escala (do Afiliado ao Empresário)", False, [
        "Ser dono da audiência (a lista)",
        "Tráfego pago quando faz sentido (CPA &lt; LTV)",
        "Próximos degraus: loja e infoproduto"]),
]

BONUS = ("Kit do Aluno", ["Templates e checklists", "Comunidade (em breve)"])

PRA_QUEM = [
    (True, "Quer uma renda online e não quer aparecer"),
    (True, "Prefere seguir um passo a passo a testar no escuro"),
    (True, "Aceita que resultado vem de execução, não de sorte"),
    (False, "Procura ficar rico rápido ou renda sem trabalho"),
    (False, "Quer garantia de valor ou de prazo — ninguém honesto dá"),
    (False, "Não pretende publicar com constância"),
]

FAQ = [
    ("Preciso mostrar o rosto?",
     "Não. O método inteiro é construído no formato <b>faceless</b> — os "
     "vídeos não mostram você. Não é uma adaptação: é o desenho do curso desde "
     "a primeira aula."),
    ("Preciso criar conteúdo do zero?",
     "Não. Uma das ideias centrais é que <b>você não cria, você conecta</b>. O "
     "conteúdo que converte já existe; o que falta é o sistema que liga uma "
     "peça na outra."),
    ("Em quanto tempo eu vejo resultado?",
     "Não tem resposta honesta com número. <b>Ninguém pode garantir resultado "
     "ou prazo</b> — e quem garante está vendendo outra coisa. O curso entrega "
     "o método e a ordem; o resto depende da sua execução."),
    ("E se meus primeiros vídeos forem ruins?",
     "Vão ser. Isso está previsto e tem uma aula inteira sobre. Quem desiste "
     "no quinto vídeo desiste <b>antes</b> da parte em que o método começa a "
     "agir."),
    ("Os módulos que estão “em breve” custam mais?",
     "Não. Você paga uma vez e recebe tudo que entrar depois, sem pagar nada a "
     "mais. O <b>Módulo 0 já está liberado</b>; os demais entram conforme são "
     "gravados."),
    ("Que nome aparece na fatura do meu cartão?",
     "A cobrança é processada pela Hotmart e aparece começando com <b>HTM*</b>, "
     "seguido de uma abreviação do produto — cada banco abrevia de um jeito. "
     "Não é cobrança de outra empresa: é a Hotmart processando a sua compra."),
    ("E se eu não gostar?",
     "Você tem <b>{garantia} dias</b> de garantia. Pede o reembolso pela "
     "própria Hotmart e recebe o valor de volta."),
]

# ── CSS ─────────────────────────────────────────────────────────────────────
# String comum + .replace("@cor@"), NÃO f-string.
_CSS = """
:root{
  --bg1:@bg1@; --bg2:@bg2@; --verde:@verde@;
  --ink:@ink@; --muted:@muted@;
  --gold:@gold@; --goldSoft:@goldSoft@; --quente:@quente@;
  --linha:rgba(216,178,90,.16);
  --card:rgba(18,37,27,.6);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg2);color:var(--ink);overflow-x:hidden;
  font:16px/1.7 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased;padding-bottom:88px}
.wrap{max-width:1090px;margin:0 auto;padding:0 22px}
section{padding:84px 0;position:relative}
section.faixa{background:linear-gradient(180deg,transparent,rgba(18,37,27,.45),transparent)}
h1,h2,h3{line-height:1.14;margin:0 0 16px;letter-spacing:-.025em}
h1{font-size:clamp(34px,6.6vw,66px);font-weight:800}
h2{font-size:clamp(27px,4.2vw,44px);font-weight:800}
h3{font-size:18.5px;font-weight:650;letter-spacing:-.012em}
p{margin:0 0 15px;color:var(--muted)}
b{color:var(--goldSoft);font-weight:650}
.g{background:linear-gradient(103deg,var(--gold),var(--goldSoft) 48%,var(--quente));
  -webkit-background-clip:text;background-clip:text;color:transparent}
.olho{display:inline-flex;align-items:center;gap:9px;
  font:700 11.5px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.19em;text-transform:uppercase;color:var(--gold);
  margin-bottom:20px;padding:9px 16px;border-radius:999px;
  border:1px solid rgba(216,178,90,.32);background:rgba(216,178,90,.08)}
.olho::before{content:"";width:6px;height:6px;border-radius:50%;
  background:var(--gold);box-shadow:0 0 0 0 rgba(216,178,90,.6);
  animation:pulso 2.4s ease-out infinite}
@keyframes pulso{70%{box-shadow:0 0 0 9px rgba(216,178,90,0)}
                100%{box-shadow:0 0 0 0 rgba(216,178,90,0)}}

.orbe{position:fixed;border-radius:50%;filter:blur(100px);z-index:-1;
  pointer-events:none}
.orbe.a{width:58vw;height:58vw;top:-20vw;right:-16vw;opacity:.55;
  background:radial-gradient(closest-side,rgba(216,178,90,.22),transparent);
  animation:flutua 24s ease-in-out infinite alternate}
.orbe.b{width:48vw;height:48vw;bottom:-18vw;left:-16vw;opacity:.45;
  background:radial-gradient(closest-side,rgba(224,139,99,.18),transparent);
  animation:flutua 33s ease-in-out infinite alternate-reverse}
@keyframes flutua{to{transform:translate3d(5vw,6vw,0) scale(1.16)}}

.heroi{padding:104px 0 84px;position:relative;isolation:isolate}
.heroi::before{content:"";position:absolute;inset:0;z-index:-1;pointer-events:none;
  background:radial-gradient(460px circle at var(--mx,74%) var(--my,26%),
             rgba(216,178,90,.13),transparent 70%)}
.heroi h1{max-width:16ch}
.lead{font-size:clamp(17.5px,2.3vw,21.5px);max-width:58ch;margin-top:22px}
.confia{display:flex;flex-wrap:wrap;gap:10px;margin-top:30px;list-style:none;padding:0}
.confia li{font-size:13.5px;color:var(--muted);border:1px solid var(--linha);
  border-radius:999px;padding:8px 15px;background:rgba(18,37,27,.5)}
.confia b{color:var(--goldSoft)}

[data-revela]{opacity:0;transform:translateY(26px);
  transition:opacity .66s cubic-bezier(.2,.7,.3,1),transform .66s cubic-bezier(.2,.7,.3,1)}
[data-revela].visivel{opacity:1;transform:none}
[data-revela][style*="--atraso"]{transition-delay:var(--atraso)}

ul.grade{list-style:none;display:grid;gap:17px;padding:0;margin:34px 0 0;
  grid-template-columns:repeat(auto-fit,minmax(276px,1fr))}
.cartao{background:var(--card);border:1px solid var(--linha);border-radius:19px;
  padding:28px;position:relative;overflow:hidden;
  transition:transform .24s ease,border-color .24s ease,box-shadow .24s ease}
.cartao::before{content:"";position:absolute;inset:0;opacity:0;pointer-events:none;
  background:radial-gradient(320px circle at 50% -10%,rgba(216,178,90,.14),transparent 70%);
  transition:opacity .28s}
.cartao:hover{transform:translateY(-5px);border-color:rgba(216,178,90,.45);
  box-shadow:0 18px 44px rgba(0,0,0,.36)}
.cartao:hover::before{opacity:1}
.cartao p{margin:0;font-size:15.5px}
.cartao .ico{font-size:30px;display:block;margin-bottom:14px;line-height:1}
.cartao .num{font:800 13px/1 ui-monospace,Menlo,monospace;color:var(--gold);
  letter-spacing:.16em;display:block;margin-bottom:13px}

.duas{display:grid;gap:17px;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));
  margin-top:34px}
.duas>div{border-radius:19px;padding:30px;border:1px solid var(--linha);
  background:var(--card)}
.duas .sim{border-color:rgba(216,178,90,.34)}
.duas .sim h3{color:var(--gold)}
.duas .nao{border-color:rgba(224,139,99,.32)}
.duas .nao h3{color:var(--quente)}

.quem{list-style:none;padding:0;margin:34px 0 0;display:grid;gap:12px;
  grid-template-columns:repeat(auto-fit,minmax(324px,1fr))}
.quem li{display:flex;gap:13px;align-items:flex-start;font-size:15.5px;
  color:var(--muted);background:var(--card);border:1px solid var(--linha);
  border-radius:14px;padding:16px 18px}
.quem .m{flex:0 0 auto;font-weight:800;line-height:1.5}
.quem .ok .m{color:var(--gold)}
.quem .no .m{color:var(--quente)}

.mods{list-style:none;padding:0;margin:34px 0 0;display:grid;gap:13px}
.mod{background:var(--card);border:1px solid var(--linha);border-radius:17px;
  overflow:hidden;transition:border-color .22s,box-shadow .22s}
.mod:hover{border-color:rgba(216,178,90,.42);box-shadow:0 12px 34px rgba(0,0,0,.3)}
.mod>summary{cursor:pointer;list-style:none;padding:21px 24px;display:flex;
  align-items:center;gap:16px}
.mod>summary::-webkit-details-marker{display:none}
.mod .idx{flex:0 0 auto;width:42px;height:42px;border-radius:13px;display:grid;
  place-items:center;background:rgba(216,178,90,.12);color:var(--gold);
  border:1px solid rgba(216,178,90,.32);
  font:800 15px/1 ui-monospace,Menlo,monospace}
.mod .tit{flex:1 1 auto;font-weight:650;font-size:17px;letter-spacing:-.015em}
.mod .tit em{display:block;font-style:normal;font-size:12.5px;color:var(--muted);
  font-weight:400;margin-top:4px}
.mod .selo-m{flex:0 0 auto;font:700 10.5px/1 ui-monospace,Menlo,monospace;
  letter-spacing:.12em;text-transform:uppercase;padding:7px 11px;border-radius:999px;
  white-space:nowrap}
.mod .ok{color:#122016;background:linear-gradient(135deg,var(--gold),var(--goldSoft))}
.mod .breve{color:var(--muted);border:1px solid var(--linha)}
.mod .seta{flex:0 0 auto;color:var(--gold);font-size:21px;transition:transform .25s;
  line-height:1}
.mod[open] .seta{transform:rotate(45deg)}
.mod ul{margin:0;padding:0 24px 22px 82px;list-style:none}
.mod ul li{color:var(--muted);font-size:15px;padding:7px 0 7px 19px;position:relative}
.mod ul li::before{content:"";position:absolute;left:0;top:16px;width:7px;height:7px;
  border-radius:50%;background:rgba(216,178,90,.5)}
.mod.bonus{border-color:rgba(224,139,99,.34)}
.mod.bonus .idx{color:var(--quente);background:rgba(224,139,99,.12);
  border-color:rgba(224,139,99,.32)}

.preco{text-align:center;border-radius:28px;padding:52px 28px;margin-top:34px;
  background:linear-gradient(165deg,rgba(18,37,27,.94),rgba(8,15,12,.94));
  border:1px solid rgba(216,178,90,.34);position:relative;overflow:hidden}
.preco::before{content:"";position:absolute;inset:-45%;
  background:conic-gradient(from 0deg,transparent,rgba(216,178,90,.16),transparent 30%);
  animation:gira 8s linear infinite;pointer-events:none}
@keyframes gira{to{transform:rotate(360deg)}}
.preco>*{position:relative}
.preco .rot{color:var(--muted);font-size:15px;margin:0}
.valor{font-size:clamp(46px,9vw,80px);font-weight:800;color:var(--goldSoft);
  letter-spacing:-.04em;line-height:1;margin:10px 0 4px}
.valor .x{font-size:.4em;font-weight:700;color:var(--gold);
  vertical-align:.55em;margin-right:6px;letter-spacing:0}
.valor small{font-size:.34em;font-weight:700;color:var(--gold);
  vertical-align:.95em;margin-right:5px}
.avista{color:var(--muted);font-size:15.5px;margin:0}
.avista b{font-size:17px}

.botao{display:inline-block;margin-top:28px;padding:19px 44px;border-radius:999px;
  background:linear-gradient(135deg,var(--gold),var(--goldSoft));color:#122016;
  font-weight:800;text-decoration:none;font-size:17.5px;position:relative;
  overflow:hidden;letter-spacing:-.01em;
  box-shadow:0 14px 38px rgba(216,178,90,.3);
  transition:transform .18s ease,box-shadow .18s ease}
.botao::after{content:"";position:absolute;top:0;left:-120%;width:55%;height:100%;
  background:linear-gradient(100deg,transparent,rgba(255,255,255,.55),transparent);
  animation:brilho 3.4s ease-in-out infinite}
@keyframes brilho{0%,66%{left:-120%}100%{left:180%}}
.botao:hover{transform:translateY(-3px);box-shadow:0 20px 48px rgba(216,178,90,.42)}
.botao.grande{font-size:19.5px;padding:22px 52px}
.botao.pendente{background:rgba(224,139,99,.16);color:var(--quente);
  border:1px dashed var(--quente);box-shadow:none;cursor:not-allowed}
.botao.pendente::after{display:none}
.selo{display:block;margin-top:17px;font-size:13.5px;color:var(--muted)}

.faq{margin-top:34px;display:grid;gap:12px}
.faq details{background:var(--card);border:1px solid var(--linha);
  border-radius:16px;overflow:hidden;transition:border-color .22s}
.faq details:hover{border-color:rgba(216,178,90,.34)}
.faq summary{cursor:pointer;padding:21px 24px;font-weight:650;font-size:16.5px;
  list-style:none;display:flex;justify-content:space-between;gap:17px;
  align-items:center;transition:color .18s}
.faq summary::-webkit-details-marker{display:none}
.faq summary:hover{color:var(--goldSoft)}
.faq summary::after{content:"+";color:var(--gold);font-size:23px;font-weight:400;
  transition:transform .25s;flex:0 0 auto;line-height:1}
.faq details[open] summary::after{transform:rotate(45deg)}
.faq .resp{padding:0 24px 22px;color:var(--muted);font-size:15.5px;margin:0}

.barra{position:fixed;left:0;right:0;bottom:0;z-index:40;
  background:rgba(6,13,10,.96);backdrop-filter:blur(14px);
  border-top:1px solid rgba(216,178,90,.24);padding:13px 20px;
  display:flex;gap:18px;align-items:center;justify-content:center;
  transform:translateY(120%);transition:transform .32s cubic-bezier(.2,.7,.3,1)}
.barra.aberta{transform:none}
.barra .b-preco{font-weight:800;color:var(--goldSoft);white-space:nowrap;
  font-size:17px;letter-spacing:-.02em}
.barra .b-preco span{display:block;font-size:12px;color:var(--muted);
  font-weight:400;letter-spacing:0}
.barra .botao{margin:0;padding:14px 30px;font-size:15.5px}

hr.div{border:0;border-top:1px solid var(--linha);margin:0}
footer{padding:52px 0 34px;color:var(--muted);font-size:13.5px}
footer .aviso{margin-top:13px;font-size:13px;opacity:.85;max-width:76ch}

@media (max-width:600px){
  section{padding:62px 0}
  .heroi{padding:74px 0 60px}
  .mod ul{padding-left:28px}
  .mod .selo-m{display:none}
  .mod>summary{padding:18px 17px;gap:13px}
  .barra{gap:13px;padding:11px 15px}
  .barra .b-preco{font-size:15px}
  .barra .botao{padding:13px 24px;font-size:14.5px}
}
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation:none!important;transition:none!important}
  html{scroll-behavior:auto}
}
"""

# O repasse do parâmetro é a PRIMEIRA coisa e roda sempre. O resto se degrada.
_JS = """
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

  var alvos = document.querySelectorAll('[data-revela]');
  if (calmo || !('IntersectionObserver' in window)){
    for (var j=0;j<alvos.length;j++) alvos[j].classList.add('visivel');
  } else {
    var obs = new IntersectionObserver(function(ents){
      ents.forEach(function(e){
        if (e.isIntersecting){ e.target.classList.add('visivel'); obs.unobserve(e.target); }
      });
    }, {rootMargin:'0px 0px -12% 0px', threshold:0.08});
    for (var k=0;k<alvos.length;k++) obs.observe(alvos[k]);
  }

  var barra = document.getElementById('barra');
  var heroi = document.getElementById('heroi');
  function mostra(v){ if (barra) barra.classList.toggle('aberta', v); }
  if (barra && heroi){
    if ('IntersectionObserver' in window){
      new IntersectionObserver(function(e){ mostra(!e[0].isIntersecting); },
                               {threshold:0}).observe(heroi);
    } else {
      window.addEventListener('scroll', function(){
        mostra(window.scrollY > heroi.offsetHeight * 0.8);
      }, {passive:true});
    }
  }

  if (!calmo && heroi && window.matchMedia('(pointer:fine)').matches){
    heroi.addEventListener('pointermove', function(e){
      var r = heroi.getBoundingClientRect();
      heroi.style.setProperty('--mx', (e.clientX - r.left) + 'px');
      heroi.style.setProperty('--my', (e.clientY - r.top) + 'px');
    });
  }

  var faqs = document.querySelectorAll('.faq details');
  for (var f=0; f<faqs.length; f++){
    faqs[f].addEventListener('toggle', function(){
      if (!this.open) return;
      for (var g=0; g<faqs.length; g++) if (faqs[g] !== this) faqs[g].open = false;
    });
  }
})();
"""


def _esc(t):
    return html.escape(t or "", quote=True)


def _css():
    css = _CSS
    for chave, valor in CORES.items():
        css = css.replace("@" + chave + "@", valor)
    return css


def _botao(texto, classe=""):
    """Sem checkout configurado o botão NÃO vira link morto: vira aviso
    visível. Botão que não compra é pior que página sem botão."""
    cls = ("botao " + classe).strip()
    if not CHECKOUT:
        return (f'<span class="{cls} pendente" title="Defina CURSO_CHECKOUT">'
                f'⚠️ checkout não configurado</span>')
    return (f'<a class="{cls}" data-checkout href="{_esc(CHECKOUT)}" '
            f'rel="noopener">{_esc(texto)}</a>')


def _modulos_html():
    linhas = []
    for n, titulo, pronto, aulas in MODULOS:
        selo = ('<span class="selo-m ok">disponível</span>' if pronto
                else '<span class="selo-m breve">em breve</span>')
        itens = "\n".join(f"        <li>{a}</li>" for a in aulas)
        plural = "s" if len(aulas) != 1 else ""
        linhas.append(
            f'      <details class="mod" data-revela{" open" if pronto else ""}>\n'
            f'        <summary><span class="idx">{n:02d}</span>'
            f'<span class="tit">{titulo}<em>{len(aulas)} aula{plural}</em></span>'
            f'{selo}<span class="seta">+</span></summary>\n'
            f'        <ul>\n{itens}\n        </ul>\n'
            f'      </details>')
    bt, ba = BONUS
    itens = "\n".join(f"        <li>{a}</li>" for a in ba)
    linhas.append(
        f'      <details class="mod bonus" data-revela>\n'
        f'        <summary><span class="idx">🎁</span>'
        f'<span class="tit">Bônus — {bt}<em>{len(ba)} itens</em></span>'
        f'<span class="seta">+</span></summary>\n'
        f'        <ul>\n{itens}\n        </ul>\n'
        f'      </details>')
    return "\n".join(linhas)


def montar():
    total_aulas = sum(len(a) for _, _, _, a in MODULOS)
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
        f'style="--atraso:{i*55}ms"><span class="m">{"✓" if bom else "✕"}</span>'
        f'<span>{_esc(txt)}</span></li>'
        for i, (bom, txt) in enumerate(PRA_QUEM))
    faq = "\n".join(
        f'      <details data-revela style="--atraso:{i*50}ms">'
        f'<summary>{_esc(p)}</summary>'
        f'<p class="resp">{r.format(garantia=GARANTIA)}</p></details>'
        for i, (p, r) in enumerate(FAQ))

    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Afiliado Online — uma renda online sem precisar aparecer</title>
<meta name="description" content="Um método passo a passo para construir renda
online no formato faceless: sem mostrar o rosto e sem postar o dia inteiro na
mão.">
<meta name="theme-color" content="{CORES['bg2']}">
<meta property="og:title" content="Afiliado Online">
<meta property="og:description" content="Uma renda online de verdade — sem
precisar aparecer. Um método, não um milagre.">
<meta property="og:type" content="website">
<style>{_css()}</style>

<div class="orbe a"></div><div class="orbe b"></div>

<div class="wrap">

<section class="heroi" id="heroi">
  <span class="olho">Afiliado Online</span>
  <h1>Uma renda online de verdade —<br><span class="g">sem precisar aparecer.</span></h1>
  <p class="lead">A vontade existe. O que trava é quase sempre o mesmo:
  <b>não quero aparecer</b>, <b>não tenho tempo</b>, <b>não sei por onde
  começar</b>. Este é o caminho que resolve os três — construindo um
  <b>sistema que trabalha por você</b>, em vez de você trabalhar o dia inteiro.</p>
  {_botao("Quero começar agora", "grande")}
  <ul class="confia">
    <li>✓ Formato <b>faceless</b></li>
    <li>✓ <b>{len(MODULOS)} módulos</b> · {total_aulas} aulas</li>
    <li>✓ Acesso <b>imediato</b></li>
    <li>✓ <b>{GARANTIA} dias</b> de garantia</li>
  </ul>
</section>

<hr class="div">

<section>
  <span class="olho" data-revela>O que te trouxe aqui</span>
  <h2 data-revela>Você quer — mas <span class="g">trava</span></h2>
  <p data-revela>São quase sempre os mesmos três motivos. E os três têm resposta.</p>
  <ul class="grade">
{travas}
  </ul>
</section>

<section class="faixa">
  <span class="olho" data-revela>O que este curso é</span>
  <h2 data-revela>Um <span class="g">método</span>. Não um milagre.</h2>
  <div class="duas">
    <div class="sim" data-revela><h3>✓ É isto</h3><p>Um sistema real, passo a
      passo, que você constrói e coloca pra rodar. Com ordem, com régua, e com
      o que fazer em cada etapa.</p></div>
    <div class="nao" data-revela style="--atraso:110ms"><h3>✕ Não é isto</h3>
      <p>Promessa de ficar rico da noite pro dia. Resultado vem de execução —
      e a gente é honesto sobre isso desde a primeira aula.</p></div>
  </div>
</section>

<section>
  <span class="olho" data-revela>A máquina</span>
  <h2 data-revela>O que você vai <span class="g">construir</span></h2>
  <p data-revela>Cinco peças que se encaixam. Sozinha, nenhuma funciona.</p>
  <ul class="grade">
{maquina}
  </ul>
</section>

<section class="faixa">
  <span class="olho" data-revela>A grade completa</span>
  <h2 data-revela>{len(MODULOS)} módulos, do <span class="g">zero ao sistema</span></h2>
  <p data-revela>Clique num módulo pra ver as aulas. O <b>Módulo 0 já está
  liberado</b>; os demais entram conforme são gravados — e você
  <b>não paga nada a mais</b> por eles.</p>
  <ul class="mods">
{_modulos_html()}
  </ul>
</section>

<section>
  <span class="olho" data-revela>A parte que ninguém te conta</span>
  <h2 data-revela>A <span class="g">mentalidade</span> que sustenta o resultado</h2>
  <p data-revela>É o que decide quem continua depois do primeiro mês.</p>
  <ul class="grade">
{mental}
  </ul>
</section>

<section class="faixa">
  <span class="olho" data-revela>Antes de decidir</span>
  <h2 data-revela>Isto é <span class="g">pra você</span>?</h2>
  <p data-revela>Prefiro que você saia agora a comprar esperando outra coisa.</p>
  <ul class="quem">
{quem}
  </ul>
</section>

<section>
  <span class="olho" data-revela>Acesso</span>
  <h2 data-revela>Comece <span class="g">hoje</span></h2>
  <div class="preco" data-revela>
    <p class="rot">Curso Afiliado Online · acesso completo</p>
    <div class="valor"><span class="x">{_esc(PARCELAS)}x</span>
      <small>R$</small>{_esc(PARCELA_VALOR)}</div>
    <p class="avista">ou <b>R$ {_esc(PRECO_VISTA)}</b> à vista</p>
    {_botao("Garantir meu acesso", "grande")}
    <span class="selo">Pagamento pela Hotmart · {GARANTIA} dias de garantia ·
      acesso imediato</span>
  </div>
</section>

<section class="faixa">
  <span class="olho" data-revela>Dúvidas</span>
  <h2 data-revela>O que costumam <span class="g">perguntar</span></h2>
  <div class="faq">
{faq}
  </div>
</section>

<hr class="div">

<footer>
  <div><b>Afiliado Online</b> — um método para construir renda online no
  formato faceless.</div>
  <p class="aviso">Este curso ensina um método. Ele não garante resultado,
  ganho ou prazo: o que você alcança depende da sua execução — e a gente diz
  isso na aula, não só aqui embaixo.</p>
</footer>

</div>

<div class="barra" id="barra">
  <div class="b-preco">{_esc(PARCELAS)}x R$ {_esc(PARCELA_VALOR)}
    <span>ou R$ {_esc(PRECO_VISTA)} à vista</span></div>
  {_botao("Quero o curso")}
</div>

<script>{_JS}</script>
"""


def main():
    p = argparse.ArgumentParser(description="Gera a página de vendas do curso.")
    p.add_argument("--saida", default=str(SAIDA_PADRAO))
    args = p.parse_args()

    if not CHECKOUT:
        print("[curso] AVISO: CURSO_CHECKOUT vazio — a página sai com aviso no")
        print("[curso]   lugar do botão. Botão que não compra é pior que")
        print("[curso]   página sem botão.")
    elif "app.hotmart.com" in CHECKOUT or "/manage/" in CHECKOUT:
        print("[curso] ERRO: CURSO_CHECKOUT aponta pro painel de ADMINISTRAÇÃO")
        print("[curso]   da Hotmart. O cliente cairia numa tela de login. Use")
        print("[curso]   o link público (go.hotmart.com/<ID>?dp=1).")
        return 2

    destino = Path(args.saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    pagina = montar()
    destino.write_text(pagina, encoding="utf-8")
    prontos = sum(1 for _, _, ok, _ in MODULOS if ok)
    print(f"[curso] OK {destino}  ({len(pagina)/1024:.1f} KB)")
    print(f"[curso]   {prontos} de {len(MODULOS)} módulos marcados como prontos")
    if CHECKOUT:
        print(f"[curso]   checkout: {CHECKOUT}")
        print("[curso]   parâmetros da URL são repassados (crédito do afiliado)")
    return 0


if __name__ == "__main__":
    try:
        from shared.trava import rodar_unico
    except Exception:
        sys.exit(main())
    sys.exit(rodar_unico("curso_page_builder", main))
