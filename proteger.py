#!/usr/bin/env python3
# proteger.py
# PROTETOR — fecha o .gitignore e salva o que só existe no disco da VPS.
#
# POR QUE: em 03/08 o conferidor mostrou que ~/jarvis tem 262 arquivos fora do
# git. Entre eles, scripts da raiz que rodam em produção e não estão em
# repositório NENHUM. Se esta VPS morrer, some um mês de trabalho.
#
# A MINA: 7 arquivos `.env.bak_*`, mais `jarvis_sessions_backup.zip` (login do
# Telegram) e `ig_cookies.txt` (sessão do Instagram) estão soltos e NÃO são
# cobertos pelo .gitignore atual. Um `git add -A` publicaria as chaves da
# Shopee, do Gemini, do Telegram e da Meta. Chave que entra em histórico de git
# conta como vazada mesmo depois de apagada — o conserto seria rotacionar
# tudo, não fazer um commit de remoção.
#
# Confirmado antes de escrever isto: nenhum segredo está rastreado hoje
# (`git ls-files | grep -iE '^\.env|token|secret|credential|\.session$'` vazio).
# Então dá pra resolver só com .gitignore, sem reescrever histórico.
#
# POR PADRÃO ELE NÃO COMMITA. Mostra o .gitignore que vai escrever, o que
# entraria no commit e o que ele está deixando de fora, e para. Só com
# --aplicar ele escreve o .gitignore e faz o commit. O `git push` continua
# sendo seu, sempre.
#
# Uso:
#     cd ~/jarvis
#     python3 proteger.py              # só mostra
#     python3 proteger.py --aplicar    # escreve .gitignore + commita (sem push)

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Nunca versionar. Cada linha aqui é credencial de verdade, não preferência.
SEGREDOS = """
# ── segredos (credencial de verdade — nunca versionar) ──
.env
.env.*
*.session
*.session-journal
ig_cookies.txt
jarvis_sessions_backup.zip
shared/credentials/
*token*.json
"""

# Entulho: reproduzível, ou saída de execução. Não é perda se sumir.
ENTULHO = """
# ── backups de patcher (97 arquivos em 03/08) ──
*.bak
*.bak-*
*.bak_*
*.old

# ── pastas de trabalho e lixo ──
_lixo/
_fila_*/
fila_descartada/
fila_vencida/
inbox_tiktok/
pronto_para_postar/

# ── artefatos de teste ──
preview*.png
frame*.jpg
frame*.png
emoji_teste_*.png
narracao_teste.mp3
produtos_teste.txt

# ── lixo de expansão de caminho do Windows ──
# (um $USERPROFILE que não expandiu virou nome de arquivo)
:USERPROFILE*
/15
"""

# Estado de execução: muda sozinho a cada rodada. Versionar enche o histórico
# de ruído e dá conflito em todo pull. Fica de fora, mas listado à parte no
# relatório pra você decidir — não escondo.
RUNTIME = {
    "shared/health_cache.json", "shared/health_cache.json.old",
    "shared/tiktok_vistos.json", "shared/produtos_vistos.json",
    "shared/ig_rotacao.json", "shared/roteador_cache.json",
    "shared/grupo_postados.json", "shared/amazon_cache.json",
    "shared/fontes_saude.json", "shared/fontes_descobertas.json",
    "shared/nichos_quentes.json", "shared/posts_ledger.jsonl",
    "shared/reach.jsonl", "shared/precos_historico.json",
    "hooks_alana_recentes.json", "candidatos_fontes.txt",
    "shared/ceo/", "shared/engajamento/",
}

MARCA = "# ── acrescentado pelo proteger.py ──"


def git(*args, checar=True):
    r = subprocess.run(["git"] + list(args), capture_output=True)
    if checar and r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="replace").strip()[:200])
    return r.stdout.decode(errors="replace")


def nao_rastreados() -> list:
    """Modo 'normal', não 'all', de propósito. Com --untracked-files=all o git
    entra em inbox_tiktok/, fila_vencida/ e _lixo/ e lista cada vídeo lá dentro
    — na VPS isso é dezenas de milhares de arquivos, leva minutos e parece
    travado. E é a resposta errada: eu quero tratar a pasta de lixo como UMA
    coisa a ignorar, não item por item."""
    saida = git("status", "--porcelain", "--untracked-files=normal")
    fora = []
    for linha in saida.splitlines():
        if linha.startswith("?? "):
            fora.append(linha[3:].strip().strip('"'))
    return fora


