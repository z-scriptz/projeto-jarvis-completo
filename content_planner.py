# agents/content_planner.py
# Agente de planejamento criativo do AgenteIA (Jarvis)
#
# Responsabilidade única: receber um produto e gerar um plano completo
# de conteúdo para TikTok/Instagram/YouTube — sem postar, sem executar.
#
# Usa Gemini para geração criativa quando disponível.
# Se a API estiver sem cota (429), gera um plano fallback local.
#
# Uso:
#   from agents.content_planner import gerar_plano_conteudo
#   plano = gerar_plano_conteudo({"produto": "Mini Aspirador de Teclado", "nicho": "Casa/Tech"})

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

from shared.logger import get_logger

log = get_logger(__name__)

# Diretório para salvar planos gerados
PLANS_DIR = Path(__file__).parent.parent / "shared" / "content_plans"

# =================================================================
# INTEGRAÇÃO SHOPEE (minera o produto e enriquece o plano com dados reais)
# =================================================================
# Antes de gerar o plano, o Jarvis minera o produto na Shopee: acha o campeão
# de maior lucro (comissão alta + nota boa), pega título/preço reais e gera o
# link de afiliado + reservas (links espelhos). Esses dados entram no plano,
# então o roteiro/legenda saem com link e preço de verdade.
#
# Import defensivo: se a Shopee não estiver disponível (sem credenciais, lib,
# etc), o planner funciona normal — só gera o plano sem os dados Shopee.
try:
    from integrations.shopee_affiliate import (
        minerar_oportunidades, gerar_link_afiliado,
    )
    _SHOPEE_OK = True
except Exception:
    _SHOPEE_OK = False

# Liga/desliga o enriquecimento Shopee (caller pode sobrescrever)
USAR_SHOPEE = True


def _enriquecer_com_shopee(produto_info: dict) -> dict:
    """
    Minera o produto na Shopee e injeta dados reais no produto_info:
      - link        → link de afiliado do campeão (a mina de ouro)
      - comissao     → comissão real (ex: "28% (R$ 27,97)")
      - preco_real   → faixa de preço do produto
      - titulo_real  → título oficial da Shopee
      - links_espelho → {principal, reserva_1, reserva_2} pra resiliência

    NÃO quebra o fluxo: se a Shopee falhar, retorna o produto_info original
    intacto (o plano sai sem os dados Shopee, como era antes).
    """
    if not (_SHOPEE_OK and USAR_SHOPEE):
        return produto_info

    nome = produto_info.get("produto", "").strip()
    if not nome:
        return produto_info

    try:
        m = minerar_oportunidades(nome)
    except Exception as e:
        log.warning(f"   ⚠️  Shopee: mineração falhou ({str(e)[:60]}) — plano sem Shopee")
        return produto_info

    if not m.get("ok"):
        log.info(f"   🛒 Shopee: sem mina de ouro pra '{nome}' ({m.get('erro','')[:50]})")
        return produto_info

    campeao = m["campeao"]
    log.info(f"   🛒 Shopee: campeão '{campeao['nome'][:40]}' "
             f"({campeao['comissao_rate']*100:.0f}%, R$ {campeao['comissao_valor']:.2f}, "
             f"{campeao['rating']:.1f}⭐)")

    # Gera os links espelhos (campeão + reservas) a partir do product_link
    links_espelho = {}
    for i, p in enumerate(m["top"]):
        origem = p.get("product_link") or p.get("offer_link")
        if not origem:
            continue
        rotulo = "principal" if i == 0 else f"reserva_{i}"
        sub = ["jarvis", re.sub(r"\W+", "", nome)[:12], rotulo]
        try:
            lk = gerar_link_afiliado(origem, sub_ids=sub)
            if lk.get("ok"):
                links_espelho[rotulo] = lk["short_link"]
        except Exception:
            pass  # se um link falhar, segue com os outros

    # Enriquece o produto_info (sem apagar o que já tinha)
    enriquecido = dict(produto_info)
    enriquecido["link"] = links_espelho.get("principal", produto_info.get("link", ""))
    enriquecido["comissao"] = (f"{campeao['comissao_rate']*100:.0f}% "
                               f"(R$ {campeao['comissao_valor']:.2f} por venda)")
    enriquecido["titulo_real"] = campeao.get("nome", "")
    preco = campeao.get("preco", 0)
    preco_max = campeao.get("preco_max", 0)
    if preco:
        enriquecido["preco_real"] = (f"R$ {preco:.2f}"
                                     + (f" a R$ {preco_max:.2f}" if preco_max > preco else ""))
    enriquecido["links_espelho"] = links_espelho
    enriquecido["shopee_score"] = campeao.get("score", 0)
    return enriquecido



