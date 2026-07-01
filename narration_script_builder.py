# creative_engine/narration_script_builder.py
# Gera roteiro NARRADO (pra ouvir) de 12-18s por produto/categoria.
#
# CASCATA DE INTELIGÊNCIA (cada camada cai pra próxima se falhar):
#   1. IA (Gemini)        -> roteiro UNICO, persuasivo, fala o nome do produto
#   2. Templates variados -> varios ganchos por categoria, sorteia 1 + injeta nome
#   3. Fallback generico  -> nunca fica sem roteiro
#
# Estrutura: [gancho forte] -> [solucao/demo] -> [beneficio] -> [CTA]
# O nome do produto SEMPRE aparece, e os ganchos VARIAM.

import re
import os
import json
import random
from typing import Optional

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("narration_script_builder")

_COPY_IMPORT_ERRO = ""
try:
    from creative_engine.copy_adapter import detectar_categoria, inferir_nicho
    _COPY_OK = True
except Exception as _e:
    _COPY_OK = False
    _COPY_IMPORT_ERRO = f"{type(_e).__name__}: {_e}"

USAR_IA_NARRACAO = True
MARCA = "TopShop"

_CATEGORIA_KEYWORDS = [
    (("cinto modelador", "modelador", "slim", "shaper", "waist", "cinta modeladora"), "fitness_moda"),
    (("massageador", "massagem", "cervical", "fitness", "academia", "treino"), "fitness_geral"),
    (("esfoliante", "skincare", "creme facial", "tonico", "serum", "hidratante facial"), "beleza_skincare"),
    (("maquiagem", "organizador acrilico", "organizador acrílico", "batom", "paleta", "porta maquiagem"), "beleza_maquiagem"),
    (("aspirador", "limpa teclado", "vacuum"), "tech_limpeza"),
    (("suporte notebook", "suporte laptop", "organizador cabos", "hub usb", "powerbank", "fone", "headset"), "tech_acessorio"),
    (("led", "lampada", "lâmpada", "fita led", "cortina led", "iluminacao", "iluminação"), "iluminacao_led"),
    (("vedante", "umidificador", "porta tempero", "organizador cozinha", "organizador armario"), "casa_utilidade"),
    (("cortador", "ralador", "espremedor", "fatiador", "descascador", "frigideira"), "cozinha_utensilio"),
    (("coleira", "comedouro", "bebedouro pet", "brinquedo pet", "tapete higienico"), "pet_acessorio"),
]


def _detectar_categoria_interna(produto: str) -> Optional[str]:
    p = re.sub(r"\s+", " ", (produto or "").lower()).strip()
    melhor = (None, 0)
    for keywords, cat in _CATEGORIA_KEYWORDS:
        for kw in keywords:
            if kw in p and len(kw) > melhor[1]:
                melhor = (cat, len(kw))
    return melhor[0]


def _categoria_do_produto(produto: str) -> Optional[str]:
    if _COPY_OK:
        try:
            cat = detectar_categoria(produto)
            if cat:
                return cat
        except Exception:
            pass
    return _detectar_categoria_interna(produto)


