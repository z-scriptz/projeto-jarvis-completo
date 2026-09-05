#!/usr/bin/env python3
# produzir_tiktok.py -- FASE 3 do coletor: pega os virais baixados em
# inbox_tiktok/ (video + plano.json do tiktok_coletor) e passa pela MESMA
# esteira do hunter: reproduzir_video (template TopShop + hook + narração)
# -> pronto_para_postar/ (daemon posta) -> vitrine do site -> posts_ledger.
#
# Fluxo completo: tiktok_coletor.py (baixa) -> produzir_tiktok.py (fabrica)
#                 -> daemon posta nos horários -> $$
#
# Uso (VPS):  python3 produzir_tiktok.py [quantos]     (padrão: 2 por rodada —
#             render é pesado no VPS; o resto fica pra próxima rodada)
import os
import sys
import json
import random
import shutil
import asyncio
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INBOX = BASE_DIR / "inbox_tiktok"
FEITOS = INBOX / "_produzidos"       # pra onde a pasta vai depois de produzir
# QUANTOS POR RODADA quando ninguém passa número na linha de comando.
#
# 2 → 12 em 05/09/2026. O motivo não é ousadia, é conta: a pirâmide do
# `daemon_maestro` (`posts_por_dia_semana = [3,2,1,3,2,1,0]`) vale POR CONTA, e
# são 6 contas. Isso é 18 posts na segunda, 12 na terça, 6 na quarta — média de
# ~10/dia, 72 na semana. Produzindo 6, a esteira alimentava menos da METADE do
# que o daemon posta num dia de pico.
#
# E o estoque comporta: ~1.300 pacotes conferidos na fila (108 dias a 12/dia),
# com o coletor ainda somando. Como o Dre resumiu: a fonte é gringa, é única e
# é reutilizável — o vídeo não "vence" como oferta de marketplace vence.
#
# ⚠️ O CUSTO REAL AQUI É TEMPO DE VPS, não dinheiro: cada render leva de 5 a 19
# minutos. 12 vídeos ≈ 2h de máquina. Rodada noturna aguenta; se apertar,
# PRODUZIR_POR_RODADA no .env resolve sem mexer no código.
MAX_PADRAO = int(os.environ.get("PRODUZIR_POR_RODADA", "12"))

# Trilha de fundo baixinha (pra nunca ficar silêncio quando a narração acaba).
# Coloque áudios sutis e "virais" nessa pasta — uma é sorteada por vídeo.
# Aceita mp4/mov também (Reels Sound): o ffmpeg usa só a faixa de áudio deles.
MUSICA_EXTS = (".mp3", ".m4a", ".wav", ".ogg", ".aac", ".mp4", ".mov", ".m4v")


def _carregar_env():
    for cand in (BASE_DIR / ".env", Path(".env")):
        if not cand.exists():
            continue
        for linha in cand.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            k, _, v = linha.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        break


_carregar_env()

# Reusa a esteira REAL do hunter (mesmo template, hook, narração, legenda)
try:
    from integrations import telegram_repurpose_hunter as H
except Exception:
    import telegram_repurpose_hunter as H

try:
    from integrations.shopee_affiliate import gerar_link_afiliado as _gerar_link
except Exception:
    try:
        from shopee_affiliate import gerar_link_afiliado as _gerar_link
    except Exception:
        _gerar_link = None


def _log(m):
    print(f"[produzir_tiktok] {m}")


# marcas de bitstream quebrado — as MESMAS do `auditoria_video.py`, que foi
# quem mediu os 5 arquivos corrompidos em 17/08
_MARCAS_QUEBRADO = (
    "Invalid NAL unit size",
    "Error splitting the input into NAL units",
    "missing picture in access unit",
    "Invalid data found when processing input",
    "moov atom not found",
)


