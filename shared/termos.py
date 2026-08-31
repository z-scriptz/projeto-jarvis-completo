# shared/termos.py
# TERMO DE BUSCA — transforma nome cru de produto em algo que a Shopee acha.
#
# Vive aqui porque dois agentes precisam da MESMA regra, e regra de busca que
# diverge entre eles vira bug difícil: a repescagem acha o produto, o validador
# não, e o mesmo item aparece vivo num lugar e morto no outro.
#
# Quem usa:
#   repescagem    procura de novo o produto cujo anúncio morreu
#   validar_fila  refaz a busca quando o nome cheio não devolve nada
#
# Medido na fila real de 03/08: de 15 buscas que voltaram VAZIAS, 13 tinham
# mais de 5 palavras, com mediana de 16. Ninguém procura na Shopee com 16
# palavras — e a relevância exige que a MAIORIA das palavras do termo apareça
# no título do candidato, então termo comprido reprova até o produto certo.

import re

# Lixo de título de vídeo. Não é nome de produto e só atrapalha a busca —
# "Capa transparente borda cromada shorts" não existe na Shopee.
LIXO_BUSCA = {"shorts", "short", "reels", "reel", "tiktok", "viral", "achadinho",
              "achadinhos", "promo", "oferta", "barato", "compre", "link", "bio"}

# Preposição e artigo não identificam produto nenhum e ainda gastam vaga das
# 5 palavras que a busca aceita.
LIGACAO = {"de", "da", "do", "dos", "das", "para", "pra", "com", "em", "no",
           "na", "nos", "nas", "e", "o", "a", "os", "as", "um", "uma", "por",
           # possessivo também não identifica produto — e "NOSSOS" sozinho
           # segurava "SIGA NOSSOS CANAIS" de pé como se fosse nome válido
           "nosso", "nossos", "nossa", "nossas", "meu", "meus", "minha",
           "minhas", "seu", "sua", "seus", "suas"}

# ⚠️ VERBO DE CHAMADA NO COMEÇO — é convite, não produto. Contar palavras não
# resolve esta classe: "SIGA NOSSOS CANAIS" tem três palavras e passava por
# uma só delas ("NOSSOS") não estar em nenhuma lista. O sinal aqui é a FORMA
# da frase, não o vocabulário dela: nome de produto não começa com imperativo.
#
# Medido em 29/08: essa mensagem estava na fila do hunter com link real, 181
# vendas e 13% de comissão — classificada `mina_ouro`, o que a punha no TOPO
# do ranking novo do grupo.
CHAMADA_INICIAL = {"siga", "sigam", "segue", "seguir", "inscreva", "inscrevam",
                   "inscreve", "participe", "participa", "entre", "entra",
                   "clique", "clica", "acesse", "acessa", "confira", "confere",
                   "aproveite", "aproveita", "corre", "chama", "manda",
                   "compartilhe", "compartilha", "marque", "marca", "curta"}

# Quantas palavras mandar pra busca.
PALAVRAS_BUSCA = 5

# Abaixo disto não dá pra cortar mais nada sem sobrar termo vazio.
PALAVRAS_MIN = 2


# Palavras que descrevem o LUGAR do produto no funil, não o produto. Um nome
# feito só delas é rótulo de planilha, não achadinho: "Produto com busca alta".
GENERICO = {"produto", "produtos", "item", "itens", "busca", "buscas", "alta",
            "alto", "baixa", "baixo", "potencial", "bom", "boa", "oferta",
            "ofertas", "promo", "promocao", "promoção", "achado", "achadinho",
            "achadinhos", "link", "novo", "nova", "top", "vendido", "vendidos",
            "mil", "viral", "tendencia", "tendência", "destaque", "video",
            "vídeo", "curto", "curta", "desconto", "barato", "barata",
            # ⚠️ CHAMADA DE CANAL — a fila do hunter vem de grupos do Telegram,
            # e mensagem de divulgação do próprio canal entra nela como se
            # fosse produto. Medido em 29/08: "SIGA NOSSOS CANAIS" estava na
            # fila com link real, 181 vendas e 13% de comissão, classificado
            # `mina_ouro` — ou seja, o ranking novo o mandaria pro TOPO e o
            # grupo receberia isso como achadinho. Três palavras úteis, nenhum
            # filtro pegava.
            # 📌 Acrescentar palavra aqui é seguro por construção: o nome só é
            # reprovado quando NADA sobra. "Suporte de Canal" continua passando
            # por causa de "suporte" — some o nome que é SÓ chamada.
            "siga", "sigam", "segue", "seguir", "canal", "canais",
            "inscreva", "inscrevam", "participe", "comunidade", "membros",
            "telegram", "whatsapp", "zap", "vip", "exclusivo", "gratis",
            "grátis", "clique", "confira", "acesse", "aproveite"}


