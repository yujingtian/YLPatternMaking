---
name: start
description: 启动（或重启）YLPatternMaking 牛仔裤打版项目：后端 uvicorn（默认 :8000，被外部进程占用时回落 :8010）+ 前端 Vite dev（:5173）。支持 dev（默认，Vite 跑源码 HMR 热更）/prod（后端 serve 已构建 dist）模式、单端启动、重启。改 Python 后自动触发重启，改引擎源码自动重打引擎 zip。
allowed-tools: Bash
---

# Start / Restart Skill

## 上下文
- 项目根：`d:/code/YLPatternMaking`
- 后端：`py -m uvicorn webapp.backend.app:app`（**必须在仓库根运行**——webapp 是根级顶层包，从子目录起报 `ModuleNotFoundError: webapp`）。路由：`GET /` 出 `webapp/frontend/dist/index.html`、`/api/*`（schema/draft/adjust/dxf/toml/templates）、`/engine/*`（浏览器 Pyodide 本地引擎资产）、`/agent/*`（httpx 转发 8001 提取服务）。**未开 `--reload`**，改 Python 代码后必须重启才生效。
- 端口：默认 **8000**（Vite dev 代理硬编码 `/api → localhost:8000`，见 vite.config.ts）。8000 被非本项目进程占用时回落 **8010**（本机 8000 常被「排料可视化工作台」等其他项目占用——身份验证不过**绝不杀**）。
- Python 解释器：本机无 `python` 命令（WindowsApps stub 报错），用 `py`（3.11）。npm 脚本（predev/prebuild 里的 build:engine）调 `python` → 需 py shim（步骤 0）。
- 依赖：首次或缺 fastapi 时 `py -m pip install -e ".[web]"`。
- 前端 prod：`webapp/frontend/dist` 由后端同源 serve，**无独立前端进程**。dist 缺失（fresh clone 没有 dist）→ 构建链：`cd webapp/frontend && npm install && npm run build`（prebuild 自动跑 build:engine 打引擎 zip + 拷 pyodide 运行时到 public）。
- 前端 dev：`cd webapp/frontend && npm run dev`（Vite :5173，proxy `/api`→:8000、`/agent`→:8001，HMR 热更）。predev 同样跑 build:engine。
- 启动顺序：先起后端。dev 模式前端依赖后端 :8000 在线（代理目标硬编码，后端回落 8010 时 /api 会 502，见步骤 1）。

## 端口 → PID 探测与身份验证（Windows Git Bash）
```bash
# 监听 <PORT> 的 PID（IPv4 127.0.0.1:PORT / IPv6 [::1]:PORT 都命中；可能多行或空）
netstat -ano | grep -E ":<PORT>[[:space:]]" | grep -i LISTENING | awk '{print $NF}' | sort -u
# 身份验证：本项目 index.html 标题固定含 "YLPattern"（prod dist 与 Vite dev 同源）
curl -s --max-time 3 http://127.0.0.1:<PORT>/ | grep -q YLPattern && echo OURS || echo NOT_OURS
```

## 解析意图（从用户消息 / args）
- 目标端：`backend` / `frontend` / `all`（默认 `all`；prod 模式下 frontend 无独立进程，等价 backend）
- 模式：`prod` / `dev`（默认）
- 动作：`start`（默认）/ `restart`（= 先停目标端再起）

## 执行步骤

### 0. 前置检查
```bash
# a) Python 依赖自检（缺则装）
py -c "import fastapi, uvicorn" 2>/dev/null || py -m pip install -e ".[web]"
# b) py shim：本机无 python 命令时，让 npm 脚本里的 build:engine 能跑（幂等）
if ! python --version >/dev/null 2>&1; then
  mkdir -p /tmp/pyshim
  printf '@py %%*\r\n' > /tmp/pyshim/python.bat            # npm 脚本走 cmd 用 .bat
  printf '#!/bin/sh\nexec py "$@"\n' > /tmp/pyshim/python  # bash 直接调用用无扩展名
fi
# c) 前端 node_modules 缺则先 npm install（dev 要起 Vite、prod 要构建，都需要）
cd d:/code/YLPatternMaking/webapp/frontend
test -d node_modules || npm install --no-fund --no-audit
# d) 仅 prod 模式：dist 缺失则构建（dev 由 Vite 直跑源码，不需要 dist）
if [ "$MODE" = prod ] && [ ! -f dist/index.html ]; then
  PATH="/tmp/pyshim:$PATH" npm run build     # 构建失败（tsc 报错）→ 报给用户，不启后端
fi
```

### 1. 探测现状，选端口 / 决定是否先停
```bash
netstat -ano | grep -E ":8000[[:space:]]" | grep -qi LISTENING && echo P8000_UP || echo P8000_DOWN
netstat -ano | grep -E ":5173[[:space:]]" | grep -qi LISTENING && echo P5173_UP || echo P5173_DOWN
```
- 后端端口决策（按序）：
  - 8000 DOWN → 用 **8000**；
  - 8000 UP 且身份 OURS → `start` 报「已在运行」跳过；`restart` 杀掉后仍用 8000；
  - 8000 UP 且身份 NOT_OURS → **不杀**，回落 **8010**（8010 也被占且非本项目则再 +1 顺延，如实报告）。
