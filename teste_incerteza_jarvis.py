#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""teste_incerteza_jarvis.py -- "não consegui olhar" nunca é "não aconteceu".

⚠️ DOIS DEFEITOS DA CAÇA DE 21/09, e os dois são o mesmo colapso em lugares
diferentes:

    VerificadorProducao    `Path.exists()` devolve False em QUALQUER OSError.
                           Permissão negada virava "o vídeo não foi produzido".

    VerificadorCarrossel   conta sem `media_id` ia toda para `sem_midia`, que
                           vira `falhos`. A conta cujo publish ficou em aberto
                           — a resposta da Meta se perdeu — entrava junto.

📌 Os três que nunca podem colapsar num só:

    SEM COBERTURA   buraco de produto — ninguém escreveu quem avalia
    INVERIFICAVEL   infra — não deu para olhar
    FAILED          incidente — a ação deu errado

    python3 teste_incerteza_jarvis.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import escopo_jarvis as EJ                                     # noqa: E402
from actrova import Estado                                     # noqa: E402

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


print("\n🔒 incerteza não é fracasso — nos dois verificadores\n")
tmp = Path(tempfile.mkdtemp(prefix="incerteza_"))

# ══════════════════════════════════════════════════════════════════════════
#  PRODUÇÃO — o disco que não deixou olhar
# ══════════════════════════════════════════════════════════════════════════
pronto = tmp / "pronto_para_postar"
pronto.mkdir()
EJ.PRONTO_DIR = pronto
EJ.BASE_DIR = tmp


def produzir(artefatos: dict, alvos=None, falharam=()):
    v = EJ.VerificadorProducao()
    return v.verificar({"alvos": list(alvos or artefatos),
                        "artefatos": dict(artefatos),
                        "falharam": list(falharam)}, {}, 1)


secao("1 · o vídeo está lá")

boa = pronto / "produto_ok"
boa.mkdir()
(boa / "video.mp4").write_bytes(b"x" * 10)
p = produzir({"produto_ok": str(boa)})
vale(p.estado is Estado.VERIFICADO, f"VERIFICADO, deu {p.estado.value}")

secao("2 · o caminho existe e o arquivo não")

vazia = pronto / "produto_vazio"
vazia.mkdir()
p = produzir({"produto_vazio": str(vazia)})
vale(p.estado is Estado.FALHOU,
     f"⚠️ olhei e não está lá — ISSO é falha, e continua sendo. "
     f"Deu {p.estado.value}")

secao("3 · 🔥 o disco não deixou olhar")

trancada = pronto / "produto_trancado"
trancada.mkdir()
(trancada / "video.mp4").write_bytes(b"x" * 10)
os.chmod(trancada, 0o000)
pulou = os.geteuid() == 0          # root atravessa qualquer permissão
if pulou:
    # ⚠️ Não vale asserção nenhuma aqui. Como root o `chmod 000` não bloqueia,
    # então este caso não foi exercitado — e marcar um ✅ por ter rodado sem
    # testar nada seria a ferramenta decorativa que este projeto persegue.
    # O defeito de verdade está no 3b, que não depende de quem roda.
    print("   ⏭️  rodando como root: `chmod 000` não bloqueia, este caso NÃO "
          "foi exercitado. Ver 3b.")
else:
    p = produzir({"produto_trancado": str(trancada)})
    vale(p.estado is Estado.INVERIFICAVEL,
         f"🔥 permissão negada NÃO é 'não produziu'. O vídeo está lá.\n"
         f"      Deu {p.estado.value}")
os.chmod(trancada, 0o755)

secao("3b · 🔥 o OSError, sem depender de quem roda o teste")

original = EJ.Path


class PathQueNaoAbre(type(Path())):
    """Um Path cujo `stat` levanta PermissionError, como um volume sem
    permissão faria. O ponto é o TIPO do erro, não como ele foi produzido."""

    def stat(self, *a, **k):
        raise PermissionError(13, "Permission denied")


try:
    EJ.Path = PathQueNaoAbre
    p = produzir({"produto_x": str(pronto / "produto_x")})
finally:
    EJ.Path = original

