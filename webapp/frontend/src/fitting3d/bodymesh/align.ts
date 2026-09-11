// 纵向对齐：mesh y -> payload y 的**分段线性 y-warp**（sole/ankle→目标 /
// knee→knee / crotch→crotch / waist→waist 节点精确过点 + 顶上斜率 1.0 外推）。
// **横向恒等**——围度全部由 morph 闭环标定负责；若按高度均匀缩放，围度会随
// 比例横向膨胀，闭环再反向压权重徒增耦合。
// 为何分段而非单一仿射（2026-09-12 实测真数据定案）：mesh 与 payload 腿比例
// 非仿射——mesh 裆→膝 29.5 vs payload 36（短大腿）、mesh 自然腰 107.6 vs 腰站
// 98（长躯干）；LSQ 仿射下腰站落髂骨带（native 围 ~82 被 waist−=1.57 硬压到
// 66）、膝站落膝下 6.5cm。分段各段独立定斜率后：膝站回解剖膝、腰站回自然腰
//（morph 权重回 ~0.2 量级）。顶上（末节点以上）斜率 1.0：torso 不再压缩、
// topY 覆盖裤顶（腰+13 < 末节点 + (cut − waistMesh)）。
// 底部锚取踝关节（ankle 地标存在时）：踝→payload.ankle 精确过点、脚底沿
// slope 1.0 保真脚高。真脚高 ~13cm——若按 sole↔hem 地面配对，脚顶会被抬进
// 裤口带、腿高度场被脚污染（脚趾在腿轴前方 ~16cm，按角度 splat 成 θ≈0° 的
// 假半径 15+，脚口带碰撞把布往外推爆）；踝节点把脚整体放到腿场底
//（= hem − legBelowHem）之下，恢复「脚在裤口下、布料不可达」口径。
// ankle 地标缺省（合成网格/无地标数据）退化 sole↔hem 地面配对。
export interface VerticalAlign {
  /** [meshY, payloadY] 节点（升序；诊断/测试用） */
  nodes: ReadonlyArray<readonly [number, number]>
  /** mesh y -> payload y（人台最终坐标） */
  mapY: (y: number) => number
  /** payload y -> mesh y（标定在 mesh 原生坐标量围度用） */
  unmapY: (y: number) => number
  /** 对齐后脚底（= groundY；mesh 脚底 y=0 的映射） */
  groundY: number
}

// 升序节点表上的分段线性求值：区间内线性插值；顶上斜率 1.0、底下沿用首段斜率
//（mesh y 域外仅脚底微越界，实际不可达）
function evalNodes(
  nodes: ReadonlyArray<readonly [number, number]>, y: number,
): number {
  const n = nodes.length
  if (y >= nodes[n - 1][0]) return nodes[n - 1][1] + (y - nodes[n - 1][0])
  for (let i = 1; i < n; i++) {
    const [u0, v0] = nodes[i - 1]
    const [u1, v1] = nodes[i]
    if (y <= u1) return v0 + ((v1 - v0) / (u1 - u0)) * (y - u0)
  }
  return nodes[n - 1][1]
}

export function fitVerticalAlign(mesh: {
  crotch: number; knee: number; sole: number; ankle?: number; waist?: number
}, payload: {
  crotch: number; knee: number; hem: number; ankle?: number; waist?: number
}): VerticalAlign {
  // 节点按 mesh y 升序收集；两侧都需严格递增（掉非法节点而非抛错：waist 缺省
  // 是合成网格常态，比例退化则退化为纯 crotch/knee/sole 三点）
  const pairs: Array<[number, number]> = [
    ...(mesh.ankle !== undefined && payload.ankle !== undefined
      // 踝路径：脚底沿 slope 1.0 保真脚高（真脚整体落在腿场底之下）
      ? ([
        [mesh.sole, payload.ankle - (mesh.ankle - mesh.sole)],
        [mesh.ankle, payload.ankle],
      ] as Array<[number, number]>)
      : [[mesh.sole, payload.hem]] as Array<[number, number]>),
    [mesh.knee, payload.knee],
    [mesh.crotch, payload.crotch],
  ]
  if (mesh.waist !== undefined && payload.waist !== undefined) {
    pairs.push([mesh.waist, payload.waist])
  }
  pairs.sort((p, q) => p[0] - q[0])
  const nodes: Array<[number, number]> = []
  for (const p of pairs) {
    // 与末节点过近（mesh 侧重合或 payload 侧非增）= 比例退化，丢弃该节点
    if (!nodes.length || (p[0] - nodes[nodes.length - 1][0] > 1e-6
      && p[1] - nodes[nodes.length - 1][1] > 1e-6)) {
      nodes.push(p)
    }
  }
  if (nodes.length < 2) {
    throw new Error('mesh 站点退化（重合），无法纵向对齐')
  }
  // 段斜率健全性：0.2~5（同旧仿射守卫口径；分段后每段独立过检）
  for (let i = 1; i < nodes.length; i++) {
    const s = (nodes[i][1] - nodes[i - 1][1]) / (nodes[i][0] - nodes[i - 1][0])
    if (!(s > 0.2 && s < 5)) {
      throw new Error(`纵向对齐段斜率异常 s=${s.toFixed(3)}（站点/地标错位？）`)
    }
  }
  return {
    nodes,
    mapY: (y: number) => evalNodes(nodes, y),
    unmapY: (y: number) => {
      // 逆映射：顶上斜率 1.0 段可直接反解；下方二分（严格单调）
      const n = nodes.length
      if (y >= nodes[n - 1][1]) return nodes[n - 1][0] + (y - nodes[n - 1][1])
      let lo = nodes[0][0] - 20, hi = nodes[n - 1][0]
      for (let k = 0; k < 60; k++) {
        const mid = (lo + hi) / 2
        if (evalNodes(nodes, mid) < y) lo = mid
        else hi = mid
      }
      return (lo + hi) / 2
    },
    groundY: evalNodes(nodes, 0),
  }
}

// 位置数组施加纵向变换（x/z 不动；返回新数组）
export function applyVertical(
  pos: Float32Array, al: VerticalAlign,
): Float32Array {
  const out = pos.slice()
  for (let i = 1; i < out.length; i += 3) out[i] = al.mapY(out[i])
  return out
}
