#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_poda_fontes.py -- a poda só pode punir fonte que foi AVALIADA.
#
# O CASO REAL (04/09/2026): a rodada rendeu 157 produtos e mesmo assim comentou
# 12 fontes, incluindo o @airlandolists — que na rodada ANTERIOR tinha sido a
# melhor de todas (~50 vídeos). Elas não morreram: levaram `Failed to parse
# JSON` do TikTok, ou seja, nem chegaram a ser perguntadas.
#
# A trava por canal (18/08) não pegou isso porque ela só dispara quando o canal
# INTEIRO dá zero — e o TikTok bloqueia INTERMITENTEMENTE: alguns perfis passam,
# outros não, no mesmo minuto.
#
# A distinção que faltava:
#   "listei e não rendeu"   → informação sobre a FONTE   → pode podar
#   "não consegui listar"   → informação sobre a REDE    → NÃO pode podar
#
# Uso:  python3 teste_poda_fontes.py
import sys
import tempfile
from pathlib import Path

import tiktok_coletor as T

falhas = []


def checa(nome, ok, detalhe=""):
    print(f"  {'✅' if ok else '❌'} {nome}{('  — ' + detalhe) if detalhe else ''}")
    if not ok:
        falhas.append(nome)


def rodar(perfis, keepers, falharam, saude_inicial=None, com_poda=True):
    """Roda a poda num ambiente isolado e devolve (saude, linhas_comentadas)."""
    import os
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "shared").mkdir()
        arq = d / "tiktok_perfis.txt"
        arq.write_text("\n".join(p for p, _f, _n in perfis) + "\n", encoding="utf-8")

        _saude, _perfis = T.SAUDE_FONTES, T.PERFIS_TXT
        _falhou = set(T._falhou_listar)
        try:
            T.SAUDE_FONTES = d / "shared" / "fontes_saude.json"
            T.PERFIS_TXT = arq          # é daqui que o _comentar_fonte lê
            if saude_inicial:
                T._salvar_saude(saude_inicial)
            T._falhou_listar.clear()
            T._falhou_listar.update(falharam)
            os.environ["COLETA_PODA_AUTO"] = "1" if com_poda else "0"
            T._atualizar_saude_e_podar(perfis, keepers, dry=False)
            saude = T._ler_saude()
            comentadas = [l for l in arq.read_text(encoding="utf-8").splitlines()
                          if l.strip().startswith("#")]
            return saude, comentadas
        finally:
            T.SAUDE_FONTES, T.PERFIS_TXT = _saude, _perfis
            T._falhou_listar.clear()
            T._falhou_listar.update(_falhou)


# ── o cenário REAL de 04/09, reduzido ────────────────────────────────────────
# 2 fontes renderam, 3 foram bloqueadas. Antes: as 3 levavam rodada 0-keeper.
PERFIS = [(p, "tiktok", "") for p in
          ("dannikafaith", "bestfindhomeitems",          # renderam
           "airlandolists", "homekitchgadgets1", "seyis.shop")]   # bloqueadas
KEEPERS = {"dannikafaith": 12, "bestfindhomeitems": 9}
BLOQUEADAS = {"airlandolists", "homekitchgadgets1", "seyis.shop"}

print("── 1. rodada com bloqueio intermitente (o caso de hoje) ──")
saude, comentadas = rodar(PERFIS, KEEPERS, BLOQUEADAS)
for p in sorted(BLOQUEADAS):
    z = (saude.get(p) or {}).get("zero_seguidas", "ausente")
    checa(f"@{p} bloqueada não foi penalizada", z in (0, "ausente"),
          f"zero_seguidas={z}")
checa("@dannikafaith zerou o contador",
      (saude.get("dannikafaith") or {}).get("zero_seguidas") == 0)

print("\n── 2. fonte que LISTOU e não rendeu CONTINUA sendo punida ──")
# ⚠️ o teste tem de provar os dois lados. Uma correção que só para de punir
# vira "nunca poda nada", e aí a lista enche de fonte morta pra sempre.
perfis2 = PERFIS + [("fonte_morta", "tiktok", "")]
saude2, _ = rodar(perfis2, KEEPERS, BLOQUEADAS)
z = (saude2.get("fonte_morta") or {}).get("zero_seguidas")
checa("@fonte_morta levou rodada 0-keeper", z == 1, f"zero_seguidas={z}")

print("\n── 3. bloqueio NÃO zera o contador (sem imunidade eterna) ──")
# quem já vinha com 2 rodadas ruins e foi bloqueada hoje continua com 2 —
# não volta pra 0 nem sobe pra 3.
inicial = {"airlandolists": {"zero_seguidas": 2, "fonte": "tiktok"}}
saude3, _ = rodar(PERFIS, KEEPERS, BLOQUEADAS, saude_inicial=inicial)
z = (saude3.get("airlandolists") or {}).get("zero_seguidas")
checa("contador preservado em 2", z == 2, f"zero_seguidas={z}")

print("\n── 4. a fonte bloqueada NÃO é comentada do arquivo ──")
# 3 rodadas seguidas de bloqueio = COLETA_ZUMBI_RUNS. Antes, isso comentava.
inicial4 = {p: {"zero_seguidas": 2, "fonte": "tiktok"} for p in BLOQUEADAS}
_, comentadas4 = rodar(PERFIS, KEEPERS, BLOQUEADAS, saude_inicial=inicial4)
vivas = [c for c in comentadas4 if any(b in c for b in BLOQUEADAS)]
checa("nenhuma bloqueada foi comentada", not vivas,
      f"{len(vivas)} comentada(s)" if vivas else "arquivo intacto")

print("\n── 5. a trava POR CANAL de 18/08 continua valendo ──")
saude5, _ = rodar(PERFIS, {}, set())      # ninguém rendeu, ninguém bloqueado
zs = [(saude5.get(p) or {}).get("zero_seguidas", "ausente")
      for p, _f, _n in PERFIS]
checa("canal mudo não penaliza ninguém", all(z in (0, "ausente") for z in zs),
      f"{zs}")

print()
if falhas:
    print(f"❌ {len(falhas)} falha(s): {', '.join(falhas)}")
    sys.exit(1)
print("✅ tudo passou")
