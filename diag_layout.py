#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# diag_layout.py -- responde "por que ESTA conta saiu diferente das outras?"
# lendo o .env DE VERDADE, em vez de eu adivinhar pelo print do Instagram.
#
# POR QUE ISSO EXISTE (03/09/2026)
# ────────────────────────────────
# O Dre: *"o bug é nas duas contas: topshoptech e topshopmoda, estilo ta
# quadrado e a letra + vídeo ta em desordem... e aparentemente a cor deles
# também continuam erradas"*.
#
# Eu tinha três hipóteses e nenhuma forma de escolher entre elas de fora: o que
# decide é o `.env` da VPS, que eu não vejo. E o roadmap já registra duas vezes
# eu concluindo de evidência indireta e errando (o @topshoppet_ "penalizado",
# que era falta de vídeo; os "18,3% de ganchos errados", que eram 2,5%).
#
# Então: em vez de opinar, este script IMPRIME a cadeia de decisão. Uma linha por
# nicho, e a coluna que diverge é o defeito.
#
# Uso (VPS):
#   .venv/bin/python diag_layout.py            # os 6 nichos
#   .venv/bin/python diag_layout.py tech moda  # só esses
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
NICHOS = ["geral", "moda", "beleza", "casa", "tech", "pet"]

# A cascata do render.py:503 — FORCE_BG ganha de BG_<NICHO>, que ganha de
# TOPSHOP_BG, que ganha da paleta. Quem estiver setado aqui MANDA.
GLOBAIS = ("FORCE_BG", "TOPSHOP_BG", "TOPSHOP_NICHO")
GEOMETRIA = ("VIDEO_W_FRAC", "VIDEO_Y", "VIDEO_RAIO", "LOGO_X", "LOGO_Y",
             "LOGO_TAM", "HK_FONT", "HK_ALT_LINHA", "HK_MARGEM", "HK_MARGEM_DIR",
             "HK_Y", "HK_GAP_VIDEO", "CTA_ATIVO", "HOOK_FONTE", "HOOK_PESO")


def _carregar_env():
    """⚠️ SEM ISSO O DIAGNÓSTICO MENTE. O `dinheiro.py` nasceu sem carregar o
    .env e falhou com um sintoma indistinguível de problema de schema — e o
    `hook_alana` tem um parágrafo inteiro sobre esse mesmo defeito. Um script
    que lê o ambiente TEM de carregar o arquivo que define o ambiente."""
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


def _quem_manda(nicho: str):
    """A chave que está decidindo o fundo deste nicho, na ordem do render.py."""
    for chave in ("FORCE_BG", "BG_" + nicho.upper(), "TOPSHOP_BG"):
        v = (os.environ.get(chave) or "").strip()
        if v:
            return chave, v
    return "paleta", ""


