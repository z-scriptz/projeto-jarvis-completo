#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_resposta_repetida.py -- 6 respostas, 4 frases, uma delas 3 vezes
#
# POR QUE ISTO EXISTE (09/09/2026)
# ────────────────────────────────
# O Dre mandou os prints de um Reel do @topshoppet_ que explodiu, com a fila de
# "Eu quero" nos comentários e o bot respondendo:
#
#   ennycosta__      → Bio 🔗 dá uma olhada e me fala
#   isa__debortoli   → Achei também! Link na bio pra você ver o preço 👀
#   melissaemari2021 → Bio 🔗 dá uma olhada e me fala          ← 2ª vez
#   brsarah7         → O link tá na bio 🔗 depois me conta o que achou!
#   bonitobeloved    → Bio 🔗 dá uma olhada e me fala          ← 3ª vez
#   gabryelle_00     → Na bio tem ele e uns parecidos 👀
#
# *"esse burro respondendo quase tudo igual, parecendo um robozinho, o povo até
# desanima de comprar, ou para de comentar"*.
#
# ⚠️ A CAUSA ERA `random.choice` PURO — e a regra que impede isso já existia no
# arquivo ao lado (`comentarios.py`, desde 22/08) e nunca chegou aqui.
#
# ⚠️ E O TESTE TEM QUE ATRAVESSAR RODADAS DE CRON. O `auto_resposta` roda a cada
# poucos minutos; os comentários daquele Reel chegaram ao longo de 22 HORAS.
# Memória que só vive em RAM durante uma rodada não impede repetição nenhuma no
# caso real — então aqui o disco é exercitado de propósito.
#
#   python3 teste_resposta_repetida.py
import ast
import importlib
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

ok = falhou = 0


def checa(desc, cond, extra=""):
    global ok, falhou
    if cond:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}" + (f"\n      {extra}" if extra else ""))


# ── a regra, sozinha ─────────────────────────────────────────────────────────
from shared.rotacao import escolher_sem_repetir as rodar

print("\n── a regra: não repete enquanto houver alternativa ──")
banco8 = [f"f{i}" for i in range(8)]
saidas, rec = [], []
for _ in range(4):
    esc, rec = rodar(banco8, rec)
    saidas.append(esc)
checa("4 sorteios num banco de 8 → 4 frases distintas", len(set(saidas)) == 4,
      str(saidas))
checa("a memória guarda METADE do banco (4 de 8)", len(rec) == 4, str(rec))

print("\n   ── ⚠️ lembrar de TUDO é o mesmo que não lembrar de nada ──")
# se o teto fosse len-1 ou len, `novas` esvaziaria e viraria sorteio puro
_, rec3 = rodar(["a", "b", "c"], [])
checa("banco de 3 lembra só 1 (metade, arredondando pra baixo)",
      len(rec3) == 1, str(rec3))
_, rec2 = rodar(["a", "b"], [])
checa("banco de 2 lembra 1 (o piso é 1, nunca 0)", len(rec2) == 1, str(rec2))
checa("banco de 1 não quebra", rodar(["a"], ["a"])[0] == "a")
checa("banco vazio devolve string vazia", rodar([], [])[0] == "")
checa("None no lugar do banco não quebra", rodar(None, None)[0] == "")

print("\n   ── ⚠️ a escolhida não pode entrar DUAS vezes na memória ──")
# ([escolhida] + recentes) sem filtrar duplicaria quando o `or candidatas`
# caísse numa frase que já estava lá, encurtando a janela real de proteção
_, rr = rodar(["a"], ["a"], lembrar=4)
checa("frase repetida não duplica na memória", rr.count("a") == 1, str(rr))

# ── a fiação, com disco de verdade ───────────────────────────────────────────
print("\n── ⚠️ O CASO REAL: um post, muitos comentários, VÁRIAS rodadas de cron ──")
tmp = Path(tempfile.mkdtemp(prefix="resp_"))
os.environ["AUTO_RESPONDER"] = "0"          # não deixa nada tentar a rede
ar = importlib.import_module("auto_resposta")
ar.FRASES_POST = tmp / "frases_por_post.json"

POST = "17900000000000000"                  # o Reel do pet
respostas = []
for rodada in range(3):                     # 3 passadas do cron
    mem = ar._carregar_frases_post()        # ⚠️ relê do DISCO, como o cron faz
    for _ in range(3):                      # 3 comentários novos por passada
        respostas.append(ar._escolhe_ig_tmpl(False, POST, mem))
    ar._salvar_frases_post(mem)

