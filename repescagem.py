# repescagem.py
# SEGUNDA CHANCE PRO PACOTE VENCIDO.
#
# O vídeo não estraga. Ele não tem preço nem link dentro dele — só a legenda
# tem, e ela manda pro "link na bio". Quem estraga é o PRODUTO: sai do ar,
# acaba o estoque, o vendedor some. Mas o produto quase nunca é exclusivo de um
# vendedor: o mesmo item costuma estar em cinco lojas da Shopee.
#
# Então, antes de dar um pacote como perdido:
#
#   1. o produto ainda está vivo?     → atualiza preço/título e volta pra esteira
#   2. morreu?                        → procura o MESMO produto em outro
#                                        vendedor (top 1, top 2, top 3) e
#                                        re-aponta o link
#   3. não achou equivalente honesto? → fica na reserva e tenta de novo depois
#
# O passo 2 é onde mora o perigo, e é onde estão as travas: trocar por um
# produto DIFERENTE seria propaganda enganosa, porque o vídeo mostra o item
# original com as fotos dele. Um candidato só é aceito se for reconhecidamente
# o mesmo produto (ver _equivalente).
#
# Não apaga nada. Não posta nada. Não gasta crédito de vídeo.
#
# CLI:
#   python3 repescagem.py --simular          # mostra o que faria
#   python3 repescagem.py                    # repesca até 5
#   python3 repescagem.py --limite 20
#   python3 repescagem.py --status           # o que tem na reserva

import argparse
import json
import os
import re
import shutil
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

try:
    from shared.logger import get_logger
    log = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("repescagem")

BASE = Path(__file__).resolve().parent
if not (BASE / "pronto_para_postar").exists() and (BASE.parent / "pronto_para_postar").exists():
    BASE = BASE.parent

def _carregar_env():
    """Rodar do terminal não carrega o .env — só o systemd carrega. A API de
    afiliado precisa de SHOPEE_APP_ID/SECRET, e sem eles a busca nem sai:
    'a busca falhou: SHOPEE_APP_ID/SHOPEE_APP_SECRET não configurados'.
    Mesmo carregador do deploy_site. Não sobrescreve o que já veio do ambiente,
    e .env ilegível não pode derrubar o import."""
    for cand in (BASE / ".env", Path(".env")):
        if not cand.exists():
            continue
        try:
            linhas = cand.read_text(encoding="utf-8").splitlines()
        except Exception:
            return
        for linha in linhas:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:]
            chave, _, valor = linha.partition("=")
            chave = chave.strip()
            if chave and chave not in os.environ:
                os.environ[chave] = valor.strip().strip('"').strip("'")
        return


_carregar_env()

PRONTO = BASE / "pronto_para_postar"
RESERVA = BASE / "fila_vencida"
FILA = BASE / "shared" / "produtos_fila.json"
ESTADO = BASE / "shared" / "content_plans" / "repescagem_estado.json"

# Quantos pacotes por rodada. Baixo de propósito: quem volta ganha data de
# hoje, e a esteira posta o mais novo primeiro. Repescar 27 de uma vez jogaria
# todos eles na frente do conteúdo realmente novo.
LIMITE_PADRAO = 5

# Espera antes de tentar de novo um produto que não deu certo. Sem isso, cada
# rodada re-consulta a API pros mesmos mortos.
ESPERA_NOVA_TENTATIVA_H = 48

# Quando o produto morre e eu procuro substituto, o candidato precisa ser
# claramente O MESMO produto. Ver _equivalente para o porquê de cada trava.
RELEVANCIA_MIN = 0.6
PALAVRAS_MIN = 2

# --diagnostico: mostra o que a busca devolveu e por que cada candidato
# foi recusado. Sem isso, "não achei o produto" não diz se o problema é o
# termo, a API ou as travas.
DIAGNOSTICO = False


# ══════════════════════════════════════════════════════════════════════════
# ARQUIVOS
# ══════════════════════════════════════════════════════════════════════════

def _ler_json(caminho, padrao):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except Exception:
        return padrao


def _gravar_json(caminho, dados):
    p = Path(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)                       # troca atômica: nunca deixa meio arquivo


def _slug(texto: str) -> str:
    """Mesma regra do production_runner, senão o pacote não acha sua origem."""
    s = re.sub(r"\W+", "_", (texto or "").lower()).strip("_")[:40]
    return s


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t or "")
                   if unicodedata.category(c) != "Mn")


