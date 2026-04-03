import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/ingest': { target: 'http://localhost:8000', changeOrigin: true, timeout: 300000 },
      '/recommend': { target: 'http://localhost:8000', changeOrigin: true, timeout: 300000 },
      '/graph': { target: 'http://localhost:8000', changeOrigin: true, timeout: 300000 },
      '/chat': { target: 'http://localhost:8000', changeOrigin: true, timeout: 300000 },
    }
  }
})
