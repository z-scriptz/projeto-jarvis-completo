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


def _voz_da_conta(nicho: str) -> str:
    """A voz do perfil, lida do contas.json (campo `voz_id`).

    POR QUE contas.json E NÃO SÓ .env:
    o `.env` já resolvia isto por ELEVENLABS_VOICE_ID_<NICHO>, mas é o lugar
    menos visível do projeto — ninguém abre o .env pra saber "que voz o
    @topshopbeauty._ usa?". O contas.json é onde o perfil JÁ mora: handle,
    instagram_user_id, page_token_env. A voz é identidade da conta tanto quanto
    o @ — pertence ao mesmo lugar.

    É a mesma lição da logo por nicho: quando a informação da conta fica
    espalhada, um perfil acaba publicando com a cara de outro.
    """
    try:
        import json
        d = json.loads((BASE_DIR / "contas.json").read_text(encoding="utf-8"))
    except Exception:
        return ""
    n = (nicho or "geral").strip().lower()
    conta = d.get(n) or (d.get("_default") if n in ("", "geral") else None) or {}
    return str(conta.get("voz_id") or "").strip()


def _voz_do_nicho(nicho: str = ""):
    """Escolhe a VOZ do perfil. Devolve (voice_id, NICHO, é_voz_própria).

    Ordem, do mais específico pro mais geral:
      1. ELEVENLABS_VOICE_ID_<NICHO>  no .env  — override rápido, pra testar
      2. contas.json[<nicho>].voz_id           — a voz OFICIAL do perfil
      3. ELEVENLABS_VOICE_ID           no .env  — a voz padrão da casa

    O .env vem antes de propósito: é onde se testa uma voz nova sem commitar
    nada. Mas quem manda no dia a dia é o contas.json, que é versionado e onde
    dá pra LER, num arquivo só, qual perfil fala com qual voz.
    """
    n = _norm_nicho(nicho)
    if n:
        v = os.getenv(f"ELEVENLABS_VOICE_ID_{n}", "").strip()
        if v:
            return v, n, True
    v = _voz_da_conta(nicho)
    if v:
        return v, n, True
    return os.getenv("ELEVENLABS_VOICE_ID", "").strip(), n, False


