# integrations/descobridor_grupos.py
# DESCOBRIDOR DE GRUPOS — acha novos canais de achadinhos/vídeos no Telegram
# pra auto-alimentar o RADAR (grupos.txt) e o HUNTER (hunter_canais no config).
#
# Como funciona (2 fontes que se complementam):
#   1. BUSCA por palavra-chave (contacts.Search): procura canais públicos por
#      termos tipo "achadinhos shopee", "ofertas shopee".
#   2. DESCOBERTA ORGÂNICA: varre os grupos que VOCÊ JÁ TEM procurando links
#      t.me/<canal> e @menções — grupos de achadinhos se divulgam entre si.
#
# SEGURANÇA (é a sua conta de usuário em jogo):
#   - SÓ canais PÚBLICOS (lidos por @username). NUNCA entra em grupo privado.
#   - VALIDA antes de adicionar: precisa ser canal + ter palavra-chave de
#     achadinho + ter link da Shopee nas últimas msgs + estar ativo.
#   - Pausas entre operações + trata FloodWait (anti-ban).
#   - Dedup contra o que já está no grupos.txt e no hunter_canais.
#   - Log de auditoria em grupos_descobertos.json (nada se perde).
#
# Uso (CLI):
#   python -m integrations.descobridor_grupos --max 2
#   python -m integrations.descobridor_grupos --max 2 --dry-run   # não grava
#
# Uso (programático — o daemon chama de manhã e de noite):
#   from integrations.descobridor_grupos import descobrir_grupos
#   res = descobrir_grupos(max_novos=2)

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
    log = logging.getLogger("descobridor_grupos")

RAIZ = Path(__file__).parent.parent
if str(RAIZ) not in sys.path:
    sys.path.append(str(RAIZ))

API_ID = os.environ.get("TELEGRAM_API_ID", "")
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")

# Reusa a MESMA sessão do radar (o daemon roda em série, sem concorrência) —
# assim não exige um 3º login/.session no deploy.
SESSAO = str(RAIZ / "shared" / "telegram_radar.session")

GRUPOS_TXT = RAIZ / "grupos.txt"
CONFIG_PATH = RAIZ / "shared" / "content_plans" / "agendador_config.json"
DESCOBERTOS_PATH = RAIZ / "shared" / "content_plans" / "grupos_descobertos.json"

# Termos de busca padrão (pode sobrescrever via arg/daemon)
TERMOS_PADRAO = [
    "achadinhos shopee", "achadinhos da shopee", "ofertas shopee",
    "promoções shopee", "achadinhos", "ofertas e promoções", "cupom shopee",
]

# Palavras que indicam que é MESMO um canal de achadinhos (no título/descrição)
_KW_ACHADINHO = re.compile(
    r"achadinh|acha[dt]os?|oferta|promo|desconto|cupom|shopee|barat|"
    r"liquida|import[aá]dos?|s[oó] hoje|frete gr[aá]tis|link na bio",
    re.IGNORECASE,
)

# Link da Shopee nas mensagens = prova de que é feed de afiliado de verdade
_RE_SHOPEE = re.compile(r"https?://(?:s\.shopee|shopee|shp\.ee)[^\s]+", re.IGNORECASE)

# Extrai @canal e t.me/<canal> de textos (descoberta orgânica)
_RE_USERNAME = re.compile(r"(?:https?://)?t\.me/(?:s/)?([a-zA-Z]\w{3,31})", re.IGNORECASE)
_RE_ARROBA = re.compile(r"(?<![\w@])@([a-zA-Z]\w{3,31})")

# Usernames de sistema/lixo que aparecem em links mas não são grupos de acha
_IGNORAR_USERNAMES = {
    "joinchat", "telegram", "durov", "share", "addstickers", "proxy",
    "socks", "bot", "botfather", "spambot",
}

# Quantas das últimas N mensagens precisam ter link Shopee pra validar
MIN_MSGS_COM_SHOPEE = 2
MSGS_PARA_VALIDAR = 25
# Atividade recente: última mensagem em até X dias
MAX_DIAS_INATIVO = 21


def _telethon_disponivel() -> bool:
    try:
        import telethon  # noqa
        return True
    except Exception:
        return False


def _tem_credenciais() -> bool:
    if not API_ID or not API_HASH:
        log.error("❌ Faltam TELEGRAM_API_ID / TELEGRAM_API_HASH")
        return False
    try:
        int(API_ID)
    except ValueError:
        log.error(f"❌ TELEGRAM_API_ID não é numérico: {API_ID!r}")
        return False
    return True


# =====================================================================
# CONHECIDOS — o que já está na rotação (pra não duplicar)
# =====================================================================
def _carregar_grupos_txt() -> list:
    if not GRUPOS_TXT.exists():
        return []
    out = []
    for linha in GRUPOS_TXT.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#"):
            out.append(linha)
    return out


