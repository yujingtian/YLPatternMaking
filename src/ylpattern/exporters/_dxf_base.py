"""DXF 输出共享底座（R12 / mm；裁床与服装 CAD 兼容口径）。

约定（详见 .doc/python工程设计.md §10.3 DXF 小节）：
- 版本 DXF R12（AC1009）：富怡/ET/格柏等服装 CAD 与裁床兼容面最广；
  实体白名单仅 LINE / CIRCLE / 2D POLYLINE / TEXT（LWPOLYLINE/SPLINE/
  MTEXT 均 R13+，R12 下 ezdxf 直接抛错）。
- 单位 mm：坐标写入前 cm × MM_PER_CM；R12 无 $INSUNITS（R2000+ 才有），
  以 TEXT "UNITS=MM" 兜底声明。
- 全部层名与 TEXT 内容 ASCII：R12 单行 TEXT + SHX/DBCS 编码跨软件易乱码，
  中文标注只留在 SVG。
- 依赖 ezdxf（pyproject 可选 extra ``dxf``）：仅在本模块 lazy import，
  核心层零第三方依赖不受影响；未安装时 RuntimeError 带安装指引。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence

from ..geometry import CubicBezier, LineSegment, Point

MM_PER_CM = 10.0        # cm -> mm
FLATTEN_TOL_CM = 0.01   # 曲线离散弦高公差 0.1mm（裁床典型切割精度）
MAX_FLATTEN_DEPTH = 12  # 递归细分深度上限（2^12 段，防病态输入）
NOTCH_LEN_CM = 0.5      # 刀口刻线长 5mm（对位刀口通用画法）
DRILL_RADIUS_MM = 0.5   # 定位孔显示半径（直径 1mm 钻孔）
TEXT_HEIGHT_MM = 2.5    # 单行 TEXT 字高

LayerSpec = tuple[int, str]                      # (ACI 颜色号, 线型名)
ToMm = Callable[[Point], tuple[float, float]]    # cm 点 -> mm 坐标


def require_ezdxf():
    """lazy import ezdxf；未安装时抛 RuntimeError（含安装指引）。"""
    try:
        import ezdxf
    except ImportError as exc:
        raise RuntimeError(
            "DXF 输出需要 ezdxf：请安装 pip install 'ylpattern[dxf]'"
            "（或 pip install 'ezdxf>=1.1'）") from exc
    return ezdxf


def new_doc(layer_specs: Mapping[str, LayerSpec]):
    """新建 R12 文档并按映射表 {(层名): (颜色, 线型)} 建层。

    setup=True 载入 DASHED 等标准线型；线型缺失时回退 CONTINUOUS
    （仅显示差异，不影响切割几何）。
    """
    ezdxf = require_ezdxf()
    # 压掉 ezdxf 建档时"R12 不导出 $INSUNITS"的 logger 警告：本层本就不设
    # 该变量（R2000+ 才有，见模块 docstring），警告属预期，逐次打印扰人。
    _logger = logging.getLogger("ezdxf")
    _level = _logger.level
    _logger.setLevel(logging.ERROR)
    try:
        doc = ezdxf.new("R12", setup=True)
    finally:
        _logger.setLevel(_level)
    for name, (color, linetype) in layer_specs.items():
        if linetype not in doc.linetypes:
            linetype = "CONTINUOUS"
        doc.layers.add(name, color=color, linetype=linetype)
    return doc


def _perp_dist(p: Point, chord_a: Point, chord_b: Point) -> float:
    """点 p 到弦 chord_a->chord_b 的垂直距离；弦退化（闭合尖点）取 |p-chord_a|。"""
    v = chord_b - chord_a
    w = p - chord_a
    if v.length < 1e-12:
        return w.length
    cross = v.dx * w.dy - v.dy * w.dx
    return abs(cross) / v.length


def flatten_bezier(b: CubicBezier, tolerance: float = FLATTEN_TOL_CM, *,
                   max_depth: int = MAX_FLATTEN_DEPTH) -> list[Point]:
    """弦高公差驱动的贝塞尔离散化（递归 de Casteljau 细分）。

    判据用控制点弦距上界：垂直弦距对控制点是仿射线性函数，曲线真实最大
    弦高 <= max(dist(p1), dist(p2))，故判据保守但严格安全。控制点全在
    弦上时（真实直线）直接返回两端点；tolerance=0 时细分到 max_depth
    （2^max_depth 段）而非死递归。
    """
    return _flatten(b, tolerance, 0, max_depth)


def _flatten(b: CubicBezier, tolerance: float,
             depth: int, max_depth: int) -> list[Point]:
    d = max(_perp_dist(b.p1, b.p0, b.p3), _perp_dist(b.p2, b.p0, b.p3))
    if d <= tolerance or depth >= max_depth:
        return [b.p0, b.p3]
    left, right = b.split(0.5)
    return (_flatten(left, tolerance, depth + 1, max_depth)[:-1]
            + _flatten(right, tolerance, depth + 1, max_depth))


def flatten_geom(g: LineSegment | CubicBezier,
                 tolerance: float = FLATTEN_TOL_CM) -> list[Point]:
    """线/曲线统一离散（直线不细分，曲线按公差 flatten）。"""
    if isinstance(g, LineSegment):
        return [g.a, g.b]
    return flatten_bezier(g, tolerance)


def add_polyline(msp, pts_cm: Sequence[Point], to_mm: ToMm, *,
                 layer: str, closed: bool = False) -> None:
    """点列（cm 域）经 to_mm 变换后写 2D POLYLINE（R12 自动 VERTEX/SEQEND）。

    连续重复点与闭合首尾重复点先去重，防零长度段（个别裁床对零长度
    顶点报错）；去重后不足 2 点则跳过（退化输入不上版）。
    """
    eps = 1e-6  # mm 域去重容差
    pts: list[tuple[float, float]] = []
    for p in pts_cm:
        xy = to_mm(p)
        if pts and abs(xy[0] - pts[-1][0]) < eps \
                and abs(xy[1] - pts[-1][1]) < eps:
            continue
        pts.append(xy)
    if closed and len(pts) > 1:
        first, last = pts[0], pts[-1]
        if abs(first[0] - last[0]) < eps and abs(first[1] - last[1]) < eps:
            pts.pop()
    if len(pts) < 2:
        return
    msp.add_polyline2d(pts, close=closed, dxfattribs={"layer": layer})


def add_text(msp, text: str, pos_cm: Point, to_mm: ToMm, *,
             layer: str = "TEXT", height_mm: float = TEXT_HEIGHT_MM) -> None:
    """单行 TEXT（左对齐，插入点由 to_mm 变换）。调用方保证 text 为 ASCII。"""
    x, y = to_mm(pos_cm)
    msp.add_text(text, dxfattribs={"layer": layer, "height": height_mm}) \
        .set_placement((float(x), float(y)))


def set_extents(doc) -> None:
    """按模型空间实体真实范围回填 $EXTMIN/$EXTMAX（连同 $LIMMIN/$LIMMAX）。

    ezdxf 的 saveas -> update_all() 会用 **modelspace 布局属性**
    msp.dxf.extmin/extmax/limmin/limmax 覆写同名 header 变量，而布局
    属性默认是 (±1e+20) 哨兵值 / A3 图幅——只写 header 会在写盘时被冲掉
    （本函数第一版踩过此坑）。必须把值设到 msp.dxf 上，header 同步直写
    供保存前内存读取。老服装 CAD（ET 2008 等）直接拿 $EXTMIN/$EXTMAX
    做初始视图/全图缩放，哨兵值导致打开黑屏；AutoCAD 自行重算无碍。
    """
    xs: list[float] = []
    ys: list[float] = []
    for e in doc.modelspace():
        t = e.dxftype()
        if t == "LINE":
            xs += [e.dxf.start.x, e.dxf.end.x]
            ys += [e.dxf.start.y, e.dxf.end.y]
        elif t == "CIRCLE":
            xs += [e.dxf.center.x - e.dxf.radius, e.dxf.center.x + e.dxf.radius]
            ys += [e.dxf.center.y - e.dxf.radius, e.dxf.center.y + e.dxf.radius]
        elif t == "TEXT":
            xs.append(e.dxf.insert.x)
            ys.append(e.dxf.insert.y)
        elif t == "POLYLINE":
            for v in e.vertices:
                xs.append(v.dxf.location.x)
                ys.append(v.dxf.location.y)
    if not xs:
        return
    xmin, ymin, xmax, ymax = min(xs), min(ys), max(xs), max(ys)
    msp = doc.modelspace()
    msp.dxf.extmin = (xmin, ymin, 0.0)     # saveas 覆写源（关键）
    msp.dxf.extmax = (xmax, ymax, 0.0)
    msp.dxf.limmin = (xmin, ymin)
    msp.dxf.limmax = (xmax, ymax)
    doc.header["$EXTMIN"] = (xmin, ymin, 0.0)
    doc.header["$EXTMAX"] = (xmax, ymax, 0.0)
    doc.header["$LIMMIN"] = (xmin, ymin)
    doc.header["$LIMMAX"] = (xmax, ymax)
