// NestPreview 纯逻辑金标（vitest node env，风格对齐 NestResultModal.test.ts）：
// 几何变换/锚点防御/需求副本不去重/图例排序/留白公式/标签口径。组件视图
// （三件套观感、翻转组 viewBox）由 US-007 Playwright 冒烟端到端覆盖。
// 口径源 = MS materialSorting-web lib/geometry.ts（pointsStr 字节级同式）
// 与 lib/canvasPad.ts（v2 无条件 ≥px 留白）。

import { describe, expect, it } from 'vitest'
import {
  fitViewWidthMm, nestLabelText, nestVPadMm, physicalAnchor, pointsStr,
  previewPolys, sizeLegendEntries,
} from './NestPreview'
import type {
  MsBest, MsManifest, MsPieceMeta, MsPlacedItem, MsPolygon,
} from '../types'

const SQ: MsPolygon = [[0, 0], [10, 0], [10, 10], [0, 10]]
const SQ2: MsPolygon = [[1, 1], [9, 1], [9, 9], [1, 9]]

function mkPiece(over: Partial<MsPieceMeta>): MsPieceMeta {
  return {
    id: 'g01', size: 30, color: '#1f77b4', area_mm2: 100,
    polygon: SQ, raw_polygon: SQ2, d_mm: 0, label: 'g01', demand: 1,
    net_polygon: SQ, internal_lines: null, notches: null, grain_line: null,
    ...over,
  }
}

function mkBest(placed: MsPlacedItem[], over: Partial<MsBest> = {}): MsBest {
  return {
    seed: 0, frame_index: 0, elapsed: 10, density: 0.8,
    density_sparrow: null, width_mm: 6000, placed_items: placed,
    ...over,
  }
}

function mkManifest(pieces: MsPieceMeta[], gate = 1750): MsManifest {
  return {
    gate_mm: gate, total_area_mm2: 1000, n_eroded: 0, pieces,
  }
}

describe('pointsStr（MS 同式变换，r2 截断）', () => {
  it('rot=0 纯平移：原样 + 平移', () => {
    expect(pointsStr(SQ, 0, [100, 50]))
      .toBe('100,50 110,50 110,60 100,60')
  })

  it('rot=90 + 平移：x\'=−y+tx、y\'=x+ty（浮点尾差被 r2 清掉）', () => {
    expect(pointsStr(SQ, 90, [100, 50]))
      .toBe('100,50 100,60 90,60 90,50')
  })

  it('mirror=true：旋转前局部 x 取负（等价 x 取负后同参变换）', () => {
    expect(pointsStr(SQ, 0, [20, 0], true))
      .toBe(pointsStr([[-0, 0], [-10, 0], [-10, 10], [-0, 10]], 0, [20, 0]))
  })

  it('r2 两位小数截断（无尾随空格）', () => {
    expect(pointsStr([[0.123456, 0.987654]], 0, [0, 0])).toBe('0.12,0.99')
  })
})

describe('physicalAnchor（渲染锚点防御）', () => {
  it('raw_polygon 优先（d=0 时 polygon 过 _clean_polygon 仍可能 ≠ raw）', () => {
    const p = mkPiece({ polygon: SQ, raw_polygon: SQ2 })
    expect(physicalAnchor(p)).toBe(SQ2)
  })

  it('raw 缺失 / <3 点 → 回退 polygon', () => {
    expect(physicalAnchor(mkPiece({ raw_polygon: null }))).toBe(SQ)
    expect(physicalAnchor(mkPiece({ raw_polygon: [[0, 0], [1, 1]] }))).toBe(SQ)
  })
})

