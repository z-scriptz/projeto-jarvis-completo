# brain/file_dialog_uploader.py
# Ação robusta de upload de arquivo no TikTok via diálogo do Windows.
#
# Substitui a sequência frágil:
#   clicar Select file → aguardar → digitar caminho → Enter
# que tinha 4 pontos de falha silenciosa:
#   1. diálogo de arquivo não abriu
#   2. diálogo abriu mas não estava focado
#   3. caminho foi digitado no lugar errado (campo de descrição do TikTok)
#   4. TikTok rejeitou o vídeo (codec, tamanho, formato)
#
# Esta ação valida CADA ETAPA antes de prosseguir:
#   0. Confirma que o arquivo existe, tem tamanho > 0 e é .mp4
#   1. AGUARDA upload page ESTABILIZAR (sem loading visível)  ← v2
#   2. Clica em "Select file" — com até 3 estratégias diferentes ← v2
#   3. Aguarda diálogo abrir
#   4. Valida que o diálogo do Windows abriu (pygetwindow OU Gemini)
#   5. Cola caminho via clipboard (pyperclip) com fallback pra digitar
#   6. Enter
#   7. Aguarda upload começar
#   8. Valida que upload realmente iniciou (Gemini observa tela mudou)
#
# v2 (este arquivo):
#   - Função aguardar_upload_pronto() que espera loading sumir antes de clicar
#   - Estratégia de clique em 3 níveis: alvo específico → texto genérico →
#     variação vertical da última coordenada
#   - Espera pós-clique aumentada de 1.5s para 2.5s
#
# Futuro (não implementado aqui):
#   - Provider Playwright que usaria input[type=file].set_input_files()
#     evitando completamente o diálogo do Windows. Refator grande,
#     fica pra próxima missão.

import os
import time
from pathlib import Path

from brain.commander import enviar_comando
from shared.logger import get_logger

log = get_logger(__name__)


# =================================================================
# CONFIGURAÇÃO
# =================================================================

ESPERA_POS_CLIQUE_BOTAO = 2.5   # tempo p/ diálogo abrir (era 1.5s, subiu)
ESPERA_POS_COLAR        = 0.3   # texto aparecer no campo
ESPERA_POS_ENTER        = 3.0   # upload iniciar

# Estabilização: quanto tentar esperar a página parar de carregar
ESTABILIZACAO_MAX_TENT  = 5
ESTABILIZACAO_DELAY     = 2.0

# Variação vertical entre tentativas de clique (px)
# Botões do TikTok têm ~50px de altura, então +/-20px ainda pega o botão
# se o Gemini estiver retornando o topo do texto em vez do centro do botão
VARIACAO_Y_FALLBACK = 20

# Títulos esperados do diálogo de arquivo (PT-BR e EN)
TITULOS_DIALOGO_ARQUIVO = (
    "abrir", "open",
    "selecionar arquivo", "select file",
    "escolher arquivo", "choose file",
    "carregar", "upload",
)

# Indicadores de "ainda carregando" que o Gemini pode mencionar
# Termos de loading com 2 níveis:
#   FORTE = quase certeza de loading bloqueante na tela (overlay, spinner central, etc)
#   FRACO = palavras genéricas que podem aparecer em motivos NEGADOS
#           ("...SEM loading visível", "não há spinner") — não confiar
#
# Regra (em aguardar_upload_pronto):
#   - encontrado=False + motivo com FRACO  → aguardar
#   - encontrado=True + FORTE              → aguardar (página ainda não pronta)
#   - encontrado=True + confiança alta     → PRONTO (ignora FRACO)
#   - encontrado=True + confiança media    → PRONTO se não tiver FORTE
TERMOS_LOADING_FORTE = (
    "tela está em estado de carregamento",
    "spinner no centro",
    "spinner central",
    "indicador de carregamento no centro",
    "loading principal",
    "página ainda carregando",
    "conteúdo bloqueado por loading",
    "overlay de carregamento",
)
TERMOS_LOADING_FRACO = (
    "loading",
    "carregando",
    "spinner",
    "aguardando",
    "carregamento",
)

# Termos que indicam popup/modal de descarte do TikTok que pode bloquear o upload.
# Crítico: priorizar "Continuar editando"/"Cancel"/"Cancelar" — NUNCA "Descartar"/
# "Discard"/"Leave"/"Sair" automaticamente (pode apagar o vídeo já uploadado).
POPUP_BOTOES_PREFERIDOS = (   # ordem de preferência — clica no primeiro que achar
    "Continuar editando",
    "Continue editing",
    "Cancelar",
    "Cancel",
)
POPUP_BOTOES_PROIBIDOS = (    # NUNCA clica automaticamente nestes
    "Descartar",
    "Discard",
    "Sair",
    "Leave",
    "Save draft",
    "Salvar rascunho",
)
# Títulos de janela que sugerem modal/popup do TikTok ativo (heurística barata,
# sem chamar Gemini). Janelas do diálogo de arquivo ("Abrir"/"Open") são tratadas
# separadamente — aqui só estamos atrás de popups DENTRO do TikTok.
POPUP_TITULOS_SUSPEITOS = (
    "descartar",
    "discard",
    "sair",
    "leave",
)

# Extensões aceitas pelo TikTok
EXTENSOES_VALIDAS = (".mp4", ".mov", ".webm", ".avi")


# =================================================================
# VALIDAÇÃO DO ARQUIVO DE VÍDEO
# =================================================================

