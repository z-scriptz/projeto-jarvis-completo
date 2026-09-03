# 🤖 Projeto Jarvis — Roadmap TopShop

Máquina autônoma de marketing de afiliados (Shopee) rodando 24/7 na VPS.
Coleta virais → reproduz no padrão **TopShop** → posta sozinha → aprende o que
converte → repete. **Objetivo: virar máquina de dinheiro, dia após dia.**

> Documento vivo. É a memória do projeto entre sessões — tudo que a gente
> combina entra aqui. Legenda: ✅ pronto · 🔜 próximo · 🧠 backlog/avançado · 🐞 bug.

> 🚩 **COMO LER ISTO — leia antes de usar qualquer seção como estado atual.**
> As duas primeiras seções (`✅ Concluído` e `🔜 Próximas (prioridade)`) foram
> escritas em **julho** e **não são atualizadas quando um item muda**. Os
> **diários (`🗓️ Dia …`) vêm depois e mandam sobre elas.** O documento cresce
> por baixo, então **o mais autoritário está no fim, não no topo** — o
> contrário do que a diagramação sugere.
>
> Isto já me fez reportar coisa errada **duas vezes**, e a segunda foi depois
> de eu ter escrito a primeira aqui dentro (16/08): li a rampa `2→3→4` da
> seção 4.5 (19/07) como plano atual quando o que roda é a **pirâmide**, e
> ressuscitei a review do TikTok como "pendente" quando ela foi **reprovada**.
> Nos dois casos a informação certa estava no MESMO arquivo, mais embaixo.
>
> **Regra:** antes de afirmar que algo está pendente/desligado/aguardando,
> `grep` o termo no arquivo inteiro e acredite na ocorrência **mais recente** —
> e quando existir código, no código, não aqui.

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

#### ✋ "AMPLO NÃO É TIRAR O 'PRA QUEM'" — a correção do Dre (16/08)

Ele derrubou a minha regra com um exemplo tirado da **minha própria saída**:

    nao_fecha  ex: "Odeio boné que amassa o cabelo! 😩"

Não tem "pra quem", passa na régua, e é estreitíssimo de assunto.
**Ausência de porta não é amplitude.** Eu implementei um filtro negativo e
chamei de amplitude — dá pra obedecer a regra inteira e continuar estreito.

No exemplo dele a frase INTEIRA muda de vocabulário:

    estreito: "se você tem um golden que come tudo, ensino isso"
    amplo   : "quer um cachorro que não come nada do chão sem sua
               permissão? siga esses passos"

**Nenhuma palavra sobrevive.** O substantivo sobe um degrau (golden→cachorro) e
a frase passa a falar do RESULTADO, não de quem a pessoa é. Nada disso uma
lista de expressões proibidas alcança.

**Conserto 1 — ensinar por transformação, não por proibição.** O prompt nomeia
3 movimentos ((1) troque quem-você-é pelo que-você-quer; (2) suba o substantivo
um degrau; (3) feche com promessa de método) e mostra 3 PARES estreito→amplo,
com a frase explícita: *"não é a mesma frase sem o recorte — é OUTRA frase,
sobre o resultado"*.

**Conserto 2 — o prompt mostrava o que proibia.** O sorteio podia colocar
`alerta_exclusao` ("Nao mostre isso pra quem <X>") e `necessidade` ("Toda
pessoa que <X>") como "exemplo de tom" **na mesma mensagem** que mandava nunca
escrever aquilo. Exemplo concreto ganha de proibição abstrata quase sempre.
Filtrados pela MESMA função que julga a saída, então molde novo que feche porta
já nasce excluído.

**Conserto 3 — rótulo honesto.** `amplo/estreito` → `nao_fecha/fecha_porta`, e
a saída avisa que uma coisa não é a outra. Medir amplitude de verdade exigiria
julgar vocabulário e especificidade do substantivo (provavelmente com o próprio
Gemini). Até lá, **rótulo honesto e estreito vale mais que rótulo bonito e
falso** — foi o rótulo bonito que me fez reportar "85 amplos" pra uma coluna
que só media a ausência de uma expressão.

#### 🕳️ REJEIÇÃO POR FORMATO IA DIRETO PRA RESERVA (16/08)

Achado montando o teste do caminho de geração com um modelo simulado — o teste
falhou por um motivo que eu não tinha previsto:

    chamadas ao modelo: 1  (esperado 2)
    "Não mostre isso pra quem ama cabelo liso 👀"
    40 caracteres visíveis · piso HOOK_MIN_CHARS = 44  →  _limpar_saida = None

`_limpar_saida` devolvia `None` e o `None` caía **direto na reserva, sem
segunda chance**. O modelo escrevia algo aproveitável, errava o tamanho por 4
caracteres, e o vídeo saía com frase fixa de banco. Comportamento antigo, não
regressão — e explica parte dos **22% de posts com hook de reserva** medidos
hoje (`gerado 76 · reserva 22`, retenção 6,2 × 6,1s).

Conserto: `_limpar_saida(txt, motivos=None)` registra POR QUE rejeitou, **com o
número** ("tinha 40 caracteres e o mínimo é 44"), e a retentativa passa a
cobrir os dois motivos. Rejeição vira PEDIDO em vez de silêncio.

Verificado com modelo simulado, 5 caminhos: porta→reescreve e aceita ·
formato→reescreve e aceita · insiste 2×→`None` e vai pra reserva com warning ·
hook bom de primeira→1 chamada só (sem custo extra) · `HOOK_AMPLO=0`→volta ao
comportamento antigo.

#### 🛟 A RESERVA TEM QUE SER TÃO BOA QUANTO O NORMAL (16/08)

Pedido do Dre, depois de eu confundir hook de fallback com hook gerado:
*"não quero ver caindo no fallback e sendo um hook horroroso"*. Três defeitos
saíram de olhar o `HOOKS_RESERVA` a sério — todos do mesmo tipo: **degradação
silenciosa**, o pool encolhendo sem ninguém ver.

**1. 21 das 107 frases (20%) FECHAVAM a porta.** *"Não mostre isso pra quem
ama…"*, *"Toda pessoa que…"* — exatamente a forma que o gerador passou a
rejeitar. O Gemini caía e o vídeo saía com o hook que a regra nova proíbe.
Reescritas mantendo nicho, tom e emoji (*"Não mostre isso pra quem ama deixar a
casa organizada"* → *"Sua casa pode ficar organizada sem tomar o seu fim de
semana"*). Pool: 21 → **0** frases estreitas.

**2. E a faxina não bastava:** o `_fallback` agora aplica `filtra_publico` **em
tempo de uso**. Reescrever zera hoje; o filtro garante amanhã, quando alguém
adicionar frase nova — e o cabeçalho do arquivo convida a isso ("cresça à
vontade"). Verificado injetando uma frase estreita no banco: 0 de 80 sorteios a
trouxeram. **Régua que só roda no dia da limpeza não é régua.**

**3. 🐞 O BUG QUE FAZIA A RESERVA PARECER POBRE — e era o pior dos três.**
`_conflita` comparava a frase com o **nome** do produto, e nome é proxy ruim de
assunto: *"Organizador de Armário Dobrável"* não contém a palavra "casa", então
**toda** frase do pool da casa que dizia "casa" era descartada. Sobravam 3 de
15, e as mesmas 3 se repetiam — era isso que fazia o fallback parecer pobre.

    nicho      antes → depois (frases utilizáveis, produto real do nicho)
    casa           3 → 14
    cozinha        0 → 12      ← ZERO
    academia       6 →  8
    beleza         8 → 13

**A `cozinha` estava em ZERO.** O filtro rejeitava 100% do pool, e o
`sem_conflito or ... or pool` caía calado no pool inteiro — inclusive nas
frases que os outros filtros tinham acabado de reprovar. O guarda-chuva do
`or` transformava "não sobrou nada" em "serve qualquer coisa", sem log.

Conserto: `_conflita` recebe o `nicho` e ignora as famílias NATIVAS daquele
pool (`_NATIVO_DO_NICHO`). A frase veio do pool da casa; o assunto dela é o
assunto do pool, por construção.

#### 📐 REFINADO pelo framework da Ava Yuergens (16/08) — recebido, NÃO implementado

O Dre trouxe um carrossel do @joelsonmadeira_ (03/08) analisando a **Ava
Yuergens** (PBL, 350-400 clientes, ~US$700k/ano). A legenda em PT dizia:

> *"Quando você deixa de falar com um público muito específico e começa a
> falar com mais pessoas, seu conteúdo tende a viralizar."*

⚠️ **E ESSA LEGENDA É UMA SIMPLIFICAÇÃO QUE INVERTE METADE DA ESTRATÉGIA.** Eu
li só ela e reportei pro Dre que "bate de frente com o 2.5". Estava errado — a
formulação original tem **três** etapas, não uma:

    HOOK AMPLO      → maximiza watch time (ninguém é filtrado no segundo 0)
    VALOR ESTREITO  → entregue pro cliente ideal (a dor, o benefício concreto)
    CTA DE NICHO    → só quem serve converte

Não é *"amplo em vez de específico"*. É **amplo e específico, em PARTES
DIFERENTES do vídeo.** O que o 2.5 já tinha achado na Alana mistura os dois no
hook: *"não mostre isso pra quem ama flores"* é curiosity-gap (amplo) **e**
recorte de público (estreito) na mesma frase. A Ava separa: o gap fica no
hook, o recorte desce pro corpo.

✅ **E NÓS JÁ TEMOS 2 DAS 3 PEÇAS**, o que torna isto ajuste, não obra:

| etapa da Ava | onde já vive | estado |
|---|---|---|
| hook amplo | `hook_alana.FORMULAS` (10 moldes) | **misturado** — 3 moldes são estreitos |
| valor estreito | `narracao_ia._PROMPT` passo (1) e (2) | ✅ já faz: "dorzinha, incômodo comum" + 1 benefício |
| CTA de nicho | `narracao_ia._PROMPT` passo (3) | ⚠️ existe, mas é **genérico** ("link da bio") |

**Os 3 moldes que filtram público no segundo 0** (contra o framework):
`necessidade` ("Toda pessoa que <gosta de X> precisa ter isso"),
`alerta_exclusao` ("Não mostre isso pra quem <ama X>"), `cumplice_humor`.
Os outros 7 já são amplos — inclusive os 4 de 1ª pessoa que o Dre priorizou
(`comprei_testei`, `virei_fa`, `eu_vs_shopee`, `desabafo_shopee`): história
pessoal não filtra ninguém.

⚠️ **O QUE EU NÃO COPIARIA IGUAL: o "CTA de nicho".** A Ava vende serviço de
ticket alto pra dono de negócio — filtrar quem clica é lucro, porque cada lead
errado custa atendimento. Nós vendemos comissão de item de R$30 por impulso:
**filtrar clique é perder comissão.** A adaptação honesta é o CTA ficar
específico **do produto**, não do público.

✅ **SLIDES RECEBIDOS (16/08) — o carrossel confirma as 3 etapas.** O slide
"PÚBLICO QUALIFICADO" fecha em caixa preta: *"o começo é amplo a ponto de
atrair todo mundo, mas do meio para o final, você pode e DEVE ser específico."*
Era exatamente a leitura de três etapas; a legenda é que só carregava a
primeira. Dois achados que só os slides deram:

**1. O mecanismo alegado é ALGORÍTMICO, não de gosto.** *"Se você filtrar muita
gente no começo, o algoritmo entende que aquele vídeo é ruim e não distribui
pra mais pessoas. É por isso que você não passa das 300 views."* Ou seja: o
custo do gancho estreito é pago em **ALCANCE**, não em retenção de quem ficou.
**Isso invalida o jeito como a gente vinha medindo hook.** A tabela de moldes
do `analise_retencao` compara `retencao_s` — mediria a tese no eixo errado e
concluiria "não tem efeito" mesmo se ela fosse verdadeira.

**2. "Amplo" NÃO é "genérico" — é um degrau acima no MESMO assunto.** O exemplo
de pets prova:

| | |
|---|---|
| estreito | *"se você tem um **golden** que come tudo, ensine isso"* |
| amplo | *"quer um **cachorro** que não come nada do chão? siga esses passos"* |

O amplo continua falando de cachorro. Isso **derruba a objeção que eu tinha
levantado** ("hook amplo em conta de nicho vira vago"): não se sobe até "todo
mundo", sobe-se de golden para cachorro. Numa conta de nicho o degrau existe e
é curto.

🔧 **FEITO (16/08): `analise_retencao` ganhou o eixo AMPLO × ESTREITO.**
Classifica cada hook do ledger por *"exige pertencer a um grupo pra continuar
assistindo?"* e compara os dois baldes em **alcance**, não só em retenção.
Os baldes também resolvem a falta de potência: a tabela de moldes tem n=5..9
por grupo (onde 0,8s de espalhamento morre contra ±1,0s de ruído); dois baldes
juntam os MESMOS posts em grupos ~10× maiores. Mesma amostra, pergunta que ela
consegue responder. Recusa comparar com <8 de cada lado, imprime exemplos dos
dois baldes pra classificação poder ser conferida a olho, e avisa que o piso de
ruído do alcance sai largo (cauda longa) — logo "não separou" é fraco ali, mas
"separou" seria forte.

⚠️ **O CLASSIFICADOR TEM UM PONTO CEGO CONHECIDO, e ele quase passou batido.**
O carrossel tem DOIS tipos de recorte: de **público** ("se você tem um golden")
e de **objeto** ("review do livro Pai Rico" — só quem conhece o livro assiste).
A função detecta o primeiro e chama o segundo de "amplo". Descobri montando o
teste: escrevi `esperava amplo` pro exemplo do livro, e o teste passou **12/12**
— porque **o gabarito era a minha própria limitação**. Teste que herda o ponto
cego do código passa sempre. Fica como está porque nossos hooks não nomeiam o
produto (o curiosity-gap existe pra escondê-lo), mas está anotado no docstring:
se os hooks passarem a citar marca/modelo, falta um segundo detector.

⚠️ **E A COLISÃO QUE ISTO CRIA COM O PRÓPRIO 2.5, dita sem maquiagem:** o
exemplo que o Dre elogiou na Alana — *"não mostre isso pra quem ama flores"* —
é **exatamente a forma que a Ava chama de flop**. Nomeia um grupo na primeira
linha. Os dois são observação do Dre, em datas diferentes, e **não dá pra
"conciliar" no papel**: ou a Alana vende apesar disso, ou o alcance dela seria
maior sem isso, e nenhuma das duas se decide argumentando. Temos 2 dos 10
moldes nessa forma (`necessidade`, `alerta_exclusao`) rodando em produção
agora — então a comparação é contra dado nosso, não contra teoria de ninguém.

🚧 **BLOQUEIO PRA DECIDIR ISSO COM DINHEIRO:** o `sub_id` usa 4 de 5 etiquetas
(`[canal, nicho, produto, FONTE]`) e **nenhuma identifica o vídeo** — então
venda não se liga a hook. A 5ª está livre, e o docstring do
`shopee_affiliate.gerar_link_afiliado` já sugeria o uso: `["tiktok",
"cortador", "video01"]`. Sem ela, "amplo vende mais?" só se responde por
retenção — e a retenção já provou não separar molde (n=80, 0,8s de spread
contra ±1,0s de ruído).

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
  ~~**Rampa recomendada:** teto 2 → 3 → 4-5~~ Ligar no `agendador_config.json`
  (recarrega sozinho; código novo precisa `systemctl restart jarvis.service`).
  - 🛑 **SUPERADO — NÃO LEIA A RAMPA ACIMA.** Correção do Dre em 16/08: o
    `post_por_conta` **já está LIGADO na VPS** há tempos, e a rampa linear
    2→3→4 **nunca foi o desenho**. O que roda é a **PIRÂMIDE SEMANAL**,
    `posts_por_dia_semana: [3, 2, 1, 3, 2, 1, 0]` (seg→dom, POR CONTA), com
    `horarios_por_volume` casando o espaçamento ao volume do dia (1 post →
    manhã; 2 → 9h/18h; 3 → 9h/13h/18h30). Volume igual todo dia faria os Reels
    da MESMA conta disputarem a mesma janela de entrega. A verdade viva está em
    `daemon_maestro.py:108-133` e no `agendador_config.json` da VPS.
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
- ✅ **1º post real pela API confirmado** (SELF_ONLY, sandbox) + review SUBMETIDO
  (2026-07-19).
- 🛑 **REPROVADO — ARQUIVADO. NÃO É MAIS OBJETIVO** (registrado 16/08, correção
  do Dre). O TikTok **não liberou**: a Content Posting API é concedida a
  **empresa**, não a uso pessoal. Não é questão de reenviar nem de ajustar o
  formulário — o critério é quem somos, não o que mandamos.
  **Nada disso está quebrado e nada precisa de conserto**; o motor
  (`tiktok_poster.py`), o painel, o Caddy, o subdomínio e as páginas legais
  continuam no disco, gated em `postar_tiktok: false`, e ficam aí caso um dia
  exista CNPJ. **Não me proponha "conferir o resultado da review" de novo** —
  o resultado é este, e ficou 4 semanas parecendo pendência aberta só porque
  ninguém escreveu o "não" aqui.
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
- ✅ **geral (@topshop.__)** — RESOLVIDO há ~3 meses (corrigido em 31/08, quando
  eu listei isso como pendência aberta e o Dre respondeu *"não renderiza em
  fundo preto já tem 3 meses"*).
  ⚠️ **Pendência marcada e nunca desmarcada vira mentira com aparência de
  registro** — e o custo é pior que o de não ter registro nenhum: eu li o
  roadmap, confiei nele e recomendei trabalho já feito. Ao fechar um item,
  desmarcar é parte do conserto.

---

## 🗓️ Dia 2026-09-02 — cada conta ganhou cor, e o vídeo saiu de dentro da moldura

### 👀 O QUE OS DOIS PERFIS QUE CRESCEM FAZEM E O NOSSO NÃO FAZIA

O Dre mandou três prints lado a lado: **@achad0ideal** (1 mês, 16k), o nosso
**@topshop.__** e **@ofertasdaflorzinha** (3 anos, 450k). A leitura dele:
*"o formato de vídeo dos dois é idêntico, já o meu? muito diferente"*. Está
certo, e as diferenças de layout são cinco:

| | eles | nós (antes) |
|---|---|---|
| fundo | claro, com cor própria | preto, igual em tudo |
| vídeo | quase da borda, 90%+ | 82%, sobrando moldura |
| vídeo (fim) | ~93% da altura | 86%, e ainda vinha CTA |
| CTA no vídeo | **nenhum** — vai na legenda | `COMENTE "QUERO"` queimado |
| cabeçalho | ~11% do topo, grande | 5,8%, pequeno |

**MAS O DEFEITO MAIOR NÃO É LAYOUT, É PAREAMENTO.** No print do @topshop.__,
o gancho queimado no vídeo diz *"Eu vivia recarregando o gás do ar do carro
sem resolver"* e a legenda, logo ao lado, fala de **sono, temperatura ambiente
e termorregulação**. São dois produtos diferentes no mesmo post. Nenhuma paleta
conserta isso, e é o tipo de coisa que faz a pessoa sair do perfil.

Não achei a causa — procurei e descartei duas hipóteses: `hook_alana` não tem
cache, e no caminho do hunter o `campeao` que alimenta gancho e legenda é o
MESMO dicionário da mineração. Fica registrado como aberto, com o print como
prova, em vez de virar uma teoria bonita que ninguém verificou.

Segundo ponto de registro: o REGISTRO da legenda. A nossa lê como *resumo de
artigo* ("Em termos de neurociência do sono..."); a da florzinha lê como
conversa ("Outro detalhe que achei interessante é..."). Mesmo produto, duas
distâncias diferentes de quem lê.

### 🎨 A PALETA VIROU MÓDULO, PORQUE A REGRA ESTAVA EM TRÊS ARQUIVOS

O "fundo" era uma PALAVRA — preto/branco/bege — decidida por uma linha
copiada três vezes:

```
_bg_padrao = "preto" if nicho in ("geral","") else "branco"
produzir_tiktok:408 · telegram_repurpose_hunter:1674 · render:485
```

Três cópias é o desenho exato que fez o @topshopcasa_ publicar com a logo do
@topshop.__ (o dicionário sem "casa", em dois arquivos). Com 6 nichos e uma
cor pra cada, não sobreviveria. Agora é **`shared/paleta.py`**, importado.

| nicho | fundo | |
|---|---|---|
| geral | `#FFFFFF` | branco puro — **era preto**, o grid do @topshop.__ vai ficar misto por semanas |
| moda | `#E6DFD3` | areia |
| beleza | `#F7E6E3` | rosa-quartzo claro |
| casa | `#DFE5D8` | sálvia clara |
| tech | `#0E0E10` | grafite |
| pet | `#FDEBB8` | amarelo-sol suave |

**O `claro` É DERIVADO DA LUMINÂNCIA, não é coluna da tabela.** O pedido do Dre
tinha uma contradição literal — *"tecnologia: preto puro"* e *"a fonte deve ser
preta"* — resolvida por ele mesmo duas linhas depois (*"se o fundo for escuro,
a letra deve ser branca"*). Derivando, essa regra deixa de depender de alguém
lembrar dela: paleta escura não CONSEGUE gerar tinta escura, nem que troquem o
hex amanhã. Verificado: `FORCE_BG=preto` num nicho claro devolve tinta branca.

### 📐 O QUE MUDOU DE GEOMETRIA (e o que eu deliberadamente não toquei)

`VIDEO_W_FRAC` 0,82→**0,90** · `VIDEO_Y` 470→**500** · `LOGO_TAM` 120→**140** ·
`LOGO_Y` 112→**168** · `HK_FONT` 48→**60** · `HK_ALT_LINHA` 62→**76** ·
`VIDEO_RAIO` **28** (novo) · `CTA_ATIVO` **0**.

O vídeo passa a ir de y=500 a y=1796 (972×1296). A faixa acima dele fica
lotada: 168 de topo + 140 de logo + 24 de vão + 152 de gancho + 16 = 500,
zero folga. Por isso o encolhimento do gancho passou a mirar **2 linhas** (era
"até a maior palavra caber", que deixava 3 passarem) e, quando nem em 34px
cabe, o log **grita com o texto inteiro**. Exercitado com stub: gancho de 145
caracteres → 3 linhas → aviso.

**LOGO_X e HK_MARGEM viraram DERIVADOS da borda do vídeo.** O render.py já
amarrava texto e mídia na mesma coluna; o narrated_video_agent não, e usava
`LOGO_X=100` absoluto — com o vídeo indo pra 0,90 a borda vai de 97 pra 54 e o
cabeçalho ficaria 46px pra dentro do vídeo.

**O QUE NÃO MEXI, DE PROPÓSITO:** `NOME_FONT` (52), `HANDLE_FONT` (42),
`TEXTO_DX` (8), `SELO_DX` (28). Eu tinha listado os três primeiros pra remoção,
e a **primeira prévia renderizada** mostrou por quê era errado: com o nome
saltando de 52 pra 65, o selo verificado foi parar EM CIMA do
`@topshopbeauty._`. O pedido era *"aumentar + o logo"*, não aumentar o nome —
alargar o escopo sozinho criou um defeito que não existia. De quebra, o padrão
do código (56/46, letra morta) foi alinhado ao valor real de produção (52/42),
e agora os dois renderizadores concordam.

### 🔵 O SELO PENDURA NO NOME, NÃO NO LOGO

Primeira tentativa: escalei `handle_dy`, `selo_dy` e `selo_tam` por
`LOGO_TAM/120`. Errado — o vão entre o nome e o @ é fato tipográfico do
**tamanho do nome**, e as duas escalas divergem (logo 1,17×, nome 1,25×).
Agora derivam de `NOME_FONT`, com constantes que reproduzem EXATAMENTE os
números de produção quando `NOME_FONT=52`: 1,038 → dy 42 · 0,50 → dy 14 ·
0,885 → tam 46. No tamanho de hoje nada muda; em qualquer outro, a relação se
mantém em vez de virar três números novos pra acertar no olho.

### ⭕ CANTO ARREDONDADO SEM MÁSCARA — e a matemática que estava errada

`_cantos_arredondados` **pinta o canto com a cor do fundo** em vez de usar
máscara alfa. Escolha, não atalho: máscara no MoviePy muda de API entre v1 e v2
e falha diferente em cada uma; e aqui o vídeo é SEMPRE composto sobre um
`ColorClip` sólido da paleta, então pintar é indistinguível de recortar.
⚠️ Por isso mesmo NÃO serve sobre fundo com foto.

A primeira versão usava o índice do pixel no SDF. Medido antes de subir:
**5.180 pixels tocados por quadro** em vez dos ~700 dos quatro cantos — a borda
reta inteira caía exatamente sobre o contorno e ganhava meio-tom, ou seja, um
**halo de 1px da cor do fundo em volta do vídeo inteiro**. É o centro do pixel
(+0,5) que conta. Depois do conserto: 788 pixels, bordas retas intactas.

### 🔤 A MONTSERRAT ESTÁTICA NÃO EXISTE MAIS

Testado antes de escrever: `ofl/montserrat/static/Montserrat-Light.ttf` → **404**;
só existe a variável `Montserrat[wght].ttf`. E baixar a variável e torcer não
resolve: o Pillow a abriria no peso padrão (400) e o "Light" sairia Regular,
**sem erro nenhum**. Então `baixar_fontes.py` agora FATIA com
`fontTools.varLib.instancer` (testado: sai com name "Montserrat Light", sem
fvar, Pillow lê `('Montserrat','Light')`). Poppins entra como plano B de
verdade, porque o fontTools pode não estar no venv.

E o fallback GRITA: cair na Liberation é entregar o feed velho achando que
entregou o novo — o mesmo silêncio da logo errada.

### ⚙️ `layout_v2.py` — porque mudar o código NÃO muda o vídeo

16 chaves: 9 pra definir, 7 pra REMOVER. **A mais perigosa é `TOPSHOP_BG`**: se
estiver fixa no `.env`, as 6 contas renderizam na mesma cor e a paleta inteira
fica invisível, sem erro em lugar nenhum. Sem `--aplicar` o script só mostra.

### 🚧 O QUE NÃO FIZ, E POR QUE ESTÁ DITO

- **Palavra em destaque (amarelo/verde-neon).** As cores existem na paleta
  (`destaque_hex`), mas NINGUÉM as pinta: o gerador de gancho não marca palavra
  nenhuma. O Dre situou o item no *"foco pra explodir os reels DEPOIS quando
  utilizarmos a ferramenta"*. Meio-construído seria pior que não construído.
- **Áudio em alta por conta** — subsistema separado (`audio_selector_agent`).
- **Destaques numerados (01-50, 51-100)** e **canal exclusivo aos 5k** — são
  automação de Instagram, não de render. Ficam pra etapa própria.

### 🚗 O GANCHO DO CARRO: achado, e é ESTRUTURAL

O Dre confirmou o produto: climatizador de ambiente. Vídeo resfriando o quarto,
legenda sobre dormir bem, e o gancho na tela dizendo *"Eu vivia recarregando o
gás do ar do CARRO sem resolver"*. E ele nomeou o custo melhor do que eu:
*"é por causa dessas coisas que mata o vídeo e a retenção cai, às vezes foi
entregue pro público errado"*.

A pista que resolveu foi dele: **"a legenda é sempre a certa"**. Gancho e
legenda saem do MESMO `nome_produto` + `descricao`, os dois pelo Gemini
(`gerar_hook_alana` / `gerar_legenda_curiosidade`). Se uma acerta e a outra
erra com a mesma entrada, a diferença está no que cada uma atravessa depois.

E estava. `_conflita()` — a regra que pergunta *"a frase fala de uma coisa que
o produto não é?"* — só era chamada em UM lugar: `_fallback`, linha 512, sobre
o banco de reserva. **O gancho do Gemini ia direto pra tela sem nenhuma
checagem de assunto.** Duas correções:

1. `_conflita` passa a filtrar TAMBÉM a saída do Gemini, recebendo a descrição
   junto do nome (é o mesmo texto que o modelo leu — se a descrição fala de
   carro, gancho de carro é legítimo; a regra barra invenção, não assunto).
2. `_CONCRETO` ganhou **família de veículo**. Não existia nenhuma: nem na
   reserva "carro" seria barrado. "Ar condicionado" puxa "ar do carro" fácil.

### 🔁 E UMA CORREÇÃO ANULAVA A OUTRA

Testando, apareceu o que eu não procurava: `_conflita("Meu celular vivia
descarregando", "Mouse Gamer", nicho="tech")` devolve **False**. O mouse de
03/08 — o caso que CRIOU a função — passaria de novo hoje. A isenção
`_NATIVO_DO_NICHO`, adicionada em 16/08 pra não esvaziar o banco da casa
(3 frases de 14), faz `continue` em "celular" porque ela é nativa de tech.

As duas estão certas e se anulavam. Resolvido por CONTEXTO, não por regra única:

| caminho | pool | rigor |
|---|---|---|
| reserva | finito, esvaziar dói | `estrito=False` — isenção vale |
| Gemini | pede outro, é de graça | `estrito=True` — sem isenção |

Rigor é barato onde existe segunda tentativa e caro onde não existe. Os dois
casos históricos voltam a ser barrados, e o organizador de armário de 16/08
continua passando. 6 casos verificados.

### 📓 `diag_gancho.py` — foi 1 post ou 30?

Consertar é metade; a outra é saber o tamanho. O gancho fica queimado no vídeo
e só é legível assistindo cada um — mas o `posts_ledger.jsonl` grava o gancho
de todo post desde sempre. O diagnóstico roda a regra nova sobre o passado e
lista os posts com produto, gancho e legenda lado a lado. Usa a LEGENDA como
retrato do produto, justamente porque ela é a que acerta. Não conserta nada:
os posts listados já estão no ar.

### 🔵 O SELO — e a metade da correção de 19/08 que ficou faltando

O Dre, na prévia: *"só o selo mesmo ficou desalinhado"*. Estava, e a causa é a
MESMA de 19/08 ("medir uma coisa e desenhar outra") — só que na vertical, onde
o conserto nunca foi feito. O x já media o clipe desenhado; o y era `logo_y +
14`, cravado no olho, que não sabe onde a tinta do nome começa nem quanto mede.
Com handle curto (@topshop.__) a folga escondia; com @topshopbeauty._ o selo
encostava no @.

A `margin=(_m,_m)` do `_textclip_esq` é (x, y): `.h` carrega a mesma margem
transparente que `.w` carrega nos lados. Então a tinta mede `h - 2m` e o selo
centra nela. Conferido no recorte do cabeçalho.

### 🎨 TOM: moda e beleza saíram claras demais

Reação do Dre à prévia. `previa_paleta.py --fundo moda=#DDD2BE` passa a existir
pra testar tom sem editar código — decidir cor é olhar, e olhar precisa ser
barato. Três degraus renderizados pra cada um; a escolha é dele.

### 🔧 fontTools não estava no venv da VPS

`.venv/bin/python baixar_fontes.py` → `No module named 'fontTools'`. A Poppins
veio (é estática), a Montserrat não (precisa ser fatiada da variável). O plano
B funcionou como desenhado. Falta `.venv/bin/pip install fonttools`.

Nota boa do mesmo log: `TOPSHOP_BG`, `FORCE_BG`, `HOOK_FONTE` e
`HOOK_FONTE_PRETO` **não estão no `.env`** — a chave que anularia a paleta
inteira já estava limpa.

### 💬 O 1º COMENTÁRIO: 3 frases, e a régua que nunca chegou aqui

O Dre: *"o primeiro comentário que o jarvis faz no post tá muito feio, vamos
fixar 3 melhores frases pra ele, até mesmo dá pra divulgar o grupo do whats"*.

O banco existia desde 22/08 (reclamação dele sobre REPETIÇÃO). O problema agora
era a QUALIDADE — e uma das frases era *"esse aqui some rápido, corre ver na
bio"*: a MESMA construção que ele vetou nos ganchos em 21/08 (*"'corre ver isso'
é gramaticalmente errado [...] só é um anúncio"*). A régua entrou no
`hook_alana` e nunca chegou ao `comentarios.py`. **Régua que vale num arquivo só
não é régua.**

Molde novo, 3 por formato: uma fala do PRODUTO, uma pede AÇÃO barata
(salvar/comentar), uma leva pro GRUPO DO WHATSAPP. 1 em 3 e não 3 em 3 —
encher os grupos é meta corrente, mas todo comentário puxando pro grupo vira
panfleto. Medido em 600 sorteios: 34,7% / 33,5% / 31,8%.

⚠️ **No Instagram link em comentário NÃO É CLICÁVEL.** Por isso a frase do grupo
manda pra BIO, onde o botão já existe (topshopoficial.com.br). No Facebook, onde
o link funciona, vai o `chat.whatsapp.com` direto — e vem de
`bio_page_builder.GRUPO_WHATSAPP`, não copiado: duas cópias do convite
significam que, no dia em que ele for trocado, uma manda gente pra grupo morto
sem dar erro em lugar nenhum.

### 🔁 ENCURTAR O BANCO QUASE MATOU O ANTI-REPETIÇÃO — DUAS VEZES

`LEMBRAR=4` com banco de 3: as 3 ficariam "recentes", `novas` sairia vazia e o
`or disponiveis` cairia em **sorteio puro** — exatamente o que o arquivo existe
pra impedir, sem sintoma nenhum além de frases repetindo. Lembrar de tudo é o
mesmo que não lembrar de nada.

Primeira correção: `teto = len - 1`. Renderizei e estava errada também — com 3
frases ele lembra 2, sobra 1 candidata e a rotação vira **ciclo fixo
1-2-3-1-2-3**. Nunca repete, e lê como robô do mesmo jeito, só que por
regularidade. `teto = len // 2` resolve os dois e preserva o comportamento de
hoje nos bancos de 8 (lembrava 4). Verificado: 0 repetições consecutivas em 13
transições, sem ciclo.

### 🔵 CENTRO GEOMÉTRICO ≠ CENTRO ÓPTICO

Depois de centrar o selo na tinta medida, o Dre: *"selo um pouco + pra cima"*.
Ele está certo e tem nome: o olho alinha pela altura-x das minúsculas, não pela
caixa da fonte, e "TopShop" tem só duas maiúsculas. Medir resolveu o
desalinhamento grosso; o ajuste fino é percepção, não geometria. `SELO_SUBIR`,
8% do corpo do nome (4px em NOME_FONT=52).

### 🎨 TOM FECHADO

moda `#E6DFD3` → **`#DDD2BE`** · beleza `#F7E6E3` → **`#F0D5D0`** (+1 tom cada,
escolha dele olhando os três degraus renderizados). As outras quatro ficam.

### ✅ A DÍVIDA DO Jul16 ESTÁ VENCIDA

`diff agents/narrated_video_agent.py` contra a versão nova: 47 linhas só na VPS,
e **todas** das regiões que eu editei (o bloco de paleta antigo, o de fonte, o
comentário do encolhimento). Os dois arquivos estavam em sincronia — a nota de
dívida no roadmap descrevia um estado que já não existia. Deploy liberado.

### 📏 18,3% ERA MENTIRA — E EU QUASE ENTREGUEI COMO VERDADE

O `diag_gancho` rodou sobre os 120 últimos posts e apontou **22 (18,3%)**. Li os
22 um a um antes de comentar. **19 eram FALSO POSITIVO**, e 19 pelo MESMO
motivo — a palavra "casa" ou "cozinha":

| produto | gancho apontado | veredito |
|---|---|---|
| Triturador de Alimentos | "cortar uma coisinha de nada **na cozinha**" | perfeito |
| Modelador de Cachos | "cabelo de salão **em casa** era só talento" | perfeito |
| Pipoqueira | "snack de filme **em casa** vinha com culpa" | perfeito |
| Fechadura Digital | "quem tinha acesso à **minha casa**" | perfeito |

Em português, "em casa" e "na cozinha" são **CENÁRIO** — onde a cena acontece —
e quase todo gancho relatável usa um dos dois. Exigir que o NOME DO PRODUTO
contenha "casa" pra liberar a frase é exigir uma coisa que quase nenhum produto
de casa tem no nome ("Kit Porta Temperos").

Duas consequências, e a segunda é a grave:
1. eu quase entreguei 18,3% como o tamanho do problema — **medição errada
   virando decisão**, o defeito que o `shared/categorias.py` inteiro existe pra
   impedir;
2. em produção o filtro estaria **rejeitando ganchos bons** e empurrando um em
   cada seis pro banco de reserva, em silêncio.

Conserto: `_AMBIENTE` — palavras que dizem ONDE/EM QUE ATIVIDADE, excluídas do
filtro estrito. "celular", "cabelo", "cachorro", "roupa", "carro" ficam de fora
dela: nomeiam OBJETO, e objeto errado é o defeito que a gente caça.

Dois buracos de vocabulário achados no mesmo exercício: "Modelador Cachos" não
casava com a família `cabelo` (faltavam cachos/modelador/chapinha) e "Relógio de
Pulso" não casava com `roupa` (faltavam relógio/bolsa/óculos — "estar arrumado"
é sobre eles também).

**Placar final nos 24 casos** (22 reais + os 2 históricos): 19 falsos positivos
→ 3, os 5 mismatches reais todos pegos, 0 falso negativo grave. Os 3 que sobram
são retóricos ("só carro e casa passavam de pai pra filho" num relógio) e o
custo é uma retentativa.

### 💬 AS FRASES DO DRE GANHARAM DAS MINHAS, E A DIFERENÇA É ENSINÁVEL

Ele mandou 6. Ficaram as 6 (pediu 3; banco maior = menos cara de robô, custo
zero). O que as dele têm:

```
minha:  "salva aí pra não perder depois"                        DESCREVE
dele:   "salva aí antes que você esqueça o nome 😂"              CONVERSA
dele:   "o perigo é comprar um e depois querer outro"           tem OPINIÃO
dele:   "quero saber se presta mesmo 👀 comenta uma nota"        admite DÚVIDA
```

Opinião, pergunta de verdade e dúvida — três coisas que um anúncio não faz. É a
mesma régua dos ganchos aplicada ao comentário. ⚠️ O CARROSSEL NÃO HERDA as
seis: quatro falam de COMPRAR, e num post de "3 erros" perguntar "alguém já tem
um desses?" é falar de um produto que o post não mostrou.

### 🔬 `estudo_ganchos.py` — a pergunta dos ganchos vira medição

O Dre: *"quero que o jarvis estude os melhores ganchos [...] pode dar uma olhada
nesses perfis"*. Eu podia responder com opinião. Em 01/09 isso já quase custou
caro — apliquei CTR de tráfego pago numa pergunta de social orgânico e ele me
parou. A lição vale aqui: gancho que funciona pro @achad0ideal é **hipótese**,
não resposta.

E o dado existe: `metricas_posts.jsonl` grava **hook + alcance + curtidas** por
post. Então o script classifica cada gancho por traço ESTRUTURAL (pessoa
gramatical, pergunta, condicional, imperativo negativo, contraste, abertura,
tamanho, cita ou não o produto) e compara a MEDIANA de quem tem contra quem não
tem.

As hipóteses vieram dos dois perfis: @achad0ideal usa 2ª pessoa + imperativo
negativo (*"não mostre isso a uma pessoa friorenta"* — convida a MARCAR alguém);
@ofertasdaflorzinha usa condicional (*"Se você tem uma estante de livros"* —
filtra por identificação). **Nenhum dos dois usa a nossa forma dominante**
("Eu vivia…", "Achava que…"), que é 1ª pessoa e testemunho. Essa é a hipótese
central a testar.

Três defesas contra superstição, porque n é pequeno: mediana e não média (um
viral distorce média), traço com <8 posts sai marcado "pouco caso", e a mediana
geral fica impressa ao lado pra comparação ser contra a base. O cabeçalho diz na
cara que **não isola o gancho** — alcance vem de gancho + produto + vídeo +
áudio + horário juntos.

⚠️ **O script mede, não conclui, e ainda não mudou nenhum prompt.** Só depois de
ver a tabela com os dados reais é que vale mexer no `hook_alana` — mudar o
gerador antes de ler a medição seria trocar meu gosto pelo gosto anterior.

### 📉 A 1ª RODADA DO ESTUDO: o número gigante era artefato, e o resto é ruído

329 posts. A tabela veio com **"tem emoji +3767%"** e todo o resto entre -8% e
+13%. Os dois fatos são o mesmo fato: **a ferramenta estava medindo errado.**

**O 3767% é falso.** O grupo "sem emoji" tinha 22 posts com mediana de alcance
**3**. Post com alcance 3 não é post com pouco emoji — é post que o Instagram
não entregou. Dividir por um número perto de zero explode qualquer diferença.

Três consertos, e o terceiro é o que mais importa:

1. **Post não entregue sai da conta.** O guard de "grupo morto" trata o sintoma
   numa linha; a causa é que esses posts entram no grupo "sem" de TODO traço e
   puxam todas as comparações. Piso: 10% da mediana da própria conta, e a
   quantidade descartada é IMPRESSA — descarte silencioso é como se fabrica um
   número bonito sem perceber.
2. **Carrossel fora do padrão.** O fundo da lista era carrossel, não Reel — o
   próprio `metricas_posts.py` avisa que "as duas coisas têm alcance típico bem
   diferente". Misturar compara FORMATO, não gancho.
3. **Normalização por conta.** Alcance bruto carrega o tamanho da conta junto:
   um traço que por acaso aparece mais no @topshop.__ ganha um bônus que é da
   conta. Cada post virou "× a mediana da PRÓPRIA conta" — 1,0 é um post mediano
   em qualquer conta.

### 🔍 E O ACHADO REAL NÃO ESTAVA NA TABELA

Com tudo dentro de ±13%, a leitura honesta é: **nenhum traço de FORMA move o
ponteiro.** Não é fracasso da ferramenta — é resultado, e é o que o próprio
cabeçalho dela avisava ("a tabela conta a FORMA, e o que decide costuma estar no
assunto").

O que separa os 8 melhores dos 8 piores está no ASSUNTO:

| alcance | gancho |
|---|---|
| 1737 | "Nunca imaginei que ter **braços fortes** fosse tão rápido" |
| 1597 | "agora minhas **mãos** não param mais de ficar" |
| 1487 | "sentia falta daquele **conforto de telefone que não encosta na cara**" |
| 1388 | "**descarregar a raiva** seria tão simples" |
| 1288 | "Meu **braço** já tava pedindo socorro nos passeios" |
| — | — |
| 2 | "Pequenas coisas que mudaram meu dia a dia" |
| 2 | "Achadinhos que mudaram o jeito de me vestir" |
| 1 | "um bom cheiro era só pra ocasiões especiais" |

Os de cima têm **sensação física concreta** — braço, mão, raiva, o telefone
encostando na cara. Os de baixo têm **benefício abstrato**. Nenhum dos dois
grupos se distingue por pessoa gramatical, tamanho ou emoji.

⚠️ E UMA PROVA CONTRÁRIA, que fica registrada porque esconder seria pior: o 2º
maior alcance (1299) é *"Corre ver isso antes que viralize e suma das
prateleiras"* — a construção que o Dre vetou em 21/08. n=1, alcance não é
conversão, e o veto foi por marca (decisão dele, não medição). Mas o dado existe
e está aqui.

### ✳️ O DESTAQUE POR PALAVRA JÁ EXISTE — só não no Reel

Investigando os `*asteriscos*` no fundo da lista: eles não são lixo, são o
MARCADOR DE DESTAQUE, e `carrossel_render._RX_MARCA` já pinta a palavra marcada.
Ou seja, o item que o Dre pôs pra "depois, quando utilizarmos a ferramenta"
(*"apenas a palavra principal em amarelo ou verde-neon"*) tem convenção e
implementação prontas — falta portar pro renderizador de Reel, que é bem menos
do que eu tinha estimado.

### 🐕 A NORMALIZAÇÃO TINHA O MESMO BUG DO EMOJI, UMA CAMADA ACIMA

2ª rodada, com a tabela já limpa: `@topshoppet_` aparece com **mediana de
alcance 3**. Dividir por 3 transforma um post de 178 (que é pouco) em
**"59× a mediana"** — e ele sobe pro topo da lista passando na frente de um post
de 1737 de alcance real.

É o MESMO defeito do "+3767%": divisão por número perto de zero. Eu tinha
consertado no nível do traço e deixado passar no nível da conta. Conta que não
está sendo entregue não mede gancho — mede a conta. Agora sai, e o log diz qual
e por quê.

### ⚡ MEDIANA É CEGA PRA VIRAL — a métrica estava errada, não só suja

A 2ª rodada deu **TODOS os 15 traços dentro de ±14%**, todos marcados "dentro do
ruído". Parece "nada funciona". Não é: é a métrica errada.

A distribuição do alcance orgânico tem cauda pesada — mediana 1,0 e os melhores
posts em **11×, 13×, 14×**. A mediana é o post do MEIO, e o post do meio nunca
estoura. Um traço que DOBRE a chance de viralizar mexe quase nada nela.

E "estourar" é a pergunta que o Dre está fazendo. Ele não quer um post levemente
acima do meio; quer um viral. Então a coluna nova é **TAXA DE ESTOURO**: que
fração dos posts com o traço passou de 3× a mediana da própria conta.

Verificado num fixture com a forma real dos dados (cauda pesada, 8% de estouro,
traço plantado com 3× mais chance):

```
condicional (se/quem)     4/19  21,1%  ×  7/116  6,0%     mediana diz  -17%
1ª pessoa (eu/meu)        3/69   4,3%  ×  8/66  12,1%     mediana diz   +3%
```

A mediana aponta pro lado ERRADO nos dois. A taxa de estouro acerta os dois.
Guarda de superstição: traço com menos de 3 estouros sai marcado — 1 ou 2 é
coincidência com nome de achado.

### 🙃 E A MINHA LEITURA DOS 16 NÃO SOBREVIVEU AOS 16 SEGUINTES

Na 1ª rodada eu li os 8 melhores e os 8 piores e escrevi que o padrão era
**sensação física concreta** (braço, mão, raiva) contra benefício abstrato.
A 2ª rodada trouxe outros 16, e o fundo tem *"meus **pés cansados** faziam parte
do pacote"* e *"o segredo de uma **boca** 'uau'"* — as duas são sensação física,
as duas no fundo.

Eu achei um padrão em 8 itens e o próximo conjunto de 8 o desmentiu. É o mesmo
erro que passei a sessão inteira caçando nos outros lugares, cometido por mim na
leitura qualitativa. **Fica sem hipótese até a taxa de estouro falar** — inventar
a segunda história depois que a primeira caiu é como se constrói superstição.

### ⚡ 3ª RODADA: apareceu sinal, e os três primeiros dizem a mesma coisa

Com conta morta fora, posts não entregues fora, carrossel fora e normalização
por conta, **45 de 298 Reels estouraram (15,1% passaram de 3× a mediana da
própria conta)**. E a tabela deixou de ser plana:

| traço | estourou | sem o traço | × a base |
|---|---|---|---|
| abre com verbo de comando | **10/34 · 29,4%** | 13,3% | **2,2×** |
| condicional (se/quem) | **6/25 · 24,0%** | 14,3% | **1,7×** |
| imperativo negativo | **6/27 · 22,2%** | 14,4% | **1,5×** |
| 1ª pessoa (eu/meu) | 27/169 · 16,0% | 14,0% | 1,1× |
| 2 linhas | 6/52 · 11,5% | 15,9% | 0,7× |
| **cita o produto** | **5/47 · 10,6%** | 15,9% | **0,7×** |

Os três de cima têm a mesma natureza: **o gancho FALA COM A PESSOA usando um
verbo** — comando, condicional, imperativo negativo. São exatamente as fórmulas
dos dois perfis que o Dre mandou (@achad0ideal "não mostre isso a uma pessoa
friorenta", @ofertasdaflorzinha "Se você tem uma estante de livros"). A hipótese
que abriu o arquivo sobreviveu à medição.

E a nossa forma DOMINANTE — 1ª pessoa em testemunho, 169 dos 298 posts — está em
16,0% contra 14,0%: **em cima da base**. Não é ruim; é neutra. Metade do
catálogo escrito na forma que não move nada.

`cita o produto` em 0,7× é o achado contra-intuitivo: repetir o nome do produto
no gancho ATRAPALHA. Os dois perfis de referência não fazem isso — falam da
situação e deixam o produto aparecer no vídeo.

### 🔎 E POR ISSO EXISTE O `--detalhe`

⚠️ O traço vencedor casa `olha|veja|para|pare|corre|marca|salva|não` — e
**"corre" é a palavra da construção que o Dre vetou em 21/08**. Se metade dos 10
estouros forem "Corre ver isso antes que viralize…" (que está na lista dos 8
maiores alcances), o achado não é "verbo de comando": é uma frase específica que
ele não quer usar. Um agregado cuja composição ninguém abriu é como se
transforma medição em superstição — e esta sessão já teve três casos disso.

`--detalhe "verbo de comando"` lista os posts do traço e conta a primeira
palavra dos que estouraram. **Nenhuma regra vai pro prompt antes dessa conta.**

### 🐕 @topshoppet_: mediana 3 é problema de ENTREGA, não só de acervo

O Dre: *"topshoppet é foda pq não tem vídeo pra ele, preciso raspar perfis
virais do tiktok, ou produzir conteudo com os 3k"*. O acervo vazio é real e já
está registrado (`roteador_contas.py:171` — "ZERO pro @topshoppet_ e ZERO pro
@topshopmoda_, e as duas contas estavam no ar").

⚠️ MAS MEDIANA DE ALCANCE **3** NÃO É SINTOMA DE POUCO CONTEÚDO. Conta nova com
9 seguidores entrega mais que 3. As outras cinco estão entre 106 e 130 com o
mesmo sistema, o mesmo horário e o mesmo tipo de vídeo. Alcance 3 é o número de
uma conta que o Instagram parou de distribuir.

Isso muda a ordem de gastar: **comprar acervo (raspagem ou R$800 de Kling) pra
uma conta que não está sendo entregue é jogar conteúdo bom num cano fechado.**
Diagnosticar primeiro custa zero e leva minutos.

### 🧨 O `--detalhe` DESMONTOU O PRÓPRIO ACHADO — e era pra isso que ele existia

Abertos os dois traços vencedores, eles são **os mesmos posts contados três
vezes**. Os 6 estouros de "condicional" são exatamente os 6 de "imperativo
negativo", e ambos estão dentro dos 10 de "verbo de comando". Não são três
descobertas independentes: é uma fórmula, medida três vezes.

A composição real dos 10 estouros do traço vencedor:

| fórmula | estouros / posts | taxa |
|---|---|---|
| "Não mostre isso pra quem [identidade]" | 6 / 25 | 24% |
| "Corre ver isso antes que…" | 4 / ~7 | ~57% |

⚠️ A segunda é a construção **vetada pelo Dre em 21/08**. Ela tem a maior taxa
da tabela inteira — e mesmo assim NÃO vira recomendação: n=7, com **três textos
idênticos** entre os 4 estouros, e o veto foi de marca, que é decisão dele e não
medição. Registrado porque esconder prova contrária é pior que ter que explicá-la.

### 💥 O MESMO TEXTO DEU 1299 E DEU 103

Este é o achado que importa, e ele saiu de LER a lista em vez de somar:

```
"Corre ver isso antes que viralize e suma das prateleiras"   1299  (11,30×)
"Corre ver isso antes que viralize e suma das prateleiras"    103  ( 0,90×)

"Não mostre isso pra quem é apaixonado por tecnologia"       1178  (10,24×)
"Não mostre isso pra quem é apaixonado por tecnologia"        378  ( 3,29×)
"Não mostre isso pra quem é apaixonado por tecnologia"        134  ( 1,17×)
```

**Texto idêntico, 12× de diferença.** Com o gancho constante, tudo o que varia é
produto, vídeo, áudio e horário — e a variação é ENORME. Ou seja: a correlação
de forma existe (24% × 15%), mas ela é pequena perto do que o gancho **não**
explica.

📌 CONSEQUÊNCIA DIRETA PRA DECISÃO DOS R$3.000: **o gancho não é a alavanca.**
Vale ajustar o prompt (é de graça), mas quem está segurando o alcance é o VÍDEO.
Isso reforça a intuição que o Dre já tinha em 01/09 — *"acredito que o meio certo
é criar conteúdo com IA mesmo"* — e agora tem número por trás.

### 🐕 EU ERREI SOBRE O PET, E ELE ESTAVA CERTO

Na rodada anterior eu escrevi: *"mediana 3 é o número de uma conta que o
Instagram parou de distribuir"* e recomendei não gastar antes de diagnosticar.
**Estava errado.** O `diag_conta.py` mostrou o que a conta tem:

```
5 posts medidos em 7 semanas — e destes:
   2, 3, 3   →  "Ninguém acreditou que foi *só isso*…"   ← ASTERISCOS = CARROSSEL
   148, 178  →  os dois Reels de verdade
```

Os 148/178 estão **em linha com as outras contas** (106–131). A conta não está
punida: ela quase não posta, e a amostra medida é dominada por carrossel. A
causa é exatamente a que o Dre deu na primeira frase — *"topshoppet é foda pq
não tem vídeo pra ele"*. Acervo, não punição.

⚠️ E O DEFEITO ERA MEU DE NOVO: o filtro `--tipo reel` não pegou esses
carrosséis porque **nem todo carrossel tem o campo `tipo`** gravado. Eles vazaram
pro conjunto de Reel, derrubaram a mediana da conta pra 3, e a partir daí eu
construí uma teoria de punição em cima de um artefato. Terceira vez nesta sessão
que um número sujo quase virou decisão.

Conserto: o `*asterisco*` denuncia o carrossel (é o marcador do
`carrossel_render._RX_MARCA` e só existe lá). Heurística, mas de precisão alta,
custo zero, e melhor que confiar num campo que nem sempre foi gravado.

### 💰 O LOOP DO DINHEIRO FECHOU (o código; o número depende da API)

O Dre autorizou: *"quero, pode fazer"*. `shopee_affiliate.relatorio_conversao()`
+ `dinheiro.py`.

⚠️ **A FUNÇÃO NÃO ASSUME O SCHEMA.** O `probe_conversao.py` nunca foi rodado,
então eu NÃO SEI o nome da query nem os campos. Inventar um schema plausível
seria o pior desfecho: o código "funcionaria", devolveria vazio, e **vazio é
indistinguível de "não vendeu nada"**. Então ela descobre por introspecção,
tenta as formas conhecidas em ordem, e diz qual funcionou.

**Três desfechos, nomeados, nunca somados:**

| desfecho | o que é |
|---|---|
| `ok:False` | bug/schema — **"eu não sei"**, não "vendeu zero" |
| `ok:True`, 0 conversões | resultado de negócio: o clique não vira compra |
| conversão órfã | etiqueta quebrada, ou link publicado fora do Jarvis |

### 🧾 E O TESTE PEGOU UMA ATRIBUIÇÃO ERRADA ANTES DE SUBIR

Primeira versão casava por QUALQUER sub_id. O contrato é
`[canal, nicho, produto, FONTE, video]` — e as quatro primeiras **se repetem em
post após post**. "ig" é etiqueta de todos.

Medido no fixture: uma conversão de um vídeo que **não existe no diário** foi
contada como casada, e **R$4,75 inteiros foram creditados a um post que ganhou
R$1,50**.

Atribuição errada é pior que atribuição nenhuma — ela vira "esse formato
converte" e vira decisão de R$3.000. Regra nova, dura: etiqueta que aponta pra
mais de um post **não amarra nada**, e a conversão vira órfã declarada. Depois
do conserto: 2,35 → triturador · 1,50 → fone · 0,90 órfã. Correto.

### 🎬 "AINDA NÃO FIZEMOS VÍDEOS IA" — e isso é o item mais importante da decisão

O Dre: *"ainda não fizemos vídeos IAs, não sabemos fazer isso da maneira certa,
apesar de parecer simples."* É a observação mais valiosa da conversa, porque
nomeia o risco que o número de payback NÃO captura: **os R$800 compram créditos,
não habilidade.**

O que o projeto já tem: `video_provider.py` está **PLACEHOLDER** (o próprio
cabeçalho diz), `providers_config.json` tem `usar_api_video: false` e lista
kling/runway/pika como opções nunca ligadas. Ou seja, zero linhas de código
testadas contra qualquer API de vídeo por IA, e zero vídeos gerados.

📌 Consequência pro plano: comprar o pacote grande antes de gerar o primeiro
vídeo é pagar pela curva de aprendizado no preço cheio. O caminho barato existe
e não foi tentado.

### ✅ O RELATÓRIO DE CONVERSÃO EXISTE E RESPONDE (03/09)

O probe rodou. A API declara `conversionReport`, **`validatedReport`** e
`partnerOrderReport` — e o primeiro devolve dados reais:

```
conversionId 241989597136981 · Luva NitrilC5 · comissão 1,9593 · valor 27,99
conversionId 241978248105489 · Luva NitrilC5 · comissão 3,9186 · valor 55,98
conversionId 241484198105519 · Acessórios de fone · comissão 2,6865
```

⚠️ **R$8,56 em três conversões de 14 dias.** O roadmap registrava "R$1,67 no
total" — esse número está velho, ou nunca cobriu tudo.

⚠️ **E OS PRODUTOS NÃO SÃO DO CATÁLOGO.** "Luva NitrilC5 resistência a cortes
nível D(5) Medix" é EPI industrial; não é geral, casa, tech, moda, beleza nem
pet. Forte indício de que essa comissão **não veio dos posts do Jarvis** — o que
é exatamente o que a categoria "órfã" existe pra revelar, em vez de virar um
"cada post rende R$0,03" falso.

### 🐛 O `dinheiro.py` NÃO CARREGAVA O .env — de novo o mesmo defeito

Primeira execução real: o `probe_conversao.py` funcionou e o `dinheiro.py` disse
`SHOPEE_APP_ID não configurado`. A ÚNICA diferença é que o probe tem
`_carregar_env()` e eu esqueci no outro. Em produção o systemd injeta; na mão,
não.

O pior é o sintoma: sem o .env, o erro sai como **"não consegui ler o
relatório"** — indistinguível de problema de schema. O `hook_alana` tem um
parágrafo inteiro no cabeçalho sobre exatamente isso (*"era o único da cadeia
que NÃO carregava o .env"*), e eu repeti.

### 🏷️ O NÓ PODE NÃO TER sub_id — e aí a amarra some sem avisar

A consulta do probe não pediu etiquetas, então não se sabe se o nó tem. E
GraphQL **rejeita a consulta inteira** quando um campo não existe: pedir
`subIds` no escuro não devolve "sem subIds", devolve nada.

Agora a função INTROSPECTA o tipo do nó, descobre o nome real do campo
(`subIds` · `subId` · `utmContent` · …) e pede só o que existe. Quando não há
nenhum, o relatório **diz isso antes da tabela** — senão a saída viraria "100%
órfãs" e mandaria consertar as nossas etiquetas, quando o problema é que a API
não devolve etiqueta nenhuma. Diagnóstico errado conserta o lado errado.

Plano B da amarra: **itemId**. Mais fraco (dois posts do mesmo produto ficam
ambíguos, e aí a regra dura vale igual), mas é a diferença entre atribuir e não.

### 🚫 E COM ZERO CASADAS, NÃO EXISTE "VALOR POR POST"

Terceiro defeito pego no teste: com nenhuma conversão casada, a conta ainda
dividia o total — **incluindo as órfãs** — pelo número de posts. Isso credita ao
Jarvis venda que veio de outro lugar e produz "cada post vale R$0,0285", que é
número bonito e falso. Agora a conta usa **só o atribuído**, e com zero casadas
ela se recusa a calcular e diz por quê.

### 💸 "MELHOR JÁ COLOCAR OS 800 E FAZER 200+" — ele tem razão, e eu estava errado

Eu tinha sugerido R$50-100 pra 5-10 vídeos antes do pacote. O Dre: *"é melhor já
colocar os 800 e fazer 200+ kkkkk"*.

Ele está certo em duas frentes e eu estava errado numa:
1. **5-10 vídeos não ensinam workflow.** Dá pra ver se a ferramenta presta, não
   pra aprender a usá-la. Meu "teste" era pequeno demais pra responder a
   pergunta que eu mesmo disse que ele precisava responder.
2. **O custo unitário é 4× pior** (R$10-20/vídeo contra ~R$4).

O que continua valendo do meu lado, e é o que importa: **a variável de risco não
é o preço, é a VALIDADE do crédito.** R$800 de crédito que expira em 30 dias,
com workflow ainda não descoberto, é diferente de R$800 permanente. E duas
perguntas custam R$0 e se respondem na documentação antes de qualquer compra:

- o crédito expira? em quanto tempo?
- a saída é 9:16 / 3:4 nativo, ou só 16:9? (o template do Reel é 3:4)

### 💥 R$121,16 EM 90 DIAS — 85× o que o roadmap dizia

O `dinheiro.py` rodou de verdade: **34 conversões, R$121,16**. O roadmap
registrava *"R$1,67 no total"* e essa frase guiou meses de conversa sobre "o
funil não converte". **Convertia.** Ninguém tinha como ver.

⚠️ E 33 das 34 são ÓRFÃS. Eu tinha escrito no código que órfã "quase sempre é
venda de link publicado FORA do Jarvis". **Era palpite, e os nomes desmentem:**

```
R$ 13,48 + 10,52  Pedicuro Elétrico Profissional        → beleza
R$  8,00          INOVA FreeClip Fone Bluetooth         → tech
R$  5,36          Roupeiro Guarda-Roupa Portátil        → casa
R$  4,94          MEIDOO Prateleira para Cozinha        → casa
R$ 21,41          Macaco Jacaré Hidráulico              → esse sim, de fora
```

Quatro dos seis maiores são **exatamente os nossos nichos**. A amarra está
quebrada, não são vendas alheias.

### 🔑 A CHAVE NASCE VAZIA — e o `--amarra` provou

"33 órfãs" é sintoma, não diagnóstico. Órfã pode ser (a) venda de fora, (b)
etiqueta que a API não devolve, (c) chave vazia do NOSSO lado. Três consertos
diferentes, e só um é problema nosso. Contar órfã sem separar isso foi o que me
fez escrever "quase sempre é venda de fora".

`dinheiro.py --amarra` compara as duas chaves dos dois lados. Reproduzido em
fixture com a forma real dos dados:

```
com sub_ids gravados: 340 (100%)
com item_id gravado:    0 (  0%)      ⛔
itemIds nas conversões: 34 · no diário: 0 · em comum: 0
```

**`posts_ledger._item_id()` extrai o padrão `i.LOJA.ITEM` da URL — e o que é
gravado é o SHORT LINK de afiliado (`s.shopee.com.br/xxxx`), que não carrega
itemId nenhum.** A chave nasce vazia desde sempre.

E o sub_id, que está gravado em 100% dos posts, não resolve porque o nó do
`conversionReport` não devolve etiqueta (a introspecção do tipo do nó também
falhou — "não consegui listar").

📌 Ou seja: **as duas pontas da amarra estão rompidas, cada uma por um motivo
diferente**, e o dinheiro que já existe não tem como ser atribuído a post. Este
é o conserto que vale mais que qualquer decisão de gasto — sem ele, R$121 ou
R$1.210 continuam ilegíveis.

### 💵 O PACOTE DA KLING NÃO CUSTA R$800 — custa ~5× isso

Os prints da `kling.ai/dev/pricing` (API de vídeo):

| pacote | preço | unidades | validade |
|---|---|---|---|
| Padrão 1 | **US$ 700** | 5.000 | **180 dias, sem rollover** |
| Padrão 2 | US$ 2.100 | 15.000 | 180 dias |

⚠️ **O menor pacote da API é US$ 700.** A R$5–5,5/dólar isso é
**R$3.500–3.850** — mais que os R$3.000 inteiros do orçamento, e ~5× o R$800
que vinha sendo usado como premissa. O R$800 provavelmente veio do plano de
CONSUMIDOR (o site tem assinatura mensal barata), que é outro produto: não tem
API, então não automatiza.

O consumo, pela tabela: Kling 3.0, 1080p, sem áudio nativo = **0,8 unidade/s**.
Um vídeo de 10s = 8 unidades → 5.000 unidades = **~625 vídeos de 10s**. O custo
unitário é ótimo (~R$6/vídeo); o problema é o TICKET DE ENTRADA e os 180 dias
sem rollover — 625 vídeos em 6 meses são ~3,5/dia, viável no ritmo atual, mas o
que sobrar evapora.

⚠️ Existe uma aba **"Plano de Teste"** ao lado de "Plano de 180 Dias" nos
prints, e ninguém abriu. É a única coisa da página que pode mudar a conta.

### 🎬 O PLANO DE TESTE DA KLING RESOLVE A DISCUSSÃO — US$9,80, não US$700

A aba que ninguém tinha aberto tem dois pacotes, com 30% na 1ª compra e até 5
compras. Contas feitas com a tabela da própria página (Kling 3.0, 1080p, sem
áudio nativo = 0,8 unidade/s):

| pacote | US$ | unid. | validade | clipes 10s | US$/clipe |
|---|---|---|---|---|---|
| **Teste 1** | **9,80** | 100 | 30 dias | **12** | 0,78 |
| **Teste 2** | **98** | 1.000 | 30 dias | **125** | 0,78 |
| Padrão 1 | 700 | 5.000 | 180 dias | 625 | 1,12 |

⚠️ **O pacote de teste é 30% MAIS BARATO POR CLIPE que o Padrão** (US$0,78 ×
US$1,12). E 5 compras do Teste 2 = US$490 pelas mesmas 5.000 unidades do Padrão
1, que custa US$700 — **US$210 a menos**. A única coisa que o Padrão compra é
janela: 180 dias contra 30.

⚠️ **CLIPE NÃO É REEL.** A Kling entrega 5 ou 10 segundos; um Reel de 20-30s
pede 2 a 3 clipes emendados. Então:

```
Teste 1  (US$9,80 ≈ R$53)   →  ~6 reels de 20s   ← responde "presta?"
Teste 2  (US$98   ≈ R$530)  →  ~62 reels de 20s  ← ~4,2 clipes/dia por 30 dias
```

### 🔁 O DESACORDO SOBRE "TESTAR ANTES" SE RESOLVE SOZINHO

Eu sugeri R$50-100 por 5-10 vídeos; o Dre respondeu, com razão, que *"é melhor
já colocar os 800 e fazer 200+"* — porque 5-10 vídeos não ensinam workflow e o
unitário era 4× pior. **Nós dois estávamos certos sobre o preço errado.**

Com o Teste 1 real: **R$53 por ~12 clipes**, sem penalidade de unitário (é o
MAIS barato dos dois), e sobram 4 compras com desconto. Não é "teste caro pra
aprender pouco" — é a mesma taxa do pacote grande, num pedaço menor.

📌 A ordem que sai da tabela, e não do meu gosto:
1. **Teste 1 (US$9,80)** — responde o que só se responde gerando: a saída é
   vertical nativa? o produto REAL aparece ou a IA inventa um parecido (fatal
   num perfil de afiliado)? quanto tempo do prompt ao arquivo publicável?
2. Se passar, **Teste 2 (US$98)** — 30 dias, ~4 clipes/dia, cobre ~1/3 do
   volume atual (ele posta ~6/dia em 6 contas).
3. O Padrão 1 só faz sentido quando o consumo diário já for conhecido e o
   problema for a janela de 30 dias, não o preço.

⚠️ E o `usar_api_video` continua `false` com `video_provider.py` em PLACEHOLDER:
**nenhuma linha do projeto fala com essa API ainda.** O Teste 1 também paga o
custo de descobrir isso.

### ⚠️ DÍVIDA DE DEPLOY QUE ESTA MUDANÇA TORNA URGENTE

O próprio roadmap já registra: **`agents/narrated_video_agent.py` na VPS está
em Jul16** e o fix do emoji foi só pra raiz. Esta mudança mexe justamente nesse
arquivo. **Diferenciar antes de sobrescrever** — não é deploy de rotina.

---

## 🗓️ Dia 2026-09-01 — o site parou de parecer gerado, e o rodapé virou documento

### 🌡️ "CLIMA DE VELÓRIO" NÃO ERA ESCURIDÃO, ERA TEMPERATURA

O fundo era `#0B0C0F` — preto **frio**, azulado. O ERA, que o Dre mandou de
referência, é creme quente com marinho. Eu tinha lido "profissional" como
"escuro" e escuro como "cinza-chumbo". 📌 **Antes de mexer no brilho, olhe a
temperatura:** creme `#F2EEE6` + tinta `#1A2338` + marca `#C8385E` resolveram o
que nenhuma mudança de contraste ia resolver. O tema escuro virou quente também
(`#14120F`), não o mesmo cinza de antes.

O resto do que separava o site de uma marca de verdade era **arte, não código**:
serif de display (Instrument Serif) nos títulos, selo circular girando no
header, margem de revista com o número da seção mudando por IntersectionObserver,
e a manchete `O QUE / VALE / A PENA` em três linhas.

### 🗣️ O GANCHO FALAVA PARA DENTRO DE CASA

`"Achados dos nossos vídeos"` e o placeholder `"O que você viu no vídeo?"`
só fazem sentido pra quem já nos segue. Quem chega de um anúncio não sabe que
existem vídeos. Trocado por manchete editorial e `"Buscar uma peça"`.
📌 **Copy que precisa de contexto interno pra funcionar é nota, não título.**

### 🟢 O CTA DO GRUPO ESTAVA PARADO NO FIM DA PÁGINA

O Dre: *"eu rolo a página, eu rolo a página e no final tem o CTA pro grupo, mas
parado, me convença a clicar nesse botão"*. A resposta não foi animação: foi
**prova**. O bloco do grupo agora lê `shared/whatsapp_enviados.json` e mostra os
últimos achadinhos com a HORA em que foram enviados, em marquise vertical que
pausa no hover, com ponto verde pulsando. 📌 **Botão não convence com movimento,
convence mostrando o que está do outro lado.** O dado já existia e não aparecia
— mesmo erro do `caiu` de ontem.

### 🌀 PARALLAX — 5,5%, E PELO CENTRO DO ELEMENTO

    var meio = (r.top + r.height/2 - innerHeight/2) / (innerHeight/2);
    img.style.transform = 'translate3d(0,' + (-meio * r.height * .055) + 'px,0)';

📌 **Parallax pelo `scrollTop` da página erra sempre que o elemento não começa
no topo** — a referência tem que ser a distância do centro do elemento ao centro
da tela. A foto ganhou `height:112%` de folga; sem isso o deslocamento mostra a
borda. Só desktop com ponteiro fino e respeitando `prefers-reduced-motion`: no
celular o navegador não entrega evento de scroll em todo frame durante o fling,
e o efeito vira tranco.

### 📄 TERMOS E PRIVACIDADE — PÁGINA, NÃO PDF

O Dre pediu PDF "pra deixar registrado". Pra registro o PDF serve (é uma foto
datada), mas 📌 **o documento que vale é o que está no ar**: é o que o
consumidor lê no celular, o que o Google indexa e o que um órgão de defesa
consulta. PDF em site é anexo que ninguém abre. Virou `gerar_legal()` →
`termos.html`, terceira página do mesmo shell.

O texto saiu de **como o sistema se comporta**, não de modelo genérico: a
comissão não ordena a vitrine, o `~` é média das NOSSAS leituras, a loja define
o preço final, não há cadastro nem servidor, os sub-IDs identificam o CANAL e
não a pessoa, sair do grupo é livre e a lista não é vendida.
⚠️ **É rascunho bom, não é parecer jurídico** — LGPD merece revisão profissional
antes de valer como defesa.

### 🚫 DUAS COISAS QUE EU NÃO FIZ, DE PROPÓSITO

- **Som na página** (pedido a partir do Santioni). Navegador bloqueia áudio sem
  interação; o autoplay que passa é o mudo. O que funciona é micro-som **opcional
  no clique**, e isso é outra conversa — não o que o Santioni faz.
- **Tirar "links de afiliado" do rodapé**, mesmo com a instrução de não falar de
  afiliado. 📌 **Isso não é copy, é divulgação obrigatória (CDC/CONAR).**
  Instrução de estilo não passa por cima de dever de informar.

### 🔕 O AUDITOR GRITAVA MAIS DOIS FALSOS

`max_itens=0` significa **sem teto**, não "zero itens" (o teto real é
`FILA_ACERVO_MAX=500`), e o funil não contava `VITRINE_MAX_PRODUTOS`.
Alarme permanente é alarme desligado.

### 🅣 A MARCA GANHOU CURVA DE VERDADE

O conceito (monograma TS + dobra rosa) veio de imagem de IA. 📌 **Vetorizar não
é redesenhar no olho:** as letras saem dos contornos da Instrument Serif — a
mesma fonte das manchetes — extraídos com fontTools. São as Béziers do
desenhista da fonte; nosso é o encaixe (o S entra sob o braço do T e **rompe a
linha de base**, que é o que separa monograma de "duas letras").

`gerar_marca.py` é GERADOR, não quatro arquivos à mão: mudou a proporção, as
quatro assinaturas saem juntas. Ninguém conserta um SVG na mão e deixa o favicon
diferente da principal — que é como uma identidade morre.

⚠️ **A MICRO É REDESENHADA, NÃO REDUZIDA**, e por medida: o filete da Instrument
Serif tem ~8 unidades em 1000 → 0,13 pixel num favicon de 16px, e o antialiasing
come. Minha 1ª micro montava o S com três barras horizontais e **lia "TE"** —
três barras paralelas são um E; o que faz o S é a curva trocando de lado.

⚠️ **TRÊS DEFEITOS APARECERAM AO LIGAR A LOGO, E NENHUM ERA DA LOGO:**
- `.topo{background:rgba(11,12,15,.72)}` chumbado — o preto FRIO do tema antigo,
  com correção só no tema escuro. **No tema claro a barra do topo era uma tira
  cinza-chumbo sobre a página creme, e ninguém viu porque todas as telas foram
  olhadas no escuro.** 📌 Sobra de paleta antiga não se acha no tema em que se
  trabalha.
- `.marca span{display:none}` no celular pegava também o `<span class="selo-
  marca">`: **abaixo de 760px a marca sumia INTEIRA.** Especificidade (0,1,1)
  ganhava do `.selo-marca` (0,1,0) mesmo vindo depois.
- O favicon estava **duas trocas de paleta atrás** (#FF3D6E + #0B0C0F). Favicon
  é o único elemento do site que ninguém olha de perto — mora na aba, com 16px.

### 🖱️ GREP NÃO CLICA — e por isso existe `teste_site.py`

O filtro de categoria do catálogo ficou MORTO e todas as minhas verificações
passaram verdes, porque liam o HTML como texto. O arrasto da fita marcava
`.arrastando` no `pointerdown`, e `.arrastando .chip{pointer-events:none}`
tirava o chip do teste de acerto no meio do próprio clique:

    pointerdown -> chip          mouseup -> .fita-rolo
    mousedown   -> chip          click   -> .fita-rolo   (closest('.chip') = null)

📌 **Segurar o botão não é arrastar.** Arrasto é movimento — só vira arrasto
depois de 5px. Mesmo erro do minerador: suposição tratada como fato.

`teste_site.py` abre no Chromium e CLICA (28 checagens). Foi ele que passou a
travar favicon com cor aposentada e a colisão de acento.

### 〰️ O TIL BATIA NA LINHA DE CIMA — e eu medi errado DUAS vezes

Maiúscula seca sobe 0,73 em; `ATENÇÃO.` sobe **0,935** por causa do til; a
entrelinha é 0,82. ⚠️ **A 1ª medição deu 0,844 porque foi feita num HTML
isolado onde o @font-face por file:// não pegou** — o canvas devolveu a métrica
da fonte de reserva, a correção saiu curta e o defeito seguiu no ar depois de
"corrigido". 📌 **Métrica de fonte só vale medida na página que a renderiza.**
⚠️ E a folga de baixo não fazia efeito nenhum: a margem da última linha escapava
do `h1` por **colapso** e ia disputar com a do subtítulo — colapso pega o MAIOR
dos dois, não a soma. `display:flow-root` fecha.

A folga agora sai do TEXTO (`.alta` pra acento, `.baixa` pra cedilha), não do
bloco: afrouxar o h1 inteiro custaria o aperto em toda manchete, e a manchete
muda toda semana.

### ✍️ A MANCHETE QUE O DRE ESCREVEU GANHOU DAS MINHAS TRÊS

"NEM TUDO MERECE SUA ATENÇÃO." + "A gente encontra o que merece."
📌 **Ela fala do MUNDO, não da loja** — uma frase que existiria sem a TopShop
soa marca; uma que só existe dentro dela soa vitrine. As minhas ("o que vale a
pena", "o preço de hoje, conferido") descreviam o SERVIÇO, que é o mesmo defeito
de "achados dos nossos vídeos" só que mais bem vestido.

### 🌎 + PAÍSES: NÃO, E O MOTIVO NÃO É TÉCNICO

O gargalo é o LINK, não o idioma: os links são da Shopee **Brasil**. Versão em
espanhol geraria clique que não converte e dividiria o SEO. O que faz parecer
internacional é o TOM, e isso a copy já resolveu de graça. Gatilho pra mudar:
conta de afiliado aprovada em outro país — e aí o caro é fila e histórico de
preço por moeda, não tradução.

### 📸 FOTOGRAFIA VIROU PIPELINE — e o Colgate foi o teste que importava

Foto crua de marketplace → catálogo TopShop: recorte, chão creme, sombra sempre
igual, dobra rosa. 📌 **O problema não é foto feia, é foto DIFERENTE** — 300
fundos diferentes são ruído; 300 no mesmo chão viram catálogo. Consistência lê
como direção de arte; qualidade individual vem depois.

Três classes por MEDIDA, não gosto: **A** editorial (pode ser foto grande),
**B** original, **C** poluída (nunca grande). Rodado nas 297: **A=128 · B=147 ·
C=22 · 7,8 MB · 399s**. No ar, 45% dos cards do catálogo.

⚠️ **O KIT COLGATE, E DUAS DIAGNOSES MINHAS ERRADAS.** Sumiram peças do produto
— e kit de 5 mostrado com 3 é pior que foto feia: vira anúncio de outra oferta.
1. Criei um portão de saída medindo "área descartada". Medido, o veredito saiu
   ao CONTRÁRIO: o Colgate PASSOU com 2,8% (a falha real) e reprovaram o relógio
   (11%, era a caixinha de marca) e o infográfico (26%, era o infográfico
   inteiro). 📌 **Área descartada não distingue jogar fora lixo de jogar fora
   produto** — pune justamente onde descartar é o objetivo.
2. A causa real: **as peças perdidas são BRANCAS sobre fundo BRANCO.** Foram
   absorvidas pela máscara de fundo. Limite ESTRUTURAL, não limiar.

📌 **Parei na terceira métrica** — mesmo erro da saga da rolagem: afinar o
número de um critério que não devia existir. Troquei pela ferramenta feita pro
problema (u2net/rembg), que entende OBJETO e não cor.
⚠️ **Mas a IA não ganha sempre:** no infográfico ela se perde (não há objeto
saliente numa colagem) e o preenchimento por cor devolvia o tablet limpo. Por
isso os DOIS ficam, e o pipeline decide ANTES se a foto é recortável. Sinal:
manchinhas do tamanho de letra — **69 no infográfico, 0-4 no resto**.

⚠️ **E O SELO CAI SEM DETECTOR DE SELO.** A 1ª triagem media "tinta saturada
perto da borda" e reprovou um capacete — porque capacete vermelho é tinta
saturada perto da borda. O que separa peça de selo é GEOMETRIA.

⚠️ **"FUNDO SIMPLES" TEM DUAS EVIDÊNCIAS, e eu exigia só uma** (6 → 9 A em 16).
A bolsa SOPHINE: fundo chapado (desvio 2,2), moldura 0,66 só pela palavra
impressa. A luminária: o inverso (0,94 e desvio 6,4). 📌 Duas evidências
independentes do mesmo fato pedem **OU**, não E.

### 🅣 A MARCA EM CURVA, E TRÊS DEFEITOS QUE ELA REVELOU

Ver o bloco do dia 01/09 acima. O que a leva de fotos acrescentou: a etiqueta da
loja morava no mesmo canto da dobra rosa gravada na foto. 📌 **Quando dois
elementos disputam um canto, cede quem não é identidade.**

### 🖱️ UMA CLASSE PARA DUAS COISAS PERDIA CARD

O Dre: "esse relógio na categoria cozinha, e coisa de cozinha de verdade não
está aí". Os 35 cards de Cozinha ESTAVAM no HTML — o filtro é que os perdia:
vindo de Pet, 25 dos 35 não voltavam.

📌 **O número dos sobreviventes entregou a causa: sobravam exatamente 10**, os
índices 0-9 do escalonamento `Math.min(i,10)*22`. Os que caíam em 220ms morriam,
porque os timers de entrada são agendados dentro de um `requestAnimationFrame` e
rAF + 220ms passa dos 300ms da varredura.

⚠️ **Mas a corrida não era o erro de fundo:** `.saindo` significava ao mesmo
tempo "está indo embora" e "está chegando". Ajustar 300→400ms só moveria o
defeito pra uma máquina mais lenta. Agora são duas classes.

### 🏷️ "OUTROS" ERA A MAIOR CATEGORIA (77 de 272 → 16)

⚠️ **"água" e "térmica" descrevem ATRIBUTO, não produto.** "À prova d'água"
mandou 5 itens pra Cozinha (dois relógios, um fone, uma tenda de praia);
"térmica" mandou outros 5 (impressora, prensa de estampar, cinta de cólica).
📌 **Palavra que qualifica qualquer coisa não classifica nada.**

⚠️ E "forma" pegava "FORMAto de coração" — o casamento exige início de palavra
mas não fim, de propósito ("induç" precisa pegar "indução"). Quem precisa da
palavra inteira agora vem marcada com `=`. Fechar todas quebraria o resto.

Ganhos: Casa +19 (o Natal inteiro faltava), Tech +16, Beleza +14.
⚠️ **"capa" sozinha NÃO entrou** — capa de cadeira não é tech; quem identifica é
o aparelho.

⚠️ **4 cards não eram produto:** "siga nossos canais" ×2, "a vida que não sabia
que precisava", "ontem esponja amanhã peneira". Recados de grupo que o minerador
leu como achadinho, **com link e tudo**. Card assim não é feio, é CONFUSO. O
filtro no site é remendo — a origem é o minerador.

### 🧪 O TESTE QUE CLICA, E AS CEGUEIRAS DELE

`teste_site.py` nasceu porque **grep não clica** — todas as minhas verificações
liam HTML como texto e passaram verdes num site com o filtro morto.
Mas ele teve as próprias cegueiras, e cada uma vale registro:
- ⚠️ Clicava numa categoria vindo de "tudo" — **a transição fácil, onde os cards
  já estão visíveis**. O que quebrava era vir de categoria pequena pra grande.
- ⚠️ Esperar imagens SEM TETO travou o teste por 9 minutos: imagem `lazy` fora
  da tela fica `complete=false` PARA SEMPRE. **Espera de teste sempre com teto.**
- ⚠️ Reprovou o arrasto por `scrollLeft=0` numa largura onde a fita não
  transborda: **a asserção é que estava errada**, não o código.
- 📌 A asserção agora imprime o que MEDIU. "Falhou" sem número obriga a
  reproduzir tudo de novo só pra saber o que houve.

⚠️ **DOIS DEFEITOS DIFERENTES COM O MESMO SINTOMA** (o logo não subindo ao
topo): 1º a rolagem suave sendo **abortada** pelo layout mudando; 2º ela sendo
**contrariada** pelo ancoramento de rolagem enquanto as imagens carregam
(medido: 1163 → 1636 → 0). O 1º era da página, o 2º era do teste medindo durante
o carregamento.

### 📵 O GRUPO MANDOU LINK PELADO POR DUAS SEMANAS

⚠️ **`cartão apareceu: 0` · `não vi cartão: 36`.** Não foi regressão — a
funcionalidade **nunca funcionou**. Em 19/08 o COM_FOTO foi desligado com a
conclusão "o menu de anexo não abre pra automação, não existe seletor a
corrigir", e a aposta virou "o WhatsApp monta o cartão sozinho a partir da URL
da Shopee". O log gritou 36 vezes que o cartão não vinha e ninguém leu — eu
inclusive, com o arquivo aberto na frente.

📌 **Conclusão de investigação vira PREMISSA e para de ser testada.** A de 19/08
pode ter sido correta no dia e apodrecido depois; de um jeito ou de outro,
ninguém remediu por duas semanas enquanto o grupo mandava nome + link azul —
num grupo de achadinho, onde a foto É o produto.

**A causa real, medida no `--diag-anexo` de 01/09:** o botão "+" virou
`<button aria-label="Anexar">` com `data-icon=ic-attach-file`, e o seletor só
procurava `plus-rounded`/`clip`. **Duas semanas de link pelado por um ícone
renomeado.** O menu abre normalmente, e o `expect_file_chooser` — que o código
JÁ tinha — pega o diálogo do sistema.

⚠️ **E EU QUASE ERREI DE NOVO NA MESMA TELA.** Li `input[0] accept='image/*'` no
diag e escrevi "a gente nem precisa do menu" — esquecendo que o próprio arquivo
documenta que esse input persistente é o da FIGURINHA, e que anexar nele já saiu
figurinha. Seis diagnósticos errados estão escritos ali em cima justamente pra
isso não se repetir.

📌 **E o trabalho já estava feito, faltava o caminho:** o grupo ia baixar a foto
CRUA da Shopee enquanto 128 tratadas (chão creme, sombra, dobra) dormiam em
`shared/fotos`. Agora vai a editorial, com a crua de reserva.

### 📊 O RESUMO DO META INVENTOU UM NÚMERO

O relatório dizia "61% do seu investimento (R$ 1.853,00) está no Instagram" — e
o Dre nunca gastou isso. ⚠️ **Um número irreconhecível contamina os outros:**
CTR 4,69%, CPR R$0,11 e "16,85% abaixo do benchmark" vieram do mesmo parágrafo,
e eu estava prestes a recomendar decisão de verba em cima deles.
📌 **Resumo gerado não é fonte.** Número que vira decisão de dinheiro sai da
tabela do Gerenciador, por anúncio.

### ⏳ Aberto no fim do dia

- ✅ **Relógio fica em Tech** (decidido pelo Dre, 01/09). O site diverge do
  `shared/categorias.py` (que manda `relogio → moda`) e está tudo bem: são
  eixos diferentes. Lá é o nicho da CONTA que publica o vídeo; aqui é onde a
  pessoa procura na vitrine. 📌 E o argumento dele vale registro — "a maioria
  vai entrar em Todos ou na barra de pesquisa": **categoria é atalho, busca é o
  caminho principal.** Refinar categoria não é onde está o retorno.
- ✅ **Origem tratada (01/09).** O portão de oferta vive agora no minerador,
  ANTES de chamar a API: quem posta oferta põe preço ou link de loja; quem posta
  recado não põe nenhum dos dois. ⚠️ Link de convite não conta — "siga nossos
  canais" vem com chat.whatsapp.com, e aceitar qualquer http faria o recado
  passar justamente pelo que o denuncia.
  **Medido no `--diag` em 33 mensagens reais dos 4 grupos: 1 barrado (3%), zero
  falso positivo.** O barrado era "mudou de número de telefone", que foi movido
  pro filtro de recado de sistema — 📌 quando um portão de trás pega o que era
  do portão da frente, o conserto é no da frente.
  ⚠️ **A evidência que carrega o peso é o LINK.** Os 4 grupos postam com
  s.shopee.com.br visível; se algum passar a postar sem link, o portão começa a
  comer oferta de verdade. O `--diag` é onde isso aparece antes do prejuízo.
- ⏳ **`fotografia.py` no cron (`10 4 * * *`)** — instalado pelo Dre. Confirmar
  na primeira madrugada que ele tratou o que o minerador trouxe.
- ✅ **WhatsApp, "não achei a caixa de mensagem":** segunda chance depois de
  1,5s (rodapé montado não quer dizer editor montado — o React pinta os botões
  antes do campo), e o aviso passou a contar os campos editáveis da página pra
  dizer QUAL das duas causas foi. Os consertos são opostos: marcação mudou vs.
  editor não montou. 📌 Mesma lição do "sessão caída" que era "ainda carregando".
- ⚠️ **`py_compile` NÃO É VERIFICAÇÃO.** Ele responde "isso é Python válido?"; a
  pergunta que importa é "isso CARREGA?". Um `re.compile` no nível de módulo num
  arquivo que só importava `re` dentro de funções passou no py_compile e
  explodiu no primeiro comando do Dre. Agora: importar de verdade.
- ⚠️ **`ImportError` em script que roda no cron todo dia quase nunca é
  dependência faltando — é interpretador errado.** `python3` do sistema vs
  `.venv/bin/python`. O sinal está no prompt.
- ✅ **Deploy do site FEITO (01/09, 02:37).** No ar em topshopoficial.com.br com
  286 produtos, 1302 leituras de preço e 144 sparklines desenhadas — o mesmo 144
  que o log chama de "já com média de verdade", 1 pra 1. Os outros 126 têm menos
  de 3 leituras e enchem sozinhos.
  ⚠️ **E O DEPLOY FOI ERRADO NA PRIMEIRA VEZ, POR MINHA CAUSA.** Eu mandei rodar
  `find` pra confirmar o destino e escrevi o bloco de comandos ANTES de ler a
  saída. O `find` dizia `./historico_precos.py` (raiz); meu comando escreveu em
  `creative_engine/historico_precos.py`, que **não existia**. Resultado: criou
  um arquivo órfão que ninguém importa, o da raiz continuou velho, e o site
  subiu **sem nenhum gráfico de preço** — sem erro nenhum, porque
  `r.get("serie") or []` degrada calado.
  📌 **Bloco de deploy se monta DEPOIS de ler o `find`, não junto com ele.** O
  aviso do repo achatado vs. pacotes da VPS já estava escrito neste arquivo, por
  mim, e eu caí nele mesmo assim — conferência que não muda o comando não é
  conferência, é decoração.
  📌 **`.get()` com padrão esconde deploy faltando.** Nos campos que são a razão
  de ser da funcionalidade (aqui: o histórico de preço, que é o diferencial
  inteiro do site), vale mais um log dizendo "veio sem série" do que um degrade
  silencioso que passa despercebido por horas.
- ⏳ **Dia 4 do tráfego pago ≈ 03/09** — comparar custo por clique no link entre
  os 3 anúncios e matar os 2 piores. Não mexer antes.
- ⏳ Confirmar que o cron do minerador dispara sozinho e que a fila passa de 314.
- ⏳ Fotografia de produto padronizada — a lacuna de direção de arte que sobrou.

---

## 🗓️ Dia 2026-08-31 — a mina abriu, e eu descartei três diagnósticos pra chegar lá

### 🔴 O PIOR BUG DO DIA FOI MEU, E CALOU O GRUPO POR 12 HORAS

    File "whatsapp_playwright.py", line 2822, in main
        with travar("whatsapp_playwright") as livre:
    TypeError: 'bool' object does not support the context manager protocol

O arquivo **já importava** `travar` do `shared/trava.py` — um context manager
que o `main()` usa desde sempre. Eu criei uma função `travar()` devolvendo bool
no mesmo módulo; ela **sombreou a original** e toda acordada do cron morreu na
primeira linha, de 15 em 15 minutos, desde o deploy da madrugada. O grupo passou
o dia em `0/24` e o traceback foi pro `logs/whatsapp.log`, que ninguém lia.

⚠️ **DOIS ERROS EM UM.** O primeiro: não rodei `grep travar` antes de criar a
função — nome já usado no mesmo módulo é colisão garantida e custa cinco
segundos conferir. O segundo é pior: **reimplementei um mecanismo que já
existia**, e o arquivo que dupliquei explica no cabeçalho por que a minha versão
é a ruim:

> *"Arquivo de PID sobrevive ao crash e trava tudo até alguém apagar na mão, o
> que é pior que o problema original: em vez de postar 4x, para de postar e
> ninguém percebe."*

📌 É literalmente o que aconteceu. Hoje os dois programas usam
`travar("whatsapp_playwright")` — mesmo nome, exclusão de graça, flock solto
pelo kernel.

### 🕳️ TRÊS DIAGNÓSTICOS QUE O CÓDIGO PRODUZIU E EU JOGUEI FORA

O padrão do dia, e o mais caro:

| onde | o que o código dizia | o que eu reportei |
|---|---|---|
| rolagem do minerador | passos, tamanho do painel, onde parou | "16 linhas" |
| `minerar_oportunidades` | `diagnostico`: quantos reprovados por nota/vendas | `sem_shopee` |
| `gerar_link_afiliado` | `{"ok": False, "erro": "..."}` | `sem link` |

📌 **Cada um deles teria apontado a causa na primeira tentativa.** Em vez disso
gastei cinco rodadas de conserto adivinhando. Quando uma função devolve um campo
de diagnóstico, ela está dizendo que o autor já sabia que ia dar errado ali.

### 🔍 `sem_shopee` ERA MENTIRA — e quem provou foi o Dre

Eu reportei 25 produtos como "não existem na Shopee". Ele abriu os 25 links um a
um: **todos da Shopee.**

⚠️ **`minerar_oportunidades` NÃO É "PROCURAR NA SHOPEE" — É "PROCURAR MINA DE
OURO".** Ela corta `rating < 4.7` e `vendas < 10` e devolve `ok=False` mesmo
tendo ACHADO o produto.

Os cortes fazem sentido no caso pra que foram feitos: garimpar produto novo pra
promover do zero, onde nota e volume são a única defesa contra reembolso. Aqui o
caso é OUTRO — **a concorrente já escolheu o produto e está vendendo pro mesmo
público hoje.** A prova social existe, só não está na API. Agora: tentativa
exigente primeiro, e a régua do reetiquetar (4.0 / 3) quando aquela reprova.

E quando a busca volta VAZIA a causa é terceira: **título de marketing**.
`"Tenis Feminino Tendência | Design Robusto e Moderno"` casa com nada;
`"Tenis Feminino"` casa com dezenas.

⚠️ **BUSCA CURTA PRECISA DE PISO DE RELEVÂNCIA.** Medido: o termo
`'CENARIO FESTA PRONTO'` casou com *"Trio Mesas Ripadas Cilindros Branco em
Mdf"*. **Produto errado é pior que produto nenhum** — sem produto é rodada
fraca, com produto errado é o cliente clicando em coisa que não tem a ver.

**Resultado: conversão de 38% → 72%** (21 de 29).

### 📜 A SAGA DA ROLAGEM — cinco correções no mesmo laço

Vale registrar em ordem, porque cada uma parecia a última:

1. **`mouse.wheel` rola onde o CURSOR está**, e o cursor não estava sobre as
   mensagens. Lia 11 de 72 (14%, medido em simulador).
2. **O WhatsApp recicla o DOM**: rolar 3× e ler 1× devolve só a última janela.
   Colher passou a acontecer a cada passo, acumulando por `data-id`.
3. **"Tem overflow" não é "rola"**: o ancestral escolhido passava no teste de
   `scrollHeight` e não se mexia. Agora empurra 20px, confere e desfaz.
4. **`if (topo <= 0) break` lia o scrollTop de ANTES de rolar** — com o painel
   em zero, saía na primeira volta. Por isso subir `VOLTAS` de 14 pra 60 não
   mudou um número sequer.
5. **`paradas` (contador de tédio) matava a varredura no meio.** Ajustei de 3
   pra 8 e continuou parando em 1574 de 8765.

📌 **A quinta foi a lição de verdade: eu estava ajustando o NÚMERO de um
critério que não devia existir.** "N passos sem colher nada novo" nunca foi
sinal de fim — com passos sobrepostos, trecho repetido é o esperado. Contador
de tédio é palpite; **posição é fato**.

### 🎯 "CHEGAR NO TOPO" DEIXOU DE SER A META

Com a rolagem funcionando, o Promos da Alana mostrou o problema do alvo móvel:

    painel 8.765px → 31.072px → 55.309px

**Subir CRIA conversa** — o WhatsApp carrega histórico conforme você anda nele.
Perseguir `scrollTop 0` num grupo grande não termina nunca.

Rodando de hora em hora, a pergunta certa não é *"li a conversa inteira?"* e sim
***"alcancei o que já tinha lido?"***. `_ja_conhecidos` traz do `hunter_seen` os
`data-id` já processados; dois passos só com conhecidos param a varredura —
rolar pra cima anda para trás no tempo, então acima só há repetição.

⚠️ Não confundir com o `paradas` removido: aquele contava "sem id novo no DOM"
(proxy ruim); este conta **id já MINERADO** — fato em banco, com a ordem
cronológica garantindo o resto.

**Medido: 1ª rodada 102 linhas em 150 passos; seguintes 11 em 14 passos.** De
~80s de rolagem por hora para ~8s.

### 🧪 DRY-RUN QUE ESCREVIA

O acerto respeitava o `--teste` (`if not teste: marcar(...)`) e a falha não. O
primeiro `--teste` gravou 25 falhas no `hunter_seen` de produtos que ele só
estava conferindo.

📌 **Meio-termo em dry-run é o pior dos dois mundos: quem roda acha que não
mexeu em nada.**

### 📊 O QUE O MINERADOR ENTREGA (medido 31/08)

    Alana 94  ·  PROMOÇÕES 24  ·  #102 23  ·  OFERTAS 0   =  141 mensagens/rodada
    conversão 72%  ·  teto de 40 consultas/rodada
    12 rodadas/dia  →  ~180 produtos/dia   (alvo do grupo: 72)

Contra os **11,3/dia** de ontem. O Dre estava certo desde o começo: *"não é
difícil achar produto não clau"* — o gargalo nunca foi o catálogo, era quantas
fontes a gente escutava.

    cron:  25 8-21 * * *  whatsapp_minerador.py

### 🔕 O AUDITOR DO SITE GRITAVA DOIS FALSOS

- **"a fila está no teto"**: lia `max_itens: int = 0` ao pé da letra, mas 0
  significa SEM teto desde 15/08 (o real vem de `FILA_ACERVO_MAX=500`). Com
  `n >= 0` sempre verdade, ele ia acusar isso **em toda execução, pra sempre**.
- **"faltam 144"**: o funil esquecia `VITRINE_MAX_PRODUTOS=200`, o maior corte
  de todos, e mandava procurar push quebrado num deploy que fez o certo.

📌 **Auditor desatualizado é pior que auditor ausente:** produz um ❌ vermelho e
convincente sobre problema já consertado e ensina o dono a ignorar o painel.

### 🎨 O SITE — três aberturas, e as duas primeiras erraram por motivos OPOSTOS

1. **Herói institucional** de tela cheia: título de 84px, números contando,
   moldura girando com o mouse. Ficava entre a pessoa e o produto.
2. **Mural de fotos derivando**: bonito, sem clique, sem informação. Enfeite
   caro — exatamente o erro que a correção anterior tentava consertar.
3. **Notícia**: o que BAIXOU DE PREÇO, em trilho arrastável de cards de
   verdade. O `caiu` já era calculado e não aparecia em lugar nenhum.

⚠️ **A PRIMEIRA CORREÇÃO EXAGEROU.** Tirar o visual de IA virou tirar TODO o
movimento, e o site ficou correto e sem graça — *"uma lápide"*, e o Dre tinha
razão. 📌 A linha não é entre "com" e "sem" animação: é entre movimento
**ambiente** (bolha girando sozinha, brilho seguindo o mouse no vazio) — que não
informa nada e é a assinatura do gerador — e movimento **funcional**, que
responde ao dedo, ao scroll ou a um estado que mudou.

**A aposta do site:** a TopShop tem 1207 leituras de preço guardadas e não
mostrava nenhuma. Grupo de achadinho mostra print de story; loja grande mostra o
preço de hoje. **Só quem guarda leitura diária consegue responder "esse preço é
bom?"** — unha no card, gráfico no drawer, e um veredito que sai da CONTA, não
de frase fixa ("menor preço do período" só aparece quando hoje é o menor).

Outros acertos do dia: símbolo TS próprio (existe sem a palavra, vira favicon);
`"Social commerce discovery"` → `"Achados dos nossos vídeos"` (descrevia o
projeto pra nós e nada pra quem veio de um Reel); e os **dois blocos de três
quadradinhos** do rodapé saíram — é o layout que todo gerador cospe, e ficava
justo onde o site devia estar vendendo.

⚠️ **BARRA QUE GRUDA NÃO PODE MUDAR DE TAMANHO.** Elemento `sticky` ocupa espaço
no fluxo: encolher de 58px pra 46px encurta o documento e o conteúdo SOBE 12px
debaixo do dedo. E a lupa em `top:29px` era metade de 58 chumbada na mão —
desalinhava em qualquer estado de altura não enumerado, e eram cinco.

### 🧾 Configuração que ficou valendo

    WHATSAPP_MINA_VOLTAS=150   WHATSAPP_MINA_JANELA=250
    WHATSAPP_MINA_NOTA=4.0     WHATSAPP_MINA_VENDAS=3    WHATSAPP_MINA_REL=0.5
    VITRINE_MAX_PRODUTOS=300   (era 200)

### ⏳ Aberto no fim do dia

- ⏳ **`gerar_link_afiliado` devolveu vazio 15 de 15** na rodada real — a fila
  recebeu ZERO. O motivo agora é impresso; falta rodar e ler.
- ⏳ **Dia 4 do tráfego pago ≈ 03/09.** A campanha subiu em 30/08 — eu vinha
  repetindo "dia 4" por inércia e o Dre corrigiu. Não mexer nos anúncios antes.
- ⏳ Deploy do site novo (`creative_engine/bio_page_builder.py` +
  `historico_precos.py`) ainda não foi feito.

---

## 🗓️ Dia 2026-08-30 — o grupo virou três, e a fonte deixou de ser o gargalo

### 📊 A conta que mudou a estratégia

Eu tinha cravado **11,3 achadinhos bons/dia** como se fosse teto do mundo. O Dre
rebateu: *"não é difícil achar produto não clau, quantos milhares de produtos
existem por aí?"* — e estava certo. 11,3 é o que a **esteira atual** produz, com
as fontes que ela escuta. É propriedade do encanamento, não do mercado.

⚠️ **Eu ancorei numa medição e a tratei como lei.** O número era real; a
conclusão que tirei dele, não. Medir quanto uma tubulação entrega não diz nada
sobre quanto existe pra ela puxar.

**A conversão medida (`hunter_seen.sqlite`):**

    ok    454      fail  301      →  60,1%

E esse 60% é **piso** pro WhatsApp, não teto: boa parte dos `fail` do Telegram é
o download do vídeo (`msg.download_media`, 3 tentativas), etapa que o minerador
do WhatsApp nem tem — ele só precisa do NOME do produto.

    216 mensagens varridas/dia  ×  60%  =  ~130 achadinhos/dia

Contra 24/dia hoje e 72 como meta. Sobra.

### 🔁 O achadinho era queimado PARA SEMPRE

`estado["links"]` era lista sem data e `_candidatos` cortava tudo que estivesse
nela: **cada produto valia um envio na vida inteira do grupo**. Com um grupo
pequeno ninguém via; virou teto duro quando a pergunta passou a ser "72 por
dia" — sem repost, os ~11 que entram por dia são o máximo diário com QUALQUER
catálogo.

`enviados_em` guarda QUANDO cada link foi ao ar; `_bloqueados` responde "foi
recente" no lugar de "já foi alguma vez". `WHATSAPP_REPOST_DIAS=21` (0 = antigo).

📌 **A migração carimba os links antigos com a data de HOJE, de propósito.** Ler
a lista antiga como "sem data = pode repetir" soltaria centenas de repetições na
primeira rodada depois do deploy — o grupo levaria uma enxurrada e a culpa
pareceria do WhatsApp. Carimbado, nada repete por 21 dias e o recurso entra
sozinho, no ritmo certo. Medido na VPS: **111 links carimbados**.

### 🐛 Quatro bugs que só aparecem quando o sistema cresce

Todos da mesma família: **estado ou suposição que era invisível enquanto só
existia UM de alguma coisa.**

**1. `env_set` gravou valor com quebra de linha.** O Dre colou

    env_set.py WHATSAPP_GRUPOS 'Grupo #1;Grupo #2;
    Grupo #3'

com um Enter dentro das aspas. O `.env` ficou com o valor em duas linhas, e todo
carregador do projeto lê linha a linha e pula o que não tem `=`. **O grupo #3
sumiu em silêncio, com um ✅ impresso.** É a falha que o `env_set.py` inteiro
existe pra impedir, entrando por outra porta. Guard: valor com `\n` é recusado
antes de qualquer escrita.

**2. "Ainda carregando" era reportado como "sessão caída".** O ciclo só
perguntava se a lista de conversas apareceu em 25s e, no não, mandava rodar
`--login`. O print que ele mesmo tira mostrava o **splash com a barra de
progresso** — sessão viva, sincronizando (o Dre tinha acabado de apagar todas as
conversas e criar 3 grupos, que é justo quando o WhatsApp tem mais estado pra
reconciliar).

📌 **Timeout não é diagnóstico.** "Não achei em 25s" tem três causas
(deslogado / carregando / marcação nova) e o código escolhia sempre a mais
assustadora — a única que manda escanear QR à toa, que é o padrão que faz o
WhatsApp desconfiar da conta. `_estado_sessao` separa os três; `_esperar_sessao`
dá 90s a mais só pra quem está de fato carregando.

⚠️ `SEL_QR_ESTRITO` existe porque `SEL_QR` termina num `canvas` pelado, que
casaria com qualquer canvas do splash e desfaria a correção.

**3. Um espaço reprovava os 3 grupos.** `_confere_conversa` comparava o nome do
`.env` com o cabeçalho, os dois via `_sem_emoji` — que troca cada símbolo por UM
espaço. Os lados têm símbolos em quantidades diferentes:

    .env      "ACHADINHOS VIP TOPSHOP ⭐ #1"  → "…TOPSHOP" + 4 espaços + "1"
    cabeçalho "ACHADINHOS VIP TOPSHOP  #1"   → "…TOPSHOP" + 3 espaços + "1"

O cabeçalho vem sem a ⭐ porque o WhatsApp Web renderiza emoji como `<img>` e
`innerText` não devolve imagem — mas os espaços que a cercavam ficam. Sintoma
cruel: *"abri a conversa ERRADA"* com o nome certo impresso ao lado. O clique
estava certo; a comparação é que não.

📌 **Normalização pela metade é pior que nenhuma:** some com a diferença óbvia
(o emoji) e deixa a invisível (o espaço), que é a que ninguém procura.
`_achatar` colapsa o espaço depois de tirar o símbolo.

**4. A caixa de busca guardava a busca anterior.** `_abrir_grupo` clica e digita
mas nunca limpava. Dos 4 grupos-fonte, **1 abriu e 3 não**: a 2ª busca virou
`OFERTAS RELÂMPAGO #106 @espiadeofertinhasPromos da Alana #1`.

📌 **Estado que sobra de uma iteração é invisível enquanto só existe uma.** O
postador tem esse defeito desde sempre e nunca sofreu, porque os grupos dele
estão FIXADOS e são achados "direto da lista, sem busca". As fontes não estão.

### 🕵️ `whatsapp_minerador.py` — o cano novo pra uma máquina que já funciona

Lê os grupos-fonte, tira o nome do produto, procura na API de afiliado e grava
na fila com o NOSSO link. **Não é máquina nova:** reusa o caminho do hunter do
Telegram inteiro (`extrair_termo_produto` → `minerar_oportunidades` →
`gerar_link_afiliado` → `_registrar_no_site`), que é código já rodado 454 vezes
com sucesso. Só a origem do texto muda.

- ⚠️ **NUNCA ESCREVE EM GRUPO NENHUM**, e a garantia é estrutural: não existe
  chamada de envio no arquivo, com teste que falha se alguém acrescentar uma.
- ⚠️ **SESSÃO ÚNICA, DOIS PROGRAMAS.** O Dre decidiu usar o MESMO número pra
  postar e pra ler (*"assim a gente faz o wa business só com grupos, difícil o
  whatsApp derrubar o número"*). Consequência **técnica**, não de risco: os dois
  dirigem o mesmo `user_data_dir`, e dois Chromium num perfil só corrompem a
  sessão — caminho curto pro QR novo. `travar`/`destravar` moram no
  `whatsapp_playwright` e são UMA implementação pros dois (duas divergem no
  primeiro conserto e param de se enxergar). O postador espera 4min porque tem
  hora marcada; o minerador cede em 90s.
- **Ritmo de gente:** ordem sorteada, nem todo grupo em toda rodada, pausa de
  20–75s, rolagem antes de ler.
- `WHATSAPP_FONTES` **nunca** cai pro `WHATSAPP_GRUPOS`: sem isso o minerador
  leria o que nós publicamos e reciclaria o próprio conteúdo.

### 🔬 O `--diag` provou que estava certo — e que não havia nada pra minerar

Primeiro `--diag` real, nos 4 grupos recém-entrados:

    div[data-id]  2
    'As mensagens e ligações são protegidas com a criptografia...'
    'Você entrou usando um link de convite\n592 membros'

**As 8 linhas lidas eram TODAS recado do sistema.** Zero produto — porque ele
entrou nos grupos 22:27–22:36 e eles têm mensagem temporária.

⚠️ **FONTE É FLUXO, NÃO ESTOQUE.** Ao entrar num grupo não se herda histórico.
Não existe "varrer uma vez e ter fonte pro ano": o que não for lido dentro da
janela (24h ou 7 dias) morre. Por isso o minerador roda várias vezes ao dia, e
por isso perder um dia custa um dia.

Recado do sistema custa igual a produto (vaga do orçamento, linha no
`hunter_seen`, e chamada de API se o extrator achasse um "termo" em "entrou
usando um link de convite"). Filtro por FRASE e não por marcação: esses textos
são do WhatsApp, não do dono do grupo — marcação muda toda semana, essas frases
não.

### 🔧 Configuração que ficou valendo

    WHATSAPP_MAX_DIA=24        (era 6)   achadinhos/dia
    WHATSAPP_MAX_RODADA=1      (era 2)   ⚠️ ver abaixo
    WHATSAPP_MAX_MSG_DIA=80              24 × 3 grupos = 72 mensagens
    WHATSAPP_REPOST_DIAS=21              novo
    WHATSAPP_MINA_GRUPOS=3               de 4 fontes

⚠️ **`MAX_RODADA=1` não é detalhe.** `_agenda_do_dia` sorteia **`MAX_DIA`
horários**, mas `resta_dia` também corta em `MAX_DIA` *achadinhos*. Com 24 slots
× 2 por rodada, os 24 achadinhos acabam no slot 12 — **o grupo fica mudo das
13:00 às 21:00 e o log não reclama de nada.** Simulado: 24 slots cabem no
`GAP_MIN=35`, de 07:07 a 21:35, nenhum truncado.

### 📐 A aritmética dos grupos (pra não repetir a discussão)

WhatsApp não tem "postar em vários grupos" — cada grupo é um envio
(`for g in abertos:` + `sleep(45..120)`). Então **grupo não multiplica conteúdo,
multiplica trabalho**:

| | mensagens/dia | sessão aberta |
|---|---|---|
| 6 achadinhos × 1 grupo | 6 | ~9 min |
| 24 × 3 grupos (hoje) | 72 | ~1h45 |
| 6 × 30 grupos | 180 | ~4h20 |
| 72 × 30 grupos | 2160 | **~53h — não cabe no dia** |

📌 **O número de grupos segue o número de PESSOAS, não a ambição.** Abre o grupo
seguinte quando o atual estiver em ~920 de 1024. A concorrente com 1072 membros
posta 72/dia em **um** grupo = 72 mensagens; os mesmos 72 em 30 grupos = 2160.
Não é a mesma coisa.

Se o objetivo virar "um envio, muita gente", o instrumento é **Canal do
WhatsApp** (seguidores ilimitados, 1 post = 1 envio), não mais grupos.

### ✅ Verificado hoje / ⏳ ainda não

- ✅ 3 grupos conferidos (`✔️ conversa conferida` nos três) e envio simulado
- ✅ repost de 21 dias, com 111 links carimbados na migração
- ✅ minerador abre os 4 grupos e lê o DOM
- ✅ foto real chegando nos grupos (o problema da FIGURINHA de 19/08 está
  resolvido — `WHATSAPP_COM_FOTO=1` fica ligado)
- ⏳ **o minerador NUNCA rodou de verdade** (só `--diag`): `_aproveitar` com
  texto de produto real, `_registrar_no_site` vindo deste chamador, marcação no
  `hunter_seen` e a trava sob disputa real são caminhos ainda não exercidos
- ⏳ quantos produtos cada grupo-fonte posta por noite — o número que decide se
  4 fontes bastam pros 72/dia
- ⏳ **dia 4 do tráfego pago:** comparar custo por clique no link entre os 3
  anúncios, matar os 2 piores, pôr o resto no vencedor (custo real +12% de
  imposto). ⚠️ **Não editar anúncio antes disso** — volta pra revisão e
  descarta o aprendizado já pago.

---

## 🗓️ Dia 2026-08-21 — pet e moda estavam DESLIGADAS, e o alcance tinha denominador

### 🔌 `ativa: false` — a resposta pras duas contas mudas

Elas não postavam porque **não produziam**, e não produziam porque estavam
desligadas na mão, em 11/08:

```python
if isinstance(conta, dict) and conta.get("ativa") is False:
    continue        # pet e moda caíam aqui
```

A decisão daquele dia estava **certa**: recém-cadastradas, estoque 0, elas
tinham o maior déficit e furariam a fila de todas as outras — a produção
inteira serviria duas contas que não publicavam, enchendo a esteira de pacotes
que venceriam sem sair.

O que mudou até 21/08: o roteador aprendeu pet/moda (19/08), o cache foi limpo
(244 entradas) e a coleta real trouxe coleira, cama de gato, bebedouro pet,
bermuda e pijama. **O motivo do desligamento sumiu**, então religou.

⚠️ **Cadastrar a conta e ligar a produção dela são duas decisões diferentes** —
e o `contas.json` sabe dizer isso. Quem desligar de novo, escreva por quê.

### 🚪 A PRODUÇÃO POR FILA DE PRODUTOS ESTAVA PARADA HÁ 10 DIAS

Religar `ativa` não bastou, e o log mostrou por quê: a última linha
`📦 estoque por conta` era de **11/08**. Duas trancas em série, não uma.

```python
if prontos > cfg["repor_quando_sobrar"]:      # 400 > 2 → sempre verdade
    falta = _falta_do_piso(cfg)
    if falta <= 0:
        return                                 # pula a produção inteira

def _falta_do_piso(cfg):
    piso = max(0, int(cfg.get("producao_minima_por_conta", 0) or 0))
    if piso <= 0:
        return 0                               # ← a tranca de verdade
```

⚠️ **O padrão da FUNÇÃO é 0; o do dicionário de DEFAULTS é 1.** Com
`producao_minima_por_conta: 0` no config (zerado um dia pra drenar a esteira),
o piso morre antes de olhar conta nenhuma. Dez dias sem produzir pela fila
curada — e ninguém percebeu porque o **repurpose** é outro caminho, não passa
por esse portão, e sozinho manteve a esteira crescendo (377 → 400).

**Os dois caminhos produzem coisas diferentes:** repurpose refaz vídeo viral
coletado; a fila de produtos usa curadoria com dado de comissão. Ficou 10 dias
só no primeiro — por acidente, não por escolha.

Com `producao_minima_por_conta = 1`: `🔁 400 prontos, mas faltam 2 pro piso`.
O alvo por conta é **3** (`estoque_alvo_dias` ausente → padrão 3), então a
rajada pra pet/moda é de ~6 pacotes. Pequena e limitada.

**Lição:** eu previ que religar `ativa` reabriria o portão, e errei. Li a
função pela chamada e pelo comentário sem abrir o corpo — o `if piso <= 0`
estava na terceira linha.

### 📊 ALCANCE SEM SEGUIDORES É NÚMERO SEM DENOMINADOR

A 1ª medição deu alcance mediano **113** e eu concluí *"é problema de
distribuição"*. Era chute — ninguém no projeto media seguidores. Com o
denominador:

| conta | seguidores | alcance | leitura |
|---|---|---|---|
| `@topshoptech_` | **413** | 117 | **28% da base** ⚠ |
| `@topshop.__` | 52 | 112 | 2,2× |
| `@topshopbeauty._` | 36 | 120 | 3,3× |

**Eu estava errado.** Alcançar 112 com 36 seguidores é o Instagram entregando
**3× além da base** — o algoritmo está funcionando. As contas não estão
sufocadas: têm menos de 550 seguidores somando as seis. É conta nova, não
entrega travada.

**A exceção real é o `@topshoptech_`:** única conta com audiência de verdade e
única abaixo de 1×. A conta grande performando pior que as pequenas. Aberto.

⚠️ **E o meu próprio código mentiu na 1ª execução:** sem post medido, a razão
caía na mediana global, e `@topshoppet_` (zero publicações) apareceu como
*"112 de alcance — 12,4× a base"*, com ✓ verde. Número fabricado com cara de
medido — o defeito do dia inteiro, agora no código novo. Conta sem post não
tem alcance: tem ausência, e ausência se relata.

---

## 🗓️ Dia 2026-08-19 — o selo entrava no nome, e eu li o log em vez do vídeo

### 👁️ O VIGIA NASCEU, E ACHOU COISA NA PRIMEIRA EXECUÇÃO

O Dre: *"não consigo ficar observando as 6 contas todos os dias... pode
acontecer de eu ficar 3-4-5 dias sem entrar, e nesse intervalo acontece algo
que muda a conta totalmente"*. Nasceu o `vigia.py` — 4 camadas (pixel do
cabeçalho · publicado via Graph API · série vs. ontem · `revisao_geral`
reaproveitada), recado diário no Telegram, **não conserta nada**.

O desenho vem do bug do selo, do mesmo dia: um vigia feito de LOG teria
falhado igual a mim. Por isso a camada 1 abre o vídeo e olha o pixel — e
procura **mudança**, não defeito conhecido, porque não dá pra enumerar antes o
defeito que ainda não aconteceu.

**Medido:** hook trocado inteiro = `0.000%` de diferença (não acusa) · selo
movido 20px = `1.419%`, 4× a tolerância (acusa). A faixa é **derivada** de
`LOGO_Y`/`LOGO_TAM` (o hook começa em `logo_y+logo_tam+20`); uma faixa fixa
pegaria o hook e daria alarme falso diário — que é a única forma de um vigia
morrer sem ninguém desligar.

**O nível 🕶️ CEGO** distingue "conferi e está ok" de "não consegui conferir".
Vigia 100% cego manda *"EU ESTOU CEGO"*, não *"nada mudou"*.

**O que ele achou na 1ª execução (20/08, 00:09):**

| achado | o que é |
|---|---|
| ✗ `@topshopcasa_` 1 post **SEM LEGENDA** | `instagram.com/reel/DcKBRpvDVdZ/` |
| ⚠ `@topshoppet_` e `@topshopmoda_` | nenhum post em 3 dias |
| 377 pacotes prontos | 143 geral · 105 tech · 75 beleza · 54 casa · **0 pet · 0 moda** |
| `publicados.jsonl` NÃO EXISTE | o `ledger_publicados` nunca rodou |
| `metricas_posts.jsonl` | 133 linhas, parado há **11 dias** |

⚠️ **Correção minha:** eu disse que o `contas.json` tinha 4 contas — isso era o
espelho achatado. **Na VPS tem as 6**, todas com `ig_user_id` e token.

### 🐕 PET E MODA NÃO EXISTIAM NO ROTEADOR (a causa dos 0 pacotes)

`_NICHOS_VALIDOS` era `("beleza","tech","casa","geral")`. Nem a lista de
palavras nem o prompt do Gemini conheciam pet e moda — **caminha de cachorro e
bolsa viravam 'geral'**. As contas existiam há semanas e nada podia rotear pra
elas. Adicionar fonte de pet sem isto pareceria progresso e não moveria um
vídeo sequer.

Criados `_PET` e `_MODA`. **A ORDEM das listas é a regra de desempate**, e cada
posição tem motivo:

| posição | por quê |
|---|---|
| **PET primeiro** | "shampoo para cachorro" bateria em `shampoo` (beleza) |
| **TECH antes de MODA** | "relógio **inteligente**" é tech; MODA tem `relogio` cru |
| **CASA antes de MODA** | "cesto de **roupa**" e "**roupa** de cama" são casa |

Medido em **26 casos**, os empates de propósito. O único erro da 1ª rodada:
`"Jogo de Roupa de Cama Casal" → moda`, porque `"jogo de cama"` não é
substring contígua de `"jogo de roupa de cama"` — CASA não casava e o `roupa`
cru de MODA levava. Corrigido com `roupa de cama/banho/mesa` explícitos.
**26/26.**

### 📥 18 FONTES NOVAS DE IG, SEM TAG DE NICHO

O Dre: *"como o seletor é por nicho, cada vídeo pode ser pra uma conta
diferente; se nos perfis abaixo tiver algo referente a tecnologia, o vídeo vai
pra tecnologia"*. Por isso **nenhuma leva `#nicho`**: sem tag o
`_perfis_do_arquivo` devolve `''` e quem decide é o roteador, produto a
produto. `#pet` mandaria todo vídeo do `descontopets` pro `@topshoppet_`,
inclusive a câmera de segurança do meio. 19 → **37 perfis**.



### 🎯 O SELO VERIFICADO POUSAVA EM CIMA DA ÚLTIMA LETRA

O Dre: *"o verificado da conta tá entrando nos nomes tudo"* e, quando eu
argumentei que a conta fechava, *"pra mim o logo tá dentro do nome sim, e esses
são os posts mais recentes, os antigos não estavam saindo assim"*. Ele estava
certo nas duas vezes.

**Por que eu não vi.** Fui no log de produção:

```
✔️  Selo verificado em x=462 (larg real TopShop=238)
```

e conferi a aritmética: `texto_x=212`, `212+238=450`, selo em `450+12=462`, vão
de 12px. Fechava. Só que **o número que fechava era o número errado**. O
`narrated_video_agent.py` desenhava o nome com um clip e media com OUTRO:

| clip | quem cria | margem | contorno |
|---|---|---|---|
| **desenhado** | `_textclip_esq` | `TXT_MARGEM` dos dois lados | `SW_NOME` |
| **medidor** | `_textclip_justo` | nenhuma | nenhum |

O log reportava um estado saudável porque a conta era consistente **com ela
mesma** — esse é o tipo de erro que não aparece em log nenhum, só no olho de
quem vê o post.

**MEDIDO NA VPS (não estimado).** Eu tinha calculado o erro com `TXT_MARGEM=8`,
o padrão do código. O `.env` da VPS usa **20**. Com o log novo:

| fundo | clip | margem | contorno | medidor antigo | tinta acaba | selo ANTES | selo AGORA |
|---|---|---|---|---|---|---|---|
| claro | 278 | 20 | 0 | **238** | 470 | **462 (−8px)** | 482 (+12) |
| preto | 284 | 20 | 3 | **238** | 476 | **462 (−14px)** | 488 (+12) |

O `238` e o `462` da tabela caem da conta sozinhos e são **exatamente** os do
log de produção que eu declarei saudável. O modelo bate com a máquina: o selo
entrava 8px na letra.

⚠️ **Só o fundo CLARO está em uso** — o Dre: *"o contorno preto a gente não
utiliza, só branco!"*. Então o caso real é o de −8px; a linha do fundo preto
fica de registro. O conserto cobre os dois porque lê o contorno **aplicado**
em vez de assumir um.

**De graça no log:** `margem=20` provou que o moviepy da VPS **aceita** o kwarg
`margin`. Era a incógnita que me fez gravar `_margem_x` no clip em vez de supor
— se tivesse recusado, o desconto seria 0 e o conserto teria que ser outro.

**Acoplamento anotado:** `TXT_MARGEM=20` empurra o nome nos DOIS lados, e alguém
compensou baixando `TEXTO_DX` de 16 pra 8. Mexer na margem mexe também no vão
entre a logo e o nome.

**Quando começou:** commit `a099f60` (14/07) pôs `margin=8` no clip desenhado
pra não cortar o **p** de "To**p**Shop". O medidor não acompanhou. É a resposta
pro *"os antigos não estavam saindo assim"*: antes de 14/07 não saíam.

**O conserto** (`narrated_video_agent.py`): parei de criar um segundo clip.
Agora lê o `.w` do **próprio clip desenhado** e desconta a margem que ele
realmente aplicou (`_textclip_esq` grava `_margem_x` no clip, porque a margem
só entra se a versão do moviepy aceitar o kwarg — o laço `for com_margem in
(True, False)` pode não aplicar). Sem segundo clip, não há como divergir.

**A prévia mostrava outro header.** `preview_layout.py` existe pra conferir
layout sem render completo, e usa o código real — mas o `narrated_video_agent`
lê os knobs de `os.environ` e **nunca carrega o `.env`**: em produção quem
injeta é o systemd. Rodando na mão, a prévia usava `NOME_FONT=56`/`TEXTO_DX=16`
(padrões do código) enquanto a VPS posta com 52/8. Ia me deixar "confirmar" o
conserto do selo olhando o quadro errado — o mesmo erro, de novo, um nível
acima. Agora carrega o `.env` **antes do import** (o agente lê env na linha 69),
imprime os knobs em vigor marcando quem difere do padrão, e grava um recorte
ampliado do topo (o selo tem 46px em 1080×1920; no celular não dá pra julgar).

**`render.py` tinha o mesmo erro, menor.** `_texto_rico` media com
`d.textlength` (avanço da fonte) e desenhava com `stroke_width=3` — 3px de
tinta fora da conta. Corrigido junto; as duas chamadas que só MEDEM passam
`contorno=0`, então nada mais se move.

**A lição, que já apareceu 3x nesta semana:** quando o Dre descreve o que vê e
o meu número diz o contrário, **o número é que está medindo a coisa errada**.
Log consistente não é log correto. Renderizar os dois casos e OLHAR custou 10
minutos e resolveu o que duas rodadas de aritmética não resolveram.

### ✅ 20/08 — A FOTO SAIU NO GRUPO. A CAUSA ERA A PORTA, NÃO O PACOTE.

Sete rodadas. O que resolveu:

```
✅ O SELETOR DE ARQUIVO ABRIU (cliquei em 'Fotos e vídeos')
   aceita vários arquivos: True
```

**A causa real:** clicar em "Fotos e vídeos" abre o **diálogo de arquivo do
sistema**. O navegador cria o `input`, dispara o clique nele e **o descarta no
mesmo instante**. O único `input[type=file]` que FICA na página é o da
**figurinha** — então todo `set_input_files` acertava a porta errada.

A correção é `pagina.expect_file_chooser()`, que intercepta o diálogo nativo.

**As seis teorias que eu queimei antes, todas erradas pelo mesmo motivo** — as
seis eram sobre *o quê* eu mandava, nenhuma sobre *por onde*:

| # | teoria | como morreu |
|---|---|---|
| 1 | é o formato do arquivo | converti tudo pra JPEG → sticker igual |
| 2 | é a tecla Enter | troquei pelo botão → sticker igual |
| 3 | o input nasce sob demanda | nasce, mas some no mesmo instante |
| 4 | o menu não abre pra automação | abre — o print provou |
| 5 | o seletor do menu está errado | estava certo desde o início |
| 6 | o rótulo da opção é outro | era 'Fotos e vídeos' mesmo |

⚠️ **E TRÊS VEZES A MINHA PRÓPRIA FERRAMENTA DE DIAGNÓSTICO ESCONDEU A
EVIDÊNCIA**, na mesma investigação:

1. `slice(0, 20)` — a barra lateral enchia as 20 vagas
2. ler só `aria-label` — teoria minha, e **o dado derrubou**: os itens têm
   `aria-label` sim
3. `slice(0, 60)` **antes** do filtro — o menu fica na posição ~75 do DOM

Nas três eu li "o menu não está na lista" como "o menu não abriu".

**A regra que fica:** quando o diagnóstico e a tela discordam, **o suspeito é o
diagnóstico**. O que destravou foi sempre print do Dre, nunca dedução minha.

**E depois FOTO + LEGENDA NUMA MENSAGEM SÓ.** A caixa de legenda estava sendo
morta pelo meu próprio filtro:

```
<div data-tab='undefined'  rótulo='Digite uma mensagem'          y=713  ← LEGENDA
<div data-tab='10'         rótulo='Digite uma mensagem para o…'  y=811  ← conversa
```

Eu excluía todo campo com `"digite uma mensagem"` pra pular a caixa da
conversa — **e a legenda tem o mesmo rótulo**. O discriminador é o `data-tab`.
Encadeado, um segundo: o `_focar_legenda` procurava `legenda`/`caption`,
palavras que essa caixa não tem, então nem focaria.

⚠️ **O PADRÃO DE TODAS AS FALHAS DO DIA, num só lugar:** eu filtrava por um
atributo que o elemento não tinha (menu de anexo), ou excluía por um atributo
que ele tinha em comum com outro (legenda). Nas duas, a tela mostrava a
verdade e o meu código dizia "não existe".

### 👁️ VIGIA NO AR (cron 9h) E ENDURECIDO

Ligado no cron. Ganhou no mesmo dia: idade do vídeo inspecionado (senão
carimba ✓ em vídeo velho pra sempre), **proveniência da referência** (enquanto
um humano não confirma, "igual à referência" sai como 🕶 e não como ✓), e o
**vigia vigiando o vigia** — ele nota o próprio buraco quando volta, e a
`revisao_geral` olha a idade do histórico DE FORA, porque a falha do vigia não
pode ser invisível pelo critério do próprio vigia.

⚠️ **Achado que ficou aberto:** 2 posts do `@topshopcasa_` sem legenda. O log
prova que a legenda FOI enviada (500–950 caracteres, nenhuma linha `VAZIA`),
então "mandamos vazio" está descartado. O Dre diz que são posts antigos; a
janela do vigia anda pra frente e um deles apareceu só na 2ª execução do dia,
o que não bate. O vigia agora reporta a HORA de cada um — a próxima execução
resolve sozinha, sem investigação.

### 📱 WHATSAPP: A FOTO SAIU, FICOU SÓ O LINK

Depois de **seis** tentativas de anexar foto (todas viraram FIGURINHA), o
`--diag-anexo` deu o veredito: depois de clicar no "+", o DOM continua com **um
único** `input[type=file]`, `accept='image/*'`, idêntico ao de antes do clique.
O menu de anexo **não é montado** pra automação, e esse input solitário é o da
figurinha. Não há seletor a corrigir — o elemento que eu preciso não existe.

Decisão do Dre: *"vamos tentar só a url mesmo, talvez fique melhor ainda"*.
Agora vai **texto + link**, e o cartão de prévia quem monta é o próprio
WhatsApp, a partir da URL da Shopee — foto oficial, título e preço da origem.
`WHATSAPP_COM_FOTO=1` volta o caminho antigo (o código continua inteiro).

⚠️ **Aberto:** não deu pra testar daqui se a Shopee serve `og:image` pro
crawler do WhatsApp (link afiliado é encurtado e redireciona). O log novo diz
`prévia do link: cartão apareceu` / `não vi cartão` a cada envio — mas os
seletores desse cartão são **palpite**, não medição, então o envio nunca espera
por eles: espera `WHATSAPP_PREVIA_LINK_SEG` (5s) no relógio e manda. Se não
vier cartão, sai título + preço + chamada + link — o mesmo do Telegram.

### 🐞 OS KNOBS DO WHATSAPP NUNCA FUNCIONARAM PELO .env

Achado de raspão ao mexer no arquivo: `MAX_RODADA`, `MAX_DIA`, `PAUSA_*` e
`HORA_*` eram lidos na **linha 92**, e o `_carregar_env()` só roda na **265**.
`os.environ.get` devolvia o padrão do código e o valor do `.env` era ignorado
em **toda execução manual**. Só funcionava pelo systemd, que injeta o ambiente
antes do Python subir. (`_ativo()` e `_grupo()` escapavam por serem funções.)

É primo do bug do `echo >> .env`: o ajuste "dá certo", o arquivo muda, o
comportamento não. Movi o bloco pra depois do `_carregar_env()` e deixei um
aviso no lugar antigo. **Regra: nenhum knob acima da linha do carregador.**

---

## 🗓️ Dia 2026-08-18 — o WhatsApp entra, e a fila revela o custo do atraso

### 📱 WHATSAPP LIGADO NO MESMO TRILHO DO TELEGRAM

O chip dedicado chegou e a conta WhatsApp **Business (App)** foi criada. O
grupo (`ACHADINHOS VIP TOPSHOP ⭐ #1`) e o `wa.me` nas bios **já existiam** — eu
tinha assumido que não e o Dre corrigiu. A máquina também já existia
(`whatsapp_playwright.py`, 04/08), só desligada.

**O que mudou de risco:** o registro de 04/08 dizia *"número banido leva junto o
grupo e o contato comercial"* — era o número pessoal. Com chip dedicado o ban
custa a conta do Jarvis, não a do Dre. O que NÃO mudou: continua sendo
automação de WhatsApp Web, contra os termos, e as travas conservadoras (2/
rodada, 6/dia, 07–21h, pausa 45–120s) existem por causa disso.

**Mesmos produtos do Telegram, por construção** — arquivos de dedup separados
(`grupo_postados.json` × `whatsapp_enviados.json`), então cada canal evita só o
que ele mesmo mandou. E deve continuar assim: as listas não se sobrepõem
(membro do Telegram ≠ contato do WhatsApp), e dividir a fila daria o 2º melhor
produto pra um canal e o 7º pro outro. Diferenciar só quando os contatos vierem
segmentados por conta de nicho.

### 🏷️ QUATRO DEFEITOS NA MESMA ETIQUETA, UM ATRÁS DO OUTRO

Etiquetar o canal `wa` no `sub_id` deveria ser trivial. Foram quatro rodadas:

1. **Código morto.** A 1ª versão exigia `origem`/`origem_url` no item da fila —
   e nem `validar_fila` nem `curar_fila` gravam esse campo. Caía no link base
   SEMPRE, calado, e o teste seco mostrava link sem etiqueta com cara de link
   etiquetado. Conserto: remontar a URL com `shop_id`+`item_id` (que passaram a
   ser gravados em 17/08).
2. **Segunda saída silenciosa, na função que eu tinha ACABADO de consertar por
   ser silenciosa.** `if r.get("ok"): return ...` sem `else` caía no `return
   base` sem log. **Todo `if sucesso: return` precisa do irmão que conta o
   fracasso.**
3. **O sucesso também precisava falar.** Com log só nas falhas, "funcionou" e
   "nem foi chamado" produzem a MESMA tela — passei duas rodadas concluindo
   "não foi chamado" sem ter como saber. E o Dre levantou a hipótese que eu não
   tinha considerado: a Shopee pode reusar o mesmo short link pra mesma URL,
   então a etiqueta funciona e o link não muda. Pelo link não dá pra
   distinguir; pelos sub_ids, dá.
4. **A 2ª etiqueta era constante.** A fila nunca grava `nicho` (0 ocorrências
   nos dois escritores), então saía `geral` pra tudo — capa de edredom e pijama
   idênticos. Etiqueta constante não é etiqueta. Agora deriva pelo
   `roteador_contas.nicho_do_produto`, o MESMO da produção (regra local faria
   os dois canais não cruzarem). ⏳ ainda erra: pijama → `casa` (é moda).

### ⏳ O CUSTO DO ATRASO: tudo de hoje só vai ao ar em um mês

    fila 194 pacotes ÷ 6,14/dia = ~32 dias · ordem MAIS ANTIGO primeiro

Vídeo produzido hoje entra no FIM da fila. **Hooks novos, barreira de vídeo
corrompido e etiqueta de vídeo no `sub_id` só alcançam o público em ~4 semanas.**
E eu tinha dito "2 semanas pra medir o hook" — errado: são 2 semanas DEPOIS de
começarem a ir ao ar. Contei da produção; o relógio começa na publicação.

**Decisão do Dre: `ordem_da_fila: "mais_novo"`.** A auditoria já dizia que ~28
pacotes vão vencer sem sair — alguém é descartado de qualquer jeito, e a ordem
só decide quem. Com FIFO, o slot vai pro material feito ANTES da melhoria e o
que vence é o melhor. Invertido, vence o que o Dre já achou pior.

### 🔕 DOIS ALARMES FALSOS QUE ENCHIAM A VARREDURA

**"101 linhas de erro nas últimas 24h"** com amostras de 14/07, 01/08 e 14/08.
O filtro era o `mtime` do ARQUIVO: bastava o log ter sido tocado hoje pra toda
linha do rabo entrar na janela. Agora a data vem da LINHA; linha de Traceback
herda a anterior (não tem carimbo próprio e pertence à entrada que a abriu); e
linha sem data nenhuma é contada à parte em vez de virar "de hoje".

**`TELEGRAM_ADMIN_CHAT_ID não encontrada`** — variável FANTASMA: nenhum código
a lê, ela só existia na checklist. A de verdade é `TELEGRAM_ALERT_CHAT_ID` (e
estava setada). Checklist que cobra variável que ninguém usa ensina a ignorar
alerta.

⚠️ **E ao conferir isso apareceu um risco real:** sem `TELEGRAM_ALERT_CHAT_ID`,
o `_avisar` do WhatsApp cai em `TELEGRAM_CHAT_ID`, que é o ID do **GRUPO**. O
QR do login do WhatsApp iria pra comunidade — e QR de login em grupo público é
sessão sequestrada. A variável fica na checklist por isso: não por ser
obrigatória (há fallback), mas porque o fallback manda pro lugar errado.

### 🐞 E UM BUG MEU, DE ONTEM, QUE A AUDITORIA PEGOU

A auditoria imprimiu *"não consegui ler a ordem do daemon"* — o conserto de
17/08 falhando. Causa: `_cfg = _cfg()`. Em Python isso torna `_cfg` local pra
função inteira e a chamada do lado direito vira `UnboundLocalError`.

**O aviso salvou.** Ele foi escrito pra dizer "não sei" em vez de chutar, e foi
isso que expôs o defeito em vez de escondê-lo atrás de um palpite sobre a ordem
da fila — que era justamente o número que o Dre estava decidindo.

---

## 🗓️ Dia 2026-08-17 — o pacote-veneno, e três números que mentiam

Começou com *"a topshoptech está 3 dias sem postar, é falta de fonte ou de
produção?"* — e a resposta era **nenhuma das duas**.

### 🧨 UM ARQUIVO CORROMPIDO PAROU UMA CONTA POR 3 DIAS

O log entregou o culpado, e ele repetia:

    08-15 09:06  'mesa_magica_de_desenho_projetor_de_giraf' → @topshoptech_  ❌ 3x
    08-17 09:15  'mesa_magica_de_desenho_projetor_de_giraf' → @topshoptech_  ❌ 3x

    ProcessingFailedError · 'retriable': False
    Facebook: "There was a problem uploading your video file.
               Please try again with another file."

O `ffprobe` disse por quê, e **não foi o que eu esperava**:

| METADADOS (container) | BITSTREAM (conteúdo) |
|---|---|
| h264 · 1080x1920 · 30fps · 7,93s · aac | `Invalid NAL unit size (-37075930 > 10943)` |
| ✅ tudo dentro do padrão de Reels | `Error splitting the input into NAL units` (×centenas) |

**O arquivo não estava fora de especificação — estava CORROMPIDO.** O container
mente bonito. Quem checa com `ffprobe -show_entries` (como eu ia fazer)
APROVA o vídeo. Só a DECODIFICAÇÃO revela — que é o que a Meta faz do lado
dela. A recusa dela estava certa.

**Por que isso parou a conta inteira:** cada conta entra no slot com UM pacote
(`alvos`), e quando ele falha o laço acaba ali — **não cai pro próximo**. Nada
marcava o pacote, então ele voltava a ser o escolhido no slot seguinte. Um
arquivo ruim = conta parada até vencer, 27 dias depois. **~40 posts.**

**Consertos (3 camadas, porque uma só não fecha):**
1. `daemon_maestro._registrar_falha` — 2 falhas e o pacote vai pra
   `fila_problema/`. MOVE, não apaga. Loga em **ERROR**: quarentena silenciosa
   vira cemitério, e o alerta é a metade útil do conserto.
2. `patch_quarentena.py` — porque o `deploy_seguro` recusou o `daemon_maestro`
   com **COLISÃO** (2 cópias) e a recusa está certa. A cópia da raiz recusou o
   patch por não ter `ok_slugs.append`: ela é anterior ao `post_por_conta`,
   logo é espelho morto — se fosse a viva, a postagem por conta não existiria.
3. `produzir_tiktok._video_integro` — **conferir ANTES de entrar na esteira.**
   Custa 0,6s/vídeo contra um slot perdido; e contra o preço real, que é o
   vídeo envelhecer dias na fila pra só então descobrir que nunca serviu.
   ⚠️ **Na dúvida DEIXA PASSAR** (sem ffmpeg → `True`): barrar produção por
   ferramenta ausente trocaria um defeito raro por uma esteira parada. Aqui o
   erro caro é o falso positivo.

### 📏 E ANTES DE CONSERTAR, MEDIR: é um acidente ou o render quebrou?

`auditoria_video.py` decodificou os **355** pacotes do disco: **5 quebrados
(1,4%)** — 4 vivos em `pronto_para_postar/`, 1 já em quarentena. A resposta
decidiu o conserto: **acidente, não defeito de linha.** Acima de 5% o certo
seria parar e arrumar o render (a produção repõe ~12/dia); em 1,4% a barreira
de entrada resolve. Reconferir em alguns dias.

### 🔢 TRÊS NÚMEROS QUE MENTIAM (e dois eram meus)

**1. O painel dizia 10 posts/semana; eram 39.** `jarvis_status` fazia
`len(por_dia[dia])` — que conta as CHAVES (horários), e no `post_por_conta`
cada chave guarda uma lista. **É o MESMO bug que a `auditoria_postagem`
corrigiu em 11/08 e que sobreviveu no painel por mais uma semana.**

**2. A auditoria AFIRMAVA a ordem da fila.** O texto dizia fixo "a ordem é MAIS
NOVO PRIMEIRO" — e saiu três linhas abaixo do log do próprio daemon dizendo
`ordem MAIS ANTIGO primeiro (drenagem)`. E a diferença muda o diagnóstico: em
LIFO quem vence é o rabo antigo; em FIFO quem vence é o material NOVO. Agora
refaz a decisão do `_drenar_por_idade` em vez de afirmar.

**3. Eu li a PIRÂMIDE como pane.** Reportei "a postagem despencou de 12 pra 0".
O Dre corrigiu: domingo é 0 **por desenho**. Conferido dia a dia:

    ter 8/8 ✅ · qua 4/4 ✅ · qui 12/12 ✅ · sex 8/8 ✅
    sáb 3/4 (faltou 1) · dom 0/0 ✅ · seg parcial (só o slot das 09h)

**A postagem estava rodando exatamente na pirâmide.** Sobrava UMA anomalia — e
era a tech, exatamente onde o Dre tinha apontado.

### 🔌 O PATCH ESTAVA NO DISCO E NÃO NO PROCESSO

O log da legenda da casa não aparecia nem no arquivo certo, mesmo com
`grep -c` = 1 no `agents/meta_uploader.py`. Eu tinha listado três explicações e
**nenhuma era a certa**: o daemon importou o módulo quando subiu, e editar o
`.py` no disco não muda um processo Python que já está rodando. O patch é de
15/08 e o serviço não tinha sido reiniciado desde então — **dois dias rodando
código velho.** Está escrito no roadmap desde julho ("código novo precisa
`systemctl restart jarvis.service`") e eu não lembrei ao montar o diagnóstico.

**Lição que vale além deste caso:** patcher que reporta "✅ escrito" está
dizendo a verdade sobre o DISCO e nada sobre o que está EXECUTANDO. Os dois
patchers novos passaram a mandar reiniciar na última linha.

### ✅ AS TRÊS PENDÊNCIAS ANTIGAS, FECHADAS (17/08)

**1. 5ª ETIQUETA DO `sub_id` — venda passa a cruzar com hook.** A ordem
canônica usava 4 de 5 (`[canal, nicho, produto, FONTE]`) e **nenhuma dizia
qual POST** gerou a venda. Feito primeiro de propósito: a estratégia de hook
mudou hoje, e post publicado sem etiqueta nunca poderá ser atribuído depois.
Três armadilhas no caminho, todas silenciosas:
- `_subids` **omitia** o slot da fonte quando vazia → um `append` ingênuo poria
  o vídeo no índice 3, que `metricas_agent._fonte()` lê como FONTE. O CEO
  passaria a ver centenas de "fontes" que são hashes, cada uma com 1 venda, e
  a poda por venda cortaria fonte boa. **Sem erro nenhum.** Sentinela
  `semfonte` segura a posição; o leitor traduz de volta.
- O ledger gravava `sub_ids=["tiktok"]` — rótulo genérico, não a lista do
  link. Os dois lados nunca tiveram como se encontrar.
- A semente do id era `slug + time.time()` com 3 casas: **5 chamadas deram 4
  ids**. Id repetido = venda atribuída ao vídeo errado, justamente na medição
  que o campo existe pra viabilizar. Com `time_ns+pid+urandom`: 20.000/20.000.

**2. `itemId` NA ORIGEM.** O `preencher_fotos` deu 0/5 porque o id **nunca foi
guardado** — o link curto não o carrega, então era preciso SEGUIR o redirect
pra redescobrir, e o redirect falha (anti-bot, interstício, URL fora do
padrão). E o dado sempre esteve na mão: `shopee_affiliate:444` devolve
`item_id`/`shop_id` no campeão, e o `validar_fila` descartava os dois
**exatamente onde já descartava a foto** — mesmo ponto, mesmo comentário de
03/08, mesmo efeito. Agora: grava na origem, o `curar_fila` repassa (ela
reescreve a fila INTEIRA, campo não copiado é campo apagado), e o consumo vai
por ordem de confiança — fila → `health_cache.json` → rede. Medido com dublês:
**id na fila ou no cache não chama a rede nenhuma vez.**

**3. RAMOS DE LEGENDA — e não era "falta um `.strip()`", era a CONDIÇÃO.**
`if descs.get("instagram")` é True pra `"   \n  "`: string de espaço é truthy.
O ramo disparava, devolvia branco, e o post saía sem legenda **sem nunca
chegar no ramo 3**, que é o único que o guarda valida. É a explicação de uma
contradição que estava solta: medimos *336/336 pacotes com legenda* e havia
post sem — a contagem olhava a EXISTÊNCIA do campo, o publicador olhava a
VERDADE dele.

⚠️ **E o patcher recusou na primeira tentativa, com razão.** Eu escrevi o
regex a partir da "RÉPLICA EXATA" do `diag_pacotes`, que devolvia
`(texto, ramo)`; a função real devolve só o texto — o nome do ramo era
invenção do diagnóstico, pra contar qual disparava. **A DECISÃO é idêntica**
(`if X.get("k"): return X["k"]`, mesma ordem, mesmos campos), então a medição
de qual ramo dispara continua valendo. *"Minha réplica estava errada"* e
*"minha conclusão estava errada"* são coisas diferentes — confundir as duas
joga fora medição que custou trabalho.

O `grep` do arquivo real ainda revelou que **`_legenda_facebook` tem o mesmo
defeito**. Foram 3 ramos corrigidos, não 2.

⚠️ **Isto NÃO prova que causou os 11 posts da casa.** Fecha um caminho real
pelo qual um post sai mudo. "Achei um mecanismo possível" ≠ "achei a causa" —
e quem responde aquele caso é o log da legenda, que só começou a rodar de
verdade depois do restart de hoje.

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

### ⚠️⚠️ O SELO: A SEÇÃO ABAIXO ESTÁ ERRADA — a causa era o `.env` (11/08)

**Leia esta parte antes da de baixo.** A seção seguinte foi escrita por mim
horas antes e a explicação dela é falsa. Deixo as duas porque o jeito como eu
errei importa mais que o erro.

O que eu afirmei: que `textlength` (avanço) tinha 26px de sobra sobre a tinta em
Montserrat, e que por isso o selo saía longe. **Medido depois, na Montserrat
Bold 52 de verdade (baixada do repo do Google Fonts): avanço 238,4 · tinta
0..238 · sobra de 0,4px.** A sobra não existe. O `_fim_da_tinta` que escrevi era
no-op duas vezes: `textbbox` do PIL é baseado em AVANÇO (acompanha espaços à
direita — testado), e mesmo que fosse tinta não mudaria 0,4px.

**A causa real, por aritmética do quadro do MP4:**

    logo termina em 204 · nome começa em 212  -> TEXTO_DX = 8  (padrão do código: 16)
    tinta do nome = 238px  (= Montserrat Bold 52 ✓)
    selo começa em 478    -> SELO_DX = 478-212-238 = 28  (padrão do código: 12)

**O `.env` da VPS define `SELO_DX` e `TEXTO_DX`, e ambiente ganha do código.**
Eu mudei o padrão no fonte duas vezes (2 → 12) e o vídeo não mudou um pixel,
porque aquela linha nunca foi lida. É a MESMA armadilha do
`ELEVENLABS_VOICE_ID_<NICHO>` mascarando o `contas.json`, documentada aqui em
10/08 — eu documentei a lição e caí nela de novo em 24h.

**Correção que fecha a classe inteira:** `knobs` no relatório agora grava
**valor + origem + padrão** (`{"valor": 28, "origem": "env", "padrao": 12}`) e
uma lista `_divergentes`. Valor sozinho não bastava: `"SELO_DX": 28` não conta
que o código dizia 12 e foi ignorado. `"28 (env, padrão 12)"` conta.

⚠️ **E o erro de método, que é o que não pode repetir:** eu diagnostiquei por
teoria e só medi o que confirmava a teoria. A pergunta certa — "o valor que
chegou no render é o que está no código?" — era uma linha de `grep` no
relatório, e a ferramenta pra responder eu já tinha construído no dia anterior.
**Quando um ajuste no código não muda o resultado, a primeira hipótese é que o
código não foi lido — não que a fórmula está errada.**

✅ **RESOLVIDO:** `.env` da VPS, linha 76, tinha `SELO_DX=28` → agora `12`.
(`TEXTO_DX=8` na linha 80 fica como está: é o espaçamento real do template.)
Geometria fechada e conferida contra o MP4: `texto_x 212 + tinta 238 + 12 =
462`, vão de 12px. **TEMPLATE V1.0 FECHADO DE VERDADE** — cinco rodadas, e
nenhuma delas era sobre design: quatro foram diagnóstico meu errado e uma foi
o `.env`.

### ~~O SELO: eu media a fonte que não é a de produção~~ (11/08 — SUPERADA)

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

### 📊 AUDITORIA DA PUBLICAÇÃO — o gargalo não era onde eu apontei (11/08)

A revisão geral achou "274 pacotes prontos, mais antigo de 15 dias" e eu
levantei a hipótese de que a postagem era o gargalo. O Dre e o ChatGPT pararam
a fila de melhorias e mandaram **medir antes de consertar**. Fizemos
`auditoria_postagem.py` (só lê; importa as funções do próprio daemon em vez de
reimplementar). O resultado derrubou a minha hipótese.

**NÃO HÁ GARGALO DE PUBLICAÇÃO:**

    44 vídeos em 7 dias  ·  capacidade configurada 48/semana  →  92%
    por conta: beauty 11 · tech 11 · geral 11 · casa 11  (balanceamento perfeito)

`post_por_conta` funciona. E as duas hipóteses que EU tinha levantado morreram
com dado: **0** pacotes com `.mp4` de nome errado, **0** vencidos na fila.

**O ESTOQUE ERA 152, NÃO 274.** 122 pastas (45%) já foram postadas e só saem de
`pronto_para_postar/` quando vencem (27d). Quem olha a pasta vê quase o dobro —
e foi esse número inflado que gerou o alarme inteiro.

**O PROBLEMA REAL — a produção não desliga, e a ordem mata o rabo da fila:**
`daemon_maestro.py:841-845` calcula `falta = alvo - estoque` (colchão de
`estoque_alvo_dias: 3` ≈ 5 pacotes/conta) e **depois** o piso sobrescreve:
`falta[n] = max(falta[n], piso - ja_hoje[n])`. Com geral em 126 e casa em 19, o
`falta` é zero em todas — mas `producao_minima_por_conta: 1` produz assim mesmo.

    entram ~4/dia · saem 6,29/dia → drenagem líquida ~2/dia
    152 ÷ 2 = 66 dias pra esvaziar   ·   validade = 27 dias

E a ordem é MAIS NOVO PRIMEIRO (`daemon_maestro.py:1050`): os 6,29 postados
consomem primeiro os 4 que chegaram hoje, e só ~2,3/dia sobram pra comer a
pilha antiga — pelo TOPO dela. O pacote de 15,3 dias está no fundo de 152:
alcançado em ~66 dias, vence em 11,7. **Os 23 pacotes na faixa 15-27d estão a
caminho da `fila_vencida/` por aritmética, não por lentidão.**

O comentário do próprio código descreve a premissa que quebrou: *"produz 3/dia
contra ~5/dia postados — a esteira encolhe"*. Valia com 3 contas e fila
pequena.

⚠️ **A trava que o ChatGPT propôs (`se fila > LIMITE: reduzir produção`) JÁ
EXISTE** — é o `estoque_alvo_dias`. Está sendo anulada pelo piso. É config
(`producao_minima_por_conta: 0`), não código.

**Decisão do Dre (11/08):** `moda` e `pet` só entram quando o Jarvis produzir
conteúdo de forma autônoma. Zero pacotes nelas é o comportamento certo, não
defeito. ⏳ Guarda a fazer junto com a autonomia: o piso itera as CHAVES do
`contas.json`, então quando o roteador começar a classificar em moda/pet ele vai
gerar 1/dia pra contas que não postam — pacote que entra na fila, conta como
estoque e vence sem sair.

**Três erros MEUS nesta auditoria, achados medindo:**
1. `len(por_dia[dia])` conta SLOTS, não posts (`por_dia[dia][HORARIO] = [slugs]`
   no modo `post_por_conta`). Reportei "publicação a 23% da capacidade" — o
   número certo é 92%. A assinatura estava na saída: a série nunca passava de 3,
   que é o teto de slots da pirâmide, e eu li como achado sobre o sistema.
2. Janela de erro de log pela data do ARQUIVO, não da LINHA: reportou erros de
   14/07 e 01/08 como "últimas 72h".
3. `RAIZ = parent.parent` do daemon aponta pra fora do projeto no repo achatado;
   a auditoria media `/home/user` e imprimia "0 pastas" com cara de resposta.

### ⚠️ PARAR A PRODUÇÃO NÃO BASTA — a ORDEM é que mata a fila (11/08)

O ChatGPT aprovou `producao_minima_por_conta: 0` e pediu FIFO "como melhoria".
Fazendo a conta, FIFO não é melhoria: **sem ela o resto não funciona.**

    estoque 152 · ritmo 6,3/dia · mais antigo 15,3d · validade 27d
    drenar tudo = 24,2 dias

    MAIS NOVO PRIMEIRO   o mais antigo é o ÚLTIMO a sair: dia 24, idade 39d → VENCE
    MAIS ANTIGO PRIMEIRO o mais antigo sai hoje; o mais NOVO é o último,
                         sai no dia 24 com 24d → cabe nos 27

Zerar o piso muda **quantos entram**, não **quem sai primeiro**. Com a ordem
antiga, o rabo vence de qualquer jeito.

**Mas FIFO não é política permanente, é MODO DE DRENAGEM.** Com fila rasa o
argumento original volta a valer (achadinho é perecível, o fresco converte
melhor), e postar sempre o mais velho seria trocar um problema por outro. Por
isso `ordem_da_fila: "auto"` (`daemon_maestro._drenar_por_idade`): se o mais
antigo passou de `limiar_drenagem × validade` (0.4 → 10,8d), ordena por IDADE;
abaixo disso, pelo FRESCO. `mais_antigo`/`mais_novo` forçam, e o log diz em
toda rodada qual escolheu e por quê. Testado nos quatro estados: fila funda,
no limiar, sarada e novinha.

Junto: `auditoria_postagem` ganhou a escadinha de envelhecimento, com degraus
relativos à validade (0,65/0,8/0,92) em vez de cravados — degrau fixo em "20
dias" mentiria no dia em que a validade virasse 14.

### 🚨 A ARMADILHA DO DÉFICIT: zerar o piso ia produzir SÓ moda e pet (11/08)

Consequência que só apareceu com o deploy no ar, e que eu tinha subestimado.
A produção escolhe por DÉFICIT: `falta = alvo - estoque` (`_priorizar_por_estoque`),
e o loop de seleção **só aceita produto cujo nicho tem `falta > 0`**. Com o piso
em 1, todas as contas tinham `falta ≥ 1` e a coisa se diluía. Com o piso em 0:

    beleza 25/6 → 0     moda 0/6 → 6
    casa   11/6 → 0     pet  0/6 → 6
    geral  88/6 → 0
    tech   33/6 → 0

**As duas contas que o Dre disse pra NÃO produzir viraram as únicas com
déficit** — conta nova tem estoque zero, então tem o maior déficit e fura a
fila de todas as outras. A produção inteira passaria a servir duas contas que
não publicam, enchendo a fila de pacote que venceria sem sair.

Não explodiu por sorte: o roteador não classificou nenhum produto em moda/pet
em ~1 dia, então `falta` ficou sem candidato. Sorte não é desenho.

**Guarda:** `"ativa": false` no `contas.json` tira o nicho de
`_nichos_das_contas()`. Cadastrar a conta e ligar a produção dela são duas
decisões diferentes, e até hoje o arquivo não conseguia dizer isso. Com a
flag, `falta` fica vazio e a produção para — que é exatamente o que a drenagem
precisa.

⚠️ **A lição:** eu tinha visto esse risco e arquivei como "guarda pra fazer
junto com a autonomia", porque associei o problema ao PISO. O problema era do
DÉFICIT, e remover o piso não o adiava — o ativava. Risco que eu descrevo mas
classifico no mecanismo errado continua sendo risco que eu não vi.

⚠️ Correção no plano do ChatGPT: ele leu que a rota `pdp/get_pc` teria
"estrutura aninhada que pode conter a galeria (`data.item.product_images.
images`)". **Não.** Aquele era um nome de campo que o probe TESTOU; a resposta
medida foi `error=90309999`, sem `data`, chaves numeradas. A galeria continua
fechada pelas três medições acima.

**A lição:** eu abri esta investigação com uma hipótese ("a postagem é o
gargalo") e ela estava errada em todos os pontos verificáveis. O que salvou foi
a ordem imposta pelo Dre e pelo ChatGPT — medir primeiro, não consertar. Se eu
tivesse "arrumado" a postagem, teria mexido no único subsistema que estava
funcionando a 92%.

### ✅ TEXTO QUEIMADO NA FOTO — o último `nao_avaliado` da escada (11/08)

`texto_queimado.py`. Fecha o campo que o `asset_ranker` carregava como literal
`"nao_avaliado"` desde 10/08, e que era o defeito da escova alisadora: a foto do
anúncio vem com texto promocional queimado e o render escreve hook, legenda e
CTA por cima.

⚠️ **NÃO é "tem texto → reprova"**, e a correção é do ChatGPT: *"uma foto de
produto pode naturalmente ter nome da marca, especificação, pequeno texto
informativo"*. Reprovar todo texto reprovaria quase toda foto de e-commerce —
o erro do `faixa_preenchida`, que reprovava o caso bom.

**O que decide é a BRIGA, não a presença.** O template tem geometria conhecida
(`render.py`): a legenda anima na BASE da caixa de vídeo, o destaque fica no
TOPO, e o miolo é onde o produto aparece. O modelo é perguntado ONDE o texto
está (topo/meio/base) e o risco é calculado NO NOSSO CÓDIGO contra a NOSSA
geometria — não estimado por ele. Texto no meio é quase inofensivo; na base,
colide de frente.

    ESCOVA: promocional 32% na base  →  reprovado  (conflito alto)
    só a marca, 3% no meio           →  aprovado
    specs cobrindo 30%, no meio      →  ressalva

`decidir()` fica separada da chamada de rede de propósito: é a única parte
testável sem chave, e é onde mora a POLÍTICA. O modelo diz o que VÊ; o que isso
significa pro vídeo é decisão do projeto. Verificada em 8 casos.

**Três regras que não podem cair:**
1. Sem chave, sem cota, timeout ou JSON inválido → `nao_avaliado`, **NUNCA
   "aprovado"**. ⚠️ Aqui eu divirjo DE PROPÓSITO do `visual_audit_agent`, que na
   dúvida MANTÉM o clipe: lá descartar vídeo pronto por falha de infra é caro;
   aqui dizer "aprovado" por falta de cota é inventar avaliação.
2. O Vision só REBAIXA o nível, nunca sobe. Diversidade e tamanho seguem
   determinísticos — opinião de modelo não vira foto grande.
3. Uma foto usável entre reprovadas NÃO bloqueia o conjunto: o EDL escolhe o
   corte.

Cache por hash do CONTEÚDO, não do nome — o piloto deriva enquadramentos com
nomes novos a cada rodada, e por nome o cache nunca acertaria (cota embora à
toa). Fica em `shared/cache_texto_queimado.json`, gitignored.

⏳ **O que NÃO foi verificado:** a chamada real ao Gemini (não tenho chave no
ambiente de desenvolvimento). Testados: a decisão, os três caminhos de
degradação e a integração com o ranker.

⚠️ **E revisar essa própria pendência achou dois furos sérios**, os dois
falhando PARA O LADO DA APROVAÇÃO — que é o único lado que a regra 1 proíbe:
- `"faixas": "base"` (string em vez de lista) era iterado como STRING e virava
  `{'b','a','s','e'}`, que não colide com `{topo, base}`: a escova saía
  `ressalva` em vez de `reprovado`;
- `"densidade": "32%"` não era parseável e caía no padrão `0.0`, que significa
  "foto limpa" → **`aprovado`**. Um banner inteiro passaria como limpo.

Agora `_faixas()` aceita lista ou string, `_densidade()` aceita `0.32`, `"0.32"`,
`"0,32"`, `"32%"` e `32`, e o que NÃO dá pra ler vira `nao_avaliado` em vez de
zero. Oito variantes de formato testadas, todas convergindo no mesmo veredito.
**"Declarei como não verificado" não é o mesmo que "tratei o caso":** o contrato
só vale se o código sobreviver a ele sendo quebrado.

### 🎯 O RECORTE MIRAVA NO TEXTO — e o detector novo provou (11/08)

Achado que só existiu porque o `texto_queimado` passou a dar número. Nas duas
rodadas do piloto, quem reprovava eram os recortes DERIVADOS, não a foto:

    fila 11   foto_1 (original) 10% de promo  →  var_3 (derivada) 35%
    fila 41   foto_1 (original) 15% de promo  →  var_2 (derivada) 25%, e na BASE

**Mecanismo:** `_detalhe()` escolhe a janela de maior variância de cinza, e
TEXTO é a coisa de maior variância numa foto de produto. O docstring dele
dizia *"variância não sabe o que é produto, mas sabe onde NÃO é fundo — e pra
escolher um close isso basta"*. Não basta: ele acha texto. **A mitigação da
foto única estava concentrando o texto promocional e jogando ele pra base,
que é exatamente onde a legenda entra.**

**Correção sem heurística nova:** o detector já diz em QUE FAIXA está o texto.
O piloto passou a consultá-lo na foto ORIGINAL **antes** de recortar
(`_faixas_com_texto`), e `_detalhe(img, frac, evitar)` foge dessas faixas. A
ordem é o ponto todo — consultando depois, o detector só constata o estrago.

⚠️ **Primeira versão exigia invasão ZERO e não funcionou**, medido: numa janela
de `frac 0.78` sobre foto quadrada, NENHUMA posição cabe fora de um terço
proibido, então ela desistia e voltava ao comportamento antigo (17% de texto no
corte). Trocado por MINIMIZAR a invasão, ordenando por `(invasão, -variância)`:

    texto na foto original: 11,6%
    frac    antigo   novo
    0.62     21,7%   0,0%
    0.70     19,2%   0,0%
    0.78     17,2%   3,4%
    0.85     15,8%   8,4%

Sem faixa proibida o resultado é byte a byte idêntico ao anterior — foto limpa
não regride. **Exigir o ideal e desistir é pior que garantir o melhor
possível**, e só a medição por tamanho de corte mostrou isso.

### 💳 ELEVENLABS COM PAGAMENTO PENDENTE (11/08) — vídeo saindo MUDO

    HTTP 401 payment_required · "failed or incomplete payment"
    Edge (fallback): No module named 'tts_edge'

Nenhum TTS funcionando. O piloto sai com `voz —` e o vídeo vai mudo, sem que
nada além do `faltou` avise. ⏳ Conferir se algum pacote da esteira entrou sem
faixa de áudio enquanto isso durou — esses seriam postados sem narração.

🛑 **DECIDIDO NÃO PAGAR POR ENQUANTO (16/08, decisão do Dre).** A voz paga só
se justifica quando a produção AUTORAL estiver de pé; estamos em fase de teste,
e pagar assinatura pra um caminho que ainda não roda sozinho é gastar antes da
resposta. **Não é pendência — é decisão.**

⚠️ **E O ALCANCE DISTO É MENOR DO QUE EU ESCREVI.** Eu tratei "TTS caído" como
"vídeo saindo mudo" e sugeri urgência no dia 16/08. Fui ler o código: **os dois
caminhos reagem DIFERENTE ao mesmo TTS caído.**

| caminho | roda sozinho? | TTS cai → |
|---|---|---|
| `produzir_tiktok.py` (reciclado) | **sim**, é toda a produção automática | mantém o **áudio ORIGINAL** do criador |
| `piloto.py` (autoral) | não, só por comando | sai **`voz —`**, sem narração |

`produzir_tiktok._narrar_e_trocar_audio` é *best-effort*: falhou o roteiro ou a
voz, ele **não muta nada** — devolve o vídeo com o som que já veio da fonte
(`produzir_tiktok.py:160,177-180`). Ou seja: **o "mudo" só atinge o caminho
autoral, que é justamente o que não está em produção.** O Dre estava certo, e
a razão é mecânica, não de prioridade.

🔧 **`auditoria_audio.py` fica de ferramenta, sem urgência.** Mas o que ela
deve procurar mudou: no caminho vivo o defeito **não é silêncio, é áudio de
terceiro**. O próprio código chama isso de `risco de copyright/crédito` e
dispara alerta no Telegram a cada ocorrência (`produzir_tiktok.py:166-168`) —
então **a pergunta útil é quantos alertas desses chegaram desde 11/08**, e essa
resposta está no Telegram, não no disco.

⚠️ **E A PERGUNTA NÃO É "TEM ÁUDIO?"** — foi isso que quase me fez escrever a
ferramenta errada. Um Reels sem narração mas COM a música de fundo tem faixa,
toca som e **passa em qualquer teste booleano de áudio**. É exatamente o que o
ElevenLabs caído produz: a música sobra, a voz some. Então são 4 estados:

| estado | o que é | pegaria num teste "tem áudio?" |
|---|---|---|
| `MUDO` | sem faixa nenhuma | sim |
| `SILENCIOSO` | faixa presente, volume médio ≤ −50 dBFS | não |
| `SEM_NARRACAO` | som de verdade, `voz —` no relatório | **não** ← o caso |
| `OK` | som + voz registrada | — |

O único jeito de separar "só música" de "música + voz" é o `voz` do
`video.relatorio.json` — o áudio sozinho não sabe. Por isso a ferramenta cruza
ffprobe (faixa), ffmpeg `volumedetect` (volume) e o relatório do render (voz),
e não conclui a partir de um só.

E ela **diz o que não mediu**: sem `ffprobe` ela recusa e sai com código 2 em
vez de imprimir "0 mudos"; pacote já postado e apagado não deixa arquivo, e
sobre esses ela declara não ter opinião. Zero medido no lugar errado é pior
que erro, porque parece resultado.

### 🔒 COLETA EXTERNA: as três portas fechadas, e o que isso decide (12/08)

O Kit 10 Calcinhas foi barrado pelo detector (43% de texto promocional, nível
D). Como edição não conserta matéria-prima, a saída seria a MESMA peça em outra
loja. Medimos as três fontes.

| fonte | resultado | como soubemos |
|---|---|---|
| Shopee | anti-bot `error=90309999` | 3 medições (10/08) |
| **Amazon** | **0/6 identidade confirmada** | 6 produtos, galeria extraída, distâncias 0,35–0,40 |
| Mercado Livre | 403 em `/sites/MLB/search` | endpoint oficial, mesmo autenticado |

**A premissa do `fontes_assets` foi falsificada.** Ela era: *"em marketplace a
foto de FÁBRICA é reusada entre vendedores e entre lojas"*. Entre Shopee e
Amazon, não é — nenhuma das 21 fotos coletadas (9+7+5) chegou perto do limiar
de 0,14, e nem do 0,28 do inconclusivo. Os títulos casavam (8, 4 e 3 palavras);
as fotos discordavam. O módulo recusou os três, que é o comportamento certo:
"a busca devolveu algo parecido" nunca foi "é o mesmo produto".

✅ **O que funcionou e fica:** a extração de galeria (`colorImages` achou 9, 7 e
5 URLs — a parte que eu não pude testar está provada), e o veredito de
identidade em duas vias. A Amazon continua utilizável para o caso minoritário
do produto de marca de verdade; ela só não resolve o gargalo.

⚠️ **E o primeiro número que eu produzi estava errado.** A amostra inicial deu
"TAXA DE ACERTO: 5/10 (50%)" e sugeriu investir. Era taxa de RESPOSTA da busca:
o Mini Inflador CYCLAMI voltou como "ENLEE Mini bomba elétrica" e eu contei
como acerto. Mesmo erro de contar slot como post — o dado existia, a leitura é
que estava errada. Com o `parecer` completo e galeria, o número virou 0/6.

**A DECISÃO QUE ISSO FORÇA:** parar de tentar coletar e passar a fazer UMA foto
funcionar. Não por preferência — por eliminação medida. E há um caminho que
ataca o defeito exato que nos trouxe aqui: **recortar o produto do fundo deixa
o texto promocional para trás**. Uma foto 43% banner vira um recorte limpo do
produto, e o `midia_viva`/`texto_queimado` saem de `lever: None`. É a conversão
de BLOQUEADO_SEM_LEVER em CORRIGÍVEL, local e sem custo de API.

### ❌ RECORTE DO PRODUTO: medido, e PIOROU a foto (12/08)

Eu afirmei que "recortar o produto do fundo deixa o texto promocional para
trás". O ChatGPT cobrou o teste antes de aceitar — e ele estava certo.

Medido no Kit 10 Calcinhas, pelos MESMOS detectores que barraram a foto:

                 ANTES        DEPOIS
    veredito     ressalva     reprovado    ← piorou
    densidade    0.15         0.25         ← o texto ficou MAIS denso
    conflito     medio        alto         ← piorou
    faixas       meio/topo    meio/topo    ← as mesmas

**O mecanismo:** a tarja "mais vendido" e o selo "10 UNIDADES" estão POR CIMA
do produto, não no fundo. O recorte levou embora o fundo — que não tinha texto
— e manteve exatamente o que atrapalha. Sobrou 25% da imagem, e nesse quarto
restante o texto pesa mais, não menos. É comum na Shopee: o selo é colado sobre
o produto justamente pra não sumir na miniatura.

⚠️ **`lever` do texto queimado continua `None`.** Recorte NÃO converte
`BLOQUEADO_SEM_LEVER` em corrigível nesta classe de foto.

**Quatro becos medidos e fechados no mesmo dia:** galeria da Shopee (anti-bot),
Amazon (0/6 de identidade), Mercado Livre (403) e segmentação (piorou). Cada um
seria uma semana construindo sobre premissa errada.

💡 **E o que isso deixou visível:** o dia inteiro foi gasto tentando CONSERTAR
foto ruim, e ninguém perguntou a coisa mais barata — **de 80 produtos na fila,
quantos JÁ vêm com foto limpa?** Se for um terço, a saída não é consertar
material ruim: é PRODUZIR PRIMEIRO o que já está bom. Não custa ferramenta
nova (o detector existe, a fila existe); custa mudar a ORDEM, que é decisão e
não engenharia. `texto_queimado.py --triagem N` mede isso.

### 🐛 O `nao_avaliado` que quase virou conclusão (12/08)

A primeira medição do recorte saiu `nao_avaliado` nos dois lados e eu supus
cota do Gemini. Era `GEMINI_API_KEY não definida`: o `texto_queimado` lia a
variável e nunca carregava o `.env`. Dentro do `piloto.py` funcionava porque
outro import carregava antes.

⚠️ **O que torna isso pior que um bug comum:** `nao_avaliado` é uma resposta
LEGÍTIMA daquele arquivo. O modo de erro é indistinguível do modo normal — a
tabela saiu com `None` dos dois lados e por pouco não foi lida como "o Vision
não viu diferença". Módulo cujo fracasso se parece com o sucesso precisa gritar,
e agora grita: o relatório declara MEDIÇÃO INVÁLIDA e mostra os dois motivos.

### 🏪 A VITRINE PAROU EM 130 — e a pergunta certa não é "o deploy quebrou?" (15/08)

Dre: *"o site tinha 130 produtos deployado, hoje dia 15/08 ainda continua com
130, será que tá rodando certo?"*

**Antes de investigar, o que a vitrine é.** `deploy_site.py:297` publica
`[p for p in produtos if p.get("link")]` — produtos da FILA que têm link de
afiliado. Postar vídeo **não** cria produto novo; quem cria é a MINERAÇÃO. Os 44
vídeos de 7 dias podem ter sido todos dos mesmos 130 produtos, e nesse caso 130
é a resposta CERTA. Trocar o deploy não move um número que já está correto.

⚠️ **Quase repeti um erro que já está escrito neste documento (linha 371).**
Meu primeiro achado foi "nenhum `.py` chama o `deploy_site`" — e o ROADMAP já
registra que eu concluí isso uma vez e estava errado: ele roda **a cada 2h** por
entrada própria do crontab, fora do bloco `JARVIS-AUTO`. *Antes de mexer em
automação, `crontab -l` primeiro.* A lição estava salva e ainda assim eu fui
pelo mesmo caminho — o que a salvou foi reler o próprio ROADMAP antes de falar.

**Buraco real encontrado no `revisao_geral.py`.** O bloco `[site]` confere
`mtime` do index e `git status --porcelain`. Depois de um commit bem-sucedido o
porcelain fica **limpo** — então se o `push` falhou (token expirado), a VPS
mostra index fresco, porcelain limpo e "site sem pendências", com a vitrine no
ar congelada. Os três sinais verdes ao mesmo tempo. Faltava contar
`@{u}..HEAD`.

Virou o **`auditoria_site.py`**: mede os dois lados e compara em vez de
adivinhar — `MATÉRIA-PRIMA` (quantos com link na fila) → `ESPERADO` (menos
mortos do health-cache, menos itemId repetido) → `PUBLICADO` (cards no
index.html) → `NO AR` (commit não empurrado). Cada seta que não bate tem causa
diferente. Roda `crontab -l` de verdade, não faz rede além do `git remote
update`, e não escreve nada.

**MEDIDO NA VPS (15/08 13:15) — a causa apareceu, e não era a que eu apostava.**
O funil inteiro:

```
134 com link na fila (125 shopee · 9 amazon)
 -1 morto no health-check      -1 fundido (mesmo itemId)
 -2 sem foto E sem preço (_vale_mostrar tira da grade)
───
130 cards no index.html  ← e o site no ar mostra 130
```

O deploy **está rodando** (cron `0 */2`, index gerado há 5h, fila atualizada há
4h, health-cache há 1h). O número está travado por **dois motivos somados**:

1. ❌ **8 commits commitados e NÃO empurrados.** Três de hoje, todos "vitrine:
   132 produtos (auto)". O `deploy_site` commita e o `push` falha — exatamente o
   ponto cego descrito acima. Tudo desde então (preço, dedup, produto novo)
   nunca chegou ao ar.
2. A fila cresce devagar: 134 com link para 130 cards. Postar vídeo não move
   esse número; só mineração move.

⚠️ **E o script errou duas leituras na VPS — as duas por olhar a fonte errada.**
(1) O bloco 2 foi caçar log em `logs/` por conta própria, achou um
`cron_site.log` de **11 dias atrás** e leu a última linha dele — *"site sem
mudança — não precisa subir"* — como se fosse o estado de hoje. O log de verdade
é o `>>` da própria linha do cron, que eu cortei em 100 caracteres na impressão.
Agora o caminho do log sai **do cron**, e o palpite em `logs/` vem marcado como
palpite. (2) O `ESPERADO 132 × PUBLICADO 130` saiu como ❌ *"o deploy não
conseguiu subir"* — mas os 2 são o `_vale_mostrar` do `bio_page_builder`
tirando da grade quem não tem **nem foto nem preço**. Era uma decisão
deliberada do builder sendo acusada como falha do deploy. Agora é um degrau
nomeado do funil.

**A lição das duas:** o script mediu certo e *narrou* errado. Contagem confere e
frase não confere é pior que erro de contagem — a frase é o que a pessoa lê.

**A CAUSA REAL: não era credencial, era DIVERGÊNCIA.** O `git push` respondeu:

```
 ! [rejected]  main -> main (non-fast-forward)
```

Alguma coisa publicou no `Topshop-Site` **por fora desta VPS**. O `deploy_site`
commitava a cada 2h, o push voltava rejeitado, a mensagem ia pro fim de um log
que ninguém lê, e a vitrine no ar congelou em 130 enquanto a VPS "publicava".

⚠️ **Eu contei só um lado.** `git rev-list --count @{u}..HEAD` deu 8 e eu li
"8 presos = token expirado". Faltava o outro lado: o `origin` também tinha
commit que o clone não tinha. **"Preso pra subir" e "as duas pontas andaram"
pedem consertos OPOSTOS** — um é autenticação, o outro é reconciliar histórico,
e só o segundo tem risco de apagar trabalho alheio. Agora é
`--left-right --count @{u}...HEAD`, que mede os dois, lista os commits que só
existem no origin e mostra **quais arquivos** eles mexeram (se for só
`index.html`, é gerado e a próxima rodada reescreve; se for outra coisa, é
trabalho que só existe lá).

**Conserto durável no `deploy_site.py`** — ele não tinha como sair disso
sozinho:

- push rejeitado por divergência → `fetch` + `rebase -X theirs` + push de novo
- `"site sem mudança"` deixou de ser saída antecipada: se houver commit nunca
  empurrado, ele empurra mesmo sem HTML novo. **Esse `return 0` era o que
  manteria os 8 commits presos pra sempre**, já que o index regenerado sai
  idêntico
- rebase que não resolve → `--abort` e manda rodar a auditoria. Nada de
  `--force` automático

⚠️ **`-X ours` estava errado e só a medição pegou.** Num **rebase** os lados são
invertidos em relação ao merge: `ours` é o *upstream*, `theirs` são os seus
commits sendo replicados. Escrevi `ours` por hábito de merge; com divergência
1/1 medida, `-X ours` **manteve a versão velha do origin**. É `theirs` que
preserva o index recém-gerado.

Testado ponta a ponta com a forma exata da VPS (3 commits presos + trabalho só
no origin em outro arquivo): antes `1 atrás/3 à frente` → depois `0/0`, o
`index.html` do origin ficou com a versão mais fresca e o `curso.html`, que só
existia no origin, **sobreviveu**.

**RODADO NA VPS, e funcionou de primeira.** `site sem mudança, mas 9 commit(s)
nunca subiram — empurrando` → rejeitado → `divergiu do origin — rebase e tento
uma vez` → `✅ reconciliado e publicado`. `HEAD..@{u}` ficou vazio.
`topshopoficial.com.br` conferido no ar: **"130 achados ativos"**, com preço e
média que antes não subiam (130/132 com valor, 108 com média real).

⚠️ **E O NÚMERO CONTINUA 130 — de propósito, não por falha.** O push quebrado
não segurava PRODUTO, segurava CONTEÚDO: preço, média, dedup, título oficial.
Tudo isso era gerado a cada 2h e morria na VPS. O site no ar era de 11 dias
atrás com os mesmos 130 produtos; agora são os mesmos 130 com dados de hoje.

A conta fecha e não deixa espaço pra ilusão: `134 com link −1 morto −1 fundido
−2 sem foto e sem preço = 130`.

### 🪟 O TETO DE 80: a fila era janela deslizante, não acervo (15/08)

Eu fechei o item acima com *"quem move esse número é mineração"*. O Dre não
aceitou: *"mas como o número não cresce? sempre cresceu, sempre usamos as APIs
e a mineração era automática"*. **Ele estava certo e eu estava repetindo o
sintoma com outras palavras.** "A mineração parou" não era diagnóstico — o
`produtos_fila.json` tinha sido escrito havia 1h.

A causa estava no gravador, `telegram_repurpose_hunter.py:1451`:

```python
def _registrar_no_site(nome, link, imagem="", max_itens: int = 80, ...):
    ...
    fila = fila[:max_itens]        # ← corta nos 80 mais recentes
```

Os **dois** chamadores usavam o default (`produzir_tiktok.py:414`,
`telegram_repurpose_hunter.py:1718`). A cada gravação a fila era truncada:
produto 81 entra, o mais antigo sai. **Cresce e encolhe na mesma rodada.**

**Medido na VPS:** `80 itens / teto 80 — ESTÁ NO TETO`, e os 80 cobriam
**7 dias**. Tudo anterior tinha sido expulso. Efeito colateral que ninguém
pediu: produto que saía da janela e não estava na curadoria **sumia do site**,
um a um, calado.

**Conserto — o teto estava no lugar errado, não no valor errado.** Acervo e
vitrine são coisas diferentes:

- `_registrar_no_site`: `max_itens=0` = **sem teto**. O JSON é o ACERVO, e
  guardar é barato
- `deploy_site.py`: teto novo `VITRINE_MAX_PRODUTOS` (default 200), aplicado
  **antes do `_filtrar_vivos`**. É aí que moram os custos que crescem de
  verdade — peso do `index.html` na primeira pintura (Reels, 4G) e **chamada
  de API do health-check por produto**. Cortar antes mantém a conta de API
  presa ao que vai pro ar, não ao acervo

Hoje isso não muda nada visível (134 < 200); muda daqui pra frente, que é
quando o acervo passa a acumular em vez de deslizar.

**E o deploy do hunter esbarrou na trava — corretamente.** O `deploy_seguro`
recusou com **COLISÃO**: existem duas cópias na VPS
(`integrations/telegram_repurpose_hunter.py` e a da raiz) e ele não sabe qual
é a viva. A recusa está certa; **errada estava a pergunta.** Eu não preciso
subir 1800 linhas para corrigir 2.

Virou o **`patch_teto_fila.py`**: substituição exata de texto, não
sobrescrita. Ou acha o trecho e troca, ou não acha e não faz nada — não tem
como regredir o que divergiu fora deste repo. Mexe em **todas** as cópias de
propósito (o `produzir_tiktok.py:53` importa a do pacote mas cai na da raiz se
o import falhar; corrigir só uma deixaria o teto voltando sem ninguém
entender por quê), roda `py_compile` e restaura o backup se quebrar. É seco
por padrão e idempotente.

Testado com duas cópias na versão antiga: seco lista as duas, `--aplicar`
grava as duas, a segunda passada não faz nada, e as gravações simuladas
acumulam em vez de deslizar.

⚠️ **E EU ARMEI UMA BOMBA NO PRÓPRIO CONSERTO.** A primeira versão deixou o
acervo **ilimitado**. Fui conferir quem mais lê a fila e achei o que tinha
acabado de desproteger:

- `validar_fila.py:281` — `--limite` default **0 (= todos)**, pausa de 1,5s e
  **uma chamada de API por produto**
- `preencher_fotos.py:120` — varre **todos** os produtos sem foto, uma
  chamada cada

Os dois estavam protegidos pelo `fila[:80]` sem que ninguém tivesse escrito
isso em lugar nenhum. Tirar o corte sem limitar os consumidores trocaria uma
janela de 7 dias por **uma rodada que não termina**.

Acervo de verdade ilimitado exigiria travar cada consumidor — em arquivos que
já deram COLISÃO. Um teto **grande e conhecido** resolve o mesmo com um número
só: `FILA_ACERVO_MAX`, default **500** (~45 dias no ritmo medido de ~11/dia,
contra os 7 de antes), e o pior caso continua conhecido. O patcher converge
os dois estados — o original de 80 e o já-patchado-ilimitado — pro mesmo
trecho, e segue idempotente.

**A lição:** eu removi uma trava sem procurar quem dependia dela. A trava não
estava documentada em lugar nenhum — mas isso é motivo pra procurar antes, não
desculpa depois. `grep` em quem lê o arquivo levou 2 minutos e devia ter vindo
antes do primeiro commit, não depois de rodar na VPS.

**Confirmado qual cópia roda:** `.venv/bin/python3` resolve para
`/root/jarvis/integrations/telegram_repurpose_hunter.py`, e as duas cópias têm
o `FILA_ACERVO_MAX`. A do pacote é a viva; a da raiz é o fallback.

✅ **CONFIRMADO PONTA A PONTA (16/08).** O número que não mexia há 11 dias
mexeu: fila **84 → 87**, vitrine **130 → 139 produtos publicados**. Não é o
deploy que voltou a rodar — o deploy já rodava e publicava os mesmos 130. É a
matéria-prima que parou de ser expulsa. A prova de que o teto era a causa não
é o conserto ter sido aplicado; é o acervo ter crescido depois dele **sem que
nada tenha sido acrescentado à mão**.

⚠️ **E APARECEU O PRÓXIMO GARGALO, que o teto escondia.** Com o acervo
crescendo, o `preencher_fotos` rodou nos 5 sem foto e preencheu **0/5**:

    [1/5] Organizador de canto giratório ...     (sem itemId no link)
    [4/5] Kit 2 Luvas de Forno 2 Aparadores ...  (API: produto não encontrado
                                                  (itemId=21797993391))

Isso **não é bug do script** — ele fez exatamente o que devia e disse por que
não deu. É defeito do que a mineração GRAVOU: 4 dos 5 links de afiliado não
carregam `itemId`, e o 1 que carrega aponta pra um item que a Shopee não
reconhece mais (produto saiu do ar). Sem `itemId` não há como perguntar a foto
pra API, e sem foto o produto fica fora da grade — são eles os
`🚧 produto(s) sem foto e sem preço fora da vitrine`.

Conserto de verdade é na ORIGEM (gravar o `itemId` junto do link, ou extraí-lo
do link curto resolvendo o redirect), não no `preencher_fotos`. Fica anotado
como pendência: **enquanto o acervo era janela de 7 dias isso quase não doía —
o produto sumia antes de alguém reparar. Agora ele fica, e fica visível.**

### 🔄 ROTAÇÃO DA VITRINE: decidido, e decidido NÃO fazer agora (15/08)

Pergunta do Dre: *"como os sites maiores fazem pra deixar tanto produto
guardado? Shopee, Amazon, Mercado Livre"* — e a ideia dele: produto que está
na vitrine há 12 semanas sai e dá lugar a um recente que nunca entrou, uma
rolagem por dia.

**Como os grandes fazem:** banco de dados + servidor que monta a página sob
demanda, com paginação. O catálogo tem milhões, mas a PÁGINA tem 40-60 itens.
Ninguém entrega o catálogo inteiro de uma vez. O `topshopoficial` é GitHub
Pages: arquivo estático, sem servidor e sem banco — "todos os produtos"
viraria um HTML gigante.

Dá pra imitar sem servidor (paginação estática: `index.html` + `/p/2.html`…).
**Não vale.** Quem chega vem da bio de um Reels atrás do produto do vídeo, ou
pra dar uma olhada. Ninguém pagina até a página 7 de um link de bio.

**A rolagem é a ideia certa, no eixo errado.** Rodar por IDADE tira do ar um
produto que está VENDENDO só porque é velho. O eixo certo é desempenho — e o
dado existe: `ceo_agent.py:157` já lê o `conversionReport` da Shopee
(`{chave: {'vendas': n, 'comissao': R$}}`). Ranquear por **o que ganhou
dinheiro**, com idade como desempate e uma cota fixa pra produto novo (senão
o recente nunca entra e nunca prova que vende).

⚠️ **E não agora.** São 134 produtos para um teto de 200: a rotação hoje
rotacionaria nada, e o ranking nasceria sem dado pra provar que ordena bem.
Isso vira trabalho quando o acervo encostar nos 200 — ~6 semanas no ritmo
medido (~11/dia) — e aí já existe histórico de conversão pra validar.

**Fica registrado como decisão, não como pendência esquecida.**

### 🎯 ORDEM DE PRODUÇÃO: produzir primeiro o que já tem material bom (15/08)

Retomada da triagem de 12/08: **12 de 20 produtos da fila (60%) já têm foto
limpa.** O esforço todo de coleta estava otimizando a minoria. A saída não é
consertar material ruim — é escolher o bom primeiro, e isso é ORDEM, não
engenharia nova: `asset_ranker` e `texto_queimado` já existem e já foram
calibrados.

Virou o **`fila_qualidade.py`**: lê a fila, julga cada produto pelos
detectores que já existem, persiste em `shared/fila_qualidade.json` e imprime
o ranking + o comando pronto. Não produz nada e não escreve na fila —
produzir continua sendo decisão de quem lê.

⚠️ **CHAVEADO POR LINK, NUNCA POR ÍNDICE — e isto é o coração do arquivo.**
O gravador insere no topo (`fila.insert(0, ...)`) ~11x por dia. Medido com a
fila real simulada: o melhor produto estava no índice 6; depois de **3
gravações** foi pro 9, e `--fila 6` passou a produzir *Produto Campeão 3* —
produto errado, link de afiliado errado, comissão pro lugar errado. **Sem
erro, sem aviso, sem uma linha de código quebrada.** Por isso o `piloto.py`
ganhou `--fila-link`, que resolve pelo link e erra alto quando não acha.

Também limitado por padrão (`--limite 25`): cada produto novo custa download +
Gemini Vision. Default `0 = todos` é o mesmo erro que o `fila[:80]` escondia
no `validar_fila`. Cache por link faz a segunda passada custar zero —
verificado: fila cresce de 31 pra 34 itens e ele só julga os novos.

⚠️ **E O ACHADO QUE MUDA O PLANO: o `piloto.py` não é chamado por NADA.**
`grep` no projeto inteiro — nenhum cron, nenhum daemon; todas as citações são
comentário. **Toda a produção automática é `produzir_tiktok.py`**, que monta
a partir do `inbox_tiktok` — ou seja, **viral do TikTok reciclado**. Os 44
vídeos em 7 dias são todos desse caminho.

O template, as vozes, a música, o crítico — tudo isso vive no caminho
ORIGINAL, que só roda quando o Dre digita o comando. É a mesma forma do
`amazon_playwright` em 03/08 ("existia, funcionava, e ninguém chamava"), com
uma diferença: aqui provavelmente é deliberado, porque o caminho original
ainda produz vídeo de 1 foto.

**Então a ordenação não é um fim — é a PRÉ-CONDIÇÃO para ligar o caminho
original.** Só faz sentido automatizar produção original quando ela puder
escolher entre os 60% com material bom, em vez de pegar o próximo da lista e
travar no `BLOQUEADO_SEM_LEVER`.

**✅ O TETO DO ACERVO FUNCIONOU.** Primeira rodada na VPS: **84 itens na
fila.** Estava travada em 80 desde sempre. Acumulando.

**✅ TRIAGEM COMPLETA (16/08) — 67%, não 55%.** Com a fila em 87 e 83 já
julgados, o número parou de ser amostra: **52 de 78 produzíveis agora (67%)**,
`aprovado 51 · ressalva 12 · reprovado 15`. A amostra parcial de 12/08 dizia
55% e subestimava — o que muda a decisão, porque 51 produtos com foto limpa e
texto aprovado é fila de produção pra semanas, não um punhado. Faltam **4** a
julgar (`--limite 4`); o cache faz a rodada custar só esses 4.

**É daqui que sai o produto do teste do Kling**, e por isso a ordem tinha que
vir antes: escolher o melhor material disponível em vez do próximo da lista é
a diferença entre testar *"foto vira vídeo?"* e testar *"foto ruim vira vídeo
ruim?"*.

⚠️ **MAS A LISTA FILTRA, NÃO ORDENA — e eu quase deixei ela mentir de novo.**
Fila completa (87/87 julgados, 55/82 produzíveis), e os 15 do topo saíram
**todos idênticos**: `C · aprovado · 1 distinta(s)`. Conferido: a chave de
ordenação é a mesma para os **55**, e como o `sorted` é estável, o que a tela
chamava de *"o melhor da fila AGORA"* era **a fila na ordem em que estava**.

A causa está escrita no próprio arquivo desde que eu o criei: com 1 foto por
produto, `nivel` é C pra todos e `distintas` é 1 pra todos — o único eixo vivo
é o texto queimado, que é categórico (3 valores). 53 aprovados não se
distinguem entre si.

**É a mesma forma do erro da tabela de moldes de hook, um dia depois:** a
FORMA de ranking convida a ler ranking mesmo quando os valores empataram.
Filtrar os 27 ruins (16 reprovados + 5 sem material + resto) é resultado real
e é o que a medição de fato entrega. Ordenar não é.

Conserto: o `fila_qualidade` agora conta os empatados no topo e, quando há
empate, diz que ali não é ranking e devolve a escolha pra quem lê ("escolha
por critério seu: nicho, sazonalidade"). Quando a medição de fato separar, ele
volta a recomendar. **E isto vira mais um argumento pro teste do Kling: só com
mais de uma foto — ou com movimento de verdade — é que existe eixo pra
ordenar.**

⚠️ **E O RANKING NÃO RANQUEOU — erro meu, de novo o mesmo.** Os 12 produtos
saíram todos `C·nao_avaliado·1 distinta`: empate geral. Causa:

```python
"texto": (r.get("texto") or {}).get("veredito", "nao_avaliado")
```

A chave que o `asset_ranker` devolve é **`texto_queimado`** e o campo é
**`pior`** (asset_ranker.py:176 · `texto_queimado.avaliar_varias`). `r.get
("texto")` → `None` → `{}` → default `"nao_avaliado"` **em todos**. Não faltou
cota nem `GEMINI_API_KEY`: eu **chutei o nome do campo em vez de ler**, a mesma
coisa da assinatura do `buscar()`.

E o default disfarçou: transformou *"eu li errado"* em *"o detector não
opinou"* — exatamente o truque que o `nao_avaliado` já pregou em 12/08, que
está descrito neste documento, e que eu reproduzi mesmo assim.

**Duas correções, não uma.** A leitura certa, e o comportamento quando a
medição não acontece:

- `nao_avaliado` deixou de pesar `2` (entre ressalva e reprovado) e passou a
  pesar `8` — **ausência de medição não pode SUBIR no ranking por não ter
  sido medida**
- com 1 foto por produto, `nivel` é C e `distintas` é 1 para **todos**: o
  único critério que separa é o texto. Se ele não rodou, o arquivo agora diz
  em voz alta *"o que segue NÃO é ranking de qualidade — é a fila na ordem em
  que estava"*, imprime a distribuição dos vereditos e troca o "produza o
  melhor" por "o primeiro da lista"

Testado nos dois estados: cache todo `nao_avaliado` dispara a recusa; cache
com medição real ordena A > B > C e, dentro do nível, aprovado antes de
ressalva, com os reprovados fora.

**Segunda rodada, com medição de verdade:** `aprovado: 12 · ressalva: 2 ·
reprovado: 8` em 22 julgados. **Replica os 12/20 (60%) de 12/08 com produtos
diferentes** — duas medições independentes batendo.

E o bug não era cosmético: o *"Kit Atacado **50 / 100** Porta Jóias"* era o
**#1** da lista com o campo errado e caiu para **#11** como `ressalva` — é
exatamente o tipo de foto com "50 UNIDADES" queimado, o defeito do Kit
Calcinhas. **A ferramenta estava mandando produzir o produto errado.**

### 🔍 O CRÍTICO APROVA O DEFEITO QUE O DRE RECLAMA (15/08)

Produzida a Camisa Feminina (#1 do ranking). O laudo saiu **PASSOU**, com
`midia_viva 56.06`. E o vídeo é 14,4s de UMA foto, sem som nenhum.

O rastro está na própria saída:

```
[piloto] assets: nível B · 3 distinta(s) de 3 · diversidade 0.479
[piloto]    nicho geral · 3 enquadramento(s) (derivados de 1 foto)
```

`piloto.py --variacoes 3` deriva 3 enquadramentos de UMA foto e **entrega os
próprios recortes ao `asset_ranker`**, que responde "3 informações visuais
distintas". O mesmo produto que o `fila_qualidade` julgou honestamente, lendo
a URL de origem, é **`C · 1 distinta`**.

⚠️ **O sistema mede os próprios recortes e chama de matéria-prima nova.** E o
`midia_viva` passa porque os pixels realmente mudam — ele mede MOVIMENTO, não
informação visual. Uma foto com Ken Burns satisfaz esse gate para sempre.

**O gate diz PASSOU exatamente no defeito que o Dre nomeou desde o começo
("cada vídeo só tem uma imagem"). Métrica que nunca é confrontada com o
veredito humano vira teatro.**

### 🧭 JARVIS 2.0: a pergunta do Dre, minha resposta e a do ChatGPT (15/08)

Dre: *"criem o Jarvis da maneira mais surreal possível... talvez exista algo
que eu não esteja vendo"*.

**Minha posição, tirada do que ACONTECEU e não do que seria bonito.** O padrão
que se repete em toda sessão é um só: **o sistema reporta sucesso enquanto faz
a coisa errada, em silêncio.** Só em 15/08: site publicando nada por 11 dias,
fila apagando um produto por produto que entrava, ranking chamando 22 produtos
de `nao_avaliado`, `midia_viva` aprovando foto parada, `SELO_DX` vindo do
`.env`. Nenhum é falta de inteligência; todos são falta de **verificabilidade**
— e cada um custou dinheiro real.

O que eu acrescentaria, nesta ordem:

1. **Toda ação automática deixa uma afirmação falsificável** — não log, mas
   uma afirmação com observável esperado ("publiquei 132" é checável contra o
   site no ar) e um verificador que confere uma amostra. Torna impossível
   repetir os 11 dias.
2. **Toda métrica que pode ser enganada é calibrada contra o veredito
   humano.** O `midia_viva` é a prova viva: ele passa e o Dre reprova. A
   memória para guardar isso já existe.
3. **O SINAL DE RECOMPENSA REAL — e este é o ponto surreal de verdade.** O
   `conversionReport` da Shopee diz qual produto deu DINHEIRO. Quase nenhum
   sistema de conteúdo com IA tem verdade de campo; quase todos aprendem com
   curtida, que é opinião. **A limitação de uma foto só importa se mudar a
   conversão — e ninguém mediu.** Experimento que decide os próximos 3 meses:
   20 vídeos, metade material rico, metade 1 foto, mesma classe de produto,
   e a comissão decide. Se empatar, economiza meses e nenhuma ferramenta paga.

**Da resposta do ChatGPT — adotar:**

- **Memória negativa.** Amazon 0/6, ML 403, recorte piorou vivem num markdown
  que só humano lê. Em 3 meses alguém repropõe raspar a Amazon. Tem que ser
  consultável pelo sistema.
- **"Quando NÃO fazer conteúdo".** O item mais valioso da lista dele para
  dinheiro: hoje o pipeline assume produto → vídeo. Para os 45% sem foto
  limpa, a resposta certa pode ser carrossel, ou nada.
- **Memória causal / Why-Engine.** Já existe em embrião: o `_knobs` do render
  grava valor + origem + default, e foi isso que resolveu o `SELO_DX`.

**Da resposta do ChatGPT — recusar, com motivo:**

- ⛔ **"Congelar o pipeline e desenhar o Jarvis 2.0."** Tudo que descobrimos
  hoje veio de rodar e medir. Nenhum desses achados apareceria numa sessão de
  arquitetura.
- ⛔ **"O Jarvis cria as próprias ferramentas."** Hoje o `deploy_seguro`
  RECUSOU um deploy porque há duas cópias do hunter e não dá pra saber qual
  roda. Dar geração de código a um sistema que não identifica os próprios
  arquivos é gasolina. Ordem inversa à dele: identidade e proveniência
  primeiro.
- ⛔ **A escada V1→V10** não é falsificável — não dá pra saber se estamos na 5
  ou na 7, então não decide nada.

⚠️ **Ironia registrada:** ele elogia o `deploy_seguro.py` como "primeira camada
de autoengenharia". Ele existe porque 83/179 arquivos são espelho parado e o
deploy ingênuo regredia a VPS em um mês. Não é o começo da autoengenharia — é
a cicatriz de um problema de identidade ainda aberto.

**Segunda rodada do ChatGPT — ele convergiu e trouxe 3 coisas melhores que as
minhas. Aceitas:**

1. **`VERIFIED` ≠ `PASS`, e `UNKNOWN` ≠ `SUCCESS`.** `PASS` = o teste passou;
   `VERIFIED` = existe evidência independente de que a afirmação é verdadeira.
   Sem evidência, o estado é `UNKNOWN` — **nunca** sucesso. Vocabulário melhor
   que o meu "afirmação falsificável".
2. **`midia_viva` em DOIS eixos** em vez de mexer no limiar: `movimento=PASS`
   + `informação=FAIL` → o gate reprova com "movimento detectado sem aumento
   de informação visual". Exatamente certo.
3. **Experimento PAREADO.** Eu propus "10 ricos × 10 simples", que confunde
   efeito de formato com efeito de produto. O certo é o MESMO produto em duas
   versões, mesma janela, mesmo CTA. Correção metodológica real.

E a melhor frase da rodada, que vale como norte: **"encontrar o menor nível de
produção capaz de atingir o objetivo"** — melhor que "fazer vídeos melhores".
Produto que vende com foto parada não deveria consumir render caro.

⚠️ **MAS O EXPERIMENTO NÃO É ATRIBUÍVEL HOJE — furo na minha própria
proposta, achado antes de rodar.** `metricas_agent.py:99` define a ordem
canônica do sub_id: **`[canal, nicho, produto, FONTE]`**. Quatro etiquetas, e
**nenhuma identifica o vídeo**. Duas versões do mesmo produto gerariam o
**mesmo sub_id**, e o `conversionReport` não teria como separá-las. Rodaríamos
20 vídeos para descobrir no fim que o dado não responde a pergunta. A Shopee
aceita 5 etiquetas e usamos 4 — a 5ª precisa carregar a variante, **antes** do
experimento.

⚠️ **E FALTA SABER SE HÁ POTÊNCIA ESTATÍSTICA.** Antes de desenhar qualquer
A/B: quantas vendas por semana existem hoje (`metricas_agent.puxar_conversoes`)?
Com contagem baixa, diferença de conversão é indetectável e o experimento
nasce morto — nesse caso a métrica tem que subir no funil (cliques por
exposição, que tem contagem muito maior). **Medir a potência antes de desenhar
o experimento é o mesmo princípio aplicado a mim mesmo.**

**Onde discordo da ordem dele:** ele quer uma *camada* de verificação antes de
consertar o `midia_viva`. Eu faço o inverso — **construir o princípio
aplicando-o**, um gate por vez, começando pelo que sabidamente mente. Camada
genérica desenhada antes de 3-4 instâncias reais vira framework que ninguém
usa. É a mesma razão de não congelar o pipeline.

### ✅ FASE 1 FEITA: `midia_viva` separa movimento de informação (15/08)

O número de fotos de ORIGEM agora viaja: `piloto` mede `fontes_distintas`
**antes** de derivar recortes → `EDL` → relatório do `render` → crítico.

Estados novos, verificados nos quatro casos:

| difs | fontes | veredito |
|---|---|---|
| alto | 1 | **FALHOU** — movimento sem informação nova |
| alto | 3 | PASSOU (com nota: "3 fotos de origem") |
| alto | ausente | **NÃO RODOU** — "não dá pra saber", nunca "passou" |
| baixo | 3 | FALHOU — slideshow parado |

O terceiro estado é o mais importante: relatório sem o campo **não vira
aprovação**. É o `UNKNOWN ≠ SUCCESS` do ChatGPT implementado no primeiro lugar
onde ele faz falta.

**CONFIRMADO NA VPS.** Mesma Camisa Feminina, mesmo produto, laudo virou:

```
❌ REPROVADO   ·   ❌ midia_viva (57.04)
→ movimento SEM informação nova: os pixels mudam porque há zoom/pan,
  mas o vídeo inteiro sai de UMA foto
```

Antes: `✅ PASSOU · midia_viva 56.06`. **O crítico voltou a dizer a verdade**, e
a partir daqui o que ele aprova significa alguma coisa.

### 💀 O A/B POR COMISSÃO NASCEU MORTO — e a medição matou antes de gastar

**9 conversões em 30 dias.** Medido antes de desenhar o experimento.

Divididas em dois braços: ~4,5 cada. Detectar 50% de diferença precisaria de
**~60 eventos por braço** — no ritmo atual, **~13 meses**. Com contagens
assim, o intervalo de confiança de 4,5 vai de ~1 a ~11: dois braços
indistinguíveis a menos que o efeito seja de 3× ou mais.

⚠️ **Eu propus esse experimento e o ChatGPT o refinou com pareamento. Os dois
estávamos desenhando um experimento impossível.** Foi a checagem de potência
— aplicar a mim mesmo a regra de medir antes de construir — que pegou. E ela
custou um comando.

**A saída não é prêmio de consolação: para ESTA pergunta a retenção é a
métrica MELHOR.** "Vídeo de uma foto só prende o espectador?" é respondido
diretamente por tempo médio assistido. Comissão fica dois saltos depois, cheia
de ruído do preço, da página e da concorrência.

`reach_agent` passou a pedir `ig_reels_avg_watch_time` e
`ig_reels_video_view_total_time` (em segundos — a Graph devolve
milissegundos), degradando para o conjunto antigo quando a métrica não vale
pro tipo de mídia. E **grita quando nenhum post trouxe retenção**: descobrir
daqui a um mês que o campo estava vazio o tempo todo é perder o mês.

**Contagem esperada: centenas por post, contra 9 por mês.** É a diferença
entre um experimento que termina em semanas e um que termina em 2027.

⚠️ **Ainda em aberto:** o sub_id não tem etiqueta de vídeo/variante
(`[canal, nicho, produto, FONTE]`, 4 de 5 slots). Para retenção isso não
bloqueia — a métrica é por `media_id` e o `reach.jsonl` já guarda por post.
Só volta a importar quando o experimento for de COMISSÃO.

**A retenção não veio, e as duas explicações óbvias caíram — medidas:**

| hipótese | veredito |
|---|---|
| falta `instagram_manage_insights` | **NÃO** — o `reach` chegou (207 · 264 · 561 · 128). Sem a permissão ele também viria vazio |
| não são Reels | **NÃO** — `2041 REELS` no `reach.jsonl`, zero de qualquer outro tipo |

Sobra a chamada. **E o defeito é meu, do mesmo feitio de tudo hoje:**

```python
if r.get("error"):
    out["_insights_erro"] = (r["error"].get("message") or "")[:120]
    continue          # ← a próxima tentativa sobrescreve, e ninguém imprime
```

O `_insights` tenta combinações da mais rica pra mais pobre; ao errar, guarda
a mensagem num campo que a tentativa seguinte apaga e que nada lê. Depois
`reach,plays` passa e ele sai satisfeito. Saída final: *"nenhum post trouxe
retenção"* **sem uma palavra sobre o motivo** — com os Reels certos e a
permissão certa.

**Dois consertos:**

- `_insights` **acumula** os erros (`_insights_erros`, lista) e o resumo
  imprime a resposta literal da API. Verificado: a queda pro plano B continua
  funcionando E o motivo sobrevive.
- **`diag_retencao.py`** — pede UMA métrica por vez num Reel real e mostra o
  que a API responde, com `reach`/`views` como controle (se o controle falhar,
  o problema não é o nome). ⚠️ **Não chuta nome de métrica**: a Meta deprecia
  e renomeia Insights por versão, e adivinhar aqui repetiria o erro do campo
  `texto` que inventei no `fila_qualidade`. Ele também fixa a versão da API
  lendo `reach_agent.GRAPH` — sondar em v23 e concluir sobre uma produção em
  v21 responderia a pergunta de outro sistema.

**A API RESPONDEU, e a culpada era `plays`:**

```
❌ plays                          (#100) metric[0] must be one of: impressions,
                                  reach, replies, saved, likes, comments,
                                  shares, total_interactions, follows...
✅ reach                        = 108
✅ views                        = 119
✅ ig_reels_avg_watch_time      = 3567     ← estava disponível o tempo todo
✅ ig_reels_video_view_total_time = 385342
```

⚠️ **O pedido de Insights é ATÔMICO: um nome inválido derruba o lote inteiro.**
`plays` foi depreciado na v21, e TODAS as minhas combinações começavam com
`reach,plays,...` — inclusive o fallback `reach,plays`. O encadeamento caía até
`reach` sozinho, e a retenção nunca chegava a ser pedida. **A métrica nunca
esteve indisponível; o nome morto ao lado dela envenenava o lote.**

Corrigido para `reach,views,...`. Verificado contra as respostas reais:
cadeia antiga devolve `{reach: 108}`; a nova devolve
`{reach: 108, views: 119, retencao_s: 3.57, tempo_total_s: 385.3}`.

### 📉 LINHA DE BASE: 3,57 SEGUNDOS (15/08)

**O espectador médio assiste 3,57s de um vídeo de 14 a 22 segundos.** ~16-25%
de retenção. Primeira medição direta do que o público faz com o que o Jarvis
produz.

⚠️ **E isso põe em dúvida a premissa do projeto inteiro — a minha, a do Dre e
a do ChatGPT.** Passamos o dia tratando "cada vídeo só tem uma imagem" como O
gargalo. Mas se a pessoa sai em 3,5s, **ela nunca chega na parte onde a
variedade visual apareceria.** Diversidade de cenas no meio do vídeo não pode
ser o gargalo de quem abandona no começo.

Hipótese que isso levanta (NÃO é conclusão, é o que a medição sugere): a
alavanca está nos **primeiros 2 segundos** — primeiro quadro, hook, gancho — e
não na riqueza de material ao longo do vídeo. Se for verdade, pagar ferramenta
de vídeo autoral resolveria a parte que ninguém vê.

**Isso muda o desenho do experimento:** testar variedade visual **nos primeiros
segundos**, não espalhada. E agora ele é viável — ~119 views por post × 10
posts por braço ≈ 1.200 observações por braço, contra as 9 conversões/mês que
inviabilizaram o A/B por comissão.

⚠️ **CORREÇÃO NA HORA SEGUINTE: são 6,0s, não 3,57s.** A primeira rodada
completa deu **80/80 posts com retenção · média 6,0s**. Os 3,57s eram **UM
post** — o que o `diag_retencao` sondou.

Sobre um vídeo de 14-22s, 6,0s são **27-43% de retenção**, e isso é outra
história: o espectador chega bem além do hook. **A hipótese que escrevi acima
— "ninguém chega na parte onde a variedade visual apareceria" — nasceu de
n=1 e a medição com n=80 a enfraquece muito.** Ela não morreu; só não sustenta
mais o peso que dei a ela. Fica registrada com a correção do lado, porque
apagar o erro esconderia como ele aconteceu: eu li um número de um post e
generalizei para a frota.

### 📊 O PRIMEIRO CONJUNTO DE DADOS DE AUDIÊNCIA (15/08)

80 posts com comportamento medido. Até ontem havia alcance (quantos viram) e
venda (9 em 30 dias) — nada sobre o que a pessoa **faz durante** o vídeo.

Virou o **`analise_retencao.py`**, e as escolhas dele são o ponto:

- **distribuição, não média.** "6,0s" pode ser 80 posts em 6s, ou 40 em 2s e
  40 em 10s — e essas duas realidades pedem ações opostas. Sai histograma,
  quartis, e um aviso quando média e mediana se afastam mais de 15%.
- **posts sem retenção não entram como zero.** As coletas anteriores ao
  conserto do `plays` ficam de fora e são contadas em voz alta.
- **`ρ` de Spearman, não Pearson:** o alcance tem cauda longa (1.288 contra
  dezenas de ~100) e Pearson viraria refém desse ponto.
- ⚠️ **e ele recusa concluir causa.** Retenção e alcance andarem juntos não
  diz quem puxa quem: o algoritmo entrega mais o que retém, e mais entrega
  muda quem assiste. O arquivo diz isso na tela toda vez.

Validado nos dois sentidos com dados sintéticos: com correlação plantada ele
acha `ρ = 0.78`; com retenção independente do alcance ele acha `ρ = -0.085` e
diz "praticamente independentes". Ferramenta que só sabe confirmar acharia
padrão em ruído.

**RODADO NA VPS — 80 posts. E o resultado contraria a leitura natural:**

```
@topshoptech_      6.4s  ·  alcance 374        mediana da retenção
@topshopcasa_      6.0s  ·  alcance 108        e do alcance
@topshopbeauty._   6.0s  ·  alcance 112
@topshop.__        5.8s  ·  alcance 112
```

**A retenção é praticamente IGUAL nas quatro contas (5,8-6,4s, desvio 2,2s).
O alcance é 3,4× diferente.** Ou seja: o conteúdo segura o espectador do mesmo
jeito em todas — o que muda é **quanta gente recebe**. "Tech é melhor" não se
sustenta: Tech não retém mais, Tech é distribuído mais.

⚠️ **E média × mediana muda a história.** O `reach_agent` reporta médias —
562 / 264 / 207 / 128, que parecem um gradiente, e foi essa tabela que o
ChatGPT leu como *"Tech performa 2,7× acima de Casa"*. Por **mediana** são
374 / 112 / 112 / 108: **Tech, e todo o resto empatado.** O gradiente era
feito de alguns posts virais puxando as médias.

Distribuição: mín 0,9 · p25 4,4 · **mediana 6,1** · p75 7,1 · máx 14,1 ·
desvio 2,2. Concentrada, sem cauda que justifique falar em média.

**Duas correções que a rodada real exigiu:**

1. **Correlação DENTRO de cada conta**, não só agregada. Com retenção quase
   igual entre contas e alcance 3,4× diferente, o `ρ = 0.69` do bolo pode ser
   pura composição (Simpson). Testado nos dois sentidos: com efeito de
   composição plantado ele acusa `agregado 0.944 × dentro 0.247 → é diferença
   entre contas`; com relação real dentro das contas, `0.956 × 0.938 → se
   sustenta`.
2. **Post com alcance < 10 sai da conta.** Apareceu um `0,9s com reach=0`:
   ninguém viu e mesmo assim veio um tempo médio. Insight de post recém-
   publicado ainda não amadureceu — **isso não é retenção baixa, é ausência de
   dado**, e deixá-lo puxava a cauda de baixo.

⚠️ **E um defeito meu que o teste pegou:** a 1ª versão do veredito só
perguntava "o agregado é maior que o interno?". Com os **dois** perto de zero
ela imprimia *"a relação se sustenta dentro das contas"* — anunciando que se
sustenta uma relação que não existe. São três casos, não dois: agregado fraco
(nada a explicar), agregado forte com interno fraco (composição), agregado
forte com interno forte (real). **Ausência de relação não é confirmação de
relação** — a mesma família do `UNKNOWN ≠ SUCCESS`.

**A CORRELAÇÃO SE SUSTENTOU DENTRO DAS CONTAS:** 0.584 · 0.797 · 0.447 ·
0.638 (média **0.617**) contra 0.679 do agregado. Não era composição — reter
mais e ser entregue mais andam juntos **no nível do post**.

### 🎯 A OBSERVAÇÃO DO DRE QUE REENQUADRA O DIA (15/08)

*"esses posts que estão sendo entregues são posts que não são autorais... mesmo
sendo outro tipo de conteúdo, ainda são bons, podemos pegar de exemplo"*

**Ele está certo, e isso é mais importante que qualquer número acima.**

Os 80 posts medidos são **TODOS reciclados** — saem do `produzir_tiktok.py`,
que monta a partir do `inbox_tiktok` (viral do TikTok). O `piloto.py`, que usa
o template autoral que levou semanas de ajuste (selo, logo, vozes, música,
crítico), **nunca foi chamado por nada e nunca postou**.

Ou seja: **mediana 6,2s · desvio 2,1 · ρ 0.617 descrevem o conteúdo
RECICLADO. O autoral tem zero medições.**

O dia inteiro — eu, o Dre e o ChatGPT — discutimos como melhorar o vídeo
autoral, com um crítico afiado, um ranking de material e uma métrica nova.
Nenhum de nós tinha notado que **o que está no ar não é ele.**

**E isso transforma a pergunta cara numa comparação barata.** Um braço já
existe, medido, com variância conhecida (n=80, mediana 6,2s, desvio 2,1). Para
detectar uma diferença de 1,5s (efeito ~0,7 desvios) com 80% de poder, o
segundo braço precisa de **~20-25 posts autorais** — cerca de uma semana no
ritmo atual. Contra os ~13 meses que o A/B por comissão exigiria.

A pergunta que isso responde é a que mais vale no projeto: **o template
autoral é melhor ou pior que reciclar viral?** Todo o investimento de semanas
está apostado no "melhor", e ninguém mediu.

### ❓ OS 42 POSTS COM PLATAFORMA "?" — um argumento omitido (15/08)

Relatório de domingo: **42 de 85 posts sem plataforma**, apagando qualquer
análise por plataforma de venda. A recomendação era *"implementar um
procedimento obrigatório"*. **Não é procedimento — é uma linha.**

São dois produtores gravando no mesmo ledger, e só um passa o campo:

```
produzir_tiktok.py:264   plataforma = (info.get("plataforma") or "shopee")
                 :425    _reg(..., plataforma=plataforma, ...)        ✅
telegram_repurpose_hunter.py:1750
                         _reg_post(..., slug=slug, sub_ids=_subs,
                                   extra={...})                       ❌
```

`posts_ledger.registrar()` tem `plataforma: str = ""` — o campo entra vazio e
vira `?`. Dois produtores, um omitindo o argumento, **quase exatamente meio a
meio: 42/85.**

Virou o **`patch_plataforma_ledger.py`** (o `deploy_seguro` recusa esse arquivo
com COLISÃO, e trocar 1800 linhas pra corrigir 1 é que estaria errado).

⚠️ **Valor DERIVADO, não chutado:** `"shopee" if url_shopee else ""`. Sem link
da Shopee eu não afirmo Shopee — **`?` honesto é melhor que rótulo errado**,
porque rótulo errado contamina justamente a análise que o conserto existe pra
viabilizar. E "não achei o trecho" conta como FALHA no patcher, não como
sucesso silencioso: cópia não corrigida segue gravando `?`.

⚠️ **Só vale pros posts NOVOS.** Os 42 antigos continuam `?`: o campo não
existe no registro gravado, e preenchê-lo agora seria adivinhar a plataforma
de um post do passado.

### 📝 A CONTA CASA POSTA SEM LEGENDA — e o repo não tem o publicador (15/08)

Dre: *"a topshopcasa_ não está postando com legenda, só o vídeo"*. E legenda
não é enfeite: o `hook_alana.py:500` registra que ela existe pra fazer a pessoa
**salvar e compartilhar**, que é dos maiores sinais de alcance do Instagram.

⚠️ **Não dá pra responder lendo este repo.** O daemon publica via
`agents.publish_guard.publicar_com_garantia` — arquivo que só existe na VPS. O
`publish_guard.py` daqui é o `brain/publish_guard.py`, que só valida permissão
e nem tem essa função. Adivinhar o que o outro faz repetiria o erro do campo
`texto` que inventei hoje de manhã.

**O que dá pra afirmar lendo o produtor** (`produzir_tiktok.py:378-411`): o
pacote que vai pro ar tem `video.mp4`, `conta.json`, `engajamento.json`,
`titulo_youtube.txt`, `descricao_youtube.txt`, `hashtags.txt` — e **nenhum
`legenda.txt`**. A legenda mora no `shared/content_plans/plano_<slug>.json`, e
o `descricao_youtube.txt` é legenda+hashtags com nome de YouTube.

Virou o **`diag_pacotes.py`**: abre os pacotes reais e conta, por conta,
quantos têm legenda e onde. O veredito separa dois consertos em arquivos
diferentes — **nenhum pacote com legenda** = defeito na produção; **todos com**
= o publicador não está lendo, e o caminho é o `agents/publish_guard.py` da
VPS. Testado com um cenário onde só a casa vem vazia: aponta a conta, o motivo
("plano existe, legenda VAZIA") e exemplos.

**MEDIDO NA VPS: 336 de 336 pacotes têm legenda no plano.** Todas as quatro
contas, 100%. **A produção está limpa — o defeito é do publicador.**

**E o publicador explica.** `agents/publish_guard._legenda_instagram` tem
**três ramos**, e o guarda da linha 95 valida **só o terceiro**:

```python
descs = plano.get("descricoes") or {}
if descs.get("instagram"):
    return descs["instagram"]            # ramo 1 — SEM .strip(), sem validação
pack = plano.get("publish_pack") or {}
if pack.get("legenda_instagram"):
    return pack["legenda_instagram"]     # ramo 2 — SEM .strip(), sem validação
return (plano.get("legenda") or "").strip()   # ramo 3 — o único exigido
```

A linha 95 bloqueia a publicação quando falta `plano["legenda"]` — o **ramo 3**,
que medimos em 336/336. Mas **o que vai pro ar pode vir do ramo 1 ou 2**, e
esses ninguém checa. Um `descricoes.instagram` com `"   \n"` é *truthy*,
sobrescreve a legenda boa, passa no guarda e sai vazio no Instagram.

⚠️ **É a assimetria que explica o sintoma exato:** post publicado (logo passou
na validação) **e** sem legenda. Nenhuma outra hipótese casa com as duas coisas
ao mesmo tempo.

`descricoes` é escrito em dois lugares — `telegram_repurpose_hunter.py:1693` e
`finalizar_plano.py:152` — ambos com
`{p: d.get("descricao", "") for p, d in descs.items()}`. String vazia é
inofensiva (cai pro ramo 3); **espaço em branco não é**.

**MEDIDO NA VPS, e o Dre fechou o caso.** Ele contou: *"os primeiros 9 vídeos
da casa estavam com legenda"* — e o diagnóstico da casa saiu:

```
@topshopcasa_    instagram:25 · legenda:9      (0 vazias)
```

**Nove pacotes usam `plano.legenda` (ramo 3, validado). Nove vídeos tiveram
legenda.** Os outros 25 saem pelo `descricoes.instagram`, o ramo que ninguém
checa. A correspondência é exata.

⚠️ **Mas nenhum sai VAZIO** — então o ramo 1 tem conteúdo, só não é a legenda
certa. *"Não está vazio" ≠ "é uma legenda"*: pode ser descrição de YouTube,
resto de template, ou só hashtags. Contar caractere responde "tem algo"; o que
responde "é a coisa certa" é ler. Por isso o `--mostrar` imprime o texto cru,
um de cada ramo, lado a lado.

⚠️ **E A MEDIÇÃO MATOU A MINHA HIPÓTESE.** O `--mostrar` na casa devolveu:

```
[descricoes.instagram] babuche_infantil_unissex  (894 caracteres)
   │ Pouca gente imagina que o tipo de calçado usado na infância...
   │ 👉 Garanta o seu no LINK DA BIO!
[plano.legenda] capa_para_colchão_king_size  (716 caracteres)
```

**O ramo 1 produz uma legenda BOA — maior que a do ramo 3.** A assimetria dos
três ramos existe e é um risco real, mas **não é a causa deste sintoma**. O
"9 bate com 9" era coincidência, e coincidência convincente é o disfarce mais
perigoso: eu tinha uma explicação elegante, casada com um número que o Dre
tinha dado, e ela estava errada.

⚠️ **E o erro de método por trás dela:** passei uma rodada medindo
`pronto_para_postar/` — os pacotes **pendentes** — pra explicar 11 vídeos que
**já foram ao ar**. O pacote de um post publicado pode nem estar mais lá. O
próprio arquivo já avisava disso na saída ("ou foi um pacote já consumido") e
eu li por cima.

**A medição certa já existia e eu não estava usando:** o `reach.jsonl` guarda o
`caption` que a própria Graph API devolve por `media_id` — a legenda que o
Instagram TEM, não a que o plano pretendia. Virou o `--postados`: lista os
posts no ar em ordem cronológica, marca os sem legenda e **aponta a data do
primeiro** — que é o divisor entre o "antes" e o "depois" que o Dre descreveu.
Verdade de campo ganha de inferência sobre arquivo local, sempre.

⚠️ **E A SEGUNDA HIPÓTESE CAIU TAMBÉM.** Se o ramo 1 fosse a causa, os planos
teriam ganhado `descricoes.instagram` em 10/08. Medido: **eles têm desde
05/08** — antes e depois da virada. Os posts de 05 a 09 tinham legenda **e**
usavam o mesmo ramo. A estrutura do plano é idêntica dos dois lados.

**O que sobrou provado, e o que não:**

| | |
|---|---|
| 11 posts sem legenda no Instagram | ✅ confirmado pela própria API |
| produção limpa | ✅ 336/336 pacotes com legenda |
| ramo 1 produz legenda boa | ✅ 894 caracteres |
| `descricoes` mudou em 10/08 | ❌ existe desde 05/08 |
| troca de produtor em 10/08 | ❌ cron da casa é de 04/08 |
| código da legenda mudou em agosto | ❌ nada desde 31/07 |
| Dre postou à mão / agendou | ❌ ele confirmou que nunca |

⚠️ **E os "280 caracteres" das legendas boas não significam nada:** é o corte do
meu próprio coletor (`reach_agent.py:114` guarda `[:280]`). Eu ia entregar um
número que parecia padrão e era artefato de medição.

**A causa de eu não conseguir responder é a mesma de sempre: ninguém anotou.**
O `postar_instagram` recebe `legenda`, cria o container e **nunca registra o
que enviou**. Quatro rodadas tentando deduzir de artefato — pacote pendente,
plano no disco, ramo do guarda, data de commit — quando uma linha de log
responderia na próxima postagem.

Virou uma linha no `meta_uploader.py`, antes da criação do container: tamanho
e começo da legenda, com aviso explícito quando vier vazia. **E o problema
está VIVO** — o último post sem legenda é de 15/08, hoje. Então a resposta
chega na próxima rodada de postagem da casa, sem precisar de mais nenhuma
hipótese minha.

O `diag_pacotes.py` ganhou uma **réplica exata** do `_legenda_instagram`,
defeitos inclusos, e reporta por conta **qual ramo dispara** e quantos sairiam
vazios. Copiar lógica normalmente é ruim; aqui é o ponto — o publicador só
existe na VPS, e a única forma honesta de saber por onde a legenda sai é rodar
a mesma decisão sobre os mesmos planos. Testado com `descricoes.instagram =
"   \n "` numa conta e `publish_pack.legenda_instagram = "\n"` noutra: aponta
as duas, com o ramo e o valor cru.

### 🔗 O 1º COMENTÁRIO SUMIU EM 43% DOS POSTS, calado (15/08)

O `diag_pacotes` achou de brinde algo que ninguém procurava:
**`engajamento.json` faltando em 146 de 336 pacotes.** Por conta:

```
@topshopcasa_    25/34   (74%)  ← a mesma conta do problema da legenda
@topshop.__      68/135  (50%)
@topshoptech_    33/96   (34%)
@topshopbeauty._ 20/71   (28%)
```

Esse arquivo monta o **1º comentário com o link etiquetado `fb`** — é o que dá
atribuição por canal no relatório de vendas. Sem ele o post sai sem link no
comentário.

A causa está em `produzir_tiktok.py:396`:

```python
try:
    link_fb = link
    if plataforma == "shopee":
        link_fb = _link_do_canal("fb", ...)      # bate na API de afiliado
    ...
    (pp / "engajamento.json").write_text(...)     # nem depende dela
except Exception:
    pass                                          # ← engole tudo
```

**A geração do link etiquetado derrubava o bloco inteiro — inclusive a escrita
do arquivo, que não dependia dela.** E o `except: pass` garantia que ninguém
soubesse.

Consertado em dois pontos: o link etiquetado tem `try` próprio e **cai pro link
base** (perder atribuição é muito melhor que perder o link), e a falha da
escrita **aparece no log**. Verificado com o link falhando: antes o arquivo não
saía; agora avisa, usa o base, e o arquivo sai.

⚠️ **Sexta vez no mesmo dia que a causa é erro silenciado.** Push num log que
ninguém lia · fila truncando · campo `texto` inventado · `midia_viva` medindo
movimento · `plays` depreciado envenenando o lote · e agora `except: pass`
comendo 43% dos primeiros comentários.

### 🎬 CLIPE DE FORA VIRA REEL: o adaptador que faltava (15/08)

O Dre tem **66 créditos/dia de Kling grátis até 16/09** (com marca d'água) e
vai gerar um clipe de 8s pra responder a pergunta que trava o caminho autoral
há semanas: **uma foto de produto vira vídeo com movimento de verdade?**

⚠️ **Sem adaptador, o teste morreria em "ficou bonito".** O `piloto.py` monta
vídeo a partir de FOTOS — não aceita clipe pronto. A gente compararia
impressão com impressão em vez de Reel com Reel.

**E a peça já existia.** `produzir_tiktok._produzir(pasta, plano, video)`
recebe um ARQUIVO DE VÍDEO local + o JSON do produto e devolve o Reel
completo: template TopShop, logo da conta, hook, narração, legenda, hashtags,
`engajamento.json`, ledger e a pasta em `pronto_para_postar/`. **Reciclar
viral do TikTok e "reciclar" um clipe do Kling é a MESMA operação.**

O `produzir_de_video.py` é só o adaptador: monta o inbox que aquela função
espera e a chama. Pipeline novo aqui seria reconstruir o que já roda 44 vezes
por semana.

Decisões que importam:
- **produto por LINK, não por índice** — mesma razão do `piloto --fila-link`:
  o gravador insere no topo ~11x/dia e o índice aponta pra outro produto
  poucas horas depois, **com o link de afiliado de outro produto junto**.
  Link ausente erra alto, não produz "o mais parecido".
- **pasta temporária**, não o inbox de verdade: teste manual largado lá dentro
  faria o cron reproduzir aquilo sozinho na próxima rodada.
- **não posta** e avisa que o daemon posta nos horários, com o comando pra
  conferir antes.

Marca d'água não atrapalha esta pergunta: quem julga é o Dre, não a audiência.
Ela só impede o A/B de retenção — esse fica pra quando houver clipe sem marca.

### 🔚 O ALARME FALSO ERA MEU: CRLF (15/08)

O `deploy_seguro` recusou o `meta_uploader.py` com **DIVERGENTE** — "alguém
editou de um lado só". Eu usei isso como prova do problema de proveniência, e
até apontei que podia ser a causa do sumiço da legenda.

**Era eu.** O `mtime` do arquivo na VPS é **12/07** e o `diff` mostrava só as
15 linhas que eu tinha acabado de adicionar. Medido:

```
antes do meu commit:  510 CR (CRLF)
depois:                 0 CR (LF)
git diff:  525 inserções, 510 deleções   ← o arquivo INTEIRO
```

Meus scripts de edição usam `Path.read_text()` + `write_text()`. O primeiro
**normaliza CRLF→LF na leitura**, o segundo grava LF: juntos reescrevem o
arquivo inteiro sem uma palavra. Blast radius medido: **2 arquivos** —
`meta_uploader.py` (510 CR) e `telegram_repurpose_hunter.py` (1968 CR).

⚠️ **E os patchers que mandei rodar na VPS faziam o mesmo**, então converteram
as cópias de lá também. Funcionalmente inofensivo em Python; mas é reescrita
de arquivo inteiro, silenciosa, feita por ferramentas que existem justamente
pra não ter efeito colateral invisível. **Nono caso do dia, e o autor sou eu.**

**Consertado nos três patchers**, e cada etapa do conserto quebrou a seguinte:

1. Ler/gravar com `newline=""` → preserva o arquivo… mas os **padrões de
   busca** usavam `\n` e passaram a não casar em arquivo CRLF. O patcher
   avisou (`ESTA CÓPIA SEGUE SEM PLATAFORMA`) — **foi a única razão de eu ver**,
   e é o retorno do princípio de falhar alto.
2. Adaptar os padrões (e as regex, com `\r?`) → passou a casar… mas as linhas
   INSERIDAS saíam em LF dentro de arquivo CRLF: 1970 CR em 1973 linhas.
3. Normalizar SEMPRE, não só quando o texto novo é puro LF.

Verificado no fim contra os arquivos CRLF reais: `1973 CR / 1973 LF` e
`517 CR / 517 LF`, nenhum misturado, os dois compilam, e as três mudanças
entraram.

**O que isso ensina sobre o dia:** eu passei a sessão inteira caçando efeito
colateral silencioso dos outros e produzi um. A diferença é só que o meu foi
encontrado — porque a ferramenta gritou em vez de seguir em frente.

### 🎣 A MEDIÇÃO DOS HOOKS EXISTIA E NÃO ALCANÇAVA A PRODUÇÃO (15/08)

Dre: *"o hook nós temos uma medição... são aqueles em primeira pessoa"*. Ele
estava certo, e ela está escrita em `storyboard.py:18`, de **133 posts de
08/08**:

```
hook em 1ª pessoa   3,8 a 5,1% de engajamento
hook de urgência    1,8 a 2,2%
"A Shopee:"         1,0 a 1,8%   (14 posts)
```

**Mas ela só valia no `storyboard.py` — o caminho AUTORAL, que nunca roda.**
Quem produz de verdade é o `produzir_tiktok.py`, que chama o `hook_alana.py`.
E lá:

```python
amostra = random.sample(FORMULAS, k=min(5, len(FORMULAS)))
```

**Sorteio uniforme sobre 10 moldes, dos quais só 4 são em 1ª pessoa.** ~60% do
que o modelo via vinha de moldes que os próprios 133 posts dizem render 2-3×
menos. E **nenhuma verificação de proibido** neste caminho: o
`storyboard.PROIBIDO` bane `corre ver/que/pra` com o número do lado, e *"corre
ver isso antes"* estava no ar com 6 posts medidos.

⚠️ **Terceira vez no mesmo dia:** o conhecimento existe, está escrito, está
até com o número ao lado — e mora num arquivo que a produção não executa. Igual
ao `piloto.py` e ao `amazon_playwright` de 03/08.

**Dois consertos no `hook_alana.py`:**

1. **Amostra garante 3 de 1ª pessoa em 5** (verificado em 2.000 sorteios).
   Sobem de ~40% para 60% — e ficam **2 vagas abertas de propósito**: gerador
   que só produz 1ª pessoa impede medir se isso continua verdade. A medição de
   08/08 tem uma semana, não é lei da natureza. Sem variação não há
   aprendizado.
2. **Trava de proibido importando `storyboard.PROIBIDO`** — importada, não
   copiada: duas listas do que é proibido envelhecem separadas, alguém corrige
   uma e a outra segue publicando. Recusa e regera (2 tentativas, não
   infinitas — cada uma custa uma chamada), e a **reserva também passa pela
   regra**, porque o banco antigo pode ter frase banida.

Validado contra os hooks que estão **em produção hoje**: barra `"Corre ver
isso antes que esgote"` (o de maior retenção medida, n=6) e o `"A Shopee:"`
(2,8s, entre os cinco piores); deixa passar `"Comprei achando que era
firula…"` e `"Não mostre isso pra quem…"`.

⚠️ **E fica uma tensão registrada, não resolvida:** "corre ver isso antes" é
proibido por ENGAJAMENTO (1,8-2,2%) e foi o de **maior RETENÇÃO** entre os
moldes com n≥5 (6,8s). São métricas diferentes e podem ordenar hooks de formas
opostas — urgência faz parar de rolar, 1ª pessoa faz comentar. O espalhamento
estava dentro do ruído, então isso não é contradição provada; é uma pergunta
que só mais posts por molde respondem.

### 📏 O HOOK NÃO EXPLICA NADA (ainda) — e a tabela convidava a mentir (15/08)

Rodada real: **casaram 68/79** posts pela legenda, e saíram **35 moldes de
hook em 68 posts** — ~2 posts por molde. Só três chegaram a n≥5:

```
6.8s  n=6  "corre ver isso antes…"
6.4s  n=5  "o segredo pra ter…"
6.0s  n=9  "não mostre isso pra…"
```

Com desvio de 2,1s, o erro esperado da mediana é ±0,9 a ±1,2s. **O
espalhamento entre o primeiro e o terceiro é 0,8s** — menor que o ruído. Os
três são indistinguíveis, e 48 dos 68 posts nem entraram na tabela.

⚠️ **A tabela ordenada convidava a concluir "use o molde do topo".** Eu ordenei
medianas e deixei parecer ranking. Corrigido: o arquivo agora imprime o
espalhamento ao lado do ruído esperado e diz na cara quando um não supera o
outro.

⚠️ **E a primeira versão da correção também estava errada.** Usei o erro de
UMA mediana para comparar o **maior com o menor de três grupos** — e amplitude
de k medianas cresce com k só por acaso. Testado com moldes rigorosamente
iguais, ele chamou ruído de "sugestivo". Agora escala pela amplitude esperada
de k amostras (d₃≈1,69). Reteste com 3 sementes de dados nulos: duas dizem
"menor que o ruído", uma cai na faixa cautelosa ("longe de conclusivo"); com
efeito real de 3s, diz "supera o ruído".

**Junção do HOOK real (`analise_retencao`):** o `caption` do reach.jsonl é a
legenda; o hook que aparece NA TELA está no `posts_ledger`. Sem juntar, a
análise fala de legenda achando que fala de hook. ⚠️ O ledger **não tem
`media_id`**, então a junção é pela legenda — e a **taxa de casamento é
impressa antes de qualquer agrupamento**, porque junção aproximada que falha
em silêncio inventa padrão. Agrupa por MOLDE (4 primeiras palavras) e só
mostra grupos com **n≥5**, dizendo quantos ficaram de fora: com 2-3 posts a
mediana é anedota. Testado com moldes plantados — casou 50/60 e recuperou a
ordem (6,9 / 4,1 / 3,5 contra 6,5 / 4,0 / 3,0 plantados).

⚠️ **E a auditoria se contradisse na própria saída.** O bloco 2 leu
`push falhou` do log (rodada das 14:00, código antigo) e o bloco 5 leu do git
que o clone estava em dia — o veredito listou os dois. **Estado vivo ganha de
texto de log, sempre:** o log conta o que aconteceu, o git responde o que é.
Agora achado vindo de log é confrontado com o git e, quando desmentido, sai
como *"resolvido, não pendente"*.

Ainda em aberto e barato: os **2 com link mas sem foto e sem preço** —
`preencher_fotos.py` existe e termina dizendo "agora rode o deploy_site".

⚠️ **Errei duas vezes no primeiro run, e é sempre o mesmo erro.** (1) O
`crontab` não existe no container e o script imprimiu ❌ *"NENHUMA entrada de
cron"*; (2) `_carregar_produtos()` devolveu `[]` porque os JSONs dele não
existem ali, e eu imprimi ❌ *"0 produtos com link"*. Nos dois casos **ausência
de medição virou medição de zero** — a mesma família do `None` vs `None` do
recorte (12/08) e do `nao_avaliado`. Agora o veredito abre com a lista do que
**NÃO foi medido** antes de concluir qualquer coisa.

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

### 🎠 CARROSSEL E STORY: o transporte, e o que a API NÃO faz (22/08)

Objetivo do Dre: **+1.000 seguidores em todas as contas** — é o portão da Shopee
(programa de afiliados dentro do Reels) e ele já provou na conta pessoal (1.200
seguidores → o programa aparece). O plano dele: além da pirâmide de Reels
(3-2-1/dia por conta, 72/semana), somar **1-2 carrosséis e 5-6 stories por dia**,
em horários fixos e diferentes dos Reels.

**Antes de propor qualquer coisa, revisei o que já existe. Três achados mudam o
plano — nenhum deles é opinião, os três são regra da Meta ou número nosso.**

#### 1. Imagem NÃO tem caminho binário. Carrossel exige host público.
A Graph API tem dois caminhos pra mídia entrar num container:

| formato | binário direto (rupload) | precisa de URL pública |
|---|---|---|
| REELS | ✅ (é o que a gente já faz) | não |
| STORIES **vídeo** | ✅ (`media_type=STORIES`, `upload_type=resumable`) | não |
| STORIES **imagem** | ❌ | **sim** (`image_url`) |
| CAROUSEL (filhos) | ❌ | **sim** (`image_url`) |

Doc oficial, literal: *"We cURL media used in publishing attempts, so the media
must be hosted on a publicly accessible server."*

**E o host já existe**: o Caddy do `jarvis.topshopoficial.com.br` (que subiu pro
painel do TikTok, §4.6, e ficou de pé mesmo com a review reprovada) tem
certificado válido. Falta uma rota de arquivo estático — 4 linhas.
`python3 midia_publica.py --caddy` imprime elas.

#### 2. Story por API não carrega figurinha NENHUMA.
Nem enquete, nem caixa de pergunta, nem link, nem contagem regressiva. Menção a
`@perfil` sem figurinha funciona; o resto, não. **Isso tira do story exatamente
a parte que gera interação** — o que sobra é conteúdo, não conversa. Não é
limitação nossa e não tem contorno pela API oficial. Se um dia a enquete valer o
risco, o caminho é Playwright na sessão logada, e aí é outra conversa
(a mesma que já decidimos não ter pra curtir/comentar).

#### 3. Story não traz seguidor. Carrossel traz. **A ordem importa.**
Story é entregue pra **quem já te segue**. O estado das contas hoje:

| conta | seguidores | 5-6 stories/dia alcançariam |
|---|---|---|
| @topshoptech_ | 413 | uma audiência de verdade |
| @topshop.__ | 52 | ~50 pessoas |
| @topshopbeauty._ | 36 | ~36 |
| @topshopmoda_ | 21 | ~21 |
| @topshoppet_ | 9 | **9** |
| @topshopcasa_ | 9 | **9** |

5-6 stories × 6 contas = **36 stories/dia** de produção, sendo que em 4 contas
eles chegam a menos de 40 pessoas. Carrossel, ao contrário, é distribuído pra
não-seguidor via salvamento/compartilhamento — é o formato que **traz** gente.
E o nosso número mais feio hoje é justamente esse: **47.202 impressões → 48
salvamentos (1 a cada mil)**. Carrossel é o formato que ataca esse número.

**Decisão: carrossel primeiro em todas as contas; story primeiro SÓ na
@topshoptech_**, e nas outras conforme cruzam ~100 seguidores. O plano do Dre
não muda — muda a ordem em que ele entra, pra não gastar 36 renders/dia num
público de 9 pessoas.

#### O que foi construído nesta etapa (transporte, não conteúdo)
- **`midia_publica.py`** (novo) — publica um arquivo local numa URL HTTPS
  temporária, com nome tokenizado (a pasta é servida inteira; sem token dava
  pra listar o que a gente ia postar antes de postar), hardlink quando dá, e
  **coleta de lixo por idade a cada publicação** (6h) — sem cron, sem mais um
  serviço pra lembrar de ligar.
  ⚠️ **`publicar()` confere que a URL responde 200 antes de devolver.** É o
  ponto do módulo: sem isso, rota errada no Caddy chega na gente como
  *"container deu ERROR no processamento"* — a mensagem mais inútil da Graph
  API — e a gente procura o dia inteiro no lugar errado.
  `--caddy` (imprime a rota) · `--teste` (prova ponta a ponta) · `--limpar`.
- **`meta_uploader.postar_instagram_story(arquivo)`** — vídeo pelo binário
  (zero infra nova), imagem pelo `midia_publica`. Recusa vídeo > 60s **com a
  frase certa**, porque a Meta recusaria com "ERROR" sem dizer que é a duração.
- **`meta_uploader.postar_instagram_carrossel(imagens, legenda)`** — 2 a 10
  slides, legenda no container **PAI** (nos filhos ela é ignorada em silêncio),
  1º comentário e permalink iguais aos do Reel.
  ⚠️ Os slides publicados **não são apagados logo após o publish** de propósito
  — a Meta pode rebuscar a imagem depois. A coleta por idade resolve sem risco.
- ⚠️ **`postar_instagram` (Reels) ficou byte a byte igual.** É a única função
  deste arquivo publicando em 6 contas todo dia; extrair helpers dela deixaria
  um arquivo de produção DIVERGENTE no `deploy_seguro`. Os helpers novos são
  novos, e só o código novo os usa. Custa ~20 linhas parecidas, e vale.
- Limites respeitados no código: carrossel 2-10 filhos · todos os slides são
  cortados pela proporção do **primeiro** (renderizar todos no mesmo tamanho) ·
  story de vídeo até 60s · 100 posts por API / 24h por conta (carrossel conta
  como 1 — nosso volume nem chega perto).

#### Segunda rodada (22/08, mesmo dia) — o desenho dos slides

**O Dre decidiu a ordem, e a decisão dele é melhor que a minha proposta:** *"os
stories é exatamente para os seguidores que já nos seguem, certo? fazendo esse
plano e chegando aos +1000 seguidores, o nosso plano de stories já estaria
sendo executado... podemos focar nos carrosséis até ficar excelente/perfeito, e
depois ir pros stories."* Ou seja — o mesmo sequenciamento a que a medição
chegou, mas pelo motivo certo: story não é uma etapa que se pula, é uma etapa
cujo público ainda está sendo construído. O roteiro dele pro story já está
anotado pra quando chegar a hora: **reel publicado no início → CTA pro grupo do
WhatsApp → 2 posts de curiosidade**.

**⚠️ JPEG É O ÚNICO FORMATO QUE A META ACEITA EM IMAGEM.** Doc, literal: *"JPEG
is the only image format supported. Extended JPEG formats such as MPO and JPS
are not supported."* PNG não devolve "formato inválido" — devolve o mesmo
`ERROR` genérico de container que qualquer outro problema devolve. O
`_garantir_jpeg()` converte antes de subir (achatando o alfa contra BRANCO, que
é o fundo do template das contas novas), e o renderizador já grava `.jpg`.

**`carrossel_render.py`** (novo) — desenha os slides. Não escolhe produto, não
escreve hook, não decide conta: recebe um plano e desenha.
- **1080×1350 (4:5)**, não 1080×1080: é a maior área que o feed cede, e o
  quadrado joga 25% da tela fora.
- **Todos os slides do mesmo tamanho** — *"Carousel images are all cropped based
  on the first image"*. Slide de proporção diferente não é reescalado, é
  **cortado**, e o corte come o texto de baixo sem avisar.
- **O cabeçalho é o do Reel** (logo redonda, "TopShop", selo aparado, @handle) e
  o fundo sai do mesmo `_cor_fundo(nicho)` — senão o carrossel entra no grid com
  outra cara e a conta parece de duas pessoas.
- Os primitivos vêm do `render.py` por **import**, não copiados: `_texto_rico`
  (emoji colorido com ZWJ), `_quebrar` (largura real), `_fonte`,
  `_logo_circular`. Duplicar garantiria divergência.
- `CAPA_FONT=112` com encolhimento automático até 56. **Encolher é o caminho,
  cortar não é** — foi o teto fixo de 40 caracteres do `hook_alana` que matou
  todo hook de duas linhas sem ninguém ver.
- Foto **coberta com corte central**, nunca esticada: produto deformado é a
  diferença entre "achadinho" e "anúncio suspeito".
- ⚠️ `👉` e não `→`: a seta U+2192 não existe na Montserrat nem na Liberation e
  sai como espaço vazio; o emoji passa pelo caminho colorido, que não depende de
  a fonte de texto ter o glifo.
- `--exemplo <nicho>` renderiza um carrossel de demonstração sem plano nenhum,
  pra ver o layout antes de gastar produto.

**`patch_carrossel_uploader.py`** (novo) — porque o `deploy_seguro` recusou o
`meta_uploader.py` com **DIVERGENTE** (8 commits acompanhados, conteúdo da VPS
não bate com nenhum; alguém editou de um lado só e ninguém sabe o quê).
`--forcar` apagaria essa edição num arquivo que publica em 6 contas todo dia — e
**não precisa**, porque todo o código novo é aditivo. O patch insere, é
idempotente, compila antes de gravar, guarda `.bak` e tem `--desfazer`.
Testado contra uma cópia real do arquivo com uma edição local simulada: as
funções novas entram, as antigas ficam, **a edição da VPS sobrevive**.
⚠️ Ele **recusa** quando não acha âncora, em vez de anexar no fim "pra não
falhar" — ali as funções ficariam depois do `if __name__`, existindo mas
inalcançáveis pelo CLI que as chama. Conserto que parece ter funcionado é pior
que erro.

#### 🧠 CAROUSEL BRAIN (22/08) — e as duas coisas que eu recusei fingir

O Dre aprovou o template ("tá ótimo e aprovado") e trouxe o ranking de
formatos + a distribuição-alvo: **40% Lista · 20% Erros · 15% Antes/Depois ·
10% Comparação · 10% Passo a passo · 5% História**, pelo motivo que ele deu:
*"você é afiliado. O objetivo não é apenas viralizar, mas fazer a pessoa chegar
no produto."* Mais: 8-12 palavras por slide, numeração `1/8` inclusive na capa,
e o slide 1 tem que parecer **capa de vídeo viral, não arte publicitária**.

**⚠️ 7 ESTRUTURAS, NÃO 10 FORMATOS.** "Lista rápida", "Produtos que parecem
mentira" e "Checklist" desenham exatamente os mesmos slides — muda o ângulo do
hook, não a arquitetura. Tratá-los como formatos distintos criaria três
geradores quase idênticos e **três entradas de métrica medindo a mesma coisa
com nomes diferentes**, e aí nenhuma delas junta amostra suficiente pra decidir
nada. Então os ângulos viram variação de hook DENTRO da lista. Mesma coisa com
"Segredo revelado", que é `historia` com outro ângulo. `mitos` ficou com peso 0:
estrutura pronta, entra na roda com `CARR_PESO_MITOS=8` no `.env`, sem código.

**⚠️⚠️ O "DESEMPENHO HISTÓRICO POR CONTA" NÃO EXISTE PRA CARROSSEL.** O Dre
pediu que o cérebro escolhesse "com base no nicho, produto e desempenho
histórico de cada conta". Os dois primeiros existem. O terceiro não:
`metricas_posts.jsonl` tem 215 registros e **todos são de Reel**, e o arquivo
nem tem campo `formato`. Escolher formato de carrossel por desempenho de Reel é
transferir aprendizado entre duas coisas que o algoritmo distribui de forma
diferente — é o mesmo erro do "hook campeão" que a medição de 21/08 desmentiu em
um comando. Então o cérebro tem duas fases e **diz em qual está**:

- **FASE 1 (agora)** — sorteio pela distribuição-alvo com **cobertura
  garantida**: enquanto uma conta não tiver `CARR_COBERTURA` (3) carrosséis de
  um formato, esse formato fura a fila. Sem isso, o sorteio de 40% pra Lista
  levaria semanas até a conta ver um "Erros" — e nunca haveria o que comparar.
- **FASE 2 (depois)** — a distribuição é inclinada pelo **salvamento medido**
  por formato naquela conta, *pooled* (Σ salvos ÷ Σ alcance), com fator preso
  entre 0,5× e 2×. ⚠️ O teto existe porque sem ele um formato com 2 posts de
  sorte comeria a distribuição inteira e a medição pararia de existir.
- Cada carrossel montado é anotado em `shared/carrosseis_ledger.jsonl` com o
  formato. **É esse arquivo que faz a fase 2 existir um dia** — sem ele, daqui a
  um mês "qual formato segura?" não tem resposta, igual a "qual legenda foi
  enviada?" não tinha em 15/08.

**O que entrou:**
- `carrossel_brain.py` (novo) — escolhe o formato (e **imprime o motivo**:
  decisão que não se explica não se corrige), busca os produtos do nicho pelo
  `roteador_contas`, baixa as fotos, pede o texto ao Gemini em JSON com retry, e
  **une o texto do modelo com os FATOS** (preço, foto, link) que nunca vêm dele.
  Reserva honesta quando não há chave: usa só nome e preço, sem fingir conteúdo
  editorial que ela não tem como escrever. `--formatos` mostra pesos, alvo e o
  que já foi feito.
- `carrossel_render`: **slide de TEXTO** (`_slide_texto`) — rótulo em pílula
  ("ERRO 1", "PASSO 2") + frase grande. ⚠️ Sem ele metade dos formatos não
  existia: Erros, Passo a passo, História e Mitos são slides de frase, e pelo
  `_slide_produto` saíam com uma moldura de foto vazia embaixo de cada erro. O
  bloco é **medido antes de desenhar** e centrado quando não há foto — começando
  sempre no mesmo y, uma frase curta deixava meia tela branca no pé, que parece
  slide que faltou carregar.
- Capa numerada (`1/8`): numerada ela **anuncia o tamanho do post** no feed, e é
  isso que faz começar o arrasto.
- `_vigiar_palavras`: avisa acima de 12 palavras. O render só avisa (ele desenha
  o que recebe); quem corta é o brain. Assim o aviso pega até plano escrito à
  mão. ⚠️ Isso importa porque `_texto_que_cabe` **obedece calado**: um slide de
  20 palavras vira parágrafo em corpo 56 e ninguém reclama.

#### 🔧 COMO OPERAR O CARROSSEL — os comandos, na ordem (22/08)

⚠️ **TUDO RODA DE DENTRO DE `~/jarvis`, NUNCA DE `~`.** Registrado porque
aconteceu: mandei os comandos sem o `cd` e a saída foi `fatal: not a git
repository` três vezes seguidas + `.venv/bin/python: No such file or
directory`. Os dois erros são a MESMA causa (diretório errado), e nenhum dos
dois diz isso. O `pjc` é um remote de `~/jarvis`; o venv também mora lá.

**1. Trazer os arquivos** (todos são de RAIZ — nenhum vai em `agents/`):

    cd ~/jarvis
    git fetch pjc claude/opa-clau-dgs591
    for f in carrossel_brain.py carrossel_render.py midia_publica.py \
             patch_carrossel_uploader.py; do
        git show FETCH_HEAD:$f > $f
    done

**2. Patchar o uploader** (o `deploy_seguro` recusa: DIVERGENTE):

    cd ~/jarvis && python3 patch_carrossel_uploader.py
    systemctl restart jarvis.service

**3. Abrir o host público** — sem isso o carrossel renderiza mas não publica:

    cd ~/jarvis && python3 midia_publica.py --caddy    # imprime a rota
    # cola no /etc/caddy/Caddyfile, dentro do bloco jarvis.topshopoficial.com.br
    caddy validate --config /etc/caddy/Caddyfile && systemctl reload caddy
    .venv/bin/python midia_publica.py --teste          # tem que dar 200

**4. Usar:**

    cd ~/jarvis
    .venv/bin/python carrossel_brain.py --formatos               # pesos e feitos
    .venv/bin/python carrossel_brain.py --nicho casa --render pronto_carrossel/teste
    .venv/bin/python carrossel_render.py --exemplo casa          # só o layout

**Knobs no `.env`** (nenhum obrigatório): `CARR_PALAVRAS_MAX` (12) ·
`CARR_COBERTURA` (3) · `CARR_PESO_<FORMATO>` · `CARR_MODELO` ·
`MIDIA_PUBLICA_DIR` · `MIDIA_PUBLICA_URL` · `MIDIA_PUBLICA_HORAS` (6).

#### 🔌 O CICLO FECHOU: `--postar` (22/08)

`preparar_pasta()` escreve na pasta o mesmo contrato que o vídeo já usa —
`conta.json`, `engajamento.json`, `legenda.txt` — e `publicar()` chama o
uploader. `carrossel_brain.py --nicho X --render PASTA --postar` faz o caminho
inteiro: escolhe formato → escreve texto → baixa fotos → desenha → publica →
anota a URL no ledger.

⚠️ **SEM `conta.json` A PASTA POSTA NA CONTA ERRADA, E EM SILÊNCIO.** O
`_ativar_conta` do uploader procura esse arquivo ao lado do 1º slide; **não
achando, ele não falha** — cai nas env vars globais e publica no `@topshop.__`.
Um carrossel de pet sairia na conta geral sem uma linha de log. Por isso
`preparar_pasta` levanta exceção em vez de seguir: é melhor não postar do que
postar no lugar errado. E é o MESMO contrato de pasta do vídeo de propósito —
formato novo não é motivo pra inventar convenção nova.

⚠️ **Legenda vazia é preenchida com hook + CTA.** A reserva (sem Gemini) não
escreve legenda, e legenda vazia já custou 11 Reels da @topshopcasa_ em 15/08.

Sem `--postar`, ele registra o carrossel MONTADO assim mesmo: a cobertura da
fase 1 conta produção, e ensaio também consome produto da fila.

⚠️ `shared/carrosseis_ledger.jsonl` entrou no `.gitignore` — é **estado da
VPS**, não código. Ele foi versionado por engano num `git add -A` meu e os
registros dos meus testes locais teriam poluído a contagem de cobertura da VPS.

#### 🔎 A PRIMEIRA RODADA REAL, E OS TRÊS DEFEITOS QUE ELA MOSTROU (22/08)

O Dre rodou na VPS com o Gemini de verdade. O carrossel saiu; o `--postar`
morreu com `ImportError: cannot import name 'postar_instagram_carrossel'` —
**o `patch_carrossel_uploader.py` foi baixado e não foi executado**. Fica
anotado que o passo 2 do roteiro de operação é fácil de pular justamente por
ser o único que não é um `git show`.

**1. ⚠️ DUAS DEFINIÇÕES DA MESMA REGRA, EM DOIS MÓDULOS — e as duas se achando
certas.** O aviso de palavras disparou em 3 dos 4 slides com o brain
convencido de ter obedecido. Causa: o brain cortava **cada campo** em 12
palavras e o render contava o **slide inteiro**. Título de 12 + linha de 12 =
24. Agora existe `_orcamento(titulo, linha)`: o teto é do SLIDE, o título tem
prioridade, e **a linha de apoio entra inteira ou não entra** — cortada no meio
ela sai como *"Preço de outro mundo e ainda vem"*, que é pior que ausente
porque parece defeito de carregamento em vez de escolha. Título é diferente:
cortado, ainda deixa uma frase que se lê. O prompt também passou a dizer
"por SLIDE, título e linha SOMADOS", em vez de "por campo".

**2. Rótulo que o desenho ignora não deve aparecer no terminal.** No formato
`lista` o `_slide_produto` não tem pílula, então o rótulo era descartado — mas
o print do CLI mostrava `[R$ 299,90]` e `[Bizarro!]` como se fossem sair no
slide. O terminal tem que mostrar o que o feed vai mostrar; agora o rótulo é
zerado em `lista` e `comparacao`.

**3. A legenda de reserva era ruim, e o Dre pegou.** *"tem como colocar outro
tipo de legenda?"* — tem, e a resposta estava dentro de casa: o projeto **já
tem** um gerador de legenda rodando nos Reels (`gerar_legenda_curiosidade`, com
banco de reserva por nicho). "hook + CTA" não é legenda, é o título repetido
embaixo da foto. Agora são três degraus: (1) a legenda que o brain escreveu,
que conhece o carrossel inteiro; (2) `gerar_legenda_curiosidade`, o mesmo
gerador dos Reels; (3) hook + CTA, só se os dois falharem. Nunca vazia.

**Falso alarme meu, registrado pra não confundir de novo:** escrevi o aviso do
`conta.json` de um jeito que soou como problema existente, e o Dre perguntou
*"como assim sem conta.json? achei que já estavam todas resolvidas"*. Estão. O
`preparar_pasta` escreve o arquivo; o aviso descreve o que aconteceria SE
faltasse, e é por isso que a função levanta exceção em vez de seguir.

**Sobre o tom, o Dre decidiu MANTER** — e a decisão é dele com razão: *"apesar
de soar meio anúncio, a gente é afiliado, de toda forma precisamos vender, e
isso é mais um CTA e uma chantagenzinha do que anúncio... só não pode parecer
muitooo anúncio"*. Eu tinha marcado *"Preço de outro mundo!"* como defeito; não
é. O prompt fica como está.

#### 📷 AS FOTOS: não faltava foto no acervo, faltava ESCOLHER quem tem (22/08)

2 de 3 produtos saíram sem foto. Antes de consertar, três causas possíveis, e
eu não conseguia dizer qual — porque **o meu próprio `_baixar_foto` engolia o
motivo num `log.debug` que ninguém lê**. É a quarta vez neste projeto que a
ferramenta de diagnóstico esconde a evidência que ela existe pra mostrar
(`slice(0,20)`, `aria-label`, `slice(0,60)` antes do filtro, e agora este).
Causa diferente pede remédio diferente: "sem URL na fila" se resolve com a API
de afiliado; "URL que não baixa" não.

O conserto, em quatro camadas:
1. **`_baixar_foto` diz o porquê em WARNING** — `HTTP 404`, `veio vazia (0
   byte)`, ou a exceção, sempre com a URL.
2. ⚠️ **QUEM JÁ TEM FOTO NA FILA VEM PRIMEIRO** — o conserto de maior efeito e
   custo zero. Eu pegava os `quantos` PRIMEIROS que batiam o nicho e ia embora:
   numa fila de 153, isso é escolher 5 por ordem de arquivo. Os 5 primeiros
   estavam sem foto e havia 148 produtos ali atrás. Agora `_candidatos_do_nicho`
   junta TODOS e a escolha ordena por "tem imagem".
3. **Resgate sob demanda** via `preencher_fotos._foto` — reusada, não
   reimplementada: aquela função já sabe resolver o redirect até o `itemId`,
   usar o cache do health-check e tratar `shop_id` ausente. Três armadilhas já
   pagas; uma segunda implementação divergiria dela na primeira mudança da
   Shopee.
4. **Em vitrine, produto sem foto não entra.** Em `lista` e `comparacao` o
   slide É a foto — melhor um carrossel de 4 com foto do que de 5 com buraco. E
   se sobrar menos de 2, o brain **recusa e diz o comando**
   (`preencher_fotos.py`), em vez de montar um carrossel que o uploader
   recusaria de qualquer jeito (mínimo de 2 filhos).

#### 🎬 A CAPA DRAMÁTICA E A SEQUÊNCIA NARRATIVA (22/08, 3ª rodada)

O Dre mandou 10 capas de referência e a estrutura narrativa do ChatGPT. As
referências fazem quatro coisas que a minha capa limpa não fazia: **foto como
fundo do slide inteiro** (escurecida, não numa caixa), **CAIXA ALTA**, **parte
da frase em COR**, e o `1/8` numa pílula no rodapé.

**⚠️ A MARCAÇÃO DE DESTAQUE TEM QUE SER POR PALAVRA, NÃO POR TRECHO.** Primeira
tentativa: procurar o par de `*asteriscos*` depois de quebrar a linha. A quebra
partia a marca ao meio — `*ACABANDO COM` numa linha, `SUA BATERIA*` na outra —
e aí nenhuma das duas tem par: nada pintava e **os asteriscos saíam literais no
slide**. Agora `_marcacao()` devolve o texto limpo + o ÍNDICE das palavras
destacadas, e a quebra pode cair onde quiser. De quebra conserta a medição:
quem é quebrado é o texto sem os asteriscos que não seriam desenhados.

**⚠️ O VÉU É GRADIENTE, NÃO CHAPADO.** Chapado em 170 o produto sumia junto com
o texto e a foto virava uma mancha de cor. O texto mora no terço superior, então
é lá que o véu é forte; embaixo ele quase some e o produto aparece. É o que
separa "foto de fundo" de "fundo colorido". E o véu é o que dispensa contorno —
a regra do Dre é contorno só branco, que sobre texto branco não serve.

**⚠️ A CAPA DRAMÁTICA EXIGE FOTO.** Sem foto ela seria um retângulo preto com
texto, pior que a capa limpa. A escolha é pelo material que existe, não por
preferência: tem foto → dramática, não tem → limpa. `CARR_CAPA=limpa` desliga.

**Cor de destaque por nicho** (`tech` verde-limão · `casa` laranja · `beleza`
roxo · `pet` azul · `moda` rosa · `geral` ouro) — é o pedido de "identidade
visual de cada TopShop mantida": duas contas nossas lado a lado no explorar
têm que se distinguir sem ler o @.

**⚠️ FALTA A FONTE, E ISSO É COMPRA, NÃO CÓDIGO.** As referências usam
condensada pesada (Anton, Archivo Black); a Montserrat é larga. Largura de letra
é desenho, não configuração — não dá pra simular. `fonte_titulo()` já procura
`Anton-Regular.ttf`, `ArchivoBlack-Regular.ttf`, `Oswald-Bold.ttf` ou
`BebasNeue-Regular.ttf` em `assets/brand` e usa a primeira que achar; sem
nenhuma, cai na Montserrat e funciona. Baixar o `.ttf` é o que falta.

**A SEQUÊNCIA NARRATIVA** — a regra que o Dre chamou de ouro: *"cada slide deve
responder uma pergunta criada pelo slide anterior ou criar uma nova que o
próximo responde"*. Entraram dois slides no meio de todo formato:
- **QUEBRA (slide 2)** — ⚠️ NÃO ENTREGA A RESPOSTA. Ele aumenta a tensão ("e
  você provavelmente faz 2 deles todo dia"). É o slide que decide se a pessoa
  continua arrastando; sem ele o carrossel é capa + informação, que é
  apresentação de PowerPoint.
- **RESUMO (penúltimo)** — a lista do que foi dito, `_slide_resumo`, com a
  pílula "SALVA ISSO". ⚠️ **É o slide que ataca o nosso pior número**: 47.202
  impressões deram 48 salvamentos. Ninguém salva uma capa; salva-se a página que
  resume. Vem antes do CTA de propósito — depois dele ainda vem o pedido.
  A fonte encolhe pela QUANTIDADE de itens (54 → 46 → 40), porque 7 itens em
  corpo 54 estouram o slide e quem descobriria isso seria o leitor, não o log.
- O tamanho é variável (5 a 10 slides), como o Dre pediu — quem manda é quantos
  `passos` o formato tem, não um número fixo.

**Sobre o tom, decisão do Dre: MANTER.** *"apesar de soar meio anúncio, a gente
é afiliado... é mais um CTA e uma chantagenzinha do que anúncio — só não pode
parecer muitooo anúncio"*. Eu tinha marcado "Preço de outro mundo!" como
defeito; não é.

#### 🧱 O PASSO MANUAL QUE FALHOU DUAS VEZES VIROU COMANDO (22/08)

O `--teste` deu 404 pela terceira vez, e a causa estava no terminal do Dre: ele
colou o BLOCO DE COMANDOS inteiro, e a linha `# cola no /etc/caddy/Caddyfile`
virou **comentário do bash**. O `caddy validate` respondeu *"Valid
configuration"* logo em seguida — porque o arquivo ESTÁ válido: ele só não tem
a rota. Dois sinais verdes e o 404 continuou.

⚠️ **INSTRUÇÃO NO MEIO DE UMA SEQUÊNCIA DE COMANDOS NÃO É INSTRUÇÃO, É UM
COMANDO QUE NÃO RODA.** A lição não é "o Dre não colou": é que eu entreguei um
roteiro onde o único passo que exigia um humano estava disfarçado de comando.
Então virou comando: `midia_publica.py --instalar-caddy`.

Ele acha o bloco do host, insere a rota **como PRIMEIRA regra** (se entrasse
depois do `reverse_proxy` solto, o Caddy mandaria `/midia/...` pro Flask do
painel do TikTok e a Meta receberia um 404 de HTML — exatamente o sintoma que
a gente quer matar), faz backup com timestamp, valida, recarrega e **restaura o
original se a validação falhar**. É idempotente, tem `--conferir`, e se o
binário `caddy` não estiver no PATH ele diz que a edição foi feita mas NÃO
validada — um "deu certo" ali seria mentira.

#### ✍️ AS FONTES: OFL, e vêm direto pra VPS (22/08)

Pergunta do Dre: *"como vamos pegar as fontes? eu baixo pelo windows?"* Não.
`baixar_fontes.py` traz **Anton** e **Archivo Black** do repositório público do
Google direto pra `assets/brand`. Testado de verdade antes de escrever o script:
`raw.githubusercontent.com/google/fonts/main/ofl/...` responde 200 (o
`github.com/.../raw/...` não).

⚠️ **LICENÇA, porque a gente monetiza:** as duas são **SIL Open Font License
1.1** — uso comercial permitido, inclusive embutir em imagem publicada. A
obrigação prática é manter o aviso junto, então o script baixa o `OFL.txt` de
cada uma pra `assets/brand/licencas/`, em vez de pegar só o `.ttf`.

⚠️ **Piso de 20 KB no download.** Um 404 do GitHub chega como página HTML de
~400 bytes; gravar isso com nome `.ttf` deixaria a fonte "instalada" e quebrada,
e o Pillow só reclamaria na hora de renderizar, longe daqui. E depois de baixar
ele ABRE a fonte pra valer — fonte quebrada é pior que fonte ausente, porque a
ausente cai na Montserrat e o carrossel sai.

**O efeito é grande**: com a Anton a capa passou de "texto grande" a cartaz —
é a diferença entre a nossa capa e as referências, e ela estava toda na fonte.

**Sobre o template: o Dre confirmou que pode ser FIXO por conta.** Já é: cor de
destaque por nicho + logo por nicho + fundo por nicho. Nada varia por post.

#### 🔐 403 ≠ 404: A PASTA PÚBLICA NÃO PODE MORAR EM /root (22/08)

O `--instalar-caddy` funcionou — a rota entrou, validou, recarregou. E o
`--teste` mudou de **404 para 403**, que é progresso disfarçado de erro: 404
era "a rota não existe"; 403 é "a rota existe e o Caddy não pode LER a pasta".

Causa: o default era `~/jarvis/midia_publica`, e **`/root` é modo 700**. O Caddy
roda como usuário `caddy` e não atravessa. ⚠️ `chmod 755 /root` resolveria o 403
e abriria a casa inteira — **o `.env` com todos os tokens mora ali**. A solução
certa é a pasta sair de `/root`: `PASTA_PADRAO = /var/www/jarvis-midia`, que é
exatamente pra que `/var/www` existe.

**⚠️ 403 E 404 MANDAM PRA ARQUIVOS DIFERENTES.** 404 → Caddyfile (rota).
403 → permissão no caminho. A mensagem antiga dizia "rode --caddy" nos dois
casos, mandando procurar no lugar errado metade das vezes. Agora ela separa, e
no 403 `_pasta_alcancavel()` percorre o caminho e aponta **qual diretório** está
sem bit de entrada.

O instalador também ganhou o que faltava:
- **cria a pasta com 755 ANTES de mexer no Caddyfile** — rota certa apontando
  pra pasta ilegível é 403, e é melhor recusar antes de editar nada;
- ⚠️ **idempotente não é "não mexer"**: a 1ª instalação gravou
  `root * /root/jarvis/midia_publica`, e sair calado na 2ª deixaria a rota
  apontando pro caminho velho pra sempre — 403 sem explicação. Agora ele compara
  o `root` e **corrige** quando diverge.

#### 🐛 O SCRIPT BAIXOU AS FONTES E APAGOU (22/08) — bug meu

Saída na VPS: `⬇️ Anton-Regular.ttf ... ❌ No module named 'PIL'`. As duas fontes
**baixaram certinho e foram apagadas em seguida**. O Dre rodou com o python do
sistema; o Pillow mora no `.venv`.

⚠️ **EU TRATAVA "NÃO CONSEGUI VALIDAR" COMO "INVÁLIDO", E APAGAVA.** Ausência de
prova não é prova de defeito. `_valida()` agora tem TRÊS estados — `ok`,
`quebrada`, `nao_deu` — e só apaga em `quebrada`. Sem Pillow a fonte fica, com
um aviso de que não deu pra conferir.

Reproduzido em sandbox com um `python3` sem PIL antes do conserto e depois: as
fontes sobrevivem. (Mesmo assim, o comando certo é `.venv/bin/python`.)

#### ✅ O HOST PÚBLICO ESTÁ DE PÉ (22/08, 21h41)

    ✅ FUNCIONA — https://jarvis.topshopoficial.com.br/midia/.teste-…png
                  respondeu 200.
    ⬇️  Anton-Regular.ttf ... OK (166 KB)
    ⬇️  ArchivoBlack-Regular.ttf ... OK (88 KB)

**Carrossel deixou de ter bloqueio.** Foram quatro rodadas até aqui e vale
anotar o que cada uma custou, porque o padrão é o mesmo: **404** (rota nunca
colada — instrução disfarçada de comando) → **404 de novo** (bloco colado
inteiro, o comentário virou no-op do bash) → **403** (rota certa, `/root` em
modo 700) → **200**. Nenhuma das quatro foi um erro de código do carrossel; as
quatro foram infra, e três delas foram roteiro meu mal desenhado.

⚠️ **A LIÇÃO QUE FICA:** todo passo que exige um humano no meio de uma sequência
de comandos vira um passo que não acontece. Se dá pra virar comando, vira
comando — e o comando confere o resultado, em vez de confiar que deu certo.

Estado da infra do carrossel: `/var/www/jarvis-midia` (755) servida em
`/midia` pelo Caddy · Anton + Archivo Black em `assets/brand` · uploader
patchado com `postar_instagram_carrossel` · brain, render e ledger no lugar.

#### 🎠🎉 O PRIMEIRO CARROSSEL NO AR (22/08, 21h44)

    ✅ Carrossel publicado [@topshopcasa_]
       https://www.instagram.com/p/DcXOszEFCiw/
    💬 1º comentário postado (17972306502124303)

Formato `erros`, 5 slides, legenda de 235 caracteres, 1º comentário junto. O
ciclo inteiro — escolher formato → escrever texto → baixar foto → desenhar →
publicar → registrar — rodou sozinho num comando.

**⚠️ E ELE SAIU COM A VERSÃO ERRADA DO BRAIN.** Dois sintomas no log, e os dois
apontam pra mesma coisa: `capa limpa: nenhum slide trouxe foto` (com 39 produtos
com foto na fila) e — a prova — **nenhum slide de QUEBRA e nenhum de RESUMO**.
O `carrossel_brain.py` da VPS parou em `7bd4ae9`; a sequência narrativa e o
`capa.foto` entraram em `9c85624`. Os deploys seguintes trouxeram
`carrossel_render.py`, `midia_publica.py` e `baixar_fontes.py` — o brain, não.

⚠️ **A CULPA É DO MÉTODO, NÃO DO DEDO.** Eu vinha mandando
`git show FETCH_HEAD:<arquivo> > <arquivo>` para os arquivos daquela rodada, e
esse comando **sempre funciona** — inclusive quando falta um arquivo na lista.
Ele não tem como dizer "o brain está atrasado", porque nem olha pro brain. O
projeto TEM a ferramenta certa pra isso e eu não estava usando: o
`deploy_seguro.py` classifica cada arquivo em IGUAL / **ATRASADO** / DIVERGENTE
e aceita vários de uma vez. ATRASADO é exatamente este caso.

**Os arquivos do carrossel — a lista canônica, todos de RAIZ:**

    cd ~/jarvis && git fetch pjc claude/opa-clau-dgs591
    python3 deploy_seguro.py carrossel_brain.py carrossel_render.py \
                             midia_publica.py baixar_fontes.py

(`patch_carrossel_uploader.py` é à parte: `agents/meta_uploader.py` está
DIVERGENTE e se atualiza pelo patch, não pelo deploy.)

#### 💬 O 1º COMENTÁRIO ERA UMA FRASE SÓ, EM 6 CONTAS, TODO DIA (22/08)

Reclamação do Dre: *"o primeiro comentário em todos os posts, reels, carrossel,
é sempre o mesmo... todo mundo que acompanha enjoa de ver o mesmo comentário
robotizado toda vez. Pra carrossel isso nem faz sentido."* Ele está certo nas
duas, e a segunda é a séria:

1. `meta_uploader._TMPL_IG` era uma **constante**: *"🛒 O link tá na BIO, corre
   pegar o seu! 😍 / 💬 comenta EU QUERO..."* em toda postagem, das 6 contas.
   Quem segue duas das nossas contas via a mesma frase duas vezes por dia.
2. ⚠️ **O COMENTÁRIO NÃO SABIA O QUE ESTAVA COMENTANDO.** Num carrossel de
   *"3 erros que quase todo mundo comete"*, pedir "corre pegar o seu" é resposta
   pra uma pergunta que ninguém fez — não tem "o seu" ali, tem conteúdo.
   Comentário desconexo denuncia a automação mais do que o repetido cansa.

`comentarios.py` (novo): bancos por **formato** (reel · carrossel · lista) e por
**plataforma** (no FB o link é clicável e o pedido é clique; no IG não é, e o
pedido é salvar/comentar). ⚠️ **Rotação com memória**, não sorteio: com 8 frases
o sorteio puro repete a anterior 1 vez em 8 — umas 9 vezes por mês no nosso
volume, e é essa repetição que faz parecer robô. As últimas 4 por conta saem do
bolo primeiro. Frase que pede `{link}` sem link não é sorteada.

`patch_comentarios.py` (novo, cirúrgico como o do carrossel): troca só
`_montar_comentario` e acrescenta `_formato_do_pacote`. ⚠️ **O formato é
deduzido da PASTA** — pacote de carrossel tem `plano.json` ao lado dos slides, o
de vídeo não tem. Assim as duas chamadas que já existiam continuam idênticas, e
nada mais do arquivo DIVERGENTE é tocado. `ENGAJAR_IG_TMPL` no `.env` ainda
manda, pra controle manual.

#### 🎨 A CAPA vs. A REFERÊNCIA: o que faltava, item a item (22/08)

O Dre comparou as capas que ele fez no ChatGPT com o que saiu: *"tá muito ruim
clauzinho"*. Comparando lado a lado, o que a referência tinha e a nossa não:

| referência | nossa | resolvido |
|---|---|---|
| bloco de cor atrás da palavra | letra colorida | ✅ `[palavra]` |
| sombra dando profundidade | texto chapado | ✅ |
| `1/5` em pílula no TOPO | rodapé, sozinho | ✅ |
| "ARRASTA PRO LADO" em pílula | texto solto | ✅ |
| fonte condensada pesada | Montserrat | ⚠️ ver abaixo |
| foto de AMBIENTE | foto de produto | ❌ ver abaixo |

⚠️ **A TARJA É O QUE MAIS SEPARA AS DUAS.** Na referência, "NA CASA" não é texto
laranja — é texto PRETO sobre um bloco laranja. Letra colorida some no meio da
foto; bloco sólido não some, e é ele que o olho encontra primeiro no feed. Agora
são dois níveis: `*palavra*` = letra na cor do nicho, `[palavra]` = bloco.

⚠️ **A FONTE NÃO ENTROU NA VPS, E EU NÃO SEI POR QUÊ — então fiz como saber.**
Aqui, com a Anton em `assets/brand`, a capa sai condensada; lá saiu Montserrat
com a Anton instalada. Três hipóteses (arquivo, pasta, versão do módulo) e
nenhum jeito de separar. `carrossel_render.py --diag` imprime `BRAND_DIR`, cada
condensada procurada com o caminho completo, e **qual fonte o Pillow devolveu**.
Uma linha de log fecha o buraco que três hipóteses não fechavam.

⚠️ **E TEM UMA DIFERENÇA QUE NÃO É CÓDIGO: A MATÉRIA-PRIMA DA IMAGEM.** As capas
do ChatGPT usam foto de AMBIENTE gerada por IA — sala com sofá, setup com
profundidade. A nossa usa foto de PRODUTO da Shopee, fundo branco de catálogo.
Escurecida, foto de catálogo vira mancha; foto de ambiente vira capa. Isso não
se resolve com layout, e é onde o "conteúdo 100% autoral" que o Dre quer fazer
depois entra de verdade.

#### 🖼️ "NÃO TEM COMO FAZER ESSAS CAPAS?" — tem, e a peça era a IMAGEM (22/08)

Pergunta do Dre depois de ver o resultado ao lado da referência. A resposta é
sim, e o que faltava não era layout: **o ChatGPT não MONTA aquelas capas, ele
GERA a imagem**. A gente montava texto sobre foto de catálogo da Shopee.

⚠️ **MAS A IA GERA SÓ O FUNDO AQUI, NÃO A CAPA INTEIRA.** A IA erra texto —
em português, com acento, ela troca letra, deforma glifo e inventa palavra, e
quando erra não dá pra consertar, só regerar. A divisão que funciona:

    IA  → o ambiente   (onde ela é ótima e a gente não tem como fazer)
    PIL → o texto      (onde ela é ruim e a gente já é exato)

É o melhor dos dois e é reversível: fundo ruim se troca sem tocar no texto.

⚠️ **E O FUNDO É REUSADO, NÃO GERADO POR POST.** Um por carrossel seriam ~60
imagens/mês por conta. O fundo é CENÁRIO, não conteúdo: 6 por nicho rodam o mês
inteiro sem ninguém notar, porque o que o olho lê primeiro (hook, tarja,
produto) muda a cada post.

`fundo_ia.py` (novo) — Fal (`flux/schnell`), 1080×1350 na proporção certa,
cache em `assets/fundos/<nicho>/`. ⚠️ Todo prompt termina com
`no text, no words, no logos` (fundo com letra da IA briga com o hook e não tem
conserto) e `empty negative space on the upper left` (é onde o hook mora; se o
assunto da foto ficar embaixo dele, o véu não salva). ⚠️ **Para no primeiro
erro**: chave errada ou crédito no fim faz as outras 5 falharem igual, e
insistir gasta tempo e possivelmente dinheiro.

No render a ordem é **fundo à mão → fundo de IA → foto do produto**. ⚠️ O fundo
de IA vem ANTES da foto, e essa ordem é o ponto: o brain SEMPRE preenche
`capa.foto`, então deixá-la na frente faria o fundo gerado nunca ser usado. Sem
fundo gerado, cai na foto do produto — o que já funcionava — e nada quebra.

**Correção minha:** eu disse que a capa do @topshoptech_ tinha saído em
Montserrat. O `--diag` mostrou `fonte de título em uso:
/root/jarvis/assets/brand/Anton-Regular.ttf` — a Anton estava em uso, e eu
julguei pelo screenshot reduzido. O `--diag` continua valendo: ele é a resposta
pra uma pergunta que eu não tinha como responder de outro jeito.

#### 🤖 A CAPA INTEIRA POR IA — eu estava desatualizado de novo (22/08)

O Dre: *"vimos nas duas capas do chatgpt que ele montou a capa perfeitamente,
com o texto exato, isso só depende de prompt"*. **Ele está certo e eu estava
errado.** Escrevi no `fundo_ia.py` que "a IA erra texto em português" — isso
valia para modelos de um/dois anos atrás e vale para o `flux/schnell` que eu
mesmo escolhi, que é o modelo RÁPIDO E BARATO da família e o pior em
tipografia. Modelos feitos pra peça gráfica (Recraft V3, Ideogram, gpt-image)
escrevem certo. ⚠️ **É a segunda vez nesta semana que meu conhecimento sobre IA
generativa está atrás do que o Dre já viu funcionando** — a primeira foi vídeo
de produto. O padrão é claro o bastante pra virar regra: quando ele diz que uma
IA já faz algo, o default é acreditar e testar, não argumentar a partir do que
eu lembro.

`capa_ia.py` (novo) — capa inteira, texto incluso, default `fal-ai/recraft-v3`
(trocável por `CAPA_MODELO`). ⚠️ **O texto vai LITERAL e entre aspas**: modelo
de imagem renderiza o que lê como texto; *descrever* ("uma manchete sobre erros
de limpeza") faz ele INVENTAR a frase.

**O que o teste tem que medir — não é teimosia, é o que decide:**
1. ⚠️ **A LOGO.** Nas capas de referência, a "TS TOPSHOP CASA" é uma invenção
   parecida com a nossa, não a nossa. A IA não reproduz o arquivo da marca.
   Duas capas seguidas com logos ligeiramente diferentes é pior que capa
   simples com a logo certa.
2. **O PREÇO.** "R$ 29,90" virando "R$ 28,90" é problema comercial, não
   estético.
3. **O CUSTO.** Recraft/Ideogram custam ~10-60× o schnell por imagem. Só a capa
   (1 por post) é sustentável; 9 slides por post, não.
4. **CORRIGIR.** Texto errado na IA só se conserta regerando a imagem inteira.

Por isso o módulo **não substitui** o híbrido — fica ao lado. `--comparar`
gera as duas versões do MESMO hook. **Quem decide é o Dre olhando, não eu
argumentando** — foi exatamente assim que o vídeo de IA e o Shopee Vídeos
foram resolvidos.

**Bloqueio na VPS:** `fal_client` não estava instalado. `.venv/bin/pip install
fal-client`.

#### 🚨 SALDO DA FAL ESGOTADO — e isso NÃO é sobre a capa (22/08, 23h10)

    fal-ai/recraft-v3 recusou: User is locked.
    Reason: Exhausted balance.

O teste da capa por IA nem chegou a rodar. Mas o achado é muito maior que o
teste: ⚠️ **É A MESMA CONTA DA FAL QUE GERA OS VÍDEOS** (`fal_provider.py`,
Kling). Se ela está travada, a **esteira de Reels parou junto** — e ninguém foi
avisado. É o tipo de coisa que só aparece dois dias depois, quando a fila
esvazia e as 6 contas ficam sem post. **Conferir a fila é a prioridade de hoje**,
não o carrossel.

`_traduzir_fal()`: saldo esgotado deixou de ser "Fal recusou: <texto>" e virou
uma mensagem que diz **o que isso significa pro resto do sistema**. Erro de
infra genérico esconde consequência; este agora aponta pra fila de vídeo.

#### 🆓 FUNDO DE GRAÇA: o Pexels resolve, e melhor (22/08)

Com a Fal travada, a pergunta certa não é "como recarregar" — é **por que a
gente estava gastando crédito de geração pra ter uma sala de estar**. Fundo é
CENÁRIO: sofá, bancada, mesa. Isso existe aos milhares em banco de foto, de
graça e com uso comercial liberado, e o crédito da Fal é o que faz VÍDEO — que
é a coisa que a gente não tem como conseguir de outro jeito.

`fundo_ia.py --pexels <nicho>` — ⚠️ **reusa `asset_autopilot_agent.buscar_pexels`**,
que já existe no projeto com orientação retrato, tratamento de erro e a licença
documentada. Reimplementar seria criar uma segunda versão pra divergir depois.
4 buscas por nicho, dedup por URL, piso de 20 KB.

**Custo zero e disponível agora** — não depende de recarga nenhuma.

#### 🖥️ A CAPA VAI PELO NAVEGADOR (22/08) — e duas correções minhas

**Correção 1 — inventei uma consequência.** Escrevi que o saldo esgotado da Fal
tinha parado a esteira de Reels. O Dre: *"a gente não usa o Fal a não sei
quantos meses"*. Eu vi `fal_provider.py` no repo, vi "Exhausted balance" e
DEDUZI o resto — sem abrir um log, sem olhar a fila. É exatamente o erro que
este ROADMAP documenta em quatro lugares diferentes: **deduzir de artefato em
vez de medir**. O saldo zerado da Fal não significa nada aqui.

**Correção 2 — ofereci um retrocesso.** Com a Fal travada, propus fundo do
Pexels. *"como assim usar o pexels? pelo amor de deus"* — e ele tem razão: é
foto genérica de banco, que mil contas usam. Duas respostas erradas pra mesma
pergunta ("por que a nossa capa é pior que a do ChatGPT?"), porque eu insistia
que a diferença era a FOTO.

**A diferença é TIPOGRAFIA E ACABAMENTO, e o PIL não faz isso:**
`letter-spacing` negativo (o aperto das manchetes), sombra em DUAS camadas (uma
dura que recorta a letra do fundo, uma difusa que dá profundidade), tarja
INCLINADA com folga em volta da palavra, vinheta, brilho de cor no canto. No
Pillow cada um desses é um algoritmo à mão. Em CSS é uma linha.

⚠️ **E O CHROMIUM JÁ ESTÁ NA VPS.** `ig_playwright`, `whatsapp_playwright`,
`coletor_assets` e outros já rodam Playwright ali. Isto não acrescenta
dependência: acrescenta um uso novo pra uma que já é paga. E **não é IA** — é
determinístico, custa zero, roda offline, e a marca sai EXATA (logo, @handle,
preço), que imagem gerada não garante.

`capa_html.py` (novo) — monta HTML/CSS e fotografa com o Chromium headless.
Três coisas que custaram tentativa:
- ⚠️ **`z-index:-1` na tarja só funciona com `z-index:1` no `.hook`.** Sem o
  contexto de empilhamento, o bloco de cor vai parar ATRÁS do véu e some
  inteiro — sobrando texto preto ilegível no escuro.
- ⚠️ **O bloco EXTRAVASA a caixa da letra.** Justo, ele fica do tamanho do
  texto e some atrás das próprias letras: laranja aparecendo só nas frestas.
- ⚠️ **Posição é trabalho do CSS, não de JS.** Eu tinha o subtítulo em
  `position:absolute` com o `top` calculado do `offsetHeight` do hook, e ele
  pousava **250px abaixo do lugar** (o `inline-block` da tarja inflava a
  altura da linha). Hook e sub agora vivem no mesmo bloco em fluxo, separados
  por `margin-top` — não há conta pra errar. O JS ficou só com o que o Python
  não sabe fazer sem chutar: **medir** se o texto cabe.
- ⚠️ `_chromium()`: o Playwright procura o navegador pela versão DELE, e quando
  lib e binários não batem o erro é `Executable doesn't exist at
  .../chromium_headless_shell-1` — com o `-1194` na mesma pasta. Não é
  navegador faltando, é número que não bate. 6 linhas evitam um
  `playwright install` de 150 MB.

**No `carrossel_render` a capa vai pelo navegador quando dá e pelo PIL quando
não dá.** Sem Chromium, sem Playwright, ou qualquer erro: a capa continua
saindo. Nenhum post depende do navegador estar bem.

#### 🎨 O SISTEMA DE DESIGN (22/08) — a resposta era design, não ferramenta

O Dre pôs um carrossel do **Claude Design** ao lado do meu: *"olha simplesmente
o claude design fazendo os slides, e você aí no código, na mão, e qual você
preferiu?"* O dele, sem discussão. E o motivo não é gosto:

    o meu   → uma CAPA bonita, e slides internos que não conversavam com ela
    o dele  → um SISTEMA: paleta, escala tipográfica, formas de fundo e
              hierarquia que se repetem slide a slide

⚠️ **CARROSSEL NÃO SE JULGA POR SLIDE, SE JULGA POR SEQUÊNCIA.** Sete peças que
parecem sete posts diferentes é o que faz um carrossel parecer amador — e era
exatamente o que saía daqui. Eu estava otimizando a capa e deixando os slides
internos como planilha.

⚠️⚠️ **E A TECNOLOGIA JÁ ERA A CERTA.** Aquele design é HTML/CSS — o mesmo motor
que eu tinha acabado de pôr na VPS. O que faltava não era ferramenta, era
DECISÃO DE DESIGN. Isso responde as três perguntas de uma vez: **Hugging Face,
ChatGPT e Fal não resolveriam**, porque nenhum deles é o problema. E um modelo
de imagem faria a peça bonita com a marca infiel — aqui a logo, o @, o preço e
a cor da conta saem exatos, de graça, em 2 segundos, sem fila e sem crédito.

`slides_html.py` (novo) — o sistema inteiro:
- **Paleta por conta é um TRIO, não uma cor**: `acento` (fecho e círculos),
  `creme` (fundo dos slides) e `sombra` (a mancha). Uma cor só não faz sistema,
  faz destaque. A família é a MESMA nas 6 contas — mesma tipografia, mesmas
  formas, mesma hierarquia — e só o trio muda: cada grid tem identidade e as
  seis continuam sendo visivelmente a mesma marca.
- **Fraunces + Poppins**, as duas OFL. ⚠️ Fraunces é VARIÁVEL: peso e `SOFT`
  (arredondamento da serifa) vêm do CSS, não do arquivo — é o que dá o desenho
  macio das referências sem comprar fonte.
- ⚠️ **A mancha é o que costura a sequência.** Sem ela cada slide é um
  retângulo de cor com texto. Ela sangra pra fora do quadro de propósito:
  forma cortada pela borda dá movimento, forma inteira e centrada dá apostila.
- ⚠️ **`ELEMENTO POSICIONADO PINTA DEPOIS DO ESTÁTICO`**, mesmo vindo antes no
  HTML — e por isso a mancha cobria o texto. No 1º teste a palavra "que" de
  *"Guardar tudo o que sobrou"* **simplesmente sumiu atrás do círculo**, e o
  título ficou agramatical sem nenhum erro aparecer em lugar nenhum. É o pior
  tipo de defeito: o post sai, publica, e só um humano lendo percebe.

**No `carrossel_render` o sistema HTML vem primeiro e o PIL ficou como rede** —
sem Chromium, sem Playwright, sem as fontes, ou qualquer erro, o post sai do
mesmo jeito. O desenho em PIL continua inteiro; ele só deixou de ser o padrão.

#### 🎬 O FECHO: CINCO MODELOS EM RODÍZIO (22/08)

O Dre: *"o CTA no final do slide tá muito simples... da pra diferenciar todo
dia o CTA"*, e mandou 5 carrosséis reais. Lendo os cinco, o padrão não é "um
CTA bonito" — é que **cada um pede UMA coisa, de um jeito**, e o jeito muda:

| referência | o pedido | o jeito |
|---|---|---|
| thaleslaray | comentar | palavra-chave em cor, dentro de caixa com borda |
| detalhesdaminhacasa | comentar | "Comenta AULA aqui embaixo ↓" |
| bettydiarista | **seguir** | **mockup do card de perfil** com o botão azul |
| carlamarquete | seguir | texto gigante, sem enfeite |
| mariffernandesdaily | seguir | "se você gosta de X, achou o perfil certo" |

Os cinco viraram modelos, em **rodízio com memória** (`shared/fechos_recentes
.json`) — mesmo remédio do 1º comentário: com 5 peças, sorteio puro repete a
anterior 1 vez em 5, e fecho repetido é o que faz quem segue duas contas
nossas ver a mesma peça duas vezes por dia. `CARR_FECHO=perfil` força um.

⚠️ **O MOCKUP DE PERFIL NÃO ESTAMPA NÚMERO DE SEGUIDORES.** O do bettydiarista
mostra "100k". Se a gente imprimir um número, ou é o real — que hoje é **9** em
duas contas, e aí a peça trabalha contra a gente — ou é mentira impressa na
arte. O card mostra avatar, @ e o botão azul, que é o que faz o pedido.

⚠️ **CADA MODELO ESCREVE O PRÓPRIO TÍTULO.** Deixando o `cta.titulo` do plano
mandar em todos, o fecho de PERFIL saiu com o botão **"Seguir"** e a frase
**"Salva pra não perder"** logo abaixo — a peça pedindo uma coisa e o texto
pedindo outra. Título e pedido são a mesma decisão, então moram juntos; só o
modelo `salva` usa o texto do plano.

**A palavra-chave do comentário sai do FORMATO** (`erros` → "EU FAÇO", `lista`
→ "QUERO", `comparacao` → "QUAL"), ou de `cta.palavra` no plano. Pedir "comenta
QUERO" num carrossel de erros é o mesmo desencontro que o 1º comentário tinha.

#### 🖼️ FOTO NOS SLIDES — mas não em todos, e o motivo está nas referências

O Dre: *"o ideal é que cada slide tenha um fundo chamativo, e não fique só com
cores, mas literalmente imagens"*. Certo — e o Claude Design confirmou o
limite dele mesmo: *"não consigo gerar imagens — cada slide tem um espaço de
fundo com a descrição da foto ideal"*.

⚠️ **MAS OLHANDO AS REFERÊNCIAS COM ATENÇÃO, ELAS NÃO PÕEM FOTO EM TODO SLIDE**
— e o motivo aparece nelas mesmas:

    CAPA e FECHO  → foto cheia, escurecida. É onde tem 5 palavras.
    CONTEÚDO      → foto SÓ NO TOPO, com fade pro creme. É onde tem um
                    PARÁGRAFO, e parágrafo sobre foto se lê mal.

A foto entra onde ajuda o olho a **parar** e sai de onde atrapalha o olho a
**ler**. "Foto em tudo" deixaria o carrossel bonito na miniatura e ilegível no
celular — que é onde ele é lido.

- **Capa**: `.fotocheia` + gradiente escuro. A mancha de cor cai de .13 pra .07
  quando há foto, senão as duas competem.
- **Conteúdo**: `.fototopo` de 620px + fade que morre no creme aos 76%.
- **Fecho**: ⚠️ **`mix-blend-mode:multiply` NA COR DA CONTA**, não véu preto —
  véu apaga a foto e sobra cinza; o multiply TINGE a foto na cor da marca e ela
  continua se lendo como foto.
- ⚠️ **A fonte da imagem é plugável de propósito**: qualquer JPG em
  `assets/fundos/<nicho>/` entra no rodízio. Foto sua, print, imagem gerada,
  banco de imagem — o módulo não sabe de onde veio. A decisão de ONDE arrumar
  foto é do Dre e mudou duas vezes hoje; ela não podia ficar soldada no código
  do desenho.

⚠️ **BUG QUE EU MESMO PLANTEI DUAS HORAS ANTES.** A regra
`.slide > *:not(.mancha) { position:relative }` — que eu tinha criado pra
resolver a mancha cobrindo o texto — sobrescrevia o `position:absolute` das
camadas de foto. O estrago era invisível de duas formas ao mesmo tempo: a
`fotocheia` da capa perdia o `inset:0`, virava um div de altura zero e **a foto
simplesmente não aparecia**; a `fototopo` do conteúdo caía no fluxo e passava a
respeitar o padding, ganhando **margem branca dos lados**. Nenhum dos dois dá
erro — os dois só saem errados. Um seletor que exclui por classe resolve, mas a
lição é outra: **conserto que muda regra global cria o próximo defeito em outro
lugar**, e o outro lugar não avisa.

#### ✍️ DOIS TETOS DE TEXTO, NÃO UM (23/08)

O layout novo comporta um parágrafo e o brain continuava escrevendo pra 12
palavras por slide — o carrossel real ia sair com o design bom e o conteúdo
raquítico, com um vão embaixo de cada slide.

⚠️ **O TETO ÚNICO ERA HERANÇA DO PIL.** Lá tudo era título: frase grande sobre
fundo liso, e 12 palavras já viravam parágrafo. O sistema em HTML tem
HIERARQUIA — manchete display em cima, corpo em cinza embaixo. Papéis
diferentes com teto igual empobrece os dois: título de 12 palavras é longo pra
manchete, corpo de 12 é curto pra valer um salvamento. **E o salvamento é o
número que a gente está tentando mover** (48 em 47.202).

    PALAVRAS_TITULO = 9      manchete
    PALAVRAS_CORPO  = 38     2-3 frases inteiras — é aqui que mora o valor

⚠️ **E ELES NÃO DISPUTAM MAIS O MESMO ORÇAMENTO.** Antes o corpo comia o que
sobrasse do título, porque no PIL os dois pousavam na mesma faixa da imagem. No
HTML moram em blocos diferentes: o corpo caber não depende do título ser curto.
O corte do corpo agora é **na última frase completa** — parágrafo cortado no
meio de uma oração parece defeito de carregamento, e é a mesma lição da linha
de apoio de ontem.

**`conclusao` (a etiqueta verde do rodapé)**: o layout sempre teve o lugar e o
brain nunca preenchia — saía um slide com um vão embaixo. Agora o prompt pede,
com teto de 5 palavras.

#### ⏰ O SLOT DO CARROSSEL: 15:30 e 20:30 (23/08)

Pergunta do Dre: *"quais são os horários de cada reels? podemos postar um
carrossel de tarde e um de noite"*.

⚠️ **OS HORÁRIOS DO REEL NÃO SÃO FIXOS** — eles mudam com o volume do dia
(`horarios_por_volume` cruzado com a pirâmide `posts_por_dia_semana`):

| dia | Reels | horários |
|---|---|---|
| seg / qui | 3 | 09:00 · 13:00 · 18:30 |
| ter / sex | 2 | 09:00 · 18:00 |
| qua / sáb | 1 | 09:00 |
| domingo | 0 | — |

Por isso o default é **15:30 e 20:30**: são os dois buracos que sobram em TODOS
os dias, não só nos de volume baixo. ⚠️ Um horário "de tarde" às 17h pareceria
livre olhando quarta-feira e **colidiria com o Reel das 18:30 em metade da
semana** — e dois posts nossos na mesma janela disputam a mesma entrega, que é
exatamente o que a pirâmide existe pra evitar.

`carrossel_agendador.py --agenda` imprime a semana com Reel e carrossel lado a
lado e **avisa se houver colisão** — a conta que eu acabei de fazer à mão fica
disponível pra quando os horários mudarem.

`carrossel_agendador.py` (novo) — ⚠️ **MÓDULO SEPARADO, DE PROPÓSITO.** O
`daemon_maestro` posta em 6 contas, todo dia, há meses. Enfiar 80 linhas novas
nele por um formato que nasceu ontem é apostar o que funciona no que ainda não.
O patch no daemon são **3 linhas dentro de um try/except**: se o carrossel
explodir, os Reels continuam saindo.

⚠️ **E NASCE DESLIGADO** (`carrossel_ligado: false`). Um formato novo que começa
publicando sozinho em 6 contas é um jeito rápido de descobrir um defeito em
público.

Config: `carrossel_horarios` · `carrosseis_por_dia_semana` ([2,1,1,2,1,1,0],
espelhando a pirâmide mais baixa) · `carrossel_contas` · `carrossel_ligado` ·
`carrossel_intervalo_seg` (90s entre contas — seis contas publicando no mesmo
minuto todo dia é padrão mais evidente que o horário cravado).

#### 📸 QUANTAS FOTOS DE FUNDO? A CONTA (23/08)

Pergunta do Dre: *"quantas fotos serão necessárias gerar no chatgpt? ou teremos
que fazer por dia pra cada carrossel e slide?"*

**Nem por dia nem por slide. Por NICHO, e reusadas.** O fundo é CENÁRIO —
sofá, bancada, armário. Ele não descreve o post; o que descreve é o texto, o
produto e a cor. Duas semanas depois ninguém lembra que a sala já apareceu.

Onde a foto entra hoje: **capa (1) + fecho (1)** por carrossel, ambas sorteadas
do acervo do nicho. Os slides de conteúdo só usam foto se o item trouxer
`fundo` — o brain não preenche, então são 2 usos por post.

Volume: a pirâmide do carrossel é `[2,1,1,2,1,1,0]` = **8 carrosséis por semana
por conta**.

⚠️ **E O RODÍZIO COM MEMÓRIA CORTA O NÚMERO PELA METADE.** Com sorteio puro e N
fundos, a chance de repetir o anterior é 1/N — com 6 fundos e 8 posts/semana, a
mesma foto sairia repetida ~1,3 vezes por semana na MESMA conta. Guardando os
últimos 3, **6 fundos rendem o que 12 renderiam no sorteio**. Mesma mecânica do
rodízio dos fechos e do 1º comentário; aqui ela vale dinheiro, não só estética.

**A conta final: 6 a 8 fundos por nicho, uma vez.** 6 nichos × 7 ≈ **42
imagens**, e depois 2-3 por nicho por mês só pra renovar. Não é trabalho diário.

⚠️ **A memória lembra no máximo METADE do acervo** (`min(3, N//2)`): guardar
demais esvazia a lista de candidatos e o rodízio degenera em ordem fixa, que é
o defeito oposto ao que ele conserta.

#### 🐍 O PYTHON ERRADO, PELA TERCEIRA VEZ (23/08)

    ⚠️ Gemini indisponível (No module named 'google') — usando reserva
    ❌ casa: não renderizei (No module named 'PIL')

Eu mandei `python3 carrossel_agendador.py` em vez de `.venv/bin/python`. ⚠️ **É
a terceira vez que esse comando meu quebra na VPS** (baixar_fontes, fundo_ia,
agora aqui), e o erro sempre aparece TARDE — depois de escolher formato, ler a
fila de 164 produtos e baixar as fotos. Trabalho jogado fora, e a mensagem não
diz a causa: não é biblioteca faltando, é o interpretador errado.

`_confere_python()` recusa na primeira linha e **imprime o comando certo, com
os argumentos que a pessoa acabou de digitar**. Erro de ambiente tem que falhar
antes do trabalho, não depois.

#### ⚠️ FALSO ALARME MEU: O DOMINGO SEMPRE ESTEVE CERTO (23/08)

Eu disse ao Dre que *"domingo tem 4 Reels e zero carrossel"* e sugeri olhar
depois. Ele: **"domingo não há posts, cuidado em!!"**. Ele está certo, e o
daemon também: `_slots_de_hoje` tem `if n <= 0: return []  # dia de descanso`
desde sempre.

⚠️ **QUEM INVENTOU O DOMINGO CHEIO FOI O MEU RELATÓRIO.** No `--agenda` eu
escrevi `reels_vol.get(str(n)) or (cfg.get("horarios") or [])` — no domingo
`n=0`, `get("0")` devolve None, o `or` caiu na lista genérica e a tabela
imprimiu `09:00, 14:00, 17:00, 21:00`. **Ferramenta de diagnóstico que mente é
pior que ferramenta nenhuma**: eu quase mandei consertar o que não estava
quebrado, num arquivo que posta em 6 contas há meses. Um `if n <= 0` ANTES do
`or` resolve — e a lição é a de sempre neste projeto: conferir o relatório
contra o código antes de tratar o relatório como fato.

#### 🖼️ FUNDO EM TODOS OS SLIDES (23/08)

*"posso criar quantas imagens eu quiser, então aproveita"* — então o fundo
deixou de ser só da capa. Agora **cada slide do carrossel recebe um fundo
diferente**, e o "diferente" é dentro DAQUELE post: não adianta o acervo ter 8
fotos se as 7 páginas sortearem a mesma sala. A lista é embaralhada e consumida
em ordem; quando acaba, reinicia (3 fundos e 7 slides = cada um aparece 2-3
vezes, nunca em sequência).

⚠️ **O SLIDE DE PRODUTO FICA DE FORA.** Ali a foto É o produto, e um cenário
atrás dele brigaria com a única coisa que a pessoa precisa ver pra querer
comprar.

Onde cada uma aparece: capa e fecho com foto **cheia** (escurecida / tingida na
cor da conta), slides de texto com foto **só no topo**, com fade pro creme.

**Com fundo em todo slide, o acervo ideal sobe de 6-8 para 10-12 por nicho** —
ainda uma vez só, e ainda ~2-3 de reposição por mês.

#### 🎨 "10 FUNDOS OU 10 SLIDES?" — fundos avulsos (23/08)

⚠️ **O CHATGPT FAZ SÓ A FOTO, NUNCA O SLIDE.** As capas que o Dre mandou eram
slides prontos, então a confusão é justa — mas no nosso sistema o papel é
outro: a IA entrega o AMBIENTE, e o texto, a logo, o `@` e a cor da conta
entram por cima no render. É isso que garante que o `R$ 29,90` está certo e que
o `@topshopcasa_` não vira `@topshopcaza_`. Slide pronto de IA seria bonito e
infiel.

⚠️ **E EU TINHA DADO UM CONSELHO IMPOSSÍVEL:** mandei gerar 10 fundos por nicho
quando o `--prompt` só tinha **3 cenários**. Pedir 10 daria 3 cenas repetidas
— exatamente o problema que o acervo grande existe pra evitar. Agora são **10
cenas por nicho**, todas de ambiente (sala, bancada, entrada, varanda...):
nenhuma é foto de produto, porque foto de produto a gente já tem da Shopee e
ela vive no slide de produto. O que falta é o LUGAR onde o produto viveria.

`--prompt <nicho> --quantos 10` imprime os 10 numerados, com o tamanho
(1080×1350), a pasta de destino e o aviso de que são fundos e não slides.

#### 📥 `--importar` — o bug calado que estava esperando as 10 imagens (23/08)

O Dre gerou os 10 fundos de `casa` no ChatGPT 5.6 e ia salvar na pasta. **Não
teria funcionado, e ninguém saberia:** o `existentes()` fazia `glob("*.jpg")` e
o ChatGPT baixa **`.png`**. O acervo teria 10 arquivos, o `existentes()`
devolveria lista vazia, o `_fundo()` do `slides_html.py` devolveria `""` e o
carrossel sairia liso — **sem erro, sem log, sem nada**. O glob era `.jpg`
porque quem alimentava o acervo era o `--gerar` do Fal, que salvava `.jpg`;
mudou quem alimenta, e a suposição ficou.

⚠️ **A categoria: bug que não reclama.** É o mesmo formato do domingo (`--agenda`
mentindo) e do `baixar_fontes` (apagando fonte boa). Todos passam no teste de
"rodou sem erro". O que os pega é conferir o RESULTADO, não o código de saída.

Duas defesas, porque uma só não cobre:
1. `existentes()` agora aceita **jpg/jpeg/png/webp** — largar o arquivo na pasta
   na mão funciona.
2. `--importar <nicho> --de <pasta|arquivos>` normaliza pra JPEG.

`--importar` faz três coisas que parecem frescura e não são:
- **Converte pra JPEG q88.** O `slides_html.py` embute o fundo como `data:` URI
  dentro do HTML e base64 engorda 33%: 7 slides × PNG de 3 MB = **~28 MB de
  HTML** por carrossel pro Chromium mastigar. Em JPEG dá ~250 KB cada. O olho
  não vê — a foto ainda leva `brightness(.6)` por cima.
- **Reduz, nunca amplia. E nunca corta.** A régua do prompt é "espaço vazio em
  cima à esquerda"; cortar aqui pra 4:5 mataria justo a margem onde o título
  pousa. Quem corta é o CSS, pelo centro, na hora.
- **Duplicata por conteúdo (sha1), não por nome.** Baixar a mesma imagem duas
  vezes dá `Cena (1).png` e `Cena (2).png`: nomes diferentes, bytes iguais. Sem
  isso o rodízio acha que tem 10 fundos quando tem 7 e mostra os clonados com o
  dobro da frequência — que é justo o que o rodízio existe pra evitar.

⚠️ **E O TESTE PEGOU UM FURO NO MEU PRÓPRIO CONSERTO.** O `--listar` sugere
`--importar casa --de assets/fundos/casa/` pra normalizar no lugar. Nesse caso
o PNG cru vira `.jpg` novo **e o PNG continua lá** — a mesma foto duas vezes no
acervo, exatamente o defeito que o sha1 existia pra impedir. Só apareceu porque
rodei e **olhei o `ls`**. Agora, quando a origem é a própria pasta de destino, o
original é substituído (ou removido, se já houver o gêmeo).

    .venv/bin/python fundo_ia.py --importar casa --de ~/fundos-chatgpt/
    .venv/bin/python fundo_ia.py --listar        # avisa se sobrou PNG cru

#### 👁️ `midia_publica.py --ver` — revisar sem publicar (23/08)

⚠️ **ERA UM DEFEITO DE PROCESSO, E EU TINHA ESCRITO UMA INSTRUÇÃO IMPOSSÍVEL.**
O "Ainda falta" dizia *"ligar depois de olhar alguns prontos"*. Só que o
`--agora` monta os slides em `pronto_carrossel/` na VPS e imprime o CAMINHO —
e quem aprova visual está no navegador, num computador que não vê aquele disco.
Na prática o Dre só via o carrossel **depois de publicado no Instagram**: a
revisão só existia quando já era tarde. Mesma família do `--prompt` mandando
gerar 10 fundos quando só havia 3 cenas — conselho que não tem como cumprir.

    .venv/bin/python midia_publica.py --ver          # o mais recente
    .venv/bin/python midia_publica.py --ver <pasta>  # um específico

Devolve **uma URL** com os slides em ordem, numerados, mais a `legenda.txt` no
topo — abre no celular. Reusa o `publicar()`, então **não abre porta nova**: só
escreve arquivo na pasta estática que o Caddy já serve, não recebe upload nem
executa nada, e some sozinho no `limpar()` das 6 horas junto com os slides.

Dois detalhes que só apareceram porque tirei print da página e olhei:
- o contador fica à **direita**. No canto superior esquerdo mora a tag do nicho
  — e é o espaço vazio que o prompt do fundo reserva. Contador de revisão
  cobrindo justo o que se quer revisar não serve pra nada.
- a legenda passa por escape de HTML. Ela vem do Gemini e é texto livre; um
  `<` solto quebraria a página inteira em silêncio.

#### 🧩 BIBLIOTECA DE COMPOSIÇÕES — "identidade consistente + composição variável" (23/08)

⚠️ **O DRE NOMEOU O DEFEITO MELHOR DO QUE EU TINHA DIAGNOSTICADO.** Eu achava
que o problema era falta de foto. Não era. Ele escreveu:

> os slides não podem parecer variações do mesmo template. Eles precisam manter
> a identidade da conta, mas mudar composição, hierarquia e tipo de visual (...)
> O erro seria fazer 6 slides assim: título à esquerda + foto à direita, título
> à esquerda + foto à direita, título à esquerda + foto à direita... Isso fica
> bonito, mas visualmente cansa rápido.

E era **literalmente** o que o `_html_conteudo` fazia: UMA composição (tag, h1,
miolo, rodapé) com três variações de MIOLO. Trocar foto por lista não muda a
composição — muda o recheio. **O olho lê a estrutura, não o recheio.**

**Seis composições**, cada uma com um tom (claro/escuro) e uma exigência de
conteúdo:

| composição | tom | serve quando | o que faz |
|---|---|---|---|
| `cheia` | escuro | tem foto | foto sangrando, ~80% imagem, texto mínimo |
| `numero` | **ambos** | sempre | número gigante como forma, sangrando pela direita |
| `respiro` | escuro | título ≤ 7 palavras | punchline em cor chapada, sem foto |
| `produto` | claro | tem foto de produto | objeto isolado + preço |
| `meio` | claro | sempre | foto na metade de cima, texto embaixo (a antiga) |
| `checklist` | claro | tem lista | blocos com ✓ — o slide feito pra SALVAR |

**A regra vale mais que as composições: nunca a mesma duas vezes seguidas, e,
quando dá, o tom oposto.** Com 6 opções e sorteio puro, repetição colada sairia
em 1/6 dos pares — e repetição colada é justo o que se vê. Mesma mecânica do
rodízio dos fundos, dos fechos e do 1º comentário: **memória do anterior vale
mais que quantidade de opções.**

⚠️ **A ALTERNÂNCIA DE TOM É PREFERÊNCIA, NÃO LEI — e a 1ª versão errou isso.**
Filtrando pelo tom oposto de forma dura, como só a `meio` era clara entre as de
texto, TODO slide depois de um escuro virava `meio`. Saía um padrão e entrava
outro (escuro→meio→escuro→meio), só que mais lento. Duas correções: a `numero`
serve nos dois tons, e o filtro só manda quando sobram ≥2 opções.

⚠️ **`.recorte` — o conserto do "parece que pegou da Shopee".** A foto de
catálogo vem em fundo BRANCO; num card creme o branco vaza e denuncia. Com
`mix-blend-mode:multiply` sobre superfície clara o branco vira a própria
superfície e só o produto sobra. Sem remover fundo, sem API, sem pagar nada. É
por isso que a `produto` é obrigatoriamente CLARA — em fundo escuro o multiply
comeria o produto junto.

⚠️ **Cabeçalho fixo em TODOS os slides** (logo + `TopShop` + `@handle` + `n/6`).
É isso que faz um carrossel parecer de uma marca; nas referências do Dre ele é
idêntico nos 6. O nosso tinha logo só na capa, e de 60px.

#### 🩹 Quatro defeitos invisíveis que este trabalho revelou (23/08)

Todos passam em `py_compile`, nenhum levanta erro, **os quatro só aparecem
olhando o JPEG**. Vale como lista de conferência, não como anedota:

1. **A logo escura sobre fundo escuro.** Quadrado preto ilegível. Consertado com
   `_logo_claro()`, que MEDE o brilho médio da logo e escolhe o fundo do círculo
   — troca um palpite por um fato, e o palpite estaria errado em metade das
   contas.
2. **O "Shop" laranja sobre o slide laranja.** No `respiro` o fundo *é* a cor de
   acento: a marca virava "Top". Contraste zero não é erro de código.
3. **O `.gigante` fora da lista de exceções do `z-index`.** Ele nasceu
   `absolute`, a regra global o converteu em `relative`, ele caiu no fluxo e o
   número foi parar em cima do cabeçalho. **O arquivo já tinha um comentário
   avisando exatamente isso** — e mesmo assim aconteceu, porque lista de
   exceções é o tipo de coisa que ninguém lembra de atualizar ao criar
   elemento novo. **Toda camada `absolute` filha direta de `.slide` PRECISA
   entrar naquela lista.**
4. **`fundo: true` onde se espera caminho.** `Path(True)` levanta TypeError na
   montagem do HTML — que ficava FORA de qualquer `try`. A exceção subia, o
   `carrossel_render` caía no PIL, e **o post saía feio, saía publicado, e o log
   não mencionava erro nenhum.** Agora a montagem tem `try` com o motivo no log,
   e o `_fundo()` valida `isinstance(cand, str)`.

E o exemplo do `--exemplo` passou a marcar `fundo: True` nos slides de texto,
porque é assim que o brain manda: **um exemplo que não passa por todos os
caminhos é um teste que aprova o que não testou** (era o caso — a `cheia` nunca
era exercitada).

#### 🔬 O 1º CARROSSEL COM FOTO DE VERDADE — o que quebrou (23/08, noite)

10 fundos do ChatGPT importados, carrossel produzido, revisado pelo Dre e pelo
ChatGPT. **Cinco defeitos reais e três críticas que eram culpa da minha
ferramenta de revisão.** A distinção importa mais que a lista.

**⚠️ O `--ver` INVENTOU TRÊS DEFEITOS.** Ele listava *todas* as imagens da
pasta, e a pasta do carrossel também guarda `produto_1.jpg` / `produto_2.jpg`
(assets de trabalho). No preview apareciam duas fotos cruas de catálogo no fim,
e quem revisou leu como parte do post: *"imagens feias, parece que vieram do
Google"*, *"o produto não tem relação com o conteúdo"*, *"diz 10 slides mas
numera até 8"*. **As três críticas eram do preview, não do carrossel** — o post
tem 8 slides e termina no CTA. Agora o `--ver` só lista `\d{2,3}.jpg`.

> **Ferramenta de revisão que mostra o que não vai ao ar não é neutra: ela
> inventa defeito e faz a gente consertar o que não está quebrado.** É a irmã
> gêmea do `--agenda` que mentia sobre domingo. Diagnóstico errado custa mais
> que diagnóstico nenhum, porque vem com confiança junto.

**Os defeitos reais:**

1. **Cabeçalho invisível no `meio`.** Ele passava `escuro=False` (o slide é
   creme) — mas o TOPO do slide é a FOTO, que é escura. Texto `#1C1A18` sobre
   foto escura: sobrava só o "Shop", que é laranja e tinha contraste. **Terceira
   vez na mesma família** (logo escura sobre escuro; "Shop" laranja sobre slide
   laranja; agora cabeçalho escuro sobre foto escura). A lição que faltava
   escrever: **o parâmetro não deve descrever a COR DO SLIDE, e sim o que está
   ATRÁS DAQUELE ELEMENTO.** Agora é `_cabecalho(..., bool(ctx['fundo']))`.
2. **⚠️ "NÃO REPETIR A ANTERIOR" NÃO BASTA.** Saiu
   `meio → respiro → meio → respiro → numero → checklist`: nenhuma repetida em
   sequência, e mesmo assim **A→B→A→B**, que é padrão tão legível quanto A→A→A.
   Eu tinha implementado uma regra que olhava UM slide pra trás, contra um
   pedido que era sobre a SÉRIE inteira. Agora a janela é dos **dois últimos** —
   alternar passa a exigir três composições, e três já não parece fórmula.
3. **Três numerações competindo no mesmo slide:** a bola dizia "3" (índice do
   slide), o rótulo dizia "HÁBITO 2" (o item real) e o contador dizia "4/8". O
   `ordem` era `i - 1`, que só coincide com o item quando não há slide de
   abertura extra. Agora `_numero_do_item()` lê o número DO RÓTULO quando existe,
   e `_marca_de_ordem()` garante **uma** marca por slide: rótulo OU bola, nunca
   as duas.
4. **4 de 6 slides sem imagem** — `respiro` não leva foto (é o contraste),
   `numero` claro não levava, `checklist` não levava. Com 10 fundos no acervo,
   slide sem foto tem que ser escolha, não consequência. `numero` claro ganhou
   faixa de foto no alto.
5. **Texto demais.** Um slide com 6 linhas de parágrafo explicando cerdas,
   esponja e cantinhos. É o `CARR_PALAVRAS_CORPO=38` sendo generoso demais pra
   celular. **Não mexido ainda** — é ajuste de brain, e mexer sem medir é chute.

#### 🔁 3ª RODADA — logo redonda, proporção e numeração semântica (23/08, noite)

- **A logo era "um quadrado dentro de um círculo maior"** (o Dre viu de
  primeira). O `img` ia a 70% com `contain` dentro do `.selo`, e como a logo da
  conta JÁ É um quadrado escuro com o TS, sobrava um anel branco de fundo em
  volta nos slides escuros. Agora é **como o avatar do Instagram**: `cover` a
  100%, o PNG preenche o círculo. Logo opaca esconde o fundo; logo com
  transparência continua apoiada nele.
- **`meio`: faixa de foto de 640px → 840px** (47% → 62% da altura). Com a
  proporção antiga sobrava área creme MAIOR que a foto: o slide lia como
  "cortado no meio" e ficava mais fraco que os escuros do mesmo carrossel, como
  se tivesse faltado imagem. **A quebra clara é boa; a proporção é que estava
  errada.**
- **`checklist` ganhou foto cheia + véu + cartão.** Ele era creme vazio e vinha
  colado no fecho, que também é claro: o carrossel terminava
  `foto → creme vazio → creme vazio`, justo o clímax perdendo energia.
- **Regra nova: nunca dois slides sem foto seguidos** (`_SEM_FOTO`). Só vale
  quando há foto disponível — sem acervo a regra não inventa nada.
- ⚠️ **`numero_semantico != numero_slide`, e isso sobreviveu ao 1º conserto.** O
  slide de ABERTURA — *"Muita gente faz 3 coisas que só atrapalham"* — ganhou
  uma bola com **"1"**, porque a bola vinha do índice do slide. Ele não é a dica
  1; é a promessa das três, e o "1" contradizia o "3" na mesma linha de visão.
  Agora **só o rótulo diz se o slide é um item**: sem rótulo, nenhuma marca de
  ordem, e a composição `numero` nem entra na disputa.
- **O tom do `checklist` virou `ambos`** porque ele fica escuro com foto e claro
  sem. Deixar `claro` fixo fazia a alternância decidir com base em informação
  falsa **e o log imprimir "(c)" onde saiu um slide escuro** — diagnóstico que
  mente, de novo.

#### 🖼️ IMAGEM POR SLIDE — "eu mesmo que preciso fazer?" (23/08, noite)

⚠️ **NÃO. E A CHAVE JÁ ESTAVA NO `.env` HÁ MESES.** O projeto inteiro chama
`google.genai` com `GEMINI_API_KEY` pra escrever texto (`main.py`, `ceo_agent`,
`narration_script_builder`…). **A mesma chave e o mesmo cliente geram imagem** —
muda só o nome do modelo (`gemini-2.5-flash-image`). Não precisa de conta nova,
chave nova nem SDK novo. Eu nunca tinha olhado pra isso: fui atrás de Fal e de
Pexels enquanto a capacidade estava dentro de casa.

⚠️ **O QUE ISSO NÃO É:** não é o ChatGPT ilimitado do Dre. Aquilo é assinatura,
e assinatura não vira API. No Gemini paga-se por imagem. **As duas fontes
coexistem e servem a coisas diferentes:**

| fonte | custo | serve pra |
|---|---|---|
| ChatGPT, na mão | grátis (31 dias) | acervo de AMBIENTE, reusado o mês inteiro |
| Gemini, API | por imagem | a foto DAQUELE slide, no dia, sozinho |

`fundo_ia.py --do-plano <pasta>` lê o `plano.json` (que já existe em disco antes
do render e já sabe o que cada slide diz) e gera **uma imagem por slide, a
partir do texto do slide**. `--seco` mostra os prompts sem gastar.

Isso é o conserto do maior defeito que sobrou, e o teste que o ChatGPT propôs
nomeia bem: *"se eu remover todo o texto, essa imagem ainda representa o assunto
deste slide?"* — dava **não em 4 dos 8**, porque o fundo saía por rodízio do
acervo do NICHO. O slide dizia "bebê em posição errada" e o fundo era uma
despensa com potes: casa a estética da conta, não casa o assunto.

⚠️ **E O RENDER PRECISAVA SABER DISSO.** `_fundo()` agora procura
`<pasta>/fundos/NN.png` ANTES de qualquer outra coisa. Faltavam duas
informações que o plano não carregava: `pasta` (era só argumento do
`renderizar_slides`) e o número do slide (só existia como índice do laço). Sem
elas o `--do-plano` geraria as imagens **e o render não olharia pra elas** —
trabalho feito, pago e jogado fora, em silêncio.

#### 🧱 O `--do-plano` FALHOU NO 1º USO — e os 3 defeitos que ele revelou (24/08)

**1. `plano.json` nunca existiu.** Eu supus que a pasta do carrossel guardava o
plano. Ela guardava `conta.json`, `engajamento.json` e `legenda.txt` — o que o
carrossel DIZ morria com o processo. Pior: no **dry-run** a pasta nem era
preparada, e dry-run é exatamente onde o `--do-plano` deveria rodar (gerar as
imagens antes de publicar). Agora os dois caminhos escrevem `plano.json`.
⚠️ **No dry-run só o `plano.json`, nunca o `conta.json`** — pasta com conta é
pasta pronta pra postar, e ensaio não pode virar publicação por engano.

**2. `produto(c) → produto(c)`, duas composições idênticas coladas.** A janela
dos dois últimos não pegou, e o motivo é estrutural:

> **Regra de variedade não funciona sem alternativa.** `_elegiveis` devolvia UMA
> opção quando o slide tem foto de produto, e não se escolhe entre uma coisa.
> Carrossel de `comparacao` e de `lista` tem vários slides de produto seguidos,
> então essa era a única família **garantida** a repetir — por construção, não
> por azar do sorteio.

Nasceu a `vitrine`: produto num cartão à direita sobre o ambiente escurecido,
texto na esquerda. Silhueta oposta à `produto`, que centraliza em fundo claro.

**3. ⚠️ O `_fundo()` USAVA A FOTO DE CATÁLOGO COMO FUNDO DE TELA CHEIA.** Este é
o grande. `item["foto"]` estava na lista de candidatos a fundo — e ela é o
recorte da Shopee em fundo branco. Escurecida a 38% e esticada em `cover`, virava
um borrão cinza gigante com a silhueta do produto atrás do texto. **O cabeçalho
do `fundo_ia.py` avisa disso desde o primeiro dia** — *"foto de catálogo vira
mancha; foto de ambiente vira capa"* — e mesmo assim o catálogo estava na lista.
Foto de produto tem um lugar só: dentro do `.palco`, no slide de produto.

**E o `.palco` virou branco, com `isolation:isolate`.** O `mix-blend-mode:
multiply` sozinho era frágil demais pra ser a estrutura: a regra global de
`z-index` cria contexto de empilhamento em todo filho direto de `.slide`, o
blend passava a mesclar contra transparente e o branco do catálogo ficava à
mostra — o "parece que pegou da Shopee" que eu já tinha declarado resolvido
**duas vezes**. Sobre cartão branco a foto de catálogo some sozinha, com ou sem
blend; o multiply virou reforço, não estrutura.

#### 🧠 O BRAIN — três consertos de conteúdo (24/08)

**1. ⚠️ O FORMATO VIRAVA RÓTULO.** O brain escolheu `passo_a_passo` e o Gemini
devolveu quatro DICAS INDEPENDENTES ("entenda os sinais do bebê", "crie um
cantinho tranquilo"). Nada ali era passo: some o terceiro e os outros continuam
de pé.

> E o estrago não é estético. O ledger registra `passo_a_passo`, e a **fase 2**
> um dia vai decidir o que postar comparando o desempenho dos formatos — usando
> um histórico de posts que nunca foram o que diziam ser. **Formato mentiroso
> envenena a medição futura**, e ninguém vai conseguir voltar atrás.

A causa: o `desc` de cada formato tem UMA LINHA, e uma linha não segura
estrutura. Nasceu o `ROTEIROS`, que diz o que CADA SLIDE tem que ser. O teste
que o `passo_a_passo` agora carrega no prompt é literal:

    "Se voce puder trocar a ordem dos slides sem estragar nada, voce
     escreveu uma lista e o formato esta errado — reescreva."

**2. O GANCHO FECHAVA A CONTA.** *"O jeito mais fácil de limpar mamadeiras"* numa
conta de **Casa**. A regra antiga só proibia o padrão `"se você tem X"` — e
nenhuma das duas falhas reais tinha esse formato. Agora a regra 3 tem exemplo
ERRADO e CERTO com o caso que aconteceu, e diz onde o específico cabe: **dentro
de um slide, não na capa.**

⚠️ **E ganhou uma segunda trava: DUPLO SENTIDO.** *"evitar o choro na mamada"*
lido rápido no feed, sem foto e sem contexto, vai pro lugar errado. A regra manda
ler a capa em voz alta imaginando quem passa rápido — **não adianta explicar no
slide 2, porque ninguém lê o slide 2 pra corrigir a leitura do slide 1.**

**3. O CTA PROMETIA O QUE O POST NÃO TINHA** — e aqui o prompt não bastou.

Primeiro tentei só a regra no prompt. No teste seguinte o Gemini devolveu
*"comenta LINK que eu te mando"* num carrossel de 8 slides **sem um único
produto**. Fui olhar o código e o problema era maior:

    CTA_PADRAO = {"linhas": ["🛒 o link tá na bio",
                             "💬 comenta QUERO que eu te mando"]}

⚠️ **AS DUAS LINHAS DO FECHO ERAM FIXAS.** O Gemini escrevia só o `titulo`; as
linhas de baixo prometiam link em TODO carrossel, inclusive os que não citam
produto. **Era estruturalmente impossível ter um fecho não-comercial** — e
nenhuma regra de prompt conserta o que o código escreve depois.

`_cta_do_conteudo()` decide pelo que os slides realmente têm:

| o post mostrou | fecho |
|---|---|
| produto com preço | "o link tá na bio" · "comenta QUERO" |
| checklist/resumo | "salva pra consultar na hora que precisar" |
| só texto | "comenta aqui embaixo — respondo todo mundo" |

E se o modelo prometer link num post sem produto, o código **troca o título** e
avisa no log (`↩️ CTA prometia link num post sem produto — troquei`).

> **Prompt pede; código garante.** Prometer link no que não tem link é anúncio
> mentiroso, e isso não pode depender de o modelo estar de bom humor.

Confirmado nos dois testes seguintes: `↩️ CTA prometia link num post sem
produto — troquei` disparou em `passo_a_passo` e em `erros`, e o `erros` saiu
com *"Qual desses você fazia?"*.

#### 🪜 REGRA O MODELO OBEDECE NA FORMA; ESTRUTURA ELE COPIA DE EXEMPLO (24/08)

O roteiro do `passo_a_passo` falhou **duas vezes, em nichos diferentes** — o que
descarta azar de sorteio:

    casa  PASSO 1 Comece eliminando o que não serve
          PASSO 2 Olhe pra sua casa com outros olhos     ← não depende do 1
          PASSO 4 Menos é mais: simplifique              ← repete o 1
    tech  PASSO 1 Comece pela proteção básica
          PASSO 2 Entenda o que desgasta mais            ← devia vir ANTES
          PASSO 3 Otimize seu carregamento diário

A regra abstrata ("o passo 2 depende do passo 1") comprou a **superfície**:
rótulo `PASSO N`, verbo no início do título. Não comprou a dependência.

Então o `passo_a_passo` ganhou o único roteiro **com exemplo trabalhado** — um
par ASSIM NÃO / ASSIM SIM, e a frase que explica o mecanismo: *"no exemplo bom,
o PASSO 2 fala do 'que sobrou' do PASSO 1, e o PASSO 3 fala do 'monte' que o
PASSO 2 criou. Cada título CITA algo que o slide anterior produziu."*

⚠️ **E UMA SAÍDA HONESTA PRO MODELO: o campo `aviso`.** Boa parte dos produtos
de afiliado **não tem procedimento de 4 passos** — "manter o celular em dia" é
lista de cuidados, não sequência. Forçar produz passo falso. Agora o modelo pode
dizer que o formato não cabe, em vez de inventar.

**RESULTADO (2ª rodada com o exemplo):**

`casa` passou. O teste de embaralhar não quebra mais:

    PASSO 1 Libere o palco da sua festa
    PASSO 2 Ache o coração da sua celebração
    PASSO 3 Dê vida ao seu ponto focal        ← precisa do 2 ter achado
    PASSO 4 Expanda a atmosfera por toda casa ← precisa do 3 ter um centro

⚠️ **`tech` SE CORRIGIU SOZINHO — E EM SILÊNCIO.** Pedimos `passo_a_passo`, o
modelo percebeu que "manter o celular" não tem sequência, **tirou os rótulos
PASSO por conta própria** e escreveu *"4 hábitos"*. O texto ficou honesto; o
registro, não — o ledger ia gravar `passo_a_passo` num post que virou lista.

> É o mesmo envenenamento da medição, só que mais difícil de ver: **antes o
> formato saía errado E rotulado errado; agora sai certo no texto e errado na
> etiqueta.** E ele nem usou o campo `aviso` — se corrigiu e seguiu.

Por isso o ledger passou a guardar **os dois**: `formato` (o que pedimos) e
`formato_real` (o que veio). Quando um `passo_a_passo` sai sem rótulos de passo,
o registro vira `lista` e o log diz por quê — *"o texto está ok, a etiqueta é
que não podia mentir"*.

⚠️ **E O `aviso` VAI PRO LEDGER, não só pro log.** Pedir sinalização e depois
ignorar o campo é pior que não pedir: cria a impressão de que existe uma trava
onde não existe. No ledger ele responde, daqui a meses, *"em quantos
`passo_a_passo` o próprio modelo avisou que não era passo?"* — número alto
significa formato sendo forçado, e o peso dele precisa cair. **Sem registrar,
essa pergunta não teria como ser feita.**

⚠️ **NÃO ENTROU O `FACT_CHECK_REQUIRED`** que o ChatGPT propôs (bebê/saúde/
suplemento): o Dre disse que já resolveu isso por outro caminho. Fica anotado que
foi decisão dele, não esquecimento — pra ninguém reintroduzir achando que faltou.

#### 🔎 ÍNDICE SEMÂNTICO — a imagem escolhida pelo ASSUNTO do slide (25/08)

O Dre e o ChatGPT chegaram no mesmo diagnóstico: **o render está resolvido, o
gargalo virou a escolha da imagem.** No carrossel de casa saiu:

    "escolher a árvore"   → foto de cesto com manta
    "abrir os galhos"     → foto de escritório com luminária
    checklist da árvore   → guarda-roupa antes/depois

Texto e imagem contando duas histórias diferentes. A biblioteca por formato
resolveu METADE: garante que um carrossel de `erros` pegue da pasta `erros`.
**Dentro da pasta o sorteio continuava cego** — e a frase do Dre nomeia o que
faltava: *"se o Jarvis ver a imagem e conseguir interpretar, vai ser um passo
absurdo"*.

⚠️ **E O CUSTO É O PONTO DE PROJETO, não detalhe.** Perguntar a uma IA "qual
destas 10 fotos combina com este slide?" a cada render seria **uma chamada por
SLIDE**, todo dia, em 6 contas:

    8 slides × 2 posts/dia × 6 contas × 30 dias  =  2.880 chamadas/mês
    230 imagens × 1 chamada                      =  custo fixo, pago uma vez

É o mesmo erro do fundo gerado por post que a gente já tinha rejeitado. Então a
visão passa **uma vez por imagem, na vida**: descreve, guarda em
`assets/fundos/indice.json`, e daí em diante a escolha é **comparação de
texto** — microssegundos.

    fundo_ia.py --indexar tech --limite 5    # prova com 5 antes de soltar
    fundo_ia.py --indexar                    # todas as que faltam
    fundo_ia.py --buscar casa "abrir os galhos" --formato passo_a_passo

⚠️ **RETOMÁVEL, porque são centenas e a rede cai.** Cada imagem é gravada assim
que descrita; refazer do zero jogaria fora o que já foi pago.

⚠️ **EMPATE VOLTA PRO RODÍZIO, de propósito.** Sem isso o melhor par
texto↔foto de cada formato sairia em TODO carrossel daquele formato: a
coerência subiria e a variedade morreria — o defeito que custou uma semana pra
consertar. **O índice desempata; ele não manda sozinho.**

⚠️ **E O `_rodizio()` FOI EXTRAÍDO pra que a busca use A MESMA memória.** Duas
memórias de rodízio no mesmo módulo seriam duas verdades sobre "o que já saiu",
e a segunda repetiria o que a primeira acabou de usar — parecendo funcionar.

**Medido no caso real** (os 4 slides da árvore de Natal, com título + corpo
como o render manda):

    "onde tudo vai"        → canto de sala vazio com tomada
    "defina a árvore"      → árvore de natal montada ao lado do sofá
    "volume começando de baixo" → mãos abrindo os galhos de baixo
    "toques finais"        → árvore montada

Quatro de quatro. Só com o título, dois de quatro casavam — **é o corpo do
slide que carrega os substantivos concretos**, e por isso o `assunto` soma
título + linha + rótulo.

#### 🌗 O VÉU NÃO DESCREVE A FOTO — DESCREVE O QUE VAI SER LIDO EM CIMA (25/08)

O Dre: *"achei o CTA final muito escuro pra ler, as letras pretas se esconderam
no design"*. E era exatamente isso.

Os cinco fechos nasceram **sem foto**, e cada um escolheu a cor do texto pro
fundo chapado que tinha: `perfil`, `ajudou` e `salva` são escuros com letra
clara; **`comente` e `perfil_certo` são cremes com letra PRETA**. Quando injetei
a mesma camada escura nos cinco (24/08), os dois últimos ficaram com letra preta
sobre foto de meio-tom. Some.

⚠️ **É A QUARTA VEZ NESTA MESMA FAMÍLIA:** a logo escura sobre escuro, o "Shop"
laranja sobre laranja, o cabeçalho do `meio` sobre a foto, agora o fecho. A
lição já estava escrita neste arquivo — e eu não a apliquei ao criar camada
nova. Escrever a lição não é o mesmo que consultá-la.

**A regra, agora explícita:** modelo de letra clara pede véu escuro; modelo de
letra escura pede a foto **lavada até quase branco** (`brightness(1.25)` +
degradê do `clarinho` a 95%). Conferido nos cinco: `comente` e `perfil_certo`
recebem véu claro, os outros três o escuro.

#### 📚 BIBLIOTECA POR FORMATO — `fundos/<nicho>/<formato>/` (24/08)

O Dre está gerando **100 imagens por nicho, separadas por formato de carrossel**
(erros, curiosidade, comparação, checklist, lista, produto, problema/solução,
CTA, não-compre, antes-depois). São ~600 imagens.

⚠️ **A ESTRUTURA PRECISAVA EXISTIR ANTES DA TRANSFERÊNCIA, não depois.** Uma
pasta chapada por nicho jogaria fora a informação mais valiosa dessa
biblioteca: **um fundo de "erros" e um de "checklist" não são
intercambiáveis**. Com o formato na pasta, o rodízio deixa de ser "uma foto
bonita do nicho" e vira "uma foto que combina com o que este carrossel está
dizendo" — sem custar uma chamada de IA.

    fundos/moda/erros/moda-erros-01.jpg
    fundos/moda/lista/moda-lista-01.jpg
    fundos/moda/*.jpg            ← a raiz continua valendo (comportamento antigo)

- `--importar <nicho> --formato erros --de <pasta>`
- `existentes(nicho, formato)` cai na raiz quando o formato não tem acervo
- `--listar` mostra a árvore com a contagem por formato
- ⚠️ **e o `_fundo()` do `slides_html` passa `plano["formato"]`** — sem isso a
  biblioteca existiria e ninguém a consultaria: 600 imagens separadas com
  cuidado voltariam a ser 600 imagens sorteadas.
- a deduplicação passou a olhar só a pasta de destino: a mesma cena pode
  legitimamente existir em `erros` e em `checklist`, são usos diferentes.

⚠️ **OS NOMES DAS PASTAS NÃO PRECISAM SER OS MEUS** (`_ALIAS`, 24/08). O Dre
organiza com os nomes que o ChatGPT sugeriu; o brain usa os dele. São listas
parecidas e **não iguais**, e a diferença falha em silêncio: `tech/curiosidade/`
com 10 imagens ótimas nunca seria encontrada por um brain que chama aquilo de
`historia` — o rodízio cai na raiz e o trabalho de separação vira enfeite.
Traduzir na leitura é melhor que renomear 600 arquivos ou obrigar quem organiza
a decorar meus nomes:

    curiosidade / segredo  → historia        top5 / ranking → lista
    antes-depois           → antes_depois    não compre     → nao_compre

⚠️ **E `cta/` E `produto/` NÃO SÃO FORMATOS — SÃO PAPÉIS DE SLIDE.** Um
carrossel de `erros` termina num CTA e pode mostrar um produto no meio; esses
dois slides não querem a mesma foto que os slides de erro. `_fundo(..., papel=)`
faz o papel GANHAR do formato, e o fecho pede `cta`, as duas composições de
produto pedem `produto`. Sem isso, o fecho de todo carrossel de `erros` pegaria
foto de erro.

#### 🖥️ ⚠️ TODO BLOCO DE COMANDO PRECISA DIZER **EM QUAL MÁQUINA** RODA (24/08)

O Dre colou um script de **PowerShell** (que cria as 60 pastas no Windows dele)
no **bash da VPS**:

    =: command not found
    New-Item: command not found
    Command 'explorer' not found

Culpa da instrução, não dele. Os dois blocos vinham seguidos na mesma resposta,
o anterior era bash da VPS, e nenhum dos dois dizia onde rodava. Os prompts são
quase idênticos (`root@vmi...#` e `PS C:\Users\...>`) e quem está no meio de
uma sequência não olha pro prompt, olha pro próximo bloco.

É a mesma família do *"instrução dentro de sequência de comando é comando que
não roda"* (o Caddyfile, 22/08) e do *"comando com data na mão tem prazo de
validade"*. **Explicar melhor não resolve — o certo é o comando não precisar da
explicação:**

    fundo_ia.py --criar-arvore ~/fundos   # cria as 60 pastas NA VPS
    fundo_ia.py --arvore ~/fundos         # importa <nicho>/<formato>/ inteiro

Assim o PowerShell sai da jogada: as pastas nascem onde o Dre já está logado, e
o Windows só precisa de `scp`, que ele já usa. **E o laço de bash de 60 pastas
que eu tinha mandado colar também sumiu** — laço colado é onde mora o erro que
ninguém vê: um `for` escrito errado importa metade, e "metade" não aparece em
lugar nenhum depois. Com um comando, quem sabe a estrutura é o programa, e o
relatório do fim conta quantas entraram em cada formato **e quantas pastas
continuam vazias**.

#### 🗂️ `--contato` — como eu reviso 260 imagens que não consigo ver (24/08)

O Dre gerou 260 fundos (tech e casa) e perguntou se eu conseguia dar uma olhada.
**Eu não vejo o disco da VPS nem a área de trabalho dele** — e mesmo publicando
com `midia_publica --ver`, 130 imagens são 130 arquivos pra abrir um por um. Na
prática, isso não é revisão: é uma lista que ninguém termina.

`fundo_ia.py --contato <nicho>` monta **uma folha por formato**: grade de
miniaturas 4:5 num JPEG só, com o nome do arquivo queimado em cada célula.

    🗂️  casa-erros.jpg  (5 imagens, 92 KB)
    🗂️  casa-lista.jpg  (6 imagens, 104 KB)

⚠️ **O NOME EM CADA CÉLULA NÃO É ENFEITE.** Sem ele eu diria "a terceira da
segunda linha está estranha" e ninguém saberia qual arquivo é. Com ele a
conversa vira "troca a `casa-lista-04`".

**E o teste provou o valor sozinho:** eu misturei imagens de `moda` dentro de
`casa/lista` de propósito, e na folha elas **saltam de imediato** — joia, terno
e flatlay masculino no meio de cozinha e quarto. Numa lista de 130 arquivos
abertos um a um, isso passaria batido; numa grade, o que destoa destoa JUNTO.
É pra isso que serve olhar tudo ao mesmo tempo.

(Detalhe pego na 1ª folha: o `—` do cabeçalho virou quadradinho — a fonte
embutida do PIL não tem travessão. Só ASCII ali. Bobo, mas a folha existe pra
ser lida, e caractere quebrado no título é a primeira coisa que o olho acha.)

#### 🕐 `--lotes` — MÁQUINA RECONSTRÓI A ORDEM, OLHO HUMANO PÕE O RÓTULO (24/08)

O Dre gerou ~260 fundos em blocos de 10, **todos caíram juntos em `Downloads`**,
e ele não lembra a ordem: *"acho que foi pet, beleza, tech, moda, casa, geral. Aí
depois tech 100 e casa 100"*. Sem separação, as 260 viram um monte só — o acervo
funciona, mas perde o nicho e o formato que custaram horas pra gerar.

⚠️ **A MEMÓRIA DE QUEM BAIXOU FALHA; O CARIMBO DE TEMPO, NÃO** — mas o carimbo
certo **não é o `mtime`**.

O `scp` sem `-p` não preserva data: os 268 arquivos chegaram na VPS com a hora
da transferência. Ordenar por `mtime` devolveria a ordem em que o shell expandiu
o `*.png`, que é **alfabética** — e alfabética junta `(1)`, `(10)`, `(2)`, `(3)`.
Os blocos originais viravam picadinho, e o `--lotes` entregaria grupos errados
**com toda a cara de certos**.

Só que o ChatGPT carimba a hora **no nome do arquivo** (`ChatGPT Image 24 de
ago. de 2026, 15_29_23 (4).png`), e nome sobrevive a qualquer cópia.
`_quando_baixou()` lê o nome primeiro e só cai no `mtime` como plano B.

⚠️ **E O CORTE É POR BURACO DE TEMPO, NÃO A CADA 10.** Cortar de 10 em 10 só
funciona se todo bloco tiver 10 — e o acervo tem avulsas (uma imagem sozinha às
17:31:40) e lotes incompletos. **Um único bloco de 9 desalinha todo o resto da
lista**, e o erro não aparece: sai um `lote-14` misturando o fim de um formato
com o começo de outro, e ninguém percebe até ver o carrossel. Baixar um lote
leva segundos; entre um lote e outro passam dezenas. Cortar onde o buraco é
grande devolve os blocos REAIS; o `--tamanho` vira só teto de segurança.

Testado contra os nomes reais do log do Dre: três blocos de 10 limpos e as
avulsas do fim agrupadas.

**RESULTADO (24/08): 256 importadas, biblioteca de pé.**

    casa   116  ·  20 na raiz + 96 em 10 formatos
    tech   110  ·  10 na raiz + 100 em 10 formatos
    beleza / pet / moda / geral   10 cada, na raiz

Duas coisas que o log confirmou sem alarde:

- ⚠️ **O `_ALIAS` fez o trabalho dele em silêncio.** O Dre importou
  `curiosidade` e a árvore mostra `historia`. Sem essa tradução, 20 imagens
  ficariam numa pasta que o brain nunca procuraria — e ninguém veria erro.
- ⚠️ **`casa/cta` ficou com 6 de 8.** Duas das avulsas eram cópias LITERAIS de
  outras duas (o ChatGPT regerou a mesma cena). A dedup por conteúdo pegou.
  Sem ela o rodízio mostraria aquela poltrona com o dobro da frequência,
  achando que eram fundos diferentes.

Mas o relógio **não sabe o que cada bloco É**. E é aí que a folha de contato
fecha o par: eu olho a grade e digo "esse é pet" (comedouro, caminha, bolsa de
transporte, gato na janela — não tem como errar). **Máquina reconstrói a ordem,
olho humano põe o rótulo. Nenhum dos dois faria o trabalho sozinho.**

    fundo_ia.py --lotes ~/downloads          # folhas + lotes.json
    midia_publica.py --ver pronto_carrossel/lotes
    (eu olho e digo o que é cada lote; o Dre preenche o JSON)
    fundo_ia.py --aplicar-lotes .../lotes.json

⚠️ **Lote sem `nicho` preenchido é PULADO E ANUNCIADO.** Pular calado seria o
pior desfecho: o Dre acharia que importou tudo e o acervo ficaria menor do que
ele pensa, sem sinal nenhum.

⚠️ **E O `~/qualquer-pasta/` QUE EU ESCREVI COMO EXEMPLO, ELE COLOU LITERAL.**
Terceira ocorrência da mesma família (o Caddyfile como comentário, o PowerShell
no bash, agora o placeholder). **Placeholder dentro de bloco de comando é
comando** — quem está executando uma sequência não separa exemplo de instrução.

#### 🎨 A PALETA DE `moda` BRIGA COM O ACERVO DE `moda` (24/08)

Medindo os 10 fundos de moda que o Dre gerou:

| imagem | brilho | cor média |
|---|---|---|
| seda + corrente de ouro | 0.09 | quente escuro |
| terno azul | 0.10 | **azul** (15,26,40) |
| sneakers | 0.17 | **azul** (20,48,77) |
| bolsa + scarpin | 0.15 | **azul** (30,39,52) |

E a paleta da conta tem acento **`#C2456B` — rosa framboesa**. Sobre foto
azul-marinho com dourado isso não combina: o acento vira um corpo estranho no
slide. O acento de `geral` (`#B98B2E`, dourado) casaria com o que ele gerou.

> **Quando o acervo é bom, é ele que define a identidade — não a paleta que eu
> escolhi antes de existir foto nenhuma.** As paletas nasceram como suposição
> ("moda = rosa"); agora existe evidência, e evidência ganha de suposição.

**DECIDIDO (24/08), com o teste lado a lado.** O Dre pediu a melhor decisão pra
conta, então rendereizei as duas paletas na mesma foto em vez de argumentar
sobre cor. Na versão rosa, o círculo de acento por cima do ombro da modelo
**parece defeito de impressão**; na azul+dourada o mesmo elemento vira
profundidade. Não foi opinião, foi olhar.

    moda: acento #C9A45C · escuro #141A26 (era #C2456B / #241B1E)

⚠️ **E o `escuro` mudou junto, de propósito.** Só trocar o acento pro dourado
deixaria `moda` idêntica a `geral` (`#B98B2E`) — duas contas com a mesma cara.
**É a BASE que separa as duas:** moda em azul-marinho, geral em marrom quente,
e o mesmo ouro por cima lê como duas marcas diferentes. Voltar é uma linha.

#### 💡 O ACERVO TEM DUAS FAMÍLIAS DE LUZ — véu medido, não chutado (24/08)

O Dre gerou 120 fundos no ChatGPT. Medindo o brilho médio deles, aparece uma
divisão limpa que **ninguém tinha pedido e que quebra o template**:

| lote | luminância medida | família |
|---|---|---|
| `casa` (jantar, despensa, quarto) | 0.14 – 0.20 | **noturna** |
| `tech` (setup neon, relógio, gadgets) | 0.14 – 0.29 | **noturna** |
| `pet` (comedouro, cachorro, gato) | 0.61 | **clara** |
| `beleza` (mármore, flatlay rosa) | 0.62 – 0.70 | **clara** |

⚠️ **As duas famílias estão ótimas. O errado era o véu ser fixo**, calibrado no
lote escuro do `casa`:

    foto escura + brightness(.40)  → dramática ✅
    foto clara  + brightness(.40)  → CINZA SUJA ❌

`_brilho()` mede (thumbnail 48px, luminância média, com cache) e `_veu(ctx,
alvo)` calcula o filtro que leva AQUELA foto até a luminância pedida. O slide
escuro pede 0.22 e cada imagem chega lá do seu jeito. Mesma ideia do
`_logo_claro()`: trocar um palpite por um fato.

⚠️ **O TETO DO VÉU É 1.12, e isso importa.** Perseguir o alvo pra CIMA clareia
foto noturna: a sala de jantar do `casa` com `brightness(1.83)` perde a
penumbra, o brilho da luminária estoura e o grão aparece. O véu existe pra
escurecer o que está claro demais pro texto ler — foto já escura está no ponto.

**E A FOTO PASSOU A TER VOTO NO TOM DO SLIDE, antes de tudo.** Foto clara vai
pra composição clara, escura pra escura. Na 1ª versão esse voto vinha DEPOIS da
janela anti-repetição, e no teste com as duas famílias misturadas uma foto clara
de pet caiu na `cheia` (escura) porque a janela já tinha eliminado as claras —
mancha cinza no meio de um carrossel bonito. A hierarquia certa:

> **foto clara em composição escura → parece DEFEITO.**
> **composição repetida → parece repetida.**
> Uma custa a credibilidade do post; a outra custa um pouco de ritmo.

Junto: a `numero` escura ganhou degradê embaixo. Era a única composição escura
sem ele, e com foto de ambiente texturizada (sofá, almofadas) o corpo em cinza
claro ficava no limite da leitura.

#### 🔴 TESTE MULTI-NICHO — dois defeitos críticos que o `casa` escondia (24/08)

Rodamos tech, beleza e pet. O `casa` sozinho tinha escondido os dois piores
problemas do sistema.

**1. 🔴 O TEXTO DE UM PRODUTO COM A FOTO DE OUTRO.** No @topshoptech_:

    "Resgate sua infancia gamer agora"   → foto de um smartphone
    "Seu cinema particular onde quiser"  → foto de um tubarao de controle remoto

A causa: `prod = produtos[i]` — **casamento por POSIÇÃO**, supondo que o modelo
escreveria os slides na mesma ordem em que a lista de produtos chegou. Ele não
escreve.

> **É o defeito mais caro que este sistema pode ter, porque não parece
> defeito.** Parece anúncio mentiroso. Quem clica encontra outra coisa, e a
> conta perde a única coisa que tem, que é a confiança de quem segue. Nenhum
> ajuste de layout conserta e o log não menciona nada.

Agora os produtos vão **numerados** no prompt e o modelo devolve
`"produto": <n>` em cada slide; `_casar_produto()` liga por esse número. Índice
repetido é tratado como sintoma (se dois slides pedem o mesmo produto, algum
ficou órfão) e cai na posição, com aviso. Sem o campo — modelo antigo, reserva —
o comportamento é o de antes, então nada quebra.

**2. 🔴 AINDA SE PAGAVA POR IMAGEM QUE NÃO APARECIA — e eu já tinha "resolvido"
isso duas vezes.** No pet foram geradas 7 imagens e o leitor não via 4. A
sequência do log é praticamente um teste unitário:

    meio(c) → SEM imagem   numero(e) → SEM imagem
    meio(c) → SEM imagem   numero(e) → SEM imagem   checklist(e) → COM

⚠️ **E as composições estavam certas.** A fonte era uma linha só, na montagem
do `ctx`:

    "fundo": _fundo(plano, item) if item.get("fundo") else ""

O slide só ia atrás de foto **quando o brain tinha marcado `fundo: True` nele** —
uma marca de outra época, de quando o fundo era sorteio do acervo do nicho e a
gente escolhia quais slides mereciam. Com imagem gerada sob medida a pergunta
perdeu o sentido: se `fundos/NN.png` existe, alguém pagou por ela pra ESTE slide.
No `casa` passou batido porque o formato usado marcava `fundo` na maioria dos
slides; no `pet` (formato `erros`) o brain não marca quase nenhum.

**A lição, e ela é sobre método:** eu consertei `respiro`, depois `checklist`,
depois `vitrine`, depois os cinco fechos — **quatro consertos, um a um, sem
nunca perguntar de onde os quatro tiravam a informação**. Era todo mundo da
mesma linha. Sintoma repetido em lugares diferentes é sinal de causa única
acima deles, não de quatro defeitos parecidos.

**3. ✅ `_conferir_imagens_usadas()` — a defesa que não depende de eu lembrar.**
Depois do render, o programa confere se cada arquivo de `fundos/` aparece em
alguma página (a foto vira `data:` URI, então basta procurar um trecho do
base64) e grita no log quando não aparece:

    💸 2 imagem(ns) GERADA(S) E NÃO USADA(S): 03.png, 05.png
       Alguém pagou por elas e o leitor não vai ver.

Três causas diferentes, o mesmo sintoma invisível, três consertos que falharam
em silêncio. **A defesa não podia ser eu conferir — tinha que ser o programa.**

#### 🎬 DIRETOR VISUAL, E A REGRA DA IMAGEM PAGA (24/08)

Primeira rodada com imagem por slide de verdade. O Dre: *"melhorou absurdamente
o nível do carrossel, imagens ótimas"* — e aprovou o visual do `casa`. O que
sobrou são três coisas nomeadas com precisão pela revisão:

**1. ⚠️ IMAGEM PAGA DESCARTADA PELA COMPOSIÇÃO.** O `04.png` foi gerado, pago, e
o slide 4 caiu na `respiro` — que é cor chapada por definição. O sistema fez o
trabalho, cobrou por ele, e o render jogou fora **sem erro nenhum no log**.

> Isso não é questão de gosto, é **defeito de arquitetura**: quando existe foto
> feita sob medida pro assunto daquele slide, uma composição que não mostra foto
> está errada por construção.

`ctx["propria"]` diz se `fundos/NN.png` existe; havendo, as composições de
`_SEM_FOTO` saem da disputa. A `respiro` continua valendo pros slides sem imagem
própria — lá ela é quebra de ritmo, não desperdício.

**E o mesmo buraco existia em três outros lugares**, todos consertados junto: o
`checklist` e a `vitrine` chamavam `_fundo(plano)` **sem o número do slide** (e
sem o `n` a função nunca olha a pasta `fundos/`, só o acervo do nicho — foi por
isso que o checklist de mamadeira saiu sobre uma prateleira de potes); e os
**cinco modelos de fecho** nasceram sem foto, então a imagem do último slide não
era usada por nenhum. A camada agora é injetada no despachante `_html_fecho`,
o que cobre os cinco de uma vez e qualquer modelo novo que apareça.

**2. 🎬 O DIRETOR VISUAL — texto literal não basta.** Mandar a frase do slide
direto pro modelo de imagem funciona quando ela é concreta ("Confira o fluxo do
bico" → saiu bico e bebê mamando) e falha quando é abstrata:

    "Você provavelmente erra em dois passos todo dia"
          ↓ o modelo não tem o que fotografar
    um bebê num trocador — sem mamadeira, sem erro, sem nada do assunto

**Frase abstrata não é fotografável.** Alguém precisa decidir O QUE MOSTRAR
quando o texto não mostra nada, e esse alguém é uma chamada de **texto**
(`gemini-2.5-flash`), que custa uma fração de uma chamada de imagem. Uma
chamada só pro carrossel inteiro: mais barato, e o modelo vê os slides juntos,
então não repete o mesmo enquadramento em dois deles. Falhou? Cai no texto
literal, que é o que já existia.

⚠️ **E ela roda no `--seco` também.** Um `--seco` que mostra prompt diferente do
que vai rodar de verdade é pior que não ter `--seco`: aprova o que não testou.

**3. Checklist e fecho passaram a receber imagem.** Eu pulava os slides de
`itens` "porque usam fundo de ambiente" — uma exceção que reintroduzia
exatamente o defeito que o `--do-plano` existe pra matar.

#### ♻️ `--refazer` — o furo que fazia o conserto produzir o defeito (24/08)

⚠️ **O FLUXO QUE EU PROPUS NÃO FECHAVA, E O JEITO COMO ELE FALHAVA ERA O PIOR
POSSÍVEL.** O passo a passo era:

    --agora casa          → monta o plano A, renderiza
    fundo_ia --do-plano   → gera as imagens DO PLANO A  (pago)
    --agora casa          → monta o plano B ← e joga o A fora

O terceiro passo chamava o brain **de novo**, e o Gemini escreve outra coisa a
cada chamada — no teste do Dre o primeiro plano era uma comparação de torneira
com aquecedor e o segundo virou um `passo_a_passo` de outro assunto. As imagens
do plano A iriam parar num carrossel que fala do plano B.

> **O passo que existe pra casar imagem e texto produzia justamente o
> descasamento** — e ainda gastando dinheiro em imagem. E nada falha: sai um
> carrossel bonito, com fotos que não têm relação nenhuma. Mesma família do
> fundo por rodízio, com o agravante de que aqui a gente pagou.

`--agora <nicho> --refazer` lê o `plano.json` da pasta e renderiza em cima dele,
sem chamar o brain. O log diz quantas imagens por slide encontrou — e avisa
quando não encontrou nenhuma, que é o caso em que o `--refazer` não tem motivo
pra existir.

O ciclo certo, e ele agora tem os três passos com o mesmo padrão (sem caminho
escrito na mão):

    carrossel_agendador.py --agora casa            # plano + 1º render
    fundo_ia.py --do-plano --seco                  # confere os prompts
    fundo_ia.py --do-plano                         # gera (pago)
    carrossel_agendador.py --agora casa --refazer  # re-render COM as imagens
    midia_publica.py --ver                         # revisa

**E o preço saiu do prompt de imagem.** *"Torneira com aquecedor: R$126,35 vale
o dobro"* foi pro briefing da foto inteiro. Preço num prompt de imagem convida o
modelo a desenhar uma etiqueta com número — e número desenhado ou sai errado, ou
sai **certo e gravado no pixel**, que é pior: não dá pra corrigir quando a Shopee
mudar o valor. Preço tem lugar próprio, a pílula do render, onde é texto.

#### ⏰ COMANDO COM DATA NA MÃO TEM PRAZO DE VALIDADE (24/08)

O `--do-plano` falhou de novo, e desta vez o sistema estava **funcionando**. Eu
mandei rodar:

    .venv/bin/python fundo_ia.py --do-plano pronto_carrossel/20260823_manual_casa

Entre o comando que eu escrevi e a hora em que ele rodou, **passou da meia-noite
na VPS**. O render criou `20260824_manual_casa`, escreveu o `plano.json` lá
dentro certinho, e o meu caminho apontava pro dia anterior. Saiu "não achei
plano.json" e pareceu que o conserto não tinha funcionado.

⚠️ **E EU JÁ TINHA APRENDIDO ISSO.** O `midia_publica --ver` pega a pasta mais
recente sozinho **exatamente por causa desta armadilha**, e está anotado neste
arquivo. Não apliquei no comando novo. **Lição repetida é lição não aprendida** —
e a forma de não repetir não é lembrar, é fazer o padrão ser o certo:

- `--do-plano` **sem argumento** usa o carrossel mais recente.
- Apontando pra pasta errada, ele **diz onde o `plano.json` está de fato** em vez
  de só reclamar.

Regra geral pra qualquer comando que eu mandar daqui pra frente: **se o caminho
tem data, hash ou id dentro, o comando está errado.** O certo é ter um padrão
que o próprio programa descobre.

#### ✂️ A COMPOSIÇÃO TEM QUE CABER NO CONTEÚDO, NÃO CORTÁ-LO (23/08)

⚠️ **A `cheia` estava DESCARTANDO o corpo do slide.** Ela desenhava só rótulo +
título. Quando um slide de explicação caía nela, o `linha` que o brain escreveu
sumia sem erro nenhum: o slide dizia *"bebê em posição errada"* e não explicava
nada. O Dre viu no post publicado, e a regra que ele deu é a certa:

> *"quando o slide tiver que explicar um assunto, ele precisa sim ter mais
> palavras e explicações; agora se for uma dica, pode conter menos texto, ou
> quase nada. Tudo depende do contexto."*

Duas mudanças: a `cheia` passou a renderizar uma frase de apoio, e **um slide
com mais de 16 palavras de corpo não é mais elegível pra ela** — vai pra uma
composição com área de leitura. O teto de palavras do brain (`PALAVRAS_CORPO`)
não estava errado; errado era o layout jogar fora o que ele produzia.

#### 🎯 DOUTRINA DE FORMATOS — o que o Dre trouxe (23/08)

Ficam registrados aqui porque são decisão de produto, não de código, e a próxima
sessão não pode perder isso.

**A cadeia que o Jarvis deveria percorrer** (hoje ele pula direto pro formato):

    OBJETIVO → FORMATO → NARRATIVA → VISUAIS → CTA

| objetivo | formato |
|---|---|
| venda | Problema → consequência → solução → prova → produto |
| alcance | Erros / curiosidade |
| seguidores | Série educacional recorrente |
| comentários | Comparação / opinião |
| saves | Checklist / guia |
| shares | Identificação ("manda isso pra quem...") |

⚠️ **E AQUI TEM UMA DESCOBERTA QUE MUDA A PRIORIDADE.** O carrossel de
referência que o Dre gerou **não tem produto, nem preço, nem link** — são 4
dicas e uma pergunta. É carrossel de SEGUIDOR, não de venda. E a meta agora é
1.000 seguidores (é onde o afiliado da Shopee abre no Reels). Ou seja:

> Até os 1k, o objetivo é **seguidores**, não vendas. E carrossel sem produto
> não tem a foto branca da Shopee que estraga o design. **O problema estético e
> o problema estratégico têm a mesma solução.**

Nossos formatos `lista`/`comparacao` (com preço em cada slide) estão empurrando
pro objetivo errado nesta fase. A distribuição 40/20/15/10/10/5 foi calibrada
pra VENDA; enquanto a meta for seguidor, `erros` + `checklist` + `passo_a_passo`
deveriam pesar mais.

**Formatos novos que valem entrar** (do ranking do Dre):
- **"Não compre antes de saber isso"** — junta viral + venda + save. É o que ele
  mais destacou pra TopShop.
- **Checklist** — o monstro dos salvamentos. O último slide tem que ser
  literalmente construído pra alguém pensar "vou salvar isso". Já temos a
  composição (`checklist`); falta o formato no brain.
- **Série recorrente** — "5 coisas simples que deixam qualquer *cômodo* mais
  bonito", repetido variando o cômodo. A pessoa não segue pelo post, segue pelo
  PRÓXIMO. É o motor de seguidor mais barato que existe e não precisa de
  código novo, só de um campo `serie` no plano.
- **Regra de ouro do hook:** proibir começar com `COMPRE ESSE ORGANIZADOR 😱`.
  Primeiro conteúdo, depois produto — o produto entra como resolução da
  história, não como propaganda do slide 1.

**Tipos visuais ainda não implementados** (a lista dele é maior que a nossa
biblioteca): antes×depois em tela dividida, comparação lado a lado, setas e
marcações apontando o detalhe, POV/perspectiva incomum, sequência de
transformação. A `metade` já tem CSS pronto pro lado-a-lado; falta a composição.

#### Ainda falta
1. ~~Ciclos e horários no `daemon_maestro`~~ ✅ feito
2. **Ligar** (`carrossel_ligado: true`) depois de olhar alguns prontos.
2. **Cruzar o ledger com as métricas** — o `carrosseis_ledger.jsonl` guarda o
   formato, mas quem mede alcance/salvamento é o `metricas_posts`. Falta juntar
   os dois pelo shortcode pra fase 2 ligar sozinha.
3. **Story (depois do carrossel, decisão do Dre)** — e o mais barato já está
   pronto: o `.mp4` do Reel que a conta acabou de postar está no disco e tem
   menos de 60s, então `--story` o republica com **zero** render e **zero**
   infra nova.

---

### 📱 WHATSAPP: HORÁRIO SORTEADO E VOLUME DOBRADO (24/08)

Pedido do Dre: *"os horários estão sempre fixos, eu queria que fosse mais
aleatório, e que ele dobrasse as postagens"*.

⚠️ **O DEFEITO NÃO ESTAVA NO `whatsapp_playwright.py`.** Ele nunca soube QUANDO
rodar — só checava a janela (07–21h) e os tetos. Quem escolhia a hora era o
**cron da VPS**, e cron é fixo por definição: `0 9,13,18 * * *` dispara às
9:00:00, 13:00:00 e 18:00:00, todo dia, no segundo.

> ⚠️ **E isso é exatamente o "padrão de robô" que o cabeçalho do arquivo diz ser
> o que derruba número — mais até que o volume.** Pessoa nenhuma manda mensagem
> no mesmo minuto todo dia. Antifraude não precisa de IA pra ver isso, só de um
> `GROUP BY minuto`. Ou seja: **o pedido do Dre reduz risco, não aumenta.**

O conserto não é "cron aleatório" (cron não sorteia) — é **inverter quem manda**.
O cron passa a acordar de 15 em 15 minutos e PERGUNTAR se é hora; quem responde
é o módulo, com uma agenda sorteada **uma vez por dia** e guardada no estado.
Mesmo desenho do `carrossel_agendador`, pelo mesmo motivo.

    .venv/bin/python whatsapp_playwright.py --agenda   # vê o dia, não envia
    */15 7-21 * * *  .../whatsapp_playwright.py --auto  # o cron novo

**Três decisões que o teste de 30 dias justificou:**
- **Sorteio por FAIXA, não uniforme.** 12 pontos uniformes numa janela de 15h
  juntam dois a 3 minutos de distância com frequência alta — e duas mensagens
  coladas chamam mais atenção que horário fixo. Um ponto por faixa + jitter, com
  piso de `WHATSAPP_GAP_MIN` (35 min). Medido: menor intervalo 35 min, maior 123.
- **Sorteada 1× e GUARDADA.** Se cada acordada tirasse dado novo, dois horários
  cairiam colados ou o dia passaria em branco — e o teto/dia deixaria de
  significar algo. Guardada, a agenda é um fato do dia: dá pra ver de manhã o
  que vai sair. Em 30 dias simulados, **0 agendas repetidas**.
- **Tolerância de 16 min, não igualdade.** O cron de 15 em 15 nunca cai no
  minuto exato do sorteio; sem folga, TODO slot seria pulado e o WhatsApp nunca
  mandaria nada.

⚠️ **O slot só é marcado como usado DEPOIS do envio dar certo.** Marcar antes
perderia o horário quando a sessão estivesse caída — e o dia terminaria abaixo
do teto sem ninguém saber por quê. Falhando, o slot segue vencido e a próxima
acordada tenta de novo dentro da tolerância.

**Volume:** `WHATSAPP_MAX_DIA` 6 → 12 é uma linha no `.env`, não código.

⚠️ **E O `--auto` MANDA UMA POR SLOT, NÃO `MAX_RODADA`.** Peguei isso só quando
o Dre mostrou o `crontab -l` — a linha antiga era `0 9,14,19` (3 rodadas × 2
mensagens = os 6/dia). Se o `--auto` herdasse esse 2, seriam **12 horários × 2 =
24 tentativas contra um teto de 12**: os 6 primeiros slots gastariam o dia
inteiro e **a noite ficaria vazia** — o espalhamento que este código existe pra
criar morreria na primeira tarde, e o log não acusaria nada além de "teto do dia
atingido". `MAX_RODADA=2` foi feito pro modo de 3 disparos, onde mandar 2 de uma
vez era o único jeito de chegar a 6. Aqui a conta é outra: **1 × N horários = N**.

⚠️ **E A JANELA RECUA ATÉ ONDE O CRON ALCANÇA (`WHATSAPP_CRON_MIN`).** Com
`*/15 7-21` a última acordada é **21:45**; um slot sorteado às 21:52 não seria
alcançado por acordada nenhuma. O dia terminaria com 11 em vez de 12 — todo dia
em que a última faixa caísse ali — **sem erro nenhum no log**. Achei simulando
as acordadas do cron contra cada minuto da janela, não esperando acontecer:

    minutos que NENHUMA acordada alcança: 21:46 … 21:59

Agora `fim = HORA_FIM*60 + (59 - CRON_MIN)` = 21:44, e 300 dias sorteados dão
**0 slots inalcançáveis**. ⚠️ **Se um dia o `*/15` do crontab mudar, mude o
`WHATSAPP_CRON_MIN` junto** — são o mesmo número em dois lugares, e é o tipo de
par que se separa em silêncio.

O crontab velho, pra referência (e ele fica com uma linha só):

    ANTES  0 9,14,19 * * *   whatsapp_playwright.py
    DEPOIS */15 7-21 * * *   whatsapp_playwright.py --auto

⚠️ **E o `crontab -l` está com o cabeçalho do `setup_cron_jarvis.sh` repetido
seis vezes** — o script vem re-anexando o bloco de comentários a cada execução
em vez de substituir. Não quebra nada (são comentários), mas o arquivo já está
com mais comentário duplicado do que cron, e um dia isso esconde uma linha de
verdade. Anotado; não mexido.

### 🐾 A CONTA PET NUNCA POSTOU — e o vigia não sabia dizer por quê (25/08)

O Dre trouxe o alerta: `[publicado] @topshoppet_: NENHUM post nos últimos
3 dia(s)`. A conta existe, o vigia a enxerga, e ela nunca publicou nada.

**Onde a resposta estava escrita o tempo todo:** em `daemon_maestro.py:795`,
num comentário meu de 11/08:

> ⚠️ CONTA COM `"ativa": false` FICA DE FORA (…). Quando o Dre zerou
> `producao_minima_por_conta` pra drenar a esteira, `moda` e `pet` (cadastradas
> no dia anterior, sem postar ainda, estoque 0/6) viraram as ÚNICAS contas com
> `falta > 0` — a produção inteira passaria a servir duas contas que não
> publicam. **Cadastrar a conta e ligar a produção dela são duas decisões
> diferentes.**

Fechei a hipótese: `pet` está `"ativa": false` desde 11/08 e nunca foi religada.

### ❌ E A HIPÓTESE ESTAVA ERRADA — a medição derrubou (25/08)

Rodado na VPS, `pet` veio **`ativa: sim`, 4 pacotes PRONTOS, último post
06/08** — 19 dias, não 3. A causa que eu tinha achado documentada era a causa
**antiga**: em algum momento pet foi religada, a produção voltou a servi-la, e
o pacote passou a ser feito e a não sair.

📌 **A explicação plausível e a explicação verdadeira se pareciam demais.** Eu
tinha um comentário meu, datado, descrevendo exatamente o sintoma — e isso é
justamente o que torna o chute perigoso: ele vem com prova. O que derrubou não
foi raciocínio melhor, foi rodar contra o estado real.

**O quadro que apareceu:**

    nicho    ativa   fila  prontos   último post
    geral    sim   11+13?      427    2026-08-24
    beleza   sim      29        0     2026-08-24
    tech     sim      52        0     2026-08-25
    casa     sim      58        1     2026-08-24
    pet      sim       6        4     2026-08-06   ← 19 dias
    moda     sim      32        1     2026-08-25

**E o "427 em geral" era artefato do MEU diagnóstico**, não um fato: eu chutava
o nicho pelo nome da pasta e o *default do chute era `geral`*. Todo pacote sem
nicho no nome caía ali. A verdade mora no `pronto_para_postar/<slug>/conta.json`
— exatamente de onde o daemon lê (`_conta_do_slug`).
📌 **Número cujo default é o próprio valor reportado não é medição, é eco.**

**A causa real, lendo `ciclo_postagem`:** `post_por_conta` é **opt-in**.
Desligado, o daemon posta **1 pacote por slot no total** — `prontos[0]` — e
conta nenhuma tem vaga reservada. Com a esteira funda e a drenagem por idade
(`_prontos_nao_postados`, que com fila funda inverte pra FIFO), quem tem
estoque pequeno **nunca alcança a frente**. Pet tem 4 pacotes atrás de
centenas. Não é token vencido nem conta desligada: **é fome**.

⚠️ E tem o agravante dos **órfãos**: pacote sem `conta.json` legível devolve
`"?"` no `_conta_do_slug`. No modo balanceado todos eles contam como UMA conta
só e sai um por slot; no clássico, sendo os mais velhos, a drenagem por idade
os põe na frente e eles comem o slot de quem tem pouco. Pacote órfão não tem
destino — envelhece até o expurgo por validade.

Por isso o `diag_contas.py` agora separa quatro estados que de fora parecem o
mesmo "a conta não posta" e pedem ações **opostas**: desligada / sem insumo /
com fome / órfã.

### ❌❌ E A FOME TAMBÉM CAIU — terceira medição (25/08)

Lendo o `conta.json` de cada pacote em vez de chutar pela pasta:

    postagem: 1 POR CONTA por slot (balanceado)  ·  teto 3  ·  validade 7d

    nicho    ativa   fila  prontos  +velho   último post
    geral    sim   11+13?     143     27d    2026-08-24
    beleza   sim      29       84     27d    2026-08-24
    tech     sim      52      116     27d    2026-08-25
    casa     sim      58       80     21d    2026-08-24
    pet      sim       6        0      -     2026-08-06   ← ZERO pacotes
    moda     sim      32       10      4d    2026-08-25

O rodízio **está ligado**, então fome não explica nada. E pet tem **0 pacotes**
— os "4" da rodada anterior eram o chute pelo nome da pasta. **Pet não deixa de
postar: pet não tem o que postar.** O problema é PRODUÇÃO, e sempre foi.

📌 **Três rodadas, três causas diferentes, e as duas primeiras foram invenção do
próprio instrumento.** Cada versão do diagnóstico produziu um culpado plausível
e distinto. Ferramenta de medição errada não fica calada — ela responde, com
convicção, o que você perguntou errado.

**O que a terceira rodada expôs de verdade, e não é pequeno:**

⚠️ **`validade 7d` e o pacote mais velho com 27d, em todas as contas.** O
`_prontos_nao_postados()` **descarta pacote vencido**, e o `_estoque_por_conta()`
conta só o que sobra dali. Ou seja: as centenas de pacotes no disco podem estar
**invisíveis pro daemon**. Quem olha `ls` vê estoque; quem lê o log vê esteira
vazia. E o comentário do próprio `_prontos_nao_postados` raciocina com validade
**27** — o 7 pode ser o default de uma chave que ninguém escreveu.
📌 **Contar pasta não é contar esteira.**

**O que entrou no diagnóstico por causa disso:**

- coluna **`vivos`** ao lado de `pastas` — o que o daemon realmente enxerga,
  pela mesma regra (não postado + dentro da validade)
- a validade agora imprime **`(DEFAULT, chave ausente)`** quando é o default.
  Mesmo erro do `geral`: valor igual ao default não é leitura, é silêncio
  disfarçado de resposta
- a **fonte da fila**, porque `_carregar_produtos_para_produzir` lê o
  `validacao_fila.json` (só `mina_ouro`/`ok`) e só CAI no `produtos_fila.json`.
  Eu contava o segundo e reportava "6 produtos de pet na fila" sobre um arquivo
  que a produção talvez nem consulte
- classificação pelo campo **`produto`** e não `campeao`, porque é o que a
  produção monta (`{"nome": p["produto"]}`) — com uma checagem separada que
  mede a divergência entre os dois. Testei: o keyword list cobre "comedouro" e
  "arranhador", então **essa divergência não se confirmou**. Fica o instrumento.

**Próximo passo:** rodar a v3 na VPS. As perguntas que ela responde: pet tem
candidato no `validacao_fila.json` (não no produtos_fila)? Quantos pacotes estão
vivos de verdade? A validade é 7 escolhido ou 7 por omissão?

### 🚨 A VALIDADE É 27 — e meu "7 por omissão" quase custou 184 pacotes (25/08)

Resposta da pergunta acima, vinda do log do daemon: **nenhuma das duas.**

    🗑️  8 pacote(s) além de 27 dias → fila_vencida/

`DEFAULTS["fila_validade_dias"] = 27`, e `carregar_config()` **mescla o arquivo
por cima do DEFAULTS**. Eu lia o `agendador_config.json` cru, não achava a
chave, e aplicava um default meu de 7.

📌 **Ler o JSON cru é ler metade da config.** A maioria das chaves nunca é
escrita no arquivo — vive só no `DEFAULTS`. Quem lê o arquivo e aplica um
default próprio descreve uma configuração que não existe em lugar nenhum.

📌 **Default inventado é pior que default ausente.** O ausente dá erro; o
inventado dá um número plausível e errado. E aqui o número plausível
**autorizava uma operação irreversível**: o `limpar_esteira --aplicar` com corte
de 7 teria tirado da esteira **184 pacotes que o daemon considera postáveis**.

**Três coisas que eu afirmei e estavam erradas:**

| eu disse | verdade |
|---|---|
| "esteira 90% morta, 43 vivos de 433" | ~220 vivos; o corte de 7 é que matava no papel |
| "o expurgo do daemon não está rodando" | está — o log mostra ele movendo por 27d |
| "184 pacotes de produção desperdiçada" | são vivos; o desperdício real é bem menor |

**O que sobrou de achado verdadeiro, e não é pouco:** **206 pacotes JÁ POSTADOS
continuam na esteira.** O `_expurgar_vencidos()` filtra por **idade**, não por
já ter cumprido a função — então o pacote postado só sai quando envelhece 27
dias. Metade da esteira é material que já foi ao ar.

**O `limpar_esteira.py` foi refeito em cima disso.** Agora são **quatro montes**,
não dois, porque as razões pedem conversas diferentes:

- **postado** — lixo natural, e o buraco que ninguém tapava
- **vencido** — passou dos 27d sem ir ao ar; é a produção desperdiçada de verdade
- **editorial** — VIVO pro daemon, mas além do corte que o Dre pedir (`--dias`)
- **vivo** — fica

⚠️ O corte editorial é **opt-in via `--dias`, nunca herdado de default**. Tirar
material que o daemon ainda considera bom é decisão de conteúdo, não manutenção
— e foi assumindo um default meu que eu quase apresentei 184 pacotes vivos como
lixo, com o Dre prestes a confirmar achando que confirmava um diagnóstico.

E as duas ferramentas agora leem a validade de `daemon_maestro._validade_dias()`.
Se não conseguirem importar o daemon, **param e dizem** — não chutam um corte
para mover pasta de produção.

**A armadilha estrutural, que é o que importa aqui:** `"ativa": false` é
INVISÍVEL em toda ferramenta que não seja o daemon. Varri o repo inteiro: o
campo tem **um único leitor em produção**, o `_nichos_das_contas()`. O vigia lê
o `contas.json` todo e reporta a conta como parada; a produção filtra e pula.
As duas estão certas — só que uma diz "a conta existe e está parada" e a outra
nunca soube que devia produzir. Quem lê os dois relatórios conclui que há um
bug, e não há.

⚠️ E note o efeito colateral: `ativa` bloqueia só a PRODUÇÃO, não a postagem.
Se existisse pacote pronto, ele sairia. Não sai porque nunca foi feito.

**`diag_contas.py`** — novo, responde "em que ponto da esteira a conta parou"
sem chute. Uma linha por conta: `ativa`, produtos na fila, pacotes prontos,
último post — e uma seção "o que está travando" que nomeia a causa (desligada /
sem insumo / encalhada na postagem).

    .venv/bin/python diag_contas.py
    .venv/bin/python diag_contas.py pet

Quatro decisões que valem mais que o script:

1. **Reusa `roteador_contas`, não reimplementa.** Duas regras de "que nicho é
   este produto" divergem com o tempo e o diagnóstico passa a descrever um
   sistema que não existe.
2. **Mas NÃO chama a IA.** `nicho_do_produto()` cai no Gemini quando nenhuma
   palavra-chave bate. Rodar um diagnóstico não pode custar uma rajada de
   chamadas pagas sobre a fila inteira — uso palavra-chave (grátis, idêntica à
   produção) e só LEIO o cache que a produção já gravou. O resto vira `+N?`.
3. **Os indefinidos entram no `geral`.** Sem isso o script gritava "geral sem
   produto na fila" — acusando de fome exatamente a conta que come as sobras.
4. **Conta inexistente não pode dar ✅.** `diag_contas.py pet` numa máquina cujo
   `contas.json` não tem pet agora fala isso em voz alta e sai com código 1.
   Tabela vazia + "nenhuma conta parada" vira "está tudo bem" na cabeça de quem
   lê — a pior resposta possível pra pergunta feita.

**Erro que eu cometi escrevendo e peguei rodando, não lendo:** procurei o nome
do produto em `item["nome"]`. O item da fila não tem `nome` — tem `produto`
(termo de busca) e `campeao` (nome real), e o sistema inteiro lê
`campeao or produto`. Resultado: 24 de 24 produtos "indefinidos" e o
diagnóstico acusaria fila vazia em TODA conta. Um diagnóstico errado é pior que
diagnóstico nenhum, porque ele encerra a investigação.
📌 **Erro de campo é erro silencioso: não estoura, só zera.** Ferramenta nova
tem que ser rodada contra dado real antes de virar fonte de verdade.

⚠️ O `contas.json` do repo tem 4 contas (`geral`, `beleza`, `tech`, `casa`) — o
da VPS tem 6. **O diagnóstico só vale rodado na VPS.**

### 🐾 A CAUSA DO PET, no fim: não há de onde tirar vídeo (25/08)

Quatro hipóteses minhas caíram antes desta. A resposta estava num arquivo que
ninguém sabia que existia:

    🌐 APIs: Pexels ❌ (sem PEXELS_API_KEY), Pixabay ❌ (sem PIXABAY_API_KEY)
    📊 Score após ciclo: 0/100 (objetivo: 60)
    Status: sem_assets → sem_assets

**Como os outros nichos produzem, então?** `orchestrator.py:320`:

```python
video_ja_pronto = fonte == "hunter" and produto.get("video_path")
```

Produto vindo do **hunter já chega com vídeo**. Todo o resto depende do
`asset_autopilot_agent` buscar B-roll de banco — e o projeto não usa banco de
vídeo, por decisão do Dre. Os 2 produtos de pet não vêm do hunter. **Não existe
caminho pelo qual eles possam virar vídeo.**

Então a cadeia inteira estava certa e o sistema mentiu em dois pontos:

**1. `❌ erro técnico — seguindo pro próximo`.** A saída da etapa ia inteira pro
`.log` em disco e NADA dela ia pro journal. Quem investigava lia "erro técnico"
e não tinha para onde ir.
📌 **Erro escrito só em disco é erro invisível** — quem investiga lê o journal,
não `outputs/<data>/run_<hora>/<slug>/tentativa_N/`.
→ `rodar_etapa` agora despeja as últimas 12 linhas da etapa que falhou.

**2. `não há produto desses nichos na fila`.** Impressa sempre que sobrava
QUALQUER déficit, inclusive quando parte tinha acabado de ser atendida. `pet:4`
com alvo 6 significa que **2 produtos de pet foram escolhidos** — o log dizia o
oposto e me mandou investigar a coleta, que estava perfeita.
📌 **Mensagem de log que descreve a causa errada é pior que log nenhum: não
deixa a investigação em branco, manda ela pro lado oposto.**

**3. E ninguém lia o próprio estado.** O `production_runner_agent` gravava
`status="erro"` a cada falha e a seleção nunca consultava isso — os mesmos 2
produtos impossíveis eram escolhidos ~130 vezes por dia, por semanas.
→ `_em_quarentena()`: **cooldown de 24h, não banimento**. Falha transitória se
cura sozinha no dia seguinte; o produto impossível queima 1 ciclo por dia em vez
de 130. Banir de vez exigiria acertar de primeira a diferença entre "impossível"
e "deu ruim agora", que é o que ninguém sabe no momento da falha.

**Decisão do Dre:** pet volta pelo **carrossel**, que não precisa de B-roll —
usa a biblioteca de fundos + foto do produto, ambas prontas. A fonte de vídeo
para pet fica para depois.

### ↩️ E EU TIVE QUE ESCREVER O DESFAZER (25/08)

O `limpar_esteira.py` com o corte errado de 7 dias mandou **410 pastas / 5,1 GB**
pra `fila_vencida/` — 206 já postadas (certo) e ~184 que o daemon considerava
postáveis (erro meu). O Dre pediu a volta.

`restaurar_esteira.py` devolve só o que foi levado por engano: não postado e
dentro da validade real. O que salvou a operação: **`shutil.move` no mesmo
filesystem é um rename, então o mtime foi preservado** — a idade de cada pacote
continua sendo a real. Se o mtime tivesse sido reescrito, tudo voltaria "novo" e
a validade do daemon passaria a mentir por mais 27 dias.

⚠️ Ele tira o sufixo de desambiguação antes de comparar com o histórico de
postados; sem isso um pacote postado voltaria como se nunca tivesse ido ao ar.

### 🎠 O CARROSSEL VIROU PUBLICÁVEL — quatro defeitos, um deles invisível (26/08)

Revisão externa nos três nichos completos apontou quatro coisas. Três eram
Brain; a quarta não era defeito de código nenhum — era código que **nunca era
alcançado**.

**1. A biblioteca de formatos estava desligada.** `montar_plano` chamava
`existentes(nicho)` **sem o formato**, que lê só a raiz: 10 imagens genéricas.
As 100 por nicho em `fundos/<nicho>/<formato>/` — três dias de geração — nunca
foram consultadas.
📌 **Trabalho que o sistema não consulta é trabalho que não existe, e ele não
avisa: só fica pior do que poderia, em silêncio.** A crítica chegou como
julgamento estético ("imagem bonita de Casa em vez de imagem que representa
esta frase") e era literalmente isso — sem o formato, a única coisa ligando
imagem e frase era a pasta.

**2. E o meu primeiro conserto não bastou.** Passei o formato, mas o brain
**pré-atribuía** `s["fundo"]` embaralhando o acervo — e `_fundo()` usa esse
valor com prioridade. A busca semântica (`combinar`) e o roteamento por papel
já existiam no `slides_html` e **nunca rodavam** para capa, quebra e resumo.
Agora: semântica primeiro, sorteio como desempate, variedade preservada.
📌 Duas soluções boas podem se anular: a de cima não sabia que a de baixo
existia.

**3. Promessa ≠ entrega.** A capa dizia "5 produtos" e o carrossel entregava 3,
porque o ângulo usava `quantos` (o que o formato pede) e não o que a fila deu
com foto. Travado em dois pontos: a origem usa a contagem real, e
`_casar_promessa` reescreve o número da capa se ainda divergir.
📌 **Regra que só existe no prompt é pedido, não garantia** — terceira vez que
anoto isso; o `CTA_PADRAO` ensinou primeiro.

**4. Slide 2 virava segunda capa.** A regra do Dre de 22/08 (a quebra aumenta a
tensão sem entregar a resposta) continua valendo — o que ela não pode é trocar
o assunto ou anunciar outra contagem. Reconciliado, não substituído.

**`qa_foto.py`** fecha o último: a foto de catálogo com "Cor Exclusiva", selo,
ícones e marca da loja cravados nos pixels. Nenhum CSS conserta, então o
sistema **troca de produto** em vez de tentar salvar a imagem.
⚠️ Três decisões que sustentam isso:
- **O modelo diz o que VÊ; o placar é código.** Perguntar "nota de 0 a 10"
  devolve número que muda de humor e não se audita. A visão responde só fatos
  observáveis; os pesos moram em `PESOS`, em Python, ajustáveis sem tocar em
  prompt.
- **Aprova na dúvida.** Sem `GEMINI_API_KEY`, ou com a API fora, ele passa
  tudo. Reprovar quando não sabe pararia a esteira das seis contas em silêncio.
- **Só troca quando sobra substituto.** No fim da lista, foto poluída ainda é
  melhor que carrossel entregando menos do que prometeu.

Placar medido: catálogo poluído **-6** (reprova), pessoa usando o produto
**+5** (passa).

**Estado da biblioteca (27/08): COMPLETA.** 620 imagens indexadas nos seis
nichos, organizadas por formato. As descrições do índice confirmam cada pasta —
`pet/erros` tem gato arranhando sofá e ração derramada, `geral/antes_depois` tem
dois celulares (um quebrado, um novo), `moda/cta` tem mulher recusando camiseta
com X vermelho.

**Como os 66 lotes foram rotulados sem abrir 66 folhas de contato:**

1. `--casar-lotes` reconheceu 27 por **identidade** — dHash contra o acervo já
   organizado. Não é palpite: é a mesma imagem.
2. `--sugerir-lotes` palpitou o resto por **assinatura visual**, com as
   definições de formato tiradas das descrições que o `--indexar` já tinha
   gerado. `cta` virou "X vermelho, expressão de recusa" porque é isso que o
   acervo mostra, não porque o nome sugere.
3. O relatório trouxe **o que o modelo viu** na mesma chamada, o que reduziu
   22 decisões em branco a 22 conferências de sim/não.
4. A **checagem de colisão** apontou 11 formatos reivindicados por dois lotes —
   coisa que o modelo não pode ver, porque avalia um lote por vez.
   📌 A checagem que a IA não consegue fazer é a que não precisa de IA: é
   contagem. Confiança alta em cada peça não garante consistência do conjunto.
5. E o **reenquadramento que fechou o dia**: colisão só é grave quando o NICHO
   está errado. Moda dentro de pet envenena a busca semântica; dois lotes no
   mesmo formato do nicho certo só deixam a pasta com 20 imagens em vez de 10 —
   isso é sobra, não defeito. Com isso, os 11 conflitos viraram 4 nichos
   trocados, todos denunciados pela hora do arquivo.

### 🏷️ 30 IMAGENS DE MODA ENTRARAM COMO PET (27/08)

O `--rotular` foi rodado com `erros=45,curiosidade=46,comparacao=47` — números
que **eu escrevi como exemplo, dentro de um bloco de comando**. O Dre rodou, com
razão: estava executável e com valores concretos. Os lotes 45-47 são a
continuação de MODA, e araras, closets, tênis e blazers viraram `pet/`.

📌 **QUARTA VEZ HOJE que um placeholder meu virou comando.** As três primeiras
só deram erro na tela (`...` inválido, JSON colado no shell). Esta escreveu
dado errado no disco, com o carrossel JÁ LIGADO — a @topshoppet_ ia puxar foto
de closet.
📌 **Regra nova: quando eu não sei os valores certos, a forma do comando vai
FORA de bloco executável, e eu digo explicitamente o que falta.** Bloco com
número concreto é uma instrução para rodar, não uma ilustração.

⚠️ E o estrago não parava no disco: o `--indexar` já tinha descrito as 30, então
a busca semântica passaria a responder "closet organizado" para um slide sobre
cachorro — **com confiança**, porque o índice não sabe que está errado.
📌 **Importar para o lugar errado é pior que não importar:** a ferramenta diz
"✅ 30 importadas", tudo parece ter dado certo, e o defeito só aparece semanas
depois como "por que esse carrossel tem foto estranha?".

**`--esquecer <nicho>/<formato>`** desfaz: tira os arquivos, tira as entradas do
índice e limpa o rótulo no `lotes.json` — esse último porque sem ele o próximo
`--aplicar-lotes` reimportaria o mesmo erro, calado. Mexe no índice ANTES dos
arquivos: se falhar no meio, é melhor sobrar arquivo sem descrição do que
descrição apontando para arquivo que não existe.

Nada irrecuperável: os PNGs originais seguem em `~/fundos` e o `lotes.json`
guarda o caminho de cada um. O que sai é a cópia convertida, não a fonte.

**E as descrições do índice deram o rótulo certo de graça:** lote-46 era um item
por foto com fundo limpo (`moda/produto`), lote-47 era incômodo + o que resolve
(`moda/problema_solucao`). Quem descreveu as imagens erradas foi quem apontou
onde elas deviam estar.

### 💸 O SLIDE DE RESUMO GERAVA IMAGEM SOBRE NADA (27/08)

Primeira rodada do `completar_fracos` no pet, com a geração ligada:

    slide 02 · força 0 · A gente faz por amor, mas *eles sofrem*
    slide 06 · força 0 ·
    slide 03 · força 1 · Forçar abraços e beijos

O título em branco no slide 06 era o sintoma. **O slide de resumo não tem
`titulo` nem `linha` — tem `itens`**, e eu montava o assunto só dos três
primeiros campos. Sobrava o rótulo "SALVA ISSO", que não casa com nada: força
0, e o prompt saía **vazio**. Uma imagem paga gerada a partir de nada, em todo
carrossel, para sempre.

O `do_plano()` já tratava `itens` desde o dia em que o checklist de mamadeira
saiu sobre potes de cozinha. Eu não reusei a regra dele.

📌 **Custo que nasce de um campo esquecido não aparece como erro:** a imagem é
gerada, o slide fica bonito, e ninguém liga o gasto à causa. Só apareceu porque
o log imprime o título e ele veio vazio.

### 🎠 O CARROSSEL ESTREOU — e a chamada dele se apagava a cada deploy (29/08)

O carrossel nunca postou desde que foi construído. `carrossel_ligado: true` no
config, agenda correta, módulo funcionando — e nenhuma linha de log em lugar
nenhum, porque **o código não existia pra falhar**.

A chamada a `carrossel_agendador.ciclo()` não morava no `daemon_maestro.py`. Ela
era INJETADA por `patch_carrossel_daemon.py` direto em
`agents/daemon_maestro.py` — que é exatamente o arquivo que o deploy sobrescreve
(`git show FETCH_HEAD:daemon_maestro.py > agents/...`). Medido: `grep -c
carrossel agents/daemon_maestro.py` deu **0**; depois do conserto, 9.

📌 **Patch aplicado no destino do deploy é patch com data de validade.** Se a
chamada precisa sobreviver, ela nasce no arquivo versionado.

Às 15:30 do mesmo dia: `🎠 slot 15:30: 6 publicado(s)`, zero falha, 13 imagens
geradas no total.

### 🚨 EU AFIRMEI CINCO VEZES ANTES DE MEDIR (29/08)

O dia começou com "nenhuma conta postou reels". Errei a causa cinco vezes:

1. limite da Graph API da Meta — era o limite do CHAT, o Dre esclareceu
2. `ciclo_producao` estourando e matando `ciclo_postagem` — o log mostrou a
   postagem rodando às 09:05, refutado
3. ranqueei a fila do grupo com dados de teste que eu inventei — os 54 itens
   reais tinham `classe` vazia, o commit era inerte
4. descartei o "TopShopToday" como artefato do Telegram porque `grep Today` não
   achou nada no render — o grep estava certo e a conclusão errada: o texto
   estava dentro da imagem gerada
5. `float(p["preco"])` na faixa de preço — estourou em `'R$ 139,80'`

E os Reels nunca tinham parado: 5/5 no Instagram às 09:00. Era sábado, não
quinta, e sábado tem um slot só.

📌 **Meu grep de diagnóstico escondeu o erro que eu procurava.** Filtrei por
`💸|🔢|🚫|🎬|🎨` e um traceback não tem nenhum desses emoji. Quem rodou sem o
filtro foi o Dre.

### 💰 A FILA NÃO TINHA NÚMERO NENHUM — e ninguém sabia (29/08)

O `postar_grupo` cortava `novos[:quantos]` na ordem da fila, apoiado num
comentário que dizia "a fila já vem mais novo primeiro". As duas metades estavam
erradas: `piloto.py` documenta `fila.insert(0, …)` ~11x/dia e `repescagem.py`
faz `append` no outro extremo — o topo é quem chegou por último. E novidade não
é qualidade.

Ordenar não adiantou: **dos 54 disponíveis, 54 sem classe.** O
`telegram_repurpose_hunter` gravava `classe: ""` e descartava vendas, rating e
comissão — que vinham na MESMA resposta da API de afiliado que ele já buscava
pra pegar a foto, e só quando faltava foto.

Depois do conserto + `enriquecer_fila.py`: **45 mina_ouro, 100 ok, 81 fraco.**

📌 **Campo que a API já devolve e o gravador não guarda é dado que custou a
chamada e vai fazer falta numa decisão que ninguém liga a esta linha.**

### 🔌 CINCO CAMADAS ATÉ A CAUSA: por que 36 posts/dia não fechava (29/08)

Pergunta do Dre: "36 por dia no grupo, dá?". A resposta desceu camada por
camada, e cada uma parecia ser a resposta:

1. o cron entrega 14/dia → não é ele, a fila repõe 16/dia
2. dos 16, só 8,3 prestam → não é qualidade, é volume de origem
3. o volume não cresce porque o hunter gira uma lista fixa de canais
4. a lista é fixa porque a descoberta de canais **nunca rodou uma vez sequer**
5. e ela nunca rodou porque faltava um login de dois minutos

O `descobridor_grupos` falhava **três vezes por dia, todos os dias**, com
`Please enter your phone (or bot token)` seguido de EOF: Telethon sem sessão,
caindo no login interativo dentro de um daemon. Custo: `grupos_descoberta_max:
5` × 3 horários = **até 15 canais/dia** que nunca entraram.

O hunter escondeu o problema porque **não depende disso** — ele lê as prévias
públicas do t.me por HTTP e nunca precisou de login.

📌 **O sintoma não era "descoberta com erro", era A FILA NÃO CRESCER** — a três
camadas de distância, sem nada no log ligando as duas coisas.

### 🎨 MANDAR MANCHETE PRO GERADOR FAZ ELE DESENHAR MANCHETE (29/08)

O slide 02 do carrossel de `casa` saiu com **"TWO WAYS TO DOCUMENT THE EARLY
YEARS"** queimado no pixel, em inglês, atravessando o cabeçalho de um post em
português.

`prompt_do_slide` já pedia "sem nenhum texto, sem palavras, sem letras". Não
adianta: o `completar_fracos` mandava o TÍTULO do slide como assunto, e quando o
assunto é uma frase de manchete, desenhar a manchete é a leitura mais óbvia do
pedido. O `do_plano` já traduzia cada frase numa cena via `_direcao_visual`;
este caminho — o que o carrossel usa de verdade — pulava a etapa.

📌 **A correção não é pedir mais forte pra não escrever; é parar de mandar texto
que pede pra ser escrito.**

### 💸 R$ 54,98 AO LADO DE R$ 2.288,00 (29/08)

Primeiro slot real: o carrossel de `pet` pôs uma cama de R$ 54,98 e um robô de
R$ 2.288,00 sob a capa "3 coisas que eu compraria de novo sem pensar", num
perfil de **achadinhos**. 41 vezes de distância.

A regra NÃO é teto por nicho: no mesmo slot, `beleza` saiu com R$ 69,90 · 79,90
· 199,09 e está certo — a capa diz "parecem caros mas custam pouco". Um teto de
R$150 mataria esse post por um defeito que ele não tem.

📌 **O problema nunca foi o valor absoluto, foi a DISTÂNCIA entre eles.** Regra
sobre o item isolado não enxerga isso; a regra tem que ser sobre o conjunto. A
âncora é a mediana — um outlier em qualquer ponta não a move, então ele é o
excluído em vez de excluir os demais.

E a primeira versão **derrubou o post inteiro** num preço formatado.
📌 **O que melhora o post e o que permite o post são camadas diferentes: a de
cima pode falhar sozinha, e falhar sozinha quer dizer não fazer nada.**

### 📣 "SIGA NOSSOS CANAIS" IA PRO TOPO DO GRUPO (29/08)

A fila vem de canais do Telegram, e a divulgação do próprio canal entra nela
como produto. "SIGA NOSSOS CANAIS" estava lá com link real, 181 vendas e 13% de
comissão — classificado **mina_ouro**, ou seja, o ranking novo o mandaria pro
topo do grupo dos clientes.

`nome_de_produto_ruim` não pegava: contar palavras úteis falha porque "NOSSOS"
não estava em lista nenhuma e segurava o nome sozinho. O sinal certo é a FORMA
da frase — **nome de produto não começa com imperativo**.

E o `postar_grupo` era o único publicador que não chamava a regra, enquanto o
`whatsapp_playwright` já chamava. Meia regra em cada superfície é como esse caso
passou.

## 📌 Referência rápida (infra)

- **VPS:** Contabo · daemon `jarvis.service` (`python -m agents.daemon_maestro`)
  · venv em `/root/jarvis/.venv`.
- **Proxy do Instagram (`IG_PROXY`):** tipo **ISP/residencial**, localização
  **Brasil**, formato `http://user:pass@host:porta` (aceita `socks5://`).
  ⚠️ **NUNCA o valor aqui** — ele vive só no `.env` da VPS. O que se anota é o
  QUE COMPRAR, não a credencial.
  - **Por que residencial e não datacenter:** o IG bloqueia IP de datacenter
    agressivamente — é a razão de o proxy existir em vez de usar a VPS direto.
  - **Por que Brasil:** as fontes são perfis BR, e o `YTDLP_COOKIES` é uma
    sessão criada daqui. Sessão brasileira entrando por IP estrangeiro é
    sinal clássico de conta comprometida, e o IG trata isso pior do que não
    ter cookie.
  - **Volume é baixo:** `IG_MAX_PERFIS_RUN=12` por rodada, 8s entre perfis. O
    que se compra é qualidade de IP, não banda — plano de entrada resolve.
  - ⚠️ **QUANDO ELE VENCE, DESLIGUE A PODA ANTES DE QUALQUER COISA:**
    `echo 'COLETA_PODA_AUTO=0' >> .env`. Sem isso o coletor interpreta o
    canal inteiro como fonte zumbi. (A trava por canal de 18/08 cobre isso,
    mas o interruptor é a garantia que não depende de código.)
  - **Registrado em 18/08 porque a pergunta "qual proxy e qual localização?"
    não tinha resposta em lugar nenhum** — o valor estava certo no `.env` e o
    CRITÉRIO não estava documentado, então venceu e ninguém sabia o que
    recomprar.
  - **DIAGNÓSTICO DE PROXY MORTO — a sequência de 2 comandos (medida 18/08):**

        .venv/bin/python ig_playwright.py --diag promosda.alana
        IG_PROXY= .venv/bin/python ig_playwright.py --diag promosda.alana

    | com proxy | sem proxy | veredito |
    |---|---|---|
    | `Timeout 45000ms` | carrega (mesmo em login wall) | **proxy morto** — comprar resolve |
    | `Timeout` | `Timeout` | rede da VPS / IP bloqueado — proxy novo NÃO conserta |

    Foi exatamente esse par que fechou o caso: timeout com proxy, e sem ele a
    página carregou (redirect pro `/accounts/login/`). **Rodar os dois ANTES de
    comprar** — o 2º comando é o que evita gastar num problema que não é o
    proxy.
  - ⚠️ **E o `login_duro: True` sem proxy é informação, não ruído.** Com 9
    cookies de IG, o IP da VPS ainda caiu na tela de login. O `ig_cookies.txt`
    não tem `sessionid` (registrado em 19/07), então o IG só entrega reels de
    perfil público **enquanto não te throttla** — e o IP da VPS não passa.
    **O proxy não é só pra contornar bloqueio: é o que faz o IG entregar
    conteúdo.** É por isso que datacenter não serve: cairia no mesmo login
    wall, só que pago.
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
