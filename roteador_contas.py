#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# roteador_contas.py -- decide EM QUAL conta cada produto vai, pelo nicho.
# Lê contas.json (mapa nicho -> conta) e classifica o produto em DUAS camadas:
#
#   1. PALAVRA-CHAVE  — grátis, instantânea e determinística. Resolve a maioria.
#   2. IA (Gemini)    — só quando a camada 1 não reconhece. Com cache em disco,
#                       então cada produto é perguntado UMA vez na vida.
#
# A ordem importa: keyword primeiro porque é de graça e sempre dá o mesmo
# resultado; a IA entra só no que sobrou, que é onde o dinheiro escapava (produto
# de tech/beleza caindo na conta geral por não estar na lista).
#
# Desligar a camada 2:  ROTEADOR_IA=0 no .env
#
# Uso rápido de teste:
#   python3 roteador_contas.py "Sérum facial com vitamina C"   -> beleza
#   python3 roteador_contas.py "Escova Secadora Rotativa"      -> beleza (via IA)
#   python3 roteador_contas.py --lote produtos.txt             -> tabela
import os
import re
import sys
import json
from pathlib import Path

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    log = logging.getLogger("roteador_contas")

BASE_DIR = Path(__file__).resolve().parent
CONTAS_JSON = BASE_DIR / "contas.json"
CACHE_IA = BASE_DIR / "shared" / "roteador_cache.json"


def _carregar_env():
    for cand in (BASE_DIR / ".env", Path(".env")):
        if not cand.exists():
            continue
        for linha in cand.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            k, _, v = linha.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and not os.environ.get(k):
                os.environ[k] = v
        break


_carregar_env()