def _validar_arquivo_video(video_path_windows: str) -> dict:
    """
    Confere antes de tentar upload:
      - arquivo existe
      - tamanho > 0
      - extensão suportada
    Detecta WSL vs Windows automaticamente.
    """
    if not video_path_windows:
        return {"valido": False, "motivo": "video_path vazio"}

    if os.name == "nt":
        path_local = Path(video_path_windows)
    else:
        try:
            from shared.path_utils import windows_to_wsl_path
            path_local = Path(windows_to_wsl_path(video_path_windows))
        except Exception:
            path_local = Path(video_path_windows)

    if not path_local.exists():
        return {"valido": False, "motivo": f"Arquivo não existe: {path_local}"}

    try:
        tamanho = path_local.stat().st_size
    except Exception as e:
        return {"valido": False, "motivo": f"Erro ao ler tamanho: {e}"}

    if tamanho == 0:
        return {"valido": False, "motivo": f"Arquivo vazio (0 bytes): {path_local}"}

    if path_local.suffix.lower() not in EXTENSOES_VALIDAS:
        return {
            "valido": False,
            "motivo": f"Extensão '{path_local.suffix}' não suportada (válidas: {EXTENSOES_VALIDAS})",
        }

    if tamanho < 50_000:
        log.warning(
            f"  ⚠️  Vídeo muito pequeno ({tamanho/1024:.1f} KB) — "
            f"pode estar corrompido"
        )

    log.info(
        f"  📁 Arquivo OK: {path_local.name} "
        f"({tamanho/1024:.1f} KB, ext={path_local.suffix})"
    )
    return {
        "valido":        True,
        "motivo":        f"OK — {tamanho} bytes, {path_local.suffix}",
        "tamanho_bytes": tamanho,
        "extensao":      path_local.suffix,
    }


# =================================================================
# DETECÇÃO E RESOLUÇÃO DE POPUP TIKTOK (v3)
# =================================================================
#
# Cenário real visto em produção: após clicar em "Selecionar vídeo" e o
# diálogo NÃO abrir, o Gemini observou a tela e relatou "pop-up de
# confirmação de descarte de publicação". Isso bloqueia o fluxo porque:
#   1. O clique no botão Selecionar vídeo é "absorvido" pelo modal
#   2. Próximos cliques caem no modal e não na página
#   3. Se clicarmos "Descartar" automaticamente, perdemos o vídeo já uploadado
#
# Estratégia:
#   - heurística barata primeiro (janela_ativa) — sem Gemini
#   - se janela_ativa não revelar nada, chamar Gemini 1x para confirmar
#   - SE popup detectado: clicar em "Continuar editando" ou "Cancelar"
#     (NUNCA em "Descartar" automaticamente — pode apagar o trabalho)

def _checar_popup_via_janela_ativa() -> dict:
    """
    Heurística barata (sem Gemini): janela_ativa revela um título de modal?
    Returns: {"suspeito": bool, "titulo": str, "metodo": "pygetwindow"}
    """
    resultado = enviar_comando("janela_ativa")
    if not resultado.get("sucesso"):
        return {"suspeito": False, "titulo": "", "metodo": "pygetwindow_indisponivel"}

    titulo = ((resultado.get("dados", {}) or {}).get("titulo") or "").lower().strip()
    suspeito = any(t in titulo for t in POPUP_TITULOS_SUSPEITOS)
    return {"suspeito": suspeito, "titulo": titulo, "metodo": "pygetwindow"}


def _localizar_botao_popup_preferido() -> dict:
    """
    Chama Gemini Vision UMA vez procurando especificamente um dos botões
    preferidos (Continuar editando / Cancel). Retorno padrão do localizar.
    """
    from brain.vision_analyzer import localizar_elemento_por_texto

    alvo = (
        "botão 'Continuar editando' / 'Continue editing' / 'Cancelar' / 'Cancel' "
        "dentro de um popup/modal do TikTok que pergunta sobre descartar publicação. "
        "Quero o botão que MANTÉM a edição atual, NÃO o que descarta."
    )
    return localizar_elemento_por_texto(
        contexto="popup_tiktok_botao_preferido",
        alvo=alvo,
    )


