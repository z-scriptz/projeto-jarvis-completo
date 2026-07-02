# integrations/telegram_radar.py
# RADAR DE TENDÊNCIAS — lê o TEXTO de grupos de achadinhos no Telegram pra
# descobrir quais produtos estão em alta, e gera o SEU link de afiliado pra eles.
#
# O que faz e NÃO faz:
#   ✅ Lê o TEXTO das mensagens (nome do produto + link no texto)
#   ✅ Gera o SEU link de afiliado (sua comissão, seu sub-id)
#
# Usa Telethon (conta de usuário) porque bots não leem grupos de terceiros.
# Cuidados pra proteger a conta: pausa entre grupos, limite de mensagens.
#
# Pré-requisitos (em https://my.telegram.org):
#   TELEGRAM_API_ID e TELEGRAM_API_HASH (variáveis de ambiente)
#
# Uso (CLI):
#   python -m integrations.telegram_radar --grupos "@grupo1,@grupo2" --limite 30
#   python -m integrations.telegram_radar --grupos "@grupo1" --gerar-links
#
# Uso (programático — chamado pelo orquestrador no Passo 0):
#   from integrations.telegram_radar import rodar_radar
#   res = rodar_radar(arquivo="grupos.txt", limite=30, gerar_links=True)

import os
import re
import sys
import json
import time
import asyncio
import argparse
from pathlib import Path

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("telegram_radar")

API_ID = os.environ.get("TELEGRAM_API_ID", "")
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")

RADAR_PATH = Path(__file__).parent.parent / "shared" / "content_plans" / "radar_tendencias.json"
SESSAO = str(Path(__file__).parent.parent / "shared" / "telegram_radar.session")

_RE_SHOPEE = re.compile(r"https?://(?:s\.shopee|shopee|shp\.ee)[^\s]+", re.IGNORECASE)


def _telethon_disponivel() -> bool:
    try:
        import telethon  # noqa
        return True
    except Exception:
        return False


def _tem_credenciais() -> bool:
    if not API_ID or not API_HASH:
        log.error("❌ Faltam credenciais. Configure TELEGRAM_API_ID e TELEGRAM_API_HASH")
        log.error("   (pegue em https://my.telegram.org → API development tools)")
        return False
    return True


def _limpar_nome(texto: str) -> str:
    """Remove markdown, emojis e símbolos das bordas, deixando o nome limpo."""
    t = re.sub(r"[*_`]", "", texto)  # markdown
    # remove emojis/símbolos do começo e fim (mantém letras, números, espaço, hífen)
    t = re.sub(r"^[^\w]+", "", t)   # lixo no começo
    t = re.sub(r"[^\w)]+$", "", t)  # lixo no fim (mantém ) pra "3 em 1)")
    return t.strip()


def _fmt_reais(valor) -> str:
    """Formata um número como R$ X,XX (2 casas, vírgula decimal brasileira)."""
    try:
        n = float(valor)
        return f"R$ {n:.2f}".replace(".", ",")
    except (ValueError, TypeError):
        return "R$ 0,00"


def _e_lixo(nome: str) -> bool:
    """Detecta 'nomes' que não são produto de verdade (selos, avisos, links)."""
    n = nome.lower().strip()
    if not n:
        return True
    # selos de venda: "10 mil vendidos", "3 mil vendidos"
    if re.search(r"\bmil\s+vendidos?\b", n):
        return True
    if re.match(r"^\d[\d.\s]*(mil|vendidos?|un|pç|pc)\b", n):
        return True
    # link solto que virou "nome"
    if re.match(r"^https?://", n) or re.match(r"^\w+\.\w+/", n):
        return True
    # genéricos de uma palavra
    if n in ("oferta", "promo", "promoção", "promocao", "achado", "achadinho",
             "achadinhos", "link", "produto", "novo", "estoque", "atualizou",
             "atualizado", "atenção", "atencao", "aviso", "importante", "leia",
             "confira", "corre", "voltou", "última", "ultima", "últimas", "ultimas"):
        return True
    # avisos administrativos do grupo (frases com essas palavras-chave)
    if re.search(r"\b(afiliad[oa]s?|cnpj|cadastr|comiss[ãa]o\s+extra|"
                 r"grupo|canal|inscrev|regras|aviso|administ|divulga)\b", n):
        return True
    # texto majoritariamente em CAIXA ALTA e curto costuma ser aviso, não produto
    # (avalia no texto ORIGINAL, não no lower)
    return False


def _e_aviso_caixa_alta(texto_original: str) -> bool:
    """Linha quase toda em CAIXA ALTA e curta = aviso do grupo, não produto."""
    t = texto_original.strip()
    letras = [c for c in t if c.isalpha()]
    if len(letras) < 4:
        return True
    maiusculas = sum(1 for c in letras if c.isupper())
    # >80% maiúsculas E poucas palavras → aviso (ex: "ATENÇÃO AFILIADOS")
    if maiusculas / len(letras) > 0.8 and len(t.split()) <= 4:
        return True
    return False


