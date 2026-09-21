# PRD: 排料系统对接二期（YLPatternMaking → MaterialSorting 接口集成）

> 配套 PRD：MaterialSorting 侧见 `D:\code\MaterialSorting\tasks\prd-machine-nesting-api.md`（`/api/machine/*` 五端点 + 三运行模式；两仓各自 Ralph 消费，联调里程碑互认）。
> 需求定稿：2026-09-21 两仓规划 + 三轮拍板（v3，15 项决策全定）。一期（2026-09-20）已落地 `/api/nest` 出带 g 码编号 DXF + numMap 弹窗——本 PRD 在其上接通全链路。
> 编号兼容性已闭环验证：块名 `{NAME}-G{NN}-{码}` 与 MS `labeling.py` 两级剥尾缀正则完全兼容，**YL 核心层 `src/ylpattern/` 零改动**。

## 概述 (Overview)

YLPatternMaking 的打版产物（带 g 码编号 DXF + numMap 数量）经 HTTP 接口送入 MaterialSorting 排料引擎求解，在 YL 弹窗内实时看利用率、预览最终排料布局（超排同款观感）、一键下载生产用 PLT。前端永不直连 MS，全部经 YL 后端 `/ms` 同源前缀 httpx 转发；任务状态全在 MS 侧，YL 后端只透传 + 配置翻译（webapp「引擎外薄壳」架构位不变）。

## 目标 (Goals)

- 一期 `/api/nest` 产物零重算复用：NestResultModal footer「发送排料」→ 携带 DXF bytes + numMap/labels/码表进入求解流程
- 表单极简（幅宽 cm 默认 175 + 运行模式三档 select），映射 MS config（gate_mm×10 / run_mode / per_type 全 0 结构 / quantities 展开）
- 2s/15s 双档轮询实时利用率（物理口径标注），弹窗防误关（点遮罩/ESC 均不关），关进度弹窗降频不停任务
- 弹窗内自渲染 SVG 预览（复刻 MS 超排三件套：顶标签 + fit-view 翻转组 + 尺码图例；color 直接消费 manifest，不复刻色表）
- 「下载 PLT」单按钮零参数（MS 默认 plt-clean + 默认表格全算）；结果弹窗显式关闭 → best-effort DELETE 回收 MS 会话名额

## 用户故事 (User Stories)

### US-001: 后端 /ms 代理通道
- **Description**: As a 前端, I want 同源 `/ms` 前缀透传到 MS 服务, so that dev/prod 同构零 CORS 地调用机器端点。文件：`webapp/backend/app.py`（`/ms/{path:path}` httpx 转发路由，镜像 `agent_forward`：懒加载 httpx、`YLP_MS_BASE` 缺省 `http://127.0.0.1:8010`、502 中文含环境变量指引、超时分档 solve/export 120s、status 30s）、`webapp/frontend/vite.config.ts`（dev proxy `'/ms'` → 8010 rewrite 剥前缀）、`webapp/frontend/src/msBase.ts`（新，`MS_BASE` 常量，镜像 `agentConfig.ts`）。
- **Acceptance Criteria**:
  1. `GET /ms/`（MS 首页探针）经 MS 返回 200 且透传 `Cache-Control` 头；MS 未启动 → 502 中文提示含 `YLP_MS_BASE` 指引。
  2. multipart POST 字节透传（echo 夹具断言 body 长度一致）；DELETE 方法可转发；`Content-Disposition` 响应头原样透传（文件流测试）。
  3. 既有后端测试全绿（`python -m pytest tests/ -q`）；`npx tsc --noEmit` 通过。
- **Priority**: 1（可与 MS-US-001 并行；联调前需 MS-US-002）

