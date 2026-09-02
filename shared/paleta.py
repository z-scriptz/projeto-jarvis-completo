# shared/paleta.py
# A IDENTIDADE VISUAL DE CADA CONTA, EM UM LUGAR SÓ.
#
# POR QUE ISSO EXISTE (02/09/2026)
# ────────────────────────────────
# O Dre comparou o feed dele com dois perfis que estão crescendo (@achad0ideal,
# 1 mês / 16k; @ofertasdaflorzinha, 3 anos / 450k) e a conclusão dele foi:
# "o formato de vídeo dos dois é idêntico, já o meu? muito diferente".
# A primeira mudança pedida, nas 6 contas: FUNDO DE COR E ESTILO DA FONTE,
# uma identidade por nicho.
#
# Até hoje o "fundo" era uma PALAVRA — "preto" / "branco" / "bege" — decidida
# por uma regra de uma linha repetida em TRÊS arquivos:
#
#     _bg_padrao = "preto" if nicho in ("geral", "") else "branco"
#     produzir_tiktok:408 · telegram_repurpose_hunter:1674 · render:485
#
# Três cópias da mesma frase é exatamente o desenho que, em shared/marca.py,
# fez o @topshopcasa_ publicar com a logo do @topshop.__: o dicionário escrito
# à mão em dois arquivos, e "casa" faltando num deles. Seis nichos × três
# cópias não sobreviveriam a isso. Então a paleta mora AQUI e os renderizadores
# a IMPORTAM.
#
# O QUE É DECIDIDO E O QUE É DERIVADO
# ───────────────────────────────────
# DECIDIDO (escolha de marca, veio do Dre):
#   o FUNDO de cada nicho, e a cor de DESTAQUE.
# DERIVADO (conta, não gosto):
#   se o fundo é claro ou escuro — pela LUMINÂNCIA, não por uma flag escrita à
#   mão. E a TINTA sai disso.
#
# Isso não é preciosismo. O Dre pediu duas coisas que se contradizem quando
# escritas literalmente:
#
#     "tecnologia: preto puro ou grafite escuro"
#     "fonte de letra: [...] deve ser preto"
#
# Preto sobre preto não é um vídeo, é um retângulo. A regra que resolve é dele
# mesmo, dita no parágrafo seguinte da mesma mensagem:
#
#     "se o fundo for escuro, a letra deve ser branca"
#
# Derivando `claro` da luminância, essa regra deixa de ser algo que alguém
# precisa lembrar de aplicar: paleta escura NUNCA consegue produzir tinta
# escura, nem que alguém troque o hex amanhã. Uma paleta nova não tem como
# nascer ilegível.

import os

# ── OS FUNDOS ────────────────────────────────────────────────────────────────
#
# Um hex por nicho. O Dre deu 2-3 opções para cada; aqui há UMA, porque paleta
# é decisão, não cardápio — seis contas com "areia OU cinza claro" viram seis
# contas parecidas com nenhuma. As opções que ficaram de fora estão anotadas
# ao lado, pra troca ser um hex e não uma pesquisa.
#
# ⚠️ "geral" ERA PRETO e passa a ser BRANCO. É a conta principal (@topshop.__),
# a do print. O grid dela vai ficar meio preto / meio branco por umas semanas,
# até os posts novos empurrarem os antigos pra baixo. Isso é consequência
# conhecida do pedido, não efeito colateral — mas é visível, então está escrito.
_FUNDOS = {
    "geral":  ("#FFFFFF", "branco puro"),          # alt: cinza neutro #F4F4F4
    "moda":   ("#E6DFD3", "areia"),                # alt: cinza claro #DEDEDA
    "beleza": ("#F7E6E3", "rosa-quartzo claro"),   # alt: pêssego #FBE4D3 · nude #EFE0D4
    "casa":   ("#DFE5D8", "sálvia clara"),         # alt: cimento queimado #DEDCD5
    "tech":   ("#0E0E10", "grafite"),              # alt: preto puro #000000
    "pet":    ("#FDEBB8", "amarelo-sol suave"),    # alt: azul-bebê #D6E9F7
}

