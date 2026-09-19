// 整裤缝合解算金标（2026-09-17 八期）：buildFullPair 四 part 摆位 +
// seams.buildSeamSet 全族缝合对（前中/后中镜像 + 侧缝/内缝弧长 + 裆尖
// 补焊）+ **自由垂**（同日用户口径「只保留腰部圆形撑开，其他地方真实
// 物理垂挂」——腰口整圈钉 = 圆形撑环、其下自重褶皱垂挂；芯碰撞版当
// 日早段已完成又被本口径取代，见决策日志），从初始摆位解算至静止。验收口径：
// · 600 帧内真 settle（capped=false 非封顶）、无 NaN、发散兜底未触发
// · 腰口整圈钉恒守初始位（360° 腰圆支点 = 用户口径①「侧缝缝合形成
//   腰圆」的钉侧验收）
// · 四族缝 stats 分族达标（三款实测：rise/cb/inseam/tip 全族 avg=p95=0
//   ——镜像/相邻共线摆位起点即闭、无对抗；side avg 0.026/p95 0.176——
//   吃势均匀吸收）：阈值 rise/cb avg<0.1/p95<0.3、side avg<0.15/p95<0.5、
//   inseam avg<0.3/p95<0.8
// · 裆四尖两两最大距 <1cm（零 rest 闭环自动坍缩 = 用户口径③「两内缝+
//   前中缝+后中缝汇集到裆交叉点」的量化）
// · 侧缝首对（两侧腰角，snap 共点 + 双钉）终态 <0.5cm
// · 不拖地 minY>1（hangLift 重定标后离地余量）
// · 终态纸样空间穿透零（pos 减 yLift 后 penetrationStats——碰撞按构造
//   保证，拦 NaN/飞点）
// 夹具 = 基础款 / 袋贴款 / 育克款（引擎 build_fitting_payload 直出）+
// 有省款（yoke 守卫拦下退化纯后片宿主，整裤照常成立）。
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../types'
import { buildFullPair, type Garment } from './assemble'
import { buildCore, buildLegAxis } from './core'
import { buildBodyField, pointInRings } from './placement'
import { buildDrape, seamStatsByGroup, stepDrape, type DrapeSim } from './drape'
import { buildBackPanel, buildFrontPanel } from './panel'
import { bandBottomChain, buildWaistbandMesh } from './band'
import { DRAPE_PRIOR } from './priors'

const HERE = import.meta.dirname   // src/fitting3d/garment

const load = (fx: string): FittingResult =>
  JSON.parse(readFileSync(`${HERE}/${fx}`, 'utf8'))

const runToSettle = (sim: DrapeSim) => {
  let st: ReturnType<typeof stepDrape> = 'running'
  for (let k = 0; k < DRAPE_PRIOR.maxFrames && st === 'running'; k++) {
    st = stepDrape(sim)
  }
  return st
}

const minY = (pos: Float32Array): number => {
  let m = Infinity
  for (let i = 1; i < pos.length; i += 3) m = Math.min(m, pos[i])
  return m
}