# ═════════════════════════════════════════════════════════════════════════════
# CAMADA 1 — palavras-chave
# ═════════════════════════════════════════════════════════════════════════════
# Casam no INÍCIO da palavra, então "maquiag" pega "maquiagem"/"maquiador" mas
# "pele" não pega "impeler". Prefixo é proposital em vários termos.
_BELEZA = (
    "beleza", "beauty", "skincare", "maquiag", "makeup", "perfume", "hidratante",
    "batom", "serum", "sérum", "depila", "cilios", "cílios", "sobrancelha",
    "gloss", "cosmetic", "esmalte", "secador de cabelo", "chapinha", "prancha de cabelo",
    "cabelo", "unha", "pele", "labial", "rímel", "rimel", "delineador",
    "autocuidado", "auto cuidado", "estetica", "estética", "modelador", "babyliss",
    "alisador", "necessaire", "nécessaire", "corporal", "facial", "protetor solar",
    "hialuron", "bronzead", "pincéis de maquiagem", "pincel de maquiagem",
    # lacunas que caíam em 'geral' (o motivo desta revisão)
    "escova secadora", "escova alisadora", "escova modeladora", "escova rotativa",
    "massageador facial", "massageador corporal", "limpeza facial", "esfoliante",
    "sabonete facial", "mascara facial", "máscara facial", "mascara capilar",
    "condicionador", "shampoo", "xampu", "leave-in", "ampola capilar",
    "removedor de cravo", "extrator de cravo", "removedor de esmalte",
    "lixa eletrica", "lixa elétrica", "kit manicure", "alicate de unha",
    "cortador de cutícula", "cutícula", "cuticula", "henna", "micropigmenta",
    "lash", "extensao de cilios", "extensão de cílios", "curvex",
    "espelho de maquiagem", "organizador de maquiagem", "paleta de sombra",
    "sombra", "corretivo", "primer", "base liquida", "base líquida", "pó compacto",
    "iluminador", "blush", "contorno facial", "bronzer",
    "creme facial", "creme corporal", "creme para as maos", "creme para as mãos",
    "oleo corporal", "óleo corporal", "oleo capilar", "óleo capilar",
    "depilador", "epilador", "aparador de pelos", "barbeador",
    "escova de dente eletrica", "escova de dente elétrica", "clareador dental",
    "gua sha", "rolo de jade", "dermaroller", "led facial",
    # vistos na fila de producao real
    "cuticle", "clareador", "toner", "tonico facial", "tônico facial",
    "esponja de maquiagem", "esponja para maquiagem", "modelador de cachos",
    "hidratante labial", "balm labial", "mascara de cilios", "máscara de cílios",
    "centella", "acido hialuronico", "ácido hialurônico", "niacinamida",
    "sabonete", "esfoliante corporal", "perfume", "eau de parfum",
)
_TECH = (
    "fone", "headset", "earbud", "carregador", "smartwatch", "smart watch",
    "powerbank", "power bank", "projetor", "drone", "caixa de som", "bluetooth",
    "webcam", "mouse", "teclado", "ring light",
    "gamer", "smart tv", "roteador wi", "ssd", "pendrive", "gadget",
    "celular", "smartphone", "iphone", "android", "telefone", "capinha",
    "capa de celular", "capa de telefone", "capa magnetica", "capa magnética",
    "magsafe", "pelicula", "película", "suporte de celular", "suporte celular",
    "suporte veicular", "cabo usb", "cabo tipo c", "cabo lightning",
    "carregador sem fio", "hub usb", "adaptador usb",
    "games", "gaming", "console", "playstation", "xbox", "nintendo", "joystick",
    "mousepad", "mouse pad", "cadeira gamer", "headset gamer", "notebook", "cooler",
    "placa de video", "placa de vídeo", "controle sem fio", "fone gamer",
    # lacunas que caíam em 'geral'
    "conducao ossea", "condução óssea", "tws", "fone sem fio", "microfone",
    "estabilizador de imagem", "gimbal", "tripé", "tripe", "bastao de selfie",
    "bastão de selfie", "aro de luz", "iluminador led", "softbox",
    "mini projetor", "projetor portatil", "projetor portátil",
    "impressora portatil", "impressora portátil", "scanner",
    "rastreador gps", "airtag", "localizador bluetooth",
    "camera de seguranca", "câmera de segurança", "camera ip", "babá eletrônica",
    "baba eletronica", "fechadura digital", "campainha inteligente",
    "lampada inteligente", "lâmpada inteligente", "tomada inteligente",
    "controle universal", "receptor bluetooth", "transmissor fm",
    "carregador veicular", "suporte notebook", "base para notebook",
    "hd externo", "cartao de memoria", "cartão de memória", "leitor de cartao",
    "caneta touch", "teclado sem fio", "monitor", "kindle", "e-reader",
    "relogio inteligente", "relógio inteligente", "pulseira inteligente",
    "smart band", "oximetro", "oxímetro",
    # vistos na fila de producao real
    "xiaomi", "redmi", "poco x", "motorola", "ipad", "tablet", "airpods",
    "capa antichoque", "capa para iphone", "capa para samsung", "iwo",
)
# 'casa' ainda NÃO tem conta própria no contas.json — classificar aqui só serve
# pra medir o volume e decidir se vale abrir a quarta conta. Sem conta, cai em geral.
_CASA = (
    "organizador", "cesto", "cabide", "porta-tempero", "porta tempero",
    "panela", "frigideira", "assadeira", "tábua de corte", "tabua de corte",
    "utensilio de cozinha", "utensílio de cozinha", "escorredor", "pote hermetico",
    "pote hermético", "lixeira", "rodo", "vassoura", "esfregao", "esfregão",
    "mop", "aspirador", "varal", "cabideiro", "prateleira", "suporte de parede",
    "toalha", "jogo de cama", "lencol", "lençol", "edredom", "cortina", "tapete",
    # ⚠️ TUDO QUE CUIDA DE ROUPA É CASA — A ROUPA EM SI É MODA.
    #
    # Esta é a segunda vez que o "roupa" cru da lista de MODA rouba um produto
    # de casa. Em 19/08 eu consertei UMA FRASE ("roupa de cama") e achei que
    # tinha resolvido; em 20/08 a limpeza do cache do Dre mostrou o resto da
    # família:
    #
    #     'passadeira ferro a vapor com tabua de passar roupa'  → moda ✗
    #     'maquina de lavar roupa portatil'                     → moda ✗
    #
    # Consertar um caso quando o problema é uma CLASSE só adia. A regra é:
    # tábua, ferro, varal, cabide, cesto e máquina cuidam de roupa e moram na
    # casa; vestido e camisa se vestem. CASA é checada antes de MODA, então
    # basta a frase existir aqui.
    "roupa de cama", "roupa de banho", "roupa de mesa", "cama mesa e banho",
    "passar roupa", "passadeira", "ferro de passar", "ferro a vapor",
    "tabua de passar", "lavar roupa", "maquina de lavar", "lava e seca",
    "secadora de roupa", "guarda-roupa", "guarda roupa", "arara de roupa",
    "amaciante", "sabao em po", "sabao liquido", "tira mancha",
    "porta-cabide", "organizador de roupa",
    # 'travesseiro' faltava (05/09/2026): a lista tinha almofada, edredom e
    # lençol, mas 'Kit 2 Travesseiro De Corpo Xuxão' saía sem nicho e ia gastar
    # chamada de IA pra descobrir que travesseiro é coisa de casa.
    "almofada", "travesseiro", "fronha", "luminaria de mesa",
    "luminária de mesa", "abajur",
    "descascador", "ralador", "abridor", "dispenser", "saboneteira",
    "porta-escova", "chuveiro", "ducha", "tapete de banheiro",
    "umidificador", "difusor de aroma", "aromatizador", "vela aromatica",
    "vela aromática", "purificador de ar", "desumidificador",
    # vistos na fila de producao real
    "luminaria", "luminária", "taça", "taca", "xicara", "xícara",
    "porta treco", "porta-treco", "garrafa termica", "garrafa térmica",
    "jogo de copos", "jogo de tacas", "jogo de taças", "bandeja",
)

