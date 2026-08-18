#!/usr/bin/env python3
# auditoria_postagem.py -- ONDE os 274 pacotes estão parando, com evidência.
#
# POR QUE EXISTE (11/08)
# A revisão geral achou 274 pacotes prontos e o mais antigo com 15 dias. O Dre e
# o ChatGPT pararam a fila de melhorias e mandaram medir antes de consertar:
# *"não deixe ele consertar nada antes de diagnosticar"*. Este arquivo é o
# diagnóstico, e ele **NÃO CONSERTA NADA** — não move, não apaga, não posta,
# não reescreve config. Só lê e conta.
#
# ⚠️ O PRINCÍPIO DE DESENHO QUE IMPORTA AQUI
# ─────────────────────────────────────────
# Ele **importa as funções do próprio daemon** (`_prontos_nao_postados`,
# `_validade_dias`, `_teto_do_dia`, `carregar_config`) em vez de reimplementar
# a mesma lógica. Se eu reescrevesse "quais pacotes estão prontos", estaria
# medindo a MINHA ideia da fila, e a resposta bateria com a realidade só por
# sorte. Foi exatamente esse o erro do `tarjas_limpas`, que lia o limiar da
# mesma config que produzia o defeito e aprovava o vazamento.
#
# Quando o import falha, ele diz isso em voz alta e cai numa releitura própria
# — marcada como tal no relatório, porque medida de segunda mão não pode se
# passar por medida direta.
#
# O QUE ELE RESPONDE
#   estoque por conta e por idade · publicações em 1/3/7 dias · cadência real
#   contra a capacidade configurada · quantos pacotes o daemon SEQUER ENXERGA
#   e por quê · erros de postagem no log · quanto já venceu
#
# Uso:
#   python3 auditoria_postagem.py
#   python3 auditoria_postagem.py --json
#   python3 auditoria_postagem.py --dias 14     # janela do histórico

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# ── liga no daemon de verdade ───────────────────────────────────────────────
DM = None
COMO = "reimplementado (o daemon não pôde ser importado)"
for tentativa in ("agents.daemon_maestro", "daemon_maestro"):
    try:
        sys.path.insert(0, str(RAIZ))
        DM = __import__(tentativa, fromlist=["*"])
        COMO = f"importado de {tentativa}"
        break
    except Exception:
        DM = None

def _pasta(do_daemon, local: Path) -> Path:
    """A pasta do daemon, mas só se ela existir de verdade.

    ⚠️ `daemon_maestro` calcula `RAIZ = Path(__file__).parent.parent`. Na VPS
    ele mora em `agents/`, então RAIZ é `/root/jarvis` e está certo. No repo
    achatado ele mora na raiz, e RAIZ vira o diretório ACIMA do projeto — a
    auditoria apontava pra `/home/user/pronto_para_postar`, que não existe, e
    imprimia "0 pastas" com cara de resposta. Zero medido no lugar errado é
    pior que erro, porque parece resultado.
    """
    try:
        if do_daemon and Path(do_daemon).is_dir():
            return Path(do_daemon)
    except Exception:
        pass
    return local


PRONTO = _pasta(getattr(DM, "PRONTO_DIR", None), RAIZ / "pronto_para_postar")
PLANS = _pasta(getattr(DM, "PLANS_DIR", None),
               RAIZ / "shared" / "content_plans")
if DM and getattr(DM, "PRONTO_DIR", None) and Path(DM.PRONTO_DIR) != PRONTO:
    COMO += f" · ⚠️ ignorei PRONTO_DIR={DM.PRONTO_DIR} (não existe)"
HIST = PLANS / "agendador_historico.json"
VENCIDA = PRONTO.parent / "fila_vencida"


def _cfg() -> dict:
    if DM:
        try:
            return DM.carregar_config()
        except Exception:
            pass
    try:
        return json.loads((PLANS / "agendador_config.json").read_text("utf-8"))
    except Exception:
        return {}


