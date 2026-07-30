// Tokens da marca TopShop Academy — os mesmos valores dos decks HTML das aulas.
// Os tamanhos em px correspondem ao que o deck HTML mostra em tela cheia 1920x1080
// (os clamp() do CSS chegam no teto nessa largura), então o vídeo sai igual ao que foi aprovado.

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

export const fontes = {
  // Georgia é fonte da Microsoft: no Linux cai em Liberation Serif (métrica Times).
  serif: 'Georgia, "Liberation Serif", "Times New Roman", serif',
  sans: 'system-ui, -apple-system, "Segoe UI", Roboto, "Liberation Sans", Helvetica, Arial, sans-serif',
  mono: 'ui-monospace, "SF Mono", Menlo, "Liberation Mono", Consolas, monospace',
};

export const FPS = 30;

// Ritmo da entrada dos elementos, em segundos — espelha os transition-delay do deck HTML.
export const ritmo = {
  fadeSlide: 0.5,
  duracaoElemento: 0.55,
  atrasos: { eyebrow: 0.12, h1: 0.28, sub: 0.46, two: 0.46, cta: 0.66 },
};
