// 纸样围度撑型芯（2026-09-14 用户定方向：裤子解算与人台彻底解耦，
// 「内部是空的也要呈圆筒、不能叠」）：芯体只在 worker 解算空间当碰撞体，
// 不渲染——显示上裤子内部仍是空的、悬挂在人台旁侧。围度逐站取 payload
// stations 的 girth_finished（纸样成衣量），芯半径 = g/2π − collisionSkin，
// 布面落在 core+skin 恰为纸样围度 → 圆筒按构造成立（想叠也叠不动），
// 廓形 = 版型。工厂悬挂展示用撑型芯的同构。坐标系 = 纸样系（y=纸样高、
// hem≈0 落地），与 payload/裁片网格同源，解算 warp=identity。
//
// 形状（v2，单一水密网格——一行一闭环、行间条带、两端封盖）：
//   腰臀段 = 圆环（站间线性插值）；裆下 = 花生环（双瓣 + 腰谷），瓣弧
//   周长锁定 2×腿站 girth；裆带 ±BLEND 圆↔花生混合。花生 = 相切双圆
//   轮廓（ρ=2rc|cosθ|）的平滑版（|cosθ| → sqrt(cos²θ+ε²) 归一）+ 整环
//   缩放补周长。腿间以腰谷相连 = 两腿沿前/后中线捏拢（真悬挂裤观感），
//   内缝闭合在瓣内侧、侧缝在瓣外侧，拓扑同真裤。
//
// 裆站躯干半径（v2.1，2026-09-15 修「大腿比臀大」掐腰）：叉口处的布量
// 是连续的——毗围 ≈ max(臀围, 2×腿围)（crotch 站无围度、thigh 缺省回退
// 臀围）。旧值直接拿单腿 rc 当躯干圆半径，臀站→裆站周长从 ~2π·rHip 掐
// 到 2π·rThigh（用户 100/63.5：91.8→69.2），臀部塌成蜂腰再猛扩到花生
// 瓣，放大成「大腿比臀大」的观感；修正后臀→裆单调过渡到双瓣。
//
// v1 三件套（圆筒+双管+龙骨）的实测死路（勿回头）：
//   · 管间留槽（d=max r 常数）——内缝缝合走捷径穿槽（不可拉伸布穿槽比
//     绕管省 10cm+），整幅布堆进两腿之间、外侧裸管 =「侧缝内凹/叠腿」
//     机制本体；
//   · 双管相切 —— 切线刀口两侧壳交替投影 = 裆部抖动泵（均速 7~16）；
//   · 双管交叠 —— 符号判陷阱：粒子「在 L 管外」即「在 R 管内」，碰撞
//     反复把它钉在管内，内象限永远无布；
//   · 细龙骨（r2.5）—— preRelax 拉链直接穿膛（碰撞间隔内一步可走 ~10cm）。
import type { FittingResult, FittingStation } from '../../types'
import { SOLVER_PRIOR } from './priors'

export interface CoreMesh {
  positions: Float32Array   // cm，纸样系 Y-up（x 侧向、z 前向、y 纸样高）
  indices: Uint32Array      // 三角（0-based）
}

const SEG = 64               // 环向分段（花生两瓣各半）
const ROW = 2                // 纵向行距 cm
const TOP_MARGIN = 8         // 腰上延伸（band 上沿 + 余量）
const BOTTOM_MARGIN = 1.5    // 脚口下延伸（hem 行粒子防端面边界抖动）
const BLEND = 3              // 裆带半高：圆↔花生过渡 cm
const EPS = 0.3              // 花生腰谷参数：waist ≈ 2rc·EPS（相对量）

// 纸样围度 -> 瓣半径：布接触壳在 core+skin，落点围度恰 = girth_finished
const coreRadius = (g: number): number =>
  g / (2 * Math.PI) - SOLVER_PRIOR.collisionSkin

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

// 环周长（极坐标折线数值积分；SEG 段求和）
function ringPerimeter(xs: number[], zs: number[]): number {
  let p = 0
  for (let s = 0; s < xs.length; s++) {
    const t = (s + 1) % xs.length
    p += Math.hypot(xs[t] - xs[s], zs[t] - zs[s])
  }
  return p
}

// 花生基形（未缩放）：点 = (ρ·sinθ, ρ·cosθ)（与筒链同向绕序，法线朝外），
// ρ0(θ) = 2rc·sqrt(sin²θ+ε²)/sqrt(1+ε²) —— 瓣沿 ±x（sinθ 峰）、腰谷在
// ±z（前后中线）。ε→0 退化为相切双圆（周长 4πrc）；ε>0 腰谷平滑。
function peanutRaw(rc: number, out: { xs: number[]; zs: number[] }): void {
  out.xs.length = 0; out.zs.length = 0
  const norm = Math.sqrt(1 + EPS * EPS)
  for (let s = 0; s < SEG; s++) {
    const th = (s / SEG) * 2 * Math.PI
    const rho = (2 * rc / norm)
      * Math.sqrt(Math.sin(th) * Math.sin(th) + EPS * EPS)
    out.xs.push(rho * Math.sin(th))
    out.zs.push(rho * Math.cos(th))
  }
}

