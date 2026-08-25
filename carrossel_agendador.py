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

def _confere_python() -> str:
    """Diz se este interpretador tem o que o carrossel precisa. "" se tem.

    ⚠️ ISTO EXISTE PORQUE EU JÁ MANDEI O COMANDO ERRADO DUAS VEZES. O Pillow e
    o `google-genai` moram no `.venv`; rodando com o `python3` do sistema o
    erro que aparece é `No module named 'PIL'` — DEPOIS de escolher formato,
    ler a fila e baixar as fotos. Três minutos de trabalho jogados fora e uma
    mensagem que não diz a causa: não é biblioteca faltando, é o interpretador
    errado. Melhor recusar na primeira linha, dizendo o comando certo."""
    faltam = []
    for mod, nome in (("PIL", "Pillow"), ("requests", "requests")):
        try:
            __import__(mod)
        except Exception:
            faltam.append(nome)
    if not faltam:
        return ""
    venv = BASE_DIR / ".venv" / "bin" / "python"
    dica = (f"\n   Use:  {venv} {' '.join(sys.argv)}" if venv.exists()
            else f"\n   Instale:  pip install {' '.join(faltam)}")
    return (f"este python não tem {', '.join(faltam)} "
            f"({sys.executable}){dica}")


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
                horario: str = "manual", refazer: bool = False,
                formato: str = "") -> dict:
    """Monta, renderiza e publica UM carrossel. Nunca levanta.

    ⚠️ `refazer=True` REAPROVEITA O PLANO QUE JÁ ESTÁ EM DISCO. Sem isso o
    fluxo das imagens por slide não fecha, e o furo é traiçoeiro:

        --agora casa          → monta o plano A, renderiza
        fundo_ia --do-plano   → gera as imagens DO PLANO A
        --agora casa          → monta o plano B ← e joga o A fora

    O terceiro passo chamava o brain de novo, e o Gemini escreve outra coisa a
    cada chamada. As imagens do plano A iam parar num carrossel que fala do
    plano B — ou seja, **o passo que existe pra casar imagem e texto produzia
    justamente o descasamento**, e ainda gastando dinheiro em imagem. Só que
    nada falha: sai um carrossel bonito, com fotos que não têm relação. É a
    mesma família do fundo por rodízio, com um agravante — aqui a gente pagou.
    """
    cfg = cfg or {}
    pasta = PRONTO / _slug(nicho, horario)

    plano = None
    if refazer:
        arq = pasta / "plano.json"
        if not arq.exists():
            log.error(f"   ❌ {nicho}: --refazer não achou {arq}. "
                      f"Rode sem --refazer primeiro pra criar o plano.")
            return {"ok": False, "motivo": "sem_plano"}
        try:
            plano = json.loads(arq.read_text(encoding="utf-8"))
            n = len(list((pasta / "fundos").glob("*"))) \
                if (pasta / "fundos").is_dir() else 0
            log.info(f"   ♻️  {nicho}: reusando o plano de {pasta.name}"
                     + (f" · {n} imagem(ns) por slide" if n else
                        " · ⚠️  sem imagens por slide ainda"))
        except Exception as e:
            log.error(f"   ❌ {nicho}: plano.json ilegível ({str(e)[:80]})")
            return {"ok": False, "motivo": "plano"}

    # ⚠️ NICHO SEM ACERVO RENDERIZA CARROSSEL SEM FUNDO, E EM SILÊNCIO (25/08).
    # `fundo_do_nicho()` devolve "" quando a pasta do nicho está vazia — não
    # levanta nada. As composições que pedem foto ficam com o buraco, e o
    # carrossel vai ao ar feio em vez de não ir.
    #
    # Isso importa AGORA porque a @topshoppet_ vai estrear no carrossel, e a
    # biblioteca de pet ainda não foi gerada. A primeira aparição de uma conta
    # com slides quebrados é pior que a conta continuar parada mais uns dias.
    #
    # ⚠️ A imagem SOB MEDIDA (`fundos/NN.png` na pasta do plano) conta como
    # acervo: o `_imagem_propria()` tem prioridade máxima no render, então um
    # plano que traz as próprias imagens não depende da biblioteca do nicho.
    #
    # ⚠️ E CONTA COM `_todas()`, NÃO COM `existentes()`. O `existentes(nicho)`
    # sem formato lê só a RAIZ da pasta do nicho — o acervo de verdade mora nas
    # subpastas por formato (`fundos/<nicho>/erros/`, `/lista/`, …), que o
    # `_todas()` varre com rglob. Medido em 25/08: `existentes()` dizia 10 por
    # nicho quando havia ~100. Com o número errado esta guarda barraria um nicho
    # de acervo cheio, e a mensagem juraria que a biblioteca não existe.
    try:
        import fundo_ia as FI
        tem_acervo = bool(FI._todas(nicho) if hasattr(FI, "_todas")
                          else FI.existentes(nicho))
    except Exception:
        tem_acervo = True          # na dúvida não bloqueia a esteira que já roda
    proprias = (pasta / "fundos")
    if not tem_acervo and not (proprias.is_dir() and any(proprias.iterdir())):
        log.warning(f"   ⏭️  {nicho}: sem NENHUM fundo — nem biblioteca em "
                    f"fundos/{nicho}/ nem imagens próprias em {proprias.name}/. "
                    f"Não publico slides sem fundo; gere a biblioteca do nicho "
                    f"antes de ligar o carrossel dele.")
        return {"ok": False, "motivo": "sem_fundo"}

    if plano is None:
        try:
            import carrossel_brain as CB
            plano = CB.montar_plano(nicho, formato=formato, fotos_em=pasta)
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
        # ⚠️ O DRY-RUN TAMBÉM PRECISA DEIXAR O `plano.json` EM DISCO. Ele saía
        # sem preparar nada, então o que o carrossel DIZ morria junto com o
        # processo — e o `fundo_ia --do-plano`, que é justamente pra rodar em
        # cima de um dry-run antes de publicar, não tinha o que ler. Só o
        # plano: `conta.json` fica de fora de propósito, porque pasta com
        # conta é pasta pronta pra postar, e ensaio não pode virar publicação
        # por engano.
        try:
            (pasta / "plano.json").write_text(
                json.dumps(plano, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8")
        except Exception as e:
            log.warning(f"   ⚠️  não escrevi plano.json ({e})")
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
        # ⚠️ VOLUME 0 = DIA DE DESCANSO, E ISSO PRECISA VIR ANTES DO `or`.
        # Eu escrevia `reels_vol.get(str(n)) or horarios`, e no domingo (n=0)
        # o `get("0")` devolve None, o `or` caía na lista genérica e a agenda
        # mostrava "domingo: 09:00, 14:00, 17:00, 21:00". O daemon SEMPRE
        # esteve certo (`if n <= 0: return []`); quem inventou o domingo cheio
        # foi este relatório — e eu quase mandei o Dre consertar o que não
        # estava quebrado. Ferramenta de diagnóstico que mente é pior que
        # ferramenta nenhuma.
        rh = [] if n <= 0 else (reels_vol.get(str(n)) or (cfg.get("horarios") or []))
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
    # ⚠️ O BRAIN JÁ ACEITAVA `formato`; O AGENDADOR É QUE NÃO PASSAVA.
    # O Dre rodou `--agora tech --formato erros` pra testar a biblioteca por
    # formato, o argparse recusou a opção, e o `||` do shell disparou o
    # fallback SEM formato — saiu `lista` e o teste de `erros` nunca aconteceu.
    # Ele só descobriu lendo o log com atenção. **Comando que morre e cai num
    # fallback silencioso é pior que comando que falha**: o resultado aparece,
    # parece legítimo, e valida outra coisa.
    p.add_argument("--formato", metavar="FORMATO", default="",
                   help="força o formato (erros, lista, comparacao...) — "
                        "sem isto o brain sorteia")
    p.add_argument("--refazer", action="store_true",
                   help="com --agora, reusa o plano em disco em vez de montar "
                        "outro (é o que faz as imagens por slide baterem)")
    a = p.parse_args()

    problema = _confere_python()
    if problema:
        print(f"❌ {problema}")
        return 1

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
        r = publicar_um(a.agora, cfg, dry_run=not a.postar,
                        refazer=a.refazer, formato=a.formato)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r.get("ok") else 1
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
