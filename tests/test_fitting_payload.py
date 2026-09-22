"""3D 试穿 payload 金标测试（.doc/python工程设计.md §10.11）。

金标（W=70, H=96, K=46, B=36, 前浪 25, 后浪 33, 裤长 102, 大腿围 58，
默认选项：直腰头宽 4、rise_ratio 0.25、rise_adjust 0、crotch_drop_adjust 0、
thigh_measure_offset 0）手工演算：
  站点高度：直裆深 = H×0.25 = 24 → 立裆 y = 102−24 = 78.0；
    臀围线 y = 78 + 24/3 = 86.0；膝围线 y = (0+78)/2 + 3 = 42.0；
    腰围线 y = 102 − 4 = 98.0（直腰头扣腰头宽）；脚口 y = 0.0；
    毗围线 y = 78 − 0 = 78.0（d=0 与立裆线重合，thigh 站点 == crotch 站点）。
  落裆 Dc = 96/100 + 0 = 0.96 → 后大裆尖 y = 78 − 0.96 = 77.04；
    前小裆尖 y = 78.0（立裆线上）。
  腰头直腰头为矩形：top_length == bottom_length（= 70.101537 = 净长代数和），
    width == waistband_width = 4.0。
  边名序列（默认选项，口袋挖削前片/后片主形态）：
    front = (waist, side, side, side, hem, inseam, inseam, rise, rise)
    back  = (waist, side, side, side, hem, inseam, inseam, cb, cb)
    腰头 = (bottom, right_end, top, top, left_end, bottom)
断言口径：链闭合/边长守恒为几何不变量；坐标序列化按 1e-6 舍入，
  故闭合容差取 2e-6（舍入上界）而非机器精度。
"""

import math

import pytest

from ylpattern.exporters.fitting import build_fitting_payload
from ylpattern.flows.back_flow import FULL_FLOW
from ylpattern.flows.collect import collect_pieces
from ylpattern.flows.runner import FlowRunner
from ylpattern.params import Measurements, PatternOptions

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
M_NO_THIGH = Measurements(waist=70, hip=96, knee=46, hem=36,
                          front_rise=25, back_rise=33, outseam=102)

FRONT_EDGE_NAMES = ("waist", "side", "side", "side",
                    "hem", "inseam", "inseam", "rise", "rise")
BACK_EDGE_NAMES = ("waist", "side", "side", "side",
                   "hem", "inseam", "inseam", "cb", "cb")
WAISTBAND_EDGE_NAMES = ("bottom", "right_end", "top", "top",
                        "left_end", "bottom")


def _payload(m=M, **kw):
    ctx = FlowRunner(m, PatternOptions(**kw)).run(FULL_FLOW)
    return build_fitting_payload(ctx, m), ctx


def test_top_level_structure():
    p, _ = _payload()
    assert set(p.keys()) == {"schema_version", "units", "frame", "body",
                             "pieces"}
    assert p["schema_version"] == 1
    assert p["units"] == "cm"
    assert p["frame"] == {"system": "sheet", "y_axis": "up"}
    assert [pc["key"] for pc in p["pieces"]] == \
        ["front_piece", "back_piece", "waistband"]


def test_stations_golden():
    """站点高度/围度/归属金标（头部手工演算）。"""
    p, _ = _payload()
    stations = {s["key"]: s for s in p["body"]["stations"]}
    assert list(stations.keys()) == \
        ["waist", "hip", "crotch", "thigh", "knee", "hem"]
    assert stations["waist"] == {"key": "waist", "y": 98.0,
                                 "girth_finished": 70, "per": "body"}
    assert stations["hip"]["y"] == pytest.approx(86.0)
    assert stations["hip"]["girth_finished"] == 96
    assert stations["crotch"] == {"key": "crotch", "y": 78.0,
                                  "girth_finished": None, "per": "body"}
    assert stations["thigh"]["y"] == pytest.approx(78.0)   # d=0 与立裆重合
    assert stations["thigh"]["girth_finished"] == 58
    assert stations["thigh"]["per"] == "leg"
    assert stations["knee"]["y"] == pytest.approx(42.0)
    assert stations["knee"]["girth_finished"] == 46
    assert stations["hem"]["y"] == 0.0
    assert stations["hem"]["girth_finished"] == 36


