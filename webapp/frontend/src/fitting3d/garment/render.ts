// garment three 装配：parts -> Group（每片一 Mesh，共享白坯材质），
// position attr 直写 + computeVertexNormals；update(pos) 供解算每帧
// 回填（M1）。setStrain（M2 应变热力图）：逐粒子顶点色 + 材质基色翻白
// （vertex color 与材质色相乘，热力图态基色必须纯白防偏色）。
// three 模块由调用方注入（Fitting3DView 惰性分包口径）。
import type * as ThreeT from 'three'
import type { Garment } from './seams'
import type { buildWaistRing } from './seams'
import { strainColor } from './heatmap'

type ThreeMod = typeof import('three')

const BASE_COLOR = 0x5b7db1

export interface GarmentView {
  group: ThreeT.Group
  /** 解算帧回填：全粒子位置直写 + 法线重算（transferable 前提下零分配） */
  update: (pos: Float32Array) => void
  /** 应变热力图：strain=逐粒子应变（null=还原白坯）。数组是全局粒子号序 */
  setStrain: (strain: Float32Array | null) => void
  dispose: () => void
}

export function buildGarmentView(
  THREE: ThreeMod, garment: Garment,
): GarmentView {
  const group = new THREE.Group()
  group.name = 'garment'
  const mat = new THREE.MeshStandardMaterial({
    color: BASE_COLOR, roughness: 0.9, metalness: 0.0,
    side: THREE.DoubleSide,
    transparent: true, opacity: 0.92,
    vertexColors: true,   // 常开：白坯态顶点色写白，热力图态写应变色
  })
  const meshes: {
    mesh: ThreeT.Mesh
    attr: ThreeT.BufferAttribute
    col: ThreeT.BufferAttribute
    offset: number
    n: number
  }[] = []
  for (const part of garment.parts) {
    const n = part.mesh.xy.length / 2
    const geo = new THREE.BufferGeometry()
    const arr = new Float32Array(3 * n)
    const col = new Float32Array(3 * n).fill(1)   // 白坯基色
    const off = part.offset
    for (let i = 0; i < n; i++) {
      arr[3 * i] = garment.pos[3 * (off + i)]
      arr[3 * i + 1] = garment.pos[3 * (off + i) + 1]
      arr[3 * i + 2] = garment.pos[3 * (off + i) + 2]
    }
    const attr = new THREE.BufferAttribute(arr, 3)
    geo.setAttribute('position', attr)
    geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
    const idx: number[] = []
    for (let t = 0; t < part.mesh.tri.length; t++) {
      idx.push(part.mesh.tri[t])   // 顶点号已是 part 内局部号
    }
    geo.setIndex(idx)
    geo.computeVertexNormals()
    const mesh = new THREE.Mesh(geo, mat)
    mesh.name = `garment-${part.key}-${part.side}`
    group.add(mesh)
    meshes.push({ mesh, attr, col: geo.getAttribute('color') as ThreeT.BufferAttribute, offset: off, n })
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
  const setStrain = (strain: Float32Array | null) => {
    mat.color.set(strain ? 0xffffff : BASE_COLOR)
    for (const m of meshes) {
      const arr = m.col.array as Float32Array
      for (let i = 0; i < m.n; i++) {
        const [r, g, b] = strain
          ? strainColor(strain[m.offset + i]) : [1, 1, 1]
        arr[3 * i] = r; arr[3 * i + 1] = g; arr[3 * i + 2] = b
      }
      m.col.needsUpdate = true
    }
  }
  return {
    group,
    update,
    setStrain,
    dispose: () => {
      for (const { mesh } of meshes) mesh.geometry.dispose()
      mat.dispose()
    },
  }
}

// 弯腰头回退视觉环带 -> Mesh（静态条带；不参与仿真）
export function buildWaistRingMesh(
  THREE: ThreeMod, ring: ReturnType<typeof buildWaistRing>,
): ThreeT.Mesh {
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position',
    new THREE.Float32BufferAttribute(ring.positions, 3))
  geo.setIndex(ring.indices)
  geo.computeVertexNormals()
  const mat = new THREE.MeshStandardMaterial({
    color: 0x5b7db1, roughness: 0.9, metalness: 0.0,
    side: THREE.DoubleSide,
    transparent: true, opacity: 0.92,
  })
  return new THREE.Mesh(geo, mat)
}
