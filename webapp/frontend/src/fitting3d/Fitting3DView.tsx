// 3D 人台视图：three 惰性分包加载（首屏零影响）；MakeHuman 官方 target
// 滑杆试验场（2026-09-13 用户口径：**下半身**切割人台 + 用它的 targets 调节）。
// 链路：loadBodyMesh（base.bin = 切割+站直姿势链产物：粗裁去臂、精裁腰+15、
// 官方 14 场 = 12 measure + 身高 macro ± 已按切割后索引重映射；targets.json
// 带 vendor 地标站 + 身高实测）→ morphPositions(权重) → BufferGeometry 直显；
// 六个部位滑杆双极（−1..+1，正推 site+ 场 / 负推 site− 场）+ 身高滑杆（cm 连续，
// 预设芯片 155/160/165/170 快捷设值，weightFor 按**切割前实测 ΔH** 换算权重——
// 测量驱动、不假设官方 macro 混合约定），拖动实时重 morph + 站点围度实时读数
// （站高取 vendor 地标检测值 × 身高因子；场会微移站高，极端权重下读数有轻微
// 口径偏差，试验场可接受；原生场固有缺陷如 thigh 膝上死区属作者化行为，原样呈现）。
// 坐标口径：顶点 cm、Y-up、脚底 y=0（bin.ts 头注）。
// 衣片展示（2026-09-15 重建三期回落）：用户判定悬挂渲染下裁片形状
// 异常，暂停撑型芯/扇区摆位/引力下垂整链（代码保留：core.ts /
// buildFrontPair / drape.ts，形状验证通过后回归），先**平铺验证**——
// 接收 fitting 快照（useDraft.generateFitting），全部裁片（前/后片、
// 腰头、育克、袋贴）按纸样净样原形逐点等距变换行式平铺在人台旁侧
// 地面上（garment/assemble.ts buildFlatLayout：成对片 L 原样 + R 前中
// 镜像并排、腰头单片），逐片分色（garment/render.ts PIECE_COLORS +
// 侧栏图例），与 2D 裁片 SVG 一比一对照，定位形状问题出在 payload
// 边链/网格还是摆位/解算层；显示层 Group 平移到人台旁侧（人台纯
// 参照）。payload schema v1 照旧（引擎零改动）。独立原则不变：
// 人台滑杆与衣片互不相干。
import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Empty, Slider, Spin } from 'antd'
import {
  CameraOutlined, EyeInvisibleOutlined, EyeOutlined, RedoOutlined,
  UndoOutlined,
} from '@ant-design/icons'
import type * as ThreeT from 'three'
import type { OrbitControls as OrbitControlsT } from 'three/examples/jsm/controls/OrbitControls.js'
import type { BodyMeshAsset } from './bodymesh/bin'
import { loadBodyMesh } from './bodymesh/bin'
import { readGirth } from './bodymesh/slice'
import type { MeshWeights } from './bodymesh/morph'
import { morphPositions } from './bodymesh/morph'
import { heightCm, stationFactor, weightFor } from './bodymesh/height'
import type { FittingResult, Snapshot } from '../types'
import { buildFlatLayout } from './garment/assemble'
import { FLAT_PRIOR } from './garment/priors'
import { buildGarmentView, pieceColor, type GarmentView } from './garment/render'

type ThreeMod = typeof import('three')
type OrbitControlsCtor = typeof import('three/examples/jsm/controls/OrbitControls.js').OrbitControls

// 滑杆部位 <-> base.bin target 槽位（SLOT_ORDER 固定序里的 6 对场）
type Site = 'waist' | 'hips' | 'thigh' | 'knee' | 'calf' | 'ankle'
const SITES: { key: Site; label: string }[] = [
  { key: 'waist', label: '腰' },
  { key: 'hips', label: '臀' },
  { key: 'thigh', label: '大腿' },
  { key: 'knee', label: '膝' },
  { key: 'calf', label: '小腿' },
  { key: 'ankle', label: '踝' },
]
type Sliders = Record<Site, number>

