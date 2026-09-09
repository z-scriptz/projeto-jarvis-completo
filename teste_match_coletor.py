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
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
_src = (BASE / "tiktok_coletor.py").read_text("utf-8")
_arv = ast.parse(_src)

_ns = {"os": __import__("os"), "time": __import__("time"), "re": re}
for _alvo in ("reprova_match", "feed_vazio", "_norm_produto",
              "_produto_queimado", "_marcar_reprovado", "_limpar_reprovado"):
    for _no in _arv.body:
        if isinstance(_no, ast.FunctionDef) and _no.name == _alvo:
            exec(compile(ast.Module([_no], []), "x", "exec"), _ns)
reprova_match = _ns.get("reprova_match")
feed_vazio = _ns.get("feed_vazio")
_norm_produto = _ns.get("_norm_produto")
_produto_queimado = _ns.get("_produto_queimado")
_marcar_reprovado = _ns.get("_marcar_reprovado")
_limpar_reprovado = _ns.get("_limpar_reprovado")

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

print("\n── ⚠️ TRÊS QUADROS, NÃO UM: o vídeo de haul tem dez produtos ──")
# o quadro do meio cai em qualquer um deles; foi assim que o juiz reprovou
# 'suporte para lavar boné' contra *Suporte Para Lavar Bonés Na Máquina*
checa("o coletor pede vários quadros (`_frames`)", "_frames" in _src)
checa("tem interruptor MATCH_FRAMES", "MATCH_FRAMES" in _src)
_cm_src = (BASE / "conferir_match.py").read_text("utf-8")
checa("o prompt do juiz pergunta por 'algum dos quadros'",
      "ALGUM dos quadros" in _cm_src)
checa("conferir() aceita lista de quadros", "isinstance(frame, (list, tuple))" in _cm_src)

print("\n── o juiz de verdade continua importável e com a mesma cara ──")
_cm = ast.parse((BASE / "conferir_match.py").read_text("utf-8"))
_fns = {n.name for n in _cm.body if isinstance(n, ast.FunctionDef)}
for nome in ("conferir", "_frame", "_frames", "_baixar_imagem"):
    checa(f"conferir_match.{nome} existe", nome in _fns)
# ⚠️ o juiz é IMPORTADO, nunca copiado: duas cópias seriam dois juízes, e um
# deles desatualizado sem ninguém saber
checa("o coletor não tem uma cópia do prompt do juiz",
      "_PROMPT" not in _src or "Duas imagens" not in _src)

print("\n── ⚠️ A FILA DE POSTAGEM TEM PONTO CEGO ──")
# 138 de 349 videos em pronto_para_postar nao casam com pacote nenhum (a
# origem foi podada). Sem plano.json, nenhum modo do auditor os alcanca -- e
# sao 40% do que ainda vai ao ar.
checa("existe o modo --fila", '"--fila"' in _cm_src)
checa("o --fila le o engajamento.json (o que sobra na pasta pronta)",
      "engajamento.json" in _cm_src)
checa("na fila o juiz e o do NOME (nao ha foto da loja)",
      "a.sem_foto = True" in _cm_src)
# ⚠️ tirar por CAMINHO, nao por slug: na fila a pasta ja esta na mao, e
# recalcular o slug seria inventar uma chance de errar onde nao ha duvida
checa("na fila tira a pasta por caminho (_tirar_pasta)",
      "_tirar_pasta(pj.parent)" in _cm_src)
checa("so 'nao' tira da fila (erro/talvez nao tiram)",
      'veredito == "nao"' in _cm_src)
checa("move pra fora de pronto_para_postar",
      'REPROVADOS = BASE_DIR / "reprovado_match"' in _cm_src)

print("\n── ⚠️ MATAR A RODADA NÃO PODE FAZER PAGAR DE NOVO ──")
# O Dre matou uma rodada de ~R$48 as 3h da manha. O cache `vistos` so era
# gravado na ULTIMA linha, entao tudo que ja tinha sido julgado (e pago)
# voltaria na rodada seguinte pra ser pago outra vez.
checa("grava o cache DURANTE a rodada, não só no fim",
      "_desde_gravou" in _src and "COLETA_GRAVA_CADA" in _src)
_i_add = _src.find("vistos.add(vid)")
_i_grava = _src.find("_desde_gravou >= _GRAVA_CADA")
checa("a gravação periódica vem logo depois de marcar como visto",
      0 < _i_add < _i_grava < _i_add + 1200,
      f"add={_i_add} grava={_i_grava}")
# ⚠️ o --dry nao pode persistir: senao a rodada real pula tudo que o teste viu
checa("o --dry continua sem gravar cache", "if not dry and _desde_gravou" in _src)
checa("o salvamento do fim continua lá (a rodada completa grava tudo)",
      "_salvar_vistos(vistos)" in _src and _src.count("_salvar_vistos(") >= 3)

