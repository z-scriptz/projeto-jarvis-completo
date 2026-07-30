# Vídeos das aulas — Afiliado Online (TopShop Academy)

Gera o MP4 de cada aula a partir de código, com as mesmas animações dos decks HTML.
Substitui o passo manual de tirar print dos slides e montar no CapCut.

## Renderizar

```bash
cd curso/remotion
npm install          # só na primeira vez
npm run aula1        # gera out/aula1.mp4
```

Saída: 1920x1080, 30 fps, H.264, CRF 18.

## Criar uma aula nova

1. Copie `src/aulas/aula1.js` para `src/aulas/aula2.js` e troque os textos.
2. Em `src/Root.jsx`, importe e adicione na lista `aulas`.
3. `npx remotion render src/index.jsx Aula2 out/aula2.mp4`

Campos de cada slide:

| Campo | O que faz |
|---|---|
| `eyebrow` | rótulo pequeno dourado no topo |
| `h1` | título — `<g>palavra</g>` deixa a palavra em dourado |
| `sub` | texto de apoio — `<b>` destaca |
| `two` | bloco de duas colunas (`is` / `isnot`) |
| `cta` | linha final em mono dourado |
| `ring` | `'um'` ou `'dois'` — posição do círculo de fundo |
| `segundos` | quanto o slide fica no ar |
| `audio` | opcional: MP3 da narração daquele slide, em `public/` |

## Sync automático com a narração

Escreva a narração **um parágrafo por slide**, gere **um MP3 por parágrafo** (ElevenLabs),
salve em `public/` e declare no slide:

```js
{ eyebrow: '...', h1: '...', audio: 'aula1_slide1.mp3', segundos: 10 }
```

A duração do slide passa a vir do próprio MP3 (+0,5s de respiro) — sem ajustar nada na mão.
O campo `segundos` continua servindo de reserva pra quando não existe áudio.

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