describe('previewPolys（demand 副本不去重——DOM 多边形计数 = placed 条数）', () => {
  it('numMap g01:2 夹具：同 pid 两条 placed → 两个多边形节点', () => {
    // numMap {g01: 2} → MS manifest demand=2 → solver 发 2 条同 id placement
    const manifest = mkManifest([mkPiece({ demand: 2 })])
    const best = mkBest([
      { id: 'g01', rotation: 0, translation: [0, 0] },
      { id: 'g01', rotation: 90, translation: [500, 200] },
    ])
    const polys = previewPolys(manifest, best)
    expect(polys).toHaveLength(2)
    expect(polys.map((p) => p.key)).toEqual(['g01#0', 'g01#1'])
    // 两副本各自承一处 placement（后不覆盖前）
    expect(polys[0].points).not.toEqual(polys[1].points)
    expect(polys[0].color).toBe('#1f77b4')
  })

  it('锚点取 raw_polygon：points 与 pointsStr(raw, rot, tr) 逐字节一致', () => {
    const manifest = mkManifest([mkPiece(
      { polygon: SQ, raw_polygon: SQ2 })])
    const best = mkBest([{ id: 'g01', rotation: 30, translation: [11, 22] }])
    expect(previewPolys(manifest, best)[0].points)
      .toBe(pointsStr(SQ2, 30, [11, 22]))
  })

  it('未知 pid 跳过（异常载荷防御）；空 placed → 空集', () => {
    const manifest = mkManifest([mkPiece({})])
    expect(previewPolys(manifest,
      mkBest([{ id: 'g99', rotation: 0, translation: [0, 0] }])))
      .toEqual([])
    expect(previewPolys(manifest, mkBest([]))).toEqual([])
  })
})

describe('fitViewWidthMm（宽度锚优先级）', () => {
  it('best.width_mm 有效即用', () => {
    expect(fitViewWidthMm(mkBest([], { width_mm: 6123.4 }), [])).toBe(6123.4)
  })

  it('缺失/非法 → 多边形最大 x 回退；空集兜底 1', () => {
    const polys = previewPolys(mkManifest([mkPiece({})]),
      mkBest([{ id: 'g01', rotation: 0, translation: [2500, 0] }]))
    expect(fitViewWidthMm(mkBest([], { width_mm: null }), polys)).toBe(2509)
    expect(fitViewWidthMm(mkBest([], { width_mm: 0 }), [])).toBe(1)
  })
})

describe('nestLabelText（MS NestLabel 同口径）', () => {
  it('density×100 两位小数 + width_mm/10 两位小数', () => {
    expect(nestLabelText(0.8157, 6123.4)).toBe('81.57% · 长度 612.34 cm')
  })
})

describe('sizeLegendEntries（尺码图例）', () => {
  it('size→color 去重、数值升序（10 排在 9 后）、null 跳过', () => {
    const entries = sizeLegendEntries([
      mkPiece({ id: 'a', size: 30, color: '#c1' }),
      mkPiece({ id: 'b', size: 10, color: '#c10' }),
      mkPiece({ id: 'c', size: 9, color: '#c9' }),
      mkPiece({ id: 'd', size: 30, color: '#dup-ignored' }),
      mkPiece({ id: 'e', size: null, color: '#null' }),
    ])
    expect(entries).toEqual([[9, '#c9'], [10, '#c10'], [30, '#c1']])
  })

  it('全 null size → 空集（图例不渲染）', () => {
    expect(sizeLegendEntries([mkPiece({ size: null })])).toEqual([])
  })
})

describe('nestVPadMm（上下自动留白，MS canvasPad v2 同式）', () => {
  it('零尺寸/未布局（jsdom）→ 0（基形态 viewBox="0 0 W gate"）', () => {
    expect(nestVPadMm(0, 0, 6000, 1750)).toBe(0)
  })

  it('宽深唛架（宽度受限、余量本已足）→ 0 不干预', () => {
    // a = 1200/6000 = 0.2 ≤ target = (800-400)/1750 ≈ 0.2286
    expect(nestVPadMm(1200, 800, 6000, 1750)).toBe(0)
  })

  it('窄高容器（少片放大撑满高）→ pad = px·vbH/(H−2px)', () => {
    // a = 712/2000 = 0.356 > target = (400-200)/600 ≈ 0.333 → pad = 100·600/200 = 300
    expect(nestVPadMm(712, 400, 2000, 600)).toBe(300)
  })

  it('小容器 px 按 H/4 优雅降级（H=300 → px=75）', () => {
    // a = 500/2000 = 0.25 > target = (300-150)/600 = 0.25？临界取等 → 0；
    // 换 a 更大：boxW=600 → a=0.3 > 0.25 → pad = 75·600/150 = 300
    expect(nestVPadMm(500, 300, 2000, 600)).toBe(0)
    expect(nestVPadMm(600, 300, 2000, 600)).toBe(300)
  })
})
