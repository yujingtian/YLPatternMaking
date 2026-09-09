// 3D 试穿视图（一期）：three 惰性分包加载（首屏零影响）；人台 + 腰头
// 环带 + 四半片布料 + 结构线随 PBD 解算逐帧渲染。侧栏：体型入口/松量
// 读数/快捷滑杆（debounce 自动重试穿）/热力图/透明度/视角/截图。
// 坐标口径：payload 整版全局系 Y-up 直接作为身体高度；θ=0 前中 +Z。
import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Empty, Slider, Spin, Switch, Tag } from 'antd'
import {
  CameraOutlined, EyeInvisibleOutlined, EyeOutlined, RedoOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import type * as ThreeT from 'three'
import type { OrbitControls as OrbitControlsT } from 'three/examples/jsm/controls/OrbitControls.js'
import type { FittingResult, Snapshot, Values } from '../types'
import type { BodyGirths } from './bodyProfile'
import { estimateBody } from './bodyProfile'
import {
  findProfile, loadStore, saveStore, type StoreShape,
} from './bodyProfileStore'
import { buildSkinMesh } from './skin'
import { buildWaistBand } from './seams'
import { bakeStructureLines, updateBakedLine, type BakedLine } from './structureLines'
import { computeStrain, strainColor } from './heatmap'
import { useFittingSolver } from './useFittingSolver'
import BodyProfileDrawer from './BodyProfileDrawer'

type ThreeMod = typeof import('three')
type OrbitControlsCtor = typeof import('three/examples/jsm/controls/OrbitControls.js').OrbitControls

const SLIDERS: { key: string; label: string; min: number; max: number }[] = [
  { key: 'waist', label: '腰围', min: 55, max: 120 },
  { key: 'hip', label: '臀围', min: 75, max: 130 },
  { key: 'thigh', label: '大腿围', min: 40, max: 80 },
  { key: 'knee', label: '膝围', min: 30, max: 60 },
  { key: 'hem', label: '脚口', min: 24, max: 50 },
  { key: 'outseam', label: '裤长', min: 60, max: 120 },
]

const STATION_LABEL: Record<string, string> = {
  waist: '腰', hip: '臀', thigh: '大腿', knee: '膝',
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

// 内容重建产物（显示控制 effect 直接取用，避免 traverse 误伤人台材质）
interface ContentHandles {
  bodyMeshes: ThreeT.Mesh[]
  clothMeshes: ThreeT.Mesh[]
  clothMat: ThreeT.MeshStandardMaterial
  heatMat: ThreeT.MeshStandardMaterial
  applyHeat: () => void     // 重算应变并写入 color attr（settled 后也能切）
}

export default function Fitting3DView({
  fitting, fittingStale, fittingBusy, onGenerateFitting, measurements,
  onMeasurement,
}: {
  fitting: Snapshot<FittingResult> | null
  fittingStale: boolean
  fittingBusy: boolean
  onGenerateFitting: () => void
  measurements: Values
  onMeasurement: (key: string, value: unknown) => void
}) {
  const mountRef = useRef<HTMLDivElement>(null)
  const ctxRef = useRef<SceneCtx | null>(null)
  const [threeMod, setThreeMod] = useState<
    { THREE: ThreeMod; OrbitControls: OrbitControlsCtor } | null>(null)
  const [store, setStore] = useState<StoreShape>(() => loadStore())
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [showHeatmap, setShowHeatmap] = useState(false)
  const [showBody, setShowBody] = useState(true)
  const [opacity, setOpacity] = useState(1)
  const flyRaf = useRef(0)
  const handlesRef = useRef<ContentHandles | null>(null)
  const heatRef = useRef(false)

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

  // ---- 体型（独立浏览器态；改体型不 bump 参数版本） ----
  const estimated = useMemo(() => estimateBody({
    waist: Number(measurements.waist ?? 0),
    hip: Number(measurements.hip ?? 0),
    knee: Number(measurements.knee ?? 0),
    thigh: measurements.thigh ? Number(measurements.thigh) : undefined,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [measurements.waist, measurements.hip, measurements.knee, measurements.thigh])
  const activeProfile = store.activeId === 'estimated'
    ? estimated
    : (findProfile(store, store.activeId) ?? estimated)
  const girths: BodyGirths = useMemo(() => ({
    waist: activeProfile.waist, hip: activeProfile.hip,
    thigh: activeProfile.thigh, knee: activeProfile.knee,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [activeProfile.waist, activeProfile.hip, activeProfile.thigh, activeProfile.knee])
  useEffect(() => { saveStore(store) }, [store])

  // ---- 围度喂入解算的 trailing debounce（200ms，2026-09-09 四轮） ----
  // 默认估计体型下腰/臀/腿/膝快捷滑杆与围度直连（estimateBody 1:1 反推），
  // 每 0.5cm tick 都会触发 useFittingSolver 重建——蒙皮+PBD 为 ~百 ms 级
  // 同步重活（buildSkinMesh 165/66A 实测 ~230ms、病理 ~500ms），拖动期间
  // 逐 tick 重建卡主线程。与 payload 的 800ms 重生成链路独立：拖动停顿
  // 200ms 后才重建一次（warm-start 语义不变，仅降频）
  const [girthsDebounced, setGirthsDebounced] = useState(girths)
  useEffect(() => {
    const t = window.setTimeout(() => setGirthsDebounced(girths), 200)
    return () => { window.clearTimeout(t) }
  }, [girths])

  const solver = useFittingSolver(fitting?.data ?? null, girthsDebounced)

  // ---- 自动生成/防抖重试穿（滑杆拖动 -> 800ms 自动重算） ----
  const baseKey = useMemo(
    () => JSON.stringify(measurements), [measurements])
  const lastReq = useRef('')
  useEffect(() => {
    if (fitting === null && !fittingBusy) {
      lastReq.current = baseKey
      onGenerateFitting()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    if (!fitting || fittingBusy || lastReq.current === '') return
    if (baseKey === lastReq.current) return
    const t = window.setTimeout(() => {
      lastReq.current = baseKey
      onGenerateFitting()
    }, 800)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseKey, fitting !== null, fittingBusy])

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
    camera.position.set(0, 72, 185)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.target.set(0, 52, 0)
    controls.enableDamping = false
    const hemi = new THREE.HemisphereLight(0xffffff, 0x8a8a95, 1.1)
    const dir = new THREE.DirectionalLight(0xffffff, 1.6)
    dir.position.set(40, 140, 80)
    scene.add(hemi, dir)
    const grid = new THREE.GridHelper(320, 32, 0xc9c9c9, 0xe0e0e0)
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

  // ---- 内容重建（每次解算对象更换：人台/布料/结构线/环带） ----
  useEffect(() => {
    const ctx = ctxRef.current
    const { man, garment, sim, onFrame } = solver
    if (!ctx || !threeMod || !man || !garment || !sim) return
    const { THREE } = ctx
    const group = new THREE.Group()

    // 人台（SDF 单张水密蒙皮：三管 smin 软并集 + marching cubes，仅体型/
    // 围度变化时重建、非每帧）+ 腰头环带（挂腰口站点高度，宽随 payload）。
    // 渲染前提守卫：蒙皮为单张水密外法向闭合面（法线 = SDF 梯度、
    // FLIP_WINDING 锁外向绕向），不透明 FrontSide + 深度写入前提由蒙皮
    // 继承；改 transparent 会透视体内布料与腰头环带，须同步
    // .doc/python工程设计.md §10.11 评估。构建失败 console.error 且
    // bodyMeshes=[] 降级（不炸 React 树，布料仍可解算渲染）
    const bodyMat = new THREE.MeshStandardMaterial({
      color: 0xd8c3b0, roughness: 0.85, metalness: 0.02,
    })
    const bodyMeshes: ThreeT.Mesh[] = []
    try {
      const skin = buildSkinMesh(man)
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position',
        new THREE.Float32BufferAttribute(skin.positions, 3))
      geo.setAttribute('normal',
        new THREE.Float32BufferAttribute(skin.normals, 3))
      geo.setIndex(new THREE.Uint32BufferAttribute(skin.indices, 1))
      const mesh = new THREE.Mesh(geo, bodyMat)
      bodyMeshes.push(mesh)
      group.add(mesh)
    } catch (e) {
      console.error('[fitting3d] 蒙皮构建失败，人台降级为空', e)
    }
    const yWaist = fitting?.data.body.stations.find((s) => s.key === 'waist')
      ?.y ?? 90
    const wb = buildWaistBand(
      man, yWaist, fitting?.data.body.waistband_width ?? 4)
    const wbGeo = new THREE.BufferGeometry()
    wbGeo.setAttribute('position',
      new THREE.Float32BufferAttribute(wb.positions, 3))
    wbGeo.setIndex(new THREE.Uint32BufferAttribute(wb.indices, 1))
    wbGeo.computeVertexNormals()
    const bandMat = new THREE.MeshStandardMaterial({
      color: 0x39435c, roughness: 0.7, side: THREE.DoubleSide,
    })
    group.add(new THREE.Mesh(wbGeo, bandMat))

    // 布料（四半片，粒子连续段 memcpy 到各自 position attr）
    const clothMat = new THREE.MeshStandardMaterial({
      color: 0x5b7ba8, roughness: 0.92, metalness: 0,
      side: THREE.DoubleSide, transparent: opacity < 1, opacity,
    })
    const heatMat = new THREE.MeshStandardMaterial({
      color: 0xffffff, roughness: 0.92, metalness: 0,
      side: THREE.DoubleSide, vertexColors: true,
      transparent: opacity < 1, opacity,
    })
    const clothMeshes: ThreeT.Mesh[] = []
    const posAttrs: ThreeT.BufferAttribute[] = []
    const colAttrs: ThreeT.BufferAttribute[] = []
    for (const part of garment.parts) {
      const n = part.mesh.xy.length / 2
      const geo = new THREE.BufferGeometry()
      const pa = new THREE.BufferAttribute(new Float32Array(3 * n), 3)
      pa.array.set(sim.pos.subarray(3 * part.offset, 3 * (part.offset + n)))
      pa.needsUpdate = true
      geo.setAttribute('position', pa)
      geo.setIndex(new THREE.Uint32BufferAttribute(part.mesh.tri, 1))
      const ca = new THREE.BufferAttribute(new Float32Array(3 * n), 3)
      ca.array.fill(1)
      geo.setAttribute('color', ca)
      geo.computeVertexNormals()
      const mesh = new THREE.Mesh(geo, clothMat)
      clothMeshes.push(mesh)
      posAttrs.push(pa)
      colAttrs.push(ca)
      group.add(mesh)
    }

    // 结构线（marks 重采样 -> 重心绑定 -> LineSegments）
    const lineMat = new THREE.LineBasicMaterial({ color: 0x16a085 })
    const lines: { baked: BakedLine; attr: ThreeT.BufferAttribute
      geo: ThreeT.BufferGeometry }[] = []
    if (fitting) {
      const pieceOf = (key: string) =>
        fitting.data.pieces.find((p) => p.key === key)
      for (const part of garment.parts) {
        const piece = pieceOf(
          part.key === 'front' ? 'front_piece' : 'back_piece')
        if (!piece) continue
        for (const baked of bakeStructureLines(piece, part.mesh, part.offset)) {
          const segCount = Math.max(0, baked.n - 1)
          const attr = new THREE.BufferAttribute(
            new Float32Array(segCount * 2 * 3), 3)
          const geo = new THREE.BufferGeometry()
          geo.setAttribute('position', attr)
          group.add(new THREE.LineSegments(geo, lineMat))
          lines.push({ baked, attr, geo })
        }
      }
    }
    ctx.scene.add(group)
    const applyHeat = () => {
      const strain = computeStrain(garment, sim.pos)
      for (let p = 0; p < garment.parts.length; p++) {
        const part = garment.parts[p]
        const n = part.mesh.xy.length / 2
        const arr = colAttrs[p].array as Float32Array
        for (let i = 0; i < n; i++) {
          const [r, g, b] = strainColor(strain[part.offset + i])
          arr[3 * i] = r; arr[3 * i + 1] = g; arr[3 * i + 2] = b
        }
        colAttrs[p].needsUpdate = true
      }
    }
    handlesRef.current = { bodyMeshes, clothMeshes, clothMat, heatMat, applyHeat }
    ctx.render()

    // 每帧：粒子 -> 布料/结构线/热力图 + 渲染
    const unregister = onFrame(() => {
      for (let p = 0; p < garment.parts.length; p++) {
        const part = garment.parts[p]
        const n = part.mesh.xy.length / 2
        posAttrs[p].array.set(
          sim.pos.subarray(3 * part.offset, 3 * (part.offset + n)))
        posAttrs[p].needsUpdate = true
        clothMeshes[p].geometry.computeVertexNormals()
      }
      for (const { baked, attr } of lines) {
        updateBakedLine(baked, sim.pos)
        const segCount = baked.n - 1
        for (let s = 0; s < segCount; s++) {
          for (let d = 0; d < 3; d++) {
            attr.array[s * 6 + d] = baked.positions[s * 3 + d]
            attr.array[s * 6 + 3 + d] = baked.positions[s * 3 + 3 + d]
          }
        }
        attr.needsUpdate = true
      }
      if (heatRef.current) applyHeat()
      ctx.render()
    })

    return () => {
      unregister()
      ctx.scene.remove(group)
      for (const m of bodyMeshes) m.geometry.dispose()
      wbGeo.dispose()
      for (const m of clothMeshes) m.geometry.dispose()
      for (const { geo } of lines) geo.dispose()
      bodyMat.dispose(); bandMat.dispose()
      clothMat.dispose(); heatMat.dispose(); lineMat.dispose()
      handlesRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threeMod, solver.buildVersion])

  // ---- 显示控制同步（材质/可见性直接改，不重建场景） ----
  useEffect(() => {
    const ctx = ctxRef.current
    const h = handlesRef.current
    if (!ctx || !h) return
    heatRef.current = showHeatmap
    for (const mat of [h.clothMat, h.heatMat]) {
      mat.opacity = opacity
      mat.transparent = opacity < 1
      mat.needsUpdate = true
    }
    for (const mesh of h.clothMeshes) {
      mesh.material = showHeatmap ? h.heatMat : h.clothMat
    }
    if (showHeatmap) h.applyHeat()     // settled 后切换也能立即上色
    ctx.render()
  }, [opacity, showHeatmap, solver.buildVersion, threeMod])

  useEffect(() => {
    const ctx = ctxRef.current
    const h = handlesRef.current
    if (!ctx || !h) return
    for (const mesh of h.bodyMeshes) mesh.visible = showBody
    ctx.render()
  }, [showBody, solver.buildVersion])

  // ---- 视角预设（球面插值 ~300ms；OrbitControls 随时可继续自由拖） ----
  const flyTo = (view: 'front' | 'side' | 'back' | 'iso') => {
    const ctx = ctxRef.current
    if (!ctx) return
    const dist = 185
    const target: [number, number, number] = view === 'front'
      ? [0, 62, dist]
      : view === 'side' ? [dist, 62, 0]
      : view === 'back' ? [0, 62, -dist]
      : [dist * 0.62, 118, dist * 0.62]
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

  // ---- 松量读数（成衣围 − 体型围；负值标「紧身」） ----
  const easeRows = (fitting?.data.body.stations ?? []).filter(
    (s) => s.girth_finished != null && STATION_LABEL[s.key]
      && girths[s.key as keyof BodyGirths] != null,
  ).map((s) => {
    const finished = s.girth_finished as number
    const body = girths[s.key as keyof BodyGirths] as number
    return { key: s.key, label: STATION_LABEL[s.key], finished, body,
      ease: finished - body }
  })

  const loading = threeMod === null || solver.status === 'building'
  const pendingRegen = fitting !== null
    && (fittingStale || baseKey !== lastReq.current)

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
        {showHeatmap && (
          <div className="fitting3d-legend">
            <span className="lg lg-tight" />紧绷
            <span className="lg lg-fit" />贴合
            <span className="lg lg-loose" />松弛
          </div>
        )}
        {loading && (
          <div className="fitting3d-loading">
            <Spin tip={threeMod === null ? '加载 3D 引擎…' : '构建试穿场景…'} />
          </div>
        )}
        {solver.status === 'frozen' && (
          <div className="fitting3d-frozen">
            仿真已暂停（数值发散），可点「重新试穿」
          </div>
        )}
        {solver.status === 'idle' && fitting === null && !loading && (
          <div className="fitting3d-loading">
            <Empty description="试穿数据未生成">
              <Button size="small" type="primary" onClick={onGenerateFitting}>
                重新生成
              </Button>
            </Empty>
          </div>
        )}
      </div>
      <div className="fitting3d-side">
        <div className="f3d-card">
          <div className="f3d-card-title">体型</div>
          <div className="f3d-body-line">
            <span>{activeProfile.name}</span>
            {activeProfile.estimated && (
              <Tag color="orange">估计值</Tag>
            )}
            <Button size="small" type="text" icon={<SettingOutlined />}
              onClick={() => setDrawerOpen(true)}>设置</Button>
          </div>
          <div className="f3d-body-girths">
            腰 {activeProfile.waist} · 臀 {activeProfile.hip}
            {activeProfile.thigh ? ` · 腿 ${activeProfile.thigh}` : ''}
            {' '}· 膝 {activeProfile.knee} cm
          </div>
        </div>

        {easeRows.length > 0 && (
          <div className="f3d-card">
            <div className="f3d-card-title">松量读数（成衣 − 体型）</div>
            {easeRows.map((r) => (
              <div key={r.key} className="f3d-ease-row">
                <span className="f3d-ease-label">{r.label}</span>
                <span>{r.finished} / {r.body}</span>
                <span className={r.ease < 0 ? 'f3d-ease tight'
                  : r.ease < 2 ? 'f3d-ease snug' : 'f3d-ease'}>
                  {r.ease >= 0 ? `+${r.ease.toFixed(1)}` : r.ease.toFixed(1)} cm
                  {r.ease < 0 ? ' 紧身' : r.ease < 2 ? ' 偏紧' : ''}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="f3d-card">
          <div className="f3d-card-title">
            快捷参数
            {pendingRegen && <Tag className="f3d-pending">自动重试穿中</Tag>}
          </div>
          {SLIDERS.filter((s) => measurements[s.key] != null).map((s) => (
            <div key={s.key} className="f3d-slider">
              <span className="f3d-slider-label">{s.label}</span>
              <Slider
                min={s.min} max={s.max} step={0.5}
                value={Number(measurements[s.key])}
                onChange={(v) => onMeasurement(s.key, v ?? 0)}
                tooltip={{ formatter: (v) => `${v ?? 0} cm` }}
              />
            </div>
          ))}
        </div>

        <div className="f3d-card">
          <div className="f3d-card-title">显示</div>
          <div className="f3d-row">
            <span>应变热力图</span>
            <Switch size="small" checked={showHeatmap}
              onChange={setShowHeatmap} />
          </div>
          <div className="f3d-row">
            <span>显示人台</span>
            <Button size="small" type="text"
              icon={showBody ? <EyeOutlined /> : <EyeInvisibleOutlined />}
              onClick={() => setShowBody(!showBody)}>
              {showBody ? '开' : '关'}
            </Button>
          </div>
          <div className="f3d-row">
            <span>布料透明度</span>
            <Slider className="f3d-opacity" min={0.2} max={1} step={0.05}
              value={opacity} onChange={(v) => setOpacity(v ?? 1)}
              tooltip={{ formatter: (v) => `${Math.round((1 - (v ?? 1)) * 100)}%` }} />
          </div>
        </div>

        <div className="f3d-card f3d-actions">
          <Button size="small" icon={<RedoOutlined />}
            onClick={solver.restart}
            disabled={solver.status === 'idle'}>
            重新试穿
          </Button>
          <Button size="small" icon={<CameraOutlined />} onClick={screenshot}>
            截图 PNG
          </Button>
          <span className="f3d-status">
            {solver.status === 'running' ? '解算中…'
              : solver.status === 'settled' ? '已稳定'
              : solver.status === 'frozen' ? '已暂停' : ''}
            {fittingBusy ? ' · 计算中' : ''}
          </span>
        </div>
      </div>
      <BodyProfileDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        store={store}
        onChange={setStore}
        measurements={measurements}
      />
    </div>
  )
}
