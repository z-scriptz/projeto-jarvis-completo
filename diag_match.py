#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# diag_match.py -- em qual estágio o vídeo deixou de ser sobre o produto?
#
# O QUE O DRE VIU (07/09/2026)
# ────────────────────────────
# *"os hooks ainda estão horríveis, alguns meio nada a ver"*. Peguei 15 pacotes
# e três eram isto:
#
#   produto: Guia Dupla Retrátil para 2 Cães
#   legenda: "V stepped into the crowd... Vogue World: Hollywood"
#
#   produto: spray de defesa pessoal
#   legenda: "Behind the scenes at a high-profile Hollywood after-party, @thv"
#
#   produto: Meia Calça Infantil para Ballet
#   legenda: "Your feet won't get cold anymore 😏 #gadgets #coolgadgets"
#
# ⚠️ E O HOOK ESTAVA CERTO NOS TRÊS. Ele é escrito a partir do NOME DO PRODUTO;
# se o produto está errado, o hook sai coerente com uma coisa que o vídeo não
# mostra. "Hook nada a ver" é SINTOMA. A doença está antes.
#
# ⚠️ MAS ANTES ONDE? SÃO TRÊS ESTÁGIOS, E EU NÃO SEI QUAL É — É PRA ISSO QUE
# ESTE ARQUIVO EXISTE. O caminho é:
#
#     legenda/vídeo → TERMO → busca na Shopee → PRODUTO
#                     (1)      (2)              (3)
#
#   (1) o termo saiu errado da legenda (heurística pegou frase em inglês)
#   (2) o termo saiu errado da VISÃO (o Gemini olhou e alucinou)
#   (3) o termo estava CERTO e a LOJA devolveu outra coisa
#
# Os três produzem o mesmo sintoma na fila e pedem consertos diferentes. Chutar
# qual é custaria um dia de trabalho no lugar errado — já aconteceu nesta
# semana (o `--frame0` que media algo *parecido* e aprovava o pacote venenoso).
#
# 📌 O SINAL QUE SEPARA (1)/(2) DE (3) É GRÁTIS: basta imprimir o `termo` ao
# lado do `produto`. Ambos deveriam ser português e falar da mesma coisa.
#   · termo "stepped into the crowd" → quebrou em (1)
#   · termo "meia térmica" + produto "Meia Calça Infantil Ballet" → quebrou (3)
#
# ⚠️ O `parentesco` É PENEIRA, NÃO VEREDITO. Ele erra pra mais em sinônimo
# honesto ("balde de gelo" → "Cooler Térmico 10L" não compartilha palavra e
# pontua 0). Por isso o `--olho` existe: quem dá a sentença é o Gemini olhando
# o VÍDEO contra o nome do produto — o mesmo desenho do `conferir_match`.
#
#   .venv/bin/python diag_match.py                # censo grátis, sem API
#   .venv/bin/python diag_match.py --listar 40    # os piores, pra ler
#   .venv/bin/python diag_match.py --olho 60      # o Gemini assiste e julga
import json
import os
import random
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
FEITOS = BASE / "inbox_tiktok" / "_produzidos"
INBOX = BASE / "inbox_tiktok"

# palavras que aparecem em quase todo título de marketplace e não provam nada
_VAZIAS = {
    "para", "com", "sem", "dos", "das", "kit", "unidades", "unidade", "pecas",
    "peca", "novo", "nova", "original", "importado", "profissional", "alta",
    "qualidade", "cores", "cor", "tamanho", "grande", "pequeno", "portatil",
    "casa", "feminino", "masculino", "infantil", "premium", "super", "mais",
    "conjunto", "jogo", "modelo", "tipo", "estilo", "linha", "und",
}
_EN_OBVIO = {"the", "and", "you", "your", "this", "that", "for", "with", "was",
             "were", "into", "was", "his", "her", "they", "them", "what", "when",
             "how", "why", "from", "have", "has", "been", "will", "would", "can"}


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t or "")
                   if unicodedata.category(c) != "Mn")


def _palavras(t: str) -> list:
    """Palavras significativas, sem acento, minúsculas, ≥4 letras."""
    bruto = re.findall(r"[A-Za-zÀ-ÿ]{4,}", _sem_acento(t or "").lower())
    return [p for p in bruto if p not in _VAZIAS]


