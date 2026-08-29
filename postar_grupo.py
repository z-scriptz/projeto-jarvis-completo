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

# ⚠️ A FILA NÃO ESTÁ ORDENADA POR QUALIDADE — ESTÁ ORDENADA POR CHEGADA (29/08).
# Este arquivo dizia, num comentário, que "a fila já vem mais novo primeiro" e
# postava `novos[:quantos]` confiando nisso. Os dois lados da afirmação estavam
# errados de uma vez:
#   · `piloto.py` documenta que o gravador da mineração faz `fila.insert(0, …)`
#     ~11 VEZES POR DIA, e `repescagem.py:440` faz `fila.append(…)` no outro
#     extremo. O topo é "quem chegou por último", não "o melhor";
#   · e mesmo que fosse novidade, novidade não é qualidade. O grupo recebia o
#     que a última rodada de mineração empurrou pra cima.
# O dado pra escolher direito SEMPRE ESTEVE NO ITEM: `curar_fila` copia classe,
# score, vendas e comissão pra dentro de cada entrada da fila, e ninguém aqui
# lia nenhum deles.
# 📌 Ordem herdada é ordem que ninguém escolheu: se este script quer o melhor
# produto, ele é quem tem que ordenar — não dá pra terceirizar isso pra um
# invariante que outro arquivo pode quebrar sem saber que existimos.
ORDEM_CLASSE = {"mina_ouro": 0, "ok": 1, "fraco": 2, "deserto": 3}

# ⚠️ CLASSE AUSENTE NÃO REPROVA, SÓ NÃO PROMOVE. `repescagem.py` devolve
# produtos pra fila sem `classe`, sem `score` e sem `vendas` — ele tem link,
# foto e preço e nada mais. Um corte duro por classe apagaria esses produtos do
# grupo pra sempre, em silêncio, e o log ficaria igual ao de um dia sem
# repescagem. Eles ficam ATRÁS de quem tem número, nunca fora.
SEM_CLASSE = 4


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


def _num(v) -> float:
    """Número do campo, 0 quando não dá. A fila mistura int, str e ausência."""
    try:
        return float(str(v).replace(",", ".").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def _qualidade(item: dict) -> tuple:
    """Chave de ordenação: melhor primeiro.

    A ordem é a MESMA que o `validar_fila` já usa pra classificar (classe, e
    score dentro da classe) — aqui ela não é reinventada, só é finalmente
    aplicada na hora de escolher. Vendas e comissão entram como desempate
    porque `score` empata bastante entre produtos parecidos.
    """
    classe = str(item.get("classe") or "").strip()
    return (ORDEM_CLASSE.get(classe, SEM_CLASSE),
            -_num(item.get("score")),
            -_num(item.get("vendas")),
            -_num(item.get("comissao_valor")))


def _porque(item: dict) -> str:
    """Os números que fizeram este produto subir — pra caber no log.

    ⚠️ SEM ISSO A ORDENAÇÃO É INVERIFICÁVEL. Uma lista ordenada e uma lista
    embaralhada têm exatamente a mesma aparência no log ("✅ nome do produto"),
    e foi por isso que a escolha por chegada durou tanto sem ninguém notar.
    """
    classe = str(item.get("classe") or "") or "sem classe"
    vendas, com = _num(item.get("vendas")), _num(item.get("comissao_valor"))
    partes = [classe]
    if vendas:
        partes.append(f"{vendas:.0f} vendas")
    if com:
        partes.append(f"R$ {com:.2f} com.")
    return " · ".join(partes)


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

    # ⚠️ O NOME PRECISA SERVIR PRA UM CLIENTE, e este script era o único
    # publicador que não conferia isso (29/08). A fila vem de grupos do
    # Telegram, e a divulgação do próprio canal entra nela como se fosse
    # produto: "SIGA NOSSOS CANAIS" estava lá com link real, 181 vendas e 13%
    # de comissão — classificado `mina_ouro`, ou seja, o ranking o mandaria
    # pro TOPO e o grupo receberia isso como achadinho.
    #
    # A regra mora em `shared/termos.py` e é IMPORTADA, nunca copiada — o
    # `whatsapp_playwright` já a usava, e ter meia regra em cada superfície é
    # exatamente como esse caso passou. Sem ela, não filtra: na dúvida
    # publicar é melhor que parar o grupo, e o defeito volta a ser visível.
    try:
        from shared.termos import nome_de_produto_ruim
    except Exception as e:
        _log(f"aviso: sem shared/termos ({str(e)[:60]}) — não filtro nomes")
        nome_de_produto_ruim = lambda _n: False

    # candidatos: tem link, tem foto (grupo sem foto fica feio), e ainda não postado.
    novos = [it for it in fila
             if isinstance(it, dict) and it.get("link") and it.get("imagem")
             and it["link"] not in ja]
    antes = len(novos)
    novos = [it for it in novos
             if not nome_de_produto_ruim(str(it.get("campeao")
                                             or it.get("produto") or ""))]
    if antes != len(novos):
        _log(f"{antes - len(novos)} descartado(s): o nome não serve pra "
             f"mostrar a um cliente")
    # …e o MELHOR primeiro. Ver ORDEM_CLASSE lá em cima pra por que a ordem que
    # a fila chega não serve. `sort` é estável, então produtos empatados em tudo
    # mantêm a ordem de chegada entre si — o desempate final continua sendo
    # "chegou antes", que é o único critério honesto quando não há número.
    novos.sort(key=_qualidade)

    if not novos:
        _log("nenhum achadinho novo pra postar (todos já foram) ✔")
        return 0

    # imprime o destino: postar no chat errado é o tipo de erro que só aparece
    # quando alguém reclama, e aí já foram 3 posts
    destino = _CANAL or os.environ.get("TELEGRAM_CHAT_ID", "?")
    _log(f"destino: {destino}" + ("  (TELEGRAM_CANAL_ID)" if _CANAL
                                  else "  (TELEGRAM_CHAT_ID — sem canal definido)"))
    _log(f"{len(novos)} novos na fila · postando até {quantos} nesta rodada "
         f"(os melhores primeiro)")
    for it in novos[:quantos]:
        _log(f"   → {str(it.get('campeao') or it.get('produto') or '')[:44]:46} "
             f"{_porque(it)}")
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
