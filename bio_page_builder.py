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
    return f"""
      <a class="card" href="{link}" target="_blank" rel="noopener"
         data-busca="{titulo.lower()} {nome.lower()}" data-categoria="{cat}"
         data-plataforma="{plat}">
        {_foto_html(p, titulo, novo)}
        <div class="corpo">
          <h3>{titulo}</h3>
          {_preco_html(p)}
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


def _mural_html(produtos: list) -> str:
    """O mural do topo: três colunas de produto DERIVANDO devagar.

    ⚠️ ESTE É O MOVIMENTO QUE VOLTOU, E ELE É O OPOSTO DO QUE SAIU (31/08). A
    versão anterior tinha bolhas desfocadas girando atrás do texto: movimento
    ambiente, sem referente, que não informa nada — a assinatura de página
    gerada. Aqui o que se move É O CATÁLOGO. A mesma técnica (transform
    infinito) muda de significado quando o que desliza é a mercadoria: vira
    vitrine de rua, não protetor de tela.

    📌 `aria-hidden` + `pointer-events:none` de propósito. Estes cards repetem
    produto que já está na grade logo abaixo; se fossem clicáveis, o mesmo link
    apareceria duas vezes na página — dobrando o link no HTML (ruim pro Google)
    e partindo a métrica de clique em dois lugares. Quem quer clicar rola 300px
    e acha o card de verdade, com preço e botão.

    Só produto COM foto entra: card sem imagem no mural vira retângulo cinza
    deslizando, que é exatamente a cara de placeholder que a gente quer evitar.
    """
    com_foto = [p for p in produtos if (p.get("imagem") or "").strip()][:18]
    if len(com_foto) < 6:
        return ""          # mural ralo é pior que mural nenhum
    colunas, n = [], len(com_foto)
    for c in range(3):
        fatia = com_foto[c * n // 3:(c + 1) * n // 3]
        if not fatia:
            continue
        tijolos = "".join(
            f'<i style="background-image:url(\'{html.escape(p["imagem"])}\')"></i>'
            for p in fatia)
        # duplicado pra emendar sem salto: a animação anda 50% e reinicia
        colunas.append(
            f'<div class="mcol" style="--dur:{34 + c * 6}s">'
            f'<div class="mfita">{tijolos}{tijolos}</div></div>')
    return ('<div class="mural" aria-hidden="true">' + "".join(colunas)
            + '<span class="mfade"></span></div>')


def _vitrine_html(produtos: list) -> str:
    """Controles + grade. Os cards vêm prontos do servidor (aparecem no Google
    e funcionam sem JS); o JS só mostra e esconde na hora de filtrar."""
    if not produtos:
        return ('<p class="vazio"><b>Em breve, novos achados</b>'
                'A vitrine enche toda semana.</p>')
    controles = ('<div class="controles">' + _toggle_plataforma_html(produtos)
                 + _filtros_html(produtos) + "</div>")
    cards = "\n".join(_card_grid(p, novo=(i < 3))
                      for i, p in enumerate(produtos))
    grade = f'<div class="grade" id="grade-prod">{cards}</div>'
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
                    .replace("{{MURAL}}", _mural_html(produtos))\
                    .replace("{{GRUPOS}}", _grupos_html())\
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
}
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

/* ══ TOPO: marca + busca, tudo num bloco que gruda ════════════════════════
   Dois `position:sticky` empilhados exigem saber a altura do primeiro pra
   posicionar o segundo — e essa altura muda quando o teclado do celular abre.
   Um bloco só não tem esse problema. */
.topo{position:sticky;top:0;z-index:50;background:var(--bg);
  transition:box-shadow .25s,padding .22s}
.topo.colado{box-shadow:0 1px 0 var(--linha),0 12px 32px rgba(0,0,0,.5)}
.barra{display:flex;align-items:center;justify-content:space-between;gap:14px;
  padding-block:14px 10px;transition:padding .22s}
.topo.colado .barra{padding-block:9px 6px}
.marca{font-size:20px;font-weight:800;font-stretch:112%;letter-spacing:-.045em;
  white-space:nowrap;display:flex;align-items:center}
.marca i{font-style:normal;color:var(--marca)}
.zap{border:1px solid var(--linha2);color:var(--ink);font-weight:650;font-size:13.5px;
  padding:9px 16px;border-radius:999px;white-space:nowrap;
  transition:background .22s,border-color .22s}
.zap:hover{background:var(--sup2);border-color:var(--marca)}

/* a busca é o elemento mais gordo da página, de propósito: é o que a pessoa
   que veio do Reels precisa em primeiro lugar */
.buscabox{position:relative;padding-bottom:12px;transition:padding .22s}
.topo.colado .buscabox{padding-bottom:9px}
.buscabox input{width:100%;height:58px;background:var(--sup);
  border:1px solid var(--linha2);color:var(--ink);border-radius:13px;
  padding:0 52px 0 50px;font:inherit;font-size:16.5px;font-weight:500;
  transition:height .22s,font-size .22s,border-color .2s,background .2s}
.topo.colado .buscabox input{height:46px;font-size:15px}
.buscabox input::placeholder{color:var(--muted);font-weight:400}
.buscabox input::-webkit-search-cancel-button{filter:invert(.6)}
.buscabox input:focus{outline:none;border-color:var(--marca);background:var(--sup2)}
.buscabox .lupa{position:absolute;left:18px;top:29px;transform:translateY(-50%);
  width:19px;height:19px;stroke:var(--muted);fill:none;stroke-width:2;
  stroke-linecap:round;transition:stroke .2s,top .22s;pointer-events:none}
.topo.colado .buscabox .lupa{top:23px}
.buscabox input:focus~.lupa{stroke:var(--marca)}
.atalho{position:absolute;right:16px;top:29px;transform:translateY(-50%);font-size:11px;
  color:var(--muted);border:1px solid var(--linha);border-radius:6px;padding:2px 7px;
  pointer-events:none;transition:top .22s}
.topo.colado .atalho{top:23px}
@media(max-width:700px){.atalho{display:none}}

/* frase de posicionamento: some ao grudar, pra devolver a altura ao produto */
.frase{color:var(--muted);font-size:14px;padding-bottom:12px;
  max-height:44px;overflow:hidden;
  transition:max-height .25s,opacity .2s,padding .25s}
.frase b{color:var(--ink);font-weight:650}
.topo.colado .frase{max-height:0;opacity:0;padding-bottom:0}

/* ══ CONTROLES: categorias e lojas em fita ════════════════════════════════ */
.controles{display:flex;flex-direction:column;gap:9px;padding-bottom:14px}
.fita-rolo{display:flex;gap:7px;overflow-x:auto;scrollbar-width:none;
  margin-inline:calc(-1 * clamp(14px,3.2vw,28px));
  padding-inline:clamp(14px,3.2vw,28px);scroll-snap-type:x proximity}
.fita-rolo::-webkit-scrollbar{display:none}
.chip{flex:none;border:1px solid var(--linha2);background:transparent;color:var(--muted);
  font:inherit;font-size:13.5px;font-weight:600;padding:9px 15px;border-radius:999px;
  cursor:pointer;scroll-snap-align:start;
  transition:color .18s,border-color .18s,background .18s}
.chip:hover{color:var(--ink);border-color:var(--linha2);background:var(--sup)}
.chip[aria-pressed="true"]{background:var(--marca);color:#fff;border-color:var(--marca)}
.loja{flex:none;border:1px solid transparent;background:var(--sup);color:var(--muted);
  font:inherit;font-size:13px;font-weight:650;padding:8px 14px;border-radius:999px;
  cursor:pointer;scroll-snap-align:start;
  transition:color .18s,background .18s,border-color .18s}
.loja[aria-selected="true"]{color:var(--ink);background:var(--sup2);
  border-color:var(--linha2)}
.loja .n{opacity:.6;margin-left:6px;font-variant-numeric:tabular-nums;font-style:normal}
.loja:disabled{opacity:.34;cursor:not-allowed}

/* ══ GRADE: densa, card premium ═══════════════════════════════════════════ */
.grade{display:grid;gap:clamp(9px,1.2vw,14px);
  grid-template-columns:repeat(auto-fill,minmax(196px,1fr))}
.card{background:var(--sup);border:1px solid var(--linha);border-radius:var(--r);
  overflow:hidden;display:flex;flex-direction:column;position:relative;
  transition:opacity .4s,transform .22s,border-color .22s,background .22s}
.card.esconde{display:none}
.js .card{opacity:0;transform:translateY(12px)}
.js .card.dentro{opacity:1;transform:none}
.card:hover{border-color:var(--linha2);background:var(--sup2);transform:translateY(-3px)}
.card .foto{aspect-ratio:1;position:relative;overflow:hidden;background:#F4F5F7}
.card .foto img{width:100%;height:100%;object-fit:cover;display:block;opacity:0;
  transition:opacity .35s,transform .35s}
.card .foto img.ok{opacity:1}
.card:hover .foto img.ok{transform:scale(1.04)}
.card .foto .fb{position:absolute;inset:0;display:none;place-items:center;font-size:42px;
  font-style:normal}
.card .foto.sem-foto{background:var(--sup2)}
.card .foto.sem-foto .fb{display:grid}
.card .foto.carregando{background-image:linear-gradient(100deg,
  #EDEEF1 42%,#F8F9FA 50%,#EDEEF1 58%);background-size:280% 100%;
  animation:esqueleto 1.2s linear infinite}
@keyframes esqueleto{from{background-position:160% 0}to{background-position:-60% 0}}
.selo{position:absolute;top:8px;left:8px;font-size:10.5px;font-weight:750;
  padding:4px 8px;border-radius:7px;letter-spacing:.02em;
  background:rgba(11,12,15,.82);backdrop-filter:blur(6px);
  border:1px solid var(--linha);color:var(--ink);z-index:2}
.selo.novo{background:rgba(11,12,15,.82);color:var(--ink);border-color:var(--linha2)}
/* ⚠️ o desconto é o único selo COLORIDO: é o número que decide o clique */
.selo.off{background:var(--marca);color:#fff;border-color:transparent;left:auto;right:8px}
.selo.plat{top:auto;bottom:8px}
.card .corpo{padding:11px 12px 13px;display:flex;flex-direction:column;gap:8px;flex:1}
.card h3{font-size:13.5px;font-weight:500;line-height:1.35;color:var(--ink);
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card .ver{display:flex;align-items:center;justify-content:center;gap:6px;
  background:var(--sup2);border:1px solid var(--linha2);border-radius:10px;
  padding:11px;font-size:13px;font-weight:700;margin-top:auto;min-height:44px;
  transition:background .2s,border-color .2s}
.card:hover .ver{background:var(--marca);border-color:var(--marca);color:#fff}

.pr{display:flex;align-items:baseline;gap:7px;flex-wrap:wrap}
.pr b,.pr s{white-space:nowrap}
.pr b{font-size:20px;font-weight:800;letter-spacing:-.03em;
  font-variant-numeric:tabular-nums}
.pr b i{font-style:normal;font-weight:600;font-size:.62em;margin-right:2px;
  position:relative;top:-.1em;color:var(--muted)}
.pr s{color:var(--muted);font-size:12px}
.afer{font-size:10.5px;color:var(--muted);margin-top:-3px;line-height:1.35}
.afer.caindo{color:var(--ok)}

.vazio{text-align:center;padding:56px 20px;color:var(--muted)}
.vazio b{display:block;color:var(--ink);font-size:19px;margin-bottom:7px;font-weight:700}

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
.passos,.provas{display:grid;
  grid-template-columns:repeat(auto-fit,minmax(250px,1fr));
  gap:clamp(10px,1.4vw,16px);margin-top:28px}
.passo,.prova{padding:22px 20px 24px;border-radius:var(--r);
  border:1px solid var(--linha);background:var(--sup);
  transition:border-color .22s,background .22s}
.passo:hover,.prova:hover{border-color:var(--linha2);background:var(--sup2)}
.passo .num{display:grid;place-items:center;width:30px;height:30px;border-radius:9px;
  background:var(--sup2);border:1px solid var(--linha2);color:var(--ink);
  font-weight:800;font-size:14px;margin-bottom:14px}
.passo h3{font-size:16px;font-weight:700;margin-bottom:7px;letter-spacing:-.01em}
.passo p,.prova p{color:var(--muted);font-size:13.5px;line-height:1.55}
.prova b{display:block;font-size:clamp(30px,4vw,40px);font-weight:800;
  letter-spacing:-.04em;line-height:1;color:var(--ink);
  font-variant-numeric:tabular-nums}
.prova h3{font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  color:var(--muted);margin:9px 0 9px}
.contato{display:grid;grid-template-columns:1fr 1fr;gap:clamp(20px,4vw,48px);
  align-items:start}
@media(max-width:820px){.contato{grid-template-columns:1fr}}
.cis{display:flex;flex-direction:column;gap:8px;margin-top:8px}
.ci{display:flex;align-items:center;gap:12px;padding:14px 16px;border-radius:12px;
  border:1px solid var(--linha);background:var(--sup);min-height:44px;
  transition:border-color .2s,background .2s}
.ci:hover{border-color:var(--linha2);background:var(--sup2)}
.ci .ico{font-size:18px;flex:none}
.ci span{display:flex;flex-direction:column;font-size:14px;font-weight:600}
.ci span i{font-style:normal;font-size:12.5px;color:var(--muted);font-weight:400;margin-top:2px}

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
  .buscabox input{height:52px;font-size:16px}   /* 16px = iOS não dá zoom */
  .buscabox .lupa,.atalho{top:26px}
  .topo.colado .buscabox input{height:44px;font-size:16px}
  .topo.colado .buscabox .lupa{top:22px}
  .zap{font-size:12.5px;padding:8px 13px}
  .frase{font-size:13px}
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

/* ── capa: o texto de um lado, o CATÁLOGO derivando do outro ────────────── */
.capa{display:grid;grid-template-columns:1.02fr .98fr;gap:clamp(20px,4vw,54px);
  align-items:center;padding:clamp(18px,3vw,44px) 0 clamp(16px,2.4vw,30px)}
.olho{display:inline-flex;align-items:center;gap:8px;font-size:11.5px;font-weight:700;
  letter-spacing:.15em;text-transform:uppercase;color:var(--muted);margin-bottom:15px}
.olho::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--marca)}
.capa h1{font-size:clamp(30px,4.6vw,52px);font-weight:800;font-stretch:110%;
  line-height:1.03;letter-spacing:-.04em;text-wrap:balance}
.capa h1 em{font-style:normal;color:var(--marca)}
.capa .sub{color:var(--muted);font-size:clamp(14px,1.6vw,16.5px);margin-top:14px;
  max-width:44ch}

.mural{position:relative;height:min(60vh,470px);overflow:hidden;border-radius:20px;
  display:grid;grid-template-columns:repeat(3,1fr);gap:10px;
  pointer-events:none;-webkit-mask-image:linear-gradient(#000 62%,transparent);
  mask-image:linear-gradient(#000 62%,transparent)}
.mcol{overflow:hidden}
.mfita{display:flex;flex-direction:column;gap:10px;
  animation:deriva var(--dur,38s) linear infinite}
.mcol:nth-child(2) .mfita{animation-direction:reverse}
@keyframes deriva{to{transform:translateY(-50%)}}
.mfita i{display:block;aspect-ratio:1;border-radius:13px;background:#F4F5F7;
  background-size:cover;background-position:center;border:1px solid var(--linha);
  flex:none}
.mfade{position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(180deg,transparent 55%,var(--bg))}
@media(max-width:900px){
  .capa{grid-template-columns:1fr;gap:16px;padding-top:10px}
  /* no celular o mural vira uma FAIXA: uma tira de 96px que dá o recado sem
     empurrar o produto pra fora da primeira tela */
  .mural{height:96px;grid-template-columns:1fr;border-radius:14px;
    -webkit-mask-image:none;mask-image:none}
  .mcol:nth-child(n+2){display:none}
  .mfita{flex-direction:row;animation-name:derivaX;--dur:30s}
  @keyframes derivaX{to{transform:translateX(-50%)}}
  .mfita i{width:96px;height:96px;aspect-ratio:auto}
  .mfade{background:linear-gradient(90deg,transparent 80%,var(--bg))}
}

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
.prova b{font-variant-numeric:tabular-nums}

@media(prefers-reduced-motion:reduce){
  .mfita{animation:none!important}
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
  <div class="wrap">
    <div class="barra">
      <a class="marca" href="#topo">top<i>shop</i></a>
      <a class="zap" href="{{GRUPO_TOPO}}" target="_blank" rel="noopener">Entrar no grupo</a>
    </div>
    <label class="buscabox">
      <input id="busca" type="search" placeholder="O que você viu no vídeo?"
             autocomplete="off" aria-label="Buscar produto">
      <svg class="lupa" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/></svg>
      <span class="atalho">/</span>
    </label>
    <p class="frase">O que você viu no vídeo, <b>achou aqui</b> — com link direto
       e preço conferido.</p>
  </div>
</div>

<main class="wrap">

  <!-- ⚠️ O HERÓI VOLTOU, MAS DE OUTRA ESPÉCIE. O antigo era institucional:
       título de 84px, três números contando e uma moldura girando com o mouse,
       tudo ENTRE a pessoa e o produto. Este é feito DE produto — o mural à
       direita é o catálogo derivando. O conceito de herói nunca foi o problema;
       o problema era um herói que não mostrava mercadoria. -->
  <section class="capa">
    <div>
      <span class="olho">Social commerce discovery</span>
      <h1>O que você viu no vídeo, <em>achou aqui</em>.</h1>
      <p class="sub">A gente garimpa nos vídeos, confere o preço e deixa o link
         pronto. Você só procura o que viu.</p>
    </div>
    {{MURAL}}
  </section>

  <section id="produtos">
    {{VITRINE}}
  </section>

  <section id="como" class="reveal">
    <span class="eyebrow">Como funciona</span>
    <h2>Do vídeo pro carrinho, sem enrolação</h2>
    <p class="sec-sub">A gente garimpa e testa. Você só precisa do link certo —
       e ele tá sempre aqui.</p>
    <div class="passos">
      <div class="passo"><span class="num">1</span>
        <h3>Você viu no vídeo</h3>
        <p>Todo achado que aparece no nosso Reels passou por garimpo e teste antes.</p></div>
      <div class="passo"><span class="num">2</span>
        <h3>Achou aqui</h3>
        <p>O produto do vídeo entra nesta página no mesmo dia, com o link certo.
           Nada de procurar no perfil.</p></div>
      <div class="passo"><span class="num">3</span>
        <h3>Compra na loja oficial</h3>
        <p>O link leva direto pra Shopee ou Amazon. A compra é lá, no preço deles,
           com a garantia deles.</p></div>
    </div>
  </section>

  <section id="confianca" class="reveal">
    <span class="eyebrow">Por que confiar no link</span>
    <h2>A vitrine se corrige sozinha</h2>
    <p class="sec-sub">Nenhuma dessas frases é promessa: é o que o sistema faz
       todo dia, e o número ao lado sai dele.</p>
    <div class="provas">
      <div class="prova"><b>{{TOTAL}}</b>
        <h3>produtos no ar agora</h3>
        <p>Conferidos em {{DATA}}. Produto que sai do ar some da vitrine sozinho —
           você não clica em link morto.</p></div>
      <div class="prova"><b>{{DIAS}}</b>
        <h3>dias de preço acompanhado</h3>
        <p>Por isso o preço aparece como média, com a data do lado. Preço exato
           numa página envelhece; média com data, não.</p></div>
      <div class="prova"><b>{{OFF}}%</b>
        <h3>de desconto médio</h3>
        <p>O selo amarelo só aparece a partir de 15%. Abaixo disso não é
           desconto, é ruído — e a gente não põe selo por pôr.</p></div>
    </div>
  </section>

  <section id="contato" class="reveal">
    <div class="contato">
      <div>
        <span class="eyebrow">Vamos conversar</span>
        <h2>Fale comigo</h2>
        <p class="sec-sub">Quer indicar um produto, propor uma parceria ou entrar
           nos grupos de achadinhos? Chama aí.</p>
      </div>
      <div class="cis">
        {{GRUPOS}}
        <a class="ci" href="mailto:{{EMAIL}}"><span class="ico">✉️</span>
          <span>E-mail<i>{{EMAIL}}</i></span></a>
        <a class="ci" href="{{INSTAGRAM}}" target="_blank" rel="noopener"><span class="ico">📸</span>
          <span>Instagram<i>@topshop.__</i></span></a>
        <a class="ci" href="{{TIKTOK}}" target="_blank" rel="noopener"><span class="ico">🎵</span>
          <span>TikTok<i>@topshop.__</i></span></a>
        <a class="ci" href="{{YOUTUBE}}" target="_blank" rel="noopener"><span class="ico">▶️</span>
          <span>YouTube<i>@TopShop._0</i></span></a>
      </div>
    </div>
  </section>
</main>

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
document.querySelectorAll('.prova b').forEach(function(b){ obsNum.observe(b); });

/* ── o mural para quando some da tela ────────────────────────────────────
   Animação rodando fora da vista gasta bateria e mantém o celular acordado
   sem nada em troca. */
var mural = document.querySelector('.mural');
if (mural) new IntersectionObserver(function(ents){
  ents.forEach(function(en){
    mural.querySelectorAll('.mfita').forEach(function(f){
      f.style.animationPlayState = en.isIntersecting ? 'running' : 'paused';
    });
  });
}).observe(mural);
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