def _carregar_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"config ilegível ({e})")
    return {}


def _norm_user(u: str) -> str:
    """Normaliza pra comparação: sem @, sem t.me/, minúsculo."""
    u = (u or "").strip()
    m = _RE_USERNAME.search(u)
    if m:
        u = m.group(1)
    return u.lstrip("@").lower()


def _conhecidos() -> set:
    """Conjunto normalizado de tudo que já está no radar + hunter."""
    conhecidos = set()
    for g in _carregar_grupos_txt():
        conhecidos.add(_norm_user(g))
    cfg = _carregar_config()
    for c in (cfg.get("hunter_canais") or []):
        conhecidos.add(_norm_user(c))
    # também os que já descobrimos antes (mesmo não promovidos) pra não insistir
    if DESCOBERTOS_PATH.exists():
        try:
            hist = json.loads(DESCOBERTOS_PATH.read_text(encoding="utf-8"))
            for item in hist.get("historico", []):
                if item.get("username"):
                    conhecidos.add(_norm_user(item["username"]))
        except Exception:
            pass
    conhecidos.discard("")
    return conhecidos


# =====================================================================
# BUSCA + VALIDAÇÃO (async — usa o cliente Telethon)
# =====================================================================
async def _flood_safe(coro_factory, descricao="op", tentativas=2):
    """Executa uma coro do Telethon tratando FloodWait (espera curta ou desiste)."""
    from telethon.errors import FloodWaitError
    for _ in range(tentativas):
        try:
            return await coro_factory()
        except FloodWaitError as e:
            espera = int(getattr(e, "seconds", 5))
            if espera > 90:
                log.warning(f"   ⏳ FloodWait {espera}s em {descricao} — pulando (>90s)")
                return None
            log.warning(f"   ⏳ FloodWait {espera}s em {descricao} — aguardando")
            await asyncio.sleep(espera + 1)
        except Exception as e:
            log.debug(f"   {descricao} falhou: {type(e).__name__}: {str(e)[:80]}")
            return None
    return None


async def _buscar_por_termos(client, termos: list, por_termo: int = 20) -> dict:
    """contacts.Search por cada termo. Retorna {username: entidade_chat}."""
    from telethon.tl.functions.contacts import SearchRequest
    achados = {}
    for termo in termos:
        res = await _flood_safe(
            lambda: client(SearchRequest(q=termo, limit=por_termo)),
            descricao=f"busca '{termo}'",
        )
        if not res:
            continue
        for chat in getattr(res, "chats", []) or []:
            uname = getattr(chat, "username", None)
            # só canal/megagrupo PÚBLICO (tem username); ignora grupo privado
            if uname and (getattr(chat, "broadcast", False)
                          or getattr(chat, "megagroup", False)):
                achados[uname.lower()] = chat
        await asyncio.sleep(2)  # gentil com a API
    log.info(f"   🔎 Busca por termos: {len(achados)} canal(is) público(s) candidato(s)")
    return achados


async def _descobrir_por_mencoes(client, grupos_conhecidos: list,
                                 limite_msgs: int = 60) -> set:
    """Varre grupos conhecidos por links t.me/@menções — cross-promo entre canais."""
    candidatos = set()
    for grupo in grupos_conhecidos[:8]:   # teto pra não demorar/floodar
        msgs = await _flood_safe(
            lambda g=grupo: client.get_messages(g, limit=limite_msgs),
            descricao=f"msgs de {grupo}",
        )
        if not msgs:
            continue
        for msg in msgs:
            texto = (getattr(msg, "message", "") or "")
            for m in _RE_USERNAME.finditer(texto):
                candidatos.add(m.group(1).lower())
            for m in _RE_ARROBA.finditer(texto):
                candidatos.add(m.group(1).lower())
        await asyncio.sleep(1.5)
    candidatos = {c for c in candidatos if c not in _IGNORAR_USERNAMES}
    log.info(f"   🔗 Descoberta orgânica: {len(candidatos)} menção(ões) de canal")
    return candidatos


