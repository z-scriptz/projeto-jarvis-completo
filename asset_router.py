# creative_engine/asset_router.py
# Router da camada criativa do AgenteIA (Jarvis)
#
# Responsabilidade: decidir QUEM vai renderizar o vídeo:
#   1. Provider externo (InVideo/HeyGen/Runway/Pika/Kling/CapCut)
#      — quando usar_api_video=true e provider configurado
#   2. Renderer local (MoviePy + Pillow)
#      — fallback padrão
#
# Não chama Gemini, não chama TikTok, não posta nada. Só gera mídia.
#
# Uso:
#   from creative_engine.asset_router import gerar_assets_para_plano
#   resultado = gerar_assets_para_plano()
#
# Teste via terminal:
#   python -m creative_engine.asset_router

import json
import time
from pathlib import Path
from typing import Optional

from shared.logger import get_logger

log = get_logger(__name__)

CONFIG_PATH = Path(__file__).parent / "providers_config.json"
PLANS_DIR   = Path(__file__).parent.parent / "shared" / "content_plans"


# =================================================================
# CARREGAR CONFIG / PLANO
# =================================================================

def _carregar_config() -> dict:
    """Carrega providers_config.json. Em caso de falha, usa defaults conservadores."""
    defaults = {
        "image_provider":   "placeholder",
        "video_provider":   "local_moviepy",
        "fallback_enabled": True,
        "usar_api_imagem":  False,
        "usar_api_video":   False,
        "video_settings": {
            "width": 1080, "height": 1920, "fps": 30, "duracao_padrao": 12,
            "bg_color": "#1a1a2e", "text_color": "#ffffff", "accent_color": "#ff2e63",
        },
    }

    if not CONFIG_PATH.exists():
        log.warning(f"providers_config.json não encontrado em {CONFIG_PATH} — usando defaults")
        return defaults

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        # Merge com defaults pra garantir todos os campos
        for k, v in defaults.items():
            config.setdefault(k, v)
        # video_settings também precisa de merge profundo
        vs_defaults = defaults["video_settings"]
        vs_config   = config.get("video_settings", {})
        for k, v in vs_defaults.items():
            vs_config.setdefault(k, v)
        config["video_settings"] = vs_config

        log.info(f"⚙️ Config carregada: video_provider={config['video_provider']} | usar_api_video={config['usar_api_video']}")
        return config

    except Exception as e:
        log.warning(f"Erro ao ler providers_config.json: {e} — usando defaults")
        return defaults


def _carregar_plano(plano_path: str) -> Optional[dict]:
    """Carrega o plano JSON. Aceita caminho relativo (shared/content_plans/...) ou absoluto."""
    caminho = Path(plano_path)
    if not caminho.is_absolute():
        # Relativo ao diretório raiz do projeto
        raiz = Path(__file__).parent.parent
        caminho = raiz / plano_path

    if not caminho.exists():
        log.error(f"❌ Plano não encontrado: {caminho}")
        return None

    try:
        with open(caminho, "r", encoding="utf-8") as f:
            plano = json.load(f)
        log.info(f"📂 Plano carregado: '{plano.get('produto', '?')}' ({caminho.name})")
        return plano
    except Exception as e:
        log.error(f"❌ Falha ao ler plano: {e}")
        return None


# =================================================================
# ROUTER PRINCIPAL
# =================================================================

