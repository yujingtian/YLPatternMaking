// 支撑半径场 + 静态摆位（2026-09-15 重建一期：前片 L+R 一对；2026-09-16
// 后身缝合起 back 同款后扇区）。
// R(y,θ) 表：对网格逐水平行切片，取全部切片环在方向 θ 上的支撑距离
// （凸上界）——多环（两腿）与并集保守带自动取最大；保证初始摆位不
// 穿体、无腿间缝隙退化。重建一期场从撑型芯（core.ts）建，人台出圈。
// 摆位约定：position = (r·sinθ, y, r·cosθ)，θ=0 前中(+Z)、90°=
// wearer 右(+X)、±180° 后中(−Z)；as-drafted 前片 = 左半扇区 [−90°,0°]、
// 后片 = 左半扇区 [−180°,−90°]，右半均镜像 θ→−θ。y = 纸样高
// （纸样系 identity，无 warp）。
import { sliceLoops } from '../bodymesh/slice'
import { CORE_SKIN, type LegAxis } from './core'
import { DRESSING_PRIOR, DRAPE_PRIOR, FIELD_PRIOR, HANG_PRIOR } from './priors'

// 行截面环（八期碰撞用）：行 y 处网格切片的闭环点列 + 质心/包围半径
// （quick reject）。躯干行 1 环、腿行 2 环（左右腿管）
export interface SliceRing {
  pts: Float64Array    // 2P 平铺 [x0,z0,...]（闭合，尾接首）
  cx: number           // 质心 x（环归属判据同 bodymesh/slice）
  cz: number           // 质心 z（外法线定向）
  r: number            // 质心包围半径（quick reject）
}

export class BodyField {
  // 行闭弦周长惰性缓存（rowPerimeter 用；行索引 → 值，缺项 = 未算）
  private readonly perimCache = new Map<number, number>()

  constructor(
    readonly table: Float32Array,   // rows × thetaBins
    readonly rows: number,
    readonly rowStep: number,
    readonly thetaBins: number,
    readonly slices: SliceRing[][] = [],   // 行 → 截面环（碰撞截面；缺省空=纯场表用）
    readonly yMin = 0,             // 行 0 对应的 y（2026-09-18 脚碰撞修复：穿台
                                   // 锚定下移后脚成纸样负 y，行表须下探到脚底；
                                   // 缺省 0 = 旁挂芯场/合成场老口径字节等价）
  ) {}

  /** 全表最大支撑半径（悬挂展示算裤筒旁置偏移用：人台 +X 侧占位上界） */
  get maxRadius(): number {
    let m = 0
    for (let i = 0; i < this.table.length; i++) {
      if (this.table[i] > m) m = this.table[i]
    }
    return m
  }

  /** 行截面环（y 夹取到表域；无截面行返回空数组） */
  loopsAt(y: number): SliceRing[] {
    const r = Math.max(0, Math.min(this.rows - 1,
      Math.round((y - this.yMin) / this.rowStep)))
    return this.slices[r] ?? []
  }

  /** 行截面环闭弦周长合计（2026-09-23 P1 挂胯判据）：行夹取同 loopsAt，
   * Σ 该行全部环 pts 闭弦长（躯干行单环；多环防御性求和），按行索引惰性
   * 缓存。空行返回 0 → 0 ≥ C×(1+jamMargin) 恒 false = 无几何信息不拦
   * （安全缺省）。弦 vs 弧差 ~0.1% 量级，远小于挂胯余量 2% */
  rowPerimeter(y: number): number {
    const r = Math.max(0, Math.min(this.rows - 1,
      Math.round((y - this.yMin) / this.rowStep)))
    const hit = this.perimCache.get(r)
    if (hit !== undefined) return hit
    let s = 0
    for (const ring of this.slices[r] ?? []) {
      const n = ring.pts.length / 2
      for (let k = 0; k < n; k++) {
        const a = 2 * k, b = 2 * ((k + 1) % n)
        s += Math.hypot(ring.pts[b] - ring.pts[a], ring.pts[b + 1] - ring.pts[a + 1])
      }
    }
    this.perimCache.set(r, s)
    return s
  }

  radiusAt(y: number, th: number): number {
    // y 夹取（腰上无几何/脚底下沿用端行），行双线性
    const rr = Math.max(0, Math.min(this.rows - 1.0001,
      (y - this.yMin) / this.rowStep))
    const r0 = Math.floor(rr), fr = rr - r0
    const r1 = Math.min(this.rows - 1, r0 + 1)
    // θ 环形双线性（bin 中心约定 (b+0.5)·Δ）
    const delta = (2 * Math.PI) / this.thetaBins
    let t = (th / delta) - 0.5
    t = ((t % this.thetaBins) + this.thetaBins) % this.thetaBins
    const b0 = Math.floor(t), fb = t - b0
    const b1 = (b0 + 1) % this.thetaBins
    const row0 = r0 * this.thetaBins, row1 = r1 * this.thetaBins
    const v00 = this.table[row0 + b0], v01 = this.table[row0 + b1]
    const v10 = this.table[row1 + b0], v11 = this.table[row1 + b1]
    return (v00 * (1 - fb) + v01 * fb) * (1 - fr)
      + (v10 * (1 - fb) + v11 * fb) * fr
  }
}

