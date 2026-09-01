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
from urllib.parse import quote

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("bio_page_builder")

# A marca, em curvas de verdade (ver gerar_marca.py). Se o módulo não tiver
# sido deployado, o site NÃO fica sem logo: cai no desenho antigo e o log diz
# qual está no ar. 📌 Cair no padrão calado foi o que colocou a logo de uma
# conta no vídeo de outra (shared/marca.py conta a história inteira).
try:
    from shared.marca_svg import (SIMBOLO as _SVG_SIMBOLO,
                                  WORDMARK as _SVG_WORDMARK, MICRO)
except Exception:
    try:
        from marca_svg import (SIMBOLO as _SVG_SIMBOLO,
                               WORDMARK as _SVG_WORDMARK, MICRO)
    except Exception:
        _SVG_SIMBOLO = _SVG_WORDMARK = MICRO = ""
        log.warning("⚠️  shared/marca_svg.py não encontrado — o site vai sair "
                    "com o desenho ANTIGO da marca. Deploye o módulo.")

MANIFESTO_FOTOS = Path(__file__).parent.parent / "shared" / "fotos_manifesto.json"

# ⚠️ SEM MANIFESTO O SITE NÃO QUEBRA, SÓ NÃO GANHA. Cada foto cai na URL
# original da loja, exatamente como antes de existir o pipeline. 📌 Recurso
# novo que derruba o que já funcionava não é recurso, é regressão.
_FOTOS = {}
try:
    if MANIFESTO_FOTOS.exists():
        _FOTOS = json.loads(MANIFESTO_FOTOS.read_text(encoding="utf-8"))
except Exception as e:
    log.warning(f"   ⚠️  manifesto de fotos ilegível ({e}) — usando as originais")

SAIDA_HTML = Path(__file__).parent.parent / "site" / "index.html"
JSON_FILA = Path(__file__).parent.parent / "shared" / "produtos_fila.json"
# ⚠️ O REGISTRO DO QUE FOI MANDADO, não da fila. A fila é intenção; este
# arquivo é fato — e a faixa do grupo só convence porque mostra fato.
ARQ_ENVIADOS = Path(__file__).parent.parent / "shared" / "whatsapp_enviados.json"
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


# larguras que o pipeline grava (fotografia.LARGURAS)
_LARGS_FOTO = (320, 640, 960)


def _foto(p, papel="card", tam=640):
    """(src, atributos extras) pra montar o <img> de um produto.

    Devolve a foto TRATADA quando existe e serve pro papel; senão a original.
    📌 O `papel` é o que impede um infográfico de virar a foto grande da
    abertura: quem decide não é o layout, é a classe que o pipeline mediu."""
    url = (p.get("imagem") or "").strip()
    if not url:
        return "", ""
    reg = _FOTOS.get(url)
    if not reg or not reg.get("larguras"):
        return url, ""
    classe = reg.get("classe", "C")
    if papel == "hero" and classe != "A":
        return url, ""
    ident = reg["id"]
    # ⚠️ É O srcset QUE PAGA A CONTA DE HOSPEDAR. Card de 170px baixando 960px
    # é pior que hotlinkar a Shopee — a gente teria trocado CDN deles por
    # servidor nosso e ainda mandado mais bytes.
    fontes = " ".join(f"f/{ident}_{L}.webp {L}w" for L in _LARGS_FOTO)
    src = f"f/{ident}_{tam if tam in _LARGS_FOTO else 640}.webp"
    return src, f' srcset="{fontes}" sizes="(max-width:700px) 45vw, 340px"'


def _classe_foto(p) -> str:
    reg = _FOTOS.get((p.get("imagem") or "").strip()) or {}
    return reg.get("classe", "")


def _foto_html(p: dict, titulo: str, novo: bool = False) -> str:
    """Foto do produto com os três estados previstos: carregando (esqueleto),
    ok, e sem-foto (a Amazon hoje não devolve imagem)."""
    src, extra = _foto(p, "card", 320)
    img = html.escape(src)
    emoji = _loja(p)[1]
    if not img:
        return (f'<div class="foto sem-foto"><em class="fb">{emoji}</em>'
                f'{_selos_html(p, novo)}</div>')
    return (f'<div class="foto carregando">'
            f'<img src="{img}"{extra} alt="{titulo}" loading="lazy" '
            f'decoding="async">'
            f'<em class="fb">{emoji}</em>{_selos_html(p, novo)}</div>')


