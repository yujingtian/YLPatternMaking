// SDF 隐式蒙皮（2026-09-09：tubeMesh 三管装配体 -> 单张水密蒙皮）。
// 用户反馈：三管互相穿插只做到几何连通，交线 C0 硬折痕、剪影髋-腿过渡
// 有凹角、明暗交线两侧突变——视觉仍是搭积木。本模块以 buildMannequin
// 环参数（SectionParams + sectionAt 单调样条插值）为单一事实源构造符号
// 距离场：三管二次紧支 smin 软并集（分叉拓扑自动处理、平端盖彻底消失、
// 融合带圆滑），自写查表 marching cubes 三角化成一张水密蒙皮。
// 2026-09-10 第四轮：融合树末端加**场加原语**——双脚（圆角盒对，smin
// 融进同侧踝穹顶）与肚脐（椭球 smax 凹刻）；环模型（y 降序放样）表达
// 不了水平前伸的脚与 θ 局部凹坑的脐，故不走截面环、直接进 SDF 场
// （蒙皮/解耦参照专用，碰撞路径零改动）。
// 纯数值零 three 依赖（node vitest 可测）；碰撞/摆位仍走 sectionAt/
// radiusAt 解析路径（seams/pbd 不动），蒙皮-碰撞差仅在 smin 融合带——
// 融合半径分对校准（blendKPelvisLeg/blendKLegLeg/blendKLegFoot），外凸由
// skin.test.ts 解耦金标按解析并集双测度断言 ≤ garmentGap（见 §10.11）。
import type { FootBox, FootParams, Mannequin, NavelParams, Tube } from './mannequin'
import { sectionAt } from './mannequin'
import { FOOT_PRIOR, NAVEL_PRIOR, SKIN_PRIOR } from './priors'

// ---- 单管闭式伪距离 ----
// 一个 y 切片内该管的全部场参数（cx/a/bF/bB 已含穹顶 sD 缩放；cap 为
// y 向帽下界 dy−L，dy=0 时 −Inf 即无帽）。skinField（逐点）与
// buildSkinMesh（逐层预计算）共用同一切片数学 -> 两路径逐位一致
export interface TubeSlice {
  cx: number; a: number; bF: number; bB: number; e: number
  cap: number
}

// 穹顶切片：y 超出管 y 范围 dy 时，端环半轴乘 sD=√(1−(dy/L)²) 缩放
// （dy→0 处 dsD/dy=0 与柱面 C1；端环收缩成点 = 平端盖彻底消失）。
// 场取 max(d₂, dy−L)：d₂ 是到缩放截面的径向距离、dy−L 是 y 向帽下界，
// 二者均为真距离下界、各自 1-Lipschitz。max 在**零点集邻域**连续（壁面
// 两支均由 d₂ 支配，sD(0)=1）；端平面深部（|d₂|>L）场值有幅度 ≤L 的
// 跳变但符号保持（两支同负），不影响 MC 与梯度法线——注意勿对该场做
// 线搜索求根/Lipschitz 假设的优化（规格原文「dy≥L 返回 dy−L」在远侧向
// 点会从 ρ 跳到 dy−L 产生断崖，且两踝下方两管各返 dy−L 相等、smin 再压
// 会凭空桥出「脚底幻影膜」——已按 max 修正，见决策日志 2026-09-09）
export function tubeSlice(t: Tube, y: number, domeHi: number, domeLo: number): TubeSlice {
  const r = t.rings
  const s = sectionAt(t, y)   // y 超界自动夹端环（单一事实源）
  const yHi = r[0].y, yLo = r[r.length - 1].y
  const dyHi = y - yHi, dyLo = yLo - y
  if (dyHi <= 0 && dyLo <= 0) return { ...s, cap: -Infinity }
  const L = dyHi > 0 ? domeHi : domeLo
  const dy = dyHi > 0 ? dyHi : dyLo
  if (dy >= L) return { cx: s.cx, a: 0, bF: 0, bB: 0, e: s.e, cap: dy - L }
  const sD = Math.sqrt(1 - (dy / L) * (dy / L))
  return { cx: s.cx, a: s.a * sD, bF: s.bF * sD, bB: s.bB * sD, e: s.e, cap: dy - L }
}

// 切片场：超椭圆闭式伪距离（径向斜率 1、零点集精确落环轮廓）。
// 齐次性：q(t·û)=t^e·q(û)，边界半径 = ρ·q(u)^(−1/e)（q 按未归一化
// u=(x−cx,z) 计算），d₂ = ρ − ρ·q^(−1/e) —— 与 radiusAt 同不动点、
// 零迭代（radiusAt 三次迭代收敛 <1e-4，此处精确）。远场短路：ρ−max(半轴)
// 与 cap 都是真值下界，>k（smin 最大窗口半宽）时该管不可能参与融合，
// 直接返回下界跳过 pow（仅影响恒正远区，零点集不受影响）
export function sliceField(sl: TubeSlice, x: number, z: number, k: number): number {
  const ux = x - sl.cx, uz = z
  const rho = Math.hypot(ux, uz)
  const maxAx = Math.max(sl.a, sl.bF, sl.bB)
  if (rho - maxAx > k || sl.cap > k) return Math.max(rho - maxAx, sl.cap)
  // d₂：截面收缩成点（穹顶尖外）时径向距离即 ρ
  const d2 = maxAx <= 1e-9 ? rho
    : rho < 1e-9 ? -Math.min(sl.a, sl.bF, sl.bB)
      : rho - rho * Math.pow(
        Math.pow(Math.abs(ux) / sl.a, sl.e)
        + Math.pow(Math.abs(uz) / (uz >= 0 ? sl.bF : sl.bB), sl.e),
        -1 / sl.e)
  return Math.max(d2, sl.cap)
}

// 二次多项式紧支 smin：|a−b|≥k 严格 =min（单原语站围度零漂移可证的
// 前提）。注意 k/4 只是**场值下压**上界，不是表面位移上界——近切向
// 接触带（两壁梯度近对消）|∇F|≈0.3 会把 k/4 的凹陷放大数倍成表面外凸
// （2026-09-09 四轮证伪原单 k=2 的 k/4<garmentGap 论证），故融合半径
// 分对校准并由 skin.test.ts 解耦金标（解析并集双测度 ≤ garmentGap）
// 锁死。**族锁死**：换指数式（全域支撑）会使所有站点围度漂移不可证，
// 臀站精确支配金标即红（SKIN_PRIOR 注释）
function smin(a: number, b: number, k: number): number {
  // +Inf 哨兵（带外原语跳过）精确恒等 smin(x,+Inf)=x：数学极限虽成立，
  // 多项式代数式在 h=1 处是 b+(a−b) = Inf−Inf = NaN——必须显式短路
  // （2026-09-10 第四轮实测：未短路时带外层全 NaN、MC 出空网格）
  if (a === Infinity) return b
  if (b === Infinity) return a
  const h = Math.max(0, Math.min(1, 0.5 + (0.5 * (b - a)) / k))
  return b + (a - b) * h - k * h * (1 - h)
}

