# agents/curar_fila.py
# CURADOR DE FILA — transforma o "mapa da mina" em ação.
#
# Lê o relatório do validador (validacao_fila.json), mantém só os produtos que
# valem a pena (mina_ouro + ok), descarta os fracos/desertos, e salva a fila
# curada em DOIS lugares:
#   1. produtos_fila.json  (fallback local limpo)
#   2. planilha Google Sheets (a dashboard oficial, só com o filé mignon)
#
# Cada produto curado guarda DOIS nomes (decisão estratégica):
#   - busca:   nome genérico ("Cortador de Legumes") → keyword pra minerar
#   - campeao: nome real do produto ("Processador Elétrico 600ml") → referência
#              pro roteiro do Gemini falar a mesma língua do link
#
# SEGURANÇA: por padrão roda em modo --simular (mostra o que faria, SEM escrever).
# Pra aplicar de verdade, use --aplicar.
#
# Uso:
#   python -m agents.curar_fila                  # simula (não escreve nada)
#   python -m agents.curar_fila --aplicar        # aplica de verdade
#   python -m agents.curar_fila --aplicar --so-json   # só JSON (não toca planilha)
#   python -m agents.curar_fila --manter ok,mina_ouro # quais classes manter

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
    log = logging.getLogger("curar_fila")

RELATORIO_PATH = Path(__file__).parent.parent / "shared" / "content_plans" / "validacao_fila.json"
JSON_FILA = Path(__file__).parent.parent / "shared" / "produtos_fila.json"

# Classes que, por padrão, MERECEM ficar na fila (o filé mignon)
CLASSES_MANTER_PADRAO = {"mina_ouro", "ok"}


def _carregar_relatorio() -> dict:
    """Lê o validacao_fila.json gerado pelo validador."""
    if not RELATORIO_PATH.exists():
        log.error(f"❌ Relatório não encontrado: {RELATORIO_PATH}")
        log.error("   Rode primeiro: python -m agents.validar_fila")
        return {}
    try:
        with open(RELATORIO_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"❌ erro lendo relatório: {e}")
        return {}


def _filtrar_aprovados(relatorio: dict, classes_manter: set) -> list:
    """
    Filtra os produtos do relatório, mantendo só as classes desejadas.
    Retorna lista de dicts com busca (nome genérico) + campeao (nome real) + dados.
    """
    aprovados = []
    for p in relatorio.get("produtos", []):
        if p.get("classe") not in classes_manter:
            continue
        aprovados.append({
            "busca":          p.get("produto", ""),       # nome genérico (keyword)
            "campeao":        p.get("campeao", ""),         # nome real do produto
            "classe":         p.get("classe", ""),
            "comissao_rate":  p.get("comissao_rate", 0),
            "comissao_valor": p.get("comissao_valor", 0),
            "vendas":         p.get("vendas", 0),
            "rating":         p.get("rating", 0),
            "score":          p.get("score", 0),
        })
    return aprovados


def _salvar_json(aprovados: list, simular: bool) -> bool:
    """Salva a fila curada no produtos_fila.json (formato rico: lista de dicts)."""
    if simular:
        log.info(f"   [simulação] gravaria {len(aprovados)} produtos em {JSON_FILA.name}")
        return True
    try:
        JSON_FILA.parent.mkdir(parents=True, exist_ok=True)
        # Salva no formato rico (dicts com busca + campeao), que o validador
        # e o pipeline conseguem ler (ambos aceitam dict com 'produto'/'busca').
        saida = [{"produto": a["busca"], "campeao": a["campeao"],
                  "classe": a["classe"]} for a in aprovados]
        with open(JSON_FILA, "w", encoding="utf-8") as f:
            json.dump(saida, f, ensure_ascii=False, indent=2)
        log.info(f"   ✅ {len(aprovados)} produtos salvos em {JSON_FILA}")
        return True
    except Exception as e:
        log.error(f"   ❌ erro salvando JSON: {e}")
        return False


