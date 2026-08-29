#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# enriquecer_fila.py — põe os NÚMEROS de volta nos produtos que já estão na fila.
#
# ⚠️ POR QUE ISTO EXISTE (29/08). O `telegram_repurpose_hunter` gravava cada
# produto com `classe: ""` e sem `vendas`, `rating` nem comissão — os campos
# vinham na MESMA resposta da API de afiliado que ele já buscava pra pegar a
# foto, e eram descartados na linha seguinte. Isso foi corrigido no hunter, mas
# a correção só vale pro que chegar DEPOIS dela.
#
# Medido no dia: 276 produtos na fila, 54 disponíveis pro grupo, **54 sem
# classe**. Ordenar por qualidade uma lista onde todo mundo empata em "não sei"
# é o mesmo que não ordenar — o `postar_grupo` continuaria postando por ordem
# de chegada com um ranking instalado por cima, e o log pareceria correto.
# 📌 Conserto que só vale pro futuro deixa o presente quebrado com cara de
# consertado — que é pior que quebrado com cara de quebrado.
#
# ⚠️ SÓ ACRESCENTA. Nenhum campo existente é sobrescrito: se o produto já tem
# `vendas`, ele passa batido e não gasta chamada. Produto cuja consulta falha
# fica exatamente como estava — sem classe, que quer dizer "não sei", e o
# `postar_grupo` já sabe que "não sei" fica atrás de quem tem número, nunca
# fora.
#
# ⚠️ LIMITADO POR PADRÃO, e por experiência própria: cada produto custa um
# redirect + uma chamada GraphQL. Um `--limite 0` como default é o mesmo erro
# que o `fila[:80]` escondia no `validar_fila` — rodada que não termina.
#
# USO (na VPS, dentro de ~/jarvis):
#   .venv/bin/python enriquecer_fila.py                 # simula 25 (não grava)
#   .venv/bin/python enriquecer_fila.py --aplicar
#   .venv/bin/python enriquecer_fila.py --limite 60 --aplicar
#   .venv/bin/python enriquecer_fila.py --so-disponiveis --aplicar   # só o que
#                                       o grupo ainda não postou (o que urge)

import argparse
import json
import os
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

FILA = BASE_DIR / "shared" / "produtos_fila.json"
POSTADOS = BASE_DIR / "shared" / "grupo_postados.json"

try:
    from shared.trava import travar
except Exception:                    # sem a trava, seguir é melhor que parar
    from contextlib import contextmanager

    @contextmanager
    def travar(_nome, base=None):
        yield True

# Os campos que a API devolve e que a fila precisa guardar. Os NOMES são os
# mesmos que o `curar_fila` usa — ver o comentário no hunter: nome divergente
# produz item que parece completo e não é lido por ninguém.
CAMPOS = ("vendas", "rating", "comissao_rate", "comissao_valor")

# Dias antes de reperguntar por um produto cuja consulta falhou. Anúncio sai do
# ar e volta; o que não pode é pagar a mesma falha toda rodada.
RETENTAR_APOS = 7


def _log(m):
    print(f"   {m}", flush=True)


def _carregar(caminho: Path, padrao):
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:
        return padrao


def _tem_numeros(item: dict) -> bool:
    """Este produto já foi MEDIDO? (pergunta de fato, sem política)

    ⚠️ SEPARADA DO `_precisa` DEPOIS DE ELE ME MORDER. Eu tinha só o
    `_precisa`, e quando acrescentei a memória de falha ele passou a devolver
    False por DOIS motivos diferentes: "já tem número" e "falhou faz pouco,
    não pergunta agora". O passo de reclassificação lia `not _precisa(...)`
    como "tem número" e classificou como `fraco` um produto sem medição
    nenhuma — vendas 0 e comissão 0 porque os campos não existiam.
    📌 `fraco` é uma afirmação: "eu medi e é ruim". Dizer isso sobre o que
    nunca foi medido é o mesmo erro do default inventado — um valor plausível
    no lugar de "não sei"."""
    return all(c in item for c in CAMPOS)


def _precisa(item: dict, agora: float = None) -> bool:
    """Vale gastar uma chamada com este produto agora? (pergunta de política)

    ⚠️ `vendas: 0` NÃO é ausência — é um produto medido que não vendeu, e
    consultar de novo toda rodada seria pagar pela mesma resposta pra sempre. A
    pergunta é se a CHAVE existe, não se o valor é verdadeiro.

    ⚠️ E FALHA TAMBÉM É RESPOSTA. Na 1ª rodada real, 51 produtos não
    resolveram (link morto, produto fora do ar, plataforma que não é Shopee) —
    e a rodada seguinte tentou os MESMOS 51, um por um, 1,5s cada, até o Dre
    dar Ctrl+C. Sem memória do fracasso, cada execução paga 77s pra reaprender
    o que já sabia.
    📌 Tentativa que não deixa registro condena todas as próximas a repeti-la.

    A memória tem validade: anúncio sai do ar e volta, e `RETENTAR_APOS` dias
    depois a gente pergunta de novo. Esquecer é diferente de nunca ter sabido.
    """
    if _tem_numeros(item):
        return False
    ultima = item.get("api_falhou_ts") or 0
    if ultima:
        agora = agora if agora is not None else time.time()
        if (agora - float(ultima)) < RETENTAR_APOS * 86400:
            return False
    return True


