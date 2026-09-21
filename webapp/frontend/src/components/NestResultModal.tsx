// 排料 numMap 弹窗（POST /api/nest 成功后呈现，§10.3.2 一期口径：
// 只拿数据不上传排料系统；不默认下载——DXF 留内存，「下载 DXF」手动取，
// 用户口径 2026-09-20）。二期 US-004 footer 增「发送排料」→ 转入
// NestSolveModal 求解弹窗（nestResult 由 App 快照内存透传）；单码场景
// 由 App 前置拦截（canSendNest=false 禁用 + tooltip 说明，同导出中心
// 推板 DXF「需先配码表」的禁用惯例）。表样式复用提取确认屏的
// extract-table（紧凑清单表），纯函数 nestRows 供测试
import { Button, Modal, Tooltip } from 'antd'
import { DownloadOutlined, SendOutlined } from '@ant-design/icons'
import type { NestResult } from '../types'
import { downloadBlobBytes } from '../api'

export interface NestRow {
  g: string        // g 码（g01…）
  label: string    // 裁片中文名（labels 缺键回退「裁片」）
  qty: number      // 数量（各码相同，numMap 扁平）
}

// numMap + labels -> 行集，g 码数字升序（g01/g02/…/g11）；
// labels 与 numMap 键集理论上同源（后端同一次遍历产出），回退仅兜底
export function nestRows(r: NestResult): NestRow[] {
  return Object.entries(r.numMap)
    .map(([g, qty]) => ({ g, label: r.labels[g] ?? '裁片', qty }))
    .sort((a, b) => gNum(a.g) - gNum(b.g))
}

function gNum(g: string): number {
  const n = parseInt(g.replace(/^g/i, ''), 10)
  return Number.isNaN(n) ? Number.MAX_SAFE_INTEGER : n
}

export default function NestResultModal({
  open, result, onClose, onSendNest, canSendNest = true,
}: {
  open: boolean
  result: NestResult | null
  onClose: () => void
  // 发送排料（二期 US-004）：转入机器排料求解弹窗；canSendNest=false
  //（单码场景）时禁用按钮 + tooltip 拦截说明
  onSendNest?: () => void
  canSendNest?: boolean
}) {
  const rows = result ? nestRows(result) : []
  return (
    <Modal
      title="排料数量清单"
      open={open}
      onCancel={onClose}
      footer={[
        // DXF 不默认下载（留在 nestResult 内存）：想留档手动点此落盘
        result ? (
          <Button
            key="download"
            icon={<DownloadOutlined />}
            onClick={() => {
              const bin = atob(result.file)
              downloadBlobBytes(
                Uint8Array.from(bin, (c) => c.charCodeAt(0)),
                result.filename)
            }}
          >
            下载 DXF
          </Button>
        ) : null,
        // 禁用态 Tooltip 需 span 包裹（disabled 按钮不响应指针事件）
        onSendNest ? (
          <Tooltip
            key="send"
            title={canSendNest
              ? null : '机器排料需要推板多码：请先完成推板设置'}
          >
            <span>
              <Button
                type="primary"
                icon={<SendOutlined />}
                disabled={!canSendNest}
                onClick={onSendNest}
              >
                发送排料
              </Button>
            </span>
          </Tooltip>
        ) : null,
        <Button key="close" onClick={onClose}>
          关闭
        </Button>,
      ]}
      width={420}
    >
      <table className="extract-table">
        <thead>
          <tr><th>编号</th><th>裁片</th><th>数量</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.g}>
              <td>{r.g}</td>
              <td>{r.label}</td>
              <td className="extract-value">{r.qty}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {result && (
        <div className="extract-meta" style={{ marginTop: 8 }}>
          图面编号 = g码-码号，各码数量相同
        </div>
      )}
    </Modal>
  )
}