def parentesco(termo: str, produto: str) -> float:
    """Quanto do TERMO buscado sobreviveu no PRODUTO que a loja devolveu (0 a 1).

    Pura, pra dar pra testar sem inbox nem API.

    ⚠️ COMPARA POR PREFIXO DE 4 LETRAS, não por igualdade: 'meia'/'meias',
    'organizador'/'organizadora', 'copo'/'copos' são a mesma coisa e igualdade
    exata diria que não são. Quatro letras porque foi o que sobrou depois de
    'cabo'/'cabide' colidirem com três.

    ⚠️ RETORNA 0.0 QUANDO NÃO DÁ PRA AFIRMAR NADA (termo sem palavra útil), e
    quem chama tem que tratar isso como "não sei", não como "não casa".
    """
    a, b = _palavras(termo), _palavras(produto)
    if not a or not b:
        return 0.0
    bat = 0
    for p in a:
        if any(p[:4] == q[:4] for q in b):
            bat += 1
    return bat / len(a)


def parece_gringo(termo: str) -> bool:
    """O termo é pedaço de legenda em inglês em vez de nome de produto?

    ⚠️ NÃO REUSA O `_palavras` — E O TESTE PEGOU ISSO. O `_palavras` corta tudo
    com menos de 4 letras porque, pro parentesco, palavra curta é ruído. Só que
    as provas mais fortes de inglês são justamente as curtas: 'the', 'you',
    'for', 'was'. Com o corte de 4, `'The Most Viral Gadget Must'` — legenda
    real que já entrou na fila em 04/09 — passava como português.
    Peneira boa pra uma pergunta não serve pra outra só porque estava por perto.
    """
    palavras = re.findall(r"[a-z]{2,}", _sem_acento(termo or "").lower())
    return any(p in _EN_OBVIO for p in palavras)


def _pacotes():
    for raiz in (FEITOS, INBOX):
        if not raiz.exists():
            continue
        for pasta in sorted(raiz.iterdir()):
            if not pasta.is_dir() or pasta.name.startswith("_"):
                continue
            pj = pasta / "plano.json"
            if not pj.exists():
                continue
            try:
                yield pasta, json.loads(pj.read_text(encoding="utf-8"))
            except Exception:
                continue


# ══════════════════════════════════════════════════════════════════════════
# O VEREDITO: o Gemini ASSISTE o vídeo e diz se é aquele produto
# ══════════════════════════════════════════════════════════════════════════
_PROMPT = (
    "Estes são frames de um vídeo curto. Abaixo, o nome do produto que nós "
    "anunciamos junto com ele.\n\n"
    "PERGUNTA: o vídeo mostra ESTE produto (ou um equivalente direto dele)?\n\n"
    "Seja RIGOROSO com a categoria e TOLERANTE com marca, cor e modelo:\n"
    "· CASA    — é o mesmo tipo de objeto, com a mesma função. Marca/cor/modelo\n"
    "            diferentes CASAM. Um copo térmico de outra marca CASA.\n"
    "· NAOCASA — é outra categoria de objeto, ou o vídeo não mostra produto\n"
    "            nenhum (bastidores, show, desfile, pessoa falando).\n\n"
    "Responda em uma linha:\nCASA | <3 a 8 palavras do que você viu>\n"
    "ou\nNAOCASA | <3 a 8 palavras do que você viu>\n\n"
    "Produto anunciado: {produto}"
)


def ler_veredito(bruto: str) -> str:
    """'casa' | 'naocasa' | 'erro'. Pura, pra testar sem API.

    ⚠️ A ORDEM IMPORTA: 'NAOCASA' CONTÉM 'CASA'. Testar `startswith('CASA')`
    primeiro classificaria todo NAOCASA como casa — e o erro seria silencioso e
    a favor de deixar passar, que é o pior lado pra errar aqui.
    """
    cabeca = (bruto or "").partition("|")[0]
    t = _sem_acento(cabeca).upper().replace(" ", "").replace("-", "")
    if t.startswith("NAOCASA"):
        return "naocasa"
    if t.startswith("CASA"):
        return "casa"
    return "erro"