# CAMADA 2 — TEMPLATES VARIADOS
VARIACOES_CATEGORIA = {
    "cozinha_utensilio": [
        ["Três segundos. É o que o {produto} leva pra picar tudo.",
         "Sem faca, sem choro, sem bagunça na cozinha.",
         "Cebola, alho, tomate — picados num apertão só.",
         "O preparo da sua comida nunca mais vai ser o mesmo.",
         "Garante o teu no link da bio!"],
        ["Para de cortar legume desse jeito!",
         "Com o {produto}, você pica tudo de uma vez.",
         "Rápido, uniforme e sem sujar meia cozinha.",
         "Praticidade que a sua rotina pedia.",
         "Corre no link da bio e pega o seu!"],
        ["Cansa de perder tempo picando tudo na faca?",
         "O {produto} resolve isso em segundos.",
         "Comida pronta mais rápido e fácil de limpar.",
         "Quem usa não volta mais pra faca.",
         "Pega o teu no link da bio!"],
    ],
    "fitness_moda": [
        ["Quer marcar a cintura na hora, por baixo de qualquer roupa?",
         "O {produto} dá sustentação e é totalmente discreto.",
         "Cintura definida na hora, sem aperto desconfortável.",
         "Ninguém vê, mas todo mundo nota a diferença.",
         "Garante o teu no link da bio!"],
        ["Esse é o segredo por baixo das roupas das blogueiras.",
         "O {produto} modela a silhueta na hora.",
         "Discreto, confortável e some por baixo do look.",
         "A autoestima muda quando a roupa veste melhor.",
         "Corre no link da bio!"],
    ],
    "fitness_geral": [
        ["Aquela tensão no corpo no fim do dia? Dá pra resolver.",
         "O {produto} alivia em poucos minutos, em casa.",
         "Compacto, prático e fácil de usar sozinho.",
         "A diferença você sente já na primeira vez.",
         "Garante o teu no link da bio!"],
        ["Seu corpo merece relaxar depois de um dia puxado.",
         "Com o {produto}, o alívio vem em minutos.",
         "Você usa quando quiser, sem depender de ninguém.",
         "É o tipo de coisa que vira hábito.",
         "Pega o teu no link da bio!"],
    ],
    "beleza_skincare": [
        ["Sua pele pede um cuidado de verdade — não enrola.",
         "O {produto} tem aplicação simples e resultado real.",
         "Em pouco tempo a pele fica renovada e radiante.",
         "Fórmula gentil pra usar todo dia.",
         "Adiciona no teu skincare pelo link da bio!"],
        ["Skincare não precisa ser complicado pra funcionar.",
         "O {produto} entrega resultado com um passo só.",
         "Pele mais bonita e saudável, dia após dia.",
         "Suave o bastante pro uso diário.",
         "Garante o teu no link da bio!"],
    ],
    "beleza_maquiagem": [
        ["Cansada da penteadeira virar bagunça?",
         "O {produto} deixa cada coisa no seu lugar.",
         "Sua make acessível e o look pronto em segundos.",
         "Estiloso e funcional ao mesmo tempo.",
         "Pega o teu no link da bio!"],
        ["Olha que diferença um organizador faz na make.",
         "O {produto} põe ordem no caos da bancada.",
         "Você acha tudo na hora e ganha tempo.",
         "Bonito o suficiente pra deixar à mostra.",
         "Corre no link da bio!"],
    ],
    "tech_limpeza": [
        ["Olha a sujeira escondida no seu teclado agora.",
         "O {produto} suga tudo isso em segundos.",
         "Portátil, prático e cabe na palma da mão.",
         "O resultado aparece na hora.",
         "Corre no link da bio pra garantir o teu!"],
        ["Seu teclado tá mais sujo do que você imagina.",
         "O {produto} resolve isso numa passada.",
         "Leve, recarregável e fácil de usar.",
         "Aquela satisfação de ver tudo limpo.",
         "Pega o teu no link da bio!"],
    ],
    "tech_acessorio": [
        ["Seu setup vive bagunçado e sem espaço?",
         "O {produto} organiza tudo de um jeito limpo.",
         "Mais mesa livre, mais foco no que importa.",
         "Discreto e funcional do jeito certo.",
         "Garante o teu no link da bio!"],
        ["Mesa organizada muda até a produtividade.",
         "Com o {produto}, cada cabo fica no lugar.",
         "Visual limpo, prático e sem nó de fios.",
         "Pequeno detalhe, grande diferença.",
         "Pega o teu no link da bio!"],
    ],
    "iluminacao_led": [
        ["Quer transformar o teu ambiente em segundos?",
         "O {produto} muda totalmente o clima do espaço.",
         "Instalação simples e um efeito que impressiona.",
         "Você controla as cores na palma da mão.",
         "Pega o teu pelo link da bio!"],
        ["Seu quarto pode ter a vibe daquele vídeo que você curtiu.",
         "O {produto} cria o clima certo na hora.",
         "Fácil de instalar e de personalizar.",
         "Ambiente novo sem reforma nenhuma.",
         "Corre no link da bio!"],
    ],
    "casa_utilidade": [
        ["Aquele probleminha chato em casa tem solução barata.",
         "O {produto} resolve de um jeito simples e rápido.",
         "Prático, durável e fácil de usar.",
         "Você vai se perguntar como vivia sem.",
         "Garante o teu no link da bio!"],
        ["Essas coisinhas que facilitam o dia fazem diferença.",
         "O {produto} é uma dessas que viram essenciais.",
         "Simples, eficiente e resolve de verdade.",
         "Custou pouco, ajudou demais.",
         "Pega o teu no link da bio!"],
    ],
    "pet_acessorio": [
        ["Seu pet merece o melhor — e você sabe disso.",
         "Olha que prático e confortável é o {produto}.",
         "Pet feliz deixa a casa toda mais leve.",
         "Seguro e pensado pra ele.",
         "Surpreende teu pet pelo link da bio!"],
        ["Quem tem pet sabe: praticidade não tem preço.",
         "O {produto} facilita a vida de vocês dois.",
         "Confortável pro bichinho, fácil pra você.",
         "Amor também é cuidar dos detalhes.",
         "Garante o teu no link da bio!"],
    ],
}

VARIACOES_FALLBACK = [
    ["Você precisa conhecer o {produto}.",
     "Olha como ele funciona na prática.",
     "Prático, simples e resolve de verdade.",
     "O resultado fala por si.",
     "Corre no link da bio pra garantir o teu!"],
    ["Esse aqui virou febre por um motivo: o {produto}.",
     "Simples de usar e útil de verdade.",
     "Daqueles que você usa e indica.",
     "Vale cada centavo.",
     "Pega o teu no link da bio!"],
]