# ⚠️ PET E MODA NASCERAM AQUI EM 19/08 — AS CONTAS EXISTIAM HÁ SEMANAS.
#
# O vigia, na 1ª execução, mostrou 377 pacotes prontos assim:
#     @topshop.__ 143 · @topshoptech_ 105 · @topshopbeauty._ 75 · @topshopcasa_ 54
# ZERO pro @topshoppet_ e ZERO pro @topshopmoda_ — e as duas contas estavam no
# contas.json, com ig_user_id e token. O buraco não era falta de fonte: era que
# `_NICHOS_VALIDOS` tinha só ("beleza","tech","casa","geral"). Caminha de
# cachorro e bolsa viravam 'geral'. Nada podia rotear pra lá, nunca.
#
# Então adicionar fonte de pet sem isto aqui pareceria progresso e não moveria
# um vídeo sequer.
#
# ⚠️ A ORDEM DAS LISTAS DECIDE O EMPATE — e cada posição abaixo tem um motivo:
#
#   PET vem PRIMEIRO   'shampoo para cachorro' bateria em "shampoo" (beleza) e
#                      'escova para pet' em "escova secadora". As frases de pet
#                      são específicas, então elas não roubam nada de beleza:
#                      "escova de cabelo" não casa com "escova para pet".
#   TECH antes de MODA "relogio inteligente" e "pulseira inteligente" são tech,
#                      e MODA tem "relogio"/"pulseira" genéricos.
#   CASA antes de MODA "roupa de cama", "cesto de roupa" e "cabide" são casa;
#                      MODA tem "roupa" cru e levaria os três.
_PET = (
    "cachorro", "cachorros", "cadela", "cao ", "cães", "caes", "dog", "doguinho",
    "gato", "gatos", "gatinho", "felino", "pet", "pets", "petshop", "pet shop",
    "coleira", "peitoral para", "guia retratil", "guia retrátil", "focinheira",
    "racao", "ração", "comedouro", "bebedouro", "petisco", "petiscos",
    "arranhador", "caixa de areia", "areia sanitaria", "areia sanitária",
    "tapete higienico", "tapete higiênico", "casinha de cachorro",
    "caminha para", "cama para pet", "aquario", "aquário", "gaiola", "viveiro",
    "hamster", "coelho", "passaro", "pássaro", "calopsita", "periquito",
    "antipulgas", "vermifugo", "vermífugo", "tosa", "tosador",
    "escova para pet", "escova removedora de pelo", "removedor de pelo",
    "cortador de unha para", "bolsa de transporte para", "caixa de transporte",
    "fonte para gato", "brinquedo para cachorro", "brinquedo para gato",
    "brinquedo para pet", "mordedor", "osso para cachorro",
)
_MODA = (
    "roupa", "roupas", "vestido", "blusa", "camiseta", "camisa", "regata",
    "calca", "calça", "jeans", "short", "saia", "macacao", "macacão",
    "conjunto feminino", "conjunto masculino", "moletom", "jaqueta", "casaco",
    "blazer", "cardiga", "sueter", "suéter", "pijama", "lingerie", "sutia",
    "sutiã", "calcinha", "cueca", "meia", "meias", "biquini", "biquíni",
    "maio ", "maiô", "sunga",
    "sapato", "tenis", "tênis", "sandalia", "sandália", "chinelo", "rasteirinha",
    "sapatilha", "bota", "botas", "salto alto", "scarpin", "mocassim",
    "bolsa", "bolsas", "mochila", "carteira", "pochete", "necessaire de viagem",
    "cinto", "oculos de sol", "óculos de sol", "chapeu", "chapéu", "bone",
    "boné", "lenco", "lenço", "cachecol", "luva", "brinco", "colar", "pulseira",
    "anel", "aneis", "anéis", "bijuteria", "bijoux", "relogio", "relógio",
    "modelador corporal", "cinta modeladora", "body feminino", "top fitness",
    "legging", "leggings",
)

