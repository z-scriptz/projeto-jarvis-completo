#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""teste_producao_guardada.py -- a TERCEIRA intenção, e o que ela expõe.

⚠️ ESTE TESTE EXISTE PARA DOCUMENTAR UMA LACUNA, não só para provar acerto.

A produção de vídeo foi instrumentada porque testa três coisas que a poda de
fontes e a resposta a comentário não testam:

    volume          60 ciclos/hora
    efeito parcial  pedir 4 e sair 2 não é sucesso nem falha
    custo           a primeira ação com dinheiro atrelado

E a terceira asserção desta lista é desconfortável de propósito: ela prende o
comportamento ATUAL de um caso que a ESCOPO ainda não sabe representar bem.
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


print("\n🔒 ESCOPO × produção de vídeo — a terceira intenção\n")
tmp = Path(tempfile.mkdtemp(prefix="escopo_prod_"))
os.environ["ESCOPO_ATIVO"] = "1"
os.environ["ESCOPO_DADOS"] = str(tmp / "dados")
os.environ["ESCOPO_POLITICAS"] = str(BASE / "politicas")

import escopo_jarvis as ej                                        # noqa: E402
from escopo import Estado                                         # noqa: E402

# A esteira de mentira: PRONTO_DIR aponta para o tmp, e cada "produção"
# bem-sucedida cria a pasta com o video.mp4 dentro.
esteira = tmp / "pronto_para_postar"
esteira.mkdir(parents=True)
ej.PRONTO_DIR = esteira


class SlugSimples:
    """A régua do renderizador, de mentira mas com a MESMA assinatura."""

    @staticmethod
    def _slugify(nome):
        return (nome or "").strip().lower().replace(" ", "-")


def instalar_slug(funciona=True):
    """`produzir_tiktok` não existe no ambiente de teste; injeta um substituto."""
    import types
    mod = types.ModuleType("produzir_tiktok")
    if funciona:
        mod.H = SlugSimples
    sys.modules["produzir_tiktok"] = mod


instalar_slug()


def produzir_de_verdade(nomes):
    """Cria o pacote na esteira — é o que 'o mundo mudou' significa aqui."""
    for n in nomes:
        d = esteira / SlugSimples._slugify(n)
        d.mkdir(parents=True, exist_ok=True)
        (d / "video.mp4").write_text("x", encoding="utf-8")


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


PROC_OK = {"estado": "OK", "fonte": "validacao_fila.json", "em": 1_700_000_000.0,
           "hash": "sha256:" + "ab" * 32}


