# agents/health_check_agent.py
# Health Check Agent v1 do AgenteIA (Jarvis).
#
# Diagnostica se o Jarvis está pronto pra rodar o autonomous_orchestrator
# SEM gastar Gemini, sem abrir TikTok, sem postar nada.
#
# Faz 8 checagens em camadas, cada uma reportando bloqueadores e warnings.
# Salva relatório em shared/content_plans/health_check_resultado.json e
# imprime resumo legível no terminal.
#
# Filosofia:
#   - NUNCA crasha: qualquer falha vira warning/bloqueador no relatório
#   - timeouts curtos pra não travar
#   - cada check é independente — se um falha, os outros continuam
#
# Uso:
#   python -m agents.health_check_agent

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

from shared.logger import get_logger

log = get_logger(__name__)

PROJETO_ROOT = Path(__file__).parent.parent
PLANS_DIR    = PROJETO_ROOT / "shared" / "content_plans"
VIDEOS_DIR   = PROJETO_ROOT / "videos"
CACHE_FILE   = PROJETO_ROOT / "refs" / "interface_cache.json"

# Pontos descontados por severidade
PONTOS_POR_BLOQUEADOR = 25
PONTOS_POR_WARNING    = 5

# Faixas de classificação
CLASSIFICACAO = [
    (90, "✅ Pronto para teste real"),
    (70, "🟡 Quase pronto, revisar warnings"),
    (50, "🟠 Atenção, ajustar antes de rodar"),
    (0,  "🔴 Não rodar orquestrador ainda"),
]


# =================================================================
# HELPERS DE COLETA
# =================================================================

class Coletor:
    """Acumula bloqueadores, warnings e dados de cada check."""

    def __init__(self):
        self.bloqueadores: list[str] = []
        self.warnings:     list[str] = []
        self.checks:       dict      = {}

    def bloquear(self, mensagem: str):
        self.bloqueadores.append(mensagem)
        log.error(f"  🛑 BLOQUEADOR: {mensagem}")

    def avisar(self, mensagem: str):
        self.warnings.append(mensagem)
        log.warning(f"  ⚠️  WARNING: {mensagem}")

    def registrar(self, nome_check: str, dados: dict):
        self.checks[nome_check] = dados

    def score(self) -> int:
        bruto = 100 - len(self.bloqueadores) * PONTOS_POR_BLOQUEADOR \
                    - len(self.warnings)     * PONTOS_POR_WARNING
        return max(0, min(100, bruto))


# =================================================================
# CHECK 1 — Estrutura de arquivos
# =================================================================

ARQUIVOS_OBRIGATORIOS = [
    # (caminho relativo ao projeto, é_bloqueador_se_faltar)
    ("agents/autonomous_orchestrator.py",            True),
    ("agents/performance_agent.py",                  True),
    ("brain/file_dialog_uploader.py",                True),
    ("brain/vision_analyzer.py",                     True),
    ("brain/interface_cache.py",                     True),
    ("creative_engine/local_video_renderer.py",      True),
    ("workflows/preparar_post_tiktok_completo.json", True),
    ("workflows/upload_completo_tiktok.json",        True),
    ("workflows/publicar_tiktok_seguro.json",        True),
    # Esses 2 podem não existir antes da 1ª execução do pipeline — só warning
    ("shared/content_plans/ultimo_plano.json",        False),
    ("shared/content_plans/produto_selecionado.json", False),
]


def check_arquivos(col: Coletor):
    log.info("\n📁 Check 1 — Estrutura de arquivos")
    presentes, ausentes = [], []
    for rel_path, eh_critico in ARQUIVOS_OBRIGATORIOS:
        caminho = PROJETO_ROOT / rel_path
        if caminho.exists():
            presentes.append(rel_path)
        else:
            ausentes.append(rel_path)
            if eh_critico:
                col.bloquear(f"Arquivo crítico ausente: {rel_path}")
            else:
                col.avisar(f"Arquivo opcional ausente: {rel_path} (pode ser 1ª execução)")

    log.info(f"  ✓ {len(presentes)}/{len(ARQUIVOS_OBRIGATORIOS)} arquivos presentes")
    col.registrar("arquivos", {
        "presentes_qtd": len(presentes),
        "total":         len(ARQUIVOS_OBRIGATORIOS),
        "ausentes":      ausentes,
    })


