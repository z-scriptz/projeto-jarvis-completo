#!/usr/bin/env python3
# patch_legenda_ramos.py -- legenda de espaço em branco para de virar post mudo.
#
# POR QUE EXISTE (17/08)
# O `_legenda_instagram` do `agents/publish_guard.py` escolhe a legenda entre
# três ramos, e os dois primeiros não passam por nenhuma validação:
#
#     1. descricoes.instagram      → devolvido SEM .strip(), sem validação
#     2. publish_pack.legenda_ig   → devolvido SEM .strip(), sem validação
#     3. plano.legenda             → .strip(), e é o ÚNICO que o guarda exige
#                                    preenchido antes de publicar
#
# ⚠️ E O DEFEITO NÃO É "FALTA UM .strip()" — É A CONDIÇÃO. `if
# descs.get("instagram")` é TRUE pra `"   \n  "`, porque string de espaço é
# truthy em Python. Então uma legenda que na prática está vazia:
#   • dispara o ramo 1,
#   • é devolvida como está,
#   • **nunca chega no ramo 3**, que é o único que o guarda valida,
#   • e o Reel sai sem legenda, com o sistema reportando sucesso.
#
# Foi por isso que medimos "336/336 pacotes com legenda" e mesmo assim houve
# post sem. A contagem olhava a existência do campo; o publicador olhava a
# verdade dele — e os dois discordavam em silêncio.
#
# ⚠️ NÃO AFIRMO QUE ISTO CAUSOU OS 11 POSTS DA CASA. A causa daquele caso
# continua em aberto (o log da legenda foi instalado e o daemon só passou a
# rodar o código novo depois do restart de 17/08). Isto conserta um caminho
# REAL pelo qual um post pode sair mudo — não é o mesmo que ter provado que
# foi este. Trocar "é um mecanismo possível" por "achei a causa" é o erro que
# este projeto já pagou caro pra aprender a não cometer.
#
# O CONSERTO: cada ramo é limpo ANTES de ser testado, e um ramo em branco CAI
# PRO PRÓXIMO em vez de ser publicado. Ninguém passa sem texto de verdade.
#
# ⚠️ POR QUE PATCH E NÃO DEPLOY: o `publish_guard.py` deste repo é outra
# versão — não tem sequer a função. A viva só existe na VPS. Sobrescrever
# apagaria o publicador de produção.
#
# Idempotente. Seco por padrão. Se as âncoras não baterem, ele DIZ e não
# escreve — "não achei" é falha, não sucesso silencioso.
#
# Uso (na VPS, dentro de ~/jarvis):
#   python3 patch_legenda_ramos.py
#   python3 patch_legenda_ramos.py --aplicar
#   sudo systemctl restart jarvis.service    # ⚠️ sem isto o código novo NÃO roda

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ALVO = "publish_guard.py"
MARCA = "_ramo_limpo"          # idempotência

# ⚠️ REGEX E NÃO TEXTO EXATO, de propósito: eu não tenho o arquivo da VPS aqui,
# só a réplica que o `diag_pacotes.py` fez dele. Casar por estrutura (com
# espaçamento flexível e aspas de qualquer tipo) erra menos que apostar em
# bytes que eu não vi. E se mesmo assim não casar, o patcher recusa — o que é
# o comportamento certo: melhor não mexer do que mexer no lugar errado.
RE_RAMO1 = re.compile(
    r"""(?P<i>[ \t]*)if\s+descs\.get\(\s*["']instagram["']\s*\)\s*:\s*\r?\n"""
    r"""[ \t]*return\s+descs\[\s*["']instagram["']\s*\]\s*,\s*"""
    r"""(?P<r>["']descricoes\.instagram["'])""")

RE_RAMO2 = re.compile(
    r"""(?P<i>[ \t]*)if\s+pack\.get\(\s*["']legenda_instagram["']\s*\)\s*:\s*\r?\n"""
    r"""[ \t]*return\s+pack\[\s*["']legenda_instagram["']\s*\]\s*,\s*"""
    r"""(?P<r>["']publish_pack\.legenda_instagram["'])""")

