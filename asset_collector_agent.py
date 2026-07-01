# agents/asset_collector_agent.py
# Asset Collector Agent v1 do AgenteIA (Jarvis).
#
# Baixa assets de URLs DIRETAS fornecidas pelo usuário (não raspa sites
# nem TikTok de terceiros). Salva em assets/inbox/{videos,imagens,audio}/,
# de onde o Asset Hunter Agent pega e organiza por produto.
#
# Fluxo típico de uso:
#   1. Você cola URLs na aba 'Asset_Sources' da planilha
#   2. python -m agents.asset_collector_agent       (processa pendentes)
#   3. python -m agents.asset_hunter_agent --produto "X" --mover
#   4. python -m creative_engine.product_video_renderer --produto "X"
#
# Filosofia:
#   - NUNCA chama Gemini
#   - NUNCA abre TikTok
#   - NUNCA raspa sites — só URLs diretas que você forneceu
#   - NUNCA baixa sem URL clara
#   - Streaming download (não estoura memória com vídeos grandes)
#   - Limite duro: 200 MB por arquivo (configurável)
#   - Nunca sobrescreve: sufixo _2, _3 se já existir
#
# Uso direto:
#   python -m agents.asset_collector_agent                       (lê planilha)
#   python -m agents.asset_collector_agent --url "https://..."   (URL avulsa)
#   python -m agents.asset_collector_agent --dry-run             (lista sem baixar)

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, unquote

from shared.logger import get_logger

# Slugify pra prefixo de nome de arquivo
from agents.asset_agent import slugificar_produto

log = get_logger(__name__)

# =================================================================
# CONFIGURAÇÃO
# =================================================================

PROJETO_ROOT = Path(__file__).parent.parent
INBOX_ROOT   = PROJETO_ROOT / "assets" / "inbox"
INBOX_VIDEOS = INBOX_ROOT / "videos"
INBOX_IMGS   = INBOX_ROOT / "imagens"
INBOX_AUDIO  = INBOX_ROOT / "audio"
PLANS_DIR    = PROJETO_ROOT / "shared" / "content_plans"

# Aba na planilha
NOME_ABA = "Asset_Sources"

# Ordem das colunas (índice 0 = coluna A)
HEADERS = ["Data", "Produto", "Nicho", "Fonte", "URL", "Tipo",
           "Status", "Destino", "Erro"]

# Status
STATUS_PENDENTE = "Pendente"
STATUS_BAIXADO  = "Baixado"
STATUS_ERRO     = "Erro"
STATUS_IGNORADO = "Ignorado"

# Tipos
TIPO_VIDEO  = "video"
TIPO_IMAGEM = "imagem"
TIPO_AUDIO  = "audio"
TIPO_AUTO   = "auto"
TIPO_DESCONHECIDO = "desconhecido"

# Extensões reconhecidas
EXT_PARA_TIPO = {
    ".mp4":  TIPO_VIDEO,  ".mov": TIPO_VIDEO, ".webm": TIPO_VIDEO,
    ".mkv":  TIPO_VIDEO,  ".avi": TIPO_VIDEO,
    ".jpg":  TIPO_IMAGEM, ".jpeg": TIPO_IMAGEM, ".png": TIPO_IMAGEM,
    ".webp": TIPO_IMAGEM, ".gif":  TIPO_IMAGEM,
    ".mp3":  TIPO_AUDIO,  ".wav": TIPO_AUDIO, ".m4a": TIPO_AUDIO,
    ".ogg":  TIPO_AUDIO,  ".aac": TIPO_AUDIO,
}

TIPO_PARA_PASTA = {
    TIPO_VIDEO:  INBOX_VIDEOS,
    TIPO_IMAGEM: INBOX_IMGS,
    TIPO_AUDIO:  INBOX_AUDIO,
}

