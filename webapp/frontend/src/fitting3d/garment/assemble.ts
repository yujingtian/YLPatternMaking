// 静态装配（3D 展示重建，2026-09-15）：整裤缝合解算链已删，只装配
// 裁片平铺。payload schema v1 照旧发全片（引擎零改动）。两种摆位：
//   · buildFlatLayout（三期回落 → 2026-09-16 四期起 = 非前身裁片的平铺
//     验证通道：前身组经 panel.ts 并集合成后走悬挂链立起旁挂，exclude
//     参数把前身组移出平铺；其余片照旧）——payload 每片一行（成对片
//     L 原样 + R 镜像并排、腰头单片），缝合拼合组（机头+后片、袋贴+
//     前片）按整版全局坐标对齐同行摆放，逐点等距变换铺地面，与 2D
//     裁片 SVG 一比一，定位形状问题出在哪层；
//   · buildFullPair（八期整裤缝合，2026-09-17）：前后身并集宿主合并
//     四 part 悬挂摆位（+ seams/drape 单 sim 解算；六期双筒 buildHangPair
//     随整裤合并退役）。
// 坐标系 = 纸样系（y=纸样高、hem≈0 落地）；显示层 Group 平移到人台
// 旁侧（Fitting3DView），本层不感知人台。
import type { FittingPiece, FittingResult } from '../../types'
import type { ClothMesh, EdgeRun } from './mesh'
import { buildClothMesh, mergeRuns } from './mesh'
import { CORE_SKIN, type LegAxis } from './core'
import { pointInRings } from './placement'
import { bandTargets, ringWalk } from './band'
import type { BodyField, PieceKey, Side } from './placement'
import {
  buildWaistRing, placePoint, ringPointAt, type WaistRing,
} from './placement'
import { FLAT_PRIOR, HANG_PRIOR, MESH_PRIOR } from './priors'

export interface GarmentPart {
  key: string             // payload 片 key（front_piece/back_piece/...）
  side: Side
  mesh: ClothMesh
  offset: number          // 粒子全局号 = offset + 网格顶点号
}

export interface Garment {
  parts: GarmentPart[]    // 平铺：payload 逐片展开（成对片 L+R 两 part）
  pos: Float32Array       // 3N 初始位置（静态展示即终态）
  total: number
}

// 单片裁片（成对与否除外）——腰头整根/幅样无左右之分，单片原样
const SINGLE_PIECES = new Set(['waistband'])

// ---- 平面缝合拼合组（2026-09-15 晚八起逐步扩）：组内成员按整版全局
// 坐标对齐 = 缝后位置，共享组 bbox 归一变换即天然贴合；**贴合守卫**——
// 缝合依据线实测重合（<STITCH_GAP）才拼合，不贴合（净样形状差异）退
// 化各自独立行，不错位硬拼。成对时整组关于组中线镜像（真裁剪 L/R
// 两片）。业务装配链：腰头 ↔ 育克 ↔ 后片 / 袋贴 ↔ 前片（腰头拼合
// 留给后续重建步骤）。
const STITCH_GAP = 0.5   // cm：缝合依据线贴合判定阈值

type Pt = [number, number]

const edgePts = (p: FittingPiece, name: string): Pt[] =>
  p.edges.filter((e) => e.name === name).flatMap((e) => e.pts)

// 双向最近点距 max（cm）：两链逐点互查——端点超出对方链段的点如实计距
function seamGap(a: Pt[], b: Pt[]): number {
  const one = (from: Pt[], to: Pt[]): number => {
    let worst = 0
    for (const p of from) {
      let dMin = Infinity
      for (const q of to) dMin = Math.min(dMin, Math.hypot(p[0] - q[0], p[1] - q[1]))
      worst = Math.max(worst, dMin)
    }
    return worst
  }
  return Math.max(one(a, b), one(b, a))
}

interface StitchGroupDef {
  members: string[]       // 组内片序（首片 = 行锚；如 back 在下、yoke 在上）
  // 贴合守卫：缝合依据线（payload 边链/净线 marks）逐点重合才拼合
  aligned: (get: (k: string) => FittingPiece | undefined) => boolean
}

