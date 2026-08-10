#!/usr/bin/env python3
# edl.py -- STORYBOARD -> EDL (Edit Decision List). Ainda sem renderizar.
#
# A SEPARAÇÃO QUE MANDA AQUI
# ──────────────────────────
#   storyboard.py  decide O QUE comunicar  (hook, narração, ordem da história)
#   edl.py         decide COMO comunicar   (corte, zoom, legenda, som)
#
# Não é elegância: é o que permite trocar o FFmpeg por outro renderizador, ou
# gerar corte diferente pra Reels e pra TikTok, SEM tocar no cérebro criativo.
# Mesma separação que já salvou este projeto em shared/termos.py,
# shared/categorias.py e shared/marca.py — regra num lugar, uso em vários.
#
# A NARRAÇÃO COMANDA O CORTE, NÃO O CRONÔMETRO
# Cortar a cada N segundos vira slideshow. O corte cai onde o SENTIDO muda:
# "ele gira," | "acende as luzes" | "e ainda foge". Por isso a narração é
# quebrada em BATIDAS e cada batida ganha seu tempo pela quantidade de fala.
#
# MAIS CORTES QUE IMAGENS — e isso é legítimo
# O storyboard só pode pedir imagem que existe (3 fotos = 3 cenas). Mas 3
# cortes em 16 segundos é slideshow. A saída é PUNCH-IN: a mesma foto cortada
# de novo com enquadramento diferente é um corte de verdade pro olho, e não
# inventa asset nenhum. É assim que editor humano trabalha com pouco material.
#
# RITMO POR SEÇÃO
#   hook            corte rápido (0,8-1,5s)  — a história começa antes de o
#                   espectador perceber que é anúncio
#   desenvolvimento corte médio  (1,6-3,0s)  — tempo de ver o produto
#   cta             estável                  — decisão precisa de calma
#
# SÓ GERA JSON. O render é o próximo passo, e ele merece ser julgado antes.
#
# Uso:
#   python3 edl.py --storyboard shared/storyboards/xxx.json
#   python3 edl.py --todos --salvar

import argparse
import json
import math
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SB_DIR = BASE_DIR / "shared" / "storyboards"
SAIDA_DIR = BASE_DIR / "shared" / "edl"

FPS = 30
RESOLUCAO = (1080, 1920)

# Velocidade de locução em português, em caracteres por segundo. 15 é o meio
# de uma fala natural de Reels — abaixo disso arrasta, acima atropela. Usada
# só pra ESTIMAR; quando existir o MP3 da narração, a duração real dele manda
# e este número é ignorado.
CPS = 15.0

RITMO = {                       # (min, max) de segundos por corte
    "hook": (0.8, 1.5),
    "desenvolvimento": (1.6, 3.0),
    "cta": (2.0, 3.0),
}

# Zoom por movimento: (início, fim). Valores pequenos de propósito — zoom forte
# em foto de e-commerce estoura o pixel e denuncia que é imagem parada.
ZOOM = {
    "zoom_in":   (1.00, 1.14),
    "zoom_out":  (1.14, 1.00),
    "pan_left":  (1.10, 1.10),
    "pan_right": (1.10, 1.10),
    "still":     (1.04, 1.04),
}
PAN = {"pan_left": (0.10, -0.10), "pan_right": (-0.10, 0.10)}

# SFX só quando AGREGA. Vídeo com efeito a cada corte cansa em 5 segundos e
# soa amador — o som tem que marcar acontecimento, não pontuar edição.
MAX_SFX = 4

# TRANSIÇÃO ENTRE CORTES. O padrão é CORTE SECO, e isso é escolha: fade e
# slide entre planos envelheceram nesse formato e denunciam edição amadora —
# Reels e TikTok vivem de corte seco. Transição só na troca de SEÇÃO, onde ela
# tem função narrativa: avisar que a história mudou de capítulo.
TRANSICAO_SECAO = {("hook", "desenvolvimento"): "flash",
                   ("desenvolvimento", "cta"): "whip"}

