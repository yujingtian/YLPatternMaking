// 3D 试穿先验常数表（唯一收敛点）。
// 全部为**非引擎数据**：前端体型估计/放样/解算的经验常数，按 165/66A
// 女体标定；改这里不需要重打引擎 zip（引擎零体型先验，§10.11）。
// 2026-09-11 换轨收口：旧环模型（BODY_RATIO/SECTION_PRIOR/SAGITTAL/
// FOOT_PRIOR/NAVEL_PRIOR/SKIN_PRIOR + USE_BODYMESH 并存开关）随 VLM 八图
// 验收通过整体退役，人台唯一路径 = 真人网格（BODYMESH_PRIOR）；
// 退役清单与演进史见决策日志 §十一。

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
  collideSweeps: 3,      // 碰撞扫描遍数：多管顺序投影非幂等（裆下两腿贴近
                         // 带、骨盆-腿交接带重叠投影），2 遍最坏残差 0.13、
                         // 3 遍 0.09（2026-09-10 环模型实测；网格人台高度场
                         // 并集保守带同理，集成测试 −0.15 容差收纳）
} as const

// ---- 网格 ----
export const MESH_PRIOR = {
  spacing: 1.5,          // cm：内部栅格间距
  boundaryStep: 1.5,     // cm：边界弧长重采样步长
  seamStep: 1.0,         // cm：缝合配对重采样步长
  markStep: 1.0,         // cm：结构线重采样步长
  ringSegments: 48,      // 腰头视觉环带离散段数（buildWaistBand）
} as const

// ---- 真人网格人台（2026-09-11 换轨：MakeHuman CC0 数据 + 自研 TS morph） ----
// 数据链：scripts/vendor_makehuman.py -> public/bodymesh/{base.bin, targets.json}
// （Python 金标 tests/test_vendor_bodymesh.py；口径权威 §10.11「真人网格人台」）。
// 唯一路径：morph + 分段 y-warp 纵向对齐 + 围度闭环标定 + 三管高度场碰撞桥
// （渲染 BufferGeometry 直出、碰撞走 SectionParams.hf 查表，
// seams/pbd/collide 零改动）。
export const BODYMESH_PRIOR = {
  thetaBins: 256,        // 高度场 θ 分辨率（R(y,θ) 表列数）
  rowStep: 0.5,          // 高度场 y 行距 cm（碰撞查表双线性插值）
  ringStep: 2,           // Tube 环采样步 cm（hf 表自带 0.5cm 双线性，环只承担
                         // y 域 + cx 线性插值 + sectionAt 定位）
  pelvisBelowCrotch: 3,  // 骨盆管裆下钳位延伸 cm（切片在该带无盆腔环，沿用
                         // 裆环 R 保守覆盖会阴）
  legAboveCrotch: 7,     // 腿管裆上头带延伸 cm（单环切片按顶点 x 符号分喂
                         // 两腿表，与骨盆管并集保守）
  legBelowHem: 2,        // 腿管底 = 踝节点目标（脚口下 cm）：踝精确落此高度、
                         // 真脚（~13cm）整体在场底之下——布料不可达（脚进
                         // 高度场会以 θ≈0° 假半径 15+ 污染脚口带碰撞）
  weightClamp: 2.0,      // 派生径向保形场（thigh±）外推钳（±）：cos² 场
                         // w=2 仍平滑（legheavy VLM 验收过），可线性外推
  nativeWeightClamp: 1.0, // MakeHuman 原生 target（waist/hips/knee±）钳（±）：
                         // 预标定/作者化域只到 w=1，外推位移分布未作者化——
                         // w≈1.3 实测膝带 +1.4cm 半径局部鼓包、满钳 2.0 髋部
                         // 大转凸包/大腿波浪（2026-09-11 两轮报障）；钳回作者
                         // 化域，超域目标残差披露（缺量的半径当量 ~毫米级
                         // 视觉不可见，宁可平滑欠量不要外推鼓包）
  calibIters: 6,         // 围度闭环最大迭代轮数
  calibFdStep: 0.1,      // 差分雅可比扰动步（权重单位；方向取该站需求方向）
  calibTol: 0.015,       // 围度相对残差收敛目标（±1.5%）
  calibDamping: 0.8,     // 联合迭代阻尼（measure targets 非正交，hips↔thigh 耦合）
  // thigh 缺省派生（BodyProfile 无大腿围时）：虚拟站点围 = hip × ratio、
  // 高度 = crotch − drop（cm）——沿用旧环模型口径
  thighGirthRatio: 0.62,
  thighStationDrop: 3,
} as const
