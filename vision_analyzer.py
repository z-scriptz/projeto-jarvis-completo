# brain/vision_analyzer.py
# Camada OBSERVE do AgenteIA
# Recebe caminho de screenshot do executor Windows,
# converte para caminho WSL, envia ao Gemini Vision e retorna análise estruturada.
#
# Fluxo:
#   commander.py → executor tira screenshot
#       → vision_analyzer converte caminho
#           → Gemini Vision analisa
#               → retorna dict estruturado pro main.py decidir
#
# Otimização (cache visual):
#   clicar_elemento_por_texto tenta primeiro o interface_cache.
#   Cache hit  → executa clique direto (rápido, sem queimar cota Gemini)
#   Cache miss → cai pra Gemini Vision (fallback premium) e salva resultado
#                no cache pra acelerar próximas chamadas.

import time
import os
import base64
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import errors

from brain.commander import enviar_comando
from brain.interface_cache import (
    buscar_elemento_cache,
    registrar_sucesso,
    registrar_sucesso_pendente,
    confirmar_clique_pendente,
    descartar_clique_pendente,
    registrar_falha,
    registrar_via_localizar,
    exige_validacao_semantica,
)
from shared.config import GEMINI_VISION_MODEL
from shared.logger import get_logger
from shared.path_utils import screenshot_path_to_wsl

log = get_logger(__name__)


# =========================
# DETECÇÃO DE QUOTA GEMINI
# =========================
#
# Diferencia 429 transitório (overloaded, rate por minuto) de 429
# quota diária esgotada. Importante porque:
#   - 429 transitório → vale retry com backoff
#   - 429 quota diária → retry é desperdício, melhor abortar limpo
#
# Pistas no texto do erro (case-insensitive):
#   RESOURCE_EXHAUSTED  → sempre quota
#   quota | exhausted   → quota
#   429 sozinho         → ambíguo, mas se tem "quota"/"exhausted" → quota
#
# Sinais de transitório (NÃO é quota):
#   overloaded | UNAVAILABLE | 503  → retry vale a pena

def _eh_erro_quota(exception_ou_str) -> bool:
    """
    Detecta se uma exceção/string indica quota Gemini esgotada
    (vs erro transitório). True = abortar sem retry.

    Conservador: "exceeded" sozinho não basta (pode ser rate limit por
    minuto, que é transitório). Exige RESOURCE_EXHAUSTED ou a palavra
    "quota" explicitamente.
    """
    msg = str(exception_ou_str).lower()
    pistas_quota = ("resource_exhausted", "quota")
    if any(p in msg for p in pistas_quota):
        return True
    return False


def _extrair_retry_delay(exception_ou_str) -> Optional[int]:
    """
    Tenta extrair retryDelay (segundos) da mensagem do Gemini.
    Retorna None se não conseguir.
    """
    import re as _re
    msg = str(exception_ou_str)
    # Padrões comuns: "retryDelay": "30s"  ou  retry_delay: 30
    m = _re.search(r'retry[_-]?[dD]elay[^0-9]*(\d+)', msg)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


# =========================
# CLIENTE GEMINI (singleton)
# =========================

_gemini_client = None

def _get_client():
    global _gemini_client
    if _gemini_client is None:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY não definida.")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


# =========================
# CONVERSÃO DE CAMINHO
# Windows → WSL
# =========================

def windows_para_wsl(caminho_windows: str) -> Path:
    """
    Converte caminho Windows para caminho WSL acessível.
    Delega para shared.path_utils para garantir consistência em todo o projeto.

    Cobre todos os casos:
        C:\\AgenteIA\\logs\\foto.png   → /mnt/c/AgenteIA/logs/foto.png
        C:/AgenteIA/foto.png           → /mnt/c/AgenteIA/foto.png
        \\mnt\\c\\AgenteIA\\foto.png   → /mnt/c/AgenteIA/foto.png
        /mnt/c/AgenteIA/foto.png       → /mnt/c/AgenteIA/foto.png  (já correto)
        D:\\Videos\\clip.mp4           → /mnt/d/Videos/clip.mp4
    """
    if os.name == "nt":
        return Path(caminho_windows)
    return Path(screenshot_path_to_wsl(caminho_windows))


# =========================
# ANÁLISE COM GEMINI VISION
# =========================

