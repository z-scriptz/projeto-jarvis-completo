#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# diag_env.py -- o que o .env está fazendo com o código, linha por linha
#
# POR QUE ISTO EXISTE (10/09/2026)
# ────────────────────────────────
# Duas vezes no mesmo dia, uma linha velha do `.env` apagou trabalho novo:
#
#   1. `AUTO_RESP_DM_TMPL=Oiee! 😍 tá tudo aqui ó: {site} 💛 corre!`
#      substituía o banco INTEIRO da DM de plano B, matando os cinco convites
#      pro grupo do WhatsApp que tinham acabado de entrar.
#   2. antes disso, o `comentarios.py` anunciava override por `.env` e nunca
#      lia o arquivo — o oposto exato, e igualmente silencioso.
#
# ⚠️ E EU CONSERTEI OS DOIS COM DETECTOR ESPECÍFICO, o que não escala: o código
# lê **262 variáveis** e o `.env` do Dre tem ~100 linhas. Escrever uma checagem
# por variável é garantir que a próxima passe.
#
# ⚠️ O QUE TORNA ISTO PERIGOSO É A ASSIMETRIA DO SINTOMA: variável que sobrepõe
# um banco não dá erro, não some do log, não muda nada visível. O sistema segue
# rodando com a frase de julho enquanto o repositório tem a de setembro, e a
# única pista é alguém reparar num print do Instagram.
#
# TRÊS PERGUNTAS, e cada uma tem um conserto diferente:
#   ⚠️ SOMBRA    — a linha substitui um padrão versionado (banco, template)
#   🕳️ FANTASMA  — nenhum arquivo lê essa variável (linha morta: erro de digitação
#                  ou sobra de algo removido)
#   ✅ NORMAL    — configuração de verdade (chave, caminho, número)
#
#   .venv/bin/python diag_env.py            # audita o .env
#   .venv/bin/python diag_env.py --tudo     # inclui as normais
import argparse
import ast
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent


# ⚠️⚠️ ESTE RELATÓRIO É FEITO PRA SER COLADO NO CHAT, e o `.env` tem token da
# Meta, chave do Gemini, senha e cookie do TikTok. A primeira versão imprimiu
# `GEMINI_API_KEY=segredo_que_nao_pode_vazar` inteiro na tela — num diagnóstico
# cuja única razão de existir é ser copiado pra outra pessoa ler.
# A regra do projeto é explícita: *"nunca colar tokens/segredos no chat"*.
# Aqui ela vira código: por padrão o valor é MASCARADO, e só aparece quando é
# claramente frase (tem espaço, `{}` ou `|||`) e a chave não cheira a segredo.
_CHEIRO_SEGREDO = re.compile(
    r"KEY|TOKEN|SECRET|SENHA|PASS|COOKIE|AUTH|CRED|_ID$|WEBHOOK|DSN|CONVITE",
    re.I)


def _seguro(chave: str, valor: str) -> str:
    """O valor, ou uma máscara. Na dúvida, mascara."""
    if _CHEIRO_SEGREDO.search(chave or ""):
        return f"‹oculto· {len(valor)} chars›"
    parece_frase = " " in valor or "|||" in valor or "{" in valor
    if not parece_frase and len(valor) > 12:
        return f"‹oculto· {len(valor)} chars›"      # sem espaço e longo = token
    return valor[:58] + ("…" if len(valor) > 58 else "")


def _chaves_do_env(arq: Path) -> dict:
    """{CHAVE: (linha, valor)} — só as ATIVAS (comentada não faz nada)."""
    fora = {}
    if not arq.exists():
        return fora
    try:
        linhas = arq.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return fora
    for i, linha in enumerate(linhas, 1):
        s = linha.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        if s.lower().startswith("export "):
            s = s[7:]
        k, _, v = s.partition("=")
        k = k.strip()
        if k and re.fullmatch(r"[A-Z][A-Z0-9_]*", k):
            fora[k] = (i, v.strip().strip('"').strip("'"))
    return fora


