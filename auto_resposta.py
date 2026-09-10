#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# auto_resposta.py -- fecha o loop do engajamento: varre os posts RECENTES das
# contas (IG + FB, via Graph API), acha comentários com o GATILHO ("eu quero",
# "quanto", "link"...) e RESPONDE na hora — no FB com o LINK clicável do produto,
# no IG mandando pra BIO (no IG link em comentário não clica). Best-effort: se
# faltar permissão ou der erro, loga e segue. Nada trava.
#
# Descobre os posts sozinho (não depende de nada gravado) — funciona pra qualquer
# post, inclusive os do hunter. Usa o MESMO contas.json do roteador (3 contas).
#
# Uso (VPS):  cd ~/jarvis && .venv/bin/python auto_resposta.py            (responde)
#             .venv/bin/python auto_resposta.py --teste                   (dry-run)
# Liga com:   echo 'AUTO_RESPONDER=1' >> ~/jarvis/.env   (senão fica dormente)
import os
import re
import sys
import json
import time
import random
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
GRAPH = "https://graph.facebook.com/v21.0"
STORE_DIR = BASE_DIR / "shared" / "engajamento"
RESPONDIDOS = STORE_DIR / "respondidos.json"


def _carregar_env():
    for cand in (BASE_DIR / ".env", Path(".env")):
        if not cand.exists():
            continue
        for linha in cand.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            k, _, v = linha.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        break


_carregar_env()

try:
    import requests
    _REQ_OK = True
except Exception:
    _REQ_OK = False

# a regra do "não repete enquanto houver alternativa" mora num lugar só desde
# 09/09 — este arquivo e o `comentarios.py` usam a MESMA. Os dois caminhos de
# import porque o repo é achatado e a VPS usa pacotes.
try:
    from shared.rotacao import escolher_sem_repetir as _rodar
except Exception:  # pragma: no cover
    from rotacao import escolher_sem_repetir as _rodar


def _log(m):
    print(f"[auto_resposta] {m}")


def _ligado() -> bool:
    return os.environ.get("AUTO_RESPONDER", "0").strip().lower() in ("1", "true", "sim")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "")).encode("ascii", "ignore").decode()
    return s.lower().strip()


# gatilhos: default pensado pra isca "comenta EU QUERO" + perguntas de compra
# ⚠️ "MANDA" ENTROU EM 10/09 E ERA UM BURACO ABERTO PELAS PRÓPRIAS FRASES.
# Os comentários fixados do Dre pedem três palavras: QUERO, LINK e MANDA. As
# duas primeiras já casavam; **"MANDA" não** — a lista só tinha `me manda`, e o
# `_bateu` faz substring, então "me manda" NÃO está contido em "manda". Ou seja:
# a conta ia pedir "comenta MANDA", a pessoa ia comentar exatamente isso, e o
# robô ia ignorar. Pedido atendido ao pé da letra e resposta nenhuma é pior que
# não ter pedido.
#
# ⚠️ E O ERRO AQUI TEM LADO BARATO. `manda` pega "mandaram", "demanda" — e o
# custo disso é uma resposta simpática a mais. O custo do contrário é ignorar
# quem fez exatamente o que a legenda mandou fazer. Na dúvida, responder.
_GATILHOS_DEFAULT = ("eu quero,quero,quanto custa,quanto,qual valor,valor,preco,"
                     "link,onde compro,onde compro,como compro,como comprar,"
                     "me manda,manda,me envia,envia,quero esse,quero o link,"
                     "quero um,quero comprar,interesse,tenho interesse")


def _gatilhos() -> list:
    raw = os.environ.get("AUTO_RESP_GATILHOS", _GATILHOS_DEFAULT)
    return [g for g in (_norm(x) for x in raw.split(",")) if g]


def _bateu(texto: str, gatilhos: list) -> bool:
    t = _norm(texto)
    if not t:
        return False
    return any(g in t for g in gatilhos)


# ── Respostas IG ───────────────────────────────────────────────────────────
# ⚠️ ERAM 3, E COM DM DESLIGADO SOBRAVA **UMA** (21/08). Duas das três
# prometem direct, e o `_escolhe_ig_tmpl` corta essas quando o DM está off —
# então todo comentário de todo post recebia a MESMA frase. O Dre: *"chega uma
# hora que fica chato e visualmente poluído"*. Está certo: quem abre o perfil e
# rola três Reels lê a mesma resposta três vezes, e isso denuncia robô mais que
# qualquer outra coisa que a gente faça.
#
# Agora são 7 de cada lado, pra a variedade sobreviver ao filtro do DM.
#
# ⚠️ ESTE BANCO É DO DRE (10/09/2026), palavra por palavra. As minhas eram 7
# variações de "te mandei no direct"; as dele mudam de VERBO e de ângulo
# ("dá uma olhadinha", "te explico onde encontrar", "o link tá te esperando").
# Sete frases que dizem a mesma coisa não são sete frases — é a mesma, com
# sinônimo. Foi por isso que "Bio 🔗 dá uma olhada e me fala" saiu três vezes e
# ninguém estranhou as outras: elas já eram quase iguais entre si.
_IG_TMPLS_DEFAULT = (
    "Dá uma olhadinha na sua DM, mandei por lá 📩|||"
    "Te chamei no direct com tudo certinho ✨|||"
    "O link tá te esperando lá na DM 😏|||"
    "Corre no direct que eu te explico onde encontrar 💛|||"
    "Te mandei o caminho certinho no direct 👀|||"
    "Feito! Corre ver seu direct 😍|||"
    "Mandei tudo no seu direct, dá uma olhada 👀")
