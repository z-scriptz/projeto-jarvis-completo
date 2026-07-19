#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ceo_agent.py -- CEO IA (modo CONSELHEIRO). Lê os dados REAIS da máquina
# (posts_ledger = o que foi produzido/postado; nichos_quentes = o que VENDEU),
# calcula um retrato factual + o Jarvis Confidence Score, e usa o Gemini pra
# escrever um RELATÓRIO EXECUTIVO com PROPOSTAS numeradas. Advisory puro: ele
# PROPÕE, o Dre aprova/rejeita. Nada é aplicado sozinho.
#
# Uso (VPS):  cd ~/jarvis && .venv/bin/python ceo_agent.py [dias]   (padrão 30)
# Saída: imprime, salva shared/ceo/relatorio_<data>.md e manda resumo no Telegram.
import os
import re
import sys
import json
import time
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LEDGER = BASE_DIR / "shared" / "posts_ledger.jsonl"
NICHOS = BASE_DIR / "shared" / "nichos_quentes.json"
CEO_DIR = BASE_DIR / "shared" / "ceo"
TIKTOK_PERFIS = BASE_DIR / "tiktok_perfis.txt"       # fontes do TikTok (podáveis)
IG_PERFIS = BASE_DIR / "instagram_perfis.txt"        # fontes do Instagram (podáveis)


def _carregar_env():
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
        break


_carregar_env()


# ── Memória de LONGO PRAZO (best-effort; o CEO funciona sem ela) ────────────
# Dá ao CEO um "hipocampo": ele ESCREVE cada relatório/decisão, LÊ o próprio
# passado antes de aconselhar de novo, e CONFERE o resultado das decisões.
try:
    from agents.memory_agent import registrar_memoria, buscar_memorias
    _MEM_OK = True
except Exception:
    try:
        from memory_agent import registrar_memoria, buscar_memorias
        _MEM_OK = True
    except Exception:
        _MEM_OK = False
        def registrar_memoria(*a, **k):
            return {"sucesso": False}
        def buscar_memorias(*a, **k):
            return {"resultados": []}


def _brl(v):
    return ("R$ " + f"{float(v or 0):,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")


# ── Leitura dos dados ──────────────────────────────────────────────────────
def _ler_ledger(dias: int) -> list:
    if not LEDGER.exists():
        return []
    corte = time.time() - dias * 86400
    regs = []
    for linha in LEDGER.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            r = json.loads(linha)
            if r.get("ts", 0) >= corte:
                regs.append(r)
        except Exception:
            pass
    return regs


def _ler_nichos() -> dict:
    try:
        return json.loads(NICHOS.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Retrato factual (produção × venda) ─────────────────────────────────────
def _analisar(dias: int) -> dict:
    ledger = _ler_ledger(dias)
    nichos = _ler_nichos()

    # produção (o que foi postado) por categoria / plataforma / fonte / hora
    prod_cat = defaultdict(int)
    prod_plat = defaultdict(int)
    prod_fonte = defaultdict(int)
    prod_hora = defaultdict(int)
    prod_nicho = defaultdict(int)
    for r in ledger:
        prod_cat[(r.get("categoria") or "sem_categoria").lower()] += 1
        prod_plat[r.get("plataforma") or r.get("plataforma_afiliado") or "?"] += 1
        prod_fonte[r.get("fonte") or "?"] += 1
        prod_hora[r.get("hora", "?")] += 1
        prod_nicho[r.get("nicho") or "?"] += 1

    # vendas (o que converteu) — do nichos_quentes (só conversões de vídeo)
    vendas_cat = {c["categoria"].lower(): c for c in nichos.get("por_categoria", [])}
    top_produtos = nichos.get("top_produtos", [])[:8]
    comissao_video = nichos.get("comissao_video", 0)

    # cruzamento por categoria: produzido vs vendido
    cats = set(prod_cat) | set(vendas_cat)
    cruzamento = []
    for c in cats:
        v = vendas_cat.get(c, {})
        cruzamento.append({
            "categoria": c,
            "postados": prod_cat.get(c, 0),
            "vendas": v.get("vendas", 0),
            "comissao": round(v.get("comissao", 0), 2),
        })
    cruzamento.sort(key=lambda x: (x["comissao"], x["vendas"]), reverse=True)

    return {
        "dias": dias,
        "posts_periodo": len(ledger),
        "comissao_video": comissao_video,
        "vendas_video": sum(c.get("vendas", 0) for c in vendas_cat.values()),
        "cruzamento_categorias": cruzamento,
        "top_produtos": top_produtos,
        "producao_por_plataforma": dict(prod_plat),
        "producao_por_nicho": dict(prod_nicho),
        "producao_por_fonte": dict(prod_fonte),
        "producao_por_hora": dict(sorted(prod_hora.items(), key=lambda x: -x[1])[:6]),
        "nichos_gerado_em": nichos.get("gerado_em"),
    }


# ── APRENDER POR FONTE: qual PERFIL de origem converte (e podar os mortos) ───
# O ciclo da descoberta autônoma só fecha se a máquina souber quais fontes VENDEM.
# Cruza posts/fonte (ledger, campo perfil_fonte) × vendas/fonte (Shopee, sub_id[3]).
def _san_fonte(h: str) -> str:
    """Handle → chave de sub_id (mesma regra do coletor/produtor): só a-z0-9, ≤16.
    É a chave de JOIN entre o ledger (perfil original) e a venda (sub_id[3])."""
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())[:16]


