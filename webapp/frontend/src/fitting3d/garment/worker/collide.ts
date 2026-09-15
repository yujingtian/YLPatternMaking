// 粒子-人台碰撞（二期重写）：旧三管解析投影退役，改 three-mesh-bvh
// 最近点查询 + BodyField 宽相。设计要点（方案定稿 #3）：
//   宽相   R(y,θ) 凸上界（场 ⊇ 真实表支撑）：|xz| > R+skin 必不贴体，
//          跳过 BVH 查询——绝大多数外层粒子零开销；
//   窄相   closestPointToPoint(maxThreshold=4×skin)，命中后按
//          (粒子−最近点)·面法线 判内外：外=沿推出方向补到 skin；内=沿
//          面外法线穿过表面推出（closest-point 方向对体内点指向内侧，
//          直推会越陷越深）；
//   方向   必须归一化（旧链 2026-09-09 前科：未归一方向灌半径函数，
//          布料沉入体表 ~10cm）；
//   摩擦   推出位移的切向分量按 friction 拉回（贴体防滑落）；
//   sweep  ×3 保留（顺序投影非幂等：一条腿的推出可能把粒子推进另一条）。
import * as THREE from 'three'
import { MeshBVH } from 'three-mesh-bvh'
import type { BodyField } from '../placement'
import { SOLVER_PRIOR } from '../priors'

export interface Collider {
  /** 全粒子多遍碰撞（原地写 pos；prev 供摩擦回拉参考） */
  resolveAll(
    pos: Float32Array, prev: Float32Array, total: number,
    skin: number, friction: number,
  ): void
  /** 单点吸附实际曲面：pos[i] ← 最近面外法线·skin（无界查询；band 初始
   *  位/pin 目标用——凸包场在体侧虚高，钉场环必悬空） */
  snapOne(pos: Float32Array, i: number, skin: number): void
  /** 网格精确穿透统计：体内粒子（面法线判向）的入深 count/worst。
   *  hull 场口径（placement.penetrationStats）对凹谷几何误报——花生
   *  腰谷里的布在 hull 内但不在网格内；金标验收用本口径 */
  penetrationStats(
    pos: Float32Array, total: number, skin: number,
  ): { count: number; worst: number }
  /** 单粒子入深（体外=0）；诊断/金标定位用 */
  meshDepth(pos: Float32Array, i: number, skin: number): number
  dispose(): void
}

