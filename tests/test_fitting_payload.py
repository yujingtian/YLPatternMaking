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
