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


def _carregar_env():
    """Lê o .env pro processo, se ninguém leu antes.

    ⚠️ POR QUE ISTO EXISTE (12/08): este módulo lia `GEMINI_API_KEY` do
    ambiente e nunca carregava o `.env`. Dentro do `piloto.py` funcionava,
    porque algum import anterior já tinha carregado — rodado sozinho, ele
    degradava para `nao_avaliado: GEMINI_API_KEY não definida`.

    E `nao_avaliado` é uma resposta LEGÍTIMA deste arquivo, então a falha não
    parecia falha: a medição do recorte saiu com nao_avaliado nos dois lados e
    eu quase li como "o Vision não viu diferença". Degradação silenciosa num
    módulo cujo modo de erro é indistinguível do modo normal.

    Mesmo formato do `amazon_playwright._carregar_env`: não sobrescreve o que
    já está no ambiente (systemd manda), e falha calado se não houver .env.
    """
    for cand in (BASE_DIR / ".env", Path(".env")):
        if not cand.exists():
            continue
        try:
            for linha in cand.read_text(encoding="utf-8").splitlines():
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                if linha.lower().startswith("export "):
                    linha = linha[7:]
                chave, _, valor = linha.partition("=")
                chave = chave.strip()
                valor = valor.strip().strip('"').strip("'")
                if chave and chave not in os.environ:
                    os.environ[chave] = valor
        except Exception:
            pass
        break


_carregar_env()


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


def _verdadeiro(v) -> bool:
    """bool tolerante: o modelo às vezes devolve "true"/"sim" como texto."""
    if isinstance(v, str):
        return v.strip().lower() in ("true", "sim", "yes", "1")
    return bool(v)


def _faixas(v) -> set:
    """As faixas como conjunto, aceitando lista OU string.

    ⚠️ O contrato pede lista, mas modelo devolve `"faixas": "base"` sem avisar.
    Iterar uma string dá as LETRAS: 'base' virava {'b','a','s','e'}, que não
    colide com {'topo','base'} — e uma foto com promoção na base saía como
    `ressalva` em vez de `reprovado`. Falha silenciosa, e para o lado errado.
    """
    if v is None:
        return set()
    if isinstance(v, str):
        v = [p for p in v.replace(";", ",").replace("/", ",").split(",")]
    try:
        return {str(f).strip().lower() for f in v if str(f).strip()}
    except TypeError:
        return set()


def _densidade(v):
    """Fração 0-1, aceitando 0.32, "0.32", "32%" e 32. None se não der.

    None NÃO é zero: quem chama trata como ausência de informação. Aceitar
    porcentagem importa porque o prompt pede fração e o modelo responde no
    formato que quiser — e "32%" lido como 0.0 aprovaria um banner inteiro.
    """
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip().replace(",", ".")
        pct = v.endswith("%")
        try:
            n = float(v.rstrip("%").strip())
        except ValueError:
            return None
        if pct:
            n /= 100.0
    else:
        try:
            n = float(v)
        except (TypeError, ValueError):
            return None
    # 32 quando o contrato pede 0-1 é claramente porcentagem escrita crua
    if n > 1.0:
        n = n / 100.0 if n <= 100.0 else 1.0
    return max(0.0, min(1.0, n))


def decidir(bruto: dict) -> dict:
    """Do laudo do modelo pro veredito, com a geometria do NOSSO template.

    Fica separada da chamada de rede de propósito: é a única parte que dá pra
    testar sem chave, e é onde mora a política. O modelo diz o que VÊ; quem
    decide o que isso significa pro vídeo é este projeto.
    """
    tem = _verdadeiro(bruto.get("tem_texto"))
    tipo = str(bruto.get("tipo") or "nenhum").strip().lower()
    faixas = _faixas(bruto.get("faixas"))
    colide = bool(faixas & FAIXAS_NOSSAS)

    dens = _densidade(bruto.get("densidade"))
    if tem and dens is None:
        # ⚠️ NÃO assumir 0. Densidade ilegível com texto presente é ausência de
        # informação, e o padrão 0.0 significaria "foto limpa" — aprovaria
        # justamente o caso que este arquivo existe pra pegar. Toda falha de
        # parse tem que cair pro mesmo lado: `nao_avaliado`.
        r = _nao_avaliado(f"densidade ilegível: {bruto.get('densidade')!r}")
        r.update(tipo=tipo, faixas=sorted(faixas))
        return r
    dens = dens or 0.0

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
        _carregar_env()          # 2ª chance: o cwd pode ter mudado desde o import
    if not os.getenv("GEMINI_API_KEY"):
        return _nao_avaliado(
            "GEMINI_API_KEY não definida (nem no ambiente, nem no .env de "
            f"{BASE_DIR})")

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


