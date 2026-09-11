# 3D 人台换真人网格（MakeHuman CC0 数据 + 自研 TS morph 引擎）

> 前一版计划（第五轮形体打磨）已完成并验收（2026-09-11 七图 VLM 全过），本版整体替换。

## Context

用户对七轮程序化打磨后的环放样人台仍不满意（VLM 判读用户截图：等径管状 + 椭圆堆叠感、无解剖 S 曲线）——环放样的表达力已到结构性天花板，继续调锚无法根治。用户要求找 GitHub 现成开源库替换。21-agent 调研工作流（5 路扫荡 → 25 候选去重 → 8 深读 → 对抗验证）已完成，**用户拍板两项**：

1. **许可红线 = 商用安全**：只用 CC0/MIT/Apache；MakeHuman 只借 CC0 数据、绝不移植其 AGPL 代码；SMPL 家族整体出局。
2. **集成路线 = B**：MakeHuman CC0 数据（基础网格 + 围度 .target）+ 自研 TS 稀疏 morph 引擎 + 闭式围度标定环 + 径向高度场碰撞桥。

## 调研结论（已对抗验证）

| 候选 | 许可 | 判定 |
|---|---|---|
| **MakeHuman Community v1.3.0 资产** | 源码 AGPL / **捆绑资产 CC0 1.0**（LICENSE.ASSETS.md；§D 输出物无主张） | ✅ 唯一「数据干净且围度键齐」的源 |
| OxiHuman v0.2.1 | Apache-2.0 + CC0 单资产 | 参考实现（MakeHuman 拓扑兼容独立实现），不引运行时 |
| SMPL-X / SMPL 家族 | 禁商用 + 禁任何形式第三方分发 + 注册墙 | ❌ 产品路径死路（连 SaaS 后端渲染都禁） |
| MB-Lab / GarmentMeasurements | 数据文件 AGPL / GPL+上游存疑 | ❌（MB-Lab 仅借「三点采样反演」思路） |
| MPFB2 | GPL 代码 + CC0 资产 | 离线备选源（headless Blender 烘焙） |
| GarmentCode(Data) | MIT 但资产 SMPL 灰区 / 数据集 CC BY 4.0 | 仅备选校准数据集，v1 不用 |

**关键事实**（verify agent 直接探测证实）：makehumancommunity v1.3.0 `data/targets/measure/` 实测含 `measure-thigh-circ-incr/decr.target`、`measure-knee-circ-incr/decr.target`（另有 calf/ankle、waist/hips），全 CC0——**BodyProfile 四键（腰/臀/大腿/膝）与可用数据一一对应**。`.target` 格式 = 稀疏顶点增量（行：顶点索引 dx dy dz）；基础网格 21,833 顶点 MakeHuman 拓扑，模型空间 decimeter Y-up（×10 → cm）。

## 方案总览

```
vendor 脚本(一次性, Python)                运行时(前端, 全新 bodymesh/ 模块)
base.obj + *.target ──解析/裁切/重映射──▶ data/{base.bin, targets.json}
                                            │ load.ts → morph.ts (pos = base + Σwᵢ·Δᵢ)
                                            │ align.ts (三站最小二乘均匀缩放+平移)
                                            │ calibrate.ts (围度闭环 ±1.5%)
                                            │ heightfield.ts (三管 R(y,θ) 表)
                                            ▼
                              mannequin 适配层（保 sectionAt/radiusAt/surfaceRadius 签名）
                                            ▼
                    Fitting3DView 渲染 BufferGeometry（skin.ts 的 SDF+MC 整体退役）
```

**红线（全部保持）**：seams.ts / pbd/ / collide.ts 零改动（适配层保签名）；引擎零改动（不重打 engine zip）；BodyProfile 四键 + 体型管理 UI + localStorage 契约不变；garmentGap/collideSweeps 不动。

## 实施阶段

### P0 数据获取与 vendor（脚本一次性）

