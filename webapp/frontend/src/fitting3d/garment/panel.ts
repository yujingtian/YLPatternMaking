// 前身整体并集净样（2026-09-16 四期前身缝合立起）：front_piece +
// front_facing 沿袋口净线 mouth 缝合成一张净样面板，喂 buildClothMesh
// 得悬挂解算宿主（drape/buildFullPair 吃宿主；前片与袋贴本体走
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
//
// 后身整体并集净样（2026-09-16 六期后身缝合立起）：back_piece +
// back_yoke 沿机头下口线缝合成一张净样面板。与前身不同处：缝合依据
// 线是 back.top（P0→PN，有 yoke 时角色 seam）= yoke.bottom（整版同一
// 净线，无省款逐点重合），并集 = 把 back 边链的 top 段**原位替换**为
// yoke 余边闭环路径（cb 反向 P0→O + 腰口反向 O→X + 侧缝反向 X→PN），
// 机头下口线内部化为缝线。边链重排（top 段丢弃后 yoke 余边接在数组
// 末尾）：back.cb（裆尖→P0）与 yoke cb 反向段（P0→O）同名相邻，经
// mesh.ts runs 聚合成**整条后浪**（裆尖→腰口 O）——drape 后中缝合
// 对沿 cb 链配对，缝线贯通育克到腰；yoke 腰口 top 角色顶替 top_chain
// （drape 挂腰 pin 自动覆盖），yoke 侧缝段与 back 侧缝同名接续。守卫
// 失败（有省款 yoke 下边是省闭口净样、与整版下口线错位 ~12cm）退化
// 纯后片宿主，育克留平铺行（Fitting3DView 按 hasYoke 决定 exclude）。
import type { FittingEdge, FittingPiece, FittingResult } from '../../types'
import type { ClothMesh } from './mesh'
import { buildClothMesh } from './mesh'
import { backYokeAligned, frontFacingAligned } from './assemble'

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

export interface BackPanel {
  host: ClothMesh        // 后身整体宿主网格（解算/摆位载体，不渲染）
  hasYoke: boolean       // 育克成功拼入；false = 退化纯后片宿主
  warnings: string[]     // 退化原因（上屏 hint 用）
}

// 边反向（端点对调、名/类/长不变）——yoke 余边按 P0→PN 绕行方向与
// back 边链衔接需要
const reversedEdge = (e: FittingEdge): FittingEdge => ({
  ...e, pts: [...e.pts].reverse(),
})

export function buildBackPanel(payload: FittingResult): BackPanel {
  const back = payload.pieces.find((p) => p.key === 'back_piece')
  if (!back) throw new Error('payload 缺 back_piece——后身并集无从合成')
  const yoke = payload.pieces.find((p) => p.key === 'back_yoke')

  // 退化宿主边角色修正：有育克款引擎把 back 的 top 边（机头下口线）角色
  // 覆写为 seam（本该由育克腰口顶替 top_chain）；守卫拦下育克后该边
  // 语义回归腰口（八期：buildFullPair/drape 都按 top_chain 找腰口钉挂）
  const degenerate = (reason: string | null): BackPanel => ({
    host: buildClothMesh({
      ...back,
      edges: back.edges.map((e) =>
        e.name === 'top' && e.role === 'seam'
          ? { ...e, role: 'top_chain' as const } : e),
    }),
    hasYoke: false,
    warnings: reason ? [reason] : [],
  })

  if (!yoke) {
    // 无育克 = 正常款型（back_yoke 未开），纯后片即后身本体，非守卫失败
    return degenerate('无育克片（back_yoke 未开）——后身宿主即纯后片')
  }
  if (!backYokeAligned(back, yoke)) {
    return degenerate('育克下边与后片上边（机头下口线）不贴合'
      + '（有省款省闭口净样与整版线错位）——并集守卫拦下，退化纯后片')
  }
  const backTop = back.edges.filter((e) => e.name === 'top')
  if (backTop.length === 0) {
    return degenerate('后片无 top 上边（无机头下口线）——并集无从下手')
  }
  const yCb = yoke.edges.find((e) => e.name === 'cb')
  const yTop = yoke.edges.find((e) => e.name === 'top')
  const ySide = yoke.edges.find((e) => e.name === 'side')
  if (!yCb || !yTop || !ySide) {
    return degenerate('育克边链缺 top/cb/side——并集无从下手')
  }
  // 后身净样边链 = back 边链丢弃 top 段（P0→PN 内部化为缝线），数组末尾
  // 接 yoke 余边反向闭环路径（cb: P0→O、top: O→X、side: X→PN）——
  // 末尾 cb 段紧接 back.cb（裆尖→P0），同名相邻聚合成整条后浪；loop
  // 末点 PN 回接首边（back.side 首点），闭环无缝
  const edges: FittingEdge[] = []
  for (const e of back.edges) {
    if (e.name !== 'top') edges.push(e)
  }
  edges.push(
    { ...reversedEdge(yCb), role: 'seam' },
    { ...reversedEdge(yTop), role: 'top_chain' },
    { ...reversedEdge(ySide), role: 'seam' },
  )
  // buildClothMesh 只读 edges；其余字段沿用 back 占位（key 改名防误用）
  const unionPiece: FittingPiece = {
    ...back, key: 'back_panel', name: '后身整体（后片+育克缝合）', edges,
  }
  return { host: buildClothMesh(unionPiece), hasYoke: true, warnings: [] }
}
