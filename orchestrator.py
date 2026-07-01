# agents/orchestrator.py
# MAESTRO DO JARVIS — esteira de produção contínua, 1 produto por ciclo.
#
# Duas fontes de produto/vídeo:
#
#   --fonte radar   (padrão)  Passo 0: radar descobre → Passo 2: IA gera vídeo original
#   --fonte hunter            Passo 0: hunter captura criativos licenciados do Telegram,
#                             re-produz com narração/hook/CTA próprios → pula Passo 2
#
#   Passo 0 — RADAR ou HUNTER (descoberta + vídeo se hunter)
#   Passo 1 — CARGA dos produtos (radar_tendencias.json ou planos do hunter)
#   Passo 2 — VÍDEO original por IA (só no modo radar; hunter já fez)
#   Passo 3 — SITE: bio_page_builder regenera index.html
#   Passo 4 — TELEGRAM: telegram_poster posta o achado no grupo
#
# CLI:
#   python -m agents.orchestrator --lote 3
#   python -m agents.orchestrator --lote 3 --fonte hunter --canal-hunter @canal_alvo
#   python -m agents.orchestrator --lote 1 --dry-run
#   python -m agents.orchestrator --status
#   python -m agents.orchestrator --lote 5 --sem-postar
#   python -m agents.orchestrator --lote 3 --sem-radar
#   python -m agents.orchestrator --lote 3 --grupos-arquivo grupos.txt --radar-limite 40

import os
import sys
import json
import time
import asyncio
import argparse
from pathlib import Path

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("orchestrator")

PROJETO_ROOT = Path(__file__).parent.parent
RADAR_PATH = PROJETO_ROOT / "shared" / "content_plans" / "radar_tendencias.json"
ESTADO_PATH = PROJETO_ROOT / "shared" / "content_plans" / "orchestrator_state.json"
SHARED_PLANS = PROJETO_ROOT / "shared" / "content_plans"

GRUPOS_ARQUIVO_PADRAO = PROJETO_ROOT / "grupos.txt"

ST_PENDENTE = "pendente"
ST_VIDEO_OK = "video_ok"
ST_SITE_OK = "site_ok"
ST_POSTADO = "postado"


# =====================================================================
# ESTADO
# =====================================================================
def _carregar_estado() -> dict:
    if ESTADO_PATH.exists():
        try:
            return json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"estado corrompido ({e}); recomeçando.")
    return {"produtos": {}}


def _salvar_estado(estado: dict):
    tmp = ESTADO_PATH.with_suffix(".json.tmp")
    try:
        ESTADO_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False, indent=2)
        tmp.replace(ESTADO_PATH)
    except Exception as e:
        log.error(f"falha ao salvar estado: {e}")
        try:
            tmp.unlink()
        except Exception:
            pass


def _marcar(estado: dict, nome: str, status: str, **extra):
    p = estado["produtos"].setdefault(nome, {})
    p["status"] = status
    p["atualizado"] = time.strftime("%Y-%m-%d %H:%M:%S")
    p.update(extra)
    _salvar_estado(estado)


def _ja_finalizado(estado: dict, nome: str) -> bool:
    return estado["produtos"].get(nome, {}).get("status") == ST_POSTADO


# =====================================================================
# PASSO 0A — RADAR (modo radar)
# =====================================================================
def _resolver_arquivo_grupos(grupos_arquivo: str) -> str:
    return (grupos_arquivo
            or os.environ.get("TELEGRAM_GRUPOS_ARQUIVO", "")
            or str(GRUPOS_ARQUIVO_PADRAO))


