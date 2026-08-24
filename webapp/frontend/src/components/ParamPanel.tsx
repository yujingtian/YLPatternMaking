import { useMemo, useState } from 'react'
import type { Gate, GroupSpec, IssueDetail, ParamSpec, Values } from '../types'
import { Input, InputNumber, Select, Switch, Collapse, Badge } from 'antd'

interface Props {
  groups: GroupSpec[]
  measurements: Values
  options: Values
  errors: IssueDetail[]
  onMeasurement: (key: string, value: unknown) => void
  onOption: (key: string, value: unknown) => void
}

// 虚拟参数 pocket_type：挖削前口袋 / 前贴袋互斥，读写两个隐藏开关
function pocketTypeOf(options: Values): string {
  if (options.front_patch) return '前贴袋'
  if (options.front_pocket) return '挖削前口袋'
  return '无'
}

// 虚拟参数 fly_type：连裁 / 独立门襟互斥（fly_separate 优先口径，同引擎）
function flyTypeOf(options: Values): string {
  if (options.fly_separate) return '独立门襟'
  if (options.fly) return '连裁门襟'
  return '无'
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

function ParamInput({ spec, value, onChange, err, options, setOption }: {
  spec: ParamSpec
  value: unknown
  onChange: (v: unknown) => void
  err?: string
  options: Values
  setOption: (key: string, value: unknown) => void
}) {
  const [jsonText, setJsonText] = useState<string | null>(null)
  const [jsonBad, setJsonBad] = useState(false)

  let control: JSX.Element
  switch (spec.type) {
    case 'pocket_type':
      control = (
        <Select
          size="small"
          style={{ width: '100%' }}
          value={pocketTypeOf(options)}
          options={(spec.choices ?? []).map((c) => ({ value: c, label: c }))}
          onChange={(v) => {
            const inset = v === '挖削前口袋'
            setOption('front_pocket', inset)
            setOption('front_patch', v === '前贴袋')
            if (!inset) {
              // 挖削附属特征随主形态一并关闭，避免残留开启触发依赖校验错误
              setOption('front_pocket_facing', false)
              setOption('front_pouch', false)
              setOption('watch_pocket', false)
            }
          }}
        />
      )
      break
    case 'fly_type':
      control = (
        <Select
          size="small"
          style={{ width: '100%' }}
          value={flyTypeOf(options)}
          options={(spec.choices ?? []).map((c) => ({ value: c, label: c }))}
          onChange={(v) => {
            setOption('fly', v === '连裁门襟')
            setOption('fly_separate', v === '独立门襟')
          }}
        />
      )
      break
    case 'bool':
      control = (
        <Switch
          size="small"
          checked={Boolean(value ?? spec.default)}
          onChange={(v) => onChange(v)}
        />
      )
      break
    case 'enum':
      control = (
        <Select
          size="small"
          style={{ width: '100%' }}
          value={String(value ?? spec.default)}
          options={spec.choices!.map((c) => ({ value: c, label: c }))}
          onChange={(v) => onChange(v)}
        />
      )
      break
    case 'sa': {
      const sa = (value ?? spec.default) as Record<string, number>
      control = (
        <div className="sa-grid">
          {Object.entries(sa).map(([k, v]) => (
            <span key={k} className="sa-item">
              <em>{k}</em>
              <InputNumber
                size="small"
                style={{ width: 72 }}
                step={0.1}
                value={v}
                status={err ? 'error' : undefined}
                onChange={(nv) => onChange({ ...sa, [k]: nv ?? 0 })}
              />
            </span>
          ))}
        </div>
      )
      break
    }
    case 'json': {
      // tuple/list 复杂结构：JSON 文本编辑，失焦解析；语法错误红框提示
      // （静默保留文本会让用户误以为已生效——state 仍是旧值）
      const text = jsonText ?? JSON.stringify(value ?? spec.default ?? [])
      control = (
        <Input
          size="small"
          className="json-input"
          status={err || jsonBad ? 'error' : undefined}
          value={text}
          onChange={(e) => {
            setJsonText(e.target.value)
            setJsonBad(false)
          }}
          onBlur={() => {
            try {
              onChange(JSON.parse(text || '[]'))
              setJsonText(null)
              setJsonBad(false)
            } catch {
              // 语法错误：保持文本并标红，值未生效
              setJsonBad(true)
            }
          }}
        />
      )
      break
    }
    case 'string':
      control = (
        <Input
          size="small"
          status={err ? 'error' : undefined}
          value={String(value ?? spec.default ?? '')}
          onChange={(e) => onChange(e.target.value)}
        />
      )
      break
    default: { // number / int / nullable
      control = (
        <InputNumber
          size="small"
          style={{ width: '100%' }}
          step={spec.type === 'int' ? 1 : 'any'}
          precision={spec.type === 'int' ? 0 : undefined}
          placeholder={spec.nullable ? '自动' : undefined}
          status={err ? 'error' : undefined}
          value={value === null || value === undefined
            ? (spec.nullable ? null : (spec.default as number))
            : (value as number)}
          onChange={(v) => onChange(v)}
        />
      )
    }
  }
  return (
    <div className={`param${err ? ' param-error' : ''}`}>
      <div className="param-head">
        <span className="param-label" title={spec.key}>{spec.label}</span>
        {control}
      </div>
      {err && <div className="param-msg">{err}</div>}
    </div>
  )
}

export default function ParamPanel({
  groups, measurements, options, errors,
  onMeasurement, onOption,
}: Props) {
  const [search, setSearch] = useState('')
  const errs = useMemo(() => errorMap(errors), [errors])
  const qs = search.trim().toLowerCase()

  const items = groups
    .map((g) => {
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
              return (
                <ParamInput
                  key={p.key}
                  spec={p}
                  value={value}
                  err={errs.get(p.key)}
                  options={options}
                  setOption={onOption}
                  onChange={(v) =>
                    (isMeasure ? onMeasurement : onOption)(p.key, v)}
                />
              )
            })}
          </div>
        ),
      }
    })
    .filter((x): x is NonNullable<typeof x> => x !== null)

  // 默认仅展开基础测量，其余全收起（用户口径 2026-08）
  const defaultActive = ['measurements']

  return (
    <div className="param-panel">
      <Input.Search
        allowClear
        placeholder="搜索参数名（如 p1_dist / 缩水）…"
        onChange={(e) => setSearch(e.target.value)}
        style={{ marginBottom: 8 }}
      />
      <Collapse
        size="small"
        defaultActiveKey={defaultActive}
        items={items}
      />
    </div>
  )
}