def test_stations_thigh_omitted():
    """大腿围未录入 -> thigh 站点整体省略（5 站）。"""
    p, _ = _payload(M_NO_THIGH)
    assert [s["key"] for s in p["body"]["stations"]] == \
        ["waist", "hip", "crotch", "knee", "hem"]


def test_body_points_and_crotch_drop():
    """落裆金标：Dc = 96/100 = 0.96；后大裆尖 77.04、前小裆尖 78.0。"""
    p, _ = _payload()
    body = p["body"]
    assert body["crotch_drop"] == pytest.approx(0.96)
    assert body["points"]["front_crotch_vertex"][1] == pytest.approx(78.0)
    assert body["points"]["back_crotch_vertex"][1] == pytest.approx(77.04)
    assert body["waistband_width"] == 4.0
    assert body["waistband_type"] == "straight"
    assert body["outseam"] == 102


def test_edge_name_sequences_golden():
    p, _ = _payload()
    by_key = {pc["key"]: pc for pc in p["pieces"]}
    assert tuple(e["name"] for e in by_key["front_piece"]["edges"]) == \
        FRONT_EDGE_NAMES
    assert tuple(e["name"] for e in by_key["back_piece"]["edges"]) == \
        BACK_EDGE_NAMES
    assert tuple(e["name"] for e in by_key["waistband"]["edges"]) == \
        WAISTBAND_EDGE_NAMES
    # role 映射：缝合边/腰口链/脚口/开放
    roles = {e["name"]: e["role"] for e in by_key["front_piece"]["edges"]}
    assert roles["waist"] == "top_chain" and roles["side"] == "seam"
    assert roles["hem"] == "hem" and roles["rise"] == "seam"
    broles = {e["name"]: e["role"] for e in by_key["back_piece"]["edges"]}
    assert broles["waist"] == "top_chain" and broles["cb"] == "seam"


def test_edge_chain_closed():
    """净边链闭合：相邻边折线首尾相接（1e-6 舍入 -> 容差 2e-6）。"""
    p, _ = _payload()
    for pc in p["pieces"]:
        edges = pc["edges"]
        for i, e in enumerate(edges):
            nxt = edges[(i + 1) % len(edges)]
            ax, ay = e["pts"][-1]
            bx, by = nxt["pts"][0]
            assert abs(ax - bx) < 2e-6 and abs(ay - by) < 2e-6, \
                f"{pc['key']} 边 {i}({e['name']}) 与下一条边不闭合"


def test_edge_length_conservation():
    """边长守恒：折线段长和 == 精确弧长（公差 0.01cm 离散）。"""
    p, _ = _payload()
    for pc in p["pieces"]:
        for e in pc["edges"]:
            poly = sum(math.dist(e["pts"][i], e["pts"][i + 1])
                       for i in range(len(e["pts"]) - 1))
            assert abs(poly - e["length"]) <= max(0.05, 0.002 * e["length"]), \
                f"{pc['key']}.{e['name']} 折线长 {poly:.4f} != 弧长 {e['length']:.4f}"


def test_hem_edges_at_global_zero():
    """反变换强断言：前后片 hem 边折线所有点 y == front.hem_line.a.y = 0。"""
    p, ctx = _payload()
    hem_y = ctx.line("front.hem_line").a.y
    assert hem_y == 0.0
    for key in ("front_piece", "back_piece"):
        pc = next(pc for pc in p["pieces"] if pc["key"] == key)
        for e in pc["edges"]:
            if e["name"] == "hem":
                assert e["pts"], f"{key}.hem 折线为空"
                for x, y in e["pts"]:
                    assert y == pytest.approx(hem_y, abs=1e-6)
                break
        else:
            pytest.fail(f"{key} 无 hem 边")


