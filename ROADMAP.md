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

### 1. Multi-conta / roteador de nicho  ✅ COMPLETO (IG + FB + YouTube)
Roteia cada produto pra conta do nicho: renderiza com o @handle certo E posta na
conta certa. Arquitetura: produção grava `conta.json` ao lado do `video.mp4`; o
`meta_uploader` lê e posta naquela conta (sem tocar no publish_guard/daemon).
- **Contas (contas.json):** geral `@topshop.__` · beleza `@topshopbeauty._` ·
  tech `@topshoptech_` (cada uma com ig_id, page_id, page_token_env).
- **Router:** `roteador_contas.py` (nicho por palavra-chave em nome+categoria).
- **Handle no render:** `narrated_video_agent` lê `TOPSHOP_HANDLE` em tempo de
  render; a produção seta por vídeo.
- **Ligado por** `MULTI_CONTA=1` no `.env` (desligado = comportamento antigo).
- ✅ **IG + Facebook CONFIRMADO** (2026-07-12): produção roteia por nicho +
  `meta_uploader` lê o `conta.json` e ativa a conta certa (ig_id + token do
  nicho) — provado em checagem seca (tech→@topshoptech_, geral→@topshop.__,
  sem conta.json→default). O daemon posta na conta certa nos horários.
- ✅ **YouTube:** token expirava (invalid_grant). `auth_youtube.py` re-autentica
  na VPS via TÚNEL SSH (`ssh -L 8765:localhost:8765`), headless, com refresh_token
  (offline). ⚠️ manter o app OAuth em **Production** (Testing expira em 7 dias).
- ✅ **YouTube multi-canal CONFIRMADO** (2026-07-12): `youtube_uploader`
  refresh-only + escolhe o token pelo `conta.youtube`. **3 canais autenticados**
  (token com refresh, app em Production): geral→`topshop.oficial`
  (youtube_token.json) · beleza→`topshopbeauty` (youtube_token_beauty.json) ·
  tech→`@topshoptech` (youtube_token_tech.json). `auth_youtube.py <canal>` faz o
  consentimento headless (fluxo de colar o code, sem túnel).

### 2. Dedup por PRODUTO no coletor/produtor
Hoje 2 vídeos diferentes do mesmo item (ex: "Gaabor Ferro a Vapor" casou 2x)
viram 2 posts iguais. Deduplicar pelo produto/item_id da Shopee (ou nome
normalizado) pra nunca postar o mesmo produto duas vezes seguidas.

### 3. Expandir a rede de vídeos (fontes novas)
- Coletar de **perfis "dark" do Instagram** que postam produtos e são
  relevantes (centenas de seguidores) — um coletor de IG análogo ao do TikTok.
- Preferir **fontes sem texto** na tela (a edição fica mais limpa).

---

## 🧠 Backlog / avançado

- **Multiplataforma de afiliados (Amazon + outras):** 🚧 em construção.
  - ✅ **Camada 1 (coletor):** Shopee falhou → tenta Amazon via LINK DE BUSCA
    afiliado (`/s?k=produto&tag=SUATAG`, sem PA-API, só a tag), com filtro
    anti-lixo (barra hook em inglês). plano carrega `plataforma`. Gated por
    `AMAZON_ATIVO=1` + `AMAZON_TAG` (desligado = só Shopee).
  - ✅ **Camada 2 (produção/site):** `plataforma` flui do plano → produção →
    `_registrar_no_site` (Amazon não busca foto na Shopee; a fila do site marca
    `plataforma`). Falta só a Camada 3 usar isso no layout.
  - ✅ **Camada 3 (layout do site):** vitrine com toggle Tudo/🛒Shopee/📦Amazon +
    selo por card + placeholder pros cards Amazon. So aditivo (com so-Shopee o
    site fica igual; o toggle so surge com produto Amazon). Testado em preview.
  - 🎬 **GO-LIVE:** aplicar patch_camada3_site.py + rodar deploy_site.py; depois
    `AMAZON_ATIVO=1` no .env liga o pipeline inteiro (coletor→produção→site).
  - 🔮 Depois: PA-API pra link direto do produto (foto/preço) + outras plataformas.
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
- **Contas por nicho:**
  - geral: IG @topshop.__ · FB TopShop & Ofertas · YT topshop.oficial
  - beleza: IG @topshopbeauty._ · FB TopShop Descontos · YT topshopbeauty
  - tech: IG @topshoptech_ · FB TopShop & Casa · YT @topshoptech
- **Marcas:** Site `topshopoficial.com.br` · Telegram `@achadinhosrelampagoh`.
