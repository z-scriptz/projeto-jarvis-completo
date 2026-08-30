#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# fechar_ciclo.py — devolve o resultado do post pra dentro da decisão.
#
# ⚠️ O CÉREBRO DO CARROSSEL TEM UMA FASE 2 QUE NUNCA ACORDOU (30/08).
# `carrossel_brain._salvamento_por_formato()` lê `reach` e `saved` do ledger pra
# inclinar a escolha de formato pelo que de fato gera salvamento. Só que o
# ledger é escrito NA HORA DE PUBLICAR — quando o post acabou de nascer e não
# tem alcance nenhum — e ninguém nunca voltava pra preencher.
#
# Resultado medido: `taxas` saía sempre vazio e a escolha caía eternamente em
# "distribuição-alvo (ainda sem salvamento medido)", que foi literalmente o que
# o log imprimiu no primeiro slot real, nas seis contas. O sistema produzia bem
# e não aprendia nada.
#
# 📌 Medição que não volta pra decisão é relatório, não aprendizado. O alcance
# de cada post está em `metricas_posts.jsonl` há meses; faltava a ponte.
#
# ⚠️ POST NOVO MENTE. Medido duas horas depois de publicar, um post tem uma
# fração do alcance final e uma proporção de salvamento que não representa nada.
# Se isso entrasse no ledger, o cérebro aprenderia com número imaturo e passaria
# a favorecer o formato que por acaso foi medido primeiro. Por isso só entra
# post com pelo menos `IDADE_MINIMA_H` horas — e quando o `metricas_posts` medir
# de novo, o número aqui melhora junto.
#
# USO (na VPS, dentro de ~/jarvis):
#   .venv/bin/python fechar_ciclo.py                # mostra o que faria
#   .venv/bin/python fechar_ciclo.py --aplicar      # escreve no ledger
#   .venv/bin/python fechar_ciclo.py --ver          # o que o cérebro já enxerga
#
# Ordem certa do dia:  metricas_posts.py  →  fechar_ciclo.py --aplicar

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

LEDGER = BASE_DIR / "shared" / "carrosseis_ledger.jsonl"
METRICAS = BASE_DIR / "shared" / "metricas_posts.jsonl"

# ⚠️ 24H É O PISO, não o ideal. Um Reel/carrossel continua ganhando alcance por
# dias; 24h é onde a ordem entre formatos para de mudar por ruído. Abaixo disso
# o dado existe mas não decide nada — e decidir com ele é pior que esperar.
IDADE_MINIMA_H = 24

# Só estes voltam pro ledger. `likes` e `comments` ficam de fora de propósito:
# o cérebro mede SALVAMENTO por mil de alcance, e trazer campo que ninguém lê
# engorda o arquivo e convida alguém a inventar uma regra em cima dele depois.
CAMPOS = ("reach", "saved")


def _log(m):
    print(f"   {m}", flush=True)


def _linhas(caminho: Path) -> list:
    if not caminho.exists():
        return []
    saida = []
    for ln in caminho.read_text(encoding="utf-8", errors="ignore").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            d = json.loads(ln)
            if isinstance(d, dict):
                saida.append(d)
        except Exception:
            continue          # linha torta não derruba o arquivo inteiro
    return saida


def _shortcode(url: str) -> str:
    """O código do post a partir da URL. Reusa o do `metricas_posts`.

    ⚠️ IMPORTADO, NÃO COPIADO. É a mesma regra dos dois lados da ponte; se
    divergir, o cruzamento passa a não casar e o sintoma é "0 fechados" — que
    parece 'ainda não tem dado' e não 'a chave está errada'."""
    for mod in ("metricas_posts", "agents.metricas_posts"):
        try:
            import importlib
            return importlib.import_module(mod)._shortcode(url) or ""
        except Exception:
            continue
    # sem o módulo, o mínimo honesto: o penúltimo pedaço de /reel/<code>/
    partes = [p for p in str(url or "").split("?")[0].split("/") if p]
    return partes[-1] if partes else ""


def _medidos() -> dict:
    """{shortcode: {reach, saved, medido_em}} — a MEDIÇÃO MAIS RECENTE.

    ⚠️ O MESMO POST É MEDIDO VÁRIAS VEZES, e o alcance só cresce. Guardar a
    primeira leitura congelaria o post no valor que ele tinha no primeiro dia."""
    por_sc = {}
    for r in _linhas(METRICAS):
        sc = str(r.get("shortcode") or "")
        if not sc:
            continue
        quando = int(r.get("medido_em") or 0)
        atual = por_sc.get(sc)
        if atual and int(atual.get("medido_em") or 0) >= quando:
            continue
        por_sc[sc] = r
    return por_sc


