# creative_engine/quality_gate.py
# Quality Gate v1 — barreira de qualidade ANTES de renderizar o vídeo narrado.
#
# FILOSOFIA (a lição da pata de cachorro + dos 5s repetidos):
#   "Um agente confiável não é o que sempre entrega; é o que sabe quando
#    NÃO deve entregar."
#
#   Antes: o Jarvis renderizava com qualquer asset → vídeo ruim com confiança.
#   Agora: ele inspeciona a EDL + os assets e, se o material não dá pra um
#   vídeo decente, BLOQUEIA e diz o que fazer (coletar / trocar produto / gerar IA).
#
# 100% determinístico, sem custo, sem API. Opera sobre a EDL já montada
# (que revela os sintomas reais) + a lista de B-roll utilizável.
#
# USO:
#   from creative_engine.quality_gate import avaliar_qualidade
#   veredito = avaliar_qualidade(edl, broll_utilizavel, suspeitos,
#                                permitir_imagens=False)
#   if not veredito["aprovado"]:
#       # não renderiza; mostra veredito["motivos"] e veredito["sugestao"]

from pathlib import Path
from typing import Optional

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    log = logging.getLogger("quality_gate")

EXT_VIDEO = {".mp4", ".mov", ".webm", ".m4v"}
EXT_IMG   = {".jpg", ".jpeg", ".png", ".webp"}

# ── Limiares (calibrados pra realidade do projeto) ───────────────────
# Não usamos número fixo de vídeos: medimos PROPORÇÃO de cortes saudáveis,
# porque o que importa é a EDL final, não a contagem bruta de arquivos.

# Quantas vezes um mesmo asset pode aparecer na EDL antes de virar "loop".
MAX_USOS_POR_ASSET = 3
# Fração máxima da timeline que pode ser imagem estática (resto deve ser vídeo).
MAX_FRACAO_IMAGEM = 0.34          # ~1/3
# Fração máxima de cortes que podem vir de fallback de cena (asset emprestado).
MAX_FRACAO_FALLBACK = 0.40
# Mínimo de assets de VÍDEO distintos na EDL pra não ser slideshow.
MIN_VIDEOS_DISTINTOS = 3


def _eh_video(nome: str) -> bool:
    return Path(nome).suffix.lower() in EXT_VIDEO


def _eh_imagem(nome: str) -> bool:
    return Path(nome).suffix.lower() in EXT_IMG


