// 3D 人台视图：three 惰性分包加载（首屏零影响）；真人网格人台常驻
// 显示（morph + 围度闭环 + 纵向对齐，随体型/尺寸重建，静态无解算）。
// 侧栏：体型入口/显示开关/视角/截图。
// 坐标口径：payload 整版全局系 Y-up 直接作为身体高度；θ=0 前中 +Z。
// 2026-09-12 裁撤试穿：布料四半片/腰头环带/结构线/应变热力图/PBD
// 解算与碰撞链整体退役，只留人台显示（演进史见决策日志）；「生成」
// 仍取 payload——body 站点（腰/裆/膝/脚口高度）是人台纵向对齐锚。
import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Empty, Spin, Tag } from 'antd'
import {
  CameraOutlined, EyeInvisibleOutlined, EyeOutlined, SettingOutlined,
} from '@ant-design/icons'
import type * as ThreeT from 'three'
import type { OrbitControls as OrbitControlsT } from 'three/examples/jsm/controls/OrbitControls.js'
import type { FittingResult, Snapshot, Values } from '../types'
import type { BodyGirths } from './bodyProfile'
import { estimateBody } from './bodyProfile'
import {
  findProfile, loadStore, saveStore, type StoreShape,
} from './bodyProfileStore'
import { loadBodyMesh } from './bodymesh/load'
import { loadRawObj } from './rawMesh'
import { useMannequin } from './useMannequin'
import BodyProfileDrawer from './BodyProfileDrawer'

type ThreeMod = typeof import('three')
type OrbitControlsCtor = typeof import('three/examples/jsm/controls/OrbitControls.js').OrbitControls

// 网格直显诊断模式（2026-09-12 160/64A 报障分层排查）：
// ?bodymesh=raw  = MakeHuman 原始 base.obj 零处理直显（A-pose 全身带头带臂）
// ?bodymesh=base = base.bin 直显（vendor 加工后、运行时 morph/标定/对齐全跳过）
// 两档与现行渲染三点对比，定位失真引入层（源数据 / vendor 脚本 / 运行时）。
const BODYMESH_MODE: 'raw' | 'base' | null =
  typeof location === 'undefined'
    ? null
    : (new URLSearchParams(location.search).get('bodymesh') as
      'raw' | 'base' | null)

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
  bodyMat: ThreeT.MeshStandardMaterial
}

