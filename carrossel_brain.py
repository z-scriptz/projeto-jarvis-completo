#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# carrossel_brain.py — decide O QUE o carrossel vai dizer.
#
# Separado do gerador de Reels de propósito (pedido do Dre, 22/08): o Reel
# transforma anúncio em movimento; o carrossel precisa parecer CONTEÚDO. Se os
# dois saíssem do mesmo lugar, o carrossel viraria "o anúncio, em imagem".
#
# DIVISÃO DE TRABALHO — três módulos, três responsabilidades:
#   carrossel_brain   escolhe o formato, escreve o texto, monta o plano
#   carrossel_render  desenha os slides (não decide nada)
#   meta_uploader     publica (não sabe o que está publicando)
#
# ⚠️⚠️ O "DESEMPENHO HISTÓRICO POR CONTA" AINDA NÃO EXISTE PRA CARROSSEL —
# e fingir que existe seria pior que não usar.
# `shared/metricas_posts.jsonl` tem 215 registros e TODOS são de Reel; o
# arquivo nem tem campo `formato`. Escolher formato de carrossel por
# desempenho de Reel é transferir um aprendizado entre duas coisas que o
# algoritmo distribui de maneira diferente — é exatamente o erro de "o hook
# campeão" que a medição de 21/08 desmentiu em um comando.
#
# Então o cérebro tem DUAS FASES, e ele diz em qual está:
#   FASE 1 (agora)  sorteio pela distribuição-alvo, com COBERTURA garantida:
#                   enquanto uma conta não tiver `CARR_COBERTURA` carrosséis
#                   de um formato, esse formato fura a fila. Sem isso o
#                   sorteio de 40% pra Lista levaria semanas até a conta ver
#                   um "Erros" — e nunca haveria o que comparar.
#   FASE 2 (depois) quando houver cobertura, a distribuição-alvo é inclinada
#                   pelo SALVAMENTO medido por formato naquela conta.
# Cada carrossel montado é registrado em `shared/carrosseis_ledger.jsonl` com
# o formato. É esse arquivo que faz a fase 2 existir um dia.
#
# USO:
#   python3 carrossel_brain.py --nicho casa                 # monta 1 e mostra
#   python3 carrossel_brain.py --nicho pet --formato erros  # força o formato
#   python3 carrossel_brain.py --nicho tech --render pronto_carrossel/x
#   python3 carrossel_brain.py --plano                      # só o JSON, pra pipe
#
#   from carrossel_brain import montar_plano
#   plano = montar_plano("casa")

import os
import re
import sys
import json
import time
import random
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LEDGER = BASE_DIR / "shared" / "carrosseis_ledger.jsonl"
METRICAS = BASE_DIR / "shared" / "metricas_posts.jsonl"

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("carrossel_brain")


def _carregar_env():
    """Rodar na mão não carrega o .env — e sem GEMINI_API_KEY o texto cai todo
    na reserva sem ninguém perceber. Primeira ocorrência vence, igual aos
    outros carregadores do projeto."""
    for cand in (Path(".env"), BASE_DIR / ".env"):
        if not cand.exists():
            continue
        for linha in cand.read_text(encoding="utf-8", errors="ignore").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            k, _, v = linha.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        break


_carregar_env()

PALAVRAS_MAX = int(os.environ.get("CARR_PALAVRAS_MAX", "12"))
COBERTURA = int(os.environ.get("CARR_COBERTURA", "3"))


