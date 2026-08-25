import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  DraftPayload, DownloadKind, IssueDetail, PiecesResult, Schema, SheetResult,
  Snapshot, Values,
} from '../types'
import { download as downloadFile, fetchSchema, postPieces, postSheet } from '../api'

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
  generateSheet: () => Promise<void>
  generatePieces: () => Promise<void>
  download: (kind: DownloadKind) => Promise<void>
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
  // （刷新后快照为 null 天然不 stale；localStorage 只存参数，生成状态不持久）
  const [version, setVersion] = useState(0)
  const [sheet, setSheet] = useState<Snapshot<SheetResult> | null>(null)
  const [pieces, setPieces] = useState<Snapshot<PiecesResult> | null>(null)
  const [errors, setErrors] = useState<IssueDetail[]>([])
  const [warnings, setWarnings] = useState<DraftWarning[]>([])
  const [sheetBusy, setSheetBusy] = useState(false)
  const [piecesBusy, setPiecesBusy] = useState(false)
  const [dlBusy, setDlBusy] = useState<DownloadKind | null>(null)

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
    setVersion((v) => v + 1)
  }, [])
  const setOption = useCallback((key: string, value: unknown) => {
    setOptions((prev) => ({ ...prev, [key]: value }))
    setVersion((v) => v + 1)
  }, [])
  const loadValues = useCallback((m: Values, o: Values) => {
    setMeasurements(m)
    setOptions(o)
    setVersion((v) => v + 1)
  }, [])

  const sheetStale = sheet !== null && sheet.version !== version
  const piecesStale = pieces !== null && pieces.version !== version

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
    generateSheet, generatePieces, download,
    sheet, pieces,
    sheetReady: sheet !== null, sheetStale,
    piecesReady: pieces !== null, piecesStale,
    errors, warnings,
    sheetBusy, piecesBusy, dlBusy,
  }
}
