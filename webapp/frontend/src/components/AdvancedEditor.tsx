// 高级编辑工作台（2026-09-11 交互重构，自 PreviewPane 改造）：3D 主视图
// 的 2D 全屏替补——整版拖拽调版（SheetView 把手）+ 逐裁片预览 + 报表。
// 进入时自动补算（sheet 缺失/过期 -> ensureSheet，Spin 兜底）；拖拽回写
// applyAdjust 链路零改动（左栏参数面板保持可见，高亮定位闭环不变）。
// 撤销/裁片生成自旧 Toolbar 收编至此；裁片生成保持先画后裁门控。
// 2026-09-24 工具栏「返回 3D」按钮移除（用户口径）：切视图统一走右栏
// Segmented（高级编辑 | 3D 试穿），工具栏不再带导航。
import { useEffect, useState } from 'react'
import { Button, Empty, Spin, Tabs, Tag, Tooltip } from 'antd'
import {
  ColumnWidthOutlined, PlayCircleOutlined, UndoOutlined, WarningOutlined,
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
  onEnsureSheet, onGeneratePieces, canUndo, onUndo, dragging,
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
  dragging: boolean
}) {
  const [tab, setTab] = useState('sheet')
  // 量取模式位（2026-10-06）：整版视图专属工具态——ESC / 切离整版 tab 即关，
  // SheetView 侧关模式自动清标注；切 3D / 换源经 draftEpoch remount 天然复位
  const [measureMode, setMeasureMode] = useState(false)

  // 进入自动补算：sheet 缺失或参数已改 -> 重跑整版（失败保留 Empty+重试）
  useEffect(() => {
    void onEnsureSheet()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ESC 退出量取（window 级：画布无焦点概念）
  useEffect(() => {
    if (!measureMode) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMeasureMode(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [measureMode])

  const busy = sheetBusy || piecesBusy
  const sheetReady = sheet !== null
  const sheetStaleTip = !dragging && sheetStale
    ? '参数已修改，整版预览已过期；重新「生成」后恢复' : null
  const piecesStaleTip = !dragging && piecesStale
    ? '参数已修改，裁片预览已过期；重新「裁片生成」后恢复' : null

  const items = [
    ...(sheet
      ? [{ key: 'sheet', label: '整版',
          children: (
            <div className="sheet-stage">
              <SheetView
                svg={sheet.data.sheet_svg}
                transform={sheet.data.transform}
                handles={sheet.data.handles}
                schema={schema}
                base={base}
                measureMode={measureMode}
                onApplyAdjust={onApplyAdjust}
                onBeginDrag={onBeginDrag}
                onDragChange={onDragChange}
              />
              {/* 量取入口 = 整版右上固定悬浮（2026-10-06 用户口径，原工具栏位移入；
                  随 sheet tab 存在才渲染，无需 disabled）；对齐 SheetPreview
                  smart-zoom-bar 悬浮先例（absolute + z-index:2） */}
              <div className="measure-fab">
                <Tooltip title="点两个点测直线距离，靠近要素点自动吸附；右键取消当前标注；ESC 退出">
                  <Button
                    size="small"
                    icon={<ColumnWidthOutlined />}
                    type={measureMode ? 'primary' : 'default'}
                    onClick={() => setMeasureMode((v) => !v)}
                  >
                    量取
                  </Button>
                </Tooltip>
              </div>
            </div>
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
            onChange={(k) => {
              setTab(k)
              // 量取只属于整版视图：切离即关（antd Tabs 保面板挂载，需显式关）
              if (k !== 'sheet') setMeasureMode(false)
            }}
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
