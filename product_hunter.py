# agents/product_hunter.py
# Caçador de produtos do AgenteIA (Jarvis)
#
# Responsabilidade: encontrar produtos com potencial para vídeos curtos
# de afiliado e salvar na Fila_de_Postagem automaticamente.
#
# Não chama Gemini, não raspa sites, não posta.
# Apenas alimenta a fila com candidatos inteligentes.
#
# Uso:
#   from agents.product_hunter import buscar_produtos_automaticamente
#   resultado = buscar_produtos_automaticamente(nicho="casa", limite=10)

import json
import time
import random
from pathlib import Path
from difflib import SequenceMatcher

from shared.logger import get_logger

log = get_logger(__name__)

PLANS_DIR = Path(__file__).parent.parent / "shared" / "content_plans"


# =================================================================
# BASE DE PRODUTOS POR NICHO
# Curadoria manual — produtos com alto potencial para vídeo curto
# =================================================================

_CATALOGO = {
    "beleza": [
        {"produto": "Esponja Elétrica de Limpeza Facial",        "obs": "Demonstração visual clara, antes/depois poderoso"},
        {"produto": "Máscara LED Facial 7 Cores",                "obs": "Visual chamativo, tendência, curiosidade"},
        {"produto": "Mini Chapinha Portátil USB",                 "obs": "Compacto, resolve dor, fácil de demonstrar"},
        {"produto": "Removedor de Cravos Elétrico",              "obs": "Satisfying content, alto engajamento"},
        {"produto": "Cílios Magnéticos com Delineador",          "obs": "Antes/depois, fácil de filmar"},
        {"produto": "Massageador Facial de Jade Roller",         "obs": "Trend, rotina de skincare"},
        {"produto": "Sérum Vitamina C com Ácido Hialurônico",    "obs": "Skincare viral, ticket baixo"},
        {"produto": "Escova Alisadora Elétrica 2 em 1",          "obs": "Transformação rápida, WOW factor"},
        {"produto": "Patch Redutor de Olheiras Colágeno",        "obs": "Antes/depois, self-care trend"},
        {"produto": "Vaporizador Facial Portátil",               "obs": "Spa em casa, demonstração fácil"},
        {"produto": "Depilador Indolor a Laser IPL",             "obs": "Resolve dor clara, ticket médio"},
        {"produto": "Kit Unha em Gel com UV LED Portátil",       "obs": "Satisfying, tendência nail art"},
    ],
    "casa": [
        {"produto": "Mini Aspirador de Teclado USB",             "obs": "Satisfying, demonstração instantânea"},
        {"produto": "Organizador de Cabos Magnético",            "obs": "Antes/depois mesa, organização"},
        {"produto": "Lâmpada LED Sensor de Movimento",           "obs": "Mágica ao vivo, WOW"},
        {"produto": "Dispenser Automático de Sabonete",          "obs": "Tech de casa, higiênico, visual"},
        {"produto": "Suporte Notebook Dobrável Alumínio",        "obs": "Setup upgrade, ergonomia"},
        {"produto": "Cortina LED Cascata 300 LEDs",              "obs": "Decoração viral, visual incrível"},
        {"produto": "Organizador Acrílico para Maquiagem",       "obs": "Antes/depois, satisfying"},
        {"produto": "Umidificador de Ar Mini com LED",           "obs": "Aesthetic, visual bonito"},
        {"produto": "Adesivo Vedante de Pia e Banheiro",         "obs": "Resolve dor, antes/depois claro"},
        {"produto": "Purificador de Ar Mini Portátil",           "obs": "Saúde em casa, compacto"},
        {"produto": "Fita LED RGB com Controle Remoto",          "obs": "Setup gamer, decoração viral"},
        {"produto": "Cinto Modelador Slim Feminino",             "obs": "Antes/depois corporal, alta conversão"},
    ],
    "cozinha": [
        {"produto": "Cortador de Legumes Multifunção 12 em 1",   "obs": "Satisfying de cortar, viral"},
        {"produto": "Espremedor de Alho Inox Prensa",            "obs": "Satisfying, facilita vida"},
        {"produto": "Balança Digital de Cozinha 5kg",            "obs": "Fitness + cozinha, útil"},
        {"produto": "Afiador Elétrico de Facas USB",             "obs": "Antes/depois de corte, WOW"},
        {"produto": "Dispenser de Tempero 6 Potes Giratório",    "obs": "Organização, visual bonito"},
        {"produto": "Escova Elétrica de Limpeza 5 em 1",         "obs": "Satisfying de limpar"},
        {"produto": "Seladora Portátil de Embalagens",           "obs": "Hack de cozinha, prático"},
        {"produto": "Forma de Gelo Esfera Silicone",             "obs": "Aesthetic, drinks virais"},
        {"produto": "Descascador Elétrico de Frutas",            "obs": "Satisfying, curiosidade"},
        {"produto": "Garrafa Térmica Inteligente com LCD",       "obs": "Tech de cozinha, visual"},
    ],
    "fitness": [
        {"produto": "Elástico de Resistência Kit 5 Faixas",      "obs": "Treino em casa, demonstração fácil"},
        {"produto": "Rolo de Massagem Muscular Bastão",          "obs": "Recovery, demonstração clara"},
        {"produto": "Garrafa de Água Motivacional 2L",           "obs": "Trend saúde, visual bonito"},
        {"produto": "Corda de Pular com Contador Digital",       "obs": "Cardio viral, tech fitness"},
        {"produto": "Luva de Musculação com Munhequeira",        "obs": "Proteção, demonstração gym"},
        {"produto": "Pistola de Massagem Mini Portátil",         "obs": "Recovery viral, demonstração fácil"},
        {"produto": "Caneleira de Peso Ajustável 2kg",           "obs": "Treino em casa, antes/depois"},
        {"produto": "Whey Protein Refil 1kg",                    "obs": "Suplemento básico, alta demanda"},
        {"produto": "Tapete de Yoga Antiderrapante 6mm",         "obs": "Wellness, demonstração visual"},
        {"produto": "Hand Grip Ajustável com Contador",          "obs": "Satisfying, treino em qualquer lugar"},
    ],
    "pets": [
        {"produto": "Escova Autopimpante para Gatos",            "obs": "Satisfying, gatos virais"},
        {"produto": "Bebedouro Fonte para Pets 2L",              "obs": "Pet feliz, visual fofo"},
        {"produto": "Brinquedo Interativo Gato Laser Auto",      "obs": "Gato perseguindo laser, viral"},
        {"produto": "Cama Suspensa de Janela para Gato",         "obs": "Gato relaxando, aesthetic"},
        {"produto": "Dispenser Automático de Ração",             "obs": "Tech pet, resolve dor de viagem"},
        {"produto": "Luva Tira Pelos para Pets",                 "obs": "Satisfying, demonstração clara"},
        {"produto": "Coleira LED Recarregável para Cachorro",    "obs": "Segurança noturna, visual legal"},
        {"produto": "Tapete Higiênico Lavável para Cães",        "obs": "Resolve dor real, economia"},
    ],
    "tecnologia": [
        {"produto": "Fone Bluetooth TWS Cancelamento de Ruído",  "obs": "Tech acessível, uso diário"},
        {"produto": "Hub USB-C 7 em 1 com HDMI",                 "obs": "Setup upgrade, produtividade"},
        {"produto": "Mouse Sem Fio Ergonômico Vertical",         "obs": "Saúde, diferente, curiosidade"},
        {"produto": "Webcam Full HD com Microfone",              "obs": "Home office, qualidade de call"},
        {"produto": "Carregador Sem Fio 3 em 1 MagSafe",        "obs": "Apple ecosystem, visual clean"},
        {"produto": "Mini Projetor LED Portátil",                "obs": "Cinema em casa, WOW factor"},
        {"produto": "Teclado Mecânico Compacto 60%",             "obs": "Setup gamer, ASMR de teclado"},
        {"produto": "Smartwatch Esportivo com Oxímetro",         "obs": "Saúde + tech, demonstração fácil"},
        {"produto": "Power Bank Solar 20000mAh",                 "obs": "Viagem, sobrevivência, prático"},
        {"produto": "Webcam Ring Light 2 em 1",                  "obs": "Criador de conteúdo, iluminação"},
    ],
    "organizacao": [
        {"produto": "Organizador de Gaveta Ajustável Bambu",     "obs": "Antes/depois gaveta, satisfying"},
        {"produto": "Etiquetadora Portátil Bluetooth",           "obs": "Organização viral, tech"},
        {"produto": "Caixa Organizadora Empilhável Transparente","obs": "Antes/depois, visual limpo"},
        {"produto": "Porta-Sapatos de Parede Magnético",         "obs": "Hack de espaço, WOW"},
        {"produto": "Organizador de Mala Cubo 6 Peças",          "obs": "Viagem, antes/depois mala"},
        {"produto": "Quadro de Cortiça com Moldura Minimalista", "obs": "Home office aesthetic"},
        {"produto": "Separador de Roupas 3 Cestos Dobrável",     "obs": "Lavanderia, organização"},
        {"produto": "Prateleira Flutuante Invisível",            "obs": "Decoração mágica, WOW"},
    ],
    "maternidade": [
        {"produto": "Almofada de Amamentação Ergonômica",        "obs": "Resolve dor real, essencial"},
        {"produto": "Termômetro Digital Infravermelho Testa",     "obs": "Praticidade, tech de mãe"},
        {"produto": "Babá Eletrônica com Câmera WiFi",           "obs": "Segurança, tech, necessidade"},
        {"produto": "Mordedor Silicone Refrigerável",             "obs": "Alívio bebê, visual fofo"},
        {"produto": "Aspirador Nasal Elétrico para Bebê",        "obs": "Resolve dor, demonstração clara"},
        {"produto": "Protetor de Quina Mesa Kit 20 Peças",       "obs": "Segurança, necessidade real"},
        {"produto": "Trava de Segurança para Gavetas Kit 10",    "obs": "Segurança, compra por impulso"},
        {"produto": "Garrafa Térmica para Mamadeira Portátil",   "obs": "Viagem com bebê, prático"},
    ],
    "moda feminina": [
        {"produto": "Cinto Modelador Invisível Slim",            "obs": "Antes/depois corporal, viral"},
        {"produto": "Bolsa Crossbody Minimalista Couro PU",      "obs": "Moda acessível, visual limpo"},
        {"produto": "Meia-Calça Térmica Fio 120 Translúcida",    "obs": "Inverno, hack de moda, visual"},
        {"produto": "Presilha Francesa Acetato Vintage",         "obs": "Trend cabelo, aesthetic"},
        {"produto": "Chinelo Nuvem Ortopédico",                  "obs": "Conforto viral, satisfying"},
        {"produto": "Óculos de Sol Oversized Retrô",             "obs": "Moda viral, look completo"},
        {"produto": "Soutien Adesivo Invisível Push Up",         "obs": "Hack de moda, antes/depois"},
        {"produto": "Tênis Chunky Plataforma Casual",            "obs": "Trend, moda acessível"},
    ],
}


