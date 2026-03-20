import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const additionalAllowedHosts = [
  process.env.__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS,
  process.env.VITE_ALLOWED_HOSTS
]
  .filter(Boolean)
  .flatMap(value => value.split(','))
  .map(host => host.trim())
  .filter(Boolean)

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    open: true,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:5001',
        changeOrigin: true,
        secure: false
      }
    }
  }
})