// 紧支 smax（smin 恒等式 smax(a,b,k) = −smin(−a,−b,k)，2026-09-10 第四轮
// 肚脐凹刻引入）：b>0 一侧挖除；|a−b|≥k 严格 max——紧支族不变，脐带外
// 零点集/围度零影响（换非紧支族即破站点围度可证性，同 SKIN_PRIOR 族锁）
function smax(a: number, b: number, k: number): number {
  return -smin(-a, -b, k)
}

// 融合树（skinField 逐点 / marchOnce 逐层共用同一表达式 -> 逐位一致）：
// F = smax( smin(F_骨盆, smin(smin(F_左腿, F_左脚, kLF), smin(F_右腿,
// F_右脚, kLF), kLL), kPL), −F_脐, k脐 )——腿对先融（内腿缝浅沟/病理
// 粗腿重叠带），脚先融进同侧腿（踝穹顶衔接；两脚相距 ≫ kLL+kLF 窗口
// 互不串扰），骨盆再加入腿群（emergence/裆区），肚脐 smax 凹刻收尾
//（2026-09-10 第四轮）。脚/脐均只进蒙皮与解耦参照，碰撞/摆位解析路径
// 零改动（脚顶 < 裤口、脐浅凹，布料不可达）。穹顶配置：骨盆顶
// capDomePelvisTop / 楔底 capDomePelvisBottom / 双腿两端 capDomeLeg
//（腿顶隐藏头穹顶深藏盆壁内，臀站逐射线金标守卫，见 skin.test.ts）
const K_PL = SKIN_PRIOR.blendKPelvisLeg
const K_LL = SKIN_PRIOR.blendKLegLeg
const K_LF = SKIN_PRIOR.blendKLegFoot
const K_FOOT = FOOT_PRIOR.blendKFoot
const K_NAVEL = NAVEL_PRIOR.blend
const K_FAR = Math.max(K_PL, K_LL, K_LF)   // 远场短路阈值（恒 ≥ 各对窗口半宽）

function blendAll(
  fp: number, fl: number, fr: number, footL: number, footR: number,
  nav: number,
): number {
  const legs = smin(smin(fl, footL, K_LF), smin(fr, footR, K_LF), K_LL)
  return smax(smin(fp, legs, K_PL), -nav, K_NAVEL)
}

// ---- 脚/脐场原语（2026-09-10 第四轮，与 mannequin FootParams/NavelParams
// 配对）----
// 圆角盒 SDF（精确距离：外区欧氏模 + 内区最深轴负值，再减圆角）
function boxField(
  b: FootBox, lx: number, ly: number, lz: number, r: number,
): number {
  const qx = Math.abs(lx - b.c[0]) - b.h[0]
  const qy = Math.abs(ly - b.c[1]) - b.h[1]
  const qz = Math.abs(lz - b.c[2]) - b.h[2]
  const out = Math.hypot(Math.max(qx, 0), Math.max(qy, 0), Math.max(qz, 0))
  return out + Math.min(Math.max(qx, Math.max(qy, qz)), 0) - r
}

// 世界 -> 脚局部系（绕 Y 旋转 yaw，原点=踝）；局部 x/z
function footLocal(
  f: FootParams, x: number, z: number,
): { lx: number; lz: number } {
  const c = Math.cos(f.yaw), s = Math.sin(f.yaw)
  const dx = x - f.origin[0], dz = z - f.origin[2]
  return { lx: dx * c - dz * s, lz: dx * s + dz * c }
}

// 单脚场：两圆角盒 smin（kFoot）
function footField(f: FootParams, x: number, y: number, z: number): number {
  const { lx, lz } = footLocal(f, x, z)
  const ly = y - f.origin[1]
  return smin(boxField(f.boxes[0], lx, ly, lz, f.round),
    boxField(f.boxes[1], lx, ly, lz, f.round), K_FOOT)
}

// 单脚原始 min（无 smin）：解耦参照 unionField 专用
function footBoxesMin(f: FootParams, x: number, y: number, z: number): number {
  const { lx, lz } = footLocal(f, x, z)
  const ly = y - f.origin[1]
  return Math.min(boxField(f.boxes[0], lx, ly, lz, f.round),
    boxField(f.boxes[1], lx, ly, lz, f.round))
}

// 肚脐椭球伪 SDF（k0(k0−1)/k1 逼近式：符号精确、表面附近近距）。
// k0>3 紧支返 +Inf：伪 SDF 远场随 k0 线性增长而**低估**真距离（骨盆心
// 实测真距 12.6、伪值 10.9），深内部 −nav > F 时 smax 会取到污染值
// （skinField(0,86,0) = −10.9 ≠ 骨盆 −11.8）破单侧性金标；k0>3 即真距
// ≥ 2×最小半轴 = 1.8 > 2·K脐，smax 恒等带外零影响（marchOnce 的 y 带
// 开关之外的第二道闸，skinField 逐点路径同样受益）
function navelField(n: NavelParams, x: number, y: number, z: number): number {
  const qx = x / n.rx, qy = (y - n.y) / n.ry, qz = (z - n.z) / n.rz
  const k0 = Math.hypot(qx, qy, qz)
  if (k0 > 3) return Infinity
  if (k0 < 1e-9) return -Math.min(n.rx, n.ry, n.rz)
  const k1 = Math.hypot(qx / n.rx, qy / n.ry, qz / n.rz)
  return k1 < 1e-12 ? 0 : (k0 * (k0 - 1)) / k1
}

// 蒙皮场（测试/法线/三角化共用的精确场）
export function skinField(man: Mannequin, x: number, y: number, z: number): number {
  return blendAll(
    sliceField(
      tubeSlice(man.pelvis, y, SKIN_PRIOR.capDomePelvisTop,
        SKIN_PRIOR.capDomePelvisBottom), x, z, K_FAR),
    sliceField(
      tubeSlice(man.legs[0], y, SKIN_PRIOR.capDomeLeg, SKIN_PRIOR.capDomeLeg),
      x, z, K_FAR),
    sliceField(
      tubeSlice(man.legs[1], y, SKIN_PRIOR.capDomeLeg, SKIN_PRIOR.capDomeLeg),
      x, z, K_FAR),
    footField(man.feet[0], x, y, z),
    footField(man.feet[1], x, y, z),
    navelField(man.navel, x, y, z))
}