// 从（morph 后）人台网格建场：逐行切片，全部环的点做方向支撑最大值
// （场表 = 摆位半径口径），同时留存行截面环（drape 截面碰撞口径——
// 两腿分离芯的腿间空隙只有截面/表面碰撞能留白，径向场是星形实心）。
// 一次性 ~几十 ms，只在建衣/重穿时跑
export function buildBodyField(
  positions: Float32Array, indices: Uint32Array, yMin = 0,
): BodyField {
  const { thetaBins, rowStep } = FIELD_PRIOR
  let maxY = -Infinity
  for (let i = 1; i < positions.length; i += 3) {
    if (positions[i] > maxY) maxY = positions[i]
  }
  // 行 r 高 = yMin + r·rowStep（yMin<0 时行表下探覆盖脚部负 y 域；缺省 0
  // = 老口径字节等价）
  const rows = Math.max(2, Math.floor((maxY - yMin) / rowStep) + 1)
  const table = new Float32Array(rows * thetaBins)
  const slices: SliceRing[][] = []
  // 方向单位向量预表（bin 中心）
  const sinT = new Float32Array(thetaBins), cosT = new Float32Array(thetaBins)
  for (let b = 0; b < thetaBins; b++) {
    const th = ((b + 0.5) / thetaBins) * 2 * Math.PI
    sinT[b] = Math.sin(th)
    cosT[b] = Math.cos(th)
  }
  for (let r = 0; r < rows; r++) {
    const y = yMin + r * rowStep
    const base = r * thetaBins
    const rings: SliceRing[] = []
    for (const loop of sliceLoops(positions, indices, y)) {
      if (!loop.closed) continue          // 撕裂兜底：碎片环不进碰撞
      const pts = new Float64Array(2 * loop.pts.length)
      let cz = 0
      for (let k = 0; k < loop.pts.length; k++) {
        pts[2 * k] = loop.pts[k].x
        pts[2 * k + 1] = loop.pts[k].z
        cz += loop.pts[k].z
      }
      cz /= loop.pts.length
      let rMax = 0
      for (let k = 0; k < loop.pts.length; k++) {
        rMax = Math.max(rMax, Math.hypot(
          pts[2 * k] - loop.cx, pts[2 * k + 1] - cz))
      }
      rings.push({ pts, cx: loop.cx, cz, r: rMax })
      for (const p of loop.pts) {
        for (let b = 0; b < thetaBins; b++) {
          const v = p.x * sinT[b] + p.z * cosT[b]
          if (v > table[base + b]) table[base + b] = v
        }
      }
    }
    slices.push(rings)
  }
  return new BodyField(table, rows, rowStep, thetaBins, slices, yMin)
}

export type PieceKey = 'front' | 'back'
export type Side = 'L' | 'R'

// 点在截面环组内（射线法，取向无关；任一环内即并集内）——drape 碰撞
// 与金标穿透查验共用
export function pointInRings(x: number, z: number, rings: SliceRing[]): boolean {
  for (const ring of rings) {
    const n = ring.pts.length / 2
    let inside = false
    for (let i = 0, j = n - 1; i < n; j = i++) {
      const xi = ring.pts[2 * i], zi = ring.pts[2 * i + 1]
      const xj = ring.pts[2 * j], zj = ring.pts[2 * j + 1]
      if ((zi > z) !== (zj > z)
        && x < ((xj - xi) * (z - zi)) / (zj - zi) + xi) {
        inside = !inside
      }
    }
    if (inside) return true
  }
  return false
}

// 单顶点摆位：纸样全局 2D (x,y) -> 3D。90° 扇区包裹（t = (x−xMin)/
// (xMax−xMin) 归一，两片 x 域同构：xMin = 侧缝、xMax = 中缝端）：
//   front 前扇区（旧 placePoint 原口径）：L 半片 θ 从 −90°（侧缝、
//     wearer 左）线性推进到 0°（前中 +Z），R 半片镜像 θ→−θ；
//   back 后扇区（2026-09-16 后身缝合）：L 半片 θ 从 −90° 退到 −180°
//     （后中 −Z），R 半片镜像 θ→−θ——后中 cb 缝对在 θ=±180° 闭合，
//     侧缝两扇区各归 ±90°，穿着拓扑同构（前中/后中相对、侧缝相邻）。
// 摆位半径 = 支撑场 + garmentGap（径向松量起步，口径见 priors）
export function placePoint(
  key: PieceKey, side: Side, x: number, y: number,
  xMin: number, xMax: number, field: BodyField,
): [number, number, number] {
  const t = Math.max(0, Math.min(1, (x - xMin) / (xMax - xMin || 1)))
  let th = -Math.PI / 2 + (Math.PI / 2) * t
  if (key === 'back') th = -Math.PI / 2 - (Math.PI / 2) * t
  if (side === 'R') th = -th
  const r = field.radiusAt(y, th) + HANG_PRIOR.garmentGap
  return [r * Math.sin(th), y, r * Math.cos(th)]
}

// 初始穿透统计（M0 验收）：粒子方向上的支撑半径 vs 当前径向距离，
// dist < r − skin 即穿透
export function penetrationStats(
  pos: Float32Array, field: BodyField, skin: number,
): { count: number; worst: number } {
  let count = 0, worst = 0
  for (let i = 0; i < pos.length; i += 3) {
    const x = pos[i], y = pos[i + 1], z = pos[i + 2]
    const dist = Math.hypot(x, z)
    if (dist < 1e-9) continue
    const r = field.radiusAt(y, Math.atan2(x, z))
    const d = dist - (r - skin)
    if (d < 0) {
      count++
      if (-d > worst) worst = -d
    }
  }
  return { count, worst }
}

// ---- 穿台（2026-09-18）：人台侧几何原语。碰撞体 = 人台切片环场
// （用户拍板口径），旁挂口径不动（芯锚纸样围度照旧）----

