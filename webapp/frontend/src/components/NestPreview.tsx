// NestPreview —— 机器排料结果静态布局图（二期对接 §10.3.2 US-005）：复刻
// MS 工作台超排三件套观感（顶标签 + fit-view 翻转 SVG + 右上尺码图例），
// 不打开 MS 工作台即可核对最终布局；底部另附信息条（利用率/幅宽/料长(m)/
// 片数）。与 MS NestSVG 的差异（有意）：MS 是 ~10fps 帧流 + 命令式
// setAttribute 逃逸 React reconciliation；YL 只消费终态 result（done/stopped
// 取果一次），静态声明式渲染即可——pointsStr 与 MS lib/geometry.ts 逐字节
// 同式（r2 截断 + 空格连接，纯函数金标锚定），与 MS /export PNG 并排目检
// 布局一致（联调 M2 判据）。
//
// 几何口径（MS 契约透传，types.ts MS 段）：
//   - 锚点多边形 = raw_polygon ?? polygon（物理毛版口径，与 /export
//     PLT/PNG 同源；d=0 时 polygon 过 _clean_polygon 仍可能与 raw 不同，
//     故恒 raw 优先、<3 点回退 polygon）
//   - world = R(rotation)·p + translation（MS 世界系 mm、Y 向上；mirror
//     仅编辑写回帧可带，solver 原生帧永无——防御性支持）
//   - demand>1 的 pid 在 placed_items 有 N 条（同 id 不同 translation）：
//     逐条建 N 个多边形节点，绝不按 pid 去重（否则 N 条共用同一 polygon
//     后覆盖前，只剩 1/N 可见——MS 同款隐蔽坑注释在案）
//   - Y 翻转组 translate(0 gate) scale(1 -1)：MS 世界 Y 向上 → SVG Y 向下，
//     与 PNG/R12-DXF 一致
//
// 交互口径（PRD FR）：静态 fit——无缩放/平移/拖拽编辑（编辑是 MS 工作台
// 职责），仅目检；上下自动留白复刻 MS canvasPad v2（无条件 ≥px，px =
// min(200, H/4)，宽深唛架余量本已足时 pad=0 逐字节不变），ResizeObserver
// 跟随容器（jsdom 无 RO → 0 尺寸兜底 pad=0，纯函数金标不受影响）。
import { useEffect, useMemo, useRef, useState } from 'react'
import type { MsBest, MsManifest, MsPieceMeta, MsPolygon } from '../types'

// ---- 纯几何（MS lib/geometry.ts pointsStr 同式；导出供金标单测） ----

/** 四舍五入到 2 位小数（MS r2 同式——points 字节级一致性的保证） */
export function r2(x: number): number {
  return Math.round(x * 100) / 100
}

/** 渲染锚点多边形（物理毛版口径）：raw_polygon 优先，缺失/<3 点回退 polygon */
export function physicalAnchor(p: MsPieceMeta): MsPolygon {
  return p.raw_polygon !== null && p.raw_polygon.length >= 3
    ? p.raw_polygon : p.polygon
}

/**
 * base 多边形按 rotation(°) + translation[tx,ty] 变换为 SVG points 字符串。
 * 与 MS pointsStr / 后端 _transform_polygon 同式（字节级一致）：
 *   rad = rot·π/180；x' = x·c − y·s + tx；y' = x·s + y·c + ty
 * mirror=true（MsPlacedItem.mirror，缺省 false）：旋转前局部 x 取负。
 * 输出格式 `r2(x),r2(y)` 空格连接、无尾随空格。
 */
export function pointsStr(
  poly: MsPolygon, rot: number, tr: [number, number], mirror = false,
): string {
  const rad = (rot * Math.PI) / 180
  const c = Math.cos(rad)
  const s = Math.sin(rad)
  let out = ''
  for (let i = 0; i < poly.length; i++) {
    const x = mirror ? -poly[i][0] : poly[i][0]
    const y = poly[i][1]
    out += (i ? ' ' : '')
      + r2(x * c - y * s + tr[0]) + ',' + r2(x * s + y * c + tr[1])
  }
  return out
}

/** 渲染多边形节点描述：一条 placed_item → 一个节点（绝不按 pid 去重） */
export interface NestPreviewPoly {
  key: string        // `${id}#${出现序}`（demand>1 同 pid 副本互异）
  points: string     // 变换后世界坐标 points 字符串
  color: string      // manifest piece.color（尺码配色透传，同码同色跨片型）
}

export function previewPolys(
  manifest: MsManifest, best: MsBest,
): NestPreviewPoly[] {
  const byId = new Map<string, MsPieceMeta>()
  for (const p of manifest.pieces) byId.set(p.id, p)
  const reached = new Map<string, number>()
  const out: NestPreviewPoly[] = []
  for (const it of best.placed_items) {
    const piece = byId.get(it.id)
    if (piece === undefined) continue   // 防御：异常载荷未知 pid 跳过
    const k = reached.get(it.id) ?? 0
    reached.set(it.id, k + 1)
    out.push({
      key: `${it.id}#${k}`,
      points: pointsStr(physicalAnchor(piece), it.rotation, it.translation,
        it.mirror === true),
      color: piece.color,
    })
  }
  return out
}

