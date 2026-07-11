# 🤖 Projeto Jarvis — Roadmap TopShop

Máquina autônoma de marketing de afiliados (Shopee) rodando 24/7 na VPS.
Coleta virais → reproduz no padrão **TopShop** → posta sozinha → aprende o que
converte → repete. **Objetivo: virar máquina de dinheiro, dia após dia.**

> Documento vivo. É a memória do projeto entre sessões — tudo que a gente
> combina entra aqui. Legenda: ✅ pronto · 🔜 próximo · 🧠 backlog/avançado · 🐞 bug.

---

## ✅ Concluído (funcionando)

### Vídeo — o coração (dá o engajamento final)
- **Pipeline TikTok completo:** `tiktok_coletor.py` (acha viral → identifica
  produto via Gemini → casa na Shopee → gera link de afiliado `sub_id=tiktok`
  → baixa sem marca d'água) → `produzir_tiktok.py` (esteira TopShop).
- **Narração própria (ElevenLabs "Michael"):** roteiro ÚNICO por vídeo escrito
  pelo Gemini, **substitui o áudio original** → mata copyright/crédito a terceiro.
- **Música de fundo baixinha** sob a narração (sorteada por vídeo) → nunca fica
  silêncio no fim; aceita `.mp4/.mov` (Reels Sound) direto.
- **VFX aleatório por vídeo** (rotação/zoom/brilho/saturação/grão) → cada post
  sai único (anti-copyright / algoritmo).
- **Hook sempre 1 linha** + auto-encolhe a fonte pra caber, posição regulável
  (`HK_Y`); acabou o hook em 2 linhas tampando o header.
- **Texto sem erro de gênero:** legendas com o nome como aposto
  ("achadinho: {nome}") + prompt da narração reforçado (masc/fem, ortografia,
  fechamentos naturais).

### Dinheiro / aprendizado
- **Posts Ledger** (`posts_ledger.py`) + **agente de métricas**
  (`metricas_agent.py`, lê o conversionReport da Shopee) → grava
  `nichos_quentes.json`.
- **Boost de nicho** no caçador (`shopee_affiliate._fator_nicho`): o que vende
  ganha score maior → o hunter aprende o que converte.

### Distribuição / site
- **Auto-post no grupo do Telegram** (@achadinhosrelampagoh).
- **Facebook posting consertado** (2026-07-11): era um TOKEN DE PÁGINA em
  `META_ACCESS_TOKEN` (o `/me/accounts` não existe pra Página). Fix: setar
  `FACEBOOK_PAGE_TOKEN` com o mesmo valor — o código usa direto, sem
  `/me/accounts`. `diag_facebook.py` detecta esse caso sozinho. ✅ post real ok.
- **Site** topshopoficial.com.br: health-check (esconde link morto), fotos
  oficiais via API de afiliado, categorias em barra fixa, mobile 2 colunas.

### Automação
- **Cron** (`setup_cron_jarvis.sh`): coleta 03:00 + produz 3 vídeos/dia
  (04h/12h/18h). O daemon (`jarvis.service`) posta nos horários.
- **Config por `.env`** (sem precisar de patch): `TOPSHOP_HANDLE`, `HK_Y`,
  `HK_FONT`, `HK_FONT_MIN`, `HK_LARG_FRAC`, `ELEVENLABS_*`, `MUSICA_FUNDO_VOL`,
  `MUSICA_FUNDO_DIR`, `NARRAR_TIKTOK`.
- **Perfis-fonte do TikTok** em `tiktok_perfis.txt` (1 por linha) — combustível
  do coletor. SEM esse arquivo o cron coleta zero. Ampliar sempre que esgotar.

---

## 🔜 Próximas (prioridade)

### 1. Multi-conta / roteador de nicho
Já existem as contas (páginas do IG configuradas). Falta o Jarvis **rotear cada
produto pra conta certa por nicho** e postar em múltiplos destinos.
- **Instagram:** `@topshop.__` (geral) · `@topshopbeauty._` (beleza) ·
  `@topshoptech_` (tech).
- **YouTube:** `topshop.oficial` (geral) · `topshopbeauty` (beleza).
- Cada conta = handle próprio + nicho + (opcional) voz própria + páginas/tokens.
- Coletor/produtor decidem o nicho do produto → mandam pro perfil e handle
  daquele nicho (o `TOPSHOP_HANDLE` vira dinâmico por conta).

### 2. Expandir a rede de vídeos (fontes novas)
- Coletar de **perfis "dark" do Instagram** que postam produtos e são
  relevantes (centenas de seguidores) — um coletor de IG análogo ao do TikTok.
- Preferir **fontes sem texto** na tela (a edição fica mais limpa).

---

## 🧠 Backlog / avançado

- **Multiplataforma de afiliados (Amazon + outras):** além da Shopee, pegar
  link de afiliado da **Amazon** (os "amazon gadgets" que viralizam) e de outras
  plataformas. Cada plataforma numa **página separada do site** (Achados Shopee /
  Achados Amazon / …). O coletor já baixa virais de vários nichos — falta o
  matcher/gerador de link por plataforma e a vitrine dividida.
- **Comentários automáticos + Stories** pro Jarvis (auto-engajamento).
- **Auto-DM** pra CTA tipo "COMENTE QUERO" → responde no direct com o link
  (precisa Graph API / permissões de mensagem).
- **CEO IA dentro do Jarvis:** uma IA estratégica que lê as métricas, decide
  nichos/orçamento, o que escalar ou cortar, e ajusta a máquina sozinha
  (o "cérebro" acima dos agentes).
- **Gemini Vision** pra detectar texto no vídeo (substituir o tesseract que
  falhava no espelhamento) e liberar espelhamento seguro só quando não há texto.
- **Proxies por conta** — só se vier punição/bloqueio (não antes).
- **Descoberta automática de grupos de Telegram** novos (grupos_descoberta) pra
  alimentar o hunter com mais fontes.

---

## 📌 Referência rápida (infra)

- **VPS:** Contabo · daemon `jarvis.service` (`python -m agents.daemon_maestro`)
  · venv em `/root/jarvis/.venv`.
- **Padrão de deploy:** arquivos raiz (`~/jarvis/*.py`, `.sh`) por scp; arquivos
  de pacote (`integrations/`, `agents/`, `creative_engine/`) por **patcher**
  (backup + verificação + idempotente). A VPS **não** dá git-sync com o repo.
- **Segurança:** nunca colar tokens/segredos no chat; segredos no `.env` da VPS
  / Bitwarden; PAT do GitHub com escopo mínimo.
- **Marcas/contas:** Site `topshopoficial.com.br` · Telegram
  `@achadinhosrelampagoh` · IG/YouTube (ver seção Multi-conta).
