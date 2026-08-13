#!/usr/bin/env python3
# recorte_produto.py -- separar o PRODUTO do que veio junto na foto.
#
# POR QUE EXISTE (12/08)
# O Kit 10 Calcinhas foi barrado: 43% de texto promocional queimado, nível D,
# não produzir. As três fontes externas estão fechadas (Shopee anti-bot, Amazon
# 0/6 de identidade, Mercado Livre 403), então o que sobra é fazer UMA foto
# funcionar. E a tarja "mais vendido" e o selo "10 UNIDADES" não são o produto:
# são coisas que o vendedor colou por cima.
#
# ⚠️ ESTE ARQUIVO NASCE COMO MEDIÇÃO, NÃO COMO FERRAMENTA DE PRODUÇÃO.
# Eu afirmei, na conversa, que "recortar o produto deixa o texto promocional
# para trás". Isso é HIPÓTESE, e o ChatGPT cobrou o teste — com razão. Os modos
# de falha são reais e conhecidos:
#   · a tarja está POR CIMA do produto e sai junto com ele
#   · o segmentador come parte da peça (tecido claro vira fundo)
#   · sombra vira produto, ou produto vira sombra
#   · borda artificial que denuncia recorte
#   · produto transparente/reflexivo destruído
#
# Por isso o comando principal é `--medir`: ele recorta, roda os MESMOS
# detectores que barraram a foto (texto_queimado, asset_ranker) no antes e no
# depois, e mostra os dois lado a lado. O número decide, não a expectativa.
#
# ⚠️ E O RISCO QUE NÃO PODE PASSAR: recorte que destrói o produto é pior que
# foto com tarja. Uma foto feia mostra o produto; um recorte quebrado mostra
# outra coisa. Por isso `_sobrou` mede quanto da imagem sobreviveu e recusa
# extremos — abaixo de um piso, o segmentador comeu o produto; acima de um
# teto, ele não recortou nada e só devolveu a foto com fundo novo.
#
# Instalar (VPS):  .venv/bin/pip install rembg onnxruntime
#   (baixa ~170MB de modelo na primeira execução; é local, sem custo de API)
#
# Uso:
#   python3 recorte_produto.py --medir foto.jpg --produto "Kit 10 Calcinhas"
#   python3 recorte_produto.py --recortar foto.jpg --saida limpo.png

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Quanto da imagem pode sobrar depois do recorte, em fração de pixels opacos.
# Fora desta faixa o resultado NÃO é usado, e o motivo é diferente em cada
# ponta — por isso dois números, não um.
SOBROU_MIN = 0.06   # abaixo: comeu o produto (ou achou que a foto é só fundo)
SOBROU_MAX = 0.92   # acima: não recortou nada, só trocou o fundo

FUNDO_PADRAO = (255, 255, 255)


def _log(m):
    print(f"[recorte] {m}", flush=True)


def _segmentador():
    """O recortador disponível, ou None. Hoje só rembg — e de propósito:
    duas implementações dariam dois resultados pro mesmo produto, e aí
    nenhuma medição comparativa valeria."""
    try:
        from rembg import remove          # noqa: F401
        return "rembg"
    except Exception:
        return None