def _card_destaque(p: dict) -> str:
    """O achado do dia, na moldura 9:16 — o formato do Reels de onde a pessoa
    veio. Continua o vídeo em vez de recomeçar do zero."""
    titulo = html.escape(_titulo_legivel(p.get("titulo") or p.get("nome", ""), 70))
    link = html.escape(p.get("link", "#"))
    src, extra = _foto(p, "card", 640)
    img = html.escape(src)
    capa = (f'<img class="capa" src="{img}"{extra} alt="{titulo}" '
            f'decoding="async">'
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


# ⚠️ O TIL BATIA NA LINHA DE CIMA (01/09). O Dre mandou o print: o ~ de ATENÇÃO
# passando por dentro de MERECE SUA. Medido NA PRÓPRIA PÁGINA renderizada, com
# a Instrument Serif carregada (168px):
#
#     NEM TUDO / MERECE SUA (maiúscula seca)  sobe 0,672 em acima da base
#     ATENÇÃO.  (com o til do Ã)              sobe 0,935 em
#     o Ç desce                               0,214 em
#
# O line-height é 0,82 em, que é a distância entre as bases. Como 0,935 > 0,82,
# a tinta da linha de baixo invade 0,115 em da linha de cima. Não é bug de
# navegador nem de fonte: é aritmética de entrelinha apertada.
#
# ⚠️ E A PRIMEIRA MEDIÇÃO MENTIU: num arquivo de teste isolado o canvas devolveu
# 0,844 em, porque o @font-face por file:// não pegou e o número veio da fonte
# de reserva. A correção dimensionada por ele ficou curta e o til continuou
# batendo. 📌 Métrica de fonte só vale medida na página que de fato a renderiza
# — e conferida no print, que é onde o defeito aparece.
#
# 📌 A CORREÇÃO É POR LINHA, NÃO NO BLOCO. Afrouxar tudo resolveria e custaria o
# aperto tipográfico em TODA manchete, inclusive as sem acento. Como a manchete
# muda toda semana, a folga sai do texto: acento alto ganha `.alta` (respiro em
# cima), cedilha e rabo ganham `.baixa` (respiro embaixo, que é o que separa o Ç
# do subtítulo). Manchete sem acento continua colada como estava.
_ACENTO_ALTO = set("ãõáàâéêíóôúüÃÕÁÀÂÉÊÍÓÔÚÜ")
_RABO_BAIXO = set("çÇqQjJ,;")


def _manchete(linhas: list, grifo: int = -1) -> str:
    """As três linhas gigantes da abertura, com a folga certa em cada uma.

    `grifo` é o índice da linha que sai na cor da marca (-1 = a última)."""
    fora = []
    grifo = grifo % len(linhas)
    for i, txt in enumerate(linhas):
        letras = set(txt)
        cls = []
        if _ACENTO_ALTO & letras:
            cls.append("alta")
        if _RABO_BAIXO & letras:
            cls.append("baixa")
        marca = f' class="{" ".join(cls)}"' if cls else ""
        miolo = html.escape(txt)
        if i == grifo:
            miolo = f"<em>{miolo}</em>"
        fora.append(f"<span{marca}><b>{miolo}</b></span>")
    return "<h1>" + "".join(fora) + "</h1>"


def _abre_html(produtos: list) -> str:
    """A abertura. Três linhas de tipo enorme e um número — nada mais.

    ⚠️ NÃO TEM PRODUTO AQUI, e é a primeira vez neste projeto que a primeira
    dobra não tenta vender. O motivo é o diagnóstico do Dre: "parecer padrão".
    Uma página que começa com grade só pode parecer grade. Esta tela existe pra
    dar UM respiro e um tom — e custa 400ms de rolagem, não uma sessão.

    ⚠️ "ACHADOS DOS NOSSOS VÍDEOS" SAIU (01/09). Era a frase que a casa usa pra
    falar de si mesma: quem chega de um anúncio não sabe que existem vídeos, e a
    manchete gastava as três linhas maiores do site explicando NOSSO processo em
    vez de dar um motivo pra ficar.

    📌 A MANCHETE DO DRE ACERTOU O QUE AS MINHAS ERRARAM: ela fala do MUNDO, não
    da loja. "Nem tudo merece sua atenção" é uma frase que existiria sem a
    TopShop — e por isso soa marca, não vitrine. As minhas ("o que vale a pena",
    "o preço de hoje, conferido") descreviam o serviço, que é o mesmo defeito de
    "achados dos nossos vídeos" num nível mais bem-vestido.

    A estrutura é dois tempos: a manchete tira algo (quase nada presta) e a
    linha menor devolve (a gente acha o que presta). O número à direita continua
    sendo a prova — promessa, resolução, evidência, nessa ordem."""
    return (
        '<section class="abre" id="abre"><div class="abre-t">'
        + _manchete(["Nem tudo", "merece sua", "atenção."], grifo=-1) +
        '<p class="abre-sub">A gente encontra o que merece.</p></div>'
        f'<p class="abre-n"><b>{len(produtos)}</b>achados no ar<br>'
        f'preço conferido em {time.strftime("%d/%m")}</p>'
        + _abre_foto(produtos) +
        '</section>')


def _abre_foto(produtos: list) -> str:
    """A foto que passa POR CIMA do título.

    ⚠️ É O MOVIMENTO QUE QUEBRA A SENSAÇÃO DE CAIXAS EMPILHADAS. No print 2 do
    ERA, a buganvília rosa cobre parte de "NEW GOLDEN MILE" — dois elementos
    disputando o mesmo espaço, um na frente do outro. Enquanto tudo estiver
    lado a lado em blocos, o layout parece grade por mais bonito que seja.
    📌 Pega o produto com foto e maior desconto: se vai ficar do tamanho de um
    terço da tela, que seja o que mais convence."""
    def _peso(p):
        r = p.get("preco_resumo") or {}
        return int(r.get("off") or 0) + int(r.get("caiu") or 0)
    com_foto = [p for p in produtos if (p.get("imagem") or "").strip()]
    if not com_foto:
        return ""
    # ⚠️ AQUI A CLASSE MANDA MAIS QUE O DESCONTO. Esta foto ocupa um terço da
    # primeira tela; um infográfico de vendedor nesse tamanho desmonta a página
    # inteira. Havendo qualquer produto tratado, ele ganha do maior desconto.
    editoriais = [p for p in com_foto if _classe_foto(p) == "A"]
    alvo = max(editoriais or com_foto, key=_peso)
    src, extra = _foto(alvo, "hero", 960)
    return (f'<div class="abre-foto"><img src="{html.escape(src)}"{extra} '
            f'alt="" loading="eager" decoding="async"></div>')


def _destaque_editorial(produtos: list) -> str:
    """Um produto grande, dois pequenos invadindo a composição.

    ⚠️ O GRANDE É O DE MAIOR QUEDA, não o mais caro nem o primeiro da lista. A
    manchete de um site de achadinho é o desconto — e escolher pelo dado
    significa que a home muda sozinha todo dia, sem ninguém curar.
    Sem queda nenhuma, cai pro maior desconto absoluto; sem isso, o primeiro.
    📌 A escolha vem de `preco_resumo`, que já existia. Nenhum campo novo."""
    if not produtos:
        return ""
    def _queda(p):
        r = p.get("preco_resumo") or {}
        return (int(r.get("caiu") or 0), int(r.get("off") or 0))
    ordenado = sorted(produtos, key=_queda, reverse=True)
    estrela, apoio = ordenado[0], ordenado[1:3]

    r = estrela.get("preco_resumo") or {}
    titulo = html.escape(_titulo_legivel(estrela.get("titulo")
                                         or estrela.get("nome", ""), 78))
    link = html.escape(estrela.get("link", "#"))
    _src_e, _ex_e = _foto(estrela, "card", 960)
    img = html.escape(_src_e)
    _extra_e = _ex_e
    marca = (f'{r["caiu"]}% mais barato' if r.get("caiu")
             else (f'{r["off"]}% off' if r.get("off") else "Achado do dia"))
    numero = (f'-{r["caiu"]}%' if r.get("caiu")
              else (f'-{r["off"]}%' if r.get("off") else "novo"))
    rot = "Baixou de preço" if r.get("caiu") else "Achado do dia"

    foto = (f'<img src="{img}"{_extra_e} alt="" loading="eager" decoding="async">'
            if img else "")
    serie = (r.get("serie") or [])
    return (
        '<section class="dest">'
        f'<div class="dest-rot"><h2>{rot}</h2>'
        f'<span>{html.escape(marca)}</span></div>'
        f'<a class="dest-foto" href="{link}" target="_blank" rel="noopener">'
        f'{foto}</a>'
        '<div class="dest-info">'
        f'<span class="dest-off">{numero}</span>'
        f'<h3>{titulo}</h3>'
        f'{_preco_html(estrela, grande=True)}'
        f'{_faixa_svg(serie, 110, 26)}'
        f'<a class="dest-ir" href="{link}" target="_blank" rel="noopener">'
        'Ver na loja <span>&rarr;</span></a>'
        '</div>'
        + (f'<div class="dest-mini">{"".join(_card_grid(x) for x in apoio)}</div>'
           if apoio else "")
        + '</section>')


def _categorias_editorial(produtos: list) -> str:
    """Categorias como porta de entrada do tamanho de um título.

    ⚠️ CHIP NÃO É PORTA. Antes eram sete pílulas de 13px que filtravam a mesma
    grade — a pessoa nem via que existiam. Aqui cada categoria é uma linha do
    tamanho de um título, com a CONTAGEM REAL e a foto de um produto dela
    aparecendo por trás no hover.
    📌 A foto no hover não é enfeite: é a prova de que a porta leva a algum
    lugar. Categoria vazia não entra — porta que abre pro nada é pior que
    porta que não existe."""
    porcat = {}
    for p in produtos:
        porcat.setdefault(_inferir_categoria(p), []).append(p)
    linhas = []
    for cat in list(_CATEGORIAS_FIXAS) + ["Outros"]:
        itens = porcat.get(cat) or []
        if len(itens) < 3:
            continue
        # 📌 A capa da categoria prefere uma foto tratada: é ela que dá o tom
        # da seção inteira. Sem nenhuma, vale qualquer uma com foto.
        com_foto = (next((i for i in itens if _classe_foto(i) == "A"), None)
                    or next((i for i in itens if (i.get("imagem") or "").strip()), None))
        _sc, _ex = _foto(com_foto, "card", 640) if com_foto else ("", "")
        fundo = (f'<img class="cf" src="{html.escape(_sc)}"{_ex} '
                 f'alt="" loading="lazy">' if com_foto else "")
        linhas.append(
            f'<a class="cat-l" href="todos.html?c={html.escape(cat)}">'
            f'{fundo}<span class="cn">{html.escape(cat)}</span>'
            f'<span class="cq">{len(itens)} achados</span></a>')
    if not linhas:
        return ""
    return ('<section class="catg"><div class="catg-rot">Por onde você quer '
            'começar</div>' + "".join(linhas) + '</section>')


def _porta_catalogo(produtos: list) -> str:
    return (f'<a class="tudo" href="todos.html"><span><b>Ver todos os '
            f'{len(produtos)} achados</b>'
            f'<i>com busca, filtro por loja e histórico de preço</i></span>'
            f'<span class="seta">&rarr;</span></a>')


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
        '<p>Quando uma peça baixa de verdade, ela vai pro grupo na hora — '
        'com o link já pronto. É de graça e você sai quando quiser.</p>'
        f'<a class="cta" href="{html.escape(destino)}" target="_blank" '
        'rel="noopener">Entrar no grupo <span>&rarr;</span></a>'
        '</div>'
        f'{_feed_grupo()}'
        '</section>')


def _feed_grupo(quantos: int = 7) -> str:
    """O que saiu no grupo, rolando devagar ao lado do botão.

    ⚠️ O CTA ESTAVA MUDO (31/08). O Dre: "eu rolo a página e no final tem o CTA
    pro grupo, mas parado, me convença a clicar nesse botão". Nenhuma animação
    conserta isso — botão que pulsa continua sendo um botão que promete. O que
    convence é MOSTRAR O QUE ACONTECE DO OUTRO LADO.

    📌 Por isso o feed sai do `whatsapp_enviados.json`, que é o registro do que
    o robô REALMENTE mandou, e não da fila (que é intenção). Se o grupo ficar um
    dia parado, o feed fica parado junto — e é assim que tem que ser: prova que
    continua bonita quando o fato para de acontecer virou enfeite.

    Sem o arquivo, devolve vazio e a faixa volta a ser só texto e botão. Melhor
    faixa simples que faixa com um feed inventado."""
    import json as _json
    try:
        est = _json.loads((ARQ_ENVIADOS).read_text(encoding="utf-8"))
        mapa = est.get("enviados_em") or {}
    except Exception:
        return ""
    if not mapa:
        return ""
    # mais recentes primeiro; o nome vem da fila pelo link
    recentes = sorted(mapa.items(), key=lambda kv: -int(kv[1] or 0))[:quantos * 2]
    nomes = {}
    try:
        for it in _json.loads(JSON_FILA.read_text(encoding="utf-8")):
            if isinstance(it, dict) and it.get("link"):
                nomes[it["link"]] = (it.get("campeao") or it.get("produto") or "")
    except Exception:
        pass
    linhas = []
    for link, quando in recentes:
        nome = _titulo_legivel(nomes.get(link, ""), 42)
        if not nome:
            continue
        hora = time.strftime("%H:%M", time.localtime(int(quando or 0)))
        linhas.append(f'<li><i>{hora}</i><span>{html.escape(nome)}</span></li>')
        if len(linhas) >= quantos:
            break
    if len(linhas) < 3:
        return ""
    # duplicado pra emendar sem salto na volta do laço
    itens = "".join(linhas) * 2
    return (f'<div class="feed" aria-hidden="true">'
            f'<div class="feed-rot">último que foi pro grupo</div>'
            f'<div class="feed-jan"><ul class="feed-fita">{itens}</ul></div>'
            f'</div>')


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
             '<b>Esse a gente ainda não tem</b>'
             'Tenta outra busca — a curadoria entra todo dia.</p>')
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