# =========================
# PROMPT GEMINI
# =========================

PROMPT_PLANO = """
Você é um estrategista de conteúdo viral para redes sociais, especializado em vídeos curtos para TikTok e Instagram Reels com foco em venda de afiliados.

PRODUTO: {produto}
NICHO: {nicho}
PLATAFORMA: {plataforma}
DURAÇÃO ALVO: {duracao}
LINK AFILIADO: {link}
COMISSÃO: {comissao}

Gere um plano de conteúdo COMPLETO. Responda APENAS com JSON válido, sem texto adicional, sem markdown:

{{
  "produto": "{produto}",
  "plataforma": "{plataforma}",
  "objetivo": "venda afiliada",
  "hook": "frase de abertura impactante para prender nos primeiros 2 segundos",
  "roteiro": "roteiro completo do vídeo em formato narração, com marcações de tempo",
  "narracao": "texto exato que será narrado/falado no vídeo (pronto para TTS)",
  "cenas": [
    {{
      "tempo": "0-2s",
      "descricao": "o que aparece visualmente na tela",
      "texto_tela": "texto overlay que aparece escrito no vídeo"
    }},
    {{
      "tempo": "2-5s",
      "descricao": "...",
      "texto_tela": "..."
    }},
    {{
      "tempo": "5-8s",
      "descricao": "...",
      "texto_tela": "..."
    }},
    {{
      "tempo": "8-12s",
      "descricao": "...",
      "texto_tela": "..."
    }}
  ],
  "legenda": "legenda viral com emojis, máximo 150 caracteres",
  "hashtags": "#hashtag1 #hashtag2 #hashtag3 ... (8-12 hashtags relevantes)",
  "cta": "call to action direto e urgente (ex: 'Link na bio! Corre que tá acabando 🔥')",
  "estilo_visual": "estilo sugerido (ex: 'close-up produto com texto grande', 'unboxing rápido', 'antes/depois')",
  "musica_sugerida": "tipo de música ou trend sonora recomendada",
  "melhor_horario": "horário sugerido para postar (ex: '19h-21h')",
  "tom": "tom da comunicação (ex: 'urgente e curioso', 'divertido e leve')"
}}

REGRAS:
- Hook DEVE ser intrigante e gerar curiosidade nos primeiros 2 segundos
- Roteiro otimizado para a duração alvo ({duracao})
- Linguagem informal, direta, estilo TikTok brasileiro
- CTA deve mencionar "link na bio" ou "link nos comentários"
- Hashtags devem misturar trending + nicho específico
- Legenda curta e viral com emojis
- Cada cena deve ter descrição visual clara para produção
"""


# =========================
# GERAÇÃO VIA GEMINI
# =========================

def _gerar_plano_gemini(produto_info: dict) -> Optional[dict]:
    """
    Gera plano de conteúdo usando Gemini.
    Retorna None se a API estiver indisponível (429, sem key, etc).
    """
    try:
        from google import genai
        from google.genai import errors
        from shared.config import GEMINI_VISION_MODEL
    except ImportError:
        log.warning("google.genai não instalado — usando fallback local")
        return None

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        log.warning("GEMINI_API_KEY não definida — usando fallback local")
        return None

    prompt = PROMPT_PLANO.format(
        produto=produto_info.get("produto", "Produto Genérico"),
        nicho=produto_info.get("nicho", "Geral"),
        plataforma=produto_info.get("plataforma", "TikTok"),
        duracao=produto_info.get("duracao", "12s"),
        link=produto_info.get("link", "link na bio"),
        comissao=produto_info.get("comissao", "não informada"),
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_VISION_MODEL,
            contents=[{"parts": [{"text": prompt}]}],
        )

        texto = response.text.strip()
        if texto.startswith("```"):
            texto = "\n".join(texto.split("\n")[1:-1])

        plano = json.loads(texto)
        plano["fonte"] = "gemini"
        plano["modelo"] = GEMINI_VISION_MODEL
        log.info(f"✅ Plano gerado via Gemini: hook='{plano.get('hook', '')[:50]}...'")
        return plano

    except json.JSONDecodeError as e:
        log.warning(f"Gemini retornou JSON inválido: {e}")
        return None

    except Exception as e:
        erro_str = str(e)
        if "429" in erro_str or "RESOURCE_EXHAUSTED" in erro_str:
            log.warning(f"⚠️ Gemini sem cota (429) — usando fallback local")
        else:
            log.error(f"Erro ao chamar Gemini: {e}")
        return None


# =========================
# FALLBACK LOCAL
# =========================

