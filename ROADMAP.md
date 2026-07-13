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

### 2. Dedup por PRODUTO  ✅ FEITO (2026-07-12)
2 vídeos diferentes do mesmo item viravam 2 posts iguais. Agora o coletor guarda
`shared/produtos_vistos.json` (chave = nome normalizado sem acento, 1as 8
palavras) com TTL `DEDUP_DIAS` (padrão 30): mesmo produto não entra 2x dentro da
janela; depois pode voltar. `--dry` não persiste. Futuro: usar o item_id da
Shopee como chave (mais preciso que o nome).

### 3. Expandir a rede de vídeos (fontes novas)
- Coletar de **perfis "dark" do Instagram** que postam produtos e são
  relevantes (centenas de seguidores) — um coletor de IG análogo ao do TikTok.
- Preferir **fontes sem texto** na tela (a edição fica mais limpa).

---

## 🐞 Observações do dia (2026-07-12) — a resolver

- 🚨 **BUG DE ATRIBUIÇÃO — vendas de TikTok saíam do radar (achado + corrigido 2026-07-13):**
  o `metricas_agent._do_video` reconhecia venda de vídeo pelo `utmContent` usando
  `VIDEO_TAGS` = (hunterradar, telegramrepurpose, hunter, topshop) — mas o pipeline
  PRINCIPAL (produzir_tiktok, 3/dia) gera o link com `sub_ids=["tiktok", termo]`, e
  **"tiktok" não estava na lista**. Resultado: toda venda de vídeo do TikTok era
  classificada como "outros" e o `nichos_quentes`/CEO mostrava `vendas_video=0` —
  podia estar mascarando venda real. **Fix:** "tiktok" adicionado ao `VIDEO_TAGS`
  + `_tags_video()` extensível por `.env` (`VIDEO_SUBID_TAGS=`) + diagnóstico
  `metricas_agent.py --utms` (lista os utmContent crus). ⚠️ Amazon continua fora do
  `conversionReport` da Shopee (programa separado) — sem relatório de venda por ora.

- ✅ **Narração sem áudio (resolvido 2026-07-12):** a chave ElevenLabs está boa
  (TTS ok; o 401 era só no endpoint de saldo). O `produzir_tiktok` narra certo.
  Os vídeos mudos eram sobras de um lote manual/antigo sem Michael (a produção
  PRÓPRIA do daemon está DESLIGADA — `producao_max_videos_dia=0`), já purgadas.
  **Blindagem:** `_narrar_e_trocar_audio` agora manda **alerta no Telegram** (chat
  de admin) quando a narração falha, em vez de cair no original silenciosamente.
- ✅ **Marca d'água VISUAL (resolvido 2026-07-12):** o coletor agora extrai 1
  frame do vídeo-fonte (a ~40%) e o **Gemini Vision** (`_tem_watermark`) detecta
  marca d'água/@usuário/logo de OUTRO criador → **descarta o vídeo** antes de
  produzir. Roda no frame CRU (antes do template TopShop, sem falso-positivo do
  nosso @). Gated por `ANTI_WATERMARK=1`; best-effort (erro/sem key → mantém+loga).
  Fecha o loop de copyright: narração mata o ÁUDIO-crédito, isto mata o VISUAL.
- ✅ **Voz por nicho** (2026-07-12): a narração escolhe a VOZ pelo nicho —
  `ELEVENLABS_VOICE_ID_<NICHO>` (ex.: `ELEVENLABS_VOICE_ID_BELEZA` = voz
  feminina) e cai na `ELEVENLABS_VOICE_ID` (Michael) pra tech/geral. Cada voz
  pode ter settings próprios (`ELEVENLABS_STABILITY_BELEZA`, `_STYLE_BELEZA`…).
  `produzir_tiktok.py` calcula o nicho UMA vez (mesmo sem MULTI_CONTA) e passa
  pra `narracao_ia.gerar(...,nicho)`. Sem `_BELEZA` no `.env` → tudo Michael
  (comportamento antigo, zero regressão). Teste: `narracao_ia.py "produto" "" beleza`.

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
- **1º comentário automático** ✅ FEITO (2026-07-12): logo após publicar, a
  máquina dropa o 1º comentário — POR PLATAFORMA: **Facebook** com o LINK do
  produto (clicável no FB → venda direta), **Instagram** com isca de engajamento
  ("link na bio, comenta EU QUERO" → gera comentários = sinal pro algoritmo).
  `meta_uploader._comentar/_montar_comentario` (gated `ENGAJAR_COMENTARIO=1`,
  best-effort — se faltar permissão, loga e segue). `produzir_tiktok` grava
  `engajamento.json` (link/produto/handle) ao lado do vídeo. Templates editáveis
  via `.env` (`ENGAJAR_IG_TMPL`/`ENGAJAR_FB_TMPL`, placeholders {link}/{handle}/{produto}).
  Permissões Graph: IG precisa `instagram_manage_comments`, FB `pages_manage_engagement`.
  🔜 v2: **Stories** (reshare do reel — precisa URL pública hospedada).
