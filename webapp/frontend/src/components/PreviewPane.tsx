import { useState } from 'react'
import { Alert, Empty, Tabs } from 'antd'
import type {
  DraftPayload, PiecesResult, Schema, SheetResult, Snapshot,
} from '../types'
import SheetView from './SheetView'

// 裁片 SVG 为 Y 向上坐标（已由 exporters 翻转适配 viewBox），直接内联渲染
function SvgView({ svg }: { svg: string }) {
  return <div className="svg-view" dangerouslySetInnerHTML={{ __html: svg }} />
}

// 双快照预览：整版 tab 在前、裁片 tabs 随裁片生成追加；
// 参数修改后预览保留、上方横幅标"已过期"（下载门控见 Toolbar）；
// 拖拽调版期间横幅暂隐（每次回写都重生成，松手后快照必然同步）
export default function PreviewPane({
  sheet, pieces, sheetStale, piecesStale, dragging,
  schema, base, onApplyAdjust, onBeginDrag, onDragChange,
}: {
  sheet: Snapshot<SheetResult> | null
  pieces: Snapshot<PiecesResult> | null
  sheetStale: boolean
  piecesStale: boolean
  dragging: boolean
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

  const staleMsg = !dragging &&
    (sheetStale && piecesStale
      ? '参数已修改，整版与裁片预览均已过期；重新生成对应步骤后才能下载 DXF'
      : sheetStale
        ? '参数已修改，整版预览已过期；重新「整版生成」后才能下载整版 DXF'
        : piecesStale
          ? '参数已修改，裁片预览已过期；重新「裁片生成」后才能下载裁片 DXF'
          : null)

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
      {staleMsg && (
        <Alert className="stale-banner" type="warning" showIcon message={staleMsg} />
      )}
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
