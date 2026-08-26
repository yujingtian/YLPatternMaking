// 把 node_modules/pyodide 的运行时资产同步到 public/pyodide/<版本>/，
// worker 里 loadPyodide({ indexURL }) 指向该目录。self-host 而非 CDN：
// 内网/离线可用、版本固定、同源无 CORS。
//
// 资产清单（读 pyodide 314 源码确认，均在包根目录、无 dist/ 子目录）：
//   pyodide.asm.mjs    —— 运行时动态 import 的 wasm 加载胶水（indexURL 拼址，
//                          不经 Vite bundle，必须实际存在于该 URL）
//   pyodide.asm.wasm   —— CPython 解释器本体
//   python_stdlib.zip  —— 标准库（indexURL + 文件名运行时 fetch）
//   pyodide-lock.json  —— loadPyodide 启动时读取的锁文件
// 主入口 pyodide.mjs 不拷——worker 里 import 'pyodide' 由 Vite 打进 bundle。
//
// 幂等：目标目录已存在即跳过（predev/prebuild 每次都跑，不能拖慢启动）；
// pyodide 未安装（npm install 之前）只警告退出 0，worker init 失败自动
// 回退 HTTP，不阻塞构建。

import { existsSync, mkdirSync, copyFileSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const ASSETS = ['pyodide.asm.mjs', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']

const frontendDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'webapp', 'frontend')
const pkgDir = join(frontendDir, 'node_modules', 'pyodide')

if (!existsSync(pkgDir)) {
  console.warn('[sync-pyodide] node_modules/pyodide 未安装，跳过（npm install 后重跑）')
  process.exit(0)
}

const version = JSON.parse(readFileSync(join(pkgDir, 'package.json'), 'utf8')).version
const dest = join(frontendDir, 'public', 'pyodide', version)
if (existsSync(dest)) {
  console.log(`[sync-pyodide] ${version} 已同步，跳过`)
  process.exit(0)
}

mkdirSync(dest, { recursive: true })
for (const f of ASSETS) {
  if (!existsSync(join(pkgDir, f))) {
    console.warn(`[sync-pyodide] 缺少资产 ${f}（版本 ${version} 布局有变？请核对清单）`)
    process.exit(1)
  }
  copyFileSync(join(pkgDir, f), join(dest, f))
}

console.log(`[sync-pyodide] ${version} -> public/pyodide/${version}/（${ASSETS.length} 个文件）`)