# ⚠️ ESTAS NUNCA PROMETEM DIRECT. É o que sobra quando o DM está desligado, e
# prometer o que não vai chegar é pior que não responder: a pessoa espera,
# não recebe, e aprende que a conta mente.
#
# ⚠️ E O GRUPO DO WHATSAPP NÃO ESTAVA EM NENHUMA DAS 8 (09/09). O Dre queimou
# R$300 de tráfego pago pra conseguir **1 membro** no grupo — e neste Reel do
# @topshoppet_ tinha uma fila de gente comentando "Eu quero", ou seja, dezenas
# de pessoas levantando a mão de graça, e nenhuma resposta convidava pro grupo.
# O anúncio pagou caro pelo que o comentário dava de graça.
#
# Entra em ~1 de cada 4 frases, não em todas: é a mesma dose do `comentarios.py`
# (encher o grupo é meta corrente, mas toda resposta puxando pro grupo vira
# panfleto e a pessoa que só queria o link some).
#
# ⚠️ NO INSTAGRAM LINK EM COMENTÁRIO NÃO CLICA — por isso a frase do grupo
# manda pra BIO, onde o botão do grupo já existe (topshopoficial.com.br), e não
# cola um `chat.whatsapp.com` que ninguém consegue tocar.
#
# ⚠️ TAMBÉM DO DRE (10/09), e ele mandou a proporção certa sem eu pedir: das
# nove, CINCO puxam pro grupo. Faz sentido aqui e não fazia antes — quando não
# há DM, a bio é um passo morto ("vai lá, procura"), enquanto o grupo é o único
# destino onde a pessoa continua sendo alcançável depois. Encher o grupo é a
# meta que R$300 de tráfego pago não conseguiu mover.
_IG_TMPLS_SEM_DM_DEFAULT = (
    "Tá no link da bio 💛 dá uma olhadinha lá!|||"
    "Deixei tudo organizado no link da bio 🔗|||"
    "Entra no link da bio que deixei os achadinhos por lá 🛍️|||"
    "Já deixei o acesso fácil pra vocês 💛 confere a bio.|||"
    "No grupo do WhatsApp eu mando esses achados primeiro 👀💚 link na bio!|||"
    "Entra no nosso grupo 💚 sempre aparecem ofertas boas por lá!|||"
    "Quer receber os próximos também? O grupo tá no link da bio 💚|||"
    "Lá no grupo eu mando links, promoções e achadinhos antes de postar aqui 👀|||"
    "Vem pro grupo do WhatsApp 💚 o acesso tá no link da bio!")
_IG_TMPL_SEM_DM = "O link tá na bio 🚀 depois me conta o que achou!"

# ── MEMÓRIA POR POST ───────────────────────────────────────────────────────
# ⚠️ ERA `random.choice` PURO, E DÁ PRA CONTAR NOS PRINTS DO DRE (09/09): num
# Reel só, **6 respostas, 4 frases, e "Bio 🔗 dá uma olhada e me fala" três
# vezes**. Ele: *"esse burro respondendo quase tudo igual, parecendo um
# robozinho, o povo até desanima de comprar, ou para de comentar"*.
#
# ⚠️ E A REGRA JÁ EXISTIA NO ARQUIVO AO LADO. O `comentarios.py` tem memória de
# rotação desde 22/08, com o raciocínio todo escrito. Este arquivo nunca soube.
# Agora os dois importam `shared/rotacao.py` — quinta vez na semana que o
# defeito é "a regra existe e mora num arquivo só".
#
# ⚠️ A MEMÓRIA É POR POST, NÃO POR CONTA. Quem lê os comentários lê UM post de
# cima a baixo: repetir a frase entre posts diferentes ninguém nota, repetir
# dentro do mesmo post é o que denuncia. E o `auto_resposta` roda de cron a
# cada poucos minutos, então a memória tem que sobreviver ao processo — daí o
# arquivo em vez de um dicionário na função.
FRASES_POST = STORE_DIR / "frases_por_post.json"


def _ig_tmpls() -> list:
    raw = os.environ.get("AUTO_RESP_IG_TMPLS", _IG_TMPLS_DEFAULT)
    return [t.strip() for t in raw.split("|||") if t.strip()]


def _menciona_dm(t: str) -> bool:
    n = _norm(t)
    return "dm" in n or "direct" in n


def _convite_grupo() -> str:
    """O link do grupo do WhatsApp, do MESMO lugar que o site publica.

    ⚠️ NÃO COPIO O `chat.whatsapp.com` PRA CÁ. Ele já mora em
    `bio_page_builder.GRUPO_WHATSAPP` e é o que vai ao ar no site. Duas cópias
    significam que, no dia em que o convite for trocado, uma delas manda gente
    pra um grupo morto — e ninguém descobre, porque link errado numa DM não dá
    erro em lugar nenhum. É a mesma decisão do `comentarios._convite_whats`.

    ⚠️ E AQUI O LINK CLICA. Na DM, ao contrário do comentário do Instagram, o
    `chat.whatsapp.com` é tocável — então aqui vai o convite direto, não a bio.
    """
    env = os.environ.get("WHATSAPP_CONVITE", "").strip()
    if env:
        return env
    for caminho in ("bio_page_builder", "creative_engine.bio_page_builder"):
        try:
            mod = __import__(caminho, fromlist=["GRUPO_WHATSAPP"])
            return (getattr(mod, "GRUPO_WHATSAPP", "") or "").strip()
        except Exception:
            continue
    return ""


def _respirar(teste: bool = False) -> None:
    """Pausa entre uma resposta e a próxima.

    ⚠️ ISTO NASCEU JUNTO COM O TETO DE 40→200 (10/09) E NÃO É ENFEITE. Responder
    200 comentários em rajada, do mesmo perfil, em segundos, é o padrão que a
    Meta usa pra marcar automação — e o Dre já disse o que está em jogo:
    *"vai quebrar o perfil novamente"*. As contas SÃO o negócio; um perfil
    limitado custa mais que 200 respostas atrasadas.

    Com jitter porque intervalo exato é assinatura de robô tanto quanto a frase
    repetida: 200 respostas espaçadas em 3,000s cada é um gráfico reto.
    """
    if teste:
        return          # dry-run não fala com ninguém, não precisa esperar
    try:
        base = float(os.environ.get("AUTO_RESP_PAUSA", "2.5"))
    except ValueError:
        base = 2.5
    if base > 0:
        time.sleep(base * random.uniform(0.6, 1.7))


def _carregar_frases_post() -> dict:
    try:
        d = json.loads(FRASES_POST.read_text(encoding="utf-8"))
        corte = time.time() - 7 * 86400        # mesmo TTL do respondidos.json
        return {k: v for k, v in d.items()
                if isinstance(v, dict) and float(v.get("ts", 0)) >= corte}
    except Exception:
        return {}


def _salvar_frases_post(d: dict) -> None:
    """Atômico, pelo mesmo motivo do `respondidos.json`: o cron pode rodar de
    novo no meio da escrita e ler um arquivo pela metade."""
    try:
        FRASES_POST.parent.mkdir(parents=True, exist_ok=True)
        tmp = FRASES_POST.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(FRASES_POST)
    except Exception:
        pass          # memória é conforto, não requisito: nunca trava a resposta


