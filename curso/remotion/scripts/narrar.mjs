#!/usr/bin/env node
// Gera a narração de uma aula no ElevenLabs: um MP3 por slide, direto do campo
// `narracao` do arquivo da aula. Os arquivos saem em public/ com o nome que o
// Root.jsx procura, então depois é só renderizar — nada pra ligar na mão.
//
//   node scripts/narrar.mjs Aula2           # só o que ainda não existe
//   node scripts/narrar.mjs Aula2 --refazer # regrava tudo
//   node scripts/narrar.mjs Aula2 --slide 3 # só o slide 3
//
// Usa as mesmas variáveis do narracao_ia.py do Jarvis, lidas do .env da raiz do
// projeto (ou do ambiente):
//   ELEVENLABS_API_KEY    obrigatória
//   ELEVENLABS_VOICE_ID   obrigatória — id da voz PT-BR
//   ELEVENLABS_MODEL      opcional (padrão eleven_multilingual_v2)
//   ELEVENLABS_STABILITY / _SIMILARITY / _STYLE / _SPEED   opcionais

import {existsSync, readFileSync, mkdirSync, writeFileSync, statSync} from 'node:fs';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const AQUI = dirname(fileURLToPath(import.meta.url));
const PROJETO = resolve(AQUI, '..');
const PUBLIC = join(PROJETO, 'public');
const RAIZ_REPO = resolve(PROJETO, '..', '..');

const API = 'https://api.elevenlabs.io/v1/text-to-speech';

// --- .env ------------------------------------------------------------------
// Mesmo formato que o narracao_ia.py lê: KEY=valor, com # de comentário.
const carregarEnv = () => {
  for (const candidato of [join(RAIZ_REPO, '.env'), join(PROJETO, '.env')]) {
    if (!existsSync(candidato)) continue;
    for (let linha of readFileSync(candidato, 'utf8').split('\n')) {
      linha = linha.trim();
      if (!linha || linha.startsWith('#') || !linha.includes('=')) continue;
      if (linha.toLowerCase().startsWith('export ')) linha = linha.slice(7);
      const corte = linha.indexOf('=');
      const chave = linha.slice(0, corte).trim();
      const valor = linha.slice(corte + 1).trim().replace(/^["']|["']$/g, '');
      if (chave && !(chave in process.env)) process.env[chave] = valor;
    }
    return candidato;
  }
  return null;
};

const numero = (nome, padrao) => {
  const bruto = process.env[nome];
  const valor = bruto === undefined || bruto === '' ? NaN : Number(bruto);
  return Number.isFinite(valor) ? valor : padrao;
};

// --- argumentos ------------------------------------------------------------
const args = process.argv.slice(2);
const idDaAula = args.find((a) => !a.startsWith('--'));
const refazer = args.includes('--refazer');
const posSlide = args.indexOf('--slide');
const apenasSlide = posSlide >= 0 ? Number(args[posSlide + 1]) : null;

if (!idDaAula) {
  console.error('Falta o id da aula. Exemplo: node scripts/narrar.mjs Aula2');
  process.exit(1);
}

// --- corpo -----------------------------------------------------------------
const principal = async () => {
  const env = carregarEnv();
  console.log(env ? `.env lido de ${env}` : 'sem .env — usando só as variáveis do ambiente');

  const chave = process.env.ELEVENLABS_API_KEY ?? '';
  const voz = process.env.ELEVENLABS_VOICE_ID ?? '';
  const modelo = process.env.ELEVENLABS_MODEL || 'eleven_multilingual_v2';

  if (!chave || !voz) {
    console.error(
      '\nFaltam credenciais: defina ELEVENLABS_API_KEY e ELEVENLABS_VOICE_ID\n' +
        'no .env da raiz do projeto ou como variáveis de ambiente.\n' +
        'São as mesmas que o narracao_ia.py já usa.'
    );
    process.exit(1);
  }

  const arquivoDaAula = join(PROJETO, 'src', 'aulas', `${idDaAula.toLowerCase()}.mjs`);
  if (!existsSync(arquivoDaAula)) {
    console.error(`Não achei ${arquivoDaAula}`);
    process.exit(1);
  }
  const modulo = await import(`file://${arquivoDaAula}`);
  const aula = modulo[idDaAula.toLowerCase()] ?? Object.values(modulo)[0];

  // mesmos ajustes de voz do narracao_ia.py, pra narração do curso soar como o resto
  const ajustes = {
    stability: numero('ELEVENLABS_STABILITY', 0.45),
    similarity_boost: numero('ELEVENLABS_SIMILARITY', 0.75),
    style: numero('ELEVENLABS_STYLE', 0.4),
    use_speaker_boost: true,
  };
  const velocidade = numero('ELEVENLABS_SPEED', 1.0);
  if (velocidade !== 1.0) ajustes.speed = Math.max(0.7, Math.min(1.2, velocidade));

  mkdirSync(PUBLIC, {recursive: true});
  console.log(`\n${aula.titulo} — ${aula.slides.length} slides | voz ${voz} | modelo ${modelo}\n`);

  let gerados = 0;
  let pulados = 0;

  for (const [i, slide] of aula.slides.entries()) {
    const n = i + 1;
    if (apenasSlide !== null && apenasSlide !== n) continue;

    const nome = `${aula.id}_slide${n}.mp3`;
    const destino = join(PUBLIC, nome);

    if (!slide.narracao) {
      console.log(`  ${n}. sem campo "narracao" — pulando`);
      pulados += 1;
      continue;
    }
    if (existsSync(destino) && !refazer) {
      console.log(`  ${n}. ${nome} já existe (use --refazer pra regravar)`);
      pulados += 1;
      continue;
    }

    const resposta = await fetch(`${API}/${voz}`, {
      method: 'POST',
      headers: {'xi-api-key': chave, 'Content-Type': 'application/json', Accept: 'audio/mpeg'},
      body: JSON.stringify({text: slide.narracao, model_id: modelo, voice_settings: ajustes}),
    });

    if (!resposta.ok) {
      const detalhe = (await resposta.text()).slice(0, 200);
      console.error(`  ${n}. falhou — HTTP ${resposta.status}: ${detalhe}`);
      process.exit(1);
    }

    writeFileSync(destino, Buffer.from(await resposta.arrayBuffer()));
    const kb = Math.round(statSync(destino).size / 1024);
    console.log(`  ${n}. ${nome} — ${kb} KB`);
    gerados += 1;
  }

  console.log(`\n${gerados} gerado(s), ${pulados} pulado(s).`);
  if (gerados > 0) {
    console.log(`Agora renderize: npx remotion render src/index.jsx ${aula.id} out/${aula.id.toLowerCase()}.mp4`);
    console.log('A duração de cada slide passa a ser a do áudio, automaticamente.');
  }
};

principal().catch((erro) => {
  console.error(`erro: ${erro.message}`);
  process.exit(1);
});