def _vendas_por_fonte(dias: int) -> dict:
    """{chave_san: {'vendas': n, 'comissao': R$}} lido do conversionReport da Shopee.
    Best-effort: sem métricas/credencial → {} (o CEO segue sem a parte de venda)."""
    out = defaultdict(lambda: {"vendas": 0, "comissao": 0.0})
    try:
        import metricas_agent as M
        itens = M.puxar_conversoes(dias)
    except Exception as e:
        print(f"(vendas por fonte off: {str(e)[:70]}) — só produção")
        return {}
    for it in itens:
        f = M._fonte(it.get("utm", ""))
        if not f:                       # link antigo sem a etiqueta de fonte → ignora
            continue
        out[f]["vendas"] += 1
        out[f]["comissao"] += float(it.get("comissao") or 0)
    return {k: {"vendas": v["vendas"], "comissao": round(v["comissao"], 2)}
            for k, v in out.items()}


def _analisar_fontes(dias: int) -> list:
    """Cruza produção × venda POR PERFIL-FONTE. Retorna lista ordenada com veredito:
    VENDE (converteu) · MORTA (≥N posts, 0 venda → poda) · NOVA (pouco dado ainda)."""
    min_posts = int(os.getenv("CEO_PODA_MIN_POSTS", 6))
    # posts por fonte (do ledger; perfil_fonte foi gravado pela produção)
    posts = defaultdict(int)
    nicho_de = {}
    for r in _ler_ledger(dias):
        pf = (r.get("perfil_fonte") or "").strip().lower()
        if not pf:
            continue
        posts[pf] += 1
        nicho_de.setdefault(pf, (r.get("nicho") or r.get("nicho_fonte") or "?"))
    vendas = _vendas_por_fonte(dias)
    fontes = []
    for pf, n in posts.items():
        vk = vendas.get(_san_fonte(pf), {"vendas": 0, "comissao": 0.0})
        if vk["vendas"] > 0:
            vd = "VENDE"
        elif n >= min_posts:
            vd = "MORTA"
        else:
            vd = "NOVA"
        fontes.append({"fonte": pf, "nicho": nicho_de.get(pf, "?"), "posts": n,
                       "vendas": vk["vendas"], "comissao": vk["comissao"],
                       "veredito": vd})
    fontes.sort(key=lambda x: (x["comissao"], x["vendas"], x["posts"]), reverse=True)
    return fontes


def _perfil_da_linha(linha: str) -> str:
    """@handle de uma linha de perfil (sem tag #nicho / comentário)."""
    l = linha.strip()
    if not l or l.startswith("#"):
        return ""
    l = re.split(r"[\s#]", l)[0]
    return l.lstrip("@").lower()


def _podar_fontes(fontes: list, executar: bool) -> list:
    """As fontes MORTAS (≥N posts, 0 venda) são comentadas nos arquivos de perfis
    (o coletor para de puxar delas). REVERSÍVEL: comenta a linha com o motivo, não
    apaga. executar=False só LISTA os candidatos (dry-run)."""
    mortas = {f["fonte"] for f in fontes if f["veredito"] == "MORTA"}
    if not mortas:
        return []
    podados = []
    hoje = time.strftime("%Y-%m-%d")
    detalhe = {f["fonte"]: f for f in fontes}
    for arq in (TIKTOK_PERFIS, IG_PERFIS):
        if not arq.exists():
            continue
        linhas = arq.read_text(encoding="utf-8").splitlines()
        mudou = False
        for i, l in enumerate(linhas):
            h = _perfil_da_linha(l)
            if h and h in mortas:
                d = detalhe.get(h, {})
                linhas[i] = (f"# {l.strip()}   # PODADO CEO {hoje}: "
                             f"{d.get('posts', '?')} posts, 0 vendas em vários dias")
                podados.append(h)
                mudou = True
        if mudou and executar:
            arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return sorted(set(podados))


