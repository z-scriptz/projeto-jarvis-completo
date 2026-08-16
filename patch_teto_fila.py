#!/usr/bin/env python3
# patch_teto_fila.py -- tirar o teto de 80 do ACERVO, sem sobrescrever arquivo.
#
# POR QUE EXISTE (15/08)
# O `deploy_seguro.py` recusou o `telegram_repurpose_hunter.py` com COLISÃO:
# existem DUAS cópias na VPS (`integrations/` e a raiz) e ele não tem como
# saber qual é a viva. A recusa está certa — o que está errado é a pergunta.
# Eu não preciso subir o arquivo inteiro: preciso mudar DUAS LINHAS que
# conheço letra por letra.
#
# A diferença importa. `git show FETCH_HEAD:arquivo > destino` troca 1800
# linhas para corrigir 2, e leva junto todo o histórico que divergiu fora
# deste repo. Substituição exata de texto não regride nada: ou acha o
# trecho e troca, ou não acha e não faz nada.
#
# O QUE ELE MUDA
# ──────────────
#   max_itens: int = 80   →   max_itens: int = 0   (0 = usa o teto do .env)
#   fila = fila[:max_itens]   →   corta em FILA_ACERVO_MAX (default 500)
#
# POR QUÊ: o gravador truncava a fila em 80 a cada gravação, e os dois
# chamadores usavam o default. Produto novo EXPULSAVA o mais antigo — medido
# na VPS em 15/08: 80/80, janela de 7 dias. O acervo virou janela deslizante e
# produto que saía dela sumia do site calado. O teto passa a viver no
# `deploy_site.py` (`VITRINE_MAX_PRODUTOS`), que é onde os custos reais estão:
# peso da página e chamada de API do health-check.
#
# ⚠️ TETO GRANDE, NÃO "SEM TETO" — e essa correção é de mim mesmo. A primeira
# versão deixava o acervo ilimitado, o que ARMAVA uma bomba em quem lê a fila:
# `validar_fila.py` tem `--limite` default 0 (= todos), pausa de 1,5s e uma
# chamada de API por produto; `preencher_fotos.py` varre todos sem foto. Os
# dois estavam implicitamente protegidos pelo `fila[:80]`. Tirar o corte sem
# limitar os consumidores trocaria uma janela de 7 dias por uma rodada que não
# termina. 500 é ~45 dias no ritmo medido (~11/dia) com pior caso conhecido.
#
# ⚠️ MEXE EM TODAS AS CÓPIAS, de propósito. Com duas no disco, corrigir só uma
# deixa uma bomba: o `produzir_tiktok.py` importa a do pacote mas cai na da
# raiz se o import falhar, e aí o teto voltaria sem ninguém entender por quê.
#
# Idempotente: rodar duas vezes não faz nada na segunda.
# Padrão é SECO. Só escreve com --aplicar.
#
# Uso (na VPS, dentro de ~/jarvis):
#   python3 patch_teto_fila.py
#   python3 patch_teto_fila.py --aplicar

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ALVO = "telegram_repurpose_hunter.py"

RE_ASSINATURA = re.compile(r"(max_itens\s*:\s*int\s*=\s*)(\d+)")
RE_CORTE = re.compile(r"^([ \t]*)fila = fila\[:max_itens\][ \t]*\r?$", re.MULTILINE)

CORTE_NOVO = (
    "\\1_teto = max_itens or int(os.environ.get(\"FILA_ACERVO_MAX\", \"500\"))\n"
    "\\1if _teto > 0:\n"
    "\\1    fila = fila[:_teto]")

# a 1a versão deste patcher escreveu ESTE trecho; ele precisa convergir pro de
# cima, senão quem já rodou fica com o acervo ilimitado pra sempre
RE_CORTE_V1 = re.compile(
    r"^([ \t]*)if max_itens and max_itens > 0:.*\r?\n[ \t]*fila = fila\[:max_itens\][ \t]*\r?$",
    re.MULTILINE)


def _log(m):
    print(f"[teto] {m}", flush=True)


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
    """Todas as cópias no disco, não só a que eu acho que é a certa."""
    achadas = []
    for p in RAIZ.rglob(ALVO):
        if ".venv" not in p.parts and "__pycache__" not in p.parts:
            achadas.append(p)
    return sorted(achadas)