def _hist() -> dict:
    if DM:
        try:
            return DM._carregar_historico()
        except Exception:
            pass
    try:
        d = json.loads(HIST.read_text(encoding="utf-8"))
        d.setdefault("por_dia", {})
        d.setdefault("postados", [])
        return d
    except Exception:
        return {"por_dia": {}, "postados": []}


def _conta(slug: str) -> str:
    try:
        d = json.loads((PRONTO / slug / "conta.json").read_text(encoding="utf-8"))
        return d.get("handle") or d.get("nicho") or "?"
    except Exception:
        return "SEM conta.json"


def _idade_dias(p: Path) -> float:
    return (time.time() - p.stat().st_mtime) / 86400


def _posts_no_dia(slots: dict) -> int:
    """Quantos VÍDEOS saíram no dia — não quantos horários foram usados.

    ⚠️ ERRO QUE ESTA FUNÇÃO CONSERTA (11/08): eu contava `len(por_dia[dia])` e
    concluí "publicação a 23% da capacidade". `daemon_maestro:1226` guarda
    `por_dia[dia][HORARIO] = slug` (modo clássico) ou `= [slug, slug, ...]`
    (modo `post_por_conta`, que está LIGADO na VPS). A chave é o horário, então
    aquele `len` contava SLOTS. O teto da pirâmide é 3 slots/dia — e a série
    "nunca passar de 3" era a assinatura do bug, não um achado sobre o sistema.
    Um slot com 4 contas vale 4 vídeos e eu contava 1.
    """
    total = 0
    for valor in (slots or {}).values():
        total += len(valor) if isinstance(valor, list) else 1
    return total


def _envelhecimento(visiveis: list, validade: int) -> dict:
    """Escadinha de quanto falta pra vencer, só do que ainda pode ser postado.

    Os degraus são relativos à validade, não fixos: com validade 27 eles caem
    em 17/22/25, e mudar `fila_validade_dias` reajusta tudo sozinho. Degrau
    cravado em "20 dias" mentiria no dia em que a validade virasse 14.
    """
    if validade <= 0 or not visiveis:
        return {"em_risco": 0, "escadinha": {}}
    degraus = [int(validade * f) for f in (0.65, 0.8, 0.92)]
    escada = {}
    for d in degraus:
        escada[d] = sum(1 for _s, _c, idade in visiveis if idade > d)
    return {"em_risco": sum(1 for _s, _c, i in visiveis if i > validade - 7),
            "escadinha": escada,
            "mais_velho": round(max(i for _s, _c, i in visiveis), 1)}