# A cor do REALCE — a palavra que sai colorida no meio do gancho branco.
# Pedido do Dre: "apenas a palavra principal em amarelo ou verde-neon".
# Neon só funciona sobre escuro; sobre fundo claro ele some. Então:
#   fundo escuro → verde-neon
#   fundo claro  → o rosa da marca (#C8385E), o mesmo do topshopoficial.com.br
# ⚠️ AINDA NÃO É PINTADO POR NINGUÉM. O gerador de gancho não marca palavra
# nenhuma hoje, e o Dre situou esse item no "foco para explodir os reels DEPOIS
# quando utilizarmos a ferramenta". A cor existe pra quando esse renderizador
# existir; dizer que está pronto seria mentira de duas linhas.
NEON = "#D6FF3D"
ROSA_MARCA = "#C8385E"

PADRAO = "geral"


def _rgb(hexa: str):
    """'#RRGGBB' -> (r, g, b). None se não for um hex legível."""
    h = (hexa or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return None
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(rgb)


def e_claro(rgb) -> bool:
    """Luminância relativa (Rec. 709) acima da metade.

    É esta função — e não uma coluna 'claro: True' na tabela — que garante que
    tinta e fundo nunca colidam. Fundo novo entra e a legibilidade vem junto.
    """
    r, g, b = (c / 255.0 for c in rgb)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) > 0.5


# Palavras que o código antigo usava no lugar de uma cor. Continuam valendo,
# porque elas estão ESCRITAS NO .env DA VPS (FORCE_BG, BG_TECH, TOPSHOP_BG) e
# um deploy que só funciona depois que alguém lembra de editar o .env é um
# deploy que quebra a produção no meio do dia.
_APELIDOS = {
    "preto": "#000000", "black": "#000000",
    "branco": "#FFFFFF", "white": "#FFFFFF",
    "bege": "#E8E0D2", "claro": "#E8E0D2",
    "grafite": "#0E0E10",
}


def cor(valor: str):
    """Lê fundo de qualquer forma que ele apareça no ambiente.

    Aceita hex ('#E6DFD3'), apelido legado ('preto'/'branco'/'bege') e nome de
    nicho ('tech'). Devolve None quando não entende — e quem chama trata isso
    como "sem override", nunca como preto.
    """
    v = (valor or "").strip().lower()
    if not v:
        return None
    if v in _APELIDOS:
        return _rgb(_APELIDOS[v])
    if v in _FUNDOS:
        return _rgb(_FUNDOS[v][0])
    return _rgb(v)


def _montar(fundo_rgb, nome_fundo: str, nicho: str) -> dict:
    """A paleta completa a partir do fundo. Tudo o que depende de claro/escuro
    é calculado aqui, uma vez, pra não haver dois lugares decidindo cor."""
    claro = e_claro(fundo_rgb)
    if claro:
        # Não é preto puro: preto absoluto sobre bege/rosa fica duro. É a mesma
        # razão pela qual a tinta do site é #1A2338 e não #000.
        tinta = (23, 21, 18)
        secundaria = (122, 122, 122)
        destaque = _rgb(ROSA_MARCA)
    else:
        tinta = (255, 255, 255)
        secundaria = (185, 185, 190)
        destaque = _rgb(NEON)
    return {
        "nicho": nicho,
        "claro": claro,
        "fundo_rgb": tuple(fundo_rgb),
        "fundo_hex": _hex(fundo_rgb),
        "fundo_nome": nome_fundo,
        "tinta_rgb": tinta,
        "tinta_hex": _hex(tinta),
        "secundaria_rgb": secundaria,
        "secundaria_hex": _hex(secundaria),
        "destaque_rgb": destaque,
        "destaque_hex": _hex(destaque),
        # contorno: só no escuro, e só porque o texto branco atravessa a borda
        # do vídeo. No claro o contorno preto engorda a fonte Light e mata
        # justamente o ar que o Dre foi buscar nos perfis de referência.
        "contorno": 0 if claro else int(os.environ.get("HK_STROKE_PRETO", 4)),
    }


