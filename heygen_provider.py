# providers/heygen_provider.py
# Provider HeyGen — avatar/apresentador falando (UGC controlado).
# API REAL implementada (lista avatar+voz -> gera -> poll -> download).
#
# Fluxo (doc oficial api.heygen.com):
#   1. GET  /v2/avatars            -> escolhe 1 avatar_id (cacheia)
#   2. GET  /v2/voices             -> escolhe 1 voice_id PT-BR (cacheia)
#   3. POST /v2/video/generate     -> video_id
#   4. GET  /v1/video_status.get   -> status (pending/processing/completed/failed) + url
#   5. baixa url -> output_dir / arquivo_esperado
#
# Header: X-Api-Key
# IMPORTANTE: HeyGen gera avatar FALANDO um roteiro. O "prompt" aqui deve ser
# o ROTEIRO (texto falado), não a descricao visual. O agente passa o texto
# de copy quando o provider e' heygen.
#
# Custo: consome creditos. Roda 1 cena por vez, espera aprovacao.

import os
import time
from pathlib import Path

try:
    import requests
    _REQUESTS_OK = True
except Exception:
    _REQUESTS_OK = False

from providers.base_provider import BaseProvider, novo_resultado

API_BASE = "https://api.heygen.com"
ENDPOINT_AVATARS = f"{API_BASE}/v2/avatars"
ENDPOINT_VOICES  = f"{API_BASE}/v2/voices"
ENDPOINT_GERAR   = f"{API_BASE}/v2/video/generate"
ENDPOINT_STATUS  = f"{API_BASE}/v1/video_status.get"  # ?video_id=

POLL_INTERVALO_SEG = 12
POLL_TIMEOUT_SEG = 420  # avatar leva mais tempo


