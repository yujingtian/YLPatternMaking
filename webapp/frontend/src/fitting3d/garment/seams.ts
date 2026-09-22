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
import { bandBottomChain, bandEndPairs, bandTargets, ringWalk } from './band'

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
// = tip 本体（角点共享规则：共享角点 = 下一条边首采样；2026-09-18
// export——穿台 settle 裆探针同款兜底）
export function tipAfterInseam(mesh: Garment['parts'][number]['mesh']): number | null {
  const run = mesh.runs.find((r) => r.name === 'inseam')
  if (!run || run.indices.length === 0) return null
  const last = run.indices[run.indices.length - 1]
  return (last + 1) % mesh.loop.length
}

export function buildSeamSet(garment: Garment): SeamSet {
  const f = hostParts(garment, 'front')
  const b = hostParts(garment, 'back')
  // seam 模式育克宿主（L/R 共享翻转网格；2026-09-22 有省闭省净样款）：
  // yokeSeam 字段在 = panel.ts 判定育克升格 sim 参与片；取不到宿主静默
  // 降级（族整组跳过，不炸主流程）
  let yh: HostParts | null = null
  if (garment.yokeSeam) {
    try { yh = hostParts(garment, 'back_yoke') } catch { yh = null }
  }
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
  // seam 模式 yokeCb 镜像族：cb'（P0→O）L/R 同号配对（六期中缝机制）
  // ——后中缝从 P0 贯通到腰口 O（union 模式靠 cb 同名边聚合成整条后浪，
  // seam 模式育克分片、镜像族补上腰口段）
  if (yh) {
    push('yokeCb', (out) => {
      const run = yh!.l.mesh.runs.find((r) => r.name === 'cb')
      if (!run) return
      for (const i of run.indices) {
        out.push(yh!.l.offset + i, yh!.r.offset + i)
      }
    })
  }

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
        // seam 模式 side 族：目标链改跨 part 拼链 [yokeSide'(X→PN'，
        // 弧 0 在 X = 腰角), backSide(PN→脚口)]——纯后片 side 不再含育克
        // 段，侧缝全长跨两片；t = s·(Ly+Lb) 与驱动链腰角端锚定一致
        if (name === 'side' && yh) {
          const ySide = mergeRuns(
            yh.l.mesh.runs.filter((r) => r.name === 'side'), yh.l.mesh.xy)
          if (!ySide) return
          const offY = side === 'L' ? yh.l.offset : yh.r.offset
          const span = ySide.length + chainB.length
          for (let k = 0; k < chainF.indices.length; k++) {
            const t = (chainF.arc[k] / (chainF.length || 1)) * span
            out.push(offF + chainF.indices[k],
              t <= ySide.length
                ? offY + runIndexAt(ySide, t / (ySide.length || 1))
                : offB + runIndexAt(chainB, (t - ySide.length) / (chainB.length || 1)))
          }
          return
        }
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

  // ---- seam 模式育克两族（2026-09-22 有省闭省净样款）：yokeWaist 分段
  // 缝合 + P0/PN 角点焊对。几何账（fixture 实测，size_draft 口径真有省
  // 款）：back top = 整版机头下口线直线（含省口段不扣，L_back 22.07）；
  // yoke bottom = 闭省净样三段（瓣1 line [0, 7.81] 与直线逐点重合
  // perp=0 + 倒圆 bezier 跨省口 + 瓣2 line，L_yoke 19.683）——sMouth =
  // L_back − L_yoke = 2.387 = 省口段布量（真实缝前状态：后片省未收）。
  // 闭式映射（back 弧 a → yoke 弧 b）：a < sCin 前段 1:1（两链同线）、
  // 省口段（sCin ≤ a < sCin+sMouth）全体收敛 C_in = 收省口的物理实现、
  // 右段 b = a − sMouth 1:1（端点对账 a=L_back → b=L_yoke）。目标分数
  // 换算：bottom' run 从 PN' 起走 → sRun = (L_yoke − b)/L_yoke。弧长
  // 口径沿用 arclen 族先例（驱动链 chord-arc 分数近似，微差动力学吸收）----
  if (yh && garment.yokeSeam) {
    const sCin = garment.yokeSeam.sCin
    for (const side of ['L', 'R'] as const) {
      const bp = side === 'L' ? b.l : b.r
      const yp = side === 'L' ? yh.l : yh.r
      const bTop = mergeRuns(
        bp.mesh.runs.filter((r) => r.name === 'top'), bp.mesh.xy)
      const yBottom = mergeRuns(
        yp.mesh.runs.filter((r) => r.name === 'bottom'), yp.mesh.xy)
      const yCb = yp.mesh.runs.find((r) => r.name === 'cb')
      const bSide = mergeRuns(
        bp.mesh.runs.filter((r) => r.name === 'side'), bp.mesh.xy)
      if (!bTop || !yBottom || !yCb || !bSide) continue
      const sMouth = bTop.length - yBottom.length
      push(`yokeWaist${side}`, (out) => {
        for (let k = 0; k < bTop.indices.length; k++) {
          const a = bTop.arc[k]
          const bv = a < sCin ? a : (a < sCin + sMouth ? sCin : a - sMouth)
          const sRun = (yBottom.length - bv) / (yBottom.length || 1)
          out.push(bp.offset + bTop.indices[k],
            yp.offset + runIndexAt(yBottom, sRun))
        }
      })
      // P0/PN 角点焊对（×2/侧）：弧长族对两端只有最近采样级覆盖，角点
      // 须显式焊（tip 补焊同款动机）——P0 = back.top[0] ↔ yoke.cb'[0]、
      // PN = back side 合链首 ↔ yoke.bottom'[0]
      push(`yokeWeld${side}`, (out) => {
        out.push(bp.offset + bTop.indices[0], yp.offset + yCb.indices[0])
        out.push(bp.offset + bSide.indices[0], yp.offset + yBottom.indices[0])
      })
    }
  }

  // 腰头两族（九期腰头立体化，用户口径「腰头两边是前中线、腰头中点是
  // 后中线」）：bandWaist = 带底边 ↔ 腰环（bandTargets 与 assemble 摆位
  // 同源——环顶点映射一致、初始间隙 0；吃势 = 带底长与纸样腰弧差沿环
  // 均匀吸收，直款对账严格相等〔腰长不变量〕、弯款差 = 省道开口）；
  // bandEnds = 两端 weld 前中会合（扣好的裤子闭合环）
  const bandPart = garment.parts.find((p) => p.key === 'waistband')
  if (bandPart) {
    try {
      const walk = ringWalk(garment.parts)
      const chain = bandBottomChain(bandPart.mesh)
      const targets = bandTargets(bandPart.mesh, walk)
      if (chain && targets) {
        // 接缝孪生角补配对：四段腰弧在前中/后中接缝处各有**两个重合角**
        //（fL|fR 腰角、bL|bR 腰角——镜像片的独立顶点）——带端/带中点只
        // 配到一个，另一个悬空 ~1cm（后中实测）成小洞。walk 弧距接缝
        // 弧（0 / P/2 / P）<0.6 的配对追加孪生角
        // 接缝弧取 0 / P/2 / P；弧距按环形回绕算（0 与 P 是同一接缝——
        // 前中角分属 fL 首点 arc≈0 与 fR 末点 arc≈P）
        const junctionArcs = [0, walk.total / 2]
        const arcDist = (a: number, b: number) => {
          const d = Math.abs(a - b) % walk.total
          return Math.min(d, walk.total - d)
        }
        const twinOf = (k: number): number | null => {
          const a = walk.verts[k].arc
          for (const j of junctionArcs) {
            if (arcDist(a, j) > 0.6) continue
            // 孪生 = 距同一接缝弧 <0.6 的另一个顶点（位置重合的镜像角）
            for (let m = 0; m < walk.verts.length; m++) {
              if (m === k) continue
              if (arcDist(walk.verts[m].arc, j) > 0.6) continue
              return m
            }
          }
          return null
        }
        push('bandWaist', (out) => {
          for (const i of chain.indices) {
            const r = walk.verts[targets[i].ringK]
            out.push(bandPart.offset + i,
              garment.parts[r.part].offset + r.idx)
            const t = twinOf(targets[i].ringK)
            if (t !== null) {
              out.push(bandPart.offset + i,
                garment.parts[walk.verts[t].part].offset + walk.verts[t].idx)
            }
          }
        })
      }
      const ends = bandEndPairs(bandPart.mesh)
      if (ends) {
        push('bandEnds', (out) => {
          for (const [a, b] of ends) {
            out.push(bandPart.offset + a, bandPart.offset + b)
          }
        })
      }
    } catch (e) {
      console.warn('[seams] 腰头缝合族跳过（坏链）:', e)
    }
  }

  return { pairs: new Uint32Array(pairs), groups }
}
