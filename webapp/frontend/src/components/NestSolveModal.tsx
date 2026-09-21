// 机器排料求解弹窗（二期对接 §10.3.2 US-004）：NestResultModal「发送排料」
// 转入，按 useNestSolve 阶段切三态视图——参数（幅宽/运行模式两项表单，
// localStorage 记忆）→ 进度（利用率〔物理口径〕+ 进度条 + per_seed 阶段 +
// 终止）→ 结果（摘要行 + 布局图 NestPreview 三件套〔US-005〕；「下载
// PLT」是 US-006 增量）。弹窗安全（PRD FR-4）：maskClosable/keyboard 全程禁（点遮罩/ESC
// 均不关闭），唯一出口 = 显式关闭按钮（右上 X / footer 关闭），语义随期别
// 分派 solveCloseBehavior（进度期 = 关窗降频 15s 后台守望，可从左栏
// 「排料进度」继续查看；结果期 = 停表 + best-effort msDeleteTask——由 App
// 接线执行）。useNestSolve 实例由 App 持有跨关窗存活，本组件纯视图零状态机。
import { useState } from 'react'
import type { ReactNode } from 'react'
import {
  Alert, Button, InputNumber, Modal, Progress, Select, Space, Spin, Tag,
} from 'antd'
import { SendOutlined, StopOutlined } from '@ant-design/icons'
import type { MsPerSeed, MsRunMode, NestResult } from '../types'
import type { NestSolveState } from '../hooks/useNestSolve'
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
  open, payload, sizes, solve, onClose, onSessionReset,
}: {
  open: boolean
  // 发送排料时刻的 /api/nest 产物快照（App 持有：NestResultModal 关窗即清
  // useDraft.nestResult，重试要用所以不直接消费它）；null = 无排料产物
  payload: NestResult | null
  // 发送时刻的推板码表快照（同上：会话期内用户改码表不影响本会话）
  sizes: string[]
  solve: NestSolveState
  onClose: () => void
  // 回参数态（再次排料/放弃并重排）：App 侧包装 reset——结果期会话先
  // best-effort DELETE 回收 MS 名额再清锚（否则旧任务泄漏到 TTL）
  onSessionReset: () => void
}) {
  const [params, setParams] = useState<NestSolveParams>(readNestSolveParams)
  const [formError, setFormError] = useState<string | null>(null)

  // 提交：buildMachineConfig（校验内置，非法输入回表单区显示）→ base64
  // 解码 DXF 字节 → multipart（client_ref 由 hook 层追加）
  const doSubmit = async () => {
    if (payload === null) return
    let config
    try {
      config = buildMachineConfig({
        numMap: payload.numMap, labels: payload.labels, sizes,
        gateCm: params.gateCm, runMode: params.runMode,
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
        <div className="extract-meta" style={{ marginTop: 4 }}>
          推板 {sizes.length} 码：{sizes.join(' / ')}
          {payload ? null : '（排料产物缺失，请重新点击「排料」生成）'}
        </div>
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
          可从左栏「排料进度」重新打开查看。
        </div>
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
            {/* 布局图三件套（US-005）：顶标签 + fit-view 翻转 SVG + 尺码
                图例 + 信息条——不打开 MS 工作台即可核对最终布局 */}
            <NestPreview
              manifest={solve.result.manifest}
              best={solve.result.best}
            />
          </>
        ) : solve.error !== null ? (
          <Alert type="error" showIcon
            message={`取回结果失败：${solve.error}`} />
        ) : (
          <div className="extract-meta">正在取回结果…</div>
        )}
      </div>
    )
  } else {
    body = (
      <Alert
        type="error" showIcon message="排料失败"
        description={solve.error ?? '未知错误'} />
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

