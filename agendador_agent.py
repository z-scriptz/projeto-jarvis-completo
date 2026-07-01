"""
agents/agendador_agent.py
=========================
AGENDADOR de postagem — processo vivo que posta a fila nos horários certos.

Mantém o teu ritmo saudável (2-4/dia em horários espaçados) em vez de despejar
tudo de uma vez. Lê os horários de agendador_config.json (editável sem mexer
no código).

COMO FUNCIONA:
  - Fica vivo, checando o relógio a cada N segundos.
  - Quando bate um horário configurado (dentro da tolerância), pega o PRÓXIMO
    vídeo não-postado da fila (pronto_para_postar/) e sobe pra(s) plataforma(s).
  - Marca no histórico pra NÃO postar o mesmo vídeo 2x, nem 2x no mesmo horário.

IMPORTANTE: é "processo vivo" — precisa ficar rodando (terminal aberto).
Se fechar/desligar o PC, ele para. Pra 24h real com PC desligado, depois
migramos pra VPS. Por ora, roda enquanto o PC está ligado.

USO:
  python -m agents.agendador_agent                  # roda com a config
  python -m agents.agendador_agent --agora          # posta 1 AGORA (teste)
  python -m agents.agendador_agent --status         # mostra fila e histórico
  python -m agents.agendador_agent --dry-run        # simula (não posta de verdade)

Ctrl+C pra parar.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, date
from pathlib import Path

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("agendador")

RAIZ = Path(__file__).resolve().parent.parent
CONFIG_PATH = RAIZ / "agendador_config.json"
PRONTO_DIR = RAIZ / "pronto_para_postar"
HISTORICO_PATH = RAIZ / "shared" / "state" / "agendador_historico.json"

DEFAULTS = {
    "horarios": ["09:00", "14:00", "20:00"],
    "plataformas": ["youtube"],
    "publico": False,
    "tolerancia_min": 10,
    "intervalo_check_seg": 60,
    "auto_repor": False,
    "repor_quando_sobrar": 2,
    "repor_quantidade": 4,
}


def carregar_config() -> dict:
    """Lê a config; usa defaults pro que faltar. Nunca quebra."""
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for k in DEFAULTS:
                if k in user:
                    cfg[k] = user[k]
        except Exception as e:
            log.warning(f"Config inválida ({e}) — usando defaults")
    return cfg


def carregar_historico() -> dict:
    """Histórico de postagens: {data: {horario: slug_postado}, postados: [slugs]}."""
    if HISTORICO_PATH.exists():
        try:
            return json.loads(HISTORICO_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"por_dia": {}, "postados": []}


def salvar_historico(h: dict):
    HISTORICO_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp = HISTORICO_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(HISTORICO_PATH)
    except Exception as e:
        log.error(f"Falha ao salvar histórico: {e}")


def fila_pendente(historico: dict) -> list:
    """
    Lista os slugs em pronto_para_postar/ que ainda NÃO foram postados.
    Ordem: alfabética (estável). Cada pasta com video.mp4 é um item da fila.
    """
    if not PRONTO_DIR.exists():
        return []
    postados = set(historico.get("postados", []))
    pendentes = []
    for pasta in sorted(PRONTO_DIR.iterdir()):
        if pasta.is_dir() and (pasta / "video.mp4").exists():
            if pasta.name not in postados:
                pendentes.append(pasta.name)
    return pendentes


def _produto_de_slug(slug: str) -> str:
    """Lê o nome do produto do manifest, ou deriva do slug."""
    # tenta achar o manifest mais recente pra esse slug
    manifs = sorted((RAIZ / "outputs").glob(f"*/run_*/{slug}/manifest.json"),
                    reverse=True)
    if manifs:
        try:
            m = json.loads(manifs[0].read_text(encoding="utf-8"))
            if m.get("produto"):
                return m["produto"]
        except Exception:
            pass
    # fallback: deriva do slug (cinto_modelador → Cinto Modelador)
    return slug.replace("_", " ").title()


def postar(slug: str, plataformas: list, publico: bool, dry_run: bool) -> bool:
    """Posta um vídeo nas plataformas. Retorna True se ao menos uma deu certo."""
    produto = _produto_de_slug(slug)
    algum_ok = False

    for plat in plataformas:
        if plat == "youtube":
            if dry_run:
                log.info(f"   [DRY-RUN] postaria '{produto}' no YouTube")
                algum_ok = True
                continue
            cmd = [sys.executable, "-m", "agents.youtube_uploader",
                   "--produto", produto]
            if publico:
                cmd.append("--publico")
            log.info(f"   📤 YouTube: subindo '{produto}'...")
            try:
                r = subprocess.run(cmd, cwd=str(RAIZ), timeout=20 * 60,
                                   capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
                if r.returncode == 0:
                    log.info(f"   ✅ YouTube OK: '{produto}'")
                    algum_ok = True
                else:
                    log.warning(f"   ❌ YouTube falhou (exit {r.returncode}) pra '{produto}'")
                    # últimas linhas do erro pra diagnóstico
                    if r.stdout:
                        for linha in r.stdout.strip().splitlines()[-3:]:
                            log.warning(f"      {linha}")
            except subprocess.TimeoutExpired:
                log.warning(f"   ⏱️  YouTube timeout pra '{produto}'")
            except Exception as e:
                log.error(f"   💥 Erro ao postar no YouTube: {e}")
        else:
            log.info(f"   ⏭️  Plataforma '{plat}' ainda não implementada — pulando")

    return algum_ok


def _ja_postou_neste_horario(historico: dict, dia: str, horario: str) -> bool:
    return horario in historico.get("por_dia", {}).get(dia, {})


def _registrar(historico: dict, dia: str, horario: str, slug: str):
    historico.setdefault("por_dia", {}).setdefault(dia, {})[horario] = slug
    historico.setdefault("postados", [])
    if slug not in historico["postados"]:
        historico["postados"].append(slug)
    salvar_historico(historico)


def _horario_devido(agora: datetime, horarios: list, tolerancia_min: int,
                     historico: dict) -> str:
    """
    Retorna o horário configurado que está 'na hora' agora (dentro da tolerância)
    e que ainda NÃO foi postado hoje. Senão, retorna "".
    """
    dia = agora.strftime("%Y-%m-%d")
    agora_min = agora.hour * 60 + agora.minute
    for h in horarios:
        try:
            hh, mm = map(int, h.split(":"))
        except Exception:
            continue
        alvo_min = hh * 60 + mm
        # 'na hora' = entre o horário e horário+tolerância
        if 0 <= (agora_min - alvo_min) <= tolerancia_min:
            if not _ja_postou_neste_horario(historico, dia, h):
                return h
    return ""


def carregar_lista_produtos() -> list:
    """
    Lê produtos_fila.json — a SUA lista de produtos a fazer (curadoria manual).
    É daqui que o Jarvis puxa pra repor a fila quando ela baixa.
    """
    p = RAIZ / "produtos_fila.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"produtos_fila.json inválido ({e})")
        return []


def _ja_produzidos(historico: dict) -> set:
    """Slugs que já foram produzidos (estão prontos ou já postados)."""
    feitos = set(historico.get("postados", []))
    # também conta os que estão prontos na fila (já produzidos, esperando)
    if PRONTO_DIR.exists():
        for pasta in PRONTO_DIR.iterdir():
            if pasta.is_dir() and (pasta / "video.mp4").exists():
                feitos.add(pasta.name)
    return feitos


def repor_fila(cfg: dict, historico: dict, dry_run: bool) -> bool:
    """
    Se a fila de vídeos prontos está baixa (≤ limite), produz mais a partir da
    SUA lista (produtos_fila.json) — pega os próximos produtos ainda não feitos
    e roda o production_runner. Mantém a esteira cheia sem você abastecer toda hora.

    Retorna True se disparou produção.
    """
    limite = cfg.get("repor_quando_sobrar", 2)
    qtd_repor = cfg.get("repor_quantidade", 4)

    fila = fila_pendente(historico)
    if len(fila) > limite:
        return False  # fila ainda tem material suficiente

    lista = carregar_lista_produtos()
    if not lista:
        log.info("   📭 Fila baixa, mas produtos_fila.json está vazio — "
                 "abasteça a lista pra reposição automática")
        return False

    # escolhe os próximos da lista que ainda não foram produzidos
    feitos = _ja_produzidos(historico)
    import re
    def _slug(p):
        s = re.sub(r"[^\w\s-]", "", p.lower())
        return re.sub(r"[\s-]+", "_", s).strip("_")
    candidatos = [p for p in lista if _slug(p) not in feitos][:qtd_repor]

    if not candidatos:
        log.info("   ✅ Fila baixa, mas todos os produtos da lista já foram "
                 "feitos — abasteça produtos_fila.json com novos")
        return False

    log.info(f"   🏭 Fila baixa ({len(fila)} ≤ {limite}) — produzindo "
             f"{len(candidatos)} novo(s): {candidatos}")
    if dry_run:
        log.info(f"   [DRY-RUN] produziria: {candidatos}")
        return True

    # roda o production_runner pros candidatos (em subprocess, isolado)
    try:
        cmd = [sys.executable, "-m", "agents.production_runner_agent",
               "--produtos"] + candidatos
        log.info(f"   ⏳ Produzindo em background (pode levar alguns minutos)...")
        subprocess.run(cmd, cwd=str(RAIZ), timeout=60 * 60)  # até 1h pro lote
        log.info(f"   ✅ Produção concluída — fila reabastecida")
        return True
    except subprocess.TimeoutExpired:
        log.warning("   ⏱️  Produção excedeu 1h — parando (verifique)")
    except Exception as e:
        log.error(f"   💥 Erro ao produzir: {e}")
    return False


def postar_proximo(cfg: dict, historico: dict, horario_label: str,
                    dry_run: bool) -> bool:
    """Pega o próximo da fila e posta. Registra no histórico se OK."""
    fila = fila_pendente(historico)
    if not fila:
        log.info("   📭 Fila vazia — nada pra postar (gere mais vídeos)")
        return False
    slug = fila[0]
    log.info(f"   🎬 Próximo da fila: '{slug}' ({len(fila)} na fila)")
    ok = postar(slug, cfg["plataformas"], cfg["publico"], dry_run)
    if ok:
        dia = datetime.now().strftime("%Y-%m-%d")
        if dry_run:
            # Dry-run NÃO persiste em disco — mas registra no histórico EM
            # MEMÓRIA pra não simular o mesmo horário repetidamente dentro da
            # janela de tolerância (evita poluir o terminal a cada minuto).
            historico.setdefault("por_dia", {}).setdefault(dia, {})[horario_label] = slug
            historico.setdefault("postados", [])
            if slug not in historico["postados"]:
                historico["postados"].append(slug)
            log.info(f"   [DRY-RUN] simulado '{slug}' em {dia} {horario_label} "
                     f"(não posta nem salva)")
        else:
            _registrar(historico, dia, horario_label, slug)
            log.info(f"   📝 Registrado: '{slug}' postado em {dia} {horario_label}")

    # AUTO-REPOSIÇÃO: depois de postar, se a fila baixou, produz mais da lista.
    # Mantém a esteira cheia sem você abastecer o tempo todo.
    if cfg.get("auto_repor", False):
        repor_fila(cfg, historico, dry_run)

    return ok


def mostrar_status(cfg: dict):
    historico = carregar_historico()
    fila = fila_pendente(historico)
    log.info("=" * 60)
    log.info("📅 STATUS DO AGENDADOR")
    log.info("=" * 60)
    log.info(f"   Horários:    {', '.join(cfg['horarios'])}")
    log.info(f"   Plataformas: {', '.join(cfg['plataformas'])}")
    log.info(f"   Modo:        {'PÚBLICO' if cfg['publico'] else 'PRIVADO (revisar)'}")
    log.info(f"\n   📋 Fila pendente ({len(fila)}):")
    for s in fila[:20]:
        log.info(f"      • {s}")
    if not fila:
        log.info("      (vazia)")
    postados = historico.get("postados", [])
    log.info(f"\n   ✅ Já postados ({len(postados)}):")
    for s in postados[-10:]:
        log.info(f"      • {s}")
    if not postados:
        log.info("      (nenhum ainda)")


def loop_vivo(cfg: dict, dry_run: bool):
    """Fica vivo checando o relógio. Posta quando bate um horário."""
    log.info("=" * 60)
    log.info("📅 AGENDADOR — PROCESSO VIVO")
    log.info("=" * 60)
    log.info(f"   Horários:    {', '.join(cfg['horarios'])}")
    log.info(f"   Plataformas: {', '.join(cfg['plataformas'])}")
    log.info(f"   Modo:        {'PÚBLICO' if cfg['publico'] else 'PRIVADO (revisar)'}"
             f"{'  [DRY-RUN]' if dry_run else ''}")
    log.info(f"   Checando a cada {cfg['intervalo_check_seg']}s. Ctrl+C pra parar.")
    log.info("=" * 60)

    # No dry-run, mantemos o histórico em memória entre as checagens (nada é
    # salvo em disco), pra ele lembrar o que já simulou e não repetir.
    historico_memoria = carregar_historico() if dry_run else None

    while True:
        try:
            historico = historico_memoria if dry_run else carregar_historico()
            agora = datetime.now()
            h = _horario_devido(agora, cfg["horarios"], cfg["tolerancia_min"],
                                historico)
            if h:
                log.info(f"\n⏰ {agora.strftime('%H:%M')} — horário {h} chegou!")
                postar_proximo(cfg, historico, h, dry_run)
            time.sleep(cfg["intervalo_check_seg"])
        except KeyboardInterrupt:
            log.info("\n👋 Agendador parado pelo usuário (Ctrl+C)")
            break
        except Exception as e:
            # NUNCA morre por um erro pontual — loga e continua
            log.error(f"Erro no loop (continuando): {e}")
            time.sleep(cfg["intervalo_check_seg"])


def main():
    parser = argparse.ArgumentParser(description="Agendador de postagem (processo vivo)")
    parser.add_argument("--agora", action="store_true",
                        help="Posta 1 vídeo AGORA (teste, ignora horário)")
    parser.add_argument("--status", action="store_true",
                        help="Mostra a fila e o histórico, sem postar")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="Simula (não posta de verdade)")
    args = parser.parse_args()

    cfg = carregar_config()

    if args.status:
        mostrar_status(cfg)
        return 0

    if args.agora:
        log.info("🧪 Teste: postando 1 vídeo AGORA")
        historico = carregar_historico()
        postar_proximo(cfg, historico, "manual", args.dry_run)
        return 0

    loop_vivo(cfg, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())