// 机器排料（MS 对接二期 §10.3.2）端到端冒烟（playwright，手动脚本不入
// vitest）——US-007：主链路 + 四异常分支回归锁。
//
// **自举起服**（无需手工起 YL 后端）：spawn py -m uvicorn 起两份 webapp
// backend——A :8040（缺省 YLP_MS_BASE → 真 MS :8010，prod 形态：托管 dist +
// /ms httpx 转发，连 US-001 代理通道一起回归）与 B :8041（YLP_MS_BASE 指向
// 死端口 = 502 夹具）。MS :8010 由环境常驻（**本脚本不 spawn 不杀**，起跑前
// 探针不在则退出 2）。脚本退出树杀两份 uvicorn（taskkill /T）。
//
// 前置：webapp/frontend/dist/ 为 npm run build 产物（backend GET / 直接托管）；
//       MS :8010 在跑；playwright 可解析（本仓 devDependencies 未装——先试
//       import('playwright')，回落 createRequire(SMOKE_PLAYWRIGHT_FROM 指定的
//       package.json，缺省 MaterialSorting-web，跨仓借用先例见 webapp/AGENTS.md）。
// 命令：cd webapp/frontend && node scripts/smoke_ms_nest.mjs  （或 npm run smoke:ms-nest）
//
// 相位总览：
//   [M 主链路] 空白默认基样载入（参数来源，代替上传）→ 工作台挂载（整版按需
//      生成）→ 单码拦截（message 提示不开弹窗、不发 POST，2026-09-22 入口
//      收口）→ 配推板码表 29/30/31 → 排料（POST /api/nest 直达参数弹窗，
//      清单数据走 console.table）→ 参数弹窗（time 短档夹具 = 普通运行
//      180s，config 不接受 time 键、三档预算 MS 侧烘焙，冒烟不空等自然完成
//      而是走终止）→ 开始排料 → 轮询进度（status 请求 ≥2 次 + 利用率物理
//      口径）。
//   [W 误关防护] ESC / 遮罩点击均不关（maskClosable/keyboard 全程禁）→ 进度期
//      显式关窗转后台守望（「排料」按钮转「排料中」态）→ 点击重开在视 →
//      F5 刷新走 localStorage 锚 attach 重连（taskId 不变）。
//   [T 终止→预览→PLT] 等 incumbent 密度 → 终止 → stopped 摘要（物理口径）→
//      NestPreview 三件套（顶标签与 result 逐字符一致 / DOM 多边形 = placed
//      条数）→ 下载 PLT（请求体仅 {task_id} / filename* 中文真名 / IN; 头 /
//      PU/PD 笔画 / 表格区 max_x 超出唛架 width_mm）→ 结果期关闭先 confirm
//      二次确认（关闭即清空告知；取消留场无 DELETE）→ 确认后 best-effort
//      DELETE 200 + 锚清 + 按钮回空闲「排料」。
//   [F 502 分支]（backend B 死链）注入 A 页 localStorage 草稿免重走码表 →
//      开始排料 → /ms 代理 httpx 连接失败 → 502 中文错误 Alert（排料失败）。
//   [C 409 分支]（backend A + 真 MS）context.route 改写 solve multipart 里
//      client_ref 为同长定值（字节替换不动 content-length）→ tab1 提交任务 A
//      在飞 → tab2（清锚 init script 避免 attach）同 ref 二次提交 → 409 错误
//      Alert「已有在飞任务」（含既有 task_id）→ Node 侧 DELETE 任务 A 清场。
//
// 报告落 out/smoke_ms_nest/report.txt；退出码 0 = 全 PASS。
import { writeFileSync, mkdirSync, accessSync, constants, readFileSync } from 'node:fs'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

const HERE = fileURLToPath(new URL('.', import.meta.url))
const ROOT = resolve(HERE, '../../..')            // 仓库根（uvicorn cwd）
const DIST_INDEX = resolve(HERE, '../dist/index.html')
const OUT = ROOT + '/out/smoke_ms_nest'
mkdirSync(OUT, { recursive: true })

const PORT_A = 8040                                // 真 MS 形态（避开常驻 8000）
const PORT_B = 8041                                // 502 夹具
const BASE_A = 'http://127.0.0.1:' + PORT_A
const BASE_B = 'http://127.0.0.1:' + PORT_B
const MS_PROBE = 'http://127.0.0.1:8010/'
const PY = process.env.SMOKE_PY || 'py'
// 409 夹具 client_ref 定值前缀（padEnd 补零保持与原值等长，charset 合法）
const REF_FIX_PREFIX = 'yl-smoke409'

