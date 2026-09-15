// 初始摆位与缝合（二期复活版）：前后片 2D 网格（整版全局系）包裹到
// 人台 + 直腰头真实布片 + 物理缝合配对 + 腰头 pin。
// 摆位约定见 placement.ts；缝合一律按弧长参数配对（前后片并排摆放、
// 锚点无全局坐标重合，坑 #1）。
// 装配链（2026-09-14 用户业务口径：完整牛仔裤 = 腰头/育克/前片/后片）：
//   前腰头↔前片、后腰头↔育克上口、育克下口↔后片上口，侧缝上段随育克。
//   无 yoke 11 条 = side×2 + inseam×2 + rise 镜像 + cb 镜像 + 腰缝×4 + 腰头后中
//   有 yoke 16 条 = 侧缝链式拆分×4 + inseam×2 + rise + cb 镜像×2（后片+育克）
//     + 腰缝×4（后侧改缝育克上口）+ 育克下口↔后片上口×2 + 腰头后中
// 腰缝环序（θ 从后中起向左半圈推进）：back_L → front_L → front_R →
// back_R，锚点 = 各片腰口弧（top_chain）链端点，恰为 CB/侧缝×2/前中
// （有 yoke 时后侧腰口件 = 育克上口，后片自身上口交给育克下口缝）。
// 前口袋袋贴（2026-09-15，front_facing 第 5 片）：袋贴外边 1:1 复制前
// 大片（腰弧段 top_chain + 外缝弧段 side），按真实装配缝——side 缝育克
// 侧边（无 yoke 缝后片侧缝上端）、整片钉摆位（衬布式贴合：解算空间
// 芯体填满筒内、袋贴垂坠动力学只会与筒面抢壳 z-fight，先钉满保「缝在
// 正确位置」的展示语义）；袋口 mouth 边保持 free（口袋开口）。
// 口袋挖削（前片有 mouth 边）时侧缝配对改道：前片侧缝自 P2 起（腰口
// 侧段被挖削接管），全长配后片侧缝**下段**（1:1 弧长自脚口端），后片
// 上段余量（袋布侧边位置，无袋布片）保持开放——旧口径前片全长对后片
// 全长，把前片 P2 硬拉到后片腰角，口袋区被剪切错位 ~4.4cm。
// 直腰头布片仅限无挖削款：挖削腰口弧缺段 + 袋布桥无片可缝，腰头底长
// 与腰口弧对不上账（checkBandLength 必炸），一律回退视觉环带（同弯
// 腰头）。弯腰头回退环带 2026-09-15 起改为**钉住腰口粒子成环**（沿真实
// 腰口弧高低/半径逐点跟随，buildWaistRingFromPins）：旧版平环挂
// field+1.5 半径，弯腰口弧前后中下垂 ~5cm，环带悬空成「腰头没连一起」。
// pin 模型（2026-09-13 用户口径升级）：直腰头 = 真实布片，pin = 腰头
// 上沿（belt line）粒子只钉 Y——高度锚住整裤防滑落；其余自由：底沿交
// 四腰缝、行距交真实布长、环向余量整环均匀浮起（真松腰带形态）；前后
// 片靠腰缝约束悬挂——裤子从腰带线挂着，腰不再是死边。弯腰头回退：视
// 觉环带 + 各片腰口全向 pin（旧一期口径，有 yoke 时腰口件含育克上口；
// 袋贴腰弧段并入 top_chain pin，其余粒子整片钉）。
import type { FittingResult } from '../../types'
import type { ClothMesh, EdgeRun } from './mesh'
import { runIndexAt } from './mesh'
import { buildBandMesh, checkBandLength } from './band'
import { MESH_PRIOR, SOLVER_PRIOR } from './priors'
import type { BodyField, PieceKey, Side } from './placement'
import { bandWarp, placePoint } from './placement'

export interface GarmentPart {
  key: PieceKey
  side: Side
  mesh: ClothMesh
  offset: number          // 粒子全局号 = offset + 网格顶点号
}

