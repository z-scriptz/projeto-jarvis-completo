#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""teste_enforce_jarvis.py -- ligar o bloqueio não pode derrubar o Jarvis.

🔥 O QUE ESTE ARQUIVO IMPEDE. Antes de 22/09, virar
`politicas/jarvis.ceo.source.disable.yaml` para `modo: enforce` teria
quebrado o `ceo_agent` em dois lugares:

    ceo_agent.py:1037   try/except PodaSemEvidencia   ← não pegava AcaoBloqueada
    ceo_agent.py:1079   sem try/except NENHUM         ← CEO_PODA_AUTO=1

O segundo é o grave: uma poda de 6 fontes levantaria `AcaoBloqueada`, a
exceção subiria, e **a geração do relatório inteiro do CEO morreria junto**
— incluindo as partes que não têm nada a ver com poda.

⚠️ Camada de controle que derruba a aplicação que ela protege é pior que
camada nenhuma. Ligar enforcement sem preparar quem chama seria exatamente
isso, no nosso próprio sistema, com a nossa própria ferramenta.

    python3 teste_enforce_jarvis.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

os.environ.pop("ESCOPO_ENFORCEMENT", None)
os.environ.pop("ESCOPO_ENFORCEMENT_MOTIVO", None)

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


tmp = Path(tempfile.mkdtemp(prefix="enf_jarvis_"))
_n = [0]


def montar(modo: str):
    """Um Escopo com a política REAL do repositório, no modo pedido."""
    _n[0] += 1
    base = tmp / f"c{_n[0]}"
    pol = base / "politicas"
    pol.mkdir(parents=True)
    for y in (BASE / "politicas").glob("*.yaml"):
        texto = y.read_text(encoding="utf-8")
        if y.name == "jarvis.ceo.source.disable.yaml":
            texto = texto.replace("\nmodo: observe\n", f"\nmodo: {modo}\n")
            texto = texto.replace("\nmodo: enforce\n", f"\nmodo: {modo}\n")
        (pol / y.name).write_text(texto, encoding="utf-8")

    for m in list(sys.modules):
        if m in {"escopo_jarvis", "ceo_agent"}:
            del sys.modules[m]
    os.environ["ESCOPO_ATIVO"] = "1"
    os.environ["ESCOPO_POLITICAS"] = str(pol)
    os.environ["ESCOPO_DADOS"] = str(base / "d")
    import escopo_jarvis as ej
    import ceo_agent as ca
    ca.guarda = ej.guarda
    ca.AcaoBloqueada = ej.AcaoBloqueada
    return ej, ca


def carimbar(mod):
    """O carimbo de procedência que `_vendas_por_fonte()` deixa em produção.

    ⚠️ SEM ISTO O BLOQUEIO ACONTECE PELO MOTIVO ERRADO, e a primeira versão
    deste arquivo caiu nisso: o portão de evidência dispara ANTES das regras
    — por desenho, porque avaliar `quantidade > 5` em cima de um número
    calculado sem dado é o bug original com outra roupa. O teste via
    `AcaoBloqueada` e achava que estava provando a regra `lote_destrutivo`,
    quando estava provando `evidencia_indisponivel`.

    📌 Em produção quem carimba é quem foi buscar o dado. Aqui a fixture
    precisa fazer o mesmo, senão ela testa outra coisa."""
    import time as _t
    mod._PROCEDENCIA_VENDAS = {
        "estado": "OK", "fonte": "shopee.conversionReport",
        "em": _t.time(), "hash": "sha256:" + "ab" * 32,
    }
    return mod


def fontes(n: int) -> list:
    """`n` fontes MORTAS, com evidência de venda consultada."""
    return [{"fonte": f"morta_{i:02d}", "posts": 9, "vendas": 0,
             "comissao": 0.0, "veredito": "MORTA", "venda_conhecida": True}
            for i in range(n)]


print("\n🛑 enforce no Jarvis — sem derrubar o Jarvis\n")

# ── 1 · o modo que roda hoje ──────────────────────────────────────────────
secao("1 · observe: 6 fontes passam, e o recibo registra o HOLD")

ej, ca = montar("observe")
perfis = tmp / "p1.txt"
perfis.write_text("\n".join(f"@morta_{i:02d} #pet" for i in range(10)) + "\n",
                  encoding="utf-8")
ca.TIKTOK_PERFIS, ca.IG_PERFIS = perfis, tmp / "nada.txt"
carimbar(ca)

podados = ca._podar_fontes(fontes(6), executar=True)
vale(len(podados) == 6,
     f"⚠️ em observe a poda ACONTECE mesmo com o veredito HOLD — é assim "
     f"que se descobre onde o limite deve ficar antes de ligar. "
     f"Podou {len(podados)}")

# ── 2 · 🔥 enforce barra, e NÃO escreve nada ──────────────────────────────
secao("2 · 🔥 enforce: 6 fontes são barradas")

ej, ca = montar("enforce")
perfis2 = tmp / "p2.txt"
perfis2.write_text("\n".join(f"@morta_{i:02d} #pet" for i in range(10)) + "\n",
                   encoding="utf-8")
ca.TIKTOK_PERFIS, ca.IG_PERFIS = perfis2, tmp / "nada.txt"
carimbar(ca)

bloqueou = None
try:
    ca._podar_fontes(fontes(6), executar=True)
except ej.AcaoBloqueada as e:
    bloqueou = e