- **Auto-comentários (Stories parte 2)** pro Jarvis (auto-engajamento).
- **Auto-resposta a comentários** ✅ FEITO (2026-07-12): `auto_resposta.py` (cron
  a cada 20min, gated `AUTO_RESPONDER=1`) varre os posts recentes das 3 contas via
  Graph API, acha comentários com GATILHO ("eu quero", "quanto", "link"...) e
  RESPONDE: **FB** com o LINK do produto (pega do nosso próprio 1º comentário do
  post; clicável no FB), **IG** mandando pra BIO. Dedup (`respondidos.json`, TTL 7d),
  cap por rodada (`AUTO_RESP_MAX`), dry-run (`--teste`), nunca responde a si mesmo.
  Gatilhos/templates/janela editáveis via `.env`. Mesma permissão do 1º comentário
  (`instagram_manage_comments`/`pages_manage_engagement`).
  - **Só top-level** (não responde subcomentário): IG usa `/media/comments` (parents)
    sem descer em `.replies`; FB usa `filter=toplevel`.
  - **3 estilos rotativos no IG** (`AUTO_RESP_IG_TMPLS`, sep `|||`): "Feito! Verifique
    suas dms…" / "Te mandei no direct 🥰" / "Corre que o link tá na bio 🚀…".
  - **DM/private reply** ✅ FEITO (gated `AUTO_RESP_DM=1`): manda o link CLICÁVEL no
    direct (`POST /{ig}/messages` recipient=comment_id). Precisa `instagram_manage_messages`.
    Trava anti-mentira: DM desligado → só usa a frase que NÃO promete direct.
- **CEO IA — Conselheiro** 🚧 v1 CONSTRUÍDO (`ceo_agent.py`): lê ledger +
  nichos_quentes, calcula retrato produção×venda + Jarvis Confidence Score (0-100,
  honesto com pouco dado), e o Gemini escreve relatório executivo + propostas
  numeradas (advisory puro). Entrega no Telegram + salva shared/ceo/relatorio_*.md.
  - ✅ **NÍVEL 1 — autonomia supervisionada** (2026-07-13): o CEO gera propostas
    ESTRUTURADAS (motor determinístico do DADO, `_propostas_estruturadas`) mirando
    knobs de uma **whitelist segura** (`SAFE_ENV`: DEDUP_DIAS, toggles de
    engajamento/Amazon/anti-watermark/multi-conta, volumes) com `de→para` concreto.
    O Dre aplica: `ceo_agent.py --aplicar N` (backup do .env + `decisoes.jsonl`),
    reverte com `--desfazer`, audita com `--decisoes`. **Trava de segurança:** só
    mexe na whitelist — NUNCA em token/segredo/id (recusa mesmo propostas.json
    adulterado). Gemini segue escrevendo a prosa; as propostas aplicáveis vêm de
    código (confiável). 🔜 Nível 2: auto-aplicar as de baixo risco quando o
    Confidence subir.
  - ✅ Cron semanal (domingo 09h) já instalado.
  Modo CONSELHEIRO permanece o default. **1º conselho já aplicado:** o CEO apontou que o ledger saía
  'sem_categoria'/'?' → agora `produzir_tiktok` grava SEMPRE categoria (cai no
  nicho), plataforma (shopee/amazon) e nicho da conta. Alertas/relatórios vão pro
  `TELEGRAM_ALERT_CHAT_ID` (privado), não pro grupo público. Modo original:
  CONSELHEIRO (não executivo): lê métricas (`nichos_quentes`, ledger,
  conversionReport), gera um RELATÓRIO + um **Jarvis Confidence Score** e
  **PROPÕE** mudanças (produzir mais de X, cortar perfil-fonte ruim, mudar
  horário, ajustar `_fator_nicho`). O Dre **aprova ou rejeita** — nada é aplicado
  sozinho. Conforme o índice de acerto dele se comprova, liberar **níveis de
  autonomia** (Nível 1, 2, 3…) por tipo de tarefa, rumo a um **conselho de
  agentes**. Modo executivo/admin só quando estiver apto.
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
