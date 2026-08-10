#!/usr/bin/env python3
# coletor_assets.py -- MAIS DE UMA IMAGEM por produto, com navegador de verdade.
#
# POR QUE EXISTE, E POR QUE SÓ AGORA (10/08)
# O Dre apontou duas vezes: "só tem uma imagem durante todo o vídeo". Eu quis
# construir um coletor na hora; em vez disso perguntamos primeiro, e as duas
# respostas vieram medidas:
#
#   API de afiliado (productOfferV2)   11 campos de galeria testados, 0 existem
#   API interna da loja (v4/item/get)  HTTP 403, do meu ambiente E da VPS
#
# Só então este arquivo se justificou. **Construir antes teria sido construir
# em cima de palpite meu** — e o palpite ("não dá pra resolver") estava errado.
#
# A IDEIA CENTRAL: NÃO RASPAR A PÁGINA, ESCUTAR O QUE ELA PEDE
# A página de produto busca os próprios dados por XHR. Dentro do navegador
# essas chamadas respondem 200, porque vão com cookie, cabeçalho e impressão
# digital que o site espera — a mesma rota que dá 403 na requisição crua.
#
# ⚠️ E NÃO SE ESPERA UMA ROTA ESPECÍFICA. A 1ª versão escutava só
# `/api/v4/item/get` e na VPS voltou "a página abriu mas a chamada não veio" —
# sem dizer se o site mudou de rota, se renderizou no servidor, ou se era
# bloqueio. Amarrar-se a um nome de rota é o mesmo erro de amarrar-se a um
# seletor de DOM: quebra no primeiro redesenho e o diagnóstico vira adivinhação.
#
# Agora: captura-se TODA resposta JSON e procura-se, em qualquer profundidade,
# uma lista que se pareça com galeria (hashes de imagem da Shopee). Se o site
# renderizar no servidor, o `--diagnostico` mostra o que ele realmente fez, com
# print e a lista de chamadas — em vez de eu chutar de novo.
#
# ⚠️ SÓ LÊ. Não posta, não compra, não mexe na fila (a não ser com --gravar).
# ⚠️ UM produto por vez, com pausa. Isto não é um raspador em massa.
#
# Uso:
#   python3 coletor_assets.py --fila 0
#   python3 coletor_assets.py --fila 0 --baixar shared/assets/
#   python3 coletor_assets.py --fila 0 --gravar        (escreve `imagens` na fila)
#   COLETOR_ASSETS=0 desliga tudo.

import argparse
import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CDN = "https://cf.shopee.com.br/file/"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _log(m):
    print(f"[assets] {m}", flush=True)


def _ligado() -> bool:
    return os.getenv("COLETOR_ASSETS", "1").strip().lower() not in ("0", "false", "nao", "não")


def _carregar_env():
    for cand in (BASE_DIR / ".env", Path(".env")):
        if not cand.exists():
            continue
        for linha in cand.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            k, _, v = linha.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        break


def _ids(link: str):
    """(shop_id, item_id) de um link, curto ou longo. Reusa quem já resolvia."""
    try:
        from preencher_fotos import _ids_do_link
        return _ids_do_link(link)
    except Exception as e:
        _log(f"não resolvi o link: {str(e)[:80]}")
        return None, None


_HASH = re.compile(r"^[a-z0-9]{2}-[a-z0-9]{8,}-[a-z0-9]{4,}-[a-z0-9]{4,}$", re.I)


def _parece_hash(v) -> bool:
    """O hash de imagem da Shopee tem cara própria: br-11134207-7r98o-abc123.

    Reconhecer pelo FORMATO, e não pelo nome do campo, é o que deixa a busca
    funcionar mesmo quando o site troca `images` por outro nome.
    """
    return isinstance(v, str) and (_HASH.match(v) or
                                   (32 <= len(v) <= 48 and v.isalnum()))


def procurar_galeria(obj, achados=None, profundidade=0):
    """Vasculha um JSON qualquer atrás de listas de hash de imagem.

    Devolve a MAIOR lista encontrada. Route-agnostic de propósito: não importa
    se a rota se chama item/get, pdp/get_pc ou o que a Shopee inventar amanhã —
    o que se procura é o FORMATO do dado.
    """
    achados = [] if achados is None else achados
    if profundidade > 8:
        return achados
    if isinstance(obj, dict):
        for v in obj.values():
            procurar_galeria(v, achados, profundidade + 1)
    elif isinstance(obj, list):
        hashes = [x for x in obj if _parece_hash(x)]
        if len(hashes) >= 2:
            achados.append(hashes)
        for v in obj:
            if isinstance(v, (dict, list)):
                procurar_galeria(v, achados, profundidade + 1)
    return achados


