// 机器排料求解弹窗（二期对接 §10.3.2 US-004；2026-09-22 入口收口：左栏
// 「排料」按钮直达——清单弹窗中转已删，App.startNestFlow 快照产物透传），
// 按 useNestSolve 阶段切三态视图——参数（幅宽/运行模式两项表单，
// localStorage 记忆 + 码号套数表〔2026-09-22：两行表格——首行码号升序 +
// 总计表头、次行每码套数输入 0.5 步进默认 1（最小 0 = 该码不排料）+
// 只读总和；替代原「推板 N 码」
// 小字，码表信息即表格本身，产物缺失/生成中状态提示保留；套数不跨会话
// 记忆、码表内容变化整表重置全 1，提交经 buildMachineConfig multiplySets
// 换算 quantities〕）→ 进度（利用率〔物理口径〕+ 进度条 + per_seed 阶段 +
// 终止 + 「下载状态文件(.msn)」当前最优快照〔三期 US-002〕）→ 结果（摘要行
// + 「下载 PLT」〔US-006：msExport 最小体 {task_id} → blob 落盘，MS 侧缺省
// plt-clean + 表格全算〕+ 「下载状态文件(.msn)」主推 + 引导文案〔三期
// US-002〕+ 布局图 NestPreview 三件套〔US-005〕）。弹窗安全（PRD FR-4）：
// maskClosable/keyboard 全程禁（点遮罩/ESC 均不关闭），唯一出口 = 显式关闭
// 按钮（右上 X / footer 关闭），语义随期别分派 solveCloseBehavior（进度期 =
// 关窗降频 15s 后台守望，可点击左栏「排料」按钮继续查看；结果期 = 停表 +
// best-effort msDeleteTask——由 App 接线执行，关闭前 confirm 二次确认）。
// useNestSolve 实例由 App 持有跨关窗存活，本组件纯视图零状态机。
import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  Alert, Button, InputNumber, Modal, Progress, Select, Space, Spin, Tag,
} from 'antd'
import {
  DownloadOutlined, FileZipOutlined, SendOutlined, StopOutlined,
} from '@ant-design/icons'
import type { MsPerSeed, MsRunMode, NestResult } from '../types'
import type { NestSolveState } from '../hooks/useNestSolve'
import { downloadBlob, downloadBlobBytes, msExport, msStateFile } from '../api'
import { MS_WORKBENCH_URL } from '../msBase'
import {
  DEFAULT_GATE_CM, DEFAULT_RUN_MODE, RUN_MODE_OPTIONS, buildMachineConfig,
} from '../msConfig'
import NestPreview from './NestPreview'

// 参数记忆锚（幅宽/运行模式跨会话记忆；runMode 非法值回默认档——
// RUN_MODE_OPTIONS 演进时不让旧锚把 select 打成空值）
export const NEST_PARAMS_STORAGE_KEY = 'ylpattern.msNestParams.v1'

export interface NestSolveParams {
  gateCm: number
  runMode: MsRunMode
}

export function readNestSolveParams(): NestSolveParams {
  try {
    const raw = localStorage.getItem(NEST_PARAMS_STORAGE_KEY)
    if (raw) {
      const p = JSON.parse(raw)
      if (typeof p?.gateCm === 'number' && Number.isFinite(p.gateCm)
        && p.gateCm > 0
        && RUN_MODE_OPTIONS.some((o) => o.value === p.runMode))
        return { gateCm: p.gateCm, runMode: p.runMode }
    }
  } catch { /* 坏 JSON/存储被禁 → 回默认 */ }
  return { gateCm: DEFAULT_GATE_CM, runMode: DEFAULT_RUN_MODE }
}

function saveNestSolveParams(p: NestSolveParams): void {
  try {
    localStorage.setItem(NEST_PARAMS_STORAGE_KEY, JSON.stringify(p))
  } catch { /* 静默：记忆丢失不阻塞主流程 */ }
}

