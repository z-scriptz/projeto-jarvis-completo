# agents/visual_audit_agent.py
# Visual Audit Agent v1 do AgenteIA (Jarvis) — "dar olhos" ao Jarvis.
#
# Problema que resolve: hoje o Jarvis escolhe asset por NOME de arquivo (dor_).
# Mas o nome não garante o conteúdo — o bug do "homem no sofá" num vídeo de
# Cinto Modelador provou isso. Este agente AUDITA visualmente os assets antes
# de entrarem no editor/narrated.
#
# Arquitetura em 2 camadas (esta é a 1ª):
#   1. Visual Audit (ESTE):  extrai frames + heurísticas baratas (OpenCV) +
#                            contact sheet + relatório. ZERO API, offline.
#   2. Vision Decision (próx): manda frames pra modelo de visão julgar de verdade.
#
# A v1 já é "meio inteligente": além de extrair frames, roda heurísticas que
# levantam SUSPEITOS automaticamente (rosto dominante, frame escuro/mono),
# então você revisa uma lista priorizada em vez de 13 arquivos no escuro.
#
# Status atribuído a cada asset:
#   pendente_revisao_visual  — extraído, aguardando seu olho (ou Vision AI)
#   suspeito                 — heurística levantou bandeira (revise primeiro)
#
# Fluxo:
#   1. Lista assets em raw/ e imagens/
#   2. Vídeo: extrai N frames (início/meio/fim) via ffmpeg
#   3. Imagem: gera thumbnail
#   4. Roda heurísticas (rosto, brilho, cor) → marca suspeitos
#   5. Monta contact sheet (grade de frames) por arquivo + geral
#   6. Salva relatório shared/content_plans/visual_audit_resultado.json
#
# CLI:
#   python -m agents.visual_audit_agent --produto "Cinto Modelador Slim Feminino"
#   python -m agents.visual_audit_agent --produto "X" --frames 5
#   python -m agents.visual_audit_agent --produto "X" --abrir-relatorio

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from shared.logger import get_logger
from agents.asset_agent import slugificar_produto

# Modelo Gemini central (mesmo que o resto do projeto usa). Best-effort:
# se o config não tiver, cai no flash-lite por padrão.
try:
    from shared.config import GEMINI_VISION_MODEL
except Exception:
    GEMINI_VISION_MODEL = "gemini-2.5-flash-lite"

# OpenCV + PIL (best-effort — degrada se faltar)
try:
    import cv2
    _CV2_OK = True
except Exception:
    _CV2_OK = False

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_OK = True
except Exception:
    _PIL_OK = False

log = get_logger(__name__)


# =================================================================
# RESOLUÇÃO DE BINÁRIOS (ffmpeg / ffprobe)
# =================================================================
# No Windows o ffmpeg/ffprobe raramente estão no PATH. Em vez de exigir
# instalação global, resolvemos os binários na carga do módulo:
#   - ffmpeg:  PATH → imageio_ffmpeg (vem junto do moviepy) → None
#   - ffprobe: PATH → None (imageio_ffmpeg não fornece ffprobe)
# Quando não há binário, caímos no OpenCV (cv2) pra duração e extração.

def resolver_ffmpeg() -> Optional[str]:
    """
    Resolve o executável do ffmpeg.
    Ordem: PATH (shutil.which) → imageio_ffmpeg.get_ffmpeg_exe() → None.
    """
    caminho = shutil.which("ffmpeg")
    if caminho:
        return caminho
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return exe
    except Exception:
        pass
    return None


def resolver_ffprobe() -> Optional[str]:
    """
    Resolve o executável do ffprobe.
    Ordem: PATH (shutil.which) → None.
    (imageio_ffmpeg empacota só o ffmpeg, não o ffprobe.)
    """
    return shutil.which("ffprobe")


# Resolvidos UMA vez na carga do módulo (evita re-checar a cada frame/asset)
FFMPEG_BIN  = resolver_ffmpeg()
FFPROBE_BIN = resolver_ffprobe()

PROJETO_ROOT  = Path(__file__).parent.parent
PRODUTOS_ROOT = PROJETO_ROOT / "assets" / "produtos"
PLANS_DIR     = PROJETO_ROOT / "shared" / "content_plans"
AUDIT_ROOT    = PROJETO_ROOT / "shared" / "visual_audit"

EXT_VIDEO = {".mp4", ".mov", ".webm", ".m4v"}
EXT_IMG   = {".jpg", ".jpeg", ".png", ".webp"}

