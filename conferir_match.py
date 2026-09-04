#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# conferir_match.py -- o vídeo mostra o MESMO produto que o link vende?
#
# POR QUE ISSO EXISTE (05/09/2026)
# ────────────────────────────────
# O match com a loja é por SOBREPOSIÇÃO DE PALAVRAS, e isso deixa passar coisas
# que nenhum humano deixaria — todos tirados do log de verdade:
#
#   'Abridor de Casca de Ovo'  → 'Copo Térmico 360ml Inox'   (casou: abridor, casca)
#   'Estação de pintura'       → 'Estação Férrea Miniatura'  (casou: estacao)
#   'July July'                → 'Kit 3 Sutiã Básico'        (casou: july)
#   'This'                     → 'Camiseta THIS & THAT'      (casou: this)
#
# O post sai bonito, o link ABRE, e a pessoa recebe outra coisa. Isso é pior que
# link morto: o clique acontece e queima a confiança de quem clicou.
#
# 📌 O DRE PERGUNTOU "daria pra tirar print do produto e jogar no Google?".
# A ideia está certa; o Google é que não serve — o Lens não tem API pública,
# e o SerpAPI custa ~US$50/mês. Mas nós temos algo MELHOR e já pago: o frame do
# vídeo E a foto do produto na loja. Comparar os dois é mais preciso que busca
# reversa, porque confere contra o candidato específico em vez de procurar no
# mundo inteiro.
#
# ⚠️ RODA NO QUE JÁ ESTÁ NA FILA. Os 2171 pacotes do inbox já têm o vídeo
# baixado e a URL da foto no plano.json — dá pra achar os matches errados que
# JÁ estão lá, sem coletar nada de novo.
#
# Uso (VPS):
#   .venv/bin/python conferir_match.py --amostra 20     # MEDE custo e acerto
#   .venv/bin/python conferir_match.py                  # confere tudo (só lista)
#   .venv/bin/python conferir_match.py --marcar         # bloqueia os errados
import argparse
import json
import os
import random
import subprocess
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INBOX = BASE_DIR / "inbox_tiktok"
MODELO = os.getenv("GEMINI_MODELO_MATCH", "gemini-2.5-flash")


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
        return cand
    return None


def _frame(video: Path, dur: float = 0) -> bytes:
    """UM frame do meio do vídeo. Um só, de propósito: dois frames dobram o
    custo da imagem e a pergunta aqui é binária ('é o mesmo objeto?'), não
    'que produto é este?' — essa já foi respondida lá atrás pela visão."""
    pos = max(1.0, (float(dur) or 6.0) * 0.5)
    f = video.with_suffix(".match.jpg")
    try:
        subprocess.run(["ffmpeg", "-y", "-ss", f"{pos:.1f}", "-i", str(video),
                        "-vframes", "1", "-vf", "scale=512:-2", "-q:v", "4",
                        str(f)], capture_output=True, timeout=40)
        return f.read_bytes() if f.exists() and f.stat().st_size > 500 else b""
    except Exception:
        return b""
    finally:
        try:
            f.unlink()
        except Exception:
            pass


def _baixar_imagem(url: str) -> bytes:
    if not url or not url.startswith("http"):
        return b""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            b = r.read(3_000_000)
        return b if len(b) > 500 else b""
    except Exception:
        return b""


_PROMPT = (
    "Duas imagens. A PRIMEIRA é um quadro de um vídeo que mostra um produto. "
    "A SEGUNDA é a foto de um produto anunciado numa loja.\n\n"
    "PERGUNTA: é o MESMO produto, ou pelo menos o mesmo TIPO de produto que "
    "resolve a mesma coisa?\n\n"
    "Responda SÓ uma palavra:\n"
    "SIM  — mesmo produto ou mesmo tipo (cor/marca/modelo diferentes tudo bem)\n"
    "NAO  — produtos diferentes, quem clicasse receberia outra coisa\n"
    "TALVEZ — o quadro do vídeo não deixa ver o produto direito\n\n"
    "⚠️ Na dúvida entre SIM e NAO, responda TALVEZ. Só diga NAO quando as duas "
    "imagens mostram claramente coisas diferentes."
)


