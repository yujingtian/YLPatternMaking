// 参数叶子控件（自 ParamPanel 抽出，2026-09-11 交互重构）：按 spec.type
// 分派的单参数渲染体 + 虚拟参数（pocket_type/fly_type）读写双开关的
// helper。ParamPanel（全部参数）与 CoreParams（核心参数）两处共用，
// 改动须保持两处行为一致。
import { useState } from 'react'
import { Input, InputNumber, Select, Switch } from 'antd'
import type {
  EdgeSpec, ParamSpec, SeedPayload, SeedResult, Values,
} from '../types'
import CustomShapeEditor from './CustomShapeEditor'

export interface ParamInputProps {
  spec: ParamSpec
  value: unknown
  onChange: (v: unknown) => void
  err?: string
  options: Values
  // 全 schema 参数默认值表（open 链近似锚点兜底用：options state 初始为 {}，
  // 只有 touched 键有值，未手输的锚点参数须回落 schema 默认而非 0）
  defaults?: Record<string, unknown>
  // 暂时中文口径（2026-09-19）：键->中文名，仅覆盖标签与枚举下拉的显示，
  // 值/搜索/校验不受影响；不传 = 英文键原样（全部参数页签现状）
  zhMap?: Record<string, string>
  setOption: (key: string, value: unknown) => void
  onSeed: (kind: SeedPayload['kind'], shape: string) =>
    Promise<SeedResult | { ok: false; message: string }>
}

// 虚拟参数 pocket_type：挖削前口袋 / 前贴袋互斥，读写两个隐藏开关
export function pocketTypeOf(options: Values): string {
  if (options.front_patch) return '前贴袋'
  if (options.front_pocket) return '挖削前口袋'
  return '无'
}

// 虚拟参数 fly_type：连裁 / 独立门襟互斥（fly_separate 优先口径，同引擎）
export function flyTypeOf(options: Values): string {
  if (options.fly_separate) return '独立门襟'
  if (options.fly) return '连裁门襟'
  return '无'
}

export default function ParamInput({
  spec, value, onChange, err, options, defaults, zhMap, setOption, onSeed,
}: ParamInputProps) {
  const [jsonText, setJsonText] = useState<string | null>(null)
  const [jsonBad, setJsonBad] = useState(false)

  // custom_shape 虚拟参数：整行块布局（编辑器自带双表 + 预览），
  // 直写 points/edges 两真实键（同 pocket_type 写多开关的先例）
  if (spec.type === 'custom_shape') {
    return (
      <div className={`param shape-param${err ? ' param-error' : ''}`}
           data-param={spec.key}>
        <div className="shape-label">{spec.label}</div>
        <CustomShapeEditor
          kind={spec.kind!}
          vPositive={spec.v_positive ?? 'down'}
          mode={spec.mode ?? 'closed'}
          edgeFormat={spec.edge_format ?? 'bulge'}
          seedChoices={spec.choices ?? []}
          anchorVals={spec.anchor_keys?.map(
            (k) => Number(options[k] ?? defaults?.[k] ?? 0))}
          points={(options[spec.points_key!] as [number, number][] | undefined) ?? []}
          edges={(options[spec.edges_key!] as EdgeSpec[] | undefined) ?? []}
          onPoints={(pts) => setOption(spec.points_key!, pts)}
          onEdges={(eds) => setOption(spec.edges_key!, eds)}
          onSeed={onSeed}
          err={err}
        />
      </div>
    )
  }

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
          options={spec.choices!.map(
            (c) => ({ value: c, label: zhMap?.[c] ?? c }))}
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
    <div className={`param${err ? ' param-error' : ''}`} data-param={spec.key}>
      <div className="param-head">
        <span className="param-label" title={spec.key}>
          {zhMap?.[spec.key] ?? spec.label}
        </span>
        {control}
      </div>
      {err && <div className="param-msg">{err}</div>}
    </div>
  )
}
