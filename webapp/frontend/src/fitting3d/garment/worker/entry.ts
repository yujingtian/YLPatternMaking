// sim worker 入口：收 init -> 建撑型芯/mesh/场/BVH/整裤（band snap 芯面）
// -> createSim（含 preRelax）-> 自驱 60Hz stepSim，每帧 pos 副本转移回传；
// settled/frozen 停走。worker 无 rAF，用 setTimeout(16)（后台 tab 不被节流，
// 回来即最新帧）。热启动判定：边名签名不变 + 非强制冷启。
// 悬挂展示（hang，2026-09-14 唯一模式）：**解算空间 = 纸样系**
// （y=纸样高、hem≈0 落地，warp=identity），碰撞体 = 纸样围度撑型芯
// （core.ts，girth_finished 逐站取值、芯半径 = g/2π − skin → 布面恰落
// 纸样围度，圆筒按构造成立、想叠也叠不动）。人台完全出圈：init 不带
// 人台几何，视图层把整裤 Group 平移到人台旁侧做纯展示参照。
// 帧数封顶兜底（HANG_PRIOR.maxFrames）：超限强制取当前帧出 settled，
// 防 basin 彩票卡死显示。
import { buildClothMesh } from '../mesh'
import { buildCore } from '../core'
import { buildBodyField } from '../placement'
import { buildGarment } from '../seams'
import type { Garment, GarmentMeshes } from '../seams'
import { buildCollider } from './collide'
import type { Collider } from './collide'
import { HANG_PRIOR, SOLVER_PRIOR } from '../priors'
import type { FromWorker, ToWorker } from './protocol'
import { createSim, seamStats, stepSim, type SimState } from './solver'

const post = (msg: FromWorker, transfer?: Transferable[]): void => {
  ;(self as unknown as {
    postMessage(m: FromWorker, t?: Transferable[]): void
  }).postMessage(msg, transfer ?? [])
}

let sim: SimState | null = null
let collider: Collider | null = null
let timer: ReturnType<typeof setTimeout> | undefined

const runSig = (g: Garment): string =>
  g.parts.map((p) => p.mesh.runs.map((r) => r.name).join('+')).join('|')

function startLoop(maxFrames: number): void {
  if (timer !== undefined) clearTimeout(timer)
  const tick = (): void => {
    if (!sim) return
    const st = stepSim(sim)
    const out = sim.pos.slice()
    // 封顶：running 且达帧数上限 -> 强制 settled 收口（悬挂兜底）
    const capped = st === 'running' && sim.stepCount >= maxFrames
    const { avg, p95 } = (sim.stepCount % 10 === 0 || st !== 'running' || capped)
      ? seamStats(sim) : { avg: -1, p95: -1 }
    post({ type: 'frame', pos: out, status: capped ? 'settled' : st,
      step: sim.stepCount, capped, seamErrAvg: avg, seamErrP95: p95 },
      [out.buffer])
    if (st === 'running' && !capped) timer = setTimeout(tick, 16)
  }
  timer = setTimeout(tick, 0)
}

self.addEventListener('message', (ev: MessageEvent<ToWorker>) => {
  const msg = ev.data
  if (!msg || msg.type !== 'init') return
  if (timer !== undefined) { clearTimeout(timer); timer = undefined }
  try {
    const { payload, cold, hang } = msg
    const yokePiece = payload.pieces.find((p) => p.key === 'back_yoke')
    const pocketPiece = payload.pieces.find((p) => p.key === 'front_facing')
    const meshes: GarmentMeshes = {
      front: buildClothMesh(payload.pieces.find((p) => p.key === 'front_piece')!),
      back: buildClothMesh(payload.pieces.find((p) => p.key === 'back_piece')!),
      ...(yokePiece ? { yoke: buildClothMesh(yokePiece) } : {}),
      ...(pocketPiece ? { pocket: buildClothMesh(pocketPiece) } : {}),
    }
    // 撑型芯：纸样系碰撞体（腰臀单筒 + 双腿管），场/BVH/摆位全由它驱动
    const core = buildCore(payload)
    const field = buildBodyField(core.positions, core.indices)
    if (collider) collider.dispose()
    collider = buildCollider(core.positions, core.indices, field)
    const identity = (y: number): number => y
    const garment = buildGarment(meshes, payload, identity, field, (pos, i) =>
      collider!.snapOne(pos, i, SOLVER_PRIOR.collisionSkin))
    const prev = sim
    const warmOk = !cold && prev !== null
      && runSig(prev.garment) === runSig(garment)
    sim = createSim(garment, identity, field, collider,
      warmOk ? prev : undefined)
    post({ type: 'ready', total: garment.total })
    startLoop(hang ? HANG_PRIOR.maxFrames : Infinity)
  } catch (e) {
    post({ type: 'error',
      message: e instanceof Error ? e.message : String(e) })
  }
})