### US-002: msConfig 配置构建器 + 契约类型
- **Description**: As a 前端, I want numMap/码表/幅宽/运行模式翻译成 MS config 的纯函数, so that 提交载荷口径单一可测。文件：`webapp/frontend/src/msConfig.ts`（新）、`src/types.ts`（MS 契约类型）、`src/msConfig.test.ts`（vitest 金标）。
- **Acceptance Criteria**:
  1. `buildMachineConfig({numMap:{g01:2,g08:1}, sizes:['29','30'], gateCm:175, runMode:'normal'})` → `{gate_mm:1750, sizes:[29,30], run_mode:'normal', per_type:{g01:{d:0,tol:0},g08:{d:0,tol:0}}, quantities:{g01:{'29':2,'30':2},g08:{'29':1,'30':1}}}`（quantities 键为数字字符串；per_type 键集 = numMap/labels 全部 g 码、值恒 `{d:0,tol:0}`）。
  2. runMode 三档映射常量：normal/advanced/extreme（文案「普通运行（180s）/ 高级运行（20min）/ 极限运行（2h）」同源标注）；gateCm 缺省 175、runMode 缺省 normal；非法输入（空 sizes/非数字码）抛可读错误。
  3. **无单码分支**（单码场景由调用侧前置拦截，不进本函数——二期仅推板多码）。
  4. `npm test`（vitest）与 `npx tsc --noEmit` 通过。
- **Priority**: 2（仅依赖类型定义，可与 US-001 并行）

### US-003: useNestSolve 轮询 hook + 五 API 函数
- **Description**: As a 前端, I want 提交任务并双档轮询到终态, so that 展示实时利用率并取回结果。文件：`src/apiHttp.ts`（`msSolveStart/msStatus/msResult/msStop/msExport` 五函数 + `normalizeMsError`，纯 HTTP 不进 `route()` 引擎通道——同 `postNest` 先例）、`src/api.ts`（re-export）、`src/hooks/useNestSolve.ts`（新）。
- **Acceptance Criteria**:
  1. 状态机 `idle→submitting→running→done|stopped|error`；弹窗开 2s / 关 15s 双档轮询，terminal 停表；组件卸载清 interval。
  2. running 期暴露 `{densityPct, elapsedSec, totalSec, perSeed}`；轮询单次网络失败不炸（连续 3 次才转 error）；done 自动拉 result 暴露 `{manifest, best}`。
  3. 409（重复提交）/404/400/502 透传为可读中文错误（`normalizeMsError`）。
  4. `npx tsc --noEmit` 通过（hook 行为由 US-007 冒烟端到端验证）。
- **Priority**: 3（依赖 US-001/002）

### US-004: NestSolveModal 参数/进度/结果弹窗 + 入口 + 弹窗安全
- **Description**: As a 用户, I want 在排料数量清单弹窗点「发送排料」、填幅宽与运行模式后看进度和结果, so that 一键把打版产物送去排料。文件：`src/components/NestSolveModal.tsx`（新）、`src/components/NestResultModal.tsx`（footer 增「发送排料」按钮，`nestResult` 内存透传）、`src/App.tsx`（接线）、参数 localStorage 记忆。
- **Acceptance Criteria**:
  1. 表单仅两项：幅宽 cm（默认 175）+ 运行模式 select（默认普通档）；单码场景入口前置拦截（禁用/不显示，方式以 YL 现有交互惯例为准）。
  2. **弹窗安全**：全程 `maskClosable=false` + `keyboard=false`（点遮罩/ESC 均不关闭）；唯一出口 = 显式关闭按钮；进度期显式关闭 = 降频 15s（task_id 存 localStorage，可「继续查看」重连）；结果期显式关闭 = 停表 + best-effort `msDeleteTask`（失败静默，MS 侧 TTL+7 天兜底）。
  3. 进度区：利用率%（标注「物理口径」）+ 进度条（elapsed/total）+ 阶段（per_seed）+「终止」按钮（→ stopped 态可返回）；error/orphan 显示 MS 中文错误 + 重试。
  4. 通过浏览器验证弹窗布局/交互与现有 antd 主题一致（大弹窗尺寸）；`npx tsc --noEmit` 通过。
- **Priority**: 4（依赖 US-003）

