# creative_engine/hook_builder.py
# Gera o HOOK visual (gancho) do vídeo — texto curto e chamativo que aparece
# nos primeiros ~2s pra fazer a pessoa PARAR de rolar (assiste sem som).
#
# PROBLEMA QUE RESOLVE:
#   O hook automático usava a 1ª frase da narração inteira. Aí a legenda da
#   fala mostrava a MESMA frase no mesmo momento → texto duplicado, amador.
#
# CORREÇÃO (v2):
#   Antes, TODO vídeo saía com "VOCE PRECISA VER". Causa: produtos sem categoria
#   detectada (eletro/geral/tech puro) caíam no HOOK_FALLBACK, que SEMPRE
#   retornava o índice 0. Agora:
#     • escolha ALEATÓRIA (random.choice) na categoria E no fallback;
#     • bancos de hook bem ampliados (8-10 por categoria);
#     • cobertura das categorias que furavam: eletro, tech, geral.
#
# REGRA:
#   HOOK    = 2-5 palavras, agressivo, NÃO é igual à legenda. Faz parar.
#   LEGENDA = acompanha a narração (outro módulo). Explica.
#   São funções diferentes — não devem repetir.
#
# Sem custo, sem IA. Reusa a detecção de categoria do Copy Adapter.

import re
import json
import random
from pathlib import Path
from typing import Optional

try:
    from creative_engine.copy_adapter import detectar_categoria
    _COPY_OK = True
except Exception:
    _COPY_OK = False

# ── Biblioteca de hooks (frases fortes) — arquivo JSON ao lado deste módulo ──
_BIBLIOTECA_PATH = Path(__file__).resolve().parent / "hooks_biblioteca.json"
# memória dos hooks usados recentemente (evita repetir no feed)
_RECENTES_PATH = Path(__file__).resolve().parent.parent / "shared" / "content_plans" / "hooks_recentes.json"
_RECENTES_MEMORIA = 40          # quantos hooks recentes lembrar
_biblioteca_cache = None

# Famílias que o detector atual reporta → nicho da biblioteca nova
_FAMILIA_PARA_NICHO = {
    "casa_utilidade": "casa", "iluminacao_led": "casa",
    "cozinha_utensilio": "cozinha",
    "tech_acessorio": "tech", "tech_limpeza": "tech",
    "beleza_skincare": "beleza", "beleza_maquiagem": "beleza",
    "pet_acessorio": "pets",
    "fitness_geral": "academia", "fitness_moda": "moda",
    # aliases diretos
    "casa": "casa", "cozinha": "cozinha", "tech": "tech", "eletro": "tech",
    "beleza": "beleza", "pet": "pets", "fitness": "academia", "moda": "moda",
    "led": "casa", "iluminacao": "casa",
}

# Nichos novos que o detector de família NÃO cobre — detecção por palavra-chave
_NICHO_KEYWORDS_EXTRA = [
    (("carro", "moto ", "automot", "pneu", "volante", "farol", "garagem",
      "veicul", "capacete", "carreta", "caminhon"), "auto"),
    (("game", "gamer", "console", "xbox", "playstation", "ps5", "ps4",
      "joystick", "headset gamer"), "games"),
    (("celular", "smartphone", "iphone", "android", "capinha", "capa de celular",
      "pelicula", "película", "suporte veicular"), "celular"),
    (("presente", "gift", "aniversario", "aniversário", "namorad"), "presentes"),
]


def _carregar_biblioteca() -> Optional[dict]:
    """Lê e cacheia a biblioteca de hooks (JSON). None se não existir/inválida."""
    global _biblioteca_cache
    if _biblioteca_cache is not None:
        return _biblioteca_cache or None
    try:
        dados = json.loads(_BIBLIOTECA_PATH.read_text(encoding="utf-8"))
        if isinstance(dados, dict) and dados.get("nichos"):
            _biblioteca_cache = dados
            return dados
    except Exception:
        pass
    _biblioteca_cache = {}   # marca "já tentou" (não fica relendo)
    return None


