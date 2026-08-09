#!/usr/bin/env python3
# storyboard.py -- ROTEIRO de vídeo ORIGINAL a partir do produto. Só JSON.
#
# POR QUE SÓ JSON, E POR QUE ISSO IMPORTA
# ───────────────────────────────────────
# Hoje o Jarvis pega o vídeo de outro perfil e reedita. Isso tem dois custos: a
# dependência de achar perfis pra raspar, e — mais grave — a assinatura do dado
# de 08/08, que é conteúdo com engajamento SAUDÁVEL (3 a 5%) e alcance BAIXO
# (mediana 116). Conteúdo que ressoa e não é distribuído é o que se espera
# quando a plataforma identifica material reciclado.
#
# Este script NÃO renderiza nada. Ele devolve o roteiro pra um humano ler e
# julgar. Roteiro burro se descobre em segundos; vídeo burro custa minutos de
# render, e a gente só descobre depois.
#
# O QUE O DADO REAL DE 08/08 MANDOU PRA DENTRO DAQUI (133 posts medidos)
#
#   hook em 1ª pessoa      3,8 a 5,1% de engajamento
#     "Comprei achando que era firula e hoje não vivo mais sem 😅"   5,1%
#     "Meu braço já tava pedindo socorro nos passeios com ele… 😫"   4,7%
#   hook de urgência       1,8 a 2,2%
#     "Corre ver isso antes que esgote"                              2,2%
#   "A Shopee:" (2 linhas)  1,0 a 1,8%  em 14 posts
#
# Por isso o roteiro nasce em primeira pessoa e "A Shopee:" é PROIBIDO aqui.
# Não é gosto meu: é o que os 133 posts disseram.
#
# A REGRA QUE SEPARA PLANO DE FANTASIA
# O roteiro só pode pedir imagem que EXISTE. Um storyboard com 6 cenas
# distintas para um produto que tem 2 fotos é um documento bonito e
# irrealizável — e a gente só descobriria na hora de renderizar. Por isso as
# cenas são geradas A PARTIR dos assets disponíveis, e o validador reprova
# quem inventar.
#
# Uso:
#   python3 storyboard.py --fila 0              # 1º produto da fila
#   python3 storyboard.py --nome "Mini aspirador" --imagens 3
#   python3 storyboard.py --fila 0 --salvar

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

FILA = BASE_DIR / "shared" / "produtos_fila.json"
SAIDA_DIR = BASE_DIR / "shared" / "storyboards"

DUR_ALVO = (15, 25)          # segundos: a faixa que retém melhor em Reels
MOVIMENTOS = ("zoom_in", "zoom_out", "pan_left", "pan_right", "still")


def _log(m):
    print(f"[storyboard] {m}", flush=True)


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
            if k and k not in os.environ:
                os.environ[k] = v
        break


_carregar_env()

# ── o que o roteiro NÃO pode fazer ──────────────────────────────────────────
# Cada item aqui saiu de uma medição ou de um pedido explícito do Dre. Nada é
# preferência estética.
PROIBIDO = [
    (re.compile(r"\ba shopee\s*:", re.I),
     "'A Shopee:' — 1,0 a 1,8% de engajamento em 14 posts medidos"),
    (re.compile(r"\bcorre (ver|que|pra)\b", re.I),
     "hook de urgência — 1,8 a 2,2%, contra 3,8 a 5,1% dos de 1ª pessoa"),
    (re.compile(r"\b(fique rico|ganhe dinheiro|renda garantida)\b", re.I),
     "promessa de ganho"),
    (re.compile(r"\b(melhor do mundo|o mais barato do brasil)\b", re.I),
     "superlativo não verificável"),
]

