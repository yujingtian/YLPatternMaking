// 3D 试穿纯几何/数据层单测（three 不进测试：视图层另行肉眼验收）。
// 金标风格：手工推演值 + 强断言。
//   1. 人台：腰环折线周长 == 体型腰围（±1.5% 标定公差）；radiusAt
//      轴向 == 半轴；sectionAt 端点夹取
//   1b. 人体化腿管（2026-09-10 外缘连续 emergence，旧 containment 藏头
//      已删）：拓扑三盖不共面；剪影不变量（Lipschitz 无台阶 / 最宽点≈臀
//      / 膝踝比例 / 内缘缝隙带 / 双腿 cx>0）；接合支撑金标（emergence
//      带腿接管 + 盆内零漂移锚 + 会阴被填带）
//   1d. 第四轮人体化（2026-09-10）：矢状 S 曲线（腰椎谷/臀峰/臀底褶/
//      小腹峰/腘窝/小腿肚/跟腱）、腰最窄（肋外扩 + argmin 带内）、
//      脚盒（局部系/地面/外八）、肚脐（挂前腹表面）金标
//   1c. （已迁移）tubeMesh 绕向/水密金标随 tubeMesh 删除整体迁至
//      skin.test.ts——蒙皮三角形法线·∇F>0（外向绕向）+ 无向边恰共享
//      2 次 + 闭合流形 V−E+F=2
//   2. estimateBody：成衣 − 先验松量 + 0.85 下限
//   3. 体型库：默认估计激活、预设存在、自定义增删、JSON 导入导出
//   4. 网格：三角化欧拉公式 V−E+F=1（圆盘）、边名聚合段、locate 权重和 1
//   5. 摆位：左半片 x<=0 / 右半片 x>=0（θ 约定）、前中 +Z / 后中 −Z
//   6. 碰撞：体内粒子推出到 R+skin（radiusAt 单位向量口径强断言——修复
//      前未归一化输入使判据退化为 dist ≥ R/dist，断言空转）
//   6b. 入口守卫：畸形/退化/极端围度 payload 不抛且环严格降序
//   7. PBD：全 pin 收敛 settled 且位置不动；自由落体 y 单调下降且有限
//   8. 应变：静止长 = 0、拉长 > 0；色带 红(紧)/绿(贴合)/蓝(松) 单调
import { describe, expect, it, vi } from 'vitest'
import type { FittingPiece, FittingResult } from '../types'
import { estimateBody, validateGirths } from './bodyProfile'
import {
  BODY_PRESETS, exportProfiles, findProfile, importProfiles, loadStore,
  removeCustom, upsertCustom,
} from './bodyProfileStore'
import { BODY_RATIO, FOOT_PRIOR, NAVEL_PRIOR } from './priors'
import {
  buildMannequin, radiusAt, sectionAt, superellipsePerimeter,
} from './mannequin'
import { buildClothMesh, runIndexAt } from './mesh'
import { placePoint, surfaceRadius } from './seams'
import { collideOne } from './pbd/collide'
import { createSim, stepSim } from './pbd/solver'
import type { Garment, GarmentPart } from './seams'
import { computeStrain, strainColor } from './heatmap'

// ---- 测试夹具：165/66A 系典型尺寸（与引擎金标 M 同族量级） ----
const BODY: FittingResult['body'] = {
  stations: [
    { key: 'waist', y: 98, girth_finished: 70, per: 'body' },
    { key: 'hip', y: 86, girth_finished: 96, per: 'body' },
    { key: 'crotch', y: 78, girth_finished: null, per: 'body' },
    { key: 'knee', y: 42, girth_finished: 46, per: 'leg' },
    { key: 'hem', y: 0, girth_finished: 36, per: 'leg' },
  ],
  points: {
    front_crotch_vertex: [15, 78],
    back_crotch_vertex: [30, 77.04],
  },
  crotch_drop: 0.96,
  waistband_width: 4,
  waistband_type: 'straight',
  outseam: 102,
}
const GIRTHS = { waist: 66, hip: 90, thigh: 54, knee: 35 }
// 夹具站点派生（硬编码高度值会随夹具漂移失联，最坏静默跳过断言环）
const Y_CROTCH = BODY.stations.find((s) => s.key === 'crotch')!.y
const Y_HIP = BODY.stations.find((s) => s.key === 'hip')!.y

// 矩形裁片（链序 waist->side->hem->rise 闭合，全局系）
function rectPiece(w: number, h: number): FittingPiece {
  const line = (a: [number, number], b: [number, number]) =>
    [a, b] as [number, number][]
  const len = (a: [number, number], b: [number, number]) =>
    Math.hypot(b[0] - a[0], b[1] - a[1])
  const e = (
    name: string, role: FittingPiece['edges'][number]['role'],
    a: [number, number], b: [number, number],
  ) => ({ name, kind: 'line' as const, role, pts: line(a, b), length: len(a, b) })
  return {
    key: 'front_piece', name: '前片',
    origin: [0, 0], frame: 'reflect_y',
    bbox: [0, 0, w, h],
    edges: [
      e('waist', 'top_chain', [0, h], [w, h]),
      e('side', 'seam', [w, h], [w, 0]),
      e('hem', 'hem', [w, 0], [0, 0]),
      e('rise', 'seam', [0, 0], [0, h]),
    ],
    marks: [], notches: [], grain: null,
  }
}

