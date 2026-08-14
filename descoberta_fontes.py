#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# descoberta_fontes.py -- ALAVANCA 2: DESCOBERTA AUTÔNOMA de fontes novas.
# Varre HASHTAGS-semente por nicho no TikTok, extrai os PERFIS-AUTORES dos virais,
# tira os que a gente já tem, pontua (frequência + views) e escreve CANDIDATOS num
# arquivo de revisão (+ auto-adiciona os fortes na lista de fontes, com a tag do
# nicho). Usa navegador real (ig_playwright, cookies/proxy). NÃO roda no pipeline principal
# — é ferramenta manual/cron, então é seguro (não posta nada, só sugere fontes).
#
# Uso (VPS):
#   python3 descoberta_fontes.py                    # todos os nichos → candidatos_fontes.txt
#   python3 descoberta_fontes.py --nicho beleza     # só um nicho
#   python3 descoberta_fontes.py --auto 60          # auto-adiciona quem tiver score >= 60
#   python3 descoberta_fontes.py --teste "#maquiagem"          # DEBUG: scraping de 1 hashtag
#   python3 descoberta_fontes.py --teste "#maquiagem" --raw    # DEBUG: janela do navegador aberta
#
# >>> PRA EDITAR: mexa em HASHTAGS (semente por nicho). São 100% suas. <<<
import os
import re
import sys
import json
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).resolve().parent
PERFIS_TXT = BASE / "tiktok_perfis.txt"
IG_PERFIS_TXT = BASE / "instagram_perfis.txt"
CANDIDATOS = BASE / "candidatos_fontes.txt"                 # revisão humana
VISTOS = BASE / "shared" / "fontes_descobertas.json"       # cache p/ não repropor

# Hashtags-SEMENTE por nicho (o ponto de partida da varredura). Edite à vontade.
HASHTAGS = {
    "beleza": ["#maquiagem", "#skincare", "#resenhadebeleza", "#achadinhosdebeleza",
               "#autocuidado", "#perfumes"],
    "tech":   ["#techtok", "#gadgets", "#achadinhostech", "#tecnologia", "#setup",
               "#eletronicos"],
    "geral":  ["#achadinhos", "#achadinhosshopee", "#utilidadesdomesticas",
               "#organizacao", "#achadinhosdacasa"],
}

MIN_VIEWS_CAND = int(os.environ.get("DESC_MIN_VIEWS", 30000))  # viral p/ contar o autor
POR_HASHTAG = int(os.environ.get("DESC_POR_HASHTAG", 30))      # vídeos por hashtag

# O sinal mais forte de "conta de PRODUTO/afiliado" (não creator) está no @ dela:
# quem vende anuncia no próprio nome. A frequência entre hashtags é fraca (o feed do
# TikTok é personalizado demais p/ repetir autor), então o nome é o que separa
# vendedor de creator/gringo/psicóloga que só aparece no meio da hashtag.
_KW_PRODUTO = (
    "achadinho", "achadin", "achados", "achadit", "achei", "indica", "recomend",
    "comprinha", "compras", "oferta", "promo", "promoc", "vitrine", "picks", "loja",
    "shop", "store", "mania", "dicas", "tips", "resenha", "review", "desconto",
    "cupom", "barato", "utilidade", "produto", "importad", "tem.de.tudo", "temdetudo",
)
_KW_NICHO = {
    "beleza": ("belez", "beauty", "makeup", "maquiag", "perfume", "cosmetic",
               "skincare", "glow", "glam", "batom", "cabelo"),
    "tech":   ("tech", "gadget", "eletro", "digital", "games", "gamer", "geek",
               "setup"),
    "geral":  (),
}


