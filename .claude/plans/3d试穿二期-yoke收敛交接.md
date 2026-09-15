# 交接：育克整裤 solver 收敛（2026-09-14）

> 接续会话读这份 + 摘要里的压缩前上下文即可无缝继续。
> 任务唯一失败项：`webapp/frontend/src/fitting3d/garment/worker/solver.test.ts`
> yoke 用例（16 缝整裤 480 帧内收敛）不收敛，`expected -1 to be greater than or equal to 0`。

## 业务背景（用户原话，2026-09-14）

「那一条完整的牛仔裤缝合需要那些部分，你不知道么？如果是裁片的话，那就是腰头育克前片后片。前腰头缝合前片，后腰头先和育克缝合再和后片，做程序要站在实际的业务场景」

装配链：前腰头↔前片腰口；后腰头↔育克上口；育克下口↔后片上口；侧缝上段随育克。这修订了「payload schema v1 零改动」红线（payload 增第 4 片 back_yoke）——已实施，需记决策日志（未记）。

## 当前状态：seams.ts 修复已完成但未达收敛

**已改**（工作区，未 commit）：`seams.ts` 侧缝链式拆分——上段配对起点从 `fy` 改为 `1−fb`（消除交界 0.6cm 条带双重预订，四交汇点永久拔河泵=旧环向蠕动泵根因）。注释已完整写入口径与反例。

**修复验证结果（已跑，双跑逐帧一致）**：
```
对照A(无bendKArr): settledAt=-1 终avgV=10.577 seam=0.034/0.360 pen=0.000/0
  轨迹: f0=31.19 f150=11.26 f300=6.34 f450=9.29 f600=10.62 f750=10.51
对照B 完全一致（确定性验证通过）
```

**结论：修复有效但不充分**——旧蠕动泵已死（见下），暴露下一层新泵。

## 诊断事实链（已确认，勿重查）

1. **旧泵（环向蠕动）已死**：修复前漂移比（净位移/路径长）0.967 纯漂移；修复后 0.486→0.245→**0.074 稳定**（f600 起）——剩余运动是**原地往复振荡**，不是漂移。
2. **新泵 = 整裤全局低频摆振**（diag2 数据，f300~f900）：
   - avgV 平台 ~10.5，99.8% 粒子不接触人台（游离 6022~6031/6035），**全体均匀抖 8~14**（front 11~13.6 / back 8.6~10.2 / yoke 8.5~9.3 / band 8.1）——全局模态非局部病。
   - 领头者恒在**前片脚口内角**（pattern x≈12~17, y≈0~7；脚口=pattern y 0 线），速度 ~27~50。
   - **L/R 半边反相交替**：f300 时 L 半边近静（front_L=3.29/back_L=2.03/yoke_L=2.18）R 半边在动（12.03/8.41/8.41）；f900 反转——像绕前后轴的扭转摆动，波在环上轮流经过 L/R。
   - 交汇点粒子（4 个，front 侧缝 t=1−fb 处）v=1.7~8.4，**非领头者**——交界三角不闹了。
   - 缝距 avg 0.034 / p95 0.360 快照达标（但布在抖，快照误差是瞬时的）；穿透全 0。
   - 接触粒子仅 4~29 个、均速 15~20 恒定——接触不是主泵源。
3. **物理解释（当前假设）**：band 顶行 pinYOnly（Y 钉 XZ 自由）→ 整裤环向无锚；99.8% 粒子悬空无摩擦阻尼；damping 0.985/子步衰减压不住约束投影（GS 走带/过冲）注入的能量 → 持续极限环。M1（无 yoke、11 缝）同参数收敛 313/314 帧——差异在 yoke 环带带来的质量/约束拓扑。

## 已失败对策（勿重试，均有反证）

| 对策 | 结果 | 死因 |
|---|---|---|
| 缝投影偶迭代反向扫描（tmp_solver_alt.ts） | yoke 地板 4.98~5.45 且 M1 坏成 1.44~1.58 | 泵能量改道各向抖动 |
| 静摩擦阈值 STATIC_EPS=0.05（tmp_collide_static.ts） | 杀蠕动但地板不动 4.275 | 非接触松量布料摩擦够不着 |
| 摩擦 1.0 | 假 settle 157，pen 19.5/4794 | 接触粒子切向冻结→塌陷 |
| 锚定单粒子 | 假 settle 175 | 冻死穿衣所需旋转模态 |
| 育克整片 bend 增硬 0.5/0.9 | （修复前数据）无效 | 根因不在刚度 |

## 方法论红线（血泪教训）

