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
                        # o relatório do validador carrega foto e link desde
                        # que ele passou a copiá-los do campeão. Zerar aqui
                        # jogava todo produto desta fonte na vitrine invisível
                        "imagem": p.get("imagem", ""),
                        "link": p.get("link", ""), "plataforma": "shopee",
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


def _reais(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _preco_html(p: dict, grande: bool = False) -> str:
    """Preço do card. Vazio quando não há dado — melhor não falar de preço do
    que falar errado numa página estática."""
    r = p.get("preco_resumo") or {}
    if not r or not r.get("preco"):
        return ""
    # o til avisa que é média, não preço travado
    til = "<i>~</i>" if r.get("media") else ""
    linha = f'<div class="pr"><b>{til}{_reais(r["preco"])}</b>'
    if r.get("de"):
        linha += f'<s>{_reais(r["de"])}</s>'
    linha += "</div>"

    if r.get("media"):
        texto = f'média de {r["obs"]} dias · {r["visto"]}'
    else:
        texto = f'conferido em {r["visto"]}'
    classe = ""
    if r.get("caiu"):
        # no destaque a queda é a informação que vende; no card a linha fica
        # longa demais e quebra em duas
        texto = (f'caiu {r["caiu"]}% na semana'
                 + (f' · média de {r["obs"]} dias' if grande else ''))
        classe = " caindo"
    return linha + f'<span class="afer{classe}">{html.escape(texto)}</span>'


def _faixa_svg(serie: list, largura=68, altura=20) -> str:
    """A linha do preço, do tamanho de uma unha, dentro do card.

    ⚠️ ESTE É O ÚNICO PEDAÇO DESTA PÁGINA QUE NENHUM CONCORRENTE PODE COPIAR.
    Grupo de achadinho mostra print de story; loja grande mostra preço de hoje.
    Só quem guarda leitura diária há 20 dias consegue mostrar se o preço de
    hoje é bom — e é a diferença entre "confia em mim" e "olha o dado".

    📌 Sem eixo, sem grade, sem rótulo. A unha responde UMA pergunta ("tá
    subindo ou caindo?") e o resto fica pro drawer, onde há espaço pra
    responder direito. Enfeitar isto aqui seria transformar prova em gráfico.

    Verde quando terminou abaixo de onde começou (bom pra quem compra),
    cinza quando não — e nunca vermelho: preço subindo não é alarme, é
    informação, e vermelho num card de compra lê como erro.
    """
    if len(serie) < 3:
        return ""
    vals = [float(v) for _, v in serie]
    lo, hi = min(vals), max(vals)
    faixa = (hi - lo) or 1.0            # série plana desenha uma reta no meio
    passo = largura / (len(vals) - 1)
    pts = " ".join(
        f"{i * passo:.1f},{altura - 2 - ((v - lo) / faixa) * (altura - 4):.1f}"
        for i, v in enumerate(vals))
    caiu = vals[-1] < vals[0]
    cor = "var(--ok)" if caiu else "var(--muted)"
    return (f'<svg class="faixa" viewBox="0 0 {largura} {altura}" '
            f'preserveAspectRatio="none" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" stroke="{cor}" '
            f'stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{largura:.1f}" cy="{altura - 2 - ((vals[-1] - lo) / faixa) * (altura - 4):.1f}" '
            f'r="2.1" fill="{cor}"/></svg>')


def _selos_html(p: dict, novo: bool = False) -> str:
    r = p.get("preco_resumo") or {}
    selos = []
    if novo:
        selos.append('<span class="selo novo">novo</span>')
    if r.get("off"):
        selos.append(f'<span class="selo off">-{r["off"]}%</span>')
    # classe `plat` e não `loja`: `.loja` já é o botão de aba lá em cima, e as
    # duas regras de CSS brigavam pelo mesmo seletor
    selos.append(f'<span class="selo plat">{_loja(p)[0]}</span>')
    return "".join(selos)


# Rótulo e emoji por loja. É TABELA e não `if amazon else shopee` de propósito:
# a forma binária mentia por omissão — qualquer plataforma que não fosse
# "amazon" saía escrita **Shopee**, inclusive um produto do Mercado Livre com
# link pro Mercado Livre. O filtro da vitrine já lista "meli" desde antes
# (_filtros_html), então o selo era a única peça que ainda decidia no par.
#
# Loja desconhecida cai em Shopee porque é o que a fila tem de fato quando o
# campo vem vazio — mas agora isso é uma ESCOLHA declarada, não um efeito
# colateral de escrever a condição ao contrário.
LOJAS = {
    "shopee": ("Shopee", "🛍️"),
    "amazon": ("Amazon", "📦"),
    "meli": ("Mercado Livre", "🟡"),
}
LOJA_PADRAO = LOJAS["shopee"]


def _loja(p: dict) -> tuple:
    """(rótulo, emoji) da loja do produto."""
    return LOJAS.get((p.get("plataforma") or "shopee").lower(), LOJA_PADRAO)


def _foto_html(p: dict, titulo: str, novo: bool = False) -> str:
    """Foto do produto com os três estados previstos: carregando (esqueleto),
    ok, e sem-foto (a Amazon hoje não devolve imagem)."""
    img = html.escape(p.get("imagem", ""))
    emoji = _loja(p)[1]
    if not img:
        return (f'<div class="foto sem-foto"><em class="fb">{emoji}</em>'
                f'{_selos_html(p, novo)}</div>')
    return (f'<div class="foto carregando">'
            f'<img src="{img}" alt="{titulo}" loading="lazy" decoding="async">'
            f'<em class="fb">{emoji}</em>{_selos_html(p, novo)}</div>')


def _card_destaque(p: dict) -> str:
    """O achado do dia, na moldura 9:16 — o formato do Reels de onde a pessoa
    veio. Continua o vídeo em vez de recomeçar do zero."""
    titulo = html.escape(_titulo_legivel(p.get("titulo") or p.get("nome", ""), 70))
    link = html.escape(p.get("link", "#"))
    img = html.escape(p.get("imagem", ""))
    capa = (f'<img class="capa" src="{img}" alt="{titulo}" decoding="async">'
            if img else f'<em class="capa-fb">{_loja(p)[1]}</em>')
    return f"""
    <a class="moldura" id="moldura" href="{link}" target="_blank" rel="noopener">
      {capa}
      <div class="brilho"></div>
      <div class="live"><b></b> VISTO NO REELS</div>
      <div class="pe">
        <h3>{titulo}</h3>
        {_preco_html(p, grande=True)}
      </div>
    </a>"""


def _card_grid(p: dict, novo: bool = False) -> str:
    titulo = html.escape(_titulo_legivel(p.get("titulo") or p.get("nome", "")))
    nome = html.escape(p.get("nome", ""))
    link = html.escape(p.get("link", "#"))
    cat = html.escape(_inferir_categoria(p))
    plat = (p.get("plataforma") or "shopee").lower()
    r = p.get("preco_resumo") or {}
    serie = r.get("serie") or []
    # ⚠️ os dados do drawer viajam em atributos do próprio card, e não num JSON
    # separado no fim da página: assim não existe a possibilidade de a lista e
    # a grade saírem de sincronia — é literalmente o mesmo elemento.
    dados_drawer = (
        f' data-serie="{",".join(str(v) for _, v in serie)}"'
        f' data-dias="{",".join(d for d, _ in serie)}"'
        f' data-min="{r.get("min", "")}" data-max="{r.get("max", "")}"'
        f' data-preco="{r.get("preco", "")}" data-visto="{html.escape(str(r.get("visto", "")))}"'
        f' data-obs="{r.get("obs", 0)}" data-img="{html.escape(p.get("imagem", ""))}"'
        f' data-loja="{html.escape(_loja(p)[0])}"')
    return f"""
      <a class="card" href="{link}" target="_blank" rel="noopener"
         data-busca="{titulo.lower()} {nome.lower()}" data-categoria="{cat}"
         data-plataforma="{plat}"{dados_drawer}>
        {_foto_html(p, titulo, novo)}
        <div class="corpo">
          <h3>{titulo}</h3>
          {_preco_html(p)}
          {_faixa_svg(serie)}
          <span class="ver">Ver oferta <span>&rarr;</span></span>
        </div>
      </a>"""


def _filtros_html(produtos: list) -> str:
    """Categorias FIXAS: sempre visíveis, mesmo sem produto no momento — assim
    a loja parece organizada e a aba não some quando o estoque muda."""
    presentes = {_inferir_categoria(p) for p in produtos}
    ordem = ["todos"] + list(_CATEGORIAS_FIXAS)
    if "Outros" in presentes:
        ordem.append("Outros")
    botoes = []
    for c in ordem:
        rotulo = "Tudo" if c == "todos" else c
        ativo = "true" if c == "todos" else "false"
        botoes.append(f'<button class="chip" aria-pressed="{ativo}" '
                      f'data-filtro="{html.escape(c)}">{html.escape(rotulo)}</button>')
    return ('<div class="chips fita-rolo" id="filtros">'
            + "".join(botoes) + "</div>")


def _toggle_plataforma_html(produtos: list) -> str:
    """Abas de loja. A contagem sai dos produtos de verdade, então nunca mente,
    e a aba do Mercado Livre nasce sozinha quando o primeiro produto de lá
    entrar na fila."""
    conta = {}
    for p in produtos:
        conta[(p.get("plataforma") or "shopee").lower()] = \
            conta.get((p.get("plataforma") or "shopee").lower(), 0) + 1
    if not conta:
        return ""
    linhas = [("todos", "Tudo", len(produtos))]
    for chave, rotulo in (("shopee", "Shopee"), ("amazon", "Amazon"),
                          ("meli", "Mercado Livre")):
        linhas.append((chave, rotulo, conta.get(chave, 0)))
    botoes = []
    for i, (chave, rotulo, n) in enumerate(linhas):
        vazia = n == 0
        desab = ' disabled title="Aparece sozinha quando o primeiro produto entrar"' if vazia else ""
        botoes.append(
            f'<button class="loja" role="tab" aria-selected="{"true" if i == 0 else "false"}"'
            f' data-plat="{chave}"{desab}>'
            f'<span>{rotulo}<i class="n">{"em breve" if vazia else n}</i></span></button>')
    return ('<div class="lojas fita-rolo" id="filtros-plat" role="tablist">'
            + "".join(botoes) + "</div>")


def _esteira_html(produtos: list) -> str:
    """Fita de novidades. Duplicada pra emendar sem salto na volta do loop."""
    itens = []
    for p in produtos[:12]:
        nome = html.escape(" ".join(
            (p.get("titulo") or p.get("nome", "")).split()[:5]))
        itens.append(f"<span>acabou de sair: <b>{nome}</b></span>")
    if not itens:
        return ""
    fita = "".join(itens) * 2
    return f'<div class="esteira"><div class="fita">{fita}</div></div>'


# Produto sem foto E sem preço não vira card. Não é regra contra a Amazon: é
# barra de qualidade da vitrine — vale pra Shopee cuja imagem falhar também.
# Hoje pega os links de BUSCA da Amazon, que não apontam pra um produto e por
# isso não têm o que mostrar. O link segue valendo na legenda do vídeo, então
# a comissão não se perde; ele só não ocupa um card que ninguém clica.
# Vira True pra mostrar tudo de novo (quando a PA-API destravar, por exemplo).
MOSTRAR_SEM_DADOS = False


def _vale_mostrar(p: dict) -> bool:
    tem_foto = bool((p.get("imagem") or "").strip())
    tem_preco = bool((p.get("preco_resumo") or {}).get("preco"))
    return MOSTRAR_SEM_DADOS or tem_foto or tem_preco


def _dias_acompanhados(produtos: list) -> int:
    """Há quantos dias a gente acompanha o preço do produto mais antigo.

    É o número que sustenta a frase 'a gente mostra média, não chute' — e ele
    cresce sozinho a cada rodada do deploy. Enquanto for pequeno, aparece
    pequeno: não vale inflar."""
    return max([(p.get("preco_resumo") or {}).get("obs", 0) for p in produtos]
               or [0])


def _metricas(produtos: list) -> tuple:
    """(achados, lojas, % off médio) — números do herói, calculados aqui e
    animados no JS a partir daqui. Sem JS, o número certo já está no HTML."""
    lojas = len({(p.get("plataforma") or "shopee").lower() for p in produtos})
    offs = [(p.get("preco_resumo") or {}).get("off", 0) for p in produtos]
    offs = [o for o in offs if o]
    medio = int(round(sum(offs) / len(offs))) if offs else 0
    return len(produtos), lojas, medio


def _baixaram(produtos: list, quantos: int = 10) -> tuple:
    """(titulo, lista) — o que abre a página.

    ⚠️ AQUI MORAVA UM MURAL DECORATIVO: três colunas de foto de produto
    derivando, sem clique, `aria-hidden`. Era bonito e não dizia nada — foto de
    mercadoria passando continua sendo enfeite, só que com enfeite caro.
    📌 O `caiu` já era calculado pelo `historico_precos` e não aparecia em
    lugar nenhum da página. Produto que BAIXOU DE PREÇO é notícia; catálogo é
    catálogo. Notícia é o que faz alguém voltar amanhã.

    O título muda com o dado, e isso não é detalhe: escrever "baixou de preço"
    num dia em que nada baixou é a primeira mentirinha, e depois dela ninguém
    acredita no gráfico. Sem quedas, o bloco assume ser o que é — o que acabou
    de entrar."""
    caiu = sorted(
        (p for p in produtos if int((p.get("preco_resumo") or {}).get("caiu") or 0) > 0),
        key=lambda p: -int(p["preco_resumo"]["caiu"]))
    if len(caiu) >= 4:
        return "Baixou de preço", caiu[:quantos]
    novos = sorted(produtos, key=lambda p: -int(p.get("ts") or 0))
    return "Acabou de entrar", novos[:quantos]


def _abertura_html(produtos: list) -> str:
    titulo, itens = _baixaram(produtos)
    if not itens:
        return ""
    cartas = "".join(_card_grid(p) for p in itens)
    marca = ('<span class="selo-queda">−{}%</span>' if titulo == "Baixou de preço"
             else "")
    return (f'<section class="abertura"><div class="abertura-topo">'
            f'<h2>{titulo}</h2>'
            f'<span class="dica">arraste para ver mais &rarr;</span></div>'
            f'<div class="trilho fita-rolo">{cartas}</div></section>')


def _grupo_faixa_html() -> str:
    """O convite pro grupo, no meio da vitrine.

    ⚠️ A PROMESSA AQUI É LITERAL, e é por isso que ela funciona: o sistema
    confere preço todo dia (`historico_precos`), esconde link morto sozinho
    (health-check) e posta no grupo 24x por dia. Nenhuma frase desta faixa é
    marketing — é a descrição do que a máquina faz.
    📌 Promessa que o produto cumpre não precisa de ponto de exclamação."""
    destino = GRUPO_WHATSAPP or GRUPO_TELEGRAM or INSTAGRAM
    if not destino:
        return ""
    return (
        '<section class="grupo-faixa">'
        '<div class="txt">'
        '<h3>A gente confere esses preços <em>todo dia</em>.</h3>'
        '<p>Quando um achado baixa de verdade, ele vai pro grupo na hora — '
        'com o link já pronto. É de graça e você sai quando quiser.</p>'
        '</div>'
        f'<a class="cta" href="{html.escape(destino)}" target="_blank" '
        'rel="noopener">Entrar no grupo <span>&rarr;</span></a>'
        '</section>')


def _vitrine_html(produtos: list) -> str:
    """Controles + grade. Os cards vêm prontos do servidor (aparecem no Google
    e funcionam sem JS); o JS só mostra e esconde na hora de filtrar."""
    if not produtos:
        return ('<p class="vazio"><b>Em breve, novos achados</b>'
                'A vitrine enche toda semana.</p>')
    modos = ('<div class="modos" id="modos" role="group" aria-label="Visualização">'
             '<button class="modo" type="button" data-modo="grade" '
             'aria-pressed="true">Grade</button>'
             '<button class="modo" type="button" data-modo="lista" '
             'aria-pressed="false">Lista</button></div>')
    linha_topo = ('<div class="linha-controles">' + _toggle_plataforma_html(produtos)
                  + modos + "</div>")
    controles = ('<div class="controles">' + linha_topo
                 + _filtros_html(produtos) + "</div>")
    # ⚠️ A FAIXA DO GRUPO ENTRA NO MEIO DA GRADE, não antes dela. Quem chega
    # pelo link do Reels quer ver achadinho; convite antes do produto é banner,
    # e banner a pessoa aprendeu a pular. Depois de uma leva de cards ela já
    # gostou do que viu, e aí o convite é a próxima coisa lógica.
    # 📌 O card fica FORA do filtro: `.grade` é o que o JS mostra e esconde, e
    # uma seção presa lá dentro sumiria quando alguém filtrasse por categoria.
    corte = min(len(produtos), 12)
    cards = "\n".join(_card_grid(p, novo=(i < 3))
                      for i, p in enumerate(produtos[:corte]))
    resto = "\n".join(_card_grid(p) for p in produtos[corte:])
    grade = f'<div class="grade" id="grade-prod">{cards}</div>'
    if resto:
        grade += _grupo_faixa_html() + f'<div class="grade">{resto}</div>'
    vazio = ('<p class="vazio" id="sem-res" style="display:none">'
             '<b>Esse a gente ainda não garimpou</b>'
             'Tenta outra busca — a vitrine enche toda semana.</p>')
    return controles + grade + vazio


def _grupos_html() -> str:
    """Grupos de achadinhos no contato (se configurados)."""
    itens = []
    if GRUPO_WHATSAPP:
        itens.append(f'<a class="ci" href="{html.escape(GRUPO_WHATSAPP)}" target="_blank" '
                     f'rel="noopener"><span class="ico">👥</span>'
                     f'<span>Grupo no WhatsApp<i>entrar no grupo</i></span></a>')
    if GRUPO_TELEGRAM:
        itens.append(f'<a class="ci" href="{html.escape(GRUPO_TELEGRAM)}" target="_blank" '
                     f'rel="noopener"><span class="ico">📨</span>'
                     f'<span>Canal no Telegram<i>entrar no canal</i></span></a>')
    return "".join(itens)


def gerar_site(produtos: list) -> str:
    _corrigir_titulos(produtos)
    antes = len(produtos)
    produtos = [p for p in produtos if _vale_mostrar(p)]
    if len(produtos) < antes:
        log.info(f"   🚧 {antes - len(produtos)} produto(s) sem foto e sem preço "
                 f"fora da vitrine (o link continua valendo na legenda)")
    total, lojas, off_medio = _metricas(produtos)
    # imagem do 1º produto vira a prévia do link no WhatsApp/Instagram
    og = (produtos[0].get("imagem", "") if produtos else "") or ""
    grupo_topo = GRUPO_WHATSAPP or GRUPO_TELEGRAM or INSTAGRAM
    return _TEMPLATE.replace("{{VITRINE}}", _vitrine_html(produtos))\
                    .replace("{{ABERTURA}}", _abertura_html(produtos))\
                    .replace("{{GRUPO_TOPO}}", html.escape(grupo_topo))\
                    .replace("{{TOTAL}}", str(total))\
                    .replace("{{LOJAS}}", str(lojas))\
                    .replace("{{LOJAS_ROTULO}}", "loja" if lojas == 1 else "lojas")\
                    .replace("{{OFF}}", str(off_medio))\
                    .replace("{{DIAS}}", str(_dias_acompanhados(produtos)))\
                    .replace("{{OGIMG}}", html.escape(og))\
                    .replace("{{ANO}}", time.strftime("%Y"))\
                    .replace("{{DATA}}", time.strftime("%d/%m/%Y"))\
                    .replace("{{WHATSAPP}}", WHATSAPP)\
                    .replace("{{EMAIL}}", EMAIL)\
                    .replace("{{INSTAGRAM}}", INSTAGRAM)\
                    .replace("{{TIKTOK}}", TIKTOK)\
                    .replace("{{YOUTUBE}}", YOUTUBE)


# ===== Template do site (casca fixa + vitrine dinâmica) =====
# A fonte vai num arquivo SEPARADO (topshop-fonte.woff2, escrito pelo
# deploy_site) e não embutida em base64: embutida ela engorda o HTML em 85KB e
# atrasa a primeira pintura. Com `swap`, o texto aparece na hora com a fonte do
# sistema e troca quando a nossa chega — quem vem do Reels no 4G não espera.
_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>topshop — o que você viu no vídeo, achou aqui</title>
<meta name="description" content="Os achados que aparecem nos nossos vídeos, com link direto e preço conferido. Shopee e Amazon.">
<meta property="og:title" content="topshop — o garimpo">
<meta property="og:description" content="O que você viu no vídeo, achou aqui.">
<meta property="og:type" content="website">
<meta property="og:image" content="{{OGIMG}}">
<!-- pinta a barra do navegador no celular com o fundo da página:
     é o detalhe que faz o site parecer app em vez de aba -->
<meta name="theme-color" content="#0B0C0F">
<!-- o símbolo é o mesmo da marca, embutido: a assinatura precisa existir
     sem a palavra "topshop" pra virar ícone de app um dia -->
<link rel="icon" href="data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%2032%2032%22%3E%3Cpath%20d%3D%22M6%200h13.4L32%2012.6V26a6%206%200%200%201-6%206H6a6%206%200%200%201-6-6V6a6%206%200%200%201%206-6Z%22%20fill%3D%22%23FF3D6E%22/%3E%3Ccircle%20cx%3D%2223.6%22%20cy%3D%228.4%22%20r%3D%222.1%22%20fill%3D%22%230B0C0F%22%20opacity%3D%22.55%22/%3E%3Cpath%20d%3D%22M6.6%2012.4h13.2v3.5h-4.8v10.4h-3.6V15.9H6.6z%22%20fill%3D%22%23fff%22/%3E%3C/svg%3E">
<link rel="apple-touch-icon" href="data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%2032%2032%22%3E%3Cpath%20d%3D%22M6%200h13.4L32%2012.6V26a6%206%200%200%201-6%206H6a6%206%200%200%201-6-6V6a6%206%200%200%201%206-6Z%22%20fill%3D%22%23FF3D6E%22/%3E%3Ccircle%20cx%3D%2223.6%22%20cy%3D%228.4%22%20r%3D%222.1%22%20fill%3D%22%230B0C0F%22%20opacity%3D%22.55%22/%3E%3Cpath%20d%3D%22M6.6%2012.4h13.2v3.5h-4.8v10.4h-3.6V15.9H6.6z%22%20fill%3D%22%23fff%22/%3E%3C/svg%3E">
<style>
@font-face{font-family:'Arch';src:url('topshop-fonte.woff2') format('woff2');
  font-weight:100 900;font-stretch:62% 125%;font-display:swap}

/* ══ PALETA: grafite + UM acento ═══════════════════════════════════════════
   ⚠️ A anterior tinha TRÊS neons (rosa #FF3D8A, menta #3DFFB0, ouro #FFD84D)
   sobre quase-preto arroxeado, mais quatro bolhas desfocadas animadas e uma
   grade com máscara radial. Essa combinação é a assinatura visual de página
   feita por IA — não porque seja feia, mas porque é o default de todo gerador,
   e o olho de quem compra já aprendeu a reconhecer.
   📌 Loja grande usa UMA cor de marca e gasta o resto em contraste e espaço.
   Aqui: grafite de verdade (neutro, não roxo), cards um degrau acima do fundo,
   e o rosa da TopShop só onde ele TRABALHA — CTA, estado ativo, selo de
   desconto. Verde sobrou só como sinal semântico de "preço caiu". */
:root{
  --bg:#0B0C0F; --sup:#131519; --sup2:#1A1D23; --linha:rgba(255,255,255,.085);
  --linha2:rgba(255,255,255,.14);
  --ink:#EDEFF2; --muted:#8D949E;
  --marca:#FF3D6E; --marca-esc:#D42A55; --ok:#35C88A;
  --r:14px; --topo:0px;
  --foto:#F4F5F7;
}

/* ══ TEMA CLARO ═══════════════════════════════════════════════════════════
   ⚠️ VEIO DAS REFERÊNCIAS, e é a técnica que aparece nas DUAS principais: o
   ERA Residence tem "by day / by night" e o Loop tem LIGHT/DARK/SYSTEM. Não é
   moda — é o sinal mais barato de "esse site foi feito por gente que pensa no
   usuário", porque respeita quem lê no sol e quem lê na cama.
   📌 Só os TOKENS mudam. Nenhuma regra de componente sabe que existe tema —
   se soubesse, cada card novo teria que ser pintado duas vezes e um dia alguém
   esqueceria metade. */
:root[data-tema="claro"]{
  --bg:#F7F7F9; --sup:#FFFFFF; --sup2:#F0F1F4;
  --linha:rgba(11,12,15,.09); --linha2:rgba(11,12,15,.16);
  --ink:#14161A; --muted:#666E7A;
  --marca:#E42060; --marca-esc:#B8144A; --ok:#128A5A;
  --foto:#EFF0F3;
}
:root[data-tema="claro"] .topo{background:rgba(247,247,249,.78)}
:root[data-tema="claro"] .card{
  box-shadow:0 1px 2px rgba(11,12,15,.06), 0 1px 1px rgba(11,12,15,.04)}
:root[data-tema="claro"] .card:hover{
  box-shadow:0 16px 38px rgba(11,12,15,.13), 0 0 0 1px rgba(228,32,96,.14)}
:root[data-tema="claro"] .selo{background:rgba(255,255,255,.86);
  border-color:rgba(11,12,15,.12);color:var(--ink)}
:root[data-tema="claro"] .card .foto::before{
  background:linear-gradient(transparent,rgba(11,12,15,.18))}
:root[data-tema="claro"] .g-x,
:root[data-tema="claro"] .gaveta{background:var(--bg)}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--ink);
  font-family:'Arch','Segoe UI',system-ui,-apple-system,sans-serif;
  line-height:1.5;overflow-x:hidden;-webkit-font-smoothing:antialiased;
  padding-bottom:env(safe-area-inset-bottom)}
