# providers/fal_provider.py
# Provider Fal.ai — agregador de modelos de vídeo (Kling, SVD, Sora, etc).
# Uma API só pra dezenas de modelos. text-to-video.
#
# Dois caminhos de chamada:
#   1. lib oficial `fal_client` (pip install fal-client) — preferido
#   2. REST puro via `requests` — fallback se a lib não estiver instalada
#
# Auth: env FAL_KEY (a lib lê sozinha; no REST mandamos no header Authorization).
# Modelo configurável por env FAL_MODEL (default: Kling 1.6 standard, barato).
# Custo: consome créditos Fal (~centavos/clipe nos modelos standard).
#
# Doc: https://fal.ai/models/fal-ai/kling-video/...
#
# A resposta da Fal traz o vídeo em result["video"]["url"].

import os
import time
from pathlib import Path

try:
    import requests
    _REQUESTS_OK = True
except Exception:
    _REQUESTS_OK = False

try:
    import fal_client
    _FAL_LIB_OK = True
except Exception:
    _FAL_LIB_OK = False

from providers.base_provider import BaseProvider, novo_resultado

# Endpoint REST (fallback). A lib usa isso por baixo dos panos.
FAL_QUEUE_BASE = "https://queue.fal.run"

POLL_INTERVALO_SEG = 5
POLL_TIMEOUT_SEG = 360


class FalProvider(BaseProvider):
    nome = "fal"
    tipo_saida = "video"
    descricao = "Agregador Fal.ai (Kling/SVD/Sora via 1 API) — requer FAL_KEY"

    # Modelo configurável. Default = Kling 1.6 standard (bom custo/qualidade).
    # Outros: fal-ai/kling-video/v2.1/master/text-to-video (melhor, mais caro),
    #         fal-ai/stable-video-diffusion (mais barato).
    model = os.environ.get("FAL_MODEL", "fal-ai/kling-video/v1.6/standard/text-to-video")
    aspect_ratio = "9:16"   # vertical TikTok
    duration = "5"          # Kling aceita "5" ou "10" (string)

    def _token(self):
        # A Fal aceita FAL_KEY (padrão da lib). Aceitamos FAL_API_KEY como alias.
        return (os.environ.get("FAL_KEY")
                or os.environ.get("FAL_API_KEY")
                or "").strip() or None

    def disponivel(self) -> bool:
        # Precisa de token E (lib OU requests) pra funcionar
        return self._token() is not None and (_FAL_LIB_OK or _REQUESTS_OK)

    def motivo_indisponivel(self) -> str:
        if self._token() is None:
            return "FAL_KEY nao configurada (env var)"
        if not (_FAL_LIB_OK or _REQUESTS_OK):
            return "nem 'fal-client' nem 'requests' instalados (pip install fal-client)"
        return ""

    def gerar(self, prompt, cena, produto, arquivo_esperado, output_dir,
              dry_run=False):
        if dry_run:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="dry_run",
                mensagem=f"[dry-run] Fal geraria via {self.model} ({self.duration}s {self.aspect_ratio})",
            )
        if not self.disponivel():
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="no_credentials",
                mensagem=self.motivo_indisponivel(),
            )
        try:
            # Garante que a lib enxergue a key (aceita alias FAL_API_KEY)
            if not os.environ.get("FAL_KEY") and self._token():
                os.environ["FAL_KEY"] = self._token()

            if _FAL_LIB_OK:
                url_video = self._gerar_via_lib(prompt)
            else:
                url_video = self._gerar_via_rest(prompt)

            if not url_video:
                return novo_resultado(
                    self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                    sucesso=False, status="erro",
                    erro="resposta sem video.url",
                    mensagem="Fal não retornou URL de vídeo",
                )
            return self._baixar(url_video, cena, prompt, arquivo_esperado, output_dir)

        except Exception as e:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="erro",
                erro=f"{type(e).__name__}: {str(e)[:300]}",
                mensagem="Falha ao chamar Fal.ai",
            )

    # ── Caminho 1: lib oficial fal_client ────────────────────────────
    def _gerar_via_lib(self, prompt) -> str:
        args = {
            "prompt":       prompt,
            "duration":     self.duration,
            "aspect_ratio": self.aspect_ratio,
        }
        # subscribe() bloqueia até concluir e já devolve o resultado
        result = fal_client.subscribe(self.model, arguments=args, with_logs=False)
        # resultado pode vir como dict direto ou com .data
        data = result.get("data") if isinstance(result, dict) and "data" in result else result
        video = (data or {}).get("video") if isinstance(data, dict) else None
        return (video or {}).get("url") if isinstance(video, dict) else None

    # ── Caminho 2: REST puro (fallback sem a lib) ────────────────────
    def _gerar_via_rest(self, prompt) -> str:
        headers = {
            "Authorization": f"Key {self._token()}",
            "Content-Type":  "application/json",
        }
        body = {
            "prompt":       prompt,
            "duration":     self.duration,
            "aspect_ratio": self.aspect_ratio,
        }
        # POST inicial → request_id
        url_submit = f"{FAL_QUEUE_BASE}/{self.model}"
        resp = requests.post(url_submit, json=body, headers=headers, timeout=30)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"HTTP {resp.status_code} no submit: {resp.text[:300]}")
        data = resp.json()
        request_id = data.get("request_id") or data.get("id")
        if not request_id:
            # algumas respostas síncronas já trazem o vídeo
            v = (data.get("video") or {}).get("url")
            if v:
                return v
            raise RuntimeError(f"sem request_id: {str(data)[:200]}")

        # Poll status
        url_status = f"{FAL_QUEUE_BASE}/{self.model}/requests/{request_id}/status"
        url_result = f"{FAL_QUEUE_BASE}/{self.model}/requests/{request_id}"
        inicio = time.time()
        while time.time() - inicio < POLL_TIMEOUT_SEG:
            time.sleep(POLL_INTERVALO_SEG)
            try:
                rs = requests.get(url_status, headers=headers, timeout=30)
                if rs.status_code != 200:
                    continue
                status = (rs.json().get("status") or "").upper()
                if status in ("COMPLETED", "OK", "SUCCESS"):
                    rr = requests.get(url_result, headers=headers, timeout=30)
                    rd = rr.json()
                    rd = rd.get("data") if "data" in rd else rd
                    return ((rd.get("video") or {}).get("url")
                            if isinstance(rd, dict) else None)
                if status in ("FAILED", "ERROR"):
                    raise RuntimeError(f"geração falhou: {str(rs.json())[:200]}")
            except RuntimeError:
                raise
            except Exception:
                continue
        raise RuntimeError(f"timeout ({POLL_TIMEOUT_SEG}s) request_id={request_id}")

    # ── Download ─────────────────────────────────────────────────────
    def _baixar(self, url_video, cena, prompt, arquivo_esperado, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        destino = output_dir / arquivo_esperado
        # usa requests se houver; senão urllib
        if _REQUESTS_OK:
            with requests.get(url_video, stream=True, timeout=180) as rv:
                rv.raise_for_status()
                with open(destino, "wb") as f:
                    for chunk in rv.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
        else:
            import urllib.request
            urllib.request.urlretrieve(url_video, str(destino))

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
            mensagem=f"Gerado via Fal ({tamanho // 1024}KB, model={self.model.split('/')[-2:]})",
        )