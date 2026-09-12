// MakeHuman 原始网格直显（诊断用，?bodymesh=raw）：vendor/makehuman/base.obj
// 原样解析——只过滤 g body 皮肤面（helper-*/joint-* 辅助几何丢弃，与
// scripts/vendor_makehuman.py parse_obj 同口径），四边面扇形三角化 + 被
// 引用顶点紧缩。除「dm→cm ×10 + 落地平移」外零处理：不裁切/不去臂/
// 不摆姿势/不 morph/不对齐。MakeHuman 原生坐标：Y-up、dm 单位、原点
// 居中（脚底 y≈−8.45dm）、z 前后向。
export interface RawMeshData {
  positions: Float32Array   // cm，Y-up，脚底 y=0
  indices: Uint32Array
}

export async function loadRawObj(url: string): Promise<RawMeshData> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`raw.obj 拉取失败 ${res.status}`)
  const text = await res.text()
  const verts: number[] = []        // 原始 v 行平铺（dm）
  const tris: number[] = []         // body 组三角化（1-based）
  let cur = ''
  for (const ln of text.split('\n')) {
    if (ln.startsWith('g ')) {
      cur = ln.slice(2).trim()
    } else if (ln.startsWith('v ')) {
      const p = ln.trim().split(/\s+/)
      verts.push(+p[1] * 10, +p[2] * 10, +p[3] * 10)   // dm -> cm
    } else if (ln.startsWith('f ') && cur === 'body') {
      const p = ln.trim().split(/\s+/).slice(1).map((t) => +t.split('/')[0])
      for (let k = 1; k < p.length - 1; k++) {
        tris.push(p[0], p[k], p[k + 1])
      }
    }
  }
  // 顶点紧缩：body 面只引用子集（helper 组顶点丢弃），同时找落地 yMin
  const remap = new Map<number, number>()
  const out: number[] = []
  let yMin = Infinity
  const idx = new Uint32Array(tris.length)
  for (let t = 0; t < tris.length; t++) {
    const old = tris[t] - 1
    let ni = remap.get(old)
    if (ni === undefined) {
      ni = out.length / 3
      remap.set(old, ni)
      out.push(verts[3 * old], verts[3 * old + 1], verts[3 * old + 2])
      if (verts[3 * old + 1] < yMin) yMin = verts[3 * old + 1]
    }
    idx[t] = ni
  }
  for (let i = 1; i < out.length; i += 3) out[i] -= yMin
  return { positions: new Float32Array(out), indices: idx }
}
