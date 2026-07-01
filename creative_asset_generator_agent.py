# agents/creative_asset_generator_agent.py
# Creative Asset Generator Agent v1 do AgenteIA (Jarvis).
#
# Em vez de só BAIXAR material genérico (Asset Autopilot = Pexels/Pixabay),
# este agente CRIA cenas sob medida pro produto via IA generativa.
#
# Camadas da estratégia (este agente é a CAMADA 2):
#   Camada 1: assets reais do produto (Shopee/Amazon) — Asset Autopilot
#   Camada 2: GERAÇÃO IA por cena                       — ESTE AGENTE
#   Camada 3: Pexels/Pixabay como apoio/B-roll          — Asset Autopilot
#   Camada 4: revisão humana se qualidade ruim
#
# Fluxo v1:
#   1. Lê plano + detecta nicho/categoria
#   2. Detecta cenas faltantes (dor/demo/resultado/close/cta)
#   3. Gera prompt cinematográfico por cena (scene_prompt_builder)
#   4. Envia pro provider escolhido (manual/heygen/pixverse)
#   5. manual → salva fila ai_video_generation_queue.json pra você gerar
#      api   → baixa direto pra assets/inbox/videos
#   6. (próxima missão) Hunter organiza, reavalia score
#
# Realidade v1: a maioria dessas ferramentas (Pixverse/Hedra/Higgsfield) não
# tem API pública barata HOJE. Por isso o modo `manual` é o que entrega valor
# agora: gera os prompts perfeitos + fila, você cola na plataforma, baixa,
# joga na inbox com o nome sugerido. Providers de API ficam como esqueleto.
#
# CLI:
#   python -m agents.creative_asset_generator_agent --produto "X" --dry-run
#   python -m agents.creative_asset_generator_agent --produto "X" --provider manual
#   python -m agents.creative_asset_generator_agent --produto "X" --provider heygen
#   python -m agents.creative_asset_generator_agent --listar-providers

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from shared.logger import get_logger
from agents.asset_agent import slugificar_produto, verificar_assets_produto

from providers import (obter_provider, listar_providers,
                       obter_provider_cascata, providers_disponiveis_da_cascata,
                       CASCATA_VIDEO)
from creative_engine.scene_prompt_builder import construir_prompts_todas_cenas

# Inferência de nicho + copy (best-effort)
try:
    from creative_engine.copy_adapter import (
        inferir_nicho as _inferir_nicho,
        escolher_copy_por_cena as _escolher_copy,
    )
    _COPY_OK = True
except Exception:
    _COPY_OK = False

import subprocess


def validar_video(path: Path, dur_esperada: float = None,
                   vertical: bool = True) -> dict:
    """
    Validação TÉCNICA do vídeo gerado (não julga conteúdo visual).
    Usa ffprobe pra checar: arquivo válido, dimensão, duração, não corrompido.

    Returns: {ok, largura, altura, duracao, vertical, problemas:[...]}
    """
    info = {"ok": False, "largura": 0, "altura": 0, "duracao": 0.0,
            "vertical": False, "problemas": []}
    if not path.exists():
        info["problemas"].append("arquivo não existe")
        return info
    tam = path.stat().st_size
    if tam < 50 * 1024:
        info["problemas"].append(f"arquivo muito pequeno ({tam // 1024}KB) — provável corrupção")
        return info
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,duration",
             "-show_entries", "format=duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            info["problemas"].append(f"ffprobe falhou: {out.stderr[:100]}")
            return info
        data = json.loads(out.stdout or "{}")
        streams = data.get("streams") or []
        if not streams:
            info["problemas"].append("sem stream de vídeo (arquivo inválido)")
            return info
        s = streams[0]
        info["largura"] = int(s.get("width", 0))
        info["altura"]  = int(s.get("height", 0))
        dur = s.get("duration") or (data.get("format") or {}).get("duration") or 0
        info["duracao"] = round(float(dur), 1)
        info["vertical"] = info["altura"] > info["largura"]

        if info["largura"] == 0 or info["altura"] == 0:
            info["problemas"].append("dimensão inválida (0)")
        if vertical and not info["vertical"]:
            info["problemas"].append(
                f"não é vertical ({info['largura']}x{info['altura']}) — ruim pra TikTok")
        # dur_esperada pode vir como string (ex: Fal usa duration="5") ou número.
        # Converte com segurança pra não quebrar a subtração (float - str).
        dur_esp_num = None
        if dur_esperada is not None:
            try:
                dur_esp_num = float(dur_esperada)
            except (TypeError, ValueError):
                dur_esp_num = None
        if dur_esp_num and info["duracao"] > 0:
            if abs(info["duracao"] - dur_esp_num) > dur_esp_num * 0.5:
                info["problemas"].append(
                    f"duração {info['duracao']}s longe do esperado (~{dur_esp_num}s)")
        if info["duracao"] < 1.0:
            info["problemas"].append(f"duração muito curta ({info['duracao']}s)")

        info["ok"] = len(info["problemas"]) == 0
    except FileNotFoundError:
        info["problemas"].append("ffprobe não encontrado (instale ffmpeg)")
    except Exception as e:
        info["problemas"].append(f"erro ao validar: {type(e).__name__}: {str(e)[:80]}")
    return info

