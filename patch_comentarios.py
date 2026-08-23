#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# patch_comentarios.py - troca o 1o comentario fixo pelo banco do comentarios.py
#
# POR QUE (reclamacao do Dre, 22/08):
# "o primeiro comentario em todos os posts, reels, carrossel, e sempre o mesmo,
# todo mundo que acompanha enjoa de ver o mesmo comentario robotizado toda vez.
# Pra carrossel isso nem faz sentido."
#
# `_TMPL_IG` era UMA constante: a mesma frase em 6 contas, todo dia. E pior,
# ela pedia "corre pegar o seu" num carrossel de "3 erros que quase todo mundo
# comete" - um post que nao mostra produto nenhum. Comentario que ignora o post
# denuncia a automacao mais do que o repetido cansa.
#
# Este patch e ADITIVO+CIRURGICO como o do carrossel: substitui SO a funcao
# `_montar_comentario` e acrescenta `_formato_do_pacote`. Nada mais e tocado,
# porque `agents/meta_uploader.py` esta DIVERGENTE e --forcar apagaria uma
# edicao de producao que ninguem sabe qual e.
#
# IDEMPOTENTE. Faz backup, compila antes de gravar, e tem --desfazer.
#
# USO (na raiz do jarvis):
#   python3 patch_comentarios.py            # aplica
#   python3 patch_comentarios.py --conferir # so diz o que faria
#   python3 patch_comentarios.py --desfazer # volta o .bak

import sys
import shutil
import py_compile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CANDIDATOS = ["agents/meta_uploader.py", "meta_uploader.py",
              "integrations/meta_uploader.py"]

MARCA = "def _formato_do_pacote"
INICIO = "def _montar_comentario(plataforma: str, video_path) -> str:"
FIM = "def _comentar("

NOVA = r'''def _formato_do_pacote(caminho) -> str:
    """reel · lista · carrossel — deduzido da PASTA, sem mudar chamada nenhuma.

    O pacote de carrossel tem `plano.json` ao lado dos slides (o brain grava);
    o pacote de video nao tem. Entao a propria pasta responde que tipo de post
    e este, e as duas chamadas de `_montar_comentario` que ja existiam
    continuam iguais."""
    try:
        pj = Path(caminho).parent / "plano.json"
        if not pj.exists():
            return "reel"
        f = (json.loads(pj.read_text(encoding="utf-8")).get("formato") or "")
        return "lista" if f in ("lista", "comparacao") else "carrossel"
    except Exception:
        return "carrossel"


def _montar_comentario(plataforma: str, video_path) -> str:
    """O 1o comentario. Vem do `comentarios.py`, que varia a frase e sabe se o
    post e Reel, carrossel ou lista.

    ATENCAO: um template no .env (ENGAJAR_IG_TMPL / ENGAJAR_FB_TMPL) ainda
    manda, pra dar controle manual. Sem ele, o banco decide."""
    d = _dados_engajamento(video_path)
    ctx = {
        "link":    (d.get("link") or "").strip(),
        "handle":  (_CTX.get("handle") or d.get("handle") or "").strip(),
        "produto": (d.get("produto") or "").strip(),
    }
    fixo = (os.environ.get("ENGAJAR_IG_TMPL", "") if plataforma == "instagram"
            else os.environ.get("ENGAJAR_FB_TMPL", "")).strip()
    if fixo:
        if "{link}" in fixo and not ctx["link"]:
            return ""
        try:
            return fixo.format(**ctx).strip()
        except Exception:
            return ""
    try:
        from comentarios import escolher
    except Exception as e:
        log.warning(f"   comentarios.py indisponivel ({e}) - 1o comentario pulado")
        return ""
    return escolher(plataforma, _formato_do_pacote(video_path),
                    conta=ctx["handle"], link=ctx["link"],
                    produto=ctx["produto"], handle=ctx["handle"])
'''


def _alvo() -> Path:
    for c in CANDIDATOS:
        p = RAIZ / c
        if p.exists():
            return p
    print("[x] nao achei o meta_uploader.py")
    sys.exit(1)


def main() -> int:
    args = set(sys.argv[1:])
    alvo = _alvo()
    print(f"[alvo] {alvo}")
    bak = alvo.with_suffix(".py.bak-coment")

    if "--desfazer" in args:
        if not bak.exists():
            print(f"[x] nao existe {bak}")
            return 1
        shutil.copy2(bak, alvo)
        print(f"[<-] restaurado. Rode: systemctl restart jarvis.service")
        return 0

    texto = alvo.read_text(encoding="utf-8")
    if MARCA in texto:
        print("[ok] o banco de comentarios JA esta instalado - nada a fazer.")
        return 0

    i = texto.find(INICIO)
    if i < 0:
        print(f"[x] nao achei `{INICIO}` em {alvo}.")
        print("    O arquivo da VPS diverge mais do que eu esperava; me mande:")
        print(f"      grep -n '_montar_comentario' {alvo}")
        return 1
    j = texto.find(FIM, i)
    if j < 0:
        print(f"[x] achei o inicio mas nao o fim (`{FIM}`). Nao vou adivinhar.")
        return 1

    novo = texto[:i] + NOVA.strip() + "\n\n\n" + texto[j:]
    if "import json" not in novo.split("def ")[0]:
        print("[!] o arquivo nao importa json no topo - conferindo...")
    print(f"[pos] substituindo _montar_comentario ({j - i} caracteres)")

    if "--conferir" in args:
        print("\n[teste] nada foi gravado.")
        return 0

    temp = alvo.with_suffix(".py.novo")
    temp.write_text(novo, encoding="utf-8")
    try:
        py_compile.compile(str(temp), doraise=True)
    except py_compile.PyCompileError as e:
        temp.unlink()
        print(f"[x] nao compila - NADA foi alterado:\n{e}")
        return 1

    shutil.copy2(alvo, bak)
    temp.replace(alvo)
    print(f"[bak] {bak.name}")
    print(f"[ok] {alvo} patchado.")
    print("\n     Agora:  systemctl restart jarvis.service")
    print("     Teste:  .venv/bin/python comentarios.py --formato carrossel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
