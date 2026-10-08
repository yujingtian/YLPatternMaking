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
  adjustNote, balanceNotes, buildChatForm, deliverySummaryLine,
  deliveryToPrefill, normalizeChatError, recheckDiffLines, recheckNote,
  reasoningText, sessionToJson,
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
            score_warnings: ['裤长'], balance_guard: [] },
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

  it('photoMeta 与 photos 对齐：JSON 串附 photo_meta（photos 之后）；无照片/未传不附', () => {
    const form = buildChatForm(
      null, 'x', [file('a.jpg'), file('b.jpg')], undefined,
      [
        { name: 'a.jpg', category: 'front' },
        { name: 'b.jpg', category: 'other', note: '袋口特写' },
      ],
    )
    expect([...form.keys()]).toEqual(
      ['session', 'text', 'photos', 'photos', 'photo_meta'])
    expect(form.get('photo_meta')).toBe(JSON.stringify([
      { name: 'a.jpg', category: 'front' },
      { name: 'b.jpg', category: 'other', note: '袋口特写' },
    ]))
    // 无 meta / 无照片 -> 不附（后端 None -> 旧行为）
    expect(buildChatForm(null, 'x', [file('a.jpg')]).has('photo_meta'))
      .toBe(false)
    expect(buildChatForm(null, 'x', [], undefined, []).has('photo_meta'))
      .toBe(false)
  })

  it('thinking 空白不附；opts 缺省不附（吃后端默认）', () => {
    const form = buildChatForm({ a: 1 }, 'x', [], { thinking: '   ' })
    expect(form.get('session')).toBe('{"a":1}')
    expect(form.has('thinking')).toBe(false)
    expect(form.has('run_probe')).toBe(false)
    expect(form.has('run_score')).toBe(false)
    expect(form.has('max_refeed')).toBe(false)
    expect(form.has('fulfill')).toBe(false)
  })

  it('fulfill=recheck 附加（D 两段握手轮次 B）；缺省不附', () => {
    const form = buildChatForm(null, '', [], { fulfill: 'recheck' })
    expect(form.get('fulfill')).toBe('recheck')
    expect(form.get('text')).toBe('')
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
      review: { reverted: [], low_confidence: [], score_warnings: [],
                balance_guard: [] },
    }
    expect(deliverySummaryLine(d)).toBe('第 3 轮交卷 · 模型 test-vl · 照片 2 张')
  })

  it('混合计数逐段拼接（0 项段省略）', () => {
    // DELIVERY：回退 1 / 低置信 2 / 评分警告 1
    expect(deliverySummaryLine(DELIVERY)).toBe(
      '第 3 轮交卷 · 模型 test-vl · 照片 2 张 · 回退 1 项 · 低置信 2 项 · 评分警告 1 项')
    const d: ChatDelivery = {
      ...DELIVERY,
      review: { reverted: [], low_confidence: ['hip'], score_warnings: [],
                balance_guard: [] },
    }
    expect(deliverySummaryLine(d)).toBe(
      '第 3 轮交卷 · 模型 test-vl · 照片 2 张 · 低置信 1 项')
  })

  it('有调版 -> 「调版 n 键」段插在照片之后；空 applied / 无 adjust 不变', () => {
    const d: ChatDelivery = {
      ...DELIVERY,
      adjust: {
        note: '袋口弧线加深', reverted: [], dropped: [],
        applied: [
          { key: 'front_pocket_mouth_bulge', value: 1.75 },
          { key: 'front_pocket_p2_drop', value: 12 },
        ],
      },
    }
    expect(deliverySummaryLine(d)).toBe(
      '第 3 轮交卷 · 模型 test-vl · 照片 2 张 · 调版 2 键 · '
      + '回退 1 项 · 低置信 2 项 · 评分警告 1 项')
    // 空调整（applied=[]）：仅 note 披露，摘要行不加段
    const empty: ChatDelivery = {
      ...DELIVERY,
      adjust: { note: '未识别到调版意图', applied: [], dropped: [], reverted: [] },
    }
    expect(deliverySummaryLine(empty)).toBe(
      '第 3 轮交卷 · 模型 test-vl · 照片 2 张 · 回退 1 项 · 低置信 2 项 · 评分警告 1 项')
    expect(deliverySummaryLine(DELIVERY)).toContain('照片 2 张 · 回退')
  })
})

describe('balanceNotes（侧缝守卫披露，2026-09-29 A5）', () => {
  it('非空 -> 「侧缝守卫 n 项」段 + 全句拼接（；分隔）', () => {
    const d: ChatDelivery = {
      ...DELIVERY,
      review: { reverted: [], low_confidence: [], score_warnings: [],
                balance_guard: [
                  '侧缝守卫：前侧收量 0.35 塌零（阈值 0.5，步进抬回）',
                  'waist_balance 1.00→1.25 重跑，前侧收量 0.60',
                ] },
    }
    expect(deliverySummaryLine(d)).toBe(
      '第 3 轮交卷 · 模型 test-vl · 照片 2 张 · 侧缝守卫 2 项')
    expect(balanceNotes(d)).toBe(
      '侧缝守卫：前侧收量 0.35 塌零（阈值 0.5，步进抬回）'
      + '；waist_balance 1.00→1.25 重跑，前侧收量 0.60')
  })

  it('未触发 / 旧会话缺键 -> 空串、摘要行不加段（?? [] 兼容）', () => {
    expect(balanceNotes(DELIVERY)).toBe('')
    const legacy: ChatDelivery = {
      ...DELIVERY,
      review: { ...DELIVERY.review, balance_guard: undefined as never },
    }
    expect(balanceNotes(legacy)).toBe('')
    expect(deliverySummaryLine(legacy)).not.toContain('侧缝守卫')
  })
})