def test_piece_frames_and_origin_alive():
    """坐标系元数据：前后片 reflect_y + origin 非空（含 None 透传链回归）；
    腰头 local + origin=None。"""
    p, _ = _payload()
    by_key = {pc["key"]: pc for pc in p["pieces"]}
    assert by_key["front_piece"]["frame"] == "reflect_y"
    assert by_key["back_piece"]["frame"] == "reflect_y"
    assert by_key["front_piece"]["origin"] is not None
    assert by_key["back_piece"]["origin"] is not None
    assert by_key["waistband"]["frame"] == "local"
    assert by_key["waistband"]["origin"] is None


def test_origin_survives_cutter_chain():
    """origin 存活性（钉死 with_shrunk/with_gross/apply_shrinkage 三处透传）：
    collect_pieces 走完整裁切链后前后片 origin 仍非空。"""
    ctx = FlowRunner(M, PatternOptions()).run(FULL_FLOW)
    pieces, _skips = collect_pieces(ctx)
    by_name = {pc.name: pc for pc in pieces}
    assert by_name["front_piece"].origin is not None
    assert by_name["back_piece"].origin is not None
    assert by_name["back_piece"].frame == "reflect_y"


def test_waistband_scalars_golden():
    """腰头标量：直腰头矩形 top == bottom == 70.101537；width == 选项宽。"""
    p, _ = _payload()
    scal = next(pc for pc in p["pieces"]
                if pc["key"] == "waistband")["scalars"]
    assert scal["top_length"] == pytest.approx(70.101537, abs=1e-6)
    assert scal["bottom_length"] == pytest.approx(scal["top_length"], abs=1e-6)
    assert scal["width"] == 4.0


def test_bbox_sanity():
    """bbox 在整版合理范围：前片 x>=0、y∈[0,98]；后片在前片右侧（piece_gap）。"""
    p, _ = _payload()
    by_key = {pc["key"]: pc for pc in p["pieces"]}
    fx0, fy0, fx1, fy1 = by_key["front_piece"]["bbox"]
    bx0, _, bx1, _ = by_key["back_piece"]["bbox"]
    assert fx0 >= 0 and fy0 == pytest.approx(0.0, abs=1e-6)
    assert fy1 == pytest.approx(98.0, abs=0.5)     # 腰口附近（含弧线起伏）
    assert bx0 > fx1                                # 后片置于前片右侧
    assert bx1 > bx0


def test_curved_waistband_marks_frame_local():
    """弯腰头形态：站点腰线 y = 裤长（不扣腰头宽），腰头仍 local。"""
    p, _ = _payload(waistband_type="curved")
    stations = {s["key"]: s for s in p["body"]["stations"]}
    assert stations["waist"]["y"] == pytest.approx(102.0)
    assert p["body"]["waistband_type"] == "curved"
    wb = next(pc for pc in p["pieces"] if pc["key"] == "waistband")
    assert wb["frame"] == "local" and wb["origin"] is None
    assert wb["scalars"]["width"] == 4.0


# ---------- 袋贴 marks 净样态（2026-09-16 缩水不同态修复） ----------

def test_facing_marks_net_state_with_shrinkage():
    """袋贴 marks 输出整版袋口净线（与 front mouth 边同源同态）：
    专用缩水 10%/6% 下逐点重合 <1e-6。回归防线——piece.marks 随裁片
    apply_shrinkage 同步缩放（2D 出图正确）与未缩水 net_edges 不同态，
    直接消费曾把缝合依据线放大错位 0.93cm（用户尺寸单实测）。"""
    p, _ = _payload(front_pocket=True, front_pocket_facing=True,
                    front_pocket_shrinkage_warp=0.1,
                    front_pocket_shrinkage_weft=0.06)
    front = next(pc for pc in p["pieces"] if pc["key"] == "front_piece")
    facing = next(pc for pc in p["pieces"] if pc["key"] == "front_facing")
    mouth = [tuple(q) for e in front["edges"] if e["name"] == "mouth"
             for q in e["pts"]]
    assert mouth
    assert len(facing["marks"]) >= 1
    for mk in facing["marks"]:
        for qx, qy in mk["pts"]:
            d = min(math.hypot(qx - x, qy - y) for x, y in mouth)
            assert d < 1e-6


