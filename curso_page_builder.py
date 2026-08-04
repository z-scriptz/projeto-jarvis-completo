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
CHECKOUT = os.environ.get("CURSO_CHECKOUT", "").strip()

PRECO = os.environ.get("CURSO_PRECO", "179,90").strip()
PARCELA = os.environ.get("CURSO_PARCELA", "").strip()   # ex.: "12x de R$ 17,90"

CORES = {
    "bg1": "#0c1512", "bg2": "#07100c", "verde": "#12251b",
    "ink": "#eaf0ea", "muted": "#a7b6ab",
    "gold": "#d8b25a", "goldSoft": "#f0d79a", "quente": "#c98a72",
}

# ── CONTEÚDO ────────────────────────────────────────────────────────────────
# Tudo abaixo sai das aulas que EXISTEM (curso/remotion/src/aulas/). Não há
# nada inventado: se uma seção não tem lastro numa aula, ela não está aqui.

TRAVAS = [
    ("Não quero aparecer", "Você não precisa. O método inteiro é feito pra funcionar "
     "sem mostrar o rosto."),
    ("Não tenho tempo", "O trabalho é montar o sistema uma vez. Depois é ele que "
     "roda, não você."),
    ("Não sei por onde começar", "Existe uma ordem. Você vai segui-la, passo a "
     "passo, sem adivinhar nada."),
]

MAQUINA = [
    ("Você não cria. Você <b>conecta</b>.",
     "O conteúdo que converte já existe. O que falta é o sistema que liga uma "
     "peça na outra."),
    ("Vídeos que <b>não mostram você</b>",
     "O formato faceless não é limitação — é o que torna possível produzir em "
     "volume sem depender da sua presença."),
    ("Alcance é <b>volume</b>, não sorte",
     "Um vídeo que estoura é ruído. Muitos vídeos, com método, viram média — e "
     "média dá pra prever."),
    ("Do vídeo até o <b>checkout</b>",
     "O caminho inteiro, sem buraco: onde a pessoa te encontra, o que ela vê "
     "depois, e como ela chega na compra."),
    ("Repita o que o <b>número</b> aprova",
     "Parar de decidir por opinião. O que mediu e funcionou, repete; o que não, "
     "sai."),
]

MENTALIDADE = [
    ("Os primeiros vão ser <b>ruins</b>",
     "E isso está previsto. Quem desiste no quinto vídeo desiste antes da parte "
     "em que o método começa a agir."),
    ("Ninguém pode <b>garantir</b> resultado",
     "Nem eu. Quem garante está vendendo outra coisa. O que dá pra garantir é o "
     "método e a ordem."),
    ("Meta de <b>processo</b>, não de resultado",
     "\"Publicar X vídeos nesta semana\" você controla. \"Faturar Y\" não. A "
     "primeira te move; a segunda te paralisa."),
    ("Compare com <b>você de ontem</b>",
     "A régua é o seu próprio avanço. Comparar com quem começou há dois anos só "
     "serve pra parar."),
]

AULAS_M0 = [
    ("Aula 1", "Bem-vindo",
     "A trava que te trouxe até aqui, por que dá pra fazer sem aparecer, e o que "
     "este curso é — e o que ele não é."),
    ("Aula 2", "A máquina que você vai construir",
     "As peças do sistema e como elas se encaixam. Sozinha, nenhuma funciona."),
    ("Aula 3", "A mentalidade que sustenta o resultado",
     "A parte que ninguém te conta, e que decide quem continua depois do "
     "primeiro mês."),
]

# Repassa TUDO que veio na URL da página pro checkout. É assim que o crédito do
# afiliado sobrevive ao clique — e a razão de a página existir num domínio
# nosso em vez de mandar o afiliado direto pra Hotmart.
_JS_AFILIADO = """
(function(){
  var params = window.location.search;
  if (!params || params.length < 2) return;
  var extra = params.substring(1);
  document.querySelectorAll('a[data-checkout]').forEach(function(a){
    var href = a.getAttribute('href');
    if (!href || href === '#') return;
    a.setAttribute('href', href + (href.indexOf('?') === -1 ? '?' : '&') + extra);
  });
})();
"""


def _esc(t: str) -> str:
    return html.escape(t or "", quote=True)


def _cartoes(itens, classe="cartao") -> str:
    return "\n".join(
        f'      <li class="{classe}"><h3>{t}</h3><p>{d}</p></li>'
        for t, d in itens)


def _botao(texto: str, grande: bool = False) -> str:
    """O botão de compra. Sem checkout configurado ele NÃO vira link morto:
    vira um aviso visível, porque publicar botão que não compra é pior que
    publicar página sem botão."""
    cls = "botao" + (" grande" if grande else "")
    if not CHECKOUT:
        return (f'<span class="{cls} pendente" title="Defina CURSO_CHECKOUT">'
                f'⚠️ checkout não configurado</span>')
    return (f'<a class="{cls}" data-checkout href="{_esc(CHECKOUT)}" '
            f'rel="noopener">{_esc(texto)}</a>')


