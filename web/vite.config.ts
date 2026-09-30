import react from '@vitejs/plugin-react';
import path from 'path';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  // The repo root holds the .env both services read. Loaded with no prefix, so
  // the agent token is available here and still never shipped to the browser:
  // it is used only by the dev proxy below, which runs in Node.
  const env = loadEnv(mode, path.resolve(__dirname, '..'), '');
  const agentToken = env.ASSISTANT_AGENT_TOKEN ?? '';

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        '/ws': {
          target: 'ws://localhost:8000',
          ws: true,
        },
        // The agent's docs surface: graph diagrams and traces. Read-only, and
        // reachable only through this proxy, which holds the shared token so the
        // browser never does.
        '/agent': {
          target: 'http://localhost:8001',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/agent/, ''),
          headers: agentToken ? { 'x-agent-token': agentToken } : undefined,
        },
      },
    },
  };
});
