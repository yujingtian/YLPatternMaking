// API 路由层（2026-08 本地引擎）：计算类调用优先走浏览器内 Pyodide
// worker（零网络往返，拖拽/预览不卡），失败透明回落 HTTP；下载/模板/
// schema 永远走 HTTP（DXF 依赖 ezdxf 留服务端；schema 首屏零等待）。
// 上层（useDraft/SheetView）对通道零感知——两条通道返回结构完全同构
// （tests/test_engine_glue.py 金标钉死）。
import { getEngine, isEngineFailure } from './engine/client'
import type { AdjustPayload, EngineCmd } from './engine/protocol'
import * as http from './apiHttp'
import type {
  AdjustResult, DraftPayload, FittingResult, PiecesResult, SeedPayload,
  SeedResult, SheetResult,
} from './types'

export type { Template } from './apiHttp'

// 下载（DXF/toml）与模板/参数 schema：永远 HTTP（引擎不落盘、
// ezdxf 不进浏览器；schema 首屏不等 worker 就绪）。
// downloadBlob 为内存直存（SVG/报表，无 HTTP）；downloadBlobBytes 为
// 二进制内存直存（排料 DXF base64 解码后落盘）；postNest 排料对接
// （/api/nest 出 JSON：DXF 依赖 ezdxf，同 DXF 类永不走本地引擎）
export const download = http.download
export const downloadBlob = http.downloadBlob
export const downloadBlobBytes = http.downloadBlobBytes
export const postNest = http.postNest
export const fetchSchema = http.fetchSchema
export const fetchTemplates = http.fetchTemplates
export const fetchTemplateDetail = http.fetchTemplateDetail

// agent 照片参数提取（一期前端接线）：纯网络调用（VLM/照片均不进
// Pyodide 本地引擎），不进 route() 引擎通道
export const postExtract = http.postExtract
export const fetchAgentHealth = http.fetchAgentHealth

// MS 机器排料六端点（二期对接 §10.3.2）：纯网络调用（求解/轮询/取果/停止/
// DELETE 清理/PLT 导出全在 MS 服务侧），不进 route() 引擎通道（同 postNest
// 先例）；MsError 供 useNestSolve 按 status 判「不可重试」（404/400）
export const msSolveStart = http.msSolveStart
export const msStatus = http.msStatus
export const msResult = http.msResult
export const msStop = http.msStop
export const msDeleteTask = http.msDeleteTask
export const msExport = http.msExport
export type { MsError } from './apiHttp'

// 本地引擎单命令超时（ms）：超时本次回落 HTTP 并计数，连续 3 次会话降级
const TIMEOUTS: Record<EngineCmd, number> = {
  sheet: 30_000,
  pieces: 30_000,
  adjust: 60_000,
  fitting: 30_000,
  seed: 5_000,           // 纯函数毫秒级
}

// P 不约束为 DraftPayload：seed 入参为 {kind, shape, options}（不带
// measurements，后端不走 _build——其余参数中间态非法时 seed 也要可用）
async function route<P, T>(
  cmd: EngineCmd, payload: P, httpFn: (p: P) => Promise<T>,
): Promise<T> {
  const eng = getEngine()
  if (eng !== null) {
    try {
      return await eng.call<T>(
        cmd, payload as DraftPayload | AdjustPayload | SeedPayload,
        TIMEOUTS[cmd])
    } catch (e) {
      // validation（参数错，与 HTTP 422 同构）直接抛给上层显示；
      // 引擎侧失败/超时才回落 HTTP 再试
      if (!isEngineFailure(e)) throw e
    }
  }
  return httpFn(payload)
}

export function postSheet(payload: DraftPayload): Promise<SheetResult> {
  return route('sheet', payload, http.postSheet)
}

export function postPieces(payload: DraftPayload): Promise<PiecesResult> {
  return route('pieces', payload, http.postPieces)
}

export function postFitting(payload: DraftPayload): Promise<FittingResult> {
  return route('fitting', payload, http.postFitting)
}

export function postAdjust(payload: AdjustPayload): Promise<AdjustResult> {
  return route('adjust', payload, http.postAdjust)
}

export function postSeed(payload: SeedPayload): Promise<SeedResult> {
  return route('seed', payload, http.postSeed)
}