def avaliar_qualidade(edl: dict,
                       broll_utilizavel: Optional[list] = None,
                       permitir_imagens: bool = False) -> dict:
    """
    Avalia se a EDL tem qualidade suficiente pra renderizar.

    Args:
        edl:              dict da Edit Decision List (tem 'timeline').
        broll_utilizavel: lista de assets utilizáveis (Paths/str) — opcional,
                          usado só pra contexto na sugestão.
        permitir_imagens: se True, relaxa a regra de imagem estática
                          (flag --permitir-imagens do agent).

    Returns:
        {
          "aprovado":  bool,
          "motivos":   [str],   # por que reprovou (vazio se aprovado)
          "avisos":    [str],   # coisas a melhorar, mas não bloqueiam
          "sugestao":  str,     # o que fazer se reprovou
          "metricas":  {...},   # números pra log/teste
        }
    """
    timeline = (edl or {}).get("timeline", [])
    motivos = []
    avisos = []

    if not timeline:
        return {
            "aprovado": False,
            "motivos": ["EDL vazia — nenhum corte pra renderizar"],
            "avisos": [],
            "sugestao": "Rode o autopilot pra coletar assets antes de gerar o vídeo.",
            "metricas": {"n_cortes": 0},
        }

    n_cortes = len(timeline)

    # ── Métricas da EDL ──────────────────────────────────────────────
    usos = {}                 # asset → contagem
    n_imagem = 0
    n_video = 0
    n_fallback = 0
    n_sem_asset = 0
    videos_distintos = set()
    cena_de_corte = {}        # cena alvo → cenas-fonte usadas

    for corte in timeline:
        asset = corte.get("asset")
        cena = corte.get("cena", "?")
        if not asset:
            n_sem_asset += 1
            continue
        usos[asset] = usos.get(asset, 0) + 1
        if _eh_imagem(asset):
            n_imagem += 1
        elif _eh_video(asset):
            n_video += 1
            videos_distintos.add(asset)
        # fallback de cena: o asset não bate com a cena alvo
        # (heurística: prefixo do nome != cena alvo)
        nome_l = asset.lower()
        if not (nome_l.startswith(f"{cena}_") or f"_{cena}_" in nome_l
                or f"ia_{cena}_" in nome_l):
            n_fallback += 1

    max_uso = max(usos.values()) if usos else 0
    asset_mais_usado = max(usos, key=usos.get) if usos else None
    frac_imagem = n_imagem / n_cortes if n_cortes else 0
    frac_fallback = n_fallback / n_cortes if n_cortes else 0

    metricas = {
        "n_cortes":          n_cortes,
        "n_video":           n_video,
        "n_imagem":          n_imagem,
        "n_sem_asset":       n_sem_asset,
        "videos_distintos":  len(videos_distintos),
        "max_uso_asset":     max_uso,
        "asset_mais_usado":  asset_mais_usado,
        "frac_imagem":       round(frac_imagem, 2),
        "frac_fallback":     round(frac_fallback, 2),
    }

    # ── REGRAS DE BLOQUEIO ───────────────────────────────────────────

    # 1. Asset repetido demais (o "2 cenas repetem 5s")
    if max_uso > MAX_USOS_POR_ASSET:
        motivos.append(
            f"Asset '{asset_mais_usado}' usado {max_uso}x na timeline "
            f"(máximo saudável: {MAX_USOS_POR_ASSET}) — vai parecer loop")

    # 2. Poucos vídeos distintos → vira slideshow
    if len(videos_distintos) < MIN_VIDEOS_DISTINTOS:
        motivos.append(
            f"Só {len(videos_distintos)} vídeo(s) distinto(s) na timeline "
            f"(mínimo: {MIN_VIDEOS_DISTINTOS}) — vídeo ficaria repetitivo")

    # 3. Imagem estática demais (a menos que permitido)
    if not permitir_imagens and frac_imagem > MAX_FRACAO_IMAGEM:
        motivos.append(
            f"{int(frac_imagem*100)}% da timeline é imagem estática "
            f"(máximo: {int(MAX_FRACAO_IMAGEM*100)}%) — parece slideshow. "
            f"Use --permitir-imagens se for intencional")

    # 4. CTA final é imagem estática (fecha mal — a "mulher parada no fim")
    ultimo = timeline[-1]
    if (not permitir_imagens and ultimo.get("asset")
            and _eh_imagem(ultimo["asset"])):
        motivos.append(
            f"Último corte (CTA) é imagem estática '{ultimo['asset']}' — "
            f"fecha o vídeo parado. Prefira vídeo no CTA")

    # ── AVISOS (não bloqueiam, mas registram) ───────────────────────

    # 5. Fallback de cena demais (asset emprestado de outra cena)
    if frac_fallback > MAX_FRACAO_FALLBACK:
        avisos.append(
            f"{int(frac_fallback*100)}% dos cortes usam asset de outra cena "
            f"(fallback) — cenas pouco fiéis ao roteiro")

    # 6. Cortes sem asset (fundo sólido)
    if n_sem_asset > 0:
        avisos.append(
            f"{n_sem_asset} corte(s) sem asset (fundo sólido) — "
            f"faltou B-roll relevante")

    aprovado = len(motivos) == 0

    # ── SUGESTÃO acionável (o gate aponta a saída, não só diz 'não') ──
    if aprovado:
        sugestao = ""
    else:
        n_disp = len(broll_utilizavel) if broll_utilizavel else n_video
        sugestao = (
            "Assets insuficientes pra um vídeo narrado de qualidade. Opções:\n"
            "   1. Coletar mais B-roll variado:\n"
            "      python -m agents.asset_autopilot_agent --produto \"<PRODUTO>\" --max-downloads 10\n"
            "   2. Testar um produto com mais B-roll no Pexels (tech/cozinha)\n"
            "   3. Gerar cenas sob medida por IA (--provider auto, requer crédito)\n"
            f"   (assets utilizáveis agora: ~{n_disp})")

    return {
        "aprovado": aprovado,
        "motivos":  motivos,
        "avisos":   avisos,
        "sugestao": sugestao,
        "metricas": metricas,
    }


def logar_veredito(veredito: dict):
    """Imprime o veredito do Quality Gate de forma legível."""
    m = veredito["metricas"]
    log.info("🚦 QUALITY GATE")
    log.info(f"   Cortes: {m.get('n_cortes')} | vídeos distintos: {m.get('videos_distintos')} "
             f"| imagens: {m.get('n_imagem')} | max uso/asset: {m.get('max_uso_asset')} "
             f"| fallback: {int(m.get('frac_fallback',0)*100)}%")

    for a in veredito["avisos"]:
        log.info(f"   ⚠️  {a}")

    if veredito["aprovado"]:
        log.info("   ✅ APROVADO — material suficiente pra renderizar")
    else:
        log.warning("   ❌ BLOQUEADO — material insuficiente pra qualidade:")
        for motivo in veredito["motivos"]:
            log.warning(f"      • {motivo}")
        log.warning("   💡 " + veredito["sugestao"].replace("\n", "\n   "))