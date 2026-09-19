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
PRONTO_DIR = BASE_DIR / "pronto_para_postar"

# A marca que `_podar_fontes()` escreve na linha comentada.
MARCA_PODA = "# PODADO CEO"

_escopo = None
_tentou = False
_motivo_off = ""


try:
    from escopo import SemEfeito
except Exception:       # noqa: BLE001 — a camada nunca derruba o Jarvis
    # ⚠️ SEM A BIBLIOTECA, ISTO PRECISA CONTINUAR SENDO UMA EXCEÇÃO DE VERDADE.
    # O `PodaSemEvidencia` herda daqui; se este nome virasse `None` ou sumisse,
    # o `ceo_agent` nem importaria. Fallback que quebra o import é pior que
    # biblioteca ausente.
    class SemEfeito(Exception):                      # type: ignore[no-redef]
        """Marcador local: a função foi chamada e de propósito não fez nada."""


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
        esc.registrar_verificador(VerificadorComentario())
        esc.registrar_verificador(VerificadorProducao())
        esc.registrar_verificador(VerificadorCarrossel())
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


def reconciliar(avisar: bool = True) -> dict:
    """Recoloca na fila o que o livro sabe que falta conferir.

    ⚠️ CHAMADA A CADA CICLO, ANTES DE DRENAR. `escopo_dados/fila.json` é um
    arquivo num diretório que já foi apagado à mão uma vez (16/09) enquanto o
    daemon rodava. Sem isto, a fila volta vazia e a ESCOPO passa a dizer "não
    há nada pendente" quando a verdade é "perdi a lista" — o defeito que este
    projeto inteiro persegue, no próprio projeto.

    📌 Em dia normal isto não faz nada e não custa nada: o livro e a fila
    concordam, o relatório vem com `recuperados: []` e ninguém é avisado."""
    esc = _construir()
    if esc is None:
        return {}
    try:
        rel = esc.reconciliar()
    except Exception as e:                        # noqa: BLE001 — proposital
        # Reconciliação é manutenção: falhar aqui não pode parar o ciclo.
        print(f"⚠️ escopo: reconciliar falhou: {type(e).__name__}: {e}")
        return {}

    n = len(rel.get("recuperados") or [])
    perdidas = len(rel.get("sem_plano") or [])
    if n:
        print(f"🔒 escopo: {n} verificação(ões) recuperada(s) do livro — a "
              f"fila tinha perdido")
    if avisar and n:
        _alerta_telegram(
            f"🔒 ESCOPO: {n} verificação(ões) pendente(s) foram recuperadas do "
            f"livro-razão porque a fila as tinha perdido.\n\n"
            f"A fila é uma projeção e foi reconstruída — nenhuma evidência se "
            f"perdeu. Mas o arquivo `escopo_dados/fila.json` sumiu ou voltou "
            f"atrás, e vale olhar por quê.")
    if perdidas:
        # ⚠️ ISSO NÃO SE RESOLVE SOZINHO e não pode virar rotina silenciosa:
        # são recibos gravados antes de o plano existir. O livro diz que estão
        # PENDENTES e não diz quem ia conferir — a verificação está perdida de
        # verdade. Dizer isso alto é melhor que fingir que a fila está limpa.
        print(f"⚠️ escopo: {perdidas} ação(ões) antiga(s) sem plano de "
              f"verificação no recibo — não dá para reconstruir, e elas "
              f"ficam PENDENTES para sempre")
    return rel


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
    acoes = [r for r in recibos if r.kind == "action"]
    integra, problemas = esc.integro()
    from collections import Counter
    decisoes = Counter(r.body["verdict"]["decision"] for r in acoes)
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
        hoje = time.strftime("%Y-%m-%d")
        marca = f"{MARCA_PODA} {hoje}:"
        # ⚠️ A MARCA DESTA EXECUÇÃO, e é ela que torna o Effect Binding
        # possível aqui. `podados_hoje` é o placar do DIA — usar isso como
        # "efeito desta ação" faria a poda da tarde reivindicar o que a da
        # manhã fez, e o diff acusaria `OVER_EFFECT` em cima de trabalho
        # legítimo de outra execução.
        run_id = str(contexto.get("run_id") or "")
        marca_run = f"{MARCA_PODA} {hoje} #{run_id}:" if run_id else None
        alvos = [str(a).lstrip("@").lower()
                 for a in (contexto.get("alvos") or [])]
        podados_hoje, podados_run, lidos = set(), set(), 0
        for arq in (TIKTOK_PERFIS, IG_PERFIS):
            if not arq.exists():
                continue                          # arquivo ausente é normal
            texto = arq.read_text(encoding="utf-8")   # deixa a exceção subir
            lidos += 1
            for linha in texto.splitlines():
                if marca_run and marca_run in linha:
                    h = self._handle(linha)
                    if h:
                        podados_run.add(h)
                # ⚠️ O placar do dia continua sendo coletado, mas SÓ para o
                # caminho legado do `_conferir`. Ele nunca alimenta o diff.
                if marca in linha or (marca_run and marca_run in linha):
                    h = self._handle(linha)
                    if h:
                        podados_hoje.add(h)
        if lidos == 0:
            raise PerfisIlegiveis(
                f"nenhum arquivo de perfil encontrado em {BASE_DIR} "
                f"({TIKTOK_PERFIS.name}, {IG_PERFIS.name}) — "
                f"sem fonte de verdade não há o que provar")
        # 📌 Com binding, a conferência passa a ser sobre ESTA execução. Sem
        # ele (recibo antigo, código antes do deploy), cai no placar do dia —
        # que é o comportamento de antes, preservado de propósito para a
        # transição não gerar FALHOU falso.
        vistos = podados_run if run_id else podados_hoje
        faltando = sorted(set(alvos) - vistos)
        return {"alvos": len(alvos),
                "confirmados": len(alvos) - len(faltando),
                "faltando": faltando[:20],
                "executar": bool(contexto.get("executar", True)),
                "arquivos_lidos": lidos,
                "run_id": run_id,
                # ⚠️ TUDO que esta execução marcou, não só o que foi pedido.
                # É aqui que o excesso aparece: se a poda tocou uma fonte que
                # não estava autorizada, ela está nesta lista e em nenhuma
                # outra.
                "podados_desta_execucao": sorted(podados_run)}

    def _efeito_observado(self, observado: dict, contexto: dict):
        """O que ESTA execução de fato podou, para comparar com o autorizado.

        ⚠️ SEM `run_id`, NÃO HÁ BINDING — e aí a resposta honesta é "não sei".

        Marca escrita antes deste selo existir não pode virar evidência da
        ação de hoje. Devolver o placar do dia aqui seria atribuir a esta
        execução o trabalho de outra: `MATCH` falso quando bate por acaso,
        `OVER_EFFECT` falso quando não bate. **Preferir UNKNOWN a inventar
        associação.**

        📌 Com `run_id`, a enumeração é honestamente `complete`: os arquivos
        de perfil foram lidos inteiros, e tudo que leva este selo está na
        lista. Não há página escondida."""
        if not observado.get("run_id"):
            # Enumeração vazia e declarada PARCIAL: o comparador devolve
            # DESCONHECIDA em vez de afirmar ausência. Ver `comparar_efeito`.
            return {"fontes": []}, "partial"
        return {"fontes": list(observado["podados_desta_execucao"])}, "complete"

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


