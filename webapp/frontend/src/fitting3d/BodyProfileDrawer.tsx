// 体型设置抽屉（仿 SizeRunDrawer 先例，挂 3D 试穿 tab 内）：
// 估计体型（按成衣尺寸反推，随参数联动）/ 内置预设 / 自定义三源单选，
// 选中后可微调数值「保存为自定义」；JSON 导入导出跨设备分享。
// 体型是纯浏览器态：改动只重建人台+重解算，不 bump 参数版本号、
// 不触发整版/裁片 stale（口径 §10.11）。
import { useEffect, useState } from 'react'
import { App, Button, Drawer, Input, InputNumber, Popconfirm, Radio,
  Space, Tag, Upload } from 'antd'
import type { Values } from '../types'
import type { BodyProfile } from './bodyProfile'
import { estimateBody, validateGirths } from './bodyProfile'
import {
  BODY_PRESETS, exportProfiles, findProfile, importProfiles, removeCustom,
  setActive, upsertCustom, type StoreShape,
} from './bodyProfileStore'

const FIELD_DEFS: { key: keyof Pick<BodyProfile, 'waist' | 'hip' | 'thigh' | 'knee'>
  label: string }[] = [
  { key: 'waist', label: '腰围' },
  { key: 'hip', label: '臀围' },
  { key: 'thigh', label: '大腿围' },
  { key: 'knee', label: '膝围' },
]

export default function BodyProfileDrawer({
  open, onClose, store, onChange, measurements,
}: {
  open: boolean
  onClose: () => void
  store: StoreShape
  onChange: (s: StoreShape) => void
  measurements: Values
}) {
  const { message } = App.useApp()
  const estimated = estimateBody({
    waist: Number(measurements.waist ?? 0),
    hip: Number(measurements.hip ?? 0),
    knee: Number(measurements.knee ?? 0),
    thigh: measurements.thigh ? Number(measurements.thigh) : undefined,
  })
  const active = store.activeId === 'estimated'
    ? estimated
    : (findProfile(store, store.activeId) ?? estimated)
  const isCustom = store.customs.some((c) => c.id === active.id)

  const [name, setName] = useState(active.name)
  const [draft, setDraft] = useState({
    waist: active.waist, hip: active.hip,
    thigh: active.thigh ?? 0, knee: active.knee,
  })
  useEffect(() => {
    if (!open) return
    setName(active.name)
    setDraft({
      waist: active.waist, hip: active.hip,
      thigh: active.thigh ?? 0, knee: active.knee,
    })
    // 切换选中/抽屉开合时重置编辑态（估计体型随参数自动刷新）
  }, [open, store.activeId, active.waist, active.hip, active.thigh, active.knee])

  const err = validateGirths(draft)

  const saveCustom = () => {
    const p: BodyProfile = {
      id: isCustom ? active.id : `custom-${Date.now()}`,
      name: name.trim() || '自定义体型',
      waist: draft.waist, hip: draft.hip,
      thigh: draft.thigh > 0 ? draft.thigh : undefined,
      knee: draft.knee,
    }
    onChange(upsertCustom(store, p))
    message.success(`已保存「${p.name}」并启用`)
  }

  const doImport = async (file: File) => {
    try {
      const text = await file.text()
      const { ok, skipped } = importProfiles(text)
      let s = store
      for (const p of ok) {
        // 预设 id 冲突时加前缀防止导入件被内置预设遮蔽
        const id = BODY_PRESETS.some((b) => b.id === p.id)
          ? `import-${p.id}` : p.id
        s = upsertCustom(s, { ...p, id })
      }
      onChange(s)
      message.success(`导入 ${ok.length} 个体型${skipped ? `（跳过非法 ${skipped} 个）` : ''}`)
    } catch (e) {
      message.error(`导入失败：${e instanceof Error ? e.message : e}`)
    }
    return false     // 阻止 antd 自动上传
  }

  const downloadExport = () => {
    const blob = new Blob(
      [exportProfiles([...BODY_PRESETS, ...store.customs])],
      { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'body-profiles.json'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  const row = (p: BodyProfile) => (
    <Radio key={p.id} value={p.id} className="body-radio">
      <span className="body-name">{p.name}</span>
      {p.estimated && <Tag color="orange" className="body-tag">估计值</Tag>}
      <span className="body-girths">
        腰 {p.waist} · 臀 {p.hip}
        {p.thigh ? ` · 腿 ${p.thigh}` : ''} · 膝 {p.knee}
      </span>
    </Radio>
  )

  return (
    <Drawer
      title="体型设置（人台围度）"
      placement="right"
      width={380}
      open={open}
      onClose={onClose}
    >
      <div className="body-hint">
        体型独立于尺寸单：成衣围含松量/调节量，直接当人体围会假紧假松。
        默认按成衣尺寸反推估计值，建议录入真实测量值。
      </div>
      <Radio.Group
        value={store.activeId}
        onChange={(e) => onChange(setActive(store, e.target.value as string))}
        className="body-list"
      >
        {row(estimated)}
        {BODY_PRESETS.map(row)}
        {store.customs.length > 0 && (
          <div className="body-group">自定义</div>
        )}
        {store.customs.map((c) => (
          <div key={c.id} className="body-custom-row">
            {row(c)}
            <Popconfirm title="删除该体型？" onConfirm={() =>
              onChange(removeCustom(store, c.id))}>
              <Button size="small" type="text" danger>删除</Button>
            </Popconfirm>
          </div>
        ))}
      </Radio.Group>

      <div className="body-edit">
        <div className="body-edit-title">
          {isCustom ? '编辑当前体型' : '微调后保存为自定义'}
        </div>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="体型名称"
          size="small"
          className="body-name-input"
        />
        <Space wrap size={[8, 4]}>
          {FIELD_DEFS.map((f) => (
            <label key={f.key} className="body-field">
              {f.label}
              <InputNumber
                size="small"
                min={0}
                value={draft[f.key]}
                onChange={(v) => setDraft((d) => ({ ...d, [f.key]: Number(v ?? 0) }))}
              />
            </label>
          ))}
        </Space>
        {err && <div className="body-err">{err}</div>}
        <Space style={{ marginTop: 8 }}>
          <Button size="small" type="primary" disabled={!!err}
            onClick={saveCustom}>
            {isCustom ? '保存修改' : '保存为自定义'}
          </Button>
          <Button size="small" onClick={() => onChange(setActive(store, 'estimated'))}>
            用估计值
          </Button>
        </Space>
      </div>

      <Space style={{ marginTop: 16 }}>
        <Button size="small" onClick={downloadExport}>导出 JSON</Button>
        <Upload accept=".json,application/json" showUploadList={false}
          beforeUpload={(f) => {
            void doImport(f as File)
            return false
          }}>
          <Button size="small">导入 JSON</Button>
        </Upload>
      </Space>
    </Drawer>
  )
}
