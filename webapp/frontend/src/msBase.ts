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

// ============ 双通道：直连本地 MS 优先 + /ms 代理回退（US-001）============
// （tasks/prd-machine-direct-channel.md）YL 部署服务器后 /ms 同源代理打的是
// 服务器自己的 loopback，连不到用户本地 MS——通道选择层在排料发起时探测
// 本地 VB超排（ping 8010..8019），命中走浏览器直连（本地算力），全败回退
// /ms 代理（服务器 MS，现状零改动）。地址恒 127.0.0.1 字面量：MS 只绑
// IPv4 loopback（localhost 可能解析 ::1 连不上），局域网 IP 在 HTTPS 部署
// 下被 mixed content 硬拦——127.0.0.1 是双重约束下唯一交集

// 直连候选端口族（MS launcher 从 8010 起逐个 +1 占端口）
export const MS_DIRECT_PORTS: readonly number[] = [
  8010, 8011, 8012, 8013, 8014, 8015, 8016, 8017, 8018, 8019,
]

// ping 探测超时（ms）：10 候选全并发，最坏墙钟 = 单档超时 ≈300ms（发起
// 预算 <1s 不拖慢）；超时/连接拒绝/CORS 预检失败/非 2xx 一律视为该端口
// 无可用 MS（跨源 fetch 失败在 JS 侧不可区分，天然归一 miss）
export const MS_PING_TIMEOUT_MS = 300

export type MsDirectChannel = { kind: 'direct'; base: string }
export type MsProxyChannel = { kind: 'proxy' }
export type MsChannel = MsDirectChannel | MsProxyChannel

// 会话级通道缓存 + 在飞去重：通道选择每页面会话只执行一次（PRD 设计口径
// ——弹窗轮询期间不重复探测，本地 MS 启停不影响进行中任务判定；后续故事
// 请求层每请求取通道也零网络成本）。会话中途装/启本地 MS 须刷新页面重新
// 探测；测试经 resetMsChannelCache 复位（seq 作废在飞探测的迟到回填）
let cachedChannel: MsChannel | null = null
let inflightProbe: Promise<MsChannel> | null = null
let probeSeq = 0

// 单轮探测：10 端口并发 GET /api/machine/ping（MS 侧无 token 无 task_id
// 的轻量端点，200 {ok,service} 恰两键），端口序首个 2xx 命中 → direct
// （launcher 从 8010 顺位占端口，多命中时低口优先——确定性归一）；全
// miss → proxy。永不 reject（所有失败路径归 null）
async function probeMsChannel(): Promise<MsChannel> {
  const attempts = MS_DIRECT_PORTS.map(
    async (port): Promise<MsDirectChannel | null> => {
      try {
        const res = await fetch(
          `http://127.0.0.1:${port}/api/machine/ping`,
          { signal: AbortSignal.timeout(MS_PING_TIMEOUT_MS) })
        return res.ok
          ? { kind: 'direct', base: `http://127.0.0.1:${port}` } : null
      } catch {
        return null
      }
    })
  const settled = await Promise.all(attempts)
  return settled.find((c): c is MsDirectChannel => c !== null)
    ?? { kind: 'proxy' }
}

// 通道解析（排料发起时调用，会话内幂等）：VITE_MS_BASE 显式覆盖优先于
// 探测（运维兜底——绝对地址即钉死直连通道，零探测网络成本；env 调用期
// 读取而非模块顶层求值，保可测性）；否则并发 ping 本地候选端口族，命中
// → direct 缓存 base，全败 → proxy（回退 /ms 代理连服务器 MS）
export async function resolveMsChannel(): Promise<MsChannel> {
  const override = import.meta.env.VITE_MS_BASE
  if (typeof override === 'string' && override)
    return { kind: 'direct', base: override }
  if (cachedChannel) return cachedChannel
  if (!inflightProbe) {
    const seq = ++probeSeq
    inflightProbe = probeMsChannel().then((channel) => {
      if (seq === probeSeq) cachedChannel = channel
      inflightProbe = null
      return channel
    })
  }
  return inflightProbe
}

// 测试钩子：清会话级通道缓存（生产代码不调用）
export function resetMsChannelCache(): void {
  probeSeq += 1
  cachedChannel = null
  inflightProbe = null
}

// 工作台引导链接通道化：三期 .msn「状态恢复」链接随直连发现端口走（工作
// 台与 API 同服务同端口静态托管）；proxy/未发现保持缺省 8010。
// VITE_MS_WORKBENCH_URL 显式覆盖恒优先（含 VITE_MS_BASE 钉远端 API 的
// 形态——工作台不自动跟随远端 base，运维须配套该变量；env 调用期读取，
// 与 resolveMsChannel 同款可测口径）
const LOCAL_MS_BASE_RE = /^http:\/\/127\.0\.0\.1:\d+$/

export function msWorkbenchUrl(channel?: MsChannel | null): string {
  const override = import.meta.env.VITE_MS_WORKBENCH_URL
  if (typeof override === 'string' && override) return override
  if (channel?.kind === 'direct' && LOCAL_MS_BASE_RE.test(channel.base))
    return `${channel.base}/`
  return MS_WORKBENCH_URL
}
