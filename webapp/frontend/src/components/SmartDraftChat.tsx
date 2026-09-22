// 智能打版对话弹层（二期前端接线 §10.9.2）：多轮对话壳——消息流 +
// 求援卡（白话批量问）+ 交卷卡（2026-09-21（三）以整版 SVG 预览为中心、
// 参数明细全删：图 + 摘要行 + 确认/继续调整；仅最新一条渲染完整卡，
// 历史折叠为摘要行）+ 底部输入区（照片池 + 文本 + 高级 thinking）。
// 零打扰口径：全料喂入直接交卷、缺啥批量问一次；照片 = 会话全量池
// （每轮全量重发，后端指纹去重只送新照片进 VLM），上限 4 张按会话池计。
// 状态全在 useSmartDraft（挂 App 层），弹层关开不丢；busy 锁 Modal 交互
// 防后端会话双份 user 事件。
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert, App as AntApp, Button, Collapse, Input, Modal, Popconfirm, Spin,
  Upload,
} from 'antd'
import type { TextAreaRef } from 'antd/es/input/TextArea'
import { PlusOutlined, RedoOutlined } from '@ant-design/icons'
import type { Values } from '../types'
import type { SmartDraftState } from '../hooks/useSmartDraft'
import SheetPreview from './SheetPreview'
import {
  compressImage, MAX_PHOTOS, validatePhotoFile,
} from '../imageCompress'
import { deliverySummaryLine } from '../chatPayload'

