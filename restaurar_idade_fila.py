#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# restaurar_idade_fila.py -- devolve a idade real das pastas de pronto_para_postar
#
# O ESTRAGO (09/09/2026)
# ──────────────────────
# O Dre: *"vídeos com formato antigo está voltando... isso é o lado ruim, vai
# quebrar o perfil novamente"*.
#
# Ele está certo, e a causa fui eu. Medido: **185 de 310 pastas** com data
# falsificada, TODAS empatadas na mesma hora — a hora em que rodou o
# `conferir_match --fila --marcar`.
#
#     idade PASTA   idade REAL   pacote
#            0.3d       23.8d    travesseiro_de_posicionamento_corporal
#            0.3d       20.4d    série_11_relógio_t800_t900_ultra_2_smart
#            0.3d       19.8d    capa_magnética_de_vidro_fosco_luxo
#
# ⚠️ POR QUE ISSO QUEBRA O PERFIL: o daemon ordena a fila pelo MTIME DA PASTA
# (`daemon_maestro._drenar_por_idade`) e o Dre está com `ordem_da_fila:
# mais_novo`. Vídeo de 24 dias, do formato que ele ABANDONOU, carimbado como
# novo, sobe pro topo e vai ao ar na frente do formato atual.
#
# ⚠️ E A CAUSA É BOBA: o `_frames` do juiz escrevia `video.match0.jpg` AO LADO
# do vídeo. Criar e apagar arquivo DENTRO de uma pasta zera o mtime dela. Uma
# passada do juiz na fila inteira rejuvenesceu tudo que ele olhou.
#
# ⚠️⚠️ É A SEGUNDA VEZ EM 48 HORAS. O `consertar_audio_fila` fez o mesmo em
# 06/09 (41 pacotes). Eu documentei o erro em dois arquivos, escrevi
# "TEMPORÁRIO FORA DA PASTA" nos dois — e não fui procurar o mesmo padrão nos
# outros. Consertei a OCORRÊNCIA e não a CLASSE, e ela voltou maior: 41 → 185.
#
# DE ONDE VEM A IDADE VERDADEIRA
# `shared/content_plans/plano_<slug>.json` é escrito uma vez, no momento da
# produção (`produzir_tiktok:770`), e nenhuma dessas ferramentas encosta nele.
# É a única testemunha que sobrou.
#
#   .venv/bin/python restaurar_idade_fila.py            # só mostra
#   .venv/bin/python restaurar_idade_fila.py --aplicar  # devolve as datas
import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRONTOS = BASE / "pronto_para_postar"
PLANOS = BASE / "shared" / "content_plans"
# diferença a partir da qual eu chamo de falsificada. 3 dias porque uma pasta
# pode ter sido tocada legitimamente (o daemon escreve `postado.json` ao postar)
# e eu não quero corrigir o que não está errado.
MARGEM_DIAS = float(os.environ.get("IDADE_MARGEM_DIAS", "3"))


def precisa_corrigir(idade_pasta: float, idade_real, margem: float = MARGEM_DIAS) -> bool:
    """A pasta está mais NOVA que o plano por mais que a margem? Pura, testável.

    ⚠️ SÓ CORRIGE NUM SENTIDO — pasta mais nova que o plano. O contrário (pasta
    mais VELHA que o plano) não é falsificação: é pacote que ninguém tocou desde
    que foi feito, e mexer nele seria eu inventar dado em cima de dado bom.
    """
    if idade_real is None:
        return False
    return (idade_real - idade_pasta) > margem


def main() -> int:
    aplicar = "--aplicar" in sys.argv[1:]
    if not PRONTOS.exists():
        print(f"❌ {PRONTOS} não existe")
        return 1

    agora = time.time()
    achados = []
    sem_plano = 0
    for pasta in sorted(PRONTOS.iterdir()):
        if not pasta.is_dir():
            continue
        pl = PLANOS / f"plano_{pasta.name}.json"
        if not pl.exists():
            sem_plano += 1
            continue
        m_pasta, m_real = pasta.stat().st_mtime, pl.stat().st_mtime
        i_pasta, i_real = (agora - m_pasta) / 86400, (agora - m_real) / 86400
        if precisa_corrigir(i_pasta, i_real):
            achados.append((pasta, m_real, i_pasta, i_real))

    total = sum(1 for p in PRONTOS.iterdir() if p.is_dir())
    print(f"\n📦 {total} pasta(s) na fila · {sem_plano} sem plano (não dá pra saber)")
    print(f"🕰️  {len(achados)} com data falsificada (>{MARGEM_DIAS:.0f}d de diferença)\n")
    if not achados:
        print("✅ nada a corrigir")
        return 0

    achados.sort(key=lambda x: -x[3])
    print(f"{'pasta':>8} {'real':>8}  pacote")
    for pasta, _m, i_p, i_r in achados[:15]:
        print(f"{i_p:7.1f}d {i_r:7.1f}d  {pasta.name[:50]}")
    if len(achados) > 15:
        print(f"   … e mais {len(achados)-15}")

    if not aplicar:
        print(f"\n   (nada foi alterado — use --aplicar)")
        print(f"   ⚠️ com `ordem_da_fila: mais_novo`, estes {len(achados)} estão "
              f"furando a fila\n      na frente do formato novo.")
        return 0

    n = 0
    for pasta, m_real, _i_p, _i_r in achados:
        try:
            os.utime(pasta, (m_real, m_real))
            n += 1
        except Exception as e:
            print(f"   ⚠️ {pasta.name[:40]}: {str(e)[:50]}")
    print(f"\n   ✅ {n} pasta(s) com a idade devolvida")
    print(f"   O daemon volta a ordenar pela data REAL de produção.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
