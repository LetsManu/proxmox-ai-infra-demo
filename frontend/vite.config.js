import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// In development, /api is proxied to the FastAPI backend.
// In Docker, nginx serves the built files and proxies /api (see nginx.conf).
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: process.env.VITE_API_TARGET || 'http://localhost:8000', changeOrigin: true },
    },
  },
})
