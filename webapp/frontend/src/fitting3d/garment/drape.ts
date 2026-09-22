// 引力下垂解算（2026-09-15 重建二期「下垂要符合地球引力」；2026-09-16
// 五期前身自由垂；同日六期「拉直」整圈钉直挂；2026-09-17 八期整裤缝合
// 现行）：主线程轻量 verlet——距离/弯曲约束（mesh.ts 的 dist/bend 数组）
// + **全族缝合对**（seams.ts buildSeamSet：前中 rise/后中 cb 镜像族 +
// 侧缝/内缝跨宿主弧长族 + 四裆尖 tip 补焊，全 rest=0 同一求解）+ 腰口
// 整圈全向钉直挂（四 part 360° 腰圆支点）+ **撑型芯径向碰撞（八期开）**
// + 地面碰撞（y≥0 推回 + 摩擦，安全网）。
// 八期口径（用户拍板）：①整裤包腿必须有碰撞体（2026-09-14 教训的正名
// ——无碰撞裤腿对折塌陷、两腿布面互穿），芯锚纸样围度与人台无关（独立
// 原则），布面碰撞壳 = 场 + CORE_SKIN 恰落纸样围度；②本期不含腰头，
// 腰圆由整圈钉挂撑形、sideHold 刚度带暂代腰头撑圆；③摆位先行——
// buildFullPair 让全部缝对初始间隙 ≈0（或 15cm 内缝常量温和闭拢），
// 动力学只做小松弛，不用旧链 preRelax 收拢战争。collide 场查询按
// sim.yLift 回纸样空间（摆位侧场查询用纸样 y，两处一致）。
// 形态沿革：二~五期 Y-only 腰口自由垂下「布塌成对折门帘」曾是预期
// 形态，2026-09-16 用户报障「前中和后中往里折、要拉直」后由整圈全向钉
// （三轮，见 buildDrape 头注）取代——中缝保持在前中/后中竖直、顶缘按
// 摆位弧全撑。五期「自由垂不用芯碰撞」是单筒口径，随八期整裤退役。
import type { Garment } from './assemble'
import { CORE_SKIN } from './core'
import type { BodyField } from './placement'
import { pointInRings, nearestRingBoundary, topSupportY } from './placement'
import { DRAPE_PRIOR, HANG_PRIOR } from './priors'
import { buildSeamSet, type SeamGroup } from './seams'
import { bandBottomChain } from './band'

export interface DrapeSim {
  pos: Float32Array       // 全粒子当前位置（解算本体；garment.pos 是初摆位）
  prev: Float32Array      // 上一子步位置（verlet）
  vel: Float32Array
  pinIdx: Uint32Array     // 腰口整圈粒子（top_chain 边全量 + 终点角，六期直挂口径）
  pinTarget: Float32Array // 3×pin 目标位（初始摆位处，全向硬钉 = 悬挂支点）
  pinFlag: Uint8Array     // 顶点级钉查询表（0/1）：strain limiting 逆质量 0 +
                          // collide 豁免共用——钉 = 刚性腰口边界条件（2026-09-19）
  seamIdx: Uint32Array    // 2S 全族缝合对（八期 buildSeamSet：rise/cb 镜像
                          // + side/inseam 弧长 + tip 补焊，全 rest=0 同一求解）
  seamGroups: SeamGroup[] // 分族切片（金标分族统计用）
  yLift: number           // 摆位整体抬升（collide 场查询按此回纸样空间）
  holdIdx: Uint32Array    // 裆尖短时硬钉粒子（crotchHold>0 fallback 旋钮用）
  holdTarget: Float32Array
  parts: { offset: number; mesh: Garment['parts'][number]['mesh'] }[]
  field: BodyField | null   // null = 自由垂（无撑型芯径向碰撞，仅地面）
  collideAboveY: number    // 碰撞生效的纸样 y 下限（-∞ = 全程；混合形态：
                            // 躯干段撑开、腿段自由垂——(九) 山脊修复）
  maxFrames: number        // 帧数封顶（per-sim：穿台 settle 控制器 wake 时
                            // 续预算用；缺省同 DRAPE_PRIOR.maxFrames）
  stepCount: number
  settledFrames: number
  settled: boolean
  capped: boolean         // maxFrames 封顶出的 settled（非真静止）
  frozen: boolean         // 发散兜底冻结（显示保终态）
  avgSpeed: number
  failStreak: number
  lastGood: Float32Array
}

