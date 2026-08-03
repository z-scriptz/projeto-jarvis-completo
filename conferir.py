#!/usr/bin/env python3
# conferir.py
# CONFERIDOR — diz o que está rodando na VPS, arquivo por arquivo.
#
# POR QUE ISSO EXISTE: em 03/08 eu afirmei que só uma correção estava pendente.
# O commit b435f3c estava parado havia um dia, e o extrator de termos que ele
# traz — o que conserta "2 mil vendidos" virar nome de produto — nunca tinha
# rodado. Eu não tinha como saber: sem leitura do que está instalado, o que eu
# "sei" é o que commitei, não o que roda.
#
# ELE NÃO ESCREVE NADA. Nenhum arquivo é criado, alterado ou apagado. O único
# comando de rede é um `git fetch pjc`, que mexe só em .git/ e nunca na árvore
# de trabalho. Pode rodar com o daemon no ar, a qualquer hora.
#
# O TRUQUE: o hash de um blob no git é o conteúdo, não a data. Então dá pra
# pegar um arquivo da VPS, calcular o hash dele e procurar esse hash no
# histórico do repositório — se casar com um commit antigo, o arquivo está
# ATRASADO e eu sei exatamente de quanto.
#
# O QUE A PRIMEIRA RODADA ENSINOU: 94 arquivos deram "não bate com nenhum
# commit", o que eu tinha rotulado de "editado na VPS". Estava errado. 132 dos
# 179 arquivos daqui têm UM commit só, de 01/07 — o "Add files via upload".
# O desenvolvimento de verdade seguiu no `agenteia` (o `origin` da VPS) e este
# espelho ficou parado. Por isso "não bate" se divide em dois:
#
#   ESPELHO PARADO  o repo tem 1 commit deste arquivo. Ele não é a fonte da
#                   verdade aqui — deployar REGRIDE a VPS em um mês.
#   DIVERGENTE      o repo acompanha o arquivo (vários commits) e mesmo assim
#                   não bate. Aí sim alguém editou de um lado só.
#
# Só ATRASADO é seguro pra deployar: a VPS está numa versão ANTIGA DESTE MESMO
# repositório, então subir é seguir a linha, não pular pra outra.
#
# AS DUAS ÁRVORES: este repositório é chapado (tudo na raiz) e a VPS é em
# pacotes (agents/, creative_engine/, integrations/...). O caminho real está no
# comentário da primeira linha de 85 dos 141 arquivos. Pros outros 56 o
# cabeçalho não existe — e "sem cabeçalho" NÃO quer dizer raiz: agendador_agent,
# production_runner_agent e youtube_uploader moram em agents/. Por isso o mapa
# tem três camadas, nesta ordem: cabeçalho, busca no disco, raiz.
#
# Uso:
#     cd ~/jarvis
#     python3 conferir.py                 # só código de produção
#     python3 conferir.py --tudo          # inclui patch_*/probe_*/diag_*
#     python3 conferir.py --ref pjc/main  # compara contra outro ramo
#     python3 conferir.py --sem-buscar    # não faz fetch (offline)

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

REMOTE = "pjc"
REF_PADRAO = f"{REMOTE}/claude/opa-clau-dgs591"

# Não são código que roda na VPS — comparar só geraria ruído.
IGNORAR = {"README.md", "ROADMAP.md", "DEPLOY.md", ".gitignore", "conferir.py",
           # 10 pacotes têm __init__.py e o espelho chapado guarda UM. Comparar
           # o único contra os dez não responde nada.
           "__init__.py"}
IGNORAR_PREFIXO = (".github/",)

# Mapa vindo do ROADMAP.md ("Referência rápida (infra)"). É a fonte
# autoritativa: foi escrito depois de a postagem balanceada ficar dias travada
# porque editávamos daemon_maestro.py na raiz enquanto o serviço rodava
# agents/daemon_maestro.py. O cabeçalho do arquivo e a busca no disco vêm
# depois disto, não antes.
MAPA_DOC = {
    "daemon_maestro.py":            "agents/daemon_maestro.py",
    "narrated_video_agent.py":      "agents/narrated_video_agent.py",
    "memory_agent.py":              "agents/memory_agent.py",
    "telegram_repurpose_hunter.py": "integrations/telegram_repurpose_hunter.py",
    "shopee_affiliate.py":          "integrations/shopee_affiliate.py",
}

# Também do ROADMAP: os que rodam DIRETO e por isso vivem na raiz. Serve pra
# não deixar a busca no disco puxar um homônimo de dentro de um pacote.
SO_NA_RAIZ = {"ceo_agent.py", "produzir_tiktok.py", "tiktok_coletor.py",
              "descoberta_fontes.py", "jarvis_status.py", "hook_alana.py",
              "ig_playwright.py", "tiktok_poster.py", "tiktok_painel.py",
              "roteador_contas.py", "metricas_agent.py", "posts_ledger.py"}

