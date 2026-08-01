#!/usr/bin/env python3
# deploy_site.py
# Regenera o index.html (VITRINE dos produtos POSTADOS) e sobe pro repositório
# do GitHub Pages (z-scriptz/Topshop-Site), que serve o topshopoficial.com.br.
#
# Fecha o funil de dinheiro: o Jarvis posta -> produtos_fila.json -> este script
# regenera o site com o produto (e o link de afiliado) -> a bio mostra o mesmo
# produto do vídeo.
#
# BLINDAGEM DE LINK (health-check): antes de publicar, confere na API oficial de
# afiliado se cada produto ainda existe. Produto CONFIRMADO fora do ar (delistado)
# é escondido da vitrine — assim o viewer nunca clica num link morto e a comissão
# não vaza. Na dúvida (erro/rede/sem credencial) MANTÉM o produto (nunca zera a
# vitrine por um problema de infra).
#
# Uso (no VPS):  python3 deploy_site.py
# Pré-requisito: um CLONE do Topshop-Site em ~/topshop-site (ou env
#                TOPSHOP_SITE_DIR), com push configurado (token/credencial).
#                O daemon (ou um cron) chama este script de tempos em tempos.

import os
import re
import sys
import json
import time
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SITE_REPO = Path(os.environ.get("TOPSHOP_SITE_DIR", str(Path.home() / "topshop-site")))
HEALTH_CACHE = BASE_DIR / "shared" / "health_cache.json"
HEALTH_TTL = 6 * 3600   # re-checa cada produto no máx. 1x a cada 6h
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"


def _log(m):
    print(f"[deploy_site] {m}")


def _carregar_env():
    """Cron/execução manual não carrega o .env sozinho — a API de afiliado
    precisa de SHOPEE_APP_ID/SECRET. Carrega o .env do ~/jarvis aqui, sem
    sobrescrever o que já estiver no ambiente."""
    for cand in (BASE_DIR / ".env", Path(".env")):
        if not cand.exists():
            continue
        for linha in cand.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            chave, _, valor = linha.partition("=")
            chave = chave.strip()
            valor = valor.strip().strip('"').strip("'")
            if chave and chave not in os.environ:
                os.environ[chave] = valor
        break


def _carregar_builder():
    try:
        from creative_engine import bio_page_builder as B   # layout do VPS
        return B
    except Exception:
        import bio_page_builder as B                          # repo flat
        return B


def _obter_dados_produto():
    """Função da API oficial de afiliado (ou None se indisponível)."""
    try:
        from integrations.shopee_affiliate import obter_dados_produto
        return obter_dados_produto
    except Exception:
        try:
            from shopee_affiliate import obter_dados_produto
            return obter_dados_produto
        except Exception:
            return None


def _historico():
    """Módulo de histórico de preços (ou None). Nunca é obrigatório: sem ele o
    deploy roda igual, só sem preço na vitrine."""
    try:
        import historico_precos as H                         # vizinho deste arquivo
        return H
    except Exception:
        try:
            from creative_engine import historico_precos as H
            return H
        except Exception:
            _log("historico_precos indisponível — vitrine sai sem preço")
            return None


# ── Health-check dos links ────────────────────────────────────────────────
def _ids_do_link(link: str):
    """Segue o link de afiliado até a página do produto e extrai (shop_id, item_id)."""
    import requests
    r = requests.get(link, allow_redirects=True, timeout=15,
                     headers={"User-Agent": _UA})
    final = r.url or ""
    m = re.search(r"i\.(\d+)\.(\d+)", final)              # formato ...-i.shop.item
    if m:
        return m.group(1), m.group(2)
    pares = re.findall(r"/(\d+)/(\d+)", final.split("?")[0])   # .../shop/item
    return pares[-1] if pares else (None, None)


def _checar_online(link, obter, nome="", H=None, hist=None):
    """'vivo' | 'morto' | 'incerto'. Só devolve 'morto' quando a API CONFIRMA
    que o produto não existe mais (delistado).

    De quebra guarda o preço que veio na resposta: essa chamada já acontecia
    de qualquer jeito, então o histórico sai de graça, sem nenhuma requisição
    nova. Falha ao anotar nunca derruba o health-check."""
    try:
        shop_id, item_id = _ids_do_link(link)
        if not item_id:
            return "incerto"
        d = obter(str(item_id), shop_id=int(shop_id))
        if d.get("ok"):
            if H is not None and hist is not None:
                try:
                    H.registrar(link, d.get("preco"),
                                nome=d.get("titulo") or nome, dados=hist)
                except Exception as e:
                    _log(f"   (preço não anotado: {str(e)[:60]})")
            return "vivo"
        erro = str(d.get("erro", "")).lower()
        if "não encontrado" in erro or "nao encontrado" in erro or "not found" in erro:
            return "morto"
        return "incerto"     # cred/rede/rate-limit → não arrisca dropar
    except Exception:
        return "incerto"
    finally:
        time.sleep(0.8)      # gentil com a API


