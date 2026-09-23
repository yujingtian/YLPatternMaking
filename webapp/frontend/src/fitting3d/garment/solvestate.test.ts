// 穿台解算序列化金标（2026-09-23 Worker 化）：toSolveState →
// structuredClone/transfer → fromSolveState 的三层把门：
// · 可克隆 + transfer 零拷贝：init 过 structuredClone（postMessage 同
//   语义）；transferBuffers 去重 L/R 共享 mesh（同一 buffer 两次进 transfer
//   清单 = DataCloneError——Set 去重把门）；transfer 后原 buffer detach
//   （零拷贝实锤，主线程此后不得再碰 sim）
// · roundtrip 完整性：field 六元组重建 BodyField（缓存惰性再生）、网格
//   数组/pinArcs（Object.is 含 NaN 弧位空洞）/seamGroups/标量逐项同
// · **双宿主锁步位级相等**（确定性红线在序列化层把门）：内存 sim（主
//   线程金标宿主）vs「投影→克隆→再水化」sim（worker 宿主路径）各自
//   createDressRun heatOn=true 全程跑——逐步 pos 逐位相等、heat 节拍同帧
//   同值（HEAT_PRIOR.every）、终态同帧、DressReport 逐字段相等。
//   序列化若引入浮点往返损失（如 JSON string 化）此测即红——worker 侧
//   解算 = 主线程解算是金标口径，不是「差不多」
// 夹具 = dress.test 同源真 base.bin + fixture_fitting.json 基础款全管线
// （build 段逐字镜像 runDress：锚定/场/腿轴/腰圈钉环/摆位，止于 buildDrape
// ——解算交 dressDriver 由本文件两宿主分别驱动）
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../types'
import type { BodyMeshAsset } from '../bodymesh/bin'
import { parseBaseBin } from '../bodymesh/bin'
import { stationFactor } from '../bodymesh/height'
import { buildFullPair } from './assemble'
import {
  buildBodyField, buildLegAxisFromRings, buildWaistRing, shiftPositionsY,
} from './placement'
import { buildDrape, type DrapeSim } from './drape'
import { buildBackPanel, buildFrontPanel } from './panel'
import { bandBottomChain, buildWaistbandMesh } from './band'
import { buildCrotchProbeIdx, type DressReport } from './settle'
import { FIELD_PRIOR } from './priors'
import {
  createDressRun,
} from './dressDriver'
import {
  fromSolveState, toSolveState, transferBuffers, type CrotchProbeIdx,
} from './solvestate'

const HERE = import.meta.dirname   // src/fitting3d/garment
const PUB = `${HERE}/../../../public/bodymesh`

// 真产物人台（dress.test 同源）
function loadBodyFromDisk(): BodyMeshAsset {
  const meta = JSON.parse(readFileSync(`${PUB}/targets.json`, 'utf8'))
  const { positions, indices, fields } = parseBaseBin(
    readFileSync(`${PUB}/base.bin`).buffer.slice(0))
  const lmRaw = (meta.landmarkHeights ?? {}) as Record<string, number>
  const landmarks: BodyMeshAsset['landmarks'] = {}
  for (const k of ['sole', 'crotch', 'waist', 'hip', 'knee', 'calf', 'ankle'] as const) {
    if (typeof lmRaw[k] === 'number') landmarks[k] = lmRaw[k]
  }
  return {
    positions, indices,
    targets: fields.map((f, k) => ({ ...f, name: meta.targets[k].name })),
    stations: {}, landmarks,
    height: meta.cut.planeY as number,
    heightInfo: {
      baseCm: meta.height.baseCm as number,
      plusCm: meta.height.plusCmAtW1 as number,
      minusCm: meta.height.minusCmAtW1 as number,
    },
  } as BodyMeshAsset
}

interface Built {
  sim: DrapeSim
  probeIdx: CrotchProbeIdx
  jam: { ringTotal: number; rowY: number }
}

