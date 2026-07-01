# creative_engine/copy_adapter.py
# Copy Adapter v1 — escolhe textos por cena adequados ao produto/nicho.
#
# Problema que resolve:
#   Editor tinha texto hardcoded universal ('Olha isso limpando',
#   'Mini portátil e prático'). Funcionava pra Mini Aspirador mas
#   vazava pra Cinto Modelador, Lâmpada LED, etc. Bug de generalização.
#
# Estratégia em 3 camadas (em ordem de prioridade):
#   1) Plano do produto: se tem 'copy_por_cena' explícito, usa
#   2) Categoria detectada: dicionário curado por categoria
#   3) Fallback genérico: textos universais inofensivos
#
# Filosofia:
#   - NUNCA chama Gemini (zero custo, zero latência)
#   - 100% determinístico (mesmo produto → mesmo copy)
#   - Aberto pra extensão: adicionar categoria nova = 5 linhas
#   - Plano é fonte de verdade quando existe (Gemini gerou contextual)
#
# Uso programático:
#   from creative_engine.copy_adapter import escolher_copy_por_cena
#   textos = escolher_copy_por_cena(produto, plano=plano_dict, cenas=['dor','demo',...])
#   # textos = {'dor': 'Texto pra dor', 'demo': '...', ...}

import re
from typing import Optional

# =================================================================
# CATEGORIAS DE PRODUTO + TEXTOS POR CENA
# =================================================================
# Cada categoria tem 5 textos (dor/demo/resultado/close/cta).
# Categoria é detectada por keywords no nome do produto.

CATEGORIAS_COPY = {
    # ─────────── BELEZA / FITNESS / MODA ───────────
    "fitness_moda": {
        "keywords": ["cinto modelador", "modelador", "waist", "slim",
                       "shaper", "modela", "afinar cintura", "redutor",
                       "compressao", "compressão"],
        "textos": {
            "dor":       "Quer modelar o look sem sofrer? ✨",
            "demo":      "Ajusta fácil e dá sustentação",
            "resultado": "Cintura mais marcada na hora",
            "close":     "Discreto por baixo da roupa",
            "cta":       "Link na bio pra garantir o seu 💖",
        },
    },
    "fitness_geral": {
        "keywords": ["massageador", "massagem", "alongamento", "yoga",
                       "treino", "academia", "fitness", "musculacao",
                       "musculação", "exercicio", "exercício"],
        "textos": {
            "dor":       "Cansado da tensão no corpo? 😩",
            "demo":      "Veja como funciona na prática",
            "resultado": "Alívio em poucos minutos ✨",
            "close":     "Compacto, prático e portátil",
            "cta":       "Garanta o seu no link da bio 💪",
        },
    },
    "beleza_skincare": {
        "keywords": ["esfoliante", "skincare", "creme", "facial",
                       "rosto", "pele", "limpeza facial", "tonico", "tônico",
                       "serum", "sérum", "hidratante", "antirrugas",
                       "anti-rugas", "anti-aging"],
        "textos": {
            "dor":       "Sua pele merece mais cuidado ✨",
            "demo":      "Aplicação simples, resultado real",
            "resultado": "Pele renovada e radiante 💖",
            "close":     "Fórmula gentil pro dia a dia",
            "cta":       "Adicione ao seu skincare 🌸",
        },
    },
    "beleza_maquiagem": {
        "keywords": ["maquiagem", "organizador acrilico", "organizador acrílico",
                       "batom", "base", "pincel", "paleta", "primer",
                       "porta maquiagem", "porta-maquiagem"],
        "textos": {
            "dor":       "Cansada da bagunça no penteadeira? 😅",
            "demo":      "Tudo organizado em um só lugar",
            "resultado": "Look pronto em segundos ✨",
            "close":     "Estiloso e funcional 💄",
            "cta":       "Pegue o seu no link da bio 💖",
        },
    },

    # ─────────── CASA / TECH ───────────
    "tech_limpeza": {
        "keywords": ["aspirador", "mini aspirador", "limpa teclado",
                       "limpador", "vacuum"],
        "textos": {
            "dor":       "Seu teclado tá sujo? 😳",
            "demo":      "Olha isso limpando em segundos",
            "resultado": "Resultado em segundos ✨",
            "close":     "Mini, portátil e prático",
            "cta":       "Corre no link da bio pra garantir o seu",
        },
    },
    "tech_acessorio": {
        "keywords": ["suporte notebook", "suporte laptop", "stand",
                       "organizador cabos", "organizador de cabos",
                       "hub usb", "carregador", "powerbank", "power bank",
                       "fone", "headset"],
        "textos": {
            "dor":       "Setup bagunçado atrapalhando? 😩",
            "demo":      "Veja como organiza tudo",
            "resultado": "Mesa limpa, foco no que importa ✨",
            "close":     "Discreto e funcional",
            "cta":       "Garante o seu no link da bio 🔥",
        },
    },
    "iluminacao_led": {
        "keywords": ["led", "lâmpada", "lampada", "fita led", "cortina led",
                       "luz", "iluminacao", "iluminação", "sensor de movimento"],
        "textos": {
            "dor":       "Quer transformar o ambiente? ✨",
            "demo":      "Instalação simples, efeito incrível",
            "resultado": "Vibe nova em segundos 🌟",
            "close":     "Controle total na palma da mão",
            "cta":       "Link na bio pra você levar 💡",
        },
    },
    "casa_utilidade": {
        "keywords": ["adesivo vedante", "vedante", "umidificador",
                       "porta tempero", "porta-tempero", "organizador cozinha",
                       "organizador armario", "organizador armário"],
        "textos": {
            "dor":       "Problema chato em casa? 🛠️",
            "demo":      "Solução simples e rápida",
            "resultado": "Resolvido em minutos ✨",
            "close":     "Prático e durável",
            "cta":       "Garante o seu no link 🏠",
        },
    },

    # ─────────── COZINHA ───────────
    "cozinha_utensilio": {
        "keywords": ["cortador", "ralador", "espremedor", "fatiador",
                       "descascador", "panela", "frigideira"],
        "textos": {
            "dor":       "Cansado de perder tempo na cozinha? ⏰",
            "demo":      "Veja como agiliza tudo",
            "resultado": "Refeição pronta em minutos ✨",
            "close":     "Prático e fácil de limpar",
            "cta":       "Link na bio pra cozinhar melhor 🍳",
        },
    },

    # ─────────── PET ───────────
    "pet_acessorio": {
        "keywords": ["pet", "cao", "cachorro", "cão", "gato", "racao", "ração",
                       "coleira", "comedouro", "bebedouro", "brinquedo pet"],
        "textos": {
            "dor":       "Seu pet merece o melhor 🐾",
            "demo":      "Olha que fofo usando",
            "resultado": "Pet feliz, dono feliz ❤️",
            "close":     "Seguro e confortável",
            "cta":       "Surpreenda seu pet 🐶",
        },
    },
}