cont = Counter(respostas)
checa("o arquivo de memória foi criado", ar.FRASES_POST.exists())

# ⚠️ A GARANTIA NÃO É "TODAS DISTINTAS", E ISTO IMPORTA. A memória guarda
# METADE do banco de propósito: se guardasse tudo, a rotação viraria uma
# permutação — nunca repete e é lida como robô do mesmo jeito, só que por
# regularidade em vez de repetição (o raciocínio está em shared/rotacao.py).
# Então o que se garante é uma JANELA: dentro de `memória + 1` respostas
# consecutivas, nenhuma frase aparece duas vezes.
JANELA = len(ar._banco_ig(False)) // 2 + 1
_colisao = [(i, j) for i in range(len(respostas))
            for j in range(i + 1, min(i + JANELA, len(respostas)))
            if respostas[i] == respostas[j]]
checa(f"⚠️ nenhuma frase repete dentro de {JANELA} respostas seguidas",
      not _colisao,
      f"colidiram nas posições {_colisao[:3]}")
checa("nunca repete a imediatamente anterior",
      not any(respostas[i] == respostas[i + 1] for i in range(len(respostas) - 1)))

# o número do print do Dre: 6 respostas, 4 frases, uma delas 3×. Com o conserto,
# 6 respostas seguidas têm que dar 6 frases (a janela é 5, mas em 6 sorteios
# sem reposição na janela o máximo que uma frase repete é 1 vez, nunca 3).
_seis = Counter(respostas[:6])
checa("nas 6 primeiras (o caso do print) nenhuma frase sai 3×",
      max(_seis.values()) < 3, str(_seis.most_common(2)))
checa("e saem pelo menos 5 frases diferentes (o print deu 4)",
      len(_seis) >= 5, f"{len(_seis)} distintas")

print("\n   ── ⚠️ a memória é POR POST, não global ──")
# repetir entre posts diferentes ninguém nota (cada um lê um post); repetir
# DENTRO do post é o que denuncia. Se a memória fosse global, um post viral
# esgotaria o banco e o post seguinte cairia em sorteio puro.
mem = ar._carregar_frases_post()
outro = ar._escolhe_ig_tmpl(False, "17911111111111111", mem)
checa("post novo escolhe do banco inteiro (não herda o esgotado)",
      bool(outro))
checa("cada post tem sua própria chave",
      len([k for k in mem if k.startswith(POST)]) == 1 and len(mem) == 2,
      str(list(mem)))

print("\n── ⚠️ SEM DM, NENHUMA RESPOSTA PODE PROMETER DIRECT ──")
# prometer o que não chega é pior que não responder: a pessoa espera, não
# recebe, e aprende que a conta mente
banco_sem_dm = ar._banco_ig(False)
checa("o banco sem-DM não cita direct/dm",
      not any(ar._menciona_dm(t) for t in banco_sem_dm), str(banco_sem_dm)[:100])
checa("o banco COM dm é outro, não o mesmo filtrado",
      set(ar._banco_ig(True)) != set(banco_sem_dm))

print("\n── ⚠️ O GRUPO DO WHATSAPP ENTRA NA ROTAÇÃO (mas não em todas) ──")
# R$300 de tráfego pago = 1 membro no grupo. Este Reel tinha dezenas de mãos
# levantadas de graça e NENHUMA resposta convidava pro grupo.
com_grupo = [t for t in banco_sem_dm if "grupo" in t.lower() or "zap" in t.lower()]
checa("existe frase que convida pro grupo", len(com_grupo) >= 1, str(com_grupo))

# ⚠️ EU TINHA POSTO "no máximo 1 em 3" AQUI, E A RÉGUA ERA EMPRESTADA DO LUGAR
# ERRADO. Ela vem do `comentarios.py`, onde a frase é o 1º comentário — uma
# transmissão que TODO MUNDO vê, e onde puxar sempre pro grupo vira panfleto.
# Aqui é RESPOSTA A QUEM PERGUNTOU: a pessoa levantou a mão, então oferecer o
# grupo é responder, não empurrar. O Dre mandou 5 de 9 e a proporção é dele.
# O que continua sendo defeito é não sobrar SAÍDA pra quem só quer o link.
sem_grupo = [t for t in banco_sem_dm if t not in com_grupo]
checa("sobra alternativa pra quem só quer o link (≥3 frases sem grupo)",
      len(sem_grupo) >= 3, f"{len(sem_grupo)} de {len(banco_sem_dm)}: {sem_grupo}")
