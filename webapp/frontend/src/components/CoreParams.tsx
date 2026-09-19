// 核心参数页签（左栏默认视图）：按 coreParams.ts 白名单从 schema 取
// spec 平铺渲染（ParamInput 共用渲染体）。值路由与 ParamPanel 同口径：
// 基础测量组读 measurements、其余读 options、虚拟参数读双开关派生值。
// 白名单键在 schema 中找不到时静默跳过（防 schema 演进崩面板）。
import { useEffect, useMemo, useRef } from 'react'
import type {
  IssueDetail, ParamSpec, SectionSpec, SeedPayload, SeedResult, Values,
} from '../types'
import ParamInput, { flyTypeOf, pocketTypeOf } from './ParamInput'
import { CORE_PARAM_GROUPS, CORE_PARAM_ZH } from '../coreParams'

// schema 白名单键 -> spec（全 section/group 扫一遍建索引）
function specIndex(sections: SectionSpec[]): Map<string, ParamSpec> {
  const m = new Map<string, ParamSpec>()
  for (const s of sections) {
    for (const g of s.groups) {
      for (const p of g.params) m.set(p.key, p)
    }
  }
  return m
}

function errorMap(errors: IssueDetail[]): Map<string, string> {
  const m = new Map<string, string>()
  for (const e of errors) if (e.param) m.set(e.param, e.message)
  return m
}

export default function CoreParams({
  sections, measurements, options, errors,
  onMeasurement, onOption, onSeed, highlight,
}: {
  sections: SectionSpec[]
  measurements: Values
  options: Values
  errors: IssueDetail[]
  onMeasurement: (key: string, value: unknown) => void
  onOption: (key: string, value: unknown) => void
  onSeed: (kind: SeedPayload['kind'], shape: string) =>
    Promise<SeedResult | { ok: false; message: string }>
  // 拖拽回写高亮（与 ParamPanel 同款闪烁；核心页签无折叠，免展开逻辑）
  highlight: { param: string; ts: number } | null
}) {
  const specs = useMemo(() => specIndex(sections), [sections])
  const errs = useMemo(() => errorMap(errors), [errors])
  const rootRef = useRef<HTMLDivElement>(null)

  // 拖拽回写目标在核心页签可见时闪烁定位（滚动居中，只滚面板自身）
  useEffect(() => {
    if (!highlight) return
    const t = window.setTimeout(() => {
      const root = rootRef.current
      const el = root?.querySelector(`[data-param="${highlight.param}"]`)
      if (!root || !el) return
      const rr = root.getBoundingClientRect()
      const er = el.getBoundingClientRect()
      root.scrollTo({
        top: root.scrollTop + er.top - rr.top - (root.clientHeight - er.height) / 2,
        behavior: 'smooth',
      })
      el.classList.remove('param-flash')
      void (el as HTMLElement).offsetWidth
      el.classList.add('param-flash')
    }, 150)
    return () => window.clearTimeout(t)
  }, [highlight])

  return (
    <div className="core-params" ref={rootRef}>
      {CORE_PARAM_GROUPS.map((g) => {
        const rows = g.params
          .map((k) => ({ spec: specs.get(k), key: k }))
          .filter((r): r is { spec: ParamSpec; key: string } => r.spec != null)
        if (rows.length === 0) return null
        return (
          <div key={g.key} className="core-group">
            <div className="core-group-title">{g.label}</div>
            {rows.map(({ spec }) => {
              const isMeasure = g.key === 'measurements'
              const value = spec.type === 'pocket_type'
                ? pocketTypeOf(options)
                : spec.type === 'fly_type'
                  ? flyTypeOf(options)
                  : isMeasure
                    ? measurements[spec.key] ?? spec.default
                    : options[spec.key] ?? spec.default
              return (
                <ParamInput
                  key={spec.key}
                  spec={spec}
                  value={value}
                  err={errs.get(spec.key)}
                  options={options}
                  zhMap={CORE_PARAM_ZH}
                  setOption={onOption}
                  onSeed={onSeed}
                  onChange={(v) =>
                    (isMeasure ? onMeasurement : onOption)(spec.key, v)}
                />
              )
            })}
          </div>
        )
      })}
    </div>
  )
}
