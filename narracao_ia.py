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


def falar_elevenlabs(texto: str, destino: Path) -> bool:
    """Sintetiza o texto com o ElevenLabs -> MP3. Retorna True se deu certo."""
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    voice = os.getenv("ELEVENLABS_VOICE_ID", "")
    model = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    if not api_key or not voice:
        print("   ⚠️ Faltam ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID no .env")
        return False
    def _f(nome, padrao):
        try:
            return float(os.getenv(nome, padrao))
        except (TypeError, ValueError):
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


def gerar(produto: str, contexto: str, destino: Path) -> str:
    """Roteiro (Gemini) -> voz (ElevenLabs) -> caminho do mp3 (ou '')."""
    txt = roteiro(produto, contexto)
    print(f"   📝 roteiro: {txt}")
    print(f"   🔤 {len(txt)} caracteres (custo ElevenLabs)")
    if falar_elevenlabs(txt, destino):
        return str(destino)
    return ""


def main():
    if len(sys.argv) < 2:
        print('Uso: python3 narracao_ia.py "Nome do Produto" "contexto do vídeo (opcional)"')
        return 1
    produto = sys.argv[1]
    contexto = sys.argv[2] if len(sys.argv) > 2 else ""
    destino = BASE_DIR / "narracao_teste.mp3"
    print(f"🎙️  Gerando narração de teste pra: {produto}")
    caminho = gerar(produto, contexto, destino)
    if caminho:
        print(f"\n✅ Pronto! Escuta: {caminho}")
        print("   (baixa pro teu PC com scp e ouve. Boa? aí a gente pluga no vídeo)")
        return 0
    print("\n❌ Não gerou. Confere as chaves no .env.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