def _banco_ig(dm_ok: bool) -> list:
    """As frases disponíveis pro modo atual.

    ⚠️ COM O DM OFF O CONJUNTO É OUTRO, não o mesmo filtrado. Antes isto
    peneirava a lista única e sobrava 1 frase — todo comentário recebia a
    mesma. Cada modo tem o seu banco, então a variedade não depende de quantas
    frases por acaso não citam direct."""
    if dm_ok:
        return _ig_tmpls() or [_IG_TMPL_SEM_DM]
    raw = os.environ.get("AUTO_RESP_IG_TMPLS_SEM_DM", _IG_TMPLS_SEM_DM_DEFAULT)
    tmpls = [t.strip() for t in raw.split("|||")
             if t.strip() and not _menciona_dm(t)]
    return tmpls or [_IG_TMPL_SEM_DM]


def _escolhe_ig_tmpl(dm_ok: bool, post: str = "", memoria: dict = None) -> str:
    """Sorteia uma resposta SEM repetir o que já foi dito NESTE post.

    Sem DM confirmado, só usa as que NÃO prometem direct — prometer o que não
    vai chegar é pior que não responder: a pessoa espera, não recebe, e aprende
    que a conta mente.
    """
    banco = _banco_ig(dm_ok)
    if memoria is None or not post:
        # sem post identificado não há como ter memória; melhor sortear que
        # travar a resposta
        return random.choice(banco)
    chave = f"{post}|{'dm' if dm_ok else 'bio'}"
    reg = memoria.get(chave) or {}
    escolhida, recentes = _rodar(banco, reg.get("frases") or [])
    memoria[chave] = {"frases": recentes, "ts": int(time.time())}
    return escolhida or random.choice(banco)


def _dm_ligado() -> bool:
    return os.environ.get("AUTO_RESP_DM", "0").strip().lower() in ("1", "true", "sim")


_LINKS_POR_POST = None


def _link_do_post(permalink: str) -> str:
    """O link de AFILIADO do produto daquele vídeo. '' se não achar.

    ⚠️ O DM MANDAVA A HOME DO SITE (21/08). A pessoa perguntava de um produto
    específico e recebia `topshopoficial.com.br` — tinha que procurar sozinha
    o que acabou de ver. O Dre: *"se não, o vídeo estoura, mas as vendas não
    existem"*. É o degrau mais caro do funil inteiro: quem pergunta é quem já
    decidiu, e é justo aí que a gente devolvia trabalho em vez de link.

    O dado já existia e ninguém tinha ligado as pontas: o `posts_ledger` grava
    o `link` de afiliado por produção, o `ledger_publicados` casa esse registro
    com o post publicado, e o `publicados.jsonl` sai com `id` (shortcode) e
    `link` na mesma linha.

    Cai pro site quando não acha — melhor a home que nada, mas o log conta,
    porque cada queda dessas é uma venda que dependia de uma junção que falhou.
    """
    ls = _links_do_post(permalink)
    return ls[0] if ls else ""


def _links_do_post(permalink: str) -> list:
    """TODOS os links do post. Reel devolve 1; carrossel devolve N.

    ⚠️ UM CARROSSEL É UMA LISTA DE PRODUTOS, e escolher um deles pra chamar de
    "o produto" seria inventar. Quem comentou "eu quero" num post de 5 itens não
    disse qual — então a DM honesta mostra os que apareceram, em vez de apostar
    num e errar em 4 de 5.
    """
    _carregar_ledger_links()
    v = _LINKS_POR_POST.get(_shortcode(permalink))
    if not v:
        return []
    return [x for x in (v if isinstance(v, (list, tuple)) else [v]) if x]


def _shortcode(permalink: str) -> str:
    """O código do post na URL. É a chave que liga o comentário ao produto."""
    m = re.search(r"/(?:reel|reels|p|tv)/([^/?#]+)", permalink or "")
    return m.group(1) if m else ""


# ⚠️ O LEDGER ENVELHECE SOZINHO, E ISSO NÃO DAVA SINAL (10/09/2026).
# O `publicados.jsonl` não é escrito por quem publica: ele é RASPADO DO LOG pelo
# `ledger_publicados --salvar`, um comando manual. Se ninguém rodar, o post de
# ontem não está lá — e o sintoma é a DM mandar a home do site, que é
# exatamente o "degrau mais caro do funil" descrito acima.
#
# Então o `auto_resposta` regenera o ledger quando ele está velho. É seguro: o
# `ledger_publicados` SÓ LÊ logs e o posts_ledger, e escreve um arquivo que já é
# a saída dele. Não encosta em quem publica.
LEDGER_VALIDADE_H = float(os.environ.get("AUTO_RESP_LEDGER_H", "6"))


def _atualizar_ledger(forcar: bool = False) -> str:
    """Regenera publicados.jsonl se estiver velho. Devolve o que aconteceu."""
    arq = BASE_DIR / "shared" / "publicados.jsonl"
    try:
        idade_h = (time.time() - arq.stat().st_mtime) / 3600 if arq.exists() else 1e9
    except Exception:
        idade_h = 1e9
    if not forcar and idade_h < LEDGER_VALIDADE_H:
        return f"ledger com {idade_h:.1f}h — ainda fresco"
    try:
        import ledger_publicados as LP
        dados = LP.juntar()
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in dados),
                       encoding="utf-8")
        global _LINKS_POR_POST
        _LINKS_POR_POST = None          # força reler
        com_link = sum(1 for d in dados if (d.get("link") or "").strip())
        return (f"ledger regenerado: {len(dados)} publicação(ões), "
                f"{com_link} com link de produto")
    except Exception as e:
        return f"⚠️ não consegui regenerar o ledger ({str(e)[:60]}) — sigo com o velho"


