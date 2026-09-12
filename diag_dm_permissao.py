#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# diag_dm_permissao.py -- POR QUE A DM NÃO SAI: é App Review ou é configuração?
#
# POR QUE ISTO EXISTE (12/09/2026)
# ────────────────────────────────
# O Dre: *"a DM não funciona, não manda link na DM, acho que precisa de uma
# revisão por parte da META, eu tenho o recurso, mas não a autorização... quando
# a pessoa escreve 'EU QUERO' e não recebe o link, ela esquece o post."*
#
# Ele tem razão de que dói: é o lead mais quente que existe. E a pergunta dele
# não foi "conserta" — foi **"quanto tempo vai durar a briga?"**. São dois
# mundos com custos completamente diferentes:
#
#   · escopo/token/configuração   → horas
#   · Advanced Access (App Review) → semanas, com chance real de recusa
#
# ⚠️ E O LOG DE HOJE NÃO SEPARA OS DOIS. O `_enviar_dm_ig` faz:
#
#       err = (r.get("error") or {}).get("message") or ""
#       _log(f"   ⚠️ DM IG falhou ({err[:100]})")
#
# Só a MENSAGEM, cortada em 100. O que distingue os mundos é o `code` e o
# `error_subcode` do objeto de erro — jogados fora. Cinco meses de "a DM não
# funciona" sem o dado que diz por quê.
#
# 📌 ESTE ARQUIVO NÃO CONSERTA NADA. Ele responde UMA pergunta: o token tem
# `instagram_manage_messages` ou não? Com resposta, a decisão é de minutos.
#
# ⚠️ SEGREDO NENHUM É IMPRESSO. Regra do projeto, e este relatório nasceu pra
# ser colado no chat: token nunca aparece, nem pedaço dele.
#
#   .venv/bin/python diag_dm_permissao.py            # só leitura
#   .venv/bin/python diag_dm_permissao.py --tentar   # ⚠️ envia DM DE VERDADE
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

try:
    from shared.envfile import carregar_env
    carregar_env(BASE_DIR)
except Exception as e:
    print(f"⚠️  não carreguei o .env ({str(e)[:60]}) — sigo com o ambiente")

import auto_resposta as AR  # noqa: E402

GRAPH = AR.GRAPH

# ⚠️ OS ESCOPOS QUE IMPORTAM PRA ESTA PERGUNTA, e o que cada um destrava.
PRECISA = {
    "instagram_manage_messages": "⭐ A DM (private reply). SEM ISTO NADA SAI.",
    "instagram_manage_comments": "ler e responder comentários",
    "instagram_basic": "ler as mídias da conta",
    "pages_messaging": "mensageria da Página ligada",
    "pages_show_list": "listar as Páginas",
}

# Leitura provável de cada código. ⚠️ O BRUTO É SEMPRE IMPRESSO JUNTO: esta
# tabela orienta, não decide. Código que não estiver aqui não vira chute.
CODIGOS = {
    190: ("TOKEN", "token inválido ou vencido — renovar. Horas, não semanas."),
    102: ("TOKEN", "sessão expirada — renovar o token."),
    10: ("PERMISSAO", "permissão negada — tipicamente falta Advanced Access."),
    200: ("PERMISSAO", "permissão insuficiente pra esta ação."),
    # ⚠️ (#3) É O APP, NÃO O TOKEN — e eu confundi os dois (12/09/2026).
    # "Application does not have the capability to make this API call."
    # A Meta separa PERMISSÃO (o que o usuário concedeu ao token, visível no
    # debug_token) de CAPABILITY/FEATURE (o que o APLICATIVO está aprovado a
    # fazer, que fica no App Dashboard). Escopo concedido não serve de nada se
    # o app não tem o recurso habilitado — e eu li só o escopo, vi ✅ nas seis
    # contas e afirmei pro Dre "não é App Review". O (#3) diz que é do app.
    3: ("APP", "capability do APP, não escopo do token — produto/feature "
               "ausente ou sem Advanced Access no App Dashboard."),
    803: ("ALVO", "objeto não encontrado — comment_id errado ou apagado."),
    100: ("ALVO", "parâmetro inválido — comentário velho, ou usuário fora "
                  "da janela de resposta."),
    4: ("LIMITE", "limite de chamadas — só esperar."),
    17: ("LIMITE", "limite de usuário — só esperar."),
    32: ("LIMITE", "limite da Página — só esperar."),
    613: ("LIMITE", "limite de chamadas."),
}


