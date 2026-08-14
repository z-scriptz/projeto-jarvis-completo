# O CRÍTICO INTERNO E A MEMÓRIA DO JARVIS

**Desenho, não implementação.** Pedido do Dre em 11/08: *"Primeiro vamos
desenhar essa arquitetura de julgamento e aprendizado; não implemente ainda."*

Este documento responde a três perguntas: o que já existe, o que dá pra
construir **agora** sem depender de views/vendas, e o que eu **não**
construiria — com o motivo de cada recusa.

---

## 1. O que já existe (medido, não suposto)

| peça | onde | estado |
|---|---|---|
| checagens determinísticas do MP4 | `conferir_render.py` | 7 checks, funcionando |
| texto queimado na foto | `texto_queimado.py` | funcionando, com Vision |
| diversidade / tamanho dos assets | `asset_ranker.py` | funcionando |
| frames + contact sheet do vídeo | `visual_audit_agent.py` | funcionando |
| julgamento por Vision de frame | `visual_audit_agent.avaliar_relevancia_frame` | funcionando |
| **memória de longo prazo** | `memory_agent.py` (1097 linhas) | **existe e está órfã** |

`memory_agent` já tem exatamente o que o desenho pede: `registrar_memoria`,
`registrar_avaliacao_video`, `registrar_avaliacao_audio`,
`buscar_contexto_para_tarefa`, JSONL + vector store com degradação graciosa.

⚠️ **E ninguém chama `registrar_avaliacao_video` fora do próprio arquivo.**
Ele é importado por `narrated_video_agent`, `conferir`, `ceo_agent`,
`supervisor_agent`, `product_video_editor` e `audio_selector_agent` — a esteira
ANTIGA. A cadeia nova (`storyboard → edl → render → conferir_render`, mais o
`piloto`) nasceu esta semana **desconectada da memória**.

**Consequência pro plano:** a primeira tarefa não é "construir memória". É
plugar a cadeia nova na memória que já existe. Construir uma segunda memória ao
lado desta seria repetir o erro do `narrated_video_agent` na raiz vs. em
`agents/` — duas verdades, nenhuma confiável.

---

## 2. A distinção que decide tudo: defeito ≠ qualidade

Esta é a parte que eu mudaria no desenho do ChatGPT, e é a única que, se
passar batido, produz um crítico confiante e errado.

**Defeito técnico tem definição objetiva e não precisa de ninguém pra
confirmar:**

    2,4s sem áudio           é medível e é ruim, sempre
    legenda sobre texto      é medível e é ruim, sempre
    imagem parada 8s         é medível e é ruim, sempre
    produto fora do quadro   é medível e é ruim, sempre

**"Vídeo bom" não tem.** É preferência, público e momento. E aqui está o
problema da frase *"o Jarvis viu milhares de vídeos bons e ruins e construiu
uma noção interna do que é bom"*:

> Sem nenhum sinal externo, quem define "bom" nos exemplos somos nós. O
> sistema não aprende o que funciona — ele aprende **o nosso gosto**, e depois
> nos devolve o nosso gosto com aparência de medição.

Isso não é inútil: gosto consistente é melhor que gosto aleatório, e um crítico
calibrado no seu gosto **é** valioso. Mas precisa ser chamado pelo nome, porque
os dois se comportam de forma diferente quando erram:

- crítico de **defeito** que erra → dá pra provar que errou, medindo de novo;
- crítico de **gosto** que erra → não dá, e ele fica cada vez mais confiante,
  porque o único juiz é ele mesmo.

**Portanto: duas camadas separadas, com selos separados no relatório.** Nunca
somar as duas numa nota só (ver §4).

---

## 3. Arquitetura

```
                          MP4 RENDERIZADO
                                 │
             ┌───────────────────┼───────────────────┐
             ↓                   ↓                   ↓
      CAMADA 1: DEFEITO   CAMADA 2: OFÍCIO   CAMADA 3: GOSTO
      determinística       determinística      Vision + rubrica
      (já existe)          (regras nossas)     (novo)
             │                   │                   │
      silêncio morto       hook > 84 chars     composição
      quadro morto         1 imagem só         o produto atrai?
      moldura instável     corte < 1,4s        parece anúncio?
      contraste            zoom em foto        prende nos 2s?
      tarjas               pequena             ritmo
             │                   │                   │
             └───────────────────┼───────────────────┘
                                 ↓
                          LAUDO ESTRUTURADO
                    (por dimensão, com evidência)
                                 ↓
                    ┌────────────┴────────────┐
                    ↓                         ↓
              TEM LEVER?                  NÃO TEM
                    ↓                         ↓
             CORRIGE E REPETE          REPORTA E PARA
             (teto de N tentativas)    (decisão humana)
                    ↓
              MEMÓRIA (memory_agent)
```

