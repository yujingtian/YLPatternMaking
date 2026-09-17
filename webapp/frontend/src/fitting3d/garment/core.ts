// 纸样围度撑型芯（2026-09-14 用户定方向：裤子展示与人台彻底解耦，
// 「内部是空的也要呈圆筒、不能叠」）：芯体不渲染——显示上裤子内部
// 仍是空的、悬挂在人台旁侧。围度逐站取 payload stations 的
// girth_finished（纸样成衣量），芯半径 = g/2π − CORE_SKIN，摆位半径
// （芯面 + skin + garmentGap）落在纸样围度附近 → 圆筒按构造成立，
// 廓形 = 版型。坐标系 = 纸样系（y=纸样高、hem≈0 落地）。
//
// 形状（v3，2026-09-17 八期整裤缝合：**三实体**——躯干管 + 左右分离
// 腿管，一个 positions/indices 数组拼装，各实体独立水密）：
//   · 腿管 ×2：hem−1.5 → fork+LEG_OVERLAP，圆环，半径 = 腿剖面（裆→
//     thigh→膝→hem），轴 |x| = r(y)+gapHalf(y)，gapHalf 从 fork 处
//     LEG_GAP_MIN 线性张开到 LEG_GAP_TAPER 以下 LEG_GAP_HALF（fork 以上
//     钳 LEG_GAP_MIN）——**裆下两腿真分离**，腿间空隙给内缝焊线与裆
//     交叉点安身（真裤两腿间有缝空隙，内缝线悬在其中）
//   · 躯干管：fork+TORSO_BOTTOM(2) → 腰+8；底部 CROTCH_FILLET(8) 带 =
//     **裆圆角**（截面 z 向压缩成椭圆、x 保持全宽，zScale 从底行
//     CROTCH_ZMIN(0.28) smoothstep 到全圆）——真身形骨盆底耻骨/会阴区
//     前后收拢、左右髋仍宽；无圆角的平底圆柱会把前中布撑到全半径壁再
//     收回裆点 = 裆上生硬尖帐篷（八期当日用户报障「裆部前后片生硬
//     凸起」，前中缝终态 z 3→16→12 实测）。fork..fork+2 带（裆交叉
//     口袋）只有腿管截面，躯干环不出现（否则裆尖摆位困进管内）
//   · 芯只经 buildBodyField 消费（场表 + 行截面环），多环行取方向支撑
//     最大；碰撞用行截面多边形（drape collide）——径向场是星形实心，
//     腿间空隙表示不了
//
// v2 花生环（裆下双瓣+腰谷单一水密环）2026-09-17 证伪退役：径向碰撞场
// 下花生腰谷仍是实心桥（槽底半径 ≥ 槽深），前内缝边(+z 谷)与后内缝边
// (−z 谷)隔桥相望焊不上、只能绕腿瓣外侧闭拢——实测整条裤腿被拖成侧挂
// 门帘（inseam 终态 θ≈±90°、r≈腿瓣外）。留档：花生的「内缝闭合在瓣
// 内侧」设想只在不碰撞或表面碰撞下成立。
//
// v1 三件套（圆筒+双管+龙骨）的实测死路（勿回头）：
//   · 管间留槽（d=max r 常数）——内缝缝合走捷径穿槽（不可拉伸布穿槽比
//     绕管省 10cm+），整幅布堆进两腿之间、外侧裸管 =「侧缝内凹/叠腿」
//     机制本体（八期对策：侧缝语义摆位 + sideHold 钉，侧缝钉死在腿外
//     侧线，布无从抄近道）；
//   · 双管相切 —— 切线刀口两侧壳交替投影 = 裆部抖动泵（八期对策：
//     fork 处保 GAP_MIN 真间隙 + 截面碰撞按环独立判内，无交替投影）；
//   · 双管交叠 —— 符号判陷阱：粒子「在 L 管外」即「在 R 管内」（八期
//     对策：腿管不交叠，截面碰撞只看所在环）；
//   · 细龙骨（r2.5）—— preRelax 拉链直接穿膛（碰撞间隔内一步可走
//     ~10cm）。
import type { FittingResult, FittingStation } from '../../types'

export interface CoreMesh {
  positions: Float32Array   // cm，纸样系 Y-up（x 侧向、z 前向、y 纸样高）
  indices: Uint32Array      // 三角（0-based）
}

const SEG = 64               // 环向分段
const ROW = 2                // 纵向行距 cm
const TOP_MARGIN = 8         // 腰上延伸（band 上沿 + 余量）
const BOTTOM_MARGIN = 1.5    // 脚口下延伸（hem 行粒子防端面边界抖动）
export const LEG_GAP_MIN = 0.8   // cm：fork 处腿轴间隙半宽（防双管相切刀口）
export const LEG_GAP_HALF = 2.6  // cm：腿间完全张开后的间隙半宽（总 5.2）
export const LEG_GAP_TAPER = 12  // cm：间隙从 fork 向下张开的锥高
export const CROTCH_FILLET = 6   // cm：躯干管底裆圆角带高（z 向压缩过渡；
                                 // 到臀站为止——臀环恢复全圆，场等值口径不变）