# ══════════════════════════════════════════════════════════════════════════
# OS FORMATOS
#
# ⚠️ AGRUPADOS POR ESTRUTURA, NÃO POR NOME. A lista do Dre tem 10 itens, mas
# "Lista rápida", "Produtos que parecem mentira" e "Checklist" desenham os
# MESMOS slides — muda o ângulo do hook, não a arquitetura do post. Tratá-los
# como 10 formatos distintos criaria 10 geradores quase idênticos e três
# entradas de métrica que medem a mesma coisa com nomes diferentes; aí a fase
# 2 nunca teria amostra suficiente em nenhuma delas.
# Então: 7 ESTRUTURAS, e os ângulos viram variação de hook DENTRO da lista.
#
# Os pesos são os que o Dre definiu (40/20/15/10/10/5), pelo motivo que ele
# deu: o objetivo não é só viralizar, é levar a pessoa até o produto.
# ══════════════════════════════════════════════════════════════════════════
FORMATOS = {
    "lista": {
        "peso": 40, "produtos": 5,
        "desc": "N produtos, um por slide — cobre 'lista rápida', "
                "'parecem mentira' e 'checklist'",
        "angulos": [
            "{n} produtos que parecem caros mas custam pouco",
            "{n} produtos que parecem mentira de tão baratos",
            "{n} coisas que eu compraria de novo sem pensar",
            "{n} achadinhos que resolvem problema de verdade",
            "{n} produtos que eu queria ter conhecido antes",
        ],
    },
    "erros": {
        "peso": 20, "produtos": 1, "passos": 3,
        "desc": "3 erros + solução + resultado — o campeão de alcance",
        "angulos": [
            "Você está cometendo esse erro sem perceber",
            "{n} erros que quase todo mundo comete",
            "Pare de fazer isso {contexto}",
            "O erro que me custou caro {contexto}",
        ],
    },
    "antes_depois": {
        "peso": 15, "produtos": 1, "passos": 3,
        "desc": "resultado, antes, transformação, produto — retenção alta",
        "angulos": [
            "Ninguém acreditou que foi só isso",
            "A diferença de antes pra depois",
            "Eu não esperava essa mudança",
        ],
    },
    "comparacao": {
        "peso": 10, "produtos": 2,
        "desc": "A, B, diferenças, vencedor — forte pra afiliado",
        "angulos": [
            "Qual vale mais a pena?",
            "Testei os dois e a diferença me surpreendeu",
            "Um custa o dobro. Vale?",
        ],
    },
    "passo_a_passo": {
        "peso": 10, "produtos": 1, "passos": 4,
        "desc": "etapas até o resultado — gera muitos salvamentos",
        "angulos": [
            "O jeito mais fácil de fazer isso",
            "Como resolver isso gastando pouco",
            "{n} passos e acabou",
        ],
    },
    "historia": {
        "peso": 5, "produtos": 1, "passos": 4,
        "desc": "problema, tentativa, descoberta, solução, resultado — "
                "cobre 'segredo revelado'",
        "angulos": [
            "Eu descobri isso por acaso",
            "Ninguém fala sobre isso",
            "Isso mudou completamente meu resultado",
        ],
    },
    # Estrutura pronta, peso 0: entra na roda quando o Dre quiser, sem código
    # novo — é só `CARR_PESO_MITOS=8` no .env.
    "mitos": {
        "peso": 0, "produtos": 1, "passos": 4,
        "desc": "mito x verdade alternados — muito compartilhado",
        "angulos": ["{n} mitos que você ainda acredita",
                    "Isso é verdade ou você só ouviu falar?"],
    },
}

# Rótulo da pílula de cada slide de texto, por formato
_ROTULOS = {
    "erros": "ERRO {i}",
    "passo_a_passo": "PASSO {i}",
    "mitos": "MITO {i}",
    "antes_depois": None,       # usa o rótulo que o gerador escrever
    "historia": None,
}

CTA_PADRAO = {
    "titulo": "Salva esse post pra não perder",
    "linhas": ["🛒 o link tá na bio", "💬 comenta QUERO que eu te mando"],
}


def _pesos() -> dict:
    """Pesos com override por .env (CARR_PESO_<FORMATO>)."""
    saida = {}
    for nome, cfg in FORMATOS.items():
        env = os.environ.get(f"CARR_PESO_{nome.upper()}")
        try:
            saida[nome] = int(env) if env is not None else int(cfg["peso"])
        except ValueError:
            saida[nome] = int(cfg["peso"])
    return saida


# ══════════════════════════════════════════════════════════════════════════
# ESCOLHA DO FORMATO
# ══════════════════════════════════════════════════════════════════════════
def _ledger() -> list:
    if not LEDGER.exists():
        return []
    saida = []
    for ln in LEDGER.read_text(encoding="utf-8", errors="ignore").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            saida.append(json.loads(ln))
        except Exception:
            continue
    return saida


def _quantos_por_formato(conta: str) -> dict:
    n = {f: 0 for f in FORMATOS}
    for r in _ledger():
        if conta and r.get("conta") != conta:
            continue
        f = r.get("formato")
        if f in n:
            n[f] += 1
    return n


def _salvamento_por_formato(conta: str) -> dict:
    """Salvamentos por mil de alcance, POR FORMATO, naquela conta.

    ⚠️ POOLED (Σ salvos ÷ Σ alcance), nunca a média das taxas por post. Com
    números pequenos, 1 salvamento de diferença DOBRA a taxa de um post e a
    média passa a ser dominada pelo post de menor alcance. Foi assim que a
    'fórmula campeã' de 14 posts virou nada em 215."""
    somas = {}
    for r in _ledger():
        if conta and r.get("conta") != conta:
            continue
        f, alc = r.get("formato"), int(r.get("reach") or 0)
        if f not in FORMATOS or alc <= 0:
            continue
        s = somas.setdefault(f, [0, 0])
        s[0] += int(r.get("saved") or 0)
        s[1] += alc
    return {f: (1000.0 * sv / alc) for f, (sv, alc) in somas.items() if alc}