# ANIMAÇÃO DE TEXTO. Aqui a ausência ERA defeito: nesse formato o texto ENTRA,
# não aparece. Texto que surge estático parece legenda de documentário e some
# no meio do movimento da imagem.
ANIM_TEXTO = {
    "hook":     {"entrada": "pop", "saida": "fade", "dur_entrada": 0.25},
    "destaque": {"entrada": "slide_cima", "saida": "fade", "dur_entrada": 0.2},
    "legenda":  {"entrada": "pop_palavra", "saida": "corte", "dur_entrada": 0.12},
    "cta":      {"entrada": "escala", "saida": "nenhuma", "dur_entrada": 0.3},
}

# Piso de duração de corte. Abaixo disto o olho registra piscada, não corte —
# e a linha do tempo da saia gerou um de 0,34s. O validador avisava e o arquivo
# era salvo assim mesmo: aviso que não impede é aviso que vira post.
PISO_CORTE = 0.5

# Teto de zoom acumulado. O punch-in progressivo somava 0,05 por corte e chegou
# a 1,25 no Kit Cachos — 25% de crop numa foto de e-commerce arrisca cortar o
# produto fora do quadro, que é o oposto do objetivo.
ZOOM_MAX = 1.18


def _log(m):
    print(f"[edl] {m}", flush=True)


def _batidas(texto: str) -> list:
    """Quebra a narração em BATIDAS de sentido.

    Corta em pontuação forte e em conectivo ("e", "mas", "até que", "aí"),
    porque é aí que o pensamento vira — e é aí que o olho aceita um corte. Um
    corte no meio de "acende as | luzes" é ruído; entre "ele gira," e "acende
    as luzes" é edição.
    """
    t = re.sub(r"\s+", " ", (texto or "").strip())
    if not t:
        return []
    partes = re.split(r"(?<=[.!?…])\s+|(?<=[,;:])\s+(?=e |mas |aí |até |porque |que )", t)
    fora = []
    for p in partes:
        p = p.strip(" ,;:")
        if not p:
            continue
        # batida curta demais gruda na anterior: corte de 0,3s é piscada, não corte
        if fora and len(p) < 14:
            fora[-1] = f"{fora[-1]} {p}"
        else:
            fora.append(p)
    return fora or [t]


def _dur_fala(texto: str) -> float:
    return max(0.6, round(len(texto or "") / CPS, 2))


def _legendas(texto: str, inicio: float, fim: float, palavras=4) -> list:
    """Legenda em blocos de 2-5 palavras, sincronizada com a fala.

    Bloco curto porque metade assiste sem som e legenda comprida obriga a ler
    em vez de ver. O tempo é repartido pelo TAMANHO de cada bloco, não em
    fatias iguais — bloco com palavra grande precisa de mais tempo na tela.
    """
    palavras_lista = (texto or "").split()
    if not palavras_lista:
        return []
    blocos = [" ".join(palavras_lista[i:i + palavras])
              for i in range(0, len(palavras_lista), palavras)]
    total = sum(len(b) for b in blocos) or 1
    fora, t = [], inicio
    for b in blocos:
        d = (fim - inicio) * (len(b) / total)
        fora.append({"inicio": round(t, 2), "fim": round(t + d, 2), "texto": b})
        t += d
    return fora


def _cortes(dur_total: float, secao: str) -> int:
    """Quantos cortes cabem nesta seção, pelo ritmo dela."""
    lo, hi = RITMO.get(secao, RITMO["desenvolvimento"])
    alvo = (lo + hi) / 2
    return max(1, round(dur_total / alvo))


MUSICAS = BASE_DIR / "shared" / "musicas.json"


