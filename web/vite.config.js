import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/analyze':   'http://localhost:8000',
      '/health':    'http://localhost:8000',
      '/settings':  'http://localhost:8000',
      '/portfolio': 'http://localhost:8000',
      '/monitor':   'http://localhost:8000',
      '/discover':     'http://localhost:8000',
      '/market-data':  'http://localhost:8000',
      '/run':          'http://localhost:8000',
      '/scout':        'http://localhost:8000',
    },
  },
})