def recortar(origem: Path, destino: Path, fundo=FUNDO_PADRAO) -> dict:
    """Separa o produto e recompõe sobre fundo liso.

    Devolve sempre `ok` + `motivo`: recorte que falha em silêncio e devolve a
    foto original é o pior resultado possível, porque o pipeline seguiria
    achando que consertou.
    """
    if _segmentador() is None:
        return {"ok": False, "motivo": "rembg não instalado "
                "(.venv/bin/pip install rembg onnxruntime)"}

    from PIL import Image
    from rembg import remove
    try:
        with Image.open(origem) as im:
            src = im.convert("RGBA")
        sem_fundo = remove(src)
    except Exception as e:
        return {"ok": False, "motivo": f"segmentação falhou: {str(e)[:90]}"}

    alfa = sem_fundo.getchannel("A")
    total = alfa.width * alfa.height
    # histograma do alfa: quanto sobrou de verdade (opaco), não "quanto tem"
    opacos = sum(n for v, n in enumerate(alfa.histogram()) if v > 128)
    sobrou = opacos / max(1, total)

    if sobrou < SOBROU_MIN:
        return {"ok": False, "sobrou": round(sobrou, 3),
                "motivo": f"sobrou {sobrou:.1%} da imagem — o segmentador comeu "
                          "o produto (ou achou que a foto inteira é fundo)"}
    if sobrou > SOBROU_MAX:
        return {"ok": False, "sobrou": round(sobrou, 3),
                "motivo": f"sobrou {sobrou:.1%} — não recortou nada de fato, "
                          "só trocaria o fundo. A tarja continuaria na foto"}

    # recompõe sobre fundo liso, no MESMO tamanho: mudar o enquadramento aqui
    # misturaria dois efeitos e a medição não saberia qual mexeu no resultado
    plano = Image.new("RGB", sem_fundo.size, fundo)
    plano.paste(sem_fundo, (0, 0), sem_fundo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    plano.save(destino, quality=95)
    return {"ok": True, "sobrou": round(sobrou, 3), "arquivo": str(destino),
            "motivo": f"produto isolado, {sobrou:.1%} da imagem preservada"}


def medir(origem: Path, produto: str, pasta: Path) -> dict:
    """ANTES e DEPOIS pelos MESMOS detectores que barraram a foto.

    Usar os detectores que já existem, e não uma métrica nova, é o ponto: se
    eu inventasse um número aqui, ele mediria a minha expectativa. O
    `texto_queimado` é quem reprovou o Kit Calcinhas — é ele que tem que dizer
    se melhorou.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    limpo = pasta / f"{Path(origem).stem}_recortado.jpg"

    try:
        import texto_queimado as TQ
    except Exception as e:
        return {"ok": False, "motivo": f"texto_queimado indisponível: {e}"}

    antes = TQ.avaliar(origem, produto)
    r = recortar(Path(origem), limpo)
    if not r.get("ok"):
        return {"ok": False, "antes": antes, "recorte": r}
    depois = TQ.avaliar(limpo, produto)

    # lado a lado pro olho humano — o número não substitui olhar o recorte
    try:
        from PIL import Image
        a, b = Image.open(origem).convert("RGB"), Image.open(limpo).convert("RGB")
        h = 700
        a = a.resize((int(a.width * h / a.height), h))
        b = b.resize((int(b.width * h / b.height), h))
        par = Image.new("RGB", (a.width + b.width + 20, h), (240, 240, 240))
        par.paste(a, (0, 0))
        par.paste(b, (a.width + 20, 0))
        comparacao = pasta / f"{Path(origem).stem}_antes_depois.jpg"
        par.save(comparacao, quality=92)
    except Exception:
        comparacao = None

    return {"ok": True, "antes": antes, "depois": depois, "recorte": r,
            "comparacao": str(comparacao) if comparacao else None}


def _num(v):
    return "—" if v is None else (f"{v:.0%}" if isinstance(v, float) else str(v))


def main():
    p = argparse.ArgumentParser(
        description="Separa o produto do que o vendedor colou por cima.")
    p.add_argument("--medir", help="foto: recorta e compara antes/depois")
    p.add_argument("--recortar", help="foto: só recorta")
    p.add_argument("--saida", default="")
    p.add_argument("--produto", default="", help="ajuda o Vision a julgar")
    p.add_argument("--pasta", default="/tmp/recorte")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    if args.recortar:
        alvo = Path(args.saida or "/tmp/recorte/limpo.png")
        r = recortar(Path(args.recortar), alvo)
        print(json.dumps(r, ensure_ascii=False, indent=2) if args.json
              else f"[recorte] {'✅' if r['ok'] else '❌'} {r['motivo']}")
        return 0 if r["ok"] else 1

    if not args.medir:
        p.error("use --medir FOTO ou --recortar FOTO")

    r = medir(Path(args.medir), args.produto, Path(args.pasta))
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r.get("ok") else 1

    if not r.get("ok"):
        _log(f"❌ {r.get('recorte', {}).get('motivo') or r.get('motivo')}")
        if r.get("antes"):
            a = r["antes"]
            _log(f"   (a foto original: {a.get('veredito')} · "
                 f"{_num(a.get('densidade'))} de texto em "
                 f"{'/'.join(a.get('faixas') or []) or '—'})")
        return 1

    a, d = r["antes"], r["depois"]
    print()
    print(f"  {'':12} {'ANTES':>26}   {'DEPOIS':>26}")
    print("  " + "─" * 68)
    for rot, ka in (("veredito", "veredito"), ("densidade", "densidade"),
                    ("tipo", "tipo"), ("conflito", "conflito")):
        print(f"  {rot:12} {str(a.get(ka)):>26}   {str(d.get(ka)):>26}")
    print(f"  {'faixas':12} {'/'.join(a.get('faixas') or []) or '—':>26}   "
          f"{'/'.join(d.get('faixas') or []) or '—':>26}")
    print("  " + "─" * 68)
    _log(f"{r['recorte']['motivo']}")
    if r.get("comparacao"):
        _log(f"lado a lado: {r['comparacao']}")
    _log("⚠️ o número diz se o TEXTO saiu. Se o PRODUTO sobreviveu, quem "
         "responde é o olho — abra a comparação.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