// 悬挂支点 = 腰口整圈**全向钉**（2026-09-16 六期「拉直」口径：真实
// 「提着整个腰口」——顶缘按摆位弧撑住、布条自顶缘竖直垂下，中缝不再
// 塌向轴心），无例外。演进（三轮）：
// 一轮（2026-09-15 顶部折角）全向钉把腰口锁成刚性折线——角点急坠
// （侧角 −2.1cm）补钉后顶缘仍是「图案角 + 侧缘陡落」的尖状凸起（用户
// 截图复验仍在）、前中角被锁在均匀映射偏心位（实测 −3.9cm ≈ 17°）与
// 前中缝合拔河出顶中缺口；二轮改 Y-only + 双角锚（单锚实测不收敛：锚
// 不住环向滑移模态）——布自重圆化顶缘、前中缝把顶缘滑到正中闭合，但
// **环向可滑 = 布自重把整圈腰口滑向轴心**：中缝跟着荡离前中/后中（前
// 中缝外伸 16.6→5.7cm）、整幅布塌成对折门帘（2026-09-16 用户报障
// 「前中和后中往里折、要拉直」）；三轮（现行）= 整圈全向钉：摆位侧经
// assemble 腰口弧长重参数化中缝腰角精确落中面（L/R 镜像重合）——一轮
// 拔河的根源是映射偏心而非钉本身，重参数化后「钉与缝同意」按构造成立
// （无需二轮的角点例外，实测缝对 avg/p95 = 0），顶缘全撑 = 直挂。
// 角点口径（边界环重采样：每边含起点采样、不含终点，共享角点
// = 下一条边的首采样）：终点角须并入钉集（不钉则急坠）。
// 前中缝合对 = rise 链（前裆弯，腰口端→裆点）L/R 同号顶点配对——真裤
// 前中缝只到裆点（inseam 是前后片缝，留给后续加后片），fly 连裁款 rise
// 链缺失则跳过缝合（前中敞口属连裁门襟固有形态）；后身（2026-09-16
// 六期）同款 = cb 链（后浪，裆尖→腰口，育克拼入时经 panel.ts 聚合贯通
// 到腰）L/R 同号配对
export function buildDrape(
  garment: Garment, field: BodyField | null, yLift = 0,
  collideAboveY = -Infinity, maxFrames = DRAPE_PRIOR.maxFrames,
): DrapeSim {
  const pinIdx: number[] = []
  // 腰头在（九期）：**腰口区全钉**——身片腰口环整圈（「腰部圆形撑开」
  // 全义）+ 带顶/带底两缘（带 = 两缘被持的真实布，中间布自由）；
  // sideHold 退役（带即腰头）。演进：先试只钉带顶（真实「提着腰头上
  // 沿」）——自由垂挂对折趋势把前中/后中往里拖 1.2cm，腰头内倾+布面
  // 内折 = 前后中透光楔形洞（用户报障）；再试加钉带底——缝对与身片
  // 网格 GS 冲突平衡留 ~0.5cm 均匀缝口；全钉后两侧钉位本就重合、缝恒 0。
  // 无腰头 = 旧口径：身片腰口整圈钉 + sideHold 带
  const bandPart = garment.parts.find((p) => p.key === 'waistband')
  for (const part of garment.parts) {
    stampStiffBands(part)
    // 有腰头（九期）：身片腰口环照旧整圈钉（「腰部圆形撑开」的全义
    // ——整个腰口区保持圆；早期只钉带顶时自由垂挂的对折趋势把前中/
    // 后中往里拖 1.2cm、只加钉带底时缝对与身片网格 GS 冲突平衡留
    // ~0.5cm 均匀缝口——两侧钉位本就重合，全钉后缝恒 0）+ 带顶带底
    // 两缘钉（带 = 两缘被持的真实布，中间布自由）；sideHold 退役（带
    // 即腰头）。无腰头 = 旧口径
    const isBand = part === bandPart
    if (isBand) {
      const top = part.mesh.runs.find((r) => r.name === 'top')
      if (top) {
        for (const i of top.indices) pinIdx.push(part.offset + i)
        const loopLen = part.mesh.loop.length
        const last = top.indices[top.indices.length - 1]
        const nextNb = (last + 1) % loopLen
        if (!top.indices.includes(nextNb)) pinIdx.push(part.offset + nextNb)
      }
      const chain = bandBottomChain(part.mesh)
      if (chain) {
        for (const i of chain.indices) {
          if (!pinIdx.includes(part.offset + i)) {
            pinIdx.push(part.offset + i)
          }
        }
      }
      continue
    }
    const top = part.mesh.runs.find((r) => r.role === 'top_chain')
    if (!top) {
      // seam 模式（有省育克升格参与片）：纯 back part 的 top 边 role
      // ='seam'（引擎 role_override，机头下口线 = 缝合边语义）无
      // top_chain——腰口钉挂由 yoke part 的 top' 顶替，此处放行跳过
      //（sideHold 刚度带同跳：back part 侧缝顶不邻腰口，由 yokeWeld/
      // side 缝对连接）
      if (garment.parts.some((p) => p.key === 'back_yoke')) continue
      throw new Error('裁片缺 top_chain（腰口）边——下垂 pin 无支点')
    }
    const loopLen = part.mesh.loop.length
    const last = top.indices[top.indices.length - 1]
    // 整圈全向钉（六期直挂）：前提 = buildFullPair 腰口弧长重参数化把
    // 中缝腰角精确摆在镜像位（L/R 重合在中面）——钉与缝天然同意，无需
    // 旧二轮的角点例外；实测缝对 avg/p95 = 0
    for (const i of top.indices) pinIdx.push(part.offset + i)
    // 终点角（下一条边首采样）：全向锚（防侧角急坠，实测 −2.1cm）
    const nextNb = (last + 1) % loopLen
    if (!top.indices.includes(nextNb)) pinIdx.push(part.offset + nextNb)
    // 侧缝边顶部刚度带（无腰头旧口径；有腰头时带即腰头、跳过）：无侧缝
    // 缝合的自由半身筒，侧缝自由边在自由垂中向筒轴心内摆（后身实测最深
    // ~25°）、顶部扇区塌角。顶部 sideHold cm 全向钉 = 腰头缝合线的刚度带
    // （真实成衣此区由腰头撑圆），配 assemble 侧缝边语义摆位（θ=±90°
    // 竖直）后顶部圆弧保持、带缘出口偏差实测 ≤0.7°（往下自由内摆渐增属
    // 自然垂）。run 首采样 = 腰口终点角（已在上方钉集）须去重；后宿主
    // 育克侧段与后片侧缝同为 side 名（可能各自成 run），全部覆盖
    for (const side of bandPart ? [] : part.mesh.runs) {
      if (side.name !== 'side') continue
      for (let k = 0; k < side.indices.length
        && side.arc[k] <= HANG_PRIOR.sideHold; k++) {
        const gi = part.offset + side.indices[k]
        if (!pinIdx.includes(gi)) pinIdx.push(gi)
      }
    }
  }
  const pinTarget = new Float32Array(3 * pinIdx.length)
  for (let k = 0; k < pinIdx.length; k++) {
    pinTarget[3 * k] = garment.pos[3 * pinIdx[k]]
    pinTarget[3 * k + 1] = garment.pos[3 * pinIdx[k] + 1]
    pinTarget[3 * k + 2] = garment.pos[3 * pinIdx[k] + 2]
  }
  // 顶点级钉查询表：strain limiting（钉逆质量 0）与 collide（钉豁免）共用
  const pinFlag = new Uint8Array(garment.pos.length / 3)
  for (const gi of pinIdx) pinFlag[gi] = 1
  // 全族缝合对（八期 buildSeamSet）：六期「parts[0] 单一 rise|cb 链同号
  // 配对」的泛化——rise/cb 镜像族同机制、side/inseam 跨宿主弧长配对、
  // 四裆尖 tip 补焊，全族 rest=0 进同一扁平数组（求解循环零改动）
  const seam = buildSeamSet(garment)
  // 裆尖短时硬钉（crotchHold fallback 旋钮，默认 0 关；先例旧链 60 硬
  // 释放）：tipL/tipR 两对共四顶点钉初始位 crotchHold 帧后硬释放交还缝合
  const holdIdx: number[] = []
  if (DRAPE_PRIOR.crotchHold > 0) {
    for (const g of seam.groups) {
      if (g.name !== 'tipL' && g.name !== 'tipR') continue
      for (let p = 0; p < g.pairCount; p++) {
        holdIdx.push(seam.pairs[2 * (g.pairOffset + p)],
          seam.pairs[2 * (g.pairOffset + p) + 1])
      }
    }
  }
  const holdTarget = new Float32Array(3 * holdIdx.length)
  for (let k = 0; k < holdIdx.length; k++) {
    holdTarget[3 * k] = garment.pos[3 * holdIdx[k]]
    holdTarget[3 * k + 1] = garment.pos[3 * holdIdx[k] + 1]
    holdTarget[3 * k + 2] = garment.pos[3 * holdIdx[k] + 2]
  }
  const pos = new Float32Array(garment.pos)
  // 穿台初始支撑面钳位（2026-09-20 长裤盖脚收口）：脚踝以下筒摆位半径
  // 钳踝值，而脚全长前伸远超筒径（zhitong 实测趾尖距腿轴 19.3 vs 筒 6.7，
  // 脚底切片周长 75~86 vs 脚口环 37.5）——第 0 帧脚就穿布；且 hem 随摆位
  // 落地面后被不可能的环抱锁进「侧喷摊地」盆地，坡面支撑救不了运输（无
  // 向前+向上的驱动）。解法 = 初始态直接落进正确 drape 盆地：全部低于
  // 上表面支撑壳的粒子一遍抬到 topSupportY 接触壳——脚区布搭在脚背/趾盒
  // 上起步（真实长裤脚口本就搭在脚上：站姿平脚不可能穿过更紧的脚口环），
  // 动力学只做局部松弛；field=null 自由垂零改动
  if (field) {
    for (let i3 = 0; i3 < pos.length; i3 += 3) {
      if (pinFlag[i3 / 3]) continue
      const patY = pos[i3 + 1] - yLift
      const supY = topSupportY(field, pos[i3], pos[i3 + 2], patY)
      if (supY !== null) {
        const wy = supY + yLift
        if (pos[i3 + 1] < wy) pos[i3 + 1] = wy
      }
    }
  }
  return {
    pos,
    prev: new Float32Array(pos),
    vel: new Float32Array(pos.length),
    pinIdx: new Uint32Array(pinIdx),
    pinTarget,
    pinFlag,
    seamIdx: seam.pairs,
    seamGroups: seam.groups,
    yLift,
    holdIdx: new Uint32Array(holdIdx),
    holdTarget,
    parts: garment.parts.map((p) => ({ offset: p.offset, mesh: p.mesh })),
    field,
    collideAboveY,
    maxFrames,
    stepCount: 0, settledFrames: 0, settled: false, capped: false,
    frozen: false, avgSpeed: 0, failStreak: 0,
    lastGood: new Float32Array(pos),
  }
}

