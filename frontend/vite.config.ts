import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  base: '/static/youtube/',
  build: {
    outDir: path.resolve(__dirname, '../static/youtube'),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8010',
    },
  },
})
