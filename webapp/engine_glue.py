"""浏览器 Pyodide worker 的 Python 侧胶水（随引擎 zip 打包，顶层模块）。

职责：把 webapp/backend/app.py 的 /api/draft/sheet、/api/adjust、
/api/draft/pieces、/api/seed 四端点**逐字段复刻**到浏览器本地执行——两边语义一致
由 tests/test_engine_glue.py 金标钉死（同输入下输出全等，含 SVG 字符串），
改任何一端跑一次测试即知漂移。

协议：worker 调 handle(cmd, payload_json) -> str（JSON 字符串往返，
不经 PyProxy，无句柄泄漏）。**永不 raise**：一切异常转为
{"ok": false, "error": {"kind": "validation" | "engine", ...}}——
  validation：与 HTTP 422 同构（build_issues error 级 → detail=IssueDetail[]；
              未注册绑定/基线不可生成 → message），前端按参数错显示、
              不触发 HTTP 回退；
  engine：其余未捕获异常，前端回落 HTTP 通道再试。
DXF/toml/templates 不在本模块（重依赖 ezdxf / 读盘，留在后端）。
"""

from __future__ import annotations

import json

from ylpattern.exporters import piece_svg as piece_exp
from ylpattern.exporters import report as report_exp
from ylpattern.exporters import svg as svg_exp
from ylpattern.flows.adjust import solve_param
from ylpattern.flows.closure import run_with_thigh_closure
from ylpattern.flows.collect import collect_pieces
from ylpattern.params import Measurements, PatternOptions, build_issues
from ylpattern.webschema import binding_for, handles, seed_patch_shape


class _ValidationError(Exception):
    """参数问题（HTTP 422 同构）：换通道结果一样，前端直接显示。"""

    def __init__(self, message: str, detail: list | None = None):
        super().__init__(message)
        self.detail = detail


def _err(kind: str, message: str, detail: list | None = None) -> str:
    error: dict = {"kind": kind, "message": message}
    if detail is not None:
        error["detail"] = detail
    return json.dumps({"ok": False, "error": error}, ensure_ascii=False)


def _issue_dicts(issues) -> list[dict]:
    return [{"param": i.param, "group": i.group, "message": i.message,
             "level": i.level} for i in issues]


def _build(payload: dict):
    """校验 + 构造 (Measurements, PatternOptions)；error 级 -> validation
    （复刻 app.py _build，含 detail 数组键名）。"""
    issues = build_issues(payload.get("measurements", {}),
                          payload.get("options", {}))
    errors = [i for i in issues if i.level == "error"]
    if errors:
        raise _ValidationError("参数校验失败", _issue_dicts(errors))
    m = Measurements.from_dict(payload["measurements"])
    o = PatternOptions.from_dict(payload.get("options", {}))
    warnings = _issue_dicts(i for i in issues if i.level == "warning")
    return m, o, warnings


def _draft_ctx(payload: dict):
    m, o, warnings = _build(payload)
    ctx, _trace = run_with_thigh_closure(m, o)
    return m, o, ctx, warnings


def _sheet(payload: dict) -> dict:
    m, o, ctx, warnings = _draft_ctx(payload)
    _w, _h, top, ox = svg_exp.compute_view(ctx.sheet)
    return {
        "ok": True,
        "sheet_svg": svg_exp.render_sheet(ctx.sheet,
                                          show_labels=o.show_labels),
        "report": report_exp.render_report(ctx.sheet, m, o),
        "transform": {"scale": svg_exp.SCALE, "ox": ox, "top": top},
        "handles": handles(ctx, o),
        "warnings": warnings,
    }


# 反解热启动缓存：把手 (element, param, axis) -> 最近两次解 [(value,
# achieved), ...]。拖拽延续场景用两点弦截外推 guess（局部斜率稳定，
# 外推点几乎落在容差内 -> solve_param 1 次求值即返回，实测拖拽第 3 步起
# 14 次求值降为 1 次）。guess 只是提示：参数/测量已变导致外推失效时，
# 引擎静默走完整求解，正确性不受影响，至多多 1 次求值。
_SOLVE_CACHE: dict[tuple[str, str, str], list[tuple[float, float]]] = {}


def _warm_guess(key: tuple[str, str, str], target: float) -> float | None:
    hist = _SOLVE_CACHE.get(key)
    if not hist:
        return None
    if len(hist) == 1:                      # 单点：直接用上次解
        return hist[0][0]
    (v1, a1), (v2, a2) = hist[-2], hist[-1]
    slope = (a2 - a1) / (v2 - v1)           # 两点弦截外推
    if abs(slope) < 1e-6:
        return v2
    return v2 + (target - a2) / slope


def _adjust(payload: dict) -> dict:
    m, o, _warnings = _build(payload)
    adj = binding_for(payload["element"], payload["param"], payload["axis"])
    if adj is None:
        raise _ValidationError(
            f"未注册的可调绑定：{payload['element']} {payload['param']} "
            f"{payload['axis']}（见 /api/schema adjustable_points）")
    key = (adj.element, adj.param, adj.axis)
    try:
        r = solve_param(m, o, element=adj.element, param=adj.param,
                        axis=adj.axis, target=payload["target"],
                        lo=adj.lo, hi=adj.hi, t=adj.t,
                        guess=_warm_guess(key, payload["target"]))
    except ValueError as e:        # 基线不可生成：配置/测量矛盾
        raise _ValidationError(str(e)) from e
    hist = _SOLVE_CACHE.setdefault(key, [])
    hist.append((r.value, r.achieved))
    del hist[:-2]                  # 只留最近两点（斜率用）
    return {"ok": True, "converged": r.converged, "value": r.value,
            "params": {adj.param: r.value},
            "achieved": r.achieved, "residual": r.residual,
            "reason": r.reason, "evaluations": r.evaluations}


def _pieces(payload: dict) -> dict:
    _, o, ctx, warnings = _draft_ctx(payload)
    pieces, skips = collect_pieces(ctx)
    return {
        "ok": True,
        "pieces": [{"key": p.name, "name": p.label, "count": 1,
                    "svg": piece_exp.render_piece_svg(
                        p, show_seam=o.show_seam_allowance)}
                   for p in pieces],
        "skips": skips,
        "warnings": warnings,
    }


def _seed(payload: dict) -> dict:
    """预设形态 -> custom 初始角点/边（复刻 /api/seed；不走 _build：
    只依赖贴袋 5 参数，其余参数中间态非法时也要可用，§10.8）。"""
    try:
        return seed_patch_shape(payload["kind"], payload["shape"],
                                payload.get("options", {}))
    except ValueError as e:        # 非法 kind/shape/尺寸：HTTP 422 同构
        raise _ValidationError(str(e)) from e


_COMMANDS = {"sheet": _sheet, "adjust": _adjust, "pieces": _pieces,
             "seed": _seed}


def handle(cmd: str, payload_json: str) -> str:
    """命令分派（worker 唯一入口）：永不 raise，异常统一转 error JSON。"""
    try:
        fn = _COMMANDS.get(cmd)
        if fn is None:
            return _err("engine", f"未知命令：{cmd}")
        payload = json.loads(payload_json)
        return json.dumps(fn(payload), ensure_ascii=False)
    except _ValidationError as e:
        return _err("validation", str(e), e.detail)
    except Exception as e:  # noqa: BLE001 —— 边界兜底，worker 不允许抛穿
        return _err("engine", f"{type(e).__name__}: {e}")
