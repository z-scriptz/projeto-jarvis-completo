# agents/daemon_maestro.py
# MAESTRO 24/7 DO JARVIS — o daemon que faz tudo rodar sozinho na VPS.
#
# Um processo só, em loop, que coordena as três frentes EM SÉRIE (nunca
# paralelo solto, pra não tomar ban do Telegram nem corromper arquivos):
#
#   CICLO DE DESCOBERTA (a cada N horas):
#     alterna radar ↔ hunter → abastece a esteira com produtos + vídeos
#
#   CICLO DE PRODUÇÃO (sob teto de gasto):
#     gera vídeos até o limite diário do Fal; premium só pros campeões
#
#   CICLO DE POSTAGEM (nos horários definidos):
#     posta 1 vídeo pronto por horário, automático
#
# TRAVAS DE SEGURANÇA:
#   - Lock de processo: nunca roda dois maestros sobrepostos
#   - Teto diário de vídeos (Fal): conta gasto por dia, para no limite
#   - Rate limit Telegram: descoberta só de N em N horas, 1 fonte por ciclo
#   - Janela de horário pra postar (não posta de madrugada)
#   - Histórico persistente: sabe o que já postou, nunca repete
#
# CLI:
#   python -m agents.daemon_maestro                 # roda o daemon (loop infinito)
#   python -m agents.daemon_maestro --once          # roda 1 ciclo e sai (teste)
#   python -m agents.daemon_maestro --dry-run       # simula tudo, não gasta nada
#   python -m agents.daemon_maestro --status        # mostra estado e sai
#   python -m agents.daemon_maestro --so-postar     # só roda o ciclo de postagem
#   python -m agents.daemon_maestro --so-descoberta # só roda descoberta
#   python -m agents.daemon_maestro --so-producao   # só roda produção

import os
import sys
import json
import time
import signal
import argparse
from pathlib import Path
from datetime import datetime, date

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("daemon_maestro")

RAIZ = Path(__file__).parent.parent
PLANS_DIR = RAIZ / "shared" / "content_plans"
CONFIG_PATH = PLANS_DIR / "agendador_config.json"
HIST_PATH = PLANS_DIR / "agendador_historico.json"
ESTADO_PATH = PLANS_DIR / "daemon_estado.json"
LOCK_PATH = PLANS_DIR / "daemon.lock"
PRONTO_DIR = RAIZ / "pronto_para_postar"


# =====================================================================
# CONFIG — defaults + merge com o arquivo (retrocompatível)
# =====================================================================

DEFAULTS = {
    # ── Descoberta ──
    "descoberta_intervalo_horas": 3,
    "descoberta_fontes":          ["radar", "hunter"],   # alterna entre elas
    "descoberta_lote":            3,
    "hunter_canais":              [],                      # ["@canal1", "@canal2"]
    "radar_grupos_arquivo":       "grupos.txt",
    "radar_limite":               30,

    # ── Descoberta de grupos (auto-alimenta radar + hunter, manhã/noite) ──
    "grupos_descoberta_ativa":    True,
    "grupos_descoberta_horarios": ["08:30", "20:30"],      # manhã e noite
    "grupos_descoberta_max":      2,                        # novos grupos por vez
    "grupos_descoberta_auto_add": True,   # False = só sugere (grupos_descobertos.json)

    # ── Produção (teto de gasto Fal) ──
    "producao_max_videos_dia":    20,
    "producao_max_downloads":     10,        # assets baixados por produto (autopilot)
    "producao_premium_campeoes":  True,
    "producao_premium_comissao_min": 15.0,   # R$ — acima disso vira premium
    "auto_repor":                 True,
    "repor_quando_sobrar":        2,
    "repor_quantidade":           4,

    # ── Postagem ──
    "horarios":                   ["09:00", "14:00", "17:00", "21:00"],
    "plataformas":                ["youtube"],
    "publico":                    True,
    # 1 vídeo de CADA conta por slot (balanceado), com teto diário por conta.
    # OFF por padrão = comportamento antigo (1 vídeo/slot, total). Ligue e ajuste
    # o teto pra abrir a torneira em rampa (2 → 3 → 4-5/conta/dia).
    "post_por_conta":             False,
    "max_posts_por_conta_dia":    4,
    # TikTok via API oficial (Content Posting API). OFF até o app ser aprovado —
    # ligue depois da aprovação (+ conta pública + credenciais de produção no .env).
    "postar_tiktok":              False,
    "tolerancia_min":             10,
    "janela_inicio":              "08:00",   # não posta antes
    "janela_fim":                 "23:00",   # não posta depois

    # ── Loop ──
    "intervalo_check_seg":        60,
}


