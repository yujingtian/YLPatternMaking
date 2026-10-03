# PRD: 排料双通道(前端直连本地 MS 优先 + 后端代理服务器 MS 回退)

## 概述 (Overview)

YL 部署到服务器后,现有 `/ms` 同源代理打的是服务器自己的 loopback,连不到用户本地 MS——排料链路断裂。本 PRD 落地双通道策略:**优先** YL 前端浏览器直连用户本地 MS(VB超排 exe,`http://127.0.0.1:8010-8019`,跨源 CORS+PNA 由 MS 侧配套支持),探测不通**回退**现有 `/ms` 代理连服务器上部署的 MS(与 YL 后端同机 loopback + token 注入,现有代理代码零改动保留);任务终态后 PLT/.msn/result JSON 统一回传 YL 后端存档。MS 侧配套改动另立 MS 仓 PRD(`D:\code\MaterialSorting\tasks\prd-machine-browser-direct.md`)。

## 目标 (Goals)

- 用户本机装有 VB超排 exe 时:排料任务跑在本地(用户机算力,通常远强于服务器),浏览器直连全链(solve/status/result/export/state-file)
- 本地 MS 未启动时:自动回退服务器 MS 通道,排料功能不断(性能受限于服务器,UI 明示)
- 两通道任务结果统一回传 YL 后端存档(`out/nest_archive/`),YL 侧首次拥有排料历史落盘

## 用户故事 (User Stories)

### US-001: msBase 通道选择层(直连端口发现 + 代理回退)
- **Description**: As a YL 用户, I want 排料发起时自动探测本地 VB超排并选择通道 so that 有本地 MS 走高性能直连、没有则无感回退服务器排料。
- **Acceptance Criteria**:
  1. `src/msBase.ts` 新增异步 `resolveMsChannel(): Promise<{kind:'direct', base:string} | {kind:'proxy'}>`:并发 fetch `http://127.0.0.1:8010..8019/api/machine/ping`(AbortSignal 短超时 ~300ms,10 候选毫秒级),首个命中 → direct 缓存 base;全败 → proxy
  2. **必须用 `127.0.0.1` 字面量**(MS 只绑 IPv4 loopback;`localhost` 可能解析 `::1`;局域网 IP 被 HTTPS mixed content 硬拦)
  3. `VITE_MS_BASE` 显式覆盖保留(运维兜底);`MS_WORKBENCH_URL`(三期引导链接,现写死 8010)跟随发现端口,未发现时保持缺省
  4. 单测 `src/msBase.test.ts`(已有先例):命中/全败回退/VITE_MS_BASE 覆盖/缓存语义(mock fetch)
  5. `npm run test` 全绿;TypeScript 编译零错误
- **Priority**: 1

### US-002: apiHttp 通道感知(七函数跟随 + state-file 双通道分派)
- **Description**: As a YL 前端开发者, I want MS 请求层通道感知 so that 七个 ms* 函数与 .msn 下载在直连/代理两通道下都正确工作。
- **Acceptance Criteria**:
  1. `src/apiHttp.ts` 的 `msJson` 壳(252-260)base 改为通道感知:direct → 发现的 base;proxy → `/ms`(现状路径零变化)
  2. `msSolveStart/msStatus/msResult/msStop/msDeleteTask/msExport`(266-330)自动跟随通道,函数签名与调用方零改动;multipart 手不设 Content-Type、30s timeout 既有约定不变
  3. `msStateFile`(339-352)双通道分派:direct → `GET {base}/api/machine/solve/{id}/state-file`(MS 侧浏览器直连模式不设 token);proxy → 现状 `GET /api/nest/tasks/{id}/state-file`(YL 后端注入 token)零改动
  4. 直连通道的跨源失败(CORS/PNA 未放行、MS 版本过旧无 ping)归一为「回退 proxy」——通道降级容错在请求层兜底
  5. 单测更新(`apiHttp` 相关 + `normalizeMsError` 双形态既有约定);`npm run test` 全绿
- **Priority**: 2(依赖 US-001)