CENAS = ["dor", "demo", "close", "resultado", "cta"]

# Heurística: limiares
ROSTO_AREA_DOMINANTE = 0.12   # rosto ocupando >12% do frame = "pessoa em destaque"
BRILHO_MUITO_ESCURO  = 40     # média de luminância < 40 (0-255) = escuro demais
SATURACAO_MONO       = 25     # saturação média < 25 = quase preto-e-branco


# =================================================================
# EXTRAÇÃO DE FRAMES
# =================================================================

def _duracao_via_opencv(caminho: Path) -> float:
    """Duração estimada via OpenCV: frame_count / fps. Fallback sem ffprobe."""
    if not _CV2_OK:
        return 0.0
    cap = None
    try:
        cap = cv2.VideoCapture(str(caminho))
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        if fps > 0 and frame_count > 0:
            return round(frame_count / fps, 2)
        return 0.0
    except Exception:
        return 0.0
    finally:
        if cap is not None:
            cap.release()


def _duracao_video(caminho: Path) -> float:
    """
    Duração do vídeo em segundos.
    Usa ffprobe se disponível; senão cai no OpenCV (frame_count / fps).
    """
    if FFPROBE_BIN:
        try:
            out = subprocess.run(
                [FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", str(caminho)],
                capture_output=True, text=True, timeout=20)
            dur = float(out.stdout.strip() or 0)
            if dur > 0:
                return dur
        except Exception:
            pass
        # ffprobe existe mas falhou → tenta OpenCV mesmo assim
        return _duracao_via_opencv(caminho)

    # Sem ffprobe: OpenCV direto
    return _duracao_via_opencv(caminho)


def _extrair_frame_ffmpeg(caminho: Path, ts: float, saida: Path) -> bool:
    """Extrai 1 frame no timestamp ts via ffmpeg. Returns True se gerou arquivo."""
    try:
        subprocess.run(
            [FFMPEG_BIN, "-y", "-ss", str(ts), "-i", str(caminho),
             "-frames:v", "1", "-q:v", "3", str(saida)],
            capture_output=True, timeout=30)
        return saida.exists() and saida.stat().st_size > 0
    except Exception as e:
        log.warning(f"      falha ffmpeg frame {ts}s: {str(e)[:60]}")
        return False


def _extrair_frame_opencv(caminho: Path, ts: float, saida: Path) -> bool:
    """
    Extrai 1 frame no timestamp ts via OpenCV (seek por POS_MSEC).
    Fallback quando não há ffmpeg. Returns True se gerou arquivo.
    """
    if not _CV2_OK:
        return False
    cap = None
    try:
        cap = cv2.VideoCapture(str(caminho))
        cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000)
        ret, frame = cap.read()
        # Se o seek caiu além do fim (ret False), tenta o primeiro frame
        if not ret or frame is None:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
        if ret and frame is not None:
            cv2.imwrite(str(saida), frame)
            return saida.exists() and saida.stat().st_size > 0
        return False
    except Exception as e:
        log.warning(f"      falha opencv frame {ts}s: {str(e)[:60]}")
        return False
    finally:
        if cap is not None:
            cap.release()


def extrair_frames(caminho: Path, destino_dir: Path, n_frames: int = 3) -> list:
    """
    Extrai N frames distribuídos (início/meio/fim) de um vídeo.
    Usa ffmpeg se disponível; senão cai no OpenCV (seek por POS_MSEC).
    Returns: lista de Paths dos frames extraídos.
    """
    destino_dir.mkdir(parents=True, exist_ok=True)
    dur = _duracao_video(caminho)
    if dur <= 0:
        # fallback: pega 1 frame no segundo 0.5
        timestamps = [0.5]
    else:
        # distribui: evita 1º e último frame exatos (costumam ser pretos)
        margem = dur * 0.1
        if n_frames == 1:
            timestamps = [dur / 2]
        else:
            inicio, fim = margem, dur - margem
            passo = (fim - inicio) / (n_frames - 1)
            timestamps = [round(inicio + passo * i, 2) for i in range(n_frames)]

    frames = []
    for i, ts in enumerate(timestamps):
        saida = destino_dir / f"frame_{i+1:02d}_{ts:.1f}s.jpg"
        if FFMPEG_BIN:
            ok = _extrair_frame_ffmpeg(caminho, ts, saida)
        else:
            ok = _extrair_frame_opencv(caminho, ts, saida)
        if ok:
            frames.append(saida)
    return frames