// 解析并集场（测试参照）：三管 + 四脚盒严格 min = 碰撞/摆位解析路径的
// 几何本体（无融合）。smin ≤ min 恒成立 -> 蒙皮永不陷入并集内部，融合
// 只向外鼓；解耦金标用它度量蒙皮外凸（点法向位移 + 射线首穿差）。脚是
// 向外新几何 -> 必须收编（否则双测度对脚全红）；脐是向内凹刻（蒙皮在
// 并集外侧），不进并集、由脐区豁免带覆盖（skin.test.ts）
export function unionField(man: Mannequin, x: number, y: number, z: number): number {
  return Math.min(
    sliceField(
      tubeSlice(man.pelvis, y, SKIN_PRIOR.capDomePelvisTop,
        SKIN_PRIOR.capDomePelvisBottom), x, z, K_FAR),
    sliceField(
      tubeSlice(man.legs[0], y, SKIN_PRIOR.capDomeLeg, SKIN_PRIOR.capDomeLeg),
      x, z, K_FAR),
    sliceField(
      tubeSlice(man.legs[1], y, SKIN_PRIOR.capDomeLeg, SKIN_PRIOR.capDomeLeg),
      x, z, K_FAR),
    footBoxesMin(man.feet[0], x, y, z),
    footBoxesMin(man.feet[1], x, y, z))
}

export interface SkinMesh {
  positions: Float32Array
  normals: Float32Array    // SDF 数值梯度（融合带 C1 连续——治交线明暗突变）
  indices: Uint32Array
  triangles: number
  spacing: number          // 实际栅格（超预算逐档放粗重跑后）
}

// ---- 自写查表 marching cubes ----
// 裁决（2026-09-09 评审）：three addon 是单位立方体网格（体型 bbox
// 40×130×35cm 细长条浪费 ~10 倍节点）且直出三角汤无法共享顶点做水密
// 金标/光滑法线；marching tetrahedra 三角 ×1.7 烧穿 3 万预算。一致
// 查表 MC + 顶点懒分配在共享栅格边上（预分配边索引 init −1，天然去重
// 且跨胞决策一致）保证闭合流形；歧义胞只夹拓扑不破水密（金标兜底）。
// 符号约定：F≥0 一律判外（含 0），bit=1 为内（F<0）；|F|<1e-12 nudge
// +1e-6 防零面积三角/法线除零
// 表来源：Paul Bourke "Polygonising a scalar field"（公有领域），
// 经 three/examples/jsm/objects/MarchingCubes.js 逐值转录（边表↔三角表
// 256 项交叉自洽脚本核验 0 不一致）；见文件尾 EDGE_TABLE/TRI_TABLE

// 胞角点编号（Bourke 序）：0=(x,y,z) 1=(+x) 2=(+x+y) 3=(+y)
// 4=(+z) 5=(+x+z) 6=(+x+y+z) 7=(+y+z)；12 条胞边 -> 角点对 + 方向
const CELL_EDGES: readonly (readonly [number, number, 0 | 1 | 2])[] = [
  [0, 1, 0], [1, 2, 1], [3, 2, 0], [0, 3, 1],
  [4, 5, 0], [5, 6, 1], [7, 6, 0], [4, 7, 1],
  [0, 4, 2], [1, 5, 2], [2, 6, 2], [3, 7, 2],
]

// 顶点绕向：表原生绕向在「内负外正 + ∇F 外向」约定下法线朝内，
// 统一翻（IN2 金标：三角几何法线·∇F>0 抽样断言锁死，重构勿静默翻转）
const FLIP_WINDING = true