# =================================================================
# GERAÇÃO DE IDEIAS
# =================================================================

def gerar_ideias_produtos_por_nicho(nicho: str = "geral", limite: int = 10) -> list[dict]:
    """
    Gera lista de produtos candidatos a partir do catálogo local.
    Se nicho="geral", mistura de todos os nichos.
    """
    nicho_lower = nicho.lower().strip()

    if nicho_lower == "geral" or nicho_lower not in _CATALOGO:
        # Mix de todos os nichos
        todos = []
        for n, produtos in _CATALOGO.items():
            for p in produtos:
                todos.append({**p, "nicho": n.title()})
        random.shuffle(todos)
        candidatos = todos[:limite]
        log.info(f"🌐 Geradas {len(candidatos)} ideias mix de todos os nichos")
    else:
        produtos = _CATALOGO[nicho_lower]
        candidatos = [{**p, "nicho": nicho.title()} for p in produtos]
        random.shuffle(candidatos)
        candidatos = candidatos[:limite]
        log.info(f"🏷️ Geradas {len(candidatos)} ideias do nicho '{nicho}'")

    # Padroniza formato
    resultado = []
    for c in candidatos:
        resultado.append({
            "produto":    c["produto"],
            "nicho":      c.get("nicho", nicho.title()),
            "plataforma": "TikTok",
            "link":       "",
            "comissao":   "",
            "prioridade": "",
            "status":     "Pendente",
            "fonte":      "hunter_local",
            "observacao":  c.get("obs", "Produto com bom potencial para vídeo curto"),
        })

    return resultado


