// Aula 1 — Bem-vindo ao Afiliado Online
//
// Cada item é um slide. Campos:
//   eyebrow   rótulo pequeno dourado no topo
//   h1        título (aceita <g> para a palavra em dourado)
//   sub       texto de apoio (aceita <b> para destaque)
//   two       bloco de duas colunas: { is: [rótulo, texto], isnot: [rótulo, texto] }
//   cta       linha final em mono dourado
//   ring      'um' ou 'dois' — posição do círculo dourado de fundo
//   segundos  duração de reserva, usada só enquanto não existe narração
//   narracao  o que a voz fala neste slide — é daqui que sai o MP3
//
// O áudio é resolvido por convenção: existindo public/Aula1_slide3.mp3, ele entra no
// vídeo e a duração do slide passa a ser a do próprio áudio. Para gerar:
//   node scripts/narrar.mjs Aula1

export const aula1 = {
  id: 'Aula1',
  titulo: 'Aula 1 — Bem-vindo',
  slides: [
    {
      ring: 'um',
      eyebrow: 'Afiliado Online · Módulo 0 · Aula 1',
      h1: 'Bem-vindo ao <g>Afiliado Online</g>',
      sub: 'Uma renda online de verdade — de forma prática, e <b>sem precisar se expor.</b>',
      segundos: 10,
      narracao:
        'Seja muito bem-vindo ao Afiliado Online. Aqui você vai aprender a construir uma renda online de forma prática — e sem precisar aparecer.',
    },
    {
      eyebrow: 'O que te trouxe aqui',
      h1: 'Você quer — mas <g>trava</g>',
      sub: 'A vontade de ter uma renda online existe. O que trava é quase sempre o mesmo: <b>"não quero aparecer"</b>, <b>"não tenho tempo"</b>, <b>"não sei por onde começar"</b>.',
      segundos: 13,
      narracao:
        'Se você já quis ter uma renda na internet mas travou, provavelmente foi por um destes motivos: não quer aparecer, não tem tempo, ou simplesmente não sabe por onde começar.',
    },
    {
      ring: 'dois',
      eyebrow: 'A boa notícia',
      h1: 'Dá pra fazer <g>sem aparecer</g>',
      sub: 'E no automático. Existe um caminho onde você constrói um <b>sistema que trabalha por você</b> — sem mostrar o rosto e sem postar o dia inteiro na mão.',
      segundos: 14,
      narracao:
        'A boa notícia é que dá pra fazer tudo isso sem mostrar o rosto e no automático. O segredo é construir um sistema que trabalha por você — em vez de você trabalhar o dia inteiro.',
    },
    {
      eyebrow: 'O que este curso é',
      h1: 'Um <g>método</g>. Não um milagre.',
      two: {
        is: ['É isto', 'Um sistema real, passo a passo, que você constrói e coloca pra rodar.'],
        isnot: [
          'Não é isto',
          'Promessa de ficar rico da noite pro dia. Resultado vem de execução — e a gente é honesto sobre isso.',
        ],
      },
      segundos: 19,
      narracao:
        'Deixa uma coisa clara desde já: isto é um método, não um milagre. Você vai aprender um sistema real, passo a passo. O que você não vai encontrar aqui é promessa de ficar rico da noite pro dia. Resultado vem de execução — e a gente é honesto sobre isso.',
    },
    {
      eyebrow: 'Como aproveitar',
      h1: 'Assista na ordem. <g>Execute.</g>',
      sub: 'Cada módulo constrói o anterior. Assista em sequência, coloque em prática e use os materiais extras de cada aula. <b>É fazendo que funciona.</b>',
      segundos: 13,
      narracao:
        'Pra aproveitar de verdade: assista as aulas na ordem, coloque cada passo em prática e use os materiais extras. É fazendo que funciona.',
    },
    {
      ring: 'um',
      eyebrow: 'Próxima aula',
      h1: 'A <g>máquina</g> que você vai construir',
      sub: 'No próximo vídeo, você vê a visão completa do sistema — as engrenagens que transformam conteúdo em renda.',
      cta: 'Continue no próximo vídeo',
      segundos: 11,
      narracao:
        'No próximo vídeo, você vai ver a visão completa da máquina que vamos construir juntos. Te espero lá.',
    },
  ],
};