def vozes_por_perfil() -> list:
    """[(nicho, handle, voz_id, origem)] — pra CONFERIR de relance.

    Existe porque configuração que ninguém consegue listar é configuração que
    ninguém confere: dois perfis acabam com a mesma voz e só se descobre
    ouvindo os dois vídeos lado a lado, semanas depois.
    """
    import json
    try:
        d = json.loads((BASE_DIR / "contas.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    fora = []
    for chave, c in d.items():
        nicho = "geral" if chave == "_default" else chave
        n = _norm_nicho(nicho)
        if os.getenv(f"ELEVENLABS_VOICE_ID_{n}", "").strip():
            origem = f".env (ELEVENLABS_VOICE_ID_{n})"
        elif str(c.get("voz_id") or "").strip():
            origem = "contas.json"
        else:
            origem = "PADRÃO DA CASA — este perfil não tem voz própria"
        voz, _, propria = _voz_do_nicho(nicho)
        fora.append((nicho, c.get("handle", ""), voz, origem, propria))
    return sorted(fora)


def _ajustes_da_conta(nicho: str) -> dict:
    """Os `voice_settings` gravados no contas.json, se houver.

    "Voz é asset de marca" — e asset de marca não pode depender de alguém
    lembrar qual era o `stability` seis meses depois. O perfil pode guardar o
    conjunto inteiro junto do `voz_id`:

        "casa": {"handle": "@topshopcasa_", "voz_id": "...",
                 "voz_nome": "tom",
                 "voz_ajustes": {"stability": 0.48, "similarity_boost": 0.82,
                                 "style": 0.20, "speed": 1.0}}

    Sem isso, uma troca de parâmetro no .env muda o timbre de TODOS os perfis
    de uma vez e a descoberta vem pelo ouvido, tarde.
    """
    try:
        import json
        d = json.loads((BASE_DIR / "contas.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    n = (nicho or "geral").strip().lower()
    conta = d.get(n) or (d.get("_default") if n in ("", "geral") else None) or {}
    a = conta.get("voz_ajustes")
    return dict(a) if isinstance(a, dict) else {}


_APELIDOS = {
    # o Dre lê os nomes da TELA do ElevenLabs; o código fala a língua da API.
    # Traduzir aqui evita que ele tenha que traduzir de cabeça toda vez — e
    # errar "estilo" por "similaridade" é o tipo de troca que ninguém percebe
    # lendo, só ouvindo semanas depois.
    "estabilidade": "stability", "stability": "stability",
    "similaridade": "similarity_boost", "similarity": "similarity_boost",
    "similarity_boost": "similarity_boost",
    "estilo": "style", "exagero": "style", "exagero_de_estilo": "style",
    "style": "style",
    "velocidade": "speed", "speed": "speed",
}
# stability/similarity/style são frações 0-1 na API, mas a TELA mostra %.
# speed não: 1.17 é 1.17. Por isso a conversão é por campo, não global.
_FRACIONARIOS = {"stability", "similarity_boost", "style"}


def _valor_ajuste(campo: str, bruto) -> float:
    """Aceita 0.70, "70", "70%" para os fracionários; speed passa direto.

    Mesma lição do `texto_queimado._densidade`: aceitar o formato que a pessoa
    TEM na mão. "70" virando 70.0 num campo que vai até 1.0 seria clamped pra
    1.0 em silêncio — voz errada, sem erro nenhum na tela.
    """
    s = str(bruto).strip().replace(",", ".").rstrip("%")
    v = float(s)
    if campo in _FRACIONARIOS:
        if v > 1.0:
            v = v / 100.0
        return max(0.0, min(1.0, v))
    return max(0.7, min(1.2, v))       # faixa que a API aceita pra speed


def definir_ajustes(pares: list) -> int:
    """Grava `voz_ajustes` no contas.json, por perfil.

    POR QUE EXISTE (11/08). O Dre perguntou se as configs de voz (estabilidade,
    similaridade, estilo, velocidade) "vêm da API ou precisa configurar". Vêm
    do NOSSO pedido: `_voice_settings` sempre manda `voice_settings`, então os
    sliders ajustados no site do ElevenLabs são IGNORADOS. E o padrão do código
    dizia no comentário ser "os valores do Michael" sem ser: style 0.40 contra
    o 0% que ele calibrou — a diferença mais audível das quatro.

    Uso:
      python3 narracao_ia.py --definir-ajustes \
        "tech=estabilidade:70,similaridade:75,estilo:0,velocidade:1.17"
    """
    import json
    arq = BASE_DIR / "contas.json"
    try:
        d = json.loads(arq.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"não li {arq}: {e}")
        return 1

    chave_de = {("geral" if k == "_default" else k): k for k in d}
    mudou, erros = [], []

    for par in pares:
        nicho, _, resto = par.partition("=")
        nicho = nicho.strip().lower()
        if nicho not in chave_de:
            erros.append(f"{nicho}: não existe no contas.json")
            continue
        ajustes = {}
        for pedaco in resto.split(","):
            if not pedaco.strip():
                continue
            nome, _, valor = pedaco.partition(":")
            campo = _APELIDOS.get(nome.strip().lower())
            if not campo:
                erros.append(f"{nicho}: campo desconhecido {nome.strip()!r} "
                             f"(use: {', '.join(sorted(set(_APELIDOS)))[:60]}…)")
                continue
            try:
                ajustes[campo] = _valor_ajuste(campo, valor)
            except ValueError:
                erros.append(f"{nicho}: valor ilegível em {nome.strip()}={valor!r}")
        if ajustes:
            c = d[chave_de[nicho]]
            antes = dict(c.get("voz_ajustes") or {})
            c.setdefault("voz_ajustes", {}).update(ajustes)
            mudou.append((nicho, antes, dict(c["voz_ajustes"])))

    if mudou:
        arq.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    for nicho, antes, agora in mudou:
        print(f"  ✅ {nicho}")
        for k in ("stability", "similarity_boost", "style", "speed"):
            if k in agora:
                de = antes.get(k, "—")
                print(f"       {k:18} {de} → {agora[k]}")
    for e in erros:
        print(f"  ⚠️  {e}")
    if not mudou and not erros:
        print("nada pra fazer")
    return 0 if mudou or not erros else 1


def _voice_settings(n: str, nicho: str = "") -> dict:
    """Os `voice_settings` do ElevenLabs: contas.json por cima do .env.

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
    # o que o PERFIL definiu ganha do padrão da casa
    for k, v in _ajustes_da_conta(nicho).items():
        if k in ("stability", "similarity_boost", "style", "speed"):
            try:
                vs[k] = float(v)
            except (TypeError, ValueError):
                pass
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
                  "voice_settings": _voice_settings(n, nicho)})
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
    vs = _voice_settings(n, nicho)

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


def definir_vozes(pares: list) -> int:
    """Grava `voz_id` no contas.json SEM tocar em mais nada.

    ⚠️ NÃO CRIA CONTA NOVA, de propósito. O `daemon_maestro._nichos_das_contas`
    monta os nichos de PRODUÇÃO a partir das chaves deste arquivo: criar "pet"
    aqui com só handle e voz faria o daemon produzir pra uma conta sem
    `instagram_user_id` nem `page_token_env`, e o post falharia depois — longe
    daqui, sem ninguém ligar uma coisa à outra.

    E é por isso que isto é um COMANDO e não um contas.json commitado: o
    arquivo da VPS tem contas que o repo não tem. Substituí-lo apagaria a
    configuração delas.
    """
    import json
    arq = BASE_DIR / "contas.json"
    try:
        texto = arq.read_text(encoding="utf-8")
        d = json.loads(texto)
    except Exception as e:
        print(f"não li {arq}: {e}")
        return 1

    # mapa nicho -> chave real do arquivo ("geral" mora em "_default")
    chave_de = {}
    for chave, c in d.items():
        nicho = "geral" if chave == "_default" else chave
        chave_de[nicho] = chave

    mudou, faltando = [], []
    for par in pares:
        if "=" not in par:
            print(f"ignorado (formato nicho=ID): {par!r}")
            continue
        nicho, _, resto = par.partition("=")
        nicho = nicho.strip().lower()
        voz_id, _, nome = resto.partition(":")
        voz_id, nome = voz_id.strip(), nome.strip()
        if nicho not in chave_de:
            faltando.append((nicho, voz_id, nome))
            continue
        c = d[chave_de[nicho]]
        antes = c.get("voz_id", "")
        c["voz_id"] = voz_id
        if nome:
            c["voz_nome"] = nome
        mudou.append((nicho, antes, voz_id, nome))

    if mudou:
        arq.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    for nicho, antes, agora, nome in mudou:
        de = antes or "(padrão da casa)"
        print(f"  ✅ {nicho:8} {de} → {agora}" + (f"  [{nome}]" if nome else ""))
    for nicho, voz, nome in faltando:
        print(f"  ⚠️  {nicho:8} NÃO existe no contas.json — a voz {voz}"
              + (f" [{nome}]" if nome else "")
              + " ficou de fora.\n      Crie a conta com TODOS os campos "
                "(handle, instagram_user_id, facebook_page_id, page_token_env) "
                "antes,\n      senão o daemon vai produzir pra ela e o post "
                "falha na hora de publicar.")
    if not mudou and not faltando:
        print("nada pra fazer")
    return 0


def criar_conta(campos: list) -> int:
    """Acrescenta uma conta ao contas.json — com TODOS os campos ou nenhum.

    ⚠️ EXIGE handle, instagram_user_id, facebook_page_id e page_token_env de
    propósito. Conta pela metade neste arquivo é pior que conta ausente: o
    `daemon_maestro._nichos_das_contas` passa a produzir vídeo pro nicho e o
    post só falha lá na frente, na hora de publicar, sem ninguém ligar as duas
    coisas.

    ⚠️ E CONFERE O FORMATO DOS IDs. O `instagram_user_id` da Graph API é o
    IGSID: 17 dígitos, começando em 178414 nas contas deste projeto. Número de
    11 dígitos ou código alfanumérico é OUTRO identificador (o que o app
    mostra), e com ele a publicação falha com erro genérico. Quem devolve os
    corretos é o `diag_contas.py`.
    """
    import json
    arq = BASE_DIR / "contas.json"
    try:
        d = json.loads(arq.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"não li {arq}: {e}")
        return 1

    novo, nicho = {}, ""
    for c in campos:
        if "=" not in c:
            continue
        k, _, v = c.partition("=")
        k, v = k.strip(), v.strip()
        if k == "nicho":
            nicho = v.lower()
        else:
            novo[k] = v

    obrigatorios = ("handle", "instagram_user_id", "facebook_page_id",
                    "page_token_env")
    faltam = [c for c in obrigatorios if not novo.get(c)]
    if not nicho or faltam:
        print("faltou: " + ", ".join(([] if nicho else ["nicho"]) + faltam))
        print("\n  uso: --criar-conta nicho=pet handle=@topshoppet_ \\")
        print("         instagram_user_id=178414... facebook_page_id=123... \\")
        print("         page_token_env=PAGE_TOKEN_TOPSHOP_PET voz_id=... voz_nome=...")
        print("\n  os IDs corretos saem de:  .venv/bin/python diag_contas.py")
        return 1
    if nicho in d:
        print(f"o nicho {nicho!r} já existe — use --definir-voz pra só a voz")
        return 1

    igs = novo["instagram_user_id"]
    if not (igs.isdigit() and len(igs) >= 16):
        print(f"⚠️  instagram_user_id {igs!r} não parece um IGSID da Graph API "
              "(17 dígitos, começa em 178414 nas outras contas).")
        print("    As contas que funcionam hoje têm este formato. Rode "
              "`.venv/bin/python diag_contas.py` e use o número que ele mostra.")
        return 1
    if not novo["facebook_page_id"].isdigit():
        print(f"⚠️  facebook_page_id {novo['facebook_page_id']!r} não é "
              "numérico — o que o app mostra não é o ID da Graph API. "
              "Rode `diag_contas.py`.")
        return 1

    d[nicho] = novo
    arq.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"  ✅ {nicho} criada: {novo.get('handle')}")
    print("     confira com: .venv/bin/python narracao_ia.py --vozes")
    return 0


def main():
    if "--criar-conta" in sys.argv:
        i = sys.argv.index("--criar-conta")
        return criar_conta([a for a in sys.argv[i + 1:] if not a.startswith("--")])
    if "--definir-voz" in sys.argv:
        i = sys.argv.index("--definir-voz")
        return definir_vozes([a for a in sys.argv[i + 1:] if not a.startswith("--")])
    if "--definir-ajustes" in sys.argv:
        i = sys.argv.index("--definir-ajustes")
        return definir_ajustes([a for a in sys.argv[i + 1:]
                                if not a.startswith("--")])
    if "--vozes" in sys.argv:
        linhas = vozes_por_perfil()
        if not linhas:
            print("não consegui ler o contas.json")
            return 1
        print("\nVOZ POR PERFIL\n" + "─" * 74)
        sem = 0
        for nicho, handle, voz, origem, propria in linhas:
            marca = "🎙️ " if propria else "⚠️ "
            sem += 0 if propria else 1
            print(f" {marca} {nicho:8} {handle:20} {voz or '(nenhuma!)':24} {origem}")
            # os SETTINGS efetivos, com a origem — mesma lição dos `knobs` do
            # render: valor sem origem não responde "por que mudei e não mudou".
            proprios = _ajustes_da_conta(nicho)
            vs = _voice_settings(_norm_nicho(nicho), nicho)
            campos = " · ".join(
                f"{k.replace('similarity_boost','simil')}={vs[k]}"
                + ("*" if k in proprios else "")
                for k in ("stability", "similarity_boost", "style", "speed")
                if k in vs)
            print(f"      {campos}")
        print("─" * 74)
        repetidas = {}
        for nicho, _, voz, _, _ in linhas:
            if voz:
                repetidas.setdefault(voz, []).append(nicho)
        for voz, nichos in repetidas.items():
            if len(nichos) > 1:
                print(f" ⚠️  a MESMA voz {voz} em: {', '.join(nichos)}")
        if sem:
            print(f" ⚠️  {sem} perfil(is) sem voz própria — acrescente "
                  '"voz_id": "..." no contas.json')
        print()
        return 0

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