// 整组 Y 平移（世界→纸样系 frame 锚定）：θ 两系同构（头注），锚定只需
// Y 平移（人台腰地标 ↔ 纸样腰站 y），1:1 cm 不缩放
export function shiftPositionsY(
  positions: Float32Array, dy: number,
): Float32Array {
  const out = new Float32Array(positions.length)
  for (let i = 0; i < positions.length; i += 3) {
    out[i] = positions[i]
    out[i + 1] = positions[i + 1] + dy
    out[i + 2] = positions[i + 2]
  }
  return out
}

// 最近截面环边界 + 外法线（drape.collide 与穿台裆探针/终态穿透扫共口径，
// 2026-09-18 从 collide 内联扫描提取）：跨全部环找最近边界段；margin =
// quick reject 包围圆余量（collide 传 CORE_SKIN；探针要量间隙须放大）。
// null = 全部环被包围圆 quick reject。性能口径：Math.hypot 慢一个量级，用 sqrt。
// out 出参（2026-09-23 无损提速 1b）：命中时复用调用方 RingHit 对象逐次
// 消灭分配（collide/probeCrotch/report/computeHeat 单线程串行调用，安全；
// 未命中返回 null，out 不动）
export interface RingHit {
  d: number              // 到最近边界距离（≥0）
  px: number; pz: number // 边界最近点
  nx: number; nz: number // 外法线（段垂线，背离环质心）
}
// ---- 角度分箱（2026-09-23 无损提速 1b）：精确剪枝取代逐段全扫 ----
// 环段按「弦中点方位角」入 RING_BINS 扇区箱（模块级 WeakMap 惰性构建——
// SliceRing 内容在 BodyField 生命周期内不变）；查询自所在箱向两侧交替
// 外扩，以「无限楔距离下界」整箱剪枝：段沿其走向的方位角单调连续（弦
// 中点角落在段角域内），段覆盖域 ⊂ 以中点角为中心的 [±span/2] 区间，
// span ≤ slack（环内最大段角跨度）→ 箱内段全部位于方位角
// [binCenter − (Δ+slack)/2, binCenter + (Δ+slack)/2] 的无限楔内；楔内任
// 意点 p 满足 |q−p| ≥ |q−c|·sin(clamp(φ))（φ = 查询角到箱角域的最近角
// 距），下界**严格大于**当前最优即整箱跳过（≥ 会藏等距 tie 段——见下）
// ；楔距沿侧内外扩单调 → 侧内首箱被剪即止该侧（后续箱下界只增不减，
// 严格更劣无 tie）。**精确无漏**（剪的是可证下界；段穿质心的退化情形
// 实际覆盖两反向角、按区间假设成超集仍安全）。
// tie 规范化（与暴力参考位级恒等的要害）：查询点最近边界恰是**顶点**
// 时相邻两段位级同 d 同点、法线各异（顶点法扇是二维区域，非测度零）
// ——两实现统一 tie-break「d2 位级最小、同值取段号小者」（剪枝严格 >
// 保证等距段不被整箱跳过），分箱/暴力输出恒等，等价金标可断言位级同
const RING_BINS = 16
interface RingBins {
  bins: number[][]        // B 箱：段索引（环序升序；空箱跳过）
  halfSpan: number        // Δ/2 + slack/2：箱角半宽（剪枝用）
}
const ringBinsCache = new WeakMap<SliceRing, RingBins>()
function ringBinsOf(ring: SliceRing): RingBins {
  let cached = ringBinsCache.get(ring)
  if (cached) return cached
  const n = ring.pts.length / 2
  const angAt = (k: number): number =>
    Math.atan2(ring.pts[2 * k + 1] - ring.cz, ring.pts[2 * k] - ring.cx)
  let slack = 0
  for (let s = 0; s < n; s++) {
    let span = Math.abs(angAt(s) - angAt((s + 1) % n))
    if (span > Math.PI) span = 2 * Math.PI - span
    if (span > slack) slack = span
  }
  const bins: number[][] = Array.from({ length: RING_BINS }, () => [])
  for (let s = 0; s < n; s++) {
    const b2 = 2 * ((s + 1) % n)
    const mx = (ring.pts[2 * s] + ring.pts[b2]) / 2
    const mz = (ring.pts[2 * s + 1] + ring.pts[b2 + 1]) / 2
    bins[Math.floor(
      ((Math.atan2(mz - ring.cz, mx - ring.cx) / (2 * Math.PI) + 1) % 1)
      * RING_BINS)].push(s)
  }
  cached = { bins, halfSpan: Math.PI / RING_BINS + slack / 2 }
  ringBinsCache.set(ring, cached)
  return cached
}
export function nearestRingBoundary(
  rings: SliceRing[], x: number, z: number, margin: number, out?: RingHit,
): RingHit | null {
  let found = false
  let bd2 = 0, bd = 0, bseg = 0, bx = 0, bz = 0, bnx = 0, bnz = 0
  for (const ring of rings) {
    const dxc = x - ring.cx, dzc = z - ring.cz
    const rr = ring.r + margin
    const qc2 = dxc * dxc + dzc * dzc
    if (qc2 > rr * rr) continue
    const { bins, halfSpan } = ringBinsOf(ring)
    const qc = Math.sqrt(qc2)
    const qi = Math.floor(
      ((Math.atan2(dzc, dxc) / (2 * Math.PI) + 1) % 1) * RING_BINS)
    const n = ring.pts.length / 2
    // 单箱处理：楔距下界严格大于当前最优 → 剪（侧内后续箱楔距只增不减
    // 且严格更劣，返 true 止该侧）；否则全段细扫。返回是否剪枝
    const scanBin = (bi: number): boolean => {
      const segs = bins[bi]
      if (segs.length === 0) return false
      if (found) {
        let ad = Math.atan2(dzc, dxc)
          - ((bi + 0.5) / RING_BINS) * 2 * Math.PI
        if (ad > Math.PI) ad -= 2 * Math.PI
        if (ad < -Math.PI) ad += 2 * Math.PI
        const phi = Math.abs(ad) - halfSpan
        if (phi > 0) {
          const lb = qc * Math.sin(Math.min(phi, Math.PI / 2))
          if (lb > bd) return true
        }
      }
      for (const s of segs) {
        const a2 = 2 * s, b2 = 2 * ((s + 1) % n)
        const ax = ring.pts[a2], az = ring.pts[a2 + 1]
        const ex = ring.pts[b2] - ax, ez = ring.pts[b2 + 1] - az
        const l2 = ex * ex + ez * ez
        const t = l2 > 1e-12
          ? Math.max(0, Math.min(1, ((x - ax) * ex + (z - az) * ez) / l2)) : 0
        const px = ax + ex * t, pz = az + ez * t
        const dxp = x - px, dzp = z - pz
        const d2 = dxp * dxp + dzp * dzp
        if (!found || d2 < bd2 || (d2 === bd2 && s < bseg)) {
          bd2 = d2; bd = Math.sqrt(d2); bseg = s; found = true
          bx = px; bz = pz
          // 外法线 = 段垂线，背离环质心
          const len = Math.sqrt(l2) || 1
          let nx = -ez / len, nz = ex / len
          if (nx * (ring.cx - px) + nz * (ring.cz - pz) > 0) {
            nx = -nx; nz = -nz
          }
          bnx = nx; bnz = nz
        }
      }
      return false
    }
    scanBin(qi)   // 自所在箱（角距 ≤ Δ/2 ≤ halfSpan → 永不剪）
    // 两侧交替外扩；k = B/2 对径箱两侧重合，只扫一次（归 + 侧）
    const half = RING_BINS / 2
    let stopL = false, stopR = false
    for (let k = 1; k <= half && !(stopL && stopR); k++) {
      if (!stopR && scanBin((qi + k) % RING_BINS)) stopR = true
      if (k < half && !stopL
        && scanBin((qi - k + RING_BINS) % RING_BINS)) stopL = true
    }
  }
  if (!found) return null
  if (out) {
    out.d = bd; out.px = bx; out.pz = bz; out.nx = bnx; out.nz = bnz
    return out
  }
  return { d: bd, px: bx, pz: bz, nx: bnx, nz: bnz }
}