def _musica(nicho: str, energia: str = "media", precisa_instrumental=False,
            semente: str = "") -> dict:
    """Escolhe a faixa da biblioteca. {} quando não há candidata.

    O Dre olhou a biblioteca do Instagram e a conclusão foi direta: os "áudios
    originais" de terceiros são estourados e esquisitos, sem condição de uso —
    música COM NOME é o caminho. A lista é mantida à mão porque o Instagram não
    expõe API pra isso, e listar faixa indisponível geraria vídeo que não posta.
    
    A ordem de preferência é por REELS: quantos vídeos já usam a faixa. É esse
    o sinal que a plataforma premia na distribuição, e distribuição é o gargalo
    medido (mediana de alcance 116).

    `precisa_instrumental` existe pro modo narracao_viral: faixa cantada por
    baixo de narração vira duas vozes brigando. Instrumental popular junta o
    empurrão do algoritmo com a história, sem competir.
    """
    try:
        faixas = json.loads(MUSICAS.read_text(encoding="utf-8"))["faixas"]
    except Exception:
        return {}
    cand = [f for f in faixas
            if (not precisa_instrumental or f.get("instrumental"))
            and (nicho in (f.get("nichos") or []) or "geral" in (f.get("nichos") or []))]
    if not cand:
        # sem faixa do nicho, aceita qualquer uma que sirva ao modo — melhor
        # música fora do tom que vídeo mudo
        cand = [f for f in faixas
                if not precisa_instrumental or f.get("instrumental")]
    if not cand:
        return {}
    # PREFERE faixa que lista o nicho ESPECÍFICO. Sem isso, quem tem "geral"
    # na lista ganha sempre e todo nicho recebe a mesma música.
    especifica = [f for f in cand if nicho in (f.get("nichos") or [])]
    cand = especifica or cand
    mesma = [f for f in cand if f.get("energia") == energia]
    cand = mesma or cand

    # E VARIA entre os candidatos bons. Pegar sempre o de mais reels fez as 8
    # linhas do tempo saírem com "Wonderful (Instrumental)" — o feed inteiro
    # com a mesma música, que é justamente o oposto de parecer conteúdo
    # humano. A escolha é determinística (mesmo produto = mesma faixa, então
    # regerar não troca a trilha), mas distribuída pelo nome do produto.
    cand.sort(key=lambda f: -f.get("reels", 0))
    topo = cand[:4] or cand          # só entre as mais usadas; o resto não
    return topo[hash(semente) % len(topo)] if topo else {}


def _template(nicho: str) -> dict:
    """A camada de MARCA que o render aplica por cima da trilha visual.

    O EDL não desenhava isso e o render sairia SEM a marca TopShop — buraco
    que o Dre encontrou perguntando "ele já joga no template pronto?".
    A resposta certa é: UM render só, com o template como CAMADA persistente.
    Colar dois vídeos daria borda, salto de cor e perda de qualidade.

    Logo e handle saem de shared/marca.py e contas.json — a mesma regra que já
    decide isso na produção de hoje. Duplicar aqui seria repetir o dicionário
    que pôs a logo do @topshop.__ num vídeo do @topshopcasa_.
    """
    try:
        from shared.marca import logo_escolhida
        logo = logo_escolhida(nicho)
    except Exception:
        logo = "logo_ts.png"
    handle = ""
    try:
        contas = json.loads((BASE_DIR / "contas.json").read_text(encoding="utf-8"))
        for chave, c in contas.items():
            if (chave if chave != "_default" else c.get("nicho", "geral")) == (nicho or "geral"):
                handle = c.get("handle", "")
                break
    except Exception:
        pass
    return {"nicho": nicho or "geral", "logo": logo, "handle": handle,
            "camada": "por_cima", "zona_superior": ["logo", "handle"],
            "zona_inferior": ["cta_fixo", "marca_dagua"],
            "obs": "render ÚNICO: a camada acompanha o vídeo inteiro"}


# MODO DE ÁUDIO — variável de EXPERIMENTO, não decisão de gosto.
#
#   narracao     voz conta a história; música em 0.12 ao fundo.
#   viral        áudio em alta em primeiro plano; SEM narração, a história é
#                contada só por texto na tela.
#
# Áudio em alta é alavanca de ALCANCE — a plataforma distribui melhor quem usa
# som que está bombando, e alcance é justamente nosso gargalo (mediana 116).
# Mas os dois COMPETEM: narração por cima de música alta vira ruído, e música
# baixa demais perde o efeito de estar "usando o som do momento".
#
# Qual ganha é pergunta pra métrica, não pra mim. Por isso é campo, e por isso
# o EDL registra qual foi usado — sem isso o A/B não separa a causa depois.
#   narracao_viral  narração conduz E o som em alta toca por baixo, baixinho.
#                   HIPÓTESE NÃO VERIFICADA: não sei se a plataforma credita o
#                   uso do som quando ele está mixado baixo. Se creditar, é o
#                   melhor dos dois mundos; se não, é só uma música de fundo
#                   com nome bonito. Testável — e é exatamente por isso que
#                   está aqui como MODO e não como padrão escondido.
MODOS_AUDIO = ("narracao", "viral", "narracao_viral")

