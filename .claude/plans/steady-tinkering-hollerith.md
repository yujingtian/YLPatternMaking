# 穿台解算 Worker 化 + 无损提速（~75s → ~10-14s）

## 背景

用户主诉：穿台解算期间「整个画面调整场景视角都是卡卡的，这是要商用的」。两层数字事实（2026-09-23 P3 事后 bench）：

- **卡顿根因**：解算跑在主线程 rAF tick 里，单步 stepDrape ~98ms（浏览器实测）× STEPS_PER_FRAME 3 ≈ 300ms 同步阻塞 → OrbitControls ~3fps。
- **时长根因**：771 帧总量（hold 240 + lowering ~21 + confirm 30 + settle ~480 capped）× ~98ms ≈ 75s 纯计算；node bench 步内分布 dist 26% + bend 26% + collide 42% + strain 5%（5845 粒子 / 5 part / dist+bend 各 ~16k 约束 / 458 缝对 / 3 子步 ×6 迭代）。

已拍板路线（用户选「Worker + 无损提速 ~10s（推荐）」，含「hold 提前转属启动序列行为变化，随本项拍板」）：
**解算搬 Worker 治卡 + sqrt/分箱优化 + 帧数压缩治时长**。目标：交互全程 60fps、总时长 ~10-14s。

## 红线（全部不动）

- 环长恒 = 成衣腰长；偏小是读数不是错误（不静默顶开钉环、不自动调版）
- 确定性双跑（同输入双跑 DressReport 逐字段相等 + pos 数组相等）
- 布不可伸长应变钳 ≤1%（限幅必在 collide 前）
- 启动序列「先静止再动钉」（hold 提前转 = 静止判据复用 sim 自身 settledFrames，语义内）
- 引擎 payload 零改动（全部改动在 webapp/frontend/src/fitting3d/ 层）
- 不代为提交——写完停工作区

---

## 实施一：无损提速（先做；含一次金标重定标）

### 1a. Math.hypot → Math.sqrt ×4（drape.ts）

V8 的 hypot 因 NaN/overflow 语义慢 ~2.7×。四处热点换 `Math.sqrt(dx*dx+dy*dy+dz*dz)`：

