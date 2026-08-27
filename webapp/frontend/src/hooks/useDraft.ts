import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  DraftPayload, DownloadKind, IssueDetail, PiecesResult, Schema, SeedPayload,
  SeedResult, SheetResult, Snapshot, Values,
} from '../types'
import {
  download as downloadFile, fetchSchema, postPieces, postSeed, postSheet,
} from '../api'
import { getEngine } from '../engine/client'

// UI 侧引擎状态：client 的 unavailable（引擎不可用）在界面上统一呈现为
// "服务端计算"（http）——对用户而言只是计算位置不同，功能不受影响
type UiEngineState = 'loading' | 'ready' | 'http'

const STORAGE_KEY = 'ylpattern.draft.v1'

function loadDraft(): DraftPayload | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed.measurements) return null
    return parsed as DraftPayload
  } catch {
    return null
  }
}

export interface DraftState {
  schema: Schema | null
  measurements: Values
  options: Values
  setMeasurement: (key: string, value: unknown) => void
  setOption: (key: string, value: unknown) => void
  loadValues: (m: Values, o: Values) => void
  // 从形态导入（custom_shape 编辑器：贴袋/袋布）：预设形态 -> custom 初始点/边。
  // 返回判别结果、不进全局 errors——非生成动作，失败内联显示在编辑器里
  seedShape: (kind: SeedPayload['kind'], shape: string) =>
    Promise<SeedResult | { ok: false; message: string }>
  generateSheet: () => Promise<void>
  generatePieces: () => Promise<void>
  download: (kind: DownloadKind) => Promise<void>
  // 二期拖拽调版：反解回写（显式载荷重生成整版）/ 撤销 / 面板高亮
  applyAdjust: (param: string, value: number, base: DraftPayload) => Promise<void>
  beginDrag: (param: string, prevValue: number) => void
  undoLastDrag: () => void
  lastDrag: { param: string; prevValue: number } | null
  adjustInfo: { param: string; ts: number } | null
  sheet: Snapshot<SheetResult> | null
  pieces: Snapshot<PiecesResult> | null
  sheetReady: boolean
  sheetStale: boolean
  piecesReady: boolean
  piecesStale: boolean
  errors: IssueDetail[]
  warnings: DraftWarning[]
  sheetBusy: boolean
  piecesBusy: boolean
  dlBusy: DownloadKind | null
  // 本地引擎状态（Pyodide worker）：loading 加载中 / ready 本地计算 /
  // http 走服务端（?engine=off、加载失败降级或 worker 反复崩溃）
  engineState: UiEngineState
}

interface DraftWarning {
  param: string | null
  message: string
}