def sobrariam(padroes_novos: str) -> list:
    """O que CONTINUARIA fora do git se estes padrões entrassem no .gitignore.

    Simula por core.excludesFile + `git status`, e não por `git check-ignore`,
    porque o check-ignore lê a entrada como PATHSPEC: um arquivo chamado
    ':USERPROFILEDownloads' (o lixo que a expansão de caminho do Windows
    deixou) é interpretado como sintaxe mágica em vez de nome, e ele responde
    "não ignorado" pra algo que o .gitignore ignora perfeitamente. Medido: com
    o padrão no .gitignore, o `git status` para de listar o arquivo; o
    check-ignore continuava dizendo que não casava.

    Também não escrevo no .gitignore pra medir: se algo interrompesse o script
    no meio, o arquivo do usuário ficaria alterado sem commit.
    """
    tmp = Path(".proteger_excludes_tmp")
    # a primeira linha faz ele se ignorar: sem isso o próprio arquivo de
    # simulação aparece como "a salvar" no relatório que ele produz
    tmp.write_text(f"{tmp.name}\n" + padroes_novos, encoding="utf-8")
    try:
        r = subprocess.run(
            ["git", "-c", f"core.excludesFile={tmp}",
             "status", "--porcelain", "--untracked-files=normal"],
            capture_output=True)
        fora = []
        for linha in r.stdout.decode(errors="replace").splitlines():
            if linha.startswith("?? "):
                fora.append(linha[3:].strip().strip('"'))
        return fora
    finally:
        tmp.unlink(missing_ok=True)


# Nome de arquivo não basta: no teste, um 'credencial_solta.txt' com
# SHOPEE_SECRET dentro passou batido porque a lista de nomes suspeitos estava
# em inglês. Quem decide é o CONTEÚDO.
# Extensão de código: aqui o nome do arquivo não diz nada sobre o conteúdo.
# 'aplicar_env.py' e 'auth_youtube.py' são scripts, não credenciais — barrar
# pelo nome só ensinava a ignorar o aviso.
_EXT_CODIGO = {".py", ".sh", ".js", ".ts", ".md", ".txt"}

# Estes SÃO credencial pelo nome, em qualquer extensão.
def _nome_e_credencial(base: str) -> str:
    if base.startswith(".env"):
        return "é um arquivo .env"
    if base.endswith((".session", ".pem", ".key", ".p12")):
        return "é arquivo de chave/sessão"
    for m in ("cookies", "sessions_backup", "id_rsa", "credentials"):
        if m in base:
            return f"o nome contém '{m}'"
    return ""

# Só pra arquivo de DADOS (json/env/ini): aí o nome pesa.
_NOME_SUSPEITO_DADOS = ("secret", "credential", "credencial", "senha", "token")
_CONTEUDO_SUSPEITO = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # CHAVE=valor com valor longo o bastante pra ser chave de verdade. O
    # os.getenv("SHOPEE_APP_SECRET", "") não casa: ali não vem '=' depois do
    # nome, vem aspas — foi conferido pra não encher de falso positivo.
    # sem \b nas bordas: '_' é caractere de palavra, então \bsecret\b NÃO
    # casaria dentro de SHOPEE_APP_SECRET — que é exatamente o formato real
    re.compile(r"(?i)[a-z0-9_]*(?:api[_-]?key|secret|token|password|passwd|"
               r"senha|credential|access[_-]?key)[a-z0-9_]*"
               # a aspa que FECHA a chave num json ("api_key": ...) vem antes
               # do ':' — sem aceitá-la aqui, todo segredo em json passava
               r"['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+]{12,})"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-.]{20,}"),
)