- **单次运行地板比较无意义**：Float32Array.fill(0.3) 与字面量 0.3 的浮点差 → 数百帧后轨迹分岔 → 不同 basin → 地板 4.3 vs 11.7。比较必须双跑验确定性 + 认清 basin 彩票。
- **初摆位塌陷靠滑动穿衣**：f0 穿透 ~5400/6035（会阴区两腿空隙，凸包场计穿透但 BVH 无推力），穿衣（un-slump）靠持续环向滑动完成（f600 pen 0.9/12）。**任何冻旋转的对策 = 冻在塌陷态假收敛**。
- M1 settle 于 314 帧，settle 瞬间 avgSpeed 0.53（阈值下冻结）；M1 f150→f300 的滑动是穿戴瞬态，yoke 的是永久泵——区分标准=pen 清零后速度是否仍在。
- **damping 是全局观感参数**（VLM 悬垂复调待做）：动它必须 M1 同步重验 + 后续 VLM 复调覆盖。

## 下一步：跑已写好的 damping 扫描（脚本已就绪未跑）

`out/tmp_yoke_diag3_entry.ts`（已写好）：yoke @ damping 0.96/0.93/0.90 各 900 帧 + M1 @ 0.96/0.90 回归（须 settledAt≤360）。SOLVER_PRIOR 运行时可写（as const 只是类型层），在 createSim **之前**改。

```bash
node -e "require('D:/work/YLPatternMaking/webapp/frontend/node_modules/esbuild').build({entryPoints:['out/tmp_yoke_diag3_entry.ts'],bundle:true,platform:'node',format:'cjs',outfile:'out/tmp_yoke_diag3_out.cjs',nodePaths:['D:/work/YLPatternMaking/webapp/frontend/node_modules']}).then(()=>console.log('built')).catch(e=>{console.error(e);process.exit(1)})" && node out/tmp_yoke_diag3_out.cjs
```

**判读**：yoke 任一 damping 档 settledAt≥0 且 ≤480、seam avg<0.3/p95<0.8、pen worst≤0.15/count<50，且 M1 同档 settledAt≤360 → 把该值写进 priors.ts（带标定注释，参照 denimBendStiffness 注释格式）→ 跑 vitest。

**若 damping 全无效**（极限环不衰减，说明是投影持续注入非欠阻尼）→ 候选顺序：
1. iterations 6→8（投影更收敛，走带残余小）——同法验证 M1；
2. substeps 3→4；
3. 结构对策：脚口边缘增重/局部阻尼（无先例，需设计）。
勿再碰：solver 扫描顺序、摩擦分支、锚定（上表全反证）。

## 收尾清单（收敛后按序）

1. `cd webapp/frontend && npx vitest run src/fitting3d/garment/worker/solver.test.ts`（timeout≥420s）3/3 绿；
2. `cd webapp/frontend && npm run build:engine`（引擎侧 exporters/fitting.py 等已改，Pyodide zip 未重打）；
3. 全量回归：仓库根 `python -m pytest tests/ -q`；`cd webapp/frontend && npx vitest run` + `npx tsc -b --noEmit`（garment.test 18/18 不受 seams 修复影响——16 缝计数公式不变）；
4. 删临时文件：`out/tmp_yoke_diag_entry.ts`、`out/tmp_yoke_diag2_entry.ts`、`out/tmp_yoke_diag3_entry.ts`、`out/tmp_solver_alt.ts`、`out/tmp_collide_static.ts`、`out/tmp_yoke_diag_out.cjs`、`out/tmp_yoke_diag2_out.cjs`、`out/tmp_yoke_diag3_out.cjs`、仓库根 `tmp_yoke_diag.txt`；
5. 文档同步：`.doc/python工程设计.md` §10.11（pieces 序、16 缝、rot180、侧缝拆分共点口径、收敛标定值）；`.doc/决策日志.md` 新条目（2026-09-14 用户业务口径修订：payload 增育克片 + 侧缝双重预订坑 + 摆振对策）；CLAUDE.md 3D 段试穿链一句话；`.claude/plans/3d试穿二期-复活.md` 纠坑 #4 改已解决；
6. 记忆：更新 `garment-dressing-revival-facts.md`（yoke 支持完成态、basin 彩票/塌陷滑动方法论）；新建 feedback 记忆「做程序要站在实际的业务场景」（牛仔裤装配链业务事实）；
7. 残留（需用户配合）：摩擦 0.5 与丹宁 0.5 悬垂观感 VLM 八视角复调（damping 若改也纳入）。

## 红线（持续有效）

- solver 旧 PBD 原样复活：**solver/collide 代码不动**；priors 常数可调（denimBendStiffness 先例）。
- 碰撞 three-mesh-bvh；独立原则（人台参数不改衣服）；弯腰头回退视觉环带+提示；vlm.toml gitignored。
- **用户未要求 git commit，勿自行提交。**

## 环境坑

- esbuild 打包 out/ 下入口必须带 `nodePaths: ['D:/work/YLPatternMaking/webapp/frontend/node_modules']`（否则 'three' 解析不到）。
- 诊断脚本运行期 `readFileSync` 路径相对仓库根（不是 out/）。
- vitest 吞 console.log；solver 测试 timeout≥180000；900 帧诊断单跑 ~40-60s。
- fixture：`garment/fixture_fitting.json`=M1（无 yoke）、`fixture_fitting_yoke.json`=yoke 版。