# =================================================================
# CHECK 2 — Dependências Python
# =================================================================

DEPENDENCIAS = [
    # (nome import, nome pip, é_bloqueador_se_faltar)
    ("moviepy",      "moviepy",      True),
    ("PIL",          "Pillow",       True),
    ("pyperclip",    "pyperclip",    True),
    ("pygetwindow",  "pygetwindow",  True),
    ("gspread",      "gspread",      True),
]


def check_dependencias(col: Coletor):
    log.info("\n📦 Check 2 — Dependências Python")
    instaladas, faltando = [], []
    for nome_import, nome_pip, eh_critico in DEPENDENCIAS:
        try:
            __import__(nome_import)
            instaladas.append(nome_import)
        except ImportError:
            faltando.append(nome_pip)
            msg = f"Dependência não instalada: {nome_pip} (pip install {nome_pip})"
            if eh_critico:
                col.bloquear(msg)
            else:
                col.avisar(msg)

    log.info(f"  ✓ {len(instaladas)}/{len(DEPENDENCIAS)} dependências OK")
    col.registrar("dependencias", {
        "instaladas_qtd": len(instaladas),
        "total":          len(DEPENDENCIAS),
        "faltando":       faltando,
    })


# =================================================================
# CHECK 3 — Executor Windows (handlers)
# =================================================================

def check_executor(col: Coletor):
    log.info("\n🤖 Check 3 — Executor Windows")
    try:
        from brain.commander import enviar_comando
    except Exception as e:
        col.avisar(f"Não consegui importar brain.commander: {e}")
        col.registrar("executor", {"erro_import": str(e)})
        return

    resultados = {}

    # Teste 1: janela_ativa
    try:
        r = enviar_comando("janela_ativa")
        sucesso = r.get("sucesso", False)
        titulo  = (r.get("dados", {}) or {}).get("titulo", "")
        resultados["janela_ativa"] = {"sucesso": sucesso, "titulo": titulo}
        if sucesso:
            log.info(f"  ✓ janela_ativa OK (título: '{titulo}')")
        else:
            col.avisar(f"janela_ativa falhou: {r.get('mensagem', 'sem mensagem')}")
    except Exception as e:
        col.avisar(f"janela_ativa lançou exceção: {e}")
        resultados["janela_ativa"] = {"erro": str(e)}

    # Teste 2: copiar_clipboard
    try:
        r = enviar_comando("copiar_clipboard", texto="health_check")
        sucesso = r.get("sucesso", False)
        resultados["copiar_clipboard"] = {"sucesso": sucesso}
        if sucesso:
            log.info(f"  ✓ copiar_clipboard OK")
        else:
            col.avisar(f"copiar_clipboard falhou: {r.get('mensagem', '?')}")
    except Exception as e:
        col.avisar(f"copiar_clipboard lançou exceção: {e}")
        resultados["copiar_clipboard"] = {"erro": str(e)}

    # Teste 3: screenshot
    try:
        r = enviar_comando("screenshot", contexto="health_check")
        sucesso = r.get("sucesso", False)
        resultados["screenshot"] = {"sucesso": sucesso}
        if sucesso:
            log.info(f"  ✓ screenshot OK")
        else:
            col.avisar(f"screenshot falhou: {r.get('mensagem', '?')}")
    except Exception as e:
        col.avisar(f"screenshot lançou exceção: {e}")
        resultados["screenshot"] = {"erro": str(e)}

    # Heurística: se todos os 3 falharam, executor provavelmente está down
    todos_falharam = all(
        not r.get("sucesso") for r in resultados.values() if isinstance(r, dict)
    )
    if todos_falharam and resultados:
        col.avisar("Os 3 testes do executor falharam — executor Windows pode estar desligado")

    col.registrar("executor", resultados)