function marchOnce(man: Mannequin, h: number): SkinMesh {
  // ---- bbox：X/Z 全环极值 + 脚盒旋转外接（2026-09-10 第四轮）外扩融合
  // 窗口+2；Y 上扩穹顶长+1.5、下扩 1.5（脚平底贴 man.bottomY，无穹顶；
  // 保证边界场恒正 -> MC 闭合；skin.test.ts 边界格恒正金标守卫）
  let extX = 0, extZ = 0
  for (const t of [man.pelvis, man.legs[0], man.legs[1]]) {
    for (const r of t.rings) {
      extX = Math.max(extX, Math.abs(r.cx) + r.a)
      extZ = Math.max(extZ, r.bF, r.bB)
    }
  }
  // 脚盒：绕 Y 旋转的轴对齐外接保守界（|cos|+|sin| 组合）。X/Z 必须含
  // 盒心偏移 |c|——盒心不在踝原点上（前盒 c2≈12.75），漏掉会把脚尖切出
  // bbox 外 ~2cm：网格在趾尖平面截断、悬挂边破水密（crotch88/hip75×80
  // 实测 46~54 条边=1；标准夹具靠粗骨盆 bB+mXZ 侥幸盖住，2026-09-10 四轮）
  let footYLo = Infinity, footYHi = -Infinity
  for (const f of man.feet) {
    const ca = Math.abs(Math.cos(f.yaw)), sa = Math.abs(Math.sin(f.yaw))
    for (const b of f.boxes) {
      const ex = Math.abs(b.c[0]) + b.h[0] + f.round
      const ez = Math.abs(b.c[2]) + b.h[2] + f.round
      extX = Math.max(extX, Math.abs(f.origin[0]) + ex * ca + ez * sa)
      extZ = Math.max(extZ, Math.abs(f.origin[2]) + ex * sa + ez * ca)
      footYLo = Math.min(footYLo, f.origin[1] + b.c[1] - b.h[1] - f.round)
      footYHi = Math.max(footYHi, f.origin[1] + b.c[1] + b.h[1] + f.round)
    }
  }
  const mXZ = K_FAR + 2
  const xMin = -extX - mXZ, xMax = extX + mXZ
  const zMin = -extZ - mXZ, zMax = extZ + mXZ
  const yMin = man.bottomY - 1.5
  const yMax = man.topY + (SKIN_PRIOR.capDomePelvisTop + 1.5)
  // 脚/脐 y 活动带（带外层跳过点原语求值：传 +Inf 进 smin/smax 为精确
  // 恒等 —— smin(x,+Inf)=x、smax(x,−Inf)=x，值逐位一致，纯性能开关）
  const footBandLo = footYLo - (K_FAR + 1), footBandHi = footYHi + (K_FAR + 1)
  const navBandLo = man.navel.y - man.navel.ry - (K_NAVEL + 1)
  const navBandHi = man.navel.y + man.navel.ry + (K_NAVEL + 1)
  const nx = Math.max(1, Math.ceil((xMax - xMin) / h))
  const ny = Math.max(1, Math.ceil((yMax - yMin) / h))
  const nz = Math.max(1, Math.ceil((zMax - zMin) / h))
  const npX = nx + 1, npY = ny + 1, npZ = nz + 1
  const gx = (i: number) => xMin + i * h
  const gy = (j: number) => yMin + j * h
  const gz = (kk: number) => zMin + kk * h
  const pIdx = (i: number, j: number, kk: number) => i + npX * (j + npY * kk)

  // ---- pass1：逐 y 层预计算三管切片（环线性扫描每层一次而非每体素），
  // 采样场进 Float64（全程 float64，输出才转 Float32）
  const val = new Float64Array(npX * npY * npZ)
  const slicesP: TubeSlice[] = new Array(npY)
  const slicesL: TubeSlice[] = new Array(npY)
  const slicesR: TubeSlice[] = new Array(npY)
  for (let j = 0; j < npY; j++) {
    slicesP[j] = tubeSlice(man.pelvis, gy(j),
      SKIN_PRIOR.capDomePelvisTop, SKIN_PRIOR.capDomePelvisBottom)
    slicesL[j] = tubeSlice(man.legs[0], gy(j),
      SKIN_PRIOR.capDomeLeg, SKIN_PRIOR.capDomeLeg)
    slicesR[j] = tubeSlice(man.legs[1], gy(j),
      SKIN_PRIOR.capDomeLeg, SKIN_PRIOR.capDomeLeg)
  }
  for (let j = 0; j < npY; j++) {
    const yv = gy(j)
    const sp = slicesP[j], sl = slicesL[j], sr = slicesR[j]
    const fOn = yv >= footBandLo && yv <= footBandHi
    const nOn = yv >= navBandLo && yv <= navBandHi
    for (let kk = 0; kk < npZ; kk++) {
      const z = gz(kk)
      const rowBase = npX * (j + npY * kk)
      for (let i = 0; i < npX; i++) {
        const x = gx(i)
        let v = blendAll(sliceField(sp, x, z, K_FAR),
          sliceField(sl, x, z, K_FAR), sliceField(sr, x, z, K_FAR),
          fOn ? footField(man.feet[0], x, yv, z) : Infinity,
          fOn ? footField(man.feet[1], x, yv, z) : Infinity,
          nOn ? navelField(man.navel, x, yv, z) : Infinity)
        if (v > -1e-12 && v < 1e-12) v = 1e-6
        val[rowBase + i] = v
      }
    }
  }

  // ---- pass2：活跃胞查表三角化；顶点懒分配在共享栅格边上
  const ex = new Int32Array(npX * npY * npZ).fill(-1)
  const ey = new Int32Array(npX * npY * npZ).fill(-1)
  const ez = new Int32Array(npX * npY * npZ).fill(-1)
  const edgeArrs = [ex, ey, ez] as const
  const pos: number[] = []
  let vertCount = 0
  const tri: number[] = []
  // 胞角点相对 (i,j,k) 的偏移（Bourke 序）
  const CO = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
    [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]] as const
  const cIdx = new Int32Array(8)
  const cVal = new Float64Array(8)
  const cX = new Float64Array(8), cY = new Float64Array(8), cZ = new Float64Array(8)

  for (let j = 0; j < ny; j++) {
    for (let kk = 0; kk < nz; kk++) {
      for (let i = 0; i < nx; i++) {
        const p0 = pIdx(i, j, kk)
        let cube = 0
        for (let c = 0; c < 8; c++) {
          const [di, dj, dk] = CO[c]
          const g = p0 + di + npX * dj + npX * npY * dk
          cIdx[c] = g
          const v = val[g]
          cVal[c] = v
          if (v < 0) cube |= 1 << c
          cX[c] = gx(i + di); cY[c] = gy(j + dj); cZ[c] = gz(kk + dk)
        }
        const edges = EDGE_TABLE[cube]
        if (edges === 0) continue
        // 12 条边的全局顶点号（懒分配；同栅格边跨胞共享 -> 水密）
        const ev = new Int32Array(12)
        for (let e = 0; e < 12; e++) {
          if (!((edges >> e) & 1)) { ev[e] = -1; continue }
          const [ca, cb, dir] = CELL_EDGES[e]
          const arr = edgeArrs[dir]
          const start = cIdx[ca]
          let vi = arr[start]
          if (vi < 0) {
            const va = cVal[ca], vb = cVal[cb]
            const t = va / (va - vb)   // iso=0；同边同式跨胞一致
            pos.push(cX[ca] + (cX[cb] - cX[ca]) * t,
              cY[ca] + (cY[cb] - cY[ca]) * t,
              cZ[ca] + (cZ[cb] - cZ[ca]) * t)
            vi = vertCount++
            arr[start] = vi
          }
          ev[e] = vi
        }
        const row = cube * 16
        for (let t3 = 0; TRI_TABLE[row + t3] >= 0; t3 += 3) {
          const a = ev[TRI_TABLE[row + t3]]
          const b = ev[TRI_TABLE[row + t3 + 1]]
          const c = ev[TRI_TABLE[row + t3 + 2]]
          // 跳过零面积三角（重复位置点）：保「无向边恰共享 2 次」不变量
          const dup = (p: number, q: number) => {
            const dx = pos[3 * p] - pos[3 * q], dy = pos[3 * p + 1] - pos[3 * q + 1]
            const dz = pos[3 * p + 2] - pos[3 * q + 2]
            return dx * dx + dy * dy + dz * dz < 1e-18
          }
          if (dup(a, b) || dup(b, c) || dup(a, c)) continue
          if (FLIP_WINDING) tri.push(a, c, b)
          else tri.push(a, b, c)
        }
      }
    }
  }

  // ---- 法线：每唯一顶点 skinField 六点中心差分（δ=0.5cm）归一化
  // （F<0 内 -> ∇F 外向 = 几何法线；否决 computeVertexNormals：MC 长条
  // 三角面片噪声且平均窗口抹平融合圆角）；|∇F|<1e-9 鞍点兜底邻面平均
  const d = 0.5
  const nrm = new Float64Array(3 * vertCount)
  const badGrad: number[] = []
  for (let v = 0; v < vertCount; v++) {
    const x = pos[3 * v], y = pos[3 * v + 1], z = pos[3 * v + 2]
    const gxv = (skinField(man, x + d, y, z) - skinField(man, x - d, y, z)) / (2 * d)
    const gyv = (skinField(man, x, y + d, z) - skinField(man, x, y - d, z)) / (2 * d)
    const gzv = (skinField(man, x, y, z + d) - skinField(man, x, y, z - d)) / (2 * d)
    const len = Math.hypot(gxv, gyv, gzv)
    if (len < 1e-9) {
      badGrad.push(v)
      continue
    }
    nrm[3 * v] = gxv / len; nrm[3 * v + 1] = gyv / len; nrm[3 * v + 2] = gzv / len
  }
  if (badGrad.length) {
    // 防御分支：梯度鞍点用邻接三角几何法线平均兜底
    const acc = new Float64Array(3 * vertCount)
    for (let t3 = 0; t3 < tri.length; t3 += 3) {
      const a = tri[t3], b = tri[t3 + 1], c = tri[t3 + 2]
      const ux = pos[3 * b] - pos[3 * a], uy = pos[3 * b + 1] - pos[3 * a + 1]
      const uz = pos[3 * b + 2] - pos[3 * a + 2]
      const vx = pos[3 * c] - pos[3 * a], vy = pos[3 * c + 1] - pos[3 * a + 1]
      const vz = pos[3 * c + 2] - pos[3 * a + 2]
      const fx = uy * vz - uz * vy, fy = uz * vx - ux * vz, fz = ux * vy - uy * vx
      for (const w of [a, b, c]) { acc[3 * w] += fx; acc[3 * w + 1] += fy; acc[3 * w + 2] += fz }
    }
    for (const v of badGrad) {
      const len = Math.hypot(acc[3 * v], acc[3 * v + 1], acc[3 * v + 2])
      if (len < 1e-12) { nrm[3 * v + 1] = 1; continue }
      nrm[3 * v] = acc[3 * v] / len
      nrm[3 * v + 1] = acc[3 * v + 1] / len
      nrm[3 * v + 2] = acc[3 * v + 2] / len
    }
  }

  return {
    positions: new Float32Array(pos),
    normals: new Float32Array(nrm),
    indices: new Uint32Array(tri),
    triangles: tri.length / 3,
    spacing: h,
  }
}

