import React from 'react';
import {Audio, Easing, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {cores, fontes, FPS, ritmo} from './theme.js';

const suave = Easing.bezier(0.2, 0.7, 0.2, 1);
const travar = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'};

// Entrada + saída de um elemento. Cada papel tem seu atraso, então os elementos
// entram em cascata no começo do slide e saem em cascata no fim — em vez de a
// tela simplesmente cortar pra próxima.
const useAnim = (papel, duracao) => {
  const frame = useCurrentFrame();

  const entraDe = ritmo.atrasos[papel] * FPS;
  const entraAte = entraDe + ritmo.entrada * FPS;
  const opEntra = interpolate(frame, [entraDe, entraAte], [0, 1], travar);
  const yEntra = interpolate(frame, [entraDe, entraAte], [26, 0], {...travar, easing: suave});

  const saiDe = duracao - (ritmo.saida + ritmo.saidas[papel]) * FPS;
  const saiAte = saiDe + ritmo.saida * FPS;
  const opSai = interpolate(frame, [saiDe, saiAte], [1, 0], travar);
  const ySai = interpolate(frame, [saiDe, saiAte], [0, -22], {...travar, easing: suave});

  return {opacity: opEntra * opSai, transform: `translateY(${yEntra + ySai}px)`};
};

// Divide o título em palavras, marcando as que estão dentro de <g> (dourado).
const separarPalavras = (html) => {
  const palavras = [];
  const padrao = /<g>(.*?)<\/g>|([^<]+)/g;
  let achado;
  while ((achado = padrao.exec(html)) !== null) {
    const texto = achado[1] !== undefined ? achado[1] : achado[2];
    const dourada = achado[1] !== undefined;
    texto.split(/\s+/).forEach((palavra) => {
      if (palavra) palavras.push({palavra, dourada});
    });
  }
  return palavras;
};

const Eyebrow = ({children, duracao}) => {
  const frame = useCurrentFrame();
  const anim = useAnim('eyebrow', duracao);
  // a régua dourada é desenhada da esquerda pra direita
  const largura = interpolate(
    frame,
    [ritmo.atrasos.eyebrow * FPS, (ritmo.atrasos.eyebrow + 0.8) * FPS],
    [0, 80],
    {...travar, easing: suave}
  );
  return (
    <div
      style={{
        ...anim,
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
      <span style={{height: 1, width: largura, background: cores.goldLinha}} />
    </div>
  );
};

// Título palavra por palavra: é o que mais tira a sensação de slide parado.
const Titulo = ({html, duracao}) => {
  const frame = useCurrentFrame();
  const saida = useAnim('h1', duracao);
  const palavras = separarPalavras(html);

  return (
    <h1
      style={{
        margin: 0,
        fontFamily: fontes.serif,
        fontWeight: 700,
        fontSize: 86,
        lineHeight: 1.06,
        letterSpacing: '-0.02em',
        color: cores.ink,
        maxWidth: '16ch',
        opacity: saida.opacity,
      }}
    >
      {palavras.map(({palavra, dourada}, i) => {
        const de = (ritmo.atrasos.h1 + i * ritmo.palavra) * FPS;
        const ate = de + ritmo.entrada * FPS;
        const op = interpolate(frame, [de, ate], [0, 1], travar);
        const y = interpolate(frame, [de, ate], [30, 0], {...travar, easing: suave});
        // o brilho da palavra dourada acende depois dela assentar
        const brilho = dourada
          ? interpolate(frame, [ate, ate + 0.7 * FPS], [0, 0.45], travar)
          : 0;
        return (
          <React.Fragment key={i}>
            <span
              style={{
                display: 'inline-block',
                opacity: op,
                transform: `translateY(${y}px)`,
                color: dourada ? cores.goldSoft : cores.ink,
                textShadow: brilho ? `0 0 26px rgba(216,178,90,${brilho})` : 'none',
              }}
            >
              {palavra}
            </span>{' '}
          </React.Fragment>
        );
      })}
    </h1>
  );
};

const Sub = ({html, duracao}) => (
  <p
    style={{
      ...useAnim('sub', duracao),
      margin: 0,
      fontSize: 27,
      lineHeight: 1.5,
      color: cores.muted,
      maxWidth: '34ch',
    }}
    dangerouslySetInnerHTML={{__html: html}}
  />
);

const Duas = ({two, duracao}) => {
  const frame = useCurrentFrame();
  const anim = useAnim('two', duracao);

  const coluna = (rotulo, texto, cor, atrasoExtra) => {
    // cada coluna entra um pouco depois da outra
    const de = (ritmo.atrasos.two + atrasoExtra) * FPS;
    const ate = de + ritmo.entrada * FPS;
    const op = interpolate(frame, [de, ate], [0, 1], travar);
    const x = interpolate(frame, [de, ate], [-14, 0], {...travar, easing: suave});
    const alturaRegua = interpolate(frame, [de, ate + 0.3 * FPS], [0, 100], travar);
    return (
      <div style={{maxWidth: '26ch', opacity: op, transform: `translateX(${x}px)`, display: 'flex', gap: 14}}>
        <span style={{width: 2, height: `${alturaRegua}%`, background: cor, flexShrink: 0, opacity: 0.55}} />
        <div>
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
      </div>
    );
  };

  return (
    <div style={{opacity: anim.opacity, transform: anim.transform, display: 'flex', gap: 48, flexWrap: 'wrap', marginTop: 6}}>
      {coluna(two.is[0], two.is[1], cores.gold, 0)}
      {coluna(two.isnot[0], two.isnot[1], cores.vermelhoSuave, 0.18)}
    </div>
  );
};

const Cta = ({children, duracao}) => {
  const frame = useCurrentFrame();
  const anim = useAnim('cta', duracao);
  // a seta continua avançando devagar, pra linha não morrer parada
  const desliza = interpolate(frame, [ritmo.atrasos.cta * FPS, duracao], [0, 10], travar);
  return (
    <div
      style={{
        ...anim,
        fontFamily: fontes.mono,
        color: cores.gold,
        fontSize: 18,
        letterSpacing: '0.06em',
        marginTop: 10,
        display: 'flex',
        gap: 10,
      }}
    >
      <span style={{transform: `translateX(${desliza}px)`}}>→</span>
      <span>{children}</span>
    </div>
  );
};

// Círculo dourado de fundo — gira e respira devagar durante todo o slide.
const Anel = ({posicao, duracao}) => {
  const frame = useCurrentFrame();
  const giro = interpolate(frame, [0, duracao], [0, 14]);
  const escala = interpolate(frame, [0, duracao / 2, duracao], [1, 1.06, 1]);
  const base = {
    position: 'absolute',
    borderRadius: '50%',
    border: `1px solid ${cores.goldLinha}`,
    background: 'radial-gradient(circle at 50% 50%, rgba(216,178,90,.05), transparent 62%)',
    transform: `rotate(${giro}deg) scale(${escala})`,
  };
  if (posicao === 'dois') {
    return <div style={{...base, width: 410, height: 410, left: -269, bottom: -173, opacity: 0.7}} />;
  }
  return <div style={{...base, width: 496, height: 496, right: -154, top: -108}} />;
};

export const Slide = ({slide, indice, duracao}) => {
  const frame = useCurrentFrame();

  // deriva contínua: o bloco de conteúdo sobe alguns pixels ao longo do slide e
  // cresce quase imperceptivelmente. É o que impede o quadro de parecer congelado.
  const deriva = interpolate(frame, [0, duracao], [0, -12]);
  const zoom = interpolate(frame, [0, duracao], [1, 1.016]);

  // marca d'água do número: deriva no sentido contrário, criando profundidade
  const derivaNumero = interpolate(frame, [0, duracao], [0, 16]);
  const opacidadeNumero = interpolate(frame, [0, duracao / 2, duracao], [0.04, 0.075, 0.04]);

  return (
    <div style={{position: 'absolute', inset: 0, fontFamily: fontes.sans}}>
      {slide.audio ? <Audio src={staticFile(slide.audio)} /> : null}
      {slide.ring ? <Anel posicao={slide.ring} duracao={duracao} /> : null}

      <div
        style={{
          position: 'absolute',
          right: 115,
          bottom: 77,
          fontFamily: fontes.serif,
          fontWeight: 700,
          fontSize: 320,
          lineHeight: 0.7,
          color: `rgba(216,178,90,${opacidadeNumero})`,
          transform: `translateY(${derivaNumero}px)`,
        }}
      >
        {String(indice + 1).padStart(2, '0')}
      </div>

      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          padding: 112,
          gap: 26,
          transform: `translateY(${deriva}px) scale(${zoom})`,
          transformOrigin: 'left center',
        }}
      >
        <Eyebrow duracao={duracao}>{slide.eyebrow}</Eyebrow>
        <Titulo html={slide.h1} duracao={duracao} />
        {slide.sub ? <Sub html={slide.sub} duracao={duracao} /> : null}
        {slide.two ? <Duas two={slide.two} duracao={duracao} /> : null}
        {slide.cta ? <Cta duracao={duracao}>{slide.cta}</Cta> : null}
      </div>
    </div>
  );
};