def _idade_h(rec: dict) -> float:
    ts = int(rec.get("ts") or 0)
    return (time.time() - ts) / 3600.0 if ts else 1e9


def _gravar(registros: list):
    """Reescrita atômica. O cérebro lê este arquivo em toda montagem de plano;
    um arquivo truncado no meio da gravação apaga o aprendizado inteiro."""
    tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False,
                                      dir=str(LEDGER.parent))
    try:
        for r in registros:
            tmp.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, LEDGER)
    except Exception:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def ver() -> int:
    """O que o cérebro enxerga HOJE — a mesma função que ele usa pra decidir."""
    try:
        from carrossel_brain import _salvamento_por_formato, _ledger
    except Exception as e:
        _log(f"❌ não importei o carrossel_brain ({str(e)[:90]})")
        return 2
    regs = _ledger()
    if not regs:
        _log("ledger vazio — nenhum carrossel registrado ainda")
        return 1
    contas = sorted({r.get("conta", "") for r in regs if r.get("conta")})
    com = sum(1 for r in regs if int(r.get("reach") or 0) > 0)
    _log(f"{len(regs)} carrossel(éis) no ledger · {com} com alcance medido")
    for c in contas:
        taxas = _salvamento_por_formato(c)
        if not taxas:
            _log(f"  {c:20} ainda sem salvamento medido → sorteia pelos pesos")
            continue
        ordem = sorted(taxas.items(), key=lambda x: -x[1])
        _log(f"  {c:20} " + " · ".join(f"{f} {t:.1f}/mil" for f, t in ordem))
    return 0


def rodar(aplicar: bool, idade_h: float) -> int:
    regs = _linhas(LEDGER)
    if not regs:
        _log(f"❌ {LEDGER} vazio — nenhum carrossel publicado registrado")
        _log("   (o registro acontece no publicar(); dry-run não registra)")
        return 1
    medidos = _medidos()
    if not medidos:
        _log(f"❌ {METRICAS.name} sem medições — rode antes: "
             f".venv/bin/python metricas_posts.py")
        return 1
    _log(f"ledger: {len(regs)} · posts medidos: {len(medidos)}")

    fechados, novos, jovens, sem_medida, sem_url = 0, 0, 0, 0, 0
    for r in regs:
        url = str(r.get("url") or "")
        if not url:
            # carrossel que não chegou a publicar (`registrar` grava url vazia
            # quando a Meta recusa) — não é falha aqui, é post que não existe
            sem_url += 1
            continue
        sc = _shortcode(url)
        m = medidos.get(sc)
        if not m:
            sem_medida += 1
            continue
        if _idade_h(r) < idade_h:
            jovens += 1
            continue
        alc = int(m.get("reach") or 0)
        if alc <= 0:
            # ⚠️ ALCANCE 0 NÃO ENTRA. Ou a métrica não veio, ou o post é novo
            # demais; gravar 0 aqui faria o cérebro somar um denominador vazio.
            sem_medida += 1
            continue
        antes = int(r.get("reach") or 0)
        novo = antes <= 0
        for c in CAMPOS:
            r[c] = int(m.get(c) or 0)
        r["medido_em"] = int(m.get("medido_em") or 0)
        fechados += 1
        novos += 1 if novo else 0

    _log(f"fecháveis: {fechados}  (novos: {novos}) · "
         f"jovens (<{idade_h:.0f}h): {jovens} · "
         f"sem medição: {sem_medida} · sem url: {sem_url}")
    if not fechados:
        _log("nada a escrever")
        return 0
    if not aplicar:
        _log("🧪 SIMULAÇÃO — nada gravado. Use --aplicar.")
        return 0
    _gravar(regs)
    _log(f"💾 ledger atualizado — {fechados} registro(s) com alcance")
    _log("")
    return ver()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Escreve o resultado dos posts de volta no ledger do "
                    "carrossel, pra fase 2 do cérebro sair do papel.")
    p.add_argument("--aplicar", action="store_true",
                   help="grava de verdade (sem isto, só simula)")
    p.add_argument("--ver", action="store_true",
                   help="só mostra o que o cérebro já enxerga hoje")
    p.add_argument("--idade-h", type=float, default=IDADE_MINIMA_H,
                   dest="idade_h",
                   help=f"horas mínimas do post (padrão {IDADE_MINIMA_H})")
    a = p.parse_args(argv)
    return ver() if a.ver else rodar(a.aplicar, max(0.0, a.idade_h))


if __name__ == "__main__":
    sys.exit(main())