// 预设体型芯片（cm）：权重按 meta.height 实测 ΔH 换算（height.ts weightFor）
const PRESET_CM = [155, 160, 165, 170] as const
// 身高滑杆窗（cm）：官方 macro 域极宽（±1 实测跨 130.7~239.4cm，极端是卡通
// 身高），滑杆钳在常人域 150~185 连续可调（可停任意身高如 162.3）；芯片值
// 全部落在窗内，不受钳制影响
const HEIGHT_SLIDER = { min: 150, max: 185, step: 0.1 }

// 平铺图例中文名（片 key -> 中文；色板在 garment/render.ts PIECE_COLORS）
const CN_PIECE_NAMES: Record<string, string> = {
  front_piece: '前片',
  back_piece: '后片',
  waistband: '腰头',
  back_yoke: '后育克',
  front_facing: '袋贴',
}

interface SceneCtx {
  THREE: ThreeMod
  renderer: ThreeT.WebGLRenderer
  scene: ThreeT.Scene
  camera: ThreeT.PerspectiveCamera
  controls: OrbitControlsT
  render: () => void
  dispose: () => void
}

interface Fitting3DProps {
  fitting: Snapshot<FittingResult> | null
  fittingStale: boolean
  fittingBusy: boolean
  onGenerateFitting: () => void
}

