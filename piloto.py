#!/usr/bin/env python3
# piloto.py -- O TESTE DE FOGO, num comando só.
#
# produto da fila → roteiro → linha do tempo → MP4 → conferência
#
# POR QUE EXISTE
# A cadeia inteira já funciona peça por peça, mas cada peça foi provada
# separada e com foto genérica. O que ninguém viu ainda é o encontro de TODAS
# as peças reais: foto de produto de verdade, logo da conta, selo, voz do
# ElevenLabs com timestamps, template do .env da VPS. Defeito de integração só
# aparece aí — e encadear seis comandos à mão é onde se erra um parâmetro e se
# passa meia hora achando que o bug é do render.
#
# UM PRODUTO. Não oito. A mesma disciplina do `--teste` do WhatsApp, do
# `--limite 10` das métricas e do `--quantos 1`: render → crítica → ajuste →
# render. Automatizar um editor mediano é multiplicar mediania.
#
# NÃO POSTA NADA. Gera arquivo e imprime veredito. Publicar é decisão humana
# enquanto este piloto não tiver rodado bem várias vezes.
#
# Uso na VPS (dentro de ~/jarvis, com o .venv que carrega o .env):
#   .venv/bin/python piloto.py --fila 0
#   .venv/bin/python piloto.py --fila 0 --encaixe cover
#   .venv/bin/python piloto.py --nome "Luminária Polvo" --fotos /caminho/fotos

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SAIDA = BASE_DIR / "shared" / "renders"

EXT_OK = (".jpg", ".jpeg", ".png", ".webp")


def _log(m):
    print(f"[piloto] {m}", flush=True)