# ── os dois corpos ────────────────────────────────────────────────────────
# ⚠️ A CASCA É UMA SÓ. Cabeça, CSS, header, drawer, rodapé e script vivem no
# `_TEMPLATE` e as duas páginas trocam só o `{{CORPO}}`. Duplicar o template
# seria garantir que um dia o tema claro funcionasse numa página e na outra
# não — é a mesma lição das duas travas, aplicada a HTML.
_CORPO_HOME = """
  {{ABRE}}
  {{DESTAQUE}}
  {{CATEGORIAS}}
  {{GRUPO_FAIXA}}
  {{PORTA}}

  <section class="rodape-prova">
    <p class="prova-linha">
      <b>{{TOTAL}}</b> achados no ar · preços conferidos em <b>{{DATA}}</b> ·
      <b>{{DIAS}}</b> dias de histórico de preço · link que morre sai sozinho
    </p>
    <div class="canais">
      <a class="ci" href="{{GRUPO_TOPO}}" target="_blank" rel="noopener">Grupo no WhatsApp</a>
      <a class="ci" href="{{INSTAGRAM}}" target="_blank" rel="noopener">Instagram</a>
      <a class="ci" href="{{TIKTOK}}" target="_blank" rel="noopener">TikTok</a>
      <a class="ci" href="{{YOUTUBE}}" target="_blank" rel="noopener">YouTube</a>
      <a class="ci" href="mailto:{{EMAIL}}">Fale com a gente</a>
    </div>
  </section>
"""

_CORPO_LEGAL = """
  <section class="cat-topo">
    <a class="voltar" href="index.html">&larr; voltar</a>
    <h1>Termos e privacidade</h1>
    <p>Atualizado em {{DATA}}. Vale para topshopoficial.com.br e para os canais
       de divulgação da TopShop.</p>
  </section>

  <section class="legal">
    <h2>Como a TopShop ganha dinheiro</h2>
    <p>A TopShop é uma <b>curadoria de produtos</b>. Nós não vendemos nada e não
       temos estoque. Os links desta página levam a lojas de terceiros —
       principalmente Shopee e Amazon — e nós recebemos uma <b>comissão de
       afiliado</b> quando alguém compra por esses links.</p>
    <p>Isso não muda o preço para você: o valor é o mesmo que a loja cobraria
       sem o nosso link. Também não influencia o que a gente mostra em primeiro
       lugar — a ordenação da vitrine é por queda de preço e desconto, não por
       comissão.</p>

    <h2>Sobre os preços</h2>
    <p>Os preços são lidos automaticamente da própria loja, todo dia, e ficam
       registrados para montar o histórico que você vê nos gráficos. Quando um
       produto tem leituras suficientes, mostramos a <b>média do período</b>, e
       não o preço de um instante — por isso o valor aparece com um til (~).</p>
    <p><b>Quem define o preço da compra é a loja</b>, no momento em que você
       finaliza o pedido. Preço de página envelhece; o nosso é informação sobre
       a tendência, não uma oferta.</p>

    <h2>Quais dados a gente coleta</h2>
    <p>Este site é uma página estática. <b>Não pedimos cadastro, não temos
       login e não guardamos os seus dados pessoais em servidor nenhum.</b></p>
    <ul>
      <li><b>No seu navegador:</b> guardamos apenas a sua preferência de tema
        (claro/escuro) e de visualização (grade/lista), com
        <code>localStorage</code>. Fica no seu aparelho, não chega até nós, e
        some quando você limpa os dados do site.</li>
      <li><b>Nos links de saída:</b> os links carregam etiquetas de origem
        (sub-IDs) que dizem à loja de qual canal veio o clique. Elas identificam
        <b>o canal</b>, nunca a pessoa.</li>
      <li><b>Nas lojas de destino:</b> a partir do clique, valem a política de
        privacidade e os cookies da Shopee, Amazon ou de quem for a loja. A
        gente não tem acesso ao que acontece lá.</li>
    </ul>

    <h2>Grupos de WhatsApp e Telegram</h2>
    <p>A entrada é voluntária e a saída também: você sai quando quiser, pelo
       próprio aplicativo. Nos grupos publicamos produtos com o link já pronto;
       não mandamos mensagem privada, não vendemos a lista de participantes e
       não repassamos números para ninguém.</p>

    <h2>Publicidade</h2>
    <p>Todo o conteúdo desta página e dos nossos canais é <b>conteúdo
       publicitário</b>, conforme o Código de Defesa do Consumidor e as regras
       do CONAR. Os vídeos e posts que levam até aqui também são.</p>

    <h2>Responsabilidade</h2>
    <p>Não somos responsáveis por entrega, garantia, defeito, troca ou
       devolução: essa relação é entre você e a loja onde a compra foi feita.
       Nossa parte é indicar o produto, conferir se o link está no ar e mostrar
       o que sabemos do preço.</p>

    <h2>Falar com a gente</h2>
    <p>Dúvida, correção de informação ou pedido para remover algo:
       <a href="mailto:{{EMAIL}}">{{EMAIL}}</a>. A gente responde.</p>
  </section>
"""


_CORPO_CATALOGO = """
  <section class="cat-topo">
    <a class="voltar" href="index.html">&larr; voltar</a>
    <h1>Todos os produtos</h1>
    <p>{{TOTAL}} produtos com preço conferido. Busque pelo nome, ou filtre
       por loja e categoria.</p>
  </section>

  <section id="produtos">
    {{VITRINE}}
  </section>
"""


_MARCA_ANTIGA = (
    '<a class="marca" href="index.html" aria-label="topshop">'
    '<span class="selo-marca" aria-hidden="true"><svg viewBox="0 0 100 100">'
    '<defs><path id="anel-t" d="M50,50 m-37,0 a37,37 0 1,1 74,0 a37,37 0 1,1 -74,0"/>'
    '</defs><g class="anel"><text><textPath href="#anel-t" startOffset="0%">'
    'topshop \u00b7 curadoria di\u00e1ria \u00b7 desde 2026 \u00b7 </textPath></text></g>'
    '<g transform="translate(50 50)">'
    '<path class="ts-mini" transform="translate(-11 -11)" '
    'd="M4 0h9.6L22 8.6V18a4 4 0 0 1-4 4H4a4 4 0 0 1-4-4V4a4 4 0 0 1 4-4Z"/>'
    '<path transform="translate(-11 -11)" fill="var(--bg)" '
    'd="M4.6 8.4h9.2v2.5h-3.3v7.4H7.9v-7.4H4.6z"/></g></svg></span>'
    '<span>top<i>shop</i></span></a>')


def _aninhar(svg: str, x: float, y: float, lado: float) -> str:
    """Encaixa um SVG inteiro dentro de outro, na caixa pedida.

    SVG aninhado escala pelo viewBox sozinho — não precisa recalcular
    transform, e é por isso que o s\u00edmbolo cabe no selo sem ninguém
    ajustar n\u00famero na m\u00e3o quando a proporção mudar."""
    vb = re.search(r'viewBox="([^"]+)"', svg)
    miolo = re.sub(r"^<svg[^>]*>|</svg>$", "", svg)
    miolo = re.sub(r"<title>.*?</title>", "", miolo, flags=re.S)
    return (f'<svg x="{x}" y="{y}" width="{lado}" height="{lado}" '
            f'viewBox="{vb.group(1)}" preserveAspectRatio="xMidYMid meet">'
            f"{miolo}</svg>")


_FAVICON_ANTIGO = (
    '<link rel="icon" href="data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A//'
    'www.w3.org/2000/svg%22%20viewBox%3D%220%200%2032%2032%22%3E%3Cpath%20d%3D'
    '%22M6%200h13.4L32%2012.6V26a6%206%200%200%201-6%206H6a6%206%200%200%201-6'
    '-6V6a6%206%200%200%201%206-6Z%22%20fill%3D%22%23C8385E%22/%3E%3Cpath%20d'
    '%3D%22M6.6%2012.4h13.2v3.5h-4.8v10.4h-3.6V15.9H6.6z%22%20fill%3D%22%23fff'
    '%22/%3E%3C/svg%3E">')


def _favicon() -> str:
    """A micro, virada em data-URI.

    ⚠️ O FAVICON FICOU PRA TRÁS DUAS TROCAS DE PALETA. Ele estava chumbado no
    HTML com o rosa neon #FF3D6E e o preto frio #0B0C0F — as duas cores que a
    marca já tinha aposentado — e ninguém viu porque favicon é o único elemento
    do site que a gente nunca olha de perto: ele mora na aba, com 16px.
    📌 Agora ele SAI da mesma fonte que as outras assinaturas. Não existe mais
    "atualizar o favicon" como tarefa separada; ele muda junto ou não muda.

    Cores fixas de propósito: a aba do navegador não enxerga as variáveis da
    página, então aqui não dá pra seguir tema — e é por isso que a micro tem
    fundo próprio, em vez de contar com o fundo de trás."""
    if not MICRO:
        return _FAVICON_ANTIGO
    uri = quote(MICRO, safe="")
    return (f'<link rel="icon" href="data:image/svg+xml,{uri}">'
            f'<link rel="apple-touch-icon" href="data:image/svg+xml,{uri}">')