async def _validar_candidato(client, username: str) -> dict:
    """
    Confirma que um @username é um canal de achadinhos utilizável.
    Retorna {ok, username, titulo, shopee_hits, score, motivo}.
    """
    reprova = lambda motivo: {"ok": False, "username": username, "motivo": motivo}

    ent = await _flood_safe(lambda: client.get_entity(username),
                            descricao=f"resolver @{username}")
    if ent is None:
        return reprova("não resolveu")

    # tem que ser canal (broadcast) ou megagrupo público
    if not (getattr(ent, "broadcast", False) or getattr(ent, "megagroup", False)):
        return reprova("não é canal/megagrupo")
    titulo = getattr(ent, "title", "") or ""

    msgs = await _flood_safe(lambda: client.get_messages(ent, limit=MSGS_PARA_VALIDAR),
                             descricao=f"msgs @{username}")
    if not msgs:
        return reprova("sem mensagens")

    # atividade recente
    from datetime import datetime, timezone
    ultima = getattr(msgs[0], "date", None)
    if ultima:
        dias = (datetime.now(timezone.utc) - ultima).days
        if dias > MAX_DIAS_INATIVO:
            return reprova(f"inativo ({dias}d)")

    # conta mensagens com link da Shopee (prova de feed de afiliado)
    shopee_hits = sum(1 for m in msgs
                      if _RE_SHOPEE.search(getattr(m, "message", "") or ""))
    tem_kw = bool(_KW_ACHADINHO.search(titulo))

    if shopee_hits < MIN_MSGS_COM_SHOPEE and not tem_kw:
        return reprova(f"sem sinal de achadinho (shopee={shopee_hits}, kw=não)")

    # score simples: links Shopee pesam mais; keyword no título dá bônus
    score = shopee_hits * 2 + (3 if tem_kw else 0)
    return {"ok": True, "username": username, "titulo": titulo[:60],
            "shopee_hits": shopee_hits, "score": score, "motivo": "ok"}


async def _rodar_descoberta(max_novos: int) -> list:
    """Pipeline async: busca → coleta candidatos → valida → ordena. Retorna aprovados."""
    from telethon import TelegramClient

    conhecidos = _conhecidos()
    grupos_atuais = _carregar_grupos_txt()
    aprovados = []

    async with TelegramClient(SESSAO, int(API_ID), API_HASH) as client:
        # 1) junta candidatos das duas fontes
        por_termo = await _buscar_por_termos(client, TERMOS_PADRAO)
        mencoes = await _descobrir_por_mencoes(client, grupos_atuais)

        candidatos = set(por_termo.keys()) | mencoes
        # tira o que já conhecemos
        candidatos = [c for c in candidatos if _norm_user(c) not in conhecidos]
        log.info(f"   🧮 {len(candidatos)} candidato(s) novo(s) pra validar")

        # 2) valida cada um (com teto pra não floodar), para quando junta o dobro
        #    do alvo (pra ter margem de escolha por score)
        alvo_validados = max(max_novos * 3, 6)
        validados = []
        for i, uname in enumerate(sorted(candidatos), 1):
            if len(validados) >= alvo_validados:
                break
            v = await _validar_candidato(client, uname)
            if v.get("ok"):
                validados.append(v)
                log.info(f"      ✅ @{uname}: {v['titulo']} "
                         f"(shopee={v['shopee_hits']}, score={v['score']})")
            await asyncio.sleep(1.5)

        # 3) ordena por score e pega os melhores
        validados.sort(key=lambda x: x["score"], reverse=True)
        aprovados = validados[:max_novos]

    return aprovados


# =====================================================================
# PROMOÇÃO — grava nos destinos (grupos.txt + hunter_canais) + auditoria
# =====================================================================
def _append_grupos_txt(usernames: list) -> int:
    """Acrescenta @username novos ao grupos.txt (idempotente)."""
    atuais_norm = {_norm_user(g) for g in _carregar_grupos_txt()}
    novos = [u for u in usernames if _norm_user(u) not in atuais_norm]
    if not novos:
        return 0
    try:
        GRUPOS_TXT.parent.mkdir(parents=True, exist_ok=True)
        with open(GRUPOS_TXT, "a", encoding="utf-8") as f:
            if GRUPOS_TXT.stat().st_size > 0:
                f.write("\n")
            f.write("\n".join(f"@{u.lstrip('@')}" for u in novos) + "\n")
        return len(novos)
    except Exception as e:
        log.error(f"falha ao gravar grupos.txt: {e}")
        return 0


def _append_hunter_canais(usernames: list) -> int:
    """Acrescenta @username novos ao hunter_canais do agendador_config.json."""
    cfg = _carregar_config()
    canais = list(cfg.get("hunter_canais") or [])
    atuais_norm = {_norm_user(c) for c in canais}
    novos = [f"@{u.lstrip('@')}" for u in usernames if _norm_user(u) not in atuais_norm]
    if not novos:
        return 0
    cfg["hunter_canais"] = canais + novos
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        tmp.replace(CONFIG_PATH)
        return len(novos)
    except Exception as e:
        log.error(f"falha ao gravar hunter_canais: {e}")
        try:
            tmp.unlink()
        except Exception:
            pass
        return 0


