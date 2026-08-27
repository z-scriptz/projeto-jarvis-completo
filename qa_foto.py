#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# qa_foto.py — A FOTO DO PRODUTO SERVE PRA UM SLIDE NOSSO?
#
# ⚠️ NASCEU DA RECLAMAÇÃO MAIS ANTIGA QUE SOBROU (26/08). O Dre disse, e o
# revisor repetiu três vezes: o slide 4 tem "o design do Jarvis + o design do
# vendedor dentro dele". A foto de catálogo da Shopee vem com "Cor Exclusiva",
# "MagSafe Magnético", "Proteção de Câmera", selo, ícones e a marca da loja
# CRAVADOS NA IMAGEM. Nenhum CSS conserta isso: o estrago está nos pixels.
#
# ⚠️ E ISSO PIOROU CONFORME O RESTO MELHOROU. Quando o carrossel inteiro era
# irregular, um anúncio no meio passava. Agora que a capa, a quebra, o resumo e
# o CTA estão coerentes, o slide de catálogo é a única coisa que grita
# "propaganda" — chama mais atenção justamente porque destoa.
#
# ⚠️ O MODELO DIZ O QUE VÊ; O PLACAR É CÓDIGO. Perguntar "de 0 a 10, quão boa é
# esta foto?" devolve um número que muda de humor entre chamadas e não dá pra
# auditar. Aqui a visão responde SÓ fatos observáveis ("tem preço escrito na
# imagem?"), e a política — quanto cada fato pesa, onde fica o corte — mora
# neste arquivo, em Python, visível e ajustável sem tocar em prompt.
#
# ⚠️ CACHE POR CONTEÚDO, senão isto vira uma conta cara. O mesmo produto volta
# em vários carrosséis, e a foto dele é byte a byte a mesma. Uma chamada por
# imagem, para sempre.
#
# USO:
#   from qa_foto import aprovada
#   if not aprovada(caminho): ...      # escolhe outro produto
#
#   python3 qa_foto.py <arquivo>...    # inspeciona na mão

import hashlib
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CACHE = BASE_DIR / "shared" / "qa_fotos.json"

# ⚠️ OS PESOS SÃO A POLÍTICA, e ficam aqui em cima porque é o que se ajusta.
# Positivo = o que a gente quer ver num slide de produto; negativo = o que
# denuncia peça de marketplace. As magnitudes não são chute: "preço na imagem"
# e "print de marketplace" pesam mais porque são os dois que fazem o slide
# parecer anúncio de terceiro dentro do nosso post.
PESOS = {
    "produto_limpo":       +3,   # o produto, sem cenário de venda em volta
    "produto_em_uso":      +3,   # alguém usando — comunica benefício sozinho
    "fundo_real":          +2,   # ambiente de verdade, não fundo de estúdio
    "texto_pequeno":       -1,   # uma legenda discreta, tolerável
    "selo_promocional":    -2,   # "OFERTA", "FRETE GRÁTIS", roseta
    "marca_do_vendedor":   -2,   # logo da loja cravado
    "muitos_icones":       -2,   # a grade de benefícios com ícones
    "preco_na_imagem":     -3,   # o preço é NOSSO, o slide já mostra
    "print_marketplace":   -4,   # captura de tela da listagem
}
PISO = 0            # abaixo disto, reprova

_MIMES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
          ".webp": "image/webp"}
_AVISADO = False    # o primeiro erro basta pra diagnosticar


def _digestao(caminho) -> str:
    return hashlib.sha1(Path(caminho).read_bytes()).hexdigest()


def _cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _gravar(cache: dict):
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    except Exception:
        pass


_PERGUNTA = """Olhe esta foto de produto de e-commerce e responda SO com JSON.
Nao avalie se e bonita: diga o que ESTA na imagem.

{"produto_limpo": <true se mostra o produto sem cartelas, faixas ou colagem
                   de venda em volta>,
 "produto_em_uso": <true se uma pessoa esta usando/segurando o produto>,
 "fundo_real": <true se o fundo e um ambiente de verdade, nao fundo liso de
                estudio nem colagem>,
 "texto_pequeno": <true se ha texto pequeno cravado na imagem>,
 "selo_promocional": <true se ha selo/faixa tipo OFERTA, DESCONTO, FRETE
                      GRATIS, NOVO>,
 "marca_do_vendedor": <true se ha logo ou nome de loja cravado>,
 "muitos_icones": <true se ha grade de icones ou lista de beneficios escrita
                   dentro da imagem>,
 "preco_na_imagem": <true se ha preco em reais escrito na imagem>,
 "print_marketplace": <true se parece captura de tela de uma pagina de loja>}

Responda apenas o JSON, sem cerca de codigo."""