export const CROTCH_ZMIN = 0.28  // 圆角带底行的 z 半径比例（耻骨区高度）
export const TORSO_BOTTOM = 2    // cm：躯干管底 = fork + 本值——fork 带
                                 // （裆交叉口袋）只有上延腿管，躯干环不出
                                 // 现在 fork 行（会把裆尖摆位困进管内）；
                                 // 腿管上延 LEG_OVERLAP 兼供圆角带下段的
                                 // 大腿支撑与场表连续
const LEG_OVERLAP = 4            // cm：腿管上延过 fork 的高度

// 皮肤壳厚度（cm）：解算时代 collisionSkin=0.98 的标定值原样沿用为
// 芯体口径常数——芯半径 = g/2π − skin，摆位壳 core+skin+gap 落纸样围度
export const CORE_SKIN = 0.98

// 纸样围度 -> 芯半径：布接触壳在 core+skin，落点围度恰 = girth_finished
const coreRadius = (g: number): number =>
  g / (2 * Math.PI) - CORE_SKIN

type Profile = [number, number][]   // [y, r] 按 y 升序

function radiusAt(profile: Profile, y: number): number {
  if (y <= profile[0][0]) return profile[0][1]
  for (let i = 1; i < profile.length; i++) {
    if (y <= profile[i][0]) {
      const [y0, r0] = profile[i - 1], [y1, r1] = profile[i]
      return y1 - y0 > 1e-9 ? r0 + ((r1 - r0) * (y - y0)) / (y1 - y0) : r1
    }
  }
  return profile[profile.length - 1][1]
}

function circleRing(r: number): { xs: number[]; zs: number[] } {
  const xs: number[] = [], zs: number[] = []
  for (let s = 0; s < SEG; s++) {
    const th = (s / SEG) * 2 * Math.PI
    xs.push(r * Math.sin(th)); zs.push(r * Math.cos(th))
  }
  return { xs, zs }
}

// 站点便捷取值（thigh 缺省回退 hip——thigh 录入可选）
function stationOf(payload: FittingResult, key: FittingStation['key']):
  FittingStation | undefined {
  return payload.body.stations.find((s) => s.key === key)
}

// 腿轴几何（八期：buildFullPair 腿局部摆位与 drape 无关，只喂摆位侧）
export interface LegAxis {
  rAt(y: number): number    // 腿管芯半径（不含 skin）
  cAt(y: number): number    // 腿轴 |x| = r(y) + gapHalf(y)
  forkY: number             // 裆站 y（腿管顶 = 躯干管底）
}

export function buildLegAxis(payload: FittingResult): LegAxis {
  const crotch = stationOf(payload, 'crotch')
  const hip = stationOf(payload, 'hip')
  const thigh = stationOf(payload, 'thigh')
  const knee = stationOf(payload, 'knee')
  const hem = stationOf(payload, 'hem')
  if (!crotch || !hip || !knee || !hem) {
    throw new Error('腿轴缺站点（crotch/hip/knee/hem）——payload 不完整')
  }
  const hipG = hip.girth_finished ?? 0
  const leg: Profile = ([
    [crotch.y, coreRadius(thigh?.girth_finished ?? hipG)],
    ...(thigh && thigh.y < crotch.y - 1e-9
      ? ([[thigh.y, coreRadius(thigh.girth_finished!)]] as Profile) : []),
    [knee.y, coreRadius(knee.girth_finished ?? 0)],
    [hem.y, coreRadius(hem.girth_finished ?? 0)],
  ] as Profile).sort((a, b) => a[0] - b[0])
  return {
    rAt: (y) => radiusAt(leg, y),
    cAt: (y) => radiusAt(leg, y) + LEG_GAP_MIN
      + (LEG_GAP_HALF - LEG_GAP_MIN)
        * Math.max(0, Math.min(1, (crotch.y - y) / LEG_GAP_TAPER)),
    forkY: crotch.y,
  }
}

// 圆管实体（逐行圆环 + 行间条带 + 两端封盖，法线朝外——collide 内外判
// 用，反了会把盖外粒子反推进管内，v1 实测穿透 16cm 的根因）。cx = 轴心
// x（腿管 ±c，躯干 0）
function tube(
  rings: { y: number; xs: number[]; zs: number[] }[],
  capCx: [number, number],   // [底盖轴心 x, 顶盖轴心 x]（腿管锥形轴两端不同）
  positions: number[], indices: number[],
): void {
  const base = positions.length / 3
  const rows = rings.length
  for (const ring of rings) {
    for (let s = 0; s < SEG; s++) {
      positions.push(ring.xs[s], ring.y, ring.zs[s])
    }
  }
  for (let r = 0; r + 1 < rows; r++) {
    for (let s = 0; s < SEG; s++) {
      const a = base + r * SEG + s
      const b = base + r * SEG + ((s + 1) % SEG)
      const c = base + (r + 1) * SEG + ((s + 1) % SEG)
      const d = base + (r + 1) * SEG + s
      indices.push(a, b, c, a, c, d)
    }
  }
  // 端面封盖：顶盖朝上、底盖朝下（中心在管轴上）
  for (const [row, up] of [[rows - 1, true], [0, false]] as const) {
    const center = positions.length / 3
    positions.push(up ? capCx[1] : capCx[0], rings[row].y, 0)
    for (let s = 0; s < SEG; s++) {
      const a = base + row * SEG + s
      const b = base + row * SEG + ((s + 1) % SEG)
      if (up) indices.push(center, a, b)
      else indices.push(center, b, a)
    }
  }
}

