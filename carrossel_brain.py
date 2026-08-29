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

# ⚠️ DOIS TETOS, NÃO UM — E ISSO MUDOU COM O LAYOUT (23/08).
# O teto único de 12 palavras nasceu do desenho em PIL, onde tudo era título:
# frase grande sobre fundo liso, e 12 palavras já viravam parágrafo. O sistema
# em HTML tem HIERARQUIA: título display curto EM CIMA, corpo em cinza EMBAIXO.
# São papéis diferentes e teto igual pra ambos empobrece os dois — título de
# 12 palavras é longo demais pra manchete, e corpo de 12 é curto demais pra
# valer um salvamento. O slide de exemplo do sistema tem 8 no título e 28 no
# corpo; era esse o alvo que o brain não sabia mirar.
PALAVRAS_TITULO = int(os.environ.get("CARR_PALAVRAS_TITULO", "9"))
PALAVRAS_CORPO = int(os.environ.get("CARR_PALAVRAS_CORPO", "38"))
PALAVRAS_MAX = int(os.environ.get("CARR_PALAVRAS_MAX", "12"))   # legado (PIL)
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


# ⚠️ COMPARAR EXIGE DUAS COISAS QUE COMPETEM. O formato `comparacao` pegava os
# dois primeiros produtos do nicho e perguntava "qual faz mais sentido pra
# você?". Em 29/08 isso pôs um QUADRO DE MEMÓRIAS DO BEBÊ contra uma CAIXA
# TÉRMICA DE LAZER, com a capa prometendo "um custa o dobro, vale o
# investimento?". Os dois são de `casa` e não competem por nada: ninguém
# escolhe entre a lembrança do filho e a cerveja gelada.
#
# 📌 Formato não é template, é uma AFIRMAÇÃO sobre os produtos. `lista` afirma
# só "estes existem" e aceita qualquer par; `comparacao` afirma "estes dois
# disputam o seu dinheiro pelo mesmo fim" — e isso pode ser FALSO. Formato cuja
# premissa o código não confere é formato que publica mentira de vez em quando.
#
# A medida é a mesma que o `fundo_ia.combinar_com_forca` já usa pra casar
# imagem com assunto: palavras em comum. Aqui não se inventa métrica nova.
_PARADAS = {
    # ligação e unidade — não dizem que tipo de produto é
    "para", "pra", "com", "sem", "dos", "das", "por", "seu", "sua", "mais",
    "unidade", "unidades", "pecas", "peca", "tamanho", "cores", "modelo",
    # embalagem: "Jogo de Panelas" e "Jogo de Ferramentas" não são o mesmo
    # tipo de coisa só porque as duas são um "jogo"
    "jogo", "kit", "conjunto", "combo", "pacote",
    # adjetivo de anúncio — cola em qualquer produto da Shopee
    "novo", "nova", "original", "premium", "profissional", "portatil",
    "recarregavel", "eletrico", "eletrica", "automatico", "inteligente",
    "qualidade", "resistente", "luxo", "barato", "promocao",
}


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def _termos(nome: str) -> set:
    """As palavras que dizem QUE COISA é o produto.

    Fora: ligação, unidade, embalagem e adjetivo de anúncio (ver `_PARADAS`),
    número solto ("5L", "59") e palavra curta — "air" de "Air Fryer" some, mas
    "fryer" fica, que é o que identifica o produto."""
    import re
    palavras = re.split(r"[^0-9a-z]+", _sem_acento(nome or "").lower())
    return {p for p in palavras
            if len(p) >= 4 and not p.isdigit() and p not in _PARADAS}