def _carregar_ledger_links() -> dict:
    global _LINKS_POR_POST
    if _LINKS_POR_POST is not None:
        return _LINKS_POR_POST
    _LINKS_POR_POST = {}
    _sem_link = 0
    try:
        arq = BASE_DIR / "shared" / "publicados.jsonl"
        for ln in arq.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                r = json.loads(ln)
            except Exception:
                continue
            sc, lk = (r.get("id") or "").strip(), (r.get("link") or "").strip()
            if sc and lk:
                _LINKS_POR_POST[sc] = lk
            elif sc:
                _sem_link += 1
        # ⚠️ OS DOIS NÚMEROS, NÃO SÓ O BOM. "505 com link" sozinho parece saúde;
        # ao lado de quantos ficaram SEM link vira diagnóstico — post no ledger
        # sem link é junção que falhou (slug não pareou), e é uma causa
        # diferente de "o post nem está no ledger" (ledger velho).
        _log(f"   {len(_LINKS_POR_POST)} post(s) com link de produto no ledger"
             + (f" · {_sem_link} sem link (junção falhou)" if _sem_link else ""))
    except Exception as e:
        _log(f"   (sem publicados.jsonl: {str(e)[:50]}) — DM vai pro site")

    # ── ⚠️ O CARROSSEL TEM O PRÓPRIO LEDGER, E É FONTE DE PRIMEIRA MÃO ──
    # Medido em 10/09: VIDEO 44/44 com link (100%), CAROUSEL 0/28 (0%).
    # Separação total — não era rotação de log, era formato.
    #
    # O `publicados.jsonl` é RASPADO do log procurando "[plataforma] publicado:",
    # e o carrossel é logado como "✅ Carrossel publicado [conta] — link": a
    # palavra cai do lado errado do colchete. Consertar aquela regex seria
    # remendar o remendo — log existe pra humano ler, muda quando alguém melhora
    # uma mensagem e some quando rotaciona.
    #
    # O `carrosseis_ledger.jsonl` é escrito pelo próprio `carrossel_brain` no
    # momento da publicação, com a `url` na mão. Fonte de primeira mão.
    _n_carr = 0
    try:
        arq = BASE_DIR / "shared" / "carrosseis_ledger.jsonl"
        for ln in arq.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                r = json.loads(ln)
            except Exception:
                continue
            sc = _shortcode(r.get("url") or "")
            links = [l for l in (r.get("links") or []) if l]
            # ⚠️ NÃO SOBRESCREVE o que já veio do publicados.jsonl: se um post
            # está nos dois, o primeiro ganha. Aqui é acréscimo, não disputa.
            if sc and links and sc not in _LINKS_POR_POST:
                _LINKS_POR_POST[sc] = links
                _n_carr += 1
        if _n_carr:
            _log(f"   +{_n_carr} carrossel(éis) com link (ledger próprio)")
    except Exception:
        pass
    return _LINKS_POR_POST


# ⚠️ A DM TAMBÉM ERA UMA FRASE SÓ (10/09). Duas constantes, uma pra cada caso —
# ou seja, 200 pessoas recebendo a MESMA mensagem privada no mesmo dia. Na DM
# isso é pior que no comentário: comentário público a pessoa entende como
# legenda, mensagem privada idêntica é claramente robô. Mesma rotação do resto.
_DM_PRODUTO_DEFAULT = (
    "Oiee! 😍 é esse aqui ó: {link} 💛 corre que some rápido!|||"
    "achei aqui pra você 🥰 {link} — qualquer coisa me chama|||"
    "é esse 👉 {link} ✨ dá uma olhada no preço|||"
    "oi! tá aqui ó 💛 {link} — se tiver dúvida me fala|||"
    "prontinho 😊 {link} · me conta depois se você gostou")

# ⚠️ E O PLANO B NÃO É MAIS SÓ A HOME DO SITE. Mandar `topshopoficial.com.br`
# pra quem perguntou de UM produto é devolver trabalho: a pessoa tem que
# procurar sozinha o que acabou de ver. Se eu não sei qual é o produto, o
# grupo do WhatsApp é o melhor destino que existe — lá tem gente e tem busca,
# e encher o grupo é meta corrente. Vira membro em vez de virar beco sem saída.
_DM_SEM_LINK_DEFAULT = (
    "Oiee! 😍 esse eu mando certinho no grupo dos achadinhos: {whats} "
    "💛 lá eu poso o link de tudo|||"
    "oi! 🥰 entra no grupo que eu mando o link de todos os achados: {whats}|||"
    "tá tudo aqui ó: {site} 💛 e no grupo eu mando antes: {whats}")
_DM_SEM_LINK_SEM_GRUPO = ("Oiee! 😍 tá tudo aqui ó: {site} "
                          "💛 corre que as ofertas somem rápido!")


# ⚠️ O CARROSSEL PRECISA DO SEU PRÓPRIO JEITO DE FALAR (10/09). "é esse aqui
# ó: <link>" num post de 5 produtos está errado em 4 de 5 vezes. Aqui a DM
# mostra a lista e deixa a pessoa escolher — e continua sendo uma conversa,
# porque termina perguntando.
_DM_LISTA_DEFAULT = (
    "Oiee! 😍 nesse post tinha mais de um — deixei todos aqui ó:\n{lista}\n"
    "💛 me fala qual você quer que eu te ajudo!|||"
    "oi! 🥰 esse post era uma listinha, então mandei todos:\n{lista}\n"
    "qual deles te interessou?|||"
    "achei aqui pra você ✨ eram esses:\n{lista}\n"
    "me conta qual chamou atenção 👀")


def _banco_dm(tem_link: bool, ctx: dict) -> list:
    # lista com mais de um item tem banco próprio: ver `_DM_LISTA_DEFAULT`
    if tem_link and ctx.get("lista") and ctx.get("n_links", 0) > 1:
        env = os.environ.get("AUTO_RESP_DM_TMPL_LISTA", "")
        bruto = env if env.strip() else _DM_LISTA_DEFAULT
        return [t.strip() for t in bruto.split("|||") if t.strip()]
    env = os.environ.get("AUTO_RESP_DM_TMPL_PRODUTO" if tem_link
                         else "AUTO_RESP_DM_TMPL", "")
    bruto = env if env.strip() else (_DM_PRODUTO_DEFAULT if tem_link
                                     else _DM_SEM_LINK_DEFAULT)
    frases = [t.strip() for t in bruto.split("|||") if t.strip()]
    # ⚠️ frase que pede {whats} sem convite viraria "entra no grupo: " — a
    # mesma regra do comentarios.py. Convidar sem dizer pra onde é pior que
    # não convidar.
    frases = [f for f in frases if "{whats}" not in f or ctx.get("whats")]
    return frases or [_DM_SEM_LINK_SEM_GRUPO]


