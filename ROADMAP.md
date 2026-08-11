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

### 🔬 EM TESTE até ~18/08: feed misto no @topshopcasa_

**A decidir em 2 semanas.** A conta recebe todo produto do nicho casa, venha da
Shopee ou da Amazon. A dúvida do Dre não era sobre o algoritmo (esse classifica
o CONTEÚDO do vídeo, não o destino do link) — era sobre ESTÉTICA: "achadinho da
Shopee" e "Amazon finds" são formatos diferentes, um é utilidade barata com cara
de promoção, o outro é decoração aspiracional.

Tende a se resolver sozinho: pela experiência dele fazendo o casamento à mão,
produto de amazon finds em geral NÃO existe na Shopee — então o vídeo gringo cai
no `elif` e vira link de Amazon, e o produto BR de casa vira Shopee. Os dois na
mesma conta por serem o mesmo nicho.

Começamos junto porque a conta já tem 27 produtos de casa prontos, e restringir
agora a deixaria parada justamente quando volume mais ajuda (conta nova).

**Se o feed ficar incoerente:** rotear por plataforma dentro do nicho casa —
Amazon fica no @topshopcasa_, Shopee de casa volta pro @topshop.__. É código
pequeno. **Se funcionar:** mantém e não mexe.

### WhatsApp: grupo automatizado por navegador (04/08)

`whatsapp_playwright.py`. **Decisão de risco tomada pelo Dre com a condição de
ser conservador** — e vale registrar por quê, pra ninguém "otimizar" depois:

O WhatsApp NÃO tem API oficial pra postar em grupo. A Cloud API da Meta é pra
conversa 1:1 com quem optou por receber; grupo não está na superfície dela. Isto
automatiza o WhatsApp **Web**, o que contraria os termos — e número banido leva
junto o grupo e o contato comercial.

O que derruba número é **volume e padrão de robô**, não a automação. Daí as
travas, todas por `.env`:

  `WHATSAPP_ATIVO=0`   desligado por padrão
  2/rodada · 6/dia · janela 07–21h · pausa 45–120s · digitação lenta

Para na primeira dúvida: sessão caída, grupo não achado ou seletor que sumiu →
print em `shared/whatsapp_erros/` + aviso no Telegram privado, e encerra. Nunca
clica adivinhando.

**Login:** `--login` tira print do QR e MANDA PRO TELEGRAM (a VPS não tem tela).
Sessão persistente em `shared/whatsapp_sessao/`.

⚠️ O WhatsApp Web troca marcação sem aviso e sem versão. Cada elemento tem
vários seletores; quando o print de erro chegar no Telegram, é sinal de que
`SEL_BUSCA`/`SEL_CAIXA` precisam de revisão. **É manutenção esperada, não bug.**

Fora do cron de propósito até o Dre validar as primeiras rodadas à mão.

**Primeira quebra e o que ela ensinou (04/08).** O `--teste` parou em "não achei
a caixa de busca". A tentação era trocar o seletor no escuro; em vez disso o
`--diag` foi escrito pra *olhar*, e o print que o Telegram mandou resolveu antes
mesmo de rodar: um **"Novidades do WhatsApp Web"** aberto por cima da interface,
com botão Continuar. A busca e o grupo estavam atrás dele, corretos. Ou seja,
**os seletores nunca estiveram errados** — `wait_for_selector(state="visible")`
é que falha quando o elemento está atrás de um modal. É a mesma lição do dia
inteiro: medir, não adivinhar. Aqui, o print É a medição.

`_fechar_modal()` roda logo depois do login ser detectado. **Só clica em botão
que esteja DENTRO de um `role=dialog` E cujo texto esteja numa lista curta**
(Continuar, OK, Entendi, Agora não...). Diálogo desconhecido ele registra e não
fecha — clicar em qualquer botão de qualquer diálogo é aceitar termo sem ler, e
um dia o diálogo é "sair de todos os aparelhos?".

O mesmo print revelou um segundo problema *antes* de ele acontecer: o grupo é
**"💭 ACHADINHOS VIP TOPSHOP"**, com emoji no nome. `keyboard.type` não emite
caractere fora do BMP de forma confiável (emoji é par surrogate) e um emoji
digitado errado zera a busca → `_digitavel()` digita só o texto legível. E
`span[title='...']` exigia o nome byte a byte → `_achar_grupo()` tenta o exato e
depois aceita título que *contenha* o texto legível. Nunca "o primeiro
resultado": isso é mandar achadinho pra conversa errada.

Detalhe que morde: o seletor exato usa `json.dumps(..., ensure_ascii=False)`. No
padrão o json troca o emoji por escapes barra-u e o **CSS lê aquilo como escape
hexadecimal**, casando com nada.

**Segunda quebra, 15:39 do mesmo dia.** Modal já não aparece — o
`_fechar_modal` resolveu. Mas a busca continuou sem casar, e o print mostrou o
motivo: **layout novo do WhatsApp Web** (o painel direito passou a oferecer
"Enviar documento / Adicionar contato / Perguntar à Meta AI"). Todo `SEL_BUSCA`
por `data-tab` morreu junto. **Perseguir `data-tab` é correr atrás de alvo que
muda sem aviso e sem versão** — então a resposta não foi um seletor novo:

1. **Abrir pela LISTA, antes da busca.** No print o grupo está no topo do painel
   lateral, visível sem pesquisar nada. `_abrir_grupo()` clica direto e não
   depende de caixa de busca nenhuma — que é justo a parte que o WhatsApp mais
   mexe. **A busca virou o caminho B.**
2. **Perguntar pelo nome acessível.** O que não muda é como o campo se
   apresenta: "Pesquisar ou começar uma nova conversa". `_achar_busca()` tenta
   os CSS conhecidos e depois pergunta por papel/placeholder/título com regex —
   funciona seja `<input>`, contenteditable, ou o que inventarem depois.

`_achar_grupo()` varre do escopo específico ao amplo (`#pane-side` → listitem →
grid → `span[title]` da página). Varrer amplo é seguro **aqui** porque a escolha
é por comparação de título: ou casa com o nome do grupo, ou é ignorado.

O `--diag` deixou de filtrar: despeja `input`/`textarea` inteiros e todo
`placeholder`. Se a busca virar um `<input>` sem aria-label, filtrar por
"pesquisa" a esconderia — **o ponto de uma medição é não esconder.**

**O `--teste` passou** — `grupo aberto direto da lista (sem busca)`. E, por ser
seco, mostrou o que ia pro cliente antes de ir:

    *Produto com busca alta*
    💰 R$ 1600,00

Rótulo interno que vazou pra fila. **Eu tinha afirmado que a vitrine escondia
isso — estava errado.** O `_nome_ruim` do `bio_page_builder` só reprova nome com
menos de 3 palavras de 3+ letras, e esse tem 4. O `_e_lixo` do `telegram_radar`
só olha selo de venda e aviso de grupo. **Cada superfície tinha meia regra;
nenhuma tinha esta** — e o WhatsApp é a primeira que manda o nome cru pro
cliente, então foi lá que apareceu.

`shared/termos.py` ganhou **`nome_de_produto_ruim()`**. A pergunta que ela faz
não é "o nome é curto?" e sim **"sobra alguma palavra que diga O QUE É a
coisa?"** — tira ligação (com, para) e palavra de funil (produto, busca, alta) e
vê o resto. "Produto com busca alta" resta 0; "Gloss Labial" resta 2.

Corte de palavra única **medido, não chutado**: com ≥6 letras o "Tênis" era
reprovado, e tênis é produto. Com ≥5 passam Tênis/Bolsa/Calça e reprovam
Fone/Capa/Copo. 32 casos, 0 falhas.

Mora em `shared/` e é **importada, nunca copiada** — regra duplicada é a
armadilha que já mordeu este projeto. Import falhou → `_candidatos` devolve
vazio e nada é enviado. **Vale a regra de quem publica: pular um produto bom
custa menos que mandar lixo pro grupo do cliente.**

Vale reusar `nome_de_produto_ruim()` no `telegram_radar` e na vitrine quando der
— hoje não mexi neles pra não tocar caminho de ingestão que está funcionando.

Preço também ganhou ponto de milhar (`R$ 1.600,00`): é o número que decide a
compra e sem separador ele some no meio da mensagem.

**Os 2 primeiros posts reais saíram — e prestaram pouco.** Link solto, sem
foto, sem legenda, sem preço, nome cortado no meio. **Tecnicamente funcionando e
comercialmente inútil**, que é um jeito de falhar que teste nenhum pega: só
quem olha o grupo como cliente enxerga.

  **Foto** — a fila já EXIGIA `imagem` pro item ser candidato, e o script não
  usava o dado. `_baixar_foto` + `_enviar_com_foto` (input escondido,
  `set_input_files`, sem abrir menu). **Sem curinga `input[type=file]`**: o
  WhatsApp tem mais de um e um é o de DOCUMENTO — foto por ali vira anexo de
  arquivo, pior que sem foto. Não casou → cai pro texto.

  Contrato: **`_enviar_com_foto` devolve False só quando NADA foi enviado.** Se
  devolvesse False depois de já ter mandado, o texto iria junto e o grupo
  receberia o produto duas vezes. Por isso a prévia é esperada antes de digitar.
  E a caixa de legenda é OUTRA que a da conversa — errar de caixa manda legenda
  solta e foto muda.

  **Legenda** — mesma FORMA do `telegram_poster._montar_legenda`, de propósito:
  as duas comunidades são do mesmo dono e recebem os mesmos produtos. Formato
  diferente por surface faz quem está nos dois achar que são revendas
  diferentes. Muda só a marcação (`*negrito*`, URL crua).

  **Nome** — passou a preferir o **título oficial da Shopee**, que o
  health-check já guardava em `precos_historico.json` e ninguém usava. Corte de
  70 → 110: em 70 o "Kit 4 Essência 10ml Para Aromatizador Difusor
  Umidificador…" morria no meio.

  **Preço** — três fontes: item → curadoria → histórico do health-check. **A
  mesma da vitrine**, que é o ponto: preço divergente entre as duas é pior que
  preço ausente, porque o cliente vê as duas. Zero rede nova.

Confirmado no seco de 04/08: `COM foto`, R$ 54,00 e R$ 75,00 vindos do
histórico, títulos oficiais inteiros.

**Lacuna registrada, não resolvida:** a fila não guarda preço na ingestão —
`postar_grupo.py:163` manda `"preco_real": ""` com esse comentário, ou seja **o
grupo do Telegram posta sem preço desde sempre**. Não é defeito do WhatsApp; ele
só tornou visível. O conserto de verdade é gravar o preço quando o produto entra
na fila. Trabalho separado, de propósito.

**Não testado ainda:** o caminho da foto exige WhatsApp Web de verdade. Escrito
pra degradar, não quebrar: falha em download/anexo/prévia → texto.

**DESLIGADO em 04/08 (`WHATSAPP_ATIVO=0`) e a razão importa.** O número que
estava rodando era o **pessoal do Dre** — família, 99+ conversas. O risco de ban
não mudou; o **custo** dele é que era outro. Perder o grupo de achadinhos custa
um chip; perder o WhatsApp pessoal não tem recurso nem backup.

Fica esperando um número dedicado. O aparelho **não tem eSIM**, mas tem **dois
IMEIs** = dois slots físicos, com o slot 2 livre. Caminho: chip pré-pago
comprado online, entregue em casa (1–5 dias), ativado pelo app com CPF, e o
WhatsApp Business no segundo número — os dois convivem no mesmo aparelho.

