# creative_engine/semantic_indexer.py
# Indexador Automático do Catálogo Semântico (Jarvis).
#
# O QUE FAZ:
#   Enche o Catálogo Semântico (semantic_catalog.py) com VARIEDADE de clipes,
#   varrendo TODAS as queries de TODOS os nichos de uma só vez. Carrega o modelo
#   de embedding UMA vez (mata o gargalo de ~45s por execução) e coleta tudo.
#
# POR QUE EXISTE:
#   Rodar `semantic_catalog --indexar --query X` na mão, query por query,
#   recarrega o modelo a cada vez (lento) e dá trabalho. Pior: catálogo só fica
#   bom com VARIEDADE — buscar "fundo futurista" só brilha quando o banco tem
#   cozinha, fitness, beleza, tech... senão devolve sempre a mesma coisa.
#
# DE ONDE VÊM AS QUERIES:
#   REUSA o QUERIES_POR_NICHO_E_CENA do asset_autopilot_agent (uma fonte de
#   verdade só). Quando você melhora uma query lá, o indexador já usa a nova.
#   Sem duplicação.
#
# FLUXO:
#   1. Carrega modelo de embedding UMA vez
#   2. Junta todas as queries (todos os nichos × cenas) + dedup
#   3. Pra cada query: coleta das APIs (Pexels+Pixabay) → acumula
#   4. Indexa TUDO de uma vez (upsert: re-rodar não duplica)
#   5. Loga estatística final por nicho/fonte
#
# CLI:
#   python -m creative_engine.semantic_indexer                  # tudo
#   python -m creative_engine.semantic_indexer --nicho "Cozinha" # só 1 nicho
#   python -m creative_engine.semantic_indexer --limite 5        # menos por query
#   python -m creative_engine.semantic_indexer --dry-run         # só lista queries

import argparse
import sys
import time
from pathlib import Path

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("semantic_indexer")

from creative_engine.semantic_catalog import (
    coletar_das_apis, indexar_itens, _get_modelo_embedding, stats,
)


# =================================================================
# COLETA DAS QUERIES (reusa o autopilot — fonte de verdade única)
# =================================================================

def _carregar_queries() -> dict:
    """
    Lê QUERIES_POR_NICHO_E_CENA + QUERIES_FALLBACK do asset_autopilot.
    Retorna {nicho: {cena: [queries]}}. Se não conseguir importar, devolve {}.
    """
    try:
        from agents.asset_autopilot_agent import (
            QUERIES_POR_NICHO_E_CENA, QUERIES_FALLBACK,
        )
    except Exception as e:
        log.warning(f"   ⚠️  Não consegui importar queries do autopilot ({e})")
        return {}
    # inclui o fallback como um "nicho" Geral pra ter variedade base
    todos = dict(QUERIES_POR_NICHO_E_CENA)
    todos.setdefault("Geral", QUERIES_FALLBACK)
    return todos


def _plano_de_queries(queries_por_nicho: dict, nicho_filtro: str = "") -> list:
    """
    Achata o dicionário em uma lista de (nicho, cena, query), deduplicando
    queries iguais (mesma query em nichos diferentes só coleta 1x, mas
    registra o 1º nicho pra contexto do embedding).

    Returns: lista de tuplas (nicho, cena, query)
    """
    plano = []
    vistas = set()
    for nicho, cenas in queries_por_nicho.items():
        if nicho_filtro and nicho.lower() != nicho_filtro.lower():
            continue
        if not isinstance(cenas, dict):
            continue
        for cena, lista in cenas.items():
            for q in (lista or []):
                chave = q.strip().lower()
                if chave in vistas:
                    continue
                vistas.add(chave)
                plano.append((nicho, cena, q))
    return plano


# =================================================================
# INDEXAÇÃO EM MASSA
# =================================================================