describe('mannequin 人台', () => {
  it('腰环折线周长标定到体型腰围（±1.5%）', () => {
    const man = buildMannequin(BODY, GIRTHS)
    const waistRing = man.pelvis.rings.find((r) => Math.abs(r.y - 98) < 1e-9)
    expect(waistRing).toBeDefined()
    const per = superellipsePerimeter(
      waistRing!.a, waistRing!.bF, waistRing!.bB, waistRing!.e)
    expect(Math.abs(per - 66) / 66).toBeLessThan(0.015)
    // 臀环同理（站点环精确采样在站点 y 上）
    const hipRing = man.pelvis.rings.find((r) => Math.abs(r.y - 86) < 1e-9)
    const hipPer = superellipsePerimeter(
      hipRing!.a, hipRing!.bF, hipRing!.bB, hipRing!.e)
    expect(Math.abs(hipPer - 90) / 90).toBeLessThan(0.015)
  })

  it('拓扑：躯干顶 = 腰+18、骨盆底 = 裆下楔底、腿顶 = 头带首环、腿底 = 脚口−8', () => {
    const man = buildMannequin(BODY, GIRTHS)
    expect(man.pelvis.rings[0].y).toBeCloseTo(98 + 18, 6)
    // 骨盆底 = 裆 − 3（五轮楔上提，穹顶止于 gap 过零锚上方），非裸裆环
    expect(man.pelvis.rings[man.pelvis.rings.length - 1].y)
      .toBeCloseTo(78 - BODY_RATIO.wedgeDropBelowCrotch, 6)
    // 五轮：上段 17（止于臀站）+ 臀下填充带 5（前瞻锚手法同楔表）+ 楔 2
    expect(man.pelvis.rings.length).toBe(24)
    // 腿顶头带：yTop = min(裆+7, 臀−2) = 84，环在 (crotch, yTop) 开区间
    // 1cm 一档（k=n 环恰在 crotch 与下段首环重合，跳过）→ 首环 83
    const yTop = Math.min(
      Y_CROTCH + BODY_RATIO.headRiseAboveCrotch,
      Y_HIP - BODY_RATIO.headTopBelowHip)
    const nHead = Math.max(2, Math.ceil(yTop - Y_CROTCH))
    expect(man.legs[0].rings[0].y)
      .toBeCloseTo(yTop - (yTop - Y_CROTCH) / nHead, 6)
    // 下段 25 环（crotch/thigh/gapFill/midGap/knee/calf/hem/ankle 八站 4cm
    // 采样，五轮b 新 gapFill 站+calf 上提各 +1）+ 头带 5 环
    expect(man.legs[0].rings.length).toBe(25 + (nHead - 1))
    expect(man.legs[0].rings[man.legs[0].rings.length - 1].y).toBeCloseTo(-8, 6)
    // 三盖不共面不变量（z-fighting 根源消除）：楔底 75 / 腿顶 83 / 腿底 −8
    expect(new Set([
      man.pelvis.rings[man.pelvis.rings.length - 1].y,
      man.legs[0].rings[0].y,
      man.legs[0].rings[man.legs[0].rings.length - 1].y,
    ]).size).toBe(3)
    // 双腿中心左右对称（逐环 cx 镜像）；ring5 = 下段首环（crotch 环）
    for (let i = 0; i < man.legs[0].rings.length; i++) {
      expect(man.legs[0].rings[i].cx)
        .toBeCloseTo(-man.legs[1].rings[i].cx, 9)
    }
    expect(man.legs[0].rings[5].y).toBeCloseTo(Y_CROTCH, 9)
  })

  it('人体形状不变量（165/66A 剪影金标，0.5cm 采样）', () => {
    const man = buildMannequin(BODY, GIRTHS)
    // 剪影采样：outer(y) = 环范围内各管 |cx|+a 最大值（门控同 collide，
    // 界外管不算——sectionAt 夹取会造 phantom 腿）
    const W_h = sectionAt(man.pelvis, Y_HIP).a
    const outerAt = (y: number): number => {
      let best = -Infinity
      for (const tube of [man.pelvis, ...man.legs]) {
        if (y > tube.rings[0].y
          || y < tube.rings[tube.rings.length - 1].y) continue
        const s = sectionAt(tube, y)
        best = Math.max(best, Math.abs(s.cx) + s.a)
      }
      return best
    }
    const innerLegAt = (y: number): number | null => {
      const s = sectionAt(man.legs[0], y)
      if (y > man.legs[0].rings[0].y
        || y < man.legs[0].rings[man.legs[0].rings.length - 1].y) return null
      return Math.abs(s.cx) - s.a
    }
    // 1) 无台阶：|Δouter|/Δy ≤ 1.05（二轮微调后实测最坏 1.016 @78.5 =
    //    头带凸坡陡段+裆环 girth 增长的真实斜率——软化坡会压低骨盆×腿穿越
    //    角、威胁 kPL 外凸预算（priors headRise 注），故阈值按实测放至
    //    1.05；阈值语义=台阶检测非斜率美学，上界仍 ≈1cm/cm。旧 0.7 阈值
    //    是 fb/bb 矢状偏置（收窄骨盆壁）前口径）
    const yFloor = man.legs[0].rings[man.legs[0].rings.length - 1].y
    let worstLip = 0
    for (let y = man.topY - 0.5; y >= yFloor; y -= 0.5) {
      const lip = Math.abs(outerAt(y) - outerAt(y + 0.5)) / 0.5
      worstLip = Math.max(worstLip, lip)
    }
    expect(worstLip).toBeLessThanOrEqual(1.05)
    // 2) 最宽点 ≈ 臀：全身 outer ≤ W_h + 0.5（实测 15.90 = 大腿带 gap 下限
    //    绑定 2a+gap，臀站 15.70——54cm 腿 × 90cm 臀的真实解剖比例）
    let maxOuter = -Infinity
    for (let y = man.topY; y >= yFloor; y -= 0.5) {
      maxOuter = Math.max(maxOuter, outerAt(y))
    }
    expect(maxOuter).toBeLessThanOrEqual(W_h + 0.5)
    expect(outerAt(Y_HIP)).toBeCloseTo(15.703, 3)
    // 3) 站点剪影锚（五轮b 实测）：腰 11.652 / 裆腿外缘 14.996（外缘目标
    //    绑定 0.955×W_h，inner −1.08）/ 膝 12.25 / 脚口
    //    11.29（X 站姿 gap 外展绑定）/ 踝 10.657
    expect(outerAt(98)).toBeCloseTo(11.652, 3)
    expect(outerAt(78)).toBeCloseTo(14.996, 3)
    expect(outerAt(42)).toBeCloseTo(12.25, 2)
    expect(outerAt(0)).toBeCloseTo(11.29, 2)
    expect(outerAt(-7)).toBeCloseTo(10.685, 2)   // 五轮c 峰下收拢站 CR 下传 +0.03
    // 4) 膝/踝外缘比例（人体比例带，W_h 归一）
    expect(outerAt(42) / W_h).toBeGreaterThan(0.72)
    expect(outerAt(42) / W_h).toBeLessThan(0.85)
    expect(outerAt(-7) / W_h).toBeGreaterThan(0.55)
    expect(outerAt(-7) / W_h).toBeLessThan(0.70)
    // 5) 小腿肚微凸：calf 站（五轮b 膝下 7→5 解剖位）外缘 > 膝外缘
    expect(outerAt(37)).toBeGreaterThan(outerAt(42))
    // 6) 内缘缝隙（五轮有意变更，决策日志 §十一）：裆下互叠带（inner<0）
    //    ≤6cm 且止于过零锚（实测零点 73.5 = 裆下 4.5cm；@72 已转正、@66
    //    缝 2×1.4=2.8 可辨——旧 10cm「接触带」微缝在 kLL 桥接与 MC 可辨
    //    阈之下视觉焊死，已废）；膝内缘 ≥ +1.1、脚口内缘 ≥ +1.0
    let band = 0
    for (let y = Y_CROTCH; y >= man.bottomY; y -= 0.5) {
      if ((innerLegAt(y) ?? 1) < 0) band += 0.5
    }
    expect(band).toBeLessThanOrEqual(6.0)
    expect(innerLegAt(Y_CROTCH)!).toBeLessThan(0)       // 裆上预支外缘预算
    expect(innerLegAt(72)!).toBeGreaterThanOrEqual(0)   // 分离点在裆下 ~5cm
    expect(innerLegAt(66)!).toBeGreaterThanOrEqual(1.3) // 中腿缝 2×1.4 稳可辨
    expect(innerLegAt(42)!).toBeGreaterThanOrEqual(1.1)
    expect(innerLegAt(0)!).toBeGreaterThanOrEqual(1.0)
    // 7) 双腿分居两侧（病理负 cx 回归守卫）：|cx| 逐环 ≥ 5（实测踝环 5.25）
    for (const leg of man.legs) {
      for (const r of leg.rings) {
        expect(Math.abs(r.cx)).toBeGreaterThanOrEqual(5)
      }
    }
    // 8) 骨盆反直筒（第四轮重述：矢状 fb/bb 偏置使 (78,86) 内 a 非单调——
    //    bB/bF 峰值带吃宽度，a 在 ~82 出浅谷；不变量退为：带内永不超臀宽
    //    + 裆环收细 ≥1.2（0.85 比直筒 0.94 的收细量）
    const aHip = sectionAt(man.pelvis, Y_HIP).a
    for (const r of man.pelvis.rings) {
      if (r.y >= Y_HIP || r.y <= Y_CROTCH) continue
      expect(r.a).toBeLessThanOrEqual(aHip + 1e-9)
    }
    expect(aHip - sectionAt(man.pelvis, Y_CROTCH).a).toBeGreaterThanOrEqual(1.2)
    // 9) 头带环贴盆：y ≥ crotch+2.5 的腿环外缘仍在盆壁内（emergence 渐出，
    //    y<crotch+2.5 段允许穿出——接管点在 crotch+2 附近）
    for (const r of man.legs[0].rings) {
      if (r.y <= Y_CROTCH + 2.5) continue
      expect(Math.abs(r.cx) + r.a)
        .toBeLessThanOrEqual(sectionAt(man.pelvis, r.y).a + 1e-9)
    }
    // 10) 盆-腿壁交接无台阶（五轮 thighTopBackBias 与 crotchBack·FrontBias
    //     对值构造；四轮前腿首锚硬编码 1.0，交接差 1.21 是臀底/小腹台阶
    //     根因）：@crotch 前后壁差 ≤0.6（实测 bB 0.253 / bF 0.501）
    expect(Math.abs(sectionAt(man.legs[0], Y_CROTCH).bB
      - sectionAt(man.pelvis, Y_CROTCH).bB)).toBeLessThanOrEqual(0.6)
    expect(Math.abs(sectionAt(man.pelvis, Y_CROTCH).bF
      - sectionAt(man.legs[0], Y_CROTCH).bF)).toBeLessThanOrEqual(0.6)
    // 11) 腰髋沟上限（五轮填充锚回归网）：outer@82 ≥ W_h−2.2（实测 14.054，
    //     谷深 1.71 ≤1.8——矢状峰锚「保围缩 a」的允许消耗带）
    expect(outerAt(82)).toBeGreaterThanOrEqual(W_h - 2.2)
  })

  it('接合支撑金标（165/66A 实测锚）', () => {
    const man = buildMannequin(BODY, GIRTHS)
    // 侧向 emergence 带 (78,80)：五轮b 填充锚下沉（hip−5）后 79 仍是盆壁
    // 主导（盆 a 14.902 > 腿 |cx|+a 14.86，五轮c 小腹降峰保围微调 −0.014）
    // ——支撑 = 骨盆半轴
    expect(surfaceRadius(man, 79, Math.PI / 2)).toBeCloseTo(14.902, 3)
    expect(surfaceRadius(man, 79, Math.PI / 2))
      .toBeCloseTo(sectionAt(man.pelvis, 79).a, 9)
    // 接管点以上零漂移锚：82 处支撑 === 骨盆半轴（头带贴盆内壁；
    // 五轮b 填充锚抬谷 14.05→15.26，五轮c 小腹降峰保围还宽 +0.10→15.36，
    // 腰髋沟上限不变量见剪影测试 11）
    expect(surfaceRadius(man, 82, Math.PI / 2))
      .toBeCloseTo(sectionAt(man.pelvis, 82).a, 9)
    expect(surfaceRadius(man, 82, Math.PI / 2)).toBeCloseTo(15.36, 2)
    // 臀站 = W_h（fb 臀站锚 1.0 -> 站点环 a 即外缘梯子 W_h 口径）
    expect(surfaceRadius(man, 86, Math.PI / 2)).toBeCloseTo(15.703, 3)
    // 会阴被填带 (75.5,78) 后中：支撑由腿 bB 决定（fixture 后浪尖 77.04
    // 落带内，布料不塌陷）
    expect(surfaceRadius(man, 76, Math.PI)).toBeCloseTo(9.627, 3)
    // 楔底(75)低于腿撑：74 处支撑仍由腿管决定（带外零漂移锚）
    expect(surfaceRadius(man, 74, Math.PI))
      .toBeCloseTo(sectionAt(man.legs[0], 74).bB, 9)
    expect(sectionAt(man.legs[0], 74).bB).toBeCloseTo(9.07, 2)
  })

  it('第四轮人体化金标：矢状 S / 腰最窄 / 腿节奏 / 脚 / 脐', () => {
    const man = buildMannequin(BODY, GIRTHS)
    const Y_WAIST = 98, Y_RIB = 98 + BODY_RATIO.ribRiseAboveWaist
    // ---- 骨盆矢状 S（bB 后半深）：腰 → 腰椎谷 → 臀站 → 臀峰 → 臀底褶 ----
    const bB = (y: number) => sectionAt(man.pelvis, y).bB
    const bF = (y: number) => sectionAt(man.pelvis, y).bF
    let vY = 0, vV = Infinity, pY = 0, pV = -Infinity, fY = 0, fV = -Infinity
    for (let y = Y_HIP; y <= Y_WAIST; y += 0.25) {
      if (bB(y) < vV) { vV = bB(y); vY = y }
    }
    for (let y = Y_CROTCH; y <= Y_HIP; y += 0.25) {
      if (bB(y) > pV) { pV = bB(y); pY = y }
      if (bF(y) > fV) { fV = bF(y); fY = y }
    }
    // 腰椎谷：(hip, waist) 带内、深度 ≤ 0.98×腰（五轮「自然圆润」重校
    // lumbarBias 0.67→0.77，实测 8.298@94 = 0.950 浅谷——四轮逐轮加深史
    // 0.73→0.70→0.67 见决策日志，用户否决深谷）
    expect(vY).toBeGreaterThan(Y_HIP)
    expect(vY).toBeLessThan(Y_WAIST)
    expect(vV / bB(Y_WAIST)).toBeLessThan(0.98)
    // 臀峰：(crotch, hip) 带内偏下（真人臀峰在臀线下 ~4.5cm）、
    // > 1.01×臀站（五轮实测 13.777@83 = 1.044——glute 1.42→1.30 自然
    // 圆润窗口 1.02-1.04 上沿）；臀底褶：裆处 ≤ 0.72×峰（实测 0.682）
    expect(pY).toBeGreaterThan(Y_CROTCH + 1)
    expect(pY).toBeLessThan(Y_HIP)
    expect(pV / bB(Y_HIP)).toBeGreaterThan(1.01)
    expect(bB(Y_CROTCH) / pV).toBeLessThan(0.72)
    // 小腹峰：frontBias 臀站锚 1.0 后 bF@86 不被小腹凸吃宽度——
    // (crotch, hip) 带内 bF 局部峰 > bF@86 + 0.3（五轮实测 12.668@83
    // vs 11.777；belly 1.28 单锚尖峰已降 1.18 宽缓微凸）
    expect(fY).toBeGreaterThan(Y_CROTCH + 1)
    expect(fY).toBeLessThan(Y_HIP)
    expect(fV).toBeGreaterThan(bF(Y_HIP) + 0.3)
    // ---- 腿矢状节奏：腘窝谷 → 小腿肚峰 → 跟腱收 ----
    const lb = (y: number) => sectionAt(man.legs[0], y).bB
    expect(lb(42)).toBeLessThan(lb(44))       // 膝站腘窝局部极小
    expect(lb(42)).toBeLessThan(lb(40))
    // 腘窝可见深度：膝上 2cm 处后壁高出谷 ≥0.2cm（五轮环缢减半 rim 1.00→
    // 0.97 / 谷 0.80→0.86 后实测 0.246；四轮推深态 0.471 见决策日志——
    // 删任一锚 dip 回落 ~0.1 即红，VLM「腘窝不可辨」回归守卫）
    expect(lb(44) - lb(42)).toBeGreaterThanOrEqual(0.2)
    expect(lb(37)).toBeGreaterThan(lb(38))    // 小腿肚站局部极大（五轮b
    expect(lb(37)).toBeGreaterThan(lb(35))    // 站膝下 7→5 解剖位，VLM 复验
                                              // 旧 7cm 站肌腹视觉重心过低+尖峰）
    expect(lb(35)).toBeGreaterThan(lb(32))
    expect(lb(-7) / lb(37)).toBeLessThan(0.65)   // 跟腱收（实测 ~0.60）
    // ---- 腰最窄（肋外扩锚后腰 = 下躯干全局最窄）----
    let aY = 0, aV = Infinity
    for (let y = Y_HIP; y <= Y_RIB; y += 0.25) {
      const a = sectionAt(man.pelvis, y).a
      if (a < aV) { aV = a; aY = y }
    }
    expect(aY).toBeGreaterThan(Y_WAIST - 2)   // argmin ∈ (waist−2, waist+2)
    expect(aY).toBeLessThan(Y_WAIST + 2)
    expect(sectionAt(man.pelvis, Y_RIB).a)
      .toBeGreaterThan(sectionAt(man.pelvis, Y_WAIST).a)   // 肋外扩 > 腰
    // ---- 脚：踝局部系圆角盒、落地地面、微外八 ----
    const yAnkle = man.legs[1].rings[man.legs[1].rings.length - 1].y
    expect(man.bottomY).toBe(FOOT_PRIOR.groundY)
    for (const [i, f] of man.feet.entries()) {
      const sgn = i === 0 ? -1 : 1
      expect(f.origin[0]).toBeCloseTo(
        sgn * Math.abs(man.legs[i].rings[man.legs[i].rings.length - 1].cx), 9)
      expect(f.origin[1]).toBeCloseTo(yAnkle, 9)
      expect(f.origin[2]).toBeCloseTo(0, 9)
      expect(f.yaw).toBeCloseTo(sgn * FOOT_PRIOR.toeOutDeg * Math.PI / 180, 9)
      // 局部系盒：世界底 = groundY（+round 圆角触地）、顶 ≈ 踝下 0.6、
      // z 跨 [−heelBehind, totalLength−heelBehind]
      for (const b of f.boxes) {
        expect(b.c[1] - b.h[1] - f.round + yAnkle)
          .toBeCloseTo(FOOT_PRIOR.groundY, 6)
        expect(b.c[1] + b.h[1] + f.round).toBeLessThan(0)
        expect(b.c[2] - b.h[2] - f.round)
          .toBeGreaterThanOrEqual(-FOOT_PRIOR.heelBehind - 1e-9)
        expect(b.c[2] + b.h[2] + f.round)
          .toBeLessThanOrEqual(FOOT_PRIOR.totalLength - FOOT_PRIOR.heelBehind + 1e-9)
      }
    }
    // ---- 脐：腰下 4.5、挂前腹表面（bF 极值内移 inset）----
    expect(man.navel.y).toBeCloseTo(Y_WAIST - NAVEL_PRIOR.dropBelowWaist, 9)
    expect(man.navel.z).toBeCloseTo(
      sectionAt(man.pelvis, man.navel.y).bF - NAVEL_PRIOR.inset, 9)
  })

  it('radiusAt 轴向收敛到半轴；sectionAt 端点夹取', () => {
    const man = buildMannequin(BODY, GIRTHS)
    const s = sectionAt(man.pelvis, 98)
    expect(radiusAt(s, 1, 0)).toBeCloseTo(s.a, 3)
    expect(radiusAt(s, 0, 1)).toBeCloseTo(s.bF, 3)
    expect(radiusAt(s, 0, -1)).toBeCloseTo(s.bB, 3)
    // 骨盆 y 范围外夹取到端环（同引用值）
    expect(sectionAt(man.pelvis, 999).y).toBe(man.pelvis.rings[0].y)
    expect(sectionAt(man.pelvis, -999).y)
      .toBe(man.pelvis.rings[man.pelvis.rings.length - 1].y)
  })
})

