# creative_engine/ia_scene_generator.py
# GERADOR DE CENAS POR IA — produz o B-roll do vídeo a partir do PRODUTO,
# usando provider de vídeo pago (Pixverse/Fal), e salva as cenas com o
# prefixo 'ia_' na pasta que o narrated_video_agent já lê:
#
#     assets/produtos/<slug>/raw/ia_<cena>_<n>.mp4
#
# Assim o fluxo fica:
#   radar → produto → [ESTE GERADOR cria cenas IA] → narrated_video_agent
#   monta o vídeo narrado (Edge-TTS + legenda + hook + CTA) sobre as cenas.
#
# As cenas seguem a sequência canônica de um anúncio curto:
#   dor → demo → close → resultado   (o CTA é overlay, não precisa de cena)
#
# O texto/áudio é 100% original (narração Edge-TTS). As cenas são geradas por
# IA a partir de prompts construídos do nome/categoria do produto — nenhum
# vídeo de terceiro é baixado ou reprocessado.
#
# CLI:
#   python -m creative_engine.ia_scene_generator --produto "Chaleira Elétrica Inox"
#   python -m creative_engine.ia_scene_generator --produto "X" --cenas dor,demo --dry-run
#   python -m creative_engine.ia_scene_generator --produto "X" --provider fal

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
    log = logging.getLogger("ia_scene_generator")

PROJETO_ROOT = Path(__file__).parent.parent
PRODUTOS_ROOT = PROJETO_ROOT / "assets" / "produtos"

# Sequência canônica de cenas (igual a do narrated_video_agent).
# O CTA é overlay de texto no motor, então não geramos cena pra ele.
SEQUENCIA_CENAS = ["dor", "demo", "close", "resultado"]

# Duração alvo de cada cena (seg). Curto = mais barato e mais dinâmico.
DUR_CENA_PADRAO = 10  # cenas mais longas = motor corta sem repetir (anti-looping)

# Resolução vertical (9:16) — o motor reenquadra, mas pedimos certo já na fonte.
LARGURA, ALTURA = 1080, 1920


# =====================================================================
# CATEGORIA (heurística simples, alinhada ao resto do projeto)
# =====================================================================
_CATEGORIAS = [
    ("cozinha", ("chaleira", "panela", "fritadeira", "liquidificador", "mixer",
                 "cafeteira", "talher", "pote", "boleira", "frigideira", "jantar",
                 "assadeira", "taça", "copo", "caneca", "garrafa", "térmico")),
    ("beleza",  ("modelador", "escova", "secador", "maquiagem", "batom", "gloss",
                 "skincare", "óleo", "cabelo", "massageador facial", "organizador de maquiagem")),
    ("casa",    ("cobertor", "manta", "lustre", "luminária", "abajur", "tapete",
                 "cortina", "rack", "espelho", "almofada", "umidificador",
                 "organizador", "cesto", "armário", "mesa", "fruteira")),
    ("tech",    ("fone", "smartwatch", "carregador", "power bank", "microfone",
                 "smartphone", "filtro de linha", "relógio", "controle", "mouse",
                 "projetor", "impressora", "amplificador")),
    ("fitness", ("creatina", "tapete yoga", "corda", "faixa", "massageador")),
    ("eletro",  ("geladeira", "frigobar", "aspirador", "robô", "ventilador",
                 "forno", "centrífuga", "secadora", "bicicleta elétrica")),
    ("moda",    ("casaco", "jaqueta", "bota", "sandália", "vestido", "camisa",
                 "blusa", "macacão", "moletom", "bolsa", "calça", "conjunto")),
]


def detectar_categoria(produto: str) -> str:
    p = (produto or "").lower()
    for rotulo, kws in _CATEGORIAS:
        for kw in kws:
            if kw in p:
                return rotulo
    return "geral"


def slugificar(produto: str) -> str:
    """
    Usa a MESMA slugificação do narrated_video_agent (agents.asset_agent.
    slugificar_produto), pra garantir que as cenas sejam salvas na MESMA
    pasta que o motor procura. Se não conseguir importar, cai num fallback
    que remove acentos (igual ao comportamento típico do motor).
    """
    try:
        from agents.asset_agent import slugificar_produto
        return slugificar_produto(produto)
    except Exception:
        # fallback: remove acento e normaliza (espelha o motor)
        import unicodedata
        t = unicodedata.normalize("NFKD", produto or "")
        t = "".join(c for c in t if not unicodedata.combining(c))
        s = re.sub(r"\W+", "_", t.lower()).strip("_")[:40]
        return s or f"produto_{int(time.time())}"


