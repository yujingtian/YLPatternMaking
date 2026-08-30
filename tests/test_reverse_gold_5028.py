"""5028 真件金标测试（推码档差提取，层 3）。

头注手工演算（5028 六码 S/M/L/XL/2XL/3XL，基码 M = 头标 SAMPLE SIZE，
缩水 W15%-L8%，还原 = 净样mm ×0.85/0.92 ÷10；逐码独立测量绕开顶点
漂移——前片净样顶点数 188→195 随码漂移，跨码索引对应禁用）：

- M 基码 8 键：waist 66.70 / hip 97.85 / thigh 58.92 / knee 51.82 /
  hem 50.70 / front_rise 30.48 / back_rise 38.44 / outseam 95.16；
- 相邻码步进（原始值差分取中位数、圆整 0.01）：waist +2.37、hip +2.34、
  knee +0.91、hem +0.69、front_rise +0.45、back_rise +0.43、
  outseam +0.49、thigh +1.11——段内均匀（hip 步进跨码 2.31~2.37 缓变，
  偏差 ≤0.06 < 容差 0.15），单 band 全码、无分段/漂移告警；
- 前片净样 bbox 线性旁证：W 293.2→327.1（dW +6.7/+6.8，偏差 ≤0.1mm）、
  H 965.9→992.6（dH +5.3 恒定）——信息性对比（本期拟合测量不拟合形状）；
- 回读展开（load_size_run，步进归属 i+1 所在段 + 自基码双向累加）：
  3XL waist = 66.70 + 4×2.37 = 76.18 vs 实测 76.16（漂移 0.02）；
  S waist = 66.70 − 2.37 = 64.33 vs 实测 64.34。最坏漂移在 S hip：
  基码圆整 97.85→97.9（+0.05）+ hip 步进跨码缓变（实际 2.37 vs 中位数
  2.34，+0.03）-> 95.56 vs 95.48（0.08）——band 步进表示法的固有下限
  （逐码步进微变 + 基码圆整），告警线 0.1 以内、报告披露不阻塞。

真件不入库（out/ gitignored）：缺文件整文件 skip。
"""

from __future__ import annotations

import glob
from pathlib import Path

import pytest

pytest.importorskip("ezdxf")

from ylpattern.params import load_size_run
from ylpattern.reverse import reverse_dxf

_OUT = Path(__file__).resolve().parent.parent / "out"
_FILES_5028 = sorted(glob.glob(str(_OUT / "5028*.dxf")))
_real = _FILES_5028[0] if _FILES_5028 else None

pytestmark = pytest.mark.skipif(
    _real is None, reason="out/5028*.dxf 真件不在库内（out/ gitignored）")

_STEP_GOLDS = {"waist": 2.37, "hip": 2.34, "knee": 0.91, "hem": 0.69,
               "front_rise": 0.45, "back_rise": 0.43, "outseam": 0.49,
               "thigh": 1.11}


@pytest.fixture(scope="module")
def result():
    return reverse_dxf(_real)


def test_sizes_base_calibration(result):
    assert result.doc.sizes == ("S", "M", "L", "XL", "2XL", "3XL")
    assert result.base == "M"                        # 头标 SAMPLE SIZE
    assert result.calib.weft == pytest.approx(0.15)
    assert result.calib.warp == pytest.approx(0.08)


def test_base_measurement_golds(result):
    """M 基码 8 键（逐码独立测量的基码子集 = 层 1）。"""
    v = result.measured["M"].values
    assert v["waist"] == pytest.approx(66.70, abs=0.01)
    assert v["hip"] == pytest.approx(97.85, abs=0.01)
    assert v["thigh"] == pytest.approx(58.92, abs=0.01)
    assert v["knee"] == pytest.approx(51.82, abs=0.01)
    assert v["hem"] == pytest.approx(50.70, abs=0.01)
    assert v["front_rise"] == pytest.approx(30.48, abs=0.01)
    assert v["back_rise"] == pytest.approx(38.44, abs=0.01)
    assert v["outseam"] == pytest.approx(95.16, abs=0.01)
    assert v["hip"] > v["waist"]                     # 结构自检绊线


