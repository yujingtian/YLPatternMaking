// 推板设置抽屉：相邻码档差表（基码锚定口径，用户拍板 2026-08-27——基码
// 行是锚：档差格恒「—」、绝对值只读取参数面板；上方行录「与更大相邻码
// 之差」、下方行录「与上一码之差」）。编辑模型 GradeTable 是草稿——打开
// 时由 canonical 重建、取消即弃；底部主按钮「导出推板 DXF」= 保存 + 下载
// 一步完成（onExport 回传 canonical，App 侧以显式覆盖参传 download 规避
// 闭包旧值）。换基码走 rebaseTable 重投影（放码关系不变）；行插入/删除/
// 换位档差跟行走（码序重组，灰字所见即所得）。转换/校验纯函数在 src/sizeRun.ts。

import { useEffect, useMemo, useState } from 'react'
import { Button, Drawer, Input, InputNumber, Radio, Space, Tag } from 'antd'
import {
  ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, PlusOutlined,
} from '@ant-design/icons'
import {
  MEASURE_KEYS, type MeasureKey, type SizeRunSpec, type Values,
} from '../types'
import {
  absoluteValues, emptySteps, fromGradeTable, rebaseTable, toGradeTable,
  validateTable, type GradeRow, type GradeTable,
} from '../sizeRun'

const MEASURE_LABELS: Record<MeasureKey, string> = {
  waist: '腰围', hip: '臀围', knee: '膝围', hem: '脚口',
  front_rise: '前浪', back_rise: '后浪', outseam: '裤长', thigh: '大腿围',
}

