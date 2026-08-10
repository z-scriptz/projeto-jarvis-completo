#!/usr/bin/env python3
# narracao_ia.py -- gera NARRAÇÃO ÚNICA por vídeo: o Gemini escreve um roteiro
# curto e natural (do produto + contexto do vídeo, NUNCA genérico) e o
# ElevenLabs fala. Serve pra matar o áudio original (copyright/crédito) e
# ainda dar valor real (voz que explica o produto = converte mais).
#
# Testar a voz ANTES de plugar no vídeo:
#   python3 narracao_ia.py "Ferro a Vapor Portátil" "vídeo mostrando o ferro passando roupa rápido em viagem"
#   -> gera narracao_teste.mp3 (escuta!) e imprime o roteiro
#
# .env necessário:
#   ELEVENLABS_API_KEY=...          (elevenlabs.io -> perfil -> API key)
#   ELEVENLABS_VOICE_ID=...         (id de uma voz PT-BR que você escolher)
#   GEMINI_API_KEY=...              (já temos)
# opcionais:
#   ELEVENLABS_MODEL=eleven_multilingual_v2   (qualidade PT; turbo = mais barato)
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


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

_PROMPT = (
    "Você escreve narração em off pra Reels/TikTok de achadinhos, como uma AMIGA "
    "contando uma dica que mudou o dia dela — NÃO uma vendedora. Português do "
    "Brasil, natural e falado, 2 a 3 frases curtas (18 a 30 palavras, ~10-12s).\n"
    "ESTRUTURA: (1) conecte com uma situação REAL do dia a dia (uma dorzinha, um "
    "incômodo comum); (2) apresente o produto como a virada de chave, com 1 "
    "benefício concreto; (3) feche com um convite curto pro link da bio.\n"
    "FECHAMENTO — use UM destes, EXATAMENTE assim (não invente variação torta "
    "tipo 'corre ver no link da bio'): 'tá tudo no link da bio', 'é só clicar no "
    "link da bio', 'garante o seu no link da bio', 'o link tá na bio', 'corre "
    "pro link da bio'.\n"
    "GÊNERO (essencial): concorde MASCULINO/FEMININO com o produto — 'essa "
    "passadeira', 'esse ferro', 'essa tomada', 'esse cortador', 'essa bota'. "
    "NUNCA use 'esse/o' pra palavra feminina, nem 'essa/a' pra masculina. Na "
    "dúvida sobre o gênero, REESCREVA a frase pra não precisar do artigo.\n"
    "QUALIDADE: frases COMPLETAS e ortografia PERFEITA — não abrevie, não 'coma' "
    "palavras, não corte no meio. Releia e corrija antes de devolver.\n"
    "TOM: acolhedor, de conversa — ZERO cara de propaganda ou 'compre já'. "
    "Varie a abertura entre vídeos (nem todo começa com pergunta).\n"
    "Sem hashtag, sem emoji, sem aspas, sem nome de marca. Devolva SÓ o texto.\n\n"
    "Produto: {produto}\nContexto do vídeo: {contexto}")