def _par_comparavel(candidatos: list) -> tuple:
    """(a, b, termo) do primeiro par que compartilha um termo — ou None.

    ⚠️ VARRE OS CANDIDATOS NA ORDEM, e isso é de propósito: `_candidatos_do_nicho`
    já entrega a fila do nicho inteira, então o par escolhido continua sendo o
    mais "de cima" possível, só que agora entre os que de fato se comparam.

    ⚠️ NENHUM PAR NÃO É ERRO. Fila de nicho com produtos todos diferentes é o
    caso NORMAL — quem chama tem que ter um plano B, e o plano B é trocar de
    formato, nunca publicar a comparação mesmo assim."""
    termos = [(p, _termos(_nome(p))) for p in candidatos]
    for i, (pa, ta) in enumerate(termos):
        if not ta:
            continue
        for pb, tb in termos[i + 1:]:
            comum = ta & tb
            if comum:
                return pa, pb, sorted(comum)[0]
    return None


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
                       exige_foto: bool = False, ordem: list = None) -> list:
    """Produtos do nicho, com nome/preço/foto local quando houver.

    ⚠️ QUEM JÁ TEM FOTO NA FILA VEM PRIMEIRO. É o conserto de maior efeito e
    custo zero do problema "2 de 3 produtos sem foto": não faltava foto no
    acervo, faltava ESCOLHER quem tem. Num formato de vitrine (lista,
    comparação) um slide sem foto é meia peça — ali o produto sem foto nem
    entra, e é melhor um carrossel de 4 com foto do que de 5 com buraco."""
    # `ordem` = candidatos já escolhidos por quem chamou (hoje: o par comparável
    # do formato `comparacao`). Quando vem, ela manda — e o resto do corpo
    # continua igual, inclusive o QA de foto, que precisa poder vetar mesmo um
    # produto que alguém pediu nominalmente.
    candidatos = ordem if ordem else _candidatos_do_nicho(nicho)
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

        # ⚠️ FOTO DE CATÁLOGO COM PROPAGANDA DENTRO NÃO ENTRA. A da Shopee vem
        # com "Cor Exclusiva", selo, ícones de benefício e a marca da loja
        # cravados nos pixels — nenhum CSS conserta, e o slide vira o design do
        # vendedor dentro do nosso. Aqui a gente não tenta consertar a imagem:
        # troca de produto. A fila tem ~59 com foto, então recusar uma é barato.
        #
        # ⚠️ E SÓ RECUSA QUANDO SOBRA ALTERNATIVA. Se já estivermos no fim da
        # lista, um slide com foto poluída ainda é melhor que um carrossel com
        # menos peças do que prometeu — a trava de promessa = entrega vale mais
        # que a estética de um slide.
        if foto:
            try:
                from qa_foto import aprovada, nota
                if not aprovada(foto):
                    restam = len(ordenados) - ordenados.index(p) - 1
                    if restam > 0 and len(saida) + restam >= quantos:
                        placar, fatos = nota(foto)
                        log.info(f"   🚫 foto reprovada ({placar:+d}): "
                                 f"{_nome(p)[:40]} — troco de produto")
                        continue
                    log.info(f"   ⚠️  foto reprovada mas sem substituto: "
                             f"{_nome(p)[:40]} — mantive")
            except Exception:
                pass
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
    """Ajusta título e corpo aos tetos de CADA UM. Devolve (titulo, corpo).

    ⚠️ ELES NÃO DISPUTAM MAIS O MESMO ORÇAMENTO. Na versão anterior o corpo
    comia o que sobrasse do título, porque no PIL os dois pousavam na mesma
    faixa da imagem. No layout HTML eles moram em blocos diferentes, com
    tamanhos diferentes — o corpo caber não depende do título ser curto.
    O que sobrou da regra antiga é o corte: título longo, cortado, ainda deixa
    uma frase que se lê; corpo é cortado na frase inteira mais próxima, porque
    parágrafo cortado no meio de uma oração parece defeito de carregamento."""
    tit = _cortar(titulo, teto or PALAVRAS_TITULO)
    corpo = (linha or "").strip()
    if len(re.findall(r"\S+", corpo)) > PALAVRAS_CORPO:
        # corta na última frase completa que ainda cabe
        frases = re.split(r"(?<=[.!?])\s+", corpo)
        junto = ""
        for f in frases:
            teste = (junto + " " + f).strip()
            if len(re.findall(r"\S+", teste)) > PALAVRAS_CORPO:
                break
            junto = teste
        corpo = junto or _cortar(corpo, PALAVRAS_CORPO)
    return (tit, corpo)


def _casar_produto(slide: dict, produtos: list, i: int, usados: set):
    """O produto de que ESTE slide fala. Pelo número que o modelo devolveu.

    ⚠️ ANTES ERA `produtos[i]` — casamento por POSIÇÃO, supondo que o modelo
    escreveria os slides na mesma ordem da lista. Ele não escreve. No teste de
    24/08, no @topshoptech_:

        "Resgate sua infancia gamer agora"  → foto de um smartphone
        "Seu cinema particular onde quiser" → foto de um tubarao de controle

    Texto de um produto com foto e preço de OUTRO. É o defeito mais caro que
    este sistema pode ter, porque não parece defeito: parece anúncio
    mentiroso. Quem clica encontra outra coisa, e a conta perde a única coisa
    que ela tem, que é a confiança de quem segue.

    O `usados` existe porque índice repetido é sintoma: se o modelo mandou dois
    slides pro mesmo produto, algum produto ficou órfão e alguém vai levar a
    foto errada. Nesse caso é melhor cair no índice do que insistir num número
    que já sabemos estar errado."""
    if not produtos:
        return None
    try:
        n = int(slide.get("produto") or 0)
    except (TypeError, ValueError):
        n = 0
    if 1 <= n <= len(produtos) and n not in usados:
        usados.add(n)
        return produtos[n - 1]
    if n:
        motivo = "repetido" if n in usados else f"fora da lista de {len(produtos)}"
        log.warning(f"   ⚠️  slide {i + 1}: 'produto': {n} {motivo} "
                    f"— caindo na posição")
    return produtos[i] if i < len(produtos) else None



