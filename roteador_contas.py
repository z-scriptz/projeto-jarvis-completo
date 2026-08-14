#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# roteador_contas.py -- decide EM QUAL conta cada produto vai, pelo nicho.
# Lê contas.json (mapa nicho -> conta) e classifica o produto em DUAS camadas:
#
#   1. PALAVRA-CHAVE  — grátis, instantânea e determinística. Resolve a maioria.
#   2. IA (Gemini)    — só quando a camada 1 não reconhece. Com cache em disco,
#                       então cada produto é perguntado UMA vez na vida.
#
# A ordem importa: keyword primeiro porque é de graça e sempre dá o mesmo
# resultado; a IA entra só no que sobrou, que é onde o dinheiro escapava (produto
# de tech/beleza caindo na conta geral por não estar na lista).
#
# Desligar a camada 2:  ROTEADOR_IA=0 no .env
#
# Uso rápido de teste:
#   python3 roteador_contas.py "Sérum facial com vitamina C"   -> beleza
#   python3 roteador_contas.py "Escova Secadora Rotativa"      -> beleza (via IA)
#   python3 roteador_contas.py --lote produtos.txt             -> tabela
import os
import re
import sys
import json
from pathlib import Path

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    log = logging.getLogger("roteador_contas")

BASE_DIR = Path(__file__).resolve().parent
CONTAS_JSON = BASE_DIR / "contas.json"
CACHE_IA = BASE_DIR / "shared" / "roteador_cache.json"


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
            if k and not os.environ.get(k):
                os.environ[k] = v
        break


_carregar_env()

