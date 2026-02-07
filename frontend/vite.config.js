import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    host: true,
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (!id.includes('node_modules')) {
            return;
          }
          if (id.includes('react-router')) {
            return 'router-vendor';
          }
          if (id.includes('recharts')) {
            return 'charts-vendor';
          }
          if (id.includes('framer-motion')) {
            return 'motion-vendor';
          }
          if (id.includes('react-query')) {
            return 'query-vendor';
          }
          return 'vendor';
        },
      },
    },
  },
})