PROMPT_ANALISE_TELA = """
Você é o sistema de visão de um agente IA que controla um computador.
Analise esta screenshot e responda EXATAMENTE neste formato JSON, sem texto adicional:

{{
  "descricao": "descrição objetiva do que está visível na tela",
  "app_ativo": "nome do app/site aberto (ou 'área de trabalho')",
  "estado": "carregando | pronto | erro | bloqueado | desconhecido",
  "elementos_visiveis": ["lista", "dos", "elementos", "importantes"],
  "texto_principal": "texto mais relevante visível na tela",
  "proxima_acao_sugerida": "o que o agente deveria fazer agora",
  "alerta": "mensagem de alerta ou erro visível (ou null se não houver)"
}}

Contexto da tarefa atual: {contexto}
"""

def analisar_tela_com_gemini(
    caminho_wsl: Path,
    contexto: str = "",
    max_tentativas: int = 3,
    backoff: list[float] = None,
) -> dict:
    """
    Envia screenshot ao Gemini Vision e retorna análise estruturada.
    Tenta até max_tentativas vezes com backoff exponencial em caso de
    erros temporários (503 UNAVAILABLE, 429, timeout).

    Args:
        caminho_wsl:    caminho WSL para o arquivo .png
        contexto:       descrição do momento (ex: "apos_abrir_tiktok")
        max_tentativas: número máximo de tentativas (padrão: 3)
        backoff:        lista de esperas em segundos entre tentativas
                        (padrão: [3, 6, 12])

    Returns:
        dict com campos: descricao, app_ativo, estado, elementos_visiveis,
                         texto_principal, proxima_acao_sugerida, alerta
        Em caso de falha total retorna dict com "erro", "tipo", "retry_excedido".
    """
    import json

    if backoff is None:
        backoff = [3, 6, 12]

    # ── Pré-validações (sem retry — erros locais) ──────────────────
    if not caminho_wsl.exists():
        log.error(f"Screenshot não encontrado: {caminho_wsl}")
        return {"erro": f"Arquivo não encontrado: {caminho_wsl}", "tipo": "arquivo_ausente"}

    try:
        with open(caminho_wsl, "rb") as f:
            imagem_bytes = f.read()
        imagem_b64 = base64.b64encode(imagem_bytes).decode("utf-8")
        log.info(f"🖼️ Imagem carregada: {caminho_wsl.name} ({len(imagem_bytes)//1024}KB)")
    except Exception as e:
        log.error(f"Erro ao ler imagem: {e}")
        return {"erro": str(e), "tipo": "leitura_arquivo"}

    prompt  = PROMPT_ANALISE_TELA.format(contexto=contexto or "tarefa geral")
    client  = _get_client()
    payload = [
        {
            "parts": [
                {"inline_data": {"mime_type": "image/png", "data": imagem_b64}},
                {"text": prompt},
            ]
        }
    ]

    ultimo_erro: dict = {}

    # ── Loop de tentativas ─────────────────────────────────────────
    for tentativa in range(1, max_tentativas + 1):

        log.info(f"🔍 Gemini Vision — tentativa {tentativa}/{max_tentativas} | contexto='{contexto}'")

        try:
            response = client.models.generate_content(
                model=GEMINI_VISION_MODEL,
                contents=payload,
            )

            texto = response.text.strip()
            if texto.startswith("```"):
                linhas = texto.split("\n")
                texto = "\n".join(linhas[1:-1])

            analise = json.loads(texto)
            log.info(
                f"✅ Gemini Vision OK (tentativa {tentativa}) — "
                f"estado='{analise.get('estado')}' | app='{analise.get('app_ativo')}'"
            )
            return analise

        except json.JSONDecodeError as e:
            # JSON malformado — provavelmente erro pontual, vale retry
            log.warning(f"⚠️ Tentativa {tentativa}: JSON inválido — {e}")
            ultimo_erro = {"erro": "JSON inválido", "tipo": "resposta_malformada", "detalhe": str(e)}

        except errors.ClientError as e:
            codigo = getattr(e, "status_code", None) or str(e)

            # PRIORIDADE: quota Gemini esgotada → aborta imediatamente
            if _eh_erro_quota(e):
                retry_delay = _extrair_retry_delay(e)
                log.error(
                    f"🚫 Gemini Vision QUOTA EXCEDIDA ({codigo}) — "
                    f"abortando sem retry. retryDelay={retry_delay}s"
                )
                return {
                    "erro":           "Gemini quota excedida",
                    "tipo":           "quota_excedida",
                    "detalhe":        str(e),
                    "retry_delay":    retry_delay,
                    "retry_excedido": False,
                }

            eh_transitorio = any(x in str(e) for x in ("503", "429", "UNAVAILABLE", "overloaded"))

            if eh_transitorio:
                log.warning(f"⚠️ Tentativa {tentativa}: Gemini sobrecarregado ({codigo})")
                ultimo_erro = {
                    "erro":  "Gemini Vision indisponível",
                    "tipo":  "modelo_sobrecarregado",
                    "detalhe": str(e),
                }
            else:
                # Erro de autenticação, billing, etc. — não adianta retry
                log.error(f"❌ Erro permanente da API Gemini ({codigo}) — abortando retries")
                return {"erro": f"Erro API: {e}", "tipo": "erro_permanente", "retry_excedido": False}

        except Exception as e:
            log.warning(f"⚠️ Tentativa {tentativa}: erro inesperado — {e}")
            ultimo_erro = {"erro": str(e), "tipo": "desconhecido"}

        # Aguarda antes da próxima tentativa (sem esperar após a última)
        if tentativa < max_tentativas:
            espera = backoff[tentativa - 1] if tentativa - 1 < len(backoff) else backoff[-1]
            log.info(f"⏳ Aguardando {espera}s antes da tentativa {tentativa + 1}...")
            time.sleep(espera)

    # ── Todas as tentativas falharam ───────────────────────────────
    log.error(
        f"🚫 Gemini Vision falhou após {max_tentativas} tentativas. "
        f"Tipo: {ultimo_erro.get('tipo')} | Contexto: '{contexto}'"
    )
    return {
        **ultimo_erro,
        "retry_excedido": True,
        "tentativas":     max_tentativas,
    }