def nome_de_produto_ruim(nome: str) -> bool:
    """O nome serve pra mostrar a um CLIENTE? Conservador de propósito.

    Nasceu do teste seco do WhatsApp em 04/08, que ia mandar pro grupo:

        *Produto com busca alta*
        💰 R$ 1600,00

    Isso é rótulo interno que vazou pra fila. Nenhum filtro pegava: o
    `_e_lixo` do telegram_radar só olha selo de venda e aviso de grupo, e o
    `_nome_ruim` da vitrine só reprova nome com menos de 3 palavras — e esse
    tem 4. Cada superfície tinha meia regra; nenhuma tinha esta.

    A pergunta certa não é "o nome é curto?" e sim **"sobra alguma palavra que
    diga O QUE É a coisa?"**. Tira ligação ("com", "para") e palavra de funil
    ("produto", "busca", "alta") e vê o que resta:

        "Produto com busca alta"          → resta 0  → ruim
        "Kit 4 Essência Aromatizador"     → resta 4  → serve
        "Gloss Labial"                    → resta 2  → serve
        "Cafeteira"                       → resta 1, mas longa → serve

    Uma palavra só passa se tiver ≥5 letras. O corte foi medido, não chutado:
    com 6 o "Tênis" era reprovado, e tênis é produto. Com 5 passam Tênis,
    Bolsa, Calça e reprovam Fone, Capa, Copo — que sozinhos não dizem o
    suficiente pra virar achadinho.

    Vale pra QUEM PUBLICA, não pra quem coleta: aqui, na dúvida, pular um
    produto bom custa muito menos que mandar lixo pro grupo do cliente.
    """
    n = (nome or "").strip()
    if len(n) < 3:
        return True
    if re.match(r"^https?://", n, re.I) or re.match(r"^[\w-]+\.\w{2,}/", n):
        return True
    if re.search(r"\bmil\s+vendidos?\b", n, re.I):
        return True
    # começa com verbo de chamada → é convite, não produto (ver CHAMADA_INICIAL)
    primeira = re.sub(r"[^\wÀ-ÿ]", "", n.split()[0] if n.split() else "").lower()
    if primeira in CHAMADA_INICIAL:
        return True

    uteis = []
    for p in re.sub(r"[^\w\s]", " ", n).split():
        b = p.lower()
        if b in LIGACAO or b in GENERICO or b in LIXO_BUSCA:
            continue
        if b.isdigit():          # "4", "10" descrevem quantidade, não produto
            continue
        uteis.append(p)
    if not uteis:
        return True
    if len(uteis) == 1:
        return len(re.sub(r"[^A-Za-zÀ-ÿ]", "", uteis[0])) < 5
    return False


def termo_de_busca(bruto: str) -> str:
    """Transforma o nome cru num termo que a Shopee encontra.

    Três defeitos vistos na VPS, os três causando 'não achei o produto':

    1. cauda de YouTube: 'Capa transparente borda cromada shorts'.
    2. corte no meio da palavra: o slug tem 40 caracteres, então sobra
       'Fones De O', 'Porcelana Ko', 'Estreito Ces'. Palavra picada não casa
       com nada e ainda conta contra a relevância.
    3. título de anúncio inteiro: 'Kit Pó Compacto Tira Brilho (6 opções) +
       Base 2 em 1 (8 opções) + Blush Duo Coradinha Rosada Fast Glam'. A busca
       devolve zero — vira 'Kit Pó Compacto Tira Brilho'.
    """
    t = re.sub(r"[^\w\s]", " ", bruto or "")
    palavras = [p for p in t.split() if p]
    # a última pode ser um pedaço de palavra, cortesia do corte em 40 chars
    if len(palavras) > PALAVRAS_MIN and len(palavras[-1]) <= 3:
        palavras.pop()
    uteis = []
    for p in palavras:
        b = p.lower()
        if b in LIXO_BUSCA or b in LIGACAO or len(p) < 2:
            continue                         # 'de'/'para' só gastam vaga
        uteis.append(p)
        if len(uteis) >= PALAVRAS_BUSCA:
            break                            # termo curto acha; termo longo não
    return " ".join(uteis)