# Ferramenta avulsa: script de uma vez só, rodado à mão e esquecido. Fica fora
# por padrão porque a pergunta que importa é sobre o que o daemon executa.
AVULSO = re.compile(r"^(patch_|probe_|diag_|teste_|preview_|aplicar_|instalar_)")

# Onde procurar cópias. Fora daqui não vale a pena varrer (venv tem milhares de
# arquivos e nenhum deles é nosso).
PASTAS_BUSCA = ("agents", "creative_engine", "integrations", "shared", "memory",
                "brain", "analytics", "automation", "executor", "providers",
                "workflows", "tools")


def git(*args, entrada=None, checar=True):
    """Roda git e devolve stdout. entrada= manda texto pro stdin."""
    r = subprocess.run(["git"] + list(args), capture_output=True,
                       input=entrada.encode() if entrada else None)
    if checar and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: "
                           f"{r.stderr.decode(errors='replace').strip()[:200]}")
    return r.stdout.decode(errors="replace")


def sha_de_blob(dados: bytes) -> str:
    """O hash que o git daria a este conteúdo.

    Calculado aqui em vez de chamar `git hash-object` de propósito: aquele
    aplica os filtros configurados (CRLF, clean/smudge) e o resultado passaria
    a depender do .gitattributes de cada lado. Este é só o conteúdo.
    """
    return hashlib.sha1(b"blob %d\0" % len(dados) + dados).hexdigest()


def cabecalho_de_caminho(dados: bytes) -> str:
    """O caminho real declarado no comentário das primeiras linhas.

    Ex.: '# agents/validar_fila.py' -> 'agents/validar_fila.py'. Só aceito se o
    nome do arquivo bater com o do comentário; um comentário citando OUTRO
    arquivo (acontece em cabeçalho que explica o fluxo) não é declaração de
    caminho e me mandaria pro lugar errado.
    """
    try:
        texto = dados[:1200].decode("utf-8", errors="replace")
    except Exception:
        return ""
    for linha in texto.splitlines()[:6]:
        m = re.match(r"^#\s*([\w./-]+\.py)\s*$", linha.strip())
        if m:
            return m.group(1)
    return ""


def copias_na_vps(nome_repo: str, declarado: str) -> list:
    """Todos os lugares onde este arquivo existe na VPS, mais provável primeiro.

    Devolve lista porque a VPS TEM duplicata divergente: daemon_maestro.py
    existe na raiz (44 KB, morto) e em agents/ (58 KB, o que o daemon importa).
    Esconder isso escolhendo uma é como a gente edita a errada.
    """
    base = Path(nome_repo).name
    achados, vistos = [], set()

    def junta(p: Path):
        if p.exists() and p.is_file() and str(p) not in vistos:
            vistos.add(str(p))
            achados.append(p)

    if base in MAPA_DOC:
        junta(Path(MAPA_DOC[base]))
    elif base in SO_NA_RAIZ:
        junta(Path(base))
    if declarado:
        junta(Path(declarado))
    for pasta in PASTAS_BUSCA:
        junta(Path(pasta) / base)
    junta(Path(base))
    return achados


def historico_do_caminho(ref: str, caminho: str, limite: int = 60) -> list:
    """[(commit, sha_do_blob, assunto)] — do mais novo pro mais velho.

    Uma chamada de git log e uma de cat-file --batch-check pro arquivo inteiro,
    em vez de um rev-parse por commit. Só é chamada pra arquivo que JÁ sabemos
    que difere, então o custo fica no punhado que interessa.
    """
    saida = git("log", f"-{limite}", "--format=%H%x09%s", ref, "--", caminho,
                checar=False)
    commits = []
    for linha in saida.splitlines():
        if "\t" in linha:
            h, _, assunto = linha.partition("\t")
            commits.append((h, assunto))
    if not commits:
        return []
    consulta = "\n".join(f"{h}:{caminho}" for h, _ in commits) + "\n"
    resp = git("cat-file", "--batch-check", entrada=consulta, checar=False)
    linhas = resp.splitlines()
    fora = []
    for (h, assunto), info in zip(commits, linhas):
        partes = info.split()
        if len(partes) >= 2 and partes[1] == "blob":
            fora.append((h, partes[0], assunto))
    return fora