export interface Garment {
  parts: GarmentPart[]    // [fL, fR, bL, bR, yL, yR?, band?]（yoke 仅
                          // back_yoke 开启；band 仅直腰头）
  pos: Float32Array       // 3P 初始位置（包裹摆位，非穿透）
  triAll: Uint32Array     // 全片合并三角形（全局粒子号；松量切片用——
                          // 缝合对不是共享顶点，须合并才能切出跨缝闭环）
  seam: Int32Array        // 2S 缝合粒子对
  seamRank: Float32Array  // S：缝合对拉链激活序（段内锚点→末端 0..1，
                          // preRelax 渐进激活用；侧缝锚=脚口端、腰缝锚=段边界）
  pinIdx: Uint32Array     // pin 粒子号（直腰头=腰头上沿 belt line；回退=腰口粒子）
  pinTarget: Float32Array // 3×pin 粒子目标位（初始摆位处）
  pinYOnly: boolean       // pin 只钉 Y（直腰头：belt line 高度锚整裤，环向/
                          // 径向自由交给碰撞地板+四腰缝；回退腰口=全向 pin）
  crotchIdx: Uint32Array  // 裆尖粒子（fL/fR=rise 链首、bL/bR=cb 链首；
                          // preRelax+早帧钉初始位防下垂，后释放）
  crotchTarget: Float32Array // 3×裆尖目标位（初始摆位处）
  total: number
  /** band 行高锚（pattern 腰站 y；bandWarp 用；null = 无真实腰头） */
  bandY0: number | null
  /** 回退视觉环带参数（弯腰头 或 口袋挖削款直腰头）；null = 有真实腰头布片 */
  bandFallback: { yWaist: number; width: number } | null
}

// 两条聚合段的子段配对：A 段弧长参数 [t0,t1]、B 段 [u0,u1]（均可反向
// 走），均分采样取段内最近顶点；n 取两段实长较长者 / seamStep。
// rank = k/(n-1)：激活序从 (t0,u0) 端向另一端推进。
function pairSeg(
  a: GarmentPart, runA: EdgeRun, t0: number, t1: number,
  b: GarmentPart, runB: EdgeRun, u0: number, u1: number,
  out: number[], rank: number[],
): void {
  const len = Math.max(Math.abs(t1 - t0) * runA.length,
    Math.abs(u1 - u0) * runB.length)
  const n = Math.max(2, Math.round(len / MESH_PRIOR.seamStep))
  for (let k = 0; k < n; k++) {
    const f = k / (n - 1)
    out.push(
      a.offset + runIndexAt(runA, t0 + (t1 - t0) * f),
      b.offset + runIndexAt(runB, u0 + (u1 - u0) * f))
    rank.push(f)
  }
}

// 两端全段配对特例：reverse=true 从末端起配（侧缝前后净长不等 0.61%，
// 脚口端对齐、余量上移——旧 pairRuns 口径，rank 锚 = 末端）
function pairRuns(
  a: GarmentPart, runA: EdgeRun,
  b: GarmentPart, runB: EdgeRun,
  reverse: boolean, out: number[], rank: number[],
): void {
  pairSeg(a, runA, reverse ? 1 : 0, reverse ? 0 : 1,
    b, runB, reverse ? 1 : 0, reverse ? 0 : 1, out, rank)
}

const runOf = (part: GarmentPart, name: string): EdgeRun | undefined =>
  part.mesh.runs.find((r) => r.name === name)

// 反转聚合段链向（indices/arc 镜像）：band 自身后中缝两竖边链向相反
// （end_a 上→下、end_b 下→上），同 t 配对会顶配底（Y 错 2W），先翻一条
const flipRun = (r: EdgeRun): EdgeRun => ({
  ...r,
  indices: [...r.indices].reverse(),
  arc: r.arc.map((a) => r.length - a).reverse(),
})

// top_chain 边（前=waist、后无 yoke=waist/有 yoke=top）按角色取
const topChainOf = (part: GarmentPart): EdgeRun | undefined =>
  part.mesh.runs.find((r) => r.role === 'top_chain')

