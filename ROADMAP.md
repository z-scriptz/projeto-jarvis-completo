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
- **Hook estilo Alana (template TopShop CONGELADO 2026-07-15):** hook de 1–3
  linhas com quebra GULOSA por largura (não vaza pela direita), fonte bold no
  fundo preto + margem anti-corte (`TXT_MARGEM`), emoji colorido escolhido pelo
  PRODUTO. O rodapé do hook fica ANCORADO logo acima do vídeo
  (`VIDEO_Y` − `HK_GAP_VIDEO` − nº de linhas), então 1, 2 ou 3 linhas colam
  sempre certo — sem calibrar `HK_Y` (REMOVIDO do `.env`; um `HK_Y=340` fixo
  travava tudo e cortava a 2ª linha). Ajuste fino SEMPRE via `preview_layout.py`
  (1 frame em segundos, sem gastar narração/crédito). Valores congelados:
  `VIDEO_Y=540` · `HK_GAP_VIDEO=20` · `HK_MARGEM_DIR=100` · `TXT_MARGEM=20` ·
  `HK_EMOJI_DY=6`. **Header (2026-07-16):** `LOGO_X=86` · `LOGO_Y=210` ·
  `LOGO_TAM=118` · `TEXTO_DX=8` (logo colado no nome) · `SELO_DX=28` (selo ✓ fora
  do nome) · `NOME_FONT=52` · `HANDLE_FONT=42`. **CTA:** `CTA_Y=1740` (embaixo do
  vídeo). **Fundo por conta:** geral agora BRANCO (`BG_GERAL=branco`) — o preto foi
  aposentado (header sumia no vídeo). Emoji do hook vai pro fim da ÚLTIMA linha
  (junta `\n` artificial do Gemini) + categoria câmera 📷 / óculos 😎.
  ⚠️ Template FIXO p/ centenas de vídeos — não mexer sem `preview_layout.py`.
  💡 `preview_layout` é FIEL no HEADER (logo/selo/nome); a área do vídeo/CTA ele só
  APROXIMA (retângulo menor que o vídeo real 3:4) — validar CTA no frame real.
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

