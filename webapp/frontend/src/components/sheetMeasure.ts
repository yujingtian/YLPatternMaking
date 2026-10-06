// 量取（两点测距，2026-10-06）：高级编辑整版视图的测量工具。
//   纯逻辑（换算/吸附/状态机）导出供 vitest node 金标；useSheetMeasure hook
//   消费 SheetView 已注入 DOM 的整版 SVG——要素点 = #elements 下
//   circle.pt（id=引擎点名、cx/cy=user 坐标，svg.py:144-154 契约），
//   标签 = text.ptlabel[data-name]（show_labels=false 缺失时回退点名）。
//   零协议改动：worker/HTTP 双通道同构 sheet_svg，本模块无感知。
//
// 口径（用户 2026-10-06 确认）：
// - 读数仅直线距离（不做 ΔX/ΔY）；两点确定成线，再点新的一组自动替换；
// - 点击靠近要素点（屏幕 12px 内）吸附取该点并显示点名，否则取自由点；
// - 点击 vs 平移死区 4px：按下不立即开平移，位移超死区才晋级（SheetView 侧）。

import { useCallback, useEffect, useRef } from 'react'
import type { Transform } from '../types'

const SVG_NS = 'http://www.w3.org/2000/svg'

/** 吸附半径（屏幕像素恒定；user 半径 = SNAP_PX / screenScale） */
export const SNAP_PX = 12
/** 点击 vs 平移的死区（屏幕像素）：位移小于它算测量点击，超过晋级平移 */
export const CLICK_SLOP_PX = 4

export interface MeasurePoint {
  name: string            // circle id（引擎点名，如 front.waist_side_point）
  label: string           // ptlabel 文本；show_labels=false 时回退点名
  ux: number              // user(px) 坐标——解析态原生单位，吸附/绘制都在 user 空间
  uy: number
}

export interface MeasureEnd {
  point: MeasurePoint | null   // null 即自由点
  cm: { x: number; y: number } // 要素点 = userToCm(其 user 坐标)——精确元素坐标
}

export interface MeasureState {
  first: MeasureEnd | null
  done: { a: MeasureEnd; b: MeasureEnd } | null
}

// ---------- px↔cm 仿射三件套（与 svg.py compute_view 同源，SheetView 共用） ----------

export function cmToUser(t: Transform, x: number, y: number) {
  return { x: x * t.scale + t.ox, y: t.top - y * t.scale }
}

export function userToCm(t: Transform, ux: number, uy: number) {
  return { x: (ux - t.ox) / t.scale, y: (t.top - uy) / t.scale }
}

/** user→屏幕比例（含 viewBox 缩放与 CSS 响应式缩放）：半径/字号恒定屏幕像素用 */
export function screenScale(svgEl: SVGSVGElement): number {
  const ctm = svgEl.getScreenCTM()
  return ctm ? Math.hypot(ctm.a, ctm.b) || 1 : 1
}

// ---------- 纯逻辑 ----------

/** user 空间最近点吸附：距离最近且 < rUser 者胜；无则 null */
export function pickNearest(
  points: MeasurePoint[], px: number, py: number, rUser: number,
): MeasurePoint | null {
  let best: MeasurePoint | null = null
  let bd = rUser
  for (const p of points) {
    const d = Math.hypot(p.ux - px, p.uy - py)
    if (d < bd) { bd = d; best = p }
  }
  return best
}

/** 两端直线距离（cm） */
export function distCm(a: MeasureEnd, b: MeasureEnd): number {
  return Math.hypot(a.cm.x - b.cm.x, a.cm.y - b.cm.y)
}

/** "27.50 cm"（两位小数，与拖拽气泡 toFixed(2) 同口径） */
export function fmtCm(cm: number): string {
  return `${cm.toFixed(2)} cm`
}

/** 点击推进状态机：空→first；first→done；done→清 done、该点作新 first（一次一条自动替换） */
export function nextMeasureState(s: MeasureState, e: MeasureEnd): MeasureState {
  if (s.done) return { first: e, done: null }
  if (s.first) return { first: null, done: { a: s.first, b: e } }
  return { first: e, done: null }
}

// ---------- hook：量取态交互 + #yl-measure overlay ----------

function endUser(t: Transform, e: MeasureEnd) {
  return e.point ? { x: e.point.ux, y: e.point.uy } : cmToUser(t, e.cm.x, e.cm.y)
}

function endLabel(e: MeasureEnd): string {
  return e.point ? e.point.label : '自由点'
}

function setLine(
  ln: SVGLineElement, a: { x: number; y: number }, b: { x: number; y: number },
) {
  ln.setAttribute('x1', String(a.x)); ln.setAttribute('y1', String(a.y))
  ln.setAttribute('x2', String(b.x)); ln.setAttribute('y2', String(b.y))
}