def escolher_formato(conta: str = "", nicho: str = "") -> tuple:
    """Devolve (formato, motivo). O motivo é impresso — decisão que não se
    explica não se corrige depois."""
    pesos = {f: p for f, p in _pesos().items() if p > 0}
    if not pesos:
        return "lista", "todos os pesos zerados no .env — caindo na lista"

    feitos = _quantos_por_formato(conta)

    # FASE 1 — cobertura: quem ainda não apareceu o bastante fura a fila
    faltando = [f for f in pesos if feitos.get(f, 0) < COBERTURA]
    if faltando:
        menos = min(feitos.get(f, 0) for f in faltando)
        candidatos = [f for f in faltando if feitos.get(f, 0) == menos]
        # entre os igualmente descobertos, o peso ainda manda
        escolha = random.choices(candidatos,
                                 weights=[pesos[f] for f in candidatos])[0]
        return escolha, (f"cobertura: {conta or 'geral'} tem {menos} de "
                         f"'{escolha}' (alvo {COBERTURA}) — ainda medindo")

    # FASE 2 — inclina a distribuição pelo salvamento medido
    taxas = _salvamento_por_formato(conta)
    if not taxas:
        escolha = random.choices(list(pesos), weights=list(pesos.values()))[0]
        return escolha, "distribuição-alvo (ainda sem salvamento medido)"

    media = sum(taxas.values()) / len(taxas)
    ajustados = {}
    for f, p in pesos.items():
        t = taxas.get(f)
        # ⚠️ TETO E PISO NO AJUSTE. Sem eles, um formato com 2 posts de sorte
        # comeria a distribuição inteira e a medição pararia de existir —
        # explorar é o que impede o cérebro de se convencer cedo demais.
        fator = 1.0 if not t or media <= 0 else max(0.5, min(2.0, t / media))
        ajustados[f] = max(1, int(round(p * fator)))
    escolha = random.choices(list(ajustados), weights=list(ajustados.values()))[0]
    t = taxas.get(escolha)
    return escolha, ("salvamento medido: " + (f"{t:.1f}/mil nesta conta"
                                              if t else "sem dado deste formato"))


# ══════════════════════════════════════════════════════════════════════════
# PRODUTOS
# ══════════════════════════════════════════════════════════════════════════
def _fila_de_produtos() -> list:
    """A fila rica (com link, preço e imagem) é a do `shared/`; a da raiz é
    a lista de curadoria, só com nomes. Aceita as duas e diz qual usou."""
    for cand in (BASE_DIR / "shared" / "produtos_fila.json",
                 BASE_DIR / "produtos_fila.json"):
        if not cand.exists():
            continue
        try:
            d = json.loads(cand.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"   ⚠️  {cand.name} ilegível ({e})")
            continue
        itens = d if isinstance(d, list) else list(d.values())
        if itens:
            log.info(f"   📦 fila: {cand.relative_to(BASE_DIR)} ({len(itens)})")
            return itens
    return []


def _preco(p: dict) -> str:
    """Preço formatado, ou "" quando não há — nunca inventar número."""
    for chave in ("preco", "price", "preco_atual"):
        v = p.get(chave)
        if isinstance(v, (int, float)) and v > 0:
            return f"R$ {v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
        if isinstance(v, str) and re.search(r"\d", v):
            return v.strip()
    resumo = p.get("preco_resumo") or {}
    v = resumo.get("media") or resumo.get("atual")
    if isinstance(v, (int, float)) and v > 0:
        return f"R$ {v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return ""


def _nome(p: dict) -> str:
    for c in ("nome", "produto", "titulo", "campeao"):
        v = (p.get(c) or "").strip() if isinstance(p.get(c), str) else ""
        if v:
            return v
    return ""


def _foto_url(p: dict) -> str:
    for c in ("imagem", "image", "imageUrl", "foto"):
        v = p.get(c)
        if isinstance(v, str) and v.startswith("http"):
            return v
    return ""


def _baixar_foto(url: str, destino: Path) -> str:
    """Baixa a foto do produto. "" quando não dá.

    ⚠️ ELE DIZ POR QUE FALHOU, EM WARNING, NÃO EM DEBUG. Na 1ª rodada real 2
    de 3 produtos saíram "sem foto" e eu não conseguia dizer se era produto sem
    URL na fila ou URL que não baixou — porque este `except` engolia o motivo
    num `log.debug` que ninguém lê. É a quarta vez neste projeto que a minha
    própria ferramenta de diagnóstico esconde a evidência que ela existia pra
    mostrar. Causa diferente, remédio diferente: sem URL se resolve com a API
    de afiliado, download falhando se resolve com outra coisa."""
    if not url:
        return ""
    try:
        import requests
        r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            log.warning(f"   ⚠️  foto respondeu HTTP {r.status_code}: {url[:70]}")
            return ""
        if not r.content:
            log.warning(f"   ⚠️  foto veio vazia (0 byte): {url[:70]}")
            return ""
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(r.content)
        return str(destino)
    except Exception as e:
        log.warning(f"   ⚠️  foto não baixou ({str(e)[:60]}): {url[:70]}")
        return ""