# ---------- 育克第 4 片（2026-09-14 业务装配链：后腰头↔育克↔后片） ----------

def test_yoke_piece_structure():
    """back_yoke 开启：pieces 固定序 [front, back, yoke, waistband]；育克
    frame=rot180 + origin 非空；边名 (bottom, side, top, cb)；role 表
    top=top_chain（顶替后片接腰头）、bottom/cb/side=seam。"""
    p, _ = _payload(back_yoke=True)
    assert [pc["key"] for pc in p["pieces"]] == \
        ["front_piece", "back_piece", "back_yoke", "waistband"]
    yoke = p["pieces"][2]
    assert yoke["frame"] == "rot180"
    assert yoke["origin"] is not None
    assert tuple(e["name"] for e in yoke["edges"]) == \
        ("bottom", "side", "top", "cb")
    roles = {e["name"]: e["role"] for e in yoke["edges"]}
    assert roles["top"] == "top_chain"
    assert roles["bottom"] == "seam" and roles["cb"] == "seam"
    assert roles["side"] == "seam"


def test_yoke_back_top_role_seam():
    """yoke 开启时后片上口边名 = top（机头下口线）且角色改判 seam
    （缝合对象换成育克下口，不再直接接腰头）；无 waist 边。"""
    p, _ = _payload(back_yoke=True)
    back = next(pc for pc in p["pieces"] if pc["key"] == "back_piece")
    names = [e["name"] for e in back["edges"]]
    assert "top" in names and "waist" not in names
    top = next(e for e in back["edges"] if e["name"] == "top")
    assert top["role"] == "seam"
    # 默认（无 yoke）后片 waist 仍 top_chain（向后兼容回归）
    p0, _ = _payload()
    back0 = next(pc for pc in p0["pieces"] if pc["key"] == "back_piece")
    w0 = next(e for e in back0["edges"] if e["name"] == "waist")
    assert w0["role"] == "top_chain"


def test_yoke_bottom_matches_back_top():
    """育克下口边与后片上口边是同一几何（机头下口线）：总长相等、
    全局端点重合（P0/PN，1e-6 舍入 -> 容差 2e-6）。"""
    p, ctx = _payload(back_yoke=True)
    yoke = next(pc for pc in p["pieces"] if pc["key"] == "back_yoke")
    back = next(pc for pc in p["pieces"] if pc["key"] == "back_piece")
    yb = [e for e in yoke["edges"] if e["name"] == "bottom"]
    bt = [e for e in back["edges"] if e["name"] == "top"]
    assert sum(e["length"] for e in yb) == \
        pytest.approx(sum(e["length"] for e in bt), abs=1e-6)
    p0, pn = ctx.point("back.yoke_cb_point"), ctx.point("back.yoke_side_point")
    first, last = yb[0]["pts"][0], yb[-1]["pts"][-1]
    ends = {(round(first[0], 4), round(first[1], 4)),
            (round(last[0], 4), round(last[1], 4))}
    assert ends == {(round(p0.x, 4), round(p0.y, 4)),
                    (round(pn.x, 4), round(pn.y, 4))}