def auditar(dias_janela: int = 7) -> dict:
    cfg, hist = _cfg(), _hist()
    postados = set(hist.get("postados", []))
    validade = (DM._validade_dias() if DM else
                int(cfg.get("fila_validade_dias", 27)))

    # ── ESTOQUE ─────────────────────────────────────────────────────────────
    pastas = ([p for p in PRONTO.iterdir() if p.is_dir()]
              if PRONTO.exists() else [])
    por_conta, idade_por_conta = Counter(), defaultdict(list)
    faixas = Counter()

    # Por que um pacote é INVISÍVEL pro daemon. Estas três condições são as do
    # `_prontos_nao_postados`; a lista é a resposta de "onde eles param".
    sem_video, ja_postados, vencidos, visiveis = [], [], [], []

    for p in pastas:
        slug, conta = p.name, _conta(p.name)
        idade = _idade_dias(p)
        por_conta[conta] += 1
        idade_por_conta[conta].append(idade)
        faixas["0-3d" if idade <= 3 else "4-7d" if idade <= 7 else
               "8-14d" if idade <= 14 else "15-27d" if idade <= validade
               else f">{validade}d (vencido)"] += 1

        # ⚠️ o daemon exige o nome EXATO video.mp4 (_prontos_nao_postados).
        # Contar "*.mp4" aqui daria um número maior que o real e esconderia
        # justamente o tipo de defeito que esta auditoria procura.
        if not (p / "video.mp4").exists():
            sem_video.append((slug, conta, round(idade, 1)))
        elif slug in postados:
            ja_postados.append((slug, conta, round(idade, 1)))
        elif validade > 0 and idade > validade:
            vencidos.append((slug, conta, round(idade, 1)))
        else:
            visiveis.append((slug, conta, idade))

    # confronta com a lista que o PRÓPRIO daemon monta
    fila_do_daemon = None
    if DM:
        try:
            fila_do_daemon = DM._prontos_nao_postados(hist)
        except Exception as e:
            fila_do_daemon = f"erro: {str(e)[:80]}"

    # ── PUBLICAÇÃO ──────────────────────────────────────────────────────────
    por_dia = hist.get("por_dia", {}) or {}
    hoje = date.today()
    serie, serie_slots = [], []
    for i in range(dias_janela):
        d = hoje - timedelta(days=i)
        chave = d.isoformat()
        slots = por_dia.get(chave, {}) or {}
        serie.append((chave, _posts_no_dia(slots)))
        serie_slots.append((chave, len(slots)))
    ult1 = sum(n for _, n in serie[:1])
    ult3 = sum(n for _, n in serie[:3])
    ult7 = sum(n for _, n in serie[:7])
    dias_com_dado = [n for _, n in serie]
    media = round(sum(dias_com_dado) / max(1, len(dias_com_dado)), 2)

    # quem postou na janela — o slug guardado no histórico leva ao conta.json
    por_conta_publicado = Counter()
    for i in range(dias_janela):
        chave = (hoje - timedelta(days=i)).isoformat()
        for valor in (por_dia.get(chave, {}) or {}).values():
            for slug in (valor if isinstance(valor, list) else [valor]):
                por_conta_publicado[_conta(str(slug))] += 1

    # ── CAPACIDADE CONFIGURADA ──────────────────────────────────────────────
    contas_ativas = len([c for c in por_conta if c not in ("?", "SEM conta.json")])
    if DM:
        try:
            semana = sum(DM._teto_do_dia(cfg, hoje + timedelta(days=i))
                         for i in range(7))
        except Exception:
            semana = 0
    else:
        pir = cfg.get("posts_por_dia_semana") or []
        semana = sum(int(x) for x in pir) if pir else 0
    # sem conta identificada não dá pra multiplicar: `max(1, 0)` faria a
    # capacidade de 5 contas virar a de 1 e o veredito sairia calibrado errado
    cap_semana_total = semana * contas_ativas if contas_ativas else 0

    estoque = len(visiveis)
    semanas_pra_drenar = (round(estoque / cap_semana_total, 1)
                          if cap_semana_total else None)
    # ⚠️ O NÚMERO QUE DECIDE não é este acima. Drenar na capacidade CONFIGURADA
    # é hipótese; drenar na cadência REAL é o que vai acontecer. Comparar o
    # segundo com a validade é o que diz se o rabo da fila vence antes de sair.
    ritmo_real = sum(n for _, n in serie) / max(1, len(serie))
    dias_drenar_real = (round(estoque / ritmo_real) if ritmo_real else None)

    return {
        "como_mediu": COMO,
        "pasta": str(PRONTO),
        "estoque": {
            "total_pastas": len(pastas),
            "visiveis_pro_daemon": len(visiveis),
            "sem_video_mp4": len(sem_video),
            "ja_marcados_postados": len(ja_postados),
            "vencidos_ainda_na_pasta": len(vencidos),
            "mais_antigo_dias": round(max((_idade_dias(p) for p in pastas),
                                          default=0), 1),
            # ordem fixa: Counter sai por frequência, e faixa de idade fora de
            # ordem cronológica obriga o leitor a reordenar de cabeça
            "faixas_de_idade": {k: faixas[k] for k in
                                ["0-3d", "4-7d", "8-14d", "15-27d",
                                 f">{validade}d (vencido)"] if faixas.get(k)},
            "fila_vencida_dir": (len(list(VENCIDA.iterdir()))
                                 if VENCIDA.exists() else 0),
            # escadinha do que está perto do fim: só contando os VISÍVEIS, que
            # são os que ainda podem ser postados. Incluir os já postados aqui
            # transformaria "vou perder isto" em número inflado — foi assim que
            # o 274 virou alarme.
            "envelhecendo": _envelhecimento(visiveis, validade),
        },
        "por_conta": {
            c: {"pacotes": n,
                "mais_antigo_dias": round(max(idade_por_conta[c]), 1),
                "mediana_dias": round(sorted(idade_por_conta[c])[len(idade_por_conta[c]) // 2], 1)}
            for c, n in por_conta.most_common()
        },
        "publicacao": {
            "ultimas_24h": ult1, "ultimos_3d": ult3, "ultimos_7d": ult7,
            "media_por_dia": media,
            "serie": serie,
            "serie_slots": serie_slots,
            "por_conta": dict(por_conta_publicado.most_common()),
            "total_historico": len(postados),
        },
        "capacidade": {
            "contas": contas_ativas,
            "posts_por_conta_semana": semana,
            "capacidade_semanal_total": cap_semana_total,
            "validade_dias": validade,
            "semanas_pra_drenar": semanas_pra_drenar,
            "ritmo_real_por_dia": round(ritmo_real, 2),
            "dias_pra_drenar_no_ritmo_real": dias_drenar_real,
            "piramide": cfg.get("posts_por_dia_semana"),
            "post_por_conta": cfg.get("post_por_conta"),
            "janela": f"{cfg.get('janela_inicio','?')}–{cfg.get('janela_fim','?')}",
        },
        "amostras": {
            "sem_video_mp4": sem_video[:10],
            "vencidos_ainda_na_pasta": vencidos[:10],
            "mais_antigos_visiveis": [
                (s, c, round(i, 1))
                for s, c, i in sorted(visiveis, key=lambda x: -x[2])[:10]],
        },
        "fila_do_daemon": (len(fila_do_daemon)
                           if isinstance(fila_do_daemon, list)
                           else fila_do_daemon),
        "erros": _erros_de_postagem(),
    }


def _erros_de_postagem() -> dict:
    """Erros de publicação nas últimas 72h, agrupados por tipo."""
    alvo = time.time() - 72 * 3600
    chaves = ("erro ao postar", "falha ao publicar", "upload falhou",
              "todas_plataformas_falharam", "OAuthException",
              "rate limit", "publish", "meta_uploader", "youtube_uploader")
    achados, sem_data = Counter(), Counter()
    exemplos = []
    for p in list(RAIZ.glob("*.log")) + list(RAIZ.glob("logs/*.log")):
        try:
            if p.stat().st_mtime < alvo:
                continue
            with p.open("rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - 600_000))
                texto = f.read().decode("utf-8", errors="replace")
        except Exception:
            continue
        for linha in texto.splitlines():
            baixa = linha.lower()
            if "error" not in baixa and "erro" not in baixa:
                continue
            if not any(k.lower() in baixa for k in chaves):
                continue
            # ⚠️ a data da LINHA, não a do arquivo. Um .log escrito hoje pode
            # ter linhas de um mês atrás no rabo: a primeira versão daqui
            # reportou erros de 14/07 e 01/08 como "últimas 72h". Evidência
            # com carimbo errado manda caçar problema que já não existe.
            quando = _data_da_linha(linha)
            if quando is not None and quando < alvo:
                continue
            if quando is None:
                sem_data[p.name] += 1
                continue
            achados[p.name] += 1
            if len(exemplos) < 6:
                exemplos.append(f"{p.name}: {linha.strip()[:130]}")
    return {"por_arquivo": dict(achados), "exemplos": exemplos,
            "linhas_sem_data_ignoradas": dict(sem_data)}


def _data_da_linha(linha: str):
    """Epoch do carimbo `AAAA-MM-DD HH:MM:SS` no início da linha, ou None."""
    try:
        return datetime.strptime(linha[:19], "%Y-%m-%d %H:%M:%S").timestamp()
    except Exception:
        return None


def _veredito(r: dict) -> list:
    """Do número pro diagnóstico. Cada item cita a evidência que o sustenta."""
    fora = []
    e, c, p = r["estoque"], r["capacidade"], r["publicacao"]

    if not e["total_pastas"]:
        # Sem estoque, "publicou pouco" não é gargalo — é não ter o que
        # publicar. Alertar aqui encheria o relatório de conclusão inventada.
        return [("ESTEIRA VAZIA",
                 f"nenhuma pasta em {r['pasta']} — nada a auditar aqui.",
                 "confira se o caminho é o que a produção usa")]

    if e["sem_video_mp4"]:
        fora.append((
            "PACOTES INVISÍVEIS PRO DAEMON",
            f"{e['sem_video_mp4']} pacote(s) não têm `video.mp4`. "
            "`_prontos_nao_postados` exige esse nome EXATO — eles nunca vão "
            "ser postados, e nem aparecem como problema em lugar nenhum.",
            f"amostra: {r['amostras']['sem_video_mp4'][:3]}"))

    # o que decide é o RITMO REAL, não a capacidade configurada
    dr = c.get("dias_pra_drenar_no_ritmo_real")
    if dr and c["validade_dias"] > 0 and dr > c["validade_dias"]:
        sobra = max(0, e["visiveis_pro_daemon"] -
                    round(c["ritmo_real_por_dia"] * c["validade_dias"]))
        # ⚠️ NÃO AFIRME A ORDEM — PERGUNTE. Esta frase dizia, fixa, "a ordem é
        # MAIS NOVO PRIMEIRO", e em 17/08 ela saiu três linhas abaixo do log do
        # próprio daemon dizendo `ordem MAIS ANTIGO primeiro (drenagem)`. O
        # `daemon_maestro` ganhou modo de drenagem (FIFO quando o mais antigo
        # passa de `limiar_drenagem × validade`) e este texto não soube.
        #
        # E a diferença muda o diagnóstico, não só a redação: em LIFO quem
        # vence é sempre o mesmo rabo antigo; em FIFO quem vence é o material
        # NOVO, que é o mais fresco e provavelmente o melhor. Conselho tirado
        # da ordem errada manda consertar a ponta errada da fila.
        # a MESMA decisão do `daemon_maestro._drenar_por_idade`, refeita com os
        # números que esta auditoria já tem (aquela função exige a lista de
        # candidatos do daemon, que aqui não existe)
        try:
            # ⚠️ NOME DIFERENTE DA FUNÇÃO, DE PROPÓSITO. A 1ª versão fazia
            # `_cfg = _cfg()`, e em Python isso torna `_cfg` local pra função
            # INTEIRA — então a chamada do lado direito vira UnboundLocalError.
            # Caía no `except` e a auditoria imprimia "não consegui ler a ordem
            # do daemon" em 18/08, um dia depois do conserto. O aviso salvou:
            # ele foi escrito pra dizer "não sei" em vez de chutar, e foi isso
            # que expôs o defeito em vez de escondê-lo atrás de um palpite.
            _conf = _cfg()
            _modo = str(_conf.get("ordem_da_fila", "auto")).strip().lower()
            if _modo == "mais_antigo":
                _drenando = True
            elif _modo == "mais_novo":
                _drenando = False
            elif c["validade_dias"] <= 0:
                _drenando = False
            else:
                _frac = float(_conf.get("limiar_drenagem", 0.4))
                _frac = max(0.0, min(1.0, _frac))
                _drenando = (e["mais_antigo_dias"]
                             > c["validade_dias"] * _frac)
        except Exception:
            _drenando = None
        if _drenando is True:
            _ordem = ("a ordem AGORA é MAIS ANTIGO primeiro (drenagem ligada), "
                      "então quem tende a vencer é o material NOVO")
        elif _drenando is False:
            _ordem = ("a ordem é MAIS NOVO primeiro, então é sempre o mesmo "
                      "rabo antigo que espera")
        else:
            _ordem = ("não consegui ler a ordem do daemon — confira no log "
                      "dele qual modo está ativo")
        fora.append((
            "A FILA NÃO DRENA ANTES DE VENCER",
            f"{e['visiveis_pro_daemon']} pacotes ÷ {c['ritmo_real_por_dia']}"
            f"/dia (ritmo REAL) = {dr} dias pra esvaziar, contra validade de "
            f"{c['validade_dias']} dias. Como {_ordem}: "
            f"~{sobra} pacote(s) tendem a vencer sem nunca sair.",
            f"no ritmo configurado ({c['capacidade_semanal_total']}/semana) "
            f"seriam {c['semanas_pra_drenar'] * 7:.0f} dias — cabe na validade. "
            "A diferença entre os dois é o problema."))

    esperado_7d = c["capacidade_semanal_total"]
    if esperado_7d and p["ultimos_7d"] < esperado_7d * 0.5:
        fora.append((
            "PUBLICAÇÃO ABAIXO DA CAPACIDADE",
            f"{p['ultimos_7d']} post(s) em 7 dias contra capacidade de "
            f"{esperado_7d}. Está saindo "
            f"{100 * p['ultimos_7d'] / esperado_7d:.0f}% do configurado.",
            f"série (dia, posts): {p['serie'][:7]}"))

    if p["ultimas_24h"] == 0 and p["ultimos_3d"] == 0:
        fora.append((
            "NADA PUBLICADO EM 3 DIAS",
            "Nenhum registro em `agendador_historico.json` nos últimos 3 dias. "
            "Ou o ciclo de postagem não roda, ou roda e falha antes de "
            "registrar.",
            f"último dia com registro: "
            f"{next((d for d, n in p['serie'] if n), 'nenhum na janela')}"))

    # ── envelhecimento: quanto do estoque está perto de virar prejuízo ──────
    env = e.get("envelhecendo") or {}
    if env.get("em_risco"):
        v = c["validade_dias"]
        fora.append((
            "ESTOQUE ENVELHECENDO",
            f"{env['em_risco']} pacote(s) a menos de 7 dias de vencer "
            f"(validade {v}d) — produção já paga que vira zero se não sair.",
            " · ".join(f">{k}d: {n}" for k, n in env["escadinha"].items())))

    if e["ja_marcados_postados"] > e["total_pastas"] * 0.2:
        fora.append((
            "O NÚMERO DA ESTEIRA ESTÁ INFLADO",
            f"{e['ja_marcados_postados']} das {e['total_pastas']} pastas JÁ "
            "foram postadas e continuam em pronto_para_postar/ — só saem "
            f"quando vencem ({c['validade_dias']}d). O estoque real é "
            f"{e['visiveis_pro_daemon']}, não {e['total_pastas']}.",
            "quem olha a pasta (inclusive eu, na revisão geral) vê quase o "
            "dobro do que existe pra postar"))

    if e["vencidos_ainda_na_pasta"]:
        fora.append((
            "VENCIDOS NÃO EXPURGADOS",
            f"{e['vencidos_ainda_na_pasta']} pacote(s) passaram de "
            f"{c['validade_dias']} dias e continuam em pronto_para_postar/. "
            "O expurgo roda no ciclo de postagem — se eles estão aqui, o "
            "ciclo pode não estar rodando.",
            f"amostra: {r['amostras']['vencidos_ainda_na_pasta'][:3]}"))

    sem_conta = r["por_conta"].get("SEM conta.json")
    if sem_conta:
        fora.append((
            "PACOTES SEM DONO",
            f"{sem_conta['pacotes']} pacote(s) sem `conta.json` — postam com a "
            "marca de 'geral' (defeito conhecido de 08/08).", ""))

    if r["erros"]["por_arquivo"]:
        fora.append((
            "ERROS DE PUBLICAÇÃO NO LOG (72h)",
            f"{sum(r['erros']['por_arquivo'].values())} linha(s) em "
            f"{len(r['erros']['por_arquivo'])} arquivo(s).",
            " | ".join(r["erros"]["exemplos"][:2])))

    return fora


def main():
    p = argparse.ArgumentParser(
        description="Diagnóstico da fila de publicação. SÓ LÊ.")
    p.add_argument("--json", action="store_true")
    p.add_argument("--dias", type=int, default=7)
    args = p.parse_args()

    r = auditar(args.dias)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
        return 0

    e, c, pu = r["estoque"], r["capacidade"], r["publicacao"]
    L = "═" * 58
    print(f"\n{L}\n        AUDITORIA DE PUBLICAÇÃO · {datetime.now():%d/%m %H:%M}\n{L}")
    print(f"  fonte: {r['como_mediu']}")
    print(f"  pasta: {r['pasta']}")

    print(f"\n  ESTOQUE")
    print(f"    {e['total_pastas']} pastas em pronto_para_postar/")
    print(f"    {e['visiveis_pro_daemon']} que o daemon ENXERGA como postável")
    print(f"    {e['sem_video_mp4']} sem video.mp4      "
          f"{e['ja_marcados_postados']} já marcados postados      "
          f"{e['vencidos_ainda_na_pasta']} vencidos ainda na pasta")
    print(f"    mais antigo: {e['mais_antigo_dias']} dias · "
          f"fila_vencida/: {e['fila_vencida_dir']}")
    print(f"    idades: " + " · ".join(f"{k} {v}"
                                       for k, v in e["faixas_de_idade"].items()))
    if isinstance(r["fila_do_daemon"], int):
        print(f"    conferência: o daemon monta uma fila de "
              f"{r['fila_do_daemon']} (meu cálculo: {e['visiveis_pro_daemon']})")

    print(f"\n  POR CONTA")
    for conta, d in r["por_conta"].items():
        print(f"    {conta:24} {d['pacotes']:4} pacotes · mais antigo "
              f"{d['mais_antigo_dias']:5}d · mediana {d['mediana_dias']}d")

    print(f"\n  PUBLICAÇÃO  (vídeos, não slots)")
    print(f"    últimas 24h: {pu['ultimas_24h']}   últimos 3d: {pu['ultimos_3d']}"
          f"   últimos 7d: {pu['ultimos_7d']}")
    print(f"    média/dia: {pu['media_por_dia']} · total no histórico: "
          f"{pu['total_historico']}")
    print("    vídeos/dia: " + " ".join(f"{d[5:]}={n}" for d, n in pu["serie"]))
    print("    slots/dia:  " + " ".join(f"{d[5:]}={n}"
                                        for d, n in pu["serie_slots"]))
    if pu["por_conta"]:
        print("    por conta na janela: " + " · ".join(
            f"{c} {n}" for c, n in pu["por_conta"].items()))

    print(f"\n  CAPACIDADE CONFIGURADA")
    print(f"    pirâmide {c['piramide']} = {c['posts_por_conta_semana']}/conta/semana")
    print(f"    {c['contas']} contas → {c['capacidade_semanal_total']}/semana")
    print(f"    validade {c['validade_dias']}d · janela {c['janela']} · "
          f"post_por_conta={c['post_por_conta']}")
    if c["semanas_pra_drenar"]:
        print(f"    no ritmo CONFIGURADO: {c['semanas_pra_drenar'] * 7:.0f} "
              f"dias pra drenar {e['visiveis_pro_daemon']} pacotes")
    if c.get("dias_pra_drenar_no_ritmo_real"):
        print(f"    no ritmo REAL ({c['ritmo_real_por_dia']}/dia): "
              f"{c['dias_pra_drenar_no_ritmo_real']} dias   "
              f"← este é o que vale, validade {c['validade_dias']}d")

    print(f"\n{L}\n  GARGALO\n{L}")
    ver = _veredito(r)
    if not ver:
        print("  nenhum gargalo detectado pelos critérios desta auditoria.")
    for i, (titulo, causa, evid) in enumerate(ver, 1):
        print(f"\n  {i}. {titulo}")
        print(f"     causa: {causa}")
        if evid:
            print(f"     evidência: {evid}")

    print(f"\n  os 10 visíveis mais antigos:")
    for s, conta, idade in r["amostras"]["mais_antigos_visiveis"]:
        print(f"     {idade:5}d  {conta:20} {s[:44]}")
    print("\n  NADA FOI ALTERADO. Este script só lê.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
