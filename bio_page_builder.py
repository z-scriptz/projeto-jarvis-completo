# creative_engine/bio_page_builder.py
# Gera o SITE INSTITUCIONAL da TopShop (hero, diferenciais, serviços, vitrine,
# contato, footer) com a VITRINE AUTOMÁTICA injetada: destaque do dia + busca +
# filtros por categoria + grade 3 colunas com imagem e link de afiliado.
#
# A casca institucional é fixa (identidade da marca). Só a vitrine é dinâmica:
# lê os produtos curados, minera o link de afiliado e a imagem, e monta os cards.
#
# Hospedar: HTML estático puro, custo zero no GitHub Pages.
# Rastreamento: sub-IDs nos links da Shopee (painel de afiliado mostra cliques).

import os
import re
import sys
import json
import html
import time
import argparse
from pathlib import Path

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("bio_page_builder")

SAIDA_HTML = Path(__file__).parent.parent / "site" / "index.html"
JSON_FILA = Path(__file__).parent.parent / "shared" / "produtos_fila.json"
VALIDACAO = Path(__file__).parent.parent / "shared" / "content_plans" / "validacao_fila.json"

# ===== Contatos e redes (edite com os teus dados reais) =====
WHATSAPP = ""
EMAIL = "jhon-henrique2018@hotmail.com"
INSTAGRAM = "https://www.instagram.com/topshop.__/"
TIKTOK = "https://www.tiktok.com/@topshop.__"
YOUTUBE = "https://www.youtube.com/@TopShop._0"
# Grupos de achadinhos (preencha quando criar; vazio = não aparece)
GRUPO_WHATSAPP = "https://chat.whatsapp.com/G0DPGQV0rRc1tFRWIwOjrv"
GRUPO_TELEGRAM = "https://t.me/achadinhosrelampagoh"


# ===== Categorias pros filtros (inferidas pelo nome) =====
# Ordem FIXA das categorias no filtro da vitrine (sempre aparecem, mesmo sem
# produto no momento — assim a loja fica organizada e a categoria não "some").
# "Tudo" e "Outros" são adicionados automaticamente pelo _filtros_html.
_CATEGORIAS_FIXAS = ["Cozinha", "Beleza", "Tech", "Fitness", "Moda", "Pet",
                     "Utilidades", "Casa"]

# Palavras-chave por categoria (o produto cai na 1ª que casar — ordem importa).
_CATEGORIAS_FILTRO = [
    # Pet PRIMEIRO: evita que "Tablete" (comprimido) case com "tablet" (Tech) e
    # dá nicho próprio pro que é de bicho (antes só caía em Utilidades/Tech).
    ("Pet",        ("antipulgas", "carrapato", "vermifugo", "vermífugo", "ração",
                    "racao", "coleira", "comedouro", "bebedouro", "cachorro",
                    "cão", "cães", "gato", "gatos", "filhote", "petisco",
                    "arranhador", "aquário", "aquario", "canino", "felino",
                    "pets")),   # "pets" e não "pet": "pet" pegaria "petisco"
    ("Cozinha",    ("cortador", "legumes", "liquidificador", "balanca", "balança",
                    "garrafa", "caneca", "termica", "térmica", "descascador",
                    "processador", "fatiador", "espremedor", "água", "agua",
                    "panela", "faca", "prato", "copo", "tigela", "ralador",
                    "forma", "air fryer", "fritadeira", "tábua", "tabua", "pote",
                    "mixer", "sanduicheira", "cafeteira", "chaleira", "talher",
                    "colher")),
    ("Beleza",     ("modelador", "cachos", "escova", "secadora", "alisadora",
                    "maquiagem", "skincare", "cravos", "espelho", "cabelo",
                    "unha", "perfume", "batom", "esmalte", "depilador",
                    "barbeador", "sobrancelha", "pelos", "hidratante", "make")),
    ("Fitness",    ("massageador", "massagem", "yoga", "pilates", "faixas",
                    "corda", "pular", "cervical", "fisioterapia", "academia",
                    "treino", "elastica", "elástica", "halter", "abdominal",
                    "musculac", "musculaç", "luva de treino")),
    # Moda DEPOIS de Fitness: "Kit 2 Shorts Femininos Academia Yoga" é roupa,
    # mas quem procura isso procura em Fitness. Antes daqui não havia categoria
    # de roupa/calçado nenhuma e sandália, scarpin, vestido e cropped caíam
    # todos em "Outros" — 7 produtos da fila real.
    ("Moda",       ("sandalia", "sandália", "sapato", "tenis", "tênis",
                    "scarpin", "papete", "babuche", "chinelo", "bota",
                    "sapatilha", "rasteirinha", "salto", "vestido", "blusa",
                    "camiseta", "camisa", "cropped", "calça", "calca", "saia",
                    "macacao", "macacão", "moletom", "jaqueta", "casaco",
                    "legging", "pijama", "biquini", "biquíni", "sutia",
                    "sutiã", "lingerie", "bolsa", "mochila", "carteira",
                    "cinto", "boné", "bone", "chapeu", "chapéu", "oculos",
                    "óculos", "bermuda", "conjunto feminino")),
    ("Tech",       ("mouse", "power bank", "powerbank", "carregador", "projetor",
                    "notebook", "cabo", "fone", "usb", "celular", "induç",
                    "induc", "teclado", "headset", "camera", "câmera",
                    "ring light", "microfone", "smartwatch", "relogio",
                    "relógio", "tablet", "ssd", "pendrive", "bluetooth",
                    "monitor", "adaptador", "hub", "roteador", "smart",
                    "led rgb", "xbox", "playstation", "nintendo", "ps4", "ps5",
                    "console", "gamer", "joystick", "controle de", "videogame",
                    "video game", "dualshock")),
    ("Utilidades", ("organizador", "gancho", "cabide", "sacola", "cesto",
                    "balde", "lixeira", "pedal", "litro", "caixa", "mala",
                    "guarda-chuva", "ferramenta", "chave", "mangueira", "varal",
                    "pinça", "pinca", "fita", "adesivo",
                    "bebê", "bebe", "criança", "crianca", "infantil",
                    "brinquedo", "fralda", "automotivo", "veicular", "carro",
                    "moto", "pneu")),
    ("Casa",       ("umidificador", "luminaria", "luminária", "led", "aspirador",
                    "tapete", "vela", "porta", "suporte", "prateleira",
                    "cortina", "toalha", "almofada", "edredom", "lençol",
                    "lencol", "vaso", "limpeza", "pano", "capacho", "difusor",
                    "quadro")),
]