def test_yoke_notches_frame_global():
    """育克 notches 全局坐标帧回归（2026-09-22 修：_piece_entry 漏传
    piece.frame，rot180 育克被按 reflect_y 逆变换、x 分量镜像错位）：
    无省款 cb 刀口 = 后中 O-P0 中点；有省款首刀口 = 省位拼合线 C_in
    （落在机头下口线上、与后片省腿 mark 上端 <0.15cm）。"""
    p, ctx = _payload(back_yoke=True)
    yoke = next(pc for pc in p["pieces"] if pc["key"] == "back_yoke")
    o = ctx.point("back.rise_top_point")
    p0 = ctx.point("back.yoke_cb_point")
    n = yoke["notches"][0]
    assert (n[0], n[1]) == pytest.approx(
        ((o.x + p0.x) / 2, (o.y + p0.y) / 2), abs=2e-6)

    # 有省几何须真切穿机头上下边界（默认省宽 2.0 在默认机头高度下不分割、
    # 引擎回退无省提取——参数取 examples/size_draft.toml 口径，与前端
    # fixture 同源）
    p2, _ = _payload(back_yoke=True, back_dart=True, back_dart_width=3.76,
                     back_dart_length=10.5, back_yoke_cb_dist=4.5)
    yoke2 = next(pc for pc in p2["pieces"] if pc["key"] == "back_yoke")
    back2 = next(pc for pc in p2["pieces"] if pc["key"] == "back_piece")
    c_in = yoke2["notches"][0]
    # C_in 在机头下口线（back.top 直线段）上
    bt = next(e for e in back2["edges"] if e["name"] == "top")
    (x0, y0), (x1, y1) = bt["pts"][0], bt["pts"][-1]
    cross = abs((x1 - x0) * (c_in[1] - y0) - (y1 - y0) * (c_in[0] - x0))
    assert cross / math.hypot(x1 - x0, y1 - y0) < 1e-3
    # C_in 与后片省腿 mark 上端（省口内侧腿 ∩ 上口线）互证
    legs = [mk["pts"] for mk in back2["marks"] if len(mk["pts"]) >= 2]
    d_min = min(math.hypot(c_in[0] - q[0], c_in[1] - q[1])
                for leg in legs for q in (leg[0], leg[-1]))
    assert d_min < 0.15


def test_curved_waistband_yoke():
    """弯腰头 + yoke：育克仍入 payload（上口=下腰头线），三片拓扑不变量
    （链闭合/边长守恒由通用用例覆盖）。"""
    p, _ = _payload(back_yoke=True, waistband_type="curved")
    assert [pc["key"] for pc in p["pieces"]][-2] == "back_yoke"
    yoke = next(pc for pc in p["pieces"] if pc["key"] == "back_yoke")
    top = next(e for e in yoke["edges"] if e["name"] == "top")
    assert top["role"] == "top_chain"


def test_front_facing_piece_structure():
    """front_pocket+facing 开启：袋贴第 5 片（yoke 之后、腰头之前）；
    外边 1:1 复制前大片——waist 并入腰口链 top_chain、side 缝合 seam、
    inner 接袋布 free；origin/frame 登记全局反变换（3D 摆位依赖，
    2026-09-15 修：漏登记会被前端当局部系原样消费）。"""
    p, _ = _payload(back_yoke=True, front_pocket=True,
                    front_pocket_facing=True)
    assert [pc["key"] for pc in p["pieces"]] == \
        ["front_piece", "back_piece", "back_yoke", "front_facing",
         "waistband"]
    facing = p["pieces"][3]
    assert facing["frame"] == "reflect_y"
    assert facing["origin"] is not None
    roles = {e["name"]: e["role"] for e in facing["edges"]}
    assert set(roles) == {"side", "inner", "waist"}
    assert roles["waist"] == "top_chain"
    assert roles["side"] == "seam"
    assert roles["inner"] == "free"


def test_front_mouth_carve_with_pocket():
    """前口袋主切口：前片净边出现 mouth 边（free = 口袋开口），
    腰口弧 top_chain 只剩 CF→P1 段（腰口侧段由袋贴接管）。"""
    p, _ = _payload(front_pocket=True, front_pocket_facing=True)
    front = next(pc for pc in p["pieces"] if pc["key"] == "front_piece")
    mouth = next(e for e in front["edges"] if e["name"] == "mouth")
    assert mouth["role"] == "free"
    assert mouth["length"] > 10          # 袋口母线量级（非退化）
