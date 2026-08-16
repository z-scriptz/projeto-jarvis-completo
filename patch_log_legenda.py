#!/usr/bin/env python3
# patch_log_legenda.py -- registrar a legenda antes de enviar, sem sobrescrever.
#
# POR QUE EXISTE (15/08)
# 11 posts do @topshopcasa_ saíram sem legenda entre 10 e 15/08, e o último é
# de HOJE — está vivo. Passei quatro rodadas tentando DEDUZIR a causa de
# artefato (pacote pendente, plano no disco, ramo do publish_guard, data de
# commit) e derrubei duas hipóteses minhas contra dado.
#
# A razão de nenhuma fechar: **ninguém anota a legenda que foi enviada**. O
# `postar_instagram` recebe `legenda`, cria o container e a informação some.
# Uma linha de log responde na próxima postagem o que a inferência não
# respondeu.
#
# ⚠️ POR QUE PATCH E NÃO DEPLOY: o `deploy_seguro` recusou o arquivo com
# **DIVERGENTE** — o repo acompanha 6 commits dele e o conteúdo da VPS não bate
# com nenhum. Alguém editou de um lado só. Sobrescrever apagaria essa edição
# sem ninguém saber o que ela fazia, e ela pode ser justamente a causa que
# estamos procurando. A recusa está certa.
#
# Este patcher insere UMA linha de log antes da criação do container e não
# toca em mais nada. Se a âncora não existir (porque a edição da VPS mexeu ali),
# ele DIZ e não escreve — "não achei" é falha, não sucesso silencioso.
#
# Idempotente. Seco por padrão.
#
# Uso (na VPS, dentro de ~/jarvis):
#   python3 patch_log_legenda.py
#   python3 patch_log_legenda.py --aplicar

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ALVO = "meta_uploader.py"

ANCORA = "    # ── 1. Cria o container resumable"
MARCA = "legenda p/ Instagram:"

LINHAS = (
    '    # ⚠️ REGISTRA O QUE VAI SER ENVIADO, ANTES DE ENVIAR (15/08). 11 posts\n'
    '    # da casa sairam sem legenda e nao havia como saber o que foi mandado.\n'
    '    _corte = (legenda or "").strip()\n'
    '    log.info(f"   📝 legenda p/ Instagram: {len(_corte)} caractere(s)"\n'
    '             + (f" · começa com {_corte.splitlines()[0][:60]!r}" if _corte\n'
    '                else "  ⚠️ VAZIA — o Reel vai sair sem legenda"))\n'
    '\n'
)


def _log(m):
    print(f"[log-legenda] {m}", flush=True)


def _ler(p: Path) -> str:
    """Lê preservando as quebras de linha ORIGINAIS.

    ⚠️ `Path.read_text()` normaliza CRLF→LF na leitura e `write_text()` grava
    LF: juntos, reescrevem o arquivo INTEIRO em silêncio. Medido em 15/08 —
    meus patchers converteram `meta_uploader.py` (510 CR) e o
    `telegram_repurpose_hunter.py` (1968 CR) sem que nada avisasse, e o
    `deploy_seguro` passou a classificar os dois como DIVERGENTE por causa
    disso. Efeito colateral invisível numa ferramenta feita justamente pra
    não ter efeito colateral invisível.
    """
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def _escrever(p: Path, texto: str):
    """Grava sem traduzir quebra de linha (o texto já traz as originais)."""
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(texto)


def _no_estilo_do_arquivo(texto: str, original: str) -> str:
    """Converte as linhas NOVAS pra mesma quebra de linha do arquivo.

    Preservar o resto e inserir `\n` num arquivo CRLF deixaria o arquivo
    misturado — funciona em Python e suja qualquer diff daqui pra frente.
    Quem manda é o arquivo que já está lá, não o meu editor.
    """
    # normaliza SEMPRE, não só quando o texto novo é puro LF: o `subn` da
    # regex devolve o arquivo inteiro (já com CRLF) mais 3 linhas novas em LF,
    # e a versão condicional desistia justamente aí — deixando 1970 CR em 1973
    # linhas. Medido.
    if "\r\n" in original:
        return texto.replace("\r\n", "\n").replace("\n", "\r\n")
    return texto.replace("\r\n", "\n")


def main():
    p = argparse.ArgumentParser(
        description="Loga a legenda antes de criar o container do Instagram.")
    p.add_argument("--aplicar", action="store_true")
    args = p.parse_args()

    copias = sorted(c for c in RAIZ.rglob(ALVO)
                    if ".venv" not in c.parts and "__pycache__" not in c.parts)
    if not copias:
        _log(f"não achei nenhum {ALVO} debaixo de {RAIZ}")
        return 1

    falhou = mexidos = 0
    for c in copias:
        texto = _ler(c)

        if MARCA in texto:
            _log(f"·  {c.relative_to(RAIZ)}: já registra a legenda")
            continue

        # ⚠️ só faz sentido no arquivo que TEM a função — as outras cópias
        # podem ser espelhos antigos sem o fluxo de Reels
        if "def postar_instagram" not in texto:
            _log(f"·  {c.relative_to(RAIZ)}: não tem `postar_instagram`, pulo")
            continue

        _ancora = _no_estilo_do_arquivo(ANCORA, texto)
        n = texto.count(_ancora)
        if n != 1:
            _log(f"⚠️  {c.relative_to(RAIZ)}: âncora aparece {n}x — NÃO mexo")
            _log(f"     a VPS divergiu do repo; confira à mão onde o container "
                 f"é criado:")
            _log(f"     grep -n 'Cria o container' {c.relative_to(RAIZ)}")
            falhou += 1
            continue

        _log(f"→  {c.relative_to(RAIZ)}: insiro o log antes do container")
        if not args.aplicar:
            _log("     (seco: não escrevi. use --aplicar)")
            continue

        bak = c.with_suffix(c.suffix + ".bak_loglegenda")
        shutil.copy2(c, bak)
        _escrever(c, texto.replace(
            _ancora, _no_estilo_do_arquivo(LINHAS, texto) + _ancora, 1))
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
    _log(f"{mexidos} cópia(s) com log"
         + (f" · {falhou} não deu" if falhou else ""))
    if mexidos:
        _log("A próxima postagem da casa vai dizer, no log, quantos caracteres "
             "de legenda foram enviados. Aí a causa para de ser hipótese.")
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
