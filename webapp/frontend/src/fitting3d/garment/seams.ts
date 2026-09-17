// 整裤缝合拓扑（2026-09-17 八期）：buildFullPair 四 part Garment
// （fL/fR/bL/bR）的全族缝合对构建。配对数学三源：
//   · 镜像族（rise/cb）：同宿主 L/R 两 part 共享同一网格，同号顶点
//     (offset_L+i, offset_R+i) 天然镜像对——六期中缝机制原样泛化；
//     fly 连裁款 rise 链缺失整族跳过（前中敞口属连裁门襟固有形态）
//   · 弧长族（side/inseam）：跨宿主两链采样不同步（后宿主 side 还要
//     mergeRuns 拼育克段），按弧长分数配对（runIndexAt 线性插值取最近
//     顶点）；吃势（前后链弧长差，fixture 实测 side 99.1 vs 99.6 /
//     inseam 78.2 vs 78.0）沿链均匀吸收——七期已验证 avg 0.045/p95
//     0.000。side 锚定腰口端（首对 = 两链腰角，摆位 θ=±90° 共点）、
//     inseam 锚定脚口端（两链方向均脚口端→裆尖，arc[0]=0 即 hem 内角）
//   · tip 补焊（×2）：四裆尖跨宿主焊拢。角点共享规则（边界重采样每
//     边不含终点）下 tip 本体 = rise/cb 链首采样，inseam 末采样是 tip
//     前一步——不补焊则前/后裆尖各悬 ~1cm。rise 末对 + tipL + cb 首对
//     + tipR 构成零 rest 四边形 FL–FR–BR–BL，解算自动坍缩为一点 =
//     裆交叉点（八期用户口径「两内缝+前中缝+后中缝汇集到裆交叉点」）
// 全族 rest=0 进同一扁平 pairs 数组——drape 求解循环对全族一视同仁
// （六期 seamIdx 机制的泛化），本文件只管配对构建。纯拓扑 + 弧长，
// 不依赖场/解算 → 独立金标（seams.test.ts）。
import type { Garment } from './assemble'
import type { EdgeRun } from './mesh'
import { mergeRuns, runIndexAt } from './mesh'

export interface SeamGroup {
  name: string          // rise / cb / sideL / sideR / inseamL / inseamR / tipL / tipR
  pairOffset: number    // pairs 内起始对号（×2 = 索引偏移）
  pairCount: number
}

export interface SeamSet {
  pairs: Uint32Array    // 2S 平铺全局粒子号（rest=0，drape 求解器直吃）
  groups: SeamGroup[]   // 分族切片（金标分族统计/诊断用；空族不入表）
}

interface HostParts {
  l: Garment['parts'][number]
  r: Garment['parts'][number]
}

// 宿主在 Garment 中的 L/R 两 part（key 相同、共享网格）
function hostParts(garment: Garment, key: string): HostParts {
  const ps = garment.parts.filter((p) => p.key === key)
  if (ps.length !== 2 || ps[0].mesh !== ps[1].mesh) {
    throw new Error(`整裤缝合需要 '${key}' 宿主恰 L/R 两 part 共享网格（实得 ${ps.length}）`)
  }
  return { l: ps[0], r: ps[1] }
}

// 无中缝链款（fly 连裁）的裆尖兜底：inseam 末采样在边界环中的下一点
// = tip 本体（角点共享规则：共享角点 = 下一条边首采样）
function tipAfterInseam(mesh: Garment['parts'][number]['mesh']): number | null {
  const run = mesh.runs.find((r) => r.name === 'inseam')
  if (!run || run.indices.length === 0) return null
  const last = run.indices[run.indices.length - 1]
  return (last + 1) % mesh.loop.length
}

export function buildSeamSet(garment: Garment): SeamSet {
  const f = hostParts(garment, 'front')
  const b = hostParts(garment, 'back')
  const pairs: number[] = []
  const groups: SeamGroup[] = []
  const push = (name: string, add: (out: number[]) => void): void => {
    const pairOffset = pairs.length / 2
    add(pairs)
    const pairCount = pairs.length / 2 - pairOffset
    if (pairCount > 0) groups.push({ name, pairOffset, pairCount })
  }

  // 镜像族：同宿主 L/R 同号顶点
  const mirror = (host: HostParts, runName: 'rise' | 'cb'): void => {
    push(runName, (out) => {
      const run = host.l.mesh.runs.find((r) => r.name === runName)
      if (!run) return                    // fly 连裁 rise 缺失：整族跳过
      for (const i of run.indices) {
        out.push(host.l.offset + i, host.r.offset + i)
      }
    })
  }
  mirror(f, 'rise')
  mirror(b, 'cb')

  // 弧长族：驱动链（front）逐顶点 -> 对侧链弧长分数取顶点；L/R 各一族
  const chainOf = (host: HostParts, name: string): EdgeRun | null =>
    name === 'side'
      ? mergeRuns(host.l.mesh.runs.filter((r) => r.name === 'side'),
        host.l.mesh.xy)
      : host.l.mesh.runs.find((r) => r.name === name) ?? null
  const arclen = (name: string): void => {
    const chainF = chainOf(f, name)
    const chainB = chainOf(b, name)
    for (const side of ['L', 'R'] as const) {
      push(`${name}${side}`, (out) => {
        if (!chainF || !chainB) return
        const offF = side === 'L' ? f.l.offset : f.r.offset
        const offB = side === 'L' ? b.l.offset : b.r.offset
        for (let k = 0; k < chainF.indices.length; k++) {
          const s = chainF.arc[k] / (chainF.length || 1)
          out.push(offF + chainF.indices[k], offB + runIndexAt(chainB, s))
        }
      })
    }
  }
  arclen('side')
  arclen('inseam')

  // tip 补焊：front tip = rise 链首采样（fly 兜底 inseam 环下一点）
  const fTip = f.l.mesh.runs.find((r) => r.name === 'rise')
    ? f.l.mesh.runs.find((r) => r.name === 'rise')!.indices[0]
    : tipAfterInseam(f.l.mesh)
  const bTip = b.l.mesh.runs.find((r) => r.name === 'cb')
    ? b.l.mesh.runs.find((r) => r.name === 'cb')!.indices[0]
    : tipAfterInseam(b.l.mesh)
  for (const side of ['L', 'R'] as const) {
    push(`tip${side}`, (out) => {
      if (fTip === null || bTip === null) return
      out.push((side === 'L' ? f.l.offset : f.r.offset) + fTip,
        (side === 'L' ? b.l.offset : b.r.offset) + bTip)
    })
  }

  return { pairs: new Uint32Array(pairs), groups }
}
