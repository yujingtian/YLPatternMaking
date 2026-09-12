// 人台构建生命周期 hook：payload body 站点 + 体型围度 -> 真人网格人台。
// 异步 bodymesh fetch + morph/标定（~百 ms 级），stale 轮次丢弃防旧结果
// 抢写；失败 console.error 且回 idle（不炸 React 树）。
// 2026-09-12 裁撤试穿：原 useFittingSolver（布料网格/缝合摆位/PBD 解算
// rAF 循环）随试穿链退役，本 hook 只建人台供显示。
import { useEffect, useMemo, useRef, useState } from 'react'
import type { FittingResult } from '../types'
import type { BodyGirths } from './bodyProfile'
import { buildMeshMannequin, type MeshMannequin } from './bodymesh/build'
import { loadBodyMesh } from './bodymesh/load'

export type MannequinStatus = 'idle' | 'building' | 'ready'

export interface MannequinHandles {
  status: MannequinStatus
  buildVersion: number            // man 对象更换计数（视图重建几何）
  man: MeshMannequin | null
}

export function useMannequin(
  body: FittingResult['body'] | null, girths: BodyGirths | null,
): MannequinHandles {
  const [status, setStatus] = useState<MannequinStatus>('idle')
  const [buildVersion, setBuildVersion] = useState(0)
  const manRef = useRef<MeshMannequin | null>(null)

  useEffect(() => {
    if (!body || !girths) {
      manRef.current = null
      setStatus('idle')
      return
    }
    setStatus('building')
    // 让出首帧给 Spin 再做重活；bodymesh fetch 异步：await 后先查
    // stale（deps 已换轮次则丢弃，防旧结果抢写新轮的 refs/状态）
    let stale = false
    const id = window.setTimeout(() => {
      void (async () => {
        try {
          const asset = await loadBodyMesh()
          if (stale) return
          const man = buildMeshMannequin(asset, body, girths)
          if (stale) return
          manRef.current = man
          setBuildVersion((v) => v + 1)
          setStatus('ready')
        } catch (e) {
          console.error('[fitting3d] 人台构建失败', e)
          if (!stale) setStatus('idle')
        }
      })()
    }, 0)
    return () => {
      stale = true
      window.clearTimeout(id)
    }
  }, [body, girths])

  return useMemo(() => ({
    status, buildVersion, man: manRef.current,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [status, buildVersion])
}
