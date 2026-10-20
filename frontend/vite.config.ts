import { rmSync } from 'node:fs';
import { resolve } from 'node:path';
import { defineConfig, loadEnv } from 'vite';

// MATCHMIND_API_PORT lets browser tests run against their own backend; the default is unchanged.
const api = `127.0.0.1:${process.env.MATCHMIND_API_PORT ?? '8000'}`;

export default defineConfig(({ mode }) => {
  const research = loadEnv(mode, process.cwd(), 'VITE_').VITE_ENABLE_RESEARCH === 'true';
  return {
    server: { proxy: { '/api': `http://${api}`, '/ws': { target: `ws://${api}`, ws: true } } },
    plugins: [{
      // The product uses synthetic data only: real research datasets are not shipped in a build
      // unless VITE_ENABLE_RESEARCH=true.
      name: 'exclude-research-data',
      apply: 'build',
      closeBundle() {
        if (research) return;
        for (const folder of ['tracking', 'datasets']) rmSync(resolve('dist', folder), { recursive: true, force: true });
      },
    }],
  };
});