def _cabecalho_marca() -> str:
    """A assinatura no topo: o selo girando com o s\u00edmbolo dentro, e o
    wordmark em curva ao lado.

    \u26a0\ufe0f O SELO GUARDAVA A LOGO VELHA. Ele continua girando — foi o Dre
    quem pediu e \u00e9 dele a decis\u00e3o de tirar — mas o quadradinho rosa com um
    T de dentro dele saiu: manter os dois seria ter duas marcas no mesmo
    cabe\u00e7alho, e a nova perde por estar menor.
    \U0001f4cc O nome ao lado deixou de ser TEXTO. Era `top<i>shop</i>` com a
    fonte do sistema; agora \u00e9 o contorno da Instrument Serif, id\u00eantico em
    qualquer m\u00e1quina. Wordmark que depende da fonte instalada n\u00e3o \u00e9 wordmark."""
    if not (_SVG_SIMBOLO and _SVG_WORDMARK):
        return _MARCA_ANTIGA
    selo = (
        '<span class="selo-marca" aria-hidden="true"><svg viewBox="0 0 100 100">'
        '<defs><path id="anel-t" d="M50,50 m-37,0 a37,37 0 1,1 74,0 a37,37 0 1,1 -74,0"/>'
        '</defs><g class="anel"><text><textPath href="#anel-t" startOffset="0%">'
        'topshop \u00b7 curadoria di\u00e1ria \u00b7 desde 2026 \u00b7 </textPath></text></g>'
        + _aninhar(_SVG_SIMBOLO, 34, 33, 32) + "</svg></span>")
    nome = ('<span class="marca-nome">'
            + re.sub(r"<title>.*?</title>", "", _SVG_WORDMARK, flags=re.S)
            + "</span>")
    return ('<a class="marca" href="index.html" aria-label="topshop">'
            + selo + nome + "</a>")


def _comuns(produtos: list, corpo: str, og: str) -> str:
    """Substituições que valem pras duas páginas."""
    total, lojas, off_medio = _metricas(produtos)
    grupo_topo = GRUPO_WHATSAPP or GRUPO_TELEGRAM or INSTAGRAM
    return _TEMPLATE.replace("{{CORPO}}", corpo)\
                    .replace("{{MARCA}}", _cabecalho_marca())\
                    .replace("{{FAVICON}}", _favicon())\
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


def gerar_site(produtos: list) -> str:
    """A HOME: escolhe, não lista.

    ⚠️ ATÉ 31/08 ESTA FUNÇÃO DESPEJAVA OS 300 PRODUTOS NUMA PÁGINA SÓ. O Dre:
    "não vamos colocar 1000 fotos na mesma página, ngm rola isso tudo, as
    pessoas pesquisam". Ele tem razão e o efeito era pior que o peso — uma
    página que repete a mesma célula 300 vezes SÓ PODE parecer template,
    porque repetição é a definição de template.
    📌 Home escolhe (um destaque, categorias, o convite); catálogo lista."""
    _corrigir_titulos(produtos)
    produtos = [p for p in produtos if _vale_mostrar(p)]
    og = (produtos[0].get("imagem", "") if produtos else "") or ""
    corpo = (_CORPO_HOME
             .replace("{{ABRE}}", _abre_html(produtos))
             .replace("{{DESTAQUE}}", _destaque_editorial(produtos))
             .replace("{{CATEGORIAS}}", _categorias_editorial(produtos))
             .replace("{{GRUPO_FAIXA}}", _grupo_faixa_html())
             .replace("{{PORTA}}", _porta_catalogo(produtos)))
    return _comuns(produtos, corpo, og)


def gerar_legal(produtos: list) -> str:
    """Termos e privacidade, como PÁGINA do site.

    ⚠️ PÁGINA E NÃO PDF, e a diferença importa. O Dre pediu PDF "pra deixar
    registrado" — e pra registro o PDF serve (é uma foto datada). Mas o
    documento que VALE é o que está no ar: é o que o consumidor consegue ler no
    celular, o que o Google indexa e o que um órgão de defesa consulta. PDF em
    site é anexo que ninguém abre.
    📌 Gerada pelo mesmo builder de propósito: assim ela herda tema, tipografia
    e cabeçalho, e não vira aquela página branca de Times New Roman que todo
    site tem — a página legal é onde a maioria das marcas desiste de ser
    marca."""
    return _comuns(produtos, _CORPO_LEGAL, "")


def gerar_catalogo(produtos: list) -> str:
    """A segunda página: a grade densa, com busca e filtro. É aqui que os 300
    moram — e aqui a repetição não é defeito, é a função."""
    _corrigir_titulos(produtos)
    antes = len(produtos)
    produtos = [p for p in produtos if _vale_mostrar(p)]
    if len(produtos) < antes:
        log.info(f"   🚧 {antes - len(produtos)} produto(s) sem foto e sem preço "
                 f"fora da vitrine (o link continua valendo na legenda)")
    og = (produtos[0].get("imagem", "") if produtos else "") or ""
    corpo = _CORPO_CATALOGO.replace("{{VITRINE}}", _vitrine_html(produtos))
    return _comuns(produtos, corpo, og)


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
<title>topshop — a gente encontra o que merece</title>
<meta name="description" content="Curadoria diária de objetos que valem o preço. A gente confere o valor todo dia e mostra o histórico antes de você comprar.">
<meta property="og:title" content="topshop — a gente encontra o que merece">
<meta property="og:description" content="Curadoria diária, com o preço conferido todo dia.">
<meta property="og:type" content="website">
<meta property="og:image" content="{{OGIMG}}">
<!-- pinta a barra do navegador no celular com o fundo da página:
     é o detalhe que faz o site parecer app em vez de aba -->
<meta name="theme-color" content="#F2EEE6">
<!-- o símbolo é o mesmo da marca, embutido: a assinatura precisa existir
     sem a palavra "topshop" pra virar ícone de app um dia -->
{{FAVICON}}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">
<style>
@font-face{font-family:'Arch';src:url('topshop-fonte.woff2') format('woff2');
  font-weight:100 900;font-stretch:62% 125%;font-display:swap}
/* ⚠️ A SERIF É A MAIOR MUDANÇA ISOLADA DE "ARTE" (31/08). O Dre mandou prints
   do ERA Residence e a diferença que salta não é cor nem animação: os títulos
   deles são SERIF DISPLAY em caixa alta, e os nossos eram a mesma sans do
   corpo, só maior. Tipo grande de sans é tipo grande; serif display é
   editorial — a mesma palavra passa a ter opinião.
   📌 `Instrument Serif` e não uma serif de sistema: Georgia e Times têm cara
   de documento, e é justamente disso que a gente está fugindo. Com
   `display=swap` o texto aparece na hora com a fonte de sistema e troca quando
   a nossa chega, então quem vem do Reels no 4G não espera nada. */

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
  /* ⚠️ "TÁ COM CLIMA DE VELÓRIO" — e tinha causa exata: #0B0C0F é um preto
     FRIO, azulado. O ERA Residence não usa preto; usa creme quente com
     marinho, e é por isso que as fotos dele parecem ensolaradas e as nossas
     pareciam necrotério.
     📌 Escuro não é o problema — TEMPERATURA é. O padrão agora é o claro
     creme (é onde as referências dele brilham), e o escuro virou quente:
     #14120F em vez de #0B0C0F, com o texto em creme e não em branco-azulado. */
  --bg:#F2EEE6; --sup:#FBF9F5; --sup2:#EAE5DA;
  --linha:rgba(26,35,56,.13); --linha2:rgba(26,35,56,.22);
  --ink:#1A2338; --muted:#6B6558;
  --marca:#C8385E; --marca-esc:#9E2748; --ok:#2F7D57;
  --r:14px; --topo:0px;
  --foto:#EAE5DA;
  --serif:'Instrument Serif','Iowan Old Style',Georgia,serif;
}

/* ══ TEMA CLARO ═══════════════════════════════════════════════════════════
   ⚠️ VEIO DAS REFERÊNCIAS, e é a técnica que aparece nas DUAS principais: o
   ERA Residence tem "by day / by night" e o Loop tem LIGHT/DARK/SYSTEM. Não é
   moda — é o sinal mais barato de "esse site foi feito por gente que pensa no
   usuário", porque respeita quem lê no sol e quem lê na cama.
   📌 Só os TOKENS mudam. Nenhuma regra de componente sabe que existe tema —
   se soubesse, cada card novo teria que ser pintado duas vezes e um dia alguém
   esqueceria metade. */
:root[data-tema="escuro"]{
  --bg:#14120F; --sup:#1D1A15; --sup2:#26221C;
  --linha:rgba(242,238,230,.10); --linha2:rgba(242,238,230,.18);
  --ink:#F2EEE6; --muted:#9A9184;
  --marca:#FF5C82; --marca-esc:#D43D63; --ok:#4FCB8E;
  --foto:#26221C;
}
:root[data-tema="escuro"] .topo,
:root[data-tema="escuro"] .topo.colado{background:rgba(20,18,15,.80)}
:root[data-tema="escuro"] .card{
  box-shadow:inset 0 1px 0 rgba(242,238,230,.06), 0 1px 2px rgba(0,0,0,.5)}
