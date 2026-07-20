import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendUrl = env.VITE_BACKEND_URL || 'http://localhost:8000'
  const backendWs  = backendUrl.replace(/^http/, 'ws')

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
        target: backendUrl,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('error', (err) => {
            console.warn('[Vite proxy] Backend unreachable at ' + backendUrl + ':', err.message)
          })
        },
      },
      '/health': {
        target: backendUrl,
        changeOrigin: true,
      },
      '/ws': {
        target: backendWs,
        ws: true,
      },
    },
  },
  }
})