// 暴力参考（等价金标专用，dressfield.test 对照；运行时勿用——逐段全扫）。
// tie-break 与分箱版同规（d2 位级最小、同值取段号小者；升序扫描天然满足
// ——首个达最小值者段号最小，显式条件保持口径自文档），比较全程用 d2
// 位级值（不经过 sqrt 回乘的舍入回环）
export function nearestRingBoundaryBrute(
  rings: SliceRing[], x: number, z: number, margin: number,
): RingHit | null {
  let bd2 = Infinity, bseg = 0, bx = 0, bz = 0, bnx = 0, bnz = 0
  for (const ring of rings) {
    const dxc = x - ring.cx, dzc = z - ring.cz
    const rr = ring.r + margin
    if (dxc * dxc + dzc * dzc > rr * rr) continue
    const n = ring.pts.length / 2
    for (let s = 0; s < n; s++) {
      const a2 = 2 * s, b2 = 2 * ((s + 1) % n)
      const ax = ring.pts[a2], az = ring.pts[a2 + 1]
      const ex = ring.pts[b2] - ax, ez = ring.pts[b2 + 1] - az
      const l2 = ex * ex + ez * ez
      const t = l2 > 1e-12
        ? Math.max(0, Math.min(1, ((x - ax) * ex + (z - az) * ez) / l2)) : 0
      const px = ax + ex * t, pz = az + ez * t
      const dxp = x - px, dzp = z - pz
      const d2 = dxp * dxp + dzp * dzp
      if (d2 < bd2 || (d2 === bd2 && s < bseg)) {
        bd2 = d2; bseg = s; bx = px; bz = pz
        const len = Math.sqrt(l2) || 1
        let nx = -ez / len, nz = ex / len
        if (nx * (ring.cx - px) + nz * (ring.cz - pz) > 0) {
          nx = -nx; nz = -nz
        }
        bnx = nx; bnz = nz
      }
    }
  }
  return bd2 === Infinity ? null
    : { d: Math.sqrt(bd2), px: bx, pz: bz, nx: bnx, nz: bnz }
}

