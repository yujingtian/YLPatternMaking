// 腰头布片（2026-09-17 九期腰头立体化）：把 payload 的 waistband 片
// （frame='local'，边链 bottom×2 + left_end/right_end + top、以**中点为
// 原点左右对称**——引擎腰头裁切链原样）作为第 5 参与片缝入腰圆。
// 用户口径：**腰头两端在前中线（会合）、中点是后中线**——与四段腰口弧
// 的自然环序 fL(前中→左侧)→bL(左侧→后中)→bR(后中→右侧)→fR(右侧→
// 前中) 完全吻合：环 arclength s=0 与 s=P 都在前中（带两端），s=P/2 落
// 后中（带中点）；左右两半弧长镜像相等（前 L/R、后 L/R 对称），中点
// 精确落中面。对账：直款 bottom_length = Σ四段腰弧（腰长不变量，
// fixture 实测 70.10 = 17.53×2+17.52×2 严格相等）；弯款 bottom > 顶
// （贝塞尔弧条），与纸样腰弧的差 = 省道开口吃势，arclen 配对沿环均匀
// 吸收（3D 无省道闭合建模，差量呈腰部轻微软褶 = 未收省的真实缝前语义）。
import type { FittingPiece, FittingResult } from '../../types'
import type { ClothMesh } from './mesh'
import { buildClothMesh } from './mesh'
import type { GarmentPart } from './assemble'

export const BAND_KEY = 'waistband'

// 腰头网格 = 通用 buildClothMesh（payload 边链闭合环：bottom/end/top；
// 弯款贝塞尔边照常重采样；内部错排栅格 + delaunay）。frame='local' 的
// 局部系只喂 rest 长——3D 位置由环序行走摆放（见 assemble），不消费
// payload 的局部方位
export function buildWaistbandMesh(payload: FittingResult): ClothMesh | null {
  const piece: FittingPiece | undefined =
    payload.pieces.find((p) => p.key === BAND_KEY)
  if (!piece) return null
  return buildClothMesh(piece)
}

// ---- 腰环行走（四段腰口弧 → 有序顶点链）----
// 方向约定（与 buildFullPair Step2 的「order[0]=中缝腰角」一致）：
// fL 正序（前中→左侧）、bL 逆序（左侧→后中）、bR 正序（后中→右侧）、
// fR 逆序（右侧→前中）——环行走自前中起、经左侧绕过后中回到前中。
// arc 记**纸样弧长**（run.arc/run.length 段内分数 × run.length 链长
// 权重——吃势按纸样弧分布，与真实车缝一致；两半弧长镜像相等 ⇒ s=P/2
// 精确落后中 = 用户口径）
export interface RingWalk {
  verts: { part: number; idx: number; arc: number }[]   // 环序顶点（part = parts 下标）
  seqParts: number[]    // 四段 part 下标（fL/后L/后R/fR）——assemble ringMap
                        // 角检测按段语义取号（seam 模式后段 = back_yoke，
                        // part 下标随 parts 实际序变）
  total: number                                        // 纸样弧总长 P
}

export function ringWalk(parts: GarmentPart[]): RingWalk {
  const partOf = (key: string, side: 'L' | 'R') =>
    parts.findIndex((p) => p.key === key && p.side === side)
  // seam 模式（2026-09-22 有省育克升格参与片）：后身腰口弧由 yoke top'
  // 顶替——纯 back part 的 top 边 role='seam' 无 top_chain 会直接 throw。
  // yoke top'（O→X，翻转 cycle 同名聚合）与 union 宿主的反向腰口段
  // 完全同构，rev 语义不变
  const backKey = parts.some((p) => p.key === 'back_yoke') ? 'back_yoke' : 'back'
  const seq: { pi: number; rev: boolean }[] = [
    { pi: partOf('front', 'L'), rev: false },
    { pi: partOf(backKey, 'L'), rev: true },
    { pi: partOf(backKey, 'R'), rev: false },
    { pi: partOf('front', 'R'), rev: true },
  ]
  const verts: RingWalk['verts'] = []
  let total = 0
  for (const { pi, rev } of seq) {
    if (pi < 0) throw new Error('腰环行走缺 part（front/back_yoke × L/R）')
    const run = parts[pi].mesh.runs.find((r) => r.role === 'top_chain')
    if (!run) throw new Error('腰环行走缺 top_chain 边')
    const idxs = rev ? [...run.indices].reverse() : run.indices
    for (let k = 0; k < idxs.length; k++) {
      // 逆序行走弧 = run.length − 原弧（原末采样变行走首点）
      const orig = rev ? idxs.length - 1 - k : k
      const walkArc = rev ? run.length - run.arc[orig] : run.arc[orig]
      verts.push({ part: pi, idx: idxs[k], arc: total + walkArc })
    }
    total += run.length
  }
  return { verts, seqParts: seq.map((s) => s.pi), total }
}