vale(p.estado is Estado.INVERIFICAVEL,
     f"🔥 A VERSÃO ANTERIOR DAVA FALHOU AQUI. `Path.exists()` engole o\n"
     f"      OSError e devolve False, e o verificador mandava para\n"
     f"      `faltando`. Um vídeo que existe virava fracasso no livro.\n"
     f"      Deu {p.estado.value}")
vale((p.dicionario().get("evidence") or {}).get("ilegiveis")
     or "ilegiveis" in str(p.evidencia),
     "⚠️ e o recibo NOMEIA a causa: `ilegiveis` separa 'o disco não deixou "
     "olhar' de 'o produtor não disse onde pôs'")

secao("4 · FileNotFoundError continua sendo falha")


class PathSumido(type(Path())):
    def stat(self, *a, **k):
        raise FileNotFoundError(2, "No such file")


try:
    EJ.Path = PathSumido
    p = produzir({"produto_y": str(pronto / "produto_y")})
finally:
    EJ.Path = original

vale(p.estado is Estado.FALHOU,
     f"📌 A DISTINÇÃO QUE FAZ O CONSERTO VALER: 'não existe' é resposta do\n"
     f"      disco, 'não posso ler' é ausência de resposta. Tratar as duas\n"
     f"      como incerteza esconderia produção que de fato falhou.\n"
     f"      Deu {p.estado.value}")

# ══════════════════════════════════════════════════════════════════════════
#  CARROSSEL — o publish que ficou em aberto
# ══════════════════════════════════════════════════════════════════════════
os.environ["FACEBOOK_PAGE_TOKEN"] = "tok-de-teste"


def carrossel(alvos, midias, incertas=()):
    v = EJ.VerificadorCarrossel(buscar=lambda mid, tok: {"id": mid})
    return v.verificar({"alvos": list(alvos), "midias": dict(midias),
                        "incertas": list(incertas)}, {}, 1)


secao("5 · as seis contas publicaram")

contas = [f"c{i}" for i in range(3)]
p = carrossel(contas, {c: f"mid_{c}" for c in contas})
vale(p.estado is Estado.VERIFICADO, f"VERIFICADO, deu {p.estado.value}")

secao("6 · a Meta recusou uma")

p = carrossel(contas, {"c0": "mid_c0", "c1": "mid_c1"})
vale(p.contagem and p.contagem.falhos == 1 and p.contagem.incertos == 0,
     f"⚠️ recusa COM motivo é falha, e continua contando como falha: "
     f"{p.contagem}")

secao("7 · 🔥 o publish de uma ficou em aberto")

p = carrossel(contas, {"c0": "mid_c0", "c1": "mid_c1"}, incertas=["c2"])
vale(p.contagem and p.contagem.incertos == 1 and p.contagem.falhos == 0,
     f"🔥 A RESPOSTA DO PUBLISH SE PERDEU. Pode haver post no ar, e sem\n"
     f"      `media_id` não dá para perguntar à Meta qual é. Antes isso\n"
     f"      entrava em `sem_midia` → `falhos`, do lado de quem a Meta\n"
     f"      recusou com motivo. Veio {p.contagem}")

secao("8 · 🔥 as duas derrotas ao mesmo tempo, sem se misturar")

p = carrossel(["c0", "c1", "c2", "c3"], {"c0": "mid_c0"},
              incertas=["c3"])
vale(p.contagem and p.contagem.confirmados == 1
     and p.contagem.falhos == 2 and p.contagem.incertos == 1,
     f"📌 1 no ar, 2 recusadas, 1 em aberto — e o recibo diz os três\n"
     f"      números separados. Somar os dois últimos daria '3 não saíram',\n"
     f"      que é redondo e mentiroso. Veio {p.contagem}")

shutil.rmtree(tmp, ignore_errors=True)

print("\n" + "─" * 70)
if FALHAS:
    print(f"❌ {len(FALHAS)} falha(s) de {OK + len(FALHAS)}\n")
    sys.exit(1)
print(f"✅ {OK}/{OK} asserções\n")
print("📌 O que muda no recibo:\n")
print("   antes   FAILED cobria 'deu errado', 'não deu para olhar' e")
print("           'a resposta sumiu' com a mesma palavra")
print("   agora   cada um tem a sua, e quem lê sabe se conserta o código,")
print("           a máquina, ou se vai olhar o perfil com os próprios olhos\n")