# ⚠️ no IG link em comentário NÃO clica — a frase do grupo tem que dizer PARA
# ONDE ir, não colar um chat.whatsapp.com que ninguém consegue tocar
checa("⚠️ nenhuma cola chat.whatsapp.com (no IG não clica)",
      not any("chat.whatsapp" in t for t in banco_sem_dm))
# ⚠️ ESTE NÚMERO É UM AVISO, NÃO UMA REPROVAÇÃO. Duas das frases do Dre
# ("Entra no nosso grupo 💚 sempre aparecem ofertas boas por lá!" e "Lá no grupo
# eu mando links... antes de postar aqui") convidam sem dizer ONDE fica o grupo.
# No Instagram isso deixa a pessoa sem caminho — mas são as palavras dele, e
# reescrever calado é o oposto do que este projeto faz. O teste garante que a
# MAIORIA aponte pra bio; as duas ficam como estão até ele decidir.
_com_destino = [t for t in com_grupo if "bio" in t.lower()]
checa("a maioria das frases de grupo diz onde ele fica (bio)",
      len(_com_destino) > len(com_grupo) / 2,
      f"{len(_com_destino)} de {len(com_grupo)} apontam pra bio")

print("\n── ⚠️ O POST DE 1000 COMENTÁRIOS (o teto real não era o AUTO_RESP_MAX) ──")
# O Dre: *"40 tá pouquíssimo, quase nada, tem post com +1000 comentários"*.
# Ele está certo de que 40 é pouco — mas 40 não era o que travava. O `limit:50`
# sem seguir `paging.next` fazia os outros 950 serem INALCANÇÁVEIS, e subir o
# AUTO_RESP_MAX pra 400 não mudaria nada.
_paginas_pedidas = []


def _api_falsa(url, params):
    """1000 comentários em páginas de 50, como o Graph devolve."""
    _paginas_pedidas.append(params.get("after"))
    ini = int(params.get("after") or 0)
    fim = min(ini + 50, 1000)
    d = {"data": [{"id": f"c{i}", "text": "eu quero"} for i in range(ini, fim)]}
    if fim < 1000:
        d["paging"] = {"next": "http://x", "cursors": {"after": str(fim)}}
    return d


_get_real = ar._get
ar._get = _api_falsa
try:
    todos = ar._get_paginas("http://x", {"limit": 50}, 20)
    checa("1000 comentários chegam inteiros (não 50)", len(todos) == 1000,
          f"vieram {len(todos)}")
    checa("pediu 20 páginas", len(_paginas_pedidas) == 20, str(len(_paginas_pedidas)))
    checa("a 1ª página vai sem cursor", _paginas_pedidas[0] is None)

    print("\n   ── ⚠️ e o teto de páginas segura, senão é chamada infinita ──")
    _paginas_pedidas.clear()
    parcial = ar._get_paginas("http://x", {"limit": 50}, 3)
    checa("com teto 3, para em 150", len(parcial) == 150, f"{len(parcial)}")

    # cursor que se repete: a API às vezes devolve o mesmo `after`
    def _api_travada(url, params):
        return {"data": [{"id": "c1"}],
                "paging": {"next": "http://x", "cursors": {"after": "MESMO"}}}
    ar._get = _api_travada
    checa("cursor repetido não vira laço infinito",
          len(ar._get_paginas("http://x", {}, 50)) == 2)

    # ⚠️ o lado que NÃO pode disparar: resposta sem paging nenhum
    ar._get = lambda u, p: {"data": [{"id": "c1"}, {"id": "c2"}]}
    checa("post pequeno (sem paging) devolve os 2 e para",
          len(ar._get_paginas("http://x", {}, 20)) == 2)
    ar._get = lambda u, p: {}
    checa("resposta vazia não quebra", ar._get_paginas("http://x", {}, 20) == [])
finally:
    ar._get = _get_real