def _baixar(url: str, destino: Path) -> bool:
    try:
        import requests
        r = requests.get(url, timeout=45,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200 or len(r.content) < 2048:
            _log(f"   ⚠️  foto HTTP {r.status_code} ({len(r.content)}B): {url[:70]}")
            return False
        destino.write_bytes(r.content)
        return True
    except Exception as e:
        _log(f"   ⚠️  falhou baixar a foto: {str(e)[:90]}")
        return False


def _fotos_do_item(item: dict, pasta: Path) -> list:
    """Baixa as fotos do produto. A fila guarda URL, não arquivo.

    Aceita tanto `imagem` (uma) quanto `imagens` (lista) — a vitrine usa a
    primeira forma e nem todo item tem a segunda. Um produto com UMA foto ainda
    rende vídeo: o EDL faz punch-in na mesma imagem, que é como editor humano
    trabalha com pouco material.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    urls = [u for u in ([item.get("imagem")] + (item.get("imagens") or []))
            if isinstance(u, str) and u.startswith("http")]
    vistas, fora = set(), []
    for u in urls:
        if u in vistas:
            continue
        vistas.add(u)
        alvo = pasta / f"foto_{len(fora) + 1}.jpg"
        if _baixar(u, alvo):
            fora.append(alvo)
    return fora


def _telegram(video: Path, legenda: str, contato: Path = None) -> bool:
    """Manda o MP4 pro chat de admin. Best-effort, nunca quebra o piloto.

    Existe por um motivo bobo e real: o vídeo nasce na VPS e quem julga está no
    celular. O Dre tentou `./video.mp4` no shell e levou "Permission denied" —
    arquivo de vídeo não é executável, e não há navegador ali. Usa as MESMAS
    variáveis do resto do projeto (TELEGRAM_BOT_TOKEN + TELEGRAM_ALERT_CHAT_ID),
    e o chat de admin, nunca o grupo público de achadinhos.
    """
    import os
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = (os.getenv("TELEGRAM_ALERT_CHAT_ID")
            or os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not tok or not chat:
        _log("   Telegram não configurado (TELEGRAM_BOT_TOKEN / "
             "TELEGRAM_ALERT_CHAT_ID) — o vídeo ficou só no disco")
        return False
    try:
        import requests
        with video.open("rb") as f:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendVideo",
                              timeout=180, data={"chat_id": chat,
                                                 "caption": legenda[:1020]},
                              files={"video": (video.name, f, "video/mp4")})
        if r.status_code != 200:
            _log(f"   Telegram HTTP {r.status_code}: {r.text[:160]}")
            return False
        if contato and contato.exists():
            with contato.open("rb") as f:
                requests.post(f"https://api.telegram.org/bot{tok}/sendPhoto",
                              timeout=120, data={"chat_id": chat,
                                                 "caption": "quadros do piloto"},
                              files={"photo": (contato.name, f, "image/png")})
        _log("   📲 vídeo enviado no Telegram")
        return True
    except Exception as e:
        _log(f"   Telegram falhou: {str(e)[:110]}")
        return False


def _item_da_fila(indice: int) -> dict:
    import storyboard as SB
    if not SB.FILA.exists():
        raise SystemExit(f"[piloto] não achei a fila em {SB.FILA}")
    dados = [x for x in json.loads(SB.FILA.read_text(encoding="utf-8"))
             if isinstance(x, dict)]
    if not dados:
        raise SystemExit("[piloto] a fila está vazia")
    if not (0 <= indice < len(dados)):
        raise SystemExit(f"[piloto] índice {indice} fora da fila "
                         f"(há {len(dados)} itens: 0 a {len(dados) - 1})")
    return dados[indice]


def main():
    p = argparse.ArgumentParser(
        description="Produto -> roteiro -> EDL -> MP4 -> conferência.")
    p.add_argument("--fila", type=int, help="índice do produto em produtos_fila.json")
    p.add_argument("--nome", help="nome do produto (em vez de --fila)")
    p.add_argument("--preco", default="")
    p.add_argument("--nicho", default="")
    p.add_argument("--fotos", help="pasta com fotos locais (pula o download)")
    p.add_argument("--audio", choices=("narracao", "viral", "narracao_viral"),
                   default="narracao",
                   help="narracao é o único 100%% automático hoje")
    p.add_argument("--encaixe", choices=("contain", "cover"), default="contain",
                   help="contain: foto inteira, sobra fundo. cover: preenche a "
                        "caixa cortando as laterais")
    p.add_argument("--mudo", action="store_true")
    p.add_argument("--telegram", action="store_true",
                   help="manda o MP4 e a folha de contato no chat de admin")
    args = p.parse_args()

    import storyboard as SB
    import edl as EDL
    import render as R
    import conferir_render as CR

    # ── 1. produto ──────────────────────────────────────────────────────────
    tmp = Path(tempfile.mkdtemp(prefix="piloto_"))
    try:
        if args.fila is not None:
            item = _item_da_fila(args.fila)
            nome = (item.get("campeao") or item.get("produto") or "").strip()
            preco, link = item.get("preco", ""), item.get("link", "")
            nicho = args.nicho
            if not nicho:
                try:
                    import roteador_contas as RC
                    nicho = (RC.nicho_do_produto(nome) or "").strip().lower()
                except Exception as e:
                    _log(f"   roteador indisponível ({str(e)[:60]}) — nicho 'geral'")
            fotos = _fotos_do_item(item, tmp / "fotos")
        elif args.nome:
            nome, preco, link, nicho = args.nome, args.preco, "", args.nicho
            fotos = []
        else:
            p.error("use --fila N ou --nome '...'")

        if args.fotos:
            pasta = Path(args.fotos)
            fotos = sorted(f for f in pasta.iterdir()
                           if f.suffix.lower() in EXT_OK) if pasta.is_dir() else [pasta]
        if not fotos:
            raise SystemExit(
                "[piloto] nenhuma foto — a fila guarda URL e o download falhou, "
                "ou o produto entrou sem imagem. Use --fotos PASTA, ou rode "
                "`python3 preencher_fotos.py` antes")

        _log(f"produto: {nome}")
        _log(f"   nicho {nicho or 'geral'} · R$ {preco or '—'} · "
             f"{len(fotos)} foto(s)")

        # ── 2. roteiro ──────────────────────────────────────────────────────
        _log("1/4 roteiro")
        sb = SB.gerar(nome, preco, len(fotos), link, nicho)
        problemas = SB.validar(sb, len(fotos))
        if problemas:
            for x in problemas:
                _log(f"   ✗ {x}")
            raise SystemExit("[piloto] o roteiro não passou na validação")
        for a in SB.avisar(sb):
            _log(f"   👀 {a}")
        _log(f"   por {sb.get('roteiro_por')} · hook: "
             f"{(sb.get('hook') or {}).get('texto', '')[:60]}")

        # ── 3. linha do tempo ───────────────────────────────────────────────
        _log("2/4 linha do tempo")
        linha = EDL.montar(sb, args.audio)
        ruins = EDL.validar(linha)
        if ruins:
            for x in ruins:
                _log(f"   ✗ {x}")
            raise SystemExit("[piloto] o EDL saiu com problema")
        _log(f"   {len(linha['trilhas']['visual'])} cortes · "
             f"{linha['duracao_total']}s · logo "
             f"{linha.get('template', {}).get('logo')} "
             f"{linha.get('template', {}).get('handle')}")

        # ── 4. render ───────────────────────────────────────────────────────
        _log("3/4 render")
        SAIDA.mkdir(parents=True, exist_ok=True)
        import re as _re
        slug = _re.sub(r"[^a-z0-9]+", "_",
                       nome.lower()).strip("_")[:48] or "produto"
        alvo = SAIDA / f"piloto_{slug}.mp4"
        rel = R.renderizar(linha, str(fotos[0].parent if len(fotos) > 1 else fotos[0]),
                           alvo, mudo=args.mudo, encaixe=args.encaixe)
        _log(f"   {rel['duracao_arquivo']}s · {rel['tamanho_mb']} MB · "
             f"voz {'/'.join(rel.get('voz') or ['—'])}")

        # ── 5. conferência ──────────────────────────────────────────────────
        _log("4/4 conferência")
        r = CR.conferir(alvo, contato=True)

        print()
        icone = {"passou": "✅", "revisar": "👀", "reprovado": "❌"}[r["veredito"]]
        print(f"{'═' * 66}")
        print(f"{icone}  {r['veredito'].upper()}  ·  {nome[:44]}")
        print(f"{'═' * 66}")
        for chave, c in r["checagens"].items():
            i = {"passou": "✅", "atencao": "👀", "falhou": "❌", "nao_rodou": "—"}
            med = "" if c["medido"] is None else f"  ({c['medido']})"
            print(f"  {i[c['estado']]} {chave:17}{med}")
        for a in r["achados"]:
            print(f"\n  → {a['descricao']}")
        if rel["faltou"]:
            print("\n  o render avisou que faltou:")
            for x in rel["faltou"]:
                print(f"    · {x}")
        print(f"\n  vídeo    {alvo}")
        print(f"  quadros  {r['pasta_quadros']}")
        if args.telegram:
            _telegram(alvo,
                      f"{icone} {r['veredito'].upper()} · {nome[:70]}\n"
                      f"{rel['duracao_arquivo']}s · {rel['cortes']} cortes · "
                      f"voz {'/'.join(rel.get('voz') or ['—'])}",
                      Path(r["pasta_quadros"]) / "_contato.png")

        print("\n  NADA FOI POSTADO. Assista antes de decidir qualquer coisa.")
        return 1 if r["veredito"] == "reprovado" else 0
    finally:
        # as fotos baixadas ficam se o usuário passou --fotos (são dele)
        if not args.fotos:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
