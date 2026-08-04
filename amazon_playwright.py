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
import unicodedata
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
  // Evidência da PÁGINA inteira, não só dos cards: distingue "a detecção
  // falhou" de "esta página realmente não tem anúncio". Sessão headless, sem
  // cookie e de IP de datacenter costuma receber página sem colocação paga.
  const pagina = {
    sspaNaPagina: document.querySelectorAll('a[href*="/sspa/click"]').length,
    palavraNaPagina: (document.body.innerText.match(/Patrocinad|Sponsored/gi) || []).length,
    asinNaPagina: document.querySelectorAll('[data-asin]').length,
  };
  return {bloqueado: false, total: cartoes.length, achados, marcadores, pagina};
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


# Teto de ABSURDO, não teste de acerto. Nasceu em 250, desceu pra 150 e voltou
# pra 500 quando os dados mostraram que a ideia estava errada:
#
#   - rejeitou "Dispensador automático de remédios" -> "Dispensador automático
#     de comprimidos" (R$ 449), que é o ÚNICO caso em que a busca acertou em
#     cheio. Escondia um card correto.
#   - deixou passar "Tips pelo huela rico todo" -> "Como ficar rico" (R$ 42),
#     que é errado e barato.
#
# Preço não mede acerto. E a vitrine já vende iPhone de R$ 11 mil vindo da
# Shopee, então travar só a Amazon em R$ 150 era incoerente. Fica alto só pra
# barrar o caso grotesco (termo vago que resolve pra uma TV).
#
# Quem separa "parecido" de "certo" é o olho humano na tabela do --simular, e
# a decisão dele agora fica gravada: veja --recusar.
PRECO_MAX_PADRAO = 500.0

# Marcas de espanhol que praticamente não aparecem em título pt-BR. O termo em
# si é difícil de julgar (pt e es compartilham muita palavra), mas o TÍTULO que
# volta denuncia: "Cuida tu pelo: Todo lo que necesitas saber" veio de um termo
# que era fragmento de legenda em espanhol.
_MARCAS_ES = (" lo que ", " necesitas ", " para el ", " para la ", " sobre el ",
              " de los ", " de las ", " todo lo ", " tu pelo ", " cómo ", " cuida tu ")

_VAZIAS = frozenset("""para com sem por que dos das uma uns umas pelo pela este esta
esse essa isso aquilo mais menos muito todo toda todos todas seu sua meu minha""".split())