def _cx(t):
    print(f"\n{'═' * 72}\n  {t}\n{'═' * 72}")


def _erro(r: dict) -> dict:
    return (r or {}).get("error") or {}


def _mostrar_erro(e: dict, ident="   ") -> str:
    """Imprime o erro INTEIRO e devolve a classe ('PERMISSAO', 'TOKEN', …)."""
    cod = e.get("code")
    sub = e.get("error_subcode")
    print(f"{ident}code          {cod}")
    if sub:
        print(f"{ident}error_subcode {sub}")
    print(f"{ident}type          {e.get('type', '—')}")
    print(f"{ident}message       {e.get('message', '—')}")
    if e.get("error_user_title"):
        print(f"{ident}título        {e['error_user_title']}")
    if e.get("error_user_msg"):
        print(f"{ident}explicação    {e['error_user_msg']}")
    # ⚠️ fbtrace_id é o que o suporte da Meta pede. Não é segredo.
    if e.get("fbtrace_id"):
        print(f"{ident}fbtrace_id    {e['fbtrace_id']}")
    classe, leitura = CODIGOS.get(cod, ("?", "código fora da tabela — "
                                             "leia a mensagem crua acima"))
    print(f"{ident}→ leitura     [{classe}] {leitura}")
    return classe


def _escopos(token: str) -> tuple:
    """(lista de escopos, granular por escopo, erro). Usa o próprio token."""
    r = AR._get(f"{GRAPH}/debug_token",
                {"input_token": token, "access_token": token})
    if _erro(r):
        return [], {}, _erro(r)
    d = (r.get("data") or {})
    gran = {}
    for g in d.get("granular_scopes") or []:
        gran[g.get("scope", "")] = g.get("target_ids") or []
    return list(d.get("scopes") or []), gran, {}, str(d.get("app_id") or "")


def _sonda_mensageria(ig: str, token: str) -> tuple:
    """A superfície de mensagens EXISTE pra este app? Só leitura — não envia.

    ⚠️ ESTA É A PERGUNTA QUE O ESCOPO NÃO RESPONDE. Ler os escopos diz o que o
    USUÁRIO concedeu; o `(#3) Application does not have the capability` diz que
    o APP não está habilitado. São camadas diferentes, e eu tratei como uma só.

    `GET /<ig>/conversations` toca a mesma superfície de mensageria do envio,
    sem mandar nada pra ninguém:
      · (#3) aqui também → o app não tem Instagram Messaging. App Dashboard.
      · responde normal  → a mensageria existe; só a private reply é barrada.
    """
    r = AR._get(f"{GRAPH}/{ig}/conversations",
                {"platform": "instagram", "limit": 1, "access_token": token})
    e = _erro(r)
    if not e:
        return "OK", e
    return ("SEM CAPABILITY" if e.get("code") == 3 else "OUTRO"), e