def extrair(payload: dict) -> dict:
    """Payload da v4/item/get -> {imagens, videos, titulo}.

    SEPARADO da parte do navegador de propósito: é aqui que mora o risco real
    (nome de campo errado, formato de vídeo diferente), e é a única parte que
    dá pra testar sem alcançar a loja. O ambiente onde escrevi isto não chega
    na Shopee — então o que eu pude provar, provei; o resto está dito.

    `images` é lista de HASH, não de URL: o site monta a URL com o prefixo do
    CDN. Guardar hash cru na fila daria 404 na hora de baixar.
    """
    dados = (payload or {}).get("data") or {}
    if not dados:
        # sem `data` ainda pode haver galeria em outro lugar do JSON — quem
        # decide é o formato do dado, não o nome do campo
        listas = procurar_galeria(payload)
        if not listas:
            return {"ok": False, "imagens": [], "videos": [], "titulo": "",
                    "erro": "payload sem `data` e sem lista de hash"}
        maior = max(listas, key=len)
        return {"ok": True, "titulo": "", "videos": [], "erro": None,
                "imagens": [h if h.startswith("http") else f"{CDN}{h}"
                            for h in maior]}

    imgs = []
    for h in (dados.get("images") or []):
        if not h:
            continue
        imgs.append(h if str(h).startswith("http") else f"{CDN}{h}")
    if not imgs:
        listas = procurar_galeria(dados)
        if listas:
            imgs = [h if h.startswith("http") else f"{CDN}{h}"
                    for h in max(listas, key=len)]

    videos = []
    for v in (dados.get("video_info_list") or []):
        # o formato varia: às vezes `default_format.url`, às vezes `url`,
        # às vezes só `video_id` (aí não dá pra montar link direto)
        u = ((v.get("default_format") or {}).get("url")
             or v.get("url") or "")
        if u:
            videos.append(u)
    return {"ok": True, "imagens": imgs, "videos": videos,
            "titulo": dados.get("name") or "", "erro": None}


