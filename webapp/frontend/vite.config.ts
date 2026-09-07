import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // 引擎 worker（src/engine/worker.ts）动态 import('pyodide') 产生代码
  // 分割，须 ES 格式 module worker（现代浏览器均支持；iife 不支持分包）
  worker: { format: 'es' },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      // agent 提取服务（8001）同源化：/agent/api/extract -> 8001 /api/extract
      // （生产无 Vite，由 webapp backend 的 /agent/{path} httpx 转发兜同款前缀）
      '/agent': {
        target: 'http://localhost:8001',
        rewrite: (p) => p.replace(/^\/agent/, ''),
      },
    },
  },
})