### Camada 1 — defeito
É o `conferir_render.py` de hoje. Nada a inventar. O que muda é o formato de
saída: em vez de `✅/❌` soltos, cada check devolve **estado + evidência +
lever** (qual parâmetro mexeria nisso).

### Camada 2 — ofício
Regras que **nós** descobrimos e que hoje estão espalhadas como comentários e
avisos: `HOOK_MAX = 70`, `PISO_SEGMENTO = 1.4`, "foto < 600px o close vira
borrão", "1 informação visual só". Elas já existem — estão hardcoded em cinco
arquivos. Aqui viram **regras nomeadas, com origem e data**, num só lugar. É o
"conhecimento operacional" do ChatGPT, e é a camada mais barata e mais útil.

### Camada 3 — gosto
Vision sobre o contact sheet (que o `visual_audit_agent` já monta) + amostras
de áudio. Responde o que as outras não conseguem: *"isso parece um anúncio
amador?"*, *"o produto é o herói do quadro?"*, *"os 2 primeiros segundos
seguram?"*.

⚠️ **A camada 3 nunca reprova sozinha.** Ela levanta ressalva e escreve na
memória. Só a camada 1 (defeito objetivo) tem poder de veto — mesma regra do
`texto_queimado`, onde o Vision só rebaixa e nunca aprova.

---

## 4. Por que NÃO uma nota única

O ChatGPT já diz que "nota: 8.3" é inútil sem justificativa. Concordo, e vou um
passo além: **a nota única não é só inútil, ela é ativamente perigosa.**

1. **Ela vira o alvo.** Assim que existir um número, todo ajuste passa a ser
   avaliado por ele — inclusive ajustes que pioram o vídeo e melhoram a nota.
2. **Ela mistura o que não se mistura.** "Silêncio de 2,4s" é fato; "composição
   8,7" é palpite. Somados, o fato desaparece dentro do palpite.
3. **Ela esconde a origem.** Foi a lição do `SELO_DX`: valor sem origem não
   responde "mudei e não mudou, por quê". Um `8.6` não diz de onde veio.

**No lugar:** veredito por dimensão, cada um com a evidência que o sustenta, e
a decisão final derivada de **regra**, não de limiar sobre número fuzzy:

    REPROVA          se qualquer defeito de camada 1 falhou
    REPROVA          se ≥2 regras de ofício violadas
    RESSALVA         se camada 3 apontou, mas 1 e 2 passaram
    APROVA           se 1 e 2 passam e 3 não apontou nada grave

Se um dia quisermos um número pra ordenar vídeos, ele se calcula A PARTIR do
laudo — nunca o contrário.

---

## 5. O laço de correção, e os três limites que ele precisa ter

O desenho `render → crítico → corrige → render → crítico → aprova` está certo.
Sem três limites explícitos, ele queima dinheiro e não termina.

**Limite 1 — só corrige o que tem lever.** Cada defeito precisa apontar um
parâmetro concreto. Sem lever mapeado, o crítico **reporta e para**; não
inventa correção.

    silêncio morto     → lever: PAUSA_APOS_FALA, ou re-narrar o trecho
    hook > 84          → lever: pedir hook novo ao storyboard
    1 imagem só        → SEM LEVER (é matéria-prima) → reporta e para
    "parece amador"    → SEM LEVER → vira memória, não correção

**Limite 2 — teto de tentativas, com o motivo registrado.** 2 tentativas. A
terceira vira relatório pro humano. Loop sem teto num sistema que se auto-avalia
é como o crítico e o corretor negociarem entre si até concordar.

**Limite 3 — re-render não pode custar uma narração nova.** Hoje cada render
chama o ElevenLabs. Um laço de 3 tentativas = 3 vezes o custo de voz, para
consertar um enquadramento que não mexeu no texto. **Pré-requisito do laço:
cache de TTS por hash do texto+voz+settings.** Sem isso, o laço é caro
exatamente nas correções mais bobas.

*(E hoje esse custo é zero pelo pior motivo: a assinatura do ElevenLabs está
com pagamento pendente e todo vídeo sai mudo. Isso precisa ser resolvido antes
de qualquer medição de áudio fazer sentido.)*

---

## 6. Memória: as três camadas do ChatGPT, com uma correção

Concordo com a separação **experiência / conhecimento / julgamento**. O
`memory_agent` já suporta as três (`tipo` + `colecao`). Duas mudanças:

