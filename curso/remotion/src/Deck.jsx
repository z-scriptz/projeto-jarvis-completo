import React from 'react';
import {AbsoluteFill, Series, useCurrentFrame, useVideoConfig} from 'remotion';
import {cssFontes} from './fontes.js';
import {cores, fontes} from './theme.js';
import {Slide} from './Slide.jsx';

// Fontes da marca + a regra do <b> dentro dos textos de apoio.
const estilos = `${cssFontes}\nb { color: ${cores.ink}; font-weight: 600; }`;

// O fundo não reinicia a cada slide: ele deriva devagar durante o vídeo inteiro,
// o que costura os slides num movimento único em vez de seis quadros parados.
const Fundo = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const t = frame / durationInFrames;
  const x = 78 - 22 * Math.sin(t * Math.PI);
  const y = 12 + 16 * Math.sin(t * Math.PI * 0.8);
  const tamanho = 120 + 14 * Math.sin(t * Math.PI * 1.3);

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(${tamanho}% ${tamanho}% at ${x}% ${y}%, ${cores.verdeClaro} 0%, ${cores.bg1} 42%, ${cores.bg2} 100%)`,
      }}
    />
  );
};

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
  <AbsoluteFill style={{color: cores.ink, fontFamily: fontes.sans}}>
    <style>{estilos}</style>

    <Fundo />

    <Series>
      {slides.map((slide, i) => (
        <Series.Sequence key={i} durationInFrames={frames[i]}>
          <Slide slide={slide} indice={i} duracao={frames[i]} />
        </Series.Sequence>
      ))}
    </Series>

    <Marca />
    <Progresso />
  </AbsoluteFill>
);
