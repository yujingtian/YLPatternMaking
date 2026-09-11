import { useState } from 'react'
import { App as AntApp, Alert, Button, ConfigProvider, Segmented, Tag, Tooltip } from 'antd'
import {
  CameraOutlined, DownloadOutlined, EditOutlined, PlayCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import zhCN from 'antd/locale/zh_CN'
import TemplatePicker from './components/TemplatePicker'
import ParamPanel from './components/ParamPanel'
import CoreParams from './components/CoreParams'
import AdvancedEditor from './components/AdvancedEditor'
import ExportCenter from './components/ExportCenter'
import SizeRunDrawer from './components/SizeRunDrawer'
import ExtractWizard from './components/ExtractWizard'
import Fitting3DView from './fitting3d/Fitting3DView'
import type { IssueDetail } from './types'
import { useDraft } from './hooks/useDraft'
import './styles.css'

// 过期角标（旧 Toolbar 口径迁入）：目标按钮右上角挂 ⚠、悬停看原因，
// 绝对定位不占布局宽度；禁用 button 不触发鼠标事件，Tooltip 须包 span
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

// 校验错误/警告条（旧 Toolbar Alert 迁入左栏，紧凑化）：错误优先全量
// 展开给明细，无错误才显警告；都没有不占位
function IssueStrip({
  errors, warnings,
}: {
  errors: IssueDetail[]
  warnings: { param: string | null; message: string }[]
}) {
  if (errors.length > 0) {
    return (
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
    )
  }
  if (warnings.length > 0) {
    return (
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
    )
  }
  return null
}

function DraftApp() {
  const d = useDraft()
  // 拖拽进行中：暂隐"已过期"角标（每次回写都重生成，松手后必然同步）
  const [dragging, setDragging] = useState(false)
  // 推板设置抽屉开合（导出中心「推板设置」/未配置引导均转到此处）
  const [sizeRunOpen, setSizeRunOpen] = useState(false)
  // 提取向导弹层开合（与模板载入同属"填表单"动作，入口在 header）
  const [extractOpen, setExtractOpen] = useState(false)
  // 导出中心弹层开合（勾选产物 -> 逐项串行下载）
  const [exportOpen, setExportOpen] = useState(false)
  // 高级编辑模式：右栏 3D 主视图整体替换为 2D 工作台，退出回到 3D
  const [advanced, setAdvanced] = useState(false)
  // 左栏参数分层：核心参数（白名单 17 控件）/ 全部参数（原全量面板）
  const [paramTab, setParamTab] = useState<'core' | 'all'>('core')

  const generateTip = !dragging && d.fittingStale
    ? '参数已修改，点击重新生成 3D 试穿' : null

  return (
    <div className="app">
      <header className="app-header">
        <h1>YLPattern 牛仔裤打版</h1>
        <TemplatePicker onLoad={d.loadValues} />
        <Button
          size="small"
          icon={<CameraOutlined />}
          onClick={() => setExtractOpen(true)}
        >
          从照片提取
        </Button>
      </header>
      <main className="app-main">
        <aside className="left-panel">
          <div className="left-head">
            <Segmented
              block
              value={paramTab}
              onChange={(v) => setParamTab(v as 'core' | 'all')}
              options={[
                { value: 'core', label: '核心参数' },
                { value: 'all', label: '全部参数' },
              ]}
            />
          </div>
          <div className="left-body">
            {d.schema ? (
              paramTab === 'core' ? (
                <CoreParams
                  sections={d.schema.sections}
                  measurements={d.measurements}
                  options={d.options}
                  errors={d.errors}
                  onMeasurement={d.setMeasurement}
                  onOption={d.setOption}
                  onSeed={d.seedShape}
                  highlight={d.adjustInfo}
                />
              ) : (
                <ParamPanel
                  sections={d.schema.sections}
                  measurements={d.measurements}
                  options={d.options}
                  errors={d.errors}
                  onMeasurement={d.setMeasurement}
                  onOption={d.setOption}
                  onSeed={d.seedShape}
                  highlight={d.adjustInfo}
                />
              )
            ) : (
              <div className="preview-empty">schema 加载中…</div>
            )}
          </div>
          <IssueStrip errors={d.errors} warnings={d.warnings} />
          <div className="action-bar">
            {d.engineState === 'loading' && <Tag color="processing">引擎…</Tag>}
            {d.engineState === 'ready' && <Tag color="success">本地计算</Tag>}
            {d.engineState === 'http' && <Tag>服务端计算</Tag>}
            <StaleFlag tip={generateTip}>
              <Button
                type="primary"
                className="btn-grow"
                icon={<PlayCircleOutlined />}
                loading={d.fittingBusy}
                disabled={d.errors.length > 0}
                onClick={() => void d.generateFitting()}
              >
                生成
              </Button>
            </StaleFlag>
            <Button
              icon={<DownloadOutlined />}
              onClick={() => setExportOpen(true)}
            >
              导出
            </Button>
            <Button
              icon={<EditOutlined />}
              disabled={advanced}
              onClick={() => setAdvanced(true)}
            >
              高级编辑
            </Button>
          </div>
        </aside>
        <section className="right-pane">
          {advanced ? (
            <AdvancedEditor
              sheet={d.sheet}
              pieces={d.pieces}
              schema={d.schema}
              base={{ measurements: d.measurements, options: d.options }}
              onApplyAdjust={(p, v, b) => void d.applyAdjust(p, v, b)}
              onBeginDrag={d.beginDrag}
              onDragChange={setDragging}
              sheetBusy={d.sheetBusy}
              piecesBusy={d.piecesBusy}
              sheetStale={d.sheetStale}
              piecesStale={d.piecesStale}
              onEnsureSheet={d.ensureSheet}
              onGeneratePieces={() => void d.generatePieces()}
              canUndo={d.lastDrag !== null}
              onUndo={d.undoLastDrag}
              onExit={() => setAdvanced(false)}
              dragging={dragging}
            />
          ) : (
            <Fitting3DView
              fitting={d.fitting}
              fittingStale={d.fittingStale}
              fittingBusy={d.fittingBusy}
              onGenerateFitting={() => void d.generateFitting()}
              measurements={d.measurements}
            />
          )}
        </section>
      </main>
      <ExportCenter
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        sheet={d.sheet}
        pieces={d.pieces}
        sheetStale={d.sheetStale}
        piecesStale={d.piecesStale}
        sizeRun={d.sizeRun}
        busy={d.sheetBusy || d.piecesBusy || d.dlBusy !== null}
        errors={d.errors}
        ensureSheet={d.ensureSheet}
        ensurePieces={d.ensurePieces}
        download={(k, opts) => d.download(k, opts)}
        onOpenSizeRun={() => setSizeRunOpen(true)}
      />
      <SizeRunDrawer
        open={sizeRunOpen}
        onClose={() => setSizeRunOpen(false)}
        spec={d.sizeRun}
        measurements={d.measurements}
        defaultLabel={String(d.options.size_label ?? '-')}
        busy={d.dlBusy === 'sizeRunDxf'}
        onExport={(s) => {
          d.setSizeRun(s)
          // 显式覆盖参传 spec：保存与下载同 tick，规避闭包旧值竞态。
          // download 失败会重抛（导出中心按项落账），此处 catch 吞掉：
          // 失败留在抽屉（错误已入全局 IssueStrip），成功才关抽屉
          void d.download('sizeRunDxf', { sizeRun: s })
            .then(() => setSizeRunOpen(false))
            .catch(() => {})
        }}
      />
      <ExtractWizard
        open={extractOpen}
        onClose={() => setExtractOpen(false)}
        schema={d.schema}
        onConfirm={(m, o) => {
          // 第三参必须显式传：loadValues 缺省 null 会清空推板码表
          d.loadValues(m, o, d.sizeRun)
        }}
      />
    </div>
  )
}

export default function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{ token: { colorPrimary: '#2c6e49', borderRadius: 4 } }}
    >
      <AntApp>
        <DraftApp />
      </AntApp>
    </ConfigProvider>
  )
}
