"""
agents/production_runner_agent.py
=================================
Orquestrador de PRODUÇÃO EM LOTE — o "Jarvis Operador 24h".

Recebe uma lista de produtos e roda o pipeline completo de cada um, em sequência,
SEM MORRER se um falhar. Cada etapa roda isolada em SUBPROCESS com TIMEOUT, então
um travamento de MoviePy/ffmpeg/Edge-TTS/API mata só aquela etapa — nunca o runner.

PIPELINE POR PRODUTO:
  1. asset_autopilot_agent   (coleta B-roll)       timeout 15min
  2. asset_hunter_agent      (move/classifica)     timeout  2min
  3. visual_audit_agent      (marca suspeitos)     timeout  5min
  4. narrated_video_agent    (gera o vídeo)        timeout 20min

Para cada etapa captura: exit_code, stdout/stderr (em log), duração, timeout.
Quality Gate bloquear (exit 3 do narrated) = "bloqueado", NÃO é erro do sistema.

USO:
  python -m agents.production_runner_agent --lista produtos_teste.json
  python -m agents.production_runner_agent --produtos "Mini Aspirador" "Cortador de Legumes"
  python -m agents.production_runner_agent --lista produtos.json --max-downloads 12

produtos_teste.json:
  ["Mini Aspirador de Teclado", "Cortador de Legumes", "Organizador de Cabos"]
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("production_runner")

try:
    from shared import production_state as pstate
except Exception:
    import importlib.util
    _p = Path(__file__).resolve().parent.parent / "shared" / "production_state.py"
    spec = importlib.util.spec_from_file_location("production_state", _p)
    pstate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pstate)

# ── Definição das etapas do pipeline ─────────────────────────────────
# (nome, módulo, args_extra_fn, timeout_seg)
TIMEOUTS = {
    "autopilot": 15 * 60,
    "hunter":     2 * 60,
    "audit":      5 * 60,
    "narrated":  20 * 60,
}

# Retry: espera progressiva entre tentativas (segundos). 3 tentativas no total.
BACKOFF = [0, 30, 120]   # tentativa 1 imediata, 2 após 30s, 3 após 2min

RAIZ = Path(__file__).resolve().parent.parent


def _slug(produto: str) -> str:
    import re
    s = re.sub(r"[^\w\s-]", "", produto.lower())
    return re.sub(r"[\s-]+", "_", s).strip("_")


def _dir_saida_rodada() -> Path:
    """
    outputs/AAAA-MM-DD/run_HHMMSS/ — uma pasta ÚNICA por execução.
    Inclui a hora pra que rodar o mesmo produto 2x no mesmo dia (ex: 15h e 21h)
    NÃO sobrescreva a rodada anterior. Cada execução guarda sua própria cópia.
    """
    agora = datetime.now()
    d = (RAIZ / "outputs" / agora.strftime("%Y-%m-%d")
         / f"run_{agora.strftime('%H%M%S')}")
    d.mkdir(parents=True, exist_ok=True)
    return d


def rodar_etapa(nome: str, modulo: str, args: list, timeout: int,
                log_dir: Path) -> dict:
    """
    Roda UMA etapa como subprocess isolado, com timeout.
    Retorna dict com exit_code, duracao, status, e caminho do log.
    NUNCA levanta exceção — captura tudo.
    """
    cmd = [sys.executable, "-m", modulo] + args
    log_file = log_dir / f"{nome}.log"
    inicio = time.time()
    log.info(f"      ▶️  {nome}: {' '.join(cmd[2:])}  (timeout {timeout//60}min)")

    try:
        proc = subprocess.run(
            cmd, cwd=str(RAIZ),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, text=True, encoding="utf-8", errors="replace",
        )
        dur = time.time() - inicio
        # salva o output da etapa num log (pra você revisar depois)
        try:
            log_file.write_text(proc.stdout or "", encoding="utf-8")
        except Exception:
            pass

        exit_code = proc.returncode
        if exit_code == 0:
            status = "sucesso"
        elif nome == "narrated" and exit_code == 3:
            status = "bloqueado_quality_gate"
        else:
            status = "falha"
        log.info(f"         {_icone(status)} {nome}: {status} "
                 f"(exit {exit_code}, {dur:.0f}s)")
        if status == "falha":
            # ⚠️ O ERRO ESTAVA SENDO ENGOLIDO, e isso custou semanas (25/08).
            # A saída da etapa ia inteira pro .log em disco e NADA dela ia pro
            # journal. O daemon anunciava "❌ erro técnico — seguindo pro
            # próximo" e seguia. Resultado: a @topshoppet_ tentou produzir os
            # mesmos 2 produtos a cada 11 minutos por semanas, falhou sempre, e
            # nenhuma ferramenta conseguia dizer POR QUÊ — o vigia via conta
            # parada, a produção via déficit, e a causa estava num arquivo que
            # ninguém sabia que existia.
            #
            # 📌 Erro escrito só em disco é erro invisível: quem investiga lê o
            # journal, não `outputs/<data>/run_<hora>/<slug>/tentativa_N/`.
            cauda = [l for l in (proc.stdout or "").splitlines() if l.strip()][-12:]
            if cauda:
                log.warning(f"         ↳ últimas linhas de {nome} "
                            f"(log completo: {log_file}):")
                for linha in cauda:
                    log.warning(f"           │ {linha[:200]}")
            else:
                log.warning(f"         ↳ {nome} não imprimiu nada — "
                            f"exit {exit_code} sem saída ({log_file})")
        return {"etapa": nome, "exit_code": exit_code, "status": status,
                "duracao_seg": round(dur, 1), "log": str(log_file)}

    except subprocess.TimeoutExpired:
        dur = time.time() - inicio
        log.warning(f"         ⏱️  {nome}: TIMEOUT após {dur:.0f}s — etapa morta")
        return {"etapa": nome, "exit_code": None, "status": "timeout",
                "duracao_seg": round(dur, 1), "log": str(log_file)}
    except Exception as e:
        dur = time.time() - inicio
        log.error(f"         ❌ {nome}: erro ao executar subprocess: {e}")
        return {"etapa": nome, "exit_code": None, "status": "erro_subprocess",
                "duracao_seg": round(dur, 1), "erro": str(e)[:200]}


def _icone(status: str) -> str:
    return {"sucesso": "✅", "bloqueado_quality_gate": "🚫",
            "falha": "❌", "timeout": "⏱️", "erro_subprocess": "💥"}.get(status, "•")


def _rodar_passada(produto: str, max_downloads: int, log_dir: Path,
                    num_tentativa: int = 1, pular_coleta: bool = False) -> tuple:
    """
    Roda UMA passada do pipeline (autopilot → audit → narrated).
    Retorna (status_final, etapas) onde status_final é um de:
      'aprovado', 'bloqueado', 'erro'.

    Os logs de cada etapa vão pra log_dir/tentativa_N/ — assim a tentativa 2
    NÃO sobrescreve os logs da 1, preservando o histórico de "por que bloqueou
    antes e por que recuperou (ou não) depois".
    """
    # Subpasta por tentativa pros logs não sobrescreverem
    log_tentativa = log_dir / f"tentativa_{num_tentativa}"
    log_tentativa.mkdir(parents=True, exist_ok=True)

    pipeline = []
    if not pular_coleta:
        pipeline.append(
            ("autopilot", "agents.asset_autopilot_agent",
             ["--produto", produto, "--max-downloads", str(max_downloads)],
             TIMEOUTS["autopilot"], True))
    pipeline += [
        ("audit", "agents.visual_audit_agent",
         ["--produto", produto], TIMEOUTS["audit"], False),
        ("narrated", "agents.narrated_video_agent",
         ["--produto", produto], TIMEOUTS["narrated"], False),
    ]

    etapas = []
    for nome, modulo, args, timeout, com_retry in pipeline:
        tentativas = len(BACKOFF) if com_retry else 1
        r = None
        for t in range(tentativas):
            if t > 0:
                espera = BACKOFF[t]
                log.info(f"      🔁 Retry {nome} (tentativa {t+1}/{tentativas}) após {espera}s")
                time.sleep(espera)
            r = rodar_etapa(nome, modulo, args, timeout, log_tentativa)
            if r["status"] in ("sucesso", "bloqueado_quality_gate"):
                break
        etapas.append(r)

        if r["status"] == "bloqueado_quality_gate":
            return "bloqueado", etapas
        if r["status"] in ("falha", "timeout", "erro_subprocess"):
            return "erro", etapas

    return "aprovado", etapas


def processar_produto(produto: str, max_downloads: int,
                       dir_rodada: Path, max_tentativas: int = 2) -> dict:
    """
    Roda o pipeline de UM produto, com AUTOCORREÇÃO v1:
      1. roda normal
      2. se BLOQUEAR por falta de B-roll, RECOLETA com mais downloads
         (traz material novo/variado) e RE-TENTA
      3. limite rígido de tentativas — produto impossível não trava a fila;
         após o limite, marca 'precisa_revisar' e segue.
    """
    slug = _slug(produto)
    log_dir = dir_rodada / slug
    log_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"\n{'─'*60}")
    log.info(f"📦 PRODUTO: {produto}")
    log.info(f"{'─'*60}")
    pstate.atualizar_produto(produto, status="processando")

    todas_etapas = []
    recuperado = False

    for tentativa in range(1, max_tentativas + 1):
        if tentativa > 1:
            # AUTOCORREÇÃO: recoleta com MAIS downloads pra trazer material novo.
            # +6 por tentativa força rodadas extras → ativa queries de fallback
            # → mais variedade. O dedup garante que não baixa repetido.
            md = max_downloads + 6 * (tentativa - 1)
            log.info(f"   🔁 AUTOCORREÇÃO v1 (tentativa {tentativa}/{max_tentativas}): "
                     f"recoletando com mais assets (max-downloads={md})")

        md_atual = max_downloads + 6 * (tentativa - 1)
        status, etapas = _rodar_passada(produto, md_atual, log_dir,
                                        num_tentativa=tentativa)
        todas_etapas.extend(etapas)

        if status == "aprovado":
            recuperado = (tentativa > 1)
            break
        if status == "erro":
            # erro técnico não é recuperável por recoleta — para
            # arquiva mesmo no erro, pra ficar auditável
            artefatos = arquivar_artefatos(produto, log_dir)
            pstate.atualizar_produto(produto, status="erro",
                                     erro="etapa técnica falhou",
                                     artefatos=artefatos,
                                     etapas=todas_etapas)
            log.warning(f"   ❌ {produto}: erro técnico — seguindo pro próximo")
            return {"produto": produto, "status": "erro",
                    "artefatos": artefatos, "etapas": todas_etapas}
        # status == "bloqueado": tenta de novo se ainda há tentativas
        if tentativa < max_tentativas:
            log.info(f"   🚫 {produto}: bloqueado na tentativa {tentativa} — "
                     f"vou tentar recuperar")
        else:
            # Esgotou tentativas → precisa_revisar (não é erro, é limite humano).
            # ARQUIVA os artefatos: são justamente os JSONs que explicam POR QUE
            # bloqueou (visual_audit, edl, narrated_resultado) — auditável.
            artefatos = arquivar_artefatos(produto, log_dir)
            pstate.atualizar_produto(produto, status="precisa_revisar",
                                     quality_gate="bloqueado",
                                     tentativas=tentativa,
                                     artefatos=artefatos,
                                     etapas=todas_etapas)
            log.info(f"   ⚠️  {produto}: bloqueado após {tentativa} tentativa(s) → "
                     f"precisa_revisar (recoleta não resolveu — material insuficiente)")
            return {"produto": produto, "status": "precisa_revisar",
                    "tentativas": tentativa, "artefatos": artefatos,
                    "etapas": todas_etapas}

    # Chegou aqui = aprovado (na tentativa 1 ou recuperado)
    video = _achar_video(produto)
    artefatos = arquivar_artefatos(produto, log_dir)
    video_arquivado = artefatos.get("video.mp4", video)
    pp = gerar_pronto_para_postar(produto, video_arquivado)
    run_id = log_dir.parent.name
    status_final = "recuperado" if recuperado else "video_gerado"
    manifest = gerar_manifest(produto, log_dir, run_id, status_final,
                              "aprovado", video_arquivado, pp)

    pstate.atualizar_produto(produto, status=status_final,
                             quality_gate="aprovado",
                             ultimo_video=video,
                             video_arquivado=video_arquivado,
                             pronto_para_postar=pp,
                             manifest=manifest,
                             etapas=todas_etapas)
    if recuperado:
        log.info(f"   ✅♻️  {produto}: RECUPERADO e aprovado pela autocorreção!")
    else:
        log.info(f"   ✅ {produto}: vídeo gerado e aprovado")
    return {"produto": produto, "status": status_final,
            "ultimo_video": video, "video_arquivado": video_arquivado,
            "pronto_para_postar": pp, "manifest": manifest,
            "recuperado": recuperado, "etapas": todas_etapas}


def _achar_video(produto: str) -> str:
    """Localiza o .mp4 final gerado pelo narrated."""
    slug = _slug(produto)
    candidatos = [
        RAIZ / "videos" / f"{slug}_narrated.mp4",
    ]
    for c in candidatos:
        if c.exists():
            return str(c)
    return ""


def arquivar_artefatos(produto: str, dir_produto: Path) -> dict:
    """
    Copia os artefatos finais pra outputs/AAAA-MM-DD/produto/ — cada rodada
    guarda SUA cópia, pra videos/ não ser sobrescrito na próxima execução.

    Copia (o que existir): video.mp4, edl.json, roteiro do narrated,
    quality_gate (dentro do narrated_resultado), visual_audit.
    Retorna dict com os caminhos arquivados.
    """
    import shutil
    slug = _slug(produto)
    plans = RAIZ / "shared" / "content_plans"
    arquivados = {}

    # (origem, nome_destino)
    fontes = [
        (RAIZ / "videos" / f"{slug}_narrated.mp4", "video.mp4"),
        (plans / "edit_decision_list.json",        "edl.json"),
        (plans / "narrated_video_resultado.json",  "narrated_resultado.json"),
        (plans / "visual_audit_resultado.json",    "visual_audit.json"),
        (plans / "asset_hunter_resultado.json",    "asset_hunter.json"),
    ]
    for origem, nome_dest in fontes:
        try:
            if origem.exists():
                destino = dir_produto / nome_dest
                shutil.copy2(origem, destino)
                arquivados[nome_dest] = str(destino)
        except Exception as e:
            log.warning(f"      ⚠️  não consegui arquivar {nome_dest}: {e}")

    if arquivados:
        log.info(f"   📦 Artefatos arquivados em {dir_produto} "
                 f"({len(arquivados)} arquivo(s))")
    return arquivados


def gerar_pronto_para_postar(produto: str, video_path: str) -> str:
    """
    Gera a pasta pronto_para_postar/produto/ com vídeo + legendas + hashtags.
    Retorna o caminho da pasta (ou "" se falhar — não derruba o pipeline).
    """
    import shutil
    try:
        from creative_engine.publish_pack_builder import (construir_pacote,
                                                          salvar_pacote)
        from creative_engine.narration_script_builder import construir_roteiro
        try:
            from creative_engine.copy_adapter import detectar_categoria
            categoria = detectar_categoria(produto) or ""
        except Exception:
            categoria = ""

        roteiro = construir_roteiro(produto)
        pacote = construir_pacote(produto, roteiro, categoria)

        dir_pp = RAIZ / "pronto_para_postar" / _slug(produto)
        dir_pp.mkdir(parents=True, exist_ok=True)
        salvar_pacote(pacote, dir_pp)

        # copia o vídeo pra junto das legendas
        if video_path and Path(video_path).exists():
            try:
                shutil.copy2(video_path, dir_pp / "video.mp4")
            except Exception:
                pass

        log.info(f"   📮 Pronto pra postar: {dir_pp}")
        return str(dir_pp)
    except Exception as e:
        log.warning(f"   ⚠️  não consegui gerar pronto_para_postar: {e}")
        return ""


def gerar_manifest(produto: str, dir_produto: Path, run_id: str,
                    status: str, quality_gate: str,
                    video_path: str, publish_pack: str) -> str:
    """
    Escreve manifest.json na pasta do produto. É o "RG" da rodada: diz o que
    foi gerado, onde está, e o status de postagem por plataforma.
    O futuro upload automático lê isto pra saber o que já postou e o que falta.
    """
    manifest = {
        "produto":           produto,
        "slug":              _slug(produto),
        "run_id":            run_id,
        "status":            status,
        "quality_gate":      quality_gate,
        "video_path":        video_path,
        "publish_pack_path": publish_pack,
        "created_at":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "posted":            False,
        "platforms": {
            "tiktok":    "pendente",
            "instagram": "pendente",
            "shopee":    "pendente",
            "youtube":   "pendente",
        },
    }
    try:
        caminho = dir_produto / "manifest.json"
        caminho.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                           encoding="utf-8")
        return str(caminho)
    except Exception as e:
        log.warning(f"      ⚠️  não consegui gerar manifest: {e}")
        return ""


def gerar_relatorio(resultados: list, dir_rodada: Path, dur_total: float) -> Path:
    """Gera relatório final legível (txt + json)."""
    aprovados = [r for r in resultados if r["status"] in ("video_gerado", "recuperado")]
    recuperados = [r for r in resultados if r["status"] == "recuperado"]
    revisar = [r for r in resultados if r["status"] == "precisa_revisar"]
    bloqueados = [r for r in resultados if r["status"] == "bloqueado"]
    erros = [r for r in resultados if r["status"] == "erro"]

    linhas = []
    linhas.append("=" * 60)
    linhas.append("  🏁 RELATÓRIO DA RODADA DE PRODUÇÃO")
    linhas.append("=" * 60)
    linhas.append(f"  Data:      {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    linhas.append(f"  Produtos:  {len(resultados)}")
    linhas.append(f"  Duração:   {dur_total/60:.1f} min")
    linhas.append(f"  ✅ Aprovados: {len(aprovados)} "
                  f"(♻️ {len(recuperados)} recuperados pela autocorreção)  "
                  f"⚠️ Revisar: {len(revisar)}  ❌ Erros: {len(erros)}")
    linhas.append("")

    for r in resultados:
        ic = {"video_gerado": "✅", "recuperado": "✅♻️", "bloqueado": "🚫",
              "precisa_revisar": "⚠️", "erro": "❌"}.get(r["status"], "•")
        linhas.append(f"{ic} {r['produto']}")
        linhas.append(f"     Status: {r['status']}")
        if r.get("video_arquivado"):
            linhas.append(f"     Vídeo arquivado:    {r['video_arquivado']}")
        elif r.get("ultimo_video"):
            linhas.append(f"     Vídeo:  {r['ultimo_video']}")
        if r.get("pronto_para_postar"):
            linhas.append(f"     Pronto pra postar:  {r['pronto_para_postar']}")
        if r.get("tentativas"):
            linhas.append(f"     Tentativas: {r['tentativas']}")
        if r.get("etapa_falha"):
            linhas.append(f"     Falhou na etapa: {r['etapa_falha']}")
        dur_prod = sum(e.get("duracao_seg", 0) for e in r.get("etapas", []))
        linhas.append(f"     Tempo:  {dur_prod:.0f}s")
        linhas.append("")

    relatorio_txt = "\n".join(linhas)
    print("\n" + relatorio_txt)

    # salva txt + json
    (dir_rodada / "relatorio.txt").write_text(relatorio_txt, encoding="utf-8")
    (dir_rodada / "relatorio.json").write_text(
        json.dumps({"data": datetime.now().isoformat(),
                    "duracao_min": round(dur_total/60, 1),
                    "resumo": {"aprovados": len(aprovados),
                               "recuperados": len(recuperados),
                               "precisa_revisar": len(revisar),
                               "bloqueados": len(bloqueados),
                               "erros": len(erros)},
                    "resultados": resultados}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return dir_rodada / "relatorio.txt"


def main():
    parser = argparse.ArgumentParser(
        description="Production Runner — roda o pipeline de vários produtos em lote, 24h-safe")
    parser.add_argument("--lista", help="JSON com lista de produtos")
    parser.add_argument("--produtos", nargs="+", help="Produtos direto na linha de comando")
    parser.add_argument("--max-downloads", type=int, default=10,
                        help="Max downloads por produto no autopilot (default 10)")
    args = parser.parse_args()

    # Carrega a lista de produtos
    produtos = []
    if args.lista:
        try:
            produtos = json.loads(Path(args.lista).read_text(encoding="utf-8"))
        except Exception as e:
            log.error(f"Não consegui ler a lista '{args.lista}': {e}")
            return 1
    elif args.produtos:
        produtos = args.produtos
    else:
        log.error("Forneça --lista arquivo.json ou --produtos 'A' 'B' ...")
        return 1

    if not produtos:
        log.error("Lista de produtos vazia")
        return 1

    log.info("=" * 60)
    log.info(f"🏭 PRODUCTION RUNNER — {len(produtos)} produto(s)")
    log.info(f"   Modo 24h-safe: subprocess + timeout + retry")
    log.info("=" * 60)

    dir_rodada = _dir_saida_rodada()
    inicio = time.time()
    resultados = []

    for i, produto in enumerate(produtos, 1):
        log.info(f"\n[{i}/{len(produtos)}] ════════════════════════════")
        try:
            r = processar_produto(produto, args.max_downloads, dir_rodada)
        except Exception as e:
            # blindagem final: NADA derruba o runner
            log.error(f"   💥 Erro inesperado em '{produto}': {e} — seguindo")
            pstate.atualizar_produto(produto, status="erro", erro=str(e)[:200])
            r = {"produto": produto, "status": "erro", "erro": str(e)[:200]}
        resultados.append(r)

    dur_total = time.time() - inicio
    gerar_relatorio(resultados, dir_rodada, dur_total)
    log.info(f"\n📂 Saída da rodada: {dir_rodada}")
    log.info(f"📊 Estado: {pstate.resumo()}")

    # exit 0 sempre que o runner completou (mesmo com produtos com erro):
    # o runner em si funcionou. Erros de produto estão no relatório.
    return 0


if __name__ == "__main__":
    sys.exit(main())