def _render_fontes(fontes: list) -> str:
    """Bloco Markdown do desempenho por fonte + candidatos a poda."""
    if not fontes:
        # histórico não carimbava a fonte; só a produção nova preenche isto.
        return ("## 🔎 Desempenho por FONTE (perfil de origem)\n"
                "_Ainda coletando — a atribuição por fonte é nova; o histórico não "
                "carimbava o perfil de origem. Conforme os vídeos novos postam e "
                "vendem, cada fonte aparece aqui com veredito VENDE/MORTA/NOVA._")
    linhas = ["## 🔎 Desempenho por FONTE (perfil de origem)"]
    vende = [f for f in fontes if f["veredito"] == "VENDE"]
    mortas = [f for f in fontes if f["veredito"] == "MORTA"]
    novas = [f for f in fontes if f["veredito"] == "NOVA"]
    for f in fontes[:12]:
        emo = {"VENDE": "✅", "MORTA": "💀", "NOVA": "🌱"}.get(f["veredito"], "•")
        linhas.append(f"- {emo} @{f['fonte']} ({f['nicho']}): {f['posts']} posts · "
                      f"{f['vendas']} vendas · {_brl(f['comissao'])}")
    if mortas:
        alvos = ", ".join("@" + f["fonte"] for f in mortas[:12])
        linhas += ["", f"**💀 {len(mortas)} fonte(s) MORTA(s)** ({alvos}) — muito post, "
                   "zero venda. Pra podar (comenta nos perfis, reversível): "
                   "`ceo_agent.py --podar-fontes`"]
    linhas.append(f"\n_({len(vende)} vendendo · {len(mortas)} mortas · {len(novas)} "
                  "novas/sem dado ainda)_")
    return "\n".join(linhas)


# ── Jarvis Confidence Score (0-100): quão confiável é a recomendação ────────
def _confidence(a: dict) -> tuple:
    """Baixa confiança com pouco dado (honesto). Cresce com volume + sinal."""
    posts = a["posts_periodo"]
    vendas = a["vendas_video"]
    cats_que_vendem = sum(1 for c in a["cruzamento_categorias"] if c["comissao"] > 0)

    s_dados = min(30, posts / 3.0)          # volume de produção (30 pts @ ~90 posts)
    s_vendas = min(40, vendas * 4.0)        # sinal de conversão (40 pts @ 10 vendas)
    s_nicho = min(20, cats_que_vendem * 10) # clareza de nicho (2 categorias vendendo)
    s_recencia = 10 if a.get("nichos_gerado_em") else 0
    score = int(round(s_dados + s_vendas + s_nicho + s_recencia))

    if score < 25:
        nivel = "MUITO BAIXA — dados insuficientes; recomendações preliminares"
    elif score < 50:
        nivel = "BAIXA — dá pra tendência, ainda não pra decidir sozinho"
    elif score < 75:
        nivel = "MÉDIA — sinais consistentes começando a aparecer"
    else:
        nivel = "ALTA — dados sólidos pra embasar decisão"
    return score, nivel


# ── MEMÓRIA DO CEO: ler passado, conferir resultado, gravar ─────────────────
def _ler_memoria_ceo(a: dict, limite: int = 6) -> str:
    """Puxa relatórios/decisões/veredictos anteriores do CEO pra ele NÃO repetir
    conselho e referenciar o que já aconteceu. Vazio se não houver memória."""
    if not _MEM_OK:
        return ""
    try:
        cats = " ".join(c["categoria"] for c in a.get("cruzamento_categorias", [])[:3])
        r = buscar_memorias(query=f"ceo relatorio decisao resultado {cats}",
                            colecao="lessons", limite=limite, filtros={"agente": "ceo"})
        itens = r.get("resultados", [])
        if not itens:
            return ""
        return "\n".join(f"- {m.get('texto', '')[:220]}" for m in itens)
    except Exception:
        return ""


def _conferir_resultados() -> str:
    """OUTCOME-CHECK — o fechamento do loop de aprendizado. Pra cada decisão
    aplicada há >=7 dias e ainda não conferida, compara a métrica-alvo (vendas/
    comissão) do momento da aplicação vs AGORA, escreve um veredito, marca
    'conferido' no decisoes.jsonl e grava na memória. Retorna bloco Markdown."""
    if not DECISOES.exists():
        return ""
    regs = []
    for l in DECISOES.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        try:
            regs.append(json.loads(l))
        except Exception:
            regs.append(None)
    agora = _analisar(30)
    v_now, c_now = agora["vendas_video"], round(agora["comissao_video"], 2)
    veredictos, mudou = [], False
    LIMITE = 7 * 86400
    for i, d in enumerate(regs):
        if not d or d.get("acao") != "aplicar" or d.get("conferido"):
            continue
        if "snap_vendas" not in d:            # decisão antiga sem snapshot → não mede
            continue
        if int(time.time()) - int(d.get("ts", 0)) < LIMITE:
            continue                          # ainda cedo (< 7 dias)
        dv = v_now - int(d.get("snap_vendas", 0))
        dc = round(c_now - float(d.get("snap_comissao", 0)), 2)
        vd = "AJUDOU" if (dv > 0 or dc > 0) else ("PIOROU" if (dv < 0 or dc < 0) else "NEUTRO")
        txt = (f"Veredito: '{d.get('proposta')}' ({d.get('env')}: "
               f"{d.get('de') or '(vazio)'}→{d.get('para')}) aplicada em {d.get('data')} → "
               f"vendas {d.get('snap_vendas')}→{v_now} ({'+' if dv >= 0 else ''}{dv}), "
               f"comissão {'+' if dc >= 0 else ''}{dc}. {vd}.")
        veredictos.append(txt)
        d.update({"conferido": True, "veredito": vd, "conferido_ts": int(time.time())})
        regs[i] = d
        mudou = True
        if _MEM_OK:
            try:
                registrar_memoria(tipo="estrategia", texto=txt,
                    metadata={"agente": "ceo", "tipo_ceo": "resultado", "env": d.get("env"),
                              "veredito": vd, "delta_vendas": dv, "delta_comissao": dc},
                    colecao="lessons", tags=["ceo", "resultado", vd.lower()])
            except Exception:
                pass
    if mudou:
        DECISOES.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in regs if r) + "\n",
            encoding="utf-8")
    if not veredictos:
        return ""
    return ("## 📈 Resultado das decisões anteriores (auto-conferido)\n"
            + "\n".join(f"- {v}" for v in veredictos) + "\n")