// 穿台 build 段（runDress 逐字镜像，止于 buildDrape——不解算）
function buildDressSim(): Built {
  const a = loadBodyFromDisk()
  const data = JSON.parse(
    readFileSync(`${HERE}/fixture_fitting.json`, 'utf8')) as FittingResult
  const lmWaist = a.landmarks.waist!
  const lmCrotch = a.landmarks.crotch!
  const lmAnkle = a.landmarks.ankle!
  const sf = stationFactor(a.heightInfo, 0)
  const waistSt = data.body.stations.find((s) => s.key === 'waist')!
  const anchorLift = lmWaist * sf - waistSt.y
  const fieldYMin = Math.floor(-anchorLift / FIELD_PRIOR.rowStep) * FIELD_PRIOR.rowStep
  const fieldM = buildBodyField(
    shiftPositionsY(a.positions, -anchorLift), a.indices, fieldYMin)
  const legAxisM = buildLegAxisFromRings(
    fieldM, lmCrotch * sf - anchorLift, lmAnkle * sf - anchorLift)
  const panel = buildFrontPanel(data)
  const backPanel = buildBackPanel(data)
  const bandMesh = buildWaistbandMesh(data)
  const waistLen0 = (bandMesh && bandBottomChain(bandMesh)?.runLength)
    ?? waistSt.girth_finished
  if (waistLen0 == null) {
    throw new Error('缺成衣腰长（腰头带底净长/腰站 girth_finished 均缺）——穿台无法定腰圈钉环')
  }
  const waistRing = buildWaistRing(fieldM, waistSt.y, waistLen0)
  const pair = buildFullPair(panel.host, backPanel.host, fieldM, {
    front: legAxisM.forkY, back: legAxisM.forkY,
  }, legAxisM, bandMesh, anchorLift, waistRing)
  const sim = buildDrape(pair, fieldM, anchorLift)
  return {
    sim,
    probeIdx: buildCrotchProbeIdx(pair),
    jam: { ringTotal: waistRing.total, rowY: waistRing.y },
  }
}

// 首个不等位（-1 = 逐位相等；位级 ===，不给容差——确定性红线）
const firstDiff = (x: Float32Array, y: Float32Array): number => {
  const n = Math.min(x.length, y.length)
  for (let i = 0; i < n; i++) if (x[i] !== y[i]) return i
  return x.length === y.length ? -1 : x.length
}