/** fit-view 宽度锚：best.width_mm 优先；缺失/非法回退多边形最大 x（≥1 防退化） */
export function fitViewWidthMm(best: MsBest, polys: NestPreviewPoly[]): number {
  if (best.width_mm !== null && best.width_mm > 0) return best.width_mm
  let maxX = 1
  for (const p of polys) {
    for (const pair of p.points.split(' ')) {
      const x = parseFloat(pair.split(',')[0])
      if (Number.isFinite(x) && x > maxX) maxX = x
    }
  }
  return maxX
}

/** 顶标签文本（MS NestLabel 同口径）：X.XX% · 长度 X.XX cm（width_mm/10） */
export function nestLabelText(density: number, widthMm: number): string {
  return `${(density * 100).toFixed(2)}% · 长度 ${(widthMm / 10).toFixed(2)} cm`
}

/** 尺码图例条目：size→color 去重、数值升序、size null 跳过（MS SizeLegend 同式） */
export function sizeLegendEntries(pieces: MsPieceMeta[]): [number, string][] {
  const bySize = new Map<number, string>()
  for (const p of pieces) {
    if (p.size === null) continue
    if (!bySize.has(p.size)) bySize.set(p.size, p.color)
  }
  return [...bySize.entries()].sort((a, b) => a[0] - b[0])
}

// ---- 上下自动留白（MS canvasPad v2 同式：无条件 ≥px；宽深唛架 pad=0 不变） ----

export const NEST_VPAD_PX = 200

export function nestVPadMm(
  boxW: number, boxH: number, vbW: number, vbH: number,
): number {
  if (!(boxW > 0) || !(boxH > 0) || !(vbW > 0) || !(vbH > 0)) return 0
  const px = Math.min(NEST_VPAD_PX, Math.floor(boxH / 4))
  const denom = boxH - 2 * px        // ≥ boxH/2 > 0
  const target = denom / vbH         // 留白后的高比上限（px/mm）
  const a = boxW / vbW               // 宽比（px/mm）
  if (a <= target) return 0          // 宽度受限且上下余量 ≥px → 不干预
  return (px * vbH) / denom
}

// ---- 组件 ----

export default function NestPreview({
  manifest, best,
}: { manifest: MsManifest; best: MsBest }) {
  // 结果快照一次成型（终态取果后 manifest/best 引用不再变化）；useMemo
  // 防 StrictMode 双渲染重算亦足够（无帧流，无需 MS 式命令式 DOM）
  const polys = useMemo(() => previewPolys(manifest, best), [manifest, best])
  const W = useMemo(() => fitViewWidthMm(best, polys), [best, polys])
  const gate = manifest.gate_mm
  const legend = useMemo(
    () => sizeLegendEntries(manifest.pieces), [manifest])
  // 用布边框宽（fab 矩形）：width_mm 有效即用（与 bg 同 W 时重合），缺失
  // 回退 W——静态终态无「历史最大宽防抖」需求（MS viewBoxMaxW 是帧流口径）
  const fabW = best.width_mm !== null && best.width_mm > 0 ? best.width_mm : W

  // 容器像素尺寸（留白计算输入）：ResizeObserver 跟随窗口缩放；jsdom/
  // 未布局零尺寸 → nestVPadMm 兜底 0（viewBox 退化基形态 0 0 W gate）
  const svgRef = useRef<SVGSVGElement>(null)
  const [box, setBox] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = svgRef.current
    if (el === null || typeof ResizeObserver !== 'function') return
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect()
      setBox({ w: r.width, h: r.height })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const padY = nestVPadMm(box.w, box.h, W, gate)

  return (
    <div className="nest-preview">
      <div className="nest-preview-label">
        {nestLabelText(best.density, W)}
      </div>
      <div className="nest-preview-body">
        <svg
          ref={svgRef}
          className="nest-preview-svg"
          viewBox={`0 ${-padY} ${W} ${gate + 2 * padY}`}
          preserveAspectRatio="xMinYMid meet"
        >
          {/* bg（画布底）与 fab（用布边界，灰虚线框）均世界锚定不动；
              留白区由 svg CSS 背景（#eef0f3 同色）铺满，观感无缝 */}
          <rect x={0} y={0} width={W} height={gate} fill="#eef0f3" />
          <rect
            x={0} y={0} width={fabW} height={gate}
            fill="#ffffff" fillOpacity={0.55}
            stroke="#8a8a8a" strokeWidth={1.5} strokeDasharray="8 5"
          />
          {/* 翻转组：MS 世界 Y 向上 → SVG Y 向下（与 PNG/R12-DXF 一致） */}
          <g transform={`translate(0 ${gate}) scale(1 -1)`}>
            {polys.map((p) => (
              <polygon
                key={p.key} points={p.points}
                fill={p.color} fillOpacity={0.55}
                stroke={p.color} strokeWidth={1.2}
              />
            ))}
          </g>
        </svg>
        {legend.length > 0 ? (
          <div className="nest-size-legend">
            <div className="nest-size-legend-title">尺码</div>
            {legend.map(([size, color]) => (
              <div className="nest-size-legend-row" key={size}>
                <span
                  className="nest-size-legend-swatch"
                  style={{ background: color, borderColor: color }}
                />
                <span className="nest-size-legend-label">{size}</span>
              </div>
            ))}
          </div>
        ) : null}
      </div>
      <div className="nest-preview-info">
        利用率 {(best.density * 100).toFixed(2)}%（物理口径）
        {' '}· 幅宽 {gate / 10} cm · 料长 {(W / 1000).toFixed(2)} m
        {' '}· {best.placed_items.length} 片
      </div>
    </div>
  )
}
