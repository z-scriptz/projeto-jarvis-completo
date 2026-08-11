#!/usr/bin/env python3
# texto_queimado.py -- a foto do produto JÁ tem texto escrito nela? E ele briga
#                      com o texto que a gente escreve por cima?
#
# POR QUE EXISTE
# O defeito da escova alisadora (10/08): a foto do anúncio vinha com texto
# promocional queimado — "50% OFF", especificações, selos — e o render põe hook,
# legenda e CTA por cima. O vídeo fica ilegível e nenhuma métrica do projeto via
# isso, porque `asset_ranker` mede DIVERSIDADE e TAMANHO, não conteúdo.
# Era o último campo `nao_avaliado` da escada de material.
#
# ⚠️ NÃO É "TEM TEXTO → REPROVA", e isso foi o ChatGPT quem corrigiu:
#
#   "Uma foto de produto pode naturalmente ter nome da marca, especificação,
#    pequeno texto informativo. O problema é quando o asset está visualmente
#    carregado."
#
# Reprovar todo texto reprovaria quase toda foto de e-commerce — repetindo o
# erro do `faixa_preenchida`, que reprovava o caso bom.
#
# O QUE DECIDE É A BRIGA, NÃO A PRESENÇA
# ──────────────────────────────────────
# O template tem geometria conhecida (render.py): a caixa do vídeo vai de
# y=540 a y=1720, a LEGENDA anima na BASE dessa caixa e o DESTAQUE fica no
# TOPO dela. O miolo é onde o produto aparece.
# Então texto queimado no MEIO é quase inofensivo (é o produto, e ninguém
# escreve por cima dele); na BASE e no TOPO ele colide com o nosso.
# Por isso o modelo é perguntado ONDE o texto está, e o risco é calculado aqui
# contra a nossa geometria — não estimado por ele.
#
# ⚠️ SEM CHAVE, O CAMPO SAI `nao_avaliado` — NUNCA "aprovado". A regra já estava
# escrita no asset_ranker e vale aqui: fingir que avaliou é pior que não
# avaliar. O mesmo para quota estourada, timeout e JSON inválido.
#
# Uso:
#   python3 texto_queimado.py --imagem foto.jpg --produto "Escova Alisadora"
#   python3 texto_queimado.py --imagem foto.jpg --json
#   python3 texto_queimado.py --decidir '{"tem_texto":true,...}'   # só a decisão

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CACHE = BASE_DIR / "shared" / "cache_texto_queimado.json"

# ── limiares, e o motivo de cada um ─────────────────────────────────────────
# Densidade é a fração da imagem coberta por texto, estimada pelo modelo.
# 0.10 = um selo de canto ou nome de marca; 0.25 = a foto virou banner.
DENS_RUIDO = 0.10       # abaixo disto é marca/etiqueta: não incomoda ninguém
DENS_CARREGADA = 0.25   # acima disto a foto já é peça publicitária

# As faixas onde NÓS escrevemos, derivadas do template (render.py):
#   destaque  no topo da caixa de vídeo
#   legenda   na base da caixa de vídeo
FAIXAS_NOSSAS = {"topo", "base"}

TIPOS_NATURAIS = {"marca", "especificacao", "nenhum"}

PROMPT = """Você está avaliando UMA FOTO DE PRODUTO de e-commerce que vai virar \
vídeo curto. O produto é: "{produto}".

Preciso saber se a foto já tem TEXTO ESCRITO NELA (queimado na imagem), porque \
nós vamos escrever legenda e chamada por cima e os dois textos brigam.

Considere texto: qualquer palavra, número, selo, etiqueta de preço, "50% OFF", \
lista de especificações, comparativo "antes/depois" com rótulo, marca d'água.
NÃO considere texto: a marca gravada no próprio produto (relevo, impressão de \
fábrica na embalagem que faz parte do objeto fotografado).

Divida a imagem em três faixas horizontais iguais: "topo", "meio", "base".

Responda EXATAMENTE neste JSON, sem markdown e sem texto fora dele:
{{
  "tem_texto": true ou false,
  "tipo": "nenhum" | "marca" | "especificacao" | "promocional" | "misto",
  "densidade": 0.0 a 1.0,
  "faixas": ["topo"] e/ou ["meio"] e/ou ["base"],
  "descricao": "o que está escrito, em poucas palavras"
}}

Onde:
- "densidade" é a FRAÇÃO da área da imagem coberta por texto (0.02 = um selinho \
de canto; 0.30 = metade da foto é banner).
- "tipo" = "promocional" para preço, desconto, "frete grátis", "oferta", \
chamada de venda. "especificacao" para medidas, voltagem, capacidade. \
"marca" para só o nome/logo da marca.
- "faixas" lista TODAS as faixas onde há texto."""


