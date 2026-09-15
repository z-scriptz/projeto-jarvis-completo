#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""escopo_jarvis.py -- liga o Jarvis à camada de controle ESCOPO.

    from escopo_jarvis import guarda

    @guarda(agente="jarvis.ceo", acao="source.disable", alvos=...)
    def _podar_fontes(fontes, executar): ...

⚠️ TODO O RISCO DA INTEGRAÇÃO ESTÁ CONCENTRADO NESTE ARQUIVO, de propósito.

O `ceo_agent.py` ganha duas linhas e nada mais. Se a ESCOPO não estiver
instalada, se a política estiver torta, se o diretório de dados não existir —
`guarda` vira um decorador que não faz nada e o Jarvis roda exatamente como
rodava. **Camada de controle que derruba a aplicação que ela deveria proteger
é pior que camada de controle nenhuma.**

📌 E o conserto que continua sendo do Jarvis: `_vendas_por_fonte()` precisa
distinguir "consultei, 0 vendas" de "não consegui consultar". A ESCOPO não
conserta o bug — ela impede que ele chegue longe, e prova depois que o
resultado não foi comprovado. As duas coisas são necessárias.

Ligar/desligar:
    ESCOPO_ATIVO=0     desliga por completo (padrão: ligado)
    ESCOPO_DADOS       onde gravar recibos (padrão: ./escopo_dados)
    ESCOPO_POLITICAS   onde estão os contratos (padrão: ./politicas)