# ⚠️ O QUE CADA FORMATO OBRIGA NA NARRATIVA (24/08).
#
# O `desc` de cada formato é UMA LINHA, e uma linha não segura estrutura. No
# teste do dia o brain escolheu `passo_a_passo` e o Gemini devolveu quatro
# DICAS INDEPENDENTES — "entenda os sinais do bebê", "crie um cantinho
# tranquilo", "use produtos pensados pra eles". Nada ali é passo: some o
# terceiro e os outros continuam de pé.
#
# **O formato virava rótulo.** O brain registrava `passo_a_passo` no ledger, a
# métrica ia medir "desempenho de passo a passo", e o que saiu foi lista. Isso
# não é só estética: envenena a fase 2, que um dia vai decidir o que postar
# comparando formatos que nunca foram o que diziam ser.
#
# Cada roteiro abaixo diz o que CADA SLIDE tem que ser. É mais texto no prompt,
# e é o texto que faz o rótulo virar verdade.
ROTEIROS = {
    "lista": (
        "Cada slide do corpo e UM produto, com o nome dele no titulo.\n"
        "  A ordem importa: o melhor achado vai por ULTIMO, nunca no primeiro.\n"
        "  O corpo diz PRA QUE serve e POR QUE vale — nao repete o nome."
    ),
    "erros": (
        "Cada slide do corpo e UM erro que a pessoa comete SEM PERCEBER.\n"
        "  O titulo nomeia o erro (nao a solucao). O corpo explica por que\n"
        "  aquilo atrapalha, e a conclusao diz o que fazer no lugar.\n"
        "  Erro tem que ser algo que a pessoa FAZ, nao algo que ela nao tem."
    ),
    "antes_depois": (
        "SLIDE 1 do corpo: como era ANTES (o incomodo concreto, sem julgar).\n"
        "  SLIDE 2: o que mudou — a acao, nao o sentimento.\n"
        "  SLIDE 3: o DEPOIS, descrito pelo que a pessoa nota no dia a dia.\n"
        "  Nao invente medida, tempo nem porcentagem de melhora."
    ),
    "comparacao": (
        "Cada slide do corpo e UMA das opcoes, e as duas sao comparadas pelo\n"
        "  MESMO criterio (preco, espaco, durabilidade — escolha um e mantenha).\n"
        "  Nenhuma das duas e 'a ruim': cada uma ganha em uma situacao.\n"
        "  O ultimo slide diz PRA QUEM cada uma serve, nao qual e melhor."
    ),
    # ⚠️ ESTE E O UNICO ROTEIRO COM EXEMPLO, e o exemplo nasceu de duas
    # falhas seguidas em nichos diferentes (casa e tech, 24/08). So a REGRA
    # ("passo 2 depende do passo 1") melhorou a superficie — rotulo PASSO N,
    # verbo no inicio — e nao a dependencia: saiu "Comece pela protecao
    # basica / Entenda o que desgasta mais / Otimize o carregamento", que da
    # pra embaralhar sem estragar nada. Regra abstrata o modelo obedece na
    # forma; **estrutura ele copia de exemplo.**
    "passo_a_passo": (
        "⚠️ ESTE FORMATO E UMA SEQUENCIA, NAO UMA LISTA DE DICAS.\n"
        "  TESTE OBRIGATORIO antes de responder: troque a ordem de dois slides\n"
        "  do corpo. Se o texto continuar fazendo sentido, voce escreveu uma\n"
        "  LISTA — jogue fora e escreva de novo.\n"
        "\n"
        "  ASSIM NAO (cada slide e independente, da pra embaralhar):\n"
        "    PASSO 1 Comece pela protecao basica\n"
        "    PASSO 2 Entenda o que desgasta mais\n"
        "    PASSO 3 Otimize seu carregamento diario\n"
        "\n"
        "  ASSIM SIM (cada slide usa o resultado do anterior):\n"
        "    PASSO 1 Tire tudo da gaveta e ponha na cama\n"
        "    PASSO 2 Separe o que sobrou em tres montes: usa, nao usa, quebrado\n"
        "    PASSO 3 Devolve so o monte 'usa' — agora sobra espaco de verdade\n"
        "    PASSO 4 O que sobrou de espaco vira o lugar fixo do que voce usa\n"
        "\n"
        "  Repare: no exemplo bom, o PASSO 2 fala do 'que sobrou' do PASSO 1, e\n"
        "  o PASSO 3 fala do 'monte' que o PASSO 2 criou. Cada titulo CITA algo\n"
        "  que o slide anterior produziu. Faca igual.\n"
        "\n"
        "  ⚠️ E SE O ASSUNTO NAO TIVER UMA SEQUENCIA DE VERDADE, diga isso no\n"
        "  campo \"aviso\" do JSON em vez de inventar passos falsos."
    ),
    "historia": (
        "A sequencia e: problema vivido -> o que voce tentou e nao deu ->\n"
        "  o que descobriu -> como aplicou -> o que mudou.\n"
        "  Escreva em primeira pessoa, no passado. Sem moral da historia."
    ),
    "mitos": (
        "Cada slide do corpo e UMA frase que todo mundo repete, e a resposta.\n"
        "  O titulo e o mito (como as pessoas falam). O corpo diz se procede\n"
        "  e o que e verdade — sem inventar dado, numero nem estudo."
    ),
}

