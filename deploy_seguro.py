#!/usr/bin/env python3
# deploy_seguro.py -- deployar sem regredir a VPS em um mês.
#
# POR QUE EXISTE (12/08)
# A semana inteira eu deployei assim:
#
#     git show FETCH_HEAD:arquivo.py > destino.py
#
# Isso é seguro SÓ para os arquivos em que este repo é a fonte da verdade — os
# que escrevemos aqui. O `conferir.py` mostrou que 83 dos 179 arquivos são
# ESPELHO PARADO: têm um commit só, do "Add files via upload" de 01/07, e o
# desenvolvimento real deles seguiu no outro repositório. Para esses, o mesmo
# comando **sobrescreve a VPS com código de um mês atrás**.
#
# Nada me impedia de errar isso. Só a atenção — e atenção não é mecanismo.
# O ChatGPT resumiu: *"vocês chegaram no ponto em que o gerenciamento do Jarvis
# virou um problema de engenharia"*. Esta é a trava.
#
# O QUE ELE FAZ, E O QUE ELE RECUSA
# ─────────────────────────────────
#   IGUAL           nada a fazer, e diz isso
#   ATRASADO        ✅ deploya — a VPS está num commit ANTIGO deste mesmo
#                   repo, então subir é seguir a linha, não pular pra outra
#   DIVERGENTE      ⛔ recusa; só com --forcar, e depois de mostrar o diff
#   ESPELHO PARADO  ⛔ recusa SEMPRE, nem com --forcar
#   COLISÃO         ⛔ recusa: dois módulos diferentes com o mesmo nome
#
# ⚠️ ESPELHO PARADO não tem escape de propósito. Um `--forcar` que libere tudo
# é um `--forcar` que alguém usa às 2 da manhã pra "resolver rápido", e aí a
# trava não serve pra nada. Se for MESMO necessário, o caminho é fazer o commit
# no repo certo primeiro — que é justamente o processo que falta.
#
# Antes de escrever: backup .bak, e depois py_compile. Falhou a compilação, ele
# RESTAURA sozinho — deploy que quebra o import derruba o daemon inteiro.
#
# Uso (na VPS, dentro de ~/jarvis):
#   python3 deploy_seguro.py render.py piloto.py
#   python3 deploy_seguro.py --ref FETCH_HEAD --tudo-que-mudou
#   python3 deploy_seguro.py contas.json --forcar     # divergente, ciente

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# grupos que NUNCA sobem, nem com --forcar
PROIBIDOS = {"ESPELHO PARADO", "COLISÃO"}
# grupos que exigem --forcar
COM_RESSALVA = {"DIVERGENTE"}


def _log(m):
    print(f"[deploy] {m}", flush=True)


def _conferir():
    """O próprio conferir.py, importado. NÃO reimplementar a classificação:
    duas ideias do que é 'espelho parado' é o mesmo que nenhuma."""
    sys.path.insert(0, str(RAIZ))
    try:
        import conferir
        return conferir
    except Exception as e:
        raise SystemExit(f"[deploy] não consegui importar conferir.py: {e}\n"
                         "        sem ele não há classificação, e sem "
                         "classificação isto vira o `git show` de sempre.")


def _sh(cmd, entrada=None):
    r = subprocess.run(cmd, capture_output=True, cwd=str(RAIZ),
                       input=entrada)
    return r.returncode, r.stdout, r.stderr


def situacao(C, nome: str, ref: str):
    """(estado, detalhe, destino_na_vps, bytes_do_ref) para um arquivo."""
    cod, dados, err = _sh(["git", "show", f"{ref}:{nome}"])
    if cod != 0:
        return "AUSENTE NO REF", err.decode()[:80], None, None

    destinos = C.copias_na_vps(nome, "")
    if not destinos:
        return "NÃO EXISTE NA VPS", "arquivo novo", RAIZ / nome, dados
    if len(destinos) > 1:
        return ("COLISÃO",
                " · ".join(str(d) for d in destinos), destinos[0], dados)

    destino = destinos[0]
    sha_vps = C.sha_de_blob(destino.read_bytes())
    sha_ref = C.sha_de_blob(dados)
    est, det = C.classificar(sha_vps, sha_ref, ref, nome)
    return est, det, destino, dados


def deployar(nome: str, ref: str, forcar: bool, seco: bool) -> bool:
    C = _conferir()
    est, det, destino, dados = situacao(C, nome, ref)

    if est == "IGUAL":
        _log(f"·  {nome}: já está em dia")
        return True
    if est == "AUSENTE NO REF":
        _log(f"✗  {nome}: não existe em {ref} — {det}")
        return False

    if est in PROIBIDOS:
        _log(f"⛔ {nome}: {est}")
        _log(f"   {det}")
        _log("   RECUSADO — e nem --forcar libera. Subir isto regride a VPS. "
             "O caminho é commitar no repositório certo primeiro.")
        return False

    if est in COM_RESSALVA and not forcar:
        _log(f"⛔ {nome}: {est}")
        _log(f"   {det}")
        _log(f"   RECUSADO. Compare antes:  git diff <(git show {ref}:{nome}) "
             f"{destino}")
        _log("   Se a versão do repo for mesmo a certa: --forcar")
        return False

    marca = "⚠️ " if est in COM_RESSALVA else "→ "
    _log(f"{marca}{nome}  [{est}]  →  {destino}")
    if det:
        _log(f"   {det}")
    if seco:
        _log("   (--seco: não escrevi nada)")
        return True

    bak = None
    if destino.exists():
        bak = destino.with_suffix(destino.suffix + ".bak")
        shutil.copy2(destino, bak)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(dados)

    # py_compile DEPOIS de escrever e restaura se quebrar: import quebrado num
    # módulo que o daemon carrega derruba o ciclo inteiro, e o erro aparece
    # longe daqui — no próximo slot de postagem.
    if destino.suffix == ".py":
        cod, _, err = _sh([sys.executable, "-m", "py_compile", str(destino)])
        if cod != 0:
            if bak:
                shutil.copy2(bak, destino)
                _log(f"   ✗ NÃO COMPILA — restaurei o backup. {err.decode()[:160]}")
            else:
                destino.unlink(missing_ok=True)
                _log(f"   ✗ NÃO COMPILA — removi o arquivo novo. "
                     f"{err.decode()[:160]}")
            return False
    _log(f"   ✅ escrito" + (f" (backup em {bak.name})" if bak else ""))
    return True


def main():
    p = argparse.ArgumentParser(
        description="Deploy que recusa o que regride a VPS.")
    p.add_argument("arquivos", nargs="*", help="nomes como no repo")
    p.add_argument("--ref", default="FETCH_HEAD")
    p.add_argument("--forcar", action="store_true",
                   help="libera DIVERGENTE (nunca ESPELHO PARADO)")
    p.add_argument("--seco", action="store_true",
                   help="mostra o que faria, sem escrever")
    args = p.parse_args()
    if not args.arquivos:
        p.error("diga quais arquivos (ex: render.py piloto.py)")

    print()
    ok = sum(deployar(a, args.ref, args.forcar, args.seco)
             for a in args.arquivos)
    print()
    _log(f"{ok}/{len(args.arquivos)} arquivo(s) ok")
    return 0 if ok == len(args.arquivos) else 1


if __name__ == "__main__":
    sys.exit(main())
