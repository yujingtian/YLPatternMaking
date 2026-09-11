// 三管径向高度场：morph+对齐后的网格 -> R(y,θ) 查表（碰撞桥）。
// 逐行切片（sliceLoops，与 Python 金标同构）替代顶点直接 splat——顶点行
// 距 ~2cm，0.5cm 行表会隔行全空；切片在任意 y 连续可得。行内 θ 向由切片
// 折线点 splat + 空洞邻域 max 膨胀填补（人体横截面相对管轴星形凸，max
// 填充是保守外推——只会偏外不会切肉）。
// 三管分工（与旧环模型等价覆盖）：
//   · 骨盆管 [crotch−pelvisBelowCrotch, 顶]：轴 x=0；裆下双环全喂（两腿
//     并集 = 旧楔底保守覆盖会阴）；
//   · 腿管 [hem−legBelowHem, crotch+legAboveCrotch]：轴 x = 当行腿点半均
//     （分叉下 = 该腿环质心；分叉上单环按点 x 符号分喂两腿表 = 旧头带，
//     与骨盆管并集保守）。
// 查表双线性：y 夹端行、θ 环向插值。返回**裸 R**（collisionSkin 由
// collideOne 自加，与 radiusAt 超椭圆口径一致）。
import { BODYMESH_PRIOR } from '../priors'
import { sliceLoops } from './slice'

export interface HeightField {
  yTop: number          // 顶行 y（payload 坐标，dy 格点对齐）
  yBottom: number
  dy: number
  thetaBins: number
  rows: number
  table: Float32Array   // rows × thetaBins，R cm（相对当行管轴 cx）
  cx: Float32Array      // rows，管轴 x
  meanR: Float32Array   // rows，行均值（SectionParams a/bF/bB 填充值）
}

export interface TubeFieldConfig {
  crotch: number        // 分叉高（payload 坐标）
  top: number           // 网格顶（裁切面，payload 坐标）
  pelvisBottom: number  // crotch − pelvisBelowCrotch
  legTop: number        // crotch + legAboveCrotch
  legBottom: number     // hem − legBelowHem
}

export function buildTubeFields(
  pos: Float32Array, idx: Uint32Array, cfg: TubeFieldConfig,
): { pelvis: HeightField; legL: HeightField; legR: HeightField } {
  const dy = BODYMESH_PRIOR.rowStep
  const bins = BODYMESH_PRIOR.thetaBins
  // 统一 dy 格点（自 0 起的 lattice）：三管行界取整到格点，行索引全局对齐
  const lat = (y: number, up: boolean) =>
    (up ? Math.ceil(y / dy - 1e-9) : Math.floor(y / dy + 1e-9)) * dy
  const mk = (yTopReq: number, yBotReq: number, axis: 'zero' | 'leg') => {
    const yTop = lat(Math.min(yTopReq, cfg.top), true)
    const yBottom = lat(Math.max(yBotReq, cfg.legBottom), false)
    // rows ≥ 2：sampleField 的 r0=rows−2 索引依赖（真数据跨度 >> dy）
    const rows = Math.max(2, Math.round((yTop - yBottom) / dy) + 1)
    return {
      yTop, yBottom, dy, thetaBins: bins, rows,
      table: new Float32Array(rows * bins),
      cx: new Float32Array(rows),
      meanR: new Float32Array(rows),
      axis,
    } as HeightField & { axis: 'zero' | 'leg' }
  }
  const pelvis = mk(cfg.top, cfg.pelvisBottom, 'zero')
  const legR = mk(cfg.legTop, cfg.legBottom, 'leg')
  const legL = mk(cfg.legTop, cfg.legBottom, 'leg')

  // 单遍切片：全局格点从上往下，落进各管域的行就地 splat
  const yHi = Math.max(pelvis.yTop, legR.yTop)
  const yLo = Math.min(pelvis.yBottom, legL.yBottom)
  const rowOf = (f: HeightField, y: number) =>
    Math.round((f.yTop - y) / dy)
  for (let y = yHi; y >= yLo - 1e-9; y -= dy) {
    const loops = sliceLoops(pos, idx, y).filter((l) => l.closed)
    if (!loops.length) continue
    const splat = (f: HeightField & { axis: 'zero' | 'leg' }, pts: { x: number; z: number }[]) => {
      if (!pts.length) return
      const r = rowOf(f, y)
      if (r < 0 || r >= f.rows) return
      const off = r * bins
      // 腿管轴 = 当行腿点半均；骨盆轴恒 0（与旧模型契约一致）
      const cx = f.axis === 'leg'
        ? pts.reduce((s, p) => s + p.x, 0) / pts.length : 0
      f.cx[r] = cx
      for (const p of pts) {
        const th = Math.atan2(p.x - cx, p.z)
        const b = Math.floor(((th + Math.PI) / (2 * Math.PI)) * bins) % bins
        const R = Math.hypot(p.x - cx, p.z)
        if (R > f.table[off + b]) f.table[off + b] = R
      }
    }
    if (y >= pelvis.yBottom - 1e-9) {
      // 骨盆：全部环（裆下双腿并集保守）
      splat(pelvis, loops.flatMap((l) => l.pts))
    }
    if (y <= legR.yTop + 1e-9) {
      // 腿：分叉下按环质心符号取本腿环；分叉上单环按点 x 符号分喂两表
      //（= 旧头带，与骨盆管并集保守）
      const right: { x: number; z: number }[] = []
      const left: { x: number; z: number }[] = []
      if (loops.length === 1) {
        for (const p of loops[0].pts) (p.x > 0 ? right : left).push(p)
      } else {
        for (const l of loops) (l.cx > 0 ? right : left).push(...l.pts)
      }
      splat(legR, right)
      splat(legL, left)
    }
  }

  for (const f of [pelvis, legL, legR]) {
    finishField(f)
  }
  return { pelvis, legL, legR }
}

