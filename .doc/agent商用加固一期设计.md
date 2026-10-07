# agent 商用加固一期设计（试点期）

> 2026-10-07 立项。背景：产品未推广、前期预计个位数用户。一期筛选标准（商用化讨论拍板）：
> **只做与并发量无关的事**——单点可靠性（重试）、成本可见性（usage 落账）、数据复利
> （确认 diff、会话持久化）；并发/扩展类（多供应商、semaphore、async 化、任务化 SSE、
> 多租户）全部缓做，触发条件见文末非目标表。
>
> 文档定位：设计冻结，各项**相互独立、可单独实施**。落地后把现行口径同步进
> [python工程设计.md](python工程设计.md) §10.9，并在本文对应章节标记「已实施」。
> 规格只写现行设计与决策理由，讨论过程不重复。

## 范围总览

| 项 | 内容 | 状态 | 改动量 |
|---|---|---|---|
| A | 共享 token 鉴权 | **已实施 2026-10-07，默认关** | 已落（app.py + 4 测试） |
| B | VLM usage 落账 | **已实施 2026-10-07** | 已落（provider + 4 调用点 purpose + CLI 开关） |
| C | VLM 瞬时错误重试 | **已实施 2026-10-07** | 已落（provider，默认 retries=1） |
| D | 确认 diff 落盘（数据飞轮） | **后缓**（2026-10-07 用户拍板：不影响现功能） | 前后端各一小块 |
| E | 会话前端持久化 | **后缓**（同上） | 前端 ~60 行 |
| F | healthz async 化 | **已实施 2026-10-07** | 已落 |

一期收口：A/B/C/F 全部落地（agent 相关 280 测试全绿）；D/E 设计保留在本文备查，
用户拍板后续再做（不阻塞现有功能：D 缺失只是丢纠错信号、E 缺失刷新后重走识别，
均为成本/数据损耗非功能故障）。

---

## A. 共享 token 鉴权（已实施，默认关闭）

**威胁模型**：agent 服务（8001 端口）原本零鉴权——公网部署时任何人可直接
`POST /api/chat/turn` 用我们的 VLM key 免费跑图。互联网扫描器专门找开放端口的服务，
不需要被针对性攻击，撞见即白嫖。

**设计**（已落码 [agent/app.py](../agent/app.py) `_require_token`）：

- 环境变量 `YLP_AGENT_TOKEN`：**未设置/为空 = 鉴权关闭（开发模式，默认）**；设置后
  `/api/extract`、`/api/chat/turn` 两个 POST 端点要求 `Authorization: Bearer <token>`，
  缺失/不匹配 → 401。
- `hmac.compare_digest` 比对（防时序侧信道），**bytes 形式**（str 形式遇非 ASCII
  header 会炸 TypeError → 500）。
- **healthz 刻意豁免**：监控/LB 探活无秘密可泄，且探活不该被业务鉴权卡死。
- 每请求读 env（非启动快照）：测试 monkeypatch 即可切换，代价可忽略。

**启用 runbook**（公网部署试点用户时）：

1. agent 服务环境设 `YLP_AGENT_TOKEN=<随机串>`（systemd/docker inject；生成：
   `python -c "import secrets; print('ylp_'+secrets.token_urlsafe(24))"`）。
2. **webapp 转发补一行**：[webapp/backend/app.py](../webapp/backend/app.py) `agent_forward`
   现只透传 `content-type` 头——补 `authorization` 透传，否则 prod 链路（浏览器 →
   webapp:8000 → agent:8001）令牌到不了 agent。Vite dev proxy 默认透传全部头，无需改。
3. 前端：设置项存 localStorage（如 `ylp.agentToken`），agent API 调用层
   （apiHttp.postChatTurn/postExtract）统一附 `Authorization` 头；口令发给试点用户
   手工填一次。UI 形态届时定（设置弹层或 URL `?token=` 首次落地）。
4. **HTTPS 前提**：token 走公网必须加密通道（reverse proxy 挂证书，Caddy/Nginx
   免费证书十分钟），否则明文可被嗅探。