def indexar_tudo(nicho_filtro: str = "", limite: int = 8,
                 tipo: str = "video", dry_run: bool = False,
                 pausa: float = 0.0) -> dict:
    """
    Varre todas as queries (ou de 1 nicho) e indexa no catálogo semântico.

    Args:
        nicho_filtro: se passado, indexa só esse nicho
        limite:       quantos clipes coletar por query, por fonte
        tipo:         "video" ou "photo"
        dry_run:      só lista as queries que coletaria, sem chamar API/indexar
        pausa:        segundos entre queries (gentileza com a API; 0 = sem pausa)

    Returns: {queries, coletados, indexados, ignorados, por_nicho}
    """
    queries_por_nicho = _carregar_queries()
    if not queries_por_nicho:
        log.error("   ❌ Sem queries pra indexar (autopilot não importou)")
        return {"queries": 0, "coletados": 0, "indexados": 0}

    plano = _plano_de_queries(queries_por_nicho, nicho_filtro)
    log.info(f"   📋 {len(plano)} query(ies) única(s) "
             f"{'no nicho ' + nicho_filtro if nicho_filtro else 'em todos os nichos'}")

    if dry_run:
        log.info("\n🔍 [DRY-RUN] Queries que seriam coletadas:")
        nicho_atual = None
        for nicho, cena, q in plano:
            if nicho != nicho_atual:
                log.info(f"\n   ▸ {nicho}:")
                nicho_atual = nicho
            log.info(f"      [{cena}] {q}")
        return {"queries": len(plano), "coletados": 0, "indexados": 0,
                "dry_run": True}

    # Carrega o modelo UMA vez antes do loop (mata o gargalo de recarregar)
    log.info("\n   🧠 Pré-carregando modelo de embedding (1x pra todo o lote)...")
    _get_modelo_embedding()

    # Coleta acumulada de todas as queries, depois indexa de uma vez
    todos_itens = []
    por_nicho = {}
    t0 = time.time()
    for i, (nicho, cena, q) in enumerate(plano, 1):
        log.info(f"   [{i}/{len(plano)}] {nicho}/{cena}: '{q}'")
        try:
            itens = coletar_das_apis(q, tipo=tipo, limite=limite, nicho=nicho)
        except Exception as e:
            log.warning(f"      ⚠️  coleta falhou: {e}")
            itens = []
        # marca a cena no item (enriquece o embedding)
        for it in itens:
            it["cena"] = cena
        todos_itens.extend(itens)
        por_nicho[nicho] = por_nicho.get(nicho, 0) + len(itens)
        log.info(f"      +{len(itens)} candidato(s)")
        if pausa and i < len(plano):
            time.sleep(pausa)

    log.info(f"\n   📦 Total coletado: {len(todos_itens)} candidato(s) "
             f"em {time.time()-t0:.0f}s")

    if not todos_itens:
        log.warning("   ⚠️  Nada coletado (PEXELS_API_KEY/PIXABAY_API_KEY setadas?)")
        return {"queries": len(plano), "coletados": 0, "indexados": 0,
                "por_nicho": por_nicho}

    # Indexa TUDO de uma vez (embeddings em lote — rápido)
    log.info(f"\n   🧮 Indexando {len(todos_itens)} clipe(s) no catálogo...")
    r = indexar_itens(todos_itens)

    return {
        "queries": len(plano),
        "coletados": len(todos_itens),
        "indexados": r["indexados"],
        "ignorados": r["ignorados"],
        "por_nicho": por_nicho,
    }


# =================================================================
# CLI
# =================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Indexador Automático — enche o Catálogo Semântico com variedade")
    parser.add_argument("--nicho", default="",
                        help="Indexar só um nicho (ex: 'Cozinha'). Vazio = todos")
    parser.add_argument("--limite", type=int, default=8,
                        help="Clipes por query, por fonte (default 8)")
    parser.add_argument("--tipo", default="video", choices=["video", "photo"],
                        help="Tipo de asset (default video)")
    parser.add_argument("--pausa", type=float, default=0.0,
                        help="Segundos entre queries (gentileza com a API; default 0)")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="Só lista as queries que coletaria, sem chamar API")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("🧠 INDEXADOR AUTOMÁTICO — Catálogo Semântico Jarvis")
    log.info("=" * 60)

    r = indexar_tudo(nicho_filtro=args.nicho, limite=args.limite,
                     tipo=args.tipo, dry_run=args.dry_run, pausa=args.pausa)

    if r.get("dry_run"):
        log.info(f"\n✅ [DRY-RUN] {r['queries']} query(ies) seriam coletadas")
        return 0

    log.info(f"\n{'═' * 60}")
    log.info("🏁 RESULTADO DA INDEXAÇÃO")
    log.info(f"   Queries varridas: {r['queries']}")
    log.info(f"   Clipes coletados: {r['coletados']}")
    log.info(f"   Indexados/atualizados: {r.get('indexados', 0)}")
    if r.get("por_nicho"):
        log.info(f"   Por nicho:")
        for nicho, n in sorted(r["por_nicho"].items(), key=lambda x: -x[1]):
            log.info(f"      • {nicho}: {n}")
    # estado total do catálogo agora
    try:
        s = stats()
        log.info(f"   📊 Catálogo total agora: {s['total']} clipe(s)")
    except Exception:
        pass
    log.info(f"{'═' * 60}")
    return 0 if r.get("indexados", 0) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())