def _resgatar_foto(produto: dict) -> str:
    """Produto sem `imagem` na fila mas COM link: pergunta à API de afiliado.

    ⚠️ REUSA `preencher_fotos._foto`, não reimplementa. Aquela função já sabe
    resolver o redirect até o itemId, usar o cache do health-check e tratar o
    `shop_id` ausente — três armadilhas já pagas. Uma segunda implementação
    aqui divergiria dela na primeira mudança da Shopee."""
    link = (produto.get("link") or "").strip()
    if not link:
        return ""
    try:
        import preencher_fotos as PF
        return PF._foto(link, item_guardado=str(produto.get("item_id") or "").strip(),
                        cache=PF._cache_ler()) or ""
    except Exception as e:
        log.warning(f"   ⚠️  resgate de foto indisponível ({str(e)[:60]})")
        return ""


def _candidatos_do_nicho(nicho: str) -> list:
    """TODOS os produtos do nicho, sem cortar em `quantos`.

    ⚠️ SEPARADO DA ESCOLHA DE PROPÓSITO. Antes eu pegava os `quantos`
    PRIMEIROS que batiam o nicho e ia embora — numa fila de 153, isso é
    escolher 5 por ordem de arquivo. Se os 5 primeiros estivessem sem foto (foi
    o que aconteceu), o carrossel saía sem foto com 148 produtos ali atrás."""
    fila = _fila_de_produtos()
    if not fila:
        return []
    try:
        from roteador_contas import nicho_do_produto
    except Exception:
        nicho_do_produto = None

    saida, vistos = [], set()
    for p in fila:
        nome = _nome(p)
        if not nome or nome.lower() in vistos:
            continue
        if nicho_do_produto and nicho:
            try:
                if nicho_do_produto(nome) != nicho:
                    continue
            except Exception:
                pass
        vistos.add(nome.lower())
        saida.append(p)
    return saida


def _produtos_do_nicho(nicho: str, quantos: int, fotos_em: Path = None,
                       exige_foto: bool = False) -> list:
    """Produtos do nicho, com nome/preço/foto local quando houver.

    ⚠️ QUEM JÁ TEM FOTO NA FILA VEM PRIMEIRO. É o conserto de maior efeito e
    custo zero do problema "2 de 3 produtos sem foto": não faltava foto no
    acervo, faltava ESCOLHER quem tem. Num formato de vitrine (lista,
    comparação) um slide sem foto é meia peça — ali o produto sem foto nem
    entra, e é melhor um carrossel de 4 com foto do que de 5 com buraco."""
    candidatos = _candidatos_do_nicho(nicho)
    if not candidatos:
        log.warning(f"   ⚠️  nenhum produto do nicho '{nicho}' na fila")
        return []

    com, sem = [], []
    for p in candidatos:
        (com if _foto_url(p) else sem).append(p)
    if sem:
        log.info(f"   📷 {len(com)} com foto na fila · {len(sem)} sem "
                 f"(rode `preencher_fotos.py` pra converter os de baixo)")
    ordenados = com + sem

    saida, i = [], 0
    for p in ordenados:
        if len(saida) >= quantos:
            break
        i += 1
        foto = ""
        if fotos_em is not None:
            url = _foto_url(p)
            if not url:
                # ⚠️ resgate SOB DEMANDA, não esperando o cron do
                # `preencher_fotos`. Uma chamada de API vale mais que um slide
                # vazio — e o resultado volta pro fluxo na mesma rodada.
                url = _resgatar_foto(p)
                if url:
                    log.info(f"   📷 foto resgatada pela API: {_nome(p)[:44]}")
            foto = _baixar_foto(url, fotos_em / f"produto_{i}.jpg")
        if exige_foto and not foto and fotos_em is not None:
            log.info(f"   ⏭️  sem foto, fora da vitrine: {_nome(p)[:44]}")
            continue
        saida.append({"nome": _nome(p), "preco": _preco(p), "foto": foto,
                      "link": p.get("link", "")})

    if len(saida) < quantos:
        log.warning(f"   ⚠️  {len(saida)} produto(s) de '{nicho}' pro carrossel "
                    f"(pedi {quantos}"
                    + (" · com foto obrigatória)" if exige_foto else ")"))
    return saida


# ══════════════════════════════════════════════════════════════════════════
# O TEXTO
# ══════════════════════════════════════════════════════════════════════════
def _cortar(frase: str, teto: int = None) -> str:
    """Garante o teto de palavras. ⚠️ CORTA NA PALAVRA, sem reticências: o
    render encolhe a fonte pra caber o que vier, calado, e um slide de 20
    palavras vira parágrafo em corpo 56 sem ninguém reclamar."""
    teto = teto or PALAVRAS_MAX
    ps = re.findall(r"\S+", frase or "")
    return " ".join(ps[:teto])