export function useSheetMeasure(opts: {
  // 结构化 ref 类型：兼容 @types/react18 的 RefObject(readonly, current 可
  // 为 null) 与 MutableRefObject；transform 由 SheetView 恒以初值初始化、
  // current 非空（故 t 无需判空）
  svgRef: { readonly current: SVGSVGElement | null }
  transformRef: { readonly current: Transform }
  measureMode: boolean
  /** 屏幕→user（pointerCm 的前半段，SheetView 提供） */
  pointerUser: (e: { clientX: number; clientY: number }) => DOMPoint | null
}): {
  hover: (e: { clientX: number; clientY: number }) => void
  pick: (e: { clientX: number; clientY: number }) => void
  cancel: () => void
  redraw: (svg: string) => void
  clear: () => void
} {
  const { svgRef, transformRef, measureMode, pointerUser } = opts
  const modeRef = useRef(measureMode)
  modeRef.current = measureMode
  // 解析缓存键 = svg 字符串：变了才重解析并清测量（整版重生成，要素点已动）
  const pointsRef = useRef<{ svg: string; points: MeasurePoint[] }>(
    { svg: '', points: [] })
  const stateRef = useRef<MeasureState>({ first: null, done: null })
  const hoverRef = useRef<{ pt: MeasurePoint | null; cm: { x: number; y: number } | null }>(
    { pt: null, cm: null })

  /** 全量重画 overlay：幂等、永远从 ref 状态出发（无陈旧节点引用可漂移） */
  const render = useCallback(() => {
    const svgEl = svgRef.current
    if (!svgEl) return
    svgEl.querySelectorAll('#yl-measure').forEach((n) => n.remove())
    if (!modeRef.current) return
    const t = transformRef.current
    const k = screenScale(svgEl)
    const g = document.createElementNS(SVG_NS, 'g')
    g.id = 'yl-measure'
    const st = stateRef.current
    const hov = hoverRef.current

    // 成线标注 / 橡皮筋 + 第一端标记
    let bubbleAt: { x: number; y: number } | null = null
    let bubbleLines: string[] = []
    if (st.done) {
      const ua = endUser(t, st.done.a)
      const ub = endUser(t, st.done.b)
      const ln = document.createElementNS(SVG_NS, 'line')
      ln.setAttribute('class', 'measure-line')
      ln.setAttribute('stroke-width', String(1.6 / k))
      setLine(ln, ua, ub)
      g.appendChild(ln)
      for (const u of [ua, ub]) {
        const c = document.createElementNS(SVG_NS, 'circle')
        c.setAttribute('class', 'measure-endpt')
        c.setAttribute('cx', String(u.x)); c.setAttribute('cy', String(u.y))
        c.setAttribute('r', String(3.5 / k))
        c.setAttribute('stroke-width', String(1 / k))
        g.appendChild(c)
      }
      bubbleAt = { x: (ua.x + ub.x) / 2, y: (ua.y + ub.y) / 2 }
      bubbleLines = [fmtCm(distCm(st.done.a, st.done.b))]
      if (st.done.a.point || st.done.b.point) {
        bubbleLines.push(`${endLabel(st.done.a)} ↔ ${endLabel(st.done.b)}`)
      }
    } else if (st.first) {
      const ua = endUser(t, st.first)
      const c = document.createElementNS(SVG_NS, 'circle')
      c.setAttribute('class', 'measure-endpt')
      c.setAttribute('cx', String(ua.x)); c.setAttribute('cy', String(ua.y))
      c.setAttribute('r', String(3.5 / k))
      c.setAttribute('stroke-width', String(1 / k))
      g.appendChild(c)
      const hovEnd = hov.pt
        ? { point: hov.pt, cm: userToCm(t, hov.pt.ux, hov.pt.uy) }
        : (hov.cm ? { point: null, cm: hov.cm } : null)
      if (hovEnd) {
        const ub = endUser(t, hovEnd)
        const ln = document.createElementNS(SVG_NS, 'line')
        ln.setAttribute('class', 'measure-preview')
        ln.setAttribute('stroke-width', String(1.4 / k))
        ln.setAttribute('stroke-dasharray', `${5 / k} ${4 / k}`)
        setLine(ln, ua, ub)
        g.appendChild(ln)
        bubbleAt = { x: (ua.x + ub.x) / 2, y: (ua.y + ub.y) / 2 }
        bubbleLines = [fmtCm(distCm(st.first, hovEnd))]
      }
    }
    svgEl.appendChild(g)

    // 气泡（g 已入 DOM 才可 getBBox；距线中点右上偏移，行高 13/k）
    if (bubbleAt) {
      const bg = document.createElementNS(SVG_NS, 'g')
      bg.setAttribute('class', 'measure-bubble')
      const rect = document.createElementNS(SVG_NS, 'rect')
      rect.setAttribute('rx', '3')
      const texts = bubbleLines.map(() => document.createElementNS(SVG_NS, 'text'))
      bg.appendChild(rect)
      for (const tx of texts) bg.appendChild(tx)
      g.appendChild(bg)
      const pad = 4 / k
      const bx = bubbleAt.x + 12 / k
      const by = bubbleAt.y - (14 + 13 * bubbleLines.length) / k
      let wMax = 0
      texts.forEach((tx, i) => {
        tx.textContent = bubbleLines[i]
        tx.style.fontSize = `${11 / k}px`
        tx.setAttribute('x', String(bx))
        tx.setAttribute('y', String(by + (13 / k) * i))
        const bb = tx.getBBox()
        if (bb.width > wMax) wMax = bb.width
        if (i === texts.length - 1) {
          rect.setAttribute('x', String(bx - pad))
          rect.setAttribute('y', String(by - pad))
          rect.setAttribute('width', String(wMax + 2 * pad))
          rect.setAttribute('height', String(bb.y + bb.height - by + 2 * pad))
        }
      })
    }

    // 悬停吸附环 + 点名标签（done 态也显示：便于选下一组第一点）
    if (hov.pt) {
      const ring = document.createElementNS(SVG_NS, 'circle')
      ring.setAttribute('class', 'measure-snap')
      ring.setAttribute('cx', String(hov.pt.ux)); ring.setAttribute('cy', String(hov.pt.uy))
      ring.setAttribute('r', String(6 / k))
      ring.setAttribute('stroke-width', String(1.5 / k))
      g.appendChild(ring)
      const tx = document.createElementNS(SVG_NS, 'text')
      tx.setAttribute('class', 'measure-snaplabel')
      tx.textContent = hov.pt.label
      tx.style.fontSize = `${11 / k}px`
      tx.setAttribute('x', String(hov.pt.ux + 9 / k))
      tx.setAttribute('y', String(hov.pt.uy - 9 / k))
      tx.setAttribute('stroke-width', String(3 / k))
      g.appendChild(tx)
    }
  }, [svgRef, transformRef])

  /** 悬停：更新吸附候选 + 橡皮筋（无按键移动时由 SheetView 容器 onMove 调） */
  const hover = useCallback((e: { clientX: number; clientY: number }) => {
    if (!modeRef.current) return
    const svgEl = svgRef.current
    const p = pointerUser(e)
    if (!svgEl || !p) return
    const t = transformRef.current
    const pt = pickNearest(
      pointsRef.current.points, p.x, p.y, SNAP_PX / screenScale(svgEl))
    hoverRef.current = pt
      ? { pt, cm: userToCm(t, pt.ux, pt.uy) }
      : { pt: null, cm: userToCm(t, p.x, p.y) }
    render()
  }, [svgRef, transformRef, pointerUser, render])

  /** 点击拾取：吸附 or 自由点 → 推进状态机（SheetView 死区判定后调） */
  const pick = useCallback((e: { clientX: number; clientY: number }) => {
    if (!modeRef.current) return
    const svgEl = svgRef.current
    const p = pointerUser(e)
    if (!svgEl || !p) return
    const t = transformRef.current
    const pt = pickNearest(
      pointsRef.current.points, p.x, p.y, SNAP_PX / screenScale(svgEl))
    const end: MeasureEnd = pt
      ? { point: pt, cm: userToCm(t, pt.ux, pt.uy) }
      : { point: null, cm: userToCm(t, p.x, p.y) }
    stateRef.current = nextMeasureState(stateRef.current, end)
    hoverRef.current = { pt: end.point, cm: end.cm }
    render()
  }, [svgRef, transformRef, pointerUser, render])

  /** svg 注入/viewBox 变化后由 SheetView useLayoutEffect 调（绘制前，无闪帧） */
  const redraw = useCallback((svg: string) => {
    const cache = pointsRef.current
    if (cache.svg !== svg) {
      const svgEl = svgRef.current
      const points: MeasurePoint[] = []
      if (svgEl) {
        const labels = new Map<string, string>()
        svgEl.querySelectorAll('#elements text.ptlabel').forEach((n) => {
          const key = n.getAttribute('data-name')
          if (key) labels.set(key, n.textContent ?? '')
        })
        svgEl.querySelectorAll('#elements circle.pt').forEach((c) => {
          const name = c.getAttribute('id')
          if (!name) return
          const ux = parseFloat(c.getAttribute('cx') ?? '')
          const uy = parseFloat(c.getAttribute('cy') ?? '')
          if (!Number.isFinite(ux) || !Number.isFinite(uy)) return
          points.push({ name, label: labels.get(name)?.trim() || name, ux, uy })
        })
      }
      pointsRef.current = { svg, points }
      // 整版重生成（拖拽调版/改参）：要素点已动，旧测量作废；模式保持开
      stateRef.current = { first: null, done: null }
      hoverRef.current = { pt: null, cm: null }
    }
    render()
  }, [svgRef, render])

  /** 右键取消：清当前标注（未成线清第一点、已成线清整条）；悬停态保留 */
  const cancel = useCallback(() => {
    stateRef.current = { first: null, done: null }
    render()
  }, [render])

  /** 清空测量（退出模式 / ESC）：状态归零 + 删 overlay */
  const clear = useCallback(() => {
    stateRef.current = { first: null, done: null }
    hoverRef.current = { pt: null, cm: null }
    svgRef.current?.querySelectorAll('#yl-measure').forEach((n) => n.remove())
  }, [svgRef])

  // 模式关闭即清场（ESC/切 tab 由 AdvancedEditor 关模式，此处统一收口）
  useEffect(() => {
    if (!measureMode) clear()
  }, [measureMode, clear])

  return { hover, pick, cancel, redraw, clear }
}
