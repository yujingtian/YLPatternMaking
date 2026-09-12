// 3D 人台先验常数表（唯一收敛点）。
// 全部为**非引擎数据**：前端体型估计/网格人台的经验常数，按 165/66A
// 女体标定；改这里不需要重打引擎 zip（引擎零体型先验，§10.11）。
// 2026-09-11 换轨收口：旧环模型（BODY_RATIO/SECTION_PRIOR/SAGITTAL/
// FOOT_PRIOR/NAVEL_PRIOR/SKIN_PRIOR + USE_BODYMESH 并存开关）随 VLM 八图
// 验收通过整体退役，人台唯一路径 = 真人网格（BODYMESH_PRIOR）；
// 2026-09-12 裁撤试穿：SOLVER_PRIOR/MESH_PRIOR（PBD 解算/布料网格）与
// 三管高度场常数（thetaBins/rowStep/ringStep/pelvisBelowCrotch/
// legAboveCrotch）随试穿链退役；退役清单与演进史见决策日志。

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

// ---- 真人网格人台（2026-09-11 换轨：MakeHuman CC0 数据 + 自研 TS morph） ----
// 数据链：scripts/vendor_makehuman.py -> public/bodymesh/{base.bin, targets.json}
// （Python 金标 tests/test_vendor_bodymesh.py；口径权威 §10.11「真人网格人台」）。
// 唯一路径：morph + 分段 y-warp 纵向对齐 + 围度闭环标定（渲染 BufferGeometry
// 直出）。
export const BODYMESH_PRIOR = {
  legBelowHem: 2,        // 踝对齐目标 = 脚口下 cm：踝精确落此高度、真脚
                         //（~13cm）整体落踝节点之下
  weightClamp: 2.0,      // 派生径向保形场（thigh±/knee±）外推钳（±）：cos² 场
                         // w=2 仍平滑（legheavy VLM 验收过），可线性外推；
                         // knee± 2026-09-11 起同为派生场（原生弃用理由见
                         // scripts/vendor_makehuman.py derived_knee_targets）
  nativeWeightClamp: 1.0, // MakeHuman 原生 target（waist/hips±）钳（±）：
                         // 预标定/作者化域只到 w=1，外推位移分布未作者化——
                         // 满钳 2.0 实测髋部大转凸包/大腿波浪（2026-09-11
                         // 两轮报障）；钳回作者化域，超域目标残差披露（缺量
                         // 的半径当量 ~毫米级视觉不可见，宁可平滑欠量不要
                         // 外推鼓包）
  calibIters: 6,         // 围度闭环最大迭代轮数
  calibFdStep: 0.1,      // 差分雅可比扰动步（权重单位；方向取该站需求方向）
  calibTol: 0.015,       // 围度相对残差收敛目标（±1.5%）
  calibDamping: 0.8,     // 联合迭代阻尼（measure targets 非正交，hips↔thigh 耦合）
  // thigh 缺省派生（BodyProfile 无大腿围时）：虚拟站点围 = hip × ratio、
  // 高度 = crotch − drop（cm）——沿用旧环模型口径
  thighGirthRatio: 0.62,
  thighStationDrop: 3,
} as const
