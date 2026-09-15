// garment three 装配：parts -> Group（每片一 Mesh，按片 key 分色材质
// ——2026-09-15 三期平铺：全裁片同色无法区分，逐片色板 PIECE_COLORS）。
// 重建一期（2026-09-15）为静态展示：无解算帧回填通道保留（后续重建
// 直接复用），应变热力图/视觉环带随解算链删除。
// three 模块由调用方注入（Fitting3DView 惰性分包口径）。
import type * as ThreeT from 'three'
import type { Garment } from './assemble'

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
