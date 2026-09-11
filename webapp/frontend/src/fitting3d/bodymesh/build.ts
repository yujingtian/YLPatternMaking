// 网格人台出口（唯一路径）：asset + payload 站点 + 体型围度 -> Mannequin。
// 链路：纵向对齐（w=0 地标一次定标，横向恒等）→ 围度闭环标定
// （morph 权重，mesh 原生坐标量围）→ morph → 对齐到 payload 坐标 → 三管
// 高度场（骨盆/左右腿 R(y,θ) 表）→ Tube 环采样（y 降序 + hf 柄）。
// 渲染走 sourceMesh 直出 BufferGeometry、碰撞/摆位走 hf 查表——
// seams/pbd/collide 零改动的适配层（§10.11「真人网格人台」）。
// 只 type-import mannequin（防环：mannequin.ts 不依赖 bodymesh/）。
import type { FittingResult } from '../../types'
import type { BodyGirths } from '../bodyProfile'
import type { Mannequin, SectionParams, Tube } from '../mannequin'
import { BODYMESH_PRIOR } from '../priors'
import { applyVertical, fitVerticalAlign } from './align'
import { calibrateWeights } from './calibrate'
import { bindField, buildTubeFields, type HeightField } from './heightfield'
import { landmarkY, morphPositions } from './morph'
import type { BodyMeshAsset } from './types'

export function buildMeshMannequin(
  asset: BodyMeshAsset,
  body: FittingResult['body'],
  girths: BodyGirths,
): Mannequin {
  const yOf = (key: string): number =>
    (body.stations.find((s) => s.key === key)?.y ?? 0)
  // 站点守卫（沿用旧环模型口径）：crotch 不越过 hip−2、thigh 缺省派生
  const yHip = yOf('hip')
  const yCrotch = Math.min(yOf('crotch'), yHip - 2)
  const yKnee = yOf('knee'), yHem = yOf('hem')
  const yThigh = body.stations.some((s) => s.key === 'thigh')
    ? yOf('thigh')
    : yCrotch - BODYMESH_PRIOR.thighStationDrop

  // 1) 纵向对齐（w=0 地标；mesh 腿管/围度闭环都在 mesh 原生坐标做）。
  //    waist 节点：mesh 自然腰地标（vendor 最小围度带）↔ payload 腰站——
  //    缺该节点（合成网格）退化为三点分段，行为不变
  const base = asset.positions
  const meshWaist = asset.meta.landmarks.waist !== undefined
    ? landmarkY(base, asset, 'waist')
    : undefined
  const payloadWaist = body.stations.some((s) => s.key === 'waist')
    ? yOf('waist')
    : undefined
  // 腿场底 = 踝节点目标（脚口下 cm）：真脚（~13cm）整体落在场底之下，
  // 布料不可达（旧环模型口径；脚进高度场会以 θ≈0° 假半径污染脚口带碰撞）
  const yLegBottom = yHem - BODYMESH_PRIOR.legBelowHem
  const meshAnkle = asset.meta.landmarks.ankle !== undefined
    ? landmarkY(base, asset, 'ankle')
    : undefined
  const align = fitVerticalAlign(
    {
      crotch: landmarkY(base, asset, 'crotch'),
      knee: landmarkY(base, asset, 'knee'),
      sole: landmarkY(base, asset, 'sole'),
      ankle: meshAnkle,
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
  // 站高 = payload 站 unmap 回 mesh 坐标（布料贴合跟站点高度走）
  const targets = {
    waist: girths.waist,
    hip: girths.hip,
    thigh: girths.thigh ?? girths.hip * BODYMESH_PRIOR.thighGirthRatio,
    knee: girths.knee,
  }
  const stationYmesh = {
    waist: align.unmapY(yOf('waist')),
    hips: align.unmapY(yHip),
    thigh: align.unmapY(yThigh),
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

  // 4) 三管高度场（payload 坐标；骨盆裆下钳位延伸 / 腿管裆上头带 +
  //    底至踝——脚在场下不进碰撞）
  const meshTop = align.mapY(asset.meta.cut.planeY)
  const fields = buildTubeFields(pos, asset.indices, {
    crotch: yCrotch,
    top: meshTop,
    pelvisBottom: yCrotch - BODYMESH_PRIOR.pelvisBelowCrotch,
    legTop: yCrotch + BODYMESH_PRIOR.legAboveCrotch,
    legBottom: yLegBottom,
  })
  // 数据自检：三管顶行非空（切片全空 = 网格/对齐损坏；宁可炸不喂空碰撞体）
  for (const [k, f] of [['pelvis', fields.pelvis], ['legL', fields.legL],
    ['legR', fields.legR]] as const) {
    if (!(f.meanR[0] > 0)) {
      throw new Error(`bodymesh 高度场 ${k} 顶行为空（网格数据/对齐异常）`)
    }
  }

  return {
    pelvis: tubeOf(fields.pelvis),
    legs: [tubeOf(fields.legL), tubeOf(fields.legR)],
    topY: meshTop,
    bottomY: align.groundY,
    sourceMesh: { positions: pos, indices: asset.indices },
  }
}

// 高度场 -> Tube：环距 ringStep 采样，hf 柄闭包查表（双线性 y 夹端 + θ 环向）。
// a/bF/bB = 行均值、e=2 填充——hf 存在时 radiusAt 短路，这些仅供兜底路径；
// cx 逐环线性插值（Lipschitz 前提，与旧模型 cx 口径一致）
function tubeOf(f: HeightField): Tube {
  const hf = bindField(f)
  const n = Math.max(2,
    Math.round((f.yTop - f.yBottom) / BODYMESH_PRIOR.ringStep) + 1)
  const rings: SectionParams[] = []
  for (let k = 0; k < n; k++) {
    const t = k / (n - 1)
    const r = Math.min(Math.round(t * (f.rows - 1)), f.rows - 1)
    rings.push({
      y: f.yTop - (f.yTop - f.yBottom) * t,
      cx: f.cx[r], a: f.meanR[r], bF: f.meanR[r], bB: f.meanR[r], e: 2, hf,
    })
  }
  return { rings }
}