print("\n── ⚠️ FONTE MORTA vs TIKTOK ME BLOQUEOU ──")
# a poda por coleta apaga quem volta 0 video. Se bloqueio entrasse por esse
# caminho, apagaria as 42 melhores fontes do Dre com o log dizendo "zumbi".
checa("feed_vazio existe", feed_vazio is not None)
if feed_vazio:
    # o retorno REAL do TikTok hoje, copiado do log do nightly
    checa("perfil resolve com entries:[null] → feed vazio",
          feed_vazio({"id": "MS4wLjAB", "title": "airlandolists",
                      "entries": [None], "playlist_count": 0}))
    checa("entries:[] também é feed vazio",
          feed_vazio({"title": "x", "entries": []}))
    checa("sem entries nenhum é feed vazio", feed_vazio({"title": "x"}))
    # ⚠️ O LADO QUE NÃO PODE DISPARAR: perfil com video de verdade
    checa("perfil COM vídeo não é feed vazio",
          not feed_vazio({"title": "x", "entries": [{"id": "1", "url": "u"}]}))
    checa("um vídeo entre nulls não é feed vazio",
          not feed_vazio({"title": "x", "entries": [None, {"id": "1"}]}))
    # sem id nem titulo o perfil nem resolveu — é outro erro, nao este
    checa("resposta sem id/título NÃO vira 'feed vazio'",
          not feed_vazio({"entries": []}))
    checa("None não quebra", not feed_vazio(None))
    checa("lista no lugar de dict não quebra", not feed_vazio([]))

print("\n── ⚠️ O MESMO PRODUTO REPROVADO 50× NÃO PAGA O JUIZ 50× ──")
# @miniluxury.perfume: ~50 videos, quase todos casando com o MESMO item
# (*Mini Frasco De Perfume 2ml 100PCS Spray Recar*), quase todos DESCARTO —
# cada um pagando 3 quadros de novo. O dedup nao pega porque `produtos_vistos`
# so marca o que FICOU: ele lembra dos acertos e esquece dos erros.
checa("_produto_queimado existe", _produto_queimado is not None)
checa("_marcar_reprovado existe", _marcar_reprovado is not None)
if _produto_queimado and _marcar_reprovado and _limpar_reprovado and _norm_produto:
    _pr = {}
    _ch = _norm_produto("Mini Frasco De Perfume 2ml 100PCS Spray Recarregável")
    checa("1ª reprovação não queima", _marcar_reprovado(_ch, _pr) == 1
          and not _produto_queimado(_ch, _pr, limite=3))
    checa("2ª reprovação não queima", _marcar_reprovado(_ch, _pr) == 2
          and not _produto_queimado(_ch, _pr, limite=3))
    checa("3ª reprovação QUEIMA", _marcar_reprovado(_ch, _pr) == 3
          and _produto_queimado(_ch, _pr, limite=3))
    # ⚠️ tem que valer pro MESMO produto vindo de video diferente: a chave e o
    # nome NORMALIZADO da loja, nao o id do video
    checa("outro vídeo do mesmo produto cai na mesma chave",
          _produto_queimado(_norm_produto("mini frasco de perfume 2ml 100pcs spray recarregavel"),
                            _pr, limite=3))
    checa("produto diferente NÃO é atingido",
          not _produto_queimado(_norm_produto("Suporte para lavar bonés"), _pr, limite=3))

    print("\n   ── e a conta tem que poder ser desfeita ──")
    # ⚠️ so 'sim' limpa. 'talvez' e a resposta que o prompt manda dar na duvida:
    # ausencia de evidencia, nao evidencia do par certo. Se 'talvez' zerasse, o
    # laco voltaria sozinho.
    _limpar_reprovado(_ch, _pr)
    checa("juiz disse 'sim' → a conta zera", not _produto_queimado(_ch, _pr, limite=3))
    _pr2 = {"x": {"n": 9, "ts": 0}}      # ts=0 → epoch, muito além da janela
    checa("conta velha (fora de MATCH_REPROVA_DIAS) expira",
          not _produto_queimado("x", _pr2, limite=3, dias=30))
    checa("limite 0 desliga o guarda",
          not _produto_queimado(_ch, {_ch: {"n": 99, "ts": 2**31}}, limite=0))

    print("\n   ── ⚠️ falha pro lado de DEIXAR PASSAR (é economia, não segurança) ──")
    checa("cache vazio não barra ninguém", not _produto_queimado(_ch, {}, limite=3))
    checa("formato antigo (int solto) não barra",
          not _produto_queimado("x", {"x": 12345}, limite=3))
    checa("chave vazia não barra", not _produto_queimado("", {"": {"n": 9, "ts": 2**31}}, limite=3))
    checa("registro sem 'n' não quebra", not _produto_queimado("x", {"x": {}}, limite=3))

print("\n── ⚠️ A FIAÇÃO DO GUARDA: pula ANTES de pagar? ──")
# depois do juiz nao economizaria nada -- ja teria sido pago.
_i_ded = _src.find("_produto_repetido(chave_prod")
_i_queim = _src.find("_produto_queimado(chave_prod")
_i_baixar = _src.find("arq = arq_pre or _baixar(")
_i_juizc = _src.find("_frames_do_video(arq")
checa("o coletor chama _produto_queimado", _i_queim > 0)
checa("o pulo vem DEPOIS do dedup e ANTES do download",
      0 < _i_ded < _i_queim < _i_baixar,
      f"dedup={_i_ded} queimado={_i_queim} baixar={_i_baixar}")
checa("e antes dos 3 quadros do juiz", 0 < _i_queim < _i_juizc)
checa("marca a reprovação onde o juiz reprova",
      "_marcar_reprovado(chave_prod" in _src)
checa("o cache dos reprovados é gravado durante a rodada",
      _src.count("_salvar_reprovados(") >= 3)
checa("o --dry continua sem gravar", "if not dry and _desde_gravou" in _src)
checa("tem interruptor MATCH_MAX_REPROVA", "MATCH_MAX_REPROVA" in _src)
checa("conta o que pulou (senão a economia some no log)",
      "barrados_queimado" in _src)

print(f"\n{'='*64}\n   {ok} passou · {falhou} falhou\n{'='*64}")
raise SystemExit(1 if falhou else 0)
