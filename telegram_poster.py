# integrations/telegram_poster.py
# Posta os achados (foto + nome + preço + link de afiliado) num grupo/canal
# do Telegram, usando a API oficial de bots (gratuita e dentro das regras).
#
# Diferente do site (que é estático e o preço desatualiza), no Telegram a
# mensagem é do momento — então mostrar preço faz sentido. Mas é configurável.
#
# Pré-requisitos (você cria no Telegram, via @BotFather):
#   - TELEGRAM_BOT_TOKEN: o token do bot
#   - TELEGRAM_CHAT_ID: o ID do grupo/canal (o bot precisa ser admin)
# Ambos vêm de variáveis de ambiente (segurança: nunca no código).
#
# Uso:
#   python -m integrations.telegram_poster --produto "Cortador de Legumes"
#   python -m integrations.telegram_poster --do-plano   # posta o ultimo_plano.json
#   python -m integrations.telegram_poster --teste      # mensagem de teste

import os
import re
import sys
import json
import time
import argparse
from pathlib import Path

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("telegram_poster")

# Credenciais via ambiente (nunca hardcode!)
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

API_BASE = "https://api.telegram.org/bot{token}/{metodo}"

# Mostrar preço na mensagem? (no Telegram faz sentido, mas configurável)
MOSTRAR_PRECO = True


def _tem_credenciais() -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        log.error("❌ Faltam credenciais. Configure as variáveis de ambiente:")
        log.error("   TELEGRAM_BOT_TOKEN (do @BotFather)")
        log.error("   TELEGRAM_CHAT_ID (o ID do grupo/canal)")
        return False
    return True


def _txt(valor) -> str:
    """Converte qualquer valor (str, float, int, None) em texto limpo, com segurança."""
    if valor is None:
        return ""
    return str(valor).strip()


def _formatar_preco(valor) -> str:
    """
    Formata o preço pra exibição. Aceita:
      - texto já formatado ("R$ 39,90 a R$ 49,90") → usa como está
      - número (39.9) → vira "R$ 39,90"
      - vazio/None → ""
    """
    if valor is None or valor == "":
        return ""
    # já é texto com cifrão? usa como está
    s = str(valor).strip()
    if "R$" in s or "a R$" in s:
        return s
    # tenta tratar como número
    try:
        n = float(str(valor).replace(",", "."))
        return f"R$ {n:.2f}".replace(".", ",")
    except (ValueError, TypeError):
        return s  # não é número nem tem cifrão; devolve o texto cru


def _montar_legenda(produto: dict) -> str:
    """
    Monta o texto do achado em HTML (mais robusto que MarkdownV2 do Telegram,
    que exige escapar dezenas de caracteres como ! . - ( ) e quebra fácil).
    No HTML mode só precisamos escapar < > &.
    """
    titulo = _txt(produto.get("titulo") or produto.get("nome"))
    preco = _formatar_preco(produto.get("preco_real"))
    link = _txt(produto.get("link") or produto.get("link_afiliado"))

    linhas = [f"🛍️ <b>{_escape_html(titulo)}</b>", ""]
    if MOSTRAR_PRECO and preco:
        linhas.append(f"💰 {_escape_html(preco)}")
    linhas.append("🔥 Corre que é por tempo limitado!")
    linhas.append("")
    if link:
        # No HTML mode, link é <a href="url">texto</a>
        linhas.append(f'👉 <a href="{_escape_html(link)}">GARANTIR O MEU</a>')
    return "\n".join(linhas)


