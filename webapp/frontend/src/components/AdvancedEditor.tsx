// 高级编辑工作台（2026-09-11 交互重构，自 PreviewPane 改造）：3D 主视图
// 的 2D 全屏替补——整版拖拽调版（SheetView 把手）+ 逐裁片预览 + 报表。
// 进入时自动补算（sheet 缺失/过期 -> ensureSheet，Spin 兜底）；拖拽回写
// applyAdjust 链路零改动（左栏参数面板保持可见，高亮定位闭环不变）。
// 撤销/裁片生成自旧 Toolbar 收编至此；裁片生成保持先画后裁门控。
import { useEffect, useState } from 'react'
import { Button, Empty, Spin, Tabs, Tag, Tooltip } from 'antd'
import {
  ArrowLeftOutlined, PlayCircleOutlined, UndoOutlined, WarningOutlined,
} from '@ant-design/icons'
import type {
  DraftPayload, PiecesResult, Schema, SheetResult, Snapshot,
} from '../types'
import SheetView from './SheetView'

// 裁片 SVG 为 Y 向上坐标（已由 exporters 翻转适配 viewBox），直接内联渲染
function SvgView({ svg }: { svg: string }) {
  return <div className="svg-view" dangerouslySetInnerHTML={{ __html: svg }} />
}

// 过期角标（旧 Toolbar StaleFlag 迁入）：禁用按钮右上角挂 ⚠，悬停看原因；
// 角标绝对定位不占布局宽度（antd 口径：禁用 button 不触发鼠标事件，
// Tooltip 须包一层 span）
function StaleFlag({ tip, children }: { tip: string | null; children: JSX.Element }) {
  if (!tip) return children
  return (
    <Tooltip title={tip}>
      <span className="stale-tip-wrap">
        {children}
        <WarningOutlined className="stale-flag" />
      </span>
    </Tooltip>
  )
}

export default function AdvancedEditor({
  sheet, pieces, schema, base, onApplyAdjust, onBeginDrag, onDragChange,
  sheetBusy, piecesBusy, sheetStale, piecesStale,
  onEnsureSheet, onGeneratePieces, canUndo, onUndo, onExit, dragging,
}: {
  sheet: Snapshot<SheetResult> | null
  pieces: Snapshot<PiecesResult> | null
  schema: Schema | null
  base: DraftPayload
  onApplyAdjust: (param: string, value: number, base: DraftPayload) => void
  onBeginDrag: (param: string, prevValue: number) => void
  onDragChange: (dragging: boolean) => void
  sheetBusy: boolean
  piecesBusy: boolean
  sheetStale: boolean
  piecesStale: boolean
  onEnsureSheet: () => Promise<Snapshot<SheetResult> | null>
  onGeneratePieces: () => void
  canUndo: boolean
  onUndo: () => void
  onExit: () => void
  dragging: boolean
}) {
  const [tab, setTab] = useState('sheet')

  // 进入自动补算：sheet 缺失或参数已改 -> 重跑整版（失败保留 Empty+重试）
  useEffect(() => {
    void onEnsureSheet()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const busy = sheetBusy || piecesBusy
  const sheetReady = sheet !== null
  const sheetStaleTip = !dragging && sheetStale
    ? '参数已修改，正在自动重新生成整版…' : null
  const piecesStaleTip = !dragging && piecesStale
    ? '参数已修改，裁片预览已过期；重新「裁片生成」后恢复' : null

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
    <div className="adv-editor">
      <div className="adv-toolbar">
        <Button size="small" icon={<ArrowLeftOutlined />} onClick={onExit}>
          返回 3D
        </Button>
        <StaleFlag tip={sheetStaleTip}>
          <Button
            size="small"
            icon={<PlayCircleOutlined />}
            loading={piecesBusy}
            disabled={busy || !sheetReady || sheetStale}
            onClick={onGeneratePieces}
          >
            裁片生成
          </Button>
        </StaleFlag>
        <Button
          size="small"
          icon={<UndoOutlined />}
          disabled={busy || !canUndo}
          onClick={onUndo}
        >
          撤销上次拖拽
        </Button>
        {piecesStaleTip && (
          <Tooltip title={piecesStaleTip}>
            <Tag color="orange">裁片已过期</Tag>
          </Tooltip>
        )}
      </div>
      {(!sheet && sheetBusy) ? (
        <div className="preview-empty">
          <Spin tip="正在重新打版…" />
        </div>
      ) : !sheet ? (
        <div className="preview-empty">
          <Empty description="整版未生成（参数校验未通过或生成失败）">
            <Button size="small" type="primary" onClick={() => void onEnsureSheet()}>
              重新生成
            </Button>
          </Empty>
        </div>
      ) : (
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
          <details className="report">
            <summary>打版报表（元素坐标 + 依据溯源）</summary>
            <pre>{sheet.data.report}</pre>
          </details>
        </div>
      )}
    </div>
  )
}