# ── nome que o cliente vê ──────────────────────────────────────────────────
# ⚠️ NASCEU DO MINERADOR DE WHATSAPP (31/08). Com o reetiquetar funcionando, o
# nome que entra na fila passou a ser o TÍTULO CRU DA SHOPEE, escrito pelo
# vendedor pra ranquear na busca dele — não pra ser lido:
#
#   "Coloração Semi Permanente TRUSS LOURO MEDIO PEROLA 7.89 60G ⚠️ ATENÇÃO –
#    LEIA ANTES DE COMPRAR"
#   "MEDOOSI-Apontador De Lápis Elétrico USB Automático/Material De Papelaria
#    Para De Cor Mecânica Crianças Artistas - 8028"
#
# Isso vai pro grupo do WhatsApp e pro site do jeito que está. `nome_de_produto_ruim`
# reprova rótulo interno ("Produto com busca alta"), mas estes aqui não são
# ruins — são REAIS e mal escritos, e reprovar jogaria fora produto bom.
#
# 📌 Reprovar e limpar são respostas diferentes pra problemas diferentes. Aqui o
# certo é limpar: cortar o recado do vendedor, tirar o SKU do fim e parar num
# tamanho que cabe numa mensagem.
AVISOS_VENDEDOR = (
    "atenção", "atencao", "leia antes", "leia com atenção", "envio imediato",
    "envio em ate", "envio em até", "frete grátis", "frete gratis",
    "últimas unidades", "ultimas unidades", "compre agora", "promoção imperdível",
    "promocao imperdivel", "aproveite", "garanta o seu", "pronta entrega",
    "12x sem juros", "menor preço", "menor preco",
)

_RE_SKU = re.compile(r"[\s\-–—]+[-–—]?\s*\d{3,6}\s*$")
_RE_ESPACO = re.compile(r"\s+")


def _sem_acento(s: str) -> str:
    """Comparação de texto sem depender de acento — o vendedor escreve
    "ATENÇÃO", "ATENCAO" e "Atenção" na mesma vitrine."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn")


def nome_para_cliente(nome: str, limite: int = 70) -> str:
    """O título da loja, legível numa mensagem.

    Corta no primeiro aviso de vendedor, tira SKU do fim e encurta em borda de
    palavra. Nunca devolve vazio: se a limpeza comer tudo, volta o original
    encurtado — nome feio ainda vende, nome vazio não.
    """
    t = _RE_ESPACO.sub(" ", (nome or "").strip())
    if not t:
        return ""
    original = t

    # 1) o ⚠️ é a fronteira mais confiável: vendedor nenhum põe emoji de alerta
    #    no meio do nome do produto
    for marca in ("⚠️", "⚠", "🚨", "❗"):
        if marca in t:
            t = t.split(marca, 1)[0]

    # 2) avisos escritos: corta na PRIMEIRA ocorrência, comparando sem acento
    baixo = _sem_acento(t.lower())
    corte = len(t)
    for aviso in AVISOS_VENDEDOR:
        pos = baixo.find(_sem_acento(aviso))
        if pos > 0:                      # > 0: aviso no começo é o nome todo
            corte = min(corte, pos)
    t = t[:corte]

    # 3) SKU/código no fim ("- 8028", "--3926")
    t = _RE_SKU.sub("", t)
    t = t.strip(" -–—/|,;:.")

    if len(t) < 8:                       # a limpeza exagerou
        t = original
    if len(t) > limite:
        t = t[:limite].rsplit(" ", 1)[0].rstrip(" -–—/|,;:.") + "…"
    return t.strip()
