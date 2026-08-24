// 与后端 /api/schema、/api/draft 对齐的类型（一期手写，二期可 openapi 生成）

// 参数级联动 gate：字符串 = 布尔开关键；对象 = 枚举参数值匹配
// （值在 values 内才显示，如贴袋形态专属参数随 back_patch_shape 切换）
export interface EnumGate {
  param: string
  values: string[]
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

export interface AdjustablePoint {
  element: string
  label: string
  bindings: { param: string; axis: string; range: [number, number] }[]
}

export interface Schema {
  groups: GroupSpec[]
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

export interface DraftResult {
  ok: boolean
  sheet_svg: string
  report: string
  pieces: PieceResult[]
  skips: string[]
  warnings: DraftWarning[]
}

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
