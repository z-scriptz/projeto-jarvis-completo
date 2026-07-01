# creative_engine/produzir_video.py
# ELO DE PRODUÇÃO — junta os 2 passos do vídeo original por IA num comando:
#
#   1) ia_scene_generator  → gera as cenas de IA (dor/demo/close/resultado)
#   2) narrated_video_agent → monta o vídeo narrado (Edge-TTS + legenda +
#                             hook + CTA) usando SÓ as cenas de IA (so_ia=True)
#
# Resultado: de um nome de produto a um MP4 vertical pronto, original de ponta
# a ponta (cenas geradas por IA + narração/texto próprios). Nenhum vídeo de
# terceiro é baixado.
#
# CLI:
#   python -m creative_engine.produzir_video --produto "Chaleira Elétrica Inox"
#   python -m creative_engine.produzir_video --produto "X" --dry-run
#   python -m creative_engine.produzir_video --produto "X" --provider fal --voz pt-BR-AntonioNeural
#   python -m creative_engine.produzir_video --produto "X" --pular-cenas   (cenas já existem)

import sys
import argparse
from pathlib import Path

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("produzir_video")


def produzir(produto: str, provider: str = "auto", voz: str = "",
             dur_cena: int = 10, dry_run: bool = False,
             pular_cenas: bool = False, premium: bool = False) -> dict:
    """
    Roda o pipeline completo de vídeo original por IA pra um produto.
    Retorna dict com o resultado de cada etapa.

    premium=True → usa o Kling 2.1 master (mãos/qualidade muito melhores,
    porém ~5-10x mais caro). Use só nos produtos campeões.
    """
    resultado = {"produto": produto, "etapas": {}}

    # PREMIUM: ativa o modelo melhor via env (o fal_provider lê FAL_MODEL).
    # Guardamos o valor antigo pra restaurar no fim (não vaza pro resto).
    import os
    _fal_model_anterior = os.environ.get("FAL_MODEL")
    if premium:
        os.environ["FAL_MODEL"] = "fal-ai/kling-video/v2.1/master/text-to-video"
        log.info("💎 MODO PREMIUM: Kling 2.1 master (melhor qualidade, mais caro)")

    log.info("█" * 60)
    log.info(f"🎬 PRODUÇÃO DE VÍDEO ORIGINAL — {produto!r}")
    log.info("█" * 60)

    # ───────────────────────────────────────────────────────────────
    # ETAPA 1 — Cenas de IA
    # ───────────────────────────────────────────────────────────────
    if pular_cenas:
        log.info("⏭️  ETAPA 1 (cenas IA) pulada por --pular-cenas")
        resultado["etapas"]["cenas"] = {"ok": True, "pulado": True}
        # premium não tem efeito sem gerar cenas; restaura a env por garantia
        if premium:
            if _fal_model_anterior is None:
                os.environ.pop("FAL_MODEL", None)
            else:
                os.environ["FAL_MODEL"] = _fal_model_anterior
    else:
        log.info("\n▶️  ETAPA 1/2 — Gerando cenas de IA...")
        try:
            from creative_engine.ia_scene_generator import gerar_cenas
        except Exception as e:
            log.error(f"❌ Não consegui importar o gerador de cenas: {e}")
            resultado["etapas"]["cenas"] = {"ok": False, "erro": str(e)}
            return resultado

        r_cenas = gerar_cenas(produto, provider=provider, dur=dur_cena,
                              dry_run=dry_run)
        resultado["etapas"]["cenas"] = r_cenas

        # Cenas geradas: o FAL_MODEL já cumpriu seu papel. Restaura o valor
        # anterior pra NÃO vazar o modelo premium pros próximos produtos do lote.
        if premium:
            if _fal_model_anterior is None:
                os.environ.pop("FAL_MODEL", None)
            else:
                os.environ["FAL_MODEL"] = _fal_model_anterior

        # Se não gerou cena nenhuma (e não é dry-run), não adianta seguir:
        # o motor não teria B-roll de IA pra montar.
        if not dry_run and not r_cenas.get("ok"):
            modo = r_cenas.get("modo")
            if modo == "manual":
                log.warning("⚠️  Provider indisponível — cenas NÃO foram geradas.")
                log.warning("   Gere-as a partir do _prompts_para_gerar.json e rode")
                log.warning("   de novo com --pular-cenas. Parando aqui por ora.")
            else:
                log.error("❌ Nenhuma cena de IA gerada. Abortando a montagem.")
            return resultado

    if dry_run:
        log.info("\n🧪 DRY-RUN concluído — cenas e roteiro apenas simulados.")
        # ainda assim mostramos o roteiro que sairia (etapa 2 em dry-run)
        try:
            from agents.narrated_video_agent import gerar_video_narrado
            r_video = gerar_video_narrado(produto, dry_run=True, so_ia=True,
                                          **({"voz": voz} if voz else {}))
            resultado["etapas"]["video"] = r_video
        except Exception as e:
            log.warning(f"   (roteiro não pôde ser pré-visualizado: {e})")
        return resultado

    # ───────────────────────────────────────────────────────────────
    # ETAPA 2 — Vídeo narrado (usando SÓ as cenas de IA)
    # ───────────────────────────────────────────────────────────────
    log.info("\n▶️  ETAPA 2/2 — Montando vídeo narrado sobre as cenas de IA...")
    try:
        from agents.narrated_video_agent import gerar_video_narrado
    except Exception as e:
        log.error(f"❌ Não consegui importar o motor de vídeo: {e}")
        resultado["etapas"]["video"] = {"ok": False, "erro": str(e)}
        return resultado

    kwargs = {"so_ia": True, "forcar_render": True}
    if voz:
        kwargs["voz"] = voz
    try:
        r_video = gerar_video_narrado(produto, **kwargs)
        resultado["etapas"]["video"] = r_video
    except Exception as e:
        log.error(f"❌ Erro na montagem do vídeo: {e}")
        resultado["etapas"]["video"] = {"ok": False, "erro": str(e)}
        return resultado

    # ───────────────────────────────────────────────────────────────
    # Resumo
    # ───────────────────────────────────────────────────────────────
    # O narrated_video_agent retorna: {"sucesso": bool, "video": caminho, ...}
    video_ok = bool(r_video.get("sucesso") or r_video.get("video")
                    or r_video.get("arquivo") or r_video.get("video_path"))
    resultado["ok"] = video_ok
    caminho = (r_video.get("video") or r_video.get("video_path")
               or r_video.get("arquivo") or "?")
    if video_ok:
        log.info("\n" + "✅" * 30)
        log.info(f"✅ VÍDEO PRONTO: {caminho}")
        log.info("✅" * 30)

        # ───────────────────────────────────────────────────────────
        # ETAPA 3 — Fecha o pacote de publicação no plano
        # (legenda + hashtags + cta + descrições por plataforma).
        # Mesmo formato que o hunter grava, pro orquestrador consumir igual.
        # ───────────────────────────────────────────────────────────
        log.info("\n▶️  ETAPA 3/3 — Fechando pacote de publicação...")
        try:
            from creative_engine.finalizar_plano import finalizar_plano_ia
            plano_publish = finalizar_plano_ia(produto, r_video)
            resultado["plano"] = plano_publish
            resultado["legenda"]  = plano_publish.get("legenda", "")
            resultado["hashtags"] = plano_publish.get("hashtags", "")
            resultado["cta"]      = plano_publish.get("cta", "")
            log.info("   ✅ Pacote de publicação pronto (legenda/hashtags/descrições)")
        except Exception as e:
            log.warning(f"   ⚠️  Não foi possível fechar o pacote de publicação: {e}")
            log.warning("   (vídeo está OK; só o plano de texto não foi consolidado)")
    else:
        log.warning("\n⚠️  Pipeline terminou mas o vídeo não foi confirmado. "
                    "Veja os logs da Etapa 2.")
    return resultado