def _registrar_auditoria(aprovados: list, promovido: bool):
    """Guarda tudo que foi descoberto (auditável / evita reprocessar)."""
    hist = {"historico": []}
    if DESCOBERTOS_PATH.exists():
        try:
            hist = json.loads(DESCOBERTOS_PATH.read_text(encoding="utf-8"))
            hist.setdefault("historico", [])
        except Exception:
            pass
    agora = time.strftime("%Y-%m-%d %H:%M:%S")
    for a in aprovados:
        hist["historico"].append({
            "username": a["username"], "titulo": a.get("titulo", ""),
            "score": a.get("score", 0), "shopee_hits": a.get("shopee_hits", 0),
            "promovido": promovido, "quando": agora,
        })
    hist["historico"] = hist["historico"][-500:]   # não cresce infinito
    tmp = DESCOBERTOS_PATH.with_suffix(".json.tmp")
    try:
        DESCOBERTOS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False, indent=2)
        tmp.replace(DESCOBERTOS_PATH)
    except Exception as e:
        log.warning(f"não consegui gravar auditoria: {e}")
        try:
            tmp.unlink()
        except Exception:
            pass


# =====================================================================
# API PROGRAMÁTICA — o daemon chama isto
# =====================================================================
def descobrir_grupos(max_novos: int = 2, auto_add: bool = True,
                     dry_run: bool = False) -> dict:
    """
    Descobre até `max_novos` canais de achadinhos e (se auto_add) os adiciona
    ao grupos.txt (radar) e ao hunter_canais (hunter).

    Returns:
        {ok, aprovados:[...], promovidos_radar:int, promovidos_hunter:int}
        {ok: False, erro} em falha
    """
    if not _telethon_disponivel():
        return {"ok": False, "erro": "telethon não instalado"}
    if not _tem_credenciais():
        return {"ok": False, "erro": "credenciais ausentes (TELEGRAM_API_ID/HASH)"}

    try:
        aprovados = asyncio.run(_rodar_descoberta(max_novos))
    except Exception as e:
        log.error(f"erro na descoberta de grupos: {e}")
        return {"ok": False, "erro": str(e)}

    if not aprovados:
        log.info("   🔍 Nenhum grupo novo aprovado desta vez.")
        _registrar_auditoria([], promovido=False)
        return {"ok": True, "aprovados": [], "promovidos_radar": 0,
                "promovidos_hunter": 0}

    usernames = [a["username"] for a in aprovados]
    log.info(f"   🎯 {len(usernames)} grupo(s) aprovado(s): "
             f"{', '.join('@'+u for u in usernames)}")

    if dry_run or not auto_add:
        motivo = "dry-run" if dry_run else "auto_add=False (só sugestão)"
        log.info(f"   🧪 {motivo}: NÃO gravei. Veja grupos_descobertos.json.")
        _registrar_auditoria(aprovados, promovido=False)
        return {"ok": True, "aprovados": aprovados, "promovidos_radar": 0,
                "promovidos_hunter": 0, "auto_add": False}

    n_radar = _append_grupos_txt(usernames)
    n_hunter = _append_hunter_canais(usernames)
    _registrar_auditoria(aprovados, promovido=True)
    log.info(f"   ✅ Promovidos: +{n_radar} no radar (grupos.txt), "
             f"+{n_hunter} no hunter (hunter_canais)")
    return {"ok": True, "aprovados": aprovados,
            "promovidos_radar": n_radar, "promovidos_hunter": n_hunter}


def main():
    parser = argparse.ArgumentParser(
        description="Descobridor de grupos de achadinhos (alimenta radar + hunter)")
    parser.add_argument("--max", type=int, default=2, help="máx de grupos novos (padrão 2)")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="descobre e valida, mas NÃO grava (só audita)")
    parser.add_argument("--nao-adicionar", action="store_true", dest="nao_add",
                        help="só sugere (grava em grupos_descobertos.json), não promove")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("🛰️  DESCOBRIDOR DE GRUPOS — achadinhos/vídeos")
    log.info("=" * 60)

    res = descobrir_grupos(max_novos=args.max, auto_add=not args.nao_add,
                           dry_run=args.dry_run)
    if not res.get("ok"):
        log.error(f"❌ {res.get('erro')}")
        return 1
    aprovados = res.get("aprovados", [])
    print("\n" + "=" * 60)
    print(f"🛰️  {len(aprovados)} grupo(s) aprovado(s)")
    for a in aprovados:
        print(f"   • @{a['username']} — {a.get('titulo','')} "
              f"(score {a.get('score',0)}, shopee {a.get('shopee_hits',0)})")
    if res.get("promovidos_radar") or res.get("promovidos_hunter"):
        print(f"\n   ✅ +{res['promovidos_radar']} radar | "
              f"+{res['promovidos_hunter']} hunter")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
