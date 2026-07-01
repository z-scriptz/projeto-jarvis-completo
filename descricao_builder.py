# creative_engine/descricao_builder.py
# Monta a DESCRIÇÃO de publicação a partir de um plano de conteúdo.
#
# Cada plataforma tem regra própria pro link (decisão já mapeada):
#   - YouTube  → link CLICÁVEL na descrição
#   - Facebook → link CLICÁVEL no texto do post
#   - TikTok   → link NÃO clica → "link na bio"
#   - Instagram→ link só na bio
#
# DECISÕES de design (do Meu Delício):
#   - SEM preço na descrição (preço muda, vídeo postado fica pra sempre →
#     manda pro link, que tem o preço sempre atualizado).
#   - Links RESERVAS (espelhos) NÃO entram na descrição pública (confundiriam
#     o cliente). Ficam guardados separados, pra trocar se o principal morrer.
#
# Entrada: o dict do plano (ultimo_plano.json), que já traz legenda, hashtags,
#          link_afiliado, titulo_real, links_espelho.

import re
from typing import Optional

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("descricao_builder")


# Plataformas onde o link é CLICÁVEL na descrição/texto
_LINK_CLICAVEL = {"youtube", "facebook"}
# Plataformas onde o link NÃO clica (vira "link na bio")
_LINK_NA_BIO = {"tiktok", "instagram"}


def _normalizar_plataforma(p: str) -> str:
    return (p or "").strip().lower()


def _limpar_hashtags(hashtags) -> str:
    """Aceita string ou lista; devolve string de hashtags separadas por espaço."""
    if isinstance(hashtags, list):
        tags = " ".join(str(h) for h in hashtags)
    else:
        tags = str(hashtags or "")
    # garante # em cada tag e remove espaços duplos
    tags = re.sub(r"\s+", " ", tags).strip()
    return tags


def _limpar_cta_link(legenda: str) -> str:
    """
    Remove variações de 'link na bio' / 'confere o link' do fim da legenda
    gerada pela IA, pra não duplicar com a linha de CTA padronizada.
    O Gemini varia o CTA a cada post ('link na bio', 'corre na bio', etc) —
    limpamos pra usar SEMPRE a mesma chamada padronizada (consistência de marca).
    """
    if not legenda:
        return ""
    txt = legenda
    # padrões comuns de CTA de link que a IA gera (case-insensitive)
    padroes = [
        r"link\s+na\s+bio[!.]*",
        r"link\s+no\s+perfil[!.]*",
        r"confere?\s+o?\s*link[^.!]*[!.]*",
        r"corre\s+(na|pra|pro)\s+bio[!.]*",
        r"garant[ae]\s+o?\s*(seu|teu)[^.!]*bio[!.]*",
        r"clica?\s+no?\s+link[^.!]*[!.]*",
        r"link\s+(t[áa]|est[áa])\s+na\s+bio[!.]*",
    ]
    for p in padroes:
        txt = re.sub(p, "", txt, flags=re.IGNORECASE)
    # limpa emojis órfãos e espaços/pontuação que sobraram no fim
    txt = re.sub(r"\s+", " ", txt).strip()
    txt = txt.rstrip(" !.,👉🔥✨🛒➡️👇")  # tira pontuação/emoji de CTA solto no fim
    return txt.strip()


def _titulo_curto(titulo: str, limite: int = 60) -> str:
    """
    Encurta título gigante de marketplace, SEM cortar no meio de termos
    importantes como '3 em 1', '110v', medidas. Corta em vírgula/separador
    natural quando possível; senão, corta na palavra e evita deixar número solto.
    """
    t = re.sub(r"\s+", " ", (titulo or "").strip())
    if len(t) <= limite:
        return t

    # 1) tenta cortar num separador natural antes do limite (vírgula, |, -, /)
    trecho = t[:limite]
    m = re.search(r"^(.*[,|/–—-])\s", trecho)
    if m and len(m.group(1)) >= limite * 0.5:
        return m.group(1).rstrip(" ,|/–—-")

    # 2) corta na última palavra completa
    corte = trecho.rsplit(" ", 1)[0]
    # 3) NÃO deixar número/termo técnico órfão no fim (ex: "3 em", "Kit 5")
    #    se terminar em número OU em palavra muito curta após número, recua
    corte = re.sub(r"\s+\d+\s*(em|x|un|pc|peças?)?$", "", corte, flags=re.IGNORECASE)
    corte = re.sub(r"\s+(em|de|com|para|pra|e|sem|3|2)$", "", corte, flags=re.IGNORECASE)
    return corte.strip() + "..."