# ══════════════════════════════════════════════════════════════════════════
# API DE AFILIADO (sempre opcional — sem ela, a repescagem só não roda)
# ══════════════════════════════════════════════════════════════════════════

def _api():
    """(obter_dados_produto, buscar_produtos, gerar_link_afiliado, relevancia)."""
    for caminho in ("integrations.shopee_affiliate", "shopee_affiliate"):
        try:
            m = __import__(caminho, fromlist=["*"])
            return (m.obter_dados_produto, m.buscar_produtos,
                    m.gerar_link_afiliado, m._relevancia)
        except Exception:
            continue
    return None


# ══════════════════════════════════════════════════════════════════════════
# LIGAR O PACOTE À SUA ORIGEM
# ══════════════════════════════════════════════════════════════════════════

def _indice_da_fila(fila: list) -> dict:
    """{slug: posição na fila}. O pacote só guarda o slug do nome do produto,
    então é por aqui que ele reencontra o próprio link."""
    idx = {}
    for i, p in enumerate(fila):
        for campo in ("produto", "campeao", "nome"):
            s = _slug(p.get(campo, ""))
            if s:
                idx.setdefault(s, i)
    return idx


def _entrada_do_pacote(slug: str, fila: list, idx: dict):
    i = idx.get(slug)
    return (i, fila[i]) if i is not None else (None, None)


def _termo_do_pacote(pasta: Path) -> str:
    """O nome do produto quando a fila não tem mais a entrada.

    A fila é uma JANELA ROLANTE (~80 produtos): o que entrou há três semanas já
    saiu dela. Medido na VPS: dos 28 pacotes vencidos, zero ainda tinham
    entrada — mas 77 dos 119 da esteira tinham. Ou seja, quanto mais velho o
    pacote, menor a chance de achar a origem, que é justamente o caso da
    repescagem.

    O pacote não guarda o link, mas guarda o NOME — e com o nome dá pra achar o
    produto de novo na Shopee. É o mesmo caminho do 'produto morto', entrando
    por outra porta.
    """
    bruto = ""
    f = pasta / "titulo_youtube.txt"
    if f.exists():
        try:
            t = f.read_text(encoding="utf-8", errors="replace").strip()
            bruto = t.splitlines()[0] if t else ""
        except Exception:
            bruto = ""
    if len(re.findall(r"\w+", bruto)) < PALAVRAS_MIN:
        bruto = pasta.name.replace("_", " ")     # o slug do produto
    return _termo_de_busca(bruto)


# Lixo de título de vídeo. Não é nome de produto e só atrapalha a busca —
# "Capa transparente borda cromada shorts" não existe na Shopee.
_LIXO_BUSCA = {"shorts", "short", "reels", "reel", "tiktok", "viral", "achadinho",
               "achadinhos", "promo", "oferta", "barato", "compre", "link", "bio"}
# Quantas palavras mandar pra busca. Título de anúncio é cheio de palavra, mas
# ninguém procura na Shopee com 9 termos — e a relevância exige que a MAIORIA
# das palavras do termo apareça no título do candidato, então termo comprido
# reprova todo mundo.
PALAVRAS_BUSCA = 5


def _termo_de_busca(bruto: str) -> str:
    """Transforma o nome cru num termo que a Shopee encontra.

    Dois defeitos vistos na VPS, os dois causando 'não achei o produto':

    1. cauda de YouTube: 'Capa transparente borda cromada shorts'.
    2. corte no meio da palavra: o slug tem 40 caracteres, então sobra
       'Fones De O', 'Porcelana Ko', 'Estreito Ces'. Palavra picada não casa
       com nada e ainda conta contra a relevância.
    """
    t = re.sub(r"[^\w\s]", " ", bruto or "")
    palavras = [p for p in t.split() if p]
    # a última pode ser um pedaço de palavra, cortesia do corte em 40 chars
    if len(palavras) > PALAVRAS_MIN and len(palavras[-1]) <= 3:
        palavras.pop()
    uteis = []
    for p in palavras:
        b = p.lower()
        if b in _LIXO_BUSCA or b in _LIGACAO or len(p) < 2:
            continue                         # 'de'/'para' só gastam vaga
        uteis.append(p)
        if len(uteis) >= PALAVRAS_BUSCA:
            break                            # termo curto acha; termo longo não
    return " ".join(uteis)