# =================================================================
# CHECK 4 — Creative Engine (config + yuv420p)
# =================================================================

def check_creative_engine(col: Coletor):
    log.info("\n🎨 Check 4 — Creative Engine")
    dados = {}

    # 4.1 — Renderer tem yuv420p?
    renderer_path = PROJETO_ROOT / "creative_engine" / "local_video_renderer.py"
    if not renderer_path.exists():
        col.bloquear("local_video_renderer.py ausente — bloqueia renderização")
        dados["renderer_existe"] = False
    else:
        try:
            conteudo = renderer_path.read_text(encoding="utf-8", errors="replace")
            tem_yuv = "yuv420p" in conteudo
            tem_pix = "-pix_fmt" in conteudo or "pix_fmt" in conteudo
            dados["renderer_existe"]   = True
            dados["tem_yuv420p"]       = tem_yuv
            dados["tem_pix_fmt_param"] = tem_pix
            if tem_yuv or tem_pix:
                log.info(f"  ✓ Renderer com codec yuv420p/pix_fmt detectado")
            else:
                col.avisar(
                    "Renderer NÃO menciona yuv420p/pix_fmt — "
                    "TikTok pode rejeitar vídeos silenciosamente"
                )
        except Exception as e:
            col.avisar(f"Não consegui ler renderer: {e}")
            dados["erro_leitura"] = str(e)

    # 4.2 — Config do creative engine
    config_paths = [
        PROJETO_ROOT / "creative_engine" / "config.json",
        PROJETO_ROOT / "shared" / "config.py",
    ]
    config_encontrado = None
    for p in config_paths:
        if p.exists():
            config_encontrado = p
            break

    if not config_encontrado:
        col.avisar("Config do creative engine não encontrada em locais conhecidos")
        dados["config_encontrado"] = False
    else:
        dados["config_encontrado"] = True
        dados["config_path"]       = str(config_encontrado.relative_to(PROJETO_ROOT))
        # Tenta ler video_provider (só funciona pra JSON; .py exigiria import)
        if config_encontrado.suffix == ".json":
            try:
                cfg = json.loads(config_encontrado.read_text(encoding="utf-8"))
                provider = cfg.get("video_provider")
                dados["video_provider"] = provider
                if provider in ("local_moviepy", "stub", "remote_api"):
                    log.info(f"  ✓ video_provider: {provider}")
                else:
                    col.avisar(f"video_provider desconhecido: '{provider}'")
            except Exception as e:
                col.avisar(f"Config inválida: {e}")
        else:
            log.info(f"  ✓ Config em {config_encontrado.name} (não JSON, sem leitura profunda)")

    col.registrar("creative_engine", dados)


# =================================================================
# CHECK 5 — Cache visual
# =================================================================

def check_cache_visual(col: Coletor):
    log.info("\n💾 Check 5 — Cache visual")
    dados = {"path": str(CACHE_FILE)}

    if not CACHE_FILE.exists():
        log.info(f"  ✓ Cache visual ainda não criado (normal antes do 1º uso)")
        dados["existe"] = False
        col.registrar("cache_visual", dados)
        return

    dados["existe"] = True
    try:
        conteudo = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        col.avisar(f"Cache visual ({CACHE_FILE.name}) é JSON inválido: {e}")
        dados["json_valido"] = False
        dados["erro"] = str(e)
        col.registrar("cache_visual", dados)
        return

    dados["json_valido"] = True
    if not isinstance(conteudo, dict):
        col.avisar("Cache visual não é um dicionário — formato inesperado")
        dados["formato_inesperado"] = True
        col.registrar("cache_visual", dados)
        return

    total       = len(conteudo)
    desconfiav  = sum(1 for v in conteudo.values() if isinstance(v, dict) and v.get("desconfiavel"))
    cooperativ  = sum(1 for v in conteudo.values() if isinstance(v, dict) and v.get("via_localizar"))

    dados.update({
        "total_entradas":         total,
        "entradas_desconfiaveis": desconfiav,
        "entradas_cooperativas":  cooperativ,
    })
    log.info(f"  ✓ Cache visual: {total} entradas ({desconfiav} desconfiáveis, {cooperativ} cooperativas)")

    if total > 0 and desconfiav / total > 0.3:
        col.avisar(
            f"Cache visual tem {desconfiav}/{total} entradas desconfiáveis "
            f"({desconfiav*100//total}%) — considere purgar com "
            f"interface_cache.limpar_cache_desconfiavel()"
        )

    col.registrar("cache_visual", dados)


