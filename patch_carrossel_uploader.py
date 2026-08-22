#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_carrossel_uploader.py - ACRESCENTA carrossel e story ao meta_uploader
# da VPS, sem reescrever o arquivo.
#
# POR QUE UM PATCH E NAO UM DEPLOY (22/08):
# O `deploy_seguro.py` recusou `meta_uploader.py` com DIVERGENTE - o repo
# acompanha o arquivo ha 8 commits e o conteudo da VPS nao bate com nenhum
# deles. Alguem editou de um lado so, e ninguem sabe o que. `--forcar` ali
# apagaria essa edicao desconhecida num arquivo que esta publicando em 6
# contas todo dia.
#
# E nao precisa: TODO o codigo novo e ADITIVO. Ele nao altera uma linha
# sequer de `postar_instagram`, `postar_facebook` ou dos helpers antigos -
# so acrescenta funcoes que ainda nao existem. Um patch que INSERE, e recusa
# quando nao tem certeza de onde inserir, faz o mesmo trabalho sem o risco.
#
# E IDEMPOTENTE: rodar de novo nao duplica nada.
#
# USO (na raiz do jarvis):
#   python3 patch_carrossel_uploader.py            # aplica
#   python3 patch_carrossel_uploader.py --conferir # so diz o que faria
#   python3 patch_carrossel_uploader.py --desfazer # volta o .bak

import sys
import shutil
import py_compile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CANDIDATOS = ["agents/meta_uploader.py", "meta_uploader.py",
              "integrations/meta_uploader.py"]

MARCA = "def postar_instagram_carrossel"
ANCORAS = ["# TESTE / DIAGN", "def diagnostico(", 'if __name__ == "__main__":']