def detectar_e_resolver_popup_tiktok(usar_gemini_se_necessario: bool = True) -> dict:
    """
    Detecta e tenta resolver popup/modal de descarte do TikTok.

    Fluxo:
      1. Tira screenshot para evidência (antes)
      2. Checagem barata via janela_ativa (heurística — sem Gemini)
      3. Se nada conclusivo e usar_gemini_se_necessario=True, chama Gemini
      4. Se localizou botão preferido, clica nele
      5. Tira screenshot depois para validar
      6. Retorna estrutura clara

    NUNCA clica em botões PROIBIDOS (Descartar/Discard/Leave/Sair/Save draft).

    Args:
        usar_gemini_se_necessario: se True, faz fallback Gemini quando
            a heurística barata não conclui (custa 1 chamada Gemini).

    Returns:
        {
            "popup_detectado": bool,
            "resolvido":       bool,
            "metodo_deteccao": str,
            "botao_clicado":   str | None,
            "motivo":          str,
        }
    """
    log.info("🪟 Verificando popup/modal TikTok...")
    enviar_comando("screenshot", contexto="popup_tiktok_antes_resolver")

    # ── Etapa 1: heurística barata via janela ativa ──
    via_janela = _checar_popup_via_janela_ativa()
    log.info(
        f"  Janela ativa: '{via_janela['titulo']}' "
        f"(suspeito={via_janela['suspeito']}, método={via_janela['metodo']})"
    )

    # Se janela_ativa indisponível, dependemos do Gemini (se permitido)
    if via_janela["metodo"] == "pygetwindow_indisponivel" and not usar_gemini_se_necessario:
        return {
            "popup_detectado": False,
            "resolvido":       False,
            "metodo_deteccao": "indisponivel",
            "botao_clicado":   None,
            "motivo":          "janela_ativa indisponível e Gemini desativado",
        }

    # Se a janela é o diálogo de arquivo (Abrir/Open), NÃO é popup de descarte —
    # é o diálogo desejado. Tratado em outro lugar.
    titulo_lower = via_janela["titulo"]
    if any(t in titulo_lower for t in ("abrir", "open")):
        return {
            "popup_detectado": False,
            "resolvido":       False,
            "metodo_deteccao": "janela_eh_dialogo_arquivo",
            "botao_clicado":   None,
            "motivo":          "Janela ativa é o diálogo de arquivo desejado, não popup",
        }

    # ── Etapa 2: Gemini Vision pra confirmar e localizar o botão preferido ──
    if not usar_gemini_se_necessario and not via_janela["suspeito"]:
        return {
            "popup_detectado": False,
            "resolvido":       False,
            "metodo_deteccao": "janela_nao_suspeita",
            "botao_clicado":   None,
            "motivo":          "Nenhum sinal de popup pela janela e Gemini desabilitado",
        }

    loc = _localizar_botao_popup_preferido()

    # Caso especial: quota
    if (loc.get("tipo") or "").lower() == "quota_excedida":
        return {
            "popup_detectado": via_janela["suspeito"],
            "resolvido":       False,
            "metodo_deteccao": "gemini_quota",
            "botao_clicado":   None,
            "motivo":          "Quota Gemini excedida durante verificação de popup",
        }

    if not loc.get("encontrado"):
        log.info(f"  ✓ Nenhum botão de popup detectado pelo Gemini")
        return {
            "popup_detectado": False,
            "resolvido":       False,
            "metodo_deteccao": "gemini_nao_encontrou",
            "botao_clicado":   None,
            "motivo":          "Gemini não identificou popup/modal",
        }

    # Gemini achou — verifica se o que ele localizou bate com botão preferido,
    # NÃO com botão proibido (proteção contra clicar em "Descartar").
    elemento_encontrado = (loc.get("elemento") or "").lower()
    eh_proibido = any(t.lower() in elemento_encontrado for t in POPUP_BOTOES_PROIBIDOS)

    if eh_proibido:
        log.warning(
            f"  ⛔ Gemini localizou botão PROIBIDO ('{loc.get('elemento')}') — "
            f"recusando clicar pra não perder o vídeo"
        )
        return {
            "popup_detectado": True,
            "resolvido":       False,
            "metodo_deteccao": "gemini_localizou_proibido",
            "botao_clicado":   None,
            "motivo":          f"Botão proibido detectado: '{loc.get('elemento')}' — operador humano deve intervir",
        }

    confianca = (loc.get("confianca") or "baixa").lower()
    if confianca == "baixa":
        log.info(f"  ⏭️  Botão localizado com confiança baixa — não clicando por segurança")
        return {
            "popup_detectado": False,
            "resolvido":       False,
            "metodo_deteccao": "gemini_confianca_baixa",
            "botao_clicado":   None,
            "motivo":          "Confiança baixa na detecção, abortando clique",
        }

    # ── Etapa 3: clica no botão preferido ──
    x, y = loc.get("x"), loc.get("y")
    log.info(f"  ✅ Popup TikTok detectado — clicando '{loc.get('elemento')}' em ({x}, {y})")
    enviar_comando("clicar", x=x, y=y)
    time.sleep(1.5)
    enviar_comando("screenshot", contexto="popup_tiktok_apos_resolver")

    log.info(f"  ✓ Popup resolvido com clique em '{loc.get('elemento')}'")
    return {
        "popup_detectado": True,
        "resolvido":       True,
        "metodo_deteccao": "gemini_localizou_preferido",
        "botao_clicado":   loc.get("elemento"),
        "motivo":          f"Clicado em '{loc.get('elemento')}' para manter o trabalho",
    }


# =================================================================
# AGUARDAR PÁGINA ESTABILIZAR (NOVA EM v2)
# =================================================================

