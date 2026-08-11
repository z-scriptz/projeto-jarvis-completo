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


def _urls_do_item(item: dict) -> list:
    """As URLs de foto de um item da fila, na ordem em que valem a pena.

    Aceita tanto `imagem` (uma) quanto `imagens` (lista) — a vitrine usa a
    primeira forma e nem todo item tem a segunda.
    """
    return [u for u in ([item.get("imagem")] + (item.get("imagens") or []))
            if isinstance(u, str) and u.startswith("http")]


def _fotos_do_item(item: dict, pasta: Path) -> list:
    """Baixa as fotos do produto. A fila guarda URL, não arquivo.

    Um produto com UMA foto ainda rende vídeo: o EDL faz punch-in na mesma
    imagem, que é como editor humano trabalha com pouco material.

    Volta lista vazia por DOIS motivos diferentes, e quem chama precisa saber
    qual foi — 11/08 o Dre levou três rodadas de terminal pra descobrir que o
    item simplesmente não tinha URL, porque a mensagem de erro listava as duas
    causas possíveis sem dizer qual tinha acontecido. Por isso o log aqui.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    urls = _urls_do_item(item)
    if not urls:
        _log("   ⚠️  este item da fila não tem NENHUMA URL de foto "
             "('imagem' e 'imagens' vazios) — não é download que falhou, "
             "não há o que baixar")
        _log(f"      campos presentes no item: {', '.join(sorted(item))}")
        return []
    vistas, fora = set(), []
    for u in urls:
        if u in vistas:
            continue
        vistas.add(u)
        alvo = pasta / f"foto_{len(fora) + 1}.jpg"
        if _baixar(u, alvo):
            fora.append(alvo)
    return fora


def _detalhe(img, frac: float):
    """A região de MAIOR DETALHE da foto, na fração pedida do quadro.

    Foto de e-commerce quase nunca é o produto centralizado: é o produto num
    canto, uma modelo de outro, e um recorte de "antes/depois" espremido embaixo.
    Cortar no centro pegaria fundo liso. Aqui a imagem é dividida numa grade e
    cada célula recebe a variância do cinza — que é uma medida crua de "quanta
    coisa acontece aqui". A janela com mais detalhe acumulado vira o close.

    Cru de propósito: detectar produto de verdade é trabalho pro Gemini Vision
    (o visual_audit_agent já tem a tubulação). Variância não sabe o que é
    produto, mas sabe onde NÃO é fundo — e pra escolher um close isso basta.
    """
    from PIL import ImageStat
    L = img.convert("L")
    W, H = img.size
    jw, jh = int(W * frac), int(H * frac)
    passo_x, passo_y = max(1, (W - jw) // 6), max(1, (H - jh) // 6)
    melhor, alvo = -1.0, (0, 0)
    for y in range(0, H - jh + 1, passo_y):
        for x in range(0, W - jw + 1, passo_x):
            v = ImageStat.Stat(L.crop((x, y, x + jw, y + jh))).stddev[0]
            if v > melhor:
                melhor, alvo = v, (x, y)
    x, y = alvo
    return img.crop((x, y, x + jw, y + jh))


def _variacoes(foto: Path, pasta: Path, quantas: int, avisos: list) -> list:
    """UMA foto -> vários ENQUADRAMENTOS distintos.

    POR QUE ISTO EXISTE (10/08)
    A `productOfferV2` da Shopee devolve UM `imageUrl` por produto. O Dre viu o
    resultado e resumiu: "só tem uma imagem durante todo o vídeo". O punch-in
    do EDL disfarça — mas disfarçar não é resolver, e ele percebeu na primeira
    olhada.

    Editor humano com uma foto só não mostra a foto inteira vinte segundos: ele
    ABRE em plano geral, FECHA num detalhe, volta. São planos diferentes da
    mesma imagem, e o olho aceita como cortes de verdade.

    ⚠️ ISTO NÃO SUBSTITUI TER MAIS FOTO. É o melhor que dá pra fazer com o
    material que existe; o gargalo continua sendo a origem.
    """
    from PIL import Image
    pasta.mkdir(parents=True, exist_ok=True)
    img = Image.open(foto).convert("RGB")
    if min(img.size) < 500:
        avisos.append(f"{foto.name} tem {img.width}x{img.height} — pequena "
                      "demais pra recortar close sem borrar; vai só o plano geral")
        return [foto]

    fora = [foto]
    for i, frac in enumerate([0.62, 0.78][:max(0, quantas - 1)], 2):
        try:
            corte = _detalhe(img, frac)
            alvo = pasta / f"var_{i}.jpg"
            corte.save(alvo, quality=94)
            fora.append(alvo)
        except Exception as e:
            avisos.append(f"variação {i} falhou: {str(e)[:70]}")
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


def _indices_com_foto() -> list:
    """Os índices da fila que têm pelo menos uma URL de foto.

    Existe só para o erro poder dizer 'use o índice 7' em vez de 'não achei
    foto'. Falha em silêncio: é ajuda de mensagem de erro, e mensagem de erro
    que estoura ao explicar outro erro é pior que mensagem curta.
    """
    try:
        import storyboard as SB
        dados = [x for x in json.loads(SB.FILA.read_text(encoding="utf-8"))
                 if isinstance(x, dict)]
        return [i for i, it in enumerate(dados) if _urls_do_item(it)]
    except Exception:
        return []


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
    p.add_argument("--variacoes", type=int, default=3,
                   help="com UMA foto só, deriva N enquadramentos dela "
                        "(1 desliga)")
    p.add_argument("--forcar", action="store_true",
                   help="produz mesmo com material nível D")
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
            # A mensagem antiga listava causas possíveis e mandava rodar
            # `preencher_fotos.py` — que mexe na VITRINE, não nesta fila. Quem
            # seguiu a instrução gastou uma rodada de terminal pra descobrir
            # que ela não tinha nada a ver com o problema. Agora o erro diz o
            # que houve E qual índice usar.
            saida_erro = ["[piloto] nenhuma foto — sem imagem não há vídeo."]
            if args.fila is not None:
                com_foto = _indices_com_foto()
                if com_foto:
                    amostra = ", ".join(str(i) for i in com_foto[:12])
                    saida_erro.append(
                        f"  O índice {args.fila} está sem foto. Com foto: "
                        f"{amostra}{' …' if len(com_foto) > 12 else ''}")
                    saida_erro.append(
                        f"  Tente:  python3 piloto.py --fila {com_foto[0]}")
                else:
                    saida_erro.append(
                        "  NENHUM item da fila tem URL de foto. Isso é problema "
                        "da coleta, não do piloto — a fila entrou sem imagem.")
            saida_erro.append("  Ou aponte fotos locais:  --fotos PASTA")
            raise SystemExit("\n".join(saida_erro))

        avisos_fotos = []
        if len(fotos) == 1 and args.variacoes > 1:
            fotos = _variacoes(fotos[0], tmp / "vars", args.variacoes,
                               avisos_fotos)

        # ── o que temos, ANTES de gastar roteiro, voz e render ──────────────
        try:
            import asset_ranker as AR
            nota = AR.avaliar(fotos)
            _log(f"assets: nível {nota['nivel']} · {nota['distintas']} "
                 f"distinta(s) de {nota['quantas']} · diversidade "
                 f"{nota['diversidade']}")
            _log(f"   → {nota['veredito']}")
            for a, b, d in nota["pares_iguais"][:3]:
                _log(f"   🔁 {a} e {b} são a mesma imagem pro olho ({d})")
            if nota["nivel"] == "D" and not args.forcar:
                raise SystemExit(
                    "[piloto] material insuficiente — nível D. Use --forcar "
                    "pra produzir assim mesmo, sabendo do que se trata")
        except SystemExit:
            raise
        except Exception as e:
            _log(f"   (ranker indisponível: {str(e)[:70]})")

        _log(f"produto: {nome}")
        _log(f"   nicho {nicho or 'geral'} · R$ {preco or '—'} · "
             f"{len(fotos)} enquadramento(s)"
             + (" (derivados de 1 foto)" if len(fotos) > 1
                and fotos[0].parent != fotos[-1].parent else ""))
        for a in avisos_fotos:
            _log(f"   👀 {a}")

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
        # com variações, as fotos ficam em pastas diferentes (a original no
        # download, os cortes em vars/). Copio todas pra uma pasta só, porque o
        # render lê uma pasta e ordena por nome — e ordem errada é cena errada.
        if len(fotos) > 1:
            juntas = tmp / "quadros"
            juntas.mkdir(parents=True, exist_ok=True)
            novas = []
            for i, f in enumerate(fotos, 1):
                d = juntas / f"a{i:02d}{f.suffix}"
                shutil.copy2(f, d)
                novas.append(d)
            fotos = novas
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