a{color:inherit;text-decoration:none}
img{max-width:100%}
.wrap{max-width:1320px;margin:0 auto;padding:0 clamp(14px,3.2vw,28px)}
:where(a,button,input):focus-visible{outline:2px solid var(--marca);
  outline-offset:2px;border-radius:10px}

/* ══ TOPO: altura FIXA, e a razão é um bug ════════════════════════════════
   ⚠️ A VERSÃO ANTERIOR ENCOLHIA O PRÓPRIO BLOCO STICKY, e era isso que o Dre
   viu de "bugado dependendo de como a pessoa subir a tela e parar". Elemento
   `sticky` ocupa espaço no fluxo: quando ele encolhe de 58px pra 46px, o
   documento inteiro encurta e o conteúdo SOBE 12px debaixo do dedo. Perto do
   limiar isso vira solavanco, e parando ali no meio a página fica tremendo.
   📌 Barra que gruda não pode mudar de tamanho. A busca grande mora na CAPA e
   rola embora normalmente; o topo tem uma busca COMPACTA que aparece quando a
   outra sai de vista. As duas escrevem no mesmo filtro.

   E a lupa: `top:29px` era metade de 58px chumbada na mão — bastava um estado
   de altura que eu não tivesse enumerado (e eram cinco) pra ela sair do lugar.
   `top:50%` não depende de altura nenhuma. */