describe('bodyProfile 体型估计', () => {
  it('成衣 − 先验松量（waist 1.5 / hip 5 / thigh 4 / knee 3）', () => {
    const b = estimateBody({ waist: 70, hip: 96, thigh: 58, knee: 46 })
    expect(b.waist).toBeCloseTo(68.5, 9)
    expect(b.hip).toBeCloseTo(91, 9)
    expect(b.thigh).toBeCloseTo(54, 9)
    expect(b.knee).toBeCloseTo(43, 9)
    expect(b.estimated).toBe(true)
  })
  it('0.85 下限：小成衣防负松量翻车', () => {
    const b = estimateBody({ waist: 1, hip: 1, knee: 1 })
    expect(b.waist).toBeCloseTo(0.85, 9)
    expect(b.thigh).toBeUndefined()
  })
  it('校验范围', () => {
    expect(validateGirths({ waist: 66, hip: 90, knee: 35 })).toBeNull()
    expect(validateGirths({ waist: 140, hip: 90, knee: 35 })).toMatch(/腰围/)
  })
})

describe('bodyProfileStore 体型库', () => {
  it('默认激活估计体型；预设含标准 165/66A', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => null, setItem: () => {}, removeItem: () => {},
    })
    const s = loadStore()
    expect(s.activeId).toBe('estimated')
    expect(BODY_PRESETS.some((p) => p.id === 'std-165-66')).toBe(true)
    vi.unstubAllGlobals()
  })
  it('自定义增删改 + 查找', () => {
    const s0 = { version: 1 as const, activeId: 'estimated', customs: [] }
    const p = { id: 'c1', name: '我的体型', waist: 64, hip: 92, knee: 34 }
    const s1 = upsertCustom(s0, p)
    expect(s1.customs).toHaveLength(1)
    expect(s1.activeId).toBe('c1')
    expect(findProfile(s1, 'c1')?.name).toBe('我的体型')
    const s2 = upsertCustom(s1, { ...p, waist: 65 })
    expect(s2.customs).toHaveLength(1)
    expect(s2.customs[0].waist).toBe(65)
    const s3 = removeCustom(s2, 'c1')
    expect(s3.customs).toHaveLength(0)
    expect(s3.activeId).toBe('estimated')
  })
  it('JSON 导出/导入回环；非法条目跳过计数', () => {
    const text = exportProfiles([
      { id: 'a', name: 'A', waist: 64, hip: 90, knee: 34 },
      { id: 'b', name: 'B', waist: 64, hip: 90, knee: 34 },
    ])
    const rt = importProfiles(text)
    expect(rt.ok).toHaveLength(2)
    expect(rt.skipped).toBe(0)
    const bad = JSON.stringify({
      profiles: [
        { id: 'x', name: 'X', waist: 999, hip: 90, knee: 34 },   // 范围外
        { id: 'y', name: 'Y', waist: 64, hip: 90, knee: 34 },
      ],
    })
    const r2 = importProfiles(bad)
    expect(r2.ok.map((p) => p.id)).toEqual(['y'])
    expect(r2.skipped).toBe(1)
    expect(() => importProfiles('[]')).toThrow()
  })
})

