// 参数化人台：体型围度（BodyProfile，独立于成衣尺寸）+ 整版站点高度
// （payload.body.stations，垂直定位跟版走）放样下半身。
// 拓扑：骨盆单管（躯干延伸→腰→臀→裆分叉→裆下楔）+ 双腿管（隐藏头
// 上插→分叉→膝→脚口下延伸至踝；上插浅裆/容纳不足时整段放弃降级）。
// 三管互相嵌入接合：腿顶盖藏入骨盆体内（containment 等比收进 (1−m)
// 内切）、骨盆楔填充会阴支撑带——消除「骨盆平底盖 + 双腿平顶盖共面于
// y=crotch」的分体感与 z-fighting。渲染层已换 SDF 单张水密蒙皮
// （skin.ts：三管 smin 软并集 + marching cubes，绕向/水密金标在
// skin.test.ts；碰撞/摆位仍走本文件 sectionAt/radiusAt 解析路径）。
// 横截面为超椭圆（|x/a|^e + |z/b|^e = 1，前后半深分离表臀凸，+Z=身体
// 前方）。围度按站点 Catmull-Rom 平滑采样成环（~4cm 一环）；骨盆上段
// 与腿下段站点表与旧版逐位一致（接合带之外零漂移）。
// 纯几何模块：不依赖 three，渲染/碰撞共用同一组截面参数。
import type { FittingResult } from '../types'
import type { BodyGirths } from './bodyProfile'
import { BODY_RATIO, MESH_PRIOR, SECTION_PRIOR } from './priors'

// 截面参数（一个环）：cx 为管中心 X 偏移（双腿管 ±，骨盆 0）
export interface SectionParams {
  y: number
  a: number    // X 半宽
  bF: number   // +Z 前半深
  bB: number   // −Z 后半深（臀凸 > bF）
  e: number    // 超椭圆指数
  cx: number
}

// 管段：按 y 降序的截面环（渲染抽环 + 碰撞插值共用）
export interface Tube {
  rings: SectionParams[]
}

export interface Mannequin {
  pelvis: Tube
  legs: [Tube, Tube]   // [wearer 左(−X), 右(+X)]
  topY: number
  bottomY: number
}

// 超椭圆截面形状 -> 标定到目标围度的半轴组
function sectionShape(
  girth: number, kind: keyof typeof SECTION_PRIOR,
): { a: number; bF: number; bB: number; e: number } {
  const s = SECTION_PRIOR[kind]
  const e = s.e
  // 基准形状（a=1）48 边折线周长 -> 等比缩放到目标围
  const per = superellipsePerimeter(1, s.depth, s.depth * s.backBias, e)
  const scale = girth / per
  return { a: scale, bF: scale * s.depth, bB: scale * s.depth * s.backBias, e }
}

// 超椭圆 48 边折线周长（离散标定，与渲染环一致）
export function superellipsePerimeter(
  a: number, bF: number, bB: number, e: number,
  seg = MESH_PRIOR.ringSegments,
): number {
  let per = 0
  let prev = ringPoint(a, bF, bB, e, 0)
  for (let i = 1; i <= seg; i++) {
    const p = ringPoint(a, bF, bB, e, i / seg)
    per += Math.hypot(p[0] - prev[0], p[1] - prev[1])
    prev = p
  }
  return per
}

// 环上参数 u∈[0,1) 的点（θ=0 前中 +Z、向 +X 方向绕）
export function ringPoint(
  a: number, bF: number, bB: number, e: number, u: number,
): [number, number] {
  const th = u * Math.PI * 2
  const c = Math.cos(th), s = Math.sin(th)
  const b = c >= 0 ? bF : bB       // cos>0 前半（+Z）、<0 后半
  const px = Math.sign(s) * Math.pow(Math.abs(s), 2 / e) * a
  const pz = Math.sign(c) * Math.pow(Math.abs(c), 2 / e) * b
  return [px, pz]
}

