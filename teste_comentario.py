#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# teste_comentario.py -- o 1º comentário sai do banco do Dre, e sai rodando?
#
# O DEFEITO QUE ISTO TRAVA (07/09/2026)
# ─────────────────────────────────────
# O Dre: *"após todo post ele posta 1 comentário igual, e eu tinha te dado 5
# comentários ou mais nas conversas passadas para colocar, e isso não mudou"*.
#
# ⚠️ E NÃO TINHA MUDADO MESMO. Em 02/09 eu escrevi o `comentarios.py` inteiro —
# as seis frases dele palavra por palavra, banco separado por formato, rotação
# com memória — e NUNCA troquei a chamada no `meta_uploader`. O
# `_montar_comentario` seguiu lendo a constante `_TMPL_IG`. Cinco dias de posts
# nas seis contas com a MESMA frase, e a frase ainda era a vetada ("corre pegar
# o seu"). Módulo escrito, testado, versionado e morto.
#
# ⚠️ POR ISSO METADE DESTE TESTE OLHA A FIAÇÃO, NÃO O BANCO. Testar só o
# `escolher()` teria passado 100% em 02/09, com o sistema publicando a frase
# velha o tempo todo. O teste tem que perguntar "o uploader CHAMA isso?", que é
# a pergunta que ninguém fez. É a terceira vez na semana que o defeito é esse
# (o `_so_musica` sem chamador, as trilhas na pasta que nada lia, e agora isto).
#
#   python3 teste_comentario.py
import ast
import os
import re
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import comentarios                                     # noqa: E402


def _fonte_uploader() -> str:
    """O código do meta_uploader, esteja ele na raiz ou em `agents/`.

    ⚠️ ISTO ESTOUROU NA VPS E A CULPA É DO PRÓPRIO ROADMAP TER AVISADO.
    Eu li o arquivo em `BASE / "meta_uploader.py"` — verdade no repo, que é
    achatado, e MENTIRA na VPS, onde ele mora em `agents/meta_uploader.py`.
    O teste morreu com FileNotFoundError bem na seção que existe pra provar que
    a fiação está certa, ou seja: o único teste que perguntava "o uploader chama
    o módulo?" não conseguia nem abrir o uploader. Caminho fixo é a mesma
    armadilha do deploy no destino errado, agora dentro do teste.
    """
    for cand in (BASE / "meta_uploader.py", BASE / "agents" / "meta_uploader.py"):
        if cand.exists():
            return cand.read_text("utf-8")
    raise SystemExit("❌ não achei meta_uploader.py nem na raiz nem em agents/")

# memória de mentira: o teste não pode sujar a rotação de produção
comentarios.MEMORIA = Path(tempfile.gettempdir()) / "teste_coment_memoria.json"
try:
    comentarios.MEMORIA.unlink()
except Exception:
    pass

ok = falhou = 0


def checa(desc, cond, extra=""):
    global ok, falhou
    if cond:
        ok += 1
        print(f"   ✅ {desc}")
    else:
        falhou += 1
        print(f"   ❌ {desc}" + (f"\n      {extra}" if extra else ""))


# ⚠️ AS CONSTRUÇÕES QUE O DRE VETOU, em 21/08 ("corre ver isso") e que eu
# repeti sem perceber no `_TMPL_IG` ("corre pegar o seu"). Nenhuma frase que vá
# ao ar pode conter isso — nem o banco, nem a rede de segurança.
VETADAS = ("corre ver", "corre pegar", "corre garantir")

print("\n── o banco é o do Dre, e nenhuma frase vetada passa ──")
_do_nicho = [f for v in comentarios._IG_REEL_POR_NICHO.values() for f in v]
todas = (comentarios._IG_REEL + _do_nicho + comentarios._IG_CARROSSEL
         + comentarios._IG_LISTA + comentarios._FB)
# ⚠️ ELE MANDOU 6 E AS 6 CONTINUAM LÁ. Em 10/09 duas saíram do banco universal
# e passaram a sair só no nicho onde funcionam ("canto da casa" → casa,
# "produto que viraliza" → tech) — é conserto de ENDEREÇO, não de texto. A
# asserção antiga contava `len(_IG_REEL) == 6` e passaria a falhar por um
# motivo bom; o que ela realmente protege é NENHUMA FRASE DELE SUMIR.
_reel_dele = set(comentarios._IG_REEL) | set(_do_nicho)
checa("as 6 frases do Dre continuam todas no ar", len(_reel_dele) == 6,
      f"tem {len(_reel_dele)}: {sorted(f[:28] for f in _reel_dele)}")