export default function Fitting3DView({
  fitting, fittingStale, fittingBusy, onGenerateFitting,
}: Fitting3DProps) {
  const mountRef = useRef<HTMLDivElement>(null)
  const ctxRef = useRef<SceneCtx | null>(null)
  // 地面格网（场景一次创建；脚底 y=0 恒落地）
  const gridRef = useRef<ThreeT.GridHelper | null>(null)
  const meshRef = useRef<ThreeT.Mesh | null>(null)
  const assetRef = useRef<BodyMeshAsset | null>(null)
  const garmentViewRef = useRef<GarmentView | null>(null)
  const [garmentError, setGarmentError] = useState<string | null>(null)
  // 平铺图例片 key（payload 片序，随 fitting 快照更新；颜色查 render 层色板）
  const [flatKeys, setFlatKeys] = useState<string[]>([])
  const autoTried = useRef(false)
  // 取景基准（mesh 身高 cm；初始机位/视角预设全由它定标，加载前 0）
  const heightRef = useRef(0)
  const flyRaf = useRef(0)
  const [threeMod, setThreeMod] = useState<
    { THREE: ThreeMod; OrbitControls: OrbitControlsCtor } | null>(null)
  const [asset, setAsset] = useState<BodyMeshAsset | null>(null)
  const [assetError, setAssetError] = useState<string | null>(null)
  const [sliders, setSliders] = useState<Sliders>(
    { waist: 0, hips: 0, thigh: 0, knee: 0, calf: 0, ankle: 0 })
  // 身高场权重（−1..+1；与围度滑杆同构的双极权重，0 = 基础身高 ~167.4）
  const [heightW, setHeightW] = useState(0)
  const [girths, setGirths] = useState<Record<Site, number | null>>(
    { waist: null, hips: null, thigh: null, knee: null, calf: null, ankle: null })
  // ---- M2/M3 状态 ----
  // 人台显示三态：0 实体 / 1 半透明（看衣片内侧）/ 2 隐藏
  const [bodyView, setBodyView] = useState<0 | 1 | 2>(0)
  // 旁挂组中心 X（显示层）：前片平铺 Group 的水平中心（组原点在 L 片
  // 左缘，中心 = 组 x + 半宽）；相机取景按「人台 0 ↔ 组中心」的中点
  // 居中双主体。camShift 记上次平移量（幂等，防效应重跑叠加）
  const hangXRef = useRef(0)
  const camShiftRef = useRef(0)

  // ---- three 分包加载（一次） ----
  useEffect(() => {
    let alive = true
    void Promise.all([
      import('three'),
      import('three/examples/jsm/controls/OrbitControls.js'),
    ]).then(([THREE, oc]) => {
      if (alive) setThreeMod({ THREE, OrbitControls: oc.OrbitControls })
    })
    return () => { alive = false }
  }, [])

  // ---- 场景初始化（three 就绪后一次） ----
  useEffect(() => {
    if (!threeMod || !mountRef.current) return
    const { THREE, OrbitControls } = threeMod
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0xf2f1ee)
    const camera = new THREE.PerspectiveCamera(
      38, 1, 0.1, 2000)
    // 初始机位按标准身高兜底，mesh 落地后按 bbox 重定标
    camera.position.set(0, 70, 240)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.target.set(0, 58, 0)
    controls.enableDamping = false
    const hemi = new THREE.HemisphereLight(0xffffff, 0x8a8a95, 1.1)
    const dir = new THREE.DirectionalLight(0xffffff, 1.6)
    dir.position.set(40, 140, 80)
    scene.add(hemi, dir)
    const grid = new THREE.GridHelper(320, 32, 0xc9c9c9, 0xe0e0e0)
    gridRef.current = grid
    scene.add(grid)
    const render = () => { renderer.render(scene, camera) }
    controls.addEventListener('change', render)
    const host = mountRef.current
    host.appendChild(renderer.domElement)
    const resize = () => {
      const w = host.clientWidth || 1, h = host.clientHeight || 1
      renderer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      render()
    }
    const ro = new ResizeObserver(resize)
    ro.observe(host)
    resize()
    ctxRef.current = {
      THREE, renderer, scene, camera, controls, render,
      dispose: () => {
        ro.disconnect()
        controls.removeEventListener('change', render)
        controls.dispose()
        grid.dispose()   // 释放 geometry+material（仅 geometry.dispose 漏材质）
        renderer.dispose()
        renderer.domElement.remove()
        ctxRef.current = null
      },
    }
    return () => { ctxRef.current?.dispose() }
  }, [threeMod])

  // ---- 人台加载（场景就绪后一次）：base.bin 下半身切割网格（w=0）上屏 ----
  useEffect(() => {
    if (!threeMod || !ctxRef.current) return
    let alive = true
    void loadBodyMesh().then((a) => {
      const ctx = ctxRef.current
      if (!alive || !ctx) return
      const { THREE } = ctx
      assetRef.current = a
      heightRef.current = a.height
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position',
        new THREE.Float32BufferAttribute(a.positions.slice(), 3))
      geo.setIndex(new THREE.Uint32BufferAttribute(a.indices, 1))
      geo.computeVertexNormals()
      const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
        color: 0xd8c3b0, roughness: 0.85, metalness: 0.02,
      }))
      ctx.scene.add(mesh)
      meshRef.current = mesh
      // 初始机位按裁切面高定标（正观下半身）
      const h = a.height
      ctx.camera.position.set(0, h * 0.55, h * 1.95)
      ctx.controls.target.set(0, h * 0.47, 0)
      ctx.controls.update()
      ctx.render()
      setAsset(a)
    }).catch((e) => {
      console.error('[fitting3d] 人台数据加载失败', e)
      if (alive) setAssetError(String(e))
    })
    return () => {
      alive = false
      const mesh = meshRef.current
      const ctx = ctxRef.current
      if (mesh && ctx) {
        ctx.scene.remove(mesh)
        mesh.geometry.dispose()
        ;(mesh.material as ThreeT.MeshStandardMaterial).dispose()
        meshRef.current = null
      }
      assetRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threeMod])

  // ---- 站点查询表（vendor 地标站：站高 + body/leg 口径，w=0 值） ----
  const stationOf = useMemo(() => {
    const m = new Map<Site, { y: number; per: 'body' | 'leg' }>()
    if (asset) {
      for (const key of Object.keys(asset.stations) as Site[]) {
        const st = asset.stations[key]
        if (st) m.set(key, st)
      }
    }
    return m
  }, [asset])

  // ---- 滑杆 -> 实时重 morph + 围度读数（in-place 写 position attr） ----
  useEffect(() => {
    const ctx = ctxRef.current
    const mesh = meshRef.current
    const a = assetRef.current
    if (!ctx || !mesh || !a) return
    // 双极值 -> 场权重：正推 site+、负推 site−（两场独立作者化，非反对称）；
    // 身高同构（height+/height- 全场，预设芯片只快捷设值不限制滑杆）
    const w: MeshWeights = {}
    for (const { key } of SITES) {
      const v = sliders[key]
      if (v > 0) w[`${key}+`] = v
      else if (v < 0) w[`${key}-`] = -v
    }
    if (heightW > 0) w['height+'] = heightW
    else if (heightW < 0) w['height-'] = -heightW
    const pos = morphPositions(a, w)
    const attr = mesh.geometry.getAttribute('position') as ThreeT.BufferAttribute
    ;(attr.array as Float32Array).set(pos)
    attr.needsUpdate = true
    mesh.geometry.computeVertexNormals()
    ctx.render()
    // 站点围度：站高随身高因子缩放（身高场近似等比，比例近似口径）
    const sf = stationFactor(a.heightInfo, heightW)
    const read: Record<Site, number | null> = {
      waist: null, hips: null, thigh: null, knee: null, calf: null, ankle: null }
    for (const { key } of SITES) {
      const st = stationOf.get(key)
      if (st) {
        read[key] = readGirth(pos, a.indices, st.y * sf, st.per)
      }
    }
    setGirths(read)
    // stationOf 随 asset 派生，asset 变化时本效应重跑取基线读数
  }, [sliders, heightW, asset, stationOf])

  // ---- 人台显示三态（实体 / 半透明看衣服内侧 / 隐藏；直接改不重建） ----
  useEffect(() => {
    const ctx = ctxRef.current
    const mesh = meshRef.current
    if (!ctx || !mesh) return
    const mat = mesh.material as ThreeT.MeshStandardMaterial
    mesh.visible = bodyView !== 2
    mat.transparent = bodyView === 1
    mat.opacity = bodyView === 1 ? 0.3 : 1
    mat.needsUpdate = true
    ctx.render()
  }, [bodyView, asset])

  // ---- 裁片上屏（重建三期回落：全裁片平铺验证）----
  // payload -> 逐片网格 -> 全裁片行式平铺在人台旁侧地面、按片分色
  // （与 2D 裁片 SVG 一比一，定位形状问题出在哪层）。依赖
  // [fitting, asset]：消费 payload 全部片（引擎零改动）；asset 守卫
  // 相机取景时序（人台先落位再让位）。悬挂链（撑型芯 + 扇区摆位 +
  // 引力下垂）暂停接线，代码保留待验证后回归。
  useEffect(() => {
    const ctx = ctxRef.current
    const a = assetRef.current
    if (!ctx || !a || !fitting) return
    const scene = ctx.scene   // 闭包捕获：卸载时更早声明的效应已清 ctxRef
    let gv: GarmentView | null = null
    try {
      const data = fitting.data
      if (data.pieces.length === 0) throw new Error('fitting payload 缺裁片')
      const garment = buildFlatLayout(data)
      setFlatKeys(data.pieces.map((p) => p.key))
      const view = buildGarmentView(ctx.THREE, garment)
      gv = view
      // 旁挂：平铺组左缘 = 人台水平半宽 + 净空（基础网格量一次，morph
      // 增量由 clearance 兜底）；组中心驱动取景让位
      let bodyHalfW = 0
      for (let i = 0; i < a.positions.length; i += 3) {
        const ax = Math.abs(a.positions[i])
        if (ax > bodyHalfW) bodyHalfW = ax
      }
      let flatW = 0
      for (let i = 0; i < garment.pos.length; i += 3) {
        if (garment.pos[i] > flatW) flatW = garment.pos[i]
      }
      const offsetX = bodyHalfW + FLAT_PRIOR.clearance
      view.group.position.x = offsetX
      view.group.position.y = FLAT_PRIOR.lift
      scene.add(view.group)
      garmentViewRef.current = view
      setGarmentError(null)
      hangXRef.current = offsetX + flatW / 2
      // 取景让位（幂等：按与上次中心的差量平移，保留用户自由视角）：
      // 双主体（人台+平铺组）中点 = 组中心/2
      const half = hangXRef.current / 2
      const d = half - camShiftRef.current
      if (Math.abs(d) > 1e-6) {
        ctx.camera.position.x += d
        ctx.controls.target.x += d
        ctx.controls.update()
        camShiftRef.current = half
      }
      ctx.render()
    } catch (e) {
      console.error('[fitting3d] 前片构建失败', e)
      setGarmentError(e instanceof Error ? e.message : String(e))
    }
    return () => {
      if (gv) { scene.remove(gv.group); gv.dispose() }
      garmentViewRef.current = null
    }
  }, [fitting, asset])

  // ---- 自动首挂（仅一次）：进系统即有衣服；失败不自动重试（按钮兜底） ----
  useEffect(() => {
    if (autoTried.current) return
    if (fitting === null && !fittingBusy) {
      autoTried.current = true
      onGenerateFitting()
    }
  }, [fitting, fittingBusy, onGenerateFitting])

  // ---- 视角预设（球面插值 ~300ms；OrbitControls 随时可继续自由拖） ----
  // 机位 x 以双主体中点居中（人台 0 ↔ 平铺组中心 hangXRef）
  const flyTo = (view: 'front' | 'side' | 'back' | 'iso') => {
    const ctx = ctxRef.current
    if (!ctx || heightRef.current <= 0) return
    const h = heightRef.current
    const cx = hangXRef.current / 2
    const d = h * 1.6, y = h * 0.47
    const target: [number, number, number] = view === 'front'
      ? [cx, y, d]
      : view === 'side' ? [d + cx, y, 0]
      : view === 'back' ? [cx, y, -d]
      : [h * 0.95 + cx, h * 0.9, h * 0.95]
    const from = ctx.camera.position.clone()
    const to = new ctx.THREE.Vector3(...target)
    const t0 = performance.now()
    cancelAnimationFrame(flyRaf.current)
    const tick = () => {
      const t = Math.min(1, (performance.now() - t0) / 300)
      const e = t * (2 - t)          // easeOutQuad
      ctx.camera.position.lerpVectors(from, to, e)
      ctx.controls.update()
      ctx.render()
      if (t < 1) flyRaf.current = requestAnimationFrame(tick)
    }
    flyRaf.current = requestAnimationFrame(tick)
  }

  const screenshot = () => {
    const ctx = ctxRef.current
    if (!ctx) return
    ctx.render()      // 同步渲染一次再取（无需 preserveDrawingBuffer 常驻）
    const a = document.createElement('a')
    a.href = ctx.renderer.domElement.toDataURL('image/png')
    a.download = 'fitting3d.png'
    a.click()
  }

  const loading = threeMod === null || (!asset && !assetError)
  const fmt = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(2)}`
  // 当前身高（cm）：芯片高亮判据（换算回算精确，滑杆拖到同值同样命中）
  const curHeightCm = asset ? heightCm(asset.heightInfo, heightW) : null
  const presetActive = (cm: number) =>
    curHeightCm !== null && Math.abs(curHeightCm - cm) < 0.05

  return (
    <div className="fitting3d">
      <div className="fitting3d-stage" ref={mountRef}>
        <div className="fitting3d-views">
          {(['front', 'side', 'back', 'iso'] as const).map((v) => (
            <Button key={v} size="small"
              onClick={() => flyTo(v)}>
              {v === 'front' ? '正面' : v === 'side' ? '侧面'
                : v === 'back' ? '背面' : '斜 45°'}
            </Button>
          ))}
        </div>
        {loading && (
          <div className="fitting3d-loading">
            <Spin tip={threeMod === null ? '加载 3D 引擎…' : '加载人台数据…'} />
          </div>
        )}
        {assetError && !loading && (
          <div className="fitting3d-loading">
            <Empty description="人台数据加载失败" />
          </div>
        )}
      </div>
      <div className="fitting3d-side">
        <div className="f3d-card">
          <div className="f3d-card-title">裁片</div>
          <div className="f3d-row">
            <span>全裁片平铺 · 按片分色</span>
            <Button size="small" icon={<RedoOutlined />}
              loading={fittingBusy}
              onClick={() => onGenerateFitting()}>
              重新生成
            </Button>
          </div>
          {flatKeys.length > 0 && (
            <div className="f3d-legend">
              {flatKeys.map((k) => (
                <span key={k} className="f3d-legend-item">
                  <span className="f3d-legend-dot" style={{
                    background: `#${pieceColor(k).toString(16).padStart(6, '0')}`,
                  }} />
                  {CN_PIECE_NAMES[k] ?? k}
                </span>
              ))}
            </div>
          )}
          <div className="f3d-hint">
            平铺 = 纸样净样原形（与 2D 裁片 SVG 一比一对照）；成对片
            L+R 并排、腰头单片；悬挂渲染暂停，形状验证通过后回归
          </div>
          {fittingStale && (
            <div className="f3d-hint">参数已改，展示待更新</div>
          )}
          {garmentError && (
            <div className="f3d-hint f3d-hint-err">{garmentError}</div>
          )}
        </div>

        <div className="f3d-card">
          <div className="f3d-card-title">预设体型</div>
          <div className="f3d-presets">
            {PRESET_CM.map((cm) => (
              <Button key={cm} size="small"
                type={presetActive(cm) ? 'primary' : 'default'}
                disabled={!asset}
                onClick={() => {
                  setHeightW(weightFor(asset!.heightInfo, cm))
                }}>
                {cm}
              </Button>
            ))}
            <Button size="small"
              type={heightW === 0 ? 'primary' : 'default'}
              disabled={!asset}
              onClick={() => {
                setHeightW(0)
              }}>
              默认
            </Button>
          </div>
          <div className="f3d-hint">
            芯片 = 快捷身高档（按实测 ΔH 换算权重）；身高连续可调见下方滑杆
          </div>
        </div>

        <div className="f3d-card">
          <div className="f3d-card-title">
            形体滑杆（MakeHuman targets）
          </div>
          {SITES.map(({ key, label }) => (
            <div key={key} className="f3d-slider">
              <div className="f3d-slider-head">
                <span>{label}</span>
                <span className="f3d-slider-val">
                  {girths[key] !== null
                    ? `${girths[key]!.toFixed(1)} cm` : ''}
                  <code>{fmt(sliders[key])}</code>
                </span>
              </div>
              <Slider
                min={-1} max={1} step={0.05}
                value={sliders[key]}
                disabled={!asset}
                onChange={(v) => {
                  setSliders((s) => ({ ...s, [key]: v }))
                }}
              />
            </div>
          ))}
          <div className="f3d-slider">
            <div className="f3d-slider-head">
              <span>身高</span>
              <span className="f3d-slider-val">
                {curHeightCm !== null ? `${curHeightCm.toFixed(1)} cm` : ''}
              </span>
            </div>
            <Slider
              min={HEIGHT_SLIDER.min} max={HEIGHT_SLIDER.max}
              step={HEIGHT_SLIDER.step}
              value={curHeightCm ?? HEIGHT_SLIDER.min}
              disabled={!asset}
              onChange={(cm) => {
                setHeightW(weightFor(asset!.heightInfo, cm))
              }}
            />
          </div>
          <Button size="small" icon={<UndoOutlined />}
            disabled={!asset}
            onClick={() => {
              setSliders(
                { waist: 0, hips: 0, thigh: 0, knee: 0, calf: 0, ankle: 0 })
              setHeightW(0)
            }}>
            全部归零
          </Button>
          <div className="f3d-hint">
            正/负 = 增/减场权重（w=1 为 MakeHuman 作者化上限）；身高滑杆 cm 连续
          </div>
        </div>

        <div className="f3d-card">
          <div className="f3d-card-title">显示</div>
          <div className="f3d-row">
            <span>人台</span>
            <Button size="small" type="text"
              icon={bodyView === 2 ? <EyeInvisibleOutlined />
                : <EyeOutlined />}
              onClick={() => setBodyView((v) => ((v + 1) % 3) as 0 | 1 | 2)}>
              {['实体', '半透明', '隐藏'][bodyView]}
            </Button>
          </div>
          <div className="f3d-hint">半透明人台可看衣片内侧</div>
        </div>

        <div className="f3d-card f3d-actions">
          <Button size="small" icon={<CameraOutlined />} onClick={screenshot}>
            截图 PNG
          </Button>
        </div>
      </div>
    </div>
  )
}