# =====================================================================
# PROMPT MESTRE TOPSHOP — identidade visual da marca.
# Filosofia: "vídeo que parece gravado por um criador comum, mas com
# qualidade de propaganda." UGC realista no início (confiança), premium
# no meio (valor), resultado claro no fim (desejo).
# Cada cena puxa: base de marca + direção própria da cena + contexto do produto.
# =====================================================================

# Base aplicada a TODAS as cenas (a "cara" da TopShop).
_TOPSHOP_BASE = (
    "realistic UGC style, filmed on a smartphone, real residential home, "
    "natural lighting, authentic everyday setting, handheld feel, "
    "ultra realistic, photorealistic, no AI look, no distortion, "
    "no deformed hands, no impossible motion, natural human movement, "
    "vertical 9:16, no text, no watermark, no logo"
)

# Negative prompt (o que a IA deve EVITAR) — reforça o realismo.
TOPSHOP_NEGATIVE = (
    "cartoon, 3d render, cgi, fake looking, plastic skin, deformed hands, "
    "extra fingers, distorted face, watermark, text overlay, logo, "
    "oversaturated, cinematic color grading overkill, studio commercial look"
)

# Arco de 3 atos mapeado nas cenas dor→demo→close→resultado.
# Cada cena tem: intenção + direção de câmera técnica + emoção/luz.
_CENA_DIRECAO = {
    # ATO 1 — UGC realista (0-3s): confiança, "alguém gravou em casa"
    "dor": (
        "ACT 1, authentic UGC opening: a real person at home facing the everyday "
        "frustration that {produto_en} solves, {ctx}, handheld smartphone shot, "
        "slightly shaky, natural window light, candid unpolished feel, "
        "relatable mundane moment, muted cool tones"
    ),
    # ATO 2a — demonstração realista virando premium
    "demo": (
        "ACT 2, the person starts using {produto_en} naturally, {ctx}, "
        "handheld follow shot transitioning to a smooth slow dolly-in, "
        "natural soft daylight, real hands interacting, satisfying first use, "
        "warm inviting tones, believable home setting"
    ),
    # ATO 2b — premium: macro do produto, "parece valer mais"
    "close": (
        "ACT 2 premium beat, extreme macro close-up of {produto_en}, "
        "85mm lens look, shallow depth of field, slow rack focus on the texture "
        "and finish, gentle slow motion, soft golden-hour light catching the "
        "details, premium tactile feel, the product looks high quality"
    ),
    # ATO 3 — resultado: antes/depois, benefício visível
    "resultado": (
        "ACT 3, clear before-and-after result of using {produto_en}, {ctx}, "
        "bright clean satisfying payoff, the visible benefit front and center, "
        "natural daylight, smartphone shot, happy relieved everyday mood, "
        "warm positive tones, the kind of result that makes you want it"
    ),
}

# Contexto residencial por categoria (ambiente real de casa).
_CTX_CATEGORIA = {
    "cozinha": "in a real home kitchen, lived-in countertop with everyday items",
    "beleza": "in a real bathroom or bedroom vanity, personal everyday setting",
    "casa": "in a real cozy living room or bedroom, lived-in home",
    "tech": "on a real desk or home table, everyday use context",
    "fitness": "in a real home corner or living room workout spot",
    "eletro": "in a real home, everyday domestic setting",
    "moda": "in a real bedroom or in front of a home mirror, getting ready",
    "geral": "in a real home, natural everyday setting",
}

# Tradução leve de termos comuns pro inglês (a IA entende melhor o conceito
# visual do que o nome cru em PT). Fallback: usa o nome como veio.
_TRADUZ = {
    "chaleira": "electric kettle", "elétrica": "", "inox": "stainless steel",
    "geladeira": "refrigerator", "frigobar": "mini fridge",
    "aspirador": "vacuum cleaner", "robô": "robot", "ventilador": "fan",
    "modelador": "hair curler", "cachos": "curls", "escova": "hair brush",
    "secadora": "hair dryer", "panela": "cooking pot", "fritadeira": "air fryer",
    "liquidificador": "blender", "cafeteira": "coffee maker",
    "organizador": "organizer", "cesto": "basket", "pote": "container",
    "luminária": "lamp", "abajur": "lamp", "cobertor": "blanket",
    "manta": "blanket", "tapete": "rug", "smartwatch": "smartwatch",
    "fone": "earbuds", "carregador": "charger", "microfone": "microphone",
}


