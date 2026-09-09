// 3D 试穿先验常数表（唯一收敛点）。
// 全部为**非引擎数据**：前端体型估计/放样/解算的经验常数，按 165/66A
// 女体标定；改这里不需要重打引擎 zip（引擎零体型先验，§10.11）。

// ---- 体型默认估计（成衣围 -> 人体围的先验松量，cm） ----
// 用户口径 2026-09-09：成衣量含调节量不能当人体量；此表仅生成「估计值」
// 默认，用户可在体型设置中改成真实测量值
export const EASE_PRIOR = {
  waist: 1.5,
  hip: 5,
  thigh: 4,
  knee: 3,
} as const

// 估计下限：人体围 >= 0.85 × 成衣围（防负松量翻车出怪体型）
export const BODY_MIN_RATIO = 0.85

// ---- 体型比例（缺省站点补全） ----
export const BODY_RATIO = {
  // 体型缺大腿围：虚拟站点围 = hip × ratio、高度 = crotch − 3cm
  thighGirthRatio: 0.62,
  thighStationDrop: 3,
  // 脚口以下腿延伸（cm）：锥缩到 ankle = hem 围 × ratio（踝部无成衣对应）
  legExtendBelow: 8,
  ankleRatio: 0.72,
  // 骨盆管在分叉高（crotch）处的围 = hip × ratio（裆部分叉收细）
  crotchGirthRatio: 0.94,
  // 两腿管中心间距 = hip × ratio（左右各半，165/66A 约 ±9.9cm）
  legCenterRatio: 0.11,
  // 腰上躯干延伸（cm）与顶围收细比
  torsoExtend: 18,
  torsoTopRatio: 0.92,
  // ---- 互嵌接合（2026-09-09 评审方案1：消除骨盆/大腿分体感） ----
  // 腿顶上插高度：腿管顶 y = min(crotch + 此值, hip − 1)，顶盖藏入骨盆
  // 管内（165/66A → 84 = hip−2，不越过臀峰，emergence 带只有 78→81 一段）
  legRiseAboveCrotch: 6,
  // 腿隐藏头围 = hip × 此值（挂 hip 不挂 thigh：粗腿/缺省腿围不放大隐藏
  // 头）。注意容纳能力没有按臀站点算出的常量余量——受力环在裆上方（骨盆
  // 围 ≈0.94×hip，腰臀差大时 CR 欠冲更低），containment 由 mannequin 逐环
  // k=min(三轴) 等比收缩闭式保证，放不下时预检整段降级放弃上插
  legTopGirthRatio: 0.30,
  // 藏盖径向余量 m：aP≈15 时 ≈0.6cm，覆盖 CR 站点间过冲（81 环需
  // 0.641 截顶）/ 4cm 环距插值误差 ≤0.15 / float32 量化
  embedMarginRatio: 0.04,
  // 骨盆楔下探深度：楔底 y = crotch − 此值，有效会阴支撑带 (crotch−2.5,
  // crotch) 恰覆盖前后浪落脚（fixture 后浪尖 77.04 落带内）
  wedgeDropBelowCrotch: 5,
  // 楔底围 = hip × 此值（165/66A → 27cm、a=4.577，横前后向均退入两腿壁内）
  wedgeBottomGirthRatio: 0.30,
} as const

// ---- 截面形状（超椭圆 |x/a|^e + |z/b|^e = 1；bF 前 +Z / bB 后 −Z） ----
export const SECTION_PRIOR: Record<string, {
  e: number       // 超椭圆指数（2=椭圆，>2 更方）
  depth: number   // bF/a 前后平均深宽比
  backBias: number // bB/bF 后凸偏置（臀 1.12 表臀凸）
}> = {
  waist: { e: 2.6, depth: 0.75, backBias: 1.0 },
  hip: { e: 2.3, depth: 0.78, backBias: 1.12 },
  default: { e: 2.4, depth: 0.85, backBias: 1.0 },
  knee: { e: 2.5, depth: 0.92, backBias: 1.0 },
}

// ---- 解算（PBD） ----
export const SOLVER_PRIOR = {
  gravity: -980,        // cm/s²
  damping: 0.985,       // 速度衰减/步
  dt: 1 / 60,           // 单步时长 s
  substeps: 3,          // rAF 帧内子步
  iterations: 6,        // 每子步约束迭代（Gauss-Seidel）
  collisionSkin: 0.3,   // cm：布料-人台皮肤厚度
  friction: 0.5,        // 碰撞切向摩擦（0~1）
  pinWeight: 0.9,       // 腰口 pin 权重（<1 防整裤刚度锁死）
  seamStiffness: 1.0,   // 缝合约束刚度
  stretchStiffness: 1.0,
  bendStiffness: 0.3,
  settleSpeed: 0.8,      // cm/s：均速低于此视为静止
  settleFrames: 30,      // 连续静止帧数 -> settled
  preRelaxIters: 200,    // 冷启动预松弛迭代
  garmentGap: 1.2,       // cm：初始摆位径向松量（贴终态，收敛快）
  collideSweeps: 2,      // 碰撞扫描遍数：互嵌交叠带（三管共覆盖 y 段）
                         // 顺序投影非幂等，单遍残差最坏 14.7cm、双遍归零
} as const