def _ler_recentes() -> list:
    try:
        return json.loads(_RECENTES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _registrar_recente(hook: str):
    try:
        recentes = _ler_recentes()
        recentes.append(hook)
        recentes = recentes[-_RECENTES_MEMORIA:]
        _RECENTES_PATH.parent.mkdir(parents=True, exist_ok=True)
        _RECENTES_PATH.write_text(json.dumps(recentes, ensure_ascii=False),
                                  encoding="utf-8")
    except Exception:
        pass   # memória é bônus; nunca quebra a geração do hook


def _nicho_do_produto(produto: str, categoria_hint: str = "") -> Optional[str]:
    """Descobre o nicho da biblioteca pro produto (auto/games/celular por
    palavra-chave; senão mapeia a família detectada)."""
    p = _normalizar(produto)
    for kws, nicho in _NICHO_KEYWORDS_EXTRA:
        if any(k in p for k in kws):
            return nicho
    fam = _detectar_categoria(produto, categoria_hint)
    if fam and fam in _FAMILIA_PARA_NICHO:
        return _FAMILIA_PARA_NICHO[fam]
    return None


def _escolher_hook_biblioteca(pool: list, evitar_norm: str) -> Optional[str]:
    """Sorteia da lista evitando: (a) igual à legenda, (b) usados recentemente.
    Se tudo estiver 'gasto', relaxa a regra de recentes."""
    recentes = set(_ler_recentes())
    frescos = [h for h in pool
               if _normalizar(h) != evitar_norm and h not in recentes]
    if not frescos:
        frescos = [h for h in pool if _normalizar(h) != evitar_norm]
    if not frescos:
        return None
    escolha = random.choice(frescos)
    _registrar_recente(escolha)
    return escolha


def _escolher_gatilho(produto: str, bib: dict) -> Optional[str]:
    """Pontua o produto pelos 'sinais_produto' e escolhe o GATILHO psicológico
    mais forte (com desempate aleatório). Sem sinal → gatilho aleatório.
    É o que deixa o hook 'combinar' com o produto em vez de ser sorteado seco."""
    gatilhos = bib.get("gatilhos") or {}
    if not gatilhos:
        return None
    sinais = bib.get("sinais_produto") or {}
    p = _normalizar(produto)
    scores = {}
    for gat, palavras in sinais.items():
        if gat not in gatilhos:
            continue
        s = sum(1 for kw in palavras if kw in p)
        if s:
            scores[gat] = s
    if scores:
        topo = max(scores.values())
        candidatos = [g for g, v in scores.items() if v == topo]
        return random.choice(candidatos)
    # sem sinal claro → sorteia um gatilho (mantém variedade)
    return random.choice(list(gatilhos.keys()))

# Fallback interno de detecção (não depende do copy_adapter).
# Inclui famílias que o copy_adapter NÃO cobre (eletro, tech genérico) pra
# essas pararem de cair no fallback fixo.
_CATEGORIA_KEYWORDS = [
    (("cinto modelador", "modelador", "slim", "shaper", "waist", "cinta modeladora"), "fitness_moda"),
    (("massageador", "massagem", "cervical", "fitness", "academia", "treino", "creatina", "whey"), "fitness_geral"),
    (("esfoliante", "skincare", "creme facial", "tonico", "serum", "hidratante facial",
      "protetor solar", "sabonete", "colageno", "dove", "wella", "truss"), "beleza_skincare"),
    (("maquiagem", "organizador acrilico", "batom", "paleta", "porta maquiagem"), "beleza_maquiagem"),
    (("aspirador", "limpa teclado", "vacuum", "robo aspirador", "robô aspirador"), "tech_limpeza"),
    (("suporte notebook", "organizador cabos", "hub usb", "powerbank", "power bank",
      "fone", "headset", "mouse", "teclado", "webcam", "carregador", "controle",
      "gabinete", "monitor", "impressora", "niimbot", "smartwatch", "celular",
      "gamer", "redmagic", "snapdragon", "console", "xbox", "playstation"), "tech_acessorio"),
    (("led", "lampada", "lâmpada", "fita led", "cortina led", "iluminacao",
      "lustre", "luminaria", "luminária", "espelho touch"), "iluminacao_led"),
    (("vedante", "umidificador", "porta tempero", "organizador cozinha",
      "pote hermetico", "pote hermético", "organizador", "guarda-roupa",
      "escrivaninha", "prateleira", "cabide", "mesa", "cadeira", "rede",
      "adega", "vaso sanitario", "vaso sanitário"), "casa_utilidade"),
    (("cortador", "ralador", "espremedor", "fatiador", "descascador",
      "chaleira", "cafeteira", "panela", "frigideira", "garrafa termica",
      "garrafa térmica", "saleiro", "azeiteiro", "balança", "balanca",
      "liquidificador", "seladora", "air fryer", "fritadeira", "micro-ondas",
      "microondas", "frigobar", "geladeira", "frost free"), "cozinha_utensilio"),
    (("coleira", "comedouro", "bebedouro pet", "brinquedo pet", "escova pet",
      "catnip", "racao", "ração"), "pet_acessorio"),
]

# Mapeia categorias que o sistema reporta mas que não têm banco próprio
# (ex.: o narration_script_builder/ia_scene_generator chamam de "eletro",
# "tech", "cozinha", "geral") → família de hook correspondente.
_ALIAS_CATEGORIA = {
    "eletro":   "tech_acessorio",
    "tech":     "tech_acessorio",
    "cozinha":  "cozinha_utensilio",
    "casa":     "casa_utilidade",
    "beleza":   "beleza_skincare",
    "fitness":  "fitness_geral",
    "moda":     "fitness_moda",
    "pet":      "pet_acessorio",
    "led":      "iluminacao_led",
    "iluminacao": "iluminacao_led",
}

# Hooks curtos por categoria (2-5 palavras). MAIÚSCULAS de propósito —
# chama mais atenção no feed. SEM emoji (Arial Bold, legibilidade).
# Bancos ampliados: agora 8-10 por categoria pra dar variedade real no feed.
HOOKS_CATEGORIA = {
    "fitness_moda": [
        "MARCA A CINTURA",
        "OLHA QUE DISCRETO",
        "CINTURA NA HORA",
        "O SEGREDO DAS BLOGUEIRAS",
        "SOME POR BAIXO DA ROUPA",
        "MODELA NA HORA",
        "AUTOESTIMA LA EM CIMA",
        "NINGUEM PERCEBE",
        "VESTE MELHOR NA HORA",
    ],
    "fitness_geral": [
        "ALIVIO NA HORA",
        "SEU CORPO AGRADECE",
        "TENSAO? RESOLVIDO",
        "ADEUS DOR NAS COSTAS",
        "RELAXA EM MINUTOS",
        "ISSO MUDOU MEU DIA",
        "TESTEI E APROVEI",
        "VICIANTE DEMAIS",
        "PRECISAVA DISSO ONTEM",
    ],
    "beleza_skincare": [
        "PELE RENOVADA",
        "OLHA ESSE GLOW",
        "SUA PELE MERECE",
        "RESULTADO EM DIAS",
        "ADEUS PELE OPACA",
        "ISSO MUDOU MINHA PELE",
        "GLOW DE VERDADE",
        "TODO MUNDO PERGUNTA",
        "VICIEI NISSO",
    ],
    "beleza_maquiagem": [
        "CHEGA DE BAGUNCA",
        "TUDO ORGANIZADO",
        "MAKE NA MAO",
        "ADEUS BANCADA BAGUNCADA",
        "ACHEI TUDO NA HORA",
        "ISSO SALVOU MINHA MAKE",
        "PRECISAVA DISSO",
        "MUDOU MINHA ROTINA",
    ],
    "tech_limpeza": [
        "OLHA ISSO",
        "CANTINHOS SUJOS?",
        "LIMPA EM SEGUNDOS",
        "SUJEIRA ESCONDIDA",
        "SATISFACAO PURA",
        "ISSO E VICIANTE",
        "OLHA O RESULTADO",
        "NUNCA MAIS SUJO",
        "PRATICO DEMAIS",
    ],
    "tech_acessorio": [
        "SETUP LIMPO",
        "ADEUS BAGUNCA",
        "ISSO MUDOU MEU SETUP",
        "PARECE COISA DO FUTURO",
        "TECNOLOGIA QUE ASSUSTA",
        "GADGET VICIANTE",
        "VALE CADA CENTAVO",
        "POTENCIA ABSURDA",
        "TODO MUNDO QUER UM",
        "ISSO E OUTRO NIVEL",
    ],
    "iluminacao_led": [
        "MUDA TUDO",
        "OLHA ESSA VIBE",
        "AMBIENTE NOVO",
        "TRANSFORMA O QUARTO",
        "VIBE DE OUTRO NIVEL",
        "SEM REFORMA NENHUMA",
        "ISSO MUDOU MEU QUARTO",
        "CLIMA NA HORA",
        "TODO MUNDO ELOGIA",
    ],
    "casa_utilidade": [
        "ISSO RESOLVE MUITO",
        "ADEUS PROBLEMA",
        "COMO EU VIVIA SEM?",
        "SOLUCAO QUE FALTAVA",
        "PRATICO E BARATO",
        "ISSO FACILITA TUDO",
        "VIROU ESSENCIAL AQUI",
        "POR QUE NAO COMPREI ANTES?",
        "RESOLVEU NA HORA",
    ],
    "cozinha_utensilio": [
        "CHEGA DE PERDER TEMPO",
        "OLHA A PRATICIDADE",
        "RAPIDO DEMAIS",
        "ISSO MUDOU MINHA COZINHA",
        "COMIDA PRONTA NUM PISCAR",
        "NUNCA MAIS NA FACA",
        "PRATICIDADE QUE FALTAVA",
        "QUEM USA NAO VOLTA",
        "VICIEI NISSO",
    ],
    "pet_acessorio": [
        "SEU PET MERECE",
        "OLHA QUE FOFO",
        "PET FELIZ",
        "ELE AMOU NA HORA",
        "ISSO FACILITOU TUDO",
        "TODO PET PRECISA",
        "MEU PET NAO LARGA",
        "PRATICO PRA CARAMBA",
    ],
}

# Fallback geral AMPLIADO (era a fonte do "VOCE PRECISA VER" eterno).
# Agora é um banco variado, escolhido aleatoriamente como qualquer outro.
HOOK_FALLBACK = [
    "VOCE PRECISA VER",
    "OLHA ISSO",
    "NAO PERDE ISSO",
    "ISSO VIRALIZOU",
    "TODO MUNDO QUER",
    "ACHADINHO DO DIA",
    "VALE MUITO A PENA",
    "OLHA QUE ACHADO",
    "PRECISA CONHECER",
    "ISSO E TOP DEMAIS",
]

# CTA final curto
CTA_CURTO = "LINK NA BIO"


def _normalizar(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _resolver_familia(categoria: Optional[str]) -> Optional[str]:
    """Resolve uma categoria reportada pra uma família com banco de hook."""
    if not categoria:
        return None
    cat = categoria.strip().lower()
    if cat in HOOKS_CATEGORIA:
        return cat
    if cat in _ALIAS_CATEGORIA:
        return _ALIAS_CATEGORIA[cat]
    return None


def _detectar_categoria(produto: str, categoria_hint: str = "") -> Optional[str]:
    # 0) dica explícita (ex.: vinda do plano/roteiro) tem prioridade
    fam = _resolver_familia(categoria_hint)
    if fam:
        return fam

    # 1) copy_adapter
    if _COPY_OK:
        try:
            c = detectar_categoria(produto)
            if c:
                return c
        except Exception:
            pass

    # 2) keywords internas (cobre eletro/tech/cozinha por nome do produto)
    p = _normalizar(produto)
    melhor = (None, 0)
    for keywords, cat in _CATEGORIA_KEYWORDS:
        for kw in keywords:
            if kw in p and len(kw) > melhor[1]:
                melhor = (cat, len(kw))
    return melhor[0]


def _escolher_diferente(candidatos: list, evitar_norm: str) -> Optional[str]:
    """
    Sorteia um hook da lista que NÃO seja basicamente igual à legenda inicial.
    Embaralha pra dar variedade; retorna None se a lista esvaziar.
    """
    opcoes = [c for c in candidatos if _normalizar(c) != evitar_norm]
    if not opcoes:
        return None
    return random.choice(opcoes)


def construir_hook(produto: str,
                   legenda_inicial: str = "",
                   plano: Optional[dict] = None) -> str:
    """
    Retorna um hook curto (2-5 palavras) pra este produto.

    Escolha ALEATÓRIA a cada chamada (varia o feed). Garante que o hook NÃO
    é igual à legenda inicial (evita duplicação com a narração).

    Prioridade:
      1. plano['hook'] (se existir e for curto)
      2. categoria detectada → sorteia da lista da categoria
      3. fallback geral → sorteia da lista ampliada

    Args:
        produto:         nome do produto
        legenda_inicial: 1ª frase da narração (pra garantir que o hook difere)
        plano:           dict do plano (opcional). Aceita 'hook' e 'categoria'.
    """
    leg_norm = _normalizar(legenda_inicial)

    # 1) hook explícito do plano (se curto o suficiente pra ser gancho)
    if isinstance(plano, dict):
        h = plano.get("hook")
        if isinstance(h, str) and h.strip() and len(h.split()) <= 6:
            if _normalizar(h) != leg_norm:
                return h.strip()

    # dica de categoria do plano (ex.: ia_scene_generator grava "eletro")
    categoria_hint = ""
    if isinstance(plano, dict):
        categoria_hint = str(plano.get("categoria") or "")

    # 2) BIBLIOTECA 2.0 — pontua o produto → escolhe o GATILHO → escolhe a frase
    bib = _carregar_biblioteca()
    if bib:
        nicho = _nicho_do_produto(produto, categoria_hint)
        universais = bib.get("universais", [])
        pool = []
        # 2a) gatilho psicológico (frases que "combinam" com o produto)
        gat = _escolher_gatilho(produto, bib)
        if gat:
            pool += bib.get("gatilhos", {}).get(gat, [])
        # 2b) tempera com o nicho (relevância do tema) + universais de reserva
        if nicho and nicho in bib.get("nichos", {}):
            pool += bib["nichos"][nicho]
        if not pool:
            pool = list(universais)
        escolhido = _escolher_hook_biblioteca(pool, leg_norm)
        if escolhido:
            return escolhido

    # 3) categoria → banco curto antigo (rede de segurança)
    categoria = _detectar_categoria(produto, categoria_hint)
    if categoria and categoria in HOOKS_CATEGORIA:
        escolhido = _escolher_diferente(HOOKS_CATEGORIA[categoria], leg_norm)
        if escolhido:
            return escolhido

    # 4) fallback geral → sorteia (não mais o índice 0 fixo)
    escolhido = _escolher_diferente(HOOK_FALLBACK, leg_norm)
    if escolhido:
        return escolhido

    # todos batem com a legenda (praticamente impossível) → 1º fallback
    return HOOK_FALLBACK[0]


def cta_curto(produto: str = "") -> str:
    """CTA final curto, diferente da legenda da última frase."""
    return CTA_CURTO