// 与后端 /api/schema、/api/draft/sheet、/api/draft/pieces 对齐的类型
// （两步生成拆分，2026-08；一期手写，后续可 openapi 生成）

// 参数级联动 gate：字符串 = 布尔开关键；对象 = 枚举参数值匹配
// （值在 values 内才显示，如贴袋形态专属参数随 shape 切换）；
// requires = 需同时为真的布尔开关键（前贴袋参数在 front_patch 开关
// 之下，形态 gate 须复合开关：开关开 AND 形态匹配才显示）
export interface EnumGate {
  param: string
  values: string[]
  requires?: string[]
}

export type Gate = string | EnumGate

export interface ParamSpec {
  key: string
  label: string
  type: 'number' | 'int' | 'bool' | 'enum' | 'string' | 'json' | 'sa' | 'pocket_type' | 'fly_type'
  default: unknown
  choices?: string[]
  nullable?: boolean
  hidden?: boolean
  visible_if?: Gate | Gate[] | null
}

export interface GroupSpec {
  key: string
  label: string
  params: ParamSpec[]
  visible_if: string | string[] | null
  collapsed: boolean
}

// 两段式分组：整版绘制（画在 DraftSheet 上的参数）/ 裁片（缩水·缝边·刀口）
export interface SectionSpec {
  key: string
  label: string
  collapsed: boolean
  groups: GroupSpec[]
}

export interface AdjustablePoint {
  element: string
  label: string
  kind: 'point' | 'curve'
  t: number | null
  visible_if: Gate | null
  bindings: { param: string; axis: string; range: [number, number] }[]
}

// ---- 二期拖拽调版 ----

// px↔cm 仿射常量（后端 compute_view 与 SVG 根 data-* 同源下发）：
// sx = x*scale + ox、sy = top − y*scale；逆变换同乘逆序
export interface Transform {
  scale: number
  ox: number
  top: number
}

export interface HandleBinding {
  param: string
  axis: string
  range: [number, number]
}

// 当前版面上的可调把手（后端已做 gate + 元素存在性自门控）
export interface HandleInfo {
  element: string
  label: string
  kind: 'point' | 'curve'
  t: number | null
  x: number
  y: number
  bindings: HandleBinding[]
}

export interface AdjustResult {
  ok: boolean
  converged: boolean
  value: number
  params: Record<string, number>
  achieved: number
  residual: number
  reason: string   // tol / range_clamped / no_effect / engine_error / max_iter
  evaluations: number
}

export interface Schema {
  sections: SectionSpec[]
  adjustable_points: AdjustablePoint[]
}

export interface PieceResult {
  key: string
  name: string
  count: number
  svg: string
}

export interface DraftWarning {
  param: string | null
  group: string | null
  message: string
  level: string
}

// 两步生成产物：整版（sheet 端点）与裁片（pieces 端点）各自独立
export interface SheetResult {
  ok: boolean
  sheet_svg: string
  report: string
  transform: Transform
  handles: HandleInfo[]
  warnings: DraftWarning[]
}

export interface PiecesResult {
  ok: boolean
  pieces: PieceResult[]
  skips: string[]
  warnings: DraftWarning[]
}

// 产物快照：data + 生成时的参数版本号（version 不匹配 = 已过期，
// 预览保留但 DXF 下载禁用，重新生成后恢复）
export interface Snapshot<T> {
  data: T
  version: number
}

// 下载种类（单一 dlBusy 串行：DXF 下载重跑引擎，防重复点击）
export type DownloadKind = 'sheetDxf' | 'piecesDxf' | 'toml'

export interface IssueDetail {
  param: string | null
  group: string | null
  message: string
  level: string
}

export type Values = Record<string, unknown>

export interface DraftPayload {
  measurements: Values
  options: Values
}