def gerar_thumbnail_imagem(caminho: Path, destino_dir: Path) -> Optional[Path]:
    """Gera thumbnail de uma imagem (640px lado maior)."""
    destino_dir.mkdir(parents=True, exist_ok=True)
    saida = destino_dir / f"thumb_{caminho.stem}.jpg"
    if not _PIL_OK:
        # fallback: copia original
        try:
            import shutil
            shutil.copy(caminho, saida)
            return saida
        except Exception:
            return None
    try:
        img = Image.open(caminho).convert("RGB")
        img.thumbnail((640, 640))
        img.save(saida, "JPEG", quality=85)
        return saida
    except Exception as e:
        log.warning(f"      falha thumbnail {caminho.name}: {str(e)[:60]}")
        return None


# =================================================================
# HEURÍSTICAS VISUAIS (OpenCV — offline, grátis)
# =================================================================

def analisar_frame(frame_path: Path) -> dict:
    """
    Roda heurísticas baratas num frame. NÃO entende contexto (isso é Vision AI),
    mas pesca sinais: rosto dominante, escuridão, falta de cor.

    Returns: {rostos, maior_rosto_frac, brilho_medio, saturacao_media, flags:[...]}
    """
    info = {"rostos": 0, "maior_rosto_frac": 0.0, "brilho_medio": 0,
            "saturacao_media": 0, "flags": []}
    if not _CV2_OK:
        info["flags"].append("opencv_indisponivel")
        return info
    try:
        img = cv2.imread(str(frame_path))
        if img is None:
            info["flags"].append("frame_ilegivel")
            return info
        h, w = img.shape[:2]
        area_frame = h * w

        # Brilho (luminância média via grayscale)
        cinza = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        info["brilho_medio"] = int(cinza.mean())

        # Saturação média (HSV)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        info["saturacao_media"] = int(hsv[:, :, 1].mean())

        # Detecção de rosto (Haar cascade frontal)
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(cascade_path)
        if not cascade.empty():
            rostos = cascade.detectMultiScale(cinza, scaleFactor=1.1,
                                               minNeighbors=5, minSize=(40, 40))
            info["rostos"] = len(rostos)
            if len(rostos) > 0:
                maior = max((rw * rh) for (rx, ry, rw, rh) in rostos)
                info["maior_rosto_frac"] = round(maior / area_frame, 3)

        # Flags
        if info["maior_rosto_frac"] >= ROSTO_AREA_DOMINANTE:
            info["flags"].append("rosto_dominante")
        if info["brilho_medio"] < BRILHO_MUITO_ESCURO:
            info["flags"].append("muito_escuro")
        if info["saturacao_media"] < SATURACAO_MONO:
            info["flags"].append("pouca_cor")
    except Exception as e:
        info["flags"].append(f"erro:{type(e).__name__}")
    return info