def _valor_de_verdade(v: str, texto: str) -> bool:
    """O que veio depois do '=' é uma CHAVE, ou é o NOME de uma variável?

    Na primeira rodada real isto barrou 7 arquivos, todos falso positivo:
        CLIENT_SECRET = TP.CLIENT_SECRET      atributo de módulo
        access_token": access_token           dict montado de variável
        token = _token_da_conta               chamada de função
        page_token_env": "PAGE_TOKEN_TOPSHOP" nome da env var, não o valor

    Três sinais separam nome de chave, e nenhum deles sozinho basta:
    """
    if not v or v.lower() in ("none", "null", "true", "false", "undefined"):
        return False
    # 1. ponto = acesso a atributo. Chave não tem ponto no meio.
    if "." in v:
        return False
    # 2. forma de identificador: uma caixa só, sem hífen. Chave de verdade
    #    quase sempre mistura caixa, ou tem '-', ou é hex longo. Hex e base64
    #    compridos escapam desta regra logo abaixo.
    so_minuscula = re.fullmatch(r"[a-z_][a-z0-9_]*", v)
    so_maiuscula = re.fullmatch(r"[A-Z_][A-Z0-9_]*", v)
    if so_minuscula or so_maiuscula:
        if re.fullmatch(r"[0-9a-f]{24,}", v):
            return True               # hex longo: é chave, não nome
        if "_" in v or len(v) < 20:
            return False              # snake_case ou curto: é nome
        return True
    # 3. aparece mais de uma vez no arquivo? Nome de variável se repete;
    #    segredo costuma aparecer uma vez só.
    if texto.count(v) > 1:
        return False
    return True


def cheiro_de_segredo(caminho: str) -> str:
    """'' se parece seguro; senão o motivo.

    Falso positivo custa uma olhada; falso negativo custa rotacionar todas as
    chaves. Mas falso positivo DEMAIS custa mais que os dois: se o aviso pega
    código normal, ele vira ruído e a pessoa aprende a passar por cima — e aí
    o dia em que for de verdade, passa também.
    """
    p = Path(caminho)
    base = p.name.lower()

    motivo = _nome_e_credencial(base)
    if motivo:
        return motivo

    if caminho.endswith("/") or p.is_dir():
        return ""

    ext = p.suffix.lower()
    if ext not in _EXT_CODIGO:
        for m in _NOME_SUSPEITO_DADOS:
            if m in base:
                return f"arquivo de dados com '{m}' no nome"

    try:
        if p.stat().st_size > 2_000_000:
            return ""
        dados = p.read_bytes()
    except Exception:
        return ""
    if b"\0" in dados[:8000]:
        return ""                      # binário: não leio, não chuto
    texto = dados.decode("utf-8", errors="replace")

    for rx in _CONTEUDO_SUSPEITO:
        for achou in rx.finditer(texto):
            grupos = achou.groups()
            valor = grupos[-1] if grupos else ""
            if valor and not _valor_de_verdade(valor, texto):
                continue              # é código lendo a chave, não a chave
            trecho = achou.group(0)[:44].replace("\n", " ")
            return f"conteúdo parece credencial: {trecho}..."
    return ""