// ---- SDF 蒙皮（2026-09-09：tubeMesh 三管装配体 -> 单张水密隐式蒙皮） ----
// 渲染层专用；碰撞/摆位仍走 sectionAt/radiusAt 解析路径（seams/pbd 不动），
// 两者差异仅在 smin 融合带。外凸界由 skin.test.ts 解耦金标按**解析并集**
// 双测度断言 ≤ SOLVER_PRIOR.garmentGap（并集表面点法向外凸 + 腿心/轴心
// 射线首穿−并集末次出射），实测最坏 0.81/0.76，布料不可见
export const SKIN_PRIOR = {
  // smin 融合半径 cm，**分对**（2026-09-09 四轮：原单 k=2 被对抗审查证伪
  // ——k/4 只是场值下压上界不是表面位移上界，裆区骨盆楔前壁与对侧腿前
  // 内壁近切向接触带 |∇F|≈0.3，凹陷被放大成 +1.66cm 射线外凸 @165/66A
  // 腿心 y=75，超 garmentGap=1.2）。**族锁死**：必须紧支多项式 smin（指数
  // 式全域支撑使站点围度漂移不可证，单原语站精确支配金标兼作防回退守卫
  // ——换 smin 族即红）；k 取值由解耦金标锁死（抬升即红），7 夹具实测：
  // 点法向外凸 ≤0.81、射线外凸 ≤0.76
  blendKPelvisLeg: 0.75,  // 骨盆↔腿群（emergence/裆区）：切向放大带所在，
                          // 主校准对象；kPL=1 时瘦小体型裆侧射线外凸已至
                          // 1.04、1.25 时 1.24 超 garmentGap
  blendKLegLeg: 1.0,      // 腿↔腿（内腿缝浅沟 + 病理粗腿重叠带）：kLL=2 时
                          // hip75×thigh80 内壁融合外凸 1.62；1.0 时 0.80。
                          // 165/66A 内腿缝 1.84cm 中点场 0.92−0.25=0.67>0
                          // 不桥接、谷成浅沟
  // 躯干顶穹顶长 cm：116 顶环（围 60.7）平盘在斜 45° 机位显突兀；只影响
  // y>topY，站点围度零漂移
  capDomePelvisTop: 5,
  // 骨盆楔底穹顶长 cm：藏两腿间防平底幅从腿缝透出
  capDomePelvisBottom: 2.5,
  // 腿管两端穹顶长 cm：踝圆头断茬替代平切；腿顶隐藏头穹顶在骨盆
  // containment 内不可见（165/66A 臀站 86 处缩到 0.6×a=2.69，骨盆壁场
  // −2.66、腿群值 2.66−kLL/4=2.41 ≥ kPL 为精确 min）；降级体型（无上插）
  // 侧伸 ~1cm 融成大转子凸
  capDomeLeg: 2.5,
  // MC 栅格 cm：1.84cm 裆缝≈1.8 格可分辨；~22 万格、名义三角 2.6~3.3 万
  spacing: 1.0,
  // 三角预算守卫：超出即 spacing 逐档 ×budgetSpacingGrow（至多
  // budgetMaxRetries 次）整管线重跑（确定性守卫，替代不可测的计时降档；
  // 165/66A 首跑即达标，病理/滑杆极值 1~2 档收敛，循环保证恒回预算内）
  maxTriangles: 30000,
  budgetSpacingGrow: 1.15,
  budgetMaxRetries: 5,
  // 单原语站（腰/臀/膝/脚口）场级周长容差：理论漂移 0，纯护栏带
  girthTolStation: 0.005,
  // thigh 站容差：融合带实测漂移（kPL=0.75 裆侧鼓包 ≤0.23），留余量
  girthTolThigh: 0.02,
} as const

// ---- 网格 ----
export const MESH_PRIOR = {
  spacing: 1.5,          // cm：内部栅格间距
  boundaryStep: 1.5,     // cm：边界弧长重采样步长
  seamStep: 1.0,         // cm：缝合配对重采样步长
  markStep: 1.0,         // cm：结构线重采样步长
  ringSegments: 48,      // 人台截面环离散段数
} as const