def _gravar_memoria_relatorio(a: dict, score: int, nivel: str, propostas: list) -> None:
    """CEO ESCREVE: registra o retrato do relatório desta semana na memória."""
    if not _MEM_OK:
        return
    try:
        aplicaveis = [p["titulo"] for p in propostas if p.get("tipo") == "config"]
        texto = (f"Relatório CEO ({a['dias']}d): Confidence {score}/100 "
                 f"({nivel.split('—')[0].strip()}). Comissão vídeo {_brl(a['comissao_video'])}, "
                 f"{a['vendas_video']} venda(s), {a['posts_periodo']} posts. "
                 f"Propostas: {'; '.join(aplicaveis) or 'nenhuma'}.")
        registrar_memoria(tipo="estrategia", texto=texto,
            metadata={"agente": "ceo", "tipo_ceo": "relatorio", "score": score,
                      "comissao_video": a["comissao_video"], "vendas_video": a["vendas_video"],
                      "posts": a["posts_periodo"], "dias": a["dias"]},
            colecao="lessons", tags=["ceo", "relatorio"])
    except Exception:
        pass


_PROMPT = (
    "Você é o CEO IA da TopShop (marketing de afiliados, vídeos de achadinhos em "
    "IG/FB/YouTube). Fale como um conselheiro estratégico DIRETO e honesto, em "
    "português do Brasil. Recebe os DADOS REAIS da operação (o que foi PRODUZIDO "
    "vs o que VENDEU) e o Jarvis Confidence Score.\n"
    "IMPORTANTíSSIMO: seja HONESTO com pouco dado — se o score é baixo, diga que "
    "é cedo e trate as propostas como HIPÓTESES a testar, não certezas.\n"
    "Escreva em Markdown, EXATAMENTE nesta estrutura:\n"
    "## 📊 Resumo executivo\n(3-5 linhas: receita, o que vende, o que não, saúde)\n"
    "## 🎯 Propostas (aprove/rejeite)\n"
    "Liste 3 a 5 propostas NUMERADAS. Cada uma: **título curto** — por quê (cite o "
    "DADO), a AÇÃO concreta (ex: 'produzir +1/dia de beleza', 'cortar a fonte X', "
    "'repostar o produto Y'), e o impacto esperado. Só proponha o que os dados "
    "sustentam.\n"
    "## ⚠️ Ressalva\n(1-2 linhas sobre a confiança dos dados)\n"
    "Sem inventar números que não estão nos dados. Devolva SÓ o Markdown.\n"
    "OBS: o campo 'fontes' traz o desempenho por PERFIL de origem (posts × vendas). "
    "Se houver fonte com muitos posts e ZERO venda (veredito MORTA), proponha PODAR; "
    "se alguma converte bem (VENDE), proponha PRIORIZAR/curar mais parecidas.\n\n"
    "MEMÓRIA (seus relatórios/decisões/veredictos anteriores). NÃO repita conselho "
    "já dado; se uma decisão passada já foi conferida, leve o RESULTADO dela em conta "
    "(reforce o que AJUDOU, recue no que PIOROU):\n{memoria}\n\n"
    "DADOS (JSON):\n{dados}\n\nJarvis Confidence Score: {score}/100 ({nivel})")


def _relatorio_gemini(a: dict, score: int, nivel: str, memoria: str = "") -> str:
    api_key = os.getenv("GEMINI_API_KEY", "")
    dados = json.dumps(a, ensure_ascii=False, indent=2)
    prompt = _PROMPT.format(dados=dados, score=score, nivel=nivel,
                            memoria=(memoria or "(sem memória anterior — 1º relatório)"))
    if api_key:
        for tent in (1, 2):
            try:
                from google import genai
                cli = genai.Client(api_key=api_key)
                r = cli.models.generate_content(
                    model="gemini-2.5-flash", contents=[{"parts": [{"text": prompt}]}])
                t = (r.text or "").strip()
                if t:
                    return t
            except Exception as e:
                s = str(e)
                if tent == 1 and ("429" in s or "RESOURCE_EXHAUSTED" in s):
                    time.sleep(20); continue
                print(f"(Gemini falhou: {s[:80]}) — uso relatório simples")
                break
    return _relatorio_simples(a)


