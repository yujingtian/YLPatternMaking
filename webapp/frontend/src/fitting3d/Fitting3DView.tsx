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
// 衣片展示（2026-09-15 三期平铺验证 → 2026-09-16 四期前身缝合立起 →
// 同日五期前身自由垂 → 同日六期后身缝合 + 同日「拉直」整圈钉直挂）：
// 平铺验证通过与 2D 裁片 SVG 一比一对照后，悬挂链回归——前身组（前片
// +袋贴沿 mouth 缝合成并集宿主，garment/panel.ts）走前 90° 扇区摆位
// → verlet 引力**自由垂**（garment/drape.ts：前中 rise 链缝合对 + 腰
// 口整圈全向钉直挂 + 地面碰撞，无撑型芯——芯撑出的前凸筒不是真实提
// 着前片的形态；直挂下顶缘按摆位弧全撑、布条自顶缘竖直垂下、中缝保
// 持在前中/后中不塌轴、下摆离地〔2026-09-17 hangLift 整体抬升 + 侧缝
// 边语义摆位 θ=±90° + 顶部腰头刚度带钉——顶部〔腰头缝合线〕圆弧、
// 不拖地〕），
// 前片/袋贴作为贴层（garment/rider.ts）逐帧回填渲染、逐片分色
// （render.ts PIECE_COLORS + 侧栏图例），袋贴径向内偏衬里侧（口径
// 「前片在前口袋上面」）；后身组（后片+育克沿机头下口线缝合并集宿主
// buildBackPanel）同款悬挂：后 90° 扇区摆位 + 后中 cb 缝合对自由垂，
// 筒并排在前身筒右侧（有省款守卫拦下 → 育克留平铺纯后片悬挂）；其余
// 裁片（腰头）照旧平铺人台旁侧地面（buildFlatLayout exclude 前后身
// 组）。独立原则：撑型芯锚**纸样围度**（payload stations，与人台滑杆
// 互不相干），现仅用于初摆位半径与取景包络；前后身旁挂人台 +X 侧不
// 套轴。payload schema v1 照旧（引擎零改动）。
// 穿台（2026-09-18 双视图 → 2026-09-19 旁挂视图退役，恒穿台，用户口径
// 「旁挂暂时不需要」——旁挂分支/纸样芯场链留 git 史，core.ts 的
// buildCore/buildLegAxis 转测试专用）。穿台 = 整裤套轴穿在人台上：碰撞体
// 换人台 morph 切片环场（buildBodyField 喂平移后网格；锚定 = 纸样腰站 ↔
// 人台腰地标，θ 两系同构只 Y 平移），落位 = settle.ts 落位控制器（拉到
// 腰 → 前后裆探针驱动钉高独立缓释 → 零穿透静止 = 真人「裆不舒服一点点
// 往下」的仿真翻译），读数 = 掉裆/裆接触/最差穿透（tooSmall 偏小信号——
// 读数不是自动调版闭环；独立原则不变：滑杆不改 payload，重穿走
// 「重新试穿」按钮）。
import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Empty, Slider, Spin, Switch } from 'antd'
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
import { buildFlatLayout, buildFullPair, type Garment } from './garment/assemble'
import {
  buildBodyField, buildLegAxisFromRings, buildWaistRing, shiftPositionsY,
} from './garment/placement'
import { buildDrape, type DrapeSim } from './garment/drape'
import {
  buildCrotchProbeIdx, type CrotchContact, type DressReport,
} from './garment/settle'
import { buildClothMesh } from './garment/mesh'
import { buildBackPanel, buildFrontPanel } from './garment/panel'
import { bindRider } from './garment/rider'
import { bandBottomChain, buildWaistbandMesh } from './garment/band'
import { FIELD_PRIOR, FLAT_PRIOR, HANG_PRIOR } from './garment/priors'
import { computeHeat } from './garment/heatmap'
// worker 协议（type-only：dressWorker 有模块级副作用，运行时不得引入主线程）
import type { WorkerOut } from './garment/dressWorker'
import { toSolveState, transferBuffers } from './garment/solvestate'
import {
  buildGarmentView, buildRiderView, buildSimView, pieceColor,
  type GarmentView, type RiderView, type SimView,
} from './garment/render'

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
// 图例固定片序：payload 里没有的片灰显「未开启」（袋贴/育克是可选
// 工艺开关，默认关——用户看不到该片时先看这里，参数面板开启后重新生成）
const PIECE_LEGEND_ORDER = [
  'front_piece', 'back_piece', 'waistband', 'back_yoke', 'front_facing',
]