# =================================================================
# SCORING
# =================================================================

# Palavras-chave de alto potencial
_KEYWORDS_DOR     = ("resolve", "alívio", "segurança", "proteção", "limpeza", "organização", "ergon")
_KEYWORDS_VISUAL  = ("satisfying", "antes/depois", "demonstração", "visual", "wow", "transformação")
_KEYWORDS_TREND   = ("viral", "trend", "tendência", "curiosidade", "aesthetic")
_KEYWORDS_IMPULSO = ("mini", "portátil", "compacto", "acessível", "kit", "usb", "led")
_KEYWORDS_APELO   = ("feminino", "beleza", "casa", "fitness", "skincare", "moda", "slim", "modelador")
_KEYWORDS_GENERICO = ("genérico", "básico", "simples", "comum")


def calcular_score_produto(produto: dict) -> int:
    """Pontua potencial do produto para vídeo curto de afiliado."""
    score = 0
    texto = f"{produto.get('produto', '')} {produto.get('observacao', '')} {produto.get('nicho', '')}".lower()

    # Resolve dor clara
    if any(k in texto for k in _KEYWORDS_DOR):
        score += 10

    # Demonstração visual fácil
    if any(k in texto for k in _KEYWORDS_VISUAL):
        score += 10

    # Bom para antes/depois
    if "antes/depois" in texto:
        score += 8

    # Cabe em vídeo curto (portátil, mini, compacto)
    if any(k in texto for k in _KEYWORDS_IMPULSO):
        score += 8

    # Apelo feminino / casa / beleza / fitness
    if any(k in texto for k in _KEYWORDS_APELO):
        score += 5

    # Tendência / curiosidade
    if any(k in texto for k in _KEYWORDS_TREND):
        score += 5

    # Ticket baixo / compra por impulso
    if any(k in texto for k in ("ticket baixo", "impulso", "acessível", "barato")):
        score += 5

    # Penalidade: produto genérico demais
    if any(k in texto for k in _KEYWORDS_GENERICO):
        score -= 5

    return max(score, 0)