def roteiro(produto: str, contexto: str = "") -> str:
    """Gemini escreve o roteiro único. Fallback simples se o Gemini falhar."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    prompt = _PROMPT.format(produto=produto or "este produto", contexto=contexto or "—")
    if api_key:
        for tent in (1, 2):
            try:
                from google import genai
                cli = genai.Client(api_key=api_key)
                r = cli.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[{"parts": [{"text": prompt}]}])
                t = (r.text or "").strip().strip('"').replace("\n", " ")
                if t:
                    return t
            except Exception as e:
                s = str(e)
                if tent == 1 and ("429" in s or "RESOURCE_EXHAUSTED" in s):
                    time.sleep(20); continue
                print(f"   (Gemini falhou: {s[:60]}) — uso roteiro simples")
                break
    # fallback (não deveria acontecer com a key certa) — gênero-safe (apposto)
    return (f"Esse achadinho vale muito a pena: {produto}. "
            f"Facilita demais o dia a dia — o link tá na bio.")


def _norm_nicho(n: str) -> str:
    """'Beleza' -> 'BELEZA' (sem acento, só alfanum) pra virar sufixo de env."""
    import unicodedata
    n = unicodedata.normalize("NFKD", (n or "")).encode("ascii", "ignore").decode()
    return "".join(c for c in n.upper() if c.isalnum())


def _voz_do_nicho(nicho: str = ""):
    """Escolhe a VOZ pelo nicho: ELEVENLABS_VOICE_ID_<NICHO> (ex.: _BELEZA = voz
    feminina) e, se não houver, cai na ELEVENLABS_VOICE_ID (Michael, padrão).
    Assim beleza/skincare fala com voz feminina e tech/geral com a masculina."""
    n = _norm_nicho(nicho)
    if n:
        v = os.getenv(f"ELEVENLABS_VOICE_ID_{n}", "").strip()
        if v:
            return v, n, True
    return os.getenv("ELEVENLABS_VOICE_ID", "").strip(), n, False


def _voice_settings(n: str) -> dict:
    """Os `voice_settings` do ElevenLabs, lidos do .env.

    Extraído de dentro do falar_elevenlabs pra o pedido COM TEMPOS usar
    exatamente os mesmos valores. Voz é identidade da marca: se as duas
    chamadas divergirem, o mesmo canal fala com dois timbres e ninguém
    descobre olhando o código — descobre ouvindo, tarde.
    """
    def _f(nome, padrao):
        # tenta NOME_<NICHO> antes de NOME — voz feminina pode querer settings próprios
        for cand in ((f"{nome}_{n}",) if n else ()) + (nome,):
            v = os.getenv(cand)
            if v not in (None, ""):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        return float(padrao)

    # settings ajustáveis pelo .env (padrão = os valores da voz do Michael)
    vs = {
        "stability":        _f("ELEVENLABS_STABILITY", 0.45),
        "similarity_boost": _f("ELEVENLABS_SIMILARITY", 0.75),
        "style":            _f("ELEVENLABS_STYLE", 0.40),
        "use_speaker_boost": True,
    }
    _spd = _f("ELEVENLABS_SPEED", 1.15)
    if _spd and _spd != 1.0:
        vs["speed"] = max(0.7, min(1.2, _spd))   # faixa aceita pela API
    return vs


def falar_com_tempos(texto: str, destino: Path, nicho: str = "") -> dict:
    """MP3 + O TEMPO EXATO DE CADA CARACTERE falado.

    Mesma voz, mesmo modelo e mesmos settings do falar_elevenlabs — muda só o
    endpoint, `/with-timestamps`, que devolve o áudio em base64 MAIS o
    alinhamento: para cada caractere do texto, quando ele começa e quando
    termina, em segundos.

    POR QUE ISSO IMPORTA MAIS QUE A DURAÇÃO:
    o render sabia esticar a linha do tempo pela duração do MP3, mas repartia a
    LEGENDA proporcionalmente ao tamanho de cada bloco — um chute educado. Com o
    alinhamento, cada bloco de legenda entra e sai no instante em que a voz diz
    aquelas palavras. Legenda fora de sincronia é o detalhe que denuncia vídeo
    automático mesmo quando todo o resto está certo.

    Retorna {"ok", "arquivo", "dur", "chars", "tempos", "erro"} — `chars` é a
    string falada e `tempos` a lista [(inicio, fim)] na mesma ordem.
    """
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    voice, n, voz_propria = _voz_do_nicho(nicho)
    model = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    if not api_key or not voice:
        return {"ok": False, "erro": "faltam ELEVENLABS_API_KEY / "
                                     "ELEVENLABS_VOICE_ID no .env"}
    try:
        import base64
        import requests
        url = (f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
               f"/with-timestamps")
        r = requests.post(url, timeout=90,
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={"text": texto, "model_id": model,
                  "voice_settings": _voice_settings(n)})
        if r.status_code != 200:
            return {"ok": False,
                    "erro": f"HTTP {r.status_code}: {r.text[:180]}"}
        d = r.json()
        audio = base64.b64decode(d.get("audio_base64") or "")
        if len(audio) < 500:
            return {"ok": False, "erro": "áudio vazio"}
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(audio)

        # `alignment` casa com o texto ORIGINAL; `normalized_alignment` casa com
        # o texto depois de a API expandir número e abreviação. Pra grudar a
        # legenda nas palavras QUE ESCREVEMOS, o original é o que serve.
        al = d.get("alignment") or d.get("normalized_alignment") or {}
        chars = al.get("characters") or []
        ini = al.get("character_start_times_seconds") or []
        fim = al.get("character_end_times_seconds") or []
        tempos = list(zip(ini, fim))
        if not (len(chars) == len(ini) == len(fim)) or not chars:
            # áudio é bom, alinhamento não veio: quem chama cai no modo antigo
            return {"ok": True, "arquivo": destino, "dur": 0.0, "chars": "",
                    "tempos": [], "voz_do_nicho": voz_propria,
                    "erro": "alinhamento ausente ou inconsistente"}
        return {"ok": True, "arquivo": destino, "dur": float(fim[-1]),
                "chars": "".join(chars), "tempos": tempos,
                # o ID da voz vai no retorno pra o render poder REGISTRAR qual
                # voz falou. "não parece a voz do ElevenLabs" tem que virar um
                # ID conferível, não uma discussão de impressão.
                "voz_id": voice, "modelo": model,
                "voz_do_nicho": voz_propria, "erro": None}
    except Exception as e:
        return {"ok": False, "erro": f"{type(e).__name__}: {str(e)[:140]}"}


def falar_elevenlabs(texto: str, destino: Path, nicho: str = "") -> bool:
    """Sintetiza o texto com o ElevenLabs -> MP3. Retorna True se deu certo.
    A voz é escolhida pelo nicho (voz feminina p/ beleza, masculina p/ o resto)."""
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    voice, n, voz_propria = _voz_do_nicho(nicho)
    model = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    if not api_key or not voice:
        print("   ⚠️ Faltam ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID no .env")
        return False
    if voz_propria:
        print(f"   🎙️ voz do nicho '{nicho}' (ELEVENLABS_VOICE_ID_{n})")
    vs = _voice_settings(n)

    try:
        import requests
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
        r = requests.post(url, timeout=60,
            headers={"xi-api-key": api_key, "Content-Type": "application/json",
                     "Accept": "audio/mpeg"},
            json={"text": texto, "model_id": model, "voice_settings": vs})
        if r.status_code != 200:
            print(f"   ❌ ElevenLabs HTTP {r.status_code}: {r.text[:180]}")
            return False
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(r.content)
        return destino.stat().st_size > 500
    except Exception as e:
        print(f"   ❌ erro ElevenLabs: {str(e)[:100]}")
        return False


def gerar(produto: str, contexto: str, destino: Path, nicho: str = "") -> str:
    """Roteiro (Gemini) -> voz (ElevenLabs, escolhida pelo nicho) -> mp3 (ou '')."""
    txt = roteiro(produto, contexto)
    print(f"   📝 roteiro: {txt}")
    print(f"   🔤 {len(txt)} caracteres (custo ElevenLabs)")
    if falar_elevenlabs(txt, destino, nicho):
        return str(destino)
    return ""


def main():
    if len(sys.argv) < 2:
        print('Uso: python3 narracao_ia.py "Nome do Produto" "contexto (opcional)" "nicho (opcional: beleza/tech/geral)"')
        return 1
    produto = sys.argv[1]
    contexto = sys.argv[2] if len(sys.argv) > 2 else ""
    nicho = sys.argv[3] if len(sys.argv) > 3 else ""
    destino = BASE_DIR / "narracao_teste.mp3"
    print(f"🎙️  Gerando narração de teste pra: {produto}"
          + (f" (nicho: {nicho})" if nicho else ""))
    caminho = gerar(produto, contexto, destino, nicho)
    if caminho:
        print(f"\n✅ Pronto! Escuta: {caminho}")
        print("   (baixa pro teu PC com scp e ouve. Boa? aí a gente pluga no vídeo)")
        return 0
    print("\n❌ Não gerou. Confere as chaves no .env.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
