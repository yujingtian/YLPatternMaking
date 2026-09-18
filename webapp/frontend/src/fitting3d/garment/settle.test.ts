// 穿台落位控制器金标（2026-09-18）：settle.ts 状态机全迹线 + frontness
// lerp 下放数学 + wake 续预算 + probeCrotch 壳口径。sim 为字面量 stub
//（不跑真解算——动力学正确性归 drape.test / dress.test），探针迹线经
// opts.probe 注入（可控穿透/净空时序）。fast 常数全用 opts 覆写，不碰
// DRESSING_PRIOR 真值。
import { describe, expect, it } from 'vitest'
import type { DrapeSim } from './drape'
import { DRAPE_PRIOR } from './priors'
import { DRESSING_PRIOR } from './priors'
import { CORE_SKIN } from './core'
import { buildSettle, probeCrotch, type SettleOptions } from './settle'
import { BodyField, type SliceRing } from './placement'

// 最小 sim stub：只填 settle 走到的字段（pos/pinTarget/计数器/wake 目标）
const mkSim = (pins: [number, number, number][]): DrapeSim => {
  const n = pins.length
  const pinIdx = new Uint32Array(n)
  const pinTarget = new Float32Array(3 * n)
  for (let k = 0; k < n; k++) {
    pinIdx[k] = k
    pinTarget[3 * k] = pins[k][0]
    pinTarget[3 * k + 1] = pins[k][1]
    pinTarget[3 * k + 2] = pins[k][2]
  }
  return {
    pos: new Float32Array(pinTarget),
    prev: new Float32Array(pinTarget),
    vel: new Float32Array(3 * n),
    pinIdx, pinTarget,
    seamIdx: new Uint32Array(0), seamGroups: [],
    yLift: 0, holdIdx: new Uint32Array(0), holdTarget: new Float32Array(0),
    parts: [], field: null, collideAboveY: -Infinity,
    maxFrames: DRAPE_PRIOR.maxFrames, stepCount: 0,
    settledFrames: 0, settled: false, capped: false, frozen: false,
    avgSpeed: 0, failStreak: 0, lastGood: new Float32Array(pinTarget),
  }
}

// 快进常数（覆盖 opts，不动真值）
const FAST: SettleOptions = {
  holdFrames: 3, dropRate: 0.5, deadZone: 0.3, maxDrop: 2.0,
  confirmFrames: 2, settleMaxFrames: 5, maxTotalFrames: 200,
}
// 钉三点：前中 (0,·,+10) f=0 / 侧 (+10,·,0) f=0.5 / 后中 (0,·,−10) f=1
const PINS: [number, number, number][] = [[0, 100, 10], [10, 101, 0], [0, 102, -10]]