describe('mesh 布料网格', () => {
  const mesh = buildClothMesh(rectPiece(10, 20))
  it('欧拉公式 V−E+F=1（三角化圆盘）+ 无退化', () => {
    const V = mesh.xy.length / 2
    const F = mesh.tri.length / 3
    const edges = new Map<number, number>()
    for (let t = 0; t < mesh.tri.length; t += 3) {
      const v = [mesh.tri[t], mesh.tri[t + 1], mesh.tri[t + 2]]
      for (let e = 0; e < 3; e++) {
        const i = v[e], j = v[(e + 1) % 3]
        const k = i < j ? i * V + j : j * V + i
        edges.set(k, (edges.get(k) ?? 0) + 1)
      }
    }
    expect(V - edges.size + F).toBe(1)
    // 每条边至多共享两次（流形）
    expect([...edges.values()].every((c) => c <= 2)).toBe(true)
  })
  it('边名聚合段沿链序，弧长累计 = 边长', () => {
    expect(mesh.runs.map((r) => r.name)).toEqual(['waist', 'side', 'hem', 'rise'])
    expect(mesh.runs[1].length).toBeCloseTo(20, 6)
    expect(runIndexAt(mesh.runs[1], 0)).toBe(mesh.runs[1].indices[0])
    expect(runIndexAt(mesh.runs[1], 1))
      .toBe(mesh.runs[1].indices[mesh.runs[1].indices.length - 1])
  })
  it('locate：内部命中且权重和 1，外部 null', () => {
    const loc = mesh.locate(5, 10)
    expect(loc).not.toBeNull()
    const w = loc!.w[0] + loc!.w[1] + loc!.w[2]
    expect(w).toBeCloseTo(1, 9)
    expect(mesh.locate(-1, 10)).toBeNull()
    expect(mesh.locate(5, 25)).toBeNull()
  })
})