def _perguntar(caminho: Path) -> dict:
    """Uma chamada de visão. {} quando não dá — e {} NÃO reprova nada."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return {}
    try:
        from google import genai
        from google.genai import types
        cli = genai.Client(api_key=key)
        r = cli.models.generate_content(
            # ⚠️ mesma variável que o resto do projeto usa pra visão. Uma
            # config própria aqui envelheceria sozinha — foi assim que o
            # `gemini-2.0-flash` aposentado derrubou o --sugerir-lotes.
            model=os.environ.get("GEMINI_MODELO_TXT", "gemini-2.5-flash"),
            contents=[types.Part.from_bytes(
                          data=Path(caminho).read_bytes(),
                          mime_type=_MIMES.get(Path(caminho).suffix.lower(),
                                               "image/jpeg")),
                      _PERGUNTA])
        txt = (r.text or "").strip()
        if txt.startswith("```"):
            txt = txt.split("```")[1].lstrip("json").strip()
        d = json.loads(txt)
        return d if isinstance(d, dict) else {}
    except Exception as e:
        # ⚠️ ESTE AVISO É OBRIGATÓRIO PORQUE ESTA FUNÇÃO APROVA NA DÚVIDA. Com
        # a visão fora do ar, `aprovada()` passa a devolver True pra tudo — o
        # QA some e o log fica idêntico ao de um dia em que nenhuma foto era
        # ruim. Um modelo aposentado derrubou o `--sugerir-lotes` do mesmo
        # jeito, e só apareceu porque alguém foi conferir.
        # 📌 Guarda-costas que falha calado é pior que não ter guarda-costas:
        # você continua andando achando que está protegido.
        global _AVISADO
        if not _AVISADO:
            _AVISADO = True
            print(f"⚠️  qa_foto: a visão falhou ({str(e)[:110]}) — "
                  f"APROVANDO TUDO até isso ser resolvido", file=sys.stderr)
        return {}


def nota(caminho) -> tuple:
    """(placar, fatos) — o placar somado a partir do que a visão enxergou.

    ⚠️ FATO AUSENTE NÃO PUNE. Se a visão falhar ou vier sem uma chave, aquele
    peso simplesmente não entra. Uma foto boa não pode ser reprovada porque a
    API caiu — o custo de barrar um produto bom é maior que o de deixar passar
    um ruim de vez em quando."""
    caminho = Path(caminho)
    if not caminho.exists():
        return 0, {}
    chave = _digestao(caminho)
    cache = _cache()
    if chave in cache:
        fatos = cache[chave]
    else:
        fatos = _perguntar(caminho)
        if not fatos:
            return 0, {}          # sem informação: neutro, e não guarda
        cache[chave] = fatos
        _gravar(cache)
    placar = sum(peso for campo, peso in PESOS.items() if fatos.get(campo))
    return placar, fatos


def aprovada(caminho, piso: int = None) -> bool:
    """True se a foto pode virar slide. Sem chave de API, aprova tudo.

    ⚠️ APROVAR NA DÚVIDA É DE PROPÓSITO. Esta função entra no meio da produção
    de conteúdo; se ela reprovasse quando não sabe, uma variável de ambiente
    faltando pararia a esteira das seis contas em silêncio — que é exatamente o
    tipo de falha que a gente passou o dia caçando."""
    piso = PISO if piso is None else piso
    placar, fatos = nota(caminho)
    if not fatos:
        return True
    return placar >= piso


def _motivos(fatos: dict) -> str:
    """O que pesou, do pior pro melhor — pra caber numa linha de log."""
    itens = [(PESOS[c], c) for c in fatos if fatos.get(c) and c in PESOS]
    return ", ".join(f"{c}({p:+d})" for p, c in sorted(itens)) or "nada notável"


def main(argv=None) -> int:
    alvos = list(argv or sys.argv[1:])
    if not alvos:
        print("uso: qa_foto.py <arquivo.jpg> [...]")
        return 2
    for a in alvos:
        placar, fatos = nota(a)
        if not fatos:
            print(f"?  {Path(a).name[:44]:46} (sem resposta da visão)")
            continue
        print(f"{'✅' if placar >= PISO else '❌'} {placar:+3d}  "
              f"{Path(a).name[:36]:38} {_motivos(fatos)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
