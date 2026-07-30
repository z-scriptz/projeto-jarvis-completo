import {Config} from '@remotion/cli/config';

Config.setVideoImageFormat('jpeg');
Config.setCodec('h264');
// 1 = melhor qualidade, 51 = pior. 18 mantém o gradiente verde sem banding.
Config.setCrf(18);
Config.setEntryPoint('./src/index.jsx');
