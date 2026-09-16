#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""teste_sem_dado.py -- ausência de dado não pode virar evidência de zero.

O bug que rodou DUAS vezes em produção — 36 fontes em 14/09, 8 em 15/09:

    vendas = _vendas_por_fonte(dias)                          # {} quando erra
    vk = vendas.get(fonte, {"vendas": 0, "comissao": 0.0})    # vira zero
    elif n >= min_posts: vd = "MORTA"                         # vira poda

⚠️ Este teste existe para esse caminho não voltar. Se alguém um dia trocar o
`return None` por `return {}` "pra simplificar", aqui quebra.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ["ESCOPO_ATIVO"] = "0"        # aqui se testa o Jarvis, não a camada

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import ceo_agent as C                                          # noqa: E402
import despodar                                                # noqa: E402

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


def ledger_falso(dias):
    """8 posts para cada uma de 10 fontes — todas acima de CEO_PODA_MIN_POSTS."""
    return [{"perfil_fonte": f"fonte_{i:02d}", "nicho": "pet"}
            for i in range(10) for _ in range(8)]


print("\n🩺 ausência de dado ≠ evidência de zero\n")
tmp = Path(tempfile.mkdtemp(prefix="sem_dado_"))
C._ler_ledger = ledger_falso

# ── 1 · consulta indisponível → SEM_DADO, nunca MORTA ─────────────────────
secao("1 · consulta indisponível")

C._vendas_por_fonte = lambda dias: None
fontes = C._analisar_fontes(30)

vale(len(fontes) == 10, f"deveriam sair 10 fontes, vieram {len(fontes)}")
vale(all(f["veredito"] == "SEM_DADO" for f in fontes),
     "⚠️ com a consulta fora, TODAS têm que ser SEM_DADO")
vale(not any(f["veredito"] == "MORTA" for f in fontes),
     "⚠️ A ASSERÇÃO QUE IMPORTA: nenhuma pode ser MORTA quando não se sabe")
vale(all(f["venda_conhecida"] is False for f in fontes),
     "venda_conhecida deveria marcar False")

# ── 2 · consulta OK e vazia → aí sim MORTA ────────────────────────────────
secao("2 · consultei e ninguém vendeu → MORTA é legítimo")

C._vendas_por_fonte = lambda dias: {}
fontes_ok = C._analisar_fontes(30)
vale(all(f["veredito"] == "MORTA" for f in fontes_ok),
     "{} é resposta válida: consultei, ninguém vendeu")
vale(all(f["venda_conhecida"] is True for f in fontes_ok),
     "venda_conhecida deveria marcar True")

C._vendas_por_fonte = lambda dias: {"fonte00": {"vendas": 3, "comissao": 24.89}}
mistas = C._analisar_fontes(30)
vale(sum(1 for f in mistas if f["veredito"] == "VENDE") == 1,
     "a fonte que vendeu tem que sair como VENDE")
vale(sum(1 for f in mistas if f["veredito"] == "MORTA") == 9,
     "as outras 9, MORTA")

# ── 3 · a poda se recusa a rodar no escuro ────────────────────────────────
secao("3 · poda cancelada quando não há dado")

perfis = tmp / "tiktok_perfis.txt"
perfis.write_text("\n".join(f"@fonte_{i:02d} #pet" for i in range(10)) + "\n",
                  encoding="utf-8")
C.TIKTOK_PERFIS = perfis
C.IG_PERFIS = tmp / "nao_existe.txt"

C._vendas_por_fonte = lambda dias: None
levantou = None
try:
    C._podar_fontes(C._analisar_fontes(30), executar=True)
except C.PodaSemEvidencia as e:
    levantou = e
vale(levantou is not None,
     "⛔ com SEM_DADO a poda tem que LEVANTAR, não devolver []")
vale("não completou" in str(levantou),
     f"a exceção tem que dizer o motivo: {levantou!r}")
vale("PODADO CEO" not in perfis.read_text(encoding="utf-8"),
     "⚠️ nenhum arquivo pode ter sido tocado")

