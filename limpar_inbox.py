#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# limpar_inbox.py -- acha no inbox os produtos que ficaram com NOME EM INGLÊS e
# conserta o link antes de virar post.
#
# POR QUE ISSO EXISTE (04/09/2026)
# ────────────────────────────────
# A rodada casou 495 produtos, mas parte deles foi coletada ANTES do prompt
# passar a exigir tradução. Ficaram assim:
#
#   'Corn Kernel Stripper'  → amazon.com.br/s?k=Corn+Kernel+Stripper
#   'Cord wraps' · 'Storage bins' · 'Quilt fixing buckles'
#
# Essa busca não devolve nada na Amazon BR. O post sairia com link que não leva
# a lugar nenhum — pior que não postar, porque queima o clique de quem confiou.
#
# ⚠️ O `_produto_pra_amazon` existe justamente pra barrar isso, mas ele usa
# `_EN_WORDS`, que é lista de palavras FUNCIONAIS e não dicionário: "corn",
# "kernel" e "stripper" não estão lá. Este script é a limpeza do que já passou;
# a defesa em regime é o prompt de tradução (commit dd86451).
#
# Uso (VPS):
#   .venv/bin/python limpar_inbox.py            # só LISTA o que está errado
#   .venv/bin/python limpar_inbox.py --corrigir # traduz e reescreve o link
import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

BASE_DIR = Path(__file__).resolve().parent
INBOX = BASE_DIR / "inbox_tiktok"


def _carregar_env():
    """Sem isto o GEMINI_API_KEY não existe e a tradução falha calada — o mesmo
    defeito que o `dinheiro.py` teve e o `hook_alana` documenta."""
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
        return cand
    return None


# Sinal de "isto não é português". Aqui a régua é DIFERENTE da do coletor, e de
# propósito: lá um falso positivo custava um download; aqui custa nada (só uma
# tradução a mais), e um falso NEGATIVO custa um link morto publicado. Então
# aqui pode ser agressivo.
_PT_MARCAS = re.compile(
    r"[áàâãéêíóôõúüç]"                       # acento
    r"|\b(de|da|do|das|dos|com|sem|para|pra|em|no|na|e)\b"   # função pt
    r"|(ção|ções|dor|dora|eira|eiro|inho|inha|ável|ível)\b",  # sufixo pt
    re.I)


def parece_ingles(termo: str) -> bool:
    """Nenhuma marca de português no termo inteiro → SUSPEITO (não "é inglês").

    ⚠️ ERREI A MEDIÇÃO DISTO, E O NÚMERO REAL É OUTRO (04/09/2026).
    Eu testei com 14 produtos pt-BR e anunciei "3 falsos positivos". Só que
    escolhi a amostra enviesada — quase todos tinham "de" ou acento. No inbox
    de verdade, dos 40 primeiros marcados uns 16 eram português puro:
    'Escada rolante', 'Salva alimentos', 'Zumbi rastejante animado', 'botas
    pantufa Dragon Ball Z', 'dispositivo anti-engasgo'. ~40%, não 21%.

    Por isso esta função virou um PENEIRA, não um juiz: ela só decide quem vai
    ser PERGUNTADO. Quem decide de fato é o Gemini, que responde JA_PT quando o
    termo já está em português — e aí nada é reescrito. É o desenho que
    sustenta o erro da régua, não a régua."""
    t = (termo or "").strip()
    return bool(t) and not _PT_MARCAS.search(t)