### 6.1 Toda memória carrega a EVIDÊNCIA, não só a conclusão

    ruim:  "cortes curtos funcionam melhor pra Casa"
    bom:   "PISO_SEGMENTO subiu 1,0 → 1,4 em 09/08 porque em 3 vídeos o
            olho não terminava de ler a imagem. Medido no contact sheet."

Conclusão sem evidência não pode ser revista depois — e memória que não pode
ser revista vira dogma. A ROADMAP funciona hoje **exatamente por isso**: cada
lição tem a medição que a gerou.

### 6.2 Esquecer por TEMPO está errado

O ChatGPT propõe arquivar memória velha. Eu arquivaria por **contradição, não
por idade**: uma lição só sai de cena quando uma medição nova a contradiz — e
aí as duas ficam registradas, com as datas. "Vídeo de 15s convertia melhor em
2026" não fica falso em 2027 por ter envelhecido; fica falso quando alguém
mede o contrário.

Descartar por tempo perderia justamente as lições estruturais, que são velhas
por serem fundamentais.

---

## 7. As outras ideias: o que entra, o que eu mudaria, o que eu adiaria

| ideia | veredito | por quê |
|---|---|---|
| **Crítico audiovisual** | ✅ entra | é o núcleo; metade já existe |
| **Momentos importantes** (linha do tempo) | ✅ entra | barato, e dá contexto que dashboard nenhum tem |
| **Capacidade de discordar** | ✅ entra | é só *consultar a memória antes de obedecer* e citar a evidência. Depende de §6.1 |
| **Conhecimento como regras nomeadas** | ✅ entra | é a camada 2; hoje está espalhado em comentário |
| **Identidade / princípios** | ⚠️ mudaria | arquivo de princípios só vale se **algum código o lê**. Princípio que ninguém consulta é poesia versionada |
| **`confianca_global: 0.74`** | ❌ cortaria | número sem derivação é decoração. De onde sai 0,74? Se ninguém sabe, ele só dá ar de rigor |
| **Laboratório de hipóteses** | ⏳ adiaria | hipótese precisa de resultado pra ser confirmada, e resultado aqui é venda/retenção — que não temos. Hoje viraria hipótese eterna |
| **Sandbox de estratégia** | ⏳ adiaria | simular exige modelo do mundo. Sem histórico de conversão, o simulador inventaria o resultado |
| **Versionamento do cérebro + rollback** | ⚠️ mudaria | já temos: é o git. Versionar "o cérebro" à parte cria uma segunda história do sistema que pode divergir da real |
| **Conselho interno (analista/estrategista/crítico)** | ⚠️ mudaria | 3 papéis, mesmo modelo, mesmos dados → concordam, ou discordam de mentira. Só vale se cada papel tiver **dado diferente** ou **veto explícito**. Ex.: o "crítico" vê só o laudo técnico e pode vetar; o "estrategista" vê só o histórico. Debate entre personas com a mesma entrada é teatro caro |
| **Reflexão diária** | ⚠️ mudaria | boa ideia, mas hoje ela só teria dado de produção. Uma retrospectiva que não pode responder "o que funcionou?" vira redação. Começaria como **retrospectiva técnica**: quantos vídeos reprovados, por qual defeito, qual regra pegou mais |

---

## 8. O ciclo completo, com todos os estados

Pedido do Dre/ChatGPT: *"quero que o desenho mostre claramente o ciclo
completo… Também quero um estado explícito para problemas sem lever."*

```
   ┌─────────────────────────────────────────────────────────────┐
   │                    ANTES DE PRODUZIR                        │
   │  consulta a memória pela ASSINATURA DA ENTRADA (§8.3)       │
   │  "já produzi sob estas condições? o que deu errado?"        │
   └──────────────────────────┬──────────────────────────────────┘
                              ↓
                    ①  PRODUZIR  (storyboard → edl → render)
                              ↓
                    ②  OBSERVAR  (extrai frames, áudio, tempos)
                              ↓
                    ③  CRITICAR
                       camada 1 defeito · camada 2 ofício · camada 3 gosto
                              ↓
                    ④  DIAGNOSTICAR
                       para cada achado: qual a CAUSA? existe LEVER?
                              ↓
        ┌──────────────┬──────┴───────┬──────────────┬───────────────┐
        ↓              ↓              ↓              ↓               ↓
   sem achado    tem lever      SEM lever      teto batido    só ressalva
        │              │        (matéria-      (2 tentativas)   camada 3
        │              │         prima)             │               │
        ↓              ↓              ↓              ↓               ↓
   ✅ APROVADO   ⑤ CORRIGIR   🔴 BLOQUEADO   🔴 BLOQUEADO   🟡 REVISÃO
    (terminal)         │       SEM_LEVER        TETO          HUMANA
                       ↓        (terminal)     (terminal)     (terminal)
                 ⑥ RE-RENDER         │              │              │
                       ↓             │              │              │
                 ⑦ REAVALIAR         │              │              │
                       │             │              │              │
                       └──────→ volta a ③           │              │
                                     │              │              │
        ┌────────────────────────────┴──────────────┴──────────────┘
        ↓
   ⑧ REGISTRAR EXPERIÊNCIA  (memory_agent) — em TODOS os finais,
     inclusive no aprovado de primeira: "nada deu errado" também é dado
        ↓
   ⑨ a próxima produção consulta isto no passo ZERO
```