_PROMPT = """Você é diretor de vídeos curtos para Reels de achadinhos.

PRODUTO: {nome}
PREÇO: {preco}
IMAGENS DISPONÍVEIS: {n} (referencie como asset_1 até asset_{n})

Escreva um roteiro de {dur} segundos em JSON, exatamente neste formato:

{{"hook": {{"texto": "...", "duracao": 2.5}},
  "cenas": [{{"asset": "asset_1", "movimento": "zoom_in", "duracao": 3.0,
              "texto_tela": "...", "narracao": "..."}}],
  "cta": {{"texto": "...", "duracao": 2.0}}}}

REGRAS OBRIGATÓRIAS:
1. O hook é em PRIMEIRA PESSOA, contando uma experiência real com o produto.
   Bons exemplos medidos (5,1% e 4,7% de engajamento):
     "Comprei achando que era firula e hoje não vivo mais sem 😅"
     "Meu braço já tava pedindo socorro nos passeios com ele… 😫"
2. PROIBIDO escrever "A Shopee:" ou hook de urgência ("corre", "antes que
   esgote"). Foram medidos e rendem 3x menos.
3. Só use assets de asset_1 até asset_{n}. NÃO invente imagens.
4. Movimento de cada cena: um de {movs}.
5. As durações somadas devem ficar entre {dmin} e {dmax} segundos.
6. Não prometa resultado, ganho ou superlativo que não dá pra verificar.
7. O CTA precisa DIZER O QUE FAZER, e o único caminho clicável no Instagram
   é a bio. Escreva algo que contenha "bio" — ex.: "Link na bio 👆".
   "Garanta já o seu" NÃO serve: soa bem e não diz onde clicar.
8. A NARRAÇÃO CONTINUA A HISTÓRIA DO HOOK, na mesma voz. Você está contando
   a um amigo o que aconteceu com VOCÊ — não apresentando um produto.
   NUNCA use "Apresento", "Conheça", "Descubra", "Esqueça o que você pensa",
   "Perfeito para quem busca", "Ideal para". Isso é voz de locutor e faz o
   vídeo virar propaganda no segundo 3.
     ruim: "Conheça a saia que une a delicadeza do tricot ao conforto do modal"
     bom:  "Botei pra ver e o caimento me pegou de surpresa — não marca nada"
9. Responda SÓ o JSON, sem cercas de código e sem comentários.
"""


def _por_ia(nome, preco, n_imagens, dur):
    """Pede o roteiro ao Gemini. None se não houver chave ou a resposta não
    for JSON — o chamador cai no modelo determinístico."""
    chave = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not chave:
        return None
    try:
        import requests
        prompt = _PROMPT.format(nome=nome, preco=preco or "não informado",
                                n=n_imagens, dur=dur,
                                movs=", ".join(MOVIMENTOS),
                                dmin=DUR_ALVO[0], dmax=DUR_ALVO[1])
        modelo = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
            params={"key": chave}, timeout=60,
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.9}})
        d = r.json()
        txt = d["candidates"][0]["content"]["parts"][0]["text"]
        txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
        return json.loads(txt)
    except Exception as e:
        _log(f"IA indisponível ({str(e)[:70]}) — uso o modelo base")
        return None


# Modelo determinístico: existe pra o script FUNCIONAR sem chave de API, e pra
# servir de piso de qualidade. Se a IA não superar isto, não vale a chamada.
_HOOKS_BASE = [
    "Comprei sem esperar nada e virou o que eu mais uso 😅",
    "Achei que era bobagem até resolver um problema que me irritava há meses",
    "Não sabia que precisava disso até parar de me incomodar todo dia",
    "Passei anos improvisando e resolvi por menos do que imaginava 😮‍💨",
]
_CTAS_BASE = ["Link na bio 👆", "Tá na bio pra quem quiser 👆",
              "Deixei o link na bio 👆"]


def _por_modelo(nome, preco, n):
    curto = " ".join(nome.split()[:6])
    cenas, restante = [], max(1, n)
    passos = [("zoom_in", "Olha só o que é"), ("pan_left", "De perto"),
              ("zoom_out", "Na prática"), ("still", "O resultado")]
    for i in range(restante):
        mov, txt = passos[i % len(passos)]
        cenas.append({"asset": f"asset_{i+1}", "movimento": mov,
                      "duracao": round(14 / restante, 1),
                      "texto_tela": f"{txt}: {curto}" if i == 0 else txt,
                      "narracao": ""})
    return {"hook": {"texto": random.choice(_HOOKS_BASE), "duracao": 2.5},
            "cenas": cenas,
            "cta": {"texto": random.choice(_CTAS_BASE), "duracao": 2.0}}