def _orcamento(titulo: str, linha: str, teto: int = None) -> tuple:
    """Ajusta título+linha pra caberem JUNTOS no teto do slide.

    ⚠️ AQUI ESTAVA O DEFEITO (visto na 1ª rodada real, 22/08): eu cortava
    CADA CAMPO em 12 palavras e o render contava o SLIDE INTEIRO. Título de 12
    + linha de 12 = 24 palavras num slide, e o aviso disparava em 3 dos 4
    slides — com o brain achando que tinha obedecido. Duas definições da mesma
    regra em dois módulos é sempre isso: uma delas está errada e as duas se
    acham certas.

    O título tem prioridade porque é o que o slide diz. A linha de apoio entra
    INTEIRA ou não entra: cortada no meio ela sai como "Preço de outro mundo e
    ainda vem" — pior que ausente, porque parece defeito de carregamento em vez
    de escolha. Título é diferente: cortar um título longo ainda deixa uma
    frase que se lê."""
    teto = teto or PALAVRAS_MAX
    tit = _cortar(titulo, teto)
    sobra = teto - len(re.findall(r"\S+", tit))
    apoio = (linha or "").strip()
    return (tit, apoio if 0 < len(re.findall(r"\S+", apoio)) <= sobra else "")


def _prompt(formato: str, nicho: str, produtos: list, angulo: str) -> str:
    cfg = FORMATOS[formato]
    nomes = "\n".join(f"- {p['nome']}" + (f" ({p['preco']})" if p["preco"] else "")
                      for p in produtos) or "- (nenhum produto informado)"
    passos = int(cfg.get("passos", 3))
    return f"""Voce escreve carrosseis para uma conta brasileira de achadinhos
da Shopee, nicho "{nicho}". Escreva em portugues do Brasil, informal, como
uma pessoa falando — NAO como anuncio.

FORMATO: {formato} — {cfg['desc']}
ANGULO DA CAPA: {angulo}

PRODUTOS DISPONIVEIS:
{nomes}

REGRAS DURAS:
1. NO MAXIMO {PALAVRAS_MAX} PALAVRAS POR SLIDE — o "titulo" e a "linha"
   SOMADOS. O ideal e 8. Slide que vira paragrafo mata o carrossel: a fonte
   encolhe pra caber e o post deixa de parecer conteudo. Se nao couber
   apoio, deixe "linha" vazia — e melhor um slide limpo.
2. Sem emoji, sem aspas, sem hashtag, sem CAIXA ALTA gritada.
3. A capa nao pode fechar porta: nada de "se voce tem X" ou "quem sofre com
   Y". Ela descreve uma situacao reconhecivel por muita gente.
4. Nao invente preco, marca, medida nem promessa de resultado.
5. Nada de "corre ver", "arrasta que eu te mostro", "voce nao vai acreditar".

RESPONDA SO COM JSON, sem cerca de codigo, neste formato exato:
{{"capa": "<a frase da capa>",
  "slides": [{{"rotulo": "<curto, ex ERRO 1 — pode ser vazio>",
               "titulo": "<a frase do slide>",
               "linha": "<uma linha de apoio, pode ser vazia>"}}],
  "cta": "<a frase do ultimo slide>",
  "legenda": "<2 a 4 linhas pra legenda do post>"}}

Gere exatamente {passos} objeto(s) em "slides"."""


def _via_gemini(formato: str, nicho: str, produtos: list, angulo: str):
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        log.warning("   ⚠️  GEMINI_API_KEY ausente — o texto sai da reserva")
        return None
    try:
        from google import genai
        cli = genai.Client(api_key=key)
        prompt = _prompt(formato, nicho, produtos, angulo)
        for tentativa in (1, 2):
            r = cli.models.generate_content(
                model=os.environ.get("CARR_MODELO", "gemini-2.5-flash"),
                contents=[{"parts": [{"text": prompt}]}])
            txt = (getattr(r, "text", "") or "").strip()
            # o modelo insiste em cercar o JSON mesmo mandando não cercar
            txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()
            try:
                d = json.loads(txt)
            except Exception:
                if tentativa == 2:
                    log.warning("   ⚠️  o modelo não devolveu JSON — usando reserva")
                    return None
                prompt += "\nATENCAO: sua resposta anterior nao era JSON valido."
                continue
            if d.get("capa") and d.get("slides"):
                return d
            if tentativa == 2:
                log.warning("   ⚠️  JSON sem capa ou sem slides — usando reserva")
                return None
            prompt += "\nATENCAO: faltou 'capa' ou 'slides' na sua resposta."
    except Exception as e:
        log.warning(f"   ⚠️  Gemini indisponível ({str(e)[:80]}) — usando reserva")
    return None


