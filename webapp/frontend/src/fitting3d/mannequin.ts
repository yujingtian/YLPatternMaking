// 人台适配层：三管截面参数模型（骨盆 + 左右腿）+ sectionAt/radiusAt
// 解析查询。消费方 = seams（摆位/腰头环带）、pbd/collide（碰撞）、视图
// （topY/bottomY 落格网）——本文件是它们的稳定契约面。
// 数据源（2026-09-11 换轨，唯一路径）：bodymesh/build.ts 的 buildMeshMannequin
// ——真人网格 morph + 对齐后抽三管高度场 R(y,θ)，经 SectionParams.hf 柄
// 注入本层；radiusAt 短路查表返回裸 R，超椭圆解析式仅测试夹具等无 hf
// 路径消费。渲染不走本层（sourceMesh 直出 BufferGeometry）。
// 纯几何模块：不依赖 three，渲染/碰撞共用同一组截面参数。
export interface SectionParams {
  y: number
  a: number    // X 半宽（hf 路径退为填充值，仅供兜底）
  bF: number   // +Z 前半深（同上）
  bB: number   // −Z 后半深（同上）
  e: number    // 超椭圆指数（同上）
  cx: number
  // 网格人台高度场柄：给 (查询 y, θ=atan2(dx,dz)) 返回**裸 R**；存在时
  // radiusAt 短路查表（表内双线性）。θ 口径与 seams/collide 的单位方向
  // (sinθ,cosθ) 一致；skin 余量由 collideOne 自加
  hf?: (y: number, th: number) => number
}

// 管段：按 y 降序的截面环（碰撞插值 + 管域门控共用）
export interface Tube {
  rings: SectionParams[]
}

export interface Mannequin {
  pelvis: Tube
  legs: [Tube, Tube]   // [wearer 左(−X), 右(+X)]
  topY: number
  bottomY: number      // 站立地面（= 对齐后脚底；格网/落地参照）
  // 网格人台源网格：渲染直出 BufferGeometry；碰撞/摆位走上方三管高度场
  sourceMesh?: { positions: Float32Array; indices: Uint32Array }
}

// 单调三次 Hermite 区间求值（sectionAt 专用，免分配）。
// s∈[0,1] 自 y0 降参至 y1（h = y0−y1），结点导数 m 为 dv/dy：
// v(s) = h00·v0 − h·m0·h10 + h01·v1 − h·m1·h11（标准 Hermite 基）
function monoHerm(
  v0: number, v1: number, m0: number, m1: number, s: number, h: number,
): number {
  const s2 = s * s, s3 = s2 * s
  return (2 * s3 - 3 * s2 + 1) * v0 - h * m0 * (s3 - 2 * s2 + s)
    + (-2 * s3 + 3 * s2) * v1 - h * m1 * (s3 - s2)
}

// 单调样条结点导数（Fritsch–Carlson 型）：相邻区间割线变号（局部极值）
// 取 0——平滑峰/谷无过冲；否则同号限幅 |m| ≤ 3×min(|σL|,|σR|) 且 ≤ 均值
// -> 区间内无过冲、|v'| ≤ 3×局部割线
function monoSlope(sl: number, sr: number): number {
  if (sl * sr <= 0) return 0
  const sg = sl > 0 ? 1 : -1
  return sg * Math.min(3 * Math.abs(sl), 3 * Math.abs(sr),
    (Math.abs(sl) + Math.abs(sr)) / 2)
}

// y 处截面参数（夹取到端环）。a/bF/bB/e 单调样条插值（环间线性折点会
// 被碰撞投影如实放大成台阶；Hermite 在环上精确过点）；cx 保持线性——
// 碰撞路径 Lipschitz 论证前提，勿顺手样条化。hf 柄原样传播（y 用查询值）
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
        hf: A.hf,
      }
    }
  }
  return last
}

// 方向 (dx,dz) 必须为单位向量（相对管中心），返回该方向上的体表半径；
// 非单位输入返回的是使 r·(dx,dz) 落界的缩放倍数（仅供内部迭代用），
// 调用方不得依赖——collide 曾因此把穿透判据退化成 dist ≥ R/dist + skin。
// hf 路径：θ 由单位方向复原（dx=sinθ、dz=cosθ），表内双线性，返回裸 R；
// 解析路径：超椭圆迭代缩放法 f(r) 随 r 单调 ^e，r ← r·f^{-1/e} 三次收敛
export function radiusAt(
  s: SectionParams, dx: number, dz: number,
): number {
  if (s.hf) return s.hf(s.y, Math.atan2(dx, dz))
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
