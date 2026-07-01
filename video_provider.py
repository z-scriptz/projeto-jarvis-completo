# creative_engine/video_provider.py
# Provider de geração de vídeo externo para o AgenteIA (Jarvis)
#
# Status atual: PLACEHOLDER — nenhum provider externo ativo ainda.
#
# Quando ativado, este módulo vai gerar vídeos completos via APIs como:
#   - InVideo AI       (vídeos a partir de roteiro)
#   - HeyGen           (vídeos com avatar falante)
#   - Runway Gen-3     (vídeo a partir de prompt/imagem)
#   - Pika Labs        (text-to-video)
#   - Kling AI         (text-to-video)
#   - CapCut Online    (edição programática)
#
# Por enquanto, retorna sucesso=false e o asset_router cai no
# local_video_renderer (MoviePy + Pillow).

from shared.logger import get_logger

log = get_logger(__name__)


def gerar_video_externo(plano: dict, provider: str = "placeholder") -> dict:
    """
    Gera um vídeo completo a partir do plano criativo via API externa.

    Args:
        plano:    dict completo do content_planner (hook, cenas, narracao, etc)
        provider: "placeholder" | "invideo" | "heygen" | "runway" | "pika" | "kling"

    Returns:
        {
            "sucesso":     bool,
            "mensagem":    str,
            "video_path":  str | None,
            "provider":    str,
            "duracao":     float | None,
            "custo_est":   float | None,
        }
    """
    produto = plano.get("produto", "?")
    log.info(f"🎥 video_provider chamado | provider={provider} | produto='{produto}'")

    # ── Provider externo ainda não implementado ──────────────────────
    return {
        "sucesso":    False,
        "mensagem":   "video_provider externo ainda não ativado — usar local_moviepy como fallback",
        "video_path": None,
        "provider":   provider,
        "duracao":    None,
        "custo_est":  None,
    }


# =================================================================
# TESTE VIA TERMINAL
# =================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  🎥 Video Provider — Teste (placeholder)")
    print("=" * 60)

    plano_teste = {
        "produto":  "Umidificador de Ar Mini com LED",
        "hook":     "Você PRECISA ver isso 👀",
        "cenas":    [],
        "duracao":  "12s",
    }

    resultado = gerar_video_externo(plano_teste, provider="placeholder")

    print(f"\n  Sucesso:  {resultado['sucesso']}")
    print(f"  Mensagem: {resultado['mensagem']}")
    print(f"  Provider: {resultado['provider']}")
    print("=" * 60)