#!/usr/bin/env python3
# auditoria_site.py -- por que a vitrine parou em N produtos?
#
# POR QUE EXISTE (15/08)
# O Dre: "o site tinha 130 produtos deployado, hoje dia 15/08 ainda continua
# com 130, será que tá rodando certo?"
#
# A pergunta parece "o deploy está quebrado?", mas antes dela existe uma que
# quase ninguém faz: **a vitrine deveria ter crescido?** O `deploy_site.py:297`
# publica `[p for p in produtos if p.get("link")]` — produtos da FILA que têm
# link de afiliado. Postar um vídeo não cria produto novo; quem cria é a
# MINERAÇÃO. Se ninguém minerou nada desde a última rodada, 130 é a resposta
# certa, e trocar o deploy não muda um número que já está correto.
#
# Então este script não pergunta "está rodando?". Ele mede os dois lados e
# compara:
#
#   MATÉRIA-PRIMA   quantos produtos com link existem na fila hoje
#        ↓ (health-check esconde os mortos, dedup funde itemId repetido)
#   ESPERADO        quantos o deploy_site publicaria se rodasse agora
#        ↓
#   PUBLICADO       quantos cards existem no index.html do clone
#        ↓
#   NO AR           o clone está empurrado, ou o commit ficou parado local?
#
# Cada seta que não bate tem uma causa diferente, e a última é a que o
# `revisao_geral.py` não enxerga: ele confere `git status --porcelain`, que
# fica LIMPO depois de um commit bem-sucedido. Se o push falhou, o porcelain
# está limpo, o index.html está fresco, e o site no ar está congelado — os três
# ao mesmo tempo. Aqui a checagem é `origin/HEAD..HEAD`.
#
# ⚠️ O FUNIL AQUI É SIMULADO A PARTIR DO CACHE, e é de propósito: o health-check
# de verdade bate na API da Shopee produto por produto. Rodar isso num script de
# diagnóstico gastaria centenas de requisições pra responder uma pergunta de
# contagem. O que sai daqui é "o que o cache sabe", e o script diz isso na cara.
#
# ⚠️ E A LIÇÃO QUE JÁ ESTÁ NO ROADMAP (linha 371): eu já afirmei uma vez que
# "nenhum .py chama o deploy_site, então ninguém o chama". Estava errado — ele
# roda a cada 2h por uma entrada própria do crontab, fora do bloco JARVIS-AUTO.
# Por isso o bloco 1 roda `crontab -l` de verdade, em vez de procurar no código.
#
# Não escreve nada e só usa stdlib. Faz UMA chamada de rede: `git remote
# update` no clone do site, porque comparar com um `origin/main` desatualizado
# responderia "está tudo empurrado" justamente quando não está.
#
# Uso (na VPS, dentro de ~/jarvis):
#   python3 auditoria_site.py
#   python3 auditoria_site.py --json

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SITE_REPO = Path(os.environ.get("TOPSHOP_SITE_DIR", str(Path.home() / "topshop-site")))

FALHA, ALERTA, OK, INFO = "falha", "alerta", "ok", "info"
SIMBOLO = {FALHA: "❌", ALERTA: "⚠️ ", OK: "✅", INFO: "· "}

_achados = []


def _diz(estado, msg, detalhe=""):
    _achados.append({"estado": estado, "msg": msg, "detalhe": detalhe})
    print(f"  {SIMBOLO[estado]} {msg}")
    if detalhe:
        print(f"       {detalhe}")


def _titulo(t):
    print(f"\n── {t} " + "─" * max(0, 62 - len(t)))


def _sh(cmd, cwd=None, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=str(cwd) if cwd else None)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return -1, str(e)[:120]


def _idade(p: Path) -> str:
    try:
        h = (time.time() - p.stat().st_mtime) / 3600
    except Exception:
        return "?"
    if h < 1:
        return f"{int(h * 60)}min"
    if h < 48:
        return f"{h:.0f}h"
    return f"{h / 24:.0f}d"


def _horas(p: Path):
    try:
        return (time.time() - p.stat().st_mtime) / 3600
    except Exception:
        return None


def _primeiro(*caminhos):
    for c in caminhos:
        if c.exists():
            return c
    return None