BLOCO = r'''# ══════════════════════════════════════════════════════════════════════════
# CARROSSEL E STORY — os dois formatos que faltavam (22/08)
#
# ⚠️ POR QUE ESTE BLOCO NÃO REAPROVEITA `postar_instagram` ACIMA.
# Aquela função é a única coisa deste arquivo que está publicando de verdade,
# em 6 contas, todo dia. Refatorar ela pra extrair helpers deixaria o deploy
# DIVERGENTE num arquivo em produção — que é exatamente o cenário que o
# `deploy_seguro.py` manda tratar cirurgicamente. Então os helpers abaixo são
# NOVOS e só o código novo os usa; `postar_instagram` fica byte a byte igual.
# O preço é ~20 linhas parecidas com as de lá. É barato pelo que compra.
#
# ⚠️ A REGRA QUE DECIDE O DESENHO (doc oficial da Meta, conferida 22/08):
#   VÍDEO  → binário direto no rupload (nada precisa ser hospedado)
#   IMAGEM → SÓ `image_url`; "we cURL media used in publishing attempts"
# Logo: story de VÍDEO funciona sem infra nenhuma. Carrossel e story de IMAGEM
# exigem host público — é o que `midia_publica.py` resolve.
#
# Limites que a Meta impõe e que a gente respeita aqui:
#   · carrossel: 2 a 10 filhos; a legenda vai no PAI, nunca nos filhos
#   · todos os slides são cortados pela proporção do PRIMEIRO — renderize
#     todos no mesmo tamanho ou o corte come o texto dos outros
#   · story de vídeo: até 60s
#   · 100 posts publicados por API em 24h por conta (o carrossel conta como 1)
# ══════════════════════════════════════════════════════════════════════════
_IMAGENS = (".jpg", ".jpeg", ".png", ".webp")
_VIDEOS = (".mp4", ".mov")
STORY_MAX_SEG = 60


def _e_imagem(p) -> bool:
    return Path(p).suffix.lower() in _IMAGENS


def _garantir_jpeg(origem: Path) -> Path:
    """Devolve um caminho JPEG. Converte se vier PNG/WEBP.

    ⚠️ A DOC É CATEGÓRICA E ISTO NÃO DÁ AVISO NENHUM SE FOR IGNORADO:
    "JPEG is the only image format supported. Extended JPEG formats such as
    MPO and JPS are not supported."  Mandar um PNG não devolve "formato
    inválido" — devolve o mesmo `ERROR` genérico de container que qualquer
    outro problema devolve. Converter aqui é mais barato que descobrir isso
    olhando log.

    O PNG do render tem canal alfa; achatar contra BRANCO é a escolha certa
    porque o template das contas novas já é branco — sobre preto apareceria
    uma borda clara em volta do texto."""
    if origem.suffix.lower() in (".jpg", ".jpeg"):
        return origem
    try:
        from PIL import Image
    except Exception:
        log.warning(f"   ⚠️  {origem.name} não é JPEG e o Pillow não está aqui "
                    "pra converter — a Meta provavelmente vai recusar")
        return origem
    destino = origem.with_suffix(".jpg")
    try:
        img = Image.open(origem)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            fundo = Image.new("RGB", img.size, (255, 255, 255))
            fundo.paste(img, mask=img.split()[-1])
            img = fundo
        else:
            img = img.convert("RGB")
        img.save(destino, "JPEG", quality=92, optimize=True)
        log.info(f"   🔄 {origem.name} → JPEG (único formato que a Meta aceita)")
        return destino
    except Exception as e:
        log.warning(f"   ⚠️  não converti {origem.name} pra JPEG ({e})")
        return origem


def _dur_segundos(arquivo) -> float:
    """Duração via ffprobe. 0.0 quando não dá pra saber (nunca levanta)."""
    import subprocess
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(arquivo)],
            capture_output=True, text=True, timeout=30)
        return float((r.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def _criar_container(ig: str, tok: str, campos: dict) -> tuple:
    """POST /{ig}/media. Devolve (container_id, erro)."""
    try:
        d = _req().post(f"{GRAPH}/{ig}/media",
                        data={**campos, "access_token": tok}, timeout=60).json()
    except Exception as e:
        return "", f"exceção criando container: {e}"
    cid = d.get("id")
    if cid:
        return cid, ""
    return "", ((d.get("error") or {}).get("message") or str(d)[:200])


def _subir_binario(container_id: str, arquivo: Path, tok: str) -> str:
    """Sobe o binário pro rupload. Devolve "" se OK, ou a mensagem de erro."""
    try:
        with open(arquivo, "rb") as f:
            d = _req().post(
                f"{RUPLOAD}/{container_id}",
                headers={"Authorization": f"OAuth {tok}", "offset": "0",
                         "file_size": str(arquivo.stat().st_size)},
                data=f.read(), timeout=600).json()
    except Exception as e:
        return f"exceção no upload binário: {e}"
    return "" if d.get("success") else (d.get("message") or str(d)[:200])


def _esperar_container(container_id: str, tok: str, tentativas: int,
                       intervalo: float, exigir_finished: bool = True) -> str:
    """Poll do status_code. "" se ficou pronto, senão a mensagem de erro.

    ⚠️ `exigir_finished=False` pros FILHOS DE CARROSSEL de imagem: container de
    imagem costuma nascer pronto e a Meta às vezes nem devolve `status_code`.
    Exigir FINISHED ali significaria esperar 6 minutos por um campo que nunca
    vem, e depois desistir de um container que estava perfeito."""
    for _ in range(max(1, tentativas)):
        try:
            st = (_req().get(f"{GRAPH}/{container_id}",
                             params={"fields": "status_code", "access_token": tok},
                             timeout=30).json() or {}).get("status_code", "")
        except Exception:
            st = ""
        if st == "FINISHED":
            return ""
        if st == "ERROR":
            return f"container {container_id} deu ERROR no processamento"
        if not st and not exigir_finished:
            return ""          # sem status = imagem já pronta
        time.sleep(intervalo)
    if not exigir_finished:
        return ""
    return f"timeout esperando processar (container {container_id})"


def _publicar_container(ig: str, creation_id: str, tok: str) -> tuple:
    """POST /{ig}/media_publish. Devolve (media_id, erro)."""
    try:
        d = _req().post(f"{GRAPH}/{ig}/media_publish",
                        data={"creation_id": creation_id, "access_token": tok},
                        timeout=60).json()
    except Exception as e:
        return "", f"exceção publicando: {e}"
    mid = d.get("id")
    if mid:
        return mid, ""
    return "", ((d.get("error") or {}).get("message") or str(d)[:200])


def postar_instagram_story(arquivo: str) -> dict:
    """
    Publica um STORY (imagem ou vídeo) na conta do `conta.json` ao lado do arquivo.

    Vídeo entra pelo binário (sem hospedar nada). Imagem passa pelo
    `midia_publica` porque a Graph API não aceita binário de imagem.

    ⚠️ O QUE A API **NÃO** FAZ, e é bom saber antes de planejar em cima:
    story publicado por API NÃO carrega figurinha nenhuma — nem enquete, nem
    caixa de pergunta, nem link, nem contagem regressiva. Menção a @perfil sem
    figurinha funciona; o resto, não. Story de API é conteúdo, não interação.

    Retorna {"sucesso", "url"|"erro"}.
    """
    _ativar_conta(arquivo)
    erro_base = _checar_base()
    if erro_base:
        return {"sucesso": False, "erro": erro_base}
    if not _ig_user_id():
        return {"sucesso": False, "erro": "INSTAGRAM_USER_ID não configurado"}

    midia = Path(arquivo)
    if not midia.exists():
        return {"sucesso": False, "erro": f"arquivo não encontrado: {arquivo}"}

    ig, tok = _ig_user_id(), _token()
    quem = _CTX.get("handle") or f"ig_user_id={ig[-6:] or '?'}"

    # ── STORY DE IMAGEM: precisa de URL pública ──────────────────────────
    if _e_imagem(midia):
        try:
            from midia_publica import publicar, MidiaPublicaErro
        except Exception as e:
            return {"sucesso": False, "erro": f"midia_publica indisponível: {e}"}
        try:
            url_img = publicar(_garantir_jpeg(midia))
        except MidiaPublicaErro as e:
            return {"sucesso": False, "erro": str(e)}
        log.info(f"   🖼️  Story (imagem) [{quem}]: {midia.name}")
        cid, err = _criar_container(ig, tok, {"media_type": "STORIES",
                                              "image_url": url_img})
        if not cid:
            return {"sucesso": False, "erro": f"container não criado: {err}"}
        err = _esperar_container(cid, tok, 10, 3, exigir_finished=False)
        if err:
            return {"sucesso": False, "erro": err}
    # ── STORY DE VÍDEO: binário direto ───────────────────────────────────
    else:
        dur = _dur_segundos(midia)
        if dur > STORY_MAX_SEG:
            # Recusar aqui é melhor que deixar a Meta recusar: ela devolve
            # "container deu ERROR", que não diz que o problema é a duração.
            return {"sucesso": False,
                    "erro": f"story de vídeo aceita até {STORY_MAX_SEG}s e este "
                            f"tem {dur:.0f}s — corte antes de mandar"}
        log.info(f"   🎬 Story (vídeo {dur:.0f}s) [{quem}]: {midia.name}")
        cid, err = _criar_container(ig, tok, {"media_type": "STORIES",
                                              "upload_type": "resumable"})
        if not cid:
            return {"sucesso": False, "erro": f"container não criado: {err}"}
        err = _subir_binario(cid, midia, tok)
        if err:
            return {"sucesso": False, "erro": f"upload binário falhou: {err}"}
        err = _esperar_container(cid, tok, IG_POLL_MAX, IG_POLL_INTERVALO)
        if err:
            return {"sucesso": False, "erro": err}

    media_id, err = _publicar_container(ig, cid, tok)
    if not media_id:
        return {"sucesso": False, "erro": f"publish do story recusado: {err}"}
    log.info(f"   ✅ Story publicado [{quem}] — {media_id}")
    # Story não tem permalink público (some em 24h); devolve o id de referência
    return {"sucesso": True, "url": f"story:{media_id}", "media_id": media_id}


def postar_instagram_carrossel(imagens: list, legenda: str = "") -> dict:
    """
    Publica um CARROSSEL de imagens. A conta sai do `conta.json` ao lado do 1º
    slide (mesmo contrato de pasta que o vídeo usa).

    Retorna {"sucesso", "url"|"erro"}.
    """
    if not imagens:
        return {"sucesso": False, "erro": "nenhum slide informado"}
    _ativar_conta(imagens[0])
    erro_base = _checar_base()
    if erro_base:
        return {"sucesso": False, "erro": erro_base}
    if not _ig_user_id():
        return {"sucesso": False, "erro": "INSTAGRAM_USER_ID não configurado"}

    slides = [Path(p) for p in imagens]
    faltando = [p.name for p in slides if not p.exists()]
    if faltando:
        return {"sucesso": False, "erro": f"slide(s) não encontrado(s): {faltando}"}
    if not all(_e_imagem(p) for p in slides):
        return {"sucesso": False,
                "erro": "por ora o carrossel é só de imagens (jpg/png)"}
    if not 2 <= len(slides) <= 10:
        return {"sucesso": False,
                "erro": f"carrossel aceita de 2 a 10 slides, recebi {len(slides)}"}

    try:
        from midia_publica import publicar, MidiaPublicaErro
    except Exception as e:
        return {"sucesso": False, "erro": f"midia_publica indisponível: {e}"}

    ig, tok = _ig_user_id(), _token()
    quem = _CTX.get("handle") or f"ig_user_id={ig[-6:] or '?'}"
    _corte = (legenda or "").strip()
    log.info(f"   🎠 Carrossel [{quem}]: {len(slides)} slides · legenda "
             f"{len(_corte)} caractere(s)"
             + (f" · começa com {_corte.splitlines()[0][:60]!r}" if _corte
                else "  ⚠️ VAZIA"))

    # ── 1. Cada slide vira um container filho ────────────────────────────
    filhos = []
    for i, slide in enumerate(slides, 1):
        try:
            url_img = publicar(_garantir_jpeg(slide))
        except MidiaPublicaErro as e:
            return {"sucesso": False, "erro": f"slide {i}: {e}"}
        cid, err = _criar_container(ig, tok, {"image_url": url_img,
                                              "is_carousel_item": "true"})
        if not cid:
            return {"sucesso": False, "erro": f"slide {i} recusado: {err}"}
        filhos.append(cid)
    log.info(f"   🎠 {len(filhos)} slide(s) aceitos, montando o carrossel...")

    for i, cid in enumerate(filhos, 1):
        err = _esperar_container(cid, tok, 10, 3, exigir_finished=False)
        if err:
            return {"sucesso": False, "erro": f"slide {i}: {err}"}

    # ── 2. Container pai (a legenda mora AQUI, não nos filhos) ───────────
    pai, err = _criar_container(ig, tok, {"media_type": "CAROUSEL",
                                          "children": ",".join(filhos),
                                          "caption": legenda})
    if not pai:
        return {"sucesso": False, "erro": f"carrossel não montado: {err}"}
    err = _esperar_container(pai, tok, 20, 3, exigir_finished=False)
    if err:
        return {"sucesso": False, "erro": err}

    # ── 3. Publica ───────────────────────────────────────────────────────
    media_id, err = _publicar_container(ig, pai, tok)
    if not media_id:
        return {"sucesso": False, "erro": f"publish do carrossel recusado: {err}"}

    if _engajar_ligado():
        _comentar(media_id, _montar_comentario("instagram", slides[0]), tok)
    # ⚠️ os arquivos publicados NÃO são apagados aqui de propósito: a Meta pode
    # rebuscar a imagem depois do publish. A coleta por idade do midia_publica
    # (6h) resolve sem correr esse risco.
    link = _buscar_permalink(media_id, "permalink", tok,
                             f"https://www.instagram.com/p/{media_id}")
    log.info(f"   ✅ Carrossel publicado [{quem}] — {link}")
    return {"sucesso": True, "url": link}
'''

