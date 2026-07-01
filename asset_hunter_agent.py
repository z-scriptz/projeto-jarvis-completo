# agents/asset_hunter_agent.py
# Asset Hunter Agent v1 do AgenteIA (Jarvis).
#
# Responsável pela "entrada de assets" do sistema. Você dropa clipes crus
# em assets/inbox/{videos,imagens,audio}/, roda o agente, e ele organiza
# pra pasta correta de cada produto + cria missões de coleta do que falta.
#
# Estrutura criada/usada:
#   assets/
#   ├── inbox/
#   │   ├── videos/      ← você dropa MP4/MOV aqui
#   │   ├── imagens/     ← thumbnails, fotos
#   │   └── audio/       ← trilhas
#   └── produtos/<slug>/{raw,imagens,audio}/   ← destino organizado
#
# Filosofia:
#   - Nunca chama Gemini, nunca abre TikTok, nunca posta
#   - mover=False por padrão (modo simulação) — sempre dry-run primeiro
#   - Nunca apaga arquivos (apenas move; sufixo _2, _3 se conflito)
#   - Nunca crasha: cada operação é try/except contida
#
# Uso direto:
#   python -m agents.asset_hunter_agent
#   python -m agents.asset_hunter_agent --produto "Mini Aspirador de Teclado"
#   python -m agents.asset_hunter_agent --produto "Mini Aspirador de Teclado" --mover
#   python -m agents.asset_hunter_agent --seed   # cria arquivos fake p/ teste

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

from shared.logger import get_logger

# Importa Asset Agent — usa as primitivas que ele já oferece
from agents.asset_agent import (
    slugificar_produto,
    criar_pasta_assets_produto,
    verificar_assets_produto,
    gerar_brief_assets_necessarios,
    EXT_VIDEO,
    EXT_IMAGEM,
    EXT_AUDIO,
    ASSETS_ROOT as PRODUTOS_ROOT,
    PLANS_DIR,
)

log = get_logger(__name__)

# =================================================================
# CONFIGURAÇÃO
# =================================================================

PROJETO_ROOT = Path(__file__).parent.parent
INBOX_ROOT   = PROJETO_ROOT / "assets" / "inbox"
INBOX_VIDEOS = INBOX_ROOT / "videos"
INBOX_IMGS   = INBOX_ROOT / "imagens"
INBOX_AUDIO  = INBOX_ROOT / "audio"

# Tamanho mínimo aceitável (abaixo disso é suspeito de placeholder/lixo)
TAMANHO_MIN_KB = 50

# Espera entre 2 leituras de tamanho pra detectar arquivo sendo gravado
INTERVALO_CHECK_ESTABILIDADE_S = 1.0

# Propósitos canônicos + suas palavras-chave (ordem importa: mais específico primeiro)
# Cada propósito tem keywords em PT e EN.
MAPA_PROPOSITOS = [
    # (proposito, [keywords PT], [keywords EN])
    ("dor",       ["dor", "problema", "antes", "sujo", "bagunca", "bagunça",
                    "ruim", "estragado", "frustracao"],
                   ["before", "problem", "issue", "dirty", "messy", "bad"]),
    ("demo",      ["demo", "demonstr", "uso", "usando", "acao", "ação",
                    "teste", "testando", "operando"],
                   ["demo", "using", "use", "test", "action", "operating", "howto"]),
    ("resultado", ["resultado", "depois", "limpo", "organizado", "perfeito",
                    "antes_depois", "transformacao"],
                   ["after", "result", "clean", "before_after", "transform"]),
    ("close",     ["close", "closeup", "produto", "detalhe", "embalagem",
                    "unboxing", "marca", "logo"],
                   ["close", "closeup", "product", "detail", "packaging", "unbox"]),
    ("cta",       ["cta", "link", "compre", "corre", "garanta", "promocao",
                    "promoção", "desconto"],
                   ["cta", "buy", "link", "click", "shop", "discount"]),
]


# =================================================================
# 1) GERAR MISSÕES DE COLETA
# =================================================================

