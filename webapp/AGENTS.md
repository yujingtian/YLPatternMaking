# webapp 前端浏览器验证套路（2026-09-21 US-004 实战沉淀）

Playwright 活体验证（MaterialSorting 侧装了 playwright，跨仓借用）：

```js
import { createRequire } from 'node:module'
const { chromium } = createRequire(
  'D:/code/MaterialSorting/materialSorting-web/package.json')('playwright')
const browser = await chromium.launch({ channel: 'chrome', headless: true })
```

- 启动：自带 Vite dev（`npx vite --port 5175 --strictPort`，勿走 `npm run dev`
  ——predev 的 `python` 在本机是 Store 假 alias，须 PATH 前置真 3.11：
  `C:/Users/ASUS/AppData/Local/Programs/Python/Python311`）；`/api`→:8000、
  `/ms`→:8010 由 vite.config.ts 代理（后端/MS 由环境常驻，勿杀）。
- 本机 Playwright 构建的坑（US-007 冒烟会再踩）：
  1. `button:text-is("中文")` 与 `getByRole('button', {name, exact})` 均匹配
     不上纯文本按钮（可达名与文本不一致）；用 `getByText(name, {exact:true})`。
  2. antd 自动给两字按钮插空格：`关闭`→`关 闭`、`重试`→`重 试`（带图标或
     四字按钮不受影响）。
  3. 可见弹窗过滤用 `.ant-modal-wrap:visible`（Playwright locator 支持
     `:visible`；page.evaluate 里不行——antd 关闭态 modal 留 DOM，wrap 是
     position:fixed，offsetParent 恒 null，用 `getComputedStyle(w).display !== 'none'` 判）。
- MS 排料活体链路已打通（US-004）：solve→status 轮询→终止 stopped→result
  取果→DELETE 全部真实往返过（81.57% / 51 片 / DELETE 200）。
- M2 布局一致性参考图（US-005）：同 task 的 best 布局走 MS 自己的 render_png
  管线出 PNG（`load_pieces(run_dir/pieces_intermediate.json)` →
  `placed_to_world` → `render_png`，run_dir 取
  `out/config_runs/machine_*` 最新——machine result 载荷**不带 run_dir**），
  与 YL 截图 PIL 拼图并排目检；几何字节级则直接比对 polygon points 与
  MS 公式（pointsStr r2 同式）。端口坑：5173 常被 MaterialSorting-web 的
  陈年 Vite 占用且页面长得很像——起服务后先 `cat` vite 日志确认实际端口。