def _relatorio_simples(a: dict) -> str:
    linhas = ["## 📊 Resumo executivo (fallback sem Gemini)",
              f"- Posts no período: {a['posts_periodo']} · "
              f"Comissão de vídeo: {_brl(a['comissao_video'])} · "
              f"Vendas de vídeo: {a['vendas_video']}",
              "", "## 🎯 Cruzamento produção × venda (categoria)"]
    for c in a["cruzamento_categorias"][:8]:
        linhas.append(f"- {c['categoria']}: {c['postados']} posts · "
                      f"{c['vendas']} vendas · {_brl(c['comissao'])}")
    return "\n".join(linhas)


def _enviar_telegram(texto: str) -> None:
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = (os.getenv("TELEGRAM_ALERT_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not tok or not chat:
        return
    try:
        import requests
        # Telegram: 4096 chars max por mensagem
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                      json={"chat_id": chat, "text": texto[:4000],
                            "disable_web_page_preview": True})
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# NÍVEL 1 — AUTONOMIA SUPERVISIONADA
# O CEO gera propostas ESTRUTURADAS (não só prosa) mirando knobs de uma WHITELIST
# segura. O Dre aplica com `--aplicar N` (backup + log, reversível com `--desfazer`).
# SEGURANÇA: só mexe nos knobs abaixo — NUNCA em token/segredo/id de conta.
# ═══════════════════════════════════════════════════════════════════════════
PROPOSTAS_JSON = CEO_DIR / "propostas.json"
DECISOES = CEO_DIR / "decisoes.jsonl"

# knob -> regras de validação. tipo: bool | int | float
SAFE_ENV = {
    "DEDUP_DIAS":         {"tipo": "int",   "min": 5,   "max": 90,  "desc": "dias até um produto poder repostar"},
    "AUTO_RESP_MAX":      {"tipo": "int",   "min": 10,  "max": 200, "desc": "máx de respostas por rodada"},
    "AUTO_RESP_HORAS":    {"tipo": "int",   "min": 12,  "max": 168, "desc": "janela de posts que o auto-resposta varre"},
    "MUSICA_FUNDO_VOL":   {"tipo": "float", "min": 0.0, "max": 0.30, "desc": "volume da trilha de fundo"},
    "ENGAJAR_COMENTARIO": {"tipo": "bool",  "desc": "1º comentário automático"},
    "AUTO_RESPONDER":     {"tipo": "bool",  "desc": "auto-resposta a comentários"},
    "AUTO_RESP_DM":       {"tipo": "bool",  "desc": "mandar o link na DM"},
    "AMAZON_ATIVO":       {"tipo": "bool",  "desc": "usar Amazon como 2ª fonte"},
    "ANTI_WATERMARK":     {"tipo": "bool",  "desc": "descartar vídeo-fonte com marca d'água"},
    "MULTI_CONTA":        {"tipo": "bool",  "desc": "rotear cada produto pra conta do nicho"},
}


def _env_atual(chave: str) -> str:
    return os.getenv(chave, "").strip()


def _bool_on(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "sim")


def _validar_valor(chave: str, valor) -> str:
    """Normaliza+valida o valor pro tipo do knob. Levanta ValueError se inválido."""
    regra = SAFE_ENV[chave]
    t = regra["tipo"]
    if t == "bool":
        return "1" if _bool_on(valor) else "0"
    if t == "int":
        n = int(float(valor))
        n = max(regra["min"], min(regra["max"], n))
        return str(n)
    if t == "float":
        f = float(valor)
        f = max(regra["min"], min(regra["max"], f))
        return f"{f:.3f}".rstrip("0").rstrip(".")
    raise ValueError(f"tipo desconhecido: {t}")


# ── Motor determinístico de propostas (do DADO, não do Gemini) ──────────────
def _propostas_estruturadas(a: dict) -> list:
    """Gera propostas APLICÁVEIS a partir do estado atual + dos dados. Honesto:
    só propõe o que o dado sustenta; com pouco dado, poucas (ou nenhuma)."""
    props = []
    vendas = a.get("vendas_video", 0)
    posts = a.get("posts_periodo", 0)
    cats_vendem = [c for c in a.get("cruzamento_categorias", []) if c.get("comissao", 0) > 0]

    def add(tipo, titulo, motivo, env, para, impacto):
        de = _env_atual(env) or ("0" if SAFE_ENV[env]["tipo"] == "bool" else "")
        try:
            para_n = _validar_valor(env, para)
        except Exception:
            return
        if str(de) == str(para_n):      # já está no valor proposto → não propõe
            return
        props.append({"id": len(props) + 1, "tipo": tipo, "titulo": titulo,
                      "motivo": motivo, "acao": {"env": env, "de": str(de), "para": para_n},
                      "impacto": impacto, "reversivel": True})

    # R1: engajamento é o motor de clique — se algo estiver desligado, liga
    if not _bool_on(_env_atual("ENGAJAR_COMENTARIO")):
        add("config", "Ligar o 1º comentário automático",
            "engajamento é o que puxa clique; está desligado", "ENGAJAR_COMENTARIO", "1",
            "todo post sai com o 1º comentário (link no FB, isca no IG)")
    if not _bool_on(_env_atual("AUTO_RESPONDER")):
        add("config", "Ligar a auto-resposta a comentários",
            "responder 'eu quero' na hora converte interesse em clique", "AUTO_RESPONDER", "1",
            "comentários com gatilho passam a ser respondidos a cada 20min")
    if _bool_on(_env_atual("AUTO_RESPONDER")) and not _bool_on(_env_atual("AUTO_RESP_DM")):
        add("config", "Ligar o link na DM",
            "no direct o link CLICA (no comentário não) — conversão direta", "AUTO_RESP_DM", "1",
            "quem comenta gatilho recebe o link clicável no direct")

    # R2: Amazon como 2ª fonte pra não desperdiçar vídeo não-Shopee
    if not _bool_on(_env_atual("AMAZON_ATIVO")):
        add("config", "Ativar a Amazon como 2ª fonte",
            "vídeos que não casam com a Shopee estão sendo desperdiçados", "AMAZON_ATIVO", "1",
            "produtos sem match na Shopee viram link de afiliado Amazon")

    # R3: sem vendas ainda + volume ok → hipótese: girar o catálogo mais rápido
    dedup = _env_atual("DEDUP_DIAS") or "30"
    if vendas == 0 and posts >= 15 and int(float(dedup)) > 15:
        add("config", "Girar o catálogo mais rápido (teste)",
            f"{posts} posts e 0 venda de vídeo no período — hipótese: renovar produtos "
            f"mais rápido acha o que converte", "DEDUP_DIAS", "15",
            "um produto pode repostar após 15d (era %sd) — mais variedade" % dedup)

    # R4: JÁ vendeu algo → repor os campeões mais cedo (acelera o que dá dinheiro)
    if vendas > 0 and int(float(dedup)) > 20:
        campea = cats_vendem[0]["categoria"] if cats_vendem else "a campeã"
        add("config", "Repor os campeões mais cedo",
            f"categoria '{campea}' já converteu; repor antes acelera a receita",
            "DEDUP_DIAS", "18", "campeões podem voltar após 18d (era %sd)" % dedup)

    # R5: revisão manual (não aplica sozinho) — cortar fonte que só gasta e não vende
    if vendas == 0 and posts >= 30:
        props.append({"id": len(props) + 1, "tipo": "revisao",
                      "titulo": "Revisar as fontes de vídeo (perfis do TikTok)",
                      "motivo": f"{posts} posts sem venda: pode haver fonte que só gasta produção",
                      "acao": None,
                      "impacto": "revisão manual em tiktok_perfis.txt — cortar perfil fraco",
                      "reversivel": False})
    return props


def _render_propostas(props: list) -> str:
    if not props:
        return ("## 🤖 Propostas aplicáveis (Nível 1)\n"
                "_Nenhuma proposta automática com os dados/estado atuais — a máquina "
                "já está com os knobs seguros no lugar. Seguimos coletando dado._\n")
    linhas = ["## 🤖 Propostas aplicáveis (Nível 1)",
              "_Aprove com `ceo_agent.py --aplicar N` · reverte com `--desfazer`_", ""]
    for p in props:
        if p["tipo"] == "config":
            ac = p["acao"]
            linhas.append(f"**{p['id']}. {p['titulo']}** — {p['motivo']}.")
            linhas.append(f"   ⚙️ `{ac['env']}`: `{ac['de'] or '(vazio)'}` → `{ac['para']}` · "
                          f"{p['impacto']} · ✅ reversível · `--aplicar {p['id']}`")
        else:
            linhas.append(f"**{p['id']}. {p['titulo']}** _(revisão manual)_ — {p['motivo']}.")
            linhas.append(f"   👀 {p['impacto']} (não aplica sozinho)")
        linhas.append("")
    return "\n".join(linhas)


def _salvar_propostas(dias: int, props: list) -> None:
    CEO_DIR.mkdir(parents=True, exist_ok=True)
    PROPOSTAS_JSON.write_text(json.dumps(
        {"gerado_em": int(time.time()), "data": time.strftime("%Y-%m-%d %H:%M"),
         "dias": dias, "propostas": props}, ensure_ascii=False, indent=2), encoding="utf-8")


def _carregar_propostas() -> list:
    try:
        return json.loads(PROPOSTAS_JSON.read_text(encoding="utf-8")).get("propostas", [])
    except Exception:
        return []


def _escrever_env(chave: str, valor: str) -> str:
    """Atualiza (ou adiciona) chave=valor no .env, com backup. Retorna o valor antigo."""
    p = BASE_DIR / ".env"
    linhas = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    antigo, achou, out = "", False, []
    for ln in linhas:
        s = ln.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k.lower().startswith("export "):
                k = k[7:].strip()
            if k == chave:
                antigo = s.split("=", 1)[1].strip().strip('"').strip("'")
                out.append(f"{chave}={valor}")
                achou = True
                continue
        out.append(ln)
    if not achou:
        out.append(f"{chave}={valor}")
    if p.exists():
        import shutil
        shutil.copy2(p, p.parent / (".env.bak_" + time.strftime("%Y%m%d_%H%M%S")))
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    return antigo


def _log_decisao(reg: dict) -> None:
    CEO_DIR.mkdir(parents=True, exist_ok=True)
    with open(DECISOES, "a", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False) + "\n")


