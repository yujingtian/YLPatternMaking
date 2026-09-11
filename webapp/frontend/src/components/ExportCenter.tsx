// 导出中心（2026-09-11 交互重构）：勾选产物 -> 逐项串行下载。
// - SVG/报表：内存快照直存（downloadBlob，本地引擎可出零后端）；
//   快照缺失/过期时先 ensureSheet/ensurePieces 自动补算（保先画后裁序）
// - DXF/TOML：走后端（ezdxf 不进浏览器），服务端按当前参数重算，
//   天然最新、不受本地快照新鲜度门控（口径见决策日志 2026-09-11）
// - 推板 DXF 未配置码表：行内「去配置」转推板设置抽屉（复用旧转跳模式）
// 队列逐项落账（spinner/✓/✗，单项失败不中断后续项）
import { useEffect, useState } from 'react'
import {
  App, Button, Checkbox, Modal, Space, Tag, Tooltip,
} from 'antd'
import {
  CheckCircleOutlined, CloseCircleOutlined, DownloadOutlined,
  LoadingOutlined, SettingOutlined,
} from '@ant-design/icons'
import type {
  DownloadKind, IssueDetail, PiecesResult, SheetResult, SizeRunSpec, Snapshot,
} from '../types'
import { downloadBlob } from '../api'

type ItemKey = 'sheetSvg' | 'pieceSvg' | 'report' | 'sheetDxf' | 'piecesDxf'
  | 'sizeRunDxf' | 'toml'
type ItemStatus = 'idle' | 'running' | 'done' | 'failed'

interface ItemDef {
  key: ItemKey
  label: string
  desc: string
}

const ITEMS: ItemDef[] = [
  { key: 'sheetSvg', label: '整版 SVG', desc: '内存直存；过期自动先重算' },
  { key: 'pieceSvg', label: '裁片 SVG', desc: '逐片下载 piece_<名称>.svg' },
  { key: 'report', label: '打版报表', desc: 'report.txt（坐标+依据溯源）' },
  { key: 'sheetDxf', label: '整版 DXF', desc: 'R12/mm，服务端重算导出' },
  { key: 'piecesDxf', label: '裁片 DXF', desc: '全部裁片平铺合一张' },
  { key: 'sizeRunDxf', label: '推板 DXF', desc: '多码合集，需先配码表' },
  { key: 'toml', label: '尺寸单 TOML', desc: '可直接喂 CLI --size' },
]

// 多文件连发间隔：浏览器（尤其 Chrome）对同 tick 多个 a[download] 会
// 合并拦截，间隔 150ms 走「允许下载多个文件」授权一次通过
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