def main() -> int:
    arq = _carregar_env()
    if arq:
        print(f"📄 .env: {arq}")
    else:
        print("📄 .env: NENHUM ENCONTRADO — os valores abaixo são os defaults "
              "do código, NÃO os da produção. Rode isto dentro de ~/jarvis.")

    try:
        from shared.paleta import do_nicho, do_ambiente
    except Exception as e:
        print(f"❌ shared/paleta.py não importa: {e}")
        return 1

    # ── 1. QUEM TEM CANTO ARREDONDADO ───────────────────────────────────────
    print("\n══ 1. CANTOS ARREDONDADOS (o 'estilo tá quadrado') ══")
    try:
        from shared import moldura
        print(f"   ✅ shared/moldura.py presente — {moldura.resumo()}")
        _tem_moldura = True
    except Exception as e:
        print(f"   ❌ shared/moldura.py AUSENTE ({str(e)[:60]})")
        print("      → o narrated_video_agent sai com canto QUADRADO e o vídeo")
        print("        na geometria antiga (desalinhado do gancho). Deploy dele.")
        _tem_moldura = False

    for mod, cam in (("narrated_video_agent", "agents/"),
                     ("telegram_repurpose_hunter", "integrations/")):
        for base in (BASE_DIR / f"{mod}.py", BASE_DIR / cam / f"{mod}.py"):
            if not base.exists():
                continue
            txt = base.read_text(encoding="utf-8", errors="ignore")
            redondo = ("cantos_arredondados" in txt)
            # ⚠️ procura o IMPORT, não a palavra. Buscar "moldura" solto dava
            # `usa shared/moldura=sim` pro hunter por causa de um comentário
            # sobre "moldura estática" do auto-crop — falso positivo justamente
            # no arquivo que eu estava conferindo.
            usa_mold = ("from shared import moldura" in txt
                        or "from shared.moldura import" in txt
                        or "import shared.moldura" in txt)
            print(f"   {'✅' if redondo else '❌'} {base.relative_to(BASE_DIR)}: "
                  f"cantos={'sim' if redondo else 'NÃO'} · "
                  f"usa shared/moldura={'sim' if usa_mold else 'NÃO'}")

    # ── 2. O FUNDO DE CADA NICHO, E QUEM DECIDIU ────────────────────────────
    print("\n══ 2. FUNDO POR NICHO (a 'cor errada') ══")
    print(f"   {'nicho':8} {'paleta diz':10} {'vai sair':10} {'quem manda':16} veredito")
    alvos = [a.lower() for a in sys.argv[1:]] or NICHOS
    problemas = []
    # ⚠️ o loop abaixo ESCREVE TOPSHOP_NICHO pra simular cada nicho. Sem guardar
    # o original, a seção 3 acusava "TOPSHOP_NICHO=pet — chave global" — que era
    # o próprio diagnóstico se olhando no espelho. Alarme falso num script que
    # existe pra achar alarme verdadeiro é o pior defeito possível aqui.
    _nicho_orig = os.environ.get("TOPSHOP_NICHO")
    for n in alvos:
        try:
            esperado = do_nicho(n)["fundo_hex"]
        except Exception:
            esperado = "?"
        chave, valor = _quem_manda(n)
        # ⚠️ REPRODUZ A CASCATA DO render.py:503, não chama do_ambiente cru.
        # O `do_ambiente` só olha TOPSHOP_BG; o BG_<NICHO> é copiado PRA DENTRO
        # dele pelo render antes da chamada. Sem imitar esse passo, o
        # diagnóstico dizia "ok" com um BG_TECH=preto ligado — testado e
        # reprovado antes de subir.
        os.environ["TOPSHOP_NICHO"] = n
        _bg_orig = os.environ.get("TOPSHOP_BG")
        try:
            if valor:
                os.environ["TOPSHOP_BG"] = valor
            real = do_ambiente(n)["fundo_hex"]
        except Exception:
            real = "?"
        finally:
            if _bg_orig is None:
                os.environ.pop("TOPSHOP_BG", None)
            else:
                os.environ["TOPSHOP_BG"] = _bg_orig
        ok = (real.upper() == esperado.upper())
        if ok:
            veredito = "ok"
        else:
            veredito = f"⚠️ SOBRESCRITO por {chave}={valor}"
            problemas.append((n, chave, valor, esperado, real))
        print(f"   {n:8} {esperado:10} {real:10} {chave:16} {veredito}")
    if _nicho_orig is None:
        os.environ.pop("TOPSHOP_NICHO", None)
    else:
        os.environ["TOPSHOP_NICHO"] = _nicho_orig

    # ── 3. GEOMETRIA ────────────────────────────────────────────────────────
    print("\n══ 3. GEOMETRIA no .env (a 'letra + vídeo em desordem') ══")
    for k in GEOMETRIA:
        v = os.environ.get(k)
        print(f"   {k:16} = {v if v is not None else '(não setado — usa o default do código)'}")
    for k in GLOBAIS:
        v = os.environ.get(k)
        if v:
            print(f"   ⚠️ {k:14} = {v}   ← chave global, afeta TODAS as contas")

    # ── 4. VEREDITO ─────────────────────────────────────────────────────────
    print("\n══ 4. O QUE FAZER ══")
    if problemas:
        chaves = sorted({p[1] for p in problemas if p[1] != "paleta"})
        print(f"   🎨 {len(problemas)} nicho(s) com fundo sobrescrito: "
              f"{', '.join(p[0] for p in problemas)}")
        if chaves:
            print(f"      Remova do .env: {', '.join(chaves)}")
            print(f"      .venv/bin/python layout_v2.py --aplicar   "
                  f"(já remove BG_<NICHO> desde 03/09)")
    else:
        print("   🎨 fundo: nenhum nicho sobrescrito — a paleta está mandando ✅")
    if not _tem_moldura:
        print("   📐 faça o deploy de shared/moldura.py (é o canto quadrado)")
    if not os.environ.get("VIDEO_RAIO"):
        print("   📐 VIDEO_RAIO não setado — o default (28) vale, mas confirme "
              "que o layout_v2 rodou")
    return 1 if (problemas or not _tem_moldura) else 0


if __name__ == "__main__":
    raise SystemExit(main())