# =================================================================
# CHECK 6 — State Manager
# =================================================================

CHAVES_IMPORTANTES_STATE = [
    "estado_atual",
    "produto_atual",
    "gemini_quota_bloqueada",
    "publish_guard_aprovado",
]


def check_state_manager(col: Coletor):
    log.info("\n📝 Check 6 — State Manager")
    dados = {}

    try:
        from memory.state_manager import carregar_estado
    except ImportError as e:
        # Pode ter nome diferente no projeto — tentar ler_estado
        try:
            from memory.state_manager import ler_estado as carregar_estado
        except ImportError:
            col.avisar(f"Não consegui importar carregar_estado do state_manager: {e}")
            dados["erro_import"] = str(e)
            col.registrar("state_manager", dados)
            return

    try:
        estado = carregar_estado() or {}
        dados["estado_carregado"] = True
        dados["total_chaves"]     = len(estado)

        presentes  = [k for k in CHAVES_IMPORTANTES_STATE if k in estado]
        ausentes   = [k for k in CHAVES_IMPORTANTES_STATE if k not in estado]
        dados["chaves_importantes_presentes"] = presentes
        dados["chaves_importantes_ausentes"]  = ausentes

        # Snapshot leve das chaves importantes (sem expor sensitive data)
        snapshot = {}
        for k in presentes:
            v = estado[k]
            if isinstance(v, (str, int, float, bool)) or v is None:
                snapshot[k] = v
            else:
                snapshot[k] = f"<{type(v).__name__}>"
        dados["snapshot_chaves_importantes"] = snapshot

        log.info(
            f"  ✓ State carregado: {len(estado)} chaves "
            f"({len(presentes)}/{len(CHAVES_IMPORTANTES_STATE)} importantes presentes)"
        )

        if ausentes:
            col.avisar(
                f"Chaves importantes ausentes do state: {ausentes} "
                f"(podem ser criadas na 1ª execução)"
            )

        # Alerta especial: se quota bloqueada estiver marcada, avisa
        if estado.get("gemini_quota_bloqueada"):
            col.avisar(
                f"gemini_quota_bloqueada=True no state — última execução "
                f"parou por quota ({estado.get('gemini_quota_ultimo_erro', '?')})"
            )

    except Exception as e:
        col.avisar(f"Falha ao carregar state: {e}")
        dados["erro_carga"] = str(e)

    col.registrar("state_manager", dados)


# =================================================================
# CHECK 7 — Planilha (Google Sheets)
# =================================================================

ABAS_ESPERADAS = [
    ("Fila_de_Postagem",  True),   # crítica
    ("Config_Agente",     True),   # crítica
    ("Performance_Posts", False),  # ideal mas pode não existir
]


