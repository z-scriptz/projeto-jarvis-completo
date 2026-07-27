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
MAX_PADRAO = 2

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


def _subids(canal: str, nicho: str, nome: str, fonte: str = "") -> list:
    """Sub-IDs na ordem canônica: [canal, nicho, produto, FONTE]. O índice 3
    (fonte = perfil de origem) é o que o CEO cruza com a venda pra saber qual
    perfil converte. Só alfanumérico e ≤16 chars cada (a Shopee rejeita
    _/-/espaço → erro 11001). Fonte vazia → slot omitido (link de canal sem fonte)."""
    import re
    def s(x, padrao):
        v = re.sub(r"[^A-Za-z0-9]", "", str(x or ""))[:16]
        return v or padrao
    ids = [s(canal, "x"), s(nicho, "geral"), s(nome, "prod")]
    if str(fonte or "").strip():
        ids.append(s(fonte, "fonte"))
    return ids


def _link_do_canal(canal: str, origem_url: str, nicho: str, nome: str, base: str,
                   fonte: str = "") -> str:
    """Gera um link de afiliado etiquetado pro CANAL (ex: 'fb') + FONTE. Se não der,
    usa o link base (best-effort — nunca quebra a produção)."""
    if not (_gerar_link and origem_url):
        return base
    try:
        r = _gerar_link(origem_url, sub_ids=_subids(canal, nicho, nome, fonte))
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


def _narrar_e_trocar_audio(video: Path, nome: str, contexto: str, nicho: str = "") -> bool:
    """Gera a narração (ElevenLabs, voz do nicho, roteiro do vídeo) e SUBSTITUI o áudio
    do vídeo por ela — mata o áudio original (fim do copyright/crédito a terceiro).
    Mixa uma TRILHA DE FUNDO baixinha por baixo (loopada até o fim do vídeo), pra
    nunca ficar silêncio quando a narração acaba antes do vídeo.
    Best-effort: se algo falhar, mantém o vídeo com o áudio original."""
    if os.getenv("NARRAR_TIKTOK", "1").strip().lower() not in ("1", "true", "sim"):
        return False

    def _avisa(motivo):
        _log(f"   🚨 alerta: narração falhou ({motivo})")
        _alerta_telegram(f"🚨 <b>Jarvis — narração falhou</b>\n🎬 {nome[:60]}\n"
                         f"⚠️ {motivo}\nVídeo saiu com o áudio ORIGINAL "
                         f"(risco de copyright/crédito). Re-narra quando puder.")

    try:
        from narracao_ia import gerar as _gerar_narr
    except Exception:
        _log("   narracao_ia indisponível — mantém áudio original")
        _avisa("narracao_ia indisponível (import)")
        return False
    narr = video.parent / (video.stem + "_narr.mp3")
    if not _gerar_narr(nome, contexto, narr, nicho):
        _log("   narração não gerada — mantém áudio original")
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
    _log(f"   ⚠️ troca de áudio falhou (mantém original): {(r.stderr or '')[-160:]}")
    _avisa("ffmpeg (troca de áudio) falhou")
    try:
        out.unlink()
    except Exception:
        pass
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
        vids = list(pasta.glob("video.*"))
        if pj.exists() and vids:
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

    # FUNDO por nicho: geral (@topshop.__) = PRETO (mantém o grid da principal);
    # contas novas (beleza/tech) = BRANCO (estilo Alana). Override por BG_<NICHO>.
    _bg_padrao = "preto" if nicho in ("geral", "") else "branco"
    os.environ["TOPSHOP_BG"] = (os.environ.get("FORCE_BG")          # p/ testar os 2
                                or os.environ.get("BG_" + nicho.upper(), _bg_padrao))
    _log(f"   🎨 fundo '{os.environ['TOPSHOP_BG']}' (nicho {nicho or 'geral'})")

    # LOGO por conta/nicho: cada perfil tem sua marca (tech=teal, beauty=rosa).
    # Coloque os PNGs em assets/brand/. Cai na logo_ts.png se o arquivo não existir.
    _LOGO_NICHO = {"beleza": "logo_ts_beauty.png", "tech": "logo_ts_tech.png"}
    os.environ["TOPSHOP_LOGO"] = (os.environ.get("FORCE_LOGO")
                                  or _LOGO_NICHO.get(nicho, "logo_ts.png"))
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
    }

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
    legenda = H._legenda_dinamica(nome, hook)
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
    try:
        link_fb = link
        if plataforma == "shopee":
            link_fb = _link_do_canal("fb", info.get("origem_url", ""), nicho, nome,
                                     link, fonte=perfil_fonte)
        eng = {"link": link_fb, "link_post": link, "produto": nome,
               "handle": (conta.get("handle") if conta else "") or "",
               "plataforma": plataforma, "nicho": nicho}
        (pp / "engajamento.json").write_text(
            json.dumps(eng, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    (pp / "titulo_youtube.txt").write_text(f"{nome} #shorts"[:100], encoding="utf-8")
    (pp / "descricao_youtube.txt").write_text(
        (legenda + "\n\n" + hashtags).strip(), encoding="utf-8")
    (pp / "hashtags.txt").write_text(hashtags, encoding="utf-8")

    # 4) Site (passo 8) — Shopee pega foto oficial; Amazon vai sem foto (Camada 3)
    H._registrar_no_site(nome, link, imagem=info.get("imagem", ""),
                         plataforma=plataforma)

    # 5) Ledger (passo 9) — tag SEMPRE categoria + plataforma + nicho (o CEO
    #    precisa disso; antes saía "sem_categoria"/"?" e cegava a análise).
    try:
        from posts_ledger import registrar as _reg
        categoria_ledger = categoria or nicho     # nunca vazio (nicho já calculado)
        _reg(produto=nome, link=link, categoria=categoria_ledger, hook=hook,
             legenda=legenda, slug=slug, sub_ids=["tiktok"],
             plataforma=plataforma,                # shopee / amazon
             extra={"fonte": "tiktok", "nicho": nicho,
                    "perfil_fonte": perfil_fonte,   # PERFIL de origem (o CEO mede/poda)
                    "plataforma_afiliado": plataforma,
                    "fonte_views": info.get("views", 0)})
    except Exception:
        pass

    _log(f"   ✅ '{nome[:45]}' na esteira (pronto_para_postar/{slug})")
    return True


def _nicho_da_pasta(pj: Path) -> str:
    """Nicho do produto de uma pasta da fila (pra filtrar produção por conta)."""
    try:
        info = json.loads(pj.read_text(encoding="utf-8"))
        # 1) nicho HERDADO da fonte (curadoria manda): '@perfil #beleza' → beleza,
        #    mesmo que o produto não bata palavra-chave de beleza.
        nf = (info.get("nicho_fonte") or "").strip().lower()
        if nf in ("beleza", "tech", "geral"):
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
    _args = sys.argv[1:]
    for _i, _a in enumerate(_args):
        if _a == "--nicho" and _i + 1 < len(_args):
            nicho_alvo = _args[_i + 1].strip().lower()
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

    ok = 0
    for pasta, pj, vid in fila[:quantos]:
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

    _log(f"fim: {ok}/{min(quantos, len(fila))} produzidos. O daemon posta nos horários. 🚚")
    return 0


if __name__ == "__main__":
    sys.exit(main())