def _produto_para_ingles(produto: str) -> str:
    """Converte o nome do produto num conceito visual em inglês (melhor pra IA)."""
    p = (produto or "").lower()
    achados = []
    for pt, en in _TRADUZ.items():
        if pt in p and en:
            achados.append(en)
    if achados:
        # de-dup preservando ordem, máx 4 termos
        vistos, out = set(), []
        for t in achados:
            if t not in vistos:
                vistos.add(t); out.append(t)
        return " ".join(out[:4])
    # fallback: nome curto original
    return " ".join((produto or "product").split()[:4])


def construir_prompt_cena(produto: str, cena: str, categoria: str) -> str:
    ctx = _CTX_CATEGORIA.get(categoria, _CTX_CATEGORIA["geral"])
    produto_en = _produto_para_ingles(produto)
    direcao = _CENA_DIRECAO.get(cena, _CENA_DIRECAO["demo"])
    corpo = direcao.format(produto_en=produto_en, ctx=ctx)
    # monta: direção da cena + base de identidade TopShop
    return f"{corpo}, {_TOPSHOP_BASE}"


# =====================================================================
# PROVIDER — usa o registry REAL do projeto (providers/__init__.py).
# obter_provider_cascata(preferido) devolve uma instância de BaseProvider
# que expõe .gerar(prompt, cena, produto, arquivo_esperado, output_dir, dry_run)
# e retorna um ResultadoGeracao padronizado (.sucesso, .arquivo, .status...).
# Com 'auto' (ou preferido indisponível), tenta a cascata Fal→Grok→Pixverse→HeyGen.
# =====================================================================
def _obter_provider(preferido: str):
    """Retorna (instância_provider, nome) ou (None, motivo) se nada disponível."""
    try:
        from providers import obter_provider_cascata, providers_disponiveis_da_cascata
    except Exception as e:
        return None, f"registry de providers indisponível ({e})"

    disp = providers_disponiveis_da_cascata()
    inst = obter_provider_cascata(preferido=preferido)
    # ManualProvider está sempre "disponível", mas não gera arquivo sozinho.
    # Tratamos manual como "sem geração automática" pra cair no fluxo de prompts.
    if inst is None or getattr(inst, "nome", "manual") == "manual":
        motivo = ("nenhum provider de vídeo com API configurada "
                  f"(disponíveis: {disp or 'nenhum'})")
        return None, motivo
    log.info(f"Provider de vídeo ativo: {inst.nome} (cascata disponível: {disp})")
    return inst, inst.nome