# Mapeamento Content-Type → tipo
CONTENT_TYPE_PARA_TIPO = [
    ("video/",      TIPO_VIDEO),
    ("image/",      TIPO_IMAGEM),
    ("audio/",      TIPO_AUDIO),
    # alguns servidores devolvem 'application/octet-stream' — não decidimos por aqui
]

# Limites
TAMANHO_MAX_MB    = 200
CHUNK_SIZE        = 8192          # 8 KB streaming
TIMEOUT_SEG       = 30
ESPERA_ENTRE_DLs  = 1.0           # rate limit suave

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 AgenteIA-Collector/1.0"
)


# =================================================================
# 1) GARANTIR ABA Asset_Sources
# =================================================================

def _headers_em_A2(ws) -> bool:
    """Confere se a linha 2 da aba contém os HEADERS esperados (case-insensitive)."""
    try:
        linha2 = ws.row_values(2)
    except Exception:
        return False
    if not linha2:
        return False
    obtidos_lower = [str(c).strip().lower() for c in linha2]
    # Aceita se contém pelo menos os 3 críticos
    return ("produto" in obtidos_lower and
            "url"     in obtidos_lower and
            "status"  in obtidos_lower)


def garantir_aba_asset_sources():
    """
    Retorna o worksheet 'Asset_Sources'.
    - Se NÃO existe: cria com TÍTULO em A1 + HEADERS em A2.
    - Se existe e headers já estão em A2: usa direto.
    - Se existe mas A2 não tem headers: escreve em A2 sem mexer em A1
      (preserva o título que o usuário pode ter posto).
    """
    try:
        from memory.sheets_engine import _aba, conectar_planilha
    except Exception as e:
        log.warning(f"Não consegui importar sheets_engine: {e}")
        return None

    # Tenta abrir aba existente
    ws = None
    try:
        ws = _aba(NOME_ABA)
    except Exception:
        ws = None

    if ws is not None:
        # Aba já existe — confere headers
        if _headers_em_A2(ws):
            log.info(f"📋 Aba '{NOME_ABA}' já existe com headers em A2 ✅")
            return ws
        # Headers faltando em A2 — escreve sem tocar em A1
        try:
            ws.update(values=[HEADERS], range_name=f"A2:{chr(64 + len(HEADERS))}2")
            log.info(f"📋 Aba '{NOME_ABA}' existia, headers gravados em A2 (A1 preservada)")
            return ws
        except Exception as e:
            log.warning(f"Falha ao gravar headers em A2: {e}")
            return ws  # devolve mesmo assim, listar_sources_pendentes tem fallback

    # Aba não existe — cria do zero
    try:
        planilha = conectar_planilha()
        ws = planilha.add_worksheet(title=NOME_ABA, rows=200, cols=max(len(HEADERS), 12))
        # Linha 1 = título; Linha 2 = headers
        ws.update(values=[["ASSET SOURCES - COLETA DE ASSETS"]],
                  range_name="A1")
        ws.update(values=[HEADERS],
                  range_name=f"A2:{chr(64 + len(HEADERS))}2")
        log.info(f"📋 Aba '{NOME_ABA}' CRIADA: título em A1, {len(HEADERS)} headers em A2")
        return ws
    except Exception as e:
        log.warning(f"Falha ao criar aba '{NOME_ABA}': {e}")
        return None


# =================================================================
# 2) LISTAR SOURCES PENDENTES
# =================================================================

