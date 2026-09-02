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
    # ⚠️ AS DUAS DE BAIXO SÃO AS DO SISTEMA NOVO (slides_html), e são as que
    # importam agora: a serifada display + a geométrica de corpo são o par que
    # dá a cara editorial das referências. Anton e Archivo servem o desenho
    # antigo em PIL, que virou rede de segurança.
    ("Fraunces.ttf",
     f"{_RAW}/fraunces/Fraunces%5BSOFT,WONK,opsz,wght%5D.ttf",
     f"{_RAW}/fraunces/OFL.txt",
     "Fraunces — serifada display VARIÁVEL (peso e serifa vêm do CSS)"),
    ("Poppins-Medium.ttf", f"{_RAW}/poppins/Poppins-Medium.ttf",
     f"{_RAW}/poppins/OFL.txt", "Poppins — geométrica, o corpo dos slides"),
    # ── o gancho dos Reels (02/09): "montserrat light, poppins, ou algo grande"
    # A Poppins entra como PLANO B da Montserrat: se o fontTools não estiver no
    # venv da VPS, a instanciação lá embaixo falha e o gancho precisa ter onde
    # cair que não seja a Liberation (que é a cara ANTIGA do feed).
    ("Poppins-Light.ttf", f"{_RAW}/poppins/Poppins-Light.ttf",
     f"{_RAW}/poppins/OFL.txt", "Poppins Light — plano B do gancho"),
    ("Poppins-Regular.ttf", f"{_RAW}/poppins/Poppins-Regular.ttf",
     f"{_RAW}/poppins/OFL.txt", "Poppins Regular — plano B, peso alternativo"),
]

# ── FONTES QUE PRECISAM SER FATIADAS ─────────────────────────────────────────
#
# A Montserrat NÃO EXISTE MAIS EM ESTÁTICO no repositório do Google. Eu testei
# os dois caminhos antes de escrever isto:
#
#   ofl/montserrat/static/Montserrat-Light.ttf   → HTTP 404
#   ofl/montserrat/Montserrat[wght].ttf          → HTTP 200, 745 KB
#
# Só existe a VARIÁVEL, com um eixo `wght` de 100 a 900. E o resto do projeto
# procura arquivo estático por nome (`_fonte_montserrat` monta
# "Montserrat-{peso}.ttf"), então baixar a variável e torcer não resolve: o
# Pillow abriria a variável na instância padrão — peso 400 — e o "Light" que o
# Dre pediu sairia Regular, sem erro nenhum, sem ninguém perceber.
#
# Então a gente FATIA: fontTools.varLib.instancer congela o eixo num peso e
# grava um .ttf estático de verdade. Testado antes de subir — o arquivo sai com
# `name` "Montserrat Light", sem tabela fvar, e o Pillow lê ('Montserrat',
# 'Light'). O peso 700 só é gerado se ainda não houver um Montserrat-Bold.ttf
# na pasta: esse já está na VPS desde sempre e é o do cabeçalho.
INSTANCIAR = [
    ("Montserrat-Light.ttf", 300, "Montserrat Light — o gancho, como pedido"),
    ("Montserrat-Regular.ttf", 400, "Montserrat Regular — se o Light ficar fino"),
    ("Montserrat-Medium.ttf", 500, "Montserrat Medium — terceiro degrau"),
    ("Montserrat-Bold.ttf", 700, "Montserrat Bold — nome da conta no cabeçalho"),
]
MONT_VAR_URL = f"{_RAW}/montserrat/Montserrat%5Bwght%5D.ttf"
MONT_VAR_OFL = f"{_RAW}/montserrat/OFL.txt"


def _fatiar_montserrat() -> int:
    """Gera os pesos estáticos da Montserrat a partir da variável.
    Devolve quantos NÃO saíram (0 = tudo certo)."""
    faltam = [(n, w, d) for n, w, d in INSTANCIAR if not (DESTINO / n).exists()]
    if not faltam:
        print("  ✅ Montserrat — os 4 pesos já estão na pasta")
        return 0
    try:
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer
    except Exception as e:
        print(f"  ❌ Montserrat: fontTools não está neste python ({str(e)[:50]}).")
        print("     Rode com .venv/bin/python, ou: .venv/bin/pip install fonttools")
        print("     Sem isso o gancho cai na Poppins Light (HOOK_FAMILIA=Poppins).")
        return len(faltam)

    var = DESTINO / "_Montserrat-var.ttf"     # insumo, não é usado no render
    if not var.exists():
        print("⬇️  Montserrat[wght].ttf ...", end=" ", flush=True)
        erro = _baixar(MONT_VAR_URL, var, TAM_MINIMO)
        if erro:
            print(f"❌ {erro}")
            return len(faltam)
        print(f"OK ({var.stat().st_size // 1024} KB)")
        _baixar(MONT_VAR_OFL, LICENCAS / "Montserrat-OFL.txt")

    erros = 0
    for nome, peso, desc in faltam:
        print(f"✂️  {nome} (wght={peso}) ...", end=" ", flush=True)
        try:
            fonte = TTFont(str(var))
            est = instancer.instantiateVariableFont(
                fonte, {"wght": peso}, inplace=False, updateFontNames=True)
            est.save(str(DESTINO / nome))
        except Exception as e:
            print(f"❌ {str(e)[:80]}")
            erros += 1
            continue
        estado, detalhe = _valida(DESTINO / nome)
        if estado == "quebrada":
            (DESTINO / nome).unlink(missing_ok=True)
            print(f"❌ saiu e não abre ({detalhe})")
            erros += 1
            continue
        print(f"OK ({(DESTINO / nome).stat().st_size // 1024} KB) · {desc}")
    return erros

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

    for nome, _peso, desc in INSTANCIAR:
        arq = DESTINO / nome
        if arq.exists():
            print(f"  ✅ {nome:<26} {arq.stat().st_size // 1024} KB · {desc}")
        else:
            print(f"  ⬜ {nome:<26} falta (fatiar da variável) · {desc}")

    if a.listar:
        return 0

    print()
    erros_mont = _fatiar_montserrat()

    if not faltando:
        if erros_mont:
            return 1
        print("\nNada mais a baixar.")
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

    erros += erros_mont
    if erros:
        print(f"\n⚠️  {erros} fonte(s) não vieram. As capas continuam saindo com "
              "a Montserrat — só não ficam com o peso das referências.")
        return 1
    print("\n✅ pronto. Capas com a condensada, e o gancho dos Reels com a "
          "Montserrat Light.")
    print("   Confira:  .venv/bin/python previa_paleta.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
