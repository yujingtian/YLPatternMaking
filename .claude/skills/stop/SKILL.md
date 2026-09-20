---
name: stop
description: 停止 YLPatternMaking 运行中的服务：后端 uvicorn（:8000 或 :8010）与/或 前端 Vite dev（:5173）。按端口现探 PID 并验证身份（标题含 YLPattern）后才 taskkill，绝不误杀端口上其他项目的进程。
allowed-tools: Bash
---

# Stop Skill

## 上下文
- 后端监听 :8000（默认）或 :8010（8000 被外部占用时的回落口）；前端 dev 监听 :5173（Vite，可能顺延到 5174+）。
- **prod 模式无独立前端进程**（dist 由后端同源 serve），停后端即等于全停；停 all 时 :5173 显示「未运行」属正常。
- 服务可能由 `/start` 后台起，也可能由用户外部起；**一律按端口现探 PID**，不依赖上次记忆的 PID（skill 无状态）。
- **端口 ≠ 归属**：本机 8000 常被其他项目（排料可视化工作台）占用。杀之前必须做身份验证——本项目任何前端入口（dist 或 Vite dev）的 HTML 标题固定含 `YLPattern`。

## 端口 → PID 探测与身份验证（Windows Git Bash）
```bash
# 监听 <PORT> 的 PID（IPv4/IPv6 都命中；可能多行或空）
netstat -ano | grep -E ":<PORT>[[:space:]]" | grep -i LISTENING | awk '{print $NF}' | sort -u
# 身份验证：标题含 YLPattern 才是本项目（8010 若回落口也如此）
curl -s --max-time 3 http://127.0.0.1:<PORT>/ | grep -q YLPattern && echo OURS || echo NOT_OURS
```

## 解析意图（从用户消息 / args）
- 目标端：`backend` / `frontend` / `all`（默认 `all`）
- backend → 候选端口 {8000, 8010}（两个都探，谁 OURS 杀谁）；frontend → 候选 {5173, 5174}（Vite 顺延口，依次探测）

## 执行步骤
1. 对每个候选端口：探测 LISTENING → 没监听则记「未运行」跳过；有监听则先验身份：
   - `NOT_OURS` → **不动**，记「端口被外部进程占用（PID ...），未处理」；
   - `OURS` → 杀进程树（覆盖 `npm run dev` → vite 父子）：
     ```bash
     # 以 backend :8010 为例；其他端口替换端口号即可
     pids=$(netstat -ano | grep -E ":8010[[:space:]]" | grep -i LISTENING | awk '{print $NF}' | sort -u)
     if [ -n "$pids" ]; then
       for pid in $pids; do MSYS_NO_PATHCONV=1 taskkill //PID $pid //F //T 2>/dev/null && echo "killed $pid"; done
     else
       echo "(后端未运行)"
     fi
     ```
2. 复探端口确认无 LISTENING 残留（只复查身份 OURS 的口）：
   ```bash
   netstat -ano | grep -E ":8010[[:space:]]" | grep -qi LISTENING && echo "STILL_UP" || echo "CLEAN"
   ```
   `STILL_UP` → 再 kill 一次；仍杀不掉就照实报权限错误。
3. 汇报：
   ```
   🛑 已停止
     后端  :8010   killed PID ...      （或：未运行 / :8000 被外部进程占用未动）
     前端  :5173   killed PID ...      （或：未运行）
   ```

## 何时自动触发（Claude 自调用，无需用户输入）
- 后台求解/仿真任务占着端口需要释放时。
- 配合 `/start restart`：restart 的「停」这一半复用本 skill 逻辑（实际由 start skill 内联执行，不必先调本 skill 再调 start）。

## 注意事项
- **身份验证是硬闸**：NOT_OURS 的端口一律不碰、如实报告。绝不按端口号盲杀。
- **`MSYS_NO_PATHCONV=1` + `//PID //F //T`**：Git Bash 会把 `/PID` 当 POSIX 路径吞掉导致参数丢失，必须双斜杠 `//PID` 或前置该 env。`//F` 强制结束、`//T` 连子进程一起杀。
- 杀不掉（权限不足 / PID 已退出）时 `taskkill` 会报错，**照实报给用户**，不要假装成功。
- 杀完后端后若 Claude 会话里还有对应的后台 Bash 任务（/start 起的），任务会以非零码退出，属预期，不算故障。