def conferir(frame: bytes, foto: bytes) -> tuple:
    """(veredito, custo_tokens). Veredito: sim / nao / talvez / erro."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key or not frame or not foto:
        return "erro", 0
    try:
        from google import genai
        from google.genai import types
        cli = genai.Client(api_key=key)
        r = cli.models.generate_content(
            model=MODELO,
            contents=[types.Part.from_bytes(data=frame, mime_type="image/jpeg"),
                      types.Part.from_bytes(data=foto, mime_type="image/jpeg"),
                      _PROMPT])
        t = (r.text or "").strip().upper()
        # ⚠️ o número de tokens vem do PRÓPRIO retorno, não de estimativa minha.
        # Foi estimativa minha ("são centavos") que virou R$50 em 04/09.
        u = getattr(r, "usage_metadata", None)
        toks = int(getattr(u, "total_token_count", 0) or 0) if u else 0
        if t.startswith("SIM"):
            return "sim", toks
        if t.startswith("NAO") or t.startswith("NÃO"):
            return "nao", toks
        if t.startswith("TALVEZ"):
            return "talvez", toks
        return "erro", toks
    except Exception as e:
        print(f"      ⚠️ {str(e)[:70]}")
        return "erro", 0


def main() -> int:
    ap = argparse.ArgumentParser(description="o vídeo mostra o produto do link?")
    ap.add_argument("--amostra", type=int, default=0,
                    help="confere só N pacotes sorteados e MEDE custo/acerto")
    ap.add_argument("--marcar", action="store_true",
                    help="bloqueia os reprovados (sem isto, só lista)")
    a = ap.parse_args()

    arq = _carregar_env()
    print(f"📄 .env: {arq or '(não achei — vai falhar)'}")
    if not os.getenv("GEMINI_API_KEY"):
        print("❌ GEMINI_API_KEY vazio — abortando antes de gastar tempo")
        return 1
    if not INBOX.exists():
        print(f"❌ {INBOX} não existe")
        return 1

    # só o que dá pra conferir: precisa de vídeo E de foto da loja.
    # Pacote de Amazon não tem foto (o link é busca), então fica de fora — e
    # isso é metade do inbox. Dizer "confere tudo" seria mentira.
    alvos = []
    sem_foto = 0
    for pj in sorted(INBOX.glob("*/plano.json")):
        try:
            info = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            continue
        if info.get("nao_e_produto") or info.get("match_conferido"):
            continue
        vids = list(pj.parent.glob("video.*"))
        if not vids:
            continue
        if not (info.get("imagem") or "").startswith("http"):
            sem_foto += 1
            continue
        alvos.append((pj, info, vids[0]))

    print(f"📦 {len(alvos)} pacote(s) conferíveis "
          f"(vídeo + foto da loja) · {sem_foto} sem foto (Amazon/busca)\n")
    if not alvos:
        print("✅ nada a conferir")
        return 0

    total_conferivel = len(alvos)      # guardado ANTES de cortar a amostra
    if a.amostra:
        random.shuffle(alvos)
        alvos = alvos[:a.amostra]
        print(f"🔬 MODO AMOSTRA: {len(alvos)} de {total_conferivel} sorteados, "
              f"nada será marcado\n")

    t0 = time.time()
    tot = {"sim": 0, "nao": 0, "talvez": 0, "erro": 0}
    tokens = 0
    reprovados = []

    for pj, info, vid in alvos:
        nome = (info.get("produto") or "?")[:38]
        # ⚠️ o plano.json NÃO guarda duração (conferi os campos que o coletor
        # escreve). Passar `info.get("duracao")` seria ler um campo que não
        # existe e achar que estou usando a duração real — o `_frame` cai no
        # padrão de 6s e tira o quadro aos 3s, que é o que de fato acontece.
        frame = _frame(vid)
        foto = _baixar_imagem(info.get("imagem", ""))
        veredito, tk = conferir(frame, foto)
        tokens += tk
        tot[veredito] = tot.get(veredito, 0) + 1

        marca = {"sim": "✅", "nao": "❌", "talvez": "🤔", "erro": "⚠️"}[veredito]
        print(f"   {marca} {nome:40} · {pj.parent.name[:30]}")
        if veredito == "nao":
            reprovados.append((pj, info, nome))

        if a.marcar and veredito == "nao":
            # ⚠️ MARCA, NÃO APAGA — mesma regra do limpar_inbox. Um veredito de
            # modelo errado tem de ser reversível tirando uma chave do JSON.
            info["nao_e_produto"] = True
            info["motivo_bloqueio"] = "conferir_match: vídeo não mostra o produto do link"
        if a.marcar:
            info["match_conferido"] = veredito
            pj.write_text(json.dumps(info, ensure_ascii=False, indent=2),
                          encoding="utf-8")

    seg = time.time() - t0
    n = len(alvos)
    print(f"\n── resultado ──")
    print(f"   ✅ {tot['sim']} confere · ❌ {tot['nao']} ERRADO · "
          f"🤔 {tot['talvez']} incerto · ⚠️ {tot['erro']} falhou")
    print(f"   ⏱️  {seg:.0f}s ({seg/max(1,n):.1f}s por pacote)")

    if tokens:
        # ⚠️ CUSTO MEDIDO, NÃO ESTIMADO. Em 04/09 eu disse "são centavos" sobre
        # 2171 chamadas e o Dre gastou R$50+. O preço vem do .env pra não ficar
        # chumbado errado aqui dentro.
        usd_mtok = float(os.getenv("GEMINI_USD_POR_MTOK", "0.30"))
        brl_usd = float(os.getenv("USD_BRL", "5.40"))
        custo = tokens / 1_000_000 * usd_mtok * brl_usd
        print(f"   🪙 {tokens:,} tokens · R$ {custo:.2f} nesta rodada "
              f"(R$ {custo/max(1,n):.4f} por pacote)")
        if a.amostra:
            proj = custo / max(1, n) * total_conferivel
            print(f"   📊 PROJEÇÃO pros {total_conferivel} conferíveis: "
                  f"R$ {proj:.2f}  ({seg/max(1,n)*total_conferivel/60:.0f} min)")
            print(f"      ⚠️ projeção, não medição — o número real sai da rodada "
                  f"cheia. Mas é conta, não palpite.")

    if reprovados and not a.marcar:
        print(f"\n❌ {len(reprovados)} com link de produto ERRADO:")
        for _pj, _i, nm in reprovados[:20]:
            print(f"   • {nm}")
        print(f"\n📋 pra bloquear: .venv/bin/python conferir_match.py --marcar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