def _aplicar(n: int) -> int:
    props = _carregar_propostas()
    alvo = next((p for p in props if p.get("id") == n), None)
    if not alvo:
        print(f"❌ proposta {n} não existe. Rode `ceo_agent.py` pra gerar as propostas.")
        return 1
    if alvo["tipo"] != "config" or not alvo.get("acao"):
        print(f"⚠️ Proposta {n} é REVISÃO manual — não dá pra aplicar automático.\n"
              f"   {alvo['titulo']}: {alvo['impacto']}")
        return 1
    env = alvo["acao"]["env"]
    if env not in SAFE_ENV:
        print(f"🛡️ recusado: '{env}' não está na whitelist segura (o CEO nunca mexe em segredo).")
        return 1
    try:
        valor = _validar_valor(env, alvo["acao"]["para"])
    except Exception as e:
        print(f"❌ valor inválido pra {env}: {e}")
        return 1
    antigo = _escrever_env(env, valor)
    _snap = _analisar(30)          # foto da métrica AGORA → o outcome-check compara depois
    _log_decisao({"ts": int(time.time()), "data": time.strftime("%Y-%m-%d %H:%M"),
                  "acao": "aplicar", "proposta": alvo["titulo"], "env": env,
                  "de": antigo, "para": valor,
                  "snap_vendas": _snap["vendas_video"], "snap_comissao": _snap["comissao_video"],
                  "snap_posts": _snap["posts_periodo"], "conferido": False})
    if _MEM_OK:
        try:
            registrar_memoria(tipo="estrategia",
                texto=(f"CEO aplicou (Nível 1): {alvo['titulo']}. "
                       f"{env}: {antigo or '(vazio)'} -> {valor}. Motivo: {alvo.get('motivo', '')}"),
                metadata={"agente": "ceo", "tipo_ceo": "decisao", "env": env,
                          "de": str(antigo), "para": str(valor), "aplicado_ts": int(time.time())},
                colecao="lessons", tags=["ceo", "decisao", env])
        except Exception:
            pass
    print(f"✅ APLICADO: {alvo['titulo']}\n   {env}: {antigo or '(vazio)'} → {valor}")
    print("   (backup do .env criado; reverte com `ceo_agent.py --desfazer`)")
    print("   ⚠️ reinicie o serviço p/ valer no daemon:  systemctl restart jarvis")
    _enviar_telegram(f"👑 CEO aplicou (Nível 1): {alvo['titulo']}\n"
                     f"{env}: {antigo or '(vazio)'} → {valor}\n"
                     f"Reverter: ceo_agent.py --desfazer")
    return 0


