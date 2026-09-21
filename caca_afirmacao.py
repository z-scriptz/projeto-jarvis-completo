#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""caca_afirmacao.py -- evidência que o verificador coleta e joga fora.

⚠️ POR QUE ISTO EXISTE. Em 21/09, duas vezes no mesmo dia, o mesmo defeito
apareceu em lugares diferentes:

    refund.amount_matches   o valor era lido da Stripe e NUNCA comparado
    id_lido / id_esperado   o Graph devolvia os dois e ninguém os confrontava

Os dois têm a mesma assinatura no código: **uma chave entra no dicionário de
observação e nenhum leitor existe.** O dado está na mão, custou uma chamada
de rede, e a decisão é tomada sem ele.

📌 É a forma mais barata de mentir que existe num verificador, porque parece
zelo: o payload fica rico, o recibo fica bonito, e a afirmação continua
apoiada em `bool(alguma_coisa)`.

    python3 caca_afirmacao.py                 # o escopo_jarvis
    python3 caca_afirmacao.py outro_arq.py    # qualquer um

⚠️ O QUE ELE NÃO ENCONTRA, e é importante dizer para ninguém ler silêncio
daqui como aprovação:

    · chave lida por `.get()` montado em runtime (`d.get(campo)`)
    · comparação feita com a régua errada — ler os dois e comparar mal
    · a família "não consegui olhar" virando "não está lá", que é outra
      caça, feita à mão, e que está anotada no ROADMAP de 21/09

Ou seja: **ele acha uma espécie de defeito, não "defeitos".** Um arquivo
limpo aqui não é um arquivo correto.
"""
import ast
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent


def chaves_devolvidas(fn: ast.FunctionDef) -> dict:
    """{chave: linha} de todo dict literal devolvido por esta função.

    Só dict LITERAL: `return {"a": 1}`. Um `return d` onde `d` foi montado
    aos poucos não dá para afirmar nada sobre as chaves sem simular o
    fluxo — e chutar aqui seria cometer o defeito que o script procura.
    """
    achadas = {}
    for no in ast.walk(fn):
        if not isinstance(no, ast.Return) or not isinstance(no.value, ast.Dict):
            continue
        for k in no.value.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                achadas.setdefault(k.value, no.lineno)
    return achadas


def usos_de_texto(caminhos) -> dict:
    """Quantas vezes cada string aparece como literal, fora de onde nasce.

    Varre .py como AST (pega só string de verdade, não comentário) e .yaml
    como texto, porque contrato consome chave de observação pelo `espera:`
    e isso conta como leitor legítimo.
    """
    contagem = {}

    def soma(s):
        contagem[s] = contagem.get(s, 0) + 1

    for p in caminhos:
        if p.suffix == ".py":
            try:
                arv = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            # 🔥 AS PRÓPRIAS DECLARAÇÕES NÃO CONTAM COMO LEITURA, e descobrir
            # isso custou um susto: ao escrever `registro_apenas = {"id_lido",
            # "id_esperado"}` a ferramenta parou de apontar as duas chaves — e
            # não foi o filtro que absolveu, foi o CONTADOR, que passou a ver
            # duas ocorrências da string e concluiu "alguém lê".
            #
            # ⚠️ É o defeito que esta ferramenta caça, dentro dela: menção
            # contada como leitura. A declaração teria virado um perdão
            # automático para qualquer chave, bastando escrever o nome.
            ignorar = set()
            for no in ast.walk(arv):
                if isinstance(no, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == "registro_apenas"
                        for t in no.targets):
                    ignorar.update(id(x) for x in ast.walk(no))
            for no in ast.walk(arv):
                if (isinstance(no, ast.Constant) and isinstance(no.value, str)
                        and id(no) not in ignorar):
                    soma(no.value)
        else:
            texto = p.read_text(encoding="utf-8", errors="replace")
            for linha in texto.splitlines():
                for pedaco in linha.replace(":", " ").split():
                    soma(pedaco.strip("\"'-"))
    return contagem


def registro_apenas(cls: ast.ClassDef) -> set:
    """As chaves que a classe DECLARA existirem só para o recibo.

    ⚠️ ISTO PRECISOU EXISTIR NO PRIMEIRO USO DA FERRAMENTA. Nem toda chave sem
    leitor é evidência jogada fora: `id_lido` e `id_esperado` entram na decisão
    por variável local e ficam no payload porque **quem audita o recibo quer
    ver os dois lados da comparação**. Isso é trilha, não desperdício.

    📌 E a saída é a regra da casa aplicada à própria ferramenta: silêncio
    continua suspeito, e só a DECLARAÇÃO absolve. Quem quer a chave no recibo
    escreve o nome dela aqui e assume; quem esqueceu de comparar não escreve
    nada e continua aparecendo na lista.
    """
    for no in cls.body:
        if not isinstance(no, ast.Assign):
            continue
        nomes = [t.id for t in no.targets if isinstance(t, ast.Name)]
        if "registro_apenas" not in nomes:
            continue
        if isinstance(no.value, (ast.Set, ast.List, ast.Tuple)):
            return {e.value for e in no.value.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return set()


def caçar(alvo: Path, universo) -> list:
    """[(classe, metodo, chave, linha)] das chaves sem nenhum leitor."""
    arv = ast.parse(alvo.read_text(encoding="utf-8"))
    usos = usos_de_texto(universo)
    mortas = []
    for cls in ast.walk(arv):
        if not isinstance(cls, ast.ClassDef):
            continue
        declaradas = registro_apenas(cls)
        for fn in cls.body:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if "consultar" not in fn.name and "observ" not in fn.name:
                continue
            for chave, linha in chaves_devolvidas(fn).items():
                if chave in declaradas:
                    continue        # assumida como trilha de auditoria
                # 1 uso = a própria construção. 2+ = alguém lê.
                if usos.get(chave, 0) <= 1:
                    mortas.append((cls.name, fn.name, chave, linha))
    return mortas


def principal(argv) -> int:
    alvo = Path(argv[1]) if len(argv) > 1 else BASE / "escopo_jarvis.py"
    if not alvo.exists():
        print(f"❌ não achei {alvo}")
        return 2

    universo = sorted(
        [p for p in BASE.rglob("*.py") if "__pycache__" not in str(p)]
        + [p for p in (BASE / "politicas").glob("*.yaml")])

    print(f"\n🔎 evidência morta em {alvo.name}")
    print(f"   procurando leitores em {len(universo)} arquivo(s)\n")

    mortas = caçar(alvo, universo)
    if not mortas:
        print("   ✅ toda chave devolvida tem ao menos um leitor.\n")
        print("   ⚠️ E isso NÃO quer dizer que as comparações estão certas —")
        print("      só que o dado não está sendo jogado fora. Ler os dois")
        print("      lados e comparar mal continua passando por aqui.\n")
        return 0

    print(f"   🔥 {len(mortas)} chave(s) que ninguém lê:\n")
    for cls, fn, chave, linha in mortas:
        print(f"   {alvo.name}:{linha}")
        print(f"      {cls}.{fn}()  →  {chave!r}")
        print(f"      custou uma consulta e não entra em decisão nenhuma\n")
    print("   📌 Para cada uma, a pergunta é uma só: se este campo não entra")
    print("      na decisão, ou a afirmação está apoiada em menos do que")
    print("      parece, ou o campo devia sair do payload.\n")
    return 1


if __name__ == "__main__":
    sys.exit(principal(sys.argv))
