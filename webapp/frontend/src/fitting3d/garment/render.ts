// garment three 装配：parts -> Group（每片一 Mesh，按片 key 分色材质
// ——2026-09-15 三期平铺：全裁片同色无法区分，逐片色板 PIECE_COLORS）。
// 重建一期（2026-09-15）为静态展示：解算帧回填通道保留（update 直写
// 全粒子位 + 法线重算），应变热力图/视觉环带随解算链删除。
// 2026-09-16 四期前身缝合立起：悬挂展示宿主不渲染，前片/袋贴双 rider
// 贴层（rider.ts 绑定宿主三角形，每帧 rideRider 回填）；本文件增补
// buildRiderView 与 buildGarmentView 同材质口径（分色/DoubleSide）。
// three 模块由调用方注入（Fitting3DView 惰性分包口径）。
import type * as ThreeT from 'three'
import type { Garment } from './assemble'
import type { ClothMesh } from './mesh'
import type { RiderBind } from './rider'
import { rideRider } from './rider'

type ThreeMod = typeof import('three')

// 片 key -> 展示色（UI 图例同源取色，hex 前端/图例共用）
export const PIECE_COLORS: Record<string, number> = {
  front_piece: 0x5b7db1,   // 前片 蓝
  back_piece: 0x679e56,    // 后片 绿
  waistband: 0xd9a05b,     // 腰头 橙
  back_yoke: 0x9a7fc9,     // 后育克 紫
  front_facing: 0x4fada0,  // 袋贴 青
}
export const DEFAULT_PIECE_COLOR = 0x8a8f98   // 未登记片（后续加片先补色板）

export function pieceColor(key: string): number {
  return PIECE_COLORS[key] ?? DEFAULT_PIECE_COLOR
}

export interface GarmentView {
  group: ThreeT.Group
  /** 位置回填：全粒子位置直写 + 法线重算（静态展示建视图时用一次） */
  update: (pos: Float32Array) => void
  dispose: () => void
}

export function buildGarmentView(
  THREE: ThreeMod, garment: Garment,
): GarmentView {
  const group = new THREE.Group()
  group.name = 'garment'
  const mats: ThreeT.MeshStandardMaterial[] = []
  const matOf = (key: string): ThreeT.MeshStandardMaterial => {
    const mat = new THREE.MeshStandardMaterial({
      color: pieceColor(key), roughness: 0.9, metalness: 0.0,
      side: THREE.DoubleSide,
      transparent: true, opacity: 0.92,
    })
    mats.push(mat)
    return mat
  }
  const meshes: { mesh: ThreeT.Mesh; attr: ThreeT.BufferAttribute }[] = []
  for (const part of garment.parts) {
    const n = part.mesh.xy.length / 2
    const geo = new THREE.BufferGeometry()
    const arr = new Float32Array(3 * n)
    const off = part.offset
    for (let i = 0; i < n; i++) {
      arr[3 * i] = garment.pos[3 * (off + i)]
      arr[3 * i + 1] = garment.pos[3 * (off + i) + 1]
      arr[3 * i + 2] = garment.pos[3 * (off + i) + 2]
    }
    const attr = new THREE.BufferAttribute(arr, 3)
    geo.setAttribute('position', attr)
    const idx: number[] = []
    for (let t = 0; t < part.mesh.tri.length; t++) {
      idx.push(part.mesh.tri[t])   // 顶点号已是 part 内局部号
    }
    geo.setIndex(idx)
    geo.computeVertexNormals()
    const mesh = new THREE.Mesh(geo, matOf(part.key))
    mesh.name = `garment-${part.key}-${part.side}`
    group.add(mesh)
    meshes.push({ mesh, attr })
  }
  const update = (pos: Float32Array) => {
    for (let pi = 0; pi < garment.parts.length; pi++) {
      const part = garment.parts[pi]
      const { attr } = meshes[pi]
      const arr = attr.array as Float32Array
      const off = part.offset
      const n = part.mesh.xy.length / 2
      for (let i = 0; i < n; i++) {
        arr[3 * i] = pos[3 * (off + i)]
        arr[3 * i + 1] = pos[3 * (off + i) + 1]
        arr[3 * i + 2] = pos[3 * (off + i) + 2]
      }
      attr.needsUpdate = true
      meshes[pi].mesh.geometry.computeVertexNormals()
    }
  }
  return {
    group,
    update,
    dispose: () => {
      for (const { mesh } of meshes) mesh.geometry.dispose()
      for (const mat of mats) mat.dispose()
    },
  }
}

