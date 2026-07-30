#!/usr/bin/env python3
"""Gera src/fontes-embutidas.js a partir da família Source.

Baixa as fontes (se faltarem), reduz cada uma aos caracteres que os slides usam
e grava o resultado em base64 num módulo JS. Assim o render não depende de fonte
instalada na máquina nem de requisição de rede.

Uso:
    pip install fonttools brotli
    python3 scripts/subset-fontes.py
"""

import base64
import io
import subprocess
import sys
from pathlib import Path

from fontTools import subset

RAIZ = Path(__file__).resolve().parent.parent
PASTA_FONTES = RAIZ / "public" / "fontes"
SAIDA = RAIZ / "src" / "fontes-embutidas.js"

BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl"
FONTES = [
    ("SourceSerif4.ttf", f"{BASE}/sourceserif4/SourceSerif4%5Bopsz,wght%5D.ttf", "serif"),
    ("SourceSans3.ttf", f"{BASE}/sourcesans3/SourceSans3%5Bwght%5D.ttf", "sans"),
    ("SourceCodePro.ttf", f"{BASE}/sourcecodepro/SourceCodePro%5Bwght%5D.ttf", "mono"),
]

# Latino básico + acentos do português + a pontuação que aparece nos slides.
CARACTERES = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    "ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ"
    " .,;:!?¡¿'\"“”‘’()[]{}—–-_/\\|@#$%&*+=<>°ºª→←↑↓•·…"
)


def baixar_se_faltar(nome: str, url: str) -> Path:
    destino = PASTA_FONTES / nome
    if destino.exists():
        return destino
    PASTA_FONTES.mkdir(parents=True, exist_ok=True)
    print(f"baixando {nome}...")
    subprocess.run(["curl", "-sSfL", "-o", str(destino), url], check=True)
    return destino


def subsetar(caminho: Path) -> bytes:
    opcoes = subset.Options()
    opcoes.flavor = "woff2"
    opcoes.layout_features = ["*"]  # mantém kerning e ligaduras
    opcoes.notdef_outline = True
    fonte = subset.load_font(str(caminho), opcoes)
    reduzir = subset.Subsetter(options=opcoes)
    reduzir.populate(unicodes=[ord(c) for c in sorted(set(CARACTERES))])
    reduzir.subset(fonte)
    buffer = io.BytesIO()
    subset.save_font(fonte, buffer, opcoes)
    return buffer.getvalue()


def main() -> int:
    partes = []
    for nome, url, familia in FONTES:
        caminho = baixar_se_faltar(nome, url)
        dados = subsetar(caminho)
        antes = caminho.stat().st_size // 1024
        print(f"{nome}: {antes} KB -> {len(dados) // 1024} KB woff2")
        partes.append((familia, base64.b64encode(dados).decode()))

    with SAIDA.open("w", encoding="utf-8") as arquivo:
        arquivo.write("// GERADO AUTOMATICAMENTE por scripts/subset-fontes.py — não editar a mão.\n")
        arquivo.write("// Família Source (SIL OFL 1.1), subsetada para latino + acentos do português\n")
        arquivo.write("// e embutida em base64: o render não depende de fonte do sistema nem de rede.\n\n")
        for familia, base64_dados in partes:
            arquivo.write(f"export const {familia} = '{base64_dados}';\n\n")

    print(f"{SAIDA.relative_to(RAIZ)} gerado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
