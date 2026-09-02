"""⑩ eval 脚本冒烟测试：示例金标 case 一轮评测全绿（召回/命中/探针）。

真实用途是判据/词典改动前后人工对比两轮报告（设计文档 §8）；此处只保证
脚本可跑、指标口径不回归。照片用例需 VLM 配置，CI 不覆盖（provider 已有
独立测试）。scripts/ 非包，用 subprocess 跑真脚本而非 import。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_CASES = _ROOT / "tests" / "_extract_golden" / "cases"
_SCRIPT = _ROOT / "scripts" / "eval_extract.py"


def test_eval_smoke_on_example_case(tmp_path):
    out = tmp_path / "eval.md"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--cases", str(_CASES),
         "--out", str(out)],
        capture_output=True, text=True, encoding="utf-8", cwd=_ROOT)
    assert proc.returncode == 0, proc.stderr
    text = out.read_text(encoding="utf-8")
    assert "female_high_sk_29" in text
    assert "8 键召回" in text and "100%" in text
    assert "探针通过" in text and "L0" in text
    assert "全部命中" in text
