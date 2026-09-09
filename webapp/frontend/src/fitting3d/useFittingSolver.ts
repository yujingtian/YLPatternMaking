// 3D 试穿解算生命周期 hook：payload/体型 -> 人台+网格+整裤+PBD 初态，
// rAF 驱动 stepSim，settled/frozen 自动停走；tab 隐藏暂停解算。
// 热启动：仅体型变化（网格复用）或边名签名不变的参数变化 -> 旧解重心
// 插值继承（跳过大部分预松弛）；签名变化/首次/手动重启 -> 冷启动预松弛。
// 网格（纯 2D）只随 payload 重建；人台/摆位随体型即时重建。
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FittingResult } from '../types'
import type { BodyGirths } from './bodyProfile'
import { buildMannequin, type Mannequin } from './mannequin'
import { buildClothMesh, type ClothMesh } from './mesh'
import { buildGarment, type Garment } from './seams'
import { createSim, stepSim, type SimState } from './pbd/solver'

export type SolverStatus = 'idle' | 'building' | 'running' | 'settled' | 'frozen'

export interface SolverHandles {
  status: SolverStatus
  buildVersion: number            // sim/garment/man 对象更换计数（视图重建几何）
  man: Mannequin | null
  garment: Garment | null
  sim: SimState | null
  /** 注册每帧回调（解算步后调用；视图渲染/热力图更新挂这里） */
  onFrame: (cb: () => void) => () => void
  /** 强制冷启动重解算（「重新试穿」按钮） */
  restart: () => void
}

const runSig = (meshes: Record<'front' | 'back', ClothMesh>): string =>
  (['front', 'back'] as const)
    .map((k) => meshes[k].runs.map((r) => r.name).join('+')).join('|')

export function useFittingSolver(
  result: FittingResult | null, girths: BodyGirths | null,
): SolverHandles {
  const [status, setStatus] = useState<SolverStatus>('idle')
  const [buildVersion, setBuildVersion] = useState(0)
  const [restartTick, setRestartTick] = useState(0)
  const simRef = useRef<SimState | null>(null)
  const garmentRef = useRef<Garment | null>(null)
  const manRef = useRef<Mannequin | null>(null)
  const meshesRef = useRef<{
    meshes: Record<'front' | 'back', ClothMesh>
    sig: string
    sigWarm: string        // 上一次成功热启动时的签名（'' = 无旧解）
    from: FittingResult
  } | null>(null)
  const forceCold = useRef(false)
  const listeners = useRef(new Set<() => void>())

  useEffect(() => {
    if (!result || !girths) {
      simRef.current = null
      garmentRef.current = null
      manRef.current = null
      meshesRef.current = null
      setStatus('idle')
      return
    }
    setStatus('building')
    // 让出首帧给 Spin 再做重活（网格/预松弛 ~百 ms 级）
    const id = window.setTimeout(() => {
      try {
        const front = result.pieces.find((p) => p.key === 'front_piece')
        const back = result.pieces.find((p) => p.key === 'back_piece')
        if (!front || !back) throw new Error('fitting payload 缺前后片')
        if (!meshesRef.current || meshesRef.current.from !== result) {
          meshesRef.current = {
            meshes: {
              front: buildClothMesh(front),
              back: buildClothMesh(back),
            },
            sig: '', sigWarm: '', from: result,
          }
          meshesRef.current.sig = runSig(meshesRef.current.meshes)
        }
        const { meshes, sig } = meshesRef.current
        const man = buildMannequin(result.body, girths)
        const garment = buildGarment(meshes, man)
        const warmOk = !forceCold.current && simRef.current !== null
          && meshesRef.current.sigWarm === sig
        forceCold.current = false
        const sim = createSim(garment, man,
          warmOk ? simRef.current! : undefined)
        simRef.current = sim
        garmentRef.current = garment
        manRef.current = man
        meshesRef.current.sigWarm = sig
        setBuildVersion((v) => v + 1)
        setStatus('running')
      } catch (e) {
        console.error('[fitting3d] 构建失败', e)
        setStatus('idle')
      }
    }, 0)
    return () => window.clearTimeout(id)
  }, [result, girths, restartTick])

  useEffect(() => {
    if (status !== 'running') return
    let raf = 0
    let stopped = false
    const tick = () => {
      if (stopped) return
      const sim = simRef.current
      if (sim) {
        if (!document.hidden) {
          const st = stepSim(sim)
          if (st !== 'running') setStatus(st)
        }
        for (const cb of listeners.current) cb()
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => { stopped = true; cancelAnimationFrame(raf) }
  }, [status])

  const onFrame = useCallback((cb: () => void) => {
    listeners.current.add(cb)
    return () => { listeners.current.delete(cb) }
  }, [])

  const restart = useCallback(() => {
    forceCold.current = true         // 本轮禁热启动；后续参数变化恢复热启
    setRestartTick((t) => t + 1)
  }, [])

  return useMemo(() => ({
    status, buildVersion,
    man: manRef.current, garment: garmentRef.current, sim: simRef.current,
    onFrame, restart,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [status, buildVersion, onFrame, restart])
}