class HeyGenProvider(BaseProvider):
    nome = "heygen"
    tipo_saida = "video"
    descricao = "Avatar/apresentador falando (UGC) — requer HEYGEN_API_KEY"

    # cache de avatar/voz escolhidos (evita re-listar a cada cena)
    _avatar_id = None
    _voice_id = None

    # dimensao vertical TikTok
    largura = 720
    altura = 1280

    def _token(self):
        return os.environ.get("HEYGEN_API_KEY", "").strip() or None

    def disponivel(self) -> bool:
        return _REQUESTS_OK and self._token() is not None

    def motivo_indisponivel(self) -> str:
        if not _REQUESTS_OK:
            return "lib 'requests' nao instalada (pip install requests)"
        if self._token() is None:
            return "HEYGEN_API_KEY nao configurada (env var)"
        return ""

    def _headers(self) -> dict:
        return {"X-Api-Key": self._token(), "Content-Type": "application/json"}

    def _resolver_avatar_e_voz(self):
        """Lista avatares e vozes, escolhe 1 de cada (prioriza voz PT-BR)."""
        if self._avatar_id and self._voice_id:
            return  # ja em cache

        # Avatar
        ra = requests.get(ENDPOINT_AVATARS, headers=self._headers(), timeout=30)
        ra.raise_for_status()
        avatares = (ra.json().get("data") or {}).get("avatars") or []
        if not avatares:
            raise RuntimeError("nenhum avatar disponivel na conta HeyGen")
        type(self)._avatar_id = avatares[0].get("avatar_id")

        # Voz — prioriza pt/portuguese
        rv = requests.get(ENDPOINT_VOICES, headers=self._headers(), timeout=30)
        rv.raise_for_status()
        vozes = (rv.json().get("data") or {}).get("voices") or []
        voz_ptbr = None
        for v in vozes:
            lang = (v.get("language") or "").lower()
            if "portug" in lang or lang.startswith("pt"):
                voz_ptbr = v.get("voice_id")
                break
        type(self)._voice_id = voz_ptbr or (vozes[0].get("voice_id") if vozes else None)
        if not self._voice_id:
            raise RuntimeError("nenhuma voz disponivel na conta HeyGen")

    def gerar(self, prompt, cena, produto, arquivo_esperado, output_dir,
              dry_run=False):
        if dry_run:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="dry_run",
                mensagem="[dry-run] HeyGen geraria avatar falando o roteiro",
            )
        if not self.disponivel():
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="no_credentials",
                mensagem=self.motivo_indisponivel(),
            )
        try:
            return self._chamar_api_heygen(prompt, cena, arquivo_esperado, output_dir)
        except Exception as e:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, prompt, arquivo_esperado,
                sucesso=False, status="erro",
                erro=f"{type(e).__name__}: {str(e)[:160]}",
                mensagem="Falha ao chamar HeyGen",
            )

    def _chamar_api_heygen(self, roteiro, cena, arquivo_esperado, output_dir):
        self._resolver_avatar_e_voz()

        body = {
            "video_inputs": [{
                "character": {
                    "type": "avatar",
                    "avatar_id": self._avatar_id,
                    "avatar_style": "normal",
                },
                "voice": {
                    "type": "text",
                    "input_text": roteiro[:1500],  # limite seguro
                    "voice_id": self._voice_id,
                },
            }],
            "dimension": {"width": self.largura, "height": self.altura},
        }
        resp = requests.post(ENDPOINT_GERAR, json=body,
                              headers=self._headers(), timeout=30)
        if resp.status_code != 200:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, roteiro, arquivo_esperado,
                sucesso=False, status="erro",
                erro=f"HTTP {resp.status_code}: {resp.text[:160]}",
                mensagem="POST generate falhou",
            )
        data = resp.json()
        if data.get("error"):
            return novo_resultado(
                self.nome, cena, self.tipo_saida, roteiro, arquivo_esperado,
                sucesso=False, status="erro",
                erro=str(data.get("error"))[:160],
                mensagem="API HeyGen retornou erro",
            )
        video_id = (data.get("data") or {}).get("video_id")
        if not video_id:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, roteiro, arquivo_esperado,
                sucesso=False, status="erro",
                erro=f"sem video_id: {str(data)[:160]}",
                mensagem="Resposta inesperada",
            )

        inicio = time.time()
        url_video = None
        while time.time() - inicio < POLL_TIMEOUT_SEG:
            time.sleep(POLL_INTERVALO_SEG)
            try:
                r_status = requests.get(ENDPOINT_STATUS,
                                         params={"video_id": video_id},
                                         headers=self._headers(), timeout=30)
                if r_status.status_code != 200:
                    continue
                sd = (r_status.json().get("data") or {})
                status = sd.get("status")
                if status == "completed":
                    url_video = sd.get("video_url")
                    break
                elif status == "failed":
                    return novo_resultado(
                        self.nome, cena, self.tipo_saida, roteiro, arquivo_esperado,
                        sucesso=False, status="erro",
                        erro=f"falhou: {sd.get('error') or sd.get('failure_message') or '?'}",
                        mensagem="HeyGen falhou na geracao",
                    )
            except Exception:
                continue

        if not url_video:
            return novo_resultado(
                self.nome, cena, self.tipo_saida, roteiro, arquivo_esperado,
                sucesso=False, status="erro",
                erro=f"timeout ({POLL_TIMEOUT_SEG}s)",
                mensagem=f"HeyGen demorou demais (video_id={video_id})",
            )

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
                self.nome, cena, self.tipo_saida, roteiro, arquivo_esperado,
                sucesso=False, status="erro",
                erro=f"arquivo pequeno ({tamanho}B)",
                mensagem="Download suspeito",
            )

        return novo_resultado(
            self.nome, cena, self.tipo_saida, roteiro, arquivo_esperado,
            sucesso=True, status="ok", arquivo=str(destino),
            mensagem=f"Gerado ({tamanho // 1024}KB, avatar={self._avatar_id}, video_id={video_id})",
        )