function projectPins(sim: DrapeSim): void {
  const { pos, pinIdx, pinTarget } = sim
  for (let k = 0; k < pinIdx.length; k++) {
    const i3 = 3 * pinIdx[k]
    pos[i3] = pinTarget[3 * k]
    pos[i3 + 1] = pinTarget[3 * k + 1]
    pos[i3 + 2] = pinTarget[3 * k + 2]
  }
}

// 局部刚度带覆写 bendKArr（三窗）：缝口摊平窗 + 腰臀过渡带（2026-09-17
// （八）缝口刀锋卷边、（九）腰臀段山脊——两窗共用 seamFlattenStiffness）
// + 脚口环带（2026-09-19（二）前缘脱扣修复，hemBandStiffness——真实
// 牛仔裤脚口是双折卷边+车缝硬圈，抗剪切压折，环口保持圆形，穿台掉裆
// 加深时前缘不滑过脚背冠）。
// 自由垂挂前后片近乎平行贴合，侧缝/内缝 = 180° 对折的刀锋卷边——
// 距 side/inseam 链纸样距离 < seamFlattenSpan 的弯曲约束，刚度升到
// seamFlattenStiffness，折痕摊开成缓坡（「向两边拉直」的物理实现：
// 全局 bend 0.45 实测无效——重力压平镜头截面缝尖不动，必须局部作用
// 在折边上）。stamp 一次幂等（bendKArr 已在则跳过）
function stampStiffBands(
  part: { mesh: Garment['parts'][number]['mesh'] },
): void {
  const mesh = part.mesh
  if (mesh.bendKArr || mesh.bend.length === 0) return
  const seamRuns = mesh.runs.filter(
    (r) => r.name === 'side' || r.name === 'inseam')
  const hemRuns = mesh.runs.filter((r) => r.name === 'hem')
  if (seamRuns.length === 0 && hemRuns.length === 0) return
  const span = DRAPE_PRIOR.seamFlattenSpan
  // 缝链 2D 点集（预抽，逐约束中点查最近距）
  const pts: number[] = []
  for (const run of seamRuns) {
    for (const i of run.indices) {
      pts.push(mesh.xy[2 * i], mesh.xy[2 * i + 1])
    }
  }
  const nearSeam = (x: number, y: number): boolean => {
    for (let k = 0; k < pts.length; k += 2) {
      if (Math.hypot(pts[k] - x, pts[k + 1] - y) < span) return true
    }
    return false
  }
  // 脚口环带（（二）修复）：hem 链 hemBandSpan 内弯曲约束刚度升到
  // hemBandStiffness——优先于缝口窗判（重叠区两者同值 0.5，语义上
  // hem 带更具体）。窗口地图见 priors.hemBandStiffness 注释
  const hemSpan = DRAPE_PRIOR.hemBandSpan
  const hemPts: number[] = []
  for (const run of hemRuns) {
    for (const i of run.indices) {
      hemPts.push(mesh.xy[2 * i], mesh.xy[2 * i + 1])
    }
  }
  const nearHem = (x: number, y: number): boolean => {
    for (let k = 0; k < hemPts.length; k += 2) {
      if (Math.hypot(hemPts[k] - x, hemPts[k + 1] - y) < hemSpan) return true
    }
    return false
  }
  // 腰臀过渡带（（九）山脊修复）：腰缝以下 waistTransitionSpan 内提刚度
  // ——钉圆的腰口往下布塌得太快（后片腰下即塌平的 D 形不对称），折角
  // 挤在缝口成脊；过渡带让截面缓慢张开。腰缝 y = top_chain 最高采样
  const top = mesh.runs.find((r) => r.role === 'top_chain')
  let topY = -Infinity
  if (top) {
    for (const i of top.indices) {
      topY = Math.max(topY, mesh.xy[2 * i + 1])
    }
  }
  const transSpan = DRAPE_PRIOR.waistTransitionSpan
  const inTransition = (y: number): boolean =>
    topY > -Infinity && y >= topY - transSpan
  const arr = new Float32Array(mesh.bend.length / 3)
  arr.fill(DRAPE_PRIOR.bendStiffness)
  for (let c = 0; c < mesh.bend.length; c += 3) {
    const i = mesh.bend[c], j = mesh.bend[c + 1]
    const mx = (mesh.xy[2 * i] + mesh.xy[2 * j]) / 2
    const my = (mesh.xy[2 * i + 1] + mesh.xy[2 * j + 1]) / 2
    if (nearHem(mx, my)) {
      arr[c / 3] = DRAPE_PRIOR.hemBandStiffness
    } else if (nearSeam(mx, my) || inTransition(my)) {
      arr[c / 3] = DRAPE_PRIOR.seamFlattenStiffness
    }
  }
  mesh.bendKArr = arr
}