# =========================
# FUNÇÃO PRINCIPAL — OBSERVE
# =========================

def observar_e_analisar(contexto: str = "") -> dict:
    """
    Loop OBSERVE completo:
    1. Manda executor tirar screenshot
    2. Recebe caminho Windows do resultado
    3. Converte para caminho WSL
    4. Envia ao Gemini Vision
    5. Retorna análise estruturada para o main.py decidir

    Args:
        contexto: descrição do momento (ex: "apos_abrir_tiktok", "antes_de_postar")

    Returns:
        dict com análise da tela + metadados:
        {
            "analise": { ...campos do Gemini... },
            "caminho_screenshot_wsl": "...",
            "caminho_screenshot_windows": "...",
            "contexto": "...",
            "sucesso": True/False
        }

    Uso em main.py:
        from brain.vision_analyzer import observar_e_analisar

        resultado = observar_e_analisar("apos_abrir_tiktok")
        if resultado["sucesso"]:
            estado = resultado["analise"]["estado"]
            proxima = resultado["analise"]["proxima_acao_sugerida"]
    """
    log.info(f"👁️ OBSERVE iniciado — contexto: '{contexto}'")

    # Passo 1: pede screenshot ao executor Windows
    resultado_executor = enviar_comando("observar_tela", contexto=contexto)

    if not resultado_executor.get("sucesso"):
        log.error(f"Executor falhou ao tirar screenshot: {resultado_executor.get('mensagem')}")
        return {
            "sucesso": False,
            "erro": resultado_executor.get("mensagem", "Executor não respondeu"),
            "contexto": contexto,
        }

    # Passo 2: extrai caminho Windows do resultado
    dados = resultado_executor.get("dados", {})
    caminho_windows = dados.get("caminho_screenshot", "")

    if not caminho_windows:
        log.error("Executor não retornou caminho da screenshot")
        return {"sucesso": False, "erro": "Caminho da screenshot ausente", "contexto": contexto}

    # Passo 3: converte Windows → WSL (via path_utils — cobre todos os formatos)
    caminho_wsl = windows_para_wsl(caminho_windows)

    # Passo 4 + 5: Gemini Vision analisa
    analise = analisar_tela_com_gemini(caminho_wsl, contexto=contexto)

    sucesso = "erro" not in analise

    log.info(
        f"✅ OBSERVE concluído — estado: {analise.get('estado', '?')} | "
        f"sugestão: {analise.get('proxima_acao_sugerida', '?')[:60]}"
        if sucesso else f"❌ OBSERVE falhou: {analise.get('erro')}"
    )

    return {
        "sucesso": sucesso,
        "analise": analise,
        "caminho_screenshot_windows": caminho_windows,
        "caminho_screenshot_wsl": str(caminho_wsl),
        "contexto": contexto,
    }


