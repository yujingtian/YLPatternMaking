// 3D 人台视图：three 惰性分包加载（首屏零影响）；MakeHuman 官方 target
// 滑杆试验场（2026-09-12 用户口径：**全身**模型 + 用它的 targets 调节）。
// 链路：loadNativeBody（raw.obj 全身 A-pose 基网格——含头/臂，顶点号与
// .target 天然对齐——+ 8 个官方 measure 场）→ morphPositions(权重) →
// BufferGeometry 直显；四个部位滑杆双极（−1..+1，正推 site+ 场 / 负推
// site− 场），拖动实时重 morph + 站点围度实时读数（站高为粗探测近似值，
// native 场会微移站高，读数在极端权重下有轻微口径偏差，试验场可接受；
// 原生场固有缺陷如 thigh 膝上死区属 MakeHuman 作者化行为，原样呈现）。
// 坐标口径：顶点 cm、Y-up、body 组脚底 y=0（native.ts）。
import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Empty, Slider, Spin } from 'antd'
import {
  CameraOutlined, EyeInvisibleOutlined, EyeOutlined, UndoOutlined,
} from '@ant-design/icons'
import type * as ThreeT from 'three'
import type { OrbitControls as OrbitControlsT } from 'three/examples/jsm/controls/OrbitControls.js'
import type { NativeBody } from './bodymesh/native'
import { loadNativeBody, readGirth } from './bodymesh/native'
import type { MeshWeights } from './bodymesh/morph'
import { morphPositions } from './bodymesh/morph'

type ThreeMod = typeof import('three')
type OrbitControlsCtor = typeof import('three/examples/jsm/controls/OrbitControls.js').OrbitControls

// 滑杆部位 <-> base.bin target 槽位（SLOT_ORDER 固定序里的 4 对场）
type Site = 'waist' | 'hips' | 'thigh' | 'knee'
const SITES: { key: Site; label: string }[] = [
  { key: 'waist', label: '腰' },
  { key: 'hips', label: '臀' },
  { key: 'thigh', label: '大腿' },
  { key: 'knee', label: '膝' },
]
type Sliders = Record<Site, number>

interface SceneCtx {
  THREE: ThreeMod
  renderer: ThreeT.WebGLRenderer
  scene: ThreeT.Scene
  camera: ThreeT.PerspectiveCamera
  controls: OrbitControlsT
  render: () => void
  dispose: () => void
}

export default function Fitting3DView() {
  const mountRef = useRef<HTMLDivElement>(null)
  const ctxRef = useRef<SceneCtx | null>(null)
  // 地面格网（场景一次创建；脚底 y=0 恒落地）
  const gridRef = useRef<ThreeT.GridHelper | null>(null)
  const meshRef = useRef<ThreeT.Mesh | null>(null)
  const assetRef = useRef<NativeBody | null>(null)
  // 取景基准（mesh 身高 cm；初始机位/视角预设全由它定标，加载前 0）
  const heightRef = useRef(0)
  const flyRaf = useRef(0)
  const [threeMod, setThreeMod] = useState<
    { THREE: ThreeMod; OrbitControls: OrbitControlsCtor } | null>(null)
  const [asset, setAsset] = useState<NativeBody | null>(null)
  const [assetError, setAssetError] = useState<string | null>(null)
  const [sliders, setSliders] = useState<Sliders>(
    { waist: 0, hips: 0, thigh: 0, knee: 0 })
  const [girths, setGirths] = useState<Record<Site, number | null>>(
    { waist: null, hips: null, thigh: null, knee: null })
  const [showBody, setShowBody] = useState(true)

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

  // ---- 人台加载（场景就绪后一次）：raw.obj 全身基网格（w=0）上屏 ----
  useEffect(() => {
    if (!threeMod || !ctxRef.current) return
    let alive = true
    void loadNativeBody().then((a) => {
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
        side: THREE.DoubleSide,   // raw.obj 面序不保证统一，先双面保观感
      }))
      ctx.scene.add(mesh)
      meshRef.current = mesh
      // 初始机位按身高定标（正观全身 A-pose）
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

  // ---- 站点查询表（粗探测站：站高 + body/leg 口径，w=0 值） ----
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
    // 双极值 -> 场权重：正推 site+、负推 site−（两场独立作者化，非反对称）
    const w: MeshWeights = {}
    for (const { key } of SITES) {
      const v = sliders[key]
      if (v > 0) w[`${key}+`] = v
      else if (v < 0) w[`${key}-`] = -v
    }
    const pos = morphPositions(a, w)
    const attr = mesh.geometry.getAttribute('position') as ThreeT.BufferAttribute
    ;(attr.array as Float32Array).set(pos)
    attr.needsUpdate = true
    mesh.geometry.computeVertexNormals()
    ctx.render()
    const read: Record<Site, number | null> = {
      waist: null, hips: null, thigh: null, knee: null }
    for (const { key } of SITES) {
      const st = stationOf.get(key)
      if (st) {
        read[key] = readGirth(pos, a.indices, st.y, st.per)
      }
    }
    setGirths(read)
    // stationOf 随 asset 派生，asset 变化时本效应重跑取基线读数
  }, [sliders, asset, stationOf])

  // ---- 显示开关（可见性直接改，不重建场景） ----
  useEffect(() => {
    const ctx = ctxRef.current
    const mesh = meshRef.current
    if (!ctx || !mesh) return
    mesh.visible = showBody
    ctx.render()
  }, [showBody, asset])

  // ---- 视角预设（球面插值 ~300ms；OrbitControls 随时可继续自由拖） ----
  const flyTo = (view: 'front' | 'side' | 'back' | 'iso') => {
    const ctx = ctxRef.current
    if (!ctx || heightRef.current <= 0) return
    const h = heightRef.current
    const d = h * 1.6, y = h * 0.47
    const target: [number, number, number] = view === 'front'
      ? [0, y, d]
      : view === 'side' ? [d, y, 0]
      : view === 'back' ? [0, y, -d]
      : [h * 0.95, h * 0.9, h * 0.95]
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
                onChange={(v) =>
                  setSliders((s) => ({ ...s, [key]: v }))}
              />
            </div>
          ))}
          <Button size="small" icon={<UndoOutlined />}
            disabled={!asset}
            onClick={() => setSliders({ waist: 0, hips: 0, thigh: 0, knee: 0 })}>
            全部归零
          </Button>
          <div className="f3d-hint">
            正/负 = 增/减场权重（w=1 为 MakeHuman 作者化上限）
          </div>
        </div>

        <div className="f3d-card">
          <div className="f3d-card-title">显示</div>
          <div className="f3d-row">
            <span>显示人台</span>
            <Button size="small" type="text"
              icon={showBody ? <EyeOutlined /> : <EyeInvisibleOutlined />}
              onClick={() => setShowBody(!showBody)}>
              {showBody ? '开' : '关'}
            </Button>
          </div>
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