def _regra():
    """A função `_classificar` do `validar_fila` — ou None se não achar.

    ⚠️ DOIS CAMINHOS DE IMPORT, porque o projeto vive nos dois: na VPS os
    módulos rodam como `agents.<nome>` e no repositório como `<nome>`. Eu
    escrevi este mesmo padrão no `limpar_esteira` e no `diag_contas` e depois
    usei só um caminho aqui — resultado medido em 29/08: 41 produtos gravados
    com vendas e comissão corretas e classe VAZIA, sem uma linha de erro.

    ⚠️ E DEVOLVE None EM VEZ DE CHUTAR. A versão anterior era
    `except Exception: return ""`, e "" é indistinguível de "produto sem
    classe" — o guarda falhou calado e escreveu 41 registros errados que
    pareciam certos. Quem chama TEM que tratar o None, não assumir.
    📌 Regra que não carregou não é regra permissiva: é ausência de regra, e
    ausência de regra tem que parar o trabalho, não deixá-lo passar."""
    for mod in ("validar_fila", "agents.validar_fila"):
        try:
            import importlib
            return getattr(importlib.import_module(mod), "_classificar")
        except Exception:
            continue
    return None


def _classe_de(dados: dict, regra) -> str:
    """A classe deste produto pelos números dele. `regra` vem do `_regra()`."""
    try:
        return regra({"ok": True, "campeao": dados}) or ""
    except Exception:
        return ""


def _consultar(link: str) -> dict:
    """Os dados oficiais do produto. {} quando não dá — e {} não estraga nada.

    Reusa a função do hunter (que segue o link curto, extrai o itemId e chama
    a productOfferV2) em vez de refazer o caminho aqui."""
    try:
        from telegram_repurpose_hunter import _dados_oficiais_do_link
        d = _dados_oficiais_do_link(link)
        return d if d.get("ok") else {}
    except Exception as e:
        _log(f"⚠️  não consegui consultar ({type(e).__name__}: {str(e)[:70]})")
        return {}


def _gravar(fila: list):
    """Escrita atômica: o hunter insere no topo desta MESMA fila a qualquer
    momento, e um arquivo truncado no meio da gravação some com o acervo."""
    FILA.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False,
                                      dir=str(FILA.parent))
    try:
        json.dump(fila, tmp, ensure_ascii=False, indent=2)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, FILA)
    except Exception:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def _distribuicao(fila: list) -> Counter:
    return Counter(str(i.get("classe") or "sem classe")
                   for i in fila if isinstance(i, dict))