.topo{position:sticky;top:0;z-index:50;background:rgba(11,12,15,.72);
  backdrop-filter:blur(22px) saturate(150%);
  -webkit-backdrop-filter:blur(22px) saturate(150%);
  border-bottom:1px solid transparent;transition:border-color .25s}
.topo.colado{border-bottom-color:var(--linha)}
.barra{display:flex;align-items:center;gap:12px;height:60px}
.marca{display:flex;align-items:center;gap:9px;font-size:19px;font-weight:800;
  font-stretch:112%;letter-spacing:-.045em;white-space:nowrap;flex:none}
.marca .ts{width:26px;height:26px;flex:none;display:block}
.marca i{font-style:normal;color:var(--marca)}
.tema{flex:none;width:40px;height:40px;border-radius:11px;cursor:pointer;
  border:1px solid var(--linha2);background:transparent;color:var(--ink);
  display:grid;place-items:center;font:inherit;font-size:16px;line-height:1;
  transition:background .2s,border-color .2s,transform .3s}
.tema:hover{background:var(--sup2);border-color:var(--marca)}
.tema:active{transform:scale(.92)}
.zap{margin-left:0;flex:none;border:1px solid var(--linha2);color:var(--ink);
  font-weight:650;font-size:13px;padding:9px 15px;border-radius:999px;
  white-space:nowrap;min-height:40px;display:flex;align-items:center;
  transition:background .2s,border-color .2s}
.zap:hover{background:var(--sup2);border-color:var(--marca)}

/* ⚠️ ANTES A BUSCA SÓ APARECIA DEPOIS DE ROLAR, e parado no topo o header
   ficava com a marca de um lado, o botão do outro e um vão no meio — vazio
   justo no instante em que a pessoa chega querendo procurar o que viu. Agora
   ela é permanente e ocupa o meio.
   📌 De quebra sumiram os dois campos sincronizados: uma caixa só não tem como
   sair de sincronia com ninguém. Simplificar foi consequência de acertar o
   lugar, não economia. */
.barra .buscabox{flex:1;min-width:0;--h:42px;--fs:15px}
@media(max-width:760px){
  /* o polegar precisa da busca inteira; a palavra "topshop" cabe no símbolo */
  .marca span{display:none}
  .zap{padding:9px 13px}
}

