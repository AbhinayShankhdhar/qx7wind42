import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development, /api calls are forwarded to the Python backend.
// Docker sets API_PROXY_TARGET=http://backend:8000; locally it defaults to localhost.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      // '/api': process.env.API_PROXY_TARGET || 'http://localhost:8000',
      '/api': process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
    },
  },
})