// 整裤通用口径（三夹具 + 退化款共用；degradedSide = 有省退化款放宽
// side 族阈值——back 宿主缺育克矮 ~4cm，腰口端锚定的 side 缝对固有开口；
// field 可空 = 自由垂口径〔腰部圆形撑开 + 真实物理垂挂，2026-09-17〕，
// 穿透查验只在有场时跑）
function assertFullPants(
  sim: DrapeSim, placed: Garment,
  opts?: { degradedSide?: boolean },
): void {
  expect(sim.capped).toBe(false)   // 真静止，非封顶兜底
  expect(sim.frozen).toBe(false)
  for (let i = 0; i < sim.pos.length; i++) {
    expect(Number.isFinite(sim.pos[i])).toBe(true)
  }
  // 腰口整圈钉恒守初始位（四 part 360° 腰圆支点）
  for (let k = 0; k < sim.pinIdx.length; k++) {
    const i3 = 3 * sim.pinIdx[k]
    expect(sim.pos[i3]).toBeCloseTo(sim.pinTarget[3 * k], 6)
    expect(sim.pos[i3 + 1]).toBeCloseTo(sim.pinTarget[3 * k + 1], 6)
    expect(sim.pos[i3 + 2]).toBeCloseTo(sim.pinTarget[3 * k + 2], 6)
  }
  // 钉集覆盖（挂腰头口径互斥）：有腰头 = **只**钉带顶（'top' run，
  // 身片顶弧经 bandWaist 缝挂不直钉——钉与缝二选一）；无腰头 = Σ 各
  // 身片（顶链 + 终点角）
  const bandP = placed.parts.find((p) => p.key === 'waistband')
  let need = 0
  for (const p of placed.parts) {
    if (p === bandP) {
      need += (p.mesh.runs.find((r) => r.name === 'top')?.indices.length ?? 0) + 1
      need += bandBottomChain(p.mesh)?.indices.length ?? 0
    } else {
      need += p.mesh.runs.find((r) => r.role === 'top_chain')!.indices.length + 1
    }
  }
  expect(sim.pinIdx.length).toBeGreaterThanOrEqual(need)
  // ---- 四族缝 stats（分族阈值，首跑实测后收紧写注释）----
  const st = seamStatsByGroup(sim)
  for (const name of ['rise', 'cb']) {
    expect(st[name].avg, `${name} avg`).toBeLessThan(0.1)
    expect(st[name].p95, `${name} p95`).toBeLessThan(0.3)
  }
  for (const name of ['sideL', 'sideR']) {
    if (opts?.degradedSide) {
      expect(st[name].avg, `${name} avg（退化开口）`).toBeLessThan(1.0)
      expect(st[name].p95, `${name} p95（退化开口）`).toBeLessThan(5.0)
    } else {
      expect(st[name].avg, `${name} avg`).toBeLessThan(0.15)
      expect(st[name].p95, `${name} p95`).toBeLessThan(0.5)
    }
  }
  for (const name of ['inseamL', 'inseamR']) {
    expect(st[name].avg, `${name} avg`).toBeLessThan(0.3)
    expect(st[name].p95, `${name} p95`).toBeLessThan(0.8)
  }
  // 腰头两族（九期）：bandWaist 摆位即闭（带底=环顶点原位）；bandEnds
  // 前中 weld。弯款省道吃势会让 bandWaist 稍开（阈值放宽档）
  if (st.bandWaist) {
    expect(st.bandWaist.avg, 'bandWaist avg').toBeLessThan(0.1)
    expect(st.bandWaist.p95, 'bandWaist p95').toBeLessThan(0.3)
  }
  if (st.bandEnds) {
    expect(st.bandEnds.avg, 'bandEnds avg').toBeLessThan(0.3)
    expect(st.bandEnds.p95, 'bandEnds p95').toBeLessThan(1.0)
  }
  // ---- 裆四尖汇集（口径③量化）：tipL/tipR 两对共四顶点两两最大距 ----
  const tips: number[] = []
  for (const g of sim.seamGroups) {
    if (g.name !== 'tipL' && g.name !== 'tipR') continue
    for (let p = 0; p < g.pairCount; p++) {
      tips.push(sim.seamIdx[2 * (g.pairOffset + p)],
        sim.seamIdx[2 * (g.pairOffset + p) + 1])
    }
  }
  expect(tips.length).toBe(4)
  let tipWorst = 0
  for (let a = 0; a < 4; a++) {
    for (let b = a + 1; b < 4; b++) {
      tipWorst = Math.max(tipWorst, Math.hypot(
        sim.pos[3 * tips[a]] - sim.pos[3 * tips[b]],
        sim.pos[3 * tips[a] + 1] - sim.pos[3 * tips[b] + 1],
        sim.pos[3 * tips[a] + 2] - sim.pos[3 * tips[b] + 2]))
    }
  }
  expect(tipWorst).toBeLessThan(1.0)
  // ---- 腰圆闭合：sideL 首对 = 两侧缝腰角（snap 共点 + 双钉）----
  const sideL = sim.seamGroups.find((g) => g.name === 'sideL')!
  const a0 = 3 * sim.seamIdx[2 * sideL.pairOffset]
  const b0 = 3 * sim.seamIdx[2 * sideL.pairOffset + 1]
  expect(Math.hypot(sim.pos[a0] - sim.pos[b0],
    sim.pos[a0 + 1] - sim.pos[b0 + 1], sim.pos[a0 + 2] - sim.pos[b0 + 2]))
    .toBeLessThan(0.5)
  // 不拖地（hangLift 重定标后离地余量；地面碰撞安全网）
  expect(minY(sim.pos)).toBeGreaterThan(1)
  // 终态纸样空间穿透零（截面环口径：两腿分离芯的腿间空隙是合法布位，
  // 旧径向查验会把内侧线布误判穿透——pos 减 yLift 回摆位空间再查环内；
  // 门控跟 sim.field 走：自由垂口径 sim 无碰撞体自然跳过〔摆位用的场
  // 不参与解算，不能拿来查〕）
  if (sim.field) {
    // 只查碰撞段（腿段自由垂、摊平布本就穿过腿管环位——混合形态口径）
    let penCount = 0
    for (let i3 = 0; i3 < sim.pos.length; i3 += 3) {
      if (sim.pos[i3 + 1] - sim.yLift < sim.collideAboveY) continue
      if (pointInRings(sim.pos[i3], sim.pos[i3 + 2],
        sim.field.loopsAt(sim.pos[i3 + 1] - sim.yLift))) penCount++
    }
    expect(penCount).toBe(0)
  }
}

