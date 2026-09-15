#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""teste_escopo_jarvis.py -- o encaixe da ESCOPO no ceo_agent.

Duas perguntas, e a primeira importa mais que a segunda:

    1. o Jarvis continua funcionando IGUAL se a ESCOPO não estiver lá?
    2. quando ela está, ela registra o que precisa registrar?

⚠️ A ordem não é acidental. Camada de controle que derruba a aplicação que
deveria proteger é pior que camada de controle nenhuma.
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


def fontes_falsas(n_mortas: int, n_vivas: int = 2) -> list:
    f = [{"fonte": f"morta_{i:02d}", "posts": 8, "vendas": 0, "veredito": "MORTA"}
         for i in range(n_mortas)]
    f += [{"fonte": f"viva_{i:02d}", "posts": 9, "vendas": 2, "veredito": "VENDE"}
          for i in range(n_vivas)]
    return f


print("\n🔒 ESCOPO × Jarvis — encaixe no ceo_agent\n")
tmp = Path(tempfile.mkdtemp(prefix="escopo_jarvis_"))

# ── 1 · o Jarvis sobrevive à ausência da ESCOPO ───────────────────────────
secao("1 · sem a ESCOPO, o ceo_agent roda igual")

os.environ["ESCOPO_ATIVO"] = "0"
import escopo_jarvis                                              # noqa: E402
import ceo_agent                                                  # noqa: E402

vale(not escopo_jarvis.ativo(), "com ESCOPO_ATIVO=0 a camada fica desligada")
vale("ESCOPO_ATIVO" in escopo_jarvis.por_que_desligado(),
     f"deveria dizer por quê: {escopo_jarvis.por_que_desligado()!r}")

perfis = tmp / "tiktok_perfis.txt"
perfis.write_text("\n".join(f"@morta_{i:02d} #pet" for i in range(3)) + "\n",
                  encoding="utf-8")
ceo_agent.TIKTOK_PERFIS = perfis
ceo_agent.IG_PERFIS = tmp / "nao_existe_ig.txt"

podados = ceo_agent._podar_fontes(fontes_falsas(3), executar=True)
vale(podados == ["morta_00", "morta_01", "morta_02"],
     f"a poda tem que funcionar sem a ESCOPO, veio {podados}")
vale(perfis.read_text(encoding="utf-8").count("PODADO CEO") == 3,
     "as 3 linhas deveriam estar comentadas")

# ── 2 · com a ESCOPO ligada ───────────────────────────────────────────────
secao("2 · com a ESCOPO ligada")

try:
    import escopo                                                 # noqa: F401
    TEM_LIB = True
except ImportError:
    TEM_LIB = False

if not TEM_LIB:
    print("   ⚠️ biblioteca `escopo` não instalada neste ambiente.")
    print("      pip install -e /root/escopo-runtime")
    print("      (os testes 2-5 foram pulados — o teste 1 é o que protege "
          "a produção)")