# ⚠️ 'geral' fica FORA das listas de propósito: é o que sobra, não o que casa.
_NICHOS_VALIDOS = ("beleza", "tech", "casa", "moda", "pet", "geral")


def _sem_acento(s: str) -> str:
    return (s or "").translate(str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc"))


def _compilar(palavras) -> re.Pattern:
    """Casa no início da palavra e deixa passar só gênero/plural: 'pele' pega
    'pele/peles', mas não 'impeler' nem 'peleteria'.

    ⚠️ ANTES O FIM ERA LIVRE, e isso fazia uma lista COMER PALAVRA DE OUTRA
    (achado em 05/09/2026): 'sabonete' (beleza) casava com o começo de
    'saboneteira' — que está na lista de CASA logo ali embaixo. Como beleza é
    testada antes de casa, toda saboneteira virava beleza, e a palavra na lista
    certa nunca teve chance. Um Dispenser de sabonete foi parar no
    @topshopbeauty._ por causa disto.

    Uso `(?![a-z0-9])` em vez de `\\b` no fim porque várias entradas são frases
    ('escova para pet') e algumas terminam em espaço ('cao ') — `\\b` depois de
    espaço tem sentido invertido e quebraria justamente essas.

    ⚠️ O FECHO PRECISA DE GÊNERO, NÃO SÓ PLURAL. A primeira versão aceitava só
    `(?:es|s)?` e isso quebrou 12 produtos de casa no inbox real: a lista tem
    'organizador' e o produto diz 'organizadorA' ('caixas organizadoras',
    'Sapateira Organizadora'). Português tem gênero, e o fim livre antigo cobria
    isso por acidente. Achado pelo `diff_roteador.py` — nos MEUS 18 testes não
    aparecia, porque fui eu que escolhi os 18.
    """
    partes = []
    for p in sorted((_sem_acento(x.lower()) for x in palavras), key=len, reverse=True):
        if p and p[-1].isalnum():
            # as|os|es antes de a|o|s: alternância casa a primeira que serve.
            partes.append(re.escape(p) + r"(?:as|os|es|a|o|s)?(?![a-z0-9])")
        else:
            partes.append(re.escape(p))     # termina em espaço/pontuação
    return re.compile(r"\b(?:" + "|".join(partes) + r")")


# ═════════════════════════════════════════════════════════════════════════════
# O BICHO COMO ENFEITE (05/09/2026)
# ─────────────────────────────────────────────────────────────────────────────
# PET roda primeiro de propósito ('shampoo para cachorro' tem que vencer
# 'shampoo'). O efeito colateral é que qualquer produto que MENCIONE um bicho
# vira pet, mesmo quando o bicho é o FORMATO e não o destinatário:
#
#   'Sutiã Adesivo ... tipo Orelha De Coelho'          → foi pro @topshoppet_
#   'Naninha Para Bebê ... Coelho ou Cachorro Pelúcia' → foi pro @topshoppet_
#
# Um sutiã no perfil de pet não flopa só aquele post: desalinha a conta, que é
# exatamente o que precisa de 1.000 seguidores coerentes.
#
# ⚠️ SÃO FRASES LITERAIS, NÃO HEURÍSTICA. Cobrem os casos que a gente VIU. O que
# escapar cai na camada 2 (IA), que é onde palpite deve morar — já apanhei aqui
# de inventar wordlist sem medir.
_VETO_PET = (
    "orelha de coelho", "orelhas de coelho", "orelha de gato", "orelhas de gato",
    "formato de gato", "formato de cachorro", "formato de coelho",
    "estampa de gato", "estampa de cachorro", "estampa de coelho",
    "para bebe", "para bebes", "para recem nascido", "para recem-nascido",
)

# ...mas estes são pet sem discussão e VENCEM o veto acima. Sem isto, uma
# 'caminha para pet do bebê' sairia de pet por causa de um 'para bebe'.
_PET_CERTO = (
    "racao", "coleira", "petshop", "pet shop", "tapete higienico", "arranhador",
    "caixa de areia", "antipulga", "veterinario", "para pet", "para cachorro",
    "para gato", "para caes", "para cao", "para gatos", "para cachorros",
)


_RX_PET = _compilar(_PET)
_RX_BELEZA = _compilar(_BELEZA)
_RX_TECH = _compilar(_TECH)
_RX_CASA = _compilar(_CASA)
_RX_MODA = _compilar(_MODA)
_RX_VETO_PET = _compilar(_VETO_PET)
_RX_PET_CERTO = _compilar(_PET_CERTO)


def _por_palavra_chave(texto: str) -> str:
    """Nicho pela lista, ou "" quando nenhuma bate.

    ⚠️ O DESEMPATE AGORA É ESPECIFICIDADE (o termo mais longo vence), com a
    ORDEM ANTIGA valendo só quando dá empate. Mudou em 05/09/2026 e o motivo
    é este:

        'Saboneteira Dispenser ... Para Sabonete Líquido' → ia pra BELEZA

    'saboneteira' está na lista de CASA e 'sabonete' na de BELEZA. As duas
    casam de verdade (o nome tem as duas palavras), e a ordem dava a vitória
    pra beleza — sempre, pra toda saboneteira que existe.

    Olhando as regras que os comentários das listas já documentavam, TODAS
    continuam valendo com especificidade, porque a ordem sempre foi um
    substituto tosco disto:
      'shampoo para cachorro' → 'cachorro'(8) vence 'shampoo'(7)   = pet ✔
      'roupa de cama'         → 'roupa de cama'(13) vence 'roupa'  = casa ✔
      'escova para pet'       → frase inteira vence 'escova'       = pet ✔
    """
    if _RX_PET.search(texto):
        # o bicho era enfeite? então NÃO devolve pet — deixa as outras listas
        # (e, se nenhuma bater, a IA) decidirem. Ver _VETO_PET lá em cima.
        if _RX_PET_CERTO.search(texto) or not _RX_VETO_PET.search(texto):
            return "pet"

    # ⚠️ COMPRIMENTO NÃO É ESPECIFICIDADE, é só um proxy — e um proxy que erra
    # por pouco. No inbox real, 'Varal de Parede ... Roupas Pesadas' foi pra
    # MODA porque 'roupas'(6) ganhou de 'varal'(5) POR UMA LETRA. 'varal' é
    # específico, 'roupa' é genérico; o comprimento disse o contrário.
    #
    # Então o comprimento só derruba a ordem curada quando é DECISIVAMENTE
    # maior. Abaixo da margem, vale a ordem — que é curadoria humana e já foi
    # justificada nos comentários das listas.
    #
    # MARGEM=3 sai dos casos reais, não de teoria:
    #   saboneteira(11) x sabonete(8)  → 3, precisa virar  → casa ✔
    #   roupa de cama(13) x roupa(5)   → 8, vira folgado   → casa ✔
    #   varal(5) x roupas(6)           → 1, NÃO vira       → casa ✔
    MARGEM = 3
    achados = []
    for nicho, rx in (("beleza", _RX_BELEZA), ("tech", _RX_TECH),
                      ("casa", _RX_CASA), ("moda", _RX_MODA)):
        m = rx.search(texto)
        if m:
            achados.append((nicho, len(m.group(0))))
    if not achados:
        return ""
    primeiro, tam_primeiro = achados[0]          # o que a ordem antiga daria
    for nicho, tam in achados[1:]:
        if tam >= tam_primeiro + MARGEM:
            primeiro, tam_primeiro = nicho, tam
    return primeiro


# ═════════════════════════════════════════════════════════════════════════════
# CAMADA 2 — IA, só pro que a lista não reconheceu
# ═════════════════════════════════════════════════════════════════════════════
def _ia_ligada() -> bool:
    return os.getenv("ROTEADOR_IA", "1").strip().lower() in ("1", "true", "sim")


def _ler_cache() -> dict:
    try:
        return json.loads(CACHE_IA.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _gravar_cache(cache: dict):
    try:
        CACHE_IA.parent.mkdir(parents=True, exist_ok=True)
        CACHE_IA.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    except Exception as erro:
        log.warning("não consegui gravar o cache do roteador: %s", str(erro)[:120])


def _chave_cache(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()[:120]


def _por_ia(texto: str) -> str:
    """Pergunta o nicho pro Gemini. Cacheia por produto — cada nome é perguntado
    uma vez só. Devolve "" se a IA estiver desligada, sem chave ou se falhar."""
    if not _ia_ligada():
        return ""

    chave = _chave_cache(texto)
    cache = _ler_cache()
    if chave in cache:
        return cache[chave]

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        log.warning("GEMINI_API_KEY ausente — roteamento fica só nas palavras-chave")
        return ""

    try:
        from google import genai
        cli = genai.Client(api_key=api_key)
        prompt = (
            "Classifique o produto abaixo em UM destes nichos, respondendo APENAS "
            "a palavra, em minusculas, sem pontuacao:\n"
            "- pet     (cachorro, gato e outros animais: racao, coleira, cama, "
            "brinquedo, higiene do animal)\n"
            "- beleza  (cuidado pessoal, cabelo, pele, unhas, maquiagem, perfume)\n"
            "- tech    (eletronicos, celular e acessorios, audio, games, gadgets)\n"
            "- casa    (cozinha, organizacao, limpeza, cama/mesa/banho, decoracao)\n"
            "- moda    (roupa, calcado, bolsa, joia/bijuteria e acessorio de vestir)\n"
            "- geral   (qualquer outra coisa, ou se ficar em duvida)\n\n"
            "Na duvida entre dois, escolha o uso PRINCIPAL do produto.\n"
            # ⚠️ estas 3 regras existem porque são os empates que a lista de
            # palavras erra, e a IA só é chamada pro que a lista NÃO resolveu:
            "Se for PARA ANIMAL, e pet — mesmo que seja shampoo, escova ou cama.\n"
            "Roupa de CAMA e de BANHO e casa, nao e moda.\n"
            "Relogio e pulseira INTELIGENTES sao tech; os comuns sao moda.\n\n"
            f"Produto: {texto[:200]}\n"
        )
        r = cli.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"parts": [{"text": prompt}]}],
        )
        bruto = (getattr(r, "text", "") or "").strip().lower()
        achado = ""
        for n in _NICHOS_VALIDOS:
            if n in bruto:
                achado = n
                break
        if not achado:
            log.warning("IA devolveu nicho irreconhecivel (%r) para %r", bruto[:40], chave)
            return ""

        cache[chave] = achado
        _gravar_cache(cache)
        return achado
    except Exception as erro:
        log.warning("IA falhou no roteamento (%s: %s) — fica nas palavras-chave",
                    type(erro).__name__, str(erro)[:140])
        return ""