def _gerar_plano_fallback(produto_info: dict) -> dict:
    """
    Gera um plano básico sem API — templates pré-definidos.
    Útil quando Gemini está sem cota ou offline.
    """
    produto    = produto_info.get("produto", "Produto")
    nicho      = produto_info.get("nicho", "Geral")
    plataforma = produto_info.get("plataforma", "TikTok")
    duracao    = produto_info.get("duracao", "12s")

    # Sanitiza nome para path de arquivo
    nome_arquivo = re.sub(r'[^\w\s-]', '', produto.lower())
    nome_arquivo = re.sub(r'[\s]+', '_', nome_arquivo).strip('_')

    plano = {
        "produto":    produto,
        "plataforma": plataforma,
        "objetivo":   "venda afiliada",
        "hook":       f"Você PRECISA conhecer esse {produto} 👀",
        "roteiro": (
            f"[0-2s] Hook: 'Você PRECISA conhecer esse {produto}'\n"
            f"[2-5s] Mostrar o produto de perto, destacar qualidade\n"
            f"[5-8s] Demonstração rápida: mostrar funcionando\n"
            f"[8-{duracao}] CTA: 'Link na bio! Corre que tá acabando 🔥'"
        ),
        "narracao": (
            f"Gente, vocês precisam conhecer esse {produto}. "
            f"Olha a qualidade desse negócio. Funciona muito bem. "
            f"Tá com preço incrível, link na bio, corre que tá acabando!"
        ),
        "cenas": [
            {
                "tempo":      "0-2s",
                "descricao":  "Close no rosto com expressão de surpresa, ou texto grande na tela",
                "texto_tela": f"Você PRECISA ver isso 👀",
            },
            {
                "tempo":      "2-5s",
                "descricao":  f"Close no {produto}, mostrando detalhes e qualidade",
                "texto_tela": f"{produto} ✨",
            },
            {
                "tempo":      "5-8s",
                "descricao":  f"Demonstração rápida do {produto} funcionando",
                "texto_tela": "Funciona DEMAIS 🔥",
            },
            {
                "tempo":      f"8-{duracao}",
                "descricao":  "Tela com CTA grande e seta apontando pra bio",
                "texto_tela": "Link na bio! 🛒",
            },
        ],
        "legenda":          f"{produto} que eu AMEI 🔥 Link na bio! #shopee #{nicho.lower().replace('/', '')}",
        "hashtags":         f"#{nome_arquivo} #shopee #achados #ofertas #{nicho.lower().replace('/', '')} #tiktokbrasil #viral #fyp",
        "cta":              "Link na bio! Corre que tá acabando 🔥",
        "estilo_visual":    "close-up produto com texto grande e cores vibrantes",
        "musica_sugerida":  "trend do momento ou electrofunk leve",
        "melhor_horario":   "19h-21h",
        "tom":              "urgente e curioso",
        "video_path_sugerido": f"C:\\AgenteIA\\videos\\{nome_arquivo}.mp4",
        "fonte":            "fallback_local",
        "modelo":           "template_v1",
    }

    log.info(f"📝 Plano fallback gerado para '{produto}'")
    return plano


# =========================
# SALVAR PLANO
# =========================

def _salvar_plano(plano: dict) -> Path:
    """Salva o plano em shared/content_plans/ e retorna o caminho."""
    PLANS_DIR.mkdir(parents=True, exist_ok=True)

    # Salva como último plano (sempre sobrescreve)
    caminho_ultimo = PLANS_DIR / "ultimo_plano.json"
    with open(caminho_ultimo, "w", encoding="utf-8") as f:
        json.dump(plano, f, ensure_ascii=False, indent=2)

    # Salva também com timestamp para histórico
    ts = time.strftime("%Y%m%d_%H%M%S")
    nome_produto = re.sub(r'[^\w]', '_', plano.get("produto", "produto")[:30]).lower()
    caminho_historico = PLANS_DIR / f"plano_{nome_produto}_{ts}.json"
    with open(caminho_historico, "w", encoding="utf-8") as f:
        json.dump(plano, f, ensure_ascii=False, indent=2)

    log.info(f"💾 Plano salvo: {caminho_ultimo}")
    log.info(f"💾 Histórico:   {caminho_historico}")
    return caminho_ultimo


# =========================
# FUNÇÃO PRINCIPAL
# =========================

