#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_corte_intro.py -- prova a MATEMÁTICA do corte de intro sem precisar de
# ffmpeg nem de vídeo. Roda em qualquer máquina, em ~0s.
#
# POR QUE ASSIM: o `_corte_intro` é ffmpeg + decisão. Se eu testasse o conjunto,
# precisaria de vídeo de amostra e o teste só rodaria na VPS — ou seja, nunca.
# A decisão pura (`_onde_comeca_acao`) recebe os `diffs` já medidos, então dá pra
# fabricar o caso e conferir o número. Foi por isso que ela nasceu separada.
#
# Uso:  python3 teste_corte_intro.py
import sys

from tiktok_coletor import _onde_comeca_acao, _perfis_do_arquivo, _CORTE_PERFIL

DT = 0.2          # 5 fps, igual ao CORTE_INTRO_FPS padrão
BASE = 12.0       # movimento típico de um vídeo de produto (mediana do meio)

falhas = []


def checa(nome, obtido, esperado):
    ok = abs(obtido - esperado) < 0.051
    print(f"  {'✅' if ok else '❌'} {nome}: {obtido:.2f}s (esperado {esperado:.2f}s)")
    if not ok:
        falhas.append(nome)


def parado(n):
    """n frames de carimbo: só ruído de compressão."""
    return [0.4] * n


def acao(n):
    """n frames de produto se mexendo, em volta da BASE."""
    return [BASE * f for f in ([1.1, 0.9, 1.2, 0.8, 1.0] * ((n // 5) + 1))[:n]]


print("── 1. o caso do Dre: 2s de carimbo 'Amazon Gadgets', depois a ação ──")
# 10 diffs parados = frames 0..10 iguais ⇒ carimbo até t=10*0.2=2.0s
checa("carimbo de 2s", _onde_comeca_acao(parado(10) + acao(10), DT, BASE), 2.0)

print("\n── 2. já começa na ação (a maioria) → NÃO cortar ──")
checa("ação no frame 0", _onde_comeca_acao(acao(20), DT, BASE), 0.0)

print("\n── 3. intro ANIMADA (texto entrando) → o detector não vê, e ADMITE ──")
checa("intro com movimento", _onde_comeca_acao(acao(20), DT, BASE), 0.0)

print("\n── 4. vídeo inteiro paradão (produto no pedestal) → sem régua, não corta ──")
# ⚠️ é o caso que mata detector ingênuo: sem a BASE do meio do vídeo, uns
# poucos frames quietos no começo pareceriam intro e ele comeria o produto.
checa("base ~0", _onde_comeca_acao(parado(20), DT, 0.3), 0.0)

print("\n── 5. quietinho de menos (0,4s) → não é carimbo, é só um instante ──")
checa("2 frames quietos", _onde_comeca_acao(parado(2) + acao(18), DT, BASE), 0.0)
checa("3 frames quietos (0,6s)", _onde_comeca_acao(parado(3) + acao(17), DT, BASE), 0.6)

print("\n── 6. janela TODA quieta → não sei onde a ação começa, não corto ──")
checa("nenhum salto na janela", _onde_comeca_acao(parado(20), DT, BASE), 0.0)

print("\n── 7. carimbo com leve tremida (vídeo recomprimido) ──")
# 35% da base é o limiar: 4.0 < 12*0.35 = 4.2 ⇒ ainda conta como parado
checa("tremida abaixo do limiar",
      _onde_comeca_acao([4.0] * 8 + acao(12), DT, BASE), 1.6)
checa("tremida acima do limiar",
      _onde_comeca_acao([5.0] * 8 + acao(12), DT, BASE), 0.0)

print("\n── 8. o parser do tiktok_perfis.txt: `corte=` e `#nicho` juntos ──")
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "perfis.txt"
    p.write_text(
        "# comentario\n"
        "simples\n"
        "com_nicho #casa\n"
        "com_corte corte=2\n"
        "@ambos #tech corte=1.5\n"
        "ordem_trocada corte=3 #pet\n"
        "virgula corte=2,5\n"
        "\n", encoding="utf-8")
    _CORTE_PERFIL.clear()
    linhas = _perfis_do_arquivo(p, "tiktok")

esperado = [("simples", ""), ("com_nicho", "casa"), ("com_corte", ""),
            ("@ambos", "tech"), ("ordem_trocada", "pet"), ("virgula", "")]
obtido = [(pf, nc) for pf, _f, nc in linhas]
ok = obtido == esperado
print(f"  {'✅' if ok else '❌'} perfil+nicho: {obtido}")
if not ok:
    falhas.append("parser perfil/nicho")
    print(f"     esperado: {esperado}")

cortes_esp = {"com_corte": 2.0, "ambos": 1.5, "ordem_trocada": 3.0, "virgula": 2.5}
ok = _CORTE_PERFIL == cortes_esp
print(f"  {'✅' if ok else '❌'} cortes: {_CORTE_PERFIL}")
if not ok:
    falhas.append("parser corte=")
    print(f"     esperado: {cortes_esp}")

print("\n── 9. as TRAVAS: nenhum corte pode roubar o vídeo ──")
# ⚠️ é a parte que mais importa. Sem teto, um `corte=10` num clipe de 12s
# deixaria 2s e o render alongaria em loop — vídeo pior que o original.
import os

os.environ.pop("CORTE_INTRO_AUTO", None)      # aqui testo só o caminho FIXO
_falso = Path("/tmp/nao-existe.mp4")

from tiktok_coletor import _corte_intro

_CORTE_PERFIL.clear()
_CORTE_PERFIL.update({"curto": 2.0, "guloso": 10.0, "normal": 2.0})
# teto = min(CORTE_INTRO_MAX=4s, 25% da duração); sobra mínima = 6s
checa("2s num vídeo de 20s (folgado)", _corte_intro(_falso, 20.0, "normal"), 2.0)
checa("10s num vídeo de 20s → teto de 4s", _corte_intro(_falso, 20.0, "guloso"), 4.0)
checa("2s num vídeo de 7s → sobrariam 5s", _corte_intro(_falso, 7.0, "curto"), 0.0)
checa("perfil sem marcação", _corte_intro(_falso, 20.0, "ninguem"), 0.0)

print()
if falhas:
    print(f"❌ {len(falhas)} falha(s): {', '.join(falhas)}")
    sys.exit(1)
print("✅ tudo passou")