def _log(m):
    print(f"[texto] {m}", flush=True)


def _cache_ler() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cache_gravar(d: dict) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    except Exception:
        pass          # cache é otimização; falhar aqui não pode travar nada


def _hash(caminho: Path) -> str:
    """Chave do cache = CONTEÚDO do arquivo, não o nome.

    O piloto deriva enquadramentos e grava com nomes novos a cada rodada; por
    nome, o cache nunca acertaria e a cota do Gemini iria embora à toa.
    """
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()[:32]


def decidir(bruto: dict) -> dict:
    """Do laudo do modelo pro veredito, com a geometria do NOSSO template.

    Fica separada da chamada de rede de propósito: é a única parte que dá pra
    testar sem chave, e é onde mora a política. O modelo diz o que VÊ; quem
    decide o que isso significa pro vídeo é este projeto.
    """
    tem = bool(bruto.get("tem_texto"))
    tipo = str(bruto.get("tipo") or "nenhum").strip().lower()
    try:
        dens = max(0.0, min(1.0, float(bruto.get("densidade") or 0.0)))
    except (TypeError, ValueError):
        dens = 0.0
    faixas = {str(f).strip().lower() for f in (bruto.get("faixas") or [])}
    colide = bool(faixas & FAIXAS_NOSSAS)

    if not tem or tipo == "nenhum":
        return {"veredito": "aprovado", "densidade": dens, "tipo": tipo,
                "faixas": sorted(faixas), "conflito": "nenhum",
                "motivo": "sem texto queimado"}

    # risco = o quanto o texto DELES ocupa onde o NOSSO vai
    if colide and dens >= DENS_CARREGADA:
        risco = "alto"
    elif colide and dens >= DENS_RUIDO:
        risco = "medio"
    elif dens >= DENS_CARREGADA:
        risco = "medio"          # não colide, mas a foto já é um banner
    else:
        risco = "baixo"

    promocional = tipo in ("promocional", "misto")

    if promocional and risco == "alto":
        v, motivo = "reprovado", (
            f"texto promocional cobrindo ~{dens:.0%} da foto em "
            f"{'/'.join(sorted(faixas & FAIXAS_NOSSAS))} — exatamente onde "
            "entram legenda e destaque")
    elif promocional and risco == "medio":
        v, motivo = "ressalva", (
            f"texto promocional ({dens:.0%}) em {'/'.join(sorted(faixas))} — "
            "dá pra usar, de preferência com --encaixe cover ou outro corte")
    elif dens >= DENS_CARREGADA:
        v, motivo = "ressalva", (
            f"foto carregada de texto ({dens:.0%}), tipo '{tipo}' — "
            "compete com a leitura mesmo sem ser promocional")
    elif tipo in TIPOS_NATURAIS:
        v, motivo = "aprovado", (
            f"só {tipo} ({dens:.0%}) — normal em foto de produto")
    else:
        v, motivo = "aprovado", f"texto discreto ({dens:.0%}), tipo '{tipo}'"

    return {"veredito": v, "densidade": round(dens, 3), "tipo": tipo,
            "faixas": sorted(faixas), "conflito": risco, "motivo": motivo,
            "descricao": str(bruto.get("descricao") or "")[:160]}


def _nao_avaliado(porque: str) -> dict:
    """O único jeito honesto de dizer 'não sei'.

    NUNCA devolver 'aprovado' aqui. Quem chama trata `nao_avaliado` como
    ausência de informação — não como sinal verde.
    """
    return {"veredito": "nao_avaliado", "motivo": porque,
            "densidade": None, "tipo": None, "faixas": [],
            "conflito": None}


