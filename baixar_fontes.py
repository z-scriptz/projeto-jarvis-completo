#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# baixar_fontes.py — baixa as fontes CONDENSADAS das capas de carrossel.
#
# ⚠️ NÃO PRECISA BAIXAR NO WINDOWS E SUBIR PRA VPS. A pergunta do Dre (22/08)
# foi "como vamos pegar as fontes? eu baixo pelo windows?" — não: elas moram
# num repositório público do Google e vêm direto pra VPS com um comando.
#
# LICENÇA — e isto importa porque a gente monetiza:
# Anton e Archivo Black são **SIL Open Font License 1.1**. A OFL permite uso
# comercial, inclusive embutir a fonte em imagem publicada. A única obrigação
# prática é não vender a FONTE em si e manter o aviso de licença junto — por
# isso o script baixa o `OFL.txt` de cada uma para `assets/brand/licencas/`,
# em vez de só pegar o `.ttf` e seguir a vida.
#
# POR QUE ESTAS DUAS:
#   Anton         a mais próxima das referências que o Dre mandou — condensada,
#                 pesadíssima, feita pra manchete. É a primeira da fila.
#   Archivo Black larga e pesada; serve de segunda opção quando a Anton fica
#                 apertada demais num nicho.
# O `carrossel_render.fonte_titulo()` procura nesta ordem e usa a primeira que
# achar; sem nenhuma, cai na Montserrat da marca e o carrossel continua saindo.
#
# USO (de dentro de ~/jarvis):
#   python3 baixar_fontes.py            # baixa o que faltar
#   python3 baixar_fontes.py --listar   # só diz o que já tem

import sys
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DESTINO = BASE_DIR / "assets" / "brand"
LICENCAS = DESTINO / "licencas"

_RAW = "https://raw.githubusercontent.com/google/fonts/main/ofl"

FONTES = [
    ("Anton-Regular.ttf", f"{_RAW}/anton/Anton-Regular.ttf",
     f"{_RAW}/anton/OFL.txt", "Anton — condensada pesada, a das referências"),
    ("ArchivoBlack-Regular.ttf", f"{_RAW}/archivoblack/ArchivoBlack-Regular.ttf",
     f"{_RAW}/archivoblack/OFL.txt", "Archivo Black — larga e pesada, 2ª opção"),
]

# ⚠️ 20 KB de piso: um 404 do GitHub vem como página HTML de ~400 bytes, e
# gravar isso com nome .ttf deixaria a fonte "instalada" e quebrada — o Pillow
# só reclamaria na hora de renderizar, longe daqui.
TAM_MINIMO = 20 * 1024


def _baixar(url: str, destino: Path, minimo: int = 0) -> str:
    """Grava e devolve "" se OK, ou a mensagem de erro."""
    try:
        import requests
    except Exception:
        return "a lib 'requests' não está instalada (pip install requests)"
    try:
        r = requests.get(url, timeout=60,
                         headers={"User-Agent": "jarvis-fontes/1.0"})
    except Exception as e:
        return f"rede: {str(e)[:80]}"
    if r.status_code != 200:
        return f"HTTP {r.status_code}"
    if minimo and len(r.content) < minimo:
        return (f"veio só {len(r.content)} byte(s) — provavelmente uma página "
                f"de erro, não a fonte")
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(r.content)
    except Exception as e:
        return f"não gravei: {str(e)[:80]}"
    return ""


def _valida(arq: Path) -> tuple:
    """Abre a fonte de verdade. Devolve (estado, detalhe).

    estado: "ok" · "quebrada" · "nao_deu" (não foi possível checar)

    ⚠️ TRÊS ESTADOS, NÃO DOIS — e o bug que isto conserta foi meu, medido na
    VPS em 22/08. Eu tratava "não consegui validar" como "fonte inválida" e
    APAGAVA o arquivo. O Dre rodou com o python do sistema, que não tem Pillow
    (ele mora no `.venv`), e as duas fontes **baixaram certinho e foram
    apagadas em seguida**, com a mensagem `❌ No module named 'PIL'`.
    Ausência de prova não é prova de defeito. Sem Pillow, a fonte fica."""
    try:
        from PIL import ImageFont
    except Exception as e:
        return ("nao_deu", str(e)[:60])
    try:
        ImageFont.truetype(str(arq), 40)
        return ("ok", "")
    except Exception as e:
        return ("quebrada", str(e)[:80])


def main() -> int:
    p = argparse.ArgumentParser(description="Baixa as fontes das capas")
    p.add_argument("--listar", action="store_true", help="só mostra o estado")
    a = p.parse_args()

    print(f"📁 {DESTINO}\n")
    faltando = []
    for nome, url, ofl, desc in FONTES:
        arq = DESTINO / nome
        if arq.exists():
            estado, detalhe = _valida(arq)
            kb = arq.stat().st_size // 1024
            if estado == "quebrada":
                print(f"  ⚠️  {nome:<26} existe mas NÃO ABRE ({detalhe}) — rebaixando")
                faltando.append((nome, url, ofl, desc))
            elif estado == "nao_deu":
                print(f"  ✅ {nome:<26} {kb} KB · {desc}")
                print(f"      (sem Pillow aqui pra conferir — use .venv/bin/python)")
            else:
                print(f"  ✅ {nome:<26} {kb} KB · {desc}")
        else:
            print(f"  ⬜ {nome:<26} falta · {desc}")
            faltando.append((nome, url, ofl, desc))

    if a.listar:
        return 0
    if not faltando:
        print("\nNada a baixar — as capas já usam a condensada.")
        return 0

    print()
    erros = 0
    for nome, url, ofl, _ in faltando:
        arq = DESTINO / nome
        print(f"⬇️  {nome} ...", end=" ", flush=True)
        erro = _baixar(url, arq, TAM_MINIMO)
        aviso = ""
        if not erro:
            estado, detalhe = _valida(arq)
            if estado == "quebrada":
                # fonte que não abre é pior que ausente: a ausente cai na
                # Montserrat e o carrossel sai
                arq.unlink(missing_ok=True)
                erro = detalhe
            elif estado == "nao_deu":
                aviso = "  (não validei: sem Pillow neste python)"
        if erro:
            print(f"❌ {erro}")
            erros += 1
            continue
        print(f"OK ({arq.stat().st_size // 1024} KB){aviso}")
        # a licença acompanha a fonte — obrigação da OFL, e cabe num arquivo
        lic = LICENCAS / f"{arq.stem}-OFL.txt"
        if _baixar(ofl, lic):
            print(f"   ⚠️  não consegui trazer a licença de {nome} "
                  f"(a fonte funciona; a licença fica pendente)")

    if erros:
        print(f"\n⚠️  {erros} fonte(s) não vieram. As capas continuam saindo com "
              "a Montserrat — só não ficam com o peso das referências.")
        return 1
    print("\n✅ pronto. As capas de carrossel já saem com a condensada.")
    print("   Confira:  .venv/bin/python carrossel_render.py --exemplo tech")
    return 0


if __name__ == "__main__":
    sys.exit(main())