def _prompt(formato: str, nicho: str, produtos: list, angulo: str) -> str:
    cfg = FORMATOS[formato]
    # ⚠️ NUMERADOS, E O MODELO TEM QUE DEVOLVER O NÚMERO. Antes era uma lista
    # de traços e o casamento slide↔produto se fazia por ÍNDICE
    # (`produtos[i]`), supondo que o modelo escreveria na mesma ordem em que a
    # lista chegou. Ele não escreve. No teste de 24/08 saiu, no @topshoptech_:
    #     "Resgate sua infancia gamer"  → foto de um smartphone
    #     "Seu cinema particular"       → foto de um tubarao de controle remoto
    # Texto de um produto com foto e preço de outro. **É o pior defeito que
    # este sistema pode ter**, porque não parece defeito: parece anúncio
    # mentiroso, e quem clica encontra outra coisa. Nenhum ajuste de layout
    # conserta, e ninguém percebe olhando o log.
    nomes = "\n".join(
        f"{i}. {p['nome']}" + (f" ({p['preco']})" if p["preco"] else "")
        for i, p in enumerate(produtos, start=1)
    ) or "- (nenhum produto informado)"
    passos = int(cfg.get("passos", 3))
    return f"""Voce escreve carrosseis para uma conta brasileira de achadinhos
da Shopee, nicho "{nicho}". Escreva em portugues do Brasil, informal, como
uma pessoa falando — NAO como anuncio.

FORMATO: {formato} — {cfg['desc']}
ANGULO DA CAPA: {angulo}

COMO ESTE FORMATO TEM QUE SER ESCRITO (isto NAO e sugestao):
  {ROTEIROS.get(formato, "Um assunto por slide, do mais fraco pro mais forte.")}

PRODUTOS DISPONIVEIS:
{nomes}

REGRAS DURAS:
1. TITULO E CORPO TEM TAMANHOS DIFERENTES, e isso e a hierarquia do slide:
   · "titulo": ate {PALAVRAS_TITULO} palavras. E manchete, nao frase.
   · "linha": 2 a 3 FRASES INTEIRAS, ate {PALAVRAS_CORPO} palavras. E aqui
     que mora o valor do post — e o que faz alguem SALVAR. Slide com titulo
     e mais nada nao vale um salvamento.
   · "conclusao": ate 5 palavras, o fecho pratico do slide (ex: "Descarta
     antes de organizar"). Vira uma etiqueta verde no rodape.
2. Sem emoji, sem aspas, sem hashtag, sem CAIXA ALTA gritada.
3. ⚠️ A CAPA E O SLIDE QUE DECIDE O POST INTEIRO, e ela tem DUAS travas:

   3a. GANCHO AMPLO. A conta e de "{nicho}", nao de um sub-assunto dele. A
       capa tem que interessar a quem ainda nao sabe que precisa daquilo.
       Nada de "se voce tem X", "quem sofre com Y" — e nem de assunto que
       so serve pra um grupo pequeno.
       ERRADO: "O jeito mais facil de limpar mamadeiras"
               (fecha a conta de Casa em quem tem bebe)
       CERTO:  "4 coisas que fazem voce perder tempo na cozinha"
               (a mamadeira pode aparecer LA DENTRO, num slide)
       O especifico e permitido quando o proprio produto so serve pra
       aquele publico — mas ai o slide 2 precisa abrir de novo.

   3b. SEM DUPLO SENTIDO. Leia a capa em voz alta imaginando alguem
       passando rapido no feed, sem contexto e sem ver a foto. Se qualquer
       palavra puder ser lida com sentido sexual, violento ou ofensivo,
       TROQUE A PALAVRA — nao adiante explicar depois, porque ninguem le o
       slide 2 pra corrigir a leitura do slide 1.
       Foi o que aconteceu com "evitar o choro na mamada".
4. Nao invente preco, marca, medida nem promessa de resultado.
5. Nada de "corre ver", "arrasta que eu te mostro", "voce nao vai acreditar".

A REGRA DE OURO DA SEQUENCIA:
Cada slide responde uma pergunta que o slide anterior criou, OU cria uma
pergunta que o proximo responde. Voce nao esta escrevendo N legendas soltas —
esta escrevendo uma sequencia que faz a pessoa chegar ate o fim.

Por isso a ordem e:
  · CAPA      o gancho. Ela promete, nao entrega.
  · QUEBRA    o 2o slide NAO entrega a resposta ainda. Ele aumenta a
              tensao ("e voce provavelmente faz 2 deles todo dia"). E o
              slide que decide se a pessoa continua arrastando.
  · CORPO     {passos} slides de entrega, um assunto por slide. O MAIS FORTE
              vai por ULTIMO, nao primeiro.
  · RESUMO    a lista do que foi dito, curta, feita pra ser SALVA.
  · CTA       ⚠️ O CTA E CONSEQUENCIA DO QUE O CARROSSEL ENTREGOU, e o
              erro classico e pedir uma coisa que o post nao sustenta.
              Escolha pelo que os slides REALMENTE mostraram:
                mostrou produto com preco  -> "comenta LINK que eu te mando"
                foi resumo/checklist       -> "salva pra consultar depois"
                foi lista de erros         -> "qual desses voce fazia?"
                foram duas opcoes          -> "qual dos dois voce levaria?"
                nao mostrou produto nenhum -> pergunta sobre o assunto,
                                              NUNCA "quer o link?"
              ⚠️ Se voce nao citou nenhum produto, esta PROIBIDO de
              prometer link — "quer o link desses achadinhos?" num post que
              so deu dicas nao e CTA, e propaganda colada no fim.
              Nada de "siga para mais dicas".

A QUEBRA (slide 2) NAO E UMA SEGUNDA CAPA. Ela pertence a promessa da capa e
comeca a cumpri-la. Pode aumentar a tensao — nao pode trocar o assunto nem
anunciar uma contagem diferente.
  capa:   "Eu nao esperava essa mudanca na bancada"
  ✗ ruim: "3 erros que baguncavam sua beleza"   (promessa NOVA, outra historia)
  ✓ bom:  "Antes eu perdia 10 minutos procurando batom"   (ja e a historia)
Se a capa promete um NUMERO, a quebra nao pode citar outro.

PROMESSA = ENTREGA: o numero da capa e o numero de itens que voce vai
entregar em "slides" e em "resumo". Prometeu 5, entregue 5. Nao existe
"5 produtos" com 3 slides de produto — quem arrasta esperando cinco e recebe
tres aprende que este perfil promete mais do que cumpre.

DESTAQUE EM COR: marque com *asteriscos* a parte da CAPA que deve sair
colorida — 1 a 3 palavras, o miolo da frase, nunca a frase toda.
Ex: "5 ERROS QUE ESTAO *ACABANDO COM SUA BATERIA*"

RESPONDA SO COM JSON, sem cerca de codigo, neste formato exato:
{{"capa": "<o gancho, com *destaque* marcado>",
  "capa_sub": "<uma linha menor embaixo do gancho, pode ser vazia>",
  "quebra": {{"titulo": "<CONTINUA a promessa da capa; nao cria outra>",
             "linha": "<uma linha de apoio, pode ser vazia>"}},
  "slides": [{{"rotulo": "<curto, ex ERRO 1 — pode ser vazio>",
               "produto": <o NUMERO do produto da lista acima sobre o qual
                           este slide fala; 0 se o slide nao fala de nenhum>,
               "titulo": "<a manchete do slide, curta>",
               "linha": "<2 a 3 frases explicando de verdade>",
               "conclusao": "<ate 5 palavras, o fecho pratico>"}}],
  "resumo": ["<item 1, curtissimo>", "<item 2>", "..."],
  "cta": "<a frase do ultimo slide, contextual>",
  "legenda": "<2 a 4 linhas pra legenda do post>",
  "aviso": "<vazio; SO preencha se o FORMATO pedido nao couber no assunto.
            NAO use pra relatar que voce seguiu uma regra: 'ajustei a capa
            pra 3' nao e aviso, e obediencia. Este campo e medido.>"}}

Gere exatamente {passos} objeto(s) em "slides" e {passos} item(ns) em "resumo".

⚠️ O CAMPO "produto" E OBRIGATORIO quando o slide fala de um produto da lista.
E por ele que a foto e o preco certos entram no slide. Escrever sobre o
produto 3 e deixar "produto": 1 faz o slide sair com a foto errada."""


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
_RX_PROMETE_LINK = re.compile(
    r"\b(link|linkin|bio|manda(r)?\s+o\s+link|comenta\s+\w+\s+que\s+eu"
    r"\s+te\s+mando|quero|compra|carrinho|cupom)\b", re.I)