### US-003: useNestSolve 通道绑定与 NestSolveModal 通道体验
- **Description**: As a YL 用户, I want 排料弹窗明示当前通道、本地 MS 中断时有清晰出路 so that 我知道任务在哪跑、断了怎么恢复。
- **Acceptance Criteria**:
  1. `src/hooks/useNestSolve.ts` 提交流程前置通道探测;任务生命周期(task_id)绑定通道,localStorage 锚 `ylpattern.msNestTask.v1` 附通道标记(kind+base),恢复轮询走原通道
  2. 状态机 2s/15s 双档轮询、409/404 幂等容错**零改动复用**;直连任务轮询连续网络失败(本地 MS 中途死)→ error 态,引导「重启本地 MS 后恢复(锚点在,MS 重启后 marker 在 → orphan 恢复)/ 转服务器重跑」,**不自动切换**
  3. `NestSolveModal.tsx` 通道指示:「本地排料(直连)」/「服务器排料(回退)」;回退触发时提示「未检测到本地 VB超排,已使用服务器排料(性能受限);启动本地 VB超排可获得更快速度」
  4. 「下载 PLT」「下载状态文件(.msn)」随通道自动切换(走 US-002 分派,弹窗层零特殊逻辑)
  5. 单测更新(`useNestSolve.test.ts`/`NestSolveModal.test.tsx` 既有先例);`npm run test` 全绿
- **Priority**: 3(依赖 US-002)

### US-004: 回传存档(YL 后端 archive 端点 + 前端自动回传)
- **Description**: As a 生产管理者, I want 排料结果(PLT/.msn/摘要)统一存档到 YL 服务器 so that 排料历史可追溯、版师可随时取 .msn 续调,且不依赖 MS 侧 7 天 run_dir 清理窗口。
- **Acceptance Criteria**:
  1. YL 后端新增 `POST /api/nest/tasks/{task_id}/archive`:multipart `file_plt`(PLT 文本)+ `file_msn`(.msn gzip)+ `meta`(JSON 字符串:task_id/通道标记/density/width_mm/码套/seed/run_mode/时间)→ 落盘 `out/nest_archive/<task_id>/`(env `YLP_NEST_ARCHIVE_DIR` 覆盖;meta 索引行追加 `out/nest_archive/index.jsonl`)
  2. 形态参照 agent 服务 UploadFile multipart 先例(agent/app.py:42-50);幂等(同 task_id 重传覆盖同路径);文件大小上限与既有上传约定一致
  3. **鉴权按 YL 现状不新增**(app.py:455 注释先例);YL 上服务器整体鉴权层为 YL 独立课题,超本 PRD 范围
  4. 前端 NestSolveModal done 终态后自动回传(PLT blob + .msn blob + meta),失败可手动重试、**不阻塞结果展示与下载**;回传状态小字指示
  5. 测试:pytest(test_nest_api.py 先例)+ 前端单测;`npm run test` 与 `pytest tests/` 全绿
- **Priority**: 4(依赖 US-003;与后端无 US-001 依赖可并行开发)

### US-005: 双通道冒烟与文档翻案
- **Description**: As a YL 维护者, I want 冒烟脚本覆盖双通道 + 回传、文档反映新架构 so that 回归有自动化护栏且架构认知不漂移。
- **Acceptance Criteria**:
  1. `webapp/frontend/scripts/smoke_ms_nest.mjs` 扩展:直连通道全链(mock 本地 MS)/ 回退通道全链(无本地 MS)/ done 自动回传落盘断言;`package.json` script 保持 `smoke:ms-nest`
  2. `tasks/prd-ms-nesting-integration.md:105`「前端永不直连 MS」设计决策翻案补记(指向本 PRD);`.doc/python工程设计.md` §10.3.2 更新双通道拓扑与部署口径
  3. 服务器 MS 部署口径文档化:pip 装 `ms-web`(恒绑 127.0.0.1 与 YL 后端同机)+ env `YLP_MS_TOKEN` ↔ `MS_MACHINE_TOKEN` 同值;运维步骤清单
  4. `npm run test` + `pytest tests/` + `smoke:ms-nest` 全绿
- **Priority**: 5(收尾;联调验收依赖 MS 仓 PRD 落地)

## 功能需求 (Functional Requirements)

