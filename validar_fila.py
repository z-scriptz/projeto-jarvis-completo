# agents/validar_fila.py
# VALIDADOR DE FILA — o "mapa da mina" do Jarvis.
#
# Varre todos os produtos da fila (planilha Google Sheets, com fallback pro
# JSON local) e roda a mineração da Shopee em cada um. Entrega um relatório
# ranqueado dizendo quais produtos são MINA DE OURO (comissão alta + tração +
# nota boa) e quais são DESERTOS (sem produto bom de afiliado).
#
# Objetivo: parar de gravar vídeo no escuro. Você foca energia só nos produtos
# que o mercado já validou.
#
# Uso:
#   python -m agents.validar_fila                 # lê da planilha (fallback JSON)
#   python -m agents.validar_fila --json          # força ler do JSON local
#   python -m agents.validar_fila --vendas-min 20 # corte mais rigoroso
#   python -m agents.validar_fila --pausa 2.0     # pausa entre buscas (rate limit)

import os
import sys
import json
import time
import argparse
from pathlib import Path

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("validar_fila")

# Import defensivo da Shopee (o coração do validador)
try:
    from integrations.shopee_affiliate import minerar_oportunidades, NOTA_MINIMA, VENDAS_MINIMAS
    _SHOPEE_OK = True
except Exception as e:
    _SHOPEE_OK = False
    _SHOPEE_ERRO = str(e)

# Caminho do JSON de fallback
JSON_FILA = Path(__file__).parent.parent / "shared" / "produtos_fila.json"
# Onde salvar o relatório
RELATORIO_PATH = Path(__file__).parent.parent / "shared" / "content_plans" / "validacao_fila.json"

# Limiares pra classificar um produto (em cima do resultado da mineração)
MINA_OURO_VENDAS = 100      # campeão com 100+ vendas = tração forte
MINA_OURO_COMISSAO = 0.10   # 10%+ de comissão = retorno bom


def _ler_fila_planilha() -> list:
    """Lê os produtos da planilha. Retorna lista de nomes (ou [] se falhar/vazia)."""
    try:
        from memory.sheets_engine import ler_produtos_pendentes
    except Exception as e:
        log.warning(f"   ⚠️  sheets_engine indisponível ({str(e)[:50]}) — tentando JSON")
        return []
    try:
        pendentes = ler_produtos_pendentes()
        nomes = [p["produto"] for p in pendentes if p.get("produto")]
        return nomes
    except Exception as e:
        log.warning(f"   ⚠️  erro lendo planilha ({str(e)[:50]}) — tentando JSON")
        return []


def _ler_fila_json() -> list:
    """Lê os produtos do JSON local. Aceita lista de strings ou de dicts."""
    if not JSON_FILA.exists():
        log.error(f"   ❌ {JSON_FILA} não encontrado")
        return []
    try:
        with open(JSON_FILA, encoding="utf-8") as f:
            dados = json.load(f)
    except Exception as e:
        log.error(f"   ❌ erro lendo JSON: {e}")
        return []
    nomes = []
    for item in dados:
        if isinstance(item, str):
            nomes.append(item)
        elif isinstance(item, dict):
            nome = item.get("produto") or item.get("nome")
            if nome:
                nomes.append(nome)
    return nomes


def _classificar(m: dict) -> str:
    """
    Classifica o resultado da mineração de um produto:
      'mina_ouro' — campeão forte (tração + comissão boa)
      'ok'        — tem produto válido, mas não é campeão brutal
      'fraco'     — passou no corte mínimo mas é fraco
      'deserto'   — nenhum produto válido (sem mina)
    """
    if not m.get("ok"):
        return "deserto"
    c = m["campeao"]
    vendas = int(c.get("vendas", 0) or 0)
    comissao = float(c.get("comissao_rate", 0) or 0)
    if vendas >= MINA_OURO_VENDAS and comissao >= MINA_OURO_COMISSAO:
        return "mina_ouro"
    if vendas >= MINA_OURO_VENDAS or comissao >= MINA_OURO_COMISSAO:
        return "ok"
    return "fraco"


