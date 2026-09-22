// MS 排料服务（MaterialSorting）的唯一 base 来源（二期机器排料对接 §10.3.2）：
//   dev  缺省 '/ms' -> Vite proxy -> http://127.0.0.1:8010
//   prod 缺省 '/ms' -> webapp backend /ms/{path} httpx 同源转发
//   特殊部署可用构建变量 VITE_MS_BASE 覆盖（绝对地址，此时自负 CORS 责任）
export const MS_BASE: string = import.meta.env.VITE_MS_BASE ?? '/ms'

// MS 排料工作台（版师日常访问地址，三期 .msn 引导链接用）：缺省直连 MS
// 服务根（:8010 静态托管工作台页）——刻意不走 '/ms' 代理前缀（那是 API 通道；
// 工作台是整页 Web 应用，内部绝对路径资源 /static/… 经代理前缀必 404），
// 特殊部署可构建变量 VITE_MS_WORKBENCH_URL 覆盖
export const MS_WORKBENCH_URL: string =
  import.meta.env.VITE_MS_WORKBENCH_URL ?? 'http://127.0.0.1:8010/'