# ═════════════════════════════════════════════════════════════════════════════
def carregar_contas() -> dict:
    try:
        return json.loads(CONTAS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"_default": {
            "nicho": "geral",
            "handle": os.environ.get("TOPSHOP_HANDLE", "@topshop.__"),
            "instagram_user_id": os.environ.get("INSTAGRAM_USER_ID", ""),
            "facebook_page_id": os.environ.get("FACEBOOK_PAGE_ID", ""),
            "page_token_env": "FACEBOOK_PAGE_TOKEN",
            "youtube": "",
        }}


def nicho_do_produto_detalhado(nome: str, categoria: str = "") -> tuple:
    """(nicho, quem_decidiu) — 'palavra-chave', 'ia' ou 'padrao'."""
    texto = _sem_acento(f"{categoria} {nome}".lower())

    nicho = _por_palavra_chave(texto)
    if nicho:
        return nicho, "palavra-chave"

    nicho = _por_ia(texto)
    if nicho:
        return nicho, "ia"

    return "geral", "padrao"


def nicho_do_produto(nome: str, categoria: str = "") -> str:
    return nicho_do_produto_detalhado(nome, categoria)[0]


def conta_do_produto(nome: str, categoria: str = "") -> dict:
    """Retorna a conta (dict) do nicho do produto, com o token JÁ resolvido do
    .env (campo 'token'). Cai no _default se o nicho não tiver conta."""
    contas = carregar_contas()
    nicho, quem = nicho_do_produto_detalhado(nome, categoria)

    escolhida = contas.get(nicho)
    if escolhida is None and nicho != "geral":
        # nicho reconhecido mas sem conta própria (hoje: 'casa'). Vai pra geral,
        # mas fica no log — é esse volume que justifica abrir uma conta nova.
        log.info("nicho '%s' (via %s) não tem conta própria — indo pra geral: %r",
                 nicho, quem, nome[:60])
    conta = dict(escolhida or contas.get("_default") or {})
    conta.setdefault("nicho", nicho)
    conta["nicho_detectado"] = nicho
    conta["decidido_por"] = quem

    env = conta.get("page_token_env", "")
    conta["token"] = os.environ.get(env, "") if env else ""
    return conta


