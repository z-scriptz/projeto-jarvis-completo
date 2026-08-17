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
# ⚠️ A FORMA REAL, vista no arquivo da VPS em 17/08 — e diferente da que eu
# tinha suposto. A "RÉPLICA EXATA" do `diag_pacotes.py` devolvia `(texto, ramo)`;
# a função de verdade devolve só o texto. O nome do ramo era invenção do
# diagnóstico, pra poder contar qual disparava.
#
# ⚠️ A DECISÃO, PORÉM, É IDÊNTICA (`if X.get("k"): return X["k"]`, mesma ordem,
# mesmos campos) — então a medição de qual ramo dispara continua valendo. Errei
# a forma, não o comportamento. Registro os dois porque "minha réplica estava
# errada" e "minha conclusão estava errada" são coisas diferentes, e confundir
# as duas joga fora medição boa.
#
# UM PADRÃO SÓ, aplicado a cada (dicionário, chave) conhecido — o mesmo defeito
# aparece 3x: instagram em 2 ramos e facebook em 1. Regex genérico demais
# pegaria `if X.get(...): return X[...]` em qualquer outro lugar do arquivo,
# então a lista de chaves é fechada de propósito.
RAMOS = [("descs", "instagram"), ("pack", "legenda_instagram"),
         ("descs", "facebook")]


def _re_ramo(var: str, chave: str):
    return re.compile(
        r"""(?P<i>[ \t]*)if\s+%s\.get\(\s*["']%s["']\s*\)\s*:\s*\r?\n"""
        r"""[ \t]*return\s+%s\[\s*["']%s["']\s*\]""" % (var, chave, var, chave))


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

        achados = [(v, k, len(_re_ramo(v, k).findall(texto))) for v, k in RAMOS]
        nd = len(RE_DEF.findall(texto))
        # ⚠️ TOLERO RAMO AUSENTE, NÃO RAMO DUPLICADO. `_legenda_facebook` pode
        # não existir numa cópia, e exigir os 3 travaria o conserto dos outros
        # 2 por causa de um que nem está lá. Mas 2+ ocorrências do MESMO ramo
        # significa que eu não entendi o arquivo — aí não mexo.
        if nd != 1 or any(n > 1 for _v, _k, n in achados) or \
                sum(n for _v, _k, n in achados) == 0:
            _log(f"⚠️  {c.relative_to(RAIZ)}: def={nd} · "
                 + " · ".join(f"{k}={n}" for _v, k, n in achados)
                 + " — NÃO mexo")
            _log(f"     veja como está escrito lá:")
            _log(f"     grep -n -A 12 'def _legenda_instagram' "
                 f"{c.relative_to(RAIZ)}")
            falhou += 1
            continue

        quais = [k for _v, k, n in achados if n == 1]
        _log(f"→  {c.relative_to(RAIZ)}: limpo {len(quais)} ramo(s) "
             f"({', '.join(quais)}) + insiro `_ramo_limpo`")
        if not args.aplicar:
            _log("     (seco: não escrevi. use --aplicar)")
            continue

        bak = c.with_suffix(c.suffix + ".bak_legramos")
        shutil.copy2(c, bak)
        novo = texto
        for var, chave, n in achados:
            if n != 1:
                continue
            novo = _re_ramo(var, chave).sub(
                "\\g<i>_t = _ramo_limpo(%s.get(\"%s\"))\n"
                "\\g<i>if _t:\n"
                "\\g<i>    return _t" % (var, chave), novo, count=1)
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
