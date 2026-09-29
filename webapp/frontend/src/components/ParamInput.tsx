// 参数叶子控件（自 ParamPanel 抽出，2026-09-11 交互重构）：按 spec.type
// 分派的单参数渲染体 + 虚拟参数（pocket_type/fly_type）读写双开关的
// helper。ParamPanel（全部参数）与 CoreParams（核心参数）两处共用，
// 改动须保持两处行为一致。
import { useEffect, useRef, useState } from 'react'
import { Input, InputNumber, Select, Switch } from 'antd'
import type {
  EdgeSpec, Gate, ParamSpec, SeedPayload, SeedResult, Values,
} from '../types'
import CustomShapeEditor from './CustomShapeEditor'

// 参数级 gate 判定（ParamPanel 参数显隐 / sa 字段级显隐共用；与引擎
// webschema.gate_on 同语义）：字符串 = 布尔开关键；对象 = requires
// 布尔开关须全真 + not 布尔开关须全假（互补开关）+ 枚举值匹配
// （省略 param = 只判开关）
export function gateOn(gate: Gate, options: Values): boolean {
  if (typeof gate === 'string') return Boolean(options[gate])
  if (!(gate.requires ?? []).every((k) => Boolean(options[k]))) return false
  if ((gate.not ?? []).some((k) => Boolean(options[k]))) return false
  if (gate.param == null) return true
  const v = options[gate.param]
  return v != null && (gate.values ?? []).includes(String(v))
}

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
  // 值/搜索/校验不受影响；不传 = 英文键原样。核心页签传 CORE_PARAM_ZH、
  // 全部页签传全量 PARAM_ZH（2026-09-24 起）
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

// 数字参数显示值（纯函数，金标 ParamInput.test.ts）：编辑期空态覆写
// 优先（受控 InputNumber 显示保持空、不被默认值回弹的机制本体）->
// value 缺失回落（可空 = null 空态 + placeholder「自动」、非可空 =
// schema 默认）
export function numberDisplayValue(
  spec: ParamSpec, value: unknown, holdEmpty: boolean,
): number | null {
  if (holdEmpty) return null
  if (value === null || value === undefined)
    return spec.nullable ? null : (spec.default as number | null)
  return value as number
}

// 数字参数空输入提交值（纯函数）：可空 -> null（自动）；非可空 ->
// undefined（未设置态——JSON.stringify 丢键，载荷/localStorage 暂存
// 均不含该键，引擎回落自身默认，与 placeholder 灰显的默认值同源）。
// 绝不提交 null：引擎 from_dict 对 None 直通会撞类型校验（旧口径的
// 隐藏雷）
export function emptyNumberCommit(spec: ParamSpec): unknown {
  return spec.nullable ? null : undefined
}

// 缝份对象（sa 类型）的语义边名 -> 中文（2026-09-24）：与参数键/枚举值
// 分表维护——边名与参数键同名异物（hem=裤口/脚口边、waist=腰围/腰口），
// 并入一张表会串义；title 同款「英文 · 中文」双名
const SA_EDGE_ZH: Record<string, string> = {
  top: '上边', bottom: '下边', left_end: '左端', right_end: '右端',
  cb: '后中', side: '侧缝', waist: '腰口', inner: '内边',
  inseam: '下裆缝', hem: '脚口', mouth: '袋口', fold: '对折边',
  rise: '前浪', outer: '外边',
  fly_top: '门襟顶', fly_outer: '门襟外边', fly_bottom: '门襟底',
}