- **来源优先级**：A) github makehumancommunity/makehuman tag v1.3.0（base mesh + `data/targets/`）；B) makehuman-assets LFS repo；C) OxiHuman release 的 `oxihuman-core-v1.ohpk`（CC0、provenance 钉同一 commit 1f508f6）。⚠️ 本会话 github 网络阻断（WebFetch/webReader/API 三路全断），实施时重试；脚本也支持对手工下载的本地文件跑。
- `scripts/vendor_makehuman.py`：解析 base.obj（三角化、dm→cm）+ 选定 targets（**macrodetail 女性 1-2 个**〔基础网格是中性人，女性形态靠 macro target〕+ **measure 腰/臀/大腿/膝 ± 共 8 个**）→ **下半身裁切**（腰上 ~18cm 等位高度截断 + 边界环质心扇形封盖，拓扑跨 morph 恒定）→ **target 顶点索引按裁切重映射** → 产出 `webapp/frontend/public/bodymesh/{base.bin, targets.json}`（位置 Float32 + 索引，~1MB 级 gzip，挂 three 同一惰性分包；可选 Int16 量化减半）。
- **许可合规**：CC0 全文（LICENSE.ASSETS.md）随数据 vendor；`PROVENANCE.md` 记 repo/tag/commit/文件清单；资产文件头扫描留档。

### P1 加载 + morph + 渲染（先旁路验证）

- `bodymesh/{load,morph}.ts`：fetch bin → Float32Array；`morph(positions, weights)` 稀疏应用增量 + `computeVertexNormals`（21.8k 顶点 ms 级）；Fitting3DView 挂 BufferGeometry。
- 本期与旧人台**并存**（priors 加 `USE_BODYMESH` 常量开关），刷新即直观对比新旧。
- **实施第一步**：读 seams.ts / collide.ts 确认 `sectionAt/radiusAt/surfaceRadius` 的精确消费签名（§10.11 口径为准），适配层契约以实读为准。

### P2 地标对齐

- v1 不用 height/proportion macro → 基网格比例恒定，**地标分数（crotch 分叉/waist 最窄/knee/ankle/脚底）离线一次测出记常数**（PROVENANCE 注明来历）。
- 运行时：mesh crotch/knee/hem 三站 vs payload.body.stations 同名三站**最小二乘均匀缩放** + crotch 平移；`groundY := 对齐后脚底`（真脚取代脚盒，地面跟随）；残余站高偏差由「围度在 payload 站点高度闭环」兜底（碰撞面按高度场在 payload 站点标定，布料贴合不受骨性标志小错位影响）。

### P3 围度闭环标定

- `calibrate.ts`：雅可比式联合迭代——逐站在 payload 站点高度量网格围度（切片折线周长）→ 误差 → **MB-Lab 三点分段线性反演**（每 target 预标定 w=0/0.5/1.0 的围度斜率）→ 联合更新 4 权重 → 3-5 轮收敛 **±1.5%**（同现行环标定口径）。
- 权重钳 ±1.5（线性外推覆盖滑杆上限）；病理体型不收敛 → 钳制 + 残差披露（诚实降级，先例：「腿确实比盆宽」）。
- MakeHuman measure 页自身开环不精确（issue #16）与本项目无关——我们自带闭环。

### P4 径向高度场桥（碰撞/摆位零改动的关键）

- **三管结构保持**（collideOne 逐管投影语义不变）：骨盆管（轴 x=0）+ 左右腿管（轴 `cx(y)` = 逐切片腿质心采样 → **分段线性**拟合，Lipschitz 论证前提保持）。
- 逐管 `R_tube(y,θ)` 表：y 步 ~0.5cm × θ 256，顶点按最近管 splat + 邻域插值 + 微膨胀封缝（管内截面近星形凸，与现超椭圆同假设；两腿分离区按管拆分解决单值性）。
- mannequin 适配层：`radiusAt` = 表 θ 双线性插值 + skin 0.3；`surfaceRadius`（摆位）= 该 y 覆盖管 R 的 max（凸上界口径同现）；`sectionAt` 返回切片柄。
- 解耦金标换成「**高度场 vs 网格真面**」双测度：站点围度一致 + 轴心射线首穿差 ≤ 容差（取代 skinField/unionField 参照）。

