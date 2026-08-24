import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  DraftPayload, DraftResult, IssueDetail, Schema, Values,
} from '../types'
import { fetchSchema, postDraft } from '../api'

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
  generate: () => Promise<void>
  result: DraftResult | null
  errors: IssueDetail[]
  warnings: DraftWarning[]
  busy: boolean
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
  const [result, setResult] = useState<DraftResult | null>(null)
  const [errors, setErrors] = useState<IssueDetail[]>([])
  const [warnings, setWarnings] = useState<DraftWarning[]>([])
  const [busy, setBusy] = useState(false)

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

  const setMeasurement = useCallback((key: string, value: unknown) => {
    setMeasurements((prev) => ({ ...prev, [key]: value }))
  }, [])
  const setOption = useCallback((key: string, value: unknown) => {
    setOptions((prev) => ({ ...prev, [key]: value }))
  }, [])
  const loadValues = useCallback((m: Values, o: Values) => {
    setMeasurements(m)
    setOptions(o)
  }, [])

  const generate = useCallback(async () => {
    setBusy(true)
    setErrors([])
    try {
      const res = await postDraft({ measurements, options })
      setResult(res)
      setWarnings(res.warnings.map((w) => ({ param: w.param, message: w.message })))
    } catch (e) {
      const err = e as Error & { detail?: IssueDetail[] }
      if (err.detail) {
        setErrors(err.detail)
      } else {
        setErrors([{ param: null, group: null, message: String(e), level: 'error' }])
      }
    } finally {
      setBusy(false)
    }
  }, [measurements, options])

  return {
    schema, measurements, options, setMeasurement, setOption, loadValues,
    generate, result, errors, warnings, busy,
  }
}
