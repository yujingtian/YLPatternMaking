# PRD: YL 侧 .msn 状态文件下载入口（机器对接三期 · YLPatternMaking 侧对接规格）

> 配套 PRD：MS 侧生成端点见 `tasks/prd-machine-state-file.md`（本仓 MaterialSorting）。本文为 **YL 团队对接需求规格**，可复制至 `D:\code\YLPatternMaking\tasks\` 由其 Ralph 消费（先例 `prd-ms-nesting-integration.md`）。
> 定位：YL 侧为**纯搬运工** —— .msn 对 YL 是不透明字节流，不解析、不感知 schema 升级；实现模式 = 克隆 YL 已为 PLT 导出（MS `/api/machine/export`）建立的「按钮 + 透传代理」通道。

## 概述 (Overview)

YL 任务结果页新增「下载状态文件(.msn)」入口：用户点击后，YL 后端凭 `task_id` 调 MS `GET /api/machine/solve/{task_id}/state-file` 取 gzip 附件并原样转发给浏览器。用户把文件交给版师，在 MS 排料工作台「状态恢复」上传后即可基于该机器任务继续人工调整（编辑布局 / 智能微调 / 改数量重解 / 导出 PNG·DXF·PLT）。

## 目标 (Goals)

- YL 用户在熟悉的任务结果页一步拿到 .msn 文件，无需知道 MS 系统、task_id 或任何技术细节
- YL 后端零业务逻辑：透传 MS 响应（字节流 + Content-Type + Content-Disposition），错误码映射为中文提示
- 与既有 PLT 导出下载通道完全同构，YL 侧边际成本 ≈ 一个按钮 + 一个 relay 端点

## 用户故事 (User Stories)

### US-001: 后端透传代理端点
- **Description**: As a YL 用户, I want 点击「下载状态文件」拿到 .msn 文件, so that 交付版师在 MS 排料系统继续调整。YL 后端新增代理端点（路由命名随 YL 既有任务路由风格，如 `GET /api/nest/tasks/{id}/state-file`）。
- **Acceptance Criteria**:
  1. 代理端点服务端调 MS `GET http://<MS>:8010/api/machine/solve/{task_id}/state-file`，请求头带 `X-Machine-Token`（值 = 服务端配置，与 PLT 导出通道同一配置项，**不下发前端**）；task_id 取 YL 任务记录中保存的 MS task_id。
  2. MS 200 → YL 200 原样透传：响应体**流式转发**（不落盘、不解析、不整体读入内存——.msn 典型几百 KB~几 MB gzip），`Content-Type: application/gzip` 与 `Content-Disposition`（含 .msn 文件名）原样透传，保证浏览器落盘文件名/扩展与 MS 侧一致。
  3. 错误映射（MS 结构化 `{"error":...}`）：401 →「排料服务认证失败，请联系管理员」；404 →「任务不存在或已清理」；409 →「任务数据已不可得，请重新提交排料」；其它/超时 →「排料服务暂不可用，请稍后重试」。超时建议 ≥30s（MS 生成秒级，留裕量）。
  4. 鉴权：YL 自身用户会话鉴权照常（该入口仅任务所属用户可见）；MS token 永不出现在前端。
  5. YL 侧测试：代理转发头/流不变形（对拍 MS 原始响应字节）、错误映射三支路、token 不泄露到前端日志。
- **Priority**: 1

### US-002: 前端下载入口 + 引导文案
- **Description**: As a YL 用户, I want 在任务结果页看到下载入口并理解文件用途, so that 顺利完成「机器排料 → 人工精调」的交接。
- **Acceptance Criteria**:
  1. 任务详情/结果页展示「下载状态文件(.msn)」按钮；可见性 = 任务存在即可（running 期可点，文案标注「当前最优快照」；error 态可点，文案「无求解结果，仅含配置」；done/stopped 主推）。
  2. 下载走浏览器原生附件下载（GET 链接 / 表单提交），前端不解析文件内容。
  3. 引导文案一处（按钮旁 tooltip 或说明行）：「下载后可在排料系统(MS)『状态恢复』中打开，继续调整布局、微调、改数量重解或导出图纸」，附 MS 工作台入口链接（版师日常访问地址）。
  4. 按钮状态与后端错误提示联动（US-001 映射文案原样展示，不重写）。
- **Priority**: 2（依赖 US-001）

## 功能需求 (Functional Requirements)

- FR-1: 透传代理：MS 响应字节流 + `Content-Type` + `Content-Disposition` 原样转发；不缓存解析、不改名。
- FR-2: MS token 服务端持有（复用 PLT 导出通道配置），前端零接触。
- FR-3: 错误码映射为中文用户提示（401/404/409/超时四支路）。
- FR-4: 按钮可见性恒可点（含 running best-so-far 与 error 纯配置档语义，文案区分）。
- FR-5: 引导文案说明 .msn 用途与 MS 工作台恢复路径。

## 非目标 (Non-Goals)

- YL 解析 / 预览 / 校验 .msn 内容（不透明字节流；MS 侧 schema 升级 YL 零感知）
- 在 YL 内嵌或 iframe MS 工作台
- YL 侧任何布局编辑能力（人工调整全部发生在 MS 工作台）
- MS 侧任何改动（见配套 MS PRD）

## 设计考虑 (Design Considerations)

- 用户动线：YL 下载 .msn → 交付版师 → MS 工作台「状态恢复」上传 → 预览/数量矩阵/最优布局全量还原 → 编辑、微调、重解、导出。文件是两系统间唯一载体，走人不走接口。
- 按钮放任务结果页（PLT 导出入口同区域），保持「一个任务一个取件区」的心智。

## 技术考虑 (Technical Considerations)

- 复用 US-004 PLT 导出已建的下载通道模式（代理 + token 配置 + 流式转发），差异仅 URL 与文案。
- MS 侧生成端点为只读幂等 GET，重复点击无副作用；下载不改变任务状态、不消耗配额。
- MS 生命周期约束透传给用户提示：任务被清理（7 天 / DELETE）后 404，文案已覆盖「请重新提交」。

## 成功指标 (Success Metrics)

- [ ] 端到端：YL 提交 normal 档任务 → 终态 → 下载 .msn → MS 工作台恢复成功，画布布局与 YL 结果页一致（密度数值相同）
- [ ] 下载文件与 curl 直连 MS 端点产物逐字节一致（代理不变形）
- [ ] MS token 不出现在任何前端可达面（网络面板/日志/构建产物）

## 待确认问题 (Open Questions)

- YL 侧路由命名与按钮具体摆放位置（YL 团队按自家路由风格定，本文不强约）。