describe('seams 摆位约定', () => {
  const man = buildMannequin(BODY, GIRTHS)
  it('左半 x<=0 / 右半 x>=0；前中 +Z、后中 −Z', () => {
    const fSide = placePoint('front', 'L', 0, 90, 0, 20, man)
    expect(fSide[0]).toBeLessThanOrEqual(0)
    expect(Math.abs(fSide[2])).toBeLessThan(1e-9)      // θ=−90°：正侧方
    const fRise = placePoint('front', 'L', 20, 90, 0, 20, man)
    expect(Math.abs(fRise[0])).toBeLessThan(1e-9)
    expect(fRise[2]).toBeGreaterThan(0)                // 前中 +Z
    const bCb = placePoint('back', 'L', 0, 90, 0, 20, man)
    expect(Math.abs(bCb[0])).toBeLessThan(1e-9)
    expect(bCb[2]).toBeLessThan(0)                     // 后中 −Z
    const bSideR = placePoint('back', 'R', 20, 90, 0, 20, man)
    expect(bSideR[0]).toBeGreaterThanOrEqual(0)
    // 摆位半径 = 体表支撑 + 松量 > 0
    expect(fSide[0]).toBeLessThan(0)
  })
  it('高度直通：全局 y 即身体高度', () => {
    const p = placePoint('front', 'L', 10, 55.5, 0, 20, man)
    expect(p[1]).toBeCloseTo(55.5, 9)
  })
})