def gerar_assets_para_plano(
    plano_path: str = "shared/content_plans/ultimo_plano.json",
) -> dict:
    """
    Gera assets de mídia (vídeo .mp4) a partir de um plano criativo.

    Fluxo:
        1. Carrega plano + config
        2. Se usar_api_video=true → tenta video_provider externo
        3. Se falhar ou desativado → cai no renderer local (MoviePy + Pillow)
        4. Salva resultado em assets_resultado.json
        5. Atualiza state_manager
        6. Retorna dict resumido

    Args:
        plano_path: caminho do plano JSON (default: último plano gerado)

    Returns:
        {
            "sucesso":          bool,
            "produto":          str,
            "video_path":       str | None,
            "provider_usado":   str,
            "mensagem":         str,
            "duracao":          float,
            "num_cenas":        int,
            "tentou_externo":   bool,
            "timestamp":        str,
        }
    """
    log.info("═" * 60)
    log.info("🎨 ASSET ROUTER — Iniciando geração de assets")
    log.info("═" * 60)

    resultado_final: dict = {
        "sucesso":          False,
        "produto":          "",
        "video_path":       None,
        "provider_usado":   "",
        "mensagem":         "",
        "duracao":          0,
        "num_cenas":        0,
        "tentou_externo":   False,
        "timestamp":        time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # ── 1. Carregar plano e config ────────────────────────────────────
    plano = _carregar_plano(plano_path)
    if plano is None:
        msg = f"Plano não encontrado em '{plano_path}'. Rode o pipeline de planejamento antes."
        log.error(msg)
        resultado_final.update(sucesso=False, mensagem=msg, provider_usado="nenhum")
        _salvar_resultado(resultado_final)
        return resultado_final

    config = _carregar_config()
    produto = plano.get("produto", "?")
    resultado_final["produto"] = produto

    log.info(f"📦 Produto: '{produto}'")
    log.info(f"🎯 Strategy: video_provider={config['video_provider']} | usar_api_video={config['usar_api_video']}")

    # ── 2. Provider externo? ──────────────────────────────────────────
    resultado_render = None
    provider_video   = config.get("video_provider", "local_moviepy")
    usar_externo     = config.get("usar_api_video", False) and provider_video != "local_moviepy"

    if usar_externo:
        log.info(f"\n🌐 Tentando provider externo: {provider_video}")
        resultado_final["tentou_externo"] = True
        try:
            from creative_engine.video_provider import gerar_video_externo
            resultado_render = gerar_video_externo(plano, provider=provider_video)

            if resultado_render.get("sucesso"):
                log.info(f"  ✅ Provider externo OK: {resultado_render.get('video_path')}")
            else:
                log.warning(f"  ⚠️ Provider externo falhou: {resultado_render.get('mensagem')}")
                if not config.get("fallback_enabled", True):
                    msg = f"Provider externo falhou e fallback desativado: {resultado_render.get('mensagem')}"
                    resultado_final.update(
                        sucesso=False, mensagem=msg, provider_usado=provider_video,
                    )
                    _salvar_resultado(resultado_final)
                    return resultado_final
                # Senão, segue pro fallback local
                resultado_render = None

        except Exception as e:
            log.error(f"  ❌ Exceção no provider externo: {e}")
            resultado_render = None

    # ── 3. Fallback local (ou provider local desde o início) ──────────
    if resultado_render is None:
        log.info(f"\n🎬 Renderizador local (MoviePy + Pillow)")
        try:
            from creative_engine.local_video_renderer import renderizar_video_local
            resultado_render = renderizar_video_local(
                plano, config=config.get("video_settings", {})
            )
        except Exception as e:
            log.error(f"❌ Exceção no renderer local: {e}")
            resultado_render = {
                "sucesso":    False,
                "mensagem":   f"Exceção no renderer local: {e}",
                "video_path": None,
                "duracao":    0,
                "num_cenas":  0,
                "provider":   "local_moviepy",
            }

    # ── 4. Consolidar resultado ───────────────────────────────────────
    resultado_final.update(
        sucesso        = resultado_render.get("sucesso", False),
        video_path     = resultado_render.get("video_path"),
        provider_usado = resultado_render.get("provider", "local_moviepy"),
        mensagem       = resultado_render.get("mensagem", ""),
        duracao        = resultado_render.get("duracao", 0),
        num_cenas      = resultado_render.get("num_cenas", 0),
    )

    # ── 5. Atualizar state_manager ────────────────────────────────────
    _atualizar_state(resultado_final, plano)

    # ── 6. Salvar resultado ───────────────────────────────────────────
    _salvar_resultado(resultado_final)

    # ── 7. Log final ──────────────────────────────────────────────────
    log.info("═" * 60)
    if resultado_final["sucesso"]:
        log.info(f"✅ ASSET ROUTER concluído: '{produto}' → {resultado_final['video_path']}")
    else:
        log.error(f"❌ ASSET ROUTER falhou: {resultado_final['mensagem']}")
    log.info("═" * 60)

    return resultado_final


# =================================================================
# HELPERS
# =================================================================

def _atualizar_state(resultado: dict, plano: dict):
    """Persiste resultado no state_manager."""
    try:
        from memory.state_manager import atualizar_varios
        atualizar_varios({
            "estado_atual":         "video_renderizado" if resultado["sucesso"] else "render_falhou",
            "produto_atual":        plano.get("produto", ""),
            "video_path_atual":     resultado.get("video_path", ""),
            "ultimo_video_render":  time.strftime("%Y-%m-%d %H:%M:%S"),
            "ultimo_render_provider": resultado.get("provider_usado", ""),
        })
        log.info(f"💾 State atualizado: estado_atual={'video_renderizado' if resultado['sucesso'] else 'render_falhou'}")
    except Exception as e:
        log.warning(f"⚠️ Não foi possível atualizar state: {e}")


def _salvar_resultado(resultado: dict) -> Optional[Path]:
    """Salva o resultado em shared/content_plans/assets_resultado.json."""
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        caminho = PLANS_DIR / "assets_resultado.json"
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2, default=str)
        log.info(f"💾 Resultado salvo: {caminho}")
        return caminho
    except Exception as e:
        log.warning(f"⚠️ Falha ao salvar resultado: {e}")
        return None