// 行内 θ 空洞膨胀填补 + 行均值；全空行纵向持有（顶/底越界行的保守回退）
function finishField(f: HeightField): void {
  const { rows, thetaBins: bins, table } = f
  for (let r = 0; r < rows; r++) {
    const off = r * bins
    // 循环膨胀：空格取两邻非空 max（星形截面保守外推）；缝宽 ~4-6 bin，
    // 8 轮内填满，安全阀 64
    for (let pass = 0; pass < 64; pass++) {
      let holes = 0
      const src = table.slice(off, off + bins)
      for (let b = 0; b < bins; b++) {
        if (src[b] > 0) continue
        const l = src[(b + bins - 1) % bins], rr = src[(b + 1) % bins]
        if (l > 0 || rr > 0) table[off + b] = Math.max(l, rr)
        else holes++
      }
      if (!holes) break
    }
  }
  // 纵向持有：自上而下空行抄上一非空行；再自下而上补头部空行（如裁切面
  // 恰在格点上方的半行残缺）
  for (let r = 1; r < rows; r++) copyIfEmpty(f, r, r - 1)
  for (let r = rows - 2; r >= 0; r--) copyIfEmpty(f, r, r + 1)
  for (let r = 0; r < rows; r++) {
    let s = 0
    for (let b = 0; b < bins; b++) s += table[r * bins + b]
    f.meanR[r] = s / bins
  }
}

function copyIfEmpty(f: HeightField, dst: number, src: number): void {
  const { thetaBins: bins, table } = f
  const d = dst * bins, s = src * bins
  if (table[d] > 0) return
  if (table[s] <= 0) return
  table.copyWithin(d, s, s + bins)
  f.cx[dst] = f.cx[src]
}

// 双线性查表：y 夹端行、θ 环向插值（th 为任意弧度，atan2 口径）
export function sampleField(f: HeightField, y: number, th: number): number {
  const { rows, dy, thetaBins: bins, table } = f
  const t = Math.min(Math.max((f.yTop - y) / dy, 0), rows - 1)
  const r0 = Math.min(Math.floor(t), rows - 2)
  const fr = t - r0
  const r1 = r0 + 1
  const u = (((th + Math.PI) / (2 * Math.PI)) % 1 + 1) % 1
  const fb = u * bins
  const b0 = Math.floor(fb) % bins
  const b1 = (b0 + 1) % bins
  const fc = fb - Math.floor(fb)
  const at = (r: number, b: number) => table[r * bins + b]
  return (at(r0, b0) * (1 - fc) + at(r0, b1) * fc) * (1 - fr)
    + (at(r1, b0) * (1 - fc) + at(r1, b1) * fc) * fr
}

// 绑定成 SectionParams.hf 柄（闭包捕获场；y 用查询值非环值）
export function bindField(f: HeightField): (y: number, th: number) => number {
  return (y, th) => sampleField(f, y, th)
}