### US-005: NestPreview SVG 自渲染（超排三件套观感）
- **Description**: As a 用户, I want 在弹窗里看到最终排料布局图, so that 不打开 MS 工作台即可核对。文件：`src/components/NestPreview.tsx`（新）。
- **Acceptance Criteria**:
  1. **三件套形态**：顶部标签 `X.XX% · 长度 X.XX cm`（density×100 两位小数、width_mm/10，同 MS NestLabel 口径）+ fit-view SVG（`viewBox="0 0 width gate"`、内容组 `translate(0,gate) scale(1,-1)` 翻转、上下自动留白）+ 右上尺码图例（size→color 去重数值升序，**color 直接消费 manifest 的 piece.color**，不复刻色表）。
  2. 几何：锚点 `piece.raw_polygon ?? piece.polygon`（d=0 时 polygon 过 `_clean_polygon` ≠ raw 的防御）；变换 `world = R(rotation)·p + translation`；**demand>1 的 pid 逐条建 N 个多边形节点**（绝不按 pid 去重——夹具 numMap g01:2 断言 DOM 多边形计数 = placed 条数）。
  3. 无缩放/平移/拖拽编辑交互（静态 fit）；信息条含 利用率/幅宽/料长(m)/片数。
  4. 与 MS `/export` PNG 并排目检布局一致（联调 M2 判据）；`npx tsc --noEmit` 通过。
- **Priority**: 5（依赖 US-004）

### US-006: PLT 下载
- **Description**: As a 用户, I want 下载生产用 PLT, so that 直接交付裁床。文件：`src/apiHttp.ts`（`msExport` blob 下载）、`NestSolveModal.tsx`（结果区下载按钮）。
- **Acceptance Criteria**:
  1. 「下载 PLT」按钮请求体仅 `{task_id}`（**零格式/表格参数**，MS 默认 plt-clean + 默认表格全算）→ blob → `downloadBlob`；文件名优先消费 MS `Content-Disposition`，兜底本地合成。
  2. 下载的 `.plt` 首行含 HPGL 头（`IN;`/`PU` 断言）；文件包含表格区内容（PU/PD 笔画）。
  3. 通过浏览器验证下载交互；`npx tsc --noEmit` 通过。
- **Priority**: 6（依赖 US-005）

### US-007: 文档 + 端到端冒烟
- **Description**: As a 开发者, I want 二期接线文档与自动化冒烟, so that 回归有护栏。文件：`.doc/python工程设计.md` §10.3.2 增补（调用链图/config 映射表/端口与环境变量/运行模式语义区分——YL「高级/极限」= MS race/extreme 求解模式，非时长别名）、`webapp/frontend/scripts/smoke_ms_nest.mjs`（Playwright，镜像 MS `scripts/smoke_*.mjs` 套路：上传→生成→排料→发送（time 短档夹具）→轮询→预览→PLT 下载 + 异常分支 409/终止/502/误关防护）。
- **Acceptance Criteria**:
  1. 冒烟脚本全绿（含四条异常分支）。
  2. 文档增补段完整（含 per_type 全 0 = 缺省语义全等注记、密度物理口径警示）。
  3. `npm run build` + `npm test` + `npx tsc --noEmit` + 后端 `python -m pytest tests/ -q` 全部通过。
- **Priority**: 7（依赖 US-006 + MS 全部 US；M2 换真服务联调）

## 功能需求 (Functional Requirements)

- FR-1: `/ms/{path:path}` httpx 转发（GET/POST/DELETE；multipart 字节透传；`Content-Disposition` 透传；超时分档；502 中文）。
- FR-2: `buildMachineConfig` 纯函数：`{numMap, sizes(推板码表数字), gateCm, runMode}` → MS config（`gate_mm=cm×10`、`sizes=数字[]`、`run_mode`、`per_type` 全 g 码 `{d:0,tol:0}`、`quantities={g:{码:numMap[g]}}`）；缺省 175cm/normal。
- FR-3: 双档轮询（开窗 2s / 关窗 15s）、连续 3 次失败容错、terminal 自动拉 result、task_id localStorage 持久化可重连。
- FR-4: 弹窗安全三则：maskClosable/keyboard 全程禁；进度期关闭=降频；结果期显式关闭=DELETE。
- FR-5: 预览三件套（顶标签/fit-view SVG/尺码图例），raw_polygon 锚点 + 多副本 N 节点 + manifest.color。
- FR-6: PLT 单按钮零参数下载，文件名消费 `Content-Disposition`。
- FR-7: 单码场景前置拦截（二期仅推板多码；处理方式 YL 定）。
- FR-8: 五 API 函数不进 `route()` 引擎通道（纯 HTTP，同 `postNest` 先例）。