class RespostaIlegivel(Exception):
    """Não deu para ler a resposta de volta na API do Meta."""


def _buscar_no_graph(resposta_id: str, token: str) -> dict:
    """GET simples no Graph. Separado para o teste poder trocar."""
    import urllib.parse
    import urllib.request
    url = ("https://graph.facebook.com/v21.0/" + urllib.parse.quote(resposta_id)
           + "?" + urllib.parse.urlencode({"fields": "id,text",
                                           "access_token": token}))
    with urllib.request.urlopen(url, timeout=20) as r:
        import json as _j
        return _j.loads(r.read().decode("utf-8"))


class VerificadorComentario(_Base):
    """A resposta apareceu mesmo no post, ou a API só disse que sim?

    ⚠️ O TOKEN É RESOLVIDO AQUI DENTRO, NUNCA VEM DO CONTEXTO.
    O contexto de verificação é gravado na fila em disco e no recibo. Uma
    credencial ali seria vazamento produzido pela própria camada que existe
    para tornar as coisas auditáveis. O contexto carrega só o id da resposta
    e a conta."""

    nome = "jarvis.comentario"

    def __init__(self, buscar=None):
        self.buscar = buscar or _buscar_no_graph

    def _consultar(self, contexto: dict) -> dict:
        rid = str(contexto.get("resposta_id") or "").strip()
        if not rid:
            # A API não devolveu id: não há o que ir ler. Isso não é "falhou",
            # é "não dá para conferir" — a distinção de sempre.
            raise RespostaIlegivel(
                "a API não devolveu id da resposta; não há o que verificar")
        token = (os.environ.get("FACEBOOK_PAGE_TOKEN", "")
                 or os.environ.get("META_ACCESS_TOKEN", "")).strip()
        if not token:
            raise RespostaIlegivel(
                "sem token no ambiente para reler a resposta no Graph")
        dados = self.buscar(rid, token)       # deixa a exceção subir
        return {"publicado": bool((dados or {}).get("id")),
                "id_lido": (dados or {}).get("id", ""),
                "id_esperado": rid}