def do_nicho(nicho: str) -> dict:
    """A paleta oficial do nicho. Nicho desconhecido cai em 'geral' — e isso é
    seguro justamente porque a tinta é derivada: o pior caso é a conta sair com
    a cara da principal, nunca ilegível."""
    n = (nicho or "").strip().lower() or PADRAO
    hexa, nome = _FUNDOS.get(n, _FUNDOS[PADRAO])
    return _montar(_rgb(hexa), nome, n if n in _FUNDOS else PADRAO)


def do_ambiente(nicho: str = None) -> dict:
    """A paleta QUE VALE NESTE RENDER, lida do ambiente.

    Ordem: a paleta do nicho manda; TOPSHOP_BG (que já carrega o resultado de
    FORCE_BG / BG_<NICHO>, resolvidos pelo produtor) troca o FUNDO por cima. A
    tinta é recalculada em cima do fundo forçado — por isso `FORCE_BG=preto`
    num nicho claro continua produzindo um vídeo legível em vez de tinta escura
    sobre fundo escuro.
    """
    p = do_nicho(nicho or os.environ.get("TOPSHOP_NICHO", ""))
    forcado = cor(os.environ.get("TOPSHOP_BG", ""))
    if forcado and tuple(forcado) != p["fundo_rgb"]:
        p = _montar(forcado, "forçado por TOPSHOP_BG", p["nicho"])
    return p


def aplicar_no_ambiente(nicho: str, log=None) -> dict:
    """O produtor chama ISTO antes de renderizar, e é a única linha que os dois
    produtores precisam ter em comum.

    Escreve TOPSHOP_NICHO e TOPSHOP_BG no ambiente, porque a renderização
    acontece noutro escopo (e, no caminho do TikTok, noutro processo): o
    ambiente é a única coisa que atravessa. Continua respeitando FORCE_BG (pra
    testar) e BG_<NICHO> (override por conta no .env), que é o que já estava
    escrito nos dois arquivos.
    """
    n = (nicho or "").strip().lower() or PADRAO
    os.environ["TOPSHOP_NICHO"] = n
    override = (os.environ.get("FORCE_BG")
                or os.environ.get("BG_" + n.upper()) or "").strip()
    p = do_nicho(n)
    if override:
        forcado = cor(override)
        if forcado:
            p = _montar(forcado, f"forçado por {override}", n)
        elif log is not None:
            _dizer(log, f"⚠️  fundo '{override}' não é hex nem apelido conhecido — "
                        f"ignorado, vale a paleta de {n}")
    os.environ["TOPSHOP_BG"] = p["fundo_hex"]
    if log is not None:
        _dizer(log, "   🎨 " + resumo(p))
    return p


def _dizer(log, msg: str):
    try:
        (log.info if hasattr(log, "info") else log)(msg)
    except Exception:
        print(msg, flush=True)


def resumo(p: dict) -> str:
    """Uma linha pro log. Existe porque 'mudei o código e o vídeo não mudou' já
    custou duas rodadas neste projeto: o log tem que dizer o que VALEU."""
    return (f"paleta {p['nicho']}: fundo {p['fundo_hex']} ({p['fundo_nome']}, "
            f"{'claro' if p['claro'] else 'escuro'}) · tinta {p['tinta_hex']} · "
            f"destaque {p['destaque_hex']}")


if __name__ == "__main__":
    for n in ("geral", "moda", "beleza", "casa", "tech", "pet", "inexistente"):
        print(resumo(do_nicho(n)))
