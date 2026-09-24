import { useEffect, useState } from 'react'
import { App as AntApp, Alert, Button, ConfigProvider, Segmented, Tag } from 'antd'
import {
  CheckCircleOutlined, DownloadOutlined, FileAddOutlined, LayoutOutlined,
  LoadingOutlined, PlayCircleOutlined, WarningOutlined,
} from '@ant-design/icons'
import zhCN from 'antd/locale/zh_CN'
import InitGate from './components/InitGate'
import ParamPanel from './components/ParamPanel'
import CoreParams from './components/CoreParams'
import AdvancedEditor from './components/AdvancedEditor'
import ExportCenter from './components/ExportCenter'
import SizeRunDrawer from './components/SizeRunDrawer'
import SmartDraftView from './components/SmartDraftView'
import NestSolveModal from './components/NestSolveModal'
import Fitting3DView from './fitting3d/Fitting3DView'
import type {
  IssueDetail, NestResult, SizeRunSpec, Values,
} from './types'
import { nestRows, useDraft } from './hooks/useDraft'
import { useSmartDraft } from './hooks/useSmartDraft'
import {
  readStoredMsTask, solveCloseBehavior, useNestSolve,
} from './hooks/useNestSolve'
import { msDeleteTask } from './api'
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
  // antd 上下文版 message/modal（ExportCenter 同款先例）：单码拦截提示、
  // 结果期关闭 confirm
  const { message, modal } = AntApp.useApp()
  // 拖拽进行中：暂隐"已过期"角标（每次回写都重生成，松手后必然同步）
  const [dragging, setDragging] = useState(false)
  // 推板设置抽屉开合（导出中心「推板设置」/未配置引导均转到此处）
  const [sizeRunOpen, setSizeRunOpen] = useState(false)
  // 智能打版独立界面（2026-09-21 二期；2026-09-24 弹层升全幅「左对话
  // 右可缩放整版预览」界面）：状态在 useSmartDraft（挂本层，界面关开
  // 不丢）；入口 = 启动选择层「智能打版」，返回自然退回选择层
  const chat = useSmartDraft()
  // 导出中心弹层开合（勾选产物 -> 逐项串行下载）
  const [exportOpen, setExportOpen] = useState(false)
  // 机器排料求解会话（二期 US-004；2026-09-22 入口收口：清单弹窗删除，
  // 左栏「排料」按钮经 startNestFlow 直达本弹窗参数页）：useNestSolve
  // 实例由 App 持有——跨弹窗开合存活（进度期关窗转 15s 后台守望，任务
  // 不中断）；solveCtx = 会话期产物 + 码表快照（error 重试/再次排料重取
  // 要用所以 App 持有；会话期内改码表不串台）
  const solve = useNestSolve()
  const [solveOpen, setSolveOpen] = useState(false)
  const [solveCtx, setSolveCtx] =
    useState<{ payload: NestResult; sizes: string[] } | null>(null)
  // 「继续查看」刷新恢复：锚在 → 后台慢档 attach（首拍轮询自对齐真实终
  // 态）；弹窗开合同步双档轮询（开 = 在视 2s / 关 = 降频 15s 即时重排）
  useEffect(() => {
    const stored = readStoredMsTask()
    if (stored) solve.attach(stored.taskId)
    // 仅挂载时执行（attach/setVisible 均 useCallback 稳定引用）
  }, [])
  useEffect(() => { solve.setVisible(solveOpen) }, [solveOpen])
  // 排料入口（2026-09-22 收口）：单码拦截（机器排料需推板多码）→
  // POST /api/nest 取产物 → console 清单打印（排查口径）→ 快照 solveCtx
  // → 直达求解弹窗参数页。码表先取局部快照（await 后闭包值不漂移）；
  // 失败已入 IssueStrip，关窗露出左栏错误条（「再次排料」入口下弹窗
  // 可能开着）；undefined = dlBusy 串行闸让位（其它下载在跑），静默
  const startNestFlow = async () => {
    const sr = d.sizeRun
    if (sr === null) {
      message.warning('机器排料需要推板多码：请先完成推板设置')
      return
    }
    try {
      const res = await d.download('nest')
      if (!res) return
      console.log(`[nest] 排料产物 ${res.filename}（码表 ${sr.order.join('/')}）`)
      console.table(nestRows(res))
      setSolveCtx({ payload: res, sizes: sr.order })
      setSolveOpen(true)
    } catch {
      setSolveOpen(false)
    }
  }
  // 求解弹窗显式关闭（唯一出口）语义分派（solveCloseBehavior）：
  // 进度期 = 关窗降频后台守望（task_id 已存锚，左栏「排料」按钮可重开）；
  // 结果期 = 先 confirm 二次确认（关闭即清空——防误关丢 3min~2h 求解
  // 成果，2026-09-22 用户口径），确认后停表清锚 + best-effort
  // msDeleteTask 回收 MS 会话名额（失败静默，MS 侧 TTL+7 天兜底）；
  // idle/error = 纯重置关窗（无结果可丢，不确认）
  const doCloseSolveModal = () => {
    const behavior = solveCloseBehavior(solve.phase)
    setSolveOpen(false)
    if (behavior.background) return
    const id = solve.taskId
    solve.reset()
    setSolveCtx(null)
    if (behavior.deleteTask && id !== null)
      void msDeleteTask(id).catch(() => {})
  }
  const closeSolveModal = () => {
    if (solve.phase === 'done' || solve.phase === 'stopped') {
      modal.confirm({
        title: '关闭后排料结果将清空',
        content: '关闭弹窗会结束本次排料会话并回收排料服务任务；'
          + '如需保留结果，请先下载 PLT 或状态文件(.msn)。',
        okText: '确定关闭',
        cancelText: '再看看',
        onOk: doCloseSolveModal,
      })
      return
    }
    doCloseSolveModal()
  }
  // 回参数态（再次排料/放弃并重排）：结果期会话先回收 MS 名额再清锚
  //（running 家族〔orphan 放弃〕不删——在飞任务删不掉，交 TTL 兜底）；
  // 产物快照随之重取（刷新恢复的会话 solveCtx 已丢，不重取会卡「产物
  // 缺失」；单码被清则拦截不动会话，2026-09-22）
  const resetSolveSession = () => {
    if (d.sizeRun === null) {
      message.warning('机器排料需要推板多码：请先完成推板设置')
      return
    }
    const terminal = solve.phase === 'done' || solve.phase === 'stopped'
    const id = solve.taskId
    solve.reset()
    setSolveCtx(null)
    if (terminal && id !== null) void msDeleteTask(id).catch(() => {})
    void startNestFlow()
  }
  // 排料按钮状态投影（2026-09-22 收口，原「排料进度」按钮并入）：在飞 =
  // submitting/running（文案「排料中」，点击重开看进度不重新取数）；有
  // 会话 = taskId 非空且非在飞（后台守望跑完的 done/stopped 或 error，
  // 点击重开回看）；否则空闲（点击走 startNestFlow 新流程）
  const nestInFlight = solve.phase === 'submitting' || solve.phase === 'running'
  const nestSessionHeld = solve.taskId !== null && !nestInFlight
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
  // 换源收口（模板/空白默认/智能打版确认共用）：整体替换参数 + 状态
  // 还原——loadValues 清旧产物快照、draftEpoch +1 重挂编辑器（挂载期
  // ensureSheet 按新参数重发）、右栏切回高级编辑（2026-09-23 用户口径：
  // 换源后停在 3D 观感仍是上一份配置）
  const switchDraftSource = (m: Values, o: Values, sr?: SizeRunSpec | null) => {
    d.loadValues(m, o, sr)
    setDraftEpoch((e) => e + 1)
    setViewMode('2d')
    finishInit()
  }

  return (
    <div className="app">
      {initialized && (
      <>
      <header className="app-header">
        <h1>YLPattern 牛仔裤打版</h1>
        {/* 新建：重开启动选择层（继续上次/模板/智能打版/出厂），参数可整体
            换源。模板/智能打版 2026-09-19 起不再各设 header 入口——参数来源
            选择统一收口到选择层，避免同一动作两个入口 */}
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
            {/* 排料对接（§10.3.2）：状态化单入口（2026-09-22 收口，原
                「排料进度」按钮并入）——空闲 = 取产物直达求解弹窗参数页
                （清单数据 console 打印）；在飞 = 「排料中」，点击重开弹窗
                看进度（刻意不用 loading prop——loading 禁点，与「可点击
                查看进度」诉求冲突；取数窗口另由 dlBusy 转圈防重点）；
                有会话 = 点击重开回看结果/错误 */}
            <Button
              icon={nestInFlight ? <LoadingOutlined spin />
                : nestSessionHeld ? (solve.phase === 'error'
                  ? <WarningOutlined /> : <CheckCircleOutlined />)
                : <LayoutOutlined />}
              loading={d.dlBusy === 'nest'}
              onClick={() => {
                if (nestInFlight || nestSessionHeld) setSolveOpen(true)
                else void startNestFlow()
              }}
            >
              {nestInFlight ? '排料中' : '排料'}
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
      {/* 启动/重开选择层：工作台之上遮罩（zIndex 900，对话 Modal 盖其上） */}
      {initOpen && (
        <InitGate
          hasSavedDraft={d.hasSavedDraft}
          initialized={initialized}
          onContinue={finishInit}
          onLoadValues={switchDraftSource}
          onOpenChat={() => chat.setOpen(true)}
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
      <NestSolveModal
        open={solveOpen}
        payload={solveCtx?.payload ?? null}
        sizes={solveCtx?.sizes ?? []}
        solve={solve}
        fetchingPayload={d.dlBusy === 'nest'}
        onClose={closeSolveModal}
        onSessionReset={resetSolveSession}
      />
      {/* 独立界面按需挂载（chat.open 门控）：卸载不清状态——会话/照片/
          消息全在 useSmartDraft（App 层持有），重开即续 */}
      {chat.open && (
        <SmartDraftView
          chat={chat}
          onConfirm={(m, o) => {
            // 第三参必须显式传：loadValues 缺省 null 会清空推板码表；
            // switchDraftSource 内已 finishInit（重开时 initialized 已真，
            // 无副作用），确认即完成初始化关层
            switchDraftSource(m, o, d.sizeRun)
            chat.setOpen(false)
          }}
        />
      )}
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
