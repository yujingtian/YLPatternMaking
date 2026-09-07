// 提取响应纯逻辑金标（vitest；风格对齐 sizeRun.test.ts）。
// 口径：agent/app.py 422 detail 双形态（字符串=照片非法 | 清单=缺必填）、
// 503=VLM 未配置/失败；keys.source 中文常量；低置信阈值 0.7（'默认' 除外）。
// 契约来源 agent/extract/__init__.py to_web_payload（详见 §10.9）。

import { describe, expect, it } from 'vitest'
import {
  buildLabelMap, formatValue, isLowConfidence, LOW_CONFIDENCE,
  normalizeExtractError, toConfirmRows, toPrefillPayload,
} from './extractPayload'
import type { ExtractResponse, Schema } from './types'

describe('normalizeExtractError（422 双形态 / 503 / 兜底）', () => {
  it('422 清单形态 -> issues（缺必填）', () => {
    const e = normalizeExtractError(422, [
      { param: 'waist', message: '描述与模型补漏后仍缺必填尺寸（不编数值）',
        level: 'error' },
      { param: 'hip', message: '描述与模型补漏后仍缺必填尺寸（不编数值）',
        level: 'error' },
    ])
    expect(e.kind).toBe('issues')
    expect(e.issues).toHaveLength(2)
    expect(e.issues?.[0].param).toBe('waist')
  })

  it('422 字符串形态 -> text（照片非法）', () => {
    const e = normalizeExtractError(422, '照片后缀非法：x.tiff')
    expect(e).toEqual({ kind: 'text', message: '照片后缀非法：x.tiff' })
  })

  it('503 无 detail -> VLM 提示；503 字符串 detail 原样', () => {
    expect(normalizeExtractError(503, undefined).message).toContain('VLM')
    expect(normalizeExtractError(503, '上游超时'))
      .toEqual({ kind: 'text', message: '上游超时' })
  })

  it('其他状态码 -> 兜底文本（含 status）', () => {
    expect(normalizeExtractError(502, undefined).message).toContain('502')
    expect(normalizeExtractError(422, null).message).toContain('422')
  })
})

describe('buildLabelMap（schema 单源白话名）', () => {
  const schema = {
    sections: [{
      key: 'measure', label: '测量', collapsed: false,
      groups: [{
        key: 'g1', label: 'G1', collapsed: false, visible_if: null,
        params: [
          { key: 'waist', label: '腰围', type: 'number', default: 0 },
          { key: 'front_patch_shape', label: '前贴袋形态', type: 'custom_shape',
            default: null, points_key: 'front_patch_points',
            edges_key: 'front_patch_edges' },
        ],
      }],
    }],
    adjustable_points: [],
  } as unknown as Schema

  it('建 key->label，custom_shape 背后隐藏键也收录', () => {
    const m = buildLabelMap(schema)
    expect(m.get('waist')).toBe('腰围')
    expect(m.get('front_patch_points')).toBe('前贴袋形态角点')
    expect(m.get('front_patch_edges')).toBe('前贴袋形态边')
  })

  it('schema=null 给空 map；缺键兜底原 key（确认屏侧）', () => {
    expect(buildLabelMap(null).size).toBe(0)
  })
})

describe('isLowConfidence（阈值 0.7，默认不标）', () => {
  it('0.69 标黄、0.7 不标、默认来源不标、无 meta 不标', () => {
    const meta = (c: number, source = '照片') =>
      ({ value: 1, source, confidence: c, evidence: '' })
    expect(isLowConfidence(meta(0.69))).toBe(true)
    expect(isLowConfidence(meta(LOW_CONFIDENCE))).toBe(false)
    expect(isLowConfidence(meta(0.1, '默认'))).toBe(false)
    expect(isLowConfidence(undefined)).toBe(false)
  })
})

describe('formatValue', () => {
  it('bool→开/关、数字圆整 2 位、字符串原样、其余 JSON', () => {
    expect(formatValue(true)).toBe('开')
    expect(formatValue(false)).toBe('关')
    expect(formatValue(74.123)).toBe('74.12')
    expect(formatValue('slim')).toBe('slim')
    expect(formatValue([1, 2])).toBe('[1,2]')
  })
})

describe('toConfirmRows / toPrefillPayload', () => {
  const res: ExtractResponse = {
    ok: true, model: 'fake', photo_count: 0,
    measurements: { waist: 74.0, hip: 91.5, knee: 44, hem: 34, front_rise: 25,
                    back_rise: 33, outseam: 102, thigh: 56 },
    options: { back_yoke: true, watch_pocket: false },
    keys: {
      waist: { value: 74, source: '描述', confidence: 0.95, evidence: '描述原文' },
      hem: { value: 34, source: '预判', confidence: 0.5, evidence: '档位表' },
      back_yoke: { value: true, source: '查表', confidence: 0.9, evidence: '' },
    },
    issues: [], probe: { stage: 'L4', ok: true, log: [] }, score: [],
  }
  const labels = new Map([['waist', '腰围'], ['hem', '脚口'],
                          ['back_yoke', '后机头'], ['watch_pocket', '小表袋']])

  it('尺寸 8 键按 MEASURE_KEYS 序、options 不混入、meta 逐键挂接', () => {
    const rows = toConfirmRows(res, labels)
    expect(rows.measures.map((r) => r.key)).toEqual(
      ['waist', 'hip', 'knee', 'hem', 'front_rise', 'back_rise', 'outseam',
       'thigh'])
    expect(rows.measures[0].label).toBe('腰围')
    expect(rows.measures[0].meta?.source).toBe('描述')
    // hem 预判 0.5 < 0.7 标黄
    expect(isLowConfidence(rows.measures[3].meta)).toBe(true)
    expect(rows.options.map((r) => r.key)).toEqual(['back_yoke', 'watch_pocket'])
    expect(rows.options[0].value).toBe('开')
    expect(rows.options[1].value).toBe('关')
  })

  it('labelMap 缺键兜底原 key', () => {
    const rows = toConfirmRows(res, new Map())
    expect(rows.measures[1].label).toBe('hip')
  })

  it('toPrefillPayload 原样透传且与源对象隔离（浅拷贝）', () => {
    const p = toPrefillPayload(res)
    expect(p.measurements).toEqual(res.measurements)
    expect(p.options).toEqual(res.options)
    p.options.back_yoke = false
    expect(res.options.back_yoke).toBe(true)
  })
})