def _extrair_produto_do_texto(texto: str) -> dict:
    """
    Extrai nome do produto + link Shopee.
    SÓ considera produto se a mensagem tiver link da Shopee — assim ignora
    anúncios, avisos do grupo, spam de outras plataformas, etc.
    """
    # 1º filtro: tem link da Shopee? Se não, NÃO é um achado (ignora)
    m = _RE_SHOPEE.search(texto or "")
    if not m:
        return {"nome": "", "link_deles": ""}

    linhas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    nome = ""
    for l in linhas:
        if _RE_SHOPEE.search(l):
            continue
        l_limpa = _limpar_nome(l)
        if l.startswith("#") or len(l_limpa) < 4:
            continue
        if re.match(r"^R\$?\s*\d", l_limpa) or l_limpa.lower().startswith("comiss"):
            continue
        # ignora propaganda em inglês (trade, market, etc)
        if re.search(r"\b(trade|market|invest|crypto|bet|casino)\b", l_limpa.lower()):
            continue
        # ignora selos de venda, links soltos, avisos administrativos
        if _e_lixo(l_limpa):
            continue
        # ignora avisos em CAIXA ALTA curtos ("ATUALIZOU", "ATENÇÃO AFILIADOS")
        if _e_aviso_caixa_alta(l):
            continue
        nome = l_limpa
        break
    return {"nome": nome, "link_deles": m.group(0)}


async def _ler_grupos(grupos: list, limite: int, pausa: float) -> list:
    from telethon import TelegramClient
    achados = []
    async with TelegramClient(SESSAO, int(API_ID), API_HASH) as client:
        for i, grupo in enumerate(grupos, 1):
            grupo = grupo.strip()
            if not grupo:
                continue
            log.info(f"   [{i}/{len(grupos)}] lendo {grupo}...")
            try:
                count = 0
                async for msg in client.iter_messages(grupo, limit=limite):
                    texto = msg.message or ""
                    if not texto:
                        continue
                    info = _extrair_produto_do_texto(texto)
                    if info["nome"]:
                        achados.append({
                            "nome": info["nome"],
                            "link_deles": info["link_deles"],
                            "grupo": grupo,
                            "data": str(msg.date) if msg.date else "",
                        })
                        count += 1
                log.info(f"      → {count} produtos encontrados")
            except Exception as e:
                log.warning(f"      ⚠️  erro lendo {grupo}: {str(e)[:60]}")
            if i < len(grupos) and pausa > 0:
                await asyncio.sleep(pausa)   # não bloqueia o event loop do Telethon
    return achados


def _dedup(achados: list) -> list:
    vistos = set()
    unicos = []
    for a in achados:
        chave = a["nome"].lower().strip()
        if chave and chave not in vistos:
            vistos.add(chave)
            unicos.append(a)
    return unicos


def _gerar_meus_links(achados: list, pausa: float = 1.0) -> list:
    try:
        from integrations.shopee_affiliate import minerar_oportunidades, gerar_link_afiliado
    except Exception:
        log.warning("   Shopee indisponível — radar só lista (sem gerar links)")
        return achados
    for i, a in enumerate(achados, 1):
        log.info(f"   [{i}/{len(achados)}] minerando '{a['nome'][:40]}'...")
        try:
            m = minerar_oportunidades(a["nome"])
            if m.get("ok"):
                camp = m["campeao"]
                origem = camp.get("product_link") or camp.get("offer_link")
                if origem:
                    sub = ["radar", re.sub(r"\W+", "", a["nome"])[:12]]
                    lk = gerar_link_afiliado(origem, sub_ids=sub)
                    if lk.get("ok"):
                        a["meu_link"] = lk["short_link"]
                        a["campeao"] = camp.get("nome", "")
                        a["comissao_valor"] = camp.get("comissao_valor", 0)
                        a["vendas"] = camp.get("vendas", 0)
                        a["rating"] = camp.get("rating", 0)
            else:
                a["meu_link"] = ""
                a["motivo"] = "sem mina de ouro"
        except Exception as e:
            log.warning(f"      ⚠️  {str(e)[:50]}")
            a["meu_link"] = ""
        time.sleep(pausa)
    return achados


def _carregar_grupos_de_arquivo(caminho: str) -> list:
    """Lê grupos de um .txt — um por linha, ignora linhas vazias e # comentários."""
    p = Path(caminho)
    if not p.exists():
        log.error(f"❌ Arquivo de grupos não encontrado: {caminho}")
        return []
    grupos = []
    for linha in p.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        grupos.append(linha)
    return grupos


def _salvar_radar(achados: list) -> bool:
    """Escrita atômica do radar_tendencias.json (tmp → replace)."""
    tmp = RADAR_PATH.with_suffix(".json.tmp")
    try:
        RADAR_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"total": len(achados), "produtos": achados}, f,
                      ensure_ascii=False, indent=2)
        tmp.replace(RADAR_PATH)
        return True
    except Exception as e:
        log.error(f"erro salvando radar: {e}")
        try:
            tmp.unlink()
        except Exception:
            pass
        return False


