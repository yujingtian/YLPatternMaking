// bodymesh 数据类型：MakeHuman 官方 12 个 measure target（腰/臀/大腿/膝/
// 小腿/踝）+ 身高 macro ±（共 14 场）的 TS 侧消费契约。裁切链契约（预标定
// 矩阵）已随调节链退役，演进史见决策日志 §十一。

export type TargetName =
  | 'waist+' | 'waist-' | 'hips+' | 'hips-'
  | 'thigh+' | 'thigh-' | 'knee+' | 'knee-'
  | 'calf+' | 'calf-' | 'ankle+' | 'ankle-'
  | 'height+' | 'height-'

export interface MeshTarget {
  name: TargetName
  idx: Uint32Array   // n 受影响顶点索引（切割后紧凑网格 0-based）
  d: Float32Array    // 3n 增量（cm）
}