# CAMADA 1 — IA (Gemini)
PROMPT_NARRACAO = """Você é um copywriter especialista em vídeos curtos de venda (TikTok/Reels) para marketing de afiliados.

Escreva um roteiro NARRADO (para uma voz falar) para o produto abaixo.

PRODUTO: {produto}
CATEGORIA: {categoria}

REGRAS OBRIGATÓRIAS:
- Exatamente 5 frases curtas, uma por linha.
- A 1a frase é um GANCHO FORTE (choque, número, erro comum ou promessa ousada) que prende em 2 segundos.
- Cite o nome do produto pelo menos uma vez de forma natural (ex: "esse {produto}"). NÃO cite marca nenhuma.
- Frases curtas e faladas, como um criador de conteúdo brasileiro real falaria. Nada formal.
- Crie DESEJO com um benefício concreto e específico do produto (não genérico).
- A última frase é um CTA chamando pra "link na bio".
- Tom: empolgado, persuasivo, brasileiro, informal. Use "você"/"teu".
- Total entre 35 e 50 palavras (cabe em ~12-18 segundos de fala).

Responda APENAS com as 5 frases, uma por linha, sem numeração, sem aspas, sem comentários."""


def _gerar_roteiro_ia(produto: str, categoria: str) -> Optional[list]:
    try:
        from google import genai
        from shared.config import GEMINI_VISION_MODEL
    except Exception:
        log.info("   google.genai indisponível — narração via template")
        return None

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        log.info("   GEMINI_API_KEY não definida — narração via template")
        return None

    prompt = PROMPT_NARRACAO.format(
        produto=produto, categoria=categoria or "geral")
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_VISION_MODEL,
            contents=[{"parts": [{"text": prompt}]}],
        )
        texto = (response.text or "").strip()
        if texto.startswith("```"):
            texto = "\n".join(texto.split("\n")[1:-1])
        frases = []
        for linha in texto.split("\n"):
            f = linha.strip()
            f = re.sub(r"^\s*\d+[\.\)]\s*", "", f)
            f = f.strip(' "\'-—•').strip()
            if f:
                frases.append(f)
        if len(frases) < 3:
            log.warning(f"   IA retornou roteiro curto ({len(frases)}) — template")
            return None
        frases = frases[:5]
        nome_curto = produto.split()[0].lower() if produto else ""
        if not (nome_curto and nome_curto in " ".join(frases).lower()):
            log.info("   (IA não citou o nome; ainda assim mais rica que template)")
        log.info(f"   ✨ Narração via IA (Gemini): gancho='{frases[0][:45]}...'")
        return frases
    except Exception as e:
        msg = str(e)
        if "429" in msg or "quota" in msg.lower() or "exhaust" in msg.lower():
            log.warning("   🚫 Gemini quota excedida — narração via template")
        else:
            log.warning(f"   ⚠️  IA falhou ({msg[:60]}) — narração via template")
        return None


def _nome_para_narracao(produto: str) -> str:
    p = re.sub(r"\s+", " ", (produto or "").strip())
    p = re.split(r"[-–—|,:/]", p)[0].strip()
    palavras = p.split()
    if len(palavras) > 4:
        p = " ".join(palavras[:4])
    return p or "produto"


def _aplicar_variacao(variacao: list, produto: str) -> list:
    nome = _nome_para_narracao(produto)
    return [f.replace("{produto}", nome) for f in variacao]


def construir_roteiro(produto: str,
                       plano: Optional[dict] = None,
                       usar_ia: Optional[bool] = None) -> dict:
    # 1) Roteiro explícito no plano
    if isinstance(plano, dict):
        rn = plano.get("roteiro_narrado")
        if isinstance(rn, list) and rn:
            frases = [str(f).strip() for f in rn if str(f).strip()]
            return {"frases": frases, "categoria": "(plano)", "fonte": "plano",
                    "texto_completo": " ".join(frases)}

    categoria = _categoria_do_produto(produto)
    ligar_ia = USAR_IA_NARRACAO if usar_ia is None else usar_ia

    # 2) IA (Gemini)
    if ligar_ia:
        frases_ia = _gerar_roteiro_ia(produto, categoria)
        if frases_ia:
            return {"frases": frases_ia, "categoria": categoria or "(nenhuma)",
                    "fonte": "ia:gemini", "texto_completo": " ".join(frases_ia)}

    # 3) Template variado da categoria
    variacoes = VARIACOES_CATEGORIA.get(categoria or "", None)
    if variacoes:
        variacao = random.choice(variacoes)
        frases = _aplicar_variacao(variacao, produto)
        return {"frases": frases, "categoria": categoria or "(nenhuma)",
                "fonte": f"template:{categoria}",
                "texto_completo": " ".join(frases)}

    # 4) Fallback genérico
    variacao = random.choice(VARIACOES_FALLBACK)
    frases = _aplicar_variacao(variacao, produto)
    return {"frases": frases, "categoria": categoria or "(nenhuma)",
            "fonte": "fallback", "texto_completo": " ".join(frases)}


def estimar_duracao_frase(frase: str, palavras_por_seg: float = 2.6) -> float:
    n_palavras = len(frase.split())
    return max(1.2, round(n_palavras / palavras_por_seg, 2))