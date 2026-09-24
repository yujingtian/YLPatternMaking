// 智能打版整版预览（2026-09-24 独立界面化：弹层交卷卡缩略图升级为右栏
// 全幅可缩放视图）：delivery 参数直喂 postSheet——本地 Pyodide 引擎优先、
// HTTP /api/draft/sheet 透明回退（api.route），返回 .sheet_svg 字符串内联
// 渲染。缩放/平移复用 SheetView 已验证的 viewBox 方案（滚轮以指针为中心
// 缩放 + 拖曳平移；useLayoutEffect 在绘制前回放用户 viewBox，防 innerHTML
// 重注入闪帧）——刻意不复用 SheetView 本体（绑把手/adjust 反解机器，
// 预览只需「看」）。新 delivery 重置为引擎适配视图（baseVb 随图重捕，
// 复位按钮回到适配态）。失败不阻塞确认——参数仍可预填，主视图会重算
// 整版；与确认后的主视图 2D 工作台同一通道，预览即所见。
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { Alert, Button, Spin } from 'antd'
import { AimOutlined, ZoomInOutlined, ZoomOutOutlined } from '@ant-design/icons'
import { postSheet } from '../api'
import type { Values } from '../types'

// 与 SheetView 同档（同源交互口径：主视图能放多大预览就能放多大）
const ZOOM_MIN = 1 / 8   // 放大 8x
const ZOOM_MAX = 1 / 0.3 // 缩小 0.3x

interface ViewBox { x: number; y: number; w: number; h: number }

function readVb(svgEl: SVGSVGElement): ViewBox {
  const raw = (svgEl.getAttribute('viewBox') ?? '0 0 0 0').split(/\s+/).map(Number)
  return { x: raw[0] || 0, y: raw[1] || 0, w: raw[2] || 1, h: raw[3] || 1 }
}

export default function SheetPreview({ measurements, options }: {
  measurements: Values
  options: Values
}) {
  // measurements/options 是 delivery 的不可变快照，序列化做 effect 依赖即可
  const key = JSON.stringify([measurements, options])
  // 预览状态；svg 为引擎整版 SVG 字符串
  const [state, setState] = useState<{ svg?: string; error?: string }>({})
  const [viewBox, setViewBox] = useState<ViewBox | null>(null)
  const [panning, setPanning] = useState(false)
  const hostRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const vbRef = useRef<ViewBox | null>(null)
  vbRef.current = viewBox
  // 引擎自带适配 viewBox（复位按钮目标；新 delivery 重捕）
  const baseVbRef = useRef<ViewBox | null>(null)
  const panRef = useRef<{ cx: number; cy: number; s: number; vb: ViewBox } | null>(null)

  useEffect(() => {
    let alive = true
    setState({})            // 新 delivery 先清旧图 + 重置缩放回适配视图
    setViewBox(null)
    baseVbRef.current = null
    // measurements/options 是稳定快照（不可变消息），effect 只随 key 重跑
    postSheet({ measurements, options })
      .then(
        (r) => { if (alive) setState({ svg: r.sheet_svg }) },
        (e) => {
          if (alive) {
            setState({ error: e instanceof Error ? e.message : String(e) })
          }
        },
      )
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  // ---------- 缩放平移（viewBox 方案，照 SheetView；无把手/反解机器） ----------

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

  // 滚轮缩放挂持久容器（passive:false 才能 preventDefault 拦页面滚动）
  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 0.85 : 1 / 0.85)
    }
    host.addEventListener('wheel', onWheel, { passive: false })
    return () => host.removeEventListener('wheel', onWheel)
  }, [zoomAt])

  const onHostPointerDown = useCallback((e: ReactPointerEvent) => {
    if (e.button !== 0) return
    const svgEl = svgRef.current
    const ctm = svgEl?.getScreenCTM()
    if (!svgEl || !ctm) return
    panRef.current = {
      cx: e.clientX, cy: e.clientY,
      // getScreenCTM 是 user->屏幕 px 方向：鼠标位移换算（px->user）须取
      // 倒数——写反则跟踪速率随缩放级漂移（SheetView 同注）
      s: 1 / (Math.hypot(ctm.a, ctm.b) || 1),
      vb: vbRef.current ?? readVb(svgEl),
    }
    hostRef.current?.setPointerCapture(e.pointerId)
    setPanning(true)
  }, [])

  // svg（重）注入后：捕获引擎适配 viewBox（复位基准）+ 绘制前回放缩放态
  useLayoutEffect(() => {
    const svgEl = hostRef.current?.querySelector('svg') as SVGSVGElement | null
    if (!svgEl) return
    svgRef.current = svgEl
    if (baseVbRef.current === null) baseVbRef.current = readVb(svgEl)
    if (viewBox) {
      svgEl.setAttribute('viewBox',
        `${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`)
    }
  }, [state.svg, viewBox])

  // 按钮缩放以容器中心为锚；复位回引擎适配视图
  const zoomBy = (factor: number) => {
    const r = hostRef.current?.getBoundingClientRect()
    if (!r) return
    zoomAt(r.left + r.width / 2, r.top + r.height / 2, factor)
  }
  const resetZoom = () => {
    if (baseVbRef.current) setViewBox({ ...baseVbRef.current })
  }

  const hasSvg = state.svg !== undefined
  return (
    <div className="smart-preview-stage">
      {/* 宿主常驻挂载（loading/error 只是覆盖层）：滚轮/指针事件监听不随
          内容切换重挂；zoom-bar 在宿主外，点按钮不会触发平移 */}
      <div
        ref={hostRef}
        className={`svg-view sheet-view${panning ? ' panning' : ''}`}
        onPointerDown={onHostPointerDown}
        onPointerMove={(e) => { if (panRef.current) doPan(e.nativeEvent) }}
        onPointerUp={() => { panRef.current = null; setPanning(false) }}
        dangerouslySetInnerHTML={{ __html: state.svg ?? '' }}
      />
      {hasSvg && (
        <div className="smart-zoom-bar">
          <Button size="small" icon={<ZoomOutOutlined />} onClick={() => zoomBy(1 / 0.7)} />
          <Button size="small" icon={<AimOutlined />} onClick={resetZoom} title="复位视图" />
          <Button size="small" icon={<ZoomInOutlined />} onClick={() => zoomBy(0.7)} />
        </div>
      )}
      {!hasSvg && state.error === undefined && (
        <div className="smart-stage-overlay">
          <Spin />
          <span className="chat-sheet-hint">
            正在生成整版预览…首次需加载本地引擎，可能数秒
          </span>
        </div>
      )}
      {state.error !== undefined && (
        <div className="smart-stage-overlay smart-stage-error">
          <Alert
            type="error"
            showIcon
            message={`整版预览生成失败：${state.error}`}
            description="不影响确认预填——预填后主视图会重新计算整版。"
          />
        </div>
      )}
    </div>
  )
}
