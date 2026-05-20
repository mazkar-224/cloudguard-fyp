import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    // Tailwind v4 works as a Vite plugin — no postcss.config.js needed
    tailwindcss(),
  ],

  server: {
    // Proxy /api calls to the FastAPI backend so we don't get CORS errors
    // in development. e.g. fetch('/api/v1/costs/summary') → localhost:8000
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