class EsteiraIlegivel(Exception):
    """Não deu para conferir a esteira `pronto_para_postar/`.

    ⚠️ Mesmo motivo de sempre: pasta ausente, sem permissão, ou slug que não
    dá para calcular — nenhuma dessas coisas é evidência de que o vídeo não
    foi produzido. Devolver 0 aqui transformaria "não consegui olhar" em
    "não produziu nada"."""


class VerificadorProducao(_Base):
    """Os pacotes entraram MESMO na esteira, ou só o contador subiu?

    ⚠️ CONFERE ALVO POR ALVO, e nomeia quem faltou. Contar quantas pastas
    existem em `pronto_para_postar/` e comparar com o pedido seria contador
    global usado como asserção por ação — o falso positivo que o
    `VerificadorPerfis` já tomou uma vez: uma rodada anterior bem-sucedida
    deixa pastas lá, e elas não são desta ação.

    📌 A FONTE DE VERDADE É O DISCO, não o retorno do `processar_produto()`.
    Ele devolver `status: video_gerado` é o agente dizendo que fez; o pacote
    estar em `pronto_para_postar/<slug>/video.mp4` é o mundo confirmando."""

    nome = "jarvis.producao"

    @staticmethod
    def _slug(nome: str) -> str:
        """O MESMO `_slugify` do renderizador — importado, nunca reescrito.

        ⚠️ E LEVANTA em vez de devolver "". Slug calculado por outra régua não
        acha pasta nenhuma, e o sintoma seria "não tinha vídeo na esteira" —
        indistinguível de a produção ter falhado. O `conferir_match` documenta
        esse risco e mesmo assim devolve ""; aqui não pode."""
        try:
            import produzir_tiktok as _PT
            slug = _PT.H._slugify(nome or "")
        except Exception as e:            # noqa: BLE001 — proposital
            raise EsteiraIlegivel(
                f"não consegui calcular o slug de {nome!r} com a régua do "
                f"renderizador ({type(e).__name__}: {str(e)[:80]}) — sem ela "
                f"qualquer busca na esteira acha nada e mente") from e
        if not slug:
            raise EsteiraIlegivel(
                f"a régua do renderizador devolveu slug vazio para {nome!r}")
        return slug

    def _contar(self, observado: dict, espera: dict):
        """⚠️ É ISTO QUE FAZ `2 de 4` VIRAR PARTIAL EM VEZ DE FAILED.

        📌 E O `incertos` APARECEU DEPOIS, vindo da realidade. A versão
        original dizia, com todas as letras, que aqui ele não existia: "a fonte
        é o disco local, ou o pacote está lá ou não está". Estava errado — o
        alvo sobre o qual o produtor não devolveu caminho é exatamente um
        incerto, e chamá-lo de falha foi o que encheu o livro de FAILED em
        17/09.

        ⚠️ O comentário antigo previa o caso certo no lugar errado: dizia que
        num verificador de Stripe o `pending` seria o incerto. Era verdade — e
        também havia um aqui, mais perto, que eu não vi."""
        from escopo import Contagem
        return Contagem(
            pedidos=int(observado.get("pedidos") or 0),
            confirmados=int(observado.get("produzidos") or 0),
            falhos=len(observado.get("faltando") or []),
            incertos=len(observado.get("sem_referencia") or []),
        )

    def _consultar(self, contexto: dict) -> dict:
        """⚠️ CONFERE O CAMINHO QUE O PRODUTOR DISSE TER CRIADO.

        📌 DEFEITO PEGO EM PRODUÇÃO (17/09): a primeira versão recalculava
        `slug(nome_do_produto)` para adivinhar a pasta. Régua ligeiramente
        diferente da de quem criou → pasta não encontrada → **um vídeo que
        EXISTE vira FAILED no livro-razão**, permanentemente.

        ⚠️ É UMA FORMA NOVA DE INVENTAR CERTEZA, e o projeto ainda não a tinha
        enfrentado: *consultar a fonte certa sobre a entidade errada*. O disco
        respondeu a verdade — sobre uma pasta que não era a do efeito.

        A regra que sai daí: **prove o efeito da MESMA entidade que a ação
        criou; não tente redescobri-la depois.**"""
        alvos = [str(a) for a in (contexto.get("alvos") or [])]
        artefatos = dict(contexto.get("artefatos") or {})
        # ⚠️ O QUE O PRODUTOR DECLAROU TER FALHADO.
        #
        # Isto é o agente afirmando — e normalmente a ESCOPO não aceita
        # afirmação do agente. A exceção é para o lado do FRACASSO: quem diz
        # "tentei e não consegui" está se incriminando, não se elogiando, e
        # não há incentivo para mentir nessa direção. Tratar isso como
        # "não sei" jogaria fora informação que o produtor tinha.
        #
        # 📌 Mas fica REGISTRADO como declarado, não como conferido — porque
        # sem caminho não houve conferência nenhuma.
        declarou_falha = {str(x) for x in (contexto.get("falharam") or [])}
        if not PRONTO_DIR.exists():
            # ⚠️ Pasta ausente NÃO é "produziu zero". Pode ser volume
            # desmontado, deploy no lugar errado, permissão.
            raise EsteiraIlegivel(
                f"a esteira {PRONTO_DIR} não existe — não dá para conferir se "
                f"os {len(alvos)} pacote(s) entraram")
        confirmados, faltando, sem_referencia = [], [], []
        for nome in alvos:
            caminho = str(artefatos.get(nome) or "").strip()
            if not caminho:
                if nome in declarou_falha:
                    # O produtor sabe que este não saiu, e disse.
                    faltando.append(nome)
                else:
                    # ⚠️ INCERTO, NÃO FALHA. Ninguém disse onde está nem que
                    # falhou. Adivinhar a pasta aqui foi exatamente o defeito
                    # que este bloco conserta.
                    sem_referencia.append(nome)
                continue
            pasta = Path(caminho)
            if not pasta.is_absolute():
                pasta = BASE_DIR / pasta
            alvo = pasta / "video.mp4" if pasta.suffix == "" else pasta
            (confirmados if alvo.exists() else faltando).append(nome)
        return {
            "produzidos": len(confirmados),
            "pedidos": len(alvos),
            # ⚠️ NOMEAR QUEM FALTOU é o que faz o recibo servir para alguma
            # coisa. "2 de 4" manda alguém procurar; "faltou o produto X"
            # manda alguém consertar.
            "faltando": sorted(faltando),
            "confirmados": sorted(confirmados),
            "sem_referencia": sorted(sem_referencia),
            # ⚠️ Quais dos `faltando` são declaração do produtor e não
            # conferência no disco. Quem audita precisa saber a diferença.
            "falha_declarada": sorted(declarou_falha & set(faltando)),
        }