# Coisas que NÃO reprovam sozinhas, mas que um humano precisa olhar. Separado
# de PROIBIDO de propósito: reprovar tudo que é duvidoso faria o gerador
# devolver roteiro sem graça; não avisar faria o Dre publicar sem perceber.
_AVISOS = [
    # ESTREITADO a pedido do Dre (08/08), e ele tem razão: "minha pele é oleosa
    # e adorei a textura" é voz de marketing, não depoimento fraudulento — o
    # público sabe ler isso. O que fica marcado é AFIRMAÇÃO DE EFICÁCIA.
    #
    # E o padrão era estreito DEMAIS: no roteiro do sabonete de açafrão passou
    # "as bolinhas diminuíram muito e o crescimento dos pelos ficou mais
    # fininho" — eficácia pura, sem disparar nada, porque eu só procurava
    # "minha X sumiu". Isso quebrava o processo do Dre, que é PESQUISAR o
    # produto antes de afirmar: se o aviso não dispara, a pesquisa não
    # acontece, e a ferramenta ainda passa a sensação de que está tudo
    # conferido. Aviso que não avisa é pior que aviso nenhum.
    #
    # Agora é CONDIÇÃO + MUDANÇA, em qualquer pessoa gramatical.
    (re.compile(r"\b(bolinha|pelo|acne|cravo|mancha|frizz|queda|caspa|"
                r"celulite|olheira|ruga|estria|foliculite|espinha|oleosidade|"
                r"pel[oe]s?)\w*\b[^.!?]{0,40}?\b(sumi|diminu|reduzi|acabou|"
                r"clareou|curou|parou de|ficou mais (fin|clar|rala))", re.I),
     "afirma EFICÁCIA (condição melhorou) — confirme no anúncio antes de "
     "publicar; se o produto não entrega, tire a frase e fique só no marketing"),
    (re.compile(r"\b(emagreci|clareou minha|curou minha|acabou com (a|minha) "
                r"(acne|celulite|queda))\b", re.I),
     "promete resultado de saúde/estética — mesma conferência"),
    (re.compile(r"\b(uso h[áa]|testei por|faz \d+ (meses|semanas) que uso)\b", re.I),
     "afirma tempo de uso que ninguém teve"),
    (re.compile(r"\b(aprovado pela anvisa|dermatologicamente testado|hipoalerg)", re.I),
     "alegação regulada — confirme que está escrita no anúncio"),
    # A crítica do Dre nos 8 primeiros roteiros: "algumas narrações parecem
    # mais um comercial do que um vídeo". Achei o padrão — o HOOK é em 1ª
    # pessoa e a NARRAÇÃO troca pra voz de locutor. O vídeo começa como
    # conversa e vira propaganda no segundo 3. Estes são os marcadores.
    (re.compile(r"\b(apresento|conhe[çc]a o|conhe[çc]a a|descubra|"
                r"esque[çc]a o que voc[êe]|perfeito para quem busca|"
                r"ideal para quem)\b", re.I),
     "voz de CATÁLOGO na narração — devia continuar a história do hook"),
]


def avisar(sb):
    """Pontos que pedem olho humano. Não reprovam.

    Nasceu do 2º roteiro real: a narração dizia "minha pele é oleosa e ele não
    deixa esbranquiçado" para um protetor solar. Hook em 1ª pessoa é
    ENQUADRAMENTO e foi o que a medição aprovou; afirmação de desempenho no
    próprio corpo é DEPOIMENTO — e depoimento inventado sobre cosmético é
    publicidade enganosa, não licença criativa.

    Fica como aviso porque a linha é de julgamento: "comprei e amei" é
    inofensivo, "minha acne sumiu" não é. Quem decide é o dono da conta.
    """
    texto = " ".join(
        [(sb.get("hook") or {}).get("texto", ""), (sb.get("cta") or {}).get("texto", "")]
        + [c.get("texto_tela", "") for c in (sb.get("cenas") or [])]
        + [c.get("narracao", "") for c in (sb.get("cenas") or [])])
    return [m for regex, m in _AVISOS if regex.search(texto)]


