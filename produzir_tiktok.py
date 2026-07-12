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


def _log(m):
    print(f"[produzir_tiktok] {m}")


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


def _narrar_e_trocar_audio(video: Path, nome: str, contexto: str) -> bool:
    """Gera a narração (Michael/ElevenLabs, roteiro do vídeo) e SUBSTITUI o áudio
    do vídeo por ela — mata o áudio original (fim do copyright/crédito a terceiro).
    Mixa uma TRILHA DE FUNDO baixinha por baixo (loopada até o fim do vídeo), pra
    nunca ficar silêncio quando a narração acaba antes do vídeo.
    Best-effort: se algo falhar, mantém o vídeo com o áudio original."""
    if os.getenv("NARRAR_TIKTOK", "1").strip().lower() not in ("1", "true", "sim"):
        return False
    try:
        from narracao_ia import gerar as _gerar_narr
    except Exception:
        _log("   narracao_ia indisponível — mantém áudio original")
        return False
    narr = video.parent / (video.stem + "_narr.mp3")
    if not _gerar_narr(nome, contexto, narr):
        _log("   narração não gerada — mantém áudio original")
        return False

    out = video.with_suffix(".narrado.mp4")
    musica = _escolher_musica()
    vol = max(0.0, min(0.5, _f("MUSICA_FUNDO_VOL", 0.10)))

    # narração = trilha 1 (volume cheio), música = trilha 2 (baixa, loopada).
    # amix normaliza dividindo por 2, então pré-amplifico o dobro pra manter os
    # níveis. -shortest corta no fim do VÍDEO (música é infinita via stream_loop).
    if musica and vol > 0:
        fc = (f"[1:a]volume=2.0[nar];"
              f"[2:a]volume={2 * vol:.3f}[bg];"
              f"[nar][bg]amix=inputs=2:duration=longest:dropout_transition=0[a]")
        cmd = ["ffmpeg", "-y", "-i", str(video), "-i", str(narr),
               "-stream_loop", "-1", "-i", str(musica),
               "-filter_complex", fc, "-map", "0:v:0", "-map", "[a]",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
               "-shortest", str(out)]
        tag = f"narração (Michael) + trilha '{musica.name}' baixinha"
    else:
        cmd = ["ffmpeg", "-y", "-i", str(video), "-i", str(narr),
               "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
               "-c:a", "aac", "-b:a", "128k", str(out)]
        tag = "narração (Michael)"
        if not musica:
            _log(f"   ℹ️ sem trilha em {_dir_musica()} — vídeo sai só com narração")

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    # se a mixagem com música falhar (ffmpeg antigo etc.), tenta só narração
    if (r.returncode != 0 or not out.exists()) and musica and vol > 0:
        _log(f"   ⚠️ mix c/ música falhou, tento só narração: {(r.stderr or '')[-140:]}")
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", str(video), "-i", str(narr),
             "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "128k", str(out)],
            capture_output=True, text=True, timeout=180)
        tag = "narração (Michael)"

    if r.returncode == 0 and out.exists() and out.stat().st_size > 1000:
        out.replace(video)
        _log(f"   🎙️  áudio original SUBSTITUÍDO por {tag}")
        return True
    _log(f"   ⚠️ troca de áudio falhou (mantém original): {(r.stderr or '')[-160:]}")
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
    _narrar_e_trocar_audio(destino, nome, info.get("descricao", ""))

    # 2) Legenda + hashtags + plano (espelha os passos 5-6 do hunter)
    legenda = H._legenda_dinamica(nome, hook)
    hashtags = H._hashtags_para(categoria)
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
    (pp / "titulo_youtube.txt").write_text(f"{nome} #shorts"[:100], encoding="utf-8")
    (pp / "descricao_youtube.txt").write_text(
        (legenda + "\n\n" + hashtags).strip(), encoding="utf-8")
    (pp / "hashtags.txt").write_text(hashtags, encoding="utf-8")

    # 4) Site (passo 8) — com a foto oficial que o coletor já pegou
    H._registrar_no_site(nome, link, imagem=info.get("imagem", ""))

    # 5) Ledger (passo 9)
    try:
        from posts_ledger import registrar as _reg
        _reg(produto=nome, link=link, categoria=categoria, hook=hook,
             legenda=legenda, slug=slug, sub_ids=["tiktok"],
             plataforma="", extra={"fonte": "tiktok",
                                   "fonte_views": info.get("views", 0)})
    except Exception:
        pass

    _log(f"   ✅ '{nome[:45]}' na esteira (pronto_para_postar/{slug})")
    return True


def main():
    quantos = MAX_PADRAO
    if len(sys.argv) > 1:
        try:
            quantos = max(1, int(sys.argv[1]))
        except ValueError:
            pass

    fila = _pendentes()
    if not fila:
        _log("inbox_tiktok vazio — roda o tiktok_coletor.py primeiro (sem --dry)")
        return 1
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
