// 排料终态回传存档编排层（四期机器对接 US-005，
// tasks/prd-machine-direct-channel.md；后端契约 US-004）：done 终态后前端
// 自动把 PLT + .msn + meta 回传 YL 后端落盘（out/nest_archive/<task_id>/
// 三件 + index.jsonl 索引）——排料历史不随 MS 侧任务 DELETE/TTL 消失，版师
// 可随时回查/续调。两通道（直连本地 MS / 代理服务器 MS）结果统一收口到
// YL 后端（archive 端点与任务绑定通道无关，PLT/.msn 取件仍走绑定通道）。
// 本模块收口三件纯逻辑（网络函数 archiveNest 在 apiHttp，同 postNest 先例
// 不进 route() 引擎通道）：
// - buildArchiveMeta：meta 字段集（前端口径，后端只透传落盘 + 索引）
// - shouldAutoArchive：done 自动触发判定（attemptedTaskId 去重防重发）
// - archiveNote：回传状态小字文案（busy/ok/fail；fail 附「不阻塞下载 +
//   可重试」引导，US-005 AC）
// 弹窗三态视图接线在 NestSolveModal（组件层零业务口径，全走本模块）。

import type { NestSolvePhase } from './hooks/useNestSolve'
import type { MsChannel } from './msBase'
import type {
  MsMachineConfig, MsResult, MsRunMode, MsStatus,
} from './types'

// 回传 meta（Form 字段 meta 的 JSON 串；后端只透传落盘 + 索引，字段集
// 前端口径 = PRD US-005：task_id/通道标记/density/width_mm/码套/seed/
// run_mode/时间）。density 保持 MS 原生分数口径（与 result.best.density
// 同源，下游工具可直接比对 MS 载荷），另附 density_pct 人类可读百分数；
// quantities 码套来自提交期 config 快照（attach 重连场景无快照 → null，
// 不臆造——套数本就不跨会话记忆，按提交现场为准）
export interface NestArchiveMeta {
  task_id: string
  channel: MsChannel
  density: number
  density_pct: number
  width_mm: number | null
  gate_mm: number
  seed: number | null
  run_mode: MsRunMode
  quantities: Record<string, Record<string, number>> | null
  started_at: string | null
  uploaded_at: string
}

export function buildArchiveMeta(src: {
  taskId: string
  // 任务绑定通道（solve.channel；null = 无任务在手的防御位，归 proxy——
  // 与 useNestSolve 锚点归一同款「未知即代理时代」口径）
  channel: MsChannel | null
  result: MsResult
  // 最后一拍 status（run_mode 权威值；attach 重连 config 缺席仍可取）
  status: MsStatus | null
  // 提交期 buildMachineConfig 快照（attach 重连场景 null）
  config: MsMachineConfig | null
  startedAt: string | null
  now?: Date
}): NestArchiveMeta {
  const d = src.result.best.density
  return {
    task_id: src.taskId,
    channel: src.channel ?? { kind: 'proxy' },
    density: d,
    density_pct: Math.round(d * 10_000) / 100,
    width_mm: src.result.best.width_mm,
    gate_mm: src.result.manifest.gate_mm,
    seed: src.result.best.seed,
    // run_mode 优先 MS status（attach 场景 config 缺席；status 是任务
    // 实际运行的权威值），回落提交 config，双缺归普通档（防御不臆造极端档）
    run_mode: src.status?.run_mode ?? src.config?.run_mode ?? 'normal',
    quantities: src.config?.quantities ?? null,
    started_at: src.startedAt,
    uploaded_at: (src.now ?? new Date()).toISOString(),
  }
}

// done 自动触发判定（US-005 AC）：done 终态 + 任务/结果在手即回传——
// stopped 是用户主动终止，不自动存档（PRD 口径只钉 done；不锁手动扩展）；
// attemptedTaskId 已触发过的任务不重发：effect 重渲染/StrictMode 双挂载/
// 关窗重开（modal 常驻挂载，phase 不回退）天然去重，失败重试只走手动按钮
export function shouldAutoArchive(
  phase: NestSolvePhase,
  taskId: string | null,
  result: MsResult | null,
  attemptedTaskId: string | null,
): boolean {
  if (phase !== 'done' || taskId === null) return false
  if (taskId === attemptedTaskId) return false
  // best 运行时判空（类型不约束运行时形态，同弹窗渲染侧防御）：无 best
  // 帧的 done 无 density 可记，不回传
  return result !== null && result.best != null
}

// 回传状态（结果区小字指示 + fail 手动重试出口的驱动；idle = 未触发
// 无事发生——stopped/error/取果失败期不渲染）
export type NestArchivePhase = 'idle' | 'busy' | 'ok' | 'fail'

export function archiveNote(
  phase: NestArchivePhase,
  message: string | null,
): string {
  switch (phase) {
    case 'busy': return '正在回传存档…'
    case 'ok': return '结果已回传存档（PLT / 状态文件 / 元数据）'
    // fail：消息 + AC 口径引导（不影响结果展示与下载，可重试）——
    // 下载入口与本状态互不相干（busy 态独立），文案明示防误关
    case 'fail':
      return `回传存档失败：${message ?? '未知错误'}。`
        + '不影响结果展示与下载，可点击重试'
    default: return ''
  }
}