/* ── caixa de busca ─────────────────────────────────────────────────────── */
.buscabox{position:relative;display:block}
.buscabox input{width:100%;height:var(--h,56px);background:var(--sup);
  border:1px solid var(--linha2);color:var(--ink);border-radius:13px;
  padding:0 16px 0 48px;font:inherit;font-size:var(--fs,16px);font-weight:500;
  transition:border-color .2s,background .2s,box-shadow .2s}
.buscabox input::placeholder{color:var(--muted);font-weight:400}
.buscabox input::-webkit-search-cancel-button{filter:invert(.6)}
.buscabox input:focus{outline:none;border-color:var(--marca);background:var(--sup2);
  box-shadow:0 0 0 3px rgba(255,61,110,.14)}
.buscabox .lupa{position:absolute;left:17px;top:50%;transform:translateY(-50%);
  width:18px;height:18px;stroke:var(--muted);fill:none;stroke-width:2;
  stroke-linecap:round;transition:stroke .2s;pointer-events:none}
.buscabox input:focus~.lupa{stroke:var(--marca)}
@media(max-width:600px){.barra .buscabox{--fs:16px}} /* 16px = iOS não dá zoom */

/* ══ CONTROLES: categorias e lojas em fita ════════════════════════════════ */
.controles{display:flex;flex-direction:column;gap:9px;padding-bottom:14px}
.linha-controles{display:flex;align-items:center;gap:10px;min-width:0}
.linha-controles .lojas{flex:1;min-width:0}
.fita-rolo{display:flex;gap:7px;overflow-x:auto;scrollbar-width:none;
  margin-inline:calc(-1 * clamp(14px,3.2vw,28px));
  padding-inline:clamp(14px,3.2vw,28px);scroll-snap-type:x proximity}
.fita-rolo::-webkit-scrollbar{display:none}
.chip{flex:none;border:1px solid var(--linha2);background:transparent;color:var(--muted);
  font:inherit;font-size:13.5px;font-weight:600;padding:9px 15px;border-radius:999px;
  cursor:pointer;scroll-snap-align:start;
  transition:color .18s,border-color .18s,background .18s}
.chip:hover{color:var(--ink);border-color:var(--linha2);background:var(--sup)}
/* ⚠️ O CHIP ATIVO ERA ROSA E DISPUTAVA COM O BOTÃO DE COMPRAR. Um acento só
   funciona quando ele significa UMA coisa: aqui o rosa é AÇÃO (ver na loja,
   selo de desconto, foco). Estado de filtro é orientação, não ação — vai de
   branco, que é mais forte e não mente sobre a hierarquia. */
.chip[aria-pressed="true"]{background:var(--ink);color:#0B0C0F;border-color:var(--ink)}
.loja{flex:none;border:1px solid transparent;background:var(--sup);color:var(--muted);
  font:inherit;font-size:13px;font-weight:650;padding:8px 14px;border-radius:999px;
  cursor:pointer;scroll-snap-align:start;
  transition:color .18s,background .18s,border-color .18s}
.loja[aria-selected="true"]{color:var(--ink);background:var(--sup2);
  border-color:var(--linha2)}
.loja .n{opacity:.6;margin-left:6px;font-variant-numeric:tabular-nums;font-style:normal}
.loja:disabled{opacity:.34;cursor:not-allowed}

/* ══ MODO DE VISUALIZAÇÃO ═════════════════════════════════════════════════
   ⚠️ TIRADO DO LOOP AGENCY, que alterna List / Gallery / Spiral. Lá é bravata
   de portfólio; aqui é utilidade real — com 300 produtos, quem procura uma
   coisa específica quer LISTA (mais itens por tela, nome inteiro visível) e
   quem está passeando quer GRADE (foto grande).
   📌 O que eu NÃO trouxe: o "Spiral". Numa vitrine, forma que atrapalha
   encontrar é forma que custa venda — a referência é de outro ofício. */
.modos{display:flex;gap:3px;background:var(--sup);border:1px solid var(--linha);
  border-radius:999px;padding:3px;flex:none}
.modo{border:0;background:none;color:var(--muted);font:inherit;font-size:12.5px;
  font-weight:650;padding:7px 13px;border-radius:999px;cursor:pointer;
  transition:color .2s,background .2s}
.modo[aria-pressed="true"]{background:var(--sup2);color:var(--ink)}

/* lista: a foto vira miniatura e o nome ganha a linha inteira */
.grade.lista{grid-template-columns:1fr;gap:8px}
.grade.lista .card{flex-direction:row;align-items:stretch}
.grade.lista .card .foto{width:104px;flex:none;aspect-ratio:1}
.grade.lista .card .foto::before{display:none}
.grade.lista .selo.plat{display:none}
.grade.lista .selo.off{top:9px;right:auto;left:9px;font-size:12px;padding:4px 8px}
.grade.lista .selo.novo{display:none}
.grade.lista .card .corpo{padding:12px 14px;gap:6px}
.grade.lista .card h3{-webkit-line-clamp:1;font-size:14px}
.grade.lista .card .ver{margin-top:0;align-self:flex-start;padding:8px 16px;
  min-height:38px;font-size:12.5px}
.grade.lista .faixa{display:none}
@media(min-width:760px){
  .grade.lista .card{align-items:center}
  .grade.lista .card .corpo{flex-direction:row;align-items:center;gap:18px}
  .grade.lista .card h3{flex:1}
  .grade.lista .card .pr{flex:none;min-width:130px;justify-content:flex-end}
}

/* ══ GRADE ═══════════════════════════════════════════════════════════════
   ⚠️ O CARD ERA QUASE INVISÍVEL (31/08). `--sup:#131519` sobre `--bg:#0B0C0F`
   é 2% de diferença de luminosidade: a grade virava uma mancha só, e o olho
   não tinha onde pousar. Escuro sem CAMADA não lê como caro, lê como barato —
   a diferença entre os dois é profundidade, não saturação.
   📌 Três coisas fazem um card escuro parecer objeto: superfície mais clara
   que o fundo, um fio de luz na borda de cima (como plástico pegando luz), e
   uma sombra que o descola da página. Nenhuma delas é decoração — todas são
   pistas de que aquilo ali é uma COISA, clicável. */
.grade{display:grid;gap:clamp(10px,1.3vw,16px);
  grid-template-columns:repeat(auto-fill,minmax(196px,1fr))}
.card{background:var(--sup);border:1px solid var(--linha);border-radius:var(--r);
  overflow:hidden;display:flex;flex-direction:column;position:relative;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.055), 0 1px 2px rgba(0,0,0,.4);
  transform-style:preserve-3d;
  transition:opacity .4s,transform .32s cubic-bezier(.22,.7,.2,1),
    border-color .22s,background .22s,box-shadow .32s}
.card.esconde{display:none}
.js .card{opacity:0;transform:translateY(16px) scale(.985)}
.js .card.dentro{opacity:1;transform:none}
.card:hover{background:var(--sup2);border-color:rgba(255,61,110,.42);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.09), 0 20px 46px rgba(0,0,0,.55),
             0 0 0 1px rgba(255,61,110,.10)}
.card.saindo{opacity:0;transform:scale(.96);pointer-events:none}

.card .foto{aspect-ratio:1;position:relative;overflow:hidden;background:var(--foto)}
.card .foto img{width:100%;height:100%;object-fit:cover;display:block;opacity:0;
  transition:opacity .35s,transform .5s cubic-bezier(.22,.7,.2,1)}
.card .foto img.ok{opacity:1}
.card:hover .foto img.ok{transform:scale(1.07)}
.card .foto .fb{position:absolute;inset:0;display:none;place-items:center;font-size:42px;
  font-style:normal}
