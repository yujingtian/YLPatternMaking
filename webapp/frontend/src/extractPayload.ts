// agent 提取响应 -> 确认屏/预填 的纯逻辑层（无 React/DOM 依赖，vitest 直测）。
// 契约对齐 agent/extract/__init__.py to_web_payload + agent/app.py 错误口径：
//   422 detail 双形态（字符串=照片非法 | [{param,message,level}]=缺必填清单）、
//   503=VLM 未配置/上游失败；keys.source 为 derive.py 中文常量
// （描述|照片|预判|查表|派生|默认）。口径详见 .doc/python工程设计.md §10.9。
import type {
  ExtractIssue, ExtractKeyMeta, ExtractResponse, Schema, Values,
} from './types'
import { MEASURE_KEYS } from './types'

// ---- 错误归一（apiHttp.postExtract 抛出形态） ----

export interface ExtractError {
  kind: 'issues' | 'text'
  message: string
  issues?: ExtractIssue[]   // kind='issues' 时：缺必填尺寸清单
}

export function normalizeExtractError(status: number, detail: unknown): ExtractError {
  if (Array.isArray(detail)) {
    // 缺必填清单（agent ExtractError.missing -> 422）
    return { kind: 'issues',
             message: '描述与模型补漏后仍缺必填尺寸（不编数值）',
             issues: detail as ExtractIssue[] }
  }
  if (typeof detail === 'string' && detail) {
    return { kind: 'text', message: detail }
  }
  if (status === 503) {
    return { kind: 'text',
             message: 'VLM 未配置或调用失败（vlm.toml / 上游服务）' }
  }
  return { kind: 'text', message: `提取失败（HTTP ${status}）` }
}

// ---- 白话名映射（单源 /api/schema 的 ParamSpec.label，不另立中文清单） ----

export function buildLabelMap(schema: Schema | null): Map<string, string> {
  const map = new Map<string, string>()
  if (!schema) return map
  for (const section of schema.sections) {
    for (const group of section.groups) {
      for (const p of group.params) {
        map.set(p.key, p.label)
        // custom_shape 虚拟参数背后两真实键也收录（隐藏键，options 直灌可见）
        if (p.points_key) map.set(p.points_key, `${p.label}角点`)
        if (p.edges_key) map.set(p.edges_key, `${p.label}边`)
      }
    }
  }
  return map
}

// ---- 置信度与来源徽章 ----

// 低置信阈值：keys.confidence < 0.7 标黄（'默认' 除外——它不是模型判断）
export const LOW_CONFIDENCE = 0.7

export function isLowConfidence(meta: ExtractKeyMeta | undefined): boolean {
  if (!meta) return false
  return meta.confidence < LOW_CONFIDENCE && meta.source !== '默认'
}

// source -> antd Tag color（未知来源兜底灰）
export const SOURCE_BADGE: Record<string, string> = {
  '描述': 'blue',
  '照片': 'purple',
  '预判': 'orange',
  '查表': 'cyan',
  '派生': 'geekblue',
  '默认': 'default',
}

// ---- 确认屏行 ----

export interface ConfirmRow {
  key: string
  label: string          // 白话名（labelMap 缺键兜底原 key）
  value: string          // 显示值（bool→开/关、数字圆整、其余 JSON）
  meta: ExtractKeyMeta | undefined
}

export function formatValue(v: unknown): string {
  if (typeof v === 'boolean') return v ? '开' : '关'
  if (typeof v === 'number') return String(Math.round(v * 100) / 100)
  if (typeof v === 'string') return v
  return JSON.stringify(v)
}

export interface ConfirmRows {
  measures: ConfirmRow[]   // 8 尺寸键按 MEASURE_KEYS 序（缺的跳过）
  options: ConfirmRow[]    // options 全键（labelMap 命中者用白话名）
}

export function toConfirmRows(
  res: ExtractResponse, labelMap: Map<string, string>,
): ConfirmRows {
  const label = (k: string) => labelMap.get(k) ?? k
  const row = (k: string, v: unknown): ConfirmRow =>
    ({ key: k, label: label(k), value: formatValue(v), meta: res.keys[k] })
  const measures = MEASURE_KEYS
    .filter((k) => k in res.measurements)
    .map((k) => row(k, res.measurements[k]))
  const options = Object.keys(res.options)
    .filter((k) => !(MEASURE_KEYS as readonly string[]).includes(k))
    .map((k) => row(k, res.options[k]))
  return { measures, options }
}

// ---- 预填映射（确认 -> loadValues） ----

// 一期原样透传（与模板 detail 的 options 全键直灌同语义）；未来要按
// schema 键过滤，只改本函数这一处
export function toPrefillPayload(
  res: ExtractResponse,
): { measurements: Values; options: Values } {
  return { measurements: { ...res.measurements }, options: { ...res.options } }
}