const rowsBetween = (y0: number, y1: number): number[] => {
  const n = Math.max(3, Math.ceil((y1 - y0) / ROW) + 1)
  return Array.from({ length: n }, (_, r) => y0 + ((y1 - y0) * r) / (n - 1))
}

// 椭圆环（z 半轴 b ≤ x 半轴 a）——裆圆角带的压缩截面
function ellipseRing(a: number, b: number): { xs: number[]; zs: number[] } {
  const xs: number[] = [], zs: number[] = []
  for (let s = 0; s < SEG; s++) {
    const th = (s / SEG) * 2 * Math.PI
    xs.push(a * Math.sin(th)); zs.push(b * Math.cos(th))
  }
  return { xs, zs }
}

export function buildCore(payload: FittingResult): CoreMesh {
  const waist = stationOf(payload, 'waist')
  const hip = stationOf(payload, 'hip')
  const crotch = stationOf(payload, 'crotch')
  const thigh = stationOf(payload, 'thigh')
  const knee = stationOf(payload, 'knee')
  const hem = stationOf(payload, 'hem')
  if (!waist || !hip || !crotch || !knee || !hem) {
    throw new Error('撑型芯缺站点（waist/hip/crotch/knee/hem）——payload 不完整')
  }
  const hipG = hip.girth_finished ?? waist.girth_finished ?? 0
  const rWaist = coreRadius(waist.girth_finished ?? hipG)
  const rHip = coreRadius(hipG)
  // 裆站躯干圆半径：毗围代理 = max(臀, 2×腿)（thigh 缺省退化臀围，
  // 不掐腰——v2.1 口径延续）。腿管外沿 = 2rThigh + GAP_MIN ≈ rFork−0.2，
  // fork 处近乎连续无台阶
  const rFork = coreRadius(
    thigh?.girth_finished ? Math.max(hipG, 2 * thigh.girth_finished) : hipG)

  const torso: Profile = ([
    [crotch.y, rFork],
    [hip.y, rHip],
    [waist.y, rWaist],
    [waist.y + TOP_MARGIN, rWaist],
  ] as Profile).sort((a, b) => a[0] - b[0])

  const positions: number[] = []
  const indices: number[] = []
  // 躯干管（fork + TORSO_BOTTOM → 腰+8）：fork..fork+TORSO_BOTTOM 带留给
  // 上延腿管（裆交叉口袋），其上 CROTCH_FILLET 带 = **裆圆角**——截面
  // 前后（z 向）压缩成椭圆、左右（x 向）保持全宽，越靠裆越扁：真身形
  // 骨盆底耻骨/会阴区 z 只有 ~4-8 而左右髋仍宽；无圆角的平底圆柱会把
  // 前中布撑到全半径壁上再收回裆点 = 裆上生硬尖帐篷（用户报障「裆部
  // 前后片生硬凸起」，前中缝终态 z 3→16→12 实测）。zScale 平滑插值
  // smoothstep；摆位半径走场表自动跟随卷进裆
  const yBotT = crotch.y + TORSO_BOTTOM
  tube(rowsBetween(yBotT, waist.y + TOP_MARGIN).map((y) => {
    const r = radiusAt(torso, y)
    if (y < yBotT + CROTCH_FILLET) {
      const u = Math.max(0, Math.min(1, (y - yBotT) / CROTCH_FILLET))
      const s = u * u * (3 - 2 * u)   // smoothstep
      const zScale = CROTCH_ZMIN + (1 - CROTCH_ZMIN) * s
      const ring = ellipseRing(r, r * zScale)
      return { y, xs: ring.xs, zs: ring.zs }
    }
    const ring = circleRing(r)
    return { y, xs: ring.xs, zs: ring.zs }
  }), [0, 0], positions, indices)
  // 腿管 ×2（hem−1.5 → fork + LEG_OVERLAP，轴 ±(r+gapHalf)，左右镜像；
  // fork 以上 gapHalf 钳在 LEG_GAP_MIN——上延段保持分离不并管）
  const axis = buildLegAxis(payload)
  for (const sgn of [-1, 1] as const) {
    const yBot = hem.y - BOTTOM_MARGIN
    const yTop = crotch.y + LEG_OVERLAP
    tube(rowsBetween(yBot, yTop).map((y) => {
      const r = axis.rAt(y), c = axis.cAt(y)
      const ring = circleRing(r)
      return {
        y,
        xs: ring.xs.map((x) => sgn * c + x),
        zs: ring.zs,
      }
    }), [sgn * axis.cAt(yBot), sgn * axis.cAt(yTop)], positions, indices)
  }
  return {
    positions: new Float32Array(positions),
    indices: new Uint32Array(indices),
  }
}