def conta_para_json(conta: dict) -> dict:
    """Só o que o meta_uploader precisa ao lado do vídeo — SEM o token (fica no
    .env; o uploader resolve pelo page_token_env)."""
    return {
        "nicho": conta.get("nicho", "geral"),
        "handle": conta.get("handle", ""),
        "instagram_user_id": conta.get("instagram_user_id", ""),
        "facebook_page_id": conta.get("facebook_page_id", ""),
        "page_token_env": conta.get("page_token_env", ""),
        "youtube": conta.get("youtube", ""),
    }


def main():
    args = sys.argv[1:]

    if args and args[0] == "--lote":
        caminho = Path(args[1]) if len(args) > 1 else None
        if not caminho or not caminho.exists():
            print("uso: python3 roteador_contas.py --lote produtos.txt")
            return 1
        produtos = [l.strip() for l in caminho.read_text(encoding="utf-8").splitlines()
                    if l.strip() and not l.startswith("#")]
        print(f"{'PRODUTO':<52} {'NICHO':<8} {'CONTA':<22} DECIDIU")
        print("─" * 104)
        contagem = {}
        for p in produtos:
            c = conta_do_produto(p)
            nicho = c.get("nicho_detectado", "?")
            contagem[nicho] = contagem.get(nicho, 0) + 1
            print(f"{p[:52]:<52} {nicho:<8} {c.get('handle', '?'):<22} {c.get('decidido_por')}")
        print("─" * 104)
        print("resumo:", ", ".join(f"{k}={v}" for k, v in sorted(contagem.items())))
        return 0

    nome = " ".join(args) or "produto teste"
    c = conta_do_produto(nome)
    print(f"produto  : {nome}")
    print(f"nicho    : {c.get('nicho_detectado')}  (decidido por {c.get('decidido_por')})")
    print(f"conta    : {c.get('nicho')} → {c.get('handle')}")
    print(f"ig_id    : {c.get('instagram_user_id')}  | page: {c.get('facebook_page_id')}")
    print(f"token    : {'✅ resolvido' if c.get('token') else '⚠️ vazio (' + c.get('page_token_env','') + ' não está no .env)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
