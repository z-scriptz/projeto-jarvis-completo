#!/usr/bin/env python3
# limpar_cache_legenda.py
# ════════════════════════════════════════════════════════════════════
# Remove a entrada poluída do cache cooperativo que estava entregando
# a coordenada (358, 566) — que NÃO é o textarea de legenda, mas sim o
# nome do arquivo de vídeo no painel lateral.
#
# Sintoma que isso resolve: preencher_detalhes_tiktok reportava
# "10/10 passos OK" mas a legenda ficava VAZIA, porque o clique caía
# no lugar errado (cache cooperativo reciclando coordenada ruim).
#
# Rodar UMA vez:
#   python limpar_cache_legenda.py
#
# Pode rodar de C:\AgenteIA\ ou de onde o refs/interface_cache.json estiver.
# ════════════════════════════════════════════════════════════════════

import json
from pathlib import Path

# Caminho do cache — ajusta se o seu estiver em outro lugar
CACHE_PATHS_POSSIVEIS = [
    Path("refs/interface_cache.json"),
    Path("C:/AgenteIA/refs/interface_cache.json"),
    Path(__file__).parent / "refs" / "interface_cache.json",
]

# Chaves que sabemos estar poluídas (substring — qualquer chave que contenha)
CHAVES_POLUIDAS_SUBSTRINGS = [
    "tela_detalhes_tiktok_apos_upload__campo_de_descricao_do_video_onde_aparecem_legenda_e_hashtags_abaixo_do_titulo",
]


def encontrar_cache() -> Path | None:
    for p in CACHE_PATHS_POSSIVEIS:
        if p.exists():
            return p
    return None


def main():
    cache_path = encontrar_cache()
    if not cache_path:
        print("❌ Não encontrei interface_cache.json em nenhum caminho conhecido.")
        print("   Caminhos testados:")
        for p in CACHE_PATHS_POSSIVEIS:
            print(f"     - {p}")
        print("   Edite CACHE_PATHS_POSSIVEIS no script com o caminho certo.")
        return

    print(f"📂 Cache encontrado: {cache_path}")

    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Cache não é JSON válido: {e}")
        return

    if not isinstance(cache, dict):
        print("❌ Cache não é um dicionário — formato inesperado.")
        return

    total_antes = len(cache)
    removidas = []

    for chave in list(cache.keys()):
        for substring in CHAVES_POLUIDAS_SUBSTRINGS:
            if substring in chave:
                coord = cache[chave]
                x = coord.get("x") if isinstance(coord, dict) else "?"
                y = coord.get("y") if isinstance(coord, dict) else "?"
                print(f"  🗑️  Removendo: '{chave[:60]}...' → ({x}, {y})")
                del cache[chave]
                removidas.append(chave)
                break

    if not removidas:
        print("  ✓ Nenhuma entrada poluída encontrada — cache já está limpo!")
        return

    # Backup antes de salvar
    backup_path = cache_path.with_suffix(".json.bak")
    backup_path.write_text(
        json.dumps(json.loads(cache_path.read_text(encoding="utf-8")),
                   ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"  💾 Backup salvo em: {backup_path}")

    # Salva cache limpo
    cache_path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n✅ Limpeza concluída:")
    print(f"   Entradas antes:   {total_antes}")
    print(f"   Removidas:        {len(removidas)}")
    print(f"   Entradas depois:  {len(cache)}")
    print(f"\n   Na próxima execução, o campo de legenda será localizado")
    print(f"   fresco pelo Gemini (sem reciclar a coordenada errada).")


if __name__ == "__main__":
    main()