import React from 'react';
import {Composition, staticFile} from 'remotion';
import {getAudioDurationInSeconds} from '@remotion/media-utils';
import {Deck} from './Deck.jsx';
import {FPS} from './theme.js';
import {aula1} from './aulas/aula1.mjs';
import {aula2} from './aulas/aula2.mjs';
import {aula3} from './aulas/aula3.mjs';

const aulas = [aula1, aula2, aula3];

// Nome do MP3 de um slide, por convenção: Aula2_slide5.mp3 dentro de public/.
// É o mesmo nome que scripts/narrar.mjs grava, então não há nada pra ligar na mão.
export const nomeDoAudio = (idDaAula, indice) => `${idDaAula}_slide${indice + 1}.mp3`;

// Descobre a duração de cada slide: havendo narração gravada, a duração é a do próprio
// áudio (mais um respiro no fim); senão vale o campo `segundos`. O slide leva de volta o
// nome do arquivo, e é isso que faz o <Audio> entrar só quando o MP3 existe de verdade.
const montarSlides = async (aula) => {
  const respiro = 0.5;

  return Promise.all(
    aula.slides.map(async (slide, i) => {
      const arquivo = slide.audio ?? nomeDoAudio(aula.id, i);
      try {
        const segundos = await getAudioDurationInSeconds(staticFile(arquivo));
        return {...slide, audio: arquivo, frames: Math.round((segundos + respiro) * FPS)};
      } catch {
        // ainda sem narração gravada: usa a duração de reserva
        return {...slide, audio: null, frames: Math.round(slide.segundos * FPS)};
      }
    })
  );
};

export const Root = () => (
  <>
    {aulas.map((aula) => {
      const reserva = aula.slides.map((s) => Math.round(s.segundos * FPS));
      return (
        <Composition
          key={aula.id}
          id={aula.id}
          component={Deck}
          fps={FPS}
          width={1920}
          height={1080}
          durationInFrames={reserva.reduce((t, f) => t + f, 0)}
          defaultProps={{slides: aula.slides.map((s) => ({...s, audio: null})), frames: reserva}}
          calculateMetadata={async () => {
            const slides = await montarSlides(aula);
            const frames = slides.map((s) => s.frames);
            return {
              durationInFrames: frames.reduce((t, f) => t + f, 0),
              props: {slides, frames},
            };
          }}
        />
      );
    })}
  </>
);