# ═════════════════════════════════════════════════════════════════════════════
# CAMADA 1 — palavras-chave
# ═════════════════════════════════════════════════════════════════════════════
# Casam no INÍCIO da palavra, então "maquiag" pega "maquiagem"/"maquiador" mas
# "pele" não pega "impeler". Prefixo é proposital em vários termos.
_BELEZA = (
    "beleza", "beauty", "skincare", "maquiag", "makeup", "perfume", "hidratante",
    "batom", "serum", "sérum", "depila", "cilios", "cílios", "sobrancelha",
    "gloss", "cosmetic", "esmalte", "secador de cabelo", "chapinha", "prancha de cabelo",
    "cabelo", "unha", "pele", "labial", "rímel", "rimel", "delineador",
    "autocuidado", "auto cuidado", "estetica", "estética", "modelador", "babyliss",
    "alisador", "necessaire", "nécessaire", "corporal", "facial", "protetor solar",
    "hialuron", "bronzead", "pincéis de maquiagem", "pincel de maquiagem",
    # lacunas que caíam em 'geral' (o motivo desta revisão)
    "escova secadora", "escova alisadora", "escova modeladora", "escova rotativa",
    "massageador facial", "massageador corporal", "limpeza facial", "esfoliante",
    "sabonete facial", "mascara facial", "máscara facial", "mascara capilar",
    "condicionador", "shampoo", "xampu", "leave-in", "ampola capilar",
    "removedor de cravo", "extrator de cravo", "removedor de esmalte",
    "lixa eletrica", "lixa elétrica", "kit manicure", "alicate de unha",
    "cortador de cutícula", "cutícula", "cuticula", "henna", "micropigmenta",
    "lash", "extensao de cilios", "extensão de cílios", "curvex",
    "espelho de maquiagem", "organizador de maquiagem", "paleta de sombra",
    "sombra", "corretivo", "primer", "base liquida", "base líquida", "pó compacto",
    "iluminador", "blush", "contorno facial", "bronzer",
    "creme facial", "creme corporal", "creme para as maos", "creme para as mãos",
    "oleo corporal", "óleo corporal", "oleo capilar", "óleo capilar",
    "depilador", "epilador", "aparador de pelos", "barbeador",
    "escova de dente eletrica", "escova de dente elétrica", "clareador dental",
    "gua sha", "rolo de jade", "dermaroller", "led facial",
    # vistos na fila de producao real
    "cuticle", "clareador", "toner", "tonico facial", "tônico facial",
    "esponja de maquiagem", "esponja para maquiagem", "modelador de cachos",
    "hidratante labial", "balm labial", "mascara de cilios", "máscara de cílios",
    "centella", "acido hialuronico", "ácido hialurônico", "niacinamida",
    "sabonete", "esfoliante corporal", "perfume", "eau de parfum",
)
_TECH = (
    "fone", "headset", "earbud", "carregador", "smartwatch", "smart watch",
    "powerbank", "power bank", "projetor", "drone", "caixa de som", "bluetooth",
    "webcam", "mouse", "teclado", "ring light",
    "gamer", "smart tv", "roteador wi", "ssd", "pendrive", "gadget",
    "celular", "smartphone", "iphone", "android", "telefone", "capinha",
    "capa de celular", "capa de telefone", "capa magnetica", "capa magnética",
    "magsafe", "pelicula", "película", "suporte de celular", "suporte celular",
    "suporte veicular", "cabo usb", "cabo tipo c", "cabo lightning",
    "carregador sem fio", "hub usb", "adaptador usb",
    "games", "gaming", "console", "playstation", "xbox", "nintendo", "joystick",
    "mousepad", "mouse pad", "cadeira gamer", "headset gamer", "notebook", "cooler",
    "placa de video", "placa de vídeo", "controle sem fio", "fone gamer",
    # lacunas que caíam em 'geral'
    "conducao ossea", "condução óssea", "tws", "fone sem fio", "microfone",
    "estabilizador de imagem", "gimbal", "tripé", "tripe", "bastao de selfie",
    "bastão de selfie", "aro de luz", "iluminador led", "softbox",
    "mini projetor", "projetor portatil", "projetor portátil",
    "impressora portatil", "impressora portátil", "scanner",
    "rastreador gps", "airtag", "localizador bluetooth",
    "camera de seguranca", "câmera de segurança", "camera ip", "babá eletrônica",
    "baba eletronica", "fechadura digital", "campainha inteligente",
    "lampada inteligente", "lâmpada inteligente", "tomada inteligente",
    "controle universal", "receptor bluetooth", "transmissor fm",
    "carregador veicular", "suporte notebook", "base para notebook",
    "hd externo", "cartao de memoria", "cartão de memória", "leitor de cartao",
    "caneta touch", "teclado sem fio", "monitor", "kindle", "e-reader",
    "relogio inteligente", "relógio inteligente", "pulseira inteligente",
    "smart band", "oximetro", "oxímetro",
    # vistos na fila de producao real
    "xiaomi", "redmi", "poco x", "motorola", "ipad", "tablet", "airpods",
    "capa antichoque", "capa para iphone", "capa para samsung", "iwo",
)
# 'casa' ainda NÃO tem conta própria no contas.json — classificar aqui só serve
# pra medir o volume e decidir se vale abrir a quarta conta. Sem conta, cai em geral.
_CASA = (
    "organizador", "cesto", "cabide", "porta-tempero", "porta tempero",
    "panela", "frigideira", "assadeira", "tábua de corte", "tabua de corte",
    "utensilio de cozinha", "utensílio de cozinha", "escorredor", "pote hermetico",
    "pote hermético", "lixeira", "rodo", "vassoura", "esfregao", "esfregão",
    "mop", "aspirador", "varal", "cabideiro", "prateleira", "suporte de parede",
    "toalha", "jogo de cama", "lencol", "lençol", "edredom", "cortina", "tapete",
    "almofada", "luminaria de mesa", "luminária de mesa", "abajur",
    "descascador", "ralador", "abridor", "dispenser", "saboneteira",
    "porta-escova", "chuveiro", "ducha", "tapete de banheiro",
    "umidificador", "difusor de aroma", "aromatizador", "vela aromatica",
    "vela aromática", "purificador de ar", "desumidificador",
    # vistos na fila de producao real
    "luminaria", "luminária", "taça", "taca", "xicara", "xícara",
    "porta treco", "porta-treco", "garrafa termica", "garrafa térmica",
    "jogo de copos", "jogo de tacas", "jogo de taças", "bandeja",
)

