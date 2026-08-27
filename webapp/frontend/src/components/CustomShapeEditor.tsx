import { useMemo, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { Button, InputNumber, Select } from 'antd'
import type { SeedResult } from '../types'

// 贴袋 custom 形态结构化编辑器：点/边双表（联动增删）+ 内联轮廓预览 +
// 预览角点直接拖拽（回写 u/v、表格行高亮联动）+ 从形态导入
// （seed，预设角点来自引擎纯函数，前端不复写公式）。
// 内部统一 v 向下正显示（前贴袋存储 dy 向上正，读写时换算）；
// 边 i 连接角点 i -> i+1（末边闭合回角点 1），闭合隐式、边数==点数。
interface Props {
  kind: 'front_patch' | 'back_patch'
  vPositive: 'down' | 'up'        // 存储值第二轴方向（back=v 向下正 / front=dy 向上正）
  seedChoices: string[]           // 可导入的预设形态
  points: [number, number][]      // 存储原样（native 系）
  edges: [number, number][]
  onPoints: (pts: [number, number][]) => void
  onEdges: (eds: [number, number][]) => void
  onSeed: (kind: 'front_patch' | 'back_patch', shape: string) =>
    Promise<SeedResult | { ok: false; message: string }>
  err?: string                    // 后端 422 合并消息（points/edges 任一键）
}

const round2 = (x: number) => Math.round(x * 100) / 100

export default function CustomShapeEditor({
  kind, vPositive, seedChoices, points, edges,
  onPoints, onEdges, onSeed, err,
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

  const setPt = (i: number, axis: 0 | 1, v: number | null) => {
    const next = disp.map((p) => [p[0], p[1]] as [number, number])
    next[i][axis] = v ?? 0
    commit(next)
  }
  const setEdge = (i: number, axis: 0 | 1, v: number | null) => {
    const next = edges.map((e) => [e[0], e[1]] as [number, number])
    next[i][axis] = v ?? 0
    onEdges(next)
  }
  // 删点 i = 同时删边 i（边跟随起点角点）；点数下限 3（引擎校验）
  const delRow = (i: number) => {
    if (points.length <= 3) return
    commit(disp.filter((_, j) => j !== i))
    onEdges(edges.filter((_, j) => j !== i))
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
  // 追加角点取闭合边中点（纯 UI 插值便利）+ 对应直线边
  const addRow = () => {
    if (disp.length === 0) {
      commit([[0, 0], [10, 0], [10, 12]])
      onEdges([[0, 0.5], [0, 0.5], [0, 0.5]])
      return
    }
    const last = disp[disp.length - 1]
    const first = disp[0]
    commit([...disp,
            [round2((last[0] + first[0]) / 2), round2((last[1] + first[1]) / 2)]])
    onEdges([...edges, [0, 0.5]])
  }

  const doSeed = async () => {
    if (!seedSel) return
    setSeeding(true)
    setSeedMsg(null)
    try {
      const r = await onSeed(kind, seedSel)
      if (r.ok) {
        // seed 返回 v 向下正规范系，写回存储系
        onPoints(r.points.map(([a, b]) => [a, b * flip] as [number, number]))
        onEdges(r.edges.map(([a, b]) => [round2(a), round2(b)] as [number, number]))
      } else {
        setSeedMsg('message' in r ? r.message : String(r))
      }
    } finally {
      setSeeding(false)
    }
  }

  // 轮廓预览：bbox 含弧顶点；弧边二次贝塞尔近似（apex = 弦上 at 比例处
  // 沿屏幕系法向 (dy,-dx) 偏移 bulge——引擎 Y-up 系左手法向 (-dy,dx) 经
  // v 向下镜像，凸向与整版一致，金标 test_patch_custom_mode 推演钉死）
  const view = useMemo(() => {
    const n = disp.length
    if (n === 0) return null
    const apexes: [number, number][] = []
    for (let i = 0; i < n; i++) {
      const [bulge, at] = edges[i] ?? [0, 0.5]
      if (bulge === 0) continue
      const a = disp[i]
      const b = disp[(i + 1) % n]
      const dx = b[0] - a[0]
      const dy = b[1] - a[1]
      const len = Math.hypot(dx, dy) || 1
      apexes.push([a[0] + dx * at + (dy / len) * bulge,
                   a[1] + dy * at + (-dx / len) * bulge])
    }
    const all = [...disp, ...apexes]
    const xs = all.map((p) => p[0])
    const ys = all.map((p) => p[1])
    const pad = 1.2
    const minX = Math.min(...xs) - pad
    const maxX = Math.max(...xs) + pad
    const minY = Math.min(...ys) - pad
    const maxY = Math.max(...ys) + pad
    let d = ''
    for (let i = 0; i < n; i++) {
      const a = disp[i]
      const b = disp[(i + 1) % n]
      const [bulge, at] = edges[i] ?? [0, 0.5]
      const cmd = i === 0 ? 'M' : 'L'
      if (bulge !== 0) {
        const dx = b[0] - a[0]
        const dy = b[1] - a[1]
        const len = Math.hypot(dx, dy) || 1
        const ax = a[0] + dx * at + (dy / len) * bulge
        const ay = a[1] + dy * at + (-dx / len) * bulge
        d += `${cmd} ${a[0]} ${a[1]} Q ${ax} ${ay} ${b[0]} ${b[1]} `
      } else {
        d += `${cmd} ${a[0]} ${a[1]} L ${b[0]} ${b[1]} `
      }
    }
    return { d, box: [minX, minY, maxX - minX, maxY - minY] as const, n }
  }, [disp, edges])

  // 拖拽命中半径自适应：密集小形不过度重叠、稀疏大形好抓
  const hitR = (i: number) => {
    let m = Infinity
    for (let j = 0; j < disp.length; j++) {
      if (j === i) continue
      m = Math.min(m, Math.hypot(disp[j][0] - disp[i][0], disp[j][1] - disp[i][1]))
    }
    if (!Number.isFinite(m)) m = 4
    return Math.max(0.5, Math.min(1.2, m * 0.35))
  }

  const rowBtns = (i: number) => (
    <span className="shape-ops">
      <Button type="text" size="small" danger disabled={points.length <= 3}
              onClick={() => delRow(i)} title="删除">✕</Button>
    </span>
  )

  return (
    <div className="shape-editor">
      <div className="shape-toolbar">
        <Select
          size="small" style={{ width: 132 }} placeholder="选择预设形态"
          value={seedSel} onChange={setSeedSel}
          options={seedChoices.map((c) => ({ value: c, label: c }))}
        />
        <Button size="small" loading={seeding} disabled={!seedSel}
                onClick={() => void doSeed()}>从形态导入</Button>
      </div>
      {seedMsg && <div className="shape-msg">{seedMsg}</div>}
      {err && <div className="param-msg">{err}</div>}
      {points.length === 0 ? (
        <div className="shape-empty">
          点集为空：从上方预设形态导入，或直接添加角点
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
                    className="shape-add" onClick={addRow}>+ 添加角点</Button>
          </div>
          <div className="shape-table">
            <div className="shape-thead">
              <span>#</span><span>弧高</span><span>位置</span><span />
            </div>
            {edges.map((e, i) => {
              const badAt = e[0] !== 0 && !(e[1] > 0 && e[1] < 1)
              return (
                <div className="shape-row" key={i}>
                  <span className="shape-idx">{i + 1}</span>
                  <InputNumber size="small" step={0.1} min={-10} max={10}
                               value={e[0]}
                               onChange={(v) => setEdge(i, 0, v)} />
                  <InputNumber size="small" step={0.05} min={0} max={1}
                               value={e[1]} disabled={e[0] === 0}
                               status={badAt ? 'error' : undefined}
                               onChange={(v) => setEdge(i, 1, v)} />
                  <span className="shape-ops" />
                </div>
              )
            })}
            <div className="shape-hint">弧高 0 = 直线；边 i 连角点 i → i+1（末边闭合）；预览中可直接拖动角点</div>
          </div>
        </div>
      )}
      {view && (
        <svg className="shape-preview" viewBox={view.box.join(' ')}
             preserveAspectRatio="xMidYMid meet" ref={svgRef}>
          <path d={view.d + 'Z'} fill="rgba(44,110,73,0.08)"
                stroke="#2c6e49" strokeWidth={0.35} />
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
      )}
    </div>
  )
}
