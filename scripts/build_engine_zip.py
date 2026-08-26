"""把 ylpattern 引擎源码打成内容寻址 zip，供浏览器 Pyodide worker 加载。

产物（webapp/frontend/public/engine/）：
    ylpattern.<sha8>.zip   —— src/ylpattern/ 整棵目录树（按目录递归，新增/
                              删除/改名 .py 自动跟随，无需登记）+ 顶层
                              webapp/engine_glue.py（worker 胶水，可缺席）
    manifest.json          —— {"zip": ..., "rev": ..., "pyodide": ...}
                              worker 冷启动先取本文件（no-store）再按指向取
                              zip；zip 内容 hash 作文件名 = 变更检测自动化：
                              代码变 -> hash 变 -> 新 URL -> 缓存必然 miss。

确定性打包：ZipInfo 固定时间戳 + 排序遍历 + 定长压缩，同代码必同 zip
（否则每次构建 hash 都变，浏览器缓存全失效）。

用法：python scripts/build_engine_zip.py（前端 predev/prebuild 自动调用；
      开发中改了引擎源码后手动跑 + 刷新页面）
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src" / "ylpattern"
_GLUE = _ROOT / "webapp" / "engine_glue.py"
_OUT_DIR = _ROOT / "webapp" / "frontend" / "public" / "engine"
_PYODIDE_PKG = _ROOT / "webapp" / "frontend" / "node_modules" / "pyodide" / "package.json"

# 固定时间戳（1980-01-01 是 zip 格式能表示的最早值），保证确定性
_FIXED_DATE = (1980, 1, 1, 0, 0, 0)

# 不进包的内容：字节码缓存与编辑器临时文件
_EXCLUDE_NAMES = {"__pycache__"}
_EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".pyd", ".tmp"}


def _iter_files(base: Path, prefix: str = "") -> list[tuple[str, Path]]:
    """递归收集 (arcname, path)，目录序 + 文件名序双重排序保确定性。"""
    out: list[tuple[str, Path]] = []
    for path in sorted(base.iterdir(), key=lambda p: p.name):
        if path.name in _EXCLUDE_NAMES or path.suffix in _EXCLUDE_SUFFIXES:
            continue
        arc = f"{prefix}{path.name}"
        if path.is_dir():
            out.extend(_iter_files(path, arc + "/"))
        else:
            out.append((arc, path))
    return out


def _git_rev() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=_ROOT, capture_output=True, text=True,
                           encoding="utf-8", timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _pyodide_version() -> str | None:
    """从已安装的 node_modules 读 pyodide 版本（worker indexURL 用）。"""
    try:
        return json.loads(_PYODIDE_PKG.read_text(encoding="utf-8"))["version"]
    except Exception:
        return None


def build() -> int:
    if not _SRC.is_dir():
        print(f"[engine-zip] 引擎目录不存在：{_SRC}", file=sys.stderr)
        return 1
    entries = [("ylpattern/" + arc, p) for arc, p in _iter_files(_SRC)]
    if _GLUE.is_file():
        entries.append(("engine_glue.py", _GLUE))
    else:
        print("[engine-zip] 提示：webapp/engine_glue.py 尚不存在，"
              "本次包不含 worker 胶水（worker 将不可用，HTTP 回退）")

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _OUT_DIR / "ylpattern.tmp.zip"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for arc, path in sorted(entries):
            info = zipfile.ZipInfo(arc, date_time=_FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())

    data = tmp.read_bytes()
    sha8 = hashlib.sha256(data).hexdigest()[:8]
    final = _OUT_DIR / f"ylpattern.{sha8}.zip"
    tmp.replace(final)

    # 只保留当前 zip：旧 hash 的包永远不会再被 manifest 指向
    for old in _OUT_DIR.glob("ylpattern.*.zip"):
        if old.name != final.name:
            old.unlink()

    manifest = {"zip": final.name, "rev": _git_rev(),
                "pyodide": _pyodide_version()}
    (_OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    n_py = sum(1 for arc, _ in entries if arc.endswith(".py"))
    print(f"[engine-zip] {final.name}  {len(data)/1024:.0f} KB  "
          f"{n_py} 个 .py  rev={manifest['rev'] or '-'}  "
          f"pyodide={manifest['pyodide'] or '未安装'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