checa("nenhuma conta recebe menos de 4 frases de Reel",
      all(len(comentarios._banco("instagram", "reel", h)) >= 4
          for h in ("@topshopcasa_", "@topshoptech_", "@naomapeada")))
for v in VETADAS:
    achou = [f for f in todas if v in f.lower()]
    checa(f"nenhuma frase do banco diz '{v}'", not achou, str(achou)[:90])

print("\n── rotação: não repete enquanto houver alternativa ──")
saidas = [comentarios.escolher("instagram", formato="reel", conta="@topshoptech_")
          for _ in range(6)]
checa("6 chamadas, nenhuma vazia", all(saidas), str(saidas)[:80])
repetiu_seguida = any(saidas[i] == saidas[i + 1] for i in range(len(saidas) - 1))
checa("nunca repete a frase imediatamente anterior", not repetiu_seguida)
checa("usou pelo menos 4 frases diferentes em 6 posts", len(set(saidas)) >= 4,
      f"usou {len(set(saidas))}")

print("\n── ⚠️ O BANCO TEM QUE SABER EM QUE CONTA ESTÁ ──")
# O Dre, sobre um Reel do @topshoppet_ (cachorro com problema de ouvido,
# produto de limpeza auricular): *"o primeiro comentário dele tá péssimo!!"*.
# O que saiu foi "esse tem muita cara de produto que viraliza e depois some" —
# frase de gadget num post de saúde do pet. E tinha "pra cada canto da CASA"
# sorteável na mesma conta.
CASA = "pra cada canto da casa"
GADGET = "produto que viraliza"
_uni = comentarios._IG_REEL
checa("nenhuma frase universal cita 'canto da casa'",
      not any(CASA in f for f in _uni), str([f for f in _uni if CASA in f])[:80])
checa("nenhuma frase universal cita 'produto que viraliza'",
      not any(GADGET in f for f in _uni))
checa("as 4 universais + as de nicho continuam sendo as 6 do Dre",
      len(_uni) + len(comentarios._IG_REEL_POR_NICHO["casa"])
      + len(comentarios._IG_REEL_POR_NICHO["tech"]) == 6,
      "o conserto é de ENDEREÇO, não apaga frase dele")

_b_casa = comentarios._banco("instagram", "reel", "@topshopcasa_")
_b_tech = comentarios._banco("instagram", "reel", "@topshoptech_")
checa("'canto da casa' sai no @topshopcasa_", any(CASA in f for f in _b_casa))
checa("'canto da casa' NÃO sai no @topshoptech_", not any(CASA in f for f in _b_tech))
checa("'produto que viraliza' sai no @topshoptech_", any(GADGET in f for f in _b_tech))
checa("'produto que viraliza' NÃO sai no @topshopcasa_",
      not any(GADGET in f for f in _b_casa))

print("\n   ── ⚠️⚠️ HANDLE QUE NÃO RESOLVE NÃO PODE CAIR EM 'geral' ──")
# `geral` é o @topshop.__ e o banco dele carrega JUSTAMENTE as duas frases que
# não podem sair no pet. Se um handle desconhecido caísse ali, o conserto se
# desfazia sozinho, em silêncio, na conta que motivou o conserto. Este teste é
# o que impede isso de voltar.
checa("handle desconhecido → nicho vazio, não 'geral'",
      comentarios._nicho_da_conta("@conta_que_nao_existe") == "")
_b_desc = comentarios._banco("instagram", "reel", "@conta_que_nao_existe")
checa("e o banco dele é só o universal", len(_b_desc) == len(_uni), str(len(_b_desc)))
checa("⚠️ sem 'canto da casa'", not any(CASA in f for f in _b_desc))
checa("⚠️ sem 'produto que viraliza'", not any(GADGET in f for f in _b_desc))
checa("conta vazia também não vira 'geral'", comentarios._nicho_da_conta("") == "")
checa("None não quebra", comentarios._nicho_da_conta(None) == "")
checa("o @ e a caixa não importam",
      comentarios._nicho_da_conta("TopShopCasa_") == "casa")

print("\n   ── ⚠️ o mapa vem do contas.json, não de uma 2ª cópia ──")
# cópia desatualizada = comentário de nicho errado, que é o defeito em questão
_src_c = (BASE / "comentarios.py").read_text("utf-8")
_codigo_c = "\n".join(l for l in _src_c.splitlines()
                      if not l.lstrip().startswith("#"))
checa("lê o contas.json", "contas.json" in _codigo_c)
for h in ("topshoppet_", "topshopcasa_", "topshoptech_"):
    checa(f"não tem '{h}' escrito no código", h not in _codigo_c)