# Textos genéricos finais (último recurso)
FALLBACK_GENERICO = {
    "dor":       "Você precisa ver isso 👀",
    "demo":      "Olha como funciona",
    "resultado": "O resultado é incrível ✨",
    "close":     "Prático e funcional",
    "cta":       "Link na bio pra garantir o seu 🔥",
}


# =================================================================
# DETECÇÃO DE CATEGORIA
# =================================================================

def _normalizar(s: str) -> str:
    """Lowercase, remove acentos básicos, normaliza espaços."""
    if not isinstance(s, str):
        return ""
    s = s.lower()
    return re.sub(r"\s+", " ", s).strip()


def detectar_categoria(produto: str, nicho: str = "") -> Optional[str]:
    """
    Detecta categoria pelo nome do produto. Retorna chave de CATEGORIAS_COPY
    ou None se nada bater.
    """
    produto_n = _normalizar(produto)
    if not produto_n:
        return None

    # Procura por melhor match: categoria com keyword mais longa que casa
    melhor = (None, 0)
    for categoria, info in CATEGORIAS_COPY.items():
        for kw in info["keywords"]:
            kw_n = _normalizar(kw)
            if kw_n in produto_n:
                if len(kw_n) > melhor[1]:
                    melhor = (categoria, len(kw_n))
    return melhor[0]


# =================================================================
# EXTRAÇÃO DO PLANO
# =================================================================

