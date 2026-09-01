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
# A fonte da marca vai como ARQUIVO separado, não embutida em base64 no HTML:
# embutida ela engorda o index em ~85KB e atrasa a primeira pintura. Como
# arquivo, o texto aparece na hora com a fonte do sistema e troca quando a
# nossa chega (font-display:swap) — quem vem do Reels no 4G não fica no branco.
FONTE = BASE_DIR / "assets" / "topshop-fonte.woff2"
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


def _checar_online(link, obter, nome="", H=None, hist=None, achados=None):
    """'vivo' | 'morto' | 'incerto'. Só devolve 'morto' quando a API CONFIRMA
    que o produto não existe mais (delistado).

    De quebra guarda o preço que veio na resposta: essa chamada já acontecia
    de qualquer jeito, então o histórico sai de graça, sem nenhuma requisição
    nova. Falha ao anotar nunca derruba o health-check."""
    try:
        shop_id, item_id = _ids_do_link(link)
        if achados is not None and item_id:
            achados[link] = str(item_id)
        if not item_id:
            return "incerto"
        d = obter(str(item_id), shop_id=int(shop_id))
        if d.get("ok"):
            if H is not None and hist is not None:
                try:
                    H.registrar(link, d.get("preco"),
                                nome=d.get("titulo") or nome,
                                de=d.get("preco_de"), dados=hist)
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
    achados = {}
    vivos, mortos, checados = [], 0, 0
    for p in produtos:
        link = p.get("link", "")
        # O health-check é feito pela API de afiliado da SHOPEE: ela não tem
        # como confirmar produto de outra loja. Passar a Amazon por aqui só
        # gastava uma requisição por rodada sem responder nada.
        if (p.get("plataforma") or "shopee").lower() != "shopee":
            vivos.append(p)
            continue
        ent = cache.get(link)
        if ent and (agora - ent.get("ts", 0)) < HEALTH_TTL:
            estado = ent.get("estado", "incerto")
        else:
            estado = _checar_online(link, obter, nome=p.get("nome", ""),
                                    H=H, hist=hist, achados=achados)
            checados += 1
            if estado in ("vivo", "morto"):     # só cacheia resultado confiável
                # guarda o itemId junto: é a identidade real do produto e é o
                # que permite achar dois links de afiliado pro mesmo anúncio
                cache[link] = {"estado": estado, "ts": agora,
                               "item": achados.get(link, "")}
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


def _deduplicar(produtos, cache):
    """Um card por produto — a identidade é o itemId da Shopee.

    Não dá pra deduplicar por nome: o campo `produto` da fila é o termo que o
    extrator tirou do vídeo, e na fila real existe entrada chamada "2 mil
    vendidos". Comparar nome fundiria produtos diferentes que por acaso caíram
    no mesmo texto ruim. Dois links de afiliado apontando pro mesmo itemId, ao
    contrário, são o mesmo anúncio sem chance de engano.

    O itemId sai do cache do health-check, que já resolveu o link — nenhuma
    requisição nova. Produto cujo cache ainda não tem itemId (entrada gravada
    antes disto existir) simplesmente não deduplica nesta rodada.
    """
    vistos, saida, repetidos = {}, [], 0
    for p in produtos:
        item = (cache.get(p.get("link", "")) or {}).get("item")
        if item and item in vistos:
            # o repetido ainda serve de doador: se tem foto ou preço que
            # faltam no que fica, aproveita antes de descartar
            mantido = vistos[item]
            for campo in ("imagem", "preco"):
                if not mantido.get(campo) and p.get(campo):
                    mantido[campo] = p[campo]
            repetidos += 1
            _log(f"   👯 mesmo produto em 2 links: {p.get('nome', '?')[:40]}")
            continue
        if item:
            vistos[item] = p
        saida.append(p)
    if repetidos:
        _log(f"deduplicação: {repetidos} link(s) repetido(s) do mesmo produto")
    return saida