def _enviar_dm_ig(ig: str, comment_id: str, token: str,
                  permalink: str = "", memoria: dict = None) -> bool:
    """DM (private reply) em resposta a um comentário. No direct o link CLICA.
    Precisa do escopo instagram_manage_messages. Best-effort."""
    links = _links_do_post(permalink)
    link = links[0] if links else ""
    # ⚠️ TETO NA LISTA: um carrossel de 10 vira uma DM que ninguém lê, e o
    # WhatsApp/Instagram encurtam mensagem longa. 5 é o que cabe numa olhada.
    _teto = int(os.environ.get("AUTO_RESP_DM_MAX_LINKS", "5"))
    ctx = {"link": link,
           "n_links": len(links),
           "lista": "\n".join(f"• {l}" for l in links[:_teto]),
           "site": os.environ.get("AUTO_RESP_SITE", "topshopoficial.com.br"),
           "whats": _convite_grupo()}
    if not link:
        _log(f"   ⚠️ sem link do produto pra {permalink[-14:] or '?'} — "
             f"{'mando o grupo' if ctx['whats'] else 'mando o site'} "
             f"(rode --diag-dm pra ver por quê)")
    banco = _banco_dm(bool(link), ctx)
    chave = (f"dm|{_shortcode(permalink)}|"
             f"{'lista' if len(links) > 1 else 'prod' if link else 'plano_b'}")
    if memoria is not None:
        reg = memoria.get(chave) or {}
        escolhida, recentes = _rodar(banco, reg.get("frases") or [])
        memoria[chave] = {"frases": recentes, "ts": int(time.time())}
    else:
        escolhida = random.choice(banco)
    try:
        msg = escolhida.format(**ctx)
    except Exception:
        msg = re.sub(r"\{[^}]*\}", "", escolhida).strip()
    r = _post(f"{GRAPH}/{ig}/messages", {
        "recipient": json.dumps({"comment_id": comment_id}),
        "message": json.dumps({"text": msg}),
        "access_token": token,
    })
    if r.get("message_id") or r.get("recipient_id") or r.get("id"):
        return True
    err = (r.get("error") or {}).get("message") or ""
    if err:
        _log(f"   ⚠️ DM IG falhou ({err[:100]})")
    return False


def _carregar_respondidos() -> dict:
    try:
        d = json.loads(RESPONDIDOS.read_text(encoding="utf-8"))
        corte = time.time() - 7 * 86400        # TTL 7 dias (limpa o histórico velho)
        return {k: v for k, v in d.items() if isinstance(v, (int, float)) and v >= corte}
    except Exception:
        return {}


def _salvar_respondidos(d: dict) -> None:
    """Grava de forma ATÔMICA: escreve num temporário e troca de nome.

    O write_text direto abre o arquivo, ZERA e só então escreve. Quem ler
    naquele instante encontra arquivo vazio — e arquivo vazio aqui significa
    "nunca respondi ninguém", ou seja, responder todo mundo de novo.

    Em 04/08 isso não era teórico: o crontab tinha 5 cópias desta linha e elas
    liam e gravavam ao mesmo tempo. O os.replace é atômico no mesmo sistema de
    arquivos — quem lê vê o conteúdo velho ou o novo, nunca um pedaço.
    """
    try:
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = RESPONDIDOS.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, RESPONDIDOS)
    except Exception:
        pass


def _token_da_conta(conta: dict) -> str:
    """Resolve o token pelo page_token_env (contas.json); fallback global."""
    env = conta.get("page_token_env", "")
    return (os.environ.get(env, "") if env else "").strip() \
        or os.environ.get("FACEBOOK_PAGE_TOKEN", "").strip() \
        or os.environ.get("META_ACCESS_TOKEN", "").strip()


def _get(url, params):
    try:
        r = requests.get(url, params=params, timeout=30)
        return r.json() or {}
    except Exception as e:
        _log(f"   ⚠️ GET falhou: {str(e)[:80]}")
        return {}


def _post(url, data):
    try:
        r = requests.post(url, data=data, timeout=30)
        return r.json() or {}
    except Exception as e:
        return {"error": {"message": f"exceção: {str(e)[:80]}"}}


# ── ⚠️ O TETO REAL NÃO ERA O `AUTO_RESP_MAX` (10/09/2026) ──────────────────
# O Dre: *"tem que ser muito mais do que isso po, 40 tá pouquíssimo, quase
# nada, tem post com +1000 comentários, como pode?"*
#
# Ele está certo de que 40 é pouco, mas 40 NÃO era o que estava travando. O
# `_get` pedia `limit: 50` e **nunca seguia `paging.next`** — nenhuma ocorrência
# da palavra `paging` no arquivo inteiro. Num post de 1000 comentários a API
# devolvia 50 e os outros 950 eram INALCANÇÁVEIS. Subir o AUTO_RESP_MAX de 40
# pra 400 não mudaria nada, porque o comentário nº 51 nunca chegava a ser lido.
#
# 📌 E o efeito é pior que "responde menos": os 50 que voltam são sempre os
# mesmos, já respondidos e já no `respondidos.json`. A cada rodada o script lia
# 50, pulava 50 e ia embora — o post ficava congelado no mesmo lugar para
# sempre, com o log dizendo "✅ respondi 0" como se estivesse tudo em dia.
def _get_paginas(url, params, max_paginas: int = 20) -> list:
    """Todos os itens, seguindo `paging.next`. Para no teto de páginas.

    ⚠️ O TETO EXISTE PRA NÃO VIRAR LAÇO INFINITO. Um cursor que se repete (a
    API às vezes devolve o mesmo `after`) rodaria pra sempre gastando chamada;
    o teto e a checagem de cursor repetido cortam os dois casos.
    """
    itens, vistos_cursores = [], set()
    d = _get(url, params)
    for _ in range(max(1, int(max_paginas))):
        itens.extend(d.get("data") or [])
        prox = ((d.get("paging") or {}).get("cursors") or {}).get("after")
        if not prox or prox in vistos_cursores or not (d.get("paging") or {}).get("next"):
            break
        vistos_cursores.add(prox)
        d = _get(url, {**params, "after": prox})
    return itens


_URL_RE = re.compile(r"https?://\S+")


def _extrai_link(texto: str) -> str:
    m = _URL_RE.search(texto or "")
    return m.group(0) if m else ""