def _video_integro(video: Path, segundos: int = 3) -> bool:
    """O arquivo DECODIFICA? (não "os metadados estão certos?")

    ⚠️ A DIFERENÇA ENTRE AS DUAS PERGUNTAS É O BUG INTEIRO. O vídeo que parou a
    @topshoptech_ por 3 dias tinha container impecável — h264, 1080x1920,
    30fps, 7,93s, aac. Qualquer checagem por `ffprobe -show_entries` aprovava.
    O fluxo H.264 lá dentro é que estava corrompido, e isso só aparece quando
    alguém decodifica de verdade — que é o que a Meta faz do lado dela.

    ⚠️ NA DÚVIDA, DEIXA PASSAR. Sem `ffmpeg` no PATH, ou com o processo
    falhando por outro motivo, devolve True: barrar produção por causa de uma
    ferramenta ausente trocaria um defeito raro (5 em 355) por uma esteira
    parada. O erro caro aqui é o falso POSITIVO, não o falso negativo.
    """
    exe = shutil.which("ffmpeg")
    if not exe:
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            exe = None
    if not exe or not Path(video).exists():
        return True
    cmd = [exe, "-v", "error", "-nostdin"]
    if segundos > 0:
        cmd += ["-t", str(segundos)]
    cmd += ["-i", str(video), "-f", "null", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except Exception:
        return True
    erro = r.stderr or ""
    achadas = [m for m in _MARCAS_QUEBRADO if m in erro]
    if achadas:
        _log(f"   🔴 bitstream quebrado em {Path(video).name}: "
             f"{' · '.join(achadas[:2])}")
        return False
    return True


SEM_FONTE = "semfonte"      # sentinela do slot 3 (ver _subids)


def _id_video(slug: str) -> str:
    """Etiqueta curta e única DESTE vídeo, pro slot 5 do sub_id.

    ⚠️ POR QUE PRECISA EXISTIR (17/08): a ordem canônica usava 4 das 5
    etiquetas — `[canal, nicho, produto, FONTE]` — e **nenhuma identifica o
    vídeo**. Uma venda dizia de qual conta, nicho, produto e perfil de origem
    veio, mas não de qual POST nem de qual HOOK. Sem isso, "hook amplo vende
    mais?" só se responde em segundos de retenção, nunca em dinheiro — e a
    estratégia de hook mudou HOJE, então cada post publicado sem etiqueta é um
    post que nunca vai poder ser atribuído depois.

    Hash e não contador: o produtor roda em processos separados (cron), e
    contador compartilhado entre processos precisaria de trava. Hash de
    semente única dá unicidade sem coordenação — e o mesmo produto produzido
    duas vezes recebe etiquetas diferentes, que é justamente o que se quer.

    ⚠️ A SEMENTE NÃO PODE SER SÓ `slug + tempo`. Foi a primeira versão, e o
    teste pegou: 5 chamadas seguidas deram 4 ids distintos — `time.time()` com
    3 casas colide dentro do mesmo milissegundo. Id repetido não é um detalhe
    estatístico aqui: são duas vendas atribuídas ao vídeo errado, em silêncio,
    justamente na medição que este campo existe pra viabilizar. Com `urandom`
    a chance de colisão em 36 bits some pro volume que a gente produz.
    """
    import hashlib
    import os as _os
    import time as _t
    semente = f"{slug}|{_t.time_ns()}|{_os.getpid()}|{_os.urandom(8).hex()}"
    return "v" + hashlib.sha1(semente.encode("utf-8")).hexdigest()[:9]


def _subids(canal: str, nicho: str, nome: str, fonte: str = "",
            video: str = "") -> list:
    """Sub-IDs na ordem canônica: [canal, nicho, produto, FONTE, VIDEO]. O
    índice 3 (fonte = perfil de origem) é o que o CEO cruza com a venda pra
    saber qual perfil converte; o índice 4 identifica o vídeo/hook. Só
    alfanumérico e ≤16 chars cada (a Shopee rejeita _/-/espaço → erro 11001).

    ⚠️ A ARMADILHA QUE QUASE ME PEGOU: a versão antiga OMITIA o slot da fonte
    quando ela vinha vazia. Um `ids.append(video)` ingênuo colocaria o vídeo no
    ÍNDICE 3 — e `metricas_agent._fonte()` lê o índice 3 como FONTE. Cada venda
    de link sem fonte passaria a reportar um "perfil de origem" que é, na
    verdade, um hash de vídeo. **Não daria erro nenhum**: o CEO simplesmente
    começaria a ver centenas de fontes inventadas, cada uma com 1 venda, e a
    poda por venda passaria a cortar fonte boa.

    Por isso, quando há vídeo, o slot 3 é preenchido com `SEM_FONTE` em vez de
    omitido — e o `metricas_agent._fonte()` traduz essa sentinela de volta pra
    "". Posição é contrato; buraco no meio de um contrato posicional não é
    "campo ausente", é o campo seguinte mentindo.
    """
    import re
    def s(x, padrao):
        v = re.sub(r"[^A-Za-z0-9]", "", str(x or ""))[:16]
        return v or padrao
    ids = [s(canal, "x"), s(nicho, "geral"), s(nome, "prod")]
    tem_fonte = bool(str(fonte or "").strip())
    if tem_fonte:
        ids.append(s(fonte, "fonte"))
    elif video:
        ids.append(SEM_FONTE)       # segura a posição, senão o vídeo vira fonte
    if video:
        ids.append(s(video, "vid"))
    return ids


def _link_do_canal(canal: str, origem_url: str, nicho: str, nome: str, base: str,
                   fonte: str = "", video: str = "") -> str:
    """Gera um link de afiliado etiquetado pro CANAL (ex: 'fb') + FONTE + VIDEO.
    Se não der, usa o link base (best-effort — nunca quebra a produção)."""
    if not (_gerar_link and origem_url):
        return base
    try:
        r = _gerar_link(origem_url,
                        sub_ids=_subids(canal, nicho, nome, fonte, video))
        if isinstance(r, dict) and r.get("ok"):
            return r.get("short_link") or r.get("link") or base
    except Exception as e:
        _log(f"   (link {canal} falhou, uso o base: {str(e)[:50]})")
    return base


def _alerta_telegram(msg: str) -> None:
    """Manda um alerta no chat de admin (best-effort, nunca quebra o fluxo).
    Usa TELEGRAM_ALERT_CHAT_ID se existir, senão TELEGRAM_CHAT_ID (mesmo canal
    do '🚨 Jarvis'). Nunca vai pro grupo público de achadinhos (userbot)."""
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = (os.getenv("TELEGRAM_ALERT_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not tok or not chat:
        return
    try:
        import requests
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=15,
                      json={"chat_id": chat, "text": msg, "parse_mode": "HTML"})
    except Exception:
        pass


def _f(nome: str, padrao: float) -> float:
    try:
        return float(os.getenv(nome, padrao))
    except (TypeError, ValueError):
        return float(padrao)


def _dir_musica() -> Path:
    d = os.getenv("MUSICA_FUNDO_DIR", "assets/inbox/audio")
    p = Path(d)
    return p if p.is_absolute() else (BASE_DIR / p)


def _escolher_musica() -> Path:
    """Sorteia uma trilha de fundo da pasta de músicas. '' se não houver nenhuma
    (aí o vídeo sai só com a narração, sem música — sem quebrar)."""
    pasta = _dir_musica()
    try:
        cands = [p for p in pasta.iterdir()
                 if p.is_file() and p.suffix.lower() in MUSICA_EXTS
                 and p.stat().st_size > 5000]
    except Exception:
        cands = []
    return random.choice(cands) if cands else Path()


def _dur_media(p) -> float:
    """Duração (s) de um vídeo/áudio via ffprobe. 0.0 se falhar (usado p/ capar
    o áudio no tamanho do vídeo com -t, evitando saída infinita com stream_loop)."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
            capture_output=True, text=True, timeout=30)
        return float((r.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def _so_musica(video: Path, nome: str) -> bool:
    """PLANO B DO ÁUDIO — troca o áudio original por TRILHA SÓ.

    ⚠️ POR QUE EXISTE (03/09/2026): as fontes agora são perfis GRINGOS, e o
    `_narrar_e_trocar_audio` tinha QUATRO caminhos de falha (import, Gemini/
    ElevenLabs, e dois do ffmpeg) — e todos os quatro devolviam False deixando
    o vídeo com o áudio ORIGINAL. O próprio código já avisava no Telegram
    "risco de copyright/crédito" e publicava assim mesmo. Com fonte brasileira
    isso passava; com fonte gringa é voz em INGLÊS no Reel em português.

    Pedido do Dre: *"se tiver alguma narração por cima, ao invés de música,
    pode raspar e colocar musica viral, ou uma música normal por cima"*.

    Isto não depende de Gemini nem de ElevenLabs — só de ffmpeg e de um arquivo
    na pasta de trilhas. Ou seja: funciona justamente quando a narração não.
    Volume próprio (MUSICA_SO_VOL): a trilha aqui é o áudio PRINCIPAL, não um
    leito por baixo de voz — os 0,10 do MUSICA_FUNDO_VOL sairiam quase mudos.
    """
    if os.getenv("MUSICA_SE_FALHAR", "1").strip().lower() not in ("1", "true", "sim"):
        return False
    musica = _escolher_musica()
    if not musica:
        _log(f"   ⚠️ sem trilha em {_dir_musica()} — NÃO consigo tirar o áudio gringo")
        return False
    vol = max(0.05, min(1.0, _f("MUSICA_SO_VOL", 0.85)))
    out = video.parent / f"_mustmp_{os.getpid()}.mp4"
    _dur = _dur_media(video)
    _tcap = ["-t", f"{_dur:.3f}"] if _dur > 0 else []
    cmd = ["ffmpeg", "-y", "-i", str(video),
           "-stream_loop", "-1", "-i", str(musica),
           "-filter_complex", f"[1:a]volume={vol:.3f}[a]",
           "-map", "0:v:0", "-map", "[a]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
           *_tcap, "-shortest", str(out)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        _log("   ⚠️ plano B (trilha) estourou 180s")
        return False
    if r.returncode == 0 and out.exists() and out.stat().st_size > 1000:
        out.replace(video)
        _log(f"   🎵 áudio gringo REMOVIDO — trilha '{musica.name}' no lugar")
        return True
    _log(f"   ⚠️ plano B (trilha) falhou: {(r.stderr or '')[-140:]}")
    try:
        out.unlink()
    except Exception:
        pass
    return False


def _narrar_e_trocar_audio(video: Path, nome: str, contexto: str, nicho: str = "") -> bool:
    """Gera a narração (ElevenLabs, voz do nicho, roteiro do vídeo) e SUBSTITUI o áudio
    do vídeo por ela — mata o áudio original (fim do copyright/crédito a terceiro).
    Mixa uma TRILHA DE FUNDO baixinha por baixo (loopada até o fim do vídeo), pra
    nunca ficar silêncio quando a narração acaba antes do vídeo.

    Se a narração não sair, cai no `_so_musica` (plano B) — o áudio original só
    fica se AS DUAS coisas falharem, e aí o alerta do Telegram diz isso."""
    if os.getenv("NARRAR_TIKTOK", "1").strip().lower() not in ("1", "true", "sim"):
        return False

    def _avisa(motivo):
        """Tenta o plano B e avisa o que REALMENTE saiu no vídeo — o alerta
        antigo dizia sempre "áudio ORIGINAL", o que passaria a ser mentira
        quando a trilha salvasse."""
        salvou = _so_musica(video, nome)
        saiu = ("Saiu com TRILHA (sem voz) — áudio gringo removido."
                if salvou else
                "Vídeo saiu com o áudio ORIGINAL (risco de copyright/crédito).")
        _log(f"   🚨 alerta: narração falhou ({motivo})")
        _alerta_telegram(f"🚨 <b>Jarvis — narração falhou</b>\n🎬 {nome[:60]}\n"
                         f"⚠️ {motivo}\n{saiu} Re-narra quando puder.")
        return salvou

    try:
        from narracao_ia import gerar as _gerar_narr
    except Exception:
        _log("   narracao_ia indisponível")
        _avisa("narracao_ia indisponível (import)")
        return False
    narr = video.parent / (video.stem + "_narr.mp3")
    if not _gerar_narr(nome, contexto, narr, nicho):
        _log("   narração não gerada")
        _avisa("roteiro (Gemini) ou voz (ElevenLabs) falhou")
        return False

    # saída em arquivo TEMP sem acento (o nome real tem 'tábua' etc. e o ffmpeg
    # quebra ao CRIAR arquivo com acento em locale não-UTF8 → "Invalid argument").
    # No fim, o Python renomeia p/ o vídeo (Path.replace lida com Unicode).
    out = video.parent / f"_narrtmp_{os.getpid()}.mp4"
    musica = _escolher_musica()
    vol = max(0.0, min(0.5, _f("MUSICA_FUNDO_VOL", 0.10)))
    # CAPA a saída na duração do VÍDEO (-t): com stream_loop -1 + amix longest a
    # música é infinita e o -shortest sozinho falhava → vídeo de 50min. -t resolve.
    _dur = _dur_media(video)
    _tcap = ["-t", f"{_dur:.3f}"] if _dur > 0 else []

    # narração = trilha 1 (volume cheio), música = trilha 2 (baixa, loopada).
    # amix normaliza dividindo por 2, então pré-amplifico o dobro pra manter os níveis.
    if musica and vol > 0:
        fc = (f"[1:a]volume=2.0[nar];"
              f"[2:a]volume={2 * vol:.3f}[bg];"
              f"[nar][bg]amix=inputs=2:duration=longest:dropout_transition=0[a]")
        cmd = ["ffmpeg", "-y", "-i", str(video), "-i", str(narr),
               "-stream_loop", "-1", "-i", str(musica),
               "-filter_complex", fc, "-map", "0:v:0", "-map", "[a]",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
               *_tcap, "-shortest", str(out)]
        tag = f"narração própria + trilha '{musica.name}' baixinha"
    else:
        cmd = ["ffmpeg", "-y", "-i", str(video), "-i", str(narr),
               "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
               "-c:a", "aac", "-b:a", "128k", *_tcap, "-shortest", str(out)]
        tag = "narração própria"
        if not musica:
            _log(f"   ℹ️ sem trilha em {_dir_musica()} — vídeo sai só com narração")

    def _roda(c):
        try:
            return subprocess.run(c, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            class _R:  # simula um resultado de falha p/ cair no fallback/aviso
                returncode = 124
                stderr = "timeout 180s (ffmpeg travou no áudio)"
            return _R()

    r = _roda(cmd)
    # se a mixagem com música falhar (ffmpeg antigo etc.), tenta só narração
    if (r.returncode != 0 or not out.exists()) and musica and vol > 0:
        _log(f"   ⚠️ mix c/ música falhou, tento só narração: {(r.stderr or '')[-140:]}")
        r = _roda(["ffmpeg", "-y", "-i", str(video), "-i", str(narr),
                   "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                   "-c:a", "aac", "-b:a", "128k", *_tcap, "-shortest", str(out)])
        tag = "narração própria"

    if r.returncode == 0 and out.exists() and out.stat().st_size > 1000:
        out.replace(video)
        _log(f"   🎙️  áudio original SUBSTITUÍDO por {tag}")
        return True
    _log(f"   ⚠️ troca de áudio falhou: {(r.stderr or '')[-160:]}")
    try:
        out.unlink()        # limpa ANTES do plano B (que grava outro temp)
    except Exception:
        pass
    _avisa("ffmpeg (troca de áudio) falhou")
    return False


def _pendentes() -> list:
    """Pastas do inbox com plano.json + video ainda não produzidos."""
    if not INBOX.exists():
        return []
    out = []
    for pasta in sorted(INBOX.iterdir()):
        if not pasta.is_dir() or pasta.name.startswith("_"):
            continue
        pj = pasta / "plano.json"
        # ⚠️ 'video.*' CASA COM 'video.mp4.part' (05/09/2026). Um download
        # interrompido deixa o parcial em disco e este glob o adotava como
        # vídeo pronto — daí saía render de arquivo pela metade. Mesmo defeito
        # estava no `_baixar` do coletor.
        vids = [v for v in pasta.glob("video.*")
                if not v.name.endswith(PARCIAIS)]
        if not (pj.exists() and vids):
            continue
        # ⚠️ PULA O QUE O `limpar_inbox.py` MARCOU COMO NÃO-PRODUTO (04/09/2026).
        # São pacotes cujo "produto" é legenda, não item: 'Nunca respondas esta
        # llamada pueden', 'Limited time special offer', 'Coisas Devia Ter
        # Comprado Antes'. Postar isso é link morto — pior que não postar,
        # porque queima o clique de quem confiou.
        #
        # Marcado, não apagado: um erro do modelo aqui é reversível tirando a
        # chave do plano.json.
        try:
            if json.loads(pj.read_text(encoding="utf-8")).get("nao_e_produto"):
                continue
        except Exception:
            pass          # plano ilegível é problema do _produzir, não daqui
        out.append((pasta, pj, vids[0]))
    return out


def _produzir(pasta: Path, pj: Path, video_src: Path) -> bool:
    info = json.loads(pj.read_text(encoding="utf-8"))
    nome = info.get("produto") or info.get("termo") or pasta.name
    link = info.get("link_afiliado", "")
    perfil_fonte = (info.get("perfil_fonte") or "").strip().lower()  # p/ CEO medir/podar
    plataforma = (info.get("plataforma") or "shopee").strip().lower()
    if not link:
        _log(f"   sem link de afiliado em {pasta.name} — pulo (não monetiza)")
        return False

    slug = H._slugify(nome)
    hook = (H._HOOK[0](nome, plano={}) if H._HOOK_OK else "Olha isso!")

    # categoria + roteamento multi-conta: decide o nicho ANTES de renderizar,
    # pra o vídeo já sair com o @handle da conta certa (beleza/tech/geral).
    categoria = ""
    try:
        from creative_engine.narration_script_builder import _categoria_do_produto
        categoria = _categoria_do_produto(nome) or ""
    except Exception:
        pass
    conta = None
    if os.getenv("MULTI_CONTA", "0").strip().lower() in ("1", "true", "sim"):
        try:
            import roteador_contas as _RC
            conta = _RC.conta_do_produto(nome, categoria)
            if conta.get("handle"):
                os.environ["TOPSHOP_HANDLE"] = conta["handle"]
                _log(f"   🎯 conta '{conta.get('nicho')}' → {conta['handle']}")
        except Exception as e:
            _log(f"   roteador de conta off ({str(e)[:60]}) — usa a principal")
            conta = None

    # nicho decide a VOZ da narração (feminina p/ beleza, masculina p/ tech/geral)
    # e também vai pro ledger. Calcula uma vez aqui, funciona mesmo sem MULTI_CONTA.
    nicho = (conta.get("nicho") if conta else "") or ""
    if not nicho:
        try:
            import roteador_contas as _RC
            nicho = _RC.nicho_do_produto(nome, categoria)
        except Exception:
            nicho = "geral"

    # FUNDO pela PALETA DO NICHO (shared/paleta.py, 02/09). Era
    #   _bg_padrao = "preto" if nicho in ("geral","") else "branco"
    # escrito igual aqui, no hunter e no render.py. Com 6 nichos e uma cor
    # própria pra cada, três cópias dessa linha não sobreviveriam — é o mesmo
    # desenho que fez o @topshopcasa_ publicar com a logo do @topshop.__.
    try:
        from shared.paleta import aplicar_no_ambiente as _aplicar_paleta
        _aplicar_paleta(nicho, log=_log)
    except Exception as _e:
        _log(f"   ⚠️  paleta indisponível ({str(_e)[:60]}) — fundo pela regra antiga")
        _bg_padrao = "preto" if nicho in ("geral", "") else "branco"
        os.environ["TOPSHOP_NICHO"] = nicho or "geral"
        os.environ["TOPSHOP_BG"] = (os.environ.get("FORCE_BG")
                                    or os.environ.get("BG_" + nicho.upper(), _bg_padrao))

    # LOGO por conta/nicho: cada perfil tem sua marca. O nome sai do NICHO
    # (shared/marca.py), não de um dicionário escrito à mão — foi um dicionário
    # sem "casa" que fez o @topshopcasa_ publicar com a logo do @topshop.__.
    # Se a logo da conta não existir, o aviso sai no log em vez de sumir.
    try:
        from shared.marca import logo_escolhida
        os.environ["TOPSHOP_LOGO"] = logo_escolhida(nicho, log=_log)
    except Exception:
        os.environ["TOPSHOP_LOGO"] = os.environ.get("FORCE_LOGO") or "logo_ts.png"
    _log(f"   🅣 logo '{os.environ['TOPSHOP_LOGO']}'")

    # HOOK estilo Alana ("frase relatable 😩" / "A Shopee:") — é o que converte.
    # Usa Gemini (HOOK_ALANA=1 + GEMINI_API_KEY); senão banco relatable por nicho.
    if os.getenv("HOOK_ALANA", "1").strip().lower() in ("1", "true", "sim"):
        try:
            from hook_alana import gerar_hook_alana
            _ha = gerar_hook_alana(nome, info.get("descricao", ""), nicho)
            if _ha:
                hook = _ha
                _log(f"   ✍️  hook Alana: \"{hook.splitlines()[0]}\" / {hook.splitlines()[-1]}")
        except Exception as _e:
            _log(f"   hook Alana off ({str(_e)[:50]}) — usa o hook padrão")

    plano = {
        "produto": nome,
        "titulo_real": nome,
        "preco_real": "",
        "link_afiliado": link,
        "musica_fundo": "",
        "hook": hook,
        # segundos de intro do criador a pular (medido pelo tiktok_coletor).
        # O hunter aplica isso no subclip ANTES da velocidade.
        "corte_inicio": info.get("corte_inicio", 0) or 0,
    }
    if plano["corte_inicio"]:
        _log(f"   ✂️  intro: pulando {float(plano['corte_inicio']):.1f}s")

    # 1) RE-PRODUÇÃO (mesma esteira do hunter: 9:16, template, narração, hook)
    destino = H.INBOX_VIDEOS / f"{slug}.mp4"
    H.INBOX_VIDEOS.mkdir(parents=True, exist_ok=True)
    _log(f"   🎬 renderizando '{nome[:45]}' (pode demorar no VPS)…")
    resultado = asyncio.run(H.reproduzir_video(video_src, destino, nome, nome, plano))
    if not resultado.get("sucesso"):
        _log(f"   ❌ render falhou: {resultado.get('erro')}")
        return False

    # 1.5) NARRAÇÃO própria + mata o áudio original (copyright/crédito)
    _narrar_e_trocar_audio(destino, nome, info.get("descricao", ""), nicho)

    # 2) Legenda + hashtags + plano (espelha os passos 5-6 do hunter)
    legenda = H._legenda_dinamica(nome, hook,
                                  descricao=info.get("descricao", ""),
                                  nicho=nicho, item_id=str(info.get("item_id", "")))
    hashtags = H._hashtags_para(categoria, nome)
    plano.update({
        "video_path_sugerido": str(destino),
        "roteiro_narrado": resultado.get("frases", []),
        "legenda": legenda,
        "hashtags": hashtags,
        "cta": (H._HOOK[1](nome) if H._HOOK_OK else "Link na Bio!"),
        "narracao": resultado.get("narracao", False),
        "duracao": resultado.get("duracao"),
        "narracao_propria": resultado.get("narracao", False),
        "duracao_video": resultado.get("duracao"),
        "categoria": categoria,
        "plataforma": plataforma,
        "status_producao": "video_gerado",
        "fonte": "tiktok",
        "fonte_url": info.get("url", ""),
        "fonte_views": info.get("views", 0),
    })
    H._salvar_json_atomico(H.SHARED_PLANS / f"plano_{slug}.json", plano)
    H._salvar_json_atomico(H.SHARED_PLANS / "ultimo_plano.json", plano)

    # 3) Esteira de postagem (passo 7 do hunter)
    #
    # ⚠️ CONFERE O ARQUIVO ANTES DE ENTRAR NA ESTEIRA (17/08). Cinco vídeos de
    # 355 estavam com o bitstream H.264 corrompido (`Invalid NAL unit size`), e
    # um deles derrubou a @topshoptech_ por 3 dias: o Instagram e o Facebook
    # recusam (`ProcessingFailedError · retriable: False`) e a conta perde o
    # slot inteiro, porque cada conta entra com UM pacote.
    #
    # O que torna isso invisível é que o CONTAINER fica perfeito — 1080x1920,
    # 30fps, duração certa, tudo dentro do padrão de Reels. Só a DECODIFICAÇÃO
    # revela. Então a checagem tem que decodificar, e não ler metadado.
    #
    # Custa ~0,6s por vídeo (medido: 355 arquivos em 208s). Barato contra o
    # preço de um slot perdido, e barato contra o preço real: o vídeo entra na
    # fila, envelhece dias esperando a vez, e só aí descobre que nunca serviu.
    if not _video_integro(destino):
        _log(f"   ❌ '{nome[:45]}' NÃO entrou na esteira: vídeo corrompido")
        _log("      (a Meta recusaria e a conta perderia o slot. Confira o "
             "render — provável interrupção na gravação do arquivo.)")
        return False

    pp = H.BASE_DIR / "pronto_para_postar" / slug
    pp.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(destino), str(pp / "video.mp4"))
    # conta.json ao lado do vídeo → o meta_uploader posta na conta certa
    if conta:
        try:
            import roteador_contas as _RC
            (pp / "conta.json").write_text(
                json.dumps(_RC.conta_para_json(conta), ensure_ascii=False, indent=2),
                encoding="utf-8")
            _log(f"   🗂️  conta.json gravado (posta em {conta.get('handle')})")
        except Exception:
            pass
    # engajamento.json → o meta_uploader monta o 1º comentário (link no FB, isca no IG).
    # O 1º comentário do FB (e a auto-resposta que reusa esse link) sai com um link
    # ETIQUETADO 'fb' → toda venda vinda dele aparece como 'fb-<nicho>-<produto>' no
    # relatório (atribuição por canal). Só Shopee re-etiqueta; Amazon usa o base.
    # ⚠️ ISTO FALHAVA CALADO EM 43% DOS PACOTES. Medido em 15/08 com o
    # `diag_pacotes.py`: `engajamento.json` faltava em 146 de 336 pacotes —
    # 25 de 34 só na conta casa (74%). O `except Exception: pass` engolia,
    # ninguém via, e o 1º comentário (que carrega o link etiquetado 'fb' e é o
    # que dá atribuição por canal) simplesmente não saía.
    #
    # A causa provável é a geração do link etiquetado: `_link_do_canal` bate na
    # API de afiliado e, falhando, derrubava o bloco INTEIRO — inclusive a
    # escrita do arquivo, que nem depende dela.
    #
    # Dois consertos: o link etiquetado tem try próprio e cai pro link base
    # (link sem etiqueta é pior que link nenhum? não: é MUITO melhor — perde
    # atribuição, não perde a venda); e a falha da escrita passa a APARECER.
    # ⚠️ A ETIQUETA DO VÍDEO NASCE AQUI e precisa ir pros DOIS lugares: o link
    # (pra venda carregar) e o ledger (pra saber qual hook era). Gerar duas
    # vezes daria dois hashes diferentes e o join nunca fecharia — por isso ela
    # é calculada uma vez só e reusada logo abaixo, no `_reg`.
    id_video = _id_video(slug)

    link_fb = link
    if plataforma == "shopee":
        try:
            link_fb = _link_do_canal("fb", info.get("origem_url", ""), nicho, nome,
                                     link, fonte=perfil_fonte, video=id_video)
        except Exception as e:
            _log(f"   ⚠️  link etiquetado 'fb' falhou ({str(e)[:60]}) — uso o "
                 f"link base; a venda conta, a atribuição por canal não")
    try:
        eng = {"link": link_fb, "link_post": link, "produto": nome,
               "handle": (conta.get("handle") if conta else "") or "",
               "plataforma": plataforma, "nicho": nicho}
        (pp / "engajamento.json").write_text(
            json.dumps(eng, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        _log(f"   ❌ NÃO gravei engajamento.json ({str(e)[:80]}) — este post "
             f"vai sair SEM o 1º comentário com o link")
    (pp / "titulo_youtube.txt").write_text(f"{nome} #shorts"[:100], encoding="utf-8")
    (pp / "descricao_youtube.txt").write_text(
        (legenda + "\n\n" + hashtags).strip(), encoding="utf-8")
    (pp / "hashtags.txt").write_text(hashtags, encoding="utf-8")

    # 4) Site (passo 8) — Shopee pega foto oficial; Amazon vai sem foto (Camada 3)
    H._registrar_no_site(nome, link, imagem=info.get("imagem", ""),
                         plataforma=plataforma,
                         origem=info.get("origem_url", "") or info.get("product_link", ""))

    # 5) Ledger (passo 9) — tag SEMPRE categoria + plataforma + nicho (o CEO
    #    precisa disso; antes saía "sem_categoria"/"?" e cegava a análise).
    try:
        from posts_ledger import registrar as _reg
        categoria_ledger = categoria or nicho     # nunca vazio (nicho já calculado)
        # ⚠️ ANTES ISTO GRAVAVA `sub_ids=["tiktok"]` — uma etiqueta que NÃO é a
        # que foi pro link. O ledger guardava um rótulo genérico enquanto o
        # link carregava [canal, nicho, produto, fonte]: os dois lados nunca
        # tiveram como se encontrar. Agora grava a MESMA lista, e o `video_id`
        # solto no extra pra quem for cruzar não precisar saber a posição.
        # ⚠️ `url_shopee` FALTAVA AQUI, E ISSO CEGOU O DINHEIRO INTEIRO (03/09).
        # `posts_ledger._item_id()` extrai o padrão `i.LOJA.ITEM` da URL — e o
        # `link` é o SHORT LINK de afiliado (s.shopee.com.br/xxxx), que não
        # carrega itemId nenhum. Sem este argumento a chave nasce VAZIA.
        # Medido: 0% dos 340 posts do diário têm item_id, e por isso 33 das 34
        # conversões (R$121 em 90 dias) não puderam ser atribuídas a post algum.
        # O `telegram_repurpose_hunter` sempre passou; este produtor — que é o
        # principal — nunca passou. Dois produtores, um omitindo o campo: é o
        # mesmo desenho que já tinha deixado 42 de 85 posts sem `plataforma`.
        _reg(produto=nome, link=link,
             url_shopee=info.get("origem_url", "") or info.get("product_link", ""),
             categoria=categoria_ledger, hook=hook,
             legenda=legenda, slug=slug,
             sub_ids=_subids("ig", nicho, nome, perfil_fonte, id_video),
             plataforma=plataforma,                # shopee / amazon
             extra={"fonte": "tiktok", "nicho": nicho,
                    "perfil_fonte": perfil_fonte,   # PERFIL de origem (o CEO mede/poda)
                    "plataforma_afiliado": plataforma,
                    "video_id": id_video,           # ← join venda × hook
                    "fonte_views": info.get("views", 0)})
    except Exception:
        pass

    _log(f"   ✅ '{nome[:45]}' na esteira (pronto_para_postar/{slug})")
    return True


MAX_FALHAS_RENDER = int(os.environ.get("MAX_FALHAS_RENDER", "3"))

# As 6 contas. O rodízio varre a fila até achar produto pra todas elas.
_CONTAS = frozenset(("geral", "beleza", "tech", "casa", "moda", "pet"))

# Sufixos de download INCOMPLETO do yt-dlp. Precisam estar aqui porque
# `glob("video.*")` casa com 'video.mp4.part'.
PARCIAIS = (".part", ".ytdl", ".temp", ".tmp", ".download")


def _contar_falha(pj: Path) -> int:
    """Marca mais uma falha de render neste pacote. Devolve o total.

    ⚠️ O PACOTE-VENENO (05/09/2026, e já tinha acontecido em 17/08). Um vídeo
    do inbox baixou truncado SEM O FRAME 0:

        OSError: failed to read the first frame of video file

    Sem contador, ele fica na fila pra sempre: é escolhido, falha, continua lá,
    e amanhã queima outro slot. Com 6 posts/dia, um veneno na frente da fila
    custa 1/6 da produção diária, todo dia, sem ninguém perceber.

    ⚠️ CONTA, NÃO APAGA — e só desiste no 3º. Falha de render também acontece
    por motivo passageiro (rede, disco cheio, ffmpeg ocupado); desistir na
    primeira jogaria fora pacote bom.
    """
    try:
        info = json.loads(pj.read_text(encoding="utf-8"))
        n = int(info.get("falhas_render", 0)) + 1
        info["falhas_render"] = n
        if n >= MAX_FALHAS_RENDER:
            info["nao_e_produto"] = True
            info["motivo_bloqueio"] = f"produzir_tiktok: falhou no render {n}x"
        pj.write_text(json.dumps(info, ensure_ascii=False, indent=2),
                      encoding="utf-8")
        if n >= MAX_FALHAS_RENDER:
            _log(f"      ☠️  {n}ª falha — pacote saiu da fila (vídeo corrompido?)")
        else:
            _log(f"      ↻ {n}ª falha de {MAX_FALHAS_RENDER} — fica na fila")
        return n
    except Exception:
        return 0        # plano ilegível: o _produzir já reclamou, não insisto


def rodizio(itens: list, quantos: int) -> list:
    """Intercala nichos: uma rodada não pode ser toda da mesma conta.

    ⚠️ POR QUE ISSO EXISTE (05/09/2026). `produzir_tiktok.py 5` produziu 5 de 5
    pro @topshoppet_ e ZERO pras outras cinco contas. Não foi escolha: a fila é
    `sorted(INBOX.iterdir())`, ordem alfabética pura, e as pastas
    `achadinhos_*` sortam primeiro. Com 2154 pacotes, a ordem alfabética é um
    sorteio viciado — quem começa com 'a' leva tudo, sempre, todo dia.

    A meta é 1.000 seguidores em TODAS as contas. Cinco contas sem post não
    chegam lá, por melhor que o vídeo da sexta esteja.

    `itens` são `(nicho, obj)` na ordem da fila; devolve até `quantos` objs
    intercalando nicho e preservando a ordem original DENTRO de cada nicho —
    quem estava na frente do seu nicho continua na frente.
    """
    baldes: dict = {}
    ordem: list = []
    for nicho, obj in itens:
        if nicho not in baldes:
            baldes[nicho] = []
            ordem.append(nicho)
        baldes[nicho].append(obj)

    out: list = []
    while len(out) < quantos:
        levou = False
        for n in ordem:
            if not baldes[n]:
                continue
            out.append(baldes[n].pop(0))
            levou = True
            if len(out) >= quantos:
                break
        if not levou:
            break          # acabaram os baldes antes de encher a rodada
    return out


def _nicho_da_pasta(pj: Path) -> str:
    """Nicho do produto de uma pasta da fila (pra filtrar produção por conta)."""
    try:
        info = json.loads(pj.read_text(encoding="utf-8"))
        # 1) nicho HERDADO da fonte (curadoria manda): '@perfil #beleza' → beleza,
        #    mesmo que o produto não bata palavra-chave de beleza.
        # ⚠️ ESTA LISTA ESTAVA DESATUALIZADA (achado em 05/09/2026): tinha só
        # beleza/tech/geral, mas casa, moda e pet têm conta desde 21/08. Fonte
        # marcada '#pet' caía no roteamento por produto e podia ir pra outra
        # conta — a curadoria manual era ignorada nas três contas mais novas.
        nf = (info.get("nicho_fonte") or "").strip().lower()
        if nf in ("beleza", "tech", "geral", "casa", "moda", "pet"):
            return nf
        # 2) senão, roteia pelo PRODUTO (comportamento antigo).
        nome = info.get("produto") or info.get("termo") or ""
        cat = ""
        try:
            from creative_engine.narration_script_builder import _categoria_do_produto
            cat = _categoria_do_produto(nome) or ""
        except Exception:
            pass
        import roteador_contas as _RC
        return _RC.nicho_do_produto(nome, cat)
    except Exception:
        return "geral"


def main():
    # args: [N] e/ou "--nicho X". Ex.: 'produzir_tiktok.py --nicho tech 4'
    quantos = MAX_PADRAO
    nicho_alvo = ""
    sem_rodizio = False
    _args = sys.argv[1:]
    for _i, _a in enumerate(_args):
        if _a == "--nicho" and _i + 1 < len(_args):
            nicho_alvo = _args[_i + 1].strip().lower()
        elif _a == "--sem-rodizio":
            sem_rodizio = True
        elif _a.isdigit():
            quantos = max(1, int(_a))

    fila = _pendentes()
    if not fila:
        _log("inbox_tiktok vazio — roda o tiktok_coletor.py primeiro (sem --dry)")
        return 1
    if nicho_alvo:
        fila = [t for t in fila if _nicho_da_pasta(t[1]) == nicho_alvo]
        if not fila:
            _log(f"nenhum produto do nicho '{nicho_alvo}' na fila agora — nada a produzir")
            return 0
        _log(f"filtro de nicho '{nicho_alvo}' → {len(fila)} na fila")
    _log(f"{len(fila)} viral(is) no inbox · produzindo até {quantos} nesta rodada")

    # RODÍZIO DE CONTA (05/09/2026). Sem isto a rodada inteira cai numa conta só
    # — ver docstring do `rodizio()`. Desligado com --sem-rodizio, e sem efeito
    # quando já existe --nicho (aí a conta foi escolhida de propósito).
    lote = fila[:quantos]
    if not sem_rodizio and not nicho_alvo and len(fila) > quantos:
        # ⚠️ A JANELA CRESCE ATÉ ACHAR TODAS AS CONTAS (05/09/2026). Na primeira
        # versão ela era fixa em 120, e numa rodada real saiu `geral=0`: não
        # havia nenhum produto de 'geral' nos 120 primeiros da fila alfabética,
        # então o @topshop.__ ficou sem post — o rodízio "funcionou" e ainda
        # assim zerou uma conta.
        #
        # Continua sem classificar a fila inteira: `_nicho_da_pasta` lê JSON e
        # importa o roteador, e são ~1300 pacotes. Varre de 120 em 120 e PARA
        # assim que as 6 contas apareceram.
        _passo = max(quantos * 20, 120)
        _teto = min(len(fila), int(os.environ.get("RODIZIO_JANELA_MAX", "800")))
        _pares, _vistos, _i = [], set(), 0
        while _i < _teto:
            _fim = min(_i + _passo, _teto)
            for _t in fila[_i:_fim]:
                _n = _nicho_da_pasta(_t[1])
                _pares.append((_n, _t))
                _vistos.add(_n)
            _i = _fim
            if _CONTAS.issubset(_vistos):
                break

        lote = rodizio(_pares, quantos)
        _contagem = {}
        for _n, _ in _pares:
            _contagem[_n] = _contagem.get(_n, 0) + 1
        _log(f"   🔀 rodízio em {len(_pares)} da frente da fila: "
             + " · ".join(f"{k or '(IA)'}={v}" for k, v in sorted(_contagem.items())))
        _faltando = _CONTAS - _vistos
        if _faltando:
            # não é erro: pode não existir produto daquele nicho na fila. Mas
            # tem que APARECER, senão uma conta seca em silêncio.
            _log(f"   ⚠️ sem produto pra: {', '.join(sorted(_faltando))} "
                 f"(varri {len(_pares)} de {len(fila)})")

    ok = 0
    for pasta, pj, vid in lote:
        try:
            sucesso = _produzir(pasta, pj, vid)
        except Exception as e:
            _log(f"   ❌ erro em {pasta.name}: {str(e)[:120]}")
            sucesso = False
        # move a pasta pra _produzidos/ (ok) — falha fica pra tentar de novo
        if sucesso:
            ok += 1
            FEITOS.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(pasta), str(FEITOS / pasta.name))
            except Exception:
                pass
        else:
            _contar_falha(pj)

    _log(f"fim: {ok}/{len(lote)} produzidos. O daemon posta nos horários. 🚚")
    return 0


if __name__ == "__main__":
    # TRAVA DE INSTÂNCIA ÚNICA. Em 04/08/2026 o `crontab -l` tinha esta
    # mesma linha repetida (algumas 4x, o ceo_agent 8x) e as cópias rodaram
    # juntas o dia inteiro. shared/trava.py conta a história inteira.
    # Sem a trava disponível, roda como antes — ela protege, não bloqueia.
    try:
        from shared.trava import rodar_unico
    except Exception:
        sys.exit(main())
    sys.exit(rodar_unico("produzir_tiktok", main))