// 蒙皮重建（体型/围度变化时调用，非每帧）：bbox 界定 -> 逐层预采样 ->
// 查表三角化 -> 边去重 -> 梯度法线。三角量超预算时 spacing 逐档
// ×budgetSpacingGrow **循环**重跑至回预算内（至多 budgetMaxRetries 次；
// 单次重跑不闭合——滑杆极值 120/130/80/60 单档后仍 32780>30000），
// 确定性守卫，替代 CI 不可测的计时降档（165/66A 首跑即达标）
export function buildSkinMesh(man: Mannequin): SkinMesh {
  let h = SKIN_PRIOR.spacing
  let mesh = marchOnce(man, h)
  for (let retry = 0; mesh.triangles > SKIN_PRIOR.maxTriangles
    && retry < SKIN_PRIOR.budgetMaxRetries; retry++) {
    h *= SKIN_PRIOR.budgetSpacingGrow
    // eslint-disable-next-line no-console
    console.warn(`[fitting3d] 蒙皮三角 ${mesh.triangles} 超预算 `
      + `${SKIN_PRIOR.maxTriangles}，spacing 放粗至 ${h.toFixed(2)} 重跑`)
    mesh = marchOnce(man, h)
  }
  return mesh
}

// ---- MC 查找表（Paul Bourke 公有领域表，经 three/examples/jsm/objects/
// MarchingCubes.js 逐值转录——其源码把负数排版为「- 1」，提取须剥空白；
// edgeTable 12 位边掩码 / triTable 每行 ≤5 三角、−1 终止；256 项
// 「triTable 引用边 ⊆ edgeTable 位图」脚本交叉核验 0 不一致）----
const EDGE_TABLE = new Int16Array([
  0x0,0x109,0x203,0x30a,0x406,0x50f,0x605,0x70c,0x80c,0x905,0xa0f,0xb06,0xc0a,0xd03,0xe09,0xf00,
  0x190,0x99,0x393,0x29a,0x596,0x49f,0x795,0x69c,0x99c,0x895,0xb9f,0xa96,0xd9a,0xc93,0xf99,0xe90,
  0x230,0x339,0x33,0x13a,0x636,0x73f,0x435,0x53c,0xa3c,0xb35,0x83f,0x936,0xe3a,0xf33,0xc39,0xd30,
  0x3a0,0x2a9,0x1a3,0xaa,0x7a6,0x6af,0x5a5,0x4ac,0xbac,0xaa5,0x9af,0x8a6,0xfaa,0xea3,0xda9,0xca0,
  0x460,0x569,0x663,0x76a,0x66,0x16f,0x265,0x36c,0xc6c,0xd65,0xe6f,0xf66,0x86a,0x963,0xa69,0xb60,
  0x5f0,0x4f9,0x7f3,0x6fa,0x1f6,0xff,0x3f5,0x2fc,0xdfc,0xcf5,0xfff,0xef6,0x9fa,0x8f3,0xbf9,0xaf0,
  0x650,0x759,0x453,0x55a,0x256,0x35f,0x55,0x15c,0xe5c,0xf55,0xc5f,0xd56,0xa5a,0xb53,0x859,0x950,
  0x7c0,0x6c9,0x5c3,0x4ca,0x3c6,0x2cf,0x1c5,0xcc,0xfcc,0xec5,0xdcf,0xcc6,0xbca,0xac3,0x9c9,0x8c0,
  0x8c0,0x9c9,0xac3,0xbca,0xcc6,0xdcf,0xec5,0xfcc,0xcc,0x1c5,0x2cf,0x3c6,0x4ca,0x5c3,0x6c9,0x7c0,
  0x950,0x859,0xb53,0xa5a,0xd56,0xc5f,0xf55,0xe5c,0x15c,0x55,0x35f,0x256,0x55a,0x453,0x759,0x650,
  0xaf0,0xbf9,0x8f3,0x9fa,0xef6,0xfff,0xcf5,0xdfc,0x2fc,0x3f5,0xff,0x1f6,0x6fa,0x7f3,0x4f9,0x5f0,
  0xb60,0xa69,0x963,0x86a,0xf66,0xe6f,0xd65,0xc6c,0x36c,0x265,0x16f,0x66,0x76a,0x663,0x569,0x460,
  0xca0,0xda9,0xea3,0xfaa,0x8a6,0x9af,0xaa5,0xbac,0x4ac,0x5a5,0x6af,0x7a6,0xaa,0x1a3,0x2a9,0x3a0,
  0xd30,0xc39,0xf33,0xe3a,0x936,0x83f,0xb35,0xa3c,0x53c,0x435,0x73f,0x636,0x13a,0x33,0x339,0x230,
  0xe90,0xf99,0xc93,0xd9a,0xa96,0xb9f,0x895,0x99c,0x69c,0x795,0x49f,0x596,0x29a,0x393,0x99,0x190,
  0xf00,0xe09,0xd03,0xc0a,0xb06,0xa0f,0x905,0x80c,0x70c,0x605,0x50f,0x406,0x30a,0x203,0x109,0x0,
])