### 2.4 Produto por VISÃO (Gemini Vision) ✅ FEITO (2026-07-13)
Os canais dark (ex: @promosda.alana) usam hook curiosity-gap ("você precisa ter ISSO
😍") que **de propósito NÃO diz o produto** — então a identificação por TEXTO da
legenda falhava (`0 produtos casados`). Fix: `_termo_por_visao` — quando a legenda
não revela, a máquina **BAIXA o vídeo e o Gemini Vision OLHA** um frame, devolve um
termo de busca PT-BR ('suporte de notebook', 'luminária de flor'…) → aí busca na
Shopee/Amazon normal. Gated `VISAO_PRODUTO=1` (+ GEMINI_API_KEY). O download da visão
é reaproveitado (não baixa 2x) e limpo se descartar. Deixa a máquina achar produto de
QUALQUER vídeo, mesmo sem legenda. Reusa o padrão do anti-watermark.

### 2.5 Hook estilo "curiosity-gap" (aprender com quem vende) 🔜 FORTE
Insight do Dre (2026-07-13) analisando a @promosda.alana: os hooks dela vendem mais
porque **nunca dizem o produto** ("você precisa ter **isso** 😍", "não mostre isso pra
quem ama flores") + **miram a dor/público primeiro** ("Se você trabalha várias horas
em pé…"). Curiosity gap = retenção alta = viraliza. Ensinar o gerador de hook do
Jarvis a copiar essa fórmula (dor/público + "isso" sem revelar o produto). Replicável.

### 3. Expandir a rede de vídeos (fontes novas)
- ✅ **Instagram como FONTE** (2026-07-13): o `tiktok_coletor` agora coleta Reels
  do Instagram na MESMA esteira (yt-dlp cobre os 2). Lê `instagram_perfis.txt`
  (além do `tiktok_perfis.txt`); na CLI aceita `ig:@perfil` ou URL do IG. `_parse_args`
  devolve `(perfil, fonte)`, `_url_perfil` monta `/reels/`, e o `plano.json` grava
  a `fonte` real (tiktok/instagram) p/ o CEO. ⚠️ IG exige **cookies logados**:
  `YTDLP_COOKIES=/root/jarvis/ig_cookies.txt` (ou `YTDLP_COOKIES_FROM_BROWSER=chrome`)
  no `.env` — senão cai no login wall. Dedup + anti-watermark + narração valem igual.
  💡 Nota: os 450 vídeos do Shopee Vídeo do Dre NÃO são exclusivos (mesma fonte
  TikTok que já circula entre afiliados) — descartado como diferencial.
- ✅ **Auto-crop de moldura** (2026-07-13): `_auto_crop` (gated `AUTO_CROP=1`) detecta
  a MOLDURA estática (borda + texto/@ do criador) e corta só a janela do PRODUTO —
  a parte que SE MEXE entre frames (`_detectar_caixa`: std temporal por pixel →
  bounding box). Perfeito p/ canais dark tipo @promosda.alana (produto pequeno com
  borda/texto em volta). Roda ANTES do anti-watermark (o corte já pode tirar o @).
  Best-effort (vídeo cheio → não corta). Tunável: `AUTO_CROP_THR`/`AUTO_CROP_FRAC`.
  Teste: `tiktok_coletor.py --crop-teste video.mp4`. Detector validado com numpy.
- ✅ **Listar perfil do IG via Playwright + stealth** (2026-07-13): `ig_playwright.py`
  abre um Chromium REAL, renderiza o `/reels/` como humano, rola e extrai os links
  dos reels do HTML — contorna o bloqueio de API (graphql 401/403) que derruba o
  instaloader/yt-dlp. Reusa `YTDLP_COOKIES` + `IG_PROXY` (proxy só pro IG). Stealth
  esconde `navigator.webdriver` etc. Coletor usa: Playwright → instaloader → yt-dlp
  (fallbacks) → link direto (curadoria). Provado: Chromium+stealth+extração de /reel/
  OK. VPS: `.venv/bin/pip install playwright && .venv/bin/playwright install chromium`.
  Teste: `python ig_playwright.py promosda.alana 8`. RAM da VPS: 11GB (folgado).
- 〰️ (histórico) instaloader sozinho: `_listar_ig_instaloader`
  enumera os Reels do perfil (o yt-dlp não faz isso de forma confiável) reusando o
  MESMO `YTDLP_COOKIES` (injeta o cookies.txt na sessão do instaloader). Retorna
  URLs de reel; o **download de cada um continua pelo yt-dlp** (que já funciona) +
  auto-crop + anti-watermark. Fallback pro yt-dlp se o instaloader vier vazio.
  Teste: `tiktok_coletor.py --ig-teste promosda.alana`. Precisa
  `.venv/bin/pip install instaloader`. Instagram como fonte agora roda AUTOMÁTICO. 🎉
- Preferir **fontes sem texto** na tela (a edição fica mais limpa).

### 4. Sourcing por FONTE + nichos LARGOS + descoberta autônoma (Alavancas 1 ✅ + 2 ✅)
Insight do Dre: a @topshopbeauty._ está com **0 post** e a tech quase parada. Causa
achada no código: o roteamento é **100% por palavra-chave do PRODUTO**
(`_nicho_da_pasta` → `roteador_contas.nicho_do_produto`), então um Reels do "mundo
feminino" com produto não-beleza cai em **geral** e a beauty passa fome. Nichos não
são só o produto: **beleza = mundo feminino + produtos**; **tech = tecnologia +
games + celulares + produtos**.
- **Alavanca 1 ✅ FEITO (2026-07-16):** rotear pela **FONTE**. `tiktok_coletor`
  lê tag `#nicho` no fim da linha do perfil (`@perfil #beleza`), grava
  `nicho_fonte` no `plano.json`; `produzir_tiktok._nicho_da_pasta` **prioriza o
  nicho da fonte** (cai no produto só se a fonte não declarar). `_BELEZA` alargado
  (mundo feminino/autocuidado), `_TECH` alargado (games/console/celular — SEM
  "tablet" p/ não regredir o NexGard). Fontes tagueadas: 17 `#beleza` + 14 `#tech`
  (o resto sem tag roteia pelo produto). Assim: curar fontes femininas → tudo delas
  vai pra @topshopbeauty, mesmo produto de cozinha.
- **Alavanca 2 ✅ FEITO (2026-07-18):** **descoberta autônoma** — `descoberta_fontes.py`
  varre hashtags-semente por nicho no TikTok, extrai os `@` dos autores, tira os que
  já temos, pontua e escreve candidatos (+ auto-adiciona os fortes com a tag do nicho).
  - **Scraping via navegador real:** o extractor de hashtag do **yt-dlp morreu**
    ("marked as broken / No working app info"), então `ig_playwright.autores_hashtag_tiktok`
    abre `/tag/<hashtag>` num Chromium stealth (reusa proxy + cookies + UA do
    `listar_reels`), rola e lê os `@` dos links `/@user/video/`. Sem captcha nos testes.
  - **Pontuação pelo NOME (a virada):** a frequência entre hashtags colapsou (o feed
    do TikTok é personalizado demais — todo autor aparece 1x), então o sinal que separa
    **vendedor de creator** é o próprio `@`: `_bonus_nome` dá +45 p/ nome de
    produto/afiliado (achadinhos, indica, loja, shop, ofertas, promo, vitrine, tips…)
    e +30 p/ nome do nicho. `score = bonus_nome + freq*18 + views`. Contas de venda
    batem 63/48 (passam no `--auto 60`); creator/gringo/ruído fica em 18 (só revisão).
  - **1ª colheita real (beleza):** 9 auto-adicionados, todos afiliado de verdade
    (`euvinashopee.__`, `achadinhos.noemi`, `achadosincriveiseofertas`, `indica.jheny`,
    `casapraticashop_`, `achadinhosgirls45`…). É ferramenta manual/cron — não posta nada,
    só sugere/adiciona fonte, então é segura. Rodar 2-3x acumula base (dedupe via
    `shared/fontes_descobertas.json`). Falta: rodar `--nicho tech` e `--nicho geral`.
- **Poda por COLETA ✅ FEITO (2026-07-19):** o 1º estágio do funil de fontes. A
  descoberta joga largo (por NOME, sem ver alcance — as views vinham "?"), então
  entrou muita fonte ZUMBI: conta de ~100 views cujo vídeo cai todo no filtro
  (`MIN_VIEWS=50k`), ou IG que só dá 429. O `tiktok_coletor` conta *keepers* por
  fonte e, quando uma passa `COLETA_ZUMBI_RUNS` (3) rodadas SEGUIDAS sem nenhum
  vídeo aproveitável, comenta a linha no `*_perfis.txt` (reversível). Trava:
  só penaliza numa rodada que PROVOU funcionar (≥1 keeper no total) — se a rodada
  inteira flopou (rede/proxy), ninguém apanha. Estado em `shared/fontes_saude.json`;
  `COLETA_PODA_AUTO=0` deixa só contando. **Funil de fontes de 3 estágios:**
  descoberta (larga) → poda por COLETA (corta quem não rende vídeo) → poda por
  VENDA no CEO (corta quem rende e não vende).
  - ⚠️ **Sintoma que motivou (2026-07-19):** produção escassa. Diagnóstico: inbox
    tinha 114 e a fila 52 (máquina viva), MAS a coleta das 03h moía 126 fontes
    (83 TikTok + 43 IG) e a maioria era lixo — as 43 de IG TODAS em 429 (+ sessão
    do instaloader sumida no `/tmp`) e vários TikTok descobertos com ~100 views.
    A poda por coleta limpa isso sozinha em ~3 dias.
  - ✅ **IG consertado (2026-07-19) — era RATE-LIMIT, não cookie:** o `ig_playwright
    --diag` provou que o MESMO perfil voltava 0 reels e depois 12 sem trocar nada no
    cookie (que nem tem `sessionid` — o IG mostra reel de perfil público sem login,
    contanto que não te throttle). A causa era martelar 43 perfis de IG por rodada +
    o fallback yt-dlp do IG (429) queimando o IP do proxy. Conserto SEM cookie novo:
    (1) RETRY do Playwright em 0 (IG é flaky); (2) cortar o fallback yt-dlp que dava
    429 (`IG_FALLBACK_YTDLP=1` religa); (3) `_rotacionar_ig` — máx `IG_MAX_PERFIS_RUN`
    (12) perfis de IG/rodada em janela rotativa (cobre todos em ~4 rodadas); (4) delay
    `IG_DELAY_SEG` (8s) entre perfis de IG. `ig_playwright --diag <perfil>` fica de
    ferramenta (URL/título/cookies/login_duro/midia_bloqueada + screenshot).
- Ordem: Alavanca 1 primeiro (baixo risco, mata a fome da beauty), depois a 2 escala.

### 4.5 Painel de saúde + gargalo da POSTAGEM (2026-07-19)
- **`jarvis_status.py` ✅:** painel num comando (coleta/inbox/fontes/funil,
  produção 7d, fila por conta, postagem 7d, dinheiro). Só lê arquivo local (rápido);
  `--full` cruza fonte×venda na Shopee. Companheiro do período de decantação.
- **Gargalo real da escassez descoberto pelo painel:** produção ~20/dia vs postagem
  **~3,4/dia**. Causa: o daemon postava **1 vídeo por slot** (4 slots = 4/dia TOTAL,
  ordem alfabética), não por conta → cada conta saía ~1/dia. O sourcing (dia todo)
  era pra QUALIDADE/auto-limpeza; a torneira que faltava abrir era a POSTAGEM.
- **Postagem balanceada ✅ (opt-in):** `daemon_maestro` ganhou `post_por_conta`
  (OFF por padrão). Ligado, cada slot posta 1 vídeo de CADA conta que ainda não bateu
  `max_posts_por_conta_dia` → beauty/tech/geral no mesmo ritmo; volume = slots×contas.
  **Rampa recomendada:** teto 2 → 3 → 4-5 conforme as contas (novas) provam que não
  tomam flag de spam. Ligar no `agendador_config.json` (recarrega sozinho; código
  novo precisa `systemctl restart jarvis.service`).
- ⚠️ **Ruído externo visto no log:** Gemini dando **503 UNAVAILABLE** intermitente
  (visão/narração caem pro fallback simples) + alguns renders em **timeout**. Lado
  Google/carga do VPS — não é bug nosso, só conviver; explica parte do "?" de nicho.

### 4.6 Postagem no TikTok via Content Posting API (2026-07-19)
Maior canal de distribuição que faltava (a gente só COLETAVA do TikTok). O antigo
caminho era PyAutoGUI (PC-only) — agora é a **API oficial**, do VPS.
- **`tiktok_painel.py` (Flask):** OAuth (Login Kit, scopes `user.info.basic,video.publish`)
  + Content Posting API (Direct Post, `push_by_file`). Rotas: `/tiktok/login`,
  `/tiktok/callback` (guarda token por conta em `shared/tiktok_tokens.json`, gitignored),
  `/` (conectar + form de post), `/tiktok/postar` (creator_info → init → PUT upload →
  publish_id), `/tiktok/debug` (creator_info bruto). Serve de UI pro review E de motor
  de post pro daemon depois.
- **Infra:** subdomínio `jarvis.topshopoficial.com.br` → VPS; **Caddy** (HTTPS auto,
  Let's Encrypt) → `127.0.0.1:8770`; systemd `tiktok_painel.service`. Registro A + o
  domínio já verificado no TikTok (cobre subdomínio).
- **Legal:** `site_legal/termos.html` + `privacidade.html` publicados no GitHub Pages
  (`topshopoficial.com.br/termos.html`, `/privacidade.html`) — requisito do review.
- **Pegadinhas resolvidas (todas):** (1) sandbox tem client key/secret PRÓPRIAS —
  produção só depois de aprovado; (2) redirect URI tem que estar no Login Kit DO
  SANDBOX, idêntico; (3) app não auditado só posta em conta **privada**; (4) e só como
  **SELF_ONLY** (não `FOLLOWER_OF_CREATOR` — o `niveis[0]` estava errado).
- ✅ **1º post real pela API confirmado** (SELF_ONLY, sandbox) + **review SUBMETIDO
  (2026-07-19) — aguardando resultado do TikTok.**
- ✅ **PRÉ-POSICIONADO pra aprovação (2026-07-19):** `tiktok_poster.py` é o motor
  ÚNICO (token/refresh, creator_info, privacidade auditado→público / sandbox→SELF_ONLY,
  init+upload+status, mapa nicho→conta via `TIKTOK_CONTA_<NICHO>`, CLI de teste). O
  painel foi refatorado pra importar esse motor. O `daemon_maestro._postar_produto`
  ganhou bloco TikTok **gated por `postar_tiktok`** (OFF). **Na aprovação, é só flip:**
  (1) creds de produção no `.env`; (2) conta pública; (3) `postar_tiktok: true` no
  config → TikTok entra no rodízio junto com IG/FB/YT. Zero build.
  - ⏳ multi-conta TikTok: hoje só `@topshopoficial_` conectada (serve todos os nichos).
    Se quiser 1 conta TikTok por nicho, conectar cada uma no painel + setar
    `TIKTOK_CONTA_BELEZA/TECH/GERAL` no `.env`.

### 5. Template do hook — SEMPRE 2 linhas (greedy) ✅ 2026-07-15
Regra fixa: **todo hook é 2 linhas**, linha 1 preenchida até o limite e o resto
DESCE pra linha 2 (greedy), nunca 1 linha só nem corte no meio. A fonte encolhe até
caber em exatamente 2 linhas; frase curta demais recebe corte equilibrado forçado.
Emoji sempre no fim da 2ª linha. (`narrated_video_agent._criar_camadas_topo`.)
Ex.: "O segredo pra ter um iPhone 17 sem gastar / uma fortuna ✨".
- ⏳ **geral (@topshop.__)** ainda saiu no template ANTIGO (fundo preto, quebra
  equilibrada) — precisa do mesmo tratamento/âncora que a tech já tem.

---

## 🗓️ Dia 2026-08-03 — a foto sumida, e o que ela revelou

Começou com "tem produtos sem imagem no site" e terminou descobrindo que eu não
tinha como saber o que está rodando. Cada item tem o commit e a hora em que
entrou na VPS.

**A foto se perdia em 3 pontos** (`e2b43f8`, no ar 12:29). O código da Shopee
nunca quebrou: `buscar_produtos` sempre devolveu `imageUrl`. A foto era
descartada depois — `validar_fila` não copiava do campeão, `curar_fila`
reescrevia a fila inteira do zero com 3 campos (apagando foto/link/preço de
TODOS a cada curadoria), e o `bio_page_builder` escrevia `"imagem": ""` fixo
pra quem vinha da curadoria. Ninguém via porque o `preencher_fotos` (07/07)
vinha tapando o vazamento desde julho. O que mudou foi o volume.

**Pane não pode virar relatório** (`6f74589`, 12:50). Rodar
`python3 -m agents.validar_fila` do terminal não carrega o `.env` — 80 produtos
viraram "deserto" e o relatório bom foi sobrescrito. Agora o validador carrega
o `.env`, se recusa a gravar quando 100% deu deserto, e o `curar_fila` não grava
se aprovar menos de ¼ da fila (antes, zero aprovados = fila vazia, sem trava).

**Busca vazia não é veredito** (`68ae6d1`, 14:13). O validador mandava o nome
inteiro do produto pra Shopee — mediana de 16 palavras nas buscas que voltavam
vazias. Agora retenta com o nome curto, e SÓ quando a busca volta vazia: se a
Shopee devolveu produtos e o corte de qualidade reprovou, o veredito é real.
O extrator virou `shared/termos.py`, compartilhado com a repescagem.
**Desertos 27 → 16, vitrine 80 → 101 produtos.**

**Nome-lixo tinha DOIS produtores** (`db8cae2` 14:31 + `b435f3c` 15:55).
- `tiktok_coletor`: o `_termo_heuristico` corta a 1ª frase da legenda e remove
  palavras funcionais do PORTUGUÊS — numa legenda em espanhol nada casa e a
  frase passa inteira. Reproduzido byte a byte. E o ramo da Amazon (o `elif`
  que recebe o que a Shopee não achou) não verificava nada, só montava a URL de
  busca. Agora `_identificar_produto` devolve `(termo, tem_juizo)` e só termo
  avaliado pelo Gemini sustenta entrada na Amazon.
- `telegram_repurpose_hunter`: o score de cada linha candidata era a CONTAGEM DE
  PALAVRAS, e gancho de venda é mais comprido que nome de produto — daí "2 mil
  vendidos" ganhar de "Suporte celular".

### ⚠️ O que isso ensinou (mais importante que os bugs)

**Eu afirmei "está no ar" o dia inteiro sem ter como verificar.** De manhã eu
disse que só `668f019` estava pendente; o `b435f3c` estava parado havia um dia,
junto com `6f74d22`. O arquivo vivo estava no commit `581b840` e eu não sabia.

Como descobrir (o par de comandos que achou):
```bash
# na VPS
sha256sum integrations/telegram_repurpose_hunter.py | cut -c1-16
# no repo: qual commit tem esse conteúdo
for c in $(git log --format=%h -8 -- ARQUIVO.py); do
  printf "%s %s\n" "$c" "$(git show $c:ARQUIVO.py | sha256sum | cut -c1-16)"
done
```

Isso virou o **`conferir.py`** — roda na VPS, compara arquivo por arquivo contra
o histórico do `pjc` e separa: em dia, atrasado (com quantos commits),
divergente, espelho parado e duplicado. Não escreve nada.

Medido em 03/08: **32 em dia, 2 atrasados, 10 divergentes, 84 espelho parado.**

⚠️ **Correção do mesmo dia, importante pra quem ler isto depois.** Eu li o
"espelho parado" como se o `pjc` estivesse abandonado e cheguei a dizer que os
scripts da raiz "não estão em repositório nenhum". **Errado.** Medido: dos 46
arquivos que eu ia commitar no `agenteia`, **34 já estavam versionados no
`pjc`** — repescagem, tiktok_coletor, deploy_site, postar_grupo,
historico_precos, todos com commits recentes. Só 12 não estavam em lugar
nenhum, e 8 desses são `diag_*`/`teste_*` descartáveis.

Os dois repositórios são **complementares**: o `agenteia` versiona os módulos de
pacote, o `pjc` versiona os scripts da raiz e é onde o trabalho do dia a dia
acontece há 3 meses. "Espelho parado" vale por ARQUIVO, nunca pelo repositório.

**Outra lição, essa sobre método:** eu passei o dia mandando patcher de 100 KB
em base64 por `scp` — e o `DEPLOY.md:219` e o `ROADMAP.md` já documentavam o
caminho certo (`git fetch pjc` + `git show FETCH_HEAD:arquivo.py > destino`).
Também criei um `ESTADO.md` sem procurar antes, duplicando este documento.
**Ler o que já existe antes de construir.**

### Amazon: existia, funcionava, e ninguém chamava (03/08 fim do dia)

O `amazon_playwright.py` resolve link de busca (`/s?k=`) em produto real — ASIN,
preço e foto. Rodando na mão deu 2 produtos legítimos na hora (Capa Motorola
G06 R$ 27,90 · Portfólio Executivo R$ 289,82).

Duas coisas o mantinham parado, e nenhuma era o código:

- **Python errado.** `python3 amazon_playwright.py` falha o import; o playwright
  só existe no venv. É `.venv/bin/python`. Mesma armadilha do `.env`.
- **Ninguém o chamava.** `grep` no projeto inteiro: o único arquivo que citava
  `amazon_playwright` era ele mesmo. Nem daemon, nem cron.

Agora no cron (`setup_cron_jarvis.sh`, com `.venv/bin/python`): `03:40` Amazon.

⚠️ **Errei junto e vale registrar.** Afirmei que o `deploy_site.py` também não
era chamado por ninguém, e cheguei a pôr duas entradas pra ele. Estava errado:
ele já roda **a cada 2 horas** por uma entrada própria do crontab, FORA do
bloco `JARVIS-AUTO`. Eu tinha procurado no `daemon_maestro.py` e no
`setup_cron_jarvis.sh` — nunca rodei `crontab -l`.

**Antes de mexer em automação, `crontab -l` primeiro.** O bloco JARVIS-AUTO não
enxerga o que foi posto à mão, e fora dele já existem: `deploy_site` a cada 2h,
`postar_grupo` a cada 2h, `metricas_agent` 04:30 e `reach_agent` 10:00.

E o freio anti-bloqueio aprendeu a diferença entre "a Amazon caiu" e "esse termo
não é produto": nome-lixo que volta vazio 3x vai pro fim da fila e para de
contar pro freio. Simulado com a fila real — antes os 2 lixos matavam a rodada
antes do primeiro produto; agora resolve 4 de 4 em duas rodadas.

### Auto-resposta: 5 em 5 min, e a janela que nunca existiu (03/08)

Pedido do Dre: responder mais rápido e olhar mais pra trás.

**O `AUTO_RESP_HORAS` era decorativo.** Lido do `.env`, impresso no log como
"janela 48h", e nunca usado pra filtrar nada — `grep` só o achava em 2 linhas.
Quem limitava de fato era o `AUTO_RESP_MIDIAS` (os N posts mais recentes). O
Instagram até pedia o `timestamp` da mídia e o descartava; o Facebook nem pedia
`created_time`.

Agora a janela é real nos dois. Falha pro lado seguro: sem carimbo, carimbo
quebrado ou `--horas 0`, ele OLHA — deixar de responder custa mais que uma
chamada a mais.

**Duas passadas no cron**, porque rodar a janela inteira de 5 em 5 minutos
multiplicaria as chamadas do Graph por 12:

  rápida  `*/5`   · 3 posts por conta, 12h → comentário novo cai no post recente
  funda   `25 2 *` · 130 posts por conta, 30 dias → alcança comentário de um mês

A funda é 1x por dia, não de hora em hora: 130 posts × 24 rodadas passa de 17
mil chamadas do Graph por dia. A conta dos 130: ~4 vídeos por conta por dia ×
30 dias. Com os 25 anteriores ela só chegava a ~7 dias.

⚠️ A janela filtra a idade do **post**, não a do comentário — é o post que a API
lista. Comentário velho mora em post velho, então alcançar 30 dias de post é o
que faz o comentário de um mês ser respondido.

Novos argumentos de CLI `--midias`, `--horas`, `--max` (sobrepõem o `.env`).
Defaults subiram: `AUTO_RESP_HORAS` 48→168, `AUTO_RESP_MIDIAS` 8→25.

⚠️ **Custo medido:** 3.888 chamadas/dia antes → 7.638/dia agora. O limite do Graph
escala com IMPRESSÃO, e as contas ainda são pequenas. Se aparecer erro de rate
limit em `logs/cron_autoresp.log`, baixe o `--midias` da linha de 5min ANTES de
mexer em qualquer outra coisa.

### 4ª conta: @topshopcasa_ (04/08) — e um token trocado que ela revelou

Conta de **casa/decoração**, não "conta da Amazon". O roteador decide por NICHO
(`contas.json` é mapa nicho→conta); uma conta por plataforma exigiria código
novo. E `_NICHOS_VALIDOS` já tinha `casa` desde antes, com lista de palavras
própria e o nicho no prompt da IA — só não havia pra onde mandar, então tudo de
casa caía no `_default`. A conta foi **uma entrada no contas.json**.

  casa · @topshopcasa_ · page 1238524326010430 · ig 17841438142967261
       · PAGE_TOKEN_TOPSHOP_CASA

⚠️ **BUG ACHADO NO CAMINHO.** O `contas.json` mandava a conta **tech** usar
`PAGE_TOKEN_TOPSHOP_CASA` — token da página "TopShop & Casa", que agora serve o
@topshopcasa_. O `page_id` da tech estava certo (1179217661943310 = TopShop &
Tech), só o nome do token estava errado. Corrigido pra
`PAGE_TOKEN_TOPSHOP_TECH`.

O `page_token_env` segue o nome da PÁGINA do Facebook, não do nicho — foi isso
que confundiu. Antes de criar conta nova, rode `diag_contas.py` e confira que
nenhuma conta compartilha token, page_id ou ig_id.

**Perfil-fonte não pertence a conta.** O roteador classifica o PRODUTO, não a
origem do vídeo. Os 9 gringos foram ligados e o que sair deles vai pro nicho
certo sozinho — inclusive `home_appliances513`, `homekitchgadgets1`,
`goodstuffdiary`, `acefastglobal` e `elnazhamai`, que já rodavam no TikTok.

Sem chave `youtube`, a conta cai no token principal (canal geral). Criar o canal
e acrescentar quando for a hora.

### YouTube Shorts: 3x por semana, fora da pirâmide (04/08)

Pedido do Dre: o Shorts entrega diferente do Reels — volume alto divide a mesma
janela de recomendação e derruba o engajamento por vídeo em vez de somar. Então
o YouTube saiu da pirâmide e virou **segunda/quarta/sexta, 1 por conta**.

  `youtube_dias_semana: [0, 2, 4]` · `youtube_max_por_conta_dia: 1`

O Instagram e o Facebook seguem a pirâmide `[3,2,1,3,2,1,0]` sem mudança — a
regra vive no laço de plataformas do `_postar_produto`, não no agendador.

O teto é POR CONTA, não global: as 4 contas são canais diferentes no YouTube,
então short da tech não gasta a vaga da casa. Contador em
`hist["youtube_por_dia"][data][conta]` — chave nova no mesmo arquivo, lida com
`setdefault`, sem migração.

Lista vazia/ausente volta ao comportamento antigo. Como `carregar_config` faz
`dict(DEFAULTS)` e só então sobrepõe o `agendador_config.json`, a regra vale sem
precisar editar o arquivo da VPS.

Canal do YouTube da conta casa: `"youtube": "casa"` → `youtube_token_casa.json`,
criado por `auth_youtube.py casa`. Sem o token ele cai no canal principal.

### Produção pra 4 contas (04/08)

Com a conta casa, a demanda da pirâmide passou de 36 pra **48 posts/semana**
(12 por conta × 4) = 6,9/dia. A produção total já dava conta — o buraco era que
o cron produz POR NICHO e não tinha entrada pra casa: tech 4, beleza 4, geral 3,
**casa 0**.

  `10:00` casa 1 · `14:30` casa 1 → 2/dia pelo cron

Horários escolhidos nas janelas vazias entre os outros renders (cada vídeo
~7min) e fora dos slots de postagem, pra não disputar CPU com o upload.

O **piso do daemon já cobriu 1/dia sozinho**: `_nichos_das_contas()` itera o
`contas.json`, então criar a conta subiu o piso de 3 pra 4/dia sem tocar em
nada. Somado, a casa fica com 3/dia — mesma cota do geral.

⚠️ **Pacote antigo mantém a conta antiga.** A produção grava `conta.json` ao
lado do vídeo e o handle é queimado no render. Os pacotes que já estão prontos
foram roteados quando `casa` não existia, então continuam indo pro
`@topshop.__` — com o handle certo no vídeo. Só o que for produzido daqui pra
frente vai pra conta nova. É o comportamento certo, mas explica por que a conta
demora alguns dias pra encher.

### Pendências pequenas deixadas conscientemente

- `validar_fila`: quando a retentativa também falha, o relatório mostra o motivo
  da 1ª tentativa (nome comprido). O log mostra as duas; o relatório não.
- 3 entradas-lixo ainda na fila + "2 mil vendidos". A vitrine já as esconde e a
  janela rolante (~80) as empurra pra fora. Não apagadas: mexer em dado de
  produção é escolha do usuário.
- Entradas Amazon com link `/s?k=` são busca, não produto — nunca terão foto.
- 5 desertos honestos (nome errado ou nicho): Cerveja "heneinken", Chopp
  ecobier, Hot Wheels 2-Pack, Boné Rabo de Cavalo, Lixeira Suspensa.

### Próximos passos combinados

1. ✅ Sincronizar `telegram_repurpose_hunter.py` (15:55)
2. 🔜 `conferir.py` — só lê, diz o que está rodando
3. 🔜 `deploy.py` — o conferidor com permissão de escrever. Aditivo, com
   backup, nunca reverte (a VPS tem ~262 arquivos não commitados; qualquer
   `checkout`/`reset` ali destrói trabalho)
4. 🔜 Desarmar as duplicatas mortas da raiz (`daemon_maestro.py`,
   `telegram_repurpose_hunter.py`)
5. 🔜 Varrer os ~45 `aplicar_*.py`/`patch_*.py` acumulados na raiz da VPS

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
  **Descoberta (2026-07-13):** as 15 vendas/R$57 do período vêm dos 450+ vídeos MANUAIS
  do Dre no Shopee Vídeo (utm vazio/`----`) — renda passiva do trabalho dele; o
  pipeline automático (IG/FB/YT) ainda não converteu venda rastreada (contas novas).
- ✅ **Atribuição por CANAL (sub_id)** (2026-07-13): esquema padrão de sub_id =
  `[canal, nicho, produto]` (alfanumérico ≤16). `tiktok_coletor` guarda `origem_url`
  no plano; `produzir_tiktok._link_do_canal` gera um link **fb-etiquetado** e põe no
  `engajamento.json` → o 1º comentário do FB (e a auto-resposta que reusa o link)
  saem como `fb-<nicho>-<produto>`, então a venda vinda dali aparece por canal.
  `metricas_agent._canal` decodifica a 1ª etiqueta e o relatório mostra **📡 POR
  CANAL** (fb/ig/tiktok/hunter/direto). Zero patcher (engajamento.json só é lido
  pelo comentário do FB). 🔜 IG por-produto precisa de store media→link (v2, IG não
  deixa link clicável no post).

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

- **TikTok POSTING — fechar o ciclo (futuro, pós-CEO)** 🧠 combinado 2026-07-15:
  hoje a máquina COLETA do TikTok mas posta só no Meta/YT; a evolução natural é
  postar de volta NO TikTok. **Não é agora** (Dre) — só quando a base estiver
  sólida (CEO rodando + atribuição confiável por canal + volume estável nas
  contas novas) e com tempo sobrando, porque a parte pesada é BUROCRÁTICA, não
  código:
  - Exige a **Content Posting API** (TikTok for Developers): criar app, passar
    por **audit/review** da TikTok, começa em *sandbox* (só posta privado/
    rascunho até liberarem o "direct post"). Precisa **domínio verificado** +
    política de privacidade. Leva dias/semanas de vai-e-volta com eles.
  - **OAuth por conta** (cada @topshop autoriza) + refresh de token.
  - **Encaixe limpo quando chegar a hora:** vira só mais um "canal" no
    `roteador_contas`/uploader, ao lado do Meta/YT — o vídeo renderizado é o
    MESMO, muda só o destino do post. Decidir por DADO (o TikTok converte?)
    antes de gastar a burocracia.
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
  - ✅ **MEMÓRIA DE LONGO PRAZO — o loop de aprendizado** (2026-07-16): o CEO
    ganhou "hipocampo" via `memory_agent` (best-effort; funciona sem). **ESCREVE**
    cada relatório + cada decisão aplicada (com snapshot da métrica) na memória
    (`agente=ceo`). **LÊ** relatórios/decisões/veredictos anteriores e injeta no
    prompt do Gemini (não repete conselho; considera o que já rolou). **CONFERE**
    (outcome-check): decisão aplicada há ≥7d compara vendas/comissão do momento vs
    agora → veredito AJUDOU/NEUTRO/PIOROU, marca `conferido` no decisoes.jsonl e
    grava na memória; o veredito entra no relatório. Deixou de ser conselheiro
    amnésico. Confirmado na VPS: cabeçalho mostra `🧠 memória ativa`. Hoje a busca
    era keyword (TF-IDF); ✅ **chromadb instalado (2026-07-16)** — tier vetorial
    leve (embedder ONNX all-MiniLM-L6-v2 ~80MB, SEM torch). Busca agora é
    SEMÂNTICA (acha por significado) p/ CEO + todos os agentes. `backfill_vector.py`
    re-indexou as 15 memórias antigas do JSONL no vetor (senão a busca vetorial as
    perderia). Confirmado: `Fonte: vector`. `chromadb` no requirements.txt.
  - ✅ **APRENDER POR FONTE — fecha o ciclo da descoberta (2026-07-18):** a máquina
    descobre fontes (Alavanca 2), agora sabe **quais VENDEM** e corta as mortas.
    **Atribuição:** a fonte (perfil de origem) vira o **sub_id[3]** do link de
    afiliado (ordem canônica `[canal, nicho, produto, FONTE]`) — `tiktok_coletor`
    grava `perfil_fonte` no plano + no link base; `produzir_tiktok` propaga pro
    ledger e pro link do canal fb; `metricas_agent._fonte(utm)` lê do
    conversionReport. **CEO:** `_analisar_fontes` cruza posts/fonte (ledger) ×
    vendas/fonte (Shopee) → veredito **VENDE / MORTA (≥`CEO_PODA_MIN_POSTS`=6 posts,
    0 venda) / NOVA**. O relatório ganhou bloco "Desempenho por FONTE" e o Gemini
    propõe podar as mortas / priorizar as que vendem. **Poda:** `ceo_agent.py
    --podar-fontes` comenta as mortas nos `*_perfis.txt` (REVERSÍVEL, não apaga);
    `CEO_PODA_AUTO=1` deixa o relatório semanal podar sozinho. Links antigos sem a
    etiqueta de fonte são ignorados — a atribuição acumula com o tempo. Isso mata o
    problema do "gringo-tech" (fonte importada que não converte na Shopee BR) sem
    curadoria manual. ⚠️ precisa de TEMPO: fonte nova só é julgada depois de
    acumular posts+vendas etiquetados (semanas), então a poda é conservadora.
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
- **Padrão de deploy (git-deploy, o `pjc`):** a VPS `/root/jarvis` é um git repo que
  faz `git fetch pjc claude/opa-clau-dgs591` e `git show FETCH_HEAD:arquivo.py > destino`.
  ⚠️⚠️ **O REPO É ACHATADO (tudo na raiz), mas a VPS usa PACOTES.** Deploy no destino
  ERRADO = o código nunca roda (foi o que travou a postagem balanceada por dias:
  editávamos `daemon_maestro.py` na raiz, mas o daemon roda `agents/daemon_maestro.py`).
  **Mapa de destino (SEMPRE conferir com `find` / `ExecStart` antes):**
  - `daemon_maestro.py` → **`agents/daemon_maestro.py`** (o serviço roda `-m agents.daemon_maestro`)
  - `narrated_video_agent.py` → **`agents/narrated_video_agent.py`** (render; import `agents.`)
  - `memory_agent.py` → **`agents/memory_agent.py`**
  - `telegram_repurpose_hunter.py` → **`integrations/telegram_repurpose_hunter.py`** (log `integrations.*`)
  - `shopee_affiliate.py` → **`integrations/`** · builders → **`creative_engine/`**
  - **Raiz** (`~/jarvis/*.py`) só o que roda DIRETO: `ceo_agent`, `produzir_tiktok`,
    `tiktok_coletor`, `descoberta_fontes`, `jarvis_status`, `hook_alana`, `ig_playwright`,
    `tiktok_poster`, `tiktok_painel`, `roteador_contas`, `metricas_agent`, `posts_ledger`.
  - Depois de deployar módulo de pacote: **backup (`.bak`) + `py_compile` + restart** do serviço.
  - ⏳ dívida: `agents/narrated_video_agent.py` está em Jul16 — o fix do emoji ☕ (e outros)
    foi pra raiz e não chegou nele; redeployar em `agents/` com cuidado quando for mexer.
- **Segurança:** nunca colar tokens/segredos no chat; segredos no `.env` da VPS
  / Bitwarden; PAT do GitHub com escopo mínimo.
- **Contas por nicho:**
  - geral: IG @topshop.__ · FB TopShop & Ofertas · YT topshop.oficial
  - beleza: IG @topshopbeauty._ · FB TopShop Descontos · YT topshopbeauty
  - tech: IG @topshoptech_ · FB TopShop & Casa · YT @topshoptech
- **Marcas:** Site `topshopoficial.com.br` · Telegram `@achadinhosrelampagoh`.
