# shared/categorias.py
# NORMALIZA A CATEGORIA DO POST para o nicho de uma CONTA.
#
# POR QUE ISSO EXISTE (08/08/2026)
# ────────────────────────────────
# A primeira medição de verdade (ledger_publicados) mostrou a categoria
# fragmentada em 14 valores para 4 contas:
#
#   beleza 66 · beleza_maquiagem 24 · beleza_skincare 14      → é tudo beleza
#   tech 122 · tech_acessorio 19                              → é tudo tech
#   casa 14 · casa_utilidade 2 · cozinha_utensilio 5 · ...    → é tudo casa
#
# Agrupar por `categoria` crua SUBCONTA beleza em 40%. Se a análise rodasse
# assim, a conclusão seria "beleza performa menos" — e a estratégia mudaria por
# causa de um artefato de NOMENCLATURA, não de desempenho. Erro de medição que
# vira decisão é pior que não medir: a gente confia nele.
#
# A REGRA É POR PREFIXO, e isso é escolha: categoria nova que apareça amanhã
# (`beleza_cabelo`, `tech_audio`) já cai no lugar certo sem ninguém editar este
# arquivo. Só o que NÃO segue o padrão precisa de exceção explícita abaixo.
#
# O que não casa com nada devolve "" — e "" aparece na contagem como buraco, em
# vez de virar "geral" e sumir no meio. Contar errado calado foi exatamente o
# defeito que a logo, a sessão do Instagram e o pareamento de slug tiveram.

import re

# Os nichos que têm CONTA. Manter alinhado com contas.json.
NICHOS = ("geral", "beleza", "tech", "casa", "moda", "pet")

# Categorias que não começam com o nome do nicho. Só as exceções moram aqui —
# o resto é resolvido pelo prefixo.
EXCECOES = {
    "cozinha": "casa",
    "iluminacao": "casa",
    "iluminação": "casa",
    "decoracao": "casa",
    "decoração": "casa",
    "utilidade": "casa",
    "organizacao": "casa",
    "organização": "casa",
    "maquiagem": "beleza",
    "skincare": "beleza",
    "cabelo": "beleza",
    "perfume": "beleza",
    "gadget": "tech",
    "acessorio": "tech",      # "acessorio" solto historicamente é de tech
    "acessório": "tech",
    "eletronico": "tech",
    "eletrônico": "tech",
    "roupa": "moda",
    "calcado": "moda",
    "calçado": "moda",
    "bolsa": "moda",
    "relogio": "moda",
    "relógio": "moda",
    "fitness": "geral",       # fitness não tem conta; cai no guarda-chuva
    "pet": "pet",
}


def _limpa(t: str) -> str:
    t = (t or "").strip().lower()
    t = re.sub(r"[\s/\-]+", "_", t)
    return re.sub(r"_+", "_", t).strip("_")


def normalizar(categoria: str) -> str:
    """Categoria crua -> nicho de conta. "" quando não dá pra decidir.

        "beleza_skincare"   -> "beleza"
        "tech_acessorio"    -> "tech"
        "cozinha_utensilio" -> "casa"
        "fitness_moda"      -> "geral"   (o 1º segmento manda)
        ""                  -> ""
        "quinquilharia"     -> ""

    O PRIMEIRO segmento manda. "fitness_moda" é um produto fitness que por
    acaso é vestível — vai pra geral, não pra moda. Deixar o último segmento
    decidir faria "casa_tech" virar tech, o que está errado pelo mesmo motivo.
    """
    c = _limpa(categoria)
    if not c:
        return ""
    partes = c.split("_")
    cabeca = partes[0]
    if cabeca in NICHOS:
        return cabeca
    if cabeca in EXCECOES:
        return EXCECOES[cabeca]
    # o primeiro segmento não decidiu; tenta os seguintes antes de desistir
    for p in partes[1:]:
        if p in NICHOS:
            return p
        if p in EXCECOES:
            return EXCECOES[p]
    return ""


def resumir(categorias) -> dict:
    """{nicho: quantidade} já normalizado. Chave "" = não classificado, e ela
    aparece de propósito: buraco escondido é buraco que ninguém conserta."""
    fora = {}
    for c in categorias:
        n = normalizar(c)
        fora[n] = fora.get(n, 0) + 1
    return fora