NOVO1 = (
    "\\g<i>_t = _ramo_limpo(descs.get(\"instagram\"))\n"
    "\\g<i>if _t:\n"
    "\\g<i>    return _t, \\g<r>")

NOVO2 = (
    "\\g<i>_t = _ramo_limpo(pack.get(\"legenda_instagram\"))\n"
    "\\g<i>if _t:\n"
    "\\g<i>    return _t, \\g<r>")

# a função auxiliar entra logo antes do `def _legenda_instagram`
RE_DEF = re.compile(r"^(?P<i>[ \t]*)def\s+_legenda_instagram\s*\(", re.MULTILINE)

AUX = '''def _ramo_limpo(valor):
    """O texto do ramo, ou "" se ele nao tem conteudo de verdade.

    ⚠️ EXISTE POR CAUSA DA TRUTHINESS. `if descs.get("instagram")` era True
    pra "   \\n  " -- string de espaco e truthy em Python. O ramo disparava,
    devolvia espaco em branco, e o post saia sem legenda SEM nunca chegar no
    ramo 3, que e o unico que o guarda valida. Limpar antes de testar faz o
    ramo em branco CAIR PRO PROXIMO em vez de ser publicado.
    """
    return (valor or "").strip() if isinstance(valor, str) else ""


'''


def _log(m):
    print(f"[legenda-ramos] {m}", flush=True)


def _ler(p: Path) -> str:
    """Preserva as quebras de linha originais (CRLF→LF silencioso já me pegou
    em 15/08: reescreveu dois arquivos inteiros e virou DIVERGENTE no deploy)."""
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def _escrever(p: Path, texto: str):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(texto)


def _no_estilo(texto: str, original: str) -> str:
    if "\r\n" in original:
        return texto.replace("\r\n", "\n").replace("\n", "\r\n")
    return texto.replace("\r\n", "\n")


def main():
    p = argparse.ArgumentParser(
        description="Ramo de legenda em branco cai pro próximo, não publica.")
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

        if "_legenda_instagram" not in texto:
            _log(f"·  {c.relative_to(RAIZ)}: não tem `_legenda_instagram`, pulo")
            continue
        if MARCA in texto:
            _log(f"·  {c.relative_to(RAIZ)}: já tem os ramos limpos")
            continue

        n1 = len(RE_RAMO1.findall(texto))
        n2 = len(RE_RAMO2.findall(texto))
        nd = len(RE_DEF.findall(texto))
        if (n1, n2, nd) != (1, 1, 1):
            # ⚠️ não achar NÃO é sucesso: esta cópia segue podendo publicar
            # espaço em branco como legenda
            _log(f"⚠️  {c.relative_to(RAIZ)}: ramo1={n1} ramo2={n2} def={nd} "
                 f"(esperado 1/1/1) — NÃO mexo")
            _log(f"     veja como está escrito lá:")
            _log(f"     grep -n -A 12 'def _legenda_instagram' "
                 f"{c.relative_to(RAIZ)}")
            falhou += 1
            continue

        _log(f"→  {c.relative_to(RAIZ)}: limpo os 2 ramos + insiro `_ramo_limpo`")
        if not args.aplicar:
            _log("     (seco: não escrevi. use --aplicar)")
            continue

        bak = c.with_suffix(c.suffix + ".bak_legramos")
        shutil.copy2(c, bak)
        novo = RE_RAMO1.sub(NOVO1, texto, count=1)
        novo = RE_RAMO2.sub(NOVO2, novo, count=1)
        m = RE_DEF.search(novo)
        novo = novo[:m.start()] + AUX + novo[m.start():]
        _escrever(c, _no_estilo(novo, texto))

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
         + (f" · {falhou} não deu" if falhou else ""))
    if mexidos:
        _log("⚠️ AGORA REINICIE:  sudo systemctl restart jarvis.service")
        _log("   O daemon carregou o módulo antigo na memória quando subiu —")
        _log("   editar o .py no disco não muda o processo que já roda. Foi")
        _log("   exatamente isso que segurou o log da legenda por 2 dias.")
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