// 滑杆/身高 -> morph 场权重（morph 效应、穿台效应、stale 判定三处同源；
// 正推 site+、负推 site−，两场独立作者化非反对称；身高同构 height±）
const weightsFrom = (sliders: Sliders, heightW: number): MeshWeights => {
  const w: MeshWeights = {}
  for (const { key } of SITES) {
    const v = sliders[key]
    if (v > 0) w[`${key}+`] = v
    else if (v < 0) w[`${key}-`] = -v
  }
  if (heightW > 0) w['height+'] = heightW
  else if (heightW < 0) w['height-'] = -heightW
  return w
}

// 穿台读数接触文案（pen 穿透 / touch 贴合 / gap 间隙）
const contactText = (c: CrotchContact): string =>
  c.kind === 'pen' ? `穿透 ${c.value.toFixed(1)} cm`
    : c.kind === 'gap' ? `间隙 ${c.value.toFixed(1)} cm` : '贴合'

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
  // 前后身并集退化提示（panel.warnings：无袋贴/育克/守卫拦下时该组员留平铺）
  const [panelHint, setPanelHint] = useState<string | null>(null)
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
  // 场景中心 X（显示层）：全场景水平包络（人台左沿 ~ 平铺组右沿）的
  // 中点；相机取景/视角预设按它居中双主体（人台+悬挂筒 ↔ 平铺组）。
  // camShift 记上次平移量（幂等，防效应重跑叠加）
  const hangXRef = useRef(0)
  const camShiftRef = useRef(0)
  // ---- 穿台（2026-09-18 双视图 → 2026-09-19 旁挂退役恒穿台）+ 落位读数 ----
  // dressEpoch 重新试穿 = ++（大效应重跑重解算）；
  // dressStale = 滑杆变化后穿着与当前人台不一致（提示重穿，不自动闭环）；
  // dressRunW = 本次穿台权重快照（stale 判据）
  const [dressEpoch, setDressEpoch] = useState(0)
  const [dressStale, setDressStale] = useState(false)
  const [dressReport, setDressReport] = useState<DressReport | null>(null)
  const dressRunW = useRef<MeshWeights | null>(null)
  // 热力图（2026-09-18 双通道 → 2026-09-19 应变通道移除，恒间隙通道）：
  // 开关只重着色当前帧不重跑仿真——heatOnRef 镜像供开关效应与解算 init
  // 透传（不进大效应 deps，避免重跑重解算）。Worker 化（2026-09-23）后
  // 着色语义三路：setHeat = 走 worker 通道（解算中后续节拍帧带 heat +
  // 立即回传当前帧一层；终态即时重算回传）、applyHeat = worker 回传数组
  // 就地重着色、clear = 本地恢复分色
  const [heatOn, setHeatOn] = useState(false)
  const heatOnRef = useRef(false)
  const dressViewsRef = useRef<{
    /** 热力图开：worker 通道重算回传（帧内节拍/终态/即时三层） */
    setHeat: (on: boolean) => void
    /** worker 回传 heat 数组 → 当前帧重着色 */
    applyHeat: (v: Float32Array) => void
    /** 恢复分色材质 */
    clear: () => void
  } | null>(null)
  // 穿台效应冻结读取滑杆（效应不随滑杆重跑——独立原则，重穿走 epoch）
  const slidersRef = useRef(sliders)
  slidersRef.current = sliders
  const heightWRef = useRef(heightW)
  heightWRef.current = heightW

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
    // 双极值 -> 场权重（weightsFrom 同源：morph/穿台/stale 三处一致）
    const w = weightsFrom(sliders, heightW)
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

  // ---- 穿台 stale 判定：滑杆/身高 vs 本次穿台权重快照（独立原则：不自动
  // 重穿，提示用户点「重新试穿」——试穿是读数不是闭环） ----
  useEffect(() => {
    if (dressRunW.current === null) return
    setDressStale(JSON.stringify(weightsFrom(sliders, heightW))
      !== JSON.stringify(dressRunW.current))
  }, [sliders, heightW])

  // ---- 热力图开关：只对当前帧重着色（refs 即时读，不重跑仿真）。
  // 穿台大效应重建（重试穿）时 startup 已按 heatOnRef 补画；
  // Worker 化后开 = worker 通道即时回传一层 ----
  useEffect(() => {
    heatOnRef.current = heatOn
    const dv = dressViewsRef.current
    if (!dv) return
    if (heatOn) dv.setHeat(true)
    else dv.clear()
  }, [heatOn])

  // ---- 裁片上屏（八期整裤缝合：单 sim 四 part 自由垂 + 其余平铺）----
  // 前身组 = 前片+袋贴沿 mouth 缝合的并集宿主（panel.ts，守卫失败退化
  // 纯前片 + 袋贴留平铺）；后身组双轨（2026-09-22）：无省 = 后片+育克
  // 并集宿主；有省（闭省净样款）= 育克升格 sim 参与片缝合（seam 模式，
  // yokeWaist/yokeCb/yokeWeld 缝族 + 直渲视图，九期腰头同模式）。八期
  // 把两筒合并为**一条完整整裤**单
  // sim：buildFullPair 四 part 摆位（腰圆 360° 整圈弧长重参数化 + 侧缝
  // 语义竖直 + 腿局部圆环绕管 + 内缝落腿内侧线）→ seams.buildSeamSet
  // 四族缝合对（前中/后中镜像 + 侧缝/内缝弧长 + 四裆尖焊拢汇集裆交叉
  // 点）→ drape 自由垂（腰部圆形撑开、其余真实物理垂挂）。
  // 腰圆整圈钉挂 + sideHold 刚度带暂代腰头（本期不含腰头）。前片/袋贴/
  // 后片/育克作为贴层（rider.ts 绑定宿主三角形）逐帧回填渲染，宿主不
  // 渲染，袋贴径向内偏衬里侧。其余裁片照旧平铺（exclude 前后身组）。
  // 依赖 [fitting, asset, dressEpoch]：asset 守卫相机取景时序（人台先落位
  // 再让位）；dressEpoch 重试穿 = 效应重跑。
  // 穿台滑杆值经 slidersRef/heightWRef 冻结读取（滑杆变化不重跑——独立
  // 原则，stale 效应只提示不闭环）。
  useEffect(() => {
    const ctx = ctxRef.current
    const a = assetRef.current
    if (!ctx || !a || !fitting) return
    const scene = ctx.scene   // 闭包捕获：卸载时更早声明的效应已清 ctxRef
    let gv: GarmentView | null = null
    let hv: RiderView | null = null
    let hfv: RiderView | null = null
    let bv: RiderView | null = null
    let byv: RiderView | null = null
    const yokeViews: { v: SimView; off: number }[] = []   // seam 模式育克直渲
    let wbv: SimView | null = null
    let raf = 0
    let worker: Worker | null = null   // 解算 worker（try 内创建；cleanup terminate）
    try {
      const data = fitting.data
      if (data.pieces.length === 0) throw new Error('fitting payload 缺裁片')
      // 人台水平半宽（基础网格量一次，morph 增量由 clearance 兜底）
      let bodyHalfW = 0
      for (let i = 0; i < a.positions.length; i += 3) {
        const ax = Math.abs(a.positions[i])
        if (ax > bodyHalfW) bodyHalfW = ax
      }
      // 前身并集宿主（无袋贴/守卫失败退化纯前片，warning 上屏提示）
      // + 后身并集宿主（后片+育克沿机头下口线缝合；无育克 = 纯后片、
      // 有省款守卫拦下育克留平铺，同前身退化口径）
      const panel = buildFrontPanel(data)
      const backPanel = buildBackPanel(data)
      setPanelHint([...panel.warnings, ...backPanel.warnings][0] ?? null)
      const hangExclude = new Set<string>(['front_piece', 'back_piece'])
      if (panel.hasFacing) hangExclude.add('front_facing')
      if (backPanel.hasYoke) hangExclude.add('back_yoke')
      hangExclude.add('waistband')   // 九期：腰头立体缝合，不再平铺
      // 其余裁片平铺（前后身组离开平铺行；退化时袋贴/育克自动留平铺）
      const garment = buildFlatLayout(data, hangExclude)
      setFlatKeys(data.pieces.map((p) => p.key))
      const view = buildGarmentView(ctx.THREE, garment)
      gv = view
      // 腰头布片（九期腰头立体化）：两端缝在前中会合、中点落后中，
      // 带顶整圈钉挂（挂腰头），裤身经缝对悬于带下
      const bandMesh = buildWaistbandMesh(data)
      // ---- 整裤解算（2026-09-18 双分支 → 2026-09-19 旁挂退役，恒穿台 =
      // 人台 morph 环场碰撞 + settle 落位） ----
      let pair!: Garment
      let sim!: DrapeSim
      let probeIdx: { front: number[]; back: number[] }
      let jam: { ringTotal: number; rowY: number }
      let flatX: number
      {
        // 锚定（θ 两系同构只 Y 平移）：纸样腰站 y ↔ 人台腰地标×身高因子
        // （身高 morph 地标按 stationFactor 近似——与围度读数同口径同量级
        // 误差，试验场可接受）。人台网格平移进纸样系建场，drape collide
        // 经 yLift 回纸样空间查环——机制原样复用
        const w = weightsFrom(slidersRef.current, heightWRef.current)
        dressRunW.current = w
        setDressReport(null)
        setDressStale(false)
        const lmWaist = a.landmarks.waist
        const lmCrotch = a.landmarks.crotch
        const lmAnkle = a.landmarks.ankle
        if (lmWaist === undefined || lmCrotch === undefined || lmAnkle === undefined) {
          throw new Error('人台缺腰/裆/踝地标（targets.json landmarks）——穿台无法锚定')
        }
        const waistSt = data.body.stations.find((st) => st.key === 'waist')
        if (!waistSt) {
          throw new Error('payload 缺 waist 站——穿台无法锚定腰位')
        }
        const sf = stationFactor(a.heightInfo, heightWRef.current)
        const anchorLift = lmWaist * sf - waistSt.y
        // 场域下探到脚底（2026-09-18 脚碰撞修复）：锚定下移后脚成纸样负 y
        // （世界 y∈[0,anchorLift)），行表从 0 起建则脚背以下无碰撞环、裤脚
        // 穿脚无推出；yMin 对齐 rowStep 格点罩住脚底
        const fieldYMin = Math.floor(-anchorLift / FIELD_PRIOR.rowStep) * FIELD_PRIOR.rowStep
        const fieldM = buildBodyField(
          shiftPositionsY(morphPositions(a, w), -anchorLift), a.indices, fieldYMin)
        // 腿区摆位输入 = 人台环场派生腿轴（forkY = 体裆叉口——穿台裆尖
        // 落位随体不随纸样裆深；forkSearch 找不到双环行 throw → 提示）；
        // 扫描止于踝——负 y 行进来的是脚环（包围半径含脚全长 ~18），混进
        // rProf 会让裤脚摆位喇叭张开
        const legAxisM = buildLegAxisFromRings(
          fieldM, lmCrotch * sf - anchorLift, lmAnkle * sf - anchorLift)
        // 腰圈钉环（2026-09-19 形随体长随衣；2026-09-20 间隙均匀）：形状
        // = 腰站人台截面边界、尺寸 = 成衣腰长（优先腰头带底净长——收省后
        // 口径；无腰头/坏链回退腰站 girth_finished 成衣量），沿外法线等距
        // 偏移至环长 = 成衣腰长——周身间隙均匀 |δ|；偏小款 δ<0 均匀穿体
        // → 碰撞推挤 + 热力图 gap 红区（穿不进读数）
        const waistLen = (bandMesh && bandBottomChain(bandMesh)?.runLength)
          ?? waistSt.girth_finished
        if (waistLen == null) {
          throw new Error('缺成衣腰长（腰头带底净长/腰站 girth_finished 均缺）——穿台无法定腰圈钉环')
        }
        const waistRing = buildWaistRing(fieldM, waistSt.y, waistLen)
        pair = buildFullPair(panel.host, backPanel.host, fieldM, {
          front: legAxisM.forkY, back: legAxisM.forkY,
        }, legAxisM, bandMesh, anchorLift, waistRing,
          backPanel.mode === 'seam' && backPanel.yokeHost && backPanel.seamInfo
            ? { host: backPanel.yokeHost, sCin: backPanel.seamInfo.sCin }
            : null)
        // 落位 = settle 控制器：拉到腰地标 → 前后裆探针驱动钉高独立
        // 缓释（俯仰涌现）→ 零穿透静止出读数（真人「裆不舒服一点点
        // 往下」的仿真翻译，口径见 settle.ts 头注）。Worker 化（2026-09-23）
        // 后控制器不在主线程建——dressDriver 在 worker 侧重建（闭包快照读
        // pinIdx/pinTarget，构造后自洽），主线程只备好 probeIdx/jam 随 init
        // 消息透传
        sim = buildDrape(pair, fieldM, anchorLift)
        // 挂胯判据（2026-09-23 P1）：钉环（总长 = 成衣腰长）候选行截面
        // 周长超环长×(1+jamMargin) 即卡停——治掉裆把刚性环拽进体围更大
        // 下行行的嵌体/深褶/波浪（口径 .claude/plans/穿台落位修复方案.md §二）
        probeIdx = buildCrotchProbeIdx(pair)
        jam = { ringTotal: waistRing.total, rowY: waistRing.y }
        // 组位 = 原点套轴（sim 系锚世界系：anchorLift 即世界腰高）
        flatX = bodyHalfW + HANG_PRIOR.clearance + FLAT_PRIOR.clearance
      }
      const hostN = panel.host.xy.length / 2
      const backHostN = backPanel.host.xy.length / 2
      const hasBand = pair.parts.some((p) => p.key === 'waistband')
      // band 偏移按键查询（seam 模式 parts 序 fL/fR/bL/bR/yL/yR/band——
      // band 续在育克后，不再恒为 2*hostN+2*backHostN）
      const bandOffset = pair.parts.find((p) => p.key === 'waistband')?.offset
        ?? 2 * hostN + 2 * backHostN
      // 贴层视图：前片（径向 0 = 解算位所见）/ 袋贴（内偏衬里侧）；
      // 前宿主 offsets {L:0, R:nF}，后宿主 {L:2nF, R:2nF+nB}
      const frontMesh = buildClothMesh(
        data.pieces.find((p) => p.key === 'front_piece')!)
      hv = buildRiderView(ctx.THREE, 'front_piece', bindRider(frontMesh, panel.host), [
        { side: 'L', hostOffset: 0, radialOffset: 0 },
        { side: 'R', hostOffset: hostN, radialOffset: 0 },
      ])
      if (panel.hasFacing) {
        const facingMesh = buildClothMesh(
          data.pieces.find((p) => p.key === 'front_facing')!)
        hfv = buildRiderView(ctx.THREE, 'front_facing',
          bindRider(facingMesh, panel.host), [
            { side: 'L', hostOffset: 0, radialOffset: -HANG_PRIOR.riderStep },
            { side: 'R', hostOffset: hostN, radialOffset: -HANG_PRIOR.riderStep },
          ])
      }
      // 后身贴层：后片/育克径向均 0——真裤后身育克与后片沿缝线相邻共
      // 面、非叠层（无袋贴的衬里语义，不偏移）
      const backMesh = buildClothMesh(
        data.pieces.find((p) => p.key === 'back_piece')!)
      bv = buildRiderView(ctx.THREE, 'back_piece',
        bindRider(backMesh, backPanel.host), [
          { side: 'L', hostOffset: 2 * hostN, radialOffset: 0 },
          { side: 'R', hostOffset: 2 * hostN + backHostN, radialOffset: 0 },
        ])
      if (backPanel.mode === 'seam' && backPanel.yokeHost) {
        // seam 模式（有省闭省净样款）：育克升格 sim 参与片——直渲视图
        // ×2（L/R 各持 offset，非贴层；绑定并集宿主的 rider 口径已废，
        // union 模式才走贴层）
        for (const yp of pair.parts.filter((p) => p.key === 'back_yoke')) {
          const v = buildSimView(ctx.THREE, 'back_yoke', backPanel.yokeHost)
          yokeViews.push({ v, off: yp.offset })
          scene.add(v.group)
        }
      } else if (backPanel.hasYoke) {
        const yokeMesh = buildClothMesh(
          data.pieces.find((p) => p.key === 'back_yoke')!)
        byv = buildRiderView(ctx.THREE, 'back_yoke',
          bindRider(yokeMesh, backPanel.host), [
            { side: 'L', hostOffset: 2 * hostN, radialOffset: 0 },
            { side: 'R', hostOffset: 2 * hostN + backHostN, radialOffset: 0 },
          ])
      }
      // 腰头直渲视图（sim 参与片，非贴层）
      if (hasBand && bandMesh) {
        wbv = buildSimView(ctx.THREE, 'waistband', bandMesh)
        scene.add(wbv.group)
      }
      // 整裤组位 = 原点套轴（sim 系锚世界系：anchorLift 即世界腰高，显示
      // 层零平移）；平铺组让位到整裤右侧
      hv.group.position.set(0, 0, 0)
      hfv?.group.position.set(0, 0, 0)
      bv.group.position.set(0, 0, 0)
      byv?.group.position.set(0, 0, 0)
      for (const { v } of yokeViews) v.group.position.set(0, 0, 0)
      wbv?.group.position.set(0, 0, 0)
      scene.add(hv.group)
      if (hfv) scene.add(hfv.group)
      scene.add(bv.group)
      if (byv) scene.add(byv.group)
      view.group.position.x = flatX
      view.group.position.y = FLAT_PRIOR.lift
      scene.add(view.group)
      garmentViewRef.current = view
      setGarmentError(null)
      // 取景让位（幂等：按与上次中心的差量平移，保留用户自由视角）：
      // 场景中心 = 人台左沿 ~ 平铺组右沿的中点（双主体：人台+整裤 / 平铺）
      let flatW = 0
      for (let i = 0; i < garment.pos.length; i += 3) {
        if (garment.pos[i] > flatW) flatW = garment.pos[i]
      }
      const cx = (flatX + flatW - bodyHalfW) / 2
      hangXRef.current = cx
      const d = cx - camShiftRef.current
      if (Math.abs(d) > 1e-6) {
        ctx.camera.position.x += d
        ctx.controls.target.x += d
        ctx.controls.update()
        camShiftRef.current = cx
      }
      // 初摆位出画（解算启动前的零帧画面）——此后主线程不再碰 sim（pos
      // buffer 随 init transfer 进 worker），全部视图回填走 worker 帧消息
      hv.update(pair.pos)
      hfv?.update(pair.pos)
      bv.update(pair.pos)
      byv?.update(pair.pos)
      for (const { v, off } of yokeViews) v.update(pair.pos, off)
      if (wbv && hasBand) {
        wbv.update(pair.pos, bandOffset)
      }
      // 视图回填（worker 帧驱动）：帧消息（transfer 的 pos 副本）落地 →
      // rAF 合流绘制（worker 步进 ~20Hz 慢于 rAF 60Hz 天然合并不排队）
      const applyPos = (pos: Float32Array) => {
        hv!.update(pos)
        hfv?.update(pos)
        bv!.update(pos)
        byv?.update(pos)
        for (const { v, off } of yokeViews) v.update(pos, off)
        if (wbv && hasBand) wbv.update(pos, bandOffset)
      }
      // 热力图着色：worker 回传数组（节拍帧/setHeat 即时/终态末帧三层）
      // 就地重着色；clear 本地恢复分色
      const applyHeat = (v: Float32Array) => {
        hv!.heat(v, 'gap')
        hfv?.heat(v, 'gap')
        bv!.heat(v, 'gap')
        byv?.heat(v, 'gap')
        for (const { v: yv, off } of yokeViews) yv.heat(v, 'gap', off)
        wbv?.heat(v, 'gap', bandOffset)
      }
      const clearHeat = () => {
        hv!.heat(null, 'gap')
        hfv?.heat(null, 'gap')
        bv!.heat(null, 'gap')
        byv?.heat(null, 'gap')
        for (const { v: yv, off } of yokeViews) yv.heat(null, 'gap', off)
        wbv?.heat(null, 'gap', bandOffset)
      }
      // ---- 解算 Worker 化（2026-09-23，取代 rAF tick 主线程解算）：
      // 构建（buildDrape 等）留主线程一次性跑完，toSolveState 投影
      // transfer 零拷贝进 worker——此后 stepDrape/settle 控制器全在
      // worker（MessageChannel 每宏任务一步全速推进，不受 rAF 节拍钳），
      // 主线程只收帧消息回填视图：解算期间取景/滑杆交互 60fps 零阻塞。
      // done 后 worker 常驻（setHeat 终态重着色走通道）；重穿 epoch/
      // 组件卸载由 cleanup terminate ----
      worker = new Worker(
        new URL('./garment/dressWorker.ts', import.meta.url), { type: 'module' })
      let pendingPos: Float32Array | null = null
      let pendingHeat: Float32Array | null = null
      let drawRaf = false
      const draw = () => {
        drawRaf = false
        const pos = pendingPos
        if (pos === null) return
        const heat = pendingHeat
        pendingPos = null
        pendingHeat = null
        applyPos(pos)
        if (heat !== null) applyHeat(heat)
        ctx.render()
      }
      worker.onmessage = (e: MessageEvent<WorkerOut>) => {
        const m = e.data
        if (m.type === 'ready') {
          // ready 握手：模块 worker 脚本加载完成前的消息会被浏览器丢弃
          //（2026-09-23 实测：创建后立刻 post 的 init 石沉大海，worker 无
          // 异常无回帧、重发即正常）——等 ready 才发 init
          worker!.postMessage(init, transferBuffers(init))
          return
        }
        if (m.type === 'frame' || m.type === 'done') {
          pendingPos = m.pos
          // 节拍帧才带 heat；非节拍帧保留上帧着色（颜色随顶点走）
          if (m.heat !== null) pendingHeat = m.heat
          if (m.type === 'done') setDressReport(m.report)
          if (!drawRaf) {
            drawRaf = true
            raf = requestAnimationFrame(draw)
          }
        } else if (m.type === 'heat') {
          // setHeat 即时回包：按当前帧重算一层就地重着色（解算中/终态皆可）
          applyHeat(m.heat)
          ctx.render()
        } else if (m.type === 'error') {
          setGarmentError(m.message)
        }
      }
      worker.onerror = (ev) => {
        setGarmentError(`解算 worker 异常：${ev.message}`)
      }
      // 初态热力：init transfer 前主线程就地算末层（此后 sim 归 worker）
      if (heatOnRef.current) applyHeat(computeHeat(sim, 'gap'))
      dressViewsRef.current = {
        setHeat: (on) => worker!.postMessage({ type: 'setHeat', on }),
        applyHeat,
        clear: clearHeat,
      }
      const init = toSolveState(sim, probeIdx, jam, heatOnRef.current)
      // init 的发送在 onmessage 的 ready 分支（握手协议，见上）
      ctx.render()
    } catch (e) {
      console.error('[fitting3d] 裁片构建失败', e)
      setPanelHint(null)
      setGarmentError(e instanceof Error ? e.message : String(e))
    }
    return () => {
      cancelAnimationFrame(raf)
      worker?.terminate()   // 解算 worker 随效应卸载/重穿 epoch 终结
      dressViewsRef.current = null
      if (gv) { scene.remove(gv.group); gv.dispose() }
      if (hv) { scene.remove(hv.group); hv.dispose() }
      if (hfv) { scene.remove(hfv.group); hfv.dispose() }
      if (bv) { scene.remove(bv.group); bv.dispose() }
      if (byv) { scene.remove(byv.group); byv.dispose() }
      for (const { v } of yokeViews) { scene.remove(v.group); v.dispose() }
      if (wbv) { scene.remove(wbv.group); wbv.dispose() }
      garmentViewRef.current = null
    }
  }, [fitting, asset, dressEpoch])

  // ---- 自动首挂（仅一次）：进系统即有衣服；失败不自动重试（按钮兜底） ----
  useEffect(() => {
    if (autoTried.current) return
    if (fitting === null && !fittingBusy) {
      autoTried.current = true
      onGenerateFitting()
    }
  }, [fitting, fittingBusy, onGenerateFitting])

  // ---- 视角预设（球面插值 ~300ms；OrbitControls 随时可继续自由拖） ----
  // 机位 x 以场景中心居中（人台+悬挂筒 ↔ 平铺组，hangXRef 即中心）
  const flyTo = (view: 'front' | 'side' | 'back' | 'iso') => {
    const ctx = ctxRef.current
    if (!ctx || heightRef.current <= 0) return
    const h = heightRef.current
    const cx = hangXRef.current
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
            {/* 重新生成（fitting 重算）2026-09-20 收口到左栏「生成」，
                此处只留重新试穿（dressEpoch++ 换滑杆快照重解算） */}
            <Button size="small" icon={<RedoOutlined />}
              onClick={() => setDressEpoch((e) => e + 1)}>
              重新试穿
            </Button>
          </div>
          {dressStale && (
            <div className="f3d-row">
              <span>人台已调，穿着待更新</span>
            </div>
          )}
          {flatKeys.length > 0 && (
            <div className="f3d-legend">
              {PIECE_LEGEND_ORDER.map((k) => {
                const on = flatKeys.includes(k)
                return (
                  <span key={k} className="f3d-legend-item"
                    style={{ opacity: on ? 1 : 0.45 }}>
                    <span className="f3d-legend-dot" style={{
                      background: on
                        ? `#${pieceColor(k).toString(16).padStart(6, '0')}`
                        : '#c0c0c0',
                    }} />
                    {CN_PIECE_NAMES[k] ?? k}
                    {!on && '（未开启）'}
                  </span>
                )
              })}
            </div>
          )}
          {panelHint && (
            <div className="f3d-hint">{panelHint}</div>
          )}
          {fittingStale && (
            <div className="f3d-hint">参数已改，左栏「生成」重算后更新</div>
          )}
          {garmentError && (
            <div className="f3d-hint f3d-hint-err">{garmentError}</div>
          )}
        </div>

        {!garmentError && (
          <div className="f3d-card">
            <div className="f3d-card-title">穿台读数</div>
            {dressReport ? (
              <>
                <div className="f3d-row">
                  <span>掉裆（相对腰地标）</span>
                  <span>
                    前 {dressReport.dropF.toFixed(1)} / 后 {dressReport.dropB.toFixed(1)} cm
                  </span>
                </div>
                <div className="f3d-row">
                  <span>前裆接触</span>
                  <span>{contactText(dressReport.contactF)}</span>
                </div>
                <div className="f3d-row">
                  <span>后裆接触</span>
                  <span>{contactText(dressReport.contactB)}</span>
                </div>
                <div className="f3d-row">
                  <span>最差穿透</span>
                  <span>
                    {dressReport.worstPen.toFixed(1)} cm @ 高度 ~{dressReport.worstPenY.toFixed(0)}
                  </span>
                </div>
                {(dressReport.jamF || dressReport.jamB) && (
                  <div className="f3d-hint">
                    卡胯停（{dressReport.jamF ? '前' : ''}
                    {dressReport.jamF && dressReport.jamB ? '/' : ''}
                    {dressReport.jamB ? '后' : ''}）：该截面套不进（偏小读数）
                  </div>
                )}
                {dressReport.tooSmall && (
                  <div className="f3d-hint">
                    偏小信号——读数提示，不改版型（独立原则）
                  </div>
                )}
                {dressReport.capped && (
                  <div className="f3d-hint">
                    预算尽收束（非真实静止，数值仅供参考）
                  </div>
                )}
              </>
            ) : (
              <div className="f3d-hint">
                穿台解算中：拉到腰 → 裆顶住逐步下放 → 静止后出读数
              </div>
            )}
          </div>
        )}

        {!garmentError && (
          <div className="f3d-card">
            <div className="f3d-card-title">穿台热力图</div>
            <div className="f3d-row">
              <span>显示</span>
              <Switch size="small" checked={heatOn}
                onChange={(ck) => setHeatOn(ck)} />
            </div>
            <div className={heatOn ? 'f3d-heat-legend' : 'f3d-heat-legend f3d-heat-legend-off'}>
              <div className="f3d-heat-bar" />
              <div className="f3d-heat-labels">
                <span>穿透 / 紧贴 0</span>
                <span>适中</span>
                <span>松 ≥4cm</span>
              </div>
            </div>
            <div className="f3d-hint">
              间隙 = 布面离身体距离（红=穿不进/紧贴、蓝=松量分布）。开关只
              重着色当前画面，不重跑解算
            </div>
          </div>
        )}

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
