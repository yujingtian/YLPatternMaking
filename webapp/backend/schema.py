"""薄再导出层：schema 的唯一实现在 ylpattern.webschema（2026-08 下沉）。

下沉动机：浏览器 Pyodide worker 胶水（webapp/engine_glue.py）与本后端
共用同一份 schema/绑定表/把手逻辑，防止两处实现漂移。本文件保留
webapp 侧 import 路径稳定（tests/test_web_api.py、test_web_adjust.py
等历史 import 不改）。
"""

from ylpattern.webschema import (  # noqa: F401
    ADJUSTABLES, Adjustable, binding_for, build_schema, gate_on, handles,
    seed_shape,
)