def validar(sb, n_assets):
    """[] quando está bom; lista de problemas quando não.

    Reprovar aqui é barato. Deixar passar custa render, publicação e um post
    que a gente vai ter que explicar depois.
    """
    p = []
    if not isinstance(sb, dict):
        return ["não é um objeto JSON"]
    hook = (sb.get("hook") or {}).get("texto", "")
    if not hook.strip():
        p.append("hook vazio")
    cenas = sb.get("cenas") or []
    if not cenas:
        p.append("nenhuma cena")
    cta = (sb.get("cta") or {}).get("texto", "").strip()
    if not cta:
        p.append("CTA vazio")
    elif not re.search(r"\bbio\b", cta, re.I):
        # No Instagram, legenda e comentário não têm link clicável — a bio é o
        # único caminho. CTA sem "bio" soa bem e não instrui: o espectador quer
        # comprar e não sabe onde. Foi o defeito do 1º roteiro real gerado.
        p.append(f"CTA não diz onde clicar (falta 'bio'): {cta!r}")

    texto_todo = " ".join([hook, (sb.get("cta") or {}).get("texto", "")]
                          + [c.get("texto_tela", "") for c in cenas]
                          + [c.get("narracao", "") for c in cenas])
    for regex, motivo in PROIBIDO:
        if regex.search(texto_todo):
            p.append(f"conteúdo proibido: {motivo}")

    for i, c in enumerate(cenas, 1):
        a = c.get("asset", "")
        m = re.match(r"asset_(\d+)$", str(a))
        if not m:
            p.append(f"cena {i}: asset '{a}' fora do formato asset_N")
        elif not (1 <= int(m.group(1)) <= n_assets):
            p.append(f"cena {i}: pede {a} mas só existem {n_assets} imagem(ns)")
        if c.get("movimento") not in MOVIMENTOS:
            p.append(f"cena {i}: movimento '{c.get('movimento')}' desconhecido")

    total = ((sb.get("hook") or {}).get("duracao", 0)
             + sum(c.get("duracao", 0) for c in cenas)
             + (sb.get("cta") or {}).get("duracao", 0))
    if not (DUR_ALVO[0] - 2 <= total <= DUR_ALVO[1] + 3):
        p.append(f"duração total {total:.1f}s fora da faixa "
                 f"{DUR_ALVO[0]}-{DUR_ALVO[1]}s")
    return p


def gerar(nome, preco="", n_imagens=3, link="", nicho=""):
    dur = random.randint(*DUR_ALVO)
    sb = _por_ia(nome, preco, n_imagens, dur)
    origem_roteiro = "ia"
    if sb is None or validar(sb, n_imagens):
        if sb is not None:
            _log("   roteiro da IA reprovado na validação — uso o modelo base")
            for x in validar(sb, n_imagens):
                _log(f"      ✗ {x}")
        sb = _por_modelo(nome, preco, n_imagens)
        origem_roteiro = "modelo"
    sb["produto"] = nome
    sb["preco"] = preco
    sb["link"] = link
    sb["assets_disponiveis"] = n_imagens
    sb["nicho"] = nicho or "geral"
    # ESTE CAMPO É O EXPERIMENTO. Sem ele, daqui a um mês não dá pra separar o
    # que foi original do que foi reciclado na hora de comparar desempenho — e
    # o A/B inteiro vira opinião.
    sb["origem"] = "original"
    sb["roteiro_por"] = origem_roteiro
    return sb


def _da_fila(indice):
    d = json.loads(FILA.read_text(encoding="utf-8"))
    it = [x for x in d if isinstance(x, dict)][indice]
    nome = (it.get("campeao") or it.get("produto") or "").strip()
    # NICHO — CALCULADO do nome, não lido de campo.
    #
    # Minha 1ª tentativa leu it["classe"] achando que era o nicho. Não é:
    # `classe` é a QUALIDADE do produto ("mina_ouro", "ok"), como o
    # bio_page_builder deixa claro ao filtrar por ela. Os itens da fila não
    # guardam nicho nenhum — resultado: os 8 EDLs saíram todos com
    # @topshop.__, e o Dre viu antes de eu ver.
    #
    # Quem decide nicho neste projeto é o roteador_contas, pelo NOME do
    # produto, e é ele que a produção já usa na hora de postar. Chamar o
    # roteador em vez de inventar leitura é a mesma lição do dicionário de
    # logo duplicado: regra num lugar só.
    nicho = ""
    try:
        import roteador_contas as _RC
        nicho = (_RC.nicho_do_produto(nome) or "").strip().lower()
    except Exception as e:
        _log(f"   roteador indisponível ({str(e)[:60]}) — nicho fica 'geral'")
    return nome, it.get("preco", ""), it.get("link", ""), nicho