def main() -> int:
    tentar = "--tentar" in sys.argv

    _cx("A DM NÃO SAI — é App Review ou é configuração?")
    print("  Uma pergunta só: o token carrega `instagram_manage_messages`?")
    print("  ⚠️ nenhum token é impresso, nem pedaço — relatório é pra colar no chat.")

    try:
        import roteador_contas as RC
        contas = RC.carregar_contas()
    except Exception as e:
        print(f"\n❌ não carreguei contas.json: {e}")
        return 1

    print(f"\n  AUTO_RESPONDER={'1' if AR._ligado() else '0'}  ·  "
          f"AUTO_RESP_DM={'1' if AR._dm_ligado() else '0'}")
    print("  (essas duas são chaves locais — desligadas, a DM nem é tentada,")
    print("   e isso não tem nada a ver com a permissão da Meta)")

    veredito = {}
    for chave, conta in contas.items():
        handle = conta.get("handle", chave)
        token = AR._token_da_conta(conta)
        ig = str(conta.get("instagram_user_id", "")).strip()

        print(f"\n── {handle} ─────────────────────────────────")
        if not token:
            print("   ❌ sem token (page_token_env não resolveu, e não há global)")
            veredito[handle] = "SEM TOKEN"
            continue
        if not ig:
            print("   ❌ sem instagram_user_id no contas.json")
            veredito[handle] = "SEM IG ID"
            continue
        print(f"   instagram_user_id  {ig}")
        print(f"   token              presente ({len(token)} car.) ·"
              f" de {conta.get('page_token_env') or 'FACEBOOK_PAGE_TOKEN'}")

        escopos, gran, err, app_id = _escopos(token)
        if app_id:
            # ⚠️ app_id NÃO é segredo (vai em toda chamada de cliente) e é o que
            # leva direto ao app certo no developers.facebook.com — que é onde
            # a capability se resolve, não no código.
            print(f"   app_id             {app_id}")
        if err:
            print("   ⚠️ o debug_token não respondeu:")
            classe = _mostrar_erro(err)
            veredito[handle] = f"DEBUG_TOKEN {classe}"
            continue

        print(f"\n   escopos concedidos ({len(escopos)}):")
        for e, pra_que in PRECISA.items():
            tem = e in escopos
            alvos = gran.get(e) or []
            # ⚠️ TER O ESCOPO NÃO BASTA: o granular diz pra QUAIS contas ele
            # vale. Escopo concedido pra outra conta é escopo ausente aqui.
            nesta = (not alvos) or (ig in [str(a) for a in alvos])
            marca = "✅" if (tem and nesta) else ("⚠️ " if tem else "❌")
            obs = ""
            if tem and not nesta:
                obs = f"  ⚠️ concedido, mas NÃO pra esta conta ({len(alvos)} outra(s))"
            print(f"   {marca} {e:<28} {pra_que}{obs}")
        extras = [e for e in escopos if e not in PRECISA]
        if extras:
            print(f"   · outros {len(extras)}: {', '.join(sorted(extras)[:6])}"
                  + (" …" if len(extras) > 6 else ""))

        chave_dm = "instagram_manage_messages"
        alvos = gran.get(chave_dm) or []
        tem = chave_dm in escopos and ((not alvos) or ig in [str(a) for a in alvos])
        if tem:
            print(f"\n   ✅ escopo `{chave_dm}` concedido pra esta conta.")
            # ⚠️ E ISSO NÃO BASTA — foi o erro de leitura de 12/09. O escopo é
            # o que o USUÁRIO concedeu; falta saber se o APP pode usar.
            print(f"   ⚠️ mas escopo concedido ≠ app habilitado. Sondando a")
            print(f"      mensageria (só leitura, não envia nada)…")
            estado, e = _sonda_mensageria(ig, token)
            if estado == "OK":
                print(f"   ✅ a mensageria RESPONDE — o app tem a capability.")
                print(f"      Se a DM falha, é caso pontual (janela de resposta,")
                print(f"      comentário velho). Rode --tentar pro erro do envio.")
                veredito[handle] = "MENSAGERIA OK"
            elif estado == "SEM CAPABILITY":
                print(f"   ❌ (#3) A MENSAGERIA NÃO EXISTE PRA ESTE APP.")
                _mostrar_erro(e, "      ")
                print(f"      Não é o token — é o aplicativo. Resolve no")
                print(f"      developers.facebook.com, não aqui.")
                veredito[handle] = "APP SEM CAPABILITY"
            else:
                print(f"   ⚠️ a sonda falhou por outro motivo:")
                classe = _mostrar_erro(e, "      ")
                veredito[handle] = f"SONDA {classe}"
        else:
            print(f"\n   ❌ FALTA `{chave_dm}` PRA ESTA CONTA.")
            print(f"      É a permissão que a DM exige. Sem ela, nenhum ajuste")
            print(f"      de código faz a mensagem sair: é autorização da Meta,")
            print(f"      no app que gerou este token.")
            veredito[handle] = "FALTA ESCOPO DM"

        if tentar:
            print(f"\n   ── tentativa real de envio ──")
            print(f"   ⚠️ se der certo, uma pessoa REAL recebe a DM.")
            midia = AR._get(f"{GRAPH}/{ig}/media",
                            {"fields": "id,permalink", "limit": 5,
                             "access_token": token}).get("data", [])
            alvo = None
            for m in midia:
                cs = AR._get(f"{GRAPH}/{m['id']}/comments",
                             {"fields": "id,text,timestamp", "limit": 5,
                              "access_token": token}).get("data", [])
                if cs:
                    alvo = (m, cs[0])
                    break
            if not alvo:
                print("   ⏭️  nenhum comentário recente pra testar")
            else:
                m, c = alvo
                print(f"   alvo: comentário em {m.get('permalink', '')[-14:]} "
                      f"— \"{(c.get('text') or '')[:44]}\"")
                r = AR._post(f"{GRAPH}/{ig}/messages", {
                    "recipient": json.dumps({"comment_id": c["id"]}),
                    "message": json.dumps({"text": "oi! te mandei o link aqui 💚"}),
                    "access_token": token,
                })
                if r.get("message_id") or r.get("recipient_id") or r.get("id"):
                    print("   ✅ A DM SAIU. O canal funciona.")
                    veredito[handle] = "DM FUNCIONA"
                else:
                    print("   ❌ não saiu. Erro COMPLETO (é isto que faltava):")
                    classe = _mostrar_erro(_erro(r), "      ")
                    veredito[handle] = f"ENVIO {classe}"

    _cx("VEREDITO")
    for h, v in veredito.items():
        print(f"   {h:<24} {v}")

    faltam = [h for h, v in veredito.items() if v == "FALTA ESCOPO DM"]
    semcap = [h for h, v in veredito.items() if v == "APP SEM CAPABILITY"]
    okz = [h for h, v in veredito.items() if v in ("MENSAGERIA OK", "DM FUNCIONA")]
    print()
    if semcap:
        # ⚠️ ESTE É O CASO REAL DE 12/09, e é o que eu tinha descartado cedo
        # demais: escopo ✅ nas seis, e mesmo assim (#3).
        print(f"   📌 É O APP, NÃO O TOKEN. {len(semcap)} conta(s) com o escopo")
        print(f"      concedido e a mensageria recusando com (#3).")
        print(f"      **Escopo concedido ≠ app habilitado.** O que falta é")
        print(f"      capability/feature no App Dashboard — produto de")
        print(f"      mensageria do Instagram, e Advanced Access pra ele.")
        print(f"      Nenhuma linha de código aqui resolve.")
        print(f"      ⚠️ Prazo é da Meta, não nosso.")
        print(f"\n      O caminho que NÃO depende deles, e funciona amanhã:")
        print(f"      responder no próprio comentário com o produto NOMEADO +")
        print(f"      endereço curto do site. Converte menos que DM, converte")
        print(f"      muito mais que silêncio — e hoje é silêncio.")
    elif faltam and not okz:
        print(f"   📌 Falta o escopo `instagram_manage_messages` em "
              f"{len(faltam)} conta(s).")
        print(f"      Concessão de permissão — refazer o token com o escopo,")
        print(f"      ou pedir Advanced Access se o app não puder pedi-lo.")
    elif okz and (faltam or semcap):
        print(f"   📌 MISTO: {len(okz)} conta(s) com a mensageria de pé.")
        print(f"      Começa ligando a DM só onde já dá: {', '.join(okz)}")
    elif okz:
        print(f"   📌 A mensageria responde em {len(okz)} conta(s) — o app TEM")
        print(f"      a capability. Se a DM falha, é caso pontual (janela de")
        print(f"      resposta, comentário velho): conserto nosso, de horas.")
        print(f"      Rode com --tentar pra ver o `code` do envio.")
    else:
        print(f"   📌 Sem conta com token utilizável — o problema é anterior")
        print(f"      à permissão (contas.json ou .env).")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