export default function ExportCenter({
  open, onClose, sheet, pieces, sheetStale, piecesStale, sizeRun, busy,
  errors, ensureSheet, ensurePieces, download, onOpenSizeRun,
}: {
  open: boolean
  onClose: () => void
  sheet: Snapshot<SheetResult> | null
  pieces: Snapshot<PiecesResult> | null
  sheetStale: boolean
  piecesStale: boolean
  sizeRun: SizeRunSpec | null
  busy: boolean
  errors: IssueDetail[]
  ensureSheet: () => Promise<Snapshot<SheetResult> | null>
  ensurePieces: () => Promise<Snapshot<PiecesResult> | null>
  download: (kind: DownloadKind, opts?: { sizeRun?: SizeRunSpec | null }) =>
    Promise<void>
  onOpenSizeRun: () => void
}) {
  const { message } = App.useApp()
  const [checked, setChecked] = useState<ItemKey[]>([])
  const [status, setStatus] = useState<Partial<Record<ItemKey, ItemStatus>>>({})
  const [running, setRunning] = useState(false)

  // 每次打开重置队列状态（勾选保留，便于重试同清单）
  useEffect(() => {
    if (open) setStatus({})
  }, [open])

  const toggle = (k: ItemKey) => {
    setChecked((cs) => cs.includes(k) ? cs.filter((x) => x !== k) : [...cs, k])
  }

  const runItem = async (key: ItemKey) => {
    if (key === 'sheetSvg') {
      const s = await ensureSheet()
      if (!s) throw new Error('整版生成失败（见左侧错误提示）')
      downloadBlob(s.data.sheet_svg, 'sheet.svg', 'image/svg+xml')
    } else if (key === 'pieceSvg') {
      const p = await ensurePieces()
      if (!p) throw new Error('裁片生成失败（见左侧错误提示）')
      for (const piece of p.data.pieces) {
        downloadBlob(piece.svg, `piece_${piece.key}.svg`, 'image/svg+xml')
        await sleep(150)
      }
    } else if (key === 'report') {
      const s = await ensureSheet()
      if (!s) throw new Error('整版生成失败（见左侧错误提示）')
      downloadBlob(s.data.report, 'report.txt')
    } else if (key === 'sizeRunDxf') {
      if (!sizeRun) throw new Error('推板未配置（请先完成推板设置）')
      await download('sizeRunDxf')
    } else {
      await download(key)
    }
  }

  const runQueue = async () => {
    const keys = [...checked]
    setRunning(true)
    let failed = 0
    for (const k of keys) {
      setStatus((s) => ({ ...s, [k]: 'running' }))
      try {
        await runItem(k)
        setStatus((s) => ({ ...s, [k]: 'done' }))
      } catch {
        failed += 1
        setStatus((s) => ({ ...s, [k]: 'failed' }))
      }
    }
    setRunning(false)
    if (failed === 0) message.success(`已下载 ${keys.length} 项产物`)
    else message.warning(`${keys.length - failed} 项成功，${failed} 项失败（详见左侧错误提示）`)
  }

  const statusIcon = (k: ItemKey) => {
    const st = status[k]
    if (st === 'running') return <LoadingOutlined style={{ color: '#2c6e49' }} />
    if (st === 'done') return <CheckCircleOutlined style={{ color: '#52c41a' }} />
    if (st === 'failed') return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
    return null
  }

  const blocked = errors.length > 0

  return (
    <Modal
      title="导出"
      open={open}
      onCancel={running ? undefined : onClose}
      width={520}
      footer={
        <Space style={{ display: 'flex', justifyContent: 'space-between' }}>
          <Button size="small" icon={<SettingOutlined />}
                  onClick={onOpenSizeRun} disabled={running}>
            推板设置…
          </Button>
          <Space>
            <Button onClick={onClose} disabled={running}>关闭</Button>
            <Tooltip title={blocked ? '参数校验未通过，先修正左侧错误' : null}>
              <Button type="primary" icon={<DownloadOutlined />}
                      loading={running}
                      disabled={blocked || checked.length === 0}
                      onClick={() => void runQueue()}>
                下载所选（{checked.length}）
              </Button>
            </Tooltip>
          </Space>
        </Space>
      }
    >
      <div className="ec-hint">
        {busy && '引擎计算中，勾选项将排队执行；'}
        DXF/TOML 由服务端按当前参数重算导出；SVG/报表取本地快照、
        过期时自动先重新生成。
      </div>
      <div className="ec-list">
        {ITEMS.map((it) => {
          const needSizeRun = it.key === 'sizeRunDxf' && !sizeRun
          const st = status[it.key] ?? 'idle'
          return (
            <div key={it.key} className={`ec-item${st === 'failed' ? ' ec-failed' : ''}`}>
              <Checkbox
                checked={checked.includes(it.key)}
                disabled={(running || needSizeRun) && st !== 'done'}
                onChange={() => toggle(it.key)}
              >
                <span className="ec-label">{it.label}</span>
              </Checkbox>
              <span className="ec-desc">
                {it.key === 'sheetSvg' && sheetStale && sheet
                  ? <Tag color="orange">过期，下载时自动重算</Tag> : null}
                {it.key === 'pieceSvg' && piecesStale && pieces
                  ? <Tag color="orange">过期，下载时自动重算</Tag> : null}
                {it.key === 'sizeRunDxf' && sizeRun
                  ? <Tag color="green">{sizeRun.order.length} 码 · 基码 {sizeRun.base}</Tag>
                  : null}
                {it.desc}
              </span>
              {it.key === 'sizeRunDxf' && !sizeRun && (
                <Button size="small" type="link" onClick={onOpenSizeRun}
                        disabled={running}>
                  去配置
                </Button>
              )}
              <span className="ec-status">{statusIcon(it.key)}</span>
            </div>
          )
        })}
      </div>
    </Modal>
  )
}