# O HOOK NÃO É NARRADO — e isso é decisão, não esquecimento.
#
# No template publicado o hook fica ESCRITO no alto, e fica o vídeo inteiro.
# Narrá-lo faz a voz ler em voz alta o que a pessoa acabou de ler sozinha, e
# gasta os 3 primeiros segundos — os únicos que decidem se ela continua —
# repetindo informação. O Dre ouviu e foi direto: "no início a narração repete
# o hook, vamos remover e já começar direto".
#
# A seção do hook continua existindo como BATIDA VISUAL: dois cortes rápidos
# que abrem o vídeo em movimento. Só que curta, porque sem fala ela é silêncio —
# e silêncio no começo é diferente de silêncio no meio, mas 2,5s ainda é muito.
NARRAR_HOOK = False
BATIDA_HOOK = 0.9              # segundos de abertura visual, sem voz


def montar(sb: dict, modo_audio: str = "narracao",
           narrar_hook: bool = NARRAR_HOOK) -> dict:
    """Storyboard -> EDL. Não chama IA: é decisão de edição, não de criação."""
    visual, texto_tr, audio, sfx_usados = [], [], [], 0
    secoes = []                    # onde cada CENA começa e termina
    t = 0.0

    # ── HOOK ────────────────────────────────────────────────────────────────
    h = sb.get("hook") or {}
    dur_hook = float(h.get("duracao") or 2.5)
    if not narrar_hook:
        # sem voz, a abertura vira batida visual curta em vez de 2,5s calados
        dur_hook = min(dur_hook, BATIDA_HOOK)
    asset_hook = "asset_1"
    n_cortes = _cortes(dur_hook, "hook")
    passo = dur_hook / n_cortes
    for i in range(n_cortes):
        # punch-in progressivo: mesma foto, enquadramento mais fechado a cada
        # corte. Dá movimento sem exigir imagem nova.
        z = round(1.00 + 0.06 * i, 3)
        visual.append({"inicio": round(t, 2), "fim": round(t + passo, 2),
                       "asset": asset_hook, "movimento": "zoom_in",
                       "zoom_de": z, "zoom_para": round(z + 0.06, 3),
                       "secao": "hook"})
        t += passo
    secoes.append({"tipo": "hook", "inicio": 0.0, "fim": round(t, 3),
                   "tem_narracao": bool(narrar_hook
                                        and (h.get("texto") or "").strip())})
    texto_tr.append({"inicio": 0.0, "fim": round(dur_hook, 2),
                     "texto": h.get("texto", ""), "estilo": "hook",
                     "posicao": "centro_alto"})
    if narrar_hook:
        audio.append({"inicio": 0.0, "tipo": "narracao",
                      "texto": h.get("texto", "")})
    if sfx_usados < MAX_SFX:
        audio.append({"inicio": 0.0, "tipo": "sfx", "som": "whoosh"})
        sfx_usados += 1

    # ── DESENVOLVIMENTO ─────────────────────────────────────────────────────
    for cena in sb.get("cenas") or []:
        asset = cena.get("asset", "asset_1")
        mov = cena.get("movimento", "zoom_in")
        dur_cena = float(cena.get("duracao") or 3.0)
        narr = cena.get("narracao", "")
        batidas = _batidas(narr) or [""]

        # o tempo da cena é repartido pelo TAMANHO DA FALA de cada batida —
        # é isso que faz o corte cair onde o sentido muda
        pesos = [_dur_fala(b) for b in batidas]
        soma = sum(pesos) or 1.0
        # Batida cujo tempo ficaria abaixo do piso é FUNDIDA na anterior. O
        # corte de 0,34s da saia nasceu aqui: a batida era curta em fala, e o
        # tempo proporcional virou piscada. Filtrar por caracteres não bastava
        # porque o que decide é a fatia do tempo DESTA cena.
        while len(batidas) > 1:
            menor = min(range(len(batidas)), key=lambda i: pesos[i])
            if dur_cena * (pesos[menor] / soma) >= PISO_CORTE:
                break
            alvo = menor - 1 if menor > 0 else 1
            batidas[alvo] = f"{batidas[alvo]} {batidas[menor]}".strip()
            pesos[alvo] += pesos[menor]
            del batidas[menor], pesos[menor]
            soma = sum(pesos) or 1.0
        ini_cena = t
        _, teto = RITMO["desenvolvimento"]
        for i_b, (b, peso) in enumerate(zip(batidas, pesos)):
            d = dur_cena * (peso / soma)
            # Batida sem conectivo pode dar um plano de 4-5s no meio do vídeo —
            # exatamente o slideshow que a gente quer evitar. Quando passa do
            # teto do ritmo, o plano é REPARTIDO em punch-ins da mesma imagem.
            # A legenda continua sendo uma só, cobrindo a batida inteira: o
            # olho recebe corte, o ouvido recebe a frase inteira.
            # CEIL, não round: com d=4,0s e teto=3,0s o round dava 1 e o plano
            # de 4 segundos passava inteiro — foi o que aconteceu nas Taças e
            # no Calção. Teto é limite, não sugestão.
            n_sub = max(1, math.ceil(d / teto - 0.001))
            # e nunca fatiar abaixo do piso: 3 cortes de 0,4s é pior que 1 de 1,2s
            while n_sub > 1 and d / n_sub < PISO_CORTE:
                n_sub -= 1
            zi, zf = ZOOM.get(mov, ZOOM["zoom_in"])
            for k in range(n_sub):
                # o zoom AVANÇA a cada corte da cena. Sem isso, dois cortes
                # seguidos mostram o mesmo enquadramento e parecem falha de
                # vídeo, não edição.
                # o deslocamento é limitado: sem teto ele somava até 1,25
                desloc = min(0.05 * (i_b + k), max(0.0, ZOOM_MAX - max(zi, zf)))
                item = {"inicio": round(t, 2), "fim": round(t + d / n_sub, 2),
                        "asset": asset, "movimento": mov,
                        "zoom_de": round(zi + desloc, 3),
                        "zoom_para": round(zf + desloc, 3),
                        "secao": "desenvolvimento"}
                if mov in PAN:
                    item["pan_de"], item["pan_para"] = PAN[mov]
                visual.append(item)
                t += d / n_sub
            if b:
                texto_tr.extend([{**leg, "estilo": "legenda",
                                  "posicao": "centro_baixo"}
                                 for leg in _legendas(b, t - d, t)])
        if cena.get("texto_tela"):
            texto_tr.append({"inicio": round(ini_cena, 2),
                             "fim": round(min(ini_cena + 2.2, t), 2),
                             "texto": cena["texto_tela"], "estilo": "destaque",
                             "posicao": "topo"})
        if narr:
            audio.append({"inicio": round(ini_cena, 2), "tipo": "narracao",
                          "texto": narr})
        if sfx_usados < MAX_SFX:
            audio.append({"inicio": round(ini_cena, 2), "tipo": "sfx",
                          "som": "pop"})
            sfx_usados += 1
        # A FRONTEIRA DA CENA VAI PRO EDL. Sem isso o render só sabe onde cada
        # NARRAÇÃO começa — e cena sem narração some dentro do trecho anterior.
        # Foi assim que uma linha do tempo de 18,6s desabou pra 6,4s quando o
        # roteiro veio sem fala nas cenas: o trecho inteiro encolheu pro tamanho
        # da fala do hook, levando junto três cenas que não falavam nada.
        secoes.append({"tipo": "cena", "inicio": round(ini_cena, 3),
                       "fim": round(t, 3), "tem_narracao": bool(narr.strip())})

    # ── CTA ─────────────────────────────────────────────────────────────────
    c = sb.get("cta") or {}
    dur_cta = float(c.get("duracao") or 2.0)
    # UM plano só, sem corte: decisão de compra precisa de calma. Cortar aqui
    # rouba a atenção justamente de onde ela deveria pousar.
    visual.append({"inicio": round(t, 2), "fim": round(t + dur_cta, 2),
                   "asset": "asset_1", "movimento": "still",
                   "zoom_de": 1.04, "zoom_para": 1.04, "secao": "cta"})
    texto_tr.append({"inicio": round(t, 2), "fim": round(t + dur_cta, 2),
                     "texto": c.get("texto", ""), "estilo": "cta",
                     "posicao": "centro"})
    audio.append({"inicio": round(t, 2), "tipo": "narracao",
                  "texto": c.get("texto", "")})
    secoes.append({"tipo": "cta", "inicio": round(t, 3),
                   "fim": round(t + dur_cta, 3),
                   "tem_narracao": bool((c.get("texto") or "").strip())})
    if sfx_usados < MAX_SFX:
        audio.append({"inicio": round(t, 2), "tipo": "sfx", "som": "impacto"})
    t += dur_cta

    nicho_v = sb.get("nicho") or "geral"
    if modo_audio == "viral":
        # sem narração: o áudio em alta é o protagonista e a história é
        # contada pelo texto. As legendas já existem na trilha de texto, então
        # o vídeo continua legível — o que muda é quem conduz.
        audio = [a for a in audio if a["tipo"] != "narracao"]
        m = _musica(nicho_v, "alta", semente=sb.get("produto", ""))
        audio.append({"inicio": 0.0, "tipo": "musica_alta", "volume": 0.9,
                      "faixa": m.get("nome", ""), "artista": m.get("artista", ""),
                      "reels": m.get("reels", 0),
                      "obs": "conduz o vídeo; a história vai pelo texto"})
    elif modo_audio == "narracao_viral":
        m = _musica(nicho_v, "media", precisa_instrumental=True,
                    semente=sb.get("produto", ""))
        audio.append({"inicio": 0.0, "tipo": "musica_alta", "volume": 0.15,
                      "faixa": m.get("nome", ""), "artista": m.get("artista", ""),
                      "reels": m.get("reels", 0),
                      "obs": "INSTRUMENTAL popular por baixo da narração — sem "
                             "letra não há duas vozes brigando. Se a plataforma "
                             "creditar o uso mixado baixo, junta alcance com "
                             "história: hipótese a testar, não fato"})
    else:
        audio.append({"inicio": 0.0, "tipo": "musica", "volume": 0.12,
                      "obs": "camada de fundo — a batidinha que segura o ritmo "
                             "sem competir com a narração"})

    # transição só onde a seção muda; o resto é corte seco
    for a, b in zip(visual, visual[1:]):
        b["transicao"] = TRANSICAO_SECAO.get((a["secao"], b["secao"]), "corte_seco")
    visual[0]["transicao"] = "corte_seco"

    for tx in texto_tr:
        tx["anim"] = ANIM_TEXTO.get(tx.get("estilo"), ANIM_TEXTO["legenda"])

    return {
        "produto": sb.get("produto", ""),
        "link": sb.get("link", ""),
        "origem": sb.get("origem", "original"),
        "fps": FPS, "resolucao": list(RESOLUCAO),
        "duracao_total": round(t, 2),
        "modo_audio": modo_audio,
        "template": _template(sb.get("nicho") or sb.get("categoria") or "geral"),
        "assets_disponiveis": sb.get("assets_disponiveis", 1),
        "secoes": secoes,
        "trilhas": {"visual": visual, "texto": texto_tr, "audio": audio},
    }