def _cta_do_conteudo(d: dict, slides: list, formato: str) -> dict:
    """O fecho, escolhido pelo que os slides REALMENTE mostraram.

    ⚠️ AS DUAS LINHAS DO CTA ERAM FIXAS, e isso era pior que o modelo
    desobedecer. O `CTA_PADRAO["linhas"]` — "🛒 o link tá na bio" e "💬 comenta
    QUERO que eu te mando" — ia pra TODO carrossel, inclusive os que não citam
    produto nenhum. O Gemini escrevia só o `titulo`; as linhas de baixo
    prometiam link de qualquer jeito. **Era estruturalmente impossível ter um
    fecho não-comercial**, e nenhuma regra de prompt conserta o que o código
    escreve depois.

    ⚠️ E A REGRA NOVA DE PROMPT TAMBÉM NÃO PEGOU SOZINHA: no teste de 24/08 o
    modelo devolveu "comenta LINK que eu te mando" num carrossel de 8 slides
    sem um único produto. Prompt pede; código garante. Aqui é o segundo caso —
    prometer link no que não tem link é anúncio mentiroso, e isso não pode
    depender de o modelo estar de bom humor."""
    tem_produto = any(s.get("tipo") == "produto" or s.get("preco")
                      for s in slides)
    tem_lista = any(s.get("itens") for s in slides)

    titulo = _cortar(d.get("cta") or "") or CTA_PADRAO["titulo"]
    if not tem_produto and _RX_PROMETE_LINK.search(titulo):
        # o modelo prometeu link num post que não mostrou produto — troco por
        # um fecho que o próprio conteúdo sustenta
        titulo = {
            "erros": "Qual desses você fazia?",
            "comparacao": "Qual dos dois você levaria?",
            "mitos": "Qual desses você achava verdade?",
        }.get(formato, "Salva pra não perder")
        log.info("   ↩️  CTA prometia link num post sem produto — troquei")

    if tem_produto:
        linhas = list(CTA_PADRAO["linhas"])
    elif tem_lista:
        linhas = ["Salva pra consultar na hora que precisar."]
    else:
        linhas = ["Comenta aqui embaixo — respondo todo mundo."]
    return {"titulo": titulo, "linhas": linhas}


_RX_NUM_CAPA = re.compile(r"(?<!\d)([2-9]|1\d)(?!\d)")


