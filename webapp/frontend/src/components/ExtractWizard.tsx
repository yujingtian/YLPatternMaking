// 提取向导弹层（一期前端接线 §10.9）：输入（描述 + 照片[≤4，前端压缩]）
// -> 同步等待（锁关 + 秒表，VLM 可能数十秒）-> 确认屏（ExtractConfirm）。
// 照片随请求 multipart 直传（agent 契约零改动）；agent 未启动禁提交但
// 不禁输入；vlm 未配置仍可纯描述提取（零模型调用路径）。
import { useEffect, useRef, useState } from 'react'
import {
  Alert, App as AntApp, Button, Collapse, Input, Modal, Spin, Upload,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import type { Schema, Values } from '../types'
import { useExtract } from '../hooks/useExtract'
import ExtractConfirm from './ExtractConfirm'
import { compressImage, MAX_PHOTOS, validatePhotoFile } from '../imageCompress'

interface PhotoItem {
  uid: string
  name: string
  url: string    // 本地预览 objectURL（随 remove/unmount 释放）
  file: File
}

export default function ExtractWizard({ open, onClose, schema, onConfirm }: {
  open: boolean
  onClose: () => void
  schema: Schema | null
  onConfirm: (m: Values, o: Values) => void
}) {
  const { message } = AntApp.useApp()
  const ex = useExtract()
  const [describe, setDescribe] = useState('')
  const [thinking, setThinking] = useState('')
  const [photos, setPhotos] = useState<PhotoItem[]>([])
  // 弹层打开时重置会话（含健康预检）；关闭即弃（一期不做重开恢复）
  useEffect(() => {
    if (open) ex.reset()
  }, [open])   // eslint-disable-line react-hooks/exhaustive-deps
  const urlsRef = useRef<string[]>([])
  useEffect(() => () => {
    for (const u of urlsRef.current) URL.revokeObjectURL(u)
  }, [])

  function addPhoto(item: PhotoItem) {
    urlsRef.current.push(item.url)
    setPhotos((prev) => [...prev, item])
  }

  function removePhoto(uid: string) {
    setPhotos((prev) => {
      const hit = prev.find((p) => p.uid === uid)
      if (hit) {
        URL.revokeObjectURL(hit.url)
        urlsRef.current = urlsRef.current.filter((u) => u !== hit.url)
      }
      return prev.filter((p) => p.uid !== uid)
    })
  }

  // 校验 + 压缩后塞进受控列表；一律 LIST_IGNORE（antd 自身不入列）
  async function beforeUpload(file: File) {
    const err = validatePhotoFile(file)
    if (err) {
      message.error(err)
      return Upload.LIST_IGNORE
    }
    if (photos.length >= MAX_PHOTOS) {
      message.error(`最多 ${MAX_PHOTOS} 张照片`)
      return Upload.LIST_IGNORE
    }
    const out = await compressImage(file)   // 解码失败内部降级直传
    addPhoto({
      uid: `${file.name}-${file.size}-${Date.now()}`,
      name: out.name, url: URL.createObjectURL(out), file: out,
    })
    return Upload.LIST_IGNORE
  }

  const healthUnknown = ex.health === null && !ex.healthLoading
  const canSubmit = describe.trim().length > 0 && ex.health !== null
      && ex.stage === 'input'

  return (
    <Modal
      open={open}
      title="从照片提取参数"
      width={720}
      footer={null}
      destroyOnHidden
      maskClosable={false}
      closable={ex.stage !== 'submitting'}
      keyboard={ex.stage !== 'submitting'}
      onCancel={onClose}
    >
      {ex.stage === 'confirm' && ex.result !== null ? (
        <ExtractConfirm
          result={ex.result}
          schema={schema}
          onBack={ex.backToInput}
          onConfirm={() => {
            const payload = ex.confirmPrefill()
            if (payload) onConfirm(payload.measurements, payload.options)
            onClose()
          }}
        />
      ) : ex.stage === 'submitting' ? (
        <div className="extract-waiting">
          <Spin size="large" />
          <div>正在提取…（含照片解析可能需要数十秒，请勿关闭）</div>
          <div className="extract-elapsed">已耗时 {ex.elapsed}s</div>
        </div>
      ) : (
        <div className="extract-input">
          {healthUnknown && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              message="agent 服务未启动或不可达（默认 http://localhost:8001）——无法提取"
            />
          )}
          {ex.health !== null && !ex.health.vlm_configured && (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message="VLM 未配置（vlm.toml）：照片不会被解析，仅从描述文字提取——纯描述也能全中"
            />
          )}
          {ex.error && (
            <Alert
              type="error"
              showIcon
              style={{ marginBottom: 12 }}
              message={ex.error.message}
              description={ex.error.issues && ex.error.issues.length > 0
                ? `缺少：${ex.error.issues.map((i) => i.param).join('、')}`
                : undefined}
            />
          )}
          <div className="extract-field">
            <div className="extract-field-label">款式描述（必填，尺寸直接写数字）</div>
            <Input.TextArea
              rows={4}
              maxLength={2000}
              value={describe}
              onChange={(e) => setDescribe(e.target.value)}
              placeholder={'例：女款高腰小脚牛仔裤，腰围 74 臀围 91 膝围 44 '
                + '脚口 34 前浪 25 后浪 33 裤长 102 大腿围 56'}
            />
          </div>
          <div className="extract-field">
            <div className="extract-field-label">
              照片（可选，最多 {MAX_PHOTOS} 张，前后片各一效果最好；自动压缩后上传）
            </div>
            <Upload
              listType="picture-card"
              accept=".jpg,.jpeg,.png,.webp,.bmp,.gif"
              fileList={photos}
              beforeUpload={(f) => void beforeUpload(f)}
              onRemove={(f) => removePhoto(f.uid)}
            >
              {photos.length < MAX_PHOTOS && (
                <div>
                  <PlusOutlined />
                  <div style={{ marginTop: 8 }}>添加照片</div>
                </div>
              )}
            </Upload>
          </div>
          <Collapse
            size="small"
            style={{ marginBottom: 12 }}
            items={[{
              key: 'advanced',
              label: '高级：思考模式（给识别模型的附加提示，一般留空）',
              children: (
                <Input.TextArea
                  rows={2}
                  value={thinking}
                  onChange={(e) => setThinking(e.target.value)}
                  placeholder="可选：附加提示词"
                />
              ),
            }]}
          />
          <div className="extract-actions">
            <Button onClick={onClose}>取消</Button>
            <Button
              type="primary"
              disabled={!canSubmit}
              onClick={() => void ex.submit(describe, photos.map((p) => p.file), thinking)}
            >
              提取
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