:root[data-tema="escuro"] .card:hover{
  box-shadow:inset 0 1px 0 rgba(242,238,230,.10), 0 20px 46px rgba(0,0,0,.6)}
:root[data-tema="escuro"] .selo{background:rgba(20,18,15,.78);
  border-color:rgba(242,238,230,.14)}
:root[data-tema="escuro"] .card .foto::before{
  background:linear-gradient(transparent,rgba(20,18,15,.5))}
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
/* ⚠️ ISTO AQUI ERA rgba(11,12,15,.72) — o preto FRIO do tema antigo, chumbado
   na regra base. Só o tema escuro tinha correção, então no tema claro a página
   era creme e a barra do topo era uma tira cinza-chumbo em cima dela. Passou
   despercebido porque as telas todas foram vistas no escuro. 📌 Sobra de
   paleta antiga não se descobre olhando o tema em que se trabalha. */
.topo{position:sticky;top:0;z-index:50;background:rgba(246,243,237,.78);
  backdrop-filter:blur(22px) saturate(150%);
  -webkit-backdrop-filter:blur(22px) saturate(150%);
  border-bottom:1px solid transparent;transition:border-color .25s}
.topo.colado{border-bottom-color:var(--linha)}
.barra{display:flex;align-items:center;gap:12px;height:86px}
.marca{display:flex;align-items:center;gap:11px;font-size:19px;font-weight:800;
  font-stretch:112%;letter-spacing:-.045em;white-space:nowrap;flex:none}
.marca i{font-style:normal;color:var(--marca)}
/* o wordmark é desenho, não texto: a altura manda e a largura acompanha. */
.marca-nome{display:block;flex:none;line-height:0}
.marca-nome svg{height:23px;width:auto;display:block;overflow:visible}
@media(max-width:700px){.marca-nome svg{height:19px}}
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
  /* o polegar precisa da busca inteira; a palavra "topshop" cabe no símbolo
     ⚠️ ERA `.marca span`, que também pegava o `<span class="selo-marca">` — ou
     seja, no celular a marca sumia INTEIRA, símbolo e nome. Especificidade
     (0,1,1) ganhava do `.selo-marca` (0,1,0) mesmo ele vindo depois. */
  .marca .marca-nome{display:none}
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
  box-shadow:0 1px 2px rgba(26,35,56,.07), 0 1px 1px rgba(26,35,56,.05);
  transform-style:preserve-3d;
  transition:opacity .4s,transform .32s cubic-bezier(.22,.7,.2,1),
    border-color .22s,background .22s,box-shadow .32s}
.card.esconde{display:none}
.js .card{opacity:0;transform:translateY(16px) scale(.985)}
.js .card.dentro{opacity:1;transform:none}
.card:hover{background:var(--sup);border-color:var(--marca);
  transform:translateY(-3px);
  box-shadow:0 18px 40px rgba(26,35,56,.16), 0 0 0 1px rgba(200,56,94,.16)}
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


/* ══════════════════════════════════════════════════════════════════════════
   HOME EDITORIAL
   ⚠️ O DIAGNÓSTICO QUE MUDOU TUDO (31/08). O Dre: "nosso site me incomoda por
   parecer padrão". Não era estética — era ARQUITETURA. Uma página que despeja
   300 cards SÓ PODE parecer template, porque a única coisa que ela consegue
   fazer é repetir a mesma célula 300 vezes.
   📌 O ERA Residence não é bonito por causa do CSS: é bonito porque cada tela
   tem um NÚMERO DIFERENTE de coisas, e por isso cada tela pode ter composição
   própria. A nossa tinha uma composição só, repetida — e repetição é a
   definição de template.
   E ele mesmo deu a saída: "não vamos colocar 1000 fotos na mesma página, ngm
   rola isso tudo, as pessoas pesquisam". Home escolhe; catálogo lista.
   ══════════════════════════════════════════════════════════════════════════ */

/* ── abertura: o TEXTO é o layout ────────────────────────────────────────
   Do ERA: "palavras enormes, espaço negativo, títulos quebrados
   deliberadamente. Não é texto colocado dentro do layout — o texto É o
   layout." Aqui a quebra em três linhas é escolhida, não consequência da
   largura da tela. */
.abre{padding:clamp(26px,6vw,86px) 0 clamp(20px,4vw,52px);
  display:grid;grid-template-columns:1fr auto;align-items:end;gap:24px}
/* flow-root: sem isto a margem de baixo da ÚLTIMA linha escapa do h1 por
   colapso e vai disputar com a margem do subtítulo — colapso pega o MAIOR dos
   dois, não a soma, então a folga da cedilha simplesmente não existia. */
.abre h1{font-size:clamp(46px,10.5vw,142px);font-weight:850;font-stretch:118%;
  line-height:.85;letter-spacing:-.055em;text-transform:none;display:flow-root}
.abre-t{min-width:0}
/* ⚠️ A CORTINA CORTAVA O TIL E A CEDILHA. `overflow:hidden` clipa na caixa de
   linha, e com line-height .82 o ~ do Ã fica ACIMA dela e o ¸ do Ç ABAIXO —
   defeito que só aparece quando a manchete tem acento, e a nossa passou a ter
   ("ATENÇÃO."). `overflow-clip-margin` alarga a janela sem mover a caixa; o
   `overflow:hidden` antes fica de reserva pra quem não entende `clip`.
   📌 .24em e não .16em: a cedilha desce .219em, medido na fonte real. O .16
   deixava o rabinho do Ç cortado — e trocar um defeito por outro é o que a
   primeira versão desta linha fez. */
.abre h1 span{display:block;overflow:hidden;overflow:clip;
  overflow-clip-margin:.24em}
/* a folga medida: a tinta que mais sobe usa .935em e a entrelinha dá .82em, e
   a linha de cima ainda desce .012em. .16em de respiro fecha a conta e sobra
   .033em — pouco, e é pra ser pouco: manchete de revista quase encosta. */
.abre h1 span.alta{margin-top:.16em}
/* embaixo é a cedilha (.214em) contra o subtítulo, que hoje começa .027em
   depois do fim da caixa. .13em separa os dois sem abrir buraco. */
.abre h1 span.baixa{margin-bottom:.13em}
.abre h1 b{display:block;font-weight:inherit}
.abre h1 em{font-style:normal;color:var(--marca)}
/* a cortina: cada linha sobe de dentro da própria caixa. É o "abrir a porta"
   que o Dre descreveu no ERA, em 520ms e sem segurar ninguém na tela.
   📌 145% e não 102%: a janela é .24em mais alta que a caixa, e a cortina tem
   que começar abaixo da JANELA, não da caixa — senão aparece uma tira do topo
   das letras antes da hora. */
.js .abre h1 b{transform:translateY(145%);
  transition:transform .72s cubic-bezier(.16,.84,.28,1)}
.js .abre h1 span:nth-child(2) b{transition-delay:.08s}
.js .abre h1 span:nth-child(3) b{transition-delay:.16s}
.abre.dentro h1 b{transform:none}
/* o segundo tempo: chega DEPOIS das três linhas, senão as duas frases disputam
   o mesmo instante e nenhuma é lida. */
.abre-sub{margin-top:clamp(14px,1.7vw,24px);max-width:26ch;
  font-size:clamp(15px,1.55vw,21px);line-height:1.35;letter-spacing:-.005em;
  color:var(--ink)}
.js .abre-sub{opacity:0;transform:translateY(14px);
  transition:opacity .7s .34s,transform .7s .34s cubic-bezier(.16,.84,.28,1)}
.abre.dentro .abre-sub{opacity:1;transform:none}
.abre-n{text-align:right;color:var(--muted);font-size:13.5px;line-height:1.6;
  padding-bottom:.6em;white-space:nowrap}
.abre-n b{display:block;color:var(--ink);font-size:clamp(26px,3.4vw,40px);
  font-weight:850;letter-spacing:-.04em;font-variant-numeric:tabular-nums;
  line-height:1}
@media(max-width:640px){
  .abre{grid-template-columns:1fr;align-items:start;gap:16px}
  .abre-n{text-align:left}
}

/* ── destaque: composição assimétrica, não [CARD][CARD][CARD] ────────────
   Do ERA: "visual grande aqui, texto deslocado ali, outra fotografia
   invadindo a composição". Grade de 12 colunas com os elementos em posições
   escolhidas — e os dois menores DESCEM, entrando no espaço do texto. */
.dest{display:grid;grid-template-columns:repeat(12,1fr);
  gap:clamp(12px,1.6vw,22px);align-items:start;
  padding-bottom:clamp(28px,5vw,64px)}
.dest-rot{grid-column:1/-1;display:flex;align-items:baseline;gap:12px;
  margin-bottom:6px}
.dest-rot h2{font-size:clamp(15px,1.8vw,19px);font-weight:750;
  letter-spacing:-.02em}
