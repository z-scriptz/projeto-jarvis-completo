#!/usr/bin/env python3
# postar_grupo.py -- ALIMENTA o grupo do Telegram com os achadinhos que o Jarvis
# já validou (foto + link de afiliado). Reusa o telegram_poster (BOT oficial —
# seguro, dentro das regras) e NÃO repete produto. Faz um "drip" (poucos por
# rodada, com respiro) pra não parecer spam.
#
# Uso (VPS):  python3 postar_grupo.py [quantos]      (padrão: 3 por rodada)
# Pré-requisito: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID no .env, e o BOT precisa
#                ser ADMIN do grupo. Teste antes:
#                python3 -m integrations.telegram_poster --teste
import os
import sys
import json
import time
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
FILA = BASE_DIR / "shared" / "produtos_fila.json"
POSTADOS = BASE_DIR / "shared" / "grupo_postados.json"
MAX_PADRAO = 3          # quantos achadinhos por rodada (drip)
PAUSA_SEG = 4.0         # respiro entre posts


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


_carregar_env()

try:
    from integrations.telegram_poster import postar_achado
except Exception:
    from telegram_poster import postar_achado


def _log(m):
    print(f"[postar_grupo] {m}")


def _carregar_json(caminho, padrao):
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:
        return padrao


def _salvar_postados(links: list):
    try:
        POSTADOS.parent.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(POSTADOS.parent),
            prefix=".grp_", suffix=".tmp", delete=False)
        json.dump({"links": links}, tmp, ensure_ascii=False, indent=2)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, POSTADOS)
    except Exception as e:
        _log(f"aviso: não consegui salvar o estado ({str(e)[:60]})")


def main():
    quantos = MAX_PADRAO
    if len(sys.argv) > 1:
        try:
            quantos = max(1, int(sys.argv[1]))
        except ValueError:
            pass

    fila = _carregar_json(FILA, [])
    if not isinstance(fila, list) or not fila:
        _log("fila vazia — nada a postar")
        return 1

    estado = _carregar_json(POSTADOS, {})
    ja = set(estado.get("links", []) if isinstance(estado, dict) else [])

    # candidatos: tem link, tem foto (grupo sem foto fica feio), e ainda não postado.
    # a fila já vem "mais novo primeiro" — mantemos essa ordem (deal fresco primeiro).
    novos = [it for it in fila
             if isinstance(it, dict) and it.get("link") and it.get("imagem")
             and it["link"] not in ja]

    if not novos:
        _log("nenhum achadinho novo pra postar (todos já foram) ✔")
        return 0

    _log(f"{len(novos)} novos na fila · postando até {quantos} nesta rodada")
    postados_agora = 0
    for it in novos[:quantos]:
        produto = {
            "nome": it.get("produto", ""),
            "titulo": it.get("produto", ""),
            "preco_real": "",            # a fila do site não guarda preço
            "link": it.get("link", ""),
            "imagem": it.get("imagem", ""),
        }
        r = postar_achado(produto)
        if r.get("ok"):
            ja.add(it["link"])
            postados_agora += 1
            _log(f"   ✅ {produto['nome'][:45]}")
        else:
            _log(f"   ❌ falhou ({str(r.get('erro'))[:70]}) — paro por aqui")
            break     # erro (bot sem admin/credencial) → não insiste
        if postados_agora < quantos:
            time.sleep(PAUSA_SEG)

    if postados_agora:
        _salvar_postados(list(ja))
        _log(f"OK! {postados_agora} achadinho(s) no grupo. 🛍️")
    return 0 if postados_agora else 1


if __name__ == "__main__":
    sys.exit(main())
