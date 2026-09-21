#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""teste_caca_afirmacao.py -- a ferramenta que caça afirmação frouxa pode falhar?

⚠️ POR QUE ISTO EXISTE. Pela regra que o próprio projeto adotou —
**afirmação sem caminho de falsificação não vale** — um scanner que nunca
aponta nada é indistinguível de um scanner quebrado. Aqui ele precisa
apontar quando há, e calar quando não há, e as duas coisas são exercitadas.

🔥 E o teste 3 existe por causa de um susto real. Quando a declaração
`registro_apenas` foi criada, a ferramenta parou de apontar `id_lido` e
`id_esperado` — e NÃO foi o filtro novo que absolveu. Foi o contador, que
passou a ver a string duas vezes no repo (uma na construção, outra na
declaração) e concluiu "alguém lê". A ferramenta que caça *menção contada
como leitura* estava cometendo exatamente isso.

    python3 teste_caca_afirmacao.py
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import caca_afirmacao as C                                     # noqa: E402

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


tmp = Path(tempfile.mkdtemp(prefix="caca_"))


def caso(codigo: str, leitores: str = "") -> list:
    """Escreve um verificador de mentira e roda a caça nele.

    ⚠️ O leitor de `publicado` entra sempre. No repo de verdade quem lê essa
    chave é o `espera:` do contrato YAML; sem um equivalente aqui, ela
    apareceria em toda fixture e escondia a chave que cada caso investiga.
    Foi o que aconteceu na primeira versão deste arquivo.
    """
    alvo = tmp / "alvo.py"
    alvo.write_text(codigo, encoding="utf-8")
    outro = tmp / "leitores.py"
    outro.write_text('def _base(o):\n    return o["publicado"]\n'
                     + (leitores or ""), encoding="utf-8")
    return C.caçar(alvo, [alvo, outro])


print("\n🔎 a caça de evidência morta, ela mesma sob teste\n")

# ── 1 · acha o que está morto ─────────────────────────────────────────────
secao("1 · chave que ninguém lê é apontada")

m = caso('''
class V:
    def _consultar(self, ctx):
        return {"publicado": True, "id_lido": "x", "id_esperado": "y"}
''')
vale(sorted(x[2] for x in m) == ["id_esperado", "id_lido"],
     f"apontou as duas: {sorted(x[2] for x in m)}")

# ── 2 · cala quando alguém lê de verdade ──────────────────────────────────
secao("2 · chave com leitor real sai da lista")

m = caso('''
class V:
    def _consultar(self, ctx):
        return {"publicado": True, "id_lido": "x"}
''', leitores='''
def usa(obs):
    return obs["id_lido"]
''')
vale([x[2] for x in m] == [],
     f"⚠️ sem isto ele apontaria tudo e viraria ruído que se ignora. "
     f"Veio {[x[2] for x in m]}")

# ── 3 · 🔥 a declaração absolve; a MENÇÃO não ─────────────────────────────
secao("3 · 🔥 declarar ≠ mencionar")

m = caso('''
class V:
    registro_apenas = {"id_lido"}
    def _consultar(self, ctx):
        return {"publicado": True, "id_lido": "x", "id_esperado": "y"}
''')
vale([x[2] for x in m] == ["id_esperado"],
     f"🔥 `id_lido` foi DECLARADO como trilha de recibo e sai; `id_esperado`\n"
     f"      não foi declarado e fica. Se a própria declaração contasse como\n"
     f"      leitura, bastaria escrever o nome da chave em qualquer lugar\n"
     f"      para ser absolvido — e foi assim que a ferramenta se enganou na\n"
     f"      primeira versão. Veio {[x[2] for x in m]}")

# ── 4 · 🔥 e a menção solta continua sendo menção ─────────────────────────
secao("4 · 🔥 o nome da chave numa docstring não é um leitor")

