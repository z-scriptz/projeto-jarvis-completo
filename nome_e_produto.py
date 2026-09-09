#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# nome_e_produto.py -- isto é o NOME DE UM PRODUTO, ou um pedaço de legenda?
#
# O ACHADO (08/09/2026)
# ─────────────────────
# Depois de o juiz de imagem limpar a fila, sobrou isto em `pronto_para_postar`,
# tudo aprovado com ✅:
#
#     assim aguentar frio          ·  Facilitam dia dia
#     salva não perder nenhum      ·  Pro dia das mães
#     Valem cada centavoo          ·  série achadinhos não precisava até
#
# Nenhum é produto. São pedaços de LEGENDA que viraram nome — a
# `_termo_heuristico` corta a primeira frase da legenda, tira as palavras
# funcionais e devolve as cinco que sobram. Nas fontes brasileiras a legenda é
# conversa ("salva pra não perder nenhum"), não nome de coisa.
#
# ⚠️ POR QUE O JUIZ DE IMAGEM NÃO PEGA: a pergunta dele é "o vídeo mostra
# ISTO?". Perguntar "o vídeo mostra 'salva não perder nenhum'?" não tem resposta
# possível, e o modelo chuta SIM. Não é falha do juiz — é pergunta errada. A
# pergunta certa é sobre o TEXTO, sozinho, sem vídeo nenhum.
#
# ⚠️ E A REGRA QUE JÁ EXISTIA NÃO COBRE. O `shared/termos.nome_de_produto_ruim`
# pergunta "sobra alguma palavra que diga o que é a coisa?" — e 'assim aguentar
# frio' tem três palavras que não estão em lista de lixo nenhuma. Medido: passou
# em 9 de 9. A regra está certa pro que ela foi feita (rótulo interno vazado);
# este padrão é outro, e empilhar mais palavra na lista dela ia estragar a
# regra antiga sem resolver esta.
#
# ⚠️ OS DOIS ERROS CUSTAM COISAS DIFERENTES, E ISSO DECIDE O DESENHO:
#   · falso POSITIVO (chamar produto de frase) → some pacote bom, em silêncio,
#     e no volume da coleta isso come a fila inteira sem ninguém ver.
#   · falso NEGATIVO (deixar frase passar) → um vídeo vai ao ar vendendo
#     "salva não perder nenhum".
# O segundo é feio; o primeiro é caro e invisível. Por isso NA DÚVIDA É
# PRODUTO: só 'frase' bloqueia, e qualquer outra coisa (erro, formato
# inesperado, API fora) deixa passar.
#
#   .venv/bin/python nome_e_produto.py --controle    # mede os DOIS lados
#   .venv/bin/python nome_e_produto.py --fila        # o que está pra ir ao ar
#   .venv/bin/python nome_e_produto.py --fila --marcar
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PRONTOS = BASE_DIR / "pronto_para_postar"
REPROVADOS = BASE_DIR / "reprovado_nome"
MODELO = os.getenv("GEMINI_MODELO_NOME", "gemini-2.5-flash")


def _carregar_env():
    for cand in (BASE_DIR / ".env", Path(".env")):
        if not cand.exists():
            continue
        for linha in cand.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            k, _, v = linha.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        return cand
    return None


_PROMPT = (
    "Abaixo vem UM texto, que saiu de um sistema que tenta extrair o nome de um "
    "produto da legenda de um vídeo. Às vezes ele acerta e às vezes devolve um "
    "pedaço da legenda.\n\n"
    "PERGUNTA: este texto é o NOME DE UM PRODUTO, ou é um pedaço de frase?\n\n"
    "PRODUTO — nomeia um objeto que dá pra comprar numa loja. Pode ser FEIO, "
    "ter marca, número, medida, caixa alta, palavra em inglês, erro de "
    "português. Nada disso importa: se dá pra procurar numa loja e receber uma "
    "coisa, é PRODUTO.\n"
    # ⚠️ NENHUM EXEMPLO DAQUI PODE ESTAR NO CONTROLE (08/09/2026). A 1ª versão
    # usava como exemplo as MESMAS frases e produtos da lista de controle — 10
    # dos 28 itens. O 100%/100% que ela deu media o modelo repetindo o que eu
    # tinha acabado de mostrar, não julgando. É a mesma falha do `--frame0`
    # desta semana, agora dentro da minha própria prova. `teste_nome_produto`
    # falha se a sobreposição voltar.
    "  ex.: 'Panela de Vidro Borossilicato com Tampa', 'aspirador de cama', "
    "'fita silicone vedação fogão', 'meia térmica masculina'\n\n"
    "FRASE — é conversa, opinião ou pedaço de legenda. Costuma ter verbo "
    "conjugado, primeira pessoa, ou simplesmente não nomeia objeto nenhum.\n"
    "  ex.: 'olha só que coisa linda', 'não acreditei quando vi', "
    "'todo mundo precisa disso', 'juro que vale muito'\n\n"
    "⚠️ NA DÚVIDA responda PRODUTO. Nome esquisito de marketplace é comum; "
    "jogar fora um produto bom custa mais caro que deixar passar uma frase.\n\n"
    "Responda em uma linha:\nPRODUTO | <2 a 5 palavras do porquê>\n"
    "ou\nFRASE | <2 a 5 palavras do porquê>\n\n"
    "Texto: {nome}"
)


