import React from 'react';
import {Audio, Easing, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {cores, fontes, FPS, ritmo} from './theme.js';

// Entrada escalonada: cada elemento sobe 16px e aparece, com o atraso do seu papel.
// É a mesma animação dos decks HTML, só reescrita em frames.
const useEntrada = (atrasoSegundos) => {
  const frame = useCurrentFrame();
  const inicio = atrasoSegundos * FPS;
  const fim = inicio + ritmo.duracaoElemento * FPS;
  const opacity = interpolate(frame, [inicio, fim], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const y = interpolate(frame, [inicio, fim], [16, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.2, 0.7, 0.2, 1),
  });
  return {opacity, transform: `translateY(${y}px)`};
};

const Eyebrow = ({children}) => (
  <div
    style={{
      ...useEntrada(ritmo.atrasos.eyebrow),
      fontFamily: fontes.mono,
      fontSize: 15,
      letterSpacing: '0.28em',
      textTransform: 'uppercase',
      color: cores.gold,
      display: 'flex',
      alignItems: 'center',
      gap: 14,
    }}
  >
    {children}
    <span style={{height: 1, width: 80, background: cores.goldLinha}} />
  </div>
);

const Titulo = ({html}) => (
  <h1
    style={{
      ...useEntrada(ritmo.atrasos.h1),
      margin: 0,
      fontFamily: fontes.serif,
      fontWeight: 700,
      fontSize: 86,
      lineHeight: 1.02,
      letterSpacing: '-0.02em',
      color: cores.ink,
      maxWidth: '16ch',
      textWrap: 'balance',
    }}
    dangerouslySetInnerHTML={{__html: html}}
  />
);

const Sub = ({html}) => (
  <p
    style={{
      ...useEntrada(ritmo.atrasos.sub),
      margin: 0,
      fontSize: 27,
      lineHeight: 1.5,
      color: cores.muted,
      maxWidth: '34ch',
    }}
    dangerouslySetInnerHTML={{__html: html}}
  />
);

const Duas = ({two}) => {
  const estilo = useEntrada(ritmo.atrasos.two);
  const coluna = (rotulo, texto, cor) => (
    <div style={{maxWidth: '26ch'}}>
      <div
        style={{
          fontFamily: fontes.mono,
          fontSize: 13,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          marginBottom: 7,
          color: cor,
        }}
      >
        {rotulo}
      </div>
      <p style={{margin: 0, color: cores.muted, fontSize: 19, lineHeight: 1.5}}>{texto}</p>
    </div>
  );
  return (
    <div style={{...estilo, display: 'flex', gap: 48, flexWrap: 'wrap', marginTop: 6}}>
      {coluna(two.is[0], two.is[1], cores.gold)}
      {coluna(two.isnot[0], two.isnot[1], cores.vermelhoSuave)}
    </div>
  );
};

const Cta = ({children}) => (
  <div
    style={{
      ...useEntrada(ritmo.atrasos.cta),
      fontFamily: fontes.mono,
      color: cores.gold,
      fontSize: 18,
      letterSpacing: '0.06em',
      marginTop: 10,
    }}
  >
    {children}
  </div>
);

// Círculo dourado de fundo — o motivo "faceless": objeto, nunca rosto.
const Anel = ({posicao}) => {
  const base = {
    position: 'absolute',
    borderRadius: '50%',
    border: `1px solid ${cores.goldLinha}`,
    background: 'radial-gradient(circle at 50% 50%, rgba(216,178,90,.05), transparent 62%)',
    pointerEvents: 'none',
  };
  if (posicao === 'dois') {
    return <div style={{...base, width: 410, height: 410, left: -269, bottom: -173, opacity: 0.7}} />;
  }
  return <div style={{...base, width: 496, height: 496, right: -154, top: -108}} />;
};

export const Slide = ({slide, indice}) => {
  const frame = useCurrentFrame();
  // fade do slide inteiro, igual à transição entre slides do deck
  const opacityDoSlide = interpolate(frame, [0, ritmo.fadeSlide * FPS], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        opacity: opacityDoSlide,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        padding: 112,
        gap: 26,
        fontFamily: fontes.sans,
      }}
    >
      {slide.audio ? <Audio src={staticFile(slide.audio)} /> : null}
      {slide.ring ? <Anel posicao={slide.ring} /> : null}

      <Eyebrow>{slide.eyebrow}</Eyebrow>
      <Titulo html={slide.h1} />
      {slide.sub ? <Sub html={slide.sub} /> : null}
      {slide.two ? <Duas two={slide.two} /> : null}
      {slide.cta ? <Cta>{slide.cta}</Cta> : null}

      {/* número do slide como marca d'água discreta */}
      <div
        style={{
          position: 'absolute',
          right: 115,
          bottom: 77,
          fontFamily: fontes.serif,
          fontWeight: 700,
          fontSize: 320,
          lineHeight: 0.7,
          color: 'rgba(216,178,90,.06)',
          userSelect: 'none',
        }}
      >
        {String(indice + 1).padStart(2, '0')}
      </div>
    </div>
  );
};
