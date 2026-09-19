#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""teste_carrossel_guardado.py -- a QUARTA intenção, e a primeira com plateia.

⚠️ As três anteriores mexem em arquivo no disco da VPS. Esta publica em seis
perfis reais do Instagram. Errar aqui não é perder um recibo — é aparecer
errado para as pessoas.

📌 E é a que mais se parece com o produto: o agendador decide pelo
`r.get("ok")`, que é o AGENTE afirmando. O que prova é o `media_id` existir no
Graph da Meta. O log do Jarvis já dizia `5 publicado(s) · 1 sem sair` meses
antes de existir um estado para isso.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

OK = 0
FALHAS = []


def vale(cond, msg):
    global OK
    if cond:
        OK += 1
    else:
        FALHAS.append(msg)
        print(f"   ❌ {msg}")


def secao(t):
    print(f"\n── {t} " + "─" * max(0, 62 - len(t)))


print("\n🔒 ESCOPO × carrossel — a quarta intenção, com plateia\n")
tmp = Path(tempfile.mkdtemp(prefix="escopo_carr_"))
os.environ["ESCOPO_ATIVO"] = "1"
os.environ["ESCOPO_DADOS"] = str(tmp / "dados")
os.environ["ESCOPO_POLITICAS"] = str(BASE / "politicas")
os.environ["FACEBOOK_PAGE_TOKEN"] = "tok_de_teste"

import escopo_jarvis as ej                                         # noqa: E402
from actrova import Estado                                         # noqa: E402

CONTAS = ["geral", "beleza", "casa", "tech", "pet", "moda"]

# O Graph de mentira: media_id → existe ou não. "CAI" derruba a consulta.
NO_AR = set()


def graph(media_id, token):
    if media_id == "CAI":
        raise RuntimeError("500 da Meta")
    if media_id in NO_AR:
        return {"id": media_id, "permalink": f"https://instagram.com/p/{media_id}"}
    return {}                     # a Meta respondeu, e não tem essa mídia


ej._construir().registrar_verificador(ej.VerificadorCarrossel(buscar=graph))

PROC_OK = {"estado": "OK", "fonte": "carrossel_historico.json",
           "em": 1_700_000_000.0, "hash": "sha256:" + "cd" * 32}


def drenar(vezes=4):
    esc = ej._construir()
    for _ in range(vezes):
        ej.processar_verificacoes()
        if esc.fila.caminho.exists():
            itens = json.loads(esc.fila.caminho.read_text(encoding="utf-8")
                               or "[]")
            for it in itens:
                it["proxima_em"] = 0
            esc.fila.caminho.write_text(json.dumps(itens), encoding="utf-8")
    return esc


def ultima_acao(esc):
    return [r for r in esc.livro.ler() if r.kind == "action"][-1]


def publicar(contas, midias, procedencia=None, dry_run=False):
    """Reproduz `_publicar_contas` guardada, sem importar o agendador inteiro."""
    @ej.guarda(
        agente="jarvis.carrossel", acao="post.publish",
        alvos=lambda contas: list(contas),
        evidencias=lambda contas: {
            "historico_do_carrossel": dict(
                procedencia if procedencia is not None else PROC_OK)},
        contexto=lambda resultado, intencao: {
            "alvos": list(intencao.alvos),
            "midias": dict((resultado or {}).get("midias") or {}),
            "dry_run": bool((resultado or {}).get("dry_run"))},
    )
    def _publicar(contas):
        return {"feitos": [c for c in contas if c in midias],
                "falhas": [c for c in contas if c not in midias],
                "midias": dict(midias), "dry_run": dry_run}

    return _publicar(contas=contas)


# ── 1 · o caminho feliz ───────────────────────────────────────────────────
secao("1 · 6 contas, 6 posts no ar → VERIFIED")

NO_AR.clear()
midias = {c: f"mid_{c}" for c in CONTAS}
NO_AR.update(midias.values())
publicar(CONTAS, midias)
esc = drenar()
a = ultima_acao(esc)
vale(a.body["verdict"]["decision"] == "ALLOW",
     f"6 contas é o inventário conhecido → ALLOW, veio "
     f"{a.body['verdict']['decision']}")
vale(esc.estado(a.hash) is Estado.VERIFICADO,
     f"os 6 media_id existem no Graph → VERIFIED, deu "
     f"{esc.estado(a.hash).value}")

# ── 2 · 🔥 o caso que o log do Jarvis já mostrava todo dia ────────────────
secao("2 · 🔥 `5 publicado(s) · 1 sem sair` → PARTIAL, com os números")

NO_AR.clear()
midias = {c: f"m2_{c}" for c in CONTAS if c != "moda"}
NO_AR.update(midias.values())
publicar(CONTAS, midias)
esc = drenar()
a = ultima_acao(esc)
prova = [r for r in esc.livro.ler() if r.kind == "verification"][-1].body["proof"]

vale(esc.estado(a.hash) is Estado.PARCIAL,
     f"⚠️ 5 de 6 é PARTIAL — e o log do Jarvis dizia exatamente isso meses "
     f"antes de existir um estado para representá-lo. Deu "
     f"{esc.estado(a.hash).value}")
