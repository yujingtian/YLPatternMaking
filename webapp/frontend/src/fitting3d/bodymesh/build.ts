// 网格人台出口（唯一路径）：asset + payload 站点 + 体型围度 -> 真人网格。
// 链路：纵向对齐（w=0 地标一次定标，横向恒等）→ 围度闭环标定
// （morph 权重，mesh 原生坐标量围）→ morph → 对齐到 payload 坐标。
// 渲染走 sourceMesh 直出 BufferGeometry。
// 2026-09-12 裁撤试穿：三管高度场碰撞桥（骨盆/左右腿 R(y,θ) 表）随
// PBD/碰撞链退役，出口只剩网格本体 + 顶底高度。
import type { FittingResult } from '../../types'
import type { BodyGirths } from '../bodyProfile'
import { BODYMESH_PRIOR } from '../priors'
import { applyVertical, fitVerticalAlign } from './align'
import { calibrateWeights } from './calibrate'
import { landmarkY, morphPositions } from './morph'
import type { BodyMeshAsset } from './types'

export interface MeshMannequin {
  topY: number
  bottomY: number      // 站立地面（= 对齐后脚底；格网/落地参照）
  sourceMesh: { positions: Float32Array; indices: Uint32Array }
}

export function buildMeshMannequin(
  asset: BodyMeshAsset,
  body: FittingResult['body'],
  girths: BodyGirths,
): MeshMannequin {
  const yOf = (key: string): number =>
    (body.stations.find((s) => s.key === key)?.y ?? 0)
  // 站点守卫（沿用旧环模型口径）：crotch 不越过 hip−2、thigh 缺省派生
  const yHip = yOf('hip')
  const yCrotch = Math.min(yOf('crotch'), yHip - 2)
  const yKnee = yOf('knee'), yHem = yOf('hem')
  const yThigh = body.stations.some((s) => s.key === 'thigh')
    ? yOf('thigh')
    : yCrotch - BODYMESH_PRIOR.thighStationDrop

  // 1) 纵向对齐（w=0 地标；mesh 围度闭环在 mesh 原生坐标做）。
  //    waist 节点：mesh 自然腰地标（vendor 最小围度带）↔ payload 腰站——
  //    缺该节点（合成网格）退化为三点分段，行为不变
  const base = asset.positions
  const meshWaist = asset.meta.landmarks.waist !== undefined
    ? landmarkY(base, asset, 'waist')
    : undefined
  const payloadWaist = body.stations.some((s) => s.key === 'waist')
    ? yOf('waist')
    : undefined
  // 踝对齐目标 = 脚口下 legBelowHem：真脚（~13cm）整体落踝节点之下
  const yLegBottom = yHem - BODYMESH_PRIOR.legBelowHem
  const meshAnkle = asset.meta.landmarks.ankle !== undefined
    ? landmarkY(base, asset, 'ankle')
    : undefined
  const meshCrotch = landmarkY(base, asset, 'crotch')
  const meshHip = asset.meta.landmarks.hip !== undefined
    ? landmarkY(base, asset, 'hip')
    : undefined
  const align = fitVerticalAlign(
    {
      crotch: meshCrotch,
      knee: landmarkY(base, asset, 'knee'),
      sole: landmarkY(base, asset, 'sole'),
      ankle: meshAnkle !== undefined ? yLegBottom : undefined,
      waist: meshWaist !== undefined && payloadWaist !== undefined
        ? meshWaist
        : undefined,
    },
    {
      crotch: yCrotch, knee: yKnee, hem: yHem,
      ankle: meshAnkle !== undefined ? yLegBottom : undefined,
      waist: meshWaist !== undefined && payloadWaist !== undefined
        ? payloadWaist
        : undefined,
    })

  // 2) 围度闭环：目标 = 体型围度（thigh 缺省 hip×ratio 同旧口径），
  // 测点口径见下方 stationYmesh 注释
  const targets = {
    waist: girths.waist,
    hip: girths.hip,
    thigh: girths.thigh ?? girths.hip * BODYMESH_PRIOR.thighGirthRatio,
    knee: girths.knee,
  }
  // 测点 = mesh 解剖站而非 payload 版线的 unmap（2026-09-12 裆叉/错位
  // 双重根因修复，此前「布料贴合跟站点高度走」口径被数字否决）：
  // · thigh 站钳到裆叉下 thighStationDrop：引擎毗围线默认与裆线等高
  //   （thigh_measure_offset=0），unmap 恰落叉点上——该处「腿环」含伸到
  //   x≈0.6 的裆桥，w=0 实测 59.2cm 虚高 ~10cm 且切片差 1e-5cm 围度
  //   ±1.4cm 病态敏感，闭环为凑数解出 thigh−≈1.8 把大腿整段挖空
  //   （「腿内凹 + 臀腿交界起伏」报障根因）；
  // · hips 钉解剖臀峰地标：unmap(payload 臀线) 因躯干段压缩（实测
  //   0.735）偏臀峰 +4.7cm，hips± 作用带上移出 vendor 设计域（围裙带
  //   包络锯齿贡献项）。waist/knee 无此病（均为对齐节点，偏差 0）。
  const stationYmesh = {
    waist: align.unmapY(yOf('waist')),
    hips: meshHip ?? align.unmapY(yHip),
    thigh: Math.min(align.unmapY(yThigh),
      meshCrotch - BODYMESH_PRIOR.thighStationDrop),
    knee: align.unmapY(yKnee),
  }
  const calib = calibrateWeights(asset, targets, stationYmesh)
  if (!calib.converged) {
    // 病理体型钳制披露（诚实降级：「腿确实比盆宽」先例）
    // eslint-disable-next-line no-console
    console.warn('[fitting3d] bodymesh 围度标定未收敛（权重钳制降级）',
      calib.residual)
  }

  // 3) morph + 纵向对齐 -> payload 坐标网格（渲染 sourceMesh）
  const pos = applyVertical(morphPositions(asset, calib.weights), align)
  const meshTop = align.mapY(asset.meta.cut.planeY)

  return {
    topY: meshTop,
    bottomY: align.groundY,
    sourceMesh: { positions: pos, indices: asset.indices },
  }
}
