// 推板（多码推码）档差表 <-> canonical [size_run] 的转换纯函数。
//
// 语义依据引擎 src/ylpattern/params/sizerun.py（实现时对齐、勿凭记忆改）：
// - 步进归属：相邻码 i -> i+1 的档差取 i+1 所属 band —— 引擎行间差
//   gapAt(i) = v(i+1) - v(i) = band_of(行 i+1)（码序升序为正）；
// - 孤儿校验：不在任何 band 的非基码会被引擎打回 -> fromGradeTable 保存时
//   把首码并入首段 band（band_of(首码) 的步进从不被查询，语义无差）；
// - thigh 特例：基码 thigh=0 时引擎忽略一切 thigh 步进（全码 0）。
// 基码锚定口径（用户拍板 2026-08-27；首版「统一与上一码、空格恒在首码」在
// 基码居中场景反直觉——基码前插码后首码格空、基码格反可录）：基码行是锚
// （档差格恒空，绝对值只读取参数面板）；上方行录「与更大相邻码之差」、
// 下方行录「与上一码之差」，全表全正数。表格档差向量 d 与 gapAt 互为投影：
//   d[k] = k > base ? gapAt(k-1) : k < base ? gapAt(k) : 0（锚位无信息）
// 换基码走 rebaseTable 重投影（物理放码关系不变）；行插入/删除/换位则档差
// 跟行走（码序重组，所见即所得）。round(2) 仅在导出（fromGradeTable）做，
// 视图切换不累积舍入。

import {
  MEASURE_KEYS, type GradeSteps, type MeasureKey, type SizeRunBandSpec,
  type SizeRunSpec,
} from './types'

/** 全 0 档差（新行/新表缺省）。 */
export function emptySteps(): GradeSteps {
  return { waist: 0, hip: 0, knee: 0, hem: 0, front_rise: 0, back_rise: 0,
           outseam: 0, thigh: 0 }
}

/** 抽屉编辑模型：行 = 码序（升序）一格；steps = 基码锚定档差——
 *  基码行恒 0（锚，格显示「—」）；基码下方 = 与上一码差；上方 = 与更大
 *  相邻码差。 */
export interface GradeRow {
  label: string
  steps: GradeSteps
}

export interface GradeTable {
  rows: GradeRow[]
  baseIndex: number
  style: string
}

function pickSteps(src: Record<string, unknown>): GradeSteps {
  const out = emptySteps()
  for (const k of MEASURE_KEYS) {
    const v = Number(src[k])
    out[k] = Number.isFinite(v) ? v : 0
  }
  return out
}

function sameSteps(a: GradeSteps, b: GradeSteps): boolean {
  return MEASURE_KEYS.every((k) => a[k] === b[k])
}

/**
 * 模板 / localStorage 的 unknown -> canonical（结构宽松校验 + 数字 coerce）。
 * enabled 值忽略（抽屉存在性即配置态，模板 enabled=false 也预填）；
 * sizes 逐码覆盖 v1 不支持：存在即丢弃并返回 droppedOverrides=true。
 * 无法解析 -> spec=null（旧存量/坏数据兜底，等价未配置）。
 */
export function normalizeSizeRun(raw: unknown): {
  spec: SizeRunSpec | null
  droppedOverrides: boolean
} {
  const dropped = raw !== null && typeof raw === 'object'
    && 'sizes' in raw && Object.keys((raw as Record<string, unknown>).sizes ?? {}).length > 0
  if (raw === null || typeof raw !== 'object') {
    return { spec: null, droppedOverrides: dropped }
  }
  const d = raw as Record<string, unknown>
  const bands: SizeRunBandSpec[] = []
  if (Array.isArray(d.band)) {
    for (const b of d.band) {
      if (b === null || typeof b !== 'object') continue
      const bd = b as Record<string, unknown>
      if (!Array.isArray(bd.sizes) || bd.sizes.length === 0) continue
      if (!bd.sizes.every((s) => typeof s === 'string' && s)) continue
      bands.push({ sizes: [...bd.sizes as string[]], ...pickSteps(bd) })
    }
  }
  let order: string[]
  if (Array.isArray(d.order) && d.order.length > 0
      && d.order.every((s) => typeof s === 'string' && s)) {
    order = [...d.order as string[]]
  } else {                       // 无显式码序：band 声明序串联去重（引擎同式）
    order = []
    for (const b of bands) {
      for (const s of b.sizes) if (!order.includes(s)) order.push(s)
    }
  }
  if (order.length === 0) return { spec: null, droppedOverrides: dropped }
  const base = typeof d.base === 'string' && d.base ? d.base : order[0]
  const style = typeof d.style === 'string' && d.style ? d.style : 'noname'
  return { spec: { enabled: true, base, style, order, band: bands },
           droppedOverrides: dropped }
}