def _reserva(formato: str, nicho: str, produtos: list, angulo: str) -> dict:
    """Texto sem modelo nenhum. Não é enfeite: é o que roda quando a chave
    vence, e 22% dos Reels de julho saíram assim sem ninguém saber. Aqui a
    reserva é honesta — ela usa só o que É FATO (o nome e o preço do produto)
    e não tenta imitar um conteúdo editorial que ela não tem como escrever."""
    cfg = FORMATOS[formato]
    slides = []
    if formato in ("lista", "comparacao"):
        for p in produtos:
            slides.append({"rotulo": "", "titulo": _cortar(p["nome"]),
                           "linha": "", "preco": p["preco"], "foto": p["foto"],
                           "tipo": "produto"})
    else:
        base = produtos[0]["nome"] if produtos else nicho
        for i in range(1, int(cfg.get("passos", 3)) + 1):
            rot = (_ROTULOS.get(formato) or "{i}").format(i=i)
            slides.append({"rotulo": rot if "{" not in rot else "",
                           "titulo": _cortar(base), "linha": "",
                           "tipo": "texto"})
        if produtos and produtos[0]["preco"]:
            slides.append({"rotulo": "", "titulo": _cortar(produtos[0]["nome"]),
                           "preco": produtos[0]["preco"],
                           "foto": produtos[0]["foto"], "tipo": "produto"})
    return {"capa": angulo, "slides": slides, "cta": CTA_PADRAO["titulo"],
            "legenda": "", "reserva": True}


# ══════════════════════════════════════════════════════════════════════════
# MONTAGEM DO PLANO
# ══════════════════════════════════════════════════════════════════════════
def _handle(nicho: str) -> str:
    try:
        c = json.loads((BASE_DIR / "contas.json").read_text(encoding="utf-8"))
        return ((c.get(nicho) or c.get("_default") or {}).get("handle") or "")
    except Exception:
        return ""


def montar_plano(nicho: str, formato: str = "", fotos_em: Path = None) -> dict:
    conta = _handle(nicho)
    if formato:
        if formato not in FORMATOS:
            raise ValueError(f"formato desconhecido: {formato} "
                             f"(tenho {', '.join(FORMATOS)})")
        motivo = "forçado na linha de comando"
    else:
        formato, motivo = escolher_formato(conta, nicho)
    cfg = FORMATOS[formato]
    log.info(f"   🧠 formato '{formato}' — {motivo}")

    quantos = int(cfg.get("produtos", 1))
    # em vitrine a foto não é enfeite, é o slide: `lista` e `comparacao` só
    # aceitam produto com foto. Nos formatos de frase ela é opcional.
    vitrine = formato in ("lista", "comparacao")
    produtos = _produtos_do_nicho(nicho, quantos, fotos_em, exige_foto=vitrine)
    if vitrine and len(produtos) < 2:
        # 1 slide de produto não é lista nem comparação — e o uploader recusa
        # carrossel com menos de 2 filhos de qualquer jeito
        raise SystemExit(
            f"❌ '{formato}' precisa de ao menos 2 produtos COM FOTO do nicho "
            f"'{nicho}', e achei {len(produtos)}.\n"
            f"   Rode:  .venv/bin/python preencher_fotos.py")
    angulo = random.choice(cfg["angulos"]).format(
        n=max(quantos, int(cfg.get("passos", 3))),
        contexto=f"com {nicho}" if nicho and nicho != "geral" else "")

    d = _via_gemini(formato, nicho, produtos, angulo) or \
        _reserva(formato, nicho, produtos, angulo)

    # Une o texto do modelo com os FATOS (preço, foto, link), que nunca vêm
    # dele. O modelo escreve; a fila é quem sabe quanto custa.
    slides = []
    for i, s in enumerate(d.get("slides") or []):
        prod = produtos[i] if i < len(produtos) else None
        tit, apoio = _orcamento(s.get("titulo") or (prod["nome"] if prod else ""),
                                s.get("linha") or "")
        # ⚠️ NO FORMATO LISTA O RÓTULO É IGNORADO PELO DESENHO (`_slide_produto`
        # não tem pílula), então deixá-lo passar só enganava o print do CLI —
        # a 1ª rodada mostrou "[R$ 299,90]" e "[Bizarro!]" como se fossem sair
        # no slide. Melhor o terminal mostrar o que o feed vai mostrar.
        rotulo = "" if formato in ("lista", "comparacao") \
            else _cortar(s.get("rotulo") or "", 4)
        item = {"rotulo": rotulo, "titulo": tit, "linha": apoio}
        if s.get("tipo"):
            item["tipo"] = s["tipo"]
        if formato in ("lista", "comparacao") and prod:
            item.update(preco=s.get("preco") or prod["preco"],
                        foto=s.get("foto") or prod["foto"], tipo="produto")
        elif s.get("preco"):
            item.update(preco=s["preco"], foto=s.get("foto", ""), tipo="produto")
        else:
            item["tipo"] = item.get("tipo") or "texto"
        slides.append(item)

    cta = dict(CTA_PADRAO)
    if d.get("cta"):
        cta["titulo"] = _cortar(d["cta"])

    return {
        "nicho": nicho, "handle": conta, "formato": formato,
        "motivo_do_formato": motivo, "reserva": bool(d.get("reserva")),
        "capa": {"hook": _cortar(d.get("capa") or angulo)},
        "slides": slides, "cta": cta,
        "legenda": (d.get("legenda") or "").strip(),
        "links": [p["link"] for p in produtos if p.get("link")],
    }