export default function Fitting3DView({
  fitting, fittingStale, fittingBusy, onGenerateFitting, measurements,
}: {
  fitting: Snapshot<FittingResult> | null
  fittingStale: boolean
  fittingBusy: boolean
  onGenerateFitting: () => void
  measurements: Values
}) {
  const mountRef = useRef<HTMLDivElement>(null)
  const ctxRef = useRef<SceneCtx | null>(null)
  // 地面格网（场景一次创建；y 随人台 bottomY 落地）
  const gridRef = useRef<ThreeT.GridHelper | null>(null)
  const [threeMod, setThreeMod] = useState<
    { THREE: ThreeMod; OrbitControls: OrbitControlsCtor } | null>(null)
  const [store, setStore] = useState<StoreShape>(() => loadStore())
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [showBody, setShowBody] = useState(true)
  const flyRaf = useRef(0)
  const handlesRef = useRef<ContentHandles | null>(null)
  // 直显诊断：网格加载态 + 挂载物（卸载/重建时释放）
  const [rawLoading, setRawLoading] = useState(BODYMESH_MODE !== null)
  const rawMeshRef = useRef<ThreeT.Mesh | null>(null)

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
  // 人台固定口径（用户 2026-09-11：设置好多少就是多少）：估计体型 = 首次
  // 出现有效尺寸时快照进 store.estimated 持久化，之后成衣参数变化零联动
  //（人台是「穿衣服的人」，不随版变）；显式重估走抽屉「按成衣尺寸重估」。
  // estimated 实时值仅作快照前兜底与重估来源。
  const estimated = useMemo(() => estimateBody({
    waist: Number(measurements.waist ?? 0),
    hip: Number(measurements.hip ?? 0),
    knee: Number(measurements.knee ?? 0),
    thigh: measurements.thigh ? Number(measurements.thigh) : undefined,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [measurements.waist, measurements.hip, measurements.knee, measurements.thigh])
  useEffect(() => {
    // 空面板 waist=0 不快照（防 0 值估计固化）
    if (!store.estimated && Number(measurements.waist ?? 0) > 0) {
      setStore({ ...store, estimated })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store, estimated])
  const activeProfile = findProfile(store, store.activeId) ?? estimated
  const girths: BodyGirths = useMemo(() => ({
    waist: activeProfile.waist, hip: activeProfile.hip,
    thigh: activeProfile.thigh, knee: activeProfile.knee,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [activeProfile.waist, activeProfile.hip, activeProfile.thigh, activeProfile.knee])
  useEffect(() => { saveStore(store) }, [store])

  // ---- 围度喂入构建的 trailing debounce（200ms）：防连续操作（切体型/
  // 重估）逐 tick 重建卡主线程，拖动停顿 200ms 后才重建一次 ----
  const [girthsDebounced, setGirthsDebounced] = useState(girths)
  useEffect(() => {
    const t = window.setTimeout(() => setGirthsDebounced(girths), 200)
    return () => { window.clearTimeout(t) }
  }, [girths])

  const man = useMannequin(fitting?.data.body ?? null, girthsDebounced)

  // ---- 首挂载自动生成一次（进系统即有人台；此后全手动：改参数走左栏，
  // stale 由舞台 Tag + 生成按钮角标提示） ----
  useEffect(() => {
    if (BODYMESH_MODE !== null) return   // 直显诊断：不触发 payload/构建链
    if (fitting === null && !fittingBusy) {
      onGenerateFitting()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    camera.position.set(0, 72, 185)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.target.set(0, 52, 0)
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

  // ---- 直显诊断（?bodymesh=raw|base）：网格原样上屏，零处理不走构建链 ----
  useEffect(() => {
    if (!threeMod || BODYMESH_MODE === null) return
    let alive = true
    void (BODYMESH_MODE === 'raw'
      ? loadRawObj('bodymesh/raw.obj')
      : loadBodyMesh().then((a) => ({
          positions: a.positions, indices: a.indices,
        }))
    ).then(({ positions, indices }) => {
      const ctx = ctxRef.current
      if (!alive || !ctx) return
      const { THREE } = ctx
      // 包围盒自适应取景（raw 全身高 ~170cm、base 裁切后 ~124cm）
      let yMin = Infinity, yMax = -Infinity
      for (let i = 1; i < positions.length; i += 3) {
        if (positions[i] < yMin) yMin = positions[i]
        if (positions[i] > yMax) yMax = positions[i]
      }
      const cy = yMin + (yMax - yMin) * 0.55
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position',
        new THREE.Float32BufferAttribute(positions, 3))
      geo.setIndex(new THREE.Uint32BufferAttribute(indices, 1))
      geo.computeVertexNormals()
      const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
        color: 0xd8c3b0, roughness: 0.85, metalness: 0.02,
      }))
      ctx.scene.add(mesh)
      rawMeshRef.current = mesh
      if (gridRef.current) gridRef.current.position.y = yMin
      ctx.camera.position.set(0, cy, (yMax - yMin) * 1.45)
      ctx.controls.target.set(0, cy, 0)
      ctx.controls.update()
      ctx.render()
      setRawLoading(false)
    }).catch((e) => {
      console.error('[fitting3d] 直显网格加载失败', e)
      setRawLoading(false)
    })
    return () => {
      alive = false
      const mesh = rawMeshRef.current
      const ctx = ctxRef.current
      if (mesh && ctx) {
        ctx.scene.remove(mesh)
        mesh.geometry.dispose()
        ;(mesh.material as ThreeT.MeshStandardMaterial).dispose()
        rawMeshRef.current = null
      }
    }
  }, [threeMod])

  // ---- 内容重建（人台对象更换时：人台网格） ----
  useEffect(() => {
    const ctx = ctxRef.current
    const m = man.man
    if (!ctx || !threeMod || !m) return
    const { THREE } = ctx
    const group = new THREE.Group()
    // 地面格网随人台落地（脚底 = m.bottomY）
    if (gridRef.current) gridRef.current.position.y = m.bottomY

    // 人台（真人网格：morph+对齐后 sourceMesh 直出 BufferGeometry，法线
    // 随绕向——vendor 侧有向体积 +37L = 外法向，Python 金标把守；仅体型/
    // 围度/尺寸变化时重建）。不透明 FrontSide + 深度写入。构建失败
    // console.error 且 bodyMeshes=[] 降级（不炸 React 树）
    const bodyMat = new THREE.MeshStandardMaterial({
      color: 0xd8c3b0, roughness: 0.85, metalness: 0.02,
    })
    const bodyMeshes: ThreeT.Mesh[] = []
    try {
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position',
        new THREE.Float32BufferAttribute(m.sourceMesh.positions, 3))
      geo.setIndex(
        new THREE.Uint32BufferAttribute(m.sourceMesh.indices, 1))
      geo.computeVertexNormals()
      const mesh = new THREE.Mesh(geo, bodyMat)
      bodyMeshes.push(mesh)
      group.add(mesh)
    } catch (e) {
      console.error('[fitting3d] 人台网格装配失败，降级为空', e)
    }
    ctx.scene.add(group)
    handlesRef.current = { bodyMeshes, bodyMat }
    ctx.render()

    return () => {
      ctx.scene.remove(group)
      for (const mesh of bodyMeshes) mesh.geometry.dispose()
      bodyMat.dispose()
      handlesRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threeMod, man.buildVersion])

  // ---- 显示控制同步（可见性直接改，不重建场景） ----
  useEffect(() => {
    const ctx = ctxRef.current
    const h = handlesRef.current
    if (!ctx || !h) return
    for (const mesh of h.bodyMeshes) mesh.visible = showBody
    ctx.render()
  }, [showBody, man.buildVersion])

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

  const loading =
    threeMod === null || man.status === 'building' || rawLoading

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
        {fittingStale && !loading && (
          <div className="fitting3d-stale">
            <Tag color="orange">参数已修改，点左下「生成」刷新人台</Tag>
          </div>
        )}
        {loading && (
          <div className="fitting3d-loading">
            <Spin tip={threeMod === null ? '加载 3D 引擎…' : '构建人台…'} />
          </div>
        )}
        {BODYMESH_MODE === null && man.status === 'idle' &&
          fitting === null && !loading && (
          <div className="fitting3d-loading">
            <Empty description="人台数据未生成">
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
          {fittingBusy && <span className="f3d-status">计算中</span>}
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