describe('落位状态机（hold → lowering → settle → done）', () => {
  it('hold 相位不动钉；到 holdFrames 转 lowering', () => {
    const sim = mkSim(PINS)
    const ctrl = buildSettle(sim, { front: [], back: [] }, FAST)
    const y0 = sim.pinTarget[1]
    ctrl.step(sim)
    ctrl.step(sim)
    expect(ctrl.phase).toBe('hold')
    expect(sim.pinTarget[1]).toBe(y0)   // hold 不动钉（启动序列红线）
    ctrl.step(sim)                      // frames=3 ≥ holdFrames
    expect(ctrl.phase).toBe('lowering')
  })

  it('frontness lerp：前穿只降前钉——前 f=0 全额、侧 f=0.5 半额、后 f=1 不动', () => {
    const sim = mkSim(PINS)
    const ctrl = buildSettle(sim, { front: [], back: [] }, {
      ...FAST,
      probe: (_s, side) => side === 'front'
        ? { worst: 1.0, best: 1.0 } : { worst: 0, best: 0 },
    })
    for (let k = 0; k < 3; k++) ctrl.step(sim)   // 过 hold
    ctrl.step(sim)                                // 第 1 次下放 hF=−0.5
    expect(ctrl.hF).toBeCloseTo(-0.5, 10)
    expect(ctrl.hB).toBe(0)
    expect(sim.pinTarget[1]).toBeCloseTo(99.5, 10)    // 前 base 100 + hF
    expect(sim.pinTarget[4]).toBeCloseTo(100.75, 10)  // 侧 base 101 + hF/2
    expect(sim.pinTarget[7]).toBe(102)                // 后 base 102 + hB=0
    ctrl.step(sim)                                   // 第 2 次 hF=−1.0
    expect(sim.pinTarget[1]).toBeCloseTo(99.0, 10)
    expect(sim.pinTarget[7]).toBe(102)
  })

  it('持续穿透迹线：钳 maxDrop → fault 停放 → confirm → settle → 真静止 done', () => {
    const sim = mkSim(PINS)
    const ctrl = buildSettle(sim, { front: [], back: [] }, {
      ...FAST,
      probe: (_s, side) => side === 'front'
        ? { worst: 1.0, best: 1.0 } : { worst: 0, best: 0 },
    })
    for (let k = 0; k < 3; k++) ctrl.step(sim)   // hold 3 帧
    // lowering：dropRate 0.5 × 4 次到 maxDrop 2.0
    for (let k = 0; k < 4; k++) ctrl.step(sim)
    expect(ctrl.hF).toBeCloseTo(-2.0, 10)
    expect(ctrl.phase).toBe('lowering')
    // 仍穿且 h 已到底 → fault 停放（不与碰撞无限拔河）
    ctrl.step(sim)
    expect(ctrl.hF).toBeCloseTo(-2.0, 10)   // 不再下放
    // 双侧完成（front fault / back 入区）confirm 累计 2 帧 → settle
    ctrl.step(sim)
    expect(ctrl.phase).toBe('settle')
    // settle 只认真实静止：未静止时相位保持
    for (let k = 0; k < 3; k++) ctrl.step(sim)
    expect(ctrl.phase).toBe('settle')
    sim.settled = true
    expect(ctrl.step(sim)).toBe('done')
    // 报告：掉裝钳在 maxDrop、前裆穿透读数、tooSmall
    const rep = ctrl.report(sim)
    expect(rep.dropF).toBeCloseTo(2.0, 10)
    expect(rep.dropB).toBeCloseTo(0, 10)   // −hB 是 −0：数值断言不看符号位
    expect(rep.contactF).toEqual({ kind: 'pen', value: 1.0 })
    expect(rep.contactB.kind).toBe('touch')
    expect(rep.tooSmall).toBe(true)
    expect(rep.capped).toBe(false)
    expect(rep.worstPen).toBe(0)   // field null → 全粒子扫跳过
  })

  it('中途清零迹线：穿透解除 → confirm → settle → done（无 fault）', () => {
    const sim = mkSim(PINS)
    let frontPen = 1.0
    const ctrl = buildSettle(sim, { front: [], back: [] }, {
      ...FAST,
      probe: (_s, side) => side === 'front'
        ? { worst: frontPen, best: frontPen } : { worst: 0, best: 0 },
    })
    for (let k = 0; k < 3; k++) ctrl.step(sim)
    ctrl.step(sim)   // hF=−0.5（穿）
    ctrl.step(sim)   // hF=−1.0（穿）
    frontPen = 0     // 前裆进入净空
    ctrl.step(sim)   // doneF 入区 → confirm 1
    ctrl.step(sim)   // confirm 2 → settle
    expect(ctrl.phase).toBe('settle')
    sim.settled = true
    expect(ctrl.step(sim)).toBe('done')
    const rep = ctrl.report(sim)
    expect(rep.dropF).toBeCloseTo(1.0, 10)
    expect(rep.contactF.kind).toBe('touch')   // worst 0 ≤ deadZone、best ≥ −deadZone
    expect(rep.tooSmall).toBe(false)
  })

  it('report 接触三态：gap 报间隙值、无信息（−∞）钳 probeMargin', () => {
    const sim = mkSim(PINS)
    const mk = (front: number, back: number) => buildSettle(sim, {
      front: [], back: [],
    }, {
      ...FAST,
      probe: (_s, side) => side === 'front'
        ? { worst: front, best: front } : { worst: back, best: back },
    })
    expect(mk(-1.0, -Infinity).report(sim).contactF)
      .toEqual({ kind: 'gap', value: 1.0 })
    expect(mk(0, -Infinity).report(sim).contactB)
      .toEqual({ kind: 'gap', value: DRESSING_PRIOR.probeMargin })
  })

  it('wake：动钉帧清假 settled 并续帧预算（maxFrames ≥ stepCount+settleMax）', () => {
    const sim = mkSim(PINS)
    const ctrl = buildSettle(sim, { front: [], back: [] }, {
      ...FAST, holdFrames: 1,
      probe: (_s, side) => side === 'front'
        ? { worst: 1.0, best: 1.0 } : { worst: 0, best: 0 },
    })
    ctrl.step(sim)   // hold 1 帧 → lowering
    // 伪造假 settled + 预算将尽
    sim.settled = true
    sim.settledFrames = 30
    sim.capped = true
    sim.stepCount = 10
    sim.maxFrames = 11
    ctrl.step(sim)   // lowering 动钉 → wake
    expect(sim.settled).toBe(false)
    expect(sim.settledFrames).toBe(0)
    expect(sim.capped).toBe(false)
    expect(sim.maxFrames).toBeGreaterThanOrEqual(10 + 5)
  })

  it('maxTotalFrames 硬顶：无论 sim 状态到帧即 done 且 capped', () => {
    const sim = mkSim(PINS)
    const ctrl = buildSettle(sim, { front: [], back: [] }, { ...FAST, maxTotalFrames: 6 })
    let ph = ctrl.phase
    for (let k = 0; k < 6; k++) ph = ctrl.step(sim)
    expect(ph).toBe('done')
    expect(ctrl.report(sim).capped).toBe(true)
  })

  it('frozen（发散冻结）：保终态直出 done', () => {
    const sim = mkSim(PINS)
    const ctrl = buildSettle(sim, { front: [], back: [] }, FAST)
    sim.frozen = true
    expect(ctrl.step(sim)).toBe('done')
    expect(ctrl.report(sim).capped).toBe(true)
  })
})