// ---- 上表面竖直支撑（2026-09-20 长裤穿台「脚背盖布」）----
// 截面环碰撞的推出只在水平面内——墙面（腿/躯干侧）正确，但「向下变宽」
// 的表面（脚背/脚尖/脚跟、大腿上侧）外法线朝上，水平推出撑不住布：布粒
// 落进下行行环内被侧向射出、再下坠，循环 = 沿坡滑到底——长裤（outseam≈
// 身高，脚全在裤筒内）脚口本该盖在脚上堆褶，实测布绕脚沉地、脚渐次穿出
// 裤筒（用户报障）。本函数补竖直支撑：粒子 (x,z) 在某下行行环内、其上行
// 行环外 = 正压在向下变宽的坡面上 → 返回接触壳支撑高度（纸样系；行间
// 交叉按两行边界带符号距离线性插值，0.5cm 行距阶梯面抹平 + skin·法线
// 竖直分量——与墙接触壳同口径，热力图 gap 在坡面接触位读 ≈0 而非 -skin
// 假穿透）。坡度 g = (dA+dB)/rowStep = tanθ（0=垂直墙、→∞=平顶）：g <
// topSupportSlope 判陡坡/墙 → null（走 collide 原水平推出，墙面行为零
// 改动）。支撑壳驻留位在交叉带上方 skin/rowStep≈2 行，自身带之外还要
// 向下扫 topSupportScan 行找回交叉带；粒子被压进坡面以下（自身行环内+
// 上行行环也内）时向上扫 topSupportScanUp 行找头顶坡面出口抬回（埋点
// 救援——墙内深埋出口远扫不到，照旧 null 水平推出）。
export function topSupportY(
  field: BodyField, x: number, z: number, patY: number,
): number | null {
  const step = field.rowStep
  const fl = Math.floor((patY - field.yMin) / step)
  if (fl < 0 || fl >= field.rows - 1) return null
  const inRow = (r: number): boolean => {
    const rings = field.slices[r]
    return !!rings?.length && inRingsQuick(x, z, rings)
  }
  // 交叉带下行行 rd 三途：自身带（下行含、上行不含）/ 向下扫首个含行
  // （壳驻留位在交叉带上方）/ 向上扫首个不含行（**埋点救援**——2026-09-20
  // 二轮：脚口 37.5 < 脚底切片周长 ~45-55，褶皱在脚面最宽截面被压进坡面
  // 以下，粒子在自身行环内、上行行环也内：旧「上下都含 = 墙内穿入」直接
  // null 交水平推出 = 被侧向射出脚印边界再坠地、褶皱循环下扎——脚穿出
  // 裤筒的主通道。真实物理：埋点头顶就是坡面出口（脚趾/脚背上侧几 cm），
  // 抬回坡面；墙内深埋（大腿等，出口远/无出口）扫不到 → null，墙面零改动）
  let rd = -1
  if (inRow(fl)) {
    if (!inRow(fl + 1)) {
      rd = fl
    } else {
      const ceil = Math.min(field.rows - 2, fl + DRAPE_PRIOR.topSupportScanUp)
      for (let r = fl + 2; r <= ceil; r++) {
        if (!inRow(r)) { rd = r - 1; break }
      }
    }
  } else {
    const floor = Math.max(0, fl - DRAPE_PRIOR.topSupportScan)
    for (let r = fl - 1; r >= floor; r--) {
      if (inRow(r)) { rd = r; break }
    }
  }
  if (rd < 0) return null
  const ringsD = field.slices[rd]
  const ringsU = field.slices[rd + 1]
  if (!ringsU?.length) return null
  // dA = 下行环内深、dB = 上行环外距（null = 远离上行环边界 → 陡坡，
  // 取行距作有限值让交点贴下行行）；g 大 = 坡平（朝上承力）
  const hitD = nearestRingBoundary(ringsD, x, z, step)
  if (!hitD) return null              // 环内却找不到边界（不可能；防御）
  const hitU = nearestRingBoundary(ringsU, x, z, step)
  const dA = hitD.d
  const dB = hitU ? hitU.d : step
  const g = (dA + dB) / step
  if (g < DRAPE_PRIOR.topSupportSlope) return null
  const ny = g / Math.sqrt(1 + g * g)  // 表面外法线竖直分量
  return field.yMin + (rd + dA / (dA + dB)) * step + CORE_SKIN * ny
}

// 环组判内（包围圆 quick reject + pointInRings 射线法；点在某环内必在其
// 包围圆内，全落空免射线扫描）
function inRingsQuick(x: number, z: number, rings: SliceRing[]): boolean {
  let near = false
  for (const ring of rings) {
    const dx = x - ring.cx, dz = z - ring.cz
    if (dx * dx + dz * dz < ring.r * ring.r) { near = true; break }
  }
  return near && pointInRings(x, z, rings)
}

// ---- 穿台腰圈钉环（2026-09-20 口径：形随体、长随衣、间隙均匀）----
// 用户口径「模拟真实的情况、腰头尺寸多少就是多少、穿不进在热力图体现」
// → 钉环 = 腰站截面边界沿局部外法线**等距偏移** δ，定点迭代解 δ 使闭弦
// 周长恰 = 成衣腰长 C：
//   · 形状来自人体（真实腰头贴合截面变形）、尺寸来自布长（环长严格
//     = 成衣腰）、间隙均匀 |δ|（周身松量一致）
//   · 偏大 δ>0 全环离体等距、偏小 δ<0 均匀穿透（钉 XZ 冻结如实呈现 +
//     热力图 gap 红区 = 穿不进读数）；旁挂分支不建环（原口径）
// 证伪留档：绕原点整体放大 s=C/周长（2026-09-19 首版）在截面中心前偏
// ~5.3cm（前伸 14.74/后缩 2.69）时每点间隙 =(s−1)·|p| ∝ 到原点距离——
// 前:后 ≈ 5.5:1 环整体前骑（用户目检「不是平均分配、整体往前」；决策
// 日志 2026-09-20 条）
export interface WaistRing {
  pts: Float64Array      // 2N 闭合折线（等距偏移后终环，N 点等弧长重采样）
  arc: Float64Array      // N 累计弦弧长（arc[0]=0；末段闭回 pts[0]）
  total: number          // 环全长 = 成衣腰长 C（定点迭代收敛 <1e-6）
  y: number              // 源截面行（assemble 带顶环按 y+带宽取行派生）
}

