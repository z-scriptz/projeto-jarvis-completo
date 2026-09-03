#!/usr/bin/env python3
# layout_v2.py -- põe o .env da VPS de acordo com o layout novo (02/09/2026).
#
# POR QUE ESTE ARQUIVO EXISTE
# ───────────────────────────
# Mudar o código NÃO muda o vídeo. Todo knob de geometria é lido assim:
#
#     LOGO_Y = int(os.environ.get("LOGO_Y", 168))
#
# e o `.env` da VPS entra no ambiente pelo systemd. Se `LOGO_Y=112` estiver lá,
# o 176 do código é letra morta. Isso já aconteceu neste projeto: o `SELO_DX`
# ficou duas rodadas sendo ajustado no código enquanto o `.env` mandava outro
# valor, e o render.py tem o parágrafo inteiro registrando o episódio.
#
# São 16 chaves envolvidas na mudança de layout — nove pra definir e sete pra
# REMOVER. Remover importa tanto quanto definir: várias delas existem no .env
# com valores calibrados pro layout antigo e, se ficarem, travam justamente a
# parte que passou a ser derivada (a coluna do texto, o tamanho do nome).
#
# ⚠️ A CHAVE MAIS PERIGOSA É `TOPSHOP_BG`. Se ela estiver fixa no .env, TODAS
# as 6 contas renderizam com a mesma cor e a paleta por nicho fica invisível —
# o trabalho inteiro não aparece, sem nenhum erro em lugar nenhum.
#
# USO (na VPS, dentro de ~/jarvis):
#   .venv/bin/python layout_v2.py              # só MOSTRA o que mudaria
#   .venv/bin/python layout_v2.py --aplicar    # escreve no .env (faz backup)
#
# Sem --aplicar ele não toca em nada. O backup vai pra .env.bak_layout_v2.

import os
import shutil
import sys
from pathlib import Path

ENV = Path(__file__).resolve().parent / ".env"

REMOVER = "«remover»"

# (chave, valor novo, por quê)
PLANO = [
    # ── o que passa a valer ──────────────────────────────────────────────────
    ("VIDEO_W_FRAC", "0.90",
     "vídeo 972px de largura (era 885) — 'aumentar o vídeo nas bordas'"),
    ("VIDEO_Y", "500",
     "vídeo de y=500 a y=1796 (era 470→1651) — 'abaixar + o vídeo'"),
    ("VIDEO_RAIO", "28",
     "cantos levemente arredondados, como nos dois perfis de referência"),
    ("LOGO_Y", "168",
     "cabeçalho a 8,8% do topo (era 5,8%) — 'abaixar + o header com a logo'"),
    ("LOGO_TAM", "140",
     "logo 140px (era 120) — 'aumentar + o logo'"),
    ("HK_FONT", "60",
     "gancho maior (era 48) — 'algo grande'"),
    ("HK_ALT_LINHA", "76",
     "entrelinha acompanhando a fonte (era 62)"),
    ("HOOK_PESO", "Light",
     "Montserrat Light no gancho. Troque pra Regular se ficar fino demais"),
    ("CTA_ATIVO", "0",
     "sem 'COMENTE QUERO' queimado no vídeo — o pedido vai na legenda"),

    # ── o que PRECISA sair ───────────────────────────────────────────────────
    ("TOPSHOP_BG", REMOVER,
     "⚠️ CRÍTICA: fixa, ela achata as 6 contas numa cor só e ANULA a paleta"),
    ("FORCE_BG", REMOVER,
     "⚠️ CRÍTICA: é ferramenta de teste e ganha até do BG_<NICHO>"),

    # ⚠️ O BURACO DE 02/09, ACHADO EM 03/09 ─────────────────────────────────
    # Este plano removia TOPSHOP_BG e FORCE_BG e PARAVA AÍ. Mas o render.py:503
    # lê `BG_` + nicho.upper() com prioridade ACIMA da paleta:
    #
    #     forcado = (FORCE_BG or BG_<NICHO> or TOPSHOP_BG)
    #
    # Ou seja: um `BG_TECH` esquecido no .env continuava mandando, e SÓ naquele
    # nicho — que é exatamente o sintoma que o Dre relatou ("a cor deles também
    # continuam erradas", em tech e moda, com as outras 4 certas). O
    # shared/paleta.py:118 até cita `BG_TECH` como chave que existe na VPS.
    #
    # Uma chave por nicho, explícita: o `_FUNDOS` do paleta.py tem seis, e
    # gerar a lista por loop economizaria seis linhas ao custo de esconder o
    # que o script mexe no .env. Aqui o explícito vale mais.
    ("BG_GERAL", REMOVER, "override por nicho — ganha da paleta (⚠️ o buraco)"),
    ("BG_MODA", REMOVER, "idem — suspeito nº 1 do fundo errado no @topshopmoda_"),
    ("BG_BELEZA", REMOVER, "idem"),
    ("BG_CASA", REMOVER, "idem"),
    ("BG_TECH", REMOVER, "idem — suspeito nº 1 do fundo errado no @topshoptech_"),
    ("BG_PET", REMOVER, "idem"),
    ("HOOK_FONTE", REMOVER,
     "aponta pra Liberation e ganharia da Montserrat"),
    ("HOOK_FONTE_PRETO", REMOVER,
     "idem, no caminho do fundo escuro (tech)"),
    ("LOGO_X", REMOVER,
     "passa a ser derivado da borda do vídeo — texto e mídia na MESMA coluna"),
    ("HK_MARGEM", REMOVER,
     "idem: 89 fixo deixaria o gancho 35px pra dentro do vídeo novo"),
    ("HK_MARGEM_DIR", REMOVER,
     "idem, do lado direito — a coluna precisa ser simétrica"),
]