# =====================================================================
# GERAÇÃO
# =====================================================================
def gerar_cenas(produto: str, cenas=None, provider="auto",
                dur=DUR_CENA_PADRAO, dry_run=False) -> dict:
    """
    Gera as cenas de IA pro produto e salva em assets/produtos/<slug>/raw/.
    Retorna dict com o resultado (cenas geradas, prompts, caminhos).
    """
    cenas = cenas or list(SEQUENCIA_CENAS)
    categoria = detectar_categoria(produto)
    slug = slugificar(produto)
    destino_dir = PRODUTOS_ROOT / slug / "raw"

    log.info("=" * 60)
    log.info(f"🎬 GERADOR DE CENAS IA — {produto!r}")
    log.info(f"   categoria: {categoria} | cenas: {cenas} | provider: {provider}")
    log.info("=" * 60)

    # monta os prompts (sempre — útil mesmo em dry-run / modo manual)
    plano_cenas = []
    for i, cena in enumerate(cenas, 1):
        prompt = construir_prompt_cena(produto, cena, categoria)
        nome_arq = f"ia_{cena}_{i}.mp4"
        plano_cenas.append({"cena": cena, "arquivo": nome_arq, "prompt": prompt})

    if dry_run:
        log.info("🧪 DRY-RUN — apenas mostrando os prompts (nada gerado):")
        for pc in plano_cenas:
            log.info(f"   [{pc['cena']}] {pc['prompt'][:90]}...")
        return {"ok": True, "dry_run": True, "categoria": categoria,
                "slug": slug, "cenas": plano_cenas}

    destino_dir.mkdir(parents=True, exist_ok=True)
    inst, info = _obter_provider(provider)

    # MODO MANUAL: sem provider automático → salva os prompts num .json pra
    # você gerar as cenas na ferramenta e soltar na pasta com o nome indicado.
    if inst is None:
        manual_path = destino_dir / "_prompts_para_gerar.json"
        with open(manual_path, "w", encoding="utf-8") as f:
            json.dump({"produto": produto, "categoria": categoria,
                       "instrucao": "Gere cada cena na ferramenta de IA e salve "
                                    "na MESMA pasta com o 'arquivo' indicado.",
                       "cenas": plano_cenas}, f, ensure_ascii=False, indent=2)
        log.warning(f"⚠️  Sem geração automática: {info}")
        log.warning(f"   Prompts salvos em: {manual_path}")
        log.warning("   Gere as cenas e solte na pasta — o motor de vídeo lê de lá.")
        return {"ok": False, "modo": "manual", "prompts": str(manual_path),
                "categoria": categoria, "slug": slug, "cenas": plano_cenas}

    # MODO AUTOMÁTICO: chama o provider pra cada cena (contrato BaseProvider)
    # Ajusta a duração das cenas no provider, se ele suportar (Fal/Pixverse têm
    # self.duration). Cenas mais longas dão "pano" pro motor cortar sem repetir
    # a mesma cena em loop. O Kling (Fal) aceita "5" ou "10".
    if dur and hasattr(inst, "duration"):
        try:
            # alguns providers usam str ("10"), outros int (10). Respeita o tipo.
            tipo_atual = type(inst.duration)
            inst.duration = tipo_atual(dur) if tipo_atual in (str, int) else dur
            log.info(f"   ⏱️  duração da cena ajustada p/ {inst.duration}s")
        except Exception as e:
            log.warning(f"   (não consegui ajustar duração: {e}; usando padrão do provider)")

    geradas = []
    for pc in plano_cenas:
        log.info(f"   🎨 gerando cena '{pc['cena']}' via {inst.nome}...")
        try:
            res = inst.gerar(
                prompt=pc["prompt"],
                cena=pc["cena"],
                produto=produto,
                arquivo_esperado=pc["arquivo"],
                output_dir=destino_dir,
                dry_run=False,
            )
        except Exception as e:
            log.warning(f"      ⚠️  exceção inesperada: {e}")
            continue

        # ResultadoGeracao é um dict padronizado
        if res and res.get("sucesso") and res.get("arquivo") and Path(res["arquivo"]).exists():
            geradas.append(res["arquivo"])
            log.info(f"      ✅ {Path(res['arquivo']).name} — {res.get('mensagem','')}")
        else:
            status = (res or {}).get("status", "?")
            msg = (res or {}).get("mensagem") or (res or {}).get("erro") or "?"
            log.warning(f"      ⚠️  cena '{pc['cena']}' não saiu (status={status}): {msg}")
        time.sleep(1.0)  # respiro entre chamadas

    ok = len(geradas) > 0
    log.info(f"{'✅' if ok else '❌'} {len(geradas)}/{len(plano_cenas)} cenas geradas em {destino_dir}")
    return {"ok": ok, "modo": "auto", "provider": inst.nome, "categoria": categoria,
            "slug": slug, "geradas": geradas, "cenas": plano_cenas,
            "destino": str(destino_dir)}


def main():
    parser = argparse.ArgumentParser(description="Gerador de cenas por IA (B-roll do vídeo)")
    parser.add_argument("--produto", required=True, help="nome do produto")
    parser.add_argument("--cenas", default="", help="subconjunto: dor,demo,close,resultado")
    parser.add_argument("--provider", default="auto", help="auto|fal|grok|pixverse|heygen")
    parser.add_argument("--dur", type=int, default=DUR_CENA_PADRAO, help="seg por cena")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="só mostra os prompts, não gera")
    args = parser.parse_args()

    cenas = [c.strip() for c in args.cenas.split(",") if c.strip()] or None
    res = gerar_cenas(args.produto, cenas=cenas, provider=args.provider,
                      dur=args.dur, dry_run=args.dry_run)

    if res.get("ok"):
        print(f"\n✅ Cenas prontas pro motor de vídeo: {res.get('destino', '(dry-run)')}")
        print(f"   Próximo passo: python -m agents.narrated_video_agent --produto \"{args.produto}\"")
    elif res.get("modo") == "manual":
        print(f"\n📝 Modo manual: gere as cenas a partir de {res['prompts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())