def _legenda_reserva(plano: dict) -> str:
    """A legenda quando o brain não escreveu uma.

    ⚠️ TRÊS DEGRAUS, NESTA ORDEM — e o degrau do meio existe porque o Dre
    reclamou do fundo do poço, com razão: "hook + CTA" não é legenda, é o
    título repetido embaixo da foto. O projeto JÁ TEM um gerador de legenda
    rodando nos Reels (`hook_alana.gerar_legenda_curiosidade`), com banco de
    reserva por nicho — usar outra coisa aqui seria construir um segundo
    gerador pior do que o que já está no ar.

      1. a legenda que o próprio brain escreveu (conhece o carrossel inteiro)
      2. `gerar_legenda_curiosidade` — o mesmo gerador dos Reels
      3. hook + CTA — só se os dois falharem; nunca legenda vazia, que já
         custou 11 Reels da @topshopcasa_ em 15/08
    """
    if (plano.get("legenda") or "").strip():
        return plano["legenda"].strip()

    slides = plano.get("slides") or []
    produto = next((s.get("titulo") for s in slides if s.get("titulo")), "")
    hook = (plano.get("capa") or {}).get("hook", "")
    try:
        from hook_alana import gerar_legenda_curiosidade
        txt = (gerar_legenda_curiosidade(produto, hook,
                                         plano.get("nicho", "")) or "").strip()
        if txt:
            cta = (plano.get("cta") or {}).get("titulo", "")
            return "\n\n".join(x for x in (txt, cta) if x)
    except Exception as e:
        log.warning(f"   ⚠️  legenda de curiosidade indisponível ({str(e)[:60]})")

    cta = (plano.get("cta") or {}).get("titulo", "")
    return "\n\n".join(x for x in (hook, cta) if x)


