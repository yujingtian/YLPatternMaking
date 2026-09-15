"""3D 试穿 payload 出口（.doc/python工程设计.md §10.11）。

build_fitting_payload(ctx, m) -> dict：前后片（back_yoke 开启时含育克）净样
边链经局部 -> 整版全局反变换（origin/frame 随 PatternPiece 携带，pieces.py）
序列化到全局坐标（cm、Y 向上），附人台放样站点（整版关键线高度 + 成衣
围度）与腰头标量。腰头为旋转局部系（origin=None、frame="local"），不逆推
坐标、只随标量导出。

完整牛仔裤装配链（2026-09-14 用户业务口径）：主件 = 腰头/育克/前片/后片，
缝合序 = 前腰头↔前片、后腰头↔育克上口、育克下口↔后片上口。back_yoke 开启
时育克作为第 4 片入 payload（front/back 之后、腰头之前），后片上口边（top
= 机头下口线）角色由 top_chain 改判 seam——它缝的是育克下口而非直接上腰头；
育克上口（top）顶替腰口链（top_chain）。无 yoke 时三片不变（向后兼容）。
前口袋袋贴（2026-09-15）：front_pocket_facing 开启时 front_facing 作为第 5
片入 payload（育克之后、腰头之前），waist 边（1:1 复制前大片腰弧段）角色
top_chain（前端并入腰口 pin/环带）、side 边（外缝弧段）角色 seam（前端缝
育克侧边/后片侧缝上端）、inner 边 free。

消费方为前端 fitting3d/ 模块；双通道（后端 /api/draft/fitting 与
engine_glue 的 fitting 命令）共用本函数，语义一致由 test_engine_glue.py
钉死。纯 stdlib；曲线离散复用 _dxf_base.flatten_geom（0.1mm 弦高，
与裁床 DXF 同口径）。

口径要点：
- 站点高度一律取前片线（back_steps 显式等高复用，仅落裆线下移），
  人台站点高度唯一、无前后分歧；
- girth_finished 是**成衣量**（waist/hip 整圈、thigh/knee/hem 单腿），
  供前端松量读数；人台围度来自前端独立 BodyProfile，不在本 payload；
- 语义边名 role 表驱动缝合配对（前端 seams.ts）：top_chain=腰口链、
  hem=脚口、seam=可缝合边、free=开放边（口袋口/门襟）。
"""

from __future__ import annotations

from ..cutter import edge_length
from ..draft import DraftContext
from ..flows.back_piece_flow import build_back_piece
from ..flows.front_piece_flow import build_front_piece
from ..flows.front_pocket_flow import build_front_pocket
from ..flows.waistband_flow import build_waistband
from ..flows.yoke_flow import build_yoke
from ..geometry import CubicBezier, LineSegment, Point
from ..params import Measurements, WaistbandType
from ._dxf_base import flatten_geom

FLATTEN_TOL = 0.01   # cm，与 _dxf_base.FLATTEN_TOL_CM 同口径

# 语义边名 -> 3D 角色（缝合配对/腰口 pin/脚口对齐用；未登记者默认 "free"）。
# back_piece 的 "top"（有 yoke = 机头下口线）默认 top_chain，yoke 开启时由
# build_fitting_payload 覆写为 seam（改缝育克下口，见模块 docstring）。
_EDGE_ROLES: dict[str, dict[str, str]] = {
    "front_piece": {
        "waist": "top_chain", "hem": "hem",
        "rise": "seam", "inseam": "seam", "side": "seam",
        "mouth": "free", "fly_top": "free", "fly_outer": "free",
        "fly_bottom": "free",
    },
    "back_piece": {
        "top": "top_chain", "waist": "top_chain", "hem": "hem",
        "cb": "seam", "inseam": "seam", "side": "seam",
    },
    "back_yoke": {
        "top": "top_chain", "bottom": "seam",
        "cb": "seam", "side": "seam",
    },
    # 袋贴外边 1:1 复制前大片：waist 腰弧段并入腰口链、side 外缝弧段缝
    # 育克侧边/后片侧缝上端；inner 内边接袋布（3D 无袋布片，free）
    "front_facing": {
        "waist": "top_chain", "side": "seam", "inner": "free",
    },
}


def _to_global(p: Point, origin: Point, frame: str) -> list[float]:
    """裁片局部坐标 -> 整版全局坐标（按 frame 逆变换）：
    reflect_y：local=(x−ox, oy−y) 故 global=(lx+ox, oy−ly)（前后片）；
    rot180：local=(ox−x, oy−y) 故 global=(ox−lx, oy−ly)（育克，保向）。"""
    if frame == "rot180":
        return [round(origin.x - p.x, 6), round(origin.y - p.y, 6)]
    return [round(p.x + origin.x, 6), round(origin.y - p.y, 6)]


def _pts_out(pts: list[Point], origin: Point | None,
             frame: str = "reflect_y") -> list[list[float]]:
    """折线点列序列化：origin=None（局部系裁片）原样输出。"""
    if origin is None:
        return [[round(p.x, 6), round(p.y, 6)] for p in pts]
    return [_to_global(p, origin, frame) for p in pts]


