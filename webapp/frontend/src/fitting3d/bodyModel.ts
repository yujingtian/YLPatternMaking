// 模特（人台）体型模型（2026-09-24 自 Fitting3DView 提出）：六部位双极
// 滑杆 <-> base.bin target 槽位（SLOT_ORDER 固定序里的 6 对场）+ 身高场
// 权重。提出动机：设置弹框化（BodySetupModal）——体型状态升 App 持有
// （BodyModel），3D 切 2D 卸载 Fitting3DView 不丢，弹框/侧栏/解算快照
// （weightsFrom）三处同源消费，不再各持一份。
import type { MeshWeights } from './bodymesh/morph'

// 滑杆部位 <-> base.bin target 槽位（SLOT_ORDER 固定序里的 6 对场）
export type Site = 'waist' | 'hips' | 'thigh' | 'knee' | 'calf' | 'ankle'
export const SITES: { key: Site; label: string }[] = [
  { key: 'waist', label: '腰' },
  { key: 'hips', label: '臀' },
  { key: 'thigh', label: '大腿' },
  { key: 'knee', label: '膝' },
  { key: 'calf', label: '小腿' },
  { key: 'ankle', label: '踝' },
]
export type Sliders = Record<Site, number>

/** App 级模特状态：六部位双极权重（−1..+1）+ 身高场权重（0 = 基础 ~167.4） */
export interface BodyModel {
  sliders: Sliders
  heightW: number
}

export const zeroBody = (): BodyModel => ({
  sliders: { waist: 0, hips: 0, thigh: 0, knee: 0, calf: 0, ankle: 0 },
  heightW: 0,
})

// 预设体型芯片（cm）：权重按 meta.height 实测 ΔH 换算（height.ts weightFor）
export const PRESET_CM = [155, 160, 165, 170] as const
// 身高滑杆窗（cm）：官方 macro 域极宽（±1 实测跨 130.7~239.4cm，极端是卡通
// 身高），滑杆钳在常人域 150~185 连续可调（可停任意身高如 162.3）；芯片值
// 全部落在窗内，不受钳制影响
export const HEIGHT_SLIDER = { min: 150, max: 185, step: 0.1 }

// 滑杆/身高 -> morph 场权重（morph 效应、穿台效应、stale 判定三处同源；
// 正推 site+、负推 site−，两场独立作者化非反对称；身高同构 height±）
export const weightsFrom = (sliders: Sliders, heightW: number): MeshWeights => {
  const w: MeshWeights = {}
  for (const { key } of SITES) {
    const v = sliders[key]
    if (v > 0) w[`${key}+`] = v
    else if (v < 0) w[`${key}-`] = -v
  }
  if (heightW > 0) w['height+'] = heightW
  else if (heightW < 0) w['height-'] = -heightW
  return w
}