# ── O QUE EU DELIBERADAMENTE NÃO MEXO ────────────────────────────────────────
# NOME_FONT (52), HANDLE_FONT (42), TEXTO_DX (8) e SELO_DX (28) ficam como
# estão. Foram calibrados no olho pelo Dre — o SELO_DX tem um parágrafo inteiro
# no render.py sobre a diferença entre "encostado" e "com respiro", que é
# escolha de marca, não de precisão.
#
# Cheguei a listar os três pra remoção. A primeira prévia mostrou por que era
# errado: com o nome saltando de 52 pra 65, o selo verificado foi parar EM CIMA
# do "@topshopbeauty._". O pedido era "aumentar + o logo", não "aumentar o
# nome" — alargar o escopo sozinho criou um defeito que não existia.

# Chaves do CTA: só viram letra morta, não atrapalham. Ficam de fora do plano
# de propósito — remover o que é inofensivo aumenta a chance de alguém rodar
# isto com pressa e apagar algo que importava.


def _chave_da(linha: str) -> str:
    l = linha.strip()
    if not l or l.startswith("#") or "=" not in l:
        return ""
    if l.lower().startswith("export "):
        l = l[7:]
    return l.partition("=")[0].strip()


def _valor_ativo(linhas, chave):
    """O valor que VALE hoje: a PRIMEIRA ocorrência, porque é onde todo
    carregador do projeto para (`if chave not in os.environ`)."""
    for l in linhas:
        if _chave_da(l) == chave:
            return l.strip().partition("=")[2].strip().strip('"').strip("'")
    return None


def main() -> int:
    aplicar = "--aplicar" in sys.argv
    if not ENV.exists():
        print(f"[layout] não achei {ENV}.")
        print("[layout] rode de dentro de ~/jarvis na VPS. "
              "Aqui só dá pra ver o plano abaixo.\n")
        linhas = []
    else:
        linhas = ENV.read_text(encoding="utf-8").splitlines()

    mudar, ja_ok = [], []
    for chave, novo, motivo in PLANO:
        atual = _valor_ativo(linhas, chave)
        if novo is REMOVER:
            (mudar if atual is not None else ja_ok).append((chave, atual, novo, motivo))
        else:
            (ja_ok if atual == novo else mudar).append((chave, atual, novo, motivo))

    print(f"[layout] {len(mudar)} chave(s) a mexer · {len(ja_ok)} já em ordem\n")
    for chave, atual, novo, motivo in mudar:
        if novo is REMOVER:
            print(f"  ⛔ REMOVER  {chave:<16} (está: {atual!r})")
        else:
            print(f"  ✏️  {chave:<16} {atual!r} → {novo!r}")
        print(f"       {motivo}")
    if ja_ok:
        print(f"\n  ✔️  já em ordem: {', '.join(c for c, _, _, _ in ja_ok)}")

    if not mudar:
        print("\n[layout] nada a fazer.")
        return 0
    if not aplicar:
        print("\n[layout] nada foi alterado. Rode com --aplicar pra escrever.")
        return 0
    if not ENV.exists():
        print("\n[layout] sem .env, não há o que aplicar.")
        return 1

    shutil.copy2(ENV, ENV.with_suffix(".env.bak_layout_v2"))
    for chave, _atual, novo, _m in mudar:
        onde = [i for i, l in enumerate(linhas) if _chave_da(l) == chave]
        if novo is REMOVER:
            # comenta, não apaga: reversível, e o motivo fica no arquivo.
            for i in onde:
                linhas[i] = f"# {linhas[i].strip()}   # layout_v2: agora é derivado"
        elif onde:
            linhas[onde[0]] = f"{chave}={novo}"
            for i in onde[1:]:      # duplicata é letra morta; some junto
                linhas[i] = f"# {linhas[i].strip()}   # layout_v2: duplicata"
        else:
            linhas.append(f"{chave}={novo}")
    ENV.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"\n[layout] ✅ {len(mudar)} chave(s) aplicada(s). "
          f"Backup em {ENV.with_suffix('.env.bak_layout_v2').name}")
    print("[layout] confira com: .venv/bin/python env_set.py --ver")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