export default function SmartDraftChat({ chat, onConfirm }: {
  chat: SmartDraftState
  onConfirm: (m: Values, o: Values) => void
}) {
  const { message } = AntApp.useApp()
  const [text, setText] = useState('')
  const logRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<TextAreaRef>(null)

  // 消息/等待态变化自动滚底（elapsed 每秒联动 = busy 期间保持钉底）
  useEffect(() => {
    const el = logRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [chat.messages, chat.busy, chat.elapsed])

  // 校验 + 压缩后入池（照抄一期 beforeUpload 口径）；上限按**会话全量池**
  // 计——满 4 张不再加（可先删再换；删除不撤销后端已识别证据，
  // §10.9.2「重识别是显式动作」口径）
  async function beforeUpload(file: File) {
    const err = validatePhotoFile(file)
    if (err) {
      message.error(err)
      return Upload.LIST_IGNORE
    }
    if (chat.photos.length >= MAX_PHOTOS) {
      message.error(`本次对话最多 ${MAX_PHOTOS} 张照片，可先删除再换`)
      return Upload.LIST_IGNORE
    }
    const out = await compressImage(file)   // 解码失败内部降级直传
    chat.addPhoto({
      uid: `${file.name}-${file.size}-${Date.now()}`,
      name: out.name, url: URL.createObjectURL(out), file: out,
    })
    return Upload.LIST_IGNORE
  }

  async function handleSend() {
    const t = text.trim()
    if (!t || chat.busy || chat.health === null) return
    const ok = await chat.send(t)
    if (ok) setText('')   // 失败输入不清：改两个词直接重发
  }

  const canSend = text.trim().length > 0 && chat.health !== null && !chat.busy
  const healthUnknown = chat.health === null && !chat.healthLoading

  // 交卷卡只完整渲染最新一条（历史折叠为摘要行——旧交卷不可再确认，
  // 改口后答会产生新 delivery）
  const lastDeliverId = useMemo(() => {
    for (let i = chat.messages.length - 1; i >= 0; i--) {
      const m = chat.messages[i]
      if (m.role === 'agent' && m.kind === 'deliver') return m.id
    }
    return -1
  }, [chat.messages])

  return (
    <Modal
      open={chat.open}
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', paddingRight: 24 }}>
          <span>智能打版</span>
          <Popconfirm
            title="清空当前对话重新开始？"
            okText="重新开始"
            cancelText="取消"
            onConfirm={chat.reset}
          >
            <Button size="small" icon={<RedoOutlined />} disabled={chat.busy}>
              重新开始
            </Button>
          </Popconfirm>
        </div>
      }
      width={860}
      footer={null}
      maskClosable={false}
      closable={!chat.busy}
      keyboard={!chat.busy}
      onCancel={() => chat.setOpen(false)}
    >
      {healthUnknown && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="agent 服务未启动或不可达（默认 http://localhost:8001）——无法发送"
        />
      )}
      {chat.health !== null && !chat.health.vlm_configured && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="VLM 未配置（vlm.toml）：照片不会被解析，仅从描述文字推断——纯描述也能全中"
        />
      )}

      <div className="chat-log" ref={logRef}>
        {chat.messages.length === 0 && (
          <div className="chat-msg agent">
            <div className="chat-bubble">
              一句话说出你要的裤子（建议含 7 必填尺寸）：
              例「女款高腰小脚牛仔裤，腰围 74 臀围 91 膝围 44 脚口 34
              前浪 25 后浪 33 裤长 102」。缺的我会一次问齐；
              也可以配上正/背面平铺照片。
            </div>
          </div>
        )}
        {chat.messages.map((m) => {
          if (m.role === 'user') {
            return (
              <div className="chat-msg user" key={m.id}>
                <div className="chat-bubble">
                  {m.text}
                  {m.photoUrls.length > 0 && (
                    <div className="chat-photos">
                      {m.photoUrls.map((u) => <img key={u} src={u} alt="" />)}
                    </div>
                  )}
                </div>
              </div>
            )
          }
          if (m.kind === 'error') {
            return (
              <div className="chat-msg agent" key={m.id}>
                <Alert type="error" showIcon message={m.message} />
              </div>
            )
          }
          if (m.kind === 'card') {
            return (
              <div className="chat-msg agent" key={m.id}>
                <div className="chat-card">
                  <div className="chat-card-message">{m.card.message}</div>
                  {m.card.asks.length > 0 && (
                    <ul className="chat-card-asks">
                      {m.card.asks.map((a) => (
                        <li key={a.key} className="chat-card-ask">
                          <b>{a.label}</b>
                          <span className="chat-card-why">
                            （{a.why}；例：{a.example}）
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {m.card.want_photos.length > 0 && (
                    <Alert
                      type="info"
                      showIcon
                      message={`建议补拍：${m.card.want_photos.join('、')}（用下方照片按钮添加后直接发送）`}
                    />
                  )}
                </div>
              </div>
            )
          }
          // deliver：最新 = 整版预览卡（图为中心，参数明细全删） / 历史摘要行
          if (m.id === lastDeliverId) {
            return (
              <div className="chat-msg agent" key={m.id}>
                <div className="chat-deliver">
                  <SheetPreview
                    measurements={m.delivery.measurements}
                    options={m.delivery.options}
                  />
                  <div className="extract-meta">
                    {deliverySummaryLine(m.delivery)}
                  </div>
                  <div className="extract-actions">
                    <Button onClick={() => inputRef.current?.focus({ cursor: 'end' })}>
                      继续调整
                    </Button>
                    <Button
                      type="primary"
                      onClick={() => {
                        const payload = chat.confirmPrefill(m.delivery)
                        onConfirm(payload.measurements, payload.options)
                      }}
                    >
                      确认并预填表单
                    </Button>
                  </div>
                </div>
              </div>
            )
          }
          return (
            <div className="chat-msg agent" key={m.id}>
              <div className="chat-bubble chat-history">
                {deliverySummaryLine(m.delivery)}（已被后续回答取代）
              </div>
            </div>
          )
        })}
        {chat.busy && (
          <div className="chat-msg agent">
            <div className="chat-typing">
              <Spin size="small" />
              正在思考…已耗时 {chat.elapsed}s（含照片解析可能需要数十秒）
            </div>
          </div>
        )}
      </div>

      <div className="chat-input-bar">
        <Upload
          listType="picture-card"
          accept=".jpg,.jpeg,.png,.webp,.bmp,.gif"
          fileList={chat.photos}
          beforeUpload={(f) => void beforeUpload(f)}
          onRemove={(f) => chat.removePhoto(f.uid)}
          disabled={chat.busy}
        >
          {chat.photos.length < MAX_PHOTOS && (
            <div>
              <PlusOutlined />
              <div style={{ marginTop: 8 }}>添加照片</div>
            </div>
          )}
        </Upload>
        <Input.TextArea
          ref={inputRef}
          rows={2}
          maxLength={2000}
          value={text}
          disabled={chat.busy}
          onChange={(e) => setText(e.target.value)}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault()   // Enter 发送、Shift+Enter 换行
              void handleSend()
            }
          }}
          placeholder="回复消息（Enter 发送，Shift+Enter 换行）；改口直接说，例：腰围改 75"
        />
        <Collapse
          size="small"
          style={{ marginTop: 8 }}
          items={[{
            key: 'advanced',
            label: '高级：思考模式（给识别模型的附加提示，一般留空）',
            children: (
              <Input.TextArea
                rows={2}
                value={chat.thinking}
                onChange={(e) => chat.setThinking(e.target.value)}
                placeholder="可选：附加提示词"
              />
            ),
          }]}
        />
        <div className="extract-actions">
          <Button onClick={() => chat.setOpen(false)} disabled={chat.busy}>
            关闭
          </Button>
          <Button type="primary" loading={chat.busy} disabled={!canSend}
                  onClick={() => void handleSend()}>
            发送
          </Button>
        </div>
      </div>
    </Modal>
  )
}