.dest-rot span{font-size:12px;color:var(--muted)}
.dest-foto{grid-column:1/8;border-radius:var(--r);overflow:hidden;
  background:var(--foto);aspect-ratio:4/3;position:relative;display:block;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.06), 0 18px 44px rgba(0,0,0,.42)}
/* ⚠️ A FOTO É MAIOR QUE A JANELA DE PROPÓSITO (112%). Parallax só funciona se
   houver folga pra deslocar: com a imagem do tamanho exato do quadro, mover
   1px já mostra o fundo da caixa. A folga é o que permite o movimento existir
   sem buraco. */
.dest-foto img{width:100%;height:112%;object-fit:cover;display:block;
  will-change:transform;
  transition:transform .7s cubic-bezier(.22,.7,.2,1)}
.dest-foto:hover img{transform:translate3d(0,var(--par,0px),0) scale(1.05)}
.dest-info{grid-column:8/13;padding-top:clamp(10px,3vw,42px)}
.dest-off{display:inline-block;font-size:clamp(30px,4.6vw,58px);font-weight:850;
  letter-spacing:-.05em;line-height:1;color:var(--marca)}
.dest-info h3{font-size:clamp(17px,2vw,23px);font-weight:600;line-height:1.28;
  margin:14px 0 12px;letter-spacing:-.015em}
.dest-info .pr b{font-size:clamp(26px,3.2vw,36px)}
.dest-info .faixa{width:110px;height:26px;margin-top:10px}
.dest-ir{display:inline-flex;align-items:center;gap:9px;margin-top:18px;
  border-bottom:1px solid var(--linha2);padding-bottom:5px;font-weight:700;
  font-size:14.5px;transition:border-color .25s,gap .25s}
.dest-ir:hover{border-color:var(--marca);gap:14px}
/* os dois menores invadem a coluna do texto, e é essa sobreposição que quebra
   a sensação de grade */
.dest-mini{grid-column:5/11;display:grid;grid-template-columns:1fr 1fr;
  gap:clamp(12px,1.6vw,22px);margin-top:clamp(-40px,-4vw,-14px);z-index:2}
@media(max-width:820px){
  .dest-foto{grid-column:1/-1;aspect-ratio:16/11}
  .dest-info{grid-column:1/-1;padding-top:4px}
  .dest-mini{grid-column:1/-1;margin-top:8px}
}

/* ── categorias: entrada tipográfica, não chip ───────────────────────────
   Do Loop: "em vez de 'aqui estão nossos trabalhos', existe 'COMO você quer
   explorar?'". Categoria vira porta de entrada do tamanho de um título, com a
   contagem real do lado — e a foto de um produto dela aparecendo por trás no
   hover, que é a prova de que a porta leva a algum lugar. */
.catg{padding:clamp(26px,5vw,64px) 0;border-top:1px solid var(--linha)}
.catg-rot{font-size:12px;font-weight:700;letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted);margin-bottom:18px}
.cat-l{position:relative;display:flex;align-items:center;justify-content:space-between;
  gap:20px;padding:clamp(14px,2vw,22px) 0;border-bottom:1px solid var(--linha);
  overflow:hidden;isolation:isolate}
.cat-l .cn{font-size:clamp(26px,4.6vw,52px);font-weight:850;letter-spacing:-.045em;
  line-height:1;transition:transform .38s cubic-bezier(.22,.7,.2,1),color .28s}
.cat-l .cq{font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums;
  white-space:nowrap;transition:color .28s}
.cat-l .cf{position:absolute;right:78px;top:50%;translate:0 -50%;z-index:-1;
  width:132px;height:88px;border-radius:10px;object-fit:cover;
  opacity:0;transform:scale(.9) rotate(-4deg);
  transition:opacity .38s,transform .5s cubic-bezier(.22,.7,.2,1)}
.cat-l:hover .cn{transform:translateX(14px);color:var(--marca)}
.cat-l:hover .cq{color:var(--ink)}
.cat-l:hover .cf{opacity:.9;transform:scale(1) rotate(-2deg)}
@media(max-width:600px){.cat-l .cf{display:none}}

/* ── porta pro catálogo ──────────────────────────────────────────────────*/
.tudo{display:flex;align-items:center;justify-content:space-between;gap:18px;
  margin:clamp(24px,4vw,44px) 0;padding:clamp(20px,3vw,30px) clamp(20px,3vw,32px);
  border:1px solid var(--linha2);border-radius:16px;background:var(--sup);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.05);
  transition:border-color .25s,background .25s,transform .25s}
.tudo:hover{border-color:var(--marca);background:var(--sup2);transform:translateY(-2px)}
.tudo b{font-size:clamp(17px,2.2vw,23px);font-weight:800;letter-spacing:-.025em}
.tudo i{font-style:normal;display:block;color:var(--muted);font-size:13.5px;
  margin-top:5px;font-weight:400}
.tudo .seta{font-size:22px;transition:transform .3s}
.tudo:hover .seta{transform:translateX(6px)}

/* ── topo do catálogo ────────────────────────────────────────────────────*/
.cat-topo{padding:clamp(18px,3vw,34px) 0 clamp(10px,1.6vw,18px)}
.cat-topo h1{font-size:clamp(28px,4.4vw,46px);font-weight:850;
  letter-spacing:-.04em;line-height:1}
.cat-topo p{color:var(--muted);font-size:14.5px;margin-top:10px}
.voltar{display:inline-flex;align-items:center;gap:7px;color:var(--muted);
  font-size:13.5px;font-weight:600;margin-bottom:14px;transition:color .2s}
.voltar:hover{color:var(--marca)}


/* ══ ELEMENTOS DE ARTE (ERA Residence, dos prints de 31/08) ═══════════════ */

/* ── títulos em serif display, caixa alta ───────────────────────────────
   No print 2 do ERA, "NEW GOLDEN MILE" ocupa meia tela em serif de caixa alta
   com marinho sobre creme. É a diferença entre "texto grande" e "tipografia":
   a mesma palavra passa a ter opinião. */
.abre h1,.dest-off,.cat-l .cn,.grupo-faixa h3,.cat-topo h1,h2{
  font-family:var(--serif);font-weight:400;font-stretch:normal}
.abre h1{font-size:clamp(52px,12.5vw,168px);line-height:.82;
  letter-spacing:-.02em;text-transform:uppercase}
.abre h1 em{color:var(--marca)}
.cat-l .cn{font-size:clamp(30px,5.4vw,64px);letter-spacing:-.01em;
  text-transform:uppercase}
.dest-off{font-size:clamp(38px,6vw,76px);letter-spacing:-.02em}
.grupo-faixa h3,.cat-topo h1{letter-spacing:-.01em}
.abertura h2,.dest-rot h2{font-family:var(--serif);font-weight:400;
  font-size:clamp(20px,2.6vw,28px);letter-spacing:0;text-transform:uppercase}

/* ── selo circular com o nome girando ───────────────────────────────────
   O ERA tem um selo com "ERA RESIDENCE" em círculo e um ornamento no meio,
   fixo no canto de toda tela. É o elemento que mais grita "isto é uma marca",
   e custa um SVG.
   ⚠️ 40s por volta, não 8: girar rápido vira spinner de carregamento, e
   spinner é a coisa mais barata que existe. Devagar, o olho lê como objeto. */
.selo-marca{position:relative;width:74px;height:74px;flex:none;display:block}
/* ⚠️ FILHO DIRETO. Sem o `>`, esta regra pega TAMBÉM o SVG aninhado do
   símbolo, e width:100% atropela o x/y/width que posicionam ele dentro do
   anel — o T saía transbordando por cima do texto do selo. */
.selo-marca > svg{width:100%;height:100%;display:block}
.selo-marca .anel{animation:gira-selo 40s linear infinite;transform-origin:50% 50%}
@keyframes gira-selo{to{transform:rotate(360deg)}}
.selo-marca text{font-family:var(--serif);font-size:8.4px;letter-spacing:.34em;
  fill:var(--ink);text-transform:uppercase}
.selo-marca .ts-mini{fill:var(--marca)}
@media(max-width:700px){.selo-marca{width:54px;height:54px}
  .selo-marca text{font-size:9.6px}}

/* ── coluna lateral: numeração e "role" na vertical ─────────────────────
   Nos quatro prints tem um número pequeno ("23", "31", "37") e a palavra
   SCROLL escrita na vertical, na margem esquerda. É detalhe de revista: não
   informa quase nada e diz tudo sobre quem fez. */
.margem{position:fixed;left:clamp(8px,1.6vw,20px);top:0;bottom:0;width:22px;
  z-index:30;pointer-events:none;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:16px;
  font-size:9.5px;letter-spacing:.24em;text-transform:uppercase;
  color:var(--muted);mix-blend-mode:difference;opacity:.9}
.margem span{writing-mode:vertical-rl;transform:rotate(180deg)}
.margem .num{font-family:var(--serif);font-size:13px;letter-spacing:0;
  writing-mode:horizontal-tb;transform:none;
  font-variant-numeric:tabular-nums}
.margem .risco{width:1px;height:clamp(28px,5vh,54px);background:currentColor;
  opacity:.4}
@media(max-width:900px){.margem{display:none}}