def _piece_entry(piece, role_override: dict[str, str] | None = None) -> dict:
    """单个裁片序列化。frame="reflect_y"（前后片）/"rot180"（育克）反变换
    到全局坐标；frame="local"（腰头）保持原样。role_override 逐边名覆写
    角色（yoke 开启时后片 top 由 top_chain 改判 seam）。"""
    roles = dict(_EDGE_ROLES.get(piece.name, {}))
    if role_override:
        roles.update(role_override)
    origin = piece.origin

    edges = []
    for e in piece.net_edges:
        edges.append({
            "name": e.name,
            "kind": "line" if isinstance(e.geom, LineSegment) else "bezier",
            "role": roles.get(e.name, "free"),
            "pts": _pts_out(flatten_geom(e.geom, FLATTEN_TOL), origin,
                            piece.frame),
            "length": round(edge_length(e.geom), 6),
        })
    flat = [pt for e in edges for pt in e["pts"]]
    xs = [p[0] for p in flat]
    ys = [p[1] for p in flat]

    grain = None
    if piece.grain is not None:
        grain = _pts_out([piece.grain.a, piece.grain.b], origin, piece.frame)

    return {
        "key": piece.name,
        "name": piece.label,
        "origin": ([round(origin.x, 6), round(origin.y, 6)]
                   if origin is not None else None),
        "frame": piece.frame,
        "bbox": [min(xs), min(ys), max(xs), max(ys)],
        "edges": edges,
        "marks": [{"pts": _pts_out(flatten_geom(g, FLATTEN_TOL), origin)}
                  for g in piece.marks],
        "notches": _pts_out(list(piece.notches), origin),
        "grain": grain,
    }


def _stations(ctx: DraftContext, m: Measurements) -> list[dict]:
    """人台放样站点：高度取整版关键线（前后等高），围度为成衣量。
    crotch 无围度（拓扑分叉站）；thigh 站点仅在录入大腿围时存在。"""
    out = [
        {"key": "waist", "y": round(ctx.line("front.waist_line").a.y, 6),
         "girth_finished": m.waist, "per": "body"},
        {"key": "hip", "y": round(ctx.line("front.hip_line").a.y, 6),
         "girth_finished": m.hip, "per": "body"},
        {"key": "crotch", "y": round(ctx.line("front.crotch_line").a.y, 6),
         "girth_finished": None, "per": "body"},
    ]
    if m.thigh and m.thigh > 0 and "front.thigh_line" in ctx.sheet:
        out.append({"key": "thigh", "per": "leg",
                    "y": round(ctx.line("front.thigh_line").a.y, 6),
                    "girth_finished": m.thigh})
    out.append({"key": "knee", "y": round(ctx.line("front.knee_line").a.y, 6),
                "girth_finished": m.knee, "per": "leg"})
    out.append({"key": "hem", "y": round(ctx.line("front.hem_line").a.y, 6),
                "girth_finished": m.hem, "per": "leg"})
    return out


def build_fitting_payload(ctx: DraftContext, m: Measurements) -> dict:
    """整版 DraftContext -> 3D 试穿 JSON payload（不含 ok/warnings，
    由 HTTP/glue 通道包装；见 app.py 与 engine_glue._fitting）。"""
    o = ctx.options
    front = build_front_piece(ctx)[0]
    back = build_back_piece(ctx)[0]
    waistband = build_waistband(ctx)[0]

    # 育克第 4 片（back_yoke 开启且机头步骤已上版；业务装配链见模块
    # docstring）。后片 top 边（机头下口线）随之改判 seam——缝合对象
    # 从腰头换成育克下口
    has_yoke = o.back_yoke and "back.yoke_cb_point" in ctx.sheet
    pieces = [
        _piece_entry(front),
        _piece_entry(back, {"top": "seam"} if has_yoke else None),
    ]
    if has_yoke:
        pieces.append(_piece_entry(build_yoke(ctx)[0]))
    # 袋贴第 5 片（front_pocket_facing 开启且袋贴步骤已上版；挖削款前片
    # 腰口弧缺段由袋贴补位缝合，见模块 docstring）
    if o.front_pocket_facing and "front.pocket_facing_waist_edge" in ctx.sheet:
        pieces.append(_piece_entry(build_front_pocket(ctx)[0]))

    f_vertex = ctx.point("front.crotch_vertex")
    b_vertex = ctx.point("back.crotch_vertex")
    crotch_drop = (ctx.line("front.crotch_line").a.y
                   - ctx.line("back.crotch_drop_line").a.y)

    wb_entry = _piece_entry(waistband)
    # 腰头标量（旋转局部系不可逆推）：上/下口净长 = 同语义边名多段代数和；
    # 宽取选项值（弯腰头顶弧有弧高，bbox 高不等于腰头宽）
    wb_entry["scalars"] = {
        "top_length": round(sum(edge_length(e.geom) for e in waistband.net_edges
                                if e.name == "top"), 6),
        "bottom_length": round(sum(edge_length(e.geom)
                                   for e in waistband.net_edges
                                   if e.name == "bottom"), 6),
        "width": o.waistband_width,
    }
    pieces.append(wb_entry)

    return {
        "schema_version": 1,
        "units": "cm",
        "frame": {"system": "sheet", "y_axis": "up"},
        "body": {
            "stations": _stations(ctx, m),
            "points": {
                "front_crotch_vertex": [round(f_vertex.x, 6),
                                        round(f_vertex.y, 6)],
                "back_crotch_vertex": [round(b_vertex.x, 6),
                                       round(b_vertex.y, 6)],
            },
            "crotch_drop": round(crotch_drop, 6),
            "waistband_width": o.waistband_width,
            "waistband_type": WaistbandType(o.waistband_type).value,
            "outseam": m.outseam,
        },
        "pieces": pieces,
    }
