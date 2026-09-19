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

// 核心参数中文名（暂时口径 2026-09-19：前端展示层翻译，不改引擎
// USE_CN_LABELS / 不重打引擎包；词条取自 params 源码注释与 WaistbandType
// 枚举注释的打版师口径）。键 = 参数键；waistband_type 的枚举值
// straight/curved 也入表作下拉显示名（值不动，仅显示翻译）。
// 悬停 title 仍显示英文键可溯源；退役时删本表 + CoreParams 的 zhMap 透传即可。
export const CORE_PARAM_ZH: Record<string, string> = {
  // 基础测量 8（measurements.py 注释口径）
  waist: '腰围',
  hip: '臀围',
  knee: '膝围',
  hem: '裤口',
  front_rise: '前浪',
  back_rise: '后浪',
  outseam: '裤长',
  thigh: '大腿围',
  // 款式开关（虚拟参数 pocket_type/fly_type 标签本就中文，无需入表）
  front_pouch: '袋布',
  watch_pocket: '小表袋',
  back_dart: '后片腰省',
  back_yoke: '后机头（育克）',
  back_patch: '后贴袋',
  belt_loop: '裤耳',
  // 腰头 + 枚举值显示名
  waistband_type: '腰头类型',
  straight: '直腰头',
  curved: '弯腰头',
}
