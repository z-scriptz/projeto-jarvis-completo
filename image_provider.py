# creative_engine/image_provider.py
# Provider de geração de imagem para o AgenteIA (Jarvis)
#
# Status atual: PLACEHOLDER — nenhum provider ativo ainda.
#
# Quando ativado, este módulo vai gerar imagens por cena (1 por momento
# do roteiro) usando APIs como:
#   - Gemini 2.5 Flash Image / Nano Banana
#   - DALL-E 3
#   - Stable Diffusion (local ou via Replicate)
#   - Midjourney via Discord API
#
# Por enquanto, retorna sucesso=false e o renderizador local usa fundos
# sólidos + texto via Pillow.

from pathlib import Path
from typing import Optional

from shared.logger import get_logger

log = get_logger(__name__)


def gerar_imagem_cena(
    prompt: str,
    output_path: str,
    largura: int = 1080,
    altura: int = 1920,
    provider: str = "placeholder",
) -> dict:
    """
    Gera uma imagem para uma cena específica do vídeo.

    Args:
        prompt:      descrição visual da cena (vem de plano["cenas"][i]["descricao"])
        output_path: caminho onde salvar a imagem gerada
        largura:    largura em pixels (padrão 1080 — vertical)
        altura:     altura em pixels (padrão 1920 — vertical)
        provider:   "placeholder" | "gemini_image" | "nano_banana" | ...

    Returns:
        {
            "sucesso":      bool,
            "mensagem":     str,
            "image_path":   str | None,
            "provider":     str,
            "prompt_usado": str,
        }
    """
    log.info(f"🎨 image_provider chamado | provider={provider} | prompt='{prompt[:50]}...'")

    # ── Provider ativado? Não. ───────────────────────────────────────
    return {
        "sucesso":      False,
        "mensagem":     "image_provider ainda não ativado — use o fallback local do renderer",
        "image_path":   None,
        "provider":     provider,
        "prompt_usado": prompt,
    }


# =================================================================
# TESTE VIA TERMINAL
# =================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  🎨 Image Provider — Teste (placeholder)")
    print("=" * 60)

    resultado = gerar_imagem_cena(
        prompt="Mini umidificador de ar com LED roxo, fundo aesthetic",
        output_path="C:\\AgenteIA\\videos\\cenas\\teste.png",
    )

    print(f"\n  Sucesso:  {resultado['sucesso']}")
    print(f"  Mensagem: {resultado['mensagem']}")
    print(f"  Provider: {resultado['provider']}")
    print("=" * 60)