def ler_veredito(bruto: str) -> str:
    """'produto' | 'frase' | 'erro'. Pura, pra testar sem API.

    ⚠️ QUALQUER COISA QUE NÃO SEJA UM 'FRASE' EXPLÍCITO TEM QUE ACABAR EM
    'produto' OU 'erro' — nunca o contrário. Quem chama só bloqueia em 'frase',
    então um parser generoso pro lado errado apagaria pacote bom em silêncio,
    que é o erro caro deste arquivo.
    """
    import unicodedata
    cabeca = (bruto or "").partition("|")[0]
    t = "".join(c for c in unicodedata.normalize("NFD", cabeca)
                if unicodedata.category(c) != "Mn").upper().strip()
    t = t.lstrip("*_ -\t")
    if t.startswith("FRASE"):
        return "frase"
    if t.startswith("PRODUTO"):
        return "produto"
    return "erro"


def bloqueia(veredito: str) -> bool:
    """Este veredito manda descartar? Só 'frase'. Ver o cabeçalho pro porquê."""
    return (veredito or "").strip().lower() == "frase"


def julgar(nome: str):
    """(veredito, tokens). Texto puro — sem imagem, então custa quase nada."""
    nome = (nome or "").strip()
    if not nome:
        return "erro", 0
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return "erro", 0
    try:
        from google import genai
        cli = genai.Client(api_key=key)
        r = cli.models.generate_content(
            model=MODELO,
            contents=[{"parts": [{"text": _PROMPT.format(nome=nome[:120])}]}])
        u = getattr(r, "usage_metadata", None)
        toks = int(getattr(u, "total_token_count", 0) or 0) if u else 0
        return ler_veredito((r.text or "").strip().split("\n")[0]), toks
    except Exception as e:
        print(f"      ⚠️ {str(e)[:70]}")
        return "erro", 0


# ══════════════════════════════════════════════════════════════════════════
# O CONTROLE — mede OS DOIS LADOS, porque os dois erros doem
#
# ⚠️ AQUI NÃO DÁ PRA EMBARALHAR PARES como no `conferir_match`: não existe "par"
# num juiz de texto. O controle certo é um conjunto ROTULADO — e eu tenho
# rótulo de verdade, tirado da fila de produção de 08/09, não inventado.
# ══════════════════════════════════════════════════════════════════════════
# Saíram da fila real. Nenhum é produto.
FRASES = [
    "assim aguentar frio", "Facilitam dia dia", "salva não perder nenhum",
    "Pro dia das mães", "série achadinhos não precisava até",
    "Valem cada centavoo", "Preciso ontem", "sou apaixonadaa",
    "Nós donas casa nutella fazemos", "hagas esto",
    "stepped into the crowd taking", "Cosas deberías hacer mejorar apariencia",
]
# ⚠️ ESTES SÃO O LADO QUE IMPORTA MAIS. Foram escolhidos por serem DIFÍCEIS:
# curtos, com verbo, com gíria, sem cara de catálogo. Se o juiz reprovar
# 'Escova lava carro giratória' porque 'lava' é verbo, ele come a fila.
PRODUTOS = [
    "Escova lava carro giratória", "pantufa cogumelo", "Cobra robótica",
    "Bloqueador Wi-Fi", "tinta efeito granilite", "Escada rolante",
    "soco inglês choque", "mini bomba de ar", "Medalhão ultrassom",
    "spray de defesa pessoal", "Capacho de pegadas de sangue",
    "Kit 3 Necessaire Impermeável Washbag Bolsa", "descascador de maçã elétrico",
    "porta cotonete ovelha", "Ímãs de geladeira Naruto", "fone de ouvido ovo",
]


