// MS 机器排料 config 构建器（二期对接 §10.3.2）：numMap（/api/nest 扁平
// 数量契约）+ 推板码表 + 幅宽/运行模式 → POST /api/machine/solve 的
// config JSON。buildMachineConfig 纯函数零副作用——提交载荷口径单一可测，
// 弹窗层（NestSolveModal）只做输入收集。映射口径：gate_mm = 幅宽 cm × 10；
// per_type 全 g 码恒 {d:0,tol:0}（= MS 缺省语义全等，三期工艺预设档才启用
// 非 0）；quantities 按 numMap 展开到每个码（/api/nest 扁平契约：各码数量
// 相同，内层键 = 数字字符串）。无单码分支——单码场景由调用侧前置拦截
// （二期仅推板多码），sizes 为空即视为非法输入响亮抛错。
import type { MsMachineConfig, MsRunMode } from './types'

// 运行模式三档（时间烘焙 MS 侧单一真相源：normal = plain --time 180 /
// advanced = --strategy race --time 1200 / extreme = --extreme --time 7200）。
// label 是 UI 唯一文案源（NestSolveModal select 直消费，勿在组件内复写）；
// budgetSec 与 MS status.total_budget_sec 对齐（进度条总时长口径）。
// 注意「高级/极限」= MS race/extreme 求解模式，非时长别名（§10.3.2 文档）
export interface RunModeOption {
  value: MsRunMode
  label: string
  budgetSec: number
}

export const RUN_MODE_OPTIONS: readonly RunModeOption[] = [
  { value: 'normal', label: '普通运行（180s）', budgetSec: 180 },
  { value: 'advanced', label: '高级运行（20min）', budgetSec: 1200 },
  { value: 'extreme', label: '极限运行（2h）', budgetSec: 7200 },
]

export const DEFAULT_GATE_CM = 175
export const DEFAULT_RUN_MODE: MsRunMode = 'normal'

export interface BuildMachineConfigInput {
  numMap: Record<string, number>   // /api/nest 扁平数量 {g码: 数量}
  labels?: Record<string, string>  // {g码: 中文名}；键集与 numMap 理论同源，
                                   // 并集兜底（独有键数量回退 0）
  sizes: string[]                  // 推板码表（须纯整数字串，如 '29'/'30'）
  gateCm?: number                  // 幅宽 cm（缺省 175）
  runMode?: MsRunMode              // 运行模式（缺省 normal）
}

// 整数码号守卫（MS sizes 仅接受 int[]；码表 labels 经后端
// assert_numeric_labels 理论已保证纯数字，此处独立守卫——构建器可被
// 直接调用/单测，不依赖上游已验）
const INT_CODE_RE = /^\d+$/

export function buildMachineConfig(
  input: BuildMachineConfigInput,
): MsMachineConfig {
  const { numMap, labels, sizes, gateCm = DEFAULT_GATE_CM,
          runMode = DEFAULT_RUN_MODE } = input

  if (sizes.length === 0)
    throw new Error('码表为空：机器排料需要推板多码（至少一个码号）')
  for (const s of sizes)
    if (!INT_CODE_RE.test(s))
      throw new Error(`码号「${s}」不是纯整数字：MS sizes 仅接受整数码（如 29、30）`)
  if (!Number.isFinite(gateCm) || gateCm <= 0)
    throw new Error(`幅宽非法（${gateCm}）：须为正数（cm）`)
  if (!RUN_MODE_OPTIONS.some((o) => o.value === runMode))
    throw new Error(`未知运行模式「${runMode}」：可选 normal/advanced/extreme`)

  // g 码键集 = numMap ∪ labels（后端同一次遍历产出，理论同源；并集兜底，
  // labels 独有键数量回退 0 = MS demand=0 跳过该片，语义安全）
  const gCodes = [...new Set([...Object.keys(numMap),
    ...Object.keys(labels ?? {})])]
  if (gCodes.length === 0)
    throw new Error('排料数量清单为空：无法生成机器排料配置')

  const per_type: MsMachineConfig['per_type'] = {}
  const quantities: MsMachineConfig['quantities'] = {}
  for (const g of gCodes) {
    per_type[g] = { d: 0, tol: 0 }
    quantities[g] = {}
    for (const s of sizes) quantities[g][s] = numMap[g] ?? 0
  }
  return {
    // round 防浮点尾差（175.3×10 = 1752.9999…）；cm 一位小数 ×10 后恒整
    gate_mm: Math.round(gateCm * 10),
    sizes: sizes.map((s) => parseInt(s, 10)),
    run_mode: runMode,
    per_type,
    quantities,
  }
}