print("\n── ⚠️ O ORÇAMENTO É POR CONTA, NÃO O BOLO DAS SEIS ──")
# antes: `rest = max - total` com `break` ao zerar. A PRIMEIRA conta do
# contas.json podia comer tudo e as outras cinco ficavam sem resposta nenhuma —
# no dia em que um post explode, que é o dia em que mais importa.
_src_ar = (BASE / "auto_resposta.py").read_text("utf-8")
checa("existe teto por conta e teto global separados",
      "AUTO_RESP_MAX_TOTAL" in _src_ar and "teto_total" in _src_ar)
checa("o laço das contas não dá break ao esgotar a conta (usa continue)",
      "min(limites[\"max\"], teto_total - total)" in _src_ar)
checa("o padrão por conta subiu de 40", '"AUTO_RESP_MAX", "200"' in _src_ar)

print("\n── ⚠️ RAJADA DE 200 RESPOSTAS É ASSINATURA DE ROBÔ PRA META ──")
# as contas SÃO o negócio; um perfil limitado custa mais que 200 respostas
# atrasadas
checa("existe pausa entre respostas", "_respirar" in _src_ar)
checa("a pausa tem jitter (intervalo exato também é assinatura)",
      "random.uniform" in _src_ar)
checa("o dry-run não dorme", "if teste:\n        return" in _src_ar)
checa("a pausa é regulável por .env", "AUTO_RESP_PAUSA" in _src_ar)

print("\n── ⚠️ A DM: quem pergunta é quem JÁ decidiu ──")
# No dry-run do Dre: "(+DM: SITE — sem link do produto)". A pessoa perguntou de
# um produto específico e ia receber a home do site pra procurar sozinha. O
# próprio código já chamava isso de "o degrau mais caro do funil inteiro".
_ctx_com = {"link": "https://s.shopee.com.br/ABC", "site": "site.com.br",
            "whats": "https://chat.whatsapp.com/XYZ"}
_ctx_sem_grupo = {"link": "", "site": "site.com.br", "whats": ""}

banco_prod = ar._banco_dm(True, _ctx_com)
banco_b = ar._banco_dm(False, _ctx_com)
checa("com link, o banco da DM tem mais de 1 frase", len(banco_prod) > 1,
      f"{len(banco_prod)}")
checa("todas as frases de produto carregam {link}",
      all("{link}" in f for f in banco_prod), str(banco_prod)[:80])

print("\n   ── ⚠️ o plano B vira MEMBRO do grupo, não beco sem saída ──")
# mandar a home pra quem perguntou de UM produto é devolver trabalho. Se eu não
# sei qual é o produto, o grupo é o melhor destino: lá tem gente e tem busca.
checa("sem link, alguma frase convida pro grupo",
      any("{whats}" in f for f in banco_b), str(banco_b)[:80])
checa("⚠️ nenhuma frase do plano B promete um produto específico",
      not any("{link}" in f for f in banco_b), str(banco_b)[:80])

print("\n   ── ⚠️ SEM CONVITE, A FRASE DO GRUPO NEM É SORTEADA ──")
# "entra no grupo: " (vazio) é pior que não convidar
b_sem = ar._banco_dm(False, _ctx_sem_grupo)
checa("sem convite, nenhuma frase de {whats} sobra",
      not any("{whats}" in f for f in b_sem), str(b_sem))
checa("e ainda sobra pelo menos uma frase (o site)", len(b_sem) >= 1, str(b_sem))
_render = [f.format(**_ctx_sem_grupo) for f in b_sem]
checa("nada sai com chave crua", not any("{" in r for r in _render), str(_render))

print("\n   ── ⚠️ na DM o link do WhatsApp CLICA (ao contrário do comentário) ──")
# no comentário do IG o link não clica e por isso a frase manda pra bio; na DM
# é o contrário, e mandar pra bio ali seria um passo a mais de graça
_gr = [f for f in banco_b if "{whats}" in f]
checa("as frases do grupo usam o convite direto, não 'bio'",
      all("bio" not in f.lower() for f in _gr), str(_gr)[:100])
# ⚠️ o que não pode existir é um CONVITE literal (domínio + código), não a
# menção ao domínio: o comentário explica de propósito por que na DM o link
# clica. Convite duplicado vira grupo morto no dia em que um dos dois trocar,
# e link errado numa DM não dá erro em lugar nenhum.
import re as _re
_convites = _re.findall(r"chat\.whatsapp\.com/[A-Za-z0-9]{6,}",
                        (BASE / "auto_resposta.py").read_text("utf-8"))
checa("nenhum convite de grupo copiado no arquivo (vem do bio_page_builder)",
      not _convites, str(_convites))