// 腰站 y 行截面边界 → 长度恰为 C 的钉环：取该行首个闭环，前中（+Z 最
// 远点）起、向左（−X）行走（与 band.ringWalk 环序一致），等弧长重采样
// 后逐点沿局部外法线（相邻段垂线均值、背离环质心取向）等距偏移 δ，定
// 点迭代 δ ← δ + (C−P(δ))/2π 至闭弦周长 = C（凸闭曲线 Steiner 公式
// P(δ)≈P+2πδ，重采样弦亏由实测修正吸收；δ<0 = 均匀内偏穿体不设防；
// 不支持场带撑型芯的多环行，腰站单环）
export function buildWaistRing(
  field: BodyField, y: number, circumference: number,
): WaistRing {
  const rings = field.loopsAt(y)
  if (rings.length === 0) {
    throw new Error(`y=${y.toFixed(1)} 行无截面环——腰圈钉环无法构建`)
  }
  const src = rings[0].pts
  const n = src.length / 2
  if (n < 8 || !Number.isFinite(circumference) || circumference <= 0) {
    throw new Error('腰站截面环退化或成衣腰长非法——腰圈钉环无法构建')
  }
  // 前中起点 = +Z 支撑最大点；行走方向取下一步 x 更小（向左）
  let start = 0, bestZ = -Infinity
  for (let k = 0; k < n; k++) {
    if (src[2 * k + 1] > bestZ) { bestZ = src[2 * k + 1]; start = k }
  }
  const dir = src[2 * ((start + 1) % n)] < src[2 * ((start - 1 + n) % n)] ? 1 : -1
  const order: number[] = []
  for (let k = 0; k < n; k++) order.push(((start + dir * k) % n + n) % n)
  // 原折线闭周长 + 沿序累计弧长表
  const cum: number[] = [0]
  for (let k = 0; k < n; k++) {
    const a = 2 * order[k], b = 2 * order[(k + 1) % n]
    cum.push(cum[k] + Math.hypot(src[b] - src[a], src[b + 1] - src[a + 1]))
  }
  const len = cum[n]
  // 等弧长重采样（N·spacing 恰铺满闭合折线）得基环（未偏移）
  const N = Math.max(64, Math.round(len / DRESSING_PRIOR.waistRingStep))
  const spacing = len / N
  const base = new Float64Array(2 * N)
  let j = 0
  for (let k = 0; k < N; k++) {
    const target = k * spacing
    while (j < n - 1 && cum[j + 1] < target) j++
    const a = 2 * order[j], b = 2 * order[(j + 1) % n]
    const seg = cum[j + 1] - cum[j] || 1
    const t = (target - cum[j]) / seg
    base[2 * k] = src[a] + (src[b] - src[a]) * t
    base[2 * k + 1] = src[a + 1] + (src[b + 1] - src[a + 1]) * t
  }
  // 基环质心 + 逐点外法线 = 相邻两段垂线均值、背离质心取向（取向技巧同
  // nearestRingBoundary——轻度凹截面也给出一致向外的法线）
  let cx = 0, cz = 0
  for (let k = 0; k < N; k++) { cx += base[2 * k]; cz += base[2 * k + 1] }
  cx /= N; cz /= N
  const nx = new Float64Array(N), nz = new Float64Array(N)
  for (let k = 0; k < N; k++) {
    const p = 2 * ((k - 1 + N) % N), q = 2 * k, r = 2 * ((k + 1) % N)
    // 段 k→k+1 与段 k−1→k 的左垂线之和（角点法线 = 角平分方向）
    const ax = -(base[r + 1] - base[q + 1]), az = base[r] - base[q]
    const bx = -(base[q + 1] - base[p + 1]), bz = base[q] - base[p]
    let ux = ax + bx, uz = az + bz
    const un = Math.hypot(ux, uz) || 1
    ux /= un; uz /= un
    if (ux * (base[q] - cx) + uz * (base[q + 1] - cz) < 0) { ux = -ux; uz = -uz }
    nx[k] = ux; nz[k] = uz
  }
  // 等距偏移 δ 定点迭代：闭弦周长 P(δ) ≈ len + 2πδ（Steiner），每轮量实测
  // 修正 δ ← δ + (C−P)/2π，2~3 轮收敛 |P−C| ≤ 1e-6（上限 32 轮防御）；
  // δ<0 = 均匀内偏（偏小款穿体，钉 XZ 冻结如实呈现，不设下限）
  const pts = new Float64Array(2 * N)
  const perim = (d: number): number => {
    for (let k = 0; k < N; k++) {
      pts[2 * k] = base[2 * k] + d * nx[k]
      pts[2 * k + 1] = base[2 * k + 1] + d * nz[k]
    }
    let s = 0
    for (let k = 0; k < N; k++) {
      const k2 = 2 * ((k + 1) % N)
      s += Math.hypot(pts[k2] - pts[2 * k], pts[k2 + 1] - pts[2 * k + 1])
    }
    return s
  }
  let delta = (circumference - len) / (2 * Math.PI)
  let P = perim(delta)
  for (let it = 0; it < 32 && Math.abs(P - circumference) > 1e-6; it++) {
    delta += (circumference - P) / (2 * Math.PI)
    P = perim(delta)
  }
  // 终环累计弦弧长表（total = P 恰 = C，kScale/弧长摆放契约保持）
  const arc = new Float64Array(N)
  for (let k = 1; k < N; k++) {
    arc[k] = arc[k - 1] + Math.hypot(
      pts[2 * k] - pts[2 * k - 2], pts[2 * k + 1] - pts[2 * k - 1])
  }
  const total = arc[N - 1] + Math.hypot(
    pts[0] - pts[2 * (N - 1)], pts[1] - pts[2 * (N - 1) + 1])
  return { pts, arc, total, y }
}