print("\n   ── as frases do Dre entram por .env, sem deploy ──")
os.environ["COMENT_IG_REEL_CASA"] = "frase nova do dre|||outra frase dele"
comentarios._NICHO_POR_HANDLE = None
_b_env = comentarios._banco("instagram", "reel", "@topshopcasa_")
checa("COMENT_IG_REEL_CASA substitui o banco daquele nicho",
      _b_env == ["frase nova do dre", "outra frase dele"], str(_b_env)[:80])
del os.environ["COMENT_IG_REEL_CASA"]
checa("e não vaza pros outros nichos",
      "frase nova do dre" not in comentarios._banco("instagram", "reel", "@topshoptech_"))

print("\n── ⚠️⚠️ A ISCA PEDE UMA PALAVRA — O ROBÔ TEM QUE RECONHECER ELA ──")
# ⚠️ ESTE É O TESTE MAIS IMPORTANTE DO ARQUIVO, e ele cruza DOIS módulos.
# Os comentários fixados do Dre pedem QUERO, LINK e MANDA. As duas primeiras já
# casavam com os gatilhos do `auto_resposta`; **MANDA não** — a lista só tinha
# `me manda`, e o casamento é por substring ("me manda" não está em "manda").
# A conta ia pedir "comenta MANDA", a pessoa ia comentar exatamente isso, e o
# robô ia ignorar. Pedido atendido ao pé da letra e resposta nenhuma é pior que
# não ter pedido.
_ar_src = (BASE / "auto_resposta.py").read_text("utf-8")
_ns_ar = {"os": os, "re": __import__("re"), "unicodedata": __import__("unicodedata")}
for _no in ast.parse(_ar_src).body:
    if isinstance(_no, ast.FunctionDef) and _no.name in ("_norm", "_bateu", "_gatilhos"):
        exec(compile(ast.Module([_no], []), "x", "exec"), _ns_ar)
    if isinstance(_no, ast.Assign) and getattr(_no.targets[0], "id", "") == "_GATILHOS_DEFAULT":
        exec(compile(ast.Module([_no], []), "x", "exec"), _ns_ar)
_gatilhos_reais = _ns_ar["_gatilhos"]()
_bateu = _ns_ar["_bateu"]

# as palavras que as iscas mandam a pessoa comentar, extraídas das próprias
# frases — assim, frase nova com palavra nova falha aqui em vez de no perfil
_pedidas = set()
for f in comentarios._IG_ISCA_DM:
    _pedidas |= set(re.findall(r"[“\"]([A-ZÀ-Ú ]{3,})[”\"]", f))
checa(f"as iscas pedem palavras identificáveis ({len(_pedidas)})", len(_pedidas) >= 3,
      str(_pedidas))
for palavra in sorted(_pedidas):
    checa(f"o robô responde a quem comenta '{palavra}'",
          _bateu(palavra, _gatilhos_reais),
          f"'{palavra}' não casa com nenhum gatilho — a conta pede e ignora")
# e com o texto do jeito que a pessoa realmente escreve
for real in ("QUERO", "quero!", "Eu Quero", "manda", "MANDA AI", "link", "Link 😍"):
    checa(f"comentário real '{real}' dispara", _bateu(real, _gatilhos_reais))

print("\n── ⚠️⚠️ A ISCA PROMETE DM: só sai se a DM estiver LIGADA ──")
# Se o auto_resposta não responde com DM, a conta pede publicamente "comenta
# QUERO que eu mando na sua DM", dezenas comentam, e nada chega. Isso não é
# post fraco — é a conta mentindo pra quem levantou a mão.
def _com_dm(lig):
    for k in ("AUTO_RESPONDER", "AUTO_RESP_DM"):
        os.environ[k] = "1" if lig else "0"
    return comentarios._banco("instagram", "reel", "@topshoppet_")

_b_off = _com_dm(False)
checa("DM desligada → nenhuma isca no banco",
      not any(f in comentarios._IG_ISCA_DM for f in _b_off), str(len(_b_off)))
_b_on = _com_dm(True)
checa("DM ligada → as 10 iscas entram",
      sum(1 for f in _b_on if f in comentarios._IG_ISCA_DM) == 10,
      f"{sum(1 for f in _b_on if f in comentarios._IG_ISCA_DM)}")
# ⚠️ os DOIS interruptores, não um: AUTO_RESP_DM=1 com AUTO_RESPONDER=0 não
# responde nada
os.environ["AUTO_RESPONDER"] = "0"; os.environ["AUTO_RESP_DM"] = "1"
checa("só o AUTO_RESP_DM ligado não basta",
      not any(f in comentarios._IG_ISCA_DM
              for f in comentarios._banco("instagram", "reel", "@x")))