/** 表格 d（基码锚定）-> 行间差序列：gaps[i] = v(i+1) - v(i)，i = 0..n-2
 *  （即引擎 band_of(行 i+1) 的步进）。d -> gapAt：行对 i 在锚下方
 *  （i >= baseIndex）取下一行 d[i+1]，锚上方取本行 d[i]（锚位 d[base]
 *  无信息、永不被读）。round2 仅导出口径启用。 */
function gapsOf(t: GradeTable, round2 = false): GradeSteps[] {
  const gaps: GradeSteps[] = []
  for (let i = 0; i < t.rows.length - 1; i++) {
    const src = t.rows[i >= t.baseIndex ? i + 1 : i].steps
    const s = pickSteps(src as unknown as Record<string, unknown>)
    if (round2) for (const k of MEASURE_KEYS) s[k] = Math.round(s[k] * 100) / 100
    gaps.push(s)
  }
  return gaps
}

/** 行间差序列 -> 表格 d（按锚 baseIndex 投影）：k > base 取 gaps[k-1]、
 *  k < base 取 gaps[k]（上方行 = 与更大相邻码差）、k = base 置 0。 */
function rowsFromGaps(labels: string[], baseIndex: number,
                      gaps: GradeSteps[]): GradeRow[] {
  return labels.map((label, k) => ({
    label,
    steps: k === baseIndex ? emptySteps()
         : pickSteps(gaps[k < baseIndex ? k : k - 1] as unknown as Record<string, unknown>),
  }))
}

/**
 * canonical -> 编辑模型：band 步进解为行间差后按锚投影（rowsFromGaps）；
 * spec=null 给单行基码空表（defaultLabel 取 options.size_label）。
 */
export function toGradeTable(spec: SizeRunSpec | null,
                             defaultLabel: string): GradeTable {
  if (!spec || spec.order.length === 0) {
    return { rows: [{ label: defaultLabel || '-', steps: emptySteps() }],
             baseIndex: 0, style: 'noname' }
  }
  const bandOf = new Map<string, SizeRunBandSpec>()
  for (const b of spec.band) {
    for (const s of b.sizes) bandOf.set(s, b)
  }
  // gaps[i] = band_of(order[i+1]) = 行间差 v(i+1) - v(i)
  const gaps: GradeSteps[] = spec.order.slice(1).map((label) =>
    bandOf.get(label) ? pickSteps(bandOf.get(label)!) : emptySteps())
  const baseIndex = Math.max(0, spec.order.indexOf(spec.base))
  return { rows: rowsFromGaps(spec.order, baseIndex, gaps), baseIndex,
           style: spec.style || 'noname' }
}

/**
 * 编辑模型 -> canonical：码序 = 行序（trim），base = 行[baseIndex]，
 * enabled 恒 true。band 合并 = 极大等值档差连段（引擎只按 band_of(k) 查
 * k>=1 的步进，等值连段拆并展开不变）；**首码并入首段**（孤儿校验免疫，
 * band_of(首码) 从不被查询）；档差 round(2)；不含 sizes 键。
 */