def classificar(sha_vps: str, sha_ref: str, ref: str, caminho_repo: str) -> tuple:
    """(situação, detalhe).

    A distinção que importa é entre ESPELHO PARADO e DIVERGENTE, e ela custou
    caro pra aparecer: 94 arquivos deram "não bate com nenhum commit", o que
    parecia edição na VPS. Não era. 132 dos 179 arquivos deste repositório têm
    UM commit só, de 01/07 — o "Add files via upload". O desenvolvimento de
    verdade seguiu no `agenteia` (o `origin` da VPS), e este espelho ficou
    parado. Pra esses, o repositório NÃO é a fonte da verdade: deployar
    regrediria a VPS em um mês.
    """
    if sha_vps == sha_ref:
        return "IGUAL", ""

    hist = historico_do_caminho(ref, caminho_repo)
    for i, (commit, sha, assunto) in enumerate(hist):
        if sha == sha_vps:
            if i == 0:
                return "IGUAL", ""
            return "ATRASADO", (f"{i} commit(s) atrás — está em {commit[:7]} "
                                f"\"{assunto[:46]}\"")

    if len(hist) <= 1:
        quando = f" ({hist[0][0][:7]})" if hist else ""
        return "ESPELHO PARADO", (
            f"este repo tem 1 commit só deste arquivo{quando}, do upload "
            f"inicial. A VPS seguiu em frente sem ele — NÃO deployar.")

    return "DIVERGENTE", (
        f"o repo acompanha este arquivo ({len(hist)} commits), mas o conteúdo "
        f"da VPS não bate com nenhum. Alguém editou de um lado só — precisa "
        f"de olho humano antes de qualquer escrita.")


