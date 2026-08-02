#!/usr/bin/env python3
# amazon_playwright.py -- pega produto REAL da Amazon (ASIN, título, preço,
# foto) a partir do termo do vídeo, pra vitrine deixar de ter link de busca.
#
# POR QUE ISSO EXISTE: o fallback da Amazon monta amazon.com.br/s?k=termo, que
# é uma BUSCA, não um produto. Não tem foto, preço nem título pra mostrar, e o
# card fica vazio. Com o ASIN a gente monta /dp/ASIN?tag= e a vitrine fica
# igual à da Shopee.
#
# O caminho oficial seria a PA-API, mas ela exige 10 vendas qualificadas nos
# últimos 30 dias — fora de alcance por ora. Esta é a escolha consciente de
# usar navegador enquanto isso, e por isso o módulo é conservador de propósito:
#
#   - VOLUME BAIXO: teto por rodada (padrão 5), pausa longa entre buscas
#   - CACHE PERMANENTE: termo já resolvido nunca é buscado de novo
#   - PARA NA HORA: viu captcha ou bloqueio, encerra a rodada inteira e avisa
#   - UMA PÁGINA POR PRODUTO: os dados saem da própria busca, sem abrir o
#     produto depois
#   - DESLIGÁVEL: AMAZON_PLAYWRIGHT=0 no .env desliga tudo
#
# Uso (no VPS):
#     python3 amazon_playwright.py --diag --termo "escova secadora"   # só olha
#     python3 amazon_playwright.py --simular       # mostra o que faria na fila
#     python3 amazon_playwright.py --limite 5      # resolve 5 e para

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
FILA = BASE_DIR / "shared" / "produtos_fila.json"
CACHE = BASE_DIR / "shared" / "amazon_cache.json"