// 弧长 → 环上点（二分段插值；s 夹取 [0,total]，末段闭回 pts[0]）
export function ringPointAt(ring: WaistRing, s: number): { x: number; z: number } {
  const t = Math.max(0, Math.min(ring.total, s))
  let lo = 0, hi = ring.arc.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (ring.arc[mid] <= t) lo = mid; else hi = mid - 1
  }
  const k = lo, k2 = (k + 1) % ring.arc.length
  const a0 = ring.arc[k]
  const a1 = k + 1 < ring.arc.length ? ring.arc[k + 1] : ring.total
  const f = a1 > a0 ? (t - a0) / (a1 - a0) : 0
  return {
    x: ring.pts[2 * k] + (ring.pts[2 * k2] - ring.pts[2 * k]) * f,
    z: ring.pts[2 * k + 1] + (ring.pts[2 * k2 + 1] - ring.pts[2 * k + 1]) * f,
  }
}

// 人台切片环 → LegAxis（穿台摆位腿区输入；数据源无关——旁挂仍用
// core.buildLegAxis 纸样站口径）。自裆地标向下 forkSearch 窗内找**首个
// 恰 2 闭环行** = 有效叉口 forkEff（体裆地标处切片可能仍单环）；双环行
// rAt = max 环包围半径（支撑上界口径——绕管摆位半径 = rAt+skin+gap 按
// 构造在环外，对冲真腿环非圆的局部凸起）、cAt = 双环 |质心 x| 均值。
// 非 2 环行跳过（相邻 2 环行线性桥接）。
// ankleY（2026-09-18 脚碰撞修复）：扫描下限——踝以下是脚不是圆柱腿，
// 脚环包围半径含脚全长（r ~18，前伸 cz 13+），混进 rProf 会让裤脚摆位
// 喇叭张开；穿台场行表下探负 y 后必须止于踝。缺省 undefined = 扫到行 0
// （合成场/老口径，脚环不存在无此问题）
export function buildLegAxisFromRings(
  field: BodyField, forkY: number, ankleY?: number,
): LegAxis {
  const step = field.rowStep
  const r0 = Math.max(0, Math.round((forkY - field.yMin) / step))
  const rMin = Math.max(0, r0 - Math.floor(DRESSING_PRIOR.forkSearch / step))
  let forkRow = -1
  for (let r = r0; r >= rMin; r--) {
    if (field.slices[r]?.length === 2) { forkRow = r; break }
  }
  if (forkRow < 0) {
    throw new Error(`穿台腿轴：裆地标下方 ${DRESSING_PRIOR.forkSearch}cm 窗内无双腿分离行（人台切片环未分开）`)
  }
  // 腿轴扫描下限行（ceil 只含踝及以上行）；无踝地标 = 行 0 老口径
  const rFloor = ankleY === undefined ? 0 : Math.max(0, Math.min(field.rows - 1,
    Math.ceil((ankleY - field.yMin) / step)))
  const rProf: [number, number][] = []
  const cProf: [number, number][] = []
  for (let r = forkRow; r >= rFloor; r--) {
    const rings = field.slices[r]
    if (!rings || rings.length !== 2) continue
    const [a, b] = rings
    // 轴心 z=0 近似（LegAxis 无 zAt）：真腿环质心 z 偏移（大腿偏前 ~2cm，
    // 穿台实测）会让绕管前侧浅穿——包围圆按 (cx,0) 圆心放大 |cz|，保证
    // 环 ⊂ 圆(轴心, rAt)，绕管半径 rAt+skin+gap 按构造在环外
    rProf.push([field.yMin + r * step,
      Math.max(a.r + Math.abs(a.cz), b.r + Math.abs(b.cz))])
    cProf.push([field.yMin + r * step, (Math.abs(a.cx) + Math.abs(b.cx)) / 2])
  }
  if (rProf.length < 2) {
    throw new Error('穿台腿轴：双腿分离行不足 2 行，无法插值')
  }
  rProf.sort((p, q) => p[0] - q[0])
  cProf.sort((p, q) => p[0] - q[0])
  const lerpAt = (prof: [number, number][], y: number): number => {
    if (y <= prof[0][0]) return prof[0][1]
    for (let i = 1; i < prof.length; i++) {
      if (y <= prof[i][0]) {
        const [ya, ra] = prof[i - 1], [yb, rb] = prof[i]
        return yb - ya > 1e-9 ? ra + ((rb - ra) * (y - ya)) / (yb - ya) : rb
      }
    }
    return prof[prof.length - 1][1]
  }
  return {
    rAt: (y) => lerpAt(rProf, y),
    cAt: (y) => lerpAt(cProf, y),
    forkY: field.yMin + forkRow * step,
    ankleY,
  }
}

