/// <reference types="vite/client" />

// 项目自定义构建变量（agentConfig.ts / msBase.ts）：
//   VITE_AGENT_BASE：agent 服务绝对地址覆盖（缺省 '/agent' 走同源转发，
//   设为绝对地址时该地址须自行放行 CORS）
//   VITE_MS_BASE：MS API 通道绝对地址覆盖（缺省 '/ms' 走同源转发）；配置
//   时 resolveMsChannel 跳过本地探测直取该地址为直连通道（运维钉死通道）
//   VITE_MS_WORKBENCH_URL：MS 工作台引导链接覆盖（缺省直连 MS 服务根，
//   见 msBase.ts 注——整页应用不走代理前缀；恒优先于通道跟随）
interface ImportMetaEnv {
  readonly VITE_AGENT_BASE?: string
  readonly VITE_MS_BASE?: string
  readonly VITE_MS_WORKBENCH_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