def revisar():
    """Mostra todos os roteiros salvos de forma legível.

    O `grep` que eu sugeri mostrava só a linha `"hook": {` — o texto fica na
    seguinte. Dava pra contar quantos rodaram e não dava pra JULGAR nenhum, que
    era o ponto. Roteiro se avalia lendo.
    """
    if not SAIDA_DIR.exists():
        _log("nenhum roteiro salvo ainda (use --salvar)")
        return 1
    arqs = sorted(SAIDA_DIR.glob("*.json"))
    _log(f"{len(arqs)} roteiro(s) em {SAIDA_DIR}\n")
    for i, f in enumerate(arqs, 1):
        try:
            sb = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        dur = ((sb.get("hook") or {}).get("duracao", 0)
               + sum(c.get("duracao", 0) for c in sb.get("cenas") or [])
               + (sb.get("cta") or {}).get("duracao", 0))
        print(f"{'─'*72}")
        print(f"{i:2}. {sb.get('produto','')[:66]}")
        print(f"    {dur:.0f}s · {sb.get('roteiro_por','?')} · "
              f"R$ {sb.get('preco') or '—'}")
        print(f"\n    HOOK  {(sb.get('hook') or {}).get('texto','')}")
        for n, c in enumerate(sb.get("cenas") or [], 1):
            print(f"    {n}. [{c.get('movimento','')}] {c.get('texto_tela','')}")
            if c.get("narracao"):
                print(f"       “{c['narracao']}”")
        print(f"    CTA   {(sb.get('cta') or {}).get('texto','')}")
        for a in avisar(sb):
            print(f"    👀 {a}")
        print()
    print(f"{'─'*72}")
    _log("quantos você publicaria SEM editar?")
    return 0


def main():
    p = argparse.ArgumentParser(description="Gera o ROTEIRO (JSON) de um vídeo original.")
    p.add_argument("--revisar", action="store_true",
                   help="lê todos os roteiros salvos, legível")
    p.add_argument("--fila", type=int, help="índice do produto em produtos_fila.json")
    p.add_argument("--nome", help="nome do produto (em vez de --fila)")
    p.add_argument("--preco", default="")
    p.add_argument("--nicho", default="", help="beleza|tech|casa|moda|pet|geral")
    p.add_argument("--imagens", type=int, default=3,
                   help="quantas imagens do produto existem (o roteiro não pode pedir mais)")
    p.add_argument("--salvar", action="store_true")
    args = p.parse_args()

    if args.revisar:
        return revisar()

    if args.fila is not None:
        nome, preco, link, nicho = _da_fila(args.fila)
    elif args.nome:
        nome, preco, link, nicho = args.nome, args.preco, "", args.nicho
    else:
        p.error("use --fila N ou --nome '...'")

    _log(f"produto: {nome}  [nicho {nicho or 'geral'}]")
    sb = gerar(nome, preco, max(1, args.imagens), link, nicho)
    problemas = validar(sb, max(1, args.imagens))

    print()
    print(json.dumps(sb, ensure_ascii=False, indent=2))
    print()
    total = (sb["hook"]["duracao"] + sum(c["duracao"] for c in sb["cenas"])
             + sb["cta"]["duracao"])
    _log(f"roteiro por: {sb['roteiro_por']} · {len(sb['cenas'])} cena(s) · "
         f"{total:.1f}s")
    if problemas:
        _log("⚠️  problemas:")
        for x in problemas:
            _log(f"      ✗ {x}")
    else:
        _log("✅ passou na validação")
    for a in avisar(sb):
        _log(f"   👀 olhe antes de publicar: {a}")

    if args.salvar:
        SAIDA_DIR.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"\W+", "_", nome.lower())[:48].strip("_")
        f = SAIDA_DIR / f"{slug}.json"
        f.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")
        _log(f"salvo em {f}")
    return 0 if not problemas else 1


if __name__ == "__main__":
    sys.exit(main())
