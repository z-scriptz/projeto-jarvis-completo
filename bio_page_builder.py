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
    plat = (p.get("plataforma") or "shopee").lower()
    # classe `plat` e não `loja`: `.loja` já é o botão de aba lá em cima, e as
    # duas regras de CSS brigavam pelo mesmo seletor
    selos.append(f'<span class="selo plat">{"Amazon" if plat == "amazon" else "Shopee"}</span>')
    return "".join(selos)


def _foto_html(p: dict, titulo: str, novo: bool = False) -> str:
    """Foto do produto com os três estados previstos: carregando (esqueleto),
    ok, e sem-foto (a Amazon hoje não devolve imagem)."""
    img = html.escape(p.get("imagem", ""))
    plat = (p.get("plataforma") or "shopee").lower()
    emoji = "📦" if plat == "amazon" else "🛍️"
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
    plat = (p.get("plataforma") or "shopee").lower()
    capa = (f'<img class="capa" src="{img}" alt="{titulo}" decoding="async">'
            if img else f'<em class="capa-fb">{"📦" if plat == "amazon" else "🛍️"}</em>')
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
    return '<div class="chips" id="filtros">' + "".join(botoes) + "</div>"


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
            f' data-plat="{chave}"{desab}><span class="pil"></span>'
            f'<span>{rotulo}<i class="n">{"em breve" if vazia else n}</i></span></button>')
    return ('<div class="lojas" id="filtros-plat" role="tablist">'
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
    grade = (f'<div class="palco"><div class="holofote" id="holofote"></div>'
             f'<div class="grade" id="grade-prod">{cards}</div></div>')
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
    destaque = _card_destaque(produtos[0]) if produtos else ""
    # imagem do 1º produto vira a prévia do link no WhatsApp/Instagram
    og = (produtos[0].get("imagem", "") if produtos else "") or ""
    grupo_topo = GRUPO_WHATSAPP or GRUPO_TELEGRAM or INSTAGRAM
    return _TEMPLATE.replace("{{VITRINE}}", _vitrine_html(produtos))\
                    .replace("{{DESTAQUE}}", destaque)\
                    .replace("{{ESTEIRA}}", _esteira_html(produtos))\
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
<meta name="theme-color" content="#09070E">
<style>
@font-face{font-family:'Arch';src:url('topshop-fonte.woff2') format('woff2');
  font-weight:100 900;font-stretch:62% 125%;font-display:swap}

:root{
  --void:#09070E; --sup:#150F22; --sup2:#1E1631; --linha:rgba(255,215,240,.10);
  --ink:#F7F2EC; --muted:#9C90AE;
  --pink:#FF3D8A; --ouro:#FFD84D; --menta:#3DFFB0;
  --r:16px;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--void);color:var(--ink);
  font-family:'Arch','Segoe UI',system-ui,-apple-system,sans-serif;
  line-height:1.5;overflow-x:hidden;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
img{max-width:100%}
.wrap{max-width:1240px;margin:0 auto;padding:0 clamp(16px,4vw,32px)}
:where(a,button,input):focus-visible{outline:2px solid var(--menta);
  outline-offset:3px;border-radius:10px}

/* ══ fundo em 3 camadas (parallax só no desktop) ══════════════════════════ */
.fundo{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden}
.cam{position:absolute;inset:-30vh -12vw;will-change:transform}
.cam i{position:absolute;border-radius:50%;display:block}
.longe i{filter:blur(100px);opacity:.30}
.longe i:nth-child(1){width:54vw;height:54vw;background:#8B1E52;top:8vh;right:-12vw;
  animation:deriva1 26s ease-in-out infinite alternate}
.longe i:nth-child(2){width:46vw;height:46vw;background:#2B1E6B;bottom:6vh;left:-10vw;
  animation:deriva2 32s ease-in-out infinite alternate}
.meio i{filter:blur(46px);opacity:.20}
.meio i:nth-child(1){width:20vw;height:20vw;background:#FF3D8A;top:52vh;left:14vw;
  animation:deriva2 19s ease-in-out infinite alternate}
.meio i:nth-child(2){width:15vw;height:15vw;background:#3DFFB0;top:22vh;right:26vw;
  opacity:.13;animation:deriva1 23s ease-in-out infinite alternate}
.perto{position:absolute;inset:0;opacity:.5;
  background-image:linear-gradient(var(--linha) 1px,transparent 1px),
                   linear-gradient(90deg,var(--linha) 1px,transparent 1px);
  background-size:72px 72px;background-position:0 var(--vy,0px),0 0;
  -webkit-mask-image:radial-gradient(70% 55% at 50% 34%,#000,transparent 78%);
  mask-image:radial-gradient(70% 55% at 50% 34%,#000,transparent 78%)}
@keyframes deriva1{to{transform:translate(-7vw,9vh) scale(1.14)}}
@keyframes deriva2{to{transform:translate(9vw,-7vh) scale(1.1)}}
body>*:not(.fundo){position:relative;z-index:1}

/* ══ topo ═════════════════════════════════════════════════════════════════ */
header{position:sticky;top:0;z-index:40;backdrop-filter:blur(20px);
  background:rgba(9,7,14,.72);border-bottom:1px solid transparent;
  transition:border-color .3s,background .3s}
header.colado{border-bottom-color:var(--linha);background:rgba(9,7,14,.92)}
.barra{display:flex;align-items:center;gap:clamp(10px,2.5vw,22px);padding-block:13px}
.marca{font-size:21px;font-weight:800;font-stretch:112%;letter-spacing:-.045em;
  white-space:nowrap;display:flex;align-items:center;gap:2px}
.marca i{font-style:normal;color:var(--pink)}
.marca .pt{color:var(--pink);animation:pisca 3.4s ease-in-out infinite}
@keyframes pisca{0%,92%,100%{opacity:1}96%{opacity:.25}}
.busca{flex:1;position:relative;max-width:520px}
.busca input{width:100%;background:rgba(255,255,255,.045);border:1px solid var(--linha);
  color:var(--ink);border-radius:999px;padding:11px 54px 11px 44px;font:inherit;
  font-size:15px;transition:border-color .25s,background .25s,box-shadow .25s}
.busca input::placeholder{color:var(--muted)}
.busca input:focus{outline:none;border-color:var(--pink);background:rgba(255,61,138,.07);
  box-shadow:0 0 0 4px rgba(255,61,138,.10)}
.busca .lupa{position:absolute;left:16px;top:50%;transform:translateY(-50%);
  width:17px;height:17px;stroke:var(--muted);fill:none;stroke-width:2;
  stroke-linecap:round;transition:stroke .25s,transform .25s;pointer-events:none}
.busca input:focus~.lupa{stroke:var(--pink);transform:translateY(-50%) scale(1.12)}
.atalho{position:absolute;right:14px;top:50%;transform:translateY(-50%);font-size:11px;
  color:var(--muted);border:1px solid var(--linha);border-radius:6px;padding:2px 6px;
  pointer-events:none}
@media(max-width:640px){.atalho{display:none}}
.zap{background:var(--menta);color:#03291B;font-weight:700;font-size:14px;
  padding:10px 17px;border-radius:999px;white-space:nowrap;
  transition:transform .2s,box-shadow .2s}
.zap:hover{transform:translateY(-2px);box-shadow:0 8px 22px rgba(61,255,176,.26)}
@media(max-width:860px){.zap{display:none}}

/* ══ herói ════════════════════════════════════════════════════════════════ */
.heroi{display:grid;grid-template-columns:1.15fr .85fr;gap:clamp(24px,5vw,56px);
  align-items:center;padding:clamp(30px,6vw,64px) 0 clamp(24px,4vw,40px);
  position:relative;isolation:isolate}
@media(max-width:900px){.heroi{grid-template-columns:1fr;gap:26px}}
.atmos{position:absolute;top:0;bottom:0;left:50%;transform:translateX(-50%);
  width:100vw;max-width:100vw;overflow:hidden;z-index:-2;pointer-events:none;
  -webkit-mask-image:linear-gradient(90deg,transparent,#000 9%,#000 91%,transparent);
  mask-image:linear-gradient(90deg,transparent,#000 9%,#000 91%,transparent)}
.vivo{position:absolute;inset:-24%;border-radius:50%;filter:blur(66px);opacity:.42;
  background:conic-gradient(from 0deg,rgba(255,61,138,.34),rgba(123,44,255,.30),
    rgba(61,255,176,.14),rgba(255,216,77,.20),rgba(255,61,138,.34));
  animation:gira 24s linear infinite}
@keyframes gira{to{transform:rotate(1turn)}}
.luz{position:absolute;inset:0;opacity:0;transition:opacity .55s;
  background:radial-gradient(430px circle at var(--hx,50%) var(--hy,50%),
    rgba(255,61,138,.15),transparent 66%)}
.heroi:hover .luz{opacity:1}
.rotulo{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:700;
  letter-spacing:.14em;text-transform:uppercase;color:var(--pink);margin-bottom:16px}
.rotulo::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--pink);
  box-shadow:0 0 0 0 rgba(255,61,138,.6);animation:pulso 2s infinite}
@keyframes pulso{70%{box-shadow:0 0 0 11px rgba(255,61,138,0)}
  100%{box-shadow:0 0 0 0 rgba(255,61,138,0)}}
h1{font-size:clamp(38px,7.4vw,84px);font-weight:800;font-stretch:118%;
  line-height:.92;letter-spacing:-.045em;text-wrap:balance;
  background:linear-gradient(100deg,var(--ink) 40%,#FFFFFF 48%,var(--ink) 56%);
  background-size:300% 100%;background-position:135% 0;
  -webkit-background-clip:text;background-clip:text;color:transparent;
  animation:varre 9s ease-in-out 1.8s infinite}
@keyframes varre{0%,62%{background-position:135% 0}100%{background-position:-35% 0}}
h1 .risca{position:relative;display:inline-block;color:var(--pink);padding-bottom:.1em}
h1 .risca::after{content:"";position:absolute;left:0;right:0;bottom:0;height:.075em;
  background:var(--ouro);transform:scaleX(0);transform-origin:left;border-radius:99px;
  animation:risca 1s cubic-bezier(.2,.7,.2,1) .5s forwards}
@keyframes risca{to{transform:scaleX(1)}}
.heroi p.sub{color:var(--muted);font-size:clamp(15px,2vw,18px);max-width:42ch;margin-top:18px}
.metricas{display:flex;gap:clamp(18px,4vw,40px);margin-top:28px;flex-wrap:wrap}
.metricas div{display:flex;flex-direction:column}
.metricas b{font-size:clamp(24px,3.4vw,34px);font-weight:800;font-stretch:110%;
  letter-spacing:-.03em;font-variant-numeric:tabular-nums;line-height:1}
.metricas span{font-size:12px;color:var(--muted);letter-spacing:.06em;
  text-transform:uppercase;margin-top:5px}
.cta-m{display:inline-flex;align-items:center;gap:9px;background:var(--pink);color:#fff;
  font-weight:750;font-size:15px;padding:14px 26px;border-radius:999px;margin-top:24px;
  transition:transform .18s,box-shadow .28s;box-shadow:0 10px 30px rgba(255,61,138,.28)}
.cta-m:hover{box-shadow:0 16px 42px rgba(255,61,138,.42)}
.cta-m .seta{transition:transform .3s}
.cta-m:hover .seta{transform:translateX(5px)}

/* moldura 9:16 — o formato do Reels de onde a pessoa veio */
.moldura{position:relative;aspect-ratio:9/16;max-height:520px;margin:0 auto;width:100%;
  max-width:300px;border-radius:26px;overflow:hidden;border:1px solid var(--linha);
  background:linear-gradient(180deg,#EFEBF4 0%,#E6E0F0 38%,#3A2E56 68%,var(--sup) 100%);
  box-shadow:0 30px 70px rgba(0,0,0,.55);display:block;
  transition:transform .35s cubic-bezier(.2,.7,.2,1)}
.moldura .capa{position:absolute;top:0;left:0;width:100%;height:64%;object-fit:cover;
  -webkit-mask-image:linear-gradient(#000 74%,transparent);
  mask-image:linear-gradient(#000 74%,transparent);
  animation:respira 12s ease-in-out infinite}
.moldura .capa-fb{position:absolute;top:0;left:0;width:100%;height:64%;display:grid;
  place-items:center;font-size:84px;font-style:normal;animation:respira 12s ease-in-out infinite}
@keyframes respira{50%{transform:scale(1.07)}}
.moldura .brilho{position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(60% 40% at 50% 0%,rgba(255,61,138,.30),transparent 70%)}
.moldura .live{position:absolute;top:14px;left:14px;display:flex;align-items:center;
  gap:6px;background:rgba(9,7,14,.7);backdrop-filter:blur(8px);
  border:1px solid var(--linha);border-radius:999px;padding:5px 11px;
  font-size:11px;font-weight:700}
.moldura .live b{width:6px;height:6px;border-radius:50%;background:var(--pink);
  animation:pulso 1.6s infinite}
.moldura .pe{position:absolute;left:0;right:0;bottom:0;padding:18px 16px 16px;
  background:linear-gradient(transparent,rgba(9,7,14,.94) 55%)}
.moldura .pe h3{font-size:14px;font-weight:600;line-height:1.3;margin-bottom:9px}
.moldura .pe .pr b{font-size:26px;color:var(--ouro)}
.moldura .pe .pr b i{color:rgba(255,216,77,.55)}
.moldura .pe .afer{margin-top:7px}

/* ══ esteira ══════════════════════════════════════════════════════════════ */
.esteira{border-top:1px solid var(--linha);border-bottom:1px solid var(--linha);
  padding:13px 0;overflow:hidden;white-space:nowrap;margin:clamp(14px,3vw,26px) 0;
  -webkit-mask-image:linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent);
  mask-image:linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent)}
.esteira .fita{display:inline-flex;gap:34px;animation:corre 40s linear infinite}
.esteira:hover .fita{animation-play-state:paused}
@keyframes corre{to{transform:translateX(-50%)}}
.esteira span{font-size:13px;color:var(--muted);display:inline-flex;align-items:center;gap:9px}
.esteira span::before{content:"";width:5px;height:5px;border-radius:50%;
  background:var(--pink);flex:none}
.esteira b{color:var(--ink);font-weight:600}

/* ══ controles ════════════════════════════════════════════════════════════ */
.controles{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-bottom:20px}
.lojas{display:flex;gap:5px;background:rgba(255,255,255,.04);border:1px solid var(--linha);
  border-radius:999px;padding:5px;overflow-x:auto;scrollbar-width:none;max-width:100%}
.lojas::-webkit-scrollbar{display:none}
.loja{border:0;background:none;color:var(--muted);font:inherit;font-size:14px;
  font-weight:650;padding:9px 17px;border-radius:999px;cursor:pointer;white-space:nowrap;
  position:relative;isolation:isolate;transition:color .22s}
.loja[aria-selected="true"]{color:#fff}
.loja .pil{position:absolute;inset:0;border-radius:999px;z-index:0;opacity:0;
  transform:scale(.85);background:linear-gradient(120deg,var(--pink),#B4247E);
  transition:opacity .3s,transform .3s cubic-bezier(.2,.7,.2,1)}
.loja[aria-selected="true"] .pil{opacity:1;transform:scale(1)}
.loja>span:not(.pil){position:relative;z-index:1}
.loja .n{opacity:.62;margin-left:6px;font-variant-numeric:tabular-nums;font-style:normal}
.loja:disabled{opacity:.38;cursor:not-allowed}
.chips{display:flex;gap:7px;flex-wrap:wrap}
.chip{border:1px solid var(--linha);background:transparent;color:var(--muted);font:inherit;
  font-size:13px;padding:8px 14px;border-radius:999px;cursor:pointer;
  transition:color .2s,border-color .2s,background .2s,transform .2s}
.chip:hover{color:var(--ink);transform:translateY(-1px)}
.chip[aria-pressed="true"]{background:var(--ink);color:#12100D;border-color:var(--ink)}

/* ══ grade ════════════════════════════════════════════════════════════════ */
.palco{position:relative}
.holofote{position:absolute;inset:0;pointer-events:none;opacity:0;transition:opacity .4s;
  background:radial-gradient(340px circle at var(--mx,50%) var(--my,50%),
    rgba(255,61,138,.13),transparent 62%)}
.palco:hover .holofote{opacity:1}
.grade{display:grid;gap:clamp(11px,1.6vw,18px);
  grid-template-columns:repeat(auto-fill,minmax(215px,1fr))}
.card{background:linear-gradient(165deg,var(--sup),rgba(21,15,34,.6));
  border:1px solid var(--linha);border-radius:var(--r);overflow:hidden;display:flex;
  flex-direction:column;position:relative;
  transition:opacity .55s,transform .4s cubic-bezier(.2,.7,.2,1),
    border-color .3s,box-shadow .4s}
.card.esconde{display:none}
.js .card{opacity:0;transform:translateY(24px)}
.js .card.dentro{opacity:1;transform:none}
.card:hover{border-color:rgba(255,61,138,.45);box-shadow:0 22px 50px rgba(0,0,0,.5)}
.card .foto{aspect-ratio:1;position:relative;overflow:hidden;
  background:linear-gradient(170deg,#F6F3F8,#DDD6E6)}
.card .foto img{width:100%;height:100%;object-fit:cover;display:block;opacity:0;
  transition:opacity .5s,transform .6s cubic-bezier(.2,.7,.2,1)}
.card .foto img.ok{opacity:1}
.card:hover .foto img.ok{transform:scale(1.07)}
.card .foto .fb{position:absolute;inset:0;display:none;place-items:center;font-size:46px;
  font-style:normal;transition:transform .45s cubic-bezier(.2,.7,.2,1)}
.card .foto.sem-foto{background:radial-gradient(110% 80% at 50% 12%,var(--sup2),transparent)}
.card .foto.sem-foto .fb{display:grid}
.card:hover .foto.sem-foto .fb{transform:scale(1.14) rotate(-4deg)}
.card .foto.carregando{background-image:linear-gradient(100deg,
  #E9E3F0 42%,#F9F6FC 50%,#E9E3F0 58%);background-size:280% 100%;
  animation:esqueleto 1.25s linear infinite}
@keyframes esqueleto{from{background-position:160% 0}to{background-position:-60% 0}}
.card .foto::after{content:"";position:absolute;inset:0;transform:translateX(-110%);
  pointer-events:none;background:linear-gradient(112deg,transparent 40%,
    rgba(255,255,255,.34) 50%,transparent 60%);transition:transform .8s}
.card:hover .foto::after{transform:translateX(110%)}
.selo{position:absolute;top:10px;left:10px;font-size:10.5px;font-weight:750;
  padding:4px 9px;border-radius:999px;letter-spacing:.03em;background:rgba(9,7,14,.72);
  backdrop-filter:blur(8px);border:1px solid var(--linha);color:var(--ink);z-index:2}
.selo.novo{background:var(--menta);color:#03291B;border-color:transparent}
.selo.off{background:var(--ouro);color:#2A1C00;border-color:transparent;left:auto;right:10px}
.selo.plat{top:auto;bottom:10px}
.card .corpo{padding:13px 14px 15px;display:flex;flex-direction:column;gap:10px;flex:1}
.card h3{font-size:14px;font-weight:550;line-height:1.35;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card .ver{display:flex;align-items:center;justify-content:center;gap:7px;
  border:1px solid var(--linha);border-radius:11px;padding:11px;font-size:13.5px;
  font-weight:700;margin-top:auto;transition:background .25s,border-color .25s,color .25s}
.card:hover .ver{background:var(--pink);border-color:var(--pink);color:#fff}

/* preço — o til avisa que é média, não preço travado */
.pr{display:flex;align-items:baseline;gap:8px}
.pr b,.pr s{white-space:nowrap}
.pr b{font-size:21px;font-weight:800;letter-spacing:-.025em;font-variant-numeric:tabular-nums}
.pr b i{font-style:normal;font-weight:600;font-size:.62em;margin-right:2px;
  position:relative;top:-.1em;color:var(--muted)}
.pr s{color:var(--muted);font-size:12px}
.afer{font-size:10.5px;color:var(--muted);letter-spacing:.015em;margin-top:-4px;
  display:flex;align-items:flex-start;gap:5px;line-height:1.35}
.afer::before{content:"";width:4px;height:4px;border-radius:50%;background:var(--muted);
  flex:none;opacity:.7;margin-top:.42em}
.afer.caindo{color:var(--menta)}
.afer.caindo::before{background:var(--menta);opacity:1}

.vazio{text-align:center;padding:60px 20px;color:var(--muted)}
.vazio b{display:block;color:var(--ink);font-size:19px;margin-bottom:7px;font-weight:700}

/* ══ seções de conteúdo ═══════════════════════════════════════════════════ */
section{padding:clamp(48px,8vw,88px) 0}
.eyebrow{display:inline-block;font-size:12px;font-weight:700;letter-spacing:.14em;
  text-transform:uppercase;color:var(--pink);margin-bottom:12px}
h2{font-size:clamp(26px,4.4vw,44px);font-weight:800;font-stretch:112%;
  letter-spacing:-.035em;line-height:1.05;text-wrap:balance}
.sec-sub{color:var(--muted);margin-top:12px;max-width:56ch;font-size:clamp(14px,1.8vw,16.5px)}
.reveal{opacity:1}
.js .reveal{opacity:0;transform:translateY(26px);
  transition:opacity .7s,transform .7s cubic-bezier(.2,.7,.2,1)}
.js .reveal.dentro{opacity:1;transform:none}
/* passos numerados: aqui a numeração significa ordem de verdade — é a
   sequência que a pessoa percorre, não enfeite */
.passos{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
  gap:clamp(11px,1.6vw,18px);margin-top:34px;counter-reset:passo}
.passo{padding:26px 22px 28px;border-radius:var(--r);border:1px solid var(--linha);
  background:linear-gradient(165deg,var(--sup),rgba(21,15,34,.55));position:relative;
  transition:border-color .3s,transform .3s,box-shadow .3s}
.passo:hover{border-color:rgba(255,61,138,.4);transform:translateY(-4px);
  box-shadow:0 20px 44px rgba(0,0,0,.45)}
.passo .num{display:grid;place-items:center;width:34px;height:34px;border-radius:50%;
  background:var(--pink);color:#fff;font-weight:800;font-size:15px;margin-bottom:16px}
.passo h3{font-size:17px;font-weight:700;margin-bottom:8px;letter-spacing:-.01em}
.passo p{color:var(--muted);font-size:14px;line-height:1.55}
/* provas: o número é o argumento, então ele é que fica grande */
.provas{display:grid;grid-template-columns:repeat(auto-fit,minmax(258px,1fr));
  gap:clamp(11px,1.6vw,18px);margin-top:34px}
.prova{padding:24px 22px 26px;border-radius:var(--r);border:1px solid var(--linha);
  background:rgba(255,255,255,.025);transition:border-color .3s,transform .3s}
.prova:hover{border-color:rgba(61,255,176,.4);transform:translateY(-3px)}
.prova b{display:block;font-size:clamp(38px,5.4vw,52px);font-weight:800;
  font-stretch:110%;letter-spacing:-.04em;line-height:1;color:var(--menta);
  font-variant-numeric:tabular-nums}
.prova h3{font-size:13px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  color:var(--ink);margin:10px 0 10px}
.prova p{color:var(--muted);font-size:14px;line-height:1.55}
.contato{display:grid;grid-template-columns:1fr 1fr;gap:clamp(24px,5vw,56px);
  align-items:start}
@media(max-width:820px){.contato{grid-template-columns:1fr}}
.cis{display:flex;flex-direction:column;gap:10px;margin-top:8px}
.ci{display:flex;align-items:center;gap:13px;padding:15px 17px;border-radius:13px;
  border:1px solid var(--linha);background:rgba(255,255,255,.025);
  transition:border-color .25s,transform .25s}
.ci:hover{border-color:rgba(61,255,176,.42);transform:translateX(3px)}
.ci .ico{font-size:19px;flex:none}
.ci span{display:flex;flex-direction:column;font-size:14.5px;font-weight:600}
.ci span i{font-style:normal;font-size:12.5px;color:var(--muted);font-weight:400;margin-top:2px}

footer.wrap{border-top:1px solid var(--linha);padding-block:30px 48px;color:var(--muted);
  font-size:13px;display:flex;gap:16px;flex-wrap:wrap;justify-content:space-between}
footer a{border-bottom:1px solid var(--linha)}

@media(max-width:560px){
  .grade{grid-template-columns:repeat(2,1fr)}
  .card .corpo{padding:10px 11px 12px;gap:8px}
  .card h3{font-size:12.5px}
  .card .ver{padding:9px;font-size:12.5px}
  .card .foto .fb{font-size:36px}
  /* preço empilhado: lado a lado o riscado quebrava no meio do número
     ("R$" numa linha, "220,37" na outra) no card de duas colunas */
  .pr{flex-direction:column;align-items:flex-start;gap:1px}
  .pr b{font-size:17px}
  .pr s{font-size:11px}
  /* chips numa fita rolável: em pé eles ocupavam 3 fileiras inteiras antes
     do primeiro produto aparecer */
  .chips{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;
    margin-inline:calc(-1 * clamp(16px,4vw,32px));
    padding-inline:clamp(16px,4vw,32px)}
  .chips::-webkit-scrollbar{display:none}
  .chip{flex:none}
}
@media(prefers-reduced-motion:reduce){
  *{animation:none!important;transition-duration:.01ms!important}
  .js .card,.js .reveal{opacity:1;transform:none}
  h1{background:none;-webkit-text-fill-color:var(--ink);color:var(--ink)}
}
</style>
</head>
<body>
<div class="fundo" aria-hidden="true">
  <div class="cam longe" data-k="0.10"><i></i><i></i></div>
  <div class="cam meio"  data-k="0.30"><i></i><i></i></div>
  <div class="perto" data-k="0.55"></div>
</div>

<header id="topo">
  <div class="wrap barra">
    <a class="marca" href="#topo">top<i>shop</i><span class="pt">.</span></a>
    <label class="busca">
      <input id="busca" type="search" placeholder="Buscar o achado do vídeo..."
             autocomplete="off" aria-label="Buscar produto">
      <svg class="lupa" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/></svg>
      <span class="atalho">/</span>
    </label>
    <a class="zap" href="{{GRUPO_TOPO}}" target="_blank" rel="noopener">Entrar no grupo</a>
  </div>
</header>

<main class="wrap">
  <section class="heroi" id="inicio">
    <div class="atmos" id="atmos"><div class="vivo"></div><div class="luz" id="luz"></div></div>
    <div>
      <div class="rotulo">Achado de hoje</div>
      <h1>O que você viu<br>no vídeo, <span class="risca">achou aqui</span>.</h1>
      <p class="sub">A gente garimpa, testa e mostra. Se apareceu no Reels, o link
         tá aqui embaixo — com preço conferido.</p>
      <div class="metricas">
        <div><b data-alvo="{{TOTAL}}">{{TOTAL}}</b><span>achados ativos</span></div>
        <div><b data-alvo="{{LOJAS}}">{{LOJAS}}</b><span>{{LOJAS_ROTULO}}</span></div>
        <div><b data-alvo="{{OFF}}">{{OFF}}</b><span>% off médio</span></div>
      </div>
      <a class="cta-m" href="#produtos">Ver o garimpo <span class="seta">&rarr;</span></a>
    </div>
    {{DESTAQUE}}
  </section>

  {{ESTEIRA}}

  <section id="produtos" style="padding-top:clamp(18px,3vw,32px)">
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

/* ── números do herói subindo (o valor certo já está no HTML) ───────────── */
document.querySelectorAll('.metricas b').forEach(function(el){
  var alvo = +el.dataset.alvo || 0;
  if (calmo || !alvo) return;
  var t0 = null;
  requestAnimationFrame(function passo(t){
    if (!t0) t0 = t;
    var k = Math.min(1, (t - t0) / 1100), e = 1 - Math.pow(1 - k, 3);
    el.textContent = Math.round(alvo * e);
    if (k < 1) requestAnimationFrame(passo);
  });
});

/* ── filtros e busca: só mostram e escondem o que já veio pronto ────────── */
var st = {plat: 'todos', cat: 'todos', q: ''};
var cards = [].slice.call(document.querySelectorAll('.card'));
var semRes = document.getElementById('sem-res');

function aplicar(){
  var visiveis = 0;
  cards.forEach(function(c){
    var ok = (st.plat === 'todos' || c.dataset.plataforma === st.plat)
          && (st.cat === 'todos' || c.dataset.categoria === st.cat)
          && (!st.q || (c.dataset.busca || '').indexOf(st.q) > -1);
    c.classList.toggle('esconde', !ok);
    if (ok) visiveis++;
  });
  if (semRes) semRes.style.display = visiveis ? 'none' : '';
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

/* ── holofote sobre a grade e inclinação 3D dos cards ───────────────────── */
var palco = document.querySelector('.palco'), holo = document.getElementById('holofote');
if (palco && holo) palco.addEventListener('pointermove', function(e){
  var r = palco.getBoundingClientRect();
  holo.style.setProperty('--mx', (e.clientX - r.left) + 'px');
  holo.style.setProperty('--my', (e.clientY - r.top) + 'px');
});
if (!calmo && fino) cards.forEach(function(c){
  c.addEventListener('pointermove', function(e){
    var r = c.getBoundingClientRect();
    var x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
    c.style.transform = 'perspective(760px) rotateX(' + (-y * 7).toFixed(2) +
      'deg) rotateY(' + (x * 7).toFixed(2) + 'deg) translateY(-5px)';
  });
  c.addEventListener('pointerleave', function(){ c.style.transform = ''; });
});

/* ── herói: luz no cursor e moldura acompanhando ────────────────────────── */
var heroi = document.querySelector('.heroi'), luz = document.getElementById('luz');
var atmos = document.getElementById('atmos'), mold = document.getElementById('moldura');
var giro = {x:0, y:0}, desloc = 0;
function porMoldura(){
  if (!mold) return;
  mold.style.transform = 'perspective(1000px) translateY(' + desloc.toFixed(1) + 'px)' +
    ' rotateY(' + giro.x.toFixed(2) + 'deg) rotateX(' + giro.y.toFixed(2) + 'deg)';
}
if (!calmo && fino && heroi){
  heroi.addEventListener('pointermove', function(e){
    /* medido contra .atmos, que é mais largo que o herói */
    var r = atmos.getBoundingClientRect();
    luz.style.setProperty('--hx', (e.clientX - r.left) + 'px');
    luz.style.setProperty('--hy', (e.clientY - r.top) + 'px');
  });
  addEventListener('pointermove', function(e){
    giro.x = (e.clientX / innerWidth - .5) * 9;
    giro.y = -(e.clientY / innerHeight - .5) * 6;
    porMoldura();
  });
}

/* ── profundidade: 3 camadas em velocidades diferentes, só no desktop ────
   No celular o parallax de scroll engasga e a gente perde mais do que ganha —
   e o tráfego daqui vem quase todo da bio do Instagram. */
var camadas = [].slice.call(document.querySelectorAll('.cam'));
var perto = document.querySelector('.perto');
if (!calmo && fino && matchMedia('(min-width:900px)').matches){
  var agendado = false;
  addEventListener('scroll', function(){
    if (agendado) return;
    agendado = true;
    requestAnimationFrame(function(){
      var y = scrollY;
      camadas.forEach(function(c){
        c.style.transform = 'translate3d(0,' + (-y * (+c.dataset.k)).toFixed(1) + 'px,0)';
      });
      if (perto) perto.style.setProperty('--vy', (-y * (+perto.dataset.k)).toFixed(1) + 'px');
      desloc = Math.max(-26, -y * 0.06);
      porMoldura();
      agendado = false;
    });
  }, {passive:true});
}

addEventListener('scroll', function(){
  document.getElementById('topo').classList.toggle('colado', scrollY > 8);
}, {passive:true});
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