def traduzir(termo: str) -> str:
    """Gemini traduz o NOME DO PRODUTO. Devolve '' quando NÃO se deve mexer.

    ⚠️ O MODELO RESPONDE `JA_PT`, NÃO "repita igual". Parece a mesma coisa e
    não é: mandado repetir, o modelo tende a MELHORAR o termo — 'Escada
    rolante' volta 'Esteira rolante', 'Salva alimentos' volta 'Conservador de
    alimentos'. Como ~40% dos marcados são português (a peneira erra muito),
    "melhorar" significaria reescrever dezenas de links que já estavam certos.

    Com JA_PT o modelo tem uma saída explícita pra "não é o meu caso", e
    qualquer resposta diferente disso é tradução de verdade."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return ""
    try:
        from google import genai
        cli = genai.Client(api_key=key)
        r = cli.models.generate_content(
            model="gemini-2.5-flash",
            contents=("Você recebe o nome de um produto. DECIDA:\n"
                      "- Se ele JÁ está em português do Brasil, responda "
                      "exatamente JA_PT. Não melhore, não reescreva, não "
                      "corrija — mesmo que você ache o nome estranho ou "
                      "incompleto.\n"
                      "- Se estiver em outro idioma, responda SÓ com a tradução "
                      "para português do Brasil, como alguém buscaria numa loja "
                      "online (2 a 6 palavras, sem aspas, sem explicar).\n"
                      "- Se não for um produto, responda NAO.\n\n"
                      "Exemplos: 'Meat Tenderizer' → amaciante de carne; "
                      "'Escada rolante' → JA_PT; 'Shower Caddy' → organizador "
                      "de chuveiro; 'Salva alimentos' → JA_PT\n\n"
                      "Produto: " + termo))
        t = (r.text or "").strip().strip('"').split("\n")[0].strip()
        if not t or t.upper().startswith(("NAO", "JA_PT")):
            return ""
        return t[:80]
    except Exception as e:
        print(f"   ⚠️  tradução falhou ({str(e)[:60]})")
        return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="conserta produto em inglês no inbox")
    ap.add_argument("--corrigir", action="store_true",
                    help="traduz e reescreve o link (sem isto, só lista)")
    a = ap.parse_args()

    arq = _carregar_env()
    print(f"📄 .env: {arq or '(não achei — a tradução vai falhar)'}")
    if not INBOX.exists():
        print(f"❌ {INBOX} não existe")
        return 1

    planos = sorted(INBOX.glob("*/plano.json"))
    print(f"📦 {len(planos)} pacote(s) no inbox\n")

    suspeitos = []
    for pj in planos:
        try:
            info = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            continue
        nome = (info.get("produto") or "").strip()
        if parece_ingles(nome):
            suspeitos.append((pj, info, nome))

    if not suspeitos:
        print("✅ nenhum produto com cara de estrangeiro — nada a fazer")
        return 0

    # ⚠️ separa por ONDE o link aponta: o link da Shopee foi casado por
    # sobreposição de palavras com um título pt-BR, então ele é REAL mesmo com
    # o nome estrangeiro. Só a busca da Amazon carrega o termo cru na URL — é
    # essa que morre. Corrigir os dois seria arriscar trocar link que funciona.
    amazon = [s for s in suspeitos if "amazon." in (s[1].get("link_afiliado") or "")]
    outros = [s for s in suspeitos if s not in amazon]

    print(f"⚠️  {len(suspeitos)} SUSPEITOS (a peneira erra ~40% pra mais — "
          f"quem decide é o Gemini):")
    print(f"   🔴 {len(amazon)} com BUSCA AMAZON (o termo vai cru na URL — link morto)")
    print(f"   🟡 {len(outros)} com link de loja já casado (o link funciona, "
          f"só o nome fica feio na legenda)")
    print(f"   ℹ️  nome em português nesta lista é NORMAL — no --corrigir o "
          f"Gemini responde JA_PT e o link não é tocado.\n")

    for pj, info, nome in amazon[:40]:
        print(f"   🔴 {nome[:44]:46} {pj.parent.name[:34]}")
    if len(amazon) > 40:
        print(f"   … e mais {len(amazon) - 40}")

    if not a.corrigir:
        print(f"\n📋 pra corrigir (traduz e reescreve só os 🔴):")
        print(f"   .venv/bin/python limpar_inbox.py --corrigir")
        return 0

    tag = os.getenv("AMAZON_TAG", "").strip()
    dom = os.getenv("AMAZON_DOMAIN", "amazon.com.br").strip() or "amazon.com.br"
    if not tag:
        print("❌ AMAZON_TAG vazio no .env — não sei montar o link. Abortando.")
        return 1

    ok = ja_pt = 0
    print()
    for pj, info, nome in amazon:
        novo = traduzir(nome)
        if not novo or novo.lower() == nome.lower():
            # JA_PT, NAO, ou falha de API — os três significam "não mexo".
            # Distinguir não mudaria o que o script faz, e um contador a mais
            # daria a impressão de que dá pra agir sobre a diferença.
            print(f"   ⏭️  '{nome[:44]}' — já está em pt (ou não deu) · intocado")
            ja_pt += 1
            continue
        info["produto"] = novo
        info["produto_original"] = nome        # rastro: dá pra auditar depois
        info["link_afiliado"] = (f"https://www.{dom}/s?k={quote_plus(novo)}"
                                 f"&tag={tag}")
        pj.write_text(json.dumps(info, ensure_ascii=False, indent=2),
                      encoding="utf-8")
        print(f"   ✅ '{nome[:34]}' → '{novo[:34]}'")
        ok += 1

    print(f"\n✅ {ok} link(s) reescrito(s) · ⏭️  {ja_pt} intocado(s) "
          f"(já em português ou sem tradução)")
    if ja_pt:
        print(f"   📌 os {ja_pt} intocados são a peneira errando — custaram uma "
              f"chamada cada e nenhum link mudou. É o preço de não perder os "
              f"{ok} que estavam quebrados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
