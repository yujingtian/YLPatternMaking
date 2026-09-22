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
  type: 'number' | 'int' | 'bool' | 'enum' | 'string' | 'json' | 'sa'
       | 'pocket_type' | 'fly_type' | 'custom_shape'
  default: unknown
  choices?: string[]
  nullable?: boolean
  hidden?: boolean
  visible_if?: Gate | Gate[] | null
  // custom_shape 虚拟参数专属：编辑器读写的两真实参数键与元数据
  kind?: 'front_patch' | 'back_patch' | 'front_pouch' | 'watch_pocket'
  points_key?: string
  edges_key?: string
  v_positive?: 'down' | 'up'  // 存储值第二轴方向（back=v 向下正 / front=dy 向上正）
  mode?: 'closed' | 'open'    // 闭合净形（贴袋/小表袋）/ 开放链（袋布 K 节点）
  edge_format?: 'bulge' | 'spec'  // (弧高,位置) 二元组 / line·arc·bezier 三模式
  anchor_keys?: string[]      // open 链两端近似锚点读的 options 键（仅预览用）
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

// ---- 3D 试穿（fitting 端点，§10.11；2026-09-13 二期复活） ----
// 净样边链已由引擎反变换到整版全局坐标（cm、Y 向上）；腰头为旋转
// 局部系（frame='local'、origin=null）只随 scalars 导出——直腰头净样
// =矩形（bottom_length×width）前端重建，弯腰头非矩形暂不支持布片。
// girth_finished 是成衣量（waist/hip 整圈、thigh/knee/hem 单腿），供
// 松量读数；人台围度独立读自 bodymesh 切片（独立原则：互不侵犯）

export type FittingStationKey =
  'waist' | 'hip' | 'crotch' | 'thigh' | 'knee' | 'hem'

export interface FittingStation {
  key: FittingStationKey
  y: number
  girth_finished: number | null   // crotch 为拓扑分叉站无围度
  per: 'body' | 'leg'
}

export type FittingEdgeRole = 'top_chain' | 'seam' | 'hem' | 'free'

export interface FittingEdge {
  name: string                    // 语义边名（缝合配对键，可重复连续段）
  kind: 'line' | 'bezier'
  role: FittingEdgeRole
  pts: [number, number][]         // 0.01cm 弦高折线（1e-6 舍入）
  length: number                  // 精确弧长（边长守恒校验基准）
}

export interface FittingPiece {
  key: string
  name: string
  origin: [number, number] | null
  frame: 'reflect_y' | 'rot180' | 'local'
  bbox: [number, number, number, number]
  edges: FittingEdge[]
  marks: { pts: [number, number][] }[]
  notches: [number, number][]
  grain: [number, number][] | null
  // 腰头专属：旋转局部系不可逆推，只随标量导出
  scalars?: { top_length: number; bottom_length: number; width: number }
}

export interface FittingResult {
  ok: boolean
  schema_version: number
  units: string
  frame: { system: string; y_axis: string }
  body: {
    stations: FittingStation[]
    points: {
      front_crotch_vertex: [number, number]
      back_crotch_vertex: [number, number]
    }
    crotch_drop: number
    waistband_width: number
    waistband_type: 'straight' | 'curved'
    outseam: number
  }
  pieces: FittingPiece[]           // 固定序：front_piece, back_piece,
                                   // back_yoke?(back_yoke 开启时),
                                   // front_facing?(front_pocket_facing 开启时),
                                   // waistband
  warnings: DraftWarning[]
}

// 产物快照：data + 生成时的参数版本号（version 不匹配 = 已过期，
// 预览保留但 DXF 下载禁用，重新生成后恢复）
export interface Snapshot<T> {
  data: T
  version: number
}

// 下载种类（单一 dlBusy 串行：DXF 下载重跑引擎，防重复点击）
export type DownloadKind = 'sheetDxf' | 'piecesDxf' | 'sizeRunDxf' | 'toml'
  | 'nest'

// 排料对接产物（POST /api/nest）：带 g 码编号的 DXF（file = base64，
// 对接文档《母版DXF编号植入对接文档》方式 A）+ numMap 数量契约。
// 字段名 file/numMap 按对接契约有意不用 snake_case（与后端逐字段同构）
export interface NestResult {
  ok: boolean
  file: string
  filename: string
  numMap: Record<string, number>
  labels: Record<string, string>
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
  // 推板码表（仅 kind=size_run 的 DXF 下载与 toml 导出携带；
  // 生成端点与本地引擎均忽略此键）
  size_run?: SizeRunSpec | null
}

// ---- 推板（多码推码 [size_run]） ----
// canonical 形状与引擎 params/sizerun 规范段对齐；enabled 恒 true
// （配置存在性即开关）；v1 永不带 sizes 逐码覆盖键（模板带覆盖在
// normalizeSizeRun 丢弃并提示）。转换/校验唯一事实源在 src/sizeRun.ts