def carregar_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            user_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            # ignora chaves de comentário (_xxx)
            for k, v in user_cfg.items():
                if not k.startswith("_"):
                    cfg[k] = v
            log.info(f"⚙️  Config carregada de {CONFIG_PATH.name}")
        except Exception as e:
            log.warning(f"⚠️  Erro lendo config ({e}); usando defaults")
    else:
        log.info("⚙️  Sem agendador_config.json — usando defaults")
    return cfg


# =====================================================================
# ESTADO DO DAEMON — contadores diários + ciclo
# =====================================================================

def _carregar_estado() -> dict:
    if ESTADO_PATH.exists():
        try:
            return json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"estado corrompido ({e}); recomeçando")
    return {
        "videos_hoje": 0,
        "data_contador": str(date.today()),
        "ciclo_descoberta": 0,
        "ultima_descoberta": None,
        "ultima_producao": None,
    }


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


def _resetar_contador_se_novo_dia(estado: dict):
    """Zera o contador de vídeos quando vira o dia."""
    hoje = str(date.today())
    if estado.get("data_contador") != hoje:
        log.info(f"📅 Novo dia ({hoje}) — zerando contador de vídeos")
        estado["videos_hoje"] = 0
        estado["data_contador"] = hoje
        _salvar_estado(estado)


# =====================================================================
# HISTÓRICO — o que já foi postado (retrocompatível com o seu arquivo)
# =====================================================================

def _carregar_historico() -> dict:
    if HIST_PATH.exists():
        try:
            h = json.loads(HIST_PATH.read_text(encoding="utf-8"))
            h.setdefault("por_dia", {})
            h.setdefault("postados", [])
            return h
        except Exception as e:
            log.warning(f"histórico corrompido ({e}); recomeçando")
    return {"por_dia": {}, "postados": []}


def _salvar_historico(hist: dict):
    tmp = HIST_PATH.with_suffix(".json.tmp")
    try:
        HIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False, indent=2)
        tmp.replace(HIST_PATH)
    except Exception as e:
        log.error(f"falha ao salvar histórico: {e}")
        try:
            tmp.unlink()
        except Exception:
            pass


# =====================================================================
# LOCK DE PROCESSO — garante 1 maestro só
# =====================================================================

def _adquirir_lock() -> bool:
    """Cria o lock. Se já existe e o PID está vivo, recusa."""
    if LOCK_PATH.exists():
        try:
            pid_antigo = int(LOCK_PATH.read_text().strip())
            # Checa se o processo ainda vive
            os.kill(pid_antigo, 0)
            log.error(f"🔒 Outro maestro já roda (PID {pid_antigo}). Abortando.")
            return False
        except (ProcessLookupError, ValueError):
            log.warning("🔓 Lock órfão encontrado (processo morto) — assumindo")
        except PermissionError:
            log.error("🔒 Lock pertence a outro processo vivo. Abortando.")
            return False

    try:
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOCK_PATH.write_text(str(os.getpid()))
        return True
    except Exception as e:
        log.error(f"falha ao criar lock: {e}")
        return False


def _liberar_lock():
    try:
        if LOCK_PATH.exists():
            LOCK_PATH.unlink()
    except Exception:
        pass


# =====================================================================
# HELPERS DE HORÁRIO
# =====================================================================

def _hora_para_min(hhmm: str) -> int:
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return -1


def _agora_min() -> int:
    agora = datetime.now()
    return agora.hour * 60 + agora.minute


def _dentro_da_janela(cfg: dict) -> bool:
    ini = _hora_para_min(cfg["janela_inicio"])
    fim = _hora_para_min(cfg["janela_fim"])
    agora = _agora_min()
    return ini <= agora <= fim


def _horario_devido(cfg: dict, hist: dict) -> str | None:
    """
    Retorna o horário que está 'na hora' agora (dentro da tolerância) e que
    ainda NÃO foi postado hoje. None se nenhum.
    """
    agora = _agora_min()
    tol = cfg["tolerancia_min"]
    hoje = str(date.today())
    postados_hoje = hist["por_dia"].get(hoje, {})

    for hhmm in cfg["horarios"]:
        alvo = _hora_para_min(hhmm)
        if alvo < 0:
            continue
        # 'na hora' = entre alvo e alvo+tolerância
        if alvo <= agora <= alvo + tol and hhmm not in postados_hoje:
            return hhmm
    return None


# =====================================================================
# CICLO 1 — DESCOBERTA (radar ↔ hunter alternando)
# =====================================================================