def _detectar_linha_header(todas: list[list[str]]) -> tuple[list[str], int]:
    """
    Encontra dinamicamente em qual linha estão os headers.

    Resolve o caso comum no projeto: a aba tem TÍTULO na linha 1
    ('ASSET SOURCES - COLETA DE ASSETS' ou similar) e os HEADERS de
    verdade ('Data | Produto | Nicho | ...') na linha 2 ou 3.
    Igual a Fila_de_Postagem faz.

    Args:
        todas: ws.get_all_values() — lista de listas, uma por linha.

    Returns:
        (headers_normalizados, start_idx)

        - headers_normalizados: linha dos headers já com strip() (lista de str)
        - start_idx: ÍNDICE ZERO-BASED da PRIMEIRA LINHA DE DADOS em `todas`.
                     Use como: `for row in todas[start_idx:]:`
                     Pra converter pra número humano da linha:
                     `numero_linha = start_idx + i + 1` onde i é o offset no slice.

    Fallback: se não achar nenhuma linha com 'produto'+'url'+'status',
    retorna (HEADERS, 1) — assume linha 1 = título, dados a partir de 2.
    """
    for idx, row in enumerate(todas):
        normalized = [str(h).strip() for h in row]
        normalized_lower = [h.lower() for h in normalized]
        if ("produto" in normalized_lower and
            "url"     in normalized_lower and
            "status"  in normalized_lower):
            return normalized, idx + 1
    return HEADERS, 1


def listar_sources_pendentes() -> list[dict]:
    """
    Lê a aba e retorna linhas com Status vazio ou Pendente.

    Não usa get_all_records (que assume linha 1 = headers).
    Usa get_all_values + detector dinâmico de header, pra suportar
    aba com título na linha 1 e headers na linha 2.

    Cada item retornado tem campo 'linha' = NÚMERO HUMANO 1-based da
    planilha, pronto pra usar em ws.update_cell(linha, col, valor).
    """
    ws = garantir_aba_asset_sources()
    if ws is None:
        log.warning("Aba indisponível — retornando lista vazia")
        return []

    try:
        todas = ws.get_all_values()
    except Exception as e:
        log.warning(f"Falha ao ler valores da aba: {e}")
        return []

    if len(todas) < 2:
        log.info("📋 Aba praticamente vazia — sem dados pra processar")
        return []

    headers, start_idx = _detectar_linha_header(todas)
    headers_lower = [h.strip().lower() for h in headers]

    log.info(
        f"📋 Headers detectados em linha {start_idx} (zero-based={start_idx - 1}) "
        f"→ primeira linha de dados na linha {start_idx + 1} da planilha"
    )

    pendentes = []
    # enumerate com start=start_idx+1 faz `i` virar NÚMERO HUMANO da linha:
    #   start_idx=2 (zero-based da 1ª linha de dados) → start=3 → primeira linha humana = 3 ✅
    for i, row in enumerate(todas[start_idx:], start=start_idx + 1):
        # Garante que row tem o mesmo número de colunas que headers (preenche vazio)
        while len(row) < len(headers_lower):
            row.append("")

        dados = {
            headers_lower[j]: (row[j].strip() if isinstance(row[j], str) else str(row[j]))
            for j in range(len(headers_lower))
        }

        url = dados.get("url", "").strip()
        status = dados.get("status", "").strip()

        if not url:
            continue
        if status and status.lower() != STATUS_PENDENTE.lower():
            continue

        pendentes.append({
            "linha":   i,  # número humano (1-based) da linha na planilha
            "data":    dados.get("data", ""),
            "produto": dados.get("produto", ""),
            "nicho":   dados.get("nicho", ""),
            "fonte":   dados.get("fonte", ""),
            "url":     url,
            "tipo":    (dados.get("tipo") or TIPO_AUTO).strip().lower() or TIPO_AUTO,
            "status":  status,
        })

    log.info(f"📥 {len(pendentes)} source(s) pendente(s) na planilha")
    return pendentes


# =================================================================
# 3) DETECTAR TIPO POR URL
# =================================================================

def detectar_tipo_por_url(url: str, tipo_hint: str = TIPO_AUTO) -> str:
    """
    Tenta inferir tipo do asset:
        1. Se tipo_hint é explícito (video/imagem/audio), respeita
        2. Senão, olha extensão da URL
        3. Senão, retorna 'desconhecido'
    """
    tipo_hint_norm = (tipo_hint or "").strip().lower()
    if tipo_hint_norm in (TIPO_VIDEO, TIPO_IMAGEM, TIPO_AUDIO):
        return tipo_hint_norm

    try:
        path = urlparse(url).path.lower()
        # Remove query do path se houver na extensão
        for ext, tipo in EXT_PARA_TIPO.items():
            if path.endswith(ext):
                return tipo
    except Exception:
        pass

    return TIPO_DESCONHECIDO