m = caso('''
class V:
    def _consultar(self, ctx):
        """Devolve id_lido para quem quiser conferir depois."""
        return {"id_lido": "x"}
''')
vale([x[2] for x in m] == ["id_lido"],
     f"⚠️ prometer na docstring que alguém confere depois não é conferir.\n"
     f"      Veio {[x[2] for x in m]}")

# ── 5 · só olha função que declara observar ───────────────────────────────
secao("5 · dict de função comum não é payload de observação")

m = caso('''
class V:
    def montar_config(self):
        return {"tema": "escuro", "fonte": 12}
''')
vale(m == [],
     f"📌 o alvo é `_consultar`/`_efeito_observado` — dict de configuração não\n"
     f"      afirma nada sobre o mundo e apontá-lo seria ruído. Veio {m}")

# ── 6 · o que ele NÃO cobre, dito em teste e não só em comentário ─────────
secao("6 · ⚠️ o limite, exercitado")

m = caso('''
class V:
    def _consultar(self, ctx):
        lido, esperado = ctx["a"], ctx["b"]
        return {"publicado": lido != esperado, "id_lido": lido,
                "id_esperado": esperado}
''', leitores='''
def usa(o):
    return o["id_lido"], o["id_esperado"]
''')
vale(m == [],
     f"🔥 ISTO PASSA LIMPO E ESTÁ ERRADO: o `!=` está invertido. A ferramenta\n"
     f"      acha dado jogado fora, NÃO comparação feita com a régua errada.\n"
     f"      Está escrito no módulo, e agora tem um teste que prova o limite\n"
     f"      em vez de só afirmá-lo. Veio {m}")

# ── 7 · 🔥 universo inflado absolve por coincidência ──────────────────────
secao("7 · 🔥 o .venv não é leitor de nada")

alvo = tmp / "alvo.py"
alvo.write_text('''
class V:
    def _consultar(self, ctx):
        return {"publicado": True, "id_lido": "x"}
''', encoding="utf-8")
base_leitor = tmp / "leitores.py"
base_leitor.write_text('def _base(o):\n    return o["publicado"]\n',
                       encoding="utf-8")

# uma biblioteca qualquer que menciona a chave por acaso
venv = tmp / ".venv" / "lib" / "site-packages" / "biblioteca"
venv.mkdir(parents=True)
intruso = venv / "qualquer.py"
intruso.write_text('CAMPOS = ["id_lido", "outra_coisa"]\n', encoding="utf-8")

so_projeto = C.caçar(alvo, [alvo, base_leitor])
com_venv = C.caçar(alvo, [alvo, base_leitor, intruso])

vale([x[2] for x in so_projeto] == ["id_lido"],
     f"no universo do projeto, `id_lido` continua apontada: "
     f"{[x[2] for x in so_projeto]}")
vale([x[2] for x in com_venv] == [],
     f"🔥 E COM O .venv NO UNIVERSO ELA SOME — absolvida por uma lista de\n"
     f"      strings dentro de uma biblioteca que nunca leu nada. Na VPS a\n"
     f"      ferramenta varreu 11.989 arquivos contra 288 aqui, e imprimiu o\n"
     f"      MESMO ✅. Veio {[x[2] for x in com_venv]}")

vale(not C._do_projeto(intruso) and C._do_projeto(alvo),
     f"📌 é o `_do_projeto` que separa os dois, e é por isso que o número de\n"
     f"      arquivos é impresso: universo fora da faixa é sinal de que a\n"
     f"      busca mudou de tamanho sem ninguém pedir")

shutil.rmtree(tmp, ignore_errors=True)

print("\n" + "─" * 70)
if FALHAS:
    print(f"❌ {len(FALHAS)} falha(s) de {OK + len(FALHAS)}\n")
    sys.exit(1)
print(f"✅ {OK}/{OK} asserções\n")
print("📌 Uma ferramenta que nunca aponta nada é indistinguível de uma")
print("   ferramenta quebrada. Estes sete casos são o caminho de")
print("   falsificação dela — inclusive o 6, que existe para deixar")
print("   escrito o que ela deixa passar, e o 7, que veio da VPS.\n")