def main():
    p = argparse.ArgumentParser(
        description="Diz o que está rodando na VPS. Não escreve nada.")
    p.add_argument("--ref", default=REF_PADRAO,
                   help=f"o que comparar (padrão: {REF_PADRAO})")
    p.add_argument("--tudo", action="store_true",
                   help="inclui patch_*/probe_*/diag_*/aplicar_*")
    p.add_argument("--sem-buscar", action="store_true", dest="sem_buscar",
                   help="não faz git fetch (usa o que já está em .git/)")
    args = p.parse_args()

    if not (Path("agents").is_dir() or Path("daemon_maestro.py").exists()):
        print("rode de dentro do ~/jarvis (não achei nem agents/ nem "
              "daemon_maestro.py)")
        return 2
    try:
        git("rev-parse", "--git-dir")
    except Exception:
        print("~/jarvis não é repositório git — sem histórico pra comparar.")
        return 2

    if not args.sem_buscar:
        ramo = args.ref.split("/", 1)[1] if "/" in args.ref else args.ref
        print(f"buscando {REMOTE}/{ramo}...", flush=True)
        try:
            git("fetch", "--quiet", REMOTE, ramo)
        except Exception as e:
            print(f"  fetch falhou ({str(e)[:90]})")
            print("  sigo com o que já está em .git/ — pode estar desatualizado.")
    try:
        git("rev-parse", "--verify", args.ref)
    except Exception:
        print(f"não conheço a referência '{args.ref}'.")
        print(f"remotes disponíveis:\n{git('remote', '-v', checar=False)}")
        return 2

    # tudo que o repositório tem, com o sha de cada blob — uma chamada só
    arquivos = {}
    for linha in git("ls-tree", "-r", args.ref).splitlines():
        cabeca, _, caminho = linha.partition("\t")
        partes = cabeca.split()
        if len(partes) >= 3 and partes[1] == "blob":
            arquivos[caminho] = partes[2]

    alvos = {c: s for c, s in arquivos.items()
             if c not in IGNORAR
             and not c.startswith(IGNORAR_PREFIXO)
             and (args.tudo or not AVULSO.match(Path(c).name))}

    # conteúdo de todos eles numa chamada, pra ler os cabeçalhos de caminho
    consulta = "".join(f"{args.ref}:{c}\n" for c in alvos)
    bruto = subprocess.run(["git", "cat-file", "--batch"],
                           input=consulta.encode(), capture_output=True).stdout
    conteudo, pos = {}, 0
    for caminho in alvos:
        fim = bruto.find(b"\n", pos)
        if fim < 0:
            break
        partes = bruto[pos:fim].split()
        if len(partes) < 3:
            pos = fim + 1
            continue
        tam = int(partes[2])
        conteudo[caminho] = bruto[fim + 1:fim + 1 + tam]
        pos = fim + 1 + tam + 1

    grupos = {"DIVERGENTE": [], "ATRASADO": [], "AUSENTE": [], "COLISÃO": [],
              "DUPLICADO": [], "ESPELHO PARADO": [], "IGUAL": []}

    for caminho_repo, sha_ref in sorted(alvos.items()):
        dados = conteudo.get(caminho_repo, b"")
        declarado = cabecalho_de_caminho(dados)
        copias = copias_na_vps(caminho_repo, declarado)

        if not copias:
            grupos["AUSENTE"].append((caminho_repo, "não existe na VPS", ""))
            continue

        estados = []
        for c in copias:
            try:
                sha_vps = sha_de_blob(c.read_bytes())
            except Exception as e:
                estados.append((c, "ILEGÍVEL", str(e)[:50]))
                continue
            sit, det = classificar(sha_vps, sha_ref, args.ref, caminho_repo)
            estados.append((c, sit, det))

        if len(estados) > 1:
            resumo = " · ".join(f"{c}={s}" for c, s, _ in estados)
            na_raiz = [c for c, _, _ in estados if c.parent == Path(".")]
            if na_raiz:
                # raiz + pacote: a da raiz é a cópia morta, o caso do
                # daemon_maestro que travou a postagem por dias
                grupos["DUPLICADO"].append((caminho_repo, resumo, estados))
            else:
                # dois pacotes diferentes: executor/engine.py e
                # workflows/engine.py são módulos DIFERENTES, e um repositório
                # chapado não consegue guardar os dois com o mesmo nome. Um
                # deles não existe aqui — chamar isso de duplicata esconde que
                # o espelho é estruturalmente incapaz de representá-los.
                grupos["COLISÃO"].append((caminho_repo, resumo, estados))
            continue

        c, sit, det = estados[0]
        grupos.setdefault(sit, []).append((caminho_repo, str(c), det))

    larg = 64
    print()
    print("=" * larg)
    print(f"CONFERIDOR — {args.ref}")
    print("=" * larg)

    def bloco(chave, titulo, explica="", teto=0):
        itens = grupos.get(chave) or []
        if not itens:
            return
        print(f"\n{titulo} ({len(itens)})")
        if explica:
            print(f"  {explica}")
        mostrar = itens[:teto] if teto else itens
        for item in mostrar:
            nome, onde, det = item[0], item[1], item[2]
            print(f"   • {nome}")
            print(f"     {onde}")
            if det and not isinstance(det, list):
                print(f"     {det}")
        if teto and len(itens) > teto:
            print(f"   ... e mais {len(itens) - teto} "
                  f"(rode com --tudo pra ver a lista inteira)")

    bloco("ATRASADO", "⏳ ATRASADO — o repo tem correção que não rodou",
          "o único grupo seguro pra deployar: a VPS bate com um commit ANTIGO\n"
          "  deste mesmo repositório, então subir é seguir a linha, não pular\n"
          "  pra outra. Foi isto que escondeu o b435f3c por um dia.")
    bloco("DIVERGENTE", "⚠️  DIVERGENTE — o repo acompanha, mas o conteúdo não bate",
          "não dá pra saber de que lado está o certo sem olhar. NÃO deployar\n"
          "  sem antes comparar à mão.")
    bloco("DUPLICADO", "👯 DUPLICADO — mesma coisa em dois lugares",
          "o daemon importa o do pacote; o da raiz é código morto. Foi assim\n"
          "  que a postagem balanceada ficou dias travada.")
    bloco("COLISÃO", "💥 COLISÃO DE NOME — o espelho não consegue guardar os dois",
          "são módulos DIFERENTES com o mesmo nome de arquivo. Um repositório\n"
          "  chapado só cabe um; o outro não existe aqui e nunca poderá ser\n"
          "  deployado por este caminho.")
    bloco("ESPELHO PARADO", "🪞 ESPELHO PARADO — o repo não é a fonte da verdade",
          "1 commit só, do upload de 01/07. O desenvolvimento seguiu no\n"
          "  'agenteia' (o origin da VPS) e este espelho ficou pra trás.\n"
          "  DEPLOYAR QUALQUER UM DESTES REGRIDE A VPS EM UM MÊS.",
          teto=0 if args.tudo else 8)
    bloco("AUSENTE", "🚫 NÃO EXISTE NA VPS",
          "arquivo novo, ou que mora em lugar que eu não procurei.",
          teto=0 if args.tudo else 12)

    print()
    print("-" * larg)
    print(f"em dia: {len(grupos['IGUAL'])}   "
          f"atrasado: {len(grupos['ATRASADO'])}   "
          f"divergente: {len(grupos['DIVERGENTE'])}")
    print(f"espelho parado: {len(grupos['ESPELHO PARADO'])}   "
          f"duplicado: {len(grupos['DUPLICADO'])}   "
          f"colisão: {len(grupos['COLISÃO'])}   "
          f"ausente: {len(grupos['AUSENTE'])}")
    if not args.tudo:
        print("(só código de produção — use --tudo pra incluir patch_/probe_/diag_)")
    print("-" * larg)
    print("nada foi alterado: este script só lê.")

    return 1 if (grupos["ATRASADO"] or grupos["DIVERGENTE"]) else 0


if __name__ == "__main__":
    sys.exit(main())
