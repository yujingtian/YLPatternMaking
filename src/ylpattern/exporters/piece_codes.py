"""排料系统对接：裁片 g 码编号植入（赋码表 / 数量表 / 锚点算法）。

口径权威：仓库根《母版DXF编号植入对接文档_2026-09.md》（排料系统
materialSorting-server 的解析与赋码规范，2026-09）。本模块是引擎侧编号
的单一来源，piece_dxf 渲染与 /api/nest 数量契约都从这里取数：

- **块名尾缀** ``{片名}-G{NN}-{码号}``：对接方先剥码号尾缀
  ``[-._](\\d+)$``，剩余部分以 ``(?:g|G|#)(\\d{1,3})$`` 结尾即命中
  方式 A（编号全量复用、all-or-nothing）；
- **数量表 numMap**：每 g 码一个默认裁剪数量（2026-09-20 用户口径：
  前后片/机头/前口袋/腰头/袋布/后贴袋/小表袋默认 2、门襟默认 1；
  裤耳整根连裁不走排料，含在常规裁片 DXF 但不进排料产物）；
- **锚点算法** label_anchor：编号 TEXT 插入点（质心落片外时取扫描线
  最宽内条带中点，凹片不悬空），纯几何零依赖。

g 码缺片留洞（如未开 watch_pocket 则 g09 空缺）不影响方式 A 的
all-or-nothing 判定——只要求「在场片全部带编号且码内唯一」。
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from ..pieces import PatternPiece

# g 码固定分配表（piece.name -> g 码号）。front_facing / front_patch 同槽
# g04（前口袋二选一形态，collect_pieces 恒互斥）；front_fly_single 与
# front_fly_double 可同场（fly_separate 时双排门襟另成一片），分占 g08/g11。
PIECE_GCODES: dict[str, int] = {
    "front_piece": 1,
    "back_piece": 2,
    "back_yoke": 3,
    "front_facing": 4,
    "front_patch": 4,
    "waistband": 5,
    "front_pouch": 6,
    "back_patch": 7,
    "front_fly_single": 8,
    "watch_pocket": 9,
    "belt_loop": 10,
    "front_fly_double": 11,
}

# 排料默认数量表（g 码载体）：用户口径 2026-09-20，各码同数量；
# 小表袋 1（2026-09-20 修订，原 2）。
PIECE_QUANTITIES: dict[str, int] = {
    "front_piece": 2,
    "back_piece": 2,
    "back_yoke": 2,
    "front_facing": 2,
    "front_patch": 2,
    "waistband": 2,
    "front_pouch": 2,
    "back_patch": 2,
    "front_fly_single": 1,
    "front_fly_double": 1,
    "watch_pocket": 1,
}

# 不进排料产物的裁片（belt_loop 整根连裁条带不走 nesting；常规裁片
# DXF 维持含裤耳现状，仅 /api/nest 侧过滤）。
NEST_EXCLUDED = frozenset({"belt_loop"})

CODE_TEXT_HEIGHT_MM = 25.0   # 编号 TEXT 字高（对接规范：与 marker 导出同口径）

# 对接文档 §3 两条识别正则的复刻（自校验测试与 parse_block_code 用）
_SIZE_TAIL_RE = re.compile(r"[-._](\d+)$")          # 块名码号尾缀
_G_TAIL_RE = re.compile(r"(?:g|G|#)(\d{1,3})$")     # 剥码号后的 g 码尾缀


def gcode_for(piece_name: str) -> int:
    """piece.name -> g 码号；未登记名 raise（all-or-nothing 防线：新片型
    忘记登记时宁可响亮失败，也不静默产出半带编号的文件让对接方整体
    回退顺序赋码）。"""
    try:
        return PIECE_GCODES[piece_name]
    except KeyError:
        raise ValueError(
            f"裁片未登记排料 g 码：{piece_name!r}（请在 exporters/"
            "piece_codes.py 的 PIECE_GCODES/PIECE_QUANTITIES 补登记）"
        ) from None


def format_gcode(n: int) -> str:
    """g 码号 -> 规范文本（g01 起，两位补零，与对接方规范化一致）。"""
    return f"g{n:02d}"


def code_text(n: int, size: str) -> str:
    """编号 TEXT 值：码号为纯数字时 ``g05-30``，否则（如单码常规导出的
    "-"）只写 ``g05``（对接方 size=None，该片不参与排料，语义自洽）。"""
    g = format_gcode(n)
    return f"{g}-{size}" if is_numeric_size(size) else g


def parse_block_code(block_name: str) -> tuple[str | None, int | None]:
    """按对接文档方式 A 复算块名携带的 (码号, g 码号)；任一不存在为
    None。自校验测试用它对产物回读复算，与渲染意图逐块比对。"""
    base = block_name
    size: str | None = None
    m = _SIZE_TAIL_RE.search(base)
    if m:
        size = m.group(1)
        base = base[:m.start()]
    g = _G_TAIL_RE.search(base)
    return size, (int(g.group(1)) if g else None)


def is_numeric_size(label: str) -> bool:
    """码号是否为纯 ASCII 数字（排料块名码号尾缀要求 ``\\d+$``）。"""
    return label.isascii() and label.isdigit()


def assert_numeric_labels(labels: Sequence[str]) -> None:
    """推板码号逐个校验纯数字；有不良码聚合 raise（消息列全部不良项，
    一次改完，不挤牙膏）。"""
    bad = [s for s in labels if not is_numeric_size(s)]
    if bad:
        raise ValueError(
            "推板码号须为纯数字（排料 DXF 块名码号尾缀要求）："
            + "、".join(repr(s) for s in bad)
        )


def inch_size_label(waist_cm: float) -> str:
    """单码（未开推板）时的排料码号：腰围 cm 换算英寸档 round(waist/2.54)
    （如 74cm -> 29、68cm -> 27）。显式 +0.5 取整防 Python banker 舍入。"""
    return str(int(waist_cm / 2.54 + 0.5))


def nest_pieces(pieces: Sequence[PatternPiece]) -> list[PatternPiece]:
    """排料裁片集：过滤 NEST_EXCLUDED（belt_loop 整根连裁不进排料）。"""
    return [p for p in pieces if p.name not in NEST_EXCLUDED]


def nest_num_map(pieces: Sequence[PatternPiece]) -> dict[str, int]:
    """排料数量契约 numMap：{g码: 默认数量}（扁平、各码同数量）。
    输入应为 nest_pieces 之后的片集（belt_loop 再滤一次，双保险）；
    未登记名/数量 raise（与渲染同一防线，带指引消息）。"""
    out: dict[str, int] = {}
    for p in pieces:
        if p.name in NEST_EXCLUDED:
            continue
        g = gcode_for(p.name)      # 先取 g 码：未登记名在此响亮 raise
        try:
            qty = PIECE_QUANTITIES[p.name]
        except KeyError:
            raise ValueError(
                f"裁片未登记排料数量：{p.name!r}（请补登记 exporters/"
                "piece_codes.py 的 PIECE_QUANTITIES）") from None
        out[format_gcode(g)] = qty
    return out


def nest_labels(pieces: Sequence[PatternPiece]) -> dict[str, str]:
    """{g码: 裁片中文名}（piece.label），仅供 Web 展示，不进 DXF（ASCII 红线）。"""
    return {format_gcode(gcode_for(p.name)): p.label for p in pieces}


def point_in_polygon(pt: tuple[float, float],
                     poly: Sequence[tuple[float, float]]) -> bool:
    """射线法偶奇判定（边界上的点按半开区间处理，不保证一致；锚点算法
    只需区分片内/片外，边界情形由条带中点与质心两级兜底覆盖）。"""
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            t = (y - y1) / (y2 - y1)
            if x1 + t * (x2 - x1) > x:
                inside = not inside
    return inside


def _round2(pt: tuple[float, float]) -> tuple[float, float]:
    return (round(pt[0], 2), round(pt[1], 2))


def label_anchor(pts_mm: Sequence[tuple[float, float]]
                 ) -> tuple[float, float]:
    """编号 TEXT 插入点（对接文档 §5 锚点算法，输入/输出均 block-local mm）：

    1. c = 顶点算术质心；c 在多边形内 -> 用 c；
    2. 否则（凹片，质心落片外）：取扫描线 y = bbox 纵向中点，与各边严格
       跨越（``(y1-my)*(y2-my) < 0``，顶点擦线不产生假交点）求交点 x，
       排序后偶奇配对成内条带，按条带宽度降序取首个「中点在片内」的
       条带，用条带中点；
    3. 全部失败 -> 质心兜底（退化情形）。

    坐标 round 到 2 位小数。"""
    n = len(pts_mm)
    if n == 0:
        return (0.0, 0.0)
    c = (sum(p[0] for p in pts_mm) / n, sum(p[1] for p in pts_mm) / n)
    if point_in_polygon(c, pts_mm):
        return _round2(c)
    my = (min(p[1] for p in pts_mm) + max(p[1] for p in pts_mm)) / 2.0
    xs: list[float] = []
    for i in range(n):
        x1, y1 = pts_mm[i]
        x2, y2 = pts_mm[(i + 1) % n]
        if (y1 - my) * (y2 - my) < 0.0:
            xs.append(x1 + (my - y1) / (y2 - y1) * (x2 - x1))
    xs.sort()
    strips = [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]
    strips.sort(key=lambda s: s[1] - s[0], reverse=True)
    for lo, hi in strips:
        mid = ((lo + hi) / 2.0, my)
        if point_in_polygon(mid, pts_mm):
            return _round2(mid)
    return _round2(c)