const TRI_TABLE = new Int8Array([
  -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,0,8,3,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  0,1,9,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,8,3,9,8,1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  1,2,10,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,0,8,3,1,2,10,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  9,2,10,0,2,9,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,2,8,3,2,10,8,10,9,8,-1,-1,-1,-1,-1,-1,-1,
  3,11,2,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,0,11,2,8,11,0,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  1,9,0,2,3,11,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,11,2,1,9,11,9,8,11,-1,-1,-1,-1,-1,-1,-1,
  3,10,1,11,10,3,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,0,10,1,0,8,10,8,11,10,-1,-1,-1,-1,-1,-1,-1,
  3,9,0,3,11,9,11,10,9,-1,-1,-1,-1,-1,-1,-1,9,8,10,10,8,11,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  4,7,8,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,4,3,0,7,3,4,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  0,1,9,8,4,7,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,4,1,9,4,7,1,7,3,1,-1,-1,-1,-1,-1,-1,-1,
  1,2,10,8,4,7,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,3,4,7,3,0,4,1,2,10,-1,-1,-1,-1,-1,-1,-1,
  9,2,10,9,0,2,8,4,7,-1,-1,-1,-1,-1,-1,-1,2,10,9,2,9,7,2,7,3,7,9,4,-1,-1,-1,-1,
  8,4,7,3,11,2,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,11,4,7,11,2,4,2,0,4,-1,-1,-1,-1,-1,-1,-1,
  9,0,1,8,4,7,2,3,11,-1,-1,-1,-1,-1,-1,-1,4,7,11,9,4,11,9,11,2,9,2,1,-1,-1,-1,-1,
  3,10,1,3,11,10,7,8,4,-1,-1,-1,-1,-1,-1,-1,1,11,10,1,4,11,1,0,4,7,11,4,-1,-1,-1,-1,
  4,7,8,9,0,11,9,11,10,11,0,3,-1,-1,-1,-1,4,7,11,4,11,9,9,11,10,-1,-1,-1,-1,-1,-1,-1,
  9,5,4,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,9,5,4,0,8,3,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  0,5,4,1,5,0,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,8,5,4,8,3,5,3,1,5,-1,-1,-1,-1,-1,-1,-1,
  1,2,10,9,5,4,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,3,0,8,1,2,10,4,9,5,-1,-1,-1,-1,-1,-1,-1,
  5,2,10,5,4,2,4,0,2,-1,-1,-1,-1,-1,-1,-1,2,10,5,3,2,5,3,5,4,3,4,8,-1,-1,-1,-1,
  9,5,4,2,3,11,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,0,11,2,0,8,11,4,9,5,-1,-1,-1,-1,-1,-1,-1,
  0,5,4,0,1,5,2,3,11,-1,-1,-1,-1,-1,-1,-1,2,1,5,2,5,8,2,8,11,4,8,5,-1,-1,-1,-1,
  10,3,11,10,1,3,9,5,4,-1,-1,-1,-1,-1,-1,-1,4,9,5,0,8,1,8,10,1,8,11,10,-1,-1,-1,-1,
  5,4,0,5,0,11,5,11,10,11,0,3,-1,-1,-1,-1,5,4,8,5,8,10,10,8,11,-1,-1,-1,-1,-1,-1,-1,
  9,7,8,5,7,9,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,9,3,0,9,5,3,5,7,3,-1,-1,-1,-1,-1,-1,-1,
  0,7,8,0,1,7,1,5,7,-1,-1,-1,-1,-1,-1,-1,1,5,3,3,5,7,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  9,7,8,9,5,7,10,1,2,-1,-1,-1,-1,-1,-1,-1,10,1,2,9,5,0,5,3,0,5,7,3,-1,-1,-1,-1,
  8,0,2,8,2,5,8,5,7,10,5,2,-1,-1,-1,-1,2,10,5,2,5,3,3,5,7,-1,-1,-1,-1,-1,-1,-1,
  7,9,5,7,8,9,3,11,2,-1,-1,-1,-1,-1,-1,-1,9,5,7,9,7,2,9,2,0,2,7,11,-1,-1,-1,-1,
  2,3,11,0,1,8,1,7,8,1,5,7,-1,-1,-1,-1,11,2,1,11,1,7,7,1,5,-1,-1,-1,-1,-1,-1,-1,
  9,5,8,8,5,7,10,1,3,10,3,11,-1,-1,-1,-1,5,7,0,5,0,9,7,11,0,1,0,10,11,10,0,-1,
  11,10,0,11,0,3,10,5,0,8,0,7,5,7,0,-1,11,10,5,7,11,5,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  10,6,5,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,0,8,3,5,10,6,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  9,0,1,5,10,6,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,8,3,1,9,8,5,10,6,-1,-1,-1,-1,-1,-1,-1,
  1,6,5,2,6,1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,6,5,1,2,6,3,0,8,-1,-1,-1,-1,-1,-1,-1,
  9,6,5,9,0,6,0,2,6,-1,-1,-1,-1,-1,-1,-1,5,9,8,5,8,2,5,2,6,3,2,8,-1,-1,-1,-1,
  2,3,11,10,6,5,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,11,0,8,11,2,0,10,6,5,-1,-1,-1,-1,-1,-1,-1,
  0,1,9,2,3,11,5,10,6,-1,-1,-1,-1,-1,-1,-1,5,10,6,1,9,2,9,11,2,9,8,11,-1,-1,-1,-1,
  6,3,11,6,5,3,5,1,3,-1,-1,-1,-1,-1,-1,-1,0,8,11,0,11,5,0,5,1,5,11,6,-1,-1,-1,-1,
  3,11,6,0,3,6,0,6,5,0,5,9,-1,-1,-1,-1,6,5,9,6,9,11,11,9,8,-1,-1,-1,-1,-1,-1,-1,
  5,10,6,4,7,8,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,4,3,0,4,7,3,6,5,10,-1,-1,-1,-1,-1,-1,-1,
  1,9,0,5,10,6,8,4,7,-1,-1,-1,-1,-1,-1,-1,10,6,5,1,9,7,1,7,3,7,9,4,-1,-1,-1,-1,
  6,1,2,6,5,1,4,7,8,-1,-1,-1,-1,-1,-1,-1,1,2,5,5,2,6,3,0,4,3,4,7,-1,-1,-1,-1,
  8,4,7,9,0,5,0,6,5,0,2,6,-1,-1,-1,-1,7,3,9,7,9,4,3,2,9,5,9,6,2,6,9,-1,
  3,11,2,7,8,4,10,6,5,-1,-1,-1,-1,-1,-1,-1,5,10,6,4,7,2,4,2,0,2,7,11,-1,-1,-1,-1,
  0,1,9,4,7,8,2,3,11,5,10,6,-1,-1,-1,-1,9,2,1,9,11,2,9,4,11,7,11,4,5,10,6,-1,
  8,4,7,3,11,5,3,5,1,5,11,6,-1,-1,-1,-1,5,1,11,5,11,6,1,0,11,7,11,4,0,4,11,-1,
  0,5,9,0,6,5,0,3,6,11,6,3,8,4,7,-1,6,5,9,6,9,11,4,7,9,7,11,9,-1,-1,-1,-1,
  10,4,9,6,4,10,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,4,10,6,4,9,10,0,8,3,-1,-1,-1,-1,-1,-1,-1,
  10,0,1,10,6,0,6,4,0,-1,-1,-1,-1,-1,-1,-1,8,3,1,8,1,6,8,6,4,6,1,10,-1,-1,-1,-1,
  1,4,9,1,2,4,2,6,4,-1,-1,-1,-1,-1,-1,-1,3,0,8,1,2,9,2,4,9,2,6,4,-1,-1,-1,-1,
  0,2,4,4,2,6,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,8,3,2,8,2,4,4,2,6,-1,-1,-1,-1,-1,-1,-1,
  10,4,9,10,6,4,11,2,3,-1,-1,-1,-1,-1,-1,-1,0,8,2,2,8,11,4,9,10,4,10,6,-1,-1,-1,-1,
  3,11,2,0,1,6,0,6,4,6,1,10,-1,-1,-1,-1,6,4,1,6,1,10,4,8,1,2,1,11,8,11,1,-1,
  9,6,4,9,3,6,9,1,3,11,6,3,-1,-1,-1,-1,8,11,1,8,1,0,11,6,1,9,1,4,6,4,1,-1,
  3,11,6,3,6,0,0,6,4,-1,-1,-1,-1,-1,-1,-1,6,4,8,11,6,8,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  7,10,6,7,8,10,8,9,10,-1,-1,-1,-1,-1,-1,-1,0,7,3,0,10,7,0,9,10,6,7,10,-1,-1,-1,-1,
  10,6,7,1,10,7,1,7,8,1,8,0,-1,-1,-1,-1,10,6,7,10,7,1,1,7,3,-1,-1,-1,-1,-1,-1,-1,
  1,2,6,1,6,8,1,8,9,8,6,7,-1,-1,-1,-1,2,6,9,2,9,1,6,7,9,0,9,3,7,3,9,-1,
  7,8,0,7,0,6,6,0,2,-1,-1,-1,-1,-1,-1,-1,7,3,2,6,7,2,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  2,3,11,10,6,8,10,8,9,8,6,7,-1,-1,-1,-1,2,0,7,2,7,11,0,9,7,6,7,10,9,10,7,-1,
  1,8,0,1,7,8,1,10,7,6,7,10,2,3,11,-1,11,2,1,11,1,7,10,6,1,6,7,1,-1,-1,-1,-1,
  8,9,6,8,6,7,9,1,6,11,6,3,1,3,6,-1,0,9,1,11,6,7,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  7,8,0,7,0,6,3,11,0,11,6,0,-1,-1,-1,-1,7,11,6,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  7,6,11,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,3,0,8,11,7,6,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  0,1,9,11,7,6,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,8,1,9,8,3,1,11,7,6,-1,-1,-1,-1,-1,-1,-1,
  10,1,2,6,11,7,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,2,10,3,0,8,6,11,7,-1,-1,-1,-1,-1,-1,-1,
  2,9,0,2,10,9,6,11,7,-1,-1,-1,-1,-1,-1,-1,6,11,7,2,10,3,10,8,3,10,9,8,-1,-1,-1,-1,
  7,2,3,6,2,7,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,7,0,8,7,6,0,6,2,0,-1,-1,-1,-1,-1,-1,-1,
  2,7,6,2,3,7,0,1,9,-1,-1,-1,-1,-1,-1,-1,1,6,2,1,8,6,1,9,8,8,7,6,-1,-1,-1,-1,
  10,7,6,10,1,7,1,3,7,-1,-1,-1,-1,-1,-1,-1,10,7,6,1,7,10,1,8,7,1,0,8,-1,-1,-1,-1,
  0,3,7,0,7,10,0,10,9,6,10,7,-1,-1,-1,-1,7,6,10,7,10,8,8,10,9,-1,-1,-1,-1,-1,-1,-1,
  6,8,4,11,8,6,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,3,6,11,3,0,6,0,4,6,-1,-1,-1,-1,-1,-1,-1,
  8,6,11,8,4,6,9,0,1,-1,-1,-1,-1,-1,-1,-1,9,4,6,9,6,3,9,3,1,11,3,6,-1,-1,-1,-1,
  6,8,4,6,11,8,2,10,1,-1,-1,-1,-1,-1,-1,-1,1,2,10,3,0,11,0,6,11,0,4,6,-1,-1,-1,-1,
  4,11,8,4,6,11,0,2,9,2,10,9,-1,-1,-1,-1,10,9,3,10,3,2,9,4,3,11,3,6,4,6,3,-1,
  8,2,3,8,4,2,4,6,2,-1,-1,-1,-1,-1,-1,-1,0,4,2,4,6,2,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  1,9,0,2,3,4,2,4,6,4,3,8,-1,-1,-1,-1,1,9,4,1,4,2,2,4,6,-1,-1,-1,-1,-1,-1,-1,
  8,1,3,8,6,1,8,4,6,6,10,1,-1,-1,-1,-1,10,1,0,10,0,6,6,0,4,-1,-1,-1,-1,-1,-1,-1,
  4,6,3,4,3,8,6,10,3,0,3,9,10,9,3,-1,10,9,4,6,10,4,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  4,9,5,7,6,11,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,0,8,3,4,9,5,11,7,6,-1,-1,-1,-1,-1,-1,-1,
  5,0,1,5,4,0,7,6,11,-1,-1,-1,-1,-1,-1,-1,11,7,6,8,3,4,3,5,4,3,1,5,-1,-1,-1,-1,
  9,5,4,10,1,2,7,6,11,-1,-1,-1,-1,-1,-1,-1,6,11,7,1,2,10,0,8,3,4,9,5,-1,-1,-1,-1,
  7,6,11,5,4,10,4,2,10,4,0,2,-1,-1,-1,-1,3,4,8,3,5,4,3,2,5,10,5,2,11,7,6,-1,
  7,2,3,7,6,2,5,4,9,-1,-1,-1,-1,-1,-1,-1,9,5,4,0,8,6,0,6,2,6,8,7,-1,-1,-1,-1,
  3,6,2,3,7,6,1,5,0,5,4,0,-1,-1,-1,-1,6,2,8,6,8,7,2,1,8,4,8,5,1,5,8,-1,
  9,5,4,10,1,6,1,7,6,1,3,7,-1,-1,-1,-1,1,6,10,1,7,6,1,0,7,8,7,0,9,5,4,-1,
  4,0,10,4,10,5,0,3,10,6,10,7,3,7,10,-1,7,6,10,7,10,8,5,4,10,4,8,10,-1,-1,-1,-1,
  6,9,5,6,11,9,11,8,9,-1,-1,-1,-1,-1,-1,-1,3,6,11,0,6,3,0,5,6,0,9,5,-1,-1,-1,-1,
  0,11,8,0,5,11,0,1,5,5,6,11,-1,-1,-1,-1,6,11,3,6,3,5,5,3,1,-1,-1,-1,-1,-1,-1,-1,
  1,2,10,9,5,11,9,11,8,11,5,6,-1,-1,-1,-1,0,11,3,0,6,11,0,9,6,5,6,9,1,2,10,-1,
  11,8,5,11,5,6,8,0,5,10,5,2,0,2,5,-1,6,11,3,6,3,5,2,10,3,10,5,3,-1,-1,-1,-1,
  5,8,9,5,2,8,5,6,2,3,8,2,-1,-1,-1,-1,9,5,6,9,6,0,0,6,2,-1,-1,-1,-1,-1,-1,-1,
  1,5,8,1,8,0,5,6,8,3,8,2,6,2,8,-1,1,5,6,2,1,6,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  1,3,6,1,6,10,3,8,6,5,6,9,8,9,6,-1,10,1,0,10,0,6,9,5,0,5,6,0,-1,-1,-1,-1,
  0,3,8,5,6,10,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,10,5,6,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  11,5,10,7,5,11,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,11,5,10,11,7,5,8,3,0,-1,-1,-1,-1,-1,-1,-1,
  5,11,7,5,10,11,1,9,0,-1,-1,-1,-1,-1,-1,-1,10,7,5,10,11,7,9,8,1,8,3,1,-1,-1,-1,-1,
  11,1,2,11,7,1,7,5,1,-1,-1,-1,-1,-1,-1,-1,0,8,3,1,2,7,1,7,5,7,2,11,-1,-1,-1,-1,
  9,7,5,9,2,7,9,0,2,2,11,7,-1,-1,-1,-1,7,5,2,7,2,11,5,9,2,3,2,8,9,8,2,-1,
  2,5,10,2,3,5,3,7,5,-1,-1,-1,-1,-1,-1,-1,8,2,0,8,5,2,8,7,5,10,2,5,-1,-1,-1,-1,
  9,0,1,5,10,3,5,3,7,3,10,2,-1,-1,-1,-1,9,8,2,9,2,1,8,7,2,10,2,5,7,5,2,-1,
  1,3,5,3,7,5,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,0,8,7,0,7,1,1,7,5,-1,-1,-1,-1,-1,-1,-1,
  9,0,3,9,3,5,5,3,7,-1,-1,-1,-1,-1,-1,-1,9,8,7,5,9,7,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  5,8,4,5,10,8,10,11,8,-1,-1,-1,-1,-1,-1,-1,5,0,4,5,11,0,5,10,11,11,3,0,-1,-1,-1,-1,
  0,1,9,8,4,10,8,10,11,10,4,5,-1,-1,-1,-1,10,11,4,10,4,5,11,3,4,9,4,1,3,1,4,-1,
  2,5,1,2,8,5,2,11,8,4,5,8,-1,-1,-1,-1,0,4,11,0,11,3,4,5,11,2,11,1,5,1,11,-1,
  0,2,5,0,5,9,2,11,5,4,5,8,11,8,5,-1,9,4,5,2,11,3,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  2,5,10,3,5,2,3,4,5,3,8,4,-1,-1,-1,-1,5,10,2,5,2,4,4,2,0,-1,-1,-1,-1,-1,-1,-1,
  3,10,2,3,5,10,3,8,5,4,5,8,0,1,9,-1,5,10,2,5,2,4,1,9,2,9,4,2,-1,-1,-1,-1,
  8,4,5,8,5,3,3,5,1,-1,-1,-1,-1,-1,-1,-1,0,4,5,1,0,5,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  8,4,5,8,5,3,9,0,5,0,3,5,-1,-1,-1,-1,9,4,5,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  4,11,7,4,9,11,9,10,11,-1,-1,-1,-1,-1,-1,-1,0,8,3,4,9,7,9,11,7,9,10,11,-1,-1,-1,-1,
  1,10,11,1,11,4,1,4,0,7,4,11,-1,-1,-1,-1,3,1,4,3,4,8,1,10,4,7,4,11,10,11,4,-1,
  4,11,7,9,11,4,9,2,11,9,1,2,-1,-1,-1,-1,9,7,4,9,11,7,9,1,11,2,11,1,0,8,3,-1,
  11,7,4,11,4,2,2,4,0,-1,-1,-1,-1,-1,-1,-1,11,7,4,11,4,2,8,3,4,3,2,4,-1,-1,-1,-1,
  2,9,10,2,7,9,2,3,7,7,4,9,-1,-1,-1,-1,9,10,7,9,7,4,10,2,7,8,7,0,2,0,7,-1,
  3,7,10,3,10,2,7,4,10,1,10,0,4,0,10,-1,1,10,2,8,7,4,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  4,9,1,4,1,7,7,1,3,-1,-1,-1,-1,-1,-1,-1,4,9,1,4,1,7,0,8,1,8,7,1,-1,-1,-1,-1,
  4,0,3,7,4,3,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,4,8,7,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  9,10,8,10,11,8,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,3,0,9,3,9,11,11,9,10,-1,-1,-1,-1,-1,-1,-1,
  0,1,10,0,10,8,8,10,11,-1,-1,-1,-1,-1,-1,-1,3,1,10,11,3,10,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  1,2,11,1,11,9,9,11,8,-1,-1,-1,-1,-1,-1,-1,3,0,9,3,9,11,1,2,9,2,11,9,-1,-1,-1,-1,
  0,2,11,8,0,11,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,3,2,11,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  2,3,8,2,8,10,10,8,9,-1,-1,-1,-1,-1,-1,-1,9,10,2,0,9,2,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  2,3,8,2,8,10,0,1,8,1,10,8,-1,-1,-1,-1,1,10,2,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  1,3,8,9,1,8,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,0,9,1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
  0,3,8,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
])