_LIGACAO = {"de", "da", "do", "dos", "das", "para", "pra", "com", "em", "no",
            "na", "nos", "nas", "e", "o", "a", "os", "as", "um", "uma", "por"}


# ══════════════════════════════════════════════════════════════════════════
# O SUBSTITUTO PRECISA SER O MESMO PRODUTO
# ══════════════════════════════════════════════════════════════════════════

def _equivalente(termo: str, titulo: str, relevancia) -> bool:
    """O candidato é o MESMO produto que o vídeo mostra?

    Três travas, e cada uma existe por um motivo:

    1. termo precisa ter palavra útil. _relevancia devolve 1.0 quando a keyword
       não tem nenhuma palavra significativa — e a fila real tem entrada
       chamada "2 mil vendidos". Sem esta trava, um nome-lixo aprovaria
       QUALQUER produto do resultado.
    2. relevância alta: a maioria das palavras do termo tem que aparecer no
       título do candidato.
    3. pelo menos 2 palavras em comum: com termo de 1 palavra ("escova"), a
       relevância dá 1.0 fácil e casaria escova de dente com escova secadora.

    O que ela NÃO pega: variação de modelo/capacidade (500ml vs 1L) e cor. Pra
    esse caso o vídeo continua batendo no essencial, então eu aceito.
    """
    palavras_termo = {p for p in re.findall(r"\w+", _sem_acento(termo).lower())
                      if len(p) >= 3}
    if len(palavras_termo) < PALAVRAS_MIN:
        return False
    palavras_tit = {p for p in re.findall(r"\w+", _sem_acento(titulo).lower())
                    if len(p) >= 3}
    if len(palavras_termo & palavras_tit) < PALAVRAS_MIN:
        return False
    try:
        return float(relevancia(termo, titulo)) >= RELEVANCIA_MIN
    except Exception:
        return False


def _fornecedores(termo: str, excluir_item=None, api=None) -> list:
    """Top vendedores do MESMO produto, do melhor pro pior.

    Ordena por vendas: entre lojas do mesmo item, a que mais vendeu tende a ter
    estoque e a não sumir na semana seguinte — que é justamente o problema que
    a repescagem existe pra resolver.
    """
    _obter, buscar, _link, relevancia = api
    r = buscar(termo, limite=20, ordenar_por=1)        # 1 = mais vendidos
    if not r.get("ok"):
        if DIAGNOSTICO:
            log.info(f"      [diag] a busca falhou: {str(r.get('erro'))[:100]}")
        return []
    achados = r.get("produtos") or []
    if DIAGNOSTICO:
        log.info(f"      [diag] termo {termo!r} → {len(achados)} resultado(s)")
    saida, recusados = [], []
    for p in achados:
        if excluir_item and str(p.get("item_id")) == str(excluir_item):
            continue                                   # esse é o que morreu
        titulo = p.get("nome") or ""
        if not _equivalente(termo, titulo, relevancia):
            recusados.append((titulo, relevancia(termo, titulo)))
            continue
        saida.append({
            "titulo": titulo,
            "item_id": p.get("item_id"),
            "shop_id": p.get("shop_id"),
            "preco": p.get("preco") or 0,
            "vendas": p.get("vendas") or 0,
            "link": p.get("offer_link") or p.get("product_link") or "",
            "relevancia": round(float(relevancia(termo, titulo)), 2),
        })
    if DIAGNOSTICO and not saida and recusados:
        log.info(f"      [diag] {len(recusados)} recusado(s) por não serem o "
                 f"mesmo produto (precisa de rel>={RELEVANCIA_MIN} e "
                 f"{PALAVRAS_MIN}+ palavras em comum):")
        for tit, rel in sorted(recusados, key=lambda x: -x[1])[:5]:
            log.info(f"               rel {rel:.2f}  {tit[:62]}")
    saida.sort(key=lambda x: (x["relevancia"], x["vendas"]), reverse=True)
    return saida[:3]                                   # top 1, top 2, top 3


# ══════════════════════════════════════════════════════════════════════════
# DEVOLVER PRA ESTEIRA
# ══════════════════════════════════════════════════════════════════════════

