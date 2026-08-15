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
#   max_itens: int = 80   →   max_itens: int = 0      (0 = acervo sem teto)
#   fila = fila[:max_itens]   →   só corta se max_itens > 0
#
# POR QUÊ: o gravador truncava a fila em 80 a cada gravação, e os dois
# chamadores usavam o default. Produto novo EXPULSAVA o mais antigo — medido
# na VPS em 15/08: 80/80, janela de 7 dias. O acervo virou janela deslizante e
# produto que saía dela sumia do site calado. O teto passa a viver no
# `deploy_site.py` (`VITRINE_MAX_PRODUTOS`), que é onde os custos reais estão:
# peso da página e chamada de API do health-check.
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
RE_CORTE = re.compile(r"^([ \t]*)fila = fila\[:max_itens\]\s*$", re.MULTILINE)

CORTE_NOVO = ("\\1if max_itens and max_itens > 0:      # 0 = acervo sem teto\n"
              "\\1    fila = fila[:max_itens]")


def _log(m):
    print(f"[teto] {m}", flush=True)


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
        mudancas.append(f"teto do gravador: {m.group(2)} → 0 (sem teto)")
        return m.group(1) + "0"

    novo = RE_ASSINATURA.sub(_troca_assinatura, texto)

    if "if max_itens and max_itens > 0:" not in novo:
        novo, n = RE_CORTE.subn(CORTE_NOVO, novo)
        if n:
            mudancas.append(f"corte da fila protegido ({n} ocorrência(s))")
    return novo, mudancas


def main():
    p = argparse.ArgumentParser(
        description="Tira o teto de 80 do acervo, por substituição exata.")
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
            texto = c.read_text(encoding="utf-8")
        except Exception as e:
            _log(f"✗ {c.name}: não consegui ler — {str(e)[:70]}")
            falhou += 1
            continue

        novo, mudancas = _patchar(texto)
        if not mudancas:
            _log(f"·  {c.relative_to(RAIZ)}: já está sem teto (nada a fazer)")
            continue

        _log(f"→  {c.relative_to(RAIZ)}")
        for m in mudancas:
            _log(f"     {m}")
        if not args.aplicar:
            _log("     (seco: não escrevi. use --aplicar)")
            continue

        bak = c.with_suffix(c.suffix + ".bak_teto")
        shutil.copy2(c, bak)
        c.write_text(novo, encoding="utf-8")
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
    _log("O efeito aparece na PRÓXIMA gravação da mineração: a fila para de "
         "ser truncada e volta a acumular.")
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
