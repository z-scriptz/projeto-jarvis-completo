#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_nome_produto.py -- o juiz de texto lê a resposta certo, e falha pro lado seguro?
#
# POR QUE ISTO EXISTE (08/09/2026)
# ────────────────────────────────
# Este juiz roda em CADA coleta, decidindo se um termo vira pacote ou vai pro
# lixo. Errar pra um lado deixa 'salva não perder nenhum' ir ao ar; errar pro
# outro apaga produto bom em silêncio, em volume, todo dia.
#
# ⚠️ O LADO PERIGOSO É O SEGUNDO, e é por isso que a metade de baixo deste
# arquivo é sobre resposta ESTRANHA. Um parser que caia em 'frase' quando não
# entendeu a resposta transformaria cada instabilidade da API num descarte —
# e o log diria "não é produto", que soa como decisão, não como falha.
#
#   python3 teste_nome_produto.py
import ast
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
_src = (BASE / "nome_e_produto.py").read_text("utf-8")
_ns = {}
for _no in ast.parse(_src).body:
    if isinstance(_no, ast.FunctionDef) and _no.name in ("ler_veredito", "bloqueia"):
        exec(compile(ast.Module([_no], []), "x", "exec"), _ns)
ler_veredito = _ns["ler_veredito"]
bloqueia = _ns["bloqueia"]

ok = falhou = 0


def checa(desc, cond, extra=""):
    global ok, falhou
    if cond:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}" + (f"\n      {extra}" if extra else ""))


print("\n── o formato que eu pedi ──")
checa("PRODUTO lido", ler_veredito("PRODUTO | nomeia um objeto") == "produto")
checa("FRASE lida", ler_veredito("FRASE | verbo conjugado, é conversa") == "frase")

print("\n── variações que o modelo produz sozinho ──")
checa("minúsculo", ler_veredito("produto | pantufa é objeto") == "produto")
checa("negrito do markdown", ler_veredito("**FRASE** | opinião") == "frase")
checa("espaço na frente", ler_veredito("   PRODUTO | kit de loja") == "produto")
checa("sem a barra", ler_veredito("PRODUTO") == "produto")
checa("FRASE sem a barra", ler_veredito("FRASE") == "frase")

print("\n── ⚠️ O LADO CARO: resposta estranha NÃO pode virar 'frase' ──")
# cada uma destas viraria um descarte silencioso se o parser fosse generoso
checa("resposta vazia → erro", ler_veredito("") == "erro")
checa("None → erro", ler_veredito(None) == "erro")
checa("modelo enrolou → erro",
      ler_veredito("Não tenho certeza sobre este texto.") == "erro")
checa("só o motivo, sem veredito → erro",
      ler_veredito("| parece nome de produto") == "erro")
checa("resposta em inglês → erro", ler_veredito("PRODUCT | it is an object") == "erro")
# ⚠️ 'FRASE' DENTRO DA EXPLICAÇÃO não pode decidir: só o PREFIXO decide
checa("'frase' no meio de uma resposta PRODUTO não vira frase",
      ler_veredito("PRODUTO | não é frase, nomeia objeto") == "produto")

print("\n── só 'frase' bloqueia ──")
checa("'frase' bloqueia", bloqueia("frase"))
checa("'produto' NÃO bloqueia", not bloqueia("produto"))
checa("'erro' NÃO bloqueia (API fora não é veredito)", not bloqueia("erro"))
checa("vazio NÃO bloqueia", not bloqueia(""))
checa("None NÃO bloqueia", not bloqueia(None))

print("\n── ⚠️ O CONTROLE MEDE OS DOIS LADOS ──")
# medir só "pega frase" premiaria um juiz que reprova tudo
checa("tem lista de FRASES rotuladas", "FRASES = [" in _src)
checa("tem lista de PRODUTOS rotuladas", "PRODUTOS = [" in _src)
checa("o controle mede 'poupa produto'", "poupa produto" in _src)
# ⚠️ o piso de poupar produto e MAIOR que o de pegar frase, de proposito:
# deixar frase passar e feio e raro; reprovar produto e caro e roda todo dia
checa("piso de poupar produto é 90", "pp < 90" in _src)
checa("piso de pegar frase é mais baixo (60)", "pf < 60" in _src)
checa("o controle sabe dizer NÃO LIGUE", "NÃO LIGUE" in _src)

print("\n── ⚠️ 'Escova lava carro' É O CASO QUE NÃO PODE MORRER ──")
# 'lava' é verbo conjugado — o sinal mais óbvio de "frase" — e mesmo assim é
# produto. Ele está na lista de controle de propósito, como armadilha.
checa("'Escova lava carro giratória' está no controle como PRODUTO",
      "Escova lava carro giratória" in _src.split("PRODUTOS = [")[1][:900])
checa("as frases do controle vieram da fila real (não inventadas)",
      "salva não perder nenhum" in _src and "Valem cada centavoo" in _src)

print("\n── move, não apaga ──")
checa("a quarentena é uma pasta separada",
      'REPROVADOS = BASE_DIR / "reprovado_nome"' in _src)
checa("usa rename, não unlink/rmtree",
      "pasta.rename(destino)" in _src and "rmtree" not in _src)

print("\n── ⚠️ A FIAÇÃO: o coletor chama o juiz? ──")
# quinta vez nesta semana que o defeito seria "escrevi o modulo e nao liguei"
_col = (BASE / "tiktok_coletor.py").read_text("utf-8")
checa("o coletor importa nome_e_produto", "from nome_e_produto import" in _col)
checa("usa `bloqueia`, não compara string solta", "_bn(_vn)" in _col)
checa("tem interruptor JUIZ_NOME", "JUIZ_NOME" in _col)
# ⚠️ ANTES da busca na loja: termo que nao e produto nao tem o que procurar
_i_juiz = _col.find("não é nome de produto")
_i_loja = _col.find("m = minerar_oportunidades(termo)")
checa("julga ANTES da busca na loja (e antes do download)",
      0 < _i_juiz < _i_loja, f"juiz={_i_juiz} loja={_i_loja}")
# ⚠️ falha PRA PASSAR, igual ao juiz de match e ao contrario do filtro +18
checa("juiz indisponível deixa passar (não barra)",
      "juiz de nome off" in _col)

print(f"\n{'='*66}\n   {ok} passou · {falhou} falhou\n{'='*66}")
raise SystemExit(1 if falhou else 0)