# ── INSTAGRAM ──────────────────────────────────────────────────────────────
def _velho_demais(carimbo: str, horas: int) -> bool:
    """O post é mais antigo que a janela?

    O AUTO_RESP_HORAS existia desde sempre, aparecia no log como "janela 48h" —
    e NUNCA era usado pra filtrar nada. Quem limitava de fato era o
    AUTO_RESP_MIDIAS (os N posts mais recentes). O log dizia uma coisa que o
    código não cumpria.

    Sem carimbo (o Facebook nem pedia created_time) devolve False: na dúvida
    olha o post, porque deixar de responder um comentário custa mais que uma
    chamada a mais.
    """
    if not carimbo or horas <= 0:
        return False
    try:
        t = carimbo.strip().replace("Z", "+0000")
        # ISO do Graph: 2026-08-03T12:34:56+0000
        from datetime import datetime
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
            try:
                dt = datetime.strptime(t, fmt)
                break
            except ValueError:
                continue
        else:
            return False
        idade_h = (time.time() - dt.timestamp()) / 3600.0
        return idade_h > horas
    except Exception:
        return False


def _resp_instagram(conta, token, gatilhos, respondidos, limites, teste,
                    frases_post=None) -> int:
    ig = str(conta.get("instagram_user_id", "")).strip()
    if not ig:
        return 0
    handle = _norm(conta.get("handle", "")).lstrip("@")
    feitos = 0

    # SÓ comentários de cima (top-level). O /media/comments do IG já devolve os
    # parents; a gente NÃO desce em .replies, então nunca responde subcomentário.
    # ⚠️ `permalink` entra aqui porque é ele que identifica o POST no ledger —
    # o media_id numérico não forma a URL do Reel (o IG usa shortcode), e é
    # pelo shortcode que o `publicados.jsonl` guarda o link do produto. Sem
    # este campo o DM não tem como saber de qual produto o vídeo fala.
    midia = _get(f"{GRAPH}/{ig}/media",
                 {"fields": "id,timestamp,permalink", "limit": limites["midias"],
                  "access_token": token}).get("data", [])
    for m in midia:
        if feitos >= limites["max"]:
            break
        if _velho_demais(m.get("timestamp", ""), limites["horas"]):
            continue          # fora da janela: nem pede os comentários
        cmts = _get_paginas(f"{GRAPH}/{m.get('id')}/comments",
                            {"fields": "id,text,username,timestamp", "limit": 50,
                             "access_token": token},
                            limites["paginas"])
        # ⚠️ SEM ESTA LINHA O CONSERTO DA PAGINAÇÃO É INVISÍVEL. O sintoma
        # antigo ("respondi 0") é idêntico ao de um post sem comentários novos;
        # a única forma de distinguir "já respondi todo mundo" de "só enxergo
        # os primeiros 50" é o script dizer quantos ele VIU.
        if len(cmts) > 50:
            _pend = sum(1 for c in cmts if str(c.get("id", "")) not in respondidos)
            _log(f"   📣 post {(m.get('permalink') or '')[-13:]}: {len(cmts)} "
                 f"comentário(s) lidos, {_pend} ainda sem resposta")
        for c in cmts:
            cid = str(c.get("id", ""))
            if not cid or cid in respondidos:
                continue
            if _norm(c.get("username", "")).lstrip("@") == handle:   # não responde a si mesmo
                continue
            if not _bateu(c.get("text", ""), gatilhos):
                continue

            # 1) DM (private reply) com o link clicável — se ligado e com escopo
            dm_ok = True if teste and _dm_ligado() else \
                (_enviar_dm_ig(ig, cid, token, m.get("permalink", ""), frases_post)
                 if (_dm_ligado() and not teste) else False)
            # 2) resposta pública, sem repetir o que já foi dito NESTE post
            # (quem lê os comentários lê um post inteiro — é aí que a
            # repetição aparece, não entre posts diferentes)
            msg = _escolhe_ig_tmpl(dm_ok, str(m.get("id") or ""), frases_post)

            if teste:
                # no dry-run mostra QUAL link o DM levaria — é o que distingue
                # "vai mandar o produto" de "vai mandar a home de novo"
                _prod = _link_do_post(m.get("permalink", "")) if _dm_ligado() else ""
                _log(f"   [DRY] IG responderia @{c.get('username')} → {msg}"
                     + (f"  (+DM: {_prod or 'SITE — sem link do produto'})"
                        if _dm_ligado() else ""))
                respondidos[cid] = int(time.time()); feitos += 1
                if feitos >= limites["max"]:
                    break
                continue
            r = _post(f"{GRAPH}/{cid}/replies", {"message": msg, "access_token": token})
            if r.get("id"):
                _log(f"   💬 IG respondeu @{c.get('username')} ({conta.get('handle')})"
                     + (" +DM" if dm_ok else ""))
                respondidos[cid] = int(time.time()); feitos += 1
                _salvar_respondidos(respondidos)
                # ⚠️ grava JUNTO com o respondidos, não só no fim: o cron roda
                # a cada poucos minutos e um post viral é respondido ao longo
                # de várias rodadas. Memória que só existe em RAM durante a
                # rodada não impede repetição NENHUMA entre rodadas — que é
                # exatamente o caso do Reel do @topshoppet_ (comentários
                # chegando por 22h seguidas).
                if frases_post is not None:
                    _salvar_frases_post(frases_post)
                _respirar(teste)
            else:
                err = (r.get("error") or {}).get("message") or str(r)[:120]
                _log(f"   ⚠️ IG não respondeu ({err})")
                if "permission" in err.lower() or "#200" in err or "#10" in err:
                    return feitos   # sem escopo: nem tenta os próximos
            if feitos >= limites["max"]:
                break
    return feitos