describe('solvestate：穿台解算序列化（Worker 化）', () => {
  it('toSolveState 可克隆 + transferBuffers 去重零拷贝（共享 mesh 不炸）',
    { timeout: 30000 }, () => {
      const { sim, probeIdx, jam } = buildDressSim()
      const init = toSolveState(sim, probeIdx, jam, false)
      // 线缆契约：init 消息必带 type:'init'——worker 端按 msg.type 分发，
      // 漏了会被送达后静默丢弃（2026-09-23「炸开的裤子不会变化」根因；
      // DOM Worker.postMessage 是 any 口径，编译期拦不住，金标自守）
      expect(init.type).toBe('init')
      // L/R part 共享同一 ClothMesh → 投影保持同引用（transfer 去重前提，
      // 现行 buildFullPair 口径）
      expect(init.state.parts.length).toBeGreaterThanOrEqual(2)
      expect(init.state.parts[0].mesh.dist === init.state.parts[1].mesh.dist)
        .toBe(true)
      // 纯克隆（无 transfer，postMessage 回退路径）可过
      const plain = structuredClone(init)
      expect(plain.state.pos.length).toBe(sim.pos.length)
      // transfer：清单无重复（同 buffer 两次进清单 = DataCloneError）+
      // 零拷贝实锤（原 buffer detach、克隆体等长接管）
      const bufs = transferBuffers(init)
      expect(new Set(bufs).size).toBe(bufs.length)
      const moved = structuredClone(init, { transfer: bufs })
      expect(sim.pos.byteLength).toBe(0)
      expect(moved.state.pos.byteLength).toBe(plain.state.pos.byteLength)
    })

  it('roundtrip 再水化：field 重建 / 网格与钉弧位逐位 / seamGroups / 标量',
    { timeout: 30000 }, () => {
      const { sim, probeIdx, jam } = buildDressSim()
      const init = structuredClone(toSolveState(sim, probeIdx, jam, true))
      const s2 = fromSolveState(init.state)
      // field 六元组重建（BodyField 新实例、环数同；缓存惰性再生不改结果）
      expect(s2.field).not.toBeNull()
      expect(sim.field).not.toBeNull()
      expect(s2.field!.slices.length).toBe(sim.field!.slices.length)
      expect(s2.field!.yMin).toBe(sim.field!.yMin)
      // 网格结构同形 + 数组逐位（bendKArr 盖章随行）
      expect(s2.parts.length).toBe(sim.parts.length)
      for (let k = 0; k < sim.parts.length; k++) {
        expect(s2.parts[k].offset).toBe(sim.parts[k].offset)
        expect(s2.parts[k].mesh.dist.length).toBe(sim.parts[k].mesh.dist.length)
        expect(firstDiff(s2.parts[k].mesh.dist, sim.parts[k].mesh.dist)).toBe(-1)
        expect(firstDiff(s2.parts[k].mesh.bend, sim.parts[k].mesh.bend)).toBe(-1)
        expect((s2.parts[k].mesh.bendKArr !== undefined))
          .toBe((sim.parts[k].mesh.bendKArr !== undefined))
        if (s2.parts[k].mesh.bendKArr && sim.parts[k].mesh.bendKArr) {
          expect(firstDiff(s2.parts[k].mesh.bendKArr!, sim.parts[k].mesh.bendKArr!))
            .toBe(-1)
        }
      }
      // 钉弧位：Object.is 含 NaN 空洞（P2 弧位缺项 = 冻结旧口径，须原样保）
      const pa1 = sim.pinArcs!, pa2 = s2.pinArcs!
      expect(pa2.length).toBe(pa1.length)
      for (let k = 0; k < pa1.length; k++) {
        expect(Object.is(pa2[k], pa1[k]), `pinArcs[${k}]`).toBe(true)
      }
      expect(s2.seamGroups).toEqual(sim.seamGroups)
      expect(firstDiff(s2.pinTarget, sim.pinTarget)).toBe(-1)
      expect(s2.yLift).toBe(sim.yLift)
      expect(s2.collideAboveY).toBe(sim.collideAboveY)
      expect(s2.maxFrames).toBe(sim.maxFrames)
    })

  it('双宿主锁步全解算位级相等（确定性红线：worker 再水化 = 主线程）',
    { timeout: 120000 }, () => {
      const a = buildDressSim()
      // worker 宿主路径：投影 → 克隆（无 transfer，node 侧模拟 postMessage
      // 拷贝档；transfer 档位级同理由前测 detach 语义把门）→ 再水化
      const init = structuredClone(toSolveState(a.sim, a.probeIdx, a.jam, true))
      const b = { sim: fromSolveState(init.state) }
      let posA!: Float32Array
      let posB!: Float32Array
      let heatA: Float32Array | null = null
      let heatB: Float32Array | null = null
      let finA = -1
      let finB = -1
      let repA: DressReport | null = null
      let repB: DressReport | null = null
      const mkSink = (
        setPos: (p: Float32Array) => void, setHeat: (h: Float32Array | null) => void,
        setFin: (f: number) => void, setRep: (r: DressReport) => void,
      ) => ({
        onFrame: (f: number, p: Float32Array, h: Float32Array | null): void => {
          setFin(f); setPos(p); setHeat(h)
        },
        onDone: (r: DressReport, p: Float32Array, h: Float32Array | null): void => {
          setRep(r); setPos(p); setHeat(h)
        },
        onError: (e: unknown): void => { throw e },
      })
      const runA = createDressRun(a.sim, a.probeIdx, a.jam, true,
        mkSink((p) => { posA = p }, (h) => { heatA = h },
          (f) => { finA = f }, (r) => { repA = r }))
      const runB = createDressRun(b.sim, init.probeIdx, init.jam, true,
        mkSink((p) => { posB = p }, (h) => { heatB = h },
          (f) => { finB = f }, (r) => { repB = r }))
      let steps = 0
      let heatFrames = 0
      while (runA.stepOnce()) {
        expect(runB.stepOnce(), `B 终态先于 A（步 ${steps}）`).toBe(true)
        expect(firstDiff(posA, posB), `pos 位级不等 @步 ${steps}`).toBe(-1)
        // heat 节拍同帧：非同 null/非 null 即序列化改变了节拍
        expect(heatA === null, `heat 节拍错位 @步 ${steps}`).toBe(heatB === null)
        if (heatA !== null && heatB !== null) {
          expect(firstDiff(heatA, heatB), `heat 位级不等 @步 ${steps}`).toBe(-1)
          heatFrames++
        }
        steps++
      }
      expect(runB.stepOnce(), 'A 停后 B 须同步终态').toBe(false)
      expect(finB).toBe(finA)
      expect(repA).not.toBeNull()
      expect(repB).toEqual(repA)   // DressReport 逐字段（NaN 由 toEqual 同值判）
      // 规模把门：真跑全程（非秒停）、heat 节拍真发生（heatOn 透传生效）
      expect(steps).toBeGreaterThan(100)
      expect(heatFrames).toBeGreaterThan(10)
      expect(heatA).not.toBeNull()   // 终态帧恒带末帧 heat（heatOn 时）
    })
})
