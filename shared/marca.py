# shared/marca.py
# QUAL LOGO É DE QUAL CONTA.
#
# POR QUE ISSO EXISTE (04/08/2026)
# ────────────────────────────────
# O @topshopcasa_ publicou um vídeo com a logo do @topshop.__. A causa era um
# dicionário escrito à mão, duplicado em DOIS arquivos:
#
#     _LOGO_NICHO = {"beleza": "logo_ts_beauty.png", "tech": "logo_ts_tech.png"}
#
# "casa" nunca foi acrescentado ali. O `.get(nicho, "logo_ts.png")` então
# devolvia a logo padrão — a da conta geral — e o vídeo saiu com a marca
# errada, no ar, pro público da conta de casa.
#
# O QUE DEIXOU ISSO PASSAR não foi o dicionário incompleto: foi o SILÊNCIO.
# `_brand_asset()` devolve None quando o arquivo não existe, o render cai no
# padrão sem dizer nada, e o log imprimia "🅣 logo 'logo_ts.png'" — uma frase
# verdadeira que ninguém tinha como identificar como errada.
#
# Duas mudanças de postura aqui:
#
#   1. O NOME É DERIVADO DO NICHO, não escrito à mão. Conta nova ganha
#      "logo_ts_<nicho>.png" automaticamente. Ninguém precisa lembrar de
#      editar um dicionário em dois arquivos.
#   2. QUANDO CAI NO PADRÃO, ELE GRITA. Cair no padrão é publicar com a marca
#      de outra conta — nunca é rotina, e o log tem que doer de ler.

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BRAND_DIR = BASE_DIR / "assets" / "brand"

LOGO_PADRAO = "logo_ts.png"

# Nomes herdados: estes arquivos já existiam com nome em inglês antes de a
# regra virar "logo_ts_<nicho>.png". Renomear na VPS quebraria a produção no
# meio do dia, então o apelido mora aqui e o resto do código não sabe disso.
APELIDO = {
    "beleza": "logo_ts_beauty.png",
    "tech": "logo_ts_tech.png",
}


def nome_da_logo(nicho: str) -> str:
    """O arquivo de logo ESPERADO pra este nicho. Não checa se existe."""
    n = (nicho or "").strip().lower()
    if not n or n == "geral":
        return LOGO_PADRAO
    return APELIDO.get(n, f"logo_ts_{n}.png")


def logo_do_nicho(nicho: str, log=None) -> tuple:
    """(arquivo_a_usar, é_a_da_conta).

    `é_a_da_conta` False significa que a logo da conta NÃO existe e o vídeo vai
    sair com a marca da conta geral. Quem chama deve avisar alto — foi
    exatamente esse caso, silencioso, que colocou a logo do @topshop.__ num
    vídeo do @topshopcasa_.

    Passe `log` (um logger ou uma função que aceita string) pra que o aviso
    saia sozinho.
    """
    esperado = nome_da_logo(nicho)
    if esperado == LOGO_PADRAO or (BRAND_DIR / esperado).exists():
        return esperado, True

    aviso = (f"⚠️  LOGO DA CONTA AUSENTE: '{esperado}' não está em "
             f"{BRAND_DIR}. O vídeo do nicho '{nicho}' vai sair com a MARCA DA "
             f"CONTA GERAL ({LOGO_PADRAO}). Coloque o PNG lá e refaça.")
    if log is not None:
        try:
            (log.warning if hasattr(log, "warning") else log)(aviso)
        except Exception:
            print(aviso, flush=True)
    else:
        print(aviso, flush=True)
    return LOGO_PADRAO, False


def logo_escolhida(nicho: str, log=None) -> str:
    """O nome do arquivo, já respeitando FORCE_LOGO (usado pra testar)."""
    forcada = (os.environ.get("FORCE_LOGO") or "").strip()
    if forcada:
        return forcada
    return logo_do_nicho(nicho, log=log)[0]