def _frames(video: Path, dur: float, n: int = 2) -> list:
    saida, tmps = [], []
    d = float(dur) or 8.0
    for i in range(n):
        pos = max(0.5, d * (i + 1) / (n + 1))
        f = video.with_suffix(f".dm{i}.jpg")
        tmps.append(f)
        try:
            subprocess.run(["ffmpeg", "-y", "-ss", f"{pos:.1f}", "-i", str(video),
                            "-vframes", "1", "-vf", "scale=480:-1", "-q:v", "5",
                            str(f)], capture_output=True, timeout=60)
            if f.exists() and f.stat().st_size > 500:
                saida.append(f.read_bytes())
        except Exception:
            pass
    for f in tmps:
        try:
            f.unlink()
        except Exception:
            pass
    return saida


def _olhar(amostra: int) -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("❌ GEMINI_API_KEY vazio — o --olho precisa dela")
        return 1
    from google import genai
    from google.genai import types
    cli = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    cands = []
    for pasta, d in _pacotes():
        vids = [v for v in pasta.glob("video.*")
                if v.suffix.lower() in (".mp4", ".mov", ".m4v")]
        if vids and (d.get("produto") or "").strip():
            cands.append((pasta, d, vids[0]))
    if not cands:
        print("❌ nenhum pacote com vídeo + produto")
        return 1
    random.seed(int(os.getenv("SEED", "7")))
    lote = random.sample(cands, min(amostra, len(cands)))
    print(f"👁️  o Gemini vai assistir {len(lote)} de {len(cands)} pacotes\n")

    casa = naocasa = erro = tokens = 0
    ruins = []
    for i, (pasta, d, v) in enumerate(lote, 1):
        prod = (d.get("produto") or "").strip()
        fr = _frames(v, d.get("duracao") or d.get("views_dur") or 0)
        if not fr:
            erro += 1
            continue
        try:
            partes = [types.Part.from_bytes(data=b, mime_type="image/jpeg") for b in fr]
            r = cli.models.generate_content(
                model="gemini-2.5-flash",
                contents=partes + [_PROMPT.format(produto=prod[:90])])
            bruto = (r.text or "").strip().split("\n")[0]
            try:
                tokens += int(r.usage_metadata.total_token_count or 0)
            except Exception:
                pass
        except Exception as e:
            erro += 1
            print(f"   ⚠️ {i:3}. erro de API: {str(e)[:60]}")
            continue
        ver = ler_veredito(bruto)
        motivo = bruto.partition("|")[2].strip()[:46]
        if ver == "casa":
            casa += 1
        elif ver == "naocasa":
            naocasa += 1
            ruins.append((pasta.name, prod, d.get("termo", ""), motivo,
                          (d.get("descricao") or "").replace("\n", " ")[:70]))
            print(f"   ❌ {i:3}. {prod[:44]:46} → {motivo}")
        else:
            erro += 1
            print(f"   ⁉️ {i:3}. resposta fora do formato: {bruto[:60]}")

    n = casa + naocasa
    print(f"\n── veredito ──")
    if n:
        print(f"   ✅ {casa} casam · ❌ {naocasa} NÃO casam ({naocasa/n*100:.0f}%) "
              f"· ⁉️ {erro} sem resposta")
    if ruins:
        print(f"\n── os que não casam, com o TERMO que os gerou ──")
        print(f"   (o termo diz QUAL estágio quebrou — leia o cabeçalho)")
        for nome, prod, termo, motivo, leg in ruins:
            est = ("(1)/(2) TERMO" if (parece_gringo(termo) or not termo)
                   else "(3) LOJA" if parentesco(termo, prod) < 0.34
                   else "(?)")
            print(f"\n   {est}")
            print(f"      produto : {prod[:70]}")
            print(f"      termo   : {termo[:70]}")
            print(f"      viu     : {motivo}")
            print(f"      legenda : {leg}")
    if tokens:
        usd = float(os.getenv("GEMINI_USD_POR_MTOK", "0.30"))
        brl = float(os.getenv("USD_BRL", "5.40"))
        print(f"\n   🪙 {tokens:,} tokens · R$ {tokens/1_000_000*usd*brl:.2f}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if "--olho" in args:
        try:
            return _olhar(int(args[args.index("--olho") + 1]))
        except (IndexError, ValueError):
            print("uso: --olho N")
            return 1

    listar = 0
    if "--listar" in args:
        try:
            listar = int(args[args.index("--listar") + 1])
        except (IndexError, ValueError):
            listar = 30

    total = 0
    sem_termo = gringo = 0
    faixas = Counter()
    suspeitos = []
    por_perfil = Counter()
    origem = Counter()
    for pasta, d in _pacotes():
        prod = (d.get("produto") or "").strip()
        termo = (d.get("termo") or "").strip()
        if not prod:
            continue
        total += 1
        # `termo_por` só existe em pacotes coletados de 07/09 pra frente. Nos
        # antigos ele vem vazio, e vazio aqui é "não registrei", não "nenhum".
        origem[d.get("termo_por") or "(antes do registro)"] += 1
        if not termo:
            sem_termo += 1
            continue
        if parece_gringo(termo):
            gringo += 1
            suspeitos.append(("TERMO GRINGO", 0.0, pasta.name, prod, termo,
                              (d.get("descricao") or "").replace("\n", " ")[:70]))
            por_perfil[d.get("perfil_fonte") or "?"] += 1
            continue
        p = parentesco(termo, prod)
        faixas["0 (nada em comum)" if p == 0 else
               "0–33%" if p < 0.34 else
               "34–66%" if p < 0.67 else "67–100%"] += 1
        if p < 0.34:
            suspeitos.append(("LOJA DEVOLVEU OUTRO", p, pasta.name, prod, termo,
                              (d.get("descricao") or "").replace("\n", " ")[:70]))
            por_perfil[d.get("perfil_fonte") or "?"] += 1

    if not total:
        print("❌ nenhum pacote com produto em inbox_tiktok/ — rode na VPS")
        return 1

    print(f"\n📦 {total} pacotes com produto\n")
    print(f"── quem decidiu o termo (campo `termo_por`, novo em 07/09) ──")
    for k, n in origem.most_common():
        print(f"   {k:24} {n:5}  ({n/total*100:.1f}%)")
    print(f"\n── estágio 1/2: o TERMO saiu do vídeo ou da legenda? ──")
    print(f"   sem termo nenhum ..................... {sem_termo:5}  "
          f"({sem_termo/total*100:.1f}%)")
    print(f"   termo é pedaço de legenda em inglês .. {gringo:5}  "
          f"({gringo/total*100:.1f}%)")
    print(f"\n── estágio 3: a LOJA devolveu o que a gente pediu? ──")
    print(f"   (quanto do termo buscado sobrou no nome do produto)")
    for f in ("0 (nada em comum)", "0–33%", "34–66%", "67–100%"):
        n = faixas.get(f, 0)
        if total:
            print(f"   {f:24} {n:5}  ({n/total*100:.1f}%)")
    ruim = sum(v for k, v in faixas.items() if k in ("0 (nada em comum)", "0–33%"))
    print(f"\n   🚩 {ruim + gringo + sem_termo} de {total} suspeitos "
          f"({(ruim+gringo+sem_termo)/total*100:.1f}%)")
    print(f"\n⚠️ SUSPEITO NÃO É CULPADO. 'balde de gelo' → 'Cooler Térmico 10L' é")
    print(f"   um acerto que pontua 0 aqui. Quem julga é o `--olho`, que assiste")
    print(f"   o vídeo. Este censo serve pra dizer ONDE olhar e quanto custa.")

    if por_perfil:
        print(f"\n── de onde vêm os suspeitos (top 8 perfis) ──")
        for perfil, n in por_perfil.most_common(8):
            print(f"   {n:4}  @{perfil}")

    if listar and suspeitos:
        print(f"\n── {min(listar, len(suspeitos))} suspeitos, pra ler com o olho ──")
        for tipo, p, nome, prod, termo, leg in suspeitos[:listar]:
            print(f"\n   [{tipo}]  parentesco {p:.0%}")
            print(f"      produto : {prod[:70]}")
            print(f"      termo   : {termo[:70]}")
            print(f"      legenda : {leg}")
    elif suspeitos:
        print(f"\n   (use --listar 40 pra ler os suspeitos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
