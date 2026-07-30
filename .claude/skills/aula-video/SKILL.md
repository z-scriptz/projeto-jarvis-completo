---
name: aula-video
description: Gera o MP4 de uma aula do curso Afiliado Online (TopShop Academy) a partir dos slides em código, com as animações e o sync da narração. Use quando pedirem para renderizar, gerar ou atualizar o vídeo de uma aula, criar os slides de uma aula nova, ou ajustar o tempo dos slides à narração.
---

# Vídeo de aula do curso

O projeto Remotion fica em `curso/remotion`. Ele produz o MP4 de cada aula com o visual da
marca (verde-escuro + dourado, Georgia + mono) e a entrada escalonada dos elementos.

## Renderizar uma aula existente

```bash
cd curso/remotion
npx remotion render src/index.jsx Aula1 out/aula1.mp4
```

Em ambiente com egress restrito o download do Chrome do Remotion é bloqueado. Nesse caso
adicione a flag apontando para o **`headless_shell`** do Playwright (o `chrome` completo
falha, porque o Chrome novo removeu o modo headless antigo):

```bash
--browser-executable=/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell
```

## Ritmo: o Módulo 0 é exceção

O Módulo 0 (Aulas 1 a 3) é manifesto — slide inteiro, ~12s cada, narração em parágrafo.
Fica assim de propósito: o aluno acabou de comprar e está no pico de atenção.
**Não reescreva o Módulo 0 sem pedido explícito.**

Do Módulo 1 em diante o formato muda, porque ali se ensina execução e o aluno decide se
continua ou abandona:

- **Um slide sustenta uma frase, não um parágrafo.** Alvo de 4 a 8 segundos por slide.
  Parágrafo de narração longo vira três slides, não um.
- **Gravação de tela é a base da aula**, não o slide. Módulo 1 em diante ensina coisas que
  acontecem numa tela (achar produto, gerar link, subir vídeo) — descrever isso em texto é
  a pior versão. Os slides viram abertura, rótulos, destaques e encerramento por cima da
  captura.
- **Quebra de padrão a cada ~25s**: muda o enquadramento, entra um número grande, um card.
- Sem rosto e sem voz do autor: a tela mostra a execução, o ElevenLabs narra.

## Criar os slides de uma aula nova

1. Copie `src/aulas/aula1.mjs`, renomeie o `id` (`Aula4`) e escreva os slides.
2. Importe o arquivo em `src/Root.jsx` e acrescente na lista `aulas`.
3. Renderize com o `id` novo.

Regras de escrita dos slides, para manter a coerência com o Módulo 0 já produzido:

- Um slide sustenta **uma ideia**. Título curto (cabe em ~16 caracteres por linha).
- `<g>` marca em dourado **a palavra-chave da frase**, nunca mais de uma por título.
- `eyebrow` diz onde o aluno está ("Engrenagem 3 · A distribuição"), não repete o título.
- Numeração só quando existe sequência real (as engrenagens, os módulos).
- Sem promessa de resultado, sem "fique rico": o curso se posiciona como método honesto,
  e os slides de honestidade (o que é / o que não é) são parte da proposta.
- O último slide é sempre o gancho para a aula seguinte, com `cta`.

## Narração e sincronia

O texto falado mora no campo `narracao` de cada slide, junto do próprio slide. Para gerar:

```bash
npm run narrar Aula2              # só o que falta
npm run narrar Aula2 -- --refazer # regrava tudo
```

O script grava `public/Aula2_slide1.mp3`, `…slide2.mp3` — o nome que o `Root.jsx` procura.
Existindo o MP3, ele entra no vídeo e a duração do slide vira a do áudio (+0,5s de respiro),
sem nenhuma ligação manual. Sem MP3, vale o campo `segundos`, e o 404 no console é esperado.

Credenciais: `ELEVENLABS_API_KEY` e `ELEVENLABS_VOICE_ID` no `.env` da raiz do projeto —
as mesmas do `narracao_ia.py`. Nunca peça a chave por chat nem a escreva em arquivo do repo.

Ao escrever a `narracao`: um parágrafo por slide, e o parágrafo tem que caber no slide —
é ele que define quanto tempo aquele slide fica no ar.

## Conferir o resultado

Antes de entregar, renderize 2–3 frames em pontos diferentes e olhe as imagens:

```bash
npx remotion still src/index.jsx Aula1 out/frame.png --frame=1300
```

Verifique: texto não estourando a caixa, dourado só na palavra-chave, marca d'água do número
correta, e o rodapé de progresso avançando.

## Ajustar a animação

Todos os tempos estão em `src/theme.js`, no objeto `ritmo`: `entrada`, `saida`, `palavra`
(atraso entre palavras do título), `atrasos` (por papel) e `saidas` (ordem da saída).
Mexer ali muda o ritmo de todas as aulas de uma vez — não edite tempo dentro dos componentes.

O texto de apoio entra só depois de o título terminar de se montar. Se aumentar
`ritmo.palavra` ou títulos ficarem mais longos, suba `atrasos.sub` na mesma medida.

## Fontes

A família Source vai embutida em base64 (`src/fontes-embutidas.js`), gerada por
`scripts/subset-fontes.py`. Não use `delayRender()` para carregar fonte aqui: o Remotion
controla os timers do ambiente de render e a espera trava o processo no meio.
Se um caractere novo aparecer nos slides, acrescente em `CARACTERES` no script e rode de novo.

## Limites conhecidos

- O Remotion é grátis para pessoa física e empresa com até 3 funcionários (uso comercial
  incluído); com 4+ exige licença paga.