### 8.1 Os estados terminais, e o que cada um exige de quem

| estado | significa | quem age |
|---|---|---|
| ✅ `APROVADO` | camadas 1 e 2 passaram | ninguém — segue pra esteira |
| 🟡 `REVISAO_HUMANA` | só a camada 3 apontou | Dre assiste e diz se concorda → vira calibração (§8.4) |
| 🔴 `BLOQUEADO_SEM_LEVER` | defeito real, **nenhum parâmetro conserta** | precisa de asset novo, não de re-render |
| 🔴 `BLOQUEADO_TETO` | tinha lever, tentou 2x, não resolveu | Dre decide: forçar, descartar, ou investigar |

⚠️ **`BLOQUEADO_SEM_LEVER` é a peça que impede a loucura** que o ChatGPT
descreveu (crop → crop → IA → zoom → render → ruim → render…). O critério é
duro: *o problema é corrigível POR MIM, mexendo em parâmetro que eu controlo?*
Se a resposta é "não, falta matéria-prima", **parar é a resposta certa** — e é
mais barato que qualquer tentativa.

    🔴 BLOQUEADO — material insuficiente
       achado:  1 informação visual, 3 enquadramentos derivados da mesma foto
       causa:   a origem entregou 1 imagem (Shopee, galeria fechada)
       lever:   NENHUM — edição não cria informação que não existe
       ação:    coletar assets; produzir assim mesmo só com --forcar

### 8.2 O que é lever, e o que não é

| achado | lever | corrigível? |
|---|---|---|
| silêncio morto de 2,1s | `PAUSA_APOS_FALA`, re-conformar cena à fala | ✅ |
| hook > 84 caracteres | pedir hook novo ao storyboard | ✅ |
| legenda sobre texto queimado | faixa evitada no recorte / `--encaixe cover` | ✅ |
| corte < `PISO_SEGMENTO` | re-conformar a linha do tempo | ✅ |
| foto 496px, close amolece | — | ❌ matéria-prima |
| 1 informação visual só | — | ❌ matéria-prima |
| "parece amador" (camada 3) | — | ❌ não é defeito, é gosto → ressalva |
| produto pouco atraente | — | ❌ é o produto, não o vídeo |

**Regra:** achado sem lever mapeado **nunca** dispara correção. Ele vira estado
terminal com a causa escrita. O crítico não inventa conserto.

### 8.3 O registro de experiência — e a coisa que faltava nele

Adoto o formato do ChatGPT, com **dois campos que ele não tinha** e sem os
quais a memória não serve pro passo ⑨:

```json
{
  "id": "exp_184",
  "quando": "2026-08-12T14:22:00",
  "produto": "Garrafa Squeeze com Infusor 700ml",

  "assinatura_da_entrada": {
    "n_fotos": 1, "n_distintas": 1, "menor_lado": 900,
    "nicho": "casa", "hook_chars": 62, "n_cenas": 8,
    "texto_queimado": "ressalva", "modo_audio": "narracao"
  },

  "achado":     "cena 3 com 2,1s sem informação audiovisual",
  "como_detectei": "conferir_render.silencio_morto · camada 1",
  "causa":      "duração da cena maior que a duração da narração dela",
  "lever":      "conformar a cena à fala (PAUSA_APOS_FALA / _conformar)",
  "correcao":   "cena 3: 4,8s → 2,7s",
  "resultado":  "silencio_morto 2,1s → 0,0s",
  "verificado": true,

  "licao": "cena que depende só de narração não guarda tempo sobrando"
}
```