def _buscar_midia(media_id: str, token: str) -> dict:
    """GET de uma mídia no Graph. Separado para o teste poder trocar."""
    import urllib.parse
    import urllib.request
    url = ("https://graph.facebook.com/v21.0/" + urllib.parse.quote(media_id)
           + "?" + urllib.parse.urlencode(
               {"fields": "id,permalink,media_type", "access_token": token}))
    with urllib.request.urlopen(url, timeout=20) as r:
        import json as _j
        return _j.loads(r.read().decode("utf-8"))


class GraphIndisponivel(Exception):
    """Não deu para perguntar à Meta se o post existe.

    ⚠️ Sem token, rede fora, 500 da Meta — nenhuma dessas coisas é evidência de
    que o carrossel não foi publicado. Devolver "não achei" aqui transformaria
    "não consegui olhar" em "não está no ar", e alguém republicaria em seis
    contas reais."""


class VerificadorCarrossel(_Base):
    """O carrossel está no ar, ou a API só disse que sim?

    ⚠️ ESTE É O VERIFICADOR QUE MAIS SE PARECE COM O PRODUTO. O agendador
    decide pelo `r.get("ok")` — que é o agente afirmando. O que prova é o
    `media_id` existir no Graph da Meta, que é a fonte de verdade e é pública:
    o post está lá para as pessoas, ou não está.

    ⚠️ E CONFERE PELO `media_id`, NUNCA PELA URL. Quando `_buscar_permalink`
    falha, o `meta_uploader` fabrica `instagram.com/p/{media_id}` como
    fallback — uma URL que parece permalink e nunca foi confirmada. Verificar
    contra ela seria conferir a afirmação contra ela mesma.

    📌 O TOKEN É RESOLVIDO AQUI DENTRO, nunca vem do contexto: o contexto vai
    para o disco, na fila e no recibo."""

    nome = "jarvis.carrossel"

    def __init__(self, buscar=None):
        self.buscar = buscar or _buscar_midia

    def _consultar(self, contexto: dict) -> dict:
        alvos = [str(a) for a in (contexto.get("alvos") or [])]
        midias = dict(contexto.get("midias") or {})
        if contexto.get("dry_run"):
            # ⚠️ Em dry-run nada foi publicado, e isso é o resultado CERTO —
            # mas não há o que conferir no Graph. INVERIFICAVEL é honesto;
            # dizer VERIFIED seria afirmar sobre um post que não existe.
            raise GraphIndisponivel(
                "dry-run: nada foi publicado, não há mídia para conferir")
        token = (os.environ.get("FACEBOOK_PAGE_TOKEN", "")
                 or os.environ.get("META_ACCESS_TOKEN", "")).strip()
        if not token:
            raise GraphIndisponivel(
                "sem token no ambiente para perguntar à Meta se os posts "
                "estão no ar")

        no_ar, sem_midia, nao_deu = [], [], {}
        for conta in alvos:
            mid = str(midias.get(conta) or "").strip()
            if not mid:
                # ⚠️ Sem `media_id`, ou a publicação falhou (e o agendador já
                # sabe disso) ou o uploader não devolveu o id. Nos DOIS casos
                # não há post confirmado — vai para `sem_midia`, e quem separa
                # falha de incerteza é o `_contar` lá embaixo.
                sem_midia.append(conta)
                continue
            try:
                dados = self.buscar(mid, token)
            except Exception as e:      # noqa: BLE001 — proposital
                # ⚠️ A CONSULTA FALHOU PARA ESTA CONTA. Isso NÃO é "o post não
                # está no ar" — é "não consegui olhar". As outras contas
                # continuam sendo conferidas: uma conta cega não pode apagar a
                # evidência das cinco que responderam.
                nao_deu[conta] = f"{type(e).__name__}: {str(e)[:80]}"
                continue
            if str((dados or {}).get("id") or "") == mid:
                no_ar.append(conta)
            else:
                sem_midia.append(conta)
        return {"no_ar": sorted(no_ar), "sem_midia": sorted(sem_midia),
                "nao_deu": nao_deu, "pedidos": len(alvos)}

    def _contar(self, observado: dict, espera: dict):
        """⚠️ TRÊS DESTINOS, E O TERCEIRO É O QUE IMPORTA.

        `nao_deu` são as contas que o Graph não respondeu. Somá-las a
        `sem_midia` daria um número redondo e mentiroso: uma conta que não
        respondeu não é uma conta cujo post não saiu."""
        from escopo import Contagem
        return Contagem(
            pedidos=int(observado.get("pedidos") or 0),
            confirmados=len(observado.get("no_ar") or []),
            falhos=len(observado.get("sem_midia") or []),
            incertos=len(observado.get("nao_deu") or {}),
        )


def maturidade(agente: str = "jarvis.ceo", acao: str = "source.disable") -> str:
    """Esta intenção já conquistou o direito de bloquear?

    📌 Troca "deixa mais uns dias em observe" — que é sentimento e nunca
    acaba — por um número que responde sozinho."""
    esc = _construir()
    if esc is None:
        return f"🔒 escopo: DESLIGADO ({_motivo_off})"
    try:
        from escopo import prontidao, relatorio
    except ImportError as e:
        return f"🔒 escopo: sem maturidade nesta versão da lib ({e})"
    return relatorio(prontidao(esc.livro, agente, acao))


if __name__ == "__main__":
    import sys
    print(resumo())
    if "--maturidade" in sys.argv:
        print()
        print(maturidade())