def _lidas_pelo_codigo() -> dict:
    """{CHAVE: [(arquivo, tipo_do_padrao)]}.

    `tipo_do_padrao` é o que decide se a variável SOBREPÕE algo:
      · 'constante'  → o código cai num `_ALGO_DEFAULT` (banco versionado)
      · 'texto_longo'→ o padrão é uma frase (>40 chars), quase sempre template
      · 'simples'    → número, caminho, "0"/"1" — configuração normal
      · 'sem_padrao' → `os.environ["X"]`, obrigatória
    """
    achados = defaultdict(list)
    for p in sorted(BASE.glob("*.py")) + sorted(BASE.glob("*/*.py")):
        if p.name == Path(__file__).name:
            continue
        try:
            arv = ast.parse(p.read_text("utf-8", errors="ignore"))
        except Exception:
            continue
        # constantes de módulo, pra resolver o padrão pelo VALOR e não pelo nome
        consts = {}
        for n in arv.body:
            if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                    and isinstance(n.targets[0], ast.Name):
                try:
                    consts[n.targets[0].id] = ast.literal_eval(n.value)
                except Exception:
                    pass
        # ⚠️ O BANCO NÃO É O PADRÃO DO `get` — ELE VEM NA LINHA SEGUINTE.
        # O idioma deste projeto inteiro é:
        #     env = os.environ.get("X", "")
        #     bruto = env if env.strip() else _BANCO_DEFAULT
        # Minha 2ª versão olhava só o padrão do `get`, viu `""` e classificou o
        # `AUTO_RESP_DM_TMPL` como configuração normal — a variável que estava
        # apagando os convites do grupo. Duas versões, dois veredictos errados
        # sobre a MESMA linha, cada um por um motivo diferente.
        #
        # Então a pergunta passa a ser sobre a FUNÇÃO: ela lê variável de
        # ambiente E menciona alguma constante que é um banco de frases? Se sim,
        # essa variável pode trocar o banco. Heurística — por isso o relatório
        # diz QUAL constante, pra quem lê julgar.
        def _bancos_da_funcao(fn):
            nomes = set()
            for s in ast.walk(fn):
                if isinstance(s, ast.Name) and s.id in consts:
                    v = consts[s.id]
                    if isinstance(v, str) and ("|||" in v or len(v) > 40):
                        nomes.add(s.id)
            return nomes

        escopo = {}          # id(nó) -> set de bancos da função que o contém
        for fn in ast.walk(arv):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                bancos = _bancos_da_funcao(fn)
                if bancos:
                    for s in ast.walk(fn):
                        escopo[id(s)] = bancos

        for n in ast.walk(arv):
            chaves, tipo = [], None
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                    and n.func.attr in ("get", "getenv") and n.args:
                if "environ" not in ast.dump(n.func) and n.func.attr != "getenv":
                    continue
                # ⚠️ TODAS as strings do 1º argumento, não só `args[0].value`.
                # `os.environ.get("A" if x else "B", ...)` é um IfExp, e minha
                # primeira versão o ignorava inteiro — justamente o formato do
                # `AUTO_RESP_DM_TMPL`, a linha que causou o defeito de hoje.
                # O diagnóstico dizia "ninguém lê essa variável" sobre a
                # variável que estava apagando as frases novas.
                chaves = [s.value for s in ast.walk(n.args[0])
                          if isinstance(s, ast.Constant) and isinstance(s.value, str)]
                tipo = _tipo_do_padrao(n.args[1] if len(n.args) > 1 else None, consts)
                if tipo == "simples" and escopo.get(id(n)):
                    tipo = "constante:" + ",".join(sorted(escopo[id(n)])[:2])
            elif isinstance(n, ast.Subscript) and \
                    getattr(n.value, "attr", None) == "environ" and \
                    isinstance(n.slice, ast.Constant) and \
                    isinstance(n.slice.value, str):
                chaves, tipo = [n.slice.value], "sem_padrao"
            for chave in chaves:
                if re.fullmatch(r"[A-Z][A-Z0-9_]*", chave):
                    achados[chave].append((p.name, tipo))
    return achados


