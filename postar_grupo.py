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

# Janela de silêncio: oferta às 3 da manhã acorda membro e faz ele silenciar o
# canal — e canal silenciado é canal morto, mesmo com todo mundo ainda dentro.
# A trava mora aqui dentro, e não no cron, porque este script também roda na
# mão. Fora da janela ele sai limpo, sem gastar chamada de API.
# Ajustável por .env: GRUPO_HORA_INICIO / GRUPO_HORA_FIM.
JANELA_INICIO = 7       # 07:00 — antes disso, não posta
JANELA_FIM = 21         # 21:00 — a partir das 22:00, não posta


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

# Achadinho é vitrine, e vitrine é CANAL — não a comunidade, onde as pessoas
# conversam. Fila de link de afiliado num grupo de conversa afoga o assunto e
# faz o membro silenciar.
#
# O telegram_poster lê TELEGRAM_CHAT_ID uma vez, no import. Então a troca tem
# que acontecer AQUI, antes dele entrar — depois já é tarde.
#
# Sem TELEGRAM_CANAL_ID no .env, nada muda: continua indo pro CHAT_ID de
# sempre. Assim ninguém acorda com o post indo pra outro lugar sem pedir.
_CANAL = os.environ.get("TELEGRAM_CANAL_ID", "").strip()
if _CANAL:
    os.environ["TELEGRAM_CHAT_ID"] = _CANAL

try:
    from integrations.telegram_poster import postar_achado
except Exception:
    from telegram_poster import postar_achado

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
try:
    from shared.trava import travar
except Exception:                    # sem a trava, seguir é melhor que parar
    from contextlib import contextmanager

    @contextmanager
    def travar(_nome, base=None):
        yield True


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


def _faixa_horaria():
    """(inicio, fim) em horas. .env manda; valor torto cai no padrão."""
    def _h(nome, padrao):
        try:
            v = int(os.environ.get(nome, "").strip())
        except (TypeError, ValueError):
            return padrao
        return v if 0 <= v <= 23 else padrao
    return _h("GRUPO_HORA_INICIO", JANELA_INICIO), _h("GRUPO_HORA_FIM", JANELA_FIM)


def _dentro_da_janela(agora=None):
    ini, fim = _faixa_horaria()
    h = (agora or time.localtime()).tm_hour
    if ini <= fim:
        return ini <= h <= fim
    return h >= ini or h <= fim          # janela que cruza a meia-noite


def main():
    """Só deixa UMA instância trabalhar por vez.

    Em 04/08 o grupo recebeu cada achadinho 4 vezes. O código estava certo: o
    `crontab -l` é que tinha esta mesma linha repetida 4x, todas em
    `15 */2 * * *`. Os quatro processos leram o `grupo_postados.json` antes de
    qualquer um gravar, e cada um achou que os produtos eram novos.

    A limpeza do crontab resolveu o caso; a trava resolve a CLASSE. Crontab é
    editado à mão e vai duplicar de novo — quem tem que se recusar a rodar
    duas vezes é o script.
    """
    with travar("postar_grupo") as livre:
        if not livre:
            _log("outra instância já está postando — saio sem fazer nada ✔")
            return 0
        return _rodar()


def _rodar():
    quantos = MAX_PADRAO
    forcar = False
    for arg in sys.argv[1:]:
        if arg in ("--forcar", "--force"):
            forcar = True                # pra testar fora do horário
            continue
        try:
            quantos = max(1, int(arg))
        except ValueError:
            pass

    if not forcar and not _dentro_da_janela():
        ini, fim = _faixa_horaria()
        _log(f"fora da janela ({ini:02d}:00–{fim:02d}:59) — nada postado. "
             "Use --forcar pra ignorar.")
        return 0

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

    # imprime o destino: postar no chat errado é o tipo de erro que só aparece
    # quando alguém reclama, e aí já foram 3 posts
    destino = _CANAL or os.environ.get("TELEGRAM_CHAT_ID", "?")
    _log(f"destino: {destino}" + ("  (TELEGRAM_CANAL_ID)" if _CANAL
                                  else "  (TELEGRAM_CHAT_ID — sem canal definido)"))
    _log(f"{len(novos)} novos na fila · postando até {quantos} nesta rodada")
    postados_agora = 0
    for it in novos[:quantos]:
        produto = {
            "nome": it.get("produto", ""),
            "titulo": it.get("produto", ""),
            "preco_real": "",            # a fila do site não guarda preço
            "link": it.get("link", ""),
            "imagem": it.get("imagem", ""),
            "origem": it.get("origem", ""),  # p/ reetiquetar o link como 'telegram'
        }
        r = postar_achado(produto)
        if r.get("ok"):
            ja.add(it["link"])
            postados_agora += 1
            # grava A CADA post, não só no fim: se o processo morrer no meio
            # da rodada, o que já foi ao ar tem que ficar registrado, senão
            # a próxima rodada posta de novo
            _salvar_postados(list(ja))
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
