import { useEffect, useMemo, useRef, useState } from 'react'
import type {
  Gate, GroupSpec, IssueDetail, SectionSpec, SeedResult, SeedPayload, Values,
} from '../types'
import { Input, Collapse, Badge } from 'antd'
import ParamInput, { flyTypeOf, pocketTypeOf } from './ParamInput'

interface Props {
  sections: SectionSpec[]
  measurements: Values
  options: Values
  errors: IssueDetail[]
  onMeasurement: (key: string, value: unknown) => void
  onOption: (key: string, value: unknown) => void
  // 从形态导入（custom_shape 编辑器 seed；失败内联显示在编辑器里）
  onSeed: (kind: SeedPayload['kind'], shape: string) =>
    Promise<SeedResult | { ok: false; message: string }>
  highlight: { param: string; ts: number } | null
}

// 参数级 gate 判定：字符串 = 布尔开关键；对象 = 枚举参数值匹配
// （形态联动；requires 布尔开关须同时全真，如前贴袋形态参数复合开关）
function gateOn(gate: Gate, options: Values): boolean {
  if (typeof gate === 'string') return Boolean(options[gate])
  if (!(gate.requires ?? []).every((k) => Boolean(options[k]))) return false
  const v = options[gate.param]
  return v != null && gate.values.includes(String(v))
}

function errorMap(errors: IssueDetail[]): Map<string, string> {
  const m = new Map<string, string>()
  for (const e of errors) if (e.param) m.set(e.param, e.message)
  return m
}

