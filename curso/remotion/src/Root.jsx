import React from 'react';
import {Composition} from 'remotion';
import {Deck} from './Deck.jsx';
import {FPS} from './theme.js';
import {aula1} from './aulas/aula1.js';

// Duração de cada slide em frames. Se o slide tem narração (campo `audio`),
// a duração vem do próprio MP3 — é isso que dá o sync automático com a voz.
// Sem MP3, usa o campo `segundos`.
const calcularFrames = async (slides) => {
  let getAudioDurationInSeconds = null;
  let staticFile = null;
  if (slides.some((s) => s.audio)) {
    ({getAudioDurationInSeconds} = await import('@remotion/media-utils'));
    ({staticFile} = await import('remotion'));
  }

  return Promise.all(
    slides.map(async (slide) => {
      if (slide.audio && getAudioDurationInSeconds) {
        try {
          const segundos = await getAudioDurationInSeconds(staticFile(slide.audio));
          // meio segundo de respiro no fim de cada narração
          return Math.round((segundos + 0.5) * FPS);
        } catch (erro) {
          console.warn(`[aula] não consegui ler ${slide.audio}, usando "segundos": ${erro.message}`);
        }
      }
      return Math.round(slide.segundos * FPS);
    })
  );
};

const aulas = [aula1];

export const Root = () => (
  <>
    {aulas.map((aula) => (
      <Composition
        key={aula.id}
        id={aula.id}
        component={Deck}
        fps={FPS}
        width={1920}
        height={1080}
        durationInFrames={Math.round(aula.slides.reduce((t, s) => t + s.segundos, 0) * FPS)}
        defaultProps={{slides: aula.slides, frames: aula.slides.map((s) => Math.round(s.segundos * FPS))}}
        calculateMetadata={async ({props}) => {
          const frames = await calcularFrames(props.slides);
          return {
            durationInFrames: frames.reduce((t, f) => t + f, 0),
            props: {...props, frames},
          };
        }}
      />
    ))}
  </>
);