describe('probeCrotch（裆接触探针壳口径，合成环场）', () => {
  const ring = (cx: number, cz: number, r: number, n = 16): SliceRing => {
    const pts = new Float64Array(2 * n)
    for (let k = 0; k < n; k++) {
      const th = (k / n) * 2 * Math.PI
      pts[2 * k] = cx + r * Math.cos(th)
      pts[2 * k + 1] = cz + r * Math.sin(th)
    }
    return { pts, cx, cz, r }
  }
  // 单环 r=5；row0 有环、row1/2 空（验 yLift 回纸样空间行选择）
  const R = ring(0, 0, 5)
  const field = new BodyField(new Float32Array(3 * 8), 3, 0.5, 8, [[R], [], []])

  it('环内深穿 / 环外近壳 / 远处净空钳 probeMargin', () => {
    const sim = mkSim([[0, 0.1, 0], [6, 0.1, 0], [20, 0.1, 0]])
    sim.field = field
    sim.pos.set(sim.pinTarget)   // pos = pinTarget（stub 直摆探针点）
    const { worst, best } = probeCrotch(sim, [0, 1, 2])
    // 环内：v = skin + d（d≈4.95 深穿）
    expect(worst).toBeGreaterThan(CORE_SKIN + 4.9)
    expect(worst).toBeLessThan(CORE_SKIN + 5.0)
    // 6,0 环外：v = skin − d ≈ −0.07；20,0 无 hit：−probeMargin
    expect(best).toBeCloseTo(-DRESSING_PRIOR.probeMargin, 10)
    // 逐点单测钳值
    expect(probeCrotch(sim, [2]).worst).toBeCloseTo(-DRESSING_PRIOR.probeMargin, 10)
    expect(probeCrotch(sim, [1]).worst).toBeGreaterThan(-0.2)
    expect(probeCrotch(sim, [1]).worst).toBeLessThan(0.0)
  })

  it('yLift 回纸样空间：行选择按 pos.y − yLift（空行跳过 = 无信息）', () => {
    const sim = mkSim([[0, 1.2, 0], [0, 1.9, 0]])
    sim.field = field
    sim.yLift = 1
    sim.pos.set(sim.pinTarget)
    // y'=0.2 → row0 有环（深穿）；y'=0.9 → row2 空行（跳过）
    expect(probeCrotch(sim, [0]).worst).toBeGreaterThan(CORE_SKIN + 4.9)
    expect(probeCrotch(sim, [1]).worst).toBe(-Infinity)
  })
})