const STITCH_GROUPS: Record<string, StitchGroupDef> = {
  // 机头+后片（晚八用户口径「先将机头和后片缝合成为一个整体」）：
  // back 上边 top = yoke 下边 bottom（整版同一净线）——无省款逐点重合
  // （fixture 实测 max 0）；有省款 yoke 下边是省闭口净样、与整版下口
  // 线错位 ~12cm（真实缝前状态：后片省未收）→ 守卫拦下退独立行，处理留后
  back_piece: {
    members: ['back_piece', 'back_yoke'],
    aligned: (get) => {
      const back = get('back_piece'), yoke = get('back_yoke')
      return !!back && !!yoke && backYokeAligned(back, yoke)
    },
  },
  // 袋贴+前片（晚九用户口径「将前口袋也平铺出来，然后和前片缝合，
  // 形成一个整体」；2026-09-16 叠层方向口径「前片在前口袋上面」）：
  // 缝合依据 = facing 袋口净线（marks，任一条）↔ front mouth 边——
  // 直/弯腰头两款 fixture 实测 marks[0] 与 mouth 逐点重合 max 0；整版
  // 坐标即缝后位置（facing 外边 1:1 复制挖削前大片轮廓，自动补齐月牙
  // 缺口，袋口净线即缝合线）。净样有重叠区（袋口条带）→ 组内按片序
  // stackStep 叠层防共面 z-fight；**片序 facing 在前 = 前片叠在上层**
  // ——外观视角前片是主体盖住袋贴条带（真裤袋贴衬在里侧，2026-09-16
  // 用户口径：前片在前口袋上面）
  front_piece: {
    members: ['front_facing', 'front_piece'],
    aligned: (get) => {
      const front = get('front_piece'), facing = get('front_facing')
      return !!front && !!facing && frontFacingAligned(front, facing)
    },
  },
}

// 袋贴↔前片贴合守卫（平铺拼合组与 panel.ts 前身并集合成共用同一口径）：
// facing 袋口净线（marks，任一条）与前片 mouth 边逐点重合 < STITCH_GAP
// ——直/弯腰头两款 fixture 实测 marks[0] 与 mouth 逐点重合 max 0
export function frontFacingAligned(
  front: FittingPiece, facing: FittingPiece,
): boolean {
  const mouth = edgePts(front, 'mouth')
  return mouth.length > 0
    && facing.marks.some((mk) => seamGap(mk.pts, mouth) < STITCH_GAP)
}

// 机头↔后片贴合守卫（平铺拼合组与 panel.ts 后身并集合成共用同一口径）：
// back 上边 top（机头下口线）与 yoke 下边 bottom（整版同一净线）逐点
// 重合 < STITCH_GAP——无省款 fixture 实测逐点重合 max 0；有省款 yoke
// 下边是省闭口净样、与整版下口线错位 ~12cm（真实缝前状态：后片省未收）
// → 守卫拦下
export function backYokeAligned(
  back: FittingPiece, yoke: FittingPiece,
): boolean {
  const top = edgePts(back, 'top')
  return top.length > 0
    && seamGap(top, edgePts(yoke, 'bottom')) < STITCH_GAP
}

