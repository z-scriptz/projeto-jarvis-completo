#!/usr/bin/env python3
# patch_quarentena.py -- pacote ruim para de derrubar a conta inteira.
#
# POR QUE EXISTE (17/08)
# O `deploy_seguro.py` recusou o `daemon_maestro.py` com **COLISÃO**: existem
# duas cópias na VPS (`agents/` e a raiz) e ele não tem como saber qual é a
# viva. A recusa está certa — subir o arquivo inteiro regride tudo que divergiu
# fora deste repo. Mas eu não preciso do arquivo inteiro: preciso de UMA função
# nova e UM `elif`.
#
# O QUE ELE CONSERTA
# ──────────────────
# A @topshoptech_ ficou 3 dias sem postar com 97 pacotes bons na fila. Um único
# pacote (`mesa_magica_de_desenho_projetor_de_giraf`) tinha o vídeo CORROMPIDO
# — `ffprobe` mostrou `Invalid NAL unit size` centenas de vezes, e o Instagram
# recusou com `ProcessingFailedError · retriable: False`, o Facebook com
# "try again with another file".
#
# Só que cada conta entra no slot com UM pacote (`alvos`), e quando ele falha o
# laço acaba ali — **não cai pro próximo**. Nada marcava o pacote, então ele
# voltava a ser o escolhido no slot seguinte, e no seguinte. Um arquivo ruim
# = a conta inteira parada até o pacote vencer, 27 dias depois. ~40 posts.
#
# O conserto conta as falhas por slug e, no teto, move o pacote pra
# `fila_problema/` — MOVE, não apaga, igual ao `_expurgar_vencidos`.
#
# ⚠️ LOGA EM ERROR, NÃO WARNING. Quarentena silenciosa vira cemitério: o pacote
# some da fila, a conta volta a postar, e ninguém descobre que o render está
# gerando vídeo que a Meta recusa. O alerta é a metade útil do conserto.
#
# Idempotente. Seco por padrão. Mexe em TODAS as cópias (o import pode resolver
# pra qualquer uma das duas).
#
# Uso (na VPS, dentro de ~/jarvis):
#   python3 patch_quarentena.py
#   python3 patch_quarentena.py --aplicar
#   sudo systemctl restart jarvis.service     # ⚠️ sem isto o código novo NÃO roda

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ALVO = "daemon_maestro.py"

MARCA = "_registrar_falha"

ANCORA_FUNC = "def _expurgar_vencidos() -> int:"

FUNC = '''_FALHAS = RAIZ / "shared" / "falhas_postagem.json"


def _registrar_falha(slug: str, cfg: dict) -> None:
    """Conta as falhas de um pacote e, no teto, tira ele da frente da conta.

    ⚠️ POR QUE ISTO EXISTE (17/08) — o pacote-veneno.
    O `mesa_magica_de_desenho_projetor_de_giraf` falhou no Instagram em 15/08
    (3 tentativas) e DE NOVO em 17/08 (3 tentativas), com o mesmo erro:
    `ProcessingFailedError`, `retriable: False`, e o Facebook pedindo "try
    again with another file". O `ffprobe` confirmou: o bitstream H.264 esta
    corrompido (`Invalid NAL unit size`), embora o container minta bonito
    (1080x1920, 30fps, 7,9s -- tudo dentro do padrao de Reels).

    As duas redes recusam o ARQUIVO e a Meta diz que nao adianta repetir. Mas
    nada marcava o pacote, entao ele seguia sendo o escolhido da conta a cada
    slot -- e como `alvos` traz UM pacote por conta e o laco nao cai pro
    proximo quando falha, **a conta inteira perdia o slot por um arquivo.**
    A tech ficou 3 dias sem postar com 97 pacotes bons esperando atras.

    Sem teto isso duraria os 27 dias da validade: ~40 posts por um video.

    Config: `falhas_pra_quarentena` (padrao 2; 0 desliga).
    """
    try:
        teto = int(cfg.get("falhas_pra_quarentena", 2))
    except (TypeError, ValueError):
        teto = 2
    if teto <= 0:
        return
    try:
        dados = (json.loads(_FALHAS.read_text(encoding="utf-8"))
                 if _FALHAS.exists() else {})
    except Exception:
        dados = {}
    n = int(dados.get(slug, 0)) + 1
    dados[slug] = n

    if n >= teto:
        destino = PRONTO_DIR.parent / "fila_problema"
        pasta = PRONTO_DIR / slug
        try:
            if pasta.is_dir():
                destino.mkdir(parents=True, exist_ok=True)
                shutil.move(str(pasta), str(destino / slug))
                # ⚠️ ERRO, nao warning: alguem precisa OLHAR o arquivo. Sem
                # isso a quarentena vira um cemiterio silencioso -- o pacote
                # some da fila e ninguem descobre que o render esta gerando
                # video que a Meta recusa.
                log.error(f"   🚧 '{slug}' falhou {n}x → fila_problema/ "
                          f"(a conta volta a postar no proximo slot). "
                          f"CONFIRA o video.mp4 com o auditoria_video.py: as "
                          f"duas redes recusaram o arquivo.")
                dados.pop(slug, None)
        except Exception as erro:
            log.warning(f"   ⚠️  nao consegui mover '{slug}' pra quarentena: "
                        f"{str(erro)[:100]}")
    else:
        log.warning(f"   ⚠️  '{slug}' falhou {n}/{teto} — mais uma e sai da "
                    f"frente da conta")
    try:
        _FALHAS.parent.mkdir(parents=True, exist_ok=True)
        _FALHAS.write_text(json.dumps(dados, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    except Exception as erro:
        log.warning(f"   ⚠️  nao gravei {_FALHAS.name}: {str(erro)[:80]}")


'''

