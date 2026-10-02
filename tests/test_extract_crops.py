# -*- coding: utf-8 -*-
"""腰头特写裁剪支路金标（2026-09-30 特征尺度修复）。

诊断背景：整照经 VLM 端点降采样后腰头区细节低于可分辨阈值——S2 不报
waistband_type 落默认、复查维持误判；裁剪放大 2× 同模型立刻判对。本文件
钉 crops 模块行为：裁剪框/放大/类别选取/静默降级。管线接线（S2 附图、
prompt 必看项）在 test_extract_pipeline / test_extract_schema。
"""
from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from agent.extract import crops as crops_mod
from agent.extract.crops import (
    make_back_pocket_crops,
    make_front_pocket_crops,
    make_waistband_crops,
)


def _make_photo(path, w=800, h=1600):
    """合成平铺照：白底 + 顶部 1/4 处一条深色横带（模拟腰头区）。"""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), (240, 240, 240))
    d = ImageDraw.Draw(im)
    d.rectangle([w // 10, int(h * 0.2), w * 9 // 10, int(h * 0.28)],
                fill=(40, 50, 90))
    im.save(path, "JPEG", quality=90)
    return str(path)


def test_front_and_back_crops(tmp_path):
    """meta 类别选取：首张正面 + 首张背面各一张；尺寸=裁剪框×2 放大。"""
    p1 = _make_photo(tmp_path / "a.jpg")
    p2 = _make_photo(tmp_path / "b.jpg")
    out = tmp_path / "crops"
    out.mkdir()
    paths, metas, notes = make_waistband_crops(
        [p1, p2], [{"category": "front"}, {"category": "back"}], str(out))
    assert len(paths) == len(metas) == 2
    assert notes and "辅助图 2 张" in notes[0]
    for m in metas:
        assert m["category"] == "other"
        assert "腰头区放大" in m["note"]
    # 裁剪框 x∈[6%,94%] y∈[0,42%]，×2 放大（取整口径同 _crop_one）
    from PIL import Image
    w, h = Image.open(paths[0]).size
    assert w == (int(800 * 0.94) - int(800 * 0.06)) * 2
    assert h == (int(1600 * 0.42) - int(1600 * 0.0)) * 2


def test_no_meta_falls_back_to_first_photo(tmp_path):
    """缺 meta：首图按正面对待、只裁一张（防猜错背面）。"""
    p1 = _make_photo(tmp_path / "a.jpg")
    paths, metas, _ = make_waistband_crops([p1], None, str(tmp_path))
    assert len(paths) == 1 and "正面" in metas[0]["note"]


def test_garbage_image_degrades_silently(tmp_path):
    """损坏文件：不抛、零辅助图（零打扰，绝不拦主提取）。"""
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"\xff\xd8notreally")
    paths, metas, notes = make_waistband_crops(
        [str(bad)], [{"category": "front"}], str(tmp_path))
    assert paths == [] and metas == [] and notes == []


def test_pil_missing_degrades(monkeypatch, tmp_path):
    """Pillow 缺失：模块旗标置 False -> 空三元组。"""
    p1 = _make_photo(tmp_path / "a.jpg")
    monkeypatch.setattr(crops_mod, "_PIL_OK", False)
    assert make_waistband_crops([p1], None, str(tmp_path)) == ([], [], [])


def test_exif_orientation_respected(tmp_path):
    """EXIF 转向：横存竖拍（Orientation=6）的照，裁剪前先转正再裁上带区。"""
    from PIL import Image
    p = tmp_path / "exif.jpg"
    im = Image.new("RGB", (1600, 800), (240, 240, 240))
    exif = Image.Exif()
    exif[274] = 6                      # Orientation: 转 90°（竖拍）
    im.save(p, "JPEG", quality=90, exif=exif)
    paths, _m, _n = make_waistband_crops([str(p)], None, str(tmp_path))
    assert len(paths) == 1
    # 转正后 800x1600：裁剪框 (48,0,752,672) ×2；未转正则会是 (96,0,1504,336)×2
    w, h = Image.open(paths[0]).size
    assert (w, h) == (1408, 1344)


# -- 后贴袋裁块（2026-09-30 扩展；同 make_waistband_crops 机制） ------------------