const need = (part: GarmentPart, name: string): EdgeRun => {
  const r = runOf(part, name)
  if (!r) throw new Error(`缝合配对缺边：${part.key}.${part.side}.${name}`)
  return r
}

const thetaOf = (pos: Float32Array, i: number): number => {
  let t = Math.atan2(pos[3 * i], pos[3 * i + 2])
  if (t < 0) t += 2 * Math.PI
  return t
}

// 丹宁区域增硬（M2 悬垂保真）：弯曲边中点 pattern-y 落在裆/膝站
// ±denimRegionSpan 窗内 → 刚度 denimBendStiffness，窗外保持全局值。
// L/R 两半片共享同一 ClothMesh，一次标定两侧生效
export function markDenimBend(
  mesh: ClothMesh, stationYs: { crotch: number; knee: number },
): void {
  const span = SOLVER_PRIOR.denimRegionSpan
  const arr = new Float32Array(mesh.bend.length / 3)
  for (let c = 0, k = 0; c < mesh.bend.length; c += 3, k++) {
    const yMid = 0.5
      * (mesh.xy[2 * mesh.bend[c] + 1] + mesh.xy[2 * mesh.bend[c + 1] + 1])
    arr[k] = Math.abs(yMid - stationYs.crotch) <= span
      || Math.abs(yMid - stationYs.knee) <= span
      ? SOLVER_PRIOR.denimBendStiffness : SOLVER_PRIOR.bendStiffness
  }
  mesh.bendKArr = arr
}
const angDist = (a: number, b: number): number => {
  const d = Math.abs(a - b) % (2 * Math.PI)
  return Math.min(d, 2 * Math.PI - d)
}

// 腰缝：band 底边段 [s0,s1]（环向弧长）↔ 面板腰口弧。方向由两端粒子
// 实际 θ 与段端 θ 的距离判定（镜像片的腰弧链向与环序相反）
function pairWaist(
  band: GarmentPart, bandBottom: EdgeRun, bandLen: number,
  panel: GarmentPart, waist: EdgeRun, s0: number, s1: number,
  pos: Float32Array, out: number[], rank: number[],
): void {
  const th0 = Math.PI + (2 * Math.PI * s0) / bandLen
  const th1 = Math.PI + (2 * Math.PI * s1) / bandLen
  const thFirst = thetaOf(pos, panel.offset + waist.indices[0])
  const flip = angDist(thFirst, th1) < angDist(thFirst, th0)
  const segLen = s1 - s0
  const n = Math.max(2, Math.round(Math.max(segLen, waist.length)
    / MESH_PRIOR.seamStep))
  for (let k = 0; k < n; k++) {
    const u = k / (n - 1)
    const sT = s0 + u * segLen
    const t = flip ? 1 - u : u
    out.push(
      band.offset + runIndexAt(bandBottom, sT / bandLen),
      panel.offset + runIndexAt(waist, t))
    rank.push(u)   // 锚 = 段边界（与相邻腰缝段边界精确成对）
  }
}

// 布片网格集：front/back 恒有；yoke 仅 back_yoke 开启（引擎 payload
// 第 4 片 back_yoke，业务装配链见模块头注）；pocket 仅挖削款
// front_pocket_facing 开启（第 5 片 front_facing 袋贴）
export interface GarmentMeshes {
  front: ClothMesh
  back: ClothMesh
  yoke?: ClothMesh
  pocket?: ClothMesh
}

