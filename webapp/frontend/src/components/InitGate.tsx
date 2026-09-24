// 启动初始化选择层（2026-09-19，替代 localStorage 静默恢复的知情权缺失）：
// 每次启动先选参数来源——继续上次草稿 / 款式模板 / 智能打版 / 空白默认，
// 显式选择后才进工作台（App 侧 initialized 门控：选择层期间 header/main
// 不挂载，3D 视图不发隐藏首挂请求）。header「新建」2026-09-24 起为二次
// 确认后整体还原（工作台卸载、initialized 复位），本层恒以「继续上次草稿」
// 出现——原「中途重开不卸载 + 返回当前参数」分支随还原语义退役删除。
// 遮罩 zIndex 900 < 智能打版独立界面 950 < antd Modal 1000：从本层进入的
// SmartDraftView 天然盖上，返回即自然退回本层（initOpen 从未关过，
// 零分支返回路径）。
// 智能打版（2026-09-21 二期，原「从照片提取」入口升级；2026-09-24 起
// 为左对话右可缩放整版预览的独立界面）：对话式多轮
// 参数推断（照片/描述均可，§10.9.2/§10.9.3）。
// 空白默认（2026-09-20 用户口径）：直接载 examples/size_female_zhitong.toml
// 直筒全特征基样（口袋/袋贴/育克/裤耳全开），不再 schema default 合成；
// 码表不预填（size_run 段显式丢弃，第三参 null 清空）。

import { useState } from 'react'
import { Button } from 'antd'
import {
  HistoryOutlined, PlusOutlined, RobotOutlined,
} from '@ant-design/icons'
import type { SizeRunSpec, Values } from '../types'
import { fetchTemplateDetail } from '../api'
import TemplatePicker from './TemplatePicker'

// 空白默认基样（examples/ 直筒全特征款）
const BLANK_TEMPLATE = 'size_female_zhitong.toml'

type BlankState = 'idle' | 'loading' | 'error'

export default function InitGate({
  hasSavedDraft, onContinue, onLoadValues, onOpenChat,
}: {
  // 挂载期是否存在有效草稿（useDraft.loadDraft 收紧口径：空对象无效）
  hasSavedDraft: boolean
  // 继续上次：直接关层（state 本就是暂存草稿恢复态——启动初值静默恢复，
  // 「新建」还原后 d.reset() 重读同源）
  onContinue: () => void
  // 模板与空白默认共用：loadValues + 关层（App 侧包装）
  onLoadValues: (m: Values, o: Values, sizeRun?: SizeRunSpec | null) => void
  // 进入智能打版独立界面（本层保持打开，返回自然退回）
  onOpenChat: () => void
}) {
  const canContinue = hasSavedDraft
  const [blank, setBlank] = useState<BlankState>('idle')

  async function loadBlank() {
    setBlank('loading')
    try {
      const detail = await fetchTemplateDetail(BLANK_TEMPLATE)
      // 码表不预填：模板 [size_run] 段显式丢弃（null = 清空）
      onLoadValues(detail.measurements, detail.options, null)
    } catch {
      setBlank('error')
    }
  }

  return (
    <div className="init-gate">
      <div className="init-gate-card">
        <h2>选择参数来源</h2>
        <p className="init-gate-sub">
          决定本次打版从哪份参数开始（进入后仍可随时调整）
        </p>
        <div className="init-gate-grid">
          <div className="init-option">
            <div className="init-option-title">
              <HistoryOutlined />
              继续上次草稿
            </div>
            <div className="init-option-desc">
              恢复最近一次会话的全部参数与推板码表
            </div>
            <Button type="primary" autoFocus disabled={!canContinue}
                    onClick={onContinue}>
              {canContinue ? '继续' : '无已保存草稿'}
            </Button>
          </div>
          <div className="init-option">
            <div className="init-option-title">款式模板载入</div>
            <div className="init-option-desc">
              examples 尺寸单一键填充（测量+选项+推板码表）
            </div>
            <TemplatePicker onLoad={onLoadValues} />
          </div>
          <div className="init-option">
            <div className="init-option-title"><RobotOutlined /> 智能打版</div>
            <div className="init-option-desc">
              一句话描述需求（可带照片），左对话右预览，确认后进入工作台
            </div>
            <Button icon={<RobotOutlined />} onClick={onOpenChat}>
              开始对话
            </Button>
          </div>
          <div className="init-option">
            <div className="init-option-title"><PlusOutlined /> 空白默认</div>
            <div className="init-option-desc">
              直筒全特征基样（口袋/育克/裤耳全开，码表不预填）
              {blank === 'error' && '，基样读取失败请重试'}
            </div>
            <Button
              icon={<PlusOutlined />}
              loading={blank === 'loading'}
              onClick={() => void loadBlank()}
            >
              {blank === 'error' ? '重试' : '开始'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
