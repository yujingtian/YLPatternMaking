// 交卷卡整版预览（2026-09-21（三）：交卷卡以图为中心、参数明细全删）：
// delivery 参数直喂 postSheet——本地 Pyodide 引擎优先、HTTP /api/draft/sheet
// 透明回退（api.route），返回 .sheet_svg 字符串内联渲染（照抄
// AdvancedEditor 的 SvgView 范本）。与确认预填后的主视图 2D 工作台同一
// 通道，预览即所见。失败不阻塞确认——参数仍可预填，主视图会重算整版。
import { useEffect, useState } from 'react'
import { Alert, Spin } from 'antd'
import { postSheet } from '../api'
import type { Values } from '../types'

// 预览状态；svg 为引擎整版 SVG 字符串
type PreviewState = { svg?: string; error?: string }

export default function SheetPreview({ measurements, options }: {
  measurements: Values
  options: Values
}) {
  // measurements/options 是 delivery 的不可变快照，序列化做 effect 依赖即可
  const key = JSON.stringify([measurements, options])
  const [state, setState] = useState<PreviewState>({})

  useEffect(() => {
    let alive = true
    setState({})   // 新 delivery 先清旧图（Modal 关闭不卸载内容，预览后台算完重开即现）
    // measurements/options 是稳定快照（不可变消息），effect 只随 key 重跑
    postSheet({ measurements, options })
      .then(
        (r) => { if (alive) setState({ svg: r.sheet_svg }) },
        (e) => {
          if (alive) {
            setState({ error: e instanceof Error ? e.message : String(e) })
          }
        },
      )
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  if (state.error !== undefined) {
    return (
      <Alert
        type="error"
        showIcon
        message={`整版预览生成失败：${state.error}`}
        description="不影响确认预填——预填后主视图会重新计算整版。"
      />
    )
  }
  if (state.svg === undefined) {
    return (
      <div className="chat-sheet">
        <Spin />
        <span className="chat-sheet-hint">
          正在生成整版预览…首次需加载本地引擎，可能数秒
        </span>
      </div>
    )
  }
  return <div className="chat-sheet" dangerouslySetInnerHTML={{ __html: state.svg }} />
}