// 裆尖短时硬钉投影（crotchHold fallback 旋钮，默认 0 不投影）
function projectHold(sim: DrapeSim): void {
  const { pos, holdIdx, holdTarget } = sim
  for (let k = 0; k < holdIdx.length; k++) {
    const i3 = 3 * holdIdx[k]
    pos[i3] = holdTarget[3 * k]
    pos[i3 + 1] = holdTarget[3 * k + 1]
    pos[i3 + 2] = holdTarget[3 * k + 2]
  }
}

// 撑型芯截面碰撞（八期）：y'（pos.y − yLift 回纸样空间）行的截面环内
// 或皮肤壳内（到最近边界 < skin）→ 推到最近边界 + skin·外法线；接触
// 时 prev 向 pos 混合摩擦（无摩擦 = 芯面周向滑转不锚，旧链 0.5 地板
// ~9 永不收敛）。截面多边形口径取代旧径向推——两腿分离芯的腿间空隙
// 径向场表示不了（星形实心），只有截面/表面碰撞能留白（旧链 BVH 同因）；
// 腿管间隙按环独立判内，无 v1「双管交叠符号判陷阱」
// （2026-09-20）上表面竖直支撑前置：水平推出只作用于水平面内，向下
// 变宽的坡面（脚背等）撑不住布——先 topSupportY 判上表面域（g≥
// topSupportSlope，阈 0.6 盖住趾盒冠 g≈0.8）抬到坡面接触壳，墙面/陡坡
// 路径零改动
function collide(sim: DrapeSim): void {
  const { pos, prev, field, pinFlag } = sim
  if (!field) return
  const fr = DRAPE_PRIOR.friction
  for (let i3 = 0; i3 < pos.length; i3 += 3) {
    // 钉豁免（2026-09-19）：钉 = 刚性腰口边界条件，人台不顶开腰环——
    // 穿台审计实测 collide 在 projectPins 之后覆写嵌体钉（漂移 max 1.57，
    // 腰环 81.68 vs 成衣 77.83）。穿不进（钉环缩进截面内）由热力图 gap
    // 带符号红区读出，不靠静默顶开（偏小是读数不是错误）
    if (pinFlag[i3 / 3]) continue
    const x = pos[i3], z = pos[i3 + 2]
    const patY = pos[i3 + 1] - sim.yLift
    if (patY < sim.collideAboveY) continue   // 腿段自由垂（混合形态）
    // 上表面竖直支撑（2026-09-20 长裤盖脚）：水平推出撑不住「向下变宽」
    // 的坡面（脚背/脚尖/脚跟、大腿上侧）——外法线朝上、推出却在水平面内，
    // 布粒被侧向射出再下坠 = 沿坡滑到底，长裤脚口盖不住脚。先判上表面域
    // （placement.topSupportY：坡 g≥topSupportSlope 才接管），抬到行间
    // 交叉插值面 + skin·法线竖直分量；上表面域跳过水平推出（会把盖在坡上
    // 的布射飞）
    const supY = topSupportY(field, x, z, patY)
    if (supY !== null) {
      const wy = supY + sim.yLift
      if (pos[i3 + 1] < wy) {
        pos[i3 + 1] = wy
        prev[i3] += (pos[i3] - prev[i3]) * fr
        prev[i3 + 1] += (pos[i3 + 1] - prev[i3 + 1]) * fr
        prev[i3 + 2] += (pos[i3 + 2] - prev[i3 + 2]) * fr
      }
      continue
    }
    const rings = field.loopsAt(patY)
    if (rings.length === 0) continue
    // 最近边界（跨全部环，quick reject 余量 = skin；2026-09-18 扫描体
    // 提取为 placement.nearestRingBoundary，与穿台裆探针共口径，迭代序
    // 不变）
    const hit = nearestRingBoundary(rings, x, z, CORE_SKIN)
    if (!hit) continue
    if (hit.d >= CORE_SKIN) {
      // 远离边界：只在某环包围圆内（可能深穿）才做射线判内兜底——正常
      // 挂相布在壳外起步，此分支零命中（v1 细龙骨穿膛教训的守门）
      let maybe = false
      for (const ring of rings) {
        const dxc = x - ring.cx, dzc = z - ring.cz
        if (dxc * dxc + dzc * dzc < ring.r * ring.r) { maybe = true; break }
      }
      if (!maybe || !pointInRings(x, z, rings)) continue
    }
    // 统一推出目标 = 最近边界 + skin·外法线：边界外侧近壳粒子与环内
    // 粒子同向处理（内侧粒子若按「边界->粒子」方向推会越推越深自陷）
    const tx = hit.px + hit.nx * CORE_SKIN
    const tz = hit.pz + hit.nz * CORE_SKIN
    pos[i3] = tx
    pos[i3 + 2] = tz
    prev[i3] += (pos[i3] - prev[i3]) * fr
    prev[i3 + 1] += (pos[i3 + 1] - prev[i3 + 1]) * fr
    prev[i3 + 2] += (pos[i3 + 2] - prev[i3 + 2]) * fr
  }
}

