#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# previa_carrossel.py — manda um carrossel pronto pro seu Telegram, pra aprovar
# antes de ele ir pro ar.
#
# ⚠️ NASCEU DE UM SCP QUE RODOU NO LUGAR ERRADO (29/08). O jeito de conferir os
# slides era `scp -r root@vps:/root/jarvis/pronto_carrossel/... ~/Downloads/`,
# digitado NO SEU MICRO. Rodado por engano dentro do SSH, ele copia a VPS pra
# ela mesma: doze linhas de "100%", zero arquivo no seu computador, e nenhum
# erro pra denunciar. O comando funcionou perfeitamente — só que na máquina
# errada, e isso não aparece na saída.
# 📌 Ferramenta que só funciona se você lembrar de qual terminal está é
# ferramenta que vai falhar num dia corrido. Aqui o carrossel vem ATÉ você.
#
# ⚠️ ISTO NÃO PUBLICA NADA. Só empurra os JPGs pro chat privado do bot. Serve
# pra decidir com o olho antes do slot valer — que é a única coisa que o log do
# dry-run não consegue dizer: ele prova que o encanamento corre, nunca que o
# slide ficou bonito.
#
# USO (na VPS, dentro de ~/jarvis):
#   .venv/bin/python previa_carrossel.py --ultimos 2
#   .venv/bin/python previa_carrossel.py pronto_carrossel/20260829_manual_pet
#   .venv/bin/python previa_carrossel.py --ultimos 6 --so-nome   # só a lista

import argparse
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PRONTO = BASE_DIR / "pronto_carrossel"

# O Telegram aceita no máximo 10 itens por álbum. Um carrossel do Instagram
# também para em 10, então os dois limites coincidem e não há o que fatiar.
MAX_ALBUM = 10


def _log(m):
    print(f"   {m}", flush=True)


def _carregar_env():
    """Mesma leitura de .env do resto do projeto — este script roda na mão,
    fora do systemd, e sem isso o token simplesmente não existe."""
    for cand in (BASE_DIR / ".env", Path(".env")):
        if not cand.exists():
            continue
        for linha in cand.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            k, v = linha.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _credenciais() -> tuple:
    """(token, chat). ⚠️ MESMA ORDEM DE PREFERÊNCIA do `_avisar` do WhatsApp:
    o chat de ALERTA vem antes do chat do grupo. Inverter isso mandaria a
    prévia — que é rascunho, com slide possivelmente torto — pro grupo dos
    clientes. É um erro de uma linha com plateia."""
    tok = (os.environ.get("TELEGRAM_BOT_TOKEN", "") or "").strip()
    chat = ((os.environ.get("TELEGRAM_ALERT_CHAT_ID")
             or os.environ.get("TELEGRAM_CHAT_ID") or "")).strip()
    return tok, chat


def _slides(pasta: Path) -> list:
    """Os JPGs numerados, em ordem. `produto_*.jpg` fica de fora: são as fotos
    de origem que o render consome, não slides."""
    return sorted(p for p in pasta.glob("*.jpg")
                  if p.stem.isdigit())


def _legenda(pasta: Path) -> str:
    """Título do plano + as primeiras linhas da legenda, pra dar contexto no
    álbum. Se não houver plano, o nome da pasta já diz nicho e formato."""
    partes = [pasta.name]
    plano = pasta / "plano.json"
    if plano.exists():
        try:
            d = json.loads(plano.read_text(encoding="utf-8"))
            fmt = d.get("formato") or d.get("format") or ""
            capa = ((d.get("slides") or [{}])[0].get("titulo") or "")
            if fmt:
                partes.append(f"formato: {fmt}")
            if capa:
                partes.append(f"capa: {capa}")
        except Exception:
            pass       # prévia sem contexto ainda é prévia; não vale falhar
    leg = pasta / "legenda.txt"
    if leg.exists():
        try:
            partes.append(leg.read_text(encoding="utf-8").strip()[:300])
        except Exception:
            pass
    return "\n".join(partes)[:1000]