/* ── a foto invade o título ──────────────────────────────────────────────
   No print 2 a buganvília rosa passa POR CIMA de "NEW GOLDEN MILE". É o que
   quebra a sensação de caixas empilhadas — dois elementos ocupando o mesmo
   espaço, um na frente do outro.
   ⚠️ `pointer-events:none` porque ela cobre o título: sem isso, o clique na
   área da foto não chega no que está embaixo. */
.abre{position:relative;isolation:isolate}
.abre-foto{position:absolute;right:clamp(-10px,-1vw,0px);
  bottom:clamp(-18px,-2vw,-6px);width:clamp(180px,30vw,420px);z-index:2;
  pointer-events:none;filter:drop-shadow(0 22px 44px rgba(26,35,56,.28));
  opacity:0;transform:translateY(26px) rotate(3deg);
  transition:opacity .9s .25s,transform 1.1s .25s cubic-bezier(.16,.84,.28,1)}
.abre.dentro .abre-foto{opacity:1;transform:none}
.abre-foto img{width:100%;display:block;border-radius:12px}
@media(max-width:640px){.abre-foto{width:150px;bottom:-8px;opacity:.85}}


/* ── feed do grupo: prova, não enfeite ──────────────────────────────────
   ⚠️ ROLA SOZINHO PORQUE O CONTEÚDO É NOVIDADE, não porque movimento é
   bonito. É a diferença que a gente aprendeu no mural: mercadoria deslizando
   é vitrine, bolha deslizando é protetor de tela. Aqui desliza o que o robô
   mandou pro grupo, com a hora — e a hora é o que prova que não é maquete.
   Pausa no hover: quem quer ler precisa poder. */
.grupo-faixa{align-items:stretch}
.grupo-faixa .txt{display:flex;flex-direction:column;justify-content:center}
.feed{flex:none;width:min(320px,100%);border-left:1px solid var(--linha);
  padding-left:clamp(16px,2.4vw,26px);display:flex;flex-direction:column;gap:9px}
.feed-rot{font-size:10px;font-weight:700;letter-spacing:.16em;
  text-transform:uppercase;color:var(--muted);display:flex;align-items:center;gap:7px}
.feed-rot::before{content:"";width:6px;height:6px;border-radius:50%;
  background:var(--ok);box-shadow:0 0 0 0 currentColor;
  animation:pulso-vivo 2.4s ease-out infinite}
@keyframes pulso-vivo{
  0%{box-shadow:0 0 0 0 rgba(47,125,87,.5)}
  70%{box-shadow:0 0 0 8px rgba(47,125,87,0)}
  100%{box-shadow:0 0 0 0 rgba(47,125,87,0)}}