def _casar_promessa(hook: str, slides: list) -> str:
    """Se a capa promete um número, ele passa a ser o que o carrossel entrega.

    ⚠️ A REGRA JÁ ESTAVA NO PROMPT E O MODELO AINDA ERRAVA (26/08): a capa do
    tech dizia "5 produtos que eu queria ter conhecido antes" e o resumo
    listava 3. Corrigi a origem — o ângulo agora usa a contagem real — mas o
    modelo escreve a capa com liberdade e pode pôr outro número lá dentro.

    📌 Regra que só existe no prompt é pedido, não garantia. Esta é a terceira
    vez que anoto isso neste arquivo: o `CTA_PADRAO` prometia link em post sem
    produto e nenhuma instrução de prompt resolveu — quem resolveu foi o
    `_cta_do_conteudo` olhando o que havia sido escrito. Aqui é o mesmo.

    Conta os slides que ENTREGAM (produto ou com rótulo do tipo "ERRO 2"), não
    os de texto solto, e reescreve o número da capa se divergir. Não mexe em
    capa sem número — nem toda capa promete contagem, e inventar uma seria
    estragar um gancho bom."""
    achado = _RX_NUM_CAPA.search(hook or "")
    if not achado:
        return hook
    entregues = sum(1 for s in slides
                    if s.get("tipo") == "produto"
                    or re.search(r"\d", str(s.get("rotulo") or "")))
    if entregues < 2:
        # sem itens numeráveis não dá pra afirmar divergência: o número da capa
        # pode ser parte da frase ("2 minutos", "24 horas"), e trocar isso
        # estragaria o gancho.
        return hook
    prometido = int(achado.group(1))
    if prometido == entregues:
        return hook
    log.info(f"   🔢 a capa prometia {prometido} e o carrossel entrega "
             f"{entregues} — reescrevi o número (promessa = entrega)")
    return hook[:achado.start()] + str(entregues) + hook[achado.end():]


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

    # ⚠️ A PREMISSA DO `comparacao` É CONFERIDA ANTES, NÃO DEPOIS. Ver
    # `_par_comparavel`: comparar dois produtos que não competem pelo mesmo fim
    # publica uma pergunta sem resposta ("quadro do bebê ou caixa térmica?").
    # Quando não há par, o certo é TROCAR DE FORMATO — `lista` afirma só "estes
    # existem", que é verdade sobre qualquer par — e nunca publicar assim mesmo.
    ordem = None
    if formato == "comparacao":
        par = _par_comparavel(_candidatos_do_nicho(nicho))
        if par:
            ordem = [par[0], par[1]]
            log.info(f"   🔗 comparação legítima por '{par[2]}': "
                     f"{_nome(par[0])[:32]} × {_nome(par[1])[:32]}")
        else:
            log.info(f"   ↔️  nenhum par comparável em '{nicho}' — "
                     f"'comparacao' vira 'lista' (comparar coisas que não "
                     f"competem é pergunta sem resposta)")
            formato, cfg = "lista", FORMATOS["lista"]

    quantos = int(cfg.get("produtos", 1))
    # em vitrine a foto não é enfeite, é o slide: `lista` e `comparacao` só
    # aceitam produto com foto. Nos formatos de frase ela é opcional.
    vitrine = formato in ("lista", "comparacao")
    produtos = _produtos_do_nicho(nicho, quantos, fotos_em, exige_foto=vitrine,
                                  ordem=ordem)
    if vitrine and len(produtos) < 2:
        # 1 slide de produto não é lista nem comparação — e o uploader recusa
        # carrossel com menos de 2 filhos de qualquer jeito
        raise SystemExit(
            f"❌ '{formato}' precisa de ao menos 2 produtos COM FOTO do nicho "
            f"'{nicho}', e achei {len(produtos)}.\n"
            f"   Rode:  .venv/bin/python preencher_fotos.py")
    # ⚠️ PROMESSA TEM QUE SER A ENTREGA, e aqui ela não era (26/08).
    # `quantos` é o que o formato PEDE; `produtos` é o que a fila REALMENTE
    # tinha com foto — e podem diferir. O ângulo usava o número pedido, então a
    # capa saía "5 produtos que eu queria ter conhecido antes" num carrossel
    # que entregava 3. Medido no teste de tech: capa prometia 5, o resumo
    # listava 3.
    #
    # 📌 Isso é pior que defeito estético: quem arrasta esperando cinco e
    # recebe três aprende que o perfil promete mais do que cumpre — e esse é
    # exatamente o aprendizado que mata retenção num perfil novo.
    #
    # O número agora sai do que existe. Se a fila só deu 3, a capa diz 3.
    n_real = len(produtos) if quantos > 1 else int(cfg.get("passos", 3))
    n_real = max(2, n_real)         # "1 produto que..." não é gancho de lista
    if quantos > 1 and n_real != quantos:
        log.info(f"   🔢 pedi {quantos} produto(s), a fila deu {len(produtos)} "
                 f"— o gancho vai prometer {n_real}, não {quantos}")
    angulo = random.choice(cfg["angulos"]).format(
        n=n_real,
        contexto=f"com {nicho}" if nicho and nicho != "geral" else "")

    d = _via_gemini(formato, nicho, produtos, angulo) or \
        _reserva(formato, nicho, produtos, angulo)

    # Une o texto do modelo com os FATOS (preço, foto, link), que nunca vêm
    # dele. O modelo escreve; a fila é quem sabe quanto custa.
    slides = []
    usados = set()
    for i, s in enumerate(d.get("slides") or []):
        prod = _casar_produto(s, produtos, i, usados)
        tit, apoio = _orcamento(s.get("titulo") or (prod["nome"] if prod else ""),
                                s.get("linha") or "")
        # ⚠️ NO FORMATO LISTA O RÓTULO É IGNORADO PELO DESENHO (`_slide_produto`
        # não tem pílula), então deixá-lo passar só enganava o print do CLI —
        # a 1ª rodada mostrou "[R$ 299,90]" e "[Bizarro!]" como se fossem sair
        # no slide. Melhor o terminal mostrar o que o feed vai mostrar.
        rotulo = "" if formato in ("lista", "comparacao") \
            else _cortar(s.get("rotulo") or "", 4)
        item = {"rotulo": rotulo, "titulo": tit, "linha": apoio,
                # a etiqueta verde do rodapé — o layout sempre teve o lugar,
                # e o brain nunca preenchia: saía um slide com um vão embaixo
                "conclusao": _cortar(s.get("conclusao") or "", 5)}
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

    # ⚠️ QUEBRA E RESUMO SÃO A SEQUÊNCIA, NÃO ENFEITE (regra do Dre, 22/08):
    # "cada slide responde uma pergunta criada pelo anterior ou cria uma que o
    # próximo responde". O slide 2 é o que decide se a pessoa continua
    # arrastando — ele aumenta a tensão e NÃO entrega a resposta. O resumo é o
    # slide feito pra ser SALVO, e salvamento é o sinal que a gente está com
    # 1 a cada mil.
    q = d.get("quebra") or {}
    if q.get("titulo"):
        tit, apoio = _orcamento(q["titulo"], q.get("linha") or "")
        slides.insert(0, {"rotulo": "", "titulo": tit, "linha": apoio,
                          "tipo": "texto"})

    resumo = [_cortar(str(x), 8) for x in (d.get("resumo") or []) if str(x).strip()]
    if len(resumo) >= 2:
        slides.append({"rotulo": "SALVA ISSO", "titulo": "", "linha": "",
                       "tipo": "resumo", "itens": resumo[:7]})

    # ⚠️ CADA SLIDE GANHA UM FUNDO DIFERENTE, e o "diferente" é dentro DESTE
    # carrossel — não adianta o acervo ter 8 fotos se as 7 páginas do post
    # sortearem a mesma sala. Aqui a lista é embaralhada e consumida em ordem;
    # acabando, ela reinicia (com 3 fundos e 7 slides, cada um aparece 2-3
    # vezes, mas nunca em sequência).
    # O slide de PRODUTO fica de fora: ali a foto é o produto, e um cenário
    # atrás dele brigaria com a coisa que a pessoa precisa ver.
    # ⚠️ O `formato` FALTAVA AQUI, E ISSO ANULAVA A BIBLIOTECA INTEIRA (26/08).
    # `existentes(nicho)` sem formato lê SÓ a raiz do nicho — 10 imagens
    # genéricas. As 100 organizadas em `fundos/<nicho>/<formato>/`, que o Dre
    # passou três dias gerando exatamente pra isso, nunca eram consultadas.
    #
    # E o sintoma não parecia um bug de código: os carrosséis saíam bonitos,
    # com fundo do nicho certo. A crítica veio como julgamento estético —
    # "imagem bonita de Casa em vez de imagem que representa esta frase" — e
    # era literalmente isso: sem o formato, não há como a imagem representar a
    # frase, porque a única coisa que ligava uma à outra era a pasta.
    #
    # 📌 Trabalho que o sistema não consulta é trabalho que não existe, e ele
    # não avisa: só fica pior do que poderia, em silêncio.
    # ⚠️ E O PAPEL DO SLIDE GANHA DO FORMATO DO CARROSSEL. Um carrossel `lista`
    # tem slides que não são lista: o resumo é um checklist, o fecho é um CTA.
    # Puxar tudo de `lista/` deixa `checklist/` e `cta/` sem uso — que é
    # metade da biblioteca parada. O `slides_html` já faz isso para produto e
    # CTA (`papel="produto"`, `papel="cta"`); aqui faltava o resumo.
    def _pasta_do_slide(s):
        return "checklist" if s.get("tipo") == "resumo" else formato

    try:
        from fundo_ia import existentes, combinar
    except Exception:
        existentes = combinar = None

    if existentes:
        usados = set()
        caches = {}
        for s in slides:
            # produto e CTA são resolvidos no render, que já sabe o papel deles
            if s.get("tipo") == "produto":
                continue
            pasta = _pasta_do_slide(s)
            if pasta not in caches:
                caches[pasta] = [str(x) for x in existentes(nicho, pasta)]
                random.shuffle(caches[pasta])
            acervo = caches[pasta]
            if not acervo:
                continue

            # ⚠️ SEMÂNTICA PRIMEIRO, SORTEIO DEPOIS — e nesta ordem porque o
            # sorteio estava ANULANDO a semântica. O `_fundo()` do slides_html
            # sabe buscar pelo assunto (`combinar`), mas só chega lá quando o
            # slide NÃO tem `fundo` definido. Como aqui a gente preenchia todos,
            # a busca por assunto nunca rodava para capa, quebra e resumo: eles
            # levavam o que o embaralhamento desse. Resultado medido em 26/08 —
            # slide "Capa Luxo com Pulseira Samsung" com um projetor no fundo.
            escolha = ""
            assunto = " ".join(str(x) for x in (s.get("titulo"), s.get("linha"),
                                                s.get("rotulo")) if x)
            if combinar and assunto:
                try:
                    achado = combinar(nicho, pasta, assunto)
                    if achado and achado not in usados:
                        escolha = achado
                except Exception:
                    pass
            if not escolha:
                # ⚠️ a variedade DENTRO do carrossel continua valendo: não
                # adianta o acervo ter 10 fotos se as 7 páginas do post
                # mostrarem a mesma sala. Só que agora ela é o desempate, não
                # a regra.
                livres = [a for a in acervo if a not in usados] or acervo
                escolha = livres[0]
            usados.add(escolha)
            s["fundo"] = escolha

    # ⚠️ O `aviso` SÓ VALE SE ALGUÉM LER. Pedir ao modelo que sinalize quando
    # o formato não cabe no assunto e depois ignorar o campo é pior que não
    # pedir: cria a impressão de que existe uma trava, e não existe. Ele vai
    # pro log E pro ledger — no ledger é o que permite, meses depois, perguntar
    # "em quantos `passo_a_passo` o próprio modelo avisou que não era passo?".
    # Se esse número for alto, o formato está sendo forçado e o peso dele
    # precisa cair; sem registrar, essa pergunta não teria como ser feita.
    # ⚠️ O MODELO SE CORRIGE EM SILÊNCIO, E ISSO TAMBÉM MENTE NO LEDGER.
    # Teste de 24/08, nicho tech: pedimos `passo_a_passo`, ele percebeu que
    # "manter o celular" não tem sequência, **tirou os rótulos PASSO sozinho**
    # e escreveu "4 hábitos". O texto ficou honesto; o registro não — o ledger
    # ia gravar `passo_a_passo` num post que virou lista.
    #
    # É o mesmo envenenamento da medição de antes, só que mais difícil de ver:
    # antes o formato saía errado E rotulado errado; agora sai certo no texto e
    # errado na etiqueta. Então o ledger guarda os DOIS: o que a gente pediu e
    # o que de fato veio.
    formato_real = formato
    if formato == "passo_a_passo":
        marcados = sum(1 for s2 in slides
                       if re.search(r"passo\s*\d", str(s2.get("rotulo") or ""),
                                    re.I))
        if marcados < 2:
            formato_real = "lista"
            log.info("   🔁 pedi 'passo_a_passo' e veio sem passos — "
                     "registro como 'lista' (o texto está ok, a etiqueta é "
                     "que não podia mentir)")

    aviso = (d.get("aviso") or "").strip()
    if aviso:
        log.warning(f"   ⚠️  o modelo avisou sobre o formato '{formato}': "
                    f"{aviso[:160]}")

    cta = _cta_do_conteudo(d, slides, formato)
    hook = _casar_promessa(d.get("capa") or angulo, slides)

    return {
        "nicho": nicho, "handle": conta, "formato": formato,
        "motivo_do_formato": motivo, "reserva": bool(d.get("reserva")),
        "capa": {"hook": _cortar(hook),
                 "sub": _cortar(d.get("capa_sub") or "", 10),
                 "foto": next((p["foto"] for p in produtos if p.get("foto")), "")},
        "slides": slides, "cta": cta, "aviso": aviso,
        "formato_real": formato_real,
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

    # ⚠️ O PLANO PRECISA SOBREVIVER À RODADA. Ele existia só na memória do
    # processo: a pasta guardava conta, engajamento e legenda, e o que o
    # carrossel DIZ morria quando o comando terminava. Foi assim que o
    # `fundo_ia --do-plano` falhou no primeiro uso — eu supus um `plano.json`
    # que nunca ninguém tinha escrito. Qualquer coisa que queira reagir ao
    # conteúdo depois do render (imagem por slide, revisão, refazer um slide
    # só) precisa dele em disco.
    try:
        (pasta / "plano.json").write_text(
            json.dumps(plano, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
    except Exception as e:
        # não é motivo pra impedir a publicação: o post sai igual sem ele
        log.warning(f"   ⚠️  não escrevi plano.json ({e}) — o post sai, mas "
                    f"`fundo_ia --do-plano` não vai achar esta pasta")


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
                # o que a gente PEDIU acima; o que de fato VEIO aqui. Iguais na
                # maioria das vezes — e quando divergem, é isso que a fase 2
                # precisa ler pra não medir uma coisa achando que é outra.
                "formato_real": plano.get("formato_real")
                or plano.get("formato", ""),
                "reserva": bool(plano.get("reserva")),
                # ⚠️ o aviso do modelo entra no ledger, não só no log: é ele
                # que vai responder, daqui a alguns meses, "em quantos
                # `passo_a_passo` o próprio modelo disse que não era passo?".
                # Número alto = formato sendo forçado, e o peso dele cai.
                "aviso": (plano.get("aviso") or "")[:200],
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
