// 贴层绑定（2026-09-16 四期前身缝合立起）：前身整体（panel.ts 并集
// 宿主）进 verlet 解算，前片/袋贴本体**不进粒子系**——各自 buildClothMesh
// 三角化后每顶点重心绑定到宿主三角形（mesh.locate 现成预留位），每帧
// 由宿主三角形顶点 3D 位置插值重构（重心权重对三角形线性形**精确**，
// verlet 帧间即分段线性，无额外误差项）。L/R 共享同一份绑定——两 part
// 共享宿主网格（buildFrontPair），2D 绑定与 side 无关，回填时按
// hostOffset 区分。袋贴沿筒轴径向内偏 riderStep 衬里侧（真裤袋贴衬在
// 裤身里侧，前片盖住袋口条带，2026-09-16 用户口径「前片在前口袋上面」；
// 与平铺 stackStep 叠层同语义，防与宿主面共面 z-fight）。locate 失败
// 兜底 = 宿主边界环最近段插值（Delaunay 无约束，凹弧处窄楔形三角形
// 被质心过滤后边界有覆盖缺口——月牙区外边恰是凹弧，实测 facing 边界
// 顶点 11 个命中；段插值 = 弦近似弧，误差亚毫米），fallbackCount 记
// 数供诊断/金标。
import type { ClothMesh } from './mesh'

export interface RiderBind {
  mesh: ClothMesh            // 被载片渲染拓扑（vtx/w 与本网格顶点对齐）
  vtx: Int32Array            // 3N 宿主顶点号（三连 = 绑定三角形三顶点，宿主 part 内局部号）
  w: Float32Array            // 3N 重心权重（与 vtx 对齐，每三连和为 1）
  fallbackCount: number      // locate 失败走最近角兜底的顶点数（诊断）
}

export function bindRider(mesh: ClothMesh, host: ClothMesh): RiderBind {
  const n = mesh.xy.length / 2
  const vtx = new Int32Array(3 * n)
  const w = new Float32Array(3 * n)
  let fallbackCount = 0
  for (let i = 0; i < n; i++) {
    const loc = host.locate(mesh.xy[2 * i], mesh.xy[2 * i + 1])
    if (loc) {
      for (let s = 0; s < 3; s++) {
        vtx[3 * i + s] = host.tri[3 * loc.tri + s]
        w[3 * i + s] = loc.w[s]
      }
      continue
    }
    fallbackCount++
    // 兜底 = 宿主边界环最近段插值绑定（两顶点、退化三角）：
    // 被载片顶点严格在并集多边形内/边界上，locate null 只能是三角形
    // 覆盖缺口（Delaunay 无约束，凹弧处质心过滤掉窄楔形三角形——
    // 月牙区外边恰好是凹弧）。边界段插值 = 弦近似边界弧，误差 = 采样
    // 弧的弓高（亚毫米，贴层显示可接受），远优于最近角绑定
    const px = mesh.xy[2 * i], py = mesh.xy[2 * i + 1]
    const L = host.loop.length
    let bestI = 0, bestT = 0, bestD = Infinity
    for (let s = 0; s < L; s++) {
      const a = host.loop[s], b = host.loop[(s + 1) % L]
      const ax = host.xy[2 * a], ay = host.xy[2 * a + 1]
      const bx = host.xy[2 * b], by = host.xy[2 * b + 1]
      const dx = bx - ax, dy = by - ay
      const len2 = dx * dx + dy * dy
      const t = len2 > 1e-12
        ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2))
        : 0
      const qx = ax + dx * t, qy = ay + dy * t
      const d = (px - qx) * (px - qx) + (py - qy) * (py - qy)
      if (d < bestD) { bestD = d; bestI = s; bestT = t }
    }
    const a = host.loop[bestI], b = host.loop[(bestI + 1) % L]
    vtx[3 * i] = a; vtx[3 * i + 1] = b; vtx[3 * i + 2] = b
    w[3 * i] = 1 - bestT; w[3 * i + 1] = bestT; w[3 * i + 2] = 0
  }
  return { mesh, vtx, w, fallbackCount }
}

// 回填：宿主解算位 -> 贴层片位置（每 side 一次；hostOffset = 该 side
// part 在解算数组里的粒子偏移）。radialOffset 沿筒轴径向（原点 = 筒轴，
// 摆位/解算均在场系原点周围；显示层 Group 整体平移不破坏相对关系），
// 负值内偏（袋贴衬里侧）；y 分量不受偏移影响（高度 = 解算位精确值）。
export function rideRider(
  b: RiderBind, hostPos: Float32Array, hostOffset: number,
  out: Float32Array, radialOffset: number,
): void {
  const n = b.mesh.xy.length / 2
  const { vtx, w } = b
  for (let i = 0; i < n; i++) {
    const a0 = 3 * (hostOffset + vtx[3 * i])
    const a1 = 3 * (hostOffset + vtx[3 * i + 1])
    const a2 = 3 * (hostOffset + vtx[3 * i + 2])
    const w0 = w[3 * i], w1 = w[3 * i + 1], w2 = w[3 * i + 2]
    let px = w0 * hostPos[a0] + w1 * hostPos[a1] + w2 * hostPos[a2]
    const py = w0 * hostPos[a0 + 1] + w1 * hostPos[a1 + 1] + w2 * hostPos[a2 + 1]
    let pz = w0 * hostPos[a0 + 2] + w1 * hostPos[a1 + 2] + w2 * hostPos[a2 + 2]
    if (radialOffset !== 0) {
      const r = Math.hypot(px, pz)
      if (r > 1e-9) {
        const k = (r + radialOffset) / r
        px *= k
        pz *= k
      }
    }
    out[3 * i] = px
    out[3 * i + 1] = py
    out[3 * i + 2] = pz
  }
}