def _atualizar_radar(grupos_arquivo: str, limite: int, dry_run: bool,
                     estado: dict) -> dict:
    log.info("─" * 60)
    log.info("📡 Passo 0/4: atualizando radar de tendências...")

    if dry_run:
        log.info("   🧪 dry-run: radar não consultado (usa cache se houver).")
        return {"ok": True, "dry_run": True}

    arquivo = _resolver_arquivo_grupos(grupos_arquivo)
    if not Path(arquivo).exists():
        log.warning(f"   ⚠️  arquivo de grupos não encontrado ({arquivo}).")
        log.warning("      Usando o radar em CACHE.")
        return {"ok": False, "erro": "sem arquivo de grupos", "cache": True}

    try:
        from integrations.telegram_radar import rodar_radar
    except Exception as e:
        log.warning(f"   ⚠️  radar indisponível ({e}); usando CACHE.")
        return {"ok": False, "erro": str(e), "cache": True}

    try:
        res = rodar_radar(arquivo=arquivo, limite=limite, gerar_links=True)
    except Exception as e:
        log.warning(f"   ⚠️  erro no radar ({e}); usando CACHE.")
        return {"ok": False, "erro": str(e), "cache": True}

    if res.get("ok"):
        n = res.get("total", 0)
        com_link = res.get("com_link", 0)
        log.info(f"   ✅ radar atualizado: {n} produto(s) | {com_link} com link.")
        estado["ultimo_radar"] = time.strftime("%Y-%m-%d %H:%M:%S")
        estado["ultimo_radar_total"] = n
        estado["ultimo_radar_com_link"] = com_link
        _salvar_estado(estado)
    else:
        log.warning(f"   ⚠️  radar não atualizou ({res.get('erro')}); usando CACHE.")
        res["cache"] = True
    return res


# =====================================================================
# PASSO 0B — HUNTER (modo hunter)
# =====================================================================
def _rodar_hunter(canal: str, limite: int, dry_run: bool, estado: dict) -> dict:
    """
    Roda o telegram_repurpose_hunter: captura criativos licenciados,
    gera link de afiliado Shopee, re-produz vídeo com camadas de conteúdo.
    Os planos ficam em shared/content_plans/plano_*.json.
    """
    log.info("─" * 60)
    log.info(f"🎯 Passo 0/4: Hunter — capturando criativos de '{canal}'...")

    if dry_run:
        log.info("   🧪 dry-run: hunter não executado.")
        return {"ok": True, "dry_run": True, "processados": 0}

    if not canal:
        log.error("   ❌ --canal-hunter obrigatório no modo hunter.")
        return {"ok": False, "erro": "canal não informado"}

    try:
        from integrations.telegram_repurpose_hunter import varrer_canal_por_criativos
    except Exception as e:
        log.error(f"   ❌ import do hunter falhou: {e}")
        return {"ok": False, "erro": str(e)}

    try:
        asyncio.run(varrer_canal_por_criativos(canal, limite))
    except RuntimeError:
        # Se já há um event loop rodando (Jupyter, etc), usa nest_asyncio ou cria task
        try:
            loop = asyncio.get_running_loop()
            loop.run_until_complete(varrer_canal_por_criativos(canal, limite))
        except Exception as e:
            log.error(f"   ❌ Falha ao rodar hunter: {e}")
            return {"ok": False, "erro": str(e)}
    except Exception as e:
        log.error(f"   ❌ Hunter falhou: {e}")
        return {"ok": False, "erro": str(e)}

    # Conta planos gerados pelo hunter
    planos = _carregar_produtos_do_hunter()
    n = len(planos)
    log.info(f"   ✅ Hunter concluído: {n} produto(s) com vídeo pronto.")
    estado["ultimo_hunter"] = time.strftime("%Y-%m-%d %H:%M:%S")
    estado["ultimo_hunter_canal"] = canal
    estado["ultimo_hunter_produtos"] = n
    _salvar_estado(estado)

    return {"ok": True, "processados": n}


def _carregar_produtos_do_hunter() -> list:
    """
    Lê os planos gerados pelo hunter (plano_*.json com status video_gerado).
    Converte pro formato que a esteira espera.
    """
    SHARED_PLANS.mkdir(parents=True, exist_ok=True)
    produtos = []

    for f in sorted(SHARED_PLANS.glob("plano_*.json")):
        try:
            plano = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue

        if plano.get("status_producao") != "video_gerado":
            continue

        nome = plano.get("produto", plano.get("titulo_real", ""))
        if not nome:
            continue

        produtos.append({
            "nome":           nome,
            "meu_link":       plano.get("link_afiliado", ""),
            "comissao_valor": plano.get("preco_real", 0),
            "imagem":         "",
            "campeao":        plano.get("titulo_real", nome),
            "video_path":     plano.get("video_path_sugerido", ""),
            "plano":          plano,
            "fonte":          "hunter",
            "_arquivo_plano": str(f),
        })

    log.info(f"📦 {len(produtos)} produto(s) do hunter com vídeo pronto.")
    return produtos


