# brain/auditor.py
# Auditoria visual do post TikTok antes da publicação.
#
# Três modos de auditoria:
#   1. auditar_post_tiktok()          — completa (legado)
#   2. auditar_conteudo_tiktok()      — vídeo, legenda, hashtags (ANTES do scroll)
#   3. auditar_botao_publicar_tiktok()— botão Publicar (DEPOIS do scroll)

import base64
import json
import os
import time
from pathlib import Path

from google import genai
from google.genai import errors

from brain.commander import enviar_comando
from shared.logger import get_logger
from shared.path_utils import windows_to_wsl_path
from shared.config import GEMINI_VISION_MODEL

log = get_logger(__name__)


def _screenshot_path(caminho_windows: str) -> Path:
    if os.name == "nt":
        return Path(caminho_windows)
    return Path(windows_to_wsl_path(caminho_windows))

_gemini_client = None
def _get_client():
    global _gemini_client
    if _gemini_client is None:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY não definida.")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


# =================================================================
# INFRAESTRUTURA COMPARTILHADA
# =================================================================

def _tirar_screenshot(contexto: str) -> tuple:
    resultado_executor = enviar_comando("observar_tela", contexto=contexto)
    if not resultado_executor.get("sucesso"):
        msg = f"Executor falhou: {resultado_executor.get('mensagem')}"
        log.error(msg)
        return None, _falha(msg, "Falha ao tirar screenshot")
    caminho_windows = resultado_executor.get("dados", {}).get("caminho_screenshot", "")
    if not caminho_windows:
        return None, _falha("Caminho ausente", "Executor não retornou caminho")
    caminho_wsl = _screenshot_path(caminho_windows)
    log.info(f"🖼️ Screenshot: {caminho_wsl}")
    if not caminho_wsl.exists():
        return None, _falha(f"Não encontrado: {caminho_wsl}", "Arquivo ausente")
    try:
        with open(caminho_wsl, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8"), None
    except Exception as e:
        return None, _falha(str(e), "Erro ao ler screenshot")

def _chamar_gemini(imagem_b64: str, prompt: str, nome: str) -> tuple:
    client = _get_client()
    payload = [{"parts": [
        {"inline_data": {"mime_type": "image/png", "data": imagem_b64}},
        {"text": prompt},
    ]}]
    backoff = [5, 10, 20]
    ultimo_erro = None
    for t in range(1, 4):
        log.info(f"  🤖 Gemini {nome} — tentativa {t}/3")
        try:
            resp = client.models.generate_content(model=GEMINI_VISION_MODEL, contents=payload)
            texto = resp.text.strip()
            if texto.startswith("```"):
                texto = "\n".join(texto.split("\n")[1:-1])
            return json.loads(texto), None
        except json.JSONDecodeError as e:
            log.warning(f"  ⚠️ Tentativa {t}: JSON inválido — {e}")
            ultimo_erro = _falha(f"JSON inválido: {e}", "Resposta malformada")
        except errors.ClientError as e:
            erro_str = str(e)
            eh_transitorio = any(x in erro_str for x in ("503", "UNAVAILABLE", "high demand", "overloaded"))
            if eh_transitorio:
                log.warning(f"  ⚠️ Tentativa {t}: Gemini sobrecarregado — {erro_str[:80]}")
                ultimo_erro = _falha(erro_str, "Gemini temporariamente indisponível")
            else:
                log.error(f"  ❌ Erro permanente API: {e}")
                return None, _falha(str(e), "Erro API Gemini")
        except Exception as e:
            log.error(f"  ❌ Erro: {e}")
            ultimo_erro = _falha(str(e), "Erro inesperado")
        if t < 3:
            espera = backoff[t - 1] if t - 1 < len(backoff) else backoff[-1]
            log.info(f"  ⏳ Aguardando {espera}s antes da tentativa {t + 1}...")
            time.sleep(espera)
    log.error(f"  🚫 Gemini {nome} falhou após 3 tentativas")
    return None, ultimo_erro or _falha("Falhou", "Gemini indisponível")


# =================================================================
# AUDITORIA 1 — CONTEÚDO (ANTES do scroll)
# =================================================================

PROMPT_CONTEUDO = """
Você é o auditor de conteúdo de um agente IA que posta vídeos no TikTok.
FOCO: verificar se o CONTEÚDO está pronto (vídeo, legenda, hashtags).
NÃO se preocupe se o botão Publicar está visível ou não.

Responda APENAS com JSON válido, sem texto adicional:
{
  "video_carregado": true,
  "legenda_preenchida": true,
  "hashtags_visiveis": true,
  "captcha_detectado": false,
  "login_necessario": false,
  "erro_visivel": false,
  "descricao_legenda": "primeiras palavras da legenda",
  "descricao_hashtags": "hashtags visíveis",
  "conteudo_pronto": true,
  "motivo": "Conteúdo OK.",
  "riscos": [],
  "itens_confirmados": ["Vídeo carregado", "Legenda preenchida", "Hashtags visíveis"]
}

REGRAS:
- video_carregado: true se houver preview/thumbnail
- legenda_preenchida: true APENAS se houver texto real (não placeholder)
- hashtags_visiveis: true se houver pelo menos uma #
- conteudo_pronto: true SOMENTE SE video+legenda=true E captcha/login/erro=false
- Não invente. Se não confirmar, marque false.
"""

def auditar_conteudo_tiktok(contexto: str = "auditoria_conteudo_tiktok") -> dict:
    log.info(f"🔍 AUDITORIA CONTEÚDO iniciada — contexto: '{contexto}'")
    imagem_b64, erro = _tirar_screenshot(contexto)
    if erro: return erro
    laudo, erro = _chamar_gemini(imagem_b64, PROMPT_CONTEUDO, "conteudo")
    if erro: return erro

    riscos = list(laudo.get("riscos", []))
    itens = list(laudo.get("itens_confirmados", []))

    if laudo.get("captcha_detectado"):
        return _falha("Captcha detectado", "Captcha", laudo=laudo, riscos=["Captcha"])
    if laudo.get("login_necessario"):
        return _falha("Login necessário", "Sessão expirada", laudo=laudo, riscos=["Login"])
    if laudo.get("erro_visivel"):
        return _falha("Erro visível", "Erro detectado", laudo=laudo, riscos=["Erro"])
    if not laudo.get("legenda_preenchida"):
        return _falha("Legenda vazia", "Legenda não preenchida", laudo=laudo, riscos=["Legenda vazia"])
    if not laudo.get("video_carregado"):
        return _falha("Vídeo não confirmado na tela", "Preview/thumbnail do vídeo não detectado", laudo=laudo, riscos=["Vídeo não carregado"])
    if not laudo.get("hashtags_visiveis"):
        return _falha("Hashtags não detectadas", "Hashtags não visíveis na auditoria de conteúdo", laudo=laudo, riscos=["Hashtags ausentes"])

    for campo, label in [("video_carregado","Vídeo carregado"),("legenda_preenchida","Legenda preenchida"),("hashtags_visiveis","Hashtags visíveis")]:
        if laudo.get(campo) and label not in itens: itens.append(label)

    try:
        from memory.state_manager import atualizar_varios
        atualizar_varios({"ultimo_laudo_conteudo": laudo})
        log.debug("💾 Laudo conteúdo salvo")
    except Exception as e:
        log.warning(f"Não salvou laudo conteúdo: {e}")

    motivo = laudo.get("motivo", "Conteúdo aprovado")
    log.info(f"✅ CONTEÚDO: {motivo}")
    return {"sucesso": True, "mensagem": motivo, "pronto_para_publicar": laudo.get("conteudo_pronto", False),
            "motivo": motivo, "riscos": riscos, "itens_confirmados": itens, "dados": laudo}


# =================================================================
# AUDITORIA 2 — BOTÃO PUBLICAR (DEPOIS do scroll)
# =================================================================

PROMPT_BOTAO = """
Você é o auditor de interface de um agente IA que posta vídeos no TikTok.
FOCO: verificar se o BOTÃO PUBLICAR está visível e clicável.
NÃO se preocupe se legenda/hashtags estão visíveis (podem ter saído da tela após scroll).

Responda APENAS com JSON válido, sem texto adicional:
{
  "botao_publicar_visivel": true,
  "texto_botao": "Post",
  "captcha_detectado": false,
  "login_necessario": false,
  "erro_visivel": false,
  "botao_pronto": true,
  "motivo": "Botão Publicar visível.",
  "riscos": [],
  "itens_confirmados": ["Botão Publicar visível"]
}

REGRAS:
- botao_publicar_visivel: true se botão de publicar visível ("Publicar","Post","Postar","Publish")
- texto_botao: texto exato do botão (null se não visível)
- botao_pronto: true SOMENTE SE botao_visivel=true E captcha/login/erro=false
- Não invente.
"""

def auditar_botao_publicar_tiktok(contexto: str = "auditoria_botao_publicar") -> dict:
    log.info(f"🔍 AUDITORIA BOTÃO iniciada — contexto: '{contexto}'")
    imagem_b64, erro = _tirar_screenshot(contexto)
    if erro: return erro
    laudo, erro = _chamar_gemini(imagem_b64, PROMPT_BOTAO, "botao")
    if erro: return erro

    riscos = list(laudo.get("riscos", []))
    itens = list(laudo.get("itens_confirmados", []))

    if laudo.get("captcha_detectado"):
        return _falha("Captcha detectado", "Captcha", laudo=laudo, riscos=["Captcha"])
    if laudo.get("login_necessario"):
        return _falha("Login necessário", "Sessão expirada", laudo=laudo, riscos=["Login"])
    if laudo.get("erro_visivel"):
        return _falha("Erro visível", "Erro detectado", laudo=laudo, riscos=["Erro"])
    if not laudo.get("botao_publicar_visivel"):
        return _falha(
            "Botão Publicar não visível após scroll",
            "Botão de publicação não encontrado/clicável",
            laudo=laudo, riscos=["Botão Publicar não visível após scroll"]
        )
    if "Botão Publicar visível" not in itens:
        itens.append("Botão Publicar visível")

    # Salva e combina com laudo de conteúdo
    try:
        from memory.state_manager import carregar_estado, atualizar_varios
        atualizar_varios({"ultimo_laudo_botao": laudo})
        state = carregar_estado()
        laudo_conteudo = state.get("ultimo_laudo_conteudo", {})
        combinado = _combinar_laudos(laudo_conteudo, laudo)
        atualizar_varios({
            "ultimo_laudo_auditoria": combinado,
            "ultimo_laudo_pronto": combinado.get("pronto_para_publicar", False),
        })
        log.info(f"💾 Laudo combinado: pronto={combinado.get('pronto_para_publicar')}")
    except Exception as e:
        log.warning(f"Não salvou/combinou laudos: {e}")

    motivo = laudo.get("motivo", "Auditoria botão concluída")
    log.info(f"✅ BOTÃO: {motivo}")
    return {"sucesso": True, "mensagem": motivo, "pronto_para_publicar": laudo.get("botao_pronto", False),
            "motivo": motivo, "riscos": riscos, "itens_confirmados": itens, "dados": laudo}


# =================================================================
# COMBINADOR DE LAUDOS
# =================================================================

def _combinar_laudos(laudo_conteudo: dict, laudo_botao: dict) -> dict:
    combinado = {
        "video_carregado":        laudo_conteudo.get("video_carregado", False),
        "legenda_preenchida":     laudo_conteudo.get("legenda_preenchida", False),
        "hashtags_visiveis":      laudo_conteudo.get("hashtags_visiveis", False),
        "descricao_legenda":      laudo_conteudo.get("descricao_legenda", ""),
        "descricao_hashtags":     laudo_conteudo.get("descricao_hashtags", ""),
        "botao_publicar_visivel": laudo_botao.get("botao_publicar_visivel", False),
        "captcha_detectado":      laudo_conteudo.get("captcha_detectado", False) or laudo_botao.get("captcha_detectado", False),
        "login_necessario":       laudo_conteudo.get("login_necessario", False) or laudo_botao.get("login_necessario", False),
        "erro_visivel":           laudo_conteudo.get("erro_visivel", False) or laudo_botao.get("erro_visivel", False),
        "pronto_para_publicar": (
            laudo_conteudo.get("conteudo_pronto", False)
            and laudo_botao.get("botao_pronto", False)
        ),
        "motivo": "Laudo combinado: conteúdo + botão avaliados separadamente",
        "riscos": list(laudo_conteudo.get("riscos", [])) + list(laudo_botao.get("riscos", [])),
        "itens_confirmados": list(laudo_conteudo.get("itens_confirmados", [])) + list(laudo_botao.get("itens_confirmados", [])),
        "fonte": "laudo_combinado",
    }
    log.info(f"🔗 Combinado: video={combinado['video_carregado']} legenda={combinado['legenda_preenchida']} "
             f"hashtags={combinado['hashtags_visiveis']} botao={combinado['botao_publicar_visivel']} "
             f"pronto={combinado['pronto_para_publicar']}")
    return combinado


# =================================================================
# AUDITORIA LEGADA — COMPLETA (compatibilidade)
# =================================================================

PROMPT_AUDITORIA = """
Você é o auditor de qualidade de um agente IA que posta vídeos no TikTok.
Analise esta screenshot e retorne laudo completo.

Responda APENAS com JSON válido:
{
  "video_carregado": true, "legenda_preenchida": true, "hashtags_visiveis": true,
  "botao_publicar_visivel": true, "captcha_detectado": false, "login_necessario": false,
  "erro_visivel": false, "descricao_legenda": "...", "descricao_hashtags": "...",
  "pronto_para_publicar": true, "motivo": "...", "riscos": [], "itens_confirmados": [...]
}
Não invente. Se não confirmar, marque false.
"""

def auditar_post_tiktok(contexto: str = "revisao_final_tiktok") -> dict:
    log.info(f"🔍 AUDITORIA COMPLETA — contexto: '{contexto}'")
    imagem_b64, erro = _tirar_screenshot(contexto)
    if erro: return erro
    laudo, erro = _chamar_gemini(imagem_b64, PROMPT_AUDITORIA, "completa")
    if erro: return erro
    resultado = _avaliar_laudo(laudo)
    try:
        from memory.state_manager import atualizar_varios
        atualizar_varios({"ultimo_laudo_auditoria": laudo, "ultimo_laudo_pronto": resultado.get("pronto_para_publicar", False)})
    except Exception: pass
    return resultado

def _avaliar_laudo(laudo: dict) -> dict:
    riscos = list(laudo.get("riscos", [])); itens = list(laudo.get("itens_confirmados", []))
    if laudo.get("captcha_detectado"): return _falha("Captcha", "Captcha", laudo=laudo, riscos=["Captcha"])
    if laudo.get("login_necessario"): return _falha("Login", "Sessão expirada", laudo=laudo, riscos=["Login"])
    if laudo.get("erro_visivel"): return _falha("Erro", "Erro detectado", laudo=laudo, riscos=["Erro"])
    if not laudo.get("legenda_preenchida"): return _falha("Legenda vazia", "Legenda vazia", laudo=laudo, riscos=["Legenda vazia"])
    if not laudo.get("botao_publicar_visivel"): riscos.append("Botão não visível")
    if not laudo.get("hashtags_visiveis"): riscos.append("Hashtags não detectadas")
    for campo, label in [("video_carregado","Vídeo carregado"),("legenda_preenchida","Legenda preenchida"),
                         ("hashtags_visiveis","Hashtags visíveis"),("botao_publicar_visivel","Botão Publicar visível")]:
        if laudo.get(campo) and label not in itens: itens.append(label)
    pronto = laudo.get("pronto_para_publicar", False); motivo = laudo.get("motivo", "Auditoria concluída")
    return {"sucesso": True, "mensagem": motivo, "pronto_para_publicar": pronto,
            "motivo": motivo, "riscos": riscos, "itens_confirmados": itens, "dados": laudo}


# =================================================================
# HELPER
# =================================================================

def _falha(mensagem, motivo, laudo=None, riscos=None, itens_confirmados=None):
    return {"sucesso": False, "mensagem": mensagem, "pronto_para_publicar": False,
            "motivo": motivo, "riscos": riscos or [mensagem], "itens_confirmados": itens_confirmados or [], "dados": laudo or {}}