# A palavra-chave tem que começar no COMEÇO de uma palavra. Sem isso,
# "plataFORMA" casava com "forma" e mandava sandália pra Cozinha, e "maCACÃO"
# casava com "cão" e mandava roupa pra Pet — os dois vistos na fila real.
# Sem \b no fim, de propósito: "induç" precisa pegar "indução" e "escova"
# precisa pegar "escovas".
_CATEGORIAS_RE = [
    (rotulo, re.compile(r"\b(?:" + "|".join(re.escape(k) for k in kws) + r")",
                        re.IGNORECASE))
    for rotulo, kws in _CATEGORIAS_FILTRO
]


def _inferir_categoria(p: dict) -> str:
    texto = f"{p.get('nome','')} {p.get('titulo','')}"
    for rotulo, rx in _CATEGORIAS_RE:
        if rx.search(texto):
            return rotulo
    return "Outros"


# O nome que chega na fila é o TERMO que o extrator tirou do vídeo, não o nome
# do produto. Às vezes ele pega o texto errado do anúncio: na fila real havia
# "2 mil vendidos" e "60 mil vendidos" — produto com link bom e card que
# ninguém clica. Quando isso acontece, o título OFICIAL da Shopee (que o
# historico_precos já guardou) entra no lugar.
#
# Só casa quando a string INTEIRA é número/contagem. "6 Pçs/set Kawaii Animal"
# e "20/30/50 Nécessaire" começam com número e são nomes de verdade — medido
# na fila de produção, 2 nomes ruins em 80, sem falso positivo.
_SO_NUMERO = re.compile(
    r"^\s*(r\$\s*)?[\d.,]+\s*(mil|k|m)?\s*"
    r"(vendidos?|vendas?|avalia\w*|un|unidades?|reais|off|%)?\s*$",
    re.IGNORECASE)


def _nome_ruim(t: str) -> bool:
    """Nome que não diz nada pro comprador. Não apaga nada: só decide se vale
    a pena preferir o título oficial da loja."""
    t = (t or "").strip()
    if not t or _SO_NUMERO.match(t):
        return True
    if not re.search(r"[A-Za-zÀ-ÿ]{3}", t):
        return True
    return len(re.findall(r"[A-Za-zÀ-ÿ]{3,}", t)) < 3


def _corrigir_titulos(produtos: list) -> list:
    """Troca nome ruim pelo título oficial da Shopee, quando existe.

    Mexe no `titulo` e no `nome`, não só no que aparece no card: a categoria do
    filtro e a busca da vitrine saem daí também, e um produto chamado "2 mil
    vendidos" caía em 'Outros' e não era encontrado por busca nenhuma.
    """
    trocados = 0
    for p in produtos:
        oficial = (p.get("titulo_oficial") or "").strip()
        if not oficial or _nome_ruim(oficial):
            continue
        if _nome_ruim(p.get("titulo") or p.get("nome", "")):
            p["titulo"] = oficial
            p["nome"] = oficial
            trocados += 1
    if trocados:
        log.info(f"   🏷️  {trocados} nome(s) sem sentido trocado(s) pelo "
                 f"título oficial da Shopee")
    return produtos


def _titulo_legivel(titulo: str, limite: int = 64) -> str:
    t = re.sub(r"\s+", " ", (titulo or "").strip())
    if len(t) <= limite:
        return t
    return t[:limite].rsplit(" ", 1)[0] + "…"


def _carregar_produtos() -> list:
    """Junta as fontes SEM duplicar. PRIORIDADE pros produtos que o Jarvis
    REALMENTE postou (produtos_fila.json — já vêm com o link de afiliado, mais
    recente primeiro); depois complementa com a curadoria (validacao_fila)."""
    produtos = []
    vistos = set()

    def _add(p):
        chave = (p.get("link") or "").strip() or (p.get("nome") or "").strip().lower()
        if not chave or chave in vistos:
            return
        vistos.add(chave)
        produtos.append(p)

    # 1) PRIORIDADE: produtos_fila.json (o que foi postado — com link pronto)
    if JSON_FILA.exists():
        try:
            with open(JSON_FILA, encoding="utf-8") as f:
                fila = json.load(f)
            for item in fila:
                if isinstance(item, dict):
                    _add({
                        "nome": item.get("produto", ""),
                        "titulo": item.get("campeao", "") or item.get("produto", ""),
                        "classe": item.get("classe", ""),
                        "comissao_valor": item.get("comissao_valor", 0) or 0,
                        "imagem": item.get("imagem", ""),
                        "link": item.get("link", ""),
                        "plataforma": (item.get("plataforma") or "shopee").lower(),
                        # preço do dia em que o produto entrou. Serve de ponto
                        # de partida até o histórico ter leituras suficientes
                        # pra virar média (historico_precos.enriquecer).
                        "preco": item.get("preco", 0) or 0,
                    })
                elif isinstance(item, str):
                    _add({"nome": item, "titulo": item, "classe": "",
                          "comissao_valor": 0, "imagem": "", "link": "",
                          "plataforma": "shopee", "preco": 0})
        except Exception as e:
            log.warning(f"   erro lendo fila JSON: {e}")

    # 2) COMPLEMENTO: validacao_fila.json (curadoria), sem duplicar
    if VALIDACAO.exists():
        try:
            with open(VALIDACAO, encoding="utf-8") as f:
                rel = json.load(f)
            for p in rel.get("produtos", []):
                if p.get("classe") in ("mina_ouro", "ok") and p.get("campeao"):
                    _add({
                        "nome": p.get("produto", ""),
                        "titulo": p.get("campeao", ""),
                        "classe": p.get("classe", ""),
                        "comissao_valor": p.get("comissao_valor", 0),
                        "imagem": "", "link": "", "plataforma": "shopee",
                        "preco": p.get("preco", 0) or 0,
                    })
        except Exception as e:
            log.warning(f"   erro lendo validação: {e}")

    return produtos