def guardada(produtos, sai_certo=True, procedencia=None):
    """Monta a função guardada como o daemon monta, sem importar o daemon."""
    @ej.guarda(
        agente="jarvis.producao", acao="video.create",
        alvos=lambda produtos: [p["nome"] for p in produtos],
        custo=lambda produtos: float(len(produtos)) * 2.5,
        evidencias=lambda produtos: {
            "fila_de_produtos": dict(procedencia if procedencia is not None
                                     else PROC_OK)},
        contexto=lambda resultado, intencao: {
            "alvos": list(intencao.alvos),
            "produzidos": (resultado or {}).get("produzidos", 0)},
    )
    def _produzir(produtos):
        nomes = [p["nome"] for p in produtos]
        feitos = nomes if sai_certo else nomes[:len(nomes) // 2]
        produzir_de_verdade(feitos)
        return {"produzidos": len(feitos), "pedidos": len(nomes),
                "entraram": feitos,
                "falharam": [n for n in nomes if n not in feitos]}

    return _produzir(produtos=produtos)


def prods(n, inicio=0):
    return [{"nome": f"produto {i:02d}", "comissao_valor": 3.0}
            for i in range(inicio, inicio + n)]


# ── 1 · o caminho feliz ───────────────────────────────────────────────────
secao("1 · 4 pedidos, 4 na esteira → VERIFIED")

r = guardada(prods(4))
vale(r["produzidos"] == 4, f"a produção acontece igual, veio {r}")
esc = drenar()
a = ultima_acao(esc)
vale(a.body["verdict"]["decision"] == "ALLOW",
     f"4 vídeos é lote normal → ALLOW, veio {a.body['verdict']['decision']}")
vale(esc.estado(a.hash) is Estado.VERIFICADO,
     f"os 4 pacotes existem no disco → VERIFIED, deu "
     f"{esc.estado(a.hash).value}")
vale(a.body["intent"]["cost"] == 10.0,
     f"⚠️ PRIMEIRA AÇÃO COM CUSTO NO RECIBO: 4 × 2.5 = 10.0, veio "
     f"{a.body['intent'].get('cost')!r}")

# ── 2 · o teste que existe para expor a lacuna ────────────────────────────
secao("2 · ⚠️ 4 pedidos, 2 na esteira — nem sucesso nem falha")

r = guardada(prods(4, inicio=10), sai_certo=False)
vale(r["produzidos"] == 2, f"metade entrou, veio {r['produzidos']}")
esc = drenar()
a = ultima_acao(esc)
estado = esc.estado(a.hash)
prova = [x for x in esc.livro.ler() if x.kind == "verification"][-1].body["proof"]

vale(estado is Estado.FALHOU,
     f"⚠️ HOJE ISTO DÁ FAILED, e está tecnicamente certo: a asserção "
     f"`produzidos == 4` foi contradita pela fonte de verdade. Deu "
     f"{estado.value}")
vale(prova["evidence"]["produzidos"] == 2
     and prova["evidence"]["pedidos"] == 4,
     f"⚠️ MAS A INFORMAÇÃO PARCIAL NÃO SE PERDE: a evidência da prova guarda "
     f"2 de 4. O que falta é o ESTADO saber representar isso — hoje ele é "
     f"binário. veio {prova['evidence']}")
vale(len(prova["evidence"]["confirmados"]) == 2
     and len(prova["evidence"]["faltando"]) == 2,
     f"e nomeia os dois lados: {prova['evidence']}")
vale("produto 12" in prova["evidence"]["faltando"],
     f"⚠️ NOMEAR QUEM FALTOU é o que faz o recibo servir: '2 de 4' manda "
     f"procurar, 'faltou o produto X' manda consertar. {prova['evidence']}")

# ── 3 · fila ilegível não pode virar "não tinha produto" ──────────────────
secao("3 · 🔥 fila que não pôde ser lida → HOLD, não ALLOW")

r = guardada(prods(2, inicio=20),
             procedencia={"estado": "UNAVAILABLE",
                          "fonte": "validacao_fila.json",
                          "em": 1_700_000_000.0,
                          "erro": "JSONDecodeError: linha 4"})
esc = drenar()
a = ultima_acao(esc)
v = a.body["verdict"]
vale(v["decision"] == "HOLD",
     f"⚠️ sem saber se a fila foi lida, a produção não pode ser julgada — "
     f"veio {v['decision']}")
vale(v["rule"] == "evidencia_indisponivel",
     f"e o recibo diz que foi FALTA DE EVIDÊNCIA: {v['rule']!r}")
vale("fila_de_produtos" in v["reason"],
     f"nomeando qual evidência faltou: {v['reason'][:90]!r}")

# ── 4 · os limites do lote ────────────────────────────────────────────────
secao("4 · lote grande → HOLD, lote absurdo → DENY")

guardada(prods(9, inicio=30))
esc = drenar(1)
vale(ultima_acao(esc).body["verdict"]["rule"] == "lote_grande",
     "9 vídeos deveria casar `lote_grande`")

guardada(prods(25, inicio=50))
esc = drenar(1)
v = ultima_acao(esc).body["verdict"]
vale(v["decision"] == "DENY" and v["rule"] == "lote_absurdo",
     f"⚠️ 25 vídeos é config errada ou laço, e o DENY tem que vir ANTES do "
     f"HOLD na ordem do arquivo. veio {v['decision']}/{v['rule']}")

# ── 5 · a régua do slug tem que levantar, nunca devolver "" ───────────────
secao("5 · ⚠️ slug incalculável é INVERIFICAVEL, não 'não produziu'")

instalar_slug(funciona=False)                    # o renderizador some
guardada(prods(2, inicio=70))
esc = drenar()
a = ultima_acao(esc)
vale(esc.estado(a.hash) is Estado.INVERIFICAVEL,
     f"⚠️ sem a régua do renderizador, QUALQUER busca na esteira acha nada — "
     f"e 'achei nada' seria lido como 'não produziu'. Tem que ser "
     f"UNVERIFIABLE, deu {esc.estado(a.hash).value}")
prova = [x for x in esc.livro.ler() if x.kind == "verification"][-1].body["proof"]
vale("slug" in prova["reason"],
     f"e o motivo tem que dizer que foi a régua: {prova['reason'][:80]!r}")
instalar_slug(True)

integra, probs = esc.integro()
vale(integra, f"a cadeia tem que fechar no fim de tudo: {probs}")

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + "─" * 70)
if FALHAS:
    print(f"❌ {len(FALHAS)} falha(s) · {OK} asserção(ões) ok")
    for f in FALHAS:
        print(f"   · {f}")
    sys.exit(1)
print(f"✅ {OK}/{OK} asserções")
print("\n📌 a terceira intenção já entregou o que foi buscar:")
print("   pedir 4 e sair 2 é um fato que o ESTADO ainda não representa.")
print("   a evidência guarda; a semântica não. → `Partial Effect`\n")
