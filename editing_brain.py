# creative_engine/editing_brain.py
# Editing Brain v1 do AgenteIA (Jarvis).
#
# PROBLEMA QUE RESOLVE:
#   A Narrated Engine pegava 1 B-roll inteiro por bloco de legenda e fazia
#   loop dele pela duração da frase. Um clipe de 3s esticado pra 3.6s vira
#   loop visível — "é uma cena só repetindo".
#
# O QUE FAZ:
#   Transforma os blocos de legenda numa EDIT DECISION LIST (EDL): uma receita
#   de timeline com MICROCORTES. Cada bloco longo vira 2-3 cortes curtos,
#   alternando assets e efeitos leves (zoom/crop), de modo que o vídeo PAREÇA
#   editado em vez de um B-roll em loop.
#
# FILOSOFIA:
#   - 100% determinístico, sem Gemini, sem custo.
#   - Função PURA: recebe dados, devolve EDL. NÃO toca MoviePy.
#     (Quem executa a EDL é o narrated_video_agent — separação decidir/executar.)
#   - Ignora assets marcados 'suspeito' pelo Visual Audit.
#   - A soma dos cortes bate EXATAMENTE com a duração de cada bloco → mantém
#     a sincronia com narração e legenda que o tts_edge garante.
#
# SAÍDA:
#   shared/content_plans/edit_decision_list.json
#
# USO:
#   from creative_engine.editing_brain import montar_edl
#   edl = montar_edl(produto, blocos_legenda, broll, audit_path=...)

import json
from pathlib import Path
from typing import Optional

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:  # permite testar isolado
    import logging
    log = logging.getLogger("editing_brain")

# Sequência canônica de cenas (mesma do narrated_video_agent)
SEQUENCIA_CENAS = ["dor", "demo", "close", "resultado", "cta"]

# FALLBACK CONTROLADO POR CENA: quando uma cena não tem asset próprio bom,
# só empresta de cenas RELACIONADAS — nunca de qualquer cena aleatória.
# Evita o caso "resultado usou asset de cta" (que trouxe a pata de cachorro).
# Ordem = prioridade. A 1ª da lista é a própria cena.
FALLBACK_CENAS = {
    "dor":       ["dor", "demo", "close"],
    "demo":      ["demo", "close", "resultado"],
    "close":     ["close", "demo", "resultado"],
    "resultado": ["resultado", "demo", "close"],
    "cta":       ["cta", "close", "demo"],
}

EXT_VIDEO = {".mp4", ".mov", ".webm", ".m4v"}
EXT_IMG   = {".jpg", ".jpeg", ".png", ".webp"}

# Efeitos leves disponíveis pra alternar (executados pelo agent).
# 'none' incluído pra não exagerar — nem todo corte precisa de movimento.
EFEITOS = ["zoom_in", "punch_in", "crop_alt", "none"]

# Limiares de microcorte
DUR_MIN_CORTE   = 1.0   # nenhum corte fica abaixo disso (frenético/ilegível)
DUR_BLOCO_PICAR = 2.5   # blocos acima disso são picados em microcortes
DUR_CORTE_ALVO  = 1.6   # duração ideal de cada microcorte (~ritmo TikTok)


# =================================================================
# LEITURA DO VISUAL AUDIT
# =================================================================

def _carregar_suspeitos(audit_path: Optional[Path]) -> set:
    """
    Lê o relatório do Visual Audit e retorna o conjunto de nomes de arquivo
    marcados como 'suspeito'. Se não houver relatório, retorna set vazio
    (nada é considerado suspeito).
    """
    if not audit_path:
        return set()
    p = Path(audit_path)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"⚠️  Não consegui ler audit ({e}) — assumindo nenhum suspeito")
        return set()

    suspeitos = set()
    for a in data.get("assets", []):
        if a.get("status") == "suspeito":
            suspeitos.add(a.get("arquivo", ""))
    return suspeitos