def _publicar_fonte():
    """Copia a fonte pro repositório do site. Devolve True se mudou algo.

    Sem o arquivo o site não quebra: o @font-face falha e o navegador usa a
    fonte do sistema, que já está na lista de fallback."""
    if not FONTE.exists():
        _log(f"fonte não encontrada em {FONTE} — o site usa a fonte do sistema")
        return False
    destino = SITE_REPO / FONTE.name
    dados = FONTE.read_bytes()
    if destino.exists() and destino.read_bytes() == dados:
        return False
    destino.write_bytes(dados)
    _log(f"fonte publicada: {FONTE.name} ({len(dados) / 1024:.0f} KB)")
    return True


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

    # TETO DA VITRINE — e ele fica AQUI, antes do health-check, de propósito.
    #
    # Até 15/08 o teto morava no gravador (`_registrar_no_site`, `fila[:80]`):
    # a fila era cortada em 80 e produto novo EXPULSAVA o mais antigo. O
    # acervo virou janela deslizante de 7 dias — o Jarvis minerava todo dia e
    # o total nunca subia, e produto que saía da janela sumia do site calado.
    #
    # Acervo e vitrine são coisas diferentes. O acervo pode crescer para
    # sempre (é um JSON); a VITRINE tem dois custos reais que crescem com ela:
    #   · peso do index.html na primeira pintura (quem vem do Reels, no 4G)
    #   · o health-check bate na API de afiliado por produto não-cacheado
    # Cortar aqui, ANTES do `_filtrar_vivos`, é o que segura os dois: a
    # chamada de API continua limitada ao que vai pro ar, não ao acervo.
    #
    # A ordem já é a certa: `_carregar_produtos` devolve o produtos_fila.json
    # primeiro (o gravador insere no índice 0, então é mais-recente-primeiro)
    # e só depois complementa com a curadoria.
    teto = int(os.environ.get("VITRINE_MAX_PRODUTOS", "200"))
    if len(produtos) > teto:
        _log(f"   teto da vitrine: mostro os {teto} mais recentes de "
             f"{len(produtos)} (VITRINE_MAX_PRODUTOS)")
        _log("   os demais continuam no acervo — não são apagados")
        produtos = produtos[:teto]

    # blindagem: esconde os que morreram (delistados)
    produtos = _filtrar_vivos(produtos)
    if not produtos:
        _log("nenhum produto ativo — nada a publicar")
        return 1

    # 1 card por produto (o cache do health-check acabou de gravar os itemIds)
    produtos = _deduplicar(produtos, _load_cache())

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

    mudou_fonte = _publicar_fonte()

    # ⚠️ DUAS PÁGINAS DESDE 31/08, E A SEGUNDA NÃO É OPCIONAL. A home passou a
    # ESCOLHER (um destaque, categorias, o convite) em vez de despejar os 300
    # produtos — "ngm rola isso tudo, as pessoas pesquisam". O botão mais
    # clicado dela aponta pra `todos.html`; publicar só o index deixaria um
    # link quebrado no lugar de maior tráfego da página.
    # 📌 `list(produtos)` nas duas: `gerar_site` filtra a própria cópia com
    # `_vale_mostrar`, e passar a mesma lista deixaria a segunda página vendo
    # o resultado do filtro da primeira.
    html = B.gerar_site(list(produtos))
    html_cat = B.gerar_catalogo(list(produtos))
    html_leg = B.gerar_legal(list(produtos))
    idx = SITE_REPO / "index.html"
    cat = SITE_REPO / "todos.html"
    leg = SITE_REPO / "termos.html"

    def _difere(caminho, conteudo):
        return not (caminho.exists()
                    and caminho.read_text(encoding="utf-8") == conteudo)

    mudou_html = (_difere(idx, html) or _difere(cat, html_cat)
                  or _difere(leg, html_leg))

    if not mudou_html and not mudou_fonte:
        # ⚠️ "sem mudança" NÃO quer dizer "nada pendente". Se um push anterior
        # falhou, o commit ficou aqui e a vitrine no ar está velha — e este
        # return sairia por cima disso sem nunca tentar de novo. Foi assim que
        # 8 rodadas seguidas ficaram presas em 15/08.
        atras_frente = _git("rev-list", "--left-right", "--count", "@{u}...HEAD")
        partes = (atras_frente.stdout or "").split()
        if len(partes) == 2 and partes[1].isdigit() and int(partes[1]) > 0:
            _log(f"site sem mudança, mas {partes[1]} commit(s) nunca subiram — "
                 f"empurrando")
            return 0 if _empurrar() else 1
        _log("site sem mudança — não precisa subir")
        return 0
    if mudou_html:
        idx.write_text(html, encoding="utf-8")
        cat.write_text(html_cat, encoding="utf-8")
        leg.write_text(html_leg, encoding="utf-8")
        _log("páginas: index.html + todos.html + termos.html")

    _git("add", "-A")
    c = _git("commit", "-m", f"vitrine: {len(produtos)} produtos (auto)")
    if c.returncode not in (0, 1):   # 1 = nada pra commitar (ok)
        _log("commit falhou: " + (c.stderr or c.stdout)[:200])
        return 1
    if not _empurrar():
        return 1
    _log(f"OK! Site publicado com {len(produtos)} produtos -> topshopoficial.com.br")
    return 0