def _qual_python_importa():
    """Qual cópia o `import` resolve DE VERDADE. É a que manda em produção —
    e descobrir isso lendo o código dá errado quando há fallback."""
    codigo = ("import sys; sys.path.insert(0, '.');\n"
              "try:\n"
              "    from integrations import telegram_repurpose_hunter as H\n"
              "except Exception:\n"
              "    import telegram_repurpose_hunter as H\n"
              "print(H.__file__)")
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True,
                       text=True, cwd=str(RAIZ), timeout=120)
    if r.returncode == 0 and r.stdout.strip():
        return Path(r.stdout.strip())
    return None


def _patchar(texto: str):
    """(novo_texto, [o que mudou]) — sem escrever nada."""
    mudancas = []

    def _troca_assinatura(m):
        if m.group(2) == "0":
            return m.group(0)
        mudancas.append(f"default do gravador: {m.group(2)} → 0 "
                        f"(0 = usa FILA_ACERVO_MAX)")
        return m.group(1) + "0"

    novo = RE_ASSINATURA.sub(_troca_assinatura, texto)

    if "FILA_ACERVO_MAX" not in novo:
        # v1 deste patcher (acervo ilimitado) → converge pro teto grande
        novo, n = RE_CORTE_V1.subn(CORTE_NOVO, novo)
        if n:
            mudancas.append(f"acervo ILIMITADO → teto FILA_ACERVO_MAX ({n})")
        else:
            novo, n = RE_CORTE.subn(CORTE_NOVO, novo)
            if n:
                mudancas.append(f"corte da fila em FILA_ACERVO_MAX ({n})")
    return novo, mudancas


def main():
    p = argparse.ArgumentParser(
        description="Troca o teto de 80 do acervo por FILA_ACERVO_MAX, "
                    "por substituição exata de texto.")
    p.add_argument("--aplicar", action="store_true",
                   help="escreve (o padrão é só mostrar)")
    args = p.parse_args()

    copias = _copias()
    if not copias:
        _log(f"não achei nenhum {ALVO} debaixo de {RAIZ}")
        return 1

    vivo = _qual_python_importa()
    _log(f"{len(copias)} cópia(s) no disco:")
    for c in copias:
        marca = "  ← é ESTA que o import resolve" if (
            vivo and c.resolve() == vivo.resolve()) else ""
        _log(f"   {c.relative_to(RAIZ)}{marca}")
    if vivo is None:
        _log("⚠️  não consegui resolver o import — sigo mesmo assim, porque "
             "vou mexer em TODAS as cópias")
    print()

    falhou = 0
    for c in copias:
        try:
            texto = _ler(c)
        except Exception as e:
            _log(f"✗ {c.name}: não consegui ler — {str(e)[:70]}")
            falhou += 1
            continue

        novo, mudancas = _patchar(texto)
        novo = _no_estilo_do_arquivo(novo, texto)
        if not mudancas:
            _log(f"·  {c.relative_to(RAIZ)}: já está no formato novo "
                 f"(nada a fazer)")
            continue

        _log(f"→  {c.relative_to(RAIZ)}")
        for m in mudancas:
            _log(f"     {m}")
        if not args.aplicar:
            _log("     (seco: não escrevi. use --aplicar)")
            continue

        bak = c.with_suffix(c.suffix + ".bak_teto")
        shutil.copy2(c, bak)
        _escrever(c, novo)
        r = subprocess.run([sys.executable, "-m", "py_compile", str(c)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            shutil.copy2(bak, c)
            _log(f"     ✗ NÃO COMPILA — restaurei o backup. "
                 f"{(r.stderr or '')[:150]}")
            falhou += 1
            continue
        _log(f"     ✅ escrito (backup em {bak.name})")

    print()
    if not args.aplicar:
        _log("nada foi escrito. Rode de novo com --aplicar.")
        return 0
    _log("pronto." if not falhou else f"{falhou} cópia(s) com problema.")
    _log("O efeito aparece na PRÓXIMA gravação da mineração: o acervo passa "
         "a acumular até FILA_ACERVO_MAX (500) em vez de 80.")
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
