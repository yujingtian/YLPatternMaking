import { useEffect, useState } from 'react'
import { Select } from 'antd'
import type { Values } from '../types'
import { fetchTemplateDetail, fetchTemplates } from '../api'

export default function TemplatePicker({ onLoad }: {
  onLoad: (m: Values, o: Values) => void
}) {
  const [templates, setTemplates] = useState<{ name: string; file: string }[]>([])
  const [current, setCurrent] = useState<string | null>(null)

  useEffect(() => {
    fetchTemplates().then(setTemplates).catch(() => setTemplates([]))
  }, [])

  async function pick(file: string) {
    setCurrent(file)
    const detail = await fetchTemplateDetail(file)
    onLoad(detail.measurements, detail.options)
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