⚠️ **`assinatura_da_entrada` é o campo que faz o passo ⑨ existir.** Sem ele, a
busca de "experiências relacionadas" só acha por nome de produto — e nome de
produto não se repete. Com ele, a pergunta vira respondível: *"o que deu errado
nas outras vezes em que produzi com 1 foto, nicho casa, hook de ~60 chars?"*.
É a diferença entre memória que arquiva e memória que **antecipa**.

⚠️ **`verificado` é o que separa experiência de boato.** Só vira lição se a
re-renderização confirmou. Correção registrada sem reavaliação é palpite com
data — e o passo ⑦ existe justamente pra preencher este campo.

### 8.4 Calibração: as fases A/B/C, com uma correção importante

Aceito as três fases. Mas **"confiança" não pode ser o modelo dizendo o quanto
ele confia em si mesmo** — modelo de linguagem é notoriamente mal calibrado
nisso, e seria o `confianca_global: 0.74` voltando por outra porta.

**Confiança tem que ser CONCORDÂNCIA MEDIDA, por categoria de achado:**

```
Fase A — o Vision fala, você julga, e a gente CONTA

   "corte estranho"        Dre concordou 17/20  →  85%
   "produto mal apresentado" Dre concordou 14/18  →  78%
   "sensação de slideshow"   Dre concordou  4/15  →  27%   ← não confiável
   "hook pouco impactante"   Dre concordou  6/19  →  32%   ← não confiável

Fase B — autonomia POR CATEGORIA, não global
   categoria acima de 80% → vira ressalva automática, sem perguntar
   categoria abaixo disso → continua indo pra revisão humana
   (e a que ficar sempre baixa é uma categoria que a gente APOSENTA:
    o modelo não enxerga aquilo, e insistir é ruído)

Fase C — a autonomia cresce sozinha, e é auditável
   a cada N julgamentos a taxa é recalculada; se cair, a categoria volta
   pra revisão. Ninguém precisa "confiar": dá pra ver o número.
```

⚠️ **Custo honesto disso:** ~20 julgamentos por categoria pra ter qualquer
sinal, e ~10 categorias = **200 julgamentos seus**. A 5 vídeos por dia, são uns
40 dias. Isso não é motivo pra não fazer — é motivo pra não desenhar como se a
Fase C chegasse semana que vem.

💡 **E dá pra acelerar muito:** a esteira tem **152 vídeos prontos** e mais em
`fila_vencida/`. A Fase A não precisa esperar produção nova — o crítico pode
rodar sobre o que já existe, e você julga em lote. Semanas viram dias.

### 8.5 O override também é dado

Quando você usa `--forcar` num `BLOQUEADO`, isso **é** um julgamento seu sobre
o crítico e tem que virar experiência. Se um tipo de bloqueio é forçado toda
vez, o bloqueio está errado — e só o registro mostra isso.

---

## 9. Primeira fatia proposta

Nada aqui depende de views, vendas ou ferramenta paga.

1. **Laudo estruturado** no lugar dos `✅/❌` do `conferir_render`: cada achado
   com estado, evidência, causa e **lever** (ou a ausência dele). É o passo ④
   e é pré-requisito de todo o resto — sem ele não existe `BLOQUEADO_SEM_LEVER`.
2. **Plugar a cadeia nova no `memory_agent`**, gravando o registro do §8.3 com
   `assinatura_da_entrada`. Acaba com a orfandade e habilita o passo ⑨.
3. **Consulta no passo ZERO**: antes de produzir, buscar experiências com
   assinatura parecida e avisar o que costuma dar errado nessas condições.
4. **Camada 2 como arquivo de regras** — tirar os limiares de dentro de cinco
   arquivos e dar a cada um nome, valor, origem e data.
5. **Camada 3 (Vision) em modo observador**, sem veto, com o placar de
   concordância por categoria do §8.4. Rodando **sobre a esteira que já
   existe**, pra Fase A não depender de produção nova.
6. **Cache de TTS** — pré-requisito do laço, e economiza dinheiro mesmo sem ele.
7. Só então **ligar o laço de correção** (⑤⑥⑦), com os três limites do §5.

⚠️ **Um pré-requisito fora desta lista:** a assinatura do ElevenLabs está com
pagamento pendente e **todo vídeo novo sai mudo**. Enquanto isso durar, metade
das checagens do crítico (silêncio, sincronismo, narração x duração) mede um
vídeo que nunca teve áudio — e o crítico aprenderia sobre um defeito que é da
fatura, não da edição.

**O que fica de fora, e o Dre decide quando entra:** hipóteses, sandbox,
conselho e reflexão — todos precisam de retorno do mundo real pra não virarem
literatura. Eles são a fase seguinte, não esta.