def _palavras_uteis(texto: str) -> set:
    """Palavras de 4+ letras, sem acento, que carregam sentido."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return {p for p in re.findall(r"[a-z]{4,}", t) if p not in _VAZIAS}


def recusar(termo: str, r: dict) -> str:
    """Motivo pra NÃO aceitar o par termo → produto, ou '' se estiver bom.

    A busca faz o que foi pedida; quando o termo do vídeo é ruim, ela devolve
    algo que casa com as palavras mas não com o produto. Estas guardas pegam os
    casos que dá pra pegar sem chutar."""
    preco = float(r.get("preco") or 0)
    teto = float(os.getenv("AMAZON_PRECO_MAX", PRECO_MAX_PADRAO) or PRECO_MAX_PADRAO)
    if preco > teto:
        return f"R$ {preco:.2f} passa do teto de R$ {teto:.0f}"

    titulo = r.get("titulo") or ""
    baixo = f" {titulo.lower()} "
    if any(m in baixo for m in _MARCAS_ES):
        return "o título voltou em espanhol"

    # Rede de segurança fraca, e vale saber por quê: título da Amazon é longo e
    # cheio de palavra-chave, então quase sempre casa alguma palavra do termo.
    # Só pega o caso extremo, de produto totalmente sem relação. Quem separa
    # "parecido" de "certo" é o olho humano na tabela do --simular.
    comuns = _palavras_uteis(termo) & _palavras_uteis(titulo)
    if not comuns:
        return "o produto não tem nenhuma palavra do termo"
    return ""


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


# Contador de buscas vazias por termo. Fica numa chave RESERVADA do cache, e
# não no registro do termo, porque `_chave(termo) in cache` é o que decide se
# ele já foi resolvido — gravar a tentativa ali marcaria o termo como pronto e
# ele nunca mais seria buscado.
#
# Por que isto existe: em 03/08 a rodada resolveu 2 produtos de verdade e então
# bateu em "Cosas deberías hacer mejorar apariencia" e "Tips pelo huela rico
# todo" — dois nomes-lixo de legenda em espanhol. Duas vazias seguidas
# dispararam o freio anti-bloqueio e a rodada morreu pela metade. O freio está
# certo; ele só não sabia diferenciar "a Amazon me bloqueou" de "esse termo não
# existe porque não é produto".
CHAVE_VAZIOS = "__vazios__"
VAZIOS_ATE_DESCONFIAR = 3

# Quantas vazias seguidas encerram a rodada. Era 2. Subiu pra 3 depois de
# simular a primeira rodada com a fila real: na estreia nenhum termo tem
# histórico, os dois nomes-lixo caem no começo da lista e o freio matava a
# rodada ANTES de tentar qualquer produto de verdade. Com 3, o terceiro termo
# desempata — se ele resolve, era lixo; se também vem vazio, é bloqueio mesmo.
# O custo quando a Amazon está realmente fora é uma requisição a mais.
VAZIOS_PRA_PARAR = 3


def _vazios_de(cache: dict) -> dict:
    v = cache.get(CHAVE_VAZIOS)
    return v if isinstance(v, dict) else {}


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
def buscar(termos: list, diag: bool = False, vazios_antes: dict = None) -> dict:
    """Resolve vários termos numa sessão só de navegador.

    Devolve {termo: {ok, asin, titulo, preco, imagem, link}} — e para tudo no
    primeiro sinal de bloqueio, sem tentar os termos restantes.

    vazios_antes = {termo: quantas vezes já voltou vazio}. Termo com histórico
    de vazio não conta pro freio anti-bloqueio: ele voltar vazio de novo é o
    esperado, não sinal de que a Amazon caiu.
    """
    vazios_antes = vazios_antes or {}
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        _log("playwright não instalado (pip install playwright && playwright install chromium)")
        return {}

    saida, bloqueou, vazios = {}, False, 0
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
                saida[termo] = {"ok": False, "transitorio": True}
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
                pg = dados.get("pagina") or {}
                _log(f"   [diag] na página inteira: {pg.get('sspaNaPagina', 0)} link(s) "
                     f"/sspa/click · a palavra 'Patrocinado' aparece "
                     f"{pg.get('palavraNaPagina', 0)}x · "
                     f"{pg.get('asinNaPagina', 0)} elementos com ASIN")
                if not any(m.values()):
                    if not pg.get("sspaNaPagina") and not pg.get("palavraNaPagina"):
                        _log("   [diag] ✅ a página REALMENTE não tem anúncio — "
                             "o 1º resultado é orgânico mesmo")
                    else:
                        _log("   [diag] ⚠️  tem anúncio na página mas o card não foi "
                             "marcado: a detecção precisa de ajuste")
                for a in achados[:3]:
                    _log(f"      {'AD ' if a['patrocinado'] else '   '}{a['asin']} "
                         f"{a['precoTxt'] or '(sem preço)'}  {a['titulo'][:52]}")

            organicos = [a for a in achados if not a["patrocinado"] and a["titulo"]]
            if not organicos:
                # NÃO cacheia: página vazia é quase sempre passageira. Medido em
                # produção — "Copo batedor de ovos" resolveu em três rodadas e
                # voltou vazio na quarta. Gravar isso marcaria pra sempre um
                # termo que funciona. Sem `motivo`, o cache ignora.
                antes = int(vazios_antes.get(_chave(termo), 0))
                if antes >= VAZIOS_ATE_DESCONFIAR:
                    _log(f"   ✗ {termo[:40]}: vazio de novo "
                         f"({antes+1}ª vez) — não parece ser produto")
                else:
                    vazios += 1
                    _log(f"   ✗ {termo[:40]}: sem resultado (tento de novo depois)")
                saida[termo] = {"ok": False, "transitorio": True}
                if vazios >= VAZIOS_PRA_PARAR:
                    _log(f"   🛑 {VAZIOS_PRA_PARAR} buscas vazias seguidas — a Amazon")
                    _log("      está servindo página vazia. Encerrando a rodada.")
                    _log("      (espere algumas horas; insistir só piora)")
                    bloqueou = True
                continue
            vazios = 0

            a = organicos[0]
            r = {
                "ok": True, "asin": a["asin"], "titulo": a["titulo"],
                "preco": _preco(a["precoTxt"]),
                "imagem": _imagem_maior(a["imagem"]),
                "link": link_de_produto(a["asin"]),
            }
            motivo = recusar(termo, r)
            if motivo:
                # Guarda o motivo no cache pra não gastar requisição repetindo
                # a mesma busca ruim. Apagar a linha do termo força nova busca.
                saida[termo] = {"ok": False, "motivo": motivo,
                                "titulo": a["titulo"], "preco": r["preco"]}
                _log(f"   ✗ \"{termo[:34]}\"  — {motivo}")
                _log(f"       (veio: {a['titulo'][:48]})")
                continue
            saida[termo] = r
            _log(f"   ✓ \"{termo[:34]}\"")
            _log(f"       → {a['asin']}  R$ {r['preco']:.2f}  "
                 f"{a['titulo'][:52]}")

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

    # Quem já voltou vazio várias vezes vai pro FIM: o teto por rodada é baixo
    # (5), e antes disto dois nomes-lixo no começo da lista consumiam metade da
    # rodada e ainda derrubavam o freio antes dos produtos de verdade.
    vazios_antes = _vazios_de(cache)
    pendentes.sort(key=lambda t: int(vazios_antes.get(_chave(t), 0)))
    teimosos = sum(1 for t in pendentes
                   if int(vazios_antes.get(_chave(t), 0)) >= VAZIOS_ATE_DESCONFIAR)

    _log(f"{len(ja_no_cache)} já resolvidos antes · {len(pendentes)} pra buscar "
         f"(teto desta rodada: {limite})"
         + (f" · {teimosos} no fim da fila por já terem vindo vazios" if teimosos else ""))
    alvo = pendentes[:limite]

    novos = buscar(alvo, diag=diag, vazios_antes=vazios_antes) if alvo else {}
    for termo, r in novos.items():
        # Cacheia decisão DURÁVEL: o acerto, e a recusa com motivo (que é
        # julgamento sobre o produto). Falha transitória — página vazia, rede —
        # fica de fora de propósito, pra ser tentada de novo.
        if r.get("ok") or (r.get("motivo") and not r.get("transitorio")):
            cache[_chave(termo)] = r
            vazios_antes.pop(_chave(termo), None)   # resolveu: zera o histórico
        elif r.get("transitorio"):
            k = _chave(termo)
            vazios_antes[k] = int(vazios_antes.get(k, 0)) + 1
    # o contador é separado do registro do termo de propósito (ver CHAVE_VAZIOS)
    cache[CHAVE_VAZIOS] = vazios_antes
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
        # Mostra o PAR, não só o resultado: quem decide se o produto casa com o
        # termo do vídeo é você, e sem ver os dois lado a lado não dá.
        _log("")
        _log("     termo do vídeo            →  produto escolhido na Amazon")
        _log("     " + "-" * 66)
        for item in fila:
            if not isinstance(item, dict):
                continue
            if (item.get("plataforma") or "").lower() != "amazon":
                continue
            termo = (item.get("produto") or "").strip()
            r = cache.get(_chave(termo))
            if not r:
                continue
            if not r.get("ok"):
                _log(f'     {termo[:24]:24}  ✗  recusado: {r.get("motivo", "?")}')
                continue
            _log(f'     {termo[:24]:24}  →  R$ {r["preco"]:>8.2f}  {r["titulo"][:34]}')
        _log("")
        _log(f"[simulação] {trocados} produto(s) da Amazon ganhariam "
             f"link de produto, foto, preço e título")
        _log("     confira os pares acima ANTES de rodar sem --simular")
        _log('     algum errado?  --recusar "termo do vídeo"  (não volta mais)')
        return 0

    tmp = FILA.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(fila, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, FILA)
    _log(f"✅ {trocados} produto(s) da Amazon agora têm produto de verdade")
    _log("   rode o deploy_site.py pra ver na vitrine")
    return 0


def recusar_termo(termo: str, motivo: str = "recusado por você") -> int:
    """Marca um par como recusado, pra sempre.

    A conferência humana é o que de fato separa "parecido" de "certo" aqui —
    então ela precisa virar estado, não sumir quando o terminal fecha. Termo
    recusado nunca mais é buscado nem entra na vitrine."""
    cache = _cache_ler()
    chave = _chave(termo)
    antes = cache.get(chave) or {}
    cache[chave] = {"ok": False, "motivo": motivo,
                    "titulo": antes.get("titulo", ""), "preco": antes.get("preco", 0)}
    _cache_gravar(cache)
    _log(f"recusado pra sempre: \"{termo}\"")
    if antes.get("titulo"):
        _log(f"   (era: {antes['titulo'][:56]})")
    _log("   pra reverter:  --esquecer \"" + termo + "\"")
    return 0


def esquecer_termo(termo: str) -> int:
    """Tira o termo do cache: ele volta a ser buscado na próxima rodada."""
    cache = _cache_ler()
    if cache.pop(_chave(termo), None) is None:
        _log(f"\"{termo}\" não estava no cache — nada a fazer")
        return 0
    _cache_gravar(cache)
    _log(f"esquecido: \"{termo}\" volta a ser buscado na próxima rodada")
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
    ap.add_argument("--recusar", default="",
                    help="marca um termo como recusado pra sempre (não vai pra vitrine)")
    ap.add_argument("--esquecer", default="",
                    help="tira o termo do cache pra ser buscado de novo")
    a = ap.parse_args()

    _carregar_env()
    if a.recusar:
        return recusar_termo(a.recusar)
    if a.esquecer:
        return esquecer_termo(a.esquecer)
    if a.termo:
        r = buscar([a.termo], diag=True).get(a.termo, {})
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r.get("ok") else 1
    return enriquecer_fila(limite=a.limite, simular=a.simular, diag=a.diag)


if __name__ == "__main__":
    sys.exit(main())
