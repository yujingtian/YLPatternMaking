import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  DraftPayload, DownloadKind, FittingResult, IssueDetail, NestResult,
  PiecesResult, Schema, SeedPayload, SeedResult, SheetResult, Snapshot,
  SizeRunSpec, Values,
} from '../types'
import {
  download as downloadFile, fetchSchema, postFitting, postNest, postPieces,
  postSeed, postSheet,
} from '../api'
import { normalizeSizeRun } from '../sizeRun'
import { PRODUCT_POCKET_KEYS } from '../factoryParams'
import { getEngine } from '../engine/client'

// UI 侧引擎状态：client 的 unavailable（引擎不可用）在界面上统一呈现为
// "服务端计算"（http）——对用户而言只是计算位置不同，功能不受影响
type UiEngineState = 'loading' | 'ready' | 'http'

const STORAGE_KEY = 'ylpattern.draft.v1'

// 有效草稿 = measurements 为对象且至少含 1 个键（空对象恢复出来本就是
// 空工作台，判无效——「继续上次」入口据此禁用，2026-09-19 收紧）
function loadDraft(): DraftPayload | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (typeof parsed.measurements !== 'object'
        || parsed.measurements === null
        || Object.keys(parsed.measurements).length === 0) return null
    return parsed as DraftPayload
  } catch {
    return null
  }
}

export interface DraftState {
  schema: Schema | null
  measurements: Values
  options: Values
  // 推板码表（canonical，sizeRun.ts 转换）：null = 未配置（推板 DXF 点击
  // 转为打开设置抽屉）。 setSizeRun 不 bump version——码表不影响整版/裁片
  // 快照的新鲜度，门控仍由 measurements/options 驱动
  sizeRun: SizeRunSpec | null
  setMeasurement: (key: string, value: unknown) => void
  setOption: (key: string, value: unknown) => void
  setSizeRun: (s: SizeRunSpec | null) => void
  loadValues: (m: Values, o: Values, sizeRun?: SizeRunSpec | null) => void
  // 整体还原（header「新建」确认后，2026-09-24）：参数重读 localStorage 回
  // 启动初态（与首挂同源——启动选择层「继续上次草稿」= 找回口），产物
  // 快照/拖拽基线/校验条全清（口径同 loadValues 换源还原段）
  reset: () => void
  // 从形态导入（custom_shape 编辑器：贴袋/袋布）：预设形态 -> custom 初始点/边。
  // 返回判别结果、不进全局 errors——非生成动作，失败内联显示在编辑器里
  seedShape: (kind: SeedPayload['kind'], shape: string) =>
    Promise<SeedResult | { ok: false; message: string }>
  // 生成动作返回快照（失败/互斥返回 null）：导出中心与高级编辑按需
  // 补算后直接消费结果，不依赖 state 重渲染取数（2026-09-11 交互重构）
  generateSheet: () => Promise<Snapshot<SheetResult> | null>
  generatePieces: () => Promise<Snapshot<PiecesResult> | null>
  // 3D 悬挂展示 payload 生成（2026-09-13 复活、09-14 改悬挂消费）：
  // 自互斥（进行中丢弃新请求），与两步生成同构的版本竞态语义
  generateFitting: () => Promise<Snapshot<FittingResult> | null>
  // 按需补算（2D 进高级编辑/导出时才补）：
  // 快照缺失或 stale 才重跑，新鲜直接复用；读 ref 规避闭包旧值
  ensureSheet: () => Promise<Snapshot<SheetResult> | null>
  ensurePieces: () => Promise<Snapshot<PiecesResult> | null>
  // opts.sizeRun：抽屉「保存+导出」同 tick 的显式覆盖（规避闭包旧值竞态）；
  // nest 分支返回排料产物（清单弹窗删除后由调用方直接消费 + console 打印，
  // 2026-09-22），其余分支返回 undefined
  download: (kind: DownloadKind, opts?: { sizeRun?: SizeRunSpec | null }) =>
    Promise<NestResult | undefined>
  // 二期拖拽调版：反解回写（显式载荷重生成整版）/ 撤销 / 面板高亮
  applyAdjust: (param: string, value: number, base: DraftPayload) => Promise<void>
  beginDrag: (param: string, prevValue: number) => void
  undoLastDrag: () => void
  lastDrag: { param: string; prevValue: number } | null
  adjustInfo: { param: string; ts: number } | null
  sheet: Snapshot<SheetResult> | null
  pieces: Snapshot<PiecesResult> | null
  fitting: Snapshot<FittingResult> | null
  sheetReady: boolean
  sheetStale: boolean
  piecesReady: boolean
  piecesStale: boolean
  fittingStale: boolean
  errors: IssueDetail[]
  warnings: DraftWarning[]
  sheetBusy: boolean
  piecesBusy: boolean
  fittingBusy: boolean
  dlBusy: DownloadKind | null
  // 本地引擎状态（Pyodide worker）：loading 加载中 / ready 本地计算 /
  // http 走服务端（?engine=off、加载失败降级或 worker 反复崩溃）
  engineState: UiEngineState
  // 挂载期是否存在有效草稿（启动初始化选择层「继续上次」入口的依据；
  // 全会话稳定事实，不随后续暂存变化）
  hasSavedDraft: boolean
}