def montar() -> str:
    c = CORES
    preco_linha = f'<div class="parcela">{_esc(PARCELA)}</div>' if PARCELA else ""
    aulas = "\n".join(
        f'      <li class="aula"><span class="n">{_esc(n)}</span>'
        f'<h3>{_esc(t)}</h3><p>{_esc(d)}</p></li>'
        for n, t, d in AULAS_M0)

    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Afiliado Online — renda online sem precisar aparecer</title>
<meta name="description" content="Um método passo a passo pra construir uma
renda online no formato faceless: sem mostrar o rosto e sem postar o dia
inteiro na mão.">
<style>
:root{{
  --bg1:{c['bg1']}; --bg2:{c['bg2']}; --verde:{c['verde']};
  --ink:{c['ink']}; --muted:{c['muted']};
  --gold:{c['gold']}; --goldSoft:{c['goldSoft']}; --quente:{c['quente']};
}}
*{{box-sizing:border-box}}
body{{margin:0;background:linear-gradient(160deg,var(--bg1),var(--bg2));
  color:var(--ink);font:16px/1.65 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}}
.wrap{{max-width:1060px;margin:0 auto;padding:0 22px}}
section{{padding:64px 0;border-top:1px solid rgba(216,178,90,.13)}}
section:first-of-type{{border-top:0}}
h1,h2,h3{{line-height:1.2;margin:0 0 14px}}
h1{{font-size:clamp(30px,5.6vw,52px);letter-spacing:-.02em}}
h2{{font-size:clamp(23px,3.4vw,33px);letter-spacing:-.01em}}
h3{{font-size:18px}}
p{{margin:0 0 14px;color:var(--muted)}}
b{{color:var(--goldSoft);font-weight:600}}
.olho{{font:600 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.16em;text-transform:uppercase;color:var(--gold);
  margin-bottom:16px;display:block}}
.g{{color:var(--gold)}}

/* herói */
.heroi{{padding:76px 0 60px;position:relative;overflow:hidden}}
.heroi::after{{content:"";position:absolute;inset:auto -20% -55% 40%;height:460px;
  background:radial-gradient(closest-side,rgba(216,178,90,.14),transparent 72%);
  pointer-events:none}}
.heroi p.lead{{font-size:clamp(17px,2.3vw,21px);max-width:62ch}}

/* listas em cartão */
ul.grade{{list-style:none;display:grid;gap:16px;padding:0;margin:26px 0 0;
  grid-template-columns:repeat(auto-fit,minmax(268px,1fr))}}
.cartao,.aula{{background:rgba(18,37,27,.55);border:1px solid rgba(216,178,90,.16);
  border-radius:15px;padding:22px}}
.cartao h3{{color:var(--ink)}}
.cartao p,.aula p{{margin:0;font-size:15px}}
.aula .n{{font:600 11px/1 ui-monospace,Menlo,monospace;letter-spacing:.14em;
  color:var(--gold);text-transform:uppercase;display:block;margin-bottom:9px}}

/* é / não é */
.duas{{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(276px,1fr));
  margin-top:26px}}
.duas>div{{border-radius:15px;padding:24px;border:1px solid rgba(216,178,90,.16);
  background:rgba(18,37,27,.55)}}
.duas .nao{{border-color:rgba(201,138,114,.3)}}
.duas .nao h3{{color:var(--quente)}}
.duas h3{{color:var(--gold)}}

/* preço */
.preco{{text-align:center;background:rgba(18,37,27,.6);
  border:1px solid rgba(216,178,90,.24);border-radius:19px;padding:38px 24px;
  margin-top:26px}}
.valor{{font-size:clamp(38px,7vw,60px);font-weight:700;color:var(--goldSoft);
  letter-spacing:-.02em;line-height:1}}
.valor small{{font-size:.42em;font-weight:600;color:var(--gold);
  vertical-align:.85em;margin-right:5px}}
.parcela{{color:var(--muted);margin-top:8px;font-size:15px}}

/* botão */
.botao{{display:inline-block;margin-top:22px;padding:16px 34px;border-radius:999px;
  background:linear-gradient(135deg,var(--gold),var(--goldSoft));color:#14200f;
  font-weight:700;text-decoration:none;font-size:16px;
  box-shadow:0 10px 28px rgba(216,178,90,.2);transition:transform .16s ease}}
.botao:hover{{transform:translateY(-2px)}}
.botao.grande{{font-size:18px;padding:19px 44px}}
.botao.pendente{{background:rgba(201,138,114,.2);color:var(--quente);
  border:1px dashed var(--quente);box-shadow:none;cursor:not-allowed}}
.selo{{display:block;margin-top:14px;font-size:13px;color:var(--muted)}}