def aguardar_upload_pronto(
    max_tentativas: int = ESTABILIZACAO_MAX_TENT,
    delay: float = ESTABILIZACAO_DELAY,
) -> dict:
    """
    Espera a página de upload do TikTok estabilizar antes de clicar em Select file.

    Problema que isso resolve: o orquestrador clicava no Select file enquanto
    a página ainda carregava. Gemini via "Selecionar vídeo" no DOM mas o
    botão real ainda não estava clicável (estava por trás de um overlay
    de loading).

    Estratégia: pergunta ao Gemini se vê o botão SEM loading visível.
    Se ainda houver loading, aguarda e tenta de novo.

    Args:
        max_tentativas: quantas vezes verificar
        delay:          segundos entre tentativas

    Returns:
        {
            "pronto":       bool,
            "tentativas":   int,
            "motivo":       str,
            "coordenada":   {"x": int, "y": int} | None  ← se já achou
        }
    """
    from brain.vision_analyzer import localizar_elemento_por_texto

    log.info(f"⏳ Aguardando upload page estabilizar (até {max_tentativas} tentativas)...")

    alvo_estabilidade = (
        "botão clicável de selecionar arquivo / Select file / Selecionar vídeo, "
        "que abre o diálogo do Windows para escolher vídeo. "
        "Botão totalmente carregado, SEM indicador de loading/spinner/carregando visível."
    )

    ultimo_motivo = "não tentado"
    for tentativa in range(1, max_tentativas + 1):
        log.info(f"  🔄 Estabilização — tentativa {tentativa}/{max_tentativas}")

        loc = localizar_elemento_por_texto(
            contexto="aguardando_upload_estabilizar",
            alvo=alvo_estabilidade,
        )

        # ── CHECAGEM ESPECIAL: quota Gemini esgotada ──
        # Sem isso, o sistema confunde quota com "loading persistente" e
        # gasta retries inúteis. Quota é condição operacional — abortar limpo.
        tipo_erro = (loc.get("tipo") or "").lower()
        erro_str  = (loc.get("erro") or "").lower()
        motivo_loc = (loc.get("motivo") or "").lower()
        if (
            tipo_erro == "quota_excedida"
            or "quota_excedida" in erro_str
            or "quota" in erro_str
            or "resource_exhausted" in motivo_loc
            or "resource_exhausted" in erro_str
        ):
            retry_delay = loc.get("retry_delay")
            log.error(
                f"  🚫 Gemini sem quota durante estabilização — "
                f"abortando aguardar_upload_pronto. retryDelay={retry_delay}s"
            )
            return {
                "pronto":      False,
                "erro":        "quota_excedida",
                "tentativas":  tentativa,
                "motivo":      "Gemini sem quota — tente novamente quando a cota renovar",
                "retry_delay": retry_delay,
                "coordenada":  None,
            }

        encontrado = bool(loc.get("encontrado"))
        confianca  = (loc.get("confianca") or "baixa").lower()
        motivo     = (loc.get("motivo") or "").lower()
        ultimo_motivo = motivo or "?"

        # Critério 1: tem que estar encontrado
        if not encontrado:
            log.info(f"  ⏸️  Botão ainda não visível: {motivo[:80]}")
            if tentativa < max_tentativas:
                time.sleep(delay)
            continue

        # Critério 2: confiança aceitável
        if confianca == "baixa":
            log.info(f"  ⏸️  Confiança baixa, página instável")
            if tentativa < max_tentativas:
                time.sleep(delay)
            continue

        # Critério 3: refinado — distingue loading FORTE (real) de FRACO (palavra genérica
        # que pode aparecer em motivos NEGADOS tipo "SEM carregamento visível").
        # Regra:
        #   - confiança alta:  só FORTE bloqueia, FRACO é ignorado
        #   - confiança media: só FORTE bloqueia
        # Razão: Gemini retornando "encontrado=True com confiança alta" já é forte
        # evidência de que o botão está clicável; é falso-negativo bloquear por
        # menção genérica à palavra "loading" no fim de uma frase positiva.
        tem_forte = any(termo in motivo for termo in TERMOS_LOADING_FORTE)
        tem_fraco = any(termo in motivo for termo in TERMOS_LOADING_FRACO)

        if tem_forte:
            log.info(f"  ⏸️  Loading FORTE detectado no motivo: '{motivo[:80]}'")
            if tentativa < max_tentativas:
                time.sleep(delay)
            continue

        if tem_fraco:
            # FRACO presente — provavelmente menção em frase negada.
            # Continua, mas registra pra debug.
            log.info(
                f"  ✓ Loading fraco ignorado porque botão está com confiança "
                f"{confianca} (motivo: '{motivo[:60]}...')"
            )

        # ✅ Tudo OK — página pronta
        x = loc.get("x")
        y = loc.get("y")
        log.info(
            f"  ✅ Página estabilizada na tentativa {tentativa}: "
            f"botão em ({x}, {y}), confiança={confianca}"
        )
        return {
            "pronto":     True,
            "tentativas": tentativa,
            "motivo":     "Botão estável e clicável detectado",
            "coordenada": {"x": x, "y": y} if (x is not None and y is not None) else None,
        }

    # Esgotou tentativas
    log.error(f"❌ Página não estabilizou após {max_tentativas} tentativas")
    return {
        "pronto":     False,
        "tentativas": max_tentativas,
        "motivo":     f"Loading persistente após {max_tentativas} tentativas — último motivo: {ultimo_motivo[:120]}",
        "coordenada": None,
    }


# =================================================================
# VALIDAÇÃO 1 — JANELA ATIVA (via executor Windows)
# =================================================================

def _validar_dialogo_via_pygetwindow() -> dict:
    """
    Pede ao executor Windows pra checar o título da janela ativa.
    Se contiver "Abrir"/"Open"/etc, é diálogo de arquivo. GRÁTIS — sem Gemini.
    """
    resultado = enviar_comando("janela_ativa")

    if not resultado.get("sucesso"):
        log.debug(
            f"  ℹ️  Executor não suporta 'janela_ativa' "
            f"({(resultado.get('mensagem') or '?')[:60]})"
        )
        return {
            "metodo":         "pygetwindow",
            "disponivel":     False,
            "dialogo_aberto": None,
            "titulo_ativo":   "",
        }

    titulo = (resultado.get("dados", {}) or {}).get("titulo", "").strip()
    if not titulo:
        return {
            "metodo":         "pygetwindow",
            "disponivel":     True,
            "dialogo_aberto": False,
            "titulo_ativo":   "",
        }

    titulo_lower = titulo.lower()
    eh_dialogo = any(t in titulo_lower for t in TITULOS_DIALOGO_ARQUIVO)

    log.info(
        f"  🪟 Janela ativa: '{titulo}' → "
        f"{'É diálogo de arquivo ✅' if eh_dialogo else 'NÃO é diálogo ❌'}"
    )

    return {
        "metodo":         "pygetwindow",
        "disponivel":     True,
        "dialogo_aberto": eh_dialogo,
        "titulo_ativo":   titulo,
    }


# =================================================================
# VALIDAÇÃO 2 — GEMINI VISION (fallback)
# =================================================================