def _score_para_prioridade(score: int) -> str:
    """Converte score numérico em prioridade textual."""
    if score >= 25:
        return "alta"
    elif score >= 15:
        return "media"
    return "baixa"


# =================================================================
# ANTI-DUPLICATA
# =================================================================

def _detectar_linha_header(todas: list[list[str]]) -> tuple[list[str], int]:
    """
    Detecta automaticamente a linha de cabeçalho na planilha.
    Procura uma linha que contenha pelo menos 'Produto' e 'Status'.
    Retorna (headers_normalizados, indice_primeira_linha_dados).
    """
    for idx, row in enumerate(todas):
        normalized = [str(h).strip().lower() for h in row]
        if "produto" in normalized and "status" in normalized:
            return normalized, idx + 1
    return [str(h).strip().lower() for h in todas[0]], 1


def carregar_produtos_existentes() -> list[dict]:
    """Lê produtos já na Fila_de_Postagem."""
    try:
        from memory.sheets_engine import _aba, ABA_FILA
        aba = _aba(ABA_FILA)
        todas = aba.get_all_values()

        if len(todas) < 2:
            return []

        headers, start_idx = _detectar_linha_header(todas)
        existentes = []
        for row in todas[start_idx:]:
            while len(row) < len(headers):
                row.append("")
            dados = {headers[j]: row[j].strip() for j in range(len(headers))}
            if dados.get("produto"):
                existentes.append(dados)

        log.info(f"📋 {len(existentes)} produto(s) já na planilha")
        return existentes

    except Exception as e:
        log.warning(f"⚠️ Não foi possível ler existentes: {e}")
        return []


def produto_duplicado(produto: dict, existentes: list[dict]) -> bool:
    """
    Verifica se o produto já existe na fila.
    Compara por similaridade de nome (>80%) ou link idêntico.
    """
    nome_novo = produto.get("produto", "").lower().strip()
    link_novo = produto.get("link", "").lower().strip()

    for ex in existentes:
        nome_ex = ex.get("produto", "").lower().strip()
        link_ex = ex.get("link", ex.get("link_post", "")).lower().strip()

        # Link idêntico (se ambos tiverem)
        if link_novo and link_ex and link_novo == link_ex:
            return True

        # Similaridade de nome > 80%
        if nome_novo and nome_ex:
            ratio = SequenceMatcher(None, nome_novo, nome_ex).ratio()
            if ratio > 0.80:
                return True

    return False


# =================================================================
# SALVAR NA PLANILHA
# =================================================================

def salvar_produtos_na_fila(produtos: list[dict]) -> dict:
    """
    Salva produtos na aba Fila_de_Postagem.
    Se planilha falhar, salva em fallback local.

    Returns:
        {"salvos": int, "destino": "sheets" | "local", "caminho": str | None}
    """
    if not produtos:
        return {"salvos": 0, "destino": "nenhum", "caminho": None}

    # Tenta planilha
    try:
        from memory.sheets_engine import _aba, ABA_FILA, ColFila
        aba = _aba(ABA_FILA)

        salvos = 0
        for p in produtos:
            hoje = time.strftime("%d/%m/%Y %H:%M")
            aba.append_row([
                hoje,                              # Data
                p.get("produto", ""),               # Produto
                "",                                 # Roteiro
                "",                                 # Legenda
                "",                                 # CTA
                "",                                 # Hashtags
                "Pendente",                         # Status
                p.get("link", ""),                   # Link_Post
                "",                                 # Erro
                p.get("plataforma", "TikTok"),       # Plataforma
            ])
            salvos += 1
            log.info(f"  📝 Salvo na planilha: '{p['produto']}' (prioridade: {p.get('prioridade', '?')})")

        log.info(f"✅ {salvos} produto(s) salvos na planilha")
        return {"salvos": salvos, "destino": "sheets", "caminho": None}

    except Exception as e:
        log.warning(f"⚠️ Planilha falhou: {e} — salvando local")

    # Fallback local
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    caminho = PLANS_DIR / "produtos_hunter_local.json"
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(produtos, f, ensure_ascii=False, indent=2)
    log.info(f"💾 {len(produtos)} produto(s) salvos em: {caminho}")
    return {"salvos": len(produtos), "destino": "local", "caminho": str(caminho)}