// 地面碰撞（hangLift 抬升后的安全网）：y < 0 推回地面；法向速度清零
// （prev.y 同钉）+ 切向摩擦（prev xz 向 pos 混合——无摩擦布在地上持续
// 滑转不锚）。抬升前布全长超挂高、下摆拖地铺地曾是主约束（front 102/
// back 202 粒子贴地实测），抬 12 后正常挂相零接触
function collideGround(sim: DrapeSim): void {
  const { pos, prev } = sim
  const fr = DRAPE_PRIOR.friction
  for (let i3 = 0; i3 < pos.length; i3 += 3) {
    if (pos[i3 + 1] < 0) {
      pos[i3 + 1] = 0
      prev[i3 + 1] = 0
      prev[i3] += (pos[i3] - prev[i3]) * fr
      prev[i3 + 2] += (pos[i3 + 2] - prev[i3 + 2]) * fr
    }
  }
}

// 应变限幅（strain limiting，2026-09-19 用户口径「牛仔裤布料很厚实、不会
// 这么被拉伸」）：穿台审计实测 PBD 平衡态残余拉伸 mean 4.3%/p95 16%（续跑
// 2400 帧一分不退、旁挂 hangLift 12 即为藏它而设）全是数值假象——dist 约束
// rest=纸样净长，模型本义就是不可伸长的布。每子步末（collide 之后）一遍
// Gauss-Seidel 硬投影：边长 > rest×(1+ε) 才动，把拉伸钳回丹宁无弹量级。
// ①只限拉不限压——压缩=褶皱=真布自由度（弯腰头省口吃势呈轻褶属缝前真实
// 语义，摊成应变读数才是错的）；②钉点逆质量 0——腰口钉是刚性边界条件，
// 邻点向钉靠拢、钉不动（配 collide 钉豁免，环长恒=成衣腰长）；
// ③缝对/弯曲约束不参与——前者 rest=0 本就是约束，后者管折痕不管拉伸
function strainLimit(sim: DrapeSim): void {
  const lim = 1 + DRAPE_PRIOR.strainLimit
  const { pos, pinFlag } = sim
  for (const part of sim.parts) {
    const { dist } = part.mesh
    const off = part.offset
    for (let c = 0; c < dist.length; c += 3) {
      const ia = off + dist[c], ib = off + dist[c + 1]
      const a = 3 * ia, b = 3 * ib
      const dx = pos[b] - pos[a], dy = pos[b + 1] - pos[a + 1]
      const dz = pos[b + 2] - pos[a + 2]
      const d = Math.hypot(dx, dy, dz)
      if (d < 1e-9 || d <= dist[c + 2] * lim) continue
      const fa = pinFlag[ia] ? 0 : 1
      const fb = pinFlag[ib] ? 0 : 1
      const w = fa + fb
      if (w === 0) continue               // 钉-钉边（腰环上）：环几何即真值
      const k = ((d - dist[c + 2] * lim) / d) / w
      pos[a] += dx * k * fa; pos[a + 1] += dy * k * fa; pos[a + 2] += dz * k * fa
      pos[b] -= dx * k * fb; pos[b + 1] -= dy * k * fb; pos[b + 2] -= dz * k * fb
    }
  }
}

