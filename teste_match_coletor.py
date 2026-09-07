#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_match_coletor.py -- o juiz de imagem está LIGADO no coletor, e decide certo?
#
# POR QUE ISTO EXISTE (07/09/2026)
# ────────────────────────────────
# O `--olho` mediu: 38% dos vídeos produzidos não mostram o produto anunciado
# (23 de 60). O juiz que pega isso — `conferir_match.conferir` — já existia,
# já tinha sido VALIDADO com controle negativo (87% reprovado no embaralhado vs
# 53% no real, z≈5,4) e rodava só como auditoria, depois do estrago.
#
# ⚠️ ESTE TESTE OLHA A FIAÇÃO, e o motivo é que esta semana esse foi o defeito
# TRÊS vezes: o `_so_musica` sem chamador, as trilhas que nada lia, o
# `comentarios.py` escrito e morto por 5 dias. Testar só a regra passaria 100%
# com o coletor ignorando o juiz — que é exatamente o estado anterior.
#
# ⚠️ E A ASSIMETRIA DAS DUAS PORTAS TEM QUE FICAR TRAVADA:
#   · juiz indisponível  → DEIXA PASSAR (match ruim é post fraco)
#   · regra +18 ausente  → NÃO COLHE    (irreversível no grupo do cliente)
# Se alguém "uniformizar" isso um dia, uma das duas vira defeito grave.
#
#   python3 teste_match_coletor.py
import ast
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
_src = (BASE / "tiktok_coletor.py").read_text("utf-8")
_arv = ast.parse(_src)

_ns = {}
for _no in _arv.body:
    if isinstance(_no, ast.FunctionDef) and _no.name == "reprova_match":
        exec(compile(ast.Module([_no], []), "x", "exec"), _ns)
reprova_match = _ns.get("reprova_match")

ok = falhou = 0


def checa(desc, cond, extra=""):
    global ok, falhou
    if cond:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}" + (f"\n      {extra}" if extra else ""))


print("\n── a regra: só 'nao' descarta ──")
checa("reprova_match existe", reprova_match is not None)
if reprova_match:
    checa("'nao' descarta", reprova_match("nao"))
    # ⚠️ o prompt do juiz MANDA responder TALVEZ na dúvida; descartar nele
    # mataria a oferta por incerteza do juiz, não por defeito do pacote
    checa("'talvez' NÃO descarta", not reprova_match("talvez"))
    checa("'sim' NÃO descarta", not reprova_match("sim"))
    checa("'erro' NÃO descarta (API que piscou não é evidência)",
          not reprova_match("erro"))
    checa("'sem_foto' NÃO descarta", not reprova_match("sem_foto"))
    checa("vazio NÃO descarta", not reprova_match(""))
    checa("None NÃO descarta", not reprova_match(None))
    checa("'NAO' maiúsculo descarta", reprova_match("NAO"))
    checa("' nao ' com espaço descarta", reprova_match(" nao "))

print("\n── ⚠️ A FIAÇÃO: o coletor chama o juiz? ──")
_fonte = ast.dump(_arv)
checa("importa `conferir_match`", "'conferir_match'" in _fonte)
checa("chama `conferir` (o juiz validado)", "'conferir'" in _fonte)
checa("usa `reprova_match` na decisão, não string solta",
      _src.count("reprova_match(") >= 1)
checa("grava `match_video` no plano.json", '"match_video"' in _src)
checa("tem interruptor MATCH_NO_COLETOR", "MATCH_NO_COLETOR" in _src)

print("\n── ⚠️ AS DUAS PORTAS FALHAM PRA LADOS OPOSTOS ──")
# o juiz de match deixa passar quando some; a regra de +18 barra quando some.
# Este teste existe pra que "uniformizar" isso um dia falhe em vez de passar.
_i_juiz = _src.find("juiz indisponível")
_i_18 = _src.find("regra indisponível")
checa("juiz de match indisponível → 'deixo passar'",
      _i_juiz > 0 and "deixo passar" in _src[_i_juiz:_i_juiz + 200])
checa("regra +18 indisponível → não colhe (_v18 = True)",
      _i_18 > 0 and "_v18, _m18 = True" in _src)

print("\n── o juiz de verdade continua importável e com a mesma cara ──")
_cm = ast.parse((BASE / "conferir_match.py").read_text("utf-8"))
_fns = {n.name for n in _cm.body if isinstance(n, ast.FunctionDef)}
for nome in ("conferir", "_frame", "_baixar_imagem"):
    checa(f"conferir_match.{nome} existe", nome in _fns)
# ⚠️ o juiz é IMPORTADO, nunca copiado: duas cópias seriam dois juízes, e um
# deles desatualizado sem ninguém saber
checa("o coletor não tem uma cópia do prompt do juiz",
      "_PROMPT" not in _src or "Duas imagens" not in _src)

print(f"\n{'='*64}\n   {ok} passou · {falhou} falhou\n{'='*64}")
raise SystemExit(1 if falhou else 0)