describe('adjustNote（调版披露一句话）', () => {
  it('有 adjust.note -> 原样返回', () => {
    const d: ChatDelivery = {
      ...DELIVERY,
      adjust: { note: '袋口弧线加深；引擎校验回退：袋口深浅',
                applied: [], dropped: [], reverted: ['front_pocket_p2_drop'] },
    }
    expect(adjustNote(d)).toBe('袋口弧线加深；引擎校验回退：袋口深浅')
  })

  it('无 adjust / note 空 -> 空串（调用方非空才渲染）', () => {
    expect(adjustNote(DELIVERY)).toBe('')
    const d: ChatDelivery = {
      ...DELIVERY, adjust: { note: '', applied: [], dropped: [], reverted: [] },
    }
    expect(adjustNote(d)).toBe('')
  })
})

describe('recheck（定向复查披露，2026-09-29 D）', () => {
  const RC: ChatDelivery = {
    ...DELIVERY,
    recheck: {
      group: '后贴袋',
      note: '我来重新细看后贴袋的形状与大小；复查后贴袋：2 处更新',
      diff: [
        { key: 'back_patch', old: null, new: true, evidence: '背面照两枚贴袋清晰' },
        { key: 'back_patch_shape', old: 'rectangle', new: 'baker_shield',
          evidence: '底部两斜线交于底中一点成尖角' },
      ],
    },
  }

  it('recheckDiffLines：null 旧值 ->（未判断）、布尔 -> 开/关、逐条带证据', () => {
    expect(recheckDiffLines(RC)).toEqual([
      'back_patch （未判断） -> 开（背面照两枚贴袋清晰）',
      'back_patch_shape rectangle -> baker_shield（底部两斜线交于底中一点成尖角）',
    ])
    expect(recheckNote(RC)).toBe(
      '我来重新细看后贴袋的形状与大小；复查后贴袋：2 处更新')
  })

  it('非复查轮 / 旧会话缺键 -> 空数组、空串（?? 兼容）', () => {
    expect(recheckDiffLines(DELIVERY)).toEqual([])
    expect(recheckNote(DELIVERY)).toBe('')
    const legacy: ChatDelivery = { ...DELIVERY, recheck: undefined }
    expect(recheckDiffLines(legacy)).toEqual([])
    expect(recheckNote(legacy)).toBe('')
  })

  it('摘要行「复查 n 处」段插在调版之后；diff 空不加段', () => {
    expect(deliverySummaryLine(RC)).toBe(
      '第 3 轮交卷 · 模型 test-vl · 照片 2 张 · 复查 2 处 · '
      + '回退 1 项 · 低置信 2 项 · 评分警告 1 项')
    // 同轮既调版又复查（复查看图后改形态 + 用户又口头调尺寸）：调版在前
    const both: ChatDelivery = {
      ...RC,
      adjust: {
        note: '腰围改 75', applied: [{ key: 'waist', value: 75 }],
        dropped: [], reverted: [],
      },
    }
    expect(deliverySummaryLine(both)).toBe(
      '第 3 轮交卷 · 模型 test-vl · 照片 2 张 · 调版 1 键 · 复查 2 处 · '
      + '回退 1 项 · 低置信 2 项 · 评分警告 1 项')
    const kept: ChatDelivery = {
      ...RC, recheck: { group: '后贴袋', diff: [], note: '维持原判断' },
    }
    expect(deliverySummaryLine(kept)).not.toContain('复查')
  })
})

describe('reasoningText（思考段折叠展示，2026-10-08）', () => {
  it('复查轮优先（复查时 S2 未跑、delivery.reasoning 恒空）', () => {
    const d: ChatDelivery = {
      ...DELIVERY,
      reasoning: '',
      recheck: { group: '后贴袋', diff: [], note: '', reasoning: '复查草稿' },
    }
    expect(reasoningText(d)).toBe('复查草稿')
  })

  it('常规轮取 S2 草稿；recheck 在场但无草稿时回落 S2', () => {
    const d: ChatDelivery = { ...DELIVERY, reasoning: 'S2 草稿' }
    expect(reasoningText(d)).toBe('S2 草稿')
    const rc: ChatDelivery = {
      ...d,
      recheck: { group: '后贴袋', diff: [], note: '' },
    }
    expect(reasoningText(rc)).toBe('S2 草稿')
  })

  it('快速模式/旧会话缺键 -> 空串（调用方非空才渲染折叠块）', () => {
    expect(reasoningText(DELIVERY)).toBe('')
    expect(reasoningText({ ...DELIVERY, reasoning: '' })).toBe('')
  })
})
