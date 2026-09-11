// bodymesh 数据契约：scripts/vendor_makehuman.py 产物的 TS 侧类型。
// base.bin（little-endian）布局（TS 解析在 load.ts，Python 金标镜像在
// tests/test_vendor_bodymesh.py::read_bin——三处同步改）：
//     uint32 V, uint32 F, uint32 T
//     float32 × 3V   顶点位置（cm，脚底 y=0、+Z 前、+X 模特右）
//     uint32  × 3F   三角形索引（0-based）
//     每 target 依次：uint32 n；uint32 × n 顶点索引；float32 × 3n 增量（cm）
// targets.json：地标顶点索引 / 站点 / 预标定影响矩阵 / sha256 溯源。

export type TargetName =
  | 'waist+' | 'waist-' | 'hips+' | 'hips-'
  | 'thigh+' | 'thigh-' | 'knee+' | 'knee-'

export interface MeshTarget {
  name: TargetName
  idx: Uint32Array   // n 受影响顶点索引
  d: Float32Array    // 3n 增量（cm）
}

// 预标定影响矩阵：target × 站点 -> w=0/0.5/1 围度三点（cm；null = 切片失败）
export type CalibrationMatrix = Record<TargetName,
  Record<'waist' | 'hips' | 'thigh' | 'knee', (number | null)[]>>

export interface BodyMeshMeta {
  vertexCount: number
  triangleCount: number
  targets: { name: TargetName; file: string; count: number }[]
  landmarks: Record<string, number>        // 地标名 -> 顶点索引（morph 后重读坐标）
  landmarkHeights: Record<string, number>  // w=0 高度 cm（仅诊断；对齐用顶点索引重读）
  cut: { aboveWaistCm: number; planeY: number }
  stations: { name: string; per: 'body' | 'leg'; y: number }[]
  calibration: CalibrationMatrix
}

export interface BodyMeshAsset {
  positions: Float32Array   // 3V 基网格（w=0）
  indices: Uint32Array      // 3F 三角形
  targets: MeshTarget[]     // 与 meta.targets 同序
  meta: BodyMeshMeta
}
