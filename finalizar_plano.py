# creative_engine/finalizar_plano.py
# Fecha o pacote de publicação do caminho IA.
#
# PROBLEMA QUE RESOLVE:
#   No caminho IA (produzir_video → narrated_video_agent), o vídeo sai pronto
#   (hook + narração + legenda sincronizada + CTA), mas o PLANO gravado não
#   carrega legenda/hashtags/cta/descrições por plataforma. O hunter (rev 4)
#   já fazia isso no fim; o caminho IA não. Este módulo fecha esse gap.
#
# O QUE FAZ:
#   1. Pega produto + frases + categoria do resultado do narrated_video_agent
#   2. Monta o pacote (publish_pack_builder) → legendas/hashtags por plataforma
#   3. Monta descrições por plataforma (descricao_builder)
#   4. Funde tudo num plano e grava plano_<slug>.json + ultimo_plano.json
#      com status_producao="video_gerado" (mesmo formato que o hunter)
#
# Não chama Gemini, não posta, não renderiza. Só consolida texto.
#
# Uso:
#   from creative_engine.finalizar_plano import finalizar_plano_ia
#   plano = finalizar_plano_ia(produto, resultado_video)

import json
import re
import time
from pathlib import Path
from typing import Optional

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("finalizar_plano")

PLANS_DIR = Path(__file__).parent.parent / "shared" / "content_plans"


def _slug(produto: str) -> str:
    s = re.sub(r"[^\w\s-]", "", (produto or "").lower())
    return re.sub(r"[\s-]+", "_", s).strip("_") or f"produto_{int(time.time())}"


def _salvar_json_atomico(caminho: Path, dados) -> bool:
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        tmp.replace(caminho)
        return True
    except Exception as e:
        log.error(f"Falha ao salvar {caminho.name}: {e}")
        try:
            tmp.unlink()
        except Exception:
            pass
        return False


def _carregar_plano_existente(slug: str) -> dict:
    """
    Se já existe um plano (ex: content_planner rodou antes), carrega pra
    preservar link_afiliado, titulo_real, preco_real, etc.
    """
    for nome in (f"plano_{slug}.json", "ultimo_plano.json"):
        caminho = PLANS_DIR / nome
        if caminho.exists():
            try:
                plano = json.loads(caminho.read_text(encoding="utf-8"))
                # confirma que é do mesmo produto (evita pegar plano de outro)
                if _slug(plano.get("produto", "")) == slug or nome.startswith("plano_"):
                    log.info(f"📂 Plano base reaproveitado: {nome}")
                    return plano
            except Exception:
                continue
    return {}


def _detectar_categoria(produto: str, resultado_video: dict) -> str:
    """Pega categoria do resultado do vídeo, ou infere."""
    cat = resultado_video.get("categoria")
    if cat and cat not in ("(nenhuma)", "(plano)"):
        return cat
    try:
        from creative_engine.narration_script_builder import _categoria_do_produto
        return _categoria_do_produto(produto) or ""
    except Exception:
        return ""