print("\n   ── ⚠️ e a DM não repete a mesma frase pra 200 pessoas ──")
mem_dm = {}
_saidas_dm = []
for _ in range(5):
    banco = ar._banco_dm(True, _ctx_com)
    esc, rec = rodar(banco, (mem_dm.get("k") or {}).get("frases") or [])
    mem_dm["k"] = {"frases": rec}
    _saidas_dm.append(esc)
checa("5 DMs seguidas não repetem a anterior",
      not any(_saidas_dm[i] == _saidas_dm[i + 1] for i in range(4)),
      str(_saidas_dm)[:100])
_src_ar_dm = (BASE / "auto_resposta.py").read_text("utf-8")
checa("o _enviar_dm_ig recebe a memória de rotação",
      "def _enviar_dm_ig(ig, comment_id" in _src_ar_dm.replace(": str", "")
      or "memoria: dict = None) -> bool:" in _src_ar_dm)
checa("e a chamada real passa o frases_post",
      '_enviar_dm_ig(ig, cid, token, m.get("permalink", ""), frases_post)' in _src_ar_dm)

print("\n── ⚠️ O CARROSSEL: 0 de 28 com link, e não era rotação de log ──")
# Medido pelo --diag-dm em 10/09: VIDEO 44/44 (100%), CAROUSEL 0/28 (0%).
# Separação total. O publicados.jsonl é RASPADO do log procurando
# "[plataforma] publicado:", e o carrossel é logado como "✅ Carrossel publicado
# [conta] — link" — a palavra cai do lado errado do colchete.
_tmp_l = Path(tempfile.mkdtemp(prefix="ledger_"))
(_tmp_l / "shared").mkdir()
(_tmp_l / "shared" / "publicados.jsonl").write_text(
    json.dumps({"id": "REEL111", "link": "https://s.shopee.com.br/reel"}), "utf-8")
(_tmp_l / "shared" / "carrosseis_ledger.jsonl").write_text("\n".join([
    json.dumps({"url": "https://www.instagram.com/p/CARR222/",
                "links": ["https://s.shopee.com.br/a", "https://s.shopee.com.br/b",
                          "https://s.shopee.com.br/c"]}),
    # linha antiga, de antes do conserto: tem url mas não tem links
    json.dumps({"url": "https://www.instagram.com/p/VELHO33/", "slug": "x"}),
    # um carrossel que também está no publicados.jsonl não pode ser sobrescrito
    json.dumps({"url": "https://www.instagram.com/reel/REEL111/",
                "links": ["https://NAO.DEVE.GANHAR"]}),
    "{ isso nao e json",
]), "utf-8")
_base_real = ar.BASE_DIR
ar.BASE_DIR = _tmp_l
ar._LINKS_POR_POST = None
try:
    checa("o Reel continua com 1 link",
          ar._links_do_post("https://www.instagram.com/reel/REEL111/")
          == ["https://s.shopee.com.br/reel"])
    _lc = ar._links_do_post("https://www.instagram.com/p/CARR222/")
    checa("o carrossel devolve os 3 links (não 1)", len(_lc) == 3, str(_lc))
    checa("_link_do_post continua devolvendo string (compat)",
          ar._link_do_post("https://www.instagram.com/p/CARR222/")
          == "https://s.shopee.com.br/a")
    checa("carrossel sem links (linha antiga) não entra",
          ar._links_do_post("https://www.instagram.com/p/VELHO33/") == [])
    checa("⚠️ o ledger do carrossel NÃO sobrescreve o publicados.jsonl",
          ar._links_do_post("https://www.instagram.com/reel/REEL111/")
          == ["https://s.shopee.com.br/reel"])
    checa("linha quebrada não derruba a leitura", len(ar._LINKS_POR_POST) == 2,
          str(list(ar._LINKS_POR_POST)))
    checa("post desconhecido devolve lista vazia",
          ar._links_do_post("https://www.instagram.com/p/NADA/") == [])

    print("\n   ── ⚠️ e a DM do carrossel não aposta num dos 5 ──")
    # "é esse aqui ó: <link>" num post de 5 produtos erra em 4 de 5
    _ctx_lista = {"link": "https://s.shopee.com.br/a", "n_links": 3,
                  "lista": "• a\n• b\n• c", "site": "s.com", "whats": "w"}
    _b_lista = ar._banco_dm(True, _ctx_lista)
    checa("com N>1 o banco é o de LISTA", all("{lista}" in f for f in _b_lista),
          str(_b_lista)[:80])
    checa("nenhuma frase de lista diz 'é esse aqui'",
          not any("é esse aqui" in f for f in _b_lista))
    # ⚠️ a propriedade é PEDIR QUE A PESSOA ESCOLHA, não a pontuação. Minha
    # primeira asserção procurava "?" ou "me fala" e reprovou "me conta qual
    # chamou atenção 👀", que pergunta do mesmo jeito. Testar a forma em vez do
    # sentido reprova texto bom — foi o mesmo erro das duas asserções que
    # caíram contra as frases do Dre.
    checa("todas pedem que a pessoa escolha (continua conversa)",
          all("qual" in f.lower() for f in _b_lista), str(_b_lista)[:100])
    _ctx_um = {"link": "https://s.shopee.com.br/a", "n_links": 1,
               "lista": "• a", "site": "s.com", "whats": "w"}
    checa("com N==1 volta o banco de produto",
          all("{link}" in f for f in ar._banco_dm(True, _ctx_um)))
