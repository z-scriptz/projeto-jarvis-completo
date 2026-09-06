#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# diag_rodizio.py -- o rodízio balanceia com um nicho e o post sai em outro?
#
# O QUE ISTO INVESTIGA (06/09/2026)
# ─────────────────────────────────
# Duas rodadas seguidas, a janela do rodízio tinha as 6 contas:
#
#   🔀 rodízio em 240: beleza=29 · casa=173 · geral=1 · moda=21 · pet=7 · tech=9
#
# Round-robin com 12 vagas e 6 contas deveria dar 2 pra cada. Saiu:
#
#   moda=5 · casa=3 · pet=2 · beleza=1 · tech=1 · geral=0
#
# @topshop.__ ficou sem post nas DUAS rodadas.
#
# ⚠️ MINHA SUSPEITA (não confirmada, e é por isso que este script existe): o
# rodízio monta os baldes com `_nicho_da_pasta`, mas o `_produzir` decide a
# conta na hora com `conta_do_produto`. Se as duas discordam, o balanço é feito
# com um nicho e a postagem acontece em outro — e o rodízio "funciona" no papel
# enquanto uma conta seca.
#
# ⚠️ CUSTO: `conta_do_produto` pode chamar a IA pro que a lista não decide, MAS
# ela tem cache por nome (`_ler_cache`). Estes pacotes já foram roteados quando
# produziram, então o normal é cache quente e custo ~zero. Rode com --limite
# baixo primeiro se quiser confirmar isso antes.
#
# ⚠️ MEDIDO EM 06/09 E O RESULTADO ME DESMENTIU DUAS VEZES. Nos 40 da frente:
# só 5% de discordância — mas a distribuição saiu `casa=35 · moda=5`, e aí está
# o furo do MÉTODO: o rodízio não produz os 40 da frente, ele escolhe 12
# ESPALHADOS, um de cada balde por volta. Casa é o balde que quase não diverge;
# quem diverge são os raros dos baldes pequenos — exatamente os que ele busca.
# Medir a frente da fila mede a população errada.
#
#   .venv/bin/python diag_rodizio.py --lote 12    # ← O QUE RESPONDE A PERGUNTA
#   .venv/bin/python diag_rodizio.py --limite 40  # a frente da fila (contexto)
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
INBOX = BASE / "inbox_tiktok"
PARCIAIS = (".part", ".ytdl", ".temp", ".tmp", ".download")


def _medir_lote(PT, RC, quantos: int) -> int:
    """Refaz a escolha do `produzir_tiktok` e mede a divergência SÓ nela.

    Não produz nada: só descobre quais 12 seriam escolhidos, com qual balde, e
    em que conta cada um cairia de verdade.
    """
    fila = PT._pendentes()
    if not fila:
        print("❌ fila vazia")
        return 1

    passo = max(quantos * 20, 120)
    teto = min(len(fila), 800)
    pares, vistos, i = [], set(), 0
    while i < teto:
        fim = min(i + passo, teto)
        for t in fila[i:fim]:
            n = PT._nicho_da_pasta(t[1])
            pares.append((n, t))
            vistos.add(n)
        i = fim
        if PT._CONTAS.issubset(vistos):
            break

    lote = PT.rodizio(pares, quantos)
    print(f"📦 {len(fila)} na fila · janela de {len(pares)} · "
          f"lote de {len(lote)}\n")

    balde_de = {}
    for n, t in pares:
        balde_de[t[0]] = n            # t[0] é a pasta

    prev, real_c, dif = {}, {}, []
    for pasta, pj, _vid in lote:
        balde = balde_de.get(pasta, "?")
        # ⚠️ TEM QUE CHAMAR IGUALZINHO AO `_produzir`, senão eu meço o meu
        # próprio script em vez da produção. A 1ª versão passava categoria
        # vazia e sem `nicho_fonte` — parte da divergência que ela acusou era
        # artefato meu, não do sistema.
        info = {}
        try:
            info = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            pass
        nome = info.get("produto") or info.get("termo") or ""
        categoria = ""
        try:
            from creative_engine.narration_script_builder import _categoria_do_produto
            categoria = _categoria_do_produto(nome) or ""
        except Exception:
            pass
        try:
            conta = RC.conta_do_produto(nome, categoria,
                                        info.get("nicho_fonte", ""))
            real = (conta.get("nicho") or "") if conta else ""
        except Exception as e:
            real = f"erro:{str(e)[:16]}"
        prev[balde] = prev.get(balde, 0) + 1
        real_c[real] = real_c.get(real, 0) + 1
        marca = "  ← MUDA" if balde != real else ""
        print(f"   {balde:8} → {real:8} {nome[:46]}{marca}")
        if balde != real:
            dif.append((nome, balde, real))

    def linha(rot, c):
        print(f"   {rot:22} " + " · ".join(f"{k or '(vazio)'}={v}"
                                           for k, v in sorted(c.items())))

    print("\n── o que o rodízio RESERVOU vs onde o post CAI ──")
    linha("reservado (balde)", prev)
    linha("real (conta.json)", real_c)

    n = len(lote)
    print(f"\n── discordam: {len(dif)} de {n} ({len(dif)/max(1,n)*100:.0f}%) ──")
    if not dif:
        print("   ✅ o rodízio reserva e posta no mesmo nicho.")
        print("   A minha suspeita estava errada: o desequilíbrio vem de outro")
        print("   lugar, e é bom saber disso antes de eu mexer no que funciona.")
    else:
        print("   ⚠️ CADA LINHA 'MUDA' É UMA VAGA CONTADA NUMA CONTA E GASTA")
        print("      NOUTRA. Foi assim que o @topshop.__ ficou sem post em duas")
        print("      rodadas seguidas com o rodízio 'funcionando'.")
    return 0


