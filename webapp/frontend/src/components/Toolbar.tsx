import { Button, Space, Alert, Tag } from 'antd'
import { DownloadOutlined, PlayCircleOutlined, UndoOutlined } from '@ant-design/icons'
import type { DownloadKind, IssueDetail } from '../types'

// 两步生成门控（先画后裁）：
//   整版生成 —— 仅互斥裁片生成
//   裁片生成 —— 须整版已生成且未过期（参数一改即过期，先重跑整版）
//   整版/裁片 DXF —— 对应步骤已生成且未过期、无未决错误；下载期间全局串行
//   toml —— 纯参数导出不跑引擎，维持仅 busy 禁用
//   撤销上次拖拽 —— 有拖拽记录且不在 busy 中才可用（单步，回写拖前值并重生成）
// 本地引擎角标：ready=浏览器内计算（拖拽实时）/ http=服务端计算（回退态）
export default function Toolbar({
  sheetBusy, piecesBusy, dlBusy,
  sheetReady, sheetStale, piecesReady, piecesStale,
  errors, warnings, onGenerateSheet, onGeneratePieces, onDownload,
  canUndo, onUndo, engineState,
}: {
  sheetBusy: boolean
  piecesBusy: boolean
  dlBusy: DownloadKind | null
  sheetReady: boolean
  sheetStale: boolean
  piecesReady: boolean
  piecesStale: boolean
  errors: IssueDetail[]
  warnings: { param: string | null; message: string }[]
  onGenerateSheet: () => void
  onGeneratePieces: () => void
  onDownload: (kind: DownloadKind) => void
  canUndo: boolean
  onUndo: () => void
  engineState: 'loading' | 'ready' | 'http'
}) {
  const blocked = errors.length > 0
  const busy = sheetBusy || piecesBusy || dlBusy !== null

  return (
    <div className="toolbar">
      <Space wrap>
        {engineState === 'loading' && <Tag color="processing">本地引擎加载中…</Tag>}
        {engineState === 'ready' && <Tag color="success">本地计算</Tag>}
        {engineState === 'http' && <Tag>服务端计算</Tag>}
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          loading={sheetBusy}
          disabled={piecesBusy}
          onClick={onGenerateSheet}
        >
          整版生成
        </Button>
        <Button
          icon={<PlayCircleOutlined />}
          loading={piecesBusy}
          disabled={!sheetReady || sheetStale || sheetBusy}
          onClick={onGeneratePieces}
        >
          裁片生成
        </Button>
        <Button
          icon={<UndoOutlined />}
          disabled={busy || !canUndo}
          onClick={onUndo}
        >
          撤销上次拖拽
        </Button>
        <Button
          icon={<DownloadOutlined />}
          loading={dlBusy === 'sheetDxf'}
          disabled={busy || !sheetReady || sheetStale || blocked}
          onClick={() => onDownload('sheetDxf')}
        >
          整版 DXF
        </Button>
        <Button
          icon={<DownloadOutlined />}
          loading={dlBusy === 'piecesDxf'}
          disabled={busy || !piecesReady || piecesStale || blocked}
          onClick={() => onDownload('piecesDxf')}
        >
          裁片 DXF
        </Button>
        <Button
          icon={<DownloadOutlined />}
          disabled={busy}
          onClick={() => onDownload('toml')}
        >
          尺寸单 toml
        </Button>
      </Space>
      {errors.length > 0 && (
        <Alert
          className="issue-banner"
          type="error"
          showIcon
          message="参数校验未通过"
          description={
            <ul className="issue-list">
              {errors.map((e, i) => (
                <li key={i}>
                  {e.param ? <code>[{e.param}]</code> : null} {e.message}
                </li>
              ))}
            </ul>
          }
        />
      )}
      {errors.length === 0 && warnings.length > 0 && (
        <Alert
          className="issue-banner"
          type="warning"
          showIcon
          message={
            <ul className="issue-list">
              {warnings.map((w, i) => (
                <li key={i}>
                  {w.param ? <code>[{w.param}]</code> : null} {w.message}
                </li>
              ))}
            </ul>
          }
        />
      )}
    </div>
  )
}
