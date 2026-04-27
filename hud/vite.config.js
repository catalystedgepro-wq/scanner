import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  base: '/cerebro/app/',
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
    dedupe: ['three'],
  },
  server: {
    port: 5173,
    host: true,
  },
  build: {
    outDir: '../docs/hud',
    emptyOutDir: true,
    target: 'es2022',
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('react-force-graph-3d')) return 'vendor-force-graph'
          if (id.includes('/three/') || id.includes('\\three\\')) return 'vendor-three'
          if (id.includes('/react/') || id.includes('\\react\\') || id.includes('/react-dom/') || id.includes('\\react-dom\\')) {
            return 'vendor-react'
          }
        },
      },
    },
  },
})