// 与引擎 sizerun.MEASURE_KEYS 对齐的 8 参数（腰/臀/膝/脚口/前后浪/外长/大腿围）
export const MEASURE_KEYS = ['waist', 'hip', 'knee', 'hem', 'front_rise',
  'back_rise', 'outseam', 'thigh'] as const
export type MeasureKey = (typeof MEASURE_KEYS)[number]
export type GradeSteps = Record<MeasureKey, number>

export type SizeRunBandSpec = { sizes: string[] } & GradeSteps

export interface SizeRunSpec {
  enabled: true
  base: string
  style: string
  order: string[]
  band: SizeRunBandSpec[]
}

// ---- 从形态导入（seed）：预设形态 -> custom 初始角点/边 ----
// points 为 v 向下正规范系（前后侧统一；前侧编辑器写回时 dy 自行取负）；
// edges 贴袋为 (bulge, at) 二元组、袋布为完整 spec（首元素为模式串）。
// 小表袋无预设（choices 恒空、seed 不可达），仅保持联合类型完备
export type EdgeSpec = (string | number)[]

export interface SeedPayload {
  kind: 'front_patch' | 'back_patch' | 'front_pouch' | 'watch_pocket'
  shape: string
  options: Values
}

export interface SeedResult {
  ok: boolean
  points: [number, number][]
  edges: EdgeSpec[]
}

// ---- agent 照片参数提取（一期前端接线，2026-09；§10.9） ----
// 对齐 agent/extract/__init__.py 的 to_web_payload + agent/runner.py 信封

// 逐键溯源（axes/switches/enums/derived 全集）；
// source 为 agent/extract/derive.py 中文常量：描述|照片|预判|查表|派生|默认
export interface ExtractKeyMeta {
  value: unknown
  source: string
  confidence: number
  evidence: string
}

export interface ExtractIssue {
  param: string
  message: string
  level: string
}

export interface ExtractProbe {
  stage: string   // "L0"~"L4"
  ok: boolean
  log: string[]
}

export interface ExtractScoreItem {
  feature: string
  value: number
  band: string
  verdict: string
}

export interface ExtractResponse {
  ok: boolean
  model: string
  photo_count: number
  measurements: Record<string, number>
  options: Values
  keys: Record<string, ExtractKeyMeta>
  issues: ExtractIssue[]
  probe: ExtractProbe
  score: ExtractScoreItem[]
}

// ---- agent 多轮对话（智能打版二期，§10.9.2） ----
// 对齐 agent/converse.py（HelpCard/_build_delivery）+ agent/app.py
// /api/chat/turn 信封。注意两处形状差：响应 session 是**对象**（请求要串，
// 前端每轮 stringify——单点收口在 chatPayload.sessionToJson）；delivery
// 顶层无 ok/model/photo_count（在 summary 里）。交卷卡只消费
// measurements/options（SheetPreview 整版预览 + 预填）与 review/summary
// （摘要行），keys/probe/score/ledger 不进前端渲染（2026-09-21（三））。

// 求援卡单项（converse.AskItem）：key=内部键名，label=人话标签
export interface ChatAsk {
  key: string
  label: string
  why: string
  example: string
}

// 求援卡（HelpCard.to_dict）：批量问缺失尺寸，白话文案
export interface ChatCard {
  asks: ChatAsk[]
  want_photos: string[]   // 建议补拍清单（要照片优先于问行话）
  message: string
}

// 交卷待确认标注（review 阈值 0.5 与确认屏标黄 0.7 是两套口径，均保留）
export interface ChatReview {
  reverted: string[]          // 探针自愈回退键（引擎默认接管，非用户确认值）
  low_confidence: string[]    // confidence<0.5 且非用户亲说键
  score_warnings: string[]    // score 表 verdict=warn 的 feature
}

export interface ChatLedgerRow {
  value: unknown
  turn: number
  evidence?: string
}

export interface ChatLedger {
  measurements: Record<string, ChatLedgerRow>
  size_label: { value: unknown; turn: number } | null
}

// 交卷体：to_web_payload 六键 + review/ledger/summary
export interface ChatDelivery {
  measurements: Record<string, number>
  options: Values
  keys: Record<string, ExtractKeyMeta>
  issues: ExtractIssue[]
  probe: ExtractProbe
  score: ExtractScoreItem[]
  review: ChatReview
  ledger: ChatLedger
  summary: { turn: number; model: string; photo_count: number }
}

export interface ChatTurnResponse {
  ok: boolean
  session: Record<string, unknown> | null
  card: ChatCard | null
  delivery: ChatDelivery | null   // card/delivery 二选一
}