_NICHOS_VALIDOS = ("beleza", "tech", "casa", "geral")


def _sem_acento(s: str) -> str:
    return (s or "").translate(str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc"))


def _compilar(palavras) -> re.Pattern:
    """Casa no início da palavra: 'pele' pega 'pele/peles', não 'impeler'."""
    alternativas = sorted((_sem_acento(p.lower()) for p in palavras), key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(re.escape(p) for p in alternativas) + r")")


_RX_BELEZA = _compilar(_BELEZA)
_RX_TECH = _compilar(_TECH)
_RX_CASA = _compilar(_CASA)


def _por_palavra_chave(texto: str) -> str:
    """Nicho pela lista, ou "" quando nenhuma bate."""
    if _RX_BELEZA.search(texto):
        return "beleza"
    if _RX_TECH.search(texto):
        return "tech"
    if _RX_CASA.search(texto):
        return "casa"
    return ""


# ═════════════════════════════════════════════════════════════════════════════
# CAMADA 2 — IA, só pro que a lista não reconheceu
# ═════════════════════════════════════════════════════════════════════════════
def _ia_ligada() -> bool:
    return os.getenv("ROTEADOR_IA", "1").strip().lower() in ("1", "true", "sim")


def _ler_cache() -> dict:
    try:
        return json.loads(CACHE_IA.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _gravar_cache(cache: dict):
    try:
        CACHE_IA.parent.mkdir(parents=True, exist_ok=True)
        CACHE_IA.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    except Exception as erro:
        log.warning("não consegui gravar o cache do roteador: %s", str(erro)[:120])


def _chave_cache(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()[:120]


def _por_ia(texto: str) -> str:
    """Pergunta o nicho pro Gemini. Cacheia por produto — cada nome é perguntado
    uma vez só. Devolve "" se a IA estiver desligada, sem chave ou se falhar."""
    if not _ia_ligada():
        return ""

    chave = _chave_cache(texto)
    cache = _ler_cache()
    if chave in cache:
        return cache[chave]

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        log.warning("GEMINI_API_KEY ausente — roteamento fica só nas palavras-chave")
        return ""

    try:
        from google import genai
        cli = genai.Client(api_key=api_key)
        prompt = (
            "Classifique o produto abaixo em UM destes nichos, respondendo APENAS "
            "a palavra, em minusculas, sem pontuacao:\n"
            "- beleza  (cuidado pessoal, cabelo, pele, unhas, maquiagem, perfume)\n"
            "- tech    (eletronicos, celular e acessorios, audio, games, gadgets)\n"
            "- casa    (cozinha, organizacao, limpeza, cama/mesa/banho, decoracao)\n"
            "- geral   (qualquer outra coisa, ou se ficar em duvida)\n\n"
            "Na duvida entre dois, escolha o uso PRINCIPAL do produto.\n\n"
            f"Produto: {texto[:200]}\n"
        )
        r = cli.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"parts": [{"text": prompt}]}],
        )
        bruto = (getattr(r, "text", "") or "").strip().lower()
        achado = ""
        for n in _NICHOS_VALIDOS:
            if n in bruto:
                achado = n
                break
        if not achado:
            log.warning("IA devolveu nicho irreconhecivel (%r) para %r", bruto[:40], chave)
            return ""

        cache[chave] = achado
        _gravar_cache(cache)
        return achado
    except Exception as erro:
        log.warning("IA falhou no roteamento (%s: %s) — fica nas palavras-chave",
                    type(erro).__name__, str(erro)[:140])
        return ""


# ═════════════════════════════════════════════════════════════════════════════
def carregar_contas() -> dict:
    try:
        return json.loads(CONTAS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"_default": {
            "nicho": "geral",
            "handle": os.environ.get("TOPSHOP_HANDLE", "@topshop.__"),
            "instagram_user_id": os.environ.get("INSTAGRAM_USER_ID", ""),
            "facebook_page_id": os.environ.get("FACEBOOK_PAGE_ID", ""),
            "page_token_env": "FACEBOOK_PAGE_TOKEN",
            "youtube": "",
        }}


