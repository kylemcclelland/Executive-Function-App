import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vitest/config'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    host: '0.0.0.0',
    port: 5173,
    // The Optima Pars backend (uvicorn runs on 8001 locally). Override with VITE_API_PROXY_TARGET
    // if the backend runs elsewhere; do NOT point this at another project's server on 8000.
    proxy: { '/api': process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8001' },
  },
  test: { environment: 'jsdom', setupFiles: './src/test/setup.ts', css: true },
})
