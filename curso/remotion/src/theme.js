// Tokens da marca TopShop Academy — os mesmos valores dos decks HTML das aulas.
// Os tamanhos em px correspondem ao deck HTML em tela cheia 1920x1080
// (os clamp() do CSS chegam no teto nessa largura).

export const cores = {
  bg1: '#0c1512',
  bg2: '#07100c',
  verdeClaro: '#12251b',
  ink: '#eaf0ea',
  muted: '#a7b6ab',
  gold: '#d8b25a',
  goldSoft: '#f0d79a',
  goldLinha: 'rgba(216,178,90,.28)',
  vermelhoSuave: '#c98a72',
};

// As três famílias são carregadas em src/fontes.js e vêm dentro do projeto.
export const fontes = {
  serif: '"TS Serif", Georgia, "Liberation Serif", serif',
  sans: '"TS Sans", system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  mono: '"TS Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace',
};

export const FPS = 30;

// Ritmo da animação, em segundos.
export const ritmo = {
  entrada: 0.6, // quanto dura a entrada de cada elemento
  saida: 0.5, // quanto dura a saída no fim do slide
  palavra: 0.13, // atraso entre uma palavra e a próxima no título (~4 frames: dá pra perceber)
  // atraso de entrada por papel
  // o texto de apoio só entra depois de o título terminar de se montar
  atrasos: {eyebrow: 0.1, h1: 0.26, sub: 1.0, two: 1.0, cta: 1.3},
  // ordem de saída: sai de baixo pra cima (o que entrou por último sai primeiro)
  saidas: {cta: 0, two: 0.06, sub: 0.06, h1: 0.12, eyebrow: 0.18},
};