# ── FACEBOOK ───────────────────────────────────────────────────────────────
def _resp_facebook(conta, token, gatilhos, respondidos, limites, teste) -> int:
    page = str(conta.get("facebook_page_id", "")).strip()
    if not page:
        return 0
    site = os.environ.get("AUTO_RESP_SITE", "topshopoficial.com.br")
    tmpl = os.environ.get("AUTO_RESP_FB_TMPL",
                          "😍 aqui ó: {link} — aproveita que a oferta some rápido!")
    feitos = 0

    videos = _get(f"{GRAPH}/{page}/videos",
                  {"fields": "id,created_time", "limit": limites["midias"],
                   "access_token": token}).get("data", [])
    for v in videos:
        if feitos >= limites["max"]:
            break
        if _velho_demais(v.get("created_time", ""), limites["horas"]):
            continue
        # filter=toplevel → só comentários de cima (ignora subcomentários/replies)
        cmts = _get_paginas(f"{GRAPH}/{v.get('id')}/comments",
                            {"fields": "id,message,from", "filter": "toplevel",
                             "limit": 50, "access_token": token},
                            limites["paginas"])
        # 1) descobre o LINK do produto a partir do NOSSO 1º comentário (tem o link)
        link = ""
        for c in cmts:
            if str((c.get("from") or {}).get("id", "")) == page:
                link = _extrai_link(c.get("message", "")) or link
        link = link or site
        # 2) responde os comentários de gatilho (que não são nossos)
        for c in cmts:
            cid = str(c.get("id", ""))
            if not cid or cid in respondidos:
                continue
            if str((c.get("from") or {}).get("id", "")) == page:      # não responde a si mesmo
                continue
            if not _bateu(c.get("message", ""), gatilhos):
                continue
            msg = tmpl.format(link=link)
            if teste:
                _log(f"   [DRY] FB responderia {(c.get('from') or {}).get('name')} → {msg}")
                respondidos[cid] = int(time.time()); feitos += 1
                if feitos >= limites["max"]:
                    break
                continue
            r = _post(f"{GRAPH}/{cid}/comments", {"message": msg, "access_token": token})
            if r.get("id"):
                _log(f"   💬 FB respondeu ({conta.get('handle') or page})")
                respondidos[cid] = int(time.time()); feitos += 1
                _salvar_respondidos(respondidos)
                _respirar(teste)
            else:
                err = (r.get("error") or {}).get("message") or str(r)[:120]
                _log(f"   ⚠️ FB não respondeu ({err})")
                if "permission" in err.lower() or "#200" in err or "#10" in err:
                    return feitos
            if feitos >= limites["max"]:
                break
    return feitos


def _diag_dm(contas, limites) -> int:
    """Por que a DM manda a home do site em vez do produto?

    ⚠️ ESTE MODO EXISTE PORQUE "SEM LINK DO PRODUTO" TEM DUAS CAUSAS QUE PEDEM
    CONSERTOS OPOSTOS, e o log antigo não distinguia:
      · o post NÃO ESTÁ no ledger  → ledger velho (ninguém rodou --salvar)
      · está no ledger SEM link    → a junção por slug falhou na produção
    Consertar a errada não muda nada, e o sintoma continua igual.
    """
    print(f"\n{'='*70}\n  DIAGNÓSTICO DA DM — de onde sai o link do produto\n{'='*70}")
    print(f"\n{_atualizar_ledger(forcar=True)}")
    ledger = _carregar_ledger_links()

    # o que está no arquivo, sem link (junção falhou) — pra separar as causas
    sem_link = set()
    try:
        arq = BASE_DIR / "shared" / "publicados.jsonl"
        for ln in arq.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                r = json.loads(ln)
            except Exception:
                continue
            sc = (r.get("id") or "").strip()
            if sc and not (r.get("link") or "").strip():
                sem_link.add(sc)
    except Exception:
        pass

    tot = com = fora = quebrado = 0
    por_tipo = {}          # media_type -> [total, com link]
    for chave, conta in contas.items():
        token = _token_da_conta(conta)
        ig = str(conta.get("instagram_user_id", "")).strip()
        if not token or not ig:
            continue
        # ⚠️ `media_type` ENTRA AQUI PRA UMA PERGUNTA ESPECÍFICA (10/09). Os
        # posts que faltam no ledger caem todos nas MESMAS datas nas SEIS
        # contas, ~metade de cada uma — o que não parece rotação de log. A
        # suspeita é carrossel: o `patch_carrossel_uploader` loga
        # "✅ Carrossel publicado [conta] — link", e o `ledger_publicados`
        # procura "[plataforma] publicado:" (palavra DEPOIS do colchete, com
        # dois-pontos). Formatos incompatíveis ⇒ carrossel nunca entra.
        # Em vez de eu afirmar isso, a coluna responde.
        midia = _get(f"{GRAPH}/{ig}/media",
                     {"fields": "id,timestamp,permalink,media_type",
                      "limit": limites["midias"], "access_token": token}).get("data", [])
        recentes = [m for m in midia
                    if not _velho_demais(m.get("timestamp", ""), limites["horas"])]
        if not recentes:
            continue
        print(f"\n── {conta.get('handle', chave)} · {len(recentes)} post(s) na janela ──")
        for m in recentes[:12]:
            sc = _shortcode(m.get("permalink", ""))
            tipo = (m.get("media_type") or "?")[:8]
            tot += 1
            por_tipo[tipo] = por_tipo.get(tipo, [0, 0])
            por_tipo[tipo][0] += 1
            if not sc:
                quebrado += 1
                marca, detalhe = "❌", "permalink sem shortcode (formato novo?)"
            elif sc in ledger:
                com += 1
                por_tipo[tipo][1] += 1
                _v = ledger[sc]
                _ls = _v if isinstance(_v, (list, tuple)) else [_v]
                marca = "✅"
                detalhe = (f"{len(_ls)} links · {_ls[0][:38]}…" if len(_ls) > 1
                           else _ls[0][:52])
            elif sc in sem_link:
                quebrado += 1
                marca, detalhe = "⚠️ ", "no ledger SEM link — a junção por slug falhou"
            else:
                fora += 1
                marca, detalhe = "🕳️ ", "não está no ledger (log não tem o par 📤/✅)"
            print(f"   {marca} {sc or '?':<14} {m.get('timestamp','')[:10]} "
                  f"{tipo:<9} {detalhe}")

    print(f"\n{'='*70}")
    print(f"  {tot} post(s) recentes · ✅ {com} mandariam o PRODUTO · "
          f"🕳️ {fora} fora do ledger · ⚠️ {quebrado} com junção quebrada")
    if tot:
        print(f"  {com/tot*100:.0f}% das DMs levariam o link certo.")
    if por_tipo:
        print(f"\n  por tipo de post:")
        for t, (n, c) in sorted(por_tipo.items(), key=lambda kv: -kv[1][0]):
            print(f"     {t:<10} {c:3}/{n:<3} com link "
                  f"({c/n*100:3.0f}%)" if n else "")
    if fora:
        print(f"\n  🕳️ {fora} não estão no ledger.")
        # ⚠️ EU JÁ ESCREVI AQUI "não há como reconstruir" E ERA CHUTE. Os
        # ausentes caem nas MESMAS datas nas seis contas, ~metade de cada —
        # padrão de FORMATO, não de rotação de log. A tabela por tipo acima é
        # quem responde: se os ausentes forem CAROUSEL, a causa é que o
        # `patch_carrossel_uploader` loga "✅ Carrossel publicado [conta] — link"
        # e o `ledger_publicados` procura "[plataforma] publicado:" — a palavra
        # cai do lado errado do colchete e o dois-pontos não existe.
        _carr = por_tipo.get("CAROUSEL")
        if _carr and _carr[1] == 0:
            print(f"     ⚠️ TODOS os {_carr[0]} CARROSSEL(éis) estão sem link — "
                  f"e nenhum outro tipo está.")
            print(f"     Não é rotação de log: o carrossel é logado em outro")
            print(f"     formato e o ledger não enxerga. Ver ROADMAP 10/09.")
            print(f"     📌 E pra carrossel isso é MENOS grave do que parece: um")
            print(f"        post de LISTA não tem 'o produto' — a DM do grupo é a")
            print(f"        resposta certa ali, não um link de item.")
        else:
            print(f"     O `publicados.jsonl` é RASPADO do log; sem o par 📤/✅")
            print(f"     o post não entra. Veja a tabela por tipo acima.")
    if quebrado:
        print(f"\n  ⚠️ {quebrado} estão no ledger mas SEM link: o slug não pareou")
        print(f"     com o posts_ledger.jsonl. Conserto é na produção, não aqui.")
    return 0


