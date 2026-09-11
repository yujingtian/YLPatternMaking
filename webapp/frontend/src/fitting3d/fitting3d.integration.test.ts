// 真实 payload 端到端烟囱（引擎产物 -> 网格 -> 缝合摆位 -> PBD 解算）。
// 夹具 _fixture_fitting.json 由引擎侧生成（W=70 H=96 K=46 B=36 前浪25
// 后浪33 裤长102 大腿围58，默认选项；重生成命令见文件头注）：
//   python -c "import json; from ylpattern.exporters.fitting import
//     build_fitting_payload; from ylpattern.flows.back_flow import FULL_FLOW;
//     from ylpattern.flows.runner import FlowRunner;
//     from ylpattern.params import Measurements, PatternOptions;
//     m = Measurements(waist=70, hip=96, knee=46, hem=36, front_rise=25,
//       back_rise=33, outseam=102, thigh=58);
//     ctx = FlowRunner(m, PatternOptions()).run(FULL_FLOW);
//     json.dump(build_fitting_payload(ctx, m),
//       open('webapp/frontend/src/fitting3d/_fixture_fitting.json','w'))"
// 断言口径：链序/缝合配对/碰撞不穿透/解算有限不冻结——几何与拓扑
// 不变量，不钉具体构型（构型随先验收敛而变）。
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../types'
import { buildMannequin, radiusAt, sectionAt } from './mannequin'
import { buildClothMesh } from './mesh'
import { buildGarment } from './seams'
import { createSim, stepSim } from './pbd/solver'
import { SOLVER_PRIOR } from './priors'
import fixtureJson from './_fixture_fitting.json'

// 静态 import（Vite JSON 导入；勿用 node:fs——tsc 浏览器 lib 无其类型）
const payload = fixtureJson as unknown as FittingResult
const GIRTHS = { waist: 66, hip: 90, thigh: 54, knee: 35 }

