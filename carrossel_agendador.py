#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# carrossel_agendador.py — decide QUANDO o carrossel sai, e faz sair.
#
# ⚠️ MÓDULO SEPARADO, E ISSO É DELIBERADO. O `daemon_maestro` é o coração do
# sistema: ele posta em 6 contas, todo dia, há meses. Enfiar 80 linhas novas
# dentro dele pra um formato que nasceu ontem é apostar o que funciona no que
# ainda não. Aqui o patch no daemon é de TRÊS linhas, dentro de um try/except:
# se este arquivo explodir, os Reels continuam saindo como sempre.
#
# ⚠️ OS HORÁRIOS DO REEL NÃO SÃO FIXOS — eles mudam com o volume do dia
# (`horarios_por_volume` + a pirâmide `posts_por_dia_semana`):
#
#     seg/qui  3 reels   09:00 · 13:00 · 18:30
#     ter/sex  2 reels   09:00 · 18:00
#     qua/sáb  1 reel    09:00
#     domingo  0
#
# Por isso o default do carrossel é **15:30 e 20:30**: são os dois buracos que
# sobram em TODOS os dias da semana, não só nos de volume baixo. Um horário
# "de tarde" às 17h colidiria com o Reel das 18:30 em metade da semana — e
# dois posts nossos na mesma janela disputam a mesma entrega, que é justamente
# o que a pirâmide foi feita pra evitar.
#
# CONFIG (no `agendador_config.json`, todas opcionais):
#   carrossel_horarios          ["15:30", "20:30"]
#   carrosseis_por_dia_semana   [2,1,1,2,1,1,0]   índice 0=segunda
#   carrossel_contas            []  vazio = todas as contas do contas.json
#   carrossel_ligado            false             ⚠️ nasce DESLIGADO
#
# USO:
#   from carrossel_agendador import ciclo
#   ciclo(cfg, dry_run)          # chamado pelo daemon a cada volta
#
#   python3 carrossel_agendador.py --agenda     # o mapa da semana
#   python3 carrossel_agendador.py --agora casa # força um, ignorando relógio

import os
import sys
import json
import time
import argparse
from datetime import datetime, date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
HIST = BASE_DIR / "shared" / "carrossel_historico.json"
PRONTO = BASE_DIR / "pronto_carrossel"

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("carrossel_agendador")

HORARIOS_PADRAO = ["15:30", "20:30"]
POR_DIA_PADRAO = [2, 1, 1, 2, 1, 1, 0]      # espelha a pirâmide, mais baixa


# ══════════════════════════════════════════════════════════════════════════
# CONFIG E ESTADO
# ══════════════════════════════════════════════════════════════════════════
def _ligado(cfg: dict) -> bool:
    """⚠️ NASCE DESLIGADO. Um formato novo que começa publicando sozinho em 6
    contas é um jeito rápido de descobrir um defeito em público. Liga com
    `"carrossel_ligado": true` depois de olhar alguns prontos."""
    return bool(cfg.get("carrossel_ligado", False))


def _horarios(cfg: dict) -> list:
    return list(cfg.get("carrossel_horarios") or HORARIOS_PADRAO)


def _quantos_hoje(cfg: dict, quando: date = None) -> int:
    piramide = cfg.get("carrosseis_por_dia_semana") or POR_DIA_PADRAO
    try:
        return max(0, int(piramide[(quando or date.today()).weekday()]))
    except Exception:
        return 1


def _contas(cfg: dict) -> list:
    """Nichos que recebem carrossel. Vazio na config = todos do contas.json."""
    escolhidas = cfg.get("carrossel_contas") or []
    if escolhidas:
        return list(escolhidas)
    try:
        c = json.loads((BASE_DIR / "contas.json").read_text(encoding="utf-8"))
        return [k if k != "_default" else "geral" for k in c]
    except Exception:
        return ["geral"]