- FR-1: 排料发起时通道探测:本地 MS ping(8010..8019)命中 → 直连;全败 → `/ms` 代理;`VITE_MS_BASE` 显式覆盖优先
- FR-2: 通道绑定任务生命周期:task_id 与通道一起入 localStorage 锚,恢复轮询走原通道;不自动切换通道
- FR-3: 直连通道任务中断 → error 态引导重启恢复或手动转服务器;不自动重跑
- FR-4: `.msn` 下载双通道分派(直连无 token / 代理 token 注入)
- FR-5: 任务终态后前端自动回传 PLT + .msn + meta 到 `POST /api/nest/tasks/{task_id}/archive`,落盘 `out/nest_archive/`
- FR-6: 通道指示与回退提示在排料弹窗明示
- FR-7: 现有 `/ms` 代理链路(ms_forward/nest_state_file/YLP_MS_BASE/YLP_MS_TOKEN/Vite proxy/test_ms_proxy.py)**零删除零改动**

## 非目标 (Non-Goals)

- 不做 MS 仓改动(CORS/PNA/ping 在 MS 仓 PRD)
- 不做排料历史列表/下载 UI(存档落盘即最小闭环,消费面后续立项)
- 不做服务器通道「后端直拉结果不绕浏览器」优化(前端回传统一口径,后续可选)
- 不做 YL 用户体系/鉴权(独立课题)
- 不做 MS 工作台嵌入 YL(三期 .msn → 版师手工「状态恢复」动线不变)

## 设计考虑 (Design Considerations)

- 通道选择只在「发起排料」时执行一次;弹窗内轮询期间不重复探测(本地 MS 启停不影响进行中任务判定)
- 回退通道是**现状零改动**( `/ms` 前缀 + httpx 转发服务器 loopback)——它同时是 MS 侧改动未部署时的安全垫
- 直连通道跨源请求必触发预检(PNA + 可选 token 头);MS 侧白名单未含当前 YL 源时请求层应把「预检失败」归一为回退(US-002 AC#4),避免用户卡死在半新半旧部署
- 排料是 CPU 密集任务,服务器多用户并发走回退通道时性能互相挤压——UI 明示通道是必要的产品诚实

## 技术考虑 (Technical Considerations)

- 直连地址恒 `127.0.0.1` 字面量(IPv4 loopback + mixed content 双重约束)
- ping 探测的 AbortSignal 超时要短(~300ms × 10 并发,总探测墙钟 <1s,不拖慢发起)
- YL 前端以 HTTPS 部署时直连属 public→local 请求(PNA),Edge/Chrome 预检由 MS 侧响应;Firefox/Safari 行为差异在联调验收覆盖
- `out/nest_archive/` 增长无自动清理(排料产物 KB~MB 级,量级低);清理策略后续按需
- YL 后端 CORS(`allow_origins` 现仅 dev localhost:5173)与本 PRD 无关(直连目标是 MS 不是 YL 后端,回传走同源)

## 成功指标 (Success Metrics)

- [ ] 本地 MS 在跑:YL 页面发起排料 → 直连通道全链跑通,弹窗示「本地排料(直连)」
- [ ] 本地 MS 关闭:同页面发起 → 自动回退代理通道跑通,弹窗示「服务器排料(回退)」+ 提示
- [ ] 两通道 done 后 `out/nest_archive/<task_id>/` 均落盘 PLT + .msn + meta,index.jsonl 追加正确
- [ ] 直连任务中途杀本地 MS → error 引导;重启 MS 后凭锚点恢复任务状态
- [ ] `npm run test` + `pytest tests/` + `smoke:ms-nest` 全绿;现有 `/ms` 代理测试(test_ms_proxy.py)零改动通过

## 待确认问题 (Open Questions)

- 服务器 MS 部署时间点与运维责任人(US-005 只交口径文档,部署本身是运维步骤)
- YL 生产域名确定后需同步 MS 仓 sidecar(两仓联动项,见 MS 仓 PRD 待确认)
- 回传存档是否需要按「款号/订单」维度组织目录(当前按 task_id 平铺;若有业务诉求后续调 meta 索引即可)