log = get_logger(__name__)

PROJETO_ROOT = Path(__file__).parent.parent
PLANS_DIR    = PROJETO_ROOT / "shared" / "content_plans"
INBOX_VIDEOS = PROJETO_ROOT / "assets" / "inbox" / "videos"
INBOX_IMGS   = PROJETO_ROOT / "assets" / "inbox" / "imagens"
FILA_PATH    = PLANS_DIR / "ai_video_generation_queue.json"

CENAS_ESSENCIAIS = ["dor", "demo", "resultado", "close", "cta"]


# =================================================================
# PLANO + CENAS FALTANTES
# =================================================================

def carregar_plano_mais_recente(produto: str) -> Optional[dict]:
    """Lê plano_<slug>_<TS>.json mais recente (mesmo padrão dos outros agentes)."""
    if not PLANS_DIR.exists():
        return None
    import re
    slug = slugificar_produto(produto)
    re_ts = re.compile(r"_(\d{8})_(\d{6})$")
    candidatos = []
    for f in PLANS_DIR.glob("plano_*.json"):
        if "_resultado" in f.stem or f.name == "ultimo_plano.json":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if slugificar_produto(data.get("produto") or data.get("nome") or "") != slug:
            continue
        m = re_ts.search(f.stem.replace("plano_", "", 1))
        ts = None
        if m:
            try:
                ts = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            except Exception:
                pass
        if ts is None:
            try:
                ts = datetime.fromtimestamp(f.stat().st_mtime)
            except Exception:
                continue
        candidatos.append((ts, f, data))
    if not candidatos:
        return None
    candidatos.sort(key=lambda x: x[0], reverse=True)
    _, path, data = candidatos[0]
    data["_plano_path"] = str(path)
    return data


def detectar_cenas_faltantes(produto: str) -> tuple[list[str], dict]:
    """Cenas essenciais que ainda não têm clipe (reusa verificar_assets_produto)."""
    status = verificar_assets_produto(produto)
    cobertura = status.get("cobertura_propositos") or {}
    faltantes = [c for c in CENAS_ESSENCIAIS if cobertura.get(c, 0) == 0]
    return faltantes, status


def _resolver_nicho(produto: str, plano: Optional[dict]) -> str:
    if plano:
        n = plano.get("nicho")
        if isinstance(n, str) and n.strip() and n.strip() != "?":
            return n.strip()
    if _COPY_OK:
        return _inferir_nicho(produto, plano) or ""
    return ""


# =================================================================
# FILA DE GERAÇÃO
# =================================================================

def _ler_fila() -> dict:
    if not FILA_PATH.exists():
        return {"entradas": []}
    try:
        return json.loads(FILA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"entradas": []}