def coletar(shop_id: str, item_id: str, espera_ms: int = 5000,
            diagnostico: Path = None) -> dict:
    """Abre a página do produto e escuta a resposta da API que ela mesma chama.

    Retorna {"ok", "imagens": [url], "videos": [url], "titulo", "erro"}.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return {"ok": False, "erro": "playwright não instalado "
                                     "(pip install playwright)"}

    url = f"https://shopee.com.br/product/{shop_id}/{item_id}"
    capturado = {}

    with sync_playwright() as pw:
        exe = (os.environ.get("PLAYWRIGHT_CHROMIUM") or "").strip() or None
        navegador = pw.chromium.launch(
            headless=True, executable_path=exe,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-dev-shm-usage"])
        ctx = navegador.new_context(
            user_agent=_UA, locale="pt-BR", timezone_id="America/Sao_Paulo",
            viewport={"width": 1366, "height": 900})
        pagina = ctx.new_page()

        vistas = []

        def ouvir(resp):
            u = resp.url
            if "/api/" not in u:
                return
            vistas.append(f"{resp.status} {u.split('?')[0]}")
            try:
                j = resp.json()
            except Exception:
                return
            listas = procurar_galeria(j)
            if listas:
                atual = capturado.get("melhor") or []
                maior = max(listas, key=len)
                if len(maior) > len(atual):
                    capturado["melhor"] = maior
                    capturado["dados"] = j
                    capturado["rota"] = u.split("?")[0]

        pagina.on("response", ouvir)
        titulo, html = "", ""
        try:
            pagina.goto(url, wait_until="domcontentloaded", timeout=60000)
            pagina.wait_for_timeout(espera_ms)
            # rolar acorda XHR que só dispara quando a galeria entra em tela
            try:
                pagina.mouse.wheel(0, 1200)
                pagina.wait_for_timeout(2500)
            except Exception:
                pass
            titulo = (pagina.title() or "").split("|")[0].strip()
            html = pagina.content()
            if diagnostico:
                pagina.screenshot(path=str(diagnostico), full_page=False)
        except Exception as e:
            ctx.close(); navegador.close()
            return {"ok": False, "erro": f"não abri a página: {str(e)[:110]}",
                    "chamadas": vistas}
        ctx.close()
        navegador.close()

    if capturado.get("melhor"):
        r = extrair(capturado["dados"])
        r["titulo"] = r.get("titulo") or titulo
        r["rota"] = capturado.get("rota", "")
        r["chamadas"] = vistas
        return r

    # ÚLTIMA TENTATIVA: a página pode ter vindo pronta do servidor, com o JSON
    # embutido num <script>. Procura-se o mesmo FORMATO de hash direto no HTML.
    achados = re.findall(r'"([a-z]{2}-[a-z0-9]{6,}-[a-z0-9]{4,}-[a-z0-9]{4,})"',
                         html or "", re.I)
    unicos = list(dict.fromkeys(achados))
    if len(unicos) >= 2:
        return {"ok": True, "titulo": titulo, "videos": [], "erro": None,
                "rota": "HTML embutido", "chamadas": vistas,
                "imagens": [f"{CDN}{h}" for h in unicos[:12]]}

    return {"ok": False, "titulo": titulo, "chamadas": vistas,
            "erro": ("nenhuma chamada trouxe galeria e o HTML não tem hash de "
                     f"imagem (título da página: {titulo[:50]!r})")}


def _baixar(urls: list, destino: Path, prefixo: str) -> list:
    import requests
    destino.mkdir(parents=True, exist_ok=True)
    fora = []
    for i, u in enumerate(urls, 1):
        alvo = destino / f"{prefixo}_{i:02d}.jpg"
        try:
            r = requests.get(u, timeout=45, headers={"User-Agent": _UA})
            if r.status_code == 200 and len(r.content) > 2048:
                alvo.write_bytes(r.content)
                fora.append(alvo)
            else:
                _log(f"   ✗ imagem {i}: HTTP {r.status_code}")
        except Exception as e:
            _log(f"   ✗ imagem {i}: {str(e)[:70]}")
    return fora


def main():
    p = argparse.ArgumentParser(
        description="Coleta as imagens do produto com navegador real.")
    p.add_argument("--fila", type=int, help="índice em produtos_fila.json")
    p.add_argument("--link", help="link do produto (curto ou longo)")
    p.add_argument("--item", help="itemId (com --shop)")
    p.add_argument("--shop", help="shopId (com --item)")
    p.add_argument("--baixar", help="pasta pra salvar as imagens")
    p.add_argument("--gravar", action="store_true",
                   help="escreve a lista em `imagens` no item da fila")
    p.add_argument("--espera", type=int, default=5000,
                   help="ms esperando a página chamar a API (padrão 5000)")
    p.add_argument("--diagnostico", action="store_true",
                   help="salva print da página e lista TODAS as chamadas /api/ "
                        "— pra ver o que o site fez, em vez de adivinhar")
    args = p.parse_args()

    _carregar_env()
    if not _ligado():
        _log("COLETOR_ASSETS=0 — desligado, nada a fazer")
        return 0

    fila_arq, fila, item = None, None, None
    if args.fila is not None:
        for cand in (BASE_DIR / "shared" / "produtos_fila.json",
                     Path("shared/produtos_fila.json")):
            if cand.exists():
                fila_arq = cand
                break
        if not fila_arq:
            raise SystemExit("[assets] não achei a produtos_fila.json")
        fila = json.loads(fila_arq.read_text(encoding="utf-8"))
        validos = [x for x in fila if isinstance(x, dict)]
        if not (0 <= args.fila < len(validos)):
            raise SystemExit(f"[assets] índice fora da fila (há {len(validos)})")
        item = validos[args.fila]

    shop_id, item_id = args.shop, args.item
    if not (shop_id and item_id):
        link = args.link or (item or {}).get("link") or ""
        if not link:
            p.error("use --fila N, --link URL, ou --item + --shop")
        shop_id, item_id = _ids(link)
        if not item_id:
            raise SystemExit(f"[assets] não extraí os IDs de {link[:70]!r}")
        _log(f"link resolvido → shop {shop_id} · item {item_id}")

    tiro = (BASE_DIR / "shared" / "assets" / f"diag_{item_id}.png"
            if args.diagnostico else None)
    if tiro:
        tiro.parent.mkdir(parents=True, exist_ok=True)
    r = coletar(str(shop_id), str(item_id), args.espera, tiro)

    if args.diagnostico:
        chamadas = r.get("chamadas") or []
        _log(f"🔎 {len(chamadas)} chamada(s) /api/ vistas:")
        for c in chamadas[:25]:
            print(f"      {c}")
        if tiro and tiro.exists():
            _log(f"   🖼️  print da página em {tiro}")

    if not r.get("ok"):
        _log(f"❌ {r.get('erro')}")
        _log("   se for bloqueio, o caminho vira: galeria da Amazon/ML pro "
             "mesmo produto, ou banco próprio de assets")
        return 1

    _log(f"✅ {r.get('titulo', '')[:60]}")
    _log(f"   {len(r['imagens'])} imagem(ns) · {len(r.get('videos') or [])} "
         f"vídeo(s) · via {r.get('rota', '?')}")
    for u in r["imagens"][:8]:
        print(f"      {u}")
    if r["videos"]:
        _log("   ⚠️  TEM VÍDEO DO PRODUTO — material melhor que foto parada")
        for u in r["videos"][:3]:
            print(f"      {u}")

    if args.baixar:
        pasta = Path(args.baixar) / f"{shop_id}_{item_id}"
        arqs = _baixar(r["imagens"], pasta, "img")
        _log(f"   💾 {len(arqs)} arquivo(s) em {pasta}")

    if args.gravar and item is not None and fila_arq is not None:
        # grava só a LISTA de URLs; quem baixa é o piloto, na hora de produzir.
        # E preserva o resto do item: a fila é dado vivo, não arquivo meu.
        item["imagens"] = r["imagens"]
        if r["videos"]:
            item["videos"] = r["videos"]
        fila_arq.write_text(json.dumps(fila, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        _log(f"   📝 `imagens` gravado no item {args.fila} da fila")
        _log("      o piloto já sabe usar `imagens` — rode "
             f"`piloto.py --fila {args.fila}`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