def _load_cache():
    try:
        return json.loads(HEALTH_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache):
    try:
        HEALTH_CACHE.parent.mkdir(parents=True, exist_ok=True)
        HEALTH_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    except Exception:
        pass


def _filtrar_vivos(produtos):
    """Esconde só os produtos CONFIRMADOS fora do ar. Usa cache com TTL pra não
    martelar a API a cada rodada do cron. Degrada com segurança: sem API/credencial
    ou se a checagem zeraria a vitrine, mantém tudo."""
    obter = _obter_dados_produto()
    if obter is None:
        _log("API de afiliado indisponível — pulo o health-check (mantém tudo)")
        return produtos

    H = _historico()
    hist = H.carregar() if H else None

    cache = _load_cache()
    agora = int(time.time())
    vivos, mortos, checados = [], 0, 0
    for p in produtos:
        link = p.get("link", "")
        ent = cache.get(link)
        if ent and (agora - ent.get("ts", 0)) < HEALTH_TTL:
            estado = ent.get("estado", "incerto")
        else:
            estado = _checar_online(link, obter, nome=p.get("nome", ""),
                                    H=H, hist=hist)
            checados += 1
            if estado in ("vivo", "morto"):     # só cacheia resultado confiável
                cache[link] = {"estado": estado, "ts": agora}
        if estado == "morto":
            mortos += 1
            _log(f"   💀 fora do ar, escondido: {p.get('nome', '?')[:45]}")
        else:
            vivos.append(p)

    _save_cache(cache)
    if checados:
        _log(f"health-check: {checados} verificados · {mortos} fora do ar")

    # histórico: poda pela vitrine ATUAL (não pelos vivos) — produto escondido
    # por estar fora do ar pode voltar, e aí o histórico dele ainda está lá
    if H and hist is not None:
        try:
            H.podar(links_vivos=[p.get("link", "") for p in produtos], dados=hist)
            H.salvar(hist)
            leituras = sum(len(v.get("leituras") or {}) for v in hist.values())
            _log(f"preços: {len(hist)} produtos · {leituras} leituras no histórico")
        except Exception as e:
            _log(f"histórico de preços não salvo: {str(e)[:80]}")

    # rede de segurança: nunca deixa a vitrine vazia por causa do check
    if produtos and not vivos:
        _log("health-check esconderia TUDO — ignorando (mantém vitrine atual)")
        return produtos
    return vivos


def _git(*args):
    return subprocess.run(["git", "-C", str(SITE_REPO), *args],
                          capture_output=True, text=True)


def main():
    if not (SITE_REPO / ".git").exists():
        _log(f"ERRO: {SITE_REPO} não é um repo git. Clone o Topshop-Site lá antes.")
        _log("Ex: git clone https://github.com/z-scriptz/Topshop-Site.git ~/topshop-site")
        return 2

    _carregar_env()
    B = _carregar_builder()

    produtos = B._carregar_produtos()
    # só o que TEM link (= produtos realmente postados)
    produtos = [p for p in produtos if p.get("link")]
    if not produtos:
        _log("nenhum produto com link — nada a publicar")
        return 1
    _log(f"{len(produtos)} produtos com link na vitrine")

    # blindagem: esconde os que morreram (delistados)
    produtos = _filtrar_vivos(produtos)
    if not produtos:
        _log("nenhum produto ativo — nada a publicar")
        return 1

    # cola média/queda/data em cada produto (campo `preco_resumo`)
    H = _historico()
    if H:
        try:
            H.enriquecer(produtos)
            com_preco = sum(1 for p in produtos if p.get("preco_resumo"))
            com_media = sum(1 for p in produtos
                            if (p.get("preco_resumo") or {}).get("media"))
            _log(f"preço: {com_preco}/{len(produtos)} com valor · "
                 f"{com_media} já com média de verdade")
        except Exception as e:
            _log(f"não consegui enriquecer preços: {str(e)[:80]}")

    html = B.gerar_site(produtos)
    idx = SITE_REPO / "index.html"

    if idx.exists() and idx.read_text(encoding="utf-8") == html:
        _log("site sem mudança — não precisa subir")
        return 0
    idx.write_text(html, encoding="utf-8")

    _git("add", "index.html")
    c = _git("commit", "-m", f"vitrine: {len(produtos)} produtos (auto)")
    if c.returncode not in (0, 1):   # 1 = nada pra commitar (ok)
        _log("commit falhou: " + (c.stderr or c.stdout)[:200])
        return 1
    p = _git("push")
    if p.returncode != 0:
        _log("push falhou: " + (p.stderr or p.stdout)[:200])
        return 1
    _log(f"OK! Site publicado com {len(produtos)} produtos -> topshopoficial.com.br")
    return 0


if __name__ == "__main__":
    sys.exit(main())