def main():
    p = argparse.ArgumentParser(
        description="Fecha o .gitignore e salva o que só existe na VPS.")
    p.add_argument("--aplicar", action="store_true",
                   help="escreve o .gitignore e commita (sem push)")
    args = p.parse_args()

    if not (Path("agents").is_dir() or Path("daemon_maestro.py").exists()):
        print("rode de dentro do ~/jarvis")
        return 2

    # 1) nada de segredo já rastreado — se houver, .gitignore não resolve
    ja = [f for f in git("ls-files").splitlines()
          if any(m in f.lower() for m in (".env", "token", "secret",
                                          "credential", ".session"))]
    if ja:
        print("PARE. Estes segredos JÁ estão rastreados:")
        for f in ja:
            print(f"   {f}")
        print("\n.gitignore não desfaz isso — o conteúdo está no histórico.")
        print("O caminho é ROTACIONAR as chaves e depois limpar o histórico.")
        print("Me mande esta lista antes de fazer qualquer outra coisa.")
        return 1
    print("nenhum segredo rastreado hoje — dá pra resolver só com .gitignore.\n")

    # 2) o .gitignore proposto
    atual = Path(".gitignore").read_text(encoding="utf-8") if Path(".gitignore").exists() else ""
    if MARCA in atual:
        print("o .gitignore já tem a seção do proteger.py — não duplico.")
        novo_texto = atual
        precisa_escrever = False
    else:
        novo_texto = atual.rstrip() + "\n\n" + MARCA + "\n" + SEGREDOS + ENTULHO
        precisa_escrever = True

    # 3) simula: com o .gitignore novo, o que sobraria pra commitar?
    print("lendo o estado do repositório...", flush=True)
    todos = nao_rastreados()
    sobra = sobrariam(SEGREDOS + ENTULHO) if precisa_escrever else todos
    cobertos = [f for f in todos if f not in set(sobra)]
    runtime = [f for f in sobra if f in RUNTIME or
               any(f.startswith(d) for d in RUNTIME if d.endswith("/"))]
    resto = [f for f in sobra if f not in runtime]
    # Pasta NUNCA entra sozinha. No modo 'normal' o git resume uma pasta
    # inteira numa linha, e adicionar essa linha arrasta tudo que há dentro —
    # inclusive o que eu não li pra checar se é credencial. Vai pro relatório
    # em separado, e quem decide é você.
    pastas = [f for f in resto if f.endswith("/") or Path(f).is_dir()]
    salvar = [f for f in resto if f not in pastas]

    # 4) conferência de segurança sobre o que REALMENTE entraria
    print(f"conferindo o conteúdo de {len(salvar)} arquivo(s)...", flush=True)
    perigo = [(f, m) for f in salvar for m in [cheiro_de_segredo(f)] if m]
    # Quarentena, não aborto. Na primeira rodada real 7 arquivos deram alarme
    # e os 7 eram falso positivo — e como o aborto era total, eles travavam os
    # outros 87. Agora o suspeito sai da lista e o resto segue: nada suspeito
    # entra sozinho, e nada limpo fica refém do suspeito.
    suspeitos = dict(perigo)
    salvar = [f for f in salvar if f not in suspeitos]

    print(f"não rastreados: {len(todos)}")
    print(f"  cobertos pelo .gitignore (atual + novo):    {len(cobertos)}")
    print(f"  estado de execução (fora, veja abaixo):     {len(runtime)}")
    print(f"  pastas (fora, veja abaixo):                 {len(pastas)}")
    print(f"  em quarentena (fora, veja abaixo):          {len(suspeitos)}")
    print(f"  A SALVAR:                                   {len(salvar)}")

    if suspeitos:
        print(f"\n🔍 EM QUARENTENA ({len(suspeitos)}) — fora do commit até você olhar")
        print("   pode ser falso positivo: código que LÊ uma chave se parece")
        print("   com uma chave. Confira e me diga quais liberar.")
        for f, motivo in sorted(suspeitos.items()):
            print(f"   • {f}")
            print(f"     {motivo}")
    else:
        print("\n✅ nenhuma credencial no que seria salvo.")

    print(f"\n── SERIA SALVO ({len(salvar)}) ──")
    for f in sorted(salvar):
        print(f"   {f}")

    if pastas:
        print(f"\n── DEIXADO DE FORA: pastas inteiras ({len(pastas)}) ──")
        print("   adicionar a pasta arrasta tudo que há dentro, e eu não li")
        print("   esse conteúdo pra saber se tem credencial. Me diga se quer")
        print("   alguma delas e eu confiro arquivo por arquivo antes:")
        for f in sorted(pastas):
            print(f"   {f}")

    if runtime:
        print(f"\n── DEIXADO DE FORA: estado de execução ({len(runtime)}) ──")
        print("   muda sozinho a cada rodada; versionar dá conflito em todo pull.")
        print("   se quiser algum destes versionado, me diga qual:")
        for f in sorted(runtime):
            print(f"   {f}")

    if not args.aplicar:
        print("\n" + "─" * 60)
        print("NADA FOI ESCRITO. Confira a lista acima e rode:")
        print("    python3 proteger.py --aplicar")
        print("o push continua sendo seu — este script nunca envia nada.")
        return 0

    if precisa_escrever:
        Path(".gitignore").write_text(novo_texto, encoding="utf-8")
        print("\n* .gitignore atualizado")
    git("add", "--", ".gitignore")
    for f in salvar:
        subprocess.run(["git", "add", "--", f], capture_output=True)

    staged = git("diff", "--cached", "--name-only").splitlines()
    if not staged:
        print("nada novo pra commitar.")
        return 0

    msg = ("Salva o que só existia no disco da VPS\n\n"
           f"{len(salvar)} arquivo(s) que não estavam em repositório nenhum — "
           "entre eles\nos scripts da raiz que rodam em produção.\n\n"
           ".gitignore passa a cobrir os segredos que estavam soltos: 7 backups\n"
           "de .env, o zip das sessões do Telegram e os cookies do Instagram.\n"
           "Nenhum deles chegou a ser versionado; isto impede o próximo add -A.\n")
    r = subprocess.run(["git", "commit", "-q", "-m", msg], capture_output=True)
    if r.returncode != 0:
        print(f"commit falhou: {r.stderr.decode(errors='replace')[:200]}")
        return 1
    print(f"* commit feito com {len(staged)} arquivo(s)")
    print("\nNÃO fiz push. Confira e envie você:")
    print("    git log -1 --stat | head -40")
    print("    git push origin main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
