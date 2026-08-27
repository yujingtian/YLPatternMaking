import { useEffect, useState } from 'react'
import { App as AntApp, Select } from 'antd'
import type { SizeRunSpec, Values } from '../types'
import { fetchTemplateDetail, fetchTemplates } from '../api'
import { normalizeSizeRun } from '../sizeRun'

// 模板载入：measurements/options 一键填充 + [size_run] 段透传为推板配置
// （后端 /api/templates/{name} 已返回 size_run；enabled=false 也预填——
// 抽屉存在性即配置态，保存时恒写 true）。模板带逐码覆盖 sizes.X 时
// 丢弃（v1 不支持）并 message 提示
export default function TemplatePicker({ onLoad }: {
  onLoad: (m: Values, o: Values, sizeRun?: SizeRunSpec | null) => void
}) {
  const { message } = AntApp.useApp()
  const [templates, setTemplates] = useState<{ name: string; file: string }[]>([])
  const [current, setCurrent] = useState<string | null>(null)

  useEffect(() => {
    fetchTemplates().then(setTemplates).catch(() => setTemplates([]))
  }, [])

  async function pick(file: string) {
    setCurrent(file)
    const detail = await fetchTemplateDetail(file)
    const { spec, droppedOverrides } = normalizeSizeRun(detail.size_run)
    onLoad(detail.measurements, detail.options, spec)
    if (droppedOverrides) {
      message.warning('模板含逐码覆盖 [size_run.sizes.X]，暂不支持，已忽略')
    }
  }

  return (
    <span className="template-picker">
      款式模板：
      <Select
        size="small"
        style={{ minWidth: 200 }}
        placeholder="选择模板载入"
        value={current}
        options={templates.map((t) => ({ value: t.file, label: t.name }))}
        onChange={(v) => void pick(v)}
      />
    </span>
  )
}