# ── 1. quem agenda ──────────────────────────────────────────────────────────
def bloco_agenda():
    """crontab -l PRIMEIRO. Procurar no código responde outra pergunta."""
    _titulo("1. quem manda o deploy_site rodar")
    cod, saida = _sh(["crontab", "-l"])
    if cod != 0:
        # ⚠️ NÃO dizer "não tem cron". Crontab ilegível é AUSÊNCIA DE MEDIÇÃO,
        # e reportá-la como zero é o erro que já me fez concluir por
        # experimento que não aconteceu. Sem leitura, não há veredito.
        _diz(ALERTA, "não consegui ler o crontab — não sei se há agendamento",
             f"{saida[:80] or 'sem saída'} · rode `crontab -l` você mesmo "
             f"antes de acreditar em qualquer conclusão deste bloco")
        return None

    linhas = [l for l in saida.splitlines()
              if "deploy_site" in l and not l.strip().startswith("#")]

    if linhas:
        _diz(OK, f"{len(linhas)} entrada(s) de cron para o deploy_site")
        for l in linhas:
            print(f"       {l.strip()[:100]}")
        if len(linhas) > 1:
            _diz(ALERTA, "MAIS DE UMA entrada — em 04/08 a duplicata rodou o "
                         "dia inteiro em paralelo",
                 "duas cópias dobram health-check e chamada de API")
    else:
        _diz(FALHA, "NENHUMA entrada de cron chama o deploy_site",
             "a vitrine só mudaria se alguém rodasse na mão — é causa "
             "suficiente pro número travado")

    cod, saida = _sh(["systemctl", "list-timers", "--all", "--no-pager"])
    if cod == 0 and "deploy" in saida.lower():
        _diz(INFO, "há também um timer systemd citando 'deploy'",
             "confira se ele e o cron não estão fazendo a mesma coisa")
    return len(linhas)


# ── 2. o log: ele rodou mesmo? ──────────────────────────────────────────────
def bloco_log():
    """Cron agendado e cron executado são coisas diferentes."""
    _titulo("2. ele rodou de fato?")
    logs = sorted(
        [p for p in (RAIZ / "logs").glob("*.log")
         if "site" in p.name or "deploy" in p.name],
        key=lambda p: p.stat().st_mtime, reverse=True) if (RAIZ / "logs").exists() else []

    if not logs:
        _diz(ALERTA, "nenhum log de deploy_site em logs/",
             "sem log, a única prova de execução é o mtime do index.html")
        return None

    alvo = logs[0]
    h = _horas(alvo)
    # a entrada roda a cada 2h; 6h de silêncio já é três rodadas perdidas
    estado = OK if (h is not None and h < 6) else ALERTA
    _diz(estado, f"{alvo.name} escrito há {_idade(alvo)}",
         "" if estado == OK else "a cada 2h significa que 3+ rodadas não "
                                 "deixaram rastro")

    try:
        linhas = alvo.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        _diz(ALERTA, f"não consegui ler {alvo.name}: {str(e)[:60]}")
        return h

    ultimas = [l for l in linhas if l.strip()][-12:]
    if ultimas:
        print("       ── últimas linhas ──")
        for l in ultimas:
            print(f"       {l[:110]}")

    # o deploy_site fala em português e diz exatamente onde parou
    texto = "\n".join(linhas[-400:])
    for marca, estado_m, leitura in (
        ("push falhou", FALHA, "COMMITOU E NÃO SUBIU — credencial/token do "
                               "clone do site. A vitrine no ar fica parada "
                               "enquanto o clone local avança"),
        ("commit falhou", FALHA, "nem commitou — repo do site em estado ruim"),
        ("site sem mudança", INFO, "rodou e não tinha o que publicar — isso é "
                                   "a vitrine CERTA, não uma falha"),
        ("nenhum produto com link", FALHA, "a fila não tem nenhum produto com "
                                           "link de afiliado"),
        ("não é um repo git", FALHA, "o clone do site sumiu do disco"),
    ):
        if marca in texto:
            _diz(estado_m, f"o log contém: “{marca}”", leitura)
    return h