footer{{padding:44px 0 58px;color:var(--muted);font-size:13.5px;
  border-top:1px solid rgba(216,178,90,.13)}}
@media (prefers-reduced-motion:reduce){{*{{transition:none!important}}}}
</style>

<div class="wrap">

<section class="heroi">
  <span class="olho">Afiliado Online</span>
  <h1>Uma renda online de verdade —<br><span class="g">sem precisar aparecer.</span></h1>
  <p class="lead">A vontade existe. O que trava é quase sempre o mesmo:
  <b>não quero aparecer</b>, <b>não tenho tempo</b>, <b>não sei por onde
  começar</b>. Este curso é o caminho que resolve os três — construindo um
  <b>sistema que trabalha por você</b>, em vez de você trabalhar o dia inteiro.</p>
  {_botao("Quero começar", grande=True)}
  <span class="selo">Método passo a passo · formato faceless · acesso imediato</span>
</section>

<section>
  <span class="olho">O que te trouxe aqui</span>
  <h2>Você quer — mas <span class="g">trava</span></h2>
  <ul class="grade">
{_cartoes([(t, d) for t, d in TRAVAS])}
  </ul>
</section>

<section>
  <span class="olho">O que este curso é</span>
  <h2>Um <span class="g">método</span>. Não um milagre.</h2>
  <div class="duas">
    <div><h3>É isto</h3><p>Um sistema real, passo a passo, que você constrói e
      coloca pra rodar. Com ordem, com régua e com o que fazer em cada etapa.</p></div>
    <div class="nao"><h3>Não é isto</h3><p>Promessa de ficar rico da noite pro
      dia. Resultado vem de execução — e a gente é honesto sobre isso desde a
      primeira aula.</p></div>
  </div>
</section>

<section>
  <span class="olho">A máquina</span>
  <h2>O que você vai <span class="g">construir</span></h2>
  <p>Peças que se encaixam. Sozinha, nenhuma funciona.</p>
  <ul class="grade">
{_cartoes(MAQUINA)}
  </ul>
</section>

<section>
  <span class="olho">A parte que ninguém te conta</span>
  <h2>A <span class="g">mentalidade</span> que sustenta o resultado</h2>
  <ul class="grade">
{_cartoes(MENTALIDADE)}
  </ul>
</section>

<section>
  <span class="olho">Começa aqui</span>
  <h2>Módulo 0 — <span class="g">a base</span></h2>
  <p>Três aulas que colocam você na direção certa antes da primeira execução.</p>
  <ul class="grade">
{aulas}
  </ul>
</section>

<section>
  <span class="olho">Acesso</span>
  <h2>Comece <span class="g">hoje</span></h2>
  <div class="preco">
    <div class="valor"><small>R$</small>{_esc(PRECO)}</div>
    {preco_linha}
    {_botao("Garantir meu acesso", grande=True)}
    <span class="selo">Pagamento processado pela Hotmart</span>
  </div>
</section>

<footer>
  <div><b>Afiliado Online</b> — um método para construir renda online no formato
  faceless.</div>
  <p style="margin-top:10px">Este curso ensina um método. Ele não garante
  resultado, ganho ou prazo: o que você alcança depende da sua execução — e a
  gente diz isso na aula, não só aqui embaixo.</p>
</footer>

</div>
<script>{_JS_AFILIADO}</script>
"""


def main() -> int:
    p = argparse.ArgumentParser(description="Gera a página de vendas do curso.")
    p.add_argument("--saida", default=str(SAIDA_PADRAO))
    args = p.parse_args()

    if not CHECKOUT:
        print("[curso] ⚠️  CURSO_CHECKOUT vazio — a página sai com AVISO no lugar")
        print("[curso]    do botão, de propósito: botão que não compra é pior")
        print("[curso]    que página sem botão. Use o link PÚBLICO da Hotmart")
        print("[curso]    (pay.hotmart.com/...), não o de app.hotmart.com/manage.")
    elif "app.hotmart.com" in CHECKOUT or "/manage/" in CHECKOUT:
        print("[curso] ❌ CURSO_CHECKOUT aponta pro painel de ADMINISTRAÇÃO da")
        print("[curso]    Hotmart. O cliente cairia numa tela de login. Pegue o")
        print("[curso]    link público de checkout do produto.")
        return 2

    destino = Path(args.saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    pagina = montar()
    destino.write_text(pagina, encoding="utf-8")
    print(f"[curso] ✅ {destino}  ({len(pagina)/1024:.1f} KB)")
    if CHECKOUT:
        print(f"[curso]    checkout: {CHECKOUT}")
        print("[curso]    parâmetros da URL são repassados pro checkout "
              "(crédito do afiliado)")
    return 0


if __name__ == "__main__":
    try:
        from shared.trava import rodar_unico
    except Exception:
        sys.exit(main())
    sys.exit(rodar_unico("curso_page_builder", main))