**不防什么**（定位 = 家 WiFi 密码）：口令泄露全员更换、无身份区分（不知道是谁干的）、
前端可见（devtools 能看到）。对外推广时换正经每用户账号体系，届时整套可扔不用迁移。

**测试**（tests/test_agent_api.py 已落 4 例）：设 token 后无头/错头/非 Bearer 前缀
→ 401、healthz 豁免 200、正确 Bearer 放行 200、chat 端点同门控、未设 env 无头照常
200（默认关闭回归）。

---

## B. VLM usage 落账（已实施 2026-10-07）

**现状**：`provider._read_sse` 把 SSE 流里的 usage 信息（prompt/completion tokens）
直接丢弃——单轮烧多少 token 完全无感知。试点期这是自己的钱，也是未来定价、
「S2 要不要换大模型」决策的唯一数据源。

**设计**：

- `_read_sse` 解析每个 data chunk 的 `usage` 键（容错：**任意 chunk 出现即记录**，
  不预设位置——各供应商有的放最后 data chunk、有的要 `stream_options.include_usage`，
  解析不到就空 dict，不报错）。
- `OpenAICompatibleVLM` 暴露 `last_usage: dict | None`（每次 complete 后更新）；
  `complete()` 返回值保持 `str` 不变（鸭子协议零破坏）。
- 日志：`logging.getLogger("ylagent.usage")` 每次调用输出一行 JSON：
  `{ts, model, purpose, prompt_tokens, completion_tokens, duration_s, n_images}`。
  CLI/uvicorn 各自配 handler；试点期人工 `grep` / python 一行聚合，不建监控设施。
- **purpose 标注**：`complete(..., purpose="")` 可选参（默认空串），管线调用处
  （S1 补漏 / S2 视觉 / 调版映射 / 聚焦复查）各自传——这是区分「哪些调用贵」的关键。
  FakeVLM 同步加参（鸭子协议演进，测试里的 calls 记录顺带可断言 purpose）。

**测试**：FakeVLM 不走真 HTTP——造 fake `urllib.request.urlopen` 返回手工拼的 SSE
字节流（含 `data: {..., "usage": {...}}` 行），断言 `last_usage` 字段与日志行内容；
usage 缺失时 `last_usage` 为空 dict 不炸。

---

## C. VLM 瞬时错误重试（已实施 2026-10-07）

**动机**：上游随机 5xx/429 一次 → 整轮 503，试点用户第一次用就碰上是最伤印象的事。
VLM 调用无状态，重试安全（代价只是钱，一次封顶）。

**设计**（全部收在 `OpenAICompatibleVLM.complete`，管线层零感知）：

- **重试范围**：HTTP 429、HTTP 5xx、连接超时（urlopen 阶段）。
- **不重试**：HTTP 400/401/403/404（请求本身错，重试无意义——400 摘参重发走既有
  `_ThinkingRejected` 通道，先于重试判断、层次不冲突）；`finish_reason=length`
  （VLMError 原样抛，重试只会再掐一次）。
- **SSE 中途空闲超时不自动重试**：已烧部分 token，重试整单重付——交上层 503，
  试点期人工看日志判断（有了 B 项的 usage 日志才有判断依据，故 B 先做）。
- **次数 1、退避**：429 且响应带 `Retry-After` → `min(parsed, 10s)`；否则固定 2s。
- **配置**：`VLMConfig` 加 `retries: int = 1`（0 = 关闭，vlm.toml 可配）。

**测试**：monkeypatch `urllib.request.urlopen`——第一次抛 `HTTPError(429)`、第二次
返正常 SSE 流 → 断言恰好两次调用 + 结果正确；`HTTPError(400)`（不带 thinking 参时）
不重试直接抛；retries=0 时不重试。

---

## D. 确认 diff 落盘（数据飞轮）

**动机**：「确认并进入工作台」时用户把交卷值**改成了什么**是最高价值的监督信号，
现在前端 prefill 完即丢弃。精度升级路线第 1 步（攒金标集）就卡在这——试点用户 =
第一批标注员，扔一天少一天。

**采集点**（前端）：