def _precisa_descobrir(cfg: dict, estado: dict) -> bool:
    """True se já passou o intervalo desde a última descoberta."""
    ultima = estado.get("ultima_descoberta")
    if not ultima:
        return True
    try:
        dt_ultima = datetime.fromisoformat(ultima)
        horas = (datetime.now() - dt_ultima).total_seconds() / 3600
        return horas >= cfg["descoberta_intervalo_horas"]
    except Exception:
        return True


def ciclo_descoberta(cfg: dict, estado: dict, dry_run: bool) -> dict:
    """
    Roda 1 fonte de descoberta (alterna radar↔hunter por ciclo).
    Abastece a esteira com produtos novos (+ vídeo, se hunter).
    """
    fontes = cfg["descoberta_fontes"] or ["radar"]
    idx = estado.get("ciclo_descoberta", 0) % len(fontes)
    fonte = fontes[idx]

    log.info("─" * 60)
    log.info(f"🔍 CICLO DESCOBERTA — fonte: {fonte} "
             f"(ciclo #{estado.get('ciclo_descoberta', 0)})")

    resultado = {"fonte": fonte, "ok": False}

    try:
        from agents.orchestrator import rodar_lote

        if fonte == "hunter":
            canais = cfg.get("hunter_canais", [])
            if not canais:
                log.warning("   ⚠️  hunter sem canais configurados (hunter_canais) "
                            "— pulando pro radar neste ciclo")
                fonte = "radar"
            else:
                # Alterna entre os canais do hunter também
                canal_idx = (estado.get("ciclo_descoberta", 0) // len(fontes)) % len(canais)
                canal = canais[canal_idx]
                log.info(f"   🎯 Hunter no canal: {canal}")
                res = rodar_lote(
                    cfg["descoberta_lote"], dry_run=dry_run,
                    sem_postar=True,  # daemon posta no ciclo de postagem
                    fonte="hunter", canal_hunter=canal,
                )
                resultado["ok"] = res.get("ok", False)
                resultado["detalhe"] = res

        if fonte == "radar":
            res = rodar_lote(
                cfg["descoberta_lote"], dry_run=dry_run,
                sem_postar=True,
                fonte="radar",
                grupos_arquivo=cfg.get("radar_grupos_arquivo", ""),
                radar_limite=cfg.get("radar_limite", 30),
            )
            resultado["ok"] = res.get("ok", False)
            resultado["detalhe"] = res

    except Exception as e:
        log.error(f"   ❌ Descoberta falhou: {e}")
        resultado["erro"] = str(e)

    # Avança o ciclo e marca o tempo
    estado["ciclo_descoberta"] = estado.get("ciclo_descoberta", 0) + 1
    estado["ultima_descoberta"] = datetime.now().isoformat()
    _salvar_estado(estado)

    return resultado


# =====================================================================
# CICLO 1.5 — DESCOBERTA DE GRUPOS (auto-alimenta radar + hunter)
# =====================================================================

def _horario_devido_grupos(cfg: dict, estado: dict) -> "str | None":
    """Horário de descoberta de grupos 'na hora' e ainda não feito hoje."""
    if not cfg.get("grupos_descoberta_ativa", True):
        return None
    horarios = cfg.get("grupos_descoberta_horarios") or []
    if not horarios:
        return None
    hoje = str(date.today())
    reg = estado.get("grupos_desc_feitos") or {}
    if reg.get("data") != hoje:
        reg = {"data": hoje, "horarios": []}
        estado["grupos_desc_feitos"] = reg
    agora = _agora_min()
    tol = cfg.get("tolerancia_min", 10)
    for hhmm in horarios:
        alvo = _hora_para_min(hhmm)
        if alvo >= 0 and alvo <= agora <= alvo + tol and hhmm not in reg["horarios"]:
            return hhmm
    return None


def ciclo_descoberta_grupos(cfg: dict, estado: dict, dry_run: bool,
                            forcar: bool = False) -> dict:
    """
    Nos horários definidos (manhã/noite), acha novos canais de achadinhos e os
    adiciona ao radar (grupos.txt) e ao hunter (hunter_canais). `forcar` ignora
    o horário (uso manual via --so-grupos).
    """
    resultado = {"rodou": False}

    horario = "manual" if forcar else _horario_devido_grupos(cfg, estado)
    if not horario:
        return resultado  # não é a hora ainda (silencioso)

    log.info("─" * 60)
    log.info(f"🛰️  CICLO DESCOBERTA DE GRUPOS — {horario}")

    try:
        from integrations.descobridor_grupos import descobrir_grupos
    except Exception as e:
        log.error(f"   ❌ descobridor indisponível: {e}")
        resultado["erro"] = str(e)
        return resultado

    max_novos = int(cfg.get("grupos_descoberta_max", 2))
    auto_add = bool(cfg.get("grupos_descoberta_auto_add", True))
    try:
        r = descobrir_grupos(max_novos=max_novos, auto_add=auto_add, dry_run=dry_run)
        resultado.update(rodou=True, detalhe=r)
    except Exception as e:
        log.error(f"   ❌ descoberta de grupos falhou: {e}")
        resultado["erro"] = str(e)

    # marca o horário como feito hoje (mesmo sem achar nada) pra não repetir
    if not forcar:
        reg = estado.get("grupos_desc_feitos") or {"data": str(date.today()),
                                                    "horarios": []}
        if horario not in reg["horarios"]:
            reg["horarios"].append(horario)
        estado["grupos_desc_feitos"] = reg
        _salvar_estado(estado)

    return resultado


# =====================================================================
# CICLO 2 — PRODUÇÃO (sob teto de gasto Fal)
# =====================================================================

def _contar_prontos() -> int:
    """Conta quantos vídeos prontos existem em pronto_para_postar/."""
    if not PRONTO_DIR.exists():
        return 0
    return sum(1 for p in PRONTO_DIR.iterdir()
               if p.is_dir() and (p / "video.mp4").exists())


def ciclo_producao(cfg: dict, estado: dict, dry_run: bool) -> dict:
    """
    Produz vídeos até o teto diário. Premium só pros campeões de comissão.
    Só repõe se a fila de prontos estiver baixa (auto_repor).
    """
    _resetar_contador_se_novo_dia(estado)

    log.info("─" * 60)
    log.info(f"🎬 CICLO PRODUÇÃO — vídeos hoje: {estado['videos_hoje']}/"
             f"{cfg['producao_max_videos_dia']}")

    resultado = {"produzidos": 0, "pulou": False}

    # Teto diário atingido?
    if estado["videos_hoje"] >= cfg["producao_max_videos_dia"]:
        log.info("   🛑 Teto diário de vídeos atingido — produção pausada até amanhã")
        resultado["pulou"] = True
        resultado["motivo"] = "teto_diario"
        return resultado

    # Precisa repor? (só produz se a fila de prontos está baixa)
    if cfg["auto_repor"]:
        prontos = _contar_prontos()
        if prontos > cfg["repor_quando_sobrar"]:
            log.info(f"   ℹ️  {prontos} vídeo(s) prontos (> {cfg['repor_quando_sobrar']}) "
                     f"— não precisa repor agora")
            resultado["pulou"] = True
            resultado["motivo"] = "fila_cheia"
            return resultado
        log.info(f"   📉 Só {prontos} prontos — repondo a esteira")

    # Quantos produzir: respeita o teto diário restante
    restante_dia = cfg["producao_max_videos_dia"] - estado["videos_hoje"]
    quantidade = min(cfg["repor_quantidade"], restante_dia)

    log.info(f"   🎯 Produzindo até {quantidade} vídeo(s) "
             f"(premium p/ campeões: {cfg['producao_premium_campeoes']})")

    if dry_run:
        log.info("   🧪 dry-run: produção simulada")
        resultado["dry_run"] = True
        return resultado

    # Produz consumindo da fila validada (campeões viram premium)
    try:
        produzidos = _produzir_lote(cfg, estado, quantidade)
        resultado["produzidos"] = produzidos
        estado["videos_hoje"] += produzidos
        estado["ultima_producao"] = datetime.now().isoformat()
        _salvar_estado(estado)
        log.info(f"   ✅ {produzidos} vídeo(s) produzido(s) "
                 f"(total hoje: {estado['videos_hoje']})")
    except Exception as e:
        log.error(f"   ❌ Produção falhou: {e}")
        resultado["erro"] = str(e)

    return resultado


def _produzir_lote(cfg: dict, estado: dict, quantidade: int) -> int:
    """
    Produz `quantidade` vídeos a partir dos produtos da fila usando o pipeline
    COMPLETO do production_runner: produz + arquiva + EMPACOTA em
    pronto_para_postar/ (a esteira que o ciclo de postagem lê). O produzir()
    cru gravava só em videos/ e não abastecia a esteira → o daemon nunca
    postava. Campeões (comissão >= limite) usam premium (Kling 2.1).
    Retorna quantos foram produzidos com sucesso.
    """
    import os
    from agents.production_runner_agent import (processar_produto,
                                                _dir_saida_rodada)

    produtos = _carregar_produtos_para_produzir(quantidade)
    if not produtos:
        log.warning("   ⚠️  Nenhum produto disponível pra produzir")
        return 0

    # Uma pasta de rodada por lote (mesma convenção do production_runner.main)
    dir_rodada = _dir_saida_rodada()
    max_downloads = int(cfg.get("producao_max_downloads", 10))

    produzidos = 0
    for p in produtos:
        nome = p["nome"]
        comissao = float(p.get("comissao_valor", 0) or 0)
        premium = (cfg["producao_premium_campeoes"]
                   and comissao >= cfg["producao_premium_comissao_min"])

        # respeita o teto mesmo dentro do lote
        if estado["videos_hoje"] + produzidos >= cfg["producao_max_videos_dia"]:
            log.info("   🛑 Teto diário atingido no meio do lote — parando")
            break

        tag = "💎 PREMIUM" if premium else "📹 standard"
        log.info(f"   {tag}: '{nome}' (comissão R$ {comissao:.2f})")

        # PREMIUM via env: o production_runner roda as etapas como subprocess,
        # que HERDA o os.environ — então setar FAL_MODEL aqui propaga o modelo
        # premium pro gerador de cenas. Restauramos depois pra não vazar.
        _fal_anterior = os.environ.get("FAL_MODEL")
        if premium:
            os.environ["FAL_MODEL"] = "fal-ai/kling-video/v2.1/master/text-to-video"
        try:
            res = processar_produto(nome, max_downloads, dir_rodada)
            status = (res or {}).get("status", "")
            if status in ("video_gerado", "recuperado"):
                produzidos += 1
                log.info(f"      ✅ '{nome}': {status} → esteira: "
                         f"{res.get('pronto_para_postar') or '?'}")
            else:
                log.warning(f"      ⚠️  '{nome}': {status or 'sem status'} "
                            f"(não entrou na esteira)")
        except Exception as e:
            log.error(f"      ❌ erro produzindo '{nome}': {e}")
        finally:
            if _fal_anterior is None:
                os.environ.pop("FAL_MODEL", None)
            else:
                os.environ["FAL_MODEL"] = _fal_anterior

    return produzidos


def _carregar_produtos_para_produzir(quantidade: int) -> list:
    """
    Carrega produtos pra produzir, priorizando o relatório validado
    (validacao_fila.json — campeões primeiro). Fallback: produtos_fila.json.
    """
    # 1) Relatório validado (tem comissão real, ordena por potencial)
    relatorio = PLANS_DIR / "validacao_fila.json"
    if relatorio.exists():
        try:
            dados = json.loads(relatorio.read_text(encoding="utf-8"))
            produtos = []
            for p in dados.get("produtos", []):
                if p.get("classe") in ("mina_ouro", "ok") and p.get("produto"):
                    produtos.append({
                        "nome": p["produto"],
                        "comissao_valor": p.get("comissao_valor", 0),
                    })
            if produtos:
                # mina_ouro já vem primeiro no relatório ordenado
                return produtos[:quantidade]
        except Exception as e:
            log.warning(f"   ⚠️  erro lendo validacao_fila ({e})")

    # 2) Fallback: produtos_fila.json (sem comissão = standard)
    fila = RAIZ / "shared" / "produtos_fila.json"
    if fila.exists():
        try:
            dados = json.loads(fila.read_text(encoding="utf-8"))
            produtos = []
            for item in dados:
                nome = item.get("produto") if isinstance(item, dict) else item
                if nome:
                    produtos.append({"nome": nome, "comissao_valor": 0})
            return produtos[:quantidade]
        except Exception as e:
            log.warning(f"   ⚠️  erro lendo produtos_fila ({e})")

    return []


# =====================================================================
# CICLO 3 — POSTAGEM (nos horários definidos)
# =====================================================================

def ciclo_postagem(cfg: dict, hist: dict, dry_run: bool) -> dict:
    """
    Se estamos num horário devido e dentro da janela, posta 1 vídeo pronto.
    """
    resultado = {"postou": False}

    if not _dentro_da_janela(cfg):
        return resultado  # fora da janela, silencioso

    horario = _horario_devido(cfg, hist)
    if not horario:
        return resultado  # nenhum horário devido agora

    log.info("─" * 60)
    log.info(f"📤 CICLO POSTAGEM — horário devido: {horario}")

    # MODO BALANCEADO (opt-in): posta 1 vídeo de CADA conta neste slot, respeitando
    # o teto diário por conta. Assim beauty/tech/geral saem no mesmo ritmo.
    if cfg.get("post_por_conta"):
        teto = int(cfg.get("max_posts_por_conta_dia", 4))
        alvos = _um_por_conta_sob_teto(hist, teto)
        if not alvos:
            log.warning("   ⚠️  Nada pra postar (esteira vazia ou todas as contas "
                        f"já no teto de {teto}/dia)")
            resultado["motivo"] = "vazio_ou_teto"
            return resultado
        log.info(f"   🎯 {len(alvos)} conta(s) neste slot (teto {teto}/dia): "
                 + ", ".join(f"{c}" for _s, c in alvos))
        ok_slugs = []
        for slug, conta in alvos:
            log.info(f"   🎬 Postando '{slug}' → {conta}")
            if dry_run or _postar_produto(slug, cfg):
                ok_slugs.append(slug)
        if ok_slugs:
            _registrar_postagem(hist, horario, ok_slugs)
            resultado.update(postou=True, produtos=ok_slugs, dry_run=dry_run)
        else:
            resultado["motivo"] = "todas_plataformas_falharam"
        return resultado

    # MODO CLÁSSICO: 1 vídeo por slot (o "próximo da fila").
    produto = _proximo_para_postar(hist)
    if not produto:
        log.warning("   ⚠️  Nenhum vídeo pronto pra postar (esteira vazia)")
        resultado["motivo"] = "esteira_vazia"
        return resultado

    log.info(f"   🎬 Postando: '{produto}'")

    if dry_run:
        log.info("   🧪 dry-run: postagem simulada")
        _registrar_postagem(hist, horario, produto)
        resultado.update(postou=True, produto=produto, dry_run=True)
        return resultado

    if _postar_produto(produto, cfg):
        _registrar_postagem(hist, horario, produto)
        resultado.update(postou=True, produto=produto)
    else:
        resultado["motivo"] = "todas_plataformas_falharam"

    return resultado


def _prontos_nao_postados(hist: dict) -> list:
    """Slugs prontos (com video.mp4) que ainda não foram postados, em ordem."""
    if not PRONTO_DIR.exists():
        return []
    postados = set(hist.get("postados", []))
    out = []
    for pasta in sorted(PRONTO_DIR.iterdir()):
        if pasta.is_dir() and (pasta / "video.mp4").exists() and pasta.name not in postados:
            out.append(pasta.name)
    return out


def _proximo_para_postar(hist: dict) -> str | None:
    """Retorna o slug de um vídeo pronto que ainda não foi postado."""
    prontos = _prontos_nao_postados(hist)
    return prontos[0] if prontos else None


def _conta_do_slug(slug: str) -> str:
    """Handle/nicho da conta de um vídeo pronto (lê conta.json ao lado)."""
    try:
        d = json.loads((PRONTO_DIR / slug / "conta.json").read_text(encoding="utf-8"))
        return d.get("handle") or d.get("nicho") or "?"
    except Exception:
        return "?"


def _nicho_do_slug(slug: str) -> str:
    """Nicho da conta de um vídeo pronto (p/ mapear a conta TikTok certa)."""
    try:
        d = json.loads((PRONTO_DIR / slug / "conta.json").read_text(encoding="utf-8"))
        return (d.get("nicho") or "").strip().lower()
    except Exception:
        return ""


def _postados_hoje_por_conta(hist: dict) -> dict:
    """{conta: nº postado HOJE} — derivado do histórico do dia (aceita formato
    antigo string e o novo lista)."""
    hoje = str(date.today())
    cont = {}
    for v in hist.get("por_dia", {}).get(hoje, {}).values():
        for slug in (v if isinstance(v, list) else [v]):
            c = _conta_do_slug(slug)
            cont[c] = cont.get(c, 0) + 1
    return cont


def _um_por_conta_sob_teto(hist: dict, teto: int) -> list:
    """1 vídeo pronto de CADA conta que ainda não bateu o teto diário. Ordem estável."""
    hoje_cont = _postados_hoje_por_conta(hist)
    escolhidos, vistas = [], set()
    for slug in _prontos_nao_postados(hist):
        c = _conta_do_slug(slug)
        if c in vistas:                       # já peguei 1 dessa conta neste slot
            continue
        if hoje_cont.get(c, 0) >= teto:       # conta já bateu o teto de hoje
            continue
        escolhidos.append((slug, c))
        vistas.add(c)
    return escolhidos


def _postar_produto(produto: str, cfg: dict) -> bool:
    """Posta 1 vídeo em todas as plataformas configuradas. True se alguma deu certo."""
    try:
        from agents.publish_guard import publicar_com_garantia
    except Exception as e:
        log.error(f"   ❌ Não consegui importar publish_guard: {e}")
        return False
    ok = False
    for plataforma in cfg["plataformas"]:
        r = publicar_com_garantia(plataforma, produto, plano=None, publico=cfg["publico"])
        if r.get("sucesso"):
            ok = True
        elif r.get("pulado"):
            log.info(f"   ⏭️  {plataforma} pulado (sem uploader ainda)")
    # TikTok via API oficial (Content Posting API) — gated até o app ser aprovado.
    # Liga com "postar_tiktok": true no config (+ conta pública + creds de produção).
    if cfg.get("postar_tiktok"):
        try:
            import tiktok_poster
            tr = tiktok_poster.postar_video(produto, nicho=_nicho_do_slug(produto))
            if tr.get("ok"):
                ok = True
                log.info(f"   🎵 TikTok: {tr.get('publish_id')} ({tr.get('privacidade')})")
            else:
                log.warning(f"   ⚠️  TikTok falhou: {tr.get('erro')}")
        except Exception as e:
            log.warning(f"   ⚠️  TikTok poster indisponível: {str(e)[:80]}")
    return ok


def _registrar_postagem(hist: dict, horario: str, produto):
    """Marca no histórico que postou (nunca repete). 'produto' pode ser 1 slug
    (str) ou vários (list) quando o slot posta 1 por conta."""
    hoje = str(date.today())
    slugs = produto if isinstance(produto, list) else [produto]
    hist["por_dia"].setdefault(hoje, {})[horario] = (
        list(slugs) if isinstance(produto, list) else produto)
    for s in slugs:
        if s not in hist["postados"]:
            hist["postados"].append(s)
    _salvar_historico(hist)
    log.info(f"   📝 Registrado: {hoje} {horario} → {', '.join(slugs)}")


# =====================================================================
# UM CICLO COMPLETO DO MAESTRO
# =====================================================================

def rodar_um_ciclo(cfg: dict, estado: dict, hist: dict, dry_run: bool,
                   so: str = "") -> dict:
    """
    Executa as três frentes EM SÉRIE (descoberta → produção → postagem).
    `so` restringe a uma frente só ('descoberta'|'producao'|'postar').
    """
    resumo = {}

    # 0) DESCOBERTA DE GRUPOS (manhã/noite) — auto-alimenta radar + hunter
    if so in ("", "grupos"):
        resumo["grupos"] = ciclo_descoberta_grupos(cfg, estado, dry_run,
                                                   forcar=(so == "grupos"))

    # 1) DESCOBERTA (só se passou o intervalo)
    if so in ("", "descoberta"):
        if so == "descoberta" or _precisa_descobrir(cfg, estado):
            resumo["descoberta"] = ciclo_descoberta(cfg, estado, dry_run)
        else:
            ultima = estado.get("ultima_descoberta", "?")
            log.debug(f"   ⏭️  Descoberta não devida (última: {ultima})")

    # 2) PRODUÇÃO (respeita teto + auto_repor)
    if so in ("", "producao"):
        resumo["producao"] = ciclo_producao(cfg, estado, dry_run)

    # 3) POSTAGEM (nos horários)
    if so in ("", "postar"):
        resumo["postagem"] = ciclo_postagem(cfg, hist, dry_run)

    return resumo


# =====================================================================
# LOOP PRINCIPAL DO DAEMON
# =====================================================================

_PARAR = False

def _signal_handler(signum, frame):
    global _PARAR
    log.info(f"\n🛑 Sinal {signum} recebido — encerrando após o ciclo atual...")
    _PARAR = True


def rodar_daemon(dry_run: bool = False):
    """Loop infinito: checa o relógio e dispara as frentes no momento certo."""
    global _PARAR

    if not _adquirir_lock():
        return 1

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    cfg = carregar_config()
    estado = _carregar_estado()
    hist = _carregar_historico()

    log.info("█" * 60)
    log.info("🤖 DAEMON MAESTRO JARVIS — iniciado")
    log.info(f"   Descoberta: a cada {cfg['descoberta_intervalo_horas']}h "
             f"(fontes: {cfg['descoberta_fontes']})")
    log.info(f"   Produção: máx {cfg['producao_max_videos_dia']} vídeos/dia "
             f"(premium ≥ R$ {cfg['producao_premium_comissao_min']})")
    log.info(f"   Postagem: {cfg['horarios']} ({cfg['plataformas']}, "
             f"{'público' if cfg['publico'] else 'privado'})")
    if cfg.get("grupos_descoberta_ativa", True):
        log.info(f"   Descoberta de grupos: {cfg.get('grupos_descoberta_horarios')} "
                 f"(até {cfg.get('grupos_descoberta_max', 2)}/vez, "
                 f"{'auto' if cfg.get('grupos_descoberta_auto_add', True) else 'só sugere'})")
    log.info(f"   Check a cada {cfg['intervalo_check_seg']}s")
    log.info("█" * 60)

    try:
        while not _PARAR:
            try:
                # Recarrega config a cada ciclo (permite editar sem reiniciar)
                cfg = carregar_config()
                _resetar_contador_se_novo_dia(estado)
                rodar_um_ciclo(cfg, estado, hist, dry_run)
            except Exception as e:
                log.error(f"❌ Erro no ciclo (continuando): {e}")

            # Dorme até o próximo check (interrompível)
            for _ in range(int(cfg["intervalo_check_seg"])):
                if _PARAR:
                    break
                time.sleep(1)
    finally:
        _liberar_lock()
        log.info("👋 Daemon encerrado. Lock liberado.")

    return 0


# =====================================================================
# STATUS
# =====================================================================

def mostrar_status():
    cfg = carregar_config()
    estado = _carregar_estado()
    hist = _carregar_historico()
    _resetar_contador_se_novo_dia(estado)

    print("\n" + "═" * 56)
    print("🤖 STATUS DO DAEMON MAESTRO")
    print("═" * 56)

    # Lock
    if LOCK_PATH.exists():
        try:
            pid = LOCK_PATH.read_text().strip()
            print(f"  🔒 Daemon RODANDO (PID {pid})")
        except Exception:
            print(f"  🔒 Lock presente (PID ?)")
    else:
        print(f"  ⭕ Daemon PARADO")

    # Produção
    print(f"\n  🎬 Vídeos hoje: {estado['videos_hoje']}/{cfg['producao_max_videos_dia']}")
    print(f"  📦 Prontos na esteira: {_contar_prontos()}")

    # Descoberta
    ultima_desc = estado.get("ultima_descoberta", "nunca")
    fontes = cfg["descoberta_fontes"]
    prox_fonte = fontes[estado.get("ciclo_descoberta", 0) % len(fontes)]
    print(f"\n  🔍 Última descoberta: {ultima_desc}")
    print(f"  🔄 Próxima fonte: {prox_fonte} (ciclo #{estado.get('ciclo_descoberta', 0)})")

    # Postagem hoje
    hoje = str(date.today())
    postados_hoje = hist["por_dia"].get(hoje, {})
    print(f"\n  📤 Postados hoje ({hoje}):")
    if postados_hoje:
        for horario, produto in sorted(postados_hoje.items()):
            print(f"     {horario} → {produto}")
    else:
        print(f"     (nenhum ainda)")

    # Próximos horários
    agora = _agora_min()
    pendentes = [h for h in cfg["horarios"]
                 if _hora_para_min(h) > agora and h not in postados_hoje]
    if pendentes:
        print(f"  ⏰ Próximos horários hoje: {pendentes}")

    print(f"\n  📊 Total histórico: {len(hist['postados'])} vídeos postados")
    print("═" * 56 + "\n")


# =====================================================================
# CLI
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Daemon Maestro Jarvis — roda descoberta + produção + postagem 24/7")
    parser.add_argument("--once", action="store_true",
                        help="roda 1 ciclo completo e sai (teste)")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="simula tudo, não gera vídeo nem posta nem consulta Telegram")
    parser.add_argument("--status", action="store_true",
                        help="mostra o estado do daemon e sai")
    parser.add_argument("--so-postar", action="store_true", dest="so_postar",
                        help="roda só o ciclo de postagem")
    parser.add_argument("--so-descoberta", action="store_true", dest="so_descoberta",
                        help="roda só o ciclo de descoberta")
    parser.add_argument("--so-producao", action="store_true", dest="so_producao",
                        help="roda só o ciclo de produção")
    parser.add_argument("--so-grupos", action="store_true", dest="so_grupos",
                        help="roda só a descoberta de grupos (manual, ignora horário)")
    args = parser.parse_args()

    if args.status:
        mostrar_status()
        return 0

    # Modos --once e --so-* não precisam de lock (são pontuais)
    so = ""
    if args.so_postar:
        so = "postar"
    elif args.so_descoberta:
        so = "descoberta"
    elif args.so_producao:
        so = "producao"
    elif args.so_grupos:
        so = "grupos"

    if args.once or so:
        cfg = carregar_config()
        estado = _carregar_estado()
        hist = _carregar_historico()
        _resetar_contador_se_novo_dia(estado)
        log.info(f"▶️  Rodando {'ciclo único' if not so else f'só {so}'}"
                 f"{' [DRY-RUN]' if args.dry_run else ''}")
        resumo = rodar_um_ciclo(cfg, estado, hist, args.dry_run, so=so)
        log.info(f"🏁 Ciclo concluído: {json.dumps(resumo, ensure_ascii=False, default=str)[:300]}")
        return 0

    # Modo daemon (loop infinito)
    return rodar_daemon(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())