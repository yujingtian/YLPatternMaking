# -*- coding: utf-8 -*-
"""腰头特写裁剪支路（2026-09-30 特征尺度修复）。

诊断（三连实验，决策日志 §九）：整照经 VLM 端点输入降采样后腰头区
（整照里仅 ~200px 高）细节低于模型可分辨阈值——S2 整轮不报
waistband_type 落引擎默认、带判据定向问仍幻觉误读；同一张照裁腰头区
放大 2× 再喂，同模型立刻判对（straight→curved conf 0.9，证据正确）。

修法：S2 摄入（及腰头组聚焦复查）时自动从首张正面照 + 首张背面照裁
上带区放大，作**辅助图**附进同一次 VLM 调用——只喂模型细看，不进照片
指纹（vlm_cache 记账按用户原图）、不进探针/几何。姿态假设 = 平铺腰在
上（用户上传惯例；腰在下的构图裁不到，判据退回整照读法，二期可加
方向检测）。Pillow 缺失、解码失败、任何异常一律静默降级为无辅助图
（零打扰：辅助图失败绝不拦主提取）。
"""
from __future__ import annotations

from pathlib import Path

try:                      # Pillow 是 [agent] 可选依赖；缺了就不附辅助图
    from PIL import Image, ImageOps
    _PIL_OK = True
except ImportError:       # pragma: no cover - 环境无 Pillow 时
    Image = ImageOps = None
    _PIL_OK = False

# 裁剪框（占原图比例）：上带区 = 顶部 42% 高、两侧各收 6% 宽（去床单背景）
_BOX = (0.06, 0.0, 0.94, 0.42)
# 长边放大目标：小图 ×2（端点降采样后仍比整照里的腰头大 ~2 倍），
# 大图不再放大（端点反正要压，省字节）
_UPSCALE_LONG = 1200


def _crop_one(src: str, out_dir: str, tag: str) -> str | None:
    """单张裁剪：成功返回产物路径，任何失败返回 None。"""
    if not _PIL_OK:
        return None
    try:
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)       # 手机照 EXIF 转向
            w, h = im.size
            x0, y0, x1, y1 = _BOX
            box = (int(w * x0), int(h * y0), int(w * x1), int(h * y1))
            if box[2] - box[0] < 40 or box[3] - box[1] < 40:
                return None                        # 图太小，裁了也没意义
            region = im.crop(box)
            long_edge = max(region.size)
            scale = 2 if long_edge < _UPSCALE_LONG else 1
            if scale > 1:
                region = region.resize(
                    (region.width * scale, region.height * scale),
                    Image.LANCZOS)
            out = Path(out_dir) / f"wb_crop_{tag}.jpg"
            region.convert("RGB").save(out, "JPEG", quality=90)
            return str(out)
    except Exception:                              # 解码失败/损坏文件等
        return None


def make_waistband_crops(photos, photo_meta, out_dir):
    """从首张正面 + 首张背面照裁腰头区放大图。

    photos: 用户原图路径列表；photo_meta: [{category, note}]（可 None/
    缺齐——缺 meta 时首图按正面对待，且只裁一张防猜错）。返回
    (crop_paths, crop_metas, notes)：metas 与 paths 对齐、category=other
    （note 向模型说明来源与用途，走 build_prompt 照片清单既有渲染）；
    notes 为披露文案（进 ExtractResult.crop_notes）。全失败返回空三元组。
    """
    paths = [str(p) for p in (photos or []) if p]
    if not paths:
        return [], [], []
    metas = list(photo_meta or [])
    targets: list[tuple[str, str]] = []            # (路径, 正面|背面)
    first_front = first_back = None
    for i, p in enumerate(paths):
        cat = str((metas[i] or {}).get("category") or "").strip() \
            if i < len(metas) and metas[i] else ""
        if cat == "front" and first_front is None:
            first_front = p
        elif cat == "back" and first_back is None:
            first_back = p
    if first_front is None and first_back is None:
        first_front = paths[0]                     # 无 meta：首图按正面
    if first_front is not None:
        targets.append((first_front, "正面"))
    if first_back is not None:
        targets.append((first_back, "背面"))

    crop_paths, crop_metas, notes = [], [], []
    for src, side in targets:
        out = _crop_one(src, out_dir, "front" if side == "正面" else "back")
        if out is None:
            continue
        crop_paths.append(out)
        crop_metas.append({
            "category": "other",
            "note": f"工程自动辅助图：{side}照的腰头区放大裁剪（非用户上传），"
                    "专用于细看腰头形态（waistband_type）与后腰细节",
        })
    if crop_paths:
        notes.append(f"腰头放大辅助图 {len(crop_paths)} 张已附"
                     "（首张正面/背面照自动裁剪，特征尺度修复）")
    return crop_paths, crop_metas, notes