describe('pbd 碰撞与解算', () => {
  const man = buildMannequin(BODY, GIRTHS)
  it('体内粒子推出到 R+skin（radiusAt 单位向量口径）', () => {
    const s = sectionAt(man.pelvis, 98)
    // 轴向粒子：推出后恰在 s.a + skin（位移纯法向，摩擦项切向分量为 0）
    const pos = new Float32Array([s.cx + s.a * 0.5, 98, 0])
    const prev = pos.slice()
    collideOne(pos, prev, 0, man, 0.3, 0.5)
    expect(pos[0] - s.cx).toBeCloseTo(s.a + 0.3, 3)
    // 斜向粒子 (3,4)：归一化后支撑半径不被距离稀释（修复前未归一化口径
    // 均衡点 ≈√R≈3.8cm、粒子可沉入体表 ~10cm——修复后此断言才有强度）
    const pos2 = new Float32Array([s.cx + 3, 98, 4])
    const prev2 = pos2.slice()
    collideOne(pos2, prev2, 0, man, 0.3, 0.5)
    const dx = pos2[0] - s.cx, dz = pos2[2]
    const dist = Math.hypot(dx, dz)
    expect(dist).toBeGreaterThanOrEqual(
      radiusAt(s, dx / dist, dz / dist) + 0.3 - 1e-6)
  })
  it('全 pin：收敛 settled 且位置钉住', () => {
    const mesh = buildClothMesh(rectPiece(6, 12))
    const n = mesh.xy.length / 2
    const pos = new Float32Array(3 * n)
    for (let i = 0; i < n; i++) {
      pos[3 * i] = mesh.xy[2 * i]
      pos[3 * i + 1] = 120 + mesh.xy[2 * i + 1]
      pos[3 * i + 2] = 8
    }
    const garment: Garment = {
      parts: [{ key: 'front', side: 'L', mesh, offset: 0 } as GarmentPart],
      pos,
      seam: new Int32Array(0),
      pinIdx: Uint32Array.from({ length: n }, (_, i) => i),
      pinTarget: pos.slice(),
      total: n,
    }
    const sim = createSim(garment, man)
    let st = 'running'
    for (let k = 0; k < 80 && st === 'running'; k++) st = stepSim(sim)
    expect(st).toBe('settled')
    for (let i = 0; i < 3 * n; i++) {
      expect(Math.abs(sim.pos[i] - pos[i])).toBeLessThan(0.05)
    }
  })
  it('无 pin 自由落体：y 单调下降且有限', () => {
    const mesh = buildClothMesh(rectPiece(6, 12))
    const n = mesh.xy.length / 2
    const pos = new Float32Array(3 * n)
    for (let i = 0; i < n; i++) {
      pos[3 * i] = mesh.xy[2 * i]
      pos[3 * i + 1] = 200 - mesh.xy[2 * i + 1]   // 身体上方悬空
      pos[3 * i + 2] = 60
    }
    const garment: Garment = {
      parts: [{ key: 'front', side: 'L', mesh, offset: 0 } as GarmentPart],
      pos, seam: new Int32Array(0),
      pinIdx: new Uint32Array(0), pinTarget: new Float32Array(0), total: n,
    }
    const sim = createSim(garment, man)
    const y0 = sim.pos[1]
    for (let k = 0; k < 10; k++) stepSim(sim)
    expect(sim.pos[1]).toBeLessThan(y0)
    for (let i = 0; i < 3 * n; i++) {
      expect(Number.isFinite(sim.pos[i])).toBe(true)
    }
  })
})