def main():
    parser = argparse.ArgumentParser(
        description="Produz um vídeo original por IA (cenas IA + narração) num comando")
    parser.add_argument("--produto", required=True, help="nome do produto")
    parser.add_argument("--provider", default="auto", help="auto|fal|grok|pixverse|heygen")
    parser.add_argument("--voz", default="", help="voz Edge-TTS (padrão: Francisca pt-BR)")
    parser.add_argument("--dur-cena", type=int, default=10, dest="dur_cena",
                        help="segundos por cena de IA")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="simula tudo, não gera nem gasta crédito")
    parser.add_argument("--pular-cenas", action="store_true", dest="pular_cenas",
                        help="usa cenas de IA já existentes na pasta do produto")
    parser.add_argument("--premium", action="store_true",
                        help="usa Kling 2.1 master (mãos/qualidade melhores, ~5-10x mais caro)")
    args = parser.parse_args()

    res = produzir(args.produto, provider=args.provider, voz=args.voz,
                   dur_cena=args.dur_cena, dry_run=args.dry_run,
                   pular_cenas=args.pular_cenas, premium=args.premium)

    if res.get("ok"):
        print("\n🎉 Pronto! Vídeo original gerado de ponta a ponta.")
        return 0
    if args.dry_run:
        print("\n🧪 Dry-run concluído — confira os prompts e o roteiro acima.")
        return 0
    print("\n⚠️  Pipeline não concluiu o vídeo. Veja os logs acima.")
    return 1


if __name__ == "__main__":
    sys.exit(main())