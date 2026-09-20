import { useEffect, useState } from 'react'
import { App as AntApp, Alert, Button, ConfigProvider, Segmented, Tag } from 'antd'
import {
  DownloadOutlined, FileAddOutlined, LayoutOutlined, PlayCircleOutlined,
} from '@ant-design/icons'
import zhCN from 'antd/locale/zh_CN'
import InitGate from './components/InitGate'
import ParamPanel from './components/ParamPanel'
import CoreParams from './components/CoreParams'
import AdvancedEditor from './components/AdvancedEditor'
import ExportCenter from './components/ExportCenter'
import SizeRunDrawer from './components/SizeRunDrawer'
import ExtractWizard from './components/ExtractWizard'
import NestResultModal from './components/NestResultModal'
import Fitting3DView from './fitting3d/Fitting3DView'
import type { IssueDetail, SizeRunSpec, Values } from './types'
import { useDraft } from './hooks/useDraft'
import './styles.css'

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
  // 提取向导弹层开合（2026-09-19 起唯一入口 = 启动选择层「从照片提取」，
  // header 按钮已随入口收口删除；取消自然退回选择层）
  const [extractOpen, setExtractOpen] = useState(false)
  // 导出中心弹层开合（勾选产物 -> 逐项串行下载）
  const [exportOpen, setExportOpen] = useState(false)
  // 排料 numMap 弹窗开合：产物到达即开（download('nest') 成功置
  // nestResult），关窗即清产物（不留快照，重点击重取）
  const [nestOpen, setNestOpen] = useState(false)
  useEffect(() => {
    if (d.nestResult !== null) setNestOpen(true)
  }, [d.nestResult])
  // 右栏主视图切换（2026-09-19 用户口径「默认是整版效果」）：'2d' 高级
  // 编辑（整版调版工作台，默认）↔ '3d' 3D 试穿——Fitting3DView 切入才
  // 挂载，首挂自动试穿在那一刻才发；编辑器内「返回」= 切回 3D
  const [viewMode, setViewMode] = useState<'2d' | '3d'>('2d')
  // 左栏参数分层：核心参数（白名单 17 控件）/ 全部参数（原全量面板）
  const [paramTab, setParamTab] = useState<'core' | 'all'>('core')
  // 启动初始化选择层（2026-09-19）：initialized 单向闩锁——首次选择前
  // 工作台不挂载（Fitting3DView 不发隐藏首挂请求），中途重开不卸载
  // （3D 场景不重建、fitting 快照不丢）；initOpen 遮罩可重开（header 新建）
  const [initialized, setInitialized] = useState(false)
  const [initOpen, setInitOpen] = useState(true)
  // 整体换源纪元：loadValues 整体替换参数时 +1，作 AdvancedEditor 的
  // remount key——中途经「新建」重开选择层时工作台不卸载，编辑器的挂载期
  // ensureSheet 不会重发，整版会停在旧参数（2026-09-20 修）；换源即视为
  // 重新进入编辑器，补算/tab/缩放全部随新草稿重置
  const [draftEpoch, setDraftEpoch] = useState(0)
  const finishInit = () => {
    setInitialized(true)
    setInitOpen(false)
  }
  // 选择层「载入即完成」：模板/空白默认共用（第三参语义各自成立——
  // 模板带码表、出厂 fresh start 显式 null）
  const initLoadValues = (m: Values, o: Values, sr?: SizeRunSpec | null) => {
    d.loadValues(m, o, sr)
    setDraftEpoch((e) => e + 1)
    finishInit()
  }

  return (
    <div className="app">
      {initialized && (
      <>
      <header className="app-header">
        <h1>YLPattern 牛仔裤打版</h1>
        {/* 新建：重开启动选择层（继续上次/模板/提取/出厂），参数可整体换源。
            模板/照片提取 2026-09-19 起不再各设 header 入口——参数来源选择
            统一收口到选择层，避免同一动作两个入口 */}
        <Button
          size="small"
          icon={<FileAddOutlined />}
          onClick={() => setInitOpen(true)}
        >
          新建
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
            {/* 生成 = 重算当前右栏视图（2026-09-20 回归左栏；3D 侧栏
                「重新生成」按钮随之收口删除）：2D 刷新整版（ensureSheet
                过期才重跑、新鲜直用），3D 重发 fitting */}
            <Button
              icon={<PlayCircleOutlined />}
              loading={viewMode === '3d' ? d.fittingBusy : d.sheetBusy}
              onClick={() => {
                if (viewMode === '3d') void d.generateFitting()
                else void d.ensureSheet()
              }}
            >
              生成
            </Button>
            <Button
              icon={<DownloadOutlined />}
              onClick={() => setExportOpen(true)}
            >
              导出
            </Button>
            {/* 排料对接（§10.3.2）：POST /api/nest 出带 g 码编号 DXF +
                numMap——下载文件 + 弹窗展示数量；失败入全局 IssueStrip */}
            <Button
              icon={<LayoutOutlined />}
              loading={d.dlBusy === 'nest'}
              onClick={() => void d.download('nest').catch(() => {})}
            >
              排料
            </Button>
          </div>
        </aside>
        <section className="right-pane">
          <div className="right-mode-bar">
            <Segmented
              value={viewMode}
              onChange={(v) => setViewMode(v as '2d' | '3d')}
              options={[
                { value: '2d', label: '高级编辑' },
                { value: '3d', label: '3D 试穿' },
              ]}
            />
          </div>
          <div className="right-mode-body">
            {viewMode === '2d' ? (
              <AdvancedEditor
                key={draftEpoch}
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
                onExit={() => setViewMode('3d')}
                dragging={dragging}
              />
            ) : (
              <Fitting3DView
                fitting={d.fitting}
                fittingStale={d.fittingStale}
                fittingBusy={d.fittingBusy}
                onGenerateFitting={() => void d.generateFitting()}
              />
            )}
          </div>
        </section>
      </main>
      </>
      )}
      {/* 启动/重开选择层：工作台之上遮罩（zIndex 900，向导 Modal 盖其上） */}
      {initOpen && (
        <InitGate
          hasSavedDraft={d.hasSavedDraft}
          initialized={initialized}
          onContinue={finishInit}
          onLoadValues={initLoadValues}
          onOpenExtract={() => setExtractOpen(true)}
        />
      )}
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
      <NestResultModal
        open={nestOpen}
        result={d.nestResult}
        onClose={() => {
          setNestOpen(false)
          d.clearNestResult()
        }}
      />
      <ExtractWizard
        open={extractOpen}
        onClose={() => setExtractOpen(false)}
        schema={d.schema}
        onConfirm={(m, o) => {
          // 第三参必须显式传：loadValues 缺省 null 会清空推板码表
          d.loadValues(m, o, d.sizeRun)
          // 换源纪元 +1（同 initLoadValues：确认预填 = 整体换参数）
          setDraftEpoch((e) => e + 1)
          // 确认即完成初始化关层（中途经「新建」重开时 initialized 已真，
          // finishInit 无副作用）
          finishInit()
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