// 全族缝合对一遍（rest=0、双向各移一半）——迭代内与限幅后共用：限幅只顾
// 边长会把缝合对拉开 ~0.2cm，紧跟一遍收回（钉投影随后）
function seamPass(sim: DrapeSim): void {
  const { pos, seamIdx } = sim
  for (let c = 0; c < seamIdx.length; c += 2) {
    const a = 3 * seamIdx[c], b = 3 * seamIdx[c + 1]
    const dx = pos[b] - pos[a], dy = pos[b + 1] - pos[a + 1]
    const dz = pos[b + 2] - pos[a + 2]
    const d = Math.hypot(dx, dy, dz)
    if (d < 1e-9) continue
    const k = 0.5 * DRAPE_PRIOR.seamStiffness
    pos[a] += dx * k; pos[a + 1] += dy * k; pos[a + 2] += dz * k
    pos[b] -= dx * k; pos[b + 1] -= dy * k; pos[b + 2] -= dz * k
  }
}

// 一帧（60Hz 调一次）；返回状态供停走判断
export function stepDrape(sim: DrapeSim): 'running' | 'settled' | 'frozen' {
  if (sim.settled || sim.frozen) {
    return sim.frozen ? 'frozen' : 'settled'
  }
  const p = DRAPE_PRIOR
  const dtSub = p.dt / p.substeps
  sim.lastGood.set(sim.pos)
  for (let sub = 0; sub < p.substeps; sub++) {
    const { pos, prev, vel } = sim
    for (let i3 = 0; i3 < pos.length; i3 += 3) {
      vel[i3] *= p.damping
      vel[i3 + 1] = vel[i3 + 1] * p.damping + p.gravity * dtSub
      vel[i3 + 2] *= p.damping
      prev[i3] = pos[i3]; prev[i3 + 1] = pos[i3 + 1]; prev[i3 + 2] = pos[i3 + 2]
      pos[i3] += vel[i3] * dtSub
      pos[i3 + 1] += vel[i3 + 1] * dtSub
      pos[i3 + 2] += vel[i3 + 2] * dtSub
    }
    for (let it = 0; it < p.iterations; it++) {
      for (const part of sim.parts) {
        const { dist, bend } = part.mesh
        const off = part.offset
        // 距离约束（拉伸+剪切，刚度 1）：双向各移一半
        for (let c = 0; c < dist.length; c += 3) {
          const a = 3 * (off + dist[c]), b = 3 * (off + dist[c + 1])
          const dx = pos[b] - pos[a], dy = pos[b + 1] - pos[a + 1]
          const dz = pos[b + 2] - pos[a + 2]
          const d = Math.hypot(dx, dy, dz)
          if (d < 1e-9) continue
          const k = ((d - dist[c + 2]) / d) * 0.5
          pos[a] += dx * k; pos[a + 1] += dy * k; pos[a + 2] += dz * k
          pos[b] -= dx * k; pos[b + 1] -= dy * k; pos[b + 2] -= dz * k
        }
        // 弯曲约束（内边对点；全局 0.3 / 局部刚度带三窗覆写：缝口摊平
        // + 腰臀过渡 + 脚口环带）
        const bendK = part.mesh.bendKArr
        for (let c = 0; c < bend.length; c += 3) {
          const a = 3 * (off + bend[c]), b = 3 * (off + bend[c + 1])
          const dx = pos[b] - pos[a], dy = pos[b + 1] - pos[a + 1]
          const dz = pos[b + 2] - pos[a + 2]
          const d = Math.hypot(dx, dy, dz)
          if (d < 1e-9) continue
          const k = ((d - bend[c + 2]) / d) * 0.5
            * (bendK ? bendK[c / 3] : p.bendStiffness)
          pos[a] += dx * k; pos[a + 1] += dy * k; pos[a + 2] += dz * k
          pos[b] -= dx * k; pos[b + 1] -= dy * k; pos[b + 2] -= dz * k
        }
      }
      // 全族缝合对（八期：rise/cb 镜像 + side/inseam 弧长 + tip 补焊，
      // 跨片 rest=0、刚度 1）——求解循环对全族一视同仁
      seamPass(sim)
      projectPins(sim)
      // 裆尖短时硬钉（crotchHold 帧后硬释放交还缝合约束；默认 0 关）
      if (sim.stepCount < DRAPE_PRIOR.crotchHold) projectHold(sim)
    }
    // 应变限幅收尾（约束迭代之后、碰撞之前）：单遍硬钳 + 缝对/钉回投影
    // （限幅只顾边长会把缝合对拉开 ~0.2cm，紧跟一遍收回；交替多遍实测
    // 无收益且缝口重开）。放在 collide 前给碰撞最后一句话——限幅若在
    // 碰撞后执行会把刚推出的接触点拽回体内（实测 worstPen 1.96→4.25），
    // 穿透比 <1% 接触区应变余量更不可接受
    strainLimit(sim)
    seamPass(sim)
    projectPins(sim)
    // 约束块速度泄压：限幅/缝对的硬投影位移会被 verlet 记成速度（下一
    // 子步反冲振荡，hang 模式实测永不静止 avgSpeed 悬在 ~1+）——块末把
    // prev 向 pos 轻混，只泄掉约束注入的那部分（同 collide 摩擦手法）
    for (let i = 0; i < pos.length; i++) prev[i] += (pos[i] - prev[i]) * 0.1
    collide(sim)
    collideGround(sim)
    for (let i3 = 0; i3 < pos.length; i3 += 3) {
      vel[i3] = (pos[i3] - prev[i3]) / dtSub
      vel[i3 + 1] = (pos[i3 + 1] - prev[i3 + 1]) / dtSub
      vel[i3 + 2] = (pos[i3 + 2] - prev[i3 + 2]) / dtSub
    }
  }

  // 发散检测（NaN/飞点）：恢复好帧、清速度重试，连败冻结保终态
  let bad = false
  let speedSum = 0
  const { pos, vel } = sim
  for (let i3 = 0; i3 < pos.length; i3 += 3) {
    if (!Number.isFinite(pos[i3]) || Math.abs(pos[i3 + 1]) > 1e4) {
      bad = true; break
    }
    speedSum += Math.abs(vel[i3]) + Math.abs(vel[i3 + 1]) + Math.abs(vel[i3 + 2])
  }
  if (bad) {
    sim.pos.set(sim.lastGood)
    sim.vel.fill(0)
    sim.prev.set(sim.pos)
    sim.failStreak += 1
    if (sim.failStreak >= 3) sim.frozen = true
    return sim.frozen ? 'frozen' : 'running'
  }
  sim.failStreak = 0
  sim.stepCount += 1
  sim.avgSpeed = speedSum / (sim.pos.length / 3)
  sim.settledFrames = sim.avgSpeed < p.settleSpeed
    ? sim.settledFrames + 1 : 0
  // 帧数封顶兜底：超限取当前帧出 settled（防极限环卡死显示；per-sim
  // maxFrames——穿台 settle 控制器可续预算，2026-09-18）
  if (sim.stepCount >= sim.maxFrames) {
    sim.settled = true
    sim.capped = true
  } else if (sim.settledFrames >= p.settleFrames) {
    sim.settled = true
  }
  return sim.settled ? 'settled' : 'running'
}