# ── 3. matéria-prima: a fila ────────────────────────────────────────────────
def bloco_fila():
    """Usa a MESMA função do deploy_site quando dá — duas ideias do que é
    'produto da vitrine' é o mesmo que nenhuma."""
    _titulo("3. matéria-prima (o que a fila tem para publicar)")
    sys.path.insert(0, str(RAIZ))
    B = None
    for imp in ("creative_engine.bio_page_builder", "bio_page_builder"):
        try:
            B = __import__(imp, fromlist=["_carregar_produtos"])
            break
        except Exception:
            continue

    if B is not None and hasattr(B, "_carregar_produtos"):
        # ⚠️ A função existe e roda mesmo quando os JSONs dela não existem —
        # devolve [] sem levantar. Sem esta checagem, "arquivo no caminho
        # errado" sai impresso como "a fila está vazia", que é uma frase
        # sobre o negócio e não sobre o disco.
        fontes = [(nome, getattr(B, nome, None))
                  for nome in ("JSON_FILA", "VALIDACAO")]
        faltando = [f"{n}={c}" for n, c in fontes if c is not None and not c.exists()]
        if any(c is not None and c.exists() for _, c in fontes):
            try:
                produtos = B._carregar_produtos()
                _diz(INFO, f"lido pelo próprio bio_page_builder."
                           f"_carregar_produtos ({len(produtos)} itens)")
                if faltando:
                    _diz(INFO, "uma das fontes não existe neste host",
                         " · ".join(faltando))
            except Exception as e:
                _diz(ALERTA, f"_carregar_produtos falhou: {str(e)[:80]}")
                produtos = None
        else:
            _diz(ALERTA, "o bio_page_builder importou, mas nenhuma fonte dele "
                         "existe aqui",
                 " · ".join(faltando) + " — leitura direta a seguir")
            produtos = None
    else:
        produtos = None

    if produtos is None:
        # fallback explícito: isto é uma RELEITURA, não a função de verdade.
        fila = _primeiro(RAIZ / "shared" / "produtos_fila.json",
                         RAIZ / "produtos_fila.json")
        if not fila:
            _diz(FALHA, "não achei produtos_fila.json",
                 "sem a fila não há vitrine e não há o que auditar")
            return None
        try:
            bruto = json.loads(fila.read_text(encoding="utf-8"))
        except Exception as e:
            _diz(FALHA, f"produtos_fila.json ilegível: {str(e)[:80]}")
            return None
        produtos = [{"nome": p.get("produto", ""), "link": p.get("link", ""),
                     "plataforma": (p.get("plataforma") or "shopee").lower()}
                    for p in bruto if isinstance(p, dict)]
        _diz(ALERTA, "li a fila na mão, sem passar pelo bio_page_builder",
             "esta contagem ignora o validacao_fila.json, que o deploy real "
             "soma — o número pode sair MENOR que a vitrine de verdade")

    com = [p for p in produtos if (p.get("link") or "").strip()]
    sem = len(produtos) - len(com)
    plat = {}
    for p in com:
        k = (p.get("plataforma") or "shopee").lower()
        plat[k] = plat.get(k, 0) + 1

    _diz(OK if com else FALHA,
         f"{len(com)} produto(s) COM link · {sem} sem link (invisíveis na vitrine)",
         " · ".join(f"{k}: {v}" for k, v in sorted(plat.items())) or "")
    if sem:
        _diz(INFO, f"os {sem} sem link são produto minerado que nunca virou "
                   f"link de afiliado",
             "eles existem na fila e podem até virar vídeo, mas nunca aparecem "
             "no site")

    fila_f = _primeiro(RAIZ / "shared" / "produtos_fila.json",
                       RAIZ / "produtos_fila.json")
    if fila_f:
        h = _horas(fila_f)
        estado = ALERTA if (h is not None and h > 72) else OK
        _diz(estado, f"produtos_fila.json alterado há {_idade(fila_f)}",
             "" if estado == OK else "a fila não recebe nada há 3+ dias — se "
                                     "ela não cresce, a vitrine NÃO TEM como "
                                     "crescer")
    return com


