import { useState } from 'react'
import { Empty, Tabs } from 'antd'
import type { DraftResult } from '../types'

// 整版 SVG 为 Y 向上坐标（已由 exporters 翻转适配 viewBox），直接内联渲染
function SvgView({ svg }: { svg: string }) {
  return <div className="svg-view" dangerouslySetInnerHTML={{ __html: svg }} />
}

export default function PreviewPane({ result }: { result: DraftResult | null }) {
  const [tab, setTab] = useState('sheet')

  if (!result) {
    return (
      <div className="preview-empty">
        <Empty description="填写参数后点击「生成」" />
      </div>
    )
  }

  const items = [
    { key: 'sheet', label: '整版', children: <SvgView svg={result.sheet_svg} /> },
    ...result.pieces.map((p) => ({
      key: p.key,
      label: p.name,
      children: <SvgView svg={p.svg} />,
    })),
  ]
  // 参数变化后重生成：原 tab 对应裁片可能已被关闭，回退整版
  const active = items.some((i) => i.key === tab) ? tab : 'sheet'

  return (
    <div className="preview-pane">
      <Tabs
        activeKey={active}
        onChange={setTab}
        size="small"
        type="card"
        items={items}
        className="preview-tabs"
      />
      {result.skips.length > 0 && (
        <details className="skips">
          <summary>未生成的裁片（{result.skips.length}）</summary>
          <ul>
            {result.skips.map((s) => <li key={s}>{s}</li>)}
          </ul>
        </details>
      )}
      <details className="report">
        <summary>打版报表（元素坐标 + 依据溯源）</summary>
        <pre>{result.report}</pre>
      </details>
    </div>
  )
}