def _sem_acento(s: str) -> str:
    return (s or "").translate(str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc"))


def _bonus_nome(handle: str, nicho: str) -> int:
    """Bônus de score pelo @: nome de conta de produto/afiliado (+45) ou do nicho
    (+30). É o que faz um perfil de venda aparecer forte mesmo aparecendo 1x só."""
    h = _sem_acento((handle or "").lower())
    if any(k in h for k in _KW_PRODUTO):
        return 45
    if any(k in h for k in _KW_NICHO.get(nicho, ())):
        return 30
    return 0


def _log(m):
    print(f"[descoberta] {m}", flush=True)


# ── scraping (Playwright/Chromium real — yt-dlp morreu pra hashtag do TikTok) ─
def _autores_da_hashtag_tiktok(tag: str, limite: int) -> list:
    """Retorna [(uploader, views)] dos vídeos de uma hashtag no TikTok.
    Usa o navegador real (ig_playwright.autores_hashtag_tiktok) porque o extractor
    de hashtag do yt-dlp foi marcado como 'broken'. views pode vir 0 — aí não filtra."""
    t = tag.lstrip("#").strip()
    if not t:
        return []
    try:
        from ig_playwright import autores_hashtag_tiktok
        return autores_hashtag_tiktok(t, limite, headless=True)
    except Exception as e:
        _log(f"  ⚠️  hashtag {tag} falhou no Playwright: {str(e)[:100]}")
        return []


# ── fontes já conhecidas (não repropor) ─────────────────────────────────────
def _perfil_limpo(linha: str) -> str:
    """Extrai só o @handle de uma linha de fonte (sem tag #nicho, sem comentário)."""
    l = linha.strip()
    if not l or l.startswith("#"):
        return ""
    l = re.split(r"[\s#]", l)[0]     # corta na 1ª tag/espaço
    return l.lstrip("@").lower()


def _fontes_conhecidas() -> set:
    known = set()
    for p in (PERFIS_TXT, IG_PERFIS_TXT, CANDIDATOS):
        if p.exists():
            for l in p.read_text(encoding="utf-8").splitlines():
                u = _perfil_limpo(l)
                if u:
                    known.add(u)
    return known


def _ler_vistos() -> dict:
    try:
        return json.loads(VISTOS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _salvar_vistos(d: dict):
    VISTOS.parent.mkdir(parents=True, exist_ok=True)
    VISTOS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


# ── descoberta + pontuação ──────────────────────────────────────────────────
def descobrir_nicho(nicho: str) -> list:
    """Varre as hashtags do nicho, agrega autores e pontua. Retorna candidatos
    ORDENADOS por score (só os que a gente ainda não tem)."""
    freq, maxv = defaultdict(int), defaultdict(int)
    tags = HASHTAGS.get(nicho, [])
    for tag in tags:
        autores = _autores_da_hashtag_tiktok(tag, POR_HASHTAG)
        _log(f"  {tag}: {len(autores)} vídeos")
        for up, vw in autores:
            if vw and vw < MIN_VIEWS_CAND:      # só conta autor de viral de verdade
                continue                        # (se views desconhecidas, conta)
            k = up.lower()
            freq[k] += 1
            maxv[k] = max(maxv[k], vw)
    conhecidos = _fontes_conhecidas()
    cands = []
    for up, f in freq.items():
        if up in conhecidos:
            continue
        # score = NOME de conta de produto/afiliado (sinal forte) + frequência entre
        # hashtags (fraco no TikTok, mas conta) + bônus de views. Piso/teto 1..100.
        bn = _bonus_nome(up, nicho)
        score = min(100, bn + f * 18 + min(40, maxv[up] // 6000))
        cands.append({"perfil": up, "nicho": nicho, "freq": f,
                      "max_views": maxv[up], "score": score, "nome": bool(bn)})
    # ordena por score; empate → quem tem nome de produto primeiro, depois freq
    cands.sort(key=lambda c: (c["score"], c["nome"], c["freq"]), reverse=True)
    return cands


def _append_fonte(perfil: str, nicho: str):
    """Adiciona o perfil (com tag do nicho) na lista de fontes do TikTok."""
    linha = f"{perfil} #{nicho}\n"
    with open(PERFIS_TXT, "a", encoding="utf-8") as f:
        f.write(linha)


def registrar(cands: list, auto_thr=None) -> tuple:
    """Escreve candidatos NOVOS no arquivo de revisão; auto-adiciona os fortes."""
    vistos = _ler_vistos()
    novos = [c for c in cands if c["perfil"] not in vistos]
    if novos:
        with open(CANDIDATOS, "a", encoding="utf-8") as f:
            for c in novos:
                f.write(f"{c['perfil']} #{c['nicho']}   # score={c['score']} "
                        f"freq={c['freq']} views={c['max_views']}\n")
    add = 0
    for c in novos:
        if auto_thr is not None and c["score"] >= auto_thr:
            _append_fonte(c["perfil"], c["nicho"])
            c["auto"] = True
            add += 1
        vistos[c["perfil"]] = {"nicho": c["nicho"], "score": c["score"]}
    _salvar_vistos(vistos)
    return len(novos), add


def main():
    args = sys.argv[1:]

    # DEBUG: testa o scraping de UMA hashtag (a prova de que o navegador pega a hashtag)
    if "--teste" in args:
        try:
            tag = args[args.index("--teste") + 1]
        except IndexError:
            print("uso: descoberta_fontes.py --teste \"#hashtag\""); return 1
        if "--raw" in args:      # diagnóstico: janela do navegador ABERTA (headed) p/ ver
            from ig_playwright import autores_hashtag_tiktok
            autores = autores_hashtag_tiktok(tag.lstrip("#").strip(), 15, headless=False)
            print(f"[raw/headed] {len(autores)} autor(es):")
            for h, vw in autores:
                print(f"  @{h}  {vw:,} views" if vw else f"  @{h}  (views ?)")
            return 0
        autores = _autores_da_hashtag_tiktok(tag, 20)
        print(f"hashtag {tag}: {len(autores)} vídeo(s)")
        for up, vw in autores[:20]:
            print(f"  @{up}  {vw:,} views" if vw else f"  @{up}  (views ?)")
        if not autores:
            print("  ⚠️  0 autores — o TikTok pode ter bloqueado/captcha. Tente com "
                  "cookies do TikTok no YTDLP_COOKIES, ou rode --raw p/ ver a janela.")
        return 0

    nichos = list(HASHTAGS.keys())
    if "--nicho" in args:
        try:
            nichos = [args[args.index("--nicho") + 1].lower()]
        except IndexError:
            pass
    auto_thr = None
    if "--auto" in args:
        try:
            auto_thr = int(args[args.index("--auto") + 1])
        except (IndexError, ValueError):
            auto_thr = 60

    total_novos = total_add = 0
    for n in nichos:
        _log(f"nicho '{n}' — varrendo {len(HASHTAGS.get(n, []))} hashtags…")
        cands = descobrir_nicho(n)
        nv, ad = registrar(cands, auto_thr)
        total_novos += nv
        total_add += ad
        _log(f"[{n}] {len(cands)} candidatos | {nv} novos | {ad} auto-adicionados")
        for c in cands[:8]:
            marca = " ⬆️AUTO" if c.get("auto") else ""
            print(f"   @{c['perfil']}  score={c['score']} "
                  f"(freq={c['freq']}, {c['max_views']:,} views){marca}")
    print(f"\n✅ {total_novos} candidatos NOVOS em {CANDIDATOS.name} (revise e promova "
          f"pros perfis com a tag) · {total_add} auto-adicionados em {PERFIS_TXT.name}")
    if auto_thr is None:
        print("   (rode com --auto SCORE pra auto-adicionar os fortes, ex.: --auto 60)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