vale(prova["tally"] == {"requested": 6, "confirmed": 5, "failed": 1,
                        "unknown": 0},
     f"e os números batem com a linha do log: {prova.get('tally')}")
vale(prova["evidence"]["sem_midia"] == ["moda"],
     f"⚠️ NOMEANDO QUEM NÃO SAIU: `1 sem sair` manda procurar, `moda` manda "
     f"consertar. veio {prova['evidence'].get('sem_midia')}")

# ── 3 · 🔥 a diferença que é o produto inteiro ────────────────────────────
secao("3 · 🔥 a API disse OK e o post NÃO está no ar")

NO_AR.clear()
# ⚠️ O agendador recebeu `ok: True` e um media_id para as 6 contas. Do ponto de
# vista dele, foi um slot perfeito. Mas o Graph não tem nenhuma das mídias.
midias = {c: f"m3_{c}" for c in CONTAS}
r = publicar(CONTAS, midias)
vale(len(r["feitos"]) == 6 and not r["falhas"],
     f"⚠️ o AGENTE reporta 6 de 6 publicados, sem uma falha: {r['feitos']}")
esc = drenar()
a = ultima_acao(esc)
vale(esc.estado(a.hash) is Estado.FALHOU,
     f"⚠️ A LINHA DESTA SEÇÃO: a Meta não tem nenhum desses posts. `ok` é o "
     f"agente dizendo que publicou; quem prova é o Graph. O recibo diz FAILED "
     f"enquanto o log do Jarvis diria '6 publicado(s)'. Deu "
     f"{esc.estado(a.hash).value}")

# ── 4 · 🔥 o histórico ilegível republica em seis contas reais ────────────
secao("4 · 🔥 histórico ilegível → HOLD, não 'ainda não saiu'")

NO_AR.clear()
publicar(CONTAS, {}, procedencia={
    "estado": "UNAVAILABLE", "fonte": "carrossel_historico.json",
    "em": 1_700_000_000.0, "erro": "JSONDecodeError: linha 12"})
esc = drenar(1)
v = ultima_acao(esc).body["verdict"]
vale(v["decision"] == "HOLD" and v["rule"] == "evidencia_indisponivel",
     f"⚠️ `_hist()` devolvia {{}} em qualquer falha, e {{}} faz `_devido()` "
     f"achar que o slot não saiu — republicando nas seis contas. Sem a "
     f"evidência declarada, cegueira é indistinguível de primeira vez. "
     f"veio {v['decision']}/{v['rule']}")
vale("historico_do_carrossel" in v["reason"],
     f"nomeando qual evidência faltou: {v['reason'][:80]!r}")

# ── 5 · uma conta cega não apaga a evidência das outras ───────────────────
secao("5 · ⚠️ Graph fora para UMA conta ≠ post não publicado")

NO_AR.clear()
midias = {c: f"m5_{c}" for c in CONTAS}
midias["pet"] = "CAI"                       # a consulta desta conta explode
NO_AR.update(v for k, v in midias.items() if k != "pet")
publicar(CONTAS, midias)
esc = drenar()
a = ultima_acao(esc)
prova = [r for r in esc.livro.ler() if r.kind == "verification"][-1].body["proof"]
vale(prova["tally"] == {"requested": 6, "confirmed": 5, "failed": 0,
                        "unknown": 1},
     f"⚠️ a conta cega vai para `unknown`, NÃO para `failed`: somar as duas "
     f"daria um número redondo e mentiroso. veio {prova.get('tally')}")
vale(esc.estado(a.hash) is Estado.PARCIAL,
     f"5 confirmados e 1 incerto é PARTIAL, deu {esc.estado(a.hash).value}")
vale("NÃO estão sendo chamados de falha" in prova["reason"],
     f"⚠️ e o motivo tem que DIZER isso — PARTIAL sozinho não distingue "
     f"'1 falhou' de '1 não deu pra conferir': {prova['reason']!r}")

# ── 6 · dry-run não pode virar VERIFIED ───────────────────────────────────
secao("6 · dry-run: nada publicado é o resultado CERTO")

NO_AR.clear()
publicar(CONTAS, {}, dry_run=True)
esc = drenar()
a = ultima_acao(esc)
vale(esc.estado(a.hash) is Estado.INVERIFICAVEL,
     f"⚠️ em dry-run nada foi publicado — e isso está certo. Mas não há post "
     f"para conferir, então UNVERIFIABLE. Dizer VERIFIED seria afirmar sobre "
     f"um post que não existe. Deu {esc.estado(a.hash).value}")

integra, probs = esc.integro()
vale(integra, f"a cadeia tem que fechar: {probs}")

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + "─" * 70)
if FALHAS:
    print(f"❌ {len(FALHAS)} falha(s) · {OK} asserção(ões) ok")
    for f in FALHAS:
        print(f"   · {f}")
    sys.exit(1)
print(f"✅ {OK}/{OK} asserções")
print("\n📌 a quarta intenção é a ESCOPO em uma frase:")
print("   o agente disse 6 publicados. A Meta confirma 5.")
print("   e o recibo prova a diferença.\n")
