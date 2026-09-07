import { Button, Space, Alert, Tag, Tooltip } from 'antd'
import {
  DownloadOutlined, PlayCircleOutlined, SettingOutlined, UndoOutlined, WarningOutlined,
} from '@ant-design/icons'
import type { DownloadKind, IssueDetail } from '../types'

// 过期角标（2026-09-07 用户口径：弃 PreviewPane 常驻横幅——显隐推挤绘图区、
// 常驻空行都不佳，提示移到按钮上）：因过期被禁用/门控的按钮右上角挂 ⚠，
// 悬停 Tooltip 看原因；角标绝对定位不占布局宽度，显隐不推动相邻按钮。
// 禁用态 button 不触发鼠标事件，Tooltip 须包一层 span（antd 官方口径）。
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

// 两步生成门控（先画后裁）：
//   整版生成 —— 仅互斥裁片生成
//   裁片生成 —— 须整版已生成且未过期（参数一改即过期，先重跑整版）
//   整版/裁片/推板 DXF —— 对应步骤已生成且未过期、无未决错误；下载期间全局串行
//   推板 DXF —— 门控同裁片 DXF（先画后裁两步口径）；未配置时点击转为打开
//   推板设置抽屉（首跑零摩擦）；「推板设置」齿轮常开不受门控
//   toml —— 纯参数导出不跑引擎，维持仅 busy 禁用
//   撤销上次拖拽 —— 有拖拽记录且不在 busy 中才可用（单步，回写拖前值并重生成）
// 本地引擎角标：ready=浏览器内计算（拖拽实时）/ http=服务端计算（回退态）
export default function Toolbar({
  sheetBusy, piecesBusy, dlBusy,
  sheetReady, sheetStale, piecesReady, piecesStale,
  errors, warnings, onGenerateSheet, onGeneratePieces, onDownload,
  canUndo, onUndo, engineState, dragging,
  sizeRunConfigured, onOpenSizeRun,
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
  dragging: boolean
  sizeRunConfigured: boolean
  onOpenSizeRun: () => void
}) {
  const blocked = errors.length > 0
  const busy = sheetBusy || piecesBusy || dlBusy !== null
  // 拖拽进行中暂隐角标：每次回写都重生成、松手后必然同步，拖拽中闪无意义
  const sheetStaleTip = !dragging && sheetStale
    ? '参数已修改，整版预览已过期；重新「整版生成」后恢复'
    : null
  const piecesStaleTip = !dragging && piecesStale
    ? '参数已修改，裁片预览已过期；重新「裁片生成」后恢复'
    : null

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
        <StaleFlag tip={sheetStaleTip}>
          <Button
            icon={<PlayCircleOutlined />}
            loading={piecesBusy}
            disabled={!sheetReady || sheetStale || sheetBusy}
            onClick={onGeneratePieces}
          >
            裁片生成
          </Button>
        </StaleFlag>
        <Button
          icon={<UndoOutlined />}
          disabled={busy || !canUndo}
          onClick={onUndo}
        >
          撤销上次拖拽
        </Button>
        <StaleFlag tip={sheetStaleTip}>
          <Button
            icon={<DownloadOutlined />}
            loading={dlBusy === 'sheetDxf'}
            disabled={busy || !sheetReady || sheetStale || blocked}
            onClick={() => onDownload('sheetDxf')}
          >
            整版 DXF
          </Button>
        </StaleFlag>
        <StaleFlag tip={piecesStaleTip}>
          <Button
            icon={<DownloadOutlined />}
            loading={dlBusy === 'piecesDxf'}
            disabled={busy || !piecesReady || piecesStale || blocked}
            onClick={() => onDownload('piecesDxf')}
          >
            裁片 DXF
          </Button>
        </StaleFlag>
        <StaleFlag tip={piecesStaleTip}>
          <Button
            icon={<DownloadOutlined />}
            loading={dlBusy === 'sizeRunDxf'}
            disabled={busy || !piecesReady || piecesStale || blocked}
            onClick={sizeRunConfigured
              ? () => onDownload('sizeRunDxf')
              : onOpenSizeRun}
          >
            推板 DXF{sizeRunConfigured ? '' : '（未配置）'}
          </Button>
        </StaleFlag>
        <Button icon={<SettingOutlined />} onClick={onOpenSizeRun}>
          推板设置
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
