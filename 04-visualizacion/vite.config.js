import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: { port: 5173, strictPort: true },
  // `npm run preview` (plan B local del build de producción): imita el proxy /api que hace Amplify.
  preview: {
    proxy: {
      '/api': {
        target: 'https://i5rev77icbkeissqixiw6h5soi0npkxh.lambda-url.us-east-1.on.aws',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
  build: {
    target: 'es2020',
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        // ECharts va en su propio archivo: solo se descarga al entrar a /analitica o /como-funciona.
        manualChunks(id) {
          if (id.includes('node_modules/echarts') || id.includes('node_modules/zrender') || id.includes('node_modules/vue-echarts')) return 'echarts'
        },
      },
    },
  },
  test: { environment: 'jsdom', include: ['tests/**/*.test.js'] },
})
