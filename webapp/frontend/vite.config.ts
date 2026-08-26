import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // 引擎 worker（src/engine/worker.ts）动态 import('pyodide') 产生代码
  // 分割，须 ES 格式 module worker（现代浏览器均支持；iife 不支持分包）
  worker: { format: 'es' },
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
})