# =================================================================
# HELPERS DE ASSET
# =================================================================

def _cena_do_arquivo(nome: str) -> str:
    """Extrai a cena do nome do arquivo (prefixo antes do 1º '_')."""
    n = nome.lower()
    for cena in SEQUENCIA_CENAS:
        if n.startswith(f"{cena}_") or f"_{cena}_" in n:
            return cena
    return ""


def _eh_video(caminho: Path) -> bool:
    return caminho.suffix.lower() in EXT_VIDEO


def _filtrar_assets(broll: list, suspeitos: set) -> list:
    """Remove assets suspeitos. Retorna lista de Paths utilizáveis."""
    usaveis = []
    for b in broll:
        nome = b.name if hasattr(b, "name") else str(b)
        if nome in suspeitos:
            log.info(f"   🚫 Ignorando suspeito: {nome}")
            continue
        usaveis.append(b)
    return usaveis


def _indexar_por_cena(broll: list) -> dict:
    """Agrupa assets por cena: {cena: [Path, ...]}."""
    idx = {}
    for b in broll:
        nome = b.name if hasattr(b, "name") else str(b)
        cena = _cena_do_arquivo(nome)
        idx.setdefault(cena, []).append(b)
    return idx


# =================================================================
# SELEÇÃO DE ASSET ALTERNANDO
# =================================================================

class SelecionadorAssets:
    """
    Escolhe assets pra cada microcorte com duas metas:
      1. Preferir assets da cena do bloco.
      2. NUNCA repetir o asset do corte imediatamente anterior (quebra loop).

    Estratégia em camadas pra cada pedido:
      a) asset da cena, diferente do último usado, menos usado até agora
      b) asset de qualquer cena, diferente do último, menos usado
      c) qualquer asset diferente do último (mesmo já bem usado)
      d) por último, repete o último (só se houver 1 asset no total)
    """

    def __init__(self, broll: list):
        self.broll = list(broll)
        self.por_cena = _indexar_por_cena(broll)
        self.uso = {self._nome(b): 0 for b in broll}  # contador de uso
        self.ultimo = None

    @staticmethod
    def _nome(b):
        return b.name if hasattr(b, "name") else str(b)

    def _eh_video(self, candidato) -> bool:
        """True se o asset é vídeo (não imagem estática)."""
        ext = Path(self._nome(candidato)).suffix.lower()
        return ext in EXT_VIDEO

    def _menos_usado(self, candidatos: list, evitar_ultimo: bool = True):
        if not candidatos:
            return None
        pool = candidatos
        if evitar_ultimo and self.ultimo is not None and len(candidatos) > 1:
            pool = [c for c in candidatos if self._nome(c) != self._nome(self.ultimo)]
            if not pool:
                pool = candidatos
        # Ordena por: (1) VÍDEO antes de imagem — imagem estática é pior,
        # principalmente no CTA (fecha o vídeo parado); (2) menos usado primeiro.
        # Assim, havendo vídeo disponível, ele é sempre preferido à imagem.
        pool_ordenado = sorted(
            pool,
            key=lambda c: (0 if self._eh_video(c) else 1,
                           self.uso.get(self._nome(c), 0)))
        return pool_ordenado[0]

    def escolher(self, cena: str):
        """
        Retorna o melhor asset pra esta cena respeitando o FALLBACK_CENAS.
        Tenta a própria cena, depois só as cenas RELACIONADAS (em ordem).
        Nunca pega de cena fora da lista de fallback — é o que impede
        'resultado' de usar um asset de 'cta' (que trazia cachorro/quadra).
        Retorna None (→ fundo sólido) se nenhuma cena permitida tiver asset.
        """
        cenas_permitidas = FALLBACK_CENAS.get(cena, [cena])
        for i, cena_fonte in enumerate(cenas_permitidas):
            candidatos = self.por_cena.get(cena_fonte, [])
            escolhido = self._menos_usado(candidatos)
            if escolhido is not None:
                if i > 0:
                    log.info(f"      ↪️  '{cena}' sem asset próprio → "
                             f"usando '{cena_fonte}' (fallback controlado)")
                self.uso[self._nome(escolhido)] = self.uso.get(self._nome(escolhido), 0) + 1
                self.ultimo = escolhido
                return escolhido
        # Nenhuma cena permitida tem asset → fundo sólido (melhor que lixo)
        log.warning(f"      ⚠️  Sem asset relevante pra '{cena}' "
                    f"(nem fallback {cenas_permitidas[1:]}) → fundo sólido")
        return None