const buildPant = (payload: FittingResult): {
  sim: DrapeSim, placed: Garment
} => {
  const frontPanel = buildFrontPanel(payload)
  const backPanel = buildBackPanel(payload)
  const core = buildCore(payload)
  const field = buildBodyField(core.positions, core.indices)
  const placed = buildFullPair(frontPanel.host, backPanel.host, field, {
    front: payload.body.points.front_crotch_vertex[1],
    back: payload.body.points.back_crotch_vertex[1],
  }, buildLegAxis(payload), buildWaistbandMesh(payload))
  // 全域自由垂（（十一）用户口径「腰头一圈+下面真实物理悬挂」；（九）
  // 混合形态机制保留在 drape 备用——正确度量证实自由垂截面前后基本
  // 对称，山脊=缝尖折痕，由加宽的缝头摊平窗处理）
  const sim = buildDrape(placed, null)
  return { sim, placed }
}

describe('drape：整裤缝合芯碰撞解算（八期）——基础款', () => {
  it('600 帧内真收敛、整圈钉恒守、四族缝达标、裆汇集、不拖地、穿透零',
    { timeout: 300000 }, () => {
      const { sim, placed } = buildPant(load('fixture_fitting.json'))
      const st = runToSettle(sim)
      expect(st).toBe('settled')
      assertFullPants(sim, placed)
    })
})

describe('drape：整裤缝合芯碰撞解算（八期）——袋贴款（前身并集宿主）', () => {
  it('袋贴月牙带并入宿主后整裤全部口径照旧', { timeout: 300000 }, () => {
    const payload = load('fixture_fitting_pocket.json')
    expect(buildFrontPanel(payload).hasFacing).toBe(true)   // 前置：并集成功
    const { sim, placed } = buildPant(payload)
    const st = runToSettle(sim)
    expect(st).toBe('settled')
    assertFullPants(sim, placed)
  })
})

describe('drape：整裤缝合芯碰撞解算（八期）——育克款（后身并集宿主）', () => {
  it('育克拼入后整裤全部口径照旧（后浪贯通 + side 双 run 合链配对）',
    { timeout: 300000 }, () => {
      const payload = load('fixture_fitting_yoke.json')
      expect(buildBackPanel(payload).hasYoke).toBe(true)    // 前置：并集成功
      const { sim, placed } = buildPant(payload)
      const st = runToSettle(sim)
      expect(st).toBe('settled')
      assertFullPants(sim, placed)
    })
})

describe('drape：整裤缝合芯碰撞解算（八期）——有省款退化（yoke 守卫拦下）', () => {
  // 已知退化形态：back 宿主缺育克矮 ~4cm（top 边升格 top_chain 钉挂），
  // side 缝对腰口端锚定的前后腰角高差拉不满——sideL/R avg ~0.42/p95
  // ~3.7 属该款固有（3D 展示侧栏 panelHint 已警示退化原因）
  it('退化纯后片宿主整裤成立（side 退化开口，其余口径照常）', { timeout: 300000 }, () => {
    const payload = load('fixture_fitting_curved_pocket.json')
    expect(buildBackPanel(payload).hasYoke).toBe(false)     // 前置：守卫拦下
    const { sim, placed } = buildPant(payload)
    const st = runToSettle(sim)
    expect(st).toBe('settled')
    assertFullPants(sim, placed, { degradedSide: true })
  })
})