# =========================
# LOCALIZAÇÃO POR TEXTO
# Sem imagem de referência — Gemini lê a tela e devolve coordenadas
# =========================

PROMPT_LOCALIZAR_ELEMENTO = """
Você é o sistema de visão de um agente IA que controla um computador Windows.
Analise a screenshot e localize o elemento solicitado.

ELEMENTO BUSCADO: "{alvo}"
CONTEXTO DA TAREFA: {contexto}

Responda APENAS com JSON válido, sem texto adicional, sem markdown:

{{
  "encontrado": true,
  "elemento": "texto exato do elemento na tela",
  "x": 760,
  "y": 430,
  "confianca": "alta",
  "motivo": "Botão 'Select file' encontrado no centro da área de upload, cor azul"
}}

Se não encontrar:
{{
  "encontrado": false,
  "elemento": null,
  "x": null,
  "y": null,
  "confianca": "baixa",
  "motivo": "Elemento não visível na tela — descreva o que está visível"
}}

REGRAS OBRIGATÓRIAS:
- x e y são coordenadas ABSOLUTAS da tela inteira do Windows (não relativas à janela)
- confianca: "alta" = certeza visual clara | "media" = provável | "baixa" = incerto
- Se detectar captcha, tela de login ou bloqueio, retorne "encontrado": false e descreva no motivo
- Não invente coordenadas — só retorne x/y se o elemento for claramente visível
"""


