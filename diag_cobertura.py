#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diag_cobertura.py -- o livro cobre tudo que acontece, ou só o que ele vê?

⚠️ DUAS PERGUNTAS QUE O `resumo()` LEVANTOU EM 19/09/2026 E NINGUÉM FECHOU.

    🔒 escopo: 152 ação(ões) registrada(s)
       verificação  VERIFIED 22 · FAILED 130

    1. os 130 FAILED em `video.create` são de QUANDO, e de que FORMA?
       (90 "o produtor declarou que falhou" · 40 "o disco desmentiu o
       caminho" — mas sem data, os 40 podem ser cicatriz do conserto do
       `artefatos` em 17/09 ou ferida aberta de hoje)

    2. 🔥 o livro registrou 1 VERIFIED em `video.create` na mesma janela em
       que 26 `video.mp4` foram escritos no disco. Existe produtor FORA da
       guarda, ou a comparação estava quebrada?

📌 A segunda pergunta importa mais que a primeira, e não é sobre o Jarvis:
**livro que cobre um caminho e é lido como se cobrisse todos mente por
omissão.** Um operador lendo "130 FAILED" conclui "a máquina quebrou" quando
a verdade pode ser "este caminho quebrou, e outro produziu 26".

⚠️ E A PRIMEIRA TENTATIVA DE RESPONDER A 2 ESTAVA QUEBRADA — por mim, com o
defeito que este repositório documenta em três lugares.

Comparei `produzir_tiktok.H._slugify(nome)` com nome de pasta, e deu ZERO de
54 contra 26. Zero absoluto é assinatura de join quebrado, não de conjunto
disjunto. O motivo está escrito em `telegram_repurpose_hunter.py:491`:

    s = re.sub(r"\\W+", "_", (texto or "").lower()).strip("_")[:40]

**A pasta é criada com a régua do hunter, TRUNCADA em 40 caracteres.** Eu
comparei com a régua do renderizador, inteira. Réguas diferentes para a mesma
entidade — o mesmo defeito que transformava vídeo existente em FAILED no
`VerificadorProducao`, e que o `youtube_uploader._resolver_pasta` já resolvia
com uma escada de candidatos desde antes.

📌 Por isso este arquivo NÃO inventa régua: usa as duas que existem, mais o
truncamento, e diz quantos casou por qual. Se um caminho casar sozinho, a
resposta veio de uma régua só — e isso também é informação.

    /root/jarvis/.venv/bin/python diag_cobertura.py
    /root/jarvis/.venv/bin/python diag_cobertura.py --dias 7
