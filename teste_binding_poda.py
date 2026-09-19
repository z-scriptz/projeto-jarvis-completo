# -*- coding: utf-8 -*-
"""As quatro invariantes do Effect Binding do `source.disable`."""
import shutil
import sys
import tempfile
import time
from pathlib import Path

# 🐞 A primeira versão deste arquivo tinha DOIS caminhos absolutos da máquina
# de desenvolvimento cravados aqui. Na VPS eles não existem, o `sys.path`
# ganhou duas entradas mortas, e o teste morreu com `No module named 'escopo'`
# — parecendo problema de instalação quando era o teste apontando para o
# nada.
#
# 📌 Os outros testes do Jarvis não inserem caminho nenhum: contam com o
# `escopo` instalado e com o diretório de trabalho para achar o
# `escopo_jarvis`. Este faz igual.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import escopo_jarvis as ej
from actrova import Relacao

tmp = Path(tempfile.mkdtemp())
tik = tmp / "perfis_tiktok.txt"; ig = tmp / "perfis_ig.txt"
ej.TIKTOK_PERFIS, ej.IG_PERFIS = tik, ig
ej.BASE_DIR = tmp
hoje = time.strftime("%Y-%m-%d")

OK, FALHAS = 0, []
def vale(c, m):
    global OK
    if c: OK += 1
    else: FALHAS.append(m)

def escrever(marcas):
    """marcas: [(handle, run_id_ou_None)]"""
    linhas = []
    for h, run in marcas:
        selo = f" #{run}" if run else ""
        linhas.append(f"# @{h}   # PODADO CEO {hoje}{selo}: 9 posts, 0 vendas")
    tik.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    ig.write_text("", encoding="utf-8")

def prova(alvos, run_id):
    v = ej.VerificadorPerfis()
    ctx = {"alvos": alvos, "executar": True, "run_id": run_id,
           "efeito_autorizado": {"fontes": sorted(a.lstrip("@").lower()
                                                  for a in alvos)}}
    return v.verificar(ctx, {"alvos": len(alvos)}, 1)

# 1️⃣ poda A de manhã + poda B à tarde → B NÃO vê A como OVER_EFFECT
escrever([("manha1", "run_AAA"), ("manha2", "run_AAA"),
          ("tarde1", "run_BBB"), ("tarde2", "run_BBB")])
p = prova(["@tarde1", "@tarde2"], "run_BBB")
vale(p.divergencia.relacao is Relacao.IGUAL,
     f"1️⃣ a poda da tarde NÃO pode ver a da manhã como excesso. "
     f"Veio {p.divergencia.relacao.value} · {p.divergencia.motivo}")
vale(not p.divergencia.inesperados,
     f"1️⃣ e nada de `manha1`/`manha2` como inesperado: {p.divergencia.inesperados}")

# 2️⃣ autoriza [A,B], marca [A,B] → MATCH
escrever([("a", "run_X"), ("b", "run_X")])
p = prova(["@a", "@b"], "run_X")
vale(p.divergencia.relacao is Relacao.IGUAL and p.estado.value == "VERIFIED",
     f"2️⃣ autorizado == podado → VERIFIED + MATCH. "
     f"Veio {p.estado.value} + {p.divergencia.relacao.value}")

# 3️⃣ autoriza [A,B], marca [A,B,C] → OVER_EFFECT com unexpected=[C]
escrever([("a", "run_X"), ("b", "run_X"), ("c", "run_X")])
p = prova(["@a", "@b"], "run_X")
vale(p.divergencia.relacao is Relacao.MAIOR,
     f"3️⃣ 🔥 fonte podada SEM autorização → OVER_EFFECT. "
     f"Veio {p.divergencia.relacao.value}")
vale(any("c" in x for x in p.divergencia.inesperados),
     f"3️⃣ e o recibo NOMEIA a fonte extra: {p.divergencia.inesperados}")
vale(p.estado.value == "VERIFIED",
     f"3️⃣ ⚠️ e a PROVA continua VERIFIED — as duas autorizadas foram mesmo "
     f"podadas. É 'provei muito bem que aconteceu coisa demais'. "
     f"Veio {p.estado.value}")

# 4️⃣ marca antiga SEM run_id → nunca atribuída à execução nova
escrever([("legado1", None), ("legado2", None)])
p = prova(["@legado1", "@legado2"], "run_NOVO")
# ⚠️ A RESPOSTA CERTA AQUI É `UNDER_EFFECT`, NÃO `UNKNOWN`, e a diferença
# importa. O requisito era "marca antiga nunca vira evidência da ação nova" —
# e ele está cumprido: nenhuma das duas legadas foi contada como feita por
# esta execução.
#
# 📌 Mas `UNKNOWN` afirmaria MENOS do que a evidência permite. Os dois
# arquivos foram lidos inteiros; qualquer coisa que ESTA execução tivesse
# marcado levaria o selo dela. A enumeração é honestamente completa, e por
# isso a ausência É provável: autorizou 2, entregou 0.
#
# ⚠️ Ser conservador além da evidência também é errar — na direção oposta,
# e de um jeito que treina gente a ignorar o campo.
vale(p.divergencia.relacao is Relacao.MENOR,
     f"4️⃣ 🔥 marca sem selo não é atribuída a esta execução — e o diff diz "
     f"AQUÉM, que é mais informativo que UNKNOWN sem afirmar demais. "
     f"Veio {p.divergencia.relacao.value} · {p.divergencia.motivo}")
vale(not p.divergencia.inesperados,
     f"4️⃣ e as legadas NÃO aparecem como excesso desta execução: "
     f"{p.divergencia.inesperados}")
vale(p.estado.value == "FAILED",
     f"4️⃣ e a prova diz FAILED — esta execução não marcou nada, o que é "
     f"verdade. Veio {p.estado.value}")

# 4️⃣b sem run_id no contexto (recibo antigo) → caminho legado preservado
escrever([("legado1", None), ("legado2", None)])
p = prova(["@legado1", "@legado2"], "")
vale(p.estado.value == "VERIFIED",
     f"4️⃣b ⚠️ recibo ANTIGO, sem `run_id`, cai no placar do dia e continua "
     f"funcionando — a transição não pode gerar FALHOU falso. "
     f"Veio {p.estado.value}")
vale(p.divergencia.relacao is Relacao.DESCONHECIDA,
     f"4️⃣b mas o DIFF continua DESCONHECIDO: sem binding não há o que "
     f"afirmar sobre conformidade. Veio {p.divergencia.relacao.value}")

shutil.rmtree(tmp, ignore_errors=True)
print()
if FALHAS:
    print(f"❌ {len(FALHAS)} falha(s) · {OK} ok")
    for f in FALHAS: print("   ·", f)
    sys.exit(1)
print(f"✅ {OK}/{OK} — as quatro invariantes do Effect Binding")
