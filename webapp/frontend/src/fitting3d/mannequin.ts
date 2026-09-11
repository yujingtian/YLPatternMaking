// 参数化人台：体型围度（BodyProfile，独立于成衣尺寸）+ 整版站点高度
// （payload.body.stations，垂直定位跟版走）放样下半身。
// 拓扑（2026-09-10 人体化重构）：骨盆单管（躯干延伸→腰→臀→裆分叉→裆
// 下楔）+ 双腿管（外缘连续 emergence 头带→分叉→大腿→膝→小腿肚→脚口
// 下延伸至踝）。腿环逐环派生 cx = max(a+gap, min(outer−a, cxMax))——
// 外缘目标梯子保证「最宽点在臀带、大腿外缘与臀线连续、膝/踝按人体比例
// 收窄」，内缘 gap 下限梯子保证裆下 ~5cm 内过零分离、大腿中段缝 ≥2cm
// 可辨（五轮移除旧「裆下 ~9cm 接触带」设计——其微缝在 kLL 桥接与 MC
// 可辨阈之下视觉焊死；替代旧 containment 藏头：隐藏头钳位使 emergence
// 一环跳变 a 4.4→9.2，是「躯干块+两腿柱搭积木」观感的直接来源，见
// 决策日志 2026-09-10）。
// 渲染层为 SDF 单张水密蒙皮（skin.ts：三管 smin 软并集 + marching
// cubes，绕向/水密金标在 skin.test.ts；碰撞/摆位仍走本文件
// sectionAt/radiusAt 解析路径，逐环 cx 天然支持）。
// 横截面为超椭圆（|x/a|^e + |z/b|^e = 1，前后半深分离表臀凸，+Z=身体
// 前方）。围度按站点 Catmull-Rom 平滑采样成环（骨盆 ~2cm/腿 ~4cm 一环）。
// 2026-09-10 第四轮人体化塑形：①矢状 S 曲线——前后半深偏置（backBias/
// frontBias）与 e/depth 均为 y 向连续梯子（SAGITTAL/SECTION_PRIOR 锚，
// 站点锚值不动 -> 单原语站金标保住）；②外缘梯子与 sectionAt 的 a/bF/bB/e
// 改单调三次 Hermite（monoSplineAt：结点导数 ≤3×割线、峰谷锚平导数），
// 治「直线锥腿」与「环间线性插值折点棱线」；③肋弓外扩锚（rib）使腰成
// 全局最窄；④双脚与肚脐为 SDF 场加原语（skin.ts 蒙皮专用；不进碰撞——
// 脚顶 ≈ y −8.6 低于裤口 y=0、脐为浅凹刻，布料均不可达）。
// cx 不进样条——分段线性 gap 梯子逐环派生 + sectionAt 线性插值，碰撞
// 路径 Lipschitz 界由构造可证（勿顺手样条化）。
// 纯几何模块：不依赖 three，渲染/碰撞共用同一组截面参数。
import type { FittingResult } from '../types'
import type { BodyGirths } from './bodyProfile'
import { BODY_RATIO, FOOT_PRIOR, MESH_PRIOR, NAVEL_PRIOR, SAGITTAL, SECTION_PRIOR } from './priors'

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
  feet: [FootParams, FootParams]  // SDF 场加原语（蒙皮/解耦参照，不进碰撞）
  navel: NavelParams   // 同上（smax 凹刻椭球）
  topY: number
  bottomY: number      // 站立地面（FOOT_PRIOR.groundY）
}

// 脚原语：局部系原点 = 踝关节、+Z = 脚尖；两圆角盒（核心半轴 + 圆角 =
// 实际半轴）；yaw 绕 Y 微外八（右脚 +、左脚 −）。绝对 cm 标准脚（病理
// 体型共用，不随围度缩放）
export interface FootBox {
  c: [number, number, number]  // 局部盒心
  h: [number, number, number]  // 核心半轴（圆角前）
}
export interface FootParams {
  origin: [number, number, number]
  yaw: number
  round: number
  boxes: [FootBox, FootBox]    // [后段 足跟/足弓, 前段 脚掌/脚趾]
}

// 肚脐凹刻椭球（挂前腹表面 x=0；z 为中心离前表面内移后的世界坐标）
export interface NavelParams {
  y: number; z: number
  rx: number; ry: number; rz: number
}