"""
from __future__ import annotations

import functools
import os
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TIKTOK_PERFIS = BASE_DIR / "tiktok_perfis.txt"
IG_PERFIS = BASE_DIR / "instagram_perfis.txt"

# A marca que `_podar_fontes()` escreve na linha comentada.
MARCA_PODA = "# PODADO CEO"

_escopo = None
_tentou = False
_motivo_off = ""


class PerfisIlegiveis(Exception):
    """Não deu para ler os arquivos de perfil para conferir a poda.

    ⚠️ Existe como exceção e não como "devolve 0" por um motivo que é a tese
    inteira do produto: retorno vazio se parece com resultado. Exceção não se
    parece com nada — quem chama é obrigado a decidir o que fazer, e a ESCOPO
    decide por INVERIFICAVEL."""


def _construir():
    """Monta o Escopo uma vez. Qualquer falha desliga a camada, sem barulho."""
    global _escopo, _tentou, _motivo_off
    if _tentou:
        return _escopo
    _tentou = True

    if os.environ.get("ESCOPO_ATIVO", "1").strip() in {"0", "false", "no"}:
        _motivo_off = "desligado por ESCOPO_ATIVO"
        return None
    try:
        from escopo import Escopo
    except ImportError as e:
        _motivo_off = (f"biblioteca não instalada ({e}) — "
                       f"pip install -e /root/escopo-runtime")
        return None
    try:
        pol = Path(os.environ.get("ESCOPO_POLITICAS") or (BASE_DIR / "politicas"))
        dados = Path(os.environ.get("ESCOPO_DADOS") or (BASE_DIR / "escopo_dados"))
        esc = Escopo(politicas=pol, dados=dados)
        esc.registrar_verificador(VerificadorPerfis())
        for aviso in esc.avisos:
            print(f"⚠️ escopo: {aviso}")
        _escopo = esc
    except Exception as e:                        # noqa: BLE001 — proposital
        _motivo_off = f"não carregou: {type(e).__name__}: {e}"
        _escopo = None
    return _escopo


def ativo() -> bool:
    return _construir() is not None


def por_que_desligado() -> str:
    _construir()
    return _motivo_off


def guarda(**kw):
    """Decorador tolerante. Sem ESCOPO, devolve a função intacta.

    ⚠️ A decisão de proteger ou não é tomada NO MOMENTO DA CHAMADA, não no
    import: o `ceo_agent` é importado por vários pontos do Jarvis e não dá
    para exigir que a camada esteja pronta em todos eles."""

    def decorador(fn):
        @functools.wraps(fn)
        def envolvida(*a, **k):
            esc = _construir()
            if esc is None:
                return fn(*a, **k)
            try:
                protegida = esc.guarda(**kw)(fn)
            except Exception as e:                # noqa: BLE001 — proposital
                # Falhou ANTES de executar qualquer coisa: seguro cair para o
                # original. (Depois de executar, a própria ESCOPO já garante
                # que não levanta — ver Escopo._escriturar.)
                print(f"⚠️ escopo: não consegui proteger {fn.__name__}: {e}")
                return fn(*a, **k)
            return protegida(*a, **k)

        return envolvida

    return decorador


def processar_verificacoes() -> list:
    """Uma passada na fila. Chamar do daemon, de tempos em tempos."""
    esc = _construir()
    return esc.processar_verificacoes() if esc else []


def resumo() -> str:
    """Estado da camada, para o `--status` e para olhar de vez em quando."""
    esc = _construir()
    if esc is None:
        return f"🔒 escopo: DESLIGADO ({_motivo_off})"
    recibos = esc.livro.ler()
    acoes = [r for r in recibos if r.tipo == "acao"]
    integra, problemas = esc.integro()
    from collections import Counter
    decisoes = Counter(r.corpo["veredito"]["decisao"] for r in acoes)
    estados = Counter(esc.estado(r.hash).value for r in acoes)
    linhas = [
        f"🔒 escopo: {len(acoes)} ação(ões) registrada(s)",
        f"   decisão      " + " · ".join(f"{k} {v}" for k, v in decisoes.items()),
        f"   verificação  " + " · ".join(f"{k} {v}" for k, v in estados.items()),
        f"   cadeia       " + ("✅ íntegra" if integra
                               else "❌ " + "; ".join(problemas)),
    ]
    if esc.falhas_de_escrituracao:
        linhas.append(f"   ⚠️ {len(esc.falhas_de_escrituracao)} recibo(s) "
                      f"perdido(s) por falha de escrita")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# O verificador real: os arquivos de perfil são a fonte de verdade
# ---------------------------------------------------------------------------

try:
    from escopo.verificacao import Verificador as _Base
except ImportError:                               # sem a lib, nada disso roda
    _Base = object


class VerificadorPerfis(_Base):
    """Conta quantas linhas foram comentadas com a marca de poda de HOJE.

    ⚠️ Repara no que NÃO tem aqui: nenhum `try/except` convertendo falha de
    leitura em número. `read_text` levanta, a exceção sobe, e a classe base
    transforma em INVERIFICAVEL. É por construção que este verificador não
    consegue repetir o bug do `_vendas_por_fonte`."""

    nome = "jarvis.fontes"

    def _consultar(self, contexto: dict) -> dict:
        marca = f"{MARCA_PODA} {time.strftime('%Y-%m-%d')}:"
        achados, lidos = 0, 0
        for arq in (TIKTOK_PERFIS, IG_PERFIS):
            if not arq.exists():
                continue                          # arquivo ausente é normal
            texto = arq.read_text(encoding="utf-8")   # deixa a exceção subir
            lidos += 1
            achados += sum(1 for l in texto.splitlines() if marca in l)
        if lidos == 0:
            raise PerfisIlegiveis(
                f"nenhum arquivo de perfil encontrado em {BASE_DIR} "
                f"({TIKTOK_PERFIS.name}, {IG_PERFIS.name}) — "
                f"sem fonte de verdade não há o que provar")
        return {"desabilitadas": achados,
                "executar": bool(contexto.get("executar", True)),
                "arquivos_lidos": lidos}

    def _conferir(self, observado: dict, espera: dict) -> tuple:
        """⚠️ DRY-RUN MUDA O QUE SE ESPERA, NÃO O QUE SE VERIFICA.

        `--podar-fontes` sem executar não escreve nada nos arquivos. Comparar
        contra `$quantidade` nesse caso daria FALHOU numa execução que se
        comportou perfeitamente — e alarme falso treina gente a ignorar
        alarme."""
        esperado = espera.get("desabilitadas", 0)
        if not observado.get("executar", True):
            if observado["desabilitadas"] == 0:
                return True, (f"dry-run: nada foi escrito nos arquivos de "
                              f"perfil, como esperado (a intenção declarava "
                              f"{esperado})")
            return False, (f"dry-run NÃO deveria alterar nada, mas "
                           f"{observado['desabilitadas']} linha(s) aparecem "
                           f"podadas hoje")
        if observado["desabilitadas"] != esperado:
            return False, (f"a intenção declarava {esperado} fonte(s), mas os "
                           f"arquivos de perfil mostram "
                           f"{observado['desabilitadas']} podada(s) hoje")
        return True, (f"{esperado} fonte(s) confirmada(s) comentada(s) em "
                      f"{observado['arquivos_lidos']} arquivo(s) de perfil")


if __name__ == "__main__":
    print(resumo())