export function fromGradeTable(t: GradeTable): SizeRunSpec {
  const labels = t.rows.map((r) => r.label.trim())
  const gaps = gapsOf(t, true)
  const band: SizeRunBandSpec[] = []
  let i = 0
  while (i < gaps.length) {
    let j = i
    while (j + 1 < gaps.length && sameSteps(gaps[j + 1], gaps[i])) j += 1
    // 连段 [i..j] 对应行 i+1..j+1；首段额外并入首码（行 0）
    const start = band.length === 0 ? 0 : i + 1
    band.push({ sizes: labels.slice(start, j + 2), ...gaps[i] })
    i = j + 1
  }
  return {
    enabled: true,
    base: labels[Math.min(t.baseIndex, labels.length - 1)] ?? '-',
    style: t.style.trim() || 'noname',
    order: labels,
    band,
  }
}

/**
 * 换基码重投影：档差表是行间差的「基码锚定」视图——换锚先解回行间差再按
 * 新锚投影，物理放码关系不变。直接改 baseIndex 不重投影会把上方/下方差值
 * 错位解读（锚位差丢失、相邻差错行）。不做 round：视图切换不累积舍入。
 */
export function rebaseTable(t: GradeTable, newBase: number): GradeTable {
  const nb = Math.min(Math.max(newBase, 0), t.rows.length - 1)
  if (nb === t.baseIndex) return t
  const gaps = gapsOf(t)
  return { rows: rowsFromGaps(t.rows.map((r) => r.label), nb, gaps),
           baseIndex: nb, style: t.style }
}

/**
 * 灰字换算：各码绝对值 = 自基码（面板值）沿档差双向走表；
 * 基码 thigh=0 时全码 thigh=0（引擎特例同式）。
 */
export function absoluteValues(
  t: GradeTable, base: Record<MeasureKey, number>,
): Record<string, Record<MeasureKey, number>> {
  const out: Record<string, Record<MeasureKey, number>> = {}
  const keys = MEASURE_KEYS as readonly MeasureKey[]
  const b = Math.min(Math.max(t.baseIndex, 0), t.rows.length - 1)
  const baseVals: Record<MeasureKey, number> = {} as Record<MeasureKey, number>
  for (const k of keys) baseVals[k] = Number.isFinite(base[k]) ? base[k] : 0
  out[t.rows[b].label] = { ...baseVals }
  for (let k = b + 1; k < t.rows.length; k++) {
    const prev = out[t.rows[k - 1].label]
    const cur: Record<MeasureKey, number> = {} as Record<MeasureKey, number>
    for (const key of keys) cur[key] = prev[key] + t.rows[k].steps[key]
    out[t.rows[k].label] = cur
  }
  for (let k = b - 1; k >= 0; k--) {
    const next = out[t.rows[k + 1].label]
    const cur: Record<MeasureKey, number> = {} as Record<MeasureKey, number>
    // 上方行：v(k) = v(k+1) - d[k]（d[k] = 与更大相邻码之差）
    for (const key of keys) cur[key] = next[key] - t.rows[k].steps[key]
    out[t.rows[k].label] = cur
  }
  if (baseVals.thigh === 0) {
    for (const label of Object.keys(out)) out[label].thigh = 0
  }
  return out
}

/**
 * 抽屉前端校验（可输入态；引擎是数值合法性唯一裁判）：
 * 码标签空 / trim 后重复、订单号非可打印 ASCII。style 空不算错（保存时
 * 默认 noname）。行数 <2 合法（单码导出）但不建议，由抽屉另行提示。
 */
export function validateTable(t: GradeTable): string[] {
  const errors: string[] = []
  const labels = t.rows.map((r) => r.label.trim())
  if (labels.some((s) => !s)) errors.push('存在空码标签（请填写或删除该行）')
  const dup = labels.filter((s, i) => s && labels.indexOf(s) !== i)
  if (dup.length > 0) errors.push(`码标签重复：${[...new Set(dup)].join('、')}`)
  const style = t.style.trim()
  if (style && !/^[\x20-\x7e]+$/.test(style)) {
    errors.push('订单号须为可打印 ASCII（进 R12 DXF 头）')
  }
  return errors
}