def montar_descricao(plano: dict, plataforma: Optional[str] = None) -> dict:
    """
    Monta a descrição de publicação a partir do plano.

    Args:
        plano: dict do plano (ultimo_plano.json)
        plataforma: sobrescreve a plataforma do plano, se quiser

    Returns:
        {
          "plataforma": str,
          "descricao": str,          # texto pronto pra publicar
          "link_principal": str,     # o link de afiliado (pra bio ou descrição)
          "links_reserva": {...},    # reservas guardados (NÃO vão na descrição)
          "tem_link": bool,
        }
    """
    plat = _normalizar_plataforma(plataforma or plano.get("plataforma", "tiktok"))

    legenda = (plano.get("legenda") or "").strip()
    titulo = _titulo_curto(plano.get("titulo_real") or plano.get("produto") or "")
    hashtags = _limpar_hashtags(plano.get("hashtags"))

    # Link principal + reservas
    links_espelho = plano.get("links_espelho") or {}
    link_principal = (plano.get("link_afiliado")
                      or links_espelho.get("principal")
                      or "")
    reservas = {k: v for k, v in links_espelho.items() if k != "principal"}

    # Remove hashtags da legenda (pra não duplicar — elas vão no fim)
    legenda_sem_tags = re.sub(r"#\S+", "", legenda).strip()
    legenda_sem_tags = re.sub(r"\s+", " ", legenda_sem_tags).strip()
    # Remove CTA de link da legenda (pra não duplicar com a linha padronizada)
    legenda_sem_tags = _limpar_cta_link(legenda_sem_tags)

    linhas = []
    if legenda_sem_tags:
        linhas.append(legenda_sem_tags)
    linhas.append("")  # linha em branco

    if plat in _LINK_CLICAVEL and link_principal:
        # YouTube/Facebook: link clicável
        linhas.append(f"🛒 GARANTA O SEU AQUI: {link_principal}")
        if titulo:
            linhas.append(f"💰 {titulo}")
        linhas.append("")
        linhas.append("⚠️ Oferta por tempo limitado!")
    else:
        # TikTok/Instagram: link na bio
        linhas.append("👉 Garanta o seu no LINK DA BIO!")
        if titulo:
            linhas.append(f"💰 {titulo}")
        linhas.append("🔥 Corre que tá saindo rápido!")

    if hashtags:
        linhas.append("")
        linhas.append(hashtags)

    descricao = "\n".join(linhas).strip()

    return {
        "plataforma": plat,
        "descricao": descricao,
        "link_principal": link_principal,
        "links_reserva": reservas,
        "tem_link": bool(link_principal),
    }


def montar_todas(plano: dict, plataformas: Optional[list] = None) -> dict:
    """
    Monta a descrição pra várias plataformas de uma vez.
    Returns: {plataforma: resultado_de_montar_descricao}
    """
    if plataformas is None:
        plataformas = ["tiktok", "youtube", "instagram", "facebook"]
    return {p: montar_descricao(plano, plataforma=p) for p in plataformas}


# CLI pra testar
def main():
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Monta descrição de publicação a partir do plano")
    parser.add_argument("--plano", default="",
                        help="Caminho do plano JSON (default: ultimo_plano.json)")
    parser.add_argument("--plataforma", default="",
                        help="tiktok|youtube|instagram|facebook (vazio = todas)")
    args = parser.parse_args()

    caminho = args.plano or str(
        Path(__file__).parent.parent / "shared" / "content_plans" / "ultimo_plano.json")
    try:
        with open(caminho, encoding="utf-8") as f:
            plano = json.load(f)
    except Exception as e:
        print(f"❌ erro lendo plano: {e}")
        return 1

    print("=" * 64)
    print(f"📝 DESCRIÇÕES — '{plano.get('produto', '?')}'")
    print("=" * 64)

    plataformas = [args.plataforma] if args.plataforma else None
    todas = montar_todas(plano, plataformas)

    for plat, r in todas.items():
        print(f"\n{'─' * 64}")
        print(f"📱 {plat.upper()}  {'(link clica)' if plat in _LINK_CLICAVEL else '(link na bio)'}")
        print(f"{'─' * 64}")
        print(r["descricao"])
        if r["links_reserva"]:
            print(f"\n   [reservas guardados p/ você: {list(r['links_reserva'].values())}]")
        elif not r["tem_link"]:
            print(f"\n   ⚠️  sem link de afiliado no plano")
    print()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())