def finalizar_plano_ia(produto: str, resultado_video: dict) -> dict:
    """
    Monta o pacote de publicação completo no plano, após o vídeo IA ficar pronto.

    Args:
        produto:          nome do produto
        resultado_video:  dict retornado por gerar_video_narrado()
                          (tem 'frases', 'categoria', 'video', 'duracao', etc)

    Returns:
        plano dict completo, já gravado em disco, com:
          - legenda, hashtags, cta
          - legendas por plataforma (tiktok/instagram/shopee/youtube)
          - descricoes por plataforma
          - video_path_sugerido, status_producao="video_gerado"
    """
    log.info(f"📦 Finalizando plano de publicação — '{produto}'")
    slug = _slug(produto)

    # Base: reaproveita plano existente (link de afiliado, título real, etc)
    plano = _carregar_plano_existente(slug)
    plano["produto"] = produto

    # Frases do roteiro narrado (vem do resultado do vídeo)
    frases = resultado_video.get("frases", []) or []
    categoria = _detectar_categoria(produto, resultado_video)
    plano["categoria"] = categoria

    roteiro_dict = {"frases": frases, "categoria": categoria}

    # ── 1. Pacote de publicação (legendas + hashtags por plataforma) ──
    try:
        from creative_engine.publish_pack_builder import construir_pacote
        pacote = construir_pacote(produto, roteiro_dict, categoria=categoria)

        # Legenda/hashtags/cta "default" = versão TikTok (o canal principal)
        plano.setdefault("legenda", pacote.get("legenda_tiktok", ""))
        plano.setdefault("cta", pacote.get("cta", "LINK NA BIO"))
        hashtags_lista = pacote.get("hashtags", [])
        plano.setdefault("hashtags", " ".join(hashtags_lista) if hashtags_lista else "")
        plano["hook"] = pacote.get("hook", plano.get("hook", ""))

        # Pacote completo por plataforma (pro publish step escolher)
        plano["publish_pack"] = {
            "legenda_tiktok":    pacote.get("legenda_tiktok", ""),
            "legenda_instagram": pacote.get("legenda_instagram", ""),
            "legenda_shopee":    pacote.get("legenda_shopee", ""),
            "titulo_youtube":    pacote.get("titulo_youtube", ""),
            "descricao_youtube": pacote.get("descricao_youtube", ""),
            "hashtags":          hashtags_lista,
        }
        log.info(f"   ✅ Pacote de publicação montado (hook='{pacote.get('hook', '')[:30]}')")
    except Exception as e:
        log.warning(f"   ⚠️ publish_pack_builder falhou: {e}")

    # ── 2. Descrições por plataforma (link clicável vs bio) ───────────
    try:
        from creative_engine.descricao_builder import montar_todas
        descs = montar_todas(plano, ["tiktok", "youtube", "instagram", "facebook"])
        plano["descricoes"] = {p: d.get("descricao", "") for p, d in descs.items()}
        log.info(f"   ✅ Descrições por plataforma: {list(plano['descricoes'].keys())}")
    except Exception as e:
        log.warning(f"   ⚠️ descricao_builder falhou: {e}")

    # ── 3. Metadados do vídeo ─────────────────────────────────────────
    video_path = (resultado_video.get("video")
                  or resultado_video.get("video_path")
                  or resultado_video.get("arquivo") or "")
    if video_path:
        plano["video_path_sugerido"] = video_path
    plano["roteiro_narrado"]   = frases
    plano["duracao_video"]     = resultado_video.get("duracao")
    plano["narracao_propria"]  = bool(resultado_video.get("narracao"))
    plano["fonte_video"]       = "ia_original"
    plano["status_producao"]   = "video_gerado"
    plano["timestamp_publish"] = time.strftime("%Y-%m-%d %H:%M:%S")

    # ── 4. Grava (atômico) — plano_<slug> + ultimo_plano ──────────────
    _salvar_json_atomico(PLANS_DIR / f"plano_{slug}.json", plano)
    _salvar_json_atomico(PLANS_DIR / "ultimo_plano.json", plano)
    log.info(f"   💾 Plano gravado: plano_{slug}.json + ultimo_plano.json")

    return plano


# =================================================================
# TESTE VIA TERMINAL
# =================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  📦 Finalizar Plano IA — Teste")
    print("=" * 60)

    # Simula o resultado de um gerar_video_narrado
    resultado_fake = {
        "produto": "Cortador de Legumes 12 em 1",
        "categoria": "cozinha_utensilio",
        "frases": [
            "Três segundos é o que esse cortador leva pra picar tudo.",
            "Sem faca, sem choro, sem bagunça na cozinha.",
            "Cebola, alho, tomate picados num apertão só.",
            "O preparo da sua comida nunca mais vai ser o mesmo.",
            "Garante o teu no link da bio!",
        ],
        "video": "C:\\AgenteIA\\videos\\cortador_de_legumes_12_em_1_narrated.mp4",
        "duracao": 16.4,
        "narracao": "ok",
    }

    plano = finalizar_plano_ia(resultado_fake["produto"], resultado_fake)

    print(f"\n📦 Produto:   {plano.get('produto')}")
    print(f"🏷️  Categoria: {plano.get('categoria')}")
    print(f"🎣 Hook:      {plano.get('hook')}")
    print(f"📝 Legenda:   {plano.get('legenda', '')[:70]}")
    print(f"#️⃣  Hashtags:  {plano.get('hashtags', '')[:70]}")
    print(f"📢 CTA:       {plano.get('cta')}")
    print(f"🎥 Vídeo:     {plano.get('video_path_sugerido')}")
    print(f"📊 Status:    {plano.get('status_producao')}")
    print(f"\n📱 Descrições por plataforma:")
    for plat, desc in (plano.get("descricoes") or {}).items():
        print(f"   ── {plat} ──")
        print(f"   {desc[:120]}")
    print("=" * 60)