"""
import collections
import datetime
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))


def _quando(v):
    """`at` é ISO 8601 e mora no RECIBO, não no corpo.

    ⚠️ Errei isso uma vez hoje: usei `r.body.get("at")`, a coluna de data
    saiu vazia, e eu quase li "sem data" como "sem informação" em vez de
    "perguntei no lugar errado"."""
    if v is None:
        return None
    try:
        return datetime.datetime.fromisoformat(str(v))
    except ValueError:
        try:
            return datetime.datetime.fromtimestamp(float(v))
        except (TypeError, ValueError):
            return None


def _at(recibo):
    return _quando(getattr(recibo, "at", None) or (recibo.body or {}).get("at"))


def _reguas():
    """Todas as réguas de slug que existem neste repositório.

    ⚠️ DEVOLVE UM DICIONÁRIO COM O NOME DE CADA UMA, de propósito. Saber
    QUAL régua casou é metade da resposta: se só a truncada casa, a outra
    está errada em algum lugar do sistema, e alguém vai tropeçar nela."""
    reguas = {}
    try:
        import produzir_tiktok as _PT
        reguas["renderizador"] = _PT.H._slugify
    except Exception as e:                            # noqa: BLE001
        print(f"   ⚠️ sem a régua do renderizador ({type(e).__name__}) — "
              f"o resultado abaixo cobre menos do que deveria")
    try:
        import telegram_repurpose_hunter as _TH
        reguas["hunter (trunca 40)"] = _TH._slugify
    except Exception as e:                            # noqa: BLE001
        print(f"   ⚠️ sem a régua do hunter ({type(e).__name__})")
    if not reguas:
        raise SystemExit("❌ nenhuma régua disponível — não dá para comparar "
                         "nada, e chutar aqui seria inventar o resultado")
    return reguas


def candidatos(nome: str, reguas: dict) -> dict:
    """{slug: qual régua o produziu}. Inclui o truncamento em 40."""
    saida = {}
    for rotulo, fn in reguas.items():
        try:
            s = fn(nome or "")
        except Exception:                             # noqa: BLE001
            continue
        if not s:
            continue
        saida.setdefault(s, rotulo)
        # 📌 O truncamento entra como candidato SEPARADO mesmo vindo da régua
        # inteira — é literalmente a diferença que anulou a comparação.
        saida.setdefault(s[:40], rotulo + " +trunc40")
    return saida


def main() -> int:
    dias = 3
    if "--dias" in sys.argv:
        dias = int(sys.argv[sys.argv.index("--dias") + 1])

    # ⚠️ NA VPS É `agents/daemon_maestro.py`; NO REPO É A RAIZ.
    # É a dualidade que o `MAPA_DOC` do `conferir.py` administra, e que já
    # travou a postagem balanceada por dias — editava-se a raiz enquanto o
    # serviço rodava o pacote. Aqui as duas são tentadas, e o script IMPRIME
    # de onde leu: diagnóstico que não diz qual cópia inspecionou pode estar
    # respondendo sobre o arquivo que não roda.
    DM = None
    for caminho in ("agents.daemon_maestro", "daemon_maestro"):
        try:
            DM = __import__(caminho, fromlist=["PRONTO_DIR"])
            print(f"   daemon lido de: {DM.__file__}")
            break
        except ImportError:
            continue
    if DM is None:
        raise SystemExit("❌ não achei o daemon nem em `agents/` nem na raiz")
    import escopo_jarvis as ej

    esc = ej._construir()
    if esc is None:
        print(f"❌ camada desligada: {ej.por_que_desligado()}")
        return 1
    recibos = esc.livro.ler()
    acoes = {r.hash: r for r in recibos if r.kind == "action"}

    # ── 1 · os FAILED, por dia E por forma ────────────────────────────────
    print(f"\n{'=' * 68}\n1 · os FAILED de `video.create`, por dia × forma\n"
          f"{'=' * 68}")
    cruz = collections.Counter()
    for r in recibos:
        if r.kind != "verification" or r.body["proof"]["state"] != "FAILED":
            continue
        a = acoes.get(r.body.get("action"))
        if not a or a.body["intent"]["action"] != "video.create":
            continue
        ev = r.body["proof"].get("evidence") or {}
        forma = ("produtor declarou" if ev.get("falha_declarada")
                 else "disco desmentiu" if ev.get("faltando") else "??")
        d = _at(r)
        cruz[(d.strftime("%Y-%m-%d") if d else "sem data", forma)] += 1

    if not cruz:
        print("\n   nenhum FAILED em `video.create` — nada a explicar aqui.")
    for (dia, forma), n in sorted(cruz.items()):
        print(f"   {dia}   {forma:<20} {n:>4}")
    desmentiu = {d: n for (d, f), n in cruz.items() if f == "disco desmentiu"}
    if desmentiu:
        print(f"\n   📌 'disco desmentiu' aparece em: "
              f"{', '.join(sorted(desmentiu))}")
        print("      só em 17/09  → cicatriz do conserto do `artefatos`, "
              "o livro\n                     não apaga e isso é o desenho")
        print("      em 19/09     → ferida aberta: o produtor diz que salvou "
              "num\n                     caminho onde não há vídeo")

    # ── 2 · 🔥 a cobertura ────────────────────────────────────────────────
    print(f"\n{'=' * 68}\n2 · o livro VIU os vídeos que o disco tem?\n"
          f"{'=' * 68}")
    reguas = _reguas()
    print(f"\n   réguas em uso: {', '.join(reguas)}")

    # tudo que a guarda declarou como alvo, em TODOS os slugs possíveis
    vistos = {}
    nomes_vistos = 0
    for r in recibos:
        if r.kind != "action":
            continue
        i = r.body["intent"]
        if i["action"] != "video.create":
            continue
        for alvo in i.get("targets") or []:
            nomes_vistos += 1
            for slug, rotulo in candidatos(str(alvo), reguas).items():
                vistos.setdefault(slug, (str(alvo), rotulo))
    print(f"   a guarda declarou {nomes_vistos} alvo(s), que geram "
          f"{len(vistos)} slug(s) possível(is)")

    corte = datetime.datetime.now() - datetime.timedelta(days=dias)
    dentro, fora, por_regua = [], [], collections.Counter()
    for d in Path(DM.PRONTO_DIR).iterdir():
        v = d / "video.mp4"
        if not (d.is_dir() and v.exists()):
            continue
        if datetime.datetime.fromtimestamp(v.stat().st_mtime) < corte:
            continue
        achado = vistos.get(d.name)
        if achado:
            dentro.append(d.name)
            por_regua[achado[1]] += 1
        else:
            fora.append(d.name)

    total = len(dentro) + len(fora)
    print(f"\n   vídeos escritos nos últimos {dias} dia(s): {total}")
    print(f"     a guarda VIU a intenção       {len(dentro):>4}")
    print(f"     a guarda NUNCA soube          {len(fora):>4}")
    if por_regua:
        print("\n   casou por qual régua:")
        for rotulo, n in por_regua.most_common():
            print(f"     {rotulo:<28} {n}")
        if len(por_regua) == 1:
            print("      ⚠️ UMA régua só casou tudo. As outras estão erradas "
                  "em algum\n         lugar do sistema, e alguém vai "
                  "tropeçar nelas.")

    if fora:
        print(f"\n   🔥 {len(fora)} vídeo(s) que o livro não conhece:")
        for n in sorted(fora)[:15]:
            print(f"      {n[:58]}")
        print("\n      Duas leituras possíveis, e elas são MUITO diferentes:")
        print("        · existe produtor rodando fora da costura → costurar")
        print("        · ou a minha comparação ainda está quebrada → o número")
        print("          acima de 'casou por qual régua' é que decide")
    elif total:
        print("\n   ✅ o livro conhece TODOS os vídeos do período. Não há")
        print("      buraco de cobertura — a comparação anterior é que estava")
        print("      quebrada pelo truncamento em 40 caracteres.")
    else:
        print("\n   ⚠️ nenhum vídeo no período: este diagnóstico não afirma")
        print("      nada sobre cobertura. Zero amostra é zero evidência,")
        print("      não evidência de que está tudo certo.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
