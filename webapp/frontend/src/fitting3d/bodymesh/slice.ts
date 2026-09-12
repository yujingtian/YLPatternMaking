// 水平切片：三角形与 y=const 平面求交 -> 交线段 -> 闭环链（native.ts
// 站高探测/围度读数的底座）。约定：d = y_vertex − y_slice，d ≤ 0 记
// 「下」；跨面三角形恰有 2 条符号相异边（顶点恰在平面上计入「下」）。

export interface SlicePoint {
  x: number
  z: number
  segs: number[]      // 关联交线段号（闭环保守式：环内点度数 2）
}

export interface SliceLoop {
  pts: SlicePoint[]
  cx: number          // 环质心 x（环 -> 管/腿归属判据）
  girth: number       // 折线周长 cm（closed=false 时含假闭合边，仅供诊断）
  closed: boolean     // 水密网格恒 true；撕裂兜底（金标把守拓扑）
}

export function sliceLoops(
  pos: Float32Array, idx: Uint32Array, y: number,
): SliceLoop[] {
  // 顶点恰在平面上时环拓扑退化（交点重合成零长段、度 1 端点断链——
  // 合成网格环高与切片格点对齐必命中；真网格浮点 y 撞格点概率 ~0）：
  // 微移 1e-6 重切，围度影响 ~1e-6 cm 可忽略
  for (let i = 1; i < pos.length; i += 3) {
    if (Math.abs(pos[i] - y) < 1e-9) return sliceLoops(pos, idx, y + 1e-6)
  }
  const edgePt = new Map<number, SlicePoint>()
  const segs: { a: SlicePoint; b: SlicePoint }[] = []
  const d = (i: number) => pos[3 * i + 1] - y
  for (let f = 0; f < idx.length; f += 3) {
    const v0 = idx[f], v1 = idx[f + 1], v2 = idx[f + 2]
    const d0 = d(v0), d1 = d(v1), d2 = d(v2)
    const b0 = d0 <= 0, b1 = d1 <= 0, b2 = d2 <= 0
    if (b0 === b1 && b1 === b2) continue
    const cross: SlicePoint[] = []
    for (const [a, bb, da, db] of [
      [v0, v1, d0, d1], [v1, v2, d1, d2], [v2, v0, d2, d0],
    ] as const) {
      if ((da <= 0) === (db <= 0)) continue
      const lo = a < bb ? a : bb, hi = a < bb ? bb : a
      const key = lo * 0x100000 + hi
      let p = edgePt.get(key)
      if (!p) {
        const t = da / (da - db)
        p = {
          x: pos[3 * a] + t * (pos[3 * bb] - pos[3 * a]),
          z: pos[3 * a + 2] + t * (pos[3 * bb + 2] - pos[3 * a + 2]),
          segs: [],
        }
        edgePt.set(key, p)
      }
      cross.push(p)
    }
    if (cross.length === 2 && cross[0] !== cross[1]) {
      segs.push({ a: cross[0], b: cross[1] })
      cross[0].segs.push(segs.length - 1)
      cross[1].segs.push(segs.length - 1)
    }
  }
  // 链环：从未用段出发沿点身份走（每点恰 2 段）。闭合判据 = 走回**起点
  // 点**（按对象身份）——不能查「下一段是 s0」：s0 在起步时已标记 used，
  // 回到起点时其两段全 used、find 返回 undefined，会把闭环误判成开链
  // （度数异常的真撕裂仍走 undefined 分支截断）
  const used = new Uint8Array(segs.length)
  const loops: SliceLoop[] = []
  for (let s0 = 0; s0 < segs.length; s0++) {
    if (used[s0]) continue
    let cur = s0
    const startPt = segs[s0].a
    let pt = startPt
    const pts: SlicePoint[] = [pt]
    used[s0] = 1
    let cx = pt.x, guard = 0
    let closed = false
    while (true) {
      const seg = segs[cur]
      const nxtPt = seg.a === pt ? seg.b : seg.a
      if (nxtPt === startPt) { closed = true; break }
      pts.push(nxtPt)
      cx += nxtPt.x
      const next = nxtPt.segs.find((s) => !used[s])
      if (next === undefined) break            // 开链（网格撕裂保护）
      used[next] = 1
      cur = next
      pt = nxtPt
      if (++guard > segs.length) break         // 环 walk 安全阀
    }
    if (pts.length < 3) continue
    let g = 0
    for (let k = 0; k < pts.length; k++) {
      const p = pts[k], q = pts[(k + 1) % pts.length]
      g += Math.hypot(p.x - q.x, p.z - q.z)
    }
    loops.push({ pts, cx: cx / pts.length, girth: g, closed })
  }
  return loops
}
