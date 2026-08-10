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
# A própria página de produto chama a `v4/item/get` — a mesma que responde 403
# pra requisição crua. Dentro do navegador ela responde 200, porque vai com os
# cookies, o cabeçalho e a impressão digital que o site espera. Então aqui não
# se lê HTML nem se procura seletor: abre-se a página e ESCUTA-SE a resposta
# daquela chamada. É mais robusto que raspar DOM (que quebra a cada redesenho)
# e é a mesma informação que o site usa pra montar a galeria.
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
        return {"ok": False, "imagens": [], "videos": [], "titulo": "",
                "erro": "payload sem `data`"}

    imgs = []
    for h in (dados.get("images") or []):
        if not h:
            continue
        imgs.append(h if str(h).startswith("http") else f"{CDN}{h}")

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


def coletar(shop_id: str, item_id: str, espera_ms: int = 5000) -> dict:
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

        def ouvir(resp):
            # a página chama /api/v4/item/get pra montar a própria galeria;
            # é a MESMA rota que dá 403 na requisição crua
            if "/api/v4/item/get" in resp.url and "dados" not in capturado:
                try:
                    capturado["dados"] = resp.json()
                except Exception:
                    pass

        pagina.on("response", ouvir)
        try:
            pagina.goto(url, wait_until="domcontentloaded", timeout=60000)
            pagina.wait_for_timeout(espera_ms)
        except Exception as e:
            ctx.close(); navegador.close()
            return {"ok": False, "erro": f"não abri a página: {str(e)[:110]}"}
        titulo = ""
        try:
            titulo = (pagina.title() or "").split("|")[0].strip()
        except Exception:
            pass
        ctx.close()
        navegador.close()

    if not (capturado.get("dados") or {}).get("data"):
        return {"ok": False, "titulo": titulo,
                "erro": "a página abriu mas a chamada da galeria não veio "
                        "(bloqueio, ou o site mudou a rota)"}
    r = extrair(capturado["dados"])
    r["titulo"] = r.get("titulo") or titulo
    return r


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

    r = coletar(str(shop_id), str(item_id), args.espera)
    if not r.get("ok"):
        _log(f"❌ {r.get('erro')}")
        _log("   se for bloqueio, o caminho vira: galeria da Amazon/ML pro "
             "mesmo produto, ou banco próprio de assets")
        return 1

    _log(f"✅ {r.get('titulo', '')[:60]}")
    _log(f"   {len(r['imagens'])} imagem(ns) · {len(r['videos'])} vídeo(s)")
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