export default function ParamPanel({
  sections, measurements, options, errors,
  onMeasurement, onOption, onSeed, highlight,
}: Props) {
  const [search, setSearch] = useState('')
  const errs = useMemo(() => errorMap(errors), [errors])
  // 参数默认值表：编辑器侧直读 options 的功能（open 链近似锚点）兜底用
  const defaults = useMemo(() => {
    const m: Record<string, unknown> = {}
    for (const s of sections) for (const g of s.groups) for (const p of g.params)
      m[p.key] = p.default
    return m
  }, [sections])
  const qs = search.trim().toLowerCase()
  const rootRef = useRef<HTMLDivElement>(null)
  // 受控折叠（原 defaultActiveKey 语义不变；二期拖拽高亮需程序化展开目标组）
  const [secOpen, setSecOpen] = useState<string[]>(() =>
    sections.filter((s) => !s.collapsed).map((s) => s.key))
  const [grpOpen, setGrpOpen] = useState<string[]>(() =>
    sections.flatMap((s) => s.groups.filter((g) => !g.collapsed)
      .map((g) => g.key)))

  // 拖拽回写高亮：展开参数所在段/组 -> 滚动居中 -> 闪烁动画。
  // 参数被 gate 隐藏（如口袋参数在开关关闭时）则静默无操作
  useEffect(() => {
    if (!highlight) return
    for (const s of sections) {
      const g = s.groups.find((gr) => gr.params.some((p) => p.key === highlight.param))
      if (!g) continue
      setSecOpen((ks) => (ks.includes(s.key) ? ks : [...ks, s.key]))
      setGrpOpen((ks) => (ks.includes(g.key) ? ks : [...ks, g.key]))
      break
    }
    const t = window.setTimeout(() => {
      const root = rootRef.current
      const el = root?.querySelector(`[data-param="${highlight.param}"]`)
      if (!root || !el) return
      // 只滚面板自身：scrollIntoView 会沿祖先链连滚 window/外层容器，
      // 把整版预览滚出视口；rect 差算 scrollTop 居中（等价 block:'center'）
      const rr = root.getBoundingClientRect()
      const er = el.getBoundingClientRect()
      root.scrollTo({
        top: root.scrollTop + er.top - rr.top - (root.clientHeight - er.height) / 2,
        behavior: 'smooth',
      })
      el.classList.remove('param-flash')
      void (el as HTMLElement).offsetWidth   // reflow 重启动画
      el.classList.add('param-flash')
    }, 150)          // 等 Collapse 展开渲染
    return () => window.clearTimeout(t)
  }, [highlight, sections])

  // 组 -> Collapse item（组级 gate / 参数级 gate / 搜索过滤 / 错误徽标 /
  // 值来源路由；两段式重构时整段逐行保留，勿顺手改动语义）
  const renderGroup = (g: GroupSpec) => {
    // 联动显隐：visible_if（单键或多键，全真才显示）指向的开关关闭时
    // 整组隐藏（搜索时仍显示）
    const gates = g.visible_if == null ? []
      : Array.isArray(g.visible_if) ? g.visible_if : [g.visible_if]
    const gate = gates.every((k) => Boolean(options[k]))
    if (!gate && qs.length === 0) return null
    const params = (qs
      ? g.params.filter(
          (p) => !p.hidden &&
            (p.key.toLowerCase().includes(qs) ||
              p.label.toLowerCase().includes(qs)))
      : g.params.filter(
          // 参数级联动：visible_if 为单键=该开关开才显示；
          // 为数组=任一开关开即显示（如口袋缩水率 gate 挖削/贴袋双形态）
          (p) => {
            if (p.hidden) return false
            if (!p.visible_if) return true
            const gates = Array.isArray(p.visible_if)
              ? p.visible_if : [p.visible_if]
            // gate：字符串=布尔开关，对象=枚举值匹配（形态联动）
            return gates.some((g) => gateOn(g, options))
          }))
    if (params.length === 0) return null

    const errCount = params.filter((p) => errs.has(p.key)).length
    const label = (
      <span className="group-title">
        {g.label}
        <span className="count">{params.length}</span>
        {gate ? null : (
          <span className="gate-hint">
            （依赖 {gates.join(' + ')}）
          </span>
        )}
      </span>
    )
    return {
      key: g.key,
      label: errCount
        ? <Badge count={errCount} offset={[10, 0]}>{label}</Badge>
        : label,
      children: (
        <div className="group-body">
          {params.map((p) => {
            const isMeasure = g.key === 'measurements'
            const value = p.type === 'pocket_type'
              ? pocketTypeOf(options)
              : p.type === 'fly_type'
                ? flyTypeOf(options)
                : isMeasure
                  ? measurements[p.key] ?? p.default
                  : options[p.key] ?? p.default
            // custom_shape 错误合并：原始 json 键已隐藏（_HIDDEN），
            // 422 归因到 points/edges 的消息由编辑器整体承接（一条足矣）
            const err = p.type === 'custom_shape'
              ? errs.get(p.points_key ?? '') ?? errs.get(p.edges_key ?? '')
              : errs.get(p.key)
            return (
              <ParamInput
                key={p.key}
                spec={p}
                value={value}
                err={err}
                options={options}
                defaults={defaults}
                setOption={onOption}
                onSeed={onSeed}
                onChange={(v) =>
                  (isMeasure ? onMeasurement : onOption)(p.key, v)}
              />
            )
          })}
        </div>
      ),
    }
  }

  // 两段式：外层 section 折叠、内层组折叠（嵌套 Collapse），默认态全由
  // schema 的 collapsed 字段驱动（用户口径 2026-08：默认仅展开基础测量，
  // 裁片段整段收起）。非搜索态下 section 内组全被 gate/过滤隐藏时整个
  // section 不渲染；搜索/错误徽标/gate-hint 均不向 section 标题上卷
  const sectionItems = sections
    .map((s) => {
      const items = s.groups.map(renderGroup)
        .filter((x): x is NonNullable<typeof x> => x !== null)
      if (items.length === 0 && qs.length === 0) return null
      return {
        key: s.key,
        label: <span className="section-title">{s.label}</span>,
        children: (
          <Collapse
            size="small"
            className="section-groups"
            activeKey={grpOpen}
            onChange={(k) => setGrpOpen(Array.isArray(k) ? k : [k])}
            items={items}
          />
        ),
      }
    })
    .filter((x): x is NonNullable<typeof x> => x !== null)

  return (
    <div className="param-panel" ref={rootRef}>
      <Input.Search
        allowClear
        placeholder="搜索参数名（如 p1_dist / 缩水）…"
        onChange={(e) => setSearch(e.target.value)}
        style={{ marginBottom: 8 }}
      />
      <Collapse
        size="small"
        activeKey={secOpen}
        onChange={(k) => setSecOpen(Array.isArray(k) ? k : [k])}
        items={sectionItems}
      />
    </div>
  )
}
