#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vigia.py -- O JARVIS OLHA AS 6 CONTAS TODO DIA, PRA VOCÊ NÃO PRECISAR.
#
# POR QUE EXISTE (19/08)
# ──────────────────────
# O Dre: *"não consigo ficar observando as 6 contas todos os dias... tem dias
# que eu entro e vejo as coisas, mas pode acontecer de eu ficar 3-4-5 dias sem
# entrar, e nesse intervalo acontece algo que muda a conta totalmente"*.
#
# ⚠️ A LIÇÃO QUE DESENHA ESTE ARQUIVO (e ela é de hoje de manhã)
# ──────────────────────────────────────────────────────────────
# O selo verificado passou semanas entrando em cima da última letra do
# "TopShop". Durante todo esse tempo:
#
#   • o log de produção dizia  ✔️ Selo verificado em x=462 (larg real=238)
#   • a `revisao_geral` dizia  render ok, knobs presentes
#   • eu conferi a aritmética  212+238+12 = 462 ✓ fechava
#
# **Tudo dizia saudável e o post estava torto.** A conta era consistente com
# ela mesma porque o código media um clip e desenhava outro. Quem viu o defeito
# foi o Dre, olhando o post no celular.
#
# Então um vigia feito de LOG teria falhado exatamente como eu falhei. Por isso
# a camada 1 deste arquivo não lê log nenhum: ela **abre o vídeo e olha o
# pixel**. E não olha procurando defeito conhecido — olha procurando MUDANÇA,
# porque não dá pra enumerar antes os defeitos que ainda não aconteceram. O que
# dá pra afirmar é: *o cabeçalho de ontem e o de hoje têm que ser iguais*.
#
# Foi um commit de 14/07 (margem anti-corte no 'p' de To**p**Shop) que quebrou
# o selo. Com este vigia no ar, no dia 15/07 chegaria no Telegram: "o cabeçalho
# do @topshop.__ mudou" com o antes e o depois. Um mês de post torto viraria
# um dia.
#
# AS QUATRO CAMADAS
# ─────────────────
#   1. O PIXEL      abre o vídeo, recorta a faixa do cabeçalho e compara com a
#                   referência guardada. Pega template, logo, selo, fonte, cor.
#   2. O PUBLICADO  Graph API nas contas: o post saiu? A LEGENDA foi junto?
#                   quanto alcançou? (é API oficial, não raspagem — não depende
#                   do proxy nem do WhatsApp Web)
#   3. A SÉRIE      compara com os dias anteriores e reporta MUDANÇA: produção
#                   parou, conta emudeceu, alcance despencou, hook novo subiu.
#   4. O SISTEMA    reaproveita a `revisao_geral` inteira em vez de reescrever.
#
# ⚠️ O NÍVEL 🕶️ CEGO É O CORAÇÃO DISTO
# Todo achado tem um nível, e um deles é CEGO: *não consegui olhar*. Sem ele o
# vigia mente por omissão — foi o que aconteceu com "101 erros nas últimas 24h"
# (a janela era o mtime do arquivo) e com "0 fontes podadas" (a poda nem rodou).
# **Silêncio não é saúde.** Se não deu pra olhar, o recado diz que não deu.
#
# ELE NÃO CONSERTA NADA. Não move pacote, não apaga, não posta, não reescreve
# config. Só lê, compara e conta. Consertar é decisão de quem lê o recado.
#
# Uso (VPS):
#   .venv/bin/python vigia.py                  # olha e imprime
#   .venv/bin/python vigia.py --telegram       # olha e manda o recado
#   .venv/bin/python vigia.py --inventario     # só mostra o que ele CONSEGUE ver
#   .venv/bin/python vigia.py --aprovar        # abençoa o cabeçalho atual
#   .venv/bin/python vigia.py --json
#
# No cron (uma vez por dia, de manhã):
#   0 9 * * * cd /root/jarvis && .venv/bin/python vigia.py --telegram >> \
#             /root/jarvis/logs/vigia.log 2>&1

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def _carregar_env():
    """⚠️ ANTES DE QUALQUER IMPORT QUE LEIA ENV. Hoje mesmo o `preview_layout`
    mostrou um header que não ia pro ar por ler os knobs sem o .env, e os knobs
    do WhatsApp nunca funcionaram manualmente pelo mesmo motivo. Aqui importa
    pro token do Graph e pro chat do Telegram."""
    for cand in (RAIZ / ".env", Path(".env")):
        if not cand.exists():
            continue
        try:
            linhas = cand.read_text(encoding="utf-8").splitlines()
        except Exception:
            return
        for linha in linhas:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            k, _, v = linha.partition("=")
            k = k.strip()
            if k and k not in os.environ:          # 1ª ocorrência vence
                os.environ[k] = v.strip().strip('"').strip("'")
        return


_carregar_env()

PRONTO = RAIZ / "pronto_para_postar"
CASA = RAIZ / "shared" / "vigia"          # referências, recortes e histórico
HISTORICO = CASA / "historico.jsonl"
LEDGER = RAIZ / "shared" / "posts_ledger.jsonl"
PUBLICADOS = RAIZ / "shared" / "publicados.jsonl"
METRICAS = RAIZ / "shared" / "metricas_posts.jsonl"

FALHA, ALERTA, CEGO, OK, INFO = "falha", "alerta", "cego", "ok", "info"
ICONE = {FALHA: "✗", ALERTA: "⚠", CEGO: "🕶", OK: "✓", INFO: "·"}
PESO = {FALHA: 0, ALERTA: 1, CEGO: 2, INFO: 3, OK: 4}

_achados = []


def _log(m):
    print(f"[vigia] {m}", flush=True)


def _diz(nivel, area, msg, detalhe="", imagem=None):
    _achados.append({"nivel": nivel, "area": area, "msg": msg,
                     "detalhe": detalhe, "imagem": str(imagem) if imagem else ""})