def validar_fila(produtos: list, vendas_minimas: int = None,
                 pausa: float = 1.5) -> dict:
    """
    Roda a mineração em cada produto da fila e classifica.

    Args:
        produtos: lista de nomes de produtos
        vendas_minimas: corte de vendas (None = usa o padrão da Shopee)
        pausa: segundos entre buscas (evita rate limit da Shopee)

    Returns: dict com os produtos classificados e ordenados por potencial.
    """
    resultados = []
    total = len(produtos)
    for i, nome in enumerate(produtos, 1):
        log.info(f"   [{i}/{total}] Minerando '{nome}'...")
        try:
            kwargs = {}
            if vendas_minimas is not None:
                kwargs["vendas_minimas"] = vendas_minimas
            m = minerar_oportunidades(nome, **kwargs)
        except Exception as e:
            log.warning(f"      ⚠️  erro: {str(e)[:60]}")
            m = {"ok": False, "erro": str(e)[:100]}

        classe = _classificar(m)
        if m.get("ok"):
            c = m["campeao"]
            resultados.append({
                "produto": nome,
                "classe": classe,
                "campeao": c.get("nome", ""),
                "comissao_rate": c.get("comissao_rate", 0),
                "comissao_valor": c.get("comissao_valor", 0),
                "vendas": c.get("vendas", 0),
                "rating": c.get("rating", 0),
                "score": c.get("score", 0),
                "relevancia": c.get("relevancia", 0),
            })
        else:
            resultados.append({
                "produto": nome, "classe": classe,
                "motivo": m.get("erro", "")[:120],
            })

        # pausa pra não tomar rate limit (exceto no último)
        if i < total and pausa > 0:
            time.sleep(pausa)

    # Ordena: mina_ouro > ok > fraco > deserto, e por score dentro de cada
    ordem_classe = {"mina_ouro": 0, "ok": 1, "fraco": 2, "deserto": 3}
    resultados.sort(key=lambda r: (ordem_classe.get(r["classe"], 9),
                                   -float(r.get("score", 0) or 0)))
    # Contagem por classe
    contagem = {}
    for r in resultados:
        contagem[r["classe"]] = contagem.get(r["classe"], 0) + 1

    return {"total": total, "contagem": contagem, "produtos": resultados}


def _imprimir_relatorio(rel: dict):
    """Imprime o relatório de forma legível (o mapa da mina)."""
    emoji = {"mina_ouro": "💰", "ok": "✅", "fraco": "⚠️", "deserto": "🏜️"}
    rotulo = {"mina_ouro": "MINA DE OURO", "ok": "OK", "fraco": "FRACO",
              "deserto": "DESERTO (sem produto bom)"}

    print("\n" + "=" * 64)
    print("📊 MAPA DA MINA — Relatório de Validação da Fila")
    print("=" * 64)
    c = rel["contagem"]
    print(f"\n   {rel['total']} produtos analisados:")
    for classe in ["mina_ouro", "ok", "fraco", "deserto"]:
        if c.get(classe):
            print(f"   {emoji[classe]} {c[classe]} {rotulo[classe]}")

    print("\n" + "-" * 64)
    print("RANKING (foque nos primeiros, descarte os últimos):")
    print("-" * 64)
    for i, r in enumerate(rel["produtos"], 1):
        e = emoji.get(r["classe"], "")
        print(f"\n  {i}. {e} {r['produto']}  [{rotulo.get(r['classe'], r['classe'])}]")
        if r.get("campeao"):
            print(f"      → {r['campeao'][:50]}")
            print(f"      → comissão {r['comissao_rate']*100:.0f}% "
                  f"(R$ {r['comissao_valor']:.2f}) | {r['vendas']} vendas | "
                  f"{r['rating']:.1f}⭐ | score {r['score']}")
        elif r.get("motivo"):
            print(f"      → {r['motivo']}")
    print("\n" + "=" * 64)


def main():
    parser = argparse.ArgumentParser(
        description="Validador de Fila — minera todos os produtos e gera o mapa da mina")
    parser.add_argument("--json", action="store_true",
                        help="Força ler do produtos_fila.json (em vez da planilha)")
    parser.add_argument("--vendas-min", type=int, default=None, dest="vendas_min",
                        help="Corte de vendas mínimas (padrão = o da Shopee)")
    parser.add_argument("--pausa", type=float, default=1.5,
                        help="Segundos entre buscas pra evitar rate limit (padrão 1.5)")
    parser.add_argument("--limite", type=int, default=0,
                        help="Validar só os N primeiros produtos (0 = todos)")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("🗺️  VALIDADOR DE FILA — Mapa da Mina")
    log.info("=" * 60)

    if not _SHOPEE_OK:
        log.error(f"❌ Shopee indisponível: {_SHOPEE_ERRO}")
        print("\n💡 Configure SHOPEE_APP_ID e SHOPEE_APP_SECRET primeiro.")
        return 1

    # Lê a fila — planilha primeiro (com fallback pro JSON), ou JSON forçado
    if args.json:
        log.info("📋 Lendo fila do JSON local (forçado)")
        produtos = _ler_fila_json()
    else:
        log.info("📋 Lendo fila da planilha Google Sheets")
        produtos = _ler_fila_planilha()
        if not produtos:
            log.info("   Planilha vazia/indisponível — usando JSON local como fallback")
            produtos = _ler_fila_json()

    if not produtos:
        log.error("❌ Nenhum produto encontrado (nem na planilha nem no JSON)")
        return 1

    if args.limite > 0:
        produtos = produtos[:args.limite]

    log.info(f"🔍 Validando {len(produtos)} produto(s) "
             f"(pausa {args.pausa}s entre buscas pra respeitar rate limit)...")

    rel = validar_fila(produtos, vendas_minimas=args.vendas_min, pausa=args.pausa)

    _imprimir_relatorio(rel)

    # Salva o relatório
    try:
        RELATORIO_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(RELATORIO_PATH, "w", encoding="utf-8") as f:
            json.dump(rel, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Relatório salvo: {RELATORIO_PATH}")
    except Exception as e:
        log.warning(f"não consegui salvar o relatório: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())