def _gerar_links_afiliado(produtos: list) -> list:
    try:
        from integrations.shopee_affiliate import minerar_oportunidades, gerar_link_afiliado
    except Exception:
        log.info("   Shopee indisponível — usando só os links existentes")
        return [p for p in produtos if p.get("link")]
    com_link = []
    for p in produtos:
        if p.get("link"):
            com_link.append(p)
            continue
        try:
            m = minerar_oportunidades(p["nome"])
            if m.get("ok"):
                origem = m["campeao"].get("product_link") or m["campeao"].get("offer_link")
                if origem:
                    sub = ["bio", re.sub(r"\W+", "", p["nome"])[:12]]
                    lk = gerar_link_afiliado(origem, sub_ids=sub)
                    if lk.get("ok"):
                        p["link"] = lk["short_link"]
                        p["titulo"] = m["campeao"].get("nome", p["titulo"])
                        p["imagem"] = m["campeao"].get("imagem", "") or p.get("imagem", "")
                        p["preco"] = m["campeao"].get("preco", 0) or p.get("preco", 0)
                        com_link.append(p)
                        log.info(f"   🔗 link gerado: {p['nome']}")
                        time.sleep(1.0)
                        continue
            log.info(f"   ⏭️  sem link pra '{p['nome']}' (omitido)")
        except Exception as e:
            log.warning(f"   erro em '{p['nome']}': {str(e)[:50]}")
    return com_link


def _card_destaque(p: dict) -> str:
    titulo = html.escape(_titulo_legivel(p.get("titulo") or p.get("nome", "")))
    nome = html.escape(p.get("nome", ""))
    link = html.escape(p.get("link", "#"))
    cat = html.escape(_inferir_categoria(p))
    img = html.escape(p.get("imagem", ""))
    plat = (p.get("plataforma") or "shopee").lower()
    ph_emoji = "📦" if plat == "amazon" else "🛍️"
    badge = "📦 Amazon" if plat == "amazon" else "🛒 Shopee"
    img_html = (f'<img src="{img}" alt="{titulo}" loading="lazy" '
                f'onerror="this.style.display=\'none\'">') if img else ""
    return f"""
    <a class="prod-destaque" href="{link}" target="_blank" rel="noopener"
       data-busca="{titulo.lower()} {nome.lower()}" data-categoria="{cat}"
       data-plataforma="{plat}">
      <div class="pd-img">{img_html}<span class="pd-ph">{ph_emoji}</span>
        <span class="selo">⭐ Produto do dia</span>
        <span class="plat-badge plat-{plat}">{badge}</span></div>
      <div class="pd-body">
        <h3>{titulo}</h3>
        <span class="pd-cta">🛒 PEGAR MEU DESCONTO</span>
      </div>
    </a>"""


def _card_grid(p: dict) -> str:
    titulo = html.escape(_titulo_legivel(p.get("titulo") or p.get("nome", "")))
    nome = html.escape(p.get("nome", ""))
    link = html.escape(p.get("link", "#"))
    cat = html.escape(_inferir_categoria(p))
    img = html.escape(p.get("imagem", ""))
    plat = (p.get("plataforma") or "shopee").lower()
    ph_emoji = "📦" if plat == "amazon" else "🛍️"
    badge = "📦 Amazon" if plat == "amazon" else "🛒 Shopee"
    img_html = (f'<img src="{img}" alt="{titulo}" loading="lazy" '
                f'onerror="this.style.display=\'none\'">') if img else ""
    return f"""
      <a class="glass prod" href="{link}" target="_blank" rel="noopener"
         data-busca="{titulo.lower()} {nome.lower()}" data-categoria="{cat}"
         data-plataforma="{plat}">
        <div class="thumb">{img_html}<span class="pd-ph">{ph_emoji}</span>
          <span class="selo">Achado topshop</span>
          <span class="plat-badge plat-{plat}">{badge}</span></div>
        <div class="body">
          <h3>{titulo}</h3>
          <span class="ver">Ver oferta →</span>
        </div>
      </a>"""


def _filtros_html(produtos: list) -> str:
    # Barra FIXA: Tudo + categorias fixas (sempre visíveis) + Outros (só se
    # houver algum produto sem categoria). Clicar numa categoria vazia mostra
    # o "nenhum produto encontrado" — normal, é a loja se enchendo aos poucos.
    presentes = {_inferir_categoria(p) for p in produtos}
    ordem = ["todos"] + list(_CATEGORIAS_FIXAS)
    if "Outros" in presentes:
        ordem.append("Outros")
    botoes = []
    for c in ordem:
        rotulo = "Tudo" if c == "todos" else c
        ativo = " ativo" if c == "todos" else ""
        botoes.append(f'<button class="filtro{ativo}" data-filtro="{html.escape(c)}">'
                      f'{html.escape(rotulo)}</button>')
    return '<div class="filtros" id="filtros">' + "".join(botoes) + "</div>"


def _toggle_plataforma_html(produtos: list) -> str:
    """Toggle 🛒 Shopee / 📦 Amazon — só aparece se houver produto de mais de
    uma plataforma (senão não polui a barra)."""
    plats = {(p.get("plataforma") or "shopee").lower() for p in produtos}
    if len(plats) < 2:
        return ""
    botoes = [
        '<button class="filtro-plat ativo" data-plat="todos">Tudo</button>',
        '<button class="filtro-plat" data-plat="shopee">🛒 Shopee</button>',
        '<button class="filtro-plat" data-plat="amazon">📦 Amazon</button>',
    ]
    return ('<div class="filtros filtros-plat" id="filtros-plat">'
            + "".join(botoes) + "</div>")


