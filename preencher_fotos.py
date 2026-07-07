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


def _foto(link: str) -> str:
    try:
        shop_id, item_id = _ids_do_link(link)
        if not item_id:
            print("   (sem itemId no link)")
            return ""
        d = obter_dados_produto(str(item_id), shop_id=int(shop_id))
        if d.get("ok") and d.get("imagem"):
            return d["imagem"]
        print(f"   (API: {str(d.get('erro'))[:70]})")
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

    achou = 0
    for i, it in enumerate(sem_foto, 1):
        nome = (it.get("produto") or "?")[:50]
        print(f"[{i}/{len(sem_foto)}] {nome} ...", end=" ")
        img = _foto(it["link"])
        if img:
            it["imagem"] = img
            achou += 1
            print("OK 📷")
        else:
            print("sem foto")
        time.sleep(1.2)   # gentil com a API

    _salvar_atomico(FILA, fila)
    print(f"\nPreenchi {achou}/{len(sem_foto)} fotos. Agora: python3 deploy_site.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