def _escrever_planilha(aprovados: list, simular: bool) -> bool:
    """
    Escreve os produtos curados na planilha Google Sheets (aba Fila_de_Postagem).
    Anti-duplicação: não adiciona produto que já está lá.
    Reusa a conexão do sheets_engine (não reinventa).
    """
    try:
        from memory.sheets_engine import (
            conectar_planilha, ABA_FILA, ColFila, ler_produtos_pendentes,
        )
    except Exception as e:
        log.warning(f"   ⚠️  sheets_engine indisponível ({str(e)[:50]}) — pulei a planilha")
        return False

    # Lê o que já existe pra não duplicar
    try:
        aba = conectar_planilha().worksheet(ABA_FILA)
        existentes_raw = aba.get_all_values()
        # nomes de produto já na planilha (coluna PRODUTO), normalizado
        ja_existe = set()
        for row in existentes_raw[1:]:
            if len(row) >= ColFila.PRODUTO:
                nome = row[ColFila.PRODUTO - 1].strip().lower()
                if nome:
                    ja_existe.add(nome)
    except Exception as e:
        log.error(f"   ❌ erro lendo planilha pra checar duplicatas: {e}")
        return False

    # Monta as linhas novas (só os que ainda não existem)
    novas = []
    pulados = 0
    hoje = time.strftime("%d/%m/%Y %H:%M")
    for a in aprovados:
        nome_busca = a["busca"]
        if nome_busca.strip().lower() in ja_existe:
            pulados += 1
            continue
        # Linha no formato da ColFila: data, produto, roteiro, legenda, cta,
        # hashtags, status, link_post, erro, plataforma
        # Guardamos o nome do campeão no campo ERRO? Não — melhor não poluir.
        # Usamos o produto = nome genérico (busca). O campeão vai como referência
        # no JSON; na planilha guardamos o genérico (que o pipeline usa).
        linha = [hoje, nome_busca, "", "", "", "", "Pendente", "", "", "TikTok"]
        novas.append(linha)

    if simular:
        log.info(f"   [simulação] adicionaria {len(novas)} produtos novos à planilha "
                 f"({pulados} já existiam)")
        return True

    if not novas:
        log.info(f"   ℹ️  nada novo pra adicionar ({pulados} já estavam na planilha)")
        return True

    try:
        aba.append_rows(novas, value_input_option="USER_ENTERED")
        log.info(f"   ✅ {len(novas)} produtos adicionados à planilha "
                 f"({pulados} já existiam, pulados)")
        return True
    except Exception as e:
        log.error(f"   ❌ erro escrevendo na planilha: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Curador de Fila — mantém só os campeões (minas de ouro + ok)")
    parser.add_argument("--aplicar", action="store_true",
                        help="Aplica de verdade (sem isso, só SIMULA)")
    parser.add_argument("--so-json", action="store_true", dest="so_json",
                        help="Só escreve no JSON (não toca na planilha)")
    parser.add_argument("--so-planilha", action="store_true", dest="so_planilha",
                        help="Só escreve na planilha (não toca no JSON)")
    parser.add_argument("--manter", default="mina_ouro,ok",
                        help="Classes a manter, separadas por vírgula "
                             "(padrão: mina_ouro,ok)")
    args = parser.parse_args()

    simular = not args.aplicar

    log.info("=" * 60)
    log.info("✂️  CURADOR DE FILA" + ("  [MODO SIMULAÇÃO]" if simular else "  [APLICANDO]"))
    log.info("=" * 60)

    relatorio = _carregar_relatorio()
    if not relatorio:
        return 1

    classes_manter = {c.strip() for c in args.manter.split(",") if c.strip()}
    aprovados = _filtrar_aprovados(relatorio, classes_manter)

    total = relatorio.get("total", len(relatorio.get("produtos", [])))
    log.info(f"📊 Relatório: {total} produtos analisados")
    log.info(f"   Mantendo classes: {', '.join(sorted(classes_manter))}")
    log.info(f"   ✅ {len(aprovados)} produtos aprovados | "
             f"❌ {total - len(aprovados)} descartados\n")

    # Mostra os aprovados
    print("PRODUTOS QUE FICAM NA FILA:")
    for i, a in enumerate(aprovados, 1):
        emoji = "💰" if a["classe"] == "mina_ouro" else "✅"
        print(f"  {i}. {emoji} {a['busca']}")
        if a["campeao"]:
            print(f"      → campeão: {a['campeao'][:50]}")
            print(f"      → R$ {a['comissao_valor']:.2f} | {a['vendas']} vendas | {a['rating']:.1f}⭐")
    print()

    if simular:
        print("⚠️  MODO SIMULAÇÃO — nada foi alterado.")
        print("    Rode com --aplicar pra salvar de verdade.\n")

    # Escreve nos destinos
    ok_json = ok_plan = True
    if not args.so_planilha:
        log.info("💾 JSON local:")
        ok_json = _salvar_json(aprovados, simular)
    if not args.so_json:
        log.info("📊 Planilha Google Sheets:")
        ok_plan = _escrever_planilha(aprovados, simular)

    print()
    if simular:
        log.info("✅ Simulação concluída — confira a lista acima e rode --aplicar")
    else:
        log.info("✅ Curadoria aplicada!" if (ok_json and ok_plan)
                 else "⚠️  Curadoria parcial — veja os avisos acima")
    return 0


if __name__ == "__main__":
    sys.exit(main())