#!/usr/bin/env python3
# memoria_producao.py -- a cadeia nova (storyboard→edl→render→conferir) grava e
#                        consulta a memória que já existia.
#
# POR QUE EXISTE (12/08)
# `memory_agent.py` tem 1097 linhas, JSONL + vector store, `registrar_memoria`,
# `registrar_avaliacao_video` e `buscar_contexto_para_tarefa`. Ele é importado
# por seis arquivos — TODOS da esteira antiga. A cadeia que construímos nesta
# semana nasceu órfã dele: `grep registrar_avaliacao_video` fora do próprio
# arquivo dá ZERO.
#
# Então a fatia 2 de ARQUITETURA_CRITICO.md não é "construir memória". É plugar.
# E plugar por FORA, num adaptador: o `memory_agent` funciona e é usado em
# produção; refatorá-lo pra caber num formato novo seria arriscar o que roda
# pra servir o que ainda não roda.
#
# O QUE ESTE ARQUIVO ACRESCENTA À MEMÓRIA QUE JÁ EXISTIA
# ─────────────────────────────────────────────────────
# `registrar_avaliacao_video` guarda texto livre (pontos bons/ruins). Isso
# responde "o que aconteceu neste vídeo?" e NÃO responde a pergunta do passo ⑨:
#
#     "o que deu errado nas outras vezes em que produzi NESTAS CONDIÇÕES?"
#
# Por isso a `assinatura_da_entrada`: 1 foto? quantas distintas? menor lado?
# hook de quantos caracteres? texto queimado? Sem ela, "buscar experiências
# relacionadas" só acha por nome de produto — e nome de produto não se repete.
# É a diferença entre memória que ARQUIVA e memória que ANTECIPA.
#
# E `verificado`: experiência só vira lição quando a re-renderização confirmou
# que a correção funcionou. Correção registrada sem reavaliação é palpite com
# data.
#
# SÓ ESCREVE MEMÓRIA. Não renderiza, não posta, não apaga vídeo.
#
# Uso:
#   python3 memoria_producao.py --relatorio shared/renders/x.relatorio.json
#   python3 memoria_producao.py --consultar --nicho casa --fotos 1 --hook 62

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
COLECAO = "creative_lessons"      # a mesma que o memory_agent já usa p/ vídeo


def _log(m):
    print(f"[memoria] {m}", flush=True)


def _MA():
    """O memory_agent, de onde ele estiver. None se não der."""
    for caminho in ("agents.memory_agent", "memory_agent"):
        try:
            sys.path.insert(0, str(BASE_DIR))
            return __import__(caminho, fromlist=["*"])
        except Exception:
            continue
    return None


def assinatura(relatorio: dict, conferencia: dict = None,
               ranker: dict = None) -> dict:
    """As CONDIÇÕES em que este vídeo foi produzido — a chave de busca do ⑨.

    Só entra aqui o que descreve a ENTRADA, nunca o resultado. Misturar as
    duas coisas faria a busca encontrar "vídeos que deram errado" em vez de
    "vídeos produzidos em condições parecidas", que é o que permite prever.

    Números viram FAIXAS de propósito: `hook_chars: 62` casa com nada;
    `hook_faixa: "50-70"` casa com a próxima produção parecida.
    """
    lay = relatorio.get("layout") or {}
    knobs = relatorio.get("knobs") or {}
    n_fotos = int(relatorio.get("assets_disponiveis") or 0) or None
    hook = int(lay.get("hook_chars") or relatorio.get("hook_chars") or 0)

    def faixa(n, cortes, rotulos):
        for lim, r in zip(cortes, rotulos):
            if n <= lim:
                return r
        return rotulos[-1]

    a = {
        "nicho": (relatorio.get("nicho")
                  or (relatorio.get("topo") or {}).get("nicho") or "geral"),
        "modo_audio": relatorio.get("modo_audio") or "",
        "n_fotos": n_fotos,
        "cortes": relatorio.get("cortes"),
        "duracao_faixa": faixa(float(relatorio.get("duracao_arquivo") or 0),
                               [12, 18, 25], ["<12s", "12-18s", "18-25s", ">25s"]),
        "narrado": bool(relatorio.get("narracoes")),
        "com_trilha": bool(relatorio.get("trilha")),
        "narrar_hook": bool(knobs.get("narrar_hook")),
    }
    if hook:
        a["hook_faixa"] = faixa(hook, [50, 70, 84], ["<50", "50-70", "70-84", ">84"])
    if ranker:
        a["nivel_assets"] = ranker.get("nivel")
        a["distintas"] = ranker.get("distintas")
        tq = ranker.get("texto_queimado") or {}
        if isinstance(tq, dict):
            a["texto_queimado"] = tq.get("pior")
    return {k: v for k, v in a.items() if v not in (None, "")}


def _chave(a: dict) -> str:
    """Texto de busca a partir da assinatura — é o que o vector store indexa."""
    return " ".join(f"{k}={v}" for k, v in sorted(a.items()))