def _tipo_por_content_type(content_type: str) -> Optional[str]:
    if not content_type:
        return None
    ct = content_type.lower().split(";")[0].strip()
    for prefixo, tipo in CONTENT_TYPE_PARA_TIPO:
        if ct.startswith(prefixo):
            return tipo
    return None


# =================================================================
# UTILS: nome de arquivo seguro + sem conflito
# =================================================================

def _nome_arquivo_da_url(url: str, tipo: str, produto: str = "") -> str:
    """
    Extrai um nome de arquivo razoável da URL.
    Sanitiza: tira query string, caracteres especiais.
    Prefixa com slug do produto se informado.
    """
    try:
        path = urlparse(url).path
        nome_bruto = unquote(Path(path).name) or "asset"
    except Exception:
        nome_bruto = "asset"

    # Remove query strings residuais e caracteres problemáticos
    nome_bruto = nome_bruto.split("?")[0].split("#")[0]
    nome_bruto = re.sub(r"[^\w\-.]", "_", nome_bruto)
    nome_bruto = re.sub(r"_+", "_", nome_bruto).strip("_") or "asset"

    # Garante extensão coerente com o tipo
    p = Path(nome_bruto)
    if p.suffix.lower() not in EXT_PARA_TIPO or EXT_PARA_TIPO.get(p.suffix.lower()) != tipo:
        # Adiciona extensão padrão baseada no tipo
        ext_padrao = {TIPO_VIDEO: ".mp4", TIPO_IMAGEM: ".jpg", TIPO_AUDIO: ".mp3"}.get(tipo, "")
        if ext_padrao:
            nome_bruto = p.stem + ext_padrao

    # Prefixo com slug do produto (ajuda Asset Hunter a auto-detectar depois)
    if produto:
        slug = slugificar_produto(produto)
        # Evita prefixo duplicado
        if not nome_bruto.lower().startswith(slug.lower()):
            nome_bruto = f"{slug}_{nome_bruto}"

    return nome_bruto


def _destino_sem_conflito(pasta: Path, nome: str) -> Path:
    """Sufixo _2, _3 se já existir. Nunca sobrescreve."""
    candidato = pasta / nome
    if not candidato.exists():
        return candidato
    stem, suf = Path(nome).stem, Path(nome).suffix
    i = 2
    while True:
        candidato = pasta / f"{stem}_{i}{suf}"
        if not candidato.exists():
            return candidato
        i += 1
        if i > 99:
            return pasta / f"{stem}_{int(time.time())}{suf}"


def _resumir_url(url: str, max_chars: int = 60) -> str:
    """Mostra só domínio + final pra log limpo."""
    try:
        p = urlparse(url)
        host = p.netloc
        tail = Path(p.path).name or "/"
        s = f"{host}/.../{tail}"
        if len(s) > max_chars:
            s = s[:max_chars - 3] + "..."
        return s
    except Exception:
        return url[:max_chars]


# =================================================================
# 4) BAIXAR ASSET
# =================================================================

