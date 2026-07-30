// Aula 1 — Bem-vindo ao Afiliado Online
//
// Cada item é um slide. Campos:
//   eyebrow  rótulo pequeno dourado no topo
//   h1       título (aceita <g> para a palavra em dourado)
//   sub      texto de apoio (aceita <b> para destaque)
//   two      bloco de duas colunas: { is: [rótulo, texto], isnot: [rótulo, texto] }
//   cta      linha final em mono dourado
//   ring     'um' ou 'dois' — posição do círculo dourado de fundo
//   segundos quanto o slide fica no ar (ajuste conforme a narração)
//   audio    opcional: nome do MP3 em public/ — a narração daquele slide

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
    },
    {
      eyebrow: 'O que te trouxe aqui',
      h1: 'Você quer — mas <g>trava</g>',
      sub: 'A vontade de ter uma renda online existe. O que trava é quase sempre o mesmo: <b>"não quero aparecer"</b>, <b>"não tenho tempo"</b>, <b>"não sei por onde começar"</b>.',
      segundos: 13,
    },
    {
      ring: 'dois',
      eyebrow: 'A boa notícia',
      h1: 'Dá pra fazer <g>sem aparecer</g>',
      sub: 'E no automático. Existe um caminho onde você constrói um <b>sistema que trabalha por você</b> — sem mostrar o rosto e sem postar o dia inteiro na mão.',
      segundos: 14,
    },
    {
      eyebrow: 'O que este curso é',
      h1: 'Um <g>método</g>. Não um milagre.',
      two: {
        is: ['É isto', 'Um sistema real, passo a passo, que você constrói e coloca pra rodar.'],
        isnot: ['Não é isto', 'Promessa de ficar rico da noite pro dia. Resultado vem de execução — e a gente é honesto sobre isso.'],
      },
      segundos: 19,
    },
    {
      eyebrow: 'Como aproveitar',
      h1: 'Assista na ordem. <g>Execute.</g>',
      sub: 'Cada módulo constrói o anterior. Assista em sequência, coloque em prática e use os materiais extras de cada aula. <b>É fazendo que funciona.</b>',
      segundos: 13,
    },
    {
      ring: 'um',
      eyebrow: 'Próxima aula',
      h1: 'A <g>máquina</g> que você vai construir',
      sub: 'No próximo vídeo, você vê a visão completa do sistema — as engrenagens que transformam conteúdo em renda.',
      cta: '→ Continue no próximo vídeo',
      segundos: 11,
    },
  ],
};