def _controle() -> int:
    print("\n🔬 CONTROLE: conjunto rotulado, tirado da fila de produção\n")
    tokens = 0
    print("── FRASES (o juiz TEM que reprovar) ──")
    acertos_f = 0
    for n in FRASES:
        v, tk = julgar(n)
        tokens += tk
        if bloqueia(v):
            acertos_f += 1
        print(f"   {'✅' if bloqueia(v) else '❌'} {v:8} {n[:52]}")
    print("\n── PRODUTOS (o juiz NÃO pode reprovar) ──")
    acertos_p = 0
    for n in PRODUTOS:
        v, tk = julgar(n)
        tokens += tk
        if not bloqueia(v):
            acertos_p += 1
        print(f"   {'✅' if not bloqueia(v) else '❌'} {v:8} {n[:52]}")

    pf = acertos_f / len(FRASES) * 100
    pp = acertos_p / len(PRODUTOS) * 100
    print(f"\n── resultado ──")
    print(f"   pega frase ...........: {acertos_f}/{len(FRASES)} ({pf:.0f}%)")
    print(f"   poupa produto ........: {acertos_p}/{len(PRODUTOS)} ({pp:.0f}%)")
    if tokens:
        usd = float(os.getenv("GEMINI_USD_POR_MTOK", "0.30"))
        brl = float(os.getenv("USD_BRL", "5.40"))
        print(f"   🪙 {tokens:,} tokens · R$ {tokens/1_000_000*usd*brl:.4f} "
              f"({tokens/(len(FRASES)+len(PRODUTOS)):.0f} tokens por nome)")

    # ⚠️ O PISO DE 'POUPA PRODUTO' É MAIS ALTO QUE O DE 'PEGA FRASE', DE
    # PROPÓSITO. Deixar frase passar é feio e raro (~4% da fila). Reprovar
    # produto é caro e some calado, e roda em CADA coleta.
    print()
    if pp < 90:
        print(f"   🚫 NÃO LIGUE: ele reprova produto bom demais ({100-pp:.0f}%).")
        print(f"      Com isso ligado na coleta, a fila seca sem ninguém ver.")
        return 1
    if pf < 60:
        print(f"   ⚠️ FRACO: poupa produto, mas só pega {pf:.0f}% das frases.")
        print(f"      Não estraga nada; também não resolve muito. Seu chamado.")
        return 0
    print(f"   ✅ PRESTA: pega {pf:.0f}% das frases e poupa {pp:.0f}% dos produtos.")
    return 0


def _fila(marcar: bool) -> int:
    if not PRONTOS.exists():
        print(f"❌ {PRONTOS} não existe")
        return 1
    alvos = []
    for pasta in sorted(PRONTOS.iterdir()):
        if not pasta.is_dir():
            continue
        ej = pasta / "engajamento.json"
        if not ej.exists() or not list(pasta.glob("video.*")):
            continue
        try:
            info = json.loads(ej.read_text(encoding="utf-8"))
        except Exception:
            continue
        nome = (info.get("produto") or "").strip()
        if nome:
            alvos.append((pasta, nome))
    print(f"📦 {len(alvos)} vídeo(s) na fila\n")
    if not alvos:
        return 0

    import shutil
    frases, tirados, tokens = 0, 0, 0
    for pasta, nome in alvos:
        v, tk = julgar(nome)
        tokens += tk
        if not bloqueia(v):
            continue
        frases += 1
        print(f"   🗣️  não é produto: {nome[:60]}")
        if marcar:
            REPROVADOS.mkdir(parents=True, exist_ok=True)
            destino = REPROVADOS / pasta.name
            if not destino.exists():
                try:
                    pasta.rename(destino)      # MOVE, não apaga
                    tirados += 1
                except Exception as e:
                    print(f"      ⚠️ não movi: {str(e)[:60]}")

    print(f"\n── resultado ──")
    print(f"   🗣️  {frases} de {len(alvos)} não são nome de produto "
          f"({frases/len(alvos)*100:.1f}%)")
    if marcar:
        print(f"   🚫 {tirados} tirado(s) → {REPROVADOS.name}/ "
              f"(reversível: é só mover de volta)")
    else:
        print(f"   (nada foi alterado — use --marcar)")
    if tokens:
        usd = float(os.getenv("GEMINI_USD_POR_MTOK", "0.30"))
        brl = float(os.getenv("USD_BRL", "5.40"))
        print(f"   🪙 {tokens:,} tokens · R$ {tokens/1_000_000*usd*brl:.3f}")
    return 0


def main() -> int:
    arq = _carregar_env()
    print(f"📄 .env: {arq or '(não achei)'}")
    args = sys.argv[1:]
    if not os.getenv("GEMINI_API_KEY"):
        print("❌ GEMINI_API_KEY não encontrada")
        return 1
    if "--controle" in args:
        return _controle()
    if "--fila" in args:
        return _fila("--marcar" in args)
    print("uso: --controle | --fila [--marcar]")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