else:
    from escopo import Estado

    def montar(nome: str, arquivo_perfis: Path | None):
        """Um Escopo limpo por cenário, com a política REAL do repositório."""
        for m in list(sys.modules):
            if m in {"escopo_jarvis"}:
                del sys.modules[m]
        os.environ["ESCOPO_ATIVO"] = "1"
        os.environ["ESCOPO_POLITICAS"] = str(BASE / "politicas")
        os.environ["ESCOPO_DADOS"] = str(tmp / nome)
        import escopo_jarvis as ej
        ausente = tmp / f"{nome}_nao_existe.txt"
        ej.TIKTOK_PERFIS = arquivo_perfis or ausente
        ej.IG_PERFIS = ausente
        ceo_agent.guarda = ej.guarda
        ceo_agent.TIKTOK_PERFIS = arquivo_perfis or ausente
        ceo_agent.IG_PERFIS = ausente
        return ej

    def redecorar(ej):
        """Reaplica o decorador — `ceo_agent` já foi importado com o fallback."""
        import importlib
        importlib.reload(ceo_agent)
        ceo_agent.guarda = ej.guarda
        return ceo_agent

    def drenar(ej, vezes: int = 4):
        """Adianta a fila para não esperar as esperas reais (0s, 2s, 10s)."""
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
        return [r for r in esc.livro.ler() if r.tipo == "acao"][-1]

    # ── 2 · poda pequena → ALLOW + VERIFIED ───────────────────────────────
    p = tmp / "a.txt"
    p.write_text("\n".join(f"@morta_{i:02d} #pet" for i in range(3)) + "\n",
                 encoding="utf-8")
    ej = montar("caso_a", p)
    ca = redecorar(ej)
    ca.TIKTOK_PERFIS, ca.IG_PERFIS = p, tmp / "nada.txt"
    ca._podar_fontes(fontes_falsas(3), executar=True)
    esc = drenar(ej)
    a = ultima_acao(esc)
    vale(a.corpo["veredito"]["decisao"] == "ALLOW",
         f"3 fontes deveria ser ALLOW, veio {a.corpo['veredito']['decisao']}")
    vale(len(a.corpo["intencao"]["alvos"]) == 3,
         "só as MORTAS entram como alvo — as VENDE não")
    vale(esc.estado(a.hash) is Estado.VERIFICADO,
         f"3 pedidas e 3 comentadas deveria dar VERIFIED, "
         f"deu {esc.estado(a.hash).value}")

    # ── 3 · o incidente: 36 fontes → HOLD, mas observe não impede ─────────
    secao("3 · 🔥 o incidente das 36, com a política real")

    p36 = tmp / "b.txt"
    p36.write_text("\n".join(f"@morta_{i:02d} #pet" for i in range(36)) + "\n",
                   encoding="utf-8")
    ej = montar("caso_b", p36)
    cb = redecorar(ej)
    cb.TIKTOK_PERFIS, cb.IG_PERFIS = p36, tmp / "nada.txt"
    podados = cb._podar_fontes(fontes_falsas(36), executar=True)
    esc = drenar(ej)
    a = ultima_acao(esc)
    vale(len(podados) == 36, "em observe a poda acontece igual — 36 podadas")
    vale(a.corpo["veredito"]["decisao"] == "HOLD",
         f"36 > 5 deveria ser HOLD, veio {a.corpo['veredito']['decisao']}")
    vale(a.corpo["veredito"]["regra"] == "lote_destrutivo",
         "deveria citar a regra `lote_destrutivo`")
    vale(a.corpo["execucao"]["executou"] is True,
         "⚠️ observe REGISTRA que extrapolou, não impede")
    vale(esc.estado(a.hash) is Estado.VERIFICADO,
         f"as 36 foram mesmo comentadas → VERIFIED, "
         f"deu {esc.estado(a.hash).value}")

    # ── 4 · dry-run não pode dar FALHOU ───────────────────────────────────
    secao("4 · dry-run: nada escrito é o resultado CERTO")

    pdry = tmp / "c.txt"
    pdry.write_text("\n".join(f"@morta_{i:02d} #pet" for i in range(9)) + "\n",
                    encoding="utf-8")
    ej = montar("caso_c", pdry)
    cc = redecorar(ej)
    cc.TIKTOK_PERFIS, cc.IG_PERFIS = pdry, tmp / "nada.txt"
    cc._podar_fontes(fontes_falsas(9), executar=False)
    esc = drenar(ej)
    a = ultima_acao(esc)
    vale(pdry.read_text(encoding="utf-8").count("PODADO CEO") == 0,
         "dry-run não pode escrever nada")
    vale(esc.estado(a.hash) is Estado.VERIFICADO,
         f"⚠️ dry-run correto tem que dar VERIFIED, não FAILED — alarme falso "
         f"treina gente a ignorar alarme. Deu {esc.estado(a.hash).value}")
    prova = [r for r in esc.livro.ler()
             if r.tipo == "verificacao"][-1].corpo["prova"]
    vale("dry-run" in prova["motivo"],
         f"o motivo deveria dizer que era dry-run: {prova['motivo']!r}")

    # ── 5 · fonte de verdade ilegível → INVERIFICAVEL ─────────────────────
    secao("5 · sem arquivo de perfil para conferir")

    ej = montar("caso_d", None)          # nenhum arquivo existe
    cd = redecorar(ej)
    cd.TIKTOK_PERFIS = tmp / "sumiu.txt"
    cd.IG_PERFIS = tmp / "sumiu2.txt"
    cd._podar_fontes(fontes_falsas(36), executar=True)
    esc = drenar(ej)
    a = ultima_acao(esc)
    estado = esc.estado(a.hash)
    vale(estado is Estado.INVERIFICAVEL,
         f"⚠️ A LINHA QUE IMPORTA: sem fonte de verdade → UNVERIFIABLE, "
         f"nunca VERIFIED nem FAILED. Deu {estado.value}")
    prova = [r for r in esc.livro.ler()
             if r.tipo == "verificacao"][-1].corpo["prova"]
    vale(prova["evidencia"].get("tipo") == "PerfisIlegiveis",
         f"a evidência deveria nomear o erro: {prova['evidencia']}")

    integra, problemas = esc.integro()
    vale(integra, f"a cadeia deveria estar íntegra: {problemas}")

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + "─" * 70)
if FALHAS:
    print(f"❌ {len(FALHAS)} falha(s) · {OK} asserção(ões) ok")
    sys.exit(1)
print(f"✅ {OK}/{OK} asserções")