**Nunca usar serviço de aluguel de número/SMS** (sms-activate, 5sim e afins): o
número é reciclado e volta pro pool, então quem pegar depois recupera a conta
com o grupo e os clientes junto. Troca "posso perder o número" por "outra pessoa
vai receber o número" — pior que o problema original.

### O crontab estava rodando TUDO multiplicado (04/08)

Começou com "por que o Telegram está quadruplicando os achadinhos?". A fila
estava limpa (0 nomes e 0 links repetidos em 80 itens) — descartou a hipótese de
coleta duplicada **pelo dado, não por argumento**. A causa estava no `crontab`:

    8x  ceo_agent.py
    5x  auto_resposta.py (*/20)
    4x  tiktok_coletor, produzir_tiktok, amazon_playwright,
        metricas_agent, reach_agent

Não era só o `postar_grupo`. **Coletor puxando 4x a cota da API, produção
rendendo 4x os vídeos** — e ninguém tinha percebido.

**O que atingiu cliente foi o `auto_resposta`.** Ele carregava
`respondidos.json`, marcava em memória e só gravava no fim. As 5 cópias liam o
arquivo antes de qualquer uma gravar → **quem comentou recebeu até 5 respostas
iguais.**

`shared/trava.py` (flock, `rodar_unico()`) entrou nos 8 pontos de entrada.
**flock e não arquivo de PID**: o kernel solta o flock quando o processo morre,
inclusive com `kill -9` ou reboot. PID sobrevive ao crash e trava tudo até
alguém apagar na mão — em vez de postar 4x, para de postar e ninguém percebe.
**Trocar um defeito barulhento por um silencioso é piorar.**

Segunda instância sai com **código 0**. Não falhou: achou trabalho em
andamento. Código de erro faria o cron mandar e-mail de falha a cada 5 min.

