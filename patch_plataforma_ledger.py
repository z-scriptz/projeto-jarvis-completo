#!/usr/bin/env python3
# patch_plataforma_ledger.py -- o CEO parar de ver "?" em metade dos posts.
#
# POR QUE EXISTE (15/08)
# Relatório de domingo: **42 dos 85 posts com plataforma desconhecida (`?`)**,
# o que apaga qualquer análise por plataforma de venda.
#
# A causa não é falta de procedimento — é UMA LINHA. São dois produtores
# gravando no `posts_ledger`, e só um passa o campo:
#
#   produzir_tiktok.py:264   plataforma = (info.get("plataforma") or "shopee")
#                    :425    _reg(..., plataforma=plataforma, ...)   ✅
#
#   telegram_repurpose_hunter.py:1750
#                            _reg_post(..., slug=slug, sub_ids=_subs,
#                                      extra={...})                  ❌ sem plataforma
#
# E `posts_ledger.registrar()` tem `plataforma: str = ""` — então o campo entra
# vazio e vira `?` no relatório. Metade da produção fora da análise por causa
# de um argumento omitido. Quase exatamente 42/85.
#
# ⚠️ POR QUE PATCH E NÃO DEPLOY: o `deploy_seguro` recusa este arquivo com
# COLISÃO (duas cópias na VPS, `integrations/` e a raiz). A recusa está certa.
# Trocar 1800 linhas pra corrigir 1 é que não está.
#
# ⚠️ E O VALOR É DERIVADO, NÃO CHUTADO: `"shopee" if url_shopee else ""`. Sem
# link da Shopee eu não afirmo Shopee — `?` honesto é melhor que rótulo errado,
# porque rótulo errado contamina exatamente a análise que este conserto existe
# pra viabilizar.
#
# Idempotente. Seco por padrão. Mexe em todas as cópias (o `produzir_tiktok`
# importa a do pacote mas cai na da raiz se o import falhar).
#
# Uso (na VPS, dentro de ~/jarvis):
#   python3 patch_plataforma_ledger.py
#   python3 patch_plataforma_ledger.py --aplicar

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ALVO = "telegram_repurpose_hunter.py"

VELHO = ('                  slug=slug, sub_ids=_subs,\n'
         '                  extra={"fonte": "telegram", "nicho": nicho})')

NOVO = ('                  slug=slug, sub_ids=_subs,\n'
        '                  # sem isto o CEO vê "?" — eram 42 de 85 posts\n'
        '                  # (produzir_tiktok passa; este caminho não passava)\n'
        '                  plataforma=("shopee" if url_shopee else ""),\n'
        '                  extra={"fonte": "telegram", "nicho": nicho})')

MARCA = 'plataforma=("shopee" if url_shopee else "")'


def _log(m):
    print(f"[plataforma] {m}", flush=True)


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


def _copias():
    return sorted(p for p in RAIZ.rglob(ALVO)
                  if ".venv" not in p.parts and "__pycache__" not in p.parts)


def main():
    p = argparse.ArgumentParser(
        description="Passa `plataforma` no ledger do hunter (1 linha).")
    p.add_argument("--aplicar", action="store_true")
    args = p.parse_args()

    copias = _copias()
    if not copias:
        _log(f"não achei nenhum {ALVO} debaixo de {RAIZ}")
        return 1

    falhou = mexidos = 0
    for c in copias:
        try:
            texto = _ler(c)
        except Exception as e:
            _log(f"✗ {c.name}: não consegui ler — {str(e)[:70]}")
            falhou += 1
            continue

        _velho = _no_estilo_do_arquivo(VELHO, texto)
        if MARCA in texto:
            _log(f"·  {c.relative_to(RAIZ)}: já passa a plataforma")
            continue
        n = texto.count(_velho)
        if n == 0:
            # ⚠️ não achar NÃO é sucesso: esta cópia continua gravando "?"
            _log(f"⚠️  {c.relative_to(RAIZ)}: não achei a chamada do ledger "
                 f"nesse formato — ESTA CÓPIA SEGUE SEM PLATAFORMA")
            _log(f"     confira à mão:  grep -n 'sub_ids=_subs' "
                 f"{c.relative_to(RAIZ)}")
            falhou += 1
            continue
        if n > 1:
            _log(f"⚠️  {c.relative_to(RAIZ)}: {n} ocorrências do trecho — "
                 f"não mexo às cegas em algo que aparece mais de uma vez")
            falhou += 1
            continue

        _log(f"→  {c.relative_to(RAIZ)}: 1 chamada do ledger, sem plataforma")
        if not args.aplicar:
            _log("     (seco: não escrevi. use --aplicar)")
            continue

        bak = c.with_suffix(c.suffix + ".bak_plat")
        shutil.copy2(c, bak)
        _escrever(c, texto.replace(_velho,
                                   _no_estilo_do_arquivo(NOVO, texto), 1))
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
    _log(f"{mexidos} cópia(s) corrigida(s)"
         + (f" · {falhou} com problema" if falhou else ""))
    _log("⚠️ vale só pros posts NOVOS. Os 42 antigos continuam '?' — o campo "
         "não existe no registro já gravado, e inventá-lo agora seria "
         "adivinhar a plataforma de um post do passado.")
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