// 环弧长 -> 最近环顶点下标（verts.arc 升序，线性扫——环顶点 ~200、
// 腰头顶点 ~50，构建期一次性，无需二分）
export function ringIndexAt(walk: RingWalk, s: number): number {
  const target = Math.max(0, Math.min(walk.total, s))
  let best = 0, bestD = Infinity
  for (let k = 0; k < walk.verts.length; k++) {
    const d = Math.abs(walk.verts[k].arc - target)
    if (d < bestD) { bestD = d; best = k }
  }
  return best
}

// ---- 腰头底边链（两条 'bottom' run 按端点衔接排成 端→中点→端 整链）----
export interface BandBottomChain {
  indices: number[]        // 有序底边顶点号（带局部号，端点含角点）
  pts: [number, number][]  // 对应局部坐标
  length: number           // 沿链累计弦长（u 归一用）
  runLength: number        // Σ 引擎边长（对账用——弦长缺角点步长会短 ~2%）
}

export function bandBottomChain(mesh: ClothMesh): BandBottomChain | null {
  const runs = mesh.runs.filter((r) => r.name === 'bottom')
  if (runs.length < 2) return null
  // 两条 run 衔接排序。角点共享规则（边界重采样每边不含终点、共享角点
  // = 下一条边首采样）：两段 bottom 的衔接端点之间差一个重采样步长
  // （~1.5cm），不能按精确重合判——放宽到一步长内（远端相距 ~70cm
  // 无误判风险）
  const near = (i: number, j: number) => Math.hypot(
    mesh.xy[2 * i] - mesh.xy[2 * j],
    mesh.xy[2 * i + 1] - mesh.xy[2 * j + 1]) < 3.5
  const [a, b] = runs
  const a0 = a.indices[0], aN = a.indices[a.indices.length - 1]
  const b0 = b.indices[0], bN = b.indices[b.indices.length - 1]
  let ordered: number[]
  if (near(a0, bN)) ordered = [...b.indices, ...a.indices]          // b→a
  else if (near(aN, b0)) ordered = [...a.indices, ...b.indices]     // a→b
  else return null
  // 链端补真实角点：bottom 边自身的终点不含采样（角点共享规则），缺的
  // 角点在 left_end/right_end 的首/末采样上——u=0/1 精确落带端（前中
  // 锚定）必须带上，否则端头投影内缩 ~1.5cm。**只收共线延展点**：候选
  // 必须沿链端段方向延展（角点在底边延长线上）——end 边自身的竖向采样
  // 距链端也近，但方向垂直，不能收
  const ends = mesh.runs.filter((r) => r.name === 'left_end' || r.name === 'right_end')
  const collinearExtend = (cand: number, endIdx: number, nextIdx: number): boolean => {
    const ex = mesh.xy[2 * endIdx] - mesh.xy[2 * nextIdx]
    const ey = mesh.xy[2 * endIdx + 1] - mesh.xy[2 * nextIdx + 1]
    const len = Math.hypot(ex, ey) || 1
    const perp = Math.abs(ex * (mesh.xy[2 * cand + 1] - mesh.xy[2 * endIdx + 1])
      - ey * (mesh.xy[2 * cand] - mesh.xy[2 * endIdx])) / len
    return perp < 0.5
  }
  for (const run of ends) {
    const first = run.indices[0], last = run.indices[run.indices.length - 1]
    const head = ordered[0], tail = ordered[ordered.length - 1]
    if (near(tail, first) && collinearExtend(first, tail, ordered[ordered.length - 2])) {
      ordered.push(first)
    } else if (near(head, last)
      && collinearExtend(last, head, ordered[1])) {
      ordered.unshift(last)
    }
  }
  const pts = ordered.map((i) =>
    [mesh.xy[2 * i], mesh.xy[2 * i + 1]] as [number, number])
  let length = 0
  for (let k = 1; k < pts.length; k++) {
    length += Math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1])
  }
  const runLength = runs.reduce((s, r) => s + r.length, 0)
  return { indices: ordered, pts, length, runLength }
}