export default function SizeRunDrawer({
  open, onClose, spec, measurements, defaultLabel, busy, onExport,
}: {
  open: boolean
  onClose: () => void
  spec: SizeRunSpec | null
  measurements: Values
  defaultLabel: string
  busy: boolean
  onExport: (spec: SizeRunSpec) => void
}) {
  const [table, setTable] = useState<GradeTable>(
    () => toGradeTable(spec, defaultLabel))
  // 草稿随开合重建（打开期间 spec 不会变：setSizeRun 只发生在导出/模板载入）
  useEffect(() => {
    setTable(toGradeTable(spec, defaultLabel))
  }, [open, spec, defaultLabel])

  // 基码 8 参数（面板值，Number coerce；缺省 0 仅防 NaN，导出走引擎校验）
  const baseVals = useMemo(() => {
    const b = {} as Record<MeasureKey, number>
    for (const k of MEASURE_KEYS) {
      const v = Number(measurements[k])
      b[k] = Number.isFinite(v) ? v : 0
    }
    return b
  }, [measurements])
  const absVals = useMemo(() => absoluteValues(table, baseVals), [table, baseVals])
  const errors = useMemo(() => validateTable(table), [table])
  const thighOff = baseVals.thigh === 0   // 基码未录入大腿围：档差不生效
  const fmt = (v: number) => (Math.round(v * 10) / 10).toFixed(1)

  const setLabel = (i: number, label: string) =>
    setTable((t) => ({ ...t, rows: t.rows.map((r, k) =>
      (k === i ? { ...r, label } : r)) }))
  const setStep = (i: number, key: MeasureKey, v: number | null) =>
    setTable((t) => ({ ...t, rows: t.rows.map((r, k) =>
      (k === i ? { ...r, steps: { ...r.steps, [key]: v ?? 0 } } : r)) }))
  // 行下插入：档差沿用上一行（连续放码最常见），标签留待填写
  const insertAfter = (i: number) =>
    setTable((t) => {
      const rows = [...t.rows]
      rows.splice(i + 1, 0, { label: '', steps: { ...t.rows[i].steps } })
      return { ...t, rows }
    })
  const removeRow = (i: number) =>
    setTable((t) => {
      if (t.rows.length <= 1) return t
      const rows = t.rows.filter((_, k) => k !== i)
      let baseIndex = t.baseIndex
      if (baseIndex === i) {
        baseIndex = Math.max(0, i - 1)
        rows[baseIndex] = { ...rows[baseIndex], steps: emptySteps() }
      } else if (baseIndex > i) baseIndex -= 1
      return { ...t, rows, baseIndex }
    })
  // 换位：基码锚定逻辑码（随行走），不是位置下标；锚位差值恒清 0（不变式）
  const moveRow = (i: number, dir: -1 | 1) =>
    setTable((t) => {
      const j = i + dir
      if (j < 0 || j >= t.rows.length) return t
      const rows = [...t.rows]
      ;[rows[i], rows[j]] = [rows[j], rows[i]]
      const baseIndex = t.baseIndex === i ? j
        : t.baseIndex === j ? i : t.baseIndex
      rows[baseIndex] = { ...rows[baseIndex], steps: emptySteps() }
      return { ...t, rows, baseIndex }
    })

  const renderCell = (row: GradeRow, i: number, k: MeasureKey) => {
    const abs = fmt(absVals[row.label]?.[k] ?? 0)
    return (
      <div className="sr-cell">
        {i === table.baseIndex ? (
          // 基码 = 锚：无档差格（绝对值即面板值，绿字加重）
          <span className="sr-step-empty">—</span>
        ) : (
          <InputNumber size="small" step={0.1} value={row.steps[k]}
                       disabled={thighOff && k === 'thigh'}
                       onChange={(v) => setStep(i, k, v)} />
        )}
        <span className="abs-hint">{abs}</span>
      </div>
    )
  }

  return (
    <Drawer title="推板设置（多码推码）" width={1080} open={open} onClose={onClose}
      footer={
        <div className="sr-footer">
          {errors.length > 0 ? (
            <span className="sr-error">{errors.join('；')}</span>
          ) : (
            <span className="sr-muted">
              导出将保存配置并下载 size_run.dxf（多码单文件，逐码完整重打版）
            </span>
          )}
          <Space>
            <Button onClick={onClose}>取消</Button>
            <Button type="primary" loading={busy} disabled={errors.length > 0}
                    onClick={() => onExport(fromGradeTable(table))}>
              导出推板 DXF
            </Button>
          </Space>
        </div>
      }>
      <div className="sr-hint">
        档差 = 相邻码之差（码序小→大，正号 = 码增大）；基码行是锚——档差
        格为「—」，各码数值取自当前参数面板（只读）。基码上方行录「与更大
        相邻码之差」、下方行录「与上一码之差」；每格下方灰字为换算出的该码
        绝对值。切换基码只换锚点（放码关系不变，数值自动重投影）；插入/
        删除/移动行则档差跟行走。保存时相同档差的相邻码自动合并为档差段。
      </div>
      <div className="sr-toolbar">
        <Space wrap>
          <span>订单号：</span>
          <Input size="small" style={{ width: 180 }} placeholder="noname"
                 value={table.style}
                 onChange={(e) => setTable((t) => ({ ...t, style: e.target.value }))} />
          <span className="sr-muted">（可打印 ASCII，进 DXF 头；留空 = noname）</span>
          {table.rows.length < 2 && (
            <Tag color="orange">仅 1 码：导出等同单码裁片合集</Tag>
          )}
          {thighOff && <Tag>基码未录入大腿围：大腿围档差不生效（全码 0）</Tag>}
        </Space>
      </div>
      <div className="sr-table-wrap">
        <table className="sr-table">
          <thead>
            <tr>
              <th>码</th>
              <th>基码</th>
              {MEASURE_KEYS.map((k) => <th key={k}>{MEASURE_LABELS[k]}</th>)}
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i} className={i === table.baseIndex ? 'sr-base-row' : ''}>
                <td>
                  <Input size="small" className="sr-label" value={row.label}
                         onChange={(e) => setLabel(i, e.target.value)} />
                </td>
                <td>
                  <Radio checked={i === table.baseIndex}
                         onChange={() => setTable((t) => rebaseTable(t, i))} />
                </td>
                {MEASURE_KEYS.map((k) => (
                  <td key={k}>{renderCell(row, i, k)}</td>
                ))}
                <td>
                  <Space size={0}>
                    <Button type="text" size="small" title="上移"
                            icon={<ArrowUpOutlined />} disabled={i === 0}
                            onClick={() => moveRow(i, -1)} />
                    <Button type="text" size="small" title="下移"
                            icon={<ArrowDownOutlined />}
                            disabled={i === table.rows.length - 1}
                            onClick={() => moveRow(i, 1)} />
                    <Button type="text" size="small" title="行下插入码"
                            icon={<PlusOutlined />} onClick={() => insertAfter(i)} />
                    <Button type="text" size="small" title="删除" danger
                            icon={<DeleteOutlined />}
                            disabled={table.rows.length <= 1}
                            onClick={() => removeRow(i)} />
                  </Space>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Drawer>
  )
}