def validar(edl: dict) -> list:
    """Problemas que impediriam o render de sair certo."""
    p = []
    v = edl["trilhas"]["visual"]
    if not v:
        return ["sem trilha visual"]

    n = int(edl.get("assets_disponiveis") or 1)
    for i, c in enumerate(v, 1):
        m = re.match(r"asset_(\d+)$", str(c.get("asset", "")))
        if not m or not (1 <= int(m.group(1)) <= n):
            p.append(f"corte {i}: asset '{c.get('asset')}' não existe "
                     f"(há {n})")
        if c["fim"] <= c["inicio"]:
            p.append(f"corte {i}: duração zero ou negativa")

    # buraco ou sobreposição na linha do tempo: no render viraria quadro preto
    # ou imagem duplicada, e é o tipo de erro que só aparece assistindo
    for a, b in zip(v, v[1:]):
        if abs(b["inicio"] - a["fim"]) > 0.05:
            p.append(f"buraco/sobreposição em {a['fim']:.2f}s → {b['inicio']:.2f}s")

    curtos = [c for c in v if (c["fim"] - c["inicio"]) < 0.45]
    if curtos:
        p.append(f"{len(curtos)} corte(s) abaixo de 0,45s — vira piscada, "
                 "não corte")

    if abs(v[-1]["fim"] - edl["duracao_total"]) > 0.1:
        p.append("duração total não bate com o fim do último corte")
    return p