def baixar_asset(url: str, tipo: str = TIPO_AUTO, produto: str = "") -> dict:
    """
    Baixa um único asset via HTTP streaming.

    Returns:
        {
            "sucesso": bool,
            "url": str,
            "tipo": str,
            "destino": str | None,
            "tamanho_bytes": int,
            "mensagem": str,
            "erro": str | None,
        }
    """
    base = {
        "url":           url,
        "tipo":          tipo,
        "destino":       None,
        "tamanho_bytes": 0,
        "mensagem":      "",
        "erro":          None,
    }

    # Valida URL básica
    if not url or not isinstance(url, str):
        return {**base, "sucesso": False, "erro": "URL vazia"}
    if not (url.startswith("http://") or url.startswith("https://")):
        return {**base, "sucesso": False, "erro": "URL precisa começar com http:// ou https://"}

    # Detecta tipo se necessário
    tipo_detectado = detectar_tipo_por_url(url, tipo_hint=tipo)
    if tipo_detectado == TIPO_DESCONHECIDO:
        # Última tentativa: vai pra HEAD e olha Content-Type
        log.info(f"   Tipo não detectado por extensão — tentando HEAD na URL...")
        tipo_detectado = _tentar_tipo_via_head(url) or TIPO_DESCONHECIDO

    if tipo_detectado == TIPO_DESCONHECIDO:
        return {**base, "sucesso": False,
                "erro": "Não consegui determinar tipo (video/imagem/audio) — informe Tipo na planilha"}

    base["tipo"] = tipo_detectado
    pasta = TIPO_PARA_PASTA[tipo_detectado]
    pasta.mkdir(parents=True, exist_ok=True)

    # Tenta importar requests
    try:
        import requests
    except ImportError:
        return {**base, "sucesso": False,
                "erro": "requests não instalado — pip install requests"}

    nome = _nome_arquivo_da_url(url, tipo_detectado, produto=produto)
    destino = _destino_sem_conflito(pasta, nome)

    log.info(f"   ⬇️  Baixando: {_resumir_url(url)}")
    log.info(f"      → {destino.relative_to(PROJETO_ROOT)}")

    headers = {"User-Agent": USER_AGENT}
    try:
        with requests.get(url, stream=True, timeout=TIMEOUT_SEG, headers=headers) as r:
            r.raise_for_status()

            # Validação prévia: Content-Type bate com tipo?
            ct = r.headers.get("Content-Type", "")
            tipo_por_ct = _tipo_por_content_type(ct)
            if tipo_por_ct and tipo_por_ct != tipo_detectado:
                return {**base, "sucesso": False,
                        "erro": f"Content-Type '{ct}' não bate com tipo '{tipo_detectado}'"}

            # Tamanho declarado (se disponível)
            content_length = r.headers.get("Content-Length")
            if content_length:
                try:
                    declarado_mb = int(content_length) / 1024 / 1024
                    if declarado_mb > TAMANHO_MAX_MB:
                        return {**base, "sucesso": False,
                                "erro": f"Arquivo declara {declarado_mb:.1f} MB > limite {TAMANHO_MAX_MB} MB"}
                except ValueError:
                    pass

            # Stream do conteúdo
            baixado = 0
            with open(destino, "wb") as f:
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                    if not chunk:
                        continue
                    f.write(chunk)
                    baixado += len(chunk)
                    # Aborta se passou do limite (mesmo sem Content-Length)
                    if baixado > TAMANHO_MAX_MB * 1024 * 1024:
                        f.close()
                        destino.unlink(missing_ok=True)
                        return {**base, "sucesso": False,
                                "erro": f"Excedeu {TAMANHO_MAX_MB} MB durante download (abortado)"}

        base["tamanho_bytes"] = baixado
        base["destino"]       = str(destino)
        base["mensagem"]      = f"Baixado {baixado/1024/1024:.2f} MB"
        log.info(f"   ✅ {base['mensagem']}")
        return {**base, "sucesso": True}

    except Exception as e:
        # Limpa arquivo parcial se existir
        try:
            destino.unlink(missing_ok=True)
        except Exception:
            pass
        return {**base, "sucesso": False, "erro": f"{type(e).__name__}: {str(e)[:140]}"}


def _tentar_tipo_via_head(url: str) -> Optional[str]:
    """HEAD request rápido só pra inferir Content-Type. Falha silenciosa."""
    try:
        import requests
        r = requests.head(url, timeout=10,
                          headers={"User-Agent": USER_AGENT},
                          allow_redirects=True)
        return _tipo_por_content_type(r.headers.get("Content-Type", ""))
    except Exception:
        return None


