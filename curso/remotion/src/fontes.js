import {mono, sans, serif} from './fontes-embutidas.js';

// Família Source (SIL OFL 1.1), subsetada e embutida em base64.
//
// Georgia não entra aqui: é proprietária da Microsoft, não existe no Linux e não pode ser
// empacotada. Com a família embutida, o render sai idêntico em qualquer máquina.
//
// Por que @font-face puro e não delayRender(): o dado da fonte já está dentro do bundle,
// então não existe requisição de rede para aguardar. E o Remotion controla os timers do
// ambiente de render, o que torna qualquer espera com setTimeout pouco confiável aqui.
const face = (familia, base64) => `
@font-face {
  font-family: '${familia}';
  src: url(data:font/woff2;base64,${base64}) format('woff2');
  font-weight: 200 900;
  font-display: block;
}`;

export const cssFontes = [
  face('TS Serif', serif),
  face('TS Sans', sans),
  face('TS Mono', mono),
].join('\n');