def main():
    teste = "--teste" in sys.argv or "--dry" in sys.argv

    def _arg(nome, padrao):
        """--midias 5 / --horas 168. Existe porque rodar a cada 5 minutos com a
        janela inteira multiplicaria as chamadas do Graph por 12 e estouraria o
        limite da API. O cron faz duas passadas: uma rápida e frequente nos
        posts novos, e uma funda de hora em hora."""
        try:
            i = sys.argv.index(nome)
            return int(float(sys.argv[i + 1]))
        except (ValueError, IndexError):
            return padrao
    if not _REQ_OK:
        _log("❌ 'requests' não instalado."); return 1
    # o --diag-dm só LÊ (ledger + lista de posts): não depende do interruptor,
    # e negar diagnóstico porque a automação está desligada seria esconder
    # justamente o dado de quem está decidindo se liga
    if not _ligado() and not teste and "--diag-dm" not in sys.argv:
        _log("⚪ AUTO_RESPONDER desligado (rode com --teste pra simular, ou "
             "'echo AUTO_RESPONDER=1 >> .env' pra ligar).")
        return 0

    try:
        import roteador_contas as RC
        contas = RC.carregar_contas()
    except Exception as e:
        _log(f"❌ não carreguei contas.json: {e}"); return 1

    if "--diag-dm" in sys.argv:
        return _diag_dm(contas, {
            "horas": _arg("--horas", int(float(os.environ.get("AUTO_RESP_HORAS", "168")))),
            "midias": _arg("--midias", int(float(os.environ.get("AUTO_RESP_MIDIAS", "25")))),
        })

    gatilhos = _gatilhos()
    respondidos = _carregar_respondidos()
    frases_post = _carregar_frases_post()
    # ⚠️ ANTES DE RESPONDER, o ledger. Sem isto a DM do post de ontem manda a
    # home do site — e é justo no post novo que a pergunta chega.
    if _dm_ligado():
        _log(f"   {_atualizar_ledger()}")
    limites = {
        "horas": _arg("--horas", int(float(os.environ.get("AUTO_RESP_HORAS", "168")))),
        "midias": _arg("--midias", int(float(os.environ.get("AUTO_RESP_MIDIAS", "25")))),
        # ⚠️ AGORA É POR CONTA, NÃO O BOLO DAS SEIS (10/09). Antes o laço fazia
        # `rest = max - total` e dava `break` quando zerava: a PRIMEIRA conta do
        # contas.json podia comer o orçamento inteiro e as outras cinco não
        # recebiam resposta nenhuma — justamente no dia em que um post explode,
        # que é o dia em que mais importa. E como o `contas.json` tem ordem
        # fixa, seria sempre a mesma conta ganhando.
        "max": _arg("--max", int(float(os.environ.get("AUTO_RESP_MAX", "200")))),
        # quantas páginas de 50 comentários buscar por post (20 = 1000)
        "paginas": _arg("--paginas", int(float(os.environ.get("AUTO_RESP_PAGINAS", "20")))),
    }
    # teto global, só como freio de emergência — o orçamento que manda é o por
    # conta. Sem isto, 6 contas × 200 num dia estranho viram 1200 chamadas.
    teto_total = _arg("--max-total", int(float(os.environ.get("AUTO_RESP_MAX_TOTAL", "600"))))
    _log(f"{'DRY-RUN' if teste else 'ATIVO'} · {len(contas)} conta(s) · "
         f"gatilhos: {len(gatilhos)} · janela {limites['horas']}h "
         f"· até {limites['midias']} post(s) por conta "
         f"· até {limites['paginas'] * 50} comentário(s) por post "
         f"· {limites['max']}/conta (teto {teto_total})")

    total = 0
    for chave, conta in contas.items():
        token = _token_da_conta(conta)
        if not token:
            _log(f"   ⏭️  {conta.get('handle', chave)}: sem token ({conta.get('page_token_env')}) — pulo")
            continue
        if total >= teto_total:
            _log(f"   ⏸️  teto global de {teto_total} atingido — as contas "
                 f"restantes ficam pra próxima rodada do cron")
            break
        rest = {**limites, "max": min(limites["max"], teto_total - total)}
        total += _resp_instagram(conta, token, gatilhos, respondidos, rest, teste,
                                 frases_post)
        rest = {**limites, "max": min(limites["max"], max(0, teto_total - total))}
        if rest["max"] <= 0:
            continue
        total += _resp_facebook(conta, token, gatilhos, respondidos, rest, teste)

    if not teste:
        _salvar_respondidos(respondidos)
        _salvar_frases_post(frases_post)
    _log(f"✅ {'simularia' if teste else 'respondi'} {total} comentário(s).")
    return 0


if __name__ == "__main__":
    # TRAVA DE INSTÂNCIA ÚNICA. Em 04/08/2026 o `crontab -l` tinha esta
    # mesma linha repetida (algumas 4x, o ceo_agent 8x) e as cópias rodaram
    # juntas o dia inteiro. shared/trava.py conta a história inteira.
    # Sem a trava disponível, roda como antes — ela protege, não bloqueia.
    try:
        from shared.trava import rodar_unico
    except Exception:
        sys.exit(main())
    sys.exit(rodar_unico("auto_resposta", main))