describe('buildMannequin 入口守卫（畸形/退化/极端 payload）', () => {
  const strictlyDown = (t: { rings: { y: number }[] }): boolean =>
    t.rings.every((r, i) => i === 0 || t.rings[i - 1].y > r.y)
  // 改站点 y / 追加站点，其余夹具字段不动
  const withStations = (
    over: Partial<Record<string, number>>,
    extra: FittingResult['body']['stations'] = [],
  ): FittingResult['body'] => ({
    ...BODY,
    stations: [
      ...BODY.stations.map((s) =>
        s.key in over ? { ...s, y: over[s.key]! } : s),
      ...extra,
    ],
  })
  it('crotch y=88 ≥ hip 86：clamp 到 hip−2，两管严格降序、头带不抛', () => {
    const man = buildMannequin(withStations({ crotch: 88 }), GIRTHS)
    expect(strictlyDown(man.pelvis)).toBe(true)
    expect(strictlyDown(man.legs[0])).toBe(true)
    // yTop = min(clamp 裆 84 + 7, 臀 86 − 2) = 84 == crotch → 头带退化为
    // 空（Δ=0 首 k 环即 break），腿顶 = 下段 crotch 环 84
    expect(man.legs[0].rings[0].y).toBeCloseTo(84, 6)
  })
  it('thigh 站 y=78 == crotch（集成夹具真实场景）：clamp 到 77.5，无重复 y 环', () => {
    const man = buildMannequin(withStations({},
      [{ key: 'thigh', y: 78, girth_finished: null, per: 'leg' }]), GIRTHS)
    expect(strictlyDown(man.legs[0])).toBe(true)
    expect(man.legs[0].rings.some((r) => Math.abs(r.y - 77.5) < 1e-9)).toBe(true)
  })
  it('浅裆（hip 80 / crotch 78，间隔 2 为入口 clamp 下限）：楔独立成立', () => {
    // 入口 clamp 保证 yHip−yCrotch ≥ 2，故 yTop ≤ crotch+0.5 的「无头带」
    // 分支为防御性代码（yTop = min(85, 78) = 78 = crotch）；几何仍完备
    const man = buildMannequin(withStations({ hip: 80 }), GIRTHS)
    // 五轮楔底 = crotch − wedgeDropBelowCrotch（3，随常数走防再失联）
    expect(man.pelvis.rings[man.pelvis.rings.length - 1].y)
      .toBeCloseTo(78 - BODY_RATIO.wedgeDropBelowCrotch, 6)
    expect(strictlyDown(man.legs[0])).toBe(true)
    expect(man.legs[0].rings[0].y).toBeCloseTo(78, 6)   // 腿自 crotch 穹顶起
  })
  it('极端围度比：hip75×thigh80 / hip130（thigh 缺省）：外缘超标=诚实降级不抛', () => {
    // 新口径无容纳预检：粗腿 gap 下限绑定（腿确实比盆宽），cx 恒正
    const slim = buildMannequin(BODY, { waist: 60, hip: 75, thigh: 80, knee: 32 })
    expect(slim.legs[0].rings[0].y).toBeCloseTo(83, 6)
    expect(slim.legs[0].rings.every((r) => Math.abs(r.cx) > 5)).toBe(true)
    const wide = buildMannequin(BODY, { waist: 100, hip: 130, knee: 44 })
    expect(wide.legs[0].rings[0].y).toBeCloseTo(83, 6)
    expect(strictlyDown(wide.legs[0])).toBe(true)
  })
  it('胖腰粗腿病理体型（waist130/hip70/thigh90 逐字段合法）：cx 恒正不抛', () => {
    // 旧 containment 口径在此体型降级放弃上插；新口径 gap 下限保证
    // cx ≥ a−1.8 > 0（实测 min 5.25），双腿永不跨中线融合/翻转
    const man = buildMannequin(
      BODY, { waist: 130, hip: 70, thigh: 90, knee: 35 })
    expect(strictlyDown(man.pelvis)).toBe(true)
    expect(strictlyDown(man.legs[0])).toBe(true)
    expect(man.legs[0].rings[0].y).toBeCloseTo(83, 6)
    for (const leg of man.legs) {
      for (const r of leg.rings) expect(Math.abs(r.cx)).toBeGreaterThan(0)
    }
    expect(man.pelvis.rings[man.pelvis.rings.length - 1].y)
      .toBeCloseTo(Y_CROTCH - BODY_RATIO.wedgeDropBelowCrotch, 6)
  })
})

