// 静态装配（3D 展示重建，2026-09-15）：整裤缝合解算链已删，只装配
// 裁片平铺。payload schema v1 照旧发全片（引擎零改动）。两种摆位：
//   · buildFlatLayout（三期回落 → 2026-09-16 四期起 = 非前身裁片的平铺
//     验证通道：前身组经 panel.ts 并集合成后走悬挂链立起旁挂，exclude
//     参数把前身组移出平铺；其余片照旧）——payload 每片一行（成对片
//     L 原样 + R 镜像并排、腰头单片），缝合拼合组（机头+后片、袋贴+
//     前片）按整版全局坐标对齐同行摆放，逐点等距变换铺地面，与 2D
//     裁片 SVG 一比一，定位形状问题出在哪层；
//   · buildHangPair（扇区摆位，四期起随前身缝合立起回归接线；前身/
//     后身悬挂链共用）——撑型芯场前/后 90° 扇区悬挂（+ drape）。
// 坐标系 = 纸样系（y=纸样高、hem≈0 落地）；显示层 Group 平移到人台
// 旁侧（Fitting3DView），本层不感知人台。
import type { FittingPiece, FittingResult } from '../../types'
import type { ClothMesh } from './mesh'
import { buildClothMesh } from './mesh'
import type { BodyField, PieceKey, Side } from './placement'
import { placePoint } from './placement'
import { FLAT_PRIOR, HANG_PRIOR } from './priors'

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

// 悬挂一对静态装配（扇区摆位；前身/后身悬挂链共用——一期前片口径
// 2026-09-16 后身缝合起泛化）：同一宿主网格 × {L, R}，逐顶点摆位到
// 撑型芯场扇区（front 前扇区 [−90°,0°] / back 后扇区 [−180°,−90°]）
export function buildHangPair(
  key: PieceKey, mesh: ClothMesh, field: BodyField,
): Garment {
  const n = mesh.xy.length / 2
  let xMin = Infinity, xMax = -Infinity
  for (let i = 0; i < mesh.xy.length; i += 2) {
    xMin = Math.min(xMin, mesh.xy[i])
    xMax = Math.max(xMax, mesh.xy[i])
  }
  const parts: GarmentPart[] = [
    { key, side: 'L', mesh, offset: 0 },
    { key, side: 'R', mesh, offset: n },
  ]
  const pos = new Float32Array(3 * 2 * n)
  for (const part of parts) {
    for (let i = 0; i < n; i++) {
      const [px, py, pz] = placePoint(
        key, part.side, mesh.xy[2 * i], mesh.xy[2 * i + 1],
        xMin, xMax, field)
      pos[3 * (part.offset + i)] = px
      pos[3 * (part.offset + i) + 1] = py
      pos[3 * (part.offset + i) + 2] = pz
    }
  }
  // 腰口弧长重参数化（2026-09-16 六期「拉直」）：均匀 x→θ 映射固有
  // 偏心——腰口两端点不落扇区边界（中缝腰角实测偏心 ~3.9cm ≈ 17°），
  // 整圈全向钉悬挂（drape）下顶缘会留顶中缺口/鞍。顶链顶点改按**腰口
  // 弧长分数** s∈[0,1]（s=0 = 中缝腰角端）均匀铺满扇区：中缝腰角精确
  // 落 0°/−180°、侧缝腰角精确落 ±90°；y/半径口径不变（y = 纸样高、
  // r = 场(y,θ)+gap），R 侧照旧 θ→−θ 镜像（保双侧镜像对称金标）。
  // 片身其余顶点照旧 x 映射（初摆位近似，解算自松弛）
  const top = mesh.runs.find((r) => r.role === 'top_chain')
  const seamRun = mesh.runs.find(
    (r) => r.name === 'rise' || r.name === 'cb')
  if (top && top.indices.length > 1) {
    // run 方向对齐：order[0] = 中缝腰角（中缝链腰口端顶点；无中缝款
    // 〔fly 连裁〕回退链首）
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
      // f=0 中缝腰角 → 扇区中心端（front 0° / back −180°）、f=1 → 侧缝 −90°
      const thL = key === 'back'
        ? -Math.PI + f * (Math.PI / 2)
        : -f * (Math.PI / 2)
      const y = mesh.xy[2 * i + 1]
      for (const part of parts) {
        const th = part.side === 'R' ? -thL : thL
        const r = field.radiusAt(y, th) + HANG_PRIOR.garmentGap
        pos[3 * (part.offset + i)] = r * Math.sin(th)
        pos[3 * (part.offset + i) + 1] = y
        pos[3 * (part.offset + i) + 2] = r * Math.cos(th)
      }
    }
  }
  return { parts, pos, total: 2 * n }
}
