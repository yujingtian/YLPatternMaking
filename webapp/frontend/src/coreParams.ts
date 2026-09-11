// 核心参数白名单（左栏「核心参数」页签，2026-09-11 交互重构）：
// 只做展示分区的前端侧白名单——不改 webschema 契约、不重打引擎包。
// 键在 schema 中找不到时 CoreParams 静默跳过（防 schema 演进崩面板）；
// 「全部参数」页签（ParamPanel）不受此清单影响，两处同值由 options/
// measurements state 同步。
import { MEASURE_KEYS } from './types'

export interface CoreParamGroup {
  key: string
  label: string
  // schema 参数键（含虚拟参数 pocket_type / fly_type）
  params: string[]
}

export const CORE_PARAM_GROUPS: CoreParamGroup[] = [
  // 基础测量 8 = 引擎 MEASURE_KEYS 同源（腰/臀/膝/脚口/前后浪/裤长/大腿围）
  { key: 'measurements', label: '基础测量', params: [...MEASURE_KEYS] },
  // 款式：口袋/门襟虚拟下拉（写多开关）+ 6 个款式开关
  {
    key: 'style',
    label: '款式',
    params: [
      'pocket_type', 'fly_type',
      'front_pouch', 'watch_pocket', 'back_dart', 'back_yoke', 'back_patch',
      'belt_loop',
    ],
  },
  // 腰头类型从腰头组提级（影响版型最大的形态开关；全部页签内保留原位）
  { key: 'waistband', label: '腰头', params: ['waistband_type'] },
]