# ── 4. o funil: quantos sobrariam ───────────────────────────────────────────
def bloco_funil(com_link):
    """Simulação a partir do cache. NÃO é o health-check: ele bate na API."""
    _titulo("4. o funil (quantos o deploy publicaria agora)")
    if com_link is None:
        _diz(INFO, "sem a fila, não dá pra simular o funil")
        return None

    cache_f = _primeiro(RAIZ / "shared" / "health_cache.json",
                        RAIZ / "health_cache.json")
    cache = {}
    if cache_f:
        try:
            cache = json.loads(cache_f.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
        h = _horas(cache_f)
        # TTL do health-check é 6h; se o cache é MAIS VELHO que isso, ou o
        # deploy não rodou, ou rodou sem conseguir checar nada
        estado = OK if (h is not None and h < 8) else ALERTA
        _diz(estado, f"health_cache.json atualizado há {_idade(cache_f)} "
                     f"({len(cache)} links)",
             "" if estado == OK else "o TTL do health-check é 6h — cache velho "
                                     "é sinal de que o deploy_site NÃO rodou, "
                                     "ou rodou sem a API de afiliado")
    else:
        _diz(ALERTA, "não achei health_cache.json",
             "sem ele o deploy re-checa tudo do zero a cada rodada")

    mortos, sem_veredito, itens = 0, 0, {}
    for p in com_link:
        link = (p.get("link") or "").strip()
        ent = cache.get(link) or {}
        if ent.get("estado") == "morto":
            mortos += 1
            continue
        if not ent:
            sem_veredito += 1
        item = (ent.get("item") or "").strip()
        # sem itemId conhecido o produto não tem como ser fundido com outro:
        # conta como identidade própria, que é o que o dedup real faz
        itens.setdefault(item or f"?{link}", []).append(p)

    esperado = len(itens)
    fundidos = sum(len(v) - 1 for v in itens.values() if len(v) > 1)

    print(f"       {len(com_link):>4} com link na fila")
    print(f"       {-mortos:>4} escondidos (health-check disse MORTO)")
    print(f"       {-fundidos:>4} fundidos (mesmo itemId, dois links)")
    print(f"       {'':>4} " + "─" * 30)
    print(f"       {esperado:>4} CARDS ESPERADOS na vitrine")
    if sem_veredito:
        _diz(INFO, f"{sem_veredito} link(s) sem veredito no cache",
             "contei como vivos, que é o que o deploy faz na dúvida — mas o "
             "número real pode cair um pouco depois do próximo health-check")
    return esperado


# ── 5. o que está publicado, e se subiu ─────────────────────────────────────
def bloco_publicado(esperado):
    _titulo("5. o clone do site (publicado e no ar)")
    if not (SITE_REPO / ".git").exists():
        _diz(FALHA, f"{SITE_REPO} não é um repo git",
             "o deploy_site aborta na primeira linha do main() — nunca "
             "publicou nada desde que isso aconteceu")
        return None

    idx = SITE_REPO / "index.html"
    cards = None
    if idx.exists():
        h = _horas(idx)
        estado = ALERTA if (h is not None and h > 72) else OK
        _diz(estado, f"index.html gerado há {_idade(idx)}",
             "" if estado == OK else "vitrine parada")
        try:
            html = idx.read_text(encoding="utf-8", errors="replace")
            cards = len(re.findall(r'<a class="card"', html))
            _diz(OK if cards else FALHA, f"{cards} card(s) no index.html")
        except Exception as e:
            _diz(ALERTA, f"não consegui ler o index.html: {str(e)[:60]}")
    else:
        _diz(FALHA, "index.html não existe no clone")

    cod, sujo = _sh(["git", "status", "--porcelain"], cwd=SITE_REPO)
    if cod == 0 and sujo:
        _diz(ALERTA, f"{len(sujo.splitlines())} arquivo(s) modificado(s) e não "
                     f"commitado(s)")

    # ⚠️ ESTE É O PONTO CEGO DO revisao_geral: depois de um commit bem-sucedido
    # o porcelain fica LIMPO. Se o push falhou, tudo parece em ordem aqui
    # embaixo e a vitrine no ar está congelada mesmo assim.
    _sh(["git", "remote", "update"], cwd=SITE_REPO, timeout=30)
    cod, pendentes = _sh(["git", "rev-list", "--count", "@{u}..HEAD"],
                         cwd=SITE_REPO)
    if cod == 0 and pendentes.isdigit():
        n = int(pendentes)
        if n:
            _diz(FALHA, f"{n} commit(s) COMMITADOS E NÃO EMPURRADOS",
                 "é exatamente este o caso em que tudo parece certo na VPS e o "
                 "site no ar está parado. Causa quase sempre: credencial/token "
                 "do push expirada")
        else:
            _diz(OK, "clone em dia com o origin (nada preso pra subir)")
    else:
        _diz(ALERTA, "não consegui comparar com o origin",
             (pendentes or "")[:90] + " — sem upstream configurado?")

    cod, log = _sh(["git", "log", "-3", "--format=%h %ad %s", "--date=short"],
                   cwd=SITE_REPO)
    if cod == 0 and log:
        print("       ── últimos commits do site ──")
        for l in log.splitlines():
            print(f"       {l[:100]}")

    if cards is not None and esperado is not None:
        print()
        if esperado > cards:
            _diz(FALHA, f"ESPERADO {esperado} × PUBLICADO {cards} "
                        f"(faltam {esperado - cards})",
                 "a fila tem produto que a vitrine não mostra — o deploy não "
                 "rodou, ou rodou e não conseguiu subir")
        elif esperado < cards:
            _diz(ALERTA, f"ESPERADO {esperado} × PUBLICADO {cards} "
                         f"({cards - esperado} a mais no site)",
                 "o site mostra produto que a fila não tem mais — dedup ou "
                 "health-check derrubariam esses na próxima rodada")
        else:
            _diz(OK, f"ESPERADO {esperado} × PUBLICADO {cards} — batem",
                 "o deploy está fazendo o trabalho dele. O número não cresce "
                 "porque a FILA não cresce, não porque o site quebrou")
    return cards


def veredito(n_cron, h_log, esperado, cards):
    _titulo("veredito")
    problemas = [a for a in _achados if a["estado"] == FALHA]

    # o que NÃO foi medido vem antes do veredito: conclusão apoiada em bloco
    # que não leu nada é chute com formatação bonita
    cegos = []
    if n_cron is None:
        cegos.append("o agendamento (crontab ilegível)")
    if h_log is None:
        cegos.append("a execução (nenhum log de deploy_site)")
    if esperado is None:
        cegos.append("o funil (fila não lida)")
    if cards is None:
        cegos.append("o publicado (index.html não lido)")
    if cegos:
        print("  ⚠️  NÃO MEDIDO nesta rodada: " + " · ".join(cegos))
        print("      O que segue vale só para o que deu pra ler.\n")

    if not problemas:
        print("  Nenhuma falha. Se o número está parado e nada aqui acusou,")
        print("  a vitrine está CERTA e o congelamento é da MINERAÇÃO:")
        print("  produto novo com link de afiliado é o que faz o site crescer,")
        print("  e postar vídeo dos produtos que já estão lá não faz.")
        print()
        print("  Onde olhar então:  repescagem.py · validar_fila.py ·")
        print("                     amazon_playwright.py · tiktok_coletor.py")
        return 0

    print(f"  {len(problemas)} problema(s) que explicam a vitrine parada:")
    for a in problemas:
        print(f"    ❌ {a['msg']}")
        if a["detalhe"]:
            print(f"       {a['detalhe']}")
    return 1


def main():
    p = argparse.ArgumentParser(
        description="Por que a vitrine parou no mesmo número de produtos?")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    print("\n" + "═" * 68)
    print("  AUDITORIA DA VITRINE — topshopoficial.com.br")
    print(f"  {time.strftime('%d/%m/%Y %H:%M')} · clone: {SITE_REPO}")
    print("═" * 68)

    n_cron = bloco_agenda()
    h_log = bloco_log()
    com_link = bloco_fila()
    esperado = bloco_funil(com_link)
    cards = bloco_publicado(esperado)
    cod = veredito(n_cron, h_log, esperado, cards)

    if args.json:
        print("\n" + json.dumps(
            {"esperado": esperado, "publicado": cards,
             "com_link_na_fila": len(com_link) if com_link is not None else None,
             "entradas_cron": n_cron, "achados": _achados},
            ensure_ascii=False, indent=2))
    print()
    return cod


if __name__ == "__main__":
    sys.exit(main())