export function useDraft(): DraftState {
  const [schema, setSchema] = useState<Schema | null>(null)
  const saved = useRef(loadDraft())
  const [measurements, setMeasurements] = useState<Values>(
    saved.current?.measurements ?? {},
  )
  const [options, setOptions] = useState<Values>(saved.current?.options ?? {})
  // 参数版本号：任意修改 +1；产物快照记录生成时版本，不等即"已过期"
  // （刷新后快照为 null 天然不 stale；localStorage 只存参数，生成状态不持久）。
  // versionRef 镜像：applyAdjust 需要在 setState 闭包外读到"下一版本号"
  // 做快照竞态判定（拖拽高频回写，不能等 state 落地）
  const versionRef = useRef(0)
  const [version, setVersion] = useState(0)
  const bump = useCallback(() => {
    versionRef.current += 1
    setVersion(versionRef.current)
  }, [])
  // 拖拽回写的参数基线（undo/下次生成用，规避闭包旧值）
  const measRef = useRef(measurements)
  measRef.current = measurements
  const optsRef = useRef(options)
  optsRef.current = options
  const [sheet, setSheet] = useState<Snapshot<SheetResult> | null>(null)
  const [pieces, setPieces] = useState<Snapshot<PiecesResult> | null>(null)
  const [errors, setErrors] = useState<IssueDetail[]>([])
  const [warnings, setWarnings] = useState<DraftWarning[]>([])
  const [sheetBusy, setSheetBusy] = useState(false)
  const [piecesBusy, setPiecesBusy] = useState(false)
  const piecesBusyRef = useRef(false)
  piecesBusyRef.current = piecesBusy
  const [dlBusy, setDlBusy] = useState<DownloadKind | null>(null)
  const [lastDrag, setLastDrag] = useState<{ param: string; prevValue: number } | null>(null)
  const [adjustInfo, setAdjustInfo] = useState<{ param: string; ts: number } | null>(null)
  const [engineState, setEngineState] = useState<UiEngineState>('loading')

  // 本地引擎生命周期（模块级单例，StrictMode 双挂载只建一个 worker）；
  // ?engine=off / 会话已降级 -> getEngine() 为 null，直标 http 态
  useEffect(() => {
    const eng = getEngine()
    if (eng === null) {
      setEngineState('http')
      return
    }
    const sync = () => setEngineState(
      eng.state === 'ready' ? 'ready' : eng.state === 'unavailable' ? 'http' : 'loading')
    sync()
    return eng.onProgress(sync)
  }, [])

  useEffect(() => {
    fetchSchema().then(setSchema).catch((e) => {
      setErrors([{ param: null, group: null, message: `schema 加载失败：${e}`, level: 'error' }])
    })
  }, [])

  // 参数草稿自动暂存（防抖 500ms）：关页面不丢参数
  useEffect(() => {
    const t = setTimeout(() => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ measurements, options }))
    }, 500)
    return () => clearTimeout(t)
  }, [measurements, options])

  // 参数修改即过版本：已有预览保留但标"已过期"，DXF 下载随之禁用
  const setMeasurement = useCallback((key: string, value: unknown) => {
    setMeasurements((prev) => ({ ...prev, [key]: value }))
    bump()
  }, [bump])
  const setOption = useCallback((key: string, value: unknown) => {
    setOptions((prev) => ({ ...prev, [key]: value }))
    bump()
  }, [bump])
  const loadValues = useCallback((m: Values, o: Values) => {
    setMeasurements(m)
    setOptions(o)
    bump()
  }, [bump])

  const sheetStale = sheet !== null && sheet.version !== version
  const piecesStale = pieces !== null && pieces.version !== version

  // 拖拽回写：显式载荷（base + 新参数值）直接重生成整版——闭包里捕获的
  // measurements/options 必然滞后于高频拖拽，参数面板与整版以 base 为准。
  // 值圆整 2 位（打版精度与面板显示一致）；ver 判定丢弃晚到的旧响应
  // （拖拽中旧快照不覆盖新参数状态）
  const applyAdjust = useCallback(async (param: string, value: number,
                                         base: DraftPayload) => {
    if (piecesBusyRef.current) return     // 两步互斥：裁片生成中丢弃回写
    const v = Math.round(value * 100) / 100
    if (Number(base.options[param]) === v) return
    const opts = { ...base.options, [param]: v }
    versionRef.current += 1
    const ver = versionRef.current
    setOptions(opts)
    setVersion(ver)
    setAdjustInfo({ param, ts: Date.now() })
    setSheetBusy(true)
    try {
      const res = await postSheet({ measurements: base.measurements, options: opts })
      if (ver !== versionRef.current) return    // 已有更新的回写/修改，丢弃旧响应
      setSheet({ data: res, version: ver })
      setWarnings(res.warnings.map((w) => ({ param: w.param, message: w.message })))
      setErrors([])
    } catch (e) {
      const err = e as Error & { detail?: IssueDetail[] }
      if (err.detail) {
        setErrors(err.detail)
      } else {
        setErrors([{ param: null, group: null, message: String(e), level: 'error' }])
      }
    } finally {
      setSheetBusy(false)
    }
  }, [])

  // 每次拖拽开始记录 {参数, 拖前值}（双击复位同口径：复位也可撤销）
  const beginDrag = useCallback((param: string, prevValue: number) => {
    setLastDrag({ param, prevValue })
  }, [])

  const undoLastDrag = useCallback(() => {
    setLastDrag((d) => {
      if (!d) return null
      void applyAdjust(d.param, d.prevValue, {
        measurements: measRef.current, options: optsRef.current,
      })
      return null
    })
  }, [applyAdjust])

  const generateSheet = useCallback(async () => {
    if (piecesBusy) return            // 两步互斥（引擎 CPU 密集，毗围闭环可多轮重跑）
    setSheetBusy(true)
    setErrors([])
    try {
      const res = await postSheet({ measurements, options })
      setSheet({ data: res, version })
      setWarnings(res.warnings.map((w) => ({ param: w.param, message: w.message })))
    } catch (e) {
      const err = e as Error & { detail?: IssueDetail[] }
      if (err.detail) {
        setErrors(err.detail)
      } else {
        setErrors([{ param: null, group: null, message: String(e), level: 'error' }])
      }
    } finally {
      setSheetBusy(false)
    }
  }, [measurements, options, version, piecesBusy])

  const generatePieces = useCallback(async () => {
    // 先画后裁（UI 门控）：整版未生成/已过期/生成中均不开裁片
    if (sheetBusy || !sheet || sheet.version !== version) return
    setPiecesBusy(true)
    setErrors([])
    try {
      const res = await postPieces({ measurements, options })
      setPieces({ data: res, version })
      setWarnings(res.warnings.map((w) => ({ param: w.param, message: w.message })))
    } catch (e) {
      const err = e as Error & { detail?: IssueDetail[] }
      if (err.detail) {
        setErrors(err.detail)
      } else {
        setErrors([{ param: null, group: null, message: String(e), level: 'error' }])
      }
    } finally {
      setPiecesBusy(false)
    }
  }, [measurements, options, version, sheet, sheetBusy])

  // 从形态导入：读 optsRef 规避闭包旧值；失败返回 {ok:false, message}
  // 内联显示在编辑器（422 detail 为字符串消息，其余取 error 文本）
  const seedShape = useCallback(async (kind: SeedPayload['kind'],
                                       shape: string) => {
    try {
      return await postSeed({ kind, shape, options: optsRef.current })
    } catch (e) {
      const err = e as Error & { detail?: unknown }
      const msg = typeof err.detail === 'string' ? err.detail : String(e)
      return { ok: false as const, message: msg }
    }
  }, [])

  const download = useCallback(async (kind: DownloadKind) => {
    if (dlBusy !== null) return       // 串行：下载重跑引擎，防重复点击
    setDlBusy(kind)
    try {
      const payload = { measurements, options }
      if (kind === 'sheetDxf') {
        await downloadFile('/api/dxf?kind=sheet', payload, 'sheet.dxf')
      } else if (kind === 'piecesDxf') {
        await downloadFile('/api/dxf?kind=pieces', payload, 'pieces.dxf')
      } else {
        await downloadFile('/api/toml', payload, 'size_draft.toml')
      }
    } catch (e) {
      // 下载失败入 errors（与 schema 加载失败同口径，Toolbar Alert 呈现）
      setErrors([{ param: null, group: null, message: `下载失败：${e}`, level: 'error' }])
    } finally {
      setDlBusy(null)
    }
  }, [measurements, options, dlBusy])

  return {
    schema, measurements, options, setMeasurement, setOption, loadValues,
    seedShape,
    generateSheet, generatePieces, download,
    applyAdjust, beginDrag, undoLastDrag, lastDrag, adjustInfo,
    sheet, pieces,
    sheetReady: sheet !== null, sheetStale,
    piecesReady: pieces !== null, piecesStale,
    errors, warnings,
    sheetBusy, piecesBusy, dlBusy,
    engineState,
  }
}
