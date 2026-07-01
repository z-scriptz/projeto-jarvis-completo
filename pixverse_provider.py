# providers/pixverse_provider.py
# Provider PixVerse — geração de cenas visuais/lifestyle (text-to-video).
# API REAL implementada (text-to-video -> poll status -> download).
#
# Fluxo (doc oficial app-api.pixverse.ai/openapi/v2):
#   1. POST /video/text/generate -> Resp.video_id
#   2. GET  /video/result/{id}   -> status (1=ok,5=gerando,7=moderacao,8=falhou) + url
#   3. baixa url -> output_dir / arquivo_esperado
#
# Headers: API-KEY, Ai-trace-id (uuid unico por request), Content-Type
# Custo: consome creditos. Por isso o agente roda 1 cena por vez e
# espera voce aprovar antes da proxima.

import os
import time
import uuid
from pathlib import Path

try:
    import requests
    _REQUESTS_OK = True
except Exception:
    _REQUESTS_OK = False

from providers.base_provider import BaseProvider, novo_resultado

API_BASE = "https://app-api.pixverse.ai/openapi/v2"
ENDPOINT_GERAR  = f"{API_BASE}/video/text/generate"
ENDPOINT_STATUS = f"{API_BASE}/video/result"  # /{video_id}

ST_OK = 1
ST_GERANDO = 5
ST_MODERACAO = 7
ST_FALHOU = 8

POLL_INTERVALO_SEG = 12
POLL_TIMEOUT_SEG = 360


class PixverseProvider(BaseProvider):
    nome = "pixverse"
    tipo_saida = "video"
    descricao = "Cenas lifestyle/produto text-to-video — requer PIXVERSE_API_KEY"

    aspect_ratio = "9:16"
    duration = 5
    model = "v5"
    quality = "720p"

    def _token(self):
        return os.environ.get("PIXVERSE_API_KEY", "").strip() or None

    def disponivel(self) -> bool:
        return _REQUESTS_OK and self._token() is not None

    def motivo_indisponivel(self) -> str:
        if not _REQUESTS_OK:
            return "lib 'requests' nao instalada (pip install requests)"
        if self._token() is None:
            return "PIXVERSE_API_KEY nao configurada (env var)"
        return ""

    def _headers(self) -> dict:
        return {
            "API-KEY":      self._token(),
            "Ai-trace-id":  str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

    def gerar(self, prompt, cena, produto, arquivo_esperado, output_dir,
              dry_run=False):
        if dry_run:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="dry_run",
                mensagem=f"[dry-run] PixVerse geraria {self.duration}s {self.aspect_ratio} {self.model}",
            )
        if not self.disponivel():
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="no_credentials",
                mensagem=self.motivo_indisponivel(),
            )
        try:
            return self._chamar_api_pixverse(prompt, cena, arquivo_esperado, output_dir)
        except Exception as e:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="erro",
                erro=f"{type(e).__name__}: {str(e)[:160]}",
                mensagem="Falha ao chamar PixVerse",
            )

    def _chamar_api_pixverse(self, prompt, cena, arquivo_esperado, output_dir):
        body = {
            "aspect_ratio":    self.aspect_ratio,
            "duration":        self.duration,
            "model":           self.model,
            "quality":         self.quality,
            "prompt":          prompt,
            "negative_prompt": "blurry, distorted, watermark, text, logo, low quality",
        }
        resp = requests.post(ENDPOINT_GERAR, json=body,
                              headers=self._headers(), timeout=30)
        if resp.status_code != 200:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="erro",
                erro=f"HTTP {resp.status_code}: {resp.text[:160]}",
                mensagem="POST generate falhou",
            )
        data = resp.json()
        if data.get("ErrCode") not in (0, None):
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="erro",
                erro=f"ErrCode {data.get('ErrCode')}: {data.get('ErrMsg', '')}",
                mensagem="API retornou erro na criacao",
            )
        video_id = (data.get("Resp") or {}).get("video_id")
        if not video_id:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="erro",
                erro=f"sem video_id: {str(data)[:160]}",
                mensagem="Resposta inesperada",
            )

        inicio = time.time()
        url_video = None
        while time.time() - inicio < POLL_TIMEOUT_SEG:
            time.sleep(POLL_INTERVALO_SEG)
            try:
                r_status = requests.get(f"{ENDPOINT_STATUS}/{video_id}",
                                         headers=self._headers(), timeout=30)
                if r_status.status_code != 200:
                    continue
                sd = r_status.json()
                resp_status = sd.get("Resp") or {}
                status_code = resp_status.get("status")
                if status_code == ST_OK:
                    url_video = resp_status.get("url")
                    break
                elif status_code == ST_MODERACAO:
                    return novo_resultado(
                        self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                        sucesso=False, status="erro",
                        erro="moderacao de conteudo (status 7) — ajuste o prompt",
                        mensagem="Prompt bloqueado pela moderacao PixVerse",
                    )
                elif status_code == ST_FALHOU:
                    return novo_resultado(
                        self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                        sucesso=False, status="erro",
                        erro="geracao falhou (status 8)",
                        mensagem="PixVerse falhou na geracao",
                    )
            except Exception:
                continue

        if not url_video:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="erro",
                erro=f"timeout ({POLL_TIMEOUT_SEG}s) esperando geracao",
                mensagem=f"PixVerse demorou demais (video_id={video_id})",
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        destino = output_dir / arquivo_esperado
        with requests.get(url_video, stream=True, timeout=120) as rv:
            rv.raise_for_status()
            with open(destino, "wb") as f:
                for chunk in rv.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        tamanho = destino.stat().st_size
        if tamanho < 1024:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="erro",
                erro=f"arquivo pequeno ({tamanho}B)",
                mensagem="Download suspeito",
            )

        return novo_resultado(
            self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
            sucesso=True, status="ok", arquivo=str(destino),
            mensagem=f"Gerado e baixado ({tamanho // 1024}KB, video_id={video_id})",
        )