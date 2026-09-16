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
import re
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


def _alerta_telegram(msg: str) -> bool:
    """Mesmo canal de admin dos outros alertas. Best-effort, nunca quebra."""
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = (os.environ.get("TELEGRAM_ALERT_CHAT_ID")
            or os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not tok or not chat:
        return False
    try:
        import requests
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=15,
                      json={"chat_id": chat, "text": msg, "parse_mode": "HTML"})
        return True
    except Exception:
        return False


_ARQ_ESTADO = None
_ESTADO_MEMORIA: dict = {}
_LEMBRETE_SEGUNDOS = 24 * 3600
# Acima disto, a fila parada deixa de ser "esperando a espera crescente" e
# passa a ser "ninguém está processando". O ciclo do daemon é bem mais curto.
LIMITE_FILA_PARADA = float(os.environ.get("ESCOPO_LIMITE_FILA", 2 * 3600))


def _arq_estado() -> Path:
    global _ARQ_ESTADO
    if _ARQ_ESTADO is None:
        base = Path(os.environ.get("ESCOPO_DADOS") or (BASE_DIR / "escopo_dados"))
        _ARQ_ESTADO = base / "camada.json"
    return _ARQ_ESTADO


def _ler_estado() -> dict:
    try:
        import json
        return json.loads(_arq_estado().read_text(encoding="utf-8"))
    except Exception:
        return dict(_ESTADO_MEMORIA)


def _gravar_estado(d: dict) -> None:
    global _ESTADO_MEMORIA
    _ESTADO_MEMORIA = dict(d)
    try:
        import json
        arq = _arq_estado()
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps(d), encoding="utf-8")
    except Exception:
        pass        # sem disco, a dedup vive só na memória do processo


def checar_camada(avisar: bool = True) -> tuple:
    """(ok, mensagem). Avisa no Telegram quando o estado MUDA.

    ⚠️ ISTO EXISTE POR CAUSA DE UM CASO REAL, e é requisito de produto, não
    conveniência: em 15/09/2026 a poda de fontes rodou com a consulta de
    vendas fora do ar e desabilitou 8 fontes sem dado — e a ESCOPO estava
    desligada por um `~/.ssh/config` faltando, então não existe recibo.

    📌 Camada de controle que depende de instalação manual não protege nada:
    na hora que importa, ela está desligada e ninguém sabe. Ligada por padrão
    e **barulhenta quando cai** é o comportamento correto.

    Anti-spam: avisa na virada de estado, e no máximo uma vez por dia
    enquanto continuar fora — daemon que reinicia não vira enxurrada."""
    ok = ativo()
    motivo = "" if ok else por_que_desligado()
    anterior = _ler_estado()
    era = anterior.get("ativo")
    ultimo = float(anterior.get("avisado_em") or 0)
    agora_ts = time.time()

    mudou = era is not None and bool(era) != ok
    primeira = era is None
    lembrete = (not ok) and (agora_ts - ultimo) > _LEMBRETE_SEGUNDOS

    if ok:
        msg = "🔒 ESCOPO ligada — ações de agente passam por contrato."
    else:
        msg = ("⚠️ <b>ESCOPO DESLIGADA</b>\n"
               f"motivo: <code>{motivo}</code>\n\n"
               "Enquanto isso, nenhuma ação de agente gera recibo — inclusive "
               "a poda de fontes.\n\n"
               "<code>/root/jarvis/.venv/bin/pip install -e /root/escopo-runtime</code>")

    # Na primeira vez só avisa se estiver FORA — "está tudo bem" não é notícia.
    deve = avisar and (mudou or lembrete or (primeira and not ok))
    if deve and _alerta_telegram(msg):
        _gravar_estado({"ativo": ok, "avisado_em": agora_ts})
    else:
        _gravar_estado({"ativo": ok, "avisado_em": ultimo})
    return ok, msg


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

    # ⚠️ FILA VELHA = NINGUÉM DRENANDO, e esse é o pior estado possível desta
    # camada: tudo fica PENDENTE, o que parece "ainda conferindo" e é
    # "ninguém vai conferir". Aconteceu de verdade em 16/09/2026 — a
    # integração agendava verificação e nada chamava processar_verificacoes().
    pendentes = esc.fila.pendentes()
    if pendentes:
        idade = esc.fila.idade_da_mais_antiga()
        marca = "⚠️" if idade > LIMITE_FILA_PARADA else "·"
        linhas.append(f"   {marca} {len(pendentes)} verificação(ões) na fila, "
                      f"a mais antiga há {idade / 60:.0f} min")
        if idade > LIMITE_FILA_PARADA:
            linhas.append("      ninguém está drenando a fila — o daemon "
                          "chama escopo_jarvis.processar_verificacoes() "
                          "a cada ciclo")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# O verificador real: os arquivos de perfil são a fonte de verdade
# ---------------------------------------------------------------------------

try:
    from escopo.verificacao import Verificador as _Base
