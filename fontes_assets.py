#!/usr/bin/env python3
# fontes_assets.py -- a MESMA foto de produto, em outras fontes.
#
# POR QUE EXISTE (12/08)
# O piloto barrou o Kit 10 Calcinhas: 1 foto, 43% de texto promocional queimado,
# três enquadramentos derivados dela, todos reprovados. Nível D, não produzir.
# Foi o `BLOQUEADO_SEM_LEVER` funcionando — e a lição dele é que edição não
# conserta matéria-prima. A galeria da Shopee está fechada por anti-bot (três
# medições em 10/08), então a saída é a MESMA peça em OUTRA loja.
#
# ⚠️ O RISCO QUE MANDA NO DESENHO
# Foto errada é MUITO pior que foto ruim: o vídeo mostra um produto e o cliente
# recebe outro. Então este arquivo é, antes de tudo, um verificador de
# identidade — a coleta é a parte fácil.
#
# E o `amazon_playwright.recusar()` já diz, no próprio comentário, que não dá
# conta disso sozinho:
#
#   "Rede de segurança fraca... título da Amazon é longo e cheio de
#    palavra-chave, então quase sempre casa alguma palavra do termo. Só pega o
#    caso extremo. Quem separa 'parecido' de 'certo' é o olho humano."
#
# O segundo sinal que faltava já existe no projeto: `asset_ranker.dhash`. Em
# marketplace a foto de FÁBRICA é reusada entre vendedores e entre lojas.
#
# ⚠️ E A VERIFICAÇÃO É NA GALERIA INTEIRA, não na foto principal. A primeira
# versão deste arquivo comparava só a principal, e a simulação derrubou na
# hora: o único caso aceito virava "a foto é idêntica à que já tenho" — que é
# exatamente a que NÃO acrescenta nada. Um coletor que só aceita foto repetida
# não coleta. Era o `faixa_preenchida` de novo, reprovando o caso bom.
#
# O mecanismo certo usa a mesma galeria pras duas coisas, por caminhos opostos:
#   IDENTIDADE   se QUALQUER foto do anúncio bate com a nossa, é o mesmo produto
#   DIVERSIDADE  as OUTRAS fotos são a informação nova
#
# OS DOIS SINAIS, E POR QUE PRECISA DOS DOIS
#   imagem  decisivo quando alguma bate; MUDO quando nenhuma bate — pode ser
#           outro produto, ou o mesmo fotografado por outro vendedor
#   nome    fraco por natureza (o próprio módulo diz), mas separa o absurdo
#
#   confirmado  alguma foto da galeria é a nossa   → usa as outras
#   provavel    nome forte, fotos inconclusivas    → usa com marca
#   duvidoso    só um sinal fraco                  → NÃO usa sem olho humano
#   recusado    nenhum                             → descarta
#
# ⚠️ `duvidoso` não vira `provavel` por falta de opção. Produzir com o produto
# errado é o único defeito desta esteira que custa a confiança do comprador, e
# ele não aparece em nenhuma checagem do render — o vídeo sai lindo.
#
# A POLÍTICA (`parecer`) É SEPARADA DA REDE, de propósito: é a parte que dá pra
# testar sem abrir navegador, e é onde mora a decisão. Mesma divisão do
# `texto_queimado.decidir`.
#
# Uso:
#   python3 fontes_assets.py --simular            # só a política, sem rede
#   python3 fontes_assets.py --produto "Mini Inflador CYCLAMI" \
#                            --foto shared/assets/x.jpg --saida /tmp/coleta

import argparse
import json
import sys
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ── limiares, herdados do asset_ranker pra falarem a mesma língua ───────────
# 0.14 é o "são a MESMA imagem pro olho" que o ranker já usa. Aqui ele vira
# "é a mesma foto de fábrica", que é o sinal forte de identidade.
D_MESMA_FOTO = 0.14
# entre 0.14 e 0.28 as imagens são parecidas mas não idênticas: pode ser o
# mesmo produto noutro ângulo, pode ser um concorrente parecido. Inconclusivo.
D_PARECIDA = 0.28
# quantas palavras úteis em comum pra chamar o nome de "forte". 2 é baixo de
# propósito: título de marketplace repete palavra-chave, então exigir muito
# rejeitaria acerto. Serve só pra separar do ruído.
NOME_FORTE = 3


def _log(m):
    print(f"[fontes] {m}", flush=True)


