import { useState } from 'react'
import { Empty, Tabs } from 'antd'
import type {
  DraftPayload, PiecesResult, Schema, SheetResult, Snapshot,
} from '../types'
import SheetView from './SheetView'

// 裁片 SVG 为 Y 向上坐标（已由 exporters 翻转适配 viewBox），直接内联渲染
function SvgView({ svg }: { svg: string }) {
  return <div className="svg-view" dangerouslySetInnerHTML={{ __html: svg }} />
}

// 双快照预览：整版 tab 在前、裁片 tabs 随裁片生成追加；
// 参数修改后预览保留，过期提示移至 Toolbar 按钮角标 + Tooltip
// （2026-09-07 用户口径：弃预览区横幅——显隐推挤绘图区/常驻空行都不可取）
export default function PreviewPane({
  sheet, pieces, schema, base, onApplyAdjust, onBeginDrag, onDragChange,
}: {
  sheet: Snapshot<SheetResult> | null
  pieces: Snapshot<PiecesResult> | null
  schema: Schema | null
  base: DraftPayload
  onApplyAdjust: (param: string, value: number, base: DraftPayload) => void
  onBeginDrag: (param: string, prevValue: number) => void
  onDragChange: (dragging: boolean) => void
}) {
  const [tab, setTab] = useState('sheet')

  if (!sheet && !pieces) {
    return (
      <div className="preview-empty">
        <Empty description="填写参数后点击「整版生成」" />
      </div>
    )
  }

  const items = [
    ...(sheet
      ? [{ key: 'sheet', label: '整版',
          children: (
            <SheetView
              svg={sheet.data.sheet_svg}
              transform={sheet.data.transform}
              handles={sheet.data.handles}
              schema={schema}
              base={base}
              onApplyAdjust={onApplyAdjust}
              onBeginDrag={onBeginDrag}
              onDragChange={onDragChange}
            />
          ) }]
      : []),
    ...(pieces
      ? pieces.data.pieces.map((p) => ({
          key: p.key,
          label: p.name,
          children: <SvgView svg={p.svg} />,
        }))
      : []),
  ]
  // 重新生成后原 tab 对应裁片可能已不在清单（开关变化），回退首个 tab
  const active = items.some((i) => i.key === tab) ? tab : (items[0]?.key ?? '')

  return (
    <div className="preview-pane">
      <Tabs
        activeKey={active}
        onChange={setTab}
        size="small"
        type="card"
        items={items}
        className="preview-tabs"
      />
      {pieces && pieces.data.skips.length > 0 && (
        <details className="skips">
          <summary>未生成的裁片（{pieces.data.skips.length}）</summary>
          <ul>
            {pieces.data.skips.map((s) => <li key={s}>{s}</li>)}
          </ul>
        </details>
      )}
      {sheet && (
        <details className="report">
          <summary>打版报表（元素坐标 + 依据溯源）</summary>
          <pre>{sheet.data.report}</pre>
        </details>
      )}
    </div>
  )
}