// 点 -> 底边链的正交投影（u 弧长分数 + 带法向 v 距离，v 朝 top 侧为正）：
// 弯腰头底边是曲线，v 必须取**到链的垂直距离**而非局部 y（局部 y 沿弧
// 下沉 9.9cm，直接当高度会把弯带顶点摆飞）
export function projectOnChain(
  chain: BandBottomChain, x: number, y: number,
): { u: number; v: number } {
  let bestD = Infinity, bestU = 0, bestBx = 0, bestBy = 0, bestEx = 1, bestEy = 0
  let acc = 0
  const segLen: number[] = []
  for (let k = 1; k < chain.pts.length; k++) {
    const l = Math.hypot(chain.pts[k][0] - chain.pts[k - 1][0],
      chain.pts[k][1] - chain.pts[k - 1][1])
    segLen.push(l)
  }
  for (let k = 1; k < chain.pts.length; k++) {
    const [ax, ay] = chain.pts[k - 1], [bx, by] = chain.pts[k]
    const ex = bx - ax, ey = by - ay
    const l2 = ex * ex + ey * ey
    const t = l2 > 1e-12
      ? Math.max(0, Math.min(1, ((x - ax) * ex + (y - ay) * ey) / l2)) : 0
    const px = ax + ex * t, py = ay + ey * t
    const d = Math.hypot(x - px, y - py)
    if (d < bestD) {
      bestD = d; bestU = (acc + t * segLen[k - 1]) / (chain.length || 1)
      bestBx = px; bestBy = py
      const len = Math.sqrt(l2) || 1
      bestEx = ex / len; bestEy = ey / len
    }
    acc += segLen[k - 1]
  }
  // 符号：top 侧为 v 正——局部系 top 在 bottom 有向链的叉积负侧
  // （ex×(p−proj) 的 z 分量对 top 点为负，实测直款 −4）
  const cross = bestEx * (y - bestBy) - bestEy * (x - bestBx)
  return { u: bestU, v: -Math.sign(cross) * bestD }
}

// 每个带顶点 -> (环顶点下标, 带法向距离 v)：**摆位与缝合配对的同源
// 映射**（assemble 摆放与 seams bandWaist 配对都调它——保证带底顶点
// 落在配对环顶点原位、初始间隙 0）。u = 底边链投影弧长分数（端 0/1
// 落前中、中点 0.5 落后中），v = 到链垂直距离（top 侧为正）
export function bandTargets(
  mesh: ClothMesh, walk: RingWalk,
): { ringK: number; v: number }[] | null {
  const chain = bandBottomChain(mesh)
  if (!chain) return null
  const out: { ringK: number; v: number }[] = []
  for (let i = 0; i < mesh.xy.length / 2; i++) {
    const { u, v } = projectOnChain(chain, mesh.xy[2 * i], mesh.xy[2 * i + 1])
    out.push({ ringK: ringIndexAt(walk, u * walk.total), v })
  }
  return out
}

// 腰头两端 weld 配对（left_end ↔ right_end）：**按等高配对**——两 end
// 边采样高度集错开一个步长（每边不含终点：left 采 4,2.67,1.33、right
// 采 0,1.33,2.67），索引一正一反配会错 1.33cm；只配高度近邻（差 < 半
// 步长），未配高度的顶点由别的族持有（底角在 bandWaist、顶角在 'top'
// 钉）。扣好的裤子（前中会合闭合环）；开门襟展示属后续可选项
export function bandEndPairs(mesh: ClothMesh): [number, number][] | null {
  const left = mesh.runs.find((r) => r.name === 'left_end')
  const right = mesh.runs.find((r) => r.name === 'right_end')
  if (!left || !right) return null
  const pairs: [number, number][] = []
  for (const li of left.indices) {
    const ly = mesh.xy[2 * li + 1]
    let best: number | null = null, bestD = Infinity
    for (const ri of right.indices) {
      const d = Math.abs(mesh.xy[2 * ri + 1] - ly)
      if (d < bestD) { bestD = d; best = ri }
    }
    if (best !== null && bestD < 0.75) pairs.push([li, best])
  }
  return pairs
}