# =================================================================
# DIVISÃO DE BLOCO EM MICROCORTES
# =================================================================

def _n_cortes_para(dur_bloco: float) -> int:
    """Decide quantos microcortes um bloco vira."""
    if dur_bloco <= DUR_BLOCO_PICAR:
        return 1
    # alvo ~DUR_CORTE_ALVO por corte, mas respeitando DUR_MIN_CORTE
    n = max(2, round(dur_bloco / DUR_CORTE_ALVO))
    # nenhum corte pode ficar abaixo do mínimo
    while n > 1 and (dur_bloco / n) < DUR_MIN_CORTE:
        n -= 1
    return n


def _trecho_fonte(asset: Path, dur_corte: float, ordinal: int) -> tuple:
    """
    Decide qual trecho do vídeo-fonte usar pra este corte.
    Imagens não têm trecho (retorna (0,0)).
    Pra vídeos, escalona o início conforme o ordinal pra, quando o MESMO
    asset reaparecer, pegar uma parte diferente (mais variedade visual).
    O agent ajusta/loopa se o trecho exceder a duração real do vídeo.
    """
    if not _eh_video(asset):
        return (0.0, 0.0)
    # início escalonado: corte 0 começa em 0, corte 1 em ~1.2s, etc.
    inicio = round(ordinal * 1.2, 2)
    fim = round(inicio + dur_corte, 2)
    return (inicio, fim)


# =================================================================
# FUNÇÃO PRINCIPAL
# =================================================================