def localizar_elemento_por_texto(
    contexto: str,
    alvo: str,
    max_tentativas: int = 2,
) -> dict:
    """
    Tira screenshot, envia ao Gemini Vision e pede as coordenadas
    de um elemento pelo seu texto/descrição — sem imagem de referência.

    Args:
        contexto:       descrição do momento (ex: "pagina_upload_tiktok")
        alvo:           texto ou descrição do elemento (ex: "Select file", "botão publicar")
        max_tentativas: retry em caso de JSON inválido (padrão: 2)

    Returns:
        dict com:
            encontrado  (bool)
            elemento    (str)  — texto exato visto na tela
            x, y        (int)  — coordenadas absolutas Windows
            confianca   (str)  — "alta" | "media" | "baixa"
            motivo      (str)  — raciocínio do Gemini
            erro        (str)  — presente só se falha técnica

    Uso:
        pos = localizar_elemento_por_texto("pagina_upload_tiktok", "Select file")
        if pos["encontrado"] and pos["confianca"] != "baixa":
            enviar_comando("clicar", x=pos["x"], y=pos["y"])
    """
    import json

    log.info(f"🔍 Localizando elemento: '{alvo}' | contexto: '{contexto}'")

    # Passo 1: tira screenshot via executor Windows
    resultado_executor = enviar_comando("observar_tela", contexto=contexto)
    if not resultado_executor.get("sucesso"):
        erro = resultado_executor.get("mensagem", "Executor não respondeu")
        log.error(f"Executor falhou ao tirar screenshot: {erro}")
        return {"encontrado": False, "erro": erro, "confianca": "baixa", "motivo": erro}

    # Passo 2: pega caminho e converte para WSL (via path_utils)
    dados           = resultado_executor.get("dados", {})
    caminho_windows = dados.get("caminho_screenshot", "")
    if not caminho_windows:
        return {"encontrado": False, "erro": "Caminho da screenshot ausente", "confianca": "baixa"}

    caminho_wsl = windows_para_wsl(caminho_windows)
    if not caminho_wsl.exists():
        return {"encontrado": False, "erro": f"Screenshot não encontrado: {caminho_wsl}", "confianca": "baixa"}

    # Passo 3: codifica imagem
    with open(caminho_wsl, "rb") as f:
        imagem_b64 = base64.b64encode(f.read()).decode("utf-8")

    prompt  = PROMPT_LOCALIZAR_ELEMENTO.format(alvo=alvo, contexto=contexto)
    client  = _get_client()
    payload = [{
        "parts": [
            {"inline_data": {"mime_type": "image/png", "data": imagem_b64}},
            {"text": prompt},
        ]
    }]

    # Passo 4: chama Gemini Vision com retry em JSON inválido
    ultimo_erro = {}
    for tentativa in range(1, max_tentativas + 1):
        log.info(f"  🤖 Gemini Vision localizando '{alvo}' — tentativa {tentativa}/{max_tentativas}")
        try:
            response = client.models.generate_content(
                model=GEMINI_VISION_MODEL,
                contents=payload,
            )
            texto = response.text.strip()
            if texto.startswith("```"):
                texto = "\n".join(texto.split("\n")[1:-1])

            resultado = json.loads(texto)

            # Valida campos obrigatórios
            if "encontrado" not in resultado:
                raise ValueError("Campo 'encontrado' ausente na resposta")

            # Loga resultado
            if resultado["encontrado"]:
                log.info(
                    f"  🎯 Elemento encontrado: '{resultado.get('elemento')}' "
                    f"em ({resultado.get('x')}, {resultado.get('y')}) "
                    f"— confiança: {resultado.get('confianca')}"
                )

                # ── Cache cooperativo ──
                # Localizar NÃO usa cache para responder (gates críticos
                # exigem visão fresca a cada chamada — falso positivo aqui
                # faz o orquestrador seguir fluxo errado).
                # MAS, se Gemini encontrou com confiança media/alta, DOAMOS
                # a coordenada pro cache para um clicar_elemento_por_texto
                # futuro reaproveitar sem chamar Gemini de novo.
                conf = (resultado.get("confianca") or "").lower()
                x_loc = resultado.get("x")
                y_loc = resultado.get("y")
                if conf in ("alta", "media", "média") and x_loc is not None and y_loc is not None:
                    try:
                        registrar_via_localizar(
                            alvo=alvo,
                            contexto=contexto,
                            x=int(x_loc),
                            y=int(y_loc),
                            confianca=conf,
                        )
                    except Exception as e:
                        log.debug(f"  ⚠️ Falha ao doar ao cache cooperativo: {e}")
            else:
                log.warning(f"  🔍 Elemento não encontrado: {resultado.get('motivo','')[:80]}")
                log.debug("  ℹ️  Localizar não usa cache para responder gates")

            return resultado

        except json.JSONDecodeError as e:
            log.warning(f"  ⚠️ Tentativa {tentativa}: JSON inválido — {e}")
            ultimo_erro = {"encontrado": False, "erro": f"JSON inválido: {e}", "confianca": "baixa", "motivo": str(e)}

        except errors.ClientError as e:
            # PRIORIDADE: quota Gemini esgotada → retorno estruturado claro
            if _eh_erro_quota(e):
                retry_delay = _extrair_retry_delay(e)
                log.error(
                    f"  🚫 Gemini QUOTA EXCEDIDA durante localizar — "
                    f"abortando. retryDelay={retry_delay}s"
                )
                return {
                    "encontrado":  False,
                    "erro":        "quota_excedida",
                    "tipo":        "quota_excedida",
                    "confianca":   "baixa",
                    "motivo":      "Gemini quota excedida",
                    "retry_delay": retry_delay,
                    "detalhe":     str(e),
                }
            log.error(f"  ❌ Erro API Gemini: {e}")
            return {"encontrado": False, "erro": str(e), "confianca": "baixa", "motivo": str(e)}

        except Exception as e:
            log.error(f"  ❌ Erro inesperado: {e}")
            ultimo_erro = {"encontrado": False, "erro": str(e), "confianca": "baixa", "motivo": str(e)}

    log.error(f"🚫 Localização de '{alvo}' falhou após {max_tentativas} tentativas")
    return ultimo_erro


# =========================
# CLIQUE POR TEXTO
# Localiza + clica — com cache visual + proteções de segurança
# =========================