def gerar_missoes_de_coleta(produto_nome: str, nicho: str = "") -> dict:
    """
    Gera uma "missão de coleta" pro produto: lista de cenas que precisam
    ser capturadas/baixadas, marcando quais JÁ EXISTEM no produto e quais
    AINDA FALTAM.

    Usa Asset Agent.gerar_brief_assets_necessarios pra texto + Asset
    Agent.verificar_assets_produto pra cobertura atual.

    Returns:
        {
            "sucesso": True,
            "produto": str,
            "slug": str,
            "nicho": str,
            "brief_completo": {...},      # brief original do Asset Agent
            "cenas": [
                {"id": "dor",  "ja_tem": False, "essencial": True, ...},
                {"id": "demo", "ja_tem": True,  "essencial": True, ...},
                ...
            ],
            "essenciais_faltando": ["dor", "cta"],
            "missao_completa":   False,
            "salvo_em": "..."
        }
    """
    brief = gerar_brief_assets_necessarios(produto_nome, nicho)
    status_atual = verificar_assets_produto(produto_nome)
    cobertura = status_atual.get("cobertura_cenas", {})

    cenas = []
    essenciais_faltando = []
    for c in brief["cenas"]:
        cena_id = c["id"]
        ja_tem = cobertura.get(cena_id, False)
        cenas.append({
            **c,
            "ja_tem": ja_tem,
        })
        if c.get("essencial") and not ja_tem:
            essenciais_faltando.append(cena_id)

    resultado = {
        "sucesso":             True,
        "produto":             produto_nome,
        "slug":                slugificar_produto(produto_nome),
        "nicho":               nicho,
        "brief_completo":      brief,
        "cenas":               cenas,
        "essenciais_faltando": essenciais_faltando,
        "missao_completa":     len(essenciais_faltando) == 0,
        "status_atual":        status_atual["status"],
        "score_atual":         status_atual["score_prontidao"],
        "timestamp":           time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Salva missão
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        path = PLANS_DIR / "asset_hunting_missao.json"
        path.write_text(json.dumps(resultado, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        resultado["salvo_em"] = str(path)
    except Exception as e:
        log.warning(f"Falha ao salvar missão: {e}")

    log.info(
        f"🎯 Missão pra '{produto_nome}': "
        f"{len(cenas) - len(essenciais_faltando)}/{len(cenas)} cenas OK | "
        f"essenciais faltando: {essenciais_faltando or 'nenhuma'}"
    )
    return resultado


# =================================================================
# 2) VERIFICAR INBOX
# =================================================================

def _garantir_inbox():
    """Cria as pastas da inbox se não existirem. Idempotente."""
    for d in (INBOX_VIDEOS, INBOX_IMGS, INBOX_AUDIO):
        d.mkdir(parents=True, exist_ok=True)


def _tamanho_estavel(arquivo: Path) -> bool:
    """
    True se o tamanho do arquivo não muda em INTERVALO_CHECK_ESTABILIDADE_S.
    Usado pra detectar arquivos sendo gravados/copiados em paralelo.
    """
    try:
        t1 = arquivo.stat().st_size
        time.sleep(INTERVALO_CHECK_ESTABILIDADE_S)
        t2 = arquivo.stat().st_size
        return t1 == t2
    except Exception:
        return False


def verificar_inbox_assets() -> dict:
    """
    Inspeciona assets/inbox/{videos,imagens,audio}/ sem mover nada.

    Returns:
        {
            "sucesso": True,
            "videos":  {qtd, total_bytes, aceitos, rejeitados, pequenos, instaveis, amostra},
            "imagens": {qtd, total_bytes, ...},
            "audio":   {qtd, total_bytes, ...},
            "total_arquivos": int,
            "vazia": bool,
            "timestamp": "..."
        }
    """
    _garantir_inbox()

    def _scan(pasta: Path, extensoes_validas: set) -> dict:
        bucket = {
            "qtd":           0,
            "total_bytes":   0,
            "aceitos":       [],
            "rejeitados":    [],
            "pequenos":      [],
            "instaveis":     [],
            "amostra":       [],
        }
        if not pasta.exists():
            return bucket

        for arq in sorted(pasta.iterdir()):
            if not arq.is_file():
                continue
            bucket["qtd"] += 1
            ext = arq.suffix.lower()
            try:
                tam = arq.stat().st_size
            except Exception:
                continue
            bucket["total_bytes"] += tam

            entry = {
                "nome":       arq.name,
                "tamanho_kb": round(tam / 1024, 1),
                "extensao":   ext,
                "proposito_detectado": classificar_clipe_por_nome(arq.name),
            }
            bucket["amostra"].append(entry)

            if ext not in extensoes_validas:
                bucket["rejeitados"].append(arq.name)
                continue

            if tam < TAMANHO_MIN_KB * 1024:
                bucket["pequenos"].append(arq.name)
                continue

            # Caro: só checa estabilidade dos que passaram nos filtros baratos
            if not _tamanho_estavel(arq):
                bucket["instaveis"].append(arq.name)
                continue

            bucket["aceitos"].append(arq.name)

        bucket["amostra"] = bucket["amostra"][:15]  # limita pra relatório
        return bucket

    videos  = _scan(INBOX_VIDEOS, EXT_VIDEO)
    imagens = _scan(INBOX_IMGS,   EXT_IMAGEM)
    audio   = _scan(INBOX_AUDIO,  EXT_AUDIO)

    total = videos["qtd"] + imagens["qtd"] + audio["qtd"]
    resultado = {
        "sucesso":         True,
        "videos":          videos,
        "imagens":         imagens,
        "audio":           audio,
        "total_arquivos":  total,
        "vazia":           total == 0,
        "timestamp":       time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    log.info(
        f"📥 Inbox: {total} arquivo(s) — "
        f"vídeos: {videos['qtd']} ({len(videos['aceitos'])} aceitos), "
        f"imagens: {imagens['qtd']}, audio: {audio['qtd']}"
    )
    return resultado


# =================================================================
# 3) CLASSIFICAR CLIPE POR NOME
# =================================================================

def classificar_clipe_por_nome(nome_arquivo: str) -> str:
    """
    Classifica um clipe pelo seu nome de arquivo.

    Returns:
        'dor' | 'demo' | 'resultado' | 'close' | 'cta' | 'desconhecido'

    Estratégia:
        - normaliza (lowercase, troca _ - . por espaço)
        - testa keywords em ordem do mapa
        - retorna primeiro match
        - 'desconhecido' se nada bater
    """
    if not isinstance(nome_arquivo, str):
        return "desconhecido"

    # Remove extensão + normaliza
    nome = Path(nome_arquivo).stem.lower()
    nome_norm = re.sub(r"[_\-.\s]+", " ", nome)

    for proposito, kw_pt, kw_en in MAPA_PROPOSITOS:
        for kw in kw_pt + kw_en:
            # Match por palavra inteira sempre que possível ('uso' não casa com 'usuario')
            if re.search(rf"\b{re.escape(kw)}\b", nome_norm):
                return proposito

    return "desconhecido"


# =================================================================
# 4) ORGANIZAR INBOX PARA PRODUTO
# =================================================================

def _destino_sem_conflito(pasta_destino: Path, nome_base: str) -> Path:
    """
    Retorna um Path que NÃO existe em pasta_destino. Adiciona sufixo _2, _3...
    se necessário. Nunca sobrescreve.
    """
    candidato = pasta_destino / nome_base
    if not candidato.exists():
        return candidato

    stem = Path(nome_base).stem
    suf  = Path(nome_base).suffix
    i = 2
    while True:
        candidato = pasta_destino / f"{stem}_{i}{suf}"
        if not candidato.exists():
            return candidato
        i += 1
        if i > 99:  # paranoia
            return pasta_destino / f"{stem}_{int(time.time())}{suf}"


def _prefixar_com_proposito(nome_arquivo: str, proposito: str) -> str:
    """
    Adiciona o prefixo do propósito ao nome do arquivo, se ainda não estiver lá.
    'IMG_2024.mp4' + 'demo' → 'demo_IMG_2024.mp4'
    'demo_aspirando.mp4' + 'demo' → 'demo_aspirando.mp4' (já tem)
    """
    if proposito == "desconhecido":
        return nome_arquivo
    nome_lower = nome_arquivo.lower()
    if nome_lower.startswith(proposito + "_") or nome_lower.startswith(proposito + "."):
        return nome_arquivo
    return f"{proposito}_{nome_arquivo}"


def organizar_inbox_para_produto(produto_nome: str, mover: bool = False) -> dict:
    """
    Para cada arquivo na inbox: planeja (ou executa) o move para a pasta
    do produto. Retorna o plano completo, com destinos sugeridos.

    Args:
        produto_nome: nome do produto (será slugificado)
        mover:       False = simula (dry run); True = move de verdade

    Returns:
        {
            "sucesso": True,
            "produto": str,
            "slug": str,
            "modo": "simulacao" | "real",
            "pasta_destino": str,
            "operacoes": [
                {"origem": ..., "destino": ..., "proposito": "demo",
                 "tipo": "video", "status": "planejado"|"movido"|"erro"|"skip_instavel"|"skip_pequeno"|"skip_invalido"},
                ...
            ],
            "resumo": {"planejadas": N, "movidas": N, "erros": N, "skipadas": N},
        }
    """
    # 0) Garante pastas do produto
    criacao = criar_pasta_assets_produto(produto_nome)
    if not criacao["sucesso"]:
        return {
            "sucesso":  False,
            "produto":  produto_nome,
            "modo":     "real" if mover else "simulacao",
            "mensagem": f"Não consegui criar pasta do produto: {criacao['mensagem']}",
        }

    slug = criacao["slug"]
    pasta_produto = Path(criacao["pasta"])
    _garantir_inbox()

    operacoes = []
    resumo = {"planejadas": 0, "movidas": 0, "erros": 0, "skipadas": 0}

    # Vê o que tem na inbox
    inbox_status = verificar_inbox_assets()

    # Os 3 buckets: video/imagem/audio
    plano = [
        (INBOX_VIDEOS, pasta_produto / "raw",     "video",  inbox_status["videos"]),
        (INBOX_IMGS,   pasta_produto / "imagens", "imagem", inbox_status["imagens"]),
        (INBOX_AUDIO,  pasta_produto / "audio",   "audio",  inbox_status["audio"]),
    ]

    for pasta_origem, pasta_dest, tipo, bucket_info in plano:
        if not pasta_origem.exists():
            continue

        for arq in sorted(pasta_origem.iterdir()):
            if not arq.is_file():
                continue

            op = {
                "origem":    str(arq.relative_to(PROJETO_ROOT)),
                "destino":   None,
                "proposito": classificar_clipe_por_nome(arq.name) if tipo == "video" else "n/a",
                "tipo":      tipo,
                "status":    "planejado",
                "mensagem":  "",
            }

            # Pula arquivos rejeitados, pequenos, instáveis (já detectados pela inbox)
            if arq.name in bucket_info.get("rejeitados", []):
                op["status"]   = "skip_invalido"
                op["mensagem"] = f"Extensão não aceita: {arq.suffix}"
                resumo["skipadas"] += 1
                operacoes.append(op)
                continue
            if arq.name in bucket_info.get("pequenos", []):
                op["status"]   = "skip_pequeno"
                op["mensagem"] = f"Arquivo < {TAMANHO_MIN_KB} KB — provável lixo/corrompido"
                resumo["skipadas"] += 1
                operacoes.append(op)
                continue
            if arq.name in bucket_info.get("instaveis", []):
                op["status"]   = "skip_instavel"
                op["mensagem"] = "Tamanho mudou durante check — arquivo provavelmente em uso"
                resumo["skipadas"] += 1
                operacoes.append(op)
                continue

            # Nome final no destino — vídeos ganham prefixo do propósito
            nome_final = arq.name
            if tipo == "video":
                nome_final = _prefixar_com_proposito(arq.name, op["proposito"])

            destino = _destino_sem_conflito(pasta_dest, nome_final)
            op["destino"] = str(destino.relative_to(PROJETO_ROOT))

            if mover:
                try:
                    pasta_dest.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(arq), str(destino))
                    op["status"]    = "movido"
                    resumo["movidas"] += 1
                    log.info(f"  ➡️  {tipo}: {arq.name} → {destino.name}")
                except Exception as e:
                    op["status"]    = "erro"
                    op["mensagem"]  = str(e)[:160]
                    resumo["erros"] += 1
                    log.warning(f"  ❌ Falha ao mover '{arq.name}': {e}")
            else:
                resumo["planejadas"] += 1
                log.info(f"  📋 (simulação) {tipo}: {arq.name} → {destino.name}")

            operacoes.append(op)

    return {
        "sucesso":        True,
        "produto":        produto_nome,
        "slug":           slug,
        "modo":           "real" if mover else "simulacao",
        "pasta_destino":  str(pasta_produto),
        "operacoes":      operacoes,
        "resumo":         resumo,
        "timestamp":      time.strftime("%Y-%m-%d %H:%M:%S"),
    }


# =================================================================
# 5) ATUALIZAR METADATA COM PROPÓSITOS
# =================================================================

def atualizar_metadata_com_assets(produto_nome: str) -> dict:
    """
    Lê os clipes em assets/produtos/<slug>/raw/, classifica cada um por
    nome, e grava o dicionário `propositos_clipes` no metadata.json.

    Útil pra Creative Engine consultar 'que arquivo é da cena demo' sem
    ter que reclassificar a cada execução.
    """
    slug = slugificar_produto(produto_nome)
    pasta_produto = PRODUTOS_ROOT / slug
    if not pasta_produto.exists():
        return {
            "sucesso":  False,
            "mensagem": f"Pasta do produto não existe: {pasta_produto}",
        }

    meta_path = pasta_produto / "metadata.json"
    if not meta_path.exists():
        return {
            "sucesso":  False,
            "mensagem": "metadata.json não existe — rode criar_pasta_assets_produto antes",
        }

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {
            "sucesso":  False,
            "mensagem": f"metadata.json corrompido: {e}",
        }

    raw_dir = pasta_produto / "raw"
    propositos = {}
    if raw_dir.exists():
        for arq in raw_dir.iterdir():
            if arq.is_file() and arq.suffix.lower() in EXT_VIDEO:
                propositos[arq.name] = classificar_clipe_por_nome(arq.name)

    meta["propositos_clipes"]  = propositos
    meta["atualizado_em"]      = time.strftime("%Y-%m-%d %H:%M:%S")

    try:
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        return {
            "sucesso":  False,
            "mensagem": f"Falha ao salvar metadata: {e}",
        }

    contagem = {}
    for prop in propositos.values():
        contagem[prop] = contagem.get(prop, 0) + 1

    log.info(
        f"🧠 metadata atualizada: {len(propositos)} clipe(s) "
        f"classificado(s) — {contagem}"
    )
    return {
        "sucesso":            True,
        "total_classificado": len(propositos),
        "por_proposito":      contagem,
        "propositos_clipes":  propositos,
    }


# =================================================================
# 6) EXECUTAR ASSET HUNTER (orquestrador)
# =================================================================

def executar_asset_hunter(produto_nome: str, nicho: str = "",
                          mover: bool = False) -> dict:
    """
    Pipeline completo:
        1. cria pastas do produto + inbox
        2. gera missão de coleta (o que falta)
        3. verifica inbox (o que tem)
        4. organiza inbox → produto (simulação ou real)
        5. atualiza metadata com propósitos
        6. verifica status final do produto

    Returns: relatório completo com snapshot antes/depois.
    """
    log.info("=" * 60)
    log.info(f"🎯 ASSET HUNTER — '{produto_nome}' (modo: {'REAL' if mover else 'simulação'})")
    log.info("=" * 60)
    inicio = time.time()

    # ── 0. Status inicial pra comparar depois ──
    status_inicial = verificar_assets_produto(produto_nome)
    score_inicial = status_inicial["score_prontidao"]
    status_inicial_str = status_inicial["status"]

    # ── 1. Garante estrutura ──
    _garantir_inbox()
    criacao = criar_pasta_assets_produto(produto_nome)

    # ── 2. Missão de coleta ──
    log.info(f"\n📋 Gerando missão de coleta...")
    missao = gerar_missoes_de_coleta(produto_nome, nicho)

    # ── 3. Verificar inbox ──
    log.info(f"\n📥 Verificando inbox...")
    inbox = verificar_inbox_assets()

    # ── 4. Organizar ──
    log.info(f"\n📦 {'Movendo' if mover else 'Simulando movimentação de'} arquivos...")
    org = organizar_inbox_para_produto(produto_nome, mover=mover)

    # ── 5. Atualizar metadata (só se moveu de verdade) ──
    meta_update = {"sucesso": True, "skipado": True,
                   "mensagem": "Atualização pulada — modo simulação"}
    if mover:
        log.info(f"\n🧠 Atualizando metadata.json...")
        meta_update = atualizar_metadata_com_assets(produto_nome)

    # ── 6. Status final + missão final (reflete o que está depois do move) ──
    status_final = verificar_assets_produto(produto_nome)
    score_final = status_final["score_prontidao"]
    delta_score = score_final - score_inicial

    # Regerar missão APÓS a movimentação — pra refletir o estado real
    if mover:
        log.info(f"\n📋 Regenerando missão de coleta com cobertura atualizada...")
        missao = gerar_missoes_de_coleta(produto_nome, nicho)

    duracao = round(time.time() - inicio, 2)

    relatorio = {
        "sucesso":           True,
        "produto":           produto_nome,
        "slug":              criacao["slug"],
        "nicho":             nicho,
        "modo":              "real" if mover else "simulacao",
        "duracao_segundos":  duracao,
        "status_inicial":    {"status": status_inicial_str, "score": score_inicial},
        "status_final":      {"status": status_final["status"], "score": score_final},
        "delta_score":       delta_score,
        "criacao_pasta":     criacao,
        "missao":            missao,
        "inbox":             inbox,
        "organizacao":       org,
        "metadata_update":   meta_update,
        "timestamp":         time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Salva relatório
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        path = PLANS_DIR / "asset_hunter_resultado.json"
        path.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2,
                                   default=str),
                        encoding="utf-8")
        relatorio["salvo_em"] = str(path)
        log.info(f"\n💾 Relatório salvo em: {path.relative_to(PROJETO_ROOT)}")
    except Exception as e:
        log.warning(f"Falha ao salvar relatório: {e}")

    log.info(f"\n⏱️  Concluído em {duracao}s")
    return relatorio


# =================================================================
# UTILITÁRIOS — auto-detecção + seed
# =================================================================

def adivinhar_produto_pelo_nome(nome_arquivo: str,
                                 produtos_conhecidos: list[str]) -> Optional[str]:
    """
    Tenta detectar o produto pelo nome de arquivo (substring match com slug).
    Retorna o slug que casou, ou None.
    """
    nome_norm = re.sub(r"[_\-.\s]+", "_", Path(nome_arquivo).stem.lower())
    for slug in produtos_conhecidos:
        if slug in nome_norm:
            return slug
    return None


def _listar_slugs_existentes() -> list[str]:
    if not PRODUTOS_ROOT.exists():
        return []
    return sorted([p.name for p in PRODUTOS_ROOT.iterdir() if p.is_dir()])


def seed_inbox_fake():
    """
    Cria arquivos fake na inbox pra você testar o pipeline sem ter clipes reais.
    Útil pra primeira validação no Windows.
    """
    _garantir_inbox()
    fakes = [
        (INBOX_VIDEOS, "dor_teclado_sujo.mp4",      600),
        (INBOX_VIDEOS, "demo_aspirando.mp4",        800),
        (INBOX_VIDEOS, "resultado_limpo.mp4",       500),
        (INBOX_VIDEOS, "closeup_produto.mp4",       400),
        (INBOX_VIDEOS, "cta_corre_link.mp4",        300),
        (INBOX_VIDEOS, "IMG_2024_aleatorio.mp4",    700),  # sem keyword → desconhecido
        (INBOX_VIDEOS, "lixo.mp4",                  10),    # pequeno → skip
        (INBOX_IMGS,   "foto_produto.jpg",          150),
        (INBOX_AUDIO,  "trilha_animada.mp3",        2000),
    ]
    criados = 0
    for pasta, nome, tam_kb in fakes:
        caminho = pasta / nome
        if not caminho.exists():
            caminho.write_bytes(b"\x00" * (tam_kb * 1024))
            criados += 1
    log.info(f"🌱 Seed concluído: {criados} arquivo(s) fake criado(s) na inbox/")
    return criados


# =================================================================
# RELATÓRIO IMPRESSO
# =================================================================

def imprimir_relatorio(rel: dict):
    print("\n" + "=" * 60)
    print(f"  🎯 ASSET HUNTER — Relatório")
    print("=" * 60)
    print(f"  Produto:     {rel['produto']}")
    print(f"  Slug:        {rel['slug']}")
    print(f"  Modo:        {rel['modo'].upper()}")
    print(f"  Duração:     {rel['duracao_segundos']}s")

    print(f"\n  📊 Status do produto:")
    si = rel["status_inicial"]
    sf = rel["status_final"]
    print(f"    Antes:  {si['status']} ({si['score']}/100)")
    print(f"    Depois: {sf['status']} ({sf['score']}/100)")
    delta = rel["delta_score"]
    if delta > 0:
        print(f"    Δ:      +{delta} pontos 📈")
    elif delta < 0:
        print(f"    Δ:      {delta} pontos 📉")
    else:
        print(f"    Δ:      sem alteração")

    inbox = rel["inbox"]
    print(f"\n  📥 Inbox:")
    print(f"    Total:         {inbox['total_arquivos']} arquivo(s)")
    if inbox["videos"]["qtd"]:
        v = inbox["videos"]
        print(f"    Vídeos:        {v['qtd']} | aceitos: {len(v['aceitos'])} | "
              f"rejeitados: {len(v['rejeitados'])} | pequenos: {len(v['pequenos'])} | "
              f"instáveis: {len(v['instaveis'])}")
    if inbox["imagens"]["qtd"]:
        print(f"    Imagens:       {inbox['imagens']['qtd']}")
    if inbox["audio"]["qtd"]:
        print(f"    Áudio:         {inbox['audio']['qtd']}")

    org = rel["organizacao"]
    res = org["resumo"]
    print(f"\n  📦 Operações:")
    if rel["modo"] == "real":
        print(f"    Movidas:    {res['movidas']}")
        print(f"    Erros:      {res['erros']}")
    else:
        print(f"    Planejadas: {res['planejadas']} (use --mover pra executar)")
    print(f"    Skipadas:   {res['skipadas']}")

    if org["operacoes"]:
        print(f"\n  📋 Detalhe das operações (até 10):")
        for op in org["operacoes"][:10]:
            origem = Path(op["origem"]).name
            destino = Path(op["destino"]).name if op["destino"] else "—"
            marca = {
                "movido":         "✅",
                "planejado":      "📋",
                "skip_invalido":  "⏭️",
                "skip_pequeno":   "⏭️",
                "skip_instavel":  "⏸️",
                "erro":           "❌",
            }.get(op["status"], "?")
            prop = f"[{op['proposito']}]" if op["proposito"] != "n/a" else ""
            print(f"    {marca} {origem:30s} → {destino:30s} {prop}")

    missao = rel["missao"]
    print(f"\n  🎯 Missão de coleta (nicho: {missao['brief_completo']['template_usado']}):")
    for cena in missao["cenas"]:
        marca = "✅" if cena["ja_tem"] else "❌"
        ess = "🎯" if cena["essencial"] else "  "
        print(f"    {marca} {ess} {cena['id']:10s} [{cena['duracao_alvo_seg']}s]")
    if missao["essenciais_faltando"]:
        print(f"\n    ⚠️  Cenas essenciais faltando: {missao['essenciais_faltando']}")
    elif missao["missao_completa"]:
        print(f"\n    🎉 Missão completa — todas as cenas essenciais cobertas!")

    print(f"\n  💾 Detalhes: shared/content_plans/asset_hunter_resultado.json")
    print("=" * 60)


# =================================================================
# CLI
# =================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Asset Hunter — organiza inbox → produtos + missão de coleta"
    )
    parser.add_argument("--produto", default="Mini Aspirador de Teclado",
                        help="Nome do produto alvo (padrão: 'Mini Aspirador de Teclado')")
    parser.add_argument("--nicho", default="Casa/Tech",
                        help="Nicho do produto (afeta o brief)")
    parser.add_argument("--mover", action="store_true",
                        help="Move os arquivos de verdade (default: só simula)")
    parser.add_argument("--seed", action="store_true",
                        help="Cria arquivos fake na inbox pra teste")
    args = parser.parse_args()

    if args.seed:
        seed_inbox_fake()
        print(f"✅ Inbox populada com arquivos fake. Rode novamente sem --seed pra testar.")
        return 0

    rel = executar_asset_hunter(args.produto, nicho=args.nicho, mover=args.mover)
    imprimir_relatorio(rel)

    if not rel["sucesso"]:
        return 2
    # Erro ao mover UM arquivo problemático (ex: lixo.mp4) não é falha do
    # sistema — só sinaliza se NADA foi movido E houve erro (falha real).
    resumo = rel["organizacao"]["resumo"]
    if resumo["erros"] > 0 and resumo.get("movidas", 0) == 0 and resumo.get("skipadas", 0) == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())