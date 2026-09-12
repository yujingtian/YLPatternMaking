// 围度闭环标定：求 8 个 measure target 权重，使 morph 后网格在**payload
// 站点高度**的切片围度逼近体型目标（±1.5%，同环标定口径）。
// 反演 = **运行时前向差分实测雅可比**（2026-09-11 二轮报障重构）：targets.json
// 预标定三点表是单 target 对角近似，忽略场间耦合（如原生 hips± 在 thigh 站
// 贡献 ~+6.6cm/w、比 thigh± 自身 +4.1 还强）——对角迭代虽收敛但落在**大对
// 消权重**上（hips− 与 thigh− 互相打架），放大成用户可见的「不平整」；差分
// 雅可比在当前权重点实测 4×4 真耦合（含 target 顶点 y 迁移效应），
// Gauss-Jordan 联立解出**最小权重**，杜绝对消。三点表降级为诊断元数据
// （vendor 金标仍把守 target 对位）。
// incr/decr 按误差符号分流（永不同时非零）；阻尼联合迭代；不收敛（目标超
// 网格可达域）分档钳界并回传残差（诚实降级）：thigh±/knee±/hips± = 派生径向
// 保形场（cos² 平滑、w=2 已验收）宽钳 weightClamp——knee± 2026-09-11 起
// 同为派生场（原生弃用：上缘 y57-66 纯内侧 −x 剪切把大腿中段往中线拖 +
// canonical 站错位 + 满钳 1.0 可达 40.8 够不着常见输入 43~46 → 常年满钳
// 剪切边永久生效）；hips± 2026-09-12 同因替换为躯干径向场（原生拉力剖面
// y79 0.71 → y81 0.66 凹 → y83 1.15 跳升的非单调台阶指纹 + 基网格裆线
// 平台 →「平顶+陡崖」方形折角，且满钳 -1 可达 83.1 够不着小臀输入）；
// waist± = MakeHuman 原生 target 钳
// nativeWeightClamp=1（作者化域 [0,1] 之外的位移分布未作者化——外推实测
// 过髋部大转凸包/大腿波浪，两轮报障）。
import { BODYMESH_PRIOR } from '../priors'
import type { BodyMeshAsset, TargetName } from './types'
import { morphPositions } from './morph'
import { stationGirth } from './slice'

export interface CalibTargets {
  waist: number
  hip: number
  thigh: number
  knee: number
}

export interface CalibResult {
  weights: Partial<Record<TargetName, number>>
  /** 各站相对残差 (measured−target)/target（诊断/披露；正=偏大） */
  residual: Record<'waist' | 'hips' | 'thigh' | 'knee', number>
  converged: boolean
}

// 站点名映射：BodyProfile/girths 用 hip，morph target 用 hips
type MK = 'waist' | 'hips' | 'thigh' | 'knee'
const ST_KEYS = [
  ['waist', 'waist'], ['hip', 'hips'], ['thigh', 'thigh'], ['knee', 'knee'],
] as const

type Weights = Partial<Record<TargetName, number>>