def avaliar(caminho, produto: str = "", usar_cache: bool = True) -> dict:
    caminho = Path(caminho)
    if not caminho.exists():
        return _nao_avaliado(f"arquivo não existe: {caminho}")

    if not os.getenv("GEMINI_API_KEY"):
        return _nao_avaliado("GEMINI_API_KEY não definida")

    chave = None
    if usar_cache:
        try:
            chave = f"{_hash(caminho)}"
            guardado = _cache_ler().get(chave)
            if guardado:
                guardado["do_cache"] = True
                return guardado
        except Exception:
            chave = None

    try:
        import base64
        from google import genai                          # noqa: F401
    except Exception as e:
        return _nao_avaliado(f"google-genai indisponível: {str(e)[:60]}")

    try:
        from shared.config import GEMINI_VISION_MODEL
    except Exception:
        GEMINI_VISION_MODEL = "gemini-2.5-flash-lite"

    mime = "image/png" if caminho.suffix.lower() == ".png" else "image/jpeg"
    try:
        img_b64 = base64.b64encode(caminho.read_bytes()).decode()
    except Exception as e:
        return _nao_avaliado(f"não consegui ler a imagem: {str(e)[:60]}")

    payload = [{"parts": [
        {"inline_data": {"mime_type": mime, "data": img_b64}},
        {"text": PROMPT.format(produto=produto or "produto de e-commerce")},
    ]}]

    try:
        from google import genai as _g
        cliente = _g.Client(api_key=os.getenv("GEMINI_API_KEY"))
        resp = cliente.models.generate_content(
            model=GEMINI_VISION_MODEL, contents=payload)
        texto = (resp.text or "").strip()
        if texto.startswith("```"):
            texto = "\n".join(texto.split("\n")[1:-1])
        bruto = json.loads(texto)
    except Exception as e:
        msg = str(e).lower()
        if "quota" in msg or "resource_exhausted" in msg:
            # ⚠️ o padrão do visual_audit_agent aqui é "na dúvida MANTÉM o
            # clipe". Lá faz sentido: descartar vídeo pronto por falha de
            # infra é caro. Aqui a resposta certa é diferente — dizer
            # "aprovado" por falta de cota seria inventar avaliação, e o
            # asset_ranker foi escrito justamente pra nunca fazer isso.
            return _nao_avaliado("cota do Gemini esgotada")
        return _nao_avaliado(f"falha na avaliação: {str(e)[:80]}")

    fora = decidir(bruto)
    if usar_cache and chave:
        c = _cache_ler()
        c[chave] = fora
        _cache_gravar(c)
    return fora


def avaliar_varias(imagens: list, produto: str = "") -> dict:
    """Roda em várias fotos e resume — é assim que o asset_ranker consulta."""
    itens = []
    for img in imagens:
        r = avaliar(img, produto)
        r["arquivo"] = Path(img).name
        itens.append(r)

    contagem = {}
    for i in itens:
        contagem[i["veredito"]] = contagem.get(i["veredito"], 0) + 1

    if contagem.get("aprovado") or contagem.get("ressalva"):
        # havendo foto usável, o conjunto é usável: o EDL escolhe o corte
        pior = ("reprovado" if contagem.get("reprovado") else
                "ressalva" if contagem.get("ressalva") else "aprovado")
        bloqueia = not (contagem.get("aprovado") or contagem.get("ressalva"))
    else:
        pior = "reprovado" if contagem.get("reprovado") else "nao_avaliado"
        bloqueia = bool(contagem.get("reprovado"))

    return {"itens": itens, "resumo": contagem, "pior": pior,
            "bloqueia": bloqueia,
            "usaveis": contagem.get("aprovado", 0) + contagem.get("ressalva", 0)}


def main():
    p = argparse.ArgumentParser(
        description="A foto já tem texto queimado que briga com o nosso?")
    p.add_argument("--imagem", nargs="*", default=[])
    p.add_argument("--pasta")
    p.add_argument("--produto", default="")
    p.add_argument("--json", action="store_true")
    p.add_argument("--sem-cache", action="store_true")
    p.add_argument("--decidir", help="testa SÓ a decisão com um laudo em JSON "
                                     "(não chama a API)")
    args = p.parse_args()

    if args.decidir:
        print(json.dumps(decidir(json.loads(args.decidir)),
                         ensure_ascii=False, indent=2))
        return 0

    imagens = [Path(x) for x in args.imagem]
    if args.pasta:
        ext = (".jpg", ".jpeg", ".png", ".webp")
        imagens += sorted(f for f in Path(args.pasta).iterdir()
                          if f.suffix.lower() in ext)
    if not imagens:
        p.error("use --imagem a.jpg [b.jpg] ou --pasta PASTA")

    r = avaliar_varias(imagens, args.produto)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 1 if r["bloqueia"] else 0

    icone = {"aprovado": "✅", "ressalva": "👀", "reprovado": "❌",
             "nao_avaliado": "❔"}
    print()
    for i in r["itens"]:
        print(f"  {icone.get(i['veredito'], '?')} {i['arquivo'][:30]:32} "
              f"{i['veredito']:13} {i['motivo'][:80]}")
    print(f"\n  {r['usaveis']}/{len(r['itens'])} usáveis · pior: {r['pior']}")
    if r["resumo"].get("nao_avaliado"):
        print("  ❔ nao_avaliado NÃO é aprovação — é ausência de informação "
              "(sem chave, sem cota ou falha)")
    return 1 if r["bloqueia"] else 0


if __name__ == "__main__":
    sys.exit(main())