vale(bloqueou is not None, "levantou AcaoBloqueada")
vale(bloqueou.veredito.regra == "lote_destrutivo",
     f"🔥 E É A REGRA CERTA: `lote_destrutivo`, a que existe por causa das 36\n"
     f"      fontes de 14/09. Veio {getattr(bloqueou.veredito, 'regra', '?')}")
vale("PODADO CEO" not in perfis2.read_text(encoding="utf-8"),
     "🔥 E NADA FOI ESCRITO NO ARQUIVO DE PERFIL. O efeito não aconteceu — "
     "é a primeira vez que este projeto impede em vez de só registrar")

# ── 3 · o que está abaixo do limite continua passando ─────────────────────
secao("3 · ⚠️ enforce não é 'barra tudo'")

ej, ca = montar("enforce")
perfis3 = tmp / "p3.txt"
perfis3.write_text("\n".join(f"@morta_{i:02d} #pet" for i in range(10)) + "\n",
                   encoding="utf-8")
ca.TIKTOK_PERFIS, ca.IG_PERFIS = perfis3, tmp / "nada.txt"
carimbar(ca)

podados = ca._podar_fontes(fontes(3), executar=True)
vale(len(podados) == 3,
     f"⚠️ 3 fontes estão dentro do limite e a poda acontece. Um teste que só\n"
     f"      olha o bloqueio passaria com uma camada que barra TUDO, e isso\n"
     f"      seria pior do que não ter camada. Podou {len(podados)}")

# ── 4 · 🔥 O RELATÓRIO NÃO PODE MORRER JUNTO ──────────────────────────────
secao("4 · 🔥 o ponto que não tinha `try` nenhum")

import inspect                                                  # noqa: E402
fonte_do_relatorio = inspect.getsource(ca)
trecho = fonte_do_relatorio[fonte_do_relatorio.index("CEO_PODA_AUTO"):]
trecho = trecho[:trecho.index("bloco_resultados")]
vale("except AcaoBloqueada" in trecho,
     "🔥 O CAMINHO AUTOMÁTICO (CEO_PODA_AUTO=1) NÃO TINHA TRY NENHUM. Com o\n"
     "      contrato em enforce, um bloqueio de 6 fontes derrubaria a geração\n"
     "      do relatório INTEIRO do CEO — as partes de alcance, produção e\n"
     "      resultados junto, que não têm nada a ver com poda.")
vale("except PodaSemEvidencia" in trecho,
     "📌 e o `PodaSemEvidencia` entrou junto: ele também subia dali, e a\n"
     "      única razão de nunca ter derrubado nada é que o caminho\n"
     "      automático raramente rodava com a consulta falhando")

# ── 5 · o freio de mão funciona no Jarvis também ──────────────────────────
secao("5 · ESCOPO_ENFORCEMENT=0 destrava sem editar contrato")

os.environ["ESCOPO_ENFORCEMENT"] = "0"
os.environ["ESCOPO_ENFORCEMENT_MOTIVO"] = "teste: destravando de propósito"
try:
    ej, ca = montar("enforce")
    perfis5 = tmp / "p5.txt"
    perfis5.write_text("\n".join(f"@morta_{i:02d} #pet" for i in range(10))
                       + "\n", encoding="utf-8")
    ca.TIKTOK_PERFIS, ca.IG_PERFIS = perfis5, tmp / "nada.txt"
    carimbar(ca)
    podados = ca._podar_fontes(fontes(6), executar=True)
    vale(len(podados) == 6,
         "⚠️ às 3h da manhã, com o bloqueio atrapalhando, dá para destravar "
         "sem deploy")
    esc = ej._construir()
    r = [x for x in esc.livro.ler() if x.kind == "action"][-1]
    vale("ENFORCEMENT DESLIGADO" in r.body["verdict"].get("reason", "")
         and "de propósito" in r.body["verdict"].get("reason", ""),
         f"📌 e o recibo guarda que alguém desligou E por quê — o freio deixa "
         f"rastro")
finally:
    os.environ.pop("ESCOPO_ENFORCEMENT", None)
    os.environ.pop("ESCOPO_ENFORCEMENT_MOTIVO", None)

# ── 6 · ⚠️ o limite deste arquivo ─────────────────────────────────────────
secao("6 · ⚠️ o que isto ainda NÃO prova")

vale(True,
     "🔥 QUE O ENFORCE RODOU EM PRODUÇÃO. Não rodou. Isto é o caminho\n"
     "      exercitado com a política REAL do repositório, com o ceo_agent\n"
     "      REAL, e com arquivos de perfil de mentira. O que falta é a\n"
     "      política subir como `enforce` na VPS e um bloqueio de verdade\n"
     "      acontecer — e só isso fecha a frase 'enforce nunca rodou em\n"
     "      lugar nenhum'.")

shutil.rmtree(tmp, ignore_errors=True)

print("\n" + "─" * 70)
if FALHAS:
    print(f"❌ {len(FALHAS)} falha(s) de {OK + len(FALHAS)}\n")
    sys.exit(1)
print(f"✅ {OK}/{OK} asserções\n")
print("📌 A ordem que isto obriga:\n")
print("   1. quem CHAMA aprende a tratar o bloqueio")
print("   2. só então o contrato vira `enforce`")
print("   Inverter é a camada derrubando a aplicação que ela protege.\n")