def _validar_dialogo_via_gemini() -> dict:
    """
    Verifica via Gemini Vision se o diálogo de arquivo está visível.
    Custa 1 chamada Gemini (~0.07% da cota diária do flash-lite).
    """
    from brain.vision_analyzer import localizar_elemento_por_texto

    alvo = (
        "diálogo de arquivo do Windows com campo 'Nome do arquivo' / 'File name' "
        "e botão 'Abrir' / 'Open'"
    )
    loc = localizar_elemento_por_texto(
        contexto="dialogo_arquivo_pos_click",
        alvo=alvo,
    )

    encontrado = bool(loc.get("encontrado"))
    confianca  = loc.get("confianca", "baixa")

    if encontrado and confianca == "baixa":
        log.warning(f"  ⚠️ Gemini diz 'encontrado' com confiança baixa — tratando como NÃO aberto")
        encontrado = False

    return {
        "metodo":         "gemini_vision",
        "disponivel":     True,
        "dialogo_aberto": encontrado,
        "confianca":      confianca,
        "motivo":         (loc.get("motivo", "") or "")[:120],
    }


def validar_dialogo_arquivo_aberto() -> dict:
    """
    Valida se o diálogo do Windows realmente abriu após clicar em Select file.
    Tenta pygetwindow primeiro (free) e cai pra Gemini Vision se necessário.

    Returns:
        {
            "sucesso":      bool,
            "mensagem":     str,
            "metodo_usado": str,
            "titulo_ativo": str,
            "dados":        dict,
        }
    """
    log.info("🔎 Validando se diálogo de arquivo está aberto...")

    via_window = _validar_dialogo_via_pygetwindow()

    if via_window["disponivel"] and via_window["dialogo_aberto"] is True:
        return {
            "sucesso":      True,
            "mensagem":     f"Diálogo aberto (janela ativa: '{via_window['titulo_ativo']}')",
            "metodo_usado": "pygetwindow",
            "titulo_ativo": via_window["titulo_ativo"],
            "dados":        via_window,
        }

    if via_window["disponivel"]:
        log.warning(
            f"  ⚠️  Janela ativa '{via_window['titulo_ativo']}' não parece diálogo — "
            f"confirmando com Gemini Vision..."
        )

    via_gemini = _validar_dialogo_via_gemini()
    sucesso = bool(via_gemini.get("dialogo_aberto"))

    return {
        "sucesso":      sucesso,
        "mensagem":     (
            "Diálogo confirmado por Gemini Vision"
            if sucesso
            else f"Diálogo NÃO aberto: {via_gemini.get('motivo', '?')}"
        ),
        "metodo_usado": "gemini_vision",
        "titulo_ativo": via_window.get("titulo_ativo", ""),
        "dados":        {"pygetwindow": via_window, "gemini": via_gemini},
    }


# =================================================================
# CLIQUE EM SELECT FILE (NOVO EM v2 — 3 ESTRATÉGIAS)
# =================================================================

def _clicar_select_file_estrategia_1(coordenada_pre_localizada: dict) -> dict:
    """
    Estratégia 1: usa coordenada já encontrada pela aguardar_upload_pronto().
    Mais barato — não chama Gemini de novo, só clica.
    """
    if not coordenada_pre_localizada:
        return {"sucesso": False, "mensagem": "Sem coordenada pré-localizada", "estrategia": 1}

    x = coordenada_pre_localizada["x"]
    y = coordenada_pre_localizada["y"]
    log.info(f"  🎯 Estratégia 1: clicar em coordenada pré-localizada ({x}, {y})")

    resultado = enviar_comando("clicar", x=x, y=y)
    return {
        "sucesso":    resultado.get("sucesso", False),
        "mensagem":   resultado.get("mensagem", ""),
        "x":          x,
        "y":          y,
        "estrategia": 1,
    }


def _clicar_select_file_estrategia_2() -> dict:
    """
    Estratégia 2: pede ao Gemini para localizar com prompt MAIS ESPECÍFICO,
    enfatizando "área/botão CLICÁVEL" e não apenas o texto.
    """
    from brain.vision_analyzer import clicar_elemento_por_texto

    log.info(f"  🎯 Estratégia 2: clique via Gemini com alvo específico de área clicável")

    alvo_especifico = (
        "botão clicável de selecionar arquivo do TikTok, "
        "área retangular destacada (geralmente azul ou roxo) "
        "que ao ser clicada abre o diálogo do Windows para escolher vídeo. "
        "NÃO o texto solto 'Select file' — o BOTÃO INTEIRO ou DROPZONE clicável."
    )

    resultado = clicar_elemento_por_texto(
        contexto="pagina_upload_tiktok_botao_real",
        alvo=alvo_especifico,
        confianca_minima="alta",
        usar_cache=False,
        validar_pos_clique=False,
    )

    return {
        "sucesso":    resultado.get("sucesso", False),
        "mensagem":   resultado.get("mensagem", ""),
        "x":          resultado.get("x"),
        "y":          resultado.get("y"),
        "estrategia": 2,
    }


def _clicar_select_file_estrategia_3(ultima_x: int, ultima_y: int) -> dict:
    """
    Estratégia 3: variação vertical da última coordenada.
    Se Gemini retornou (528, 621) e não funcionou, o botão real pode estar
    +/-20px abaixo (o centro do botão estilizado em vez do topo do texto).
    Tenta primeiro +20 (abaixo), depois -20 (acima).
    """
    log.info(
        f"  🎯 Estratégia 3: variação vertical da última coord ({ultima_x}, {ultima_y})"
    )

    for offset in (VARIACAO_Y_FALLBACK, -VARIACAO_Y_FALLBACK):
        novo_y = ultima_y + offset
        log.info(f"     Tentando ({ultima_x}, {novo_y}) [offset={offset:+d}px]")

        resultado = enviar_comando("clicar", x=ultima_x, y=novo_y)
        if resultado.get("sucesso"):
            # Espera pra UI estabilizar antes de validar
            # (mesma espera das estratégias 1 e 2, pra consistência)
            time.sleep(ESPERA_POS_CLIQUE_BOTAO)
            val = validar_dialogo_arquivo_aberto()
            if val.get("sucesso"):
                log.info(f"  ✅ Variação Y={offset:+d} acertou! Diálogo abriu.")
                return {
                    "sucesso":           True,
                    "mensagem":          f"Variação Y={offset:+d}px funcionou",
                    "x":                 ultima_x,
                    "y":                 novo_y,
                    "estrategia":        3,
                    "validacao_dialogo": val,
                }
            log.info(f"     Variação Y={offset:+d} não abriu diálogo, tentando outra")

    return {
        "sucesso":           False,
        "mensagem":          "Nenhuma variação vertical abriu o diálogo",
        "estrategia":        3,
        "validacao_dialogo": None,
    }