// ---- 贴层视图（四期前身缝合立起）：被载片（前片/袋贴）随宿主解算位
// 逐帧回填。每 slot（L/R）一 Mesh，key 用 payload 片 key 对色；袋贴
// slot 传负 radialOffset 衬里侧（前片盖袋口条带）。宿主本身不渲染。 ----
export interface RiderViewSlot {
  side: string            // 'L' | 'R'（展示命名；不参与几何）
  hostOffset: number      // 该 side 宿主 part 在解算数组的粒子偏移
  radialOffset: number    // 径向偏移 cm（负内偏；0 = 贴宿主面）
}

export interface RiderView {
  group: ThreeT.Group
  /** 宿主解算位 -> 双 side 贴层回填 + 法线重算（建视图后先调一次出初摆位） */
  update: (hostPos: Float32Array) => void
  dispose: () => void
}

export function buildRiderView(
  THREE: ThreeMod, key: string, bind: RiderBind, slots: RiderViewSlot[],
): RiderView {
  const group = new THREE.Group()
  group.name = `rider-${key}`
  const n = bind.mesh.xy.length / 2
  const mat = new THREE.MeshStandardMaterial({
    color: pieceColor(key), roughness: 0.9, metalness: 0.0,
    side: THREE.DoubleSide,
    transparent: true, opacity: 0.92,
  })
  const entries: { mesh: ThreeT.Mesh; attr: ThreeT.BufferAttribute; slot: RiderViewSlot }[] = []
  const idx: number[] = []
  for (let t = 0; t < bind.mesh.tri.length; t++) idx.push(bind.mesh.tri[t])
  for (const slot of slots) {
    const geo = new THREE.BufferGeometry()
    const attr = new THREE.BufferAttribute(new Float32Array(3 * n), 3)
    geo.setAttribute('position', attr)
    geo.setIndex(idx)
    geo.computeVertexNormals()
    const mesh = new THREE.Mesh(geo, mat)
    mesh.name = `rider-${key}-${slot.side}`
    group.add(mesh)
    entries.push({ mesh, attr, slot })
  }
  const update = (hostPos: Float32Array) => {
    for (const { attr, slot } of entries) {
      rideRider(bind, hostPos, slot.hostOffset, attr.array as Float32Array, slot.radialOffset)
      attr.needsUpdate = true
      // slot.mesh 同 entries 内一一对应；法线重算
    }
    for (const { mesh } of entries) mesh.geometry.computeVertexNormals()
  }
  return {
    group,
    update,
    dispose: () => {
      for (const { mesh } of entries) mesh.geometry.dispose()
      mat.dispose()
    },
  }
}

// ---- sim 参与片直渲视图（九期腰头立体化）：腰头是解算参与片（非贴层
// ——bandWaist/bandEnds 缝对直连裤身），从 sim 粒子位逐帧直拷三角形
// 几何 + 法线重算。key 用 payload 片 key 对色（waistband 橙）。 ----
export interface SimView {
  group: ThreeT.Group
  /** sim 解算位 + part 偏移 -> 几何回填（建视图后先调一次出初摆位） */
  update: (simPos: Float32Array, offset: number) => void
  dispose: () => void
}

export function buildSimView(
  THREE: ThreeMod, key: string, mesh: ClothMesh,
): SimView {
  const group = new THREE.Group()
  group.name = `sim-${key}`
  const n = mesh.xy.length / 2
  const mat = new THREE.MeshStandardMaterial({
    color: pieceColor(key), roughness: 0.9, metalness: 0.0,
    side: THREE.DoubleSide,
    transparent: true, opacity: 0.92,
  })
  const geo = new THREE.BufferGeometry()
  const attr = new THREE.BufferAttribute(new Float32Array(3 * n), 3)
  geo.setAttribute('position', attr)
  geo.setIndex(Array.from(mesh.tri))
  const m = new THREE.Mesh(geo, mat)
  m.name = `sim-${key}`
  group.add(m)
  const update = (simPos: Float32Array, offset: number) => {
    const arr = attr.array as Float32Array
    for (let i = 0; i < n; i++) {
      arr[3 * i] = simPos[3 * (offset + i)]
      arr[3 * i + 1] = simPos[3 * (offset + i) + 1]
      arr[3 * i + 2] = simPos[3 * (offset + i) + 2]
    }
    attr.needsUpdate = true
    geo.computeVertexNormals()
  }
  return {
    group,
    update,
    dispose: () => {
      geo.dispose()
      mat.dispose()
    },
  }
}
