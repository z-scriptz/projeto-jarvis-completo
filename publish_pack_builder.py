# creative_engine/publish_pack_builder.py
# Monta o "pacote de publicação" de um produto: legendas por plataforma +
# hashtags, prontos pra você COPIAR e postar (manual por enquanto).
#
# FILOSOFIA (o meio-termo inteligente antes do upload automático):
#   Gerar vídeo + legenda + hashtags numa pasta pronto_para_postar/ economiza
#   ~80% do trabalho manual SEM arriscar suas contas com automação de upload.
#   Quando o upload automático vier (fase futura), ele só lê esta pasta.
#
# Cada plataforma tem seu tom:
#   - TikTok:    curto, gancho, 3-5 hashtags
#   - Instagram: um pouco mais descritivo, 8-12 hashtags, emojis ok
#   - Shopee:    foco em produto/benefício, sem gíria, call pra loja
#   - YouTube:   título + descrição (Shorts)
#
# 100% determinístico, sem custo. Reusa roteiro + categoria + hook.

import re
from pathlib import Path
from typing import Optional

try:
    from creative_engine.hook_builder import construir_hook, cta_curto
    _HOOK_OK = True
except Exception:
    _HOOK_OK = False

# Hashtags base por categoria (PT-BR, focadas em descoberta/afiliado)
HASHTAGS_CATEGORIA = {
    "tech_limpeza": ["#limpeza", "#gadget", "#achadinhos", "#organizacao",
                     "#casa", "#tecnologia", "#praticidade", "#minivacuum"],
    "cozinha_utensilio": ["#cozinha", "#receitas", "#praticidade", "#achadinhos",
                          "#utensilios", "#cozinhar", "#foodprep", "#cortador"],
    "fitness_moda": ["#moda", "#look", "#cinturafina", "#autoestima",
                     "#modeladora", "#fitness", "#achadinhos", "#estilo"],
    "beleza_skincare": ["#skincare", "#beleza", "#autocuidado", "#peleperfeita",
                        "#rotina", "#glow", "#achadinhos", "#cosmeticos"],
    "casa_utilidade": ["#casa", "#organizacao", "#achadinhos", "#utilidades",
                       "#lar", "#praticidade", "#decor", "#donadecasa"],
    "iluminacao_led": ["#led", "#decor", "#setup", "#iluminacao",
                       "#quartoaesthetic", "#achadinhos", "#vibes", "#casa"],
    "pet_acessorio": ["#pet", "#cachorro", "#gato", "#petlovers",
                      "#achadinhos", "#petshop", "#aupair", "#dog"],
}

HASHTAGS_BASE = ["#achadinhosshopee", "#promo", "#ofertas", "#linknabio"]


def _slug(produto: str) -> str:
    s = re.sub(r"[^\w\s-]", "", (produto or "").lower())
    return re.sub(r"[\s-]+", "_", s).strip("_")


def _hashtags(categoria: str, n: int) -> list:
    tags = list(HASHTAGS_CATEGORIA.get(categoria, []))
    tags += HASHTAGS_BASE
    # dedup preservando ordem
    vistos, out = set(), []
    for t in tags:
        if t not in vistos:
            vistos.add(t); out.append(t)
    return out[:n]


def construir_pacote(produto: str, roteiro: dict,
                      categoria: str = "") -> dict:
    """
    Monta o pacote de publicação a partir do roteiro + categoria.

    roteiro: dict com 'frases' (lista) — a narração.
    Retorna dict com as legendas por plataforma e hashtags.
    """
    frases = roteiro.get("frases") or roteiro.get("blocos") or []
    if frases and isinstance(frases[0], dict):
        frases = [f.get("texto", "") for f in frases]

    # Hook e CTA (reusa o hook_builder se disponível)
    if _HOOK_OK:
        hook = construir_hook(produto, legenda_inicial=frases[0] if frases else "")
        cta = cta_curto(produto)
    else:
        hook = "OLHA ISSO"
        cta = "LINK NA BIO"

    # Corpo da legenda = junção das frases do roteiro (a "história" do vídeo)
    corpo = " ".join(frases).strip()

    tags_ig = _hashtags(categoria, 12)
    tags_tk = _hashtags(categoria, 5)

    # TikTok: curto, gancho na frente
    legenda_tiktok = f"{hook}! {corpo}\n{cta} 👇\n\n" + " ".join(tags_tk)

    # Instagram: descritivo + mais hashtags no fim
    legenda_instagram = (
        f"{hook} ✨\n\n{corpo}\n\n{cta} (link na bio)\n\n"
        + " ".join(tags_ig)
    )

    # Shopee: foco no produto e benefício, sem gíria, tom de loja
    legenda_shopee = (
        f"{produto}\n\n{corpo}\n\n"
        f"✅ Garanta o seu agora pelo link da loja.\n"
        f"✅ Envio rápido e produto de qualidade."
    )

    # YouTube Shorts: título + descrição
    titulo_youtube = f"{hook} | {produto} #shorts"
    descricao_youtube = (
        f"{corpo}\n\n{cta}\n\n" + " ".join(tags_ig)
    )

    return {
        "produto": produto,
        "categoria": categoria,
        "hook": hook,
        "cta": cta,
        "legenda_tiktok": legenda_tiktok,
        "legenda_instagram": legenda_instagram,
        "legenda_shopee": legenda_shopee,
        "titulo_youtube": titulo_youtube,
        "descricao_youtube": descricao_youtube,
        "hashtags": tags_ig,
    }


def salvar_pacote(pacote: dict, dir_destino: Path) -> dict:
    """
    Escreve os arquivos do pacote numa pasta (pronto_para_postar/produto/).
    Retorna dict {nome_arquivo: caminho}.
    """
    dir_destino.mkdir(parents=True, exist_ok=True)
    arquivos = {
        "legenda_tiktok.txt":    pacote["legenda_tiktok"],
        "legenda_instagram.txt": pacote["legenda_instagram"],
        "legenda_shopee.txt":    pacote["legenda_shopee"],
        "titulo_youtube.txt":    pacote["titulo_youtube"],
        "descricao_youtube.txt": pacote["descricao_youtube"],
        "hashtags.txt":          " ".join(pacote["hashtags"]),
    }
    salvos = {}
    for nome, conteudo in arquivos.items():
        try:
            (dir_destino / nome).write_text(conteudo, encoding="utf-8")
            salvos[nome] = str(dir_destino / nome)
        except Exception:
            pass
    return salvos