// 3D 展示先验常数表（唯一收敛点）。2026-09-15 重建一期起解算链已删
// （整裤缝合/worker/PBD 全退役），本表只剩网格、支撑场、静态展示三类；
// SOLVER_PRIOR 族随解算链删除，skin 壳口径移 core.ts（CORE_SKIN）。
// 体型估计（EASE/BODY_*/BODYMESH_PRIOR 标定族）随一期 BodyProfile 链
// 退役不复活——独立原则下人台围度读 bodymesh 切片、衣服尺寸读引擎，
// 互不反推。改这里不需要重打引擎 zip（引擎零体型先验）。

export const MESH_PRIOR = {
  spacing: 1.5,          // cm：内部栅格间距
  boundaryStep: 1.5,     // cm：边界弧长重采样步长
  seamStep: 1.0,         // cm：缝合角色边的重采样步长（缝合链已删，边
                         // 角色表仍在 payload/mesh 层保留，后续重建复用）
  markStep: 1.0,         // cm：结构线重采样步长
} as const

// ---- 支撑半径场（R(y,θ) 查表；从网格截面预计算） ----
// 每行取全部切片环在方向 θ 上的支撑距离（凸上界——腿间/多环并集取
// 最大），保证初始摆位不穿体。
export const FIELD_PRIOR = {
  thetaBins: 256,        // θ 分辨率（查询双线性，环形回绕）
  rowStep: 0.5,          // y 行距 cm
} as const

// ---- 静态旁挂展示（2026-09-15 重建一期：前片 L+R 一对） ----
export const HANG_PRIOR = {
  clearance: 6,          // cm：前片筒与人台之间净空（视图层偏移量由此推导）
  hemLift: 2,            // cm：显示层整体抬高（纸样 hem 站 y=0 恰落地，脚口
                         // 边与地面格网线共面打架——用户截图裤脚「白色交叉
                         // 线」观感；抬离地面亦更贴近真实悬挂陈列）
  garmentGap: 1.2,       // cm：摆位径向松量（placePoint 半径 = 场 + 本值）。
                         // 解算时代实测值原样沿用：贴皮起摆会让大量粒子
                         // 立即进入接触壳（下垂解算起步即接触，见 DRAPE）
} as const

// ---- 平铺验证展示（2026-09-15 重建三期回落：用户判定悬挂渲染下裁片
// 形状异常，先平铺对照 2D 裁片 SVG 定位问题层；悬挂链常数保留上方 ----
export const FLAT_PRIOR = {
  clearance: 6,          // cm：平铺片与人台净空（旁挂偏移由此推导）
  gap: 4,                // cm：L/R 两片间距（前中边相对，拼近整前片观感）
  rowGap: 6,             // cm：裁片行距（每种裁片一行，行式布局）
  lift: 2,               // cm：显示层离地高度（防与地面格网共面打架，
                         // 同 hemLift 理由）
} as const

// ---- 引力下垂解算（2026-09-15 重建二期：用户口径「裤子的下垂要符合
// 地球引力」+ 同日拍板「前中缝合」。主线程轻量 verlet——距离/弯曲约束
// + 前中缝合对（L/R rise 链镜像配对）+ 撑型芯径向碰撞 + 腰口全向 pin，
// 无跨片装配缝合/无 worker/无 BVH。数值继承已删 SOLVER_PRIOR
// （git d784de1，整裤标定值）——单片地形更温和，旧值直接起步；
// 若不 settle 按旧方法论调 damping/friction，勿动 dt/substeps 结构） ----
export const DRAPE_PRIOR = {
  gravity: -980,         // cm/s²（地球引力 9.8 m/s²，纸样系 Y 向上）
  damping: 0.985,        // 速度衰减/步
  dt: 1 / 60,            // 单步时长 s
  substeps: 3,           // 帧内子步
  iterations: 6,         // 每子步约束迭代（Gauss-Seidel）
  bendStiffness: 0.3,    // 弯曲刚度（dist 全刚 1.0 对照）
  seamStiffness: 1.0,    // 前中缝合约束刚度（L/R rise 链镜像配对 rest=0，
                         // 2026-09-15 用户拍板「前片先将前中缝合在一起」；
                         // 值继承旧 SOLVER_PRIOR.seamStiffness）
  friction: 0.8,         // 接触摩擦：碰撞推出时 prev 向 pos 混合的比例——
                         // 旧链教训：摩擦 0.5 在撑型芯上周向慢转不锚（地板
                         // ~9 永不收敛），0.8 + SEG64 芯实测收敛
  settleSpeed: 0.8,      // cm/s：均速低于此视为静止
  settleFrames: 30,      // 连续静止帧数 -> settled
  maxFrames: 600,        // 帧数封顶（兜底）：超限取当前帧出 settled
} as const