def consolidar_heuristica(frames_info: list) -> dict:
    """
    Junta a análise de vários frames de um asset num veredito de suspeita.
    Returns: {suspeito, motivos:[...], resumo}
    """
    if not frames_info:
        return {"suspeito": True, "motivos": ["sem frames analisados"], "resumo": {}}

    n = len(frames_info)
    rostos_dom = sum(1 for f in frames_info if "rosto_dominante" in f["flags"])
    escuros    = sum(1 for f in frames_info if "muito_escuro" in f["flags"])
    mono       = sum(1 for f in frames_info if "pouca_cor" in f["flags"])
    brilho_med = int(sum(f["brilho_medio"] for f in frames_info) / n)

    motivos = []
    # Rosto dominante na MAIORIA dos frames = pessoa em destaque (tipo "homem no sofá")
    if rostos_dom >= max(1, n // 2):
        motivos.append(f"rosto dominante em {rostos_dom}/{n} frames "
                       f"(pessoa em destaque — pode não combinar com produto)")
    if escuros >= max(1, n // 2):
        motivos.append(f"frames escuros ({escuros}/{n}, brilho médio {brilho_med})")
    if mono >= max(1, n // 2):
        motivos.append(f"pouca cor ({mono}/{n} frames quase mono)")

    return {
        "suspeito": len(motivos) > 0,
        "motivos":  motivos,
        "resumo":   {"frames": n, "rostos_dominantes": rostos_dom,
                     "escuros": escuros, "mono": mono, "brilho_medio": brilho_med},
    }


# =================================================================
# CAMADA 2 — VISION DECISION (Gemini Vision: "isso combina com o produto?")
# =================================================================
# A Camada 1 (heurística OpenCV acima) pesca rosto/escuro/mono, mas NÃO
# entende contexto: uma girafa colorida e bem iluminada passa como "limpa".
# Esta camada dá olhos de verdade ao Jarvis — manda 1 frame de cada clipe pro
# Gemini Vision e pergunta se tem relação com o produto. O que for reprovado
# vira status 'suspeito', e o editing_brain já exclui suspeitos da montagem.
#
# Reusa o MESMO padrão do brain/vision_analyzer.py (google.genai + Client +
# generate_content + inline_data) e o MESMO modelo central (GEMINI_VISION_MODEL
# = gemini-2.5-flash-lite, free tier alto). Não cria 2ª forma de chamar a API.
#
# Política de decisão: na DÚVIDA, MANTÉM o clipe. Só marca suspeito quando o
# Gemini diz NÃO com clareza. Assim nunca deixa o produto sem material por engano.

import base64 as _base64

# Cliente Gemini (singleton) — mesmo desenho do vision_analyzer
_gemini_client = None


def _get_gemini_client():
    """Cliente Gemini singleton, no mesmo padrão do brain/vision_analyzer.py."""
    global _gemini_client
    if _gemini_client is None:
        try:
            from google import genai
        except Exception as e:
            raise RuntimeError(f"google-genai não instalado ({e})")
        import os as _os
        api_key = _os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY não definida.")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _eh_erro_quota_gemini(exc) -> bool:
    """Detecta quota Gemini esgotada (mesma lógica do vision_analyzer)."""
    msg = str(exc).lower()
    return any(p in msg for p in ("resource_exhausted", "quota"))


PROMPT_RELEVANCIA = """Você está auditando um frame de um vídeo curto de divulgação \
de um produto de e-commerce. O produto é: "{produto}".

Sua tarefa: dizer se a imagem TEM RELAÇÃO com esse produto ou com o universo dele \
(uso, contexto, ambiente, benefício, pessoa usando, ou o próprio produto).

Seja TOLERANTE: cenas de cozinha pra um utensílio de cozinha, mãos preparando \
comida, bancada, ingredientes — tudo isso TEM relação. Só reprove se a imagem for \
claramente DESCONEXA do produto (ex: girafa, animal aleatório, estrada, paisagem \
sem nada a ver, esporte sem relação).

Responda EXATAMENTE neste formato JSON, sem texto adicional, sem markdown:
{{
  "relacionado": true ou false,
  "confianca": "alta" | "media" | "baixa",
  "motivo": "explicação curta do que você vê e por que combina ou não"
}}"""


def avaliar_relevancia_frame(frame_path: Path, produto: str,
                              max_tentativas: int = 2) -> dict:
    """
    Pergunta ao Gemini Vision se um frame tem relação com o produto.

    Returns: {relacionado: bool, confianca: str, motivo: str, erro?: str}
    Em caso de falha de API, retorna relacionado=True (na dúvida MANTÉM) com
    o campo 'erro' preenchido — pra nunca excluir clipe por causa de falha técnica.
    """
    import json as _json
    try:
        with open(frame_path, "rb") as f:
            img_b64 = _base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return {"relacionado": True, "confianca": "baixa",
                "motivo": "falha ao ler frame", "erro": str(e)}

    # detecta mime pelo sufixo (frames são .jpg)
    sufixo = frame_path.suffix.lower()
    mime = "image/png" if sufixo == ".png" else "image/jpeg"

    prompt = PROMPT_RELEVANCIA.format(produto=produto)
    payload = [{"parts": [
        {"inline_data": {"mime_type": mime, "data": img_b64}},
        {"text": prompt},
    ]}]

    try:
        client = _get_gemini_client()
    except Exception as e:
        return {"relacionado": True, "confianca": "baixa",
                "motivo": "Gemini indisponível", "erro": str(e)}

    backoff = [3, 6]
    ultimo_erro = None
    for tentativa in range(1, max_tentativas + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_VISION_MODEL, contents=payload)
            texto = (response.text or "").strip()
            if texto.startswith("```"):
                linhas = texto.split("\n")
                texto = "\n".join(linhas[1:-1])
            dados = _json.loads(texto)
            return {
                "relacionado": bool(dados.get("relacionado", True)),
                "confianca":   dados.get("confianca", "media"),
                "motivo":      dados.get("motivo", ""),
            }
        except Exception as e:
            ultimo_erro = e
            # quota esgotada → não adianta retry, aborta MANTENDO o clipe
            if _eh_erro_quota_gemini(e):
                log.warning(f"      🚫 Gemini quota excedida — mantendo clipe por segurança")
                return {"relacionado": True, "confianca": "baixa",
                        "motivo": "quota Gemini excedida", "erro": str(e)}
            if tentativa < max_tentativas:
                import time as _t
                _t.sleep(backoff[min(tentativa - 1, len(backoff) - 1)])

    # falhou todas → na dúvida MANTÉM
    return {"relacionado": True, "confianca": "baixa",
            "motivo": "falha na avaliação de visão", "erro": str(ultimo_erro)}


def avaliar_relevancia_clipe(frames: list, produto: str,
                              pausa_entre: float = 0.0) -> dict:
    """
    Avalia a relevância de um CLIPE olhando MÚLTIPLOS frames (início, meio, fim),
    não só o do meio. Um clipe do Pixabay pode começar mostrando o produto e
    TERMINAR mostrando planta/paisagem — auditar só 1 frame deixa esse lixo passar.

    Regra: o clipe é REPROVADO se QUALQUER frame for claramente irrelevante
    (conf média/alta). Um clipe só é "bom" se for relevante do começo ao fim.

    Otimização (short-circuit): para no PRIMEIRO frame reprovado — se o início
    já é planta, nem checa o resto (economiza chamadas de API). Só gasta os 3
    quando o clipe é bom de verdade.

    Returns: o veredito do frame que decidiu (reprovado, ou o último OK), com
    um campo extra 'frames_avaliados' (quantas chamadas de API foram feitas).
    """
    if not frames:
        return {"relacionado": True, "confianca": "baixa",
                "motivo": "sem frames", "frames_avaliados": 0}

    ultimo_ok = None
    chamadas = 0
    total = len(frames)
    for idx, frame in enumerate(frames):
        if chamadas > 0 and pausa_entre:
            import time as _t
            _t.sleep(pausa_entre)
        v = avaliar_relevancia_frame(frame, produto)
        chamadas += 1

        # erro de API (quota etc): não conta como reprovação, mantém clipe.
        # Aborta o loop (não adianta tentar os outros frames com quota zerada).
        if v.get("erro"):
            v["frames_avaliados"] = chamadas
            return v

        rel = v.get("relacionado", True)
        conf = v.get("confianca", "media")
        # REPROVOU com confiança razoável em QUALQUER frame → suspeito (para já)
        if not rel and conf in ("media", "alta"):
            posicao = ("início" if idx == 0
                       else "fim" if idx == total - 1 else "meio")
            v["motivo"] = f"[{posicao}] {v.get('motivo','')}"
            v["frames_avaliados"] = chamadas
            return v
        # frame OK (ou "não" com baixa confiança) → guarda e segue checando
        ultimo_ok = v

    # Nenhum frame reprovou → clipe aprovado (devolve o último veredito OK)
    if ultimo_ok is None:
        ultimo_ok = {"relacionado": True, "confianca": "baixa", "motivo": "ok"}
    ultimo_ok["frames_avaliados"] = chamadas
    return ultimo_ok


# =================================================================
# CONTACT SHEET (grade de frames pra revisão rápida)
# =================================================================

def montar_contact_sheet(frames: list, saida: Path, titulo: str = "",
                          suspeito: bool = False) -> Optional[Path]:
    """Monta uma imagem-grade com os frames + título (PIL)."""
    if not _PIL_OK or not frames:
        return None
    try:
        thumb_w, thumb_h = 320, 180
        cols = min(len(frames), 3)
        rows = (len(frames) + cols - 1) // cols
        margem, faixa_titulo = 8, 40
        W = cols * thumb_w + (cols + 1) * margem
        H = rows * thumb_h + (rows + 1) * margem + faixa_titulo

        # Fundo: vermelho-escuro se suspeito, cinza se ok
        cor_fundo = (60, 25, 25) if suspeito else (30, 30, 35)
        sheet = Image.new("RGB", (W, H), cor_fundo)
        draw = ImageDraw.Draw(sheet)

        # Título
        marca = "⚠ SUSPEITO" if suspeito else "○"
        try:
            draw.text((margem, 10), f"{marca}  {titulo}", fill=(255, 255, 255))
        except Exception:
            pass

        for i, fp in enumerate(frames):
            try:
                im = Image.open(fp).convert("RGB")
                im.thumbnail((thumb_w, thumb_h))
                r, c = divmod(i, cols)
                x = margem + c * (thumb_w + margem)
                y = faixa_titulo + margem + r * (thumb_h + margem)
                sheet.paste(im, (x, y))
            except Exception:
                continue

        saida.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(saida, "JPEG", quality=85)
        return saida
    except Exception as e:
        log.warning(f"   falha contact sheet: {str(e)[:60]}")
        return None


# =================================================================
# B-ROLL / ASSETS DO PRODUTO
# =================================================================

def _cena_do_arquivo(nome: str) -> str:
    n = nome.lower()
    for cena in CENAS:
        if n.startswith(f"{cena}_") or f"_{cena}_" in n:
            return cena
    return "?"


def listar_assets(produto: str) -> list:
    slug = slugificar_produto(produto)
    pasta = PRODUTOS_ROOT / slug
    assets = []
    for sub, tipo in (("raw", "video"), ("imagens", "imagem")):
        d = pasta / sub
        if d.exists():
            for f in sorted(d.iterdir()):
                if f.is_file() and f.suffix.lower() in (EXT_VIDEO | EXT_IMG):
                    eh_video = f.suffix.lower() in EXT_VIDEO
                    assets.append({
                        "arquivo": f.name, "caminho": f,
                        "tipo": "video" if eh_video else "imagem",
                        "cena_esperada": _cena_do_arquivo(f.name),
                    })
    return assets


# =================================================================
# CACHE DE VISÃO (reusa veredito do Gemini entre execuções)
# =================================================================
# Auditar com Gemini custa cota/tempo. Uma vez que o modelo "viu" um clipe e
# decidiu, não faz sentido re-perguntar toda vez. O cache guarda o veredito por
# (arquivo + produto) num JSON. Na próxima execução, clipe já visto = pula a API.
# Isso torna o audit INCREMENTAL: a 1ª passada audita tudo; as próximas só
# avaliam o que é novo. Economiza cota (o gargalo de hoje) e tempo.

CACHE_VISION_PATH = PLANS_DIR / "visual_audit_cache.json"


def _carregar_cache_vision() -> dict:
    """Carrega o cache de vereditos da visão. Retorna {} se não existir."""
    try:
        if CACHE_VISION_PATH.exists():
            return json.loads(CACHE_VISION_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"   ⚠️  Falha ao ler cache de visão ({e}) — começando vazio")
    return {}


def _salvar_cache_vision(cache: dict) -> None:
    """Salva o cache de vereditos da visão (best-effort)."""
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_VISION_PATH.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
    except Exception as e:
        log.warning(f"   ⚠️  Falha ao salvar cache de visão: {e}")


def _chave_cache(arquivo: str, produto: str) -> str:
    """Chave do cache: arquivo + produto (mesmo clipe pode servir a 2 produtos)."""
    return f"{slugificar_produto(produto)}::{arquivo}"


# =================================================================
# PIPELINE PRINCIPAL
# =================================================================

def auditar_produto(produto: str, n_frames: int = 3,
                    usar_vision: bool = False) -> dict:
    log.info("=" * 60)
    log.info(f"👁️  VISUAL AUDIT — '{produto}'")
    log.info(f"   Frames por vídeo: {n_frames} | OpenCV: {'✅' if _CV2_OK else '❌'} | "
             f"PIL: {'✅' if _PIL_OK else '❌'}")
    log.info(f"   Camada 2 (Gemini Vision): {'✅ LIGADA' if usar_vision else '❌ desligada (só heurística)'}")
    if FFMPEG_BIN:
        log.info(f"   FFmpeg:  ✅ {FFMPEG_BIN}")
    else:
        log.info(f"   FFmpeg:  ❌ usando fallback OpenCV")
    if FFPROBE_BIN:
        log.info(f"   FFprobe: ✅ {FFPROBE_BIN}")
    else:
        log.info(f"   FFprobe: ❌ duração via OpenCV")
    log.info("=" * 60)

    slug = slugificar_produto(produto)
    audit_dir = AUDIT_ROOT / slug
    audit_dir.mkdir(parents=True, exist_ok=True)

    assets = listar_assets(produto)
    log.info(f"   📦 {len(assets)} asset(s) encontrado(s)")
    if not assets:
        log.warning(f"   ⚠️  Nenhum asset em assets/produtos/{slug}/")
        return {"produto": produto, "slug": slug, "total": 0, "assets": []}

    resultado = {
        "produto": produto, "slug": slug,
        "auditado_em": datetime.now().isoformat(timespec="seconds"),
        "total": len(assets), "suspeitos": 0,
        "vision_ligada": usar_vision, "reprovados_vision": 0,
        "vision_via_cache": 0, "vision_chamadas_api": 0,
        "assets": [],
    }

    # Cache de visão: reusa vereditos de execuções anteriores (economiza cota)
    cache_vision = _carregar_cache_vision() if usar_vision else {}
    if usar_vision and cache_vision:
        log.info(f"   💾 Cache de visão: {len(cache_vision)} veredito(s) salvos")
    PAUSA_ENTRE_CHAMADAS = 4.0  # segundos — respeita ~15 req/min do tier grátis
    houve_chamada_api = False   # controla a pausa (só pausa após chamada real)

    for i, a in enumerate(assets, 1):
        log.info(f"\n[{i}/{len(assets)}] {a['arquivo']} (cena: {a['cena_esperada']})")
        asset_audit_dir = audit_dir / a["arquivo"]

        # Extrai frames / thumbnail
        if a["tipo"] == "video":
            frames = extrair_frames(a["caminho"], asset_audit_dir, n_frames)
            log.info(f"   🎞️  {len(frames)} frame(s) extraído(s)")
        else:
            thumb = gerar_thumbnail_imagem(a["caminho"], asset_audit_dir)
            frames = [thumb] if thumb else []
            log.info(f"   🖼️  thumbnail gerado")

        # Heurística (Camada 1 — barata, offline)
        frames_info = [analisar_frame(f) for f in frames if f]
        veredito = consolidar_heuristica(frames_info)

        # ── Camada 2 — Vision Decision (Gemini): "isso combina com o produto?" ──
        vision = None
        suspeito_vision = False
        if usar_vision and frames:
            chave = _chave_cache(a["arquivo"], produto)
            if chave in cache_vision:
                # Já auditado antes → reusa veredito (zero cota, instantâneo)
                vision = cache_vision[chave]
                resultado["vision_via_cache"] += 1
                log.info(f"   💾 Vision (cache): {'OK' if vision.get('relacionado', True) else 'REPROVOU'}")
            else:
                # Novo → pausa pra respeitar rate limit, depois chama a API.
                # Avalia MÚLTIPLOS frames (início/meio/fim) com short-circuit:
                # pega lixo que aparece em qualquer parte do clipe, não só no meio.
                if houve_chamada_api:
                    import time as _t
                    _t.sleep(PAUSA_ENTRE_CHAMADAS)
                vision = avaliar_relevancia_clipe(
                    frames, produto, pausa_entre=PAUSA_ENTRE_CHAMADAS)
                resultado["vision_chamadas_api"] += vision.get("frames_avaliados", 1)
                houve_chamada_api = True
                # só cacheia vereditos VÁLIDOS (não cacheia falha de quota/erro)
                if not vision.get("erro"):
                    cache_vision[chave] = vision

            rel = vision.get("relacionado", True)
            conf = vision.get("confianca", "media")
            if vision.get("erro"):
                log.info(f"   👁️‍🗨️  Vision: indisponível ({vision['motivo']}) — mantém clipe")
            elif not rel and conf in ("media", "alta"):
                # Gemini tem certeza razoável que NÃO combina → suspeito
                suspeito_vision = True
                resultado["reprovados_vision"] += 1
                log.warning(f"   🚫 Vision REPROVOU [{conf}]: {vision.get('motivo','')}")
            elif not rel:
                # disse não, mas com baixa confiança → na dúvida MANTÉM
                log.info(f"   👁️‍🗨️  Vision incerto (não-relacionado mas conf baixa) — mantém clipe")
            else:
                log.info(f"   👁️  Vision OK [{conf}]: {vision.get('motivo','')[:60]}")

        # Status final: suspeito se heurística OU vision reprovou
        eh_suspeito = veredito["suspeito"] or suspeito_vision

        # Contact sheet
        cs = montar_contact_sheet(
            frames, asset_audit_dir / "_contact_sheet.jpg",
            titulo=f"{a['arquivo']} [{a['cena_esperada']}]",
            suspeito=eh_suspeito)

        status = "suspeito" if eh_suspeito else "pendente_revisao_visual"
        if eh_suspeito:
            resultado["suspeitos"] += 1
            motivos_todos = list(veredito["motivos"])
            if suspeito_vision:
                motivos_todos.append(f"Vision: {vision.get('motivo','irrelevante')}")
            log.warning(f"   ⚠️  SUSPEITO: {'; '.join(motivos_todos)}")
        else:
            log.info(f"   ○ pendente revisão (nada levantou bandeira)")

        resultado["assets"].append({
            "arquivo":       a["arquivo"],
            "tipo":          a["tipo"],
            "cena_esperada": a["cena_esperada"],
            "status":        status,
            "frames":        [str(f) for f in frames if f],
            "contact_sheet": str(cs) if cs else None,
            "heuristica":    veredito,
            "vision":        vision,
        })

    # Salva o cache de visão atualizado (pra próxima execução reusar)
    if usar_vision:
        _salvar_cache_vision(cache_vision)

    # Resumo
    log.info(f"\n📋 RESUMO")
    log.info(f"   Total: {resultado['total']} | Suspeitos: {resultado['suspeitos']}"
             + (f" | Reprovados pela Vision: {resultado['reprovados_vision']}" if usar_vision else ""))
    if usar_vision:
        log.info(f"   👁️  Vision: {resultado['vision_chamadas_api']} chamada(s) à API, "
                 f"{resultado['vision_via_cache']} reusada(s) do cache")
    if resultado["suspeitos"]:
        log.warning(f"   ⚠️  Suspeitos (serão excluídos da montagem):")
        for a in resultado["assets"]:
            if a["status"] == "suspeito":
                motivos = list(a["heuristica"]["motivos"])
                if a.get("vision") and not a["vision"].get("relacionado", True):
                    motivos.append(f"Vision: {a['vision'].get('motivo','')}")
                log.warning(f"      • {a['arquivo']} ({a['cena_esperada']}): "
                            f"{'; '.join(motivos) or 'reprovado'}")

    return resultado


def salvar_relatorio(resultado: dict) -> Optional[str]:
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        path = PLANS_DIR / "visual_audit_resultado.json"
        path.write_text(json.dumps(resultado, ensure_ascii=False, indent=2,
                                    default=str), encoding="utf-8")
        return str(path)
    except Exception as e:
        log.warning(f"falha ao salvar relatório: {e}")
        return None


# =================================================================
# CLI
# =================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Visual Audit — extrai frames + heurísticas pra auditar assets")
    parser.add_argument("--produto", required=True, help="Nome do produto")
    parser.add_argument("--frames", type=int, default=3,
                        help="Frames por vídeo (default 3)")
    parser.add_argument("--vision", action="store_true",
                        help="Liga a Camada 2 (Gemini Vision): avalia se cada "
                             "clipe combina com o produto e marca os desconexos "
                             "(girafa/estrada/etc) como suspeitos. Usa cota Gemini.")
    parser.add_argument("--abrir-relatorio", action="store_true",
                        dest="abrir", help="Mostra o último relatório e sai")
    args = parser.parse_args()

    if args.abrir:
        path = PLANS_DIR / "visual_audit_resultado.json"
        if not path.exists():
            print("Nenhum relatório ainda. Rode sem --abrir-relatorio primeiro.")
            return 1
        data = json.loads(path.read_text(encoding="utf-8"))
        print("=" * 60)
        print(f"  👁️  VISUAL AUDIT — {data.get('produto')}")
        print(f"  Auditado: {data.get('auditado_em')}")
        print(f"  Total: {data.get('total')} | Suspeitos: {data.get('suspeitos')}")
        print("=" * 60)
        for a in data.get("assets", []):
            marca = "⚠️ " if a["status"] == "suspeito" else "○ "
            print(f"\n  {marca}{a['arquivo']} [{a['cena_esperada']}] — {a['status']}")
            if a["heuristica"]["motivos"]:
                for m in a["heuristica"]["motivos"]:
                    print(f"       • {m}")
            if a.get("contact_sheet"):
                print(f"       contact sheet: {a['contact_sheet']}")
        return 0

    log.info("=" * 60)
    log.info(f"👁️  VISUAL AUDIT AGENT v1")
    log.info("=" * 60)

    r = auditar_produto(args.produto, n_frames=args.frames, usar_vision=args.vision)
    path = salvar_relatorio(r)
    if path:
        log.info(f"\n💾 Relatório: {path}")
        log.info(f"   Frames/contact sheets em: shared/visual_audit/{r.get('slug')}/")

    return 0


if __name__ == "__main__":
    sys.exit(main())