// 全裁片平铺装配（三期回落，2026-09-15 用户口径「把所有裁片都平铺
// 出来，颜色区分下」）：payload 逐片一行摆在地面上（缝合拼合组共用
// 一行），行序 = payload 片序（前片最近 → 腰头最远），行距
// FLAT_PRIOR.rowGap；成对裁片（front/back+yoke/facing 及后续加片）
// L 原样 + R 镜像并排留 FLAT_PRIOR.gap（真实排料观感：同一纸样画两次
// 一左一右），腰头单片。纸样 2D (x,y) 逐点等距变换到 (x−组xMin, 0,
// 行基 z + y−组yMin)——无弯折、无解算，网格即净样原形；拼合组内第 j
// 片 y = j×stackStep 叠层（袋贴条带与前片净样重叠，共面 z-fight）；
// 全组 z 居中（组中心 z=0，旁挂取景对称）。验证通道：此处形状
// 若与 2D 裁片 SVG 不符 → payload 边链/网格层问题（mesh.ts 上游）；
// 相符而悬挂不符 → 摆位/解算层问题。颜色区分在 render 层
// （PIECE_COLORS 按片 key 取色）。
export function buildFlatLayout(
  payload: FittingResult, exclude?: ReadonlySet<string>,
): Garment {
  // 行构建：payload 片序遍历，拼合组首片建行、其余片并入（consumed
  // 防重复建行；守卫不贴合或成员缺片自动退化为单片行）。exclude =
  // 离开平铺的片（2026-09-16 四期：前身组立起旁挂后不再平铺）——
  // 排除锚片且守卫通过时**整组**离开（缝合整体要么全平铺要么全立起）；
  // 守卫不通过则组员照旧独立行平铺（panel 退化兜底：袋贴留平铺验证）
  const byKey = new Map(payload.pieces.map((p) => [p.key, p]))
  const consumed = new Set<string>()
  const rows: { meshes: { key: string; mesh: ClothMesh }[] }[] = []
  for (const piece of payload.pieces) {
    if (consumed.has(piece.key)) continue
    const def = STITCH_GROUPS[piece.key]
    const aligned = !!def?.aligned((k) => byKey.get(k))
      && def!.members.every((k) => byKey.has(k))
    if (exclude?.has(piece.key)) {
      if (aligned) for (const k of def!.members) consumed.add(k)
      continue
    }
    const group = aligned ? def!.members : [piece.key]
    for (const k of group) {
      if (k !== piece.key) consumed.add(k)
    }
    rows.push({
      meshes: group.map((k) => ({ key: k, mesh: buildClothMesh(byKey.get(k)!) })),
    })
  }
  // 行盒：组内跨片并集 bbox（共享变换 = 拼合对齐），由网格顶点实算
  const boxes = rows.map((row) => {
    let xMin = Infinity, xMax = -Infinity
    let yMin = Infinity, yMax = -Infinity
    for (const { mesh } of row.meshes) {
      for (let i = 0; i < mesh.xy.length; i += 2) {
        xMin = Math.min(xMin, mesh.xy[i])
        xMax = Math.max(xMax, mesh.xy[i])
        yMin = Math.min(yMin, mesh.xy[i + 1])
        yMax = Math.max(yMax, mesh.xy[i + 1])
      }
    }
    const single = row.meshes.length === 1
      && SINGLE_PIECES.has(row.meshes[0].key)
    const perSide = row.meshes.reduce((s, m) => s + m.mesh.xy.length / 2, 0)
    return {
      row, xMin, yMin, single, perSide,
      w: xMax - xMin, h: yMax - yMin,
    }
  })
  const depth = boxes.reduce((s, b) => s + b.h, 0)
    + (boxes.length - 1) * FLAT_PRIOR.rowGap
  const parts: GarmentPart[] = []
  const pos = new Float32Array(3 * boxes.reduce(
    (s, b) => s + b.perSide * (b.single ? 1 : 2), 0))
  let z = -depth / 2
  let off = 0
  for (const b of boxes) {
    const sides: Side[] = b.single ? ['L'] : ['L', 'R']
    for (const side of sides) {
      let j = 0
      for (const { key, mesh } of b.row.meshes) {
        const n = mesh.xy.length / 2
        const y = j * FLAT_PRIOR.stackStep   // 组内叠层：重叠区防共面
        parts.push({ key, side, mesh, offset: off })
        for (let i = 0; i < n; i++) {
          const u = mesh.xy[2 * i] - b.xMin      // 组内归一 x ∈ [0, w]
          const v = mesh.xy[2 * i + 1] - b.yMin
          // L：u 原样；R：w−u 镜像后平移到 L 右侧（成对组前中边相对）
          const px = side === 'L' ? u : b.w + FLAT_PRIOR.gap + (b.w - u)
          pos[3 * off] = px
          pos[3 * off + 1] = y
          pos[3 * off + 2] = z + v
          off++
        }
        j++
      }
    }
    z += b.h + FLAT_PRIOR.rowGap
  }
  return { parts, pos, total: off }
}

// 链折线按 y 插值取 x（腿区逐高度参考）：从链首扫描首个跨 y 段线性插值，
// 范围外端点 clamp。side（腰口→脚口）/inseam（脚口→裆尖）链 y 近单调，
// 首个跨段即所求
function chainXAt(chain: EdgeRun, xy: Float64Array, y: number): number {
  const idx = chain.indices
  for (let k = 0; k < idx.length - 1; k++) {
    const y0 = xy[2 * idx[k] + 1], y1 = xy[2 * idx[k + 1] + 1]
    if ((y0 - y) * (y1 - y) <= 0 && Math.abs(y1 - y0) > 1e-12) {
      const t = (y - y0) / (y1 - y0)
      return xy[2 * idx[k]] + (xy[2 * idx[k + 1]] - xy[2 * idx[k]]) * t
    }
  }
  return y <= xy[2 * idx[0] + 1]
    ? xy[2 * idx[0]] : xy[2 * (idx[idx.length - 1])]
}