def _desfazer() -> int:
    if not DECISOES.exists():
        print("nada pra desfazer (sem decisões registradas).")
        return 0
    linhas = [l for l in DECISOES.read_text(encoding="utf-8").splitlines() if l.strip()]
    # acha a última decisão do tipo 'aplicar' ainda não desfeita
    for i in range(len(linhas) - 1, -1, -1):
        try:
            d = json.loads(linhas[i])
        except Exception:
            continue
        if d.get("acao") == "aplicar" and not d.get("desfeita"):
            env, de = d["env"], d.get("de", "")
            _escrever_env(env, de if de != "" else ("0" if SAFE_ENV.get(env, {}).get("tipo") == "bool" else ""))
            d["desfeita"] = True
            linhas[i] = json.dumps(d, ensure_ascii=False)
            DECISOES.write_text("\n".join(linhas) + "\n", encoding="utf-8")
            _log_decisao({"ts": int(time.time()), "data": time.strftime("%Y-%m-%d %H:%M"),
                          "acao": "desfazer", "proposta": d.get("proposta", ""),
                          "env": env, "de": d.get("para", ""), "para": de})
            print(f"↩️  DESFEITO: {d.get('proposta')}\n   {env}: {d.get('para')} → {de or '(vazio)'}")
            print("   ⚠️ reinicie:  systemctl restart jarvis")
            return 0
    print("nada pra desfazer (todas as decisões já foram revertidas).")
    return 0


