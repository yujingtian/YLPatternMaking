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
import {
  BodyField, buildWaistRing, ringPointAt, type SliceRing,
} from './placement'

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
    pinFlag: new Uint8Array(n).fill(1),   // stub 全顶点皆钉（pinIdx[k]=k）
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

  it('hold 提前转（1c）：settledFrames 达全局静止判据即转 lowering，holdFrames 退居上限', () => {
    const sim = mkSim(PINS)
    const ctrl = buildSettle(sim, { front: [], back: [] }, FAST)
    sim.settledFrames = DRAPE_PRIOR.settleFrames   // 布已静（判据真值，非 FAST 覆写）
    ctrl.step(sim)   // frames=1 < holdFrames=3，但 settledFrames 先达 → 提前转
    expect(ctrl.phase).toBe('lowering')
  })

  it('hold 提前转不越界：settledFrames 差一帧不触发，仍守 holdFrames 上限', () => {
    const sim = mkSim(PINS)
    const ctrl = buildSettle(sim, { front: [], back: [] }, FAST)
    sim.settledFrames = DRAPE_PRIOR.settleFrames - 1
    ctrl.step(sim)
    ctrl.step(sim)
    expect(ctrl.phase).toBe('hold')   // 未静且 frames=2 < 3
    ctrl.step(sim)                     // frames=3 ≥ holdFrames 上限兜底
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

// ---- 挂胯判据 jam（2026-09-23 P1）：合成行周长场三例——卡停精确性 /
// jam-fault 互斥 / 前后独立。行为模型：不可伸长闭环（总长 C）套不进
// 周长 > C×(1+jamMargin) 的截面 → 钉在卡停行冻结（真人裤子滑到胯骨
// 滑不动即停的钉扎等价，settle.ts 头注）----
describe('挂胯判据 jam（合成行周长场）', () => {
  // 圆近似 64 边形环：闭弦周长恰 = perim（chord = 2R·sin(π/n)，n 段合计）
  const polyRing = (perim: number): SliceRing => {
    const n = 64
    const R = perim / (2 * n * Math.sin(Math.PI / n))
    const pts = new Float64Array(2 * n)
    for (let k = 0; k < n; k++) {
      const th = (k / n) * 2 * Math.PI
      pts[2 * k] = R * Math.cos(th)
      pts[2 * k + 1] = R * Math.sin(th)
    }
    return { pts, cx: 0, cz: 0, r: R }
  }
  // 行周长向下单调涨：yMin 97 / rowStep 0.5（= dropRate 每档恰 1 行），
  // 行 r → y=97+0.5r，rowPerim(r) = 50+2(6−r)（腰行 y=100 即行 6）
  const jamField = (): BodyField => {
    const slices: SliceRing[][] = []
    for (let r = 0; r < 9; r++) {
      slices.push(r <= 6 ? [polyRing(50 + 2 * (6 - r))] : [])
    }
    return new BodyField(new Float32Array(9 * 8), 9, 0.5, 8, slices, 97)
  }
  // 环长 C：阈值 C×1.02 = 59 恰落行 2（58）与行 1（60）之间——行 2 是
  // 周长 < 阈值的最深可停档、候选行 1 卡停
  const JAM = { jam: { ringTotal: 59 / 1.02, rowY: 100 } }
  const PEN = { worst: 1.0, best: 1.0 }
  const CLEAR = { worst: 0, best: 0 }

  it('卡停位置精确：jam 恰停在周长 < C×1.02 的最深档、drop 精确到档', () => {
    const sim = mkSim(PINS)
    sim.field = jamField()
    const ctrl = buildSettle(sim, { front: [], back: [] }, {
      ...FAST, maxDrop: 4.0, ...JAM,
      probe: (_s, side) => side === 'front' ? PEN : CLEAR,
    })
    for (let k = 0; k < 3; k++) ctrl.step(sim)   // hold 3 帧
    // lowering：行 5/4/3/2 周长 52/54/56/58 < 59 照放；第 5 次候选行 1
    //（60 ≥ 59）卡停——恰停行 2（最深可容档），drop 精确到档 2.0
    for (let k = 0; k < 5; k++) ctrl.step(sim)
    expect(ctrl.hF).toBeCloseTo(-2.0, 10)
    // jam 粘滞：后续帧不动钉（changed 不置位、无需 wake）
    const yPin = sim.pinTarget[1]
    for (let k = 0; k < 3; k++) ctrl.step(sim)
    expect(ctrl.hF).toBeCloseTo(-2.0, 10)
    expect(sim.pinTarget[1]).toBe(yPin)
    // confirm → settle → 预算尽 done；报告 jamF 直读 state
    for (let k = 0; k < 12; k++) ctrl.step(sim)
    expect(ctrl.phase).toBe('done')
    const rep = ctrl.report(sim)
    expect(rep.jamF).toBe(true)
    expect(rep.jamB).toBe(false)
    expect(rep.dropF).toBeCloseTo(2.0, 10)
    expect(rep.contactF).toEqual({ kind: 'pen', value: 1.0 })
    expect(rep.tooSmall).toBe(true)
  })

  it('jam 与 fault 互斥：行周长处处可容 → 到底仍穿走 fault，不受 jam 影响', () => {
    const sim = mkSim(PINS)
    // 全场周长 50 + 空行交错（空行周长 0 亦恒不拦 = 安全缺省）
    const slices: SliceRing[][] = []
    for (let r = 0; r < 9; r++) slices.push(r % 2 ? [] : [polyRing(50)])
    sim.field = new BodyField(new Float32Array(9 * 8), 9, 0.5, 8, slices, 97)
    const ctrl = buildSettle(sim, { front: [], back: [] }, {
      ...FAST, ...JAM,   // maxDrop 2.0
      probe: (_s, side) => side === 'front' ? PEN : CLEAR,
    })
    for (let k = 0; k < 3; k++) ctrl.step(sim)
    for (let k = 0; k < 4; k++) ctrl.step(sim)   // 4 档钳 maxDrop −2.0
    ctrl.step(sim)                                // 到底仍穿 → fault（非 jam）
    expect(ctrl.hF).toBeCloseTo(-2.0, 10)
    for (let k = 0; k < 10; k++) ctrl.step(sim)
    expect(ctrl.phase).toBe('done')
    const rep = ctrl.report(sim)
    expect(rep.jamF).toBe(false)   // fault 路径不受 jam 影响（互斥）
    expect(rep.dropF).toBeCloseTo(2.0, 10)
    expect(rep.contactF.kind).toBe('pen')
  })

  it('前后独立：jamF 侧卡停后，jamB 侧继续独立下放入区', () => {
    const sim = mkSim(PINS)
    sim.field = jamField()
    let backPen = 1.0
    const ctrl = buildSettle(sim, { front: [], back: [] }, {
      ...FAST, maxDrop: 4.0, ...JAM,
      probe: (_s, side) => side === 'front' ? PEN
        : { worst: backPen, best: backPen },
    })
    for (let k = 0; k < 3; k++) ctrl.step(sim)
    ctrl.step(sim)   // 双侧各下放 1 档（行 5 周长 52 可容）
    ctrl.step(sim)   // 前 −1.0；后 −1.0
    backPen = 0      // 后裆入区 → 后侧停（非 jam）
    for (let k = 0; k < 8; k++) ctrl.step(sim)   // 前再放 2 档 → 行 1 卡停
    expect(ctrl.hF).toBeCloseTo(-2.0, 10)
    expect(ctrl.hB).toBeCloseTo(-1.0, 10)   // 后侧不被前侧 jam 拖停
    for (let k = 0; k < 6; k++) ctrl.step(sim)
    expect(ctrl.phase).toBe('done')
    const rep = ctrl.report(sim)
    expect(rep.jamF).toBe(true)
    expect(rep.jamB).toBe(false)
  })
})

// ---- P2 钉环随行重投影（2026-09-23）：lowering 下放后钉 XZ 不冻结——
// 有弧位的钉沿参考环 buildWaistRing(field, 自身参考行, C) 重投影（C 恒定
// → s 直通）。合成场手推锚：同心等周长圆环行互为平移 → 重投影环 = 行环
// 平移，整档 drop 后钉位移恰 = 行心位移、半档 = 线性插值份额——与
// buildWaistRing 内部实现无关的独立几何断言 ----
describe('钉环随行重投影（P2，合成参考环场）', () => {
  const polyRingC = (perim: number, cx: number, cz: number): SliceRing => {
    const n = 64
    const R = perim / (2 * n * Math.sin(Math.PI / n))
    const pts = new Float64Array(2 * n)
    for (let k = 0; k < n; k++) {
      const th = (k / n) * 2 * Math.PI
      pts[2 * k] = cx + R * Math.cos(th)
      pts[2 * k + 1] = cz + R * Math.sin(th)
    }
    return { pts, cx, cz, r: R }
  }
  // 行布局：row0 y=96（周长 66 = jam 墙）/ row1 y=96.5（圆心 (3,2)、周长
  // C）/ row2 y=97（圆心原点、周长 C = 腰行，钉起点）
  const C = 60
  const mkField = (row1: SliceRing[]): BodyField =>
    new BodyField(new Float32Array(3 * 8), 3, 0.5, 8, [
      [polyRingC(66, 0, 0)], row1, [polyRingC(C, 0, 0)],
    ], 96)
  const JAM2 = { jam: { ringTotal: C, rowY: 97 } }
  const PEN = { worst: 1.0, best: 1.0 }
  const CLEAR = { worst: 0, best: 0 }

  it('形状随行：整档 drop 后钉落参考行环上（位移 = 行心位移）+ jam 共存', () => {
    const field = mkField([polyRingC(C, 3, 2)])
    const start = ringPointAt(buildWaistRing(field, 97, C), 0)   // 前中 f=0
    const sim = mkSim([[start.x, 97, start.z]])
    sim.field = field
    sim.pinArcs = new Float64Array([0])
    const ctrl = buildSettle(sim, { front: [], back: [] }, {
      ...FAST, maxDrop: 4.0, ...JAM2,
      probe: (_s, side) => side === 'front' ? PEN : CLEAR,
    })
    for (let k = 0; k < 3; k++) ctrl.step(sim)   // hold
    ctrl.step(sim)   // hF=−0.5 → yT=96.5 恰 row1 档 → 重投影
    expect(ctrl.hF).toBeCloseTo(-0.5, 10)
    expect(sim.pinTarget[1]).toBeCloseTo(96.5, 10)
    const exp = ringPointAt(buildWaistRing(field, 96.5, C), 0)
    expect(sim.pinTarget[0]).toBeCloseTo(exp.x, 4)
    expect(sim.pinTarget[2]).toBeCloseTo(exp.z, 4)
    // 手推锚：两行等周长同心圆 → 重投影环 = 行环平移 → 钉位移 = 行心位移
    expect(sim.pinTarget[0] - start.x).toBeCloseTo(3, 4)
    expect(sim.pinTarget[2] - start.z).toBeCloseTo(2, 4)
    // 再放候选 row0（66 ≥ C×1.02）→ jam 卡停；弧位钉随 jam 冻结
    ctrl.step(sim)
    expect(ctrl.hF).toBeCloseTo(-0.5, 10)
    for (let k = 0; k < 12; k++) ctrl.step(sim)
    expect(ctrl.phase).toBe('done')
    expect(ctrl.report(sim).jamF).toBe(true)
    expect(sim.pinTarget[0]).toBeCloseTo(exp.x, 4)
    expect(sim.pinTarget[2]).toBeCloseTo(exp.z, 4)
  })

  it('档间线性插值：半档 drop → 钉位 = 相邻两档环位线性插值（侧钉 f≈0.5）', () => {
    const field = mkField([polyRingC(C, 3, 2)])
    const start = ringPointAt(buildWaistRing(field, 97, C), 15)  // C/4 侧向
    const sim = mkSim([[start.x, 97, start.z]])
    sim.field = field
    sim.pinArcs = new Float64Array([15])
    let frontPen = 1.0
    const ctrl = buildSettle(sim, { front: [], back: [] }, {
      ...FAST, dropRate: 0.25, ...JAM2,
      probe: (_s, side) => side === 'front'
        ? { worst: frontPen, best: frontPen } : CLEAR,
    })
    for (let k = 0; k < 3; k++) ctrl.step(sim)
    ctrl.step(sim)   // hF=−0.25 → yT≈96.875（f≈0.5）→ 档 1、fr≈0.75
    frontPen = 0
    for (let k = 0; k < 12; k++) ctrl.step(sim)
    expect(ctrl.phase).toBe('done')
    // 手推锚：XZ = 档1环 + fr·(档2环 − 档1环)，相对初始位移 = (1−fr)·行心
    // 位移 = 0.25×(3,2)
    expect(sim.pinTarget[0]).toBeCloseTo(start.x + 0.75, 4)
    expect(sim.pinTarget[2]).toBeCloseTo(start.z + 0.5, 4)
    expect(sim.pinTarget[1]).toBeCloseTo(96.875, 6)
  })

  it('多环行守卫：参考行 loopsAt ≠ 1 环 → 钉 XZ 冻结（防御兜底，Y 照降）', () => {
    // 两环各周长 30（和 = C < C×1.02 → 不 jam，下放照走）
    const field = mkField([polyRingC(30, 5, 5), polyRingC(30, -5, -5)])
    const start = ringPointAt(buildWaistRing(field, 97, C), 0)
    const sim = mkSim([[start.x, 97, start.z]])
    sim.field = field
    sim.pinArcs = new Float64Array([0])
    const t0 = new Float32Array(sim.pinTarget)   // Float32 位级对照快照
    let frontPen = 1.0
    const ctrl = buildSettle(sim, { front: [], back: [] }, {
      ...FAST, ...JAM2,
      probe: (_s, side) => side === 'front'
        ? { worst: frontPen, best: frontPen } : CLEAR,
    })
    for (let k = 0; k < 3; k++) ctrl.step(sim)
    ctrl.step(sim)   // hF=−0.5 → 参考行 row1 双环 → 无参考环 → XZ 冻结
    frontPen = 0
    for (let k = 0; k < 12; k++) ctrl.step(sim)
    expect(ctrl.phase).toBe('done')
    expect(sim.pinTarget[0]).toBe(t0[0])   // Float32 位级不动
    expect(sim.pinTarget[2]).toBe(t0[2])
    expect(sim.pinTarget[1]).toBeCloseTo(96.5, 10)   // Y 照旧下放
  })

  it('混合钉集：有弧位钉随行、无弧位钉（NaN）XZ 冻结', () => {
    const field = mkField([polyRingC(C, 3, 2)])
    const start = ringPointAt(buildWaistRing(field, 97, C), 0)
    const sim = mkSim([[start.x, 97, start.z], [start.x, 97, start.z]])
    sim.field = field
    sim.pinArcs = new Float64Array([0, NaN])
    const t0 = new Float32Array(sim.pinTarget)
    let frontPen = 1.0
    const ctrl = buildSettle(sim, { front: [], back: [] }, {
      ...FAST, ...JAM2,
      probe: (_s, side) => side === 'front'
        ? { worst: frontPen, best: frontPen } : CLEAR,
    })
    for (let k = 0; k < 3; k++) ctrl.step(sim)
    ctrl.step(sim)
    frontPen = 0
    for (let k = 0; k < 12; k++) ctrl.step(sim)
    expect(ctrl.phase).toBe('done')
    expect(sim.pinTarget[0]).toBeCloseTo(start.x + 3, 4)   // 钉0 随行
    expect(sim.pinTarget[3]).toBe(t0[3])                   // 钉1 冻结
    expect(sim.pinTarget[5]).toBe(t0[5])
    expect(sim.pinTarget[4]).toBeCloseTo(96.5, 10)         // Y 都降
  })

  it('激活门槛：缺 pinArcs 或缺 jam → 旧口径（XZ 冻结只降 Y）', () => {
    const field = mkField([polyRingC(C, 3, 2)])
    const start = ringPointAt(buildWaistRing(field, 97, C), 0)
    // (a) 有 jam 无 pinArcs（旁挂 sim）
    const simA = mkSim([[start.x, 97, start.z]])
    simA.field = field
    const tA = new Float32Array(simA.pinTarget)
    const ctrlA = buildSettle(simA, { front: [], back: [] }, {
      ...FAST, ...JAM2,
      probe: (_s, side) => side === 'front' ? PEN : CLEAR,
    })
    // (b) 有 pinArcs 无 jam
    const simB = mkSim([[start.x, 97, start.z]])
    simB.field = field
    simB.pinArcs = new Float64Array([0])
    const tB = new Float32Array(simB.pinTarget)
    const ctrlB = buildSettle(simB, { front: [], back: [] }, {
      ...FAST,
      probe: (_s, side) => side === 'front' ? PEN : CLEAR,
    })
    for (const [s, c] of [[simA, ctrlA], [simB, ctrlB]] as const) {
      for (let k = 0; k < 4; k++) c.step(s)
    }
    for (const [s, t0] of [[simA, tA], [simB, tB]] as const) {
      expect(s.pinTarget[0]).toBe(t0[0])
      expect(s.pinTarget[2]).toBe(t0[2])
      expect(s.pinTarget[1]).toBeCloseTo(96.5, 10)
    }
  })

  it('参考行下钳：腰口钉（前中下垂）钳在腰站环、带顶钉随自身行', () => {
    // 对照数字证伪裸逐钉行（前中 −0.67 嵌体）后的修正口径：参考行 =
    // max(自身行, 腰站行 + 下放量)。行布局 9 档 y=96..100：row0=jam 墙
    //（周长 66）、row1（96.5）圆心 (0,2)、row2（97）= 腰站圆心原点、
    // row7（99.5）圆心 (0,1)、其余原点，全部周长 C——等周长同心圆互为
    // 平移 → 手推锚 = 行心位移。圆心 x 恒 0 → s=0 钉恰前中 f=0（hF 全额）
    const slices: SliceRing[][] = [
      [polyRingC(66, 0, 0)],
      [polyRingC(C, 0, 2)],                       // row1 96.5
      [polyRingC(C, 0, 0)],                       // row2 97 腰站
      [polyRingC(C, 0, 0)], [polyRingC(C, 0, 0)],
      [polyRingC(C, 0, 0)], [polyRingC(C, 0, 0)],
      [polyRingC(C, 0, 1)],                       // row7 99.5
      [polyRingC(C, 0, 0)],                       // row8 100
    ]
    const field = new BodyField(new Float32Array(9 * 8), 9, 0.5, 8, slices, 96)
    const startA = ringPointAt(buildWaistRing(field, 96.5, C), 0)   // 腰口钉起点
    const startB = ringPointAt(buildWaistRing(field, 100, C), 0)    // 带顶钉起点
    const sim = mkSim([
      [startA.x, 96.5, startA.z],   // 钉A：腰口前中（baseY 比腰站低 0.5 = 前中下垂）
      [startB.x, 100, startB.z],    // 钉B：带顶（baseY 比腰站高 3）
    ])
    sim.field = field
    sim.pinArcs = new Float64Array([0, 0])
    let frontPen = 1.0
    const ctrl = buildSettle(sim, { front: [], back: [] }, {
      ...FAST, ...JAM2,
      probe: (_s, side) => side === 'front'
        ? { worst: frontPen, best: frontPen } : CLEAR,
    })
    for (let k = 0; k < 3; k++) ctrl.step(sim)   // hold
    ctrl.step(sim)   // hF=−0.5：候选行 96.5 周长 C 可容 → 下放
    frontPen = 0
    for (let k = 0; k < 12; k++) ctrl.step(sim)
    expect(ctrl.phase).toBe('done')
    // 钉A：Y 随下垂降到 96.0，XZ 钳在腰站+下放行（96.5）环上 = 不动
    //（裸逐钉行会落 row0 大环 = 证伪形态）
    expect(sim.pinTarget[1]).toBeCloseTo(96.0, 10)
    expect(sim.pinTarget[0]).toBeCloseTo(startA.x, 4)
    expect(sim.pinTarget[2]).toBeCloseTo(startA.z, 4)
    // 钉B：带顶高于腰站行 → 随自身行 99.5 环（圆心 (0,1) → z 位移 +1）
    expect(sim.pinTarget[4]).toBeCloseTo(99.5, 10)
    expect(sim.pinTarget[3]).toBeCloseTo(startB.x, 4)
    expect(sim.pinTarget[5]).toBeCloseTo(startB.z + 1, 4)
  })
})

// ---- 指定穿位（2026-09-24；当日二次修正 = 摆位层整组下移）：钉初始即
// 终位（摆位层把整裤 pos 连同钉目标源整体下移所选 cm、钉环建所选行），
// lowering 不探不降不等 confirm 直通 settle——切档秒出；掉裆/jam 退场 ----
describe('指定穿位（pinned）', () => {
  it('迹线 hold → settle 直通：探针不咨询、钉目标全程不动、hF/hB 恒 0', () => {
    const sim = mkSim(PINS)
    const y0 = new Float32Array(sim.pinTarget)
    const ctrl = buildSettle(sim, { front: [], back: [] }, {
      ...FAST, pinned: true,
      // 探针被咨询即炸——证明 lowering 旁路不碰探针（下放逻辑全退场）
      probe: () => { throw new Error('pinned 不咨询探针') },
    })
    ctrl.step(sim); ctrl.step(sim)
    expect(ctrl.phase).toBe('hold')
    ctrl.step(sim)                     // frames=3 ≥ holdFrames → lowering
    expect(ctrl.phase).toBe('lowering')
    ctrl.step(sim)                     // pinned 旁路：直通 settle（无 confirm 等待）
    expect(ctrl.phase).toBe('settle')
    expect(ctrl.hF).toBe(0); expect(ctrl.hB).toBe(0)
    expect([...sim.pinTarget]).toEqual([...y0])   // applyDrop 从未执行
    sim.settled = true
    ctrl.step(sim)                     // settled 已真 → done（无 wake 重测）
    expect(ctrl.phase).toBe('done')
  })

  it('报表语义：drop 恒 0、jam 恒 false、裆接触终态照实读', () => {
    const sim = mkSim(PINS)
    const ctrl = buildSettle(sim, { front: [], back: [] }, {
      ...FAST, pinned: true,
      probe: (_s, side) => side === 'front'
        ? { worst: 0.1, best: -0.1 } : { worst: -1.2, best: -1.2 },
    })
    for (let k = 0; k < 6; k++) ctrl.step(sim)   // hold 3 + 旁路转 settle + settle
    sim.settled = true
    ctrl.step(sim)
    expect(ctrl.phase).toBe('done')
    const rep = ctrl.report(sim)
    // drop = −hF：hF=0 时取负得 −0，toBe(0) 会败——量值断言用近似
    expect(rep.dropF).toBeCloseTo(0, 10); expect(rep.dropB).toBeCloseTo(0, 10)
    expect(rep.jamF).toBe(false); expect(rep.jamB).toBe(false)
    expect(rep.contactF.kind).toBe('touch')      // 前 0.1 ≤ deadZone 贴合
    expect(rep.contactB.kind).toBe('gap')        // 后 1.2 净空
    expect(rep.tooSmall).toBe(false)
  })

  it('hold 提前静止 + pinned：settled 判据即收，帧数下限 3（秒出口径）', () => {
    const sim = mkSim(PINS)
    const ctrl = buildSettle(sim, { front: [], back: [] }, { ...FAST, pinned: true })
    sim.settledFrames = DRAPE_PRIOR.settleFrames   // 布已静（全局真值判据）
    sim.settled = true
    ctrl.step(sim)   // hold 提前转 lowering（settledFrames 先达，holdFrames 退居上限）
    expect(ctrl.phase).toBe('lowering')
    ctrl.step(sim)   // pinned 直通 settle
    expect(ctrl.phase).toBe('settle')
    ctrl.step(sim)   // settled 已真 → done：共 3 帧
    expect(ctrl.phase).toBe('done')
    expect(ctrl.report(sim).frames).toBe(3)
  })
})