def clicar_elemento_por_texto(
    contexto: str,
    alvo: str,
    confianca_minima: str = "media",
    guard_aprovado: bool = False,
    usar_cache: bool = True,
    validar_pos_clique: Optional[bool] = None,
) -> dict:
    """
    Localiza um elemento pelo texto/descrição e clica nele via PyAutoGUI.
    Não clica se a confiança for baixa ou se detectar captcha/login.

    Estratégia em 2 níveis:
      1. Tenta cache visual primeiro (rápido, free)
      2. Se cache MISS ou cache FAIL → cai pra Gemini Vision (fallback premium)

    Validação semântica (CRÍTICO):
        "Clique executado pelo PyAutoGUI" NÃO significa "acertou o elemento certo".
        Para alvos como "Select file", "Publicar", etc., se a coordenada do cache
        estiver errada, o clique passa em coordenadas vazias e o PyAutoGUI marca
        sucesso — mas o efeito (diálogo, mudança de tela) nunca acontece.

        Quando validar_pos_clique=True, esta função:
          - Executa o clique
          - NÃO chama registrar_sucesso() automaticamente
          - Marca o clique como PENDENTE no cache (em memória)
          - Retorna aguardando_validacao=True
          - O caller (workflow / engine) é responsável por validar o efeito
            e chamar confirmar_clique_pendente() ou descartar_clique_pendente()

    Args:
        contexto:          descrição do momento (ex: "pagina_upload_tiktok")
        alvo:              texto do elemento (ex: "Select file")
        confianca_minima:  "media" | "alta". "baixa" nunca clica.
        guard_aprovado:    True se o Publish Guard aprovou (obrigatório p/ Publicar)
        usar_cache:        False força chamada Gemini (debug)
        validar_pos_clique:
            True  → não persiste sucesso, marca pendente, caller valida depois
            False → comportamento legacy (persiste sucesso na hora)
            None  → AUTO: True para alvos críticos conhecidos (Select file,
                    Publicar, Upload, etc), False para o resto

    Returns:
        dict com:
            sucesso              (bool)
            mensagem             (str)
            x, y                 (int)
            confianca            (str)
            bloqueado            (bool)
            via_cache            (bool)
            aguardando_validacao (bool)  — True se validar_pos_clique ativo
            chave_pendente       (str)   — chave usada pelo cache pendente
                                            (passar pra confirmar/descartar)
    """
    NIVEIS = {"baixa": 0, "media": 1, "média": 1, "alta": 2}

    # ── AUTO: decide se exige validação semântica ───────────────────
    if validar_pos_clique is None:
        validar_pos_clique = exige_validacao_semantica(alvo)
        if validar_pos_clique:
            log.info(
                f"  🛡️ Alvo '{alvo}' marcado como crítico — validação semântica EXIGIDA"
            )

    chave_pendente_retorno = None

    # ═══════════════════════════════════════════════════════════════
    # NÍVEL 1 — TENTAR CACHE VISUAL
    # ═══════════════════════════════════════════════════════════════
    if usar_cache:
        cached = buscar_elemento_cache(
            alvo=alvo,
            contexto=contexto,
            guard_aprovado=guard_aprovado,
        )

        if cached:
            # Verifica se a confiança salva atende o mínimo solicitado
            conf_cache = cached.get("confianca", "baixa")
            if NIVEIS.get(conf_cache, 0) >= NIVEIS.get(confianca_minima, 1):
                x, y = int(cached["x"]), int(cached["y"])
                log.info(f"  ⚡ Usando cache visual: '{alvo}' → ({x}, {y}) [conf={conf_cache}]")

                resultado_clique = enviar_comando("clicar", x=x, y=y)

                if resultado_clique.get("sucesso"):
                    log.info(f"  ✅ Clique via cache OK: '{alvo}' em ({x}, {y})")

                    if validar_pos_clique:
                        # Marca como pendente — caller decide se foi sucesso real
                        registrar_sucesso_pendente(alvo, contexto, x, y, conf_cache)
                        chave_pendente_retorno = f"{contexto}||{alvo}"
                    else:
                        # Comportamento legacy: confia no clique
                        registrar_sucesso(alvo, contexto, x, y, conf_cache)

                    return {
                        "sucesso":              True,
                        "mensagem":             f"Clicado em '{alvo}' via cache em ({x}, {y})",
                        "x":                    x,
                        "y":                    y,
                        "confianca":            conf_cache,
                        "bloqueado":            False,
                        "via_cache":            True,
                        "aguardando_validacao": bool(validar_pos_clique),
                        "chave_pendente":       chave_pendente_retorno,
                    }
                else:
                    # Cache falhou no clique — registra falha e cai pra Gemini
                    erro = resultado_clique.get("mensagem", "?")
                    log.warning(f"  ⚠️ Cache falhou no clique ({erro}), chamando Gemini...")
                    registrar_falha(alvo, contexto, motivo=f"Clique falhou: {erro}")
            else:
                log.info(
                    f"  ⚠️ Cache HIT mas confiança '{conf_cache}' < mínima '{confianca_minima}' — "
                    f"chamando Gemini"
                )

    # ═══════════════════════════════════════════════════════════════
    # NÍVEL 2 — GEMINI VISION (fallback premium)
    # ═══════════════════════════════════════════════════════════════
    log.info(f"  🤖 Cache MISS/INDISPONÍVEL — chamando Gemini Vision para '{alvo}'")

    loc = localizar_elemento_por_texto(contexto, alvo)

    # Erro técnico na localização
    if "erro" in loc and not loc.get("encontrado"):
        return {
            "sucesso":              False,
            "mensagem":             f"Falha na localização: {loc['erro']}",
            "bloqueado":            False,
            "via_cache":            False,
            "aguardando_validacao": False,
            "chave_pendente":       None,
        }

    # Detecta captcha / login / bloqueio
    motivo = loc.get("motivo", "").lower()
    alertas_bloqueio = ("captcha", "login", "sign in", "entrar", "verify", "bloqueado", "ban", "sessão")
    if any(p in motivo for p in alertas_bloqueio):
        log.error(f"🚨 Bloqueio detectado durante localização: {loc.get('motivo')}")
        return {
            "sucesso":              False,
            "mensagem":             f"Bloqueio detectado: {loc.get('motivo')}",
            "bloqueado":            True,
            "confianca":            loc.get("confianca"),
            "via_cache":            False,
            "aguardando_validacao": False,
            "chave_pendente":       None,
        }

    # Elemento não encontrado
    if not loc.get("encontrado"):
        return {
            "sucesso":              False,
            "mensagem":             f"Elemento '{alvo}' não encontrado na tela: {loc.get('motivo','')}",
            "bloqueado":            False,
            "confianca":            loc.get("confianca"),
            "via_cache":            False,
            "aguardando_validacao": False,
            "chave_pendente":       None,
        }

    # Confiança insuficiente — não clica
    confianca_atual = loc.get("confianca", "baixa")
    if NIVEIS.get(confianca_atual, 0) < NIVEIS.get(confianca_minima, 1):
        log.warning(
            f"⚠️ Confiança insuficiente para clicar: '{confianca_atual}' "
            f"(mínima: '{confianca_minima}') — abortando"
        )
        return {
            "sucesso":              False,
            "mensagem":             f"Confiança '{confianca_atual}' abaixo do mínimo '{confianca_minima}' — clique cancelado",
            "bloqueado":            False,
            "confianca":            confianca_atual,
            "x":                    loc.get("x"),
            "y":                    loc.get("y"),
            "via_cache":            False,
            "aguardando_validacao": False,
            "chave_pendente":       None,
        }

    # Tudo OK — clica
    x, y = int(loc["x"]), int(loc["y"])
    log.info(f"🖱️ Clicando em '{alvo}' → ({x}, {y}) [confiança: {confianca_atual}]")

    resultado_clique = enviar_comando("clicar", x=x, y=y)

    if resultado_clique.get("sucesso"):
        log.info(f"✅ Clique em '{alvo}' executado com sucesso")

        # ── Cache: pendente ou direto, conforme criticidade ──
        if usar_cache and NIVEIS.get(confianca_atual, 0) >= 1:
            if validar_pos_clique:
                registrar_sucesso_pendente(alvo, contexto, x, y, confianca_atual)
                chave_pendente_retorno = f"{contexto}||{alvo}"
            else:
                registrar_sucesso(alvo, contexto, x, y, confianca_atual)

        return {
            "sucesso":              True,
            "mensagem":             f"Clicado em '{loc.get('elemento', alvo)}' em ({x}, {y})",
            "x":                    x,
            "y":                    y,
            "confianca":            confianca_atual,
            "bloqueado":            False,
            "via_cache":            False,
            "aguardando_validacao": bool(validar_pos_clique),
            "chave_pendente":       chave_pendente_retorno,
        }
    else:
        log.error(f"❌ Executor falhou ao clicar: {resultado_clique.get('mensagem')}")
        return {
            "sucesso":              False,
            "mensagem":             f"Clique falhou: {resultado_clique.get('mensagem')}",
            "x":                    x,
            "y":                    y,
            "confianca":            confianca_atual,
            "bloqueado":            False,
            "via_cache":            False,
            "aguardando_validacao": False,
            "chave_pendente":       None,
        }