// 四半片（+育克半片、+直腰头）-> 整裤初始态（粒子、缝合、pin）。
// snap：可选单点吸附（把腰头粒子从凸包场环压到实际曲面+skin——人台腰
// 截面前移 ~8cm 且体侧凹，凸包支撑在体侧虚高 3.7cm，钉凸包环必悬空；
// worker 建 BVH 后传入，主线程静态首帧无 collider 时省略）
export function buildGarment(
  meshes: GarmentMeshes,
  result: FittingResult,
  warp: (y: number) => number,
  field: BodyField,
  snap?: (pos: Float32Array, i: number) => void,
): Garment {
  // 数据一致性守卫：后片上口边名 = top（机头下口线）必有育克件配套
  // （2026-09-14 起育克参与真实缝合；缺件 = payload 与网格不同源）
  const hasYoke = !!meshes.yoke
  if (meshes.back.runs.some((r) => r.name === 'top') && !hasYoke) {
    throw new Error('后片上口为机头线但缺育克网格——payload 与网格不一致')
  }
  if (hasYoke && !meshes.back.runs.some((r) => r.name === 'top')) {
    throw new Error('育克网格存在但后片上口非机头线——payload 与网格不一致')
  }
  // fly 连裁拦截：前中缝链只剩裆下残段、fly 区 free 边敞口（坑 #3）
  if (!meshes.front.runs.some((r) => r.name === 'rise')) {
    throw new Error('连裁门襟（fly）暂不支持 3D 试穿——请改分体门襟或关闭后重试')
  }

  const parts: GarmentPart[] = []
  let offset = 0
  const panelMeshes: [PieceKey, ClothMesh][] = [
    ['front', meshes.front], ['back', meshes.back],
    ...(hasYoke ? [['yoke', meshes.yoke!] as [PieceKey, ClothMesh]] : []),
    ...(meshes.pocket ? [['pocket', meshes.pocket] as [PieceKey, ClothMesh]] : []),
  ]
  for (const [key, mesh] of panelMeshes) {
    for (const side of ['L', 'R'] as Side[]) {
      parts.push({ key, side, mesh, offset })
      offset += mesh.xy.length / 2
    }
  }
  // 丹宁裆/膝区域增硬（站高缺省不标定，退全局刚度；育克在腰胯部、
  // 远离裆/膝 ±span 窗，不标定）
  {
    const stY = (k: string) => result.body.stations.find((s) => s.key === k)?.y
    const crotchY = stY('crotch'), kneeY = stY('knee')
    if (crotchY !== undefined && kneeY !== undefined) {
      markDenimBend(meshes.front, { crotch: crotchY, knee: kneeY })
      markDenimBend(meshes.back, { crotch: crotchY, knee: kneeY })
    }
  }
  const P = (key: PieceKey, side: Side): GarmentPart =>
    parts.find((p) => p.key === key && p.side === side)!

  // 腰口件（业务链）：后侧上腰头的是育克（有 yoke 时），前侧恒为前片；
  // 后片自身上口（top）改缝育克下口
  const waistPartOf = (key: 'front' | 'back', side: Side): GarmentPart =>
    key === 'back' && hasYoke ? P('yoke', side) : P(key, side)

  // ---- 直腰头布片（scalars 重建矩形；弯腰头/挖削款回退视觉环带+腰口 pin） ----
  const wbPiece = result.pieces.find((p) => p.key === 'waistband')
  const wbScalars = wbPiece?.scalars
  // 挖削款（前片 mouth 边存在）：腰口弧缺段 + 袋布桥无片可缝，直腰头
  // 底长对不上账（checkBandLength 必炸）——一律走视觉环带回退
  const carve = meshes.front.runs.some((r) => r.name === 'mouth')
  const straight = result.body.waistband_type === 'straight' && !carve
  const waistSt = result.body.stations.find((s) => s.key === 'waist')
  if (!waistSt) throw new Error('payload 缺 waist 站——y-warp/腰缝锚点失效')
  let band: GarmentPart | null = null
  let bandFallback: Garment['bandFallback'] = null
  if (straight && wbScalars) {
    const arcs = [waistPartOf('back', 'L'), waistPartOf('front', 'L'),
      waistPartOf('front', 'R'), waistPartOf('back', 'R')]
      .map((p) => topChainOf(p)?.length ?? 0)
    checkBandLength(wbScalars.bottom_length, arcs)
    const mesh = buildBandMesh({
      length: wbScalars.bottom_length,
      width: wbScalars.width,
      y0: waistSt.y,
    })
    band = { key: 'band', side: 'L', mesh, offset }
    offset += mesh.xy.length / 2
    parts.push(band)
  } else {
    bandFallback = {
      yWaist: warp(waistSt.y),
      width: warp(waistSt.y + result.body.waistband_width) - warp(waistSt.y),
    }
  }

  const total = offset
  const pos = new Float32Array(3 * total)

  // ---- 摆位（右半镜像 θ→−θ；band 整圈；band 行高=腰站锚+真布高；
  // pocket 走 front 扇区且用前片 x 全程归一——见 placement.placePoint） ----
  const warpForBand = bandWarp(warp, waistSt.y)
  let frontXMin = Infinity, frontXMax = -Infinity
  for (let i = 0; i < meshes.front.xy.length; i += 2) {
    frontXMin = Math.min(frontXMin, meshes.front.xy[i])
    frontXMax = Math.max(frontXMax, meshes.front.xy[i])
  }
  for (const part of parts) {
    const { xy } = part.mesh
    const off = part.offset
    const warpPart = part.key === 'band' ? warpForBand : warp
    let xMin = Infinity, xMax = -Infinity
    if (part.key === 'pocket') {
      xMin = frontXMin; xMax = frontXMax
    } else {
      for (let i = 0; i < xy.length; i += 2) {
        xMin = Math.min(xMin, xy[i]); xMax = Math.max(xMax, xy[i])
      }
    }
    for (let i = 0; i < xy.length / 2; i++) {
      const [px, py, pz] = placePoint(
        part.key, part.side, xy[2 * i], xy[2 * i + 1], xMin, xMax, warpPart,
        field)
      pos[3 * (off + i)] = px
      pos[3 * (off + i) + 1] = py
      pos[3 * (off + i) + 2] = pz
    }
  }
  // 腰头吸附实际曲面（凸包场体侧虚高 → 钉真实腰环；面板仍留松量摆位，
  // 动力学沉降自理）。band rest 不做任何重定——全保纸样矩形（无预应变
  // 的真布）：摆位/warp 顶段外推造成的行距拉伸由动力学压回真实 4cm 布
  // 宽。实测教训：按吸附构型重定跨行 rest 会与环向纸样 rest 自相矛盾
  // （吸附环周长 66.8 vs 纸样 70.1），预应力把 band 撑成上大下小喇叭且
  // 腰缝垂向永久拔河喂漂移（avgSpeed 平台 ~1.0 不收敛）。
  if (band && snap) {
    for (let i = 0; i < band.mesh.xy.length / 2; i++) snap(pos, band.offset + i)
  }

  // ---- 缝合配对（无 yoke 11 条 / 有 yoke 16 条，见模块头注） ----
  const seam: number[] = []
  const seamRank: number[] = []
  for (const side of ['L', 'R'] as Side[]) {
    const fSide = need(P('front', side), 'side')
    const bSide = need(P('back', side), 'side')
    if (carve) {
      // 挖削款侧缝（2026-09-15）：前侧链 = 袋贴侧边[O→深端]（1:1 复制
      // 挖削侧段）+ 前片侧缝[P2→hem]；后侧链 = 育克侧边 + 后片侧缝。
      // 前片侧缝自脚口端全长配后片侧缝下段，后侧链余量（育克侧边 +
      // 后片上端）配袋贴侧边——腰口端锚、沿链推进。旧口径前片全长对
      // 后片全长把 P2 硬拉到后侧链顶 = 口袋区 ~4cm 剪切错位的根因
      const ratio = Math.min(1, fSide.length / bSide.length)
      pairSeg(P('front', side), fSide, 1, 0,
        P('back', side), bSide, 1, 1 - ratio, seam, seamRank)
      if (meshes.pocket) {
        const pSide = need(P('pocket', side), 'side')   // t=0 = 腰口端 O
        const ySide = hasYoke ? need(P('yoke', side), 'side') : null
        // 后片侧缝上端余量（P2 水平以上 = 袋布侧位，无袋布片由袋贴吸收）
        const backUpper = Math.max(0, bSide.length - fSide.length)
        if (ySide) {
          if (backUpper < 0.01) {
            pairSeg(P('pocket', side), pSide, 0, 1,
              P('yoke', side), ySide, 1, 0, seam, seamRank)
          } else {
            const chainLen = ySide.length + backUpper
            const yShare = ySide.length / chainLen
            pairSeg(P('pocket', side), pSide, 0, yShare,
              P('yoke', side), ySide, 1, 0, seam, seamRank)
            pairSeg(P('pocket', side), pSide, yShare, 1,
              P('back', side), bSide, 0, backUpper / bSide.length,
              seam, seamRank)
          }
        } else if (backUpper > 0.01) {
          pairSeg(P('pocket', side), pSide, 0, 1,
            P('back', side), bSide, 0,
            Math.min(1, pSide.length / bSide.length), seam, seamRank)
        }
      }
    } else if (hasYoke) {
      // 侧缝链式拆分（业务链：机头把后片侧缝上段收归育克）——前片侧缝
      // 全长按弧长对开：下段配后片（脚口端对齐向上到交汇）、上段配育克
      // （自交汇续配到腰）。前后+育克侧缝净长和差 ~0.61% 按 M1 同口径
      // 全段对全段分数配对均匀吸收（应变 ~0.6%）；两段在前片 t=1-fb 处
      // 精确共点闭合三角（front↔back 交汇点 ↔ yoke 交汇点粒子本互缝）。
      // 勿改回按 fy 起配：fy+fb>1 会把交界 0.6cm 条带双重预订到交汇点
      // 上下两侧的目标（相距 ~1.2cm），四交汇点永久拔河=环向蠕动泵
      //（实测 avgSpeed 地板 4~12 随 basin 漂移永不收敛）
      const ySide = need(P('yoke', side), 'side')
      const fs = fSide.length
      const fb = Math.min(1, bSide.length / fs)   // 后片段占前片侧缝比（脚口端起）
      pairSeg(P('front', side), fSide, 1, 1 - fb,
        P('back', side), bSide, 1, 0, seam, seamRank)
      pairSeg(P('front', side), fSide, 1 - fb, 0,
        P('yoke', side), ySide, 0, 1, seam, seamRank)
    } else {
      pairRuns(P('front', side), fSide,
        P('back', side), bSide, true, seam, seamRank)
    }
    pairRuns(P('front', side), need(P('front', side), 'inseam'),
      P('back', side), need(P('back', side), 'inseam'), false, seam, seamRank)
  }
  pairRuns(P('front', 'L'), need(P('front', 'L'), 'rise'),
    P('front', 'R'), need(P('front', 'R'), 'rise'), false, seam, seamRank)
  pairRuns(P('back', 'L'), need(P('back', 'L'), 'cb'),
    P('back', 'R'), need(P('back', 'R'), 'cb'), false, seam, seamRank)
  if (hasYoke) {
    // 育克后中镜像（同后片 cb 口径）+ 育克下口↔后片上口（同一条机头
    // 下口线几何，端点本重合；链向若反则翻转配对，防顶配底）
    pairRuns(P('yoke', 'L'), need(P('yoke', 'L'), 'cb'),
      P('yoke', 'R'), need(P('yoke', 'R'), 'cb'), false, seam, seamRank)
    for (const side of ['L', 'R'] as Side[]) {
      const yb = need(P('yoke', side), 'bottom')
      const bt = need(P('back', side), 'top')
      const y0 = P('yoke', side).mesh.xy
      const b0 = P('back', side).mesh.xy
      const yHead = [y0[2 * yb.indices[0]], y0[2 * yb.indices[0] + 1]]
      const bHead = [b0[2 * bt.indices[0]], b0[2 * bt.indices[0] + 1]]
      const same = Math.hypot(yHead[0] - bHead[0], yHead[1] - bHead[1]) < 0.05
      pairSeg(P('yoke', side), yb, 0, 1,
        P('back', side), bt, same ? 0 : 1, same ? 1 : 0, seam, seamRank)
    }
  }

  if (band) {
    // 腰缝×4：环序 back_L → front_L → front_R → back_R（θ 自 CB 180° 起
    // 向左半圈推进，与 placePoint band 分支一致；后侧件 = 育克上口）
    const bottom = runOf(band, 'bottom')
    if (!bottom) throw new Error('腰头网格缺底边（bottom）')
    const bandLen = bottom.length
    const ring: [GarmentPart, EdgeRun][] = []
    for (const [key, side] of [['back', 'L'], ['front', 'L'],
      ['front', 'R'], ['back', 'R']] as const) {
      const part = waistPartOf(key, side)
      const w = topChainOf(part)
      if (!w) throw new Error(`缝合配对缺腰口边：${key}.${side}（top_chain）`)
      ring.push([part, w])
    }
    // 分点：按四片腰弧占比映射到 band 底边（Σ弧 ≈ bandLen 已过对账，
    // 微差按比例均摊，锚点落在段边界两侧精确成对）
    const arcSum = ring.reduce((a, [, w]) => a + w.length, 0)
    let s0 = 0
    for (const [panel, waist] of ring) {
      const s1 = s0 + (waist.length / arcSum) * bandLen
      pairWaist(band, bottom, bandLen, panel, waist, s0, s1, pos, seam,
        seamRank)
      s0 = s1
    }
    // 腰头自身后中缝：end_a（上→下）↔ flipRun(end_b)（翻成上→下），逐行对齐
    const endA = runOf(band, 'end_a'), endB = runOf(band, 'end_b')
    if (!endA || !endB) throw new Error('腰头网格缺端边（end_a/end_b）')
    pairRuns(band, endA, band, flipRun(endB), false, seam, seamRank)
  }

  // ---- pin：直腰头 = 只钉腰头上沿（belt line）Y——高度锚住整裤防滑
  // 落；腰头底沿交给四腰缝、行距交给真实布长（pattern rest），环向/径向
  // 全自由（周长 70.1 环 vs 人台腰 ~66 的余量=整环均匀浮起，真松腰带形
  // 态）。全体粒子 Y-pin 已否决：底行钉在 warp 高度 vs 面板腰口自然悬垂
  // 差 ~1.1cm，腰缝垂向永久拔河不收敛。弯腰头回退 = 四片腰口粒子全向
  // pin（旧口径） ----
  const pinIdx: number[] = []
  const pinTarget: number[] = []
  if (band) {
    const topRun = runOf(band, 'top')
    if (!topRun) throw new Error('腰头网格缺顶边（top）——belt line pin 失效')
    for (const idx of topRun.indices) {
      const gi = band.offset + idx
      pinIdx.push(gi)
      pinTarget.push(pos[3 * gi], pos[3 * gi + 1], pos[3 * gi + 2])
    }
  } else {
    for (const part of parts) {
      if (part.key === 'pocket') {
        // 袋贴整片钉摆位（衬布式贴合）：解算空间芯体填满筒内，袋贴垂坠
        // 动力学只会与筒面抢同一壳层 z-fight；「缝在前片正确位置」的
        // 展示语义优先（腰弧段本就是 top_chain，其余粒子一并钉住）
        for (let i = 0; i < part.mesh.xy.length / 2; i++) {
          const gi = part.offset + i
          pinIdx.push(gi)
          pinTarget.push(pos[3 * gi], pos[3 * gi + 1], pos[3 * gi + 2])
        }
        continue
      }
      const run = topChainOf(part)
      if (!run) continue
      for (const idx of run.indices) {
        const gi = part.offset + idx
        pinIdx.push(gi)
        pinTarget.push(pos[3 * gi], pos[3 * gi + 1], pos[3 * gi + 2])
      }
    }
  }

  // ---- 裆尖粒子（四缝交汇防下垂 pin）：rise/cb 聚合段链首 = 裆尖。
  // 育克/band 不参与（育克 cb 链首在腰部、非裆尖）。
  // 目标位 = 初始摆位原值（snap 到实际曲面已试过被否决：从 hull 摆位跳
  // 1~4cm 到会阴曲面后与缝合构型自相矛盾，四缝交汇处永久张力振荡，
  // avg 卡 ~3.2 不收敛）----
  const crotchIdx: number[] = []
  const crotchTarget: number[] = []
  for (const part of parts) {
    if (part.key === 'band' || part.key === 'yoke') continue
    const run = runOf(part, part.key === 'front' ? 'rise' : 'cb')
    if (!run || run.indices.length === 0) continue
    const gi = part.offset + run.indices[0]
    crotchIdx.push(gi)
    crotchTarget.push(pos[3 * gi], pos[3 * gi + 1], pos[3 * gi + 2])
  }

  // 全片合并三角形（松量切片跨缝闭环用；parts 已含 band 若直腰头）
  const triAll = new Uint32Array(
    parts.reduce((a, p) => a + p.mesh.tri.length, 0))
  let triWrite = 0
  for (const part of parts) {
    for (let t = 0; t < part.mesh.tri.length; t++) {
      triAll[triWrite++] = part.offset + part.mesh.tri[t]
    }
  }

  return {
    parts, pos, triAll,
    seam: new Int32Array(seam),
    seamRank: new Float32Array(seamRank),
    pinIdx: new Uint32Array(pinIdx),
    pinTarget: new Float32Array(pinTarget),
    pinYOnly: !!band,
    crotchIdx: new Uint32Array(crotchIdx),
    crotchTarget: new Float32Array(crotchTarget),
    total,
    bandY0: band ? waistSt.y : null,
    bandFallback,
  }
}