.feed-jan{height:132px;overflow:hidden;
  -webkit-mask-image:linear-gradient(transparent,#000 18%,#000 82%,transparent);
  mask-image:linear-gradient(transparent,#000 18%,#000 82%,transparent)}
.feed-fita{list-style:none;animation:sobe-feed 22s linear infinite}
.feed:hover .feed-fita{animation-play-state:paused}
@keyframes sobe-feed{to{transform:translateY(-50%)}}
.feed-fita li{display:flex;gap:10px;align-items:baseline;padding:5px 0;
  font-size:12.5px;line-height:1.35}
.feed-fita i{font-style:normal;color:var(--muted);font-variant-numeric:tabular-nums;
  font-size:11px;flex:none}
.feed-fita span{color:var(--ink);overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
@media(max-width:820px){
  .feed{width:100%;border-left:0;border-top:1px solid var(--linha);
    padding-left:0;padding-top:16px}
  .feed-jan{height:96px}
}
@media(prefers-reduced-motion:reduce){
  .feed-fita{animation:none}
  .feed-rot::before{animation:none}
}

/* ── revelação por seção: o conteúdo entra conforme você rola ────────────
   ⚠️ TODA a página estava parada — "eu rolo, rolo, e no final tem o CTA". As
   seções nasciam prontas e nada acontecia entre uma e outra. 14px e 520ms:
   o suficiente pra o olho registrar que algo chegou, pouco o bastante pra
   ninguém esperar por isso. */
.js main > section,.js main > a.tudo{opacity:0;transform:translateY(18px);
  transition:opacity .6s cubic-bezier(.22,.7,.2,1),
             transform .6s cubic-bezier(.22,.7,.2,1)}
.js main > section.dentro,.js main > a.tudo.dentro{opacity:1;transform:none}
.js .abre{opacity:1;transform:none}   /* a abertura tem cortina própria */
@media(prefers-reduced-motion:reduce){
  .js main > section,.js main > a.tudo{opacity:1;transform:none}
}

/* ── página legal: leitura longa, não vitrine ───────────────────────────
   Medida de linha curta (68ch) porque texto jurídico já é difícil sem a linha
   atravessando a tela inteira. */
.legal{max-width:68ch;padding-bottom:clamp(40px,6vw,80px)}
.legal h2{font-family:var(--serif);font-weight:400;
  font-size:clamp(21px,2.6vw,29px);letter-spacing:-.01em;
  margin:clamp(28px,4vw,44px) 0 12px}
.legal h2:first-child{margin-top:0}
.legal p{color:var(--muted);font-size:15px;line-height:1.72;margin-bottom:13px}
.legal p b{color:var(--ink);font-weight:650}
.legal ul{margin:6px 0 16px 20px;color:var(--muted);font-size:15px;
  line-height:1.72}
.legal li{margin-bottom:9px}
.legal li b{color:var(--ink);font-weight:650}
.legal code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:.9em;background:var(--sup2);padding:1px 6px;border-radius:5px}
.legal a{color:var(--marca);border-bottom:1px solid currentColor}

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
.topo.colado{background:rgba(246,243,237,.82);
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
    {{MARCA}}
    <label class="buscabox">
      <input id="busca" type="search" placeholder="Buscar um produto"
             autocomplete="off" aria-label="Buscar produto">
      <svg class="lupa" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/></svg>
    </label>
    <button class="tema" id="tema" type="button" aria-label="Trocar entre claro e escuro">☾</button>
    <a class="zap" href="{{GRUPO_TOPO}}" target="_blank" rel="noopener">Grupo</a>
  </div>
</div>

<!-- ⚠️ A MARGEM É PURO DETALHE DE REVISTA, e é de propósito. Nos quatro
     prints do ERA tem um número pequeno e a palavra SCROLL na vertical, na
     borda esquerda. Não informa quase nada e diz tudo sobre quem fez o site.
     `mix-blend-mode:difference` pra ela funcionar sobre foto clara ou escura
     sem precisar saber o que tem atrás. -->
<div class="margem" aria-hidden="true">
  <span>role</span>
  <div class="risco"></div>
  <div class="num" id="margem-num">01</div>
</div>

<main class="wrap">
{{CORPO}}
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
    &middot; atualizado em {{DATA}} &middot;
    <a href="termos.html">termos e privacidade</a></span>
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
   o mesmo gesto pro mouse, e solta com velocidade decrescente.

   ⚠️ ESTE ARRASTO MATOU O FILTRO DE CATEGORIA (01/09) — o Dre: "clico em todos
   ou qualquer coisa e simplesmente não muda". A versão anterior marcava
   `.arrastando` já no `pointerdown`, e `.arrastando .chip{pointer-events:none}`
   tirava o chip do teste de acerto no meio do próprio clique:

       pointerdown -> chip            mouseup -> .fita-rolo
       mousedown   -> chip            click   -> .fita-rolo   (closest('.chip') = null)

   O clique existia, chegava na fita e morria ali. 📌 SEGURAR O BOTÃO NÃO É
   ARRASTAR: arrasto é movimento, e só vira arrasto depois de 5px. É o mesmo
   erro do minerador — tratar uma suposição ("está apertado, deve querer
   arrastar") como se fosse fato ("andou 5px"). */
document.querySelectorAll('.fita-rolo').forEach(function(f){
  var baixo = false, andou = false, x0 = 0, e0 = 0, v = 0, ultimo = 0, quadro;
  f.addEventListener('pointerdown', function(e){
    if (e.pointerType === 'touch' || e.button !== 0) return;  /* o celular já sabe */
    baixo = true; andou = false;
    x0 = e.clientX; e0 = f.scrollLeft; v = 0; ultimo = e.clientX;
    cancelAnimationFrame(quadro);
  });
  addEventListener('pointermove', function(e){
    if (!baixo) return;
    if (!andou){
      if (Math.abs(e.clientX - x0) < 5) return;   /* ainda é um clique parado */
      andou = true; f.classList.add('arrastando');
    }
    f.scrollLeft = e0 - (e.clientX - x0);
    v = e.clientX - ultimo; ultimo = e.clientX;
  });
  addEventListener('pointerup', function(){
    if (!baixo) return;
    baixo = false;
    if (!andou) return;              /* clique puro: nada a frear, nada a engolir */
    f.classList.remove('arrastando');
    /* soltar em cima de um chip depois de arrastar não pode filtrar: o clique
       que vem a seguir é resíduo do gesto. Engolido na captura, e o listener
       sai no próximo tique — o click chega antes, na mesma tarefa. */
    var engole = function(ev){ ev.stopPropagation(); ev.preventDefault(); };
    f.addEventListener('click', engole, true);
    setTimeout(function(){ f.removeEventListener('click', engole, true); }, 0);
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



/* ══ PARALLAX DA FOTO DO DESTAQUE ════════════════════════════════════════
   ⚠️ MOVIMENTO COM REFERENTE, que é a linha que a gente traçou lá atrás: a
   imagem responde AO SEU GESTO, não a um cronômetro. Bolha girando sozinha é
   protetor de tela; foto que acompanha a rolagem é profundidade.

   ⚠️ E É SÓ NO DESKTOP. No celular o parallax de scroll engasga (o navegador
   já está ocupado compondo a rolagem) e a gente perde mais do que ganha — é a
   mesma decisão que o site antigo tinha tomado e estava certa. O tráfego daqui
   vem quase todo do Reels, então travar no celular custaria justamente onde
   dói.

   📌 12% de deslocamento, não 40%: parallax forte descola a imagem do card e
   vira efeito. Nesta faixa o olho não vê "parallax", vê que a foto tem
   profundidade. */
(function(){
  var foto = document.querySelector('.dest-foto');
  if (!foto || calmo || !fino || !matchMedia('(min-width:900px)').matches) return;
  var img = foto.querySelector('img');
  if (!img) return;
  var pedido = false;
  function medir(){
    var r = foto.getBoundingClientRect();
    if (r.bottom < 0 || r.top > innerHeight) { pedido = false; return; }
    /* -1 (entrando por baixo) → +1 (saindo por cima) */
    var meio = (r.top + r.height / 2 - innerHeight / 2) / (innerHeight / 2);
    img.style.setProperty('--par', (-meio * r.height * 0.055).toFixed(1) + 'px');
    img.style.transform = 'translate3d(0,' +
      (-meio * r.height * 0.055).toFixed(1) + 'px,0)';
    pedido = false;
  }
  addEventListener('scroll', function(){
    if (pedido) return;
    pedido = true; requestAnimationFrame(medir);
  }, {passive:true});
  medir();
})();
/* ══ SEÇÕES ENTRANDO NO SCROLL ═══════════════════════════════════════════
   Uma por vez, quando chega perto. `unobserve` depois de revelar: seção que
   re-anima ao subir a página vira enjoo, e a pessoa que volta pra reler não
   quer ver o texto sumir e voltar. */
(function(){
  var alvos = [].slice.call(
    document.querySelectorAll('main > section, main > a.tudo'));
  if (!alvos.length) return;
  if (calmo) { alvos.forEach(function(x){ x.classList.add('dentro'); }); return; }
  var obs = new IntersectionObserver(function(ents){
    ents.forEach(function(en){
      if (!en.isIntersecting) return;
      en.target.classList.add('dentro');
      obs.unobserve(en.target);
    });
  }, {rootMargin: '0px 0px -12% 0px'});
  alvos.forEach(function(x){ obs.observe(x); });
})();
/* ══ NÚMERO DA MARGEM ════════════════════════════════════════════════════
   No ERA o número da lateral muda conforme a seção — 23, 31, 37. Não é
   contador de nada: é paginação de revista, e serve pra dizer "você está em
   algum lugar de uma coisa maior". Aqui ele conta as seções de verdade. */
(function(){
  var alvo = document.getElementById('margem-num');
  if (!alvo) return;
  var secoes = [].slice.call(document.querySelectorAll('main > section, main > a.tudo'));
  if (!secoes.length) return;
  var obs = new IntersectionObserver(function(ents){
    ents.forEach(function(en){
      if (!en.isIntersecting) return;
      var i = secoes.indexOf(en.target) + 1;
      alvo.textContent = (i < 10 ? '0' : '') + i;
    });
  }, {rootMargin: '-45% 0px -45% 0px'});
  secoes.forEach(function(x){ obs.observe(x); });
})();

/* o tema começa no CREME e o botão diz pra onde vai */
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
  /* ⚠️ O CREME É O PADRÃO AGORA. Era o escuro, e o Dre resumiu em uma frase:
     "tá com clima de velório". As referências que ele mandou brilham no claro
     — o ERA usa creme com marinho, não preto. Quem prefere escuro clica uma
     vez e a escolha fica; quem tem o celular em modo escuro também recebe o
     escuro. Mudou só quem NÃO tem preferência nenhuma: recebia luto, agora
     recebe luz. */
  var escuro = guardado ? guardado === 'escuro'
             : matchMedia('(prefers-color-scheme: dark)').matches;
  function pintar(){
    raiz.setAttribute('data-tema', escuro ? 'escuro' : 'claro');
    if (bt) bt.textContent = escuro ? '☀' : '☾';
    var m = document.querySelector('meta[name=theme-color]');
    if (m) m.setAttribute('content', escuro ? '#14120F' : '#F2EEE6');
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
/* ══ CORTINA DA ABERTURA ═════════════════════════════════════════════════
   As três linhas do título sobem de dentro da própria caixa, escalonadas em
   80ms. É o "abrir a porta" que o Dre descreveu no ERA Residence — mas em
   520ms e SEM segurar ninguém numa tela de loading: quem chega do Reels não
   veio assistir a uma abertura, veio procurar um produto.
   📌 A diferença entre atmosfera e pedágio é quem manda no relógio. */
(function(){
  var a = document.getElementById('abre');
  if (!a) return;
  if (calmo) { a.classList.add('dentro'); return; }
  requestAnimationFrame(function(){
    requestAnimationFrame(function(){ a.classList.add('dentro'); });
  });
})();

/* ══ CLICAR NA MARCA ESTANDO NA HOME ═════════════════════════════════════
   ⚠️ O Dre: "toda vez que clico no selo a página reseta". Ela recarregava
   MESMO — o link é href="index.html" e o navegador obedece, mesmo quando você
   já está no index. Recarregar a página em que você já está não é navegação, é
   perder a rolagem e o estado por nada.
   📌 Na home o clique vira "voltar ao topo"; nas outras páginas continua sendo
   link de verdade. E respeita ctrl/cmd/shift e o botão do meio: quem quer abrir
   noutra aba tem que conseguir. */
(function(){
  var a = document.querySelector('a.marca');
  if (!a) return;
  var aqui = location.pathname.replace(/\/$/, '/index.html');
  if (!/index\.html$/.test(aqui)) return;
  a.addEventListener('click', function(e){
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    scrollTo({top: 0, behavior: calmo ? 'auto' : 'smooth'});
    /* ⚠️ ROLAGEM SUAVE É CANCELÁVEL. O navegador aborta a animação se o layout
       mudar no meio — e com foto carregando, o layout MUDA. O sintoma é a
       página parar no meio do caminho, e ele é intermitente por natureza:
       depende de a imagem chegar durante a animação. 📌 Quem descobriu foi um
       teste que falhava 1 em 2 — flaky ali não era teste ruim, era o defeito
       aparecendo na frequência dele. Aqui a saída não é confiar: é OLHAR se a
       rolagem parou de andar, e terminar na mão se parou longe do topo. */
    var ultimo = scrollY, parado = 0;
    (function conferir(){
      if (scrollY === 0) return;
      parado = (scrollY === ultimo) ? parado + 1 : 0;
      ultimo = scrollY;
      if (parado > 12) { scrollTo(0, 0); return; }   /* ~200ms sem andar */
      requestAnimationFrame(conferir);
    })();
  });
})();

/* ══ CATEGORIA VINDA DA HOME ═════════════════════════════════════════════
   A home manda `todos.html?c=Casa`. Sem isto o link levaria pro catálogo
   inteiro e a pessoa teria que filtrar de novo — uma porta que não abre onde
   diz que abre. */
(function(){
  var m = location.search.match(/[?&]c=([^&]+)/);
  if (!m || typeof aplicar !== 'function') return;
  var alvo = decodeURIComponent(m[1]);
  var b = document.querySelector('.chip[data-filtro="' + CSS.escape(alvo) + '"]');
  if (!b) return;
  document.querySelectorAll('.chip').forEach(function(o){
    o.setAttribute('aria-pressed', String(o === b)); });
  st.cat = alvo; aplicar();
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
    html_final = gerar_site(list(produtos))

    saida = Path(args.saida) if args.saida else SAIDA_HTML
    saida.parent.mkdir(parents=True, exist_ok=True)
    with open(saida, "w", encoding="utf-8") as f:
        f.write(html_final)
    # ⚠️ DUAS PÁGINAS, E A SEGUNDA NÃO É OPCIONAL: a home tem um botão "ver
    # todos" apontando pra `todos.html`. Gerar só a primeira publica um link
    # quebrado no lugar mais clicado da página.
    catalogo = saida.parent / "todos.html"
    catalogo.write_text(gerar_catalogo(list(produtos)), encoding="utf-8")
    log.info(f"✅ Catálogo gerado: {catalogo}")
    legal = saida.parent / "termos.html"
    legal.write_text(gerar_legal(list(produtos)), encoding="utf-8")
    log.info(f"✅ Termos gerados: {legal}")
    log.info(f"✅ Site gerado: {saida} ({len(produtos)} produtos, {len(html_final)//1024}KB)")
    print(f"\n🌐 Site pronto: {saida}\n   Sobe no GitHub Pages e aponta tua bio pra ele!")

    if args.abrir:
        import webbrowser
        webbrowser.open(f"file://{saida.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())