def gerar_plano_conteudo(produto_info: dict) -> dict:
    """
    Gera um plano completo de conteúdo para um produto.

    Tenta Gemini primeiro. Se sem cota (429) ou sem key, usa fallback local.
    Salva o resultado em shared/content_plans/.

    Args:
        produto_info: dict com campos:
            produto     (str) — obrigatório
            nicho       (str) — ex: "Casa/Tech"
            plataforma  (str) — "TikTok" | "Instagram" | "YouTube"
            duracao     (str) — ex: "12s"
            link        (str) — link afiliado
            comissao    (str) — valor da comissão

    Returns:
        dict com plano completo (hook, roteiro, cenas, legenda, hashtags, cta, etc)
        Inclui campo "fonte": "gemini" ou "fallback_local"

    Uso:
        from agents.content_planner import gerar_plano_conteudo

        plano = gerar_plano_conteudo({
            "produto": "Mini Aspirador de Teclado",
            "nicho": "Casa/Tech",
            "plataforma": "TikTok",
            "duracao": "12s",
        })
        print(plano["hook"])
        print(plano["roteiro"])
    """
    produto = produto_info.get("produto", "?")
    log.info(f"🎬 Content Planner iniciado para: '{produto}'")

    # Enriquece com dados reais da Shopee (mina de ouro: link, comissão, preço).
    # Se a Shopee não estiver disponível, retorna o produto_info intacto.
    produto_info = _enriquecer_com_shopee(produto_info)

    # Tenta Gemini primeiro
    plano = _gerar_plano_gemini(produto_info)

    # Fallback se Gemini falhou
    if plano is None:
        plano = _gerar_plano_fallback(produto_info)

    # Adiciona video_path_sugerido se não veio do Gemini
    if "video_path_sugerido" not in plano:
        nome_arquivo = re.sub(r'[^\w\s-]', '', produto.lower())
        nome_arquivo = re.sub(r'[\s]+', '_', nome_arquivo).strip('_')
        plano["video_path_sugerido"] = f"C:\\AgenteIA\\videos\\{nome_arquivo}.mp4"

    # Metadados
    plano["timestamp"]    = time.strftime("%Y-%m-%d %H:%M:%S")
    plano["produto_input"] = produto_info

    # Propaga os dados da Shopee pro plano final (pra seguirem até a publicação).
    # O link de afiliado e os reservas precisam viajar junto com o vídeo.
    if produto_info.get("link"):
        plano["link_afiliado"] = produto_info["link"]
    if produto_info.get("comissao"):
        plano["comissao"] = produto_info["comissao"]
    if produto_info.get("links_espelho"):
        plano["links_espelho"] = produto_info["links_espelho"]
    if produto_info.get("preco_real"):
        plano["preco_real"] = produto_info["preco_real"]
    if produto_info.get("titulo_real"):
        plano["titulo_real"] = produto_info["titulo_real"]

    # Salva
    _salvar_plano(plano)

    log.info(f"✅ Plano completo — fonte: {plano.get('fonte')} | hook: '{plano.get('hook', '')[:50]}'")
    return plano


# =========================
# TESTE VIA TERMINAL
# =========================

if __name__ == "__main__":
    print("=" * 60)
    print("  🎬 Content Planner — Teste")
    print("=" * 60)

    produto_teste = {
        "produto":    "Mini Aspirador de Teclado",
        "nicho":      "Casa/Tech",
        "plataforma": "TikTok",
        "duracao":    "12s",
        "link":       "",
        "comissao":   "",
    }

    print(f"\n📦 Produto: {produto_teste['produto']}")
    print(f"🏷️  Nicho:   {produto_teste['nicho']}")
    print(f"📱 Plataforma: {produto_teste['plataforma']}")
    print()

    plano = gerar_plano_conteudo(produto_teste)

    print(f"\n{'─' * 60}")
    print(f"📡 Fonte: {plano.get('fonte', '?')}")
    print(f"🎣 Hook:  {plano.get('hook', '?')}")
    print(f"\n📜 Roteiro:")
    print(f"   {plano.get('roteiro', '?')}")
    print(f"\n🎙️  Narração:")
    print(f"   {plano.get('narracao', '?')}")
    print(f"\n🎬 Cenas:")
    for cena in plano.get("cenas", []):
        print(f"   [{cena['tempo']}] {cena['descricao']}")
        print(f"   Texto tela: {cena['texto_tela']}")
    print(f"\n📝 Legenda:  {plano.get('legenda', '?')}")
    print(f"#️⃣  Hashtags: {plano.get('hashtags', '?')}")
    print(f"📢 CTA:      {plano.get('cta', '?')}")
    print(f"🎵 Música:   {plano.get('musica_sugerida', '?')}")
    print(f"⏰ Horário:  {plano.get('melhor_horario', '?')}")
    print(f"🎥 Vídeo:    {plano.get('video_path_sugerido', '?')}")
    print(f"\n💾 Salvo em: shared/content_plans/ultimo_plano.json")
    print("=" * 60)