def _clicar_select_file_com_estrategias(coord_pre: dict) -> dict:
    """
    Tenta clicar no Select file usando até 3 estratégias diferentes,
    validando o diálogo entre cada uma. Para na primeira que abrir o diálogo.

    Args:
        coord_pre: coordenada já localizada por aguardar_upload_pronto()
                   (pode ser None se não conseguiu pré-localizar)

    Returns:
        dict com sucesso, qual estratégia funcionou, e validação do diálogo
    """
    ultima_x, ultima_y = None, None
    historico_estrategias = []

    # ── Estratégia 1: coordenada já localizada ─────────────────────
    if coord_pre:
        r1 = _clicar_select_file_estrategia_1(coord_pre)
        historico_estrategias.append(r1)
        ultima_x, ultima_y = r1.get("x"), r1.get("y")

        if r1.get("sucesso"):
            log.info(f"     Aguardando {ESPERA_POS_CLIQUE_BOTAO}s pra ver se diálogo abriu...")
            time.sleep(ESPERA_POS_CLIQUE_BOTAO)
            val = validar_dialogo_arquivo_aberto()
            if val.get("sucesso"):
                log.info(f"  ✅ Estratégia 1 funcionou — diálogo aberto")
                return {
                    "sucesso":              True,
                    "estrategia_vencedora": 1,
                    "x":                    ultima_x,
                    "y":                    ultima_y,
                    "historico":            historico_estrategias,
                    "validacao_dialogo":    val,
                }
            log.warning(f"  ⚠️ Estratégia 1: clique passou mas diálogo NÃO abriu")
            enviar_comando("screenshot", contexto="apos_estrategia_1_sem_dialogo")

            # Pode ser popup do TikTok bloqueando — tenta resolver antes de partir
            # pra estratégia 2 (mais custosa em Gemini)
            popup_check = detectar_e_resolver_popup_tiktok(usar_gemini_se_necessario=True)
            if popup_check.get("resolvido"):
                log.info(f"  🔁 Repetindo clique após resolver popup ({coord_pre['x']}, {coord_pre['y']})")
                enviar_comando("clicar", x=coord_pre["x"], y=coord_pre["y"])
                time.sleep(ESPERA_POS_CLIQUE_BOTAO)
                val_pos_popup = validar_dialogo_arquivo_aberto()
                if val_pos_popup.get("sucesso"):
                    log.info(f"  ✅ Diálogo abriu após resolver popup — vitória da estratégia 1+popup")
                    return {
                        "sucesso":              True,
                        "estrategia_vencedora": "1+popup",
                        "x":                    coord_pre["x"],
                        "y":                    coord_pre["y"],
                        "historico":            historico_estrategias + [{"acao": "popup_resolvido", "info": popup_check}],
                        "validacao_dialogo":    val_pos_popup,
                    }
                log.warning(f"  ⚠️ Popup resolvido mas diálogo ainda não abriu — seguindo pra estratégia 2")

    # ── Estratégia 2: Gemini com prompt específico de "botão clicável" ──
    r2 = _clicar_select_file_estrategia_2()
    historico_estrategias.append(r2)
    if r2.get("x") is not None:
        ultima_x, ultima_y = r2.get("x"), r2.get("y")

    if r2.get("sucesso"):
        log.info(f"     Aguardando {ESPERA_POS_CLIQUE_BOTAO}s pra ver se diálogo abriu...")
        time.sleep(ESPERA_POS_CLIQUE_BOTAO)
        val = validar_dialogo_arquivo_aberto()
        if val.get("sucesso"):
            log.info(f"  ✅ Estratégia 2 funcionou — diálogo aberto")
            return {
                "sucesso":              True,
                "estrategia_vencedora": 2,
                "x":                    ultima_x,
                "y":                    ultima_y,
                "historico":            historico_estrategias,
                "validacao_dialogo":    val,
            }
        log.warning(f"  ⚠️ Estratégia 2: clique passou mas diálogo NÃO abriu")
        enviar_comando("screenshot", contexto="apos_estrategia_2_sem_dialogo")

        # Mesmo tratamento — popup pode ter aparecido entre estratégia 1 e 2
        popup_check2 = detectar_e_resolver_popup_tiktok(usar_gemini_se_necessario=True)
        if popup_check2.get("resolvido") and ultima_x is not None:
            log.info(f"  🔁 Repetindo clique após resolver popup ({ultima_x}, {ultima_y})")
            enviar_comando("clicar", x=ultima_x, y=ultima_y)
            time.sleep(ESPERA_POS_CLIQUE_BOTAO)
            val_pos_popup = validar_dialogo_arquivo_aberto()
            if val_pos_popup.get("sucesso"):
                log.info(f"  ✅ Diálogo abriu após resolver popup — vitória da estratégia 2+popup")
                return {
                    "sucesso":              True,
                    "estrategia_vencedora": "2+popup",
                    "x":                    ultima_x,
                    "y":                    ultima_y,
                    "historico":            historico_estrategias + [{"acao": "popup_resolvido", "info": popup_check2}],
                    "validacao_dialogo":    val_pos_popup,
                }

    # ── Estratégia 3: variação vertical da última coordenada conhecida ──
    if ultima_x is not None and ultima_y is not None:
        r3 = _clicar_select_file_estrategia_3(ultima_x, ultima_y)
        historico_estrategias.append(r3)
        if r3.get("sucesso"):
            return {
                "sucesso":              True,
                "estrategia_vencedora": 3,
                "x":                    r3.get("x"),
                "y":                    r3.get("y"),
                "historico":            historico_estrategias,
                "validacao_dialogo":    r3.get("validacao_dialogo"),
            }
    else:
        log.warning("  ⚠️ Estratégia 3 pulada — sem coordenada base para variar")

    # ── Falhou tudo ─────────────────────────────────────────────────
    return {
        "sucesso":              False,
        "estrategia_vencedora": None,
        "historico":            historico_estrategias,
        "mensagem":             "Nenhuma das 3 estratégias abriu o diálogo de arquivo",
    }