def _resumo(edl):
    v = edl["trilhas"]["visual"]
    secoes = {}
    for c in v:
        s = c.get("secao", "?")
        secoes.setdefault(s, []).append(c["fim"] - c["inicio"])
    print(f"\n  {edl['produto'][:62]}")
    tp = edl.get("template", {})
    print(f"  {edl['duracao_total']}s · {len(v)} cortes · "
          f"{edl['assets_disponiveis']} imagem(ns) · {FPS}fps")
    mus = next((a for a in edl["trilhas"]["audio"]
                if a["tipo"] == "musica_alta"), None)
    linha_m = ""
    if mus:
        linha_m = (f" · ♪ {mus.get('faixa') or '(sem faixa!)'}"
                   f" ({mus.get('reels', 0):,} reels)".replace(",", "."))
    print(f"  áudio: {edl.get('modo_audio')} · template: {tp.get('logo')} "
          f"{tp.get('handle') or '(handle?)'}{linha_m}")
    for s, ds in secoes.items():
        print(f"     {s:16} {len(ds):2} corte(s) · média {sum(ds)/len(ds):.2f}s")
    leg = [t for t in edl["trilhas"]["texto"] if t["estilo"] == "legenda"]
    sfx = [a for a in edl["trilhas"]["audio"] if a["tipo"] == "sfx"]
    print(f"     legendas         {len(leg)} bloco(s) · sfx {len(sfx)}")
    print("\n  linha do tempo:")
    for c in v:
        marca = {"hook": "🔥", "desenvolvimento": "▶", "cta": "👆"}.get(c["secao"], " ")
        tr = c.get("transicao", "corte_seco")
        tr = "" if tr == "corte_seco" else f"  ⟨{tr}⟩"
        print(f"     {marca} {c['inicio']:5.2f}→{c['fim']:5.2f}  {c['asset']:8} "
              f"{c['movimento']:10} zoom {c['zoom_de']}→{c['zoom_para']}{tr}")