# =====================================================================
# API PROGRAMÁTICA — usada pelo orquestrador (Passo 0)
# =====================================================================
def rodar_radar(grupos=None, arquivo: str = "", limite: int = 30,
                gerar_links: bool = True, pausa: float = 2.0) -> dict:
    """
    Roda o radar de ponta a ponta e salva o radar_tendencias.json.

    Args:
        grupos:      lista ["@g1","@g2"] OU string "@g1,@g2"
                     (ignorado se 'arquivo' for informado)
        arquivo:     caminho .txt com 1 grupo por linha (tem prioridade)
        limite:      mensagens por grupo
        gerar_links: se True, minera Shopee e gera o TEU link de afiliado
        pausa:       pausa (seg) entre grupos pra proteger a conta

    Returns:
        {ok, total, com_link, produtos, arquivo}  em sucesso
        {ok: False, erro}                          em falha
    """
    import asyncio

    if not _telethon_disponivel():
        return {"ok": False, "erro": "telethon não instalado"}
    if not _tem_credenciais():
        return {"ok": False, "erro": "credenciais ausentes (TELEGRAM_API_ID/HASH)"}

    # Resolve a fonte dos grupos: 'arquivo' tem prioridade
    if arquivo:
        grupos = _carregar_grupos_de_arquivo(arquivo)
    elif isinstance(grupos, str):
        grupos = [g.strip() for g in grupos.split(",") if g.strip()]
    grupos = [g for g in (grupos or []) if g]
    if not grupos:
        return {"ok": False, "erro": "nenhum grupo informado"}

    try:
        achados = asyncio.run(_ler_grupos(grupos, limite, pausa))
        achados = _dedup(achados)
        if gerar_links:
            achados = _gerar_meus_links(achados)
        if not _salvar_radar(achados):
            return {"ok": False, "erro": "falha ao salvar radar_tendencias.json"}
        com_link = sum(1 for a in achados if a.get("meu_link"))
        log.info(f"💾 Radar salvo: {RADAR_PATH} "
                 f"({len(achados)} produtos, {com_link} com teu link)")
        return {"ok": True, "total": len(achados), "com_link": com_link,
                "produtos": achados, "arquivo": str(RADAR_PATH)}
    except Exception as e:
        log.error(f"erro no radar: {e}")
        return {"ok": False, "erro": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Radar de tendências do Telegram")
    parser.add_argument("--grupos", default="", help="@grupo1,@grupo2")
    parser.add_argument("--arquivo", default="", help="arquivo .txt com 1 grupo por linha")
    parser.add_argument("--limite", type=int, default=30, help="msgs por grupo (padrão 30)")
    parser.add_argument("--gerar-links", action="store_true", dest="gerar_links",
                        help="Gera o TEU link de afiliado")
    parser.add_argument("--pausa", type=float, default=2.0, help="pausa entre grupos")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("📡 RADAR DE TENDÊNCIAS — TopShop")
    log.info("=" * 60)

    if not _telethon_disponivel():
        log.error("❌ Telethon não instalado. Rode: pip install telethon")
        return 1
    if not _tem_credenciais():
        return 1

    # Fonte dos grupos: --arquivo tem prioridade; senão --grupos
    if args.arquivo:
        grupos = _carregar_grupos_de_arquivo(args.arquivo)
        if not grupos:
            return 1
    elif args.grupos:
        grupos = [g for g in args.grupos.split(",") if g.strip()]
    else:
        parser.error("informe --grupos \"@g1,@g2\" ou --arquivo grupos.txt")

    log.info(f"📡 Lendo {len(grupos)} grupo(s), {args.limite} msgs cada...")

    # Reusa a MESMA lógica que o orquestrador chama (fonte única de verdade)
    res = rodar_radar(grupos=grupos, limite=args.limite,
                      gerar_links=args.gerar_links, pausa=args.pausa)
    if not res.get("ok"):
        log.error(f"❌ Radar não concluiu: {res.get('erro')}")
        return 1

    achados = res["produtos"]
    log.info(f"🔍 {len(achados)} produtos únicos encontrados")

    print("\n" + "=" * 60)
    print("📡 PRODUTOS EM ALTA NOS GRUPOS")
    print("=" * 60)
    for i, a in enumerate(achados, 1):
        print(f"\n  {i}. {a['nome'][:50]}")
        print(f"     grupo: {a['grupo']}")
        if a.get("meu_link"):
            print(f"     🔗 TEU link: {a['meu_link']}")
            print(f"     💰 {_fmt_reais(a.get('comissao_valor',0))} comissão | "
                  f"{a.get('vendas',0)} vendas | {a.get('rating',0)}⭐")
        elif args.gerar_links:
            print(f"     ⏭️  {a.get('motivo','sem link')}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())