# =================================================================
# COLAR CAMINHO VIA CLIPBOARD
# =================================================================

def _colar_caminho_via_clipboard(video_path: str) -> dict:
    """
    Copia o caminho pro clipboard e cola com Ctrl+V.
    Fallback: digitar caractere por caractere.
    """
    resultado_copy = enviar_comando("copiar_clipboard", texto=video_path)

    if resultado_copy.get("sucesso"):
        log.info(f"  📋 Caminho copiado pro clipboard: {video_path}")
        time.sleep(ESPERA_POS_COLAR)
        resultado_paste = enviar_comando("atalho", teclas=["ctrl", "v"])
        if resultado_paste.get("sucesso"):
            log.info("  ✅ Ctrl+V executado")
            return {"sucesso": True, "metodo": "clipboard"}
        log.warning(f"  ⚠️ Ctrl+V falhou: {resultado_paste.get('mensagem')}")

    log.info(f"  ⌨️  Fallback — digitando caminho caractere a caractere")
    resultado_digit = enviar_comando("digitar", texto=video_path)
    return {
        "sucesso": resultado_digit.get("sucesso", False),
        "metodo":  "digitar",
        "erro":    resultado_digit.get("mensagem") if not resultado_digit.get("sucesso") else None,
    }


# =================================================================
# FUNÇÃO PRINCIPAL (v2)
# =================================================================