1. `SmartDraftView` 确认时（onConfirm）：快照本次 delivery 的 `{measurements,
   options}` 存入 store（键 = 本次 draftEpoch），随换源收口走。
2. 工作台侧：下次「生成 / 导出」动作时，比对当前 store 值 vs 快照，diff 非空则
   一次性上报（**幂等键 = draftEpoch**，同 epoch 只报首次非空 diff，防止每次生成
   重复上报）。

**后端**（agent 服务，不动 webapp 薄壳不落盘口径）：

- 新端点 `POST /api/feedback/diff`（同挂 `_require_token` 依赖）。
- 追加写 JSONL：路径 = 环境变量 `YLP_AGENT_DIFF_LOG`（默认
  `agent_data/confirm_diff.jsonl`，相对仓库根；目录自动建，**进 .gitignore**）。
- 行格式（隐私最小化——只落 diff 键与双值，不落全量、照片永不落盘）：
  `{ts, turn, model, photo_count, diff: [{key, delivered, confirmed}]}`。

**边界与口径**：确认后弃用 = 无信号（接受）；改了又改回 = 最终态无 diff（接受，
过程信号不值钱）；上报失败 console.warn 静默——飞轮绝不打断工作流。

**测试**：后端端点 JSONL 追加行为 + token 门控（同 A 测试形态）；前端 diff 计算
收纯函数（建议放 chatPayload.ts 旁或独立 util）配 vitest 金标。

---

## E. 会话前端持久化

**动机**：会话 JSON 只在 App 内存态（useSmartDraft，文档标注「跨启动 localStorage
持久化留后续」）——分钟级轮次中手滑刷新 = 会话 + vlm_cache 全丢 → 照片全部重新
识别**重新计费**。用户越少，单个用户事故的损失占比越大。

**设计（v1 范围收窄）**：

- localStorage 键 `ylp.smartdraft.session`：存 session JSON 串（含 vlm_cache）+
  thinking 态。挂载时恢复、每次 send 成功后写。
- **照片 blob 不持久**（objectURL 刷新即失效；File 对象落 IndexedDB 留二期）：
  损失面 = 复查 directive 待办时刷新，需用户重传该类别照片——现有降级路径
  （按类别求援卡 catch-up）已兜底，不产生新分支。
- **版本字段**：序列化带 `schema_version`，读侧不认识即整体丢弃重建（防未来格式
  漂移炸 parse；session.py 的 C5 旧格式迁移是后端侧先例，前端同思路）。
- 容量观察项：事件流 append-only 会长大，试点期会话普遍短，暂不做截断；
  序列化超 ~256KB 再引入「保留最近 N 轮」策略（届时定，勿提前做）。
- 出口同步清空：现有「重新开始」/「返回」清会话的路径同时清 localStorage。

**测试**：vitest——恢复、清空、版本不认识丢弃重建三个用例。

---

## F. healthz async 化（已实施 2026-10-07）

1 行：`def healthz` → `async def healthz`（`VLMConfig.load` 是磁盘读 toml，毫秒级、
async 里可接受）。动机：探活不进 sync threadpool、不被分钟级轮次拖死——「40 线程
耗尽连坐 healthz」场景唯一的一行解，与并发改造解耦。现有 test_healthz 不动即过。

---

## 非目标（缓做清单与触发条件）

| 事项 | 触发条件 |
|---|---|
| 多供应商故障转移、配额告警体系 | 签企业协议 / 单 key 限流频发 |
| VLM 并发 semaphore、httpx async 化、任务化 + SSE 实时进度 | 并发用户 > 10 / 代理层 504 出现 |
| webapp 侧鉴权（token 目前只护 agent） | 对外推广 |
| 上传 magic bytes 校验、隐私合规披露、多租户 | 收费 / 对外推广 |

并发模型现状备忘（本期不动）：app.py 全部 sync def → AnyIO 默认 40 线程池共享，
单轮占线分钟级；40+ 并发 → 第 41 个请求静默排队、代理超时 504、healthz 连坐、
用户重发双倍计费。症状是「静默挂起」而非崩溃，监控上只见延迟飙高。