def _listar_decisoes() -> int:
    if not DECISOES.exists():
        print("nenhuma decisão registrada ainda.")
        return 0
    print("📒 Histórico de decisões do CEO (Nível 1):")
    for l in DECISOES.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(l)
        except Exception:
            continue
        tag = "✅" if d.get("acao") == "aplicar" else "↩️"
        risca = " (desfeita)" if d.get("desfeita") else ""
        print(f"  {tag} {d.get('data')} · {d.get('proposta')} · "
              f"{d.get('env')}: {d.get('de') or '(vazio)'} → {d.get('para') or '(vazio)'}{risca}")
    return 0


def main():
    argv = sys.argv[1:]
    if "--aplicar" in argv:
        i = argv.index("--aplicar")
        try:
            return _aplicar(int(argv[i + 1]))
        except (IndexError, ValueError):
            print("uso: ceo_agent.py --aplicar N")
            return 1
    if "--desfazer" in argv:
        return _desfazer()
    if "--decisoes" in argv:
        return _listar_decisoes()

    dias = 30
    for arg in argv:
        if arg.isdigit():
            dias = max(1, int(arg))
            break

    # PODAR FONTES sob demanda: comenta as fontes MORTAS nos arquivos de perfis.
    if "--podar-fontes" in argv:
        fontes = _analisar_fontes(dias)
        podados = _podar_fontes(fontes, executar=True)
        if podados:
            print(f"💀 {len(podados)} fonte(s) podada(s) (comentadas, reversível): "
                  + ", ".join("@" + p for p in podados))
        else:
            print("✅ nenhuma fonte MORTA pra podar (todas vendem ou ainda têm poucos "
                  "posts). Rode o relatório pra ver o desempenho por fonte.")
        return 0

    a = _analisar(dias)
    score, nivel = _confidence(a)
    fontes = _analisar_fontes(dias)                  # APRENDE: qual perfil-fonte converte
    a["fontes"] = fontes                             # entra no JSON que o Gemini lê
    bloco_resultados = _conferir_resultados()        # CONFERE: outcome-check das decisões
    memoria = _ler_memoria_ceo(a)                    # LÊ: o que o CEO já aconselhou/aprendeu
    relatorio = _relatorio_gemini(a, score, nivel, memoria)
    propostas = _propostas_estruturadas(a)
    _salvar_propostas(dias, propostas)
    bloco_props = _render_propostas(propostas)
    _gravar_memoria_relatorio(a, score, nivel, propostas)   # ESCREVE: registra este relatório

    cabecalho = (f"# 👑 CEO TopShop — Conselheiro\n"
                 f"Período: últimos {dias} dias · "
                 f"**Jarvis Confidence Score: {score}/100** ({nivel})\n"
                 f"Gerado: {time.strftime('%Y-%m-%d %H:%M')}"
                 f"{' · 🧠 memória ativa' if _MEM_OK else ''}\n\n---\n\n")
    doc = cabecalho + relatorio + "\n\n---\n\n"
    # bloco de desempenho por fonte + poda automática opcional (CEO_PODA_AUTO=1)
    bloco_fontes = _render_fontes(fontes)
    if bloco_fontes:
        if os.getenv("CEO_PODA_AUTO", "0").strip().lower() in ("1", "true", "sim"):
            podados = _podar_fontes(fontes, executar=True)
            if podados:
                bloco_fontes += ("\n\n**✂️ Poda automática (CEO_PODA_AUTO):** "
                                 + ", ".join("@" + p for p in podados) + " — comentadas.")
        doc += bloco_fontes + "\n\n---\n\n"
    if bloco_resultados:
        doc += bloco_resultados + "\n---\n\n"
    doc += bloco_props

    print("\n" + "=" * 66)
    print(doc)
    print("=" * 66)

    CEO_DIR.mkdir(parents=True, exist_ok=True)
    arq = CEO_DIR / f"relatorio_{time.strftime('%Y-%m-%d_%H%M')}.md"
    arq.write_text(doc, encoding="utf-8")
    print(f"\n💾 Salvo em {arq}")

    # resumo curto no Telegram (o relatório completo fica no arquivo)
    aplicaveis = [p for p in propostas if p["tipo"] == "config"]
    resumo = (f"👑 CEO TopShop — relatório dos últimos {dias}d\n"
              f"Confidence: {score}/100 ({nivel.split('—')[0].strip()})\n"
              f"Comissão vídeo: {_brl(a['comissao_video'])} · "
              f"vendas: {a['vendas_video']} · posts: {a['posts_periodo']}\n"
              f"Propostas aplicáveis: {len(aplicaveis)} "
              f"(aprove com: ceo_agent.py --aplicar N)\n\n"
              f"{relatorio}")
    _enviar_telegram(resumo)
    print("📱 Resumo enviado no Telegram (se configurado).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