def check_planilha(col: Coletor):
    log.info("\n📊 Check 7 — Planilha Google Sheets")
    dados = {}

    try:
        from memory.sheets_engine import conectar_planilha
    except Exception as e:
        col.avisar(f"Não consegui importar conectar_planilha: {e}")
        dados["erro_import"] = str(e)
        col.registrar("planilha", dados)
        return

    try:
        planilha = conectar_planilha()
        dados["conectou"] = True
        log.info(f"  ✓ Conectado à planilha")
    except Exception as e:
        col.avisar(f"Não consegui conectar à planilha: {str(e)[:120]}")
        dados["conectou"]   = False
        dados["erro_conexao"] = str(e)[:200]
        col.registrar("planilha", dados)
        return

    # Verifica abas
    try:
        # gspread usa worksheets() pra listar; nomes ficam em .title
        worksheets = planilha.worksheets()
        nomes_abas = [w.title for w in worksheets]
        dados["abas_existentes"] = nomes_abas
    except Exception as e:
        col.avisar(f"Não consegui listar abas: {e}")
        dados["erro_listar_abas"] = str(e)
        col.registrar("planilha", dados)
        return

    presentes, faltando = [], []
    for nome, eh_critica in ABAS_ESPERADAS:
        if nome in nomes_abas:
            presentes.append(nome)
        else:
            faltando.append(nome)
            if eh_critica:
                col.avisar(f"Aba crítica ausente na planilha: '{nome}'")
            else:
                log.info(f"  • Aba opcional ausente: '{nome}' (será criada quando preciso)")

    dados["abas_presentes"] = presentes
    dados["abas_faltando"]  = faltando
    log.info(f"  ✓ Abas: {len(presentes)}/{len(ABAS_ESPERADAS)} esperadas presentes")

    col.registrar("planilha", dados)


# =================================================================
# CHECK 8 — Vídeos
# =================================================================

TAMANHO_MIN_VIDEO_OK = 50_000  # 50 KB


def check_videos(col: Coletor):
    log.info("\n🎬 Check 8 — Vídeos")
    dados = {"videos_dir": str(VIDEOS_DIR)}

    if not VIDEOS_DIR.exists():
        col.avisar(f"Diretório de vídeos não existe: {VIDEOS_DIR}")
        dados["existe"] = False
        col.registrar("videos", dados)
        return

    dados["existe"] = True
    try:
        mp4s = sorted(VIDEOS_DIR.glob("*.mp4"))
    except Exception as e:
        col.avisar(f"Erro ao listar vídeos: {e}")
        dados["erro_glob"] = str(e)
        col.registrar("videos", dados)
        return

    pequenos = []
    info_videos = []
    for v in mp4s:
        try:
            tam = v.stat().st_size
            info_videos.append({"nome": v.name, "tamanho_bytes": tam})
            if tam < TAMANHO_MIN_VIDEO_OK:
                pequenos.append((v.name, tam))
        except Exception:
            pass

    dados["total_mp4"] = len(mp4s)
    dados["pequenos_qtd"] = len(pequenos)
    dados["amostra"] = info_videos[-5:]  # últimos 5 só
    log.info(f"  ✓ {len(mp4s)} vídeo(s) MP4 em {VIDEOS_DIR.name}/")

    if pequenos:
        for nome, tam in pequenos[:5]:
            col.avisar(f"Vídeo pequeno ({tam/1024:.1f} KB): {nome} — pode estar corrompido")

    # Verifica último video_path do ultimo_plano.json
    ultimo_plano = PLANS_DIR / "ultimo_plano.json"
    if ultimo_plano.exists():
        try:
            plano = json.loads(ultimo_plano.read_text(encoding="utf-8"))
            sugerido = plano.get("video_path_sugerido") or plano.get("video_path") or ""
            dados["ultimo_video_path_sugerido"] = sugerido
            if sugerido:
                # Converte path windows pra checagem local
                p_check = Path(sugerido) if os.name == "nt" else None
                if p_check and p_check.exists():
                    log.info(f"  ✓ Último video_path do plano existe: {p_check.name}")
                    dados["ultimo_video_existe"] = True
                elif p_check:
                    col.avisar(f"video_path do último plano não existe no disco: {sugerido}")
                    dados["ultimo_video_existe"] = False
        except Exception as e:
            log.debug(f"  Não consegui ler ultimo_plano.json: {e}")

    col.registrar("videos", dados)