### P5 切换 + 退役

- **先 `git commit` 留档七轮人台改动**（工作树 +1093/−356 未提交，退役前必须进历史）。
- `USE_BODYMESH = true`；删 skin.ts（SDF+MC）、环模型（buildMannequin 三管/超椭圆/SAGITTAL 梯子/脚盒/脐先验/monoSplineAt 形状部分）；priors.ts 收敛为 `SOLVER_PRIOR`（collideSweeps 等不动）+ 新 `BODYMESH_PRIOR`（切片步/θ 数/权重钳/标定容差/裁切高度）。

### P6 测试重写 + VLM 验收 + 文档

- **新 `bodymesh.test.ts`**（数据缺席整文件 skip，test_reverse_gold 先例；逻辑用合成小网格覆盖）：拓扑跨 morph 恒定（V/E/F 不变 + 含封盖水密）；站点围度 ±1.5%；**单调响应 + 跨参数串扰界**（如 thigh target 动膝围 < 阈）；病理收敛/诚实降级；高度场-网格一致性。
- `fitting3d.test.ts`：estimateBody/摆位约定/碰撞投影/全 pin settled **结构金标保留**（锚值按高度场重 dump 回填）；环模型专属不变量（SR 接合锚/SAGITTAL S 曲线/缝隙梯子/worstLip 等）整体退役 → 决策日志留档退役清单。
- `skin.test.ts` 删除（SDF 蒙皮随子系统退役）。
- **integration 零语义变化**：引擎 fixture 不变（引擎零改动）、断言语义不变（参照面 helper skinField → 高度场），−0.15 容差 / collideSweeps 3 不动——桥行为等价性的最强证明。
- **VLM 七图验收**（harness 同记忆口径：Playwright 截图 → analyze_image 分批 2-3 防 429；已知简化清单更新：无头/无臂/腰上截断平盖/单色无纹理，删「两段圆角盒脚」——现在是真脚）；std 正/侧/背/斜/default + 病理双图不炸。
- 文档：§10.11 「人台人体化/形体塑形/SDF 蒙皮」三节 → 「真人网格人台」节重写（数据来源与许可/morph/对齐/标定/高度场）；决策日志 §十一 新条目（调研矩阵/两项拍板/退役清单）；记忆 mannequin-shape-root-cause.md 增补换轨记录。

## 风险与回退（优先序）

- **github 网络持续阻断**（本会话实测三路全断）→ vendor 延后 / 换 ohpk 源 / 用户手工下载放本地喂脚本；数据缺席不阻塞 P1/P4 的合成网格开发。
- **thigh/knee target 对 payload 站点高度影响弱**（target 影响带 vs 站位错位）→ 检查 target 空间覆盖；必要时 vendor 附加 macro（weight ±）扩形状自由度（纯数据增量零代码）。
- **标定耦合不收敛**（measure targets 非正交）→ 联合迭代 + 阻尼；病理极限钳制 + 披露。
- **高度场稀疏区空洞/表缝** → splat 邻域 + 膨胀兜底，围度一致性金标把守。
- **性能**：morph+法线+高度场 splat 全部 ms 级，远低于现 MC ~200ms，200ms debounce 预算内。
- **视觉仍不满意** → 加 macrodetail/weight targets 扩形状空间；最终回退 = `USE_BODYMESH=false` 一行恢复环模型（验收前并存开关保底）。

## 验证

1. `cd webapp/frontend && npx tsc -b && npm test`（bodymesh + fitting3d 重写金标 + integration 全绿）。
2. `npm run build` 产物体积检查（bodymesh 数据挂惰性分包，首屏主包零增量）。
3. 引擎侧零改动确认：`git status` 无 src/ylpattern 变更；`python -m pytest tests/ -q` 照常全绿。
4. 浏览器（uvicorn 用户驻 8000，刷新即生效）目检 + VLM 七图逐项验收 + 病理预设切换不炸。
5. 许可合规自查：vendored 数据含 CC0 全文 + PROVENANCE；`grep -ri "makehuman"` 前端源码无移植代码痕迹（只有数据格式解析）。