def _escape_html(texto: str) -> str:
    """Escapa os 3 caracteres que o HTML mode do Telegram exige: < > &."""
    return (texto.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;"))


def _escape_md(texto: str) -> str:
    """(legado) Escapa caracteres do MarkdownV2 — mantido por compatibilidade."""
    for ch in r"_*[]()~`>#+-=|{}.!":
        texto = texto.replace(ch, f"\\{ch}")
    return texto


def postar_achado(produto: dict) -> dict:
    """
    Posta um achado no grupo do Telegram (foto + legenda + link).
    Se tiver imagem, manda como foto; senão, manda como texto.
    """
    if not _tem_credenciais():
        return {"ok": False, "erro": "sem credenciais"}

    try:
        import requests
    except Exception:
        return {"ok": False, "erro": "biblioteca requests não instalada"}

    legenda = _montar_legenda(produto)
    imagem = _txt(produto.get("imagem"))
    link = _txt(produto.get("link") or produto.get("link_afiliado"))

    if not link:
        return {"ok": False, "erro": "produto sem link de afiliado — não posto"}

    try:
        if imagem:
            # Posta como foto com legenda
            url = API_BASE.format(token=BOT_TOKEN, metodo="sendPhoto")
            payload = {
                "chat_id": CHAT_ID,
                "photo": imagem,
                "caption": legenda,
                "parse_mode": "HTML",
            }
        else:
            # Sem imagem: posta como texto
            url = API_BASE.format(token=BOT_TOKEN, metodo="sendMessage")
            payload = {
                "chat_id": CHAT_ID,
                "text": legenda,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            }
        r = requests.post(url, json=payload, timeout=20)
        data = r.json()
        if data.get("ok"):
            log.info(f"   ✅ postado: {produto.get('nome', '?')}")
            return {"ok": True, "message_id": data["result"].get("message_id")}
        else:
            erro = data.get("description", "erro desconhecido")
            log.error(f"   ❌ Telegram recusou: {erro}")
            return {"ok": False, "erro": erro}
    except Exception as e:
        log.error(f"   ❌ erro ao postar: {e}")
        return {"ok": False, "erro": str(e)}


def postar_varios(produtos: list, pausa: float = 3.0) -> dict:
    """Posta vários achados em sequência (com pausa pra não floodar)."""
    ok = 0
    falhas = 0
    for i, p in enumerate(produtos, 1):
        log.info(f"   [{i}/{len(produtos)}] {p.get('nome', '?')}")
        r = postar_achado(p)
        if r["ok"]:
            ok += 1
        else:
            falhas += 1
        if i < len(produtos) and pausa > 0:
            time.sleep(pausa)
    return {"ok": ok, "falhas": falhas, "total": len(produtos)}


def _enviar_teste() -> dict:
    """Manda uma mensagem de teste pra confirmar que o bot tá funcionando."""
    if not _tem_credenciais():
        return {"ok": False}
    try:
        import requests
        url = API_BASE.format(token=BOT_TOKEN, metodo="sendMessage")
        payload = {"chat_id": CHAT_ID,
                   "text": "✅ Bot da TopShop conectado! Achados chegando em breve 🛍️"}
        r = requests.post(url, json=payload, timeout=20)
        data = r.json()
        if data.get("ok"):
            log.info("✅ Mensagem de teste enviada! O bot tá funcionando.")
            return {"ok": True}
        log.error(f"❌ {data.get('description')}")
        return {"ok": False, "erro": data.get("description")}
    except Exception as e:
        log.error(f"❌ {e}")
        return {"ok": False, "erro": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Posta achados no grupo do Telegram")
    parser.add_argument("--teste", action="store_true",
                        help="Manda uma mensagem de teste pra validar o bot")
    parser.add_argument("--do-plano", action="store_true", dest="do_plano",
                        help="Posta o produto do ultimo_plano.json")
    parser.add_argument("--produto", default="",
                        help="Minera e posta um produto específico")
    parser.add_argument("--sem-preco", action="store_true", dest="sem_preco",
                        help="Não mostra preço na mensagem")
    args = parser.parse_args()

    global MOSTRAR_PRECO
    if args.sem_preco:
        MOSTRAR_PRECO = False

    log.info("=" * 60)
    log.info("📨 TELEGRAM POSTER — TopShop")
    log.info("=" * 60)

    if args.teste:
        return 0 if _enviar_teste()["ok"] else 1

    if args.do_plano:
        caminho = Path(__file__).parent.parent / "shared" / "content_plans" / "ultimo_plano.json"
        try:
            with open(caminho, encoding="utf-8") as f:
                plano = json.load(f)
        except Exception as e:
            log.error(f"❌ erro lendo plano: {e}")
            return 1
        produto = {
            "nome": plano.get("produto", ""),
            "titulo": plano.get("titulo_real") or plano.get("produto", ""),
            "preco_real": plano.get("preco_real", ""),
            "link": plano.get("link_afiliado", ""),
            "imagem": plano.get("imagem", ""),
        }
        r = postar_achado(produto)
        return 0 if r["ok"] else 1

    if args.produto:
        try:
            from integrations.shopee_affiliate import minerar_oportunidades, gerar_link_afiliado
        except Exception as e:
            log.error(f"❌ Shopee indisponível: {e}")
            return 1
        m = minerar_oportunidades(args.produto)
        if not m.get("ok"):
            log.error(f"❌ {m.get('erro')}")
            return 1
        camp = m["campeao"]
        origem = camp.get("product_link") or camp.get("offer_link")
        sub = ["telegram", re.sub(r"\W+", "", args.produto)[:12]]
        lk = gerar_link_afiliado(origem, sub_ids=sub)
        produto = {
            "nome": args.produto,
            "titulo": camp.get("nome", args.produto),
            "preco_real": camp.get("preco", ""),
            "link": lk.get("short_link", "") if lk.get("ok") else "",
            "imagem": camp.get("imagem", ""),
        }
        r = postar_achado(produto)
        return 0 if r["ok"] else 1

    parser.error("use --teste, --do-plano ou --produto")


if __name__ == "__main__":
    sys.exit(main())