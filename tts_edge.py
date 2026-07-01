# creative_engine/tts_edge.py
# Wrapper sync pro edge-tts (que é async por natureza).
#
# Gera narração MP3 a partir de texto + captura word boundaries (timing real
# de cada palavra), que usamos pra sincronizar legenda sem precisar de Whisper.
#
# edge-tts usa vozes online do Microsoft Edge — grátis, sem API key.
# Se a lib não estiver instalada, gera_narracao retorna erro amigável.

import asyncio
import re
from pathlib import Path
from typing import Optional

try:
    import edge_tts
    _EDGE_OK = True
except Exception:
    _EDGE_OK = False

# Vozes PT-BR comuns do Edge (todas grátis)
VOZ_PADRAO = "pt-BR-ThalitaNeural"   # feminina jovem/suave (identidade TopShop)
VOZES_PTBR = [
    "pt-BR-FranciscaNeural",   # feminina
    "pt-BR-AntonioNeural",     # masculina
    "pt-BR-ThalitaNeural",     # feminina alternativa
]


def edge_tts_disponivel() -> bool:
    return _EDGE_OK


def motivo_indisponivel() -> str:
    if not _EDGE_OK:
        return "edge-tts não instalado (pip install edge-tts)"
    return ""


async def _gerar_async(texto: str, voz: str, destino: str,
                        rate: str, volume: str) -> tuple:
    """
    Gera o MP3 e coleta word boundaries.
    Returns: (boundaries, bytes_audio_escritos)
    """
    comunicador = edge_tts.Communicate(texto, voz, rate=rate, volume=volume)
    boundaries = []
    bytes_audio = 0
    with open(destino, "wb") as f:
        async for chunk in comunicador.stream():
            tipo = chunk.get("type")
            if tipo == "audio":
                dados = chunk.get("data") or b""
                f.write(dados)
                bytes_audio += len(dados)
            elif tipo in ("WordBoundary", "SentenceBoundary"):
                # offset/duration em 100-nanosegundos (ticks)
                off = chunk.get("offset")
                dur = chunk.get("duration")
                if off is not None and dur is not None:
                    boundaries.append({
                        "palavra":     chunk.get("text", ""),
                        "offset_seg":  off / 10_000_000,
                        "duracao_seg": dur / 10_000_000,
                    })
    return boundaries, bytes_audio


def gerar_narracao(texto: str, destino: Path,
                    voz: str = VOZ_PADRAO,
                    rate: str = "+0%",
                    volume: str = "+0%",
                    dur_minima_esperada: float = 0.0,
                    tentativas: int = 3) -> dict:
    """
    Gera narração MP3 (sync wrapper) com retry + validação de integridade.

    Args:
        texto:               texto completo a narrar
        destino:             caminho do MP3 de saída
        voz:                 voz Edge-TTS
        rate/volume:         ajustes de fala
        dur_minima_esperada: se >0, rejeita MP3 com menos de ~60% disso
                             (pega narração truncada por instabilidade de rede)
        tentativas:          quantas vezes tentar antes de desistir

    Returns: {sucesso, arquivo, word_boundaries, dur_aprox, tentativas_usadas, erro}
    """
    if not _EDGE_OK:
        return {"sucesso": False, "arquivo": None, "word_boundaries": [],
                "dur_aprox": 0, "tentativas_usadas": 0, "erro": motivo_indisponivel()}

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    # Limiar de bytes: ~ estima 16kbps de MP3 → ~2KB/s. Se esperamos N seg,
    # exige pelo menos ~60% disso em áudio escrito.
    bytes_min = 0
    if dur_minima_esperada > 0:
        bytes_min = int(dur_minima_esperada * 0.6 * 2000)  # 2KB/s conservador

    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            boundaries, bytes_audio = asyncio.run(
                _gerar_async(texto, voz, str(destino), rate, volume))

            if not destino.exists():
                ultimo_erro = "MP3 não criado"
                continue
            tam = destino.stat().st_size
            if tam < 1024:
                ultimo_erro = f"MP3 vazio ({tam}B)"
                continue
            # Validação de truncamento: bytes de áudio abaixo do esperado
            if bytes_min and bytes_audio < bytes_min:
                ultimo_erro = (f"narração truncada (~{bytes_audio}B de áudio, "
                               f"esperava >{bytes_min}B) — tentativa {tentativa}")
                continue
            # Sucesso
            dur_aprox = round(bytes_audio / 2000, 1) if bytes_audio else 0
            return {"sucesso": True, "arquivo": str(destino),
                    "word_boundaries": boundaries, "dur_aprox": dur_aprox,
                    "tentativas_usadas": tentativa, "erro": None}
        except Exception as e:
            ultimo_erro = f"{type(e).__name__}: {str(e)[:140]}"

    return {"sucesso": False, "arquivo": None, "word_boundaries": [],
            "dur_aprox": 0, "tentativas_usadas": tentativas,
            "erro": ultimo_erro or "falha desconhecida"}