ANCORA_CHAMADA = """            if dry_run or _postar_produto(slug, cfg, hist):
                ok_slugs.append(slug)"""

CHAMADA = """            if dry_run or _postar_produto(slug, cfg, hist):
                ok_slugs.append(slug)
            elif not dry_run:
                # ⚠️ FALHA AQUI CUSTAVA O SLOT INTEIRO DA CONTA (17/08). Cada
                # conta traz UM pacote em `alvos`; se ele falha, antes acabava
                # aqui e a conta simplesmente nao postava -- mesmo com 97
                # pacotes bons atras.
                _registrar_falha(slug, cfg)"""


def _log(m):
    print(f"[quarentena] {m}", flush=True)


def _ler(p: Path) -> str:
    """Lê preservando as quebras de linha ORIGINAIS.

    ⚠️ `Path.read_text()` normaliza CRLF→LF e `write_text()` grava LF: juntos
    reescrevem o arquivo INTEIRO em silêncio. Medido em 15/08 — meus patchers
    converteram dois arquivos sem avisar e o `deploy_seguro` passou a
    classificá-los como DIVERGENTE por causa disso.
    """
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def _escrever(p: Path, texto: str):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(texto)


def _no_estilo(texto: str, original: str) -> str:
    if "\r\n" in original:
        return texto.replace("\r\n", "\n").replace("\n", "\r\n")
    return texto.replace("\r\n", "\n")


def _copias():
    return sorted(p for p in RAIZ.rglob(ALVO)
                  if ".venv" not in p.parts and "__pycache__" not in p.parts)


def main():
    p = argparse.ArgumentParser(
        description="Quarentena de pacote que a Meta recusa (2 inserções).")
    p.add_argument("--aplicar", action="store_true")
    args = p.parse_args()

    copias = _copias()
    if not copias:
        _log(f"não achei nenhum {ALVO} debaixo de {RAIZ}")
        return 1

    _log(f"{len(copias)} cópia(s) no disco:")
    for c in copias:
        _log(f"   {c.relative_to(RAIZ)}")
    print()

    falhou = mexidos = 0
    for c in copias:
        texto = _ler(c)

        if MARCA in texto:
            _log(f"·  {c.relative_to(RAIZ)}: já tem a quarentena")
            continue

        a_func = _no_estilo(ANCORA_FUNC, texto)
        a_cham = _no_estilo(ANCORA_CHAMADA, texto)
        n1, n2 = texto.count(a_func), texto.count(a_cham)
        if n1 != 1 or n2 != 1:
            # ⚠️ não achar NÃO é sucesso: esta cópia segue derrubando a conta
            _log(f"⚠️  {c.relative_to(RAIZ)}: âncoras {n1}x e {n2}x "
                 f"(esperado 1 e 1) — NÃO mexo")
            _log(f"     confira à mão:  grep -n '_expurgar_vencidos\\|"
                 f"ok_slugs.append' {c.relative_to(RAIZ)}")
            falhou += 1
            continue

        _log(f"→  {c.relative_to(RAIZ)}: insiro a função + o `elif`")
        if not args.aplicar:
            _log("     (seco: não escrevi. use --aplicar)")
            continue

        bak = c.with_suffix(c.suffix + ".bak_quarentena")
        shutil.copy2(c, bak)
        novo = texto.replace(a_func, _no_estilo(FUNC, texto) + a_func, 1)
        novo = novo.replace(a_cham, _no_estilo(CHAMADA, texto), 1)
        _escrever(c, novo)

        r = subprocess.run([sys.executable, "-m", "py_compile", str(c)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            shutil.copy2(bak, c)
            _log(f"     ✗ NÃO COMPILA — restaurei. {(r.stderr or '')[:140]}")
            falhou += 1
            continue
        mexidos += 1
        _log(f"     ✅ escrito (backup em {bak.name})")

    print()
    if not args.aplicar:
        _log("nada foi escrito. Rode de novo com --aplicar.")
        return 0
    _log(f"{mexidos} cópia(s) com quarentena"
         + (f" · {falhou} não deu" if falhou else ""))
    if mexidos:
        _log("⚠️ AGORA REINICIE:  sudo systemctl restart jarvis.service")
        _log("   O daemon carregou o módulo ANTIGO na memória quando subiu —")
        _log("   editar o .py no disco não muda o processo que já está rodando.")
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