def _salvar_fila(fila: dict):
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        FILA_PATH.write_text(
            json.dumps(fila, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
    except Exception as e:
        log.warning(f"Falha ao salvar fila: {e}")


def _registrar_na_fila(produto: str, slug: str, nicho: str,
                        provider: str, itens_cena: list[dict]):
    """Adiciona/atualiza entrada do produto na fila de geração."""
    fila = _ler_fila()
    # Remove entrada anterior do mesmo produto+provider (regenera)
    fila["entradas"] = [
        e for e in fila.get("entradas", [])
        if not (e.get("slug") == slug and e.get("provider") == provider)
    ]
    fila["entradas"].append({
        "produto":   produto,
        "slug":      slug,
        "nicho":     nicho,
        "provider":  provider,
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "cenas":     itens_cena,
    })
    _salvar_fila(fila)


# =================================================================
# PIPELINE PRINCIPAL
# =================================================================

def _pedir_aprovacao(cena: str, item: dict, callback=None) -> bool:
    """
    Pede aprovação humana de uma cena antes de seguir pra próxima.

    - Se callback fornecido (ex: Supervisor), usa ele.
    - Senão, pergunta no terminal (input interativo).
    - Se não há terminal (daemon/redirect), aprova só se validação técnica passou.
    """
    val = item.get("validacao") or {}
    if callback is not None:
        try:
            return bool(callback(cena, item))
        except Exception:
            return False

    arquivo = item.get("arquivo", "?")
    print("\n" + "─" * 60)
    print(f"  🎬 REVISÃO DA CENA '{cena}'")
    print(f"     Arquivo: {arquivo}")
    if val:
        print(f"     Técnico: {val.get('largura')}x{val.get('altura')}, "
              f"{val.get('duracao')}s, "
              f"{'vertical ✅' if val.get('vertical') else 'NÃO vertical ⚠️'}")
        if val.get("problemas"):
            print(f"     ⚠️  Problemas técnicos:")
            for p in val["problemas"]:
                print(f"        • {p}")
    print(f"\n  👉 Abra o vídeo e confira se está bom (sem cena bizarra).")
    print("─" * 60)
    try:
        resp = input("  Aprovar e gerar a próxima cena? [s/N]: ").strip().lower()
        return resp in ("s", "sim", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        # Sem terminal interativo: aprova só se técnico OK
        print("  (sem terminal interativo — aprovando só se validação técnica passou)")
        return bool(val.get("ok"))


def gerar_assets_ia(produto: str,
                     provider_nome: str = "manual",
                     dry_run: bool = False,
                     forcar_todas_cenas: bool = False,
                     revisar: bool = False,
                     max_cenas: int = 0,
                     aprovar_callback=None) -> dict:
    """
    Gera (ou enfileira) cenas IA pras cenas faltantes do produto.

    Args:
        produto:             nome do produto
        provider_nome:       manual | heygen | pixverse
        dry_run:             só mostra prompts, não gera/enfileira
        forcar_todas_cenas:  ignora cobertura e gera as 5 cenas

    Returns: relatório completo.
    """
    log.info("=" * 60)
    log.info(f"🎨 CREATIVE ASSET GENERATOR — '{produto}'")
    log.info(f"   Provider: {provider_nome} | Modo: {'DRY-RUN' if dry_run else 'REAL'}")
    log.info("=" * 60)

    slug = slugificar_produto(produto)
    plano = carregar_plano_mais_recente(produto)
    nicho = _resolver_nicho(produto, plano)
    if nicho:
        log.info(f"   📋 Nicho: '{nicho}'")
    else:
        log.warning(f"   ⚠️  Nicho não detectado — prompts usam fallback genérico")

    # Cenas a gerar
    if forcar_todas_cenas:
        cenas = list(CENAS_ESSENCIAIS)
        status = verificar_assets_produto(produto)
    else:
        cenas, status = detectar_cenas_faltantes(produto)

    score_inicial = status.get("score_prontidao", 0)
    log.info(f"   📊 Status: {status.get('status', '?')} (score {score_inicial}/100)")
    log.info(f"   🎬 Cenas a gerar: {cenas or 'nenhuma (já cobertas)'}")

    resultado = {
        "produto":         produto,
        "slug":            slug,
        "nicho":           nicho,
        "provider":        provider_nome,
        "score_inicial":   score_inicial,
        "cenas_alvo":      cenas,
        "itens":           [],
        "fila_salva":      False,
        "gerados_ok":      0,
        "enfileirados":    0,
    }

    if not cenas:
        log.info(f"\n✅ Todas as cenas já cobertas — nada a gerar")
        resultado["mensagem"] = "Nenhuma cena faltante"
        return resultado

    # Resolve provider — com CASCATA (grok → pixverse → heygen → manual)
    if (provider_nome or "").lower() == "auto":
        # Modo auto: usa a cascata direto (1º provider de IA disponível)
        disp = providers_disponiveis_da_cascata()
        provider = obter_provider_cascata()
        if provider.nome == "manual":
            log.warning(f"   → 'auto': nenhum provider de IA disponível "
                        f"(cascata: {CASCATA_VIDEO}) — modo 'manual' (prompts + fila)")
        else:
            log.info(f"   🔁 'auto' → cascata escolheu '{provider.nome}' "
                     f"(disponíveis: {disp})")
        resultado["provider"] = provider.nome
        resultado["fallback_de"] = "auto"
    else:
        provider = obter_provider(provider_nome)
        if not provider.disponivel() and provider.nome != "manual":
            log.warning(f"   ⚠️  Provider '{provider.nome}' indisponível: "
                        f"{provider.motivo_indisponivel()}")
            disp = providers_disponiveis_da_cascata()
            provider = obter_provider_cascata(preferido=provider_nome)
            if provider.nome == "manual":
                log.warning(f"   → nenhum provider de IA disponível (cascata: {CASCATA_VIDEO}) "
                            f"— caindo pro modo 'manual' (prompts + fila)")
            else:
                log.info(f"   🔁 Cascata: usando '{provider.nome}' "
                         f"(disponíveis: {disp})")
            resultado["provider"] = provider.nome
            resultado["fallback_de"] = provider_nome

    # Gera prompts visuais (uma vez)
    prompts_por_cena, categoria = construir_prompts_todas_cenas(produto, cenas, nicho)
    log.info(f"   🎨 Categoria visual: {categoria}")

    # HeyGen fala um ROTEIRO (texto), não um prompt visual.
    # Pega os textos de copy se o provider for heygen.
    roteiros_por_cena = {}
    if provider.nome == "heygen" and _COPY_OK:
        try:
            copy_r = _escolher_copy(produto=produto, plano=plano, cenas=cenas)
            copy_r.pop("_fontes", None); copy_r.pop("_categoria_detectada", None)
            roteiros_por_cena = copy_r
        except Exception:
            pass

    # Limite de cenas (controle de custo)
    if max_cenas and max_cenas > 0:
        cenas = cenas[:max_cenas]
        log.info(f"   🔢 Limite de cenas nesta execução: {max_cenas}")

    INBOX_VIDEOS.mkdir(parents=True, exist_ok=True)
    output_dir = INBOX_VIDEOS

    itens_fila = []
    interrompido = False
    for i, cena in enumerate(cenas, 1):
        prompt_visual = prompts_por_cena[cena]
        # HeyGen usa roteiro falado; outros usam prompt visual
        if provider.nome == "heygen" and roteiros_por_cena.get(cena):
            conteudo = roteiros_por_cena[cena]
            tipo_conteudo = "roteiro"
        else:
            conteudo = prompt_visual
            tipo_conteudo = "prompt visual"

        ext = ".mp4" if provider.tipo_saida == "video" else ".jpg"
        arquivo_esperado = f"ia_{cena}_{slug}{ext}"

        log.info(f"\n[{i}/{len(cenas)}] 🎬 Cena '{cena}' ({tipo_conteudo})")
        log.info(f"   {conteudo[:120]}{'...' if len(conteudo) > 120 else ''}")

        # CASCATA POR CENA: tenta o provider escolhido; se for de IA e falhar
        # (erro de API, não no_credentials), tenta o próximo da cascata NA MESMA
        # cena. Assim Grok falhar não aborta tudo — cai pro PixVerse/HeyGen.
        r = provider.gerar(prompt=conteudo, cena=cena, produto=produto,
                            arquivo_esperado=arquivo_esperado,
                            output_dir=output_dir, dry_run=dry_run)
        provider_usado = provider.nome

        if (not dry_run and not r.get("sucesso")
                and r.get("status") == "erro" and provider.nome in CASCATA_VIDEO):
            # loga o erro do provider que falhou ANTES de tentar o próximo
            log.warning(f"   ❌ {r.get('mensagem', '?')}")
            log.warning(f"      erro: {r.get('erro', '?')}")
            # tenta os próximos da cascata, na ordem, pulando o que já falhou
            idx_atual = CASCATA_VIDEO.index(provider.nome)
            for prox_nome in CASCATA_VIDEO[idx_atual + 1:]:
                prox = obter_provider(prox_nome)
                if not prox.disponivel():
                    continue
                ext_p = ".mp4" if prox.tipo_saida == "video" else ".jpg"
                arq_esp_p = f"ia_{cena}_{slug}{ext_p}"
                log.info(f"   🔁 Cascata: tentando '{prox_nome}' pra cena '{cena}'")
                r = prox.gerar(prompt=conteudo, cena=cena, produto=produto,
                               arquivo_esperado=arq_esp_p,
                               output_dir=output_dir, dry_run=dry_run)
                provider_usado = prox_nome
                arquivo_esperado = arq_esp_p
                if r.get("sucesso") or r.get("status") != "erro":
                    break
                log.warning(f"   ❌ '{prox_nome}' também falhou: {r.get('erro', '?')}")

        item = {
            "cena":             cena,
            "prompt":           conteudo,
            "tipo":             r.get("tipo"),
            "status":           r.get("status"),
            "provider_usado":   provider_usado,
            "arquivo_esperado": arquivo_esperado,
            "arquivo":          r.get("arquivo"),
            "mensagem":         r.get("mensagem", ""),
            "erro":             r.get("erro"),
            "validacao":        None,
        }

        if r.get("sucesso"):
            resultado["gerados_ok"] += 1
            log.info(f"   ✅ Gerado: {r.get('arquivo')}")
            log.info(f"      {r.get('mensagem', '')}")

            # ── VALIDAÇÃO TÉCNICA da cena ──
            arq = Path(r["arquivo"]) if r.get("arquivo") else None
            if arq:
                dur_esperada = getattr(provider, "duration", None)
                val = validar_video(arq, dur_esperada=dur_esperada, vertical=True)
                item["validacao"] = val
                if val["ok"]:
                    log.info(f"      🔍 Validação: OK ({val['largura']}x{val['altura']}, "
                             f"{val['duracao']}s, vertical)")
                else:
                    log.warning(f"      ⚠️  Validação encontrou problemas:")
                    for p in val["problemas"]:
                        log.warning(f"         • {p}")

            # ── CHECKPOINT DE APROVAÇÃO antes da próxima cena ──
            # Só faz sentido se há mais cenas pela frente e modo revisar ativo
            if revisar and i < len(cenas):
                aprovado = _pedir_aprovacao(cena, item, aprovar_callback)
                if not aprovado:
                    log.warning(f"   🛑 Cena '{cena}' NÃO aprovada — parando antes de gastar "
                                f"crédito nas próximas {len(cenas) - i} cena(s)")
                    item["aprovado"] = False
                    resultado["itens"].append(item)
                    interrompido = True
                    break
                else:
                    item["aprovado"] = True
                    log.info(f"   👍 Cena '{cena}' aprovada — seguindo")
        elif r.get("status") == "queued":
            resultado["enfileirados"] += 1
            itens_fila.append(item)
            log.info(f"   📋 Enfileirado como '{arquivo_esperado}'")
        elif r.get("status") == "dry_run":
            log.info(f"   🔍 [dry-run]")
        elif r.get("status") == "no_credentials":
            log.warning(f"   ⚠️  {r.get('mensagem')}")
        else:
            log.warning(f"   ❌ {r.get('mensagem', '?')}")
            if r.get("erro"):
                log.warning(f"      erro: {r.get('erro')}")
            # Cascata já foi tentada acima; se chegou aqui, todos falharam.
            if provider_usado in ("pixverse", "heygen", "grok") and not dry_run:
                log.warning(f"   🛑 Todos os providers de IA disponíveis falharam "
                            f"nesta cena — parando pra você verificar")
                resultado["itens"].append(item)
                interrompido = True
                break

        resultado["itens"].append(item)

    resultado["interrompido"] = interrompido

    # Salva fila se houve enfileirados (modo manual)
    if itens_fila and not dry_run:
        _registrar_na_fila(produto, slug, nicho, resultado["provider"], itens_fila)
        resultado["fila_salva"] = True
        log.info(f"\n💾 Fila salva: {FILA_PATH}")

    # Resumo
    log.info(f"\n{'═' * 60}")
    log.info(f"🏁 RESULTADO")
    log.info(f"   Cenas alvo: {len(cenas)}")
    log.info(f"   Gerados (API): {resultado['gerados_ok']}")
    log.info(f"   Enfileirados (manual): {resultado['enfileirados']}")
    if resultado["fila_salva"]:
        log.info(f"   📋 Próximo passo: gere os prompts na plataforma, baixe e salve")
        log.info(f"      em assets/inbox/videos/ com os nomes 'ia_<cena>_{slug}.mp4'")
        log.info(f"      depois rode: python -m agents.asset_hunter_agent --produto \"{produto}\" --mover")
    log.info(f"{'═' * 60}")

    return resultado


def imprimir_fila_atual():
    """Mostra a fila de geração pendente (pra você saber o que gerar)."""
    fila = _ler_fila()
    entradas = fila.get("entradas", [])
    print("=" * 70)
    print(f"  📋 FILA DE GERAÇÃO IA — {len(entradas)} produto(s)")
    print("=" * 70)
    if not entradas:
        print("  (vazia)")
        return
    for e in entradas:
        print(f"\n  🎬 {e['produto']} [{e.get('provider', '?')}] — {e.get('gerado_em', '?')[:19]}")
        print(f"     nicho: {e.get('nicho', '?')}")
        for item in e.get("cenas", []):
            print(f"\n     ── cena '{item['cena']}' → salvar como: {item['arquivo_esperado']}")
            print(f"        PROMPT: {item['prompt']}")
    print("\n" + "=" * 70)


# =================================================================
# CLI
# =================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Creative Asset Generator — gera cenas IA sob medida pro produto"
    )
    parser.add_argument("--produto", default="",
                        help="Nome do produto (ou slug)")
    parser.add_argument("--provider", default="manual",
                        help="manual | heygen | pixverse (default: manual)")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="Mostra prompts sem gerar/enfileirar")
    parser.add_argument("--forcar-todas-cenas", action="store_true",
                        dest="forcar_todas",
                        help="Gera as 5 cenas mesmo se já cobertas")
    parser.add_argument("--listar-providers", action="store_true",
                        dest="listar_prov",
                        help="Lista providers e disponibilidade")
    parser.add_argument("--ver-fila", action="store_true", dest="ver_fila",
                        help="Mostra a fila de geração pendente")
    parser.add_argument("--revisar", action="store_true", dest="revisar",
                        help="Para após cada cena pra você aprovar antes de gastar "
                             "crédito na próxima (recomendado pra pixverse/heygen)")
    parser.add_argument("--max-cenas", type=int, default=0, dest="max_cenas",
                        help="Limita quantas cenas gerar nesta execução (controle de custo)")
    args = parser.parse_args()

    if args.listar_prov:
        print("=" * 60)
        print("  🎨 PROVIDERS DE GERAÇÃO IA")
        print("=" * 60)
        for p in listar_providers():
            marca = "✅" if p["disponivel"] else "❌"
            print(f"  {marca} {p['nome']:12s} ({p['tipo']}) — {p['descricao']}")
            if not p["disponivel"] and p["motivo"]:
                print(f"        motivo: {p['motivo']}")
        print("=" * 60)
        return 0

    if args.ver_fila:
        imprimir_fila_atual()
        return 0

    if not args.produto:
        parser.error("--produto é obrigatório (ou use --listar-providers / --ver-fila)")

    log.info("=" * 60)
    log.info(f"🎨 CREATIVE ASSET GENERATOR v1")
    log.info("=" * 60)

    r = gerar_assets_ia(
        produto=args.produto,
        provider_nome=args.provider,
        dry_run=args.dry_run,
        forcar_todas_cenas=args.forcar_todas,
        revisar=args.revisar,
        max_cenas=args.max_cenas,
    )

    # Salva relatório
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        (PLANS_DIR / "creative_generator_resultado.json").write_text(
            json.dumps(r, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass

    if r.get("gerados_ok", 0) > 0 or r.get("enfileirados", 0) > 0:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())