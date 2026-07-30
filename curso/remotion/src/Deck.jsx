import React from 'react';
import {AbsoluteFill, Series, useCurrentFrame, useVideoConfig} from 'remotion';
import {cores, fontes} from './theme.js';
import {Slide} from './Slide.jsx';

// Regras usadas pelo texto rico dos slides (<g> = palavra em dourado, <b> = destaque).
const estiloTextoRico = `
  g { color: ${cores.goldSoft}; }
  b { color: ${cores.ink}; font-weight: 600; }
`;

const Marca = () => (
  <div
    style={{
      position: 'absolute',
      top: 38,
      left: 46,
      fontFamily: fontes.mono,
      fontSize: 13,
      letterSpacing: '0.22em',
      textTransform: 'uppercase',
      color: cores.gold,
      opacity: 0.85,
    }}
  >
    TopShop Academy
  </div>
);

// Barra de progresso da aula inteira, no rodapé.
const Progresso = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const pct = Math.min(100, ((frame + 1) / durationInFrames) * 100);
  return (
    <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 4, background: 'rgba(255,255,255,.05)'}}>
      <div
        style={{
          height: '100%',
          width: `${pct}%`,
          background: `linear-gradient(90deg, ${cores.gold}, ${cores.goldSoft})`,
        }}
      />
    </div>
  );
};

export const Deck = ({slides, frames}) => (
  <AbsoluteFill
    style={{
      background: `radial-gradient(120% 120% at 78% 12%, ${cores.verdeClaro} 0%, ${cores.bg1} 42%, ${cores.bg2} 100%)`,
      color: cores.ink,
      fontFamily: fontes.sans,
    }}
  >
    <style>{estiloTextoRico}</style>

    <Series>
      {slides.map((slide, i) => (
        <Series.Sequence key={i} durationInFrames={frames[i]}>
          <Slide slide={slide} indice={i} />
        </Series.Sequence>
      ))}
    </Series>

    <Marca />
    <Progresso />
  </AbsoluteFill>
);