_com_dm(True)

print("\n   ── ⚠️ e NUNCA em carrossel: o pedido não tem objeto ──")
# num carrossel de "3 erros" não existe "esse achadinho" pra mandar
_b_carr = comentarios._banco("instagram", "carrossel", "@topshoppet_")
checa("carrossel não recebe isca de DM",
      not any(f in comentarios._IG_ISCA_DM for f in _b_carr))
checa("carrossel não promete direct nenhum",
      not any("DM" in f or "direct" in f.lower() for f in _b_carr), str(_b_carr)[:80])
for k in ("AUTO_RESPONDER", "AUTO_RESP_DM"):
    os.environ.pop(k, None)

print("\n── carrossel NÃO herda o banco de Reel ──")
# num carrossel de "3 erros" não existe "um desses" pra comprar
carr = set(comentarios._IG_CARROSSEL)
checa("banco do carrossel é diferente do de Reel",
      carr != set(comentarios._IG_REEL))
vaza = [f for f in carr if "comprar um" in f or "já tem um desses" in f]
checa("nenhuma frase de carrossel fala de comprar um produto", not vaza,
      str(vaza)[:90])

print("\n── frase com {link} não sai sem link ──")
fb_sem = [comentarios.escolher("facebook", formato="reel", conta="@x", link="")
          for _ in range(8)]
checa("no Facebook sem link, nunca sai '{link}' cru",
      all("{link}" not in (f or "") for f in fb_sem), str(fb_sem)[:90])
# ⚠️ ESTA ASSERÇÃO ERA FALHA INTERMITENTE (~1 em 3) DESDE 02/09, e passar a
# maioria das vezes é justamente o que a escondeu: o banco do FB tem TRÊS
# frases e uma delas é a do grupo ({whats}), que legitimamente não leva
# {link}. Sortear essa não é defeito — a asserção é que estava errada.
# Testar 12 sorteios em vez de 1 troca "às vezes falha" por "sempre responde".
fb_com = [comentarios.escolher("facebook", formato="reel", conta="@y",
                               link="https://s.shopee.com.br/abc")
          for _ in range(12)]
checa("com link, alguma frase do FB carrega o link de verdade",
      any("shopee.com.br/abc" in (f or "") for f in fb_com), str(fb_com)[:120])
checa("nenhuma sai com chave crua ({link} ou {whats})",
      not any("{" in (f or "") for f in fb_com), str(fb_com)[:120])

print("\n── ⚠️ A FIAÇÃO: o meta_uploader realmente chama o módulo? ──")
# Isto é o que faltou em 02/09. Não importo o meta_uploader (ele puxa requests
# e token da Meta); leio a árvore, que é suficiente pra responder a pergunta.
_arv = ast.parse(_fonte_uploader())
_fn = next((n for n in ast.walk(_arv)
            if isinstance(n, ast.FunctionDef) and n.name == "_montar_comentario"), None)
checa("_montar_comentario existe", _fn is not None)
if _fn:
    corpo = ast.dump(_fn)
    checa("ele importa `comentarios`", "'comentarios'" in corpo)
    checa("ele chama `escolher`", "escolher" in corpo)
    checa("ele aceita `formato`", any(a.arg == "formato" for a in _fn.args.args))

# o carrossel precisa passar formato="carrossel" — senão herda o banco de Reel
_chamadas = [n for n in ast.walk(_arv)
             if isinstance(n, ast.Call)
             and getattr(n.func, "id", "") == "_montar_comentario"]
checa("as 3 chamadas do uploader continuam lá", len(_chamadas) == 3,
      f"achei {len(_chamadas)}")
_carr = [c for c in _chamadas
         if any(k.arg == "formato" and getattr(k.value, "value", "") == "carrossel"
                for k in c.keywords)]
checa("exatamente 1 chamada passa formato='carrossel'", len(_carr) == 1,
      f"achei {len(_carr)}")

print("\n── a rede de segurança não pode ressuscitar a frase vetada ──")
_tmpl = [n for n in ast.walk(_arv)
         if isinstance(n, ast.Assign)
         and any(getattr(t, "id", "").startswith("_TMPL_") for t in n.targets)]
_textos = " ".join(ast.literal_eval(ast.unparse(n.value)) if isinstance(n.value, ast.Constant)
                   else ast.unparse(n.value) for n in _tmpl).lower()
for v in VETADAS:
    checa(f"a reserva do uploader não diz '{v}'", v not in _textos)

print(f"\n{'='*62}\n   {ok} passou · {falhou} falhou\n{'='*62}")
raise SystemExit(1 if falhou else 0)