# =====================================================================
# PASSO 1 — CARREGAR PRODUTOS DO RADAR
# =====================================================================
def _carregar_produtos_do_radar() -> list:
    if not RADAR_PATH.exists():
        log.error(f"❌ radar não encontrado: {RADAR_PATH}")
        return []
    try:
        dados = json.loads(RADAR_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.error(f"❌ erro lendo radar: {e}")
        return []
    produtos = []
    for p in dados.get("produtos", []):
        if p.get("meu_link"):
            produtos.append(p)
    produtos.sort(key=lambda p: float(p.get("comissao_valor", 0) or 0), reverse=True)
    return produtos


# =====================================================================
# PASSO 2 — VÍDEO ORIGINAL POR IA (só no modo radar)
# =====================================================================
def _gerar_video(nome: str, dry_run: bool) -> dict:
    try:
        from creative_engine.produzir_video import produzir
    except Exception as e:
        return {"ok": False, "erro": f"import produzir_video: {e}"}
    try:
        res = produzir(nome, dry_run=dry_run)
        return {"ok": bool(res.get("ok")), "detalhe": res}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


# =====================================================================
# PASSO 3 — REGENERAR O SITE
# =====================================================================
def _regenerar_site(dry_run: bool) -> dict:
    if dry_run:
        return {"ok": True, "dry_run": True}
    try:
        from creative_engine.bio_page_builder import _carregar_produtos, gerar_site, SAIDA_HTML
    except Exception as e:
        return {"ok": False, "erro": f"import bio_page_builder: {e}"}
    try:
        produtos = _carregar_produtos()
        if not produtos:
            return {"ok": False, "erro": "sem produtos pro site"}
        html = gerar_site(produtos)
        SAIDA_HTML.parent.mkdir(parents=True, exist_ok=True)
        with open(SAIDA_HTML, "w", encoding="utf-8") as f:
            f.write(html)
        return {"ok": True, "saida": str(SAIDA_HTML), "n": len(produtos)}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


# =====================================================================
# PASSO 4 — POSTAR NO TELEGRAM
# =====================================================================
def _postar_telegram(produto_radar: dict, dry_run: bool) -> dict:
    if dry_run:
        return {"ok": True, "dry_run": True}
    try:
        from integrations.telegram_poster import postar_achado
    except Exception as e:
        return {"ok": False, "erro": f"import telegram_poster: {e}"}
    produto = {
        "nome": produto_radar.get("nome", ""),
        "titulo": produto_radar.get("campeao") or produto_radar.get("nome", ""),
        "preco_real": produto_radar.get("comissao_valor", ""),
        "link": produto_radar.get("meu_link", ""),
        "imagem": produto_radar.get("imagem", ""),
    }
    try:
        return postar_achado(produto)
    except Exception as e:
        return {"ok": False, "erro": str(e)}


# =====================================================================
# CICLO POR PRODUTO
# =====================================================================
def processar_produto(produto: dict, estado: dict, dry_run: bool,
                      sem_postar: bool) -> str:
    nome = produto.get("nome", "")
    fonte = produto.get("fonte", "radar")
    video_ja_pronto = fonte == "hunter" and produto.get("video_path")

    log.info("─" * 60)
    log.info(f"🛠️  PROCESSANDO: {nome}")
    log.info(f"   💰 comissão R$ {produto.get('comissao_valor', 0)} | "
             f"fonte: {fonte} | "
             f"link: {produto.get('meu_link', '')[:40]}")

    _marcar(estado, nome, ST_PENDENTE,
            comissao=produto.get("comissao_valor", 0), fonte=fonte)

    # Passo 2 — vídeo (pula se hunter já gerou)
    if video_ja_pronto:
        log.info(f"   ⏭️  Passo 2/4: vídeo já pronto pelo hunter → {produto['video_path'][-50:]}")
        _marcar(estado, nome, ST_VIDEO_OK, video_fonte="hunter")
    else:
        log.info("   ▶️  Passo 2/4: gerando vídeo original por IA...")
        r_video = _gerar_video(nome, dry_run)
        if not r_video.get("ok"):
            erro_real = (r_video.get("erro")
                         or (r_video.get("detalhe") or {}).get("erro")
                         or "falha na geração do vídeo")
            log.error(f"   ❌ vídeo falhou: {erro_real}")
            _marcar(estado, nome, "erro_video", erro=str(erro_real)[:200])
            return "erro_video"
        log.info("   ✅ vídeo pronto")
        _marcar(estado, nome, ST_VIDEO_OK, video_fonte="ia_original")

    # Passo 3 — site
    log.info("   ▶️  Passo 3/4: regenerando o site...")
    r_site = _regenerar_site(dry_run)
    if not r_site.get("ok"):
        log.warning(f"   ⚠️  site falhou: {r_site.get('erro', '?')} (segue mesmo assim)")
        _marcar(estado, nome, "erro_site", erro=str(r_site.get("erro", "?"))[:200])
    else:
        log.info(f"   ✅ site atualizado ({r_site.get('n', '?')} produtos)")
        _marcar(estado, nome, ST_SITE_OK)

    # Passo 4 — telegram
    if sem_postar:
        log.info("   ⏭️  Passo 4/4: postagem pulada (--sem-postar)")
        return estado["produtos"][nome]["status"]

    log.info("   ▶️  Passo 4/4: postando no Telegram...")
    r_post = _postar_telegram(produto, dry_run)
    if not r_post.get("ok"):
        log.error(f"   ❌ telegram falhou: {r_post.get('erro', '?')}")
        _marcar(estado, nome, "erro_telegram", erro=str(r_post.get("erro", "?"))[:200])
        return "erro_telegram"
    log.info("   ✅ postado no Telegram")
    _marcar(estado, nome, ST_POSTADO)
    return ST_POSTADO


# =====================================================================
# ESTEIRA
# =====================================================================
def rodar_lote(tamanho: int, dry_run: bool = False, sem_postar: bool = False,
               pausa: float = 5.0, sem_radar: bool = False,
               grupos_arquivo: str = "", radar_limite: int = 30,
               fonte: str = "radar", canal_hunter: str = "") -> dict:
    log.info("█" * 60)
    log.info(f"🎯 ORQUESTRADOR JARVIS — lote de {tamanho} | fonte: {fonte}"
             f"{' [DRY-RUN]' if dry_run else ''}")
    log.info("█" * 60)

    estado = _carregar_estado()

    # ── Passo 0 — descoberta ───────────────────────────────────────────
    if fonte == "hunter":
        res_fonte = _rodar_hunter(canal_hunter, tamanho, dry_run, estado)
        if not res_fonte.get("ok") and not dry_run:
            log.error("❌ Hunter falhou. Nenhum produto capturado.")
            return {"ok": False, "erro": res_fonte.get("erro", "hunter falhou")}
    else:
        if sem_radar:
            log.info("─" * 60)
            log.info("⏭️  Passo 0/4: radar pulado (--sem-radar) — usando cache.")
        else:
            _atualizar_radar(grupos_arquivo, radar_limite, dry_run, estado)

    # ── Passo 1 — carga ───────────────────────────────────────────────
    if fonte == "hunter":
        produtos = _carregar_produtos_do_hunter()
    else:
        produtos = _carregar_produtos_do_radar()

    if not produtos:
        msg = "radar vazio" if fonte == "radar" else "hunter não gerou produtos"
        log.error(f"❌ Nenhum produto disponível ({msg}).")
        return {"ok": False, "erro": msg}

    pendentes = [p for p in produtos if not _ja_finalizado(estado, p.get("nome", ""))]
    if not pendentes:
        log.info("✅ Todos os produtos já foram processados!")
        return {"ok": True, "processados": 0, "todos_feitos": True}

    alvos = pendentes[:tamanho]
    log.info(f"📦 {len(pendentes)} pendente(s); processando {len(alvos)} neste lote.")

    resultados = {"postado": 0, "erro": 0, "outros": 0}
    for i, produto in enumerate(alvos, 1):
        log.info(f"\n[{i}/{len(alvos)}]")
        try:
            status = processar_produto(produto, estado, dry_run, sem_postar)
            if status == ST_POSTADO:
                resultados["postado"] += 1
            elif status.startswith("erro"):
                resultados["erro"] += 1
            else:
                resultados["outros"] += 1
        except Exception as e:
            log.error(f"   ❌ erro inesperado: {e}")
            resultados["erro"] += 1
        if i < len(alvos) and pausa > 0:
            time.sleep(pausa)

    log.info("\n" + "═" * 60)
    log.info(f"🏁 LOTE CONCLUÍDO ({fonte}): ✅ {resultados['postado']} postado(s) | "
             f"❌ {resultados['erro']} erro(s) | ⏸️ {resultados['outros']} parcial(is)")
    log.info("═" * 60)
    return {"ok": True, "fonte": fonte, **resultados}


# =====================================================================
# STATUS
# =====================================================================
def mostrar_status():
    estado = _carregar_estado()
    produtos = estado.get("produtos", {})
    if estado.get("ultimo_radar"):
        print(f"\n📡 Último radar: {estado['ultimo_radar']} "
              f"({estado.get('ultimo_radar_com_link', '?')} com link)")
    if estado.get("ultimo_hunter"):
        print(f"🎯 Último hunter: {estado['ultimo_hunter']} "
              f"(canal: {estado.get('ultimo_hunter_canal', '?')} | "
              f"{estado.get('ultimo_hunter_produtos', '?')} produtos)")
    if not produtos:
        print("\n📭 Nenhum produto processado ainda.\n")
        return
    contagem = {}
    for p in produtos.values():
        s = p.get("status", "?")
        contagem[s] = contagem.get(s, 0) + 1
    print("\n" + "═" * 50)
    print("📊 ESTADO DA ESTEIRA")
    print("═" * 50)
    for s, n in sorted(contagem.items()):
        emoji = {"postado": "✅", "video_ok": "🎬", "site_ok": "🌐",
                 "pendente": "⏳"}.get(s, "❌")
        print(f"  {emoji} {s:16} {n}")
    # Mostra fonte de cada produto
    fontes = {}
    for p in produtos.values():
        f = p.get("fonte", "radar")
        fontes[f] = fontes.get(f, 0) + 1
    if fontes:
        print(f"\n  📡 Por fonte: {fontes}")
    print("═" * 50)
    erros = {k: v for k, v in produtos.items() if v.get("status", "").startswith("erro")}
    if erros:
        print("\n⚠️  Produtos com erro:")
        for nome, info in list(erros.items())[:10]:
            print(f"  • {nome[:40]}: {info.get('status')} — {info.get('erro', '')[:60]}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Orquestrador Jarvis — esteira de produção")
    parser.add_argument("--lote", type=int, default=3, help="quantos produtos processar")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    parser.add_argument("--sem-postar", action="store_true", dest="sem_postar")
    parser.add_argument("--sem-radar", action="store_true", dest="sem_radar")
    parser.add_argument("--grupos-arquivo", default="", dest="grupos_arquivo")
    parser.add_argument("--radar-limite", type=int, default=30, dest="radar_limite")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--pausa", type=float, default=5.0)

    # Integração Hunter
    parser.add_argument("--fonte", choices=["radar", "hunter"], default="radar",
                        help="Fonte de produtos: 'radar' (IA original) ou 'hunter' (criativos Telegram)")
    parser.add_argument("--canal-hunter", default="", dest="canal_hunter",
                        help="@canal do Telegram para o hunter capturar criativos")

    args = parser.parse_args()

    if args.status:
        mostrar_status()
        return 0

    res = rodar_lote(
        args.lote, dry_run=args.dry_run, sem_postar=args.sem_postar,
        pausa=args.pausa, sem_radar=args.sem_radar,
        grupos_arquivo=args.grupos_arquivo, radar_limite=args.radar_limite,
        fonte=args.fonte, canal_hunter=args.canal_hunter,
    )
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())