- [drape.ts:446](webapp/frontend/src/fitting3d/garment/drape.ts#L446) strainLimit
- [drape.ts:467](webapp/frontend/src/fitting3d/garment/drape.ts#L467) seamPass
- [drape.ts:503](webapp/frontend/src/fitting3d/garment/drape.ts#L503) dist 约束
- [drape.ts:516](webapp/frontend/src/fitting3d/garment/drape.ts#L516) bend 约束

**非热点不动**（seamStats/seamStatsByGroup、stampStiffBands 的 nearSeam/nearHem、placement.ts 构建期）——构建期路径金标不受扰。node 实测 84.8→59.1ms（1.44×）。sqrt 与 hypot 非 bit 等价（ulp 差）→ 混沌盆地重掷 → 一轮金标重定标（见 1d）。

### 1b. nearestRingBoundary 角度分箱 + scratch（placement.ts + drape.ts collide）

现状（[placement.ts:239-272](webapp/frontend/src/fitting3d/garment/placement.ts#L239-L272)）：跨全部环线性扫段（每查询 ~100 段）+ 每次命中分配 RingHit 对象（~17k/步）。collide 逐粒子独立（只读场+自身 pos）→ 顺序不敏感 → 可安全重构：

1. **精确角度分箱**：模块级 `WeakMap<SliceRing, RingBins>` 惰性构建；B=16 扇区，段按中点角入箱；每环 slack = 最大段角跨度。查询剪枝：查询点到「无限楔」的距离下界 = |q−c|·sin(clamp(φ))，φ = 查询角到箱中心角距离 − (Δ/2+slack)，≥ 当前最优 d 则整箱跳过；从查询所在箱向两侧交替外扩、逐侧楔距单调即终止。**精确无漏**（剪的是可证下界）。tie-break 顺序差为测度零事件；金标用 d 精确 + px/pz tol 1e-9 容纳（兜底：候选段排回原全局序）。
2. **scratch 出参**：`nearestRingBoundary(rings, x, z, margin, out?)`——复用调用方提供的 RingHit 对象消灭逐次分配（collide/probeCrotch/report 单线程串行调用，安全）。
3. topSupportY 本轮不动（F3 备份见风险表）。

预期 collide 37→15-22ms，步 ~40-45ms。

### 1c. 帧数压缩（settle.ts + priors.ts）

1. **hold 提前转**（[settle.ts:256-259](webapp/frontend/src/fitting3d/garment/settle.ts#L256-L259)）：`if (state.frames >= holdFrames || s.settledFrames >= DRAPE_PRIOR.settleFrames)` → lowering。settledFrames 是 stepDrape 自持的连续低速帧计数（[drape.ts:573-574](webapp/frontend/src/fitting3d/garment/drape.ts#L573-L574)），hold 期 wake 不触发、计数有效；**零新常数**——「静止」定义全局唯一（settleSpeed/settleFrames 同源）。settle.ts 增 import DRAPE_PRIOR。
2. **settleMaxFrames 480→200**（priors.ts DRESSING_PRIOR + 注释换代）：wake() 的 `max(maxFrames, stepCount + settleMaxFrames)`（[settle.ts:174](webapp/frontend/src/fitting3d/garment/settle.ts#L174)）自动跟随。maxTotalFrames 1800 兜底不动。

帧预算：240→~80（hold 提前）+ ~21 + 30 + ≤200 ≈ **330-350 帧**（原 771）。

### 1d. 金标重定标 + 超时收紧

- **dress.test.ts**：dropF/dropB ∈[1,3] 重测、frontRim >6 重测、minY、正面扇区 med 窗、zhitong 断言、双跑确定性照旧必须过。
- **drape.test.ts**：自由垂夹具重测（settle 帧数等）。
- **settle.test.ts** +2 hold 用例：stub sim.settledFrames 钉在/差一于 DRAPE_PRIOR.settleFrames。
- **dressfield.test.ts** +分箱等价用例：分箱版 vs 暴力参考（随机查询点阵），d 精确、px/pz 1e-9。
- **超时收紧**（测试提速 ~10×后防假绿漂移）：dress.test 480_000→180_000、300_000→120_000（hips+/zhitong）、60_000 偏小款不动、drape.test→120_000。
- 数字全部实测后回写（measure before claiming，P3 教训）。

**阶段门**：tsc + vitest 全绿 + bench 数字记录 → 才进实施二。

---

## 实施二：Worker 迁移（零物理改动、金标不动）

### 2a. 新 `garment/solvestate.ts` —— 序列化/再水化

`toSolveState(sim, probeIdx, jam, heatOn)` → structuredClone 可通过的对象；`fromSolveState(state)` → {sim, probeIdx, jam}：

- DrapeSim 全部字段可克隆，唯二障碍：
  - `field: BodyField` → 传构造参数 `{table, rows, rowStep, thetaBins, slices: {pts:Float64Array, cx, cz, r}[][], yMin}`，worker 侧 `new BodyField(...)`；perimCache/分箱 WeakMap 惰性重建（确定性：同输入同输出）。
  - `parts[].mesh`（ClothMesh 含 locate 闭包）→ 收窄 `SolverMesh {dist, bend, bendKArr?}`——求解器只读这三个（drape.ts 消费点已核实），**类型级收窄、运行时零拷贝复用**。
- probeIdx = `buildCrotchProbeIdx(pair)` 产物（main 线程建，plain number[][]）；jam = `{ringTotal, rowY}`（[Fitting3DView.tsx:510-512](webapp/frontend/src/fitting3d/Fitting3DView.tsx#L510-L512) 现值）。
- ctrl 必须在 worker 侧 `buildSettle(sim, probeIdx, {jam})` 重建（闭包快照 fArr/baseY 读 sim.pinIdx/pinTarget，构造后即自洽）。

### 2b. 新 `garment/dressDriver.ts` —— 双宿主解算驱动（node 可测）

```ts
createDressRun(sim, probeIdx, jam, heatOn, sink): {
  stepOnce(): boolean   // false = 终态
  setHeat(on): void
}
```

stepOnce **逐字复刻 tick 语义**（[Fitting3DView.tsx:644-678](webapp/frontend/src/fitting3d/Fitting3DView.tsx#L644-L678) 现行）：`st=stepDrape(sim); ph=ctrl.step(sim); finished = st!=='running' && !(ctrl && ph!=='done')`（ctrl null → finished = st!=='running'）；热力图按 HEAT_PRIOR.every 节拍（frames 在步内自增）经 sink 回调。sink：`onFrame(frame, pos, heat?)` / `onDone(report, pos, heat?)` / `onError(err)`。主线程与 worker 共用此驱动（worker 是其中一宿主）。

### 2c. 新 `garment/dressWorker.ts` —— worker 入口

- 协议：`init {state, probeIdx, jam, heatOn}` → 每步 `frame {frame, pos: sim.pos.slice()（transfer）, heat?}` → `done {report, pos, heat}` → `error {message}`；`setHeat {on}`（worker 存活期内随时）。
- **调度 = MessageChannel 自 post**：每宏任务跑 1 个 stepDrape（非 setTimeout——嵌套定时器 4ms 钳 ~10% 开销；兜底方案 setTimeout 2 步/任务留注释）。
- 热力图 worker 侧算：computeHeat 只读 sim.pos/field/yLift（gap-only 现行），heat Float32Array 随 frame 传。
- done 后 worker 不 terminate（setHeat 重着色用）；epoch 重跑/组件卸载由 main 侧 terminate。
- 先例：engine/client.ts `new Worker(new URL(...), {type:'module'})`；vite.config `worker.format:'es'` 已配。

### 2d. Fitting3DView 接线改造

- **构建留在主线程**（~0.4-0.5s 一次性，非热点）：现有 build 链不动 → `toSolveState` → post init（**transfer 后主线程不再碰 sim**——pos buffer 已 detach；初摆位出画用 pair.pos）。
- 删 rAF tick 循环；onFrame → **rAF 合并绘制**（最新 pos 存 ref，每 rAF 一次视图回填 + render——帧消息频率 ~25Hz < rAF 60Hz，天然合流）；onDone → 末帧绘制 + `setDressReport(report)`。
- dressViewsRef 语义改：`{applyPos(pos), applyHeat(heat), setHeat(on)→postMessage, clearHeat()}`——**不再存 sim**；热力图开关效应改走 setHeat 通道（worker 端重算 heat 回传重着色，开关仍不重跑仿真）。
- 生命周期：每次 dress 大效应 spawn 新 worker、cleanup `worker.terminate()`（StrictMode 双挂载安全）；worker error → setGarmentError。
- STEPS_PER_FRAME 常量随 tick 循环删除（worker 自由步进取代）。

### 2e. 新 `garment/solvestate.test.ts`

- structuredClone 往返 + fromSolveState 再水化 → 与内存直跑 **20 步 bitwise pos 相等**（确定性红线在序列化层的验证）。
- driver 等价：createDressRun 双宿主（内存 sim vs 再水化 sim）同帧数同 report。

---

## 风险与回退

| 风险 | 处置 |
|---|---|
| sqrt ulp → 盆地重掷、某夹具劣化 | sqrt 与分箱**分开落地**（便于二分）；金标重定标吸收正常漂移 |
| 分箱 tie-break 顺序差（测度零） | 等价用例 d 精确 + px/pz 1e-9；兜底候选段排回原全局序 |
| 序列化遗漏字段 | 往返测试 20 步 bitwise 相等 + worker error 通道透出 |
| transfer 后主线程读 detach buffer | 初画用 pair.pos；dressViewsRef 不存 sim；post 后 sim 弃用 |
| StrictMode 双挂载双 worker | 每次效应 spawn + cleanup terminate |
| MessageChannel 不可用 | setTimeout(0) 每任务 2 步兜底（注释留） |
| 分箱后 collide 仍不达标 | F3 备份：topSupportY 对 fl−3..fl+9 行先做包围圆预扫、全外 → null（精确，~11 行检查砍掉深扫） |

## 验证

1. `npx tsc -b` 零错。
2. `npx vitest run src/fitting3d/garment`（新 solvestate/dressfield/settle 用例 + 重定标全绿）。
3. `npm test` 全量（timeout 收紧后全绿）。
4. `npm run build`（worker 打包通过）。
5. 临时 perf diag（`throw new Error(JSON.stringify(...))` 先例）：步时/帧数/总时长三数字实测记录进文档后删临时件。
6. 浏览器手验（uvicorn + npm run dev）：解算中拖相机全程流畅（60fps）；解算中/终态切热力图；「重新试穿」epoch 重跑；zhitong 长裤盖脚形态不变；dev StrictMode 无残留 worker。

## 文档同步（stop-hook 契约）

- §10.11 新条：穿台解算 Worker 架构（协议/调度/序列化口径）+ 提速实测数字（规格只写现行，历史归日志）。
- 决策日志：本期条目（P3 事后纠偏的延续——worker 化拍板、两阶段落地、实测数字、hold 提前转口径）。
- CLAUDE.md：穿台句补「解算 Worker 化」一句。
- 全部完成后停工作区，不 git commit。
