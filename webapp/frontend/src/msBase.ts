// MS 排料服务（MaterialSorting）的唯一 base 来源（二期机器排料对接 §10.3.2）：
//   dev  缺省 '/ms' -> Vite proxy -> http://127.0.0.1:8010
//   prod 缺省 '/ms' -> webapp backend /ms/{path} httpx 同源转发
//   特殊部署可用构建变量 VITE_MS_BASE 覆盖（绝对地址，此时自负 CORS 责任）
export const MS_BASE: string = import.meta.env.VITE_MS_BASE ?? '/ms'
