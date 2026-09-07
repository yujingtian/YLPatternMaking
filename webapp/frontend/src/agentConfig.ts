// agent 提取服务的唯一 base 来源（一期前端接线 §10.9）：
//   dev  缺省 '/agent' -> Vite proxy -> http://localhost:8001
//   prod 缺省 '/agent' -> webapp backend /agent/{path} httpx 同源转发
//   特殊部署可用构建变量 VITE_AGENT_BASE 覆盖（绝对地址，此时自负 CORS 责任）
export const AGENT_BASE: string = import.meta.env.VITE_AGENT_BASE ?? '/agent'
