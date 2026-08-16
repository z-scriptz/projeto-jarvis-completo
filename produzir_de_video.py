#!/usr/bin/env python3
# produzir_de_video.py -- um clipe de vídeo QUALQUER vira Reel TopShop completo.
#
# POR QUE EXISTE (15/08)
# O Dre está gerando um clipe de 8s no Kling (créditos grátis, com marca
# d'água) pra responder a pergunta que trava o caminho autoral há semanas:
# **uma foto de produto vira vídeo com movimento de verdade?**
#
# Só que sem isto o teste morreria em "ficou bonito". O caminho autoral
# (`piloto.py`) monta vídeo a partir de FOTOS — não aceita um clipe pronto.
# Então o clipe do Kling não teria como virar Reel, e a gente compararia
# impressão com impressão em vez de vídeo com vídeo.
#
# ⚠️ E A PEÇA JÁ EXISTIA. O `produzir_tiktok._produzir(pasta, plano, video)`
# recebe um ARQUIVO DE VÍDEO local + o JSON do produto e devolve o Reel
# completo: template TopShop, logo da conta, hook, narração, legenda,
# hashtags, `engajamento.json`, ledger, e a pasta pronta em
# `pronto_para_postar/`. É literalmente o que ele faz com viral do TikTok.
# Reciclar viral e "reciclar" um clipe do Kling é a MESMA operação.
#
# Este arquivo é só o adaptador: monta o inbox que aquela função espera e a
# chama. Nada de pipeline novo — pipeline novo aqui seria construir de novo o
# que já roda 44 vezes por semana.
#
# ⚠️ O PRODUTO VEM POR LINK, NÃO POR ÍNDICE. Mesma razão do `piloto
# --fila-link`: o gravador da mineração insere no topo ~11x por dia, e um
# índice aponta pra outro produto poucas horas depois — com o link de afiliado
# de outro produto junto.
#
# Uso (na VPS, dentro de ~/jarvis):
#   .venv/bin/python fila_qualidade.py --so-cache          # pega um link bom
#   .venv/bin/python produzir_de_video.py --video kling.mp4 \
#       --fila-link 'https://s.shopee.com.br/...'
#
# NÃO POSTA NADA. Deixa o pacote pronto e diz onde está.

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent


def _log(m):
    print(f"[de-video] {m}", flush=True)


def _item_por_link(link: str) -> dict:
    """O produto na fila, pelo link. Erra alto se não achar: produzir com o
    link de outro produto manda a comissão pro lugar errado."""
    import storyboard as SB
    if not SB.FILA.exists():
        raise SystemExit(f"[de-video] não achei a fila em {SB.FILA}")
    dados = [x for x in json.loads(SB.FILA.read_text(encoding="utf-8"))
             if isinstance(x, dict)]
    alvo = (link or "").strip()
    achados = [x for x in dados if (x.get("link") or "").strip() == alvo]
    if not achados:
        raise SystemExit(
            f"[de-video] nenhum produto da fila com este link:\n  {alvo}\n"
            f"  A fila tem {len(dados)} itens. Rode o `fila_qualidade.py` "
            f"pra pegar a lista atual.")
    return achados[0]


def main():
    p = argparse.ArgumentParser(
        description="Transforma um clipe de vídeo em Reel TopShop completo.")
    p.add_argument("--video", required=True, help="o arquivo .mp4 do clipe")
    p.add_argument("--fila-link", dest="fila_link", default="",
                   help="link de afiliado do produto na fila")
    p.add_argument("--nome", default="",
                   help="nome do produto (só se NÃO usar --fila-link)")
    p.add_argument("--link", default="",
                   help="link de afiliado (só se NÃO usar --fila-link)")
    p.add_argument("--nicho", default="", help="força o nicho/conta")
    p.add_argument("--manter", action="store_true",
                   help="não apaga a pasta temporária do inbox")
    args = p.parse_args()

    video = Path(args.video).expanduser()
    if not video.exists():
        raise SystemExit(f"[de-video] não achei o vídeo: {video}")

    sys.path.insert(0, str(BASE))
    try:
        import produzir_tiktok as PT
    except Exception as e:
        raise SystemExit(f"[de-video] não importei o produzir_tiktok: "
                         f"{str(e)[:100]}\n  (use o .venv: "
                         f".venv/bin/python produzir_de_video.py ...)")

    # ── de onde vem o produto ───────────────────────────────────────────────
    if args.fila_link:
        item = _item_por_link(args.fila_link)
        nome = (item.get("campeao") or item.get("produto") or "").strip()
        link = (item.get("link") or "").strip()
        info = {
            "produto": nome,
            "link_afiliado": link,
            "plataforma": (item.get("plataforma") or "shopee").lower(),
            "descricao": item.get("campeao") or "",
            "imagem": item.get("imagem", ""),
            "origem_url": item.get("origem", ""),
            "item_id": item.get("item_id", ""),
        }
    else:
        if not (args.nome and args.link):
            p.error("use --fila-link, ou --nome junto com --link")
        nome, link = args.nome.strip(), args.link.strip()
        info = {"produto": nome, "link_afiliado": link,
                "plataforma": "shopee", "descricao": nome}

    if args.nicho:
        info["nicho"] = args.nicho.strip().lower()

    _log(f"produto: {nome}")
    _log(f"clipe:   {video.name} ({video.stat().st_size / 1e6:.1f} MB)")

    # ── monta o inbox que o `_produzir` espera ──────────────────────────────
    # Pasta temporária de propósito: o inbox de verdade é do coletor do TikTok,
    # e misturar um teste manual lá dentro faria a próxima rodada do cron
    # produzir isto de novo sozinha.
    tmp = Path(tempfile.mkdtemp(prefix="de_video_", dir=str(BASE / "inbox_tiktok")
                                if (BASE / "inbox_tiktok").exists() else None))
    try:
        pasta = tmp / PT.H._slugify(nome)[:60]
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / f"video{video.suffix or '.mp4'}"
        shutil.copy2(video, destino)
        pj = pasta / "plano.json"
        pj.write_text(json.dumps(info, ensure_ascii=False, indent=2),
                      encoding="utf-8")

        _log("chamando a MESMA esteira que recicla viral do TikTok…")
        print()
        ok = PT._produzir(pasta, pj, destino)
        print()
        if not ok:
            _log("❌ a esteira não concluiu — a mensagem acima diz onde parou")
            return 1

        slug = PT.H._slugify(nome)
        saida = PT.H.BASE_DIR / "pronto_para_postar" / slug
        _log(f"✅ pacote pronto: {saida}")
        _log("   NADA foi postado. O daemon posta nos horários — se você NÃO "
             "quiser isso ainda, mova ou apague a pasta acima.")
        _log("   Confira antes:  ls -la " + str(saida))
        return 0
    finally:
        if args.manter:
            _log(f"(--manter: deixei {tmp})")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
