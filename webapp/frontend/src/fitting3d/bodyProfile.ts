// 体型（人台围度）参数：独立于打版参数的 BodyProfile。
// 用户口径 2026-09-09：尺寸单围度是成衣量（含松量/调节量）不能直接当
// 人体量——体型独立设置、不进引擎 Measurements/DraftPayload、不影响
// 打版；默认值由成衣尺寸按先验松量反推估计（标注「估计值」），
// 用户选预设或手输真实测量值后覆盖。
import { BODY_MIN_RATIO, EASE_PRIOR } from './priors'

// 单位 cm；thigh 可缺（缺省站点由 mannequin 按比例先验补全）
export interface BodyProfile {
  id: string
  name: string
  waist: number
  hip: number
  thigh?: number
  knee: number
  height?: number       // 仅信息展示（躯干延伸恒为先验 18cm）
  estimated?: boolean   // true = 从成衣尺寸反推的估计值（UI 标注）
}

export type BodyGirths = Pick<BodyProfile, 'waist' | 'hip' | 'thigh' | 'knee'>

const _est = (finished: number, ease: number): number =>
  Math.max(finished * BODY_MIN_RATIO, finished - ease)

// 成衣围 -> 人体围估计（先验松量反推 + 0.85 下限防负松量翻车）
export function estimateBody(
  m: { waist: number; hip: number; knee: number; thigh?: number },
): BodyProfile {
  return {
    id: 'estimated',
    name: '估计体型（按成衣尺寸）',
    waist: _est(m.waist, EASE_PRIOR.waist),
    hip: _est(m.hip, EASE_PRIOR.hip),
    thigh: m.thigh && m.thigh > 0
      ? _est(m.thigh, EASE_PRIOR.thigh) : undefined,
    knee: _est(m.knee, EASE_PRIOR.knee),
    estimated: true,
  }
}

// 体型围度合法性（导入/手输校验）：与成衣围同数量级的人体围范围
export function validateGirths(b: {
  waist: number; hip: number; knee: number; thigh?: number
}): string | null {
  const rng = (v: number, lo: number, hi: number, label: string) =>
    (v >= lo && v <= hi) ? null : `${label}应在 ${lo}~${hi}cm 之间`
  return rng(b.waist, 50, 130, '腰围') ?? rng(b.hip, 70, 150, '臀围')
    ?? rng(b.knee, 28, 60, '膝围')
    ?? (b.thigh != null ? rng(b.thigh, 35, 90, '大腿围') : null)
}