LIMITE_PADRAO = 5
PAUSA_MIN, PAUSA_MAX = 9.0, 18.0     # segundos entre buscas
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR','pt','en-US']});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
window.chrome = { runtime: {} };
"""

# O que roda dentro da página. Fica em JS porque precisa do DOM montado.
# Vários seletores por campo de propósito: a Amazon troca marcação sem aviso, e
# é melhor cair pro seletor seguinte do que voltar de mãos vazias.
_EXTRAIR_JS = r"""
() => {
  const bloqueado = !!document.querySelector('form[action*="validateCaptcha"]')
    || /Digite os caracteres|Enter the characters|Sorry, we just need/i
       .test(document.body.innerText.slice(0, 800));
  if (bloqueado) return {bloqueado: true};

  const cartoes = [...document.querySelectorAll('[data-component-type="s-search-result"]')];
  const achados = [];
  const marcadores = {sspa: 0, rotulo: 0, tipo: 0, texto: 0};
  for (const c of cartoes) {
    const asin = c.getAttribute('data-asin');
    if (!asin || asin.length < 8) continue;

    // Patrocinado é anúncio: pula. Nem sempre é o produto do vídeo, e a
    // primeira posição orgânica costuma casar melhor com o termo.
    //
    // O sinal PRINCIPAL é o link passar por /sspa/click: todo anúncio da
    // Amazon é rastreado por essa rota, e ela quase não muda. Rótulo de texto
    // e nome de classe mudam sem aviso — na 1ª rodada em produção eles deram
    // 0 patrocinados em 48 resultados, o que não existe numa busca popular.
    const sspa = !!c.querySelector('a[href*="/sspa/click"]');
    const rotulo = !!c.querySelector('.puis-sponsored-label-text, .s-sponsored-label-text, [aria-label*="Patrocinad"], [aria-label*="Sponsored"]');
    const tipo = !!c.querySelector('[data-component-type="sp-sponsored-result"]');
    const texto = /Patrocinad|Sponsored/i.test(c.innerText.slice(0, 300));
    if (sspa) marcadores.sspa++;
    if (rotulo) marcadores.rotulo++;
    if (tipo) marcadores.tipo++;
    if (texto) marcadores.texto++;
    const patrocinado = sspa || rotulo || tipo || texto;

    const el = s => c.querySelector(s);
    const titulo = (el('h2 a span') || el('h2 span') || el('[data-cy="title-recipe"] span') || {}).innerText || '';
    const precoTxt = (el('.a-price > .a-offscreen') || el('.a-price .a-offscreen') || {}).textContent || '';
    const img = el('img.s-image');
    achados.push({
      asin, patrocinado,
      titulo: titulo.trim(),
      precoTxt: precoTxt.trim(),
      imagem: img ? (img.getAttribute('src') || '') : '',
    });
  }
  return {bloqueado: false, total: cartoes.length, achados, marcadores};
}
"""


def _log(m):
    print(f"[amazon] {m}")


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
            chave, _, valor = linha.partition("=")
            chave, valor = chave.strip(), valor.strip().strip('"').strip("'")
            if chave and chave not in os.environ:
                os.environ[chave] = valor
        break


def ligado() -> bool:
    return (os.getenv("AMAZON_PLAYWRIGHT", "1").strip().lower()
            in ("1", "true", "sim"))


def _tag() -> str:
    return (os.getenv("AMAZON_TAG", "") or "").strip()


def _dominio() -> str:
    return (os.getenv("AMAZON_DOMAIN", "amazon.com.br") or "amazon.com.br").strip()


def link_de_produto(asin: str) -> str:
    """Link de afiliado apontando pro PRODUTO, não pra busca."""
    tag = _tag()
    base = f"https://www.{_dominio()}/dp/{asin}"
    return f"{base}?tag={tag}" if tag else base


def _imagem_maior(url: str, lado: int = 640) -> str:
    """Pede uma versão maior da mesma foto.

    A busca devolve miniatura de 320px (…_AC_UL320_.jpg), que fica borrada num
    card de celular retina. O tamanho é um pedaço da própria URL, então trocar
    o número basta — não é raspagem extra, é a mesma imagem noutro corte.
    640 é o meio-termo: nítido no 2x sem virar peso de página."""
    if not url:
        return ""
    novo, n = re.subn(r"_(AC_)?U[LXYSF]\d+_", f"_\\g<1>UL{lado}_", url)
    return novo if n else url


def _preco(texto: str) -> float:
    """'R$ 1.234,56' -> 1234.56"""
    t = re.sub(r"[^\d,.]", "", texto or "")
    if not t:
        return 0.0
    t = t.replace(".", "").replace(",", ".")
    try:
        return round(float(t), 2)
    except ValueError:
        return 0.0


# ── cache ─────────────────────────────────────────────────────────────────
def _cache_ler() -> dict:
    try:
        d = json.loads(CACHE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _cache_gravar(d: dict):
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, CACHE)
    except Exception as e:
        _log(f"não consegui gravar o cache: {e}")


def _chave(termo: str) -> str:
    return re.sub(r"\s+", " ", (termo or "").strip().lower())


def _anotar_preco(link: str, preco, nome: str = ""):
    """Grava a leitura no histórico de preços, com a data de HOJE.

    Sem isso o card da Amazon diria "conferido em <hoje>" usando um preço que
    pode ser de dias atrás — o health-check só consulta a API da Shopee, então
    produto da Amazon nunca ganharia leitura própria. Com isso, cada rodada
    deste script vira um ponto real e a data no card passa a ser verdade."""
    if not preco:
        return
    try:
        try:
            import historico_precos as _H
        except Exception:
            from creative_engine import historico_precos as _H
        _H.registrar(link, preco, nome=nome)
    except Exception as e:
        _log(f"   (preço não anotado no histórico: {str(e)[:60]})")


# ── busca ─────────────────────────────────────────────────────────────────
def buscar(termos: list, diag: bool = False) -> dict:
    """Resolve vários termos numa sessão só de navegador.

    Devolve {termo: {ok, asin, titulo, preco, imagem, link}} — e para tudo no
    primeiro sinal de bloqueio, sem tentar os termos restantes.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        _log("playwright não instalado (pip install playwright && playwright install chromium)")
        return {}

    saida, bloqueou = {}, False
    with sync_playwright() as pw:
        exe = (os.environ.get("PLAYWRIGHT_CHROMIUM") or "").strip() or None
        navegador = pw.chromium.launch(
            headless=True, executable_path=exe,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-dev-shm-usage"])
        ctx = navegador.new_context(
            user_agent=_UA, locale="pt-BR", timezone_id="America/Sao_Paulo",
            viewport={"width": 1366, "height": 900})
        ctx.add_init_script(_STEALTH_JS)
        pagina = ctx.new_page()

        for i, termo in enumerate(termos):
            if bloqueou:
                break
            if i:
                espera = random.uniform(PAUSA_MIN, PAUSA_MAX)
                _log(f"   (aguardando {espera:.0f}s)")
                time.sleep(espera)
            url = (f"https://www.{_dominio()}/s?k="
                   + re.sub(r"\s+", "+", termo.strip()))
            try:
                pagina.goto(url, timeout=35000, wait_until="domcontentloaded")
                pagina.wait_for_timeout(1800)
                dados = pagina.evaluate(_EXTRAIR_JS)
            except Exception as e:
                _log(f"   ✗ {termo[:40]}: {str(e)[:70]}")
                saida[termo] = {"ok": False, "motivo": "erro de rede"}
                continue

            if dados.get("bloqueado"):
                _log("   🛑 a Amazon pediu captcha — encerrando a rodada AGORA")
                _log("      (não insista hoje; tente de novo amanhã, com limite menor)")
                saida[termo] = {"ok": False, "motivo": "captcha"}
                bloqueou = True
                break

            achados = dados.get("achados") or []
            if diag:
                m = dados.get("marcadores") or {}
                _log(f"   [diag] {dados.get('total', 0)} cartões, "
                     f"{len(achados)} com ASIN, "
                     f"{sum(1 for a in achados if a['patrocinado'])} patrocinados")
                _log(f"   [diag] quem detectou: sspa={m.get('sspa', 0)} "
                     f"rotulo={m.get('rotulo', 0)} tipo={m.get('tipo', 0)} "
                     f"texto={m.get('texto', 0)}")
                if not any(m.values()):
                    _log("   [diag] ⚠️  NENHUM marcador de anúncio bateu — ou a busca"
                         " não tinha anúncio, ou a detecção precisa de ajuste")
                for a in achados[:3]:
                    _log(f"      {'AD ' if a['patrocinado'] else '   '}{a['asin']} "
                         f"{a['precoTxt'] or '(sem preço)'}  {a['titulo'][:52]}")

            organicos = [a for a in achados if not a["patrocinado"] and a["titulo"]]
            if not organicos:
                _log(f"   ✗ {termo[:40]}: nenhum resultado orgânico")
                saida[termo] = {"ok": False, "motivo": "sem resultado"}
                continue

            a = organicos[0]
            saida[termo] = {
                "ok": True, "asin": a["asin"], "titulo": a["titulo"],
                "preco": _preco(a["precoTxt"]),
                "imagem": _imagem_maior(a["imagem"]),
                "link": link_de_produto(a["asin"]),
            }
            _log(f"   ✓ {a['asin']}  R$ {saida[termo]['preco']:.2f}  "
                 f"{a['titulo'][:46]}")

        ctx.close()
        navegador.close()
    return saida


# ── fila ──────────────────────────────────────────────────────────────────
def _precisa(item: dict) -> bool:
    """Entrada da Amazon que ainda é link de BUSCA (ou está sem foto)."""
    if (item.get("plataforma") or "").lower() != "amazon":
        return False
    link = item.get("link") or ""
    return ("/s?k=" in link) or (not (item.get("imagem") or "").strip())


def enriquecer_fila(limite: int = LIMITE_PADRAO, simular: bool = False,
                    diag: bool = False) -> int:
    if not ligado():
        _log("AMAZON_PLAYWRIGHT=0 — desligado, nada a fazer")
        return 0
    if not _tag():
        _log("AMAZON_TAG vazio no .env — sem ele o link não é de afiliado")
        return 1
    try:
        fila = json.loads(FILA.read_text(encoding="utf-8"))
    except Exception as e:
        _log(f"não consegui ler {FILA}: {e}")
        return 1

    cache = _cache_ler()
    pendentes, ja_no_cache = [], []
    for item in fila:
        if not isinstance(item, dict) or not _precisa(item):
            continue
        termo = (item.get("campeao") or item.get("produto") or "").strip()
        if not termo:
            continue
        if _chave(termo) in cache:
            ja_no_cache.append((item, termo))
        elif termo not in pendentes:
            pendentes.append(termo)

    _log(f"{len(ja_no_cache)} já resolvidos antes · {len(pendentes)} pra buscar "
         f"(teto desta rodada: {limite})")
    alvo = pendentes[:limite]

    novos = buscar(alvo, diag=diag) if alvo else {}
    for termo, r in novos.items():
        if r.get("ok"):
            cache[_chave(termo)] = r
    if novos and not simular:
        _cache_gravar(cache)

    # aplica na fila: cache antigo + o que acabou de sair
    trocados = 0
    for item in fila:
        if not isinstance(item, dict) or not _precisa(item):
            continue
        termo = (item.get("campeao") or item.get("produto") or "").strip()
        r = cache.get(_chave(termo))
        if not r or not r.get("ok"):
            continue
        item["link"] = r["link"]
        item["imagem"] = r.get("imagem") or item.get("imagem", "")
        item["preco"] = r.get("preco") or item.get("preco", 0)
        if r.get("titulo"):
            item["campeao"] = r["titulo"]     # título oficial no lugar do termo
        if not simular:
            _anotar_preco(r["link"], r.get("preco"), r.get("titulo", ""))
        trocados += 1

    if not trocados:
        _log("nada pra aplicar na fila")
        return 0
    if simular:
        _log(f"[simulação] {trocados} produto(s) da Amazon ganhariam "
             f"link de produto, foto, preço e título")
        return 0

    tmp = FILA.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(fila, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, FILA)
    _log(f"✅ {trocados} produto(s) da Amazon agora têm produto de verdade")
    _log("   rode o deploy_site.py pra ver na vitrine")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Resolve produto real da Amazon")
    ap.add_argument("--limite", type=int, default=LIMITE_PADRAO,
                    help=f"quantos termos buscar nesta rodada (padrão {LIMITE_PADRAO})")
    ap.add_argument("--simular", action="store_true", help="não grava nada")
    ap.add_argument("--diag", action="store_true",
                    help="mostra o que a página devolveu (pra ajustar seletor)")
    ap.add_argument("--termo", default="",
                    help="busca UM termo e mostra o resultado, sem tocar na fila")
    a = ap.parse_args()

    _carregar_env()
    if a.termo:
        r = buscar([a.termo], diag=True).get(a.termo, {})
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r.get("ok") else 1
    return enriquecer_fila(limite=a.limite, simular=a.simular, diag=a.diag)


if __name__ == "__main__":
    sys.exit(main())