def preparar_pasta(plano: dict, pasta: Path) -> None:
    """Escreve na pasta o que o uploader espera encontrar ao lado dos slides.

    ⚠️ SEM `conta.json` A PASTA POSTA NA CONTA ERRADA, E EM SILÊNCIO. O
    `meta_uploader._ativar_conta` procura esse arquivo ao lado do 1º slide; se
    não acha, ele NÃO falha — cai nas env vars globais e publica tudo no
    @topshop.__. Um carrossel de pet sairia na conta geral sem uma linha de
    log dizendo isso. É o mesmo contrato de pasta do vídeo, de propósito: um
    formato novo não é motivo pra inventar convenção nova."""
    pasta.mkdir(parents=True, exist_ok=True)
    nicho = plano.get("nicho") or "geral"
    try:
        from roteador_contas import carregar_contas, conta_para_json
        contas = carregar_contas()
        conta = dict(contas.get(nicho) or contas.get("_default") or {})
        conta.setdefault("nicho", nicho)
        (pasta / "conta.json").write_text(
            json.dumps(conta_para_json(conta), ensure_ascii=False, indent=2),
            encoding="utf-8")
    except Exception as e:
        log.error(f"   ❌ não escrevi conta.json ({e}) — NÃO poste esta pasta: "
                  "ela publicaria na conta geral")
        raise

    links = plano.get("links") or []
    (pasta / "engajamento.json").write_text(json.dumps({
        "link": links[0] if links else "",
        "handle": plano.get("handle", ""),
        "produto": (plano.get("slides") or [{}])[0].get("titulo", ""),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    arq = pasta / "legenda.txt"
    if not arq.exists() or not arq.read_text(encoding="utf-8").strip():
        arq.write_text(_legenda_reserva(plano), encoding="utf-8")


def publicar(plano: dict, pasta: Path, arquivos: list) -> dict:
    """Renderizado → publicado. Devolve o resultado do uploader."""
    preparar_pasta(plano, pasta)
    try:
        from agents.meta_uploader import postar_instagram_carrossel
    except Exception:
        from meta_uploader import postar_instagram_carrossel
    legenda = (pasta / "legenda.txt").read_text(encoding="utf-8").strip()
    r = postar_instagram_carrossel([str(a) for a in arquivos], legenda)
    registrar(plano, slug=pasta.name, url=r.get("url", "") if r.get("sucesso") else "")
    return r


def registrar(plano: dict, slug: str = "", url: str = "") -> None:
    """Anota o formato usado. ⚠️ É ISTO que faz a fase 2 existir um dia — sem
    o registro, daqui a um mês a pergunta 'qual formato segura?' não tem
    resposta, do mesmo jeito que 'qual legenda foi enviada?' não tinha."""
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": int(time.time()),
                "data": time.strftime("%Y-%m-%d"),
                "conta": plano.get("handle", ""), "nicho": plano.get("nicho", ""),
                "formato": plano.get("formato", ""),
                "reserva": bool(plano.get("reserva")),
                "hook": (plano.get("capa") or {}).get("hook", ""),
                "slides": len(plano.get("slides") or []),
                "slug": slug, "url": url,
            }, ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning(f"   ⚠️  não registrei no ledger: {e}")


# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════
def main() -> int:
    p = argparse.ArgumentParser(description="Decide o conteúdo de um carrossel")
    p.add_argument("--nicho", default="geral",
                   help="geral, beleza, tech, casa, pet ou moda")
    p.add_argument("--formato", default="", help=f"força: {', '.join(FORMATOS)}")
    p.add_argument("--render", metavar="PASTA",
                   help="além de montar, renderiza os slides nessa pasta")
    p.add_argument("--postar", action="store_true",
                   help="depois de renderizar, PUBLICA no Instagram (exige --render)")
    p.add_argument("--plano", action="store_true", help="imprime só o JSON")
    p.add_argument("--formatos", action="store_true",
                   help="mostra os formatos, pesos e o que já foi feito")
    a = p.parse_args()

    if a.formatos:
        pesos, feitos = _pesos(), _quantos_por_formato("")
        total = sum(v for v in pesos.values() if v > 0) or 1
        print(f"{'formato':<14} {'peso':>5} {'alvo':>6} {'feitos':>7}   descrição")
        print("─" * 92)
        for nome, cfg in FORMATOS.items():
            pc = f"{100 * pesos[nome] / total:.0f}%" if pesos[nome] else "—"
            print(f"{nome:<14} {pesos[nome]:>5} {pc:>6} {feitos.get(nome, 0):>7}   "
                  f"{cfg['desc'][:44]}")
        print(f"\ncobertura mínima por conta antes de otimizar: {COBERTURA}")
        return 0

    pasta = Path(a.render) if a.render else None
    plano = montar_plano(a.nicho, a.formato, pasta)

    if a.plano:
        print(json.dumps(plano, ensure_ascii=False, indent=2))
        return 0

    print(f"\n🧠 {plano['formato']}  ({plano['motivo_do_formato']})")
    if plano["reserva"]:
        print("   ⚠️  TEXTO DE RESERVA — o Gemini não respondeu")
    print(f"\n  1/{len(plano['slides']) + 2}  CAPA   {plano['capa']['hook']}")
    for i, s in enumerate(plano["slides"], start=2):
        rot = f"[{s['rotulo']}] " if s.get("rotulo") else ""
        preco = f"  ({s['preco']})" if s.get("preco") else ""
        print(f"  {i}/{len(plano['slides']) + 2}  {s.get('tipo', '?'):<8}"
              f"{rot}{s['titulo']}{preco}")
    print(f"  {len(plano['slides']) + 2}/{len(plano['slides']) + 2}  CTA    "
          f"{plano['cta']['titulo']}")
    if plano["legenda"]:
        print(f"\n  legenda: {plano['legenda'][:160]}")

    if not pasta:
        if a.postar:
            print("\n⚠️  --postar precisa de --render (o que se publica é a pasta)")
            return 1
        return 0

    import carrossel_render
    arquivos = carrossel_render.renderizar(plano, pasta)
    (pasta / "plano.json").write_text(
        json.dumps(plano, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + "\n".join(str(x) for x in arquivos))

    if not a.postar:
        # registra o que foi MONTADO mesmo sem publicar: a cobertura da fase 1
        # conta carrossel produzido, e ensaio também consome produto da fila
        preparar_pasta(plano, pasta)
        registrar(plano, slug=pasta.name)
        print(f"\nPra postar:  .venv/bin/python carrossel_brain.py --nicho "
              f"{a.nicho} --render {pasta} --postar")
        print(f"   (ou direto:  .venv/bin/python -m agents.meta_uploader "
              f"--carrossel {pasta}/*.jpg --legenda \"$(cat {pasta}/legenda.txt)\")")
        return 0

    print(f"\n📤 publicando em {plano['handle'] or '(conta do nicho)'}...")
    r = publicar(plano, pasta, arquivos)
    if r.get("sucesso"):
        print(f"✅ no ar: {r['url']}")
        return 0
    print(f"❌ não publicou: {r.get('erro')}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