def _vitrine_html(produtos: list) -> str:
    """Monta a vitrine completa: busca + toggle plataforma + filtros + destaque + grade."""
    if not produtos:
        return '<p style="text-align:center;color:var(--muted);padding:40px 0;">Em breve, novos achados ✨</p>'
    busca = ('<div class="busca-wrap">'
             '<input id="busca" type="search" placeholder="🔍 Buscar produto do vídeo..." '
             'autocomplete="off"></div>')
    toggle = _toggle_plataforma_html(produtos)
    filtros = _filtros_html(produtos)
    destaque = _card_destaque(produtos[0])
    grade_cards = "\n".join(_card_grid(p) for p in produtos[1:])
    grade = f'<div class="grid-3" id="grade-prod">{grade_cards}</div>' if grade_cards else ""
    sem = '<p class="sem-res" id="sem-res" style="display:none;text-align:center;color:var(--muted);padding:24px;">Nenhum produto encontrado 🔍</p>'
    return busca + toggle + filtros + destaque + grade + sem


def _grupos_html() -> str:
    """Linha extra de grupos de achadinhos no contato (se configurados)."""
    itens = []
    if GRUPO_WHATSAPP:
        itens.append(f'<div class="ci"><div class="ico">👥</div><span>Grupo no WhatsApp: '
                     f'<a href="{html.escape(GRUPO_WHATSAPP)}" target="_blank">Entrar no grupo</a></span></div>')
    if GRUPO_TELEGRAM:
        itens.append(f'<div class="ci"><div class="ico">📨</div><span>Canal no Telegram: '
                     f'<a href="{html.escape(GRUPO_TELEGRAM)}" target="_blank">Entrar no canal</a></span></div>')
    return "".join(itens)


def gerar_site(produtos: list) -> str:
    _corrigir_titulos(produtos)
    vitrine = _vitrine_html(produtos)
    grupos = _grupos_html()
    total = len(produtos)
    ano = time.strftime("%Y")
    data = time.strftime("%d/%m/%Y")
    return _TEMPLATE.replace("{{VITRINE}}", vitrine)\
                    .replace("{{GRUPOS}}", grupos)\
                    .replace("{{TOTAL}}", str(total))\
                    .replace("{{ANO}}", ano)\
                    .replace("{{DATA}}", data)\
                    .replace("{{WHATSAPP}}", WHATSAPP)\
                    .replace("{{EMAIL}}", EMAIL)\
                    .replace("{{INSTAGRAM}}", INSTAGRAM)\
                    .replace("{{TIKTOK}}", TIKTOK)\
                    .replace("{{YOUTUBE}}", YOUTUBE)