// ---- 脚区幕帘摆位（2026-09-20 长裤盖脚，assemble step 4.5 消费）----
// 腿区绕管摆位在踝以下把筒半径钳在踝值，而脚全长前伸远超筒径（zhitong
// 实测趾尖距腿轴 19.3 vs 筒 6.7；脚底切片周长 75~86 vs 脚口环 37.5）——
// 摆位即穿模，且脚口环不可能环抱脚最宽截面（真实物理：站姿平脚穿不过更
// 紧的脚口，长裤脚口本就搭在脚背上）。踝下脚区改「幕帘」摆位：从踝环沿
// 重力下行（未触面 = 筒半径竖直垂），触到脚面（表面径距 + 壳距超出筒
// 半径）后贴表面走线，长度预算（纸样到踝的距离）用尽即停；表面尽/到地
// 后竖直落地、余量沿地外摊——脚口前缘自然落在趾盒/脚背上、侧后缘垂地，
// 初值直接落进物理正确的 drape 盆地（此前从「脚穿进筒里」的错误初值出
// 发，脚区永动 churn、脚渐次穿出裤筒）。方向无触面的侧/内 sectors 走线
// = 竖直垂在筒半径上，与原绕管摆位逐点一致（偏离仅出现在脚面凸出处）。
export interface FootCurtain {
  bins: number            // 方向 bin 数
  cx: number              // 腿轴 x（z≈0 口径同 buildLegAxisFromRings）
  tables: Float32Array[]  // 每 bin 3N 平铺 [s,h,t]：s 累计弧长（自踝）、
                          // h 图案 y、t 径向距；线性插值查任意 s
}

// 两腿幕帘表（[L, R]；行 = 自踝行向下的场行，行内 tSurf = 本腿环沿该
// 方向射线最远穿越，表面尽后 t 冻结、落地后沿地外摊 40·rowStep 防御上限）
export function buildFootCurtain(
  field: BodyField, axis: LegAxis, yFloor: number,
): FootCurtain[] {
  const step = field.rowStep
  const ankleY = axis.ankleY!
  const off = CORE_SKIN + HANG_PRIOR.garmentGap
  const rTube = axis.rAt(ankleY) + off
  const rA = Math.max(0, Math.min(field.rows - 1,
    Math.round((ankleY - field.yMin) / step)))
  const bins = 96
  const out: FootCurtain[] = []
  for (const sgn of [-1, 1] as const) {
    const cx = sgn * axis.cAt(ankleY)
    const tables: Float32Array[] = []
    for (let b = 0; b < bins; b++) {
      const th = ((b + 0.5) / bins) * 2 * Math.PI
      const ux = Math.sin(th), uz = Math.cos(th)
      const tbl: number[] = []
      let h = field.yMin + rA * step
      let s = 0
      let t = rTube
      tbl.push(0, h, t)
      for (let r = rA - 1; r >= 0; r--) {
        const rings = field.slices[r] ?? []
        // 本腿环（质心同侧；踝下双脚行 2 环，单环归同侧防御）
        let tSurf: number | null = null
        for (const ring of rings) {
          if (Math.abs(ring.cx) > 1 && Math.sign(ring.cx) !== sgn) continue
          const n = ring.pts.length / 2
          for (let k = 0; k < n; k++) {
            // 射线 (cx,0)+t·(ux,uz) 与环段交点，取最远 t≥0（外缘口径，
            // 趾尖前伸必在环沿该向的最远边界上）；段端点先换到轴心相对系
            const a = 2 * k, c = 2 * ((k + 1) % n)
            const ax = ring.pts[a] - cx, az = ring.pts[a + 1]
            const ex = ring.pts[c] - ring.pts[a], ez = ring.pts[c + 1] - ring.pts[a + 1]
            const den = ux * ez - uz * ex
            if (Math.abs(den) < 1e-12) continue
            const lam = (ax * uz - ux * az) / den
            if (lam < 0 || lam > 1) continue
            const hx = ax + lam * ex, hz = az + lam * ez
            const tt = Math.abs(uz) > Math.abs(ux) ? hz / uz : hx / ux
            if (tt >= 0 && (tSurf === null || tt > tSurf)) tSurf = tt
          }
        }
        const hNext = field.yMin + r * step
        const tNext = tSurf === null ? t : Math.max(rTube, tSurf + off)
        s += Math.hypot(hNext - h, tNext - t)
        h = hNext; t = tNext
        tbl.push(s, h, t)
      }
      // 地面（世界 y=0 → 图案 y = yFloor）：竖直落地 + 余量沿地外摊
      if (h > yFloor) {
        s += h - yFloor
        h = yFloor
        tbl.push(s, h, t)
      }
      for (let g = 0; g < 40; g++) {
        s += step
        t += step
        tbl.push(s, h, t)
      }
      tables.push(Float32Array.from(tbl))
    }
    out.push({ bins, cx, tables })
  }
  return out
}

// 幕帘表查询：方向 θ（自腿轴）、弧长 s → (h, t)；bin 内表线性插值
export function curtainAt(
  curtain: FootCurtain, th: number, s: number,
): { h: number; t: number } {
  let b = Math.floor((th / (2 * Math.PI)) * curtain.bins)
  b = ((b % curtain.bins) + curtain.bins) % curtain.bins
  const tbl = curtain.tables[b]
  const n = tbl.length / 3
  if (s <= 0) return { h: tbl[1], t: tbl[2] }
  for (let k = 1; k < n; k++) {
    const s1 = tbl[3 * k]
    if (s <= s1 || k === n - 1) {
      const s0 = tbl[3 * (k - 1)]
      const f = s1 > s0 ? Math.min(1, Math.max(0, (s - s0) / (s1 - s0))) : 1
      return {
        h: tbl[3 * (k - 1) + 1] + (tbl[3 * k + 1] - tbl[3 * (k - 1) + 1]) * f,
        t: tbl[3 * (k - 1) + 2] + (tbl[3 * k + 2] - tbl[3 * (k - 1) + 2]) * f,
      }
    }
  }
  return { h: tbl[1], t: tbl[2] }
}
