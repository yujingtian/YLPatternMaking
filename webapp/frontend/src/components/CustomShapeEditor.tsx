import { useEffect, useMemo, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { Button, InputNumber, Select } from 'antd'
import type { EdgeSpec, SeedResult } from '../types'

// custom 净形/自由链结构化编辑器（custom_shape 虚拟参数的通用渲染体）。
// 三类对象 = mode × edge_format 正交组合（schema _SHAPE_EDITOR_SPECS 下发）：
//   贴袋   closed + bulge：点 i → i+1 末边闭合，边 (弧高, 位置) 二元组
//   小表袋 closed + spec ：同闭合，边 line/arc/bezier 三模式（rotate 只影响摆放，不进预览）
//   袋布   open   + spec ：链 P_w0 → K1..Kn → P_s0，边数 = 节点数 + 1，
//           两端锚点不在存储数据里——由 anchor 参数前端近似复算（标注近似、不可拖）
// 点/边双表（联动增删）+ 内联轮廓预览 + 预览角点直接拖拽（回写 u/v、表格行
// 高亮联动）+ 从形态导入（seed，预设角点来自引擎纯函数，前端不复写公式）。
// 内部统一 v 向下正显示（前贴袋存储 dy 向上正，读写时换算）。
type EditorKind = 'front_patch' | 'back_patch' | 'front_pouch' | 'watch_pocket'

interface Props {
  kind: EditorKind
  vPositive: 'down' | 'up'        // 存储值第二轴方向（back=v 向下正 / front=dy 向上正）
  mode: 'closed' | 'open'         // 闭合净形 / 开放链
  edgeFormat: 'bulge' | 'spec'    // 边形态格式
  seedChoices: string[]           // 可导入的预设形态（空 = 无导入入口，如小表袋）
  anchorVals?: number[]           // open 模式近似锚点四参数
                                 // [p1_dist, waist_safe, p2_drop, side_safe]
  points: [number, number][]      // 存储原样（native 系）
  edges: EdgeSpec[]
  onPoints: (pts: [number, number][]) => void
  onEdges: (eds: EdgeSpec[]) => void
  onSeed: (kind: EditorKind, shape: string) =>
    Promise<SeedResult | { ok: false; message: string }>
  err?: string                    // 后端 422 合并消息（points/edges 任一键）
}

const round2 = (x: number) => Math.round(x * 100) / 100

// spec 边三模式的切换默认值（纯 UI 便利，不进引擎）
const EDGE_DEFAULTS: Record<string, EdgeSpec> = {
  line: ['line'],
  arc: ['arc', 2, 0.5],
  bezier: ['bezier', 30, 0.4, -30, 0.4],
}

// 弧边控制点：引擎 curves.arc_through 同式——两控制点各沿法向偏移 bulge·8/3、
// 放在弦上 at/2 与 (1+at)/2 处（实际弧高 ≈ 2·bulge；显示系法向 (dy,-dx) 为
// 引擎 Y-up 左手法向 (-dy,dx) 经 v 向下镜像，凸向与整版一致）。
// 初版误用二次贝塞尔 Q、控制点只偏移 bulge，弧高仅 0.5·bulge，差 4 倍
// （2026-08-27 用户报障：预览弧线效果不明显、与整版形状不符）
const arcCtrls = (a: [number, number], b: [number, number],
                  bulge: number, at: number): [[number, number],
                                                [number, number]] => {
  const dx = b[0] - a[0]
  const dy = b[1] - a[1]
  const len = Math.hypot(dx, dy) || 1
  const off = (bulge * 8) / 3
  const nx = (dy / len) * off
  const ny = (-dx / len) * off
  return [[a[0] + dx * (at / 2) + nx, a[1] + dy * (at / 2) + ny],
          [a[0] + dx * ((1 + at) / 2) + nx, a[1] + dy * ((1 + at) / 2) + ny]]
}

// 引擎 Y-up 系 rotate(+α) 经 v 向下镜像 = 显示系矩阵 [[cos,sin],[-sin,cos]]
// （bezier 控制点前端按 edge_geom 同式复算，显示层近似、引擎为准）
const rotDisp = (vx: number, vy: number, deg: number): [number, number] => {
  const t = (deg * Math.PI) / 180
  return [vx * Math.cos(t) + vy * Math.sin(t),
          -vx * Math.sin(t) + vy * Math.cos(t)]
}

export default function CustomShapeEditor({
  kind, vPositive, mode, edgeFormat, seedChoices, anchorVals,
  points, edges, onPoints, onEdges, onSeed, err,
}: Props) {
  const [seedSel, setSeedSel] = useState<string | undefined>(undefined)
  const [seeding, setSeeding] = useState(false)
  const [seedMsg, setSeedMsg] = useState<string | null>(null)

  // 预览拖拽：dragIdx = 正在拖的角点序号（表格行高亮 + scrollIntoView 联动）
  const svgRef = useRef<SVGSVGElement | null>(null)
  const rowRefs = useRef<(HTMLDivElement | null)[]>([])
  const [dragIdx, setDragIdx] = useState<number | null>(null)

  // 显示系（v 向下正）<-> 存储系：front 存 dy 向上正，读写取负
  const flip = vPositive === 'up' ? -1 : 1
  const disp = points.map(([a, b]) => [a, b * flip] as [number, number])
  const commit = (next: [number, number][]) =>
    onPoints(next.map(([a, b]) => [a, b * flip] as [number, number]))

  // open 链两端近似锚点（袋布）：腰弧近似水平 / 侧缝近似竖直的前端直算，
  // 真值由整版几何实时定（P_w0 = 腰弧上越过 P1 朝门襟 +x、P_s0 = P2 沿
  // 侧缝下探——x 正向与 K 节点 dx 同系，front_pouch_steps L70-82）
  const open = mode === 'open'
  const [a0, a1, a2, a3] = anchorVals ?? []
  const anchorStart: [number, number] | null = open
    ? [(a0 ?? 0) + (a1 ?? 0), 0] : null
  const anchorEnd: [number, number] | null = open
    ? [0, (a2 ?? 0) + (a3 ?? 0)] : null
  // 显示系全链：closed = 角点环；open = [P_w0, K 节点…, P_s0]
  const chain = open ? [anchorStart!, ...disp, anchorEnd!] : disp
  const minPts = open ? 2 : 3
  // 边 j 连链点 j → j+1（closed 末边绕回首点）；缺行兜底按格式给直线
  const edgeAt = (j: number): EdgeSpec =>
    edges[j] ?? (edgeFormat === 'bulge' ? [0, 0.5] : ['line'])

  const setPt = (i: number, axis: 0 | 1, v: number | null) => {
    const next = disp.map((p) => [p[0], p[1]] as [number, number])
    next[i][axis] = v ?? 0
    commit(next)
  }
  // spec 边参数位 1..4（arc 用 1-2、bezier 全用）；bulge 边等价位 0..1
  const setEdgeNum = (i: number, idx: number, v: number | null) => {
    const next = edges.map((e) => [...e])
    next[i][idx] = v ?? 0
    onEdges(next)
  }
  // spec 边模式切换：该边参数重置为新模式默认值
  const setEdgeMode = (i: number, m: string) => {
    const next = edges.map((e) => [...e])
    next[i] = [...EDGE_DEFAULTS[m]]
    onEdges(next)
  }
  // 删点 i = 同时删该点发出的边（closed 边 i / open 链位 i+1：首边归 P_w0）
  const delRow = (i: number) => {
    if (points.length <= minPts) return
    commit(disp.filter((_, j) => j !== i))
    onEdges(edges.filter((_, j) => j !== (open ? i + 1 : i)))
  }
  // 预览拖拽：指针坐标 -> SVG 用户系（getScreenCTM 已含 viewBox + meet 等比
  // 映射），0.1 步进圆整后回写存储系；setPointerCapture 后移出预览仍可拖
  const toLocal = (e: ReactPointerEvent): [number, number] | null => {
    const ctm = svgRef.current?.getScreenCTM()
    if (!ctm) return null
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse())
    return [p.x, p.y]
  }
  const startDrag = (i: number) => (e: ReactPointerEvent) => {
    e.preventDefault()
    try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* 忽略 */ }
    setDragIdx(i)
    rowRefs.current[i]?.scrollIntoView({ block: 'nearest' })
  }
  const moveDrag = (i: number) => (e: ReactPointerEvent) => {
    if (dragIdx !== i) return
    const p = toLocal(e)
    if (!p) return
    const next = disp.map((q) => [q[0], q[1]] as [number, number])
    next[i] = [Math.round(p[0] * 10) / 10, Math.round(p[1] * 10) / 10]
    commit(next)
  }
  const endDrag = () => setDragIdx(null)
  // 追加节点：closed 取闭合边中点、open 取末节点与 P_s0 中点（纯 UI 插值便利）
  // + 对应格式的新边；空态按对象给合法最小骨架
  const addRow = () => {
    if (disp.length === 0) {
      if (open) {
        commit([[4, 14], [1, 12]])
        onEdges([['line'], ['line'], ['line']])
      } else if (edgeFormat === 'spec') {
        commit([[0, 0], [6, 0], [6, 7]])
        onEdges([['line'], ['line'], ['line']])
      } else {
        commit([[0, 0], [10, 0], [10, 12]])
        onEdges([[0, 0.5], [0, 0.5], [0, 0.5]])
      }
      return
    }
    const last = disp[disp.length - 1]
    const tail = open ? anchorEnd! : disp[0]
    commit([...disp,
            [round2((last[0] + tail[0]) / 2), round2((last[1] + tail[1]) / 2)]])
    onEdges([...edges, edgeFormat === 'bulge' ? [0, 0.5] : ['line']])
  }

  const doSeed = async () => {
    if (!seedSel) return
    setSeeding(true)
    setSeedMsg(null)
    try {
      const r = await onSeed(kind, seedSel)
      if (r.ok) {
        // seed 返回 v 向下正规范系，写回存储系；数字圆整、模式串保留
        onPoints(r.points.map(([a, b]) => [a, b * flip] as [number, number]))
        onEdges(r.edges.map((e) =>
          e.map((x) => (typeof x === 'number' ? round2(x) : x))))
      } else {
        setSeedMsg('message' in r ? r.message : String(r))
      }
    } finally {
      setSeeding(false)
    }
  }

  // 轮廓预览：bbox 含弧顶点与 bezier 控制点（曲线凸包上界，安全近似）
  const view = useMemo(() => {
    const n = chain.length
    if (n === 0) return null
    const segs = open ? n - 1 : n
    const hull: [number, number][] = [...chain]
    let d = ''
    for (let j = 0; j < segs; j++) {
      const a = chain[j]
      const b = chain[(j + 1) % n]
      const cmd = j === 0 ? 'M' : 'L'
      d += `${cmd} ${a[0]} ${a[1]} `
      if (edgeFormat === 'spec') {
        const spec = edgeAt(j)
        const m = String(spec[0])
        if (m === 'arc') {
          const [c1, c2] = arcCtrls(a, b, Number(spec[1]), Number(spec[2]))
          hull.push(c1, c2)
          d += `C ${c1[0]} ${c1[1]} ${c2[0]} ${c2[1]} ${b[0]} ${b[1]} `
        } else if (m === 'bezier') {
          // C1 = A + κ1·L0·û(α)、C2 = B + κ2·L0·û(β)，角度经 Y 翻镜像取负
          const dx = b[0] - a[0]
          const dy = b[1] - a[1]
          const l0 = Math.hypot(dx, dy) || 1
          const r1 = rotDisp(dx / l0, dy / l0, Number(spec[1]))
          const r2 = rotDisp(dx / l0, dy / l0, Number(spec[3]))
          const k1 = Number(spec[2]) * l0
          const k2 = Number(spec[4]) * l0
          const c1: [number, number] = [a[0] + r1[0] * k1, a[1] + r1[1] * k1]
          const c2: [number, number] = [b[0] + r2[0] * k2, b[1] + r2[1] * k2]
          hull.push(c1, c2)
          d += `C ${c1[0]} ${c1[1]} ${c2[0]} ${c2[1]} ${b[0]} ${b[1]} `
        } else {
          d += `L ${b[0]} ${b[1]} `
        }
      } else {
        const bulge = Number(edgeAt(j)[0])
        const at = Number(edgeAt(j)[1] ?? 0.5)
        if (bulge !== 0) {
          const [c1, c2] = arcCtrls(a, b, bulge, at)
          hull.push(c1, c2)
          d += `C ${c1[0]} ${c1[1]} ${c2[0]} ${c2[1]} ${b[0]} ${b[1]} `
        } else {
          d += `L ${b[0]} ${b[1]} `
        }
      }
    }
    const xs = hull.map((p) => p[0])
    const ys = hull.map((p) => p[1])
    const pad = 2.4      // 含角点序号/锚点标签的出框量
    const minX = Math.min(...xs) - pad
    const maxX = Math.max(...xs) + pad
    const minY = Math.min(...ys) - pad
    const maxY = Math.max(...ys) + pad
    return { d, box: [minX, minY, maxX - minX, maxY - minY] as const }
  }, [chain, edges, edgeFormat, open])

  // 预览缩放（细长形/密集点检查用）：vp=null 自适应 bbox；用户缩放后接管为
  // 显式 viewBox，重置回自适应。滚轮以指针为焦点、按钮以当前中心为焦点；
  // getScreenCTM 含当前 viewBox，拖拽/焦点换算在任意缩放级下自动正确
  const [vp, setVp] =
    useState<{ x: number; y: number; w: number; h: number } | null>(null)
  const zoomBy = (k: number, focus?: { x: number; y: number }) => {
    if (!view) return
    const cur = vp ?? { x: view.box[0], y: view.box[1],
                        w: view.box[2], h: view.box[3] }
    const w = Math.min(Math.max(cur.w / k, view.box[2] / 15), view.box[2])
    const s = w / cur.w          // 等比（缩放极限夹在 1x~15x）
    const f = focus ?? { x: cur.x + cur.w / 2, y: cur.y + cur.h / 2 }
    setVp({ x: f.x - (f.x - cur.x) * s, y: f.y - (f.y - cur.y) * s,
            w, h: cur.h * s })
  }
  // 滚轮缩放须原生 non-passive 监听（React 合成 onWheel 是 passive，
  // preventDefault 无效页面会跟着滚）；经 ref 取最新 zoomBy 防闭包陈旧
  const zoomRef = useRef(zoomBy)
  zoomRef.current = zoomBy
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const ctm = svg.getScreenCTM()
      if (!ctm) return
      const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse())
      zoomRef.current(e.deltaY < 0 ? 1.25 : 0.8, { x: p.x, y: p.y })
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  }, [])

  // 拖拽命中半径自适应：密集小形不过度重叠、稀疏大形好抓（open 含锚点间距）
  const hitR = (i: number) => {
    const ci = open ? i + 1 : i
    let m = Infinity
    for (let j = 0; j < chain.length; j++) {
      if (j === ci) continue
      m = Math.min(m, Math.hypot(chain[j][0] - chain[ci][0],
                                 chain[j][1] - chain[ci][1]))
    }
    if (!Number.isFinite(m)) m = 4
    return Math.max(0.5, Math.min(1.2, m * 0.35))
  }

  const rowBtns = (i: number) => (
    <span className="shape-ops">
      <Button type="text" size="small" danger disabled={points.length <= minPts}
              onClick={() => delRow(i)} title="删除">✕</Button>
    </span>
  )

  // spec 边表列含义随模式复用：slot1 = 弧高/α°、slot2 = 位置/κ1、
  // slot3 = β°、slot4 = κ2（arc 用 1-2、bezier 全用、line 全禁）
  const specRow = (e: EdgeSpec, i: number) => {
    const m = String(e[0] ?? 'line')
    const isArc = m === 'arc'
    const isBez = m === 'bezier'
    // 软校验口径与引擎 _normalize_edge_specs 对齐：袋布弧顶分位闭区间
    // [0.1,0.9]、其余开区间 (0,1)；|弧高|≤10、|α|,|β|≤90°、κ∈(0,1]
    const pouch = kind === 'front_pouch'
    const atBad = isArc && (pouch
      ? !(Number(e[2]) >= 0.1 && Number(e[2]) <= 0.9)
      : !(Number(e[2]) > 0 && Number(e[2]) < 1))
    const kap1Bad = isBez && !(Number(e[2]) > 0 && Number(e[2]) <= 1)
    const kap2Bad = isBez && !(Number(e[4]) > 0 && Number(e[4]) <= 1)
    return (
      <div className="shape-row spec" key={i}>
        <span className="shape-idx">{i + 1}</span>
        <Select size="small" value={m}
                options={['line', 'arc', 'bezier'].map((v) => ({ value: v, label: v }))}
                onChange={(v) => setEdgeMode(i, v)} />
        <InputNumber size="small" step={0.1}
                     min={isArc ? -10 : isBez ? -90 : undefined}
                     max={isArc ? 10 : isBez ? 90 : undefined}
                     disabled={!isArc && !isBez}
                     value={isArc || isBez ? Number(e[1]) : undefined}
                     status={isArc && Math.abs(Number(e[1])) > 10
                       || isBez && Math.abs(Number(e[1])) > 90 ? 'error' : undefined}
                     onChange={(v) => setEdgeNum(i, 1, v)} />
        <InputNumber size="small" step={0.05}
                     min={isArc && pouch ? 0.1 : 0}
                     max={isArc && pouch ? 0.9 : 1}
                     disabled={m === 'line'}
                     value={isArc || isBez ? Number(e[2]) : undefined}
                     status={atBad || kap1Bad ? 'error' : undefined}
                     onChange={(v) => setEdgeNum(i, 2, v)} />
        <InputNumber size="small" step={5} min={-90} max={90} disabled={!isBez}
                     value={isBez ? Number(e[3]) : undefined}
                     status={isBez && Math.abs(Number(e[3])) > 90 ? 'error' : undefined}
                     onChange={(v) => setEdgeNum(i, 3, v)} />
        <InputNumber size="small" step={0.05} min={0} max={1} disabled={!isBez}
                     value={isBez ? Number(e[4]) : undefined}
                     status={kap2Bad ? 'error' : undefined}
                     onChange={(v) => setEdgeNum(i, 4, v)} />
        <span className="shape-ops" />
      </div>
    )
  }

  const nodeWord = open ? '节点' : '角点'

  return (
    <div className="shape-editor">
      {seedChoices.length > 0 && (
        <div className="shape-toolbar">
          <Select
            size="small" style={{ width: 132 }} placeholder="选择预设形态"
            value={seedSel} onChange={setSeedSel}
            options={seedChoices.map((c) => ({ value: c, label: c }))}
          />
          <Button size="small" loading={seeding} disabled={!seedSel}
                  onClick={() => void doSeed()}>从形态导入</Button>
        </div>
      )}
      {seedMsg && <div className="shape-msg">{seedMsg}</div>}
      {err && <div className="param-msg">{err}</div>}
      {points.length === 0 ? (
        <div className="shape-empty">
          点集为空：{seedChoices.length > 0 ? '从上方预设形态导入，或直接添加' : '直接添加'}{nodeWord}
        </div>
      ) : (
        <div className="shape-tables">
          <div className="shape-table">
            <div className="shape-thead">
              <span>#</span><span>u</span><span>v↓</span><span />
            </div>
            {disp.map((p, i) => (
              <div className={dragIdx === i ? 'shape-row active' : 'shape-row'}
                   key={i}
                   ref={(el) => { rowRefs.current[i] = el }}>
                <span className="shape-idx">{i + 1}</span>
                <InputNumber size="small" step={0.1} value={p[0]}
                             onChange={(v) => setPt(i, 0, v)} />
                <InputNumber size="small" step={0.1} value={p[1]}
                             onChange={(v) => setPt(i, 1, v)} />
                {rowBtns(i)}
              </div>
            ))}
            <Button size="small" type="dashed" block
                    className="shape-add" onClick={addRow}>+ 添加{nodeWord}</Button>
          </div>
          <div className="shape-table">
            {edgeFormat === 'spec' ? (
              <>
                <div className="shape-thead spec">
                  <span>#</span><span>模式</span><span>弧高/α°</span>
                  <span>位置/κ1</span><span>β°</span><span>κ2</span><span />
                </div>
                {edges.map(specRow)}
                <div className="shape-hint">
                  边 i 连链点 i → i+1{open ? '（首段接 P_w0、末段接 P_s0）' : '（末边闭合）'}；
                  arc = 弧高 + 弧顶分位、bezier = 双手柄夹角 + 弦长比；预览支持滚轮/右上按钮缩放
                </div>
              </>
            ) : (
              <>
                <div className="shape-thead">
                  <span>#</span><span>弧高</span><span>位置</span><span />
                </div>
                {edges.map((e, i) => {
                  const badAt = Number(e[0]) !== 0
                    && !(Number(e[1]) > 0 && Number(e[1]) < 1)
                  return (
                    <div className="shape-row" key={i}>
                      <span className="shape-idx">{i + 1}</span>
                      <InputNumber size="small" step={0.1} min={-10} max={10}
                                   value={Number(e[0])}
                                   onChange={(v) => setEdgeNum(i, 0, v)} />
                      <InputNumber size="small" step={0.05} min={0} max={1}
                                   value={Number(e[1])} disabled={Number(e[0]) === 0}
                                   status={badAt ? 'error' : undefined}
                                   onChange={(v) => setEdgeNum(i, 1, v)} />
                      <span className="shape-ops" />
                    </div>
                  )
                })}
                <div className="shape-hint">弧高 0 = 直线；边 i 连角点 i → i+1（末边闭合）；预览中可直接拖动角点；预览支持滚轮/右上按钮缩放</div>
              </>
            )}
          </div>
        </div>
      )}
      {view && (
        <div className="shape-preview-wrap">
          <div className="shape-zoom">
            <Button size="small" onClick={() => zoomBy(1 / 1.3)}
                    title="缩小">−</Button>
            <Button size="small" disabled={!vp} onClick={() => setVp(null)}
                    title="回到自适应视图">重置</Button>
            <Button size="small" onClick={() => zoomBy(1.3)}
                    title="放大">+</Button>
          </div>
          <svg className="shape-preview"
               viewBox={(vp ? [vp.x, vp.y, vp.w, vp.h] : view.box).join(' ')}
               preserveAspectRatio="xMidYMid meet" ref={svgRef}>
          <path d={view.d + (open ? '' : 'Z')}
                fill={open ? 'none' : 'rgba(44,110,73,0.08)'}
                stroke="#2c6e49" strokeWidth={0.35} />
          {anchorStart && (
            <g className="pt-anchor">
              <rect x={anchorStart[0] - 0.5} y={anchorStart[1] - 0.5}
                    width={1} height={1} fill="#bfbfbf" stroke="#8c8c8c"
                    strokeWidth={0.18} />
              <text x={anchorStart[0] - 0.8} y={anchorStart[1] - 0.4}
                    fontSize={2.2} fill="#8c8c8c" textAnchor="end">P_w0(近似)</text>
            </g>
          )}
          {anchorEnd && (
            <g className="pt-anchor">
              <rect x={anchorEnd[0] - 0.5} y={anchorEnd[1] - 0.5}
                    width={1} height={1} fill="#bfbfbf" stroke="#8c8c8c"
                    strokeWidth={0.18} />
              <text x={anchorEnd[0] + 0.8} y={anchorEnd[1] - 0.4}
                    fontSize={2.2} fill="#8c8c8c">P_s0(近似)</text>
            </g>
          )}
          {disp.map((p, i) => (
            <g key={i} className={dragIdx === i ? 'pt-dragging' : undefined}
               onPointerDown={startDrag(i)} onPointerMove={moveDrag(i)}
               onPointerUp={endDrag} onPointerCancel={endDrag}>
              <circle cx={p[0]} cy={p[1]} r={hitR(i)}
                      fill="transparent" pointerEvents="all" />
              <circle cx={p[0]} cy={p[1]} r={dragIdx === i ? 0.62 : 0.45}
                      fill={dragIdx === i ? '#d46b08' : '#fff'}
                      stroke={dragIdx === i ? '#d46b08' : '#2c6e49'}
                      strokeWidth={0.25} pointerEvents="none" />
              <text x={p[0] + 0.7} y={p[1] - 0.5} fontSize={2.2}
                    fill="#666" pointerEvents="none">{i + 1}</text>
            </g>
          ))}
        </svg>
        </div>
      )}
    </div>
  )
}