# =================================================================
# FUNÇÃO PRINCIPAL
# =================================================================

def buscar_produtos_automaticamente(nicho: str = "geral", limite: int = 10) -> dict:
    """
    Busca produtos candidatos e salva na Fila_de_Postagem.

    Fluxo:
        1. Gera ideias por nicho (catálogo local)
        2. Calcula score de cada um
        3. Remove duplicados com planilha
        4. Ordena por score
        5. Salva os melhores na fila

    Args:
        nicho:  "beleza" | "casa" | "cozinha" | "fitness" | "pets" |
                "tecnologia" | "organizacao" | "maternidade" | "moda feminina" | "geral"
        limite: máximo de produtos a gerar

    Returns:
        {
            "sucesso":              bool,
            "nicho":                str,
            "gerados":              int,
            "salvos":               int,
            "ignorados_duplicados": int,
            "destino":              "sheets" | "local",
            "produtos":             list[dict],
        }
    """
    log.info(f"🔎 Product Hunter — nicho='{nicho}' | limite={limite}")

    # 1. Gera ideias
    candidatos = gerar_ideias_produtos_por_nicho(nicho, limite=limite * 2)
    total_gerado = len(candidatos)

    # 2. Calcula score e prioridade
    for c in candidatos:
        score = calcular_score_produto(c)
        c["score"] = score
        c["prioridade"] = _score_para_prioridade(score)

    # 3. Ordena por score
    candidatos.sort(key=lambda x: x.get("score", 0), reverse=True)

    # 4. Remove duplicados
    existentes = carregar_produtos_existentes()
    novos = []
    ignorados = 0
    for c in candidatos:
        if produto_duplicado(c, existentes):
            log.info(f"  ↩ Duplicado ignorado: '{c['produto']}'")
            ignorados += 1
        else:
            novos.append(c)
            # Adiciona ao existentes para evitar duplicatas internas
            existentes.append(c)

    # 5. Limita ao pedido
    novos = novos[:limite]

    # 6. Salva
    resultado_salvar = salvar_produtos_na_fila(novos)

    resumo = {
        "sucesso":              True,
        "nicho":                nicho,
        "gerados":              total_gerado,
        "salvos":               resultado_salvar["salvos"],
        "ignorados_duplicados": ignorados,
        "destino":              resultado_salvar["destino"],
        "produtos":             novos,
    }

    log.info(
        f"✅ Product Hunter concluído: "
        f"{total_gerado} gerados → {ignorados} duplicados → "
        f"{resultado_salvar['salvos']} salvos ({resultado_salvar['destino']})"
    )

    return resumo


# =================================================================
# NICHOS DISPONÍVEIS
# =================================================================

def listar_nichos() -> list[str]:
    """Retorna lista de nichos disponíveis no catálogo."""
    return sorted(_CATALOGO.keys()) + ["geral"]


# =================================================================
# TESTE VIA TERMINAL
# =================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  🔎 Product Hunter — Teste")
    print("=" * 60)

    print(f"\n📂 Nichos disponíveis: {listar_nichos()}")
    print()

    resultado = buscar_produtos_automaticamente(nicho="casa", limite=10)

    print(f"\n{'─' * 60}")
    print(f"📊 Resumo:")
    print(f"   Nicho:      {resultado['nicho']}")
    print(f"   Gerados:    {resultado['gerados']}")
    print(f"   Duplicados: {resultado['ignorados_duplicados']}")
    print(f"   Salvos:     {resultado['salvos']}")
    print(f"   Destino:    {resultado['destino']}")

    print(f"\n🏆 Produtos salvos:")
    for i, p in enumerate(resultado["produtos"], 1):
        print(f"   {i:2d}. [{p.get('prioridade', '?'):5s} | score={p.get('score', 0):2d}] {p['produto']}")
        print(f"       {p.get('observacao', '')}")

    print("=" * 60)