const results = []
function check(name, ok, extra) {
  results.push({ name, ok })
  console.log(ok ? 'PASS' : 'FAIL', name, extra ? '  [' + String(extra).slice(0, 200) + ']' : '')
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const log = (s) => console.log('---', s)

// ---------------------------------------------------------------- 前置检查
try {
  accessSync(DIST_INDEX, constants.R_OK)
} catch {
  console.error('前置缺失：webapp/frontend/dist/index.html 不存在 —— 先 cd webapp/frontend && npm run build')
  process.exit(2)
}
try {
  const ms = await fetch(MS_PROBE, { signal: AbortSignal.timeout(3000) })
  if (!ms.ok) throw new Error('status ' + ms.status)
} catch (e) {
  console.error('前置缺失：MS 排料服务 ' + MS_PROBE + ' 不可达（' + e + '）—— 冒烟走真 MS，请先启动')
  process.exit(2)
}
for (const base of [BASE_A, BASE_B]) {
  try {
    const r = await fetch(base + '/', { signal: AbortSignal.timeout(1000) })
    if (r.ok) {
      console.error('端口 ' + base + ' 已被占用（疑似上次冒烟残留）—— 请先释放再跑')
      process.exit(2)
    }
  } catch { /* 未占用 = 正常 */ }
}
// 502 夹具死端口：从候选里挑一个确实无监听的（防误指到真实服务）
let DEAD_PORT = null
for (const p of [8049, 8059, 8069, 8079]) {
  try {
    const r = await fetch('http://127.0.0.1:' + p + '/', { signal: AbortSignal.timeout(800) })
    if (!r.ok) continue           // 有监听但非 ok 也算被占
  } catch {
    DEAD_PORT = p
    break
  }
}
if (DEAD_PORT === null) {
  console.error('前置缺失：502 夹具死端口候选全被占用（8049/8059/8069/8079）')
  process.exit(2)
}

// ---------------------------------------------------------------- 起服（自举双实例）
function bootBackend(port, extraEnv) {
  const server = spawn(PY, ['-m', 'uvicorn', 'webapp.backend.app:app',
    '--host', '127.0.0.1', '--port', String(port)], {
    cwd: ROOT,
    env: { ...process.env, ...extraEnv },
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  const srv = { server, log: [] }
  server.stdout.on('data', (d) => srv.log.push(String(d)))
  server.stderr.on('data', (d) => srv.log.push(String(d)))
  return srv
}
function killBackend(srv) {
  if (srv.server.exitCode !== null) return
  if (process.platform === 'win32') {
    try { spawn('taskkill', ['/F', '/T', '/PID', String(srv.server.pid)], { windowsHide: true }) } catch { /* 尽力 */ }
  }
  try { srv.server.kill() } catch { /* 尽力 */ }
}
async function waitReady(srv, base) {
  for (let i = 0; i < 60; i++) {
    if (srv.server.exitCode !== null) return false
    try {
      const r = await fetch(base + '/', { signal: AbortSignal.timeout(1000) })
      if (r.ok) return true
    } catch { /* 等下一轮 */ }
    await sleep(1000)
  }
  return false
}
const srvA = bootBackend(PORT_A, {})
const srvB = bootBackend(PORT_B, { YLP_MS_BASE: 'http://127.0.0.1:' + DEAD_PORT })
for (const [srv, base, label] of [[srvA, BASE_A, 'A'], [srvB, BASE_B, 'B']]) {
  if (!(await waitReady(srv, base))) {
    console.error('起服失败（:' + label + ' 未就绪）—— 服务日志尾：\n' + srv.log.join('').slice(-1500))
    killBackend(srvA); killBackend(srvB)
    process.exit(2)
  }
}
log('服务就绪 A=' + BASE_A + '（真 MS :8010）/ B=' + BASE_B + '（死链 :' + DEAD_PORT + ' 502 夹具）')

// ---------------------------------------------------------------- playwright 装载
async function loadChromium() {
  try {
    const pw = await import('playwright')
    return pw.chromium
  } catch { /* 本仓未装：跨仓借用（webapp/AGENTS.md 先例） */ }
  const { createRequire } = await import('node:module')
  const from = process.env.SMOKE_PLAYWRIGHT_FROM
    || 'D:/code/MaterialSorting/materialSorting-web/package.json'
  return createRequire(from)('playwright').chromium
}
const chromium = await loadChromium()
let browser
try {
  browser = await chromium.launch({ channel: 'chrome', headless: true })
} catch {
  browser = await chromium.launch({ channel: 'msedge', headless: true })
}

// ---------------------------------------------------------------- 公共助手
// 可见弹窗定位器（antd 关闭态 modal 留 DOM，须 :visible 过滤；按钮定位用
// getByText exact——本 Playwright 构建 :text-is/getByRole exact 匹配不上 CJK，
// 见 webapp/AGENTS.md）
const visModalOf = (p, text) => p.locator('.ant-modal-wrap:visible', { hasText: text })
const visBtnOf = (p, modalText, name) => visModalOf(p, modalText).getByText(name, { exact: true })
const barBtnOf = (p, name) => p.locator('.action-bar').getByText(name, { exact: true })

// /ms 网络台账（响应码断言用）
function tapMs(p, logArr) {
  p.on('response', (r) => {
    if (r.url().includes('/ms/api/machine/')) {
      logArr.push({ url: r.url(), status: r.status(), method: r.request().method() })
    }
  })
}
async function anchorOf(p) {
  const raw = await p.evaluate(() => localStorage.getItem('ylpattern.msNestTask.v1'))
  return raw === null ? null : JSON.parse(raw)
}
/** 等 incumbent 利用率数字出现（首帧前 nest-density-num 是 --） */
async function waitDensity(p, timeoutMs) {
  const t0 = Date.now()
  for (;;) {
    const t = await p.locator('.nest-density-num').first().textContent()
    if (t && /\d/.test(t)) return t.trim()
    if (Date.now() - t0 > timeoutMs) return null
    await sleep(2000)
  }
}
/** 配推板码表 29/30/31（导出中心 → 推板设置 → 导出推板 DXF 保存信号） */
async function setupSizeRun(p) {
  await barBtnOf(p, '导出').click()
  await visModalOf(p, '导出').waitFor()
  await visBtnOf(p, '导出', '推板设置…').click()
  await p.waitForSelector('.ant-drawer:visible')
  const row0 = p.locator('.sr-table tbody tr').nth(0)
  await row0.locator('button[title="行下插入码"]').click()
  await row0.locator('button[title="行下插入码"]').click()
  await p.locator('.sr-label').nth(0).fill('29')
  await p.locator('.sr-label').nth(1).fill('30')
  await p.locator('.sr-label').nth(2).fill('31')
  await p.locator('.ant-drawer').getByText('导出推板 DXF').click()
  await p.locator('.ant-modal-wrap:visible', { hasText: '3 码 · 基码 29' })
    .waitFor({ timeout: 90_000 })
  await visBtnOf(p, '导出', '关 闭').click()
  await sleep(600)
}
/** 排料 → POST /api/nest → 直达机器排料参数弹窗（返回弹窗定位器；
 *  2026-09-22 入口收口：清单弹窗中转已删，须先配好推板码表） */
async function openSolveModal(p) {
  await barBtnOf(p, '排料').click()
  await visModalOf(p, '机器排料').waitFor({ timeout: 60_000 })
  return visModalOf(p, '机器排料')
}

try {
  const ctxA = await browser.newContext({
    viewport: { width: 1600, height: 1200 }, acceptDownloads: true,
  })
  const pageA = await ctxA.newPage()
  pageA.setDefaultTimeout(30_000)
  const netA = []
  tapMs(pageA, netA)
  // console 清单打印取证（2026-09-22 入口收口：排料数据清单走 console.table
  // 排查通道，捕获 [nest] 前缀行）
  const nestConsoleLogs = []
  pageA.on('console', (msg) => {
    if (msg.text().includes('[nest]')) nestConsoleLogs.push(msg.text())
  })
  // PLT 导出请求体取证（断言请求体仅 {task_id}）
  let exportBody = null
  pageA.on('request', (req) => {
    if (req.url().includes('/ms/api/machine/export')) exportBody = req.postData()
  })

  // ==================== M 主链路：载入 → 生成 → 码表 → 排料 → 发送 → 轮询 ====================
  await pageA.goto(BASE_A)
  // 空白默认（直筒全特征基样）= 参数来源载入（本应用无文件上传，代替「上传」相位）
  await pageA.getByText('开始', { exact: true }).click()
  await pageA.waitForSelector('.app-header')
  check('M1 工作台挂载（基样载入 + 整版按需生成入口就绪）', true)

  // 单码拦截：入口收口回归锁（2026-09-22：清单弹窗删除，拦截前置到点击
  // 时刻——message 提示 + 不开机器排料弹窗）
  await barBtnOf(pageA, '排料').click()
  await pageA.locator('.ant-message-notice',
    { hasText: '机器排料需要推板多码' }).waitFor({ timeout: 3000 })
  const m2NoModal = !(await visModalOf(pageA, '机器排料')
    .isVisible().catch(() => false))
  check('M2 单码拦截：message 提示且不开机器排料弹窗', m2NoModal)
  await sleep(3200)   // 等 message 3s 自动消失，不干扰后续弹窗断言

  await setupSizeRun(pageA)
  check('M3 推板码表 29/30/31 已保存（3 码 · 基码 29）', true)

  const modalM = await openSolveModal(pageA)
  check('M4 排料数据清单已 console 打印（[nest] 产物行，排查通道）',
    nestConsoleLogs.length >= 1
    && nestConsoleLogs.some((t) => t.includes('nest_size_run') || t.includes('.dxf')),
    nestConsoleLogs.join(' | ').slice(0, 120) || '无 [nest] 输出')
  const gateVal = await pageA.locator('.nest-field input').first().inputValue()
  check('M4 幅宽默认 175（cm → gate_mm×10 提交口径）', parseFloat(gateVal) === 175, gateVal)
  check('M4 运行模式默认普通档 = time 短档夹具（180s，config 不接受 time 键）',
    await modalM.getByText('普通运行（180s）').isVisible())

  await visBtnOf(pageA, '机器排料', '开始排料').click()
  await visModalOf(pageA, '机器排料').getByText('当前利用率（物理口径）')
    .waitFor({ timeout: 60_000 })
  check('M5 进度视图出现（利用率物理口径标注）', true)
  const anchor1 = await anchorOf(pageA)
  check('M5 task_id 已存锚（localStorage ylpattern.msNestTask.v1）',
    anchor1 !== null && typeof anchor1.taskId === 'string' && anchor1.taskId.length > 4,
    anchor1 ? anchor1.taskId : 'null')
  const taskId = anchor1.taskId
  await sleep(5000)   // 在视 2s 档攒轮询样本
  const polls = netA.filter((r) => r.method === 'GET'
    && r.url.endsWith('/status') && r.status === 200)
  check('M5 status 轮询进行中（2s 档 ≥2 次，走 /ms 代理通道）', polls.length >= 2,
    'polls=' + polls.length)

  // ==================== W 误关防护：ESC/遮罩不关 + 后台守望 + 刷新重连 ====================
  await pageA.keyboard.press('Escape')
  await sleep(400)
  check('W1 ESC 不关闭（keyboard=false 全程）',
    await visModalOf(pageA, '机器排料').isVisible())
  await pageA.mouse.click(20, 20)
  await sleep(400)
  check('W1 遮罩点击不关闭（maskClosable=false 全程）',
    await visModalOf(pageA, '机器排料').isVisible())
  await visBtnOf(pageA, '机器排料', '关 闭').click()
  await sleep(600)
  check('W2 进度期显式关窗 → 排料按钮转「排料中」态（后台守望）',
    await barBtnOf(pageA, '排料中').isVisible())
  await barBtnOf(pageA, '排料中').click()
  await visModalOf(pageA, '机器排料').getByText('当前利用率（物理口径）').waitFor()
  check('W3 「排料中」点击重开在视进度（15s 慢档提速回 2s）', true)
  await pageA.reload({ waitUntil: 'load' })
  await sleep(1500)
  // 刷新后启动选择层重开：草稿防抖已落盘，「继续上次草稿」恢复参数与码表
  await pageA.getByText('继 续', { exact: true }).click()
  await pageA.waitForSelector('.app-header')
  const anchor2 = await anchorOf(pageA)
  check('W4 刷新后锚仍在且 taskId 不变（attach 重连依据）',
    anchor2 !== null && anchor2.taskId === taskId, anchor2 ? anchor2.taskId : 'null')
  await barBtnOf(pageA, '排料中').click()
  await visModalOf(pageA, '机器排料').getByText('当前利用率（物理口径）')
    .waitFor({ timeout: 30_000 })
  check('W4 刷新后 attach 重连进度视图（首拍轮询自对齐）', true)
  await pageA.screenshot({ path: OUT + '/w_progress_reconnect.png' })

  // ==================== T 终止 → 预览 → PLT 下载 → 结果期关闭回收 ====================
  const density = await waitDensity(pageA, 150_000)
  check('T1 incumbent 利用率出现（物理口径首帧）', density !== null, density ?? '150s 内无帧')
  netA.length = 0
  await visBtnOf(pageA, '机器排料', '终止').click()
  await pageA.locator('.ant-modal-wrap:visible .ant-tag', { hasText: '已终止' })
    .waitFor({ timeout: 30_000 })
  await pageA.locator('.ant-modal-wrap:visible .nest-result-line').waitFor()
  const resultLine = await pageA.locator('.nest-result-line').first().textContent()
  check('T2 终止 → stopped 摘要（取回终止前最优解，物理口径）',
    /利用率 [\d.]+%（物理口径）/.test(resultLine ?? ''), resultLine)
  const stopCalls = netA.filter((r) => r.method === 'POST' && r.url.endsWith('/stop'))
  check('T2 stop 走 /ms 代理（POST .../stop 非 5xx）',
    stopCalls.length === 1 && stopCalls[0].status < 300, JSON.stringify(stopCalls))

  // 预览三件套：顶标签与 MS result 逐字符一致 + DOM 多边形 = placed 条数
  const ms = await pageA.evaluate(async (id) => {
    const r = await fetch('/ms/api/machine/solve/' + id + '/result')
    return r.json()
  }, taskId)
  const expectLabel = (ms.best.density * 100).toFixed(2) + '% · 长度 '
    + (ms.best.width_mm / 10).toFixed(2) + ' cm'
  await pageA.locator('.nest-preview').waitFor({ timeout: 30_000 })
  const labelTxt = (await pageA.locator('.nest-preview-label').textContent()).trim()
  check('T3 预览顶标签与 result 逐字符一致（density/width_mm 同源）',
    labelTxt === expectLabel, labelTxt + ' vs ' + expectLabel)
  const polys = await pageA.locator('.nest-preview-svg polygon').count()
  check('T3 DOM 多边形数 = best.placed_items 条数（demand>1 不去重）',
    polys === ms.best.placed_items.length,
    'dom=' + polys + ' placed=' + ms.best.placed_items.length)
  const infoTxt = (await pageA.locator('.nest-preview-info').textContent()).trim()
  check('T3 信息条物理口径四要素',
    infoTxt.includes('物理口径') && infoTxt.includes('幅宽 175 cm')
    && infoTxt.includes(ms.best.placed_items.length + ' 片'), infoTxt)
  await pageA.screenshot({ path: OUT + '/t_stopped_preview.png' })

  // PLT 下载：请求体仅 {task_id} + 文件名 + HPGL 头 + 表格区在唛架外
  const [dl] = await Promise.all([
    pageA.waitForEvent('download', { timeout: 30_000 }),
    visBtnOf(pageA, '机器排料', '下载 PLT').click(),
  ])
  const fname = dl.suggestedFilename()
  const pltText = readFileSync(await dl.path(), 'utf8')
  check('T4 请求体仅 {task_id}（零格式/表格参数）',
    exportBody === JSON.stringify({ task_id: taskId }), exportBody ?? '未捕获')
  check('T4 文件名 = filename* 中文真名（machine_<task6>_<rand6>_码29-30-31_…毛版.plt）',
    /^machine_[0-9a-z]{6}_[0-9a-z]{6}_码29-30-31_[\d.]+pct_seed\d+_毛版\.plt$/.test(fname), fname)
  const firstLine = pltText.split('\r\n')[0]
  check('T4 首行 HPGL 头 IN;', firstLine.includes('IN;'), firstLine)
  check('T4 PU/PD 笔画在场',
    pltText.includes('PU') && pltText.includes('PD'),
    'PU×' + (pltText.match(/PU/g) || []).length + ' PD×' + (pltText.match(/PD/g) || []).length)
  let maxX = 0
  for (const m of pltText.matchAll(/(?:PU|PD)([-\d.,]+);/g)) {
    const nums = m[1].split(',').map(Number)
    for (let i = 0; i + 1 < nums.length; i += 2)
      if (Number.isFinite(nums[i]) && nums[i] > maxX) maxX = nums[i]
  }
  check('T4 表格区笔画在唛架外（max_x > width_mm + 40 单位）',
    maxX > ms.best.width_mm + 40, 'max_x=' + maxX + ' width_mm=' + ms.best.width_mm)
  await pageA.screenshot({ path: OUT + '/t_plt_downloaded.png' })

  // 结果期显式关闭（2026-09-22 用户口径）：先 confirm 二次确认——「再
  // 看看」取消留场（无 DELETE、结果弹窗不动）；「确定关闭」才回收
  netA.length = 0
  await visBtnOf(pageA, '机器排料', '关 闭').click()
  await pageA.locator('.ant-modal-confirm',
    { hasText: '关闭后排料结果将清空' }).waitFor()
  check('T5 结果期关闭 → confirm 二次确认（关闭即清空告知）', true)
  await pageA.locator('.ant-modal-confirm')
    .getByText('再看看', { exact: true }).click()
  await sleep(800)
  check('T5 confirm 取消 → 留在结果页（无 DELETE 发出、锚仍在）',
    await visModalOf(pageA, '机器排料').isVisible()
    && netA.filter((r) => r.method === 'DELETE').length === 0
    && (await anchorOf(pageA)) !== null)
  await visBtnOf(pageA, '机器排料', '关 闭').click()
  await pageA.locator('.ant-modal-confirm',
    { hasText: '关闭后排料结果将清空' }).waitFor()
  await pageA.locator('.ant-modal-confirm')
    .getByText('确定关闭', { exact: true }).click()
  await sleep(1500)
  const dels = netA.filter((r) => r.method === 'DELETE')
  check('T5 confirm 确认 → DELETE 走 /ms 且回收 200',
    dels.length === 1 && dels[0].status === 200, JSON.stringify(dels))
  check('T5 锚已清除', (await anchorOf(pageA)) === null)
  check('T5 排料按钮回空闲态（文案「排料」，会话已弃）',
    await barBtnOf(pageA, '排料').isVisible()
    && !(await barBtnOf(pageA, '排料中').isVisible().catch(() => false)))

  // ==================== F 502 分支（backend B 死链夹具） ====================
  // 注入 A 页草稿 localStorage（免重走码表；剔除任务锚防 B 页挂载期 attach）
  const lsA = await pageA.evaluate(() => Object.fromEntries(
    Object.entries(localStorage).filter(([k]) => k !== 'ylpattern.msNestTask.v1')))
  const ctxB = await browser.newContext({
    viewport: { width: 1600, height: 1000 }, acceptDownloads: true,
  })
  await ctxB.addInitScript((entries) => {
    for (const [k, v] of Object.entries(entries)) localStorage.setItem(k, v)
  }, lsA)
  const pageB = await ctxB.newPage()
  pageB.setDefaultTimeout(30_000)
  const netB = []
  tapMs(pageB, netB)
  await pageB.goto(BASE_B)
  await pageB.getByText('继 续', { exact: true }).click()
  await pageB.waitForSelector('.app-header')
  await openSolveModal(pageB)
  check('F1 草稿注入生效（B 页码表恢复 → 发送排料可用）', true)
  await visBtnOf(pageB, '机器排料', '开始排料').click()
  await visModalOf(pageB, '机器排料').locator('.ant-alert', { hasText: '排料失败' })
    .waitFor({ timeout: 30_000 })
  const alertTxt = await visModalOf(pageB, '机器排料').locator('.ant-alert').textContent()
  const f502 = netB.filter((r) => r.status === 502)
  check('F2 /ms 代理对死链回 502（YL 后端中文 detail）',
    f502.length >= 1, JSON.stringify(netB))
  check('F2 错误 Alert 透传 502 中文提示（服务未启动/不可达）',
    alertTxt.includes('MS 排料服务未启动或不可达'), (alertTxt || '').slice(0, 120))
  await pageB.screenshot({ path: OUT + '/f_502_alert.png' })
  await visBtnOf(pageB, '机器排料', '关 闭').click()
  await sleep(600)
  check('F2 error 期关闭 = 纯重置（无 DELETE 发出）',
    netB.filter((r) => r.method === 'DELETE').length === 0)
  await ctxB.close()

  // ==================== C 409 分支（同 client_ref 在飞冲突） ====================
  // context.route 改写 solve multipart 的 client_ref 为同长定值（latin1 字节
  // 替换不动 content-length/boundary）；fixRef 开关分相位启停
  let fixRef = false
  await ctxA.route('**/api/machine/solve', async (route) => {
    const req = route.request()
    if (!fixRef || req.method() !== 'POST') {
      await route.continue()
      return
    }
    const buf = req.postDataBuffer()
    if (buf === null) {
      await route.continue()
      return
    }
    const body = buf.toString('latin1').replace(/yl-[0-9a-z]+-[0-9a-z]+/g, (m) =>
      REF_FIX_PREFIX.padEnd(m.length, '0').slice(0, m.length))
    await route.continue({ postData: Buffer.from(body, 'latin1') })
  })
  fixRef = true
  const modalC = await openSolveModal(pageA)
  await visBtnOf(pageA, '机器排料', '开始排料').click()
  await visModalOf(pageA, '机器排料').getByText('当前利用率（物理口径）')
    .waitFor({ timeout: 60_000 })
  const anchorC = await anchorOf(pageA)
  const idC = anchorC.taskId
  check('C1 夹具任务 A 提交在飞（client_ref 已改写为定值）', idC !== taskId, idC)
  await visBtnOf(pageA, '机器排料', '关 闭').click()   // 后台守望：A 不中断
  await sleep(600)

  // tab2 同源新页：清任务锚 init script（否则挂载期 attach 到 A，无参数态可提交）
  const pageC = await ctxA.newPage()
  await pageC.addInitScript(() => {
    localStorage.removeItem('ylpattern.msNestTask.v1')
  })
  pageC.setDefaultTimeout(30_000)
  const netC = []
  tapMs(pageC, netC)
  await pageC.goto(BASE_A)
  await pageC.getByText('继 续', { exact: true }).click()
  await pageC.waitForSelector('.app-header')
  const modalC2 = await openSolveModal(pageC)
  check('C2 tab2 清锚后为参数态（未被挂载期 attach 劫走）',
    await modalC2.locator('.nest-field input').first().isVisible())
  await visBtnOf(pageC, '机器排料', '开始排料').click()
  await visModalOf(pageC, '机器排料').locator('.ant-alert', { hasText: '排料失败' })
    .waitFor({ timeout: 30_000 })
  const alertC = await visModalOf(pageC, '机器排料').locator('.ant-alert').textContent()
  const c409 = netC.filter((r) => r.status === 409)
  check('C3 同 client_ref 二次提交 → MS 409（在飞冲突）',
    c409.length >= 1, JSON.stringify(netC))
  check('C3 错误 Alert「已有在飞任务」且带既有 task_id',
    alertC.includes('已有在飞任务') && alertC.includes(idC), (alertC || '').slice(0, 160))
  await pageC.screenshot({ path: OUT + '/c_409_alert.png' })
  fixRef = false
  await visBtnOf(pageC, '机器排料', '关 闭').click()
  await sleep(600)
  await pageC.close()

  // 清场：Node 侧 DELETE 任务 A（脚本不留在飞任务白烧 CPU）
  const cleanup = await fetch(
    BASE_A + '/ms/api/machine/solve/' + encodeURIComponent(idC), { method: 'DELETE' })
  let cleanupJson = null
  try { cleanupJson = await cleanup.json() } catch { /* 非 JSON */ }
  check('C4 清场 DELETE 任务 A → 200 {ok:true}',
    cleanup.status === 200 && cleanupJson && cleanupJson.ok === true,
    cleanup.status + ' ' + JSON.stringify(cleanupJson))
  await ctxA.close()
} catch (e) {
  check('脚本异常中断', false, String(e && e.stack || e).slice(0, 400))
} finally {
  await browser.close().catch(() => {})
  killBackend(srvA)
  killBackend(srvB)
  await sleep(1000)
}

const pass = results.filter((r) => r.ok).length
writeFileSync(OUT + '/report.txt',
  results.map((r) => (r.ok ? 'PASS' : 'FAIL') + '  ' + r.name).join('\n')
  + '\n' + pass + '/' + results.length + ' passed\n')
console.log('\n' + pass + '/' + results.length + ' passed')
process.exit(pass === results.length ? 0 : 1)
