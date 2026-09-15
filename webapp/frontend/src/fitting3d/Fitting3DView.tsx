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
// 二期试穿链（2026-09-14 悬挂展示；同日晚解耦定型）：接收 fitting 快照
// （useDraft.generateFitting），前后片+育克+直腰头布片缝合——解算在
// **纸样系**进行（y=纸样高），碰撞体 = 纸样围度撑型芯（core.ts，
// girth_finished 逐站取值 → 圆筒按构造成立、廓形=版型），**不消费人台
// 几何**；显示层整体 X 偏移把整裤平移到人台旁侧悬挂（晾衣架观感；人台
// 纯参照）。穿台显示口径与应变热力图退役（代码留档）。独立原则贯彻到
// 解算：人台滑杆与裤子互不相干；合体度只经松量读数表达。
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
import { bodyLandmarksOf, buildWarp } from './garment/align'
import { buildCore } from './garment/core'
import { buildClothMesh } from './garment/mesh'
import { buildBodyField } from './garment/placement'
import { buildGarment, buildWaistRing } from './garment/seams'
import type { Garment } from './garment/seams'
import { HANG_PRIOR, SOLVER_PRIOR } from './garment/priors'
import { easeRows, type EaseRow } from './garment/ease'
import {
  buildGarmentView, buildWaistRingMesh, type GarmentView,
} from './garment/render'
import { useGarment, type SolverStatus } from './garment/useGarment'

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
// 松量读数站名（payload FittingStationKey；crotch 分叉站不出现）
const EASE_LABEL: Record<string, string> = {
  waist: '腰', hip: '臀', thigh: '大腿', knee: '膝', hem: '脚口',
}
// 解算状态角标（悬挂：build→成形动画→settled，约 4~5s）
const SOLVER_LABEL: Record<SolverStatus, string> = {
  idle: '未悬挂',
  building: '构建整裤…',
  running: '悬挂成形…',
  settled: '已悬挂',
  frozen: '已暂停（发散兜底）',
}
// 身高滑杆窗（cm）：官方 macro 域极宽（±1 实测跨 130.7~239.4cm，极端是卡通
// 身高），滑杆钳在常人域 150~185 连续可调（可停任意身高如 162.3）；芯片值
// 全部落在窗内，不受钳制影响
const HEIGHT_SLIDER = { min: 150, max: 185, step: 0.1 }

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
  const ringMeshRef = useRef<ThreeT.Mesh | null>(null)
  const [garmentError, setGarmentError] = useState<string | null>(null)
  // 弯腰头回退提示（bandFallback 非空 = 视觉环带、无真实布片缝合）
  const [curvedBand, setCurvedBand] = useState(false)
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
  // 人台显示三态：0 实体 / 1 半透明（看裤子内侧）/ 2 隐藏
  const [bodyView, setBodyView] = useState<0 | 1 | 2>(0)
  // 松量读数（settled 时算一次；null=未算）
  const [easeData, setEaseData] = useState<EaseRow[] | null>(null)
  const garmentRef = useRef<Garment | null>(null)
  const warpRef = useRef<((y: number) => number) | null>(null)
  const lastPosRef = useRef<Float32Array | null>(null)
  // 悬挂偏移（显示层）：裤筒 Group 平移到人台 +X 侧；相机取景按半偏移
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

  // ---- 衣服静态上屏（M0）：payload -> 撑型芯场 -> 初始摆位 ----
  // 依赖 [fitting, asset]：asset 只为松量读数的人台侧 warp（解算本体在
  // 纸样系、不消费人台几何——2026-09-14 解耦）。悬挂口径：初始摆位是
  // 裙形（缝未闭），visible=false 只藏静态裙形；首帧起播放成形动画
  // （解算逐帧流回），终态 = 圆筒悬挂。
  useEffect(() => {
    const ctx = ctxRef.current
    const mesh = meshRef.current
    const a = assetRef.current
    if (!ctx || !mesh || !a || !fitting) return
    const scene = ctx.scene   // 闭包捕获：卸载时更早声明的效应已清 ctxRef
    let gv: GarmentView | null = null
    let ring: ThreeT.Mesh | null = null
    try {
      const data = fitting.data
      const front = data.pieces.find((p) => p.key === 'front_piece')
      const back = data.pieces.find((p) => p.key === 'back_piece')
      if (!front || !back) throw new Error('fitting payload 缺前/后片')
      const yoke = data.pieces.find((p) => p.key === 'back_yoke')
      const pocket = data.pieces.find((p) => p.key === 'front_facing')
      const meshes = {
        front: buildClothMesh(front),
        back: buildClothMesh(back),
        ...(yoke ? { yoke: buildClothMesh(yoke) } : {}),
        ...(pocket ? { pocket: buildClothMesh(pocket) } : {}),
      }
      // warp 仅服务松量读数的人台侧切片（身高/体型站高映射）
      const warp = buildWarp(data.body.stations, bodyLandmarksOf(a))
      const core = buildCore(data)
      const field = buildBodyField(core.positions, core.indices)
      const identity = (y: number): number => y
      const garment = buildGarment(meshes, data, identity, field)
      garmentRef.current = garment
      warpRef.current = warp
      setEaseData(null)
      gv = buildGarmentView(ctx.THREE, garment)
      // 悬挂偏移：裤筒整体平移到人台 +X 侧（显示层；worker 几何空间
      // 不变）。净空 = 偏移 − 人台 maxR − 裤筒半径(maxR+gap) = clearance；
      // 整裤抬 hemLift 让裤口离地（hem 站 y=0 恰落地会与地面格网共面打架）
      const offsetX = 2 * field.maxRadius + SOLVER_PRIOR.garmentGap
        + HANG_PRIOR.clearance
      hangXRef.current = offsetX
      gv.group.position.x = offsetX
      gv.group.position.y = HANG_PRIOR.hemLift
      gv.group.visible = false   // 初始摆位是裙形（缝未闭合），藏到松弛单帧
      scene.add(gv.group)
      garmentViewRef.current = gv
      if (garment.bandFallback) {
        // 视觉环带沿钉住的腰口弧逐点成环（贴合裤身顶口，不再平环悬空）
        const rb = buildWaistRing(garment)
        ring = buildWaistRingMesh(ctx.THREE, rb)
        ring.position.x = offsetX
        ring.position.y = HANG_PRIOR.hemLift
        ring.visible = false
        scene.add(ring)
      }
      ringMeshRef.current = ring
      setCurvedBand(!!garment.bandFallback)
      setGarmentError(null)
      // 取景让位（幂等：按与上次中心的差量平移，保留用户自由视角）：
      // 双主体（人台+裤子）中点为 offset/2
      const half = offsetX / 2
      const d = half - camShiftRef.current
      if (Math.abs(d) > 1e-6) {
        ctx.camera.position.x += d
        ctx.controls.target.x += d
        ctx.controls.update()
        camShiftRef.current = half
      }
      ctx.render()
    } catch (e) {
      console.error('[fitting3d] 衣服构建失败', e)
      setGarmentError(e instanceof Error ? e.message : String(e))
    }
    return () => {
      if (gv) { scene.remove(gv.group); gv.dispose() }
      if (ring) {
        scene.remove(ring)
        ring.geometry.dispose()
        ;(ring.material as ThreeT.MeshStandardMaterial).dispose()
      }
      garmentViewRef.current = null
      garmentRef.current = null
      warpRef.current = null
      ringMeshRef.current = null
      setCurvedBand(false)
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

  // ---- M1 解算链：sim worker（纸样系撑型芯）帧直写 garment mesh ----
  // init 只带 payload（2026-09-14 解耦：人台几何不出现在解算里）
  const sim = useGarment(fitting)
  useEffect(() => sim.onFrame((pos) => {
    lastPosRef.current = pos
    const gv = garmentViewRef.current
    if (gv) {
      gv.update(pos)
      gv.group.visible = true   // 首帧揭幕，此后成形动画逐帧直写
    }
    const ring = ringMeshRef.current
    if (ring) ring.visible = true
    ctxRef.current?.render()
  }), [sim.onFrame])

  // ---- 松量读数（M2）：settled（悬挂单帧）时切片一次 ----
  // 整裤侧在纸样系 st.y 切；人台侧经 warp 在人台高度切（纯显示参照）
  useEffect(() => {
    if (sim.status !== 'settled') return
    const garment = garmentRef.current
    const pos = lastPosRef.current
    const warp = warpRef.current
    const mesh = meshRef.current
    const a = assetRef.current
    if (!garment || !pos || !warp || !mesh || !a || !fitting) return
    const attr = mesh.geometry.getAttribute('position') as ThreeT.BufferAttribute
    setEaseData(easeRows(garment, pos, fitting.data.body.stations, warp,
      attr.array as Float32Array, a.indices))
  }, [sim.status])

  // ---- 视角预设（球面插值 ~300ms；OrbitControls 随时可继续自由拖） ----
  // 机位 x 以悬挂偏移半量居中（人台+裤子双主体）
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
          <div className="f3d-card-title">悬挂</div>
          <div className="f3d-row">
            <span>{SOLVER_LABEL[sim.status]}</span>
            {sim.status === 'settled' && sim.capped && (
              <span className="f3d-hint">
                （600 帧未静止，已取终态）
              </span>
            )}
            <div>
              <Button size="small" icon={<RedoOutlined />}
                loading={fittingBusy}
                onClick={() => onGenerateFitting()}>
                重新悬挂
              </Button>{' '}
              <Button size="small"
                disabled={sim.status === 'idle'}
                onClick={() => sim.restart()}>
                重置解算
              </Button>
            </div>
          </div>
          <div className="f3d-hint">
            裤子解算只用纸样围度（撑型芯），与人台滑杆互不相干
          </div>
          {curvedBand && (
            <div className="f3d-hint">
              腰头现为视觉环带（沿腰口弧贴合）：弯腰头净样非矩形、口袋
              挖削款腰口弧缺段，均无真实腰头布片缝合（直腰头无挖削才参与）
            </div>
          )}
          {sim.seamErr && (
            <div className="f3d-hint">
              缝合误差 均值 {sim.seamErr.avg.toFixed(2)} / P95 {' '}
              {sim.seamErr.p95.toFixed(2)} cm
            </div>
          )}
          {fittingStale && (
            <div className="f3d-hint">参数已改，悬挂结果待更新</div>
          )}
          {(garmentError ?? sim.simError) && (
            <div className="f3d-hint f3d-hint-err">
              {garmentError ?? sim.simError}
            </div>
          )}
        </div>

        <div className="f3d-card">
          <div className="f3d-card-title">松量读数</div>
          {easeData ? (
            <table className="f3d-ease">
              <thead>
                <tr>
                  <th />
                  <th>成衣</th><th>人台</th><th>松量</th><th>纸样</th>
                </tr>
              </thead>
              <tbody>
                {easeData.map((r) => (
                  <tr key={r.key}>
                    <td>{EASE_LABEL[r.key]}</td>
                    <td>{r.sim === null ? '—' : r.sim.toFixed(1)}</td>
                    <td>{r.body === null ? '—' : r.body.toFixed(1)}</td>
                    <td>{r.ease === null ? '—'
                      : `${r.ease > 0 ? '+' : ''}${r.ease.toFixed(1)}`}</td>
                    <td>{r.pattern === null ? '—' : r.pattern.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="f3d-hint">悬挂就绪后自动切片测量（cm）</div>
          )}
          <div className="f3d-hint">
            成衣=整裤切片围度（跨缝闭环）；松量=成衣−人台；纸样=引擎
            girth_finished（设计目标）。正值松、负值绷
          </div>
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
          <div className="f3d-hint">半透明人台可看裤子内侧</div>
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