# ===== Template do site institucional (casca fixa + {{VITRINE}} dinâmica) =====
_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>topshop · Produtos inteligentes. Conteúdo estratégico.</title>
<link rel="icon" type="image/png" href="/favicon-96x96.png?v=v1" sizes="96x96" />
<link rel="shortcut icon" href="/favicon.ico?v=v1" />
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png?v=v1" />
<meta name="apple-mobile-web-app-title" content="TopShop" />
<link rel="manifest" href="/site.webmanifest?v=v1" />
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  :root {
    --bg: #0a0a12; --bg-soft: #12121f; --ink: #f4f4f8; --muted: #9a9ab0;
    --pop: #6d5dfc; --pop2: #00d4ff; --gold: #ffc83d; --cta: #00e0b8;
    --grad: linear-gradient(135deg, #6d5dfc 0%, #00d4ff 100%);
    --glass: rgba(255,255,255,0.04); --glass-border: rgba(255,255,255,0.10);
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html { scroll-behavior: smooth; overflow-x: hidden; max-width: 100%; }
  body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background: var(--bg); color: var(--ink); line-height: 1.6;
    -webkit-font-smoothing: antialiased; overflow-x: hidden;
    max-width: 100%; position: relative; }
  .wrap { max-width: 1140px; margin: 0 auto; padding: 0 24px; }
  a { color: inherit; text-decoration: none; }
  @media (prefers-reduced-motion: no-preference) {
    .reveal { opacity: 0; transform: translateY(24px);
              transition: opacity 0.7s ease, transform 0.7s ease; }
    .reveal.in { opacity: 1; transform: none; }
  }
  nav { position: sticky; top: 0; z-index: 100;
    background: rgba(10,10,18,0.72); backdrop-filter: blur(14px);
    border-bottom: 1px solid var(--glass-border); }
  .nav-in { display: flex; justify-content: space-between; align-items: center;
            padding: 16px 24px; max-width: 1140px; margin: 0 auto; }
  .logo { font-weight: 800; font-size: 1.3rem; letter-spacing: -0.02em; }
  .logo b { background: var(--grad); -webkit-background-clip: text;
            background-clip: text; color: transparent; }
  .nav-links { display: flex; gap: 28px; }
  .nav-links a { color: var(--muted); font-weight: 600; font-size: 0.92rem;
                 transition: color 0.2s; }
  .nav-links a:hover { color: var(--ink); }
  @media (max-width: 760px) { .nav-links { display: none; } }
  .hero { position: relative; text-align: center; padding: 110px 0 90px; overflow: hidden; }
  .hero::before { content: ''; position: absolute; top: -10%; left: 50%;
    transform: translateX(-50%); width: min(700px, 100vw); height: min(700px, 100vw);
    max-width: 100%; background: radial-gradient(circle, rgba(109,93,252,0.22) 0%, transparent 60%);
    z-index: -1; animation: float 8s ease-in-out infinite; pointer-events: none; }
  @keyframes float { 0%,100% { transform: translateX(-50%) translateY(0); }
                     50% { transform: translateX(-50%) translateY(-24px); } }
  .badge { display: inline-block; background: var(--glass);
    border: 1px solid var(--glass-border); color: var(--pop2);
    font-weight: 600; font-size: 0.82rem; letter-spacing: 0.06em;
    padding: 8px 18px; border-radius: 100px; margin-bottom: 30px;
    text-transform: uppercase; }
  .hero h1 { font-size: clamp(2.6rem, 6.5vw, 5rem); font-weight: 800;
             letter-spacing: -0.03em; line-height: 1.04; margin-bottom: 26px; }
  .hero h1 b { background: var(--grad); -webkit-background-clip: text;
               background-clip: text; color: transparent; }
  .hero p { font-size: 1.22rem; color: var(--muted); max-width: 600px;
            margin: 0 auto 40px; }
  .hero-cta { display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; }
  .btn { display: inline-flex; align-items: center; gap: 8px;
    font-weight: 700; font-size: 1rem; padding: 15px 32px;
    border-radius: 100px; cursor: pointer; border: none;
    transition: transform 0.18s ease, box-shadow 0.18s ease; }
  .btn-primary { background: var(--grad); color: #fff;
                 box-shadow: 0 8px 30px rgba(109,93,252,0.4); }
  .btn-primary:hover { transform: translateY(-2px);
                       box-shadow: 0 14px 40px rgba(109,93,252,0.55); }
  .btn-ghost { background: var(--glass); color: var(--ink);
               border: 1px solid var(--glass-border); }
  .btn-ghost:hover { transform: translateY(-2px); border-color: var(--pop2); }
  section { padding: 90px 0; }
  .eyebrow { color: var(--pop2); font-weight: 700; font-size: 0.85rem;
             letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 14px; }
  .sec-title { font-size: clamp(2rem, 4.5vw, 3rem); font-weight: 800;
               letter-spacing: -0.02em; margin-bottom: 18px; }
  .sec-sub { color: var(--muted); font-size: 1.12rem; max-width: 600px;
             margin-bottom: 56px; }
  .center { text-align: center; }
  .center .sec-sub { margin-left: auto; margin-right: auto; }
  .glass { background: var(--glass); border: 1px solid var(--glass-border);
    border-radius: 20px; backdrop-filter: blur(12px);
    transition: transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease; }
  .glass:hover { transform: translateY(-6px); border-color: rgba(109,93,252,0.5);
                 box-shadow: 0 20px 50px rgba(0,0,0,0.4); }
  .grid-3 { display: grid; grid-template-columns: repeat(3,1fr); gap: 24px; }
  .grid-2 { display: grid; grid-template-columns: repeat(2,1fr); gap: 24px; }
  @media (max-width: 860px) { .grid-3, .grid-2 { grid-template-columns: 1fr 1fr; } }
  /* no celular os cards de PRODUTO ficam 2-por-linha (menores/mais "shopáveis");
     só os cards de texto (grid-2) é que passam pra 1 coluna. */
  @media (max-width: 560px) {
    .grid-2 { grid-template-columns: 1fr; }
    .grid-3 { grid-template-columns: 1fr 1fr; gap: 12px; }
  }
  .feat { padding: 32px 28px; }
  .feat .ico { width: 46px; height: 46px; border-radius: 12px;
               background: var(--grad); display: flex; align-items: center;
               justify-content: center; margin-bottom: 18px; font-size: 1.3rem; }
  .feat h3 { font-size: 1.15rem; font-weight: 700; margin-bottom: 8px; }
  .feat p { color: var(--muted); font-size: 0.96rem; }
  .difs { display: grid; grid-template-columns: repeat(2,1fr); gap: 14px 32px; margin-top: 10px; }
  @media (max-width: 760px) { .difs { grid-template-columns: 1fr; } }
  .dif { display: flex; align-items: center; gap: 14px; padding: 16px 0;
         border-bottom: 1px solid var(--glass-border); }
  .dif .check { color: var(--pop2); font-weight: 800; font-size: 1.1rem; }
  .dif span:last-child { font-weight: 600; }
  /* ===== Vitrine (busca + filtros + destaque + grade) ===== */
  .busca-wrap { max-width: 560px; margin: 0 auto 18px; }
  #busca { width: 100%; padding: 14px 18px; border-radius: 14px;
    border: 1px solid var(--glass-border); background: var(--glass);
    color: var(--ink); font-size: 1rem; outline: none; font-family: inherit;
    transition: border-color .2s, box-shadow .2s; }
  #busca:focus { border-color: var(--pop); box-shadow: 0 0 0 3px rgba(109,93,252,0.25); }
  #busca::placeholder { color: var(--muted); }
  .filtros { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-bottom: 40px; }
  .filtros-plat { margin-bottom: 16px; }
  .filtro, .filtro-plat { background: var(--glass); color: var(--muted);
    border: 1px solid var(--glass-border); border-radius: 100px;
    padding: 8px 18px; font-size: 0.88rem; font-weight: 600; cursor: pointer;
    transition: all .2s; font-family: inherit; }
  .filtro:hover, .filtro-plat:hover { color: var(--ink); border-color: var(--pop2); }
  .filtro.ativo, .filtro-plat.ativo { background: var(--grad); color: #fff; border-color: transparent;
    box-shadow: 0 6px 20px rgba(109,93,252,0.4); }
  .plat-badge { position: absolute; top: 14px; right: 14px; z-index: 2;
    font-size: 0.62rem; font-weight: 800; letter-spacing: .3px;
    padding: 4px 9px; border-radius: 100px; color: #fff; white-space: nowrap;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3); }
  .plat-shopee { background: #ee4d2d; }
  .plat-amazon { background: #ff9900; color: #131a22; }
  .prod-destaque { display: grid; grid-template-columns: 1fr 1fr; gap: 0;
    background: linear-gradient(135deg, rgba(109,93,252,0.12), var(--glass));
    border: 1px solid var(--pop); border-radius: 24px; overflow: hidden;
    margin-bottom: 50px; box-shadow: 0 0 40px rgba(109,93,252,0.25);
    transition: transform .2s; }
  .prod-destaque:hover { transform: translateY(-4px); }
  @media (max-width: 760px) { .prod-destaque { grid-template-columns: 1fr; } }
  .pd-img { position: relative; aspect-ratio: 1/1; background: linear-gradient(135deg,#1a1a2e,#16213e);
    display: flex; align-items: center; justify-content: center; }
  .pd-img img { width: 100%; height: 100%; object-fit: cover; }
  .pd-ph { position: absolute; font-size: 3rem; opacity: 0.4; }
  .pd-body { padding: 36px 32px; display: flex; flex-direction: column;
    justify-content: center; gap: 18px; }
  .pd-body h3 { font-size: 1.5rem; font-weight: 800; line-height: 1.25; }
  .pd-cta { align-self: flex-start; background: var(--cta); color: #04201b;
    font-weight: 800; padding: 13px 26px; border-radius: 100px; font-size: 1rem;
    animation: pulsar 2.6s ease-in-out infinite; }
  @keyframes pulsar { 0%,100% { box-shadow: 0 0 0 0 rgba(0,224,184,0); transform: scale(1); }
    50% { box-shadow: 0 0 22px 3px rgba(0,224,184,0.5); transform: scale(1.03); } }
  @media (prefers-reduced-motion: reduce) { .pd-cta { animation: none; } }
  .selo { position: absolute; top: 14px; left: 14px; background: var(--gold);
    color: #0a0a12; font-weight: 800; font-size: 0.72rem; padding: 6px 12px;
    border-radius: 100px; letter-spacing: 0.03em; z-index: 3; }
  .prod { overflow: hidden; display: flex; flex-direction: column; }
  .prod .thumb { position: relative; aspect-ratio: 1/1;
    background: linear-gradient(135deg,#1a1a2e,#16213e);
    display: flex; align-items: center; justify-content: center; }
  .prod .thumb img { width: 100%; height: 100%; object-fit: cover; }
  .prod .body { padding: 20px; display: flex; flex-direction: column; gap: 12px; flex: 1; }
  .prod h3 { font-size: 1rem; font-weight: 700; line-height: 1.35;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .prod .ver { margin-top: auto; display: block; text-align: center; background: var(--glass);
    border: 1px solid var(--glass-border); padding: 11px; border-radius: 100px;
    font-weight: 700; font-size: 0.92rem; transition: background 0.2s, border-color 0.2s; }
  .prod .ver:hover { border-color: var(--pop2); background: rgba(0,212,255,0.08); }
  .contact-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; align-items: center; }
  @media (max-width: 860px) { .contact-grid { grid-template-columns: 1fr; } }
  .contact-info { display: flex; flex-direction: column; gap: 16px; }
  .ci { display: flex; align-items: center; gap: 14px; color: var(--muted); }
  .ci .ico { width: 40px; height: 40px; border-radius: 10px; background: var(--glass);
    border: 1px solid var(--glass-border); display: flex; align-items: center;
    justify-content: center; font-size: 1.1rem; flex-shrink: 0; }
  .ci a { color: var(--ink); font-weight: 600; }
  .contact-btns { display: flex; flex-direction: column; gap: 14px; }
  .contact-btns .btn { justify-content: center; width: 100%; }
  .btn-wa { background: #25d366; color: #052e16; }
  .btn-tg { background: #29a9eb; color: #03263a; }
  .btn-mail { background: var(--glass); border: 1px solid var(--glass-border); color: var(--ink); }
  .contact-btns .btn:hover { transform: translateY(-2px); }
  footer { background: var(--bg-soft); border-top: 1px solid var(--glass-border);
           padding: 60px 0 30px; margin-top: 40px; }
  .foot-top { display: flex; justify-content: space-between; flex-wrap: wrap;
              gap: 30px; margin-bottom: 40px; }
  .foot-brand { max-width: 320px; }
  .foot-brand .logo { font-size: 1.5rem; margin-bottom: 12px; }
  .foot-brand p { color: var(--muted); font-size: 0.95rem; }
  .foot-links { display: flex; gap: 50px; flex-wrap: wrap; }
  .foot-col h4 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.08em;
                 color: var(--muted); margin-bottom: 14px; }
  .foot-col a { display: block; color: var(--ink); font-weight: 600; font-size: 0.95rem;
                margin-bottom: 10px; opacity: 0.85; transition: opacity 0.2s; }
  .foot-col a:hover { opacity: 1; color: var(--pop2); }
  .afiliado { color: var(--muted); font-size: 0.82rem; line-height: 1.6;
              border-top: 1px solid var(--glass-border); padding-top: 24px; margin-bottom: 16px; }
  .copy { color: var(--muted); font-size: 0.85rem; text-align: center; }
  .copy a { color: var(--muted); margin: 0 8px; }
  .copy a:hover { color: var(--pop2); }

  /* ===== AJUSTES MOBILE (telas pequenas) ===== */
  @media (max-width: 600px) {
    .wrap { padding: 0 18px; }
    section { padding: 56px 0; }
    .nav-in { padding: 14px 18px; }
    .logo { font-size: 1.15rem; }
    .hero { padding: 64px 0 56px; }
    .hero h1 { font-size: clamp(2rem, 9vw, 2.8rem); line-height: 1.1; margin-bottom: 20px; }
    .hero p { font-size: 1.02rem; padding: 0 4px; }
    .badge { font-size: 0.7rem; padding: 7px 14px; margin-bottom: 22px; }
    .sec-title { font-size: clamp(1.7rem, 7vw, 2.2rem); }
    .sec-sub { font-size: 1rem; margin-bottom: 36px; }
    .hero-cta { gap: 12px; }
    .hero-cta .btn { width: 100%; justify-content: center; }
    .btn { padding: 14px 26px; font-size: 0.98rem; }
    .feat { padding: 26px 22px; }
    .pd-body { padding: 26px 22px; }
    .pd-body h3 { font-size: 1.25rem; }
    .prod h3 { font-size: 0.9rem; line-height: 1.3; }
    .prod .body { padding: 12px; gap: 8px; }
    .prod .ver { padding: 9px; font-size: 0.85rem; }
    .difs { gap: 4px 0; }
    .dif { padding: 14px 0; }
    /* trava qualquer vazamento horizontal */
    section, .wrap, .hero, .prod-destaque, .grid-3, .grid-2 { max-width: 100%; }
    img { max-width: 100%; height: auto; }
  }
  @media (max-width: 380px) {
    .hero h1 { font-size: 1.85rem; }
    .sec-title { font-size: 1.6rem; }
  }
</style>
</head>
<body>
<nav><div class="nav-in">
  <div class="logo">top<b>shop</b>.</div>
  <div class="nav-links">
    <a href="#inicio">Início</a><a href="#diferenciais">Diferenciais</a>
    <a href="#servicos">Serviços</a><a href="#produtos">Produtos</a>
    <a href="#contato">Contato</a>
  </div>
  <a href="#contato" class="btn btn-primary" style="padding:10px 22px;font-size:0.9rem;">Parcerias</a>
</div></nav>

<header class="hero" id="inicio"><div class="wrap">
  <span class="badge">Curadoria · Conteúdo · Tecnologia</span>
  <h1>Produtos inteligentes.<br><b>Conteúdo que converte.</b></h1>
  <p>A topshop garimpa, testa e transforma achados em vídeos estratégicos —
     unindo curadoria afiada e inteligência artificial pra escalar resultado.</p>
  <div class="hero-cta">
    <a href="#produtos" class="btn btn-primary">Ver produtos</a>
    <a href="#contato" class="btn btn-ghost">Propor parceria</a>
  </div>
</div></header>

<section id="diferenciais" class="wrap reveal">
  <span class="eyebrow">Por que a topshop</span>
  <h2 class="sec-title">Diferenciais que entregam</h2>
  <p class="sec-sub">Não é sobre postar muito. É sobre postar o que funciona, com método e tecnologia por trás.</p>
  <div class="difs">
    <div class="dif"><span class="check">✦</span><span>Curadoria inteligente de produtos</span></div>
    <div class="dif"><span class="check">✦</span><span>Conteúdo feito pra prender atenção</span></div>
    <div class="dif"><span class="check">✦</span><span>Uso estratégico de inteligência artificial</span></div>
    <div class="dif"><span class="check">✦</span><span>Foco em produtos úteis e virais</span></div>
    <div class="dif"><span class="check">✦</span><span>Presença em múltiplas plataformas</span></div>
    <div class="dif"><span class="check">✦</span><span>Mentalidade de escala</span></div>
    <div class="dif"><span class="check">✦</span><span>Atendimento direto pra parcerias</span></div>
    <div class="dif"><span class="check">✦</span><span>Tecnologia própria em movimento</span></div>
  </div>
</section>

<section id="servicos" class="wrap reveal">
  <div class="center">
    <span class="eyebrow">O que fazemos</span>
    <h2 class="sec-title">Serviços</h2>
    <p class="sec-sub">Do achado ao alcance — uma operação completa de conteúdo e divulgação.</p>
  </div>
  <div class="grid-3">
    <div class="glass feat"><div class="ico">📢</div><h3>Divulgação de produtos</h3><p>Seu produto apresentado pra um público pronto pra comprar.</p></div>
    <div class="glass feat"><div class="ico">🎬</div><h3>Conteúdo para redes</h3><p>Vídeos curtos e diretos, pensados pra cada plataforma.</p></div>
    <div class="glass feat"><div class="ico">⭐</div><h3>Reviews e demonstrações</h3><p>Demonstração honesta que mostra o produto em ação.</p></div>
    <div class="glass feat"><div class="ico">🔗</div><h3>Estratégia de afiliados</h3><p>Links rastreáveis e conversão acompanhada de perto.</p></div>
    <div class="glass feat"><div class="ico">🤝</div><h3>Parcerias comerciais</h3><p>Colaborações sob medida pra marcas e lojistas.</p></div>
    <div class="glass feat"><div class="ico">⚡</div><h3>Campanhas com vídeos curtos</h3><p>Volume e ritmo de publicação pensados pra escala.</p></div>
  </div>
</section>

<section id="produtos" class="wrap reveal">
  <div class="center">
    <span class="eyebrow">Achados da vez</span>
    <h2 class="sec-title">Vitrine topshop</h2>
    <p class="sec-sub">Os produtos que ganharam o selo de achado esperto. Busque, filtre e garanta o seu.</p>
  </div>
  {{VITRINE}}
</section>

<section id="contato" class="wrap reveal">
  <div class="contact-grid">
    <div>
      <span class="eyebrow">Vamos conversar</span>
      <h2 class="sec-title">Fale comigo</h2>
      <p class="sec-sub" style="margin-bottom:30px;">Quer indicar um produto, propor uma parceria ou entrar nos grupos de achadinhos? Chama aí.</p>
      <div class="contact-info">

        {{GRUPOS}}
        <div class="ci"><div class="ico">✉️</div><span>E-mail: <a href="mailto:{{EMAIL}}">{{EMAIL}}</a></span></div>
        <div class="ci"><div class="ico">📍</div><span>Goiânia — GO</span></div>
        <div class="ci"><div class="ico">📸</div><span>Instagram: <a href="{{INSTAGRAM}}" target="_blank">@topshop.__</a></span></div>
        <div class="ci"><div class="ico">🎵</div><span>TikTok: <a href="{{TIKTOK}}" target="_blank">@topshop.__</a></span></div>
        <div class="ci"><div class="ico">▶️</div><span>YouTube: <a href="{{YOUTUBE}}" target="_blank">TopShop_.</a></span></div>
      </div>
    </div>
    <div class="contact-btns">
      <a href="mailto:{{EMAIL}}" class="btn btn-mail">Enviar e-mail</a>
      <a href="#produtos" class="btn btn-primary" style="justify-content:center;">Ver ofertas</a>
    </div>
  </div>
</section>

<footer><div class="wrap">
  <div class="foot-top">
    <div class="foot-brand">
      <div class="logo">top<b>shop</b>.</div>
      <p>Produtos inteligentes. Conteúdo estratégico. Tecnologia em movimento.</p>
    </div>
    <div class="foot-links">
      <div class="foot-col"><h4>Navegação</h4>
        <a href="#inicio">Início</a><a href="#produtos">Produtos</a>
        <a href="#servicos">Serviços</a><a href="#contato">Contato</a></div>
      <div class="foot-col"><h4>Redes</h4>
        <a href="{{INSTAGRAM}}" target="_blank">Instagram</a>
        <a href="{{TIKTOK}}" target="_blank">TikTok</a>
        <a href="{{YOUTUBE}}" target="_blank">YouTube</a></div>
    </div>
  </div>
  <p class="afiliado">Aviso de afiliado: a topshop participa de programas de afiliados.
     Alguns links nesta página podem gerar comissão sobre compras, sem custo adicional
     para você. Esta página não coleta dados pessoais. As ofertas e disponibilidades são
     de responsabilidade das lojas anunciantes.</p>
  <p class="copy">© {{ANO}} topshop · {{TOTAL}} achados · atualizado em {{DATA}}</p>
</div></footer>

<script>
  const reveals = document.querySelectorAll('.reveal');
  function revelarTudo() { reveals.forEach(el => el.classList.add('in')); }
  if ('IntersectionObserver' in window) {
    const obs = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting) { e.target.classList.add('in'); obs.unobserve(e.target); }
      });
    }, { threshold: 0, rootMargin: '0px 0px -8% 0px' });
    reveals.forEach(el => obs.observe(el));
    // rede de segurança: no celular, uma seção mais alta que a tela pode nunca
    // "intersectar" o suficiente e ficaria invisível (opacity:0). Depois de um
    // tempinho, mostra tudo de qualquer jeito.
    setTimeout(revelarTudo, 1600);
  } else {
    revelarTudo();
  }

  // Busca + filtro da vitrine
  const busca = document.getElementById('busca');
  if (busca) {
    const cards = Array.from(document.querySelectorAll('.prod, .prod-destaque'));
    const semRes = document.getElementById('sem-res');
    const filtros = document.querySelectorAll('.filtro');
    const filtrosPlat = document.querySelectorAll('.filtro-plat');
    let catAtiva = 'todos';
    let platAtiva = 'todos';
    function aplicar() {
      const termo = busca.value.trim().toLowerCase();
      let achou = 0;
      cards.forEach(function(c) {
        const alvo = c.getAttribute('data-busca') || '';
        const cat = c.getAttribute('data-categoria') || '';
        const plat = c.getAttribute('data-plataforma') || 'shopee';
        const okB = !termo || alvo.indexOf(termo) !== -1;
        const okC = catAtiva === 'todos' || cat === catAtiva;
        const okP = platAtiva === 'todos' || plat === platAtiva;
        const mostra = okB && okC && okP;
        c.style.display = mostra ? '' : 'none';
        if (mostra) achou++;
      });
      if (semRes) semRes.style.display = achou === 0 ? 'block' : 'none';
    }
    busca.addEventListener('input', aplicar);
    filtros.forEach(function(b) {
      b.addEventListener('click', function() {
        filtros.forEach(function(x) { x.classList.remove('ativo'); });
        b.classList.add('ativo');
        catAtiva = b.getAttribute('data-filtro');
        aplicar();
      });
    });
    filtrosPlat.forEach(function(b) {
      b.addEventListener('click', function() {
        filtrosPlat.forEach(function(x) { x.classList.remove('ativo'); });
        b.classList.add('ativo');
        platAtiva = b.getAttribute('data-plat');
        aplicar();
      });
    });
  }
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Gera o site institucional TopShop com vitrine automática")
    parser.add_argument("--abrir", action="store_true", help="Abre no navegador depois")
    parser.add_argument("--sem-shopee", action="store_true", dest="sem_shopee",
                        help="Não gera links via Shopee (usa só os existentes)")
    parser.add_argument("--saida", default="", help="Caminho de saída (default: site/index.html)")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("🌐 SITE BUILDER — TopShop institucional + vitrine")
    log.info("=" * 60)

    produtos = _carregar_produtos()
    if not produtos:
        log.error("❌ Nenhum produto (rode validar_fila/curar_fila antes)")
        return 1
    log.info(f"📦 {len(produtos)} produtos carregados")

    if not args.sem_shopee:
        log.info("🔗 Gerando links de afiliado (sub-id 'bio')...")
        produtos = _gerar_links_afiliado(produtos)
    else:
        produtos = [p for p in produtos if p.get("link")]

    if not produtos:
        log.error("❌ Nenhum produto com link — nada pra publicar")
        return 1

    produtos.sort(key=lambda p: (0 if p.get("classe") == "mina_ouro" else 1,
                                 -float(p.get("comissao_valor", 0) or 0)))
    html_final = gerar_site(produtos)

    saida = Path(args.saida) if args.saida else SAIDA_HTML
    saida.parent.mkdir(parents=True, exist_ok=True)
    with open(saida, "w", encoding="utf-8") as f:
        f.write(html_final)
    log.info(f"✅ Site gerado: {saida} ({len(produtos)} produtos, {len(html_final)//1024}KB)")
    print(f"\n🌐 Site pronto: {saida}\n   Sobe no GitHub Pages e aponta tua bio pra ele!")

    if args.abrir:
        import webbrowser
        webbrowser.open(f"file://{saida.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())