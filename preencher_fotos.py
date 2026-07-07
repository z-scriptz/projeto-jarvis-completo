#!/usr/bin/env python3
# preencher_fotos.py -- pega a foto (og:image) dos produtos que JA estao na
# vitrine mas entraram sem imagem (foram gravados antes do patch). Segue o link
# de afiliado ate a pagina do produto e extrai a foto. Best-effort e idempotente
# (so mexe em quem esta sem imagem). Roda de dentro de ~/jarvis:
#     python3 preencher_fotos.py   &&   python3 deploy_site.py
import os
import re
import sys
import json
import time
import tempfile
from pathlib import Path

# acha o produtos_fila.json (mesmo que o site usa)
CANDIDATOS = [
    Path("shared/produtos_fila.json"),
    Path(__file__).resolve().parent / "shared" / "produtos_fila.json",
]
FILA = next((c for c in CANDIDATOS if c.exists()), CANDIDATOS[0])

_UA = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Mobile Safari/537.36"
_RE_OG = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', re.I)
_RE_TW = re.compile(
    r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)', re.I)


def _foto_do_link(url: str) -> str:
    try:
        import requests
        r = requests.get(url, allow_redirects=True, timeout=15,
                         headers={"User-Agent": _UA})
        html = r.text or ""
        m = _RE_OG.search(html) or _RE_TW.search(html)
        return m.group(1) if m else ""
    except Exception as e:
        print(f"   (falhou: {str(e)[:60]})")
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
        img = _foto_do_link(it["link"])
        if img:
            it["imagem"] = img
            achou += 1
            print("OK 📷")
        else:
            print("sem foto na pagina")
        time.sleep(1.2)   # gentil com a Shopee

    _salvar_atomico(FILA, fila)
    print(f"\nPreenchi {achou}/{len(sem_foto)} fotos. Agora: python3 deploy_site.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
