"""reverse.emit 金标测试（TOML 发射/回读/回验；不依赖 ezdxf/真件）。

头注手工演算（Calibration 同 test_reverse_measure：weft 0.15 / warp 0.08，
8 键与选项取该文件 measure_options 产物形状）：
- 圆整：测量 0.1（waist 29.75 -> 29.8、hip 94.18 -> 94.2）；选项/缝份/
  档差 0.01/0.02 原样；
- 回验：options 含未知键 -> PatternOptions.from_dict TypeError（发射前
  拦截，不写文件）；
- 回读：tomllib 解析产物逐键相等（int 形态 2 == 2.0）；子表 coerce 成
  FrontSeamAllowances；
- [size_run] 单 band 展开：S 基码 + 步进 waist 2.5 -> M = S+2.5、
  L = M+2.5（±0.05；步进归属 i+1 所属段）。
"""

from __future__ import annotations

import pytest

from ylpattern.params import Measurements, PatternOptions, load_size_run
from ylpattern.params.sizefile import load_size_file
from ylpattern.reverse.emit import (build_size_file, options_whitelist,
                                    render_toml)
from ylpattern.reverse.measure import MeasuredSize

_MS = MeasuredSize(size="S", values={
    "waist": 29.75, "hip": 94.18, "thigh": 52.70, "knee": 45.90,
    "hem": 42.517, "front_rise": 32.786, "back_rise": 38.250,
    "outseam": 62.380}, trace=["hip=2*(250+304)*0.85 = 94.18cm"], extras={})

_OPTS = {
    "delta": 2.0, "knee_adjust": 2.55, "hem_adjust": 2.55,
    "waist_balance": 0.04, "rise_adjust": 8.56,
    "front_intake_adjust": -2.83, "back_intake": 2.62,
    "waistband_width": 4.51, "waistband_type": "curved",
    "back_yoke_cb_dist": 5.6, "back_yoke_side_dist": 7.19,
    "shrinkage_warp": 0.08, "shrinkage_weft": 0.15,
    "back_yoke": True, "front_pocket": True, "front_pocket_facing": True,
    "front_pouch": False, "belt_loop": False, "fly_separate": True,
    "thigh_limit": True, "size_label": "S",
    "front_pocket_p1_dist": 13.6, "front_pocket_p2_drop": 6.9,
    "front_pocket_mouth_mode": "polyline",
    "front_pocket_mouth_corners": ((0.18, 2.7), (0.44, 2.97), (0.69, 2.06)),
    "front_pocket_facing_width": 2.15, "front_pocket_facing_side_w": 4.8,
    "front_pocket_facing_mode": "bulge",
    "front_pocket_facing_bulge": 3.1, "front_pocket_facing_bulge_at": 0.47,
    "front_piece_seam_allowances": {"waist": 1.27, "rise": 1.27,
                                    "inseam": 1.27, "side": 1.27,
                                    "mouth": 1.27, "hem": 3.17},
}

_SR = {"base": "S", "style": "T5015", "order": ["S", "M", "L"],
       "band": [{"sizes": ["S", "M", "L"], "waist": 2.5, "hip": 2.5,
                 "knee": 1.3, "hem": 1.0, "front_rise": 0.3, "back_rise": 0.5,
                 "outseam": 1.2, "thigh": 1.3}]}


def test_whitelist_contains_emit_keys():
    wl = options_whitelist()
    for k in ("delta", "front_intake_adjust", "waistband_grain",
              "front_piece_seam_allowances", "thigh_limit"):
        assert k in wl


def test_build_roundtrip_and_rounding(tmp_path):
    data = build_size_file(_MS, dict(_OPTS), None)
    assert data["measurements"]["waist"] == pytest.approx(29.8, abs=1e-9)
    assert data["measurements"]["hip"] == pytest.approx(94.2, abs=1e-9)
    path = tmp_path / "rev.toml"
    path.write_text(render_toml(data, ["头注行"]), encoding="utf-8")
    raw = load_size_file(str(path))
    m = Measurements.from_dict(raw["measurements"])
    assert m.hip == pytest.approx(94.2, abs=1e-9)
    assert m.outseam == pytest.approx(62.4, abs=1e-9)
    o = PatternOptions.from_dict(raw["options"])
    assert o.delta == pytest.approx(2.0)          # TOML int 2 回读
    assert o.waistband_type.value == "curved"     # 字符串加引号回读
    assert o.back_yoke is True and o.fly_separate is True
    assert o.thigh_limit is True and o.size_label == "S"
    sa = o.front_piece_seam_allowances            # 子表 coerce
    assert sa.hem == pytest.approx(3.17)
    assert sa.side == pytest.approx(1.27)
    # 挖削口袋：标量键 + 折角元组表（数组字面量渲染 -> list 回读归一化）
    assert o.front_pocket_p1_dist == pytest.approx(13.6)
    assert o.front_pocket_p2_drop == pytest.approx(6.9)
    assert o.front_pocket_mouth_mode == "polyline"
    assert o.front_pocket_mouth_corners == ((0.18, 2.7), (0.44, 2.97),
                                            (0.69, 2.06))
    # 袋贴内边族（净边大弧量测；bulge = 引擎单位，真弧高减半发射）
    assert o.front_pocket_facing_width == pytest.approx(2.15)
    assert o.front_pocket_facing_side_w == pytest.approx(4.8)
    assert o.front_pocket_facing_mode == "bulge"
    assert o.front_pocket_facing_bulge == pytest.approx(3.1)
    assert o.front_pocket_facing_bulge_at == pytest.approx(0.47)


def test_unknown_option_key_rejected_before_write():
    bad = dict(_OPTS)
    bad["nonexistent_knob"] = 1.0
    with pytest.raises(TypeError):                # PatternOptions.from_dict
        build_size_file(_MS, bad, None)


def test_size_run_roundtrip_expansion(tmp_path):
    data = build_size_file(_MS, dict(_OPTS), _SR)
    path = tmp_path / "rev_run.toml"
    path.write_text(render_toml(data, ["头注行"]), encoding="utf-8")
    run = load_size_run(str(path), fallback_base="S")
    assert run is not None and run.base == "S" and run.style_name == "T5015"
    assert run.labels == ("S", "M", "L")
    m_s = run.measurements("S")
    assert m_s.waist == pytest.approx(29.8, abs=0.05)
    assert run.measurements("M").waist == pytest.approx(29.8 + 2.5, abs=0.05)
    assert run.measurements("L").hip == pytest.approx(94.2 + 5.0, abs=0.05)
    # thigh 步进生效（基码 thigh>0）
    assert run.measurements("L").thigh == pytest.approx(52.7 + 2.6, abs=0.05)