// Catmull-Rom 一维插值（站点围度平滑采样）
function catmull(p0: number, p1: number, p2: number, p3: number, t: number) {
  const t2 = t * t, t3 = t2 * t
  return 0.5 * ((2 * p1) + (-p0 + p2) * t
    + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
    + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
}

// 站点列 [(y, girth)]（y 降序）-> 每 ~step cm 一环的采样（含端点）
function sampleStations(
  stations: [number, number][], step = 4,
): [number, number][] {
  const out: [number, number][] = []
  for (let i = 0; i < stations.length - 1; i++) {
    const [y0, g0] = stations[i]
    const [y1, g1] = stations[i + 1]
    const pm = stations[i - 1] ?? stations[i]
    const pp = stations[i + 2] ?? stations[i + 1]
    const n = Math.max(1, Math.ceil((y0 - y1) / step))
    for (let k = 0; k < n; k++) {
      const t = k / n
      out.push([y0 + (y1 - y0) * t, catmull(pm[1], g0, g1, pp[1], t)])
    }
  }
  out.push(stations[stations.length - 1])
  return out
}

// BodyProfile + payload 站点高度 -> 人台
export function buildMannequin(
  body: FittingResult['body'], girths: BodyGirths,
): Mannequin {
  const yOf = (key: string): number =>
    (body.stations.find((s) => s.key === key)?.y ?? 0)
  const yWaist = yOf('waist'), yHip = yOf('hip')
  // 入口守卫：crotch 不越过 hip−2（畸形 payload 保站点严格降序）
  const yCrotch = Math.min(yOf('crotch'), yHip - 2)
  const yKnee = yOf('knee'), yHem = yOf('hem')
  const yThighRaw = body.stations.some((s) => s.key === 'thigh')
    ? yOf('thigh')
    : yCrotch - BODY_RATIO.thighStationDrop
  // 大腿站守卫：clamp 进 [knee+2, crotch−0.5]（集成夹具 thigh@y==crotch
  // 的重复 y 站点即命中，杜绝腿管零面积环）
  const yThigh = Math.min(Math.max(yThighRaw, yKnee + 2), yCrotch - 0.5)
  const gThigh = girths.thigh ?? girths.hip * BODY_RATIO.thighGirthRatio
  const ankle = (body.stations.find((s) => s.key === 'hem')
    ?.girth_finished ?? girths.knee / 0.78) * BODY_RATIO.ankleRatio

  // 骨盆管上段：躯干顶 -> 腰 -> 臀 -> 裆（分叉），站点表与旧版逐位一致
  const pelvisUpper = sampleStations([
    [yWaist + BODY_RATIO.torsoExtend, girths.waist * BODY_RATIO.torsoTopRatio],
    [yWaist, girths.waist],
    [yHip, girths.hip],
    [yCrotch, girths.hip * BODY_RATIO.crotchGirthRatio],
  ])
  // 骨盆楔（裆下延伸填充会阴）：[hip, hip 围] 作前瞻锚保 crotch 处切向
  // 向下连续，采样后只留 y < crotch 的环（杜绝单表追加站点造成的
  // CR 过冲：82 环围度会从 88.8 漂到 91.28）
  const pelvisWedge = sampleStations([
    [yHip, girths.hip],
    [yCrotch, girths.hip * BODY_RATIO.crotchGirthRatio],
    [yCrotch - BODY_RATIO.wedgeDropBelowCrotch,
      girths.hip * BODY_RATIO.wedgeBottomGirthRatio],
  ]).filter(([y]) => y < yCrotch)
  const pelvisRings = [...pelvisUpper, ...pelvisWedge].map(([y, g]) => {
    const kind = y > yWaist + 1 ? 'default'
      : y > yHip - 1 ? 'waist' : 'hip'   // 楔环 y<crotch 自动落 hip 档
    return { y, cx: 0, ...sectionShape(g, kind) }
  })
  // 拼接守卫：骨盆环 y 严格降序（无重复 y -> 无零面积面/NaN 法线）
  for (let i = 1; i < pelvisRings.length; i++) {
    if (!(pelvisRings[i - 1].y > pelvisRings[i].y)) {
      throw new Error(`骨盆环 y 非严格降序 i=${i} y=${pelvisRings[i].y}`)
    }
  }
  const pelvis: Tube = { rings: pelvisRings }

  // 腿管隐藏头（上插段）：顶 y = min(crotch+6, hip−1)，头围挂 hip 派生
  // （容纳能力只由骨盆决定，thigh 缺省/极端腿围不影响）；浅裆退化
  // （yTop ≤ crotch+0.5）或下方容纳预检不过时整段放弃上插、只保骨盆楔
  // ——共面盖对的消除不依赖上插成立
  const yTop = Math.min(yCrotch + BODY_RATIO.legRiseAboveCrotch, yHip - 1)
  let legUpper: [number, number][] = yTop > yCrotch + 0.5
    ? sampleStations([
      [yTop, girths.hip * BODY_RATIO.legTopGirthRatio],
      [yCrotch, gThigh * 1.02],
    ]).slice(0, -1)   // 去 y=crotch 尾环（下段首环已含）
    : []
  // 腿管下段：分叉 -> 大腿站 -> 膝 -> 脚口 -> 踝（脚口下延伸），
  // 站点表与旧版逐位一致
  const legStations: [number, number][] = [
    [yCrotch, gThigh * 1.02],
    [yThigh, gThigh],
    [yKnee, girths.knee],
    [yHem, (girths.knee + ankle) / 2],
    [yHem - BODY_RATIO.legExtendBelow, ankle],
  ]
  const legCenter = girths.hip * BODY_RATIO.legCenterRatio
  const m = BODY_RATIO.embedMarginRatio
  // 藏盖 clamp 系数（单一来源，预检与 mkLeg 共用）：上插环等比收进骨盆
  // (1−m) 内切的最大收缩比 k = min(三轴)（等比保形，e/cx 不动）。k 不可
  // 反向钳大——它是满足 containment 的最大值，放大即穿出骨盆壁。容纳
  // 能力在裆上环段对腿臀比/腰臀差敏感（该处骨盆围 ≈0.94×hip，腰围≫臀围
  // 时 CR 欠冲更低），放不下由预检整段降级、不由常量余量保证
  const embedKOf = (
    y: number, s: { a: number; bF: number; bB: number }, cx: number,
  ): number => {
    const P = sectionAt(pelvis, y)
    return Math.min(1,
      ((1 - m) * P.a - Math.abs(cx)) / s.a,
      ((1 - m) * P.bF) / s.bF,
      ((1 - m) * P.bB) / s.bB)
  }
  // 容纳预检（优雅降级而非抛错）：任一上插环 k < 0.3 = 该体型在裆上环段
  // 真实放不下（如 waist≫hip + thigh>hip 的逐字段合法病理输入，抛错会被
  // 解算层 catch 掉使 3D tab 静默空白）——整段放弃上插，三盖不共面/楔
  // 填充不依赖上插成立，代价仅腿顶平盖露出（旧观感）
  if (legUpper.length && !legUpper.every(([y, g]) =>
    embedKOf(y, sectionShape(g, 'default'), legCenter) >= 0.3)) {
    legUpper = []
  }
  const mkLeg = (cx: number): Tube => {
    const rings = [...legUpper, ...sampleStations(legStations)]
      .map(([y, g]) => ({
        y, cx,
        ...sectionShape(g, Math.abs(y - yKnee) < 1 ? 'knee' : 'default'),
      }))
      .map((r) => {
        if (r.y <= yCrotch) return r
        // 上插环 y > yCrotch > yKnee+1 恒为 default 档，与预检同式同参
        //（上插段已移除时此处无环可进），预检保证 k ≥ 0.3
        const k = embedKOf(r.y, r, cx)
        return { ...r, a: r.a * k, bF: r.bF * k, bB: r.bB * k }
      })
    // 拼接守卫：腿环 y 严格降序（上下段拼接无重复 y）
    for (let i = 1; i < rings.length; i++) {
      if (!(rings[i - 1].y > rings[i].y)) {
        throw new Error(`腿环 y 非严格降序 i=${i} y=${rings[i].y}`)
      }
    }
    return { rings }
  }

  return {
    pelvis,
    legs: [mkLeg(-legCenter), mkLeg(legCenter)],
    topY: yWaist + BODY_RATIO.torsoExtend,
    bottomY: yHem - BODY_RATIO.legExtendBelow,
  }
}

// y 处截面参数（夹取到端环，相邻环线性插值）
export function sectionAt(tube: Tube, y: number): SectionParams {
  const r = tube.rings
  if (y >= r[0].y) return r[0]
  const last = r[r.length - 1]
  if (y <= last.y) return last
  for (let i = 0; i < r.length - 1; i++) {
    if (y <= r[i].y && y >= r[i + 1].y) {
      const t = (r[i].y - y) / (r[i].y - r[i + 1].y || 1)
      const A = r[i], B = r[i + 1]
      return {
        y, cx: A.cx + (B.cx - A.cx) * t,
        a: A.a + (B.a - A.a) * t,
        bF: A.bF + (B.bF - A.bF) * t,
        bB: A.bB + (B.bB - A.bB) * t,
        e: A.e + (B.e - A.e) * t,
      }
    }
  }
  return last
}

// 方向 (dx,dz) 必须为单位向量（相对管中心），返回该方向上的超椭圆半径；
// 非单位输入返回的是使 r·(dx,dz) 落界的缩放倍数（仅供内部迭代用），
// 调用方不得依赖——collide 曾因此把穿透判据退化成 dist ≥ R/dist + skin。
// 迭代缩放法：f(r) 随 r 单调 ^e，r ← r·f^{-1/e} 三次收敛（<1e-4 相对误差）
export function radiusAt(
  s: SectionParams, dx: number, dz: number,
): number {
  const sx = Math.abs(dx) / s.a
  const sz = Math.abs(dz) / (dz >= 0 ? s.bF : s.bB)
  if (sx + sz < 1e-9) return 0
  let r = 1 / Math.pow(sx + sz, 1 / s.e)   // e=1 线性精确；e≈2 起步近优
  for (let k = 0; k < 3; k++) {
    const f = Math.pow(r * sx, s.e) + Math.pow(r * sz, s.e)
    if (f < 1e-12) break
    r *= Math.pow(f, -1 / s.e)
  }
  return r
}