# =================================================================
# RELATÓRIO FINAL
# =================================================================

def classificar(score: int) -> str:
    for limite, rotulo in CLASSIFICACAO:
        if score >= limite:
            return rotulo
    return "🔴 Score inválido"


def salvar_relatorio(resultado: dict):
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        caminho = PLANS_DIR / "health_check_resultado.json"
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2, default=str)
        log.info(f"\n💾 Relatório salvo em: {caminho}")
        return str(caminho)
    except Exception as e:
        log.warning(f"⚠️ Não consegui salvar relatório: {e}")
        return None


def imprimir_relatorio_final(resultado: dict):
    score = resultado["score_prontidao"]
    print("\n" + "=" * 60)
    print(f"  🏥 HEALTH CHECK — RELATÓRIO FINAL")
    print("=" * 60)
    print(f"\n  Score de prontidão: {score}/100")
    print(f"  Status: {classificar(score)}")
    print(f"  Timestamp: {resultado['timestamp']}")

    print(f"\n  📊 Resumo:")
    print(f"    Bloqueadores: {len(resultado['bloqueadores'])}")
    print(f"    Warnings:     {len(resultado['warnings'])}")

    if resultado["bloqueadores"]:
        print(f"\n  🛑 BLOQUEADORES ({len(resultado['bloqueadores'])}):")
        for b in resultado["bloqueadores"]:
            print(f"     • {b}")

    if resultado["warnings"]:
        print(f"\n  ⚠️  WARNINGS ({len(resultado['warnings'])}):")
        for w in resultado["warnings"]:
            print(f"     • {w}")

    if not resultado["bloqueadores"] and not resultado["warnings"]:
        print(f"\n  🎉 Sistema 100% pronto — sem bloqueadores nem warnings")

    print(f"\n  💾 Detalhes completos em: shared/content_plans/health_check_resultado.json")
    print("=" * 60)


# =================================================================
# FUNÇÃO PRINCIPAL
# =================================================================

def executar_health_check() -> dict:
    """
    Roda todas as 8 checagens e retorna o relatório.
    NUNCA crasha: qualquer falha de check vira warning/bloqueador.
    """
    log.info("=" * 60)
    log.info("🏥 HEALTH CHECK AGENT v1 — Iniciando diagnóstico")
    log.info("=" * 60)
    inicio = time.time()
    col = Coletor()

    checks_a_rodar = [
        check_arquivos,
        check_dependencias,
        check_executor,
        check_creative_engine,
        check_cache_visual,
        check_state_manager,
        check_planilha,
        check_videos,
    ]

    for fn in checks_a_rodar:
        try:
            fn(col)
        except Exception as e:
            # Failsafe: nenhum check pode crashar o agent
            col.avisar(f"Check '{fn.__name__}' lançou exceção inesperada: {e}")
            log.warning(f"⚠️ Exceção em {fn.__name__}: {e}")

    duracao = round(time.time() - inicio, 2)
    score = col.score()

    resultado = {
        "sucesso":          len(col.bloqueadores) == 0,
        "score_prontidao":  score,
        "classificacao":    classificar(score),
        "bloqueadores":     col.bloqueadores,
        "warnings":         col.warnings,
        "checks":           col.checks,
        "duracao_segundos": duracao,
        "timestamp":        time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    log.info(f"\n⏱️ Health check concluído em {duracao}s — score: {score}/100")
    return resultado


# =================================================================
# TESTE VIA TERMINAL
# =================================================================

if __name__ == "__main__":
    resultado = executar_health_check()
    salvar_relatorio(resultado)
    imprimir_relatorio_final(resultado)

    # Exit code útil pra scripts/CI: 0 se pronto, 1 se warnings, 2 se bloqueadores
    if resultado["bloqueadores"]:
        sys.exit(2)
    elif resultado["warnings"]:
        sys.exit(1)
    else:
        sys.exit(0)