describe('drape：脚口环带刚度 stamp（2026-09-19（二）脚口前缘脱扣修复）', () => {
  // 真实牛仔裤脚口 = 双折卷边+车缝硬圈：hem 链 hemBandSpan 内弯曲约束
  // 刚度升 hemBandStiffness（抗剪切压折——穿台掉裆加深时环口保持圆形、
  // 前缘不滑过脚背冠）。验收 = 第三窗存在性：「只被 hem 窗覆盖」的约束
  // （缝口摊平/腰臀过渡两窗皆窗外）必须取 hemBandStiffness——删 hem 窗
  // 即回落 0.3 假绿；大腿中段对照回落 bendStiffness。k/span 窗口地图
  // 见 priors.hemBandStiffness 注释（3/3.5/6 与 k 0.8/1.0 均已证伪）
  it('hem 窗覆盖约束取 hemBandStiffness、三窗外回落 bendStiffness', { timeout: 60000 }, () => {
    const { placed } = buildPant(load('fixture_fitting.json'))
    let inHem = 0, hemOnly = 0, plain = 0
    const seen = new Set<unknown>()
    for (const part of placed.parts) {
      if (part.key === 'waistband' || seen.has(part.mesh)) continue
      seen.add(part.mesh)   // L/R 共享 ClothMesh，重复写同值幂等
      const mesh = part.mesh
      expect(mesh.bendKArr).toBeDefined()
      const ptsOf = (names: string[]): number[] => {
        const pts: number[] = []
        for (const r of mesh.runs) {
          if (!names.includes(r.name)) continue
          for (const i of r.indices) pts.push(mesh.xy[2 * i], mesh.xy[2 * i + 1])
        }
        return pts
      }
      const hemPts = ptsOf(['hem'])
      const seamPts = ptsOf(['side', 'inseam'])
      expect(hemPts.length).toBeGreaterThan(0)
      const dMin = (pts: number[], x: number, y: number): number => {
        let d = Infinity
        for (let k = 0; k < pts.length; k += 2) {
          d = Math.min(d, Math.hypot(pts[k] - x, pts[k + 1] - y))
        }
        return d
      }
      const top = mesh.runs.find((r) => r.role === 'top_chain')
      let topY = -Infinity
      if (top) {
        for (const i of top.indices) topY = Math.max(topY, mesh.xy[2 * i + 1])
      }
      for (let c = 0; c < mesh.bend.length; c += 3) {
        const i = mesh.bend[c], j = mesh.bend[c + 1]
        const mx = (mesh.xy[2 * i] + mesh.xy[2 * j]) / 2
        const my = (mesh.xy[2 * i + 1] + mesh.xy[2 * j + 1]) / 2
        const dHem = dMin(hemPts, mx, my)
        const dSeam = dMin(seamPts, mx, my)
        const inTrans = topY > -Infinity
          && my >= topY - DRAPE_PRIOR.waistTransitionSpan
        if (dHem < DRAPE_PRIOR.hemBandSpan) {
          inHem++
          if (dSeam >= DRAPE_PRIOR.seamFlattenSpan && !inTrans) {
            expect(mesh.bendKArr![c / 3], 'hem-only 约束刚度')
              .toBe(DRAPE_PRIOR.hemBandStiffness)
            hemOnly++
          }
        } else if (dSeam >= DRAPE_PRIOR.seamFlattenSpan && !inTrans) {
          // Float32 量化：0.3 存不精确（本仓已知坑），CloseTo 6 位
          expect(mesh.bendKArr![c / 3], '三窗外约束刚度')
            .toBeCloseTo(DRAPE_PRIOR.bendStiffness, 6)
          plain++
        }
      }
    }
    // 规模把门（diag 实测 front+back 两 mesh 合计 stamp ~285 约束；
    // 腰头无 hem 链被跳过）
    expect(inHem).toBeGreaterThan(100)
    expect(hemOnly).toBeGreaterThan(10)
    expect(plain).toBeGreaterThan(50)
  })
})