def _extrair_copy_do_plano(plano: dict, cenas: list[str]) -> dict:
    """
    Tenta extrair textos por cena do plano.

    Procura, em ordem:
      1. plano['copy_por_cena'][cena]
      2. plano['cenas'][cena]['texto'] ou ['legenda']
      3. plano['textos_por_cena'][cena]
      4. plano['legenda'] (texto único: usa pra 'dor' como hook)
      5. plano['cta'] (usa pra 'cta')
      6. plano['hook'] (usa pra 'dor')

    Returns: dict só com cenas que CONSEGUIU extrair (pode estar incompleto)
    """
    if not isinstance(plano, dict):
        return {}

    saida = {}

    # 1) copy_por_cena direto
    cpc = plano.get("copy_por_cena") or plano.get("textos_por_cena")
    if isinstance(cpc, dict):
        for cena in cenas:
            v = cpc.get(cena)
            if isinstance(v, str) and v.strip():
                saida[cena] = v.strip()

    # 2) plano['cenas'][cena]['texto']
    cenas_plano = plano.get("cenas")
    if isinstance(cenas_plano, dict):
        for cena in cenas:
            if cena in saida:
                continue
            entrada = cenas_plano.get(cena)
            if isinstance(entrada, dict):
                v = entrada.get("texto") or entrada.get("legenda") or entrada.get("copy")
                if isinstance(v, str) and v.strip():
                    saida[cena] = v.strip()

    # 3) Hook/CTA do plano são sinais valiosos pra cenas específicas
    hook = plano.get("hook")
    if isinstance(hook, str) and hook.strip() and "dor" in cenas and "dor" not in saida:
        saida["dor"] = hook.strip()

    cta = plano.get("cta")
    if isinstance(cta, str) and cta.strip() and "cta" in cenas and "cta" not in saida:
        saida["cta"] = cta.strip()

    return saida


# =================================================================
# API PÚBLICA
# =================================================================

def escolher_copy_por_cena(produto: str,
                             plano: Optional[dict] = None,
                             cenas: Optional[list[str]] = None,
                             nicho: str = "") -> dict:
    """
    Retorna dict {cena: texto} pra cada cena solicitada.

    Estratégia em 3 camadas (mais específico ganha):
      1. Plano explícito (Gemini gerou contextual)
      2. Categoria detectada (dicionário curado deste módulo)
      3. Fallback genérico (textos universais inofensivos)

    Args:
        produto: nome do produto
        plano:   dict do plano (opcional). Se tiver 'copy_por_cena',
                  'cenas[X].texto', 'hook' ou 'cta', são usados.
        cenas:   lista de cenas a preencher. Default: 5 essenciais.
        nicho:   pra desempate quando categoria for ambígua (opcional)

    Returns: {cena: texto} pronto pra usar no editor.
    """
    cenas = cenas or ["dor", "demo", "resultado", "close", "cta"]

    # Camada 1: plano
    copy_do_plano = _extrair_copy_do_plano(plano or {}, cenas)

    # Camada 2: categoria
    categoria = detectar_categoria(produto, nicho)
    if categoria:
        textos_cat = CATEGORIAS_COPY[categoria]["textos"]
    else:
        textos_cat = {}

    # Camada 3: fallback
    saida = {}
    fontes_usadas = {}  # debug: qual camada respondeu cada cena
    for cena in cenas:
        if cena in copy_do_plano:
            saida[cena] = copy_do_plano[cena]
            fontes_usadas[cena] = "plano"
        elif cena in textos_cat:
            saida[cena] = textos_cat[cena]
            fontes_usadas[cena] = f"categoria:{categoria}"
        else:
            saida[cena] = FALLBACK_GENERICO.get(cena, "")
            fontes_usadas[cena] = "fallback"

    # Anexa metadado pra debug (Editor pode logar)
    saida["_fontes"] = fontes_usadas
    saida["_categoria_detectada"] = categoria or "(nenhuma)"
    return saida


def descrever_decisao(produto: str, plano: Optional[dict] = None,
                       nicho: str = "") -> str:
    """
    Retorna string explicando qual estratégia foi usada (útil pra logs).
    """
    copy_do_plano = _extrair_copy_do_plano(plano or {}, ["dor","demo","resultado","close","cta"])
    categoria = detectar_categoria(produto, nicho)
    partes = []
    if copy_do_plano:
        partes.append(f"plano supre {len(copy_do_plano)} cena(s)")
    if categoria:
        partes.append(f"categoria='{categoria}'")
    if not partes:
        partes.append("fallback genérico (categoria não detectada)")
    return " + ".join(partes)