export default function ParamInput({
  spec, value, onChange, err, options, defaults, zhMap, setOption, onSeed,
}: ParamInputProps) {
  const [jsonText, setJsonText] = useState<string | null>(null)
  const [jsonBad, setJsonBad] = useState(false)
  // 编辑期空态覆写（2026-09-29 修「删不掉」）：数字/int 参数清空时 antd
  // InputNumber 上抛 onChange(null)，旧口径 null 直进 options 后被
  // ParamPanel/CoreParams 的 ?? default 与本组件的非空兜底两层回落，
  // 受控 value 立即回填显示——清空的瞬间默认值弹回。现口径：清空只改
  // 本地覆写（显示保持空），提交走 emptyNumberCommit。外部改值（拖拽
  // 回写/一键修复/换源）解除覆写；聚焦中除外——清空提交本身就是一次
  // 值变化，不能自解锁（custom_shape 分支提前 return 在后，hook 须在前）
  const [numEmpty, setNumEmpty] = useState(false)
  const [saEmpty, setSaEmpty] = useState<string | null>(null)
  const focusRef = useRef(false)
  useEffect(() => {
    if (!focusRef.current) {
      setNumEmpty(false)
      setSaEmpty(null)
    }
  }, [value])
  // 中文名 + 双名 title（字段名 · 中文；无翻译回落英文键单名）
  const zh = zhMap?.[spec.key]

  // custom_shape 虚拟参数：整行块布局（编辑器自带双表 + 预览），
  // 直写 points/edges 两真实键（同 pocket_type 写多开关的先例）
  if (spec.type === 'custom_shape') {
    return (
      <div className={`param shape-param${err ? ' param-error' : ''}`}
           data-param={spec.key}>
        <div className="shape-label"
             title={zh ? `${spec.key} · ${zh}` : spec.key}>
          {zh ?? spec.label}
        </div>
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
      // 字段级 gate（schema sa_field_gates）：不消费的语义边不显示
      // （如前片 fly_* 三边在连裁门襟关闭时隐藏）。gate 读值回落 schema
      // 默认（options 只存碰过的键，未手改的开关键缺失——与 ParamPanel
      // gateVals 同口径）
      const fieldGates = spec.sa_field_gates
      const gateVals = { ...defaults, ...options }
      const fields = Object.entries(sa).filter(
        ([k]) => fieldGates?.[k] == null || gateOn(fieldGates[k], gateVals))
      control = (
        <div className="sa-grid">
          {fields.map(([k, v]) => (
            <span key={k} className="sa-item">
              <em title={SA_EDGE_ZH[k] ? `${k} · ${SA_EDGE_ZH[k]}` : k}>
                {SA_EDGE_ZH[k] ?? k}
              </em>
              <InputNumber
                size="small"
                style={{ width: 72 }}
                step={0.1}
                value={saEmpty === k ? null : v}
                status={err ? 'error' : undefined}
                onFocus={() => { focusRef.current = true }}
                onBlur={() => {
                  focusRef.current = false
                  // 缝边无「未设置」语义：清空只在编辑期持空，失焦恢复
                  // 已提交值（不落 0——缝边被静默清零会出废裁片）
                  setSaEmpty((e) => (e === k ? null : e))
                }}
                onChange={(nv) => {
                  if (nv == null) {
                    setSaEmpty(k)
                    return
                  }
                  setSaEmpty(null)
                  onChange({ ...sa, [k]: nv })
                }}
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
          // placeholder 顺带承载「当前生效默认值」：清空后的未设置态灰显
          // schema 默认，与引擎实际回落值同源（nullable 照旧「自动」）
          placeholder={spec.nullable ? '自动'
            : spec.default != null ? String(spec.default) : undefined}
          status={err ? 'error' : undefined}
          value={numberDisplayValue(spec, value, numEmpty)}
          onFocus={() => { focusRef.current = true }}
          onBlur={() => { focusRef.current = false }}
          onChange={(nv) => {
            if (nv == null) {
              setNumEmpty(true)
              onChange(emptyNumberCommit(spec))
            } else {
              setNumEmpty(false)
              onChange(nv)
            }
          }}
        />
      )
    }
  }
  return (
    <div className={`param${err ? ' param-error' : ''}`} data-param={spec.key}>
      <div className="param-head">
        <span className="param-label"
              title={zh ? `${spec.key} · ${zh}` : spec.key}>
          {zh ?? spec.label}
        </span>
        {control}
      </div>
      {err && <div className="param-msg">{err}</div>}
    </div>
  )
}
