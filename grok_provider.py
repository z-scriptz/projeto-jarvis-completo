# providers/grok_provider.py
# Provider Grok Imagine (xAI) — geração de cenas text-to-video.
# API REAL implementada (start generation -> poll -> download).
#
# Fluxo (doc oficial api.x.ai/v1):
#   1. POST /videos/generations  -> request_id
#   2. GET  /videos/{request_id} -> status (done/...) + video.url
#   3. baixa url -> output_dir / arquivo_esperado
#
# Header: Authorization: Bearer <XAI_API_KEY>
# Custo: consome créditos da conta xAI (~US$0.08/seg de output em jun/2026).
#
# NOTA IMPORTANTE (jun/2026): alguns modelos de preview do Grok Imagine
# (ex: grok-imagine-video-1.5-preview) só fazem image-to-video, NÃO
# text-to-video puro. O modelo 'grok-imagine-video' (estável) faz t2v.
# Por isso o modelo é configurável via env GROK_IMAGINE_MODEL.
# Se a sua conta só tiver o preview, o provider vai retornar erro claro
# e a cascata cai pro próximo provider (PixVerse/HeyGen).

import os
import time
from pathlib import Path

try:
    import requests
    _REQUESTS_OK = True
except Exception:
    _REQUESTS_OK = False

from providers.base_provider import BaseProvider, novo_resultado

API_BASE = "https://api.x.ai/v1"
ENDPOINT_GERAR  = f"{API_BASE}/videos/generations"
ENDPOINT_STATUS = f"{API_BASE}/videos"  # /{request_id}

POLL_INTERVALO_SEG = 5
POLL_TIMEOUT_SEG = 360


class GrokProvider(BaseProvider):
    nome = "grok"
    tipo_saida = "video"
    descricao = "Cenas text-to-video via Grok Imagine (xAI) — requer XAI_API_KEY"

    # Configuráveis por env (default = modelo estável de t2v)
    model = os.environ.get("GROK_IMAGINE_MODEL", "grok-imagine-video")
    aspect_ratio = "9:16"   # vertical TikTok
    duration = 6            # segundos por clipe
    resolution = "720p"     # doc oficial xAI: 480p | 720p

    def _token(self):
        return os.environ.get("XAI_API_KEY", "").strip() or None

    def disponivel(self) -> bool:
        return _REQUESTS_OK and self._token() is not None

    def motivo_indisponivel(self) -> str:
        if not _REQUESTS_OK:
            return "lib 'requests' nao instalada (pip install requests)"
        if self._token() is None:
            return "XAI_API_KEY nao configurada (env var)"
        return ""

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token()}",
            "Content-Type":  "application/json",
        }

    def gerar(self, prompt, cena, produto, arquivo_esperado, output_dir,
              dry_run=False):
        if dry_run:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="dry_run",
                mensagem=f"[dry-run] Grok geraria {self.duration}s {self.aspect_ratio} ({self.model})",
            )
        if not self.disponivel():
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="no_credentials",
                mensagem=self.motivo_indisponivel(),
            )
        try:
            return self._chamar_api_grok(prompt, cena, arquivo_esperado, output_dir)
        except Exception as e:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="erro",
                erro=f"{type(e).__name__}: {str(e)[:160]}",
                mensagem="Falha ao chamar Grok Imagine",
            )

    def _chamar_api_grok(self, prompt, cena, arquivo_esperado, output_dir):
        body = {
            "model":        self.model,
            "prompt":       prompt,
            "aspect_ratio": self.aspect_ratio,
            "duration":     self.duration,
            "resolution":   self.resolution,
        }
        resp = requests.post(ENDPOINT_GERAR, json=body,
                              headers=self._headers(), timeout=30)

        # 429 = rate limit / cota (comum no Grok). Retorna erro claro pra
        # cascata cair pro próximo provider.
        if resp.status_code == 429:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="erro",
                erro="HTTP 429: rate limit / cota Grok esgotada",
                mensagem="Grok sem cota agora — cascata tenta próximo provider",
            )
        if resp.status_code not in (200, 201):
            # Erro detalhado: status + body + contexto (sem expor o token).
            erro_detalhado = (
                f"HTTP {resp.status_code} @ POST {ENDPOINT_GERAR} "
                f"(model={self.model}, dur={self.duration}s, "
                f"ar={self.aspect_ratio}, res={self.resolution}) "
                f"| body_resp: {resp.text[:1000]}"
            )
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="erro",
                erro=erro_detalhado,
                mensagem=f"POST generations falhou (HTTP {resp.status_code})",
            )

        data = resp.json()
        # A resposta pode trazer request_id direto, ou um id aninhado
        request_id = (data.get("request_id") or data.get("id")
                      or (data.get("data") or {}).get("id"))
        if not request_id:
            # Algumas respostas já trazem a URL direto (geração síncrona)
            url_direta = ((data.get("video") or {}).get("url")
                          or (data.get("data") or {}).get("url"))
            if url_direta:
                return self._baixar(url_direta, cena, prompt, arquivo_esperado, output_dir)
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="erro",
                erro=f"sem request_id: {str(data)[:160]}",
                mensagem="Resposta inesperada do Grok",
            )

        # Poll até concluir
        inicio = time.time()
        url_video = None
        while time.time() - inicio < POLL_TIMEOUT_SEG:
            time.sleep(POLL_INTERVALO_SEG)
            try:
                r_status = requests.get(f"{ENDPOINT_STATUS}/{request_id}",
                                         headers=self._headers(), timeout=30)
                if r_status.status_code != 200:
                    continue
                sd = r_status.json()
                status = (sd.get("status") or "").lower()
                if status in ("done", "completed", "succeeded"):
                    url_video = ((sd.get("video") or {}).get("url")
                                 or sd.get("video_url")
                                 or (sd.get("data") or {}).get("url"))
                    break
                elif status in ("failed", "error", "moderated"):
                    return novo_resultado(
                        self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                        sucesso=False, status="erro",
                        erro=f"status '{status}': {str(sd.get('error') or sd)[:120]}",
                        mensagem="Grok falhou/moderou a geração",
                    )
            except Exception:
                continue

        if not url_video:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="erro",
                erro=f"timeout ({POLL_TIMEOUT_SEG}s)",
                mensagem=f"Grok demorou demais (request_id={request_id})",
            )

        return self._baixar(url_video, cena, prompt, arquivo_esperado, output_dir)

    def _baixar(self, url_video, cena, prompt, arquivo_esperado, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        destino = output_dir / arquivo_esperado
        with requests.get(url_video, stream=True, timeout=180) as rv:
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
            mensagem=f"Gerado e baixado ({tamanho // 1024}KB, model={self.model})",
        )