import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import {fileURLToPath, URL} from 'node:url'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {alias: {'@': fileURLToPath(new URL('.', import.meta.url))}},
  build: {
    outDir: 'static', emptyOutDir: false,
    lib: {entry: 'src/widgets.tsx', formats: ['es'], fileName: () => 'widgets.js', cssFileName: 'widgets'},
  },
})