// 弯腰头视觉环带（静态、不参与仿真；2026-09-15 重做）：沿**腰口弧摆位
// 点**逐点成环——底圈 = 各片（front/back/yoke，不含袋贴）top_chain 边
// 的初始摆位点（θ 排序去重），真实腰口弧的高低/半径逐点跟随（弯腰口
// 前后中下垂 ~5cm 也能贴合，不再平环悬空出「腰头没连一起」的缝）；顶圈
// = 底圈 + 腰头宽。回退模式腰口粒子本就全向 pin，底圈与裤身永不脱开。
// 纯数组，three 装配在视图层
export function buildWaistRing(
  garment: Garment,
): { positions: number[]; indices: number[] } {
  const width = garment.bandFallback?.width
  if (!width) throw new Error('buildWaistRing 仅回退模式（bandFallback）可用')
  const pts: { th: number; x: number; y: number; z: number }[] = []
  for (const part of garment.parts) {
    if (part.key === 'band' || part.key === 'pocket') continue
    const run = topChainOf(part)
    if (!run) continue
    for (const idx of run.indices) {
      const gi = part.offset + idx
      pts.push({
        th: Math.atan2(garment.pos[3 * gi], garment.pos[3 * gi + 2]),
        x: garment.pos[3 * gi], y: garment.pos[3 * gi + 1],
        z: garment.pos[3 * gi + 2],
      })
    }
  }
  pts.sort((a, b) => a.th - b.th)
  // θ 去重（前后中缝两侧 pin 同 θ；余下即唯一环序）
  const ring = pts.filter((p, i) =>
    i === 0 || p.th - pts[i - 1].th > 1e-4)
  if (ring.length < 3) throw new Error('腰口弧点不足 3——环带不可建')
  const n = ring.length
  const positions: number[] = []
  const indices: number[] = []
  for (const p of ring) positions.push(p.x, p.y, p.z)
  for (const p of ring) positions.push(p.x, p.y + width, p.z)
  const idxAt = (k: number, top: boolean) => (k % n) + (top ? n : 0)
  for (let k = 0; k < n; k++) {
    indices.push(idxAt(k, false), idxAt(k + 1, false), idxAt(k + 1, true))
    indices.push(idxAt(k, false), idxAt(k + 1, true), idxAt(k, true))
  }
  return { positions, indices }
}