except ImportError:                               # sem a lib, nada disso roda
    _Base = object

try:
    from escopo import impressao
except ImportError:
    import hashlib
    import json as _json

    def impressao(dados) -> str:
        """Cópia local, byte-a-byte igual à da biblioteca.

        ⚠️ Existe para o Jarvis conseguir carimbar procedência mesmo com a
        ESCOPO desinstalada — a mesma regra de sempre: a camada ausente não
        pode mudar o comportamento da aplicação."""
        return "sha256:" + hashlib.sha256(
            _json.dumps(dados, sort_keys=True, ensure_ascii=False,
                        separators=(",", ":")).encode("utf-8")).hexdigest()


class VerificadorPerfis(_Base):
    """Conta quantas linhas foram comentadas com a marca de poda de HOJE.

    ⚠️ Repara no que NÃO tem aqui: nenhum `try/except` convertendo falha de
    leitura em número. `read_text` levanta, a exceção sobe, e a classe base
    transforma em INVERIFICAVEL. É por construção que este verificador não
    consegue repetir o bug do `_vendas_por_fonte`."""

    nome = "jarvis.fontes"

    @staticmethod
    def _handle(linha: str) -> str:
        """O @handle de uma linha, podada ou não. '' se a linha não for perfil."""
        l = linha.strip().lstrip("#").strip()
        if not l:
            return ""
        return re.split(r"[\s#]", l)[0].lstrip("@").lower()

    def _consultar(self, contexto: dict) -> dict:
        """⚠️ CONFERE OS ALVOS DESTA AÇÃO, não o total de podas do dia.

        A primeira versão contava quantas linhas tinham a marca de hoje e
        comparava com a quantidade da intenção. Parece a mesma coisa e não é:

            10h  poda 5 fontes com sucesso       → 5 marcas de hoje
            11h  a consulta cai e a poda RECUSA  → intenção com 0 alvos
                 o contador global diz 5, a espera diz 0  →  FALHOU

        Uma recusa que não encostou em nada seria reportada como ação que
        falhou. **Contador global usado como asserção por ação** é medição que
        parece certa e responde outra pergunta."""
        marca = f"{MARCA_PODA} {time.strftime('%Y-%m-%d')}:"
        alvos = [str(a).lstrip("@").lower()
                 for a in (contexto.get("alvos") or [])]
        podados_hoje, lidos = set(), 0
        for arq in (TIKTOK_PERFIS, IG_PERFIS):
            if not arq.exists():
                continue                          # arquivo ausente é normal
            texto = arq.read_text(encoding="utf-8")   # deixa a exceção subir
            lidos += 1
            for linha in texto.splitlines():
                if marca in linha:
                    h = self._handle(linha)
                    if h:
                        podados_hoje.add(h)
        if lidos == 0:
            raise PerfisIlegiveis(
                f"nenhum arquivo de perfil encontrado em {BASE_DIR} "
                f"({TIKTOK_PERFIS.name}, {IG_PERFIS.name}) — "
                f"sem fonte de verdade não há o que provar")
        faltando = sorted(set(alvos) - podados_hoje)
        return {"alvos": len(alvos),
                "confirmados": len(alvos) - len(faltando),
                "faltando": faltando[:20],
                "executar": bool(contexto.get("executar", True)),
                "arquivos_lidos": lidos}

    def _conferir(self, observado: dict, espera: dict) -> tuple:
        """⚠️ DRY-RUN MUDA O QUE SE ESPERA, NÃO O QUE SE VERIFICA.

        `--podar-fontes` sem executar não escreve nada nos arquivos. Cobrar
        confirmação nesse caso daria FALHOU numa execução que se comportou
        perfeitamente — e alarme falso treina gente a ignorar alarme."""
        alvos = observado["alvos"]
        confirmados = observado["confirmados"]

        if not observado.get("executar", True):
            if confirmados == 0:
                return True, (f"dry-run: nenhum dos {alvos} alvo(s) foi "
                              f"escrito nos arquivos, como esperado")
            return False, (f"dry-run NÃO deveria alterar nada, mas "
                           f"{confirmados} alvo(s) aparecem podados hoje")

        if alvos == 0:
            # Ação sem alvo — recusa, ou nada a fazer. Verificar isso não é
            # perda de tempo: prova que a recusa foi limpa, que nada vazou.
            return True, "nenhum alvo declarado — nada aconteceu, como devia"

        if confirmados != alvos:
            return False, (f"a intenção declarava {alvos} fonte(s), mas "
                           f"{alvos - confirmados} não aparece(m) comentada(s) "
                           f"hoje: {', '.join(observado['faltando']) or '—'}")
        return True, (f"{confirmados} de {alvos} fonte(s) confirmada(s) "
                      f"comentada(s) em {observado['arquivos_lidos']} "
                      f"arquivo(s) de perfil")


if __name__ == "__main__":
    print(resumo())
