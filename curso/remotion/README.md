# Vídeos das aulas — Afiliado Online (TopShop Academy)

Gera o MP4 de cada aula a partir de código, com as mesmas animações dos decks HTML.
Substitui o passo manual de tirar print dos slides e montar no CapCut.

## O fluxo completo

```bash
cd curso/remotion
npm install                     # só na primeira vez
npm run narrar Aula2            # gera a narração no ElevenLabs (um MP3 por slide)
npm run aula2                   # gera out/aula2.mp4, já sincronizado
```

Saída: 1920x1080, 30 fps, H.264, CRF 18.

## Narração (ElevenLabs)

O texto que a voz fala mora no campo `narracao` de cada slide, ao lado do próprio slide.
`scripts/narrar.mjs` lê esse campo, sintetiza no ElevenLabs e grava
`public/Aula2_slide1.mp3`, `public/Aula2_slide2.mp3`… — que é exatamente o nome que o
`Root.jsx` procura. Não há nada pra ligar na mão: existindo o MP3, ele entra no vídeo e a
duração do slide passa a ser a do áudio.

```bash
npm run narrar Aula2              # só o que ainda não existe
npm run narrar Aula2 -- --refazer # regrava tudo
npm run narrar Aula2 -- --slide 3 # só o slide 3
```

Credenciais: as mesmas que o `narracao_ia.py` do Jarvis já usa, lidas do `.env` da raiz
do projeto — `ELEVENLABS_API_KEY` e `ELEVENLABS_VOICE_ID` (obrigatórias), mais
`ELEVENLABS_MODEL`, `_STABILITY`, `_SIMILARITY`, `_STYLE` e `_SPEED` (opcionais).

Enquanto a narração não existe, vale o campo `segundos` de cada slide e o render funciona
igual — só sem voz. No console aparece um 404 por slide sem MP3: é a checagem de
existência, e é esperado.

## Criar uma aula nova

1. Copie `src/aulas/aula1.mjs` para `src/aulas/aula4.mjs`, troque o `id` e os textos
   (inclusive o `narracao` de cada slide).
2. Em `src/Root.jsx`, importe e adicione na lista `aulas`.
3. `npm run narrar Aula4 && npx remotion render src/index.jsx Aula4 out/aula4.mp4`

Campos de cada slide:

| Campo | O que faz |
|---|---|
| `eyebrow` | rótulo pequeno dourado no topo |
| `h1` | título — `<g>palavra</g>` deixa a palavra em dourado |
| `sub` | texto de apoio — `<b>` destaca |
| `two` | bloco de duas colunas (`is` / `isnot`) |
| `cta` | linha final em mono dourado |
| `ring` | `'um'` ou `'dois'` — posição do círculo de fundo |
| `segundos` | duração de reserva, usada só enquanto não há narração |
| `narracao` | o que a voz fala neste slide — é daqui que sai o MP3 |

## Pré-visualizar antes de renderizar

```bash
npm run studio
```

Abre o Remotion Studio no navegador, com timeline — dá pra arrastar e ver cada frame.

## Chromium: a pegadinha do ambiente

O Remotion baixa um Chrome Headless Shell próprio na primeira execução. Em ambiente com
egress restrito (como as sessões do Claude Code na web) esse download é bloqueado, e aí
é preciso apontar pra um Chromium já instalado:

```bash
npx remotion render src/index.jsx Aula1 out/aula1.mp4 \
  --browser-executable=/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell
```

Tem que ser o binário **`headless_shell`**, não o `chrome` completo — o Chrome novo removeu
o modo headless antigo que o Remotion usa, e falha com "Old Headless mode has been removed".

## Animação

O que mantém o vídeo vivo, em vez de seis quadros parados:

- **título palavra por palavra** — cada palavra sobe e aparece, ~4 frames de diferença
- **entrada em cascata** — rótulo, título, texto e CTA entram em sequência
- **saída em cascata** — no fim do slide os elementos saem de baixo pra cima, então a
  troca de slide é uma transição autoral e não um corte seco
- **deriva contínua** — o bloco de conteúdo sobe alguns pixels e cresce 1,6% ao longo do
  slide; o número da marca d'água deriva no sentido oposto, criando profundidade
- **fundo que nunca reinicia** — o gradiente verde caminha durante o vídeo inteiro,
  costurando os slides num movimento único
- **anel dourado** girando e respirando devagar
- **brilho na palavra dourada**, que acende depois de a palavra assentar

Os tempos ficam todos em `src/theme.js`, no objeto `ritmo` — é lá que se acelera ou
desacelera tudo de uma vez.

## Fontes

O projeto embute a família **Source** (Serif 4, Sans 3, Code Pro — licença SIL OFL),
subsetada para latino + acentos do português e convertida em base64 dentro de
`src/fontes-embutidas.js`. Assim o render sai idêntico em qualquer máquina e não depende
de fonte instalada nem de rede.

Georgia não é usada: é proprietária da Microsoft, não existe no Linux e não pode ser
empacotada junto do projeto.

Para regerar (por exemplo, se aparecer um caractere novo nos slides):

```bash
pip install fonttools brotli
python3 scripts/subset-fontes.py
```

O script baixa as fontes se faltarem. Os `.ttf` originais não vão pro git — só o
módulo base64, que é o que o render usa.

## Licença do Remotion

Grátis para pessoa física e empresa com até 3 funcionários, incluindo uso comercial e
vídeos ilimitados. Com 4+ funcionários passa a exigir licença paga.
Ver <https://www.remotion.dev/docs/license>.
