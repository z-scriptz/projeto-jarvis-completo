#!/usr/bin/env python3
# revisao_geral.py -- um comando que olha o sistema inteiro e diz o que está
#                     quebrado, o que está estranho e o que está ok.
#
# POR QUE EXISTE (11/08)
# O Dre pediu: "roda um comando pra gente analisar geral, o site, o jarvis, ver
# se tem algum erro, ou aconteceu algo". Até hoje a resposta pra isso era abrir
# seis scripts diferentes (check_ambiente, conferir, conferir_esteira,
# health_check, diag_contas...) e juntar de cabeça. Isso não é revisão, é
# arqueologia.
#
# E o gatilho imediato foi pior: naquele mesmo dia ele rodou `python3 piloto.py`
# em vez de `.venv/bin/python piloto.py` e levou um ModuleNotFoundError de PIL.
# Nada no sistema avisava que existiam DOIS interpretadores e que só um deles
# servia. Por isso o PRIMEIRO bloco daqui é justamente esse.
#
# REGRAS DESTE ARQUIVO
# ───────────────────
# 1. SÓ LÊ. Não cria, não move, não apaga, não posta, não faz rede. Pode rodar
#    com o daemon no ar, a qualquer hora, sem medo.
# 2. SÓ STDLIB. Se ele dependesse de PIL ou requests, morreria exatamente no
#    ambiente quebrado que ele existe pra diagnosticar.
# 3. NUNCA imprime valor de segredo. Chave de API, token e senha aparecem como
#    "definida"/"faltando" e mais nada. O Dre lê esta saída no Telegram, e o
#    ROADMAP é explícito: segredo não passa por chat.
# 4. Cada bloco falha sozinho. Um `shared/` corrompido não pode impedir a
#    checagem do systemd — o dia em que tudo está ruim é justamente o dia em
#    que a revisão precisa terminar.
#
# Uso:
#   python3 revisao_geral.py              # roda em qualquer python
#   python3 revisao_geral.py --json       # pra outro programa consumir
#   python3 revisao_geral.py --tudo       # mostra também o que passou

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

FALHA, ALERTA, OK, INFO = "falha", "alerta", "ok", "info"
ICONE = {FALHA: "✗", ALERTA: "⚠", OK: "✓", INFO: "·"}

# Bibliotecas que o pipeline REALMENTE usa. Cada uma com quem morre sem ela —
# lista sem dono vira lista que ninguém corrige.
LIBS = [
    ("PIL", "render.py, piloto.py (desenha a moldura e os enquadramentos)"),
    ("requests", "piloto.py, deploy_site.py (baixa foto, checa link)"),
    ("dotenv", "carrega o .env"),
]
LIBS_OPCIONAIS = [
    ("playwright", "coletor_assets.py, ig_playwright.py"),
    ("google.genai", "auditor.py, visual_audit_agent.py (Gemini Vision)"),
]

# Nomes de env que interessam. Só os NOMES — o valor nunca é impresso.
ENV_ESPERADO = [
    ("ELEVENLABS_API_KEY", "narração"),
    ("GEMINI_API_KEY", "auditoria visual"),
    ("TELEGRAM_BOT_TOKEN", "avisos"),
    ("TELEGRAM_ADMIN_CHAT_ID", "avisos"),
]

SERVICOS = ["jarvis.service", "tiktok_painel.service"]

_achados = []


def _diz(estado, bloco, msg, detalhe=""):
    _achados.append({"estado": estado, "bloco": bloco, "msg": msg,
                     "detalhe": detalhe})


def _idade(p: Path) -> str:
    try:
        h = (time.time() - p.stat().st_mtime) / 3600
    except Exception:
        return "?"
    if h < 1:
        return f"{int(h * 60)}min"
    if h < 48:
        return f"{h:.0f}h"
    return f"{h / 24:.0f}d"