C._vendas_por_fonte = lambda dias: {}
podados = C._podar_fontes(C._analisar_fontes(30), executar=True)
vale(len(podados) == 10, f"com dado real a poda funciona igual, veio {podados}")
vale(perfis.read_text(encoding="utf-8").count("PODADO CEO") == 10,
     "as 10 deveriam estar comentadas")

# ── 4 · o relatório diz que não sabe ──────────────────────────────────────
secao("4 · o relatório não esconde a ausência de dado")

C._vendas_por_fonte = lambda dias: None
md = C._render_fontes(C._analisar_fontes(30))
vale("não completou" in md,
     "o relatório tem que dizer que a consulta não completou")
vale("💀" not in md and "MORTA" not in md,
     "⚠️ não pode aparecer veredito nenhum quando não há dado")
vale("NÃO quer dizer que elas não venderam" in md,
     "tem que explicar a diferença, não só avisar")

C._vendas_por_fonte = lambda dias: {}
md_ok = C._render_fontes(C._analisar_fontes(30))
vale("MORTA" in md_ok, "com dado, o relatório volta ao normal")

# ── 4b · o CHAMADOR não pode mentir sobre a lista vazia ───────────────────
secao("4b · [] por cancelamento ≠ [] por não haver nada")

import contextlib                                                 # noqa: E402
import io                                                         # noqa: E402


def rodar_podar():
    """Roda `ceo_agent --podar-fontes` capturando saída e código de retorno."""
    buf = io.StringIO()
    argv_antes = sys.argv
    sys.argv = ["ceo_agent.py", "150", "--podar-fontes"]
    try:
        with contextlib.redirect_stdout(buf):
            codigo = C.main()
    finally:
        sys.argv = argv_antes
    return codigo, buf.getvalue()


C._vendas_por_fonte = lambda dias: None
codigo, saida = rodar_podar()
vale(codigo == 1,
     f"⚠️ cancelamento tem que sair com código != 0 — script que checa "
     f"exit code precisa saber que o trabalho não foi feito. Veio {codigo}")
vale("CANCELADA" in saida, "tem que dizer que cancelou")
vale("não dá pra saber" in saida,
     "⚠️ tem que dizer que NÃO SABE, não que está tudo bem")
vale("todas vendem" not in saida and "nenhuma fonte MORTA" not in saida,
     f"⚠️ A ASSERÇÃO QUE IMPORTA: não pode afirmar nada sobre as fontes "
     f"quando não há dado. Saída: {saida!r}")

# com dado e sem nada a podar, a mensagem otimista é legítima
perfis.write_text("\n".join(f"@fonte_{i:02d} #pet" for i in range(10)) + "\n",
                  encoding="utf-8")
C._vendas_por_fonte = lambda dias: {
    f"fonte{i:02d}": {"vendas": 1, "comissao": 1.0} for i in range(10)}
codigo, saida = rodar_podar()
vale(codigo == 0, f"com dado e nada a podar, sai 0 — veio {codigo}")
vale("nenhuma fonte MORTA" in saida,
     f"com dado, a mensagem otimista é legítima: {saida!r}")


# ── 5 · despodar devolve a rodada errada ──────────────────────────────────
secao("5 · despodar")

linha = "# @fonte_03 #pet   # PODADO CEO 2026-09-15: 8 posts, 0 vendas em vários dias"
vale(despodar.despodar(linha, "2026-09-15") == "@fonte_03 #pet",
     f"deveria devolver a linha original, veio "
     f"{despodar.despodar(linha, '2026-09-15')!r}")
vale(despodar.despodar(linha, "2026-09-14") == linha,
     "poda de outra data não pode ser tocada")
vale(despodar.despodar("@fonte_09 #pet", "2026-09-15") == "@fonte_09 #pet",
     "linha normal não pode ser alterada")
vale(despodar.despodar("# comentário do usuário", "2026-09-15")
     == "# comentário do usuário",
     "comentário que não é poda tem que ficar intacto")

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + "─" * 70)
if FALHAS:
    print(f"❌ {len(FALHAS)} falha(s) · {OK} asserção(ões) ok")
    sys.exit(1)
print(f"✅ {OK}/{OK} asserções")