# =================================================================
# TESTE VIA TERMINAL
# =================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  🎨 Asset Router — Teste")
    print("=" * 60)

    resultado = gerar_assets_para_plano()

    print(f"\n{'─' * 60}")
    print(f"  📊 RESULTADO")
    print(f"{'─' * 60}")
    icone = "✅" if resultado["sucesso"] else "❌"
    print(f"  {icone} Sucesso:    {resultado['sucesso']}")
    print(f"  📦 Produto:        {resultado['produto']}")
    print(f"  🎥 Vídeo:          {resultado['video_path']}")
    print(f"  🛠️  Provider:       {resultado['provider_usado']}")
    print(f"  ⏱️  Duração:        {resultado['duracao']}s")
    print(f"  🎬 Cenas:          {resultado['num_cenas']}")
    print(f"  🌐 Tentou externo: {resultado['tentou_externo']}")
    print(f"  💬 Mensagem:       {resultado['mensagem']}")
    print(f"  ⏰ Timestamp:      {resultado['timestamp']}")

    print(f"\n{'─' * 60}")
    print(f"  💡 PRÓXIMO PASSO")
    print(f"{'─' * 60}")
    if resultado["sucesso"]:
        print(f"  Agora o vídeo existe! Rode o orquestrador novamente:")
        print(f"      python -m agents.autonomous_orchestrator")
        print(f"  Ele vai pular Aguardando_Video e entrar em preparar_post_tiktok_completo.")
    else:
        print(f"  ❌ {resultado['mensagem']}")
        if "moviepy" in resultado['mensagem'].lower() or "pillow" in resultado['mensagem'].lower():
            print(f"\n  Instale as dependências:")
            print(f"      pip install moviepy imageio-ffmpeg pillow")

    print(f"\n{'─' * 60}")
    print(f"  💾 ARQUIVOS")
    print(f"{'─' * 60}")
    print(f"  Resultado:   shared/content_plans/assets_resultado.json")
    print(f"  Plano lido:  shared/content_plans/ultimo_plano.json")
    if resultado["video_path"]:
        print(f"  Vídeo:       {resultado['video_path']}")
    print("=" * 60)