CLI_DE = '    parser.add_argument("--legenda", default="Teste TopShop", help="legenda")'
CLI_PARA = """    parser.add_argument("--story", help="caminho da imagem OU video pra postar como Story")
    parser.add_argument("--carrossel", nargs="+", metavar="IMG",
                        help="2 a 10 imagens, na ordem dos slides")
""" + CLI_DE

CLI_ACAO_DE = """    else:
        print("\\nUse --diagnostico, --facebook <video> ou --instagram <video>")"""
CLI_ACAO_PARA = """    elif args.story:
        print(f"\\n\U0001f4f2 Postando Story: {args.story}")
        print(f"   -> {postar_instagram_story(args.story)}")
    elif args.carrossel:
        print(f"\\n\U0001f3a0 Postando carrossel de {len(args.carrossel)} slide(s)")
        print(f"   -> {postar_instagram_carrossel(args.carrossel, args.legenda)}")
    else:
        print("\\nUse --diagnostico, --facebook <video>, --instagram <video>,")
        print("    --story <arquivo> ou --carrossel <img1> <img2> ...")"""


def _alvo() -> Path:
    for c in CANDIDATOS:
        p = RAIZ / c
        if p.exists():
            return p
    print("[x] nao achei o meta_uploader.py. Procurei em:")
    for c in CANDIDATOS:
        print(f"      {RAIZ / c}")
    sys.exit(1)


