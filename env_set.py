#!/usr/bin/env python3
# env_set.py -- mexer no .env sem criar duplicata (e sem imprimir segredo).
#
# POR QUE EXISTE (18/08)
# Eu passei a sessão inteira recomendando `echo 'CHAVE=valor' >> .env`. Está
# ERRADO, e o dia provou: o Dre rodou
#
#     echo 'WHATSAPP_ATIVO=1' >> .env
#     .venv/bin/python whatsapp_playwright.py --quantos 1
#     → "⚪ WHATSAPP_ATIVO desligado"
#
# porque TODOS os carregadores do projeto param na PRIMEIRA ocorrência:
#
#     if chave and chave not in os.environ:      # whatsapp_playwright:174
#         os.environ[chave] = valor              # (idem hook_alana, validar_fila…)
#
# Uma vez lida a chave, as linhas seguintes com o mesmo nome são ignoradas.
# Então `>>` só funciona quando a chave AINDA NÃO EXISTE — e ninguém confere
# isso antes. O resultado é o pior tipo de falha: o comando "dá certo", o
# arquivo muda, e o comportamento não. Foi assim que o `WHATSAPP_ATIVO=1`
# ficou no arquivo com o script dizendo que estava desligado.
#
# ⚠️ NUNCA IMPRIME VALOR. Só o nome da chave e o que foi feito. Isto roda em
# terminal cujo histórico fica salvo, e a metade das chaves aqui é credencial.
#
# Uso (na VPS, dentro de ~/jarvis):
#   python3 env_set.py WHATSAPP_ATIVO 1
#   python3 env_set.py IG_PROXY 'http://user:senha@host:porta'
#   python3 env_set.py --remover COLETA_PODA_AUTO
#   python3 env_set.py --ver                 # lista chaves e duplicatas

import argparse
import shutil
import sys
from pathlib import Path

ENV = Path(__file__).resolve().parent / ".env"


def _log(m):
    print(f"[env] {m}", flush=True)


def _linhas():
    if not ENV.exists():
        return []
    return ENV.read_text(encoding="utf-8").splitlines()


def _chave_da(linha: str) -> str:
    l = linha.strip()
    if not l or l.startswith("#") or "=" not in l:
        return ""
    if l.lower().startswith("export "):
        l = l[7:]
    return l.partition("=")[0].strip()


def _ocorrencias(linhas, chave):
    return [i for i, l in enumerate(linhas) if _chave_da(l) == chave]


def main():
    p = argparse.ArgumentParser(
        description="Define/remove chave no .env sem duplicar. Nunca imprime valor.")
    p.add_argument("chave", nargs="?", help="nome da variável")
    p.add_argument("valor", nargs="?", help="valor (não é impresso)")
    p.add_argument("--remover", action="store_true",
                   help="comenta a chave em vez de definir")
    p.add_argument("--ver", action="store_true",
                   help="lista as chaves e aponta duplicatas")
    args = p.parse_args()

    if not ENV.exists():
        _log(f"não achei {ENV} — está rodando de dentro de ~/jarvis?")
        return 1

    linhas = _linhas()

    if args.ver:
        vistas, dup = [], []
        for l in linhas:
            k = _chave_da(l)
            if not k:
                continue
            (dup if k in vistas else vistas).append(k)
        _log(f"{len(vistas)} chave(s) ativa(s)")
        if dup:
            # ⚠️ duplicata NÃO é cosmética: a 1ª vence e as outras são letra
            # morta. Quem edita a última acha que mudou e não mudou.
            _log(f"⚠️  {len(set(dup))} chave(s) DUPLICADA(s) — só a 1ª vale, "
                 f"as demais são ignoradas pelos carregadores:")
            for k in sorted(set(dup)):
                onde = [i + 1 for i in _ocorrencias(linhas, k)]
                _log(f"     {k}  nas linhas {onde}  (vale a {onde[0]})")
        else:
            _log("nenhuma duplicata.")
        return 1 if dup else 0

    if not args.chave:
        p.error("informe a chave (ou use --ver)")
    if not args.remover and args.valor is None:
        p.error("informe o valor, ou use --remover")

    onde = _ocorrencias(linhas, args.chave)
    shutil.copy2(ENV, ENV.with_suffix(".env.bak_envset"))

    if args.remover:
        if not onde:
            _log(f"{args.chave} não está no .env — nada a remover")
            return 0
        for i in onde:
            linhas[i] = f"# {linhas[i].strip()}   # removido por env_set"
        ENV.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        _log(f"✅ {args.chave} comentada em {len(onde)} linha(s) "
             f"(comentei, não apaguei — reversível)")
        return 0

    nova = f"{args.chave}={args.valor}"
    if not onde:
        linhas.append(nova)
        acao = "acrescentada no fim"
    else:
        # ⚠️ escreve na PRIMEIRA ocorrência, que é a que os carregadores leem.
        # Escrever na última manteria a antiga valendo — exatamente o bug que
        # este arquivo existe pra impedir.
        linhas[onde[0]] = nova
        for i in onde[1:]:
            linhas[i] = f"# {linhas[i].strip()}   # duplicata, env_set comentou"
        acao = (f"substituída na linha {onde[0] + 1}"
                + (f" · {len(onde) - 1} duplicata(s) comentada(s)"
                   if len(onde) > 1 else ""))

    ENV.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    _log(f"✅ {args.chave} {acao}")
    _log("   (valor não impresso de propósito)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