export function calibrateWeights(
  asset: BodyMeshAsset,
  targets: CalibTargets,
  /** mesh 原生坐标下的站点高度（payload 站经 unmapY） */
  stationYmesh: Record<MK, number>,
): CalibResult {
  const weights: Weights = {}
  const residual: Record<MK, number> = { waist: 0, hips: 0, thigh: 0, knee: 0 }
  let converged = false

  const measure = (w: Weights) => {
    const pos = morphPositions(asset, w)
    const out: Record<string, number> = {}
    for (const [gk, mk] of ST_KEYS) {
      const g = stationGirth(pos, asset.indices, stationYmesh[mk],
        mk === 'thigh' || mk === 'knee' ? 'leg' : 'body')
      out[gk] = g ?? NaN
    }
    return out
  }

  // 符号化等效权重（incr/decr 永不同时非零的读写两侧）
  const signed = (mk: MK) =>
    (weights[`${mk}+` as TargetName] ?? 0) - (weights[`${mk}-` as TargetName] ?? 0)
  const withSigned = (mk: MK, v: number): Weights => ({
    ...weights,
    [`${mk}+`]: v > 0 ? v : 0,
    [`${mk}-`]: v < 0 ? -v : 0,
  })

  const N = ST_KEYS.length
  const h = BODYMESH_PRIOR.calibFdStep

  for (let iter = 0; iter < BODYMESH_PRIOR.calibIters; iter++) {
    const g = measure(weights)
    converged = true
    const need: number[] = []
    for (let i = 0; i < N; i++) {
      const [gk, mk] = ST_KEYS[i]
      const err = (g[gk] - targets[gk]) / targets[gk]
      residual[mk] = err
      // NaN（切片失败）不得静默判收敛——NaN 比较恒 false 会把 converged
      // 留在 true、权重停在 w=0 出「未标定人台」
      if (!Number.isFinite(err) || Math.abs(err) > BODYMESH_PRIOR.calibTol) {
        converged = false
      }
      need.push(targets[gk] - g[gk])          // cm 缺口（正=要变大）
    }
    if (converged) break

    // 前向差分实测雅可比 J[j][i] = ∂g_j/∂w_i。扰动方向取该站需求方向：
    // +/− 是两个不同位移场，需求的反向场测不出正确响应。**分母必须带
    // dir**——withSigned 在 dir=−1 时等效改变的是 −h，除以 +h 会让所有
    // 缩小方向的站斜率反号、求解器满舵冲向 +钳（合成测试全正需求测不出，
    // 真数据腰/臀全部变小才暴露，2026-09-11）
    const J: number[][] = Array.from({ length: N }, () => new Array(N).fill(0))
    for (let i = 0; i < N; i++) {
      const mk = ST_KEYS[i][1]
      const dir = need[i] >= 0 ? 1 : -1
      const gp = measure(withSigned(mk, signed(mk) + h * dir))
      for (let j = 0; j < N; j++) {
        const v = (gp[ST_KEYS[j][0]] - g[ST_KEYS[j][0]]) / (h * dir)
        J[j][i] = Number.isFinite(v) ? v : 0
      }
    }
    const dw = solveLinear(J, need)
    for (let i = 0; i < N; i++) {
      const mk = ST_KEYS[i][1]
      if (!Number.isFinite(dw[i])) continue
      // 分档钳界：thigh±/knee±/hips± 派生场平滑可外推（宽钳），原生 target 钳回
      // 作者化域（knee± 已派生替换 2026-09-11、hips± 2026-09-12 同因——原生
      // 拉力剖面非单调台阶指纹 + 满钳不可达常见小臀输入，见头注）
      const clamp = mk === 'thigh' || mk === 'knee' || mk === 'hips'
        ? BODYMESH_PRIOR.weightClamp : BODYMESH_PRIOR.nativeWeightClamp
      const nw = Math.max(-clamp,
        Math.min(clamp, signed(mk) + dw[i] * BODYMESH_PRIOR.calibDamping))
      weights[`${mk}+` as TargetName] = nw > 0 ? nw : 0
      weights[`${mk}-` as TargetName] = nw < 0 ? -nw : 0
    }
  }
  const g = measure(weights)
  for (const [gk, mk] of ST_KEYS) {
    residual[mk] = Number.isFinite(g[gk])
      ? (g[gk] - targets[gk]) / targets[gk] : NaN
  }
  return { weights, residual, converged }
}

// n×n 线性求解 A·x=b（Gauss-Jordan 带部分主元；奇异回退对角步进——
// |A[i][i]| 微小的站不动，交给下一轮差分；合成网格无全部 8 个 target 时
// 常态走此回退）
function solveLinear(A: number[][], b: number[]): number[] {
  const n = b.length
  const M = A.map((row, i) => [...row, b[i]])
  let ok = true
  for (let col = 0; col < n; col++) {
    let piv = col
    for (let r = col + 1; r < n; r++) {
      if (Math.abs(M[r][col]) > Math.abs(M[piv][col])) piv = r
    }
    if (Math.abs(M[piv][col]) < 1e-9) { ok = false; break }
    [M[col], M[piv]] = [M[piv], M[col]]
    for (let r = 0; r < n; r++) {
      if (r === col) continue
      const f = M[r][col] / M[col][col]
      for (let c = col; c <= n; c++) M[r][c] -= f * M[col][c]
    }
  }
  if (ok) {
    return M.map((row, i) => row[n] / row[i])
  }
  return A.map((row, i) => (Math.abs(row[i]) > 1e-6 ? b[i] / row[i] : 0))
}