// 全族缝合误差统计（金标用）：全部缝合对点距 avg / P95。读 sim.pos
// 当前解算位——garment.pos 是初始摆位，别解构它
export function seamStats(sim: DrapeSim): { avg: number; p95: number } {
  const { pos, seamIdx } = sim
  const ds: number[] = []
  for (let c = 0; c < seamIdx.length; c += 2) {
    const a = 3 * seamIdx[c], b = 3 * seamIdx[c + 1]
    ds.push(Math.hypot(pos[b] - pos[a], pos[b + 1] - pos[a + 1],
      pos[b + 2] - pos[a + 2]))
  }
  if (ds.length === 0) return { avg: -1, p95: -1 }
  ds.sort((x, y) => x - y)
  const avg = ds.reduce((s, d) => s + d, 0) / ds.length
  const p95 = ds[Math.min(ds.length - 1, Math.floor(ds.length * 0.95))]
  return { avg, p95 }
}

// 分族缝合误差统计（八期金标：rise/cb/sideL/sideR/inseamL/inseamR/tip
// 各族单独 avg/P95——各族几何性质不同，阈值分开钉）
export function seamStatsByGroup(
  sim: DrapeSim,
): Record<string, { avg: number; p95: number }> {
  const out: Record<string, { avg: number; p95: number }> = {}
  for (const g of sim.seamGroups) {
    const ds: number[] = []
    for (let p = 0; p < g.pairCount; p++) {
      const a = 3 * sim.seamIdx[2 * (g.pairOffset + p)]
      const b = 3 * sim.seamIdx[2 * (g.pairOffset + p) + 1]
      ds.push(Math.hypot(sim.pos[b] - sim.pos[a],
        sim.pos[b + 1] - sim.pos[a + 1], sim.pos[b + 2] - sim.pos[a + 2]))
    }
    ds.sort((x, y) => x - y)
    out[g.name] = {
      avg: ds.reduce((s, d) => s + d, 0) / ds.length,
      p95: ds[Math.min(ds.length - 1, Math.floor(ds.length * 0.95))],
    }
  }
  return out
}