def test_back_pocket_crop_from_marked_back(tmp_path):
    """meta 明示 back：从背面照裁后贴袋区一张；尺寸=口袋框×2 放大。"""
    p1 = _make_photo(tmp_path / "a.jpg")
    p2 = _make_photo(tmp_path / "b.jpg")
    paths, metas, notes = make_back_pocket_crops(
        [p1, p2], [{"category": "front"}, {"category": "back"}], str(tmp_path))
    assert len(paths) == len(metas) == 1
    assert "后贴袋区放大" in metas[0]["note"] and metas[0]["category"] == "other"
    assert notes and "1 张" in notes[0]
    # 裁剪框 x∈[5%,95%] y∈[24%,64%]，×2 放大（口径同 _crop_one）
    from PIL import Image
    w, h = Image.open(paths[0]).size
    assert w == (int(800 * 0.95) - int(800 * 0.05)) * 2
    assert h == (int(1600 * 0.64) - int(1600 * 0.24)) * 2


def test_back_pocket_single_photo_no_meta_crops(tmp_path):
    """无 meta 单照：裁一张（分面交给模型按画面自辨）。"""
    p1 = _make_photo(tmp_path / "a.jpg")
    paths, metas, _ = make_back_pocket_crops([p1], None, str(tmp_path))
    assert len(paths) == 1 and "后贴袋" in metas[0]["note"]


def test_back_pocket_no_guess_multi_unmarked(tmp_path):
    """多照无 meta：不猜面，零辅助图（后贴袋裁错面=主动错误证据）。"""
    p1 = _make_photo(tmp_path / "a.jpg")
    p2 = _make_photo(tmp_path / "b.jpg")
    assert make_back_pocket_crops([p1, p2], None, str(tmp_path)) == ([], [], [])


def test_back_pocket_garbage_degrades_silently(tmp_path):
    """损坏文件：不抛、零辅助图（零打扰）。"""
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"\xff\xd8notreally")
    paths, metas, notes = make_back_pocket_crops(
        [str(bad)], [{"category": "back"}], str(tmp_path))
    assert paths == [] and metas == [] and notes == []


# -- 前袋口裁块（2026-10-02 第三贴；同 make_back_pocket_crops 机制） --------------

def test_front_pocket_crop_from_marked_front(tmp_path):
    """meta 明示 front：从正面照裁前袋口区一张；尺寸=袋口框×2 放大。

    实照教训：整照上袋口曲线仅几十像素，VLM 判 bulge conf 0.65 而像素
    定标/用户口径为 tangent——特征尺度同腰头/后贴袋族，裁块放大解。
    """
    p1 = _make_photo(tmp_path / "a.jpg")
    p2 = _make_photo(tmp_path / "b.jpg")
    paths, metas, notes = make_front_pocket_crops(
        [p1, p2], [{"category": "front"}, {"category": "back"}], str(tmp_path))
    assert len(paths) == len(metas) == 1
    assert "前袋口区放大" in metas[0]["note"] and metas[0]["category"] == "other"
    assert "弧线落点" in metas[0]["note"]      # 判型读法=弧线最低点 vs 侧缝端点
    assert notes and "1 张" in notes[0]
    # 裁剪框 x∈[6%,94%] y∈[12%,56%]，×2 放大（口径同 _crop_one）
    from PIL import Image
    w, h = Image.open(paths[0]).size
    assert w == (int(800 * 0.94) - int(800 * 0.06)) * 2
    assert h == (int(1600 * 0.56) - int(1600 * 0.12)) * 2


def test_front_pocket_single_photo_no_meta_crops(tmp_path):
    """无 meta 单照：裁一张（分面交给模型按画面自辨）。"""
    p1 = _make_photo(tmp_path / "a.jpg")
    paths, metas, _ = make_front_pocket_crops([p1], None, str(tmp_path))
    assert len(paths) == 1 and "前袋口" in metas[0]["note"]


def test_front_pocket_no_guess_multi_unmarked(tmp_path):
    """多照无 meta：不猜面，零辅助图（前袋口在背面照不存在，裁错面=
    主动错误证据）。"""
    p1 = _make_photo(tmp_path / "a.jpg")
    p2 = _make_photo(tmp_path / "b.jpg")
    assert make_front_pocket_crops([p1, p2], None, str(tmp_path)) == ([], [], [])


def test_front_pocket_garbage_degrades_silently(tmp_path):
    """损坏文件：不抛、零辅助图（零打扰）。"""
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"\xff\xd8notreally")
    paths, metas, notes = make_front_pocket_crops(
        [str(bad)], [{"category": "front"}], str(tmp_path))
    assert paths == [] and metas == [] and notes == []
