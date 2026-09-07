/// <reference types="vite/client" />

// 项目自定义构建变量（agentConfig.ts）：
//   VITE_AGENT_BASE：agent 服务绝对地址覆盖（缺省 '/agent' 走同源转发，
//   设为绝对地址时该地址须自行放行 CORS）
interface ImportMetaEnv {
  readonly VITE_AGENT_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