def enviar(pasta: Path, tok: str, chat: str) -> bool:
    """Um álbum por carrossel. True se o Telegram aceitou."""
    fotos = _slides(pasta)
    if not fotos:
        _log(f"❌ {pasta.name}: nenhum slide numerado (01.jpg, 02.jpg…)")
        return False
    fotos = fotos[:MAX_ALBUM]
    import requests
    midia, arquivos, abertos = [], {}, []
    try:
        for i, f in enumerate(fotos):
            nome = f"s{i}"
            fh = open(f, "rb")
            abertos.append(fh)
            arquivos[nome] = fh
            item = {"type": "photo", "media": f"attach://{nome}"}
            if i == 0:
                # ⚠️ A LEGENDA VAI SÓ NO PRIMEIRO. O Telegram usa a do primeiro
                # item como legenda do álbum inteiro; repetir em todos faz o
                # texto aparecer colado em cada foto ao abrir.
                item["caption"] = _legenda(pasta)
            midia.append(item)
        r = requests.post(
            f"https://api.telegram.org/bot{tok}/sendMediaGroup",
            timeout=120,
            data={"chat_id": chat, "media": json.dumps(midia)},
            files=arquivos)
        if r.status_code == 200 and r.json().get("ok"):
            _log(f"✅ {pasta.name}: {len(fotos)} slide(s) no seu Telegram")
            return True
        # ⚠️ O CORPO DA RESPOSTA É O DIAGNÓSTICO. "chat not found" e "file too
        # big" são problemas completamente diferentes, e um status 400 pelado
        # não distingue os dois — foi assim que o `--sugerir-lotes` passou dias
        # devolvendo 0/10 sem ninguém saber que era o mime errado.
        _log(f"❌ {pasta.name}: Telegram recusou "
             f"({r.status_code}) {r.text[:200]}")
        return False
    except Exception as e:
        _log(f"❌ {pasta.name}: {type(e).__name__} {str(e)[:140]}")
        return False
    finally:
        for fh in abertos:
            try:
                fh.close()
            except Exception:
                pass


def _quando(pasta: Path) -> float:
    """Quando o CONTEÚDO desta pasta foi escrito por último.

    ⚠️ NÃO É O MTIME DA PASTA, e essa diferença mandou o carrossel errado no
    primeiro uso real (29/08). O mtime de um diretório só muda quando uma
    entrada é criada ou apagada dentro dele. O `--refazer` sobrescreve
    `01.jpg`…`07.jpg` com os MESMOS nomes: os arquivos ficam novos, o diretório
    não muda, e "a pasta mais recente" continua apontando pro carrossel antigo.
    📌 Data de pasta responde "quando a pasta nasceu", não "quando o conteúdo
    mudou" — e era a segunda pergunta que estava sendo feita."""
    try:
        return max((f.stat().st_mtime for f in pasta.glob("*.jpg")),
                   default=pasta.stat().st_mtime)
    except OSError:
        return 0.0


def _ultimos(n: int) -> list:
    """As n pastas com conteúdo mais recente, mais nova primeiro."""
    if not PRONTO.exists():
        return []
    pastas = [p for p in PRONTO.iterdir() if p.is_dir()]
    pastas.sort(key=_quando, reverse=True)
    return pastas[:max(1, n)]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Manda carrosséis prontos pro seu Telegram (não publica).")
    p.add_argument("pastas", nargs="*", help="pastas de pronto_carrossel/")
    p.add_argument("--ultimos", type=int, default=0,
                   help="pega as N pastas mais recentes em vez de nomeá-las")
    p.add_argument("--so-nome", action="store_true", dest="so_nome",
                   help="só lista o que enviaria, sem mandar nada")
    a = p.parse_args(argv)

    alvos = [Path(x) for x in a.pastas]
    if a.ultimos:
        alvos = _ultimos(a.ultimos) + alvos
    if not alvos:
        alvos = _ultimos(1)
    alvos = [x if x.is_absolute() else (BASE_DIR / x) for x in alvos]

    faltando = [x for x in alvos if not x.is_dir()]
    for x in faltando:
        _log(f"❌ não é pasta: {x}")
    alvos = [x for x in alvos if x.is_dir()]
    if not alvos:
        _log("nada pra enviar — pronto_carrossel/ está vazio?")
        return 1

    if a.so_nome:
        for x in alvos:
            _log(f"{x.name}  ({len(_slides(x))} slides)")
        return 0

    _carregar_env()
    tok, chat = _credenciais()
    if not tok or not chat:
        # 📌 Falta de credencial é erro de configuração, não "não deu certo":
        # dizer QUAL variável falta economiza a próxima meia hora.
        _log("❌ falta TELEGRAM_BOT_TOKEN e/ou "
             "TELEGRAM_ALERT_CHAT_ID/TELEGRAM_CHAT_ID no .env")
        return 2

    ok = sum(1 for x in alvos if enviar(x, tok, chat))
    _log(f"{ok}/{len(alvos)} carrossel(éis) enviado(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