# =================================================================
# 5) PROCESSAR ASSET SOURCES (planilha)
# =================================================================

def processar_asset_sources(limite: int = 10, dry_run: bool = False) -> dict:
    """
    Lê pendentes da planilha, baixa cada um, atualiza a linha com
    Status / Destino / Erro.

    Args:
        limite:  máximo de linhas a processar nesta rodada
        dry_run: se True, só lista o que faria, não baixa nem atualiza planilha
    """
    log.info("=" * 60)
    log.info(f"📦 ASSET COLLECTOR — Processando planilha")
    log.info(f"   modo: {'DRY-RUN' if dry_run else 'REAL'} | limite: {limite}")
    log.info("=" * 60)

    ws = garantir_aba_asset_sources()
    if ws is None and not dry_run:
        return {
            "sucesso":     False,
            "mensagem":    "Aba Asset_Sources indisponível e modo não é dry-run",
            "processados": 0, "baixados": 0, "erros": 0,
            "destinos":    [],
        }

    pendentes = listar_sources_pendentes()
    if not pendentes:
        log.info("✅ Sem pendentes pra processar")
        return {
            "sucesso":     True,
            "processados": 0, "baixados": 0, "erros": 0,
            "destinos":    [],
            "mensagem":    "Sem sources pendentes",
        }

    a_processar = pendentes[:limite]
    log.info(f"\n📋 {len(a_processar)} source(s) a processar (limite={limite})\n")

    resultados = []
    baixados = erros = 0
    destinos = []

    for i, src in enumerate(a_processar, 1):
        log.info(f"\n── [{i}/{len(a_processar)}] linha {src['linha']}: {src['produto'] or '(sem produto)'}")

        if dry_run:
            tipo = detectar_tipo_por_url(src["url"], tipo_hint=src["tipo"])
            log.info(f"   (dry-run) tipo={tipo}, url={_resumir_url(src['url'])}")
            resultados.append({**src, "tipo_detectado": tipo, "acao": "skipado_dry_run"})
            continue

        r = baixar_asset(src["url"], tipo=src["tipo"], produto=src["produto"])
        resultados.append({**src, "resultado": r})

        # Atualiza planilha
        try:
            agora = time.strftime("%Y-%m-%d %H:%M:%S")
            if r["sucesso"]:
                novo_status = STATUS_BAIXADO
                destino_str = r["destino"] or ""
                erro_str = ""
                baixados += 1
                destinos.append(destino_str)
            else:
                novo_status = STATUS_ERRO
                destino_str = ""
                erro_str = r["erro"] or "erro desconhecido"
                erros += 1

            # Atualiza colunas G (Status), H (Destino), I (Erro), A (Data se vazia)
            linha = src["linha"]
            ws.update_cell(linha, HEADERS.index("Status")  + 1, novo_status)
            ws.update_cell(linha, HEADERS.index("Destino") + 1, destino_str)
            ws.update_cell(linha, HEADERS.index("Erro")    + 1, erro_str)
            if not src["data"]:
                ws.update_cell(linha, HEADERS.index("Data") + 1, agora)
        except Exception as e:
            log.warning(f"   ⚠️  Falha ao atualizar planilha linha {src['linha']}: {e}")

        # Rate limit suave
        if i < len(a_processar):
            time.sleep(ESPERA_ENTRE_DLs)

    log.info(f"\n📊 Total: {len(a_processar)} processado(s) | "
             f"baixado(s): {baixados} | erro(s): {erros}")

    return {
        "sucesso":     True,
        "processados": len(a_processar),
        "baixados":    baixados,
        "erros":       erros,
        "destinos":    destinos,
        "resultados":  resultados,
        "modo":        "dry_run" if dry_run else "real",
        "timestamp":   time.strftime("%Y-%m-%d %H:%M:%S"),
    }