def _prefixos_dinamicos() -> list:
    """Prefixos de chaves montadas em tempo de execução: `f"CARR_PESO_{x}"`.

    ⚠️ SEM ISTO O RELATÓRIO MANDA APAGAR CONFIGURAÇÃO VIVA. Na primeira
    execução real ele listou 18 "linhas mortas" — e a maioria não era. O
    `CARR_PESO_COMPARACAO` é lido por `os.environ.get(f"CARR_PESO_{nome.upper()}")`
    e o AST não vê a chave montada.
    """
    pref = []
    for p in sorted(BASE.glob("*.py")) + sorted(BASE.glob("*/*.py")):
        try:
            arv = ast.parse(p.read_text("utf-8", errors="ignore"))
        except Exception:
            continue
        for n in ast.walk(arv):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("get", "getenv") and n.args):
                continue
            if "environ" not in ast.dump(n.func) and n.func.attr != "getenv":
                continue
            a0 = n.args[0]
            if isinstance(a0, ast.JoinedStr):
                # o pedaço literal do começo é o prefixo
                for v in a0.values:
                    if isinstance(v, ast.Constant) and isinstance(v.value, str) \
                            and len(v.value) >= 4:
                        pref.append((v.value, p.name))
                    break
    return pref


def _citada_em_algum_lugar(chave: str) -> str:
    """Onde a chave aparece como TEXTO, fora dos `.env`. "" se em lugar nenhum.

    ⚠️⚠️ ESTA FUNÇÃO É O QUE IMPEDE O RELATÓRIO DE CAUSAR ESTRAGO. Duas formas
    de leitura são invisíveis pro AST e as duas apareceram no primeiro uso real:
      · `os.environ.get(especifico)` com `especifico = "TIKTOK_COOKIES" if ...`
        — o Dre tinha ACABADO de configurar esses cookies;
      · `os.environ.get(conta["page_token_env"])`, com o NOME DA CHAVE vindo do
        `contas.json` — apagar essas quatro linhas derrubaria a postagem de
        quatro contas.
    Se o nome aparece em qualquer arquivo do projeto, a variável não está morta:
    está sendo lida por um caminho que o AST não alcança.
    """
    for padrao in ("*.py", "*/*.py", "*.json", "*/*.json", "*.txt", "*.sh"):
        for p in BASE.glob(padrao):
            # ⚠️ TESTE NÃO CONTA COMO USO. Uma variável citada só numa fixture
            # de teste continua morta em produção — e contá-la faria o relatório
            # dizer "está viva" sobre exatamente o que se quer limpar.
            if p.name.startswith("teste_") or p.suffix == ".env" \
                    or p.name.startswith(".env"):
                continue
            try:
                if chave in p.read_text("utf-8", errors="ignore"):
                    return p.name
            except Exception:
                continue
    return ""


def _tipo_do_padrao(no, consts: dict) -> str:
    """O padrão que a variável substitui é um BANCO ou um número?

    ⚠️ MINHA PRIMEIRA VERSÃO OLHAVA O NOME: qualquer padrão que fosse uma
    constante MAIÚSCULA virava "sombra". Isso marcou `MIN_VIEWS=5000` — que é
    configuração legítima, com padrão `int` — como se estivesse apagando um
    banco de frases. Alarme falso em diagnóstico é como pendência que não é
    pendência: ensina a ignorar a saída.
    Agora decide pelo VALOR: sobrepõe se o padrão for texto longo ou uma lista
    de frases (`|||`).
    """
    if no is None:
        return "simples"
    valor = None
    if isinstance(no, ast.Constant):
        valor = no.value
    elif isinstance(no, ast.Name):
        if no.id in consts:
            valor = consts[no.id]
        elif no.id.endswith("_DEFAULT") or "TMPL" in no.id.upper():
            return "constante"       # não resolvi, mas o nome é explícito
    if isinstance(valor, str) and ("|||" in valor or len(valor) > 40):
        return "texto_longo"
    return "simples"