def main() -> int:
    args = sys.argv[1:]
    limite = 240
    if "--limite" in args:
        try:
            limite = int(args[args.index("--limite") + 1])
        except Exception:
            pass

    sys.path.insert(0, str(BASE))
    try:
        import produzir_tiktok as PT
        import roteador_contas as RC
    except Exception as e:
        print(f"❌ não consegui importar (rode na VPS, com a .venv): {str(e)[:90]}")
        return 1

    # ⚠️ MEDIR A FRENTE DA FILA MEDE A POPULAÇÃO ERRADA (achado em 06/09/2026,
    # na primeira rodada deste próprio script). Os 40 da frente deram
    # `casa=35 · moda=5` e só 5% de discordância — mas o rodízio NÃO produz os
    # 40 da frente: ele escolhe 12 ESPALHADOS, um de cada balde por volta. Casa
    # é o balde que quase não diverge; quem diverge são os itens raros dos
    # baldes pequenos, e são exatamente esses que o rodízio vai buscar.
    #
    # `--lote N` refaz a MESMA escolha que o `produzir_tiktok` faria e mede só
    # nela. É a única amostra que responde a pergunta.
    if "--lote" in args:
        try:
            quantos = int(args[args.index("--lote") + 1])
        except Exception:
            quantos = 12
        return _medir_lote(PT, RC, quantos)

    pastas = []
    for pasta in sorted(INBOX.iterdir()):
        if len(pastas) >= limite:
            break
        if not pasta.is_dir() or pasta.name.startswith("_"):
            continue
        pj = pasta / "plano.json"
        vids = [v for v in pasta.glob("video.*")
                if not v.name.endswith(PARCIAIS)]
        if not (pj.exists() and vids):
            continue
        try:
            info = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            continue
        if info.get("nao_e_produto"):
            continue
        pastas.append((pj, info))

    if not pastas:
        print("❌ nada na fila — rode na VPS, dentro de ~/jarvis")
        return 1

    print(f"📦 {len(pastas)} pacote(s) da frente da fila\n")

    discordam = []
    cont_balde, cont_real = {}, {}
    for pj, info in pastas:
        balde = PT._nicho_da_pasta(pj)          # o que o RODÍZIO usa
        nome = info.get("produto") or info.get("termo") or ""
        try:
            conta = RC.conta_do_produto(nome, "")
            real = (conta.get("nicho") or "") if conta else ""
        except Exception as e:
            real = f"erro:{str(e)[:20]}"
        cont_balde[balde] = cont_balde.get(balde, 0) + 1
        cont_real[real] = cont_real.get(real, 0) + 1
        if balde != real:
            discordam.append((nome, balde, real))

    def linha(rot, c):
        print(f"   {rot:10} " + " · ".join(f"{k or '(vazio)'}={v}"
                                           for k, v in sorted(c.items())))

    print("── distribuição ──")
    linha("BALDE", cont_balde)      # o que o rodízio acha que tem
    linha("REAL", cont_real)        # onde o post de fato vai cair

    n = len(pastas)
    print(f"\n── discordam: {len(discordam)} de {n} "
          f"({len(discordam)/n*100:.0f}%) ──")
    if not discordam:
        print("   ✅ o rodízio balanceia com o mesmo nicho que posta.")
        print("   Então o desequilíbrio vem de outro lugar, e a minha suspeita")
        print("   estava errada — bom saber antes de eu 'consertar' o certo.")
        return 0

    por_par = {}
    for nome, b, r in discordam:
        por_par.setdefault((b, r), []).append(nome)
    for (b, r), itens in sorted(por_par.items(), key=lambda kv: -len(kv[1])):
        print(f"\n   balde '{b or '(vazio)'}' → posta em '{r or '(vazio)'}'   "
              f"({len(itens)})")
        for nm in itens[:5]:
            print(f"      • {nm[:70]}")
        if len(itens) > 5:
            print(f"      … +{len(itens) - 5}")

    print(f"\n⚠️ CADA LINHA ACIMA É UMA VAGA CONTADA NA CONTA ERRADA. O rodízio")
    print(f"   reserva um slot pro balde e o vídeo sai noutro perfil — por isso")
    print(f"   uma conta pode secar mesmo com o rodízio 'funcionando'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