# =================================================================
# RELATÓRIO IMPRESSO + SAVE
# =================================================================

def salvar_resultado(resultado: dict) -> Optional[str]:
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        path = PLANS_DIR / "asset_collector_resultado.json"
        path.write_text(json.dumps(resultado, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8")
        return str(path)
    except Exception as e:
        log.warning(f"Falha ao salvar resultado: {e}")
        return None


def imprimir_relatorio(r: dict):
    print("\n" + "=" * 60)
    print(f"  📦 ASSET COLLECTOR — Relatório")
    print("=" * 60)
    print(f"  Modo:         {r.get('modo', '?')}")
    print(f"  Processadas:  {r.get('processados', 0)}")
    print(f"  Baixadas:     {r.get('baixados', 0)}")
    print(f"  Erros:        {r.get('erros', 0)}")

    destinos = r.get("destinos") or []
    if destinos:
        print(f"\n  💾 Destinos:")
        for d in destinos[:15]:
            print(f"     • {d}")

    resultados = r.get("resultados") or []
    if resultados:
        # Mostra erros se houve algum
        com_erro = [x for x in resultados if x.get("resultado", {}).get("erro")]
        if com_erro:
            print(f"\n  ⚠️  Erros detalhados:")
            for x in com_erro[:10]:
                url = _resumir_url(x.get("url", ""))
                err = x.get("resultado", {}).get("erro", "?")
                print(f"     • {url} → {err}")

    print(f"\n  💾 Detalhes em: shared/content_plans/asset_collector_resultado.json")
    print("=" * 60)


# =================================================================
# CLI
# =================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Asset Collector — baixa URLs diretas pra assets/inbox/"
    )
    parser.add_argument("--url", default="",
                        help="Baixa UMA URL avulsa (não usa planilha)")
    parser.add_argument("--produto", default="",
                        help="Produto associado (usado pra prefixar nome do arquivo)")
    parser.add_argument("--tipo", default=TIPO_AUTO,
                        choices=[TIPO_AUTO, TIPO_VIDEO, TIPO_IMAGEM, TIPO_AUDIO],
                        help="Tipo do asset (default: auto-detecta)")
    parser.add_argument("--limite", type=int, default=10,
                        help="Máximo de linhas da planilha a processar (default: 10)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Lista o que baixaria sem realmente baixar")
    args = parser.parse_args()

    # Modo URL direta — não usa planilha
    if args.url:
        log.info("=" * 60)
        log.info(f"📦 ASSET COLLECTOR — Modo URL direta")
        log.info(f"   url: {_resumir_url(args.url)}")
        log.info(f"   produto: {args.produto or '(sem produto)'}")
        log.info(f"   tipo: {args.tipo}")
        log.info("=" * 60)

        if args.dry_run:
            tipo = detectar_tipo_por_url(args.url, tipo_hint=args.tipo)
            print(f"\n  (dry-run) Tipo detectado: {tipo}")
            print(f"  (dry-run) Não baixou — passe sem --dry-run pra baixar de verdade")
            return 0

        r = baixar_asset(args.url, tipo=args.tipo, produto=args.produto)
        resultado = {
            "sucesso":     r["sucesso"],
            "processados": 1,
            "baixados":    1 if r["sucesso"] else 0,
            "erros":       0 if r["sucesso"] else 1,
            "destinos":    [r["destino"]] if r["destino"] else [],
            "resultados":  [{"url": args.url, "produto": args.produto, "resultado": r}],
            "modo":        "url_direta",
            "timestamp":   time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        salvar_resultado(resultado)
        imprimir_relatorio(resultado)
        return 0 if r["sucesso"] else 2

    # Modo planilha
    resultado = processar_asset_sources(limite=args.limite, dry_run=args.dry_run)
    salvar_resultado(resultado)
    imprimir_relatorio(resultado)

    if not resultado.get("sucesso"):
        return 2
    if resultado.get("erros", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())