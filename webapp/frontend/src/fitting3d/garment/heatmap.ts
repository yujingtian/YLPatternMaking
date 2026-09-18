// 穿台热力图（2026-09-18 十期后补）：双通道标量场 + 色映射，纯函数
// 不触渲染。用户拍板口径（AskUserQuestion）：**双通道切换**——
//   gap 间隙 = 布离身体距离（贴身≈0/适中余量/松垮悬空）→ 看松量分布
//   strain 应变 = 布料网格被拉伸程度（绷紧=偏小信号/压缩=堆布）→ 看偏小
// 两者互补一个开关切换，色带沿用一期口径**红紧/绿贴(适中)/蓝松**。
// · gap 逐粒子 = nearestRingBoundary − CORE_SKIN（与 collide 推出位同
//   口径：0 = 恰在接触壳上、负 = 穿透；无环行/超 margin 钳 gapMax 松端）
// · strain 逐顶点 = 参与的 dist 约束 (len−rest)/rest 的 signed 最大值
//   （最被拉长的一条边；rest = 纸样净长）
// · 开关切换只重着色当前帧，不重跑仿真（heatmap.ts 无状态）
import type { DrapeSim } from './drape'
import { CORE_SKIN } from './core'
import { nearestRingBoundary } from './placement'
import { HEAT_PRIOR } from './priors'

export type HeatMode = 'gap' | 'strain'

// 逐粒子标量。field 为 null（旁挂自由垂）时 gap 通道无意义 → 全 0 中性
export function computeHeat(sim: DrapeSim, mode: HeatMode): Float32Array {
  const n = sim.pos.length / 3
  const out = new Float32Array(n)
  if (mode === 'gap') {
    if (sim.field === null) return out
    const margin = CORE_SKIN + HEAT_PRIOR.gapMax
    for (let i = 0; i < n; i++) {
      const x = sim.pos[3 * i], y = sim.pos[3 * i + 1], z = sim.pos[3 * i + 2]
      const rings = sim.field.loopsAt(y - sim.yLift)
      if (rings.length === 0) { out[i] = HEAT_PRIOR.gapMax; continue }
      const hit = nearestRingBoundary(rings, x, z, margin)
      out[i] = hit === null ? HEAT_PRIOR.gapMax : hit.d - CORE_SKIN
    }
  } else {
    // strain：三角网格每顶点至少连一条 dist 边，NaN 哨兵兜底无约束顶点
    out.fill(NaN)
    for (const part of sim.parts) {
      const off = part.offset, dist = part.mesh.dist
      for (let c = 0; c < dist.length; c += 3) {
        const ia = off + dist[c], ib = off + dist[c + 1], rest = dist[c + 2]
        const a = 3 * ia, b = 3 * ib
        const len = Math.sqrt(
          (sim.pos[a] - sim.pos[b]) ** 2
          + (sim.pos[a + 1] - sim.pos[b + 1]) ** 2
          + (sim.pos[a + 2] - sim.pos[b + 2]) ** 2)
        const s = rest > 1e-9 ? (len - rest) / rest : 0
        if (!(s <= out[ia])) out[ia] = s   // NaN 哨兵下同 max
        if (!(s <= out[ib])) out[ib] = s
      }
    }
    for (let i = 0; i < n; i++) {
      if (!Number.isFinite(out[i])) out[i] = 0
    }
  }
  return out
}

// 色带停靠点（红紧 → 绿适中 → 蓝松，线性两段插值）
const RED: [number, number, number] = [1.0, 0.25, 0.2]
const GREEN: [number, number, number] = [0.3, 0.8, 0.35]
const BLUE: [number, number, number] = [0.25, 0.45, 0.95]

// v → RGB。gap：t = clamp(gap/gapMax)（穿透负值 → 0 红）；strain：
// t = clamp((strainMax−s)/2strainMax)（+max 拉伸绷紧 → 0 红 / 0 绿 /
// −max 压缩堆布 → 1 蓝——红紧/蓝松两通道同向）
export function heatColor(v: number, mode: HeatMode): [number, number, number] {
  let t: number
  if (mode === 'gap') {
    t = Math.max(0, Math.min(1, v / HEAT_PRIOR.gapMax))
  } else {
    t = Math.max(0, Math.min(1,
      (HEAT_PRIOR.strainMax - v) / (2 * HEAT_PRIOR.strainMax)))
  }
  const lerp = (
    a: [number, number, number], b: [number, number, number], f: number,
  ): [number, number, number] => [a[0] + (b[0] - a[0]) * f,
    a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f]
  return t <= 0.5 ? lerp(RED, GREEN, t * 2) : lerp(GREEN, BLUE, t * 2 - 1)
}