No `auto_resposta`, mais duas: `_salvar_respondidos` virou **atômico**
(`write_text` ZERA o arquivo antes de escrever, e vazio ali significa "nunca
respondi ninguém"), e grava **a cada resposta**, não só no fim.

**Limpar o crontab resolve o caso; a trava resolve a classe.** Crontab é editado
à mão e vai duplicar de novo.

#### A causa: uma crase num comentário (04/08, resolvido)

Linha 53 do `setup_cron_jarvis.sh`, **dentro** do `BLOCO="..."`:

    # chamada de API. Confira com `crontab -l` antes de acrescentar qualquer coisa

`BLOCO` é string entre **aspas duplas**, e **crase dentro de aspas duplas é
substituição de comando**. O bash executava `crontab -l` e colava o crontab
inteiro dentro do próprio bloco. Toda execução do script.

A assinatura ficou no crontab e foi ela que entregou o caso:

    # JARVIS-AUTO-END antes de acrescentar qualquer coisa

É o **fim do crontab embutido** grudado no texto que vinha depois da crase.
Reproduzido em teste isolado: sai idêntica, com 2 BEGIN num bloco que deveria
ter 1.

A conta fecha: **3 execuções no histórico do shell → 4 cópias**, e foram 4 BEGIN
encontrados. E explica o que a teoria do "bloco se reinserindo" não explicava:
`postar_grupo`, `metricas_agent` e `reach_agent` são entradas **manuais**, fora
do bloco, e mesmo assim estavam 4x — vinham de carona no crontab embutido.

**O detalhe que dói:** o cabeçalho dizia *"Idempotente: pode rodar de novo sem
duplicar"*. Era falso e passou semanas assim, porque o script **sempre**
terminava imprimindo "✅ cron instalado" — ele nunca olhou o que acabara de
escrever. **Script que só sabe dizer que deu certo não é verificação.**

Trocar a crase conserta a ocorrência. Pra fechar a classe, entraram três
conferências: antes de gravar exige 1 BEGIN + 1 END e no máximo 60 linhas de
tarefa; **depois** de gravar confere o crontab resultante e avisa se sobrou mais
de um bloco. Testado com o bloco defeituoso (aborta sem tocar no crontab) e com
o corrigido (grava). Confirmado na VPS: `grep -c JARVIS-AUTO-BEGIN` → 1.

⚠️ **Nunca use crase dentro do `$BLOCO`, nem em comentário.** O aviso está em
caixa alta no topo do `setup_cron_jarvis.sh`.

### Mercado Livre como 3ª loja — levantado, não construído (04/08)

**Não existe API oficial de afiliados.** O Developer Portal do ML documenta
pedidos, opiniões, perguntas, lojas oficiais — **nenhuma seção de afiliados**, e
há reclamação formal registrada com esse título. As "APIs de afiliado ML" que
aparecem em blog são de terceiros (scraper ou automação de painel), não do ML.
Comissão anunciada: até 16%.

**Conta criada em 04/08** — perfil "TOPSHOP", **etiqueta `topshop2413`**. A
ferramenta é o **"Gerador de produtos recomendados"** (Central de afiliados →
Ferramentas → Gerador de links): recebe uma ou mais URLs de produto, uma por
linha, mais a etiqueta, e devolve os links. Aceitar VÁRIAS URLs de uma vez é
bom sinal — é o formato de quem tem back-end de geração em lote.

**MEDIDO em 04/08 — e deu o resultado inverso do esperado.** O link do "Gerador
de produtos recomendados" (`meli.la/2gy5qtz`) redireciona 301 para:

    mercadolivre.com.br/social/topshop2413
      ?matt_word=topshop2413&matt_tool=35246996&forceInApp=true&ref=<TOKEN>

**Não aponta pro produto.** Aponta pro PERFIL SOCIAL do afiliado; o produto
está dentro do `ref=`, um token opaco gerado no servidor. Duas conclusões:

  1. **Essa ferramenta não serve pro nosso caso**, mesmo se fosse automatizável:
     o cliente cai no perfil e ainda precisa achar o produto. Um clique a mais
     entre o vídeo e o carrinho.
  2. **`ref=` não é construível.** Por concatenação, essa via está fechada.

**A outra ferramenta foi testada e dá no MESMO lugar.** O "Gerar link / ID de
produto" (botão *Compartilhar* de cada produto no hub) devolveu
`meli.la/33F2j7h`, que redireciona 301 para o mesmo
`/social/topshop2413?...&ref=<TOKEN>`. **Todo link de afiliado do ML passa pelo
perfil social com token opaco.**

**VEREDITO: não dá pra montar link de afiliado do ML por concatenação.** Ao
contrário da Amazon (`?tag=SUATAG`, custo zero), aqui cada link precisa ser
gerado no painel. Consequências:

  - O ML **não entra no fluxo automático** como Shopee e Amazon entram.
  - Automatizar o painel com navegador é tecnicamente possível, mas é a mesma
    classe de risco do WhatsApp Web — com a diferença de que uma conta de
    afiliado banida custa muito menos que um WhatsApp pessoal. **Decisão pra
    depois, não agora.**
  - Existe também o **"ID do produto"** (ex.: `TJH03T-TZPA`), que a pessoa cola
    no buscador do ML. Não serve pra link clicável em vídeo.

**Enquanto isso, ML = curadoria manual.** A vitrine já sabe exibir `meli`
(filtro + selo), então produto colado à mão na fila aparece certinho.

⚠️ Mesmo se a concatenação parecer funcionar, **testar com uma venda real** —
link que não credita é trabalhar de graça e só aparece no extrato. Se o link for a URL do produto + parâmetro de rastreio
(`matt_tool`/`matt_word`), dá pra montar link por concatenação — que é
exatamente como a Amazon funciona aqui (`?tag=SUATAG`, sem PA-API,
`tiktok_coletor.py:34`). Se for um short link opaco gerado no servidor, só o
painel gera, e aí a automação sairia cara demais pro retorno.

⚠️ **Não presumir que o parâmetro credita.** Promover produto com link que não
credita é trabalhar de graça sem saber. Testa com uma venda antes de escalar.

**O que já está pronto:** o filtro da vitrine lista `("meli", "Mercado Livre")`,
e o selo de loja virou tabela (`LOJAS`/`_loja`) — antes era
`"Amazon" if plat == "amazon" else "Shopee"`, que rotularia produto do ML como
Shopee.

**O que falta, medido:**

  1. `tiktok_coletor` — a cascata é Shopee → Amazon → descarta. Falta o ramo ML.
  2. Geração de link — um `meli_afiliado.py`; depende da medição acima.
  3. `validar_fila`/`repescagem` — chamam `minerar_oportunidades`, que é Shopee.
     Produto ML não é validado nem repescado.
  4. `historico_precos` — o preço vem do health-check da API da Shopee. Produto
     ML entraria **sem preço**, igual a Amazon hoje.
  5. Roteador/`contas.json` — decidir qual conta recebe produto do ML.

**Recomendação:** não abrir esta frente antes de fechar o WhatsApp (chip
chegando ~08/08) e antes da avaliação de 2 semanas do feed misto do
`@topshopcasa_` (~18/08). A Amazon ainda está em teste; abrir uma terceira loja
com a segunda não avaliada é multiplicar variável sem ter medida de nenhuma.

### CURSO "AFILIADO ONLINE" — o que ele É

> ⚠️ Isto está escrito aqui porque em 04/08 eu **perdi essa informação numa
> compactação de contexto** e tive que recuperá-la da transcrição da sessão. O
> Dre tinha pedido, semanas antes, que tudo fosse salvo em arquivo justamente
> pra isso não acontecer. **Decisão de produto que só existe no chat está
> perdida** — só ainda não se sabe quando.

**Promessa:** construir uma renda online de forma prática, **sem precisar
aparecer** (formato *faceless*).

**Posicionamento, e ele é deliberado:** é um **método/sistema passo a passo**,
**não** promessa de ficar rico rápido. A honestidade sobre resultado é parte da
oferta, não ressalva de rodapé — a Aula 3 inteira é sobre isso ("ninguém pode
garantir resultado", "os primeiros vão ser ruins", "meta de processo, não de
resultado"). **A página de vendas tem que soar como isso.** Copy de promessa
fácil contradiz o produto e queima a confiança que o curso constrói.

**Dor de entrada (Aula 1):** a pessoa quer renda online mas trava em três
coisas — *"não quero aparecer"*, *"não tenho tempo"*, *"não sei por onde
começar"*.

**Módulo 0 — 3 aulas prontas:**

  1. **Bem-vindo** — a trava, a boa notícia (dá pra fazer sem aparecer e no
     automático), o que o curso é e o que não é, como aproveitar.
  2. **A máquina que você vai construir** — "você não cria, você **conecta**" ·
     vídeos que não mostram você · alcance é **volume**, não sorte · do vídeo
     até o checkout · repita o que o **número** aprova · sozinha nenhuma peça
     funciona.
  3. **A mentalidade que sustenta o resultado** — volume, não sorte · os
     primeiros vão ser ruins · ninguém garante resultado · meta de processo ·
     compare com você de ontem.

**Onde mora:** branch `claude/curso-video-aulas`, pasta `curso/remotion/`
(**PR #2**). Slides em código (Remotion), narração ElevenLabs — o MP3 por slide
vai em `curso/remotion/public/` e a duração se ajusta sozinha
(`node scripts/narrar.mjs Aula1`).

**Marca do curso é OUTRA que a da vitrine:** verde escuro (`#0c1512` / `#07100c`)
com dourado (`#d8b25a` / `#f0d79a`). A vitrine é rosa choque. **Não misturar** —
a página de vendas usa a paleta do curso.

**Pendente:** gravação de tela de ~30s do painel de afiliados da Shopee, pro
Módulo 1.

**Falta pra escrever a página de vendas** (só o Dre tem): **preço**, **URL do
checkout da Hotmart**, e o que os módulos PAGOS entregam (o Módulo 0 parece ser
a porta de entrada).

### CURSO: páginas próprias fora da Hotmart (pedido em 04/08)

O Dre quer sair das páginas padrão da Hotmart. Três peças, e elas **não têm o
mesmo grau de liberdade** — o que decide a ordem de fazer:

  1. **Página de vendas** — a que os afiliados divulgam. **Liberdade total**,
     pode morar no nosso domínio. É a que dá mais retorno e a que não depende
     de ninguém. **Começar por aqui.**
  2. **Página do produto** — a que a Hotmart gera. Substituível pela de vendas:
     o link de afiliado aponta pra nossa página, e ela leva ao checkout.
  3. **Página de pagamento (checkout)** — ⚠️ **aqui NÃO há liberdade total.**
     Quem processa cartão e Pix é a Hotmart, e checkout próprio de verdade
     significaria virar gateway (PCI, antifraude, chargeback). O que existe é
     personalização dentro do que a plataforma permite. **Verificar o que o
     plano do Dre libera ANTES de prometer qualquer coisa** — nunca desenhar um
     checkout que a Hotmart não deixa publicar.

Ponto de atenção que vale mais que o visual: **o link de afiliado tem que
sobreviver ao caminho todo.** Se a nossa página de vendas perder o parâmetro de
afiliado no meio, o afiliado divulga, a venda acontece e ele não recebe — e
descobre pelo extrato, semanas depois. É a mesma armadilha do Mercado Livre
anotada acima: **testar com uma venda real antes de escalar.**

Reaproveita o que já existe: `bio_page_builder.py` já gera página estática
responsiva com tema claro/escuro e `deploy_site.py` já publica. A página de
vendas é o mesmo maquinário com outro conteúdo — não é começar do zero.

### Espelhamento: regra que o Dre quer (04/08, adiado por ele)

Hoje é binário: tem texto → não espelha. O que ele pediu é mais fino:

  - vídeo **sem texto** → pode espelhar (diferenciação, como hoje)
  - vídeo **com texto** → não espelha (como hoje)
  - vídeo **com @ de outro perfil** → **espelha de propósito**, pra atrapalhar
    a leitura do @ alheio e proteger o direito autoral do vídeo dele

O terceiro caso inverte a regra: hoje o `@` conta como "texto" e BLOQUEIA o
espelhamento — justo o oposto do que ele quer. Vai exigir separar, no OCR, o
que é hook (texto que deve ser preservado) do que é arroba (texto que deve ser
embaralhado). Provavelmente por regex de `@\w+` no resultado do Tesseract.

**Adiado a pedido dele** ("veremos isso outra hora, com calma"). A correção da
amostragem de 04/08 já resolve o sintoma que doía (texto invertido no ar).

### Raio-x de 08/08 — o que 3 dias sem sessão revelaram

`raio_x.sh` (read-only, 10 blocos) e `conferir_esteira.py` nasceram aqui. Rode
os dois antes de perguntar "como está o Jarvis" — economizam 10 idas e voltas.

**A COLETA DO INSTAGRAM ESTAVA MORTA HÁ DIAS.** 673 erros no `cron_coletor.log`.
Causa final: **o `.env` tinha o nome da conta errado** — `INSTALOADER_USER=sxrwping`
quando a conta é **`sxrwpingg`, com dois "g"**. O código pedia a sessão de um
usuário que não existe, caía no caminho padrão (`/tmp`, que o sistema limpa) e
o log dizia "falhou" em vez de "não existe". Corrigido no `.env`; a sessão
precisa ser gerada **no PC do Dre**, nunca na VPS (o IG barra login de IP de
datacenter — duas contas tomaram checkpoint tentando).

⚠️ **Conta de scraping é descartável, como o chip do WhatsApp.** O
`@topshopmoda_` foi usado numa tentativa e tomou checkpoint. Nunca usar conta
que é marca.

**HIPÓTESE ERRADA, REGISTRADA PRA NÃO SE REPETIR:** eu achei que vídeos eram
renderizados pra uma conta e postados em outra, por causa do `or "geral"` em
`daemon_maestro:1102-1117`. **Medido: 241 pacotes, 241 com `conta.json`, zero
sem.** O roteamento está correto. O defeito real era só a logo: 1 pacote de
casa renderizado antes de a `logo_ts_casa.png` chegar (04/08 19:08).

**Alarme falso meu #2:** `agente.log` com "11.109 ❌" — o símbolo está no RÓTULO
`❌ 0 erro(s)` das linhas de resumo. Grep de símbolo não distingue rótulo de
ocorrência.

**Alarme falso meu #3:** "0 vídeos postados hoje" era o contador de PRODUÇÃO
(`vídeos hoje: 0/9`), e ele está em 0 porque o estoque está cheio — o sistema
funcionando como projetado.

**As travas em disco NÃO ficam presas.** `flock` é solto pelo kernel quando o
processo morre; o arquivo `.trava_*` fica, o cadeado não. Não apagar.

#### O desequilíbrio que sobrou (não resolvido)

    produção  ~16-18/dia        postagem  ~9/dia        esteira  241 pacotes

Cresce ~8/dia. O mais antigo tem 16 dias; **nada apodreceu ainda** (0 acima de
30 dias), mas chega sozinho em duas semanas — e vídeo com link morto é pior que
vídeo nenhum. As cotas do cron (tech 4 · beleza 4 · geral 3 · casa 2) foram
calibradas **quando a produção rodava em quádruplo** pelo bug do crontab, ou
seja, com o número errado na tela.

Recomendado: **cortar produção pela metade** até a esteira cair pra 60-80.
**Exceto `casa`**, que tem só 13 pacotes e é a conta que o Dre quer crescer.

**Composição da fila:** geral 120 · tech 61 · beleza 47 · casa 13. Metade em
"geral" significa que o classificador não está decidindo — e produto em geral é
produto que não foi pra conta especializada, onde converteria melhor.

### PRODUTOR ORIGINAL — começou em 08/08

**Por que existe.** Os 133 posts medidos deram engajamento SAUDÁVEL (3-5%) com
alcance BAIXO (mediana 116). Conteúdo que ressoa e não é distribuído é a
assinatura do que a plataforma trata como **material reciclado** — e o pipeline
hoje é: pegar vídeo de outro perfil, reeditar, publicar. Não dá pra provar sem
comparar contra original, e é isso que o experimento vai fazer.

`storyboard.py` — **só JSON, não renderiza nada.** Roteiro burro se descobre em
segundos; vídeo burro custa render. Traz o dado dentro: hook em 1ª pessoa,
"A Shopee:" e urgência PROIBIDOS pelo validador **com o número na mensagem de
erro**, pra quem for "consertar" isso um dia saber o que está desfazendo.

Regras que vieram de defeito real, não de teoria:

  **só pede imagem que EXISTE** — storyboard com 6 cenas pra produto com 2
  fotos é documento bonito e irrealizável, e só se descobriria no render.

  **CTA tem que conter "bio"** — o 1º roteiro dizia "Garanta já o seu kit!".
  Garanta onde? No IG só a bio é clicável. Soava bem e não instruía.

  **narração continua a história do hook** — o Dre aprovou 6 de 8 e apontou
  "parece comercial". O padrão: hook em 1ª pessoa, narração vira locutor
  ("Conheça a saia que une...", "Apresento..."). O vídeo começa conversa e
  vira propaganda no segundo 3, jogando fora o que a medição premiou.

  **modelo determinístico como piso** — roda sem chave de API e serve de
  régua: se a IA não superar o modelo base, não vale a chamada.

  **`origem: "original"` em todo roteiro** — é o experimento. Sem esse campo,
  daqui a um mês não dá pra separar original de reciclado, e o A/B vira opinião.

**Avisos ≠ reprovação.** Eficácia no corpo e alegação regulada AVISAM, nunca
bloqueiam: a regra do Dre é pesquisar o produto antes e tirar a frase se ele
não entregar. A mensagem serve esse processo em vez de discutir com ele. E o
aviso de "experiência pessoal" foi ESTREITADO a pedido dele, com razão —
"minha pele é oleosa e adorei a textura" é voz de marketing, não fraude.

**Fora de propósito: quality gate com nota 0-10.** Modelo dando nota ao próprio
roteiro é opinião com casa decimal, e raramente reprova a si mesmo. O validador
só checa o VERIFICÁVEL. Nota entra quando houver correlação medida entre ela e
o alcance real — aí vira preditor, não achismo.

**Próximo passo:** storyboard → EDL → FFmpeg. Só depois que a rodada nova
mostrar a narração corrigida.

### EDL — decisões de arquitetura antes de codar (08/08)

**A melhor ideia da rodada, e ela é adotada:** o storyboard diz **O QUE**
comunicar; o EDL decide **COMO**. São dois cérebros, não um.

    storyboard  { narracao, intencao: "demonstracao", energia: "alta",
                  prioridade_visual: "produto_em_movimento" }
    EDL         { inicio, fim, assets[], zoom, cut_points[], caption_style, sfx }

Isso não é elegância: é o que permite trocar FFmpeg por outro renderizador, ou
gerar corte diferente pra Reels e TikTok, **sem mexer no cérebro criativo**. E é
a mesma separação que já salvou este projeto — `shared/termos.py`,
`shared/categorias.py`, `shared/marca.py`: regra num lugar, uso em vários.

**A narração comanda o corte, não o cronômetro.** Cortar a cada N segundos vira
slideshow. O corte cai onde o SENTIDO muda: "ele gira" → produto; "acende as
luzes" → a foto onde as luzes aparecem. A gente já gera `narracao` por cena;
falta os `cut_points` seguirem as batidas dela.

**Ritmo por seção:** hook com corte rápido (0,8-1,5s), demonstração com tempo
pra ver, CTA estável. Vídeo sem respiração cansa.

**UM PILOTO, não oito.** Mesma disciplina do `--teste` do WhatsApp, do
`--limite 10` das métricas e do `--quantos 1`. Render → crítica → EDL v2 →
render. Só depois escala. Automatizar um editor mediano é multiplicar mediania.

**Fica pra depois (depende de coisa que não existe):** escolher movimento pelo
TIPO do asset (detalhe → punch-in, pessoa → seguir região de interesse,
antes/depois → split). Exige análise por imagem, que a gente ainda não tem. O
`visual_audit_agent` é o candidato natural.

⚠️ **Não adotado — CTA por objetivo com urgência.** A sugestão incluía "Se
ainda estiver nesse preço, corre." Urgência foi MEDIDA em 1,8-2,2% contra
3,8-5,1% dos hooks de 1ª pessoa, e a própria sugestão diz "não inventar
urgência". CTA fica simples e verdadeiro.

⚠️ **Não adotado — quality gate com nota 0-10.** Já registrado acima: modelo
dando nota a si mesmo é opinião com casa decimal.

### A REGRA DE OURO (adotada, e vale pro projeto inteiro)

> O Jarvis nunca deve tratar uma experiência como verdade só porque aconteceu
> uma vez. **fato → observação → hipótese → experimento → evidência → conclusão.**

Isto é o melhor que saiu das conversas paralelas, e o projeto já viveu a lição:
em 08/08 eu afirmei que o hook "Corre ver isso" era **11x melhor** olhando só
alcance — e vinte minutos depois, com engajamento, ele virou um dos PIORES.
Se eu tivesse mexido no gerador na primeira leitura, teria cravado o hook
errado no código com a confiança de quem tem número.

O `--minimo 3` do ranking já é uma versão primitiva disso: grupo com menos de 3
posts fica fora, e o total de ignorados é impresso.

### MEMÓRIA — arquitetura desejada (levantada, não construída)

Em arquivos primeiro, índice depois, vetor por último. Nesta escala, arquivo é
transparente e depurável; banco é peso sem retorno.

    memory/
      short_term/    contexto e tarefas atuais
      long_term/     conhecimento, padrões, aprendizados
      episodic/      AAAA/MM/DD.jsonl — o que aconteceu
      decisions/     o que foi decidido e por quê
      mistakes/      o que deu errado
      hypotheses/    o que ainda não foi confirmado
      autobiography/ timeline.md — a história legível

**A parte que vale mais:** a memória tem NÍVEL DE CONFIANÇA e evolui.

    "acho que vídeo demonstrativo converte"   → hipótese
    "evidência moderada"                      → 12 casos
    "padrão confirmado em 87 vídeos"          → conhecimento

E um **Memory Manager** decide o que merece ser lembrado, em que categoria, com
que confiança, se contradiz memória antiga e se algo deve ser esquecido. Sem
ele, o LLM escreve qualquer coisa na memória permanente e coincidência vira
"conhecimento" — exatamente o que a regra de ouro proíbe.

⚠️ **NÃO adotado: auto-modificação de código.** A ideia de o sistema copiar a
si mesmo, gerar variantes e selecionar as melhores é interessante como
experimento mental e é a direção errada aqui, agora. Em 08/08 **uma crase num
comentário** fez este projeto rodar tudo em quádruplo por semanas sem ninguém
perceber. Dar ao sistema permissão de escrever no próprio código antes de ele
saber detectar que está errado multiplica o estrago na velocidade da máquina.
A ordem certa é: **primeiro perceber, depois decidir, e só muito depois mexer
em si mesmo.**

### ⚠️ MÚSICA EM ALTA vs. POSTAGEM POR API — conflito não resolvido (08/08)

**O Dre ia mandar centenas de faixas da biblioteca do Instagram pra catalogar.
Parei antes, porque a lista pode ser inútil pro fluxo automático.**

`meta_uploader.py:378` manda `{"media_type": "REELS"}` + o arquivo de vídeo.
**Não há campo de música.** O áudio que vai ao ar é o que está dentro do MP4.
A biblioteca do Instagram vive DENTRO do app e é escolhida na hora de postar,
pelo celular.

Consequência: **vídeo postado pela Graph API não usa faixa da biblioteca**, e o
empurrão de distribuição do "som em alta" não acontece. Os modos `viral` e
`narracao_viral` do EDL, do jeito que estão, descrevem algo que o pipeline
automático não consegue executar.

**Três saídas, e a escolha é do Dre:**

  1. **Música própria no render** — arquivos livres de direitos, em disco,
     embutidos no MP4. Automático, sem empurrão de trending. É o que dá pra
     fazer hoje sem mudar nada no fluxo.
  2. **Postagem manual pelo celular** só no braço do experimento que testa
     música em alta. Não escala, mas responde a pergunta.
  3. ✅ **RESOLVIDO pelo Dre: o METRICOOL tem parceria oficial** e agenda Reels
     com faixa da biblioteca. Ou seja, o automático É possível — só não pela
     Graph API direta. **Este é o caminho a investigar** (o Metricool tem API
     própria; falta ver se ela expõe a escolha de música ou se o agendamento
     precisa ser feito no painel).

**O que isto NÃO invalida:** `shared/musicas.json` continua útil como guia de
qual faixa escolher ao postar à mão. E a hipótese "alcance baixo é por conteúdo
reciclado" continua testável só com conteúdo original — que é automático.

**Recomendação atualizada:** o piloto sai em `narracao` (100% automático pela
via de hoje) e, em paralelo, investigar o Metricool. Se ele agendar com música
por API, o braço "música em alta" também vira automático e o experimento roda
inteiro sozinho.

**A biblioteca precisa CRESCER, e agora por um motivo medido.** Com 7 faixas,
as 8 linhas do tempo saíram com a MESMA música — pra tech instrumental de
energia média só existe uma candidata. O Dre ofereceu mandar centenas; agora
faz sentido aceitar. O que interessa por faixa:

    nome · artista · nº de reels · duração · instrumental? · energia · nichos

Instrumental é o que mais falta: é o único que serve pro modo narracao_viral,
e hoje há 5 na lista. **Faixa cantada não serve** por baixo de narração — duas
vozes brigando.

### RENDER — `render.py`, o piloto saiu (09/08)

A cadeia fechou: **storyboard (o quê) → EDL (como) → render (pixel)**. Nenhuma
decisão criativa mora no render; se o vídeo ficou lento conserta-se no `edl.py`,
se a frase ficou fraca no `storyboard.py`.

    python3 render.py --edl shared/edl/x.json --imagens pasta/ --quadros 8

**O que foi MEDIDO e mudou o desenho (nada aqui é palpite):**

1. **A narração real não cabe no tempo planejado.** O `edl.py` estima fala em 15
   caracteres/segundo. O hook do polvo: **2,5s planejados, 4,08s de Edge-TTS**.
   Renderizar pelo plano cortaria a voz no meio da primeira frase — a única que
   decide se a pessoa fica. Por isso o render **gera a voz primeiro, mede, e
   estica a linha do tempo** (passo `_conformar`). O piloto foi de 18,00s pra
   20,19s, e as 5 falas caem no início do trecho certo (conferido com
   `silencedetect`: 0,00 · 4,45 · 9,23 · 13,73 · 18,23). O trecho só CRESCE,
   nunca encolhe: sobrar imagem é respiro, faltar é frase cortada.
2. **`drawtext` não existe em todo FFmpeg.** O build estático testado tem
   `libfreetype` ligado e mesmo assim **não traz o filtro**. Texto sai por
   **libass**, e é melhor: ASS anima de verdade (`\t`, `\move`, `\fad`, cor por
   palavra) — que é o que o `ANIM_TEXTO` pede e o drawtext não faz. O render
   checa o filtro `ass` ANTES de gastar 5 chamadas de TTS.
3. **Emoji queimado no vídeo está DESLIGADO, e dói.** Quadro de teste com
   😩 👆 😮‍💨 🔥 💡 em duas fontes, inclusive forçando a Noto Color Emoji: o libass
   desenhou **todos em preto e branco**, pequenos, e **quebrou a sequência ZWJ**
   do 😮‍💨 em dois desenhos soltos. O projeto já resolveu isso do jeito certo em
   outro lugar — o `narrated_video_agent` cola **PNG de emoji** da pasta brand
   (`_emoji_aparado`). **Esse é o caminho da v2.** Emoji continua na legenda do
   post; sai só do que é queimado no vídeo, e o render avisa quando tira.

**Três defeitos que só apareceram OLHANDO o render** (por isso existe o
`--quadros N`, que extrai PNGs — revisar vídeo sem player é o normal aqui):

  - **cartão com canto arredondado** ficou bonito no 1º corte e errado em
    movimento: a partir do zoom 1,06 as bordas saem da tela. O efeito aparecia e
    sumia. Trocado por **foto na largura cheia** — não há canto pra cortar, e o
    produto ainda fica maior.
  - **legenda cinza-lavada**: a animação de entrada valia pra todo estado da
    revelação palavra a palavra; cada estado dura ~0,1s e o fade 0,12s, então o
    fade **reiniciava a cada palavra e nunca chegava a opaco**. Entrada agora é
    só do 1º estado.
  - **palavra solta e torta**: revelar por transparência deixava "lado" sozinho
    e deslocado, com o resto do bloco como espaço vazio. Agora o bloco inteiro
    aparece e o que anda é o **destaque dourado** na palavra do momento — nada
    se mexe e a leitura acompanha a fala.

**A marca entra DEPOIS do movimento**, como PNG com alfa, senão o punch-in
ampliaria a logo a cada corte. A geometria lê as MESMAS variáveis do template
que já está no ar (`LOGO_X`, `LOGO_Y`, `LOGO_TAM`, `NOME_FONT`, `HANDLE_FONT`,
`TEXTO_DX`) — mudou lá, muda aqui.

**O que ainda NÃO sai do render** (o relatório lista em toda rodada, e o
`.relatorio.json` fica ao lado do MP4):
  - transição **`whip`** — sai corte seco. O **`flash`** sai, desenhado no ASS
    (de propósito: `xfade` encurta o vídeo e desalinha voz e legenda).
  - **SFX** (whoosh/pop/impacto) — não há arquivo de som no projeto.
  - **música** — não há arquivo, e a do Instagram não se baixa. Por isso o
    piloto é modo `narracao`, como já estava recomendado acima.
  - **emoji** — item 3.

⚠️ **O piloto foi renderizado com fotos genéricas**, porque este ambiente não
tem a fila de produtos nem a pasta `assets/brand`. O que está PROVADO é a
mecânica: tempo, corte, zoom, pan, legenda, marca, áudio e encode. **Falta rodar
na VPS** com foto de produto de verdade, `logo_ts_casa.png` e `verificado.png`
no lugar — e aí julgar o vídeo, não o encanamento.

### RENDER v2 — a voz certa, o template certo, e o olho (09/08)

**1. A VOZ É O ELEVENLABS, NÃO O EDGE-TTS.** Correção do Dre, e ela vale muito
mais que trocar de fornecedor: o endpoint `/with-timestamps` devolve **o
instante de início e fim de CADA CARACTERE**. Duas consequências:
  - a duração deixa de ser medida do arquivo e passa a ser **lida**;
  - a legenda deixa de ser ESTIMADA. O `edl.py` repartia o tempo de cada bloco
    proporcionalmente ao número de letras — chute educado que assume que toda
    letra dura o mesmo, e nenhuma dura. Agora cada bloco entra e sai no
    instante em que a voz diz aquelas palavras (`_resincronizar_legendas`).
  - `narracao_ia.falar_com_tempos()` usa **a mesma voz por nicho e os mesmos
    `voice_settings`** do `falar_elevenlabs` (extraídos pra `_voice_settings`,
    regra num lugar só). Edge-TTS vira **rede de segurança** e o render avisa
    alto quando cai nela: *"NÃO é a voz da marca, não publique sem ouvir"*.
  - ⚠️ O casamento legenda↔alinhamento compara **só alfanumérico**, porque o
    `_batidas` faz `strip(" ,;:")` e a pontuação do bloco quase nunca bate com
    a do texto falado. Bloco que não casa **fica com o tempo antigo e avisa** —
    legenda aproximada é ruim, legenda no lugar errado é pior. Testado com
    alinhamento sintético: 4 blocos contíguos, sem sobreposição, e o bloco
    inexistente preservado + avisado.

**2. O TEMPLATE — E O ERRO QUE EU COMETI DUAS VEZES.** Primeiro montei um
template inventado. Depois o Dre mandou o print do feed e eu montei um template
tirado do PRINT, no olho. As duas vezes errado, e o Dre foi direto ao ponto:
*"o template já está no projeto, é só olhar como são feitos os vídeos."*
Estava — em `narrated_video_agent._criar_camadas_topo` / `_criar_cta_fixo`, no
layout 3:4 do `telegram_repurpose_hunter` e na regra de fundo do
`produzir_tiktok`. **É exatamente a classe de erro do dicionário de logo
duplicado, que este projeto já pagou**: reescrever do zero o que já existe.

O que eu tinha errado, medido contra o código real:

| campo | eu tinha | é |
|---|---|---|
| logo | 64px em (52,44) | **120px em (100,112)** |
| nome / handle | 42 / 34 | **56 / 46** |
| margem do hook | 52 | **55** |
| fonte do hook | 46 fixa | **48, caindo até 34** antes de aceitar 3ª linha |
| mídia | largura cheia, altura variável | **82% centrada, 3:4 (885x1180)** |
| topo da mídia | calculado a partir do hook | **FIXO em `VIDEO_Y=470`** |
| hook | topo fixo, empurra a mídia | **rodapé ancorado acima do vídeo** |
| CTA | `👉` a ~95px do pé | **`COMENTE "QUERO" 👇`, `CTA_Y=1672`, fonte 52** |
| fundo | branco por padrão | **geral=preto, contas novas=branco** |

O erro que mais custaria: com o topo da mídia calculado a partir do hook, o
bloco de vídeo **muda de altura de post pra post** conforme o hook tem 1 ou 2
linhas. Num grid de perfil isso salta aos olhos. O template real faz o
contrário — a mídia fica cravada e o hook sobe.

Agora `render.py` lê **as mesmas variáveis de ambiente com os mesmos padrões**
(`LOGO_X/Y/TAM`, `NOME_FONT`, `HANDLE_FONT`, `TEXTO_DX`, `SELO_DX`, `HK_MARGEM`,
`HK_GAP_VIDEO`, `VIDEO_Y`, `VIDEO_W_FRAC`, `CTA_TEXTO/FONT/Y`, `TOPSHOP_BG`,
`FORCE_BG`, `BG_<NICHO>`): ajustar o template continua sendo mexer no `.env`,
num lugar só, e os dois renderizadores obedecem.

⚠️ **Uma diferença DELIBERADA:** o hunter chega no 3:4 esticando o vídeo pra
9:16 e cortando o meio. Isso funciona pra vídeo vertical de terceiro e
**deformaria foto de produto**, que é quadrada. O render de conteúdo original
usa a MESMA caixa mas encaixa a foto inteira dentro dela. Geometria idêntica,
produto intacto.

⚠️⚠️ **E MESMO ASSIM AS ALTURAS ESTAVAM ERRADAS — 3ª rodada.** Os padrões do
código não são o que está publicado: o `.env` da VPS já foi calibrado à mão e o
bloco inteiro desce ~90px. Medindo um Reel real por FRAÇÃO DA ALTURA do quadro:

| marca | fração medida | era no código | virou |
|---|---|---|---|
| topo da logo | 0,102 | `LOGO_Y=112` | **196** |
| nome "TopShop" | 0,125 | `logo_y-12` | **`logo_y+44`** |
| @handle | 0,161 | `logo_y+42` | **`logo_y+113`** |
| topo do vídeo | 0,295 | `VIDEO_Y=470` | **566** |
| rodapé do vídeo | 0,877 | 0,909 (`W_FRAC` 0,82) | **0,879 (`W_FRAC` 0,78)** |
| CTA | ~0,92 | `CTA_Y=1672` | **1745** |

Duas lições distintas aqui:
  - **O nome e o @ não erraram por descuido: erraram por CONTEXTO.** No template
    são `TextClip` do MoviePy, e posicionar o CANTO de um clipe não é posicionar
    a LETRA — o clipe carrega folga própria acima do glifo. Copiar `logo_y+42`
    cru subia o @ em ~48px e abria um vão branco entre cabeçalho e hook. Número
    certo, contexto errado. Mesma armadilha do selo verificado.
  - **O `.env` é a autoridade, não o padrão do código.** Os valores acima são os
    MEDIDOS, pra o render sair parecido de saída; `LOGO_Y`, `NOME_DY`,
    `HANDLE_DY`, `VIDEO_Y`, `VIDEO_W_FRAC` e `CTA_Y` continuam mandando.

E entrou uma trava: se o CTA encostar no rodapé do vídeo (< 20px), o render
avisa. Foi um defeito real desta rodada — 14px de folga — e é exatamente o tipo
que se vê num quadro e não se vê no código.

⚠️⚠️⚠️ **4ª rodada, e a correção mais ESTRUTURAL: a coluna do texto É a coluna
do vídeo.** No post publicado a logo e o hook começam EXATAMENTE na borda
esquerda do vídeo, e o hook nunca passa da direita. Eu vinha usando margens
absolutas (`LOGO_X=100`, `HK_MARGEM=55`) enquanto a caixa do vídeo começa em
**119** — resultado: logo e hook vazando pras **tarjas brancas laterais**, que
são parte do template e devem ficar limpas. O Dre: *"tem que ficar em cima do
vídeo, perfeitamente simétrico, não pode ficar saindo pras pontas brancas"*.

Agora `LOGO_X` e `HK_MARGEM` têm como padrão o `x_midia`, e o hook quebra na
LARGURA DO VÍDEO. A simetria deixou de ser um número pra acertar e virou
consequência: mude `VIDEO_W_FRAC` e a coluna inteira acompanha. (Os dois
continuam existindo como override.) `LOGO_Y` foi de 196 pra **222**, também a
pedido — logo e @ um pouco mais baixos.

**E este defeito virou checagem: `tarjas_limpas`.** As faixas laterais têm que
ser chapadas; conteúdo nelas levanta o desvio-padrão. Testada reproduzindo o
defeito com `LOGO_X=100 HK_MARGEM=55`: **reprovou com desvio 21,9** e o render
certo passou. É a 3ª checagem que nasce de um defeito que o DRE viu antes de
mim — e a razão de o `conferir_render` existir: o que um humano pega no olho
duas vezes, a máquina tem que passar a pegar sozinha.

### ✅ FIM DA ADIVINHAÇÃO — o `.env` da VPS (09/08)

O Dre mandou o `grep` do `.env` e ele é a autoridade: é com esses números que os
vídeos que estão no ar foram feitos. **Duas rodadas minhas foram gastas medindo
print quando bastava pedir isto.**

    VIDEO_Y=540   HK_GAP_VIDEO=20   HK_MARGEM=89   HK_MARGEM_DIR=100
    HK_FONT=46    HK_ALT_LINHA=62   LOGO_X=86      LOGO_Y=210
    LOGO_TAM=118  NOME_FONT=52      HANDLE_FONT=42 CTA_Y=1740

**Calibrando minha confiança em "medir por fração de altura de um print":**

| campo | eu medi | é | erro |
|---|---|---|---|
| `VIDEO_Y` | 566 | **540** | +26 |
| `LOGO_Y` | 222 | **210** | +12 |
| `CTA_Y` | 1745 | **1740** | +5 |
| `LOGO_X` | 119 (deduzi) | **86** | +33 |
| `HK_MARGEM` | 119 (deduzi) | **89** | +30 |

**A leitura VERTICAL do print aproximou bem; a HORIZONTAL não serviu.** Pior: eu
tinha mexido no `VIDEO_W_FRAC` (0,82 → 0,78) pra fechar uma conta que só não
fechava porque o `VIDEO_Y` estava errado — mudei o parâmetro certo pra compensar
o parâmetro errado. Desfeito, voltou pro 0,82 do código.

E uma pegadinha de nome: a variável é **`HK_ALT_LINHA`**, não `HK_ALTURA_LINHA`.
Ler o nome errado é ler o padrão pra sempre, sem erro nenhum aparecer.

⚠️ **A "coluna perfeitamente simétrica" NÃO é alinhamento exato:** no template
real a logo (86) e o hook (89) avançam ~11px sobre a tarja em relação ao vídeo
(97). É template, não erro — e o inspetor precisa saber disso.

**E aí eu quase estraguei a checagem `tarjas_limpas` tentando acomodar isso.**
Primeiro fiz a borda vir de `x_coluna` = o mais à esquerda entre vídeo, logo e
hook. Testei mandando o hook pra margem 30 de propósito: **a checagem PASSOU** —
ela moveu a régua junto com o defeito. **Checagem que lê o limite da mesma
configuração que produziu o defeito não pega defeito nenhum, nunca.** A régua
agora é a caixa do VÍDEO com tolerância FIXA (24px): cobre os 11px reais do
template e reprova o vazamento (desvio 22,2).

Do print, o que se confirmou: **fundo branco**, cabeçalho
pequeno no alto (logo redonda · TopShop · selo azul · @handle em cinza),
**HOOK EM PRETO alinhado à esquerda**, a mídia como um **bloco de largura
cheia** no meio, e a barra fixa **`COMENTE "QUERO" 👉`** no pé.
  - **O hook dura o vídeo inteiro**, não só a seção do hook. É o cabeçalho do
    post, não uma legenda — o EDL trata como texto de seção e é o render que
    reconcilia com o template real.
  - **Só a mídia se mexe.** O zoom é aplicado à FAIXA da mídia e o template
    entra por cima, inteiro e parado. Foi isto que matou de vez a classe de bug
    do cartão saindo da tela: não existe mais "quadro montado sendo zoomado".
  - A faixa da mídia **ocupa todo o espaço livre** entre o hook e a barra de
    CTA. A 1ª versão usava a altura natural da foto e sobrava uma tira branca
    morta de ~320px — buraco no meio de baixo do quadro.
  - Tudo tunável por `.env` (`LOGO_X/Y/TAM`, `NOME_FONT`, `HANDLE_FONT`,
    `TEXTO_DX`, `TOPSHOP_BG`, `TOPSHOP_CTA_FIXO`), os mesmos nomes do
    `narrated_video_agent`.

**3. EMOJI: O PIL DESENHA, O LIBASS NÃO.** Medido lado a lado num quadro só. O
libass pinta 😩 👆 😮‍💨 em preto e branco e quebra o ZWJ; o Pillow pinta colorido
e compõe o ZWJ certo (`embedded_color=True` na NotoColorEmoji, que é bitmap —
abre em 109 e reduz). Daí a divisão de trabalho, que é regra e não gosto:

    PIL     o que é FIXO — cabeçalho, hook, barra de CTA.  TEM emoji.
    libass  o que ANIMA  — legendas e destaques.           SEM emoji.

Legenda é transcrição de narração, não leva emoji — então a divisão não custa
nada. E o hook, que é onde o emoji importa, saiu ganhando.

### RENDER → INSPEÇÃO → CORREÇÃO (`conferir_render.py`, 09/08)

**A observação do Dre que fecha o ciclo:**

> "muitos problemas só aparecem depois que o vídeo existe. O render não pode
> ser o último estágio lógico do sistema: render → inspeção → correção."

E a prova é o próprio piloto: **cartão saindo da tela no zoom, legenda lavada,
palavra isolada, emoji quebrado**. Nenhum dos quatro existe no storyboard nem
no EDL — os dois estavam certos. Os defeitos nasceram no encontro do plano com
o pixel. ⚠️ **E eu só os achei porque olhei.** Renderizados oito e postados, os
quatro teriam ido ao ar.

`conferir_render.py` é checagem **determinística** no arquivo final — mede
pixel e tempo, não pede opinião a modelo nenhum, na mesma disciplina da regra
de ouro. Cada achado carrega o número que o produziu.

    duracao          arquivo ≠ EDL          → conform/áudio saiu do lugar
    moldura_estavel  a moldura muda         → o zoom está comendo a marca
    midia_viva       a mídia não muda       → zoompan quebrado, vídeo parado
    quadro_morto     quadro chapado         → asset falhou, saiu tela lisa
    contraste_texto  faixa da legenda lisa  → legenda lavada ou ausente
    faixa_preenchida buraco na faixa        → foto pequena demais pro bloco

**Estado POR CHECAGEM, não só um veredito** (sugestão do ChatGPT via Dre, e
certeira): `reprovado` sozinho não diz ao CEO qual parte do pipeline
investigar. Com `moldura_estavel=falhou` o dedo aponta direto pro render. E o
estado `nao_rodou` existe pra que uma checagem que **não pôde** rodar nunca se
confunda com uma que passou — esse é o jeito silencioso de um validador virar
decoração.

**E o checador foi TESTADO CONTRA DEFEITO DE VERDADE**, não só contra o vídeo
bom — senão seria mais um aviso que não avisa. Fabriquei dois vídeos quebrados
de propósito: um com zoom no quadro inteiro (a marca zoomando junto) e um
congelado. `moldura_estavel` pegou o primeiro (diferença 63,0) e `midia_viva` o
segundo (0,41). O render bom passou.

**Sobre o `visual_audit_agent` — sim, ele existe e funciona**, com extração de
frames, heurísticas OpenCV, folha de contato e uma camada Gemini Vision
(`avaliar_relevancia_frame`). Mas ele audita os **INGREDIENTES** — "este clipe
combina com este produto?" — e não o **BOLO**. Nenhum dos quatro defeitos do
piloto seria pego por ele. O caminho natural é reaproveitar a camada Vision
dele apontada pro MP4 pronto, com o `conferir_render` entregando os quadros já
recortados por zona (moldura × mídia). **Ainda não feito.**

**O que isto abre**, e era o ponto do Dre: com veredito em JSON por render, a
memória do projeto pode começar a guardar não só o que VENDEU, mas o que o
sistema APRENDEU A PRODUZIR — *"o render #184 teve invasão de moldura em zoom
> 1,06; o limite virou 1,04"*.

⚠️ **Pergunta em aberto, não resolvida por mim:** a barra `COMENTE "QUERO" 👉`
fica a ~95px do rodapé. No print (grade do perfil) ela aparece inteira, mas no
**player de Reels** a interface do Instagram cobre a faixa de baixo. Não mexi
no template publicado por causa disso — é medição pra fazer no app, não palpite
meu.

### PILOTO — `piloto.py`, a cadeia inteira num comando (09/08)

    produto da fila → roteiro → linha do tempo → MP4 → conferência

    .venv/bin/python piloto.py --fila 0

Baixa a foto do produto (a fila guarda URL, não arquivo), gera o roteiro, monta
a linha do tempo, renderiza e confere. **NÃO POSTA NADA.** Existe porque cada
peça foi provada separada e com foto genérica; defeito de integração só aparece
quando todas as peças reais se encontram — e encadear seis comandos à mão é
onde se erra um parâmetro e se perde meia hora culpando o render.

**A 1ª rodada do piloto já pagou o próprio custo**, com duas descobertas:

1. ✅ **O "erro" que o Dre viu no print era a MINHA FOTO DE TESTE, não o
   render.** Com foto de produto sobre fundo BRANCO — que é a esmagadora
   maioria na Shopee — o preenchimento da caixa 3:4 sai quase branco e **funde
   com o template**. Com a minha foto (paisagem P&B) virava uma faixa cinza que
   parecia defeito. Fica registrado o `--encaixe cover` pra quem tiver foto com
   margem de sobra: preenche a caixa cortando ~25% da largura, e avisa quando
   corta demais.

2. ❌ **Duas checagens minhas estavam erradas, e o piloto expôs as duas:**
   - `faixa_preenchida` reprovava o caso BOM. Ela deduzia dos pixels que "a
     foto é pequena demais pro bloco" — e o preenchimento branco fundido com o
     template é exatamente o resultado desejado. **REMOVIDA.** Quem sabe essa
     proporção é o render, que a CALCULA; virou aviso lá (`ocupa < 62%`).
     Checagem que não distingue o certo do errado não é frouxa, é ruído.
   - `contraste_texto` acusava "legenda lavada" quando o vídeo **não tinha
     legenda nenhuma** — o roteiro tinha caído no modelo base, sem narração nas
     cenas. Diagnóstico errado manda consertar o arquivo errado: mandaria
     depurar o render por horas quando o problema está no storyboard. Agora o
     relatório do render carrega a CONTAGEM de legendas e o inspetor separa os
     dois casos.

⚠️ **O que ainda não foi provado** (não dá pra provar fora da VPS): voz do
ElevenLabs com timestamps, logo e selo reais, e o `.env` de verdade. É o teste
de fogo que falta.

### 🔥 TESTE DE FOGO NA VPS — passou, e achou dois defeitos de ROTEIRO (09/08)

`piloto.py --fila 0` rodou com tudo real. **Veredito: ✅ PASSOU** nas seis
checagens, e o que importa mais:

  - **ElevenLabs com timestamps FUNCIONOU**: 90, 81, 108, 118 e 26 tempos de
    caractere nas cinco falas. A legenda deixou de ser estimada de verdade.
  - **`logo_ts_casa.png` + `@topshopcasa_`** — a marca certa da conta certa.
  - A linha do tempo conformou 20,0s → 27,26s, e o arquivo bateu com o EDL
    (diferença 0,00s).
  - `moldura_estavel` 0,2 · `midia_viva` 35,24 · `tarjas_limpas` ok.

**E o CPS=15 do edl.py foi confirmado pela voz real:** 108 caracteres viraram
7,18s (15,0 c/s) e 81 viraram 5,02s (16,1 c/s). A estimativa estava certa; quem
estava errado era o ROTEIRO.

**Os dois defeitos são do storyboard, não do render** — e é exatamente o que a
separação em três arquivos existe pra permitir descobrir:

1. **Hook de 103 caracteres.** O template dá 2 linhas entre a marca e o vídeo.
   O render encolheu a fonte de 46 até 34px e mesmo assim saiu em 3 linhas,
   encostando no cabeçalho. Agora `HOOK_MAX=70` no prompt e `HOOK_LIMITE=84` na
   validação — acima disso o roteiro é REPROVADO, não avisado.
2. **Narração que não cabe na cena que ela mesma pediu.** Cena declarada com
   4,7s e narração de 108 caracteres = 7,2s de fala. O render conforma
   esticando, então nada quebra — mas o vídeo de 20s vira 27,3s e a decisão de
   ritmo do storyboard vira letra morta. Agora o prompt dá o orçamento
   (15 c/s: "cena de 4s = até 60 caracteres") e a validação reprova acima de
   35% de estouro.

⚠️ **E o meu aviso escondeu a própria evidência:** ele imprimia `hook_txt[:70]`,
truncando em 70 caracteres justamente o texto cujo problema ERA ter mais de 70.
Passei a impressão de que o hook tinha 70. Agora sai inteiro, com a contagem.
**Aviso que corta a evidência é meio aviso** — irmão do "aviso que não avisa".

**`piloto.py --telegram`** manda o MP4 e a folha de contato pro chat de admin.
Motivo bobo e real: o vídeo nasce na VPS e quem julga está no celular — o Dre
tentou executar o `.mp4` no shell e levou `Permission denied`.

### 🎧 O DEFEITO QUE NENHUMA CHECAGEM DE PIXEL PEGARIA (09/08)

O piloto da Garrafa Squeeze **passou em tudo** — moldura estável, mídia viva,
duração exata, tarjas limpas — e mesmo assim era um vídeo ruim. O Dre ouviu:

> "a narração fica muito curta, literalmente 2-3 segundos sem narração, sem
> música... parece que fica um climão horrível, o pessoal certamente vai pular"

**Medido no arquivo dele:** 3 buracos de **2,0s, 2,2s e 3,6s** = 7,9s calados
num vídeo de 19,9s. **40% do vídeo era silêncio puro.**

**A causa é uma decisão minha, escrita com justificativa e errada.** O
`_conformar` fazia `max(largura_planejada, fala)` — eu tinha comentado que
"sobrar imagem é respiro; faltar é frase cortada". A primeira metade é falsa:
3,16s de fala numa cena de 4,7s não é respiro, é BURACO. **A voz manda nos DOIS
sentidos** — agora o trecho com fala vale o tempo da fala (com piso de 1,4s), e
só trecho sem narração nenhuma mantém o tempo do roteiro.
Resultado no mesmo roteiro: 18,00s → **16,95s**, e zero buracos.

**E virou checagem: `silencio_morto`.** Roda o `silencedetect` a cada render e
reprova buraco > 1,2s no meio (o silêncio do FIM não conta — é respiro). É a
primeira checagem de ÁUDIO, e nasceu de um defeito que passou por todas as de
pixel. Prova de que "tecnicamente correto" e "bom" não são a mesma pergunta.

**Três acertos de design, todos do olho do Dre:**
  - **selo verificado sumindo** — eu redimensionava o PNG direto. A lição já
    estava escrita no projeto, em `narrated_video_agent._emoji_aparado`: PNG de
    marca vem com muita margem transparente, e sem APARAR o alfa antes o resize
    conta o vazio e o desenho sai bem menor. Agora apara.
  - **@ longe do nome** — `HANDLE_DY` de 113 → 96 (entrelinha normal pra 52px).
  - **CTA baixo demais** — `CTA_DY=-26`, sem tocar no `CTA_Y` do `.env`, que os
    dois renderizadores compartilham.

**O relatório agora grava o `voz_id` do ElevenLabs.** O Dre achou que a voz não
era a do ElevenLabs; o log dizia que era (52, 43, 55, 44 e 29 tempos de
caractere só saem de lá). Impressão contra impressão não resolve — ID resolve.

⚠️ **Limitação real que o piloto expôs e que NÃO é do render: UMA foto.** A
`productOfferV2` da Shopee devolve um `imageUrl` só, então a fila guarda uma
imagem por produto e o vídeo inteiro vive dela (com punch-in, que disfarça, mas
não resolve). **Nenhum ajuste de render conserta isso** — precisa de mais
imagem na origem. É o próximo gargalo do produtor original.

### VOZ POR PERFIL + UMA FOTO SÓ (10/08)

**Voz por perfil: o mecanismo já existia e morava no lugar errado.**
`ELEVENLABS_VOICE_ID_<NICHO>` resolvia no `.env` — que é o arquivo menos
visível do projeto. Ninguém abre o `.env` pra saber "que voz o
@topshopbeauty._ usa?". Agora a voz mora no **`contas.json`**, campo `voz_id`,
ao lado do handle e do `instagram_user_id`. Voz é identidade da conta tanto
quanto o @; é a mesma lição da logo por nicho — informação de conta espalhada
faz um perfil publicar com a cara de outro.

    ELEVENLABS_VOICE_ID_<NICHO>   .env       override rápido, pra testar
    contas.json[nicho].voz_id                a voz OFICIAL do perfil
    ELEVENLABS_VOICE_ID           .env       a voz padrão da casa

    python3 narracao_ia.py --vozes

lista perfil → handle → voz → de onde veio, e **avisa quando dois perfis
compartilham a mesma voz** ou quando um está sem voz própria. Configuração que
ninguém consegue listar é configuração que ninguém confere.

**UMA FOTO SÓ — o gargalo que o Dre apontou duas vezes.** A `productOfferV2`
devolve um `imageUrl` por produto. O punch-in disfarça, e ele percebeu na
primeira olhada: *"só tem uma imagem durante todo o vídeo"*.

`piloto.py` agora deriva **enquadramentos** de uma foto só: plano geral +
closes escolhidos pela região de MAIOR DETALHE (variância do cinza numa grade
deslizante). Foto de e-commerce raramente tem o produto no centro — é produto
num canto, modelo no outro, "antes/depois" espremido embaixo; cortar no centro
pegaria fundo liso. Testado numa foto composta: 3 planos visivelmente
diferentes, um deles fechando no produto + insets.

⚠️ **Isto NÃO substitui ter mais foto.** É o melhor que dá pra fazer com o
material que existe. O gargalo continua na ORIGEM, e o próximo passo real é
buscar mais imagem por produto (ou filtrar as ruins — a foto do piloto tinha
texto promocional queimado, que briga com a nossa legenda).

**E o conserto do silêncio criou um bug que o piloto pegou na hora.** Com o
trecho passando a valer o tempo da FALA, uma linha do tempo de 18,6s desabou
pra **6,4s**: as fronteiras vinham do início de cada NARRAÇÃO, então três cenas
sem fala foram engolidas pelo trecho do hook e encolheram junto. O `edl.py`
passou a carimbar `secoes` (início/fim de cada cena) e o `_conformar` usa
essas fronteiras. Agora:
  - roteiro COM narração: 18,00s → 16,95s, `silencio_morto` 0,0 ✅
  - roteiro SEM narração nas cenas: mantém 20,67s e **REPROVA** com 14,8s de
    silêncio — que é a verdade, e vídeo assim não deve ser publicado.

### VOZ POR PERFIL — configurada (10/08)

    geral   @topshop.__        7b9mYhmnp0y2qSH1FnBL   bunty
    beleza  @topshopbeauty._   1hlpeD1ydbI2ow0Tt3EW   verinity x
    casa    @topshopcasa_      DYkrAHD8iwork3YSUBbs   tom
    tech    @topshoptech_      n1PvBOwxb8X6m7tahp2h   michael c vincent
    pet     @topshoppet_       Czw3Dn181ypdrCOnPfif   brian c
    moda    @topshopmoda_      yj30vwTGJxSHezdAGsv9   jessa

    python3 narracao_ia.py --definir-voz geral=ID:nome beleza=ID:nome ...
    python3 narracao_ia.py --vozes

⚠️⚠️ **O `contas.json` NÃO é commitado com as vozes, e isso é deliberado.**
O arquivo da VPS tem contas que este repo não tem (pet e moda foram criadas
depois). Commitar a minha versão e deployar **apagaria a configuração delas** —
`instagram_user_id`, `page_token_env`, tudo. Por isso a voz entra por COMANDO,
que faz merge no arquivo que já está lá.

⚠️ **E o comando se RECUSA a criar conta nova.** O
`daemon_maestro._nichos_das_contas` monta os nichos de PRODUÇÃO a partir das
chaves deste arquivo: criar "pet" aqui com só handle e voz faria o daemon
produzir pra uma conta sem `instagram_user_id`, e o post falharia depois, longe
daqui, sem ninguém ligar uma coisa à outra. Nicho que não existe vira aviso.

**Ajustes de voz por perfil** (`voz_ajustes` no contas.json) sobrepõem o padrão
da casa — a sugestão do ChatGPT via Dre, e ela é certa: *"daqui a seis meses
você não quer descobrir que trocaram um parâmetro"*. Voz é asset de marca.

### O GARGALO AGORA É ALIMENTAÇÃO VISUAL, NÃO EDIÇÃO (10/08)

O piloto tem 9 cortes e **uma composição só**. O ChatGPT resumiu bem: *"9
cortes não significam 9 informações visuais — o cérebro percebe que é a mesma
foto"*. O motor de edição está pronto; o que falta é matéria-prima.

⚠️ **E eu afirmei uma coisa que não verifiquei.** Disse que "a API da Shopee
devolve uma imagem só, então não dá pra resolver". A verdade é mais estreita:
**a nossa query pede `imageUrl` e mais nada**, então ela nunca teve chance de
devolver outra coisa. Construir coletor, ranker e fila de assets em cima dessa
suposição seria construir em cima de um palpite meu.

`probe_imagens.py` pergunta à API, um campo por pedido (GraphQL derruba a query
inteira por um campo inválido — é o mesmo motivo do truque do
`priceDiscountRate`). Testa `images`, `imageUrls`, `gallery`, `videoUrl` e mais
alguns. **Se existir galeria, metade do problema some hoje e de graça; se não
existir, pelo menos vira FATO** e o coletor se justifica.

**A ordem acordada** (do ChatGPT, e eu concordo — não mexer mais em corte/zoom):

    ✅ template · cortes · zoom · mini-hooks · timestamps · voz por perfil
    🔄 probe: a API tem galeria?          ← primeiro, é uma pergunta
    🔴 Asset Collector (mais imagem/vídeo por produto)
    🔴 Asset Ranker (rejeita texto queimado, marca d'água, duplicata)
    🔴 Storyboard escolhe o asset por PAPEL (hero / feature / uso / detalhe)
    🔴 Variation Engine como FALLBACK, não como solução
    🧠 CEO aprende: retenção × quantidade de assets

**Níveis de material visual** (a ideia é do ChatGPT e vale adotar quando o
coletor existir): S = vídeo + 5 imagens · A = 4+ imagens · B = 2-3 + variações ·
C = 1 imagem boa + variações · **D = 1 imagem ruim com texto queimado → BLOCK,
nem chega ao render**. A foto da escova alisadora era nível D: texto promocional
dentro da imagem brigando com hook, mini-hook, legenda e CTA.

### ❌ FATO MEDIDO: a API de afiliado NÃO tem galeria (10/08)

`probe_imagens.py --fila 0` na VPS, um campo por pedido:

    ✗ images  ✗ imageUrls  ✗ imageList  ✗ productImages  ✗ itemImages
    ✗ gallery ✗ galleryImages ✗ mainImages ✗ videoUrl ✗ productVideoUrl ✗ video

**Nenhum existe.** A `productOfferV2` entrega `imageUrl` e mais nada. Isso agora
é FATO, não suposição minha — e é o que faltava pra o Asset Collector deixar de
ser palpite e virar necessidade justificada.

E a API interna da loja (`v4/item/get`), que é onde a galeria costuma estar,
devolveu **HTTP 403** do meu ambiente. Falta o mesmo teste da VPS (IP diferente):

    .venv/bin/python probe_imagens.py --fila 0 --interna

**O que sobra, se a interna também bloquear:**
  1. **Playwright na página do produto** — o projeto já tem navegador real e
     contexto persistente (`ig_playwright`, `amazon_playwright`). Navegador de
     verdade é exatamente o que derruba 403 de requisição crua. É a aposta mais
     forte, e usa ferramenta que já existe aqui.
  2. **Amazon / Mercado Livre** pro mesmo produto: as duas expõem galeria, e o
     `amazon_playwright.py` já está no projeto.
  3. **Vídeo do hunter** — o `telegram_repurpose_hunter` já traz vídeo real do
     produto. ⚠️ Mas usar vídeo de terceiro num vídeo "original" contradiz o
     experimento inteiro: a hipótese em teste é que alcance baixo vem de
     conteúdo reciclado.
  4. **`ia_scene_generator`** — caro e arrisca parecer falso.

### CONTAS PET E MODA — os IDs certos (10/08)

O `diag_contas.py` devolveu o que eu precisava, e confirmou o alerta: os IDs
que tinham vindo antes eram os do APP, não os da Graph API.

    pet   @topshoppet_    ig 17841437267536246  fb 1313800555148371
                          PAGE_TOKEN_TOPSHOP_PET_SHOP     · voz brian_c
    moda  @topshopmoda_   ig 17841449168252255  fb 1270945889431368
                          PAGE_TOKEN_TOPSHOP_MODA_STYLE   · voz jessa

    python3 narracao_ia.py --criar-conta nicho=pet handle=@topshoppet_ \
        instagram_user_id=... facebook_page_id=... page_token_env=... voz_id=...

⚠️ `ELEVENLABS_VOICE_ID_BELEZA` no `.env` estava sobrepondo a voz do
`contas.json` — e só se viu porque a listagem mostra a ORIGEM de cada voz. Sem
essa coluna, o Dre teria configurado a verinity x e continuado ouvindo outra.

### ASSET COLLECTOR — construído DEPOIS de duas medições (10/08)

    API de afiliado (productOfferV2)   11 campos de galeria testados · 0 existem
    API interna (v4/item/get) crua     HTTP 403 · aqui E na VPS

**Só com esses dois fatos o coletor se justificou.** Se eu tivesse construído
quando o Dre apontou o problema, teria construído em cima do meu palpite — e o
palpite ("não dá pra resolver") estava errado.

`coletor_assets.py` **não raspa a página: escuta o que ela pede.** A própria
página de produto chama a `v4/item/get` — a MESMA rota que dá 403 na requisição
crua — e dentro do navegador ela responde 200, porque vai com cookie, cabeçalho
e impressão digital que o site espera. Então o coletor abre a página e ouve a
resposta daquela chamada (`page.on("response")`). É mais robusto que ler DOM,
que quebra a cada redesenho, e é exatamente a informação que o site usa pra
montar a galeria — inclusive `video_info_list`, que é material melhor que foto.

Rails: `COLETOR_ASSETS=0` desliga · só lê · um produto por vez · a fila só é
tocada com `--gravar`, preservando o resto do item.

    python3 coletor_assets.py --fila 0
    python3 coletor_assets.py --fila 0 --gravar     → `imagens` na fila
    python3 piloto.py --fila 0                      → o piloto já usa `imagens`

⚠️ **1ª VERSÃO FALHOU NA VPS, E FALHOU MAL:** *"a página abriu mas a chamada
da galeria não veio"*. Eu tinha amarrado o ouvinte a UMA rota
(`/api/v4/item/get`) — o mesmo erro de amarrar-se a um seletor de DOM. E o
aviso não distinguia "o site mudou de rota" de "renderizou no servidor" de
"bloqueou": **diagnóstico que não distingue causa não é diagnóstico**.

**Redesenhado pra procurar FORMATO, não nome.** Agora captura TODA resposta
JSON de qualquer `/api/` e vasculha atrás de listas com cara de hash da Shopee
(`br-11134207-7r98o-abc123`). Não importa se a rota vira `pdp/get_pc` amanhã.
Se nada vier por XHR, ainda procura o mesmo formato no HTML — página renderizada
no servidor traz o JSON embutido. E `--diagnostico` salva print + lista todas as
chamadas `/api/` vistas, pra a próxima decisão ser por evidência.

**2ª rodada na VPS — a rota APARECEU:** `200 /api/v4/pdp/get_pc`. Ou seja, a
chamada da galeria chegou e minha busca não a reconheceu, ou ela veio com erro
silencioso (a Shopee responde 200 com `error` no corpo quando bloqueia). Duas
causas muito diferentes, e nenhuma delas se decide adivinhando pela terceira
vez. Com `--diagnostico` o corpo das rotas de produto agora é SALVO em JSON, com
um resumo de chaves e do campo `error` — é o que encerra a dúvida.

Testado com três payloads: rota inventada com campo `image_list` (achou pelo
formato), formato antigo `images` + `video_info_list` (não regrediu), e JSON com
listas que NÃO são galeria (não inventou). ⚠️ O caminho feliz continua sem teste
meu — este ambiente não alcança a Shopee (`ERR_CONNECTION_RESET`). O que testei foi a parte onde mora o risco real — a
leitura do payload — isolada em `extrair()`: hash virando URL do CDN, hash
vazio descartado, vídeo sem `url` ignorado, URL já completa preservada, payload
sem `data` avisando. Passou. O resto depende da VPS alcançar a loja.

### 🔒 GALERIA DA SHOPEE: FECHADO POR BLOQUEIO — três medições (10/08)

    1. API de afiliado (productOfferV2)   11 campos testados · nenhum existe
    2. API interna (v4/item/get) crua     HTTP 403 · aqui E na VPS
    3. Página real, navegador headless    200 /api/v4/pdp/get_pc, MAS:
                                          error=90309999 · sem `data`
                                          chaves numeradas = resposta ofuscada
                                          título da página "Shopee Brasil"

**`error=90309999` é anti-bot.** Não é formato, não é rota, não é tempo de
espera: é o IP do servidor. Insistir daqui não muda resultado, e o coletor
agora DIZ isso em vez de reportar "não achei galeria" — que era verdade e
escondia a causa.

⚠️ **Valeu a pena mesmo assim, e por um motivo:** eu tinha declarado "não dá
pra resolver" no primeiro palpite. Estava errado — havia caminhos, e só três
medições fecharam a porta de verdade. **A diferença entre "eu acho que não dá"
e "medi e não dá" é o que separa uma decisão de uma desculpa.**

**O que muda resultado, com o custo honesto de cada um:**

  1. **Amazon / Mercado Livre pro mesmo produto** — as duas expõem galeria e o
     `amazon_playwright.py` já existe. ⚠️ Só serve pra produto que exista nos
     dois lugares, e o link de afiliado continua sendo o da Shopee.
  2. **Sessão logada da Shopee** — cookie de conta real no contexto persistente
     do Playwright (o projeto já faz isso pro Instagram). Custo: um login
     manual, e o risco de a conta ser marcada.
  3. **Proxy residencial** — o ROADMAP já dizia *"proxies por conta: só se vier
     punição/bloqueio, não antes"*. **Veio.** Custo mensal e mais uma peça.
  4. **Aceitar 1 foto** e investir em SELEÇÃO em vez de quantidade: rejeitar
     foto ruim (texto promocional queimado, como a da escova alisadora) antes
     de produzir. Não aumenta o material, mas aumenta o piso da qualidade — e é
     independente de qualquer decisão acima.

**Enquanto isso o piloto não parou:** 1 foto + 3 enquadramentos derivados por
região de detalhe, e `--encaixe cover` pra foto com margem sobrando.

### 🎙️ O HOOK SAIU DA NARRAÇÃO (10/08)

O Dre ouviu o piloto do teclado e pegou: *"no início a narração repete o hook,
vamos remover e já começar direto"*. Está certo, e o desperdício era grande —
**o hook fica ESCRITO no alto o vídeo inteiro** (é template), então narrá-lo
gastava os 3 primeiros segundos, os únicos que decidem se a pessoa fica,
repetindo em voz o que ela acabou de ler com os olhos.

`NARRAR_HOOK = False` no `edl.py` (`--narrar-hook` volta atrás). A seção do
hook continua existindo como **batida visual** de 0,9s — dois cortes rápidos
que abrem em movimento — mas sem voz. ⚠️ E a duração precisou encolher junto:
seção sem fala mantém o tempo do roteiro, então deixar 2,5s ali criaria
silêncio de abertura. 0,9s abre o vídeo e passa longe do `SILENCIO_MAX` de 1,2s.

Medido no mesmo roteiro: 16,40s → **13,93s**, `silencio_morto` 0,0, ✅ PASSOU.
O vídeo começa com a história em vez de com o eco do título.

### 🔒 TEMPLATE V1.0 — CONGELADO (10/08)

O ChatGPT tem razão: *"não deixa o Claude ficar melhorando o design
infinitamente"*. Foram QUATRO rodadas de correção do Dre no mesmo arquivo, e
todas as quatro eram legítimas — mas o retorno já caiu. **Template fechado.**
Só se mexe com defeito reportado, não com "acho que fica melhor".

O último ajuste foi o selo, e ele rendeu duas lições — uma boa e uma minha.

**A boa:** depois de errar com 12 e com 4, em vez de um terceiro palpite eu
**renderizei a faixa do cabeçalho em -10, -6, -2 e +2 e comparei lado a lado**.
Quatro renders custam menos que quatro rodadas de ida e volta.

⚠️ **A minha:** gerei a comparação certa e **li o resultado errado**. Escolhi
-2 porque "encosta limpo"; o Dre queria +2 — *"abre só um vãozinho e não fica
encostado"*. Encostado vs. com respiro é escolha de DESIGN, não de precisão, e
quem decide é o dono da marca. **Produzir a evidência era meu trabalho;
concluir por ele, não.** Ficou `SELO_DX +2`.

**E a confusão que veio depois virou melhoria.** O Dre mandou outro vídeo com o
selo ainda encostado; eu não tinha como saber se o valor estava errado ou se
era o build antigo — era o build antigo (o `+2` foi commitado depois do comando
de deploy que eu tinha mandado). Antes de mexer em pixel de novo, medi se o
offset dependia da fonte: `textlength` e `textbbox` batem (0,4px de diferença
em Liberation, -0,1 em DejaVu), então o valor é estável entre fontes e não era
essa a causa.
**O relatório do render passou a gravar os KNOBS que geraram o arquivo**
(`SELO_DX`, `LOGO_*`, `VIDEO_Y`, `CTA_*`, `narrar_hook`). "Qual versão gerou
este vídeo" deixa de ser dedução e vira leitura — mesma ideia do `voz_id`.

    logo 86,210 (118px) · nome +44 · @ +96 · selo SELO_DX +2
    hook: coluna do vídeo, 2 linhas, 46px caindo até 34
    mídia: x 97→982 · y 540→1720 (82% em 3:4)
    CTA: COMENTE "QUERO" 👇 · CTA_Y 1740 · CTA_DY -8

Voz por perfil: ✅ seis contas, cada uma com `voz_id` no `contas.json`.

### ⚠️ O SELO, ENFIM: eu media a fonte que não é a de produção (11/08)

Quinta rodada do mesmo selo. O Dre: *"é só esse verificado cara, tá enchendo o
saco já, o resto tá perfeito"*. Ele estava certo de estar cansado — e a causa
não era nenhum dos quatro palpites anteriores.

**Medido no MP4 dele:** "TopShop" termina em x=449, selo começa em x=478.
**Vão real de 28px, com `SELO_DX = 2`.** O knob estava mentindo.

**A causa:** `render.py` posicionava o selo em `texto_x + d.textlength(...)`.
`textlength` é o **AVANÇO** da fonte — quanto o cursor anda, incluindo o espaço
reservado depois da última letra. O template original **nunca** teve esse
defeito: `narrated_video_agent.py:1042` mede com `_textclip_justo`, um clip
JUSTO cujo `.w` é a **TINTA**, e soma `SELO_DX=12`. Estava escrito no projeto o
tempo todo — de novo.

⚠️⚠️ **E o erro que fez isso durar cinco rodadas:** na rodada anterior eu
"provei" que avanço ≈ tinta medindo **Liberation (0,4px) e DejaVu (-0,1px)**.
As duas fontes que eu tinha na minha máquina. A produção usa
**`assets/brand/Montserrat-Bold.ttf`** (`_fonte()` prefere ela; só cai em
Liberation/DejaVu quando a brand não existe — que é exatamente o meu ambiente).
No Montserrat a sobra do avanço é de **26px**. **Eu medi as duas fontes que
tinha, não a fonte que envia o produto**, e apresentei o resultado como se
fechasse a questão.

**Correção:** `_fim_da_tinta()` (usa `textbbox`, com `stroke_width`, porque no
fundo escuro o contorno 3 também é tinta que aparece). O selo passa a ser
`fim_da_tinta + SELO_DX`, e **`SELO_DX` agora É o vão em pixels** — mesmo
sentido que ele tem no template original. Padrão de volta pra **12**.
Verificado medindo o pixel em 8 combinações (dx 2/8/12/20 × contorno 0/3): o
vão sai igual ao `SELO_DX` (+1px, borda exclusiva do `textbbox`), em qualquer
fonte, porque agora nada depende de métrica de avanço.

Junto, um bug latente: `Image.getbbox()` em RGBA olha os **quatro** canais, e
pixel branco-transparente `(255,255,255,0)` não é zero — margem de PNG branca
não era aparada. Agora usa `s.getchannel("A").getbbox()`.

    selo: fim_da_tinta("TopShop") + SELO_DX(12)   ← vão real, não avanço

**A lição, que vale além do selo:** medir na minha máquina só prova o que
acontece na minha máquina. Quando o número depende de um asset que a produção
tem e eu não (fonte, logo, binário), a medição precisa sair de um artefato
DELA — foi o quadro do MP4 do Dre que resolveu, em cinco minutos, o que quatro
rodadas de palpite não resolveram.

### ASSET RANKER — diversidade é o número que faltava (10/08)

> "9 cortes não significam 9 informações visuais — o cérebro percebe que é a
> mesma foto." — ChatGPT, e é a frase que define o arquivo.

`asset_ranker.py` responde, ANTES de gastar roteiro, voz e render: *com estas
imagens dá pra fazer um vídeo, ou dá nove cortes da mesma coisa?* Usa dHash +
distância de Hamming — assinatura perceptual, sem modelo nenhum.

Medido nos três casos que importam:

    5 fotos reais diferentes         5 distintas · diversidade 0,391 → nível A
    3 fotos quase iguais             1 distinta                     → ressalva
    1 foto + 2 enquadramentos meus   3 distintas · diversidade 0,521 → ok

⚠️ **O 3º resultado me surpreendeu e vale registrar:** os enquadramentos que o
piloto deriva de UMA foto pontuaram diversidade **maior** (0,521) que três
fotos "diferentes" do mesmo produto (0,125). Ou seja — recortar bem uma foto
boa pode render mais informação visual que três fotos redundantes. Isso não
apaga o gargalo, mas muda o que "mais imagens" significa: **diversidade, não
quantidade**, exatamente como o ChatGPT colocou.

O piloto agora consulta o ranker e **barra nível D** (`--forcar` ignora).

⚠️⚠️ **UMA MÉTRICA FOI REMOVIDA ANTES DE ENTRAR, e o motivo importa.**
Eu tinha incluído NITIDEZ (variância de Laplaciano, limiar 90). Calibrei contra
fotos reais antes de mandar: cinco fotos boas deram 0,9 · 4,0 · 10,6 · 11,0 ·
15,0, e duas DEGRADADAS de propósito deram 1,5 (esticada de 260px) e **7,3
(comprimida a qualidade 8) — mais alto que duas fotos boas.** Os intervalos se
sobrepõem: a métrica não separa o que promete. Removida.
É a terceira vez nesta sequência que a mesma lição aparece — `faixa_preenchida`,
a régua do `tarjas_limpas`, e agora esta. **Métrica que não distingue não é
métrica rigorosa; é ruído com casa decimal.**

Falta, e está dito: **texto promocional queimado na foto** (o defeito da escova
alisadora) sai como `nao_avaliado`, nunca "aprovado" — depende do Gemini Vision.

### Onde parou (04/08, fim do dia)

**Esperando o chip.** Pedido feito — Claro pré-pago, R$ 20,99, chegada prevista
~08/08. Pix conferido campo a campo antes de pagar (valor travado em 20.99,
recebedor Pagar.me/Stone, **CRC calculado e batendo** — prova de que ninguém
alterou valor nem destinatário depois de gerado).

Quando chegar: chip no slot 2 → ativa pelo app → WhatsApp Business no número
novo → migra o grupo → `WHATSAPP_ATIVO=1` → `--login` (QR vai pro Telegram).

**A única coisa do WhatsApp que nunca rodou de verdade é o envio COM FOTO.**
`_baixar_foto` já foi validado no seco (baixa e diz "COM foto"), mas
`_enviar_com_foto` — anexo, prévia, caixa de legenda — só dá pra testar
mandando. Escrito pra degradar em texto, não quebrar. **Testar com
`--quantos 1`.**

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
