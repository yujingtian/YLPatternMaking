// 前身整体并集净样（2026-09-16 四期前身缝合立起）：front_piece +
// front_facing 沿袋口净线 mouth 缝合成一张净样面板，喂 buildClothMesh
// 得悬挂解算宿主（drape/buildFrontPair 吃宿主；前片与袋贴本体走
// rider.ts 贴层渲染）。几何真相（fixture 实测）：前片开口袋后腰口被
// 挖短（waist 止于 mouth 首点 M0），mouth 弧以上到原始轮廓的月牙区已
// 在前片净样之外；facing 外边 1:1 复制挖削**前**前大片轮廓，mouth 两
// 端点分别落在 facing 的 waist/side 边上（投影残差 ~0.003cm）——所以
// 袋贴无法直接绑前片网格（月牙区顶点 locate 全 null），必须先并集。
// 并集 = 业务真相「袋贴已缝前片」（2026-09-16 用户口径）：mouth 内部
// 化为缝线；facing 腰口子段命名 'waist' 与 front.waist 同名相邻，经
// mesh.ts runs 自动聚合成整条腰口，drape 悬挂 pin 语义自动覆盖袋贴
// 腰口段——整个前身挂腰，物理正确。守卫失败（marks↔mouth 不贴合 /
// 端点投影超差）退化纯前片宿主，袋贴留平铺行（Fitting3DView 按
// hasFacing 决定 exclude），不硬拼。
import type { FittingEdge, FittingPiece, FittingResult } from '../../types'
import type { ClothMesh } from './mesh'
import { buildClothMesh } from './mesh'
import { frontFacingAligned } from './assemble'

export interface FrontPanel {
  host: ClothMesh        // 前身整体宿主网格（解算/摆位载体，不渲染）
  hasFacing: boolean     // 袋贴成功拼入；false = 退化纯前片宿主
  warnings: string[]     // 退化原因（上屏 hint 用）
}

// 点投影到折线：最近所在段号 + 段内参数 + 距离（分段最近，端点如实计）
function projectOnPolyline(
  p: [number, number], pts: [number, number][],
): { seg: number; t: number; dist: number } {
  let seg = 0, t = 0
  let best = Infinity
  for (let s = 0; s < pts.length - 1; s++) {
    const [x0, y0] = pts[s], [x1, y1] = pts[s + 1]
    const dx = x1 - x0, dy = y1 - y0
    const len2 = dx * dx + dy * dy
    const u = len2 > 1e-12
      ? Math.max(0, Math.min(1, ((p[0] - x0) * dx + (p[1] - y0) * dy) / len2))
      : 0
    const dist = Math.hypot(p[0] - (x0 + dx * u), p[1] - (y0 + dy * u))
    if (dist < best) { best = dist; seg = s; t = u }
  }
  return { seg, t, dist: best }
}

const JOIN_TOL = 0.5   // cm：mouth 端点落在 facing 边上的投影容差（与 STITCH_GAP 同量级）

const polylineLen = (pts: [number, number][]): number => {
  let l = 0
  for (let i = 0; i < pts.length - 1; i++) {
    l += Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
  }
  return l
}

export function buildFrontPanel(payload: FittingResult): FrontPanel {
  const front = payload.pieces.find((p) => p.key === 'front_piece')
  if (!front) throw new Error('payload 缺 front_piece——前身并集无从合成')
  const facing = payload.pieces.find((p) => p.key === 'front_facing')

  const degenerate = (reason: string): FrontPanel => ({
    host: buildClothMesh(front),
    hasFacing: false,
    warnings: [reason],
  })

  if (!facing) {
    return degenerate('无袋贴片（front_pocket_facing 未开）——前身宿主退化纯前片')
  }
  if (!frontFacingAligned(front, facing)) {
    return degenerate('袋贴袋口净线与前片 mouth 边不贴合——并集守卫拦下，退化纯前片')
  }
  // mouth 聚合链（同名连续段拼接）：首点 M0 = 近腰口端（落在 facing
  // waist 边上）、末点 M1 = 侧缝端（落在 facing side 边上）
  const mouthPts = front.edges
    .filter((e) => e.name === 'mouth')
    .flatMap((e) => e.pts)
  if (mouthPts.length < 2) {
    return degenerate('前片无 mouth 袋口边——并集无从下手')
  }
  // facing 边链闭环：side(O→P_fs) → inner(P_fs→P_fw) → waist(P_fw→O)
  const fSide = facing.edges.find((e) => e.name === 'side')
  const fWaist = facing.edges.find((e) => e.name === 'waist')
  if (!fSide || !fWaist) {
    return degenerate('袋贴边链缺 side/waist——并集无从下手')
  }
  const M0 = mouthPts[0], M1 = mouthPts[mouthPts.length - 1]
  const p0 = projectOnPolyline(M0, fWaist.pts)
  const p1 = projectOnPolyline(M1, fSide.pts)
  if (p0.dist > JOIN_TOL || p1.dist > JOIN_TOL) {
    return degenerate(`mouth 端点投影超差（waist ${p0.dist.toFixed(2)} / `
      + `side ${p1.dist.toFixed(2)} cm > ${JOIN_TOL}）——退化纯前片`)
  }
  // 子段截取（保持 facing 原方向）：waist M0→O（正向至末点 O = 侧腰点）、
  // side O→M1（首点 O 正向至 M1）——与 front 边链 mouth 前后邻接方向
  // 天然一致（front.waist 止于 M0、front.side 始于 M1），闭环无缝
  const waistPartial: [number, number][] = [M0, ...fWaist.pts.slice(p0.seg + 1)]
  const sidePartial: [number, number][] = [...fSide.pts.slice(0, p1.seg + 1), M1]
  const joinWaist: FittingEdge = {
    name: 'waist', kind: 'line', role: 'top_chain',
    pts: waistPartial, length: polylineLen(waistPartial),
  }
  const joinSide: FittingEdge = {
    name: 'side', kind: 'line', role: 'seam',
    pts: sidePartial, length: polylineLen(sidePartial),
  }
  // 前身净样边链 = front 边链 mouth 段原位替换为 facing 月牙边
  const edges: FittingEdge[] = []
  for (const e of front.edges) {
    if (e.name === 'mouth') edges.push(joinWaist, joinSide)
    else edges.push(e)
  }
  // buildClothMesh 只读 edges；其余字段沿用 front 占位（key 改名防误用）
  const unionPiece: FittingPiece = {
    ...front, key: 'front_panel', name: '前身整体（前片+袋贴缝合）', edges,
  }
  return { host: buildClothMesh(unionPiece), hasFacing: true, warnings: [] }
}