describe('heatmap 应变', () => {
  it('静止长 0 / 拉长为正；色带 红-绿-蓝 单调', () => {
    const mesh = buildClothMesh(rectPiece(4, 8))
    const n = mesh.xy.length / 2
    const pos = new Float32Array(3 * n)
    for (let i = 0; i < n; i++) {
      pos[3 * i] = mesh.xy[2 * i]
      pos[3 * i + 1] = 100 + mesh.xy[2 * i + 1]
      pos[3 * i + 2] = 0
    }
    const garment: Garment = {
      parts: [{ key: 'front', side: 'L', mesh, offset: 0 } as GarmentPart],
      pos, seam: new Int32Array(0),
      pinIdx: new Uint32Array(0), pinTarget: new Float32Array(0), total: n,
    }
    const s0 = computeStrain(garment, pos)
    // rest 存 Float32（相对精度 ~1e-7），零应变容差取 1e-5
    for (let i = 0; i < n; i++) expect(Math.abs(s0[i])).toBeLessThan(1e-5)
    pos[2] += 1      // 拉开 0 号粒子：其邻接应变转正
    const s1 = computeStrain(garment, pos)
    expect(s1[0]).toBeGreaterThan(0)
    // 色带：紧=红分量最大、贴合=绿、松=蓝分量最大
    const [rT, , bT] = strainColor(0.08)
    const [, gF] = strainColor(0)
    const [rL, , bL] = strainColor(-0.08)
    expect(rT).toBeGreaterThan(bT)
    expect(gF).toBeGreaterThan(0.7)
    expect(bL).toBeGreaterThan(rL)
  })
})