def rodar(limite: int, aplicar: bool, pausa: float,
          so_disponiveis: bool) -> int:
    fila = _carregar(FILA, [])
    if not isinstance(fila, list) or not fila:
        _log(f"❌ {FILA} vazia ou ilegível")
        return 1

    regra = _regra()
    if regra is None:
        # ⚠️ PARA, não continua sem classificar. Foi assim que 41 produtos
        # foram gravados com número certo e classe vazia: seguir sem a regra
        # produz um arquivo que parece enriquecido e não é.
        _log("❌ não consegui carregar `_classificar` do validar_fila "
             "(tentei 'validar_fila' e 'agents.validar_fila').")
        _log("   Sem a regra eu classificaria tudo como vazio — que é o bug "
             "que este aviso existe pra impedir. Nada foi tocado.")
        return 2

    # ── PASSO 1, DE GRAÇA: quem JÁ tem os números e está sem classe.
    # ⚠️ CLASSIFICAR NÃO CUSTA CHAMADA — a conta é local, sobre dados que já
    # estão no arquivo. Misturar isto com a consulta foi o que fez os 41
    # produtos ficarem sem classe e, pior, INELEGÍVEIS pra uma segunda rodada:
    # `_precisa` olha se os campos existem, e eles existiam.
    # 📌 Buscar dado e decidir sobre ele são passos diferentes; juntar os dois
    # faz a falha de um esconder o resultado do outro.
    reclass = 0
    for item in fila:
        if not isinstance(item, dict) or str(item.get("classe") or "").strip():
            continue
        if not _tem_numeros(item):
            continue        # ⚠️ `_tem_numeros`, NÃO `not _precisa`: o segundo
                            # também é False pra quem falhou há pouco, e isso
                            # classificava como `fraco` quem nunca foi medido
        c = _classe_de(item, regra)
        if c:
            item["classe"] = c
            reclass += 1
    if reclass:
        _log(f"🔁 {reclass} produto(s) já tinham os números e ganharam classe "
             f"sem gastar chamada")

    alvos = [i for i in fila if isinstance(i, dict) and i.get("link")
             and _precisa(i)]
    if so_disponiveis:
        # ⚠️ O QUE URGE É O QUE O GRUPO AINDA VAI POSTAR. Enriquecer 200
        # produtos já postados não muda uma decisão sequer — e cada um custa
        # uma chamada.
        est = _carregar(POSTADOS, {})
        ja = set(est.get("links", []) if isinstance(est, dict) else [])
        alvos = [i for i in alvos if i["link"] not in ja and i.get("imagem")]

    _log(f"fila={len(fila)}  sem número={len(alvos)}  "
         f"vou consultar={min(len(alvos), limite)}")
    _log(f"antes:  {dict(_distribuicao(fila))}")
    if not alvos:
        if reclass and aplicar:
            _gravar(fila)
            _log(f"depois: {dict(_distribuicao(fila))}")
            _log(f"💾 gravado: {reclass} reclassificado(s), 0 chamada(s)")
        elif reclass:
            _log(f"depois: {dict(_distribuicao(fila))}")
            _log(f"🧪 SIMULAÇÃO — {reclass} reclassificado(s). Use --aplicar.")
        else:
            _log("✅ nada a enriquecer")
        return 0

    feitos, falhos = 0, 0
    for i, item in enumerate(alvos[:limite]):
        d = _consultar(item["link"])
        nome = str(item.get("campeao") or item.get("produto") or "")[:40]
        if not d:
            falhos += 1
            # ⚠️ MARCA A FALHA NO ITEM. Sem isto a próxima rodada refaz
            # exatamente esta chamada, e a seguinte também — ver `_precisa`.
            item["api_falhou_ts"] = int(time.time())
            _log(f"?  {nome:42} (sem resposta da API — só reconsulto em "
                 f"{RETENTAR_APOS}d)")
        else:
            for c in CAMPOS:
                item[c] = d.get(c) or 0
            item["item_id"] = str(d.get("item_id") or item.get("item_id") or "")
            item["shop_id"] = str(d.get("shop_id") or item.get("shop_id") or "")
            # ⚠️ CLASSE EXISTENTE NÃO É PISADA. Se o `curar_fila` já
            # classificou este produto, a palavra dele vale mais que a nossa:
            # ele viu a mineração inteira, nós vimos um anúncio.
            if not str(item.get("classe") or "").strip():
                item["classe"] = _classe_de(d, regra)
            if not item.get("imagem"):
                item["imagem"] = d.get("imagem") or ""
            item.pop("api_falhou_ts", None)   # deu certo: a marca não vale mais
            feitos += 1
            _log(f"✅ {nome:42} {item['classe'] or 'sem classe':10} "
                 f"{item['vendas']:>6} vendas · "
                 f"{item['comissao_rate'] * 100:.0f}% com.")
        # pausa pra não tomar rate limit da Shopee (exceto na última)
        if pausa > 0 and i < min(len(alvos), limite) - 1:
            time.sleep(pausa)

    _log(f"depois: {dict(_distribuicao(fila))}")
    if not aplicar:
        _log(f"🧪 SIMULAÇÃO — {feitos} enriquecido(s), "
             f"{reclass} reclassificado(s), {falhos} sem resposta. "
             f"Nada foi gravado. Use --aplicar.")
        return 0
    if feitos or reclass or falhos:
        _gravar(fila)
        _log(f"💾 gravado: {feitos} enriquecido(s), "
             f"{reclass} reclassificado(s), {falhos} sem resposta")
    else:
        _log(f"nada gravado ({falhos} sem resposta)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Preenche vendas/comissão/classe nos produtos da fila.")
    p.add_argument("--limite", type=int, default=25,
                   help="quantos produtos consultar nesta rodada (padrão 25)")
    p.add_argument("--aplicar", action="store_true",
                   help="grava de verdade (sem isto, só simula)")
    p.add_argument("--pausa", type=float, default=1.5,
                   help="segundos entre chamadas (padrão 1.5)")
    p.add_argument("--so-disponiveis", action="store_true",
                   dest="so_disponiveis",
                   help="só os que o grupo ainda não postou e têm foto")
    a = p.parse_args(argv)

    # Mesma trava do postar_grupo, pela mesma razão: dois processos reescrevendo
    # a fila ao mesmo tempo perdem o trabalho de um deles, sem erro nenhum.
    with travar("enriquecer_fila") as livre:
        if not livre:
            _log("outra instância já está rodando — saio sem fazer nada ✔")
            return 0
        return rodar(max(1, a.limite), a.aplicar, max(0.0, a.pausa),
                     a.so_disponiveis)


if __name__ == "__main__":
    sys.exit(main())