def _sh(cmd, timeout=15):
    """Roda comando e devolve (codigo, saida). Nunca levanta."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, cwd=str(RAIZ))
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return -1, str(e)[:120]


def _json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


# ── 1. interpretador e bibliotecas ──────────────────────────────────────────
def bloco_ambiente():
    B = "ambiente"
    venv = RAIZ / ".venv" / "bin" / "python"
    atual = Path(sys.executable).resolve()

    _diz(INFO, B, f"python em uso: {sys.executable} ({sys.version.split()[0]})")

    if venv.exists():
        if atual != venv.resolve():
            # ESTE é o achado que motivou o arquivo. Não é detalhe: é a
            # diferença entre o piloto rodar e explodir no import.
            _diz(ALERTA, B,
                 "você está FORA do .venv — o pipeline não roda assim",
                 f"use: {venv} em vez de {sys.executable}")
        else:
            _diz(OK, B, "rodando dentro do .venv")
    else:
        _diz(ALERTA, B, f"não achei .venv em {venv.parent.parent}")

    for mod, dono in LIBS:
        try:
            __import__(mod)
            _diz(OK, B, f"{mod} instalado")
        except Exception as e:
            _diz(FALHA, B, f"{mod} FALTANDO — quebra {dono}",
                 str(e)[:80])
    for mod, dono in LIBS_OPCIONAIS:
        try:
            __import__(mod)
            _diz(OK, B, f"{mod} instalado")
        except Exception:
            _diz(INFO, B, f"{mod} ausente (opcional; afeta {dono})")

    livre = None
    try:
        st = os.statvfs(str(RAIZ))
        livre = st.f_bavail * st.f_frsize / (1024 ** 3)
    except Exception:
        pass
    if livre is not None:
        if livre < 1:
            _diz(FALHA, B, f"disco quase cheio: {livre:.1f} GB livres")
        elif livre < 5:
            _diz(ALERTA, B, f"disco apertado: {livre:.1f} GB livres")
        else:
            _diz(OK, B, f"disco: {livre:.1f} GB livres")


# ── 2. env (nomes, nunca valores) ───────────────────────────────────────────
def bloco_env():
    B = "env"
    env = RAIZ / ".env"
    nomes = set()
    if not env.exists():
        _diz(ALERTA, B, ".env não existe nesta pasta",
             "normal se as variáveis vêm do systemd")
    else:
        try:
            nomes = set()
            for linha in env.read_text(encoding="utf-8",
                                       errors="replace").splitlines():
                linha = linha.strip()
                if linha and not linha.startswith("#") and "=" in linha:
                    nomes.add(linha.split("=", 1)[0].strip())
            _diz(OK, B, f".env presente com {len(nomes)} variáveis")
        except Exception as e:
            _diz(ALERTA, B, f".env ilegível: {str(e)[:60]}")
            nomes = set()
    for nome, pra_que in ENV_ESPERADO:
        # Presença no processo OU no arquivo. O daemon recebe pelo systemd, o
        # terminal lê do arquivo — checar só um dos dois dá falso negativo.
        tem = bool(os.environ.get(nome)) or (env.exists() and nome in nomes)
        if tem:
            _diz(OK, B, f"{nome} definida")
        else:
            _diz(ALERTA, B, f"{nome} não encontrada — afeta {pra_que}")


# ── 3. git: o que está instalado é o que eu acho que está? ──────────────────
def bloco_git():
    B = "git"
    cod, ramo = _sh(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if cod != 0:
        _diz(INFO, B, "esta pasta não é um repositório git")
        return
    cod, curto = _sh(["git", "rev-parse", "--short", "HEAD"])
    _diz(INFO, B, f"HEAD {curto} ({ramo})")

    cod, sujo = _sh(["git", "status", "--porcelain"])
    if sujo:
        linhas = sujo.splitlines()
        # Na VPS os arquivos chegam por `git show FETCH_HEAD:x > x`, então
        # "modificado" aqui quase sempre significa "atualizado à mão" — o que
        # é o fluxo normal, não um problema. Por isso é alerta, não falha.
        # split, não l[3:]: o _sh dá strip() na saída inteira e come o espaço
        # da PRIMEIRA linha (' M piloto.py' vira 'M piloto.py'), então cortar
        # por posição fixa comia a inicial do nome — apareceu "iloto.py".
        _diz(ALERTA, B, f"{len(linhas)} arquivo(s) diferentes do HEAD",
             ", ".join(l.split(maxsplit=1)[-1] for l in linhas[:8]))
    else:
        _diz(OK, B, "árvore limpa")

    cod, remotos = _sh(["git", "remote"])
    if "pjc" in remotos.split():
        cod, atras = _sh(["git", "rev-list", "--count", "HEAD..pjc/" + ramo])
        if cod == 0 and atras.isdigit() and int(atras) > 0:
            _diz(ALERTA, B, f"{atras} commit(s) atrás de pjc/{ramo}",
                 "sem rede aqui: rode `git fetch pjc` pra atualizar a conta")
        elif cod == 0:
            _diz(OK, B, f"em dia com pjc/{ramo} (última referência local)")


# ── 4. a fila de produtos ───────────────────────────────────────────────────
def bloco_fila():
    B = "fila"
    fila = RAIZ / "shared" / "produtos_fila.json"
    if not fila.exists():
        _diz(FALHA, B, f"não achei {fila}")
        return
    try:
        itens = [x for x in _json(fila) if isinstance(x, dict)]
    except Exception as e:
        _diz(FALHA, B, f"fila ilegível: {str(e)[:80]}")
        return

    sem_foto, sem_link, nomes = [], 0, {}
    for i, it in enumerate(itens):
        urls = [u for u in ([it.get("imagem")] + (it.get("imagens") or []))
                if isinstance(u, str) and u.startswith("http")]
        if not urls:
            sem_foto.append(i)
        if not (it.get("link") or "").startswith("http"):
            sem_link += 1
        nome = (it.get("campeao") or it.get("produto") or "").strip().lower()
        if nome:
            nomes[nome] = nomes.get(nome, 0) + 1

    _diz(INFO, B, f"{len(itens)} produtos · atualizada há {_idade(fila)}")

    if sem_foto:
        pct = 100 * len(sem_foto) / max(1, len(itens))
        estado = FALHA if pct > 30 else ALERTA
        _diz(estado, B,
             f"{len(sem_foto)} produto(s) sem foto ({pct:.0f}%) — "
             f"o piloto recusa esses índices",
             "índices: " + ", ".join(str(i) for i in sem_foto[:15]))
    else:
        _diz(OK, B, "todos os produtos têm foto")

    if sem_link:
        _diz(ALERTA, B, f"{sem_link} produto(s) sem link de afiliado "
                        "(vídeo sem comissão)")
    repetidos = [n for n, c in nomes.items() if c > 1]
    if repetidos:
        _diz(ALERTA, B, f"{len(repetidos)} nome(s) repetido(s) na fila",
             "; ".join(n[:40] for n in repetidos[:5]))


# ── 5. a esteira de vídeos prontos ──────────────────────────────────────────
def bloco_esteira():
    B = "esteira"
    pronto = RAIZ / "pronto_para_postar"
    if not pronto.exists():
        _diz(INFO, B, "pasta pronto_para_postar não existe aqui")
        return
    pastas = [p for p in pronto.iterdir() if p.is_dir()]
    if not pastas:
        _diz(ALERTA, B, "esteira VAZIA — nada pra postar")
        return

    sem_conta, sem_video = [], []
    for p in pastas:
        if not (p / "conta.json").exists():
            sem_conta.append(p.name)
        if not any(p.glob("*.mp4")):
            sem_video.append(p.name)

    pastas.sort(key=lambda p: p.stat().st_mtime)
    _diz(INFO, B, f"{len(pastas)} pacote(s) · mais antigo há "
                  f"{_idade(pastas[0])}")

    if sem_conta:
        # Este é o defeito de 08/08: pacote sem conta.json vira "geral" e sai
        # com a marca da conta errada. Não é cosmético.
        _diz(FALHA, B,
             f"{len(sem_conta)} pacote(s) SEM conta.json — vão postar com a "
             f"marca errada",
             ", ".join(sem_conta[:6]))
    else:
        _diz(OK, B, "todo pacote sabe de que conta é")
    if sem_video:
        _diz(ALERTA, B, f"{len(sem_video)} pacote(s) sem .mp4",
             ", ".join(sem_video[:6]))


# ── 6. os últimos renders ───────────────────────────────────────────────────
def bloco_renders():
    B = "render"
    pasta = RAIZ / "shared" / "renders"
    if not pasta.exists():
        _diz(INFO, B, "nenhum render ainda")
        return
    rels = sorted(pasta.glob("*.relatorio.json"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    if not rels:
        _diz(INFO, B, "nenhum relatório de render")
        return

    _diz(INFO, B, f"{len(rels)} render(s) · último há {_idade(rels[0])}")
    try:
        r = _json(rels[0])
    except Exception as e:
        _diz(ALERTA, B, f"último relatório ilegível: {str(e)[:60]}")
        return

    dur = r.get("duracao_arquivo")
    _diz(INFO, B, f"último: {rels[0].stem.replace('.relatorio', '')[:40]} · "
                  f"{dur}s · {r.get('cortes')} cortes · "
                  f"{r.get('narracoes')} narração(ões)")

    if r.get("mudo"):
        _diz(INFO, B, "o último rodou com --mudo (teste, sem narração)")
    elif not r.get("narracoes"):
        _diz(ALERTA, B, "o último saiu SEM narração e não era teste")

    knobs = r.get("knobs") or {}
    if knobs:
        _diz(INFO, B, "knobs do último: " +
             " ".join(f"{k}={v}" for k, v in knobs.items()))
    else:
        # Sem isso não dá pra saber se um vídeo saiu do build novo ou velho —
        # foi exatamente a confusão do selo em 10/08.
        _diz(ALERTA, B, "o último relatório não tem 'knobs' (build antigo)")

    faltou = r.get("faltou") or []
    if faltou:
        _diz(INFO, B, f"{len(faltou)} pendência(s) conhecida(s) no render",
             " | ".join(str(x)[:70] for x in faltou[:4]))


# ── 7. contas e vozes ───────────────────────────────────────────────────────
def bloco_contas():
    B = "contas"
    arq = RAIZ / "contas.json"
    if not arq.exists():
        _diz(ALERTA, B, "contas.json não existe")
        return
    try:
        d = _json(arq)
    except Exception as e:
        _diz(FALHA, B, f"contas.json ilegível: {str(e)[:70]}")
        return
    if not isinstance(d, dict):
        _diz(ALERTA, B, "contas.json não é um objeto")
        return

    # `_default` é modelo, não conta. Cobrar voz e ID dele gera alerta que
    # ninguém pode resolver.
    reais = {k: v for k, v in d.items() if not k.startswith("_")}
    _diz(INFO, B, f"{len(reais)} conta(s): {', '.join(sorted(reais))}")
    sem_voz, sem_id = [], []
    for nicho, c in reais.items():
        if not isinstance(c, dict):
            continue
        # a voz pode vir do contas.json OU do .env — checar só um dos dois
        # acusa falta onde não há
        if not (c.get("voz_id")
                or os.environ.get(f"ELEVENLABS_VOICE_ID_{nicho.upper()}")):
            sem_voz.append(nicho)
        # o campo se chama instagram_user_id. Eu tinha escrito ig_user_id e o
        # revisor acusou as 4 contas de estarem sem ID — todas tinham.
        if not c.get("instagram_user_id"):
            sem_id.append(nicho)
    if sem_voz:
        _diz(ALERTA, B, f"{len(sem_voz)} conta(s) sem voz própria "
                        f"(caem na voz padrão)", ", ".join(sem_voz))
    else:
        _diz(OK, B, "toda conta tem voz definida")
    if sem_id:
        _diz(ALERTA, B, f"{len(sem_id)} conta(s) sem ID do Instagram",
             ", ".join(sem_id))

    # A pegadinha de 10/08: o .env sobrescreve o contas.json em silêncio.
    for nicho in reais:
        chave = f"ELEVENLABS_VOICE_ID_{nicho.upper()}"
        if os.environ.get(chave):
            _diz(INFO, B, f"{chave} no ambiente MANDA sobre contas.json "
                          f"para '{nicho}'")


# ── 8. o site ───────────────────────────────────────────────────────────────
def bloco_site():
    B = "site"
    dir_site = Path(os.environ.get("TOPSHOP_SITE_DIR",
                                   str(Path.home() / "topshop-site")))
    if not dir_site.exists():
        _diz(ALERTA, B, f"clone do site não existe em {dir_site}",
             "deploy_site.py não tem pra onde publicar")
        return
    idx = dir_site / "index.html"
    if idx.exists():
        h = (time.time() - idx.stat().st_mtime) / 3600
        estado = ALERTA if h > 72 else OK
        _diz(estado, B, f"index.html gerado há {_idade(idx)}"
             + (" — vitrine parada" if h > 72 else ""))
    else:
        _diz(FALHA, B, "index.html não existe no clone do site")

    cod, saida = _sh(["git", "-C", str(dir_site), "status", "--porcelain"])
    if cod == 0 and saida:
        _diz(ALERTA, B, "site tem mudanças não publicadas",
             f"{len(saida.splitlines())} arquivo(s)")
    elif cod == 0:
        _diz(OK, B, "site sem pendências locais")

    cache = RAIZ / "shared" / "health_cache.json"
    if cache.exists():
        _diz(INFO, B, f"health_cache dos links: {_idade(cache)}")


# ── 9. serviços ─────────────────────────────────────────────────────────────
def bloco_servicos():
    B = "serviço"
    cod, _ = _sh(["which", "systemctl"])
    if cod != 0:
        _diz(INFO, B, "systemctl indisponível aqui")
        return
    for s in SERVICOS:
        cod, estado = _sh(["systemctl", "is-active", s])
        estado = (estado or "?").splitlines()[0]
        if "not been booted with systemd" in estado:
            # container de desenvolvimento: systemctl existe, systemd não é
            # PID 1. Isso não é serviço caído, é máquina diferente — reportar
            # como falha aqui enche a lista de ação com coisa que não é ação.
            _diz(INFO, B, "sem systemd nesta máquina (não é a VPS) — "
                          "serviços não verificáveis")
            return
        if estado == "active":
            _diz(OK, B, f"{s} ativo")
        elif estado in ("inactive", "unknown"):
            _diz(INFO, B, f"{s}: {estado}")
        else:
            _diz(FALHA, B, f"{s}: {estado}")


# ── 10. travas esquecidas ───────────────────────────────────────────────────
def _processo_vivo(pid: int, nome: str) -> bool:
    """O PID existe E parece ser o job certo? Só leitura de /proc.

    Checar o PID em vez de tentar pegar o flock mantém a promessa de "só lê":
    adquirir a trava, mesmo por microssegundos, faria um cron que subisse
    naquele instante desistir da rodada.
    """
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().decode(
            "utf-8", "replace").replace("\x00", " ")
    except Exception:
        return False
    # PID é reciclado; o nome do job na linha de comando dá a confirmação
    return nome.split("_")[0] in cmd or nome in cmd


def bloco_travas():
    B = "travas"
    # ⚠️ ARQUIVO DE TRAVA VELHO NÃO É TRAVA PRESA. `shared/trava.py` usa flock,
    # e o cabeçalho dele diz o porquê: "o flock é solto pelo KERNEL quando o
    # processo morre — inclusive com -9 ou reboot". O arquivo `.trava_*` nunca
    # é apagado, então ele sobrevive à execução e o que a data dele conta é
    # QUANDO AQUELE JOB RODOU PELA ÚLTIMA VEZ.
    # A primeira versão deste bloco dizia "provável processo morto sem soltar a
    # trava" e assustou à toa — era exatamente o contrário do que o mecanismo
    # garante. Quem responde de verdade é o PID gravado dentro do arquivo.
    travas = list(RAIZ.glob(".trava_*")) + list((RAIZ / "shared").glob(".trava_*"))
    if not travas:
        _diz(INFO, B, "nenhum arquivo de trava (nenhum job com trava rodou "
                      "nesta pasta)")
        return

    presas, ociosas = [], []
    for p in sorted(travas, key=lambda q: q.stat().st_mtime):
        nome = p.name.replace(".trava_", "")
        try:
            pid = int((p.read_text(errors="replace").strip() or "0"))
        except Exception:
            pid = 0
        if pid and _processo_vivo(pid, nome):
            presas.append((nome, pid, _idade(p)))
        else:
            ociosas.append((nome, _idade(p)))

    for nome, pid, idade in presas:
        h = idade
        _diz(ALERTA, B, f"{nome} está RODANDO agora (pid {pid}), desde {h}",
             "se isso passar de algumas horas, é processo pendurado")
    if ociosas:
        _diz(OK, B, f"{len(ociosas)} trava(s) livre(s) — nenhuma presa")
        # a data vira relógio: "quando este job rodou pela última vez"
        _diz(INFO, B, "última execução de cada job: " + " · ".join(
            f"{n} {i}" for n, i in ociosas))


# ── 11. erros recentes nos logs ─────────────────────────────────────────────
def bloco_logs():
    B = "logs"
    arqs = [p for p in list(RAIZ.glob("*.log")) + list(RAIZ.glob("logs/*.log"))
            if p.is_file()]
    if not arqs:
        _diz(INFO, B, "nenhum .log nesta pasta (o daemon loga no journald)")
        return
    limite = time.time() - 24 * 3600
    total, exemplos = 0, []
    for p in arqs:
        if p.stat().st_mtime < limite:
            continue
        try:
            # só o rabo do arquivo: log de daemon passa de centenas de MB
            with p.open("rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - 400_000))
                texto = f.read().decode("utf-8", errors="replace")
        except Exception:
            continue
        for linha in texto.splitlines():
            if ("Traceback" in linha or "ERROR" in linha
                    or "CRITICAL" in linha):
                total += 1
                if len(exemplos) < 4:
                    exemplos.append(f"{p.name}: {linha.strip()[:100]}")
    if total:
        _diz(ALERTA, B, f"{total} linha(s) de erro nas últimas 24h",
             " | ".join(exemplos))
    else:
        _diz(OK, B, f"{len(arqs)} log(s), nenhum erro nas últimas 24h")


BLOCOS = [
    ("ambiente", bloco_ambiente), ("env", bloco_env), ("git", bloco_git),
    ("fila", bloco_fila), ("esteira", bloco_esteira),
    ("render", bloco_renders), ("contas", bloco_contas), ("site", bloco_site),
    ("serviços", bloco_servicos), ("travas", bloco_travas),
    ("logs", bloco_logs),
]


def main():
    p = argparse.ArgumentParser(
        description="Revisão geral do Jarvis. SÓ LÊ — não altera nada.")
    p.add_argument("--json", action="store_true")
    p.add_argument("--tudo", action="store_true",
                   help="mostra também o que passou, não só os problemas")
    args = p.parse_args()

    for nome, fn in BLOCOS:
        try:
            fn()
        except Exception as e:
            # Um bloco que explode não pode levar a revisão junto — o dia em
            # que tudo está ruim é o dia em que ela mais importa.
            _diz(FALHA, nome, f"a própria checagem falhou: {str(e)[:90]}")

    if args.json:
        print(json.dumps(_achados, ensure_ascii=False, indent=2))
        return 1 if any(a["estado"] == FALHA for a in _achados) else 0

    falhas = [a for a in _achados if a["estado"] == FALHA]
    alertas = [a for a in _achados if a["estado"] == ALERTA]

    print(f"\n  REVISÃO GERAL · {datetime.now():%d/%m %H:%M} · {RAIZ}")
    print("  " + "─" * 66)

    mostrar = _achados if args.tudo else [
        a for a in _achados if a["estado"] in (FALHA, ALERTA, INFO)]
    atual = None
    for a in mostrar:
        if a["bloco"] != atual:
            atual = a["bloco"]
            print(f"\n  [{atual}]")
        print(f"   {ICONE[a['estado']]} {a['msg']}")
        if a["detalhe"]:
            print(f"       {a['detalhe']}")

    print("\n  " + "─" * 66)
    oks = sum(1 for a in _achados if a["estado"] == OK)
    print(f"  {len(falhas)} falha(s) · {len(alertas)} alerta(s) · {oks} ok")
    if falhas:
        print("\n  PRECISA DE AÇÃO:")
        for a in falhas:
            print(f"   ✗ [{a['bloco']}] {a['msg']}")
    elif not alertas:
        print("  nada quebrado.")
    if not args.tudo:
        print("\n  (--tudo mostra também o que passou · --json pra consumir)")
    print()
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