- **dev 模式警告**：后端不在 8000 时 Vite 代理 `/api` 会 502 → 如实报告冲突，建议用户释放 8000 或改用 prod 模式。
- 动作 = `restart`：目标端中 UP 且 OURS 的全部杀掉再起；`start`（默认）**不杀**，UP 的跳过。

kill 单端口（仅限身份 OURS 的；PORT ∈ {8000, 8010, 5173}）：
```bash
for pid in $(netstat -ano | grep -E ":<PORT>[[:space:]]" | grep -i LISTENING | awk '{print $NF}' | sort -u); do
  MSYS_NO_PATHCONV=1 taskkill //PID $pid //F //T 2>/dev/null && echo "killed $pid"
done
```

### 2. 启动后端（目标含 backend 时）
- 前台阻塞，**必须**用 Bash 工具 `run_in_background: true`，且**必须先 cd 仓库根**：
  ```bash
  cd d:/code/YLPatternMaking && py -m uvicorn webapp.backend.app:app --host 127.0.0.1 --port <PORT>
  ```
- 轮询确认（LISTENING + 接口 200 双条件）：
  ```bash
  for i in $(seq 1 15); do
    netstat -ano | grep -E ":<PORT>[[:space:]]" | grep -q LISTENING && \
    [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:<PORT>/api/schema)" = 200 ] && { echo up; break; }
    sleep 1
  done
  ```
  15s 内没起来 → 读后台任务输出报错（多半：端口占用 / cwd 不在仓库根 / 依赖未装）。

### 3. 启动前端（**仅 dev 模式**且目标含 frontend 时）
- `run_in_background: true` 起：
  ```bash
  cd d:/code/YLPatternMaking/webapp/frontend && PATH="/tmp/pyshim:$PATH" npm run dev
  ```
  （PATH 前置 py shim 是为 predev 的 build:engine；机器上 python 可用时不加也无妨）
- 轮询 :5173 LISTENING。**Vite 未设 strictPort**：5173 被占会自动顺延 5174/5175…，以启动日志里 `Local:` 行的实际端口为准。prod 模式跳过此步。

### 4. 冒烟（推荐）
- `GET /` 标题含 YLPattern；`GET /engine/manifest.json` 200（本地引擎就绪）。
- 引擎链路真打一版：
  ```bash
  curl -s -X POST http://127.0.0.1:<PORT>/api/draft/sheet -H "Content-Type: application/json" \
    -d '{"measurements":{"waist":74,"hip":100,"knee":54,"hem":47,"front_rise":30,"back_rise":40,"outseam":102,"thigh":63.5},"options":{"front_pocket":true,"front_pocket_facing":true}}' \
    -o out/draft_smoke.json -w "%{http_code}\n"
  ```
  返回 200 且 `ok=true` 即全链路通。

### 5. 汇报
```
✅ 项目已启动（dev）
  后端 uvicorn   :8000   http://127.0.0.1:8000/   (PID ...)
  前端 Vite dev  :5173   http://127.0.0.1:5173/   (PID ...)
  打开 → http://127.0.0.1:5173/
```
prod 模式只有后端一行（dist 同源 serve，打开 :8000）。8000 被外部占用回落时要注明原因。PID 用步骤 2/3 起来后复探 netstat 取。

## 何时自动触发（Claude 自调用，无需用户输入）
- 改了后端 Python 代码（webapp/、src/ylpattern/）→ 自动 `/start restart backend` 让改动生效。
- 改了引擎源码（src/ylpattern/）且需浏览器本地 Pyodide 引擎生效 → 先 `cd webapp/frontend && npm run build:engine` 重打 zip（manifest 带 hash，重打后浏览器才拿得到新引擎），再 restart backend。
- 改前端 src/ **不需要**重启（dev 下 Vite HMR 自动热更；prod 下 `npm run build` 后浏览器强刷即可——StaticFiles 从磁盘读，后端无需重启）。仅当改 `vite.config.ts` / 装新依赖后才 `/start restart frontend`。

## 注意事项
- 一律 `run_in_background: true`，**绝不**前台跑 uvicorn / `npm run dev`（会阻塞会话）。
- 后端必须在仓库根 cwd 启动；后台任务里 `cd` 不影响后续命令的会话 cwd。
- 只杀身份验证为 OURS 的进程；8000/8010/5173 上可能是用户其他项目（本机 8000 = 排料可视化工作台）。
- 后台进程随当前 Claude 会话存活（Bash 后台任务）；关掉 Claude 即停。要脱离会话长驻请用户外起。
- 首次启动（fresh clone）dist 不存在：dev 模式不构建也能用（走 Vite :5173）；仅 prod 模式必须走步骤 0d 构建链，否则 `GET /` 只返回「前端未构建」提示文本。