def _palavras(texto: str) -> set:
    """Palavras de 4+ letras, sem acento. Espelha _palavras_uteis do
    amazon_playwright — se as duas divergirem, o mesmo par termo/produto teria
    dois vereditos no mesmo sistema."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    import re
    vazias = {"para", "com", "sem", "dos", "das", "por", "que", "uma", "kit",
              "pcs", "unidades", "original", "promocao", "frete", "gratis",
              "envio", "imediato", "novo", "nova", "top", "mais", "vendido"}
    return {p for p in re.findall(r"[a-z]{4,}", t) if p not in vazias}


def _distancia(a: Path, b: Path):
    """Distância perceptual entre duas imagens. None se não der pra medir."""
    try:
        import asset_ranker as AR
        return AR.distancia(AR.dhash(a), AR.dhash(b))
    except Exception:
        return None


def parecer(nome_origem: str, foto_origem: Path, candidato: dict) -> dict:
    """É o MESMO produto? E quantas fotos NOVAS este anúncio traz?

    `candidato`: {"fonte", "titulo", "url", "galeria": [Path, ...]}

    ⚠️ A VERIFICAÇÃO É NA GALERIA INTEIRA, NÃO NA FOTO PRINCIPAL — e a primeira
    versão deste arquivo errava isso. Ela comparava só a imagem principal, e o
    resultado foi que o único caso aceito era "a foto é idêntica à que já
    tenho": justamente a que NÃO acrescenta nada. A simulação mostrou na hora —
    "nome forte, foto outra" saía `duvidoso`, e esse é o caso que o módulo
    existe pra aproveitar. Teste que reprova o caso bom é o erro do
    `faixa_preenchida` outra vez.

    O mecanismo certo: galeria de marketplace tem 5-8 fotos, e a de FÁBRICA
    costuma estar entre elas. Se QUALQUER uma bate com a nossa, o anúncio é do
    mesmo produto — e as OUTRAS são a informação nova. A prova de identidade e
    o ganho de diversidade vêm da mesma galeria, por caminhos opostos.

    Devolve sempre `motivo` legível: veredito de identidade que ninguém audita
    é veredito que ninguém contesta quando erra.
    """
    titulo = candidato.get("titulo") or ""
    comuns = _palavras(nome_origem) & _palavras(titulo)
    nome_forte = len(comuns) >= NOME_FORTE
    nome_algum = len(comuns) >= 1

    galeria = [Path(g) for g in (candidato.get("galeria") or [])]
    dists = []
    for g in galeria:
        d = _distancia(g, Path(foto_origem)) if foto_origem else None
        if d is not None:
            dists.append((d, g))
    d_min = min((d for d, _ in dists), default=None)
    # as que ACRESCENTAM: diferentes da que já temos
    novas = [g for d, g in dists if d > D_MESMA_FOTO]

    if d_min is not None and d_min <= D_MESMA_FOTO:
        v = "confirmado"
        motivo = (f"uma das {len(galeria)} fotos do anúncio é a MESMA da "
                  f"origem (distância {d_min:.3f}) — mesmo produto, e as "
                  f"outras {len(novas)} são informação nova")
    elif nome_forte and (d_min is None or d_min <= D_PARECIDA):
        v = "provavel"
        motivo = (f"{len(comuns)} palavras em comum "
                  f"({', '.join(sorted(comuns)[:5])})"
                  + (f", foto mais próxima a {d_min:.3f}" if d_min is not None
                     else ", sem foto pra comparar"))
    elif nome_algum or (d_min is not None and d_min <= D_PARECIDA):
        v = "duvidoso"
        motivo = (f"sinal fraco: {len(comuns)} palavra(s) em comum"
                  + (f", foto mais próxima a {d_min:.3f}" if d_min is not None
                     else "")
                  + " — pode ser outro produto parecido")
    else:
        v, motivo = "recusado", "nada em comum: nem título nem foto"

    return {"veredito": v, "motivo": motivo, "fonte": candidato.get("fonte"),
            "titulo": titulo[:90], "url": candidato.get("url", ""),
            "palavras_comuns": sorted(comuns), "distancia_min": d_min,
            "fotos_no_anuncio": len(galeria),
            "fotos_novas": [str(g) for g in novas]}


def usar_galeria(p: dict, aceitar_provavel: bool = True) -> bool:
    """A galeria deste candidato pode virar cena do vídeo?

    `duvidoso` NUNCA passa. É a única decisão desta esteira cujo erro o
    comprador paga, e nenhuma checagem do render pega: o vídeo sai perfeito
    mostrando a coisa errada.
    """
    if p["veredito"] == "confirmado":
        return True
    return bool(aceitar_provavel and p["veredito"] == "provavel")


# ── rede: buscar candidatos nas fontes ──────────────────────────────────────
# ⚠️ ESTA PARTE NÃO FOI TESTADA CONTRA AS LOJAS. Não tenho acesso a Amazon/ML
# no ambiente onde escrevo, então o que está verificado é a POLÍTICA acima. O
# `--simular` roda a política com casos montados; a coleta real só se prova na
# VPS, e o primeiro run deve ser com `--seco`.

def galeria_da_pagina(url: str, destino: Path, prefixo: str,
                      max_fotos: int = 8) -> list:
    """Abre a página do produto e baixa a galeria.

    ⚠️ NÃO VERIFICADO CONTRA A AMAZON. Não tenho acesso à loja no ambiente onde
    isto foi escrito, então o que está provado é a POLÍTICA (`parecer`), não
    esta extração. Rode `--seco` primeiro: ele busca, extrai e JULGA sem baixar
    galeria nenhuma, e aí dá pra ver se os seletores acham alguma coisa.

    Por que várias estratégias: a Amazon serve a galeria de formas diferentes
    conforme a categoria e o teste A/B do dia. Uma só quebra em silêncio e o
    módulo reporta "0 fotos" como se o anúncio não tivesse — que é
    indistinguível de "meu seletor está velho". Por isso cada tentativa loga.
    """
    fotos = []
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        _log(f"playwright indisponível: {str(e)[:60]}")
        return fotos

    import json as _json
    import re as _re
    with sync_playwright() as pw:
        nav = pw.chromium.launch(headless=True)
        pg = nav.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        try:
            pg.goto(url, timeout=45000, wait_until="domcontentloaded")
            html = pg.content()
        except Exception as e:
            _log(f"não abri a página: {str(e)[:70]}")
            nav.close()
            return fotos
        nav.close()

    urls, como = [], ""
    # 1) o blob que a própria página usa pro visualizador — o mais completo
    m = _re.search(r"'colorImages':\s*(\{.*?\}),\n", html, _re.S)
    if m:
        try:
            for it in _json.loads(m.group(1).replace("'", '"')).get("initial", []):
                for chave in ("hiRes", "large", "thumb"):
                    if it.get(chave):
                        urls.append(it[chave])
                        break
            como = "colorImages"
        except Exception:
            urls = []
    # 2) fallback: as URLs de imagem de produto no HTML cru
    if not urls:
        urls = _re.findall(r'https://m\.media-amazon\.com/images/I/[A-Za-z0-9%+._-]+\.jpg', html)
        como = "regex no HTML"
    # a mesma foto aparece em vários tamanhos; normaliza pro maior e deduplica
    vistas, limpas = set(), []
    for u in urls:
        base = _re.sub(r"\._[A-Z0-9_,]+_\.jpg$", ".jpg", u)
        if base not in vistas:
            vistas.add(base)
            limpas.append(base)

    _log(f"   galeria: {len(limpas)} url(s) distintas por '{como}'")
    for i, u in enumerate(limpas[:max_fotos], 1):
        alvo = destino / f"{prefixo}_{i}.jpg"
        if _baixar(u, alvo):
            fotos.append(alvo)
    return fotos


def candidatos_amazon(termo: str, destino: Path, seco: bool = False,
                      limite: int = 1) -> list:
    """Usa o amazon_playwright que já existe — inclusive o cache e as travas
    dele (teto por rodada, pausa longa, para em captcha). Reimplementar a busca
    seria criar um segundo caminho pra tomar bloqueio, e o módulo é conservador
    justamente porque a PA-API não está ao alcance."""
    try:
        import amazon_playwright as AP
    except Exception as e:
        _log(f"amazon_playwright indisponível: {str(e)[:70]}")
        return []
    if not AP.ligado():
        _log("AMAZON_PLAYWRIGHT=0 — Amazon desligada no .env")
        return []
    try:
        achados = AP.buscar([termo], limite=limite)
    except AttributeError:
        _log("amazon_playwright não expõe buscar() — versão diferente na VPS")
        return []
    except Exception as e:
        _log(f"busca Amazon falhou: {str(e)[:80]}")
        return []

    fora = []
    for r in (achados or []):
        recusa = AP.recusar(termo, r)
        if recusa:
            _log(f"   Amazon recusou por nome/preço: {recusa}")
            continue
        link = r.get("link") or AP.link_de_produto(r.get("asin", ""))
        galeria = []
        if link and not seco:
            galeria = galeria_da_pagina(link, destino, "amazon")
        elif seco:
            _log("   (--seco: não abri a página do produto)")
        fora.append({"fonte": "amazon", "titulo": r.get("titulo", ""),
                     "url": link, "galeria": galeria,
                     "asin": r.get("asin", "")})
    return fora


def _baixar(url: str, destino: Path) -> bool:
    try:
        import requests
        destino.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(url, timeout=45, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200 or len(r.content) < 2048:
            return False
        destino.write_bytes(r.content)
        return True
    except Exception:
        return False


def coletar(nome: str, foto_origem: Path, destino: Path,
            aceitar_provavel: bool = True, seco: bool = False) -> dict:
    """Procura o mesmo produto em outras fontes e traz o que for confirmado."""
    destino.mkdir(parents=True, exist_ok=True)
    pareceres, aceitos = [], []

    for cand in candidatos_amazon(nome, destino, seco=seco):
        p = parecer(nome, foto_origem, cand)
        pareceres.append(p)
        icone = {"confirmado": "✅", "provavel": "👍",
                 "duvidoso": "❓", "recusado": "✗"}[p["veredito"]]
        _log(f" {icone} [{p['fonte']}] {p['veredito']}: {p['motivo'][:88]}")
        if usar_galeria(p, aceitar_provavel) and p["fotos_novas"]:
            aceitos.extend(p["fotos_novas"])

    return {"produto": nome, "pareceres": pareceres,
            "fotos_novas": aceitos, "destino": str(destino), "seco": seco}


# ── simulação: a política, sem rede ─────────────────────────────────────────
def _simular():
    """A política, com galerias inteiras. Cada caso traz as distâncias de TODAS
    as fotos do anúncio até a foto que já temos."""
    casos = [
        ("galeria com a nossa foto", "Mini Inflador Elétrico CYCLAMI 130 PSI",
         "Mini Inflador de Pneu Elétrico Portátil CYCLAMI 130PSI",
         [0.05, 0.31, 0.38, 0.44, 0.29]),
        ("mesmo produto, fotos todas outras", "Mini Inflador Elétrico CYCLAMI 130 PSI",
         "Inflador Elétrico Portátil CYCLAMI 130 PSI Recarregável",
         [0.33, 0.36, 0.41]),
        ("nome forte, fotos próximas", "Escova Alisadora Elétrica EARNEST",
         "Escova Alisadora Elétrica EARNEST Cerâmica Bivolt",
         [0.21, 0.26, 0.30]),
        ("concorrente parecido", "Mini Inflador Elétrico CYCLAMI 130 PSI",
         "Compressor de Ar Portátil Automotivo Xiaomi", [0.27, 0.35]),
        ("nada a ver", "Kit 10 Calcinhas Tanga Sem Costura",
         "Fone de Ouvido Bluetooth TWS", [0.58, 0.62]),
        ("sem galeria pra comparar", "Garrafa Squeeze com Infusor 700ml",
         "Garrafa Squeeze Infusor Frutas 700ml Academia", []),
    ]
    print(f"\n  {'caso':34} {'veredito':12} {'usa?':5} {'fotos novas':11} motivo")
    print("  " + "─" * 116)
    for nome_caso, origem, titulo, dists in casos:
        # injeta as distâncias na ordem em que a galeria é percorrida
        fila = list(dists)
        globals()["_distancia"] = lambda a, b: fila.pop(0) if fila else None
        cand = {"fonte": "amazon", "titulo": titulo,
                "galeria": [Path(f"g{i}.jpg") for i in range(len(dists))]}
        p = parecer(origem, Path("nossa.jpg"), cand)
        usa = "SIM" if usar_galeria(p) else "não"
        print(f"  {nome_caso:34} {p['veredito']:12} {usa:5} "
              f"{len(p['fotos_novas']):^11} {p['motivo'][:52]}")
    print()


def main():
    p = argparse.ArgumentParser(
        description="Mesma peça em outras fontes, com prova de identidade.")
    p.add_argument("--produto")
    p.add_argument("--foto", help="a foto que já temos (referência de identidade)")
    p.add_argument("--saida", default="/tmp/coleta_fontes")
    p.add_argument("--simular", action="store_true",
                   help="roda só a política de identidade, sem rede")
    p.add_argument("--seco", action="store_true",
                   help="busca e julga, mas não baixa galeria")
    p.add_argument("--so-confirmado", action="store_true",
                   help="recusa até os 'provavel' — só foto de fábrica igual")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    if args.simular:
        _simular()
        return 0
    if not (args.produto and args.foto):
        p.error("use --simular, ou --produto NOME --foto CAMINHO")

    r = coletar(args.produto, Path(args.foto), Path(args.saida),
                aceitar_provavel=not args.so_confirmado, seco=args.seco)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    else:
        print()
        _log(f"{len(r['fotos_novas'])} foto(s) NOVA(s) aceita(s) · {r['destino']}")
        if not r["pareceres"]:
            _log("nenhum candidato — a busca não devolveu nada utilizável")
    return 0


if __name__ == "__main__":
    sys.exit(main())
