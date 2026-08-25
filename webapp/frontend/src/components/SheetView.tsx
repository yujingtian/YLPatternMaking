import { useCallback, useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import type {
  DraftPayload, HandleBinding, HandleInfo, Schema, Transform,
} from '../types'
import { postAdjust } from '../api'

// 整版交互视图（二期拖拽调版）：
//   把手 overlay 注入 SVG 内部（styles.css 使 svg max-width:100% 响应式
//   缩放，SVG 内坐标自动跟随；指针→cm 必走 getScreenCTM().inverse()）；
//   拖拽把手 -> /api/adjust 反解参数 -> applyAdjust 回写+重生成（~100ms）；
//   滚轮以指针为中心缩放 + 空白拖曳平移（viewBox 方案，CTM 链自动正确）；
//   双击把手复位默认值；拖拽中气泡显示参数实时值。
//
// 关键决策：
// - dangerouslySetInnerHTML 每次刷新销毁重建整棵 SVG 子树：pointer capture
//   设在持久容器 div 上（React 不替换它）；effect 每次刷新后重建 overlay，
//   拖拽进行中立即把被拖把手钉回指针投影位（不随刷新复位到 achieved）；
// - 拖拽会话/节流/单飞全走 ref，不进 React state（避免 100ms 级全树重渲）；
// - in-flight 期间新目标只存 pending，响应返回后发最新（单飞不堆积）；
//   seq 计数丢弃松手后的过期响应。

const SVG_NS = 'http://www.w3.org/2000/svg'
const THROTTLE_MS = 100
const ZOOM_MIN = 1 / 8   // 放大 8x
const ZOOM_MAX = 1 / 0.3 // 缩小 0.3x

interface Props {
  svg: string
  transform: Transform
  handles: HandleInfo[]
  schema: Schema | null
  base: DraftPayload
  onApplyAdjust: (param: string, value: number, base: DraftPayload) => void
  onBeginDrag: (param: string, prevValue: number) => void
  onDragChange: (dragging: boolean) => void
}

interface ViewBox { x: number; y: number; w: number; h: number }

interface DragState {
  element: string
  binding: HandleBinding
  label: string
  base: DraftPayload
  value: number        // 气泡最新参数值（调整响应回填）
  clamped: boolean
  aborted: boolean     // 新拖拽会话开启：旧会话在途响应作废
  dot: SVGCircleElement | null   // 当前 DOM 节点（每次刷新重建后重挂）
  hint: SVGLineElement | null
  bubble: SVGGElement | null
  bubbleText: SVGTextElement | null
  bubbleRect: SVGRectElement | null
}

// px→cm 仿射（transform 与 SVG 根 data-* 同源下发）
function cmToUser(t: Transform, x: number, y: number) {
  return { x: x * t.scale + t.ox, y: t.top - y * t.scale }
}

function defaultOf(schema: Schema | null, param: string): number {
  for (const s of schema?.sections ?? [])
    for (const g of s.groups) {
      const spec = g.params.find((p) => p.key === param)
      if (spec && typeof spec.default === 'number') return spec.default
    }
  return 0
}

function readVb(svgEl: SVGSVGElement): ViewBox {
  const raw = (svgEl.getAttribute('viewBox') ?? '0 0 0 0').split(/\s+/).map(Number)
  return { x: raw[0] || 0, y: raw[1] || 0, w: raw[2] || 1, h: raw[3] || 1 }
}

export default function SheetView({
  svg, transform, handles, schema, base,
  onApplyAdjust, onBeginDrag, onDragChange,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const [viewBox, setViewBox] = useState<ViewBox | null>(null)
  const vbRef = useRef<ViewBox | null>(null)
  vbRef.current = viewBox
  const [panning, setPanning] = useState(false)
  const dragRef = useRef<DragState | null>(null)
  const panRef = useRef<{ cx: number; cy: number; s: number; vb: ViewBox } | null>(null)
  const lastPointerCm = useRef<{ x: number; y: number } | null>(null)
  const inFlight = useRef(false)
  const pendingTarget = useRef<number | null>(null)
  const lastSent = useRef(0)
  const trailTimer = useRef<number | null>(null)
  const seq = useRef(0)

  // 高频回调读最新 props/回调（保持 handler 自身稳定，effect 一次性挂载）
  const transformRef = useRef(transform)
  transformRef.current = transform
  const baseRef = useRef(base)
  baseRef.current = base
  const schemaRef = useRef(schema)
  schemaRef.current = schema
  const onApplyRef = useRef(onApplyAdjust)
  onApplyRef.current = onApplyAdjust
  const onBeginRef = useRef(onBeginDrag)
  onBeginRef.current = onBeginDrag
  const onDragChangeRef = useRef(onDragChange)
  onDragChangeRef.current = onDragChange

  // ---------- 指针换算 ----------

  const pointerCm = useCallback((e: { clientX: number; clientY: number }) => {
    const svgEl = svgRef.current
    const ctm = svgEl?.getScreenCTM()
    if (!svgEl || !ctm) return null
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse())
    const t = transformRef.current
    return { x: (p.x - t.ox) / t.scale, y: (t.top - p.y) / t.scale }
  }, [])

  // ---------- 气泡 ----------

  const makeBubble = useCallback((svgEl: SVGSVGElement, d: DragState) => {
    const g = document.createElementNS(SVG_NS, 'g')
    g.setAttribute('class', 'drag-bubble')
    const rect = document.createElementNS(SVG_NS, 'rect')
    rect.setAttribute('rx', '3')
    const text = document.createElementNS(SVG_NS, 'text')
    text.textContent = `${d.label} ${d.value.toFixed(2)}`
    g.append(rect, text)
    svgEl.appendChild(g)
    d.bubble = g
    d.bubbleText = text
    d.bubbleRect = rect
  }, [])

  const updateBubble = useCallback((d: DragState) => {
    if (!d.bubble || !d.bubbleText || !d.bubbleRect || !lastPointerCm.current) return
    d.bubbleText.textContent = `${d.label} ${d.value.toFixed(2)}`
    const svgEl = svgRef.current
    const k = svgEl ? screenScale(svgEl) : 1
    const u = cmToUser(transformRef.current, lastPointerCm.current.x,
                       lastPointerCm.current.y)
    const pad = 4 / k
    const bx = u.x + 10 / k
    const by = u.y - 26 / k
    const bb = d.bubbleText.getBBox()
    // CSS dominant-baseline: hanging -> text y 即顶边，rect 包住字高
    d.bubbleText.setAttribute('x', String(bx))
    d.bubbleText.setAttribute('y', String(by))
    d.bubbleRect.setAttribute('x', String(bx - pad))
    d.bubbleRect.setAttribute('y', String(by - pad))
    d.bubbleRect.setAttribute('width', String(bb.width + 2 * pad))
    d.bubbleRect.setAttribute('height', String(bb.height + 2 * pad))
  }, [])

  // 屏幕比例（user→screen 缩放，含 viewBox 缩放与 CSS 响应式缩放两级）：
  // 把手半径/字号按屏幕像素恒定——缩小时不糊、放大时不巨大
  function screenScale(svgEl: SVGSVGElement): number {
    const ctm = svgEl.getScreenCTM()
    return ctm ? Math.hypot(ctm.a, ctm.b) || 1 : 1
  }

  // ---------- 拖拽求解（节流 + 单飞 + 过期丢弃） ----------

  const send = useCallback((target: number) => {
    const d = dragRef.current
    if (!d) return
    if (inFlight.current) { pendingTarget.current = target; return }
    inFlight.current = true
    lastSent.current = performance.now()
    const mySeq = ++seq.current
    postAdjust({
      ...d.base, element: d.element, param: d.binding.param,
      axis: d.binding.axis, target,
    }).then((res) => {
      inFlight.current = false
      // 会话作废（新拖拽开启）或过期响应：丢弃；松手后的最终 flush 不作废
      if (d.aborted || mySeq !== seq.current) return
      d.value = res.value
      d.clamped = !res.converged
      const item = svgRef.current?.querySelector(
        `#yl-handles .handle[data-element="${d.element}"]`)
      item?.classList.toggle('clamped', d.clamped)
      updateBubble(d)
      onApplyRef.current(d.binding.param, res.value, d.base)
      if (pendingTarget.current !== null) {
        const t = pendingTarget.current
        pendingTarget.current = null
        send(t)
      }
    }).catch(() => { inFlight.current = false })
  }, [updateBubble])

  const pinHandle = useCallback((d: DragState, cm: { x: number; y: number }) => {
    const u = cmToUser(transformRef.current, cm.x, cm.y)
    if (d.binding.axis === 'x') d.dot?.setAttribute('cx', String(u.x))
    else d.dot?.setAttribute('cy', String(u.y))
  }, [])

  const moveTarget = useCallback((e: PointerEvent) => {
    const d = dragRef.current
    if (!d) return
    const cm = pointerCm(e)
    if (!cm) return
    lastPointerCm.current = cm
    pinHandle(d, cm)
    updateBubble(d)
    const target = d.binding.axis === 'x' ? cm.x : cm.y
    const now = performance.now()
    if (now - lastSent.current >= THROTTLE_MS) {
      if (trailTimer.current !== null) {
        window.clearTimeout(trailTimer.current)
        trailTimer.current = null
      }
      send(target)
    } else {
      pendingTarget.current = target
      if (trailTimer.current === null) {
        trailTimer.current = window.setTimeout(() => {
          trailTimer.current = null
          const dd = dragRef.current
          if (!dd || inFlight.current || pendingTarget.current === null) return
          const t = pendingTarget.current
          pendingTarget.current = null
          send(t)
        }, THROTTLE_MS)
      }
    }
  }, [pointerCm, pinHandle, updateBubble, send])

  const startDrag = useCallback((e: PointerEvent, h: HandleInfo) => {
    if (e.button !== 0) return
    e.stopPropagation()
    e.preventDefault()
    const b = h.bindings[0]
    if (!b) return
    // 新会话作废旧会话在途响应（abort + seq 跳变）
    if (dragRef.current) dragRef.current.aborted = true
    seq.current += 1
    const baseNow = baseRef.current
    const cur = typeof baseNow.options[b.param] === 'number'
      ? (baseNow.options[b.param] as number)
      : defaultOf(schemaRef.current, b.param)
    onBeginRef.current(b.param, cur)     // 记录拖前值（撤销用）
    lastPointerCm.current = null
    pendingTarget.current = null
    dragRef.current = {
      element: h.element, binding: b, label: h.label, base: baseNow,
      value: cur, clamped: false, aborted: false,
      dot: null, hint: null, bubble: null, bubbleText: null, bubbleRect: null,
    }
    const svgEl = svgRef.current
    if (svgEl) makeBubble(svgEl, dragRef.current)
    svgRef.current?.querySelector(
      `#yl-handles .handle[data-element="${h.element}"]`)?.classList.add('dragging')
    hostRef.current?.setPointerCapture(e.pointerId)
    onDragChangeRef.current(true)
  }, [makeBubble])

  const endDrag = useCallback(() => {
    const d = dragRef.current
    if (!d) return
    // 松手 flush 最终目标（in-flight 时由响应链补发 pending）；
    // 最终响应允许在松手后落地（精确落位），不作废本会话
    if (pendingTarget.current !== null && !inFlight.current) {
      const t = pendingTarget.current
      pendingTarget.current = null
      send(t)
    }
    if (trailTimer.current !== null) {
      window.clearTimeout(trailTimer.current)
      trailTimer.current = null
    }
    svgRef.current?.querySelector(
      `#yl-handles .handle[data-element="${d.element}"]`)?.classList.remove('dragging')
    // 气泡淡出移除
    d.bubble?.classList.add('fade')
    window.setTimeout(() => d.bubble?.remove(), 300)
    dragRef.current = null
    onDragChangeRef.current(false)
  }, [send])

  // 双击把手：参数复位 schema 默认值（同样走 beginDrag 记录，可撤销）
  const resetHandle = useCallback((h: HandleInfo) => {
    const b = h.bindings[0]
    if (!b) return
    const baseNow = baseRef.current
    const cur = typeof baseNow.options[b.param] === 'number'
      ? (baseNow.options[b.param] as number)
      : defaultOf(schemaRef.current, b.param)
    onBeginRef.current(b.param, cur)
    onApplyRef.current(b.param, defaultOf(schemaRef.current, b.param), baseNow)
  }, [])

  // ---------- 缩放平移（viewBox 方案） ----------

  const zoomAt = useCallback((cx: number, cy: number, factor: number) => {
    const svgEl = svgRef.current
    const ctm = svgEl?.getScreenCTM()
    if (!svgEl || !ctm) return
    const vb0 = vbRef.current ?? readVb(svgEl)
    const p = new DOMPoint(cx, cy).matrixTransform(ctm.inverse())
    const w = Math.min(Math.max(vb0.w * factor, vb0.w * ZOOM_MIN), vb0.w * ZOOM_MAX)
    const h = vb0.h * (w / vb0.w)
    setViewBox({
      x: p.x - (p.x - vb0.x) * (w / vb0.w),
      y: p.y - (p.y - vb0.y) * (w / vb0.w),
      w, h,
    })
  }, [])

  const doPan = useCallback((e: PointerEvent) => {
    const p = panRef.current
    if (!p) return
    const dx = (e.clientX - p.cx) * p.s
    const dy = (e.clientY - p.cy) * p.s
    setViewBox({ ...p.vb, x: p.vb.x - dx, y: p.vb.y - dy })
  }, [])

  // ---------- 容器级事件（一次性挂载；capture 设在持久容器上） ----------

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const onMove = (e: PointerEvent) => {
      if (dragRef.current) moveTarget(e)
      else if (panRef.current) doPan(e)
    }
    const onUp = () => {
      if (dragRef.current) endDrag()
      if (panRef.current) {
        panRef.current = null
        setPanning(false)
      }
    }
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 0.85 : 1 / 0.85)
    }
    host.addEventListener('pointermove', onMove)
    host.addEventListener('pointerup', onUp)
    host.addEventListener('pointercancel', onUp)
    host.addEventListener('wheel', onWheel, { passive: false })
    return () => {
      host.removeEventListener('pointermove', onMove)
      host.removeEventListener('pointerup', onUp)
      host.removeEventListener('pointercancel', onUp)
      host.removeEventListener('wheel', onWheel)
    }
  }, [moveTarget, endDrag, doPan, zoomAt])

  const onHostPointerDown = useCallback((e: ReactPointerEvent) => {
    if (e.button !== 0) return
    const svgEl = svgRef.current
    const ctm = svgEl?.getScreenCTM()
    if (!svgEl || !ctm) return
    panRef.current = {
      cx: e.clientX, cy: e.clientY,
      s: Math.hypot(ctm.a, ctm.b) || 1,   // user 单位/屏幕 px
      vb: vbRef.current ?? readVb(svgEl),
    }
    hostRef.current?.setPointerCapture(e.pointerId)
    setPanning(true)
  }, [])

  // ---------- overlay：每次整版刷新重建（React 重注入销毁旧子树） ----------

  useEffect(() => {
    const host = hostRef.current
    const svgEl = host?.querySelector('svg') as SVGSVGElement | null
    if (!svgEl) return
    svgRef.current = svgEl
    if (viewBox) {
      svgEl.setAttribute('viewBox',
        `${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`)
    }
    svgEl.querySelectorAll('#yl-handles').forEach((n) => n.remove())
    const k = screenScale(svgEl)
    const g = document.createElementNS(SVG_NS, 'g')
    g.id = 'yl-handles'
    for (const h of handles) {
      const b = h.bindings[0]
      if (!b) continue
      const u = cmToUser(transform, h.x, h.y)
      const item = document.createElementNS(SVG_NS, 'g')
      item.setAttribute('class', 'handle')
      item.setAttribute('data-element', h.element)
      const hint = document.createElementNS(SVG_NS, 'line')
      hint.setAttribute('class', 'axis-hint')
      const L = 9 / k
      if (b.axis === 'x') {
        hint.setAttribute('x1', String(u.x - L)); hint.setAttribute('x2', String(u.x + L))
        hint.setAttribute('y1', String(u.y)); hint.setAttribute('y2', String(u.y))
      } else {
        hint.setAttribute('x1', String(u.x)); hint.setAttribute('x2', String(u.x))
        hint.setAttribute('y1', String(u.y - L)); hint.setAttribute('y2', String(u.y + L))
      }
      const dot = document.createElementNS(SVG_NS, 'circle')
      dot.setAttribute('class', 'handle-dot')
      dot.setAttribute('cx', String(u.x))
      dot.setAttribute('cy', String(u.y))
      dot.setAttribute('r', String(4.5 / k))
      const hit = document.createElementNS(SVG_NS, 'circle')
      hit.setAttribute('class', 'handle-hit')
      hit.setAttribute('cx', String(u.x))
      hit.setAttribute('cy', String(u.y))
      hit.setAttribute('r', String(13 / k))
      hit.addEventListener('pointerdown', (e) => startDrag(e, h))
      hit.addEventListener('dblclick', () => resetHandle(h))
      item.append(hint, dot, hit)
      g.appendChild(item)
    }
    svgEl.appendChild(g)
    // 拖拽进行中：重挂被拖把手到新 DOM 节点 + 钉回指针位 + 重建气泡
    const d = dragRef.current
    if (d) {
      const item = svgEl.querySelector(
        `#yl-handles .handle[data-element="${d.element}"]`)
      if (item) {
        d.dot = item.querySelector('.handle-dot')
        d.hint = item.querySelector('.axis-hint')
        item.classList.add('dragging')
        item.classList.toggle('clamped', d.clamped)
        d.bubble = null
        makeBubble(svgEl, d)
        if (lastPointerCm.current) {
          pinHandle(d, lastPointerCm.current)
          updateBubble(d)
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [svg, handles, transform, viewBox, startDrag, resetHandle, makeBubble,
     pinHandle, updateBubble])

  return (
    <div
      ref={hostRef}
      className={`svg-view sheet-view${panning ? ' panning' : ''}`}
      onPointerDown={onHostPointerDown}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}