def montar_edl(produto: str,
               blocos_legenda: list,
               broll: list,
               cenas_por_bloco: Optional[list] = None,
               audit_path: Optional[Path] = None,
               salvar_em: Optional[Path] = None) -> dict:
    """
    Constrói a Edit Decision List a partir dos blocos de legenda + B-roll.

    Args:
        produto:         nome do produto
        blocos_legenda:  [{texto, inicio_seg, fim_seg}] vindos do tts_edge
        broll:           lista de Paths de B-roll disponíveis
        cenas_por_bloco: cena de cada bloco (se None, usa sequência canônica)
        audit_path:      caminho do visual_audit_resultado.json (ignora suspeitos)
        salvar_em:       onde salvar a EDL (se None, não salva em disco)

    Returns:
        {
          "produto": str,
          "estilo": "ugc_narrado_microcortes",
          "dur_total": float,
          "n_blocos": int,
          "n_cortes": int,
          "timeline": [
             {inicio, fim, cena, asset, trecho_inicio, trecho_fim,
              efeito, texto, bloco_idx}
          ],
          "assets_ignorados": [nomes suspeitos],
        }
    """
    suspeitos = _carregar_suspeitos(audit_path)
    broll_ok = _filtrar_assets(broll, suspeitos)

    # cenas por bloco
    n_blocos = len(blocos_legenda)
    if cenas_por_bloco is None:
        if n_blocos == len(SEQUENCIA_CENAS):
            cenas_por_bloco = list(SEQUENCIA_CENAS)
        else:
            # distribui canônico proporcional (dor no início, cta no fim)
            cenas_por_bloco = []
            for i in range(n_blocos):
                if i == 0:
                    cenas_por_bloco.append("dor")
                elif i == n_blocos - 1:
                    cenas_por_bloco.append("cta")
                else:
                    meio = SEQUENCIA_CENAS[1:-1]
                    idx = min(int((i - 1) / max(1, n_blocos - 2) * len(meio)),
                              len(meio) - 1)
                    cenas_por_bloco.append(meio[idx])

    selecionador = SelecionadorAssets(broll_ok)
    timeline = []
    efeito_idx = 0

    for bi, bloco in enumerate(blocos_legenda):
        ini = float(bloco["inicio_seg"])
        fim = float(bloco["fim_seg"])
        dur_bloco = max(DUR_MIN_CORTE, fim - ini)
        cena = cenas_por_bloco[bi] if bi < len(cenas_por_bloco) else "demo"

        n_cortes = _n_cortes_para(dur_bloco) if broll_ok else 1
        dur_corte = dur_bloco / n_cortes

        for c in range(n_cortes):
            corte_ini = round(ini + c * dur_corte, 2)
            # último corte fecha exatamente no fim do bloco (evita drift)
            corte_fim = round(fim, 2) if c == n_cortes - 1 else round(corte_ini + dur_corte, 2)

            asset = selecionador.escolher(cena)
            asset_nome = selecionador._nome(asset) if asset is not None else None
            trecho_ini, trecho_fim = ((0.0, 0.0) if asset is None
                                      else _trecho_fonte(asset, corte_fim - corte_ini, c))

            # alterna efeito; corte único de bloco curto fica 'none' (mais limpo)
            if n_cortes == 1 and dur_bloco <= DUR_BLOCO_PICAR:
                efeito = "none"
            else:
                efeito = EFEITOS[efeito_idx % len(EFEITOS)]
                efeito_idx += 1

            timeline.append({
                "inicio":        corte_ini,
                "fim":           corte_fim,
                "cena":          cena,
                "asset":         asset_nome,
                "trecho_inicio": trecho_ini,
                "trecho_fim":    trecho_fim,
                "efeito":        efeito,
                "texto":         bloco["texto"],
                "bloco_idx":     bi,
            })

    dur_total = round(float(blocos_legenda[-1]["fim_seg"]), 2) if blocos_legenda else 0.0

    edl = {
        "produto":           produto,
        "estilo":            "ugc_narrado_microcortes",
        "dur_total":         dur_total,
        "n_blocos":          n_blocos,
        "n_cortes":          len(timeline),
        "timeline":          timeline,
        "assets_ignorados":  sorted(suspeitos),
    }

    if salvar_em:
        try:
            Path(salvar_em).parent.mkdir(parents=True, exist_ok=True)
            Path(salvar_em).write_text(
                json.dumps(edl, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8")
            log.info(f"💾 EDL salva: {salvar_em}")
        except Exception as e:
            log.warning(f"⚠️  Falha ao salvar EDL: {e}")

    return edl


def logar_edl(edl: dict):
    """Imprime a timeline de forma legível no terminal."""
    log.info(f"🎬 EDIT DECISION LIST — '{edl['produto']}' ({edl['estilo']})")
    log.info(f"   {edl['n_blocos']} bloco(s) → {edl['n_cortes']} corte(s) | "
             f"dur {edl['dur_total']}s")
    if edl.get("assets_ignorados"):
        log.info(f"   🚫 Ignorados (suspeitos): {edl['assets_ignorados']}")
    bloco_atual = -1
    for corte in edl["timeline"]:
        if corte["bloco_idx"] != bloco_atual:
            bloco_atual = corte["bloco_idx"]
            log.info(f"   ── Bloco {bloco_atual + 1} [{corte['cena']}]: "
                     f"\"{corte['texto'][:40]}\"")
        dur = corte["fim"] - corte["inicio"]
        asset_lbl = corte["asset"] or "(fundo sólido)"
        log.info(f"      {corte['inicio']:5.1f}→{corte['fim']:5.1f}s "
                 f"({dur:4.1f}s) {corte['efeito']:9s} {asset_lbl}")