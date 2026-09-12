// bodymesh 数据类型（2026-09-12 全身原生链）：MakeHuman 官方 measure
// target 的 TS 侧消费契约。裁切链契约（base.bin 布局/预标定矩阵）已随
// 调节链退役，演进史见决策日志 §十一。

export type TargetName =
  | 'waist+' | 'waist-' | 'hips+' | 'hips-'
  | 'thigh+' | 'thigh-' | 'knee+' | 'knee-'

export interface MeshTarget {
  name: TargetName
  idx: Uint32Array   // n 受影响顶点索引（base.obj 原始 0-based 顶点号）
  d: Float32Array    // 3n 增量（cm）
}