def _hist() -> dict:
    try:
        return json.loads(HIST.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _grava(h: dict) -> None:
    try:
        HIST.parent.mkdir(parents=True, exist_ok=True)
        tmp = HIST.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(HIST)
    except Exception as e:
        log.warning(f"   ⚠️  não gravei o histórico do carrossel: {e}")


def _devido(cfg: dict, hist: dict) -> str:
    """O horário que está 'na hora' e ainda não saiu hoje. "" se não é hora.

    ⚠️ A TOLERÂNCIA É A MESMA DO REEL de propósito: o daemon acorda de minuto
    em minuto, mas uma volta pode demorar (produção, upload, espera entre
    contas). Sem janela, um slot que caísse no meio de uma volta longa seria
    pulado em silêncio — e ninguém veria, porque não há erro nenhum."""
    tol = int(cfg.get("tolerancia_min", 10))
    agora = datetime.now()
    agora_min = agora.hour * 60 + agora.minute
    dia = agora.strftime("%Y-%m-%d")
    feitos = (hist.get("por_dia") or {}).get(dia) or {}
    for h in _horarios(cfg)[:_quantos_hoje(cfg)]:
        try:
            hh, mm = map(int, h.split(":"))
        except Exception:
            continue
        if 0 <= (agora_min - (hh * 60 + mm)) <= tol and h not in feitos:
            return h
    return ""


# ══════════════════════════════════════════════════════════════════════════
# PRODUZIR E PUBLICAR
# ══════════════════════════════════════════════════════════════════════════
def _slug(nicho: str, horario: str) -> str:
    return f"{date.today():%Y%m%d}_{horario.replace(':', '')}_{nicho}"


def publicar_um(nicho: str, cfg: dict = None, dry_run: bool = False,
                horario: str = "manual") -> dict:
    """Monta, renderiza e publica UM carrossel. Nunca levanta."""
    cfg = cfg or {}
    pasta = PRONTO / _slug(nicho, horario)
    try:
        import carrossel_brain as CB
        plano = CB.montar_plano(nicho, fotos_em=pasta)
    except SystemExit as e:
        # o brain recusa formato de vitrine sem foto — é decisão dele, e o
        # motivo já vem escrito na mensagem
        log.warning(f"   ⏭️  {nicho}: {str(e)[:120]}")
        return {"ok": False, "motivo": "sem_material"}
    except Exception as e:
        log.error(f"   ❌ {nicho}: não montei o plano ({str(e)[:100]})")
        return {"ok": False, "motivo": "plano"}

    try:
        import carrossel_render as CR
        arquivos = CR.renderizar(plano, pasta)
    except Exception as e:
        log.error(f"   ❌ {nicho}: não renderizei ({str(e)[:100]})")
        return {"ok": False, "motivo": "render"}
    if not arquivos:
        return {"ok": False, "motivo": "render_vazio"}

    if dry_run:
        log.info(f"   🧪 [dry-run] {nicho}: {len(arquivos)} slide(s) em {pasta}")
        return {"ok": True, "dry_run": True, "pasta": str(pasta)}

    try:
        r = CB.publicar(plano, pasta, arquivos)
    except Exception as e:
        log.error(f"   ❌ {nicho}: exceção publicando ({str(e)[:100]})")
        return {"ok": False, "motivo": "publish"}
    if r.get("sucesso"):
        log.info(f"   ✅ carrossel no ar [{nicho}] {r['url']}")
        return {"ok": True, "url": r["url"]}
    log.warning(f"   ⚠️  {nicho}: {str(r.get('erro'))[:140]}")
    return {"ok": False, "motivo": "recusado"}


def ciclo(cfg: dict, dry_run: bool = False) -> dict:
    """Uma volta. Chamado pelo daemon; devolve o que fez (ou nada)."""
    if not _ligado(cfg):
        return {"postou": False, "motivo": "desligado"}
    hist = _hist()
    horario = _devido(cfg, hist)
    if not horario:
        return {"postou": False}

    contas = _contas(cfg)
    log.info("─" * 60)
    log.info(f"🎠 CICLO CARROSSEL — slot {horario} · {len(contas)} conta(s)")

    feitos, falhas = [], []
    for nicho in contas:
        r = publicar_um(nicho, cfg, dry_run, horario)
        (feitos if r.get("ok") else falhas).append(nicho)
        # ⚠️ RESPIRO ENTRE CONTAS, pelo mesmo motivo do Reel: seis contas
        # publicando no mesmo minuto, todo dia, é um padrão mais evidente que
        # o horário cravado.
        if not dry_run and nicho != contas[-1]:
            time.sleep(float(cfg.get("carrossel_intervalo_seg", 90)))

    if not dry_run:
        dia = date.today().isoformat()
        hist.setdefault("por_dia", {}).setdefault(dia, {})[horario] = feitos
        _grava(hist)
    log.info(f"🎠 slot {horario}: {len(feitos)} publicado(s)"
             + (f" · {len(falhas)} sem sair: {', '.join(falhas)}" if falhas else ""))
    return {"postou": bool(feitos), "contas": feitos, "falhas": falhas}


# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════
_DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _agenda(cfg: dict) -> int:
    """O mapa da semana, com o Reel do lado — é assim que se vê colisão."""
    reels_vol = cfg.get("horarios_por_volume") or {
        "1": ["09:00"], "2": ["09:00", "18:00"],
        "3": ["09:00", "13:00", "18:30"]}
    piramide = cfg.get("posts_por_dia_semana") or [3, 2, 1, 3, 2, 1, 0]
    print(f"{'dia':<9} {'REELS':<26} CARROSSEL")
    print("─" * 62)
    for i, nome in enumerate(_DIAS):
        n = piramide[i] if i < len(piramide) else 0
        rh = reels_vol.get(str(n)) or (cfg.get("horarios") or [])
        ch = _horarios(cfg)[:_quantos_hoje(cfg, date.fromordinal(
            date.today().toordinal() - date.today().weekday() + i))]
        print(f"{nome:<9} {', '.join(rh) if rh else '—':<26} "
              f"{', '.join(ch) if ch else '—'}")
    colisao = set(_horarios(cfg)) & {h for v in reels_vol.values() for h in v}
    print()
    if colisao:
        print(f"⚠️  COLIDE com o Reel em: {', '.join(sorted(colisao))} — dois "
              "posts nossos na mesma janela disputam a mesma entrega.")
    else:
        print("✅ nenhum horário do carrossel colide com os do Reel.")
    print(f"\nligado: {'SIM' if _ligado(cfg) else 'NÃO (carrossel_ligado)'}"
          f" · contas: {', '.join(_contas(cfg))}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Agenda do carrossel")
    p.add_argument("--agenda", action="store_true", help="o mapa da semana")
    p.add_argument("--agora", metavar="NICHO", help="produz 1 agora (teste)")
    p.add_argument("--postar", action="store_true", help="com --agora, publica")
    a = p.parse_args()

    cfg = {}
    for cand in (BASE_DIR / "agendador_config.json",
                 BASE_DIR / "shared" / "content_plans" / "agendador_config.json"):
        try:
            cfg = json.loads(cand.read_text(encoding="utf-8"))
            print(f"📄 config: {cand}\n")
            break
        except Exception:
            continue

    if a.agenda:
        return _agenda(cfg)
    if a.agora:
        r = publicar_um(a.agora, cfg, dry_run=not a.postar)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r.get("ok") else 1
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