// .msn 状态文件下载入口（三期机器对接 US-002，PRD FR-4）：三态共用——
// done/stopped 结果区主推（PLT 动作行下）、running 标注「当前最优快照」、
// error 标注「无求解结果，仅含配置」（note 随期别由调用方给文案；结果区
// note 兼容引导文案 ReactNode 带 MS 工作台链接）。可见性 = taskId 存在即可
// 点（MS state-file 只读幂等，任何态下载无副作用、不动终态）；失败 Alert
// 与「下载 PLT」错误链同构（US-001 映射文案经 normalizeMsError 已透出，
// 原样展示不重写，可重按重试）
function MsnDownload({
  taskId, busy, error, note, onDownload,
}: {
  taskId: string | null
  busy: boolean
  error: string | null
  note: ReactNode
  onDownload: () => void
}) {
  return (
    <>
      <div className="nest-result-actions">
        <Button icon={<FileZipOutlined />} loading={busy}
          disabled={taskId === null} onClick={onDownload}>
          下载状态文件(.msn)
        </Button>
        <span className="extract-meta">{note}</span>
      </div>
      {error !== null
        ? <Alert type="error" showIcon
          message={`状态文件下载失败：${error}`}
          style={{ marginTop: 8 }} />
        : null}
    </>
  )
}

// per_seed 阶段标签（seed 完成后入账；current.seed 命中且未杀 = 在跑高亮）
function SeedTags({
  perSeed, currentSeed,
}: { perSeed: MsPerSeed[]; currentSeed: number | null }) {
  if (perSeed.length === 0)
    return <span className="extract-meta">阶段统计启动中…</span>
  return (
    <Space size={[4, 4]} wrap>
      {perSeed.map((s) => {
        const pct = s.best_density !== null
          ? `${Math.round(s.best_density * 10_000) / 100}%` : null
        const color = s.killed ? 'red'
          : currentSeed === s.seed ? 'processing' : 'default'
        return (
          <Tag key={s.seed} color={color}>
            种子{s.seed}
            {s.phase ? `·${s.phase}` : ''}
            {pct !== null ? ` ${pct}` : ''}
            {s.killed ? '·终止' : ''}
          </Tag>
        )
      })}
    </Space>
  )
}