finally:
    ar.BASE_DIR = _base_real
    ar._LINKS_POR_POST = None
    shutil.rmtree(_tmp_l, ignore_errors=True)

print("\n   ── ⚠️ o carrossel grava os links na PUBLICAÇÃO, não no log ──")
# consertar a regex do ledger_publicados seria remendar o remendo: log existe
# pra humano ler, muda quando alguém melhora a mensagem e some ao rotacionar
_cb = (BASE / "carrossel_brain.py").read_text("utf-8")
checa("o registrar() grava os links", '"links": [l for l in (plano.get("links")' in _cb)
checa("grava também os nomes dos produtos", '"produtos"' in _cb)
checa("e a url já era passada na publicação",
      'url=r.get("url", "") if r.get("sucesso")' in _cb)

print("\n── ⚠️ O LEDGER ENVELHECE E ISSO NÃO DAVA SINAL ──")
# publicados.jsonl é RASPADO do log por um comando manual. Se ninguém roda, o
# post de ontem não está lá -- e é justo no post novo que a pergunta chega.
checa("o auto_resposta regenera o ledger quando está velho",
      "_atualizar_ledger" in _src_ar_dm and "AUTO_RESP_LEDGER_H" in _src_ar_dm)
checa("só regenera se a DM estiver ligada (senão é trabalho à toa)",
      "if _dm_ligado():" in _src_ar_dm)
checa("existe o modo --diag-dm", "--diag-dm" in _src_ar_dm)
checa("o --diag-dm funciona com o AUTO_RESPONDER desligado",
      '"--diag-dm" not in sys.argv' in _src_ar_dm)
# ⚠️ as duas causas pedem consertos OPOSTOS e o log antigo não distinguia
checa("o diagnóstico separa 'fora do ledger' de 'junção quebrada'",
      "não está no ledger" in _src_ar_dm and "junção por slug falhou" in _src_ar_dm)
checa("o carregador conta os SEM link, não só os bons",
      "sem link (junção falhou)" in _src_ar_dm)

print("\n── ⚠️ A REGRA MORA NUM LUGAR SÓ ──")
# foi o defeito da semana inteira: regra certa, documentada, num arquivo só.
_src_ar = (BASE / "auto_resposta.py").read_text("utf-8")
_src_cm = (BASE / "comentarios.py").read_text("utf-8")
checa("auto_resposta importa shared.rotacao", "from shared.rotacao import" in _src_ar)
checa("comentarios importa shared.rotacao", "from shared.rotacao import" in _src_cm)
for arq, s in (("auto_resposta.py", _src_ar), ("comentarios.py", _src_cm)):
    codigo = "\n".join(l for l in s.splitlines() if not l.lstrip().startswith("#"))
    checa(f"{arq} não tem cópia própria da regra",
          "def escolher_sem_repetir" not in codigo)
checa("o coletor de frases grava de forma atômica (cron concorrente)",
      ".json.tmp" in _src_ar and "tmp.replace(" in _src_ar)
checa("o --teste não grava a memória no disco",
      "if not teste:" in _src_ar and "_salvar_frases_post(frases_post)" in _src_ar)

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{'='*66}\n   {ok} passou · {falhou} falhou\n{'='*66}")
raise SystemExit(1 if falhou else 0)