def _json_de(p: Path, padrao=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return padrao


def _linhas_jsonl(p: Path, limite=0) -> list:
    """Lê .jsonl tolerando linha corrompida — o ledger é append-only e uma
    linha truncada por queda de energia não pode cegar o vigia inteiro."""
    fora = []
    try:
        for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                fora.append(json.loads(ln))
            except Exception:
                continue
    except Exception:
        return []
    return fora[-limite:] if limite else fora


# ══════════════════════════════════════════════════════════════════════════
#  CAMADA 1 — O PIXEL
#
#  Não procura "o selo está torto". Procura "isto está diferente de ontem".
#  A diferença é que a primeira lista precisa que eu adivinhe o defeito antes
#  de ele existir, e a segunda não precisa: pega troca de fonte, logo errada,
#  cor mudada, selo movido, faixa cortada — inclusive o que eu não imaginei.
# ══════════════════════════════════════════════════════════════════════════

# ⚠️ A FAIXA VEM DOS MESMOS KNOBS QUE O RENDER USA — NÃO É NÚMERO CHUTADO.
#
# A faixa precisa conter SÓ o que é igual em todo vídeo da mesma conta (logo,
# "TopShop", selo, @handle) e NADA do que muda a cada vídeo (o hook). Se pegar
# o hook, o vigia acusa mudança todo dia e vira ruído — que é a única forma de
# um vigia morrer sem ninguém desligar.
#
# Onde o hook começa, no `narrated_video_agent`:
#
#     HK_Y = max(logo_y + logo_tam + 20,  VIDEO_Y - HK_GAP_VIDEO - n*HK_ALT_LINHA)
#
# O `max` garante um PISO: com os knobs da VPS (LOGO_Y=210, LOGO_TAM=118) o
# hook nunca começa antes de y=348, tenha 1, 2 ou 3 linhas. Então a faixa
# segura termina em 348.
#
# ⚠️ Eu poderia ter escrito 344 aqui e teria funcionado — HOJE. Seria o mesmo
# erro que o selo cometeu por um mês: duas partes calculando a mesma geometria
# por caminhos diferentes, e uma delas envelhecendo sozinha quando um knob
# muda. Por isso a faixa é DERIVADA das mesmas variáveis, com os mesmos
# padrões. Se o layout subir ou descer, ela acompanha.
def _faixa_do_template() -> tuple:
    """(y0, y1, x1) da região que é puro template. Derivada, não chutada."""
    logo_y = int(os.environ.get("LOGO_Y", 112))
    logo_tam = int(os.environ.get("LOGO_TAM", 120))
    piso_do_hook = logo_y + logo_tam + 20          # a mesma conta do render
    y0 = max(0, logo_y - int(os.environ.get("VIGIA_FOLGA_TOPO", "20")))
    y1 = min(piso_do_hook - 4, int(os.environ.get("VIDEO_Y", 470)))
    x1 = int(os.environ.get("VIGIA_FAIXA_X1", "820"))
    return y0, y1, x1


# Quantos % dos pixels podem diferir sem virar alerta. Não é zero de propósito:
# compressão de vídeo mexe em pixel isolado sem nada ter mudado no template.
TOLERANCIA_PCT = float(os.environ.get("VIGIA_TOLERANCIA_PCT", "0.35"))


def _ffmpeg() -> str:
    for c in ("ffmpeg", "/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        try:
            subprocess.run([c, "-version"], capture_output=True, timeout=10)
            return c
        except Exception:
            continue
    return ""


def _quadro(ff: str, video: Path, destino: Path, t=1.0) -> bool:
    """Um quadro do vídeo em PNG. t=1s e não 0 porque o primeiro quadro às
    vezes sai antes das camadas assentarem."""
    try:
        r = subprocess.run(
            [ff, "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1",
             "-q:v", "2", str(destino)],
            capture_output=True, timeout=90)
        return destino.exists() and destino.stat().st_size > 0 and r.returncode == 0
    except Exception:
        return False


def _faixa(png, saida):
    """Recorta a faixa do cabeçalho e grava. Devolve a imagem ou None.

    Aceita str ou Path: recebendo str o `saida.parent` estourava e o recorte
    sumia calado — o `_diferenca` devolvia -1 e, num teste menos cuidadoso,
    -1 passaria por 'nada mudou'. Erro que se disfarça de aprovação é o pior
    tipo, e este arquivo existe justamente por causa de um."""
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        png, saida = Path(png), Path(saida)
        y0, y1, x1 = _faixa_do_template()
        im = Image.open(png).convert("RGB")
        corte = im.crop((0, min(y0, im.height), min(x1, im.width),
                         min(y1, im.height)))
        saida.parent.mkdir(parents=True, exist_ok=True)
        corte.save(saida)
        return corte
    except Exception:
        return None


def _diferenca(a, b) -> float:
    """% de pixels que mudaram de verdade. Não usa média: uma média baixa
    esconde um selo inteiro deslocado num cabeçalho grande. Conta PIXEL."""
    try:
        from PIL import Image, ImageChops, ImageStat
    except Exception:
        return -1.0
    try:
        if a.size != b.size:
            return 100.0            # tamanho diferente já É a mudança
        dif = ImageChops.difference(a, b).convert("L")
        # 24/255: acima disso é mudança visível, abaixo é ruído de compressão
        mascara = dif.point(lambda p: 255 if p > 24 else 0)
        total = mascara.size[0] * mascara.size[1]
        mudados = ImageStat.Stat(mascara).sum[0] / 255.0
        return 100.0 * mudados / total if total else 0.0
    except Exception:
        return -1.0


def _lado_a_lado(antes: Path, depois: Path, saida: Path) -> bool:
    """Empilha referência e atual com rótulo. Mandar só o 'depois' obriga quem
    lê a lembrar como era — e ninguém lembra de um vão de 8px."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return False
    try:
        a, b = Image.open(antes).convert("RGB"), Image.open(depois).convert("RGB")
        larg = max(a.width, b.width)
        alt = a.height + b.height + 46
        canvas = Image.new("RGB", (larg, alt), (24, 24, 24))
        canvas.paste(a, (0, 22))
        canvas.paste(b, (0, a.height + 46))
        d = ImageDraw.Draw(canvas)
        d.text((6, 5), "REFERENCIA (como era)", fill=(150, 150, 150))
        d.text((6, a.height + 28), "AGORA", fill=(255, 180, 60))
        canvas = canvas.resize((larg * 2, alt * 2), Image.LANCZOS)
        canvas.save(saida)
        return True
    except Exception:
        return False


def _pacotes() -> list:
    """(slug, video, conta, mtime) de cada pacote pronto, do mais novo pro velho."""
    if not PRONTO.exists():
        return []
    fora = []
    for pasta in PRONTO.iterdir():
        try:
            video = pasta / "video.mp4"
            if not (pasta.is_dir() and video.exists()):
                continue
            c = _json_de(pasta / "conta.json", {}) or {}
            conta = (c.get("handle") or c.get("nicho") or "?").strip()
            fora.append((pasta.name, video, conta, video.stat().st_mtime))
        except Exception:
            continue
    fora.sort(key=lambda x: -x[3])
    return fora


# Acima disto, o vídeo mais novo da conta é velho demais pra dizer alguma
# coisa sobre o estado de HOJE.
DIAS_PRA_VELHO = float(os.environ.get("VIGIA_DIAS_PRA_VELHO", "3"))


def _prov(ref: Path) -> Path:
    return ref.with_suffix(".json")


def _gravar_proveniencia(ref: Path, slug: str, humano: bool):
    """De ONDE veio esta referência, e se alguém de carne e osso olhou.

    ⚠️ ESTE É O CALCANHAR DE AQUILES DO VIGIA e ele foi apontado antes de
    virar problema: *"se alguma daquelas 4 estiver com o cabeçalho torto, ele
    passa a defender o defeito como se fosse o normal"*. Uma referência criada
    sozinha não é verdade — é só a primeira coisa que ele viu. Enquanto
    ninguém confirmar, todo "✓ igual à referência" daquela conta vale menos, e
    o recado tem que dizer isso em vez de exibir um check verde."""
    agora = datetime.now().isoformat(timespec="seconds")
    antes = _json_de(_prov(ref), {}) or {}
    dados = {
        "criada": antes.get("criada") or agora,
        "video": slug,
        "confirmada_por_humano": bool(humano),
        "confirmada_em": agora if humano else antes.get("confirmada_em"),
    }
    try:
        _prov(ref).write_text(json.dumps(dados, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    except Exception:
        pass


def _slug_conta(conta: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in conta)[:40] or "sem_conta"


def olhar_pixel(aprovar=False, quantos=1):
    """Compara o cabeçalho dos vídeos novos com a referência de cada conta."""
    A = "template"
    ff = _ffmpeg()
    if not ff:
        _diz(CEGO, A, "sem ffmpeg — não consigo abrir vídeo nenhum")
        return
    try:
        import PIL  # noqa: F401
    except Exception:
        _diz(CEGO, A, "sem Pillow — não consigo olhar pixel")
        return

    pacotes = _pacotes()
    if not pacotes:
        _diz(CEGO, A, "nenhum pacote com video.mp4 em pronto_para_postar/")
        return

    # um vídeo por conta (o mais novo) — o objetivo é flagrar mudança de
    # template, e pra isso um vídeo por conta basta e é barato
    por_conta, vistos = [], set()
    for slug, video, conta, quando in pacotes:
        if conta in vistos:
            continue
        vistos.add(conta)
        por_conta.append((slug, video, conta, quando))
        if len(por_conta) >= 12:
            break

    CASA.mkdir(parents=True, exist_ok=True)
    (CASA / "recortes").mkdir(exist_ok=True)
    conferidos = 0

    for slug, video, conta, quando in por_conta:
        chave = _slug_conta(conta)
        tmp = CASA / "recortes" / f"_quadro_{chave}.png"
        atual = CASA / "recortes" / f"atual_{chave}.png"
        ref = CASA / f"referencia_{chave}.png"

        # ⚠️ "IGUAL À REFERÊNCIA" NUM VÍDEO VELHO NÃO É NOTÍCIA DE HOJE.
        # `_pacotes` devolve o mais novo de cada conta. Se a produção parar, o
        # mais novo continua sendo o mesmo arquivo, e esta camada carimbaria ✓
        # todo dia com base num vídeo de uma semana atrás. Seria o defeito que
        # este arquivo existe pra combater — silêncio parecendo saúde — dentro
        # do próprio vigia.
        dias = (datetime.now().timestamp() - quando) / 86400
        if dias > DIAS_PRA_VELHO:
            _diz(ALERTA, A, f"{conta}: o vídeo mais novo tem {dias:.0f} dias",
                 f"confiro o template dele mesmo assim, mas isso não diz nada "
                 f"sobre hoje — a produção desta conta parou?")

        if not _quadro(ff, video, tmp):
            _diz(CEGO, A, f"{conta}: não consegui extrair quadro de '{slug[:34]}'")
            continue
        img = _faixa(tmp, atual)
        try:
            tmp.unlink()
        except Exception:
            pass
        if img is None:
            _diz(CEGO, A, f"{conta}: não consegui recortar o cabeçalho")
            continue
        conferidos += 1

        if aprovar or not ref.exists():
            try:
                ref.write_bytes(atual.read_bytes())
            except Exception as e:
                _diz(CEGO, A, f"{conta}: não consegui gravar a referência: {str(e)[:50]}")
                continue
            _gravar_proveniencia(ref, slug, humano=bool(aprovar))
            _diz(INFO if aprovar else CEGO, A,
                 f"{conta}: referência {'CONFIRMADA por você' if aprovar else 'criada agora'}"
                 + ("" if aprovar else " — só comparo a partir do próximo vídeo"),
                 f"veja se está do jeito certo: {ref}")
            continue

        try:
            from PIL import Image
            pct = _diferenca(Image.open(ref).convert("RGB"), img)
        except Exception as e:
            _diz(CEGO, A, f"{conta}: comparação falhou: {str(e)[:60]}")
            continue

        confirmada = bool((_json_de(_prov(ref), {}) or {}).get("confirmada_por_humano"))
        if pct < 0:
            _diz(CEGO, A, f"{conta}: não consegui comparar o cabeçalho")
        elif pct <= TOLERANCIA_PCT:
            # "igual à referência" só vale o que a referência vale
            if confirmada:
                _diz(OK, A, f"{conta}: cabeçalho igual à referência ({pct:.2f}%)")
            else:
                _diz(CEGO, A,
                     f"{conta}: igual a uma referência que ninguém conferiu",
                     f"eu me criei sozinho a partir de um vídeo. Se ele já "
                     f"estava torto, estou defendendo o defeito. Olhe {ref.name} "
                     f"e rode: vigia.py --aprovar")
        else:
            comp = CASA / "recortes" / f"mudou_{chave}.png"
            tem = _lado_a_lado(ref, atual, comp)
            _diz(FALHA, A, f"{conta}: O CABEÇALHO MUDOU ({pct:.1f}% dos pixels)",
                 f"vídeo '{slug[:40]}' · se a mudança for de propósito, "
                 f"rode: vigia.py --aprovar",
                 imagem=comp if tem else atual)

    if conferidos:
        _diz(INFO, A, f"{conferidos} cabeçalho(s) conferido(s) no pixel")


# ══════════════════════════════════════════════════════════════════════════
#  CAMADA 2 — O PUBLICADO (Graph API oficial, não raspagem)
# ══════════════════════════════════════════════════════════════════════════

def _contas_config() -> dict:
    d = _json_de(RAIZ / "contas.json", {}) or {}
    return d if isinstance(d, dict) else {}


def olhar_publicado(dias=3):
    """Por conta: saiu post? a LEGENDA foi junto? quanto alcançou?"""
    A = "publicado"
    contas = _contas_config()
    if not contas:
        _diz(CEGO, A, "contas.json ausente ou ilegível — não sei quais contas olhar")
        return

    try:
        import metricas_posts as MP        # reaproveita transporte e token
    except Exception as e:
        _diz(CEGO, A, f"não consegui usar o metricas_posts: {str(e)[:60]}")
        return

    # ⚠️ CONTA QUE NÃO ESTÁ NO contas.json NÃO É VIGIADA — E NINGUÉM AVISA.
    # O Dre falou em SEIS contas; o contas.json que eu revisei tinha QUATRO.
    # Sem esta checagem, @topshoppet_ e @topshopmoda_ ficariam fora do vigia
    # para sempre e o recado diria "todas ok" — porque "todas" seria quatro.
    # O buraco que ele descreveu ("fico 5 dias fora e algo muda") é exatamente
    # este: o silêncio de quem ninguém está olhando.
    reais = [c for c in contas.values() if isinstance(c, dict)]
    esperadas = int(os.environ.get("VIGIA_CONTAS_ESPERADAS", "6"))
    if len(reais) < esperadas:
        conhecidas = sorted((c.get("handle") or "?") for c in reais)
        _diz(ALERTA, A,
             f"o contas.json tem {len(reais)} conta(s), você tem {esperadas}",
             "vigiadas: " + ", ".join(conhecidas)
             + " — o que não está aqui, ninguém olha")

    limite = datetime.now(timezone.utc) - timedelta(days=dias)
    olhadas = 0

    for nicho, conta in contas.items():
        if not isinstance(conta, dict):
            continue
        handle = (conta.get("handle") or nicho).strip()
        ig = str(conta.get("instagram_user_id", "")).strip()
        if not ig:
            # ⚠️ isto é CEGO, não OK. Uma conta sem id no contas.json passaria
            # despercebida pra sempre e o vigia diria "tudo certo".
            _diz(CEGO, A, f"{handle}: sem instagram_user_id no contas.json")
            continue
        token = MP._token(conta)
        if not token:
            _diz(CEGO, A, f"{handle}: sem token de página utilizável")
            continue

        r = MP._get(f"{MP.GRAPH}/{ig}/media",
                    {"fields": "id,permalink,timestamp,caption,media_type",
                     "limit": 25, "access_token": token})
        if r.get("error"):
            _diz(CEGO, A, f"{handle}: o Graph recusou a listagem",
                 str(r["error"].get("message", ""))[:110])
            continue
        olhadas += 1

        # ⚠️ O ALCANCE SOZINHO NÃO SIGNIFICA NADA (21/08).
        # A 1ª medição deu alcance mediano de 113 e eu disse "isso é problema
        # de distribuição". Era chute: 113 numa conta de 150 seguidores é 75%
        # de alcance, que é ótimo; numa de 5.000 é grave. O número que importa
        # é a RAZÃO, e ninguém no projeto media seguidores.
        #
        # É a mesma lição do dia inteiro num lugar novo: número sem
        # denominador convence sem informar.
        try:
            rp = MP._get(f"{MP.GRAPH}/{ig}",
                         {"fields": "followers_count,media_count",
                          "access_token": token})
            if not rp.get("error"):
                n = int(rp.get("followers_count") or 0)
                if n:
                    _seguidores[nicho] = (handle, n)
                    # ⚠️ 1.000 SEGUIDORES É UM PORTÃO, NÃO UMA VAIDADE (21/08).
                    # A Shopee exige conta profissional, pública e com 1.000+
                    # seguidores pra liberar a MARCAÇÃO DE PRODUTO no Reel —
                    # o caminho de compra mais curto que existe: a pessoa toca
                    # no produto dentro do vídeo, sem bio, sem DM, sem link.
                    #
                    # Enquanto nenhuma conta passa disso, todo o funil que a
                    # gente otimiza (legenda, DM, comentário) é desvio. Por
                    # isso a distância aparece todo dia: é a única meta do
                    # projeto hoje com número e recompensa definidos.
        except Exception:
            pass

        recentes = []
        for m in r.get("data", []):
            try:
                q = datetime.fromisoformat(
                    str(m.get("timestamp", "")).replace("Z", "+00:00"))
            except Exception:
                continue
            if q >= limite:
                recentes.append((q, m))

        if not recentes:
            _diz(ALERTA, A, f"{handle}: NENHUM post nos últimos {dias} dia(s)")
            continue

        sem_legenda = [(q, m) for q, m in recentes
                       if not (m.get("caption") or "").strip()]
        if sem_legenda:
            # o Dre pediu isto com todas as letras: "legenda não saiu"
            #
            # ⚠️ REPORTA A HORA, não só o link (20/08). O `meta_uploader` grava
            # "📝 legenda p/ Instagram: N caractere(s)" ANTES de enviar, desde
            # 15/08. Com a hora do post dá pra cruzar as duas pontas e separar
            # duas causas que ficam em lugares opostos:
            #
            #   log diz 0 caractere(s)  → a legenda não chegou a ser montada
            #   log diz 800 e o post    → mandamos e a Meta descartou
            #   está sem               (ou este vigia está lendo errado)
            #
            # Sem a hora, o achado é verdadeiro e inútil: aponta o problema e
            # não deixa ninguém agir. Foi o que aconteceu hoje.
            det = " · ".join(
                f"{q:%d/%m %H:%M} {str(m.get('permalink',''))[-14:]}"
                for q, m in sem_legenda[:4])
            _diz(FALHA, A,
                 f"{handle}: {len(sem_legenda)} post(s) SEM LEGENDA",
                 det + "  → cruze com: grep 'legenda p/ Instagram' "
                       "logs/agente.log")
        else:
            _diz(OK, A, f"{handle}: {len(recentes)} post(s) em {dias}d, todos com legenda")

    # ── O PORTÃO DA SHOPEE ────────────────────────────────────────────────
    # ⚠️ SEMPRE MOSTRA A CONTA MAIS PERTO, não importa a distância. A 1ª
    # versão só falava quando faltavam menos de 300 — e com a líder em 413 ela
    # ficava MUDA justamente sobre a única conta que interessa. Meta que só
    # aparece quando já está quase alcançada não serve de meta.
    if _seguidores:
        handle, n = max(((h, q) for h, q in _seguidores.values()),
                        key=lambda x: x[1])
        falta = _PORTAO_SHOPEE - n
        # ⚠️ formata o NÚMERO, não a frase — pela SEGUNDA vez hoje eu escrevi
        # `f"…({handle}, {n:,})".replace(",", ".")` e a vírgula do texto virou
        # ponto: "(@topshoptech_. 413)". Consertei igual no diag_conta e
        # reintroduzi aqui. O jeito de não repetir é não deixar o replace
        # encostar na frase.
        _n = f"{n:,}".replace(",", ".")
        _f = f"{falta:,}".replace(",", ".")
        if falta <= 0:
            _diz(OK, A, f"🎯 {handle} PASSOU do portão: {_n} seguidores",
                 "dá pra marcar produto Shopee no Reel — Painel Profissional › "
                 "Monetização › Parceria de Afiliados. É o caminho de compra "
                 "mais curto que existe.")
        else:
            _diz(INFO, A, f"🎯 portão da Shopee: faltam {_f} seguidores na "
                          f"conta mais perto ({handle}, {_n})",
                 "com 1.000 dá pra marcar o produto DENTRO do Reel; "
                 "até lá todo caminho de compra é desvio")

    if not olhadas:
        _diz(CEGO, A, "não consegui ler NENHUMA conta pelo Graph — "
                      "a camada do publicado está cega inteira")


# ══════════════════════════════════════════════════════════════════════════
#  CAMADA 2.5 — O DESEMPENHO ("qual hook está segurando")
#
#  Era o pedido original do Dre — *"hooks novos em altas, legendas novas em
#  altas"* — e ficou de fora até 21/08 por falta de matéria-prima, não de
#  código: o `metricas_posts.jsonl` estava parado havia 11 dias porque
#  **ninguém agendou a coleta**. Não estava quebrado; estava sem cron, igual
#  o vigia antes de ontem.
# ══════════════════════════════════════════════════════════════════════════

# Preenchido pela camada do PUBLICADO (que já tem token e id na mão) e lido
# pela do DESEMPENHO. A ordem é explícita no `main`: publicado roda antes.
# Vazio = não consegui medir, e aí o desempenho fala em números absolutos e
# diz que está sem denominador — nunca inventa a razão.
_seguidores = {}

# Mínimo de seguidores que a Shopee exige pra liberar a marcação de produto no
# Instagram (conta profissional + pública + 1.000 seguidores). Medido no
# material oficial que o Dre mandou em 21/08.
_PORTAO_SHOPEE = int(os.environ.get("VIGIA_PORTAO_SEGUIDORES", "1000"))


def _mediana(ns):
    ns = sorted(n for n in ns if isinstance(n, (int, float)))
    return ns[len(ns) // 2] if ns else 0


def olhar_desempenho(dias=7):
    """O que os números dizem sobre o CONTEÚDO, não sobre defeito."""
    A = "desempenho"
    linhas = _linhas_jsonl(METRICAS)
    if not linhas:
        _diz(CEGO, A, "sem métricas de post — a cadeia nunca rodou",
             "ligue com: .venv/bin/python metricas_posts.py")
        return

    # ⚠️ MÉTRICA VELHA É PIOR QUE MÉTRICA NENHUMA: ela responde com confiança
    # sobre um mundo que já mudou. Os hooks novos entraram em 19/08; ranking
    # feito com dado de 11 dias atrás falaria só dos velhos e pareceria atual.
    try:
        idade = (datetime.now()
                 - datetime.fromtimestamp(METRICAS.stat().st_mtime)).days
    except Exception:
        idade = 0
    if idade > 3:
        _diz(ALERTA, A, f"as métricas estão paradas há {idade} dias",
             "o ranking abaixo fala do passado. Rode: metricas_posts.py")

    corte = datetime.now() - timedelta(days=dias)
    recentes, antigos = [], []
    for r in linhas:
        try:
            q = datetime.strptime(f"{r.get('data')} {r.get('hora')}",
                                  "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        (recentes if q >= corte else antigos).append(r)

    if not recentes:
        _diz(CEGO, A, f"nenhum post medido nos últimos {dias} dias")
        return

    alc = [r.get("reach", 0) or 0 for r in recentes]
    med_agora = _mediana(alc)
    _diz(INFO, A, f"{len(recentes)} post(s) medidos em {dias}d · "
                  f"alcance mediano {med_agora:,}".replace(",", "."))

    # ── ALCANCE POR SEGUIDOR: é isto que diz se o número é bom ou ruim ──
    if not _seguidores:
        _diz(CEGO, A, "não sei quantos seguidores as contas têm",
             "sem esse denominador, alcance alto ou baixo é palpite")
    else:
        # ⚠️ casa pelo NICHO, que é a chave que os dois lados já usam.
        # A 1ª versão comparava strings (`"@topshopcasa_".endswith("casa")`),
        # que é sempre falso por causa do `_` no fim — a razão sairia sempre da
        # mediana global e pareceria certa. Chave existente vale mais que
        # ginástica de texto.
        for nicho, (handle, segs) in sorted(_seguidores.items()):
            # ⚠️ CASA PELA CONTA QUE PUBLICOU, não pela categoria do produto.
            # Até 21/08 eu comparava `r["nicho"]` (categoria) com a conta, como
            # se fossem a mesma chave. Não são: produto de categoria pet
            # publicado no @topshop.__ contava como alcance do @topshoppet_ —
            # conta que nunca publicou. O `metricas_posts` passou a gravar
            # `conta`; linhas antigas não têm, e essas ficam de fora em vez de
            # entrar pela chave errada. Amostra menor e certa vale mais que
            # amostra cheia e torta.
            do_perfil = [r.get("reach", 0) or 0 for r in recentes
                         if (r.get("conta") or "").lower() == handle.lower()]
            antigas = sum(1 for r in recentes if not r.get("conta"))
            if not do_perfil and antigas:
                _diz(CEGO, A, f"{handle}: {antigas} medição(ões) sem a conta "
                              f"gravada — não sei de quem são",
                     "linhas anteriores a 21/08; some sozinho conforme mede")
                continue
            # ⚠️ SEM POST MEDIDO, NÃO INVENTA UM NÚMERO (21/08).
            # A 1ª versão caía na mediana GLOBAL quando a conta não tinha post
            # próprio. Resultado na 1ª execução real: @topshoppet_ e
            # @topshopmoda_, que têm ZERO publicações, apareceram com "112 de
            # alcance — 12.4× a base". Alcance fabricado, com cara de medido, e
            # ainda por cima como ✓ verde.
            #
            # É o mesmo defeito do dia todo, agora no meu código novo: um
            # número que parece específico e não é. Conta sem post não tem
            # alcance — tem ausência, e ausência se relata.
            if not do_perfil:
                _diz(INFO, A, f"{handle}: {segs:,} seguidor(es), nenhum post "
                              f"medido em {dias}d".replace(",", "."),
                     "sem post não há alcance a comparar")
                continue
            base = _mediana(do_perfil)
            razao = base / segs if segs else 0
            # 1.0 = alcançou tanta gente quanto o número de seguidores. Reels
            # saudável passa disso (o IG entrega pra não-seguidor); muito
            # abaixo significa que nem os seguidores estão vendo.
            if razao >= 1.0:
                _diz(OK, A, f"{handle}: {base:,} de alcance com {segs:,} "
                            f"seguidor(es) — {razao:.1f}× a base"
                     .replace(",", "."))
            elif razao >= 0.3:
                _diz(INFO, A, f"{handle}: {base:,} de alcance com {segs:,} "
                              f"seguidor(es) — {razao * 100:.0f}% da base"
                     .replace(",", "."))
            else:
                _diz(ALERTA, A, f"{handle}: {base:,} de alcance com {segs:,} "
                                f"seguidor(es) — só {razao * 100:.0f}% da base"
                     .replace(",", ""),
                     "nem os próprios seguidores estão vendo os posts")

    # tendência: só fala quando a amostra dos DOIS lados é suficiente pra
    # significar algo. Comparar 2 posts com 40 é ruído com cara de conclusão.
    janela_antes = [r for r in antigos]
    if len(recentes) >= 4 and len(janela_antes) >= 4:
        med_antes = _mediana([r.get("reach", 0) or 0 for r in janela_antes])
        if med_antes:
            var = 100.0 * (med_agora - med_antes) / med_antes
            if var <= -30:
                _diz(ALERTA, A, f"o alcance mediano CAIU {abs(var):.0f}% "
                                f"({med_antes:,} → {med_agora:,})".replace(",", "."))
            elif var >= 30:
                _diz(OK, A, f"o alcance mediano SUBIU {var:.0f}% "
                            f"({med_antes:,} → {med_agora:,})".replace(",", "."))

    # ── INTENÇÃO: quem QUIS GUARDAR ──────────────────────────────────────
    # ⚠️ POR QUE ISTO ENTROU (21/08). A tabela por fórmula deu alcance mediano
    # entre 109 e 134 em TODAS as fórmulas, contas e semanas. Essa
    # uniformidade é o achado: o Instagram dá a cada post uma audiência de
    # teste pequena e fixa, e nenhum dos nossos escapa dela. Otimizar hook
    # olhando alcance é medir a régua do Instagram, não o nosso conteúdo.
    #
    # Salvar é o sinal mais forte pra conteúdo de compra — quem salva pretende
    # voltar — e é ele que faz o algoritmo empurrar além do teste.
    #
    # SOMA ANTES DE DIVIDIR: com alcance ~112 e 1-2 salvos, a taxa de um post
    # é ruído (2 em 100 = 2,0%; 1 em 112 = 0,9% — um salvo de diferença vira
    # "o dobro"). Agrupado, cada post entra com o peso do alcance dele.
    def _taxa(rs, campo):
        alc = sum(int(r.get("reach", 0) or 0) for r in rs)
        return (1000.0 * sum(int(r.get(campo, 0) or 0) for r in rs) / alc,
                alc) if alc else (0.0, 0)

    sv_agora, alc_agora = _taxa(recentes, "saved")
    if alc_agora >= 400:
        sh_agora, _ = _taxa(recentes, "shares")
        msg = (f"intenção: {sv_agora:.1f} salvos/mil · {sh_agora:.1f} "
               f"compart./mil ({alc_agora:,} impressões)".replace(",", "."))
        if len(antigos) >= 4:
            sv_antes, alc_antes = _taxa(antigos, "saved")
            if alc_antes >= 400 and sv_antes:
                var = 100.0 * (sv_agora - sv_antes) / sv_antes
                if var <= -30:
                    _diz(ALERTA, A, msg + f" — CAIU {abs(var):.0f}%",
                         f"antes {sv_antes:.1f}/mil. Menos gente querendo "
                         f"guardar é o sinal que some antes da venda")
                elif var >= 30:
                    _diz(OK, A, msg + f" — SUBIU {var:.0f}%")
                else:
                    _diz(INFO, A, msg)
            else:
                _diz(INFO, A, msg)
        else:
            _diz(INFO, A, msg)
    else:
        _diz(CEGO, A, f"só {alc_agora} impressões em {dias}d — pouco pra "
                      f"calcular taxa de salvamento")

    # ⚠️ RANKING POR POST, NÃO POR HOOK REPETIDO. Os hooks gerados são únicos
    # por construção (cada vídeo ganha o seu), então agrupar por hook e exigir
    # n>=5 seleciona SÓ as frases de reserva — que se repetem — e dá a
    # impressão de que a reserva é o que funciona. Foi um erro que eu já
    # cometi neste projeto. O que responde "qual hook segurou" é o hook dos
    # posts que mais alcançaram.
    campeoes = sorted(recentes, key=lambda r: -(r.get("reach", 0) or 0))[:3]
    for r in campeoes:
        hook = (r.get("hook") or "").strip().replace("\n", " / ")
        if not hook:
            continue
        _diz(INFO, A,
             f"🔥 {(r.get('reach', 0) or 0):,}".replace(",", ".")
             + f" · {r.get('nicho') or '?'} · {hook[:70]}",
             f"salvos {r.get('saved', 0)} · curtidas {r.get('likes', 0)} · "
             f"{r.get('url', '')[:52]}")

    # o pior serve tanto quanto o melhor: é ele que diz o que parar de fazer
    piores = [r for r in sorted(recentes, key=lambda r: (r.get("reach", 0) or 0))
              if (r.get("hook") or "").strip()][:1]
    for r in piores:
        hook = (r.get("hook") or "").strip().replace("\n", " / ")
        _diz(INFO, A, f"🥶 {(r.get('reach', 0) or 0):,}".replace(",", ".")
                      + f" · {r.get('nicho') or '?'} · {hook[:70]}")


# ══════════════════════════════════════════════════════════════════════════
#  CAMADA 3 — A SÉRIE (o que MUDOU desde a última olhada)
# ══════════════════════════════════════════════════════════════════════════

def _fotografia() -> dict:
    """Os números do dia. Só contagem — nada que dependa de rede."""
    hoje = datetime.now()
    def _novos(linhas, campo="quando", horas=24):
        n = 0
        for r in linhas:
            try:
                q = str(r.get(campo) or r.get("data") or r.get("timestamp") or "")
                if not q:
                    continue
                d = datetime.fromisoformat(q.replace("Z", "+00:00"))
                if d.tzinfo:
                    d = d.replace(tzinfo=None)
                if (hoje - d) <= timedelta(hours=horas):
                    n += 1
            except Exception:
                continue
        return n

    ledger = _linhas_jsonl(LEDGER)
    return {
        "quando": hoje.isoformat(timespec="seconds"),
        "pacotes_prontos": len(_pacotes()),
        "ledger_total": len(ledger),
        "produzidos_24h": _novos(ledger),
        "publicados_total": len(_linhas_jsonl(PUBLICADOS)),
        "metricas_total": len(_linhas_jsonl(METRICAS)),
    }


def olhar_serie(foto: dict):
    """Compara com a última fotografia. É a camada que responde ao 'fiquei 5
    dias sem entrar': ela não descreve o estado, descreve a MUDANÇA."""
    A = "mudança"
    antigas = _linhas_jsonl(HISTORICO)
    if not antigas:
        _diz(INFO, A, "primeira fotografia — a partir de amanhã eu comparo")
        return

    ant = antigas[-1]
    try:
        quando = datetime.fromisoformat(str(ant.get("quando")))
        gap = datetime.now() - quando
        horas = gap.total_seconds() / 3600
    except Exception:
        horas = 0
    desde = f"desde a última olhada ({horas:.0f}h atrás)" if horas else "desde a última olhada"

    # ⚠️ O VIGIA VIGIANDO O PRÓPRIO VIGIA.
    # O pior cenário de todos não é o vigia achar algo errado: é ele PARAR e
    # todo mundo continuar achando que está sendo vigiado. Aí são 3, 4, 5 dias
    # de problema sem ninguém olhar — o cenário exato que ele foi feito pra
    # impedir, agora com uma falsa sensação de cobertura por cima.
    #
    # Isto aqui é o que dá pra fazer de dentro: quando ele volta a rodar,
    # percebe o buraco e conta. Não cobre "parou e nunca mais rodou" — pra
    # isso a `revisao_geral` ganhou um bloco que olha a idade deste arquivo de
    # fora. Duas checagens fracas em lugares diferentes valem mais que uma
    # forte que mora dentro do que ela deveria auditar.
    esperado = float(os.environ.get("VIGIA_INTERVALO_H", "24"))
    if horas > esperado * 1.5:
        _diz(FALHA, A, f"EU FIQUEI {horas:.0f}h SEM RODAR (o normal é {esperado:.0f}h)",
             "o cron falhou ou a máquina ficou fora. Neste intervalo ninguém "
             "estava olhando as contas — e o silêncio parecia saúde.")

    prod = foto["ledger_total"] - int(ant.get("ledger_total", 0) or 0)
    if prod <= 0 and horas >= 20:
        _diz(FALHA, A, f"NENHUM vídeo novo produzido {desde}",
             "a esteira parou — é o tipo de coisa que só aparece depois de dias")
    elif prod > 0:
        _diz(OK, A, f"{prod} vídeo(s) produzido(s) {desde}")

    pub = foto["publicados_total"] - int(ant.get("publicados_total", 0) or 0)
    if pub <= 0 and horas >= 20:
        _diz(ALERTA, A, f"nenhuma publicação nova registrada {desde}")

    fila_antes = int(ant.get("pacotes_prontos", 0) or 0)
    delta = foto["pacotes_prontos"] - fila_antes
    if fila_antes and delta >= max(12, fila_antes * 0.5):
        _diz(ALERTA, A,
             f"a fila de prontos INCHOU: {fila_antes} → {foto['pacotes_prontos']}",
             "produzindo mais do que postando — o pacote velho vence antes de sair")


def gravar_fotografia(foto: dict):
    try:
        CASA.mkdir(parents=True, exist_ok=True)
        with open(HISTORICO, "a", encoding="utf-8") as f:
            f.write(json.dumps(foto, ensure_ascii=False) + "\n")
    except Exception as e:
        _log(f"não consegui gravar a fotografia: {str(e)[:70]}")


# ══════════════════════════════════════════════════════════════════════════
#  CAMADA 4 — O SISTEMA (reaproveita a revisao_geral inteira)
# ══════════════════════════════════════════════════════════════════════════

def olhar_sistema():
    """Roda a `revisao_geral` de verdade em vez de reescrever as checagens.

    Mesmo princípio da `auditoria_postagem`, que importa as funções do daemon:
    duas implementações da mesma pergunta divergem, e a divergência aparece
    como um vigia que diz OK enquanto o outro script diz FALHA. Foi exatamente
    isso que o selo ensinou hoje, num nível abaixo."""
    A = "sistema"
    try:
        import revisao_geral as RG
    except Exception as e:
        _diz(CEGO, A, f"não consegui carregar a revisao_geral: {str(e)[:70]}")
        return
    try:
        RG._achados.clear()
        for nome, fn in RG.BLOCOS:
            try:
                fn()
            except Exception as e:
                _diz(CEGO, A, f"o bloco '{nome}' da revisão falhou: {str(e)[:60]}")
        traduz = {RG.FALHA: FALHA, RG.ALERTA: ALERTA}
        for a in RG._achados:
            n = traduz.get(a.get("estado"))
            if n:                       # só o que precisa de ação sobe pro vigia
                _diz(n, A, f"[{a.get('bloco')}] {a.get('msg')}",
                     str(a.get("detalhe") or "")[:160])
    except Exception as e:
        _diz(CEGO, A, f"a revisão geral quebrou: {str(e)[:80]}")


# ══════════════════════════════════════════════════════════════════════════
#  INVENTÁRIO — o que o vigia CONSEGUE ver (sem julgar nada)
# ══════════════════════════════════════════════════════════════════════════

def inventario():
    """Antes de confiar num vigia, saber o que ele alcança.

    Existe porque eu já perdi rodadas inventando seletor sem ver o DOM (a saga
    da figurinha) e lendo log sem ver o vídeo (o selo). Aqui não há juízo: é a
    lista do que está ao alcance, pra decidir o que dá pra vigiar de fato."""
    print(f"\n  INVENTÁRIO DO VIGIA · {datetime.now():%d/%m %H:%M}")
    print("  " + "─" * 66)

    pac = _pacotes()
    print(f"\n  [pacotes prontos] {len(pac)}")
    contas = {}
    for _, _, c in pac:
        contas[c] = contas.get(c, 0) + 1
    for c, n in sorted(contas.items(), key=lambda kv: -kv[1]):
        print(f"     {c:24} {n:4} pacote(s)")
    if "?" in contas:
        print(f"     ⚠  {contas['?']} pacote(s) SEM conta.json — "
              "esses eu não sei de qual conta são")

    print(f"\n  [contas.json]")
    for nicho, c in (_contas_config() or {}).items():
        if not isinstance(c, dict):
            continue
        print(f"     {nicho:12} handle={str(c.get('handle') or '?'):20} "
              f"ig_user_id={'SIM' if c.get('instagram_user_id') else 'NÃO'} "
              f"token_env={'SIM' if c.get('page_token_env') else 'herda'}")

    print(f"\n  [arquivos de dado]")
    for p in (LEDGER, PUBLICADOS, METRICAS, HISTORICO):
        if p.exists():
            n = len(_linhas_jsonl(p))
            idade = (datetime.now()
                     - datetime.fromtimestamp(p.stat().st_mtime))
            print(f"     {p.name:26} {n:6} linha(s) · mexido há "
                  f"{idade.days}d{idade.seconds // 3600}h")
        else:
            print(f"     {p.name:26} NÃO EXISTE")

    print(f"\n  [referências de cabeçalho]")
    refs = sorted(CASA.glob("referencia_*.png")) if CASA.exists() else []
    if not refs:
        print("     nenhuma ainda — a 1ª execução cria uma por conta")
    for r in refs:
        idade = datetime.now() - datetime.fromtimestamp(r.stat().st_mtime)
        print(f"     {r.name:36} de {idade.days}d atrás")

    print(f"\n  [ferramentas]")
    print(f"     ffmpeg  {'ok' if _ffmpeg() else 'AUSENTE (camada do pixel fica cega)'}")
    try:
        import PIL
        print(f"     Pillow  ok ({PIL.__version__})")
    except Exception:
        print("     Pillow  AUSENTE (camada do pixel fica cega)")
    tok = bool((os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip())
    cht = bool((os.environ.get("TELEGRAM_ALERT_CHAT_ID")
                or os.environ.get("TELEGRAM_CHAT_ID") or "").strip())
    print(f"     Telegram  token={'ok' if tok else 'AUSENTE'} · "
          f"chat={'ok' if cht else 'AUSENTE'}   (valores nunca impressos)")
    print()


# ══════════════════════════════════════════════════════════════════════════
#  O RECADO
# ══════════════════════════════════════════════════════════════════════════

def _avisar(texto: str, imagem: Path = None):
    """Mesma via do resto do projeto: Telegram privado."""
    tok = (os.environ.get("TELEGRAM_BOT_TOKEN", "") or "").strip()
    chat = ((os.environ.get("TELEGRAM_ALERT_CHAT_ID")
             or os.environ.get("TELEGRAM_CHAT_ID") or "")).strip()
    if not tok or not chat:
        _log("sem TELEGRAM_BOT_TOKEN/CHAT_ID — não mandei o recado")
        return False
    try:
        import requests
        if imagem and Path(imagem).exists():
            with open(imagem, "rb") as f:
                requests.post(f"https://api.telegram.org/bot{tok}/sendPhoto",
                              timeout=40,
                              data={"chat_id": chat, "caption": texto[:900]},
                              files={"photo": f})
        else:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          timeout=25, json={"chat_id": chat, "text": texto[:4000]})
        return True
    except Exception as e:
        _log(f"falhei ao mandar o recado: {str(e)[:80]}")
        return False


def _recado() -> str:
    """Curto quando está tudo bem, longo quando não está.

    ⚠️ MANDA TODO DIA, MESMO SEM PROBLEMA. Vigia que só fala quando quebra é
    indistinguível de vigia morto — e quem fica 5 dias fora não tem como saber
    a diferença. As duas linhas do dia bom são a prova de vida."""
    falhas = [a for a in _achados if a["nivel"] == FALHA]
    alertas = [a for a in _achados if a["nivel"] == ALERTA]
    cegos = [a for a in _achados if a["nivel"] == CEGO]
    oks = [a for a in _achados if a["nivel"] == OK]

    cab = f"🕶️ VIGIA · {datetime.now():%d/%m %H:%M}"

    # ⚠️ VIGIA CEGO NÃO DIZ "NADA MUDOU".
    # Sem isto, uma noite em que o ffmpeg some e o token vence produz o recado
    # mais tranquilizador do dia — e quem está 5 dias fora lê "tudo certo"
    # exatamente quando ninguém está olhando. É a mesma armadilha do "0 fontes
    # podadas" (a poda não rodou) e do "101 erros em 24h" (a janela era outra):
    # ausência de achado sendo lida como ausência de problema.
    #
    # ⚠️ E só quando NÃO HÁ MAIS NADA A DIZER. A primeira versão testava só
    # `sem oks + tem cegos`, e retornava aqui mesmo havendo 2 falhas — o
    # cabeçalho de cego escondia as falhas que eu tinha acabado de encontrar.
    # Um vigia que engole o achado pra falar de si mesmo é pior que nenhum.
    if not oks and not falhas and not alertas and cegos:
        linhas = [f"{cab} — ⚠️ EU ESTOU CEGO.",
                  "",
                  "Não consegui conferir NADA hoje. Isto não é 'tudo certo':",
                  ""]
        linhas += [f"🕶 [{a['area']}] {a['msg']}" for a in cegos[:8]]
        return "\n".join(linhas)

    if not falhas and not alertas:
        linhas = [f"{cab} — nada mudou.",
                  f"✓ {len(oks)} checagem(ns) ok" +
                  (f" · 🕶 {len(cegos)} sem enxergar" if cegos else "")]
        if cegos:
            linhas.append("")
            linhas += [f"🕶 {a['msg']}" for a in cegos[:4]]
        return "\n".join(linhas)

    linhas = [cab, ""]
    if falhas:
        linhas.append(f"✗ {len(falhas)} coisa(s) PRA VER HOJE:")
        for a in falhas[:8]:
            linhas.append(f"   [{a['area']}] {a['msg']}")
            if a["detalhe"]:
                linhas.append(f"      {a['detalhe'][:150]}")
        linhas.append("")
    if alertas:
        linhas.append(f"⚠ {len(alertas)} alerta(s):")
        for a in alertas[:6]:
            linhas.append(f"   [{a['area']}] {a['msg']}")
        linhas.append("")
    if cegos:
        linhas.append(f"🕶 {len(cegos)} coisa(s) que NÃO consegui olhar:")
        for a in cegos[:5]:
            linhas.append(f"   [{a['area']}] {a['msg']}")
        linhas.append("")
    linhas.append(f"✓ {len(oks)} ok")
    return "\n".join(linhas)


def imprimir():
    print(f"\n  VIGIA DAS CONTAS · {datetime.now():%d/%m %H:%M}")
    print("  " + "─" * 66)
    area = None
    for a in sorted(_achados, key=lambda x: (PESO[x["nivel"]], x["area"])):
        if a["area"] != area:
            area = a["area"]
            print(f"\n  [{area}]")
        print(f"   {ICONE[a['nivel']]} {a['msg']}")
        if a["detalhe"]:
            print(f"       {a['detalhe']}")
        if a["imagem"]:
            print(f"       imagem: {a['imagem']}")
    n = {k: sum(1 for a in _achados if a["nivel"] == k)
         for k in (FALHA, ALERTA, CEGO, OK)}
    print("\n  " + "─" * 66)
    print(f"  {n[FALHA]} falha(s) · {n[ALERTA]} alerta(s) · "
          f"{n[CEGO]} sem enxergar · {n[OK]} ok\n")


def main():
    p = argparse.ArgumentParser(
        description="O Jarvis olha as contas todo dia. SÓ LÊ — não conserta nada.")
    p.add_argument("--telegram", action="store_true", help="manda o recado")
    p.add_argument("--inventario", action="store_true",
                   help="mostra o que ele CONSEGUE ver, sem julgar")
    p.add_argument("--aprovar", action="store_true",
                   help="abençoa o cabeçalho atual como referência")
    p.add_argument("--mandar-referencias", dest="mandar_ref", action="store_true",
                   help="manda os PNG de referência pro seu Telegram")
    p.add_argument("--dias", type=int, default=3,
                   help="janela do que foi publicado (padrão 3)")
    p.add_argument("--sem-sistema", dest="sem_sistema", action="store_true",
                   help="pula a revisao_geral (mais rápido)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    if args.inventario:
        inventario()
        return 0

    if args.mandar_ref:
        # ⚠️ A REFERÊNCIA SÓ VALE SE ALGUÉM OLHAR, e ela mora numa VPS sem
        # tela. Aprovar sem ver é abençoar o que estiver lá — inclusive um
        # defeito. O caminho mais curto entre o arquivo e o olho do Dre é o
        # mesmo Telegram por onde já chegam os erros.
        refs = sorted(CASA.glob("referencia_*.png")) if CASA.exists() else []
        if not refs:
            _log("nenhuma referência ainda — rode o vigia uma vez primeiro")
            return 1
        for r in refs:
            conta = r.stem.replace("referencia_", "")
            prov = _json_de(_prov(r), {}) or {}
            selo = ("CONFIRMADA" if prov.get("confirmada_por_humano")
                    else "ainda não conferida")
            ok = _avisar(f"🕶️ referência de {conta} ({selo})\n"
                         f"criada em {str(prov.get('criada'))[:16]} "
                         f"do vídeo {str(prov.get('video'))[:40]}\n\n"
                         f"O selo azul tem que estar FORA do nome, com um vão "
                         f"visível. Se estiver colado, é o selo velho.", r)
            _log(f"{'enviei' if ok else 'FALHEI ao enviar'} {r.name}")
        return 0

    # cada camada é independente: uma que exploda não pode levar as outras —
    # o dia em que tudo está ruim é o dia em que o vigia mais importa
    for nome, fn in (("pixel", lambda: olhar_pixel(aprovar=args.aprovar)),
                     ("publicado", lambda: olhar_publicado(dias=args.dias)),
                     ("desempenho", olhar_desempenho),
                     ("sistema", (lambda: None) if args.sem_sistema else olhar_sistema)):
        try:
            fn()
        except Exception as e:
            _diz(CEGO, nome, f"a própria camada falhou: {str(e)[:90]}")

    foto = {}
    try:
        foto = _fotografia()
        olhar_serie(foto)
    except Exception as e:
        _diz(CEGO, "mudança", f"não consegui comparar com ontem: {str(e)[:80]}")

    if args.json:
        print(json.dumps({"achados": _achados, "fotografia": foto},
                         ensure_ascii=False, indent=2))
    else:
        imprimir()

    if args.telegram:
        # a imagem do 1º cabeçalho que mudou vai junto: o Dre lê no celular, e
        # "mudou 4% dos pixels" não diz nada sem o antes e o depois
        img = next((a["imagem"] for a in _achados
                    if a["nivel"] == FALHA and a["imagem"]), None)
        if _avisar(_recado(), Path(img) if img else None):
            _log("recado enviado")

    if foto and not args.aprovar:
        gravar_fotografia(foto)

    return 1 if any(a["nivel"] == FALHA for a in _achados) else 0


if __name__ == "__main__":
    sys.exit(main())
