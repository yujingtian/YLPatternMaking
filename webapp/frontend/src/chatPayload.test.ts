// 智能打版对话壳纯逻辑金标（vitest；风格对齐 extractPayload.test.ts）。
// 口径：agent/app.py POST /api/chat/turn——Form session（JSON 串）/text/
// photos/thinking/run_probe/run_score/max_refeed；响应 session 是**对象**
// （前端每轮 stringify 回传）；delivery 顶层无 ok/model/photo_count（在
// summary 里）；交卷卡以整版 SVG 预览为中心、参数明细不渲染（2026-09-21
// （三），预览走 SheetPreview 直喂 postSheet，不经本层）。错误 422 照片
// 非法串/400 会话非法/503 VLM，缺必填不 422 转求援卡。
// 详见 .doc/python工程设计.md §10.9.2。
import { describe, expect, it } from 'vitest'
import {
  buildChatForm, deliverySummaryLine, deliveryToPrefill,
  normalizeChatError, sessionToJson,
} from './chatPayload'
import type { ChatDelivery, ExtractKeyMeta } from './types'

function file(name: string): File {
  return new File([new Uint8Array([1, 2, 3])], name, { type: 'image/jpeg' })
}

const META = (source: string, confidence: number): ExtractKeyMeta =>
  ({ value: 1, source, confidence, evidence: '' })

const DELIVERY: ChatDelivery = {
  measurements: { waist: 74 },
  options: { front_pocket: true },
  keys: { waist: META('描述', 1.0) },
  issues: [],
  probe: { stage: 'L0', ok: true, log: [] },
  score: [],
  review: { reverted: ['knee'], low_confidence: ['hip', 'thigh'],
            score_warnings: ['裤长'] },
  ledger: { measurements: { waist: { value: 74, turn: 1 } }, size_label: null },
  summary: { turn: 3, model: 'test-vl', photo_count: 2 },
}

describe('sessionToJson（响应对象 -> 请求串）', () => {
  it('null/undefined/空对象 -> "{}"（首轮）', () => {
    expect(sessionToJson(null)).toBe('{}')
    expect(sessionToJson(undefined)).toBe('{}')
    expect(sessionToJson({})).toBe('{}')
  })

  it('对象 -> 可还原 JSON 串（含中文）', () => {
    const obj = { events: [{ turn: 1, text: '腰围74' }] }
    const s = sessionToJson(obj)
    expect(s).toBe(JSON.stringify(obj))
    expect(JSON.parse(s)).toEqual(obj)
  })
})

describe('buildChatForm', () => {
  it('字段序与多值 photos', () => {
    const form = buildChatForm(null, '你好', [file('a.jpg'), file('b.jpg')])
    // FormData keys() 对多值重复产出键名：photos ×2
    expect([...form.keys()]).toEqual(['session', 'text', 'photos', 'photos'])
    expect(form.get('session')).toBe('{}')
    expect(form.get('text')).toBe('你好')
    expect(form.getAll('photos')).toHaveLength(2)
  })

  it('thinking 空白不附；opts 缺省不附（吃后端默认）', () => {
    const form = buildChatForm({ a: 1 }, 'x', [], { thinking: '   ' })
    expect(form.get('session')).toBe('{"a":1}')
    expect(form.has('thinking')).toBe(false)
    expect(form.has('run_probe')).toBe(false)
    expect(form.has('run_score')).toBe(false)
    expect(form.has('max_refeed')).toBe(false)
  })

  it('thinking 非空白 trim 后附加；布尔串化（后端 Form(bool) 可析）', () => {
    const form = buildChatForm(null, 'x', [], {
      thinking: ' 提示 ', run_probe: false, run_score: true, max_refeed: 3,
    })
    expect(form.get('thinking')).toBe('提示')
    // FormData 布尔一律串化——'false' 而非丢弃，FastAPI 可解析为 False
    expect(form.get('run_probe')).toBe('false')
    expect(form.get('run_score')).toBe('true')
    expect(form.get('max_refeed')).toBe('3')
  })
})

describe('normalizeChatError', () => {
  it('422/400 字符串 detail 透传', () => {
    expect(normalizeChatError(422, '照片后缀非法：x.tiff').message)
      .toBe('照片后缀非法：x.tiff')
    expect(normalizeChatError(400, '会话 JSON 非法：xx').message)
      .toBe('会话 JSON 非法：xx')
  })

  it('400 无 detail -> 引导重开对话', () => {
    expect(normalizeChatError(400, null).message)
      .toBe('会话状态异常，请点「重新开始」重开对话')
  })

  it('503 -> VLM 文案；其余无 body -> HTTP 兜底', () => {
    expect(normalizeChatError(503, undefined).message)
      .toBe('VLM 未配置或调用失败（vlm.toml / 上游服务）')
    expect(normalizeChatError(418, null).message).toBe('对话失败（HTTP 418）')
  })

  it('detail 为数组/对象（契约不该出现）-> HTTP 兜底', () => {
    expect(normalizeChatError(422, [{ param: 'waist' }]).message)
      .toBe('对话失败（HTTP 422）')
  })
})

describe('deliveryToPrefill', () => {
  it('浅拷贝：改返回值不污染原 delivery', () => {
    const p = deliveryToPrefill(DELIVERY)
    p.measurements.waist = 99
    p.options.extra = 1
    expect(DELIVERY.measurements.waist).toBe(74)
    expect(DELIVERY.options.extra).toBeUndefined()
  })
})

describe('deliverySummaryLine', () => {
  it('review 全空 -> 只有轮次/模型/照片三段', () => {
    const d: ChatDelivery = {
      ...DELIVERY,
      review: { reverted: [], low_confidence: [], score_warnings: [] },
    }
    expect(deliverySummaryLine(d)).toBe('第 3 轮交卷 · 模型 test-vl · 照片 2 张')
  })

  it('混合计数逐段拼接（0 项段省略）', () => {
    // DELIVERY：回退 1 / 低置信 2 / 评分警告 1
    expect(deliverySummaryLine(DELIVERY)).toBe(
      '第 3 轮交卷 · 模型 test-vl · 照片 2 张 · 回退 1 项 · 低置信 2 项 · 评分警告 1 项')
    const d: ChatDelivery = {
      ...DELIVERY,
      review: { reverted: [], low_confidence: ['hip'], score_warnings: [] },
    }
    expect(deliverySummaryLine(d)).toBe(
      '第 3 轮交卷 · 模型 test-vl · 照片 2 张 · 低置信 1 项')
  })
})