def _empurrar() -> bool:
    """Empurra, e se tiver divergido do origin, reconcilia e tenta de novo."""
    p = _git("push")
    if p.returncode != 0:
        erro = (p.stderr or p.stdout)
        _log("push falhou: " + erro[:200])
        # DIVERGÊNCIA: o origin andou por fora (outro clone, edição pelo site do
        # GitHub, o curso_page_builder de outra máquina). Em 15/08 isso ficou 8
        # rodadas em pé: o cron commitava a cada 2h, o push voltava
        # 'non-fast-forward', e o log da falha ia pro fim de um arquivo que
        # ninguém lia. A vitrine no ar congelou em 130 enquanto a VPS achava
        # que estava publicando.
        if "non-fast-forward" in erro or "fetch first" in erro or "rejected" in erro:
            _log("   divergiu do origin — rebase e tento uma vez")
            # --rebase põe os commits locais EM CIMA do que veio; --autostash
            # protege alteração solta no diretório. Se der conflito no
            # index.html (arquivo gerado), a versão de agora é a certa: ela
            # saiu da fila atual, e a do origin saiu de uma fila mais velha.
            _git("fetch", "origin")
            # ⚠️ `-X theirs`, NÃO `-X ours`. Num REBASE os lados são
            # invertidos em relação ao merge: "ours" é o upstream (que fica
            # em cima da mesa) e "theirs" são os SEUS commits sendo
            # replicados. Escrevi `ours` primeiro e medi: com divergência
            # 1/1, `-X ours` manteve a versão VELHA do origin. É `theirs`
            # que preserva o index.html recém-gerado — e ele é o certo
            # porque saiu da fila de agora, não de uma fila de dias atrás.
            r = _git("rebase", "-X", "theirs", "@{u}")
            if r.returncode != 0:
                _git("rebase", "--abort")
                _log("   ✗ rebase não resolveu — histórico precisa de mão "
                     "humana. Rode: python3 auditoria_site.py")
                return False
            p = _git("push")
            if p.returncode != 0:
                _log("   ✗ push falhou de novo: "
                     + (p.stderr or p.stdout)[:160])
                return False
            _log("   ✅ reconciliado e publicado")
        else:
            return False
    return True


if __name__ == "__main__":
    # TRAVA DE INSTÂNCIA ÚNICA. Em 04/08/2026 o `crontab -l` tinha esta
    # mesma linha repetida (algumas 4x, o ceo_agent 8x) e as cópias rodaram
    # juntas o dia inteiro. shared/trava.py conta a história inteira.
    # Sem a trava disponível, roda como antes — ela protege, não bloqueia.
    try:
        from shared.trava import rodar_unico
    except Exception:
        sys.exit(main())
    sys.exit(rodar_unico("deploy_site", main))