// 超椭圆截面形状 -> 标定到目标围度的半轴组。bias 形参（2026-09-10 第四轮）
// ：周长标定用实际前后半深 (depth×frontBias, depth×backBias) -> a 同步
// 重算，**每环围度精确不变**（bias 只改形不改围）
function sectionShape(
  girth: number, e: number, depth: number, backBias: number, frontBias: number,
): { a: number; bF: number; bB: number; e: number } {
  // 基准形状（a=1）48 边折线周长 -> 等比缩放到目标围
  const per = superellipsePerimeter(1, depth * frontBias, depth * backBias, e)
  const scale = girth / per
  return {
    a: scale, bF: scale * depth * frontBias, bB: scale * depth * backBias, e,
  }
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

// 分段线性梯子插值：锚点 [(y, v)]（y 严格降序）-> v(y)（界外夹端值）。
// gapLadder/headLadder 专用（cx 路径——线性使 |Δcx|/|Δy| 由构造有界，
// Lipschitz 论证前提，勿换样条；外缘/形状梯子已改 monoSplineAt）
function ladderAt(
  anchors: readonly (readonly [number, number])[], y: number,
): number {
  if (y >= anchors[0][0]) return anchors[0][1]
  for (let i = 0; i < anchors.length - 1; i++) {
    const [y0, v0] = anchors[i]
    const [y1, v1] = anchors[i + 1]
    if (y <= y0 && y >= y1) {
      return v0 + (v1 - v0) * ((y0 - y) / (y0 - y1 || 1))
    }
  }
  return anchors[anchors.length - 1][1]
}

// 单调三次 Hermite 区间求值（monoSplineAt / sectionAt 共用，免分配）。
// s∈[0,1] 自 y0 降参至 y1（h = y0−y1），结点导数 m 为 dv/dy：
// v(s) = h00·v0 − h·m0·h10 + h01·v1 − h·m1·h11（标准 Hermite 基）
function monoHerm(
  v0: number, v1: number, m0: number, m1: number, s: number, h: number,
): number {
  const s2 = s * s, s3 = s2 * s
  return (2 * s3 - 3 * s2 + 1) * v0 - h * m0 * (s3 - 2 * s2 + s)
    + (-2 * s3 + 3 * s2) * v1 - h * m1 * (s3 - s2)
}

// 单调样条结点导数（Fritsch–Carlson 型）：相邻区间割线变号（局部极值锚）
// 取 0——平滑峰/谷无过冲；否则同号限幅 |m| ≤ 3×min(|σL|,|σR|) 且 ≤ 均值
// -> 区间内无过冲、|v'| ≤ 3×局部割线（外缘 Lipschitz ≤0.7 论证依据）
function monoSlope(sl: number, sr: number): number {
  if (sl * sr <= 0) return 0
  const sg = sl > 0 ? 1 : -1
  return sg * Math.min(3 * Math.abs(sl), 3 * Math.abs(sr),
    (Math.abs(sl) + Math.abs(sr)) / 2)
}

// 锚点 [(y, v)]（y 严格降序）-> 单调样条 v(y)（界外夹端值；端点取单侧
// 割线）。ladderAt 的样条化替代——外缘/形状参数梯子专用；gapLadder 与
// headLadder 维持线性（cx 路径，Lipschitz 论证前提）
function monoSplineAt(
  anchors: readonly (readonly [number, number])[], y: number,
): number {
  if (y >= anchors[0][0]) return anchors[0][1]
  for (let i = 0; i < anchors.length - 1; i++) {
    const [y0, v0] = anchors[i]
    const [y1, v1] = anchors[i + 1]
    if (y <= y0 && y >= y1) {
      const h = y0 - y1 || 1
      const sig = (v0 - v1) / h
      const sl = i > 0
        ? (anchors[i - 1][1] - v0) / ((anchors[i - 1][0] - y0) || 1) : sig
      const sr = i < anchors.length - 2
        ? (v1 - anchors[i + 2][1]) / ((y1 - anchors[i + 2][0]) || 1) : sig
      return monoHerm(v0, v1, monoSlope(sl, sig), monoSlope(sig, sr),
        (y0 - y) / h, h)
    }
  }
  return anchors[anchors.length - 1][1]
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

  // 骨盆管上段：躯干顶 -> 下肋（外扩锚）-> 腰 -> 臀（止于臀站）。
  // 2026-09-10 第四轮：新肋锚 ribGirthRatio×腰 @ waist+ribRiseAboveWaist
  // ——躯干上段腰以上双向展开，腰成全局最窄点（治「腰线弱」）；采样步
  // 4→2（臀峰/腰椎谷特征宽 ~4-6cm，4cm 环画不出连续曲率，也是环棱线
  // 观感来源之一）
  const pelvisUpper = sampleStations([
    [yWaist + BODY_RATIO.torsoExtend, girths.waist * BODY_RATIO.torsoTopRatio],
    [yWaist + BODY_RATIO.ribRiseAboveWaist,
      girths.waist * BODY_RATIO.ribGirthRatio],
    [yWaist, girths.waist],
    [yHip, girths.hip],
  ], 2)
  // 臀下填充带（五轮腰髋沟修复）：独立前瞻表（[hip] 锚被滤掉、只压 CR
  // 切向——直接在 pelvisUpper 插站会让 hip 切向受腰围拖拽产生 +1 围度
  // 臀上鼓包破「带内 a ≤ aHip」不变量）；产 (crotch, hip) 开区间环 + 裆
  // 环端点（上段止于臀站，无重复 y）。锚 y 钳入区间内 0.75——入口 clamp
  // 只保 hip−crotch ≥ 2（浅裆/裆高 clamp 夹具站点仍严格降序不抛）
  const yFill = Math.min(
    Math.max(yHip - BODY_RATIO.fillBelowHip, yCrotch + 0.75), yHip - 0.75)
  const pelvisFill = sampleStations([
    [yHip, girths.hip],
    [yFill, girths.hip * BODY_RATIO.fillGirthRatio],
    [yCrotch, girths.hip * BODY_RATIO.crotchGirthRatio],
  ], 2).filter(([y]) => y < yHip)
  // 骨盆楔（裆下延伸填充会阴）：[hip, hip 围] 作前瞻锚保 crotch 处切向
  // 向下连续，采样后只留 y < crotch 的环（杜绝单表追加站点造成的
  // CR 过冲：82 环围度会从 88.8 漂到 91.28）
  const pelvisWedge = sampleStations([
    [yHip, girths.hip],
    [yCrotch, girths.hip * BODY_RATIO.crotchGirthRatio],
    [yCrotch - BODY_RATIO.wedgeDropBelowCrotch,
      girths.hip * BODY_RATIO.wedgeBottomGirthRatio],
  ], 2).filter(([y]) => y < yCrotch)
  // 形状参数 y 向连续梯子（2026-09-10 第四轮，锚值 = SECTION_PRIOR 站点
  // 锚 + SAGITTAL 中间锚；kind 档位跳变整类消失）。矢状 S 曲线：腰椎谷
  // -> 臀峰 -> 臀底褶（bB）与小腹微凸（bF）；绝对 y 锚按体型站点组装，
  // 楔底以下夹端值
  const yTorsoTop = yWaist + BODY_RATIO.torsoExtend
  const yWedgeBottom = yCrotch - BODY_RATIO.wedgeDropBelowCrotch
  const dflt = SECTION_PRIOR.default
  const pelvisLadders = {
    e: [
      [yTorsoTop, dflt.e], [yWaist, SECTION_PRIOR.waist.e],
      [yHip, SECTION_PRIOR.hip.e], [yWedgeBottom, SECTION_PRIOR.hip.e],
    ],
    depth: [
      [yTorsoTop, dflt.depth], [yWaist, SECTION_PRIOR.waist.depth],
      [yHip, SECTION_PRIOR.hip.depth], [yWedgeBottom, SECTION_PRIOR.hip.depth],
    ],
    bB: [
      [yTorsoTop, dflt.backBias], [yWaist, SECTION_PRIOR.waist.backBias],
      [(yWaist + yHip) / 2, SAGITTAL.lumbarBias],
      [yHip, SECTION_PRIOR.hip.backBias],
      [yHip - SAGITTAL.glutealBelowRatio * (yHip - yCrotch),
        SAGITTAL.glutealBias],
      [yCrotch, SAGITTAL.crotchBackBias],
      [yWedgeBottom, SAGITTAL.wedgeBackBias],
    ],
    bF: [
      [yTorsoTop, dflt.backBias], [yWaist, SECTION_PRIOR.waist.backBias],
      // 臀站锚 1.0（dump 重校）：无此锚 fb@86≈1.09 吃掉臀站宽度 0.5cm，
      // 大腿带外缘反超臀线破「最宽点≈臀」；锚后小腹凸严格限于臀线下。
      // 五轮b 双侧沿锚（VLM「屋檐棱线」= 峰锚与端锚均被 monoSlope 钳 0
      // 导数、两段 Hermite 双端零斜率的平台-升-平台-落）：非极值沿锚
      // 斜率非零，峰区曲率摊开成 ~3cm 圆穹顶（常数语义见 priors 注）
      [yHip, 1.0],
      [yHip - SAGITTAL.bellyUpperRimRatio * (yHip - yCrotch),
        SAGITTAL.bellyUpperRimBias],
      [yHip - SAGITTAL.bellyBelowRatio * (yHip - yCrotch),
        SAGITTAL.bellyBias],
      [yHip - SAGITTAL.bellyRimRatio * (yHip - yCrotch),
        SAGITTAL.bellyRimBias],
      [yCrotch, SAGITTAL.crotchFrontBias],
      [yWedgeBottom, SAGITTAL.wedgeFrontBias],
    ],
  } as const
  const pelvisRings = [...pelvisUpper, ...pelvisFill, ...pelvisWedge].map(([y, g]) => ({
    y, cx: 0,
    ...sectionShape(g,
      monoSplineAt(pelvisLadders.e, y), monoSplineAt(pelvisLadders.depth, y),
      monoSplineAt(pelvisLadders.bB, y), monoSplineAt(pelvisLadders.bF, y)),
  }))
  // 拼接守卫：骨盆环 y 严格降序（无重复 y -> 无零面积面/NaN 法线）
  for (let i = 1; i < pelvisRings.length; i++) {
    if (!(pelvisRings[i - 1].y > pelvisRings[i].y)) {
      throw new Error(`骨盆环 y 非严格降序 i=${i} y=${pelvisRings[i].y}`)
    }
  }
  const pelvis: Tube = { rings: pelvisRings }

  // ---- 腿管（2026-09-10 人体化）：围度站点 CR 采样（机制不变）+ 每环按
  // 「外缘目标梯子 / 内缘 gap 下限梯子」派生 cx；头带 (crotch, yTop] 按
  // outerHead 凸坡直接构造（外缘连续长出骨盆壁，替代旧 containment 藏头
  // 的一环跳变）。所有常数语义见 priors.ts BODY_RATIO 注释 ----
  const hipAnchor = SECTION_PRIOR.hip
  const W_h = sectionShape(girths.hip, hipAnchor.e, hipAnchor.depth,
    hipAnchor.backBias, 1).a
  const cxMax = W_h * BODY_RATIO.cxMaxRatio
  const yAnkle = yHem - BODY_RATIO.legExtendBelow
  // 小腿肚站：膝下 calfBelowKnee cm（短腿 clamp 进 (hem+2, knee−1)，
  // 防站点乱序触发严格降序断言 → 3D tab 静默空白）；围钳 ≤thigh×0.97
  // 防短腿体型小腿倒挂粗过大腿
  const yCalf = Math.min(yKnee - 1,
    Math.max(yKnee - BODY_RATIO.calfBelowKnee, yHem + 2))
  const gCalf = Math.min(
    girths.knee * BODY_RATIO.calfGirthRatio, gThigh * 0.97)
  // 五轮c 峰下收拢站（calf 站下 calfTaperBelow cm，短腿钳入 (hem+2,
  // calf−2) 防乱序）：真小腿围度峰下快-慢凹降（VLM 复验「下降段太直」）
  const yCalfTaper = Math.min(yCalf - 2,
    Math.max(yCalf - BODY_RATIO.calfTaperBelow, yHem + 2))
  // 外缘梯子 2026-09-10 第四轮样条化 + calf 显式锚（膝局部最窄、小腿肚
  // 局部最凸，峰谷锚平导数）；gapLadder 维持线性（cx 不进样条）
  const outerLadder: readonly (readonly [number, number])[] = [
    [yThigh, W_h * BODY_RATIO.outerAtThigh],
    [yKnee, W_h * BODY_RATIO.outerAtKnee],
    [yCalf, W_h * BODY_RATIO.outerAtCalf],
    [yHem, W_h * BODY_RATIO.outerAtHem],
    [yAnkle, W_h * BODY_RATIO.outerAtAnkle],
  ]
  // 五轮开缝：yMidGap 钳 ≤ yThigh−1（该 y 同时入下段站位表，防短腿体型
  // 站点乱序触发腿环严格降序断言）；新过零锚 yGapOpen（crotch 下
  // gapOpenBelowCrotch）使可见分离保持在裆下 ~5cm——其上 gap<0 两腿内壁
  // 互叠由 kLL 桥接、其下转正成缝（维持线性，cx Lipschitz 论证前提）
  const yMidGap = Math.min(
    Math.max(yCrotch - BODY_RATIO.gapMidDrop, yKnee + 1), yThigh - 1)
  const yGapOpen = Math.min(
    Math.max(yCrotch - BODY_RATIO.gapOpenBelowCrotch, yMidGap + 1), yCrotch - 1)
  // 分离点围度站 y：钳入 (yMidGap+0.5, yThigh−0.5)——短腿 clamp 体型
  // yGapOpen 可与 yThigh/yMidGap 贴近甚至乱序（站位表要求严格降序）；
  // gap 梯子锚仍用真 yGapOpen（标准体型二者同值）
  const yGapFill = Math.min(Math.max(yGapOpen, yMidGap + 0.5), yThigh - 0.5)
  const gapLadder: readonly (readonly [number, number])[] = [
    [yCrotch, BODY_RATIO.gapAtCrotch],
    [yGapOpen, 0],
    [yMidGap, BODY_RATIO.gapAtMidThigh],
    [yKnee, BODY_RATIO.gapAtKnee],
    [yCalf, BODY_RATIO.gapAtCalf],
    [yHem, BODY_RATIO.gapAtHem],
    [yAnkle, BODY_RATIO.gapAtAnkle],
  ]
  // 统一派生式：下限（贴腿可行性）优先于上限（cxMax），
  // 外缘目标区间内取 outer−a。cx 恒 > 0（a+gap ≥ a−1.8，病理粗腿 a>1.8）
  const cxOf = (y: number, a: number): number => Math.max(
    a + ladderAt(gapLadder, y),
    Math.min(monoSplineAt(outerLadder, y) - a, cxMax),
  )
  // 腿形状梯子（锚 = SECTION_PRIOR 站点锚 + SAGITTAL 腿锚：大腿中段 ham
  // 后凸锚 + 膝上 4cm 腘窝上沿锚（两锚把「ham 饱满→陡降入谷」的曲率集中
  // 到膝上 4cm，无它们时 crotch→knee 长段两端零斜率、腘窝谷 dip 0.07cm
  // 不可见）、腘窝凹/小腿肚后凸/跟腱收；frontBias 恒 1。派生锚 y 防站点
  // 乱序钳位（yRim 钳 ≤ yHam−1，膝贴近裆的畸形 payload 也不乱序）
  const yHam = (yCrotch + yKnee) / 2
  const yRim = Math.min(yHam - 1, yKnee + 4)
  const legLadders = {
    e: [
      [yCrotch, dflt.e], [yKnee, SECTION_PRIOR.knee.e],
      [yCalf, SECTION_PRIOR.calf.e], [yAnkle, dflt.e],
    ],
    depth: [
      [yCrotch, dflt.depth], [yKnee, SECTION_PRIOR.knee.depth],
      [yCalf, SECTION_PRIOR.calf.depth], [yAnkle, dflt.depth],
    ],
    bB: [
      // 五轮裆首锚 thighTopBackBias（臀底过渡主锚；四轮前硬编码 1.0 是
      // 盆-腿后壁交接台阶 1.21 的根因之一）
      [yCrotch, SAGITTAL.thighTopBackBias],
      [yHam, SAGITTAL.thighBackBias],
      [yRim, SAGITTAL.poplitealRimBias],
      [yKnee, SAGITTAL.poplitealBias],
      [yCalf, SAGITTAL.calfBackBias],
      // 五轮c 峰下收拢锚：后壁与围度收拢站同步拉进中段（视觉重心上移）
      [yCalfTaper, SAGITTAL.calfTaperBias], [yHem, dflt.backBias],
      [yAnkle, SAGITTAL.achillesBias],
    ],
  } as const
  // 下段环：分叉 -> 大腿站 -> 膝 -> 小腿肚 -> 脚口 -> 踝（脚口下延伸）
  // 五轮中腿围度锚（yMidGap 与 gap 锚共用派生 y）：开缝联动收腿管——
  // 无它则 a@66≈7.45、outer≈16.9 超预算；站间围度自由、thigh 站点环不动。
  // 五轮b 分离点围度锚（yGapFill）：[crotch,thigh] 平顶切向使 CR 在 74
  // 鼓出 girth≈53.5、gap 绑定下 outer@74≈15.9 成反超臀带次峰（VLM 正面
  // 「下鼓包@大转子」）；收 gapOpenGirthRatio 后 73~75 外缘带压平 ~15.0
  const lowerRings: SectionParams[] = sampleStations([
    [yCrotch, gThigh],
    [yThigh, gThigh],
    [yGapFill, gThigh * BODY_RATIO.gapOpenGirthRatio],
    [yMidGap, gThigh * BODY_RATIO.midThighGirthRatio],
    [yKnee, girths.knee],
    [yCalf, gCalf],
    // 五轮c 峰下收拢围度站：calf→hem 直落改快-慢凹降（37.8@37 → 32.5@25
    // → 30.35@0，[37→25]n=3+[25→0]n=7 与旧 [37→0]n=10 环数不变）
    [yCalfTaper, girths.knee * BODY_RATIO.calfTaperGirthRatio],
    [yHem, (girths.knee + ankle) / 2],
    [yAnkle, ankle],
  ]).map(([y, g]) => {
    const s = sectionShape(g,
      monoSplineAt(legLadders.e, y), monoSplineAt(legLadders.depth, y),
      monoSplineAt(legLadders.bB, y), 1)
    return { y, cx: cxOf(y, s.a), ...s }
  })
  // 头带环：cx 恒取裆环值（a = outerHead − cx 由外缘定半轴，与下段裆环
  // 在 y=crotch 处逐值连续）；outerHead 三锚凸坡——贴盆内壁 → 陡降入盆
  // → 放量至 outer(crotch)。浅裆退化（yTop ≤ crotch+0.5）无头，腿自
  // crotch 穹顶起（穹顶外露余量见 skin.test 病理夹具）
  const yTop = Math.min(
    yCrotch + BODY_RATIO.headRiseAboveCrotch, yHip - BODY_RATIO.headTopBelowHip)
  const headRings: SectionParams[] = []
  if (yTop > yCrotch + 0.5) {
    const r0 = lowerRings[0]
    const cxHead = r0.cx
    const outerTop = Math.min(sectionAt(pelvis, yTop).a, W_h)
      - BODY_RATIO.headFlushInset
    const ySteep = Math.max(yTop - BODY_RATIO.headSteepDrop, yCrotch + 0.5)
    const outerSteep = sectionAt(pelvis, ySteep).a - BODY_RATIO.headSteepDepth
    const headLadder: readonly (readonly [number, number])[] = [
      [yTop, outerTop],
      [ySteep, outerSteep],
      [yCrotch, cxHead + r0.a],
    ]
    const n = Math.max(2, Math.ceil(yTop - yCrotch))
    for (let k = 1; k <= n; k++) {
      const y = yTop - ((yTop - yCrotch) * k) / n
      if (y <= yCrotch) break
      const a = ladderAt(headLadder, y) - cxHead
      headRings.push({
        y, cx: cxHead, a,
        bF: a * dflt.depth, bB: a * dflt.depth * dflt.backBias, e: dflt.e,
      })
    }
  }
  const mkLeg = (sign: number): Tube => {
    const rings = [...headRings, ...lowerRings]
      .map((r) => ({ ...r, cx: r.cx * sign }))
    // 拼接守卫：腿环 y 严格降序（头带环开区间、下段首环在 crotch，无重复）
    for (let i = 1; i < rings.length; i++) {
      if (!(rings[i - 1].y > rings[i].y)) {
        throw new Error(`腿环 y 非严格降序 i=${i} y=${rings[i].y}`)
      }
    }
    return { rings }
  }

  // ---- 脚 + 肚脐（SDF 场加原语，蒙皮/解耦参照专用，不进碰撞） ----
  // 脚局部系：原点=踝关节、+Z=脚尖、+X=脚外侧；盒心 z 取段两端均值、
  // 盒心 y = 地面+半高−踝高（**局部系**——skin.footField 以 origin 平移后
  // 求值，直接存世界 y 会把脚沉到地面下 |yAnkle|）；核心半轴 = 实际半轴 −
  // 圆角；yaw 右脚 +/左脚 −（微外八）。脚盒中心 x 取踝环 cx（与腿管同轴
  // 衔接，smin 融合见 skin）
  const zHeel = -FOOT_PRIOR.heelBehind
  const zToe = FOOT_PRIOR.totalLength - FOOT_PRIOR.heelBehind
  const zSplit = zHeel + FOOT_PRIOR.rearLen
  const mkFoot = (sign: number): FootParams => {
    const ank = lowerRings[lowerRings.length - 1]   // 踝环（y = yAnkle）
    return {
      origin: [sign * ank.cx, yAnkle, 0],
      yaw: (sign * FOOT_PRIOR.toeOutDeg * Math.PI) / 180,
      round: FOOT_PRIOR.round,
      boxes: [
        {
          c: [0, FOOT_PRIOR.groundY + FOOT_PRIOR.rearHalfH - yAnkle,
            (zHeel + zSplit) / 2],
          h: [FOOT_PRIOR.rearHalfW - FOOT_PRIOR.round,
            FOOT_PRIOR.rearHalfH - FOOT_PRIOR.round,
            FOOT_PRIOR.rearLen / 2 - FOOT_PRIOR.round],
        },
        {
          c: [0, FOOT_PRIOR.groundY + FOOT_PRIOR.frontHalfH - yAnkle,
            (zSplit + zToe) / 2],
          h: [FOOT_PRIOR.frontHalfW - FOOT_PRIOR.round,
            FOOT_PRIOR.frontHalfH - FOOT_PRIOR.round,
            (FOOT_PRIOR.totalLength - FOOT_PRIOR.rearLen) / 2
              - FOOT_PRIOR.round],
        },
      ],
    }
  }
  // 肚脐：y = waist − drop；z 取当环前表面极值（x=0 处 = bF）内移 inset
  //（距站点环 98/86 均 >2cm，不碰单原语站金标）
  const yNavel = yWaist - NAVEL_PRIOR.dropBelowWaist
  const navel: NavelParams = {
    y: yNavel, z: sectionAt(pelvis, yNavel).bF - NAVEL_PRIOR.inset,
    rx: NAVEL_PRIOR.radiusX, ry: NAVEL_PRIOR.radiusY, rz: NAVEL_PRIOR.radiusZ,
  }

  return {
    pelvis,
    legs: [mkLeg(-1), mkLeg(1)],
    feet: [mkFoot(-1), mkFoot(1)],
    navel,
    topY: yWaist + BODY_RATIO.torsoExtend,
    bottomY: FOOT_PRIOR.groundY,
  }
}

// y 处截面参数（夹取到端环）。a/bF/bB/e 单调样条插值（2026-09-10 第四轮：
// 环间线性插值的 ~2-4cm 折点被 MC spacing 1.0 如实画出成「水平环棱线」；
// Hermite 在站点环精确过点 -> ±1e-6 单原语站金标不破）；cx 保持线性——
// 碰撞路径 Lipschitz 论证前提，勿顺手样条化
export function sectionAt(tube: Tube, y: number): SectionParams {
  const r = tube.rings
  if (y >= r[0].y) return r[0]
  const last = r[r.length - 1]
  if (y <= last.y) return last
  for (let i = 0; i < r.length - 1; i++) {
    if (y <= r[i].y && y >= r[i + 1].y) {
      const A = r[i], B = r[i + 1]
      const h = A.y - B.y || 1
      const s = (A.y - y) / h
      // 单字段单调样条：端点单侧割线、内部取相邻区间割线（免分配——
      // collide 每粒子每帧调用，热路径）
      const mono = (f: 'a' | 'bF' | 'bB' | 'e'): number => {
        const v0 = A[f], v1 = B[f]
        const sig = (v0 - v1) / h
        const sl = i > 0
          ? (r[i - 1][f] - v0) / ((r[i - 1].y - A.y) || 1) : sig
        const sr = i < r.length - 2
          ? (v1 - r[i + 2][f]) / ((B.y - r[i + 2].y) || 1) : sig
        return monoHerm(v0, v1, monoSlope(sl, sig), monoSlope(sig, sr), s, h)
      }
      return {
        y, cx: A.cx + (B.cx - A.cx) * s,
        a: mono('a'), bF: mono('bF'), bB: mono('bB'), e: mono('e'),
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

