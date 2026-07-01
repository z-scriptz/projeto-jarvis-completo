# creative_engine/scene_prompt_builder.py
# Gera prompts de geração IA (text-to-video / text-to-image) por cena.
#
# Em vez de hardcodar 10 categorias × 5 cenas = 50 prompts, monta por camadas:
#   prompt = [descritor visual da categoria] + [ação da cena] + [sufixo de estilo]
#
# 100% determinístico, sem Gemini. Manutenível: nova categoria = 1 entrada.
#
# Reusa a detecção de categoria do Copy Adapter pra consistência.

from typing import Optional

try:
    from creative_engine.copy_adapter import detectar_categoria
    _COPY_OK = True
except Exception:
    _COPY_OK = False


# Sufixo de estilo comum a TODAS as cenas (formato TikTok vertical, realista)
ESTILO_SUFIXO = (
    "vertical 9:16 format, realistic, soft natural lighting, clean modern aesthetic, "
    "high quality, short social media clip, no text overlay"
)

# Descritor visual por categoria: cenário + sujeito + produto (em inglês = melhor pra IA)
CATEGORIA_VISUAL = {
    "fitness_moda": {
        "setting": "elegant young woman at home near a mirror, fashion-ad style",
        "produto": "slimming waist shaper belt worn under neutral clothing",
        "vibe":    "confident, aspirational, tasteful (no nudity, no exaggeration)",
    },
    "fitness_geral": {
        "setting": "person in a bright minimalist room, wellness vibe",
        "produto": "compact massage / wellness device",
        "vibe":    "relaxing, relief, self-care",
    },
    "beleza_skincare": {
        "setting": "woman in a clean bright bathroom, beauty-routine setting",
        "produto": "skincare product being applied to face",
        "vibe":    "fresh, glowing, gentle",
    },
    "beleza_maquiagem": {
        "setting": "tidy vanity desk with soft lighting",
        "produto": "makeup organizer holding cosmetics neatly",
        "vibe":    "stylish, organized, aesthetic",
    },
    "tech_limpeza": {
        "setting": "modern home office desk close-up",
        "produto": "mini handheld vacuum cleaning a keyboard",
        "vibe":    "satisfying, practical, clean",
    },
    "tech_acessorio": {
        "setting": "modern desk setup, tech flat-lay",
        "produto": "tech accessory organizing the workspace",
        "vibe":    "clean, productive, minimalist",
    },
    "iluminacao_led": {
        "setting": "cozy bedroom at night",
        "produto": "colorful LED lights transforming the room ambiance",
        "vibe":    "atmospheric, vibrant, cozy",
    },
    "casa_utilidade": {
        "setting": "clean modern home interior",
        "produto": "practical home utility product solving a small problem",
        "vibe":    "helpful, satisfying, tidy",
    },
    "cozinha_utensilio": {
        "setting": "bright modern kitchen counter",
        "produto": "kitchen gadget speeding up food prep",
        "vibe":    "fun, fast, appetizing",
    },
    "pet_acessorio": {
        "setting": "cozy living room with a happy pet",
        "produto": "pet accessory in use",
        "vibe":    "warm, playful, heartwarming",
    },
}

# Descritor visual genérico (fallback se categoria não detectada)
CATEGORIA_VISUAL_FALLBACK = {
    "setting": "clean modern setting, product-focused",
    "produto": "the product in use",
    "vibe":    "appealing, trustworthy, social-media friendly",
}

# Ação por cena — o que ESTÁ acontecendo no clipe (independe do produto)
CENA_ACAO = {
    "dor":       ("show the problem/frustration the product solves, "
                  "person looking slightly unsatisfied before using it"),
    "demo":      ("clear close-up demonstration of the product being used, "
                  "hands interacting with it, showing how it works"),
    "resultado": ("show the happy result after using the product, "
                  "satisfied person, before/after feeling"),
    "close":     ("clean product close-up on a neutral background, "
                  "highlighting texture and details, e-commerce style"),
    "cta":       ("hand pointing to / presenting the product on a clean surface, "
                  "inviting call-to-action vibe"),
}


# Cenas que são SOBRE O PRODUTO (não sobre a pessoa) — usam setting neutro
CENAS_PRODUTO_FOCO = {"close", "cta"}

# Setting product-focused (override pra close/cta)
SETTING_PRODUTO = "clean neutral background, product hero shot, studio lighting"


def construir_prompt(produto: str, cena: str,
                      categoria: Optional[str] = None,
                      nicho: str = "") -> str:
    """
    Monta o prompt de geração IA pra uma cena específica.

    prompt = descritor_categoria(setting + produto + vibe) + ação_cena + estilo

    Cenas close/cta focam NO PRODUTO (setting neutro), não na pessoa.
    """
    if categoria is None and _COPY_OK:
        categoria = detectar_categoria(produto)

    visual = CATEGORIA_VISUAL.get(categoria or "", CATEGORIA_VISUAL_FALLBACK)
    acao = CENA_ACAO.get(cena, "show the product in an appealing way")

    # close/cta: setting neutro focado no produto
    if cena in CENAS_PRODUTO_FOCO:
        setting = SETTING_PRODUTO
    else:
        setting = visual["setting"]

    prompt = (
        f"{setting}, featuring {visual['produto']} "
        f"(product: {produto}). "
        f"Scene goal: {acao}. "
        f"Mood: {visual['vibe']}. "
        f"{ESTILO_SUFIXO}."
    )
    return " ".join(prompt.split())


def construir_prompts_todas_cenas(produto: str, cenas: list[str],
                                   nicho: str = "") -> dict:
    """
    Retorna {cena: prompt} pra cada cena pedida.
    Detecta categoria UMA vez (eficiência).
    """
    categoria = detectar_categoria(produto) if _COPY_OK else None
    return {cena: construir_prompt(produto, cena, categoria=categoria, nicho=nicho)
            for cena in cenas}, (categoria or "(nenhuma)")