def _quebrar_frase_longa(frase: str, max_palavras: int = 7) -> list:
    """
    Quebra uma frase longa em pedaços curtos pra legenda não virar paredão
    de 3 linhas. Divide em vírgulas/pontuação primeiro (corte natural), e se
    ainda ficar grande, parte por número de palavras.

    Ex: "Chega de escorregar e se cortar, ele é super seguro e prático pra você"
        → ["Chega de escorregar e se cortar,", "ele é super seguro e prático pra você"]

    Returns: lista de pedaços (1 item se a frase já é curta).
    """
    frase = frase.strip()
    if len(frase.split()) <= max_palavras:
        return [frase]

    # 1) tenta cortar em pontuação interna (vírgula, ponto-e-vírgula, travessão)
    partes_pont = re.split(r"(?<=[,;:—–])\s+", frase)
    partes_pont = [p.strip() for p in partes_pont if p.strip()]

    # 2) pra cada parte que ainda é longa, quebra por palavras
    saida = []
    for parte in partes_pont:
        palavras = parte.split()
        if len(palavras) <= max_palavras:
            saida.append(parte)
        else:
            # parte em blocos de ~max_palavras, equilibrando o tamanho
            n = len(palavras)
            n_pedacos = (n + max_palavras - 1) // max_palavras
            tam = (n + n_pedacos - 1) // n_pedacos  # tamanho equilibrado
            for i in range(0, n, tam):
                saida.append(" ".join(palavras[i:i + tam]))
    return saida or [frase]


def _expandir_frases_curtas(frases: list, max_palavras: int = 7) -> list:
    """
    Recebe as frases do roteiro e devolve uma lista MAIOR onde frases longas
    foram quebradas em pedaços curtos. Retorna pares (texto, peso_palavras)
    pra quem for distribuir o tempo saber o peso de cada pedaço.

    Returns: lista de tuplas (texto_curto, n_palavras)
    """
    expandidas = []
    for f in frases:
        for pedaco in _quebrar_frase_longa(f, max_palavras):
            expandidas.append((pedaco, len(pedaco.split())))
    return expandidas


def boundaries_para_blocos(frases: list, word_boundaries: list,
                            dur_total: float) -> list:
    """
    Converte frases + word boundaries em blocos de legenda com timing.

    Se word_boundaries disponível: usa timing real (casa palavras → frases).
    Senão: distribui proporcional ao número de palavras de cada frase.

    Returns: [{texto, inicio_seg, fim_seg}]
    """
    if not frases:
        return []

    # Calcula o bloco de tempo de CADA FRASE, depois subdivide frases longas
    # em pedaços curtos repartindo o tempo proporcionalmente.
    blocos_frase = []  # [(texto, inicio, fim)] — 1 por frase original

    # Os word_boundaries do Edge-TTS às vezes vêm INCOMPLETOS (ex: 5 boundaries
    # pra 30 palavras) ou numa escala de tempo diferente da duração real do
    # áudio. Se não há boundaries SUFICIENTES (pelo menos ~70% das palavras),
    # não dá pra confiar neles pra casar palavra→tempo: caímos no modo
    # proporcional, que reparte o tempo de forma justa entre as frases.
    total_palavras_roteiro = sum(len(f.split()) for f in frases) or 1
    boundaries_confiaveis = (
        word_boundaries and len(word_boundaries) >= 0.7 * total_palavras_roteiro)

    # Também ignora boundaries cuja escala de tempo destoa da duração real
    # (ex: último offset >> dur_total): sinal de escala inconsistente.
    if boundaries_confiaveis:
        try:
            ultimo_off = word_boundaries[-1].get("offset_seg", 0)
            if dur_total > 0 and ultimo_off > dur_total * 1.5:
                boundaries_confiaveis = False
        except Exception:
            boundaries_confiaveis = False

    # Modo proporcional (sem boundaries OU boundaries não confiáveis)
    if not boundaries_confiaveis:
        total_palavras = total_palavras_roteiro
        t = 0.0
        for f in frases:
            frac = len(f.split()) / total_palavras
            dur = dur_total * frac
            blocos_frase.append((f, t, t + dur))
            t += dur
    else:
        # Com boundaries confiáveis: acumula palavras até casar com cada frase
        idx_word = 0
        n_words = len(word_boundaries)
        for f in frases:
            n_pal_frase = len(f.split())
            if idx_word >= n_words:
                ini = blocos_frase[-1][2] if blocos_frase else 0.0
                blocos_frase.append((f, ini, dur_total))
                continue
            inicio = word_boundaries[idx_word]["offset_seg"]
            idx_fim = min(idx_word + n_pal_frase - 1, n_words - 1)
            wb_fim = word_boundaries[idx_fim]
            fim = wb_fim["offset_seg"] + wb_fim["duracao_seg"]
            blocos_frase.append((f, inicio, fim))
            idx_word += n_pal_frase

    # SUBDIVIDE cada frase em pedaços curtos (legenda não vira paredão),
    # repartindo o tempo da frase entre os pedaços conforme o nº de palavras.
    blocos = []
    for texto, ini, fim in blocos_frase:
        pedacos = _expandir_frases_curtas([texto])  # [(pedaco, n_palavras)]
        if len(pedacos) <= 1:
            blocos.append({"texto": texto, "inicio_seg": round(ini, 2),
                           "fim_seg": round(fim, 2)})
            continue
        total_pal = sum(p[1] for p in pedacos) or 1
        dur_frase = max(0.0, fim - ini)
        t = ini
        for pedaco, n_pal in pedacos:
            dur_p = dur_frase * (n_pal / total_pal)
            blocos.append({"texto": pedaco, "inicio_seg": round(t, 2),
                           "fim_seg": round(t + dur_p, 2)})
            t += dur_p

    # Garante que o último bloco vai até o fim do áudio
    if blocos:
        blocos[-1]["fim_seg"] = max(blocos[-1]["fim_seg"], dur_total)
    return blocos