// 一行闭环点：花生（缩放到周长 = 2×瓣目标 2πrc）
function peanutRing(rc: number): { xs: number[]; zs: number[] } {
  const ring = { xs: [] as number[], zs: [] as number[] }
  peanutRaw(rc, ring)
  const k = (4 * Math.PI * rc) / ringPerimeter(ring.xs, ring.zs)
  for (let s = 0; s < SEG; s++) {
    ring.xs[s] *= k; ring.zs[s] *= k
  }
  return ring
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
  const rThigh = coreRadius(
    thigh?.girth_finished ?? hipG ?? waist.girth_finished ?? 0)
  const rKnee = coreRadius(knee.girth_finished ?? 0)
  const rHem = coreRadius(hem.girth_finished ?? 0)
  // 裆站躯干圆半径：毗围代理 = max(臀, 2×腿)（thigh 缺省退化臀围，
  // 不掐腰）。见模块头注 v2.1
  const rFork = coreRadius(
    thigh?.girth_finished ? Math.max(hipG, 2 * thigh.girth_finished) : hipG)

  const torso: Profile = ([
    [crotch.y, rFork],
    [hip.y, rHip],
    [waist.y, rWaist],
    [waist.y + TOP_MARGIN, rWaist],
  ] as Profile).sort((a, b) => a[0] - b[0])
  const leg: Profile = ([
    [crotch.y, rThigh],
    ...(thigh && thigh.y < crotch.y - 1e-9
      ? ([[thigh.y, rThigh]] as Profile) : []),
    [knee.y, rKnee],
    [hem.y, rHem],
  ] as Profile).sort((a, b) => a[0] - b[0])

  // 逐行环：裆下花生 / 裆上圆 / 裡带混合，周长插值后整体缩放锁定
  const yBot = hem.y - BOTTOM_MARGIN
  const yTop = waist.y + TOP_MARGIN
  const rows = Math.max(3, Math.ceil((yTop - yBot) / ROW) + 1)
  const positions: number[] = []
  const indices: number[] = []
  for (let r = 0; r < rows; r++) {
    const y = yBot + ((yTop - yBot) * r) / (rows - 1)
    // 裆下 t=1（花生）、裆上 t=0（圆）、±BLEND 带内混合
    const t = Math.max(0, Math.min(1, (crotch.y + BLEND - y) / (2 * BLEND)))
    const circ = circleRing(radiusAt(torso, y))
    const pea = peanutRing(radiusAt(leg, y))
    const xs: number[] = [], zs: number[] = []
    for (let s = 0; s < SEG; s++) {
      xs.push((1 - t) * circ.xs[s] + t * pea.xs[s])
      zs.push((1 - t) * circ.zs[s] + t * pea.zs[s])
    }
    // 周长目标：圆 2πR → 花生 4πrc 线性插值（裆带过渡带不苛求精确）
    const rTor = radiusAt(torso, y), rLeg = radiusAt(leg, y)
    const target = (1 - t) * 2 * Math.PI * rTor + t * 4 * Math.PI * rLeg
    const k = target / ringPerimeter(xs, zs)
    for (let s = 0; s < SEG; s++) {
      positions.push(k * xs[s], y, k * zs[s])
    }
  }
  for (let r = 0; r + 1 < rows; r++) {
    for (let s = 0; s < SEG; s++) {
      const a = r * SEG + s
      const b = r * SEG + ((s + 1) % SEG)
      const c = (r + 1) * SEG + ((s + 1) % SEG)
      const d = (r + 1) * SEG + s
      indices.push(a, b, c, a, c, d)
    }
  }
  // 端面封盖（法线朝外：collide 内外判用面法线，反了会把盖外粒子反推进
  // 管内——v1 实测穿透 16cm 的根因）。底盖中心 (0, yBot)、顶盖 (0, yTop)
  for (const [row, up] of [[rows - 1, true], [0, false]] as const) {
    const y = yBot + ((yTop - yBot) * row) / (rows - 1)
    const center = positions.length / 3
    positions.push(0, y, 0)
    for (let s = 0; s < SEG; s++) {
      const a = row * SEG + s
      const b = row * SEG + ((s + 1) % SEG)
      if (up) indices.push(center, a, b)
      else indices.push(center, b, a)
    }
  }
  return {
    positions: new Float32Array(positions),
    indices: new Uint32Array(indices),
  }
}