def test_pocket_inference_golds(result):
    """挖削口袋参数（M 基码发射；袋口形态与 5015 同族，仅侧边段微差）。"""
    opts, warns = result.options, result.warns
    assert opts["front_pocket_p1_dist"] == pytest.approx(8.80, abs=0.05)
    assert opts["front_pocket_p2_drop"] == pytest.approx(6.96, abs=0.05)
    assert opts["front_pocket_mouth_mode"] == "bulge"
    # 发射 = 引擎单位（arc_through 渲染弧高 = 2×bulge：真 3.36 -> 1.68）
    assert opts["front_pocket_mouth_bulge"] == pytest.approx(1.68, abs=0.05)
    assert opts["front_pocket_mouth_bulge_at"] == pytest.approx(0.21, abs=0.03)
    assert "front_pocket_mouth_corners" not in opts
    assert opts["front_pouch"] is False
    # 袋贴内边与 5015 同族（工厂袋贴不随码变化），仅侧段微差 52.7mm；
    # bulge 发射 = 引擎单位（真 6.24 -> 3.12、弦位 0.49 -> 0.47）
    assert opts["front_pocket_facing_width"] == pytest.approx(2.15, abs=0.02)
    assert opts["front_pocket_facing_side_w"] == pytest.approx(4.85, abs=0.05)
    assert opts["front_pocket_facing_mode"] == "bulge"
    assert opts["front_pocket_facing_bulge"] == pytest.approx(3.12, abs=0.1)
    assert opts["front_pocket_facing_bulge_at"] == pytest.approx(0.47, abs=0.03)
    assert any("袋贴内边 = 前代净边大弧" in w for w in warns)
    assert any("dart_width" in w and "不可分离" in w for w in warns)
    # 小表袋在场即开：火机袋净环 = 光板矩形 120.65×82.55mm、丝缕横 ->
    # 还原顶边 11.1cm > 0.9×p1（袋口装不下），对折片缝态两读（对折
    # 半幅/短边袋口）不自设（用户口径：不自己想象）-> 回退袋贴相交
    # 默认放置（保守矩形）：顶边深 0.42×p2=2.92、外端 0.12×p1=1.06、
    # 宽 0.55×p1=4.84（5015 是 custom 净样原样，两款分道）
    assert opts["watch_pocket"] is True
    assert "watch_pocket_mode" not in opts     # 回退 facing_intersect 默认
    assert opts["watch_pocket_offset_from_top"] == pytest.approx(2.92, abs=0.02)
    assert opts["watch_pocket_offset_from_side"] == pytest.approx(1.06, abs=0.02)
    assert opts["watch_pocket_width"] == pytest.approx(4.84, abs=0.02)
    assert any("对折" in w and "回退" in w for w in warns)


def test_grade_single_band_step_golds(result):
    """档差：单 band 全码、步进中位数金标、无分段/漂移告警。"""
    sr = result.size_run
    assert sr is not None and sr["base"] == "M"
    assert sr["order"] == ["S", "M", "L", "XL", "2XL", "3XL"]
    assert len(sr["band"]) == 1
    band = sr["band"][0]
    assert band["sizes"] == ["S", "M", "L", "XL", "2XL", "3XL"]
    for k, gold in _STEP_GOLDS.items():
        assert band[k] == pytest.approx(gold, abs=0.01), k
    assert not any("档差" in w for w in result.warns)   # 无分段/漂移告警


def test_per_size_monotonic(result):
    """逐码独立测量：围度/长度随码单调增（推码方向正确性旁证）。"""
    order = list(result.doc.sizes)
    for k in _STEP_GOLDS:
        vs = [result.measured[s].values[k] for s in order]
        assert all(b > a for a, b in zip(vs, vs[1:])), k


def test_front_bbox_linearity_probe(result):
    """前片净样 bbox 线性：dW≈6.8/dH≈5.3（mm；信息性，不入发射）+
    顶点数随码漂移（grade 绕开索引对应的实证）。"""
    ws, hs, nvs = [], [], []
    for s in result.doc.sizes:
        r = result.doc.by_block("前", s)[0].net_or_gross()
        bb = r.bbox()
        ws.append(bb[2] - bb[0])
        hs.append(bb[3] - bb[1])
        nvs.append(len(r.pts))
    dw = [b - a for a, b in zip(ws, ws[1:])]
    dh = [b - a for a, b in zip(hs, hs[1:])]
    assert all(abs(d - 6.8) <= 0.15 for d in dw)      # +6.7/+6.8
    assert all(abs(d - 5.3) <= 0.1 for d in dh)
    assert len(set(nvs)) > 1 and nvs == sorted(nvs)   # 188→195 漂移


def test_toml_roundtrip_expansion(result, tmp_path):
    """发射 -> load_size_run 展开：自基码双向累加复现逐码实测（±0.06）。"""
    from ylpattern.reverse.emit import build_size_file, render_toml
    data = build_size_file(result.measured[result.base], result.options,
                           result.size_run)
    path = tmp_path / "rev5028.toml"
    path.write_text(render_toml(data, ["回环"]), encoding="utf-8")
    run = load_size_run(str(path), fallback_base="M")
    assert run is not None and run.base == "M"
    assert run.labels == ("S", "M", "L", "XL", "2XL", "3XL")
    for label in run.labels:                     # ±0.12（见头注：S hip 0.08）
        m_run = run.measurements(label)
        m_ref = result.measured[label].values
        for k in _STEP_GOLDS:
            assert getattr(m_run, k) == pytest.approx(m_ref[k], abs=0.12), \
                (label, k)
    assert run.measurements("3XL").waist == pytest.approx(76.16, abs=0.06)
    assert run.measurements("S").waist == pytest.approx(64.34, abs=0.06)
