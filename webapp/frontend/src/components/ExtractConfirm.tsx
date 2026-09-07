// 提取确认屏（一期前端接线 §10.9）：清单式确认——逐键白话名/值/来源徽章/
// 置信度（<0.7 且非默认标黄）/evidence 溯源（Popover）；issues 置顶、款式
// 选项与探针/评分折叠。确认动作回调 App 层 loadValues（覆盖全部参数，
// 须显式传 d.sizeRun 保留推板配置）。
import { useMemo } from 'react'
import { Alert, Button, Collapse, Popover, Space, Tag } from 'antd'
import {
  buildLabelMap, isLowConfidence, SOURCE_BADGE, toConfirmRows,
} from '../extractPayload'
import type { ExtractResponse, Schema } from '../types'

function SourceTag({ source }: { source: string }) {
  return <Tag color={SOURCE_BADGE[source] ?? 'default'}>{source}</Tag>
}

function EvidencePopover({ evidence, children }: {
  evidence: string; children: React.ReactNode
}) {
  if (!evidence) return <>{children}</>
  return (
    <Popover
      trigger="click"
      title="判定依据"
      content={<div className="extract-evidence">{evidence}</div>}
    >
      {children}
    </Popover>
  )
}

function RowsTable({ rows }: { rows: ReturnType<typeof toConfirmRows>['measures'] }) {
  return (
    <table className="extract-table">
      <thead>
        <tr>
          <th>参数</th><th>值</th><th>来源</th><th>置信度</th><th>依据</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.key} className={isLowConfidence(r.meta) ? 'low-conf' : ''}>
            <td>{r.label}</td>
            <td className="extract-value">{r.value}</td>
            <td>{r.meta ? <SourceTag source={r.meta.source} /> : '—'}</td>
            <td>
              {r.meta
                ? (r.meta.confidence >= 0
                    ? r.meta.confidence.toFixed(2)
                    : '—')
                : '—'}
              {isLowConfidence(r.meta) && <Tag color="warning">低置信</Tag>}
            </td>
            <td>
              {r.meta?.evidence
                ? <EvidencePopover evidence={r.meta.evidence}>
                    <Button type="link" size="small">查看</Button>
                  </EvidencePopover>
                : '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function ExtractConfirm({ result, schema, onBack, onConfirm }: {
  result: ExtractResponse
  schema: Schema | null
  onBack: () => void
  onConfirm: () => void
}) {
  const labelMap = useMemo(() => buildLabelMap(schema), [schema])
  const rows = useMemo(() => toConfirmRows(result, labelMap), [result, labelMap])

  return (
    <div className="extract-confirm">
      <Alert
        type="warning"
        showIcon
        message="确认后将覆盖当前表单的全部尺寸与选项参数（推板码表保留）"
        style={{ marginBottom: 12 }}
      />
      {result.issues.length > 0 && (
        <Space direction="vertical" style={{ width: '100%', marginBottom: 12 }}>
          {result.issues.map((i, idx) => (
            <Alert
              key={idx}
              type={i.level === 'error' ? 'error' : 'warning'}
              showIcon
              message={`${labelMap.get(i.param) ?? i.param}：${i.message}`}
            />
          ))}
        </Space>
      )}
      <div className="extract-meta">
        模型 {result.model} · 照片 {result.photo_count} 张
      </div>

      <RowsTable rows={rows.measures} />

      <Collapse
        size="small"
        style={{ marginTop: 12 }}
        items={[{
          key: 'options',
          label: `款式选项（${rows.options.length} 项，多为档位表/款式默认）`,
          children: <RowsTable rows={rows.options} />,
        }, {
          key: 'probe',
          label: `探针 ${result.probe.stage}${result.probe.ok ? '（通过）' : '（未通过）'}`,
          children: (
            <pre className="extract-probe-log">
              {result.probe.log.join('\n') || '（无日志）'}
            </pre>
          ),
        }, ...(result.score.length > 0 ? [{
          key: 'score',
          label: `合理性评分（${result.score.length} 项）`,
          children: (
            <table className="extract-table">
              <thead>
                <tr><th>特征</th><th>值</th><th>区间</th><th>判定</th></tr>
              </thead>
              <tbody>
                {result.score.map((s, i) => (
                  <tr key={i}>
                    <td>{s.feature}</td>
                    <td className="extract-value">{s.value}</td>
                    <td>{s.band}</td>
                    <td>{s.verdict}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ),
        }] : [])]}
      />

      <div className="extract-actions">
        <Button onClick={onBack}>返回修改</Button>
        <Button type="primary" onClick={onConfirm}>确认并预填表单</Button>
      </div>
    </div>
  )
}
