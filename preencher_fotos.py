#!/usr/bin/env python3
# preencher_fotos.py -- pega a foto OFICIAL (API de afiliado Shopee) dos produtos
# que JA estao na vitrine mas entraram sem imagem. A Shopee bloqueia raspar a
# pagina (sem og:image) e a API interna (403), entao usamos a API OFICIAL de
# afiliado: segue o link -> pega o itemId -> productOfferV2 -> imageUrl.
# Best-effort e idempotente (so mexe em quem esta sem imagem). Roda em ~/jarvis:
#     python3 preencher_fotos.py   &&   python3 deploy_site.py
import os
import re
import sys
import json
import time
import tempfile
from pathlib import Path


def _carregar_env():
    """Roda 'na mao' (fora do daemon) nao carrega o .env sozinho — a API de
    afiliado precisa de SHOPEE_APP_ID/SECRET. Carrega o .env do ~/jarvis aqui,
    sem sobrescrever o que ja estiver no ambiente."""
    for cand in (Path(".env"), Path(__file__).resolve().parent / ".env"):
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


_carregar_env()

# API oficial de afiliado do projeto (flat OU package)
try:
    from integrations.shopee_affiliate import obter_dados_produto
except Exception:
    from shopee_affiliate import obter_dados_produto

# acha o produtos_fila.json (mesmo que o site usa)
CANDIDATOS = [
    Path("shared/produtos_fila.json"),
    Path(__file__).resolve().parent / "shared" / "produtos_fila.json",
]
FILA = next((c for c in CANDIDATOS if c.exists()), CANDIDATOS[0])

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"

# ⚠️ O MESMO ARQUIVO QUE O `deploy_site` JÁ ESCREVE. O health-check resolve o
# link e guarda `{link: {estado, ts, item}}` — o `item` é o itemId. Este script
# resolvia tudo de novo, do zero, a cada rodada: mesma requisição, mesmo
# resultado, mesma exposição ao anti-bot da Shopee. Cache compartilhado não é
# otimização aqui, é parar de jogar fora trabalho que já foi feito.
CACHE_IDS = Path(__file__).resolve().parent / "shared" / "health_cache.json"