// 整裤四 part 悬挂摆位（2026-09-17 八期整裤缝合）：前宿主 ×2（fL/fR）+
// 后宿主 ×2（bL/bR）合并一张 Garment（offset 依次 0, nF, 2nF, 2nF+nB），
// 配 seams.ts buildSeamSet 四族缝合对 + drape 单 sim 解算。摆位五步
// （顺序执行、后者覆盖先）——「钉与缝同意」的整裤版，让全部缝合对初始
// 间隙 ≈0，动力学只做小松弛（摆位先行，不用旧链 preRelax 大 Gap 收拢）：
// 1) 片身基础映射：躯干段（fork + forkBlend 以上）照旧全局 x→θ
//    （placePoint，六期已验证）；腿段**腿局部圆环绕管**——逐高度局部
//    归一 t=(x−xi)/(xo−xi)（xi/xo = 该高度 inseam 链/side 合链 x，
//    chainXAt 折线插值），φ = t·π 从腿内侧（φ=0）经前/后（±z）到腿
//    外侧（φ=π），绕腿轴（±cAt(y)）铺半径 rAt(y)+skin+gap——内缝边
//    落腿内侧线、侧缝边落腿外侧线，hem 内外角自然归位；fork 向上
//    forkBlend 线性过渡（裆角布从躯干前面顺滑收进腿间）
// 2) 腰圆 360° 整圈弧长重参数化（六期 per-host 逻辑扩角度表）：fL
//    −f·90° / fR +f·90° / bL −180°+f·90° / bR 180°−f·90°（f = 腰口
//    弧长分数，0=中缝腰角、1=侧缝腰角）——侧腰角前后宿主共点 ±90°、
//    中缝腰角镜像共点 0°/180°，**腰圆初始已闭**（八期口径①「侧缝缝合
//    形成腰圆」的摆位侧前提）
// 3) 侧缝语义摆位竖直线（六期 θ=±90° 逻辑的腿局部版）：躯干行照旧
//    径向场 ±90°、腿行 = 腿外侧线（cAt+rAt+skin+gap），fork 带内线性
//    过渡——前/后宿主同线，side 缝对（seams 弧长族，首对锚腰口端）
//    初始间隙 ≈0
// 4) 内缝语义摆位 = 腿内侧线（cAt−rAt−skin−gap，钳 ≥0.3 不越中线）：
//    前后宿主**相邻共线**——内缝焊对初始间隙 ≈0（腿管两半在此合拢成
//    筒，八期口径②），L/R 腿内侧线隔腿间隙相望不交叉；四裆尖经 tip
//    补焊零 rest 闭环汇集裆交叉点=口径③（叉口在 fork 下方的腿间隙里）
// 5) hangLift 统一抬升（碰撞模式重定标：布撑芯上不下坠，hem≈纸样 y
//    +lift；drape collide 截面环查询按 yLift 回纸样空间，两处一致）
// 穿台分支（2026-09-19 形随体长随衣）：waistRing 在时腰口/顶链相关段
// 沿钉环弧长摆放（环 = 腰站截面边界放大至成衣腰长，见 placement.
// buildWaistRing），侧缝语义竖直线方向随侧腰角（扁截面下前移）；腿区/
// 躯干非腰口段照旧（有碰撞管终态）。缺省 waistRing = 旁挂 θ 角度表
// 原口径，字节等价
export function buildFullPair(
  front: ClothMesh, back: ClothMesh, field: BodyField,
  forkY: { front: number; back: number },
  axis: LegAxis,
  band?: ClothMesh | null,
  lift: number = HANG_PRIOR.hangLift,   // 统一抬升（旁挂缺省 hangLift 抬离
                                        // 地面；穿台传人台腰地标锚 anchorLift
                                        // ——钉初始即钉在腰地标高度，2026-09-18）
  waistRing?: WaistRing,                // 穿台腰圈钉环（形随体长随衣）；缺省
                                        // 旁挂原口径（保回归零改动）
): Garment {
  const nF = front.xy.length / 2
  const nB = back.xy.length / 2
  const parts: GarmentPart[] = [
    { key: 'front', side: 'L', mesh: front, offset: 0 },
    { key: 'front', side: 'R', mesh: front, offset: nF },
    { key: 'back', side: 'L', mesh: back, offset: 2 * nF },
    { key: 'back', side: 'R', mesh: back, offset: 2 * nF + nB },
  ]
  // 腰环行走（四段腰口弧 → 有序顶点链）：腰头配对（九期）与穿台腰圈
  // 摆位（2026-09-19）共用；坏链时腰头降级无腰头（主展示不炸）、穿台
  // 腰圈硬依赖（waistRing 在而行走失败 = 腰口无法摆位，直接抛）
  const walk = (() => {
    try { return ringWalk(parts) } catch (e) {
      console.warn('[assemble] 腰环行走失败（腰头降级/腰圈不可用）:', e)
      return null
    }
  })()
  const bandPlan = (() => {
    if (!band || !walk) return null
    try {
      const targets = bandTargets(band, walk)
      if (!targets) return null
      return { walk, targets }
    } catch (e) {
      console.warn('[assemble] 腰头摆放降级（无腰头）:', e)
      return null
    }
  })()
  if (waistRing && !walk) {
    throw new Error('穿台腰圈摆位缺 top_chain 边（腰环行走失败）')
  }
  // 穿台腰圈映射：fabric 弧（ringWalk 纸样弧）→ 环弧换算 kScale，与左右
  // 侧缝腰角弧位（fL/bR 段末；角点本体 = 顶链末再走一个边界步——边界
  // 重采样角点共享规则，角点不在 top run 采样内）
  const ringMap = !waistRing || !walk ? null : (() => {
    const kScale = waistRing.total / walk.total
    let arcL = 0, arcR = 0
    for (let k = 0; k < walk.verts.length; k++) {
      const v = walk.verts[k]
      const nxt = walk.verts[k + 1]
      if (nxt === undefined || nxt.part !== v.part) {
        if (v.part === 0) arcL = v.arc        // fL 段末 = 左侧缝腰角
        else if (v.part === 3) arcR = v.arc   // bR 段末 = 右侧缝腰角
      }
    }
    return {
      kScale,
      cornerArcL: arcL + MESH_PRIOR.boundaryStep,
      cornerArcR: arcR + MESH_PRIOR.boundaryStep,
    }
  })()
  const nBand = bandPlan ? band!.xy.length / 2 : 0
  const pos = new Float32Array(3 * (2 * nF + 2 * nB + nBand))
  // ---- 1) 片身基础映射（躯干全局 x→θ / 腿区腿局部圆环绕管）----
  for (const part of parts) {
    const mesh = part.mesh
    let xMin = Infinity, xMax = -Infinity
    for (let i = 0; i < mesh.xy.length; i += 2) {
      xMin = Math.min(xMin, mesh.xy[i])
      xMax = Math.max(xMax, mesh.xy[i])
    }
    const inner = mesh.runs.find((r) => r.name === 'inseam') ?? null
    const outer = mergeRuns(mesh.runs.filter((r) => r.name === 'side'), mesh.xy)
    const fork = part.key === 'back' ? forkY.back : forkY.front
    // 腿区权重：fork 以下 1、fork+forkBlend 以上 0，带内线性过渡
    const legW = (y: number): number => {
      if (!HANG_PRIOR.legReparam) return 0
      const blend = HANG_PRIOR.forkBlend
      if (blend <= 0) return y < fork ? 1 : 0
      return Math.max(0, Math.min(1, (fork + blend - y) / blend))
    }
    const canLeg = !!inner && !!outer
    for (let i = 0; i < mesh.xy.length / 2; i++) {
      const x = mesh.xy[2 * i], y = mesh.xy[2 * i + 1]
      // 腿局部圆环：φ 从腿内侧（0）经前/后到腿外侧（π）
      const legPos = (): [number, number, number] => {
        const sgn = part.side === 'R' ? 1 : -1
        const r = axis.rAt(y) + CORE_SKIN + HANG_PRIOR.garmentGap
        const cx = sgn * axis.cAt(y)
        const xi = chainXAt(inner!, mesh.xy, y)
        const xo = chainXAt(outer!, mesh.xy, y)
        const t = Math.max(0, Math.min(1, (x - xi) / ((xo - xi) || 1)))
        const phi = t * Math.PI
        const ux = -sgn * Math.cos(phi)
        const uz = (part.key === 'back' ? -1 : 1) * Math.sin(phi)
        let px = cx + r * ux
        if (px * sgn < 0.3) px = sgn * 0.3   // 内侧线不越中线（裆汇集处）
        return [px, y, r * uz]
      }
      const w = canLeg ? legW(y) : 0
      const i3 = 3 * (part.offset + i)
      if (w >= 1) {
        const [px, py, pz] = legPos()
        pos[i3] = px; pos[i3 + 1] = py; pos[i3 + 2] = pz
      } else {
        const [px, py, pz] = placePoint(
          part.key as PieceKey, part.side, x, y, xMin, xMax, field)
        if (w > 0) {
          const [lx, , lz] = legPos()
          let mx = px + (lx - px) * w
          let mz = pz + (lz - pz) * w
          // 混合弦线可能穿芯（躯干径向位与腿局部位连线过实心）：落环内
          // 回退径向摆位（径向场+gap 按构造在全体外）——保证初摆位零穿透
          if (pointInRings(mx, mz, field.loopsAt(y))) {
            mx = px; mz = pz
          }
          pos[i3] = mx; pos[i3 + 1] = py; pos[i3 + 2] = mz
        } else {
          pos[i3] = px; pos[i3 + 1] = py; pos[i3 + 2] = pz
        }
      }
    }
  }
  // ---- 2) 腰圆 360° 整圈弧长重参数化（per part；order[0]=中缝腰角）----
  if (ringMap && waistRing && walk) {
    // 穿台（2026-09-19 形随体长随衣）：顶链沿钉环弧长摆放——fabric 弧
    // （ringWalk 纸样弧）× kScale 映到环弧：环长 = 成衣腰长，直款顶链
    // 总弧 ≈ 带底净长 → 钉间距 = 纸样边长（零应变，腰头真实尺寸守恒的
    // 摆位侧前提）；弯款身片省口富余按比例压缩 = bandWaist 吃势软褶。
    // 中缝/侧缝腰角由弧长自然落位（扁截面下侧缝腰角前移是布量分布的
    // 真实几何，不再钉死 0°/±90°）
    for (const v of walk.verts) {
      const p = ringPointAt(waistRing, v.arc * ringMap.kScale)
      const part = parts[v.part]
      const i3 = 3 * (part.offset + v.idx)
      pos[i3] = p.x
      pos[i3 + 1] = part.mesh.xy[2 * v.idx + 1]
      pos[i3 + 2] = p.z
    }
  } else {
    for (const part of parts) {
      const mesh = part.mesh
      const top = mesh.runs.find((r) => r.role === 'top_chain')
      const seamRun = mesh.runs.find(
        (r) => r.name === 'rise' || r.name === 'cb')
      if (!top || top.indices.length <= 1) continue
      const seamTop = seamRun
        ? seamRun.indices[seamRun.indices.length - 1] : null
      const order = seamTop !== null
        && seamTop === top.indices[top.indices.length - 1]
        ? [...top.indices].reverse() : [...top.indices]
      const arc: number[] = [0]
      for (let k = 1; k < order.length; k++) {
        const a = order[k - 1], b = order[k]
        arc.push(arc[k - 1] + Math.hypot(
          mesh.xy[2 * b] - mesh.xy[2 * a], mesh.xy[2 * b + 1] - mesh.xy[2 * a + 1]))
      }
      const total = arc[order.length - 1] || 1
      for (let k = 0; k < order.length; k++) {
        const i = order[k]
        const f = arc[k] / total
        // f=0 中缝腰角落中面（front 0° / back −180°）、f=1 侧缝腰角落 ±90°
        const thL = part.key === 'back'
          ? -Math.PI + f * (Math.PI / 2)
          : -f * (Math.PI / 2)
        const th = part.side === 'R' ? -thL : thL
        const y = mesh.xy[2 * i + 1]
        const r = field.radiusAt(y, th) + HANG_PRIOR.garmentGap
        const i3 = 3 * (part.offset + i)
        pos[i3] = r * Math.sin(th)
        pos[i3 + 1] = y
        pos[i3 + 2] = r * Math.cos(th)
      }
    }
  }
  // ---- 3) 侧缝语义摆位竖直线（六期 θ=±90° 的腿局部版）：躯干行照旧
  // 径向场 ±90°、腿行 = 腿外侧线（cAt+rAt+skin+gap），fork 过渡带内线性
  // 混合（带内两口径在 fork 处差 ~0.8cm，硬切会留台阶）。'side' 全 run
  // 覆盖（后宿主育克侧段与后片侧缝各自成 run，同一顶点集）。穿台分支
  // （2026-09-19）：竖直线方向 = 钉环侧缝腰角方向（与腰圈连续，扁截面
  // 下前移；±90° 硬切会在角点与下一行间留 ~4cm 台阶）----
  // 穿台侧缝腰角方向（旁挂缺省 null = ±90° 原口径）
  const cornerDir = !ringMap || !waistRing ? null : (() => {
    const pL = ringPointAt(waistRing, ringMap.cornerArcL * ringMap.kScale)
    const pR = ringPointAt(waistRing, ringMap.cornerArcR * ringMap.kScale)
    return { L: Math.atan2(pL.x, pL.z), R: Math.atan2(pR.x, pR.z) }
  })()
  for (const part of parts) {
    const fork = part.key === 'back' ? forkY.back : forkY.front
    const legW = (y: number): number => {
      const blend = HANG_PRIOR.forkBlend
      if (blend <= 0) return y < fork ? 1 : 0
      return Math.max(0, Math.min(1, (fork + blend - y) / blend))
    }
    for (const run of part.mesh.runs) {
      if (run.name !== 'side') continue
      for (const i of run.indices) {
        const y = part.mesh.xy[2 * i + 1]
        const sgn = part.side === 'L' ? -1 : 1
        const th = cornerDir
          ? cornerDir[part.side]
          : (part.side === 'L' ? -Math.PI / 2 : Math.PI / 2)
        const radial = field.radiusAt(y, th) + HANG_PRIOR.garmentGap
        const lateral = axis.cAt(y) + axis.rAt(y)
          + CORE_SKIN + HANG_PRIOR.garmentGap
        const r = radial + (lateral - radial) * legW(y)
        const i3 = 3 * (part.offset + i)
        if (cornerDir) {
          // 向量式（θ 非特殊角）：躯干行沿角方向、腿行混合到腿外侧线
          const rx = r * Math.sin(th), rz = r * Math.cos(th)
          const w = legW(y)
          pos[i3] = rx + (sgn * lateral - rx) * w
          pos[i3 + 1] = y
          pos[i3 + 2] = rz * (1 - w)
        } else {
          pos[i3] = sgn * r
          pos[i3 + 1] = y
          pos[i3 + 2] = 0
        }
      }
    }
  }
  // 侧缝腰角前后共点 snap（八期）：前后腰口线在纸样上是曲线、侧腰角 y
  // 有起翘差（fixture 实测 front 97.7 / back 98.1，~0.4cm；退化款差更大），
  // 各自摆位后两角不重合——它们在钉集（sideHold 带首点）又是 side 缝对
  // 首对，不 snap 则钉与缝永久拔河。**角点本体 = side 合链首采样**（边
  // 界重采样共享角点规则；top run 末端只是角点前一步，写它没用）。前后
  // 两角统一摆到平均 y（旁挂 θ=±90°、r = 场(平均 y)+gap；穿台 = 钉环
  // 侧腰角弧位点）——「钉与缝同意」的腰圆闭合收尾
  for (const [iF, iB] of [[0, 2], [1, 3]] as const) {
    const cornerOf = (p: GarmentPart): { v: number; y: number } => {
      const chain = mergeRuns(
        p.mesh.runs.filter((r) => r.name === 'side'), p.mesh.xy)!
      const v = chain.indices[0]
      return { v, y: p.mesh.xy[2 * v + 1] }
    }
    const fC = cornerOf(parts[iF]), bC = cornerOf(parts[iB])
    const cp = !ringMap || !waistRing ? null : ringPointAt(
      waistRing,
      (parts[iF].side === 'L' ? ringMap.cornerArcL : ringMap.cornerArcR)
        * ringMap.kScale)
    const th = cp !== null
      ? Math.atan2(cp.x, cp.z)
      : (parts[iF].side === 'L' ? -Math.PI / 2 : Math.PI / 2)
    const yAvg = (fC.y + bC.y) / 2
    const r = cp !== null
      ? Math.hypot(cp.x, cp.z)
      : field.radiusAt(yAvg, th) + HANG_PRIOR.garmentGap
    for (const [p, c] of [[parts[iF], fC], [parts[iB], bC]] as const) {
      const i3 = 3 * (p.offset + c.v)
      if (cp !== null) {
        pos[i3] = cp.x
        pos[i3 + 1] = yAvg
        pos[i3 + 2] = cp.z
      } else {
        pos[i3] = r * Math.sin(th)
        pos[i3 + 1] = yAvg
        pos[i3 + 2] = r * Math.cos(th)
      }
    }
    // 高差渐变（（十）腰头侧缝不平整）：角点两侧 waistBlendSpan 弧内的
    // 顶链顶点 y 向 snap 高度渐变——只平均角点会在缝口两侧留台阶，腰头
    // 底边跟出折点。order[last] = 侧缝腰角端，弧距 = total − arc[k]。
    // 穿台分支：钉环是 2D 钉目标（与 y 无关），只渐变 y、x/z 保持环位
    for (const p of [parts[iF], parts[iB]]) {
      const top = p.mesh.runs.find((rr) => rr.role === 'top_chain')!
      const seam = p.mesh.runs.find((rr) => rr.name === 'rise' || rr.name === 'cb')
      const seamTop = seam ? seam.indices[seam.indices.length - 1] : null
      const order = seamTop !== null
        && seamTop === top.indices[top.indices.length - 1]
        ? [...top.indices].reverse() : [...top.indices]
      const arcs: number[] = [0]
      for (let k = 1; k < order.length; k++) {
        arcs.push(arcs[k - 1] + Math.hypot(
          p.mesh.xy[2 * order[k]] - p.mesh.xy[2 * order[k - 1]],
          p.mesh.xy[2 * order[k] + 1] - p.mesh.xy[2 * order[k - 1] + 1]))
      }
      const total = arcs[arcs.length - 1] || 1
      const span = HANG_PRIOR.waistBlendSpan
      for (let k = 0; k < order.length; k++) {
        const fromCorner = total - arcs[k]
        if (fromCorner > span) continue
        const w = 1 - fromCorner / (span || 1)
        const i3 = 3 * (p.offset + order[k])
        const yNew = pos[i3 + 1] * (1 - w) + yAvg * w
        if (cp !== null) {
          pos[i3 + 1] = yNew
        } else {
          // 半径随 y 同步重算（场半径沿高度变化——y 调低不更新 r 会陷进
          // 碰撞壳 ~0.07cm，钉与 collide 打架，有省款金标实测）
          const th = Math.atan2(pos[i3], pos[i3 + 2])
          const r = field.radiusAt(yNew, th) + HANG_PRIOR.garmentGap
          pos[i3] = r * Math.sin(th)
          pos[i3 + 1] = yNew
          pos[i3 + 2] = r * Math.cos(th)
        }
      }
    }
  }
  // ---- 4) 内缝语义摆位 = 腿内侧线（cAt−rAt−skin−gap，钳 ≥0.3 不越
  // 中线）：前后宿主相邻共线（同一公式），内缝焊对初始间隙 ≈0；L/R 腿
  // 内侧线隔腿间隙相望（近裆处收敛到 ±0.3——四裆尖 tip 补焊在此汇集）----
  for (const part of parts) {
    for (const run of part.mesh.runs) {
      if (run.name !== 'inseam') continue
      const fork = part.key === 'back' ? forkY.back : forkY.front
      const sgn = part.side === 'L' ? -1 : 1
      for (const i of run.indices) {
        const y = part.mesh.xy[2 * i + 1]
        // 叉口以上的内缝顶段 = 裆布区：穿台体叉口可低于纸样裆深（体叉 70
        // vs 纸样裆 78），钳位内侧线（x=±0.3）会插进骨盆环——这些行归
        // step1 躯干/混合摆位（含穿芯回退）。旁挂纸样叉 = 内缝链顶，
        // 严格 > 不触发（回归零改动，2026-09-18 穿台实测 7 行/腿 最深
        // 6.7cm）
        if (y > fork) continue
        const medial = Math.max(
          axis.cAt(y) - (axis.rAt(y) + CORE_SKIN + HANG_PRIOR.garmentGap), 0.3)
        const i3 = 3 * (part.offset + i)
        pos[i3] = sgn * medial
        pos[i3 + 1] = y
        pos[i3 + 2] = 0
      }
    }
  }
  // ---- 4.5) 腰头摆放（九期腰头立体化，用户口径「腰头两边是前中线、
  // 腰头中点是后中线」）：bandTargets 对每个带顶点给 (环顶点, 带法向
  // 距离 v)——底边顶点摆到**配对环顶点原位**（bandWaist 焊对初始间隙
  // 0，摆位先行），列沿竖直向上 v；u 沿带弧的环映射 = 端 u=0/1 落前中
  // （环 s=0/P）、中点 u=0.5 落后中（s=P/2，左右半弧镜像相等）----
  if (bandPlan) {
    const { walk, targets } = bandPlan
    parts.push({ key: 'waistband', side: 'L', mesh: band!,
      offset: 2 * nF + 2 * nB })
    // 穿台带顶环（2026-09-19）：腰上方身体围收窄但前腹外凸（base.bin 实测
    // y=98→102.5：周长 69.05→67.11、前 z 14.72→15.55）——带顶边沿用腰站环
    // x,z 会前腹嵌体 0.3~0.6（钉 XZ 冻结救不回）。顶环 = 「环源行+带宽」行
    // 截面同口径缩放（该行形随体长随衣：上方收窄 → 真实带顶微悬空 ~0.5；
    // 隆起体则负 gap 顶紧）。带列 XZ 随 v 从底环位渐变到顶环位；顶环构建
    // 失败退化竖直列（旁挂路径不触发）
    let topRing: WaistRing | null = null
    let vMax = 0
    if (ringMap && waistRing) {
      for (const t of targets) vMax = Math.max(vMax, t.v)
      if (vMax > 0.01) {
        try {
          topRing = buildWaistRing(field, waistRing.y + vMax, waistRing.total)
        } catch {
          topRing = null
        }
      }
    }
    for (let i = 0; i < targets.length; i++) {
      const r = walk.verts[targets[i].ringK]
      const gi = 3 * (parts[r.part].offset + r.idx)
      const bi = 3 * (parts[4].offset + i)
      const f = topRing !== null ? targets[i].v / vMax : 0
      if (topRing !== null && f > 0) {
        // 配对底边环顶点的环弧（纸样弧 × kScale）等比例映到顶环
        const sB = r.arc * ringMap!.kScale
        const tp = ringPointAt(
          topRing, sB * (topRing.total / waistRing!.total))
        pos[bi] = pos[gi] + (tp.x - pos[gi]) * f
        pos[bi + 1] = pos[gi + 1] + targets[i].v
        pos[bi + 2] = pos[gi + 2] + (tp.z - pos[gi + 2]) * f
      } else {
        pos[bi] = pos[gi]
        pos[bi + 1] = pos[gi + 1] + targets[i].v
        pos[bi + 2] = pos[gi + 2]
      }
    }
  }
  // ---- 5) 统一抬升 lift（最后施加，含全部钉目标；上方场查询均用
  // 纸样 y，drape collide 按 yLift 回减保持一致。旁挂 = hangLift 抬离
  // 地面；穿台 = anchorLift 腰地标锚——落位下放由 settle 控制器接管）----
  for (let i = 1; i < pos.length; i += 3) pos[i] += lift
  return { parts, pos, total: 2 * nF + 2 * nB + nBand }
}