def _desfazer(alvo: Path) -> int:
    bak = alvo.with_suffix(".py.bak")
    if not bak.exists():
        print(f"[x] nao existe backup em {bak}")
        return 1
    shutil.copy2(bak, alvo)
    print(f"[<-] {alvo} restaurado de {bak.name}")
    print("     Nao esqueca:  systemctl restart jarvis.service")
    return 0


def main() -> int:
    args = set(sys.argv[1:])
    alvo = _alvo()
    print(f"[alvo] {alvo}")

    if "--desfazer" in args:
        return _desfazer(alvo)

    texto = alvo.read_text(encoding="utf-8")

    if MARCA in texto:
        print("[ok] carrossel e story JA estao instalados - nada a fazer.")
        return 0

    pos = -1
    for a in ANCORAS:
        pos = texto.find(a)
        if pos >= 0:
            # sobe ate o comeco da linha (ou da barra de secao acima dela)
            pos = texto.rfind("\n", 0, pos) + 1
            linha_acima = texto.rfind("\n", 0, pos - 1) + 1
            if texto[linha_acima:pos].startswith("# " + "\u2550" * 5):
                pos = linha_acima
            print(f"[pos] inserindo antes de: {a}")
            break
    if pos < 0:
        # RECUSAR E O CERTO AQUI. Anexar no fim "pra nao falhar" colocaria as
        # funcoes DEPOIS do `if __name__`, onde elas existem mas o CLI que as
        # chama ja rodou - o tipo de conserto que parece ter funcionado.
        print("[x] nao achei onde inserir (nenhuma ancora bate).")
        print("    O arquivo da VPS esta mais diferente do que eu esperava.")
        print(f"    Mande a saida de:  grep -n 'def diagnostico\\|__main__' {alvo}")
        return 1

    novo = texto[:pos] + BLOCO + "\n\n" + texto[pos:]

    if CLI_DE in novo and "--carrossel" not in novo:
        novo = novo.replace(CLI_DE, CLI_PARA, 1)
        print("[pos] CLI: --story e --carrossel acrescentados")
    else:
        print("[!] CLI: nao mexi (as funcoes funcionam por import do mesmo jeito)")
    if CLI_ACAO_DE in novo:
        novo = novo.replace(CLI_ACAO_DE, CLI_ACAO_PARA, 1)
    else:
        print("[!] CLI: bloco de acoes nao bateu - chame por import, nao por --story")

    if "--conferir" in args:
        print(f"\n[teste] inseriria {BLOCO.count(chr(10))} linhas. Nada gravado.")
        return 0

    # compila ANTES de trocar o arquivo bom por um quebrado
    temp = alvo.with_suffix(".py.novo")
    temp.write_text(novo, encoding="utf-8")
    try:
        py_compile.compile(str(temp), doraise=True)
    except py_compile.PyCompileError as e:
        temp.unlink()
        print(f"[x] o resultado nao compila - NADA foi alterado:\n{e}")
        return 1

    shutil.copy2(alvo, alvo.with_suffix(".py.bak"))
    temp.replace(alvo)
    print(f"[bak] backup em {alvo.name}.bak")
    print(f"[ok] {alvo} patchado e compilando.")
    print("\n     Agora:  systemctl restart jarvis.service")
    print("     (editar o .py NAO troca o modulo ja carregado no daemon)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