.card .foto.sem-foto{background:linear-gradient(160deg,var(--sup2),var(--sup))}
.card .foto.sem-foto .fb{display:grid}
.card .foto.carregando{background-image:linear-gradient(100deg,
  #EDEEF1 42%,#F8F9FA 50%,#EDEEF1 58%);background-size:280% 100%;
  animation:esqueleto 1.2s linear infinite}
@keyframes esqueleto{from{background-position:160% 0}to{background-position:-60% 0}}
/* véu que escurece o pé da foto: o selo branco some sobre foto clara */
.card .foto::before{content:"";position:absolute;inset:auto 0 0;height:38%;
  pointer-events:none;background:linear-gradient(transparent,rgba(11,12,15,.5))}

/* ── selos ───────────────────────────────────────────────────────────────
   ⚠️ O DESCONTO É O PRODUTO. Num site de achadinho a pessoa não procura
   "cortador de legumes", procura "quanto tá abatido" — então o % é o elemento
   mais gritante da grade inteira, e o resto dos selos se cala pra ele
   aparecer. Antes os três tinham o mesmo peso e nenhum era lido. */
.selo{position:absolute;top:9px;left:9px;font-size:10.5px;font-weight:700;
  padding:4px 9px;border-radius:8px;letter-spacing:.02em;
  background:rgba(11,12,15,.74);backdrop-filter:blur(8px);
  border:1px solid rgba(255,255,255,.12);color:var(--ink);z-index:2}
.selo.novo{color:var(--ink)}
.selo.off{left:auto;right:9px;font-size:14px;font-weight:850;letter-spacing:-.02em;
  padding:6px 11px;border-radius:10px;border-color:transparent;color:#fff;
  background:linear-gradient(160deg,var(--marca),var(--marca-esc));
  box-shadow:0 6px 18px rgba(255,61,110,.34)}
.selo.plat{top:auto;bottom:9px;font-size:10px;background:rgba(11,12,15,.6)}

.card .corpo{padding:12px 13px 14px;display:flex;flex-direction:column;gap:9px;flex:1}
.card h3{font-size:13px;font-weight:500;line-height:1.4;color:var(--muted);
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
  transition:color .22s}
.card:hover h3{color:var(--ink)}

/* ── botão: enche da esquerda pra direita no hover ─────────────────────── */
.card .ver{position:relative;overflow:hidden;isolation:isolate;
  display:flex;align-items:center;justify-content:center;gap:6px;
  background:var(--sup2);border:1px solid var(--linha2);border-radius:11px;
  padding:11px;font-size:13px;font-weight:750;margin-top:auto;min-height:44px;
  transition:border-color .22s,color .22s}
.card .ver::before{content:"";position:absolute;inset:0;z-index:-1;
  background:linear-gradient(100deg,var(--marca),var(--marca-esc));
  transform:scaleX(0);transform-origin:left;
  transition:transform .34s cubic-bezier(.22,.7,.2,1)}
.card:hover .ver{border-color:transparent;color:#fff}
.card:hover .ver::before{transform:scaleX(1)}
.card .ver span{display:inline-block;transition:transform .28s}
.card:hover .ver span{transform:translateX(4px)}

/* ── preço: o número é o argumento, então ele manda ─────────────────────
   ⚠️ 20px NÃO É PREÇO DE SITE DE DESCONTO. Era do mesmo tamanho do nome do
   produto, e a pessoa lia o card inteiro pra achar o que só interessava ela. */
.pr{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.pr b,.pr s{white-space:nowrap}
.pr b{font-size:25px;font-weight:850;letter-spacing:-.035em;color:var(--ink);
  font-variant-numeric:tabular-nums;line-height:1.05}
.pr b i{font-style:normal;font-weight:600;font-size:.5em;margin-right:3px;
  position:relative;top:-.35em;color:var(--muted)}
.pr s{color:var(--muted);font-size:12.5px;opacity:.8}
.afer{font-size:10.5px;color:var(--muted);margin-top:-4px;line-height:1.4;
  display:flex;align-items:center;gap:5px}
/* queda de preço é notícia: ganha cor, seta e peso */
.afer.caindo{color:var(--ok);font-weight:650}
.afer.caindo::before{content:"↓";font-weight:850;font-size:12px}

.vazio{text-align:center;padding:56px 20px;color:var(--muted)}
.vazio b{display:block;color:var(--ink);font-size:19px;margin-bottom:7px;font-weight:700}

/* ══ FAIXA DO GRUPO ══════════════════════════════════════════════════════
   O clique de afiliado é uma venda; o membro do grupo é uma anuidade. A faixa
   fica DEPOIS da primeira leva de produtos, não antes: quem acabou de chegar
   quer ver achadinho, e o convite convence melhor quem já gostou do que viu. */
.grupo-faixa{position:relative;overflow:hidden;border-radius:18px;
  border:1px solid rgba(255,61,110,.28);
  background:radial-gradient(120% 140% at 12% 0%,rgba(255,61,110,.16),transparent 62%),
             var(--sup);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.07);
  padding:clamp(20px,3vw,32px);margin:clamp(22px,3vw,34px) 0;
  display:flex;align-items:center;gap:clamp(16px,3vw,34px);flex-wrap:wrap}
.grupo-faixa .txt{flex:1;min-width:min(280px,100%)}
.grupo-faixa h3{font-size:clamp(19px,2.6vw,26px);font-weight:800;
  letter-spacing:-.03em;line-height:1.15}
.grupo-faixa h3 em{font-style:normal;color:var(--marca)}
.grupo-faixa p{color:var(--muted);font-size:14.5px;margin-top:9px;max-width:56ch}
.grupo-faixa .cta{flex:none;display:flex;align-items:center;gap:9px;
  background:linear-gradient(100deg,var(--marca),var(--marca-esc));color:#fff;
  font-weight:800;font-size:15px;padding:15px 26px;border-radius:13px;
  min-height:52px;box-shadow:0 12px 30px rgba(255,61,110,.32);
  transition:transform .2s,box-shadow .28s}
.grupo-faixa .cta:hover{transform:translateY(-2px);
  box-shadow:0 18px 44px rgba(255,61,110,.46)}
.grupo-faixa .cta span{transition:transform .28s}
.grupo-faixa .cta:hover span{transform:translateX(4px)}

/* ══ A LINHA DO PREÇO ═════════════════════════════════════════════════════
   O argumento da casa, em dois tamanhos: unha no card, gráfico no drawer. */
.faixa{width:68px;height:20px;display:block;margin-top:-2px;opacity:.9}

/* ══ DRAWER ═══════════════════════════════════════════════════════════════
   ⚠️ O CARD LEVA DIRETO PRA LOJA, E ISSO CONTINUA VALENDO — o drawer só
   intercepta o clique quando há histórico pra mostrar (3+ leituras). Sem
   histórico ele não tem o que dizer, e roubar o clique pra exibir menos do que
   a loja já mostra seria piorar a página em nome de um efeito.
   📌 E o `href` continua no HTML: sem JS, ou pra quem abre em aba nova com o
   meio do mouse, o card é um link normal. O drawer é ganho, não requisito. */
.veu{position:fixed;inset:0;z-index:60;background:rgba(5,6,8,.66);
  backdrop-filter:blur(3px);opacity:0;pointer-events:none;transition:opacity .28s}
.veu.aberto{opacity:1;pointer-events:auto}
.gaveta{position:fixed;top:0;right:0;bottom:0;z-index:61;width:min(430px,100%);
  background:var(--bg);border-left:1px solid var(--linha);
  transform:translateX(100%);transition:transform .34s cubic-bezier(.22,.72,.2,1);
  display:flex;flex-direction:column;overflow-y:auto;overscroll-behavior:contain}
.gaveta.aberta{transform:none}
@media(max-width:560px){
  /* no celular vem DE BAIXO: é de onde o polegar alcança, e é o gesto que
     todo app de compra usa pra detalhe de produto */
  .gaveta{top:auto;left:0;width:100%;max-height:88vh;border-left:0;
    border-top:1px solid var(--linha2);border-radius:20px 20px 0 0;
    transform:translateY(100%);padding-bottom:env(safe-area-inset-bottom)}
  .gaveta.aberta{transform:none}
  .gaveta::before{content:"";position:sticky;top:0;display:block;width:38px;
    height:4px;border-radius:99px;background:var(--linha2);margin:9px auto 0}
}
.g-x{position:absolute;top:12px;right:12px;z-index:2;width:36px;height:36px;
  border-radius:50%;border:1px solid var(--linha2);background:rgba(11,12,15,.7);
  backdrop-filter:blur(8px);color:var(--ink);font:inherit;font-size:17px;
  cursor:pointer;display:grid;place-items:center}
.g-foto{aspect-ratio:1;background:var(--foto);background-size:cover;
  background-position:center;flex:none}
.g-corpo{padding:18px 20px 24px;display:flex;flex-direction:column;gap:14px}
.g-corpo h3{font-size:17px;font-weight:650;line-height:1.35}
.g-preco{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.g-preco b{font-size:32px;font-weight:800;letter-spacing:-.03em;
  font-variant-numeric:tabular-nums}
.g-preco .tag{font-size:12px;font-weight:700;padding:4px 9px;border-radius:7px;
  background:var(--sup2);border:1px solid var(--linha2);color:var(--muted)}
.g-preco .tag.bom{background:var(--marca);border-color:transparent;color:#fff}

/* o gráfico grande: aqui cabe eixo, porque aqui a pergunta é "quanto" */
.g-graf{background:var(--sup);border:1px solid var(--linha);border-radius:var(--r);
  padding:16px 14px 10px}
.g-graf svg{width:100%;height:110px;display:block;overflow:visible}
.g-eixo{display:flex;justify-content:space-between;font-size:11px;
  color:var(--muted);margin-top:8px;font-variant-numeric:tabular-nums}
.g-cotas{display:flex;gap:8px;margin-top:12px}
.g-cota{flex:1;background:var(--sup);border:1px solid var(--linha);
  border-radius:11px;padding:10px 12px}
.g-cota i{font-style:normal;display:block;font-size:10.5px;color:var(--muted);
  text-transform:uppercase;letter-spacing:.07em}
.g-cota b{font-size:16px;font-weight:750;font-variant-numeric:tabular-nums}
.g-ir{display:flex;align-items:center;justify-content:center;gap:8px;
  background:var(--marca);color:#fff;border-radius:12px;padding:15px;
  font-size:15px;font-weight:750;min-height:50px;margin-top:2px;
  transition:filter .2s}
.g-ir:hover{filter:brightness(1.08)}
.g-nota{font-size:11.5px;color:var(--muted);line-height:1.5;text-align:center}

/* ══ SEÇÕES ═══════════════════════════════════════════════════════════════ */
section{padding:clamp(40px,6vw,72px) 0}
#produtos{padding-top:4px}
.eyebrow{display:inline-block;font-size:11.5px;font-weight:700;letter-spacing:.13em;
  text-transform:uppercase;color:var(--muted);margin-bottom:11px}
h2{font-size:clamp(22px,3.2vw,34px);font-weight:800;font-stretch:108%;
  letter-spacing:-.03em;line-height:1.1;text-wrap:balance}
.sec-sub{color:var(--muted);margin-top:11px;max-width:58ch;font-size:15px}
.reveal{opacity:1}
.js .reveal{opacity:0;transform:translateY(14px);
  transition:opacity .5s,transform .5s}
.js .reveal.dentro{opacity:1;transform:none}
.rodape-prova{padding:clamp(30px,5vw,54px) 0 clamp(20px,3vw,34px);
  border-top:1px solid var(--linha);margin-top:clamp(26px,4vw,46px)}
.prova-linha{color:var(--muted);font-size:14px;line-height:1.9;max-width:78ch}
.prova-linha b{color:var(--ink);font-weight:700;font-variant-numeric:tabular-nums}
.canais{display:flex;gap:8px;flex-wrap:wrap;margin-top:20px}
.ci{border:1px solid var(--linha2);background:var(--sup);border-radius:999px;
  padding:10px 16px;font-size:13.5px;font-weight:600;min-height:42px;
  display:flex;align-items:center;transition:background .2s,border-color .2s}
.ci:hover{background:var(--sup2);border-color:var(--marca)}

footer.wrap{border-top:1px solid var(--linha);padding-block:26px 40px;color:var(--muted);
  font-size:12.5px;display:flex;gap:16px;flex-wrap:wrap;justify-content:space-between}
footer a{border-bottom:1px solid var(--linha)}

/* ══ CELULAR: prioridade absoluta ═════════════════════════════════════════ */
@media(max-width:600px){
  /* 2 colunas com gap curto: cabe uma linha inteira a mais na primeira tela */
  .grade{grid-template-columns:repeat(2,1fr);gap:8px}
  .card .corpo{padding:9px 10px 11px;gap:7px}
  .card h3{font-size:12.5px}
  .card .ver{padding:10px;font-size:12.5px}
  .card .foto .fb{font-size:34px}
  /* preço empilhado: lado a lado o riscado quebrava no meio do número */
  .pr{flex-direction:column;align-items:flex-start;gap:1px}
  .pr b{font-size:17px}
  .pr s{font-size:11px}
  /* ⚠️ AQUI SOBRAVA A ALTURA CHUMBADA DA VERSÃO ANTIGA (height:52px/44px e
     lupa em top:26px/22px). Ela reintroduzia exatamente o defeito que o bloco
     do topo acabou de consertar: barra grudada mudando de tamanho. A altura
     agora vem da variável --h de cada caixa, num lugar só. */
  .zap{font-size:12.5px;padding:8px 13px}
}
@media(prefers-reduced-motion:reduce){
  *{animation:none!important;transition-duration:.01ms!important}
  .js .card,.js .reveal{opacity:1;transform:none}
}

/* ══ MOVIMENTO ════════════════════════════════════════════════════════════
   ⚠️ A PRIMEIRA CORREÇÃO EXAGEROU (31/08). Tirar o visual de IA virou tirar
   TODO o movimento, e o site ficou correto e sem graça — "uma lápide", nas
   palavras do Dre, e ele tinha razão.
   📌 A linha não é entre "com" e "sem" animação. É entre movimento AMBIENTE
   (bolha girando sozinha, brilho seguindo o mouse no vazio, gradiente varrendo
   texto) — que não informa nada e é a assinatura do gerador — e movimento
   FUNCIONAL, que responde ao dedo, ao scroll ou a um estado que mudou. O
   primeiro saiu e não volta. O segundo é o que faz parecer produto caro. */

/* ── capa: só a voz. A busca subiu pro topo e a notícia vem logo abaixo ── */
.capa{padding:clamp(22px,3.4vw,44px) 0 clamp(14px,2vw,24px);max-width:60ch}
.olho{display:inline-flex;align-items:center;gap:8px;font-size:11.5px;font-weight:700;
  letter-spacing:.15em;text-transform:uppercase;color:var(--muted);margin-bottom:13px}
.olho::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--marca)}
.capa h1{font-size:clamp(28px,4.2vw,46px);font-weight:800;font-stretch:110%;
  line-height:1.05;letter-spacing:-.04em;text-wrap:balance}
.capa h1 em{font-style:normal;color:var(--marca)}
.capa .sub{color:var(--muted);font-size:clamp(14px,1.6vw,16px);margin-top:13px;
  max-width:52ch}

/* ── abertura: a notícia do dia, em trilho ──────────────────────────────
   ⚠️ Aqui rodava um mural de fotos derivando, sem clique. O movimento era
   bonito e o conteúdo era zero. Um trilho ARRASTÁVEL de produto que baixou de
   preço tem a mesma energia visual e cada peça é notícia — e clicável, o que
   o mural nunca foi. */
.abertura{padding:clamp(6px,1.4vw,14px) 0 clamp(18px,2.6vw,30px)}
.abertura-topo{display:flex;align-items:baseline;justify-content:space-between;
  gap:12px;margin-bottom:13px}
.abertura h2{font-size:clamp(18px,2.4vw,24px);font-weight:800;letter-spacing:-.03em}
.abertura .dica{font-size:12px;color:var(--muted);white-space:nowrap}
.trilho{display:flex;gap:clamp(9px,1.2vw,14px);scroll-snap-type:x mandatory;
  padding-bottom:6px}
.trilho .card{flex:none;width:min(210px,62vw);scroll-snap-align:start}
@media(max-width:600px){.trilho .card{width:60vw;max-width:220px}}

/* ── header em vidro ao rolar ───────────────────────────────────────────── */
.topo.colado{background:rgba(11,12,15,.72);
  backdrop-filter:blur(22px) saturate(150%);
  -webkit-backdrop-filter:blur(22px) saturate(150%)}

/* ── card: responde ao dedo ─────────────────────────────────────────────── */
.card{transform-style:preserve-3d;
  transition:opacity .4s,transform .32s cubic-bezier(.22,.7,.2,1),
    border-color .22s,background .22s,box-shadow .32s}
.card:hover{border-color:var(--linha2);background:var(--sup2);
  box-shadow:0 18px 44px rgba(0,0,0,.42)}
.card .foto img{transition:opacity .35s,transform .5s cubic-bezier(.22,.7,.2,1)}
.card:hover .foto img.ok{transform:scale(1.07)}
.card .ver span{display:inline-block;transition:transform .28s}
.card:hover .ver span{transform:translateX(4px)}
/* entrada em cascata, escalonada por POSIÇÃO na grade e não por índice global:
   o card 40 não deve esperar 40 passos pra aparecer quando você rola até ele */
.js .card{opacity:0;transform:translateY(16px) scale(.985)}
.js .card.dentro{opacity:1;transform:none}
/* o filtro re-anima a saída: bater display:none faz a grade PISCAR, e é a
   diferença entre "o site respondeu" e "o site engasgou" */
.card.saindo{opacity:0;transform:scale(.96);pointer-events:none}

/* ── fitas com inércia: o cursor vira mão ao arrastar ───────────────────── */
.fita-rolo{scroll-behavior:smooth;cursor:grab}
.fita-rolo.arrastando{cursor:grabbing;scroll-behavior:auto;scroll-snap-type:none}
.fita-rolo.arrastando .chip,.fita-rolo.arrastando .loja{pointer-events:none}

/* ── números que sobem quando VOCÊ chega neles ──────────────────────────── */
.prova-linha b{font-variant-numeric:tabular-nums}

@media(prefers-reduced-motion:reduce){
  .card.saindo{opacity:1;transform:none}
}
</style>
</head>
<body>

<!-- ══ PRIMEIRA DOBRA ═══════════════════════════════════════════════════════
     Antes daqui vinha: 4 bolhas desfocadas com parallax, uma grade mascarada,
     um herói de tela cheia com título de 84px em gradiente animado, três
     números que subiam contando e uma moldura 9:16 girando com o mouse.
     Tudo isso ficava ENTRE a pessoa e o produto — e quem chega pelo link do
     Reels já sabe onde está: quer procurar o que viu.
     📌 Ordem nova = marca, busca, categorias, produto. A prova de confiança
     (quantos produtos, quantos dias de preço) desceu pra depois da grade:
     ela convence quem já está explorando, não quem acabou de chegar. -->
<div class="topo" id="topo">
  <div class="wrap barra">
    <a class="marca" href="#topo" aria-label="topshop"><svg class="ts" viewBox="0 0 32 32" aria-hidden="true"><path d="M6 0h13.4L32 12.6V26a6 6 0 0 1-6 6H6a6 6 0 0 1-6-6V6a6 6 0 0 1 6-6Z" fill="#FF3D6E"/><circle cx="23.6" cy="8.4" r="2.1" fill="#0B0C0F" opacity=".55"/><path d="M6.6 12.4h13.2v3.5h-4.8v10.4h-3.6V15.9H6.6z" fill="#fff"/></svg><span>top<i>shop</i></span></a>
    <label class="buscabox">
      <input id="busca" type="search" placeholder="O que você viu no vídeo?"
             autocomplete="off" aria-label="Buscar produto">
      <svg class="lupa" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/></svg>
    </label>
    <button class="tema" id="tema" type="button" aria-label="Trocar entre claro e escuro">☾</button>
    <a class="zap" href="{{GRUPO_TOPO}}" target="_blank" rel="noopener">Grupo</a>
  </div>
</div>

<main class="wrap">

  <!-- ⚠️ TERCEIRA VERSÃO DESTA ABERTURA, e as duas anteriores erraram por
       motivos OPOSTOS. A primeira era um herói institucional de tela cheia,
       que ficava entre a pessoa e o produto. A segunda foi um mural de fotos
       derivando: bonito, sem clique, sem informação — enfeite caro.
       📌 O que abre a página agora é NOTÍCIA: o que baixou de preço hoje, com
       o título mudando quando não baixou nada. A voz da marca cabe em três
       linhas acima; o resto da primeira dobra é mercadoria clicável. -->
  <section class="capa">
    <span class="olho">Achados dos nossos vídeos</span>
    <h1>Viralizou. <em>A gente achou.</em></h1>
    <p class="sub">A gente confere o preço todo dia. Clica em qualquer produto
       pra ver o histórico e saber se hoje é hora de comprar.</p>
  </section>

  {{ABERTURA}}

  <section id="produtos">
    {{VITRINE}}
  </section>

  <!-- ⚠️ AQUI MORAVAM DOIS BLOCOS DE TRÊS QUADRADINHOS: "Como funciona" com
       passos numerados e "Por que confiar" com três números gigantes. O Dre
       matou a charada: "esse final aí é a cara da IA, todo site que eu vejo das
       pessoas sempre tem isso". Está certo — trio de cards com ícone, título e
       parágrafo é o layout que todo gerador cospe, e ele aparece justamente
       onde o site devia estar VENDENDO.
       📌 Loja não explica como loja funciona. A prova vira UMA LINHA honesta, e
       o espaço volta pro que converte. Os números continuam aqui: só pararam
       de posar de infográfico. -->
  <section class="rodape-prova">
    <p class="prova-linha">
      <b>{{TOTAL}}</b> achados no ar · preços conferidos em <b>{{DATA}}</b> ·
      <b>{{DIAS}}</b> dias de histórico de preço · link que morre sai sozinho
    </p>
    <div class="canais">
      <a class="ci" href="{{GRUPO_TOPO}}" target="_blank" rel="noopener">Grupo de achadinhos</a>
      <a class="ci" href="{{INSTAGRAM}}" target="_blank" rel="noopener">Instagram</a>
      <a class="ci" href="{{TIKTOK}}" target="_blank" rel="noopener">TikTok</a>
      <a class="ci" href="{{YOUTUBE}}" target="_blank" rel="noopener">YouTube</a>
      <a class="ci" href="mailto:{{EMAIL}}">Fale com a gente</a>
    </div>
  </section>
</main>

<div class="veu" id="veu" hidden></div>
<aside class="gaveta" id="gaveta" role="dialog" aria-modal="true"
       aria-label="Detalhe do produto" hidden>
  <button class="g-x" id="g-x" aria-label="Fechar">&times;</button>
  <div class="g-foto" id="g-foto"></div>
  <div class="g-corpo">
    <h3 id="g-nome"></h3>
    <div class="g-preco"><b id="g-preco"></b><span class="tag" id="g-tag"></span></div>
    <div class="g-graf" id="g-graf"></div>
    <div class="g-cotas" id="g-cotas"></div>
    <a class="g-ir" id="g-ir" target="_blank" rel="noopener">Ver na loja <span>&rarr;</span></a>
    <p class="g-nota" id="g-nota"></p>
  </div>
</aside>

<footer class="wrap">
  <span>&copy; {{ANO}} topshop &middot; conteúdo publicitário &middot; links de afiliado
    &middot; atualizado em {{DATA}}</span>
  <span><a href="{{INSTAGRAM}}" target="_blank" rel="noopener">Instagram</a>
    &middot; <a href="{{TIKTOK}}" target="_blank" rel="noopener">TikTok</a>
    &middot; <a href="{{YOUTUBE}}" target="_blank" rel="noopener">YouTube</a></span>
</footer>

<script>
/* a classe .js liga as animações de entrada. Sem JS, tudo já nasce visível —
   os cards vêm prontos do servidor, então a vitrine funciona mesmo assim. */
document.documentElement.className += ' js';
var calmo = matchMedia('(prefers-reduced-motion: reduce)').matches;
var fino  = matchMedia('(pointer:fine)').matches;
if (calmo) document.documentElement.className =
  document.documentElement.className.replace(' js', '');

/* ── fotos: esqueleto -> ok, ou volta pro emoji se a CDN falhar ─────────── */
document.querySelectorAll('.foto img').forEach(function(im){
  var box = im.parentNode;
  var pronto = function(){ box.classList.remove('carregando'); im.classList.add('ok'); };
  var falhou = function(){ box.classList.remove('carregando');
                           box.classList.add('sem-foto'); im.remove(); };
  if (im.complete) { im.naturalWidth ? pronto() : falhou(); return; }
  im.addEventListener('load', pronto);
  im.addEventListener('error', falhou);
});

/* ── revelação em cascata ───────────────────────────────────────────────── */
var obs = new IntersectionObserver(function(ents){
  ents.forEach(function(en){
    if (!en.isIntersecting) return;
    var el = en.target, i = +(el.dataset.i || 0);
    setTimeout(function(){ el.classList.add('dentro'); }, (i % 8) * 55);
    obs.unobserve(el);
  });
}, {rootMargin: '0px 0px -8% 0px'});
document.querySelectorAll('.card').forEach(function(c, i){
  c.dataset.i = i; obs.observe(c);
});
document.querySelectorAll('.reveal').forEach(function(s){ obs.observe(s); });

/* ── filtros e busca: só mostram e escondem o que já veio pronto ────────── */
var st = {plat: 'todos', cat: 'todos', q: ''};
var cards = [].slice.call(document.querySelectorAll('.card'));
var semRes = document.getElementById('sem-res');

/* ⚠️ FILTRAR COM display:none FAZ A GRADE PISCAR. O card some no mesmo frame
   e os vizinhos saltam pro lugar dele — parece engasgo, não resposta. Aqui a
   saída é animada (.saindo) e só depois vira .esconde; a volta re-escalona a
   entrada. É a diferença entre "o site respondeu" e "o site travou".
   Sem JS a grade nasce inteira e o filtro simplesmente não existe. */
var pintando = null;
function aplicar(){
  var visiveis = 0, entrando = [];
  cards.forEach(function(c){
    var ok = (st.plat === 'todos' || c.dataset.plataforma === st.plat)
          && (st.cat === 'todos' || c.dataset.categoria === st.cat)
          && (!st.q || (c.dataset.busca || '').indexOf(st.q) > -1);
    if (ok){
      visiveis++;
      if (c.classList.contains('esconde')){
        c.classList.remove('esconde');
        c.classList.add('saindo');       /* nasce encolhido e cresce */
        entrando.push(c);
      }
    } else if (!c.classList.contains('esconde')) {
      c.classList.add('saindo');
    }
  });
  if (semRes) semRes.style.display = visiveis ? 'none' : '';

  clearTimeout(pintando);
  requestAnimationFrame(function(){
    entrando.forEach(function(c, i){
      setTimeout(function(){ c.classList.remove('saindo'); }, Math.min(i, 10) * 22);
    });
  });
  /* só tira do fluxo depois que a saída terminou */
  pintando = setTimeout(function(){
    cards.forEach(function(c){
      if (c.classList.contains('saindo')) c.classList.add('esconde');
    });
  }, 300);
}

var caixaLojas = document.getElementById('filtros-plat');
if (caixaLojas) caixaLojas.addEventListener('click', function(e){
  var b = e.target.closest('.loja');
  if (!b || b.disabled) return;
  caixaLojas.querySelectorAll('.loja').forEach(function(o){
    o.setAttribute('aria-selected', String(o === b)); });
  st.plat = b.dataset.plat; aplicar();
});
var caixaCats = document.getElementById('filtros');
if (caixaCats) caixaCats.addEventListener('click', function(e){
  var b = e.target.closest('.chip');
  if (!b) return;
  caixaCats.querySelectorAll('.chip').forEach(function(o){
    o.setAttribute('aria-pressed', String(o === b)); });
  st.cat = b.dataset.filtro; aplicar();
});
/* ⚠️ DUAS CAIXAS, UM ESTADO SÓ. A grande vive na capa e rola embora; a
   compacta vive no topo grudado. Se cada uma tivesse a própria busca, digitar
   numa e rolar até a outra mostraria a página filtrada com o campo vazio — e a
   pessoa não teria como saber por que faltam produtos. Cada uma escreve no
   mesmo `st.q` e espelha o texto na irmã. */
var inp = document.getElementById('busca');
if (inp){
  inp.addEventListener('input', function(e){
    st.q = e.target.value.toLowerCase().trim(); aplicar();
  });
  document.addEventListener('keydown', function(e){
    if (e.key === '/' && document.activeElement !== inp){ e.preventDefault(); inp.focus(); }
  });
}

/* ── o topo encolhe ao grudar ────────────────────────────────────────────
   ⚠️ NÃO É `position:sticky` SOZINHO. Sticky mantém a busca na tela, mas com o
   tamanho de tela cheia ela comeria 150px de altura o scroll inteiro — no
   celular, quase uma linha de produtos, permanentemente. A classe `.colado`
   encolhe a busca, esconde a frase de posicionamento e devolve essa altura pro
   que interessa. É a mesma coisa que app de marketplace faz.

   O limiar tem HISTERESE (32/8) de propósito: com um valor só, parar o dedo
   exatamente na fronteira faz a barra piscar entre os dois tamanhos a cada
   pixel de rolagem. */
var topo = document.getElementById('topo'), colado = false, pedido = false;
function medirTopo(){
  var y = scrollY;
  if (!colado && y > 32){ colado = true; topo.classList.add('colado'); }
  else if (colado && y < 8){ colado = false; topo.classList.remove('colado'); }
  pedido = false;
}
addEventListener('scroll', function(){
  if (pedido) return;
  pedido = true; requestAnimationFrame(medirTopo);
}, {passive:true});
medirTopo();

/* ⌨️ o teclado do celular cobre metade da tela: ao focar a busca, leva a
   grade pro topo pra pessoa ver o resultado enquanto digita */
if (inp) inp.addEventListener('focus', function(){
  if (matchMedia('(max-width:600px)').matches && scrollY < 8)
    setTimeout(function(){ scrollTo({top: 40, behavior: 'smooth'}); }, 60);
});
/* ── card acompanhando o dedo, discretamente ─────────────────────────────
   ⚠️ 2.5° E NÃO 7°. A versão antiga inclinava 7 graus e ficava com cara de
   cartinha de RPG girando — movimento chamando atenção pra si. Nesta faixa o
   olho não vê "animação", vê que o card TEM peso. Só em ponteiro fino: no
   celular não existe hover e o cálculo por toque só atrapalha o scroll. */
if (!calmo && fino) cards.forEach(function(c){
  c.addEventListener('pointermove', function(e){
    var r = c.getBoundingClientRect();
    var x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
    c.style.transform = 'perspective(900px) rotateX(' + (-y * 2.5).toFixed(2) +
      'deg) rotateY(' + (x * 2.5).toFixed(2) + 'deg) translateY(-4px)';
  });
  c.addEventListener('pointerleave', function(){ c.style.transform = ''; });
});

/* ── fitas de categoria arrastáveis, com inércia ─────────────────────────
   O navegador já dá inércia ao dedo no celular. O que falta é o DESKTOP, onde
   arrastar não faz nada e a fita parece travada — então aqui a gente empresta
   o mesmo gesto pro mouse, e solta com velocidade decrescente. */
document.querySelectorAll('.fita-rolo').forEach(function(f){
  var baixo = false, x0 = 0, e0 = 0, v = 0, ultimo = 0, quadro;
  f.addEventListener('pointerdown', function(e){
    if (e.pointerType === 'touch') return;   /* o celular já sabe fazer isso */
    baixo = true; x0 = e.clientX; e0 = f.scrollLeft; v = 0; ultimo = e.clientX;
    cancelAnimationFrame(quadro); f.classList.add('arrastando');
  });
  addEventListener('pointermove', function(e){
    if (!baixo) return;
    f.scrollLeft = e0 - (e.clientX - x0);
    v = e.clientX - ultimo; ultimo = e.clientX;
  });
  addEventListener('pointerup', function(){
    if (!baixo) return;
    baixo = false; f.classList.remove('arrastando');
    (function desliza(){
      if (Math.abs(v) < .4) return;
      f.scrollLeft -= v; v *= .93;          /* atrito */
      quadro = requestAnimationFrame(desliza);
    })();
  });
});

/* ── números subindo QUANDO VOCÊ CHEGA NELES ─────────────────────────────
   ⚠️ Isto já existiu e eu tirei junto com o resto — mas o defeito não era o
   número subir: era subir no carregamento, longe dos olhos, num herói que
   ninguém pediu. Disparado por chegada, o movimento tem causa: você rolou até
   ali, e o número reage. O valor certo está no HTML desde sempre, então sem JS
   (ou com reduced-motion) a página mostra o número final e pronto. */
var obsNum = new IntersectionObserver(function(ents){
  ents.forEach(function(en){
    if (!en.isIntersecting) return;
    var el = en.target, alvo = parseInt(el.textContent, 10) || 0;
    obsNum.unobserve(el);
    if (calmo || !alvo) return;
    var sufixo = el.textContent.replace(/[\d.]/g, ''), t0 = null;
    requestAnimationFrame(function passo(t){
      if (!t0) t0 = t;
      var k = Math.min(1, (t - t0) / 900), e = 1 - Math.pow(1 - k, 3);
      el.textContent = Math.round(alvo * e) + sufixo;
      if (k < 1) requestAnimationFrame(passo);
    });
  });
}, {threshold: .6});
document.querySelectorAll('.prova-linha b').forEach(function(b){ obsNum.observe(b); });


/* ══ O DRAWER — a única coisa nesta página que o concorrente não copia ═════
   Ele existe pra responder a pergunta que o card não cabe: "esse preço é
   bom?". Não é "ver mais": é o histórico que só quem guarda leitura diária há
   semanas consegue mostrar.

   ⚠️ SÓ INTERCEPTA O CLIQUE QUANDO TEM O QUE DIZER (3+ leituras). Sem série,
   o card segue como link direto pra loja — roubar o clique pra exibir menos do
   que a loja já mostra seria piorar a página em nome de um efeito. Ctrl/⌘,
   botão do meio e "abrir em nova aba" também passam direto: quem pediu outra
   aba pediu a loja, não um painel. */
var veu = document.getElementById('veu'), gav = document.getElementById('gaveta');
var reais = function(n){ return 'R$ ' + n.toFixed(2).replace('.', ','); };

function grafico(vals, dias){
  var L = 100, A = 46, lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
  var faixa = (hi - lo) || 1, passo = L / (vals.length - 1);
  var y = function(v){ return A - 3 - ((v - lo) / faixa) * (A - 6); };
  var pts = vals.map(function(v, i){ return (i*passo).toFixed(2) + ',' + y(v).toFixed(2); });
  var caiu = vals[vals.length-1] < vals[0];
  var cor = caiu ? 'var(--ok)' : 'var(--marca)';
  /* a área sob a linha dá volume sem inventar dado: é a mesma curva */
  return '<svg viewBox="0 0 ' + L + ' ' + A + '" preserveAspectRatio="none">' +
    '<defs><linearGradient id="gsob" x1="0" x2="0" y1="0" y2="1">' +
    '<stop offset="0" stop-color="' + cor + '" stop-opacity=".28"/>' +
    '<stop offset="1" stop-color="' + cor + '" stop-opacity="0"/></linearGradient></defs>' +
    '<polygon points="0,' + A + ' ' + pts.join(' ') + ' ' + L + ',' + A + '" fill="url(#gsob)"/>' +
    '<polyline points="' + pts.join(' ') + '" fill="none" stroke="' + cor +
      '" stroke-width="1.8" vector-effect="non-scaling-stroke" ' +
      'stroke-linejoin="round" stroke-linecap="round"/>' +
    '<circle cx="' + L + '" cy="' + y(vals[vals.length-1]).toFixed(2) +
      '" r="2.6" fill="' + cor + '" vector-effect="non-scaling-stroke"/></svg>' +
    '<div class="g-eixo"><span>' + dias[0] + '</span><span>' +
      dias[dias.length-1] + '</span></div>';
}

function abrir(c){
  var vals = (c.dataset.serie || '').split(',').filter(Boolean).map(Number);
  var dias = (c.dataset.dias || '').split(',').filter(Boolean);
  if (vals.length < 3) return false;
  var preco = +c.dataset.preco || vals[vals.length-1];
  var mn = +c.dataset.min, mx = +c.dataset.max;

  document.getElementById('g-nome').textContent = c.querySelector('h3').textContent;
  document.getElementById('g-foto').style.backgroundImage =
    c.dataset.img ? 'url("' + c.dataset.img + '")' : '';
  document.getElementById('g-preco').textContent = reais(preco);
  document.getElementById('g-graf').innerHTML = grafico(vals, dias);
  document.getElementById('g-ir').href = c.href;

  /* ⚠️ O VEREDITO SAI DA CONTA, NÃO DE UMA FRASE FIXA. "menor preço" só
     aparece quando o preço de hoje É o menor observado — texto de urgência
     inventado é o que faz a pessoa parar de acreditar na página inteira. */
  var tag = document.getElementById('g-tag'), hoje = vals[vals.length-1];
  var dif = mx > mn ? Math.round((1 - (hoje - mn) / (mx - mn)) * 100) : 0;
  if (hoje <= mn){ tag.textContent = 'menor preço do período'; tag.className = 'tag bom'; }
  else if (dif >= 60){ tag.textContent = 'perto do menor preço'; tag.className = 'tag bom'; }
  else if (hoje >= mx){ tag.textContent = 'maior preço do período'; tag.className = 'tag'; }
  else { tag.textContent = dif + '% abaixo do topo'; tag.className = 'tag'; }

  document.getElementById('g-cotas').innerHTML =
    '<div class="g-cota"><i>menor</i><b>' + reais(mn) + '</b></div>' +
    '<div class="g-cota"><i>maior</i><b>' + reais(mx) + '</b></div>' +
    '<div class="g-cota"><i>leituras</i><b>' + (c.dataset.obs || vals.length) + '</b></div>';
  document.getElementById('g-nota').textContent =
    'Preços conferidos por nós em ' + (c.dataset.loja || 'loja') +
    '. Última leitura em ' + (c.dataset.visto || '—') +
    '. Quem define o preço da compra é a loja.';

  veu.hidden = gav.hidden = false;
  requestAnimationFrame(function(){
    veu.classList.add('aberto'); gav.classList.add('aberta');
  });
  document.body.style.overflow = 'hidden';
  document.getElementById('g-x').focus();
  return true;
}

function fechar(){
  veu.classList.remove('aberto'); gav.classList.remove('aberta');
  document.body.style.overflow = '';
  setTimeout(function(){ veu.hidden = gav.hidden = true; }, 340);
}

cards.forEach(function(c){
  c.addEventListener('click', function(e){
    /* modificadores e botão do meio querem a loja, não o painel */
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    if (abrir(c)) e.preventDefault();
  });
});
document.getElementById('g-x').addEventListener('click', fechar);
veu.addEventListener('click', fechar);
addEventListener('keydown', function(e){ if (e.key === 'Escape' && !gav.hidden) fechar(); });
/* ══ TEMA CLARO/ESCURO ═══════════════════════════════════════════════════
   ⚠️ A PREFERÊNCIA DO SISTEMA É O PADRÃO, e a escolha manual vence. Quem nunca
   clicou recebe o que o celular dele já diz (`prefers-color-scheme`); quem
   clicou uma vez recebe o que pediu, pra sempre. Assumir escuro pra todo mundo
   é decidir pelo outro num assunto em que ele já tem uma opinião registrada.
   📌 `localStorage` dentro de try/catch: navegador em janela anônima e alguns
   modos de privacidade LANÇAM ao acessar, e um tema quebrado derrubaria o
   resto do script — inclusive a busca. */
(function(){
  var raiz = document.documentElement, bt = document.getElementById('tema');
  var guardado = null;
  try { guardado = localStorage.getItem('topshop-tema'); } catch (e) {}
  var escuro = guardado ? guardado === 'escuro'
             : !matchMedia('(prefers-color-scheme: light)').matches;
  function pintar(){
    raiz.setAttribute('data-tema', escuro ? 'escuro' : 'claro');
    if (bt) bt.textContent = escuro ? '☾' : '☀';
    var m = document.querySelector('meta[name=theme-color]');
    if (m) m.setAttribute('content', escuro ? '#0B0C0F' : '#F7F7F9');
  }
  pintar();
  if (bt) bt.addEventListener('click', function(){
    escuro = !escuro; pintar();
    try { localStorage.setItem('topshop-tema', escuro ? 'escuro' : 'claro'); } catch (e) {}
  });
})();

/* ══ MODO GRADE / LISTA ══════════════════════════════════════════════════
   Só troca uma classe: os mesmos cards, outro arranjo. Nada é re-renderizado,
   então o filtro, a busca e o drawer continuam funcionando sem saber que isto
   existe. */
(function(){
  var caixa = document.getElementById('modos');
  if (!caixa) return;
  var grades = [].slice.call(document.querySelectorAll('.grade'));
  var lembrado = null;
  try { lembrado = localStorage.getItem('topshop-modo'); } catch (e) {}
  function aplicarModo(m){
    grades.forEach(function(g){ g.classList.toggle('lista', m === 'lista'); });
    caixa.querySelectorAll('.modo').forEach(function(b){
      b.setAttribute('aria-pressed', String(b.dataset.modo === m)); });
    try { localStorage.setItem('topshop-modo', m); } catch (e) {}
  }
  if (lembrado === 'lista') aplicarModo('lista');
  caixa.addEventListener('click', function(e){
    var b = e.target.closest('.modo');
    if (b) aplicarModo(b.dataset.modo);
  });
})();
</script>
</body>
</html>
"""


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