def nicho_do_produto_detalhado(nome: str, categoria: str = "") -> tuple:
    """(nicho, quem_decidiu) — 'palavra-chave', 'ia' ou 'padrao'."""
    texto = _sem_acento(f"{categoria} {nome}".lower())

    nicho = _por_palavra_chave(texto)
    if nicho:
        return nicho, "palavra-chave"

    nicho = _por_ia(texto)
    if nicho:
        return nicho, "ia"

    return "geral", "padrao"


def nicho_do_produto(nome: str, categoria: str = "") -> str:
    return nicho_do_produto_detalhado(nome, categoria)[0]


def conta_do_produto(nome: str, categoria: str = "") -> dict:
    """Retorna a conta (dict) do nicho do produto, com o token JÁ resolvido do
    .env (campo 'token'). Cai no _default se o nicho não tiver conta."""
    contas = carregar_contas()
    nicho, quem = nicho_do_produto_detalhado(nome, categoria)

    escolhida = contas.get(nicho)
    if escolhida is None and nicho != "geral":
        # nicho reconhecido mas sem conta própria (hoje: 'casa'). Vai pra geral,
        # mas fica no log — é esse volume que justifica abrir uma conta nova.
        log.info("nicho '%s' (via %s) não tem conta própria — indo pra geral: %r",
                 nicho, quem, nome[:60])
    conta = dict(escolhida or contas.get("_default") or {})
    conta.setdefault("nicho", nicho)
    conta["nicho_detectado"] = nicho
    conta["decidido_por"] = quem

    env = conta.get("page_token_env", "")
    conta["token"] = os.environ.get(env, "") if env else ""
    return conta


def conta_para_json(conta: dict) -> dict:
    """Só o que o meta_uploader precisa ao lado do vídeo — SEM o token (fica no
    .env; o uploader resolve pelo page_token_env)."""
    return {
        "nicho": conta.get("nicho", "geral"),
        "handle": conta.get("handle", ""),
        "instagram_user_id": conta.get("instagram_user_id", ""),
        "facebook_page_id": conta.get("facebook_page_id", ""),
        "page_token_env": conta.get("page_token_env", ""),
        "youtube": conta.get("youtube", ""),
    }


def main():
    args = sys.argv[1:]

    if args and args[0] == "--lote":
        caminho = Path(args[1]) if len(args) > 1 else None
        if not caminho or not caminho.exists():
            print("uso: python3 roteador_contas.py --lote produtos.txt")
            return 1
        produtos = [l.strip() for l in caminho.read_text(encoding="utf-8").splitlines()
                    if l.strip() and not l.startswith("#")]
        print(f"{'PRODUTO':<52} {'NICHO':<8} {'CONTA':<22} DECIDIU")
        print("─" * 104)
        contagem = {}
        for p in produtos:
            c = conta_do_produto(p)
            nicho = c.get("nicho_detectado", "?")
            contagem[nicho] = contagem.get(nicho, 0) + 1
            print(f"{p[:52]:<52} {nicho:<8} {c.get('handle', '?'):<22} {c.get('decidido_por')}")
        print("─" * 104)
        print("resumo:", ", ".join(f"{k}={v}" for k, v in sorted(contagem.items())))
        return 0

    nome = " ".join(args) or "produto teste"
    c = conta_do_produto(nome)
    print(f"produto  : {nome}")
    print(f"nicho    : {c.get('nicho_detectado')}  (decidido por {c.get('decidido_por')})")
    print(f"conta    : {c.get('nicho')} → {c.get('handle')}")
    print(f"ig_id    : {c.get('instagram_user_id')}  | page: {c.get('facebook_page_id')}")
    print(f"token    : {'✅ resolvido' if c.get('token') else '⚠️ vazio (' + c.get('page_token_env','') + ' não está no .env)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