interface DraftWarning {
  param: string | null
  message: string
}

// 排料清单行集（numMap + labels -> 可读行，g 码数字升序）：排料数量清单
// 弹窗删除后（2026-09-22 入口收口）供 console.table 排查打印；labels 与
// numMap 键集理论上同源（后端同一次遍历产出），回退仅兜底
export interface NestRow {
  g: string        // g 码（g01…）
  label: string    // 裁片中文名（labels 缺键回退「裁片」）
  qty: number      // 数量（各码相同，numMap 扁平）
}

function gNum(g: string): number {
  const n = parseInt(g.replace(/^g/i, ''), 10)
  return Number.isNaN(n) ? Number.MAX_SAFE_INTEGER : n
}

export function nestRows(r: NestResult): NestRow[] {
  return Object.entries(r.numMap)
    .map(([g, qty]) => ({ g, label: r.labels[g] ?? '裁片', qty }))
    .sort((a, b) => gNum(a.g) - gNum(b.g))
}

export function useDraft(): DraftState {
  const [schema, setSchema] = useState<Schema | null>(null)
  const saved = useRef(loadDraft())
  const [measurements, setMeasurements] = useState<Values>(
    saved.current?.measurements ?? {},
  )
  // 产品层「标准牛仔裤」初始（2026-09-16 用户口径：牛仔裤前口袋挖削式
  // + 袋贴是标配，质疑引擎默认关）：引擎 PatternOptions 默认保持最小
  // 裸版（extract 探针链/金标锚定最小版型，2026-09-16 试改引擎默认因
  // 探针守卫拒绝口袋特征 + 部分 extract 测量组合 facing 默认参数几何
  // 越界而回滚），Web 初始在产品层显式开口袋族。存量 localStorage 缺
  // 键 = 未曾表态，补默认；显式关过的用户键值 false 不受影响。
  const [options, setOptions] = useState<Values>(() => {
    const o: Values = { ...(saved.current?.options ?? {}) }
    for (const k of PRODUCT_POCKET_KEYS) if (!(k in o)) o[k] = true
    return o
  })
  // 推板码表：normalize 兜底（旧存量无键 / 坏数据 -> null = 未配置）
  const [sizeRun, setSizeRunState] = useState<SizeRunSpec | null>(
    () => normalizeSizeRun(saved.current?.size_run).spec)
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
  const [fitting, setFitting] = useState<Snapshot<FittingResult> | null>(null)
  // 快照镜像：ensure* 的"已新鲜即复用"判定读 ref（回调闭包不滞后）
  const sheetRef = useRef<Snapshot<SheetResult> | null>(null)
  sheetRef.current = sheet
  const piecesRef = useRef<Snapshot<PiecesResult> | null>(null)
  piecesRef.current = pieces
  const [errors, setErrors] = useState<IssueDetail[]>([])
  const [warnings, setWarnings] = useState<DraftWarning[]>([])
  const [sheetBusy, setSheetBusy] = useState(false)
  const sheetBusyRef = useRef(false)
  sheetBusyRef.current = sheetBusy
  const [piecesBusy, setPiecesBusy] = useState(false)
  const piecesBusyRef = useRef(false)
  piecesBusyRef.current = piecesBusy
  const [fittingBusy, setFittingBusy] = useState(false)
  const fittingBusyRef = useRef(false)
  fittingBusyRef.current = fittingBusy
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
      localStorage.setItem(STORAGE_KEY,
        JSON.stringify({ measurements, options, size_run: sizeRun }))
    }, 500)
    return () => clearTimeout(t)
  }, [measurements, options, sizeRun])

  // 参数修改即过版本：已有预览保留但标"已过期"，DXF 下载随之禁用
  const setMeasurement = useCallback((key: string, value: unknown) => {
    setMeasurements((prev) => ({ ...prev, [key]: value }))
    bump()
  }, [bump])
  const setOption = useCallback((key: string, value: unknown) => {
    setOptions((prev) => ({ ...prev, [key]: value }))
    bump()
  }, [bump])
  // 推板码表不 bump version（见 DraftState.sizeRun 注释）
  const setSizeRun = useCallback((s: SizeRunSpec | null) => {
    setSizeRunState(s)
  }, [])
  const loadValues = useCallback((m: Values, o: Values,
                                 sizeRun: SizeRunSpec | null = null) => {
    setMeasurements(m)
    setOptions(o)
    setSizeRunState(sizeRun)
    bump()
    // 整体换源状态还原（2026-09-23 用户口径：新建换源后上一草稿的裁片/
    // 3D 不许残留）：旧产物快照只标 stale 不清空，编辑器重挂后仍渲染上
    // 一份裁片、3D 侧仍消费上一份 fitting——换源即作废清空（sheetRef/
    // piecesRef 同步置空，防 ensure*「已新鲜」误判复用），编辑器重挂的
    // ensureSheet 与 3D 重挂的首挂自动试穿按新参数重发；拖拽撤销基线与
    // 校验条同属旧草稿残留，一并清
    sheetRef.current = null
    piecesRef.current = null
    setSheet(null)
    setPieces(null)
    setFitting(null)
    setLastDrag(null)
    setAdjustInfo(null)
    setErrors([])
    setWarnings([])
  }, [bump])

  // 整体还原（「新建」确认后）：重读 localStorage 草稿回到启动初态（选项
  // 缺键补口袋族默认与首挂同口径）——不空置参数，保证选择层「继续上次
  // 草稿」恢复的是最近一次暂存；产物快照/拖拽基线/校验条清空口径同
  // loadValues 换源还原段
  const reset = useCallback(() => {
    const savedNow = loadDraft()
    const o: Values = { ...(savedNow?.options ?? {}) }
    for (const k of PRODUCT_POCKET_KEYS) if (!(k in o)) o[k] = true
    setMeasurements(savedNow?.measurements ?? {})
    setOptions(o)
    setSizeRunState(normalizeSizeRun(savedNow?.size_run).spec)
    bump()
    sheetRef.current = null
    piecesRef.current = null
    setSheet(null)
    setPieces(null)
    setFitting(null)
    setLastDrag(null)
    setAdjustInfo(null)
    setErrors([])
    setWarnings([])
  }, [bump])

  const sheetStale = sheet !== null && sheet.version !== version
  const piecesStale = pieces !== null && pieces.version !== version
  const fittingStale = fitting !== null && fitting.version !== version

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

  // 三个生成动作统一 ref 取参（measRef/optsRef 恒新，闭包不滞后）+
  // 调用时捕获版本号 ver 落快照（生成途中改参数 -> 快照落后于当前
  // version 自然标过期，语义与旧 state 闭包版一致）；返回快照本体，
  // 失败/互斥返回 null（导出中心/高级编辑按需补算直接消费返回值）
  const generateSheet = useCallback(async () => {
    if (piecesBusyRef.current) return null   // 两步互斥（引擎 CPU 密集）
    const ver = versionRef.current
    const payload = { measurements: measRef.current, options: optsRef.current }
    setSheetBusy(true)
    setErrors([])
    try {
      const res = await postSheet(payload)
      const snap = { data: res, version: ver }
      sheetRef.current = snap      // 先同步 ref：紧随其后的 ensurePieces 门控可读
      setSheet(snap)
      setWarnings(res.warnings.map((w) => ({ param: w.param, message: w.message })))
      return snap
    } catch (e) {
      const err = e as Error & { detail?: IssueDetail[] }
      if (err.detail) {
        setErrors(err.detail)
      } else {
        setErrors([{ param: null, group: null, message: String(e), level: 'error' }])
      }
      return null
    } finally {
      setSheetBusy(false)
    }
  }, [])

  const generatePieces = useCallback(async () => {
    // 先画后裁（UI 门控）：整版未生成/已过期/生成中均不开裁片
    const s = sheetRef.current
    if (piecesBusyRef.current || sheetBusyRef.current
        || !s || s.version !== versionRef.current) return null
    const ver = versionRef.current
    const payload = { measurements: measRef.current, options: optsRef.current }
    setPiecesBusy(true)
    setErrors([])
    try {
      const res = await postPieces(payload)
      const snap = { data: res, version: ver }
      piecesRef.current = snap
      setPieces(snap)
      setWarnings(res.warnings.map((w) => ({ param: w.param, message: w.message })))
      return snap
    } catch (e) {
      const err = e as Error & { detail?: IssueDetail[] }
      if (err.detail) {
        setErrors(err.detail)
      } else {
        setErrors([{ param: null, group: null, message: String(e), level: 'error' }])
      }
      return null
    } finally {
      setPiecesBusy(false)
    }
  }, [])

  // 3D 悬挂 payload：与两步生成同构的版本竞态语义；自互斥（重挂/
  // 参数连调高频触发，进行中直接丢弃新请求——调用层 debounce 补发最后
  // 一拍）。不与 sheet/pieces 互斥：互为独立产物，参数变化各自标 stale
  const generateFitting = useCallback(async () => {
    if (fittingBusyRef.current) return null
    fittingBusyRef.current = true
    const ver = versionRef.current
    const payload = { measurements: measRef.current, options: optsRef.current }
    setFittingBusy(true)
    setErrors([])
    try {
      const res = await postFitting(payload)
      const snap = { data: res, version: ver }
      setFitting(snap)
      setWarnings(res.warnings.map((w) => ({ param: w.param, message: w.message })))
      return snap
    } catch (e) {
      const err = e as Error & { detail?: IssueDetail[] }
      if (err.detail) {
        setErrors(err.detail)
      } else {
        setErrors([{ param: null, group: null, message: String(e), level: 'error' }])
      }
      return null
    } finally {
      fittingBusyRef.current = false
      setFittingBusy(false)
    }
  }, [])

  // 按需补算：新鲜（快照存在且 version 一致）直接复用，否则重跑对应
  // 生成动作；generate* 内部已同步 ref，ensurePieces 紧随 ensureSheet
  // 的门控（先画后裁）天然通过。供高级编辑进入与导出中心复用
  const ensureSheet = useCallback(async () => {
    const s = sheetRef.current
    if (s && s.version === versionRef.current) return s
    return generateSheet()
  }, [generateSheet])

  const ensurePieces = useCallback(async () => {
    const p = piecesRef.current
    if (p && p.version === versionRef.current) return p
    const s = await ensureSheet()
    if (!s) return null
    return generatePieces()
  }, [ensureSheet, generatePieces])

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

  const download = useCallback(async (kind: DownloadKind,
                                     opts?: { sizeRun?: SizeRunSpec | null }) => {
    if (dlBusy !== null) return       // 串行：下载重跑引擎，防重复点击
    // 抽屉「保存+导出」同 tick：显式覆盖优先，规避闭包旧值（首次导出必用）
    const sr = opts && 'sizeRun' in opts ? opts.sizeRun : sizeRun
    if (kind === 'sizeRunDxf' && !sr) {
      setErrors([{ param: null, group: null,
                   message: '推板导出缺少码表配置（请先在推板设置抽屉完成配置）',
                   level: 'error' }])
      return
    }
    setDlBusy(kind)
    try {
      // sheetDxf/piecesDxf 载荷不带 size_run：与两步生成严格同构
      const base = { measurements, options }
      if (kind === 'sheetDxf') {
        await downloadFile('/api/dxf?kind=sheet', base, 'sheet.dxf')
      } else if (kind === 'piecesDxf') {
        await downloadFile('/api/dxf?kind=pieces', base, 'pieces.dxf')
      } else if (kind === 'sizeRunDxf') {
        await downloadFile('/api/dxf?kind=size_run', { ...base, size_run: sr },
                           'size_run.dxf')
      } else if (kind === 'nest') {
        // 排料对接（§10.3.2）：JSON 响应只拿数据不落盘（用户口径
        // 2026-09-20：不要默认下载），产物直接返回调用方消费（console
        // 清单打印 + 求解弹窗参数页内存快照，2026-09-22 清单弹窗删除）；
        // 载荷口径同 toml（有码表才带段）
        const res = await postNest(sr ? { ...base, size_run: sr } : base)
        return res
      } else {
        await downloadFile('/api/toml',
                           sr ? { ...base, size_run: sr } : base,
                           'size_draft.toml')
      }
    } catch (e) {
      // 下载失败入 errors（左栏 IssueStrip 呈现）并向上抛出——导出中心
      // 队列按项落账 failed；调用方 void 消费时须自带 catch
      setErrors([{ param: null, group: null, message: `下载失败：${e}`, level: 'error' }])
      throw e
    } finally {
      setDlBusy(null)
    }
  }, [measurements, options, sizeRun, dlBusy])

  return {
    schema, measurements, options, sizeRun,
    setMeasurement, setOption, setSizeRun, loadValues, reset,
    seedShape,
    generateSheet, generatePieces, generateFitting, ensureSheet, ensurePieces,
    download,
    applyAdjust, beginDrag, undoLastDrag, lastDrag, adjustInfo,
    sheet, pieces, fitting,
    sheetReady: sheet !== null, sheetStale,
    piecesReady: pieces !== null, piecesStale,
    fittingStale,
    errors, warnings,
    sheetBusy, piecesBusy, fittingBusy, dlBusy,
    engineState,
    hasSavedDraft: saved.current !== null,
  }
}