def _triagem(n: int) -> int:
    """Quantos produtos da fila JÁ têm foto boa?

    POR QUE ISTO EXISTE (12/08). O dia inteiro foi gasto tentando CONSERTAR
    foto ruim: coletar em outra loja (Amazon 0/6), recortar o produto (piorou,
    15% → 25% de densidade). Quatro becos medidos.
    E ninguém tinha perguntado a coisa mais barata: **de 80 produtos na fila,
    quantos já vêm com foto limpa?** Se for um terço, a saída não é consertar
    material ruim — é PRODUZIR PRIMEIRO o que já está bom. Isso não custa
    ferramenta nova: o detector já existe, a fila já existe, e a ordem de
    produção é decisão, não engenharia.

    Usa o cache por hash, então rodar duas vezes não gasta cota duas vezes.
    """
    import tempfile
    try:
        import storyboard as SB
        itens = [x for x in json.loads(SB.FILA.read_text(encoding="utf-8"))
                 if isinstance(x, dict)]
    except Exception as e:
        print(f"[texto] não li a fila: {str(e)[:70]}")
        return 1

    try:
        import requests
    except Exception:
        print("[texto] requests indisponível")
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="triagem_"))
    from collections import Counter
    placar, linhas = Counter(), []
    vistos = 0
    for i, it in enumerate(itens):
        if vistos >= n:
            break
        urls = [u for u in ([it.get("imagem")] + (it.get("imagens") or []))
                if isinstance(u, str) and u.startswith("http")]
        if not urls:
            continue
        nome = (it.get("campeao") or it.get("produto") or "")[:46]
        alvo = tmp / f"{i}.jpg"
        try:
            r = requests.get(urls[0], timeout=40,
                             headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200 or len(r.content) < 2048:
                continue
            alvo.write_bytes(r.content)
        except Exception:
            continue
        vistos += 1
        d = avaliar(alvo, nome)
        v = d.get("veredito", "nao_avaliado")
        placar[v] += 1
        icone = {"aprovado": "✅", "ressalva": "👀",
                 "reprovado": "❌", "nao_avaliado": "❔"}.get(v, "?")
        dens = d.get("densidade")
        linhas.append(f"  [{i:3}] {icone} {v:13} "
                      f"{('%.0f%%' % (dens*100)) if dens is not None else '  — ':>5}  {nome}")

    print()
    for l in linhas:
        print(l)
    total = sum(placar.values()) or 1
    limpos = placar["aprovado"]
    print()
    print(f"[texto] de {total} produtos com foto: {limpos} aprovado · "
          f"{placar['ressalva']} ressalva · {placar['reprovado']} reprovado · "
          f"{placar['nao_avaliado']} não avaliado")
    print(f"[texto] FOTO JÁ BOA: {limpos}/{total} ({100*limpos/total:.0f}%)")
    if limpos + placar["ressalva"] >= total * 0.4:
        print("[texto] → dá pra PRODUZIR SÓ O QUE JÁ PRESTA e parar de tentar")
        print("        consertar material ruim. Custa zero: o detector já")
        print("        existe, falta só a fila respeitar a ordem.")
    else:
        print("[texto] → a maioria tem foto ruim; selecionar não basta e o")
        print("        gargalo é mesmo de origem.")
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


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
    p.add_argument("--triagem", type=int, metavar="N",
                   help="avalia a foto dos N primeiros produtos da FILA e diz "
                        "quantos já têm foto limpa — selecionar em vez de "
                        "consertar")
    args = p.parse_args()

    if args.triagem:
        return _triagem(args.triagem)

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