describe('真实 payload 端到端（引擎 -> 3D 试穿）', () => {
  const front = payload.pieces.find((p) => p.key === 'front_piece')!
  const back = payload.pieces.find((p) => p.key === 'back_piece')!

  it('前后片网格：欧拉公式 + 缝合边名齐全', () => {
    for (const piece of [front, back]) {
      const mesh = buildClothMesh(piece)
      const V = mesh.xy.length / 2
      const F = mesh.tri.length / 3
      const edges = new Set<number>()
      for (let t = 0; t < mesh.tri.length; t += 3) {
        const v = [mesh.tri[t], mesh.tri[t + 1], mesh.tri[t + 2]]
        for (let e = 0; e < 3; e++) {
          const i = v[e], j = v[(e + 1) % 3]
          edges.add(i < j ? i * V + j : j * V + i)
        }
      }
      expect(V - edges.size + F).toBe(1)
      const names = mesh.runs.map((r) => r.name)
      for (const need of ['waist', 'side', 'hem', 'inseam']) {
        expect(names).toContain(need)
      }
      expect(names).toContain(front === piece ? 'rise' : 'cb')
    }
  })

  it('整裤摆位：缝合对完备、左负右正、初态不穿体', () => {
    const man = buildMannequin(payload.body, GIRTHS)
    const meshes = {
      front: buildClothMesh(front), back: buildClothMesh(back),
    }
    const g = buildGarment(meshes, man)
    expect(g.seam.length).toBeGreaterThan(100)
    // 腰口 pin = 4 半片 top_chain 采样点（~17cm ÷ 1.5cm ≈ 12 × 4）
    expect(g.pinIdx.length).toBeGreaterThan(30)
    for (const part of g.parts) {
      const sign = part.side === 'L' ? -1 : 1
      for (let i = 0; i < part.mesh.xy.length / 2; i++) {
        const x = g.pos[3 * (part.offset + i)]
        expect(sign * x).toBeGreaterThanOrEqual(-1e-6)   // 左半 x<=0 右半 x>=0
      }
    }
    // 初态支撑半径：任一粒子到所属管中心的距离 >= 体表半径（支撑摆位
    // 上界保证；松量已在 placePoint 里加过）。radiusAt 单位向量口径：
    // 未归一化输入使其返回向量倍数、判据空转（2026-09-09 修复）
    for (let i = 0; i < g.total; i++) {
      const px = g.pos[3 * i], py = g.pos[3 * i + 1], pz = g.pos[3 * i + 2]
      for (const tube of [man.pelvis, man.legs[0], man.legs[1]]) {
        const lo = tube.rings[tube.rings.length - 1].y
        const hi = tube.rings[0].y
        if (py < lo || py > hi) continue
        const s = sectionAt(tube, py)
        const dist = Math.hypot(px - s.cx, pz)
        if (dist < 1e-9) continue
        expect(dist).toBeGreaterThanOrEqual(
          radiusAt(s, (px - s.cx) / dist, pz / dist) - 0.5)
      }
    }
  })

  it('PBD 150 帧解算：有限、不冻结、缝合闭合、无穿透', () => {
    const man = buildMannequin(payload.body, GIRTHS)
    const g = buildGarment({
      front: buildClothMesh(front), back: buildClothMesh(back),
    }, man)
    const sim = createSim(g, man)
    let frozen = false
    for (let k = 0; k < 150; k++) {
      const st = stepSim(sim)
      if (st === 'frozen') { frozen = true; break }
      if (st === 'settled') break
    }
    expect(frozen).toBe(false)
    // 有限性
    for (let i = 0; i < sim.pos.length; i += 3) {
      expect(Number.isFinite(sim.pos[i])).toBe(true)
      expect(Number.isFinite(sim.pos[i + 1])).toBe(true)
      expect(Number.isFinite(sim.pos[i + 2])).toBe(true)
    }
    // 缝合闭合：配对粒子平均间距 < 1cm（预松弛 + 收敛后的焊合残差）
    let seamSum = 0
    for (let c = 0; c < g.seam.length; c += 2) {
      const a = 3 * g.seam[c], b = 3 * g.seam[c + 1]
      seamSum += Math.hypot(
        sim.pos[a] - sim.pos[b], sim.pos[a + 1] - sim.pos[b + 1],
        sim.pos[a + 2] - sim.pos[b + 2])
    }
    expect(seamSum / (g.seam.length / 2)).toBeLessThan(1)
    // 无穿透：碰撞投影后粒子在体表外（skin 余量；float32 存储 eps）。
    // radiusAt 单位向量口径 + collideSweeps 扫描后此断言才真正检验
    // 无穿透（修复前未归一化输入使其空转）。−0.15 容差（先例口径随实测
    // 收放：−0.01/−0.1/−0.15/−0.30 → 二轮微调后收回 −0.15：ham/腘窝上沿
    // 锚使大腿接触带 bB 增 → a 重标定收细、两腿壁分开，内缝焊合与碰撞
    // 推出的对抗减轻，实测最坏侵入 skin 余量带 0.283→0.082 @y66.0——
    // 全部粒子仍在各管真实表面外 ≥0.218cm，零可见穿模；容差语义 =
    // 不进真实表面，collideSweeps 维持 3（4 遍 +33% 每帧碰撞开销不值）
    const skin = SOLVER_PRIOR.collisionSkin
    for (let i = 0; i < g.total; i++) {
      const px = sim.pos[3 * i], py = sim.pos[3 * i + 1], pz = sim.pos[3 * i + 2]
      for (const tube of [man.pelvis, man.legs[0], man.legs[1]]) {
        const lo = tube.rings[tube.rings.length - 1].y
        const hi = tube.rings[0].y
        if (py < lo || py > hi) continue
        const s = sectionAt(tube, py)
        const dx = px - s.cx, dz = pz
        const dist = Math.hypot(dx, dz)
        if (dist < 1e-9) continue
        expect(dist).toBeGreaterThanOrEqual(
          radiusAt(s, dx / dist, dz / dist) + skin - 0.15)
      }
    }
    // 3 遍扫描下本测实测 33-36s（2 遍最坏残差 0.13 超 −0.1 容差，见
    // priors.ts collideSweeps 注释），超时给足 60s；全量并行 CPU 争抢下
    // 曾到 ~58s（30s/60s 预算间歇假红——几何断言全过），放宽 120s
  }, 120_000)
})