export default function NestSolveModal({
  open, payload, sizes, solve, fetchingPayload, onClose, onSessionReset,
}: {
  open: boolean
  // 会话期的 /api/nest 产物快照（App 的 solveCtx 持有：再次排料重取、
  // error 重试都要用）；null = 无排料产物
  payload: NestResult | null
  // 会话期的推板码表快照（同上：会话期内用户改码表不影响本会话）
  sizes: string[]
  solve: NestSolveState
  // App 侧正在（重新）获取排料产物（dlBusy==='nest'）：参数页 null 占位
  // 文案从「产物缺失」切「正在生成」（2026-09-22 再次排料自动重取）
  fetchingPayload?: boolean
  onClose: () => void
  // 回参数态（再次排料/放弃并重排）：App 侧包装 reset——结果期会话先
  // best-effort DELETE 回收 MS 名额再清锚（否则旧任务泄漏到 TTL）
  onSessionReset: () => void
}) {
  const [params, setParams] = useState<NestSolveParams>(readNestSolveParams)
  const [formError, setFormError] = useState<string | null>(null)
  const [pltBusy, setPltBusy] = useState(false)
  const [pltError, setPltError] = useState<string | null>(null)
  const [msnBusy, setMsnBusy] = useState(false)
  const [msnError, setMsnError] = useState<string | null>(null)

  // 码号套数表（2026-09-22 用户口径）：码号按数字升序展示（solveCtx 码表
  // 快照为用户配置序，MS sizes 顺序无语义）；套数不跨会话记忆——码表内容
  // （join 键）变化时整表重置全 1，同表重开/再次排料保留已输值。0 = 该码
  // 不排料（该码全部裁片数量上送 0，MS demand=0 跳过），全 0 由 buildMachine
  // Config 套数守卫拦下回表单区显示
  const sortedSizes = useMemo(
    () => [...sizes].sort((a, b) => Number(a) - Number(b)), [sizes])
  const sizesKey = sortedSizes.join(',')
  const [sets, setSets] = useState<Record<string, number>>(() =>
    Object.fromEntries(sizes.map((s) => [s, 1])))
  useEffect(() => {
    setSets(Object.fromEntries(
      sizesKey.split(',').filter(Boolean).map((s) => [s, 1])))
  }, [sizesKey])
  const setsTotal = sortedSizes.reduce((acc, s) => acc + (sets[s] ?? 1), 0)
  const setsTotalLabel = Number.isInteger(setsTotal)
    ? String(setsTotal) : setsTotal.toFixed(1)

  // 提交：buildMachineConfig（校验内置，非法输入回表单区显示）→ base64
  // 解码 DXF 字节 → multipart（client_ref 由 hook 层追加）
  const doSubmit = async () => {
    if (payload === null) return
    let config
    try {
      config = buildMachineConfig({
        numMap: payload.numMap, labels: payload.labels, sizes: sortedSizes,
        sets, gateCm: params.gateCm, runMode: params.runMode,
      })
    } catch (e) {
      setFormError((e as Error).message)
      return
    }
    setFormError(null)
    saveNestSolveParams(params)
    // TS 5.7 起 BlobPart 不再接受 ArrayBufferLike（同 downloadBlobBytes
    // 形参注记）：atob/Uint8Array.from 产物显式收窄
    const bytes: Uint8Array<ArrayBuffer> =
      Uint8Array.from(atob(payload.file), (c) => c.charCodeAt(0))
    await solve.submit(
      new Blob([bytes], { type: 'application/dxf' }),
      payload.filename, config)
  }

  // 下载 PLT（US-006）：msExport 请求体仅 {task_id}（零格式/表格参数——
  // MS 侧缺省 plt-clean 毛版 + 唛架表格全算）→ blob → downloadBlob 落盘。
  // PLT 是纯 ASCII HPGL 文本（MS write_marker_plt 末步 encode('ascii')），
  // blob.text() 往返字节安全；失败消息经 normalizeMsError 已是可读中文，
  // 不动终态（弹窗留在结果区，可重按重试）
  const doExportPlt = async () => {
    if (solve.taskId === null) return
    setPltBusy(true)
    setPltError(null)
    try {
      const { blob, filename } = await msExport(solve.taskId)
      downloadBlob(await blob.text(), filename, 'application/plt')
    } catch (e) {
      setPltError((e as Error).message)
    } finally {
      setPltBusy(false)
    }
  }

  // 下载 .msn 状态文件（三期 US-002）：msStateFile 走 YL 代理端点（US-001，
  // MS token 服务端注入）→ blob 字节直存 downloadBlobBytes。落盘刻意不走
  // PLT 的 blob.text() 字符串通道——.msn 是 gzip 二进制，UTF-8 解码往返即
  // 毁字节（PLT 纯 ASCII 才安全）；内容零解析（对前端不透明）。MS 端点只读
  // 幂等：任何态（running 快照 / error 纯配置档）可按，失败不动终态可重试
  const doDownloadMsn = async () => {
    if (solve.taskId === null) return
    setMsnBusy(true)
    setMsnError(null)
    try {
      const { blob, filename } = await msStateFile(solve.taskId)
      const bytes: Uint8Array<ArrayBuffer> =
        new Uint8Array(await blob.arrayBuffer())
      downloadBlobBytes(bytes, filename, 'application/gzip')
    } catch (e) {
      setMsnError((e as Error).message)
    } finally {
      setMsnBusy(false)
    }
  }

  const { phase } = solve
  const pct = solve.totalSec !== null && solve.totalSec > 0
    ? Math.min(100, Math.round((solve.elapsedSec / solve.totalSec) * 100))
    : null
  // best 运行时判空：极早终止（尚无 best_frame 边车）时 MS 载荷可缺 best，
  // 类型不约束运行时形态——渲染侧防御（US-007 冒烟另有兜底断言）
  const bestDensityPct = solve.result !== null && solve.result.best != null
    ? Math.round(solve.result.best.density * 10_000) / 100 : null

  // 三态视图体
  let body: ReactNode
  if (phase === 'idle') {
    body = (
      <div>
        <div className="nest-field">
          <label>幅宽（cm）</label>
          <InputNumber
            min={1} max={1000} step={0.5}
            value={params.gateCm}
            onChange={(v) => {
              setParams((p) => ({ ...p, gateCm: v ?? 0 }))
              setFormError(null)
            }}
            style={{ width: 160 }}
          />
        </div>
        <div className="nest-field">
          <label>运行模式</label>
          <Select
            value={params.runMode}
            onChange={(v) => {
              setParams((p) => ({ ...p, runMode: v }))
              setFormError(null)
            }}
            options={RUN_MODE_OPTIONS.map(
              (o) => ({ value: o.value, label: o.label }))}
            style={{ width: 240 }}
          />
        </div>
        {/* 码号套数表（2026-09-22）：首行码号升序 + 总计表头（首格空），
            次行套数输入（默认 1、0.5 步进、最小 0 = 该码不排料，合法性
            提交时守卫）+ 只读总和。原「推板 N 码」小字退役——码表信息即本表 */}
        <div className="nest-field">
          <label>码号套数</label>
          <div className="nest-sets-wrap">
            <table className="nest-sets-table">
              <tbody>
                <tr>
                  <th aria-label="码号"></th>
                  {sortedSizes.map((s) => <th key={s}>{s}</th>)}
                  <th>总计</th>
                </tr>
                <tr>
                  <th>套数</th>
                  {sortedSizes.map((s) => (
                    <td key={s}>
                      <InputNumber
                        size="small" min={0} step={0.5}
                        value={sets[s] ?? 1}
                        onChange={(v) => {
                          setSets((p) => ({ ...p, [s]: v ?? 0 }))
                          setFormError(null)
                        }}
                        style={{ width: 56 }}
                      />
                    </td>
                  ))}
                  <td className="nest-sets-total">{setsTotalLabel}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        {/* 产物状态提示（码表枚举已由套数表承担，仅在产物缺失/生成中
            出现——否则「开始排料」按钮禁用无解释 */}
        {payload === null
          ? <div className="extract-meta" style={{ marginTop: 4 }}>
              {fetchingPayload
                ? '正在生成排料数据…'
                : '排料产物缺失，请关闭弹窗后重新点击「排料」生成'}
            </div>
          : null}
        {formError !== null
          ? <Alert type="error" showIcon message={formError}
              style={{ marginTop: 12 }} />
          : null}
      </div>
    )
  } else if (phase === 'submitting') {
    body = (
      <div className="nest-progress-head">
        <Spin />
        <span>正在提交排料任务（上传母版 DXF）…</span>
      </div>
    )
  } else if (phase === 'running') {
    body = (
      <div>
        {/* orphan = MS 重启遗留诊断态：宽限窗内继续轮询自然落 error，
            提前给中文说明 + 放弃重排出口（PRD：error/orphan 显错误可重试） */}
        {solve.status?.state === 'orphan' && (
          <Alert
            type="warning" showIcon style={{ marginBottom: 12 }}
            message="MS 排料服务重启，任务遗留恢复中（宽限期内自动判定）"
            description={solve.status.error ?? undefined}
            action={
              <Button size="small" onClick={onSessionReset}>
                放弃并重排
              </Button>
            }
          />
        )}
        <div className="nest-density">
          <span className="nest-density-num">
            {solve.densityPct !== null
              ? `${solve.densityPct.toFixed(2)}%` : '--'}
          </span>
          <span className="extract-meta">当前利用率（物理口径）</span>
        </div>
        {pct !== null
          ? <Progress
              percent={pct}
              format={() => `${solve.elapsedSec}s / ${solve.totalSec}s`} />
          : <div className="extract-meta">
              已运行 {solve.elapsedSec}s（总预算未知）
            </div>}
        <div className="nest-sect">
          <span className="extract-meta">阶段（per_seed）</span>
          <SeedTags
            perSeed={solve.perSeed}
            currentSeed={solve.status?.current?.seed ?? null} />
        </div>
        <div className="extract-meta" style={{ marginTop: 12 }}>
          关闭弹窗后任务在后台继续求解（15s 轮询守望），
          可点击左栏「排料」按钮重新打开查看。
        </div>
        {/* .msn 快照取件（三期 US-002 / PRD FR-4 running 档）：MS 语义 =
            best-so-far 快照（幂等只读，稍后可再取更新版） */}
        <MsnDownload
          taskId={solve.taskId} busy={msnBusy} error={msnError}
          note="当前最优快照（求解继续进行，稍后可再取更新版）"
          onDownload={() => void doDownloadMsn()}
        />
      </div>
    )
  } else if (phase === 'done' || phase === 'stopped') {
    body = (
      <div>
        <Space size={8} style={{ marginBottom: 12 }}>
          {phase === 'done'
            ? <Tag color="success">排料完成</Tag>
            : <Tag color="orange">已终止（取回终止前最优解）</Tag>}
        </Space>
        {solve.result !== null && solve.result.best != null ? (
          <>
            <div className="nest-result-line">
              利用率 {bestDensityPct?.toFixed(2)}%（物理口径）
              {' '}· 种子 {solve.result.best.seed ?? '-'}
              {' '}· 摆放 {solve.result.best.placed_items.length} 片
            </div>
            <div className="nest-result-actions">
              <Button
                icon={<DownloadOutlined />}
                loading={pltBusy}
                disabled={solve.taskId === null}
                onClick={() => void doExportPlt()}>
                下载 PLT
              </Button>
              <span className="extract-meta">
                毛版 + 唛架信息表格（plt-clean，直接交付裁床）
              </span>
            </div>
            {/* .msn 主推入口（三期 US-002）：「一个任务一个取件区」——PLT
                动作行下方；引导文案一处（PRD FR-5）附 MS 工作台入口链接 */}
            <MsnDownload
              taskId={solve.taskId} busy={msnBusy} error={msnError}
              note={<>下载后可在排料系统(MS)『状态恢复』中打开，继续调整
                布局、微调、改数量重解或导出图纸（
                <a href={MS_WORKBENCH_URL} target="_blank" rel="noreferrer">
                  打开 MS 工作台
                </a>）</>}
              onDownload={() => void doDownloadMsn()}
            />
            {pltError !== null
              ? <Alert type="error" showIcon
                message={`PLT 导出失败：${pltError}`}
                style={{ marginTop: 8 }} />
              : null}
            {/* 布局图三件套（US-005）：顶标签 + fit-view 翻转 SVG + 尺码
                图例 + 信息条——不打开 MS 工作台即可核对最终布局 */}
            <NestPreview
              manifest={solve.result.manifest}
              best={solve.result.best}
            />
          </>
        ) : solve.error !== null ? (
          <>
            <Alert type="error" showIcon
              message={`取回结果失败：${solve.error}`} />
            <MsnDownload
              taskId={solve.taskId} busy={msnBusy} error={msnError}
              note="无求解结果，仅含配置"
              onDownload={() => void doDownloadMsn()}
            />
          </>
        ) : (
          <>
            {/* 极早终止（result 在场但无 best 帧）会停在此分支：.msn 纯配置
                档仍可取（PRD FR-4 error 档文案同款） */}
            <div className="extract-meta">正在取回结果…</div>
            <MsnDownload
              taskId={solve.taskId} busy={msnBusy} error={msnError}
              note="无求解结果，仅含配置"
              onDownload={() => void doDownloadMsn()}
            />
          </>
        )}
      </div>
    )
  } else {
    body = (
      <div>
        <Alert
          type="error" showIcon message="排料失败"
          description={solve.error ?? '未知错误'} />
        {/* 提交即失败 taskId 仍空 → 无可下载（MS 侧无任务）；轮询期失败
            （404/连续失联等）taskId 在场 → 纯配置档 .msn 仍可取（FR-4） */}
        {solve.taskId !== null
          ? <MsnDownload
              taskId={solve.taskId} busy={msnBusy} error={msnError}
              note="无求解结果，仅含配置"
              onDownload={() => void doDownloadMsn()} />
          : null}
      </div>
    )
  }

  // footer 随期别：进度期主按钮 = 终止（→ stopped 态可返回）；
  // 结果期 = 再次排料（reset 回参数态，表单记忆保留）
  let footer: ReactNode
  if (phase === 'idle') {
    footer = [
      <Button key="close" onClick={onClose}>关闭</Button>,
      <Button key="go" type="primary" icon={<SendOutlined />}
        disabled={payload === null}
        onClick={() => void doSubmit()}>
        开始排料
      </Button>,
    ]
  } else if (phase === 'submitting') {
    footer = <Button key="close" onClick={onClose}>关闭</Button>
  } else if (phase === 'running') {
    footer = [
      <Button key="close" onClick={onClose}>关闭</Button>,
      <Button key="stop" danger icon={<StopOutlined />}
        onClick={() => solve.stop()}>
        终止
      </Button>,
    ]
  } else if (phase === 'done' || phase === 'stopped') {
    footer = [
      <Button key="again" onClick={onSessionReset}>再次排料</Button>,
      <Button key="close" type="primary" onClick={onClose}>关闭</Button>,
    ]
  } else {
    footer = [
      <Button key="close" onClick={onClose}>关闭</Button>,
      <Button key="retry" type="primary"
        disabled={payload === null}
        onClick={() => void doSubmit()}>
        重试
      </Button>,
    ]
  }

  return (
    <Modal
      title="机器排料"
      open={open}
      onCancel={onClose}
      maskClosable={false}
      keyboard={false}
      width={760}
      footer={footer}
    >
      {body}
    </Modal>
  )
}