def selecionar_arquivo_upload_tiktok(video_path: str) -> dict:
    """
    Fluxo completo de seleção de arquivo no TikTok upload (v2).

    Cada etapa valida antes da próxima:
      0. Valida arquivo de vídeo
      1. ⭐ Aguarda página estabilizar (espera loading sumir)
      2. ⭐ Clica em Select file com até 3 estratégias diferentes
      3. Valida que diálogo abriu (pygetwindow → Gemini)
      4. Cola caminho via clipboard
      5. Enter
      6. Aguarda upload começar
      7. Valida que upload realmente iniciou

    ⭐ = novidades em v2 que resolvem o problema do orquestrador

    Returns:
        {
            "sucesso":     bool,
            "mensagem":    str,
            "etapa_falha": str | None,
            "dados":       dict,
        }
    """
    log.info("═" * 60)
    log.info("📤 SELECIONAR ARQUIVO UPLOAD TIKTOK (v2)")
    log.info(f"   Arquivo: {video_path}")
    log.info("═" * 60)

    dados: dict = {}

    # ── 0. Valida arquivo ──────────────────────────────────────────
    log.info("\n0️⃣  Validando arquivo de vídeo...")
    val_arquivo = _validar_arquivo_video(video_path)
    dados["validacao_arquivo"] = val_arquivo

    if not val_arquivo["valido"]:
        return _falhou(dados, "validacao_arquivo", val_arquivo["motivo"])

    # ── 0.5. Verificação prévia de popup TikTok (heurística barata) ──
    # Antes de tentar estabilizar a página, conferimos rapidamente se NÃO há
    # popup/modal bloqueando. Usamos só heurística barata (sem Gemini) aqui
    # pra economizar cota — Gemini só será chamado se janela_ativa for
    # explicitamente suspeita.
    log.info("\n0️⃣ .5  Verificação prévia de popup TikTok...")
    popup_pre = detectar_e_resolver_popup_tiktok(usar_gemini_se_necessario=False)
    dados["popup_pre"] = popup_pre
    if popup_pre.get("resolvido"):
        log.info(f"  ✅ Popup resolvido antes da estabilização: {popup_pre['botao_clicado']}")
        time.sleep(1.5)  # dá um respiro pro modal sumir antes de estabilizar

    # ── 1. Aguarda página estabilizar ──────────────────────────────
    log.info("\n1️⃣  Aguardando página de upload estabilizar...")
    estabilizacao = aguardar_upload_pronto()
    dados["estabilizacao"] = estabilizacao

    if not estabilizacao["pronto"]:
        # CASO ESPECIAL: quota Gemini esgotada — não é erro do TikTok nem
        # falha de fluxo. É condição operacional. Falha com etapa específica
        # pra orquestrador classificar corretamente como "Aguardando_Quota".
        if estabilizacao.get("erro") == "quota_excedida":
            return _falhou(
                dados, "quota_gemini",
                (
                    "Gemini sem quota durante estabilização do upload. "
                    "Nenhum clique foi feito. Tente novamente quando a cota voltar."
                ),
            )

        return _falhou(
            dados, "estabilizacao",
            (
                f"Página de upload não estabilizou: {estabilizacao['motivo']}. "
                f"Possível causa: conexão lenta, TikTok com problemas, ou loading "
                f"persistente. Tente novamente em alguns minutos."
            ),
        )

    coord_pre = estabilizacao.get("coordenada")

    # ── 2. Clica em Select file (com até 3 estratégias) ────────────
    log.info("\n2️⃣  Clicando em Select file (estratégia multi-nível)...")
    resultado_clique = _clicar_select_file_com_estrategias(coord_pre)
    dados["clique_select_file"] = resultado_clique

    if not resultado_clique.get("sucesso"):
        enviar_comando("screenshot", contexto="dialogo_nao_abriu_apos_estrategias")
        return _falhou(
            dados, "clique_select_file",
            (
                f"Nenhuma das 3 estratégias abriu o diálogo após clicar. "
                f"Causas prováveis: "
                f"(a) UI do TikTok mudou (novo layout do botão); "
                f"(b) extensão de browser interferindo com file inputs; "
                f"(c) Chrome bloqueou file dialog por security policy. "
                f"Recomendado: testar manualmente o upload na mesma sessão "
                f"do browser para descartar problemas de conta/permissão."
            ),
        )

    log.info(
        f"  ✅ Estratégia {resultado_clique['estrategia_vencedora']} funcionou — "
        f"diálogo confirmado"
    )

    # ── 3. Cola o caminho ──────────────────────────────────────────
    log.info("\n3️⃣  Colando caminho via clipboard...")
    resultado_cole = _colar_caminho_via_clipboard(video_path)
    dados["cole_caminho"] = resultado_cole

    if not resultado_cole.get("sucesso"):
        return _falhou(
            dados, "cole_caminho",
            f"Não consegui colar/digitar o caminho: {resultado_cole.get('erro')}",
        )

    # ── 4. Enter pra confirmar ─────────────────────────────────────
    log.info("\n4️⃣  Pressionando Enter para confirmar seleção...")
    time.sleep(0.5)
    resultado_enter = enviar_comando("tecla", tecla="enter")
    dados["enter"] = resultado_enter

    if not resultado_enter.get("sucesso"):
        return _falhou(dados, "enter", f"Enter falhou: {resultado_enter.get('mensagem')}")

    # ── 5. Aguarda upload começar ──────────────────────────────────
    log.info(f"\n5️⃣  Aguardando {ESPERA_POS_ENTER}s para upload iniciar...")
    time.sleep(ESPERA_POS_ENTER)

    # ── 6. Valida que upload realmente iniciou ─────────────────────
    log.info("\n6️⃣  Validando que upload iniciou (tela mudou)...")
    from brain.vision_analyzer import localizar_elemento_por_texto

    sinais_de_progresso = (
        "barra de progresso de upload, porcentagem sendo exibida, "
        "ou tela de detalhes do vídeo com campo de descrição/legenda"
    )
    loc_progresso = localizar_elemento_por_texto(
        contexto="apos_select_file_enter",
        alvo=sinais_de_progresso,
    )
    dados["validacao_upload_iniciou"] = loc_progresso

    encontrado_progresso = (
        loc_progresso.get("encontrado") and
        loc_progresso.get("confianca") != "baixa"
    )

    if not encontrado_progresso:
        enviar_comando("screenshot", contexto="upload_nao_iniciou")
        return _falhou(
            dados, "validacao_upload_iniciou",
            (
                f"Diálogo abriu e Enter foi pressionado, mas upload não iniciou. "
                f"Causas prováveis: "
                f"(a) caminho colado no campo errado; "
                f"(b) TikTok rejeitou silenciosamente (codec/formato); "
                f"(c) arquivo não foi aceito pelo file picker. "
                f"Verifique screenshot 'upload_nao_iniciou.png'. "
                f"Detalhes: {(loc_progresso.get('motivo', '') or '')[:120]}"
            ),
        )

    log.info("\n" + "═" * 60)
    log.info("✅ SUCESSO — Arquivo selecionado e upload iniciado")
    log.info("═" * 60)

    return {
        "sucesso":     True,
        "mensagem":    "Arquivo selecionado e upload iniciado",
        "etapa_falha": None,
        "dados":       dados,
    }


# =================================================================
# HELPERS
# =================================================================

def _falhou(dados: dict, etapa: str, mensagem: str) -> dict:
    log.error(f"\n❌ FALHA na etapa '{etapa}': {mensagem}")
    log.error("═" * 60)
    return {
        "sucesso":     False,
        "mensagem":    mensagem,
        "etapa_falha": etapa,
        "dados":       dados,
    }


# =================================================================
# TESTE VIA TERMINAL
# =================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso: python -m brain.file_dialog_uploader <caminho_do_video>")
        print(r"Ex:  python -m brain.file_dialog_uploader C:\AgenteIA\videos\teste.mp4")
        sys.exit(1)

    video = sys.argv[1]
    print("=" * 60)
    print(f"  📤 Teste v2: selecionar_arquivo_upload_tiktok")
    print(f"  Vídeo: {video}")
    print("=" * 60)

    resultado = selecionar_arquivo_upload_tiktok(video)

    print(f"\n{'─' * 60}")
    print(f"  RESULTADO")
    print(f"{'─' * 60}")
    icone = "✅" if resultado["sucesso"] else "❌"
    print(f"  {icone} Sucesso:     {resultado['sucesso']}")
    print(f"  💬 Mensagem:    {resultado['mensagem']}")
    if resultado.get("etapa_falha"):
        print(f"  🛑 Etapa falha: {resultado['etapa_falha']}")
    print(f"  📂 Dados:      {len(resultado.get('dados', {}))} etapas registradas")
    print("=" * 60)