def registrar(relatorio: dict, conferencia: dict, ranker: dict = None,
              correcao: dict = None) -> dict:
    """Grava UMA experiência de produção. Chamado pelo piloto no fim do ciclo.

    `correcao` só existe quando o laço já rodou: {"o_que", "resultado",
    "verificado"}. Sem ele, o campo sai `verificado: false` — e é assim que
    tem que ser, porque nada foi reavaliado ainda.
    """
    ma = _MA()
    if ma is None:
        return {"sucesso": False, "mensagem": "memory_agent indisponível"}

    a = assinatura(relatorio, conferencia, ranker)
    estado = conferencia.get("estado") or "?"
    achados = conferencia.get("achados") or []

    # o texto é o que a busca semântica lê; a metadata é o que o filtro usa
    linhas = [f"Produção de '{relatorio.get('produto','?')}' ({a.get('nicho')}).",
              f"Condições: {_chave(a)}.",
              f"Estado: {estado}. {conferencia.get('quem_age','')}"]
    for x in achados:
        laudo = (conferencia.get("checagens") or {}).get(x["checagem"], {})
        lever = laudo.get("lever") or "NENHUM (matéria-prima)"
        linhas.append(f"Achado [{x['gravidade']}] {x['checagem']}: "
                      f"{x['descricao']} · causa: {laudo.get('causa','?')} · "
                      f"lever: {lever}")
    if correcao:
        linhas.append(f"Correção aplicada: {correcao.get('o_que','?')} → "
                      f"{correcao.get('resultado','?')}")

    meta = {"produto": relatorio.get("produto", ""),
            "video": relatorio.get("arquivo", ""),
            "estado": estado,
            "verificado": bool(correcao and correcao.get("verificado")),
            # a assinatura entra ACHATADA: o filtro do vector store é por
            # chave=valor simples, e dict aninhado não é filtrável
            **{f"ass_{k}": str(v) for k, v in a.items()},
            "achados": ";".join(x["checagem"] for x in achados),
            "sem_lever": ";".join(conferencia.get("sem_lever") or [])}

    tags = ["producao", estado.lower()]
    tags += [x["checagem"] for x in achados]

    return ma.registrar_memoria(
        tipo="avaliacao", texto="\n".join(linhas), metadata=meta,
        colecao=COLECAO, tags=tags)


def consultar(a: dict, limite: int = 8) -> dict:
    """O passo ZERO: o que costuma dar errado NESTAS condições?

    Devolve os achados mais frequentes em produções de assinatura parecida,
    com a contagem. Contagem importa: um achado que apareceu 1 vez é ruído; o
    que apareceu 7 vezes em 8 produções parecidas é previsão.
    """
    ma = _MA()
    if ma is None:
        return {"ok": False, "motivo": "memory_agent indisponível", "achados": {}}

    r = ma.buscar_memorias(_chave(a), colecao=COLECAO, limite=limite)
    itens = r.get("resultados") or r.get("itens") or []

    from collections import Counter
    achados, estados, total = Counter(), Counter(), 0
    for it in itens:
        md = it.get("metadata") or it.get("meta") or {}
        # só conta experiência do MESMO nicho: "1 foto" pesa diferente em
        # beleza (close de textura) e em tech (o produto tem que aparecer)
        if a.get("nicho") and md.get("ass_nicho") not in (None, "", a["nicho"]):
            continue
        total += 1
        estados[md.get("estado", "?")] += 1
        for c in (md.get("achados") or "").split(";"):
            if c:
                achados[c] += 1

    return {"ok": True, "consultadas": total,
            "achados": dict(achados.most_common()),
            "estados": dict(estados),
            "aviso": _aviso(achados, total)}


def _aviso(achados, total: int) -> str:
    """A frase que o piloto imprime ANTES de gastar roteiro, voz e render."""
    if not total:
        return ""
    fortes = [(c, n) for c, n in achados.items() if n >= max(2, total * 0.5)]
    if not fortes:
        return f"{total} produção(ões) parecida(s), sem padrão de defeito claro"
    partes = ", ".join(f"{c} ({n}/{total})" for c, n in fortes)
    # "PARECIDAS", não "nestas condições": a busca é semântica e casa por
    # aproximação — testado, uma consulta por "1 foto" trouxe também uma
    # produção de 3. O número é honesto (4 de 5 tiveram o defeito); prometer
    # que as 5 eram idênticas não seria.
    return f"em {total} produção(ões) parecida(s), isto repetiu: {partes}"


def main():
    p = argparse.ArgumentParser(
        description="Grava e consulta a memória da cadeia nova. Só memória.")
    p.add_argument("--relatorio", help="shared/renders/<x>.relatorio.json")
    p.add_argument("--consultar", action="store_true")
    p.add_argument("--nicho", default="")
    p.add_argument("--fotos", type=int)
    p.add_argument("--hook", type=int)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    if args.relatorio:
        rel = json.loads(Path(args.relatorio).read_text(encoding="utf-8"))
        conf_arq = Path(args.relatorio.replace(".relatorio.json",
                                               ".conferencia.json"))
        conf = (json.loads(conf_arq.read_text(encoding="utf-8"))
                if conf_arq.exists() else {})
        if not conf:
            _log("⚠️  sem .conferencia.json ao lado — gravando só o render")
        r = registrar(rel, conf)
        print(json.dumps(r, ensure_ascii=False, indent=2) if args.json else
              f"[memoria] {'✅' if r.get('sucesso') else '❌'} {r}")
        return 0 if r.get("sucesso") else 1

    if args.consultar:
        a = {k: v for k, v in {"nicho": args.nicho or None,
                               "n_fotos": args.fotos}.items() if v}
        if args.hook:
            a["hook_faixa"] = ("<50" if args.hook <= 50 else
                               "50-70" if args.hook <= 70 else
                               "70-84" if args.hook <= 84 else ">84")
        r = consultar(a)
        print(json.dumps(r, ensure_ascii=False, indent=2) if args.json else
              f"[memoria] {r.get('aviso') or 'nada parecido na memória'}")
        return 0

    p.error("use --relatorio ARQ ou --consultar")


if __name__ == "__main__":
    sys.exit(main())