def main():
    p = argparse.ArgumentParser(description="Storyboard -> EDL (sem renderizar).")
    p.add_argument("--storyboard", help="arquivo JSON do storyboard")
    p.add_argument("--todos", action="store_true", help="todos de shared/storyboards")
    p.add_argument("--salvar", action="store_true")
    p.add_argument("--audio", choices=MODOS_AUDIO, default="narracao",
                   help="narracao (voz conduz) ou viral (som em alta conduz)")
    p.add_argument("--narrar-hook", action="store_true",
                   help="volta a narrar o hook (padrão: não, ele já está "
                        "escrito na tela o vídeo inteiro)")
    args = p.parse_args()

    if args.todos:
        arqs = sorted(SB_DIR.glob("*.json"))
    elif args.storyboard:
        arqs = [Path(args.storyboard)]
    else:
        p.error("use --storyboard ARQ ou --todos")

    if not arqs:
        _log(f"nenhum storyboard em {SB_DIR}")
        return 1

    ruins = 0
    for f in arqs:
        try:
            sb = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            _log(f"não li {f.name}: {e}")
            ruins += 1
            continue
        edl = montar(sb, args.audio, narrar_hook=args.narrar_hook)
        problemas = validar(edl)
        _resumo(edl)
        if problemas:
            ruins += 1
            for x in problemas:
                print(f"     ✗ {x}")
        else:
            print("     ✅ válido")
        if args.salvar:
            SAIDA_DIR.mkdir(parents=True, exist_ok=True)
            d = SAIDA_DIR / f.name
            d.write_text(json.dumps(edl, ensure_ascii=False, indent=2),
                         encoding="utf-8")
            print(f"     salvo em {d}")
    print()
    _log(f"{len(arqs)} EDL gerado(s) · {ruins} com problema")
    return 1 if ruins else 0


if __name__ == "__main__":
    sys.exit(main())