## 非目标 (Non-Goals)

- MS 侧任何改动（见配套 PRD）
- YL 核心层 `src/ylpattern/` 改动（零改动，httpx 已在 `[web]` extra，零新依赖）
- PLT 格式/表格字段配置 UI（后续扩展；API 侧 MS 已留 `fmt`/`table` 可选参数）
- per_type 工艺参数编辑（全 0 结构预留）
- 预览缩放/平移/编辑交互（静态 fit；三期议）
- YL 侧并发治理（多任务排队/名额管理留 YL 后续项目）
- 单码打版接入（YL 侧另行处理）
- band/prefix（腰头成带/起始端成套不经二期链路）

## 设计考虑 (Design Considerations)

- 前端永不直连 MS：一切走 `/ms` 同源前缀（复刻 `/agent` 三件套先例），dev/prod 同构、服务发现单点在 YL 后端。
- 任务状态归属 MS：YL 后端不自建任务存储（webapp 是「引擎外薄壳」既定架构位）；前端持 task_id 轮询。
- 预览弹窗尺寸沿用 YL 现有大弹窗；防误关是硬需求（误触导致结果全无）。
- 「高级运行/极限运行」文案与 MS 工作台同名功能语义一致（真实触发 race/extreme），文档需写明非时长别名。

## 技术考虑 (Technical Considerations)

- 端口/环境：YL 后端 8000、MS `MS_WEB_PORT` 缺省建议 8010（两仓同机默认）；`YLP_MS_BASE` 单点覆盖（跨机时 MS token 必开）。
- 坐标系：MS 世界 X=用布长度、Y=门幅且 **Y 向上**——SVG 需 `translate(0,gate) scale(1,-1)` 翻转组（与 MS PNG/R12-DXF 同口径）。
- 密度口径：UI 标注「物理口径」；不与 MS 历史 erode 口径数值对比。
- result 载荷多边形 MB 级：代理超时 120s、预览只渲染一次；必要时后期加简化多边形参数。
- vitest 不查类型（§10.5 已知坑）：改接口必跑 `npx tsc --noEmit`。
- 长任务（2h 极限档）+ 关窗降频：MS 侧 alive-hook 钉住子进程不丢，「继续查看」靠 task_id 重连（MS 内存态路径不受会话逐出影响）。

## 成功指标 (Success Metrics)

- [ ] 冒烟脚本全绿（含 409/终止/502/误关防护四分支）
- [ ] 双通道对拍：YL 自渲染 SVG 与 MS `/export` PNG 并排布局一致（片数/包络 ±1mm）
- [ ] PLT 下载落地（HPGL 头 + 表格区可读，WT/刻字链路可用）
- [ ] 弹窗安全验收：点遮罩/ESC 不关；结果期关闭触发 DELETE（MS 侧名额回收）
- [ ] `npm run build` + `npm test` + `npx tsc --noEmit` + 后端 pytest 全绿
- [ ] M4：普通档对拍 MS 工作台手跑 ±0.5pt（物理口径）必测；高级/极限各抽一单同模式对拍

## 待确认问题 (Open Questions)

- 无阻塞项（15 项决策 2026-09-21 全部拍板）。执行层备注：ESC 与点遮罩一并禁（`keyboard=false`）已并入 FR-4；极限档文案「极限运行（2h）」即满核长跑提示，不加额外警告弹窗。