def _devolver(pasta: Path, simular: bool) -> bool:
    """Move o pacote de volta pra esteira com data de hoje.

    A data nova é o ponto: a esteira posta o mais novo primeiro, e a oferta
    deste pacote acabou de ser revalidada — ela é, de fato, a mais fresca que
    existe. Por isso o limite por rodada é baixo.
    """
    destino = PRONTO / pasta.name
    if destino.exists():
        log.warning(f"   ⚠️  '{pasta.name}' já está na esteira — deixei na reserva")
        return False
    if simular:
        return True
    PRONTO.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pasta), str(destino))
    agora = time.time()
    os.utime(destino, (agora, agora))
    return True


# ══════════════════════════════════════════════════════════════════════════
# O CICLO
# ══════════════════════════════════════════════════════════════════════════

def _pode_tentar(slug: str, estado: dict) -> bool:
    ultima = (estado.get(slug) or {}).get("ultima_tentativa", 0)
    return (time.time() - ultima) >= ESPERA_NOVA_TENTATIVA_H * 3600


def _anotar(estado: dict, slug: str, motivo: str, extra: dict = None):
    estado[slug] = {"ultima_tentativa": time.time(),
                    "quando": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "motivo": motivo, **(extra or {})}


def repescar(limite: int = LIMITE_PADRAO, simular: bool = False) -> dict:
    resumo = {"revalidados": 0, "trocados": 0, "reencontrados": 0,
              "reserva": 0, "sem_origem": 0}

    if not RESERVA.exists():
        log.info("Nada na reserva — nenhum pacote venceu ainda.")
        return resumo

    api = _api()
    if api is None:
        log.warning("API de afiliado indisponível — não dá pra conferir "
                    "se os produtos estão vivos. Nada foi movido.")
        return resumo
    obter, _buscar, gerar_link, _rel = api

    fila = _ler_json(FILA, [])
    if not isinstance(fila, list) or not fila:
        log.warning(f"{FILA.name} vazio ou ilegível — sem ele não dá pra saber "
                    "qual produto cada pacote é. Nada foi movido.")
        return resumo
    idx = _indice_da_fila(fila)
    estado = _ler_json(ESTADO, {})

    # mais novo primeiro: o que venceu ontem tem mais chance de ainda estar bom
    pastas = sorted((p for p in RESERVA.iterdir() if p.is_dir()),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    log.info(f"🎣 Reserva: {len(pastas)} pacote(s). Vou tentar até {limite}."
             + ("  [SIMULAÇÃO]" if simular else ""))

    tentados = 0
    for pasta in pastas:
        if tentados >= limite:
            break
        slug = pasta.name
        if not _pode_tentar(slug, estado):
            continue
        tentados += 1
        i, entrada = _entrada_do_pacote(slug, fila, idx)

        if entrada is None:
            # a fila rolou e perdeu este produto. Não é o fim: o nome está no
            # pacote, e com ele dá pra procurar o produto de novo.
            termo = _termo_do_pacote(pasta)
            log.info(f"   ? '{slug}': fora da fila — procurando por "
                     f"'{termo[:44]}'")
            alts = _fornecedores(termo, api=api)
            if not alts:
                log.info("      não achei o produto na Shopee — fica na reserva")
                _anotar(estado, slug, "sem_origem")
                resumo["sem_origem"] += 1
                continue
            melhor = alts[0]
            if not melhor["link"]:
                _anotar(estado, slug, "sem_link")
                resumo["reserva"] += 1
                continue
            log.info(f"      ↺ {melhor['titulo'][:50]}  R$ {melhor['preco']:.2f}"
                     f"  ({melhor['vendas']} vendas)")
            if not simular:
                # volta pra fila: sem isso ele sai da esteira mas não aparece
                # na vitrine, e o post manda pra um produto que o site não tem
                fila.append({"produto": termo, "campeao": melhor["titulo"],
                             "link": melhor["link"], "preco": melhor["preco"],
                             "imagem": "", "plataforma": "shopee",
                             "origem": "repescagem", "ts": int(time.time()),
                             "fornecedores": alts})
                idx[slug] = len(fila) - 1
            if _devolver(pasta, simular):
                _anotar(estado, slug, "reencontrado", {"item": melhor["item_id"]})
                resumo["reencontrados"] += 1
            continue

        link = (entrada.get("link") or "").strip()
        termo = (entrada.get("campeao") or entrada.get("produto") or "").strip()

        # 1) o produto ainda está vivo?
        d = obter(link) if link else {"ok": False, "erro": "sem link"}
        if d.get("ok") and (d.get("preco") or 0) > 0:
            if not simular:
                entrada["preco"] = d["preco"]
                entrada["imagem"] = d.get("imagem") or entrada.get("imagem", "")
                if d.get("titulo"):
                    entrada["campeao"] = d["titulo"]
            if _devolver(pasta, simular):
                log.info(f"   ✅ '{slug}': vivo (R$ {d['preco']:.2f}) → volta pra esteira")
                _anotar(estado, slug, "revalidado")
                resumo["revalidados"] += 1
            continue

        # 2) morreu — o mesmo produto em outro vendedor
        log.info(f"   ✖ '{slug}': fora do ar ({str(d.get('erro'))[:60]}). "
                 "Procurando outro vendedor...")
        alts = _fornecedores(termo, excluir_item=d.get("item_id"), api=api)
        if not alts:
            log.info(f"      sem equivalente honesto — fica na reserva")
            _anotar(estado, slug, "sem_equivalente")
            resumo["reserva"] += 1
            continue

        melhor = alts[0]
        novo_link = melhor["link"]
        if not novo_link:                       # veio sem link de afiliado
            g = gerar_link(f"https://shopee.com.br/product/"
                           f"{melhor['shop_id']}/{melhor['item_id']}")
            novo_link = g.get("short_link", "") if g.get("ok") else ""
        if not novo_link:
            log.info("      achei o produto mas não consegui o link — reserva")
            _anotar(estado, slug, "sem_link")
            resumo["reserva"] += 1
            continue

        log.info(f"      → {melhor['titulo'][:52]}  R$ {melhor['preco']:.2f}"
                 f"  ({melhor['vendas']} vendas, rel {melhor['relevancia']})")
        if not simular:
            entrada["link"] = novo_link
            entrada["preco"] = melhor["preco"]
            entrada["campeao"] = melhor["titulo"]
            # guarda os outros: se este também morrer, desce a lista sem
            # precisar buscar de novo
            entrada["fornecedores"] = alts
        if _devolver(pasta, simular):
            _anotar(estado, slug, "trocado", {"para": melhor["item_id"]})
            resumo["trocados"] += 1

    if not simular:
        _gravar_json(FILA, fila)
        _gravar_json(ESTADO, estado)

    log.info(f"🎣 {resumo['revalidados']} revalidado(s), {resumo['trocados']} "
             f"trocado(s) de vendedor, {resumo['reencontrados']} reencontrado(s) "
             f"pelo nome, {resumo['reserva'] + resumo['sem_origem']} seguem na reserva")
    return resumo


def status():
    n_reserva = len([p for p in RESERVA.iterdir() if p.is_dir()]) if RESERVA.exists() else 0
    n_esteira = len([p for p in PRONTO.iterdir()
                     if p.is_dir() and (p / "video.mp4").exists()]) if PRONTO.exists() else 0
    estado = _ler_json(ESTADO, {})
    print(f"\n  🎬 esteira:  {n_esteira}")
    print(f"  🎣 reserva:  {n_reserva}")
    if estado:
        from collections import Counter
        c = Counter(v.get("motivo", "?") for v in estado.values())
        print("\n  últimas tentativas:")
        for motivo, n in c.most_common():
            print(f"     {motivo:16} {n}")
        prontos = sum(1 for s in estado if _pode_tentar(s, estado))
        print(f"\n  {prontos} liberado(s) pra nova tentativa "
              f"(espera de {ESPERA_NOVA_TENTATIVA_H}h entre tentativas)")
    print()


def main():
    ap = argparse.ArgumentParser(description="Segunda chance pro pacote vencido")
    ap.add_argument("--simular", action="store_true", help="não move nem grava")
    ap.add_argument("--limite", type=int, default=LIMITE_PADRAO,
                    help=f"quantos por rodada (padrão {LIMITE_PADRAO})")
    ap.add_argument("--status", action="store_true", help="só mostra o estado")
    ap.add_argument("--diagnostico", action="store_true",
                    help="mostra o que a busca devolveu e por que recusou")
    a = ap.parse_args()
    global DIAGNOSTICO
    DIAGNOSTICO = a.diagnostico
    if a.status:
        status()
        return 0
    repescar(limite=a.limite, simular=a.simular)
    return 0


if __name__ == "__main__":
    sys.exit(main())
