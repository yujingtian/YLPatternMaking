// 智能打版独立界面（2026-09-24 弹层退役，前端接线口径 §10.9.3）：
// 全幅「左对话右预览」工作面——多轮对话是长驻交互（VLM 解析动辄数十秒）、
// 审图是确认前的质量闸口，860px 弹框把整版挤成缩略图审不了图，故升独立
// 界面镜像主应用「左参数右视图」心智。
//   左栏 = 对话流（消息 + 求援卡白话批量问 + busy 秒表）+ 底部输入区
//   （照片池 + 文本 + 高级 thinking）——对话内交卷一律折叠为摘要行；
//   右栏 = 最新交卷的整版大图预览（SheetPreview：滚轮缩放 + 拖曳平移，
//   跟最新 delivery 自动刷新）+ 摘要行 + 确认/继续调整。
// 零打扰口径：全料喂入直接交卷、缺啥批量问一次；照片 = 待提交池
// （**提交成功即清空**，用户口径 2026-09-24——证据入会话 vlm_cache、
// 历史气泡保留缩略），上限 4 张按「池内待提交 + 累计已提交」计。
// 状态全在 useSmartDraft（挂 App 层），界面关开不丢；busy 锁返回/发送/
// 加照片（防后端会话双份 user 事件）。覆盖渲染（fixed z 950）：入口 =
// 启动选择层「智能打版」（盖选择层 z 900），「返回」= 二次确认后清空
// 会话（数据不保存，2026-09-24 用户口径；空会话直接返回）退回选择层；
// 「确认并进入工作台」走 App 侧换源收口 switchDraftSource。
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert, App as AntApp, Button, Collapse, Input, Popconfirm, Spin,
  Upload,
} from 'antd'
import type { TextAreaRef } from 'antd/es/input/TextArea'
import {
  PlusOutlined, RedoOutlined, RobotOutlined,
} from '@ant-design/icons'
import type { Values } from '../types'
import type { ChatMsg, SmartDraftState } from '../hooks/useSmartDraft'
import SheetPreview from './SheetPreview'
import {
  compressImage, MAX_PHOTOS, validatePhotoFile,
} from '../imageCompress'
import { deliverySummaryLine } from '../chatPayload'

export default function SmartDraftView({ chat, onConfirm }: {
  chat: SmartDraftState
  onConfirm: (m: Values, o: Values) => void
}) {
  const { message, modal } = AntApp.useApp()
  const [text, setText] = useState('')
  const logRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<TextAreaRef>(null)

  // 返回 = 确认后清空会话再退回选择层（数据不保存）；空会话（无消息
  // 无待提交照片）无事可丢，直接返回不弹确认
  function handleBack() {
    if (chat.messages.length === 0 && chat.photos.length === 0) {
      chat.setOpen(false)
      return
    }
    modal.confirm({
      title: '返回将清空当前对话',
      content: '当前对话与照片不会被保存，返回后全部清空。',
      okText: '确定返回',
      cancelText: '继续对话',
      onOk: () => {
        chat.reset()
        chat.setOpen(false)
      },
    })
  }

  // 消息/等待态变化自动滚底（elapsed 每秒联动 = busy 期间保持钉底）
  useEffect(() => {
    const el = logRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [chat.messages, chat.busy, chat.elapsed])

  // 校验 + 压缩后入池（照抄一期 beforeUpload 口径）；上限按**会话累计**
  // 计（池内待提交 + 已提交数）：满 4 张不再加（池内有待提交的可先删再
  // 换；删除不撤销后端已识别证据，§10.9.2「重识别是显式动作」口径）
  async function beforeUpload(file: File) {
    const err = validatePhotoFile(file)
    if (err) {
      message.error(err)
      return Upload.LIST_IGNORE
    }
    if (chat.photos.length + chat.sentPhotoCount >= MAX_PHOTOS) {
      message.error(`本次对话最多 ${MAX_PHOTOS} 张照片${
        chat.sentPhotoCount > 0 ? `，已提交 ${chat.sentPhotoCount} 张` : '，可先删除再换'
      }`)
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

  // 最新交卷（右栏预览/确认动作的数据源）；对话内所有交卷（含最新）
  // 折叠为摘要行——预览中心在右栏，日志不重复嵌图
  const lastDeliver = useMemo(() => {
    for (let i = chat.messages.length - 1; i >= 0; i--) {
      const m = chat.messages[i]
      if (m.role === 'agent' && m.kind === 'deliver') return m
    }
    return null
  }, [chat.messages])

  const confirmDeliver = () => {
    if (!lastDeliver) return
    const payload = chat.confirmPrefill(lastDeliver.delivery)
    onConfirm(payload.measurements, payload.options)
  }

  return (
    <div className="smart-view">
      <header className="smart-head">
        <h2><RobotOutlined /> 智能打版</h2>
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
        <span className="smart-head-spacer" />
        <Button disabled={chat.busy} onClick={handleBack}>
          返回
        </Button>
      </header>
      <div className="smart-body">
        <div className="smart-chat">
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
            {chat.messages.map((m) => (
              <MessageRow key={m.id} m={m} lastDeliverId={lastDeliver?.id ?? -1} />
            ))}
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
              {chat.photos.length + chat.sentPhotoCount < MAX_PHOTOS && (
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
              <Button type="primary" loading={chat.busy} disabled={!canSend}
                      onClick={() => void handleSend()}>
                发送
              </Button>
            </div>
          </div>
        </div>

        <section className="smart-preview">
          <div className="smart-preview-head">
            {lastDeliver ? (
              <>
                <span className="extract-meta">
                  {deliverySummaryLine(lastDeliver.delivery)}
                </span>
                <div className="smart-preview-actions">
                  <Button onClick={() => inputRef.current?.focus({ cursor: 'end' })}>
                    继续调整
                  </Button>
                  <Button type="primary" onClick={confirmDeliver}>
                    确认并进入工作台
                  </Button>
                </div>
              </>
            ) : (
              <span className="smart-preview-hint">
                整版预览：交卷后显示最新整版图（滚轮缩放 · 拖曳平移）
              </span>
            )}
          </div>
          <div className="smart-preview-body">
            {lastDeliver ? (
              <SheetPreview
                measurements={lastDeliver.delivery.measurements}
                options={lastDeliver.delivery.options}
              />
            ) : (
              <div className="smart-preview-empty">
                完成对话后这里显示整版预览——审图确认无误再进工作台
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}

// 单条消息渲染：user 气泡 / 求援卡 / 内联 error；交卷一律摘要行
// （最新一条标注右侧已更新，历史标注已被后续回答取代）
function MessageRow({ m, lastDeliverId }: { m: ChatMsg; lastDeliverId: number }) {
  if (m.role === 'user') {
    return (
      <div className="chat-msg user">
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
      <div className="chat-msg agent">
        <Alert type="error" showIcon message={m.message} />
      </div>
    )
  }
  if (m.kind === 'card') {
    return (
      <div className="chat-msg agent">
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
  return (
    <div className="chat-msg agent">
      <div className="chat-bubble chat-history">
        {deliverySummaryLine(m.delivery)}
        （{m.id === lastDeliverId ? '右侧已更新预览' : '已被后续回答取代'}）
      </div>
    </div>
  )
}
