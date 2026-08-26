// 引擎 worker：Pyodide（wasm 版 CPython）+ 同一份 ylpattern 源码 zip，
// 在后台线程执行打版计算（整版/裁片/拖拽反解），主线程零阻塞。
//
// 启动链：loadPyodide(indexURL=self-host 资产) -> fetch manifest（no-store，
// 内容寻址 zip 名 = 变更检测）-> unpackArchive 解包到 /ylengine ->
// sys.path 指入 -> import engine_glue -> ready。
//
// RPC：主线程发 EngineRequest（带 id），本线程调 engine_glue.handle(cmd,
// payload_json) -> str（JSON 字符串往返，不经 PyProxy，无句柄泄漏），
// 回 EngineResponse。glue 永不 raise；此处对 JSON 解析再做一层兜底。
import type { EngineMessage, EngineRequest } from './protocol'

// 本文件在 DOM lib 下编译（tsconfig 无 webworker lib），postMessage 走薄封装
const post = (msg: EngineMessage): void => {
  (self as unknown as { postMessage(m: EngineMessage): void }).postMessage(msg)
}

interface Glue {
  handle(cmd: string, payloadJson: string): string
}

let glue: Glue | null = null

async function boot(): Promise<void> {
  post({ type: 'progress', phase: 'pyodide', message: '加载 Python 运行时（首次约 10MB，之后走缓存）' })
  const manifest = await fetch('/engine/manifest.json', { cache: 'no-store' }).then(
    (r) => { if (!r.ok) throw new Error(`manifest ${r.status}`); return r.json() as Promise<{ zip: string; rev?: string; pyodide?: string }> },
  )
  if (!manifest.pyodide) throw new Error('Pyodide 运行时未同步（npm install 后重跑 build:engine）')

  const { loadPyodide } = await import('pyodide')
  const py = await loadPyodide({ indexURL: `/pyodide/${manifest.pyodide}/` })

  post({ type: 'progress', phase: 'engine', message: '加载打版引擎', rev: manifest.rev })
  const zip = await fetch(`/engine/${manifest.zip}`).then((r) => {
    if (!r.ok) throw new Error(`engine zip ${r.status}`); return r.arrayBuffer()
  })
  py.unpackArchive(zip, 'zip', { extractDir: '/ylengine' })
  py.runPython("import sys; sys.path.insert(0, '/ylengine')")
  glue = py.pyimport('engine_glue') as unknown as Glue
  post({ type: 'progress', phase: 'ready', rev: manifest.rev })
}

self.addEventListener('message', (ev: MessageEvent<EngineRequest>) => {
  const req = ev.data
  if (!req || typeof req.id !== 'number') return
  void (async () => {
    if (glue === null) {
      post({ type: 'response', id: req.id, ok: false, error: { kind: 'engine', message: '引擎尚未就绪' } })
      return
    }
    try {
      // JSON 字符串往返：与 HTTP 端点同构的结果对象由胶水侧保证。
      // glue 永不 raise——失败也是 {"ok":false,"error":{kind,...}} 信封，
      // 必须拆开按 kind 转错误通道（否则错误信封会被当 SheetResult 返回，
      // 上层 res.warnings.map 直接 TypeError、整版被错误信封顶掉消失）：
      //   validation -> 客户端抛 EngineValidationError（与 HTTP 422 同构，不回退）
      //   engine     -> 客户端抛 EngineFailure（路由层回落 HTTP 再试）
      const out = JSON.parse(glue.handle(req.cmd, JSON.stringify(req.payload)))
      if (out && out.ok === false && out.error) {
        post({ type: 'response', id: req.id, ok: false, error: out.error })
      } else {
        post({ type: 'response', id: req.id, ok: true, result: out })
      }
    } catch (e) {
      post({ type: 'response', id: req.id, ok: false, error: { kind: 'engine', message: String(e) } })
    }
  })()
})

void boot().catch((e: unknown) => {
  // 初始化失败（资产缺失/版本不匹配/引擎语法错）：上报后本 worker 作废，
  // client 侧降级 HTTP；不能让 worker 静默死掉（主线程要能感知）
  post({ type: 'progress', phase: 'failed', message: String(e) })
})
