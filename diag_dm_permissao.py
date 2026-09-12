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
    3: ("PERMISSAO", "método exige uma permissão que o app não tem."),
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
    return list(d.get("scopes") or []), gran, {}


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

        escopos, gran, err = _escopos(token)
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
            print(f"\n   ✅ O ESCOPO DA DM ESTÁ CONCEDIDO PRA ESTA CONTA.")
            print(f"      Então a falha NÃO é App Review — é outra coisa")
            print(f"      (janela de resposta, comentário velho, conta sem")
            print(f"      Página ligada, ou o envio nem está sendo tentado).")
            print(f"      Rode com --tentar pra ver o erro real do envio.")
            veredito[handle] = "ESCOPO OK"
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
    okz = [h for h, v in veredito.items() if v in ("ESCOPO OK", "DM FUNCIONA")]
    print()
    if faltam and not okz:
        print(f"   📌 É APP REVIEW. {len(faltam)} conta(s) sem o escopo da DM.")
        print(f"      Nenhuma linha de código resolve — é pedir Advanced Access")
        print(f"      pra `instagram_manage_messages` no app que gerou o token.")
        print(f"      ⚠️ Prazo é da Meta, não nosso. Enquanto isso, o caminho que")
        print(f"      NÃO depende deles: responder no comentário com o produto")
        print(f"      nomeado + endereço curto do site.")
    elif okz and faltam:
        print(f"   📌 MISTO: {len(okz)} conta(s) com escopo, {len(faltam)} sem.")
        print(f"      Não é App Review do app inteiro — é concessão por conta.")
        print(f"      Começa ligando a DM só onde já dá: {', '.join(okz)}")
    elif okz:
        print(f"   📌 NÃO É APP REVIEW — o escopo está lá em {len(okz)} conta(s).")
        print(f"      A DM falha por outro motivo. Rode com --tentar: o `code`")
        print(f"      do erro de envio diz qual, e aí é conserto nosso.")
    else:
        print(f"   📌 Sem conta com token utilizável — o problema é anterior")
        print(f"      à permissão (contas.json ou .env).")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
