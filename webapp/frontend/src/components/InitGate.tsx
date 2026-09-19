// 启动初始化选择层（2026-09-19，替代 localStorage 静默恢复的知情权缺失）：
// 每次启动先选参数来源——继续上次草稿 / 款式模板 / 照片提取 / 空白默认，
// 显式选择后才进工作台（App 侧 initialized 门控：选择层期间 header/main
// 不挂载，3D 视图不发隐藏首挂请求）。中途经 header「新建」重开时
// 工作台保持挂载，「继续上次」语义切为「返回当前参数」。
// 遮罩 zIndex 900 < antd Modal 1000：从本层拉起的 ExtractWizard 天然盖上，
// 取消向导即自然退回本层（initOpen 从未关过，零分支返回路径）。
// 空白默认（2026-09-20 用户口径）：直接载 examples/size_female_zhitong.toml
// 直筒全特征基样（口袋/袋贴/育克/裤耳全开），不再 schema default 合成；
// 码表不预填（size_run 段显式丢弃，第三参 null 清空）。

import { useState } from 'react'
import { Button } from 'antd'
import {
  CameraOutlined, HistoryOutlined, PlusOutlined,
} from '@ant-design/icons'
import type { SizeRunSpec, Values } from '../types'
import { fetchTemplateDetail } from '../api'
import TemplatePicker from './TemplatePicker'

// 空白默认基样（examples/ 直筒全特征款）
const BLANK_TEMPLATE = 'size_female_zhitong.toml'

type BlankState = 'idle' | 'loading' | 'error'

export default function InitGate({
  hasSavedDraft, initialized,
  onContinue, onLoadValues, onOpenExtract,
}: {
  // 挂载期是否存在有效草稿（useDraft.loadDraft 收紧口径：空对象无效）
  hasSavedDraft: boolean
  // 已进过工作台（中途重开）：「返回当前参数」恒可用
  initialized: boolean
  // 继续上次 / 返回当前：直接关层（state 初值本就静默恢复过）
  onContinue: () => void
  // 模板与空白默认共用：loadValues + 关层（App 侧包装）
  onLoadValues: (m: Values, o: Values, sizeRun?: SizeRunSpec | null) => void
  // 拉起照片提取向导（本层保持打开，取消自然退回）
  onOpenExtract: () => void
}) {
  const canContinue = hasSavedDraft || initialized
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
              {initialized ? '返回当前参数' : '继续上次草稿'}
            </div>
            <div className="init-option-desc">
              {initialized
                ? '保持当前参数不动，直接回到工作台'
                : '恢复最近一次会话的全部参数与推板码表'}
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
            <div className="init-option-title"><CameraOutlined /> 从照片提取</div>
            <div className="init-option-desc">
              照片/款式描述智能识别，确认后预填表单
            </div>
            <Button icon={<CameraOutlined />} onClick={onOpenExtract}>
              打开提取向导
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
