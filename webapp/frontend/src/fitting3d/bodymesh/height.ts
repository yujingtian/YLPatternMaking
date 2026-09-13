// 身高 macro 场纯函数（预设体型，2026-09-13）：**测量驱动、约定无关**——
// baseCm/plusCm/minusCm 全部来自 vendor 进程内对切割前全身网格的实测
// （targets.json meta.height，w=±1 的 max y 响应），预设权重 = 目标Δ ÷ 实测ΔH，
// 不假设 MakeHuman macro 权重混合约定。minusCm 是负值。
// 官方 macro 域极宽（±1 实测跨 130.7~239.4cm），预设 155/160/165/170 全部
// 落在小权重区（−0.34 ~ +0.04）。

export interface HeightInfo {
  baseCm: number    // w=0 基础身高（实测 ~167.4）
  plusCm: number    // w=+1 身高增量（正，cm；实测 +72.02）
  minusCm: number   // w=−1 身高减量（负，cm；实测 −36.69）
}

/** 权重 → 身高（cm）：w≥0 走 plus、w<0 走 minus（两场独立，非反对称）。 */
export function heightCm(info: HeightInfo, w: number): number {
  return info.baseCm + (w >= 0 ? w * info.plusCm : -w * info.minusCm)
}

/** 身高（cm）→ 权重（预设芯片换算）；结果钳制进官方域 [−1,1]。 */
export function weightFor(info: HeightInfo, targetCm: number): number {
  const w = targetCm >= info.baseCm
    ? (targetCm - info.baseCm) / info.plusCm
    : (info.baseCm - targetCm) / info.minusCm
  return Math.min(1, Math.max(-1, w))
}

/** 站点高度缩放因子：身高场近似等比缩放全身，围度站 y 随身体升降
 *（比例近似——场非严格等比，极端档位读数有轻微口径偏差，试验场口径）。 */
export function stationFactor(info: HeightInfo, w: number): number {
  return heightCm(info, w) / info.baseCm
}