def _cache_ler() -> dict:
    try:
        return json.loads(CACHE_IDS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cache_gravar(cache: dict) -> None:
    """Grava sem NUNCA derrubar a rodada: cache é conveniência, não requisito.

    ⚠️ E preserva o que já estava lá. O `deploy_site` guarda `estado` e `ts`
    nas mesmas chaves; sobrescrever a entrada inteira com só o `item` apagaria
    o health-check e faria o site re-checar tudo na próxima rodada — uma
    chamada de API por produto, de graça, por causa de uma escrita descuidada.
    """
    try:
        CACHE_IDS.parent.mkdir(parents=True, exist_ok=True)
        CACHE_IDS.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    except Exception as e:
        print(f"   (não gravei o cache de itemId: {str(e)[:60]})")


def _ids_do_link(link: str):
    """Segue o link de afiliado ate a pagina do produto e extrai (shop_id, item_id)."""
    import requests
    r = requests.get(link, allow_redirects=True, timeout=15,
                     headers={"User-Agent": _UA})
    final = r.url or ""
    m = re.search(r"i\.(\d+)\.(\d+)", final)          # formato ...-i.shop.item
    if m:
        return m.group(1), m.group(2)
    pares = re.findall(r"/(\d+)/(\d+)", final.split("?")[0])   # .../shop/item
    return pares[-1] if pares else (None, None)


def _foto(link: str, item_guardado: str = "", cache: dict = None) -> str:
    """A foto oficial do produto. `item_guardado` = itemId que a FILA já tem.

    ⚠️ A ORDEM DAS FONTES É O CONSERTO. Antes ele ia direto pro redirect, e o
    redirect é a parte frágil: em 17/08 falhou em 4 de 5 produtos com
    `(sem itemId no link)` — o link curto da Shopee não carrega o id, então
    era preciso segui-lo até a página, e a página nem sempre responde o que a
    gente espera (anti-bot, interstício, URL sem o padrão `i.shop.item`).

    O id, porém, **já é conhecido em dois lugares mais confiáveis**: gravado na
    própria fila pela mineração, e no `health_cache.json` que o `deploy_site`
    escreve. Perguntar à rede algo que está no disco é o desperdício; e aqui
    não era só lentidão, era falha — 0 de 5 fotos preenchidas.
    """
    try:
        shop_id = item_id = None
        origem = ""

        # 1) o que a fila guardou (mineração) — não custa nada
        if item_guardado:
            item_id, shop_id, origem = str(item_guardado), None, "fila"

        # 2) o que o health-check do site já resolveu
        if not item_id and cache is not None:
            ent = cache.get(link) or {}
            if ent.get("item"):
                item_id, origem = str(ent["item"]), "cache"

        # 3) só então a rede
        if not item_id:
            shop_id, item_id = _ids_do_link(link)
            origem = "redirect"
            if item_id and cache is not None:
                ent = dict(cache.get(link) or {})   # preserva estado/ts
                ent["item"] = str(item_id)
                cache[link] = ent

        if not item_id:
            print("   (sem itemId: nem na fila, nem no cache, nem no redirect)")
            return ""

        # ⚠️ `shop_id` pode ser None quando o id veio da fila/cache — a API
        # aceita a consulta só com o itemId. `int(None)` explodiria, e a
        # exceção viraria "(erro: ...)" mascarando um caminho que FUNCIONA.
        d = (obter_dados_produto(str(item_id), shop_id=int(shop_id))
             if shop_id else obter_dados_produto(str(item_id)))
        if d.get("ok") and d.get("imagem"):
            return d["imagem"]
        print(f"   (API via {origem}: {str(d.get('erro'))[:60]})")
        return ""
    except Exception as e:
        print(f"   (erro: {str(e)[:70]})")
        return ""


def _salvar_atomico(caminho: Path, dados):
    tmp = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(caminho.parent),
        prefix=".fila_", suffix=".tmp", delete=False)
    try:
        json.dump(dados, tmp, ensure_ascii=False, indent=2)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, caminho)
    except Exception:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def main():
    if not FILA.exists():
        print(f"ERRO: nao achei {FILA}. Roda de dentro de ~/jarvis.")
        return 2
    fila = json.loads(FILA.read_text(encoding="utf-8"))
    if not isinstance(fila, list):
        print("ERRO: fila em formato inesperado.")
        return 2

    sem_foto = [it for it in fila
                if isinstance(it, dict) and it.get("link") and not it.get("imagem")]
    print(f"{len(fila)} produtos na vitrine · {len(sem_foto)} sem foto")
    if not sem_foto:
        print("nada a fazer — todos ja tem foto ✔")
        return 0

    # ⚠️ TETO, porque o acervo agora CRESCE (15/08). Até hoje a fila era
    # truncada em 80 pelo gravador, e esse corte protegia este laço sem que
    # ninguém tivesse escrito isso em lugar nenhum. Com o teto movido pro
    # deploy_site (FILA_ACERVO_MAX=500), este laço passaria a fazer centenas
    # de chamadas de API com 1,2s cada — mesma armadilha que o validar_fila
    # tinha. Default generoso: hoje não muda nada, e amanhã não vira rodada
    # que não termina.
    limite = int(os.environ.get("PREENCHER_FOTOS_MAX", "60"))
    if len(sem_foto) > limite:
        print(f"⚠️  {len(sem_foto)} sem foto, mas paro em {limite} nesta "
              f"rodada (PREENCHER_FOTOS_MAX). Rode de novo pra continuar.")
        sem_foto = sem_foto[:limite]

    cache = _cache_ler()
    achou = sem_id = 0
    for i, it in enumerate(sem_foto, 1):
        nome = (it.get("produto") or "?")[:50]
        print(f"[{i}/{len(sem_foto)}] {nome} ...", end=" ")
        guardado = str(it.get("item_id") or "").strip()
        img = _foto(it["link"], item_guardado=guardado, cache=cache)
        if img:
            it["imagem"] = img
            achou += 1
            print("OK 📷")
        else:
            print("sem foto")
        # ⚠️ o itemId resolvido volta pra FILA, não só pro cache: o cache é do
        # health-check e tem TTL de 6h; a fila é o registro do produto. Gravar
        # nos dois faz a próxima rodada não repetir nada.
        ent = cache.get(it["link"]) or {}
        if ent.get("item") and not guardado:
            it["item_id"] = str(ent["item"])
        if not (it.get("item_id") or ent.get("item")):
            sem_id += 1
        time.sleep(1.2)   # gentil com a API

    _cache_gravar(cache)
    _salvar_atomico(FILA, fila)
    print(f"\nPreenchi {achou}/{len(sem_foto)} fotos.")
    if sem_id:
        # ⚠️ ISTO NÃO É "TENTE DE NOVO". Sem itemId em nenhuma das três fontes,
        # repetir a rodada dá exatamente o mesmo resultado — o link não leva a
        # um produto que a API reconheça. É defeito do que a mineração gravou,
        # e o conserto é lá, não aqui.
        print(f"⚠️  {sem_id} produto(s) sem itemId em NENHUMA fonte (fila, "
              f"cache, redirect).")
        print("    Rodar de novo não muda: o link não resolve pra um produto "
              "que a API conheça.")
        print("    Esses ficam fora da vitrine até a mineração gravar o "
              "item_id na origem.")
    print("Agora: python3 deploy_site.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