def main() -> int:
    ap = argparse.ArgumentParser(description="Audita o .env contra o código")
    ap.add_argument("--tudo", action="store_true",
                    help="mostra também as variáveis normais")
    ap.add_argument("--env", default="", help="caminho do .env (padrão: ./.env)")
    a = ap.parse_args()

    arq = Path(a.env) if a.env else (BASE / ".env")
    import warnings
    warnings.simplefilter("ignore")      # SyntaxWarning de arquivos analisados
    env = _chaves_do_env(arq)
    lidas = _lidas_pelo_codigo()
    prefixos = _prefixos_dinamicos()

    print(f"\n{'='*72}\n  AUDITORIA DO .env — {arq}\n{'='*72}")
    if not env:
        print(f"\n❌ nenhuma variável ativa lida de {arq}")
        return 1
    print(f"\n  {len(env)} variável(is) ativa(s) no .env · "
          f"{len(lidas)} lida(s) pelo código\n")

    sombras, fantasmas, indiretas, normais = [], [], [], []
    for k, (linha, valor) in sorted(env.items(), key=lambda kv: kv[1][0]):
        usos = lidas.get(k)
        if not usos:
            # ⚠️ ANTES DE CHAMAR DE MORTA: a chave pode ser montada em tempo de
            # execução (f-string) ou vir de um JSON. Ver `_citada_em_algum_lugar`.
            _pref = next(((pf, a) for pf, a in prefixos if k.startswith(pf)), None)
            if _pref:
                indiretas.append((linha, k, f'montada como f"{_pref[0]}…"', _pref[1]))
            else:
                _onde = _citada_em_algum_lugar(k)
                if _onde:
                    indiretas.append((linha, k, "nome citado em", _onde))
                else:
                    fantasmas.append((linha, k, valor))
        elif (any(t and (t.startswith("constante") or t == "texto_longo")
                  for _, t in usos)
              # ⚠️ E O VALOR TEM QUE PARECER FRASE. Sem isto, a heurística de
              # escopo marcava GEMINI_API_KEY como sombra — porque as funções
              # que a leem também mencionam PROMPTs longos — e o relatório
              # mandava comentar a chave da API. Diagnóstico que sugere
              # quebrar a produção é pior que diagnóstico nenhum.
              and (" " in valor or "|||" in valor or "{" in valor)
              and not _CHEIRO_SEGREDO.search(k)):
            _b = {c for _, t in usos if t and t.startswith("constante:")
                  for c in t.split(":", 1)[1].split(",")}
            sombras.append((linha, k, valor, sorted({f for f, _ in usos}), _b))
        else:
            normais.append((linha, k, valor, sorted({f for f, _ in usos})))

    if sombras:
        print(f"⚠️  SOMBRA — {len(sombras)}: substituem um padrão VERSIONADO.")
        print("    O código tem um banco/template pronto e esta linha o troca.")
        print("    Comente a linha pra usar o que está no repositório.\n")
        for linha, k, valor, arqs, bancos in sombras:
            print(f"   linha {linha:>3}  {k}")
            print(f"             = {_seguro(k, valor)}")
            print(f"             lida por: {', '.join(arqs[:3])}")
            if bancos:
                print(f"             substitui: {', '.join(sorted(bancos)[:3])}")
    if indiretas:
        print(f"\n🔗 INDIRETA — {len(indiretas)}: lida por caminho que o AST não vê.")
        print("    Chave montada em f-string ou vinda de um JSON (contas.json).")
        print("    ⚠️ NÃO APAGUE: é configuração VIVA.\n")
        for linha, k, como, onde in indiretas:
            print(f"   linha {linha:>3}  {k:<30} {como} {onde}")
    if fantasmas:
        print(f"\n🕳️  FANTASMA — {len(fantasmas)}: o nome não aparece em NENHUM arquivo.")
        print("    Linha morta: erro de digitação, ou sobra de algo removido.")
        print("    ⚠️ Não faz mal — mas quem lê o .env acha que está configurado.\n")
        for linha, k, valor in fantasmas:
            print(f"   linha {linha:>3}  {k} = {_seguro(k, valor)}")
    if a.tudo and normais:
        print(f"\n✅ NORMAIS — {len(normais)}:\n")
        for linha, k, valor, arqs in normais:
            # ⚠️ NÃO IMPRIME O VALOR: o .env tem token, senha e cookie. Um
            # diagnóstico que despeja segredo no terminal é um diagnóstico que
            # ninguém pode colar num chat — e colar no chat é o que se faz com
            # saída de diagnóstico.
            print(f"   linha {linha:>3}  {k:<28} ({len(arqs)} arquivo(s))")

    print(f"\n{'='*72}")
    print(f"  ⚠️ {len(sombras)} sombra(s) · 🔗 {len(indiretas)} indireta(s) · "
          f"🕳️ {len(fantasmas)} fantasma(s) · ✅ {len(normais)} normal(is)")
    if sombras:
        print(f"\n  As sombras são as que apagam trabalho novo sem dar sinal.")
        print(f"  Comente estas linhas do .env:")
        for linha, k, *_ in sombras:
            print(f"     sed -i '{linha}s/^/# /' {arq}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