export function buildCollider(
  bodyPos: Float32Array, bodyIdx: Uint32Array, field: BodyField,
): Collider {
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(bodyPos, 3))
  geo.setIndex(new THREE.Uint32BufferAttribute(bodyIdx, 1))
  const bvh = new MeshBVH(geo)
  const q = new THREE.Vector3()
  const hit = { point: new THREE.Vector3(), distance: 0, faceIndex: -1 }
  // 查询不设 maxThreshold：体内深陷粒子（距面 >4×skin）必须能查到命中，
  // 否则碰撞永久失明（实测面板腰口沉入 1.5cm 后再也不被推出）；远粒子
  // 由宽相 field.radiusAt 过滤，不进窄相
  const index = geo.index!

  return {
    resolveAll(pos, prev, total, skin, friction) {
      for (let sweep = 0; sweep < SOLVER_PRIOR.collideSweeps; sweep++) {
        for (let i = 0; i < total; i++) {
          const i3 = 3 * i
          const x = pos[i3], y = pos[i3 + 1], z = pos[i3 + 2]
          const dist = Math.hypot(x, z)
          if (dist < 1e-9) continue
          if (dist > field.radiusAt(y, Math.atan2(x, z)) + skin) continue
          q.set(x, y, z)
          const r = bvh.closestPointToPoint(q, hit, 0, Infinity)
          if (!r || r.faceIndex < 0) continue
          // 命中三角形面外法线（水密网格外向）判内外
          const f = 3 * r.faceIndex
          const a = index.getX(f), b = index.getX(f + 1), c = index.getX(f + 2)
          const ax = bodyPos[3 * a], ay = bodyPos[3 * a + 1], az = bodyPos[3 * a + 2]
          const e1x = bodyPos[3 * b] - ax, e1y = bodyPos[3 * b + 1] - ay
          const e1z = bodyPos[3 * b + 2] - az
          const e2x = bodyPos[3 * c] - ax, e2y = bodyPos[3 * c + 1] - ay
          const e2z = bodyPos[3 * c + 2] - az
          let nx = e1y * e2z - e1z * e2y
          let ny = e1z * e2x - e1x * e2z
          let nz = e1x * e2y - e1y * e2x
          const nl = Math.hypot(nx, ny, nz)
          if (nl < 1e-12) continue
          nx /= nl; ny /= nl; nz /= nl
          const dx = x - r.point.x, dy = y - r.point.y, dz = z - r.point.z
          if (dx * nx + dy * ny + dz * nz >= 0) {
            // 体外：距面 ≥ skin 无接触才跳过——**体内粒子不论多深都必须
            // 走穿面推出**（旧代码在查询后先 `distance >= skin → continue`，
            // 深陷体内的粒子被静默跳过 = 永久失明，缝合把它们拖进瓣心
            // 8cm 也无人推出；无界查询只修了命中、没修这个过滤）
            if (r.distance >= skin) continue
            // 体外：沿 (粒子−最近点) 推出到 skin 距离
            const d = r.distance
            if (d < 1e-6) {
              pos[i3] += nx * skin; pos[i3 + 1] += ny * skin
              pos[i3 + 2] += nz * skin
            } else {
              const push = (skin - d) / d
              pos[i3] += dx * push; pos[i3 + 1] += dy * push
              pos[i3 + 2] += dz * push
            }
          } else {
            // 体内：沿面外法线穿过表面推出到 skin。深陷粒子一次弹出
            // 是厘米级位移，若不同步 prev，速度更新 (pos-prev)/dt 会把它
            // 变成 ~10^3 cm/s 的踢腿灌回全场（实测地板 2.3 永不收敛）——
            // 弹出按约束投影处理：prev 跟着搬到新位，只留物理位移
            pos[i3] = r.point.x + nx * skin
            pos[i3 + 1] = r.point.y + ny * skin
            pos[i3 + 2] = r.point.z + nz * skin
            prev[i3] = pos[i3]; prev[i3 + 1] = pos[i3 + 1]
            prev[i3 + 2] = pos[i3 + 2]
          }
          // 摩擦：推出后位移的切向分量按 friction 拉回
          const mx = pos[i3] - prev[i3], my = pos[i3 + 1] - prev[i3 + 1]
          const mz = pos[i3 + 2] - prev[i3 + 2]
          const mn = mx * nx + my * ny + mz * nz
          pos[i3] -= (mx - nx * mn) * friction
          pos[i3 + 1] -= (my - ny * mn) * friction
          pos[i3 + 2] -= (mz - nz * mn) * friction
        }
      }
    },
    snapOne(pos, i, skin) {
      const i3 = 3 * i
      q.set(pos[i3], pos[i3 + 1], pos[i3 + 2])
      const r = bvh.closestPointToPoint(q, hit, 0, Infinity)
      if (!r || r.faceIndex < 0) return
      const f = 3 * r.faceIndex
      const a = index.getX(f), b = index.getX(f + 1), c = index.getX(f + 2)
      const ax = bodyPos[3 * a], ay = bodyPos[3 * a + 1], az = bodyPos[3 * a + 2]
      const e1x = bodyPos[3 * b] - ax, e1y = bodyPos[3 * b + 1] - ay
      const e1z = bodyPos[3 * b + 2] - az
      const e2x = bodyPos[3 * c] - ax, e2y = bodyPos[3 * c + 1] - ay
      const e2z = bodyPos[3 * c + 2] - az
      let nx = e1y * e2z - e1z * e2y
      let ny = e1z * e2x - e1x * e2z
      let nz = e1x * e2y - e1y * e2x
      const nl = Math.hypot(nx, ny, nz)
      if (nl < 1e-12) return
      nx /= nl; ny /= nl; nz /= nl
      pos[i3] = r.point.x + nx * skin
      pos[i3 + 1] = r.point.y + ny * skin
      pos[i3 + 2] = r.point.z + nz * skin
    },
    penetrationStats(pos, total, skin) {
      let count = 0, worst = 0
      for (let i = 0; i < total; i++) {
        const i3 = 3 * i
        const x = pos[i3], y = pos[i3 + 1], z = pos[i3 + 2]
        const dist = Math.hypot(x, z)
        if (dist < 1e-9) continue
        if (dist > field.radiusAt(y, Math.atan2(x, z)) + skin) continue
        q.set(x, y, z)
        const r = bvh.closestPointToPoint(q, hit, 0, Infinity)
        if (!r || r.faceIndex < 0) continue
        const f = 3 * r.faceIndex
        const a = index.getX(f), b = index.getX(f + 1), c = index.getX(f + 2)
        const ax = bodyPos[3 * a], ay = bodyPos[3 * a + 1], az = bodyPos[3 * a + 2]
        const e1x = bodyPos[3 * b] - ax, e1y = bodyPos[3 * b + 1] - ay
        const e1z = bodyPos[3 * b + 2] - az
        const e2x = bodyPos[3 * c] - ax, e2y = bodyPos[3 * c + 1] - ay
        const e2z = bodyPos[3 * c + 2] - az
        let nx = e1y * e2z - e1z * e2y
        let ny = e1z * e2x - e1x * e2z
        let nz = e1x * e2y - e1y * e2x
        const nl = Math.hypot(nx, ny, nz)
        if (nl < 1e-12) continue
        const dx = x - r.point.x, dy = y - r.point.y, dz = z - r.point.z
        if ((dx * nx + dy * ny + dz * nz) / nl < 0) {
          count++
          if (r.distance > worst) worst = r.distance
        }
      }
      return { count, worst }
    },
    meshDepth(pos: Float32Array, i: number, _skin: number): number {
      const i3 = 3 * i
      q.set(pos[i3], pos[i3 + 1], pos[i3 + 2])
      const r = bvh.closestPointToPoint(q, hit, 0, Infinity)
      if (!r || r.faceIndex < 0) return 0
      const f = 3 * r.faceIndex
      const a = index.getX(f), b = index.getX(f + 1), c = index.getX(f + 2)
      const ax = bodyPos[3 * a], ay = bodyPos[3 * a + 1], az = bodyPos[3 * a + 2]
      const e1x = bodyPos[3 * b] - ax, e1y = bodyPos[3 * b + 1] - ay
      const e1z = bodyPos[3 * b + 2] - az
      const e2x = bodyPos[3 * c] - ax, e2y = bodyPos[3 * c + 1] - ay
      const e2z = bodyPos[3 * c + 2] - az
      const nx = e1y * e2z - e1z * e2y
      const ny = e1z * e2x - e1x * e2z
      const nz = e1x * e2y - e1y * e2x
      const nl = Math.hypot(nx, ny, nz)
      if (nl < 1e-12) return 0
      const dx = pos[i3] - r.point.x, dy = pos[i3 + 1] - r.point.y
      const dz = pos[i3 + 2] - r.point.z
      return (dx * nx + dy * ny + dz * nz) / nl < 0 ? r.distance : 0
    },
    dispose() {
      geo.dispose()
    },
  }
}
