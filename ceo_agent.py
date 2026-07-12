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
import sys
import json
import time
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LEDGER = BASE_DIR / "shared" / "posts_ledger.jsonl"
NICHOS = BASE_DIR / "shared" / "nichos_quentes.json"
CEO_DIR = BASE_DIR / "shared" / "ceo"


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
    for r in ledger:
        prod_cat[(r.get("categoria") or "sem_categoria").lower()] += 1
        prod_plat[r.get("plataforma") or r.get("plataforma_afiliado") or "?"] += 1
        prod_fonte[r.get("fonte") or "?"] += 1
        prod_hora[r.get("hora", "?")] += 1

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
        "producao_por_fonte": dict(prod_fonte),
        "producao_por_hora": dict(sorted(prod_hora.items(), key=lambda x: -x[1])[:6]),
        "nichos_gerado_em": nichos.get("gerado_em"),
    }


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
    "Sem inventar números que não estão nos dados. Devolva SÓ o Markdown.\n\n"
    "DADOS (JSON):\n{dados}\n\nJarvis Confidence Score: {score}/100 ({nivel})")


def _relatorio_gemini(a: dict, score: int, nivel: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "")
    dados = json.dumps(a, ensure_ascii=False, indent=2)
    prompt = _PROMPT.format(dados=dados, score=score, nivel=nivel)
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


def main():
    dias = 30
    if len(sys.argv) > 1:
        try:
            dias = max(1, int(sys.argv[1]))
        except ValueError:
            pass

    a = _analisar(dias)
    score, nivel = _confidence(a)
    relatorio = _relatorio_gemini(a, score, nivel)

    cabecalho = (f"# 👑 CEO TopShop — Conselheiro\n"
                 f"Período: últimos {dias} dias · "
                 f"**Jarvis Confidence Score: {score}/100** ({nivel})\n"
                 f"Gerado: {time.strftime('%Y-%m-%d %H:%M')}\n\n---\n\n")
    doc = cabecalho + relatorio

    print("\n" + "=" * 66)
    print(doc)
    print("=" * 66)

    CEO_DIR.mkdir(parents=True, exist_ok=True)
    arq = CEO_DIR / f"relatorio_{time.strftime('%Y-%m-%d_%H%M')}.md"
    arq.write_text(doc, encoding="utf-8")
    print(f"\n💾 Salvo em {arq}")

    # resumo curto no Telegram (o relatório completo fica no arquivo)
    resumo = (f"👑 CEO TopShop — relatório dos últimos {dias}d\n"
              f"Confidence: {score}/100 ({nivel.split('—')[0].strip()})\n"
              f"Comissão vídeo: {_brl(a['comissao_video'])} · "
              f"vendas: {a['vendas_video']} · posts: {a['posts_periodo']}\n\n"
              f"{relatorio}")
    _enviar_telegram(resumo)
    print("📱 Resumo enviado no Telegram (se configurado).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
